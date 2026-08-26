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
from .assistive_support import AssistanceConfig, caregiver_force
from .capability_frontier import (
    CapabilityFrontier,
    FrontierConfig,
    FrontierEvidence,
)
from .developmental_events import (
    DevelopmentalEventConfig,
    SustainedDevelopmentalEvents,
)
from .developmental_phase_gate import (
    DevelopmentalPhaseGate,
    PhaseEvidence,
    PhaseGateConfig,
)
from .ground_development import (
    blend_pose_sampling_probabilities,
    competence_weighted_pose_probabilities,
    frontier_preserving_score,
    noncompensatory_pair_score,
    normalized_torque_headroom_cost,
    rehearsal_bounded_pose_probabilities,
    rise_progress_score,
    safety_refined_skill_score,
    stage_goal_score,
)
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
        # PBHC may invoke reset hooks while constructing the base class. Keep
        # the new ground curriculum dormant until all pose tensors exist.
        self.ground_curriculum_enabled = False
        self._ground_curriculum_ready = False
        self._assistance_ready = False
        self._developmental_events_ready = False
        self.capability_frontier_enabled = False
        self._phase_gate_ready = False
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
        self.action_smoothing_alpha = float(
            developmental.action_smoothing_alpha
        )
        if not 0.0 < self.action_smoothing_alpha <= 1.0:
            raise ValueError("action_smoothing_alpha must be in (0, 1]")
        self.waist_alignment_indices = torch.tensor(
            [
                self.dof_names.index("waist_pitch_joint"),
                self.dof_names.index("waist_roll_joint"),
            ],
            device=self.device,
            dtype=torch.long,
        )
        self.raw_policy_actions = torch.zeros_like(self.actions)
        self.smoothed_maturation_actions = torch.zeros_like(self.actions)
        self._configure_ground_curriculum(developmental)
        self._configure_capability_frontier(developmental)
        self._configure_phase_gate(developmental)
        self._configure_assistance(developmental)
        self._configure_developmental_events(developmental)
        self._refresh_maturation_parameters()

    def _configure_phase_gate(self, developmental) -> None:
        gate = developmental.get("phase_gate", None)
        if gate is None or not bool(gate.get("enabled", False)):
            return
        self.developmental_phase_gate = DevelopmentalPhaseGate(
            PhaseGateConfig(
                metric_names=tuple(str(name) for name in gate.metric_names),
                metric_thresholds=tuple(float(value) for value in gate.metric_thresholds),
                required_safe_fraction=float(gate.required_safe_fraction),
                required_low_saturation_fraction=float(
                    gate.required_low_saturation_fraction
                ),
                confirmation_windows=int(gate.confirmation_windows),
            )
        )
        if len(self.developmental_phase_gate.config.metric_names) != len(
            self.maturation_controller.stages
        ):
            raise ValueError("phase gate must define one metric per maturation stage")
        self._phase_gate_ready = True

    def _configure_developmental_events(self, developmental) -> None:
        events = developmental.get("developmental_events", None)
        if events is None or not bool(events.get("enabled", False)):
            return
        self.developmental_event_tracker = SustainedDevelopmentalEvents(
            self.num_envs,
            self.device,
            DevelopmentalEventConfig(
                roll_angle_rad=float(events.roll_angle_rad),
                bracing_min_orientation_change_rad=float(
                    events.bracing_min_orientation_change_rad
                ),
                rolling_min_height=float(events.rolling_min_height),
                raised_height=float(events.raised_height),
                bracing_min_height=float(events.bracing_min_height),
                standing_height=float(events.standing_height),
                standing_upright_score=float(events.standing_upright_score),
                standing_max_speed=float(events.standing_max_speed),
                support_contact_count=int(events.support_contact_count),
                foot_contact_count=int(events.foot_contact_count),
                roll_steps=int(events.roll_steps),
                brace_steps=int(events.brace_steps),
                raised_steps=int(events.raised_steps),
                upright_steps=int(events.upright_steps),
                independent_standing_steps=int(events.independent_standing_steps),
            ),
        )
        support_body_names = tuple(str(name) for name in events.support_body_names)
        if not support_body_names:
            raise ValueError("developmental events need explicit support bodies")
        self.developmental_support_body_indices = torch.tensor(
            [self.body_names.index(name) for name in support_body_names],
            device=self.device,
            dtype=torch.long,
        )
        self.ground_initial_root_quat = self.simulator.robot_root_states[:, 3:7].clone()
        self._developmental_events_ready = True

    def _configure_assistance(self, developmental) -> None:
        assistance = developmental.get("assistance", None)
        if assistance is None or not bool(assistance.get("enabled", False)):
            return
        fractions = tuple(float(value) for value in assistance.fraction_by_stage)
        if len(fractions) != len(self.maturation_controller.stages) or any(
            value < 0.0 or value > 1.0 for value in fractions
        ):
            raise ValueError("assistance fractions must match stages and lie in [0, 1]")
        self.assistance_fraction_by_stage = fractions
        self.assistance_config = AssistanceConfig(
            max_upward_force=float(assistance.max_upward_force),
            max_horizontal_force=float(assistance.max_horizontal_force),
            horizontal_stiffness=float(assistance.horizontal_stiffness),
            horizontal_damping=float(assistance.horizontal_damping),
            activation_height=float(assistance.activation_height),
            full_support_height=float(assistance.full_support_height),
        )
        self.assistance_body_index = self.body_names.index(str(assistance.body_name))
        self.assistance_anchor_xy = self.simulator.robot_root_states[:, :2].clone()
        self.assistance_force = torch.zeros(self.num_envs, 3, device=self.device)
        self.assistance_impulse = torch.zeros(self.num_envs, device=self.device)
        self.assistance_abs_work = torch.zeros(self.num_envs, device=self.device)
        self.assistance_peak_force = torch.zeros(self.num_envs, device=self.device)
        self._assistance_force_tensor = torch.zeros(
            self.num_envs, self.num_bodies, 3, device=self.device
        )
        self._assistance_position_tensor = torch.zeros_like(
            self._assistance_force_tensor
        )
        self._assistance_ready = True

    def _configure_capability_frontier(self, developmental) -> None:
        frontier = developmental.get("capability_frontier", None)
        if frontier is None or not bool(frontier.get("enabled", False)):
            return
        self.capability_frontier = CapabilityFrontier(
            FrontierConfig(
                floor_height=float(frontier.floor_height),
                final_height=float(frontier.final_height),
                initial_upright_score=float(frontier.initial_upright_score),
                final_upright_score=float(frontier.final_upright_score),
                height_margin=float(frontier.height_margin),
                upright_margin=float(frontier.upright_margin),
                required_success_fraction=float(frontier.required_success_fraction),
                required_safe_fraction=float(frontier.required_safe_fraction),
                maximum_saturation_fraction=float(frontier.maximum_saturation_fraction),
                required_schema_accuracy=float(frontier.required_schema_accuracy),
                confirmation_windows=int(frontier.confirmation_windows),
            )
        )
        self.capability_frontier_enabled = True

    def _configure_ground_curriculum(self, developmental) -> None:
        """Build ground-start reset poses and stage goals from auditable config."""

        curriculum = developmental.get("ground_curriculum", None)
        if curriculum is None or not bool(curriculum.get("enabled", False)):
            return
        poses = list(curriculum.reset_poses)
        if not poses:
            raise ValueError("ground_curriculum.reset_poses must not be empty")
        root_states = []
        dof_positions = []
        pose_names = []
        for pose in poses:
            position = torch.tensor(pose.root_pos, device=self.device, dtype=self.actions.dtype)
            rotation = torch.tensor(pose.root_rot, device=self.device, dtype=self.actions.dtype)
            if position.numel() != 3 or rotation.numel() != 4:
                raise ValueError("ground reset poses need 3-D positions and xyzw quaternions")
            rotation_norm = torch.linalg.vector_norm(rotation)
            if not torch.isfinite(rotation_norm) or float(rotation_norm) <= 0.0:
                raise ValueError("ground reset quaternion must be finite and non-zero")
            rotation = rotation / rotation_norm
            root_state = self.base_init_state.clone()
            root_state[:3] = position
            root_state[3:7] = rotation
            root_state[7:13] = 0.0
            dof_position = self.default_dof_pos[0].clone()
            for joint_name, angle in pose.get("joint_angles", {}).items():
                if joint_name not in self.dof_names:
                    raise ValueError(f"unknown ground reset joint {joint_name!r}")
                dof_position[self.dof_names.index(joint_name)] = float(angle)
            root_states.append(root_state)
            dof_positions.append(dof_position)
            pose_names.append(str(pose.name))

        stage_count = len(self.maturation_controller.stages)
        stage_goals = list(curriculum.stage_goals)
        if len(stage_goals) != stage_count:
            raise ValueError(
                "ground_curriculum.stage_goals must match maturation stage count"
            )
        self.ground_pose_root_states = torch.stack(root_states)
        self.ground_pose_dof_positions = torch.stack(dof_positions)
        self.ground_pose_names = tuple(pose_names)
        self.ground_reset_pose_indices = torch.zeros(
            self.num_envs, device=self.device, dtype=torch.long
        )
        self.ground_initial_projected_gravity = torch.zeros(
            self.num_envs, 3, device=self.device, dtype=self.actions.dtype
        )
        self.ground_pose_sampling_weights = torch.full(
            (len(pose_names),),
            1.0 / len(pose_names),
            device=self.device,
            dtype=self.actions.dtype,
        )
        self.ground_reset_joint_noise = float(curriculum.reset_joint_noise)
        self.ground_reset_xy_jitter = float(curriculum.reset_xy_jitter)
        if self.ground_reset_joint_noise < 0.0 or self.ground_reset_xy_jitter < 0.0:
            raise ValueError("ground reset noise and jitter cannot be negative")
        self.developmental_goal_height = torch.tensor(
            [float(goal.base_height) for goal in stage_goals],
            device=self.device,
            dtype=self.actions.dtype,
        )
        self.developmental_goal_upright_weight = torch.tensor(
            [float(goal.upright_weight) for goal in stage_goals],
            device=self.device,
            dtype=self.actions.dtype,
        )
        self.developmental_goal_exploration_weight = torch.tensor(
            [float(goal.exploration_weight) for goal in stage_goals],
            device=self.device,
            dtype=self.actions.dtype,
        )
        self.developmental_goal_joint_speed = torch.tensor(
            [float(goal.joint_speed) for goal in stage_goals],
            device=self.device,
            dtype=self.actions.dtype,
        )
        weights = (
            self.developmental_goal_upright_weight
            + self.developmental_goal_exploration_weight
        )
        if torch.any((weights < 0.0) | (weights > 1.0)):
            raise ValueError("ground stage goal weights must be non-negative and sum to <= 1")
        self.developmental_goal_height_scale = float(curriculum.height_scale)
        self.developmental_rise_initial_target = float(
            curriculum.get("rise_initial_target", 0.28)
        )
        self.developmental_rise_required_success_fraction = float(
            curriculum.get("rise_required_success_fraction", 0.40)
        )
        if not 0.12 < self.developmental_rise_initial_target <= float(
            self.developmental_goal_height[2]
        ):
            raise ValueError("initial rise target must lie above the floor and within stage 2")
        if not 0.0 <= self.developmental_rise_required_success_fraction <= 1.0:
            raise ValueError("rise required success fraction must be in [0, 1]")
        self.developmental_goal_upright_sigma = float(curriculum.upright_sigma)
        self.developmental_goal_joint_speed_sigma = float(curriculum.joint_speed_sigma)
        self.ground_safe_support_force = float(curriculum.safe_support_force)
        self.ground_safe_roll_angular_speed = float(
            curriculum.safe_roll_angular_speed
        )
        if min(
            self.developmental_goal_height_scale,
            self.developmental_goal_upright_sigma,
            self.developmental_goal_joint_speed_sigma,
            self.ground_safe_support_force,
            self.ground_safe_roll_angular_speed,
        ) <= 0.0:
            raise ValueError("ground curriculum scales must be positive")
        self.ground_curriculum_enabled = True
        self._ground_curriculum_ready = True

    def update_ground_pose_sampling(
        self, pose_competence: list[float] | tuple[float, ...]
    ) -> None:
        """Allocate training resets toward weak poses without biasing evaluation."""

        if not self._ground_curriculum_ready:
            return
        competence = torch.as_tensor(
            pose_competence,
            device=self.device,
            dtype=self.ground_pose_sampling_weights.dtype,
        )
        if competence.shape != self.ground_pose_sampling_weights.shape:
            raise ValueError("pose competence must match configured reset poses")
        if not torch.isfinite(competence).all():
            raise ValueError("pose competence must be finite")
        # Keep mastered poses in rehearsal while assigning most new attempts
        # to the weakest observed capability boundary.
        target_weights = rehearsal_bounded_pose_probabilities(
            competence_weighted_pose_probabilities(competence)
        )
        self.ground_pose_sampling_weights = blend_pose_sampling_probabilities(
            self.ground_pose_sampling_weights,
            target_weights,
        )

    def _refresh_maturation_parameters(self) -> None:
        mask, action_range = self.maturation_transform.parameters(
            self.maturation_controller.stage,
            device=self.device,
            dtype=self.actions.dtype,
        )
        self.maturation_mask = mask
        self.maturation_action_range = action_range
        if self._assistance_ready:
            self.assistance_fraction = self.assistance_fraction_by_stage[
                self.maturation_controller.stage_index
            ]
        if (
            self.capability_frontier_enabled
            and self.maturation_controller.stage_index == 2
        ):
            self.capability_frontier.height_target = max(
                self.capability_frontier.height_target,
                self.developmental_rise_initial_target,
            )

    def _reset_dofs(self, env_ids, target_state=None):
        """Reset only selected defaults; PBHC upstream multiplies all env rows."""

        if target_state is not None:
            self.simulator.dof_pos[env_ids] = target_state[..., 0]
            self.simulator.dof_vel[env_ids] = target_state[..., 1]
        elif self._ground_curriculum_ready:
            pose_indices = self.ground_reset_pose_indices[env_ids]
            targets = self.ground_pose_dof_positions[pose_indices]
            if self.ground_reset_joint_noise > 0.0:
                targets = targets + torch.empty_like(targets).uniform_(
                    -self.ground_reset_joint_noise, self.ground_reset_joint_noise
                )
            self.simulator.dof_pos[env_ids] = targets
            self.simulator.dof_vel[env_ids] = 0.0
        else:
            scale = torch.empty(
                (len(env_ids), self.num_dof), device=self.device
            ).uniform_(*self.reset_dof_scale_range)
            self.simulator.dof_pos[env_ids] = self.default_dof_pos[env_ids] * scale
            self.simulator.dof_vel[env_ids] = 0.0

    def _reset_root_states(self, env_ids, target_root_states=None):
        """Make nominal and disturbed initial velocity conditions explicit."""

        if target_root_states is not None or not self._ground_curriculum_ready:
            super()._reset_root_states(env_ids, target_root_states)
        else:
            pose_indices = self.ground_reset_pose_indices[env_ids]
            root_states = self.ground_pose_root_states[pose_indices].clone()
            root_states[:, :3] += self.env_origins[env_ids]
            if self.ground_reset_xy_jitter > 0.0:
                root_states[:, :2] += torch.empty(
                    len(env_ids), 2, device=self.device
                ).uniform_(-self.ground_reset_xy_jitter, self.ground_reset_xy_jitter)
            self.simulator.robot_root_states[env_ids] = root_states
        if target_root_states is None:
            injected_velocity = torch.empty(
                (len(env_ids), 6), device=self.device
            ).uniform_(*self.reset_root_velocity_range)
            self.simulator.robot_root_states[env_ids, 7:13] = injected_velocity
            if not hasattr(self, "last_injected_root_velocity"):
                self.last_injected_root_velocity = torch.zeros(
                    self.num_envs, 6, device=self.device
                )
            self.last_injected_root_velocity[env_ids] = injected_velocity
        if self._assistance_ready and target_root_states is None:
            self.assistance_anchor_xy[env_ids] = self.simulator.robot_root_states[
                env_ids, :2
            ]
        if self._developmental_events_ready and target_root_states is None:
            self.ground_initial_root_quat[env_ids] = self.simulator.robot_root_states[
                env_ids, 3:7
            ]

    def _reset_robot_states_callback(self, env_ids, target_states=None):
        if (
            self._ground_curriculum_ready
            and target_states is None
            and len(env_ids) > 0
        ):
            weights = (
                torch.ones_like(self.ground_pose_sampling_weights)
                if self.is_evaluating
                else self.ground_pose_sampling_weights
            )
            self.ground_reset_pose_indices[env_ids] = torch.multinomial(
                weights,
                len(env_ids),
                replacement=True,
            )
        super()._reset_robot_states_callback(env_ids, target_states)

    def _update_reset_buf(self):
        if self._ground_curriculum_ready:
            # Lying, rolling and supported ground contact are valid states.
            # Episodes end at the common horizon; risk is measured explicitly.
            return
        super()._update_reset_buf()

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
            self.ground_initial_projected_gravity[reset_ids] = (
                self.projected_gravity[reset_ids]
            )
            for obs_key, obs_config in self.config.obs.obs_dict.items():
                if "initial_projected_gravity" in obs_config:
                    self.obs_buf_dict_raw[obs_key][
                        "initial_projected_gravity"
                    ][reset_ids] = self.ground_initial_projected_gravity[reset_ids]
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

    def _reset_buffers_callback(self, env_ids, target_buf=None):
        super()._reset_buffers_callback(env_ids, target_buf)
        if hasattr(self, "smoothed_maturation_actions"):
            self.smoothed_maturation_actions[env_ids] = 0.0
        if self._assistance_ready:
            self.assistance_impulse[env_ids] = 0.0
            self.assistance_abs_work[env_ids] = 0.0
            self.assistance_peak_force[env_ids] = 0.0
        if self._developmental_events_ready:
            self.developmental_event_tracker.reset(env_ids)

    def _pre_physics_step(self, actions):
        self.raw_policy_actions[:] = actions
        executed, _, _ = self.maturation_transform.apply(
            actions, self.maturation_controller.stage
        )
        alpha = self.action_smoothing_alpha
        self.smoothed_maturation_actions.mul_(1.0 - alpha).add_(
            executed, alpha=alpha
        )
        super()._pre_physics_step(self.smoothed_maturation_actions)

    def _apply_force_in_physics_step(self):
        super()._apply_force_in_physics_step()
        if not self._assistance_ready or self.assistance_fraction <= 0.0:
            if self._assistance_ready:
                self.assistance_force.zero_()
            return
        self.assistance_force = caregiver_force(
            base_position=self.simulator.robot_root_states[:, :3],
            base_velocity=self.simulator.robot_root_states[:, 7:10],
            anchor_xy=self.assistance_anchor_xy,
            assistance_fraction=self.assistance_fraction,
            config=self.assistance_config,
        )
        self._assistance_force_tensor.zero_()
        self._assistance_force_tensor[:, self.assistance_body_index] = (
            self.assistance_force
        )
        self._assistance_position_tensor.copy_(self.simulator._rigid_body_pos)
        self.simulator.apply_rigid_body_force_at_pos_tensor(
            self._assistance_force_tensor, self._assistance_position_tensor
        )
        force_norm = torch.linalg.vector_norm(self.assistance_force, dim=1)
        self.assistance_impulse += force_norm * self.sim_dt
        self.assistance_abs_work += torch.abs(
            torch.sum(
                self.assistance_force
                * self.simulator.robot_root_states[:, 7:10],
                dim=1,
            )
        ) * self.sim_dt
        self.assistance_peak_force = torch.maximum(
            self.assistance_peak_force, force_norm
        )

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
        if self.capability_frontier_enabled:
            state["capability_frontier"] = self.capability_frontier.state_dict()
        if self._phase_gate_ready:
            state["developmental_phase_gate"] = (
                self.developmental_phase_gate.state_dict()
            )
        if self._ground_curriculum_ready:
            state["ground_pose_sampling_weights"] = (
                self.ground_pose_sampling_weights.detach().cpu().tolist()
            )
        return state

    def load_maturation_state_dict(self, state: dict[str, int | float]) -> None:
        controller_state = dict(state)
        self.maturation_schedule_environment_steps = int(
            controller_state.pop("schedule_environment_steps", 0)
        )
        frontier_state = controller_state.pop("capability_frontier", None)
        phase_gate_state = controller_state.pop("developmental_phase_gate", None)
        ground_pose_sampling_weights = controller_state.pop(
            "ground_pose_sampling_weights", None
        )
        self.maturation_controller.load_state_dict(controller_state)
        if frontier_state is not None:
            if not self.capability_frontier_enabled:
                raise ValueError("checkpoint contains a disabled capability frontier")
            self.capability_frontier.load_state_dict(frontier_state)
        if phase_gate_state is not None:
            if not self._phase_gate_ready:
                raise ValueError("checkpoint contains a disabled phase gate")
            self.developmental_phase_gate.load_state_dict(phase_gate_state)
        if ground_pose_sampling_weights is not None:
            weights = torch.as_tensor(
                ground_pose_sampling_weights,
                device=self.device,
                dtype=self.ground_pose_sampling_weights.dtype,
            )
            if weights.shape != self.ground_pose_sampling_weights.shape:
                raise ValueError("checkpoint ground pose weights do not match config")
            if not torch.isfinite(weights).all() or bool(torch.any(weights <= 0.0)):
                raise ValueError(
                    "checkpoint ground pose weights must be finite and positive"
                )
            self.ground_pose_sampling_weights = rehearsal_bounded_pose_probabilities(
                weights
            )
        self._refresh_maturation_parameters()

    def update_capability_frontier(self, evidence: FrontierEvidence):
        if not self.capability_frontier_enabled:
            raise RuntimeError("capability frontier is disabled")
        if self.capability_frontier.calibrated:
            update = self.capability_frontier.observe(evidence)
        else:
            update = self.capability_frontier.calibrate(evidence)
        target_stage = min(
            int(
                self.capability_frontier.progress
                * len(self.maturation_controller.stages)
            ),
            len(self.maturation_controller.stages) - 1,
        )
        if target_stage > self.maturation_controller.stage_index:
            self.maturation_controller.stage_index = target_stage
            self.maturation_controller.windows_in_stage = 0
            self.maturation_controller.promotion_streak = 0
            self.maturation_controller.demotion_streak = 0
            self._refresh_maturation_parameters()
        return update

    def update_rise_frontier(self, evidence: FrontierEvidence):
        """Advance only the within-stage supported-rise height subgoal."""

        if not self.capability_frontier_enabled:
            raise RuntimeError("capability frontier is disabled")
        ceiling = float(self.developmental_goal_height[2])
        return self.capability_frontier.observe_height_only(
            evidence,
            ceiling=ceiling,
            required_success_fraction=(
                self.developmental_rise_required_success_fraction
            ),
        )

    def update_developmental_phase(self, evidence: PhaseEvidence):
        if not self._phase_gate_ready:
            raise RuntimeError("developmental phase gate is disabled")
        update = self.developmental_phase_gate.observe(evidence)
        if update.advanced:
            self.maturation_controller.stage_index = update.stage
            self.maturation_controller.windows_in_stage = 0
            self._refresh_maturation_parameters()
        return update

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
        if self._developmental_events_ready:
            quaternion_similarity = torch.abs(
                torch.sum(
                    self.simulator.robot_root_states[:, 3:7]
                    * self.ground_initial_root_quat,
                    dim=1,
                )
            ).clamp(0.0, 1.0)
            orientation_change = 2.0 * torch.acos(quaternion_similarity)
            support_indices = self.developmental_support_body_indices
            contact_force = torch.linalg.vector_norm(
                self.simulator.contact_forces[:, support_indices, :], dim=-1
            )
            low_support = (
                self.simulator._rigid_body_pos[:, support_indices, 2] <= 0.25
            )
            support_count = ((contact_force > 5.0) & low_support).sum(dim=1)
            foot_contact_count = (self.contacts_filt > 0.5).sum(dim=1)
            gravity_error = torch.sum(
                torch.square(
                    self.projected_gravity
                    - torch.tensor(
                        [0.0, 0.0, -1.0],
                        device=self.device,
                        dtype=self.projected_gravity.dtype,
                    )
                ),
                dim=1,
            )
            upright_score = torch.exp(
                -gravity_error / self.developmental_goal_upright_sigma
            )
            assistance_fraction = (
                self.assistance_fraction if self._assistance_ready else 0.0
            )
            self.developmental_event_tracker.update(
                orientation_change_rad=orientation_change,
                support_contact_count=support_count,
                foot_contact_count=foot_contact_count,
                base_height=self.simulator.robot_root_states[:, 2],
                upright_score=upright_score,
                base_speed=torch.linalg.vector_norm(
                    self.simulator.robot_root_states[:, 7:10], dim=1
                ),
                assistance_fraction=assistance_fraction,
            )
            for name, fraction in self.developmental_event_tracker.fractions().items():
                self.log_dict[f"events/{name}_fraction"] = fraction
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
        if self._ground_curriculum_ready:
            self.log_dict["development/stage_goal_score"] = (
                self.developmental_competence_score().mean()
            )
            self.log_dict["development/base_height"] = (
                self.simulator.robot_root_states[:, 2].mean()
            )
            self.log_dict["development/reset_pose_index_mean"] = (
                self.ground_reset_pose_indices.float().mean()
            )
        if self.capability_frontier_enabled:
            self.log_dict["frontier/progress"] = torch.tensor(
                self.capability_frontier.progress,
                device=self.device,
                dtype=self.actions.dtype,
            )
            self.log_dict["frontier/height_target"] = torch.tensor(
                self.capability_frontier.height_target,
                device=self.device,
                dtype=self.actions.dtype,
            )
            self.log_dict["frontier/upright_target"] = torch.tensor(
                self.capability_frontier.upright_target,
                device=self.device,
                dtype=self.actions.dtype,
            )
        if self._assistance_ready:
            self.log_dict["assistance/fraction"] = torch.tensor(
                self.assistance_fraction,
                device=self.device,
                dtype=self.actions.dtype,
            )
            self.log_dict["assistance/force_mean_n"] = torch.linalg.vector_norm(
                self.assistance_force, dim=1
            ).mean()
            self.log_dict["assistance/impulse_mean_ns"] = self.assistance_impulse.mean()
            self.log_dict["assistance/abs_work_mean_j"] = self.assistance_abs_work.mean()
            self.log_dict["assistance/peak_force_mean_n"] = (
                self.assistance_peak_force.mean()
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

    # Deployable observations: IMU-like signals, joint state, normalized
    # actuator-torque history, action history, and the capability condition.
    # Contact-force tensors are intentionally absent from actor observations.
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

    def _get_obs_assistance_fraction(self):
        fraction = self.assistance_fraction if self._assistance_ready else 0.0
        return torch.full(
            (self.num_envs, 1),
            fraction,
            device=self.device,
            dtype=self.actions.dtype,
        )

    def _get_obs_initial_projected_gravity(self):
        """Initial IMU gravity cached at reset; deployable episodic memory."""

        return self.ground_initial_projected_gravity

    def _get_obs_torque_ratio(self):
        """Measured actuator effort normalized by the published motor limit."""

        return self.torques / self.torque_limits.clamp_min(1e-6)

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

    def _reward_developmental_base_motion(self):
        """Quadratic sway cost with a gradient outside an exponential basin."""

        return torch.sum(torch.square(self.base_lin_vel[:, :2]), dim=1) + torch.sum(
            torch.square(self.base_ang_vel), dim=1
        )

    def _reward_developmental_waist_velocity(self):
        return torch.sum(
            torch.square(
                self.simulator.dof_vel[:, self.waist_alignment_indices]
            ),
            dim=1,
        )

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

    def _reward_developmental_raw_action_peak(self):
        """Prevent one ignored joint from hiding inside an action-vector mean."""

        return torch.amax(torch.square(self.raw_policy_actions), dim=1)

    def _reward_developmental_torque_headroom(self):
        """Keep equal relative margin on small arm and large leg actuators."""

        return normalized_torque_headroom_cost(
            self.torques,
            self.torque_limits,
            soft_ratio=0.80,
        )

    def developmental_competence_score(self):
        """Stage-relative capability score; no standing assumption in early stages."""

        if not self._ground_curriculum_ready:
            gravity_error = torch.sum(torch.square(self.projected_gravity[:, :2]), dim=1)
            return torch.exp(-gravity_error / 0.10)
        stage = self.maturation_controller.stage_index
        height = self.simulator.robot_root_states[:, 2]
        gravity_error = torch.sum(torch.square(self.projected_gravity[:, :2]), dim=1)
        joint_speed = torch.sqrt(
            torch.mean(torch.square(self.simulator.dof_vel), dim=1) + 1e-8
        )
        if self._phase_gate_ready:
            target_joint_speed = self.developmental_goal_joint_speed[stage]
            exploration_score = torch.exp(
                -torch.square(joint_speed - target_joint_speed)
                / self.developmental_goal_joint_speed_sigma
            )
            if stage == 0:
                height_retention = torch.sigmoid((height - 0.06) / 0.03)
                return height_retention * (0.50 + 0.50 * exploration_score)
            if stage == 1:
                quaternion_similarity = torch.abs(
                    torch.sum(
                        self.simulator.robot_root_states[:, 3:7]
                        * self.ground_initial_root_quat,
                        dim=1,
                    )
                ).clamp(0.0, 1.0)
                orientation_change = 2.0 * torch.acos(quaternion_similarity)
                event_cfg = self.developmental_event_tracker.config
                rolling_score = torch.sigmoid(
                    (orientation_change - event_cfg.roll_angle_rad) / 0.20
                ) * torch.sigmoid(
                    (height - event_cfg.rolling_min_height) / 0.03
                )
                support_indices = self.developmental_support_body_indices
                contact_force = torch.linalg.vector_norm(
                    self.simulator.contact_forces[:, support_indices, :], dim=-1
                )
                low_support = (
                    self.simulator._rigid_body_pos[:, support_indices, 2] <= 0.25
                )
                support_count = ((contact_force > 5.0) & low_support).sum(dim=1)
                bracing_score = (
                    support_count >= event_cfg.support_contact_count
                ).float() * torch.sigmoid(
                    (height - event_cfg.bracing_min_height) / 0.03
                ) * torch.sigmoid(
                    (
                        orientation_change
                        - event_cfg.bracing_min_orientation_change_rad
                    )
                    / 0.15
                )
                skill_score = noncompensatory_pair_score(
                    rolling_score, bracing_score
                )
                nonfoot_force = torch.linalg.vector_norm(
                    self.simulator.contact_forces[
                        :, self.penalised_contact_indices, :
                    ],
                    dim=-1,
                ).amax(dim=1)
                angular_speed = torch.linalg.vector_norm(
                    self.simulator.robot_root_states[:, 10:13], dim=1
                )
                peak_torque_ratio = (
                    torch.abs(self.torques)
                    / self.torque_limits.clamp_min(1e-6)
                ).amax(dim=1)
                return safety_refined_skill_score(
                    skill_score=skill_score,
                    impact_force=nonfoot_force,
                    angular_speed=angular_speed,
                    peak_torque_ratio=peak_torque_ratio,
                    safe_support_force=self.ground_safe_support_force,
                    safe_angular_speed=self.ground_safe_roll_angular_speed,
                )
            # Once rising begins, reward every increment from the floor. A
            # sigmoid centred at the final target was effectively flat at the
            # 0.20--0.25 m heights reached by the ground-skill policy.
            if stage >= 2:
                target_height = self.developmental_goal_height[stage]
                if stage == 2 and self.capability_frontier_enabled:
                    target_height = torch.as_tensor(
                        self.capability_frontier.height_target,
                        device=self.device,
                        dtype=height.dtype,
                    )
                return rise_progress_score(
                    base_height=height,
                    gravity_error=gravity_error,
                    joint_speed=joint_speed,
                    floor_height=0.12,
                    target_height=target_height,
                    upright_weight=self.developmental_goal_upright_weight[stage],
                    exploration_weight=self.developmental_goal_exploration_weight[stage],
                    target_joint_speed=target_joint_speed,
                    upright_sigma=self.developmental_goal_upright_sigma,
                    joint_speed_sigma=self.developmental_goal_joint_speed_sigma,
                )
        if self.capability_frontier_enabled and self.capability_frontier.calibrated:
            upright_measure = torch.exp(
                -gravity_error / self.developmental_goal_upright_sigma
            )
            progress = self.capability_frontier.progress
            upright_goal_score = torch.sigmoid(
                (upright_measure - self.capability_frontier.upright_target) / 0.05
            )
            height_goal_score = torch.sigmoid(
                (height - self.capability_frontier.height_target)
                / self.developmental_goal_height_scale
            )
            target_joint_speed = 0.35 * (1.0 - progress) + 0.05 * progress
            exploration_score = torch.exp(
                -torch.square(joint_speed - target_joint_speed)
                / self.developmental_goal_joint_speed_sigma
            )
            return frontier_preserving_score(
                height_goal_score=height_goal_score,
                upright_goal_score=upright_goal_score,
                exploration_score=exploration_score,
            )
        return stage_goal_score(
            base_height=height,
            gravity_error=gravity_error,
            joint_speed=joint_speed,
            target_height=self.developmental_goal_height[stage],
            upright_weight=self.developmental_goal_upright_weight[stage],
            exploration_weight=self.developmental_goal_exploration_weight[stage],
            target_joint_speed=self.developmental_goal_joint_speed[stage],
            height_scale=self.developmental_goal_height_scale,
            upright_sigma=self.developmental_goal_upright_sigma,
            joint_speed_sigma=self.developmental_goal_joint_speed_sigma,
        )

    def _reward_developmental_stage_goal(self):
        return self.developmental_competence_score()

    def _reward_developmental_excess_angular_speed(self):
        """Discourage violent spinning while retaining ordinary rolling freedom."""

        if self.maturation_controller.stage_index != 1:
            return torch.zeros(self.num_envs, device=self.device)
        angular_speed = torch.linalg.vector_norm(
            self.simulator.robot_root_states[:, 10:13], dim=1
        )
        excess_ratio = torch.clamp(
            (angular_speed - self.ground_safe_roll_angular_speed)
            / self.ground_safe_roll_angular_speed,
            min=0.0,
            max=2.0,
        )
        return torch.square(excess_ratio)

    def _reward_developmental_ground_load(self):
        """Penalize impact above supported body weight, not ordinary floor support."""

        forces = torch.linalg.vector_norm(
            self.simulator.contact_forces[:, self.penalised_contact_indices, :],
            dim=-1,
        )
        excess = torch.clamp(
            (forces - self.ground_safe_support_force)
            / float(self.config.developmental.severe_impact_force),
            min=0.0,
            max=2.0,
        )
        return torch.sum(torch.square(excess), dim=1)

    def _reward_developmental_landing_velocity(self):
        """Give a dense pre-impact signal for controlled body placement."""

        body_height = self.simulator._rigid_body_pos[
            :, self.penalised_contact_indices, 2
        ]
        downward_speed = torch.clamp(
            -self.simulator._rigid_body_vel[
                :, self.penalised_contact_indices, 2
            ],
            min=0.0,
            max=3.0,
        )
        near_ground = (body_height <= 0.25).float()
        return torch.sum(near_ground * torch.square(downward_speed), dim=1)
