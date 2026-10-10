"""A supported two-joint toy plant and a separate, immutable nominal model.

This spring/damper system is locally stable without control. It is neither a
humanoid nor a contact simulator. No state clipping or parameter fitting occurs.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json

import numpy as np


@dataclass(frozen=True)
class JointParameters:
    inertia: tuple[float, float] = (0.8, 1.0)
    damping: tuple[float, float] = (1.1, 1.25)
    stiffness: tuple[float, float] = (2.8, 3.2)
    actuator_gain: tuple[float, float] = (1.0, 1.0)
    coupling: float = 0.15
    delay_steps: int = 0

    def __post_init__(self):
        for name in ("inertia", "damping", "stiffness", "actuator_gain"):
            values = getattr(self, name)
            if not isinstance(values, tuple) or len(values) != 2:
                raise ValueError(f"{name} must be an immutable two-value tuple")
            if not np.isfinite(values).all() or min(values) <= 0:
                raise ValueError(f"{name} must be finite and positive")
        if not np.isfinite(self.coupling) or self.coupling < 0:
            raise ValueError("coupling must be finite and nonnegative")
        if type(self.delay_steps) is not int or self.delay_steps < 0:
            raise ValueError("delay_steps must be a nonnegative integer")


def _check_dt(dt: float) -> None:
    if not np.isfinite(dt) or dt <= 0:
        raise ValueError("dt must be finite and positive")


def advance(state, applied_torque, parameters: JointParameters, dt: float, external_torque=None):
    """Semi-implicit Euler integration; accepts a batch for model rollouts."""
    _check_dt(dt)
    state = np.asarray(state, dtype=np.float64)
    applied_torque = np.asarray(applied_torque, dtype=np.float64)
    if state.shape[-1:] != (4,) or applied_torque.shape[-1:] != (2,):
        raise ValueError("state must end in 4 and torque in 2 dimensions")
    if not np.isfinite(state).all() or not np.isfinite(applied_torque).all():
        raise ValueError("state and torque must be finite")
    disturbance = np.zeros(2) if external_torque is None else np.asarray(external_torque, dtype=float)
    if disturbance.shape != (2,) or not np.isfinite(disturbance).all():
        raise ValueError("external_torque must contain two finite values")
    q, velocity = state[..., :2], state[..., 2:]
    spring = np.asarray(parameters.stiffness) * q
    coupling = parameters.coupling * (q - q[..., ::-1])
    acceleration = (
        np.asarray(parameters.actuator_gain) * applied_torque + disturbance
        - np.asarray(parameters.damping) * velocity - spring - coupling
    ) / np.asarray(parameters.inertia)
    next_velocity = velocity + dt * acceleration
    next_q = q + dt * next_velocity
    return np.concatenate((next_q, next_velocity), axis=-1)


@dataclass(frozen=True)
class FixedBodyModel:
    parameters: JointParameters = JointParameters()
    dt: float = 0.02

    def __post_init__(self):
        _check_dt(self.dt)
        if self.parameters.delay_steps:
            raise ValueError("this initial nominal model assumes immediate actuation")

    def predict(self, state, action):
        return advance(state, action, self.parameters, self.dt)

    def fingerprint(self) -> str:
        payload = json.dumps(asdict(self), sort_keys=True).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()


class JointPlant:
    """Simulation fixture. Controllers receive observations, not this object."""

    def __init__(self, parameters: JointParameters, initial_state, dt: float = 0.02):
        _check_dt(dt)
        state = np.asarray(initial_state, dtype=np.float64)
        if state.shape != (4,) or not np.isfinite(state).all():
            raise ValueError("initial_state must contain four finite values")
        self.parameters = parameters
        self.dt = dt
        self._state = state.copy()
        self._pending = [np.zeros(2) for _ in range(parameters.delay_steps)]
        self.executed_steps = 0

    @property
    def observation(self):
        return self._state.copy()

    def step(self, command, external_torque=None):
        command = np.asarray(command, dtype=np.float64)
        if command.shape != (2,) or not np.isfinite(command).all():
            raise ValueError("command must contain two finite values")
        if self._pending:
            applied = self._pending.pop(0)
            self._pending.append(command.copy())
        else:
            applied = command
        self._state = advance(self._state, applied, self.parameters, self.dt, external_torque)
        self.executed_steps += 1
        return self.observation
