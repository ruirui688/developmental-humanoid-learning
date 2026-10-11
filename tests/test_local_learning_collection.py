import gzip
import json

import pytest

pytest.importorskip("mujoco")
from developmental_physics import local_learning as runner


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_learning_updates_only_calibration_and_evaluation_is_frozen(tmp_path):
    out = tmp_path / "local"
    meta = runner.run_learning(out, "supine", 0, [0])
    assert meta["complete"] and meta["model_updates"] == 300
    assert meta["control_steps"] == meta["control_calls_attempted"] == 1800
    assert meta["physics_steps"] == 18000
    seed = read(out / "seed_results.json")[0]
    assert seed["initial_model"]["update_count"] == 0
    assert seed["learned_model"]["update_count"] == 300
    for name, trial in seed["evaluations"].items():
        assert trial["completed"]
        if name != "calibration":
            assert trial["models_before"] == trial["models_after"]
    with gzip.open(out / "trace.jsonl.gz", "rt", encoding="utf-8") as stream:
        rows = [json.loads(line) for line in stream]
    calibration_prefix = [r for r in rows if r["kind"] == "calibration" and r["phase"] == "prefix"]
    for kind in ("prediction", "frozen_mpc", "learned_mpc", "fixed_pd", "zero_torque"):
        prefix = [r for r in rows if r["kind"] == kind and r["phase"] == "prefix"]
        assert [r["observation_after"] for r in prefix] == [r["observation_after"] for r in calibration_prefix]
    for row in rows:
        update = row["model_update"]
        if update is not None:
            assert row["phase"] == "calibration"
            assert update["features"][2] == row["requested_torque"][0]
            assert update["observed_next_v_rad_s"] == row["observation_after"]["joint_velocity"][0]
            assert update["preupdate_prediction"]["next_v_rad_s"] == row["predicted_next_qv"]["learned"][1]
        assert all(abs(u) <= .5 for u in row["requested_torque"])
        assert row["requested_torque"][1:] == [0.] * 7
    with pytest.raises(FileExistsError):
        runner.run_learning(out, "supine", 0, [0])


def test_integration_fault_cost_and_prefix_has_no_updates(tmp_path, monkeypatch):
    original = runner.mujoco.mj_forward
    def fail(model, data):
        if data.time > .02+1e-9:
            raise RuntimeError("injected RLS prefix fault")
        return original(model, data)
    monkeypatch.setattr(runner.mujoco, "mj_forward", fail)
    out = tmp_path / "fault"
    with pytest.raises(RuntimeError, match="injected"):
        runner.run_learning(out, "supine", 0, [0])
    meta = read(out / "metadata.json")
    assert not meta["complete"] and meta["model_updates"] == 0
    assert meta["control_calls_attempted"] == 2
    assert meta["control_steps"] == 1 and meta["physics_steps"] == 11
    episode = read(out / "episodes.json")[0]
    assert episode["phase_budgets"]["prefix"]["physics_steps"] == 11
