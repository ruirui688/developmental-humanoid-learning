"""Explicit-history variant of the unchanged constant-vector pair MPC.

This controller has no simulator access, parameter updates or stored velocity
history. The caller supplies the immediately preceding native velocity from
the same uninterrupted sequence. Every candidate starts from that same pair
of endpoints and advances its own predicted history independently.
"""
from __future__ import annotations

from itertools import product

import numpy as np

from developmental_physics.guard_lag_pair_model import GuardLagPairBodyModel
from developmental_physics.local_model import MPCConfig
from developmental_physics.local_pair_model import (
    FixedPairMPC, PairCandidateRecord, PairMPCDecision, PairPredictionError, _pair,
)


class FixedGuardLagPairMPC(FixedPairMPC):
    """Keep original H15/grid/cost/tie/limits; pass explicit lag history."""

    def __init__(self, model: GuardLagPairBodyModel, joint_ranges,
                 config: MPCConfig | None = None):
        if not isinstance(model, GuardLagPairBodyModel):
            raise TypeError("model must be a GuardLagPairBodyModel")
        self.model = model
        self.config = MPCConfig() if config is None else config
        if not isinstance(self.config, MPCConfig):
            raise TypeError("config must be MPCConfig")
        limits = np.asarray(joint_ranges, dtype=float)
        if (limits.shape != (2, 2) or not np.isfinite(limits).all()
                or np.any(limits[:, 0] >= limits[:, 1])):
            raise ValueError("two finite ordered public joint ranges required")
        self.joint_ranges = tuple(tuple(float(x) for x in row) for row in limits)
        cfg = self.config
        self.forecast_bounds = tuple(
            (max(model.qref[i]-cfg.local_position_radius_rad,
                 limits[i, 0]-cfg.prediction_limit_tolerance_rad),
             min(model.qref[i]+cfg.local_position_radius_rad,
                 limits[i, 1]+cfg.prediction_limit_tolerance_rad)) for i in range(2))
        self.target_bounds = tuple(
            (max(model.qref[i]-cfg.local_position_radius_rad,
                 limits[i, 0]+cfg.target_limit_margin_rad),
             min(model.qref[i]+cfg.local_position_radius_rad,
                 limits[i, 1]-cfg.target_limit_margin_rad)) for i in range(2))
        self._axis_candidates = tuple(float(x) for x in np.linspace(
            -cfg.torque_limit_nm, cfg.torque_limit_nm, cfg.candidate_count))
        self._candidates = tuple(product(self._axis_candidates, repeat=2))

    def spec(self):
        return {**super().spec(), "history": {
            "argument": "previous_v", "stored_in_model_or_controller": False,
            "native_initialization": "immediately preceding native endpoint, 20 ms apart",
            "unknown_or_reset_history": "must not call select; never substitute zero",
            "candidate_initialization": "each candidate independently starts from supplied previous_v",
            "rollout_advance": "predict first, then previous_v becomes old current v",
        }}

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
        for torque in self._candidates:
            predicted_q, predicted_v = position, velocity
            rollout_previous_v = history
            trajectory_q, trajectory_v = [], []
            axis_costs = [cfg.change_weight*(torque[i]-previous[i])**2 for i in range(2)]
            reason = None
            candidate_pair = candidate_scalar = 0
            candidate_counts_complete = True
            for _ in range(cfg.horizon):
                pair_attempts += 1
                candidate_pair += 1
                old_current_v = predicted_v
                try:
                    predicted_q, predicted_v = self.model.predict(
                        predicted_q, predicted_v, torque, rollout_previous_v)
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
                    # Preserve IO/interrupt semantics and all prior mathematical cost.
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
                for i in range(2):
                    axis_costs[i] += (
                        cfg.position_weight*(predicted_q[i]-target[i])**2
                        +cfg.velocity_weight*predicted_v[i]**2
                        +cfg.effort_weight*torque[i]**2)
                if not np.isfinite(axis_costs).all() or not np.isfinite(sum(axis_costs)):
                    reason = "nonfinite_cost"
                    break
            else:
                cost = sum(axis_costs)
                feasible.append((cost, sum(abs(u) for u in torque), *torque,
                                 tuple(trajectory_q), tuple(trajectory_v)))
            ok = reason is None and len(trajectory_q) == cfg.horizon
            records.append(PairCandidateRecord(
                torque, ok, sum(axis_costs) if ok else None, reason,
                len(trajectory_q), candidate_pair, candidate_scalar, candidate_counts_complete))
        if feasible:
            cost, _, u0, u1, trajectory_q, trajectory_v = min(feasible)
            torque = (u0, u1)
        else:
            cost = None
            torque = (0., 0.)
            trajectory_q = trajectory_v = ()
        return PairMPCDecision(
            torque, len(feasible), not feasible, cost, trajectory_q, trajectory_v,
            pair_attempts, pair_successes, scalar_attempts, scalar_successes,
            pair_attempts-pair_successes, unknown_failures == 0,
            unknown_failures > 0, unknown_failures, tuple(records))
