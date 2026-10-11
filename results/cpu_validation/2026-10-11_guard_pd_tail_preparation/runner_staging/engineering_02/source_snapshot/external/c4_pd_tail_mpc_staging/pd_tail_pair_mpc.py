"""Unselected engineering draft: first-free request with fixed PD tail.

This NumPy-only mathematical controller has no simulator, data loader, model
update or mutable velocity history. A formal experiment is not authorized.
The first request uses the original grid; later requests use each candidate's
own predicted state and the current target, without target-switch preview.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from developmental_physics.guard_lag_pair_mpc import FixedGuardLagPairMPC
from developmental_physics.local_pair_model import (
    PairCandidateRecord, PairMPCDecision, PairPredictionError, _pair,
)


FORMAL_PD_TAIL_CONTROL_ENABLED = False
TAIL_KP = (64., 64.)
TAIL_KD = (0., 4.)


@dataclass(frozen=True)
class PDTailMPCDecision(PairMPCDecision):
    trajectory_requested_torque: tuple[tuple[float, float], ...] = ()


class FixedPDTailGuardLagPairMPC(FixedGuardLagPairMPC):
    """Keep original first grid/history/cost constants; replace the tail only."""

    def spec(self):
        return {**super().spec(),
            "action_rollout": "first request is a grid vector; remaining requests use fixed PD on candidate-predicted states; apply first request only",
            "cost": "original per-stage weights, using each stage's requested torque; change at first request only",
            "tail_policy": {
                "first_stage": "original candidate vector b",
                "remaining_stages": "clip(Kp*(current target-predicted q)-Kd*predicted v, -.5, .5)",
                "kp": list(TAIL_KP), "kd": list(TAIL_KD),
                "gain_source": "previously selected disclosed PD baseline; no new gain selection",
                "gain_updates": 0, "model_updates": 0,
                "target_preview": False, "future_actual_state": False,
                "execution": "apply b only; observe and replan after the next 20 ms interval",
                "replanned_future_matches_tail_is_guaranteed": False,
                "physical_validation": False,
            },
            "trajectory_request_field": "trajectory_requested_torque",
            "formal_experiment_enabled": FORMAL_PD_TAIL_CONTROL_ENABLED,
        }

    @staticmethod
    def _tail_request(q, v, target):
        return tuple(float(np.clip(TAIL_KP[i]*(target[i]-q[i])-TAIL_KD[i]*v[i], -.5, .5))
                     for i in range(2))

    def select(self, q, v, target_q, previous_v, *, previous_torque=(0., 0.)):
        position, velocity, target, previous, history = (
            _pair(name, value) for name, value in (
                ("q", q), ("v", v), ("target_q", target_q),
                ("previous_torque", previous_torque), ("previous_v", previous_v)))
        cfg = self.config
        if any(abs(u) > cfg.torque_limit_nm for u in previous):
            raise ValueError("previous vector torque exceeds per-axis fixed permission")
        if any(not self.target_bounds[i][0] <= target[i] <= self.target_bounds[i][1]
               for i in range(2)):
            raise ValueError("current target must be local and inside each public limit margin")
        feasible = []
        records = []
        pair_attempts = pair_successes = scalar_attempts = scalar_successes = unknown_failures = 0
        for first_request in self._candidates:
            predicted_q, predicted_v = position, velocity
            rollout_previous_v = history
            trajectory_q, trajectory_v, trajectory_requested = [], [], []
            axis_costs = [cfg.change_weight*(first_request[i]-previous[i])**2 for i in range(2)]
            reason = None
            candidate_pair = candidate_scalar = 0
            candidate_counts_complete = True
            for stage in range(cfg.horizon):
                request = (first_request if stage == 0
                           else self._tail_request(predicted_q, predicted_v, target))
                pair_attempts += 1
                candidate_pair += 1
                old_current_v = predicted_v
                try:
                    predicted_q, predicted_v = self.model.predict(
                        predicted_q, predicted_v, request, rollout_previous_v)
                except ValueError as exc:
                    if isinstance(exc, PairPredictionError):
                        scalar_attempts += exc.scalar_prediction_attempts
                        candidate_scalar += exc.scalar_prediction_attempts
                        scalar_successes += exc.scalar_prediction_successes
                    else:
                        unknown_failures += 1
                        candidate_counts_complete = False
                    reason = f"prediction_error:{type(exc).__name__}"
                    break
                except BaseException as exc:
                    head_cost = getattr(exc, "pair_prediction_accounting", None)
                    if head_cost is not None:
                        scalar_attempts += head_cost["scalar_prediction_attempts"]
                        scalar_successes += head_cost["scalar_prediction_successes"]
                    else:
                        unknown_failures += 1
                    exc.pair_planning_accounting = {
                        "pair_prediction_attempts": pair_attempts,
                        "pair_prediction_successes": pair_successes,
                        "scalar_prediction_attempts": scalar_attempts,
                        "scalar_prediction_successes": scalar_successes,
                        "failed_pair_prediction_attempts": pair_attempts-pair_successes,
                        "scalar_counts_complete": unknown_failures == 0,
                        "scalar_counts_is_lower_bound": unknown_failures > 0,
                        "unknown_scalar_failure_count": unknown_failures,
                    }
                    raise
                rollout_previous_v = old_current_v
                pair_successes += 1
                scalar_attempts += 2
                scalar_successes += 2
                candidate_scalar += 2
                if any(not self.forecast_bounds[i][0] <= predicted_q[i] <= self.forecast_bounds[i][1]
                       for i in range(2)):
                    reason = "forecast_position_bounds"
                    break
                if any(abs(predicted_v[i]) > cfg.velocity_limit_rad_s for i in range(2)):
                    reason = "forecast_velocity_bound"
                    break
                trajectory_q.append(tuple(predicted_q))
                trajectory_v.append(tuple(predicted_v))
                trajectory_requested.append(tuple(request))
                for i in range(2):
                    axis_costs[i] += (
                        cfg.position_weight*(predicted_q[i]-target[i])**2
                        +cfg.velocity_weight*predicted_v[i]**2
                        +cfg.effort_weight*request[i]**2)
                if not np.isfinite(axis_costs).all() or not np.isfinite(sum(axis_costs)):
                    reason = "nonfinite_cost"
                    break
            else:
                cost = sum(axis_costs)
                feasible.append((cost, sum(abs(u) for u in first_request), *first_request,
                                 tuple(trajectory_q), tuple(trajectory_v), tuple(trajectory_requested)))
            ok = reason is None and len(trajectory_q) == cfg.horizon
            records.append(PairCandidateRecord(
                first_request, ok, sum(axis_costs) if ok else None, reason,
                len(trajectory_q), candidate_pair, candidate_scalar, candidate_counts_complete))
        if feasible:
            cost, _, u0, u1, trajectory_q, trajectory_v, trajectory_requested = min(feasible)
            torque = (u0, u1)
        else:
            cost = None
            torque = (0., 0.)
            trajectory_q = trajectory_v = trajectory_requested = ()
        return PDTailMPCDecision(
            torque, len(feasible), not feasible, cost, trajectory_q, trajectory_v,
            pair_attempts, pair_successes, scalar_attempts, scalar_successes,
            pair_attempts-pair_successes, unknown_failures == 0,
            unknown_failures > 0, unknown_failures, tuple(records), trajectory_requested)
