"""Small handwritten continuous-native fixtures; no saved C data or physics."""
from collections import defaultdict
import copy
import importlib.util
import io
import json
from pathlib import Path
import unittest

import numpy as np


from developmental_physics import guard_lag_offline_development as subject


ARTIFICIAL_COST = defaultdict(int)


def fixture(active=4, phase="control", kind="learned_sparse"):
    # Rows98/99 initialize genuine nonzero native history. No simulator/reset.
    q, v = (.1, -.1), (.03, -.02)
    rows = []
    for step in range(98, 100+active):
        before = {"joint_position": list(q), "joint_velocity": list(v)}
        u = (.1, -.1) if step >= 100 else (0., 0.)
        next_v = (v[0]+.001, v[1]-.002)
        next_q = tuple(q[i]+.02*next_v[i] for i in range(2))
        rows.append({"trial_id": f"seed0_{kind}", "seed": 0, "kind": kind, "step_index": step,
                     "shared_transition_id": f"seed0_{kind}:{step}", "phase": "prefix" if step < 100 else phase,
                     "observation_before": before, "observation_after": {"joint_position": list(next_q), "joint_velocity": list(next_v)},
                     "requested_torque": list(u), "diagnostics": {"executed_substeps": 10}, "study_abort": None,
                     "predicted_next_qv": {}, "model_fingerprints": {}, "model_input_diagnostics": {}})
        q, v = next_q, next_v
    return rows


class HandModel:
    """Explicit fake endpoint equation, never a research fit or helper test."""
    def __init__(self, *, lag=True, fail_call=None):
        self.lag, self.calls, self.fail_call = lag, [], fail_call
        self.update_count = 0
        self._features = lambda *args: [args[1][0], args[1][1]]

    def parameter_fingerprint(self):
        return "handwritten-frozen-identity" if self.update_count == 0 else f"handwritten-update-{self.update_count}"

    def snapshot(self):
        return {"parameter_fingerprint": self.parameter_fingerprint(), "vector_update_count": self.update_count,
                "coefficients": [[0.]*11, [0.]*11]}

    def _predict_state(self, q, v, u, previous_v=None, state=None):
        self._features(q, v, u, previous_v)
        self.calls.append({"q": tuple(q), "v": tuple(v), "previous_v": previous_v, "u": tuple(u)})
        if self.fail_call == len(self.calls):
            error = ValueError("deliberate handcrafted pair failure")
            error.pair_prediction_accounting = {"scalar_prediction_attempts": 1, "scalar_prediction_successes": 0}
            raise error
        increment = tuple(v[i]-previous_v[i] for i in range(2)) if self.lag else (.001, -.002)
        next_v = tuple(v[i]+increment[i] for i in range(2))
        return tuple(q[i]+.02*next_v[i] for i in range(2)), next_v

    def predict(self, q, v, u, previous_v=None):
        return self._predict_state(q, v, u, previous_v)

    def _propose_update(self, index, *args):
        return {"index": index, "handcrafted_proposal": True}

    def update(self, q, v, u, next_v, previous_v, *, transition_id):
        self._features(q, v, u, previous_v)
        pre = self._predict_state(q, v, u, previous_v)
        proposals = [self._propose_update(i) for i in range(2)]
        self.update_count += 1
        return {"shared_transition_id": transition_id, "preupdate_prediction": {"next_q_rad": pre[0], "next_v_rad_s": pre[1]},
                "output_records": proposals, "committed_scalar_updates": 2}

    def clone_frozen(self):
        clone = HandModel(lag=self.lag)
        clone.update_count = self.update_count
        return clone


class OfflineEngineeringTests(unittest.TestCase):
    def test_native_prefix_and_discontinuity_no_zero_history(self):
        rows = fixture()
        intervals, unavailable = subject.native_intervals(rows, phase="control")
        self.assertEqual(len(intervals), 4)
        self.assertFalse(unavailable)
        self.assertEqual(intervals[0]["previous_v"], tuple(rows[0]["observation_after"]["joint_velocity"]))
        self.assertEqual(intervals[0]["v"], tuple(rows[1]["observation_after"]["joint_velocity"]))
        self.assertNotEqual(intervals[0]["previous_v"], (0., 0.))
        broken = copy.deepcopy(rows)
        broken[1]["diagnostics"]["executed_substeps"] = 9
        rejected, missing = subject.native_intervals(broken, phase="control")
        self.assertNotIn(100, [x["row"]["step_index"] for x in rejected])
        self.assertTrue(missing)

    def test_shared_windows_stop_and_long_h_unavailable(self):
        rows = fixture()
        rows[-1]["study_abort"] = {"reason": "handcrafted_stop"}
        intervals, _ = subject.native_intervals(rows, phase="control")
        actual = subject.windows(intervals)
        self.assertEqual([sum(h in x["available_horizons"] for x in actual) for h in subject.HORIZONS], [4, 3, 0, 0])
        after_stop = fixture(active=8)[6:]
        intervals2, missing = subject.native_intervals(rows+after_stop, phase="control")
        self.assertEqual(len(intervals2), 4)
        self.assertEqual([x["reason"] for x in missing], ["after_source_stop"]*4)

    def test_once_rollout_own_predicted_history(self):
        intervals, _ = subject.native_intervals(fixture(active=16), phase="control")
        model = HandModel()
        local = defaultdict(int)
        subject.instrument_evaluation_model(model, local)
        record = subject.rollout(subject.windows(intervals)[0], "lag_sparse11", model, ((-1., 1.), (-1., 1.)), {}, local)
        self.assertEqual(len(record["steps"]), 15)
        self.assertEqual(local["evaluation_pair_attempts"], 15)
        self.assertEqual(local["evaluation_scalar_attempts"], 30)
        self.assertEqual(local["evaluation_model_feature_pair_successes"], 15)
        for i in range(1, 15):
            self.assertEqual(record["steps"][i]["input"]["previous_v"], record["steps"][i-1]["input"]["v"])
            self.assertEqual(record["steps"][i]["input"]["q"], record["steps"][i-1]["prediction"]["q"])
        ARTIFICIAL_COST.update({k: ARTIFICIAL_COST[k]+v for k, v in local.items()})

    def test_saved_one_step_exact_binding_reuse_no_prediction(self):
        intervals, _ = subject.native_intervals(fixture(active=1), phase="control")
        item, model = intervals[0], HandModel(lag=False)
        row = item["row"]
        expected_q, expected_v = tuple(row["observation_after"]["joint_position"]), tuple(row["observation_after"]["joint_velocity"])
        row["predicted_next_qv"]["learned_sparse"] = [expected_q, expected_v]
        row["model_input_diagnostics"]["learned_sparse"] = {"native_q_rad": item["q"], "requested_nm": item["u"],
            "model_feature_command_nm": item["u"], "projected_start_nm": item["u"], "input_basis": "known_angle_guard"}
        bound = {"model_fingerprint_before": model.parameter_fingerprint(), "model_fingerprint_after": model.parameter_fingerprint()}
        local = defaultdict(int)
        record = subject.rollout(subject.windows(intervals)[0], "sparse9", model, ((-1., 1.), (-1., 1.)), bound, local)
        self.assertEqual(local["reused_saved_pair_predictions"], 1)
        self.assertEqual(len(model.calls), 0)
        self.assertEqual(record["steps"][0]["prediction"]["v"], expected_v)
        row["model_input_diagnostics"]["learned_sparse"]["requested_nm"] = (.2, -.1)
        self.assertIsNone(subject.saved_one_step(item, "sparse9", model, bound))
        ARTIFICIAL_COST.update({k: ARTIFICIAL_COST[k]+v for k, v in local.items()})

    def test_invalid_saved_prediction_retains_window_without_new_predict(self):
        intervals, _ = subject.native_intervals(fixture(active=1), phase="control")
        item, model = intervals[0], HandModel(lag=False)
        row = item["row"]
        row["predicted_next_qv"]["learned_sparse"] = [[.1, .2], [float("nan"), .2]]
        row["model_input_diagnostics"]["learned_sparse"] = {"native_q_rad": item["q"], "requested_nm": item["u"],
            "model_feature_command_nm": item["u"], "projected_start_nm": item["u"], "input_basis": "known_angle_guard"}
        bound = {"model_fingerprint_before": model.parameter_fingerprint(), "model_fingerprint_after": model.parameter_fingerprint()}
        local = defaultdict(int)
        record = subject.rollout(subject.windows(intervals)[0], "sparse9", model, ((-1., 1.), (-1., 1.)), bound, local)
        self.assertEqual(record["failure"]["at_h"], 1)
        self.assertEqual(record["failure"]["failure_stage"], "saved_prediction_validation")
        self.assertEqual(local["saved_prediction_validation_failures"], 1)
        self.assertEqual(local["evaluation_pair_attempts"], 0)
        self.assertEqual(model.calls, [])
        ARTIFICIAL_COST.update({k: ARTIFICIAL_COST[k]+v for k, v in local.items()})

    def test_numerical_failure_not_dropped_and_calibration_remaining_cost(self):
        intervals, _ = subject.native_intervals(fixture(active=4), phase="control")
        actual = subject.windows(intervals)
        local = defaultdict(int)
        model = HandModel(fail_call=2)
        record = subject.rollout(actual[0], "lag_sparse11", model, ((-1., 1.), (-1., 1.)), {}, local)
        self.assertEqual(record["failure"]["at_h"], 2)
        self.assertEqual(local["evaluation_pair_failures"], 1)
        self.assertEqual(local["evaluation_scalar_attempts"], 3)
        # Supply one record for every common origin for this predictor.
        records = [record]+[subject.rollout(w, "lag_sparse11", HandModel(), ((-1., 1.), (-1., 1.)), {}, local) for w in actual[1:]]
        values = subject.metrics(records, actual, ((-1., 1.), (-1., 1.)), local)
        h2 = next(x for x in values if x["predictor"] == "lag_sparse11" and x["h"] == 2 and x["axis"] == 0 and x["group"] == "all")
        self.assertEqual(h2["complete_window_count"], 3)
        self.assertEqual(h2["mathematical_failure_count"], 1)
        self.assertFalse(h2["available"])
        self.assertIsNone(h2["v"])
        cal_rows = fixture(active=3, phase="calibration", kind="calibration_sparse")
        cal, _ = subject.native_intervals(cal_rows, phase="calibration")
        writer = io.StringIO()
        fitted = subject.fit_calibration(HandModel(fail_call=2), cal, writer, local, expected_count=3)
        self.assertFalse(fitted["completed"])
        self.assertEqual(fitted["attempted_vector_updates"], 2)
        self.assertEqual(fitted["unexecuted_planned_updates"], 1)
        self.assertEqual(fitted["remaining_uncommitted_updates"], 2)
        self.assertEqual(len(writer.getvalue().splitlines()), 2)
        self.assertEqual(local["offline_scalar_updates_committed"], 2)
        ARTIFICIAL_COST.update({k: ARTIFICIAL_COST[k]+v for k, v in local.items()})

    def test_design_normalization_modal_matrix_and_staging_refusal(self):
        local = defaultdict(int)
        matrix = [[0., 1., 1.], [1., 1., 1.], [2., 1., 1.], [3., 1., 1.]]
        design = subject.design_diagnostics(matrix, ("varying", "constant_one", "bias"), local)
        self.assertEqual(design["numerical_rank"], 2)
        self.assertEqual(design["standardized_design_condition"], float("inf"))
        self.assertAlmostEqual(design["standardized_gram"][0, 0], 1.)
        self.assertEqual(design["coefficient_column_scale"][2], 1.)
        theta = np.zeros((2, 11))
        theta[0, 0], theta[1, 1] = 1., 1.
        theta[:, 9:11] = [[.1, .2], [.3, .4]]
        modal = subject.modal_diagnostics(theta, True, local)
        self.assertTrue(np.array_equal(modal["matrix"][4:6, 2:4], np.eye(2)))
        self.assertTrue(np.array_equal(modal["matrix"][2:4, 4:6], -theta[:, 9:11]))
        if not subject.FORMAL_OFFLINE_ENABLED:
            with self.assertRaisesRegex(RuntimeError, "not authorized"):
                subject.run_single_lag_offline("unused", source_root="unused", protocol_path="unused", source_freeze_path="unused", execution_context={})
        ARTIFICIAL_COST.update({k: ARTIFICIAL_COST[k]+v for k, v in local.items()})


if __name__ == "__main__":
    unittest.main()
