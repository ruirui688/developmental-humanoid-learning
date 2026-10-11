"""C2-C synthetic accounting/study-stop tests. No MuJoCo physical step."""
from collections import Counter
import gzip
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

pytest.importorskip("mujoco")
from developmental_physics import local_frozen_validation as runner


ROOT = next(p for p in Path(__file__).resolve().parents if (p/"pyproject.toml").is_file())
PROTOCOL = ROOT / "docs/LOCAL_FROZEN_VALIDATION_PROTOCOL.md"


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
    declared=dict(runner.SUITES["shoulder_final"]); declared["seeds"]=[0]
    monkeypatch.setitem(runner.SUITES,"shoulder_final",declared)


def read(output, name):
    return json.loads((output/name).read_text(encoding="utf-8"))


def run(output, **kwargs):
    return runner.run_validation(output, calibration_schedule="short", protocol_path=PROTOCOL, **kwargs)


def trace(output):
    with gzip.open(output/"trace.jsonl.gz", "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream]


def test_single_seed_full_matrix_budget_and_frozen_baselines(tmp_path):
    output=tmp_path/"full"
    metadata=run(output)
    assert metadata["complete"] and metadata["all_trials_successful"]
    assert metadata["seeds"] == [0] and metadata["planned_episode_count"] == 7
    assert metadata["control_calls_attempted"] == metadata["control_steps"] == 2000
    assert metadata["physics_steps"] == 20000 and metadata["model_updates"] == 300
    assert metadata["cpu_seconds"] >= 0. and metadata["wall_seconds"] >= 0.
    assert metadata["suite"] == "shoulder_final" and metadata["pd_gains"] == {"kp":64.,"kd":0.}
    assert metadata["pd_controller_spec"]["body_model_input"] is False
    episodes=read(output,"episodes.json")
    assert [e["kind"] for e in episodes] == ["calibration","prediction_low","prediction_full", "nominal_mpc","learned_mpc","tuned_pd","zero_torque"]
    phases={p:sum(e["phase_budgets"][p]["control_steps"] for e in episodes) for p in ("prefix","calibration","prediction","control")}
    assert phases == {"prefix":700,"calibration":300,"prediction":200,"control":800}
    sr=read(output,"seed_results.json")[0]
    assert sr["calibration_updates"] == 300 and sr["calibration_completed"] == {"short":True}
    assert len(sr["learned_models"]) == 1 and set(sr["integration_models"]) == {"nominal_mpc","learned_mpc"}
    assert sr["calibration_models"]["short"]["hinge5"]["update_count"] == 300
    for kind,result in sr["evaluations"].items():
        if kind != "calibration":
            assert result["models_before"] == result["models_after"]
            assert result["integration_models_before"] == result["integration_models_after"]
        assert all(result["phase_actual_effort_complete"].values())
    assert sr["evaluations"]["tuned_pd"]["pd_calls_successful"] == 200
    assert sr["evaluations"]["tuned_pd"]["planner_decision_count"] == 0
    assert sr["evaluations"]["zero_torque"]["planner_decision_count"] == 0
    assert sr["evaluations"]["zero_torque"]["tracking_rmse_rad"] == pytest.approx(np.sqrt((.04**2+.08**2)/2))
    rows=trace(output)
    assert len(rows) == 2000
    for row in rows:
        if row["phase"] == "prefix":
            assert row["requested_torque"] == [0.]*8 and row["model_update"] is None
        elif row["phase"] == "calibration":
            assert row["model_update"]["hinge5"]["update_count"] == row["step_index"]-99
        else:
            assert row["model_update"] is None
            assert set(row["predicted_next_qv"]) == {"nominal_mpc","learned_mpc","persistence"}
        if row["kind"] == "tuned_pd" and row["phase"] == "control":
            q=row["observation_before"]["joint_position"][0]
            raw=64.*(row["target_q"]-q)
            assert row["raw_pd_torque_nm"] == pytest.approx(raw)
            assert row["requested_torque"][0] == pytest.approx(np.clip(raw,-.5,.5))
            assert row["planner_decision"] is None
        if row["kind"] == "zero_torque":
            assert row["requested_torque"] == [0.]*8 and row["raw_pd_torque_nm"] is None
    assert all(env.trial < 7 for env in SyntheticEnv.instances)


def test_failed_calibration_blocks_only_prediction_and_learned_mpc(tmp_path):
    SyntheticEnv.fail_trial,SyntheticEnv.fail_step=0,101
    output=tmp_path/"failed_cal"
    metadata=run(output)
    episodes=read(output,"episodes.json")
    assert episodes[0]["status"] == "exception" and episodes[0]["physics_steps"] == 1013
    assert all(episodes[i]["status"] == "blocked" for i in (1,2,4))
    assert all(episodes[i]["status"] == "completed" for i in (3,5,6))
    assert metadata["model_updates"] == 1 and metadata["physics_steps"] == 10013
    sr=read(output,"seed_results.json")[0]
    assert sr["calibration_models"]["short"]["hinge5"]["update_count"] == 1
    assert sr["evaluations"]["tuned_pd"]["pd_calls_successful"] == 200
    assert sr["evaluations"]["zero_torque"]["control_effort"]["actual_absolute_nm_s"] == 0.


def test_nominal_pd_zero_are_independent_of_calibration_prefix_failure(tmp_path):
    SyntheticEnv.fail_trial,SyntheticEnv.fail_step=0,2
    output=tmp_path/"prefix_failure"
    metadata=run(output)
    sr=read(output,"seed_results.json")[0]
    assert metadata["model_updates"] == 0 and metadata["physics_steps"] == 9023
    assert sr["learned_models"] == {} and sr["initial_models"] == {}
    assert all(sr["evaluations"][k]["completed"] for k in ("nominal_mpc","tuned_pd","zero_torque"))
    assert all(sr["evaluations"][k]["models_before"] == sr["evaluations"][k]["models_after"] for k in ("nominal_mpc","tuned_pd","zero_torque"))


@pytest.mark.parametrize("trial",(5,6))
def test_new_baselines_share_study_abort_without_marking_environment_stopped(tmp_path,monkeypatch,trial):
    original=SyntheticEnv.step
    def stop(env,request):
        mark=env.trial == trial and env.step_id == 100
        result=original(env,request)
        if mark:
            env.data.qpos[0]=.12
            result.observation=env.observation()
        return result
    monkeypatch.setattr(SyntheticEnv,"step",stop)
    output=tmp_path/f"study_{trial}"
    metadata=run(output)
    episode=read(output,"episodes.json")[trial]
    assert metadata["complete"] and not metadata["all_trials_successful"]
    assert metadata["physics_steps"] == 18010 and metadata["model_updates"] == 300
    assert episode["status"] == "terminated" and episode["reason"]["type"] == "StudyAbort"
    assert not episode["environment_terminated"] and episode["environment_stop_reason"] is None
    assert len(SyntheticEnv.instances[trial].commands) == 101
    result=read(output,"seed_results.json")[0]["evaluations"][episode["kind"]]
    assert result["metric_control_step_count"] == 1 and result["models_before"] == result["models_after"]


def test_partial_pd_preserves_raw_output_paid_effort_and_excludes_main_rmse(tmp_path,monkeypatch):
    original=SyntheticEnv.step
    def stop(env,request):
        mark=env.trial == 5 and env.step_id == 100
        result=original(env,request)
        if mark:
            env.physics_steps-=7
            env.terminated=result.terminated=True
            env.reason="environment_partial"
            env.data.qpos[0]=.12
            result.observation=env.observation()
            result.diagnostics.update(executed_substeps=3,applied_torque_history=[request.tolist()]*3,terminated=True)
        return result
    monkeypatch.setattr(SyntheticEnv,"step",stop)
    output=tmp_path/"partial_pd"
    run(output)
    result=read(output,"seed_results.json")[0]["evaluations"]["tuned_pd"]
    assert result["metric_control_step_count"] == 0 and result["tracking_rmse_rad"] is None
    assert result["partial_interval_target_errors_rad"] == [pytest.approx(.08)]
    assert result["control_effort"]["requested_absolute_nm_s"] == pytest.approx(.5*.006)
    assert result["control_effort"]["actual_squared_nm2_s"] == pytest.approx(.25*.006)
    row=next(r for r in trace(output) if r["kind"] == "tuned_pd" and r["phase"] == "control")
    assert row["raw_pd_torque_nm"] == pytest.approx(2.56) and row["partial_interval_target_error_rad"] == pytest.approx(.08)
    assert row["model_update"] is None


def test_failed_pd_computation_records_time_and_does_not_add_physical_call(tmp_path,monkeypatch):
    original=runner.pd_request
    def fail(*args):
        original(*args)
        raise ValueError("injected PD after computation")
    monkeypatch.setattr(runner,"pd_request",fail)
    output=tmp_path/"pd_failure"
    run(output)
    result=read(output,"seed_results.json")[0]["evaluations"]["tuned_pd"]
    episode=read(output,"episodes.json")[5]
    assert result["status"] == "exception" and episode["physics_steps"] == 1000
    assert result["pd_calls_attempted"] == result["failed_pd_attempts"] == 1
    assert result["pd_calls_successful"] == 0 and result["pd_seconds_total"] > 0.
    assert result["models_before"] == result["models_after"]


@pytest.mark.parametrize("kwargs",({"seeds":[20,21,22]},{"pd_kp":8.},{"pd_kd":1.},
                                    {"integration":"trapezoid"},{"model_structure":"linear4"},
                                    {"calibration_dose":"new"},{"suite":"undeclared"}))
def test_rejects_outside_declared_suite_without_output_or_reset(tmp_path,kwargs):
    output=tmp_path/"forbidden"
    with pytest.raises(ValueError):
        run(output,**kwargs)
    assert not output.exists() and not SyntheticEnv.instances


def test_unfrozen_suite_gains_reject_before_environment_or_output(tmp_path, monkeypatch):
    declared = dict(runner.SUITES["elbow_development"])
    declared["pd_kp"] = declared["pd_kd"] = None
    monkeypatch.setitem(runner.SUITES, "elbow_development", declared)
    with pytest.raises(ValueError, match="not been frozen"):
        run(tmp_path/"unfrozen", suite="elbow_development")
    assert not SyntheticEnv.instances and not (tmp_path/"unfrozen").exists()


def test_suite_requires_its_exact_protocol_before_environment_or_output(tmp_path):
    with pytest.raises(ValueError, match="exact frozen suite protocol"):
        runner.run_validation(tmp_path/"wrong_protocol", calibration_schedule="short",
                              protocol_path=ROOT/"docs/LOCAL_COVERAGE_ABLATION_PROTOCOL.md")
    assert not SyntheticEnv.instances and not (tmp_path/"wrong_protocol").exists()


def test_frozen_elbow_source_and_audit_declarations_match():
    from test_local_frozen_audit import core
    assert runner.SUITES["elbow_development"]["pd_kp"] == core.ELBOW_DEVELOPMENT_SPEC.pd_kp == 64.
    assert runner.SUITES["elbow_development"]["pd_kd"] == core.ELBOW_DEVELOPMENT_SPEC.pd_kd == 1.
    assert runner.SUITE_PROTOCOLS["elbow_development"] == core.ELBOW_DEVELOPMENT_SPEC.protocol
    assert runner.PD_SELECTION_SOURCES["elbow_development"] == core.ELBOW_DEVELOPMENT_SPEC.pd_selection_source


def test_elbow_native_layout_negative_reference_and_frozen_source(tmp_path, monkeypatch):
    class ElbowEnv(SyntheticEnv):
        def reset(self, seed, pose):
            super().reset(seed, pose)
            self.data.qpos[0], self.data.qpos[1] = .4, -.005
            self.model.joint = lambda name: SimpleNamespace(range=np.array([0., 2.3] if name == "1" else [-2., 2.]))
            return self.observation()
    declared = dict(runner.SUITES["elbow_development"])
    declared["seeds"] = [0]
    monkeypatch.setitem(runner.SUITES, "elbow_development", declared)
    monkeypatch.setattr(runner, "GroundBodyEnv", ElbowEnv)
    output = tmp_path/"elbow"
    metadata = runner.run_validation(output, suite="elbow_development", calibration_schedule="short",
                                    protocol_path=ROOT/runner.SUITE_PROTOCOLS["elbow_development"])
    assert metadata["all_trials_successful"] and metadata["model_updates"] == 300
    assert metadata["pd_selection_source"] == dict(runner.PD_SELECTION_SOURCES["elbow_development"])
    assert metadata["pd_gains"] == {"kp": 64., "kd": 1.}
    rows = trace(output)
    for row in rows:
        assert row["observation_before"]["joint_position"][0] == .4
        assert row["requested_torque"][0] == 0.
        assert all(row["requested_torque"][j] == 0. for j in range(2, 8))
        if row["target_q"] is not None:
            assert row["target_q"] in (.035, .075)
    seed = read(output, "seed_results.json")[0]
    assert seed["calibration_models"]["short"]["hinge5"]["qref_rad"] == -.005


def test_schedule_becomes_strict_when_root_freezes_it(tmp_path,monkeypatch):
    monkeypatch.setattr(runner,"FROZEN_FINAL_SCHEDULE","reordered")
    output=tmp_path/"wrong_schedule"
    with pytest.raises(ValueError,match="frozen final"):
        run(output)
    assert not output.exists()


@pytest.mark.parametrize("flag,value",[("--schedule","short"),("--pd-kp","64"),("--integration","endpoint_euler")])
def test_cli_does_not_offer_tunable_recipe_parameters(tmp_path,monkeypatch,flag,value):
    monkeypatch.setattr("sys.argv",["local_frozen_validation","--output",str(tmp_path/"cli"),
                                  "--protocol",str(PROTOCOL),"--suite","shoulder_final",flag,value])
    with pytest.raises(SystemExit) as exc:
        runner.main()
    assert exc.value.code == 2 and not SyntheticEnv.instances


def test_cli_refuses_execution_before_final_schedule_declaration(tmp_path,monkeypatch):
    monkeypatch.setattr(runner,"FROZEN_FINAL_SCHEDULE",None)
    monkeypatch.setattr("sys.argv",["local_frozen_validation","--output",str(tmp_path/"cli"),
                                  "--protocol",str(PROTOCOL),"--suite","shoulder_final"])
    with pytest.raises(SystemExit) as exc:
        runner.main()
    assert exc.value.code == 2 and not SyntheticEnv.instances
