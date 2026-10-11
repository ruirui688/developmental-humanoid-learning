"""Artificial A records + fake dynamics only; real physics/Git are forbidden.

Actual mathematical calls and atomic RLS commits are counted. Fake environment
calls are fixture operations, not MuJoCo calls. The substituted planner performs
one actual prediction and declares that single cost; it never claims 81x15 work.
One test explicitly exercises the original FixedPairMPC against fake encoders.
"""
from copy import deepcopy
import gzip
import importlib
import importlib.util
import inspect
import io
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
import pytest

pytest.importorskip("mujoco")
from developmental_physics import local_pair_model as core
from developmental_physics import guard_pair_model as diagonal_core

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / "pyproject.toml").is_file())
sys.path.insert(0, str(HERE))
if (ROOT / "src/developmental_physics/guard_pair_source_binding.py").is_file():
    binding_module = importlib.import_module("developmental_physics.guard_pair_source_binding")
else:
    import guard_pair_source_binding as binding_module
sys.modules["guard_pair_source_binding"] = binding_module
from synthetic_a_source_fixture import ArtificialAArchive

sys.modules["developmental_physics.guard_pair_source_binding"] = binding_module
model_source = ROOT / "src/developmental_physics/guard_coupled_pair_model.py"
if model_source.is_file():
    model_module = importlib.import_module("developmental_physics.guard_coupled_pair_model")
else:
    model_source = ROOT / "external/c4_guard_coupled_staging/guard_coupled_pair_model.py"
    model_spec = importlib.util.spec_from_file_location("developmental_physics.guard_coupled_pair_model", model_source)
    model_module = importlib.util.module_from_spec(model_spec)
    sys.modules[model_spec.name] = model_module
    model_spec.loader.exec_module(model_module)
runner_source = ROOT / "src/developmental_physics/guard_coupled_development.py"
if not runner_source.is_file():
    runner_source = HERE / "guard_coupled_development.py"
runner_spec = importlib.util.spec_from_file_location("c4_coupled_runner_tested", runner_source)
runner = importlib.util.module_from_spec(runner_spec)
sys.modules[runner_spec.name] = runner
runner_spec.loader.exec_module(runner)

COST = {"real_physical_calls": 0, "real_physics_substeps": 0, "real_git_calls": 0,
        "real_A_archive_reads": 0, "fixture_environment_calls": 0, "fixture_environment_substeps": 0,
        "pair_prediction_attempts": 0, "pair_prediction_successes": 0,
        "scalar_prediction_attempts": 0, "scalar_prediction_successes": 0,
        "vector_update_attempts": 0, "committed_vector_updates": 0, "committed_scalar_updates": 0,
        "original_mpc_select_attempts": 0, "fake_planner_select_attempts": 0}


@pytest.fixture(scope="session", autouse=True)
def save_cost():
    yield
    target = os.environ.get("C4_COUPLED_SYNTHETIC_COST_PATH")
    if target:
        Path(target).write_text(json.dumps({
            "scope": "artificial A fixtures and synthetic B runner tests only",
            "prior_A_physics_and_RLS": "fixture handwritten declarations, zero real prior A operations",
            "prediction_and_update_counts": "instrumented actual mathematical calls; successful atomic publishes",
            "injected_failure_ledgers": "handwritten exception-cost assertions are synthetic test inputs, excluded from actual math-call totals",
            "fixture_environment_counts": "fake Python operations, not physical simulation",
            **COST}, indent=2) + "\n", encoding="utf-8")


class FakeEnv:
    instances = []
    plant = ""
    qref_delta = 0.
    range_delta = 0.
    plant_delta = False
    stop_step = fail_step = None
    partial = missing_history = prefix_excursion = False
    stop_joint = 1
    stop_signal = "v"
    fault_trial = 0
    failure_type = RuntimeError

    def __init__(self, config):
        self.config = config
        self.trial = len(self.instances)
        self.instances.append(self)
        self.joint_names = [str(i) for i in range(8)]
        self.ranges = np.asarray([[-1.7, 1.7], [0., 2.36], [-1.7, 1.7], [0., 2.36],
                                  [-1.5, 1.5], [0., 2.36], [-1.5, 1.5], [0., 2.36]])
        self.ranges[1, 1] += self.range_delta
        self.model = SimpleNamespace(joint=lambda name: SimpleNamespace(range=self.ranges[int(name)]))
        self.data = SimpleNamespace(qpos=np.zeros(15), qvel=np.zeros(14))
        self.data.qpos[3] = 1.
        self.q, self.v, self.command = np.zeros(8), np.zeros(8), np.zeros(8)
        self.q[1] = .04 + self.qref_delta
        self.commands = []
        self.step_id = self.physics_steps = 0
        self.terminated = False
        self.reason = None

    def reset(self, seed, pose):
        assert pose == "supine" and seed in binding_module.RESET_SEEDS.values()
        return self.observation()

    def observation(self):
        self.data.qpos[7:] = self.q
        self.data.qvel[6:] = self.v
        return {"joint_position": self.q.copy(), "joint_velocity": self.v.copy(),
                "imu_gyro": np.zeros(3), "imu_acceleration": np.zeros(3),
                "actuator_torque": self.command.copy(), "previous_command": self.command.copy()}

    def parameter_fingerprint(self):
        return "0"*64 if self.plant_delta else self.plant

    def diagnostics(self):
        return {"step_id": self.step_id, "physics_steps": self.physics_steps,
                "time": .002*self.physics_steps, "terminated": self.terminated, "reason": self.reason}

    def step(self, requested):
        COST["fixture_environment_calls"] += 1
        index = self.step_id
        if self.trial == self.fault_trial and index == self.fail_step:
            self.physics_steps += 3
            COST["fixture_environment_substeps"] += 3
            raise self.failure_type("three synthetic paid substeps, no return")
        self.command = requested.copy()
        self.commands.append(requested.copy())
        n = 3 if self.trial == self.fault_trial and index == self.stop_step and self.partial else 10
        self.v = .5*self.v + .02*requested
        self.q += n*.002*self.v
        if self.prefix_excursion and index == 0:
            self.v[1] = 1.
        elif self.prefix_excursion and index == 1:
            self.q[:] = self.v[:] = 0.
            self.q[1] = .04 + self.qref_delta
        if self.trial == self.fault_trial and index == self.stop_step:
            if self.stop_signal == "v":
                self.v[self.stop_joint] = 1.
            else:
                self.q[self.stop_joint] = (0. if self.stop_joint == 0 else .04) + .12
            if self.partial:
                self.terminated = True
                self.reason = {"type": "SyntheticEnvironmentStop", "message": "partial terminal"}
        self.step_id += 1
        self.physics_steps += n
        COST["fixture_environment_substeps"] += n
        diagnostic = {**self.diagnostics(), "executed_substeps": n,
            "applied_torque_history": [requested.tolist()]*n, "requested_torque": requested,
            "accepted_torque": requested, "applied_torque": requested, "guarded_substeps": 0,
            "substep_ground_normal_forces": [1.]*n, "substep_kinetic_energies": [.2]*n,
            "substep_minimum_contact_distances": [-.0001]*n, "peak_substep_ground_normal_force": 1.,
            "ground_normal_impulse_ns": .002*n, "peak_substep_kinetic_energy": .2,
            "minimum_substep_contact_distance": -.0001}
        if self.trial == self.fault_trial and index == 100 and self.missing_history:
            diagnostic.pop("applied_torque_history")
        return SimpleNamespace(observation=self.observation(), diagnostics=diagnostic,
                               terminated=self.terminated, reason=self.reason)


class FakePlanner:
    def __init__(self, model, limits):
        self.model, self.limits = model, limits

    def spec(self):
        return {"synthetic_planner": True, "prediction_calls_per_select": 1,
                "fixture_boundary": "one measured real math prediction; no 81-vector/H15 claim"}

    def select(self, q, v, target, previous_torque):
        COST["fake_planner_select_attempts"] += 1
        self.model.predict(q, v, (.125, .125))
        return SimpleNamespace(torque=(.125, .125), fallback=False, to_dict=lambda: {
            "torque": [.125, .125], "pair_prediction_attempts": 1, "pair_prediction_successes": 1,
            "scalar_prediction_attempts": 2, "scalar_prediction_successes": 2,
            "failed_pair_prediction_attempts": 0, "unknown_scalar_failure_count": 0,
            "scalar_counts_complete": True, "scalar_counts_is_lower_bound": False,
            "synthetic_planner": True})


@pytest.fixture(autouse=True)
def forbidden_real_operations(monkeypatch):
    FakeEnv.instances = []
    FakeEnv.qref_delta = FakeEnv.range_delta = 0.
    FakeEnv.plant_delta = False
    FakeEnv.stop_step = FakeEnv.fail_step = None
    FakeEnv.partial = FakeEnv.missing_history = FakeEnv.prefix_excursion = False
    FakeEnv.stop_joint, FakeEnv.stop_signal = 1, "v"
    FakeEnv.fault_trial, FakeEnv.failure_type = 0, RuntimeError

    def forbid(*args, **kwargs):
        raise AssertionError("real Git, physics or diagonal refit is forbidden")

    monkeypatch.setattr(runner.subprocess, "check_output", forbid)
    monkeypatch.setattr(runner.mujoco, "mj_step", forbid)
    monkeypatch.setattr(runner._REAL_ENV, "__init__", forbid)
    monkeypatch.setattr(diagonal_core.InputMappedDiagonalPairBodyModel, "update", forbid)
    monkeypatch.setattr(runner, "GroundBodyEnv", FakeEnv)
    monkeypatch.setattr(runner, "FixedPairMPC", FakePlanner)
    monkeypatch.setattr(runner, "FORMAL_EXECUTION_FROZEN", False)
    original_read = Path.read_bytes
    actual_a_root = (ROOT / binding_module.A_ROOT).resolve()

    def read_fake_only(path):
        if path.resolve().is_relative_to(actual_a_root):
            raise AssertionError("actual A archive read is forbidden")
        return original_read(path)

    monkeypatch.setattr(Path, "read_bytes", read_fake_only)

    original_predict = core.PairBodyModel._predict_state
    original_output = core.PairBodyModel._predict_output
    original_update = core.PairBodyModel.update
    original_select = core.FixedPairMPC.select

    def predict(self, *args, **kwargs):
        COST["pair_prediction_attempts"] += 1
        output = original_predict(self, *args, **kwargs)
        COST["pair_prediction_successes"] += 1
        return output

    def output(self, *args, **kwargs):
        COST["scalar_prediction_attempts"] += 1
        value = original_output(self, *args, **kwargs)
        COST["scalar_prediction_successes"] += 1
        return value

    def update(self, *args, **kwargs):
        assert isinstance(self, model_module.GuardCoupledPairBodyModel)
        COST["vector_update_attempts"] += 1
        old = self.update_count
        try:
            return original_update(self, *args, **kwargs)
        finally:
            delta = self.update_count - old
            COST["committed_vector_updates"] += delta
            COST["committed_scalar_updates"] += 2*delta

    def select(self, *args, **kwargs):
        COST["original_mpc_select_attempts"] += 1
        return original_select(self, *args, **kwargs)

    monkeypatch.setattr(core.PairBodyModel, "_predict_state", predict)
    monkeypatch.setattr(core.PairBodyModel, "_predict_output", output)
    monkeypatch.setattr(core.PairBodyModel, "update", update)
    monkeypatch.setattr(core.FixedPairMPC, "select", select)


def artificial(tmp_path, mutate=None):
    fixture = ArtificialAArchive(tmp_path / "artificial_repo")
    if mutate:
        mutate(fixture)
    fixture.write()
    FakeEnv.plant = fixture.plant
    bound = binding_module.load_a_source_binding(fixture.root, **fixture.kwargs())
    return fixture, bound


def run(tmp_path, monkeypatch, mutate=None, seeds=(0,)):
    monkeypatch.setattr(runner, "DEVELOPMENT_SEEDS", seeds)
    fixture, bound = artificial(tmp_path, mutate)
    output = tmp_path / "b_output"
    sources = {runner.PROTOCOL_PATH: b"explicit artificial B protocol",
               runner.SOURCE_PATH: runner_source.read_bytes()}
    metadata = runner.run_guard_coupled_development(output, protocol_path=ROOT / runner.PROTOCOL_PATH,
        synthetic=True, synthetic_source_bytes=sources, binding=bound)
    return output, metadata, fixture, bound


def saved(path, name):
    return json.loads((path / name).read_text(encoding="utf-8"))


def rows(path, name):
    with gzip.open(path / name, "rt", encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def test_draft_rejects_real_before_any_source_or_output_read(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "FORMAL_EXECUTION_FROZEN", False)
    output = tmp_path / "untouched"
    with pytest.raises(RuntimeError, match="draft B real execution disabled"):
        runner.run_guard_coupled_development(output, protocol_path=tmp_path / "missing")
    assert not output.exists() and not FakeEnv.instances


def test_synthetic_requires_explicit_env_and_binding(tmp_path, monkeypatch):
    with pytest.raises(RuntimeError, match="strict artificial A binding"):
        runner.run_guard_coupled_development(tmp_path / "untouched", protocol_path=tmp_path / "missing", synthetic=True)
    monkeypatch.setattr(runner, "GroundBodyEnv", runner._REAL_ENV)
    with pytest.raises(RuntimeError, match="replaced environment"):
        runner.run_guard_coupled_development(tmp_path / "untouched", protocol_path=tmp_path / "missing", synthetic=True)


def test_formal_source_precheck_passes_all_shared_A_paths_with_fake_Git(tmp_path, monkeypatch):
    root = tmp_path / "formal_mock_repo"
    names = {runner.SOURCE_PATH, runner.PROTOCOL_PATH, runner.AUDITOR_PATH,
             *runner.AUDITOR_SUPPORT_PATHS, *binding_module.SHARED_SOURCE_PATHS,
             "pyproject.toml", binding_module.ASSET_PATH}
    content = {name: ("explicit fake tracked source: " + name).encode() for name in names}
    for name, data in content.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    commit = "a"*40
    commands = []
    def fake_git(command, *, cwd, text=False):
        assert cwd == root
        commands.append(command)
        if command[1:3] == ["rev-parse", "HEAD"]:
            return commit
        if command[1:3] == ["status", "--porcelain"]:
            return ""
        if command[1:] == ["ls-files"]:
            return "\n".join(sorted(names))
        if command[1] == "show":
            return content[command[2].split(":", 1)[1]]
        raise AssertionError("unexpected fake Git command")
    captured = {}
    sentinel = object()
    def bound(source_root, **kwargs):
        captured.update(source_root=source_root, **kwargs)
        return sentinel
    monkeypatch.setattr(runner, "__file__", str(root / runner.SOURCE_PATH))
    monkeypatch.setattr(runner, "MODEL_PATH", root / binding_module.ASSET_PATH)
    monkeypatch.setattr(runner.subprocess, "check_output", fake_git)
    monkeypatch.setattr(runner, "load_a_source_binding", bound)
    found_commit, status, sources, found_binding = runner._formal_provenance(root, (root / runner.PROTOCOL_PATH).resolve())
    assert found_commit == commit and status == "" and found_binding is sentinel
    assert binding_module.SHARED_SOURCE_PATHS.issubset(sources)
    assert binding_module.A_PROTOCOL_PATH in captured["current_source_bytes"]
    assert binding_module.A_AUDITOR_PATH in captured["current_source_bytes"]
    assert captured["synthetic"] is False and captured["tracked_paths"] == names
    assert not FakeEnv.instances and len(commands) >= len(names)+3


def test_complete_three_seed_budget_and_exact_offline_ids(tmp_path, monkeypatch):
    before = dict(COST)
    output, metadata, fixture, bound = run(tmp_path, monkeypatch, seeds=(0, 1, 2))
    assert metadata["complete"] and metadata["all_trials_successful"] and metadata["synthetic"]
    assert (metadata["control_calls_attempted"], metadata["control_steps"], metadata["physics_steps"]) == (900, 900, 9000)
    assert (metadata["model_updates"], metadata["vector_model_updates"]) == (2400, 1200)
    assert COST["committed_vector_updates"]-before["committed_vector_updates"] == 1200
    assert COST["pair_prediction_attempts"]-before["pair_prediction_attempts"] == 2700
    assert COST["scalar_prediction_attempts"]-before["scalar_prediction_attempts"] == 5400
    cal_rows, pred_rows, control_rows = (rows(output, name) for name in (
        "calibration_replay.jsonl.gz", "prediction_replay.jsonl.gz", "trace.jsonl.gz"))
    assert (len(cal_rows), len(pred_rows), len(control_rows)) == (1200, 300, 900)
    for seed, result in enumerate(saved(output, "seed_results.json")):
        replay = result["calibration_replay"]
        assert replay["source_transition_ids"] == [f"seed{seed}_calibration:{i}" for i in range(100, 500)]
        assert replay["committed_scalar_updates"] == 800 and replay["new_physical_calls"] == 0
        assert replay["rls_prediction_accounting"]["pair_prediction_attempts"] == 400
        assert replay["frozen_model"]["trainable"] is False
        assert result["prediction_replay"]["prediction_accounting"]["pair_prediction_attempts"] == 100
        assert result["reused_baselines"] == bound.seed(seed)["reused_baselines"]
        assert result["reused_baselines"]["learned_guard"]["status"] == "terminated"
        controls = [r for r in control_rows if r["seed"] == seed and r["phase"] == "control"]
        assert controls[0]["target_q"] == [.04, .08]
        assert controls[100]["target_q"] == [.08, .12]
        assert all(r["model_update"] is None and r["requested_torque"][2:] == [0.]*6 for r in controls)
        assert result["evaluations"][runner.MODEL_NAME]["control_effort"]["actual_absolute_nm_s"] == pytest.approx([.5, .5])
    assert metadata["a_binding"]["scientific_A_contribution_required"] is False
    assert len(FakeEnv.instances) == 3


def test_incomplete_calibration_blocks_only_its_seed_without_replay(tmp_path, monkeypatch):
    def incomplete(fixture):
        fixture.seeds[0]["calibration_completed"] = False
        fixture.seeds[0]["learned_models"] = {}
        fixture.rows = [r for r in fixture.rows if not (r["trial_id"] == "seed0_calibration" and r["step_index"] >= 110)]
        ep = next(e for e in fixture.episodes if e["trial_id"] == "seed0_calibration")
        ep.update(status="terminated", completed=False)
    output, metadata, *_ = run(tmp_path, monkeypatch, mutate=incomplete, seeds=(0, 1, 2))
    result = saved(output, "seed_results.json")[0]
    assert result["calibration_replay"]["committed_scalar_updates"] == 0
    assert saved(output, "episodes.json")[0]["status"] == "blocked"
    assert metadata["blocked_trials"] == 1 and metadata["model_updates"] == 1600
    assert metadata["control_steps"] == 600 and metadata["physics_steps"] == 6000
    assert all(row["seed"] != 0 for row in rows(output, "calibration_replay.jsonl.gz"))


def test_full_terminal_A_calibration_not_a_complete_dependency(tmp_path, monkeypatch):
    def terminal(fixture):
        fixture.seeds[0]["calibration_completed"] = False
        fixture.seeds[0]["learned_models"] = {}
        last = next(r for r in fixture.rows if r["shared_transition_id"] == "seed0_calibration:499")
        last["study_abort"] = {"type": "SyntheticStudyAbort"}
        next(e for e in fixture.episodes if e["trial_id"] == "seed0_calibration").update(status="terminated", completed=False)
    output, metadata, *_ = run(tmp_path, monkeypatch, mutate=terminal)
    assert metadata["model_updates"] == metadata["control_calls_attempted"] == metadata["physics_steps"] == 0
    assert saved(output, "seed_results.json")[0]["calibration_replay"]["status"] == "blocked"


def test_partial_A_prediction_once_scored_separately_no_fit_control_allowed(tmp_path, monkeypatch):
    def partial(fixture):
        fixture.rows = [r for r in fixture.rows if not (r["trial_id"] == "seed0_prediction" and r["step_index"] > 102)]
        last = next(r for r in fixture.rows if r["shared_transition_id"] == "seed0_prediction:102")
        last["diagnostics"].update(executed_substeps=3, terminated=True)
        next(e for e in fixture.episodes if e["trial_id"] == "seed0_prediction").update(status="terminated", completed=False)
    output, metadata, *_ = run(tmp_path, monkeypatch, mutate=partial)
    result = saved(output, "seed_results.json")[0]
    replay = result["prediction_replay"]
    assert replay["prediction_accounting"]["pair_prediction_attempts"] == 3
    assert replay["metric_complete_endpoints"] == 2 and len(replay["partial_endpoint_scores"]) == 1
    assert replay["status"] == "terminated" and not replay["completed"]
    assert replay["model_fingerprint_before"] == replay["model_fingerprint_after"]
    assert metadata["completed_trials"] == 1 and metadata["model_updates"] == 800


def test_replay_causal_outputs_do_not_depend_on_labels(tmp_path):
    _, bound = artificial(tmp_path)
    data = bound.seed(0)
    result = {}
    model = runner.replay_calibration(data, io.StringIO(), result)
    changed = deepcopy(data)
    for row in changed["prediction_transitions"]:
        row["observation_after"]["joint_velocity"][0] = .875
    a, b = io.StringIO(), io.StringIO()
    ra, rb = {}, {}
    runner.replay_prediction(data, model, a, ra)
    runner.replay_prediction(changed, model, b, rb)
    left = [json.loads(x)["predicted_next_qv"] for x in a.getvalue().splitlines()]
    right = [json.loads(x)["predicted_next_qv"] for x in b.getvalue().splitlines()]
    assert left == right
    assert ra["prediction_replay"]["velocity_prediction_rmse"] != rb["prediction_replay"]["velocity_prediction_rmse"]
    assert model.scalar_update_count == 800 and not model.trainable


@pytest.mark.parametrize("signal,joint", [("v", 0), ("v", 1), ("q", 0), ("q", 1)])
def test_equal_active_boundary_scores_complete_terminal_without_passing(tmp_path, monkeypatch, signal, joint):
    FakeEnv.stop_step, FakeEnv.stop_signal, FakeEnv.stop_joint = 100, signal, joint
    output, metadata, *_ = run(tmp_path, monkeypatch)
    ep = saved(output, "episodes.json")[0]
    ev = saved(output, "seed_results.json")[0]["evaluations"][runner.MODEL_NAME]
    assert ep["status"] == "terminated" and not ep["completed"]
    assert ep["control_steps"] == 101 and ep["physics_steps"] == 1010
    assert ev["metric_control_step_count"] == 1 and ev["study_abort"] is not None
    assert metadata["model_updates"] == 800 and not metadata["all_trials_successful"]


def test_partial_B_terminal_excluded_from_complete_scores(tmp_path, monkeypatch):
    FakeEnv.stop_step, FakeEnv.partial = 100, True
    output, metadata, *_ = run(tmp_path, monkeypatch)
    ep = saved(output, "episodes.json")[0]
    ev = saved(output, "seed_results.json")[0]["evaluations"][runner.MODEL_NAME]
    assert ep["physics_steps"] == 1003 and ep["control_calls_attempted"] == 101
    assert ev["metric_control_step_count"] == 0 and len(ev["partial_interval_target_errors_rad"]) == 1
    assert ev["tracking_rmse"] is None and ev["actual_control_effort_substeps"] == 3
    assert metadata["model_updates"] == 800


def test_paid_unreturned_is_unknown_actual_effort_not_zero(tmp_path, monkeypatch):
    FakeEnv.fail_step = 100
    output, metadata, *_ = run(tmp_path, monkeypatch)
    ep = saved(output, "episodes.json")[0]
    ev = saved(output, "seed_results.json")[0]["evaluations"][runner.MODEL_NAME]
    assert (ep["control_calls_attempted"], ep["control_steps"], ep["physics_steps"]) == (101, 100, 1003)
    assert ep["unreturned_physics_steps"] == 3 and not ep["risk_telemetry_complete"]
    assert not ev["actual_effort_complete"] and ev["actual_effort_is_lower_bound"]
    assert ev["missing_control_effort_substeps"] == 3 and ev["metric_control_step_count"] == 0
    assert ev["control_effort"]["requested_absolute_nm_s"] == pytest.approx([.00075, .00075])
    assert metadata["model_updates"] == 800


def test_missing_actual_history_retains_paid_and_returned_count(tmp_path, monkeypatch):
    FakeEnv.missing_history = True
    output, metadata, *_ = run(tmp_path, monkeypatch)
    ep = saved(output, "episodes.json")[0]
    ev = saved(output, "seed_results.json")[0]["evaluations"][runner.MODEL_NAME]
    assert ep["control_steps"] == ep["returned_steps"] == 101 and ep["written_returned_steps"] == 100
    assert ep["returned_unwritten_steps"] == 1 and ev["missing_control_effort_substeps"] == 10
    assert not ev["actual_effort_complete"] and metadata["physics_steps"] == 1010


def test_ordinary_control_exception_continues_other_seeds_once(tmp_path, monkeypatch):
    FakeEnv.fail_step = 100
    output, metadata, *_ = run(tmp_path, monkeypatch, seeds=(0, 1, 2))
    episodes = saved(output, "episodes.json")
    assert [e["status"] for e in episodes] == ["exception", "completed", "completed"]
    assert (metadata["control_calls_attempted"], metadata["control_steps"], metadata["physics_steps"]) == (701, 700, 7003)
    assert metadata["model_updates"] == 2400 and len(FakeEnv.instances) == 3


def test_unknown_planner_failure_retains_lower_bound_without_step(tmp_path, monkeypatch):
    def fail(self, *args, **kwargs):
        raise RuntimeError("artificial unknown planner failure")
    monkeypatch.setattr(FakePlanner, "select", fail)
    output, metadata, *_ = run(tmp_path, monkeypatch)
    ev = saved(output, "seed_results.json")[0]["evaluations"][runner.MODEL_NAME]
    assert metadata["control_steps"] == 100 and metadata["physics_steps"] == 1000
    assert ev["planner_attempt_count"] == ev["failed_planner_attempts"] == 1
    assert ev["planning_accounting"]["scalar_counts_is_lower_bound"]
    assert not ev["planning_accounting"]["scalar_counts_complete"]
    assert ev["planning_accounting"]["unknown_failed_planner_calls"] == 1


def test_attached_planner_failure_retains_precise_cost(tmp_path, monkeypatch):
    def fail(self, *args, **kwargs):
        exc = RuntimeError("artificial attached planner failure")
        exc.pair_planning_accounting = {"pair_prediction_attempts": 4, "pair_prediction_successes": 3,
            "scalar_prediction_attempts": 8, "scalar_prediction_successes": 7,
            "failed_pair_prediction_attempts": 1, "unknown_scalar_failure_count": 0}
        raise exc
    monkeypatch.setattr(FakePlanner, "select", fail)
    output, metadata, *_ = run(tmp_path, monkeypatch)
    cost = saved(output, "seed_results.json")[0]["evaluations"][runner.MODEL_NAME]["planning_accounting"]
    assert cost["pair_prediction_attempts"] == 4 and cost["scalar_prediction_successes"] == 7
    assert cost["scalar_counts_complete"] and not cost["scalar_counts_is_lower_bound"]
    assert metadata["control_calls_attempted"] == 100


def test_prediction_head_failure_once_retains_partial_math_cost_no_fit(tmp_path, monkeypatch):
    _, bound = artificial(tmp_path)
    source, result = bound.seed(0), {}
    model = runner.replay_calibration(source, io.StringIO(), result)
    original = model._predict_output
    once = False
    def fail(index, *args):
        nonlocal once
        if index == 1 and not once:
            once = True
            COST["scalar_prediction_attempts"] += 1
            raise ValueError("one artificial second velocity-head failure")
        return original(index, *args)
    monkeypatch.setattr(model, "_predict_output", fail)
    runner.replay_prediction(source, model, io.StringIO(), result)
    pred = result["prediction_replay"]
    assert pred["status"] == "exception" and pred["metric_complete_endpoints"] == 0
    assert pred["prediction_accounting"]["pair_prediction_attempts"] == 1
    assert pred["prediction_accounting"]["scalar_prediction_attempts"] == 2
    assert pred["prediction_accounting"]["scalar_prediction_successes"] == 1
    assert model.update_count == 400 and pred["model_fingerprint_before"] == pred["model_fingerprint_after"]
    episode = {"trial_id": "seed0_coupled_guard", "phase_budgets": {
        phase: {"control_calls_attempted": 0, "control_steps": 0, "physics_steps": 0} for phase in runner.PHASES}}
    result["evaluations"] = {}
    runner.run_fresh_control(source, model, episode, io.StringIO(), result)
    assert episode["completed"] and model.update_count == 400


@pytest.mark.parametrize("changed", ["qref", "range", "plant"])
def test_fresh_binding_mismatch_fails_without_repair(tmp_path, monkeypatch, changed):
    if changed == "qref":
        FakeEnv.qref_delta = 1e-12
    elif changed == "range":
        FakeEnv.range_delta = 1e-12
    else:
        FakeEnv.plant_delta = True
    output, metadata, *_ = run(tmp_path, monkeypatch)
    ep = saved(output, "episodes.json")[0]
    assert ep["status"] == "exception"
    assert ep["control_steps"] == (0 if changed == "plant" else 100)
    assert saved(output, "seed_results.json")[0]["evaluations"][runner.MODEL_NAME]["planner_attempt_count"] == 0
    assert metadata["model_updates"] == 800


def test_prefix_only_uses_original_environment_protection(tmp_path, monkeypatch):
    FakeEnv.prefix_excursion = True
    output, metadata, *_ = run(tmp_path, monkeypatch)
    assert metadata["completed_trials"] == 1
    first = rows(output, "trace.jsonl.gz")[0]
    assert first["observation_after"]["joint_velocity"][1] == 1. and first["study_abort"] is None


def test_atomic_second_head_failure_preserves_prior_zero_commit(tmp_path, monkeypatch):
    original = core.PairBodyModel._propose_update
    def fail_second(self, index, *args):
        if index == 1:
            raise ValueError("artificial second-head proposal failure")
        return original(self, index, *args)
    monkeypatch.setattr(core.PairBodyModel, "_propose_update", fail_second)
    output, metadata, *_ = run(tmp_path, monkeypatch)
    replay = saved(output, "seed_results.json")[0]["calibration_replay"]
    assert metadata["model_updates"] == metadata["physics_steps"] == 0
    assert replay["attempted_vector_updates"] == 1 and replay["committed_scalar_updates"] == 0
    assert replay["model_snapshot"]["coefficients"] == replay["initial_model"]["coefficients"]
    assert replay["failure_accounting"]["structured_failure"]["committed_scalar_updates"] == 0
    assert replay["rls_prediction_accounting"]["scalar_prediction_successes"] == 2


@pytest.mark.parametrize("side", ["before", "after"])
def test_interrupt_publish_boundary_retains_actual_atomic_cost(tmp_path, monkeypatch, side):
    fixture, bound = artificial(tmp_path)
    source = bound.seed(0)
    result, out = {}, io.StringIO()
    if side == "before":
        original = core._parameter_state
        def interrupt_state(theta, covariance, count):
            if count == 1:
                raise KeyboardInterrupt("before atomic publish")
            return original(theta, covariance, count)
        monkeypatch.setattr(core, "_parameter_state", interrupt_state)
    else:
        original = core.PairBodyModel.update
        def interrupt_update(self, *args, **kwargs):
            original(self, *args, **kwargs)
            raise KeyboardInterrupt("after atomic publish")
        monkeypatch.setattr(core.PairBodyModel, "update", interrupt_update)
    with pytest.raises(KeyboardInterrupt):
        runner.replay_calibration(source, out, result)
    replay = result["calibration_replay"]
    assert replay["committed_vector_updates"] == (0 if side == "before" else 1)
    assert replay["committed_scalar_updates"] == (0 if side == "before" else 2)
    assert replay["rls_prediction_accounting"]["pair_prediction_attempts"] == 1
    assert replay["status"] == "exception" and not FakeEnv.instances


def test_calibration_trace_failure_preserves_commit_and_blocks_rest(tmp_path, monkeypatch):
    fixture, bound = artificial(tmp_path)
    original = runner._emit
    failed = False
    def once(writer, row):
        nonlocal failed
        if row.get("phase") == "offline_calibration_replay" and not failed:
            failed = True
            raise OSError("artificial write failure after first successful commit")
        return original(writer, row)
    monkeypatch.setattr(runner, "_emit", once)
    output = tmp_path / "failed_b"
    with pytest.raises(OSError):
        runner.run_guard_coupled_development(output, protocol_path=tmp_path / "protocol",
            synthetic=True, synthetic_source_bytes={runner.PROTOCOL_PATH: b"fixture"}, binding=bound)
    metadata = saved(output, "metadata.json")
    assert metadata["model_updates"] == 2 and metadata["physics_steps"] == 0
    assert metadata["blocked_trials"] == 3 and metadata["archive_status"] == "failed"
    assert saved(output, "seed_results.json")[0]["calibration_replay"]["committed_scalar_updates"] == 2


def test_control_trace_failure_preserves_returned_effort_and_blocks_rest(tmp_path, monkeypatch):
    fixture, bound = artificial(tmp_path)
    original = runner._emit
    failed = False
    def once(writer, row):
        nonlocal failed
        if row.get("phase") == "control" and "collector_exception" not in row and not failed:
            failed = True
            raise OSError("artificial control trace failure after return")
        return original(writer, row)
    monkeypatch.setattr(runner, "_emit", once)
    output = tmp_path / "failed_b"
    with pytest.raises(OSError):
        runner.run_guard_coupled_development(output, protocol_path=tmp_path / "protocol",
            synthetic=True, synthetic_source_bytes={runner.PROTOCOL_PATH: b"fixture"}, binding=bound)
    metadata = saved(output, "metadata.json")
    ep = saved(output, "episodes.json")[0]
    assert (metadata["control_steps"], metadata["physics_steps"], metadata["model_updates"]) == (101, 1010, 800)
    assert ep["returned_unwritten_steps"] == 1 and ep["unreturned_physics_steps"] == 0
    assert metadata["blocked_trials"] == 2


def test_original_fixed_MPC_settings_and_measured_counts(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "FixedPairMPC", core.FixedPairMPC)
    monkeypatch.setattr(runner, "CONTROL_STEPS", 1)
    before = dict(COST)
    output, metadata, *_ = run(tmp_path, monkeypatch)
    ev = saved(output, "seed_results.json")[0]["evaluations"][runner.MODEL_NAME]
    spec = ev["planner_spec"]
    assert spec["config_per_axis"]["horizon"] == 15 and spec["vector_candidate_count"] == 81
    assert spec["tie_break"] == "exact cost, sum(abs(u)), signed u0, signed u1"
    cost = ev["planning_accounting"]
    assert 81 <= cost["pair_prediction_attempts"] <= 1215
    assert cost["scalar_prediction_attempts"] == 2*cost["pair_prediction_attempts"]
    assert COST["pair_prediction_attempts"]-before["pair_prediction_attempts"] == 400+100+1+cost["pair_prediction_attempts"]
    assert metadata["physics_steps"] == 1010 and metadata["model_updates"] == 800


def test_runner_imports_exact_core_not_synthetic_fallbacks():
    text = inspect.getsource(runner)
    assert "from developmental_physics.guard_coupled_pair_model import GuardCoupledPairBodyModel" in text
    assert "InputMappedDiagonalPairBodyModel(" not in text and "DiagonalPairBodyModel(" not in text
    assert "if not synthetic and not FORMAL_EXECUTION_FROZEN:" in text
    assert "update_shared_models(" not in text
    assert "load_a_source_binding(" in text
