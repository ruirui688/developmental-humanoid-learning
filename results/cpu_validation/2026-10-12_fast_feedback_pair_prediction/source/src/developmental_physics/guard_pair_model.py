"""Causal control-start guard input basis, without physical validation.

Only current native pair q/v, known requests and public joint ranges enter
the body features. G(q, u) is a control-start projection, not the realized
average input over a 20 ms interval. This module never queries a simulator.
The original pair RLS and FixedPairMPC implementations remain unchanged.
No experiment protocol or scientific acceptance gate is defined here.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

import numpy as np

from developmental_physics.local_pair_model import (
    PairBodyModel, _pair, _parameter_state,
)
from developmental_physics.local_model import _scalar


INPUT_BASES = ("raw_request", "known_angle_guard")


def _public_pair_ranges(value):
    try:
        items = np.asarray(value, dtype=object)
    except (TypeError, ValueError) as exc:
        raise ValueError("public_joint_ranges must contain two ordered finite ranges") from exc
    if items.shape != (2, 2):
        raise ValueError("public_joint_ranges must contain two ordered finite ranges")
    ranges = tuple(
        tuple(_scalar(f"public_joint_ranges[{i}][{j}]", items[i, j]) for j in range(2))
        for i in range(2)
    )
    if any(lower >= upper for lower, upper in ranges):
        raise ValueError("public_joint_ranges must contain two ordered finite ranges")
    return ranges


@dataclass(frozen=True)
class GuardProjection:
    """Separate known request, clip and start-only projection diagnostics."""
    native_q_rad: tuple[float, float]
    requested_nm: tuple[float, float]
    clipped_request_nm: tuple[float, float]
    projected_start_nm: tuple[float, float]
    start_blocked: tuple[bool, bool]

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class KnownAngleGuard:
    """Immutable public two-axis execution rule at the control start.

    Equality at L + .03 or U - .03 blocks only an outward request. Native
    q is never clamped. Zero commands are never marked blocked. The rule
    provides no information about guard switching inside the next interval.
    """
    public_joint_ranges: tuple[tuple[float, float], tuple[float, float]]
    margin_rad: float = field(default=.03, init=False)
    torque_clip_nm: float = field(default=.5, init=False)

    def __post_init__(self):
        object.__setattr__(self, "public_joint_ranges", _public_pair_ranges(self.public_joint_ranges))

    def project(self, q, u):
        positions = _pair("q", q)
        requests = _pair("u", u)
        clipped = tuple(max(-self.torque_clip_nm, min(self.torque_clip_nm, x)) for x in requests)
        blocked = tuple(
            bool((positions[i] <= lower + self.margin_rad and clipped[i] < 0.)
                 or (positions[i] >= upper - self.margin_rad and clipped[i] > 0.))
            for i, (lower, upper) in enumerate(self.public_joint_ranges)
        )
        projected = tuple(0. if blocked[i] else clipped[i] for i in range(2))
        return GuardProjection(positions, requests, clipped, projected, blocked)

    def spec(self):
        return {
            "rule": "known_angle_guard_control_start_v1",
            "public_joint_ranges_rad": [list(row) for row in self.public_joint_ranges],
            "angle_margin_rad": self.margin_rad,
            "request_clip_per_axis_nm": self.torque_clip_nm,
            "outward_block_comparison": "q <= lower + margin or q >= upper - margin",
            "zero_is_blocked": False,
            "q_clipped": False,
            "evaluation_time": "current control-start q and already known request",
            "interval_semantics": "start-only projection; not realized 20 ms average input",
            "future_actual_input": False,
            "physical_queries": 0,
        }


class InputMappedDiagonalPairBodyModel(PairBodyModel):
    """Matching raw/guard diagonal models with unchanged atomic RLS core.

    Guard models replace u and h(u) by start_G(q,u) and h(start_G(q,u)).
    Raw models retain the original requested-input features, including their
    original lack of model-side clipping. Both disclose the shared public
    guard information, although raw models use it only for diagnostics.
    """
    def __init__(self, qref, *, public_joint_ranges, input_basis, dt=.02, trainable=True):
        if not isinstance(input_basis, str) or input_basis not in INPUT_BASES:
            raise ValueError("input_basis must be raw_request or known_angle_guard")
        self._guard = KnownAngleGuard(public_joint_ranges)
        self._input_basis = input_basis
        super().__init__(qref, structure="diagonal_hinge5", dt=dt, trainable=trainable)

    @property
    def input_basis(self):
        return self._input_basis

    @property
    def public_guard(self):
        return self._guard

    def describe_input(self, q, u):
        """Public diagnostics only; no actual-input argument is accepted."""
        projection = self.public_guard.project(q, u)
        command = (projection.requested_nm if self.input_basis == "raw_request"
                   else projection.projected_start_nm)
        return {**projection.to_dict(), "input_basis": self.input_basis,
                "model_feature_command_nm": command}

    def _features(self, q, v, u):
        if self.input_basis == "raw_request":
            return super()._features(q, v, u)
        projection = self.public_guard.project(q, u)
        return super()._features(projection.native_q_rad, v, projection.projected_start_nm)

    def _parameter_record(self, state=None):
        record = super()._parameter_record(state)
        if self.input_basis == "known_angle_guard":
            record["features_per_output"] = [
                [f"v{i}", f"q{i}-qref{i}", f"start_G{i}(q{i},u{i})",
                 f"h(start_G{i}(q{i},u{i}))", "1"] for i in range(2)
            ]
        record["input_mapping"] = {
            "basis": self.input_basis,
            "feature_command": ("original requested u without model-side clip"
                                if self.input_basis == "raw_request"
                                else "G(current q, original requested u) at control start"),
            "public_guard": self.public_guard.spec(),
            "guard_used_by_model": self.input_basis == "known_angle_guard",
            "recompute": "same causal mapping on every RLS and mathematical prediction call",
        }
        return record

    def clone_frozen(self):
        state = self._state
        clone = InputMappedDiagonalPairBodyModel(
            self.qref, public_joint_ranges=self.public_guard.public_joint_ranges,
            input_basis=self.input_basis, dt=self.dt, trainable=False,
        )
        clone._state = _parameter_state(
            state.theta.copy(), state.covariance.copy(), state.vector_update_count,
        )
        return clone
