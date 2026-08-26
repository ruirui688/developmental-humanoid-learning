"""PBHC MHPPO extension implementing the developmental Body Schema loss."""

from __future__ import annotations

from dataclasses import asdict
import json
import os

import torch
from torch import nn, optim

from humanoidverse.agents.mh_ppo.mh_ppo import MHPPO
from humanoidverse.agents.modules.ppo_modules import PPOCritic

from .body_schema import BodySchemaActor
from .evaluation import CompetenceWindow


class DevelopmentalPPO(MHPPO):
    """PBHC PPO optimisation plus a done-masked one-step dynamics objective."""

    def _init_config(self):
        super()._init_config()
        schema = self.config.body_schema
        self.body_schema_loss_coef = float(schema.loss_coef)
        self.body_schema_target_dim = int(schema.target_dim)
        self.body_schema_target_scale = torch.tensor(
            list(schema.target_scale), device=self.device, dtype=torch.float
        )
        if self.body_schema_target_scale.numel() != self.body_schema_target_dim:
            raise ValueError(
                "body_schema.target_scale length must equal body_schema.target_dim"
            )
        evaluation = self.config.competence_evaluation
        self.competence_eval_enabled = bool(evaluation.enabled)
        self.competence_eval_interval = int(evaluation.interval_iterations)
        self.competence_eval_episode_banks = int(evaluation.episode_banks)
        self.competence_eval_seed = int(evaluation.seed)
        self.competence_schema_error_scale = float(evaluation.schema_error_scale)
        self.competence_horizon_steps = tuple(
            int(value) for value in evaluation.horizon_steps_by_stage
        )
        if self.competence_eval_enabled and self.competence_eval_interval < 1:
            raise ValueError("competence evaluation interval must be positive")
        if self.competence_eval_episode_banks < 1:
            raise ValueError("competence evaluation episode_banks must be positive")
        if self.competence_schema_error_scale <= 0.0:
            raise ValueError("competence schema_error_scale must be positive")
        stage_count = len(self.env.maturation_controller.stages)
        if len(self.competence_horizon_steps) != stage_count:
            raise ValueError(
                "competence_evaluation.horizon_steps_by_stage must match "
                f"the {stage_count} maturation stages"
            )
        if any(value < 1 for value in self.competence_horizon_steps):
            raise ValueError("competence evaluation horizons must be positive")
        self._needs_training_reset = False
        self.competence_evaluation_steps = 0

    def _setup_models_and_optimizer(self):
        actor_cfg = self.config.module_dict.actor
        critic_cfg = self.config.module_dict.critic
        critic_cfg.output_dim[-1] = self.num_rew_fn
        self.actor = BodySchemaActor(
            observation_dim=int(self.algo_obs_dim_dict["actor_obs"]),
            num_actions=self.num_act,
            schema_target_dim=self.body_schema_target_dim,
            hidden_dims=tuple(int(value) for value in actor_cfg.layer_config.hidden_dims),
            schema_hidden_dim=int(self.config.body_schema.hidden_dim),
            activation=str(actor_cfg.layer_config.activation),
            init_noise_std=float(self.config.init_noise_std),
            min_noise_std=float(self.config.min_noise_std),
            max_noise_std=float(self.config.max_noise_std),
        ).to(self.device)
        self.critic = PPOCritic(
            obs_dim_dict=self.algo_obs_dim_dict,
            module_config_dict=critic_cfg,
        ).to(self.device)
        self.actor_optimizer = optim.Adam(
            self.actor.parameters(), lr=self.actor_learning_rate
        )
        self.critic_optimizer = optim.Adam(
            self.critic.parameters(), lr=self.critic_learning_rate
        )

    def _actor_act_step(self, obs_dict):
        self.actor.noise_scale = float(
            self.env.maturation_controller.stage.exploration_scale
        )
        return super()._actor_act_step(obs_dict)

    def _rollout_step(self, obs_dict):
        if self._needs_training_reset:
            with torch.inference_mode():
                obs_dict = self.env.reset_all()
            self._needs_training_reset = False
        self.env.count_maturation_schedule_steps = True
        return super()._rollout_step(obs_dict)

    def _post_epoch_logging(self, log_dict, width=80, pad=40):
        super()._post_epoch_logging(log_dict, width=width, pad=pad)
        iteration = int(log_dict["it"]) + 1
        if (
            self.competence_eval_enabled
            and iteration % self.competence_eval_interval == 0
        ):
            gate_stage_index = self.env.maturation_controller.stage_index
            gate_horizon_steps = self.competence_horizon_steps[gate_stage_index]
            result = self.evaluate_competence_window(
                seed=self.competence_eval_seed,
                episode_banks=self.competence_eval_episode_banks,
                horizon_steps=gate_horizon_steps,
            )
            transition = self.env.update_competence(result.sample)
            record = {
                "training_iteration": iteration,
                "rl_environment_steps": self.env.maturation_schedule_environment_steps,
                "cumulative_evaluation_steps": self.competence_evaluation_steps,
                "gate_stage_index": gate_stage_index,
                "gate_horizon_steps": gate_horizon_steps,
                **asdict(result),
                "transition": None if transition is None else asdict(transition),
            }
            record["sample"] = asdict(result.sample)
            record["diagnostics"] = self.last_competence_diagnostics
            with open(
                os.path.join(self.log_dir, "competence_windows.jsonl"),
                "a",
                encoding="utf-8",
            ) as stream:
                stream.write(json.dumps(record, sort_keys=True) + "\n")
        # PBHC saves ``current_learning_iteration`` as the next loop start, but
        # upstream only updates it at save boundaries using the zero-based
        # iteration that just finished. Store the completed-iteration count so
        # resumed runs neither repeat work nor under-report their budget.
        self.current_learning_iteration = iteration
        self._last_completed_iteration = iteration

    @torch.inference_mode()
    def evaluate_competence_window(
        self, *, seed: int, episode_banks: int, horizon_steps: int
    ):
        """Run fixed banks where each environment contributes exactly one episode."""

        cpu_rng_state = torch.get_rng_state()
        cuda_rng_state = torch.cuda.get_rng_state_all()
        self._eval_mode()
        self.env.is_evaluating = True
        self.env.count_maturation_schedule_steps = False
        try:
            torch.manual_seed(seed)
            torch.cuda.manual_seed_all(seed)
            window = CompetenceWindow(episode_banks * self.env.num_envs)
            action_abs_sum = torch.zeros(
                self.env.num_dof, device=self.device, dtype=torch.float64
            )
            action_boundary_count = torch.zeros_like(action_abs_sum)
            diagnostic_signal_rows = 0
            for _ in range(episode_banks):
                observations = self.env.reset_all()
                active = torch.ones(
                    self.env.num_envs, device=self.device, dtype=torch.bool
                )
                episode_steps = torch.zeros(
                    self.env.num_envs, device=self.device, dtype=torch.long
                )
                for _ in range(horizon_steps):
                    actor_obs = observations["actor_obs"]
                    raw_actions = self.actor.act_inference(actor_obs)
                    next_observations, _, dones, infos = self.env.step(
                        {"actions": raw_actions}
                    )
                    prediction = self.actor.predict_body_schema(
                        actor_obs, self.env.actions_after_delay
                    )
                    target = (
                        next_observations["body_schema_target"]
                        * self.body_schema_target_scale
                    )
                    schema_mse = torch.mean(
                        torch.square(prediction - target), dim=-1
                    )
                    schema_accuracy = torch.exp(
                        -schema_mse / self.competence_schema_error_scale
                    )
                    gravity_error = torch.sum(
                        torch.square(self.env.projected_gravity[:, :2]), dim=-1
                    )
                    nonfoot_force = torch.linalg.vector_norm(
                        self.env.simulator.contact_forces[
                            :, self.env.penalised_contact_indices, :
                        ],
                        dim=-1,
                    ).amax(dim=-1)
                    torque_ratio = torch.abs(self.env.torques) / (
                        self.env.torque_limits.clamp_min(1e-6)
                    )
                    natural_done = dones.bool()
                    time_outs = infos["time_outs"].bool()
                    episode_steps[active] += 1
                    reached_horizon = episode_steps >= horizon_steps
                    completed = active & (natural_done | reached_horizon)
                    active_indices = active.nonzero(as_tuple=False).flatten()
                    active_raw_actions = raw_actions[active_indices]
                    action_abs_sum += active_raw_actions.abs().double().sum(dim=0)
                    # abs(raw)>2 means tanh(raw) uses over 96.4% of the
                    # available maturation range.
                    action_boundary_count += (
                        active_raw_actions.abs() > 2.0
                    ).double().sum(dim=0)
                    diagnostic_signal_rows += int(active_indices.numel())
                    window.record_step(
                        episode_done=completed[active_indices],
                        episode_fell=(natural_done & ~time_outs)[active_indices],
                        upright=(gravity_error <= 0.10).float()[active_indices],
                        low_risk=(
                            nonfoot_force
                            <= float(
                                self.env.config.developmental.severe_impact_force
                            )
                        ).float()[active_indices],
                        low_saturation=(torque_ratio < 0.95)
                        .float()
                        .mean(dim=-1)[active_indices],
                        schema_accuracy=schema_accuracy[active_indices],
                        schema_valid=(~natural_done)[active_indices],
                        simulated_environment_steps=self.env.num_envs,
                    )
                    active[completed] = False
                    observations = next_observations
                    if not torch.any(active):
                        break
                if torch.any(active):
                    raise RuntimeError(
                        "competence bank did not finish within its fixed horizon"
                    )
            if not window.complete:
                raise RuntimeError("held-out competence evaluation bank is incomplete")
            result = window.result()
            per_joint_boundary = action_boundary_count / max(
                diagnostic_signal_rows, 1
            )
            per_joint_abs = action_abs_sum / max(diagnostic_signal_rows, 1)
            self.last_competence_diagnostics = {
                "mean_abs_raw_action": float(per_joint_abs.mean().item()),
                "raw_action_boundary_fraction": float(
                    per_joint_boundary.mean().item()
                ),
                "per_joint_raw_action_boundary_fraction": {
                    name: float(value)
                    for name, value in zip(
                        self.env.dof_names, per_joint_boundary.tolist()
                    )
                },
            }
            self.competence_evaluation_steps += result.evaluation_steps
            return result
        finally:
            torch.set_rng_state(cpu_rng_state)
            torch.cuda.set_rng_state_all(cuda_rng_state)
            self.env.is_evaluating = False
            self.env.count_maturation_schedule_steps = False
            self._train_mode()
            self._needs_training_reset = True

    def save(self, path, infos=None):
        self.current_learning_iteration = max(
            self.current_learning_iteration,
            getattr(self, "_last_completed_iteration", 0),
        )
        checkpoint_info = dict(infos or {})
        checkpoint_info["maturation_state"] = self.env.maturation_state_dict()
        checkpoint_info["competence_evaluation_steps"] = (
            self.competence_evaluation_steps
        )
        super().save(path, checkpoint_info)

    def load(self, ckpt_path):
        infos = super().load(ckpt_path)
        if isinstance(infos, dict) and "maturation_state" in infos:
            self.env.load_maturation_state_dict(infos["maturation_state"])
            self.competence_evaluation_steps = int(
                infos.get("competence_evaluation_steps", 0)
            )
        return infos

    def _init_loss_dict_at_training_step(self):
        losses = super()._init_loss_dict_at_training_step()
        losses["Body_Schema"] = 0
        return losses

    def _update_algo_step(self, policy_state_dict, loss_dict):
        loss_dict = super()._update_algo_step(policy_state_dict, loss_dict)

        # A zero-coefficient ablation must not take a second Adam step. Even
        # zero gradients can advance Adam's momentum state and change shared
        # actor parameters after the PPO update.
        if self.body_schema_loss_coef == 0.0:
            return loss_dict

        prediction = self.actor.predict_body_schema(
            policy_state_dict["actor_obs"],
            policy_state_dict["next_executed_actions"],
        )
        target = (
            policy_state_dict["next_body_schema_target"]
            * self.body_schema_target_scale
        )
        valid = (~policy_state_dict["dones"].squeeze(-1)).float()
        per_sample = torch.mean(torch.square(prediction - target), dim=-1)
        schema_loss = torch.sum(per_sample * valid) / valid.sum().clamp_min(1.0)

        self.actor_optimizer.zero_grad()
        (self.body_schema_loss_coef * schema_loss).backward()
        nn.utils.clip_grad_norm_(self.actor.parameters(), self.max_grad_norm)
        self.actor_optimizer.step()

        loss_dict["Body_Schema"] += schema_loss.item()
        return loss_dict
