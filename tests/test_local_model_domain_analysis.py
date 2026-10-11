"""Causality, continuity, denominator and input-protection checks."""
import gzip
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import zipfile

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "analyze_local_model_domain.py"
spec = importlib.util.spec_from_file_location("local_model_domain", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def snapshot(hinge=False):
    size = 5 if hinge else 4
    record = {"qref_rad": .1, "dt_seconds": .02, "features": module.HINGE_FEATURES if hinge else module.LINEAR_FEATURES, "initial_coefficients": [1., 0., .02] + [0.] * (size - 3), "initial_covariance_scale": 100., "forgetting_factor": 1., "coefficients": [1., 0., .02] + [0.] * (size - 3), "covariance": [[100. if i == j else 0. for j in range(size)] for i in range(size)], "dtype": "float64"}
    if hinge:
        record.update(hinge_threshold_nm=.25, hinge_threshold_updates=0, hinge_structure_prior="fixed signed torque hinge; structural prior, not a learned threshold or physics label")
    fingerprint = hashlib.sha256(json.dumps(record, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    return {**record, "parameter_fingerprint": fingerprint, "update_count": 0, "trainable": False}


def native(q, v):
    return {"joint_position": [q] + [0.] * 7, "joint_velocity": [v] + [0.] * 7}


def row(index, before, after):
    return {"step_index": index, "phase": "prediction", "observation_before": before, "observation_after": after, "requested_torque": [0.] * 8, "diagnostics": {"time": (index + 1) * .02, "executed_substeps": 10, "terminated": False}}


@pytest.mark.parametrize("horizon", [2, 5, 15])
def test_free_rollout_integrates_own_predictions_and_recorded_inputs(horizon):
    model = module.snapshot_model(snapshot())
    path = module.free_rollout(model, .2, .1, [.5] * horizon)
    expected_v = .1 + .01 * horizon
    expected_q = .2 + .02 * (horizon * .1 + .01 * horizon * (horizon + 1) / 2)
    assert path[-1] == pytest.approx([expected_q, expected_v], abs=1e-14)


def test_constant_velocity_baseline_has_no_requested_torque_response():
    path = module.free_rollout(None, .2, .1, [.5, -.5, .25, 0.])
    assert path[-1] == pytest.approx([.208, .1])


def test_hinge_model_features_use_requested_signed_fixed_threshold():
    model = module.snapshot_model(snapshot(hinge=True))
    assert module.features(model, .2, .3, -.5) == pytest.approx([.3, .1, -.5, -.25, 1.])


def test_saved_parameter_corruption_is_rejected():
    model = snapshot()
    model["coefficients"][2] = .04
    with pytest.raises(ValueError, match="fingerprint"):
        module.snapshot_model(model)


def test_valid_window_requires_continuous_native_state_and_full_intervals():
    first = row(100, native(.1, .2), native(.104, .2))
    second = row(101, native(.104, .2), native(.108, .2))
    indexed = {100: first, 101: second}
    assert module.valid_window(indexed, 100, 2, 0)[1] is None
    second["diagnostics"]["executed_substeps"] = 5
    assert module.valid_window(indexed, 100, 2, 0)[1] == "partial_physics_interval"
    assert module.valid_window(indexed, 100, 1, 0)[1] is None
    second["diagnostics"]["executed_substeps"] = 10
    second["observation_before"] = native(9., .2)
    assert module.valid_window(indexed, 100, 2, 0)[1] == "native_state_discontinuity"


def test_missing_phase_boundary_and_terminal_continuation_are_explicit():
    first = row(100, native(.1, .2), native(.104, .2))
    second = row(101, native(.104, .2), native(.108, .2))
    assert module.valid_window({100: first}, 100, 2, 0)[1] == "missing_control_row"
    second["phase"] = "control"
    assert module.valid_window({100: first, 101: second}, 100, 2, 0)[1] == "crossed_phase_boundary"
    second["phase"] = "prediction"
    first["diagnostics"]["terminated"] = True
    assert module.valid_window({100: first, 101: second}, 100, 2, 0)[1] == "continued_after_termination"


def test_window_and_path_error_denominators_are_separate():
    errors = module.Errors()
    errors.add([(1., 2.), (2., 4.)], [(0., 0.), (0., 0.)])
    result = errors.result()
    assert result["valid_prediction_windows"] == 1
    assert result["path_endpoint_samples"] == 2
    assert result["terminal_q_rmse_rad"] == 2.
    assert result["path_q_rmse_rad"] == pytest.approx((5/2) ** .5)


def test_holdout_is_rejected_before_manifest_or_output_access(tmp_path):
    archive = tmp_path / "holdout"
    archive.mkdir()
    (archive / "metadata.json").write_text(json.dumps({"split": "holdout"}), encoding="utf-8")
    output = tmp_path / "diagnostics.json"
    process = subprocess.run([sys.executable, str(SCRIPT), str(archive), "--output", str(output)], capture_output=True, text=True)
    assert process.returncode == 2
    assert "development" in process.stderr
    assert not output.exists()
    assert not output.with_name(output.stem + ".windows.jsonl.gz").exists()


def test_output_guard_protects_input_and_existing_window_sidecar(tmp_path):
    archive = tmp_path / "archive"
    archive.mkdir()
    with pytest.raises(ValueError, match="outside"):
        module.validate_outputs(archive / "analysis.json", [archive])
    output = tmp_path / "analysis.json"
    sidecar = tmp_path / "analysis.windows.jsonl.gz"
    sidecar.write_bytes(b"preserve")
    with pytest.raises(ValueError, match="overwrite"):
        module.validate_outputs(output, [archive])
    assert sidecar.read_bytes() == b"preserve"


def test_partial_trial_does_not_masquerade_as_complete(tmp_path):
    path = tmp_path / "partial"
    path.mkdir()
    model = snapshot()
    (path / "episodes.json").write_text(json.dumps([{"seed": 0, "kind": "prediction", "trial_id": "seed0_prediction", "maximum_control_steps": 104, "status": "completed", "control_steps": 104, "control_calls_attempted": 104, "physics_steps": 1040}]), encoding="utf-8")
    (path / "seed_results.json").write_text(json.dumps([{"seed": 0, "initial_model": model, "learned_model": model}]), encoding="utf-8")
    first = row(100, native(.1, .2), native(.104, .2))
    first["trial_id"] = "seed0_prediction"
    second = row(101, native(.104, .2), native(.108, .2))
    second["trial_id"] = "seed0_prediction"
    second["diagnostics"]["executed_substeps"] = 5
    with gzip.open(path / "trace.jsonl.gz", "wt", encoding="utf-8") as stream:
        stream.write(json.dumps(first) + "\n" + json.dumps(second) + "\n")
    report = module.analyze_archive(path, {"joint_index": 0, "source_commit": "1"*40, "split": "development", "pose": "supine", "complete": False}, io.StringIO())
    trial = report["trials"][0]
    assert trial["complete_trial"] is False
    assert trial["horizons"][0]["expected_windows_from_planned_active_duration"] == 4
    assert trial["horizons"][0]["valid_physical_windows"] == 1
    assert trial["horizons"][0]["excluded_windows"] == 3
    assert trial["horizons"][1]["valid_physical_windows"] == 0


def test_manifest_hash_mismatch_is_rejected(tmp_path):
    path = tmp_path / "development"
    path.mkdir()
    (path / "metadata.json").write_text(json.dumps({"split": "development", "pose": "supine", "joint_index": 0}), encoding="utf-8")
    for name in module.CORE - {"metadata.json"}:
        (path / name).write_bytes(b"fixture")
    manifest = {name: module.sha(path / name) for name in module.CORE}
    manifest["trace.jsonl.gz"] = "0" * 64
    (path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="Manifest hash"):
        module.verify_archive(path)
