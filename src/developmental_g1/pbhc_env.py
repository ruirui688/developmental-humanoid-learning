"""PBHC G1 task with competence-gated residual motor maturation.

PBHC remains the simulator and low-level residual-PD implementation.  This
module deliberately contains no reference-motion loader and no teacher-policy
interface, so the pure-developmental experiment cannot silently consume those
priors.
"""

from __future__ import annotations

from dataclasses import fields
from typing import Any

import torch

from humanoidverse.envs.legged_base_task.legged_robot_base import LeggedRobotBase

from .action_transform import MaturationTransform
from .maturation import (
    CompetenceSample,
    MaturationConfig,
    MaturationController,
    MaturationStage,
    StageTransition,
)


def _plain_mapping(config: Any) -> dict[str, Any]:
    """Convert a Hydra/OmegaConf mapping without importing OmegaConf here."""

    return {str(key): value for key, value in config.items()}


class DevelopmentalG1Env(LeggedRobotBase):
    """Reference-free G1 task layered on PBHC's legged robot base."""

    def __init__(self, config, device):
        super().__init__(config, device)

        developmental = config.developmental
        stages = tuple(
            MaturationStage(
                name=str(stage.name),
                enabled_groups=tuple(str(name) for name in stage.enabled_groups),
                action_range=float(stage.action_range),
                exploration_scale=float(stage.exploration_scale),
            )
            for stage in developmental.stages
        )
        gate_keys = {field.name for field in fields(MaturationConfig)}
        gate_values = {
            key: value
            for key, value in _plain_mapping(developmental.gate).items()
            if key in gate_keys
        }
        self.maturation_controller = MaturationController(
            stages, MaturationConfig(**gate_values)
        )
        initial_stage = int(developmental.initial_stage)
        if not 0 <= initial_stage < len(stages):
            raise ValueError(f"invalid initial maturation stage {initial_stage}")
        self.maturation_controller.stage_index = initial_stage
        self.maturation_mode = str(developmental.mode)
        if self.maturation_mode not in {"locked", "fixed", "adaptive"}:
            raise ValueError(
                "developmental.mode must be one of locked, fixed, adaptive"
            )
        self.fixed_transition_environment_steps = tuple(
            int(step) for step in developmental.get("fixed_transition_environment_steps", [])
        )
        self.maturation_schedule_environment_steps = 0
        # The algorithm enables this only around PPO rollout collection. Reset
        # warm-ups and held-out evaluation are separate budgets.
        self.count_maturation_schedule_steps = False
        if self.maturation_mode == "fixed":
            # Validate the schedule before creating a simulator rollout.
            self.maturation_controller.follow_fixed_schedule(
                0, self.fixed_transition_environment_steps
            )
        self.maturation_gate_enabled = bool(developmental.gate.enabled)
        if self.maturation_mode == "adaptive" and not self.maturation_gate_enabled:
            raise ValueError("adaptive maturation requires gate.enabled=true")
        self.maturation_transform = MaturationTransform(
            self.dof_names,
            {
                str(group): tuple(str(name) for name in names)
                for group, names in developmental.joint_groups.items()
            },
        )
        reset_range = tuple(float(value) for value in developmental.reset_dof_scale_range)
        if len(reset_range) != 2 or not 0.0 < reset_range[0] <= reset_range[1]:
            raise ValueError("reset_dof_scale_range must be two positive ordered values")
        self.reset_dof_scale_range = reset_range
        root_velocity_range = tuple(
            float(value) for value in developmental.reset_root_velocity_range
        )
        if (
            len(root_velocity_range) != 2
            or root_velocity_range[0] > root_velocity_range[1]
        ):
            raise ValueError(
                "reset_root_velocity_range must contain two ordered values"
            )
        self.reset_root_velocity_range = root_velocity_range
        self.waist_alignment_indices = torch.tensor(
            [
                self.dof_names.index("waist_pitch_joint"),
                self.dof_names.index("waist_roll_joint"),
            ],
            device=self.device,
            dtype=torch.long,
        )
        self.raw_policy_actions = torch.zeros_like(self.actions)
        self._refresh_maturation_parameters()

    def _refresh_maturation_parameters(self) -> None:
        mask, action_range = self.maturation_transform.parameters(
            self.maturation_controller.stage,
            device=self.device,
            dtype=self.actions.dtype,
        )
        self.maturation_mask = mask
        self.maturation_action_range = action_range

    def _reset_dofs(self, env_ids, target_state=None):
        """Reset only selected defaults; PBHC upstream multiplies all env rows."""

        if target_state is not None:
            self.simulator.dof_pos[env_ids] = target_state[..., 0]
            self.simulator.dof_vel[env_ids] = target_state[..., 1]
        else:
            scale = torch.empty(
                (len(env_ids), self.num_dof), device=self.device
            ).uniform_(*self.reset_dof_scale_range)
            self.simulator.dof_pos[env_ids] = self.default_dof_pos[env_ids] * scale
            self.simulator.dof_vel[env_ids] = 0.0

    def _reset_root_states(self, env_ids, target_root_states=None):
        """Make nominal and disturbed initial velocity conditions explicit."""

        super()._reset_root_states(env_ids, target_root_states)
        if target_root_states is None:
            self.simulator.robot_root_states[env_ids, 7:13] = torch.empty(
                (len(env_ids), 6), device=self.device
            ).uniform_(*self.reset_root_velocity_range)

    def _post_config_observation_callback(self):
        """Seed reset histories with the first physical observation.

        PBHC clears every history slot on reset and normally returns that
        all-zero history to the policy for one control step.  Zero is not a
        neutral value for joint positions or projected gravity, so it creates
        an artificial observation discontinuity and an avoidable start-up
        recovery motion.  Repeating the first post-reset observation is the
        causal initialization available on a real robot before control starts.
        """

        reset_ids = self.reset_buf.nonzero(as_tuple=False).flatten()
        if reset_ids.numel() > 0:
            for key, history in self.history_handler.history.items():
                current = self.hist_obs_dict[key][reset_ids]
                history[reset_ids] = current.unsqueeze(1).expand(
                    -1, history.shape[1], -1
                )
            seeded_history = self._get_obs_history()
            for obs_key, obs_config in self.config.obs.obs_dict.items():
                if "history" in obs_config:
                    self.obs_buf_dict_raw[obs_key]["history"] = seeded_history
        super()._post_config_observation_callback()

    def _pre_physics_step(self, actions):
        self.raw_policy_actions[:] = actions
        executed, _, _ = self.maturation_transform.apply(
            actions, self.maturation_controller.stage
        )
        super()._pre_physics_step(executed)

    def update_competence(self, sample: CompetenceSample) -> StageTransition | None:
        """Update the global stage from one fixed, held-out evaluation window.

        Training rollouts do not call this automatically.  Keeping promotion
        outside episode reset logic prevents favourable training resets from
        masquerading as held-out competence.
        """

        if self.maturation_mode != "adaptive" or not self.maturation_gate_enabled:
            return None
        transition = self.maturation_controller.observe(sample)
        if transition is not None:
            self._refresh_maturation_parameters()
        return transition

    def maturation_state_dict(self) -> dict[str, int | float]:
        state = self.maturation_controller.state_dict()
        state["schedule_environment_steps"] = self.maturation_schedule_environment_steps
        return state

    def load_maturation_state_dict(self, state: dict[str, int | float]) -> None:
        controller_state = dict(state)
        self.maturation_schedule_environment_steps = int(
            controller_state.pop("schedule_environment_steps", 0)
        )
        self.maturation_controller.load_state_dict(controller_state)
        self._refresh_maturation_parameters()

    def _update_tasks_callback(self):
        super()._update_tasks_callback()
        if self.count_maturation_schedule_steps:
            self.maturation_schedule_environment_steps += self.num_envs
        if self.maturation_mode == "fixed":
            transition = self.maturation_controller.follow_fixed_schedule(
                self.maturation_schedule_environment_steps,
                self.fixed_transition_environment_steps,
            )
            if transition is not None:
                self._refresh_maturation_parameters()
        torque_ratio = torch.abs(self.torques) / self.torque_limits.clamp_min(1e-6)
        nonfoot_force = torch.linalg.vector_norm(
            self.simulator.contact_forces[:, self.penalised_contact_indices, :], dim=-1
        )
        termination_contact = torch.linalg.vector_norm(
            self.simulator.contact_forces[:, self.termination_contact_indices, :],
            dim=-1,
        ) > 1.0
        termination_contact_height = self.simulator._rigid_body_pos[
            :, self.termination_contact_indices, 2
        ]
        self.log_dict["development/maturation_stage"] = torch.tensor(
            self.maturation_controller.normalized_stage, device=self.device
        )
        self.log_dict["development/active_joint_fraction"] = self.maturation_mask.mean()
        self.log_dict["development/exploration_scale"] = torch.tensor(
            self.maturation_controller.stage.exploration_scale, device=self.device
        )
        self.log_dict["development/environment_steps"] = torch.tensor(
            float(self.maturation_schedule_environment_steps),
            device=self.device,
            dtype=self.actions.dtype,
        )
        self.log_dict["risk/torque_saturation_fraction"] = (torque_ratio >= 0.95).float().mean()
        self.log_dict["risk/nonfoot_contact_fraction"] = (nonfoot_force > 1.0).float().mean()
        self.log_dict["risk/severe_impact_fraction"] = (
            nonfoot_force > float(self.config.developmental.severe_impact_force)
        ).float().mean()
        self.log_dict["risk/elevated_termination_contact_fraction"] = (
            termination_contact & (termination_contact_height > 0.25)
        ).float().mean()
        self.log_dict["risk/ground_termination_contact_fraction"] = (
            termination_contact & (termination_contact_height <= 0.25)
        ).float().mean()

    # Deployable observations: IMU-like signals, joint state, action history,
    # and the capability condition.  Contact-force tensors are intentionally
    # absent from actor observations.
    def _get_obs_maturation_stage(self):
        return torch.full(
            (self.num_envs, 1),
            self.maturation_controller.normalized_stage,
            device=self.device,
            dtype=self.actions.dtype,
        )

    def _get_obs_maturation_mask(self):
        return self.maturation_mask.unsqueeze(0).expand(self.num_envs, -1)

    def _get_obs_maturation_range(self):
        return self.maturation_action_range.unsqueeze(0).expand(self.num_envs, -1)

    def _get_obs_body_schema_target(self):
        """52-D privileged training label, never part of the actor input."""

        return torch.cat(
            (
                self.simulator.dof_pos - self.default_dof_pos,
                self.simulator.dof_vel,
                self.projected_gravity,
                self.base_ang_vel,
            ),
            dim=-1,
        )

    def _get_obs_executed_actions(self):
        """Residual action actually consumed after PBHC's delay model."""

        return self.actions_after_delay

    # Reference-free postural task rewards.  Raw risk indicators are logged
    # separately above so reward optimisation cannot hide unsafe behaviour.
    def _reward_developmental_upright(self):
        error = torch.sum(torch.square(self.projected_gravity[:, :2]), dim=1)
        return torch.exp(-error / float(self.config.developmental.upright_sigma))

    def _reward_developmental_height(self):
        error = self.simulator.robot_root_states[:, 2] - float(
            self.config.developmental.target_base_height
        )
        return torch.exp(
            -torch.square(error) / float(self.config.developmental.height_sigma)
        )

    def _reward_developmental_stillness(self):
        error = (
            torch.sum(torch.square(self.base_lin_vel), dim=1)
            + torch.sum(torch.square(self.base_ang_vel), dim=1)
            + 0.02 * torch.sum(torch.square(self.simulator.dof_vel), dim=1)
        )
        return torch.exp(-error / float(self.config.developmental.stillness_sigma))

    def _reward_developmental_waist_alignment(self):
        deviation = self.simulator.dof_pos[:, self.waist_alignment_indices] - (
            self.default_dof_pos[:, self.waist_alignment_indices]
        )
        # This is paired with a negative reward scale. A quadratic term keeps
        # a usable gradient even for the strongly leaned policy discovered by
        # the first survival-only standing run.
        return torch.sum(torch.square(deviation), dim=1)

    def _reward_developmental_double_support(self):
        return torch.all(self.contacts_filt > 0.5, dim=1).float()

    def _reward_developmental_nonfoot_impact(self):
        forces = torch.linalg.vector_norm(
            self.simulator.contact_forces[:, self.penalised_contact_indices, :], dim=-1
        )
        return torch.sum(
            torch.clamp(
                forces / float(self.config.developmental.severe_impact_force),
                min=0.0,
                max=2.0,
            ),
            dim=1,
        )

    def _reward_developmental_raw_action_magnitude(self):
        """Keep the pre-tanh Gaussian policy in a resolvable control range."""

        return torch.mean(torch.square(self.raw_policy_actions), dim=1)
