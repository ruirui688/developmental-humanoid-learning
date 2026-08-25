"""PBHC MHPPO extension implementing the developmental Body Schema loss."""

from __future__ import annotations

import torch
from torch import nn, optim

from humanoidverse.agents.mh_ppo.mh_ppo import MHPPO
from humanoidverse.agents.modules.ppo_modules import PPOCritic

from .body_schema import BodySchemaActor


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

    def save(self, path, infos=None):
        checkpoint_info = dict(infos or {})
        checkpoint_info["maturation_state"] = self.env.maturation_state_dict()
        super().save(path, checkpoint_info)

    def load(self, ckpt_path):
        infos = super().load(ckpt_path)
        if isinstance(infos, dict) and "maturation_state" in infos:
            self.env.load_maturation_state_dict(infos["maturation_state"])
        return infos

    def _init_loss_dict_at_training_step(self):
        losses = super()._init_loss_dict_at_training_step()
        losses["Body_Schema"] = 0
        return losses

    def _update_algo_step(self, policy_state_dict, loss_dict):
        loss_dict = super()._update_algo_step(policy_state_dict, loss_dict)

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
