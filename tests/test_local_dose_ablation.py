"""Accounting/failure tests use a synthetic environment; no MuJoCo steps."""
import gzip
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

pytest.importorskip("mujoco")
from developmental_physics import local_dose_ablation as runner


ROOT = next(p for p in Path(__file__).resolve().parents if (p/"pyproject.toml").is_file())
PROTOCOL = ROOT / "docs/LOCAL_DOSE_ABLATION_PROTOCOL.md"


class SyntheticEnv:
    instances = 0
    fail_trial = None
    fail_step = None
    interrupt = False

    def __init__(self):
        self.trial = SyntheticEnv.instances
        SyntheticEnv.instances += 1
        self.config = SimpleNamespace(physics_dt=.002)
        self.control_dt = .02
        self.joint_names = [str(i) for i in range(8)]
        self.model = SimpleNamespace(joint=lambda name: SimpleNamespace(range=np.array([-1., 1.])))
        self.data = SimpleNamespace(qpos=np.zeros(8), qvel=np.zeros(8))
        self.step_id = self.physics_steps = 0
        self.terminated = False
        self.reason = None
        self.command = np.zeros(8)

    def reset(self, seed, pose):
        assert pose == "supine"
        self.data.qpos[:] = 0.
        self.data.qvel[:] = 0.
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
            self.physics_steps += 3  # A real partial cost before the injected fault.
            if self.interrupt:
                raise KeyboardInterrupt()
            raise RuntimeError("injected partial step")
        self.command = request.copy()
        self.data.qvel = .5*self.data.qvel + .02*request
        self.data.qpos += .02*self.data.qvel
        self.step_id += 1
        self.physics_steps += 10
        diagnostics = {"executed_substeps": 10, "applied_torque_history": [request.tolist()]*10,
                       "terminated": False}
        return SimpleNamespace(observation=self.observation(), diagnostics=diagnostics, terminated=False)


class CheapPlanner:
    def __init__(self, model, joint_range):
        self.model = model

    def select(self, q, v, target_q, previous_torque=0.):
        # Run the actual integration model, while avoiding expensive grid tests.
        u = float(np.clip(2*(target_q-q)-.2*v, -.5, .5))
        self.model.predict(q, v, u)
        return SimpleNamespace(torque=u, fallback=False, mathematical_prediction_calls=1,
                               to_dict=lambda: {"torque":u,"fallback":False,"mathematical_prediction_calls":1})

    def spec(self):
        return {"synthetic_test": True, "physical_queries": 0}


@pytest.fixture(autouse=True)
def synthetic_only(monkeypatch):
    SyntheticEnv.instances = 0
    SyntheticEnv.fail_trial = SyntheticEnv.fail_step = None
    SyntheticEnv.interrupt = False
    monkeypatch.setattr(runner, "GroundBodyEnv", SyntheticEnv)
    monkeypatch.setattr(runner, "FixedLocalMPC", CheapPlanner)


def read(output, name):
    return json.loads((output/name).read_text(encoding="utf-8"))


def test_full_factorial_budget_and_isolated_models(tmp_path):
    output=tmp_path/"complete"
    metadata=runner.run_ablation(output,[0,1,2],integration="endpoint_euler",protocol_path=PROTOCOL)
    assert metadata["complete"] and metadata["all_trials_successful"]
    assert metadata["planned_episode_count"] == metadata["completed_trials"] == 27
    assert metadata["control_calls_attempted"] == metadata["control_steps"] == 8100
    assert metadata["physics_steps"] == 81000 and metadata["model_updates"] == 3600
    episodes=read(output,"episodes.json")
    totals={phase:sum(e["phase_budgets"][phase]["control_steps"] for e in episodes) for phase in ("prefix","calibration","prediction","control")}
    assert totals == {"prefix":2700,"calibration":1800,"prediction":600,"control":3000}
    for sr in read(output,"seed_results.json"):
        assert sr["calibration_updates"] == 1200 and sr["calibration_completed"] == {"old":True,"new":True}
        assert len(sr["learned_models"]) == 4 and len(sr["integration_models"]) == 5
        for name,model in sr["learned_models"].items():
            assert model["update_count"] == 300 and not model["trainable"]
            assert len(model["coefficients"]) == (4 if "linear4" in name else 5)
            initial=sr["initial_models"][name]
            assert initial["update_count"] == 0
            assert initial["coefficients"] == ([1.,0.,.02,0.] if "linear4" in name else [1.,0.,.02,0.,0.])
            assert np.array_equal(initial["covariance"],100*np.eye(len(initial["coefficients"])))
        for name,result in sr["evaluations"].items():
            if not name.startswith("calibration_"):
                assert result["models_before"] == result["models_after"]
                assert result["integration_models_before"] == result["integration_models_after"]
                assert all(result["phase_actual_effort_complete"].values())
        for dose,absolute,squared in (("old",.55,.20),("new",.70,.275)):
            effort=sr["evaluations"][f"calibration_{dose}"]["phase_effort"]["calibration"]
            assert effort["requested_absolute_nm_s"] == pytest.approx(absolute)
            assert effort["requested_squared_nm2_s"] == pytest.approx(squared)
        for name,absolute,squared in (("low",.35,.0875),("full",.455,.170625)):
            effort=sr["evaluations"][f"prediction_{name}"]["phase_effort"]["prediction"]
            assert effort["requested_absolute_nm_s"] == pytest.approx(absolute)
            assert effort["requested_squared_nm2_s"] == pytest.approx(squared)
    with gzip.open(output/"trace.jsonl.gz","rt",encoding="utf-8") as stream:
        rows=[json.loads(line) for line in stream]
    assert len(rows) == 8100
    for row in rows:
        if row["phase"] == "prefix":
            assert row["requested_torque"] == [0.]*8 and row["model_update"] is None
        elif row["phase"] != "calibration":
            assert row["model_update"] is None
            assert set(row["predicted_next_qv"]) == {"nominal_mpc","old_linear4_mpc","old_hinge5_mpc","new_linear4_mpc","new_hinge5_mpc","persistence"}
        else:
            assert set(row["model_update"]) == {"linear4","hinge5"}
            for name,item in row["model_update"].items():
                assert item["update_count"] == row["step_index"]-99
                assert item["shared_transition_id"] == row["shared_transition_id"]
                assert item["model_id"] == f'{row["calibration_dose"]}_{name}'
    with pytest.raises(FileExistsError):
        runner.run_ablation(output,[0,1,2],integration="endpoint_euler",protocol_path=PROTOCOL)


def test_calibration_failure_blocks_dependencies_but_preserves_other_seeds(tmp_path):
    SyntheticEnv.fail_trial, SyntheticEnv.fail_step = 0, 102
    output=tmp_path/"failed_calibration"
    metadata=runner.run_ablation(output,[0,1,2],integration="endpoint_euler",protocol_path=PROTOCOL)
    episodes=read(output,"episodes.json")
    assert episodes[0]["status"] == "exception" and episodes[0]["physics_steps"] == 1023
    assert episodes[0]["control_calls_attempted"] == 103
    assert all(episodes[i]["status"] == "blocked" and episodes[i]["physics_steps"] == 0 for i in (2,3,4,5))
    assert all(episodes[i]["status"] == "completed" for i in [1,6,7,8,*range(9,27)])
    assert metadata["model_updates"] == 3004 and metadata["physics_steps"] == 68023


def test_evaluation_failure_keeps_calibration_and_continues_other_methods(tmp_path):
    SyntheticEnv.fail_trial, SyntheticEnv.fail_step=4,105
    output=tmp_path/"failed_evaluation"
    metadata=runner.run_ablation(output,[0,1,2],integration="endpoint_euler",protocol_path=PROTOCOL)
    episodes=read(output,"episodes.json")
    assert episodes[4]["status"] == "exception" and episodes[4]["physics_steps"] == 1053
    assert episodes[5]["status"] == "completed"
    assert metadata["model_updates"] == 3600 and not metadata["all_trials_successful"]


def test_interrupt_retains_partial_substeps_and_blocks_remaining_plan(tmp_path):
    SyntheticEnv.fail_trial,SyntheticEnv.fail_step,SyntheticEnv.interrupt=0,102,True
    output=tmp_path/"interrupted"
    with pytest.raises(KeyboardInterrupt):
        runner.run_ablation(output,[0,1,2],integration="endpoint_euler",protocol_path=PROTOCOL)
    metadata=read(output,"metadata.json");episodes=read(output,"episodes.json")
    assert metadata["physics_steps"] == 1023 and metadata["model_updates"] == 4
    assert episodes[0]["status"] == "exception" and all(e["status"] == "blocked" for e in episodes[1:])
    assert metadata["archive_status"] == "interrupted"


def test_transient_non_oserror_trace_failure_still_stops_paid_interaction(tmp_path, monkeypatch):
    original=runner.gzip.open
    class FaultyStream:
        def __init__(self, inner): self.inner=inner;self.failed=False
        def __enter__(self): self.inner.__enter__();return self
        def __exit__(self,*args): return self.inner.__exit__(*args)
        def write(self,text):
            if not self.failed:
                self.failed=True
                raise RuntimeError("injected trace write failure")
            return self.inner.write(text)
    monkeypatch.setattr(runner.gzip,"open",lambda *args,**kwargs:FaultyStream(original(*args,**kwargs)))
    output=tmp_path/"log_fault"
    with pytest.raises(RuntimeError,match="trace write"):
        runner.run_ablation(output,[0,1,2],integration="endpoint_euler",protocol_path=PROTOCOL)
    metadata=read(output,"metadata.json");episodes=read(output,"episodes.json")
    assert metadata["control_steps"] == 1 and metadata["physics_steps"] == 10
    assert episodes[0]["status"] == "exception" and all(e["status"] == "blocked" for e in episodes[1:])


def test_rejects_heldout_scope_before_creating_output(tmp_path):
    output=tmp_path/"forbidden"
    with pytest.raises(ValueError,match="development only"):
        runner.run_ablation(output,[0,1,2],split="holdout",integration="endpoint_euler",protocol_path=PROTOCOL)
    with pytest.raises(ValueError,match="seeds"):
        runner.run_ablation(output,[20,21,22],integration="endpoint_euler",protocol_path=PROTOCOL)
    with pytest.raises(ValueError,match="seeds"):
        runner.run_ablation(output,[False,True,2],integration="endpoint_euler",protocol_path=PROTOCOL)
    assert not output.exists()


def test_returned_partial_calibration_is_not_fitted_as_20ms(tmp_path, monkeypatch):
    original = SyntheticEnv.step
    def stop(env, request):
        partial = env.trial == 0 and env.step_id == 100
        result = original(env, request)
        if partial:
            env.physics_steps -= 7
            env.terminated = result.terminated = True
            env.reason = "injected_short_interval"
            result.diagnostics.update(executed_substeps=3, applied_torque_history=[request.tolist()]*3,
                                      terminated=True)
        return result
    monkeypatch.setattr(SyntheticEnv, "step", stop)
    output = tmp_path/"partial_calibration"
    metadata = runner.run_ablation(output,[0,1,2],integration="endpoint_euler",protocol_path=PROTOCOL)
    sr = read(output,"seed_results.json")[0]
    assert sum(m["update_count"] for m in sr["calibration_models"]["old"].values()) == 0 and all(m["update_count"] == 0 for m in sr["calibration_models"]["old"].values())
    assert metadata["model_updates"] == 3000 and metadata["physics_steps"] == 68003
    with gzip.open(output/"trace.jsonl.gz","rt",encoding="utf-8") as stream:
        row = next(json.loads(line) for line in stream if '"step_index": 100' in line)
    assert all(item["updated"] is False for item in row["model_update"].values())
    assert all(item["phase"] == "partial_calibration_interval" for item in row["model_update"].values())


def test_unreturned_control_substeps_charge_request_and_mark_actual_lower_bound(tmp_path):
    SyntheticEnv.fail_trial,SyntheticEnv.fail_step=4,100
    output=tmp_path/"control_telemetry_missing"
    runner.run_ablation(output,[0,1,2],integration="endpoint_euler",protocol_path=PROTOCOL)
    result=read(output,"seed_results.json")[0]["evaluations"]["old_linear4_mpc"]
    episode=read(output,"episodes.json")[4]
    assert result["missing_control_effort_substeps"] == episode["unreturned_physics_steps"] == 3
    assert result["actual_effort_is_lower_bound"] and not result["actual_effort_complete"]
    assert not episode["risk_telemetry_complete"]
    assert result["control_effort"]["requested_absolute_nm_s"] == pytest.approx(.08*.006)
    assert result["control_effort"]["actual_absolute_nm_s"] == 0.
    assert result["planner_decision_count"] == result["mathematical_prediction_calls"] == 1


@pytest.mark.parametrize("substeps", [0, 3])
def test_returned_control_stop_uses_paid_duration_in_effort(tmp_path, monkeypatch, substeps):
    original=SyntheticEnv.step
    def stop(env,request):
        partial=env.trial == 4 and env.step_id == 100
        result=original(env,request)
        if partial:
            env.physics_steps -= 10-substeps
            env.terminated=result.terminated=True
            env.reason="injected_short_control"
            result.diagnostics.update(executed_substeps=substeps,
                                      applied_torque_history=[request.tolist()]*substeps,terminated=True)
        return result
    monkeypatch.setattr(SyntheticEnv,"step",stop)
    output=tmp_path/f"control_stop_{substeps}"
    runner.run_ablation(output,[0,1,2],integration="endpoint_euler",protocol_path=PROTOCOL)
    result=read(output,"seed_results.json")[0]["evaluations"]["old_linear4_mpc"]
    assert result["status"] == "terminated" and not result["completed"]
    assert result["control_effort"]["actual_absolute_nm_s"] == pytest.approx(.08*substeps*.002)
    assert result["control_effort"]["actual_squared_nm2_s"] == pytest.approx(.08**2*substeps*.002)
    assert result["actual_effort_complete"]


def test_checkpoint_fault_preserves_calibration_cost_and_models(tmp_path, monkeypatch):
    original=runner._write_json
    calls=0
    def fail(path,content):
        nonlocal calls
        if path.name == "seed_results.json":
            calls += 1
            if calls == 2:
                raise OSError("injected checkpoint fault")
        return original(path,content)
    monkeypatch.setattr(runner,"_write_json",fail)
    output=tmp_path/"checkpoint_fault"
    with pytest.raises(OSError,match="checkpoint fault"):
        runner.run_ablation(output,[0,1,2],integration="endpoint_euler",protocol_path=PROTOCOL)
    metadata=read(output,"metadata.json")
    assert metadata["model_updates"] == 600 and metadata["physics_steps"] == 4000
    assert metadata["archive_status"] == "failed"
    assert all(m["update_count"] == 300 for m in read(output,"seed_results.json")[0]["calibration_models"]["old"].values())
    assert all(e["status"] == "blocked" for e in read(output,"episodes.json")[1:])


def test_post_return_error_preserves_request_cost_and_marks_missing_actual(tmp_path, monkeypatch):
    original=SyntheticEnv.step
    def corrupt(env,request):
        post_error=env.trial == 4 and env.step_id == 100
        result=original(env,request)
        if post_error:
            # Real executed substeps are paid even if post-return telemetry is invalid.
            result.diagnostics["applied_torque_history"] = []
        return result
    monkeypatch.setattr(SyntheticEnv,"step",corrupt)
    output=tmp_path/"post_return_fault"
    runner.run_ablation(output,[0,1,2],integration="endpoint_euler",protocol_path=PROTOCOL)
    result=read(output,"seed_results.json")[0]["evaluations"]["old_linear4_mpc"]
    episode=read(output,"episodes.json")[4]
    assert episode["physics_steps"] == 1010 and episode["unreturned_physics_steps"] == 0
    assert result["control_effort"]["requested_absolute_nm_s"] == pytest.approx(.08*.02)
    assert result["control_effort"]["requested_squared_nm2_s"] == pytest.approx(.08**2*.02)
    assert result["actual_control_effort_substeps"] == 0 and result["missing_control_effort_substeps"] == 10
    assert result["actual_effort_is_lower_bound"] and not episode["risk_telemetry_complete"]
    assert result["planner_decision_count"] == result["mathematical_prediction_calls"] == 1


def test_oserror_stops_without_repeating_physics_trials(tmp_path, monkeypatch):
    original=SyntheticEnv.step
    def io_fault(env,request):
        if env.trial == 0 and env.step_id == 2:
            env.physics_steps += 3
            raise OSError("injected persistent IO fault")
        return original(env,request)
    monkeypatch.setattr(SyntheticEnv,"step",io_fault)
    output=tmp_path/"io_fault"
    with pytest.raises(OSError,match="persistent IO"):
        runner.run_ablation(output,[0,1,2],integration="endpoint_euler",protocol_path=PROTOCOL)
    episodes=read(output,"episodes.json")
    assert episodes[0]["physics_steps"] == 23
    assert all(e["status"] == "blocked" for e in episodes[1:])


def test_failed_planner_time_is_paid_and_unknown_calls_marked_lower_bound(tmp_path, monkeypatch):
    def fail(planner,q,v,target_q,previous_torque=0.):
        planner.model.predict(q,v,.25)
        raise ValueError("injected planner failure after computing")
    monkeypatch.setattr(CheapPlanner,"select",fail)
    output=tmp_path/"planner_fault"
    runner.run_ablation(output,[0,1,2],integration="endpoint_euler",protocol_path=PROTOCOL)
    result=read(output,"seed_results.json")[0]["evaluations"]["old_linear4_mpc"]
    episode=read(output,"episodes.json")[4]
    assert episode["physics_steps"] == 1000 and episode["control_calls_attempted"] == 100
    assert result["failed_planner_attempts"] == result["planner_attempt_count"] == 1
    assert result["planner_decision_count"] == 0 and result["controller_seconds_total"] > 0.
    assert not result["mathematical_prediction_calls_complete"] and result["mathematical_prediction_calls_is_lower_bound"]


@pytest.mark.parametrize("integration", [None, "unknown", False, "trapezoid"])
def test_invalid_integration_is_rejected_before_output(tmp_path, integration):
    output=tmp_path/"invalid_integration"
    with pytest.raises(ValueError,match="integration"):
        runner.run_ablation(output,[0,1,2],integration=integration,protocol_path=PROTOCOL)
    assert not output.exists()


def test_initial_structure_predictions_share_the_same_prior_exactly():
    linear=runner.LocalBodyModel(.1,trainable=False)
    hinge=runner.HingeBodyModel(.1,trainable=False)
    assert linear.coefficients.tolist() == [1.,0.,.02,0.]
    assert hinge.coefficients.tolist() == [1.,0.,.02,0.,0.]
    for integration in ("endpoint_euler","trapezoid"):
        left=runner.FrozenIntegrationModel(linear,integration)
        right=runner.FrozenIntegrationModel(hinge,integration)
        for q,v,u in ((.1,.2,.125),(.02,-.04,-.25),(.05,0.,.375),(.1,.1,-.5)):
            assert left.predict(q,v,u) == right.predict(q,v,u)


def test_one_structure_update_fault_preserves_other_parameters_and_cost(tmp_path, monkeypatch):
    original=runner.HingeBodyModel.update
    failed=False
    def fail(model,*args,**kwargs):
        nonlocal failed
        if not failed and model.update_count == 1:
            failed=True
            raise ValueError("injected hinge update fault")
        return original(model,*args,**kwargs)
    monkeypatch.setattr(runner.HingeBodyModel,"update",fail)
    output=tmp_path/"single_model_fault"
    metadata=runner.run_ablation(output,[0,1,2],integration="endpoint_euler",protocol_path=PROTOCOL)
    sr=read(output,"seed_results.json")[0]
    episodes=read(output,"episodes.json")
    assert sr["calibration_models"]["old"]["linear4"]["update_count"] == 2
    assert sr["calibration_models"]["old"]["hinge5"]["update_count"] == 1
    assert metadata["model_updates"] == 3003 and metadata["physics_steps"] == 68020
    assert episodes[0]["status"] == "exception" and episodes[1]["status"] == "completed"
    assert all(episodes[i]["status"] == "blocked" for i in (2,3,4,5))
    assert all(episodes[i]["status"] == "completed" for i in (6,7,8))
    assert sr["evaluations"]["calibration_old"]["phase_effort"]["calibration"]["requested_absolute_nm_s"] == pytest.approx(.005)
    with gzip.open(output/"trace.jsonl.gz","rt",encoding="utf-8") as stream:
        exception=next(json.loads(line) for line in stream if '"collector_exception"' in line)
    assert exception["model_update"]["linear4"]["update_count"] == 2
    assert exception["partial_model_snapshots"]["hinge5"]["update_count"] == 1
    assert exception["step_index"] == 101 and exception["predicted_next_qv"]


def test_nominal_is_independent_of_both_failed_calibration_prefixes(tmp_path, monkeypatch):
    original=SyntheticEnv.step
    def fail_prefix(env,request):
        if env.trial in (0,1) and env.step_id == 2:
            env.physics_steps += 3
            raise ValueError("injected calibration prefix failure")
        return original(env,request)
    monkeypatch.setattr(SyntheticEnv,"step",fail_prefix)
    output=tmp_path/"nominal_independent"
    metadata=runner.run_ablation(output,[0,1,2],integration="endpoint_euler",protocol_path=PROTOCOL)
    sr=read(output,"seed_results.json")[0]
    assert sr["calibration_completed"] == {"old":False,"new":False}
    assert sr["learned_models"] == {} and sr["initial_models"] == {}
    assert sr["evaluations"]["nominal_mpc"]["completed"]
    assert sr["evaluations"]["nominal_mpc"]["models_before"] == sr["evaluations"]["nominal_mpc"]["models_after"]
    assert metadata["model_updates"] == 2400 and metadata["physics_steps"] == 57046


def test_cli_rejects_unfrozen_integration_before_interaction(tmp_path, monkeypatch, capsys):
    output=tmp_path/"trap"
    monkeypatch.setattr("sys.argv",["local_dose_ablation", "--output",str(output),
                                   "--protocol",str(PROTOCOL),"--integration","trapezoid"])
    with pytest.raises(SystemExit) as failure:
        runner.main()
    assert failure.value.code == 2 and "invalid choice" in capsys.readouterr().err
    assert not output.exists() and SyntheticEnv.instances == 0
