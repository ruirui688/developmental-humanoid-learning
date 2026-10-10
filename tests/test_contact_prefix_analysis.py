"""Synthetic offline arithmetic tests: no physics backend or fitting."""

from copy import deepcopy
import gzip
import importlib.util
import json
from pathlib import Path
import sys

import numpy as np
import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("contact_analysis", ROOT / "scripts/analyze_ground_contact_prefix.py")
ANALYSIS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ANALYSIS)
PHYSICS_DT, STEPS = .01, 103


def _write_archive(folder, metadata, trials, rows):
    folder.mkdir()
    for name, value in (("metadata.json", metadata), ("trials.json", trials)):
        (folder / name).write_text(json.dumps(value), encoding="utf-8")
    (folder / "source_snapshot.zip").write_bytes(b"synthetic fixture, no physics")
    with gzip.open(folder / "trace.jsonl.gz", "wt", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row) + "\n")


def _row_record(trial_id, contact, prefix, index, mode):
    active = index >= prefix
    command = .1 * (index - prefix + 1) if mode == "smooth_random" and active else 0.
    request = [command] * 8
    actual_first, actual_second = request.copy(), request.copy()
    actual_second[0] = 0.
    position = [float(index + 1) * .001] * 8
    if active and mode == "smooth_random":
        position = [item + .005 * (index - prefix + 1) for item in position]
    before = {"joint_position": [float(index) * .001] * 8, "joint_velocity": [0.] * 8, "imu_gyro": [0.] * 3}
    after = {"joint_position": position, "joint_velocity": [0.] * 8, "imu_gyro": [0.] * 3}
    diagnostic = {
        "time": .02 * (index + 1), "requested_torque": request,
        "applied_torque_history": [actual_first, actual_second],
        "executed_substeps": 2, "ground_contact_count": index % 2,
        "substep_ground_normal_forces": [1., 2.], "substep_kinetic_energies": [.1, .2],
        "substep_minimum_contact_distances": [-.001, -.002],
        "ground_normal_impulse_ns": .03, "peak_substep_ground_normal_force": 2.,
        "peak_substep_kinetic_energy": .2, "minimum_substep_contact_distance": -.002,
        "kinetic_energy": .2,
    }
    return {"trial_id": trial_id, "contact_profile": contact, "prefix_steps": prefix,
            "phase": "exploration" if active else "prefix", "action_index": index - prefix if active else None,
            "observation_before": before, "observation_after": after,
            "qpos": position, "qvel": [0.] * 8, "diagnostics": diagnostic, "invalid_numeric_fields": []}


@pytest.fixture
def synthetic_archive(tmp_path):
    metadata = {
        "poses": ["supine"], "seeds": [0], "steps_per_trial_limit": STEPS,
        "config": {"physics_dt": PHYSICS_DT, "control_substeps": 2},
        "source_commit": "synthetic", "source_dirty": False, "expected_trial_count": 8,
        "complete": True, "parameter_updates": {"model": 0, "policy": 0, "gate": 0},
        "control_steps": 8 * STEPS, "control_calls_attempted": 8 * STEPS,
        "physics_steps": 16 * STEPS, "wall_seconds": 0,
    }
    rows, trials = [], []
    for contact in ("baseline", "compliant"):
        for prefix in (0, 100):
            for mode in ("zero_torque", "smooth_random"):
                tid = f"{contact}_prefix{prefix}_supine_seed0_{mode}"
                trials.append({"trial_id": tid, "contact_profile": contact, "prefix_steps": prefix,
                               "pose": "supine", "seed": 0, "mode": mode, "status": "completed",
                               "control_steps": STEPS, "physics_steps": 2 * STEPS,
                               "control_calls_attempted": STEPS, "terminated": False,
                               "initial_qpos": [0.] * 8, "reset_seed": 123,
                               "exploration_seed": 456, "invalid_numeric_fields": []})
                rows.extend(_row_record(tid, contact, prefix, i, mode) for i in range(STEPS))
    original = []
    for row in rows:
        if row["contact_profile"] == "baseline" and row["prefix_steps"] == 0:
            copied = deepcopy(row)
            copied["trial_id"] = "supine_seed0_" + row["trial_id"].split("_seed0_", 1)[1]
            for key in ("phase", "action_index", "contact_profile", "prefix_steps"):
                copied.pop(key)
            original.append(copied)
    folder, reference = tmp_path / "input", tmp_path / "reference"
    _write_archive(folder, metadata, trials, rows)
    _write_archive(reference, metadata, [], original)
    return folder, reference, metadata, trials, rows


def test_applied_action_denominators_and_pair_alignment(synthetic_archive):
    folder, reference, *_ = synthetic_archive
    result = ANALYSIS.analyze(folder, reference, shared_steps=3)
    paired = result["paired_active_responses"][0]
    expected = np.array([.1, .2, .3])
    metrics = paired["random_shared_action_metrics"]
    np.testing.assert_allclose(metrics["requested_torque_rms_nm_per_joint"], np.sqrt(np.mean(expected ** 2)))
    assert metrics["blocked_fraction_of_nonzero_requested_substeps_per_joint"] == [.5] + [0.] * 7
    np.testing.assert_allclose(metrics["applied_signed_torque_integral_nms_per_joint"], [.006] + [.012] * 7)
    np.testing.assert_allclose(paired["native_position_trajectory_difference_rms_rad_all_joints"],
                               np.sqrt(np.mean(np.array([.005, .010, .015]) ** 2)))
    assert paired["zero_shared_action_metrics"]["blocked_fraction_of_nonzero_requested_substeps_per_joint"] == [None] * 8
    assert paired["random_shared_substep_metrics"]["physics_samples"] == 6
    assert paired["zero_shared_substep_metrics"]["ground_normal_impulse_ns"] == pytest.approx(.09)


def test_passive_duplicate_and_unconsumed_rng_replay(synthetic_archive):
    folder, reference, *_ = synthetic_archive
    result = ANALYSIS.analyze(folder, reference, shared_steps=3)
    assert result["baseline_prefix0_reference_replay"]["exact"]
    assert result["prefix_invariance"]["all_available_and_exact"]
    assert len(result["prefix_invariance"]["zero_prefix_duplicate_trajectory_checks"]) == 2
    assert result["trials"][0]["prefix_endpoint"]["kinetic_energy_j"] == 0.
    assert result["trials"][0]["prefix_endpoint"]["stability_decision"] is None
    with_prefix = result["trials"][2]
    assert with_prefix["executed_active_steps"] == 3 and with_prefix["executed_prefix_steps"] == 100
    assert with_prefix["prefix_endpoint"]["kinetic_energy_j"] == .2


@pytest.mark.parametrize("failure", ["invalid", "collector_exception"])
def test_invalid_and_interrupted_trials_stay_visible(synthetic_archive, failure):
    folder, reference, metadata, trials, rows = synthetic_archive
    rows = deepcopy(rows)
    if failure == "invalid":
        rows[0]["invalid_numeric_fields"] = [{"path": "/qpos/0", "value": "nan"}]
    else:
        rows.insert(1, {"trial_id": trials[0]["trial_id"], "collector_exception": {"type": "RuntimeError", "message": "synthetic interruption"}, "invalid_numeric_fields": []})
        metadata = deepcopy(metadata)
        metadata["physics_steps"] += 1
    interrupted = folder.parent / failure
    _write_archive(interrupted, metadata, trials, rows)
    result = ANALYSIS.analyze(interrupted, reference, shared_steps=3)
    assert result["metrics_unavailable_trial_ids"] == [trials[0]["trial_id"]]
    assert len(result["trials"]) == 8 and not result["paired_active_responses"][0]["complete"]
    assert result["budget"]["physics_steps"] == metadata["physics_steps"]
    assert "whole_trial" not in result["trials"][0]


def test_zero_executed_substeps_have_no_rms(synthetic_archive):
    *_, rows = synthetic_archive
    row = deepcopy(rows[0])
    row["diagnostics"].update(executed_substeps=0, applied_torque_history=[])
    metrics = ANALYSIS.action_metrics([row], PHYSICS_DT)
    assert metrics["executed_physics_substeps"] == 0
    assert metrics["applied_torque_rms_nm_per_joint"] is None


@pytest.mark.parametrize("location", ["input", "reference"])
def test_cli_rejects_writes_inside_either_input(tmp_path, monkeypatch, location):
    monkeypatch.setattr(sys, "argv", ["analyze", str(tmp_path / "input"), "--reference", str(tmp_path / "reference"),
                                      "--output", str(tmp_path / location / "new.json")])
    with pytest.raises(SystemExit) as error:
        ANALYSIS.main()
    assert error.value.code == 2


def test_missing_case_is_reported(synthetic_archive):
    folder, reference, metadata, trials, rows = synthetic_archive
    missing_id = trials[-1]["trial_id"]
    incomplete = folder.parent / "missing"
    _write_archive(incomplete, metadata, trials[:-1], [row for row in rows if row["trial_id"] != missing_id])
    result = ANALYSIS.analyze(incomplete, reference, shared_steps=3)
    assert result["missing_trial_ids"] == [missing_id]
