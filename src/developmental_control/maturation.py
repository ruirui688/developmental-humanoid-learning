"""Auditable permission changes for a CPU-only control prototype.

The gate changes control permissions, never model or policy parameters.  This
software envelope is not an independent hardware safety controller.
"""

from __future__ import annotations

from dataclasses import dataclass
from numbers import Real

import numpy as np


def _finite_nonnegative(value: float, name: str) -> None:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real):
        raise ValueError(f"{name} must be a finite nonnegative real number")
    if not np.isfinite(value) or value < 0:
        raise ValueError(f"{name} must be a finite nonnegative real number")


def _validate_limits(limits: tuple[float, ...], name: str) -> None:
    if not isinstance(limits, tuple) or not limits:
        raise ValueError(f"{name} must be a nonempty tuple")
    for value in limits:
        _finite_nonnegative(value, name)


@dataclass(frozen=True)
class StagePermission:
    name: str
    active_joints: tuple[bool, ...]
    torque_limits: tuple[float, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("stage name must be a nonempty string")
        if not isinstance(self.active_joints, tuple) or not self.active_joints:
            raise ValueError("active_joints must be a nonempty tuple")
        if any(not isinstance(active, (bool, np.bool_)) for active in self.active_joints):
            raise ValueError("active_joints must contain only booleans")
        _validate_limits(self.torque_limits, "torque_limits")
        if len(self.active_joints) != len(self.torque_limits):
            raise ValueError("joint mask and torque limits must have equal dimensions")


@dataclass(frozen=True)
class GateEvidence:
    prediction_rmse: float
    tracking_rmse: float
    peak_speed: float
    model_error_bound: float
    safe: bool
    recovered: bool


@dataclass(frozen=True)
class GateConfig:
    max_prediction_rmse: float = 0.005
    max_tracking_rmse: float = 0.035
    max_peak_speed: float = 1.0
    max_model_error_bound: float = 0.02
    pass_windows: int = 3
    min_dwell_windows: int = 3

    def __post_init__(self) -> None:
        for name in (
            "max_prediction_rmse", "max_tracking_rmse", "max_peak_speed",
            "max_model_error_bound",
        ):
            _finite_nonnegative(getattr(self, name), name)
        for name in ("pass_windows", "min_dwell_windows"):
            value = getattr(self, name)
            if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, np.integer)) or value < 1:
                raise ValueError(f"{name} must be a positive integer")


class CompetenceGate:
    """Promote after repeated competence; withdraw permissions on bad evidence.

    Each ``observe`` call represents one nonoverlapping evidence window.  A
    transition resets both counters.  Normal unsuccessful windows reset only
    the consecutive-pass counter, so they still count toward minimum dwell.
    """

    def __init__(self, stages: tuple[StagePermission, ...], config: GateConfig):
        if not isinstance(stages, tuple) or not stages:
            raise ValueError("stages must be a nonempty tuple")
        if not isinstance(config, GateConfig):
            raise ValueError("config must be a GateConfig")
        if any(not isinstance(stage, StagePermission) for stage in stages):
            raise ValueError("all stages must be StagePermission instances")
        dimensions = len(stages[0].active_joints)
        for stage in stages:
            if len(stage.active_joints) != dimensions:
                raise ValueError("all stages must have equal joint dimensions")
        for previous, current in zip(stages, stages[1:]):
            if any(before and not after for before, after in zip(previous.active_joints, current.active_joints)):
                raise ValueError("later stages cannot deactivate joints")
            if any(after < before for before, after in zip(previous.torque_limits, current.torque_limits)):
                raise ValueError("later stages cannot reduce torque permissions")
        self.stages = stages
        self.config = config
        self.level = 0
        self.pass_count = 0
        self.dwell_windows = 0
        self.events: list[dict[str, object]] = []

    @property
    def permission(self) -> StagePermission:
        return self.stages[self.level]

    def observe(self, evidence: GateEvidence) -> str:
        if not isinstance(evidence, GateEvidence):
            raise ValueError("evidence must be GateEvidence")
        if not isinstance(evidence.safe, (bool, np.bool_)) or not isinstance(evidence.recovered, (bool, np.bool_)):
            raise ValueError("safe and recovered must be booleans")
        values = (
            evidence.prediction_rmse, evidence.tracking_rmse,
            evidence.peak_speed, evidence.model_error_bound,
        )
        if any(isinstance(value, (bool, np.bool_)) or not isinstance(value, Real) for value in values):
            raise ValueError("evidence measurements must be real numbers")

        previous_level = self.level
        self.dwell_windows += 1
        critical_reason = None
        if not all(np.isfinite(value) and value >= 0 for value in values):
            critical_reason = "invalid_measurement"
        elif not evidence.safe:
            critical_reason = "unsafe"
        elif evidence.prediction_rmse > self.config.max_prediction_rmse:
            critical_reason = "prediction_mismatch"
        elif evidence.model_error_bound > self.config.max_model_error_bound:
            critical_reason = "model_uncertainty"

        if critical_reason is not None:
            self.level = max(0, self.level - 1)
            self.pass_count = 0
            self.dwell_windows = 0
            decision = "retreat" if self.level < previous_level else "hold"
            reason = critical_reason
        else:
            competent = (
                evidence.tracking_rmse <= self.config.max_tracking_rmse
                and evidence.peak_speed <= self.config.max_peak_speed
                and evidence.recovered
            )
            self.pass_count = self.pass_count + 1 if competent else 0
            can_promote = (
                self.pass_count >= self.config.pass_windows
                and self.dwell_windows >= self.config.min_dwell_windows
                and self.level < len(self.stages) - 1
            )
            if can_promote:
                self.level += 1
                self.pass_count = 0
                self.dwell_windows = 0
                decision, reason = "promote", "competence_confirmed"
            else:
                decision = "hold"
                reason = "competence_pending" if competent else "competence_failed"
        self.events.append({
            "window": len(self.events) + 1,
            "level_before": previous_level,
            "level_after": self.level,
            "decision": decision,
            "reason": reason,
            "pass_count": self.pass_count,
            "dwell_windows": self.dwell_windows,
            "evidence": {
                "prediction_rmse": float(evidence.prediction_rmse) if np.isfinite(evidence.prediction_rmse) else None,
                "tracking_rmse": float(evidence.tracking_rmse) if np.isfinite(evidence.tracking_rmse) else None,
                "peak_speed": float(evidence.peak_speed) if np.isfinite(evidence.peak_speed) else None,
                "model_error_bound": float(evidence.model_error_bound) if np.isfinite(evidence.model_error_bound) else None,
                "safe": bool(evidence.safe),
                "recovered": bool(evidence.recovered),
            },
        })
        return decision


@dataclass(frozen=True)
class ActionEnvelope:
    """Clip a finite action vector to immutable per-joint permissions."""

    hard_torque_limits: tuple[float, ...]

    def __post_init__(self) -> None:
        _validate_limits(self.hard_torque_limits, "hard_torque_limits")

    def apply(self, action: np.ndarray, permission: StagePermission) -> np.ndarray:
        if not isinstance(permission, StagePermission):
            raise ValueError("permission must be StagePermission")
        hard = np.asarray(self.hard_torque_limits, dtype=float)
        permitted = np.asarray(permission.torque_limits, dtype=float)
        if permitted.shape != hard.shape:
            raise ValueError("permission and hard limits must have equal dimensions")
        if np.any(permitted > hard):
            raise ValueError("permission exceeds independent hard torque limits")
        action = np.asarray(action)
        if action.dtype.kind not in "fiu" or action.shape != hard.shape:
            raise ValueError("action must be a real vector with one value per joint")
        action = action.astype(float, copy=False)
        if not np.all(np.isfinite(action)):
            raise ValueError("action must be finite")
        clipped = np.clip(action, -np.minimum(permitted, hard), np.minimum(permitted, hard))
        return np.where(permission.active_joints, clipped, 0.0)
