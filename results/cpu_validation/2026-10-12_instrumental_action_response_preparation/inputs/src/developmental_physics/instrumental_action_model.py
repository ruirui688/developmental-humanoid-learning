"""Native-only, just-identified IV replacement of the coupled_hinge9 action heads.

No physical backend, hidden state, actual torque or future label enters a model
prediction. The original order is [v0,v1,qrel0,qrel1,G0,G1,h0,h1,1].
"""
from __future__ import annotations

import hashlib
import json

import numpy as np

DT = .002
DOSE = .125
RCOND = 128. * np.finfo(np.float64).eps
SIGNS = ((-1., -1.), (-1., 1.), (1., -1.), (1., 1.))
NONACTION = (0, 1, 2, 3, 8)


def count(cost, key, value=1):
    if cost is not None:
        cost[key] = cost.get(key, 0) + value


def finite(name, value, shape):
    result = np.asarray(value, dtype=np.float64)
    if result.shape != shape or not np.isfinite(result).all():
        raise ValueError(name + "_must_be_finite_" + str(shape))
    return result


def action_features(q, request, ranges, cost=None):
    """The original public start guard and signed hinge; never clip a request."""
    count(cost, "public_guard_projection_attempts")
    q, request = finite("native_q2", q, (2,)), finite("known_request2", request, (2,))
    ranges = finite("public_ranges2", ranges, (2, 2))
    if np.any(ranges[:, 0] >= ranges[:, 1]) or np.any(np.abs(request) > .5):
        raise ValueError("ordered_public_ranges_and_legal_request_required_no_clip")
    blocked = ((q <= ranges[:, 0]+.03) & (request < 0.)) | ((q >= ranges[:, 1]-.03) & (request > 0.))
    g = np.where(blocked, 0., request)
    with np.errstate(over="raise", invalid="raise"):
        h = np.sign(g)*np.maximum(np.abs(g)-.25, 0.)
        x = finite("action_features", np.concatenate((g, h)), (4,))
    count(cost, "public_guard_projection_returns")
    count(cost, "public_guard_input_scalar_uses", 8)
    count(cost, "signed_hinge_scalar_evaluations", 2)
    count(cost, "action_feature_scalar_outputs", 4)
    return x, blocked


def centered_instrument(q, base, dither, ranges, cost=None):
    base, dither = finite("known_base2", base, (2,)), finite("known_dither2", dither, (2,))
    if np.any(np.abs(base) > .375) or not np.all(np.isin(dither, (-DOSE, DOSE))):
        raise ValueError("fixed_inner_base_and_Rademacher_dose_required")
    count(cost, "instrument_pair_attempts")
    with np.errstate(over="raise", invalid="raise"):
        candidates = np.asarray([base+DOSE*np.asarray(sign) for sign in SIGNS])
        mapped = np.asarray([action_features(q, u, ranges, cost)[0] for u in candidates])
        mean = finite("conditional_public_mean", np.mean(mapped, axis=0), (4,))
        request = finite("known_final_request2", base+dither, (2,))
        x, blocked = action_features(q, request, ranges, cost)
        z = finite("centered_IV4", x-mean, (4,))
    count(cost, "conditional_mapping_candidates", 4)
    count(cost, "conditional_mapping_mean_scalar_outputs", 4)
    count(cost, "instrument_scalar_outputs", 4)
    count(cost, "instrument_pair_returns")
    return {"request2": request, "action4": x, "conditional_mean4": mean,
            "instrument4": z, "blocked2": blocked, "candidate_requests2": candidates}


class InstrumentalActionBodyModel:
    """Immutable coefficients, original two-head endpoint-Euler prediction."""
    def __init__(self, qref, ranges, theta):
        self.qref = finite("qref2", qref, (2,)).copy()
        self.ranges = finite("public_ranges2", ranges, (2, 2)).copy()
        self.theta = finite("coupled_hinge9_theta", theta, (2, 9)).copy()
        if np.any(self.ranges[:, 0] >= self.ranges[:, 1]):
            raise ValueError("ordered_public_ranges_required")
        for array in (self.qref, self.ranges, self.theta):
            array.flags.writeable = False

    def state_term(self, q, v, cost=None):
        q, v = finite("native_q2", q, (2,)), finite("native_v2", v, (2,))
        count(cost, "frozen_nonaction_matvec_attempts")
        with np.errstate(over="raise", invalid="raise"):
            features = finite("nonaction5", [*v, *(q-self.qref), 1.], (5,))
            result = finite("frozen_nonaction_v2", self.theta[:, NONACTION] @ features, (2,))
        count(cost, "frozen_nonaction_matvec_returns")
        count(cost, "frozen_nonaction_coefficient_scalar_uses", 10)
        return result

    def predict(self, q, v, request, cost=None):
        count(cost, "pair_prediction_attempts")
        count(cost, "scalar_velocity_head_attempts", 2)
        try:
            q, v = finite("native_q2", q, (2,)), finite("native_v2", v, (2,))
            x, _ = action_features(q, request, self.ranges, cost)
            with np.errstate(over="raise", invalid="raise"):
                phi = finite("coupled_hinge9_phi", [*v, *(q-self.qref), *x, 1.], (9,))
                next_v = finite("predicted_v2", self.theta @ phi, (2,))
                next_q = finite("predicted_q2", q+DT*next_v, (2,))
        except BaseException:
            count(cost, "pair_prediction_exceptions")
            raise
        count(cost, "pair_prediction_returns")
        count(cost, "scalar_velocity_head_returns", 2)
        count(cost, "prediction_coefficient_scalar_uses", 18)
        count(cost, "predicted_qv_scalar_outputs", 4)
        return next_q, next_v

    def record(self):
        return {"structure": "coupled_hinge9", "qref_rad": self.qref.tolist(), "dt_seconds": DT,
                "public_joint_ranges_rad": self.ranges.tolist(), "coefficients": self.theta.tolist(),
                "feature_order": ["v0", "v1", "qrel0", "qrel1", "G0", "G1", "h0", "h1", "1"],
                "integration": "endpoint_euler", "guard_margin_rad": .03, "request_limit_nm": .5,
                "hinge_threshold_nm": .25, "trainable": False, "physical_queries": 0}

    def parameter_fingerprint(self):
        return hashlib.sha256(json.dumps(self.record(), sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


class ActionIVMoments:
    """One continuous native stream; one joint two-head solve, without RLS."""
    def __init__(self, frozen_model, cost=None):
        self.model, self.cost = frozen_model, cost
        self.M, self.Y = np.zeros((4, 4)), np.zeros((4, 2))
        self.samples, self.fit_attempted, self.fit_record = 0, False, None

    def add(self, q, v, base, dither, next_v):
        if self.fit_attempted:
            raise ValueError("no_labels_after_first_fit_attempt")
        count(self.cost, "IV_moment_update_attempts")
        label = finite("new_native_next_v2", next_v, (2,))
        count(self.cost, "new_IV_scalar_label_uses", 2)
        instrument = centered_instrument(q, base, dither, self.model.ranges, self.cost)
        drift = self.model.state_term(q, v, self.cost)
        with np.errstate(over="raise", invalid="raise"):
            residual = finite("native_label_minus_frozen_state", label-drift, (2,))
            proposed_M = finite("proposed_IV_M", self.M+np.outer(instrument["instrument4"], instrument["action4"]), (4, 4))
            proposed_Y = finite("proposed_IV_Y", self.Y+np.outer(instrument["instrument4"], residual), (4, 2))
        self.M, self.Y = proposed_M, proposed_Y
        self.samples += 1
        count(self.cost, "IV_outer_products", 2)
        count(self.cost, "IV_moment_scalar_additions", 24)
        count(self.cost, "IV_moment_update_returns")
        return {**instrument, "frozen_state_v2": drift, "native_next_v2": label, "fit_residual_v2": residual}

    def fit_once(self):
        if self.fit_attempted:
            raise ValueError("IV_first_fit_only_no_retry")
        self.fit_attempted = True
        count(self.cost, "IV_fit_attempts")
        count(self.cost, "IV_lstsq_attempts")
        try:
            M, Y = finite("IV_M", self.M, (4, 4)), finite("IV_Y", self.Y, (4, 2))
            try:
                solution, residuals, rank, singular = np.linalg.lstsq(M, Y, rcond=RCOND)
            except BaseException:
                count(self.cost, "IV_lstsq_exceptions")
                raise
            count(self.cost, "IV_lstsq_returns")
            self.fit_record = {"solution_4x2": solution.tolist(), "rank": int(rank), "singular_values": singular.tolist(),
                "lstsq_residuals": residuals.tolist(), "rcond": RCOND, "samples": self.samples}
            solution = finite("IV_action_solution_4x2", solution, (4, 2))
            if rank != 4 or not np.isfinite(singular).all() or not np.isfinite(residuals).all():
                raise ValueError("IV_finite_full_rank4_required_no_rank_completion")
            theta = self.model.theta.copy()
            theta[:, 4:8] = solution.T
            if theta[:, NONACTION].tobytes() != self.model.theta[:, NONACTION].tobytes():
                raise ValueError("frozen_nonaction_coefficients_changed")
            corrected = InstrumentalActionBodyModel(self.model.qref, self.model.ranges, theta)
            count(self.cost, "IV_fitted_coefficient_scalar_outputs", 8)
            count(self.cost, "IV_fit_returns")
            return corrected
        except BaseException:
            count(self.cost, "IV_fit_exceptions")
            raise

    def record(self):
        return {"M_z_action_transpose": self.M.tolist(), "Y_z_native_residual_transpose": self.Y.tolist(),
                "samples": self.samples, "fit_attempted": self.fit_attempted, "fit": self.fit_record,
                "nonaction_columns_frozen": list(NONACTION), "action_columns_replaced": [4, 5, 6, 7]}
