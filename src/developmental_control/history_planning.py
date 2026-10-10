"""Fixed-delay candidate planning from issued command history.

The delay is a declared assumption, never read from the simulated plant. This
module performs no fitting or online parameter updates. Future commands are a
constant candidate, just as in the original planner; prior commands remain
unchanged even if the current permission has since decreased.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product

import numpy as np

from .joints import FixedBodyModel
from .maturation import ActionEnvelope, StagePermission
from .planning import CandidatePlanner, PlanResult, PlannerConfig


@dataclass(frozen=True)
class HistoryPlannerConfig:
    assumed_delay_steps: int = 0
    use_history: bool = True

    def __post_init__(self) -> None:
        if type(self.assumed_delay_steps) is not int or self.assumed_delay_steps < 0:
            raise ValueError("assumed_delay_steps must be a nonnegative integer")
        if type(self.use_history) is not bool:
            raise ValueError("use_history must be a boolean")

    @property
    def effective_delay_steps(self) -> int:
        return self.assumed_delay_steps if self.use_history else 0


def _finite_real_array(value, name: str) -> np.ndarray:
    array = np.asarray(value)
    if array.dtype.kind not in "fiu":
        raise ValueError(f"{name} must contain real numbers")
    array = array.astype(np.float64, copy=False)
    if not np.isfinite(array).all():
        raise ValueError(f"{name} must be finite")
    return array


def _command_history(value) -> np.ndarray:
    history = _finite_real_array(value, "command_history")
    if history.shape == (0,):
        return history.reshape(0, 2)
    if history.ndim != 2 or history.shape[1] != 2:
        raise ValueError("command_history must have shape (previous_steps, 2)")
    return history


class HistoryCandidatePlanner(CandidatePlanner):
    """Use a frozen delay assumption and the full prior issued-command history.

    At decision index ``t = len(command_history)``, rollout offset ``k`` uses
    command index ``t + k - effective_delay_steps``. Negative indices mean
    initial zero commands; indices before ``t`` use history; all later indices
    use the constant current candidate. The candidate command, rather than the
    delayed applied torque, retains the original effort and change penalties.
    """

    def __init__(self, model: FixedBodyModel, envelope: ActionEnvelope,
                 config: PlannerConfig = PlannerConfig(),
                 history_config: HistoryPlannerConfig = HistoryPlannerConfig()):
        if not isinstance(history_config, HistoryPlannerConfig):
            raise ValueError("history_config must be a HistoryPlannerConfig")
        super().__init__(model, envelope, config)
        self.history_config = history_config

    def assumed_applied_action(self, command, command_history) -> np.ndarray:
        """Return the nominal action for the next single-step prediction.

        The caller supplies only a newly issued command and prior commands.
        This helper cannot anticipate external disturbances or plant changes.
        A returned copy cannot mutate the caller's command history.
        """
        action = _finite_real_array(command, "command")
        if action.shape != (2,):
            raise ValueError("command must contain two values")
        history = _command_history(command_history)
        source = len(history) - self.history_config.effective_delay_steps
        if source < 0:
            return np.zeros(2, dtype=np.float64)
        if source < len(history):
            return history[source].copy()
        return action.copy()

    def plan(self, observation, target, permission: StagePermission,
             previous_action, command_history) -> PlanResult:
        obs = _finite_real_array(observation, "observation")
        target = _finite_real_array(target, "target")
        previous = _finite_real_array(previous_action, "previous_action")
        history = _command_history(command_history)
        if obs.shape != (4,) or target.shape != (2,) or previous.shape != (2,):
            raise ValueError("expected a four-state observation and two-joint targets/actions")
        self.envelope.apply(np.zeros(2), permission)
        ranges = [np.linspace(-limit, limit, self.config.candidates_per_joint)
                  if active else np.array([0.0])
                  for active, limit in zip(permission.active_joints, permission.torque_limits)]
        actions = np.asarray(list(product(*ranges)), dtype=np.float64)
        states = np.broadcast_to(obs, (len(actions), 4)).copy()
        costs = self.config.change_weight * np.sum((actions - previous) ** 2, axis=1)
        feasible = np.ones(len(actions), dtype=bool)
        decision_step = len(history)
        delay = self.history_config.effective_delay_steps
        for offset in range(self.config.horizon_steps):
            source = decision_step + offset - delay
            if source < 0:
                applied = np.zeros_like(actions)
            elif source < decision_step:
                # Existing commands are not re-clamped by today's permission.
                applied = np.broadcast_to(history[source], actions.shape)
            else:
                applied = actions
            states = self.model.predict(states, applied)
            feasible &= ((np.max(np.abs(states[:, :2]), axis=1) <= self.config.position_limit)
                         & (np.max(np.abs(states[:, 2:]), axis=1) <= self.config.speed_limit))
            costs += (
                self.config.position_weight * np.sum((states[:, :2] - target) ** 2, axis=1)
                + self.config.velocity_weight * np.sum(states[:, 2:] ** 2, axis=1)
                + self.config.effort_weight * np.sum(actions ** 2, axis=1)
            )
        if not feasible.any():
            # This supported fixture's zero-command fallback does not cancel
            # pending history commands and is not a humanoid safety guarantee.
            return PlanResult(self.envelope.apply(np.zeros(2), permission), 0, True)
        index = int(np.argmin(np.where(feasible, costs, np.inf)))
        return PlanResult(self.envelope.apply(actions[index], permission), int(feasible.sum()), False)
