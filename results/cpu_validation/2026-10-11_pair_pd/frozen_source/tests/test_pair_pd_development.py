"""Draft synthetic PD checks; explicit mock environment, no Git or physics."""
import copy
import gzip
import hashlib
import inspect
import json
import math
from pathlib import Path
from types import SimpleNamespace
import xml.etree.ElementTree as ET
import zipfile

import numpy as np
import pytest

pytest.importorskip("mujoco")
try:
    import pair_pd_development as runner
except ModuleNotFoundError as exc:
    if exc.name != "pair_pd_development":
        raise
    from developmental_physics import pair_pd_development as runner
from developmental_physics.environment import JOINT_NAMES


ROOT = next(p for p in Path(__file__).resolve().parents if (p/"pyproject.toml").is_file())
PROTOCOL = ROOT/runner.PROTOCOL_PATH


class SyntheticEnv:
    instances = []
    fault_trial = 0
    fail_step = stop_step = None
    failure_type = RuntimeError
    stop_joint, stop_signal = 1, "v"
    partial = missing_history = invalid_history = prefix_excursion = False
    nonfinite_joint = None
    infeasible = False

    def __init__(self, config):
        self.config = config
        self.trial = len(self.instances)
        self.instances.append(self)
        self.joint_names = JOINT_NAMES
        asset = ET.fromstring(runner.MODEL_PATH.read_bytes())
        compiler = asset.find("compiler")
        factor = math.pi/180. if compiler is None or compiler.get("angle", "degree") == "degree" else 1.
        public_ranges = {joint.get("name"): [float(x)*factor for x in joint.get("range").split()]
                         for joint in asset.findall(".//joint") if joint.get("range")}
        self.ranges = np.asarray([public_ranges[name] for name in self.joint_names])
        if self.infeasible:
            self.ranges[0] = [-.04, .04]
        self.model = SimpleNamespace(joint=lambda name: SimpleNamespace(range=self.ranges[self.joint_names.index(name)]))
        self.data = SimpleNamespace(qpos=np.zeros(15), qvel=np.zeros(14))
        self.data.qpos[3] = 1.
        self.step_id = self.physics_steps = 0
        self.terminated, self.reason = False, None
        self.q, self.v, self.command = np.zeros(8), np.zeros(8), np.zeros(8)
        self.q[1] = -.0005
        self.commands = []

    def reset(self, seed, pose):
        assert pose == "supine"
        assert seed in {int(np.random.SeedSequence(s).spawn(2)[0].generate_state(1)[0]) for s in (0, 1, 2)}
        return self.observation()

    def parameter_fingerprint(self):
        return "synthetic fixed body, no physics"

    def observation(self):
        self.data.qpos[7:] = self.q
        self.data.qvel[6:] = self.v
        return {"joint_position": self.q.copy(), "joint_velocity": self.v.copy(),
                "imu_gyro": np.zeros(3), "imu_acceleration": np.zeros(3),
                "actuator_torque": self.command.copy(), "previous_command": self.command.copy()}

    def diagnostics(self):
        return {"step_id": self.step_id, "physics_steps": self.physics_steps, "time": .002*self.physics_steps,
                "terminated": self.terminated, "reason": self.reason}

    def step(self, requested):
        index = self.step_id
        if self.trial == self.fault_trial and index == self.fail_step:
            self.physics_steps += 3
            raise self.failure_type("synthetic three paid substeps without return")
        applied = requested.copy()
        outside = ((self.q <= self.ranges[:, 0]+.03) & (applied < 0.)) | ((self.q >= self.ranges[:, 1]-.03) & (applied > 0.))
        applied[outside] = 0.
        self.command = applied.copy()
        self.commands.append(requested.copy())
        n = 3 if self.trial == self.fault_trial and index == self.stop_step and self.partial else 10
        self.v = .5*self.v + .02*applied
        self.q += n*.002*self.v
        if self.prefix_excursion and index == 5:
            self.v[4] = 2.
        elif self.prefix_excursion and index == 6:
            self.q[4] = self.v[4] = 0.
        if self.trial == self.fault_trial and index == self.stop_step:
            if self.stop_signal == "v":
                self.v[self.stop_joint] = 1.
            elif self.stop_signal == "q":
                self.q[self.stop_joint] = (.0 if self.stop_joint == 0 else -.0005)+.12
            if self.partial:
                self.terminated = True
                self.reason = {"type": "SyntheticEnvironmentStop", "message": "partial terminal"}
        if self.trial == self.fault_trial and index == 100 and self.nonfinite_joint is not None:
            self.q[self.nonfinite_joint] = np.nan
        self.step_id += 1
        self.physics_steps += n
        diagnostic = {**self.diagnostics(), "executed_substeps": n,
            "applied_torque_history": [applied.tolist() for _ in range(n)], "requested_torque": requested,
            "accepted_torque": requested, "applied_torque": applied,
            "guarded_substeps": n if np.any(applied != requested) else 0,
            "substep_ground_normal_forces": [1.]*n, "substep_kinetic_energies": [.2]*n,
            "substep_minimum_contact_distances": [-.0001]*n, "peak_substep_ground_normal_force": 1.,
            "ground_normal_impulse_ns": .002*n, "peak_substep_kinetic_energy": .2,
            "minimum_substep_contact_distance": -.0001}
        if self.trial == self.fault_trial and index == 100:
            if self.missing_history:
                diagnostic.pop("applied_torque_history")
            if self.invalid_history:
                diagnostic["applied_torque_history"][0][0] = np.nan
        return SimpleNamespace(observation=self.observation(), diagnostics=diagnostic,
                               terminated=self.terminated, reason=self.reason)


@pytest.fixture(autouse=True)
def synthetic_only(monkeypatch):
    def forbid(*args, **kwargs):
        raise AssertionError("real physics/Git must never be called by these synthetic tests")
    monkeypatch.setattr(runner._REAL_ENV, "__init__", forbid)
    monkeypatch.setattr(runner.subprocess, "check_output", forbid)
    # Windows platform.platform() itself uses subprocess("ver"); keep the
    # complete subprocess prohibition and explicitly omit this test-only field.
    monkeypatch.setattr(runner.platform, "platform", lambda: "synthetic platform not queried")
    monkeypatch.setattr(runner, "GroundBodyEnv", SyntheticEnv)
    SyntheticEnv.instances = []
    SyntheticEnv.fault_trial = 0
    SyntheticEnv.fail_step = SyntheticEnv.stop_step = None
    SyntheticEnv.failure_type = RuntimeError
    SyntheticEnv.stop_joint, SyntheticEnv.stop_signal = 1, "v"
    SyntheticEnv.partial = SyntheticEnv.missing_history = SyntheticEnv.invalid_history = False
    SyntheticEnv.prefix_excursion = SyntheticEnv.infeasible = False
    SyntheticEnv.nonfinite_joint = None


def small_recipe(monkeypatch, candidates=1):
    monkeypatch.setattr(runner, "DEVELOPMENT_SEEDS", (0,))
    monkeypatch.setattr(runner, "FIXED_KD", runner.FIXED_KD[:candidates])


def run(output):
    return runner.run_pair_pd(output, protocol_path=PROTOCOL, synthetic=True)


def read(output, name):
    return json.loads((output/name).read_text(encoding="utf-8"))


def rows(output):
    with gzip.open(output/"trace.jsonl.gz", "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream]


def test_real_disabled_and_synthetic_cannot_use_original_environment(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "FORMAL_EXECUTION_FROZEN", False)
    with pytest.raises(RuntimeError, match="disabled"):
        runner.run_pair_pd(tmp_path/"real", protocol_path=PROTOCOL)
    monkeypatch.setattr(runner, "GroundBodyEnv", runner._REAL_ENV)
    with pytest.raises(RuntimeError, match="replaced"):
        run(tmp_path/"synthetic")
    assert not (tmp_path/"real").exists() and not (tmp_path/"synthetic").exists()


def test_fixed_grid_full_8100_paid_calls_and_snapshot_source_identity(tmp_path):
    output = tmp_path/"full"
    metadata = run(output)
    assert metadata["synthetic"] and metadata["backend"] == "synthetic, no physics"
    assert metadata["complete"] and metadata["all_trials_successful"]
    assert metadata["source_commit"] is metadata["source_status"] is metadata["source_dirty"] is None
    assert metadata["source_git_blobs"] == {}
    assert metadata["seeds"] == [0, 1, 2] and metadata["joint_indices"] == [0, 1]
    assert metadata["kp"] == [64., 64.]
    assert metadata["kd_candidates"] == [[0., 1.], [0., 2.], [0., 4.], [1., 1.], [1., 2.], [1., 4.], [2., 1.], [2., 2.], [2., 4.]]
    assert metadata["planned_episode_count"] == metadata["completed_trials"] == 27
    assert metadata["control_calls_attempted"] == metadata["control_steps"] == metadata["maximum_control_steps"] == 8100
    assert metadata["physics_steps"] == metadata["maximum_physics_steps"] == 81000
    assert metadata["model_updates"] == 0 and metadata["parameter_updates"] == {"body_model": 0, "policy": 0, "gains": 0}
    assert metadata["gpu"] is None
    episodes = read(output, "episodes.json")
    assert sum(e["phase_budgets"]["prefix"]["control_steps"] for e in episodes) == 2700
    assert sum(e["phase_budgets"]["control"]["physics_steps"] for e in episodes) == 54000
    for episode in episodes:
        assert episode["prefix_end_q_rad"] == [0., -.0005]
        assert [s["direction"] for s in episode["selection_records"]] == [1, 1]
        assert episode["metric_control_step_count"] == 200
        assert episode["phase_complete_transition_counts"] == {"prefix": 100, "control": 200}
        assert episode["returned_control_steps"] == episode["trace_rows_written"] == 300
        assert episode["actual_effort_complete"] and not episode["actual_effort_is_lower_bound"]
        assert episode["pd_action_calls"] == 200 and episode["failed_pd_attempts"] == 0
        assert episode["environment_fingerprint_before"] == episode["environment_fingerprint_after"]
        assert episode["phase_risk"]["full"]["ground_normal_impulse_ns"] == pytest.approx(6.)
        assert episode["phase_risk"]["prefix"]["ground_normal_impulse_ns"] == pytest.approx(2.)
        for name, count in (("segment0", 100), ("segment1", 100), ("segment0_last20", 20), ("segment1_last20", 20)):
            window = episode["tracking_windows"][name]
            assert window["complete_count"] == window["returned_count"] == count
            assert window["missing_complete_count"] == window["missing_returned_count"] == 0
    trace = rows(output)
    assert len(trace) == 8100 and all(r["requested_torque"][2:] == [0.]*6 for r in trace)
    assert trace[100]["target_q_rad"] == [.04, .0395]
    assert trace[199]["target_q_rad"] == [.04, .0395]
    assert trace[200]["target_q_rad"] == [.08, .0795]
    assert all(r["target_q_rad"] is None and r["study_abort"] is None for r in trace[:100])
    selection = read(output, "selection.json")
    assert selection["status"] == "selected" and len(selection["candidates"]) == 9
    assert all(c["eligible"] for c in selection["candidates"])
    assert sum(c["paid_control_steps"] for c in selection["candidates"]) == 8100
    with zipfile.ZipFile(output/"source_snapshot.zip") as snapshot:
        assert set(snapshot.namelist()) == set(metadata["source_sha256"])
        for name, sha in metadata["source_sha256"].items():
            assert hashlib.sha256(snapshot.read(name)).hexdigest() == sha
        assert runner.SYNTHETIC_FIXTURE_PATH in snapshot.namelist()
    assert metadata["source_snapshot_sha256"] == hashlib.sha256((output/"source_snapshot.zip").read_bytes()).hexdigest()
    assert metadata["protocol"]["sha256"] == hashlib.sha256(PROTOCOL.read_bytes()).hexdigest()
    with pytest.raises(FileExistsError):
        run(output)


@pytest.mark.parametrize("joint", [0, 1])
@pytest.mark.parametrize("signal", ["q", "v"])
def test_each_axis_equal_study_threshold_scores_full_terminal_and_independent_next(tmp_path, monkeypatch, joint, signal):
    small_recipe(monkeypatch, 2)
    SyntheticEnv.stop_step, SyntheticEnv.stop_joint, SyntheticEnv.stop_signal = 100, joint, signal
    output = tmp_path/"stop"
    metadata = run(output)
    first, second = read(output, "episodes.json")
    assert metadata["complete"] and not metadata["all_trials_successful"] and second["complete"]
    assert first["status"] == "terminated" and not first["complete"]
    assert first["reason"] == first["study_abort"] and first["environment_terminated"] is False
    assert first["study_abort"]["triggers"][0]["joint_index"] == joint
    assert first["control_steps"] == 101 and first["physics_steps"] == 1010
    assert first["metric_control_step_count"] == 1
    assert first["tracking_windows"]["segment0"]["complete_count"] == 1
    assert first["tracking_windows"]["segment0_last20"]["tracking"] is None
    assert not read(output, "selection.json")["candidates"][0]["eligible"]


def test_partial_endpoint_raw_errors_paid_effort_and_environment_reason_are_retained(tmp_path, monkeypatch):
    small_recipe(monkeypatch)
    SyntheticEnv.stop_step, SyntheticEnv.partial = 100, True
    output = tmp_path/"partial"
    run(output)
    first = read(output, "episodes.json")[0]
    last = rows(output)[-1]
    assert first["status"] == "terminated" and first["reason"]["type"] == "SyntheticEnvironmentStop"
    assert first["study_abort"] is not None and first["environment_terminated"] is True
    assert first["physics_steps"] == 1003 and first["metric_control_step_count"] == 0
    assert first["tracking"] is None and first["partial_interval_target_error_count"] == 1
    assert first["partial_interval_target_errors_rad"][0]["error_rad"] == last["partial_interval_target_error_rad"]
    assert first["phase_effort"]["control"]["requested_squared_nm2_s"] == pytest.approx([.0015, .0015])
    assert first["phase_effort_combined"]["control"]["actual_squared_nm2_s"] == pytest.approx(.003)
    assert first["actual_effort_complete"]
    window = first["tracking_windows"]["segment0"]
    assert window["returned_count"] == window["partial_count"] == 1 and window["complete_count"] == 0
    assert window["missing_returned_count"] == 99 and window["missing_complete_count"] == 100


def test_last_planned_stop_keeps_200_scores_but_never_qualifies(tmp_path, monkeypatch):
    small_recipe(monkeypatch)
    SyntheticEnv.stop_step = 299
    output = tmp_path/"last"
    run(output)
    first = read(output, "episodes.json")[0]
    assert first["metric_control_step_count"] == 200 and first["physics_steps"] == 3000
    assert first["status"] == "terminated" and not first["complete"]
    assert first["tracking_windows"]["segment1_last20"]["complete_count"] == 20
    selection = read(output, "selection.json")
    assert selection["status"] == "blocked" and selection["picked"] is None


def test_prefix_fullbody_excursion_uses_only_environment_protection(tmp_path, monkeypatch):
    small_recipe(monkeypatch)
    SyntheticEnv.prefix_excursion = True
    output = tmp_path/"prefix"
    assert run(output)["all_trials_successful"]
    first = read(output, "episodes.json")[0]
    assert first["phase_risk"]["prefix"]["max_native_speed_rad_s"] == 2.
    assert all(r["study_abort"] is None for r in rows(output)[:100])


@pytest.mark.parametrize("kind", [RuntimeError, OSError, KeyboardInterrupt])
def test_failed_step_paid_request_and_unknown_actual_fatal_block_rules(tmp_path, monkeypatch, kind):
    small_recipe(monkeypatch, 2)
    SyntheticEnv.fail_step, SyntheticEnv.failure_type = 100, kind
    output = tmp_path/kind.__name__
    if kind is RuntimeError:
        assert run(output)["complete"]
    else:
        with pytest.raises(kind):
            run(output)
    first, second = read(output, "episodes.json")
    assert first["status"] == "exception" and first["control_calls_attempted"] == 101
    assert first["control_steps"] == 100 and first["physics_steps"] == 1003
    assert first["returned_control_steps"] == first["trace_rows_written"] == 100
    assert first["unreturned_physics_steps"] == 3 and first["actual_effort_is_lower_bound"]
    assert first["phase_actual_effort_missing_substeps"]["control"] == 3
    assert first["phase_effort_combined"]["control"]["requested_squared_nm2_s"] == pytest.approx(.003)
    assert second["status"] == ("completed" if kind is RuntimeError else "blocked")
    assert rows(output)[100]["physics_steps_after"] == 1003


def test_missing_history_remains_lower_bound_while_complete_tracking_is_not_selected(tmp_path, monkeypatch):
    small_recipe(monkeypatch)
    SyntheticEnv.missing_history = True
    output = tmp_path/"missing"
    assert run(output)["all_trials_successful"]
    first = read(output, "episodes.json")[0]
    assert first["complete"] and first["metric_control_step_count"] == 200
    assert not first["actual_effort_complete"] and first["actual_effort_is_lower_bound"]
    assert first["phase_actual_effort_missing_substeps"]["control"] == 10
    assert first["phase_actual_effort_substeps"]["control"] == 1990
    assert first["actual_history_issues"] == [{"type": "ActualHistoryMissing", "phase": "control", "control_index": 100, "missing_substeps": 10}]
    assert "applied_torque_history" not in rows(output)[100]["diagnostics"]
    assert read(output, "selection.json")["picked"] is None


def test_invalid_history_retains_paid_full_endpoint_and_returned_unstored_exception(tmp_path, monkeypatch):
    small_recipe(monkeypatch, 2)
    SyntheticEnv.invalid_history = True
    output = tmp_path/"invalid"
    run(output)
    first, second = read(output, "episodes.json")
    assert first["status"] == "exception" and second["complete"]
    assert first["metric_control_step_count"] == 1
    assert first["returned_unstored_control_steps"] == 1 and first["unreturned_physics_steps"] == 0
    assert first["actual_effort_is_lower_bound"] and first["phase_actual_effort_missing_substeps"]["control"] == 10
    failed = rows(output)[100]
    assert failed["invalid_numeric_fields"]
    assert failed["returned_step_diagnostics"]["applied_torque_history"][0][0] is None


def test_nonfinite_other_axis_is_preserved_and_disqualifies_trial(tmp_path, monkeypatch):
    small_recipe(monkeypatch, 2)
    SyntheticEnv.nonfinite_joint = 7
    output = tmp_path/"nonfinite"
    run(output)
    first, second = read(output, "episodes.json")
    assert first["status"] == "exception" and second["complete"]
    assert first["physics_steps"] == 1010 and first["metric_control_step_count"] == 0
    failed = rows(output)[100]
    assert failed["returned_observation_after"]["joint_position"][7] is None
    assert failed["invalid_numeric_fields"]


def test_pd_failure_before_step_has_no_stale_return_or_cost(tmp_path, monkeypatch):
    small_recipe(monkeypatch, 2)
    original = runner.pd_pair_request
    calls = 0
    def fail(*args):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("synthetic PD failure")
        return original(*args)
    monkeypatch.setattr(runner, "pd_pair_request", fail)
    output = tmp_path/"pd_failure"
    run(output)
    first, second = read(output, "episodes.json")
    assert first["status"] == "exception" and second["complete"]
    assert first["pd_action_calls"] == first["failed_pd_attempts"] == 1
    assert first["control_steps"] == first["control_calls_attempted"] == 100 and first["physics_steps"] == 1000
    failed = rows(output)[100]
    assert failed["control_steps_before"] is failed["physics_steps_before"] is None
    assert failed["returned_step_diagnostics"] is failed["returned_observation_after"] is None


def test_any_trace_write_failure_is_fatal_after_paid_return(tmp_path, monkeypatch):
    small_recipe(monkeypatch, 2)
    original = runner.gzip.open
    class BrokenTrace:
        def __init__(self, path, mode, **kwargs):
            self.stream = original(path, mode, **kwargs)
            self.failed = False
        def __enter__(self):
            self.stream.__enter__()
            return self
        def __exit__(self, *args):
            return self.stream.__exit__(*args)
        def write(self, line):
            row = json.loads(line)
            if not self.failed and row.get("control_index") == 100 and "collector_exception" not in row:
                self.failed = True
                raise ValueError("synthetic trace serialization failure")
            return self.stream.write(line)
    monkeypatch.setattr(runner.gzip, "open", lambda path, mode, **kw:
                        BrokenTrace(path, mode, **kw) if mode == "wt" else original(path, mode, **kw))
    output = tmp_path/"trace"
    with pytest.raises(ValueError, match="trace serialization"):
        run(output)
    first, second = read(output, "episodes.json")
    assert first["status"] == "exception" and second["status"] == "blocked"
    assert first["control_steps"] == 101 and first["physics_steps"] == 1010
    assert first["actual_effort_complete"] and first["returned_unstored_control_steps"] == 1
    assert first["trace_write_failure"]["type"] == "ValueError" and not first["risk_telemetry_complete"]
    assert rows(output)[100]["returned_step_diagnostics"]["executed_substeps"] == 10


def test_infeasible_targets_fail_after_own_paid_prefix_without_clipping(tmp_path, monkeypatch):
    small_recipe(monkeypatch)
    SyntheticEnv.infeasible = True
    output = tmp_path/"target"
    run(output)
    first = read(output, "episodes.json")[0]
    assert first["status"] == "exception" and "infeasible" in first["collector_exception"]["message"]
    assert first["control_steps"] == 100 and first["physics_steps"] == 1000
    assert first["pd_action_calls"] == 0 and first["prefix_end_q_rad"] == [0., -.0005]


def test_selection_strict_full_seed_qualification_and_exact_sort_hierarchy(monkeypatch):
    monkeypatch.setattr(runner, "FIXED_KD", runner.FIXED_KD[:2])
    trials = []
    for seed in (0, 1, 2):
        for candidate in (0, 1):
            trials.append({"trial_id": f"seed{seed}_candidate{candidate}", "seed": seed, "candidate": candidate,
                "status": "completed", "complete": True, "actual_effort_complete": True,
                "metric_control_step_count": 200, "phase_complete_transition_counts": {"prefix": 100, "control": 200},
                "tracking": {"joint": .1, "per_axis": [.1, .1]},
                "collector_exception": None, "study_abort": None, "environment_terminated": False,
                "control_steps": 300, "physics_steps": 3000,
                "phase_effort_combined": {"control": {"actual_squared_nm2_s": 1.}}})
    assert runner._selection(trials)["picked"]["candidate"] == 0
    modified = copy.deepcopy(trials)
    for row in modified:
        if row["candidate"] == 1:
            row["tracking"]["joint"] = float(np.nextafter(.1, 0.))
            row["tracking"]["per_axis"] = [.2, .2]
            row["phase_effort_combined"]["control"]["actual_squared_nm2_s"] = 100.
    assert runner._selection(modified)["picked"]["candidate"] == 1
    modified = copy.deepcopy(trials)
    for row in modified:
        if row["candidate"] == 0:
            row["tracking"]["joint"] = float(row["seed"]+1)
            row["tracking"]["per_axis"] = [.2, .05]
        else:
            row["tracking"]["joint"] = 2.
            row["phase_effort_combined"]["control"]["actual_squared_nm2_s"] = 100.
    assert runner._selection(modified)["picked"]["candidate"] == 1
    modified = copy.deepcopy(trials)
    for row in modified:
        if row["candidate"] == 1:
            row["phase_effort_combined"]["control"]["actual_squared_nm2_s"] = .9
    assert runner._selection(modified)["picked"]["candidate"] == 1
    modified = copy.deepcopy(trials)
    modified[0]["complete"] = False
    modified[1]["actual_effort_complete"] = False
    selected = runner._selection(modified)
    assert selected["status"] == "blocked" and selected["picked"] is None
    assert all(not c["eligible"] and c["sort_key"] is None for c in selected["candidates"])


def test_selection_worst_seed_beats_opposite_worst_axis_order(monkeypatch):
    """Hand-designed non-mirror witness: equal mean2, seed max3 vs2.

    Candidate0 alternates its error axis. Its largest axis mean is
    4*sqrt(2)/3, below candidate1's 2*sqrt(2), so the discarded axis rule
    selects 0. The specified worst-seed rule must select 1 despite effort100.
    Each per-axis pair has joint RMSE sqrt((a*a+b*b)/2) as recorded.
    """
    monkeypatch.setattr(runner, "FIXED_KD", runner.FIXED_KD[:2])
    trials = []
    for seed in (0, 1, 2):
        for candidate in (0, 1):
            joint = float(seed+1) if candidate == 0 else 2.
            axis = [joint*math.sqrt(2.), 0.] if candidate == 1 or seed != 1 else [0., joint*math.sqrt(2.)]
            trials.append({"trial_id": f"seed{seed}_candidate{candidate}", "seed": seed, "candidate": candidate,
                "status": "completed", "complete": True, "actual_effort_complete": True,
                "metric_control_step_count": 200, "phase_complete_transition_counts": {"prefix": 100, "control": 200},
                "tracking": {"joint": joint, "per_axis": axis},
                "collector_exception": None, "study_abort": None, "environment_terminated": False,
                "control_steps": 300, "physics_steps": 3000,
                "phase_effort_combined": {"control": {"actual_squared_nm2_s": 1. if candidate == 0 else 100.}}})
    assert 4*math.sqrt(2.)/3 < 2*math.sqrt(2.)
    selected = runner._selection(trials)
    assert selected["picked"]["candidate"] == 1
    assert [c["sort_key"] for c in selected["candidates"]] == [[2., 3., 1., 0], [2., 2., 100., 1]]
    assert selected["sort_order"][1] == "max_seed_joint_rmse"


def test_current_pd_math_finite_inputs_and_restricted_trial_api(tmp_path):
    assert list(inspect.signature(runner.pd_pair_request).parameters) == ["q", "v", "current_target", "kd"]
    capped, raw = runner.pd_pair_request((0., -.0005), (.2, -.3), (.04, .0395), (2., 4.))
    assert raw == pytest.approx((2.16, 3.76)) and capped == (.5, .5)
    with pytest.raises(ValueError):
        runner.pd_pair_request((np.nan, 0.), (0., 0.), (.04, .04), (0., 1.))
    for key, value in (("seeds", [20]), ("gains", [(1., 0.)]), ("joint", 1), ("pose", "prone")):
        with pytest.raises(TypeError):
            runner.run_pair_pd(tmp_path/key, protocol_path=PROTOCOL, synthetic=True, **{key: value})
    with pytest.raises(ValueError, match="exact declared"):
        runner.run_pair_pd(tmp_path/"protocol", protocol_path=ROOT/"README.md", synthetic=True)
    assert not SyntheticEnv.instances
