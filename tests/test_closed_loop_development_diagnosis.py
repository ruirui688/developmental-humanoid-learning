"""Archive boundary and causal-input checks for development-only replay."""
import importlib.util
import json
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/diagnose_closed_loop_development.py"
SPEC = importlib.util.spec_from_file_location("closed_loop_development_diagnosis", SCRIPT)
diagnosis = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(diagnosis)


def test_outputs_resolve_outside_inputs_and_cannot_collide(tmp_path):
    archive = tmp_path / "archive"
    archive.mkdir()
    inputs = {"v1": archive, "v2": tmp_path / "second"}
    with pytest.raises(ValueError, match="outside input"):
        diagnosis.validate_outputs(inputs, archive / "report.json", tmp_path / "report.md")
    with pytest.raises(ValueError, match="different paths"):
        diagnosis.validate_outputs(inputs, tmp_path / "same", tmp_path / "same")
    existing = tmp_path / "old.json"
    existing.write_text("unchanged")
    with pytest.raises(ValueError, match="overwrite"):
        diagnosis.validate_outputs(inputs, existing, tmp_path / "report.md")
    assert existing.read_text() == "unchanged"
    with pytest.raises(ValueError, match="parent"):
        diagnosis.validate_outputs(inputs, tmp_path / "nested", tmp_path / "nested" / "report.md")


def test_holdout_rejected_before_native_trace_access(tmp_path):
    archive = tmp_path / "archive"
    archive.mkdir()
    (archive / "metadata.json").write_text(json.dumps({"split": "holdout", "seeds": [0, 1, 2]}))
    # No model or trace files exist; a missing-file error would expose late validation.
    with pytest.raises(ValueError, match="Only development"):
        diagnosis.load(archive, "v2")


def test_native_extractor_never_indexes_privileged_fields():
    class CausalRow(dict):
        def __getitem__(self, key):
            if key in {"diagnostics", "qpos", "qvel", "predicted_next_qv", "model_update"}:
                raise AssertionError("Forbidden fitting input")
            return super().__getitem__(key)

    row = CausalRow(step_index=100, phase="calibration", requested_torque=[.25],
                    observation_before={"joint_position": [.1], "joint_velocity": [.2], "previous_command": [.125]},
                    observation_after={"joint_position": [.11], "joint_velocity": [.3]},
                    diagnostics=object(), qpos=object(), qvel=object())
    extracted = diagnosis.extract(row, 0)
    assert extracted["u"] == .25 and extracted["previous_u"] == .125
    assert extracted["next_q"] == .11 and extracted["next_v"] == .3


def test_history_rejects_different_input_bytes(tmp_path):
    first, second = tmp_path / "first", tmp_path / "second"
    first.mkdir(); second.mkdir()
    (first / "metadata.json").write_text("different")
    (second / "metadata.json").write_text("second")
    history = tmp_path / "history.json"
    history.write_text(json.dumps({"holdout_read": False, "inputs": {
        "v1": {"sha256": {"metadata.json": "wrong"}},
        "v2": {"sha256": {"metadata.json": diagnosis.sha(second / "metadata.json")}},
    }}))
    with pytest.raises(ValueError, match="same input bytes"):
        diagnosis.load_history(history, {"v1": first, "v2": second})


def test_replay_distinguishes_endpoint_and_integrated_position():
    rows = [{"q": 0., "v": 0., "u": 0., "previous_u": 0., "next_q": .001, "next_v": .1}]
    # Exactly right endpoint speed still doubles a linear-ramp displacement.
    theta = [0., 0., 0., 0., .1]
    endpoint = diagnosis.score(rows, 0., theta)
    trapezoid = diagnosis.score(rows, 0., theta, integration="trapezoid")
    assert endpoint["endpoint_velocity_rmse_rad_s"] == 0.
    assert endpoint["position_rmse_rad"] == pytest.approx(.001)
    assert trapezoid["position_rmse_rad"] == pytest.approx(0.)


def test_cli_refuses_output_before_fitting(tmp_path, monkeypatch):
    output = tmp_path / "old.json"
    output.write_text("unchanged")
    monkeypatch.setattr("sys.argv", [str(SCRIPT), "--output", str(output), "--markdown", str(tmp_path / "new.md")])
    monkeypatch.setattr(diagnosis, "run", lambda *args: pytest.fail("No replay fitting after output rejection"))
    with pytest.raises(SystemExit) as exit_info:
        diagnosis.main()
    assert exit_info.value.code == 2 and output.read_text() == "unchanged"
