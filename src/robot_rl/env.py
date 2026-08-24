"""Vectorized idealized planar stickman dynamics.

This is intentionally a small, transparent concept-validation environment.  It
is not a rigid-body simulator and must not be used to make Sim2Real claims.
"""

from __future__ import annotations

from dataclasses import dataclass
import numpy as np


@dataclass(frozen=True)
class StageConfig:
    name: str
    gait_amplitude: float
    target_speed: float
    external_support: float
    disturbance: float
    tracking_weight: float
    speed_weight: float
    balance_weight: float


STAGES = {
    "body_babbling": StageConfig("body_babbling", 0.35, 0.0, 1.0, 0.00, 2.5, 0.0, 0.5),
    "balance": StageConfig("balance", 0.0, 0.0, 0.55, 0.015, 1.0, 0.0, 2.5),
    "weight_transfer": StageConfig("weight_transfer", 0.65, 0.40, 0.35, 0.025, 2.0, 0.8, 1.5),
    "supported_walk": StageConfig("supported_walk", 1.0, 0.75, 0.18, 0.035, 1.8, 1.5, 1.2),
    "independent_walk": StageConfig("independent_walk", 1.0, 1.00, 0.0, 0.045, 1.5, 2.0, 1.5),
}


class IdealStickmanEnv:
    """Batched 2-D stickman with four actuated leg joints and torso balance.

    Observation (18): four joint angles, four joint velocities, torso angle,
    torso angular velocity, forward speed, gait clock sin/cos, and two idealized
    foot-contact indicators.  Action (4): normalized target positions for left
    hip/knee and right hip/knee.
    """

    observation_size = 18
    action_size = 4
    proprioceptive_size = 11

    def __init__(
        self,
        num_envs: int = 32,
        stage: str = "independent_walk",
        seed: int = 0,
        horizon: int = 300,
        dt: float = 0.04,
    ) -> None:
        if stage not in STAGES:
            raise ValueError(f"Unknown stage {stage!r}; choose from {tuple(STAGES)}")
        self.num_envs = num_envs
        self.cfg = STAGES[stage]
        self.horizon = horizon
        self.dt = dt
        self.rng = np.random.default_rng(seed)
        self.q = np.zeros((num_envs, 4), np.float32)
        self.qd = np.zeros_like(self.q)
        self.tilt = np.zeros(num_envs, np.float32)
        self.tilt_rate = np.zeros(num_envs, np.float32)
        self.x = np.zeros(num_envs, np.float32)
        self.vx = np.zeros(num_envs, np.float32)
        self.phase = np.zeros(num_envs, np.float32)
        self.steps = np.zeros(num_envs, np.int32)
        self.episode_return = np.zeros(num_envs, np.float32)
        self.episode_distance = np.zeros(num_envs, np.float32)
        self._last_action = np.zeros_like(self.q)
        self.reset()

    def set_stage(self, stage: str) -> np.ndarray:
        if stage not in STAGES:
            raise ValueError(stage)
        self.cfg = STAGES[stage]
        return self.reset()

    def reset(self, mask: np.ndarray | None = None) -> np.ndarray:
        if mask is None:
            mask = np.ones(self.num_envs, dtype=bool)
        n = int(mask.sum())
        if n:
            neutral = np.array([0.0, 0.12, 0.0, 0.12], np.float32)
            self.q[mask] = neutral + self.rng.normal(0.0, 0.025, (n, 4))
            self.qd[mask] = self.rng.normal(0.0, 0.015, (n, 4))
            self.tilt[mask] = self.rng.normal(0.0, 0.025, n)
            self.tilt_rate[mask] = self.rng.normal(0.0, 0.015, n)
            self.x[mask] = 0.0
            self.vx[mask] = 0.0
            self.phase[mask] = self.rng.uniform(-0.08, 0.08, n)
            self.steps[mask] = 0
            self.episode_return[mask] = 0.0
            self.episode_distance[mask] = 0.0
            self._last_action[mask] = 0.0
        return self._observation()

    def reference_joints(self) -> np.ndarray:
        amp = self.cfg.gait_amplitude
        left = np.sin(self.phase)
        right = np.sin(self.phase + np.pi)
        left_knee = 0.10 + 0.50 * np.maximum(left, 0.0)
        right_knee = 0.10 + 0.50 * np.maximum(right, 0.0)
        return amp * np.stack(
            [0.48 * left, left_knee, 0.48 * right, right_knee], axis=1
        ).astype(np.float32) + (1.0 - amp) * np.array([0.0, 0.10, 0.0, 0.10], np.float32)

    @staticmethod
    def action_to_targets(action: np.ndarray) -> np.ndarray:
        target = np.empty_like(action, dtype=np.float32)
        target[:, 0] = 0.70 * action[:, 0]
        target[:, 1] = 0.60 * (action[:, 1] + 1.0)
        target[:, 2] = 0.70 * action[:, 2]
        target[:, 3] = 0.60 * (action[:, 3] + 1.0)
        return target

    def expert_action(self) -> np.ndarray:
        """Reference gait plus a simple vestibular balance reflex."""
        ref = self.reference_joints()
        act = np.empty_like(ref)
        correction = 0.70 * self.tilt + 0.12 * self.tilt_rate
        act[:, 0] = (ref[:, 0] + correction) / 0.70
        act[:, 1] = ref[:, 1] / 0.60 - 1.0
        act[:, 2] = (ref[:, 2] + correction) / 0.70
        act[:, 3] = ref[:, 3] / 0.60 - 1.0
        return np.clip(act, -1.0, 1.0).astype(np.float32)

    def _observation(self) -> np.ndarray:
        left_contact = (np.sin(self.phase) <= 0.0).astype(np.float32)
        right_contact = 1.0 - left_contact
        return np.concatenate(
            [
                self.q,
                0.25 * self.qd,
                self.tilt[:, None],
                0.25 * self.tilt_rate[:, None],
                self.vx[:, None],
                np.sin(self.phase)[:, None],
                np.cos(self.phase)[:, None],
                left_contact[:, None],
                right_contact[:, None],
                np.full((self.num_envs, 1), self.cfg.gait_amplitude, np.float32),
                np.full((self.num_envs, 1), self.cfg.target_speed, np.float32),
                np.full((self.num_envs, 1), self.cfg.external_support, np.float32),
            ],
            axis=1,
        ).astype(np.float32)

    def step(self, action: np.ndarray):
        action = np.asarray(action, dtype=np.float32)
        if action.shape != (self.num_envs, self.action_size):
            raise ValueError(f"Expected {(self.num_envs, self.action_size)}, got {action.shape}")
        action = np.clip(action, -1.0, 1.0)
        target = self.action_to_targets(action)
        ref = self.reference_joints()

        qdd = 28.0 * (target - self.q) - 5.5 * self.qd
        qdd = np.clip(qdd, -35.0, 35.0)
        self.qd += self.dt * qdd
        self.q += self.dt * self.qd
        self.q[:, (1, 3)] = np.clip(self.q[:, (1, 3)], 0.0, 1.25)
        self.q[:, (0, 2)] = np.clip(self.q[:, (0, 2)], -0.85, 0.85)

        support = self.cfg.external_support
        hip_common = 0.5 * (target[:, 0] + target[:, 2])
        gait_coupling = 0.20 * (self.q[:, 0] + self.q[:, 2])
        noise = self.rng.normal(0.0, self.cfg.disturbance, self.num_envs)
        tilt_acc = (
            (5.8 - 10.0 * support) * self.tilt
            - (2.5 + 3.0 * support) * self.tilt_rate
            - 8.0 * hip_common
            + gait_coupling
            + noise
        )
        self.tilt_rate += self.dt * tilt_acc
        self.tilt += self.dt * self.tilt_rate

        track_mse = np.mean((self.q - ref) ** 2, axis=1)
        # Servo lag means even the reference controller has a small phase error;
        # the propulsion proxy should reward coordinated gait without making the
        # nominal 1 m/s target physically unreachable.
        gait_quality = np.exp(-2.0 * track_mse)
        upright_quality = np.exp(-5.0 * self.tilt**2)
        desired_v = self.cfg.target_speed * gait_quality * upright_quality
        self.vx += self.dt * 3.2 * (desired_v - self.vx)
        self.x += self.dt * self.vx
        self.episode_distance += self.dt * self.vx

        speed_score = np.exp(-3.0 * (self.vx - self.cfg.target_speed) ** 2)
        tracking_score = np.exp(-6.0 * track_mse)
        balance_score = np.exp(-7.0 * self.tilt**2 - 0.12 * self.tilt_rate**2)
        energy = np.mean((action - self._last_action) ** 2, axis=1)
        pre_failure = np.maximum(np.abs(self.tilt) - 0.32, 0.0) ** 2
        reward = (
            self.cfg.tracking_weight * tracking_score
            + self.cfg.speed_weight * speed_score
            + self.cfg.balance_weight * balance_score
            + 0.15
            - 0.025 * energy
            - 4.0 * pre_failure
        ).astype(np.float32)
        self._last_action = action.copy()
        self.phase = (self.phase + self.dt * 2.0 * np.pi * 1.15 + np.pi) % (2.0 * np.pi) - np.pi
        self.steps += 1
        self.episode_return += reward

        fallen = (np.abs(self.tilt) > 0.62) | (np.mean(self.q[:, (1, 3)], axis=1) > 1.05)
        timeout = self.steps >= self.horizon
        done = fallen | timeout
        info = {
            "fallen": fallen.copy(),
            "timeout": timeout.copy(),
            "tracking_mse": track_mse.astype(np.float32),
            "speed": self.vx.copy(),
            "distance": self.episode_distance.copy(),
            "episode_return": self.episode_return.copy(),
        }
        obs = self._observation()
        if done.any():
            terminal_obs = obs.copy()
            self.reset(done)
            obs = self._observation()
            info["terminal_observation"] = terminal_obs
        return obs, reward, done.astype(np.float32), info
