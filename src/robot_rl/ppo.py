"""Small CPU-friendly PPO implementation with an optional body-model head."""

from __future__ import annotations

from dataclasses import dataclass
import random
import numpy as np
import torch
from torch import nn
from torch.distributions import Normal

from .env import IdealStickmanEnv


@dataclass
class PPOConfig:
    num_envs: int = 32
    rollout_steps: int = 96
    total_updates: int = 80
    update_epochs: int = 4
    minibatch_size: int = 768
    learning_rate: float = 3e-4
    gamma: float = 0.99
    gae_lambda: float = 0.95
    clip_coef: float = 0.2
    entropy_coef: float = 0.005
    value_coef: float = 0.5
    max_grad_norm: float = 0.5
    body_model_coef: float = 0.0
    human_prior_coef: float = 0.50
    human_prior_samples: int = 8192
    human_prior_updates: int = 120


class ActorCritic(nn.Module):
    def __init__(self, obs_size: int, action_size: int) -> None:
        super().__init__()
        self.encoder = nn.Sequential(
            nn.Linear(obs_size, 64), nn.Tanh(), nn.Linear(64, 64), nn.Tanh()
        )
        self.actor = nn.Linear(64, action_size)
        # A separate critic prevents large value-regression gradients from
        # overwriting a previously acquired motor primitive in the actor.
        self.critic = nn.Sequential(
            nn.Linear(obs_size, 64), nn.Tanh(), nn.Linear(64, 64), nn.Tanh(), nn.Linear(64, 1)
        )
        self.log_std = nn.Parameter(torch.full((action_size,), -0.35))
        self.forward_model = nn.Sequential(
            nn.Linear(64 + action_size, 64), nn.SiLU(), nn.Linear(64, IdealStickmanEnv.proprioceptive_size)
        )

    def distribution_value(self, obs: torch.Tensor):
        latent = self.encoder(obs)
        mean = torch.tanh(self.actor(latent))
        dist = Normal(mean, self.log_std.exp().expand_as(mean))
        return dist, self.critic(obs).squeeze(-1), latent

    def act(self, obs: torch.Tensor, deterministic: bool = False):
        dist, value, _ = self.distribution_value(obs)
        action = dist.mean if deterministic else dist.sample()
        action = action.clamp(-1.0, 1.0)
        log_prob = dist.log_prob(action).sum(-1)
        return action, log_prob, value


def human_prior_action(obs: torch.Tensor, gait_amplitude: float | torch.Tensor | None = None) -> torch.Tensor:
    """Differentiation-free low-dimensional human gait/balance prior.

    The clock generates an alternating gait primitive; torso angle and angular
    velocity provide a vestibular-like common-hip reflex.  This is deliberately
    simple so the provenance of the prior is auditable.
    """
    sin_phase = obs[:, 11]
    if gait_amplitude is None:
        gait_amplitude = obs[:, 15]
    left = sin_phase
    right = -sin_phase
    left_knee = 0.10 + 0.50 * torch.relu(left)
    right_knee = 0.10 + 0.50 * torch.relu(right)
    neutral = 1.0 - gait_amplitude
    left_hip_ref = gait_amplitude * 0.48 * left
    right_hip_ref = gait_amplitude * 0.48 * right
    left_knee_ref = gait_amplitude * left_knee + neutral * 0.10
    right_knee_ref = gait_amplitude * right_knee + neutral * 0.10
    tilt = obs[:, 8]
    tilt_rate = 4.0 * obs[:, 9]
    correction = 0.70 * tilt + 0.12 * tilt_rate
    return torch.stack(
        [
            (left_hip_ref + correction) / 0.70,
            left_knee_ref / 0.60 - 1.0,
            (right_hip_ref + correction) / 0.70,
            right_knee_ref / 0.60 - 1.0,
        ],
        dim=1,
    ).clamp(-1.0, 1.0)


def pretrain_human_prior(model: ActorCritic, config: PPOConfig, seed: int) -> None:
    """Initialize the developmental policy from auditable synthetic prior samples."""
    generator = torch.Generator().manual_seed(seed + 91_337)
    n = config.human_prior_samples
    obs = torch.zeros((n, IdealStickmanEnv.observation_size))
    obs[:, :4] = 0.35 * torch.randn((n, 4), generator=generator)
    obs[:, 4:8] = 0.20 * torch.randn((n, 4), generator=generator)
    obs[:, 8] = torch.empty(n).uniform_(-0.35, 0.35, generator=generator)
    obs[:, 9] = torch.empty(n).uniform_(-0.20, 0.20, generator=generator)  # scaled tilt rate
    obs[:, 10] = torch.empty(n).uniform_(0.0, 1.0, generator=generator)
    phase = torch.empty(n).uniform_(-torch.pi, torch.pi, generator=generator)
    obs[:, 11], obs[:, 12] = torch.sin(phase), torch.cos(phase)
    obs[:, 13] = (obs[:, 11] <= 0).float()
    obs[:, 14] = 1.0 - obs[:, 13]
    amplitudes = torch.tensor([0.0, 0.35, 0.65, 1.0])
    obs[:, 15] = amplitudes[torch.randint(0, len(amplitudes), (n,), generator=generator)]
    obs[:, 16] = obs[:, 15]
    obs[:, 17] = torch.empty(n).uniform_(0.0, 1.0, generator=generator)
    targets = human_prior_action(obs)
    optimizer = torch.optim.Adam(
        list(model.encoder.parameters()) + list(model.actor.parameters()), lr=1e-3
    )
    batch = min(512, n)
    for _ in range(config.human_prior_updates):
        idx = torch.randint(0, n, (batch,), generator=generator)
        dist, _, _ = model.distribution_value(obs[idx])
        loss = (dist.mean - targets[idx]).pow(2).mean()
        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        optimizer.step()


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.set_num_threads(max(1, min(4, torch.get_num_threads())))


def train_ppo(
    method: str,
    seed: int,
    config: PPOConfig,
    progress_callback=None,
):
    if method not in {"traditional", "developmental"}:
        raise ValueError("method must be traditional or developmental")
    set_seed(seed)
    device = torch.device("cpu")
    model = ActorCritic(IdealStickmanEnv.observation_size, IdealStickmanEnv.action_size).to(device)

    if method == "traditional":
        schedule = [("independent_walk", config.total_updates)]
        body_coef = 0.0
        prior_coef = 0.0
    else:
        names = ["body_babbling", "balance", "weight_transfer", "supported_walk", "independent_walk"]
        base, extra = divmod(config.total_updates, len(names))
        schedule = [(name, base + (1 if i < extra else 0)) for i, name in enumerate(names)]
        body_coef = config.body_model_coef
        prior_coef = config.human_prior_coef

    if method == "developmental" and config.human_prior_updates > 0:
        pretrain_human_prior(model, config, seed)
    optimizer = torch.optim.Adam(model.parameters(), lr=config.learning_rate, eps=1e-5)

    env = IdealStickmanEnv(config.num_envs, schedule[0][0], seed=seed)
    obs = env.reset()
    curves = []
    total_steps = 0
    total_falls = 0
    global_update = 0

    for stage, stage_updates in schedule:
        obs = env.set_stage(stage)
        for _ in range(stage_updates):
            obs_buf = np.zeros((config.rollout_steps, config.num_envs, env.observation_size), np.float32)
            next_obs_buf = np.zeros_like(obs_buf)
            action_buf = np.zeros((config.rollout_steps, config.num_envs, env.action_size), np.float32)
            logp_buf = np.zeros((config.rollout_steps, config.num_envs), np.float32)
            reward_buf = np.zeros_like(logp_buf)
            done_buf = np.zeros_like(logp_buf)
            value_buf = np.zeros_like(logp_buf)

            for t in range(config.rollout_steps):
                obs_buf[t] = obs
                with torch.no_grad():
                    action_t, logp_t, value_t = model.act(torch.from_numpy(obs).to(device))
                action = action_t.cpu().numpy()
                next_obs, reward, done, info = env.step(action)
                action_buf[t] = action
                logp_buf[t] = logp_t.cpu().numpy()
                reward_buf[t] = reward
                done_buf[t] = done
                value_buf[t] = value_t.cpu().numpy()
                next_obs_buf[t] = next_obs
                total_falls += int(info["fallen"].sum())
                total_steps += config.num_envs
                obs = next_obs

            with torch.no_grad():
                _, _, next_value_t = model.act(torch.from_numpy(obs).to(device), deterministic=True)
            next_value = next_value_t.cpu().numpy()
            advantages = np.zeros_like(reward_buf)
            last_gae = np.zeros(config.num_envs, np.float32)
            for t in reversed(range(config.rollout_steps)):
                nonterminal = 1.0 - done_buf[t]
                delta = reward_buf[t] + config.gamma * next_value * nonterminal - value_buf[t]
                last_gae = delta + config.gamma * config.gae_lambda * nonterminal * last_gae
                advantages[t] = last_gae
                next_value = value_buf[t]
            returns = advantages + value_buf

            b_obs = torch.from_numpy(obs_buf.reshape(-1, env.observation_size)).to(device)
            b_next_obs = torch.from_numpy(next_obs_buf.reshape(-1, env.observation_size)).to(device)
            b_actions = torch.from_numpy(action_buf.reshape(-1, env.action_size)).to(device)
            b_logp = torch.from_numpy(logp_buf.ravel()).to(device)
            b_adv = torch.from_numpy(advantages.ravel()).to(device)
            b_returns = torch.from_numpy(returns.ravel()).to(device)
            b_adv = (b_adv - b_adv.mean()) / (b_adv.std() + 1e-8)
            batch_size = b_obs.shape[0]
            indices = np.arange(batch_size)

            losses = []
            for _epoch in range(config.update_epochs):
                np.random.shuffle(indices)
                for start in range(0, batch_size, config.minibatch_size):
                    mb = indices[start : start + config.minibatch_size]
                    dist, value, latent = model.distribution_value(b_obs[mb])
                    new_logp = dist.log_prob(b_actions[mb]).sum(-1)
                    ratio = (new_logp - b_logp[mb]).exp()
                    pg1 = -b_adv[mb] * ratio
                    pg2 = -b_adv[mb] * ratio.clamp(1.0 - config.clip_coef, 1.0 + config.clip_coef)
                    policy_loss = torch.max(pg1, pg2).mean()
                    value_loss = 0.5 * (value - b_returns[mb]).pow(2).mean()
                    entropy = dist.entropy().sum(-1).mean()
                    predicted_next = model.forward_model(torch.cat([latent, b_actions[mb]], dim=1))
                    body_loss = (predicted_next - b_next_obs[mb, : env.proprioceptive_size]).pow(2).mean()
                    prior_target = human_prior_action(b_obs[mb])
                    prior_loss = (dist.mean - prior_target).pow(2).mean()
                    loss = (
                        policy_loss
                        + config.value_coef * value_loss
                        - config.entropy_coef * entropy
                        + body_coef * body_loss
                        + prior_coef * prior_loss
                    )
                    optimizer.zero_grad(set_to_none=True)
                    loss.backward()
                    nn.utils.clip_grad_norm_(model.parameters(), config.max_grad_norm)
                    optimizer.step()
                    losses.append((loss.item(), body_loss.item()))

            global_update += 1
            mean_loss = float(np.mean([x[0] for x in losses]))
            mean_body_loss = float(np.mean([x[1] for x in losses]))
            point = {
                "method": method,
                "seed": seed,
                "update": global_update,
                "environment_steps": total_steps,
                "stage": stage,
                "training_falls": total_falls,
                "loss": mean_loss,
                "body_model_loss": mean_body_loss,
            }
            curves.append(point)
            if progress_callback:
                progress_callback(point, model)
    return model, curves
