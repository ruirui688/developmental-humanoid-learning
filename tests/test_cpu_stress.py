from dataclasses import FrozenInstanceError
import csv
import gzip
import hashlib
import json
import zipfile

import numpy as np
import pytest

from developmental_control.joints import FixedBodyModel, JointParameters, advance
from developmental_control import stress
from developmental_control.stress import StressConfig, StressPlant, StressScenario, run_stress, write_outputs


def test_dynamic_delay_uses_permanent_command_history_without_reset():
    scenario = StressScenario("delay", after=JointParameters(delay_steps=2), change_step=3)
    plant = StressPlant(scenario, [0.01, -0.02, 0.003, -0.004])
    commands = [np.array([0.1 * index, -0.05 * index]) for index in range(6)]
    expected_state = plant.observation
    expected_source_steps = [0, 1, 2, 1, 2, 3]
    for step, command in enumerate(commands):
        expected_applied = commands[expected_source_steps[step]]
        expected_state = advance(expected_state, expected_applied, scenario.parameters_at(step), plant.dt)
        np.testing.assert_allclose(plant.step(command), expected_state)
        np.testing.assert_array_equal(plant.applied_command, expected_applied)
        assert plant.applied_command_step == expected_source_steps[step]
        assert plant.executed_steps == step + 1
    assert len(plant.commands) == 6
    command_copy = plant.commands[-1].copy()
    commands[-1][:] = 9
    np.testing.assert_array_equal(plant.commands[-1], command_copy)
    observation = plant.observation
    observation[:] = 42
    assert np.max(plant.observation) < 1


def test_negative_delay_history_is_zero_then_first_command_is_applied():
    plant = StressPlant(StressScenario("delay", JointParameters(delay_steps=2)), np.zeros(4))
    for step in range(2):
        np.testing.assert_array_equal(plant.step([0.3, -0.2]), np.zeros(4))
        assert plant.applied_command_step is None
    plant.step([0.0, 0.0])
    np.testing.assert_array_equal(plant.applied_command, [0.3, -0.2])
    assert plant.applied_command_step == 0


def test_parameter_jump_preserves_state_and_effective_torque_is_not_clipped():
    scenario = StressScenario("gain", after=JointParameters(actuator_gain=(4.0, 4.0)), change_step=2)
    plant = StressPlant(scenario, np.zeros(4))
    plant.step([1.0, -1.0])
    before = plant.step([1.0, -1.0])
    expected = advance(before, [1.0, -1.0], scenario.after, plant.dt)
    np.testing.assert_allclose(plant.step([1.0, -1.0]), expected)
    np.testing.assert_array_equal(plant.effective_torque, [4.0, -4.0])
    assert plant.executed_steps == 3


def test_stress_reports_aligned_window_phases_and_exact_interaction_budget():
    config = StressConfig(seeds=(10,), rollout_steps=50, window_steps=5, fixed_stage_steps=15)
    scenario = StressScenario("jump", after=JointParameters(actuator_gain=(0.25, 0.25)), change_step=25)
    report, trace, gates = run_stress(config, scenarios=(scenario,))
    assert len(report["records"]) == 6
    assert report["planned_interaction_steps"] == report["total_executed_steps"] == len(trace) == 300
    assert report["model_parameter_updates"] == report["policy_parameter_updates"] == 0
    assert report["model_fingerprint_before"] == report["model_fingerprint_after"]
    assert report["fixed_parameters_before"] == report["fixed_parameters_after"]
    assert report["config"]["sustained_failure_windows"] == 3
    for record in report["records"]:
        assert record["initial_state"] == report["records"][0]["initial_state"]
        assert record["gate_parameter_fingerprint_before"] == record["gate_parameter_fingerprint_after"]
        assert record["phases"]["pre_change"]["executed_steps"] == 25
        assert record["phases"]["post_change"]["executed_steps"] == 25
        assert record["termination_reason"] == "completed"
        if record["mode"] in ("zero", "pd", "full"):
            assert record["permission_limit_joint_seconds"] == pytest.approx(50 * 2 * config.dt)
            assert record["phases"]["post_change"]["permission_limit_joint_seconds"] == pytest.approx(25 * 2 * config.dt)
        windows = record["windows"]
        assert len(windows) == 10
        assert [(window["start_step"], window["end_step_exclusive"]) for window in windows] == [(step, step + 5) for step in range(0, 50, 5)]
        assert windows[4]["phase"] == "pre_change" and windows[5]["phase"] == "post_change"
        assert windows[5]["completed_steps_at_detection"] == 30
        if record["first_post_change_failure_observed_step"] is not None:
            assert record["first_post_change_failure_latency_steps"] == record["first_post_change_failure_observed_step"] - 25
    for event in gates:
        assert event["decision_effective_command_step"] == event["end_step_exclusive"]
    assert not any(row["command_limit_violation"] for row in trace)
    json.dumps(report, allow_nan=False)


def test_safe_exit_precedes_gate_even_for_complete_terminal_window(monkeypatch):
    original = StressPlant.step

    def unsafe_step(self, command, external_torque=None):
        original(self, command, external_torque)
        return np.array([0.4, 0.0, 0.0, 0.0])

    monkeypatch.setattr(StressPlant, "step", unsafe_step)
    config = StressConfig(seeds=(10,), rollout_steps=3, window_steps=1, fixed_stage_steps=1)
    report, trace, gates = run_stress(config, scenarios=(StressScenario("nominal"),))
    assert len(trace) == report["total_executed_steps"] == 6
    assert not gates
    for record in report["records"]:
        assert record["termination_reason"] == "state_limit"
        assert record["gate_retreats"] == record["gate_observed_windows"] == 0
        assert record["complete_evidence_windows"] == 1
        assert record["windows"][0]["reason"] == "independent_safety_exit"


def test_nonfinite_outputs_keep_all_trials_and_partial_window_evidence(monkeypatch):
    original = StressPlant.step

    def broken_step(self, command, external_torque=None):
        original(self, command, external_torque)
        return np.full(4, np.nan)

    monkeypatch.setattr(StressPlant, "step", broken_step)
    config = StressConfig(seeds=(10,), rollout_steps=5, window_steps=5, fixed_stage_steps=5)
    report, trace, gates = run_stress(config, scenarios=(StressScenario("nominal"),))
    assert len(report["records"]) == 6
    assert report["total_executed_steps"] == len(trace) == 6
    assert not gates
    for record in report["records"]:
        assert record["termination_reason"] == "nonfinite_state"
        assert record["full_target_rmse"] is None
        assert record["terminal_partial_window_steps"] == 1
        assert record["windows"][0]["failures"] == ["nonfinite_state"]
    json.dumps(report, allow_nan=False)


def test_post_change_partial_failure_has_no_complete_window_detection(monkeypatch):
    original = StressPlant.step

    def fail_after_change(self, command, external_torque=None):
        state = original(self, command, external_torque)
        return np.full(4, np.nan) if self.executed_steps == 26 else state

    monkeypatch.setattr(StressPlant, "step", fail_after_change)
    config = StressConfig(seeds=(10,), rollout_steps=50, window_steps=25, fixed_stage_steps=25)
    scenario = StressScenario("jump", after=JointParameters(actuator_gain=(4.0, 4.0)), change_step=25)
    report, trace, _ = run_stress(config, scenarios=(scenario,), modes=("competence",))
    record = report["records"][0]
    assert len(trace) == record["executed_steps"] == 26
    assert record["phases"]["pre_change"]["executed_steps"] == 25
    assert record["phases"]["post_change"]["executed_steps"] == 1
    assert record["terminal_partial_window_steps"] == 1
    assert record["windows"][-1]["phase"] == "post_change"
    assert record["windows"][-1]["failures"] == ["nonfinite_state"]
    assert record["first_post_change_failure_observed_step"] is None
    assert record["first_post_change_gate_detection_step"] is None
    assert record["first_post_change_retreat_step"] is None


def test_snapshot_and_compressed_trace_are_auditable(tmp_path):
    config = StressConfig(seeds=(10,), rollout_steps=2, window_steps=1, fixed_stage_steps=1)
    report, trace, gates = run_stress(config, scenarios=(StressScenario("nominal"),), modes=("zero",))
    write_outputs(tmp_path, report, trace, gates)
    with gzip.open(tmp_path / "trace.csv.gz", "rt", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == report["total_executed_steps"]
    with zipfile.ZipFile(tmp_path / "source_snapshot.zip") as archive:
        for source, digest in report["source_sha256"].items():
            assert hashlib.sha256(archive.read(source)).hexdigest() == digest
    before = (tmp_path / "trace.csv.gz").read_bytes()
    write_outputs(tmp_path, report, trace, gates)
    assert (tmp_path / "trace.csv.gz").read_bytes() == before


def test_fixed_parameters_cannot_change_silently(monkeypatch):
    model = FixedBodyModel()
    with pytest.raises(FrozenInstanceError):
        model.dt = 0.04
    original_observe = stress.SustainedCompetenceGate.observe

    def mutate_threshold(self, evidence):
        result = original_observe(self, evidence)
        self.failure_windows += 1
        return result

    monkeypatch.setattr(stress.SustainedCompetenceGate, "observe", mutate_threshold)
    config = StressConfig(seeds=(10,), rollout_steps=2, window_steps=1, fixed_stage_steps=1)
    with pytest.raises(AssertionError, match="gate parameters changed"):
        run_stress(config, scenarios=(StressScenario("nominal"),), modes=("competence_sustained",))


def test_applied_history_exposure_is_distinct_from_new_command_violation(monkeypatch):
    original_observe = stress.CompetenceGate.observe

    def force_withdrawal(self, evidence):
        decision = original_observe(self, evidence)
        if len(self.events) == 1:
            self.level = 2
        else:
            self.level = 0
        return decision

    monkeypatch.setattr(stress.CompetenceGate, "observe", force_withdrawal)
    config = StressConfig(seeds=(10,), rollout_steps=3, window_steps=1, fixed_stage_steps=1)
    scenario = StressScenario("delay", JointParameters(delay_steps=1))
    report, trace, _ = run_stress(config, scenarios=(scenario,), modes=("competence",))
    assert [row["level"] for row in trace] == [0, 2, 0]
    assert [row["applied_command_level"] for row in trace] == [None, 0, 2]
    assert trace[2]["command1"] == 0
    assert trace[2]["applied1"] != 0
    assert trace[2]["applied_exceeds_current_permission"]
    assert not trace[2]["command_limit_violation"]
    assert report["records"][0]["applied_command_exceeds_current_permission_steps"] == 1


def test_invalid_protocol_changes_are_rejected():
    with pytest.raises(ValueError, match="align"):
        StressConfig(window_steps=25, fixed_stage_steps=74)
    with pytest.raises(ValueError, match="together"):
        StressScenario("bad", after=JointParameters())
    config = StressConfig(seeds=(10,), rollout_steps=10, window_steps=5, fixed_stage_steps=5)
    with pytest.raises(ValueError, match="boundary"):
        run_stress(config, scenarios=(StressScenario("bad", after=JointParameters(), change_step=3),))
