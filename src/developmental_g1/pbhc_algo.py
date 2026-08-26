"""PBHC MHPPO extension implementing the developmental Body Schema loss."""

from __future__ import annotations

from dataclasses import asdict
import copy
import hashlib
import json
import os

import torch
from torch import nn, optim

from humanoidverse.agents.mh_ppo.mh_ppo import MHPPO
from humanoidverse.agents.modules.ppo_modules import PPOCritic

from .body_schema import BodySchemaActor
from .capability_frontier import FrontierEvidence
from .developmental_phase_gate import PhaseEvidence
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
        self.body_schema_learning_rate = float(
            schema.get("learning_rate", self.actor_learning_rate)
        )
        if self.body_schema_learning_rate <= 0.0:
            raise ValueError("body schema learning rate must be positive")
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
        self.schema_optimizer = optim.Adam(
            self.actor.schema_head.parameters(),
            lr=self.body_schema_learning_rate,
        )
        self.critic_optimizer = optim.Adam(
            self.critic.parameters(), lr=self.critic_learning_rate
        )
        consolidation = self.config.get("policy_consolidation", {})
        self.policy_consolidation_enabled = bool(
            consolidation.get("enabled", False)
        )
        self.policy_consolidation_retention_rate = float(
            consolidation.get("retention_rate", 0.0)
        )
        if not 0.0 <= self.policy_consolidation_retention_rate <= 1.0:
            raise ValueError("policy consolidation retention rate must be in [0, 1]")
        stage_rates = consolidation.get("retention_rate_by_stage", None)
        self.policy_consolidation_retention_rates = (
            None if stage_rates is None else [float(rate) for rate in stage_rates]
        )
        if self.policy_consolidation_retention_rates is not None:
            if len(self.policy_consolidation_retention_rates) != len(
                self.env.maturation_controller.stages
            ):
                raise ValueError(
                    "policy consolidation retention_rate_by_stage must match "
                    "the maturation stage count"
                )
            if any(
                not 0.0 <= rate <= 1.0
                for rate in self.policy_consolidation_retention_rates
            ):
                raise ValueError(
                    "policy consolidation retention rates must be in [0, 1]"
                )
        self.policy_consolidation_anchor = None

    def _policy_consolidation_rate(self) -> float:
        if self.policy_consolidation_retention_rates is None:
            return self.policy_consolidation_retention_rate
        return self.policy_consolidation_retention_rates[
            self.env.maturation_controller.stage_index
        ]

    def _refresh_policy_consolidation_anchor(self) -> None:
        if not self.policy_consolidation_enabled:
            return
        # Some PBHC actor implementations cache the most recent sampled
        # distribution on the module.  After evaluation those cached tensors
        # are non-leaf autograd values, which makes deepcopy fail exactly at a
        # curriculum transition.  Reuse the already clean anchor module and
        # copy only the serializable model state when refreshing it.
        if self.policy_consolidation_anchor is None:
            self.policy_consolidation_anchor = copy.deepcopy(self.actor)
        else:
            self.policy_consolidation_anchor.load_state_dict(
                self.actor.state_dict()
            )
        self.policy_consolidation_anchor.eval()
        for parameter in self.policy_consolidation_anchor.parameters():
            parameter.requires_grad_(False)

    def _training_step(self):
        losses = super()._training_step()
        retention_rate = self._policy_consolidation_rate()
        if (
            self.policy_consolidation_anchor is not None
            and retention_rate > 0.0
        ):
            anchor_parameters = dict(
                self.policy_consolidation_anchor.named_parameters()
            )
            with torch.no_grad():
                for name, parameter in self.actor.named_parameters():
                    if name.startswith(("encoder.", "action_head.")):
                        if name == "encoder.0.weight":
                            history_end = int(
                                self.env.config.obs.post_compute_config.obs_slices[
                                    "actor_obs"
                                ]["history"][1]
                            )
                            torque_history_width = 4 * int(self.env.num_dof)
                            torque_history_start = (
                                history_end - torque_history_width
                            )
                            # Preserve the previously mastered perception and
                            # action pathway, but do not pull newly introduced
                            # torque-feedback weights back toward their zero-
                            # initialized checkpoint-migration anchor.
                            parameter[:, :torque_history_start].lerp_(
                                anchor_parameters[name][
                                    :, :torque_history_start
                                ],
                                retention_rate,
                            )
                            parameter[:, history_end:].lerp_(
                                anchor_parameters[name][:, history_end:],
                                retention_rate,
                            )
                        else:
                            parameter.lerp_(
                                anchor_parameters[name],
                                retention_rate,
                            )
        return losses

    def _actor_act_step(self, obs_dict):
        self.actor.noise_scale = float(
            self.env.maturation_controller.stage.exploration_scale
        )
        return super()._actor_act_step(obs_dict)

    def _rollout_step(self, obs_dict):
        if (
            self.env.capability_frontier_enabled
            and not self.env.capability_frontier.calibrated
        ):
            calibration = self.evaluate_competence_window(
                seed=self.competence_eval_seed - 1,
                episode_banks=self.competence_eval_episode_banks,
                horizon_steps=self.competence_horizon_steps[0],
            )
            update = self.env.update_capability_frontier(
                self._frontier_evidence(calibration)
            )
            with open(
                os.path.join(self.log_dir, "frontier_calibration.json"),
                "w",
                encoding="utf-8",
            ) as stream:
                json.dump(
                    {
                        "rl_environment_steps": 0,
                        "evaluation_steps": calibration.evaluation_steps,
                        "sample": asdict(calibration.sample),
                        "diagnostics": self.last_competence_diagnostics,
                        "frontier_update": asdict(update),
                    },
                    stream,
                    indent=2,
                    sort_keys=True,
                )
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
            if self.env._phase_gate_ready:
                diagnostics = self.last_competence_diagnostics
                def conservative_event(name):
                    return float(
                        diagnostics.get(
                            f"event_{name}_conservative_fraction",
                            diagnostics[f"event_{name}_fraction"],
                        )
                    )

                pose_event_names = {
                    1: ("rolling", "bracing"),
                    2: ("raised",),
                    3: ("upright",),
                    4: ("independent_standing",),
                }.get(gate_stage_index)
                if pose_event_names and self.env._ground_curriculum_ready:
                    if gate_stage_index == 2:
                        # Before any pose reaches the final 0.45 m event, using
                        # `raised` makes every competence value zero and leaves
                        # training sampling uniform. Focus the within-stage
                        # rehearsal on failure at the current height subgoal;
                        # held-out evaluation remains uniformly distributed.
                        pose_competence = [
                            float(
                                diagnostics[
                                    f"reset_pose_{pose_name}_height_target_success_fraction"
                                ]
                            )
                            for pose_name in self.env.ground_pose_names
                        ]
                    else:
                        pose_competence = [
                            min(
                                float(
                                    diagnostics[
                                        f"reset_pose_{pose_name}_event_{event_name}_fraction"
                                    ]
                                )
                                for event_name in pose_event_names
                            )
                            for pose_name in self.env.ground_pose_names
                        ]
                    self.env.update_ground_pose_sampling(pose_competence)
                    diagnostics.update(
                        {
                            f"training_reset_pose_{pose_name}_sampling_probability": float(
                                probability.item()
                            )
                            for pose_name, probability in zip(
                                self.env.ground_pose_names,
                                self.env.ground_pose_sampling_weights,
                            )
                        }
                    )

                if gate_stage_index == 2 and self.env.capability_frontier_enabled:
                    rise_frontier_update = self.env.update_rise_frontier(
                        self._frontier_evidence(result)
                    )
                    diagnostics.update(
                        {
                            "rise_frontier_previous_height_target": float(
                                rise_frontier_update.previous_height_target
                            ),
                            "rise_frontier_height_target": float(
                                rise_frontier_update.height_target
                            ),
                            "rise_frontier_advanced": bool(
                                rise_frontier_update.advanced
                            ),
                            "rise_frontier_reason": rise_frontier_update.reason,
                        }
                    )

                schema_gate_accuracy = float(
                    diagnostics.get(
                        "body_schema_dynamic_accuracy",
                        result.sample.schema_accuracy,
                    )
                )
                transition = self.env.update_developmental_phase(
                    PhaseEvidence(
                        schema_accuracy=schema_gate_accuracy,
                        rolling=conservative_event("rolling"),
                        bracing=conservative_event("bracing"),
                        rolling_and_bracing=min(
                            conservative_event("rolling"),
                            conservative_event("bracing"),
                        ),
                        raised=conservative_event("raised"),
                        upright=conservative_event("upright"),
                        independent_standing=conservative_event(
                            "independent_standing"
                        ),
                        safe_fraction=float(result.sample.low_risk),
                        low_saturation_fraction=float(result.sample.low_saturation),
                    )
                )
            elif self.env.capability_frontier_enabled:
                transition = self.env.update_capability_frontier(
                    self._frontier_evidence(result)
                )
            else:
                transition = self.env.update_competence(result.sample)
            if (
                self.env._phase_gate_ready
                and getattr(transition, "advanced", False)
            ):
                self._refresh_policy_consolidation_anchor()
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

    def _frontier_evidence(self, result) -> FrontierEvidence:
        diagnostics = self.last_competence_diagnostics
        return FrontierEvidence(
            height_quantile=float(
                diagnostics.get(
                    "frontier_conservative_height_quantile",
                    diagnostics["frontier_height_quantile"],
                )
            ),
            upright_quantile=float(
                diagnostics.get(
                    "frontier_conservative_upright_quantile",
                    diagnostics["frontier_upright_quantile"],
                )
            ),
            height_target_success_fraction=float(
                diagnostics.get(
                    "frontier_conservative_height_target_success_fraction",
                    diagnostics["frontier_height_target_success_fraction"],
                )
            ),
            upright_target_success_fraction=float(
                diagnostics.get(
                    "frontier_conservative_upright_target_success_fraction",
                    diagnostics["frontier_upright_target_success_fraction"],
                )
            ),
            safe_fraction=float(result.sample.low_risk),
            saturation_fraction=float(1.0 - result.sample.low_saturation),
            schema_accuracy=float(result.sample.schema_accuracy),
            episodes=int(result.episodes),
        )

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
            torque_saturation_count = torch.zeros_like(action_abs_sum)
            early_torque_saturation_count = torch.zeros_like(action_abs_sum)
            late_torque_saturation_count = torch.zeros_like(action_abs_sum)
            diagnostic_signal_rows = 0
            early_torque_rows = 0
            late_torque_rows = 0
            early_unsafe_impact_count = 0
            late_unsafe_impact_count = 0
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
            frontier_height_maxima = []
            frontier_upright_maxima = []
            event_achievements = (
                {
                    name: []
                    for name in self.env.developmental_event_tracker.event_names
                }
                if self.env._developmental_events_ready
                else {}
            )
            assistance_impulses = []
            assistance_abs_work = []
            assistance_peak_forces = []
            ground_reset_pose_indices = []
            schema_model_mse_sum = 0.0
            schema_persistence_mse_sum = 0.0
            schema_metric_rows = 0
            schema_joint_count = self.env.num_dof
            schema_group_slices = {
                "joint_position": slice(0, schema_joint_count),
                "joint_velocity": slice(schema_joint_count, 2 * schema_joint_count),
                "projected_gravity": slice(
                    2 * schema_joint_count, 2 * schema_joint_count + 3
                ),
                "base_angular_velocity": slice(
                    2 * schema_joint_count + 3, 2 * schema_joint_count + 6
                ),
            }
            schema_group_model_mse_sum = {
                name: 0.0 for name in schema_group_slices
            }
            schema_group_persistence_mse_sum = {
                name: 0.0 for name in schema_group_slices
            }
            schema_group_accuracy_sum = {
                name: 0.0 for name in schema_group_slices
            }
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
                if self.env._ground_curriculum_ready:
                    ground_reset_pose_indices.append(
                        self.env.ground_reset_pose_indices.clone()
                    )
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
                bank_frontier_max_height = torch.zeros(
                    self.env.num_envs, device=self.device
                )
                bank_frontier_max_upright = torch.zeros_like(
                    bank_frontier_max_height
                )
                active = torch.ones(
                    self.env.num_envs, device=self.device, dtype=torch.bool
                )
                episode_steps = torch.zeros(
                    self.env.num_envs, device=self.device, dtype=torch.long
                )
                for _ in range(horizon_steps):
                    actor_obs = observations["actor_obs"]
                    current_schema_target = (
                        observations["body_schema_target"]
                        * self.body_schema_target_scale
                    )
                    raw_actions = self.actor.act_inference(actor_obs)
                    next_observations, _, dones, infos = self.env.step(
                        {"actions": raw_actions}
                    )
                    prediction = self.actor.predict_body_schema(
                        actor_obs,
                        self.env.actions_after_delay,
                        current_schema_target,
                    )
                    target = (
                        next_observations["body_schema_target"]
                        * self.body_schema_target_scale
                    )
                    schema_mse = torch.mean(
                        torch.square(prediction - target), dim=-1
                    )
                    persistence_mse = torch.mean(
                        torch.square(current_schema_target - target), dim=-1
                    )
                    # A small absolute target makes an untrained near-zero
                    # predictor look deceptively accurate. Require predictive
                    # skill over the causal persistence baseline instead.
                    schema_accuracy = torch.clamp(
                        1.0
                        - schema_mse
                        / persistence_mse.clamp_min(1e-8),
                        min=0.0,
                        max=1.0,
                    )
                    gravity_error = torch.sum(
                        torch.square(self.env.projected_gravity[:, :2]), dim=-1
                    )
                    frontier_upright = torch.exp(
                        -gravity_error
                        / float(self.env.developmental_goal_upright_sigma)
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
                    active_torque_saturation = (
                        torque_ratio[active_indices] >= 0.95
                    )
                    torque_saturation_count += (
                        active_torque_saturation.double().sum(dim=0)
                    )
                    early_rows = episode_steps[active_indices] <= 10
                    if torch.any(early_rows):
                        early_torque_saturation_count += (
                            active_torque_saturation[early_rows]
                            .double()
                            .sum(dim=0)
                        )
                        early_torque_rows += int(early_rows.sum().item())
                        early_unsafe_impact_count += int(
                            (
                                nonfoot_force[active_indices][early_rows]
                                > float(
                                    self.env.config.developmental.severe_impact_force
                                )
                            )
                            .sum()
                            .item()
                        )
                    if torch.any(~early_rows):
                        late_torque_saturation_count += (
                            active_torque_saturation[~early_rows]
                            .double()
                            .sum(dim=0)
                        )
                        late_torque_rows += int((~early_rows).sum().item())
                        late_unsafe_impact_count += int(
                            (
                                nonfoot_force[active_indices][~early_rows]
                                > float(
                                    self.env.config.developmental.severe_impact_force
                                )
                            )
                            .sum()
                            .item()
                        )
                    schema_model_mse_sum += float(
                        schema_mse[active_indices].sum().item()
                    )
                    schema_persistence_mse_sum += float(
                        persistence_mse[active_indices].sum().item()
                    )
                    schema_metric_rows += int(active_indices.numel())
                    for group_name, group_slice in schema_group_slices.items():
                        group_model_mse = torch.mean(
                            torch.square(
                                prediction[:, group_slice] - target[:, group_slice]
                            ),
                            dim=-1,
                        )
                        group_persistence_mse = torch.mean(
                            torch.square(
                                current_schema_target[:, group_slice]
                                - target[:, group_slice]
                            ),
                            dim=-1,
                        )
                        schema_group_model_mse_sum[group_name] += float(
                            group_model_mse[active_indices].sum().item()
                        )
                        schema_group_persistence_mse_sum[group_name] += float(
                            group_persistence_mse[active_indices].sum().item()
                        )
                        schema_group_accuracy_sum[group_name] += float(
                            torch.clamp(
                                1.0
                                - group_model_mse
                                / group_persistence_mse.clamp_min(1e-8),
                                min=0.0,
                                max=1.0,
                            )[active_indices]
                            .sum()
                            .item()
                        )
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
                    bank_frontier_max_height[valid_state_indices] = torch.maximum(
                        bank_frontier_max_height[valid_state_indices], active_heights
                    )
                    bank_frontier_max_upright[valid_state_indices] = torch.maximum(
                        bank_frontier_max_upright[valid_state_indices],
                        frontier_upright[valid_state_indices],
                    )
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
                        # Ground-start stages use a frozen stage-relative goal
                        # (safe exploration, rising, then upright standing).
                        upright=self.env.developmental_competence_score()[
                            active_indices
                        ],
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
                frontier_height_maxima.append(bank_frontier_max_height)
                frontier_upright_maxima.append(bank_frontier_max_upright)
                if self.env._developmental_events_ready:
                    for name in event_achievements:
                        event_achievements[name].append(
                            self.env.developmental_event_tracker.achieved[name].clone()
                        )
                if self.env._assistance_ready:
                    assistance_impulses.append(self.env.assistance_impulse.clone())
                    assistance_abs_work.append(self.env.assistance_abs_work.clone())
                    assistance_peak_forces.append(
                        self.env.assistance_peak_force.clone()
                    )
            if not window.complete:
                raise RuntimeError("held-out competence evaluation bank is incomplete")
            result = window.result()
            all_frontier_heights = torch.cat(frontier_height_maxima)
            all_frontier_upright = torch.cat(frontier_upright_maxima)
            all_ground_reset_pose_indices = (
                torch.cat(ground_reset_pose_indices)
                if ground_reset_pose_indices
                else None
            )
            all_event_achievements = {
                name: torch.cat(values)
                for name, values in event_achievements.items()
                if values
            }
            frontier_quantile = 0.80
            frontier_height_target = (
                self.env.capability_frontier.height_target
                if self.env.capability_frontier_enabled
                else self.competence_standing_min_base_height
            )
            frontier_upright_target = (
                self.env.capability_frontier.upright_target
                if self.env.capability_frontier_enabled
                else 0.90
            )
            pose_diagnostics = {}
            if all_ground_reset_pose_indices is not None:
                pose_height_quantiles = []
                pose_upright_quantiles = []
                pose_height_success_fractions = []
                pose_upright_success_fractions = []
                pose_event_fractions = {
                    name: [] for name in all_event_achievements
                }
                for pose_index, pose_name in enumerate(self.env.ground_pose_names):
                    pose_mask = all_ground_reset_pose_indices == pose_index
                    pose_heights = all_frontier_heights[pose_mask]
                    pose_uprights = all_frontier_upright[pose_mask]
                    height_quantile = torch.quantile(pose_heights, 0.80)
                    upright_quantile = torch.quantile(pose_uprights, 0.80)
                    height_success = (
                        (pose_heights >= frontier_height_target).float().mean()
                    )
                    upright_success = (
                        (pose_uprights >= frontier_upright_target).float().mean()
                    )
                    pose_height_quantiles.append(height_quantile)
                    pose_upright_quantiles.append(upright_quantile)
                    pose_height_success_fractions.append(height_success)
                    pose_upright_success_fractions.append(upright_success)
                    event_fractions = {
                        name: achievements[pose_mask].float().mean()
                        for name, achievements in all_event_achievements.items()
                    }
                    for name, fraction in event_fractions.items():
                        pose_event_fractions[name].append(fraction)
                    pose_diagnostics.update(
                        {
                            f"reset_pose_{pose_name}_episodes": int(
                                pose_mask.sum().item()
                            ),
                            f"reset_pose_{pose_name}_height_q80": float(
                                height_quantile.item()
                            ),
                            f"reset_pose_{pose_name}_upright_q80": float(
                                upright_quantile.item()
                            ),
                            f"reset_pose_{pose_name}_height_target_success_fraction": float(
                                height_success.item()
                            ),
                            f"reset_pose_{pose_name}_upright_target_success_fraction": float(
                                upright_success.item()
                            ),
                            **{
                                f"reset_pose_{pose_name}_event_{name}_fraction": float(
                                    fraction.item()
                                )
                                for name, fraction in event_fractions.items()
                            },
                        }
                    )
                pose_diagnostics.update(
                    {
                        "frontier_conservative_height_quantile": float(
                            torch.stack(pose_height_quantiles).min().item()
                        ),
                        "frontier_conservative_upright_quantile": float(
                            torch.stack(pose_upright_quantiles).min().item()
                        ),
                        "frontier_conservative_height_target_success_fraction": float(
                            torch.stack(pose_height_success_fractions).min().item()
                        ),
                        "frontier_conservative_upright_target_success_fraction": float(
                            torch.stack(pose_upright_success_fractions).min().item()
                        ),
                        **{
                            f"event_{name}_conservative_fraction": float(
                                torch.stack(fractions).min().item()
                            )
                            for name, fractions in pose_event_fractions.items()
                        },
                    }
                )
            per_joint_boundary = action_boundary_count / max(
                diagnostic_signal_rows, 1
            )
            per_joint_abs = action_abs_sum / max(diagnostic_signal_rows, 1)
            per_joint_torque_saturation = torque_saturation_count / max(
                diagnostic_signal_rows, 1
            )
            per_joint_early_torque_saturation = (
                early_torque_saturation_count / max(early_torque_rows, 1)
            )
            per_joint_late_torque_saturation = (
                late_torque_saturation_count / max(late_torque_rows, 1)
            )
            self.last_competence_diagnostics = {
                "frontier_quantile": frontier_quantile,
                "frontier_height_quantile": float(
                    torch.quantile(all_frontier_heights, frontier_quantile).item()
                ),
                "frontier_upright_quantile": float(
                    torch.quantile(all_frontier_upright, frontier_quantile).item()
                ),
                "frontier_height_target_success_fraction": float(
                    (all_frontier_heights >= frontier_height_target)
                    .float()
                    .mean()
                    .item()
                ),
                "frontier_upright_target_success_fraction": float(
                    (all_frontier_upright >= frontier_upright_target)
                    .float()
                    .mean()
                    .item()
                ),
                **{
                    f"event_{name}_fraction": float(values.float().mean().item())
                    for name, values in all_event_achievements.items()
                },
                **pose_diagnostics,
                "assistance_mean_impulse_ns": (
                    float(torch.cat(assistance_impulses).mean().item())
                    if assistance_impulses
                    else 0.0
                ),
                "assistance_mean_abs_work_j": (
                    float(torch.cat(assistance_abs_work).mean().item())
                    if assistance_abs_work
                    else 0.0
                ),
                "assistance_mean_peak_force_n": (
                    float(torch.cat(assistance_peak_forces).mean().item())
                    if assistance_peak_forces
                    else 0.0
                ),
                "body_schema_model_mse": schema_model_mse_sum
                / max(schema_metric_rows, 1),
                "body_schema_persistence_mse": schema_persistence_mse_sum
                / max(schema_metric_rows, 1),
                "body_schema_skill_definition": (
                    "clip(1 - model_mse / persistence_mse, 0, 1)"
                ),
                "body_schema_group_model_mse": {
                    name: value / max(schema_metric_rows, 1)
                    for name, value in schema_group_model_mse_sum.items()
                },
                "body_schema_group_persistence_mse": {
                    name: value / max(schema_metric_rows, 1)
                    for name, value in schema_group_persistence_mse_sum.items()
                },
                "body_schema_group_accuracy": {
                    name: value / max(schema_metric_rows, 1)
                    for name, value in schema_group_accuracy_sum.items()
                },
                "body_schema_dynamic_accuracy": 0.5
                * (
                    schema_group_accuracy_sum["joint_velocity"]
                    + schema_group_accuracy_sum["base_angular_velocity"]
                )
                / max(schema_metric_rows, 1),
                "body_schema_gate_definition": (
                    "mean clipped skill over joint velocity and base angular velocity"
                ),
                "mean_abs_raw_action": float(per_joint_abs.mean().item()),
                "raw_action_boundary_fraction": float(
                    per_joint_boundary.mean().item()
                ),
                "early_unsafe_impact_fraction": early_unsafe_impact_count
                / max(early_torque_rows, 1),
                "late_unsafe_impact_fraction": late_unsafe_impact_count
                / max(late_torque_rows, 1),
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
                "per_joint_torque_saturation_fraction": {
                    name: float(value)
                    for name, value in zip(
                        self.env.dof_names,
                        per_joint_torque_saturation.tolist(),
                    )
                },
                "per_joint_early_torque_saturation_fraction": {
                    name: float(value)
                    for name, value in zip(
                        self.env.dof_names,
                        per_joint_early_torque_saturation.tolist(),
                    )
                },
                "per_joint_late_torque_saturation_fraction": {
                    name: float(value)
                    for name, value in zip(
                        self.env.dof_names,
                        per_joint_late_torque_saturation.tolist(),
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
        checkpoint_info["schema_optimizer_state_dict"] = (
            self.schema_optimizer.state_dict()
        )
        if self.policy_consolidation_anchor is not None:
            checkpoint_info["policy_consolidation_anchor_state_dict"] = (
                self.policy_consolidation_anchor.state_dict()
            )
        super().save(path, checkpoint_info)

    def load(self, ckpt_path):
        if ckpt_path is None:
            return None
        loaded_dict = torch.load(ckpt_path, map_location=self.device)
        actor_state = dict(loaded_dict["actor_model_state_dict"])
        critic_state = dict(loaded_dict["critic_model_state_dict"])
        migrated_observation = False
        obs_slices = self.env.config.obs.post_compute_config.obs_slices

        def migrate_input_weight(state, key, expected, obs_name):
            existing = state[key]
            if existing.shape == expected.shape:
                return False
            if existing.shape[0] != expected.shape[0]:
                raise ValueError(
                    f"cannot migrate {obs_name} checkpoint input "
                    f"{tuple(existing.shape)} to {tuple(expected.shape)}"
                )
            missing = expected.shape[1] - existing.shape[1]
            migrated = False
            torque_history_width = 4 * int(self.env.num_dof)
            if missing >= torque_history_width:
                # torque_ratio sorts last within the flattened history block.
                insertion = int(obs_slices[obs_name]["history"][1]) - (
                    torque_history_width
                )
                zero_columns = torch.zeros(
                    existing.shape[0],
                    torque_history_width,
                    device=existing.device,
                    dtype=existing.dtype,
                )
                existing = torch.cat(
                    (existing[:, :insertion], zero_columns, existing[:, insertion:]),
                    dim=1,
                )
                missing -= torque_history_width
                migrated = True
            if missing == 3:
                insertion = int(
                    obs_slices[obs_name]["initial_projected_gravity"][0]
                )
                zero_columns = torch.zeros(
                    existing.shape[0],
                    3,
                    device=existing.device,
                    dtype=existing.dtype,
                )
                existing = torch.cat(
                    (existing[:, :insertion], zero_columns, existing[:, insertion:]),
                    dim=1,
                )
                missing = 0
                migrated = True
            if missing != 0 or existing.shape != expected.shape:
                raise ValueError(
                    f"cannot migrate {obs_name} checkpoint input "
                    f"{tuple(state[key].shape)} to {tuple(expected.shape)}"
                )
            state[key] = existing
            return migrated

        input_specs = (
            (
                actor_state,
                "encoder.0.weight",
                self.actor.state_dict()["encoder.0.weight"],
                "actor_obs",
            ),
            (
                critic_state,
                "critic_module.module.0.weight",
                self.critic.state_dict()["critic_module.module.0.weight"],
                "critic_obs",
            ),
        )
        for state, key, expected, obs_name in input_specs:
            migrated_observation |= migrate_input_weight(
                state, key, expected, obs_name
            )
        self.actor.load_state_dict(actor_state)
        self.critic.load_state_dict(critic_state)
        if self.load_optimizer and not migrated_observation:
            self.actor_optimizer.load_state_dict(
                loaded_dict["actor_optimizer_state_dict"]
            )
            self.critic_optimizer.load_state_dict(
                loaded_dict["critic_optimizer_state_dict"]
            )
            self.actor_learning_rate = loaded_dict[
                "actor_optimizer_state_dict"
            ]["param_groups"][0]["lr"]
            self.critic_learning_rate = loaded_dict[
                "critic_optimizer_state_dict"
            ]["param_groups"][0]["lr"]
            self.set_learning_rate(
                self.actor_learning_rate, self.critic_learning_rate
            )
        self.current_learning_iteration = loaded_dict["iter"]
        infos = loaded_dict.get("infos")
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
        if isinstance(infos, dict) and "schema_optimizer_state_dict" in infos:
            self.schema_optimizer.load_state_dict(
                infos["schema_optimizer_state_dict"]
            )
        if self.policy_consolidation_enabled:
            self._refresh_policy_consolidation_anchor()
            anchor_state = (
                infos.get("policy_consolidation_anchor_state_dict")
                if isinstance(infos, dict)
                else None
            )
            if anchor_state is not None:
                anchor_state = dict(anchor_state)
                migrate_input_weight(
                    anchor_state,
                    "encoder.0.weight",
                    self.policy_consolidation_anchor.state_dict()[
                        "encoder.0.weight"
                    ],
                    "actor_obs",
                )
                self.policy_consolidation_anchor.load_state_dict(anchor_state)
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
            policy_state_dict["body_schema_target"]
            * self.body_schema_target_scale,
        )
        target = (
            policy_state_dict["next_body_schema_target"]
            * self.body_schema_target_scale
        )
        valid = (~policy_state_dict["dones"].squeeze(-1)).float()
        per_sample = torch.mean(torch.square(prediction - target), dim=-1)
        schema_loss = torch.sum(per_sample * valid) / valid.sum().clamp_min(1.0)

        self.schema_optimizer.zero_grad()
        (self.body_schema_loss_coef * schema_loss).backward()
        nn.utils.clip_grad_norm_(
            self.actor.schema_head.parameters(), self.max_grad_norm
        )
        self.schema_optimizer.step()

        loss_dict["Body_Schema"] += schema_loss.item()
        return loss_dict
