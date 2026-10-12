"""IV2: fixed action heads, one native state-head consistency fit.

The data selector accepts only complete top-level IV1 identification rows.
Neither selection nor model math imports a physical backend.
"""
from __future__ import annotations

import numpy as np

from .instrumental_action_model import (
    InstrumentalActionBodyModel, NONACTION, RCOND, action_features, count, finite,
)


def identification_transition(row):
    """Exclude nested paid copies, annotations, prefixes and evaluation labels."""
    if not isinstance(row, dict):
        raise ValueError("saved_trace_row_must_be_object")
    if row.get("kind") != "identification" or row.get("phase") != "active":
        return None
    seed, index = row.get("seed"), row.get("active_index")
    if (type(seed) is not int or type(index) is not int or not 0 <= index < 2000
        or row.get("control_index") != 1000+index or row.get("trial_id") != f"s{seed}_identification"
        or row.get("stage") != ("A" if index < 1000 else "B") or row.get("returned") is not True
        or row.get("confirmed_physics_substeps") != 1 or row.get("failure") is not None
        or row.get("stop") is not None or row.get("diagnostics", {}).get("executed_substeps") != 1):
        raise ValueError("only_complete_declared_identification_transition_required")
    def native_pair(observation):
        q = finite("saved_native_q8", observation["joint_position"], (8,))
        v = finite("saved_native_v8", observation["joint_velocity"], (8,))
        return q[:2].copy(), v[:2].copy()
    q, v = native_pair(row["observation_before"])
    next_q, next_v = native_pair(row["observation_after"])
    request = finite("saved_known_request8", row["requested_torque8"], (8,))
    if np.any(np.abs(request[:2]) > .5) or np.any(request[2:] != 0.):
        raise ValueError("original_pair_permission_and_other_six_zero_required")
    return {"seed": seed, "index": index, "q": q, "v": v, "next_q": next_q,
            "next_v": next_v, "request": request[:2].copy()}


class NativeIdentificationStream:
    """Exactly ordered native transitions; never silently deduplicate."""
    def __init__(self, seeds=(8101, 8102, 8103), active_count=2000, cost=None):
        if not seeds or len(set(seeds)) != len(seeds) or type(active_count) is not int or not 0 < active_count <= 2000:
            raise ValueError("fixed_unique_seeds_and_positive_declared_count_required")
        self.seeds, self.active_count, self.cost = tuple(seeds), active_count, cost
        self.counts, self.previous = {seed: 0 for seed in seeds}, {}

    def accept(self, row):
        count(self.cost, "saved_trace_selection_attempts")
        selected = identification_transition(row)
        if selected is None:
            count(self.cost, "saved_trace_nontraining_rows_skipped")
            return None
        seed, index = selected["seed"], selected["index"]
        if seed not in self.counts or index != self.counts[seed] or index >= self.active_count:
            raise ValueError("exact_identification_indices_no_duplicate_missing_or_reordering")
        if seed in self.previous:
            last_q, last_v = self.previous[seed]
            if selected["q"].tobytes() != last_q.tobytes() or selected["v"].tobytes() != last_v.tobytes():
                raise ValueError("same_trial_native_endpoints_not_exactly_continuous")
        self.previous[seed] = (selected["next_q"].copy(), selected["next_v"].copy())
        self.counts[seed] += 1
        count(self.cost, "saved_identification_transition_returns")
        count(self.cost, "saved_native_continuity_scalar_uses", 8)
        return selected

    def finish(self):
        if any(value != self.active_count for value in self.counts.values()):
            raise ValueError("complete_fixed_identification_population_required")
        return dict(self.counts)


class StateConsistencyFit:
    """An ordinary least-squares state fit conditional on immutable IV1 action."""
    def __init__(self, frozen_model, cost=None):
        self.model, self.cost = frozen_model, cost
        self.psi, self.labels = [], []
        self.fit_attempted, self.fit_record = False, None
        self.action_bytes_before = frozen_model.theta[:, 4:8].tobytes()

    @property
    def samples(self):
        return len(self.psi)

    def add(self, q, v, request, next_v):
        if self.fit_attempted:
            raise ValueError("no_labels_after_first_state_fit_attempt")
        count(self.cost, "state_design_row_attempts")
        q, v = finite("current_native_q2", q, (2,)), finite("current_native_v2", v, (2,))
        next_v = finite("reused_native_next_v2", next_v, (2,))
        count(self.cost, "reused_state_fit_scalar_label_uses", 2)
        phi, _ = action_features(q, request, self.model.ranges, self.cost)
        count(self.cost, "frozen_action_matvec_attempts")
        with np.errstate(over="raise", invalid="raise"):
            psi = finite("state_psi5", [*v, *(q-self.model.qref), 1.], (5,))
            action = finite("frozen_IV1_action_v2", self.model.theta[:, 4:8] @ phi, (2,))
            label = finite("native_label_minus_fixed_action", next_v-action, (2,))
        self.psi.append(psi.copy())
        self.labels.append(label.copy())
        count(self.cost, "frozen_action_matvec_returns")
        count(self.cost, "frozen_action_coefficient_scalar_uses", 8)
        count(self.cost, "state_design_scalar_outputs", 7)
        count(self.cost, "state_design_row_returns")
        return {"psi5": psi, "fixed_action_v2": action, "native_next_v2": next_v, "state_label_v2": label}

    def fit_once(self):
        if self.fit_attempted:
            raise ValueError("state_first_fit_only_no_retry")
        self.fit_attempted = True
        count(self.cost, "state_fit_attempts")
        try:
            psi = finite("full_state_design", self.psi, (self.samples, 5))
            labels = finite("full_state_labels", self.labels, (self.samples, 2))
            count(self.cost, "state_lstsq_attempts")
            try:
                solution, residuals, rank, singular = np.linalg.lstsq(psi, labels, rcond=RCOND)
            except BaseException:
                count(self.cost, "state_lstsq_exceptions")
                raise
            count(self.cost, "state_lstsq_returns")
            self.fit_record = {"solution_5x2": solution.tolist(), "lstsq_residuals": residuals.tolist(),
                "rank": int(rank), "singular_values": singular.tolist(), "rcond": RCOND, "samples": self.samples}
            solution = finite("state_solution_5x2", solution, (5, 2))
            if rank != 5 or not np.isfinite(residuals).all() or not np.isfinite(singular).all():
                raise ValueError("finite_full_rank5_state_fit_required_no_rank_completion")
            theta = self.model.theta.copy()
            theta[:, NONACTION] = solution.T
            if theta[:, 4:8].tobytes() != self.action_bytes_before:
                raise ValueError("frozen_IV1_action_coefficients_changed")
            matched = InstrumentalActionBodyModel(self.model.qref, self.model.ranges, theta)
            count(self.cost, "state_fitted_coefficient_scalar_outputs", 10)
            count(self.cost, "state_fit_returns")
            return matched
        except BaseException:
            count(self.cost, "state_fit_exceptions")
            raise

    def record(self):
        return {"Psi_native_state_5": [row.tolist() for row in self.psi],
            "Y_native_minus_fixed_action_2": [row.tolist() for row in self.labels],
            "samples": self.samples, "fit_attempted": self.fit_attempted, "fit": self.fit_record,
            "state_columns_replaced": list(NONACTION), "action_columns_frozen": [4, 5, 6, 7],
            "fixed_action_2x4": self.model.theta[:, 4:8].tolist(),
            "fixed_action_float64_bytes_hex": self.action_bytes_before.hex(),
            "initial_IV1_fingerprint": self.model.parameter_fingerprint()}
