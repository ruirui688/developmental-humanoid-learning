"""C synthetic regressions only: no real physics/Git/A/B/PD raw reads.

Instrument actual model mathematics and atomic publications. FakePlanner uses
one real predict per select and reports one, never an invented 81x15 cost.
"""
from copy import deepcopy
import gzip
import importlib.util
import io
import json
import hashlib
import math
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace
import xml.etree.ElementTree as ET

import numpy as np
import pytest

pytest.importorskip("mujoco")
from developmental_physics import local_pair_model as core
from developmental_physics.guard_coupled_pair_model import GuardCoupledPairBodyModel
from developmental_physics.guard_pair_model import KnownAngleGuard

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / "pyproject.toml").is_file())
SOURCE = ROOT / "src/developmental_physics/guard_exploration_development.py"
if not SOURCE.is_file():
    SOURCE = HERE / "guard_exploration_development.py"
spec = importlib.util.spec_from_file_location("c4_exploration_runner_tested", SOURCE)
runner = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = runner
spec.loader.exec_module(runner)

COST = {"real_physical_calls": 0, "real_physics_substeps": 0, "real_git_calls": 0,
    "real_A_B_PD_archive_reads": 0, "fixture_environment_calls": 0, "fixture_environment_substeps": 0,
    "pair_prediction_attempts": 0, "pair_prediction_successes": 0,
    "scalar_prediction_attempts": 0, "scalar_prediction_successes": 0,
    "vector_update_attempts": 0, "committed_vector_updates": 0, "committed_scalar_updates": 0,
    "original_mpc_select_attempts": 0, "fake_planner_select_attempts": 0}
STARTED, CPU_STARTED = time.perf_counter(), time.process_time()


@pytest.fixture(scope="session", autouse=True)
def save_cost():
    yield
    target = os.environ.get("C4_EXPLORATION_SYNTHETIC_COST_PATH")
    if target:
        Path(target).write_text(json.dumps({"scope": "artificial encoder/environment C runner tests only",
            "fixture_environment_counts": "fake Python operations, zero real MuJoCo integration",
            "mathematics": "instrumented actual predictions/atomic publishes, not injected cost declarations",
            "wall_seconds": time.perf_counter()-STARTED, "cpu_seconds": time.process_time()-CPU_STARTED,
            **COST}, indent=2)+"\n", encoding="utf-8")


class FakeEnv:
    instances = []
    fault_trials = set()
    stop_step = fail_step = None
    partial = missing_history = fail_native = False
    changed_prefix_trial = None
    failure_type = RuntimeError

    def __init__(self, config):
        self.config = config
        self.trial = len(self.instances)
        self.instances.append(self)
        self.joint_names = ["left_shoulder", "left_elbow", "right_shoulder", "right_elbow",
                            "left_hip", "left_knee", "right_hip", "right_knee"]
        # Public XML only, no MuJoCo model construction or hidden parameter read.
        xml = ET.fromstring((ROOT / "src/developmental_physics/assets/ground_body.xml").read_bytes())
        factor = math.pi/180. if xml.find("compiler").get("angle") == "degree" else 1.
        entries = {joint.get("name"): [float(x)*factor for x in joint.get("range").split()]
                   for joint in xml.findall(".//joint") if joint.get("name") in self.joint_names}
        self.ranges = np.asarray([entries[name] for name in self.joint_names])
        self.guard = KnownAngleGuard(self.ranges[:2])
        self.model = SimpleNamespace(joint=lambda name: SimpleNamespace(range=self.ranges[self.joint_names.index(name)]))
        self.data = SimpleNamespace(qpos=np.zeros(15), qvel=np.zeros(14))
        self.data.qpos[3] = 1.
        self.q, self.v, self.command = np.zeros(8), np.zeros(8), np.zeros(8)
        self.applied = np.zeros(8)
        self.q[1] = .04 + (.001 if self.trial == self.changed_prefix_trial else 0.)
        self.commands = []
        self.step_id = self.physics_steps = 0
        self.terminated, self.reason = False, None

    def reset(self, seed, pose):
        assert pose == "supine" and seed in runner.RESET_SEEDS.values()
        return self.observation()

    def observation(self):
        if self.fail_native and self.step_id > 100 and self.trial in self.fault_trials:
            raise RuntimeError("injected native getter unavailable")
        self.data.qpos[7:] = self.q
        self.data.qvel[6:] = self.v
        return {"joint_position": self.q.copy(), "joint_velocity": self.v.copy(),
            "imu_gyro": np.zeros(3), "imu_acceleration": np.zeros(3),
            "actuator_torque": self.applied.copy(), "previous_command": self.command.copy()}

    def parameter_fingerprint(self):
        return "synthetic-unchanged-plant"

    def diagnostics(self):
        return {"step_id": self.step_id, "physics_steps": self.physics_steps,
                "time": .002*self.physics_steps, "terminated": self.terminated, "reason": self.reason}

    def step(self, requested):
        COST["fixture_environment_calls"] += 1
        index = self.step_id
        fault = self.trial in self.fault_trials
        if fault and index == self.fail_step:
            self.physics_steps += 3
            COST["fixture_environment_substeps"] += 3
            raise self.failure_type("three synthetic paid substeps, no return")
        self.command = requested.copy()
        self.commands.append(requested.copy())
        self.applied = requested.copy()
        self.applied[:2] = self.guard.project(self.q[:2], requested[:2]).projected_start_nm
        n = 3 if fault and index == self.stop_step and self.partial else 10
        self.v = .5*self.v + .02*self.applied
        self.q += n*.002*self.v
        if fault and index == self.stop_step:
            self.v[1] = 1.
            if self.partial:
                self.terminated = True
                self.reason = {"type": "SyntheticEnvironmentStop", "message": "partial terminal"}
        self.step_id += 1
        self.physics_steps += n
        COST["fixture_environment_substeps"] += n
        diagnostic = {**self.diagnostics(), "executed_substeps": n,
            "applied_torque_history": [self.applied.tolist()]*n, "requested_torque": requested,
            "accepted_torque": requested, "applied_torque": self.applied,
            "guarded_substeps": n if not np.array_equal(requested, self.applied) else 0,
            "substep_ground_normal_forces": [1.]*n, "substep_kinetic_energies": [.2]*n,
            "substep_minimum_contact_distances": [-.0001]*n, "peak_substep_ground_normal_force": 1.,
            "ground_normal_impulse_ns": .002*n, "peak_substep_kinetic_energy": .2,
            "minimum_substep_contact_distance": -.0001}
        if fault and index == 100 and self.missing_history:
            diagnostic.pop("applied_torque_history")
        return SimpleNamespace(observation=self.observation(), diagnostics=diagnostic,
                               terminated=self.terminated, reason=self.reason)


class FakePlanner:
    torque = (.125, .125)

    def __init__(self, model, limits):
        self.model = model

    def spec(self):
        return {"synthetic_planner": True, "prediction_calls_per_select": 1,
                "fixture_boundary": "one measured real predict, no 81-vector/H15 claim"}

    def select(self, q, v, target, previous_torque):
        COST["fake_planner_select_attempts"] += 1
        self.model.predict(q, v, self.torque)
        return SimpleNamespace(torque=self.torque, fallback=False, to_dict=lambda: {
            "torque": list(self.torque), "pair_prediction_attempts": 1, "pair_prediction_successes": 1,
            "scalar_prediction_attempts": 2, "scalar_prediction_successes": 2,
            "failed_pair_prediction_attempts": 0, "unknown_scalar_failure_count": 0,
            "scalar_counts_complete": True, "scalar_counts_is_lower_bound": False,
            "synthetic_planner": True})


@pytest.fixture(autouse=True)
def forbid_real_operations(monkeypatch):
    FakeEnv.instances, FakeEnv.fault_trials = [], set()
    FakeEnv.stop_step = FakeEnv.fail_step = FakeEnv.changed_prefix_trial = None
    FakeEnv.partial = FakeEnv.missing_history = FakeEnv.fail_native = False
    FakeEnv.failure_type = RuntimeError
    FakePlanner.torque = (.125, .125)

    def forbid(*args, **kwargs):
        raise AssertionError("real Git, MuJoCo construction/integration or PD source read forbidden")

    monkeypatch.setattr(runner.subprocess, "check_output", forbid)
    monkeypatch.setattr(runner.mujoco, "mj_step", forbid)
    monkeypatch.setattr(runner._REAL_ENV, "__init__", forbid)
    monkeypatch.setattr(runner, "load_pd_binding", forbid)
    monkeypatch.setattr(runner, "GroundBodyEnv", FakeEnv)
    monkeypatch.setattr(runner, "FixedPairMPC", FakePlanner)
    monkeypatch.setattr(runner, "FORMAL_EXECUTION_FROZEN", False)
    original_read = Path.read_bytes

    def synthetic_only(path):
        if path.resolve().is_relative_to((ROOT / "results/cpu_validation").resolve()):
            raise AssertionError("actual A/B/PD archive bytes forbidden")
        return original_read(path)

    monkeypatch.setattr(Path, "read_bytes", synthetic_only)
    original_predict = core.PairBodyModel._predict_state
    original_output = core.PairBodyModel._predict_output
    original_update = core.PairBodyModel.update
    original_select = core.FixedPairMPC.select

    def predict(self, *args, **kwargs):
        COST["pair_prediction_attempts"] += 1
        answer = original_predict(self, *args, **kwargs)
        COST["pair_prediction_successes"] += 1
        return answer

    def output(self, *args, **kwargs):
        COST["scalar_prediction_attempts"] += 1
        answer = original_output(self, *args, **kwargs)
        COST["scalar_prediction_successes"] += 1
        return answer

    def update(self, *args, **kwargs):
        assert isinstance(self, GuardCoupledPairBodyModel)
        COST["vector_update_attempts"] += 1
        before = self.update_count
        try:
            return original_update(self, *args, **kwargs)
        finally:
            delta = self.update_count-before
            COST["committed_vector_updates"] += delta
            COST["committed_scalar_updates"] += 2*delta

    def select(self, *args, **kwargs):
        COST["original_mpc_select_attempts"] += 1
        return original_select(self, *args, **kwargs)

    monkeypatch.setattr(core.PairBodyModel, "_predict_state", predict)
    monkeypatch.setattr(core.PairBodyModel, "_predict_output", output)
    monkeypatch.setattr(core.PairBodyModel, "update", update)
    monkeypatch.setattr(core.FixedPairMPC, "select", select)


def pd_fixture():
    return {"status": "selected", "selected_id": 2, "kp": [64., 64.], "kd": [0., 4.],
            "synthetic": True, "source_records": {}, "raw_trace_or_episodes_read": False}


def seed_fixture():
    return {"seed": 0, "reset_seed": runner.RESET_SEEDS[0], "calibrations": {},
            "evaluations": {}, "learned_models": {}, "fresh_prefix_bindings": {}}


def episode_fixture(kind):
    duration = 400 if kind.startswith("calibration_") else (100 if kind == "prediction" else 200)
    return {"trial_id": f"seed0_{kind}", "seed": 0, "kind": kind,
        "maximum_control_steps": 100+duration, "status": "planned", "completed": False,
        "phase_budgets": {p: {"control_calls_attempted": 0, "control_steps": 0, "physics_steps": 0}
                          for p in runner.PHASES}}


def trial(kind, writer=None, result=None, models=None):
    result = seed_fixture() if result is None else result
    models = {} if models is None else models
    episode, trace = episode_fixture(kind), writer if writer is not None else io.StringIO()
    runner.run_trial(result, models, episode, trace, pd_fixture())
    return result, models, episode, trace


def suite(tmp_path):
    return runner.run_guard_exploration_development(tmp_path / "raw", protocol_path=HERE / "GUARD_EXPLORATION_DEVELOPMENT_PROTOCOL.md",
        synthetic=True, synthetic_source_bytes={runner.PROTOCOL_PATH: b"handwritten C protocol fixture",
        runner.SOURCE_PATH: SOURCE.read_bytes()}, synthetic_pd_binding=pd_fixture())


def rows(path):
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream]


@pytest.mark.parametrize("kind,slots,duration", [
    ("calibration_sparse", {0: 1., 10: -1.}, 400),
    ("calibration_continuation", {0: 1., 1: 1., 10: -1., 11: -1.}, 400),
    ("prediction", {0: 1., 1: 1., 10: -1., 11: -1.}, 100)])
def test_exact_schedule(kind, slots, duration):
    count = np.zeros(2, dtype=int)
    for active in range(duration):
        planned, requested, diagnostic = runner.exploration_command(kind, active, (1., -1.), (0., .04), (0., 0.), (0., .04))
        assert diagnostic["active_index"] == active and diagnostic["slot_index"] == active % 20
        pulse = slots.get(active % 20, 0.)
        expected = pulse*diagnostic["amplitude_nm"]*np.asarray(diagnostic["shape"])*np.asarray([1., -1.])
        np.testing.assert_array_equal(planned[:2], expected)
        np.testing.assert_array_equal(planned, requested)
        np.testing.assert_array_equal(requested[2:], np.zeros(6))
        assert diagnostic["command_vetoed"] == [False, False]
        count += (requested[:2] != 0).astype(int)
    assert count.tolist() == ([30, 30] if kind == "calibration_sparse" else
                              ([60, 60] if kind == "calibration_continuation" else [16, 16]))


@pytest.mark.parametrize("kind", ["calibration_continuation", "prediction"])
@pytest.mark.parametrize("q,v,veto", [((0., 0.), (.5, 0.), [True, False]),
    ((0., 0.), (-.5, 0.), [True, False]), ((.06, 0.), (0., 0.), [True, False]),
    ((0., .06), (0., 0.), [False, True])])
def test_equal_threshold_per_axis(kind, q, v, veto):
    # Both axes scheduled in calibration block10 / prediction block2.
    active = 200 if kind.startswith("calibration") else 40
    planned, requested, diagnostic = runner.exploration_command(kind, active, (1., 1.), q, v, (0., 0.))
    assert diagnostic["command_vetoed"] == veto
    assert diagnostic["comparison"] == ">=" and diagnostic["learned_gate"] is False
    for axis in range(2):
        assert requested[axis] == (0. if veto[axis] else planned[axis])


def test_sparse_never_veto_and_natural_zero_not_veto():
    planned, requested, diagnostic = runner.exploration_command("calibration_sparse", 200, (1., 1.), (.1, .1), (.8, .8), (0., 0.))
    np.testing.assert_array_equal(planned, requested)
    assert diagnostic["command_vetoed"] == [False, False]
    _, requested, diagnostic = runner.exploration_command("prediction", 42, (1., 1.), (.1, .1), (.8, .8), (0., 0.))
    assert diagnostic["velocity_veto"] == [True, True] and diagnostic["position_veto"] == [True, True]
    assert diagnostic["command_vetoed"] == [False, False] and not requested.any()


def test_control_exploration_function_rejected():
    for kind in runner.KINDS[3:]:
        with pytest.raises(ValueError):
            runner.exploration_command(kind, 0, (1., 1.), (0., 0.), (0., 0.), (0., 0.))


def test_draft_guard_precedes_output_and_sources(tmp_path):
    with pytest.raises(RuntimeError, match="draft C"):
        runner.run_guard_exploration_development(tmp_path / "raw", protocol_path=tmp_path / "missing")
    assert not (tmp_path / "raw").exists()


def test_full_24_matrix_exact_cost_and_freeze(tmp_path):
    metadata = suite(tmp_path)
    assert metadata["complete"] and metadata["all_trials_successful"]
    assert (metadata["control_steps"], metadata["physics_steps"], metadata["model_updates"], metadata["vector_model_updates"]) == (8100, 81000, 4800, 2400)
    assert len(FakeEnv.instances) == 24
    records = json.loads((tmp_path / "raw/seed_results.json").read_text())
    trace = rows(tmp_path / "raw/trace.jsonl.gz")
    assert len(trace) == 8100
    for seed in records:
        assert len(seed["fresh_prefix_bindings"]) == 8
        assert set(seed["learned_models"]) == {"learned_sparse", "learned_continuation"}
        for name, cal in seed["calibrations"].items():
            assert cal["completed"] and cal["committed_scalar_updates"] == 800
            assert cal["initial_model"]["scalar_update_count"] == 0
            assert cal["rls_prediction_accounting"]["pair_prediction_attempts"] == 400
            assert not cal["frozen_model"]["trainable"]
            assert cal["excitation"]["nonzero_start_guard_intervals_per_axis"][0] > 0
        prediction = seed["evaluations"]["prediction"]
        assert prediction["available_models"] == list(runner.MPC_KINDS)
        assert prediction["diagnostic_prediction_accounting"]["pair_prediction_attempts"] == 300
        assert set(prediction["metric_prediction_step_count"]) == {*runner.MPC_KINDS, "persistence"}
        for kind in runner.KINDS[3:]:
            ev = seed["evaluations"][kind]
            assert ev["model_updates"] == 0 and ev["models_before"] == ev["models_after"]
            assert ev["metric_control_step_count"] == 200
            assert ev["diagnostic_prediction_accounting"]["pair_prediction_attempts"] == (200 if kind in runner.MPC_KINDS else 0)
    active = [row for row in trace if row["phase"] == "control"]
    assert all(row["exploration_diagnostics"] is None for row in active)
    assert all(row["requested_torque"][2:] == [0.]*6 for row in trace)


def test_sparse_failure_continuation_is_independent(tmp_path):
    FakeEnv.fault_trials, FakeEnv.stop_step = {0}, 100
    metadata = suite(tmp_path)
    seed = json.loads((tmp_path / "raw/seed_results.json").read_text())[0]
    assert metadata["complete"] and not metadata["all_trials_successful"]
    assert seed["calibrations"]["sparse"]["committed_scalar_updates"] == 2
    assert seed["calibrations"]["sparse"]["frozen_model"] is None
    assert seed["calibrations"]["continuation"]["completed"]
    assert seed["evaluations"]["prediction"]["available_models"] == ["nominal_guard", "learned_continuation"]
    assert seed["evaluations"]["prediction"]["model_availability"]["learned_sparse"] == "unavailable"
    assert seed["evaluations"]["learned_sparse"]["status"] == "blocked"
    assert all(seed["evaluations"][k]["completed"] for k in ("learned_continuation", "nominal_guard", "PDselected", "zero"))
    assert metadata["model_updates"] == 4002


def test_both_calibration_failures_only_block_learning_dependencies(tmp_path):
    FakeEnv.fault_trials, FakeEnv.stop_step = {0, 1}, 100
    metadata = suite(tmp_path)
    seed = json.loads((tmp_path / "raw/seed_results.json").read_text())[0]
    assert metadata["complete"] and seed["learned_models"] == {}
    assert seed["evaluations"]["prediction"]["status"] == "blocked"
    for kind in ("learned_sparse", "learned_continuation"):
        assert seed["evaluations"][kind]["status"] == "blocked"
    assert all(seed["evaluations"][k]["completed"] for k in ("nominal_guard", "PDselected", "zero"))


def test_partial_calibration_no_update_or_publish():
    FakeEnv.fault_trials, FakeEnv.stop_step, FakeEnv.partial = {0}, 100, True
    result, models, episode, trace = trial("calibration_continuation")
    assert episode["status"] == "terminated" and episode["physics_steps"] == 1003
    cal = result["calibrations"]["continuation"]
    assert cal["committed_scalar_updates"] == 0 and cal["attempted_vector_updates"] == 0
    assert cal["frozen_model"] is None and "learned_continuation" not in models
    row = json.loads(trace.getvalue().splitlines()[-1])
    assert row["model_update"]["updated"] is False and row["predicted_next_qv"] == {}


def test_original_mpc_cost_is_real_not_fixture_claim(monkeypatch):
    FakeEnv.fault_trials, FakeEnv.stop_step = {0}, 100
    monkeypatch.setattr(runner, "FixedPairMPC", core.FixedPairMPC)
    result, _, episode, trace = trial("nominal_guard")
    assert episode["status"] == "terminated" and episode["control_steps"] == 101
    evaluation = result["evaluations"]["nominal_guard"]
    assert evaluation["planning_accounting"]["pair_prediction_attempts"] == 81*15
    assert evaluation["diagnostic_prediction_accounting"]["pair_prediction_attempts"] == 1
    decision = json.loads(trace.getvalue().splitlines()[-1])["planner_decision"]
    assert len(decision["candidate_records"]) == 81


def test_control_keeps_full_permission_without_exploration_veto(monkeypatch):
    FakeEnv.fault_trials, FakeEnv.stop_step = {0}, 100
    FakePlanner.torque = (.5, -.5)
    original = runner.exploration_command

    def exploration_only(kind, *args):
        assert kind in runner.KINDS[:3]
        return original(kind, *args)

    monkeypatch.setattr(runner, "exploration_command", exploration_only)
    _, _, episode, trace = trial("nominal_guard")
    row = json.loads(trace.getvalue().splitlines()[-1])
    assert row["requested_torque"][:2] == [.5, -.5]
    assert row["exploration_diagnostics"] is None and episode["status"] == "terminated"


def test_atomic_second_head_failure_no_partial_publish(monkeypatch):
    original = core.PairBodyModel._propose_update

    def fail_second(self, index, *args, **kwargs):
        if index == 1:
            raise ValueError("injected second-head proposal failure")
        return original(self, index, *args, **kwargs)

    monkeypatch.setattr(core.PairBodyModel, "_propose_update", fail_second)
    result, models, episode, trace = trial("calibration_sparse")
    cal = result["calibrations"]["sparse"]
    assert episode["status"] == "exception" and cal["attempted_vector_updates"] == 1
    assert cal["committed_scalar_updates"] == 0 and cal["model_snapshot"] == cal["initial_model"]
    assert "learned_sparse" not in models and episode["returned_unwritten_steps"] == 1
    failure = json.loads(trace.getvalue().splitlines()[-1])
    assert failure["failure_accounting"]["structured_failure"]["committed_scalar_updates"] == 0


def test_post_publish_interrupt_keeps_atomic_cost(monkeypatch):
    original = core.PairBodyModel.update

    def interrupt(self, *args, **kwargs):
        original(self, *args, **kwargs)
        raise KeyboardInterrupt("injected interrupt after complete atomic publish")

    monkeypatch.setattr(core.PairBodyModel, "update", interrupt)
    result, episode = seed_fixture(), episode_fixture("calibration_sparse")
    with pytest.raises(KeyboardInterrupt):
        runner.run_trial(result, {}, episode, io.StringIO(), pd_fixture())
    cal = result["calibrations"]["sparse"]
    assert cal["committed_vector_updates"] == 1 and cal["committed_scalar_updates"] == 2
    assert cal["model_snapshot"]["output_update_counts"] == [1, 1] and cal["frozen_model"] is None


def test_unreturned_paid_substeps_and_request_effort_retained():
    FakeEnv.fault_trials, FakeEnv.fail_step = {0}, 100
    result, _, episode, trace = trial("calibration_sparse")
    assert (episode["control_steps"], episode["physics_steps"], episode["control_calls_attempted"]) == (100, 1003, 101)
    assert episode["unreturned_physics_steps"] == 3 and episode["returned_steps"] == 100
    ev = result["evaluations"]["calibration_sparse"]
    assert ev["phase_missing_actual_effort_substeps"]["calibration"] == 3
    assert ev["phase_effort"]["calibration"]["requested_absolute_nm_s"][0] == pytest.approx(.125*.006)
    assert result["calibrations"]["sparse"]["committed_scalar_updates"] == 0


def test_prediction_success_then_write_failure_keeps_three_calls():
    result, models, _, _ = trial("calibration_continuation")
    # Fresh trial number1, writer fails first active normal row then permits exception.
    class FailWriter(io.StringIO):
        writes = 0

        def write(self, value):
            self.writes += 1
            if self.writes == 101:
                raise OSError("injected trace write failure after causal predictions and paid step")
            return super().write(value)

    episode = episode_fixture("prediction")
    with pytest.raises(OSError):
        runner.run_trial(result, models, episode, FailWriter(), pd_fixture())
    ev = result["evaluations"]["prediction"]
    assert ev["diagnostic_prediction_accounting"]["pair_prediction_successes"] == 2
    assert episode["returned_unwritten_steps"] == 1 and episode["control_steps"] == 101
    assert episode["trace_write_failure"] is not None
    assert result["calibrations"]["continuation"]["committed_scalar_updates"] == 800


def test_missing_native_getter_does_not_hide_paid_failure():
    FakeEnv.fault_trials, FakeEnv.fail_native = {0}, True
    result, _, episode, trace = trial("calibration_sparse")
    assert episode["control_steps"] == 101 and episode["physics_steps"] == 1010
    assert episode["unreturned_physics_steps"] == 10
    assert result["calibrations"]["sparse"]["committed_scalar_updates"] == 0
    failure = json.loads(trace.getvalue().splitlines()[-1])
    assert failure["observation_after_retrieval_error"]["message"] == "injected native getter unavailable"


def test_missing_actual_history_explicit_lower_bound():
    FakeEnv.fault_trials, FakeEnv.missing_history = {0}, True
    result, _, episode, _ = trial("calibration_sparse")
    assert episode["status"] == "exception" and episode["control_steps"] == 101
    ev = result["evaluations"]["calibration_sparse"]
    assert not ev["phase_actual_effort_complete"]["calibration"]
    assert ev["phase_missing_actual_effort_substeps"]["calibration"] == 10
    assert result["calibrations"]["sparse"]["committed_scalar_updates"] == 0


def test_unknown_failed_planner_is_lower_bound(monkeypatch):
    def fail(self, *args, **kwargs):
        raise RuntimeError("unknown planner failure, no fabricated work")

    monkeypatch.setattr(FakePlanner, "select", fail)
    result, _, episode, _ = trial("nominal_guard")
    ev = result["evaluations"]["nominal_guard"]
    assert episode["control_steps"] == 100 and ev["failed_planner_attempts"] == 1
    assert ev["planning_accounting"]["unknown_failed_planner_calls"] == 1
    assert ev["planning_accounting"]["scalar_counts_is_lower_bound"]
    assert ev["planning_accounting"]["pair_prediction_attempts"] == 0


def test_later_native_prefix_not_repaired():
    result, models, _, _ = trial("calibration_sparse")
    FakeEnv.changed_prefix_trial = 1
    result, _, episode, _ = trial("calibration_continuation", result=result, models=models)
    assert episode["status"] == "exception" and episode["control_steps"] == 100
    assert "differs" in episode["collector_exception"]["message"]
    assert result["calibrations"]["continuation"]["initial_model"] is None
    assert "learned_sparse" in models and "learned_continuation" not in models


def test_single_original_mpc_engineering_archive(monkeypatch):
    """One permanent fake archive; all nine MPCs stop on first active interval.

    Exact public asset ranges, current C auditor and four math supports are bound.
    Collection is never repeated to fix an auditor. Synthetic is never validated.
    """
    target = os.environ.get("C4_EXPLORATION_ENGINEERING_ARCHIVE_PATH")
    expected_auditor_sha = os.environ.get("C4_EXPLORATION_ENGINEERING_AUDITOR_SHA256")
    if target is None:
        pytest.skip("permanent engineering archive not explicitly requested")
    auditor_path = ROOT / "external/c4_guard_exploration_audit_staging/audit_guard_exploration_development.py"
    auditor_bytes = auditor_path.read_bytes()
    assert expected_auditor_sha is not None
    assert hashlib.sha256(auditor_bytes).hexdigest() == expected_auditor_sha
    sources = {p.relative_to(ROOT).as_posix(): p.read_bytes()
               for p in sorted((ROOT / "src/developmental_physics").glob("*.py"))}
    for name in ("src/developmental_physics/assets/ground_body.xml", "pyproject.toml",
                 runner.PD_PROTOCOL_PATH, *runner.AUDITOR_SUPPORT_PATHS):
        sources[name] = (ROOT / name).read_bytes()
    sources[runner.SOURCE_PATH] = SOURCE.read_bytes()
    sources[runner.PROTOCOL_PATH] = (HERE / "GUARD_EXPLORATION_DEVELOPMENT_PROTOCOL.md").read_bytes()
    sources[runner.AUDITOR_PATH] = auditor_bytes
    FakeEnv.fault_trials, FakeEnv.stop_step = {3, 4, 5, 11, 12, 13, 19, 20, 21}, 100
    monkeypatch.setattr(runner, "FixedPairMPC", core.FixedPairMPC)
    before_cost = deepcopy(COST)
    metadata = runner.run_guard_exploration_development(Path(target),
        protocol_path=HERE / "GUARD_EXPLORATION_DEVELOPMENT_PROTOCOL.md", synthetic=True,
        synthetic_source_bytes=sources, synthetic_pd_binding=pd_fixture())
    assert metadata["complete"] and metadata["synthetic"] and not metadata["all_trials_successful"]
    assert (metadata["control_steps"], metadata["physics_steps"], metadata["model_updates"]) == (6309, 63090, 4800)
    assert metadata["completed_trials"] == 15 and metadata["terminated_trials"] == 9
    after = {key: COST[key]-before_cost[key] for key in COST}
    assert after["original_mpc_select_attempts"] == 9 and after["fake_planner_select_attempts"] == 0
    assert after["committed_scalar_updates"] == 4800
    Path(target).parent.joinpath("engineering_cost.json").write_text(json.dumps({
        "scope": "one fixed artificial original-MPC 24-plan archive, never real physics",
        "archive": str(Path(target)), "actual_math_and_fixture_delta": after,
        "auditor_sha256_before_collection": expected_auditor_sha,
        "scientific_validated": False}, indent=2)+"\n", encoding="utf-8")
