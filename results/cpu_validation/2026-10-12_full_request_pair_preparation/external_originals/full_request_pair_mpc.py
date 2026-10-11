"""FR3 bounded full-final-first-request candidate; no execution on import.

Scalar and supported batch cores copy the frozen original controller. Only the
static first-request grid is converted once to dynamic held residuals per select.
Original controllers are never edited. Spec/grid stay independent of current q/v.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import replace
from itertools import product

import numpy as np

from developmental_physics.fast_feedback_pair_model import FastFeedbackGuardCoupledPairBodyModel
from developmental_physics.fast_feedback_pair_development import CountedGuardModel
from developmental_physics.fast_feedback_pair_mpc import KP, KD, ResidualPDMPCDecision, public_pd_request
from developmental_physics.guard_coupled_pair_model import GuardCoupledPairBodyModel
from developmental_physics.guard_pair_model import KnownAngleGuard
from developmental_physics.local_model import HINGE_THRESHOLD_NM, MPCConfig
from developmental_physics.local_pair_model import FixedPairMPC, PairBodyModel, PairCandidateRecord, PairPredictionError, _pair

FULL_REQUEST_AXIS_GRID_NM = (-.5, -.375, -.25, -.125, 0., .125, .25, .375, .5)


def _method_is(instance, name, function):
    return getattr(getattr(instance, name, None), "__func__", None) is function


def _same_wrapper_code(first, second):
    """Exclude module/file locations; root must separately freeze matching class AST."""
    first, second = getattr(first, "__code__", None), getattr(second, "__code__", None)
    return first is not None and second is not None and all(
        getattr(first, name) == getattr(second, name) for name in (
            "co_code", "co_consts", "co_names", "co_varnames", "co_cellvars", "co_freevars",
            "co_argcount", "co_kwonlyargcount"))


class FullRequestResidualPDPairMPC(FixedPairMPC):
    """81 final-first-request grids mapped to held delta; unchanged H150 PD tail."""

    def __init__(self, model, joint_ranges, config=None):
        baseline = MPCConfig()
        micro = replace(baseline, horizon=150, position_weight=.1 * baseline.position_weight,
                        velocity_weight=.1 * baseline.velocity_weight, effort_weight=.1 * baseline.effort_weight)
        if config is not None and config != micro:
            raise ValueError("Z_fixed_micro_horizon_and_time_normalized_cost_required")
        if model.dt != .002:
            raise ValueError("Z_controller_requires_2ms_body_model")
        super().__init__(model, joint_ranges, micro)
        if self.config.torque_limit_nm != .5 or self.config.candidate_count != 9:
            raise ValueError("shared .5 Nm permission and nine-point residual grid required")
        self._axis_candidates = FULL_REQUEST_AXIS_GRID_NM
        self._candidates = tuple(product(self._axis_candidates, repeat=2))

    def spec(self):
        return {**super().spec(),
                "axis_candidates_nm": None, "vector_candidates_nm": None,
                "first_final_request_axis_grid_nm": list(FULL_REQUEST_AXIS_GRID_NM),
                "first_final_request_grid_nm": [list(row) for row in self._candidates],
                "first_final_request_grid_spacing_nm": .125,
                "first_final_request_candidate_count": 81,
                "dynamic_residual_definition": "delta=grid-first-clipped-PD-current-native; once per macro",
                "first_request_float_semantics": "clip(p+(grid-p),-.5,.5); no bit equality promise to nominal grid",
                "residual_candidates_nm": None, "residual_axis_candidates_nm": None,
                "maximum_absolute_dynamic_delta_nm": 1., "final_request_permission_nm": .5,
                "pure_PD_candidate_guaranteed": False,
                "zero_nominal_first_request_is_not_literal_zero_fallback": True,
                "shared_pd": {"kp": KP, "kd": KD, "gain_updates": 0,
                              "source": "original_public_PD64_Kd4_4_no_gain_change_or_scan"},
                "action_rollout": "PD(predicted q/v)+held dynamic delta first ten 2ms steps; remaining 140 PD delta zero",
                "execution": "hold chosen dynamic delta for ten native-feedback microsteps; fallback literal torque zero for ten",
                "micro_dt_seconds": .002, "planning_period_seconds": .02,
                "residual_hold_microsteps": 10, "running_cost_time_scale": .1,
                "discount": "none; original cost has no discount",
                "cost": "full final requested torque at every stage and first full-request change",
                "tie_break": "cost, abs(full first request), signed full request, signed dynamic residual",
                "model_signature": "predict(q,v,u); no fabricated previous_v",
                "fallback_nm": [0., 0.]}

    def select(self, q, v, target_q, *, previous_torque=(0., 0.)):
        position, velocity, target, previous = (
            _pair(name, value) for name, value in (
                ("q", q), ("v", v), ("target_q", target_q),
                ("previous_torque", previous_torque)))
        cfg = self.config
        if any(abs(u) > cfg.torque_limit_nm for u in previous):
            raise ValueError("previous request exceeds shared permission")
        if any(not self.target_bounds[i][0] <= target[i] <= self.target_bounds[i][1]
               for i in range(2)):
            raise ValueError("target outside public local bounds")
        feasible, records = [], []
        pair_attempts = pair_returns = scalar_attempts = scalar_returns = unknown = 0
        pd_attempts = pd_returns = candidates = 0

        def accounting():
            return {"pair_prediction_attempts": pair_attempts,
                    "pair_prediction_successes": pair_returns,
                    "scalar_prediction_attempts": scalar_attempts,
                    "scalar_prediction_successes": scalar_returns,
                    "failed_pair_prediction_attempts": pair_attempts-pair_returns,
                    "scalar_counts_complete": unknown == 0,
                    "scalar_counts_is_lower_bound": unknown > 0,
                    "unknown_scalar_failure_count": unknown,
                    "pd_request_attempts": pd_attempts, "pd_request_returns": pd_returns,
                    "residual_candidate_attempts": candidates}

        def pd_request(pq, pv):
            nonlocal pd_attempts, pd_returns
            pd_attempts += 1
            try:
                request = public_pd_request(pq, pv, target)
            except BaseException as exc:
                exc.pair_planning_accounting = accounting()
                raise
            pd_returns += 1
            return request

        base_request = pd_request(position, velocity)
        residual_candidates = tuple(tuple(float(grid[i]-base_request[i]) for i in range(2))
                                    for grid in self._candidates)
        for residual in residual_candidates:
            candidates += 1
            first = tuple(float(np.clip(base_request[i]+residual[i], -.5, .5)) for i in range(2))
            pq, pv = position, velocity
            trajectory_q, trajectory_v, requests = [], [], []
            costs = [cfg.change_weight*(first[i]-previous[i])**2 for i in range(2)]
            reason = None
            local_pair = local_scalar = 0
            complete_counts = True
            for stage in range(cfg.horizon):
                if stage == 0:
                    request = first
                else:
                    base = pd_request(pq, pv)
                    delta = residual if stage < 10 else (0., 0.)
                    request = tuple(float(np.clip(base[i]+delta[i], -.5, .5)) for i in range(2))
                pair_attempts += 1
                local_pair += 1
                try:
                    pq, pv = self.model.predict(pq, pv, request)
                except BaseException as exc:
                    if isinstance(exc, PairPredictionError):
                        scalar_attempts += exc.scalar_prediction_attempts
                        scalar_returns += exc.scalar_prediction_successes
                        local_scalar += exc.scalar_prediction_attempts
                    else:
                        head = getattr(exc, "pair_prediction_accounting", None)
                        if head is not None:
                            scalar_attempts += head["scalar_prediction_attempts"]
                            scalar_returns += head["scalar_prediction_successes"]
                            local_scalar += head["scalar_prediction_attempts"]
                        else:
                            unknown += 1
                            complete_counts = False
                    if isinstance(exc, ValueError):
                        reason = "prediction_error:"+type(exc).__name__
                        break
                    exc.pair_planning_accounting = accounting()
                    raise
                pair_returns += 1
                scalar_attempts += 2
                scalar_returns += 2
                local_scalar += 2
                if any(not self.forecast_bounds[i][0] <= pq[i] <= self.forecast_bounds[i][1]
                       for i in range(2)):
                    reason = "forecast_position_bounds"
                    break
                if any(abs(pv[i]) > cfg.velocity_limit_rad_s for i in range(2)):
                    reason = "forecast_velocity_bound"
                    break
                trajectory_q.append(tuple(pq))
                trajectory_v.append(tuple(pv))
                requests.append(tuple(request))
                for i in range(2):
                    costs[i] += (cfg.position_weight*(pq[i]-target[i])**2
                                 +cfg.velocity_weight*pv[i]**2
                                 +cfg.effort_weight*request[i]**2)
                if not np.isfinite(costs).all() or not np.isfinite(sum(costs)):
                    reason = "nonfinite_cost"
                    break
            else:
                feasible.append((sum(costs), sum(abs(u) for u in first), *first,
                                 *residual, tuple(trajectory_q), tuple(trajectory_v), tuple(requests)))
            ok = reason is None and len(trajectory_q) == cfg.horizon
            records.append(PairCandidateRecord(first, ok, sum(costs) if ok else None, reason,
                                               len(trajectory_q), local_pair, local_scalar, complete_counts))
        if feasible:
            cost, _, u0, u1, d0, d1, tq, tv, tr = min(feasible)
            torque, chosen = (u0, u1), (d0, d1)
        else:
            cost, torque, chosen, tq, tv, tr = None, (0., 0.), None, (), (), ()
        return ResidualPDMPCDecision(
            torque, len(feasible), not feasible, cost, tq, tv,
            pair_attempts, pair_returns, scalar_attempts, scalar_returns,
            pair_attempts-pair_returns, unknown == 0, unknown > 0, unknown,
            tuple(records), tr, chosen, pd_attempts, pd_returns, candidates)


class BatchedFullRequestResidualPDPairMPC(FullRequestResidualPDPairMPC):
    """150 stage batches; each live row keeps the original two nine-term dots."""

    def __init__(self, model, joint_ranges, config=None, *, counted_model_type=CountedGuardModel):
        self._counted_model_type = counted_model_type
        super().__init__(model, joint_ranges, config)

    def _supported(self):
        model = self.model
        plain = type(model) is FastFeedbackGuardCoupledPairBodyModel
        counted_type = self._counted_model_type
        counted = isinstance(counted_type, type) and type(model) is counted_type
        if counted and (counted_type.__mro__[1:] != CountedGuardModel.__mro__[1:]
                        or not all(_same_wrapper_code(getattr(counted_type, name, None), getattr(CountedGuardModel, name))
                                   for name in ("_count", "_features", "_predict_state", "_predict_output"))):
            return False
        if not (plain or counted):
            return False
        expected = {
            "predict": PairBodyModel.predict,
            "_features": counted_type._features if counted else GuardCoupledPairBodyModel._features,
            "_predict_state": counted_type._predict_state if counted else PairBodyModel._predict_state,
            "_predict_output": counted_type._predict_output if counted else PairBodyModel._predict_output,
        }
        if not all(_method_is(model, name, function) for name, function in expected.items()):
            return False
        if counted and (type(model.cost) is not Counter or type(model.forward_counts) is not Counter
                        or not _method_is(model, "_count", counted_type._count)):
            return False
        guard = model.public_guard
        full_requests = tuple(product(FULL_REQUEST_AXIS_GRID_NM, repeat=2))
        return (type(guard) is KnownAngleGuard and _method_is(guard, "project", KnownAngleGuard.project)
                and model.structure == "coupled_hinge9" and model.dt == .002
                and model._state.theta.shape == (2, 9) and model._state.theta.dtype == np.float64
                and not model._state.theta.flags.writeable and self._candidates == full_requests
                and self._axis_candidates == FULL_REQUEST_AXIS_GRID_NM)

    def spec(self):
        return {**super().spec(), "implementation_candidate": {
            "elementwise_batches": "PD, guard and coupled features",
            "velocity_reduction": "original _predict_output one unchanged nine-term vector dot per head",
            "cost_accumulation": "original Python float expression and stage/axis order per candidate",
            "known_CountedGuardModel_supported": self._supported() and type(self.model) is self._counted_model_type,
            "counted_adapter_class": getattr(self._counted_model_type, "__name__", None),
            "counted_adapter_class_AST_must_be_frozen_equal": True,
            "unknown_or_overridden_model": "new full-request scalar reference select",
            "logical_work_units": "unchanged pair/scalar/features/PD/candidates, actual batch kernels separate",
            "realtime_20ms_demonstrated": False}}

    def select(self, q, v, target_q, *, previous_torque=(0., 0.)):
        self.last_batch_execution = {"stage_batches": 0, "feature_batch_rows": 0,
                                     "original_scalar_dot_calls": 0, "serial_fallback_selections": 0}
        if not self._supported():
            self.last_batch_execution["serial_fallback_selections"] = 1
            return super().select(q, v, target_q, previous_torque=previous_torque)
        position, velocity, target, previous = (
            _pair(name, value) for name, value in (
                ("q", q), ("v", v), ("target_q", target_q), ("previous_torque", previous_torque)))
        cfg, model, state = self.config, self.model, self.model._state
        if any(abs(u) > cfg.torque_limit_nm for u in previous):
            raise ValueError("previous request exceeds shared permission")
        if any(not self.target_bounds[i][0] <= target[i] <= self.target_bounds[i][1] for i in range(2)):
            raise ValueError("target outside public local bounds")
        counted = type(model) is self._counted_model_type

        def count(key):
            if counted:
                model._count(key)

        pair_attempts = pair_returns = scalar_attempts = scalar_returns = 0
        pd_attempts = pd_returns = candidates = 0

        def accounting():
            return {"pair_prediction_attempts": pair_attempts, "pair_prediction_successes": pair_returns,
                    "scalar_prediction_attempts": scalar_attempts, "scalar_prediction_successes": scalar_returns,
                    "failed_pair_prediction_attempts": pair_attempts-pair_returns,
                    "scalar_counts_complete": True, "scalar_counts_is_lower_bound": False,
                    "unknown_scalar_failure_count": 0, "pd_request_attempts": pd_attempts,
                    "pd_request_returns": pd_returns, "residual_candidate_attempts": candidates}

        pd_attempts += 1
        open_pair = False
        try:
            base_request = public_pd_request(position, velocity, target)
        except BaseException as exc:
            exc.pair_planning_accounting = accounting()
            raise
        pd_returns += 1
        residual_candidates = tuple(tuple(float(grid[i]-base_request[i]) for i in range(2))
                                    for grid in self._candidates)
        residuals = np.asarray(residual_candidates, dtype=np.float64)
        n = len(residuals)
        first = np.clip(np.asarray(base_request)[None, :] + residuals, -.5, .5)
        pq = np.repeat(np.asarray(position)[None, :], n, axis=0)
        pv = np.repeat(np.asarray(velocity)[None, :], n, axis=0)
        costs = [[cfg.change_weight*(float(first[j, i])-previous[i])**2 for i in range(2)] for j in range(n)]
        active = np.ones(n, dtype=bool)
        reasons = [None] * n
        local_pair, local_scalar = [0]*n, [0]*n
        steps = [0]*n
        trajectory_q = np.empty((n, cfg.horizon, 2), dtype=np.float64)
        trajectory_v = np.empty_like(trajectory_q)
        trajectory_u = np.empty_like(trajectory_q)
        ranges = np.asarray(model.public_guard.public_joint_ranges, dtype=np.float64)
        lower, upper = ranges[:, 0] + .03, ranges[:, 1] - .03
        qref = np.asarray(model.qref, dtype=np.float64)

        try:
            for stage in range(cfg.horizon):
                ids = np.flatnonzero(active)
                if not len(ids):
                    break
                self.last_batch_execution["stage_batches"] += 1
                if stage == 0:
                    request = first[ids].copy()
                else:
                    pd_attempts += len(ids)
                    with np.errstate(over="ignore", invalid="ignore"):
                        base = np.clip(64.*(np.asarray(target)-pq[ids])-4.*pv[ids], -.5, .5)
                        request = np.clip(base + (residuals[ids] if stage < 10 else 0.), -.5, .5)
                    pd_returns += len(ids)
                # Every live row retains raw q/v. Only the original command guard clips u.
                with np.errstate(over="ignore", invalid="ignore"):
                    command = np.clip(request, -.5, .5)
                    blocked = ((pq[ids] <= lower) & (command < 0.)) | ((pq[ids] >= upper) & (command > 0.))
                    command = np.where(blocked, 0., command)
                    displacement = pq[ids] - qref
                    hinge = np.sign(command)*np.maximum(np.abs(command)-HINGE_THRESHOLD_NM, 0.)
                    features = np.column_stack((pv[ids], displacement, command, hinge, np.ones(len(ids))))
                self.last_batch_execution["feature_batch_rows"] += len(ids)
                finite_features = np.isfinite(features).all(axis=1)
                for row, j in enumerate(ids):
                    j = int(j)
                    if stage == 0:
                        candidates += 1
                    pair_attempts += 1; local_pair[j] += 1
                    open_pair = True
                    count("pair_prediction_attempts"); count("feature_guard_projection_attempts")
                    if not finite_features[row]:
                        reasons[j] = "prediction_error:PairPredictionError"
                        active[j] = False
                        count("pair_prediction_failures")
                        open_pair = False
                        continue
                    count("feature_guard_projection_returns")
                    pair_features = np.repeat(features[row][None, :], 2, axis=0)
                    predicted_v = []
                    for head in range(2):
                        scalar_attempts += 1; local_scalar[j] += 1
                        self.last_batch_execution["original_scalar_dot_calls"] += 1
                        try:
                            # Keep the original 1D dot reduction and instrumentation.
                            predicted_v.append(model._predict_output(head, pair_features[head], state))
                        except ValueError:
                            reasons[j] = "prediction_error:PairPredictionError"
                            active[j] = False
                            count("pair_prediction_failures")
                            open_pair = False
                            break
                        except BaseException as exc:
                            count("pair_prediction_failures")
                            open_pair = False
                            exc.pair_prediction_accounting = {
                                "scalar_prediction_attempts": head+1, "scalar_prediction_successes": head,
                                "scalar_counts_complete": True, "failure_stage": f"velocity_output_{head}"}
                            raise
                        scalar_returns += 1
                    else:
                        with np.errstate(over="ignore", invalid="ignore"):
                            endpoint = np.asarray(pq[j])+model.dt*np.asarray(predicted_v)
                        if not np.isfinite(endpoint).all():
                            reasons[j] = "prediction_error:PairPredictionError"
                            active[j] = False
                            count("pair_prediction_failures")
                            open_pair = False
                            continue
                        pair_returns += 1
                        count("pair_prediction_returns")
                        open_pair = False
                        next_q, next_v = tuple(float(x) for x in endpoint), tuple(predicted_v)
                        if any(not self.forecast_bounds[i][0] <= next_q[i] <= self.forecast_bounds[i][1] for i in range(2)):
                            reasons[j] = "forecast_position_bounds"; active[j] = False
                            continue
                        if any(abs(next_v[i]) > cfg.velocity_limit_rad_s for i in range(2)):
                            reasons[j] = "forecast_velocity_bound"; active[j] = False
                            continue
                        torque = tuple(float(x) for x in request[row])
                        trajectory_q[j, stage] = next_q; trajectory_v[j, stage] = next_v; trajectory_u[j, stage] = torque
                        steps[j] += 1
                        for i in range(2):
                            costs[j][i] += (cfg.position_weight*(next_q[i]-target[i])**2
                                           +cfg.velocity_weight*next_v[i]**2 +cfg.effort_weight*torque[i]**2)
                        if not np.isfinite(costs[j]).all() or not np.isfinite(sum(costs[j])):
                            reasons[j] = "nonfinite_cost"; active[j] = False
                            continue
                        pq[j], pv[j] = next_q, next_v
            if model._state is not state:
                raise RuntimeError("body_parameters_changed_during_select_not_permitted")
        except BaseException as exc:
            if open_pair:
                count("pair_prediction_failures")
            exc.pair_planning_accounting = accounting()
            exc.batch_execution_cost = dict(self.last_batch_execution)
            raise

        feasible, records = [], []
        for j, residual in enumerate(residual_candidates):
            first_request = tuple(float(x) for x in first[j])
            ok = reasons[j] is None and steps[j] == cfg.horizon
            records.append(PairCandidateRecord(first_request, ok, sum(costs[j]) if ok else None,
                          reasons[j], steps[j], local_pair[j], local_scalar[j], True))
            if ok:
                tq = tuple(tuple(float(x) for x in row) for row in trajectory_q[j])
                tv = tuple(tuple(float(x) for x in row) for row in trajectory_v[j])
                tr = tuple(tuple(float(x) for x in row) for row in trajectory_u[j])
                feasible.append((sum(costs[j]), sum(abs(u) for u in first_request), *first_request,
                                 *residual, tq, tv, tr))
        if feasible:
            cost, _, u0, u1, d0, d1, tq, tv, tr = min(feasible)
            torque, chosen = (u0, u1), (d0, d1)
        else:
            cost, torque, chosen, tq, tv, tr = None, (0., 0.), None, (), (), ()
        return ResidualPDMPCDecision(
            torque, len(feasible), not feasible, cost, tq, tv,
            pair_attempts, pair_returns, scalar_attempts, scalar_returns,
            pair_attempts-pair_returns, True, False, 0, tuple(records), tr, chosen,
            pd_attempts, pd_returns, candidates)
