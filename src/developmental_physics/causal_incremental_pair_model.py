"""Pure CF1 native causal memory and incremental action prediction.

Only q/v, known requests, public ranges and fixed action8 enter prediction.
No backend, actual torque, root state, contact data or fitted state head is used.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json

import numpy as np

from .instrumental_action_model import action_features, count, finite

DT = .002


def _immutable(name, value, shape):
    result = finite(name, value, shape).copy()
    result.flags.writeable = False
    return result


@dataclass(frozen=True)
class NativeIntervalMemory:
    """One complete preceding interval, including its exact native endpoint."""

    trial_id: str
    control_index: int
    qprev: np.ndarray
    vprev: np.ndarray
    requestprev: np.ndarray
    endpoint_q: np.ndarray
    endpoint_v: np.ndarray

    def __post_init__(self):
        if not isinstance(self.trial_id, str) or not self.trial_id or type(self.control_index) is not int or self.control_index < 0:
            raise ValueError("legal_same_trial_interval_identity_required")
        for name in ("qprev", "vprev", "requestprev", "endpoint_q", "endpoint_v"):
            object.__setattr__(self, name, _immutable(name, getattr(self, name), (2,)))
        if np.any(np.abs(self.requestprev) > .5):
            raise ValueError("legal_known_previous_request_required_no_clip")

    def require_current(self, q, v, trial_id, control_index):
        if trial_id != self.trial_id or type(control_index) is not int or control_index != self.control_index + 1:
            raise ValueError("immediately_preceding_same_trial_history_required")
        if q.tobytes() != self.endpoint_q.tobytes() or v.tobytes() != self.endpoint_v.tobytes():
            raise ValueError("history_endpoint_must_exactly_match_current_native_qv")

    def record(self):
        return {"trial_id": self.trial_id, "control_index": self.control_index,
                **{name: getattr(self, name).tolist() for name in
                   ("qprev", "vprev", "requestprev", "endpoint_q", "endpoint_v")}}


class CausalIncrementalPairModel:
    """Fixed action8 plus previous lawful native velocity-increment residual."""

    def __init__(self, ranges, action8):
        self.ranges = _immutable("public_ranges2", ranges, (2, 2))
        self.action8 = _immutable("fixed_action8", action8, (2, 4))
        if np.any(self.ranges[:, 0] >= self.ranges[:, 1]):
            raise ValueError("ordered_public_ranges_required")

    def action_increment(self, q, request, cost=None):
        count(cost, "action_increment_pair_attempts")
        phi, _ = action_features(q, request, self.ranges, cost)
        with np.errstate(over="raise", invalid="raise"):
            result = finite("fixed_action_velocity_increment2", self.action8 @ phi, (2,))
        count(cost, "action_increment_pair_returns")
        count(cost, "action_coefficient_scalar_uses", 8)
        count(cost, "action_velocity_increment_scalar_outputs", 2)
        return result

    def predict(self, q, v, request, memory, trial_id, control_index, cost=None):
        count(cost, "pair_prediction_attempts")
        count(cost, "scalar_velocity_head_attempts", 2)
        try:
            q, v = finite("current_native_q2", q, (2,)), finite("current_native_v2", v, (2,))
            request = finite("known_current_request2", request, (2,))
            if not isinstance(memory, NativeIntervalMemory):
                raise ValueError("real_preceding_interval_memory_required_no_zero_fill")
            count(cost, "same_trial_history_consistency_attempts")
            memory.require_current(q, v, trial_id, control_index)
            count(cost, "same_trial_history_consistency_returns")
            previous_action = self.action_increment(memory.qprev, memory.requestprev, cost)
            current_action = self.action_increment(q, request, cost)
            with np.errstate(over="raise", invalid="raise"):
                count(cost, "causal_drift_pair_attempts")
                drift = finite("past_interval_remaining_velocity_increment2", (v-memory.vprev)-previous_action, (2,))
                count(cost, "causal_drift_pair_returns")
                next_v = finite("predicted_v2", v+drift+current_action, (2,))
                count(cost, "position_integration_pair_attempts")
                next_q = finite("predicted_q2", q+DT*next_v, (2,))
                count(cost, "position_integration_pair_returns")
            count(cost, "own_recursive_memory_build_attempts")
            next_memory = NativeIntervalMemory(trial_id, control_index, q, v, request, next_q, next_v)
            count(cost, "own_recursive_memory_build_returns")
        except BaseException:
            count(cost, "pair_prediction_exceptions")
            raise
        count(cost, "pair_prediction_returns")
        count(cost, "scalar_velocity_head_returns", 2)
        count(cost, "past_history_scalar_input_uses", 6)
        count(cost, "predicted_qv_scalar_outputs", 4)
        return next_q, next_v, next_memory, drift

    def record(self):
        return {"structure": "causal_incremental_action8", "dt_seconds": DT,
                "public_joint_ranges_rad": self.ranges.tolist(), "action8": self.action8.tolist(),
                "action_order": ["G0", "G1", "h0", "h1"], "guard_margin_rad": .03,
                "request_limit_nm": .5, "hinge_threshold_nm": .25, "integration": "endpoint_euler",
                "history": "previous_complete_same_trial_interval_start_qv_known_request",
                "drift": "(current_v-previous_v)-f_B(previous_q,previous_known_request)",
                "recursive_history": "own_current_qv_request_and_predicted_endpoint_only",
                "trainable": False, "physical_queries": 0, "state_head_used": False}

    def parameter_fingerprint(self):
        return hashlib.sha256(json.dumps(self.record(), sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def interval_memory(transition):
    return NativeIntervalMemory(transition["trial_id"], transition["control_index"],
                               transition["q"], transition["v"], transition["request"],
                               transition["next_q"], transition["next_v"])


class NativeCausalTraceStream:
    """Select final top-level records, requiring the entire native trial stream."""

    def __init__(self, seeds, trial_ids, qrefs, cost=None, total_count=3000, prefix_count=1000):
        if not seeds or len(set(seeds)) != len(seeds) or type(total_count) is not int or type(prefix_count) is not int or not 0 < prefix_count < total_count:
            raise ValueError("declared_complete_native_trial_dimensions_required")
        self.seeds, self.trial_ids = tuple(seeds), dict(trial_ids)
        self.qrefs = {seed: finite("source_qref2", qrefs[seed], (2,)).copy() for seed in seeds}
        self.cost, self.total_count, self.prefix_count = cost, total_count, prefix_count
        self.counts, self.previous = {seed: 0 for seed in seeds}, {}
        self.total = 0

    def accept(self, row):
        count(self.cost, "saved_native_selection_attempts")
        if not isinstance(row, dict) or row.get("kind") != "identification":
            raise ValueError("final_top_level_identification_record_required")
        seed, index = row.get("seed"), row.get("control_index")
        if self.total >= self.total_count*len(self.seeds) or seed != self.seeds[self.total//self.total_count]:
            raise ValueError("declared_trial_order_required_no_reordering")
        if type(index) is not int or index != self.counts[seed] or row.get("trial_id") != self.trial_ids[seed]:
            raise ValueError("exact_same_trial_indices_required_no_duplicate_missing_or_reordering")
        active = index-self.prefix_count
        stage = "prefix" if active < 0 else "A" if active < 1000 else "B"
        phase = "prefix" if active < 0 else "active"
        diagnostics = row.get("diagnostics", {})
        if (row.get("active_index") != active or row.get("stage") != stage or row.get("phase") != phase
                or row.get("returned") is not True or row.get("confirmed_physics_substeps") != 1
                or diagnostics.get("executed_substeps") != 1 or diagnostics.get("terminated") is not False
                or diagnostics.get("reason") is not None or row.get("stop") is not None or row.get("failure") is not None):
            raise ValueError("complete_unstopped_final_native_interval_required")
        before, after = row["observation_before"], row["observation_after"]
        q8, v8 = finite("source_native_before_q8", before["joint_position"], (8,)), finite("source_native_before_v8", before["joint_velocity"], (8,))
        next_q8, next_v8 = finite("source_native_after_q8", after["joint_position"], (8,)), finite("source_native_after_v8", after["joint_velocity"], (8,))
        request8 = finite("source_known_final_request8", row["requested_torque8"], (8,))
        count(self.cost, "saved_native_qv_scalar_reads", 32)
        count(self.cost, "saved_known_request_scalar_reads", 8)
        if np.any(np.abs(request8[:2]) > .5) or np.any(request8[2:] != 0.) or (active < 0 and np.any(request8 != 0.)):
            raise ValueError("original_pair_permission_other_six_zero_and_zero_prefix_required")
        if seed in self.previous:
            old_q8, old_v8 = self.previous[seed]
            count(self.cost, "saved_native_continuity_scalar_uses", 16)
            if q8.tobytes() != old_q8.tobytes() or v8.tobytes() != old_v8.tobytes():
                raise ValueError("complete_same_trial_native_qv_continuity_required")
        if active >= 0:
            if (np.any(np.abs(next_q8[:2]-self.qrefs[seed]) >= .12) or np.any(np.abs(next_v8[:2]) >= 1.)):
                raise ValueError("source_active_original_StudyAbort_must_remain_untriggered")
            target = finite("source_constant_fresh_target_q2", row["current_target_q2"], (2,))
            if target.tobytes() != self.qrefs[seed].tobytes():
                raise ValueError("original_constant_fresh_target_required")
        self.previous[seed] = (next_q8.copy(), next_v8.copy())
        self.counts[seed] += 1
        self.total += 1
        count(self.cost, "saved_native_selection_returns")
        return {"seed": seed, "trial_id": row["trial_id"], "control_index": index, "active_index": active,
                "stage": stage, "q": q8[:2].copy(), "v": v8[:2].copy(),
                "request": request8[:2].copy(), "next_q": next_q8[:2].copy(), "next_v": next_v8[:2].copy()}

    def finish(self):
        if any(value != self.total_count for value in self.counts.values()):
            raise ValueError("full_declared_source_trials_required_no_subset")
        return dict(self.counts)
