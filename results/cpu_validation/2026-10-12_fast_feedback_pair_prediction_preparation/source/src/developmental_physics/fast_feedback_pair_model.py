"""Explicit 2 ms adaptation of an unlearned generic coupled-body prior."""
from __future__ import annotations

import numpy as np

from .guard_coupled_pair_model import GuardCoupledPairBodyModel
from .local_model import _scalar
from .local_pair_model import _parameter_state


REFERENCE_DT = .02
MICRO_DT = .002
TIME_SCALE = MICRO_DT / REFERENCE_DT


class FastFeedbackGuardCoupledPairBodyModel(GuardCoupledPairBodyModel):
    """Same atomic RLS, public input mapping and features; explicit new time prior."""
    def __init__(self, qref, *, public_joint_ranges, dt=MICRO_DT, trainable=True):
        if _scalar("dt", dt) != MICRO_DT:
            raise ValueError("Z_pair_model_fixes_complete_interval_at_2ms")
        super().__init__(qref, public_joint_ranges=public_joint_ranges,
                         dt=REFERENCE_DT, trainable=trainable)
        reference = self._state
        if reference.vector_update_count != 0:
            raise ValueError("Z_time_adapter_requires_unlearned_generic_prior")
        self._reference_initial_theta = reference.theta.copy()
        identity = np.zeros_like(reference.theta)
        for i in range(2):
            identity[i, i] = 1.
        initial = identity + TIME_SCALE * (reference.theta - identity)
        self._dt = MICRO_DT
        self._initial_theta = initial.copy()
        self._state = _parameter_state(initial.copy(), reference.covariance.copy(), 0)

    def _parameter_record(self, state=None):
        record = super()._parameter_record(state)
        record["model_definition"]["own_prior"] = "v continuity 1; known guarded torque .002; other own coefficients zero"
        record["time_adaptation"] = {
            "reference_constructor_dt_seconds": REFERENCE_DT,
            "active_dt_seconds": MICRO_DT,
            "velocity_increment_scale": TIME_SCALE,
            "rule": "E + .1 * (unlearned generic theta_20ms - E); E is own-axis velocity identity",
            "reference_initial_coefficients": self._reference_initial_theta.tolist(),
            "old_learned_snapshot_restoration": False,
            "forgetting_factor": 1.,
            "forgetting_physical_rate_rule": "lambda_micro = lambda_macro ** .1; 1 remains 1",
            "initial_covariance_scale": 100.,
            "more_correlated_micro_updates_change_prior_relative_weight": True,
        }
        return record

    def clone_frozen(self):
        state = self._state
        clone = FastFeedbackGuardCoupledPairBodyModel(
            self.qref, public_joint_ranges=self.public_guard.public_joint_ranges,
            dt=MICRO_DT, trainable=False)
        clone._state = _parameter_state(
            state.theta.copy(), state.covariance.copy(), state.vector_update_count)
        return clone
