"""Bounded checks of experiment information flow, accounting and failure logs."""

import csv
import gzip
import hashlib
import json
import zipfile

import numpy as np
import pytest

from developmental_control import history
from developmental_control.history import ControllerSpec, HistoryConfig, HistoryScenario, run_history
from developmental_control.joints import JointParameters
from developmental_control.stress import StressScenario, write_outputs


def test_history_factorial_keeps_priors_fixed_through_hidden_delay_jump(monkeypatch):
    assumed = []
    original = history.HistoryCandidatePlanner.plan

    def capture(self, observation, target, permission, previous_action, command_history):
        assumed.append((self.history_config.assumed_delay_steps,
                        self.history_config.effective_delay_steps, len(command_history)))
        return original(self, observation, target, permission, previous_action, command_history)

    monkeypatch.setattr(history.HistoryCandidatePlanner, "plan", capture)
    config = HistoryConfig(seeds=(10,), rollout_steps=6, window_steps=1)
    scenario = HistoryScenario(StressScenario("jump", JointParameters(delay_steps=1),
                                            JointParameters(delay_steps=3), 3), 1)
    controller = ControllerSpec("history_h50", 50, True)
    report, trace = run_history(config, (scenario,), (controller,))
    assert assumed == [(1, 1, step) for step in range(6)]
    assert [row["true_delay_steps"] for row in trace] == [1, 1, 1, 3, 3, 3]
    assert [row["assumed_delay_steps"] for row in trace] == [1] * 6
    assert [row["applied_command_step"] for row in trace] == [None, 0, 1, 0, 1, 2]
    assert [row["assumed_applied_command_step"] for row in trace] == [None, 0, 1, 2, 3, 4]
    assert report["delay_parameter_updates"] == 0
    assert report["records"][0]["phases"]["post_change"]["executed_steps"] == 3


def test_small_matrix_records_equal_initial_conditions_and_exact_budgets():
    config = HistoryConfig(seeds=(10, 11), rollout_steps=4, window_steps=1)
    report, trace = run_history(config, (HistoryScenario(StressScenario("nominal")),))
    assert len(report["records"]) == 10
    assert report["planned_interaction_steps"] == report["total_executed_steps"] == len(trace) == 40
    assert report["diagnostic_one_step_model_predictions"] == 120
    assert report["total_planner_model_transitions"] == 2 * 4 * 49 * (20 + 50 + 20 + 50)
    assert report["model_fingerprint_before"] == report["model_fingerprint_after"]
    assert report["fixed_parameters_before"] == report["fixed_parameters_after"]
    assert report["model_parameter_updates"] == report["policy_parameter_updates"] == 0
    for seed in config.seeds:
        records = [row for row in report["records"] if row["seed"] == seed]
        assert all(row["initial_state"] == records[0]["initial_state"] for row in records)
    for pair in report["paired_comparisons"]:
        assert pair["common_executed_steps"] == 4
        if pair["left"].replace("immediate", "history") == pair["right"]:
            assert pair["identical_common_state_and_commands"]
    assert not any(row["command_limit_violation"] for row in trace)
    json.dumps(report, allow_nan=False)


def test_applied_label_residual_is_offline_and_keeps_unknown_gain_mismatch():
    config = HistoryConfig(seeds=(10,), rollout_steps=4, window_steps=1)
    scenario = HistoryScenario(StressScenario("weak", after=JointParameters(actuator_gain=(0.125, 0.125)), change_step=2))
    report, trace = run_history(config, (scenario,), (ControllerSpec("history_h20", 20, True),))
    assert all(row["prediction_rmse"] == row["immediate_prediction_rmse"] == row["applied_label_prediction_rmse"]
               for row in trace)
    assert any(row["applied_label_prediction_rmse"] > 0 for row in trace[2:])
    params = report["records"][0]["controller_parameters"]["model"]["parameters"]
    assert params["actuator_gain"] == (1.0, 1.0)
    assert report["records"][0]["fixed_parameters_before"] == report["records"][0]["fixed_parameters_after"]


@pytest.mark.parametrize("nonfinite", [False, True])
def test_exits_keep_all_methods_and_missing_phases(monkeypatch, nonfinite):
    original = history.StressPlant.step

    def fail(self, command, external_torque=None):
        original(self, command, external_torque)
        return np.full(4, np.nan) if nonfinite else np.array([0.4, 0, 0, 0])

    monkeypatch.setattr(history.StressPlant, "step", fail)
    config = HistoryConfig(seeds=(10,), rollout_steps=4, window_steps=1)
    scenario = HistoryScenario(StressScenario("change", after=JointParameters(delay_steps=1), change_step=2))
    report, trace = run_history(config, (scenario,))
    assert len(report["records"]) == len(trace) == 5
    for row in report["records"]:
        assert row["exit_step"] == 1
        assert row["phases"]["post_change"] is None
        assert row["audit_halves"]["second225"] is None
        assert row["termination_reason"] == ("nonfinite_state" if nonfinite else "state_limit")
        if nonfinite:
            assert row["full_target_rmse"] is None
    json.dumps(report, allow_nan=False)


def test_history_archive_sources_and_csv_match_report(tmp_path):
    config = HistoryConfig(seeds=(10,), rollout_steps=2, window_steps=1)
    report, trace = run_history(config, (HistoryScenario(StressScenario("nominal")),), (ControllerSpec("pd", 20, False, "pd"),))
    write_outputs(tmp_path, report, trace, [])
    with gzip.open(tmp_path / "trace.csv.gz", "rt", encoding="utf-8", newline="") as handle:
        assert len(list(csv.DictReader(handle))) == report["total_executed_steps"]
    with zipfile.ZipFile(tmp_path / "source_snapshot.zip") as archive:
        for name, digest in report["source_sha256"].items():
            assert hashlib.sha256(archive.read(name)).hexdigest() == digest
    assert json.loads((tmp_path / "gates.json").read_text(encoding="utf-8")) == []


def test_invalid_or_duplicate_designs_do_not_execute():
    with pytest.raises(ValueError, match="nonnegative"):
        HistoryScenario(StressScenario("nominal"), -1)
    config = HistoryConfig(seeds=(10,), rollout_steps=4, window_steps=2)
    scenario = HistoryScenario(StressScenario("bad", after=JointParameters(delay_steps=2), change_step=3))
    with pytest.raises(ValueError, match="boundary"):
        run_history(config, (scenario,))
    nominal = HistoryScenario(StressScenario("nominal"))
    with pytest.raises(ValueError, match="unique"):
        run_history(config, (nominal, nominal))


def test_main_rejects_nonempty_output_before_running(monkeypatch, tmp_path):
    (tmp_path / "report.json").write_text("keep me", encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["history", "--output", str(tmp_path)])
    monkeypatch.setattr(history, "run_history", lambda: pytest.fail("must not run before overwrite check"))
    with pytest.raises(FileExistsError, match="refusing"):
        history.main()
    assert (tmp_path / "report.json").read_text(encoding="utf-8") == "keep me"
