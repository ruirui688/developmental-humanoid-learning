"""Pure synthetic records: paired arithmetic, missing data and audit guards."""

from copy import deepcopy
import gzip
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("joint_probe_analysis", ROOT / "scripts/analyze_joint_probes.py")
ANALYSIS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ANALYSIS)


def _write(folder, metadata, trials, rows):
    folder.mkdir()
    for name, value in (("metadata.json", metadata), ("trials.json", trials)):
        (folder / name).write_text(json.dumps(value), encoding="utf-8")
    (folder / "source_snapshot.zip").write_bytes(b"synthetic arithmetic fixture, no simulator")
    with gzip.open(folder / "trace.jsonl.gz", "wt", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row) + "\n")


def _observation(position=0., velocity=0., gyro=0.):
    return {"joint_position": [position] + [0.] * 7, "joint_velocity": [velocity] + [0.] * 7,
            "imu_gyro": [gyro, 0., 0.], "imu_acceleration": [0., 0., 9.81],
            "actuator_torque": [0.] * 8, "previous_command": [0.] * 8}


@pytest.fixture
def archive_fixture(tmp_path):
    rows, trials = [], []
    phase_budgets = {phase: {"control_calls_attempted": 2, "control_steps": 2, "physics_steps": 4}
                     for phase in ("prefix", "probe", "recovery")}
    for seed in (0, 1, 2):
        for amplitude in (0., .125, .25, .5):
            mode = "zero_torque" if amplitude == 0 else "joint_probe"
            tid = f"supine_seed{seed}_" + ("zero" if amplitude == 0 else f"joint0_amp{amplitude:g}")
            actor_spec = {
                "config": {"mode": "zero" if amplitude == 0 else "pulse", "joint_index": None if amplitude == 0 else 0,
                           "amplitude_nm": .5 if amplitude == 0 else amplitude,
                           "prefix_steps": 2, "pulse_steps": 2, "recovery_steps": 2},
                "joint_ranges_rad": [[-1., 2.] for _ in range(8)], "model_updates": 0,
                "policy_updates": 0, "gate_updates": 0, "direction_updates_after_selection": 0,
            }
            actor_hash = hashlib.sha256(json.dumps(actor_spec, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            selection = None if amplitude == 0 else {
                "joint_position_rad": 0., "lower_limit_rad": -1., "upper_limit_rad": 2.,
                "direction": 1, "selection_step": 2,
            }
            trials.append({"trial_id": tid, "pose": "supine", "seed": seed, "mode": mode,
                           "joint_index": None if amplitude == 0 else 0, "amplitude_nm": amplitude,
                           "selected_direction": None if amplitude == 0 else 1, "selection_record": selection,
                           "status": "completed", "terminated": False, "reason": None,
                           "control_steps": 6, "control_calls_attempted": 6, "physics_steps": 12,
                           "phase_budgets": deepcopy(phase_budgets), "probe_spec": actor_spec,
                           "environment_fingerprint_before": "fixed-env", "environment_fingerprint_after": "fixed-env",
                           "actor_fingerprint_before": actor_hash, "actor_fingerprint_after": actor_hash,
                           "invalid_numeric_fields": []})
            before = _observation()
            for index in range(6):
                phase = "prefix" if index < 2 else ("probe" if index < 4 else "recovery")
                command = amplitude if phase == "probe" else 0.
                after = _observation(amplitude * .01 * (index - 1) if phase == "probe" else
                                     (amplitude * .015 if phase == "recovery" else 0.),
                                     command, command)
                request = [command] + [0.] * 7
                diagnostic = {
                    "requested_torque": request, "accepted_torque": request, "applied_torque_history": [request, [0.] * 8],
                    "executed_substeps": 2, "substep_ground_normal_forces": [1., 2.],
                    "substep_kinetic_energies": [.1, .2], "substep_minimum_contact_distances": [-.001, -.002],
                    "peak_substep_ground_normal_force": 2., "peak_substep_kinetic_energy": .2,
                    "minimum_substep_contact_distance": -.002, "ground_normal_impulse_ns": .03,
                    "time": .02 * (index + 1),
                }
                rows.append({"trial_id": tid, "mode": mode, "pose": "supine", "seed": seed,
                             "joint_index": None if amplitude == 0 else 0, "amplitude_nm": amplitude,
                             "phase": phase, "action_index": index - 2 if phase == "probe" else None,
                             "observation_before": before, "observation_after": after,
                             "diagnostics": diagnostic, "invalid_numeric_fields": []})
                before = after
    metadata = {
        "source_commit": "synthetic", "source_dirty": False, "split": "development",
        "prefix_steps": 2, "pulse_steps": 2, "recovery_steps": 2,
        "environment_config": {"physics_dt": .01, "control_substeps": 2},
        "poses": ["supine"], "seeds": [0, 1, 2], "joints": [0], "amplitudes_nm": [.125, .25, .5],
        "parameter_updates": {"model": 0, "policy": 0, "gate": 0}, "complete": True,
        "control_steps": 72, "control_calls_attempted": 72, "physics_steps": 144,
        "expected_trial_count": 12,
        "phase_budgets": {phase: {"control_calls_attempted": 24, "control_steps": 24, "physics_steps": 48}
                          for phase in ("prefix", "probe", "recovery")},
    }
    folder = tmp_path / "valid"
    _write(folder, metadata, trials, rows)
    return folder, metadata, trials, rows


def test_paired_native_response_and_true_exposure(archive_fixture):
    folder, *_ = archive_fixture
    result = ANALYSIS.analyze(folder)
    assert result["protocol_valid"] and not result["unavailable_trial_ids"]
    pair = result["pairs"][0]
    assert pair["exact_prefix_replay"] and pair["available"]
    assert pair["pulse_end"]["target_joint_directed_paired_delta_rad"] == pytest.approx(.0025)
    assert pair["recovery_end"]["target_joint_directed_paired_delta_rad"] == pytest.approx(.001875)
    assert pair["paired_native_rms"]["probe"]["joint_position"]["per_component"][0] == pytest.approx(.125 * math.sqrt((.01 ** 2 + .02 ** 2) / 2))
    assert pair["pulse_action_metrics"]["applied_torque_rms_nm_per_joint"][0] == pytest.approx(.125 / math.sqrt(2))
    assert pair["pulse_action_metrics"]["blocked_fraction_of_nonzero_requested_substeps_per_joint"] == [.5] + [None] * 7
    assert pair["pulse_action_metrics"]["applied_signed_torque_integral_nms_per_joint"][0] == pytest.approx(.0025)
    assert pair["pulse_action_metrics"]["ground_normal_force_integral_ns"] == pytest.approx(.06)
    assert pair["pulse_action_metrics"]["accepted_torque_rms_nm_per_joint"][0] == pytest.approx(.125)
    assert pair["pulse_action_metrics"]["target_directed_requested_torque_integral_nms"] == pytest.approx(.005)
    assert pair["pulse_action_metrics"]["target_directed_applied_torque_integral_nms"] == pytest.approx(.0025)
    assert pair["first_recorded_pulse_threshold_crossing"]["reached"]
    assert pair["first_recorded_pulse_threshold_crossing"]["elapsed_from_pulse_start_seconds"] == pytest.approx(.02)
    assert result["trials"][1]["whole_trial"]["ground_normal_force_integral_ns"] == pytest.approx(.18)
    assert result["shared_zero_trial_count"] == 3 and result["probe_pair_count"] == 9
    assert result["analysis_runtime"]["third_party_analysis_dependencies"] == []


def test_three_seed_measurement_gates_and_dose_curves(archive_fixture):
    folder, *_ = archive_fixture
    result = ANALYSIS.analyze(folder)
    assert len(result["measurement_gates"]) == 3 and all(gate["passes"] for gate in result["measurement_gates"])
    assert all(not gate["hardware_safety_standard"] for gate in result["measurement_gates"])
    assert all(curve["nondecreasing_directed_dose_response"] for curve in result["dose_response"][0]["seed_curves"])
    pairs = deepcopy(result["pairs"])
    pairs[0]["pulse_end"]["target_joint_directed_paired_delta_rad"] = .001
    gates, _ = ANALYSIS._gates_and_doses(pairs, {"poses": ["supine"], "joints": [0], "seeds": [0, 1, 2]}, True)
    assert gates[0]["available"] and gates[0]["passes"]
    pairs[0]["pulse_end"]["target_joint_directed_paired_delta_rad"] = .000999
    gates, _ = ANALYSIS._gates_and_doses(pairs, {"poses": ["supine"], "joints": [0], "seeds": [0, 1, 2]}, True)
    assert gates[0]["available"] and not gates[0]["passes"]
    pairs[0]["pulse_end"]["target_joint_directed_paired_delta_rad"] = .0025
    pairs[0]["selected_direction"] = -1
    pairs[0]["pulse_end"]["target_joint_paired_delta_rad"] = -.0025
    gates, _ = ANALYSIS._gates_and_doses(pairs, {"poses": ["supine"], "joints": [0], "seeds": [0, 1, 2]}, True)
    assert gates[0]["available"] and not gates[0]["response_direction_consistent_across_seeds"]


@pytest.mark.parametrize("failure", ["invalid", "exception", "terminated", "changed_parameters"])
def test_failed_trials_excluded_but_budget_and_seed_retained(archive_fixture, failure):
    folder, metadata, trials, rows = archive_fixture
    trials, rows, metadata = deepcopy(trials), deepcopy(rows), deepcopy(metadata)
    tid = trials[1]["trial_id"]
    index = next(i for i, row in enumerate(rows) if row["trial_id"] == tid)
    if failure == "invalid":
        rows[index]["invalid_numeric_fields"] = [{"path": "/observation_after/joint_position/0", "value": "nan"}]
    elif failure == "exception":
        rows.insert(index, {"trial_id": tid, "collector_exception": {"type": "RuntimeError", "message": "synthetic"}})
        metadata["physics_steps"] += 1
        trials[1]["physics_steps"] += 1
        metadata["phase_budgets"]["probe"]["physics_steps"] += 1
        trials[1]["phase_budgets"]["probe"]["physics_steps"] += 1
    elif failure == "terminated":
        trials[1]["terminated"], trials[1]["status"] = True, "terminated"
    else:
        trials[1]["environment_fingerprint_after"] = "changed"
    modified = folder.parent / failure
    _write(modified, metadata, trials, rows)
    result = ANALYSIS.analyze(modified)
    assert result["unavailable_trial_ids"] == [tid]
    assert len(result["trials"]) == 12 and len(result["pairs"]) == 9
    assert not result["pairs"][0]["available"] and not result["measurement_gates"][0]["available"]
    assert result["budget_checks"]["physics_steps"]["metadata"] == metadata["physics_steps"]


def test_exact_prefix_pair_is_required(archive_fixture):
    folder, metadata, trials, rows = archive_fixture
    rows = deepcopy(rows)
    index = next(i for i, row in enumerate(rows) if row["trial_id"] == trials[1]["trial_id"])
    rows[index]["observation_after"]["imu_gyro"][0] = .01
    rows[index + 1]["observation_before"]["imu_gyro"][0] = .01
    modified = folder.parent / "prefix_mismatch"
    _write(modified, metadata, trials, rows)
    result = ANALYSIS.analyze(modified)
    assert result["trials"][1]["metrics_available"]
    assert not result["pairs"][0]["exact_prefix_replay"] and not result["pairs"][0]["available"]


def test_missing_trial_does_not_disappear_from_gate(archive_fixture):
    folder, metadata, trials, rows = archive_fixture
    modified = folder.parent / "missing"
    missing = trials[1]
    _write(modified, metadata, trials[:1] + trials[2:], [row for row in rows if row["trial_id"] != missing["trial_id"]])
    result = ANALYSIS.analyze(modified)
    assert result["missing_trial_cases"] == [{"pose": "supine", "seed": 0, "mode": "joint_probe", "joint_index": 0, "amplitude_nm": .125}]
    assert not result["protocol_valid"] and not result["measurement_gates"][0]["available"]


def test_duplicate_trial_ids_rejected(archive_fixture):
    folder, metadata, trials, rows = archive_fixture
    modified = folder.parent / "duplicate"
    _write(modified, metadata, trials + [trials[0]], rows)
    with pytest.raises(ValueError, match="duplicate trial IDs"):
        ANALYSIS.analyze(modified)


@pytest.mark.parametrize("location", ["inside", "existing"])
def test_output_protection(tmp_path, monkeypatch, location):
    archive = tmp_path / "input"
    output = archive / "analysis.json" if location == "inside" else tmp_path / "prior.json"
    if location == "existing":
        output.write_text("preserve", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["analysis", str(archive), "--output", str(output)])
    with pytest.raises(SystemExit) as error:
        ANALYSIS.main()
    assert error.value.code == 2
    if location == "existing":
        assert output.read_text(encoding="utf-8") == "preserve"
