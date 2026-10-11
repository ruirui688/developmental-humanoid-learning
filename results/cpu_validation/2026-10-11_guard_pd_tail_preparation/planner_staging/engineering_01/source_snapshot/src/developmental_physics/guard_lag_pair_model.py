"""Unpromoted NumPy-only causal 11-feature candidate, with explicit history.

This helper has no simulator, data loader, controller or mutable history.
previous_v must be the immediately preceding native velocity endpoint from
the same uninterrupted 20 ms sequence. A caller must have two real native
endpoints before use; unknown/reset history cannot be replaced by zeros.
For a mathematical rollout, each call receives the preceding predicted
endpoint and the caller advances previous_v to the old current v.
"""
from __future__ import annotations

import numpy as np

from developmental_physics.guard_pair_model import KnownAngleGuard
from developmental_physics.local_model import (
    FORGETTING_FACTOR, HINGE_THRESHOLD_NM, INITIAL_COVARIANCE, _digest, _scalar,
)
from developmental_physics.local_pair_model import (
    PairBodyModel, PairPredictionError, PairUpdateError, _pair, _parameter_state,
)


FEATURE_NAMES = (
    "v0", "v1", "q0-qref0", "q1-qref1",
    "start_G0(q0,u0)", "start_G1(q1,u1)",
    "h(start_G0(q0,u0))", "h(start_G1(q1,u1))", "1",
    "v0-previous_v0", "v1-previous_v1",
)


class GuardLagPairBodyModel:
    """Append two native velocity increments to the existing coupled9 basis.

    The first nine columns and their prior are unchanged. Both new columns
    start at zero in both heads. The old pure linear RLS proposal arithmetic
    is reused for the 11-dimensional arrays; PairBodyModel is not modified.
    """

    def __init__(self, qref, *, public_joint_ranges, dt=.02, trainable=True):
        if type(trainable) is not bool:
            raise ValueError("trainable must be boolean")
        self._qref = _pair("qref", qref)
        self._dt = _scalar("dt", dt)
        if self._dt != .02:
            raise ValueError("lag candidate fixes the complete interval at 20 ms")
        self._trainable = trainable
        self._guard = KnownAngleGuard(public_joint_ranges)
        theta = np.zeros((2, 11), dtype=np.float64)
        for index in range(2):
            theta[index, index] = 1.
            theta[index, 4+index] = .02
        self._initial_theta = theta.copy()
        self._initial_theta.setflags(write=False)
        covariance = np.repeat((INITIAL_COVARIANCE*np.eye(11))[None, :, :], 2, axis=0)
        self._state = _parameter_state(theta, covariance, 0)

    @property
    def qref(self):
        return self._qref

    @property
    def dt(self):
        return self._dt

    @property
    def trainable(self):
        return self._trainable

    @property
    def structure(self):
        return "guard_coupled_hinge9_velocity_increment11"

    @property
    def public_guard(self):
        return self._guard

    @property
    def update_count(self):
        return self._state.vector_update_count

    @property
    def scalar_update_count(self):
        return 2*self.update_count

    @property
    def coefficients(self):
        return self._state.theta.copy()

    @property
    def covariance(self):
        return self._state.covariance.copy()

    def _features(self, q, v, u, previous_v):
        projection = self.public_guard.project(q, u)
        positions = projection.native_q_rad
        velocities = _pair("v", v)
        previous = _pair("previous_v", previous_v)
        commands = projection.projected_start_nm
        with np.errstate(over="ignore", invalid="ignore"):
            displacements = np.asarray(positions)-np.asarray(self.qref)
            hinges = np.sign(commands)*np.maximum(np.abs(commands)-HINGE_THRESHOLD_NM, 0.)
            increments = np.asarray(velocities)-np.asarray(previous)
            row = np.asarray([*velocities, *displacements, *commands, *hinges,
                              1., *increments], dtype=np.float64)
            features = np.repeat(row[None, :], 2, axis=0)
        if not np.isfinite(features).all():
            raise ValueError("native pair and explicit history features must remain finite")
        return positions, features

    # These existing helpers use the supplied state/feature array shape and
    # have no history, simulator access, or fixed nine-column assumption.
    _predict_output = PairBodyModel._predict_output
    _propose_update = PairBodyModel._propose_update

    def predict(self, q, v, u, previous_v):
        """Pure endpoint-Euler prediction; previous_v is mandatory."""
        return self._predict_state(q, v, u, previous_v, self._state)

    def _predict_state(self, q, v, u, previous_v, state):
        try:
            positions, features = self._features(q, v, u, previous_v)
        except ValueError as exc:
            raise PairPredictionError(exc, 0, 0, "native_features") from exc
        attempts = successes = 0
        velocities = []
        for index in range(2):
            attempts += 1
            try:
                velocities.append(self._predict_output(index, features[index], state))
            except ValueError as exc:
                raise PairPredictionError(exc, attempts, successes, f"velocity_output_{index}") from exc
            successes += 1
        with np.errstate(over="ignore", invalid="ignore"):
            next_q = np.asarray(positions)+self.dt*np.asarray(velocities)
        if not np.isfinite(next_q).all():
            raise PairPredictionError(ValueError("pair position prediction overflowed"),
                                      attempts, successes, "endpoint_euler")
        return tuple(float(x) for x in next_q), tuple(velocities)

    def _parameter_record(self, state=None):
        state = self._state if state is None else state
        return {
            "structure": self.structure, "qref_rad": list(self.qref), "dt_seconds": self.dt,
            "features_per_output": [list(FEATURE_NAMES), list(FEATURE_NAMES)],
            "coefficients": state.theta.tolist(), "covariance": state.covariance.tolist(),
            "initial_coefficients": self._initial_theta.tolist(),
            "initial_covariance_scale": INITIAL_COVARIANCE, "forgetting_factor": FORGETTING_FACTOR,
            "hinge_threshold_nm": HINGE_THRESHOLD_NM, "hinge_threshold_updates": 0,
            "integration": "endpoint_euler", "dtype": "float64",
            "input_mapping": {"basis": "known_angle_guard", "public_guard": self.public_guard.spec(),
                              "feature_command": "G(current q, already known original requested u) at control start"},
            "history": {"stored_in_model": False, "argument": "previous_v",
                        "native_initialization": "two consecutive observed native velocity endpoints, 20 ms apart",
                        "unknown_or_reset_history": "must not call predict/update; never substitute zero",
                        "rollout_advance": "caller assigns old current v to previous_v after each predicted step"},
            "model_definition": {"parameter_count_per_output": 11, "base_columns": list(range(9)),
                                 "added_columns": [9, 10], "added_prior": "zero in both outputs",
                                 "prediction_arithmetic": "single ordinary float64 11-column dot per output",
                                 "rls_arithmetic_source": "unchanged PairBodyModel._propose_update",
                                 "physical_queries": 0},
        }

    def parameter_fingerprint(self):
        return _digest(self._parameter_record())

    def _snapshot_state(self, state):
        record = self._parameter_record(state)
        count = state.vector_update_count
        return {**record, "parameter_fingerprint": _digest(record), "trainable": self.trainable,
                "vector_update_count": count, "scalar_update_count": 2*count,
                "output_update_counts": [count, count],
                "update_commit": "single immutable state reference for both outputs, covariance and counts",
                "input_boundary": "native current/previous velocities, current q and already known u; no future actual torque"}

    def snapshot(self):
        return self._snapshot_state(self._state)

    def clone_frozen(self):
        state = self._state
        clone = GuardLagPairBodyModel(self.qref,
            public_joint_ranges=self.public_guard.public_joint_ranges, dt=self.dt, trainable=False)
        clone._state = _parameter_state(state.theta.copy(), state.covariance.copy(), state.vector_update_count)
        return clone

    def update(self, q, v, u, next_v, previous_v, *, transition_id):
        """One calibration transition, two scalar labels, one atomic publish.

        next_v enters only as the observed RLS label; it never enters features.
        A prefix collector must not call this method while building history.
        """
        if not self.trainable:
            raise RuntimeError("frozen lag pair evaluation model cannot update")
        if not isinstance(transition_id, str) or not transition_id:
            raise ValueError("nonempty explicit transition_id required")
        state = self._state
        positions, features = self._features(q, v, u, previous_v)
        labels = _pair("next_v", next_v)
        predicted_q, predicted_v = self._predict_state(positions, v, u, previous_v, state)
        before = _digest(self._parameter_record(state))
        proposals = []
        try:
            for index in range(2):
                proposals.append(self._propose_update(index, features[index], labels[index], predicted_v[index], state))
            theta = np.asarray([p["proposed_coefficients"] for p in proposals], dtype=np.float64)
            covariance = np.asarray([p["proposed_covariance"] for p in proposals], dtype=np.float64)
            if (theta.shape != (2, 11) or covariance.shape != (2, 11, 11)
                    or not np.isfinite(theta).all() or not np.isfinite(covariance).all()):
                raise ValueError("invalid 11-feature two-output proposal state")
            next_state = _parameter_state(theta, covariance, state.vector_update_count+1)
            record = {"shared_transition_id": transition_id, "updated": True,
                      "features_per_output": features.tolist(),
                      "preupdate_prediction": {"next_q_rad": list(predicted_q), "next_v_rad_s": list(predicted_v)},
                      "observed_next_v_rad_s": list(labels),
                      "output_records": [{**p, "committed": True} for p in proposals],
                      "vector_update_count": next_state.vector_update_count,
                      "scalar_update_count": 2*next_state.vector_update_count,
                      "committed_scalar_updates": 2,
                      "parameter_fingerprint_before": before,
                      "parameter_fingerprint_after": _digest(self._parameter_record(next_state))}
            self._state = next_state
            return record
        except BaseException as exc:
            actual_state = self._state
            committed = 2*(actual_state.vector_update_count-state.vector_update_count)
            ledger = PairUpdateError(exc,
                proposed_outputs=[{**p, "committed": committed == 2} for p in proposals],
                snapshot=self._snapshot_state(actual_state), committed_scalar_updates=committed)
            if isinstance(exc, (KeyboardInterrupt, SystemExit, OSError)):
                exc.pair_update_accounting = ledger.to_dict()
                raise
            raise ledger from exc
