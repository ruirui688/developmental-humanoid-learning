"""All observations/labels are synthetic; never step MuJoCo."""
import dis
import gzip
import importlib.util
import inspect
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
import pytest

pytest.importorskip("mujoco")
from developmental_physics import local_pair_model as core

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file())
source = ROOT/"src/developmental_physics/guard_pair_development.py"
if not source.is_file():
    source = Path(__file__).with_name("guard_pair_development.py")
    helper_source = Path(__file__).with_name("pd_binding.py")
    helper_spec = importlib.util.spec_from_file_location("developmental_physics.pd_selection_binding", helper_source)
    helper = importlib.util.module_from_spec(helper_spec)
    sys.modules[helper_spec.name] = helper
    helper_spec.loader.exec_module(helper)
spec = importlib.util.spec_from_file_location("c4_guard_runner", source)
runner = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = runner
spec.loader.exec_module(runner)
PROTOCOL = ROOT / runner.PROTOCOL_PATH
PD_FIXTURE = {"status": "selected", "selected_id": "synthetic-only-selected", "kp": [8., 8.], "kd": [2., 2.]}
SOURCE_FIXTURE = {runner.PROTOCOL_PATH: b"synthetic explicit protocol", runner.SOURCE_PATH: source.read_bytes()}


class SyntheticEnv:
    instances = []
    stop_step = fail_step = None
    stop_joint = 1
    stop_signal = "v"
    partial = missing_history = prefix_excursion = False
    failure_type = RuntimeError
    fault_trial = 0

    def __init__(self, config):
        self.config = config
        self.trial = len(self.instances)
        self.instances.append(self)
        self.joint_names = [str(i) for i in range(8)]
        self.ranges = np.deg2rad(np.asarray([[-100., 100.], [0., 135.], [-100., 100.], [0., 135.],
                                            [-90., 90.], [0., 135.], [-90., 90.], [0., 135.]]))
        self.model = SimpleNamespace(joint=lambda name: SimpleNamespace(range=self.ranges[int(name)]))
        self.data = SimpleNamespace(qpos=np.zeros(15), qvel=np.zeros(14))
        self.data.qpos[3] = 1.
        self.step_id = self.physics_steps = 0
        self.terminated = False
        self.reason = None
        self.q, self.v, self.command = np.zeros(8), np.zeros(8), np.zeros(8)
        self.q[1] = -.0005
        self.commands = []

    def reset(self, seed, pose):
        assert pose == "supine"
        assert seed in {int(np.random.SeedSequence(s).spawn(2)[0].generate_state(1)[0]) for s in (0, 1, 2)}
        return self.observation()

    def observation(self):
        self.data.qpos[7:] = self.q
        self.data.qvel[6:] = self.v
        return {"joint_position": self.q.copy(), "joint_velocity": self.v.copy(),
                "imu_gyro": np.zeros(3), "imu_acceleration": np.zeros(3),
                "actuator_torque": self.command.copy(), "previous_command": self.command.copy()}

    def parameter_fingerprint(self):
        return "synthetic fixed body"

    def diagnostics(self):
        return {"step_id": self.step_id, "physics_steps": self.physics_steps,
                "time": .002*self.physics_steps, "terminated": self.terminated, "reason": self.reason}

    def step(self, requested):
        index = self.step_id
        if self.trial == self.fault_trial and index == self.fail_step:
            self.physics_steps += 3
            raise self.failure_type("synthetic three paid substeps, no return")
        self.command = requested.copy()
        self.commands.append(requested.copy())
        n = 3 if self.trial == self.fault_trial and index == self.stop_step and self.partial else 10
        self.v = .5*self.v + .02*requested
        self.q += n*.002*self.v
        if self.prefix_excursion and index == 0:
            self.v[1] = 1.
        elif self.prefix_excursion and index == 1:
            self.q[:] = self.v[:] = 0.
            self.q[1] = -.0005
        if self.trial == self.fault_trial and index == self.stop_step:
            if self.stop_signal == "v":
                self.v[self.stop_joint] = 1.
            elif self.stop_signal == "q":
                self.q[self.stop_joint] = (.0 if self.stop_joint == 0 else -.0005)+.12
            if self.partial:
                self.terminated = True
                self.reason = {"type": "SyntheticEnvironmentStop", "message": "three-substep terminal"}
        self.step_id += 1
        self.physics_steps += n
        diagnostic = {**self.diagnostics(), "executed_substeps": n,
            "applied_torque_history": [requested.tolist()]*n, "requested_torque": requested,
            "accepted_torque": requested, "applied_torque": requested, "guarded_substeps": 0,
            "substep_ground_normal_forces": [1.]*n, "substep_kinetic_energies": [.2]*n,
            "substep_minimum_contact_distances": [-.0001]*n, "peak_substep_ground_normal_force": 1.,
            "ground_normal_impulse_ns": .002*n, "peak_substep_kinetic_energy": .2,
            "minimum_substep_contact_distance": -.0001}
        if self.trial == self.fault_trial and index == runner.PREFIX_STEPS and self.missing_history:
            diagnostic.pop("applied_torque_history")
        return SimpleNamespace(observation=self.observation(), diagnostics=diagnostic,
                               terminated=self.terminated, reason=self.reason)


class SyntheticPlanner:
    def __init__(self, model, limits):
        self.model, self.limits = model, limits

    def spec(self):
        return {"synthetic_planner": True, "config_per_axis": {"horizon": 15}, "vector_candidate_count": 81}

    def select(self, q, v, target, previous_torque):
        return SimpleNamespace(torque=(.125, .125), fallback=False, to_dict=lambda: {
            "torque": [.125, .125], "pair_prediction_attempts": 1, "pair_prediction_successes": 1,
            "scalar_prediction_attempts": 2, "scalar_prediction_successes": 2,
            "failed_pair_prediction_attempts": 0, "unknown_scalar_failure_count": 0,
            "scalar_counts_complete": True, "scalar_counts_is_lower_bound": False})


@pytest.fixture(autouse=True)
def synthetic_only(monkeypatch):
    SyntheticEnv.instances = []
    SyntheticEnv.stop_step = SyntheticEnv.fail_step = None
    SyntheticEnv.stop_joint, SyntheticEnv.stop_signal = 1, "v"
    SyntheticEnv.partial = SyntheticEnv.missing_history = SyntheticEnv.prefix_excursion = False
    SyntheticEnv.failure_type = RuntimeError
    SyntheticEnv.fault_trial = 0
    def forbid_git(*args, **kwargs):
        raise AssertionError("synthetic tests may not query real Git")
    monkeypatch.setattr(runner.subprocess, "check_output", forbid_git)
    monkeypatch.setattr(runner, "GroundBodyEnv", SyntheticEnv)
    monkeypatch.setattr(runner, "FixedPairMPC", SyntheticPlanner)
    monkeypatch.setattr(runner, "DEVELOPMENT_SEEDS", (0,))


def small_recipe(monkeypatch):
    for name in ("PREFIX_STEPS", "CALIBRATION_STEPS", "PREDICTION_STEPS", "CONTROL_STEPS"):
        monkeypatch.setattr(runner, name, 2)


def run(output):
    return runner.run_guard_pair_development(output, protocol_path=PROTOCOL, synthetic=True,
        synthetic_source_bytes=SOURCE_FIXTURE, synthetic_pd_binding=PD_FIXTURE)


def read(output, name):
    return json.loads((output / name).read_text(encoding="utf-8"))


def rows(output):
    with gzip.open(output / "trace.jsonl.gz", "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream]


def test_unfrozen_real_physics_disabled_even_with_mock_environment(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "FORMAL_EXECUTION_FROZEN", False)
    with pytest.raises(RuntimeError, match="disabled"):
        runner.run_guard_pair_development(tmp_path / "forbidden", protocol_path=PROTOCOL)
    assert not (tmp_path / "forbidden").exists()


def test_synthetic_flag_cannot_enter_real_environment(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "GroundBodyEnv", runner._REAL_ENV)
    with pytest.raises(RuntimeError, match="replaced"):
        runner.run_guard_pair_development(tmp_path / "forbidden", protocol_path=PROTOCOL, synthetic=True)


def test_full_plan_2500_calls_and_1600_committed_scalar_labels_per_seed(tmp_path):
    result = run(tmp_path / "out")
    assert result["complete"] and result["all_trials_successful"]
    assert result["control_steps"] == 2500 and result["physics_steps"] == 25000
    assert result["model_updates"] == 1600 and result["vector_model_updates"] == 800
    seed = read(tmp_path / "out", "seed_results.json")[0]
    assert seed["reference_q"] == [0., -.0005]
    assert seed["calibration_completed"]
    for name in ("learned_raw", "learned_guard"):
        assert seed["learned_models"][name]["scalar_update_count"] == 800
        assert seed["learned_models"][name]["trainable"] is False
        assert seed["learned_models"][name]["output_update_counts"] == [400, 400]
    for kind in runner.KINDS[1:]:
        ev = seed["evaluations"][kind]
        assert ev["models_before"] == ev["models_after"]
        assert ev["phase_actual_effort_complete"]["prefix"]
    trace = rows(tmp_path / "out")
    assert len(trace) == 2500
    assert all(len(r["requested_torque"]) == 8 and r["requested_torque"][2:] == [0.]*6 for r in trace)
    assert all(len(r["observation_after"]["joint_position"]) == 8 for r in trace)
    cal = [r for r in trace if r["phase"] == "calibration"]
    assert all(r["model_update"]["learned_raw"]["shared_transition_id"] == r["model_update"]["learned_guard"]["shared_transition_id"] == r["shared_transition_id"] for r in cal)
    absolute = np.sum(np.abs([r["requested_torque"][:2] for r in cal]), axis=0)*.02
    squared = np.sum(np.square([r["requested_torque"][:2] for r in cal]), axis=0)*.02
    assert absolute == pytest.approx([.18, .18]) and squared == pytest.approx([.06375, .06375])
    final_control = next(r for r in trace if r["kind"] == "PDselected" and r["step_index"] == 200)
    assert final_control["target_q"] == [.08, .0795]


def test_fixed_multidose_schedule_independent_of_physical_observations():
    assert list(inspect.signature(runner.calibration_request).parameters) == ["active", "directions"]
    commands = np.asarray([runner.calibration_request(k, (1, -1)) for k in range(400)])
    assert np.all(commands[:100, 1] == 0.) and np.all(commands[100:200, 0] == 0.)
    assert np.array_equal(commands[200:300, 0], -commands[200:300, 1])
    assert np.array_equal(commands[300:400, 0], commands[300:400, 1])
    assert np.sum(commands, axis=0) == pytest.approx([0., 0.])
    assert all(np.count_nonzero(commands[k:k+20], axis=0).max() == 2 for k in range(0, 400, 20))
    assert runner.calibration_request(5, (1, 1)) == (0., 0.)
    assert runner.calibration_request(10, (1, 1)) == (-.125, 0.)
    assert runner.prediction_request(5, (1, 1)) == (0., 0.)
    with pytest.raises(ValueError):
        runner.calibration_request(400, (1, 1))


def test_full_three_seed_plan_has_7500_calls_75000_substeps_4800_scalar_updates(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "DEVELOPMENT_SEEDS", (0, 1, 2))
    output = tmp_path / "out"
    meta = run(output)
    assert meta["planned_episode_count"] == 24 and meta["maximum_control_steps"] == 7500
    assert meta["control_steps"] == 7500 and meta["physics_steps"] == 75000
    assert meta["model_updates"] == 4800 and meta["vector_model_updates"] == 2400
    assert meta["completed_trials"] == 24 and meta["all_trials_successful"]
    episodes = read(output, "episodes.json")
    sums = {phase: {key: sum(e["phase_budgets"][phase][key] for e in episodes)
                   for key in ("control_steps", "physics_steps")} for phase in runner.PHASES}
    assert sums == {"prefix": {"control_steps": 2400, "physics_steps": 24000},
                    "calibration": {"control_steps": 1200, "physics_steps": 12000},
                    "prediction": {"control_steps": 300, "physics_steps": 3000},
                    "control": {"control_steps": 3600, "physics_steps": 36000}}


def test_real_pair_mpc_math_on_synthetic_encoders_short_control_archive(tmp_path, monkeypatch):
    # Only the mathematical planner is real; GroundBodyEnv remains SyntheticEnv.
    # Full 400-label calibration and 100-step predictions, reduced two-step
    # controls are explicit fixture costs, never a formal 200-step evaluation.
    monkeypatch.setattr(runner, "FixedPairMPC", core.FixedPairMPC)
    monkeypatch.setattr(runner, "CONTROL_STEPS", 2)
    SyntheticEnv.fault_trial, SyntheticEnv.stop_step = 2, 100
    output = tmp_path / "out"
    meta = run(output)
    seed = read(output, "seed_results.json")[0]
    assert meta["synthetic"] and meta["backend"] == "synthetic, no physics"
    assert meta["model_updates"] == 1600 and seed["calibration_completed"]
    nominal = seed["evaluations"]["nominal_raw"]
    assert nominal["study_abort"] is not None and nominal["metric_control_step_count"] == 1
    assert nominal["planner_spec"]["vector_candidate_count"] == 81
    assert nominal["planning_accounting"]["pair_prediction_attempts"] > 0
    assert nominal["planning_accounting"]["scalar_prediction_attempts"] == 2*nominal["planning_accounting"]["pair_prediction_attempts"]
    assert nominal["planning_accounting"]["scalar_counts_complete"]


@pytest.mark.parametrize("joint", [0, 1])
def test_either_axis_stop_at_equal_threshold_keeps_env_flag_false_and_blocks_only_dependents(tmp_path, monkeypatch, joint):
    small_recipe(monkeypatch)
    SyntheticEnv.stop_step, SyntheticEnv.stop_joint = 2, joint
    output = tmp_path / "out"
    result = run(output)
    episodes = read(output, "episodes.json")
    assert episodes[0]["status"] == "terminated" and episodes[0]["environment_terminated"] is False
    assert episodes[0]["study_abort"]["triggers"][0]["joint_index"] == joint
    assert result["model_updates"] == 4
    assert [e["kind"] for e in episodes if e["status"] == "blocked"] == ["prediction", "learned_raw", "learned_guard"]
    assert all(next(e for e in episodes if e["kind"] == kind)["completed"] for kind in ("nominal_raw", "nominal_guard", "PDselected", "zero"))


def test_prefix_excursion_uses_no_added_study_abort(tmp_path, monkeypatch):
    small_recipe(monkeypatch)
    SyntheticEnv.prefix_excursion = True
    result = run(tmp_path / "out")
    assert result["all_trials_successful"]


def test_last_planned_calibration_stop_is_not_complete(tmp_path, monkeypatch):
    small_recipe(monkeypatch)
    SyntheticEnv.stop_step = 3
    result = run(tmp_path / "out")
    seed = read(tmp_path / "out", "seed_results.json")[0]
    assert not seed["calibration_completed"]
    assert result["model_updates"] == 8
    assert result["blocked_trials"] == 3


def test_partial_terminal_keeps_both_stop_flags_no_update_and_no_prediction_score(tmp_path, monkeypatch):
    small_recipe(monkeypatch)
    SyntheticEnv.stop_step = 2
    SyntheticEnv.partial = True
    output = tmp_path / "out"
    result = run(output)
    episode = read(output, "episodes.json")[0]
    assert episode["environment_terminated"] is True and episode["study_abort"] is not None
    assert episode["reason"]["type"] == "SyntheticEnvironmentStop"
    assert episode["physics_steps"] == 23 and result["model_updates"] == 0
    ev = read(output, "seed_results.json")[0]["evaluations"]["calibration"]
    assert not ev["velocity_prediction_rmse"]


def test_partial_control_retains_known_target_error_but_no_complete_tracking_score(tmp_path, monkeypatch):
    small_recipe(monkeypatch)
    SyntheticEnv.fault_trial = 2
    SyntheticEnv.stop_step = 2
    SyntheticEnv.partial = True
    output = tmp_path / "out"
    run(output)
    ev = read(output, "seed_results.json")[0]["evaluations"]["nominal_raw"]
    assert ev["metric_control_step_count"] == 0 and ev["tracking_rmse"] is None
    assert len(ev["partial_interval_target_errors_rad"]) == 1
    partial = ev["partial_interval_target_errors_rad"][0]
    assert partial["target_q"] == [0.04, 0.0395]
    assert len(partial["errors_rad"]) == 2 and partial["executed_substeps"] == 3
    assert not ev["completed"] and ev["study_abort"] is not None


def test_calibration_prefix_failure_still_allows_independent_paid_baseline_prefix(tmp_path, monkeypatch):
    small_recipe(monkeypatch)
    SyntheticEnv.fail_step = 0
    output = tmp_path / "out"
    meta = run(output)
    seed = read(output, "seed_results.json")[0]
    assert meta["model_updates"] == 0 and seed["calibration_models"] == {}
    assert seed["reference_q"] == [0., -.0005]
    for kind in ("nominal_raw", "nominal_guard", "PDselected", "zero"):
        assert seed["evaluations"][kind]["completed"]


def test_partial_without_a_stop_latch_cannot_publish_complete_calibration(tmp_path, monkeypatch):
    small_recipe(monkeypatch)
    SyntheticEnv.stop_step, SyntheticEnv.stop_signal, SyntheticEnv.partial = 2, "none", True
    original = SyntheticEnv.step
    def missing_latch(self, request):
        returned = original(self, request)
        if self.trial == 0:
            self.terminated = returned.terminated = False
            self.reason = returned.reason = None
        return returned
    monkeypatch.setattr(SyntheticEnv, "step", missing_latch)
    output = tmp_path / "out"
    meta = run(output)
    seed = read(output, "seed_results.json")[0]
    assert not seed["calibration_completed"] and seed["learned_models"] == {}
    assert seed["evaluations"]["calibration"]["status"] == "incomplete"
    assert meta["model_updates"] == 4 and meta["blocked_trials"] == 3


@pytest.mark.parametrize("fatal", [False, True])
def test_paid_unreturned_substeps_are_not_free_or_zero_actual_effort(tmp_path, monkeypatch, fatal):
    small_recipe(monkeypatch)
    SyntheticEnv.fail_step = 2
    SyntheticEnv.failure_type = OSError if fatal else RuntimeError
    output = tmp_path / "out"
    if fatal:
        with pytest.raises(OSError):
            run(output)
    else:
        run(output)
    meta, episodes = read(output, "metadata.json"), read(output, "episodes.json")
    assert episodes[0]["control_calls_attempted"] == 3 and episodes[0]["physics_steps"] == 23
    assert episodes[0]["unreturned_physics_steps"] == 3
    ev = read(output, "seed_results.json")[0]["evaluations"]["calibration"]
    assert ev["phase_missing_actual_effort_substeps"]["calibration"] == 3
    assert ev["phase_actual_effort_complete"]["calibration"] is False
    if fatal:
        assert meta["blocked_trials"] == 7 and not meta["complete"]
    else:
        assert meta["blocked_trials"] == 3 and meta["complete"]


def test_missing_native_actual_history_blocks_update_and_keeps_paid_cost_unknown(tmp_path, monkeypatch):
    small_recipe(monkeypatch)
    SyntheticEnv.missing_history = True
    output = tmp_path / "out"
    meta = run(output)
    ev = read(output, "seed_results.json")[0]["evaluations"]["calibration"]
    assert meta["model_updates"] == 0
    assert ev["phase_missing_actual_effort_substeps"]["calibration"] == 10
    assert ev["phase_actual_effort_complete"]["calibration"] is False
    assert read(output, "episodes.json")[0]["returned_unwritten_steps"] == 1


@pytest.mark.parametrize("fatal", [False, True])
def test_failed_second_model_retains_first_model_real_commits(tmp_path, monkeypatch, fatal):
    small_recipe(monkeypatch)
    original_proposal = core.PairBodyModel._propose_update
    def fail(self, *args, **kwargs):
        if self.input_basis == "known_angle_guard":
            raise OSError("synthetic guard failure") if fatal else ValueError("synthetic guard failure")
        return original_proposal(self, *args, **kwargs)
    monkeypatch.setattr(core.PairBodyModel, "_propose_update", fail)
    output = tmp_path / "out"
    if fatal:
        with pytest.raises(OSError):
            run(output)
    else:
        run(output)
    meta, seed = read(output, "metadata.json"), read(output, "seed_results.json")[0]
    assert meta["model_updates"] == 2 and meta["vector_model_updates"] == 1
    assert seed["calibration_models"]["learned_raw"]["scalar_update_count"] == 2
    assert seed["calibration_models"]["learned_guard"]["scalar_update_count"] == 0
    assert seed["learned_models"] == {}
    failure = read(output, "episodes.json")[0]["failure_accounting"]
    ledger = failure["shared_pair_update_accounting"] if fatal else failure["structured_failure"]
    assert ledger["snapshots_after_attempt"]["learned_raw"]["scalar_update_count"] == 2
    assert ledger["snapshots_after_attempt"]["learned_guard"]["scalar_update_count"] == 0


def test_failed_calibration_model_cannot_poison_independent_baseline_predictions(tmp_path, monkeypatch):
    small_recipe(monkeypatch)
    original = runner.InputMappedDiagonalPairBodyModel.predict
    def poison_after_commit(self, *args):
        if self.scalar_update_count:
            raise ValueError("failed partial model must never predict in baselines")
        return original(self, *args)
    original_proposal = core.PairBodyModel._propose_update
    def fail(self, *args, **kwargs):
        if self.input_basis == "known_angle_guard":
            raise ValueError("synthetic later guard model failure")
        return original_proposal(self, *args, **kwargs)
    monkeypatch.setattr(runner.InputMappedDiagonalPairBodyModel, "predict", poison_after_commit)
    monkeypatch.setattr(core.PairBodyModel, "_propose_update", fail)
    output = tmp_path / "out"
    meta = run(output)
    seed = read(output, "seed_results.json")[0]
    assert meta["model_updates"] == 2
    assert seed["calibration_models"]["learned_raw"]["scalar_update_count"] == 2
    assert seed["learned_models"] == {}
    for kind in ("nominal_raw", "nominal_guard", "PDselected", "zero"):
        assert seed["evaluations"][kind]["completed"]
        assert set(seed["evaluations"][kind]["models_after"]) == {"nominal_raw", "nominal_guard"}


@pytest.mark.parametrize("after_commit", [False, True])
def test_interrupt_adjacent_to_single_state_commit_reports_actual_scalar_count(tmp_path, monkeypatch, after_commit):
    small_recipe(monkeypatch)
    codes = core.PairBodyModel.update.__code__
    commit_offset = next(i.offset for i in dis.get_instructions(codes) if i.opname == "STORE_ATTR" and i.argval == "_state")
    def tracer(frame, event, arg):
        if frame.f_code is codes:
            frame.f_trace_opcodes = True
            if event == "opcode" and (frame.f_lasti > commit_offset if after_commit else frame.f_lasti == commit_offset):
                sys.settrace(None)
                raise KeyboardInterrupt("synthetic exact commit boundary")
        return tracer
    output = tmp_path / "out"
    sys.settrace(tracer)
    try:
        with pytest.raises(KeyboardInterrupt):
            run(output)
    finally:
        sys.settrace(None)
    meta, seed = read(output, "metadata.json"), read(output, "seed_results.json")[0]
    expected = 2 if after_commit else 0
    assert meta["model_updates"] == expected
    assert seed["calibration_models"]["learned_raw"]["scalar_update_count"] == expected
    assert seed["calibration_models"]["learned_guard"]["scalar_update_count"] == 0
    assert seed["learned_models"] == {}
    assert meta["blocked_trials"] == 7


def test_trace_write_failure_is_fatal_after_real_model_commits(tmp_path, monkeypatch):
    small_recipe(monkeypatch)
    original = runner.gzip.open
    class FailWriter:
        def __init__(self, *args, **kwargs):
            self.inner = original(*args, **kwargs)
            self.did_fail = False
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return self.inner.__exit__(*args)
        def write(self, value):
            row = json.loads(value)
            if row.get("phase") == "calibration" and "collector_exception" not in row and not self.did_fail:
                self.did_fail = True
                raise ValueError("synthetic trace sink failure")
            return self.inner.write(value)
    monkeypatch.setattr(runner.gzip, "open", FailWriter)
    output = tmp_path / "out"
    with pytest.raises(ValueError, match="trace sink"):
        run(output)
    meta, episode = read(output, "metadata.json"), read(output, "episodes.json")[0]
    assert meta["model_updates"] == 4 and meta["blocked_trials"] == 7
    assert episode["trace_write_failure"]["type"] == "ValueError"
    assert episode["returned_unwritten_steps"] == 1


def test_failed_planner_attempt_has_exact_attached_mathematical_cost(tmp_path, monkeypatch):
    small_recipe(monkeypatch)
    def fail(*args, **kwargs):
        error = OSError("synthetic planner IO")
        error.pair_planning_accounting = {"pair_prediction_attempts": 5, "pair_prediction_successes": 4,
            "scalar_prediction_attempts": 9, "scalar_prediction_successes": 8,
            "failed_pair_prediction_attempts": 1, "unknown_scalar_failure_count": 0}
        raise error
    monkeypatch.setattr(SyntheticPlanner, "select", fail)
    output = tmp_path / "out"
    with pytest.raises(OSError):
        run(output)
    ev = read(output, "seed_results.json")[0]["evaluations"]["nominal_raw"]
    assert ev["failed_planner_attempts"] == 1
    assert ev["planning_accounting"]["pair_prediction_attempts"] == 5
    assert ev["planning_accounting"]["scalar_prediction_attempts"] == 9
    assert ev["planning_accounting"]["scalar_counts_complete"]


def test_failed_planner_without_ledger_marks_unknown_lower_bound(tmp_path, monkeypatch):
    small_recipe(monkeypatch)
    def fail(*args, **kwargs):
        raise ValueError("synthetic uninstrumented planner")
    monkeypatch.setattr(SyntheticPlanner, "select", fail)
    output = tmp_path / "out"
    run(output)
    ev = read(output, "seed_results.json")[0]["evaluations"]["nominal_raw"]
    assert ev["planning_accounting"]["unknown_failed_planner_calls"] == 1
    assert ev["planning_accounting"]["scalar_counts_is_lower_bound"]
    assert not ev["planning_accounting"]["scalar_counts_complete"]


def test_native_shape_cannot_be_reordered_to_a_pair_only_fake_observation():
    with pytest.raises(ValueError, match="eight-axis"):
        runner.native_pair({"joint_position": [0., 0.], "joint_velocity": [0., 0.]})


def test_four_models_share_reference_and_initial_coefficients_but_mapping_is_explicit(tmp_path, monkeypatch):
    small_recipe(monkeypatch)
    output = tmp_path / "out"
    run(output)
    seed = read(output, "seed_results.json")[0]
    all_initial = {**seed["initial_models"], **seed["nominal_models"]}
    assert set(all_initial) == set(runner.MPC_KINDS)
    coefficients = [record["coefficients"] for record in all_initial.values()]
    assert all(item == coefficients[0] for item in coefficients)
    assert all(record["qref_rad"] == [0., -.0005] for record in all_initial.values())
    assert all(record["scalar_update_count"] == 0 for record in seed["nominal_models"].values())
    for name, record in all_initial.items():
        assert record["input_mapping"]["basis"] == runner.MODEL_BASES[name]


def test_independent_prediction_is_one_trajectory_and_four_calls_per_endpoint(tmp_path, monkeypatch):
    small_recipe(monkeypatch)
    output = tmp_path / "out"
    meta = run(output)
    seed = read(output, "seed_results.json")[0]
    pred = seed["evaluations"]["prediction"]
    assert meta["prediction_trajectory_count_per_seed"] == 1
    assert pred["diagnostic_prediction_accounting"]["pair_prediction_attempts"] == 8
    assert pred["metric_prediction_step_count"] == dict.fromkeys((*runner.MPC_KINDS, "persistence"), 2)
    assert len([e for e in read(output, "episodes.json") if e["kind"] == "prediction"]) == 1
    for name, costs in seed["rls_prediction_accounting"].items():
        assert costs["pair_prediction_attempts"] == 2
        assert costs["scalar_prediction_attempts"] == 4
    assert seed["evaluations"]["calibration"]["diagnostic_prediction_accounting"]["pair_prediction_attempts"] == 0
    cal = [r for r in rows(output) if r["phase"] == "calibration"]
    for row in cal:
        for name, update in row["model_update"].items():
            assert row["predicted_next_qv"][name] == [update["preupdate_prediction"]["next_q_rad"],
                                                        update["preupdate_prediction"]["next_v_rad_s"]]


@pytest.mark.parametrize("fixture", [None, {}, {"status": "draft", "selected_id": "unknown", "kp": [64., 64.], "kd": [0., 1.]}])
def test_synthetic_unknown_pd_is_rejected_without_default_gains(tmp_path, fixture):
    with pytest.raises((RuntimeError, ValueError)):
        runner.run_guard_pair_development(tmp_path / "forbidden", protocol_path=PROTOCOL, synthetic=True,
            synthetic_source_bytes=SOURCE_FIXTURE, synthetic_pd_binding=fixture)
    assert not SyntheticEnv.instances
    assert not (tmp_path / "forbidden").exists()


def test_guard_recomputed_at_each_mathematical_prediction_start_without_future_actual():
    model = runner.InputMappedDiagonalPairBodyModel((0., 0.), public_joint_ranges=((-1., 1.), (0., 2.)),
        input_basis="known_angle_guard", trainable=False)
    seen = []
    original = model.public_guard.project
    # The immutable public guard implementation is observed at its class method.
    guard_type = type(model.public_guard)
    original_unbound = guard_type.project
    def record(self, q, u):
        seen.append((tuple(q), tuple(u)))
        return original_unbound(self, q, u)
    from unittest.mock import patch
    with patch.object(guard_type, "project", record):
        planner = core.FixedPairMPC(model, ((-1., 1.), (0., 2.)))
        decision = planner.select((0., .01), (0., .01), (.04, .04))
    assert len(seen) == decision.pair_prediction_attempts
    assert len({q for q, command in seen}) > 1
    assert all(len(q) == len(command) == 2 for q, command in seen)
    assert model.describe_input((0., .01), (0., -.5))["model_feature_command_nm"] == (0., 0.)
    assert original((0., .01), (0., -.5)).projected_start_nm == (0., 0.)


@pytest.mark.parametrize("error_kind", ["pair", "attached", "unknown"])
def test_prediction_meter_retains_failed_scalar_cost_without_retry(error_kind):
    meter = runner.PredictionMeter()
    attempts = []
    def fail():
        attempts.append(1)
        if error_kind == "pair":
            raise core.PairPredictionError(ValueError("second head"), 2, 1, "velocity_output_1")
        exc = OSError("synthetic prediction interrupted")
        if error_kind == "attached":
            exc.pair_prediction_accounting = {"scalar_prediction_attempts": 2, "scalar_prediction_successes": 1}
        raise exc
    with pytest.raises((ValueError, OSError)):
        meter.call(fail)
    cost = meter.snapshot()
    assert len(attempts) == 1 and cost["pair_prediction_attempts"] == 1
    assert cost["failed_pair_prediction_attempts"] == 1
    assert cost["scalar_prediction_attempts"] == (0 if error_kind == "unknown" else 2)
    assert cost["scalar_counts_is_lower_bound"] == (error_kind == "unknown")


def test_planner_fallback_is_kept_as_zero_command_and_not_credited_as_learning(tmp_path, monkeypatch):
    small_recipe(monkeypatch)
    original = SyntheticPlanner.select
    def fallback(self, *args, **kwargs):
        decision = original(self, *args, **kwargs)
        decision.torque, decision.fallback = (0., 0.), True
        return decision
    monkeypatch.setattr(SyntheticPlanner, "select", fallback)
    output = tmp_path / "out"
    run(output)
    seed = read(output, "seed_results.json")[0]
    for kind in runner.MPC_KINDS:
        assert seed["evaluations"][kind]["planner_fallbacks"] == 2
        active = [r for r in rows(output) if r["kind"] == kind and r["phase"] == "control"]
        assert all(r["requested_torque"] == [0.]*8 for r in active)


@pytest.mark.parametrize("fault", [None, "dirty", "untracked_auditor", "changed_blob"])
def test_formal_source_binding_uses_only_explicit_mock_git_before_environment(tmp_path, monkeypatch, fault):
    fake_root = tmp_path / "fixture_project"
    fake_names = (runner.SOURCE_PATH, runner.AUDITOR_PATH, *runner.AUDITOR_SUPPORT_PATHS,
        runner.PROTOCOL_PATH, runner.PD_PROTOCOL_PATH, "pyproject.toml",
        "src/developmental_physics/assets/ground_body.xml", runner.PD_SELECTION_PATH,
        runner.PD_MANIFEST_PATH, runner.PD_AUDIT_PATH)
    blobs = {}
    for name in fake_names:
        path = fake_root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        blobs[name] = ("explicit fixture " + name).encode()
        path.write_bytes(blobs[name])
    monkeypatch.setattr(runner, "__file__", str(fake_root / runner.SOURCE_PATH))
    monkeypatch.setattr(runner, "MODEL_PATH", fake_root / "src/developmental_physics/assets/ground_body.xml")
    calls = []
    def fake_git(args, **kwargs):
        calls.append(list(args))
        if args[:2] == ["git", "rev-parse"]:
            return "a"*40
        if args[:2] == ["git", "status"]:
            return " M fixture" if fault == "dirty" else ""
        if args[:2] == ["git", "ls-files"]:
            names = set(blobs) - ({runner.AUDITOR_PATH} if fault == "untracked_auditor" else set())
            return "\n".join(sorted(names))
        if args[:2] == ["git", "show"]:
            name = args[2].split(":", 1)[1]
            return b"changed fixture blob" if fault == "changed_blob" and name == runner.SOURCE_PATH else blobs[name]
        raise AssertionError(args)
    class FakeBinding(dict):
        def archive_source_bytes(self):
            return {name: blobs[name] for name in (runner.PD_SELECTION_PATH, runner.PD_MANIFEST_PATH, runner.PD_AUDIT_PATH)}
    pd_calls = []
    def fake_pd(root, **kwargs):
        pd_calls.append(kwargs)
        assert root == fake_root
        import hashlib
        assert kwargs["expected_protocol"] == {"path": runner.PD_PROTOCOL_PATH,
            "sha256": hashlib.sha256(blobs[runner.PD_PROTOCOL_PATH]).hexdigest()}
        return FakeBinding(PD_FIXTURE)
    monkeypatch.setattr(runner.subprocess, "check_output", fake_git)
    monkeypatch.setattr(runner, "load_pd_binding", fake_pd)
    if fault:
        with pytest.raises(RuntimeError):
            runner._formal_provenance(fake_root, fake_root / runner.PROTOCOL_PATH)
    else:
        commit, status, pd, archive = runner._formal_provenance(fake_root, fake_root / runner.PROTOCOL_PATH)
        assert commit == "a"*40 and status == ""
        assert set(archive) == set(blobs)
        assert archive == blobs
    assert not SyntheticEnv.instances
    assert calls and all(call[0] == "git" for call in calls)
    assert len(pd_calls) == (0 if fault == "dirty" else 1)
