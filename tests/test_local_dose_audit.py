"""Synthetic arithmetic and saved-log fixtures; no simulator or fitting imports."""
import copy
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import zipfile

import pytest

SCRIPT = Path(__file__).resolve().parents[1]/"scripts/audit_local_dose.py"
spec = importlib.util.spec_from_file_location("dose_audit_core", SCRIPT)
core = importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)


@pytest.mark.parametrize("structure,denominator,last_index", [("linear4", 126., 3), ("hinge5", 132.25, 4)])
def test_rls_matches_hand_gain_and_keeps_input_arrays(structure, denominator, last_index):
    state = core.initial_state(structure)
    features = core.feature_vector(0., 0., 0., .5, structure)
    original = copy.deepcopy(state)
    theta, covariance = core.replay_rls(state["theta"], state["covariance"], features, .1)
    assert theta[2] == pytest.approx(.02+50./denominator*.09)
    assert theta[last_index] == pytest.approx(100./denominator*.09)
    assert covariance[2][last_index] == pytest.approx(-50./denominator*100.)
    assert covariance[2][last_index] == covariance[last_index][2]
    assert state == original
    if structure == "hinge5":
        assert theta[3] == pytest.approx(25./denominator*.09)


@pytest.mark.parametrize("u", [-.5, -.375, -.25, -.125, 0., .125, .25, .375, .5])
def test_nominal_structures_predict_identically_and_hinge_sign_is_fixed(u):
    assert core.predict(core.INITIAL["linear4"], .1, .2, -.1, u) == core.predict(core.INITIAL["hinge5"], .1, .2, -.1, u)
    feature = core.feature_vector(0., 0., 0., u, "hinge5")[3]
    assert feature == (1. if u > 0 else -1. if u < 0 else 0.)*max(abs(u)-.25, 0.)


@pytest.mark.parametrize("fault", ["dimension", "bool", "nonfinite", "covariance", "denominator"])
def test_invalid_math_input_is_rejected(fault):
    state, features = core.initial_state("linear4"), [0., 0., .5, 1.]
    if fault == "dimension":
        state["theta"].append(0.)
    elif fault == "bool":
        features[0] = True
    elif fault == "nonfinite":
        state["theta"][0] = float("inf")
    elif fault == "covariance":
        state["covariance"].pop()
    else:
        state["covariance"] = [[-100. if i == j else 0. for j in range(4)] for i in range(4)]
    with pytest.raises(ValueError):
        core.replay_rls(state["theta"], state["covariance"], features, .1)


def test_mpc_planning_permission_horizon_and_zero_fallback():
    normal = core.replay_mpc(core.INITIAL["linear4"], 0., 0., 0., .04, 0., [-1., 1.])
    assert normal["mathematical_prediction_calls"] == 135
    assert normal["feasible_candidates"] == 9 and len(normal["predicted_q"]) == 15
    assert normal["torque"] in [-.5+i*.125 for i in range(9)]
    fallback = core.replay_mpc(core.INITIAL["hinge5"], 0., 0., 2., .04, 0., [-1., 1.])
    assert fallback["fallback"] and fallback["torque"] == 0.
    assert fallback["mathematical_prediction_calls"] == 9


def test_free_rollout_never_reads_future_state_and_persistence_ignores_commands():
    result = core.free_rollout(core.INITIAL["linear4"], .1, .2, .1, [.5, .5])
    assert result[-1] == pytest.approx((.2046, .12))
    assert core.free_rollout(None, 0., .2, .1, [.5, -.5])[-1] == pytest.approx((.204, .1))
    with pytest.raises(ValueError):
        core.free_rollout([1e308, 0., .02, 0.], 0., .2, 2., [0.])


def native(q=0., v=0., u=0.):
    return {"joint_position": [q]+[0.]*7, "joint_velocity": [v]+[0.]*7,
        "imu_gyro": [0.]*3, "imu_acceleration": [0.]*3,
        "actuator_torque": [u]+[0.]*7, "previous_command": [u]+[0.]*7}


def transition(index, *, kind="old_hinge5_mpc", phase="control", q=0., v=0., u=0., next_q=0., next_v=0., before=None, n=10, terminated=False):
    request, observation = [u]+[0.]*7, native(next_q, next_v, u)
    physics = index*10+n
    d = {"executed_substeps": n, "terminated": terminated, "step_id": index+1, "physics_steps": physics, "time": physics*.002,
        "requested_torque": request, "accepted_torque": request, "applied_torque": request,
        "applied_torque_history": [request.copy() for _ in range(n)], "guarded_substeps": 0,
        "substep_ground_normal_forces": [0.]*n, "substep_kinetic_energies": [0.]*n,
        "substep_minimum_contact_distances": [0.]*n, "peak_substep_ground_normal_force": 0.,
        "ground_normal_impulse_ns": 0., "peak_substep_kinetic_energy": 0., "minimum_substep_contact_distance": 0.}
    plan = next(p for p in core.planned_matrix() if p["trial_id"] == "seed0_"+kind)
    return {**{k: plan[k] for k in ("trial_id", "seed", "kind", "model_scope", "calibration_dose", "model_structure", "integration")},
        "step_index": index, "phase": phase, "shared_transition_id": "seed0_"+kind+":"+str(index),
        "observation_before": native(q, v) if before is None else before, "observation_after": observation,
        "requested_torque": request, "target_q": None, "predicted_next_qv": {}, "model_update": None, "planner_decision": None,
        "diagnostics": d, "qpos": [0., 0., .5, 1., 0., 0., 0.]+observation["joint_position"],
        "qvel": [0.]*6+observation["joint_velocity"]}


@pytest.mark.parametrize("steps,expected", [(100, [100, 96, 86, 51]), (200, [200, 196, 186, 151]), (300, [300, 296, 286, 251])])
def test_legal_denominators_all_horizons(steps, expected):
    indexed = {i: transition(i) for i in range(100, 100+steps)}
    for h, count in zip(core.HORIZONS, expected):
        d = core.window_denominators(indexed, steps, h)
        assert d["expected_windows_from_planned_active_duration"] == d["valid_physical_windows"] == count
        assert d["excluded_windows"] == 0


@pytest.mark.parametrize("fault,reason", [("missing", "missing_control_row"), ("partial", "partial_physics_interval"),
    ("stop", "continued_after_termination"), ("phase", "crossed_phase_or_trial_boundary"),
    ("reset", "crossed_phase_or_trial_boundary"), ("native", "native_state_discontinuity"), ("time", "time_discontinuity")])
def test_windows_reject_invalid_continuations(fault, reason):
    rows = {i: transition(i) for i in range(100, 105)}
    if fault == "missing":
        rows.pop(102)
    elif fault == "partial":
        rows[102]["diagnostics"]["executed_substeps"] = 3
    elif fault == "stop":
        rows[101]["diagnostics"]["terminated"] = True
    elif fault == "phase":
        rows[102]["phase"] = "prefix"
    elif fault == "reset":
        rows[102]["trial_id"] = "another_reset"
    elif fault == "native":
        rows[102]["observation_before"]["joint_velocity"][0] = .1
    else:
        rows[102]["diagnostics"]["time"] += .001
    assert core.valid_window(rows, 100, 5)[1] == reason


def test_full_terminal_can_end_window_but_partial_terminal_cannot():
    rows = {i: transition(i) for i in range(100, 105)}
    rows[104]["diagnostics"]["terminated"] = True
    d = core.window_denominators(rows, 5, 5)
    assert d["valid_physical_windows"] == d["valid_windows_ending_in_termination"] == 1
    rows[104]["diagnostics"]["executed_substeps"] = 3
    assert core.window_denominators(rows, 5, 5)["valid_physical_windows"] == 0


def gate_fixture(tracking=(1., 1., 1.), candidate=(.9, .9, .9), effort=1.):
    rows = []
    for seed, a, b in zip(core.SEEDS, tracking, candidate):
        evaluations = {}
        for name in core.CANDIDATES:
            evaluations[name+"_mpc"] = {"eligible": True, "actual_effort_complete": True,
                "tracking_rmse_rad": a if name == core.ANCHOR else b,
                "control_effort": {"actual_absolute_nm_s": 1. if name == core.ANCHOR else effort,
                                   "actual_squared_nm2_s": 1. if name == core.ANCHOR else effort}}
        for kind in ("prediction_low", "prediction_full"):
            evaluations[kind] = {"eligible": True, "velocity_prediction_rmse": {c+"_mpc": 1. for c in core.CANDIDATES}}
        rows.append({"seed": seed, "evaluations": evaluations})
    return rows


def test_predeclared_adoption_and_exact_dimension_id_ties():
    result = core.adoption_gate(gate_fixture())
    assert result["passed"] and result["selected_candidate"] == "old_linear4"
    assert [r["passed"] for r in result["candidates"]] == [True, False, True, True]
    rows = gate_fixture()
    for r in rows:
        r["evaluations"]["new_hinge5_mpc"]["tracking_rmse_rad"] = .899999999999
    assert core.adoption_gate(rows)["selected_candidate"] == "new_hinge5"


@pytest.mark.parametrize("fault", ["worse_prediction_low", "worse_prediction_full", "worse_tracking", "missing_prediction", "duplicate_seed", "missing_seed", "incomplete", "missing_actual", "negative_actual", "effort"])
def test_any_failed_gate_retains_anchor(fault):
    rows = gate_fixture()
    for name in core.CANDIDATES:
        if name == core.ANCHOR:
            continue
        c = rows[0]["evaluations"][name+"_mpc"]
        if fault.startswith("worse_prediction"):
            k = "prediction_low" if fault.endswith("low") else "prediction_full"
            rows[0]["evaluations"][k]["velocity_prediction_rmse"][name+"_mpc"] = 1.00000000001
        elif fault == "worse_tracking":
            c["tracking_rmse_rad"] = 1.01
        elif fault == "missing_prediction":
            rows[0]["evaluations"]["prediction_full"]["eligible"] = False
        elif fault == "incomplete":
            c["eligible"] = False
        elif fault == "missing_actual":
            c["actual_effort_complete"] = False
        elif fault == "negative_actual":
            c["control_effort"]["actual_absolute_nm_s"] = -1.
        elif fault == "effort":
            c["control_effort"]["actual_squared_nm2_s"] = 1.151
    if fault == "duplicate_seed":
        rows[2]["seed"] = 0
    elif fault == "missing_seed":
        rows.pop()
    result = core.adoption_gate(rows)
    assert not result["passed"] and result["selected_candidate"] == core.ANCHOR


def test_gate_uses_raw_means_not_average_percentages():
    result = core.adoption_gate(gate_fixture((.1, 1., 10.), (.04, .9, 9.95)))
    assert not result["passed"]
    assert result["candidates"][0]["tracking_mean_improvement"] < .05


def test_effort_mean_bound_allows_predeclared_per_seed_difference():
    rows = gate_fixture()
    for r in rows:
        for c in core.CANDIDATES:
            if c != core.ANCHOR:
                r["evaluations"][c+"_mpc"]["control_effort"] = dict.fromkeys(core.EFFORT_KEYS[2:], 1.05)
    assert core.adoption_gate(rows)["passed"]
    for c in core.CANDIDATES:
        if c != core.ANCHOR:
            rows[0]["evaluations"][c+"_mpc"]["control_effort"]["actual_squared_nm2_s"] += 1e-9
    assert not core.adoption_gate(rows)["passed"]


def test_zero_denominators_are_not_invented_percentages():
    rows = gate_fixture()
    for r in rows:
        for c in core.CANDIDATES:
            r["evaluations"][c+"_mpc"]["control_effort"] = dict.fromkeys(core.EFFORT_KEYS[2:], 0.)
    assert core.adoption_gate(rows)["passed"]
    for c in core.CANDIDATES:
        if c != core.ANCHOR:
            rows[0]["evaluations"][c+"_mpc"]["control_effort"]["actual_absolute_nm_s"] = .0001
    assert not core.adoption_gate(rows)["passed"]
    assert not core.adoption_gate(gate_fixture((0., 0., 0.), (0., 0., 0.)))["passed"]


def test_factorial_contrasts_use_signed_raw_values():
    effects = core.factorial_effects({"old_linear4": 4., "old_hinge5": 3., "new_linear4": 2., "new_hinge5": 1.5})
    assert effects == {"hinge_minus_linear": {"old": -1., "new": -.5},
        "new_minus_old": {"linear4": -2., "hinge5": -1.5}, "difference_of_differences": .5}


def test_q_only_coverage_equality_inside_and_partial_excluded():
    cal = [transition(100, q=0., v=0.), transition(101, q=1., v=2.), transition(102, q=10., v=20., n=3)]
    control = [transition(100, q=0., v=0.), transition(101, q=1., v=2.), transition(102, q=1.5, v=1.), transition(103, q=.5, v=3.)]
    result = core.state_coverage(cal, control, 0.)
    assert result["calibration_native_samples"] == 2
    assert result["q_outside_fraction"] == result["v_outside_fraction"] == .25
    assert result["either_outside_fraction"] == .5
    assert result["nearest_q_distance_mean_rad"] == .25
    assert result["nearest_q_distance_max_rad"] == .5
    assert not any("normalized" in key for key in result)


def test_frozen_plan_caps_and_schedules_effort():
    plans = core.planned_matrix()
    assert len(plans) == 27 and sum(p["maximum_control_steps"] for p in plans) == 8100
    for d, absolute, square in (("old", .55, .2), ("new", .7, .275)):
        amplitudes = core.CALIBRATION_AMPLITUDES[d]
        assert sum(amplitudes)*10*.02 == pytest.approx(absolute)
        assert sum(a*a for a in amplitudes)*10*.02 == pytest.approx(square)
    for name, a, s in (("low", .35, .0875), ("full", .455, .170625)):
        values = core.PREDICTION_AMPLITUDES[name]
        assert sum(values)*14*.02 == pytest.approx(a)
        assert sum(v*v for v in values)*14*.02 == pytest.approx(s)
    assert core.CALIBRATION_AMPLITUDES["old"][:3] == core.CALIBRATION_AMPLITUDES["new"][:3]


def write_manifest(path):
    (path/"manifest.json").write_text(json.dumps({p.name: core.file_hash(p) for p in path.iterdir() if p.name != "manifest.json"}), encoding="utf-8")


def partial_archive(path):
    """A paid 3-substep prefix stop; all other planned outcomes remain visible."""
    path.mkdir()
    plans = core.planned_matrix()
    episodes = [{**p, "status": "blocked", "reason": {"type": "ArchiveAborted"}, "collector_exception": None,
        "control_calls_attempted": 0, "control_steps": 0, "physics_steps": 0,
        "phase_budgets": {phase: {"control_calls_attempted": 0, "control_steps": 0, "physics_steps": 0} for phase in core.PHASES}} for p in plans]
    episodes[0].update(status="terminated", reason="synthetic_stop", control_calls_attempted=1, control_steps=1,
        physics_steps=3, unreturned_physics_steps=0, risk_telemetry_complete=True,
        environment_fingerprint_before="1"*64, environment_fingerprint_after="1"*64)
    episodes[0]["phase_budgets"]["prefix"] = {"control_calls_attempted": 1, "control_steps": 1, "physics_steps": 3}
    row = transition(0, kind="calibration_old", phase="prefix", n=3, terminated=True)
    ev = {"completed": False, "status": "terminated", "tracking_rmse_rad": None,
        "position_prediction_rmse": {}, "velocity_prediction_rmse": {}, "metric_control_step_count": 0,
        "saturated_control_steps": 0, "phase_effort": {p: core.new_effort() for p in core.PHASES},
        "phase_actual_effort_substeps": {p: 3 if p == "prefix" else 0 for p in core.PHASES},
        "phase_actual_effort_complete": dict.fromkeys(core.PHASES, True), "control_effort": core.new_effort(),
        "actual_control_effort_substeps": 0, "missing_control_effort_substeps": 0,
        "actual_effort_complete": True, "actual_effort_is_lower_bound": False,
        "planner_attempt_count": 0, "failed_planner_attempts": 0, "planner_decision_count": 0,
        "mathematical_prediction_calls": 0, "mathematical_prediction_calls_complete": True,
        "mathematical_prediction_calls_is_lower_bound": False, "controller_seconds_total": 0., "planner_fallbacks": 0,
        "models_before": None, "models_after": {}, "integration_models_before": {}, "integration_models_after": {}}
    evaluations = {k: {"completed": False, "status": "blocked"} for k in core.KINDS}
    evaluations["calibration_old"] = ev
    results = [{"seed": 0, "reset_seed": 3757552657, "calibration_updates": 0,
        "calibration_completed": {"old": False, "new": False}, "calibration_models": {"old": {}},
        "initial_models": {}, "learned_models": {}, "integration_models": {}, "evaluations": evaluations}]
    sources = {n: (core.ROOT/n).read_bytes() for n in core.REQUIRED_SOURCES}
    metadata = {"schema_version": 1, "split": "development", "seeds": core.SEEDS, "pose": "supine", "joint_index": 0,
        "source_commit": "1"*40, "source_status": "", "source_dirty": False,
        "source_sha256": {n: hashlib.sha256(b).hexdigest() for n, b in sources.items()},
        "protocol": {"path": core.PROTOCOL, "sha256": hashlib.sha256(sources[core.PROTOCOL]).hexdigest()},
        "environment_config": core.ENVIRONMENT, "integration": core.INTEGRATION, "evaluation_prediction_integration": core.INTEGRATION,
        "structures": list(core.STRUCTURES), "factorial": {"calibration_dose": ["old", "new"], "model_structure": list(core.STRUCTURES)},
        "calibration_block_amplitudes_nm": core.CALIBRATION_AMPLITUDES, "prediction_block_amplitudes_nm": core.PREDICTION_AMPLITUDES,
        "gpu": None, "prefix_steps": 100, "calibration_steps": 300, "prediction_steps": 100, "control_steps_per_trial": 200,
        "teacher_calls": 0, "external_demonstration_samples": 0, "policy_parameter_updates": 0,
        "planned_episodes": plans, "planned_episode_count": 27, "maximum_control_steps": 8100,
        "control_calls_attempted": 1, "control_steps": 1, "physics_steps": 3, "model_updates": 0,
        "completed_trials": 0, "terminated_trials": 1, "exception_trials": 0, "blocked_trials": 26,
        "unprocessed_trials": 0, "failed_trials": 1, "skipped_trials": 26, "all_trials_successful": False,
        "complete": False, "archive_status": "interrupted"}
    for n, obj in (("metadata.json", metadata), ("episodes.json", episodes), ("seed_results.json", results)):
        (path/n).write_text(json.dumps(obj), encoding="utf-8")
    with gzip.open(path/"trace.jsonl.gz", "wt", encoding="utf-8") as out:
        out.write(json.dumps(row)+"\n")
    with zipfile.ZipFile(path/"source_snapshot.zip", "w") as out:
        for n, b in sources.items():
            out.writestr(n, b)
    write_manifest(path)
    return path


def test_partial_archived_paid_cost_is_not_success(tmp_path):
    archive = partial_archive(tmp_path/"partial")
    report = core.audit(archive, git_root=None)
    assert report["failed"] == 0, report["violations"]
    assert report["archive"]["budget"]["physics_steps"] == 3
    assert report["archive"]["budget"]["model_updates"] == 0
    assert not report["archive"]["seeds"][0]["evaluations"]["calibration_old"]["eligible"]
    assert not report["development_adoption_gate"]["validated_pass"]
    assert report["execution"]["physical_simulation_calls"] == report["execution"]["model_parameter_updates"] == 0


@pytest.mark.parametrize("fault", ["manifest", "zip", "source_dirty", "plan", "permission", "batch_cost", "native_privilege", "counter"])
def test_archive_tampering_is_rejected_without_hiding_paid_budget(tmp_path, fault):
    archive = partial_archive(tmp_path/"partial")
    metadata = core.load_json(archive/"metadata.json")
    if fault == "manifest":
        (archive/"extra.txt").write_text("not in manifest")
    elif fault == "zip":
        with zipfile.ZipFile(archive/"source_snapshot.zip", "a") as z:
            z.writestr("unexpected.py", b"extra")
        write_manifest(archive)
    elif fault == "native_privilege":
        with gzip.open(archive/"trace.jsonl.gz", "rt", encoding="utf-8") as s:
            row = json.loads(s.readline())
        row["observation_before"]["hidden_mass"] = [1.]
        with gzip.open(archive/"trace.jsonl.gz", "wt", encoding="utf-8") as s:
            s.write(json.dumps(row)+"\n")
        write_manifest(archive)
    else:
        if fault == "source_dirty":
            metadata["source_status"], metadata["source_dirty"] = "M tracked.py", True
        elif fault == "plan":
            metadata["planned_episodes"].pop()
        elif fault == "permission":
            metadata["environment_config"]["torque_limit"] = .6
        elif fault == "batch_cost":
            metadata["physics_steps"] = 81001
        else:
            metadata["physics_steps"] = 4
        (archive/"metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
        write_manifest(archive)
    report = core.audit(archive, git_root=None)
    assert report["failed"] > 0
    assert report["reported_paid_budget_if_replay_incomplete"]["physics_steps"] == metadata["physics_steps"]
    assert not report["development_adoption_gate"]["validated_pass"]


def test_output_guard_and_cli_holdout_rejection_before_trace(tmp_path):
    archive = tmp_path/"heldout"
    archive.mkdir()
    (archive/"metadata.json").write_text(json.dumps({"split": "holdout", "seeds": [20, 21, 22], "pose": "supine", "joint_index": 0}), encoding="utf-8")
    output = tmp_path/"audit.json"
    process = subprocess.run([sys.executable, str(SCRIPT), str(archive), "--output", str(output)], capture_output=True, text=True)
    assert process.returncode == 2 and "development" in process.stderr and not output.exists()
    with pytest.raises(ValueError, match="outside"):
        core.validate_output_path(archive/"audit.json", [archive])
    output.write_text("preserve", encoding="utf-8")
    with pytest.raises(ValueError, match="overwrite"):
        core.validate_output_path(output, [archive])
    assert output.read_text() == "preserve"


def test_phase_actual_missing_remains_lower_bound_even_if_collector_measured_it():
    ev = {"phase_effort": {"calibration": {"requested_absolute_nm_s": .003,
        "requested_squared_nm2_s": .00075, "actual_absolute_nm_s": .003, "actual_squared_nm2_s": .00075}},
        "phase_actual_effort_substeps": {"calibration": 6}, "phase_actual_effort_complete": {"calibration": True}}
    checks = core.Checks()
    report = core.reconcile_effort(ev, "calibration", core.new_effort(), 6, 0,
        [{"phase": "calibration", "requested_torque": [.25]+[0.]*7, "unreturned_physics_steps": 0}], checks, "test")
    assert checks.failed == 0
    assert report["requested_effort_reconstruction_complete"]
    assert report["independent_effort"]["requested_absolute_nm_s"] == .003
    assert report["independent_effort"]["actual_absolute_nm_s"] == 0.
    assert report["actual_effort_is_lower_bound"] and report["unreconstructed_actual_effort_substeps"] == 6


def test_unknown_missing_request_is_not_assigned_zero_effort():
    ev = {"phase_effort": {"control": dict.fromkeys(core.EFFORT_KEYS, .001)},
        "phase_actual_effort_substeps": {"control": 2}, "phase_actual_effort_complete": {"control": True}}
    report = core.reconcile_effort(ev, "control", core.new_effort(), 2, 0, [], core.Checks(), "test")
    assert not report["requested_effort_reconstruction_complete"]
    assert not report["actual_effort_reconstruction_complete"]


def saved_model(state, trainable=False):
    return {**core.model_record(0., state["observed_theta"], state["observed_covariance"]),
        "parameter_fingerprint": core.state_hash(0., state), "update_count": state["updates"], "trainable": trainable}


def update_item(row, state, structure):
    """Build a synthetic logged atomic update without the experiment model."""
    q, v = (row["observation_before"][k][0] for k in ("joint_position", "joint_velocity"))
    u, nv = row["requested_torque"][0], row["observation_after"]["joint_velocity"][0]
    features = core.feature_vector(0., q, v, u, structure)
    prediction = core.predict(state["observed_theta"], 0., q, v, u)
    item = {"model_id": row["calibration_dose"]+"_"+structure, "shared_transition_id": row["shared_transition_id"],
        "phase": "identification", "updated": True, "features": features,
        "observed_next_v_rad_s": nv, "preupdate_prediction": {"next_q_rad": prediction[0], "next_v_rad_s": prediction[1]},
        "preupdate_error_rad_s": nv-prediction[1], "parameter_fingerprint_before": core.state_hash(0., state)}
    state["theta"], state["covariance"] = core.replay_rls(state["theta"], state["covariance"], features, nv)
    state["observed_theta"], state["observed_covariance"] = state["theta"], state["covariance"]
    state["updates"] += 1
    item.update(coefficients_after=state["theta"], covariance_after=state["covariance"], update_count=state["updates"],
        parameter_fingerprint_after=core.state_hash(0., state))
    return item


def dual_failure_archive(path, *, missing_item=False):
    """Linear succeeds twice, hinge once; second endpoint is exception-only."""
    partial_archive(path)
    metadata, episodes, results = [core.load_json(path/n) for n in ("metadata.json", "episodes.json", "seed_results.json")]
    sr, ep = results[0], episodes[0]
    rows = [transition(i, kind="calibration_old", phase="prefix") for i in range(100)]
    states = {s: core.initial_state(s) for s in core.STRUCTURES}
    initial = {"old_"+s: saved_model(state) for s, state in states.items()}
    nominal = saved_model(core.initial_state("linear4"))
    first = transition(100, kind="calibration_old", phase="calibration", u=.125, next_q=.00005, next_v=.0025)
    first["predicted_next_qv"] = {s: core.predict(st["theta"], 0., 0., 0., .125) for s, st in states.items()}
    first["model_update"] = {s: update_item(first, st, s) for s, st in states.items()}
    rows.append(first)
    second = transition(101, kind="calibration_old", phase="calibration", before=first["observation_after"],
        q=.00005, v=.0025, u=.125, next_q=.000125, next_v=.00375)
    second["predicted_next_qv"] = {s: core.predict(st["theta"], 0., .00005, .0025, .125) for s, st in states.items()}
    success = update_item(second, states["linear4"], "linear4")
    second["model_update"] = {} if missing_item else {"linear4": success}
    second["collector_exception"] = {"type": "OSError", "message": "synthetic atomic failure then archive abort"}
    second["partial_model_snapshots"] = {s: saved_model(st, trainable=True) for s, st in states.items()}
    # Match the real best-effort endpoint: no raw substep arrays are returned.
    second["diagnostics"] = {k: second["diagnostics"][k] for k in ("step_id", "physics_steps", "time")}
    second["unreturned_physics_steps"] = 0
    rows.append(second)
    frozen = {"old_"+s: saved_model(st) for s, st in states.items()}
    view = {**nominal, "integration": core.integration_spec(nominal["parameter_fingerprint"]),
        "integration_fingerprint": core.digest(core.integration_spec(nominal["parameter_fingerprint"])), "frozen_view": True}
    limit = 100.*3.141592653589793/180.
    sr.update(reference_q=0., direction=1, selection_record={"joint_index": 0, "joint_position_rad": 0.,
        "lower_limit_rad": -limit, "upper_limit_rad": limit, "positive_room_rad": limit, "negative_room_rad": limit,
        "direction": 1, "rule": "larger distance to the public joint limit; ties choose positive"}, nominal_model=nominal,
        calibration_updates=3, initial_models=initial, learned_models=frozen,
        calibration_models={"old": {s: frozen["old_"+s] for s in core.STRUCTURES}}, integration_models={"nominal_mpc": view})
    ep.update(status="exception", collector_exception=second["collector_exception"], control_calls_attempted=102,
        control_steps=102, physics_steps=1020, risk_telemetry_complete=False)
    ep["phase_budgets"]["prefix"] = {"control_calls_attempted": 100, "control_steps": 100, "physics_steps": 1000}
    ep["phase_budgets"]["calibration"] = {"control_calls_attempted": 2, "control_steps": 2, "physics_steps": 20}
    ev = sr["evaluations"]["calibration_old"]
    ev.update(status="exception", models_after={"nominal": nominal["parameter_fingerprint"], **{n: m["parameter_fingerprint"] for n, m in frozen.items()}},
        integration_models_after={"nominal_mpc": view["integration_fingerprint"]})
    ev["phase_effort"]["calibration"] = {"requested_absolute_nm_s": .005, "requested_squared_nm2_s": .000625,
        "actual_absolute_nm_s": .005, "actual_squared_nm2_s": .000625}
    ev["phase_actual_effort_substeps"].update(prefix=1000, calibration=20)
    metadata.update(control_calls_attempted=102, control_steps=102, physics_steps=1020, model_updates=3,
        terminated_trials=0, exception_trials=1, archive_status="failed")
    for n, obj in (("metadata.json", metadata), ("episodes.json", episodes), ("seed_results.json", results)):
        (path/n).write_text(json.dumps(obj), encoding="utf-8")
    with gzip.open(path/"trace.jsonl.gz", "wt", encoding="utf-8") as out:
        for r in rows:
            out.write(json.dumps(r)+"\n")
    write_manifest(path)
    return path


@pytest.mark.parametrize("missing_item", [False, True])
def test_single_model_failure_keeps_distinct_counts_and_exception_snapshot_cost(tmp_path, missing_item):
    archive = dual_failure_archive(tmp_path/"dual", missing_item=missing_item)
    report = core.audit(archive, git_root=None)
    assert report["failed"] == 0, report["violations"]
    seed = report["archive"]["seeds"][0]
    assert seed["models"]["old_linear4"]["replayed_updates"] == 2
    assert seed["models"]["old_hinge5"]["replayed_updates"] == 1
    assert seed["model_updates"] == seed["independently_replayed_updates"] == 3
    assert seed["exception_snapshot_replayed_updates"] == 1
    phase = seed["evaluations"]["calibration_old"]["phase_effort"]["calibration"]
    assert phase["independent_effort"]["requested_absolute_nm_s"] == .005
    assert phase["independent_effort"]["actual_absolute_nm_s"] == .0025
    assert phase["actual_effort_is_lower_bound"]
    assert phase["collector_reported_actual_measured_substeps"] == 20
    assert phase["unreconstructed_actual_effort_substeps"] == 10
    assert not seed["evaluations"]["calibration_old"]["eligible"]


@pytest.mark.parametrize("fault", ["model_id", "shared_id", "hash", "theta", "P", "partial", "count"])
def test_dual_update_tampering_is_rejected(tmp_path, fault):
    archive = dual_failure_archive(tmp_path/"dual")
    with gzip.open(archive/"trace.jsonl.gz", "rt", encoding="utf-8") as out:
        rows = [json.loads(line) for line in out]
    item = rows[-1]["model_update"]["linear4"]
    if fault == "model_id":
        item["model_id"] = "old_hinge5"
    elif fault == "shared_id":
        item["shared_transition_id"] += "bad"
    elif fault == "hash":
        item["parameter_fingerprint_before"] = "0"*64
    elif fault == "theta":
        item["coefficients_after"][2] += .001
    elif fault == "P":
        item["covariance_after"][0][0] += .001
    elif fault == "partial":
        rows[-1]["diagnostics"]["physics_steps"] -= 7
    else:
        item["update_count"] += 1
    with gzip.open(archive/"trace.jsonl.gz", "wt", encoding="utf-8") as out:
        for row in rows:
            out.write(json.dumps(row)+"\n")
    write_manifest(archive)
    report = core.audit(archive, git_root=None)
    assert report["failed"] > 0 and report["reported_paid_budget_if_replay_incomplete"]["model_updates"] == 3


def test_failed_calibration_cannot_silently_enable_learned_control(tmp_path):
    archive = partial_archive(tmp_path/"partial")
    episodes = core.load_json(archive/"episodes.json")
    next(ep for ep in episodes if ep["trial_id"] == "seed0_old_linear4_mpc")["status"] = "exception"
    (archive/"episodes.json").write_text(json.dumps(episodes), encoding="utf-8")
    write_manifest(archive)
    report = core.audit(archive, git_root=None)
    assert any(v["check"] == "failed_calibration_dependents_blocked" for v in report["violations"])


def test_reference_holdout_is_refused_before_any_trace_read(tmp_path, monkeypatch):
    archive = partial_archive(tmp_path/"partial")
    reference = tmp_path/"holdout"
    reference.mkdir()
    (reference/"metadata.json").write_text(json.dumps({"split": "holdout", "seeds": [20, 21, 22], "pose": "supine", "joint_index": 0}), encoding="utf-8")
    def forbidden(*args, **kwargs):
        raise AssertionError("trace should not be opened")
    monkeypatch.setattr(core.gzip, "open", forbidden)
    report = core.audit(archive, reference=reference, git_root=None)
    assert report["failed"] == 1 and report["archive"] is None


def test_audit_has_no_imports_of_simulator_numerical_or_experiment_code():
    import ast
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.append(node.module)
    assert all(not n.startswith(("mujoco", "numpy", "developmental_physics", "torch", "scipy")) for n in names)


def complete_arithmetic_archive(path):
    """Full protocol shape on declared toy algebra, zero physical queries.

    The fixture's next-v algebra is explicit and does not import the experiment.
    Hand-gain tests separately establish RLS arithmetic; this checks orchestration
    and the complete archived schema rather than asserting a physical outcome.
    """
    partial_archive(path)
    metadata, episodes = [core.load_json(path/n) for n in ("metadata.json", "episodes.json")]
    results, all_rows = [], []
    limit = 100.*3.141592653589793/180.
    nominal = saved_model(core.initial_state("linear4"))
    nominal_view = {**nominal, "integration": core.integration_spec(nominal["parameter_fingerprint"]),
        "integration_fingerprint": core.digest(core.integration_spec(nominal["parameter_fingerprint"])), "frozen_view": True}
    for seed in core.SEEDS:
        sr = {"seed": seed, "reset_seed": [3757552657, 1641411168, 2001025171][seed], "reference_q": 0., "direction": 1,
            "selection_record": {"joint_index": 0, "joint_position_rad": 0., "lower_limit_rad": -limit,
                "upper_limit_rad": limit, "positive_room_rad": limit, "negative_room_rad": limit, "direction": 1,
                "rule": "larger distance to the public joint limit; ties choose positive"}, "nominal_model": nominal,
            "initial_models": {}, "learned_models": {}, "calibration_models": {}, "integration_models": {},
            "calibration_completed": {"old": True, "new": True}, "calibration_updates": 1200, "evaluations": {}}
        hashes, views, fitted = {}, {}, {}
        for kind in core.KINDS:
            ep = next(e for e in episodes if e["trial_id"] == f"seed{seed}_{kind}")
            is_cal, q, v = kind.startswith("calibration_"), 0., 0.
            previous, previous_torque = native(), 0.
            before_hashes, before_views = (None if is_cal else dict(hashes)), dict(views)
            effort = {p: core.new_effort() for p in core.PHASES}
            q_errors, q_scores, v_scores = [], {}, {}
            fallbacks = saturated = math_calls = 0
            calibrators = {}
            for index in range(100+core.duration(kind)):
                phase = "prefix" if index < 100 else ("calibration" if is_cal else "prediction" if kind.startswith("prediction_") else "control")
                if index == 100:
                    if "nominal" not in hashes:
                        hashes["nominal"] = nominal["parameter_fingerprint"]
                        views["nominal_mpc"] = nominal_view["integration_fingerprint"]
                        fitted["nominal_mpc"] = core.INITIAL["linear4"]
                        sr["integration_models"]["nominal_mpc"] = nominal_view
                    if is_cal:
                        calibrators = {s: core.initial_state(s) for s in core.STRUCTURES}
                        for s, state in calibrators.items():
                            name = kind.split("_")[1]+"_"+s
                            sr["initial_models"][name] = saved_model(state)
                            hashes[name] = core.state_hash(0., state)
                    else:
                        before_hashes, before_views = dict(hashes), dict(views)
                u, target, decision = 0., None, None
                active = index-100
                if index >= 100 and phase in ("calibration", "prediction"):
                    width, ends = (30, (5, 15, 20)) if is_cal else (20, (7, 10, 17))
                    amplitudes = core.CALIBRATION_AMPLITUDES[kind.split("_")[1]] if is_cal else core.PREDICTION_AMPLITUDES[kind.split("_")[1]]
                    slot, amplitude = active % width, amplitudes[active//width]
                    u = amplitude if slot < ends[0] else -amplitude if ends[1] <= slot < ends[2] else 0.
                elif phase == "control":
                    target = .04 if active < 100 else .08
                    decision = core.replay_mpc(fitted[kind], 0., q, v, target, previous_torque, [-limit, limit])
                    u = decision["torque"]
                    fallbacks += int(decision["fallback"])
                    saturated += int(abs(u) == .5)
                    math_calls += decision["mathematical_prediction_calls"]
                hinge = (1. if u > 0 else -1. if u < 0 else 0.)*max(abs(u)-.25, 0.)
                nv, nq = .5*v+.02*u+.08*hinge, None
                nq = q+.02*nv
                row = transition(index, kind=kind, phase=phase, q=q, v=v, u=u, next_q=nq, next_v=nv, before=previous)
                row.update(seed=seed, trial_id=ep["trial_id"], shared_transition_id=ep["trial_id"]+":"+str(index), target_q=target, planner_decision=decision)
                if index >= 100:
                    predicted = {s: core.predict(st["observed_theta"], 0., q, v, u) for s, st in calibrators.items()} if is_cal else {
                        n: core.predict(t, 0., q, v, u) for n, t in fitted.items()}
                    if not is_cal:
                        predicted["persistence"] = (q+.02*v, v)
                    row["predicted_next_qv"] = predicted
                    if is_cal:
                        row["model_update"] = {s: update_item(row, st, s) for s, st in calibrators.items()}
                    for n, (pq, pv) in predicted.items():
                        q_scores.setdefault(n, []).append(nq-pq)
                        v_scores.setdefault(n, []).append(nv-pv)
                if target is not None:
                    q_errors.append(nq-target)
                for k, value in zip(core.EFFORT_KEYS, (abs(u)*.02, u*u*.02, abs(u)*.02, u*u*.02)):
                    effort[phase][k] += value
                previous, previous_torque, q, v = row["observation_after"], u, nq, nv
                all_rows.append(row)
            if is_cal:
                dose = kind.split("_")[1]
                sr["calibration_models"][dose] = {}
                for structure, state in calibrators.items():
                    name, saved = dose+"_"+structure, saved_model(state)
                    hashes[name] = saved["parameter_fingerprint"]
                    sr["learned_models"][name] = saved
                    sr["calibration_models"][dose][structure] = saved
                    view = {**saved, "integration": core.integration_spec(hashes[name]),
                        "integration_fingerprint": core.digest(core.integration_spec(hashes[name])), "frozen_view": True}
                    views[name+"_mpc"] = view["integration_fingerprint"]
                    fitted[name+"_mpc"] = saved["coefficients"]
                    sr["integration_models"][name+"_mpc"] = view
            ep.update(status="completed", reason=None, control_calls_attempted=100+core.duration(kind),
                control_steps=100+core.duration(kind), physics_steps=(100+core.duration(kind))*10,
                risk_telemetry_complete=True, unreturned_physics_steps=0,
                environment_fingerprint_before="1"*64, environment_fingerprint_after="1"*64)
            ep["phase_budgets"]["prefix"] = {"control_calls_attempted": 100, "control_steps": 100, "physics_steps": 1000}
            active_phase = "calibration" if is_cal else "prediction" if kind.startswith("prediction_") else "control"
            ep["phase_budgets"][active_phase] = {"control_calls_attempted": core.duration(kind), "control_steps": core.duration(kind), "physics_steps": core.duration(kind)*10}
            planner_spec = None
            if kind in core.CONTROL_KINDS:
                fp = hashes["nominal" if kind == "nominal_mpc" else kind.removesuffix("_mpc")]
                planner_spec = {"config": core.MPC_CONFIG, "qref_rad": 0., "joint_range_rad": [-limit, limit],
                    "candidates_nm": [-.5+i*.125 for i in range(9)], "physical_queries": 0,
                    "forecast_bounds_rad": [-.15, .15], "target_bounds_rad": [-.15, .15],
                    "integration": core.integration_spec(fp), "integration_fingerprint": views[kind]}
            sr["evaluations"][kind] = {"completed": True, "status": "completed", "tracking_rmse_rad": core.rmse(q_errors),
                "metric_control_step_count": len(q_errors), "velocity_prediction_rmse": {n: core.rmse(vs) for n, vs in v_scores.items()},
                "position_prediction_rmse": {n: core.rmse(qs) for n, qs in q_scores.items()}, "saturated_control_steps": saturated,
                "control_effort": effort["control"], "phase_effort": effort,
                "phase_actual_effort_substeps": {p: b["physics_steps"] for p, b in ep["phase_budgets"].items()},
                "phase_actual_effort_complete": dict.fromkeys(core.PHASES, True),
                "actual_effort_complete": True, "actual_effort_is_lower_bound": False,
                "actual_control_effort_substeps": ep["phase_budgets"]["control"]["physics_steps"], "missing_control_effort_substeps": 0,
                "mathematical_prediction_calls": math_calls, "mathematical_prediction_calls_complete": True,
                "mathematical_prediction_calls_is_lower_bound": False, "planner_attempt_count": len(q_errors),
                "failed_planner_attempts": 0, "planner_decision_count": len(q_errors), "planner_fallbacks": fallbacks,
                "controller_seconds_total": len(q_errors)*.001, "models_before": before_hashes, "models_after": dict(hashes),
                "integration_models_before": before_views, "integration_models_after": dict(views), "planner_spec": planner_spec}
        results.append(sr)
    metadata.update(control_calls_attempted=8100, control_steps=8100, physics_steps=81000, model_updates=3600,
        completed_trials=27, terminated_trials=0, exception_trials=0, blocked_trials=0, failed_trials=0, skipped_trials=0,
        all_trials_successful=True, complete=True, archive_status="complete")
    for n, obj in (("metadata.json", metadata), ("episodes.json", episodes), ("seed_results.json", results)):
        (path/n).write_text(json.dumps(obj), encoding="utf-8")
    with gzip.open(path/"trace.jsonl.gz", "wt", encoding="utf-8") as out:
        for r in all_rows:
            out.write(json.dumps(r)+"\n")
    write_manifest(path)
    return path


def test_full_arithmetic_archive_reconstructs_all_models_and_fixed_8100_budget(tmp_path):
    archive = complete_arithmetic_archive(tmp_path/"complete")
    report = core.audit(archive, git_root=None)
    assert report["failed"] == 0, report["violations"]
    assert report["archive"]["budget"] == {"control_calls_attempted": 8100, "control_steps": 8100, "physics_steps": 81000, "model_updates": 3600}
    assert report["archive"]["physical_calibration_transfers"] == 1800
    for seed in report["archive"]["seeds"]:
        assert seed["complete"] and seed["model_updates"] == seed["independently_replayed_updates"] == 1200
        assert seed["paired_prefix_first90"]
        assert all(m["reported_updates"] == m["replayed_updates"] == 300 for m in seed["models"].values())
        for kind in core.KINDS:
            e = seed["evaluations"][kind]
            assert e["eligible"] and e["actual_effort_complete"]
            assert all(p["actual_effort_reconstruction_complete"] for p in e["phase_effort"].values())
            assert len(e["free_rollouts"]) == 4
            assert len(e["free_rollouts"][0]["predictors"]) == 6
        full_bins = seed["evaluations"]["prediction_full"]["conditional_metrics"]
        assert full_bins["abs_u=0.375"]["returned_transition_count"] == 28
        assert full_bins["abs_u=0.0"]["returned_transition_count"] == 30
        for name in ("old_linear4_mpc", "old_hinge5_mpc", "new_linear4_mpc", "new_hinge5_mpc"):
            assert seed["evaluations"][name]["state_coverage"]["calibration_native_samples"] == 300
    assert report["four_group_factorial_summary"]["complete_four_group_three_seed_matrix"]
    assert not report["development_adoption_gate"]["validated_pass"]  # No Git verification/historical anchor in synthetic fixture.
