"""Finite primitive/schema audit checks; standard-library fixture generation.

No collector/environment/model/NumPy/MuJoCo import, real action or Git call.
The deliberately static synthetic body provides schema evidence only.
"""
import ast
import copy
import gzip
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys
from dataclasses import FrozenInstanceError
import xml.etree.ElementTree as ET
import zipfile

import pytest

try:
    import audit_pair_pd as audit
except ModuleNotFoundError as exc:
    if exc.name != "audit_pair_pd":
        raise
    _root = next(p for p in Path(__file__).resolve().parents if (p/"pyproject.toml").is_file())
    _loader = importlib.util.spec_from_file_location("audit_pair_pd", _root/"scripts/audit_pair_pd.py")
    audit = importlib.util.module_from_spec(_loader)
    sys.modules[_loader.name] = audit
    _loader.loader.exec_module(audit)


ROOT = audit.ROOT


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2, allow_nan=False)+"\n", encoding="utf-8")


def public_ranges():
    xml = ET.fromstring((ROOT/audit.ASSET).read_bytes())
    factor = math.pi/180. if xml.find("compiler").get("angle", "degree") == "degree" else 1.
    ranges = {joint.get("name"): [float(value)*factor for value in joint.get("range").split()]
              for joint in xml.findall(".//joint") if joint.get("range")}
    return [ranges[name] for name in audit.JOINTS]


def obs(command, *, stop=False):
    q, v = [0., -.0005, 0., 0., 0., 0., 0., 0.], [0.]*8
    if stop:
        v[1] = 1.
    return {"joint_position": q, "joint_velocity": v, "imu_gyro": [0.]*3,
            "imu_acceleration": [0.]*3, "actuator_torque": list(command), "previous_command": list(command)}


def selection_choices():
    ranges = public_ranges()
    result = []
    for i, q in enumerate((0., -.0005)):
        low, high = ranges[i]
        result.append({"joint_index": i, "joint_position_rad": q, "lower_limit_rad": low,
                       "upper_limit_rad": high, "positive_room_rad": high-q, "negative_room_rad": q-low,
                       "direction": 1, "rule": "larger distance to the public joint limit; ties choose positive"})
    return result


def tracking(errors):
    if not errors:
        return None
    return {"joint": math.sqrt(math.fsum(value*value for row in errors for value in row)/(2*len(errors))),
            "per_axis": [math.sqrt(math.fsum(row[i]*row[i] for row in errors)/len(errors)) for i in range(2)],
            "complete_endpoints": len(errors)}


def windows(endpoints):
    result = {}
    for name, lower, upper in (("segment0", 0, 100), ("segment1", 100, 200),
                              ("segment0_last20", 80, 100), ("segment1_last20", 180, 200)):
        found = [row for row in endpoints if lower <= row["active_index"] < upper]
        complete = [row["error_rad"] for row in found if row["complete_transition"]]
        result[name] = {"planned_active_index_start": lower, "planned_active_index_end_exclusive": upper,
            "planned_count": upper-lower, "returned_count": len(found), "complete_count": len(complete),
            "partial_count": len(found)-len(complete), "missing_returned_count": upper-lower-len(found),
            "missing_complete_count": upper-lower-len(complete), "tracking": tracking(complete),
            "signed_mean_error_rad": [math.fsum(row[i] for row in complete)/len(complete) for i in range(2)] if complete else None,
            "returned_endpoints": found}
    return result


def make_row(plan, index, previous, *, stop=False, partial=False, missing=False):
    phase = "prefix" if index < 100 else "control"
    target = None if phase == "prefix" else [.04 if index < 200 else .08, -.0005+(.04 if index < 200 else .08)]
    raw = None if target is None else [64.*(target[i]-previous["joint_position"][i])-plan["kd"][i]*previous["joint_velocity"][i] for i in range(2)]
    request = [0.]*8
    if raw is not None:
        request[:2] = [max(-.5, min(.5, value)) for value in raw]
    n = 3 if partial else 10
    after = obs(request, stop=stop)
    reason = {"type": "SyntheticEnvironmentStop", "message": "partial terminal"} if partial else None
    d = {"step_id": index+1, "physics_steps": index*10+n, "time": (index*10+n)*.002,
         "executed_substeps": n, "terminated": partial, "reason": reason,
         "requested_torque": request, "accepted_torque": request, "applied_torque": request,
         "applied_torque_history": [list(request) for _ in range(n)], "guarded_substeps": 0,
         "substep_ground_normal_forces": [1.]*n, "substep_kinetic_energies": [.2]*n,
         "substep_minimum_contact_distances": [-.0001]*n, "peak_substep_ground_normal_force": 1.,
         "ground_normal_impulse_ns": .002*n, "peak_substep_kinetic_energy": .2,
         "minimum_substep_contact_distance": -.0001}
    if missing:
        d.pop("applied_torque_history")
    study = None
    if stop:
        study = {"type": "StudyAbort", "triggers": [{"joint_index": 1, "signal": "absolute_velocity_rad_s"}],
            "q_rad": after["joint_position"][:2], "qref_rad": [0., -.0005], "velocity_rad_s": [0., 1.],
            "thresholds": {"absolute_q_minus_qref_rad": .12, "absolute_velocity_rad_s": 1.},
            "feedback_action": None, "phase": "control", "step_index": index, "active_index": index-100}
    return {"trial_id": plan["trial_id"], "seed": plan["seed"], "candidate": plan["candidate"],
        "kp": plan["kp"], "kd": plan["kd"], "control_index": index, "phase": phase,
        "control_steps_before": index, "control_steps_after": index+1,
        "physics_steps_before": index*10, "physics_steps_after": index*10+n,
        "requested_torque": request, "raw_pd_torque_nm": raw, "target_q_rad": target,
        "study_abort": study, "environment_terminated": partial, "environment_stop_reason": reason,
        "complete_transition": n == 10,
        "actual_history_issue": {"type": "ActualHistoryMissing", "phase": phase, "control_index": index, "missing_substeps": n} if missing else None,
        "partial_interval_target_error_rad": [after["joint_position"][i]-target[i] for i in range(2)] if partial and target else None,
        "observation_before": previous, "observation_after": after, "diagnostics": d,
        "qpos": [0., 0., 0., 1., 0., 0., 0., *after["joint_position"]],
        "qvel": [0.]*6+after["joint_velocity"], "invalid_numeric_fields": []}


def new_risk():
    return {"peak_ground_force_n": 0., "ground_normal_impulse_ns": 0., "peak_kinetic_energy_j": 0.,
            "minimum_contact_distance_m": 0., "max_native_speed_rad_s": 0., "guarded_substeps": 0,
            "outside_public_limit_endpoint_count": 0}


def build_trial(plan, *, stop_index=None, partial=False, missing=False, fatal=False):
    rows, previous, endpoints, errors = [], obs([0.]*8), [], []
    effort = {p: {key: [0., 0.] for key in audit.EFFORT_KEYS} for p in audit.PHASES}
    budget = {p: dict.fromkeys(audit.BUDGET_KEYS, 0) for p in audit.PHASES}
    actual = dict.fromkeys(audit.PHASES, 0)
    complete_counts = dict.fromkeys(audit.PHASES, 0)
    risk = {p: new_risk() for p in ("full", *audit.PHASES)}
    history_issues, partial_errors = [], []
    saturation = [0, 0]
    terminal_study = terminal_reason = None
    max_index = 99 if fatal else (stop_index if stop_index is not None else 299)
    for index in range(max_index+1):
        row = make_row(plan, index, previous, stop=stop_index == index,
                       partial=partial and stop_index == index, missing=missing and index == 100)
        rows.append(row)
        previous = row["observation_after"]
        phase, n = row["phase"], row["diagnostics"]["executed_substeps"]
        budget[phase]["control_calls_attempted"] += 1
        budget[phase]["control_steps"] += 1
        budget[phase]["physics_steps"] += n
        complete_counts[phase] += int(n == 10)
        for i in range(2):
            command = row["requested_torque"][i]
            effort[phase]["requested_absolute_nm_s"][i] += abs(command)*n*.002
            effort[phase]["requested_squared_nm2_s"][i] += command*command*n*.002
            if "applied_torque_history" in row["diagnostics"]:
                effort[phase]["actual_absolute_nm_s"][i] += abs(command)*n*.002
                effort[phase]["actual_squared_nm2_s"][i] += command*command*n*.002
        if "applied_torque_history" in row["diagnostics"]:
            actual[phase] += n
        else:
            history_issues.append(row["actual_history_issue"])
        for p in ("full", phase):
            risk[p]["peak_ground_force_n"] = 1.
            risk[p]["ground_normal_impulse_ns"] += n*.002
            risk[p]["peak_kinetic_energy_j"] = .2
            risk[p]["minimum_contact_distance_m"] = -.0001
            risk[p]["max_native_speed_rad_s"] = max(risk[p]["max_native_speed_rad_s"], 1. if index == stop_index else 0.)
            risk[p]["outside_public_limit_endpoint_count"] += 1
        if phase == "control":
            err = [previous["joint_position"][i]-row["target_q_rad"][i] for i in range(2)]
            endpoints.append({"active_index": index-100, "error_rad": err, "complete_transition": n == 10})
            if n == 10:
                errors.append(err)
                saturation = [value+1 for value in saturation]
            else:
                partial_errors.append({"active_index": index-100, "error_rad": err})
        terminal_study, terminal_reason = row["study_abort"], row["environment_stop_reason"]
    returned, telemetry = len(rows), sum(row["diagnostics"]["executed_substeps"] for row in rows)
    exception = None
    if fatal:
        raw = [2.56, 2.56]
        request = [.5, .5]+[0.]*6
        exception = {"type": "OSError", "message": "synthetic three paid substeps, no return"}
        rows.append({"trial_id": plan["trial_id"], "seed": plan["seed"], "candidate": plan["candidate"],
            "kp": plan["kp"], "kd": plan["kd"], "control_index": 100, "phase": "control",
            "collector_exception": exception, "study_abort": None, "requested_torque": request,
            "raw_pd_torque_nm": raw, "target_q_rad": [.04, .0395], "observation_before": previous,
            "control_steps_before": 100, "physics_steps_before": 1000,
            "control_steps_after": 100, "physics_steps_after": 1003,
            "returned_step_diagnostics": None, "returned_observation_after": None,
            "partial_interval_target_error_rad": None, "unreturned_physics_steps": 3,
            "returned_control_steps": 100, "trace_rows_written": 100, "invalid_numeric_fields": []})
        budget["control"].update(control_calls_attempted=1, control_steps=0, physics_steps=3)
        effort["control"]["requested_absolute_nm_s"] = [.003, .003]
        effort["control"]["requested_squared_nm2_s"] = [.0015, .0015]
    missing_counts = {p: budget[p]["physics_steps"]-actual[p] for p in audit.PHASES}
    full = not fatal and stop_index is None
    episode = {**plan, "reset_seed": audit.RESET_SEEDS[plan["seed"]], "public_joint_ranges_rad": public_ranges(),
        "status": "exception" if fatal else "terminated" if stop_index is not None else "completed",
        "complete": full, "collector_exception": exception, "reason": terminal_reason or terminal_study or exception,
        "trace_write_failure": None, "study_abort": terminal_study, "environment_terminated": partial,
        "environment_stop_reason": terminal_reason, "environment_fingerprint_before": "synthetic static body",
        "environment_fingerprint_after": "synthetic static body", "prefix_end_q_rad": [0., -.0005],
        "selection_records": selection_choices(), "metric_control_step_count": len(errors), "tracking": tracking(errors),
        "complete_tracking_errors_rad": errors, "tracking_windows": windows(endpoints),
        "partial_interval_target_errors_rad": partial_errors, "partial_interval_target_error_count": len(partial_errors),
        "phase_complete_transition_counts": complete_counts, "phase_budgets": budget, "phase_effort": effort,
        "phase_effort_combined": {p: {key: sum(value) for key, value in effort[p].items()} for p in audit.PHASES},
        "phase_actual_effort_substeps": actual, "phase_actual_effort_complete": {p: missing_counts[p] == 0 for p in audit.PHASES},
        "phase_actual_effort_missing_substeps": missing_counts, "actual_effort_complete": not any(missing_counts.values()),
        "actual_effort_is_lower_bound": any(missing_counts.values()), "actual_history_issues": history_issues,
        "returned_control_steps": returned, "trace_rows_written": returned, "returned_unstored_control_steps": 0,
        "unreturned_physics_steps": 3 if fatal else 0, "saturated_control_steps_per_axis": saturation, "phase_risk": risk,
        "observed_diagnostic_substeps": telemetry, "telemetry_complete_for_paid_substeps": not fatal,
        "risk_telemetry_complete": not fatal, "pd_action_calls": max(0, returned-100)+(1 if fatal else 0),
        "failed_pd_attempts": 0, "pd_action_seconds": 0., "invalid_numeric_fields": []}
    for key in audit.BUDGET_KEYS:
        episode[key] = sum(budget[p][key] for p in audit.PHASES)
    return episode, rows


def saved_selection(episodes):
    candidates = []
    for candidate, kd in enumerate(audit.KD):
        trials = [e for e in episodes if e["candidate"] == candidate]
        eligible = all(e["complete"] and e.get("actual_effort_complete", False) for e in trials)
        key = None
        if eligible:
            key = [math.fsum(e["tracking"]["joint"] for e in trials)/3,
                   max(e["tracking"]["joint"] for e in trials),
                   math.fsum(e["phase_effort_combined"]["control"]["actual_squared_nm2_s"] for e in trials)/3, candidate]
        candidates.append({"candidate": candidate, "kp": list(audit.KP), "kd": list(kd), "eligible": eligible,
            "qualification_failures": [] if eligible else [{"reason": "explicit synthetic incomplete or missing actual trial"}],
            "sort_key": key, "paid_control_steps": sum(e["control_steps"] for e in trials),
            "paid_physics_steps": sum(e["physics_steps"] for e in trials)})
    available = [c for c in candidates if c["eligible"]]
    picked = min(available, key=lambda row: row["sort_key"]) if available else None
    return {"status": "selected" if picked else "blocked", "picked": picked, "candidates": candidates,
            "sort_order": ["mean_seed_joint_rmse", "max_seed_joint_rmse",
                           "mean_seed_control_actual_squared_effort", "candidate_index"]}


def make_archive(path, *, fatal=False, stop_index=None, partial=False, missing=False):
    path.mkdir()
    episodes, traces = [], []
    for index, plan in enumerate(audit.planned_matrix()):
        if fatal and index:
            episodes.append({**plan, "complete": False, "status": "blocked", "collector_exception": None,
                "reason": {"type": "ArchiveAborted", "message": "not attempted after fatal archive failure"},
                **dict.fromkeys(audit.BUDGET_KEYS, 0), "phase_budgets": {p: dict.fromkeys(audit.BUDGET_KEYS, 0) for p in audit.PHASES}})
            continue
        episode, rows = build_trial(plan, fatal=fatal and index == 0,
            stop_index=stop_index if index == 0 else None, partial=partial and index == 0, missing=missing and index == 0)
        episodes.append(episode)
        traces.extend(rows)
    sources = [*sorted((ROOT/"src/developmental_physics").glob("*.py")), ROOT/audit.ASSET, ROOT/"pyproject.toml",
               ROOT/audit.DRAFT_SPEC.collector, ROOT/audit.DRAFT_SPEC.protocol,
               ROOT/audit.DRAFT_SPEC.auditor, audit.COMMON_PATH, Path(__file__)]
    blobs = {path.relative_to(ROOT).as_posix(): path.read_bytes() for path in sources}
    with zipfile.ZipFile(path/"source_snapshot.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for name, blob in blobs.items():
            archive.writestr(name, blob)
    hashes = {name: hashlib.sha256(blob).hexdigest() for name, blob in blobs.items()}
    metadata = {"suite": audit.DRAFT_SPEC.suite, "synthetic": True, "source_commit": None,
        "source_status": None, "source_dirty": None, "source_git_blobs": {}, "source_sha256": hashes,
        "source_snapshot_sha256": audit.file_hash(path/"source_snapshot.zip"),
        "protocol": {"path": audit.DRAFT_SPEC.protocol, "sha256": hashes[audit.DRAFT_SPEC.protocol]},
        "auditor": {"path": audit.DRAFT_SPEC.auditor, "sha256": hashes[audit.DRAFT_SPEC.auditor], "pending": False, "required_for_formal": True},
        "seeds": list(audit.SEEDS), "kp": list(audit.KP), "kd_candidates": [list(pair) for pair in audit.KD],
        "pose": "supine", "split": "development", "joint_indices": [0, 1], "native_joint_count": 8,
        "prefix_steps": 100, "control_steps_per_trial": 200, "target_offsets_rad": [.04, .08],
        "environment_config": audit.ENVIRONMENT, "planned_episodes": audit.planned_matrix(),
        "planned_episode_count": 27, "maximum_control_steps": 8100, "maximum_physics_steps": 81000,
        "gpu": None, "model_updates": 0, "parameter_updates": {"body_model": 0, "policy": 0, "gains": 0},
        "teacher_calls": 0, "external_demonstration_samples": 0, "backend": "synthetic, no physics",
        "pd_controller_spec": {"implementation": "feedback_validate.pd_request per original j0/j1",
                               "permission_nm": .5, "body_model_input": False, "gain_updates": 0},
        "study_abort_spec": {"active_only": True, "absolute_q_minus_qref_rad": .12,
            "absolute_velocity_rad_s": 1., "comparison": ">=", "any_axis": True,
            "feedback_action": None, "complete_terminal_scored_not_complete": True},
        "wall_seconds": 0., "cpu_seconds": 0., "all_trials_successful": all(e["complete"] for e in episodes),
        "complete": not fatal, "archive_status": "failed" if fatal else "complete"}
    for key in audit.BUDGET_KEYS:
        metadata[key] = sum(e[key] for e in episodes)
    for status in ("completed", "terminated", "exception", "blocked"):
        metadata[status+"_trials"] = sum(e["status"] == status for e in episodes)
    for name, data in (("metadata.json", metadata), ("episodes.json", episodes), ("selection.json", saved_selection(episodes))):
        write_json(path/name, data)
    with gzip.open(path/"trace.jsonl.gz", "wt", encoding="utf-8") as stream:
        for row in traces:
            stream.write(json.dumps(row, allow_nan=False)+"\n")
    write_json(path/"manifest.json", {file.name: audit.file_hash(file) for file in path.iterdir() if file.is_file()})
    return path


@pytest.fixture(autouse=True)
def prohibit_git(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("no Git, process or physics calls in independent synthetic audit tests")
    monkeypatch.setattr(audit.subprocess, "run", forbidden)
    monkeypatch.setattr(audit.subprocess, "check_output", forbidden)


def test_auditor_and_common_direct_imports_are_standard_library_only():
    forbidden = {"numpy", "mujoco", "developmental_physics", "pair_pd_development", "torch"}
    for path in (Path(audit.__file__), audit.COMMON_PATH):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported = {node.module.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
        imported |= {alias.name.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
        assert not imported & forbidden


def test_scope_is_immutable_full_plan_and_never_metadata_selected(tmp_path):
    assert len(audit.planned_matrix()) == 27
    assert sum(p["maximum_control_steps"] for p in audit.planned_matrix()) == 8100
    with pytest.raises(FrozenInstanceError):
        audit.DRAFT_SPEC.synthetic_fixture = False
    with pytest.raises(TypeError):
        audit.PairPDAuditSpec(seeds=(0,))
    with pytest.raises(ValueError):
        audit.PairPDAuditSpec(synthetic_fixture=True, scientific_frozen=True)
    path = tmp_path/"scope"
    path.mkdir()
    write_json(path/"metadata.json", {"suite": "pair_pd_development_draft", "seeds": [0], "kp": [64., 64.]})
    with pytest.raises(ValueError, match="immutable"):
        audit.audit(path, git_root=None, spec=audit.DRAFT_SPEC)


@pytest.mark.parametrize("q,v,target,kd,raw,command", [
    ([0., -.0005], [.2, -.3], [.04, .0395], [2., 4.], [2.16, 3.76], [.5, .5]),
    ([.04, .04], [0., 0.], [.04, .04], [0., 1.], [0., 0.], [0., 0.]),
    ([.04, .04], [1., -1.], [0., 0.], [1., 4.], [-3.56, 1.44], [-.5, .5]),
])
def test_independent_current_only_pd_math(q, v, target, kd, raw, command):
    actual, uncapped = audit.pd_action(q, v, target, kd)
    assert uncapped == pytest.approx(raw) and actual == command


@pytest.mark.parametrize("bad", [[True, 0.], [math.nan, 0.], [math.inf, 0.], ["0", 0.], [0.], [0., 0., 0.]])
def test_nonfinite_shape_and_non_native_pd_inputs_are_rejected(bad):
    with pytest.raises(ValueError):
        audit.pd_action(bad, [0., 0.], [.04, .04], [0., 1.])


@pytest.mark.parametrize("axis,signal", [(0, "q"), (1, "q"), (0, "v"), (1, "v")])
def test_equal_boundary_study_abort_each_axis(axis, signal):
    q, v, ref = [0., 0.], [0., 0.], [0., 0.]
    (q if signal == "q" else v)[axis] = .12 if signal == "q" else 1.
    result = audit.study_abort(q, v, ref, 299)
    assert result["triggers"][0]["joint_index"] == axis
    assert result["step_index"] == 299 and result["active_index"] == 199


def test_fixed_last20_windows_do_not_shift_after_partial_or_early_stop():
    endpoints = [{"active_index": 0, "error_rad": [.1, -.2], "complete_transition": True},
                 {"active_index": 1, "error_rad": [.3, -.4], "complete_transition": False}]
    actual = audit.tail_windows(endpoints)
    assert actual["segment0"]["complete_count"] == 1 and actual["segment0"]["partial_count"] == 1
    assert actual["segment0"]["missing_complete_count"] == 99
    assert actual["segment0_last20"]["tracking"] is None
    assert actual["segment1_last20"]["missing_returned_count"] == 20


def test_full_standard_library_schema_archive_recomputes_and_never_passes_source_without_git(tmp_path):
    path = make_archive(tmp_path/"full")
    report = audit.audit(path, git_root=None, spec=audit.DRAFT_SPEC)
    labels = [violation["check"] for violation in report["violations"]]
    assert report["failed_checks"] == 2, report["violations"]
    assert labels == ["source_commit_format", "clean_collection_source"]
    assert report["budget"] == {"control_calls_attempted": 8100, "control_steps": 8100, "physics_steps": 81000}
    assert report["selection"]["picked"]["candidate"] == 0
    assert not report["validated_selection"] and not report["source_git_verification_enabled"]
    assert report["audit_sources_sha256"]["auditor"] == audit.file_hash(Path(audit.__file__))
    assert report["audit_sources_sha256"]["common"] == audit.file_hash(audit.COMMON_PATH)


def test_stdlib_fatal_paid_schema_blocks_all_remaining_and_has_no_pick(tmp_path):
    path = make_archive(tmp_path/"fatal", fatal=True)
    report = audit.audit(path, git_root=None, spec=audit.DRAFT_SPEC)
    assert report["failed_checks"] == 2, report["violations"]
    assert report["budget"] == {"control_calls_attempted": 101, "control_steps": 100, "physics_steps": 1003}
    assert report["trials"][0]["actual_missing_substeps"]["control"] == 3
    assert all(row["status"] == "blocked" for row in report["trials"][1:])
    assert report["selection"]["status"] == "blocked" and report["selection"]["picked"] is None


def test_partial_and_missing_history_primitives_retain_costs_and_window_denominators():
    plan, checks = audit.planned_matrix()[0], audit.Checks()
    state, ranges, previous = audit._state(plan), public_ranges(), obs([0.]*8)
    for index in range(100):
        row = make_row(plan, index, previous)
        audit.consume_return(row, state, ranges, checks)
        previous = row["observation_after"]
    terminal = make_row(plan, 100, previous, stop=True, partial=True, missing=True)
    audit.consume_return(terminal, state, ranges, checks)
    assert checks.failed == 0, checks.violations
    assert state["budgets"]["control"] == {"control_calls_attempted": 1, "control_steps": 1, "physics_steps": 3}
    assert state["effort"]["control"]["requested_squared_nm2_s"] == pytest.approx([.0015, .0015])
    assert state["actual_substeps"]["control"] == 0
    assert state["tracking"] == [] and len(state["partial"]) == 1
    assert audit.tail_windows(state["endpoints"])["segment0"]["missing_complete_count"] == 100


def test_returned_unwritten_trace_fault_is_one_paid_return_and_not_double_counted():
    plan, checks = audit.planned_matrix()[0], audit.Checks()
    state, ranges, previous = audit._state(plan), public_ranges(), obs([0.]*8)
    for index in range(100):
        row = make_row(plan, index, previous)
        audit.consume_return(row, state, ranges, checks)
        previous = row["observation_after"]
    terminal = make_row(plan, 100, previous)
    failed = {key: value for key, value in terminal.items() if key not in ("diagnostics", "observation_after")}
    failed.update(collector_exception={"type": "ValueError", "message": "synthetic trace write failure"},
                  returned_step_diagnostics=terminal["diagnostics"], returned_observation_after=terminal["observation_after"],
                  returned_control_steps=101, trace_rows_written=100)
    audit.consume_exception(failed, state, ranges, checks)
    assert checks.failed == 0, checks.violations
    assert state["returned"] == 101 and state["normal_rows"] == 100
    assert state["budgets"]["control"]["physics_steps"] == 10 and len(state["tracking"]) == 1
    assert state["exception_returns"][0]["n"] == 10


def test_selection_all_seed_completion_exact_hierarchy_and_missing_no_pick():
    trials = []
    for plan in audit.planned_matrix():
        trials.append({**plan, "eligible": plan["candidate"] in (0, 1), "complete": True, "status": "completed",
            "tracking": {"joint": .1, "per_axis": [.1, .1]}, "actual_squared_control_effort": 1.,
            "budget": {"control_calls_attempted": 300, "control_steps": 300, "physics_steps": 3000}})
    assert audit.select_candidates(trials)["picked"]["candidate"] == 0
    changed = copy.deepcopy(trials)
    for row in changed:
        if row["candidate"] == 1:
            row["tracking"]["joint"] = math.nextafter(.1, 0.)
            row["tracking"]["per_axis"] = [.9, .9]
            row["actual_squared_control_effort"] = 100.
    assert audit.select_candidates(changed)["picked"]["candidate"] == 1
    changed = copy.deepcopy(trials)
    for row in changed:
        if row["candidate"] in (0, 1):
            row["tracking"]["joint"] = float(row["seed"]+1) if row["candidate"] == 0 else 2.
        if row["candidate"] == 1:
            row["tracking"]["per_axis"] = [.09, .09]
            row["actual_squared_control_effort"] = 100.
    assert audit.select_candidates(changed)["picked"]["candidate"] == 1
    changed = copy.deepcopy(trials)
    for row in changed:
        if row["candidate"] == 1:
            row["actual_squared_control_effort"] = .9
    assert audit.select_candidates(changed)["picked"]["candidate"] == 1
    changed = copy.deepcopy(trials)
    changed[0]["eligible"] = changed[1]["eligible"] = False
    assert audit.select_candidates(changed)["picked"] is None


def test_selection_worst_seed_disagrees_with_worst_axis_order():
    # A: joint RMSE 1/2/3 across seeds, errors on alternating axes.
    # B: joint RMSE 2/2/2, errors always on axis0. Mean joint ties at2;
    # worst seed3 vs2 chooses B, while largest axis mean chooses A.
    trials = []
    for plan in audit.planned_matrix():
        candidate, seed = plan["candidate"], plan["seed"]
        joint = float(seed+1) if candidate == 0 else 2.
        axis = [joint*math.sqrt(2.), 0.] if candidate != 0 or seed != 1 else [0., joint*math.sqrt(2.)]
        trials.append({**plan, "eligible": candidate in (0, 1), "complete": True, "status": "completed",
            "tracking": {"joint": joint, "per_axis": axis}, "actual_squared_control_effort": 1. if candidate == 0 else 100.,
            "budget": {"control_calls_attempted": 300, "control_steps": 300, "physics_steps": 3000}})
    assert 4*math.sqrt(2.)/3 < 2*math.sqrt(2.)
    selected = audit.select_candidates(trials)
    assert selected["picked"]["candidate"] == 1
    assert selected["candidates"][0]["sort_key"] == [2., 3., 1., 0]
    assert selected["candidates"][1]["sort_key"] == [2., 2., 100., 1]


def test_counter_forgery_and_future_target_preview_are_detected_by_independent_replay():
    plan, checks = audit.planned_matrix()[0], audit.Checks()
    state, ranges, previous = audit._state(plan), public_ranges(), obs([0.]*8)
    for index in range(100):
        row = make_row(plan, index, previous)
        audit.consume_return(row, state, ranges, checks)
        previous = row["observation_after"]
    row = make_row(plan, 100, previous)
    row["target_q_rad"] = [.08, .0795]
    row["physics_steps_after"] = 1009
    audit.consume_return(row, state, ranges, checks)
    assert checks.failed > 0
    assert any("current_target_no_preview" in str(item["location"]) for item in checks.violations)
    assert any("paid_counters" in str(item["location"]) for item in checks.violations)
