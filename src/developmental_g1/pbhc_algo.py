"""PBHC MHPPO extension implementing the developmental Body Schema loss."""

from __future__ import annotations

from dataclasses import asdict
import hashlib
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

    @staticmethod
    def _module_state_sha256(module: nn.Module) -> str:
        """Hash names, metadata and bytes of every persistent tensor."""

        digest = hashlib.sha256()
        for name, tensor in sorted(module.state_dict().items()):
            value = tensor.detach().cpu().contiguous()
            digest.update(name.encode("utf-8"))
            digest.update(str(value.dtype).encode("ascii"))
            digest.update(str(tuple(value.shape)).encode("ascii"))
            digest.update(value.numpy().tobytes())
        return digest.hexdigest()

    @staticmethod
    def _file_sha256(path: str) -> str:
        digest = hashlib.sha256()
        with open(path, "rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def learn(self):
        """Train normally, or evaluate one frozen checkpoint without updates."""

        evaluation_only = self.config.evaluation_only
        if not bool(evaluation_only.enabled):
            return super().learn()
        if self.log_dir is None:
            raise ValueError("evaluation-only mode requires a log directory")
        checkpoint_path = evaluation_only.get("checkpoint_path", None)
        if not checkpoint_path:
            raise ValueError(
                "evaluation_only.checkpoint_path must identify the loaded policy"
            )
        checkpoint_path = os.path.abspath(str(checkpoint_path))
        if not os.path.isfile(checkpoint_path):
            raise FileNotFoundError(checkpoint_path)
        loaded_checkpoint_path = getattr(self, "_loaded_checkpoint_path", None)
        if loaded_checkpoint_path is None or not os.path.samefile(
            checkpoint_path, loaded_checkpoint_path
        ):
            raise RuntimeError(
                "evaluation-only checkpoint declaration does not match "
                "the policy loaded by the algorithm"
            )
        episode_banks = int(evaluation_only.episode_banks)
        horizon_steps = int(evaluation_only.horizon_steps)
        if episode_banks < 1 or horizon_steps < 1:
            raise ValueError(
                "evaluation-only episode_banks and horizon_steps must be positive"
            )
        actor_sha256_before = self._module_state_sha256(self.actor)
        critic_sha256_before = self._module_state_sha256(self.critic)
        checkpoint_sha256_before = self._file_sha256(checkpoint_path)
        checkpoint_stat_before = os.stat(checkpoint_path)
        maturation_state_before = self.env.maturation_state_dict()
        maturation_steps_before = int(
            self.env.maturation_schedule_environment_steps
        )
        evaluation_steps_before = self.competence_evaluation_steps
        result = self.evaluate_competence_window(
            seed=int(evaluation_only.seed),
            episode_banks=episode_banks,
            horizon_steps=horizon_steps,
        )
        evaluation_steps_delta = (
            self.competence_evaluation_steps - evaluation_steps_before
        )
        if evaluation_steps_delta != result.evaluation_steps:
            raise RuntimeError("evaluation-step accounting changed unexpectedly")
        actor_sha256_after = self._module_state_sha256(self.actor)
        critic_sha256_after = self._module_state_sha256(self.critic)
        checkpoint_sha256_after = self._file_sha256(checkpoint_path)
        checkpoint_stat_after = os.stat(checkpoint_path)
        maturation_state_after = self.env.maturation_state_dict()
        maturation_steps_after = int(
            self.env.maturation_schedule_environment_steps
        )
        if actor_sha256_before != actor_sha256_after:
            raise RuntimeError("actor parameters changed during evaluation-only run")
        if critic_sha256_before != critic_sha256_after:
            raise RuntimeError("critic parameters changed during evaluation-only run")
        if maturation_steps_before != maturation_steps_after:
            raise RuntimeError(
                "maturation schedule advanced during evaluation-only run"
            )
        if maturation_state_before != maturation_state_after:
            raise RuntimeError("maturation controller changed during evaluation")
        if checkpoint_sha256_before != checkpoint_sha256_after:
            raise RuntimeError("checkpoint file changed during evaluation")
        if (
            checkpoint_stat_before.st_size != checkpoint_stat_after.st_size
            or checkpoint_stat_before.st_mtime_ns
            != checkpoint_stat_after.st_mtime_ns
        ):
            raise RuntimeError("checkpoint metadata changed during evaluation")
        output_path = os.path.abspath(
            os.path.join(self.log_dir, str(evaluation_only.output_filename))
        )
        run_config_path = os.path.abspath(os.path.join(self.log_dir, "config.yaml"))
        run_config_sha256 = self._file_sha256(run_config_path)
        record = {
            "evaluation_only": True,
            "policy_updates_during_run": 0,
            "checkpoint_path": checkpoint_path,
            "checkpoint_sha256_before": checkpoint_sha256_before,
            "checkpoint_sha256_after": checkpoint_sha256_after,
            "actor_state_sha256_before": actor_sha256_before,
            "actor_state_sha256_after": actor_sha256_after,
            "critic_state_sha256_before": critic_sha256_before,
            "critic_state_sha256_after": critic_sha256_after,
            "training_iteration": int(self.current_learning_iteration),
            "source_revision": evaluation_only.get("source_revision", None),
            "pbhc_revision": evaluation_only.get("pbhc_revision", None),
            "output_path": output_path,
            "run_config_path": run_config_path,
            "run_config_sha256": run_config_sha256,
            "num_envs": int(self.env.num_envs),
            "episode_banks": episode_banks,
            "maturation_mode": self.env.maturation_mode,
            "maturation_state_before": maturation_state_before,
            "maturation_state_after": maturation_state_after,
            "reset_root_velocity_range": list(
                self.env.reset_root_velocity_range
            ),
            "strict_standing_thresholds": {
                "minimum_base_height": self.competence_standing_min_base_height,
                "maximum_gravity_error": (
                    self.competence_standing_max_gravity_error
                ),
                "maximum_waist_deviation": (
                    self.competence_standing_max_waist_deviation
                ),
                "maximum_horizontal_drift": (
                    self.competence_standing_max_horizontal_drift
                ),
                "maximum_horizontal_speed": (
                    self.competence_standing_max_horizontal_speed
                ),
                "maximum_base_angular_speed": (
                    self.competence_standing_max_base_angular_speed
                ),
                "maximum_waist_velocity": (
                    self.competence_standing_max_waist_velocity
                ),
                "motion_settling_steps": (
                    self.competence_standing_motion_settling_steps
                ),
                "safety_minimum_base_height": (
                    self.competence_standing_safety_min_base_height
                ),
                "safety_maximum_gravity_error": (
                    self.competence_standing_safety_max_gravity_error
                ),
                "safety_maximum_waist_deviation": (
                    self.competence_standing_safety_max_waist_deviation
                ),
                "maximum_motion_violation_fraction": (
                    self.competence_standing_max_motion_violation_fraction
                ),
                "maximum_consecutive_motion_violation_steps": (
                    self.competence_standing_max_consecutive_motion_violation_steps
                ),
                "require_endpoint_double_support": (
                    self.competence_require_endpoint_double_support
                ),
            },
            "rl_environment_steps_before": maturation_steps_before,
            "rl_environment_steps_after": maturation_steps_after,
            "prior_cumulative_evaluation_steps": int(evaluation_steps_before),
            "evaluation_steps_after": int(self.competence_evaluation_steps),
            "evaluation_steps_delta": int(evaluation_steps_delta),
            "maximum_evaluation_steps": int(
                self.env.num_envs * episode_banks * horizon_steps
            ),
            "reset_warmup_control_steps": 1,
            "evaluation_seed": int(evaluation_only.seed),
            "horizon_steps": horizon_steps,
            **asdict(result),
            "sample": asdict(result.sample),
            "diagnostics": self.last_competence_diagnostics,
        }
        with open(output_path, "w", encoding="utf-8") as stream:
            json.dump(record, stream, indent=2, sort_keys=True)
            stream.write("\n")
        return record

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
        self.competence_standing_min_base_height = float(
            evaluation.standing_min_base_height
        )
        self.competence_standing_max_gravity_error = float(
            evaluation.standing_max_gravity_error
        )
        self.competence_require_endpoint_double_support = bool(
            evaluation.require_endpoint_double_support
        )
        self.competence_standing_max_waist_deviation = float(
            evaluation.standing_max_waist_deviation
        )
        self.competence_standing_max_horizontal_drift = float(
            evaluation.standing_max_horizontal_drift
        )
        self.competence_standing_max_horizontal_speed = float(
            evaluation.standing_max_horizontal_speed
        )
        self.competence_standing_max_base_angular_speed = float(
            evaluation.standing_max_base_angular_speed
        )
        self.competence_standing_max_waist_velocity = float(
            evaluation.standing_max_waist_velocity
        )
        self.competence_standing_motion_settling_steps = int(
            evaluation.standing_motion_settling_steps
        )
        self.competence_standing_safety_min_base_height = float(
            evaluation.standing_safety_min_base_height
        )
        self.competence_standing_safety_max_gravity_error = float(
            evaluation.standing_safety_max_gravity_error
        )
        self.competence_standing_safety_max_waist_deviation = float(
            evaluation.standing_safety_max_waist_deviation
        )
        self.competence_standing_max_motion_violation_fraction = float(
            evaluation.standing_max_motion_violation_fraction
        )
        self.competence_standing_max_consecutive_motion_violation_steps = int(
            evaluation.standing_max_consecutive_motion_violation_steps
        )
        self.competence_horizon_steps = tuple(
            int(value) for value in evaluation.horizon_steps_by_stage
        )
        if self.competence_eval_enabled and self.competence_eval_interval < 1:
            raise ValueError("competence evaluation interval must be positive")
        if self.competence_eval_episode_banks < 1:
            raise ValueError("competence evaluation episode_banks must be positive")
        if self.competence_schema_error_scale <= 0.0:
            raise ValueError("competence schema_error_scale must be positive")
        if self.competence_standing_min_base_height <= 0.0:
            raise ValueError("standing_min_base_height must be positive")
        if self.competence_standing_max_gravity_error < 0.0:
            raise ValueError("standing_max_gravity_error cannot be negative")
        if self.competence_standing_max_waist_deviation < 0.0:
            raise ValueError("standing_max_waist_deviation cannot be negative")
        motion_limits = (
            self.competence_standing_max_horizontal_drift,
            self.competence_standing_max_horizontal_speed,
            self.competence_standing_max_base_angular_speed,
            self.competence_standing_max_waist_velocity,
        )
        if any(value < 0.0 for value in motion_limits):
            raise ValueError("standing motion limits cannot be negative")
        if self.competence_standing_motion_settling_steps < 0:
            raise ValueError("standing_motion_settling_steps cannot be negative")
        if self.competence_standing_safety_min_base_height <= 0.0:
            raise ValueError("standing_safety_min_base_height must be positive")
        if self.competence_standing_safety_max_gravity_error < 0.0:
            raise ValueError("standing_safety_max_gravity_error cannot be negative")
        if self.competence_standing_safety_max_waist_deviation < 0.0:
            raise ValueError("standing_safety_max_waist_deviation cannot be negative")
        if not 0.0 <= self.competence_standing_max_motion_violation_fraction <= 1.0:
            raise ValueError(
                "standing_max_motion_violation_fraction must be in [0, 1]"
            )
        if self.competence_standing_max_consecutive_motion_violation_steps < 0:
            raise ValueError(
                "standing_max_consecutive_motion_violation_steps cannot be negative"
            )
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
        original_max_episode_length = self.env.max_episode_length
        # PBHC resets timed-out environments inside env.step(). Keep the
        # formal horizon one step before timeout so endpoint state diagnostics
        # observe the actual standing state rather than the reset state.
        self.env.max_episode_length = max(
            int(original_max_episode_length), horizon_steps + 1
        )
        try:
            torch.manual_seed(seed)
            torch.cuda.manual_seed_all(seed)
            window = CompetenceWindow(episode_banks * self.env.num_envs)
            action_abs_sum = torch.zeros(
                self.env.num_dof, device=self.device, dtype=torch.float64
            )
            action_boundary_count = torch.zeros_like(action_abs_sum)
            diagnostic_signal_rows = 0
            state_diagnostic_rows = 0
            base_height_sum = 0.0
            gravity_error_sum = 0.0
            waist_deviation_sum = torch.zeros(
                2, device=self.device, dtype=torch.float64
            )
            double_support_sum = 0.0
            successful_endpoint_height_sum = 0.0
            successful_endpoint_height_min = float("inf")
            successful_endpoint_gravity_error_sum = 0.0
            successful_endpoint_gravity_error_max = 0.0
            successful_endpoint_waist_deviation_sum = torch.zeros_like(
                waist_deviation_sum
            )
            successful_endpoint_waist_deviation_max = torch.zeros_like(
                waist_deviation_sum
            )
            successful_endpoint_count = 0
            strict_standing_episodes = 0
            recovered_standing_episodes = 0
            trajectory_safety_valid_episodes = 0
            trajectory_post_settling_standing_valid_episodes = 0
            trajectory_motion_duty_valid_episodes = 0
            trajectory_motion_violation_steps_sum = 0.0
            trajectory_motion_violation_steps_max = 0
            trajectory_motion_violation_fraction_sum = 0.0
            trajectory_motion_violation_fraction_max = 0.0
            trajectory_motion_max_consecutive_steps_max = 0
            trajectory_height_valid_episodes = 0
            trajectory_gravity_valid_episodes = 0
            trajectory_waist_valid_episodes = 0
            trajectory_motion_valid_episodes = 0
            trajectory_post_settling_motion_valid_episodes = 0
            trajectory_post_settling_drift_valid_episodes = 0
            trajectory_post_settling_horizontal_speed_valid_episodes = 0
            trajectory_post_settling_angular_speed_valid_episodes = 0
            trajectory_post_settling_waist_velocity_valid_episodes = 0
            endpoint_double_support_episodes = 0
            trajectory_max_gravity_error_sum = 0.0
            trajectory_max_gravity_error_max = 0.0
            trajectory_max_waist_deviation_sum = torch.zeros_like(
                waist_deviation_sum
            )
            trajectory_max_waist_deviation_max = torch.zeros_like(
                waist_deviation_sum
            )
            trajectory_last_gravity_violation_step_sum = 0.0
            trajectory_last_gravity_violation_step_max = 0
            trajectory_last_waist_violation_step_sum = 0.0
            trajectory_last_waist_violation_step_max = 0
            trajectory_last_motion_violation_step_sum = 0.0
            trajectory_last_motion_violation_step_max = 0
            trajectory_max_horizontal_drift_sum = 0.0
            trajectory_max_horizontal_drift_max = 0.0
            trajectory_max_horizontal_speed_sum = 0.0
            trajectory_max_horizontal_speed_max = 0.0
            trajectory_max_base_angular_speed_sum = 0.0
            trajectory_max_base_angular_speed_max = 0.0
            trajectory_max_abs_base_angular_velocity_sum = torch.zeros(
                3, device=self.device, dtype=torch.float64
            )
            trajectory_max_abs_base_angular_velocity_max = torch.zeros_like(
                trajectory_max_abs_base_angular_velocity_sum
            )
            trajectory_post_settling_max_base_angular_speed_sum = 0.0
            trajectory_post_settling_max_base_angular_speed_max = 0.0
            trajectory_max_waist_velocity_sum = torch.zeros_like(
                waist_deviation_sum
            )
            trajectory_max_waist_velocity_max = torch.zeros_like(
                waist_deviation_sum
            )
            fallen_initial_abs_velocity_sum = torch.zeros(
                6, device=self.device, dtype=torch.float64
            )
            successful_initial_abs_velocity_sum = torch.zeros_like(
                fallen_initial_abs_velocity_sum
            )
            fallen_injected_abs_velocity_sum = torch.zeros_like(
                fallen_initial_abs_velocity_sum
            )
            successful_injected_abs_velocity_sum = torch.zeros_like(
                fallen_initial_abs_velocity_sum
            )
            fallen_initial_count = 0
            successful_initial_count = 0
            for _ in range(episode_banks):
                observations = self.env.reset_all()
                initial_root_velocity = self.env.simulator.robot_root_states[
                    :, 7:13
                ].detach().clone()
                injected_root_velocity = (
                    self.env.last_injected_root_velocity.detach().clone()
                )
                initial_root_xy = self.env.simulator.robot_root_states[
                    :, :2
                ].detach().clone()
                bank_fell = torch.zeros(
                    self.env.num_envs, device=self.device, dtype=torch.bool
                )
                bank_standing_valid = torch.ones_like(bank_fell)
                bank_safety_valid = torch.ones_like(bank_fell)
                bank_post_settling_standing_valid = torch.ones_like(bank_fell)
                bank_height_valid = torch.ones_like(bank_fell)
                bank_gravity_valid = torch.ones_like(bank_fell)
                bank_waist_valid = torch.ones_like(bank_fell)
                bank_motion_valid = torch.ones_like(bank_fell)
                bank_post_settling_motion_valid = torch.ones_like(bank_fell)
                bank_post_settling_drift_valid = torch.ones_like(bank_fell)
                bank_post_settling_horizontal_speed_valid = torch.ones_like(
                    bank_fell
                )
                bank_post_settling_angular_speed_valid = torch.ones_like(
                    bank_fell
                )
                bank_post_settling_waist_velocity_valid = torch.ones_like(
                    bank_fell
                )
                bank_post_settling_motion_violation_steps = torch.zeros(
                    self.env.num_envs, device=self.device, dtype=torch.long
                )
                bank_post_settling_motion_consecutive_steps = torch.zeros_like(
                    bank_post_settling_motion_violation_steps
                )
                bank_post_settling_motion_max_consecutive_steps = torch.zeros_like(
                    bank_post_settling_motion_violation_steps
                )
                bank_max_gravity_error = torch.zeros(
                    self.env.num_envs, device=self.device
                )
                bank_max_waist_deviation = torch.zeros(
                    self.env.num_envs, 2, device=self.device
                )
                bank_last_gravity_violation_step = torch.zeros(
                    self.env.num_envs, device=self.device, dtype=torch.long
                )
                bank_last_waist_violation_step = torch.zeros_like(
                    bank_last_gravity_violation_step
                )
                bank_last_motion_violation_step = torch.zeros_like(
                    bank_last_gravity_violation_step
                )
                bank_max_horizontal_drift = torch.zeros(
                    self.env.num_envs, device=self.device
                )
                bank_max_horizontal_speed = torch.zeros_like(
                    bank_max_horizontal_drift
                )
                bank_max_base_angular_speed = torch.zeros_like(
                    bank_max_horizontal_drift
                )
                bank_max_abs_base_angular_velocity = torch.zeros(
                    self.env.num_envs, 3, device=self.device
                )
                bank_post_settling_max_base_angular_speed = torch.zeros_like(
                    bank_max_horizontal_drift
                )
                bank_max_waist_velocity = torch.zeros(
                    self.env.num_envs, 2, device=self.device
                )
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
                    bank_fell |= active & natural_done & ~time_outs
                    active_indices = active.nonzero(as_tuple=False).flatten()
                    active_raw_actions = raw_actions[active_indices]
                    action_abs_sum += active_raw_actions.abs().double().sum(dim=0)
                    # abs(raw)>2 means tanh(raw) uses over 96.4% of the
                    # available maturation range.
                    action_boundary_count += (
                        active_raw_actions.abs() > 2.0
                    ).double().sum(dim=0)
                    diagnostic_signal_rows += int(active_indices.numel())
                    valid_state_indices = (active & ~natural_done).nonzero(
                        as_tuple=False
                    ).flatten()
                    active_heights = self.env.simulator.robot_root_states[
                        valid_state_indices, 2
                    ]
                    base_height_sum += float(active_heights.sum().item())
                    gravity_error_sum += float(
                        gravity_error[valid_state_indices].sum().item()
                    )
                    waist_deviation = torch.abs(
                        self.env.simulator.dof_pos[
                            valid_state_indices
                        ][:, self.env.waist_alignment_indices]
                        - self.env.default_dof_pos[
                            valid_state_indices
                        ][:, self.env.waist_alignment_indices]
                    )
                    waist_deviation_sum += waist_deviation.double().sum(dim=0)
                    horizontal_drift = torch.linalg.vector_norm(
                        self.env.simulator.robot_root_states[
                            valid_state_indices, :2
                        ]
                        - initial_root_xy[valid_state_indices],
                        dim=1,
                    )
                    horizontal_speed = torch.linalg.vector_norm(
                        self.env.base_lin_vel[valid_state_indices, :2], dim=1
                    )
                    base_angular_speed = torch.linalg.vector_norm(
                        self.env.base_ang_vel[valid_state_indices], dim=1
                    )
                    abs_base_angular_velocity = torch.abs(
                        self.env.base_ang_vel[valid_state_indices]
                    )
                    waist_velocity = torch.abs(
                        self.env.simulator.dof_vel[valid_state_indices][
                            :, self.env.waist_alignment_indices
                        ]
                    )
                    motion_valid = (
                        (
                            horizontal_drift
                            <= self.competence_standing_max_horizontal_drift
                        )
                        & (
                            horizontal_speed
                            <= self.competence_standing_max_horizontal_speed
                        )
                        & (
                            base_angular_speed
                            <= self.competence_standing_max_base_angular_speed
                        )
                        & (
                            torch.amax(waist_velocity, dim=1)
                            <= self.competence_standing_max_waist_velocity
                        )
                    )
                    double_support_sum += float(
                        torch.all(
                            self.env.contacts_filt[valid_state_indices] > 0.5,
                            dim=1,
                        )
                        .float()
                        .sum()
                        .item()
                    )
                    state_diagnostic_rows += int(valid_state_indices.numel())
                    bank_standing_valid[valid_state_indices] &= (
                        active_heights >= self.competence_standing_min_base_height
                    ) & (
                        gravity_error[valid_state_indices]
                        <= self.competence_standing_max_gravity_error
                    ) & (
                        torch.amax(waist_deviation, dim=1)
                        <= self.competence_standing_max_waist_deviation
                    )
                    bank_safety_valid[valid_state_indices] &= (
                        active_heights
                        >= self.competence_standing_safety_min_base_height
                    ) & (
                        gravity_error[valid_state_indices]
                        <= self.competence_standing_safety_max_gravity_error
                    ) & (
                        torch.amax(waist_deviation, dim=1)
                        <= self.competence_standing_safety_max_waist_deviation
                    )
                    bank_height_valid[valid_state_indices] &= (
                        active_heights >= self.competence_standing_min_base_height
                    )
                    bank_gravity_valid[valid_state_indices] &= (
                        gravity_error[valid_state_indices]
                        <= self.competence_standing_max_gravity_error
                    )
                    bank_waist_valid[valid_state_indices] &= (
                        torch.amax(waist_deviation, dim=1)
                        <= self.competence_standing_max_waist_deviation
                    )
                    bank_motion_valid[valid_state_indices] &= motion_valid
                    after_settling = (
                        episode_steps[valid_state_indices]
                        > self.competence_standing_motion_settling_steps
                    )
                    post_settling_indices = valid_state_indices[after_settling]
                    bank_post_settling_standing_valid[
                        post_settling_indices
                    ] &= (
                        active_heights[after_settling]
                        >= self.competence_standing_min_base_height
                    ) & (
                        gravity_error[post_settling_indices]
                        <= self.competence_standing_max_gravity_error
                    ) & (
                        torch.amax(waist_deviation[after_settling], dim=1)
                        <= self.competence_standing_max_waist_deviation
                    )
                    bank_post_settling_motion_valid[post_settling_indices] &= (
                        motion_valid[after_settling]
                    )
                    post_motion_invalid = ~motion_valid[after_settling]
                    bank_post_settling_motion_violation_steps[
                        post_settling_indices
                    ] += post_motion_invalid.long()
                    prior_consecutive = bank_post_settling_motion_consecutive_steps[
                        post_settling_indices
                    ]
                    current_consecutive = torch.where(
                        post_motion_invalid,
                        prior_consecutive + 1,
                        torch.zeros_like(prior_consecutive),
                    )
                    bank_post_settling_motion_consecutive_steps[
                        post_settling_indices
                    ] = current_consecutive
                    bank_post_settling_motion_max_consecutive_steps[
                        post_settling_indices
                    ] = torch.maximum(
                        bank_post_settling_motion_max_consecutive_steps[
                            post_settling_indices
                        ],
                        current_consecutive,
                    )
                    bank_post_settling_drift_valid[post_settling_indices] &= (
                        horizontal_drift[after_settling]
                        <= self.competence_standing_max_horizontal_drift
                    )
                    bank_post_settling_horizontal_speed_valid[
                        post_settling_indices
                    ] &= (
                        horizontal_speed[after_settling]
                        <= self.competence_standing_max_horizontal_speed
                    )
                    bank_post_settling_angular_speed_valid[
                        post_settling_indices
                    ] &= (
                        base_angular_speed[after_settling]
                        <= self.competence_standing_max_base_angular_speed
                    )
                    bank_post_settling_waist_velocity_valid[
                        post_settling_indices
                    ] &= (
                        torch.amax(waist_velocity[after_settling], dim=1)
                        <= self.competence_standing_max_waist_velocity
                    )
                    bank_post_settling_max_base_angular_speed[
                        post_settling_indices
                    ] = torch.maximum(
                        bank_post_settling_max_base_angular_speed[
                            post_settling_indices
                        ],
                        base_angular_speed[after_settling],
                    )
                    bank_last_motion_violation_step[
                        valid_state_indices[~motion_valid]
                    ] = episode_steps[valid_state_indices[~motion_valid]]
                    bank_max_gravity_error[valid_state_indices] = torch.maximum(
                        bank_max_gravity_error[valid_state_indices],
                        gravity_error[valid_state_indices],
                    )
                    bank_max_waist_deviation[valid_state_indices] = torch.maximum(
                        bank_max_waist_deviation[valid_state_indices],
                        waist_deviation,
                    )
                    bank_max_horizontal_drift[valid_state_indices] = torch.maximum(
                        bank_max_horizontal_drift[valid_state_indices],
                        horizontal_drift,
                    )
                    bank_max_horizontal_speed[valid_state_indices] = torch.maximum(
                        bank_max_horizontal_speed[valid_state_indices],
                        horizontal_speed,
                    )
                    bank_max_base_angular_speed[valid_state_indices] = torch.maximum(
                        bank_max_base_angular_speed[valid_state_indices],
                        base_angular_speed,
                    )
                    bank_max_abs_base_angular_velocity[
                        valid_state_indices
                    ] = torch.maximum(
                        bank_max_abs_base_angular_velocity[valid_state_indices],
                        abs_base_angular_velocity,
                    )
                    bank_max_waist_velocity[valid_state_indices] = torch.maximum(
                        bank_max_waist_velocity[valid_state_indices],
                        waist_velocity,
                    )
                    gravity_invalid = (
                        gravity_error[valid_state_indices]
                        > self.competence_standing_max_gravity_error
                    )
                    waist_invalid = (
                        torch.amax(waist_deviation, dim=1)
                        > self.competence_standing_max_waist_deviation
                    )
                    bank_last_gravity_violation_step[
                        valid_state_indices[gravity_invalid]
                    ] = episode_steps[valid_state_indices[gravity_invalid]]
                    bank_last_waist_violation_step[
                        valid_state_indices[waist_invalid]
                    ] = episode_steps[valid_state_indices[waist_invalid]]
                    horizon_success = active & reached_horizon & ~natural_done
                    endpoint_heights = self.env.simulator.robot_root_states[
                        horizon_success, 2
                    ]
                    if endpoint_heights.numel() > 0:
                        endpoint_gravity_error = gravity_error[horizon_success]
                        endpoint_waist_deviation = torch.abs(
                            self.env.simulator.dof_pos[horizon_success][
                                :, self.env.waist_alignment_indices
                            ]
                            - self.env.default_dof_pos[horizon_success][
                                :, self.env.waist_alignment_indices
                            ]
                        )
                        successful_endpoint_height_sum += float(
                            endpoint_heights.sum().item()
                        )
                        successful_endpoint_height_min = min(
                            successful_endpoint_height_min,
                            float(endpoint_heights.min().item()),
                        )
                        successful_endpoint_count += int(endpoint_heights.numel())
                        successful_endpoint_gravity_error_sum += float(
                            endpoint_gravity_error.sum().item()
                        )
                        successful_endpoint_gravity_error_max = max(
                            successful_endpoint_gravity_error_max,
                            float(endpoint_gravity_error.max().item()),
                        )
                        successful_endpoint_waist_deviation_sum += (
                            endpoint_waist_deviation.double().sum(dim=0)
                        )
                        successful_endpoint_waist_deviation_max = torch.maximum(
                            successful_endpoint_waist_deviation_max,
                            endpoint_waist_deviation.double().amax(dim=0),
                        )
                        endpoint_double_support = torch.all(
                            self.env.contacts_filt[horizon_success] > 0.5, dim=1
                        )
                        trajectory_height_valid_episodes += int(
                            bank_height_valid[horizon_success].sum().item()
                        )
                        trajectory_gravity_valid_episodes += int(
                            bank_gravity_valid[horizon_success].sum().item()
                        )
                        trajectory_waist_valid_episodes += int(
                            bank_waist_valid[horizon_success].sum().item()
                        )
                        trajectory_motion_valid_episodes += int(
                            bank_motion_valid[horizon_success].sum().item()
                        )
                        trajectory_post_settling_motion_valid_episodes += int(
                            bank_post_settling_motion_valid[horizon_success]
                            .sum()
                            .item()
                        )
                        trajectory_post_settling_drift_valid_episodes += int(
                            bank_post_settling_drift_valid[horizon_success]
                            .sum()
                            .item()
                        )
                        trajectory_post_settling_horizontal_speed_valid_episodes += int(
                            bank_post_settling_horizontal_speed_valid[
                                horizon_success
                            ]
                            .sum()
                            .item()
                        )
                        trajectory_post_settling_angular_speed_valid_episodes += int(
                            bank_post_settling_angular_speed_valid[
                                horizon_success
                            ]
                            .sum()
                            .item()
                        )
                        trajectory_post_settling_waist_velocity_valid_episodes += int(
                            bank_post_settling_waist_velocity_valid[
                                horizon_success
                            ]
                            .sum()
                            .item()
                        )
                        endpoint_double_support_episodes += int(
                            endpoint_double_support.sum().item()
                        )
                        trajectory_safety_valid_episodes += int(
                            bank_safety_valid[horizon_success].sum().item()
                        )
                        trajectory_post_settling_standing_valid_episodes += int(
                            bank_post_settling_standing_valid[horizon_success]
                            .sum()
                            .item()
                        )
                        post_settling_steps = max(
                            horizon_steps
                            - self.competence_standing_motion_settling_steps,
                            1,
                        )
                        motion_violation_steps = (
                            bank_post_settling_motion_violation_steps[
                                horizon_success
                            ]
                        )
                        motion_violation_fraction = (
                            motion_violation_steps.float() / post_settling_steps
                        )
                        motion_max_consecutive_steps = (
                            bank_post_settling_motion_max_consecutive_steps[
                                horizon_success
                            ]
                        )
                        motion_duty_valid = (
                            motion_violation_fraction
                            <= self.competence_standing_max_motion_violation_fraction
                        ) & (
                            motion_max_consecutive_steps
                            <= self.competence_standing_max_consecutive_motion_violation_steps
                        )
                        trajectory_motion_duty_valid_episodes += int(
                            motion_duty_valid.sum().item()
                        )
                        trajectory_motion_violation_steps_sum += float(
                            motion_violation_steps.sum().item()
                        )
                        trajectory_motion_violation_steps_max = max(
                            trajectory_motion_violation_steps_max,
                            int(motion_violation_steps.max().item()),
                        )
                        trajectory_motion_violation_fraction_sum += float(
                            motion_violation_fraction.sum().item()
                        )
                        trajectory_motion_violation_fraction_max = max(
                            trajectory_motion_violation_fraction_max,
                            float(motion_violation_fraction.max().item()),
                        )
                        trajectory_motion_max_consecutive_steps_max = max(
                            trajectory_motion_max_consecutive_steps_max,
                            int(motion_max_consecutive_steps.max().item()),
                        )
                        successful_max_gravity = bank_max_gravity_error[
                            horizon_success
                        ]
                        successful_max_waist = bank_max_waist_deviation[
                            horizon_success
                        ]
                        trajectory_max_gravity_error_sum += float(
                            successful_max_gravity.sum().item()
                        )
                        trajectory_max_gravity_error_max = max(
                            trajectory_max_gravity_error_max,
                            float(successful_max_gravity.max().item()),
                        )
                        trajectory_max_waist_deviation_sum += (
                            successful_max_waist.double().sum(dim=0)
                        )
                        trajectory_max_waist_deviation_max = torch.maximum(
                            trajectory_max_waist_deviation_max,
                            successful_max_waist.double().amax(dim=0),
                        )
                        last_gravity_violation = (
                            bank_last_gravity_violation_step[horizon_success]
                        )
                        last_waist_violation = (
                            bank_last_waist_violation_step[horizon_success]
                        )
                        trajectory_last_gravity_violation_step_sum += float(
                            last_gravity_violation.sum().item()
                        )
                        trajectory_last_gravity_violation_step_max = max(
                            trajectory_last_gravity_violation_step_max,
                            int(last_gravity_violation.max().item()),
                        )
                        trajectory_last_waist_violation_step_sum += float(
                            last_waist_violation.sum().item()
                        )
                        trajectory_last_waist_violation_step_max = max(
                            trajectory_last_waist_violation_step_max,
                            int(last_waist_violation.max().item()),
                        )
                        last_motion_violation = (
                            bank_last_motion_violation_step[horizon_success]
                        )
                        trajectory_last_motion_violation_step_sum += float(
                            last_motion_violation.sum().item()
                        )
                        trajectory_last_motion_violation_step_max = max(
                            trajectory_last_motion_violation_step_max,
                            int(last_motion_violation.max().item()),
                        )
                        successful_max_horizontal_drift = (
                            bank_max_horizontal_drift[horizon_success]
                        )
                        successful_max_horizontal_speed = (
                            bank_max_horizontal_speed[horizon_success]
                        )
                        successful_max_base_angular_speed = (
                            bank_max_base_angular_speed[horizon_success]
                        )
                        successful_max_abs_base_angular_velocity = (
                            bank_max_abs_base_angular_velocity[horizon_success]
                        )
                        successful_post_settling_max_base_angular_speed = (
                            bank_post_settling_max_base_angular_speed[
                                horizon_success
                            ]
                        )
                        successful_max_waist_velocity = (
                            bank_max_waist_velocity[horizon_success]
                        )
                        trajectory_max_horizontal_drift_sum += float(
                            successful_max_horizontal_drift.sum().item()
                        )
                        trajectory_max_horizontal_drift_max = max(
                            trajectory_max_horizontal_drift_max,
                            float(successful_max_horizontal_drift.max().item()),
                        )
                        trajectory_max_horizontal_speed_sum += float(
                            successful_max_horizontal_speed.sum().item()
                        )
                        trajectory_max_horizontal_speed_max = max(
                            trajectory_max_horizontal_speed_max,
                            float(successful_max_horizontal_speed.max().item()),
                        )
                        trajectory_max_base_angular_speed_sum += float(
                            successful_max_base_angular_speed.sum().item()
                        )
                        trajectory_max_base_angular_speed_max = max(
                            trajectory_max_base_angular_speed_max,
                            float(successful_max_base_angular_speed.max().item()),
                        )
                        trajectory_max_abs_base_angular_velocity_sum += (
                            successful_max_abs_base_angular_velocity.double().sum(
                                dim=0
                            )
                        )
                        trajectory_max_abs_base_angular_velocity_max = torch.maximum(
                            trajectory_max_abs_base_angular_velocity_max,
                            successful_max_abs_base_angular_velocity.double().amax(
                                dim=0
                            ),
                        )
                        trajectory_post_settling_max_base_angular_speed_sum += float(
                            successful_post_settling_max_base_angular_speed
                            .sum()
                            .item()
                        )
                        trajectory_post_settling_max_base_angular_speed_max = max(
                            trajectory_post_settling_max_base_angular_speed_max,
                            float(
                                successful_post_settling_max_base_angular_speed
                                .max()
                                .item()
                            ),
                        )
                        trajectory_max_waist_velocity_sum += (
                            successful_max_waist_velocity.double().sum(dim=0)
                        )
                        trajectory_max_waist_velocity_max = torch.maximum(
                            trajectory_max_waist_velocity_max,
                            successful_max_waist_velocity.double().amax(dim=0),
                        )
                        endpoint_strict = (
                            bank_standing_valid[horizon_success]
                            & bank_post_settling_motion_valid[horizon_success]
                        )
                        if self.competence_require_endpoint_double_support:
                            endpoint_strict &= endpoint_double_support
                        strict_standing_episodes += int(
                            endpoint_strict.sum().item()
                        )
                        endpoint_recovered = (
                            bank_safety_valid[horizon_success]
                            & bank_post_settling_standing_valid[horizon_success]
                            & motion_duty_valid
                        )
                        if self.competence_require_endpoint_double_support:
                            endpoint_recovered &= endpoint_double_support
                        recovered_standing_episodes += int(
                            endpoint_recovered.sum().item()
                        )
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
                fallen_initial_abs_velocity_sum += initial_root_velocity[
                    bank_fell
                ].abs().double().sum(dim=0)
                successful_initial_abs_velocity_sum += initial_root_velocity[
                    ~bank_fell
                ].abs().double().sum(dim=0)
                fallen_injected_abs_velocity_sum += injected_root_velocity[
                    bank_fell
                ].abs().double().sum(dim=0)
                successful_injected_abs_velocity_sum += injected_root_velocity[
                    ~bank_fell
                ].abs().double().sum(dim=0)
                fallen_initial_count += int(bank_fell.sum().item())
                successful_initial_count += int((~bank_fell).sum().item())
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
                "mean_base_height": base_height_sum
                / max(state_diagnostic_rows, 1),
                "mean_gravity_error": gravity_error_sum
                / max(state_diagnostic_rows, 1),
                "mean_abs_waist_pitch_roll_deviation": (
                    waist_deviation_sum / max(state_diagnostic_rows, 1)
                ).tolist(),
                "double_support_fraction": double_support_sum
                / max(state_diagnostic_rows, 1),
                "successful_endpoint_mean_base_height": (
                    successful_endpoint_height_sum
                    / max(successful_endpoint_count, 1)
                ),
                "successful_endpoint_min_base_height": (
                    successful_endpoint_height_min
                    if successful_endpoint_count > 0
                    else None
                ),
                "successful_endpoint_mean_gravity_error": (
                    successful_endpoint_gravity_error_sum
                    / max(successful_endpoint_count, 1)
                ),
                "successful_endpoint_max_gravity_error": (
                    successful_endpoint_gravity_error_max
                    if successful_endpoint_count > 0
                    else None
                ),
                "successful_endpoint_mean_abs_waist_pitch_roll_deviation": (
                    successful_endpoint_waist_deviation_sum
                    / max(successful_endpoint_count, 1)
                ).tolist(),
                "successful_endpoint_max_abs_waist_pitch_roll_deviation": (
                    successful_endpoint_waist_deviation_max.tolist()
                    if successful_endpoint_count > 0
                    else None
                ),
                "strict_standing_episodes": strict_standing_episodes,
                "strict_standing_fraction": strict_standing_episodes
                / max(result.episodes, 1),
                "recovered_standing_episodes": recovered_standing_episodes,
                "recovered_standing_fraction": recovered_standing_episodes
                / max(result.episodes, 1),
                "trajectory_safety_valid_episodes": (
                    trajectory_safety_valid_episodes
                ),
                "trajectory_post_settling_standing_valid_episodes": (
                    trajectory_post_settling_standing_valid_episodes
                ),
                "trajectory_motion_duty_valid_episodes": (
                    trajectory_motion_duty_valid_episodes
                ),
                "trajectory_mean_motion_violation_steps": (
                    trajectory_motion_violation_steps_sum
                    / max(successful_endpoint_count, 1)
                ),
                "trajectory_max_motion_violation_steps": (
                    trajectory_motion_violation_steps_max
                ),
                "trajectory_mean_motion_violation_fraction": (
                    trajectory_motion_violation_fraction_sum
                    / max(successful_endpoint_count, 1)
                ),
                "trajectory_max_motion_violation_fraction": (
                    trajectory_motion_violation_fraction_max
                ),
                "trajectory_max_consecutive_motion_violation_steps": (
                    trajectory_motion_max_consecutive_steps_max
                ),
                "trajectory_height_valid_episodes": (
                    trajectory_height_valid_episodes
                ),
                "trajectory_gravity_valid_episodes": (
                    trajectory_gravity_valid_episodes
                ),
                "trajectory_waist_valid_episodes": trajectory_waist_valid_episodes,
                "trajectory_motion_valid_episodes": trajectory_motion_valid_episodes,
                "trajectory_post_settling_motion_valid_episodes": (
                    trajectory_post_settling_motion_valid_episodes
                ),
                "trajectory_post_settling_drift_valid_episodes": (
                    trajectory_post_settling_drift_valid_episodes
                ),
                "trajectory_post_settling_horizontal_speed_valid_episodes": (
                    trajectory_post_settling_horizontal_speed_valid_episodes
                ),
                "trajectory_post_settling_angular_speed_valid_episodes": (
                    trajectory_post_settling_angular_speed_valid_episodes
                ),
                "trajectory_post_settling_waist_velocity_valid_episodes": (
                    trajectory_post_settling_waist_velocity_valid_episodes
                ),
                "endpoint_double_support_episodes": (
                    endpoint_double_support_episodes
                ),
                "trajectory_mean_max_gravity_error": (
                    trajectory_max_gravity_error_sum
                    / max(successful_endpoint_count, 1)
                ),
                "trajectory_max_gravity_error": (
                    trajectory_max_gravity_error_max
                    if successful_endpoint_count > 0
                    else None
                ),
                "trajectory_mean_max_abs_waist_pitch_roll_deviation": (
                    trajectory_max_waist_deviation_sum
                    / max(successful_endpoint_count, 1)
                ).tolist(),
                "trajectory_max_abs_waist_pitch_roll_deviation": (
                    trajectory_max_waist_deviation_max.tolist()
                    if successful_endpoint_count > 0
                    else None
                ),
                "trajectory_mean_last_gravity_violation_step": (
                    trajectory_last_gravity_violation_step_sum
                    / max(successful_endpoint_count, 1)
                ),
                "trajectory_max_last_gravity_violation_step": (
                    trajectory_last_gravity_violation_step_max
                ),
                "trajectory_mean_last_waist_violation_step": (
                    trajectory_last_waist_violation_step_sum
                    / max(successful_endpoint_count, 1)
                ),
                "trajectory_max_last_waist_violation_step": (
                    trajectory_last_waist_violation_step_max
                ),
                "trajectory_mean_last_motion_violation_step": (
                    trajectory_last_motion_violation_step_sum
                    / max(successful_endpoint_count, 1)
                ),
                "trajectory_max_last_motion_violation_step": (
                    trajectory_last_motion_violation_step_max
                ),
                "trajectory_mean_max_horizontal_drift": (
                    trajectory_max_horizontal_drift_sum
                    / max(successful_endpoint_count, 1)
                ),
                "trajectory_max_horizontal_drift": (
                    trajectory_max_horizontal_drift_max
                    if successful_endpoint_count > 0
                    else None
                ),
                "trajectory_mean_max_horizontal_speed": (
                    trajectory_max_horizontal_speed_sum
                    / max(successful_endpoint_count, 1)
                ),
                "trajectory_max_horizontal_speed": (
                    trajectory_max_horizontal_speed_max
                    if successful_endpoint_count > 0
                    else None
                ),
                "trajectory_mean_max_base_angular_speed": (
                    trajectory_max_base_angular_speed_sum
                    / max(successful_endpoint_count, 1)
                ),
                "trajectory_max_base_angular_speed": (
                    trajectory_max_base_angular_speed_max
                    if successful_endpoint_count > 0
                    else None
                ),
                "trajectory_mean_max_abs_base_angular_velocity": (
                    trajectory_max_abs_base_angular_velocity_sum
                    / max(successful_endpoint_count, 1)
                ).tolist(),
                "trajectory_max_abs_base_angular_velocity": (
                    trajectory_max_abs_base_angular_velocity_max.tolist()
                    if successful_endpoint_count > 0
                    else None
                ),
                "trajectory_post_settling_mean_max_base_angular_speed": (
                    trajectory_post_settling_max_base_angular_speed_sum
                    / max(successful_endpoint_count, 1)
                ),
                "trajectory_post_settling_max_base_angular_speed": (
                    trajectory_post_settling_max_base_angular_speed_max
                    if successful_endpoint_count > 0
                    else None
                ),
                "trajectory_mean_max_abs_waist_pitch_roll_velocity": (
                    trajectory_max_waist_velocity_sum
                    / max(successful_endpoint_count, 1)
                ).tolist(),
                "trajectory_max_abs_waist_pitch_roll_velocity": (
                    trajectory_max_waist_velocity_max.tolist()
                    if successful_endpoint_count > 0
                    else None
                ),
                "fallen_first_observation_mean_abs_base_linear_velocity": (
                    fallen_initial_abs_velocity_sum[:3]
                    / max(fallen_initial_count, 1)
                ).tolist(),
                "fallen_first_observation_mean_abs_base_angular_velocity": (
                    fallen_initial_abs_velocity_sum[3:]
                    / max(fallen_initial_count, 1)
                ).tolist(),
                "successful_first_observation_mean_abs_base_linear_velocity": (
                    successful_initial_abs_velocity_sum[:3]
                    / max(successful_initial_count, 1)
                ).tolist(),
                "successful_first_observation_mean_abs_base_angular_velocity": (
                    successful_initial_abs_velocity_sum[3:]
                    / max(successful_initial_count, 1)
                ).tolist(),
                "fallen_injected_mean_abs_base_linear_velocity": (
                    fallen_injected_abs_velocity_sum[:3]
                    / max(fallen_initial_count, 1)
                ).tolist(),
                "fallen_injected_mean_abs_base_angular_velocity": (
                    fallen_injected_abs_velocity_sum[3:]
                    / max(fallen_initial_count, 1)
                ).tolist(),
                "successful_injected_mean_abs_base_linear_velocity": (
                    successful_injected_abs_velocity_sum[:3]
                    / max(successful_initial_count, 1)
                ).tolist(),
                "successful_injected_mean_abs_base_angular_velocity": (
                    successful_injected_abs_velocity_sum[3:]
                    / max(successful_initial_count, 1)
                ).tolist(),
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
            self.env.max_episode_length = original_max_episode_length
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
        self._loaded_checkpoint_path = os.path.abspath(str(ckpt_path))
        resume_learning_rate = self.config.get("resume_learning_rate", None)
        if resume_learning_rate is not None:
            resume_learning_rate = float(resume_learning_rate)
            if resume_learning_rate <= 0.0:
                raise ValueError("resume_learning_rate must be positive")
            self.set_learning_rate(resume_learning_rate, resume_learning_rate)
            for optimizer in (self.actor_optimizer, self.critic_optimizer):
                for param_group in optimizer.param_groups:
                    param_group["lr"] = resume_learning_rate
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
