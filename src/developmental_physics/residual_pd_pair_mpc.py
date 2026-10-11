"""Native-only pair MPC with a bounded first-stage residual over disclosed PD.

Each candidate closes its own prediction loop. The controller reads no physical
model, future state, target schedule, velocity history, or learned updates.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import product

import numpy as np

from .local_pair_model import (
    FixedPairMPC, PairCandidateRecord, PairMPCDecision, PairPredictionError, _pair,
)

KP = (64., 64.)
KD = (0., 4.)
RESIDUAL_LIMIT_NM = .125


def public_pd_request(q, v, target):
    """The same previously disclosed classical gains for both model groups."""
    return tuple(float(np.clip(KP[i]*(target[i]-q[i])-KD[i]*v[i], -.5, .5))
                 for i in range(2))


@dataclass(frozen=True)
class ResidualPDMPCDecision(PairMPCDecision):
    trajectory_requested_torque: tuple[tuple[float, float], ...] = ()
    selected_residual_nm: tuple[float, float] | None = None
    pd_request_attempts: int = 0
    pd_request_returns: int = 0
    residual_candidate_attempts: int = 0


class ResidualPDPairMPC(FixedPairMPC):
    """81 first residuals, H15 predicted PD tail, complete-request costs."""

    def __init__(self, model, joint_ranges, config=None):
        super().__init__(model, joint_ranges, config)
        if self.config.torque_limit_nm != .5 or self.config.candidate_count != 9:
            raise ValueError("shared .5 Nm permission and nine-point residual grid required")
        self._axis_candidates = tuple(float(x) for x in np.linspace(-.125, .125, 9))
        self._candidates = tuple(product(self._axis_candidates, repeat=2))

    def spec(self):
        return {**super().spec(),
                "axis_candidates_nm": None, "vector_candidates_nm": None,
                "residual_candidates_nm": [list(row) for row in self._candidates],
                "residual_axis_candidates_nm": list(self._axis_candidates),
                "residual_limit_nm": RESIDUAL_LIMIT_NM,
                "shared_pd": {"kp": KP, "kd": KD, "gain_updates": 0,
                              "source": "existing_public_PD64_Kd0_4_development_prior"},
                "action_rollout": "clip(PD(current)+delta) first; PD(each candidate predicted state) tail; apply first only",
                "cost": "full final requested torque at every stage and first full-request change",
                "tie_break": "cost, abs(full first request), signed full request, signed residual",
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
        for residual in self._candidates:
            candidates += 1
            first = tuple(float(np.clip(base_request[i]+residual[i], -.5, .5)) for i in range(2))
            pq, pv = position, velocity
            trajectory_q, trajectory_v, requests = [], [], []
            costs = [cfg.change_weight*(first[i]-previous[i])**2 for i in range(2)]
            reason = None
            local_pair = local_scalar = 0
            complete_counts = True
            for stage in range(cfg.horizon):
                request = first if stage == 0 else pd_request(pq, pv)
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
