"""C4-A synthetic labels only. This suite never calls MuJoCo stepping."""
import gzip
import inspect
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

pytest.importorskip("mujoco")
from developmental_physics import elbow_feedback_validate as runner


ROOT = next(p for p in Path(__file__).resolve().parents if (p/"pyproject.toml").is_file())
PROTOCOL = ROOT/runner.PROTOCOL_PATH


class SyntheticEnv:
    instances = []
    fail_step = None
    failure_type = RuntimeError
    stop_step = None
    trigger = None
    partial = False
    missing_history = False
    prefix_excursion = False

    def __init__(self, config):
        self.config = config
        self.trial = len(self.instances)
        self.instances.append(self)
        self.joint_names = [str(i) for i in range(8)]
        self.ranges = np.array([[-1.,1.]]*8)
        self.ranges[1] = (0.,2.356194490192345)
        self.model = SimpleNamespace(joint=lambda name:SimpleNamespace(range=self.ranges[int(name)]))
        self.data = SimpleNamespace(qpos=np.zeros(15),qvel=np.zeros(14))
        self.step_id = self.physics_steps = 0
        self.terminated = False
        self.reason = None
        self.q, self.v, self.command = np.zeros(8), np.zeros(8), np.zeros(8)
        self.q[1] = -.0005
        self.commands = []

    def reset(self, seed, pose):
        assert pose == "supine"
        assert seed in {int(np.random.SeedSequence(s).spawn(2)[0].generate_state(1)[0]) for s in (0,1,2)}
        return self.observation()

    def parameter_fingerprint(self):
        return "synthetic fixed body"

    def observation(self):
        return {"joint_position":self.q.copy(),"joint_velocity":self.v.copy(),
                "imu_gyro":np.zeros(3),"imu_acceleration":np.zeros(3),
                "actuator_torque":self.command.copy(),"previous_command":self.command.copy()}

    def diagnostics(self):
        return {"step_id":self.step_id,"physics_steps":self.physics_steps,
                "time":self.physics_steps*.002,"executed_substeps":0,
                "applied_torque_history":[],"terminated":self.terminated,"reason":self.reason}

    def step(self, requested):
        index = self.step_id
        if self.trial == 0 and index == self.fail_step:
            self.physics_steps += 3
            raise self.failure_type("synthetic paid three-substep failure")
        self.command = requested.copy()
        self.commands.append(requested.copy())
        n = 3 if self.trial == 0 and index == self.stop_step and self.partial else 10
        self.v = .5*self.v+.02*requested
        self.q += n*.002*self.v
        if self.prefix_excursion and index == 5:
            self.v[1] = 1.
        elif self.prefix_excursion and index == 6:
            self.v[1], self.q[1] = 0., -.0005
        if self.trial == 0 and index == self.stop_step:
            if self.trigger == "q":
                self.q[1] = -.0005+.12
            elif self.trigger == "v":
                self.v[1] = 1.
            if self.partial:
                self.terminated = True
                self.reason = {"type":"SyntheticEnvironmentStop","message":"partial protected interval"}
        self.step_id += 1
        self.physics_steps += n
        diagnostic = self.diagnostics()
        diagnostic.update(executed_substeps=n,applied_torque_history=[requested.tolist()]*n,
            requested_torque=requested.tolist(),accepted_torque=requested.tolist(),applied_torque=requested.tolist(),
            guarded_substeps=0,substep_ground_normal_forces=[1.]*n,substep_kinetic_energies=[.2]*n,
            substep_minimum_contact_distances=[-.0001]*n,peak_substep_ground_normal_force=1.,
            ground_normal_impulse_ns=.002*n,peak_substep_kinetic_energy=.2,
            minimum_substep_contact_distance=-.0001)
        if self.trial == 0 and index == 100 and self.missing_history:
            diagnostic.pop("applied_torque_history")
        return SimpleNamespace(observation=self.observation(),diagnostics=diagnostic,
                               terminated=self.terminated,reason=self.reason)


@pytest.fixture(autouse=True)
def synthetic_only(monkeypatch):
    SyntheticEnv.instances = []
    SyntheticEnv.fail_step = SyntheticEnv.stop_step = None
    SyntheticEnv.trigger = None
    SyntheticEnv.failure_type = RuntimeError
    SyntheticEnv.partial = SyntheticEnv.missing_history = SyntheticEnv.prefix_excursion = False
    monkeypatch.setattr(runner,"GroundBodyEnv",SyntheticEnv)


def small_recipe(monkeypatch, candidates=1):
    monkeypatch.setattr(runner,"DEVELOPMENT_SEEDS",(0,))
    monkeypatch.setattr(runner,"FIXED_GAINS",runner.FIXED_GAINS[:candidates])


def run(output):
    return runner.run_feedback(output,protocol_path=PROTOCOL)


def read(output, name):
    return json.loads((output/name).read_text(encoding="utf-8"))


def rows(output):
    with gzip.open(output/"trace.jsonl.gz","rt",encoding="utf-8") as stream:
        return [json.loads(line) for line in stream]


def test_fixed_full_plan_negative_qref_paid_targets_and_budget(tmp_path):
    output = tmp_path/"full"
    metadata = run(output)
    assert metadata["complete"] and metadata["all_trials_successful"]
    assert metadata["joint_index"] == 1 and metadata["seeds"] == [0,1,2]
    assert metadata["planned_episode_count"] == metadata["completed_trials"] == 27
    assert metadata["control_calls_attempted"] == metadata["control_steps"] == 8100
    assert metadata["physics_steps"] == 81000 and metadata["model_updates"] == 0
    assert metadata["parameter_updates"] == {"body_model":0,"policy":0,"gains":0}
    assert metadata["gpu"] is None and metadata["cpu_seconds"] >= 0.
    episodes = read(output,"episodes.json")
    assert sum(e["phase_budgets"]["prefix"]["physics_steps"] for e in episodes) == 27000
    assert sum(e["phase_budgets"]["control"]["physics_steps"] for e in episodes) == 54000
    for e in episodes:
        assert e["prefix_end_q_rad"] == -.0005 and e["selection_record"]["direction"] == 1
        assert e["phase_complete_transition_counts"] == {"prefix":100,"control":200}
        assert e["metric_control_step_count"] == 200 and e["partial_interval_target_error_count"] == 0
        assert e["actual_effort_complete"] and not e["actual_effort_is_lower_bound"]
        assert e["returned_control_steps"] == e["trace_rows_written"] == 300
        assert e["pd_action_calls"] == 200 and e["failed_pd_attempts"] == 0
        assert e["environment_fingerprint_before"] == e["environment_fingerprint_after"]
        assert e["phase_risk"]["full"]["ground_normal_impulse_ns"] == pytest.approx(6.)
        assert e["phase_risk"]["prefix"]["ground_normal_impulse_ns"] == pytest.approx(2.)
        assert e["phase_effort"]["prefix"] == runner._effort()
    first = [r for r in rows(output) if r["trial_id"] == "seed0_candidate0"]
    assert first[100]["target_q_rad"] == .0395 and first[200]["target_q_rad"] == .0795
    assert first[100]["requested_torque"][1] == pytest.approx(.16)
    assert all(all(u == 0. for i,u in enumerate(r["requested_torque"]) if i != 1) for r in first)
    assert all(r["target_q_rad"] is None and r["study_abort"] is None for r in first[:100])
    assert first[100]["physics_steps_before"] == 1000 and first[100]["physics_steps_after"] == 1010
    with pytest.raises(FileExistsError):
        run(output)


@pytest.mark.parametrize("trigger",["q","v"])
def test_active_native_stop_is_independent_of_env_and_scores_full_terminal(tmp_path,monkeypatch,trigger):
    small_recipe(monkeypatch,2)
    SyntheticEnv.stop_step, SyntheticEnv.trigger = 100, trigger
    output = tmp_path/trigger
    metadata = run(output)
    e, second = read(output,"episodes.json")
    assert metadata["complete"] and not metadata["all_trials_successful"] and second["complete"]
    assert e["status"] == "terminated" and not e["complete"] and e["collector_exception"] is None
    assert e["environment_terminated"] is False and e["environment_stop_reason"] is None
    assert e["reason"] == e["study_abort"] and e["reason"]["feedback_action"] is None
    assert e["control_steps"] == 101 and e["physics_steps"] == 1010 and e["metric_control_step_count"] == 1
    assert len(SyntheticEnv.instances[0].commands) == 101 and not SyntheticEnv.instances[0].terminated
    terminal = [r for r in rows(output) if r["trial_id"] == e["trial_id"]][-1]
    assert terminal["study_abort"]["step_index"] == 100 and terminal["complete_transition"]


def test_partial_interval_excluded_with_raw_error_cost_and_both_stop_flags(tmp_path,monkeypatch):
    small_recipe(monkeypatch)
    SyntheticEnv.stop_step, SyntheticEnv.trigger, SyntheticEnv.partial = 100, "v", True
    output = tmp_path/"partial"
    run(output)
    e = read(output,"episodes.json")[0]
    terminal = rows(output)[-1]
    assert e["status"] == "terminated" and e["reason"]["type"] == "SyntheticEnvironmentStop"
    assert e["study_abort"] is not None and e["environment_terminated"] is True
    assert e["physics_steps"] == 1003 and e["metric_control_step_count"] == 0
    assert e["tracking_rmse_rad"] is None and e["partial_interval_target_error_count"] == 1
    assert e["partial_interval_target_errors_rad"] == [terminal["partial_interval_target_error_rad"]]
    assert terminal["partial_interval_target_error_rad"] == terminal["observation_after"]["joint_position"][1]-.0395
    assert not terminal["complete_transition"] and terminal["diagnostics"]["executed_substeps"] == 3
    assert e["phase_effort"]["control"]["requested_squared_nm2_s"] == pytest.approx(.16**2*.006)
    assert e["phase_effort"]["control"]["actual_squared_nm2_s"] == pytest.approx(.16**2*.006)
    assert e["phase_actual_effort_substeps"]["control"] == 3 and e["actual_effort_complete"]


def test_last_planned_complete_step_stop_is_still_ineligible(tmp_path,monkeypatch):
    small_recipe(monkeypatch)
    SyntheticEnv.stop_step, SyntheticEnv.trigger = 299, "v"
    output = tmp_path/"last"
    run(output)
    e = read(output,"episodes.json")[0]
    assert e["control_steps"] == 300 and e["physics_steps"] == 3000 and e["metric_control_step_count"] == 200
    assert e["status"] == "terminated" and not e["complete"]


def test_prefix_excursion_does_not_use_active_research_threshold(tmp_path,monkeypatch):
    small_recipe(monkeypatch)
    SyntheticEnv.prefix_excursion = True
    output = tmp_path/"prefix"
    assert run(output)["all_trials_successful"]
    e = read(output,"episodes.json")[0]
    assert e["phase_risk"]["prefix"]["max_native_speed_rad_s"] == 1.
    assert all(r["study_abort"] is None for r in rows(output)[:100])


@pytest.mark.parametrize("kind",[RuntimeError,OSError,KeyboardInterrupt])
def test_failed_paid_step_records_missing_telemetry_and_fatal_blocks(tmp_path,monkeypatch,kind):
    small_recipe(monkeypatch,2)
    SyntheticEnv.fail_step, SyntheticEnv.failure_type = 100, kind
    output = tmp_path/kind.__name__
    if kind is RuntimeError:
        assert run(output)["complete"]
    else:
        with pytest.raises(kind):
            run(output)
    e, second = read(output,"episodes.json")
    assert e["status"] == "exception" and e["control_calls_attempted"] == 101
    assert e["control_steps"] == 100 and e["physics_steps"] == 1003
    assert e["returned_control_steps"] == e["trace_rows_written"] == 100
    assert e["unreturned_physics_steps"] == 3 and e["actual_effort_is_lower_bound"]
    assert e["phase_actual_effort_missing_substeps"]["control"] == 3
    assert e["phase_effort"]["control"]["requested_squared_nm2_s"] == pytest.approx(.16**2*.006)
    assert second["status"] == ("completed" if kind is RuntimeError else "blocked")
    assert rows(output)[100]["physics_steps_before"] == 1000
    assert rows(output)[100]["physics_steps_after"] == 1003


def test_missing_returned_torque_history_is_not_zero_filled(tmp_path,monkeypatch):
    small_recipe(monkeypatch,2)
    SyntheticEnv.missing_history = True
    output = tmp_path/"missing"
    run(output)
    e, second = read(output,"episodes.json")
    assert e["status"] == "exception" and second["complete"]
    assert e["returned_control_steps"] == 101 and e["trace_rows_written"] == 100
    assert e["returned_unstored_control_steps"] == 1 and e["unreturned_physics_steps"] == 0
    assert e["phase_actual_effort_missing_substeps"]["control"] == 10
    assert e["actual_effort_is_lower_bound"] and e["phase_actual_effort_substeps"]["control"] == 0
    exception = rows(output)[100]
    assert exception["returned_step_diagnostics"]["executed_substeps"] == 10
    assert "applied_torque_history" not in exception["returned_step_diagnostics"]


def test_missing_history_keeps_partial_target_error_and_environment_reason(tmp_path,monkeypatch):
    small_recipe(monkeypatch)
    SyntheticEnv.stop_step, SyntheticEnv.trigger, SyntheticEnv.partial = 100, "v", True
    SyntheticEnv.missing_history = True
    output = tmp_path/"missing_partial"
    run(output)
    e = read(output,"episodes.json")[0]
    exception = rows(output)[100]
    assert e["status"] == "exception" and e["reason"]["type"] == "SyntheticEnvironmentStop"
    assert e["study_abort"] is not None and e["partial_interval_target_error_count"] == 1
    assert e["partial_interval_target_errors_rad"] == [exception["partial_interval_target_error_rad"]]
    assert e["metric_control_step_count"] == 0 and e["tracking_rmse_rad"] is None
    assert e["phase_actual_effort_missing_substeps"]["control"] == 3
    assert exception["returned_step_diagnostics"]["executed_substeps"] == 3


def test_pd_failure_before_step_has_no_stale_return_or_paid_counter(tmp_path,monkeypatch):
    small_recipe(monkeypatch,2)
    original = runner.pd_request
    calls = 0
    def failing_pd(*args):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("synthetic PD proposal failure")
        return original(*args)
    monkeypatch.setattr(runner,"pd_request",failing_pd)
    output = tmp_path/"pd_failure"
    run(output)
    e, second = read(output,"episodes.json")
    exception = rows(output)[100]
    assert e["status"] == "exception" and second["complete"]
    assert e["pd_action_calls"] == e["failed_pd_attempts"] == 1
    assert e["control_calls_attempted"] == e["control_steps"] == e["returned_control_steps"] == 100
    assert e["physics_steps"] == 1000 and e["phase_effort"]["control"] == runner._effort()
    assert exception["control_steps_before"] is None and exception["physics_steps_before"] is None
    assert exception["returned_step_diagnostics"] is None and exception["returned_observation_after"] is None
    assert exception["observation_before"] == exception["observation_after"]


def test_non_io_trace_failure_is_fatal_after_paid_return_and_blocks_rest(tmp_path,monkeypatch):
    small_recipe(monkeypatch,2)
    original = runner.gzip.open
    class BrokenTrace:
        def __init__(self,path,mode,**kwargs):
            self.stream = original(path,mode,**kwargs)
            self.failed = False
        def __enter__(self):
            self.stream.__enter__()
            return self
        def __exit__(self,*args):
            return self.stream.__exit__(*args)
        def write(self,line):
            row = json.loads(line)
            if not self.failed and row.get("control_index") == 100 and "collector_exception" not in row:
                self.failed = True
                raise ValueError("synthetic serialization/trace failure")
            return self.stream.write(line)
    def traced(path,mode,*args,**kwargs):
        return BrokenTrace(path,mode,**kwargs) if mode == "wt" else original(path,mode,*args,**kwargs)
    monkeypatch.setattr(runner.gzip,"open",traced)
    output = tmp_path/"trace"
    with pytest.raises(ValueError,match="trace failure"):
        run(output)
    e, second = read(output,"episodes.json")
    assert e["status"] == "exception" and second["status"] == "blocked"
    assert e["trace_write_failure"] == {"type":"ValueError","message":"synthetic serialization/trace failure"}
    assert "exception_trace_write_error" not in e
    assert e["control_steps"] == 101 and e["physics_steps"] == 1010 and e["returned_unstored_control_steps"] == 1
    assert e["actual_effort_complete"] and not e["risk_telemetry_complete"]
    assert rows(output)[100]["returned_step_diagnostics"]["executed_substeps"] == 10


def test_restricted_api_refuses_extra_seed_gain_joint_pose_before_steps(tmp_path):
    assert list(inspect.signature(runner.run_feedback).parameters) == ["output","protocol_path"]
    for key,value in (("seeds",[20]),("gains",[(1.,0.)]),("joint",0),("pose","prone")):
        with pytest.raises(TypeError):
            runner.run_feedback(tmp_path/key,protocol_path=PROTOCOL,**{key:value})
    with pytest.raises(ValueError,match="exact frozen"):
        runner.run_feedback(tmp_path/"protocol",protocol_path=ROOT/"README.md")
    assert not SyntheticEnv.instances
