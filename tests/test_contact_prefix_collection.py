"""Paired command streams and paid prefixes for optional no-training physics."""

from __future__ import annotations

import gzip
import hashlib
import json
from collections import defaultdict

import pytest

pytest.importorskip("mujoco")

from developmental_physics import collect as collection


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def rows(path):
    with gzip.open(path / "trace.jsonl.gz", "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream]


def test_prefix_budget_random_stream_and_zero_control_pairing(tmp_path):
    output = tmp_path / "matrix"
    metadata = collection.collect(output, [0], 4,
                                  contact_profiles=["baseline", "compliant"],
                                  prefix_steps=[0, 2])
    assert metadata["complete"] and metadata["trial_count"] == 32
    assert metadata["control_steps"] == metadata["maximum_control_steps"] == 128
    assert metadata["physics_steps"] == metadata["maximum_physics_steps"] == 1280
    assert metadata["prefix_control_steps"] == 32
    assert metadata["prefix_physics_steps"] == 320
    assert metadata["exploration_control_steps"] == 96
    assert metadata["exploration_physics_steps"] == 960
    assert metadata["prefix_control_calls_attempted"] == 32
    assert metadata["exploration_control_calls_attempted"] == 96
    assert metadata["parameter_updates"] == {"model": 0, "policy": 0, "gate": 0}
    by_trial = defaultdict(list)
    for row in rows(output):
        by_trial[row["trial_id"]].append(row)
    for profile in ("baseline", "compliant"):
        for pose in collection.POSES:
            zero = by_trial[f"{profile}_prefix0_{pose}_seed0_zero_torque"]
            delayed_zero = by_trial[f"{profile}_prefix2_{pose}_seed0_zero_torque"]
            random = by_trial[f"{profile}_prefix0_{pose}_seed0_smooth_random"]
            delayed = by_trial[f"{profile}_prefix2_{pose}_seed0_smooth_random"]
            for a, b in zip(zero, delayed_zero):
                assert a["qpos"] == b["qpos"] and a["qvel"] == b["qvel"]
                assert a["observation_after"] == b["observation_after"]
                assert a["diagnostics"] == b["diagnostics"]
            for index, row in enumerate(delayed):
                assert row["phase"] == ("prefix" if index < 2 else "exploration")
                assert row["action_index"] == (None if index < 2 else index - 2)
                if index < 2:
                    assert row["diagnostics"]["requested_torque"] == [0.] * 8
                    assert row["qpos"] == delayed_zero[index]["qpos"]
                else:
                    assert row["diagnostics"]["requested_torque"] == random[index - 2]["diagnostics"]["requested_torque"]
    for trial in read(output / "trials.json"):
        assert trial["environment_fingerprint_before"] == trial["environment_fingerprint_after"]
        assert trial["explorer_fingerprint_before"] == trial["explorer_fingerprint_after"]
    for name, digest in read(output / "manifest.json").items():
        assert hashlib.sha256((output / name).read_bytes()).hexdigest() == digest


@pytest.mark.parametrize("kwargs", [
    {"prefix_steps": []}, {"prefix_steps": [-1]}, {"prefix_steps": [4]},
    {"prefix_steps": [True]}, {"prefix_steps": [0, 0]},
    {"contact_profiles": []}, {"contact_profiles": ["unknown"]},
    {"contact_profiles": ["baseline", "baseline"]},
])
def test_invalid_matrix_rejected_before_creating_archive(tmp_path, kwargs):
    output = tmp_path / "invalid"
    with pytest.raises(ValueError):
        collection.collect(output, [0], 4, **kwargs)
    assert not output.exists()


def test_exception_counts_paid_prefix_and_partial_exploration(tmp_path, monkeypatch):
    base = collection.GroundBodyEnv

    class StepExceptionEnv(base):
        def step(self, command):
            result = super().step(command)
            if self.step_id == 3:
                raise RuntimeError("failure after first exploration integration")
            return result

    monkeypatch.setattr(collection, "GroundBodyEnv", StepExceptionEnv)
    output = tmp_path / "failed"
    with pytest.raises(RuntimeError, match="first exploration"):
        collection.collect(output, [0], 4, contact_profiles=["baseline"], prefix_steps=[2])
    metadata = read(output / "metadata.json")
    assert not metadata["complete"] and metadata["exception_trials"] == 1
    assert metadata["control_steps"] == 3 and metadata["physics_steps"] == 30
    assert metadata["prefix_control_steps"] == 2 and metadata["prefix_physics_steps"] == 20
    assert metadata["exploration_control_steps"] == 1 and metadata["exploration_physics_steps"] == 10
    assert rows(output)[-1]["collector_exception"]
    assert rows(output)[-1]["prefix_steps"] == 2
    assert read(output / "trials.json")[0]["metric_samples"] == 2


def test_frozen_protocol_is_in_source_snapshot(tmp_path):
    protocol = collection.Path(__file__).resolve().parents[1] / "docs/GROUND_CONTACT_PREFIX_PROTOCOL.md"
    output = tmp_path / "with_protocol"
    metadata = collection.collect(output, [0], 1, protocol_path=protocol)
    name = "docs/GROUND_CONTACT_PREFIX_PROTOCOL.md"
    assert metadata["protocol"]["path"] == name
    assert metadata["protocol"]["sha256"] == metadata["source_sha256"][name]
    with collection.zipfile.ZipFile(output / "source_snapshot.zip") as snapshot:
        assert snapshot.read(name) == protocol.read_bytes()


def test_exception_inside_first_active_call_keeps_attempt_and_substep_budget(tmp_path, monkeypatch):
    original = collection.mujoco.mj_forward

    def fail_after_one_active_substep(model, data):
        if data.time > .04 + 1e-9:
            raise RuntimeError("forward failed during first active call")
        return original(model, data)

    monkeypatch.setattr(collection.mujoco, "mj_forward", fail_after_one_active_substep)
    output = tmp_path / "partial_call"
    with pytest.raises(RuntimeError, match="first active call"):
        collection.collect(output, [0], 4, contact_profiles=["baseline"], prefix_steps=[2])
    metadata = read(output / "metadata.json")
    assert metadata["control_steps"] == 2  # wrapper has not completed call 3
    assert metadata["control_calls_attempted"] == 3
    assert metadata["prefix_control_calls_attempted"] == 2
    assert metadata["exploration_control_calls_attempted"] == 1
    assert metadata["physics_steps"] == 21
    assert metadata["prefix_physics_steps"] == 20
    assert metadata["exploration_physics_steps"] == 1
    error_row = rows(output)[-1]
    assert error_row["phase"] == "exploration" and error_row["action_index"] == 0
    assert error_row["diagnostics"]["physics_steps"] == 21
