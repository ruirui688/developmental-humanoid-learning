"""Failure preservation for the optional CPU collector; no parameter fitting."""

from __future__ import annotations

import gzip
import hashlib
import json

import numpy as np
import pytest

pytest.importorskip("mujoco")

from developmental_physics import collect as collection


def _read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _trace(output):
    with gzip.open(output / "trace.jsonl.gz", "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream]


def _assert_manifest(output):
    for filename, digest in _read(output / "manifest.json").items():
        assert hashlib.sha256((output / filename).read_bytes()).hexdigest() == digest


def test_invalid_numbers_have_explicit_markers_and_finite_values_keep_precision():
    finite = 1.2345678901234567
    archived = collection._archive_record({
        "values": np.array([finite, np.nan, np.inf, -np.inf]),
        "a/b~c": np.float64(np.nan),
    })
    assert archived["values"] == [finite, None, None, None]
    assert archived["invalid_numeric_fields"] == [
        {"path": "/values/1", "value": "nan"},
        {"path": "/values/2", "value": "+inf"},
        {"path": "/values/3", "value": "-inf"},
        {"path": "/a~1b~0c", "value": "nan"},
    ]
    assert json.loads(json.dumps(archived, allow_nan=False))["values"][0] == finite


def test_nonfinite_stop_retains_fault_row_and_each_failed_trial(tmp_path, monkeypatch):
    base = collection.GroundBodyEnv

    class NonfiniteStateEnv(base):
        def step(self, command):
            # Inject invalid sensor/state data before the pre-integration check.
            # Do not ask MuJoCo to integrate a corrupt state.
            self.data.qvel[self._joint_dof[0]] = np.inf
            self.data.qpos[self._joint_qpos[1]] = np.nan
            return super().step(command)

    monkeypatch.setattr(collection, "GroundBodyEnv", NonfiniteStateEnv)
    output = tmp_path / "nonfinite"
    metadata = collection.collect(output, seeds=[0], steps=2)
    assert metadata["complete"] is True
    assert metadata["archive_status"] == "complete"
    assert metadata["trial_count"] == metadata["terminated_trials"] == 8
    assert metadata["physics_steps"] == 0
    assert metadata["parameter_updates"] == {"model": 0, "policy": 0, "gate": 0}
    rows = _trace(output)
    assert len(rows) == 8
    for row in rows:
        assert row["diagnostics"]["reason"] == "nonfinite_state"
        assert row["observation_after"]["joint_velocity"][0] is None
        assert {"path": "/observation_after/joint_velocity/0", "value": "+inf"} in row["invalid_numeric_fields"]
        assert {"path": "/qpos/8", "value": "nan"} in row["invalid_numeric_fields"]
    for trial in _read(output / "trials.json"):
        assert trial["status"] == "terminated"
        assert trial["reason"] == "nonfinite_state"
        assert trial["peak_joint_speed_rad_s"] is None
        assert trial["joint_excursion_rms_rad"] is None
        assert trial["invalid_numeric_fields"]
    _assert_manifest(output)


def test_exception_after_integration_keeps_budget_and_reraises(tmp_path, monkeypatch):
    base = collection.GroundBodyEnv

    class StepExceptionEnv(base):
        def step(self, command):
            result = super().step(command)
            if self.step_id == 2:
                raise RuntimeError("injected failure after integration")
            return result

    monkeypatch.setattr(collection, "GroundBodyEnv", StepExceptionEnv)
    output = tmp_path / "exception"
    with pytest.raises(RuntimeError, match="injected failure"):
        collection.collect(output, seeds=[0], steps=3)
    metadata = _read(output / "metadata.json")
    assert metadata["archive_status"] == "failed"
    assert metadata["complete"] is False
    assert metadata["exception_trials"] == metadata["trial_count"] == 1
    assert metadata["control_steps"] == metadata["control_calls_attempted"] == 2
    assert metadata["physics_steps"] == 20
    assert metadata["collector_exception"]["type"] == "RuntimeError"
    trial = _read(output / "trials.json")[0]
    assert trial["status"] == "exception"
    assert trial["reason"] == "collector_exception"
    assert trial["metric_samples"] == 1  # partial metrics are explicitly marked
    assert trial["simulated_seconds"] == pytest.approx(.04)
    assert trial["final_endpoint"]["qpos"] == trial["final_qpos"]
    rows = _trace(output)
    assert len(rows) == 2
    assert rows[-1]["collector_exception"]["message"] == "injected failure after integration"
    assert rows[-1]["diagnostics"]["physics_steps"] == 20
    _assert_manifest(output)


def test_successful_trials_checkpoint_before_starting_the_next(tmp_path, monkeypatch):
    base = collection.GroundBodyEnv
    output = tmp_path / "checkpoint"
    constructions = []

    class CheckpointInspectingEnv(base):
        def __init__(self, config):
            if constructions:
                metadata = _read(output / "metadata.json")
                assert metadata["archive_status"] == "running"
                assert metadata["complete"] is False
                assert metadata["trial_count"] == len(constructions)
                assert len(_read(output / "trials.json")) == len(constructions)
            constructions.append(None)
            super().__init__(config)

    monkeypatch.setattr(collection, "GroundBodyEnv", CheckpointInspectingEnv)
    metadata = collection.collect(output, seeds=[0], steps=1)
    assert metadata["trial_count"] == len(constructions) == 8
    assert metadata["complete"] is True
    assert metadata["control_steps"] == 8
    assert metadata["physics_steps"] == 80
    assert len(_trace(output)) == 8
    _assert_manifest(output)
