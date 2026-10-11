"""Small synthetic branches only: no H read or formal diagnostic execution."""
import copy
import importlib.util
from pathlib import Path
import unittest


path = Path(__file__).with_name("diagnose_guard_pd_tail_native_residual.py")
spec = importlib.util.spec_from_file_location("native_residual_staging", path)
diagnostic = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diagnostic)


def row(active, residual=(1., 2.), *, trial="seed0_learned_sparse11"):
    return {"trial_id": trial, "step_index": 100+active, "active_index": active,
            "actual_next_qv": [[.03, .06], list(residual)],
            "interval_effort": {"executed_substeps": 10, "complete_20ms_interval": True},
            "independent_current_request_prediction": {
                "prediction_available": True, "saved_prediction_qv": [[0., 0.], [0., 0.]]}}


class CausalResidualBranches(unittest.TestCase):
    def test_first_record_is_history_only_and_q_scale_is_point_zero_two(self):
        pairs, unscored, cost = diagnostic.score_records([row(0), row(1)])
        self.assertEqual(len(pairs), 1)
        self.assertEqual(unscored[0]["reason"], "no_valid_window_history")
        self.assertEqual(pairs[0]["corrected_prediction_qv"], [[.02, .04], [1., 2.]])
        self.assertEqual(cost["bias_state_scalar_calculations"], 4)

    def test_bias_never_uses_previous_corrected_error(self):
        pairs, _, _ = diagnostic.score_records([row(0, (1., 1.)), row(1, (3., 3.)), row(2, (5., 5.))])
        self.assertEqual(pairs[1]["previous_original_base_velocity_residual"], [3., 3.])
        self.assertEqual(pairs[1]["corrected_prediction_qv"][1], [3., 3.])
        self.assertEqual(pairs[1]["signed_actual_minus_prediction_qv"]["corrected"][1], [2., 2.])

    def test_current_actual_cannot_change_current_corrected_prediction(self):
        first = row(0)
        current = row(1, (3., 4.))
        pairs1, _, _ = diagnostic.score_records([first, current])
        changed = copy.deepcopy(current)
        changed["actual_next_qv"] = [[100., 200.], [-30., 40.]]
        pairs2, _, _ = diagnostic.score_records([first, changed])
        self.assertEqual(pairs1[0]["corrected_prediction_qv"], pairs2[0]["corrected_prediction_qv"])

    def test_partial_and_missing_break_history(self):
        for missing in ("partial", "prediction", "actual"):
            bad = row(1)
            if missing == "partial":
                bad["interval_effort"]["executed_substeps"] = 9
            elif missing == "prediction":
                bad["independent_current_request_prediction"]["prediction_available"] = False
            else:
                bad["actual_next_qv"] = None
            pairs, unscored, _ = diagnostic.score_records([row(0), bad, row(2), row(3)])
            self.assertEqual(len(pairs), 1)
            self.assertEqual(pairs[0]["previous_active_index"], 2)
            self.assertEqual(len(unscored), 3)

    def test_noncontiguous_does_not_repair_history(self):
        pairs, unscored, _ = diagnostic.score_records([row(0), row(2), row(3)])
        self.assertEqual(len(pairs), 1)
        self.assertEqual(unscored[1]["reason"], "noncontiguous_history")
        self.assertEqual(pairs[0]["previous_active_index"], 2)
        pairs, _, _ = diagnostic.score_records([row(0), row(1, trial="seed1_learned_sparse11")])
        self.assertEqual(pairs, [])

    def test_cross_segment_is_b_and_separately_counted(self):
        pairs, _, _ = diagnostic.score_records([row(99), row(100)])
        groups, gates, _ = diagnostic.summarize_pairs(pairs)
        counts = {g["segment"]: g["pair_count"] for g in groups
                  if g["trial_id"] == "seed0_learned_sparse11" and g["signal"] == "v" and g["axis"] == 0}
        self.assertEqual(counts, {"ALL": 1, "A": 0, "B": 1, "CROSS_A_TO_B": 1})
        self.assertFalse(gates["learned_sparse11"]["passed"])

    def test_zero_baseline_and_empty_are_not_success(self):
        pairs, _, _ = diagnostic.score_records([row(0, (0., 0.)), row(1, (0., 0.))])
        groups, gates, _ = diagnostic.summarize_pairs(pairs)
        self.assertFalse(gates["learned_sparse11"]["evaluated"])
        self.assertFalse(gates["learned_sparse11"]["passed"])
        self.assertIsNone(next(g for g in groups if g["segment"] == "ALL" and g["signal"] == "v")["rmse_relative_improvement"])

    def test_primary_gate_requires_every_seed_axis_and_mean_twenty_percent(self):
        rows = [record for seed in (0, 1, 2) for record in
                (row(0, (1., 1.), trial=f"seed{seed}_learned_sparse11"),
                 row(1, (2., 2.), trial=f"seed{seed}_learned_sparse11"))]
        pairs, _, _ = diagnostic.score_records(rows)
        _, gates, _ = diagnostic.summarize_pairs(pairs)
        self.assertTrue(gates["learned_sparse11"]["passed"])
        rows[-1]["actual_next_qv"][1][1] = .1
        pairs, _, _ = diagnostic.score_records(rows)
        _, gates, _ = diagnostic.summarize_pairs(pairs)
        self.assertFalse(gates["learned_sparse11"]["passed"])


if __name__ == "__main__":
    unittest.main()
