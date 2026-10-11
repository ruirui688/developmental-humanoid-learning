"""C2-C synthetic accounting/study-stop tests. No MuJoCo physical step."""
from collections import Counter
import gzip
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

pytest.importorskip("mujoco")
from developmental_physics import local_coverage_ablation as runner


ROOT = next(p for p in Path(__file__).resolve().parents if (p/"pyproject.toml").is_file())
PROTOCOL = ROOT / "docs/LOCAL_COVERAGE_ABLATION_PROTOCOL.md"


class SyntheticEnv:
    instances = []
    fail_trial = fail_step = None
    interrupt = False

    def __init__(self):
        self.trial = len(SyntheticEnv.instances)
        SyntheticEnv.instances.append(self)
        self.config = SimpleNamespace(physics_dt=.002)
        self.control_dt = .02
        self.joint_names = [str(i) for i in range(8)]
        self.model = SimpleNamespace(joint=lambda name: SimpleNamespace(range=np.array([-1., 1.])))
        self.data = SimpleNamespace(qpos=np.zeros(8), qvel=np.zeros(8))
        self.step_id = self.physics_steps = 0
        self.terminated = False
        self.reason = None
        self.command = np.zeros(8)
        self.commands = []

    def reset(self, seed, pose):
        assert pose == "supine"
        self.data.qpos[:] = self.data.qvel[:] = 0.
        return self.observation()

    def parameter_fingerprint(self):
        return "synthetic fixed body"

    def observation(self):
        return {"joint_position": self.data.qpos.copy(), "joint_velocity": self.data.qvel.copy(),
                "previous_command": self.command.copy()}

    def diagnostics(self):
        return {"executed_substeps": 0, "applied_torque_history": [], "terminated": self.terminated}

    def step(self, request):
        if self.trial == self.fail_trial and self.step_id == self.fail_step:
            self.physics_steps += 3
            if self.interrupt:
                raise KeyboardInterrupt()
            raise RuntimeError("injected partial step")
        self.command = request.copy()
        self.commands.append(request.copy())
        self.data.qvel = .5*self.data.qvel + .02*request
        self.data.qpos += .02*self.data.qvel
        self.step_id += 1
        self.physics_steps += 10
        return SimpleNamespace(observation=self.observation(), diagnostics={
            "executed_substeps": 10, "applied_torque_history": [request.tolist()]*10,
            "terminated": False}, terminated=False)


class CheapPlanner:
    def __init__(self, model, joint_range):
        self.model = model

    def select(self, q, v, target_q, previous_torque=0.):
        u = float(np.clip(2*(target_q-q)-.2*v, -.5, .5))
        self.model.predict(q, v, u)
        return SimpleNamespace(torque=u, fallback=False, mathematical_prediction_calls=1,
                               to_dict=lambda: {"torque":u,"fallback":False,"mathematical_prediction_calls":1})

    def spec(self):
        return {"synthetic_test": True, "physical_queries": 0}


@pytest.fixture(autouse=True)
def synthetic_only(monkeypatch):
    SyntheticEnv.instances = []
    SyntheticEnv.fail_trial = SyntheticEnv.fail_step = None
    SyntheticEnv.interrupt = False
    monkeypatch.setattr(runner, "GroundBodyEnv", SyntheticEnv)
    monkeypatch.setattr(runner, "FixedLocalMPC", CheapPlanner)


def read(output, name):
    return json.loads((output/name).read_text(encoding="utf-8"))


def run(output, **kwargs):
    return runner.run_ablation(output, [0,1,2], integration="endpoint_euler", protocol_path=PROTOCOL, **kwargs)


def trace(output):
    with gzip.open(output/"trace.jsonl.gz", "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream]


def test_complete_fixed_recipe_budget_freeze_and_command_histogram(tmp_path):
    output = tmp_path/"complete"
    metadata = run(output)
    assert metadata["complete"] and metadata["all_trials_successful"]
    assert metadata["planned_episode_count"] == metadata["completed_trials"] == 21
    assert metadata["control_calls_attempted"] == metadata["control_steps"] == 6300
    assert metadata["physics_steps"] == 63000 and metadata["model_updates"] == 1800
    assert metadata["calibration_dose"] == "old" and metadata["structures"] == ["hinge5"]
    assert "target-position control" in metadata["initial_controller_capability"]
    episodes = read(output, "episodes.json")
    phases = {p:sum(e["phase_budgets"][p]["control_steps"] for e in episodes)
              for p in ("prefix","calibration","prediction","control")}
    assert phases == {"prefix":2100,"calibration":1800,"prediction":600,"control":1800}
    for sr in read(output, "seed_results.json"):
        assert sr["calibration_completed"] == {"short":True,"reordered":True}
        assert sr["calibration_updates"] == 600 and len(sr["learned_models"]) == 2
        assert set(sr["integration_models"]) == {"nominal_mpc","short_mpc","reordered_mpc"}
        for name, model in sr["learned_models"].items():
            assert model["update_count"] == 300 and not model["trainable"]
            assert sr["initial_models"][name]["coefficients"] == [1.,0.,.02,0.,0.]
            assert np.array_equal(sr["initial_models"][name]["covariance"],100*np.eye(5))
        for name, result in sr["evaluations"].items():
            assert result["study_abort"] is None
            assert all(result["phase_actual_effort_complete"].values())
            if not name.startswith("calibration_"):
                assert result["models_before"] == result["models_after"]
                assert result["integration_models_before"] == result["integration_models_after"]
        for schedule in ("short","reordered"):
            effort = sr["evaluations"][f"calibration_{schedule}"]["phase_effort"]["calibration"]
            assert effort["requested_absolute_nm_s"] == pytest.approx(.55)
            assert effort["requested_squared_nm2_s"] == pytest.approx(.20)
    rows = trace(output)
    assert len(rows) == 6300
    for row in rows:
        assert row["study_abort"] is None
        if row["phase"] == "prefix":
            assert row["requested_torque"] == [0.]*8 and row["model_update"] is None
        elif row["phase"] == "calibration":
            assert set(row["model_update"]) == {"hinge5"}
            item = row["model_update"]["hinge5"]
            assert item["shared_transition_id"] == row["shared_transition_id"]
            assert item["model_id"] == f'{row["calibration_schedule"]}_hinge5'
            assert item["update_count"] == row["step_index"]-99
        else:
            assert row["model_update"] is None
            assert set(row["predicted_next_qv"]) == {"nominal_mpc","short_mpc","reordered_mpc","persistence"}
    short = [r["requested_torque"][0] for r in rows if r["trial_id"] == "seed0_calibration_short" and r["phase"] == "calibration"]
    reordered = [r["requested_torque"][0] for r in rows if r["trial_id"] == "seed0_calibration_reordered" and r["phase"] == "calibration"]
    assert Counter(short) == Counter(reordered)
    assert sum(u != v for u,v in zip([0.]+short,short)) == 40
    assert sum(u != v for u,v in zip([0.]+reordered,reordered)) == 22
    with pytest.raises(FileExistsError):
        run(output)


@pytest.mark.parametrize("trial", range(7))
@pytest.mark.parametrize("trigger", ("q", "v"))
def test_study_abort_all_active_trials_preserves_terminal_without_feedback(tmp_path, monkeypatch, trial, trigger):
    original = SyntheticEnv.step
    def stop(env, request):
        mark = env.trial == trial and env.step_id == 100
        result = original(env, request)
        if mark:
            if trigger == "q":
                env.data.qpos[0] = .12
            else:
                env.data.qvel[0] = 1.
            result.observation = env.observation()
        return result
    monkeypatch.setattr(SyntheticEnv, "step", stop)
    output = tmp_path/f"study_{trial}_{trigger}"
    metadata = run(output)
    episode = read(output,"episodes.json")[trial]
    assert metadata["complete"] and not metadata["all_trials_successful"]
    assert episode["status"] == "terminated" and episode["collector_exception"] is None
    assert episode["reason"]["type"] == "StudyAbort" and episode["study_abort"] == episode["reason"]
    assert episode["environment_terminated"] is False and episode["environment_stop_reason"] is None
    assert episode["control_steps"] == 101 and episode["physics_steps"] == 1010
    assert not SyntheticEnv.instances[trial].terminated and len(SyntheticEnv.instances[trial].commands) == 101
    assert episode["risk_telemetry_complete"]
    rows = [r for r in trace(output) if r["trial_id"] == episode["trial_id"]]
    assert len(rows) == 101 and rows[-1]["study_abort"]["stage"] == "endpoint"
    assert not rows[-1]["diagnostics"]["terminated"]
    assert rows[-1]["study_abort"]["feedback_action"] is None
    sr = read(output,"seed_results.json")[0]
    if trial < 2:
        schedule = "short" if trial == 0 else "reordered"
        assert sr["calibration_models"][schedule]["hinge5"]["update_count"] == 1
        assert rows[-1]["model_update"]["hinge5"]["updated"]
        assert not sr["calibration_completed"][schedule]
        assert all(read(output,"episodes.json")[i]["status"] == "blocked" for i in (2,3,4+trial))
        assert sr["evaluations"]["nominal_mpc"]["completed"]
        assert metadata["model_updates"] == 1501
    else:
        assert rows[-1]["predicted_next_qv"] and rows[-1]["model_update"] is None
        assert metadata["model_updates"] == 1800
        if trial >= 4:
            assert sr["evaluations"][episode["kind"]]["metric_control_step_count"] == 1


def test_prefix_high_state_does_not_activate_research_stop(tmp_path, monkeypatch):
    original = SyntheticEnv.step
    def prefix(env, request):
        step = env.step_id
        result = original(env, request)
        if step == 5:
            env.data.qvel[0] = 1.
            result.observation = env.observation()
        elif step == 6:
            env.data.qvel[0] = env.data.qpos[0] = 0.
            result.observation = env.observation()
        return result
    monkeypatch.setattr(SyntheticEnv,"step",prefix)
    output = tmp_path/"prefix"
    assert run(output)["all_trials_successful"]
    rows = trace(output)
    assert any(r["phase"] == "prefix" and r["observation_after"]["joint_velocity"][0] == 1. for r in rows)
    assert all(r["study_abort"] is None for r in rows)


def test_last_prefix_velocity_does_not_activate_active_endpoint_rule_early(tmp_path, monkeypatch):
    original = SyntheticEnv.step
    def prefix(env, request):
        mark = env.trial == 0 and env.step_id == 99
        result = original(env, request)
        if mark:
            env.data.qvel[0] = 1.
            result.observation = env.observation()
        return result
    monkeypatch.setattr(SyntheticEnv,"step",prefix)
    output = tmp_path/"prefix_last"
    assert run(output)["all_trials_successful"]
    episode = read(output,"episodes.json")[0]
    assert episode["status"] == "completed" and episode["control_steps"] == 400
    assert episode["phase_budgets"]["calibration"]["control_calls_attempted"] == 300
    assert read(output,"seed_results.json")[0]["calibration_models"]["short"]["hinge5"]["update_count"] == 300
    assert len(SyntheticEnv.instances[0].commands) == 400


@pytest.mark.parametrize("substeps", [0,3,10])
def test_environment_stop_keeps_original_reason_and_full_interval_rule(tmp_path, monkeypatch, substeps):
    original = SyntheticEnv.step
    def stop(env, request):
        mark = env.trial == 0 and env.step_id == 100
        result = original(env,request)
        if mark:
            env.physics_steps -= 10-substeps
            env.terminated = result.terminated = True
            env.reason = "independent_environment_stop"
            env.data.qpos[0] = .12
            result.observation = env.observation()
            result.diagnostics.update(executed_substeps=substeps, applied_torque_history=[request.tolist()]*substeps,terminated=True)
        return result
    monkeypatch.setattr(SyntheticEnv,"step",stop)
    output = tmp_path/f"partial_{substeps}"
    run(output)
    episode = read(output,"episodes.json")[0]
    assert episode["reason"] == "independent_environment_stop"
    assert episode["environment_terminated"] is True and episode["environment_stop_reason"] == episode["reason"]
    assert episode["study_abort"]["type"] == "StudyAbort"
    assert episode["physics_steps"] == 1000+substeps
    sr = read(output,"seed_results.json")[0]
    assert sr["calibration_models"]["short"]["hinge5"]["update_count"] == int(substeps == 10)
    effort=sr["evaluations"]["calibration_short"]["phase_effort"]["calibration"]
    assert effort["requested_absolute_nm_s"] == pytest.approx(.125*.002*substeps)
    assert effort["actual_absolute_nm_s"] == pytest.approx(.125*.002*substeps)
    row=next(r for r in trace(output) if r["trial_id"] == "seed0_calibration_short" and r["phase"] == "calibration")
    assert row["model_update"]["hinge5"]["updated"] == (substeps == 10)


def test_unreturned_substeps_pay_request_preserve_parameters_and_block_dependencies(tmp_path):
    SyntheticEnv.fail_trial,SyntheticEnv.fail_step = 0,101
    output=tmp_path/"ordinary_fault"
    metadata=run(output)
    sr=read(output,"seed_results.json")[0]
    episode=read(output,"episodes.json")[0]
    assert metadata["complete"] and episode["status"] == "exception"
    assert episode["physics_steps"] == 1013 and not episode["risk_telemetry_complete"]
    assert sr["calibration_models"]["short"]["hinge5"]["update_count"] == 1
    result=sr["evaluations"]["calibration_short"]
    assert not result["phase_actual_effort_complete"]["calibration"]
    assert result["phase_effort"]["calibration"]["requested_absolute_nm_s"] == pytest.approx(.125*.026)
    assert metadata["model_updates"] == 1501 and metadata["physics_steps"] == 53013


def test_interrupt_is_fatal_and_preserves_partial_paid_cost(tmp_path):
    SyntheticEnv.fail_trial,SyntheticEnv.fail_step,SyntheticEnv.interrupt = 0,101,True
    output=tmp_path/"interrupt"
    with pytest.raises(KeyboardInterrupt):
        run(output)
    metadata=read(output,"metadata.json")
    assert metadata["archive_status"] == "interrupted" and not metadata["complete"]
    assert metadata["physics_steps"] == 1013 and metadata["model_updates"] == 1
    assert all(e["status"] == "blocked" for e in read(output,"episodes.json")[1:])


def test_cpu_seconds_checkpoint_is_nonnegative_and_scope_is_disclosed(tmp_path):
    SyntheticEnv.fail_trial,SyntheticEnv.fail_step,SyntheticEnv.interrupt = 0,2,True
    output=tmp_path/"timing_checkpoint"
    with pytest.raises(KeyboardInterrupt):
        run(output)
    metadata=read(output,"metadata.json")
    assert metadata["cpu_seconds"] >= 0. and metadata["wall_seconds"] >= 0.
    assert "same timer-start/checkpoint scope as wall_seconds" in metadata["cpu_seconds_scope"]
    assert "excludes imports, initial source snapshot" in metadata["cpu_seconds_scope"]


def test_checkpoint_io_failure_is_fatal_and_saved_parameters_survive(tmp_path,monkeypatch):
    original=runner._write_json
    calls=0
    def fault(path,value):
        nonlocal calls
        if path.name == "seed_results.json":
            calls+=1
            if calls == 2:
                raise OSError("injected checkpoint write")
        return original(path,value)
    monkeypatch.setattr(runner,"_write_json",fault)
    output=tmp_path/"checkpoint"
    with pytest.raises(OSError,match="checkpoint write"):
        run(output)
    metadata=read(output,"metadata.json")
    assert metadata["archive_status"] == "failed" and metadata["physics_steps"] == 4000
    assert metadata["model_updates"] == 300 and len(SyntheticEnv.instances) == 1
    assert read(output,"seed_results.json")[0]["calibration_models"]["short"]["hinge5"]["update_count"] == 300


@pytest.mark.parametrize("field,value",[("calibration_dose","new"),("calibration_dose",False),
                                         ("model_structure","linear4"),("model_structure",None)])
def test_rejects_unfrozen_recipe_before_creating_output(tmp_path,field,value):
    output=tmp_path/"bad_recipe"
    with pytest.raises(ValueError,match="frozen"):
        run(output,**{field:value})
    assert not output.exists() and not SyntheticEnv.instances


@pytest.mark.parametrize("field,value",[("integration","trapezoid"),("split","holdout"),
                                         ("seeds",[20,21,22]),("seeds",[False,True,2])])
def test_rejects_outside_frozen_scope(tmp_path,field,value):
    args=dict(seeds=[0,1,2],integration="endpoint_euler",protocol_path=PROTOCOL)
    args[field]=value
    output=tmp_path/"bad_scope"
    with pytest.raises(ValueError):
        runner.run_ablation(output,**args)
    assert not output.exists() and not SyntheticEnv.instances


def test_study_boundaries_are_inclusive_and_negative_symmetric():
    for q,v in ((.12,0.),(-.12,0.),(0.,1.),(0.,-1.)):
        assert runner.native_study_abort(q,v,0.,stage="endpoint")["type"] == "StudyAbort"
    assert runner.native_study_abort(.119999,.999999,0.,stage="endpoint") is None


@pytest.mark.parametrize("substeps", [0,3,10])
def test_partial_control_is_not_scored_as_complete_transition(tmp_path,monkeypatch,substeps):
    original=SyntheticEnv.step
    def stop(env,request):
        mark=env.trial == 4 and env.step_id == 100
        result=original(env,request)
        if mark:
            env.physics_steps -= 10-substeps
            env.terminated=result.terminated=True
            env.reason="independent_partial_control"
            env.data.qpos[0]=.12
            result.observation=env.observation()
            result.diagnostics.update(executed_substeps=substeps,
                applied_torque_history=[request.tolist()]*substeps,terminated=True)
        return result
    monkeypatch.setattr(SyntheticEnv,"step",stop)
    output=tmp_path/f"partial_control_{substeps}"
    run(output)
    sr=read(output,"seed_results.json")[0]
    result=sr["evaluations"]["short_mpc"]
    assert result["metric_control_step_count"] == int(substeps == 10)
    assert set(result["metric_prediction_step_count"].values()) == {int(substeps == 10)}
    assert result["control_effort"]["requested_absolute_nm_s"] == pytest.approx(.08*.002*substeps)
    assert result["models_before"] == result["models_after"] and result["actual_effort_complete"]
    assert result["environment_terminated"] and result["study_abort"]["type"] == "StudyAbort"
    rows=[r for r in trace(output) if r["trial_id"] == "seed0_short_mpc" and r["phase"] == "control"]
    assert len(rows) == 1
    assert rows[0]["partial_interval_target_error_rad"] == (None if substeps == 10 else pytest.approx(.08))
    assert result["partial_interval_target_errors_rad"] == ([] if substeps == 10 else [pytest.approx(.08)])


@pytest.mark.parametrize("trial,last_step",[(0,399),(4,299)])
def test_final_planned_endpoint_stop_is_terminated_even_with_full_budget(tmp_path,monkeypatch,trial,last_step):
    original=SyntheticEnv.step
    def stop(env,request):
        mark=env.trial == trial and env.step_id == last_step
        result=original(env,request)
        if mark:
            env.data.qpos[0]=.12
            result.observation=env.observation()
        return result
    monkeypatch.setattr(SyntheticEnv,"step",stop)
    output=tmp_path/f"last_terminal_{trial}"
    run(output)
    episode=read(output,"episodes.json")[trial]
    assert episode["status"] == "terminated" and episode["control_steps"] == last_step+1
    result=read(output,"seed_results.json")[0]["evaluations"][episode["kind"]]
    assert not result["completed"] and result["reason"]["type"] == "StudyAbort"
    if trial == 0:
        assert read(output,"seed_results.json")[0]["calibration_models"]["short"]["hinge5"]["update_count"] == 300
        assert result["metric_prediction_step_count"] == {"hinge5":300}
    else:
        assert result["metric_control_step_count"] == 200


def test_trace_failure_of_any_exception_type_is_fatal_after_paid_update(tmp_path,monkeypatch):
    original=runner.gzip.open
    class FaultStream:
        def __init__(self,wrapped):
            self.wrapped=wrapped
            self.calls=0
        def __enter__(self):
            self.wrapped.__enter__()
            return self
        def __exit__(self,*args):
            return self.wrapped.__exit__(*args)
        def write(self,row):
            self.calls+=1
            if self.calls == 102:
                raise ValueError("injected non-IO trace failure")
            return self.wrapped.write(row)
    def fault(path,*args,**kwargs):
        stream=original(path,*args,**kwargs)
        return FaultStream(stream) if Path(path).name == "trace.jsonl.gz" and args and args[0] == "wt" else stream
    monkeypatch.setattr(runner.gzip,"open",fault)
    output=tmp_path/"trace_fault"
    with pytest.raises(ValueError,match="non-IO trace"):
        run(output)
    metadata=read(output,"metadata.json")
    assert metadata["archive_status"] == "failed" and metadata["model_updates"] == 2
    assert metadata["physics_steps"] == 1020 and len(SyntheticEnv.instances) == 1
    assert all(e["status"] == "blocked" for e in read(output,"episodes.json")[1:])
    assert read(output,"seed_results.json")[0]["calibration_models"]["short"]["hinge5"]["update_count"] == 2


def test_post_return_invalid_telemetry_keeps_request_paid_and_actual_missing(tmp_path,monkeypatch):
    original=SyntheticEnv.step
    def fault(env,request):
        mark=env.trial == 4 and env.step_id == 100
        result=original(env,request)
        if mark:
            result.diagnostics["applied_torque_history"] = []
        return result
    monkeypatch.setattr(SyntheticEnv,"step",fault)
    output=tmp_path/"post_return"
    run(output)
    result=read(output,"seed_results.json")[0]["evaluations"]["short_mpc"]
    episode=read(output,"episodes.json")[4]
    assert result["status"] == "exception" and episode["physics_steps"] == 1010
    assert not episode["risk_telemetry_complete"] and result["missing_control_effort_substeps"] == 10
    assert result["control_effort"]["requested_absolute_nm_s"] == pytest.approx(.08*.02)
    assert result["actual_effort_is_lower_bound"] and not result["actual_effort_complete"]


def test_planner_failure_records_computation_time_without_physics_charge(tmp_path,monkeypatch):
    def fail(planner,q,v,target_q,previous_torque=0.):
        planner.model.predict(q,v,.25)
        raise ValueError("injected planner after computation")
    monkeypatch.setattr(CheapPlanner,"select",fail)
    output=tmp_path/"planner_fault"
    run(output)
    result=read(output,"seed_results.json")[0]["evaluations"]["short_mpc"]
    episode=read(output,"episodes.json")[4]
    assert episode["physics_steps"] == 1000 and episode["control_calls_attempted"] == 100
    assert result["planner_attempt_count"] == result["failed_planner_attempts"] == 1
    assert result["planner_decision_count"] == 0 and result["controller_seconds_total"] > 0.
    assert result["mathematical_prediction_calls_is_lower_bound"]


def test_nominal_prior_cold_initializes_from_own_prefix_after_both_calibration_prefix_failures(tmp_path,monkeypatch):
    original=SyntheticEnv.step
    def fail(env,request):
        if env.trial in (0,1) and env.step_id == 2:
            env.physics_steps += 3
            raise ValueError("injected calibration prefix failure")
        return original(env,request)
    monkeypatch.setattr(SyntheticEnv,"step",fail)
    output=tmp_path/"nominal_independent"
    metadata=run(output)
    sr=read(output,"seed_results.json")[0]
    assert sr["calibration_completed"] == {"short":False,"reordered":False}
    assert sr["learned_models"] == {} and sr["initial_models"] == {}
    assert sr["evaluations"]["nominal_mpc"]["completed"]
    assert metadata["model_updates"] == 1200 and metadata["physics_steps"] == 45046


@pytest.mark.parametrize("option,value",[("--integration","endpoint_euler"),("--calibration-dose","old"),("--model-structure","hinge5")])
def test_cli_has_no_tunable_recipe_options(tmp_path,monkeypatch,option,value,capsys):
    output=tmp_path/"cli_forbidden"
    monkeypatch.setattr("sys.argv",["local_coverage_ablation","--output",str(output),
                                   "--protocol",str(PROTOCOL),option,value])
    with pytest.raises(SystemExit) as failure:
        runner.main()
    assert failure.value.code == 2 and "unrecognized arguments" in capsys.readouterr().err
    assert not output.exists() and not SyntheticEnv.instances
