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
    meta = runner.run_learning(out, "supine", 0, [0])
    meta = read(out / "metadata.json")
    assert meta["complete"] and not meta["all_trials_successful"] and meta["model_updates"] == 0
    assert meta["control_calls_attempted"] == 2
    assert meta["control_steps"] == 1 and meta["physics_steps"] == 11
    episodes = read(out / "episodes.json")
    assert len(episodes) == meta["planned_episode_count"] == 6
    episode = episodes[0]
    assert episode["phase_budgets"]["prefix"]["physics_steps"] == 11
    assert episode["status"] == "exception" and "injected" in episode["reason"]["message"]
    assert all(e["status"] == "blocked" for e in episodes[1:])
    assert meta["exception_trials"] == 1 and meta["blocked_trials"] == meta["skipped_trials"] == 5
    assert meta["unprocessed_trials"] == 0


def test_real_prefix_stop_preserves_reason_blocks_dependents_and_continues_seed(tmp_path, monkeypatch):
    original = runner.GroundBodyEnv
    count = 0

    def make_env():
        nonlocal count
        count += 1
        if count == 1:
            return original(runner.ExplorationConfig(kinetic_energy_limit=1e-9))
        return original()

    monkeypatch.setattr(runner, "GroundBodyEnv", make_env)
    out = tmp_path / "early_stop"
    meta = runner.run_learning(out, "supine", 0, [0, 1])
    episodes = read(out / "episodes.json")
    seeds = read(out / "seed_results.json")
    first = episodes[0]
    assert first["status"] == "terminated" and first["reason"] == "kinetic_energy_limit"
    assert first["collector_exception"] is None and first["control_steps"] < 100
    assert first["physics_steps"] > 0
    assert all(e["status"] == "blocked" for e in episodes[1:6])
    assert seeds[0]["calibration_updates"] == 0 and seeds[0]["learned_model"] is None
    assert seeds[1]["calibration_completed"] and seeds[1]["calibration_updates"] == 300
    assert all(e["status"] == "completed" for e in episodes[6:])
    assert meta["complete"] and not meta["all_trials_successful"]
    assert meta["terminated_trials"] == 1 and meta["exception_trials"] == 0


def test_evaluation_prefix_stop_does_not_claim_model_change_or_abort_other_methods(tmp_path, monkeypatch):
    original = runner.GroundBodyEnv
    count = 0

    def make_env():
        nonlocal count
        count += 1
        if count == 2:  # Calibration succeeds; prediction stops during its prefix.
            return original(runner.ExplorationConfig(kinetic_energy_limit=1e-9))
        return original()

    monkeypatch.setattr(runner, "GroundBodyEnv", make_env)
    out = tmp_path / "evaluation_stop"
    meta = runner.run_learning(out, "supine", 0, [0])
    episodes = read(out / "episodes.json")
    seed = read(out / "seed_results.json")[0]
    assert episodes[1]["status"] == "terminated" and episodes[1]["reason"] == "kinetic_energy_limit"
    prediction = seed["evaluations"]["prediction"]
    assert prediction["models_before"] == prediction["models_after"]
    assert not prediction["completed"]
    assert all(e["status"] == "completed" for e in episodes[2:])
    assert meta["complete"] and meta["exception_trials"] == 0 and meta["terminated_trials"] == 1


def test_infeasible_target_is_recorded_and_other_methods_and_seed_continue(tmp_path, monkeypatch):
    original = runner.FixedLocalMPC

    class InfeasibleFirstController(original):
        def select(self, *args, **kwargs):
            raise ValueError("injected target infeasible in fixed controller")

    controllers = 0

    def planner(*args, **kwargs):
        nonlocal controllers
        controllers += 1
        return (InfeasibleFirstController if controllers == 1 else original)(*args, **kwargs)

    monkeypatch.setattr(runner, "FixedLocalMPC", planner)
    out = tmp_path / "target_failure"
    meta = runner.run_learning(out, "supine", 0, [0, 1])
    episodes = read(out / "episodes.json")
    assert len(episodes) == 12
    failed = episodes[2]
    assert failed["kind"] == "frozen_mpc" and failed["status"] == "exception"
    assert "target infeasible" in failed["reason"]["message"]
    assert failed["control_steps"] == 100
    assert all(e["status"] == "completed" for e in episodes[3:])
    assert meta["complete"] and meta["exception_trials"] == 1 and meta["blocked_trials"] == 0


def test_trace_write_failure_after_update_saves_snapshot_and_exact_cost(tmp_path, monkeypatch):
    original_open = runner.gzip.open

    class FailingTrace:
        def __init__(self, wrapped):
            self.wrapped = wrapped
            self.failed = False

        def __enter__(self):
            self.wrapped.__enter__()
            return self

        def __exit__(self, *args):
            return self.wrapped.__exit__(*args)

        def write(self, text):
            row = json.loads(text)
            if self.failed or row.get("model_update") is not None:
                self.failed = True
                raise OSError("injected trace disk fault after RLS update")
            return self.wrapped.write(text)

    def open_trace(*args, **kwargs):
        return FailingTrace(original_open(*args, **kwargs))

    monkeypatch.setattr(runner.gzip, "open", open_trace)
    out = tmp_path / "write_failure"
    with pytest.raises(OSError, match="trace disk fault"):
        runner.run_learning(out, "supine", 0, [0, 1])
    seed = read(out / "seed_results.json")[0]
    metadata = read(out / "metadata.json")
    episodes = read(out / "episodes.json")
    assert seed["calibration_updates"] == seed["learned_model"]["update_count"] == 1
    assert seed["learned_model"]["coefficients"] != seed["initial_model"]["coefficients"]
    assert seed["learned_model"]["parameter_fingerprint"] != seed["initial_model"]["parameter_fingerprint"]
    assert not seed["learned_model"]["trainable"]
    assert metadata["model_updates"] == 1 and not metadata["complete"]
    assert metadata["control_calls_attempted"] == metadata["control_steps"] == 101
    assert metadata["physics_steps"] == 1010
    assert len(episodes) == 12 and all(e["status"] == "blocked" for e in episodes[1:])
    assert episodes[0]["status"] == "exception"
    assert episodes[0]["phase_budgets"]["calibration"]["control_steps"] == 1
    assert metadata["blocked_trials"] == 11 and metadata["unprocessed_trials"] == 0
    assert (out / "manifest.json").is_file()


def test_predeclared_public_target_check_preserves_failure_in_every_seed(tmp_path, monkeypatch):
    original = runner.direction_record

    def select_outward_direction(*args, **kwargs):
        record = original(*args, **kwargs)
        # A fault in a shared direction selector makes the knee target point
        # out of its public range; the runner must retain and report the gate.
        record["direction"] = -1
        return record

    monkeypatch.setattr(runner, "direction_record", select_outward_direction)
    out = tmp_path / "public_target_failure"
    meta = runner.run_learning(out, "supine", 5, [0, 1])
    episodes = read(out / "episodes.json")
    seeds = read(out / "seed_results.json")
    assert len(episodes) == 12 and len(seeds) == 2
    for index in (2, 3, 4, 5, 8, 9, 10, 11):
        episode = episodes[index]
        assert episode["status"] == "exception"
        assert episode["reason"]["message"] == "predeclared target outside public interior; do not clip"
        assert episode["control_steps"] == 100
    assert all(seed["calibration_completed"] for seed in seeds)
    assert meta["complete"] and meta["exception_trials"] == 8 and meta["blocked_trials"] == 0


@pytest.mark.parametrize("interrupt", [KeyboardInterrupt, SystemExit])
def test_interrupt_is_rethrown_after_preserving_all_planned_episode_costs(tmp_path, monkeypatch, interrupt):
    original = runner.GroundBodyEnv.step

    def stop(env, requested):
        if env.step_id == 1:
            raise interrupt("injected interruption")
        return original(env, requested)

    monkeypatch.setattr(runner.GroundBodyEnv, "step", stop)
    out = tmp_path / interrupt.__name__
    with pytest.raises(interrupt, match="interruption"):
        runner.run_learning(out, "supine", 0, [0, 1])
    meta = read(out / "metadata.json")
    episodes = read(out / "episodes.json")
    assert not meta["complete"] and meta["archive_status"] == "interrupted"
    assert meta["control_calls_attempted"] == 2 and meta["control_steps"] == 1
    assert meta["physics_steps"] == 10 and meta["model_updates"] == 0
    assert len(episodes) == 12 and meta["blocked_trials"] == 11
    assert episodes[0]["collector_exception"]["type"] == interrupt.__name__
