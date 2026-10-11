import gzip
import hashlib
import json

import pytest

pytest.importorskip("mujoco")
from developmental_physics import probe_collect as collection


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_short_shared_zero_probe_matrix_and_budget(tmp_path):
    out = tmp_path / "probes"
    meta = collection.collect_probes(out, [0], poses=["supine"], joints=[0],
        amplitudes=[.125, .5], prefix_steps=2, pulse_steps=2, recovery_steps=1)
    trials = read(out / "trials.json")
    assert len(trials) == 3 and len({t["trial_id"] for t in trials}) == 3
    assert [t["mode"] for t in trials] == ["zero_torque", "joint_probe", "joint_probe"]
    assert meta["control_calls_attempted"] == meta["control_steps"] == 15
    assert meta["physics_steps"] == 150
    assert meta["phase_budgets"]["prefix"]["physics_steps"] == 60
    assert meta["phase_budgets"]["probe"]["physics_steps"] == 60
    assert meta["phase_budgets"]["recovery"]["physics_steps"] == 30
    with gzip.open(out / "trace.jsonl.gz", "rt", encoding="utf-8") as stream:
        rows = [json.loads(line) for line in stream]
    for i in (5, 10):
        for j in range(2):
            assert rows[j]["observation_after"] == rows[i+j]["observation_after"]
        assert any(rows[i+2]["diagnostics"]["requested_torque"])
    for trial in trials:
        assert trial["environment_fingerprint_before"] == trial["environment_fingerprint_after"]
        assert trial["actor_fingerprint_before"] == trial["actor_fingerprint_after"]
    for name, digest in read(out / "manifest.json").items():
        assert hashlib.sha256((out/name).read_bytes()).hexdigest() == digest
    with pytest.raises(FileExistsError):
        collection.collect_probes(out, [0])


def test_fault_retains_partial_substep_phase_cost(tmp_path, monkeypatch):
    original = collection.mujoco.mj_forward
    def fail(model, data):
        if data.time > .04 + 1e-9:
            raise RuntimeError("injected probe integration failure")
        return original(model, data)
    monkeypatch.setattr(collection.mujoco, "mj_forward", fail)
    out = tmp_path / "fault"
    with pytest.raises(RuntimeError, match="injected"):
        collection.collect_probes(out, [0], poses=["supine"], joints=[0],
            amplitudes=[.5], prefix_steps=2, pulse_steps=2, recovery_steps=1)
    meta = read(out / "metadata.json")
    assert not meta["complete"]
    assert meta["control_calls_attempted"] == 3
    assert meta["control_steps"] == 2 and meta["physics_steps"] == 21
    assert meta["phase_budgets"]["prefix"]["physics_steps"] == 20
    assert meta["phase_budgets"]["probe"]["physics_steps"] == 1
    assert meta["exception_trials"] == 1


@pytest.mark.parametrize("kwargs", [dict(seeds=[]), dict(seeds=[0,0]),
    dict(seeds=[0], joints=[True]), dict(seeds=[0], amplitudes=[.6])])
def test_invalid_matrix_does_not_create_output(tmp_path, kwargs):
    out = tmp_path / "invalid"
    with pytest.raises(ValueError):
        collection.collect_probes(out, **kwargs)
    assert not out.exists()
