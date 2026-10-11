"""Independent standard-library fixed shoulder/elbow PD development audit.

No collector, controller, environment, NumPy, MuJoCo or learning code is
imported. Scope is selected from immutable source declarations before logs
are read. Git=None supports engineering diagnostics, never validation.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
import gzip
import hashlib
import importlib.util
from itertools import product
import json
import math
from pathlib import Path, PurePosixPath
import platform
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
import zipfile


ROOT = next(p for p in Path(__file__).resolve().parents if (p/"pyproject.toml").is_file())
COMMON_PATH = ROOT/"scripts/audit_local_frozen.py"
_loader = importlib.util.spec_from_file_location("_pair_pd_common_audit", COMMON_PATH)
common = importlib.util.module_from_spec(_loader)
sys.modules[_loader.name] = common
_loader.loader.exec_module(common)
Checks, finite, vector = common.Checks, common.finite, common.vector
file_hash, load_json = common.file_hash, common.load_json
SEEDS = (0, 1, 2)
RESET_SEEDS = {0: 3757552657, 1: 1641411168, 2: 2001025171}
KP = (64., 64.)
KD = tuple(product((0., 1., 2.), (1., 2., 4.)))
PHASES = ("prefix", "control")
BUDGET_KEYS = ("control_calls_attempted", "control_steps", "physics_steps")
EFFORT_KEYS = common.EFFORT_KEYS
NATIVE, ENVIRONMENT, ASSET, JOINTS = common.NATIVE, common.ENVIRONMENT, common.ASSET, common.JOINTS
DT = .002


@dataclass(frozen=True)
class PairPDAuditSpec:
    """Only exact production/draft paths vary; numerical scope never varies."""
    synthetic_fixture: bool = False
    scientific_frozen: bool = False

    def __post_init__(self):
        if type(self.synthetic_fixture) is not bool or type(self.scientific_frozen) is not bool:
            raise ValueError("exact boolean source scope required")
        if self.synthetic_fixture and self.scientific_frozen:
            raise ValueError("synthetic fixture cannot freeze scientific adoption")

    @property
    def suite(self):
        return "pair_pd_development"

    @property
    def protocol(self):
        return "docs/PAIR_PD_DEVELOPMENT_PROTOCOL.md"

    @property
    def collector(self):
        return "src/developmental_physics/pair_pd_development.py"

    @property
    def auditor(self):
        return "scripts/audit_pair_pd.py"

    @property
    def required_sources(self):
        return common.BASE_REQUIRED_SOURCES | {
            self.protocol, self.collector, self.auditor, "scripts/audit_local_frozen.py",
            "src/developmental_physics/elbow_feedback_validate.py",
            "src/developmental_physics/local_coverage_ablation.py",
        }

    def record(self):
        return {"synthetic_fixture": self.synthetic_fixture, "scientific_frozen": self.scientific_frozen,
                "suite": self.suite, "protocol": self.protocol, "collector": self.collector,
                "auditor": self.auditor, "seeds": list(SEEDS), "kp": list(KP),
                "kd_candidates": [list(pair) for pair in KD], "prefix_steps": 100,
                "control_steps": 200, "joint_indices": [0, 1], "pose": "supine", "split": "development"}


PRODUCTION_SPEC = PairPDAuditSpec(scientific_frozen=True)
DRAFT_SPEC = PairPDAuditSpec(synthetic_fixture=True)


def planned_matrix():
    return [{"trial_id": f"seed{seed}_candidate{i}", "seed": seed, "candidate": i,
             "kp": list(KP), "kd": list(kd), "maximum_control_steps": 300}
            for seed in SEEDS for i, kd in enumerate(KD)]


def _count(value):
    if type(value) is not int or value < 0:
        raise ValueError("nonnegative integer count required")
    return value


def _native(obs, *, allow_invalid=False):
    if not isinstance(obs, dict) or set(obs) != set(NATIVE):
        raise ValueError("original native observation whitelist required")
    valid = True
    for key, width in NATIVE.items():
        try:
            vector(obs[key], width)
        except ValueError:
            if not allow_invalid:
                raise
            valid = False
    return valid


def _markers(row, checks, where, *, failure):
    markers = row.get("invalid_numeric_fields", [])
    checks.check(type(markers) is list, "invalid_numeric_markers_list", where)
    checks.check(not markers or failure, "nonfinite_records_only_failed_outcomes", where)
    for marker in markers:
        checks.check(isinstance(marker, dict) and set(marker) == {"path", "value"}
                     and marker.get("value") in ("nan", "+inf", "-inf"), "invalid_numeric_marker_schema", where)
        path = marker.get("path", "")
        current = row
        try:
            if not isinstance(path, str) or not path.startswith("/"):
                raise ValueError("invalid marker pointer")
            for part in path[1:].split("/"):
                key = part.replace("~1", "/").replace("~0", "~")
                current = current[int(key)] if isinstance(current, list) else current[key]
            checks.check(current is None, "nonfinite_marker_points_to_null", where+path)
        except (KeyError, ValueError, TypeError, IndexError):
            checks.check(False, "nonfinite_marker_pointer_exists", where)
    return bool(markers)


def require_scope(path, spec):
    if not isinstance(spec, PairPDAuditSpec):
        raise ValueError("immutable declared PairPDAuditSpec required")
    metadata = load_json(Path(path)/"metadata.json")
    expected = {"suite": spec.suite, "seeds": list(SEEDS), "kp": list(KP),
                "kd_candidates": [list(pair) for pair in KD], "pose": "supine", "split": "development",
                "joint_indices": [0, 1], "native_joint_count": 8, "prefix_steps": 100,
                "control_steps_per_trial": 200, "target_offsets_rad": [.04, .08]}
    if any(metadata.get(key) != value for key, value in expected.items()):
        raise ValueError("archive differs from immutable pair-PD scope or gains")
    if (any(type(seed) is not int for seed in metadata["seeds"])
        or any(type(j) is not int for j in metadata["joint_indices"])
        or any(not finite(value) for value in metadata["kp"])
        or any(not finite(value) for pair in metadata["kd_candidates"] for value in pair)
        or any(type(metadata.get(key)) is not int for key in ("native_joint_count", "prefix_steps", "control_steps_per_trial"))
        or metadata.get("protocol", {}).get("path") != spec.protocol
        or type(metadata.get("synthetic")) is not bool
        or metadata["synthetic"] is not spec.synthetic_fixture):
        raise ValueError("invalid types or exact source declaration for pair-PD scope")
    return metadata


def verify_sources(path, metadata, checks, git_root, spec):
    manifest = load_json(path/"manifest.json")
    checks.check(set(manifest) == {p.name for p in path.iterdir() if p.is_file() and p.name != "manifest.json"}, "manifest_exact_coverage")
    checks.check({"metadata.json", "episodes.json", "selection.json", "trace.jsonl.gz", "source_snapshot.zip"}.issubset(manifest), "manifest_core_files")
    for name, sha in manifest.items():
        safe = isinstance(name, str) and Path(name).name == name and name not in (".", "..")
        checks.check(safe, "manifest_local_filename", name)
        if safe:
            checks.check((path/name).is_file() and file_hash(path/name) == sha, "manifest_hash", name)
    hashes = metadata["source_sha256"]
    checks.check(spec.required_sources.issubset(hashes), "required_source_coverage")
    checks.compare(metadata["protocol"], {"path": spec.protocol, "sha256": hashes.get(spec.protocol)}, "frozen_protocol_hash")
    checks.compare(metadata.get("auditor"), {"path": spec.auditor, "sha256": hashes.get(spec.auditor),
                                            "pending": False, "required_for_formal": True}, "independent_auditor_source_record")
    checks.compare(metadata.get("source_snapshot_sha256"), file_hash(path/"source_snapshot.zip"), "source_snapshot_hash")
    commit = metadata.get("source_commit")
    valid_commit = isinstance(commit, str) and re.fullmatch(r"[0-9a-f]{40}", commit) is not None
    checks.check(valid_commit, "source_commit_format")
    checks.check(metadata.get("source_status") == "" and metadata.get("source_dirty") is False, "clean_collection_source")
    if git_root is not None and valid_commit:
        tree = subprocess.run(["git", "ls-tree", "-r", "--name-only", commit, "src/developmental_physics"],
                              cwd=git_root, capture_output=True, text=True, check=False)
        python_sources = {name for name in tree.stdout.splitlines() if name.endswith(".py") and name.count("/") == 2}
        checks.check(tree.returncode == 0 and python_sources.issubset(hashes), "all_package_sources_archived")
    with zipfile.ZipFile(path/"source_snapshot.zip") as archive:
        names = archive.namelist()
        checks.check(len(names) == len(set(names)) and set(names) == set(hashes), "source_zip_exact_unique_coverage")
        git_blobs = {}
        for name, sha in hashes.items():
            pure = PurePosixPath(name)
            safe = (not pure.is_absolute() and ".." not in pure.parts and "\\" not in name
                    and ":" not in name and not name.startswith("/"))
            checks.check(safe, "source_relative_path", name)
            blob = archive.read(name)
            checks.check(hashlib.sha256(blob).hexdigest() == sha, "source_zip_hash", name)
            git_blobs[name] = hashlib.sha1(b"blob "+str(len(blob)).encode("ascii")+b"\0"+blob).hexdigest()
            if git_root is not None and valid_commit and safe:
                result = subprocess.run(["git", "show", f"{commit}:{name}"], cwd=git_root, capture_output=True, check=False)
                checks.check(result.returncode == 0 and result.stdout == blob, "source_git_blob_bytes", name)
        if valid_commit:
            checks.compare(metadata.get("source_git_blobs"), git_blobs, "zip_matches_recorded_git_blob_ids")
        else:
            checks.check(spec.synthetic_fixture and metadata.get("source_git_blobs") == {}, "unresolved_synthetic_git_is_explicit")
        checks.check(hashes.get(spec.auditor) == file_hash(Path(__file__)), "runtime_auditor_matches_archived_source")
        checks.check(hashes.get("scripts/audit_local_frozen.py") == file_hash(COMMON_PATH), "runtime_common_matches_archived_source")
        xml = ET.fromstring(archive.read(ASSET))
    compiler = xml.find("compiler")
    factor = math.pi/180. if compiler is None or compiler.get("angle", "degree") == "degree" else 1.
    joint_ranges = {joint.get("name"): [float(x)*factor for x in joint.get("range").split()]
                    for joint in xml.findall(".//joint") if joint.get("range")}
    ranges = [vector(joint_ranges[name], 2) for name in JOINTS]
    checks.check(all(low < high for low, high in ranges), "ordered_asset_public_joint_ranges")
    return ranges, {**manifest, "manifest.json": file_hash(path/"manifest.json")}


def pd_action(q, v, target, kd):
    q, v, target, kd = (vector(list(value) if isinstance(value, tuple) else value, 2) for value in (q, v, target, kd))
    raw = [64.*(target[i]-q[i])-kd[i]*v[i] for i in range(2)]
    if not all(finite(value) for value in raw):
        raise ValueError("independent PD arithmetic overflowed")
    return [max(-.5, min(.5, value)) for value in raw], raw


def _direction(qref, ranges):
    choices = []
    for i in range(2):
        q, (lower, upper) = qref[i], ranges[i]
        positive, negative = upper-q, q-lower
        choices.append({"joint_index": i, "joint_position_rad": q, "lower_limit_rad": lower,
                        "upper_limit_rad": upper, "positive_room_rad": positive, "negative_room_rad": negative,
                        "direction": 1 if positive >= negative else -1,
                        "rule": "larger distance to the public joint limit; ties choose positive"})
    return choices


def study_abort(q, v, qref, index):
    triggers = []
    for i in range(2):
        if abs(q[i]-qref[i]) >= .12:
            triggers.append({"joint_index": i, "signal": "absolute_q_minus_qref_rad"})
        if abs(v[i]) >= 1.:
            triggers.append({"joint_index": i, "signal": "absolute_velocity_rad_s"})
    return None if not triggers else {"type": "StudyAbort", "triggers": triggers, "q_rad": list(q),
        "qref_rad": list(qref), "velocity_rad_s": list(v),
        "thresholds": {"absolute_q_minus_qref_rad": .12, "absolute_velocity_rad_s": 1.},
        "feedback_action": None, "phase": "control", "step_index": index, "active_index": index-100}


def pair_tracking(errors):
    if not errors:
        return None
    for error in errors:
        vector(error, 2)
    return {"joint": common.rmse([x for row in errors for x in row]),
            "per_axis": [common.rmse([row[i] for row in errors]) for i in range(2)],
            "complete_endpoints": len(errors)}


def tail_windows(endpoints):
    result = {}
    for name, start, end in (("segment0", 0, 100), ("segment1", 100, 200),
                             ("segment0_last20", 80, 100), ("segment1_last20", 180, 200)):
        returned = [row for row in endpoints if start <= row["active_index"] < end]
        errors = [row["error_rad"] for row in returned if row["complete_transition"]]
        complete = len(errors)
        result[name] = {"planned_active_index_start": start, "planned_active_index_end_exclusive": end,
            "planned_count": end-start, "returned_count": len(returned), "complete_count": complete,
            "partial_count": len(returned)-complete, "missing_returned_count": end-start-len(returned),
            "missing_complete_count": end-start-complete, "tracking": pair_tracking(errors),
            "signed_mean_error_rad": [math.fsum(row[i] for row in errors)/complete for i in range(2)] if errors else None,
            "returned_endpoints": returned}
    return result


def new_risk():
    return {"peak_ground_force_n": 0., "ground_normal_impulse_ns": 0., "peak_kinetic_energy_j": 0.,
            "minimum_contact_distance_m": 0., "max_native_speed_rad_s": 0., "guarded_substeps": 0,
            "outside_public_limit_endpoint_count": 0}


def add_risk(risk, diagnostic, after, ranges):
    n = _count(diagnostic["executed_substeps"])
    force, energy, distance = [vector(diagnostic[key], n) for key in
                              ("substep_ground_normal_forces", "substep_kinetic_energies", "substep_minimum_contact_distances")]
    if any(value < 0. for value in force+energy):
        raise ValueError("nonnegative force and energy required")
    q, v = vector(after["joint_position"], 8), vector(after["joint_velocity"], 8)
    guarded = _count(diagnostic["guarded_substeps"])
    if guarded > n:
        raise ValueError("guarded substeps exceed paid samples")
    risk["peak_ground_force_n"] = max(risk["peak_ground_force_n"], *force, 0.)
    risk["ground_normal_impulse_ns"] += sum(force)*DT
    risk["peak_kinetic_energy_j"] = max(risk["peak_kinetic_energy_j"], *energy, 0.)
    risk["minimum_contact_distance_m"] = min(risk["minimum_contact_distance_m"], *distance, 0.)
    risk["max_native_speed_rad_s"] = max(risk["max_native_speed_rad_s"], *[abs(x) for x in v])
    risk["guarded_substeps"] += guarded
    risk["outside_public_limit_endpoint_count"] += int(any(q[i] < limits[0] or q[i] > limits[1] for i, limits in enumerate(ranges)))


def _state(plan):
    return {"plan": plan, "normal_rows": 0, "returned": 0, "exceptions": [], "last_observation": None,
            "qref": None, "choices": None, "study": None, "environment_terminated": False, "environment_reason": None,
            "invalid": False, "endpoints": [], "tracking": [], "partial": [], "unreturned": 0,
            "budgets": {p: dict.fromkeys(BUDGET_KEYS, 0) for p in PHASES},
            "complete": dict.fromkeys(PHASES, 0), "history_issues": [], "exception_returns": [],
            "effort": {p: {key: [0., 0.] for key in EFFORT_KEYS} for p in PHASES},
            "actual_substeps": dict.fromkeys(PHASES, 0), "risk_substeps": 0,
            "risks": {p: new_risk() for p in ("full", *PHASES)}, "saturation": [0, 0], "pd_success_calls": 0}


def _action(row, state, ranges, checks, where, *, before_step_failure=False):
    index, before = _count(row["control_index"]), row["observation_before"]
    _native(before)
    checks.check(state["last_observation"] is None or before == state["last_observation"], "exact_native_chain", where)
    phase = "prefix" if index < 100 else "control"
    checks.compare(row["phase"], phase, where+"/fixed_phase")
    q, v = before["joint_position"][:2], before["joint_velocity"][:2]
    if index == 100:
        state["qref"], state["choices"] = list(q), _direction(q, ranges)
    request = vector(row["requested_torque"], 8)
    expected = [0.]*8
    if phase == "prefix":
        checks.compare(row.get("target_q_rad"), None, where+"/prefix_target")
        checks.compare(row.get("raw_pd_torque_nm"), None, where+"/prefix_pd")
    else:
        if state["qref"] is None:
            raise ValueError("control has no own paid prefix reference")
        target = [state["qref"][i]+state["choices"][i]["direction"]*(.04 if index < 200 else .08) for i in range(2)]
        if before_step_failure and row.get("target_q_rad") is None:
            feasible = all(ranges[i][0]+.03 <= state["qref"][i]+state["choices"][i]["direction"]*offset <= ranges[i][1]-.03
                           for i in range(2) for offset in (.04, .08))
            checks.check(not feasible, "target_rejection_requires_actual_infeasibility", where)
            checks.compare(row.get("raw_pd_torque_nm"), None, where+"/infeasible_before_pd")
            checks.compare(request, expected, where+"/infeasible_no_requested_action")
            return phase, request
        checks.compare(row.get("target_q_rad"), target, where+"/current_target_no_preview")
        command, raw = pd_action(q, v, target, state["plan"]["kd"])
        if before_step_failure:
            checks.compare(row.get("raw_pd_torque_nm"), None, where+"/failed_before_step_no_completed_pd")
        else:
            checks.compare(row.get("raw_pd_torque_nm"), raw, where+"/independent_pd_raw")
            expected[:2] = command
            state["pd_success_calls"] += 1
    checks.compare(request, expected, where+"/independent_original_8d_request")
    checks.check(all(abs(value) <= .5 for value in request[:2]) and all(value == 0. for value in request[2:]), "shared_permission_and_other_six_zero", where)
    return phase, request


def _actual(diagnostic, request, before, ranges, checks, where, *, failure):
    n = diagnostic["executed_substeps"]
    if "applied_torque_history" not in diagnostic:
        return None
    try:
        history = diagnostic["applied_torque_history"]
        if not isinstance(history, list) or len(history) != n:
            raise ValueError("actual history substep shape")
        for row in history:
            vector(row, 8)
            if any(abs(value) > .5 for value in row):
                raise ValueError("actual history permission")
    except (ValueError, TypeError):
        checks.check(failure, "invalid_actual_history_only_failed_trial", where)
        return "invalid"
    for sample in history:
        checks.check(all(value == request[i] or value == 0. for i, value in enumerate(sample)), "actual_guard_only_zero_or_request", where)
    if history:
        q = before["joint_position"]
        start = [0. if (q[i] <= ranges[i][0]+.03 and request[i] < 0.) or
                 (q[i] >= ranges[i][1]-.03 and request[i] > 0.) else request[i] for i in range(8)]
        checks.compare(history[0], start, where+"/known_control_start_guard")
    checks.compare(diagnostic["guarded_substeps"], sum(any(sample[i] != request[i] for i in range(8)) for sample in history), where+"/guard_count_from_actual_history")
    return history


def _add_actual(state, phase, history):
    for i in range(2):
        state["effort"][phase]["actual_absolute_nm_s"][i] += sum(abs(row[i]) for row in history)*DT
        state["effort"][phase]["actual_squared_nm2_s"][i] += sum(row[i]**2 for row in history)*DT
    state["actual_substeps"][phase] += len(history)


def consume_return(row, state, ranges, checks, *, exception=False):
    where = state["plan"]["trial_id"]+"/"+str(row.get("control_index"))
    phase, request = _action(row, state, ranges, checks, where)
    index = row["control_index"]
    checks.check(index == state["returned"] and index < 300, "sequential_control_index", where)
    checks.check(not state["study"] and not state["environment_terminated"], "no_action_after_any_stop", where)
    before_calls = sum(b["control_steps"] for b in state["budgets"].values())
    before_physics = sum(b["physics_steps"] for b in state["budgets"].values())
    diagnostic = row["diagnostics"]
    n = _count(diagnostic["executed_substeps"])
    checks.check(n <= 10, "substep_permission_bound", where)
    checks.compare(row, {"control_steps_before": before_calls, "control_steps_after": before_calls+1,
                         "physics_steps_before": before_physics, "physics_steps_after": before_physics+n}, where+"/paid_counters")
    state["budgets"][phase]["control_calls_attempted"] += 1
    state["budgets"][phase]["control_steps"] += 1
    state["budgets"][phase]["physics_steps"] += n
    for i in range(2):
        state["effort"][phase]["requested_absolute_nm_s"][i] += abs(request[i])*n*DT
        state["effort"][phase]["requested_squared_nm2_s"][i] += request[i]**2*n*DT
    state["returned"] += 1
    if not exception:
        state["normal_rows"] += 1
    checks.compare(diagnostic, {"step_id": before_calls+1, "physics_steps": before_physics+n,
                               "time": (before_physics+n)*DT, "requested_torque": request,
                               "accepted_torque": request}, where+"/native_diagnostic_counters")
    checks.check(type(diagnostic.get("terminated")) is bool and (n == 10 or diagnostic.get("terminated") is True), "partial_requires_environment_stop", where)
    state["environment_terminated"] = diagnostic["terminated"]
    state["environment_reason"] = diagnostic.get("reason")
    checks.compare(row.get("environment_terminated"), diagnostic["terminated"], where+"/environment_stop_flag")
    checks.compare(row.get("environment_stop_reason"), diagnostic.get("reason"), where+"/environment_reason")
    checks.compare(row.get("complete_transition"), n == 10, where+"/complete_interval")
    after = row["observation_after"]
    native_valid = _native(after, allow_invalid=exception)
    state["invalid"] = state["invalid"] or not native_valid
    qvel_valid = all(isinstance(after.get(key), list) and len(after[key]) == 8 and all(finite(x) for x in after[key]) for key in ("joint_position", "joint_velocity"))
    if not exception:
        vector(row.get("qpos"), 15)
        vector(row.get("qvel"), 14)
    if qvel_valid:
        checks.compare(row.get("qpos", [])[7:], after["joint_position"], where+"/qpos_native_mapping")
        checks.compare(row.get("qvel", [])[6:], after["joint_velocity"], where+"/qvel_native_mapping")
        state["complete"][phase] += int(n == 10)
        if phase == "control":
            errors = [after["joint_position"][i]-row["target_q_rad"][i] for i in range(2)]
            endpoint = {"active_index": index-100, "error_rad": errors, "complete_transition": n == 10}
            state["endpoints"].append(endpoint)
            if n == 10:
                state["tracking"].append(errors)
                state["saturation"] = [state["saturation"][i]+int(abs(request[i]) == .5) for i in range(2)]
            else:
                state["partial"].append({"active_index": index-100, "error_rad": errors})
            state["study"] = study_abort(after["joint_position"][:2], after["joint_velocity"][:2], state["qref"], index)
        checks.compare(row.get("partial_interval_target_error_rad"), errors if phase == "control" and n != 10 else None, where+"/partial_error_not_scored")
    checks.compare(row.get("study_abort"), state["study"], where+"/independent_study_stop")
    history = _actual(diagnostic, request, row["observation_before"], ranges, checks, where, failure=exception)
    if history is None:
        issue = {"type": "ActualHistoryMissing", "phase": phase, "control_index": index, "missing_substeps": n}
        state["history_issues"].append(issue)
        if not exception:
            checks.compare(row.get("actual_history_issue"), issue, where+"/explicit_missing_actual_history")
    elif not exception:
        _add_actual(state, phase, history)
        checks.compare(row.get("actual_history_issue"), None, where+"/complete_actual_history")
    risk_valid = True
    try:
        risk_check = new_risk()
        add_risk(risk_check, diagnostic, after, ranges)
        checks.compare(diagnostic, {"peak_substep_ground_normal_force": max(diagnostic["substep_ground_normal_forces"], default=0.),
            "ground_normal_impulse_ns": sum(diagnostic["substep_ground_normal_forces"])*DT,
            "peak_substep_kinetic_energy": max(diagnostic["substep_kinetic_energies"], default=0.),
            "minimum_substep_contact_distance": min(diagnostic["substep_minimum_contact_distances"], default=0.)}, where+"/substep_risk_reduction")
    except (ValueError, KeyError, TypeError):
        risk_valid = False
        checks.check(exception, "invalid_risk_only_failed_trial", where)
    if exception:
        state["exception_returns"].append({"phase": phase, "n": n, "history": history,
                                          "risk_valid": risk_valid, "diagnostic": diagnostic, "after": after})
    else:
        for p in ("full", phase):
            add_risk(state["risks"][p], diagnostic, after, ranges)
        state["risk_substeps"] += n
    state["last_observation"] = after


def consume_exception(row, state, ranges, checks):
    where = state["plan"]["trial_id"]+"/exception"
    state["exceptions"].append(row)
    checks.check(len(state["exceptions"]) == 1, "one_terminal_exception_record", where)
    checks.check(isinstance(row.get("collector_exception"), dict), "explicit_collector_exception", where)
    returned = row.get("returned_step_diagnostics")
    index = row.get("control_index")
    if returned is not None:
        if index == state["returned"]-1:
            checks.compare(row.get("returned_control_steps"), state["returned"], where+"/duplicate_saved_return")
            checks.compare(row.get("trace_rows_written"), state["normal_rows"], where+"/duplicate_saved_trace_count")
            return
        recovered = dict(row)
        recovered.update(diagnostics=returned, observation_after=row["returned_observation_after"],
                         environment_terminated=returned["terminated"], environment_stop_reason=returned.get("reason"),
                         complete_transition=returned["executed_substeps"] == 10)
        consume_return(recovered, state, ranges, checks, exception=True)
        return
    if index is None or row.get("observation_before") is None:
        checks.check(all(row.get(key) is None for key in ("control_steps_before", "physics_steps_before")), "setup_exception_has_no_paid_step", where)
        return
    before_step = row.get("control_steps_before") is None
    phase, request = _action(row, state, ranges, checks, where, before_step_failure=before_step)
    checks.check(index == state["returned"], "exception_next_planned_index", where)
    if before_step:
        checks.compare(row.get("physics_steps_before"), None, where+"/before_step_no_physics_counter")
        return
    before_calls = sum(b["control_steps"] for b in state["budgets"].values())
    before_physics = sum(b["physics_steps"] for b in state["budgets"].values())
    checks.compare(row, {"control_steps_before": before_calls, "physics_steps_before": before_physics}, where+"/before_unreturned_paid_step")
    dc = _count(row["control_steps_after"])-before_calls
    dp = _count(row["physics_steps_after"])-before_physics
    checks.check(dc in (0, 1) and 0 <= dp <= 10, "unreturned_paid_delta_bounds", where)
    state["budgets"][phase]["control_calls_attempted"] += 1
    state["budgets"][phase]["control_steps"] += dc
    state["budgets"][phase]["physics_steps"] += dp
    state["unreturned"] += dp
    for i in range(2):
        state["effort"][phase]["requested_absolute_nm_s"][i] += abs(request[i])*dp*DT
        state["effort"][phase]["requested_squared_nm2_s"][i] += request[i]**2*dp*DT


def finish_trial(ep, state, ranges, checks):
    where, plan = ep["trial_id"], state["plan"]
    checks.compare(ep, plan, where+"/exact_plan")
    checks.check(ep.get("status") in ("completed", "terminated", "exception", "blocked"), "declared_outcome", where)
    if ep.get("status") == "blocked":
        checks.check(state["returned"] == 0 and not state["exceptions"] and ep.get("complete") is False, "blocked_has_no_work", where)
        checks.compare(ep["phase_budgets"], state["budgets"], where+"/blocked_zero_budgets")
        checks.compare(ep, dict.fromkeys(BUDGET_KEYS, 0), where+"/blocked_zero_cost")
        checks.compare(ep.get("reason"), {"type": "ArchiveAborted", "message": "not attempted after fatal archive failure"}, where+"/blocked_fatal_reason")
        return {**plan, "eligible": False, "complete": False, "status": "blocked", "tracking": None,
                "actual_squared_control_effort": None, "budget": dict.fromkeys(BUDGET_KEYS, 0)}
    checks.compare(ep.get("reset_seed"), RESET_SEEDS[plan["seed"]], where+"/seed_derivation")
    checks.compare(ep.get("public_joint_ranges_rad"), ranges, where+"/public_ranges_from_archived_asset")
    checks.compare(ep["phase_budgets"], state["budgets"], where+"/independent_phase_paid_budgets")
    budgets = {key: sum(state["budgets"][p][key] for p in PHASES) for key in BUDGET_KEYS}
    checks.compare(ep, budgets, where+"/independent_paid_totals")
    for p, cap in (("prefix", 100), ("control", 200)):
        b = state["budgets"][p]
        checks.check(b["control_calls_attempted"] <= cap and b["control_steps"] <= b["control_calls_attempted"]
                     and b["physics_steps"] <= b["control_calls_attempted"]*10, "fixed_trial_phase_budget_cap", where+"/"+p)
    checks.compare(ep.get("prefix_end_q_rad"), state["qref"], where+"/own_paid_prefix_qref")
    checks.compare(ep.get("selection_records"), state["choices"], where+"/public_fixed_direction")
    if state["qref"] is not None and state["returned"] > 100:
        checks.check(all(ranges[i][0]+.03 <= state["qref"][i]+state["choices"][i]["direction"]*offset <= ranges[i][1]-.03
                         for i in range(2) for offset in (.04, .08)), "unclipped_feasible_targets", where)
    for recovered in state["exception_returns"]:
        p, n, history = recovered["phase"], recovered["n"], recovered["history"]
        actual_extra = ep["phase_actual_effort_substeps"][p]-state["actual_substeps"][p]
        checks.check(actual_extra in (0, n), "exception_actual_committed_whole_return_or_none", where)
        if actual_extra:
            checks.check(isinstance(history, list), "exception_actual_commit_requires_valid_history", where)
            if isinstance(history, list):
                _add_actual(state, p, history)
        risk_extra = ep["observed_diagnostic_substeps"]-state["risk_substeps"]
        checks.check(risk_extra in (0, n), "exception_risk_committed_whole_return_or_none", where)
        if risk_extra:
            checks.check(recovered["risk_valid"], "exception_risk_commit_requires_valid_samples", where)
            if recovered["risk_valid"]:
                for phase in ("full", p):
                    add_risk(state["risks"][phase], recovered["diagnostic"], recovered["after"], ranges)
                state["risk_substeps"] += n
    actual_missing = {p: state["budgets"][p]["physics_steps"]-state["actual_substeps"][p] for p in PHASES}
    actual_complete = not any(actual_missing.values())
    checks.compare(ep.get("phase_effort"), state["effort"], where+"/independent_paid_effort")
    checks.compare(ep.get("phase_effort_combined"), {p: {key: sum(state["effort"][p][key]) for key in EFFORT_KEYS} for p in PHASES}, where+"/two_axis_effort_sums")
    checks.compare(ep, {"phase_actual_effort_substeps": state["actual_substeps"],
        "phase_actual_effort_complete": {p: actual_missing[p] == 0 for p in PHASES},
        "phase_actual_effort_missing_substeps": actual_missing, "actual_effort_complete": actual_complete,
        "actual_effort_is_lower_bound": not actual_complete, "actual_history_issues": state["history_issues"],
        "returned_control_steps": state["returned"], "trace_rows_written": state["normal_rows"],
        "returned_unstored_control_steps": state["returned"]-state["normal_rows"], "unreturned_physics_steps": state["unreturned"],
        "phase_complete_transition_counts": state["complete"], "metric_control_step_count": len(state["tracking"]),
        "tracking": pair_tracking(state["tracking"]), "complete_tracking_errors_rad": state["tracking"],
        "tracking_windows": tail_windows(state["endpoints"]), "partial_interval_target_errors_rad": state["partial"],
        "partial_interval_target_error_count": len(state["partial"]), "saturated_control_steps_per_axis": state["saturation"],
        "phase_risk": state["risks"], "observed_diagnostic_substeps": state["risk_substeps"],
        "telemetry_complete_for_paid_substeps": state["risk_substeps"] == budgets["physics_steps"],
        "study_abort": state["study"], "environment_terminated": state["environment_terminated"],
        "environment_stop_reason": state["environment_reason"]}, where+"/independent_raw_reductions")
    exception = state["exceptions"][0].get("collector_exception") if state["exceptions"] else None
    checks.compare(ep.get("collector_exception"), exception, where+"/exception_record_matches_episode")
    terminated = state["environment_terminated"] or state["study"] is not None
    complete = (exception is None and not terminated and budgets["control_steps"] == 300
                and budgets["physics_steps"] == 3000 and state["complete"] == {"prefix": 100, "control": 200}
                and state["returned"] == state["normal_rows"] == 300 and state["risk_substeps"] == 3000)
    status = "exception" if exception else "terminated" if terminated else "completed"
    checks.compare(ep.get("complete"), complete, where+"/complete_terminal_never_complete")
    checks.compare(ep.get("status"), status, where+"/independent_outcome")
    reason = state["environment_reason"] if state["environment_terminated"] else state["study"] if state["study"] else exception
    checks.compare(ep.get("reason"), reason, where+"/environment_reason_priority")
    checks.compare(ep.get("risk_telemetry_complete"), exception is None and ep.get("trace_write_failure") is None
                   and state["unreturned"] == 0 and state["risk_substeps"] == budgets["physics_steps"], where+"/risk_known_scope")
    failed_pd = int(bool(state["exceptions"] and state["exceptions"][0].get("control_steps_before") is None
                         and state["exceptions"][0].get("phase") == "control"
                         and state["exceptions"][0].get("raw_pd_torque_nm") is None
                         and state["exceptions"][0].get("target_q_rad") is not None))
    checks.compare(ep.get("pd_action_calls"), state["pd_success_calls"]+failed_pd, where+"/paid_and_failed_pd_calls")
    checks.compare(ep.get("failed_pd_attempts"), failed_pd, where+"/failed_before_step_pd_count")
    checks.check(finite(ep.get("pd_action_seconds")) and ep["pd_action_seconds"] >= 0., "finite_pd_timing", where)
    fingerprint = ep.get("environment_fingerprint_before")
    checks.check(isinstance(fingerprint, str) and bool(fingerprint) and ep.get("environment_fingerprint_after") == fingerprint, "unchanged_environment_fingerprint", where)
    if not ep.get("status") == "blocked" and not state["invalid"]:
        checks.check(not ep.get("invalid_numeric_fields"), "finite_episode_metrics", where)
    eligible = complete and actual_complete and not state["invalid"]
    return {**plan, "eligible": eligible, "complete": complete, "status": status,
            "tracking": pair_tracking(state["tracking"]),
            "actual_squared_control_effort": sum(state["effort"]["control"]["actual_squared_nm2_s"]),
            "budget": budgets, "actual_missing_substeps": actual_missing}


def select_candidates(trials):
    records = []
    for candidate, kd in enumerate(KD):
        rows = [row for row in trials if row["candidate"] == candidate]
        eligible = (len(rows) == 3 and {r["seed"] for r in rows} == set(SEEDS)
                    and all(r["eligible"] for r in rows))
        sort_key = None
        if eligible:
            sort_key = [math.fsum(r["tracking"]["joint"] for r in rows)/3,
                        max(r["tracking"]["joint"] for r in rows),
                        math.fsum(r["actual_squared_control_effort"] for r in rows)/3, candidate]
        records.append({"candidate": candidate, "kp": list(KP), "kd": list(kd), "eligible": eligible,
                        "sort_key": sort_key, "paid_control_steps": sum(r["budget"]["control_steps"] for r in rows),
                        "paid_physics_steps": sum(r["budget"]["physics_steps"] for r in rows)})
    eligible = [row for row in records if row["eligible"]]
    picked = min(eligible, key=lambda row: row["sort_key"]) if eligible else None
    return {"status": "selected" if picked else "blocked", "picked": picked, "candidates": records}


def audit(path, *, git_root=ROOT, spec=PRODUCTION_SPEC):
    """Fixed plan replay. Existing failed trials remain failed scientific cases."""
    started, cpu_started = time.perf_counter(), time.process_time()
    path, checks = Path(path), Checks()
    metadata = require_scope(path, spec)
    ranges, input_hashes = verify_sources(path, metadata, checks, git_root, spec)
    checks.compare(metadata.get("environment_config"), ENVIRONMENT, "fixed_environment_and_permission")
    checks.compare(metadata.get("planned_episodes"), planned_matrix(), "fixed_27_trial_plan")
    checks.compare(metadata, {"planned_episode_count": 27, "maximum_control_steps": 8100,
        "maximum_physics_steps": 81000, "gpu": None, "model_updates": 0,
        "parameter_updates": {"body_model": 0, "policy": 0, "gains": 0},
        "teacher_calls": 0, "external_demonstration_samples": 0,
        "pd_controller_spec": {"implementation": "feedback_validate.pd_request per original j0/j1",
                               "permission_nm": .5, "body_model_input": False, "gain_updates": 0}}, "fixed_budget_no_learning")
    checks.compare(metadata.get("study_abort_spec"), {"active_only": True, "absolute_q_minus_qref_rad": .12,
        "absolute_velocity_rad_s": 1., "comparison": ">=", "any_axis": True,
        "feedback_action": None, "complete_terminal_scored_not_complete": True}, "fixed_active_study_spec")
    checks.compare(metadata.get("backend"), "synthetic, no physics" if spec.synthetic_fixture else "MuJoCo CPU", "backend_source_disclosure")
    episodes = load_json(path/"episodes.json")
    checks.check(len(episodes) == 27 and [e["trial_id"] for e in episodes] == [p["trial_id"] for p in planned_matrix()], "exact_episode_matrix_order")
    states = {plan["trial_id"]: _state(plan) for plan in planned_matrix()}
    by_id = {episode["trial_id"]: episode for episode in episodes}
    checks.check(len(by_id) == len(episodes), "unique_trial_outcomes")
    plan_order = {plan["trial_id"]: i for i, plan in enumerate(planned_matrix())}
    last_trial = -1
    with gzip.open(path/"trace.jsonl.gz", "rt", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            row = json.loads(line)
            tid = row.get("trial_id")
            checks.check(tid in states, "known_planned_trace_trial", str(line_number))
            if tid not in states:
                continue
            checks.check(plan_order[tid] >= last_trial, "trace_follows_fixed_trial_order", str(line_number))
            last_trial = plan_order[tid]
            state = states[tid]
            for key in ("seed", "candidate", "kp", "kd"):
                checks.compare(row.get(key), state["plan"][key], tid+"/row_identity/"+key)
            exception = "collector_exception" in row
            state["invalid"] = state["invalid"] or _markers(row, checks, tid, failure=exception)
            try:
                if exception:
                    consume_exception(row, state, ranges, checks)
                else:
                    checks.check(not state["exceptions"], "no_action_after_exception", tid)
                    consume_return(row, state, ranges, checks)
            except (KeyError, ValueError, TypeError, IndexError) as exc:
                checks.check(False, "trace_schema_or_independent_replay", {"line": line_number, "trial": tid, "error": str(exc)})
                state["invalid"] = True
    trials = []
    for plan in planned_matrix():
        ep = by_id.get(plan["trial_id"])
        if ep is None:
            checks.check(False, "required_trial_outcome", plan["trial_id"])
            continue
        try:
            trials.append(finish_trial(ep, states[plan["trial_id"]], ranges, checks))
        except (KeyError, ValueError, TypeError, IndexError) as exc:
            checks.check(False, "episode_schema_or_reduction", {"trial": plan["trial_id"], "error": str(exc)})
            trials.append({**plan, "eligible": False, "complete": False, "status": ep.get("status"),
                           "tracking": None, "actual_squared_control_effort": None,
                           "budget": {key: ep.get(key, 0) for key in BUDGET_KEYS}})
    for key in BUDGET_KEYS:
        checks.compare(metadata.get(key), sum(row["budget"][key] for row in trials), "metadata_actual_"+key)
    checks.check(metadata["control_calls_attempted"] <= 8100 and metadata["control_steps"] <= 8100
                 and metadata["physics_steps"] <= 81000, "fixed_actual_budget_caps")
    statuses = Counter(ep["status"] for ep in episodes)
    for status in ("completed", "terminated", "exception", "blocked"):
        checks.compare(metadata.get(status+"_trials"), statuses[status], "metadata_status_"+status)
    checks.compare(metadata.get("all_trials_successful"), all(ep.get("complete") is True for ep in episodes), "archive_complete_not_selection")
    checks.compare(metadata.get("complete"), metadata.get("archive_status") == "complete", "archive_outcome_scope")
    blocked_started = False
    for ep in episodes:
        if ep["status"] == "blocked":
            blocked_started = True
        else:
            checks.check(not blocked_started, "fatal_blocks_all_remaining_trials", ep["trial_id"])
    if blocked_started:
        preceding = next((ep for ep in reversed(episodes[:next(i for i, ep in enumerate(episodes) if ep["status"] == "blocked")]) if ep["status"] != "blocked"), None)
        cause = {} if preceding is None else preceding.get("collector_exception") or {}
        checks.check(preceding is not None and (cause.get("type") in ("KeyboardInterrupt", "SystemExit", "OSError", "PermissionError")
                     or preceding.get("trace_write_failure") is not None or metadata.get("checkpoint_exception") is not None), "blocked_requires_actual_fatal_record")
        checks.check(metadata.get("complete") is False and metadata.get("archive_status") in ("interrupted", "failed"), "fatal_archive_not_complete")
    selection = select_candidates(trials)
    saved_selection = load_json(path/"selection.json")
    checks.compare(saved_selection.get("sort_order"), ["mean_seed_joint_rmse", "max_seed_joint_rmse",
                   "mean_seed_control_actual_squared_effort", "candidate_index"], "fixed_worst_seed_selection_order")
    checks.compare(saved_selection.get("status"), selection["status"], "independent_selection_status")
    checks.check(len(saved_selection.get("candidates", [])) == 9, "all_nine_candidates_retained")
    for actual, expected in zip(saved_selection.get("candidates", []), selection["candidates"]):
        checks.compare(actual, expected, "independent_candidate_qualification/"+str(expected["candidate"]))
        checks.check(isinstance(actual.get("qualification_failures"), list)
                     and bool(actual["qualification_failures"]) is not expected["eligible"],
                     "qualification_failures_preserved_for_every_ineligible_candidate", str(expected["candidate"]))
    if selection["picked"] is None:
        checks.compare(saved_selection.get("picked"), None, "no_eligible_no_picked")
    else:
        checks.compare(saved_selection.get("picked"), selection["picked"], "exact_independent_pick")
    checks.check(finite(metadata.get("wall_seconds")) and metadata["wall_seconds"] >= 0.
                 and finite(metadata.get("cpu_seconds")) and metadata["cpu_seconds"] >= 0., "finite_collector_timing")
    validated = (selection["picked"] is not None and checks.failed == 0 and git_root is not None
                 and spec.scientific_frozen and not spec.synthetic_fixture)
    return {"schema_version": 1, "kind": "independent stdlib pair-PD development audit",
        "created_at_utc": datetime.now(timezone.utc).isoformat(), "path": str(path), "immutable_scope": spec.record(),
        "check_count": checks.count, "failed_checks": checks.failed, "maximum_numeric_difference": checks.maximum_difference,
        "violations": checks.violations, "trials": trials, "selection": selection, "validated_selection": validated,
        "source_git_verification_enabled": git_root is not None, "input_hashes": input_hashes,
        "audit_sources_sha256": {"auditor": file_hash(Path(__file__)), "common": file_hash(COMMON_PATH)},
        "budget": {key: sum(row["budget"][key] for row in trials) for key in BUDGET_KEYS},
        "audit_cpu_seconds": time.process_time()-cpu_started, "audit_wall_seconds": time.perf_counter()-started,
        "third_party_dependencies": [], "claim_boundary": "finite fixed-Kp damping selection only; no method advantage, global optimality, skill or safety proof"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = common.validate_output_path(args.output, [args.input])
    report = audit(args.input)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False)+"\n", encoding="utf-8")
    print(json.dumps({"checks": report["check_count"], "failed": report["failed_checks"],
                      "validated_selection": report["validated_selection"]}))


if __name__ == "__main__":
    main()
