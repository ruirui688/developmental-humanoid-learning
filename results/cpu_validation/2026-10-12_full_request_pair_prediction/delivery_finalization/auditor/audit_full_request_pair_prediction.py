"""One bounded audit of newly archived FR3A evidence; never invokes a body model.

Prepared candidate only. Source, paid counters, complete populations, saved
prediction labels, raw-RMSE mean gates and sampled effort/contact summaries are
checked once. No old experiment is read, no model is restored, and no trajectory
is rerun. Output must be a new directory outside the immutable FR3A raw directory.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import gzip
import hashlib
import io
import json
import math
from pathlib import Path
import subprocess
import time
import traceback
import zipfile


FR3A_RELATIVE = "results/cpu_validation/2026-10-12_full_request_pair_prediction/raw"
SEEDS = (8001, 8002, 8003)
HORIZONS = (1, 10, 20, 50, 150)
MODELS = ("cold", "learned")
FLAGS = ("scientific_adoption", "old_free_root_C4_validation", "c4_scientific_validation",
         "c4_contact_scientific_validation", "c5_scientific_dependency_released")
OTHER_GATES = ("fr3b_model_contribution_gate_passed", "fr3b_pd_reference_gate_passed",
               "fr3_free_root_mechanism_validation")
SOURCE_PATHS = (
    "scripts/develop_full_request_pair.py", "src/developmental_physics/full_request_pair_development.py",
    "docs/FULL_REQUEST_PAIR_LEARNING_PROTOCOL.md",
    "scripts/validate_free_root_fast_feedback_engineering.py",
    "src/developmental_physics/free_root_fast_feedback_environment.py",
    "docs/FREE_ROOT_FAST_FEEDBACK_ENGINEERING_PROTOCOL.md",
    "src/developmental_physics/environment.py", "src/developmental_physics/assets/ground_body.xml",
    "src/developmental_physics/__init__.py", "pyproject.toml",
    "src/developmental_physics/fast_feedback_pair_model.py",
    "src/developmental_physics/guard_coupled_pair_model.py",
    "src/developmental_physics/guard_pair_model.py", "src/developmental_physics/local_pair_model.py",
    "src/developmental_physics/local_model.py", "src/developmental_physics/fast_feedback_pair_mpc.py",
    "src/developmental_physics/batched_fast_feedback_pair_mpc.py",
    "src/developmental_physics/full_request_pair_mpc.py",
    "src/developmental_physics/fast_feedback_pair_development.py",
)
MAX_TRACE_RECORDS = 21000
MAX_PREDICTION_RECORDS = 2886
MAX_SAVED_PAIR_PATH_STEPS = 124680
MAX_JSON_BYTES = 16 * 1024 * 1024
MAX_COMPRESSED_BYTES = 512 * 1024 * 1024
MAX_TRACE_DECODED_BYTES = 2 * 1024 * 1024 * 1024
MAX_PREDICTION_DECODED_BYTES = 128 * 1024 * 1024
MAX_LINE_BYTES = 2 * 1024 * 1024
# These are fixed serialization/arithmetic tolerances, never scientific gates.
ABS_TOL = 2e-12
REL_TOL = 2e-10


class AuditBoundError(ValueError):
    pass


def json_safe(value):
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_safe(item) for item in (sorted(value, key=str) if isinstance(value, set) else value)]
    if isinstance(value, float) and not math.isfinite(value):
        return {"nonfinite_float": str(value)}
    return value


class Checks:
    def __init__(self):
        self.counts, self.failed, self.failures = Counter(), Counter(), []

    def check(self, condition, scope, label, *, actual=None, expected=None):
        self.counts[scope] += 1
        if not condition:
            self.failed[scope] += 1
            if len(self.failures) < 128:
                self.failures.append({"scope": scope, "label": label,
                                      "actual": json_safe(actual), "expected": json_safe(expected)})

    def equal(self, actual, expected, scope, label):
        self.check(actual == expected, scope, label, actual=actual, expected=expected)

    def numeric(self, actual, expected, scope, label):
        self.check(close_tree(actual, expected), scope, label, actual=actual, expected=expected)


def require(condition, message):
    if not condition:
        raise AuditBoundError(message)


def finite_number(value):
    return type(value) in (int, float) and math.isfinite(value)


def vector(value, size):
    return tuple(float(x) for x in value) if (isinstance(value, list) and len(value) == size
        and all(finite_number(x) for x in value)) else None


def close_tree(actual, expected):
    if actual is None or expected is None:
        return actual is expected
    if isinstance(expected, bool) or isinstance(actual, bool):
        return actual is expected
    if finite_number(actual) and finite_number(expected):
        return math.isclose(actual, expected, abs_tol=ABS_TOL, rel_tol=REL_TOL)
    if isinstance(actual, dict) and isinstance(expected, dict):
        return actual.keys() == expected.keys() and all(close_tree(actual[k], expected[k]) for k in expected)
    if isinstance(actual, (list, tuple)) and isinstance(expected, (list, tuple)):
        return len(actual) == len(expected) and all(close_tree(a, b) for a, b in zip(actual, expected))
    return actual == expected


def identity(data):
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def duplicate_free(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "duplicate_json_key:" + key)
        result[key] = value
    return result


def parse_json(data, cost):
    cost["json_parse_attempts"] += 1
    value = json.loads(data, object_pairs_hook=duplicate_free,
                       parse_constant=lambda value: (_ for _ in ()).throw(AuditBoundError("nonfinite_json:" + value)))
    cost["json_parse_returns"] += 1
    return value


def read_small(path, cost, limit=MAX_JSON_BYTES):
    size = path.stat().st_size
    require(size <= limit, "file_size_bound:" + path.name)
    cost["file_read_attempts"] += 1
    data = path.read_bytes()
    cost["file_read_returns"] += 1
    cost["read_bytes"] += len(data)
    return data


def hash_stream(path, cost):
    require(path.stat().st_size <= MAX_COMPRESSED_BYTES, "compressed_size_bound:" + path.name)
    digest, count = hashlib.sha256(), 0
    cost["file_hash_attempts"] += 1
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
            count += len(chunk)
    cost["file_hash_returns"] += 1
    cost["hashed_bytes"] += count
    return {"bytes": count, "sha256": digest.hexdigest()}


def iter_records(path, cost, *, record_limit, decoded_limit):
    decoded, count = 0, 0
    cost["gzip_stream_open_attempts"] += 1
    with gzip.open(path, "rb") as stream:
        cost["gzip_stream_open_returns"] += 1
        while line := stream.readline(MAX_LINE_BYTES + 1):
            require(len(line) <= MAX_LINE_BYTES, "jsonl_line_bound:" + path.name)
            decoded += len(line)
            count += 1
            require(decoded <= decoded_limit and count <= record_limit, "decoded_population_bound:" + path.name)
            require(line.endswith(b"\n") and line.strip(), "complete_nonblank_jsonl_line_required")
            value = parse_json(line, cost)
            require(isinstance(value, dict), "jsonl_dictionary_required")
            yield value
    cost[path.name + "_decoded_bytes"] = decoded
    cost[path.name + "_records"] = count


def check_sources(repo, raw, run, manifest, commit, checks, cost):
    source = run.get("source", {})
    checks.equal(source.get("commit"), commit, "source", "exact_requested_commit")
    clean = source.get("clean_committed_bytes_verified") is True
    pins = source.get("files", {})
    checks.check(isinstance(pins, dict) and set(pins).issubset(SOURCE_PATHS), "source", "bounded_dependency_names")
    if not clean:
        checks.check(run.get("failure") is not None, "source", "unverified_source_requires_saved_failure")
        checks.check(not run.get("seed_results") and not run.get("trials"), "source", "unverified_source_has_no_physics_trials")
        return False
    checks.equal(set(pins), set(SOURCE_PATHS), "source", "all_19_frozen_dependencies")
    archive_bytes = read_small(raw / "source.zip", cost, 64 * 1024 * 1024)
    checks.equal(identity(archive_bytes), manifest["files"].get("source.zip"), "source", "source_zip_payload_pin")
    total = 0
    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
        infos = archive.infolist()
        require(len(infos) <= len(SOURCE_PATHS), "source_zip_member_bound")
        checks.equal({item.filename for item in infos}, set(SOURCE_PATHS), "source", "source_zip_exact_names")
        require(len({item.filename for item in infos}) == len(infos), "source_zip_duplicate_name")
        for info in infos:
            require(info.filename in SOURCE_PATHS and info.file_size <= MAX_JSON_BYTES, "source_zip_member_size_or_name")
            total += info.file_size
            require(total <= 128 * 1024 * 1024, "source_zip_decoded_bound")
            data = archive.read(info)
            cost["source_zip_member_reads"] += 1
            cost["source_zip_member_bytes"] += len(data)
            checks.equal(identity(data), pins.get(info.filename), "source", "archived_dependency:" + info.filename)
            cost["git_show_attempts"] += 1
            returned = subprocess.run(["git", "show", commit + ":" + info.filename], cwd=repo,
                                      capture_output=True, check=False)
            cost["git_show_return_bytes"] += len(returned.stdout) + len(returned.stderr)
            checks.check(returned.returncode == 0, "source", "frozen_git_object_read:" + info.filename,
                         actual=returned.returncode, expected=0)
            checks.equal(identity(returned.stdout), identity(data), "source", "committed_archived_bytes:" + info.filename)
    return clean


def complete_native_observation(observation):
    return isinstance(observation, dict) and all(vector(observation.get(key), size) is not None
        for key, size in (("joint_position", 8), ("joint_velocity", 8), ("imu_gyro", 3),
                          ("imu_acceleration", 3), ("actuator_torque", 8), ("previous_command", 8)))


def capture_row(row, ordinal, checks, ledger):
    scope, index = "trace", row.get("control_index")
    require(type(index) is int and 0 <= index < 5000, "bounded_control_index")
    seed, kind = row.get("seed"), row.get("trial_id", "")
    require(seed in SEEDS and kind in {f"FR3_{seed}_calibration", f"FR3_{seed}_prediction"}, "new_FR3A_trial_identity")
    phase = "prefix" if index < 1000 else "active"
    phase_index = index if index < 1000 else index - 1000
    checks.equal(row.get("phase"), phase, scope, "phase:" + row.get("transition_id", ""))
    checks.equal(row.get("phase_index"), phase_index, scope, "phase_index:" + row.get("transition_id", ""))
    checks.equal(row.get("transition_id"), f"{kind}:{index}", scope, "transition_id")
    request = vector(row.get("requested_torque"), 8)
    checks.check(request is not None and all(abs(x) <= .5 for x in request[:2])
                 and request[2:] == (0.,) * 6, scope, "shared_permissions")
    if phase == "prefix":
        checks.equal(request, (0.,) * 8, scope, "zero_prefix_request")
    delta = row.get("confirmed_completed_substeps")
    checks.check(type(delta) is int and 0 <= delta <= 1, scope, "one_micro_paid_delta", actual=delta, expected="0_or_1")
    paid = delta if type(delta) is int and delta >= 0 else 0
    ledger["control_call_attempts"] += 1
    ledger["control_call_returns"] += int(row.get("returned") is True)
    ledger["control_call_exceptions"] += int("collector_exception" in row)
    ledger["confirmed_physics_substeps"] += paid
    ledger["captured_native_endpoints"] += int(row.get("complete_native_endpoint") is True)
    before, after = row.get("observation_before", {}), row.get("observation_after", {})
    bq, bv, aq, av = (vector(o.get(k), 8) for o, k in
                     ((before, "joint_position"), (before, "joint_velocity"),
                      (after, "joint_position"), (after, "joint_velocity")))
    diagnostic = row.get("diagnostics") or row.get("saved_partial") or {}
    samples = diagnostic.get("substep_native_and_contact_records", [])
    require(isinstance(samples, list) and len(samples) <= 1, "bounded_micro_sample_count")
    actual, applied, missing_effort = None, None, False
    pair_classes, sample_telemetry = Counter(), False
    if samples:
        sample = samples[0]
        actual = vector(sample.get("actual_actuator_torque8"), 8)
        applied = vector(sample.get("applied_command8"), 8)
        missing_effort = actual is None or applied is None
        if not missing_effort:
            ledger["captured_substep_endpoint_forward_returns"] += 1
        checks.equal(sample.get("physics_step"), index + 1, scope, "sample_physics_index")
        checks.numeric(sample.get("time"), (index + 1) * .002, scope, "sample_time")
        for pair in sample.get("floor_contacts", []):
            pair_classes[pair.get("contact_class", "left_arm" if pair.get("left_arm") else "other")] += 1
        contacts_finite = all(finite_number(pair.get(key)) for pair in sample.get("floor_contacts", [])
                              for key in ("normal_force_n", "distance_m"))
        sample_telemetry = (actual is not None and applied is not None
            and complete_native_observation(sample.get("observation")) and contacts_finite)
        if vector(after.get("actuator_torque"), 8) is not None:
            checks.numeric(actual, after["actuator_torque"], scope, "paid_actual_native_sample")
        if vector(diagnostic.get("applied_torque"), 8) is not None:
            checks.numeric(applied, diagnostic["applied_torque"], scope, "known_guarded_applied_sample")
    telemetry = (row.get("contact_audit_complete") is True and row.get("returned") is True
        and diagnostic.get("executed_substeps") == 1 and paid == 1 and len(samples) == 1
        and all(value is not None for value in (bq, bv, aq, av)) and sample_telemetry)
    audit = row.get("audit_contacts") if row.get("contact_audit_complete") is True else None
    normal_sums = None
    if audit is not None:
        checks.numeric(audit.get("time_s"), (index + 1) * .002, scope, "audit_endpoint_time")
        pairs = audit.get("floor_pairs", [])
        require(isinstance(pairs, list) and len(pairs) <= 4096, "floor_pair_bound")
        normal_sums = {category: 0. for category in ("left_arm", "feet", "other")}
        for pair in pairs:
            category, positive, signed = pair.get("category"), pair.get("positive_normal_force_n"), pair.get("signed_normal_force_n")
            checks.check(category in normal_sums and finite_number(positive) and finite_number(signed), scope, "finite_contact_pair")
            if category in normal_sums and finite_number(positive) and finite_number(signed):
                checks.numeric(positive, max(0., signed), scope, "signed_positive_force_relation")
                normal_sums[category] += positive
            ledger["known_audit_floor_pairs"] += 1
        ledger["known_complete_contact_endpoints"] += 1
        if samples:
            checks.equal(sum(pair_classes.values()), len(pairs), scope, "audit_sample_pair_count")
    update, update_failure = row.get("model_update"), row.get("model_update_failure")
    committed = row.get("committed_vector_updates_this_attempt", 0)
    checks.check(type(committed) is int and committed in (0, 1), scope, "atomic_vector_commit")
    ledger["RLS_vector_update_attempts"] += int(update is not None or update_failure is not None)
    ledger["RLS_vector_update_returns"] += int(update is not None)
    ledger["RLS_vector_update_exceptions"] += int(update_failure is not None)
    ledger["RLS_vector_update_commits"] += committed if type(committed) is int else 0
    ledger["RLS_scalar_update_commits"] += 2 * committed if type(committed) is int else 0
    if update is not None or update_failure is not None:
        checks.check(phase == "active" and kind.endswith("_calibration") and telemetry
                     and not row.get("environment_terminated") and row.get("study_abort") is None,
                     scope, "updates_only_legal_full_calibration")
    if update is not None:
        checks.equal(update.get("shared_transition_id"), row.get("transition_id"), scope, "update_native_transition_id")
        checks.numeric(update.get("observed_next_v_rad_s"), av[:2] if av is not None else None, scope, "native_velocity_label")
        checks.equal(update.get("committed_scalar_updates"), 2 * committed, scope, "atomic_scalar_count")
        checks.check(len(update.get("output_records", [])) == 2
                     and all(item.get("committed") is True for item in update.get("output_records", [])),
                     scope, "both_head_commit_records")
    return {"ordinal": ordinal, "index": index, "phase": phase, "phase_index": phase_index,
            "paid": paid, "returned": row.get("returned") is True, "telemetry": telemetry,
            "bq": bq[:2] if bq is not None else None, "bv": bv[:2] if bv is not None else None,
            "aq": aq[:2] if aq is not None else None, "av": av[:2] if av is not None else None,
            "request": request[:2] if request is not None else None,
            "applied2": tuple(diagnostic["applied_torque"][:2]) if vector(diagnostic.get("applied_torque"), 8) is not None else None,
            "actual": actual, "applied": applied, "missing_effort": missing_effort,
            "normal_sums": normal_sums, "pair_classes": pair_classes, "committed": committed}


def input_ranges(records):
    result = {}
    for name, key in (("q2", "bq"), ("v2", "bv"), ("requested2", "request"), ("public_guarded_applied2", "applied2")):
        values = [row[key] for row in records if row[key] is not None]
        result[name] = {"planned_record_count": len(records), "known_record_count": len(values),
                        "missing_record_count": len(records) - len(values),
                        "minimum_axis": [min(x[i] for x in values) for i in range(2)] if values else None,
                        "maximum_axis": [max(x[i] for x in values) for i in range(2)] if values else None}
    return result


def contact_summary(records, *, name, planned, gate, complete):
    observed = [row for row in records if row["normal_sums"] is not None]
    paid = sum(row["paid"] for row in records)
    result = {"name": name, "planned_count": planned, "record_count": len(records),
              "confirmed_substeps": paid, "observed_contact_endpoints": len(observed),
              "unknown_paid_contact_substeps": paid - len(observed), "classes": {},
              "native_input_ranges": input_ranges(records), "is_qualification_phase": gate}
    for category in ("left_arm", "feet", "other"):
        sums = [row["normal_sums"][category] for row in observed]
        positive = sum(value > 0 for value in sums)
        result["classes"][category] = {"positive_contact_endpoint_count": positive,
            "known_positive_fraction_of_paid_substeps": positive / paid if paid else None,
            "positive_count_unknown_if_missing": len(observed) != paid,
            "sampled_positive_duration_s": positive * .002,
            "endpoint_sample_normal_impulse_ns": sum(sums) * .002,
            "maximum_endpoint_normal_force_n": max(sums) if sums else None,
            "maximum_scope": "observed_endpoints_only_partial_is_not_full_maximum"}
    result["qualification_passed"] = bool(gate and complete and len(records) == planned
        and paid == len(observed) == planned and result["classes"]["left_arm"]["positive_contact_endpoint_count"] >= 1)
    return result


def effort_summary(records, *, active, complete):
    values = {"actual_absolute_axis_nm_s": [0., 0.], "actual_squared_axis_nm2_s": [0., 0.],
              "all8_actual_absolute_nm_s": 0., "all8_actual_squared_nm2_s": 0.,
              "applied_absolute_axis_nm_s": [0., 0.], "applied_squared_axis_nm2_s": [0., 0.],
              "captured_substeps": 0}
    malformed = any(row["missing_effort"] for row in records)
    for row in records:
        if row["actual"] is None or row["applied"] is None:
            continue
        for axis in range(2):
            values["actual_absolute_axis_nm_s"][axis] += abs(row["actual"][axis]) * .002
            values["actual_squared_axis_nm2_s"][axis] += row["actual"][axis] ** 2 * .002
            values["applied_absolute_axis_nm_s"][axis] += abs(row["applied"][axis]) * .002
            values["applied_squared_axis_nm2_s"][axis] += row["applied"][axis] ** 2 * .002
        values["all8_actual_absolute_nm_s"] += sum(abs(x) for x in row["actual"]) * .002
        values["all8_actual_squared_nm2_s"] += sum(x*x for x in row["actual"]) * .002
        values["captured_substeps"] += 1
    population_complete = bool(records and all(row["telemetry"] for row in records)
        and values["captured_substeps"] == len(records) and not malformed)
    values["complete"] = population_complete and (complete if active else True)
    values["counts_are_lower_bounds_if_incomplete"] = not population_complete
    values["actual_absolute_two_axis_nm_s"] = sum(values["actual_absolute_axis_nm_s"])
    values["actual_squared_two_axis_nm2_s"] = sum(values["actual_squared_axis_nm2_s"])
    values["confirmed_paid_substeps"] = sum(row["paid"] for row in records)
    values["unknown_actual_effort_substeps"] = values["confirmed_paid_substeps"] - values["captured_substeps"]
    values["actual_effort_population_complete"] = (values["confirmed_paid_substeps"] == values["captured_substeps"] and not malformed)
    if malformed:
        values["nonfinite_or_missing_effort"] = True
    return values


def audit_trial(trial, records, source_files, checks):
    name = trial["trial_id"]
    kind, expected_active = trial.get("kind"), 4000 if trial.get("kind") == "calibration" else 1000
    checks.equal(trial.get("planned_prefix"), 1000, "trials", "prefix:" + name)
    checks.equal(trial.get("planned_active"), expected_active, "trials", "active_budget:" + name)
    checks.equal([row["index"] for row in records], list(range(len(records))), "trials", "continuous_indexes:" + name)
    checks.check(len(records) <= 1000 + expected_active, "trials", "bounded_trial_population:" + name)
    checks.equal(trial.get("returned_intervals"), sum(row["returned"] for row in records), "trials", "returned_population:" + name)
    complete = bool(len(records) == 1000 + expected_active and not trial.get("failure") and not trial.get("stop")
        and trial.get("metadata_stable") is True and all(row["telemetry"] for row in records))
    checks.equal(trial.get("complete"), complete, "trials", "native_complete_priority:" + name)
    checks.equal(trial.get("native_execution_complete"), complete, "trials", "native_execution_complete:" + name)
    if trial.get("metadata_stable") is True:
        for field in ("physical_fingerprint", "execution_fingerprint"):
            checks.equal(trial.get(field + "_before"), trial.get(field + "_after"),
                         "trials", "stable_frozen_metadata:" + name + ":" + field)
    prefix = [row for row in records if row["phase"] == "prefix"]
    active = [row for row in records if row["phase"] == "active"]
    if trial.get("qref2") is not None and len(prefix) == 1000:
        checks.numeric(trial["qref2"], prefix[-1]["aq"], "trials", "prefix_last_native_qref:" + name)
    if records:
        checks.equal(trial.get("record_start"), records[0]["ordinal"], "trials", "record_start:" + name)
        checks.equal(trial.get("record_end"), records[-1]["ordinal"] + 1, "trials", "record_end:" + name)
    checks.equal(trial.get("installed_xml_identity"), source_files.get("src/developmental_physics/assets/ground_body.xml"),
                 "trials", "original_asset_identity:" + name)
    checks.equal(trial.get("original_asset_unchanged_no_mount"), True, "trials", "no_mount_asset:" + name)
    support = trial.get("support", {})
    checks.equal(support, {"root": "original_asset_freejoint", "mount": None,
                          "initial_pose": "supine", "external_support": False}, "trials", "supine_free_root:" + name)
    contact = {"phases": {}, "blocks_0_4s_report_only": [], "contact_causality_or_continuous_support_demonstrated": False,
               "no_contact_based_training_selection": True}
    for phase, selected, planned in (("prefix", prefix, 1000), ("active", active, expected_active)):
        contact["phases"][phase] = contact_summary(selected, name=phase, planned=planned, gate=True, complete=complete)
        checks.numeric(trial.get("actual_effort", {}).get(phase), effort_summary(selected, active=phase == "active", complete=complete),
                       "effort", name + ":" + phase)
        for start in range(0, planned, 200):
            selected_block = [row for row in selected if start <= row["phase_index"] < min(start + 200, planned)]
            block_name = f"{phase}_{start}_{min(start+200, planned)-1}"
            contact["blocks_0_4s_report_only"].append(contact_summary(selected_block, name=block_name,
                planned=min(200, planned - start), gate=False, complete=complete))
    contact["qualification_passed"] = all(x["qualification_passed"] for x in contact["phases"].values())
    checks.numeric(trial.get("contact_population"), contact, "contact", name + ":phase_and_block_summaries")
    checks.equal(trial.get("free_root_domain_qualification_passed"), contact["qualification_passed"], "contact", name + ":domain_gate")
    pair_counts = Counter()
    for row in records:
        pair_counts.update(row["pair_classes"])
    checks.equal(trial.get("floor_contact_classes"), dict(pair_counts), "contact", name + ":pair_count_not_positive_endpoint_count")
    return {"complete": complete, "domain": contact["qualification_passed"], "active": active,
            "committed": sum(row["committed"] for row in active)}


def snapshot_check(snapshot, checks, label, *, count, frozen):
    checks.equal(snapshot.get("structure"), "coupled_hinge9", "models", label + ":structure")
    checks.equal(snapshot.get("dt_seconds"), .002, "models", label + ":new_micro_dt")
    checks.equal(snapshot.get("integration"), "endpoint_euler", "models", label + ":integration")
    checks.equal(snapshot.get("trainable"), not frozen, "models", label + ":frozen_state")
    checks.equal(snapshot.get("vector_update_count"), count, "models", label + ":vector_count")
    checks.equal(snapshot.get("scalar_update_count"), 2*count, "models", label + ":scalar_count")
    checks.equal(snapshot.get("output_update_counts"), [count, count], "models", label + ":both_head_counts")
    checks.check(isinstance(snapshot.get("coefficients"), list) and len(snapshot["coefficients"]) == 2
        and all(vector(row, 9) is not None for row in snapshot["coefficients"]), "models", label + ":finite_18_coefficients")
    covariance = snapshot.get("covariance", [])
    checks.check(isinstance(covariance, list) and len(covariance) == 2
        and all(isinstance(matrix, list) and len(matrix) == 9 and all(vector(row, 9) is not None for row in matrix)
                for matrix in covariance), "models", label + ":finite_two_9x9_covariances")
    checks.check(vector(snapshot.get("qref_rad"), 2) is not None, "models", label + ":finite_qref")
    checks.check(isinstance(snapshot.get("parameter_fingerprint"), str)
        and len(snapshot["parameter_fingerprint"]) == 64, "models", label + ":saved_fingerprint_only_no_restore")


def audit_predictions(raw, seed_rows, trial_info, models, checks, cost):
    group_rows, path_steps = defaultdict(dict), 0
    for row in iter_records(raw / "predictions.jsonl.gz", cost, record_limit=MAX_PREDICTION_RECORDS,
                            decoded_limit=MAX_PREDICTION_DECODED_BYTES):
        seed, horizon, model, origin = (row.get(k) for k in ("seed", "horizon", "model", "origin_active_index"))
        require(seed in SEEDS and horizon in HORIZONS and model in MODELS and type(origin) is int,
                "fixed_new_prediction_group_identity")
        require(origin in range(0, 1000-horizon+1, 10), "fixed_prediction_origin")
        group = (seed, horizon, model)
        require(origin not in group_rows[group], "duplicate_prediction_origin")
        group_rows[group][origin] = {"available": row.get("available") is True, "dq": None, "dv": None}
        checks.equal(row.get("scope"), "independent_prediction", "predictions", "new_independent_scope")
        checks.equal(row.get("trial_id"), f"FR3_{seed}_prediction", "predictions", "prediction_trial_id")
        qp, vp = row.get("predicted_q_path", []), row.get("predicted_v_path", [])
        require(isinstance(qp, list) and isinstance(vp, list) and len(qp) <= horizon and len(vp) <= horizon,
                "saved_prediction_path_bound")
        path_steps += max(len(qp), len(vp))
        require(path_steps <= MAX_SAVED_PAIR_PATH_STEPS, "saved_pair_path_budget")
        info = trial_info.get(f"FR3_{seed}_prediction", {"complete": False, "domain": False, "active": []})
        segment = info["active"][origin:origin+horizon]
        saved_input = row.get("model_input")
        if saved_input is not None and len(segment) == horizon:
            checks.numeric(saved_input.get("q2"), segment[0]["bq"], "predictions", "origin_native_q")
            checks.numeric(saved_input.get("v2"), segment[0]["bv"], "predictions", "origin_native_v")
            checks.numeric(saved_input.get("known_requests2"), [x["request"] for x in segment],
                           "predictions", "saved_future_final_requests_only")
        if row.get("available") is True:
            valid = len(qp) == len(vp) == horizon and all(vector(x, 2) is not None for x in qp+vp)
            checks.check(valid and len(segment) == horizon and all(x["telemetry"] for x in segment),
                         "predictions", "available_origin_has_full_finite_path_and_native_labels")
            if valid and len(segment) == horizon and segment[-1]["aq"] is not None and segment[-1]["av"] is not None:
                aq, av = segment[-1]["aq"], segment[-1]["av"]
                checks.numeric(row.get("actual_endpoint_q2"), aq, "predictions", "native_q_endpoint_label")
                checks.numeric(row.get("actual_endpoint_v2"), av, "predictions", "native_v_endpoint_label")
                dq = [qp[-1][i]-aq[i] for i in range(2)]
                dv = [vp[-1][i]-av[i] for i in range(2)]
                checks.numeric(row.get("q_error_rad"), dq, "predictions", "saved_last_q_minus_native_label")
                checks.numeric(row.get("v_error_rad_s"), dv, "predictions", "saved_last_v_minus_native_label")
                group_rows[group][origin].update(dq=dq, dv=dv)
        else:
            checks.check(bool(row.get("unavailable_reason") or row.get("failure")), "predictions", "unavailable_origin_has_reason")
        snapshot = models.get(str(seed), {}).get(model, {})
        if saved_input is not None:
            checks.equal(row.get("model_parameter_fingerprint"), snapshot.get("parameter_fingerprint"),
                         "predictions", "new_frozen_model_reference")
    cost["saved_pair_path_steps_inspected_no_model_calls"] = path_steps
    rechecked = []
    for seed in SEEDS:
        srow = seed_rows.get(seed, {})
        score = srow.get("prediction_scores", {})
        info = trial_info.get(f"FR3_{seed}_prediction", {"complete": False, "domain": False})
        if score.get("trial_id") is not None:
            checks.equal(score.get("trial_id"), f"FR3_{seed}_prediction", "RMSE", "score_trial_id")
            checks.equal(score.get("complete_population"), info["complete"] and info["domain"], "RMSE", "score_full_qualified_population")
            checks.equal(score.get("native_execution_complete"), info["complete"], "RMSE", "score_native_complete")
            checks.equal(score.get("free_root_domain_qualification_passed"), info["domain"], "RMSE", "score_contact_qualified")
            expected_fingerprints = {name: models.get(str(seed), {}).get(name, {}).get("parameter_fingerprint") for name in MODELS}
            checks.equal(score.get("model_fingerprints"), expected_fingerprints, "RMSE", "score_new_frozen_model_pair")
            checks.equal(score.get("model_fingerprints_after"), expected_fingerprints, "RMSE", "score_models_stayed_frozen")
        horizons = {}
        for horizon in HORIZONS:
            origins = list(range(0, 1000-horizon+1, 10))
            output = horizons[str(horizon)] = {"planned_origin_count": len(origins), "models": {}}
            original_h = score.get("horizons", {}).get(str(horizon), {})
            if original_h.get("models"):
                checks.equal(original_h.get("planned_origin_count"), len(origins), "RMSE", "declared_full_origin_population")
            for model in MODELS:
                rows = group_rows[(seed, horizon, model)]
                complete = bool(info["complete"] and info["domain"] and set(rows) == set(origins)
                    and all(x["available"] and x["dq"] is not None and x["dv"] is not None for x in rows.values()))
                rmse_q = rmse_v = None
                if complete:
                    ordered = [rows[origin] for origin in origins]
                    rmse_q = [math.sqrt(sum(x["dq"][axis] ** 2 for x in ordered) / len(origins)) for axis in range(2)]
                    rmse_v = [math.sqrt(sum(x["dv"][axis] ** 2 for x in ordered) / len(origins)) for axis in range(2)]
                output["models"][model] = {"available": complete, "q_rmse_axis_rad": rmse_q,
                                           "v_rmse_axis_rad_s": rmse_v, "partial_subset_ranking": False}
                original = original_h.get("models", {}).get(model, {})
                checks.equal(bool(original.get("available")), complete, "RMSE", f"{seed}:{horizon}:{model}:complete_priority")
                if original:
                    checks.equal(original.get("partial_subset_ranking"), False, "RMSE", "no_partial_ranking")
                    checks.equal(original.get("observed_origin_count"), sum(x["available"] for x in rows.values()),
                                 "RMSE", "observed_origin_count")
                    checks.numeric(original.get("q_rmse_axis_rad"), rmse_q, "RMSE", f"{seed}:{horizon}:{model}:q_native_label_RMSE")
                    checks.numeric(original.get("v_rmse_axis_rad_s"), rmse_v, "RMSE", f"{seed}:{horizon}:{model}:v_native_label_RMSE")
                if not complete:
                    checks.check(original.get("q_rmse_axis_rad") is None and original.get("v_rmse_axis_rad_s") is None,
                                 "RMSE", "incomplete_or_unqualified_RMSE_unavailable")
        rechecked.append({"seed": seed, "prediction_scores": {"horizons": horizons}})
    return rechecked


def original_gate_from_saved_scores(seed_rows):
    """Same declared FR3A comparisons; no new H1/H10q veto or new threshold."""
    checks, complete = [], set(seed_rows) == set(SEEDS)
    for horizon in HORIZONS:
        for signal in ("q", "v"):
            key = "q_rmse_axis_rad" if signal == "q" else "v_rmse_axis_rad_s"
            strict = (horizon, signal) in ((10, "v"), (150, "q"))
            gated = horizon != 1 and (horizon, signal) != (10, "q")
            bases, candidates = [], []
            for seed in SEEDS:
                hrow = seed_rows.get(seed, {}).get("prediction_scores", {}).get("horizons", {}).get(str(horizon), {}).get("models", {})
                cold, learned = hrow.get("cold", {}), hrow.get("learned", {})
                available = bool(cold.get("available") and learned.get("available"))
                if not available:
                    if gated:
                        complete = False
                    checks.append({"seed": seed, "horizon": horizon, "signal": signal,
                                   "available": False, "gated": gated, "passed": False})
                    continue
                base, candidate = cold[key], learned[key]
                bases.append(base)
                candidates.append(candidate)
                passed = all(candidate[i] < base[i] if strict else candidate[i] <= base[i] for i in range(2))
                checks.append({"seed": seed, "horizon": horizon, "signal": signal, "available": True,
                               "gated": gated, "strict": strict, "passed": passed,
                               "cold_axis": base, "learned_axis": candidate})
            if strict:
                available = len(bases) == len(candidates) == 3 and all(finite_number(x) for values in bases+candidates for x in values)
                base_mean = [sum(x[i] for x in bases)/3 for i in range(2)] if available else None
                candidate_mean = [sum(x[i] for x in candidates)/3 for i in range(2)] if available else None
                fractions = [((base_mean[i]-candidate_mean[i])/base_mean[i] if base_mean[i] > 0 else None)
                             for i in range(2)] if available else None
                checks.append({"scope": "three_seed_raw_RMSE_mean", "horizon": horizon, "signal": signal,
                    "available": available, "cold_axis_mean": base_mean, "learned_axis_mean": candidate_mean,
                    "improvement_fractions": fractions, "required_improvement": .20,
                    "passed": bool(available and all(x is not None and x >= .20 for x in fractions))})
    return {"complete_population": complete, "checks": checks,
            "fr3a_prediction_gate_passed": bool(complete and all(x["passed"] for x in checks if x.get("gated", True))),
            "mean_type": "arithmetic mean of original per_seed axis RMSE", "partial_subset_ranking": False}


def run_audit(args, checks, cost):
    repo, raw = Path(args.repo).resolve(), Path(args.raw).resolve()
    require(raw == (repo / FR3A_RELATIVE).resolve(), "only_fixed_new_FR3A_raw_directory_is_allowed")
    require(len(args.source_commit) == 40 and all(x in "0123456789abcdef" for x in args.source_commit), "exact_source_commit_required")
    manifest = parse_json(read_small(raw / "manifest.json", cost), cost)
    loaded, pins = {}, {}
    for name in ("run.json", "metrics.json", "models.json"):
        data = read_small(raw / name, cost)
        pins[name] = identity(data)
        checks.equal(pins[name], manifest.get("files", {}).get(name), "payload", name)
        loaded[name] = parse_json(data, cost)
    for name in ("trace.jsonl.gz", "predictions.jsonl.gz"):
        pins[name] = hash_stream(raw / name, cost)
        checks.equal(pins[name], manifest.get("files", {}).get(name), "payload", name)
    run, metrics, models = (loaded[name] for name in ("run.json", "metrics.json", "models.json"))
    for item in (run, manifest):
        checks.equal(item.get("experiment_id"), "FR3A", "boundary", "only_FR3A_experiment")
        checks.equal(item.get("stage"), "prediction", "boundary", "only_prediction_stage")
    checks.equal(run.get("status"), manifest.get("status"), "boundary", "manifest_run_status")
    checks.equal(run.get("seeds"), list(SEEDS), "boundary", "fixed_development_seed_bank")
    for item in (run, manifest, metrics):
        for flag in FLAGS:
            checks.equal(item.get(flag), False, "boundary", flag)
    for key in OTHER_GATES:
        checks.equal(metrics.get(key), False, "boundary", key)
    checks.equal(run.get("planned_upper_bounds"), {"control_calls": 21000, "physics_substeps": 21000,
        "RLS_vector_commits": 12000, "RLS_scalar_commits": 24000, "independent_prediction_pairs": 124680},
        "boundary", "frozen_FR3A_budget")
    source_ok = check_sources(repo, raw, run, manifest, args.source_commit, checks, cost)
    trials, seed_rows_list = run.get("trials", []), run.get("seed_results", [])
    require(isinstance(trials, list) and len(trials) <= 6 and isinstance(seed_rows_list, list) and len(seed_rows_list) <= 3,
            "bounded_FR3A_trial_seed_matrix")
    seed_rows = {row["seed"]: row for row in seed_rows_list}
    require(len(seed_rows) == len(seed_rows_list) and set(seed_rows).issubset(SEEDS), "unique_seed_results")
    by_id = {trial["trial_id"]: trial for trial in trials}
    require(len(by_id) == len(trials), "unique_trial_ids")
    ledger, trace = Counter(), defaultdict(list)
    for ordinal, row in enumerate(iter_records(raw / "trace.jsonl.gz", cost, record_limit=MAX_TRACE_RECORDS,
                                             decoded_limit=MAX_TRACE_DECODED_BYTES)):
        trace[row["trial_id"]].append(capture_row(row, ordinal, checks, ledger))
    checks.check(set(trace).issubset(by_id), "trials", "trace_belongs_to_saved_trial_matrix")
    trial_info = {name: audit_trial(trial, trace.get(name, []), run.get("source", {}).get("files", {}), checks)
                  for name, trial in by_id.items()}
    for seed, row in seed_rows.items():
        for kind in ("calibration", "prediction"):
            trial = row.get(kind, {})
            if trial.get("trial_id"):
                checks.equal(trial, by_id.get(trial["trial_id"]), "trials", "matrix_seed_same_trial_summary")
            else:
                checks.check(kind == "prediction" and trial.get("complete") is False,
                             "trials", "only_unattempted_prediction_can_be_blocked")
        calibration, prediction = row.get("calibration", {}), row.get("prediction", {})
        if prediction.get("trial_id"):
            for field in ("installed_xml_identity", "physical_fingerprint_before", "execution_fingerprint_before", "interface_fingerprint", "public_joint_ranges2"):
                checks.equal(prediction.get(field), calibration.get(field), "trials", "fresh_same_seed_binding:" + field)
            if prediction.get("qref2") is not None and calibration.get("qref2") is not None:
                checks.check(all(abs(prediction["qref2"][i]-calibration["qref2"][i]) <= 1e-12 for i in range(2)),
                             "trials", "fresh_same_seed_qref_original_tolerance")
        if str(seed) in models:
            checks.equal(set(models[str(seed)]), set(MODELS), "models", "new_frozen_model_pair")
            for name, count in (("cold", 0), ("learned", 4000)):
                snapshot_check(models[str(seed)].get(name, {}), checks, f"{seed}:{name}", count=count, frozen=True)
                checks.numeric(models[str(seed)][name].get("qref_rad"), calibration.get("qref2"), "models", "new_model_calibration_reference")
            checks.check(trial_info.get(f"FR3_{seed}_calibration", {}).get("complete")
                         and trial_info[f"FR3_{seed}_calibration"]["domain"], "models", "models_saved_only_after_complete_domain_calibration")
        if row.get("cold_initial_snapshot") and row.get("learned_initial_snapshot"):
            checks.equal(row["cold_initial_snapshot"].get("parameter_fingerprint"), row["learned_initial_snapshot"].get("parameter_fingerprint"),
                         "models", "matching_new_unlearned_initial_fingerprints")
        final = row.get("learned_snapshot_after_calibration")
        if final is not None:
            snapshot_check(final, checks, f"{seed}:calibration_final", count=trial_info.get(f"FR3_{seed}_calibration", {}).get("committed", 0), frozen=False)
    checks.check(set(models).issubset({str(seed) for seed in SEEDS}), "models", "only_new_bank_models")
    paid = run.get("cost", {})
    for key in ("control_call_attempts", "control_call_returns", "control_call_exceptions", "confirmed_physics_substeps",
                "captured_substep_endpoint_forward_returns", "RLS_vector_update_attempts", "RLS_vector_update_returns",
                "RLS_vector_update_exceptions", "RLS_vector_update_commits", "RLS_scalar_update_commits"):
        checks.equal(paid.get(key, 0), ledger[key], "ledger", key)
    for key, upper in (("control_call_attempts", 21000), ("confirmed_physics_substeps", 21000),
                       ("RLS_vector_update_commits", 12000), ("RLS_scalar_update_commits", 24000)):
        checks.check(type(paid.get(key)) is int and 0 <= paid[key] <= upper, "ledger", key + ":bound")
    for key in ("MPC_decision_attempts", "MPC_decision_returns", "MPC_decision_exceptions", "teacher_calls",
                "batch_fit_calls", "task_policy_updates", "GPU_training_seconds"):
        checks.equal(paid.get(key), 0, "ledger", "no_FR3A_task_training_or_planning:" + key)
    if trials:
        checks.equal(paid.get("captured_native_endpoints", 0), ledger["captured_native_endpoints"], "ledger", "captured_native_endpoints")
        checks.equal(paid.get("audit_contact_snapshot_attempts", 0), ledger["captured_native_endpoints"], "ledger", "audit_attempt_after_native_capture")
        checks.check(ledger["known_complete_contact_endpoints"] <= paid.get("audit_contact_snapshot_returns", 0)
                     <= paid.get("audit_contact_snapshot_attempts", 0), "ledger", "audit_return_lower_bound")
        checks.check(ledger["known_audit_floor_pairs"] <= paid.get("audit_contact_force_query_returns", 0)
                     <= paid.get("audit_contact_force_query_attempts", 0), "ledger", "force_query_known_lower_bound")
    rechecked = audit_predictions(raw, seed_rows, trial_info, models, checks, cost)
    if run.get("status") == "completed" and run.get("failure") is None:
        checks.equal(paid.get("independent_prediction_pair_prediction_returns"),
                     cost["saved_pair_path_steps_inspected_no_model_calls"], "ledger", "new_saved_pair_return_accounting")
        checks.equal(paid.get("independent_prediction_scalar_prediction_returns"),
                     2 * cost["saved_pair_path_steps_inspected_no_model_calls"], "ledger", "new_saved_two_head_return_accounting")
    original_gate = original_gate_from_saved_scores(seed_rows)
    if metrics.get("checks") is not None:
        checks.numeric(metrics["checks"], original_gate["checks"], "gate", "original_saved_RMSE_comparisons")
        checks.equal(metrics.get("complete_population"), original_gate["complete_population"], "gate", "complete_gate_population")
        checks.equal(metrics.get("mean_type"), original_gate["mean_type"], "gate", "raw_RMSE_arithmetic_mean")
        checks.equal(metrics.get("partial_subset_ranking"), False, "gate", "no_partial_gate_ranking")
    else:
        checks.check(run.get("failure") is not None or not seed_rows, "gate", "absent_final_gate_requires_failed_or_unattempted_execution")
    expected_gate = bool(original_gate["fr3a_prediction_gate_passed"] and run.get("failure") is None and source_ok)
    checks.equal(metrics.get("fr3a_prediction_gate_passed"), expected_gate, "gate", "original_gate_with_execution_failure_veto")
    if not all(info["complete"] and info["domain"] for info in trial_info.values()) or len(trial_info) != 6:
        checks.equal(metrics.get("fr3a_prediction_gate_passed"), False, "gate", "missing_complete_domain_cannot_pass")
    checks.equal(run.get("unattempted_seeds"), [seed for seed in SEEDS if seed not in seed_rows], "trials", "unattempted_seeds_preserved")
    if run.get("failure") is None:
        expected_status = "completed" if len(trial_info) == 6 and all(x["complete"] for x in trial_info.values()) else "stopped"
        checks.equal(run.get("status"), expected_status, "boundary", "engineering_status_independent_of_science_gate")
    else:
        checks.equal(run.get("status"), "failed", "boundary", "saved_failure_status")
    return {"payload_pins": pins, "source_verified": source_ok, "trace_ledger": dict(ledger),
            "trial_eligibility": {name: {key: info[key] for key in ("complete", "domain", "committed")} for name, info in trial_info.items()},
            "saved_prediction_RMSE_recheck": rechecked, "original_saved_RMSE_gate_recheck": original_gate,
            "execution_vetoed_FR3A_gate": expected_gate, "partial_subset_ranking": False, "science_flags": {flag: False for flag in FLAGS}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".")
    parser.add_argument("--raw", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    raw, output = Path(args.raw).resolve(), Path(args.output).resolve()
    require(output != raw and not output.is_relative_to(raw) and not raw.is_relative_to(output),
            "audit_output_must_not_modify_or_contain_raw")
    output.mkdir(parents=True, exist_ok=False)
    checks, cost, result, problem = Checks(), Counter(), None, None
    wall, cpu = time.perf_counter(), time.process_time()
    try:
        result = run_audit(args, checks, cost)
    except BaseException as exc:
        problem = {"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()}
    cost["wall_seconds"], cost["cpu_seconds"] = time.perf_counter()-wall, time.process_time()-cpu
    auditor_bytes = Path(__file__).read_bytes()
    report = {"schema": "first_FR3A_saved_evidence_audit_v1", "raw": str(raw), "source_commit": args.source_commit,
        "auditor": identity(auditor_bytes), "status": "passed" if problem is None and not sum(checks.failed.values()) else "failed",
        "checks": dict(checks.counts), "failed_checks": dict(checks.failed), "first_128_failures": checks.failures,
        "first_failure": problem or (checks.failures[0] if checks.failures else None), "cost": dict(cost),
        "bounds": {"seeds": 3, "trials": 6, "trace_records": 21000, "prediction_records": 2886,
                   "model_horizon_groups": 30, "saved_pair_path_steps": 124680,
                   "source_members_and_git_shows": 19},
        "execution": {"model_calls": 0, "model_restorations": 0, "fit": 0, "RLS": 0, "physics": 0,
                      "old_scientific_recomputations": 0, "old_raw_reads": 0, "automatic_retries": 0,
                      "sample_effort_is_endpoint_estimate": True, "science_thresholds_changed": False},
        "recheck": result}
    for name, value in (("audit.json", report), ("metric_recheck.json", result)):
        with (output / name).open("x", encoding="utf-8") as stream:
            json.dump(json_safe(value), stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
    if report["first_failure"] is not None:
        with (output / "first_failure.json").open("x", encoding="utf-8") as stream:
            json.dump(json_safe(report["first_failure"]), stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
    print(json.dumps({"audit_status": report["status"], "output": str(output),
                      "checks": sum(checks.counts.values()), "failed": sum(checks.failed.values()),
                      "failure": problem, "new_FR3A_gate": result.get("execution_vetoed_FR3A_gate") if result else None},
                     ensure_ascii=False, allow_nan=False))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
