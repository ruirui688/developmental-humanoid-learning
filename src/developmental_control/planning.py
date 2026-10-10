"""Fixed, short-horizon candidate planning. Optimization here does not fit a model."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product

import numpy as np

from .joints import FixedBodyModel
from .maturation import ActionEnvelope, StagePermission


@dataclass(frozen=True)
class PlannerConfig:
    horizon_steps: int = 20
    candidates_per_joint: int = 7
    position_weight: float = 30.0
    velocity_weight: float = 0.2
    effort_weight: float = 0.025
    change_weight: float = 0.04
    position_limit: float = 0.30
    speed_limit: float = 1.15

    def __post_init__(self):
        if type(self.horizon_steps) is not int or self.horizon_steps < 1:
            raise ValueError("horizon_steps must be a positive integer")
        if (type(self.candidates_per_joint) is not int
                or self.candidates_per_joint < 3 or self.candidates_per_joint % 2 == 0):
            raise ValueError("candidate count must be odd and at least three")
        for name in ("position_weight", "velocity_weight", "effort_weight",
                     "change_weight", "position_limit", "speed_limit"):
            value = getattr(self, name)
            if not np.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and positive")


@dataclass(frozen=True)
class PlanResult:
    action: np.ndarray
    feasible_candidates: int
    fallback: bool


class CandidatePlanner:
    def __init__(self, model: FixedBodyModel, envelope: ActionEnvelope,
                 config: PlannerConfig = PlannerConfig()):
        self.model = model
        self.envelope = envelope
        self.config = config

    def plan(self, observation, target, permission: StagePermission, previous_action):
        obs = np.asarray(observation, dtype=np.float64)
        target = np.asarray(target, dtype=np.float64)
        previous = np.asarray(previous_action, dtype=np.float64)
        if obs.shape != (4,) or target.shape != (2,) or previous.shape != (2,):
            raise ValueError("expected a four-state observation and two-joint targets/actions")
        if not all(np.isfinite(x).all() for x in (obs, target, previous)):
            raise ValueError("planner inputs must be finite")
        # Validate the permission before building candidate ranges.
        self.envelope.apply(np.zeros(2), permission)
        ranges = [np.linspace(-limit, limit, self.config.candidates_per_joint)
                  if active else np.array([0.0])
                  for active, limit in zip(permission.active_joints, permission.torque_limits)]
        actions = np.asarray(list(product(*ranges)), dtype=np.float64)
        states = np.broadcast_to(obs, (len(actions), 4)).copy()
        costs = self.config.change_weight * np.sum((actions - previous) ** 2, axis=1)
        feasible = np.ones(len(actions), dtype=bool)
        for _ in range(self.config.horizon_steps):
            states = self.model.predict(states, actions)
            feasible &= ((np.max(np.abs(states[:, :2]), axis=1) <= self.config.position_limit)
                         & (np.max(np.abs(states[:, 2:]), axis=1) <= self.config.speed_limit))
            costs += (
                self.config.position_weight * np.sum((states[:, :2] - target) ** 2, axis=1)
                + self.config.velocity_weight * np.sum(states[:, 2:] ** 2, axis=1)
                + self.config.effort_weight * np.sum(actions ** 2, axis=1)
            )
        if not feasible.any():
            # Zero torque is only a fallback for this stable, supported fixture.
            # It is not a generally safe humanoid control action.
            return PlanResult(self.envelope.apply(np.zeros(2), permission), 0, True)
        index = int(np.argmin(np.where(feasible, costs, np.inf)))
        return PlanResult(self.envelope.apply(actions[index], permission), int(feasible.sum()), False)
