"""C2-C pure arithmetic/archival fixtures; no physics/fitting/heldout calls."""
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
SCRIPT = Path(__file__).with_name("audit_local_coverage.py")
if not SCRIPT.is_file():
    SCRIPT = Path(__file__).resolve().parents[1]/"scripts/audit_local_coverage.py"
spec = importlib.util.spec_from_file_location("coverage_audit_core", SCRIPT)
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


def transition(index, *, kind="short_mpc", phase="control", q=0., v=0., u=0., next_q=0., next_v=0., before=None, n=10, terminated=False):
    request, observation = [u]+[0.]*7, native(next_q, next_v, u)
    physics = index*10+n
    d = {"executed_substeps": n, "terminated": terminated, "reason": "synthetic_env_stop" if terminated else None, "step_id": index+1, "physics_steps": physics, "time": physics*.002,
        "requested_torque": request, "accepted_torque": request, "applied_torque": request,
        "applied_torque_history": [request.copy() for _ in range(n)], "guarded_substeps": 0,
        "substep_ground_normal_forces": [0.]*n, "substep_kinetic_energies": [0.]*n,
        "substep_minimum_contact_distances": [0.]*n, "peak_substep_ground_normal_force": 0.,
        "ground_normal_impulse_ns": 0., "peak_substep_kinetic_energy": 0., "minimum_substep_contact_distance": 0.}
    plan = next(p for p in core.planned_matrix() if p["trial_id"] == "seed0_"+kind)
    return {**{k: plan[k] for k in ("trial_id", "seed", "kind", "model_scope", "calibration_dose", "calibration_schedule", "model_structure", "integration")},
        "step_index": index, "phase": phase, "shared_transition_id": "seed0_"+kind+":"+str(index),
        "observation_before": native(q, v) if before is None else before, "observation_after": observation,
        "requested_torque": request, "target_q": None, "predicted_next_qv": {}, "model_update": None, "planner_decision": None,
        "study_abort": None, "partial_interval_target_error_rad": None, "diagnostics": d, "qpos": [0., 0., .5, 1., 0., 0., 0.]+observation["joint_position"],
        "qvel": [0.]*6+observation["joint_velocity"]}


@pytest.mark.parametrize("steps,expected", [(100, [100, 96, 86, 51]), (200, [200, 196, 186, 151]), (300, [300, 296, 286, 251])])
def test_legal_denominators_all_horizons(steps, expected):
    indexed = {i: transition(i) for i in range(100, 100+steps)}
    for h, count in zip(core.HORIZONS, expected):
        d = core.window_denominators(indexed, steps, h)
        assert d["expected_windows_from_planned_active_duration"] == d["valid_physical_windows"] == count
        assert d["excluded_windows"] == 0


@pytest.mark.parametrize("fault,reason", [("missing", "missing_control_row"), ("partial", "partial_physics_interval"),
    ("stop", "continued_after_study_or_environment_stop"), ("phase", "crossed_phase_or_trial_boundary"),
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
        study_abort=None, environment_terminated=True, environment_stop_reason="synthetic_stop", environment_fingerprint_before="1"*64, environment_fingerprint_after="1"*64)
    episodes[0]["phase_budgets"]["prefix"] = {"control_calls_attempted": 1, "control_steps": 1, "physics_steps": 3}
    row = transition(0, kind="calibration_short", phase="prefix", n=3, terminated=True)
    row["diagnostics"]["reason"] = "synthetic_stop"
    ev = {"completed": False, "status": "terminated", "study_abort": None, "environment_terminated": True, "environment_stop_reason": "synthetic_stop", "partial_interval_target_errors_rad": [], "partial_interval_target_error_count": 0, "tracking_rmse_rad": None,
        "position_prediction_rmse": {}, "velocity_prediction_rmse": {}, "metric_prediction_step_count": {}, "metric_control_step_count": 0,
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
    evaluations["calibration_short"] = ev
    results = [{"seed": 0, "reset_seed": 3757552657, "calibration_updates": 0,
        "calibration_completed": {"short": False, "reordered": False}, "calibration_models": {"short": {}},
        "initial_models": {}, "learned_models": {}, "integration_models": {}, "evaluations": evaluations}]
    sources = {n: (core.ROOT/n).read_bytes() for n in core.REQUIRED_SOURCES}
    metadata = {"schema_version": 1, "split": "development", "seeds": core.SEEDS, "pose": "supine", "joint_index": 0,
        "source_commit": "1"*40, "source_status": "", "source_dirty": False,
        "source_sha256": {n: hashlib.sha256(b).hexdigest() for n, b in sources.items()},
        "protocol": {"path": core.PROTOCOL, "sha256": hashlib.sha256(sources[core.PROTOCOL]).hexdigest()},
        "environment_config": core.ENVIRONMENT, "integration": core.INTEGRATION, "evaluation_prediction_integration": core.INTEGRATION,
        "structures": ["hinge5"], "calibration_dose": "old", "model_structure": "hinge5", "calibration_schedules": ["short", "reordered"],
        "comparison": {"calibration_schedule": ["short", "reordered"], "single_fixed_dose": "old", "single_fixed_structure": "hinge5"},
        "study_abort_spec": core.study_abort_spec(), "calibration_schedule_definition": core.calibration_schedule_spec(),
        "wall_seconds": 1., "cpu_seconds": 1., "cpu_seconds_scope": "Current process only; same timer-start/checkpoint scope as wall_seconds; excludes imports, initial source snapshot and setup before timers",
        "calibration_block_amplitudes_nm": core.CALIBRATION_AMPLITUDES, "prediction_block_amplitudes_nm": core.PREDICTION_AMPLITUDES,
        "gpu": None, "prefix_steps": 100, "calibration_steps": 300, "prediction_steps": 100, "control_steps_per_trial": 200,
        "teacher_calls": 0, "external_demonstration_samples": 0, "policy_parameter_updates": 0,
        "planned_episodes": plans, "planned_episode_count": 21, "maximum_control_steps": 6300,
        "control_calls_attempted": 1, "control_steps": 1, "physics_steps": 3, "model_updates": 0,
        "completed_trials": 0, "terminated_trials": 1, "exception_trials": 0, "blocked_trials": 20,
        "unprocessed_trials": 0, "failed_trials": 1, "skipped_trials": 20, "all_trials_successful": False,
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


def saved_model(state, trainable=False):
    return {**core.model_record(0., state["observed_theta"], state["observed_covariance"]),
        "parameter_fingerprint": core.state_hash(0., state), "update_count": state["updates"], "trainable": trainable}


def update_item(row, state, structure):
    """Build a synthetic logged atomic update without the experiment model."""
    q, v = (row["observation_before"][k][0] for k in ("joint_position", "joint_velocity"))
    u, nv = row["requested_torque"][0], row["observation_after"]["joint_velocity"][0]
    features = core.feature_vector(0., q, v, u, structure)
    prediction = core.predict(state["observed_theta"], 0., q, v, u)
    item = {"model_id": row["calibration_schedule"]+"_"+structure, "shared_transition_id": row["shared_transition_id"],
        "phase": "identification", "updated": True, "features": features,
        "observed_next_v_rad_s": nv, "preupdate_prediction": {"next_q_rad": prediction[0], "next_v_rad_s": prediction[1]},
        "preupdate_error_rad_s": nv-prediction[1], "parameter_fingerprint_before": core.state_hash(0., state)}
    state["theta"], state["covariance"] = core.replay_rls(state["theta"], state["covariance"], features, nv)
    state["observed_theta"], state["observed_covariance"] = state["theta"], state["covariance"]
    state["updates"] += 1
    item.update(coefficients_after=state["theta"], covariance_after=state["covariance"], update_count=state["updates"],
        parameter_fingerprint_after=core.state_hash(0., state))
    return item


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
            "calibration_completed": {"short": True, "reordered": True}, "calibration_updates": 600, "evaluations": {}}
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
                        calibrators = {s: core.initial_state(s) for s in ("hinge5",)}
                        for s, state in calibrators.items():
                            name = kind.split("_")[1]+"_"+s
                            sr["initial_models"][name] = saved_model(state)
                            hashes[name] = core.state_hash(0., state)
                    else:
                        before_hashes, before_views = dict(hashes), dict(views)
                u, target, decision = 0., None, None
                active = index-100
                if index >= 100 and phase in ("calibration", "prediction"):
                    if is_cal:
                        u = core.calibration_request(kind.split("_")[1], active, 1)
                    else:
                        slot, amplitude = active % 20, core.PREDICTION_AMPLITUDES[kind.split("_")[1]][active//20]
                        u = amplitude if slot < 7 else -amplitude if 10 <= slot < 17 else 0.
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
                    views[dose+"_mpc"] = view["integration_fingerprint"]
                    fitted[dose+"_mpc"] = saved["coefficients"]
                    sr["integration_models"][dose+"_mpc"] = view
            ep.update(status="completed", reason=None, control_calls_attempted=100+core.duration(kind),
                control_steps=100+core.duration(kind), physics_steps=(100+core.duration(kind))*10,
                risk_telemetry_complete=True, unreturned_physics_steps=0,
                study_abort=None, environment_terminated=False, environment_stop_reason=None, environment_fingerprint_before="1"*64, environment_fingerprint_after="1"*64)
            ep["phase_budgets"]["prefix"] = {"control_calls_attempted": 100, "control_steps": 100, "physics_steps": 1000}
            active_phase = "calibration" if is_cal else "prediction" if kind.startswith("prediction_") else "control"
            ep["phase_budgets"][active_phase] = {"control_calls_attempted": core.duration(kind), "control_steps": core.duration(kind), "physics_steps": core.duration(kind)*10}
            planner_spec = None
            if kind in core.CONTROL_KINDS:
                fp = hashes["nominal" if kind == "nominal_mpc" else kind.removesuffix("_mpc")+"_hinge5"]
                planner_spec = {"config": core.MPC_CONFIG, "qref_rad": 0., "joint_range_rad": [-limit, limit],
                    "candidates_nm": [-.5+i*.125 for i in range(9)], "physical_queries": 0,
                    "forecast_bounds_rad": [-.15, .15], "target_bounds_rad": [-.15, .15],
                    "integration": core.integration_spec(fp), "integration_fingerprint": views[kind]}
            sr["evaluations"][kind] = {"completed": True, "status": "completed", "study_abort": None, "environment_terminated": False, "environment_stop_reason": None, "partial_interval_target_errors_rad": [], "partial_interval_target_error_count": 0, "tracking_rmse_rad": core.rmse(q_errors),
                "metric_control_step_count": len(q_errors), "metric_prediction_step_count": {n: len(vs) for n, vs in v_scores.items()}, "velocity_prediction_rmse": {n: core.rmse(vs) for n, vs in v_scores.items()},
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
    metadata.update(control_calls_attempted=6300, control_steps=6300, physics_steps=63000, model_updates=1800,
        completed_trials=21, terminated_trials=0, exception_trials=0, blocked_trials=0, failed_trials=0, skipped_trials=0,
        all_trials_successful=True, complete=True, archive_status="complete")
    for n, obj in (("metadata.json", metadata), ("episodes.json", episodes), ("seed_results.json", results)):
        (path/n).write_text(json.dumps(obj), encoding="utf-8")
    with gzip.open(path/"trace.jsonl.gz", "wt", encoding="utf-8") as out:
        for r in all_rows:
            out.write(json.dumps(r)+"\n")
    write_manifest(path)
    return path


def test_full_arithmetic_archive_reconstructs_all_models_and_fixed_6300_budget(tmp_path):
    archive = complete_arithmetic_archive(tmp_path/"complete")
    report = core.audit(archive, git_root=None)
    assert report["failed"] == 0, report["violations"]
    assert report["archive"]["budget"] == {"control_calls_attempted": 6300, "control_steps": 6300, "physics_steps": 63000, "model_updates": 1800}
    assert report["archive"]["physical_calibration_transfers"] == 1800
    for seed in report["archive"]["seeds"]:
        assert seed["complete"] and seed["model_updates"] == seed["independently_replayed_updates"] == 600
        assert seed["paired_prefix_first5"]
        assert all(m["reported_updates"] == m["replayed_updates"] == 300 for m in seed["models"].values())
        for kind in core.KINDS:
            e = seed["evaluations"][kind]
            assert e["eligible"] and e["actual_effort_complete"]
            assert all(p["actual_effort_reconstruction_complete"] for p in e["phase_effort"].values())
            assert len(e["free_rollouts"]) == 4
            assert len(e["free_rollouts"][0]["predictors"]) == 4
        full_bins = seed["evaluations"]["prediction_full"]["conditional_metrics"]
        assert full_bins["abs_u=0.375"]["returned_transition_count"] == 28
        assert full_bins["abs_u=0.0"]["returned_transition_count"] == 30
        for name in ("short_mpc", "reordered_mpc", "nominal_mpc"):
            assert all(c["calibration_native_samples"] == 300 for c in seed["evaluations"][name]["state_coverage"].values())
    assert not report["development_adoption_gate"]["validated_pass"]  # No Git verification/historical anchor in synthetic fixture.


@pytest.mark.parametrize("phase", core.PHASES)
@pytest.mark.parametrize("q,v,position,velocity", [(0., 0., False, False), (.12, 0., True, False), (-.12, 0., True, False), (0., 1., False, True), (0., -1., False, True), (.12, 1., True, True), (.119999999, .999999999, False, False)])
def test_native_research_monitor_every_active_endpoint_and_prefix_exception(phase, q, v, position, velocity):
    c = core.study_condition(0., q, v, phase)
    assert c["applicable"] == (phase != "prefix")
    assert c["triggered"] == (phase != "prefix" and (position or velocity))
    assert c["position_triggered"] == (phase != "prefix" and position)
    assert c["velocity_triggered"] == (phase != "prefix" and velocity)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), True])
def test_nonfinite_active_cannot_escape_native_monitor(bad):
    with pytest.raises(ValueError):
        core.study_condition(0., bad, 0., "control")


def monitor_payload(q, v, index, phase, qref=0.):
    triggers = ([] if abs(q-qref) < .12 else ["absolute_q_minus_qref_rad"])+([] if abs(v) < 1. else ["absolute_velocity_rad_s"])
    return None if not triggers else {"type": "StudyAbort", "message": "predeclared native active envelope reached", "stage": "endpoint",
        "triggers": triggers, "q_rad": q, "qref_rad": qref, "q_minus_qref_rad": q-qref, "velocity_rad_s": v,
        "thresholds": {"absolute_q_minus_qref_rad": .12, "absolute_velocity_rad_s": 1.}, "feedback_action": None, "phase": phase, "step_index": index}


@pytest.mark.parametrize("fault", ["missing", "false_positive", "feedback", "threshold", "trigger", "index"])
def test_study_raw_flags_cannot_replace_independent_native_recomputation(fault):
    r = transition(100, next_q=.12, next_v=1.)
    r["study_abort"] = monitor_payload(.12, 1., 100, "control")
    if fault == "missing":
        r["study_abort"] = None
    elif fault == "false_positive":
        r["observation_after"] = native(.01, .1)
    elif fault == "feedback":
        r["study_abort"]["feedback_action"] = "return to target"
    elif fault == "threshold":
        r["study_abort"]["thresholds"]["absolute_q_minus_qref_rad"] = .15
    elif fault == "trigger":
        r["study_abort"]["triggers"].pop()
    else:
        r["study_abort"]["step_index"] = 99
    checks = core.Checks()
    core.normalize_study_row(r, 0., checks, "toy")
    assert checks.failed > 0


@pytest.mark.parametrize("study,env", [(True, False), (False, True), (True, True)])
def test_full_terminal_window_counts_study_environment_overlap_separately(study, env):
    rows = {i: transition(i) for i in range(100, 105)}
    rows[104].update(audited_study_abort_triggered=study)
    rows[104]["diagnostics"]["terminated"] = env
    d = core.window_denominators(rows, 5, 5)
    assert d["valid_physical_windows"] == d["valid_windows_ending_in_termination"] == 1
    assert d["valid_windows_ending_in_study_abort"] == int(study)
    assert d["valid_windows_ending_in_environment_termination"] == int(env)
    assert d["valid_windows_ending_in_both_stop_conditions"] == int(study and env)
    rows[104]["diagnostics"]["executed_substeps"] = 3
    assert core.window_denominators(rows, 5, 5)["valid_physical_windows"] == 0


def test_cannot_continue_after_native_study_stop_even_when_environment_is_live():
    rows = {i: transition(i) for i in range(100, 105)}
    rows[101]["audited_study_abort_triggered"] = True
    assert core.valid_window(rows, 100, 5)[1] == "continued_after_study_or_environment_stop"


def test_schedule_histogram_effort_and_common_initial_requests():
    sequences = {name: [core.calibration_request(name, k, 1) for k in range(300)] for name in ("short", "reordered")}
    from collections import Counter
    assert Counter(sequences["short"]) == Counter(sequences["reordered"]) == {0.: 200, .125: 20, -.125: 20, .25: 15, -.25: 15, .5: 15, -.5: 15}
    assert sequences["short"][:5] == sequences["reordered"][:5]
    for name, switches in (("short", 40), ("reordered", 22)):
        seq = sequences[name]
        assert sum(abs(u) for u in seq)*.02 == pytest.approx(.55)
        assert sum(u*u for u in seq)*.02 == pytest.approx(.20)
        assert sum(seq)*.02 == pytest.approx(0.)
        assert sum(a != b for a, b in zip([0.]+seq[:-1], seq)) == switches
    plans = core.planned_matrix()
    assert len(plans) == 21 and sum(p["maximum_control_steps"] for p in plans) == 6300


def support(q=10, v=20, union=None):
    union = max(q, v) if union is None else union
    return {"available": True, "calibration_native_samples": 300, "control_native_samples": 200,
        "q_outside_count": q, "v_outside_count": v, "either_outside_count": union,
        "q_outside_fraction": q/200., "v_outside_fraction": v/200., "either_outside_fraction": union/200.}


def gate_fixture(tracking=(1., 1., 1.), candidate=(.9, .9, .9), effort=1.):
    rows = []
    for seed, a, b in zip(core.SEEDS, tracking, candidate):
        ev = {kind: {"eligible": True, "completed": True, "status": "completed", "study_aborted": False, "environment_terminated": False} for kind in core.KINDS}
        for kind in core.CONTROL_KINDS:
            ev[kind].update(actual_effort_complete=True, tracking_rmse_rad=a if kind == "short_mpc" else b,
                control_effort=dict.fromkeys(core.EFFORT_KEYS[2:], 1. if kind == "short_mpc" else effort),
                state_coverage={"short": support(20, 30), "reordered": support(10, 20)})
        for kind in ("prediction_low", "prediction_full"):
            ev[kind]["velocity_prediction_rmse"] = {"short_mpc": 1., "reordered_mpc": .9}
        rows.append({"seed": seed, "evaluations": ev})
    return rows


def test_predeclared_independent_gates_adopt_single_global_reordered():
    gate = core.adoption_gate(gate_fixture())
    assert gate["passed"] and gate["selected_candidate"] == "reordered"
    assert gate["coverage_gate"]["passed"] and gate["performance_gate"]["passed"]


@pytest.mark.parametrize("kind", ["prediction_low", "prediction_full", "nominal_mpc"])
def test_prediction_or_nominal_failure_preserves_independent_coverage_but_denies_performance(kind):
    rows = gate_fixture()
    rows[0]["evaluations"][kind].update(completed=False, status="terminated", study_aborted=True, eligible=False)
    gate = core.adoption_gate(rows)
    assert gate["coverage_gate"]["passed"]
    assert not gate["performance_gate"]["passed"] and gate["selected_candidate"] == "short"


@pytest.mark.parametrize("kind", ["calibration_short", "calibration_reordered", "short_mpc", "reordered_mpc"])
def test_any_coverage_support_trial_failure_denies_coverage_and_adoption(kind):
    rows = gate_fixture()
    rows[0]["evaluations"][kind].update(completed=False, status="terminated", study_aborted=True, eligible=False)
    assert not core.coverage_gate(rows)["passed"]
    assert core.adoption_gate(rows)["selected_candidate"] == "short"


@pytest.mark.parametrize("trajectory", ["short_mpc", "reordered_mpc"])
@pytest.mark.parametrize("fault", ["q_threshold", "q_vs_short", "v_vs_short", "short_partial", "candidate_partial", "bad_fraction", "bad_union"])
def test_coverage_requires_same_trajectory_comparison_with_complete_support(trajectory, fault):
    rows = gate_fixture()
    cell = rows[0]["evaluations"][trajectory]["state_coverage"]
    if fault == "q_threshold":
        cell["short"] = support(100, 100)
        cell["reordered"] = support(21, 20)
    elif fault == "q_vs_short":
        cell["short"] = support(9, 30)
    elif fault == "v_vs_short":
        cell["short"] = support(20, 19)
    elif fault == "short_partial":
        cell["short"]["calibration_native_samples"] = 299
    elif fault == "candidate_partial":
        cell["reordered"]["control_native_samples"] = 199
    elif fault == "bad_fraction":
        cell["reordered"]["q_outside_fraction"] = 0.
    else:
        cell["reordered"]["either_outside_count"] = 0
        cell["reordered"]["either_outside_fraction"] = 0.
    assert not core.coverage_gate(rows)["passed"]


def test_ten_percent_coverage_equality_is_exactly_accepted():
    rows = gate_fixture()
    for r in rows:
        for kind in ("short_mpc", "reordered_mpc"):
            r["evaluations"][kind]["state_coverage"]["reordered"] = support(20, 30)
    assert core.coverage_gate(rows)["passed"]


@pytest.mark.parametrize("fault", ["prediction_low", "prediction_full", "tracking", "actual_abs", "actual_square", "missing_actual", "nonfinite", "negative", "duplicate", "missing"])
def test_each_failed_performance_condition_retains_short(fault):
    rows = gate_fixture()
    trial = rows[0]["evaluations"]["reordered_mpc"]
    if fault.startswith("prediction"):
        rows[0]["evaluations"][fault]["velocity_prediction_rmse"]["reordered_mpc"] = 1.0000001
    elif fault == "tracking":
        trial["tracking_rmse_rad"] = 1.0000001
    elif fault == "actual_abs":
        trial["control_effort"]["actual_absolute_nm_s"] = 1.151
    elif fault == "actual_square":
        trial["control_effort"]["actual_squared_nm2_s"] = 1.151
    elif fault == "missing_actual":
        trial["actual_effort_complete"] = False
    elif fault == "nonfinite":
        trial["tracking_rmse_rad"] = float("nan")
    elif fault == "negative":
        trial["control_effort"]["actual_squared_nm2_s"] = -1.
    elif fault == "duplicate":
        rows[2]["seed"] = 0
    else:
        rows.pop()
    assert not core.performance_gate(rows)["passed"]
    assert core.adoption_gate(rows)["selected_candidate"] == "short"


def test_tracking_improvement_uses_raw_means_and_zero_is_undefined():
    gate = core.performance_gate(gate_fixture((.1, 1., 10.), (.04, .9, 9.95)))
    assert gate["tracking_mean_improvement"] < .05 and not gate["passed"]
    zero = core.performance_gate(gate_fixture((0., 0., 0.), (0., 0., 0.)))
    assert zero["tracking_mean_improvement"] is None and not zero["passed"]


def test_both_actual_effort_means_use_exact_five_percent_cap_and_zero_rule():
    rows = gate_fixture(effort=1.05)
    assert core.performance_gate(rows)["passed"]
    rows[0]["evaluations"]["reordered_mpc"]["control_effort"]["actual_squared_nm2_s"] += 1e-9
    assert not core.performance_gate(rows)["passed"]
    rows = gate_fixture(effort=0.)
    for r in rows:
        r["evaluations"]["short_mpc"]["control_effort"] = dict.fromkeys(core.EFFORT_KEYS[2:], 0.)
    assert core.performance_gate(rows)["passed"]
    rows[0]["evaluations"]["reordered_mpc"]["control_effort"]["actual_absolute_nm_s"] = .00001
    assert not core.performance_gate(rows)["passed"]


def test_initial_partial_prefix_archive_retains_paid_cost_without_monitor_or_model(tmp_path):
    archive = partial_archive(tmp_path/"partial")
    report = core.audit(archive, git_root=None)
    assert report["failed"] == 0, report["violations"]
    assert report["archive"]["budget"] == {"control_calls_attempted": 1, "control_steps": 1, "physics_steps": 3, "model_updates": 0}
    assert report["archive"]["stops"] == {"study": 0, "environment": 1, "both": 0}
    assert not report["development_adoption_gate"]["passed"]


@pytest.mark.parametrize("fault", ["manifest", "source", "protocol", "paid", "study"])
def test_small_archive_tampering_fails_and_keeps_reported_paid_budget(tmp_path, fault):
    archive = partial_archive(tmp_path/"partial")
    if fault == "manifest":
        (archive/"seed_results.json").write_text("[]", encoding="utf-8")
    elif fault == "source":
        with pytest.warns(UserWarning, match="Duplicate name"):
            with zipfile.ZipFile(archive/"source_snapshot.zip", "a") as out:
                out.writestr(core.ASSET, b"tampered")
        write_manifest(archive)
    elif fault == "protocol":
        metadata = core.load_json(archive/"metadata.json")
        metadata["study_abort_spec"]["absolute_q_minus_qref_rad"] = .15
        (archive/"metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
        write_manifest(archive)
    elif fault == "paid":
        episodes = core.load_json(archive/"episodes.json")
        episodes[0]["physics_steps"] = 0
        (archive/"episodes.json").write_text(json.dumps(episodes), encoding="utf-8")
        write_manifest(archive)
    else:
        with gzip.open(archive/"trace.jsonl.gz", "rt", encoding="utf-8") as inp:
            row = json.loads(inp.readline())
        row["study_abort"] = monitor_payload(.12, 1., 0, "prefix")
        with gzip.open(archive/"trace.jsonl.gz", "wt", encoding="utf-8") as out:
            out.write(json.dumps(row)+"\n")
        write_manifest(archive)
    report = core.audit(archive, git_root=None)
    assert report["failed"] > 0
    assert report["reported_paid_budget_if_replay_incomplete"]["physics_steps"] == 3


def test_output_and_holdout_are_refused_before_trace(tmp_path, monkeypatch):
    archive = tmp_path/"holdout"
    archive.mkdir()
    (archive/"metadata.json").write_text(json.dumps({"split": "final", "seeds": [20, 21, 22], "pose": "supine", "joint_index": 0}), encoding="utf-8")
    def forbidden(*args, **kwargs):
        raise AssertionError("Heldout trace must not be opened")
    monkeypatch.setattr(core.gzip, "open", forbidden)
    report = core.audit(archive, git_root=None)
    assert report["failed"] and report["archive"] is None
    with pytest.raises(ValueError):
        core.validate_output_path(archive/"audit.json", [archive])
    existing = tmp_path/"existing.json"
    existing.write_text("keep", encoding="utf-8")
    with pytest.raises(ValueError):
        core.validate_output_path(existing, [])
    development = tmp_path/"development"
    development.mkdir()
    (development/"metadata.json").write_text(json.dumps({"split": "development", "seeds": [0, 1, 2], "pose": "supine", "joint_index": 0}), encoding="utf-8")
    report = core.audit(development, reference=archive, git_root=None)
    assert report["failed"] and report["archive"] is None


def test_auditor_only_imports_standard_library_and_does_not_access_physics():
    import ast
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    modules = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(n.name.split(".")[0] for n in node.names)
        elif isinstance(node, ast.ImportFrom):
            modules.append((node.module or "").split(".")[0])
    assert set(modules).issubset(set(sys.stdlib_module_names)|{"__future__"})
    assert not {"mujoco", "numpy", "developmental_physics"}.intersection(modules)



def failure_archive(path, *, missing_item=False):
    """Second returned endpoint then IO failure: successful update survives raw snapshot."""
    partial_archive(path)
    metadata, episodes, results = [core.load_json(path/n) for n in ("metadata.json", "episodes.json", "seed_results.json")]
    sr, ep = results[0], episodes[0]
    rows = [transition(i, kind="calibration_short", phase="prefix") for i in range(100)]
    state = core.initial_state("hinge5")
    initial = {"short_hinge5": saved_model(state)}
    nominal = saved_model(core.initial_state("linear4"))
    first = transition(100, kind="calibration_short", phase="calibration", u=.125, next_q=.00005, next_v=.0025)
    first["predicted_next_qv"] = {"hinge5": core.predict(state["theta"], 0., 0., 0., .125)}
    first["model_update"] = {"hinge5": update_item(first, state, "hinge5")}
    rows.append(first)
    second = transition(101, kind="calibration_short", phase="calibration", before=first["observation_after"], q=.00005, v=.0025, u=.125, next_q=.000125, next_v=.00375)
    second["predicted_next_qv"] = {"hinge5": core.predict(state["theta"], 0., .00005, .0025, .125)}
    success = update_item(second, state, "hinge5")
    second["model_update"] = {} if missing_item else {"hinge5": success}
    second["collector_exception"] = {"type": "OSError", "message": "synthetic returned endpoint then IO failure"}
    second["partial_model_snapshots"] = {"hinge5": saved_model(state, trainable=True)}
    second["diagnostics"] = {k: second["diagnostics"][k] for k in ("step_id", "physics_steps", "time")}
    second["unreturned_physics_steps"] = 0
    rows.append(second)
    frozen = {"short_hinge5": saved_model(state)}
    view = {**nominal, "integration": core.integration_spec(nominal["parameter_fingerprint"]),
        "integration_fingerprint": core.digest(core.integration_spec(nominal["parameter_fingerprint"])), "frozen_view": True}
    limit = 100.*3.141592653589793/180.
    sr.update(reference_q=0., direction=1, selection_record={"joint_index": 0, "joint_position_rad": 0., "lower_limit_rad": -limit,
        "upper_limit_rad": limit, "positive_room_rad": limit, "negative_room_rad": limit, "direction": 1,
        "rule": "larger distance to the public joint limit; ties choose positive"}, nominal_model=nominal,
        calibration_updates=2, initial_models=initial, learned_models=frozen,
        calibration_models={"short": {"hinge5": frozen["short_hinge5"]}}, integration_models={"nominal_mpc": view})
    ep.update(status="exception", reason=second["collector_exception"], collector_exception=second["collector_exception"], control_calls_attempted=102,
        control_steps=102, physics_steps=1020, risk_telemetry_complete=False, environment_terminated=False, environment_stop_reason=None)
    ep["phase_budgets"]["prefix"] = {"control_calls_attempted": 100, "control_steps": 100, "physics_steps": 1000}
    ep["phase_budgets"]["calibration"] = {"control_calls_attempted": 2, "control_steps": 2, "physics_steps": 20}
    ev = sr["evaluations"]["calibration_short"]
    ev.update(status="exception", environment_terminated=False, environment_stop_reason=None,
        models_after={"nominal": nominal["parameter_fingerprint"], **{n: m["parameter_fingerprint"] for n, m in frozen.items()}},
        integration_models_after={"nominal_mpc": view["integration_fingerprint"]})
    ev["phase_effort"]["calibration"] = {"requested_absolute_nm_s": .005, "requested_squared_nm2_s": .000625,
        "actual_absolute_nm_s": .005, "actual_squared_nm2_s": .000625}
    ev["phase_actual_effort_substeps"].update(prefix=1000, calibration=20)
    metadata.update(control_calls_attempted=102, control_steps=102, physics_steps=1020, model_updates=2,
        terminated_trials=0, exception_trials=1, archive_status="failed")
    for n, obj in (("metadata.json", metadata), ("episodes.json", episodes), ("seed_results.json", results)):
        (path/n).write_text(json.dumps(obj), encoding="utf-8")
    with gzip.open(path/"trace.jsonl.gz", "wt", encoding="utf-8") as out:
        for r in rows:
            out.write(json.dumps(r)+"\n")
    write_manifest(path)
    return path


@pytest.mark.parametrize("missing_item", [False, True])
def test_exception_after_return_preserves_successful_atomic_updates_and_measured_paid_cost(tmp_path, missing_item):
    archive = failure_archive(tmp_path/"failed", missing_item=missing_item)
    report = core.audit(archive, git_root=None)
    assert report["failed"] == 0, report["violations"]
    seed = report["archive"]["seeds"][0]
    assert seed["model_updates"] == seed["independently_replayed_updates"] == 2
    assert seed["exception_snapshot_replayed_updates"] == 1
    ev = seed["evaluations"]["calibration_short"]
    assert ev["unreconstructed_transition_rows"] == 1 and ev["missing_risk_substeps"] == 10
    effort = ev["phase_effort"]["calibration"]
    assert effort["independent_effort"]["requested_absolute_nm_s"] == pytest.approx(.005)
    assert effort["actual_effort_is_lower_bound"]
    assert effort["collector_reported_actual_measured_substeps"] == 20
    assert ev["free_rollouts"][0]["valid_physical_windows"] == 1
    assert not report["development_adoption_gate"]["passed"]


@pytest.mark.parametrize("fault", ["snapshot_key", "snapshot_count", "snapshot_coefficients", "update_count", "cold_start"])
def test_exception_snapshot_and_cold_start_tampering_rejected(tmp_path, fault):
    archive = failure_archive(tmp_path/"failed")
    if fault == "cold_start":
        results = core.load_json(archive/"seed_results.json")
        results[0]["initial_models"]["short_hinge5"]["coefficients"][2] = .5
        (archive/"seed_results.json").write_text(json.dumps(results), encoding="utf-8")
    else:
        with gzip.open(archive/"trace.jsonl.gz", "rt", encoding="utf-8") as stream:
            rows = [json.loads(line) for line in stream]
        endpoint = rows[-1]
        if fault == "snapshot_key":
            endpoint["partial_model_snapshots"] = {"short_hinge5": endpoint["partial_model_snapshots"]["hinge5"]}
        elif fault == "snapshot_count":
            endpoint["partial_model_snapshots"]["hinge5"]["update_count"] = 1
        elif fault == "snapshot_coefficients":
            endpoint["partial_model_snapshots"]["hinge5"]["coefficients"][2] += .001
        else:
            endpoint["model_update"]["hinge5"]["update_count"] = 3
        with gzip.open(archive/"trace.jsonl.gz", "wt", encoding="utf-8") as stream:
            for row in rows:
                stream.write(json.dumps(row)+"\n")
    write_manifest(archive)
    report = core.audit(archive, git_root=None)
    assert report["failed"] > 0
    assert report["reported_paid_budget_if_replay_incomplete"]["model_updates"] == 2


def test_zero_over_zero_relative_effort_remains_undefined():
    rows = gate_fixture(effort=0.)
    for r in rows:
        r["evaluations"]["short_mpc"]["control_effort"] = dict.fromkeys(core.EFFORT_KEYS[2:], 0.)
    result = core.performance_gate(rows)
    assert result["passed"]
    assert all(e["relative_increase"] is None for e in result["actual_effort_gates"].values())



def stopped_calibration_archive(path, count=300, last_substeps=10, env_stop=False):
    """Native terminal endpoint at last paid request; stopped fit is never eligible."""
    partial_archive(path)
    metadata, episodes, results = [core.load_json(path/n) for n in ("metadata.json", "episodes.json", "seed_results.json")]
    sr, ep = results[0], episodes[0]
    state = core.initial_state("hinge5")
    initial = {"short_hinge5": saved_model(state)}
    nominal = saved_model(core.initial_state("linear4"))
    view = {**nominal, "integration": core.integration_spec(nominal["parameter_fingerprint"]),
        "integration_fingerprint": core.digest(core.integration_spec(nominal["parameter_fingerprint"])), "frozen_view": True}
    rows = [transition(i, kind="calibration_short", phase="prefix") for i in range(100)]
    before, qe, ve, effort = rows[-1]["observation_after"], [], [], core.new_effort()
    for active in range(count):
        index, n = active+100, last_substeps if active == count-1 else 10
        u = core.calibration_request("short", active, 1)
        nq, nv = (.12, 1.) if active == count-1 else (0., 0.)
        r = transition(index, kind="calibration_short", phase="calibration", q=0., v=0., u=u, next_q=nq, next_v=nv, before=before, n=n, terminated=env_stop and active == count-1)
        prediction = core.predict(state["observed_theta"], 0., 0., 0., u)
        r["predicted_next_qv"] = {"hinge5": prediction}
        r["study_abort"] = monitor_payload(nq, nv, index, "calibration")
        if n == 10:
            r["model_update"] = {"hinge5": update_item(r, state, "hinge5")}
            qe.append(nq-prediction[0])
            ve.append(nv-prediction[1])
        else:
            r["model_update"] = {"hinge5": {"updated": False, "phase": "partial_calibration_interval", "executed_substeps": n,
                "update_count": state["updates"], "model_id": "short_hinge5", "shared_transition_id": r["shared_transition_id"]}}
        for key, value in zip(core.EFFORT_KEYS, (abs(u)*n*.002, u*u*n*.002, abs(u)*n*.002, u*u*n*.002)):
            effort[key] += value
        before = r["observation_after"]
        rows.append(r)
    final, reason = saved_model(state), rows[-1]["study_abort"]
    limit = 100.*3.141592653589793/180.
    sr.update(reference_q=0., direction=1, selection_record={"joint_index": 0, "joint_position_rad": 0., "lower_limit_rad": -limit,
        "upper_limit_rad": limit, "positive_room_rad": limit, "negative_room_rad": limit, "direction": 1,
        "rule": "larger distance to the public joint limit; ties choose positive"}, nominal_model=nominal,
        calibration_updates=state["updates"], initial_models=initial, learned_models={"short_hinge5": final},
        calibration_models={"short": {"hinge5": final}}, integration_models={"nominal_mpc": view})
    physics = 1000+(count-1)*10+last_substeps
    ep.update(status="terminated", reason="synthetic_env_stop" if env_stop else reason, study_abort=reason,
        environment_terminated=env_stop, environment_stop_reason="synthetic_env_stop" if env_stop else None,
        control_calls_attempted=100+count, control_steps=100+count, physics_steps=physics, risk_telemetry_complete=True)
    ep["phase_budgets"]["prefix"] = {"control_calls_attempted": 100, "control_steps": 100, "physics_steps": 1000}
    ep["phase_budgets"]["calibration"] = {"control_calls_attempted": count, "control_steps": count, "physics_steps": physics-1000}
    ev = sr["evaluations"]["calibration_short"]
    ev.update(study_abort=reason, environment_terminated=env_stop, environment_stop_reason=ep["environment_stop_reason"],
        position_prediction_rmse={"hinge5": core.rmse(qe)}, velocity_prediction_rmse={"hinge5": core.rmse(ve)}, metric_prediction_step_count={"hinge5": len(qe)},
        models_after={"nominal": nominal["parameter_fingerprint"], "short_hinge5": final["parameter_fingerprint"]},
        integration_models_after={"nominal_mpc": view["integration_fingerprint"]})
    ev["phase_effort"]["calibration"] = effort
    ev["phase_actual_effort_substeps"].update(prefix=1000, calibration=physics-1000)
    metadata.update(control_calls_attempted=100+count, control_steps=100+count, physics_steps=physics, model_updates=state["updates"])
    for name, value in (("metadata.json", metadata), ("episodes.json", episodes), ("seed_results.json", results)):
        (path/name).write_text(json.dumps(value), encoding="utf-8")
    with gzip.open(path/"trace.jsonl.gz", "wt", encoding="utf-8") as out:
        for row in rows:
            out.write(json.dumps(row)+"\n")
    write_manifest(path)
    return path


def test_last_planned_calibration_step_can_update_three_hundred_but_study_still_fails(tmp_path):
    archive = stopped_calibration_archive(tmp_path/"last_step")
    report = core.audit(archive, git_root=None)
    assert report["failed"] == 0, report["violations"]
    seed = report["archive"]["seeds"][0]
    assert seed["model_updates"] == seed["independently_replayed_updates"] == 300
    e = seed["evaluations"]["calibration_short"]
    assert e["study_aborted"] and not e["completed"] and not e["eligible"]
    assert e["free_rollouts"][0]["valid_physical_windows"] == 300
    assert all(w["valid_windows_ending_in_study_abort"] == 1 for w in e["free_rollouts"])
    assert e["paid_budget"] == {"control_calls_attempted": 400, "control_steps": 400, "physics_steps": 4000}
    assert report["archive"]["stops"] == {"study": 1, "environment": 0, "both": 0}
    assert report["development_adoption_gate"]["selected_candidate"] == "short"


@pytest.mark.parametrize("n", [3, 10])
def test_same_returned_endpoint_can_have_both_stops_and_partial_never_updates_or_scores(tmp_path, n):
    archive = stopped_calibration_archive(tmp_path/"stopped", count=1, last_substeps=n, env_stop=True)
    report = core.audit(archive, git_root=None)
    assert report["failed"] == 0, report["violations"]
    seed = report["archive"]["seeds"][0]
    assert seed["model_updates"] == int(n == 10)
    e = seed["evaluations"]["calibration_short"]
    assert e["study_aborted"] and e["environment_terminated"] and not e["completed"]
    assert e["free_rollouts"][0]["valid_physical_windows"] == int(n == 10)
    assert (e["velocity_prediction_rmse"]["hinge5"] is None) == (n == 3)
    assert report["archive"]["stops"] == {"study": 1, "environment": 1, "both": 1}
    assert e["phase_effort"]["calibration"]["independent_effort"]["requested_absolute_nm_s"] == pytest.approx(.125*n*.002)



def partial_nominal_control_archive(path):
    """No successful fit, independent nominal attempt returns partial target endpoint."""
    partial_archive(path)
    metadata, episodes, results = [core.load_json(path/n) for n in ("metadata.json", "episodes.json", "seed_results.json")]
    first = episodes[0]
    first.update(status="blocked", reason={"type": "ArchiveAborted"}, control_calls_attempted=0, control_steps=0, physics_steps=0)
    first["phase_budgets"] = {p: {"control_calls_attempted": 0, "control_steps": 0, "physics_steps": 0} for p in core.PHASES}
    nominal = saved_model(core.initial_state("linear4"))
    fingerprint = nominal["parameter_fingerprint"]
    integration = core.integration_spec(fingerprint)
    view_hash = core.digest(integration)
    view = {**nominal, "integration": integration, "integration_fingerprint": view_hash, "frozen_view": True}
    limit = 100.*3.141592653589793/180.
    decision = core.replay_mpc(core.INITIAL["linear4"], 0., 0., 0., .04, 0., [-limit, limit])
    u = decision["torque"]
    rows = [transition(i, kind="nominal_mpc", phase="prefix") for i in range(100)]
    r = transition(100, kind="nominal_mpc", phase="control", before=rows[-1]["observation_after"], u=u, next_q=.12, next_v=1., n=3, terminated=True)
    reason = monitor_payload(.12, 1., 100, "control")
    r.update(target_q=.04, planner_decision=decision, study_abort=reason, partial_interval_target_error_rad=.12-.04,
        predicted_next_qv={"nominal_mpc": core.predict(core.INITIAL["linear4"], 0., 0., 0., u), "persistence": (0., 0.)})
    rows.append(r)
    ep = episodes[6]
    ep.update(status="terminated", reason="synthetic_env_stop", study_abort=reason, environment_terminated=True, environment_stop_reason="synthetic_env_stop",
        control_calls_attempted=101, control_steps=101, physics_steps=1003, risk_telemetry_complete=True, unreturned_physics_steps=0,
        environment_fingerprint_before="1"*64, environment_fingerprint_after="1"*64)
    ep["phase_budgets"]["prefix"] = {"control_calls_attempted": 100, "control_steps": 100, "physics_steps": 1000}
    ep["phase_budgets"]["control"] = {"control_calls_attempted": 1, "control_steps": 1, "physics_steps": 3}
    sr = results[0]
    sr.update(reference_q=0., direction=1, selection_record={"joint_index": 0, "joint_position_rad": 0., "lower_limit_rad": -limit,
        "upper_limit_rad": limit, "positive_room_rad": limit, "negative_room_rad": limit, "direction": 1,
        "rule": "larger distance to the public joint limit; ties choose positive"}, nominal_model=nominal, integration_models={"nominal_mpc": view})
    ev = sr["evaluations"].pop("calibration_short")
    sr["evaluations"]["calibration_short"] = {"completed": False, "status": "blocked"}
    sr["evaluations"]["nominal_mpc"] = ev
    effort = dict(zip(core.EFFORT_KEYS, (abs(u)*.006, u*u*.006, abs(u)*.006, u*u*.006)))
    ev.update(environment_terminated=True, environment_stop_reason="synthetic_env_stop", study_abort=reason,
        position_prediction_rmse={"nominal_mpc": None, "persistence": None}, velocity_prediction_rmse={"nominal_mpc": None, "persistence": None},
        metric_prediction_step_count={"nominal_mpc": 0, "persistence": 0}, partial_interval_target_errors_rad=[.12-.04], partial_interval_target_error_count=1,
        control_effort=effort, actual_control_effort_substeps=3, planner_attempt_count=1, planner_decision_count=1,
        mathematical_prediction_calls=decision["mathematical_prediction_calls"], planner_fallbacks=int(decision["fallback"]),
        controller_seconds_total=.001, models_before={"nominal": fingerprint}, models_after={"nominal": fingerprint},
        integration_models_before={"nominal_mpc": view_hash}, integration_models_after={"nominal_mpc": view_hash},
        planner_spec={"config": core.MPC_CONFIG, "qref_rad": 0., "joint_range_rad": [-limit, limit], "candidates_nm": [-.5+i*.125 for i in range(9)],
            "physical_queries": 0, "forecast_bounds_rad": [-.15, .15], "target_bounds_rad": [-.15, .15], "integration": integration, "integration_fingerprint": view_hash})
    ev["phase_effort"]["control"] = effort
    ev["phase_actual_effort_substeps"].update(prefix=1000, control=3)
    metadata.update(control_calls_attempted=101, control_steps=101, physics_steps=1003)
    for name, value in (("metadata.json", metadata), ("episodes.json", episodes), ("seed_results.json", results)):
        (path/name).write_text(json.dumps(value), encoding="utf-8")
    with gzip.open(path/"trace.jsonl.gz", "wt", encoding="utf-8") as out:
        for row in rows:
            out.write(json.dumps(row)+"\n")
    write_manifest(path)
    return path


def test_partial_nominal_control_is_fit_independent_paid_and_never_scored_as_twenty_ms(tmp_path):
    archive = partial_nominal_control_archive(tmp_path/"control_partial")
    report = core.audit(archive, git_root=None)
    assert report["failed"] == 0, report["violations"]
    e = report["archive"]["seeds"][0]["evaluations"]["nominal_mpc"]
    assert e["tracking_rmse_rad"] is None and e["velocity_prediction_rmse"] == {"nominal_mpc": None, "persistence": None}
    assert e["free_rollouts"][0]["valid_physical_windows"] == 0
    assert e["control_effort"]["actual_absolute_nm_s"] == pytest.approx(.003)
    assert e["mathematical_prediction_calls"] == 135
    assert e["study_aborted"] and e["environment_terminated"] and not e["eligible"]
    assert report["archive"]["budget"]["model_updates"] == 0
