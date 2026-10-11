"""Six synthetic contract branches. Never call fit, solve, model or real trace."""
from collections import Counter
import copy
import gzip
import importlib.util
import json
from pathlib import Path
import unittest

import numpy as np

path = Path(__file__).with_name("develop_guard_imu_residual.py")
spec = importlib.util.spec_from_file_location("imu_residual_staging", path)
j = importlib.util.module_from_spec(spec)
spec.loader.exec_module(j)


def observation(v=0.):
    return {"joint_position": [0.]*8, "joint_velocity": [v]*8,
            "imu_gyro": [1., 2., 3.], "imu_acceleration": [9.81, 19.62, 29.43]}


def row(step, *, stopped=False, trial="seed0_zero", kind="zero"):
    return {"trial_id": trial, "seed": 0, "kind": kind, "step_index": step,
            "shared_transition_id": f"{trial}:{step}", "phase": "prefix" if step < 100 else "control",
            "observation_before": observation(), "observation_after": observation(),
            "requested_torque": [0.]*8, "study_abort": {"test": True} if stopped else None,
            "diagnostics": {"executed_substeps": 10, "terminated": False},
            "model_fingerprints": {"learned_sparse11": "synthetic"},
            "predicted_next_qv": {"learned_sparse11": [[0., 0.], [0., 0.]]},
            "model_input_diagnostics": {"learned_sparse11": {
                "native_q_rad": [0., 0.], "native_v_rad_s": [0., 0.], "requested_nm": [0., 0.],
                "previous_v_rad_s": [0., 0.], "history_transition_ids": [f"{trial}:{step-2}", f"{trial}:{step-1}"]}}}


def gate_groups(improvement=.20):
    return [{"collection": "C", "kind": "prediction", "seed": seed, "signal": "v", "axis": axis,
             "pair_count": 100, "source_active_count_ALL": 100, "rmse_relative_improvement": improvement,
             "base": {"rmse": 1.}, "corrected": {"rmse": 1.-improvement}}
            for seed in j.SEEDS for axis in (0, 1)]


class IMUBranches(unittest.TestCase):
    def test_all_six_columns_current_scaling_no_bias(self):
        phi = j.imu_feature(observation())
        np.testing.assert_allclose(phi, [1., 2., 3., 1., 2., 3.])
        self.assertEqual(phi.shape, (6,))
        self.assertEqual(phi.dtype, np.float64)

    def test_current_label_and_after_imu_do_not_change_features(self):
        past, current = [row(98), row(99)], row(100)
        first = j.extract_sample(current, past, "G")
        changed = copy.deepcopy(current)
        changed["observation_after"] = observation(8.)
        changed["observation_after"]["imu_gyro"] = [99., 98., 97.]
        second = j.extract_sample(changed, past, "G")
        self.assertEqual(first["phi"], second["phi"])
        self.assertNotEqual(first["actual_qv"], second["actual_qv"])

    def test_native_history_never_crosses_gaps_partial_trial_or_stop(self):
        for mode in ("gap", "partial", "trial", "stop", "missing_imu"):
            past, current = [row(98), row(99)], row(100)
            if mode == "gap":
                past[0]["step_index"] = 97
            elif mode == "partial":
                past[0]["diagnostics"]["executed_substeps"] = 9
            elif mode == "trial":
                past[0]["trial_id"] = "other_trial"
            elif mode == "stop":
                past[1]["study_abort"] = {"test": True}
            else:
                del current["observation_before"]["imu_gyro"]
            with self.assertRaises((ValueError, KeyError)):
                j.extract_sample(current, past, "G")
        with self.assertRaises(ValueError):
            j.extract_sample(row(100), [row(99)], "G")

    def test_fixed_parameter_forward_is_one_step_q_diagnostic_only(self):
        weights = np.zeros((6, 2))
        weights[0] = [2., -3.]
        cost = Counter()
        residual, corrected = j.apply_residual([[.1, .2], [.3, .4]], [1., 2., 3., 4., 5., 6.], weights, cost)
        self.assertEqual(residual, [2., -3.])
        np.testing.assert_allclose(corrected, [[.14, .14], [2.3, -2.6]])
        self.assertEqual(cost["residual_forward_scalar_heads"], 2)

    def test_main_gate_strict_each_seed_twenty_mean_and_full_count(self):
        self.assertTrue(j.development_gate(gate_groups())["passed"])
        for mode in ("worse_axis", "below_mean", "short", "undefined", "nonfinite"):
            groups = gate_groups()
            if mode == "worse_axis":
                groups[-1].update(rmse_relative_improvement=-.1, corrected={"rmse": 1.1})
            elif mode == "below_mean":
                groups = gate_groups(.19)
            elif mode == "short":
                groups[-1]["pair_count"] = 99
            elif mode == "undefined":
                groups[-1]["rmse_relative_improvement"] = None
            else:
                groups[-1]["rmse_relative_improvement"] = float("nan")
            self.assertFalse(j.development_gate(groups)["passed"])

    def test_saved_g_independent_reuse_keeps_terminal_and_rejects_after_stop(self):
        rows = [row(98), row(99), row(100), row(101, stopped=True), row(102)]
        blob = gzip.compress(b"".join((json.dumps(r)+"\n").encode() for r in rows))
        cost = Counter()
        samples, unavailable, counts = j.collect_samples(blob, "G", {0: "synthetic"}, cost)
        self.assertEqual([s["step_index"] for s in samples], [100, 101])
        self.assertTrue(samples[-1]["source_stopped_here"])
        self.assertEqual(cost["saved_base_prediction_reuses"], 2)
        self.assertEqual(unavailable[0]["reason"], "after_source_stop")
        self.assertEqual(counts["seed0_zero"], 3)
        described = j.summarize([], counts)
        self.assertTrue(all(g["pair_count"] == 0 and g["base"]["rmse"] is None for g in described))


if __name__ == "__main__":
    unittest.main()
