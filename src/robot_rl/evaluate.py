"""Evaluation, rollout recording, and stickman visualization."""

from __future__ import annotations

import numpy as np
import torch

from .env import IdealStickmanEnv


@torch.no_grad()
def evaluate(model, seed: int, episodes: int = 20, horizon: int = 300):
    env = IdealStickmanEnv(episodes, "independent_walk", seed=seed, horizon=horizon)
    obs = env.reset()
    active = np.ones(episodes, dtype=bool)
    fell = np.zeros(episodes, dtype=bool)
    speeds = [[] for _ in range(episodes)]
    errors = [[] for _ in range(episodes)]
    distances = np.zeros(episodes, np.float32)
    for _ in range(horizon):
        action, _, _ = model.act(torch.from_numpy(obs), deterministic=True)
        obs, _, done, info = env.step(action.numpy())
        for i in range(episodes):
            if active[i]:
                speeds[i].append(float(info["speed"][i]))
                errors[i].append(float(info["tracking_mse"][i]))
                distances[i] = float(info["distance"][i])
                if done[i]:
                    fell[i] = bool(info["fallen"][i])
                    active[i] = False
        if not active.any():
            break
    mean_speed_per_ep = np.array([np.mean(x) if x else 0.0 for x in speeds])
    rmse_per_ep = np.sqrt(np.array([np.mean(x) if x else np.inf for x in errors]))
    success = (~fell) & (mean_speed_per_ep >= 0.70) & (rmse_per_ep <= 0.38)
    return {
        "success_rate": float(success.mean()),
        "fall_rate": float(fell.mean()),
        "mean_speed": float(mean_speed_per_ep.mean()),
        "joint_tracking_rmse": float(rmse_per_ep.mean()),
        "mean_distance": float(distances.mean()),
    }


@torch.no_grad()
def record_rollout(model, seed: int = 123, horizon: int = 300):
    env = IdealStickmanEnv(1, "independent_walk", seed=seed, horizon=horizon)
    obs = env.reset()
    frames = []
    for step in range(horizon):
        action, _, _ = model.act(torch.from_numpy(obs), deterministic=True)
        obs, _, done, info = env.step(action.numpy())
        if done[0]:
            terminal = info["terminal_observation"][0]
            q = terminal[:4]
            tilt = terminal[8]
            speed = terminal[10]
            x = info["distance"][0]
        else:
            q = env.q[0]
            tilt = env.tilt[0]
            speed = env.vx[0]
            x = env.x[0]
        frames.append(
            {
                "step": step + 1,
                "time": float((step + 1) * env.dt),
                "x": float(x),
                "speed": float(speed),
                "tilt": float(tilt),
                "q": np.asarray(q).copy().tolist(),
                "fallen": bool(info["fallen"][0]),
                "done": bool(done[0]),
            }
        )
        if done[0]:
            break
    return frames


def joint_points(frame):
    """Return head/torso/hip/knees/feet points for a display-only skeleton."""
    x, tilt = frame["x"], frame["tilt"]
    lh, lk, rh, rk = frame["q"]
    hip = np.array([x, 1.05])
    torso = hip + 0.55 * np.array([-np.sin(tilt), np.cos(tilt)])
    head = torso + 0.18 * np.array([-np.sin(tilt), np.cos(tilt)])

    def leg(hip_angle, knee_angle):
        knee = hip + 0.52 * np.array([np.sin(hip_angle), -np.cos(hip_angle)])
        lower_angle = hip_angle - knee_angle
        foot = knee + 0.50 * np.array([np.sin(lower_angle), -np.cos(lower_angle)])
        return knee, foot

    left_knee, left_foot = leg(lh, lk)
    right_knee, right_foot = leg(rh, rk)
    return head, torso, hip, left_knee, left_foot, right_knee, right_foot
