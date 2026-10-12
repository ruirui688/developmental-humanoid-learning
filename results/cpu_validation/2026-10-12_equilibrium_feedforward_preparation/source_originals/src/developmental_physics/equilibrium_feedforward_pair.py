"""Frozen native-model equilibrium feedforward and one H150 forecast.

No physics, fitting, file I/O or experiment execution occurs in this module.
The inverse uses the complete public guard/hinge map in sixteen bounded boxes.
The actor must use equilibrium_feedback_request: feedforward precedes the one
final request clip. A clipped public-PD request plus feedforward is different.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, replace
from itertools import product

import numpy as np

from .fast_feedback_pair_mpc import ResidualPDMPCDecision
from .guard_coupled_pair_model import GuardCoupledPairBodyModel
from .guard_pair_model import KnownAngleGuard
from .local_model import HINGE_THRESHOLD_NM, MPCConfig
from .local_pair_model import FixedPairMPC, PairCandidateRecord, PairPredictionError, _pair


ROOT_EPS_MULTIPLIER = 128.
ROOT_EPS = ROOT_EPS_MULTIPLIER * np.finfo(np.float64).eps
ROOT_AXIS_BOXES = ((-.5, -.25), (-.25, 0.), (0., .25), (.25, .5))
ROOT_ACCOUNTING_KEYS = (
    "root_cache_hits", "root_cache_misses", "root_solve_attempts", "root_solve_returns",
    "root_solve_failures", "root_coefficient_validations", "branch_affine_build_attempts",
    "branch_affine_build_returns", "branch_svd_attempts", "branch_svd_returns",
    "branch_rank0", "branch_rank1", "branch_rank2", "branch_minimum_norm_attempts",
    "branch_minimum_norm_returns", "branch_box_candidate_checks",
    "branch_linear_residual_checks", "branch_guard_residual_checks",
    "root_guard_projection_attempts", "root_guard_projection_returns",
    "root_algebraic_pair_evaluations", "root_algebraic_scalar_evaluations",
    "root_model_pair_prediction_attempts", "root_model_pair_prediction_returns",
    "root_model_pair_prediction_failures", "root_model_scalar_prediction_attempts",
    "root_model_scalar_prediction_returns", "root_model_scalar_prediction_failures",
    "root_model_unknown_scalar_failure_count", "root_feasible_branch_roots",
    "root_selected_returns", "root_no_root_returns",
)
FORECAST_ACCOUNTING_KEYS = (
    "pair_prediction_attempts", "pair_prediction_returns", "pair_prediction_failures",
    "scalar_prediction_attempts", "scalar_prediction_returns", "scalar_prediction_failures",
    "unknown_scalar_failure_count", "pd_request_attempts", "pd_request_returns",
    "forecast_steps_accepted",
)


def _finite(name, value, shape=None):
    array = np.asarray(value, dtype=np.float64)
    if (shape is not None and array.shape != shape) or not np.isfinite(array).all():
        raise ValueError(f"{name}_must_have_finite_shape_{shape}")
    return array


def _tolerance(terms):
    with np.errstate(over="ignore", invalid="ignore"):
        scale = float(np.sum(np.abs(_finite("residual_terms", terms))))
    if not np.isfinite(scale):
        raise ValueError("nonfinite_root_residual_scale")
    return ROOT_EPS * max(1., scale)


def equilibrium_feedback_request(q, v, target_q, u_hold):
    """Raw PD64/Kd4 plus fixed hold request, followed by one final clip."""
    position, velocity, target, hold = (
        _pair(name, value) for name, value in (
            ("q", q), ("v", v), ("target_q", target_q), ("u_hold", u_hold)))
    if any(abs(value) > .5 for value in hold):
        raise ValueError("equilibrium_hold_exceeds_shared_permission")
    with np.errstate(over="ignore", invalid="ignore"):
        raw = 64.*(np.asarray(target)-position)-4.*np.asarray(velocity)+hold
    _finite("raw_equilibrium_feedback_request", raw, (2,))
    return tuple(float(value) for value in np.clip(raw, -.5, .5))


@dataclass(frozen=True)
class EquilibriumBranchRecord:
    index: int
    axis_branch_indices: tuple[int, int]
    bounds_nm: tuple[tuple[float, float], tuple[float, float]]
    rank: int
    affine_matrix: tuple[tuple[float, float], tuple[float, float]]
    affine_offset: tuple[float, float]
    request_nm: tuple[float, float] | None
    status: str
    algebraic_velocity_residual_rad_s: tuple[float, float] | None
    model_velocity_residual_rad_s: tuple[float, float] | None
    tolerance_rad_s: float | None


@dataclass(frozen=True)
class EquilibriumRootResult:
    target_q: tuple[float, float]
    request_nm: tuple[float, float] | None
    has_root: bool
    selected_branch_index: int | None
    status: str
    records: tuple[EquilibriumBranchRecord, ...]
    accounting: dict

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class EquilibriumFeedforwardDecision(ResidualPDMPCDecision):
    root_result: EquilibriumRootResult | None = None
    root_cache_hit: bool = False
    root_accounting: dict | None = None
    forecast_accounting: dict | None = None


def _closest_zero(lower, upper):
    # This chooses the rank-zero box minimizer; it never clips a solved root.
    return lower if lower > 0. else upper if upper < 0. else 0.


def _box_minimum_norm(matrix, offset, bounds, left, singular, right, rank, count):
    """Rank2 point, rank1 line/box intersection, or rank0 whole-box minimizer."""
    count["branch_minimum_norm_attempts"] += 1
    candidates = []
    if rank == 2:
        with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
            candidates.append(_finite("rank2_root", np.linalg.solve(matrix, -offset), (2,)))
    elif rank == 1:
        row = right[0]
        with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
            rhs = float(-(left[:, 0] @ offset) / singular[0])
        if not np.isfinite(rhs):
            raise ValueError("nonfinite_rank1_line")
        candidates.append(_finite("rank1_unbounded_minimum", row*rhs, (2,)))
        for axis in range(2):
            other = 1-axis
            for bound in bounds[axis]:
                numerator = float(rhs-row[axis]*bound)
                if not np.isfinite(numerator):
                    raise ValueError("nonfinite_rank1_edge_numerator")
                if row[other] == 0.:
                    if abs(numerator) > _tolerance((rhs, row[axis]*bound)):
                        continue
                    coordinate = _closest_zero(*bounds[other])
                else:
                    interval = tuple(row[other]*value for value in bounds[other])
                    if not min(interval) <= numerator <= max(interval):
                        continue
                    coordinate = float(numerator/row[other])
                point = np.zeros(2)
                point[axis], point[other] = bound, coordinate
                candidates.append(_finite("rank1_edge_root", point, (2,)))
    else:
        candidates.append(np.asarray([_closest_zero(*box) for box in bounds]))
    feasible = []
    for point in candidates:
        count["branch_box_candidate_checks"] += 1
        if any(not lower <= point[axis] <= upper for axis, (lower, upper) in enumerate(bounds)):
            continue
        count["branch_linear_residual_checks"] += 1
        with np.errstate(over="ignore", invalid="ignore"):
            residual = _finite("branch_linear_residual", matrix @ point+offset, (2,))
            tolerance = _tolerance(np.concatenate(((matrix*point).ravel(), offset)))
        if np.max(np.abs(residual)) <= tolerance:
            values = tuple(float(value) for value in point)
            feasible.append((sum(value*value for value in values), *values))
    count["branch_minimum_norm_returns"] += 1
    return None if not feasible else tuple(min(feasible)[1:])


def _prediction_failure_counts(exc):
    if isinstance(exc, PairPredictionError):
        return exc.scalar_prediction_attempts, exc.scalar_prediction_successes, 0
    attached = getattr(exc, "pair_prediction_accounting", None)
    if attached is not None:
        return attached["scalar_prediction_attempts"], attached["scalar_prediction_successes"], 0
    return 0, 0, 1


def solve_equilibrium_root(coefficients, qref, public_joint_ranges, target_q, *, predictor=None):
    """Find the global minimum-norm verified root over sixteen exact G/h boxes.

    predictor, when supplied, is called at most once per feasible branch at
    (current target, zero velocity, bounded root). It adds no future actual data.
    Numeric failures raise with partial counters/records; finite absence of a
    verified bounded root is returned explicitly, never repaired by clipping.
    """
    count = Counter({key: 0 for key in ROOT_ACCOUNTING_KEYS})
    records, feasible = [], []
    count["root_solve_attempts"] += 1
    try:
        theta = _finite("coupled_hinge9_coefficients", coefficients, (2, 9))
        count["root_coefficient_validations"] += 1
        reference, target = _pair("qref", qref), _pair("target_q", target_q)
        guard = KnownAngleGuard(public_joint_ranges)
        if HINGE_THRESHOLD_NM != .25:
            raise ValueError("equilibrium_inverse_requires_frozen_hinge_quarter_Nm")
        with np.errstate(over="ignore", invalid="ignore"):
            displacement = _finite("target_displacement", np.asarray(target)-reference, (2,))
            base_offset = _finite("base_equilibrium_offset", theta[:, 2:4] @ displacement+theta[:, 8], (2,))
        for index, axes in enumerate(product(range(4), repeat=2)):
            bounds = tuple(ROOT_AXIS_BOXES[axis] for axis in axes)
            count["branch_affine_build_attempts"] += 1
            matrix, offset = np.zeros((2, 2)), base_offset.copy()
            with np.errstate(over="ignore", invalid="ignore"):
                for axis, branch in enumerate(axes):
                    representative = sum(bounds[axis])*.5
                    lower, upper = guard.public_joint_ranges[axis]
                    blocked = ((target[axis] <= lower+guard.margin_rad and representative < 0.)
                               or (target[axis] >= upper-guard.margin_rad and representative > 0.))
                    if blocked:
                        continue
                    matrix[:, axis] = theta[:, 4+axis]
                    if branch in (0, 3):
                        matrix[:, axis] += theta[:, 6+axis]
                        offset += theta[:, 6+axis] * (.25 if branch == 0 else -.25)
            _finite("branch_affine_matrix", matrix, (2, 2))
            _finite("branch_affine_offset", offset, (2,))
            count["branch_affine_build_returns"] += 1
            count["branch_svd_attempts"] += 1
            left, singular, right = np.linalg.svd(matrix, full_matrices=True)
            _finite("branch_singular_values", singular, (2,))
            _finite("branch_left_vectors", left, (2, 2))
            _finite("branch_right_vectors", right, (2, 2))
            count["branch_svd_returns"] += 1
            rank = int(np.count_nonzero(singular > ROOT_EPS*singular[0])) if singular[0] > 0. else 0
            count[f"branch_rank{rank}"] += 1
            root = _box_minimum_norm(matrix, offset, bounds, left, singular, right, rank, count)
            status, algebraic, model_residual, tolerance = "no_bounded_linear_root", None, None, None
            if root is not None:
                count["branch_guard_residual_checks"] += 1
                count["root_guard_projection_attempts"] += 1
                projected = guard.project(target, root).projected_start_nm
                count["root_guard_projection_returns"] += 1
                with np.errstate(over="ignore", invalid="ignore"):
                    hinge = np.sign(projected)*np.maximum(np.abs(projected)-.25, 0.)
                    features = _finite("complete_equilibrium_features", [0., 0., *displacement, *projected, *hinge, 1.], (9,))
                    count["root_algebraic_pair_evaluations"] += 1
                    algebraic_values = []
                    for head in range(2):
                        count["root_algebraic_scalar_evaluations"] += 1
                        algebraic_values.append(float(theta[head] @ features))
                    algebraic = tuple(float(value) for value in _finite("complete_equilibrium_velocity", algebraic_values, (2,)))
                    tolerance = _tolerance(theta*features)
                status = "full_guard_residual_rejected"
                if max(abs(value) for value in algebraic) <= tolerance:
                    status = "verified_root"
                    if predictor is not None:
                        count["root_model_pair_prediction_attempts"] += 1
                        try:
                            next_q, next_v = predictor(target, (0., 0.), root)
                        except BaseException as exc:
                            attempts, returns, unknown = _prediction_failure_counts(exc)
                            count["root_model_pair_prediction_failures"] += 1
                            count["root_model_scalar_prediction_attempts"] += attempts
                            count["root_model_scalar_prediction_returns"] += returns
                            count["root_model_scalar_prediction_failures"] += attempts-returns
                            count["root_model_unknown_scalar_failure_count"] += unknown
                            raise
                        count["root_model_pair_prediction_returns"] += 1
                        count["root_model_scalar_prediction_attempts"] += 2
                        count["root_model_scalar_prediction_returns"] += 2
                        _pair("equilibrium_model_next_q", next_q)
                        model_residual = _pair("equilibrium_model_next_v", next_v)
                        if max(abs(value) for value in model_residual) > tolerance:
                            status = "model_residual_rejected"
                    if status == "verified_root":
                        count["root_feasible_branch_roots"] += 1
                        feasible.append((sum(value*value for value in root), *root, index))
            records.append(EquilibriumBranchRecord(
                index, axes, bounds, rank,
                tuple(tuple(float(value) for value in row) for row in matrix),
                tuple(float(value) for value in offset), root, status, algebraic, model_residual, tolerance))
        selected = min(feasible) if feasible else None
        count["root_selected_returns" if selected is not None else "root_no_root_returns"] += 1
        count["root_solve_returns"] += 1
        return EquilibriumRootResult(target, None if selected is None else tuple(selected[1:3]),
                                     selected is not None, None if selected is None else selected[3],
                                     "verified_root" if selected is not None else "no_equilibrium_root",
                                     tuple(records), dict(count))
    except BaseException as exc:
        count["root_solve_failures"] += 1
        exc.equilibrium_root_accounting = dict(count)
        exc.equilibrium_root_records = tuple(records)
        raise


class EquilibriumFeedforwardPairMPC(FixedPairMPC):
    """One direct hold-request proposal, original H150 veto and zero fallback."""
    def __init__(self, model, joint_ranges, config=None):
        if not isinstance(model, GuardCoupledPairBodyModel):
            raise TypeError("frozen_guard_coupled_pair_model_required")
        if model.trainable or model.dt != .002 or model.structure != "coupled_hinge9":
            raise ValueError("frozen_2ms_coupled_hinge9_required")
        baseline = MPCConfig()
        micro = replace(baseline, horizon=150, position_weight=.1*baseline.position_weight,
                        velocity_weight=.1*baseline.velocity_weight, effort_weight=.1*baseline.effort_weight)
        if config is not None and config != micro:
            raise ValueError("original_micro_forecast_configuration_required")
        limits = _finite("public_joint_ranges", joint_ranges, (2, 2))
        if np.any(limits[:, 0] >= limits[:, 1]):
            raise ValueError("ordered_public_joint_ranges_required")
        self.model, self.config = model, micro
        self.joint_ranges = tuple(tuple(float(value) for value in row) for row in limits)
        if self.joint_ranges != model.public_guard.public_joint_ranges:
            raise ValueError("model_and_controller_public_guard_ranges_must_match")
        self.forecast_bounds = tuple((max(model.qref[i]-micro.local_position_radius_rad, limits[i, 0]-micro.prediction_limit_tolerance_rad),
                                      min(model.qref[i]+micro.local_position_radius_rad, limits[i, 1]+micro.prediction_limit_tolerance_rad)) for i in range(2))
        self.target_bounds = tuple((max(model.qref[i]-micro.local_position_radius_rad, limits[i, 0]+micro.target_limit_margin_rad),
                                    min(model.qref[i]+micro.local_position_radius_rad, limits[i, 1]-micro.target_limit_margin_rad)) for i in range(2))
        self._captured_state = model._state
        self.initialization_accounting = {"coefficient_read_attempts": 1, "coefficient_read_returns": 0,
                                          "coefficient_scalars_copied": 0, "parameter_state_identity_captures": 1}
        try:
            coefficients = model.coefficients
            self.initialization_accounting["coefficient_read_returns"] = 1
            self._theta = _finite("frozen_equilibrium_coefficients", coefficients, (2, 9)).copy()
            self._theta.setflags(write=False)
            self.initialization_accounting["coefficient_scalars_copied"] = 18
        except BaseException as exc:
            exc.equilibrium_initialization_accounting = dict(self.initialization_accounting)
            raise
        self._cached_target, self._cached_root = None, None

    def spec(self):
        return {"controller": "EquilibriumFeedforwardPairMPC", "config_per_axis": asdict(self.config),
                "qref_rad": list(self.model.qref), "joint_ranges_rad": [list(row) for row in self.joint_ranges],
                "forecast_bounds_rad": [list(row) for row in self.forecast_bounds],
                "target_bounds_rad": [list(row) for row in self.target_bounds],
                "equilibrium_axis_boxes_nm": [list(box) for box in ROOT_AXIS_BOXES],
                "equilibrium_branch_count": 16, "hinge_threshold_nm": .25,
                "root_rank_rule": "s > 128*float64_eps*smax; zero matrix rank zero",
                "root_residual_rule": "128*float64_eps*max(1,sum(abs(contributing products)))",
                "root_box_rule": "strict closed bounds; solved roots never clipped",
                "root_selection": "minimum squared Euclidean norm, signed u0, signed u1, branch index",
                "finite_no_root": "hold request zero; still forecast the one PD trajectory",
                "root_cache": "only latest current target under identical frozen parameter state",
                "shared_pd": {"kp": [64., 64.], "kd": [4., 4.], "gain_updates": 0},
                "action_rollout": "raw PD plus current-target hold request; one final clip; H150 single trajectory",
                "execution": "native-feedback equilibrium_feedback_request each 2ms; selected hold unchanged for ten steps",
                "planning_period_seconds": .02, "micro_dt_seconds": .002,
                "forecast_cost": None, "cost_weights_used_for_selection": False,
                "fallback_nm": [0., 0.], "fallback_hold_microsteps": 10,
                "target_information": "current target only; no target-switch preview",
                "physical_queries": 0}

    def select(self, q, v, target_q, *, previous_torque=(0., 0.)):
        root_count = Counter({key: 0 for key in ROOT_ACCOUNTING_KEYS})
        forecast = Counter({key: 0 for key in FORECAST_ACCOUNTING_KEYS})
        proposal_attempts = 0

        def totals():
            pair_a = root_count["root_model_pair_prediction_attempts"]+forecast["pair_prediction_attempts"]
            pair_r = root_count["root_model_pair_prediction_returns"]+forecast["pair_prediction_returns"]
            scalar_a = root_count["root_model_scalar_prediction_attempts"]+forecast["scalar_prediction_attempts"]
            scalar_r = root_count["root_model_scalar_prediction_returns"]+forecast["scalar_prediction_returns"]
            missing = root_count["root_model_unknown_scalar_failure_count"]+forecast["unknown_scalar_failure_count"]
            return {"pair_prediction_attempts": pair_a, "pair_prediction_successes": pair_r,
                    "scalar_prediction_attempts": scalar_a, "scalar_prediction_successes": scalar_r,
                    "failed_pair_prediction_attempts": pair_a-pair_r,
                    "scalar_counts_complete": missing == 0, "scalar_counts_is_lower_bound": missing > 0,
                    "unknown_scalar_failure_count": missing, "pd_request_attempts": forecast["pd_request_attempts"],
                    "pd_request_returns": forecast["pd_request_returns"], "residual_candidate_attempts": proposal_attempts}

        try:
            position, velocity, target, previous = (
                _pair(name, value) for name, value in (
                    ("q", q), ("v", v), ("target_q", target_q), ("previous_torque", previous_torque)))
            if any(abs(value) > .5 for value in previous):
                raise ValueError("previous_request_exceeds_shared_permission")
            if any(not self.target_bounds[i][0] <= target[i] <= self.target_bounds[i][1] for i in range(2)):
                raise ValueError("target_outside_original_public_local_bounds")
            if self.model._state is not self._captured_state:
                raise ValueError("frozen_body_parameters_changed")
            cache_hit = self._cached_target == target
            root_count["root_cache_hits" if cache_hit else "root_cache_misses"] += 1
            if cache_hit:
                root = self._cached_root
            else:
                try:
                    root = solve_equilibrium_root(self._theta, self.model.qref, self.joint_ranges, target,
                                                  predictor=self.model.predict)
                except BaseException as exc:
                    root_count.update(getattr(exc, "equilibrium_root_accounting", {}))
                    raise
                root_count.update(root.accounting)
                if self.model._state is not self._captured_state:
                    raise ValueError("body_parameters_changed_during_equilibrium_inverse")
                self._cached_target, self._cached_root = target, root
            hold = root.request_nm if root.has_root else (0., 0.)
            pq, pv = position, velocity
            trajectory_q, trajectory_v, requests = [], [], []
            reason, first = None, None
            for stage in range(self.config.horizon):
                if stage == 0:
                    proposal_attempts += 1
                forecast["pd_request_attempts"] += 1
                request = equilibrium_feedback_request(pq, pv, target, hold)
                forecast["pd_request_returns"] += 1
                if stage == 0:
                    first = request
                forecast["pair_prediction_attempts"] += 1
                try:
                    next_q, next_v = self.model.predict(pq, pv, request)
                except BaseException as exc:
                    attempts, returns, missing = _prediction_failure_counts(exc)
                    forecast["pair_prediction_failures"] += 1
                    forecast["scalar_prediction_attempts"] += attempts
                    forecast["scalar_prediction_returns"] += returns
                    forecast["scalar_prediction_failures"] += attempts-returns
                    forecast["unknown_scalar_failure_count"] += missing
                    raise
                forecast["pair_prediction_returns"] += 1
                forecast["scalar_prediction_attempts"] += 2
                forecast["scalar_prediction_returns"] += 2
                pq, pv = _pair("forecast_q", next_q), _pair("forecast_v", next_v)
                if any(not self.forecast_bounds[i][0] <= pq[i] <= self.forecast_bounds[i][1] for i in range(2)):
                    reason = "forecast_position_bounds"
                    break
                if any(abs(value) > self.config.velocity_limit_rad_s for value in pv):
                    reason = "forecast_velocity_bound"
                    break
                trajectory_q.append(pq)
                trajectory_v.append(pv)
                requests.append(request)
                forecast["forecast_steps_accepted"] += 1
            if self.model._state is not self._captured_state:
                raise ValueError("body_parameters_changed_during_single_forecast")
            feasible = reason is None and len(trajectory_q) == self.config.horizon
            candidate = PairCandidateRecord(first, feasible, None, reason, len(trajectory_q),
                                            forecast["pair_prediction_attempts"],
                                            forecast["scalar_prediction_attempts"],
                                            forecast["unknown_scalar_failure_count"] == 0)
            total = totals()
            return EquilibriumFeedforwardDecision(
                torque=first if feasible else (0., 0.), feasible_candidates=int(feasible), fallback=not feasible,
                cost=None, predicted_q=tuple(trajectory_q) if feasible else (),
                predicted_v=tuple(trajectory_v) if feasible else (),
                pair_prediction_attempts=total["pair_prediction_attempts"],
                pair_prediction_successes=total["pair_prediction_successes"],
                scalar_prediction_attempts=total["scalar_prediction_attempts"],
                scalar_prediction_successes=total["scalar_prediction_successes"],
                failed_pair_prediction_attempts=total["failed_pair_prediction_attempts"],
                scalar_counts_complete=total["scalar_counts_complete"],
                scalar_counts_is_lower_bound=total["scalar_counts_is_lower_bound"],
                unknown_scalar_failure_count=total["unknown_scalar_failure_count"], candidate_records=(candidate,),
                trajectory_requested_torque=tuple(requests) if feasible else (), selected_residual_nm=hold if feasible else None,
                pd_request_attempts=total["pd_request_attempts"], pd_request_returns=total["pd_request_returns"],
                residual_candidate_attempts=proposal_attempts, root_result=root, root_cache_hit=cache_hit,
                root_accounting=dict(root_count), forecast_accounting=dict(forecast))
        except BaseException as exc:
            exc.pair_planning_accounting = totals()
            exc.equilibrium_accounting = {"root": dict(root_count), "forecast": dict(forecast)}
            raise
