"""Fixed, single-joint torque probes using only encoders and public limits.

These probes collect action--sensation evidence; they do not identify a body
model, update a policy or optimize a task. Direction is selected once at the
paid prefix endpoint and remains fixed during the probe and recovery.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json

import numpy as np


JOINT_COUNT = 8
AMPLITUDES_NM = (0.125, 0.25, 0.5)
DIRECTION_RULE = "larger distance to the public joint limit; ties choose positive"


def _index(joint_index: int) -> None:
    if type(joint_index) is not int or not 0 <= joint_index < JOINT_COUNT:
        raise ValueError("joint_index must be an integer in [0, 8)")


def _ranges(joint_ranges: object) -> np.ndarray:
    try:
        ranges = np.asarray(joint_ranges, dtype=float)
    except (TypeError, ValueError) as error:
        raise ValueError("joint_ranges must be finite ordered [8, 2] limits") from error
    if (ranges.shape != (JOINT_COUNT, 2) or not np.isfinite(ranges).all()
            or np.any(ranges[:, 0] >= ranges[:, 1])):
        raise ValueError("joint_ranges must be finite ordered [8, 2] limits")
    return ranges


def direction_record(joint_index: int, joint_position: object,
                     joint_ranges: object) -> dict[str, object]:
    """Choose the roomier direction without contacts or hidden dynamics.

    Slightly out-of-range encoder readings still select a direction back
    toward the public range. This choice does not bypass the environment's
    torque and limit guards, and it is not a guarantee of collision safety.
    """
    _index(joint_index)
    ranges = _ranges(joint_ranges)
    try:
        position = np.asarray(joint_position, dtype=float)
    except (TypeError, ValueError) as error:
        raise ValueError("joint_position must contain 8 finite encoder values") from error
    if position.shape != (JOINT_COUNT,) or not np.isfinite(position).all():
        raise ValueError("joint_position must contain 8 finite encoder values")
    lower, upper = (float(value) for value in ranges[joint_index])
    current = float(position[joint_index])
    positive_room = upper - current
    negative_room = current - lower
    return {
        "joint_index": joint_index,
        "joint_position_rad": current,
        "lower_limit_rad": lower,
        "upper_limit_rad": upper,
        "positive_room_rad": positive_room,
        "negative_room_rad": negative_room,
        "direction": 1 if positive_room >= negative_room else -1,
        "rule": DIRECTION_RULE,
    }


@dataclass(frozen=True)
class ProbeConfig:
    """Immutable per-trial command specification; default duration is 4 s."""

    joint_index: int | None = None
    amplitude_nm: float = 0.5
    mode: str = "zero"
    prefix_steps: int = 100
    pulse_steps: int = 25
    recovery_steps: int = 75

    def __post_init__(self) -> None:
        if self.mode not in ("zero", "pulse"):
            raise ValueError("mode must be zero or pulse")
        if self.joint_index is not None:
            _index(self.joint_index)
        elif self.mode != "zero":
            raise ValueError("pulse mode requires a selected joint_index")
        if (isinstance(self.amplitude_nm, bool)
                or not isinstance(self.amplitude_nm, (int, float))
                or self.amplitude_nm not in AMPLITUDES_NM):
            raise ValueError("amplitude_nm must be one of 0.125, 0.25, 0.5")
        for name in ("prefix_steps", "pulse_steps", "recovery_steps"):
            value = getattr(self, name)
            minimum = 1 if name == "pulse_steps" else 0
            if type(value) is not int or value < minimum:
                raise ValueError(f"{name} must be an integer >= {minimum}")

    @property
    def total_steps(self) -> int:
        return self.prefix_steps + self.pulse_steps + self.recovery_steps


class FixedJointProbe:
    """One fixed pulse, with paid zero prefix and zero recovery.

    Pass joint ranges in actuator order as shared morphology information.
    A shared zero reference uses joint_index=None and never reads an encoder.
    A selected-joint zero reference records the same direction it would use
    for a pulse, permitting tests without duplicating collection trials.
    """

    def __init__(self, config: ProbeConfig, joint_ranges: object):
        if not isinstance(config, ProbeConfig):
            raise TypeError("config must be a ProbeConfig")
        self.config = config
        self._joint_ranges = tuple(tuple(float(v) for v in row)
                                   for row in _ranges(joint_ranges))
        self._selection: dict[str, object] | None = None

    def spec(self) -> dict[str, object]:
        """Return an independent, JSON-serializable fixed parameter record."""
        return {
            "config": asdict(self.config),
            "total_steps": self.config.total_steps,
            "joint_ranges_rad": [list(row) for row in self._joint_ranges],
            "joint_count": JOINT_COUNT,
            "direction_rule": DIRECTION_RULE,
            "direction_selection_step": self.config.prefix_steps,
            "direction_observation": "joint_position",
            "direction_updates_after_selection": 0,
            "model_updates": 0,
            "policy_updates": 0,
            "gate_updates": 0,
            "torque_unit": "N m",
        }

    def parameter_fingerprint(self) -> str:
        """Hash fixed parameters; one-time direction selection is action state."""
        encoded = json.dumps(self.spec(), sort_keys=True, separators=(",", ":"),
                             allow_nan=False).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    @property
    def selection_record(self) -> dict[str, object] | None:
        return None if self._selection is None else dict(self._selection)

    def phase(self, step_index: int) -> str:
        if type(step_index) is not int or not 0 <= step_index < self.config.total_steps:
            raise ValueError("step_index must be an integer within the trial")
        if step_index < self.config.prefix_steps:
            return "prefix"
        if step_index < self.config.prefix_steps + self.config.pulse_steps:
            return "probe"
        return "recovery"

    def action_index(self, step_index: int) -> int | None:
        return (step_index - self.config.prefix_steps
                if self.phase(step_index) == "probe" else None)

    def schedule(self, step_index: int) -> dict[str, object]:
        return {"phase": self.phase(step_index),
                "action_index": self.action_index(step_index)}

    def act(self, observation: dict[str, np.ndarray], step_index: int) -> np.ndarray:
        phase = self.phase(step_index)
        command = np.zeros(JOINT_COUNT)
        selected = self.config.joint_index
        if phase == "prefix" or selected is None:
            return command
        if self._selection is None:
            if step_index != self.config.prefix_steps:
                raise RuntimeError("direction must be selected at the paid prefix endpoint")
            self._selection = direction_record(selected, observation["joint_position"],
                                               self._joint_ranges)
            self._selection["selection_step"] = step_index
        if phase == "probe" and self.config.mode == "pulse":
            command[selected] = self._selection["direction"] * self.config.amplitude_nm
        return command
