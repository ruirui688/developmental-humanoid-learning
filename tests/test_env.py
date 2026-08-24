import numpy as np
import torch

from robot_rl.env import IdealStickmanEnv
from robot_rl.ppo import human_prior_action


def test_shapes_and_finite_values():
    env = IdealStickmanEnv(num_envs=4, seed=1)
    obs = env.reset()
    assert obs.shape == (4, 18)
    next_obs, reward, done, info = env.step(np.zeros((4, 4), np.float32))
    assert next_obs.shape == obs.shape
    assert reward.shape == done.shape == (4,)
    assert np.isfinite(next_obs).all()
    assert np.isfinite(reward).all()
    assert info["fallen"].shape == (4,)


def test_expert_survives_and_moves_in_ideal_environment():
    env = IdealStickmanEnv(num_envs=8, stage="independent_walk", seed=2)
    obs = env.reset()
    falls = 0
    speed = []
    for _ in range(250):
        obs, _, _, info = env.step(env.expert_action())
        falls += int(info["fallen"].sum())
        speed.append(info["speed"].mean())
    assert falls == 0
    assert np.mean(speed[-50:]) > 0.75


def test_developmental_stages_have_decreasing_support():
    env = IdealStickmanEnv(num_envs=1, stage="body_babbling")
    supports = []
    for stage in ["body_babbling", "balance", "weight_transfer", "supported_walk", "independent_walk"]:
        env.set_stage(stage)
        supports.append(env.cfg.external_support)
    assert supports == sorted(supports, reverse=True)


def test_human_prior_is_conditioned_and_finite():
    env = IdealStickmanEnv(num_envs=4, stage="supported_walk", seed=3)
    obs = torch.from_numpy(env.reset())
    action = human_prior_action(obs)
    assert action.shape == (4, 4)
    assert torch.isfinite(action).all()
    assert torch.all(action.abs() <= 1.0)
    env.set_stage("balance")
    balance_action = human_prior_action(torch.from_numpy(env._observation()))
    assert not torch.allclose(action, balance_action)
