"""Draft production runner: one frozen free-root 2ms engineering trial only.

No learning imports, models, fit, MPC, task teacher, retries or gain search.
Production imports occur only after clean committed source verification.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import importlib
import json
import math
from pathlib import Path
import platform
import re
import subprocess
import sys
import time
import traceback
import zipfile


SEED = 7800
DT = .002
PREFIX = 1000
ACTIVE = 2000
SOURCE_PATH = "scripts/validate_free_root_fast_feedback_engineering.py"
ENVIRONMENT_PATH = "src/developmental_physics/free_root_fast_feedback_environment.py"
PROTOCOL_PATH = "docs/FREE_ROOT_FAST_FEEDBACK_ENGINEERING_PROTOCOL.md"
CANDIDATE_PROTOCOL_PIN = {"bytes": 9381, "sha256": "41e9c323c51e4c3bc0e1f6cf4ea7e47c72b2c60777f3d8f2762839a0ff9011d3"}
# Publication changes only the protocol header; root must bind its final identity.
PROTOCOL_PIN = {'bytes': 9189, 'sha256': '5bb40312c37418b639f11ea32da007c3e5835a74ace19defe9c235e29bfe2c86'}
DEPENDENCIES = (SOURCE_PATH, ENVIRONMENT_PATH, PROTOCOL_PATH,
                "src/developmental_physics/environment.py",
                "src/developmental_physics/assets/ground_body.xml",
                "src/developmental_physics/__init__.py", "pyproject.toml")
FLAGS = {key: False for key in (
    "scientific_adoption", "old_free_root_C4_validation", "c4_scientific_validation",
    "c4_contact_scientific_validation", "c5_scientific_dependency_released")}
COUNTERS = (
    "control_call_attempts", "control_call_returns", "control_call_exceptions",
    "confirmed_physics_substeps", "captured_native_endpoints", "captured_complete_endpoints",
    "environment_constructor_attempts", "environment_constructor_returns",
    "environment_constructor_exceptions", "reset_attempts", "reset_returns", "reset_exceptions",
    "pd_request_attempts", "pd_request_returns", "pd_request_exceptions",
    "study_check_attempts", "study_check_returns",
    "production_import_attempts", "production_import_returns", "production_import_exceptions",
    "source_read_attempts", "source_read_returns", "source_bytes_read", "source_git_show_bytes",
    "git_command_attempts", "git_command_returns", "journal_write_attempts", "journal_write_returns",
    "journal_known_utf8_bytes", "audit_contact_snapshot_attempts", "audit_contact_snapshot_returns",
    "audit_contact_snapshot_exceptions", "audit_contact_pair_inspections",
    "audit_geom_name_query_attempts", "audit_geom_name_query_returns", "audit_geom_name_query_exceptions",
    "audit_contact_force_query_attempts", "audit_contact_force_query_returns", "audit_contact_force_query_exceptions",
    "physical_identity_attempts", "physical_identity_returns", "physical_asset_read_returns",
    "physical_asset_bytes_read", "model_calls", "model_restores", "fit_calls", "RLS_updates",
    "MPC_decisions", "teacher_calls", "task_policy_updates", "GPU_training_seconds")


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def vector(value, length):
    return isinstance(value, list) and len(value) == length and all(finite(x) for x in value)


def plain(value):
    if isinstance(value, dict):
        return {str(k): plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(v) for v in value]
    if isinstance(value, float) and not math.isfinite(value):
        return {"nonfinite": repr(value)}
    if hasattr(value, "tolist"):
        return plain(value.tolist())
    return value


def failure(exc):
    return {"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()}


def identity(data):
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def phase(index):
    return "prefix" if index < PREFIX else "target_A" if index < PREFIX + 1000 else "target_B"


def native(observation):
    keys = {"joint_position": 8, "joint_velocity": 8, "imu_gyro": 3,
            "imu_acceleration": 3, "actuator_torque": 8, "previous_command": 8}
    if not isinstance(observation, dict) or not all(vector(observation.get(k), n) for k, n in keys.items()):
        raise ValueError("finite_complete_original_native_observation_required")
    return observation["joint_position"][:2], observation["joint_velocity"][:2]


def bind_targets(qref, ranges):
    if not vector(qref, 2) or not isinstance(ranges, list) or len(ranges) != 2 or not all(vector(r, 2) and r[0] < r[1] for r in ranges):
        raise ValueError("finite_two_axis_reference_and_public_ranges_required")
    direction = [1 if hi - q >= q - lo else -1 for q, (lo, hi) in zip(qref, ranges)]
    targets = [[q + s * amplitude for q, s in zip(qref, direction)] for amplitude in (.04, .08)]
    if any(not lo + .03 <= t <= hi - .03 for target in targets for t, (lo, hi) in zip(target, ranges)):
        raise ValueError("fixed_target_infeasible_no_clip_or_direction_retry")
    return direction, targets


def pd_request(q, v, target):
    if not all(vector(x, 2) for x in (q, v, target)):
        raise ValueError("finite_current_two_axis_pd_inputs_required")
    raw = [64. * (t - p) - 4. * speed for p, speed, t in zip(q, v, target)]
    return [max(-.5, min(.5, x)) for x in raw], raw


def study_abort(q, v, qref):
    triggers = []
    for axis in range(2):
        if abs(q[axis] - qref[axis]) >= .12:
            triggers.append({"joint_index": axis, "signal": "absolute_q_minus_qref_rad"})
        if abs(v[axis]) >= 1.:
            triggers.append({"joint_index": axis, "signal": "absolute_velocity_rad_s"})
    return None if not triggers else {"type": "StudyAbort", "triggers": triggers, "q_rad": q,
        "v_rad_s": v, "qref_rad": qref, "position_threshold_rad": .12,
        "speed_threshold_rad_s": 1., "comparison": ">=", "feedback_action": None}


def effort_and_contacts(records):
    output = {}
    for name in ("prefix", "target_A", "target_B"):
        population = [r for r in records if r["phase"] == name]
        paid = sum(r.get("confirmed_physics_substeps", 0) for r in population)
        observed = [r for r in population if r.get("contact_audit_complete") is True]
        native_observed = [r for r in population if r.get("complete_native_endpoint") is True]
        summary = {"planned_substeps": 1000, "confirmed_substeps": paid, "observed_contact_endpoints": len(observed),
                   "observed_native_endpoints": len(native_observed),
                   "missing_contact_endpoint_substeps": paid - len(observed), "classes": {},
                   "requested_absolute_nm_s_axis": [0., 0.], "requested_squared_nm2_s_axis": [0., 0.],
                   "actual_endpoint_sample_absolute_nm_s_axis": [0., 0.],
                   "actual_endpoint_sample_squared_nm2_s_axis": [0., 0.],
                   "actual_effort_method": "returned actuator_torque endpoint sample times 2ms; no unreturned sample imputation",
                   "actual_effort_complete": paid == len(native_observed)}
        for category in ("left_arm", "feet", "other"):
            forces = [[pair["positive_normal_force_n"] for pair in r["contacts"]["floor_pairs"]
                       if pair["category"] == category] for r in observed]
            endpoint_sums = [sum(values) for values in forces]
            positives = sum(value > 0 for value in endpoint_sums)
            summary["classes"][category] = {
                "positive_contact_endpoint_count": positives,
                "positive_pair_event_count": sum(sum(value > 0 for value in values) for values in forces),
                "observed_positive_duration_s": positives * DT,
                "known_positive_fraction_of_paid_substeps": positives / paid if paid else None,
                "fraction_is_lower_bound_if_missing": len(observed) != paid,
                "full_positive_contact_count_unknown": len(observed) != paid,
                "endpoint_sample_normal_impulse_ns": sum(endpoint_sums) * DT,
                "maximum_endpoint_normal_force_n": max(endpoint_sums, default=0.),
                "complete_phase_required_for_qualification": True,
            }
        for row in population:
            request, count = row["requested_torque"][:2], row.get("confirmed_physics_substeps", 0)
            for axis in range(2):
                summary["requested_absolute_nm_s_axis"][axis] += abs(request[axis]) * count * DT
                summary["requested_squared_nm2_s_axis"][axis] += request[axis] ** 2 * count * DT
        for row in native_observed:
            torque = row["observation_after"]["actuator_torque"][:2]
            for axis in range(2):
                summary["actual_endpoint_sample_absolute_nm_s_axis"][axis] += abs(torque[axis]) * DT
                summary["actual_endpoint_sample_squared_nm2_s_axis"][axis] += torque[axis] ** 2 * DT
        output[name] = summary
    return output


def engineering_metrics(records, *, complete, metadata_stable):
    phases = effort_and_contacts(records)
    windows = []
    for label, first, last in (("A", 800, 999), ("B", 1800, 1999)):
        population = [r for r in records if type(r.get("active_index")) is int
                      and first <= r["active_index"] <= last]
        errors = [r.get("target_error_rad") for r in population]
        available = (complete and len(population) == 200 and all(r.get("complete_endpoint") is True for r in population)
                     and all(vector(e, 2) for e in errors))
        mae = [sum(abs(e[axis]) for e in errors) / 200 for axis in range(2)] if available else None
        windows.append({"target": label, "active_first": first, "active_last": last, "planned_count": 200,
                        "observed_count": len(population), "full_trial_required": True,
                        "available": available, "mae_axis_rad": mae, "threshold_rad": .01,
                        "passed_axis": [x <= .01 for x in mae] if available else [False, False]})
    contact_checks = {name: bool(complete and item["confirmed_substeps"] == item["observed_contact_endpoints"] == 1000
                         and item["classes"]["left_arm"]["positive_contact_endpoint_count"] >= 1)
                      for name, item in phases.items()}
    qualified = bool(complete and metadata_stable and all(all(w["passed_axis"]) for w in windows)
                     and all(contact_checks.values()))
    return {"complete_population": bool(complete), "metadata_stable": bool(metadata_stable),
            "windows": windows, "phase_effort_and_contacts": phases, "left_arm_contact_checks": contact_checks,
            "contact_requirement": "each complete prefix/A/B has >=1 floor-left_arm positive normal force event",
            "partial_subset_ranking": False, "engineering_qualification_passed": qualified,
            "sustained_support_or_contact_causality_demonstrated": False, **FLAGS}


def collect(env, cost, journal):
    records, qref, targets, direction = [], None, None, None
    stop = error = before = after = None
    observation = row = None
    def save_journal(value):
        text = json.dumps(value, ensure_ascii=False, allow_nan=False) + "\n"
        cost["journal_write_attempts"] += 1
        journal.write(text)
        journal.flush()
        cost["journal_write_returns"] += 1
        cost["journal_known_utf8_bytes"] += len(text.encode("utf-8"))
    try:
        cost["reset_attempts"] += 1
        try:
            observation = plain(env.reset(seed=SEED, pose="supine"))
        except BaseException:
            cost["reset_exceptions"] += 1
            raise
        cost["reset_returns"] += 1
        native(observation)
        before = plain(env.frozen_metadata())
        ranges = plain(env.model.jnt_range[env._joint_ids][:2])
        for index in range(PREFIX + ACTIVE):
            row = None
            name = phase(index)
            q, v = native(observation)
            if index == PREFIX:
                qref = list(q)
                direction, targets = bind_targets(qref, ranges)
            target = None if name == "prefix" else targets[0 if name == "target_A" else 1]
            request, raw = [0.] * 8, None
            if target is not None:
                cost["pd_request_attempts"] += 1
                try:
                    request[:2], raw = pd_request(q, v, target)
                except BaseException:
                    cost["pd_request_exceptions"] += 1
                    raise
                cost["pd_request_returns"] += 1
            row = {"index": index, "phase": name, "active_index": index - PREFIX if target is not None else None,
                   "requested_torque": request, "raw_pd_torque_nm": raw, "target_rad": target,
                   "observation_before": observation, "returned": False, "complete_endpoint": False,
                   "complete_native_endpoint": False, "contact_audit_complete": False,
                   "confirmed_physics_substeps": 0, "stop": None, "failure": None}
            records.append(row)
            old_physics = env.physics_steps
            cost["control_call_attempts"] += 1
            try:
                stepped = env.step(request)
                cost["control_call_returns"] += 1
                row["returned"] = True
            except BaseException as exc:
                cost["control_call_exceptions"] += 1
                row["failure"] = failure(exc)
                raise
            finally:
                delta = env.physics_steps - old_physics
                if type(delta) is not int or delta < 0:
                    raise ValueError("invalid_confirmed_substep_delta_unknown")
                row["confirmed_physics_substeps"] = delta
                cost["confirmed_physics_substeps"] += delta
                if delta > 1:
                    raise ValueError("unexpected_multiple_paid_substeps_preserved")
            observation = plain(stepped.observation)
            row.update(observation_after=observation, diagnostics=plain(stepped.diagnostics),
                       environment_terminated=bool(stepped.terminated), environment_reason=stepped.reason)
            # Preserve the returned paid row BEFORE any new contact query or StudyAbort.
            save_journal({"entry_kind": "paid_native_endpoint", "record": row})
            next_q, next_v = native(observation)
            if stepped.diagnostics.get("executed_substeps") != row["confirmed_physics_substeps"]:
                raise ValueError("returned_paid_substeps_differ")
            if row["confirmed_physics_substeps"] == 1:
                row["complete_native_endpoint"] = True
                cost["captured_native_endpoints"] += 1
                row["contacts"] = plain(env.audit_floor_pairs())
                if not finite(row["contacts"]["time_s"]) or abs(row["contacts"]["time_s"] - (index + 1) * DT) > 1e-9:
                    raise ValueError("endpoint_time_not_fixed_2ms_population")
                row["contact_audit_complete"] = True
                row["complete_endpoint"] = True
                cost["captured_complete_endpoints"] += 1
                if target is not None:
                    row["target_error_rad"] = [a - b for a, b in zip(next_q, target)]
                    cost["study_check_attempts"] += 1
                    row["stop"] = study_abort(next_q, next_v, qref)
                    cost["study_check_returns"] += 1
                    row["study_check_available"] = True
            elif not stepped.terminated:
                raise ValueError("zero_substep_return_without_base_stop")
            save_journal({"entry_kind": "endpoint_audit_annotation", "index": index,
                          "contacts": row.get("contacts"), "study_abort": row["stop"],
                          "complete_native_endpoint": row["complete_native_endpoint"],
                          "contact_audit_complete": row["contact_audit_complete"],
                          "complete_endpoint": row["complete_endpoint"]})
            if stepped.terminated or row["stop"] is not None:
                stop = {"environment_reason": stepped.reason, "study_abort": row["stop"], "index": index}
                break
            if index in (999, 1999, 2999):
                print(json.dumps({"progress": "phase_finished", "phase": name,
                                  "confirmed_substeps": cost["confirmed_physics_substeps"]}), flush=True)
    except BaseException as exc:
        error = failure(exc)
        if row is not None and row.get("failure") is None:
            row["failure"] = error
        if row is not None:
            try:
                save_journal({"entry_kind": "collector_failure_annotation", "index": row["index"],
                              "failure": error, "record": row,
                              "confirmed_physics_substeps": row["confirmed_physics_substeps"],
                              "complete_native_endpoint": row["complete_native_endpoint"],
                              "contact_audit_complete": row["contact_audit_complete"]})
            except BaseException as journal_error:
                error["failure_annotation_write_failure"] = failure(journal_error)
    finally:
        try:
            after = plain(env.frozen_metadata())
        except BaseException as exc:
            error = error or failure(exc)
    stable = before is not None and after == before
    complete = bool(error is None and stop is None and len(records) == 3000
                    and all(r["complete_endpoint"] for r in records))
    return {"records": records, "failure": error, "stop": stop, "complete": complete,
            "qref_rad": qref, "direction": direction, "targets_rad": targets,
            "metadata_before": before, "metadata_after": after,
            "metrics": engineering_metrics(records, complete=complete, metadata_stable=stable)}


def source_gate(root, commit, cost, files, pins):
    def git(*args):
        cost["git_command_attempts"] += 1
        result = subprocess.check_output(["git", *args], cwd=root)
        cost["git_command_returns"] += 1
        return result
    if not isinstance(PROTOCOL_PIN, dict):
        raise ValueError("final_published_protocol_pin_required_before_production_import")
    if re.fullmatch(r"[0-9a-f]{40}", commit) is None or git("rev-parse", "HEAD").decode().strip() != commit:
        raise ValueError("exact_source_HEAD_required")
    if git("status", "--porcelain").strip():
        raise ValueError("clean_source_checkout_required_before_new_output_creation")
    if Path(__file__).resolve() != (root / SOURCE_PATH).resolve():
        raise ValueError("production_runner_path_required")
    for name in DEPENDENCIES:
        cost["source_read_attempts"] += 1
        data = (root / name).read_bytes()
        cost["source_read_returns"] += 1
        cost["source_bytes_read"] += len(data)
        committed = git("show", commit + ":" + name)
        cost["source_git_show_bytes"] += len(committed)
        if data != committed:
            raise ValueError("source_bytes_differ:" + name)
        if name == PROTOCOL_PATH and identity(data) != PROTOCOL_PIN:
            raise ValueError("frozen_protocol_identity_differs")
        files[name], pins[name] = data, identity(data)
    return files, pins


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    args = parser.parse_args()
    root, output = args.repo.resolve(), args.output.resolve()
    if output == root or root.is_relative_to(output):
        raise ValueError("output_cannot_contain_repository")
    if output.exists():
        raise FileExistsError("new_output_required")
    wall, cpu = time.perf_counter(), time.process_time()
    cost = Counter({key: 0 for key in COUNTERS})
    files, pins, source_error = {}, {}, None
    try:
        files, pins = source_gate(root, args.source_commit, cost, files, pins)
    except BaseException as exc:
        source_error = failure(exc)
    output.mkdir(parents=True, exist_ok=False)
    result = {"records": [], "complete": False, "failure": source_error, "stop": None,
              "metrics": engineering_metrics([], complete=False, metadata_stable=False)}
    runtime = {"python": sys.version, "platform": platform.platform()}
    if source_error is None:
        try:
            with zipfile.ZipFile(output / "source_snapshot.zip", "w", zipfile.ZIP_DEFLATED) as archive:
                for name, data in files.items():
                    archive.writestr(name, data)
            sys.path.insert(0, str(root / "src"))
            cost["production_import_attempts"] += 1
            try:
                module = importlib.import_module("developmental_physics.free_root_fast_feedback_environment")
                if Path(module.__file__).resolve() != (root / ENVIRONMENT_PATH).resolve():
                    raise ValueError("production_environment_import_path_differs")
                cost["production_import_returns"] += 1
            except BaseException:
                cost["production_import_exceptions"] += 1
                raise
            runtime.update(mujoco=module.mujoco.__version__, numpy=module.np.__version__)
            cost["environment_constructor_attempts"] += 1
            try:
                env = module.FreeRootFastFeedbackGroundBodyEnv(audit_cost=cost)
            except BaseException:
                cost["environment_constructor_exceptions"] += 1
                raise
            cost["environment_constructor_returns"] += 1
            with (output / "paid_journal.jsonl").open("x", encoding="utf-8", newline="\n") as journal:
                result = collect(env, cost, journal)
        except BaseException as exc:
            result["failure"] = failure(exc)
            result["complete"] = False
            result["metrics"] = engineering_metrics(result["records"], complete=False, metadata_stable=False)
    status = "failed" if result["failure"] else "completed" if result["complete"] else "stopped"
    cost["wall_seconds"], cost["cpu_seconds"] = time.perf_counter() - wall, time.process_time() - cpu
    run = {"schema_version": 1, "experiment_id": "FR0", "stage": "free_root_fast_feedback_engineering", "status": status,
           "created_at_utc": datetime.now(timezone.utc).isoformat(), "seed": SEED, "pose": "supine",
           "source": {"commit": args.source_commit, "files": pins,
                      "clean_committed_bytes_verified": source_error is None},
           "runtime": runtime, "planned_upper_bounds": {"control_calls": 3000, "physics_substeps": 3000,
                       "prefix_controls": 1000, "active_controls": 2000, "pd_requests": 2000},
           "cost": dict(cost), "trial": {key: value for key, value in result.items() if key not in ("records", "metrics")},
           "no_reset_retry_or_parameter_search": True, "learning_permitted_this_trial": False,
           "unconfirmed_integrator_and_forward_attempts": "unknown_if_core_exception",
           "constructor_model_builds_and_reset_forward_attempts": "unmeasured_unknown_not_zero",
           "inherited_execution_fingerprint_asset_IO": "unknown_not_zero",
           "unmeasured_OS_IO": "unknown_not_zero", "timing_excludes": "final_serialization_and_manifest_writes", **FLAGS}
    for name, value in (("run.json", run), ("metrics.json", result["metrics"])):
        (output / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    with (output / "trace.jsonl").open("x", encoding="utf-8", newline="\n") as trace:
        for row in result["records"]:
            trace.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
    payloads = {path.name: identity(path.read_bytes()) for path in output.iterdir() if path.is_file()}
    manifest = {"schema_version": 1, "experiment_id": "FR0", "stage": run["stage"], "status": status,
                "files": payloads, "manifest_payload_read_calls": len(payloads),
                "manifest_payload_bytes_read": sum(item["bytes"] for item in payloads.values()), **FLAGS}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": status, "complete": result["complete"],
                      "engineering_qualification_passed": result["metrics"]["engineering_qualification_passed"],
                      "control_attempts": cost["control_call_attempts"], "confirmed_substeps": cost["confirmed_physics_substeps"]}), flush=True)
    return 1 if result["failure"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
