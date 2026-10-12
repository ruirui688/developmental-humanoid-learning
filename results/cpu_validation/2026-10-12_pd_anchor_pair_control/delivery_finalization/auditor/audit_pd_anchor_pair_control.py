"""First bounded audit of saved FR4B control evidence; no model or physics calls.

Stdlib source/JSON/effort/contact helpers are copied unchanged from the reviewed
FR2 auditor. This script reads only new FR4B payloads and their frozen source.
PD-anchor request arithmetic uses saved values; no rollout, cost or tie replay.
Tracking, conditional forecasts and original adoption gates are checked once;
zero stays descriptive and no self-forecast veto is introduced.
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



SEEDS = (8101, 8102, 8103)


HORIZONS = (1, 10, 20, 50, 150)


MODELS = ("cold", "learned")


FLAGS = ("scientific_adoption", "old_free_root_C4_validation", "c4_scientific_validation",
         "c4_contact_scientific_validation", "c5_scientific_dependency_released")


SOURCE_PATHS = (
    "scripts/develop_pd_anchor_pair.py", "src/developmental_physics/pd_anchor_pair_development.py",
    "docs/PD_ANCHOR_PAIR_LEARNING_PROTOCOL.md",
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
    "src/developmental_physics/pd_anchor_pair_mpc.py",
    "src/developmental_physics/fast_feedback_pair_development.py",
)


MAX_JSON_BYTES = 16 * 1024 * 1024


MAX_COMPRESSED_BYTES = 512 * 1024 * 1024


MAX_LINE_BYTES = 2 * 1024 * 1024


ABS_TOL = 2e-12


REL_TOL = 2e-10


FR4B_RELATIVE = "results/cpu_validation/2026-10-12_pd_anchor_pair_control/raw"
CONTROLS = ("cold", "learned", "pd", "zero")
FULL_REQUEST_AXIS_GRID_NM = (-.5, -.375, -.25, -.125, 0., .125, .25, .375, .5)
MAX_TRACE_RECORDS = 36000
MAX_PREDICTION_RECORDS = 11772
MAX_SAVED_PAIR_PATH_STEPS = 526560
MAX_TRACE_DECODED_BYTES = 2*1024*1024*1024
MAX_PREDICTION_DECODED_BYTES = 512*1024*1024


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


def decision_accounting(decision, ledger, checks):
    """Saved records/counters only; no candidate rollout, cost or tie recomputation."""
    candidates = decision.get("candidate_records", [])
    require(isinstance(candidates, list) and len(candidates) <= 81, "candidate_record_bound")
    checks.equal(len(candidates), 81, "planning", "complete_returned_candidate_population")
    checks.check(all(vector(item.get("torque"), 2) is not None
        and type(item.get("feasible")) is bool and type(item.get("scalar_counts_complete")) is bool
        and all(type(item.get(key)) is int and item[key] >= 0 for key in
                ("pair_prediction_attempts", "scalar_prediction_attempts")) for item in candidates),
        "planning", "saved_candidate_request_and_counter_schema")
    checks.check(all(type(decision.get(key)) is int and decision[key] >= 0 for key in
        ("pair_prediction_attempts", "pair_prediction_successes", "scalar_prediction_attempts",
         "scalar_prediction_successes", "unknown_scalar_failure_count", "pd_request_attempts",
         "pd_request_returns", "residual_candidate_attempts"))
        and decision.get("pair_prediction_successes", 0) <= decision.get("pair_prediction_attempts", 0)
        and decision.get("scalar_prediction_successes", 0) <= decision.get("scalar_prediction_attempts", 0)
        and type(decision.get("scalar_counts_complete")) is bool
        and decision.get("scalar_counts_is_lower_bound") == (not decision.get("scalar_counts_complete")),
        "planning", "returned_nonnegative_and_known_lower_bound_counter_schema")
    feasible = sum(item.get("feasible") is True for item in candidates)
    checks.equal(decision.get("feasible_candidates"), feasible, "planning", "feasible_record_count")
    checks.equal(decision.get("fallback"), feasible == 0, "planning", "fallback_record_count")
    checks.equal(sum(item.get("pair_prediction_attempts", 0) for item in candidates),
                 decision.get("pair_prediction_attempts"), "planning", "saved_candidate_pair_attempt_sum")
    checks.equal(sum(item.get("scalar_prediction_attempts", 0) for item in candidates),
                 decision.get("scalar_prediction_attempts"), "planning", "saved_candidate_scalar_attempt_sum")
    checks.check(all(type(item.get("completed_prediction_steps")) is int and 0 <= item["completed_prediction_steps"] <= 150
        and (item.get("completed_prediction_steps") == 150 and item.get("rejection_reason") is None and finite_number(item.get("cost"))
             if item.get("feasible") else item.get("cost") is None) for item in candidates),
        "planning", "saved_feasible_rejected_record_shape")
    checks.equal(decision.get("failed_pair_prediction_attempts"), decision.get("pair_prediction_attempts", 0)-decision.get("pair_prediction_successes", 0),
                 "planning", "returned_pair_attempt_success_difference")
    if decision.get("fallback"):
        checks.check(decision.get("torque") == [0., 0.] and decision.get("selected_residual_nm") is None
            and decision.get("cost") is None and not decision.get("predicted_q") and not decision.get("predicted_v")
            and not decision.get("trajectory_requested_torque"), "planning", "literal_zero_fallback_saved_shape")
    else:
        checks.check(vector(decision.get("selected_residual_nm"), 2) is not None
            and all(len(decision.get(key, [])) == 150 for key in ("predicted_q", "predicted_v", "trajectory_requested_torque")),
            "planning", "returned_selected_path_population")
    for key in ("pd_request_attempts", "pd_request_returns", "residual_candidate_attempts"):
        ledger["planning_"+key] += decision.get(key, 0)
    for key, target in (("pair_prediction_attempts", "planning_pair_prediction_attempts"),
                        ("pair_prediction_successes", "planning_pair_prediction_returns"),
                        ("scalar_prediction_attempts", "planning_scalar_prediction_attempts"),
                        ("scalar_prediction_successes", "planning_scalar_prediction_returns")):
        ledger[target] += decision.get(key, 0)
    ledger["MPC_decision_returns"] += 1
    ledger["planning_returned_candidate_rejections"] += len(candidates)-feasible
    ledger["planning_fallback_returns"] += int(bool(decision.get("fallback")))


def clipped_public_PD_checksum(q, v, target):
    """Fixed expression on saved states only; no controller/model invocation."""
    return tuple(min(.5, max(-.5, 64.*(target[i]-q[i])-4.*v[i])) for i in range(2))


def pd_anchor_saved_request_check(decision, q, v, target, ledger, checks):
    """Current saved PD-anchor mapping and selected requests; no rollout/cost/tie."""
    ledger["pd_anchor_grid_macro_checks"] += 1
    require(ledger["pd_anchor_grid_macro_checks"] <= 1200, "pd_anchor_grid_macro_check_bound")
    origin_known = q is not None and v is not None and vector(target, 2) is not None
    checks.check(origin_known, "pd_anchor_grid", "known_current_native_origin_and_current_target")
    if not origin_known:
        return
    base = clipped_public_PD_checksum(q, v, target)
    ledger["clipped_PD_pair_expressions_on_saved_states"] += 1
    axes, nearest_slots = [], []
    for value in base:
        axis = list(FULL_REQUEST_AXIS_GRID_NM)
        distances = [abs(point-value) for point in axis]
        ledger["PD_anchor_nominal_scalar_distances"] += len(distances)
        nearest = min(range(9), key=lambda index: (distances[index], index))
        axis[nearest] = value
        axes.append(tuple(axis))
        nearest_slots.append(nearest)
        ledger["PD_anchor_axis_slot_replacements"] += 1
    require(ledger["PD_anchor_nominal_scalar_distances"] <= 21600
            and ledger["PD_anchor_axis_slot_replacements"] <= 2400, "PD_anchor_generation_bound")
    dynamic_grid = tuple((axes[0][index//9], axes[1][index%9]) for index in range(81))
    records = decision.get("candidate_records", [])
    for index, record in enumerate(records):
        grid = dynamic_grid[index]
        delta = tuple(grid[i]-base[i] for i in range(2))
        expected = tuple(min(.5, max(-.5, base[i]+delta[i])) for i in range(2))
        checks.numeric(record.get("torque"), expected, "pd_anchor_grid", "saved_81_first_request_roundtrip_in_original_slot_order")
        ledger["pd_anchor_grid_first_request_pairs_checked"] += 1
    pure_PD_index = nearest_slots[0]*9+nearest_slots[1]
    pure_PD_delta = tuple(dynamic_grid[pure_PD_index][i]-base[i] for i in range(2))
    checks.equal(pure_PD_delta, (0., 0.), "pd_anchor_grid", "pure_PD_delta_zero_expression_exists_no_feasibility_or_selection_veto")
    if pure_PD_index < len(records):
        checks.numeric(records[pure_PD_index].get("torque"), base, "pd_anchor_grid", "saved_pure_PD_first_request_no_feasibility_or_selection_veto")
    ledger["PD_anchor_pure_PD_delta_zero_checks"] += 1
    require(ledger["PD_anchor_pure_PD_delta_zero_checks"] <= 1200, "PD_anchor_pure_PD_expression_bound")
    if decision.get("fallback"):
        return
    delta = vector(decision.get("selected_residual_nm"), 2)
    delta_known = delta is not None and all(abs(value) <= 1. for value in delta)
    checks.check(delta_known, "pd_anchor_grid", "finite_selected_dynamic_delta_within_one_Nm")
    if not delta_known:
        return
    nominal = tuple(base[i]+delta[i] for i in range(2))
    matches = [index for index in range(81) if close_tree(nominal, dynamic_grid[index])]
    checks.check(len(matches) == 1, "pd_anchor_grid", "selected_delta_from_one_PD_anchored_grid_minus_current_clipped_PD")
    if len(matches) == 1:
        grid = dynamic_grid[matches[0]]
        checks.numeric(delta, tuple(grid[i]-base[i] for i in range(2)), "pd_anchor_grid", "selected_dynamic_delta_definition")
        selected = records[matches[0]]
        checks.check(selected.get("feasible") is True and close_tree(selected.get("torque"), decision.get("torque")),
                     "pd_anchor_grid", "selected_first_request_is_saved_feasible_candidate")
    qp, vp, requests = (decision.get(key, []) for key in ("predicted_q", "predicted_v", "trajectory_requested_torque"))
    for stage in range(min(150, len(qp), len(vp), len(requests))):
        state_q, state_v = (q, v) if stage == 0 else (vector(qp[stage-1], 2), vector(vp[stage-1], 2))
        request = vector(requests[stage], 2)
        known = state_q is not None and state_v is not None and request is not None
        checks.check(known, "pd_anchor_grid", "finite_saved_selected_request_and_prior_predicted_state")
        if not known:
            continue
        stage_PD = base if stage == 0 else clipped_public_PD_checksum(state_q, state_v, target)
        ledger["clipped_PD_pair_expressions_on_saved_states"] += int(stage != 0)
        expected = tuple(min(.5, max(-.5, stage_PD[i]+(delta[i] if stage < 10 else 0.))) for i in range(2))
        checks.numeric(request, expected, "pd_anchor_grid", "saved_selected_ten_held_then_140_PD_tail_requests")
        checks.check(all(abs(value) <= .5 for value in request), "pd_anchor_grid", "saved_selected_final_permission")
        if stage == 0:
            checks.numeric(decision.get("torque"), request, "pd_anchor_grid", "saved_first_request_matches_selected_path")
        ledger["selected_saved_request_path_steps_checked"] += 1
        require(ledger["selected_saved_request_path_steps_checked"] <= 180000, "selected_request_path_checksum_bound")


def pd_anchor_saved_spec_check(spec, checks, ledger, label):
    """Saved static metadata only; no controller construction or fingerprint call."""
    ledger["PD_anchor_saved_spec_checks"] += 1
    require(ledger["PD_anchor_saved_spec_checks"] <= 6, "PD_anchor_spec_population_bound")
    checks.check(isinstance(spec, dict), "pd_anchor_spec", label+":saved_static_spec_object")
    if not isinstance(spec, dict):
        return
    for key in ("axis_candidates_nm", "vector_candidates_nm", "residual_candidates_nm", "residual_axis_candidates_nm",
                "first_final_request_axis_grid_nm", "first_final_request_grid_nm", "first_final_request_grid_spacing_nm"):
        checks.equal(spec.get(key), None, "pd_anchor_spec", label+":"+key)
    checks.numeric(spec.get("nominal_first_final_request_axis_grid_nm"), list(FULL_REQUEST_AXIS_GRID_NM),
                   "pd_anchor_spec", label+":static_nominal_axis_grid")
    checks.numeric(spec.get("nominal_first_final_request_grid_nm"),
                   [[FULL_REQUEST_AXIS_GRID_NM[index//9], FULL_REQUEST_AXIS_GRID_NM[index%9]] for index in range(81)],
                   "pd_anchor_spec", label+":static_nominal_81_pairs")
    checks.numeric(spec.get("nominal_first_final_request_grid_spacing_nm"), .125,
                   "pd_anchor_spec", label+":static_nominal_spacing")
    expected_replacement = {
        "current_public_PD_evaluations_for_candidate_generation": 1,
        "rule": "each axis: replace original slot argmin(abs(nominal-p), original_index) with current clipped p",
        "axis_points": 9, "cartesian_pairs": 81,
        "sort_expand_or_mutate_nominal_grid": False,
        "scalar_nearest_distances_per_macro": 18,
        "pure_PD_delta_zero_expression_guaranteed": True,
        "pure_PD_feasibility_or_selection_guaranteed": False,
        "coverage_loss": {
            "maximum_replaced_nominal_points_per_axis": 1,
            "maximum_point_displacement_nm": .0625,
            "maximum_adjacent_dynamic_gap_nm": .1875,
            "nominal_permission_endpoints_may_be_removed": True,
            "minimum_original_nominal_pairs_retained": 64}}
    checks.numeric(spec.get("PD_anchor_replacement"), expected_replacement,
                   "pd_anchor_spec", label+":fixed_replacement_metadata")
    for key, expected in (
        ("first_final_request_candidate_count", 81), ("maximum_absolute_dynamic_delta_nm", 1.),
        ("final_request_permission_nm", .5), ("pure_PD_candidate_guaranteed", True),
        ("zero_request_candidate_is_not_literal_zero_fallback", True),
        ("dynamic_residual_definition", "delta=PD-anchored-point-first-clipped-PD-current-native; once per macro"),
        ("first_request_float_semantics", "clip(p+(dynamic-point-p),-.5,.5); no bit equality promise to dynamic point")):
        checks.equal(spec.get(key), expected, "pd_anchor_spec", label+":"+key)


def capture_control(row, ordinal, ledger, checks):
    seed, trial_id, index = row.get("seed"), row.get("trial_id"), row.get("control_index")
    require(seed in SEEDS and trial_id in {f"FR4_{seed}_control_{name}" for name in CONTROLS}
            and type(index) is int and 0 <= index < 3000, "fixed_new_FR4B_trace_identity")
    name = trial_id.rsplit("_", 1)[-1]
    phase, active_index = ("prefix", index) if index < 1000 else ("active", index-1000)
    request = vector(row.get("requested_torque"), 8)
    paid = row.get("confirmed_completed_substeps", 0)
    before, after = row.get("observation_before", {}), row.get("observation_after", {})
    bq, bv, aq, av = (vector(o.get(key), 8) for o, key in
        ((before, "joint_position"), (before, "joint_velocity"), (after, "joint_position"), (after, "joint_velocity")))
    diagnostic = row.get("diagnostics") or row.get("saved_partial") or {}
    samples = diagnostic.get("substep_native_and_contact_records", [])
    require(isinstance(samples, list) and len(samples) <= 1 and type(paid) is int and 0 <= paid <= 1,
            "fixed_one_micro_capture_population")
    actual = applied = None
    pair_classes, normal_sums = Counter(), None
    missing_effort, sample_valid = False, False
    if samples:
        sample = samples[0]
        actual, applied = vector(sample.get("actual_actuator_torque8"), 8), vector(sample.get("applied_command8"), 8)
        missing_effort = actual is None or applied is None
        sample_valid = not missing_effort and complete_native_observation(sample.get("observation"))
        sample_valid &= sample.get("physics_step") == index+1 and finite_number(sample.get("time"))
        sample_valid &= all(finite_number(pair.get(key)) for pair in sample.get("floor_contacts", []) for key in ("normal_force_n", "distance_m"))
        for pair in sample.get("floor_contacts", []):
            pair_classes[pair.get("contact_class", "left_arm" if pair.get("left_arm") else "other")] += 1
        if not missing_effort:
            ledger["captured_substep_endpoint_forward_returns"] += 1
    if row.get("contact_audit_complete") is True:
        audit = row.get("audit_contacts", {})
        pairs = audit.get("floor_pairs", [])
        require(isinstance(pairs, list) and len(pairs) <= 4096, "new_floor_pair_bound")
        normal_sums = {category: 0. for category in ("left_arm", "feet", "other")}
        for pair in pairs:
            require(pair.get("category") in normal_sums and finite_number(pair.get("positive_normal_force_n")), "finite_saved_contact_pair")
            normal_sums[pair["category"]] += pair["positive_normal_force_n"]
        ledger["known_audit_floor_pairs"] += len(pairs)
        ledger["known_complete_contact_endpoints"] += 1
    telemetry = bool(row.get("returned") is True and row.get("contact_audit_complete") is True and paid == 1
        and diagnostic.get("executed_substeps") == 1 and len(samples) == 1 and sample_valid
        and all(value is not None for value in (bq, bv, aq, av)))
    valid_info = (row.get("phase") == phase and row.get("phase_index") == active_index
        and row.get("transition_id") == f"{trial_id}:{index}" and request is not None
        and all(abs(x) <= .5 for x in request[:2]) and request[2:] == (0.,)*6
        and (phase != "prefix" or request == (0.,)*8)
        and row.get("model_update") is None and row.get("model_update_failure") is None)
    ledger["invalid_trace_information_rows"] += int(not valid_info)
    ledger["control_call_attempts"] += 1
    ledger["control_call_returns"] += int(row.get("returned") is True)
    ledger["control_call_exceptions"] += int("collector_exception" in row)
    ledger["confirmed_physics_substeps"] += paid
    ledger["captured_native_endpoints"] += int(row.get("complete_native_endpoint") is True)
    if row.get("planning_decision") is not None:
        checks.check(name in MODELS and phase == "active" and active_index % 10 == 0,
                     "planning", "decisions_only_cold_learned_macro_origins")
        decision_accounting(row["planning_decision"], ledger, checks)
        pd_anchor_saved_request_check(row["planning_decision"], bq[:2] if bq is not None else None,
            bv[:2] if bv is not None else None, row.get("current_target_q2"), ledger, checks)
    return {"ordinal": ordinal, "index": index, "phase": phase, "phase_index": active_index,
        "paid": paid, "returned": row.get("returned") is True, "telemetry": telemetry,
        "bq": bq[:2] if bq is not None else None, "bv": bv[:2] if bv is not None else None,
        "aq": aq[:2] if aq is not None else None, "av": av[:2] if av is not None else None,
        "request": request[:2] if request is not None else None,
        "applied2": tuple(diagnostic["applied_torque"][:2]) if vector(diagnostic.get("applied_torque"), 8) is not None else None,
        "actual": actual, "applied": applied, "missing_effort": missing_effort, "normal_sums": normal_sums,
        "pair_classes": pair_classes, "target": row.get("current_target_q2"), "saved_error": row.get("target_error_rad"),
        "decision": row.get("planning_decision"), "held_residual": row.get("held_residual2"), "held_fallback": row.get("held_fallback"),
        "public_PD": vector(row.get("public_pd_request2"), 2), "residual_hold_micro_index": row.get("residual_hold_micro_index"),
        "macro_decision_index": row.get("macro_decision_index")}


def trial_recheck(trial, records, models, source_files, ledger, checks):
    trial_id, seed, name = trial["trial_id"], trial["seed"], trial["kind"].removeprefix("control_")
    checks.equal((trial.get("planned_prefix"), trial.get("planned_active")), (1000, 2000), "trials", trial_id+":budget")
    checks.equal([row["index"] for row in records], list(range(len(records))), "trials", trial_id+":continuous_population")
    complete = bool(len(records) == 3000 and trial.get("metadata_stable") is True and not trial.get("failure")
                    and not trial.get("stop") and all(row["telemetry"] for row in records))
    checks.equal(trial.get("complete"), complete, "trials", trial_id+":native_complete_priority")
    checks.equal(trial.get("native_execution_complete"), complete, "trials", trial_id+":native_complete_metadata")
    checks.equal(trial.get("returned_intervals"), sum(row["returned"] for row in records), "trials", trial_id+":returns")
    prefix, active = [row for row in records if row["phase"] == "prefix"], [row for row in records if row["phase"] == "active"]
    if trial.get("qref2") is not None and len(prefix) == 1000:
        checks.numeric(trial["qref2"], prefix[-1]["aq"], "trials", trial_id+":prefix_reference")
        checks.numeric(trial["qref2"], models[str(seed)]["cold"].get("qref_rad"), "trials", trial_id+":new_saved_model_reference")
    fingerprints = {model: models.get(str(seed), {}).get(model, {}).get("parameter_fingerprint") for model in MODELS}
    for key in ("model_fingerprints_before", "model_fingerprints_after_control", "model_fingerprints_after"):
        checks.equal(trial.get(key), fingerprints, "models", trial_id+":"+key)
    checks.equal(trial.get("installed_xml_identity"), source_files.get("src/developmental_physics/assets/ground_body.xml"), "source", trial_id+":original_asset")
    checks.equal(trial.get("support"), {"root": "original_asset_freejoint", "mount": None, "initial_pose": "supine", "external_support": False}, "source", trial_id+":free_root")
    phases = {}
    for phase, selected in (("prefix", prefix), ("target_A", active[:1000]), ("target_B", active[1000:])):
        phases[phase] = contact_summary(selected, name=phase, planned=1000, gate=True, complete=complete)
    domain = all(value["qualification_passed"] for value in phases.values())
    stored_contact = trial.get("contact_population", {})
    checks.numeric(stored_contact.get("phases"), phases, "contact", trial_id+":complete_phases")
    checks.equal(stored_contact.get("qualification_passed"), domain, "contact", trial_id+":domain")
    checks.equal(trial.get("free_root_domain_qualification_passed"), domain, "contact", trial_id+":domain_metadata")
    blocks = []
    for phase, selected, planned in (("prefix", prefix, 1000), ("active", active, 2000)):
        for start in range(0, planned, 200):
            block = [row for row in selected if start <= row["phase_index"] < start+200]
            blocks.append(contact_summary(block, name=f"{phase}_{start}_{start+199}", planned=200, gate=False, complete=complete))
        checks.numeric(trial.get("actual_effort", {}).get(phase), effort_summary(selected, active=phase == "active", complete=complete), "effort", trial_id+":"+phase)
    checks.numeric(stored_contact.get("blocks_0_4s_report_only"), blocks, "contact", trial_id+":report_only_blocks")
    if name in MODELS and (trial.get("controller_spec") is not None or active):
        pd_anchor_saved_spec_check(trial.get("controller_spec"), checks, ledger, trial_id)
    active_effort = effort_summary(active, active=True, complete=complete)
    eligible = bool(complete and len(active) == 2000 and active_effort["complete"] and (domain or name == "zero"))
    errors = []
    held = None
    for row in active:
        target = trial.get("targets_q2", [None, None])[0 if row["phase_index"] < 1000 else 1]
        if row["aq"] is None or vector(target, 2) is None:
            eligible = False
            continue
        error = [row["aq"][axis]-target[axis] for axis in range(2)]
        if not close_tree(row["target"], target) or not close_tree(row["saved_error"], error):
            ledger["invalid_tracking_label_rows"] += 1
        errors.append(error)
        if name in MODELS:
            if row["decision"] is not None:
                held = row["decision"]
            if held is not None and (row["held_residual"] != held.get("selected_residual_nm") or row["held_fallback"] != held.get("fallback")):
                ledger["invalid_held_decision_rows"] += 1
            if held is not None and held.get("fallback") and row["request"] != (0., 0.):
                ledger["invalid_literal_zero_fallback_rows"] += 1
            checks.equal((row["residual_hold_micro_index"], row["macro_decision_index"]),
                         (row["phase_index"]%10, row["phase_index"]//10), "pd_anchor_grid", "saved_ten_native_step_hold_indices")
        if (name == "pd" or name in MODELS and held is not None and held.get("fallback") is False):
            known = row["bq"] is not None and row["bv"] is not None and row["public_PD"] is not None
            checks.check(known, "pd_anchor_grid", "known_saved_public_PD_for_nonfallback_request")
            if known:
                base = clipped_public_PD_checksum(row["bq"], row["bv"], target)
                ledger["clipped_PD_pair_expressions_on_saved_states"] += 1
                checks.numeric(row["public_PD"], base, "pd_anchor_grid", "current_native_clipped_PD_checksum")
                delta = vector(row["held_residual"], 2) if name in MODELS else (0., 0.)
                checks.check(delta is not None and all(abs(value) <= 1. for value in delta),
                             "pd_anchor_grid", "known_held_dynamic_delta_with_shared_bound")
                if delta is not None:
                    expected = tuple(min(.5, max(-.5, base[i]+delta[i])) for i in range(2))
                    checks.numeric(row["request"], expected, "pd_anchor_grid", "actual_saved_final_request_from_current_PD_plus_held_delta")
                ledger["actual_saved_request_origins_checked"] += 1
                require(ledger["actual_saved_request_origins_checked"] <= 18000, "actual_saved_request_checksum_bound")
    axis = [math.sqrt(sum(error[i]**2 for error in errors)/2000) for i in range(2)] if eligible else None
    tracking = {"available": eligible, "planned_active_count": 2000, "observed_active_count": len(active),
        "axis_rmse_rad": axis, "joint_rmse_rad": math.sqrt(sum(sum(error[i]**2 for i in range(2)) for error in errors)/4000) if eligible else None,
        "actual_absolute_two_axis_nm_s": active_effort["actual_absolute_two_axis_nm_s"] if eligible else None,
        "actual_squared_two_axis_nm2_s": active_effort["actual_squared_two_axis_nm2_s"] if eligible else None,
        "native_execution_complete": complete, "free_root_domain_qualification_required": name != "zero",
        "free_root_domain_qualification_passed": domain, "partial_subset_ranking": False}
    batch_records = trial.get("batch_execution_records", [])
    require(isinstance(batch_records, list) and len(batch_records) <= 200, "batch_decision_record_bound")
    decisions = {row["phase_index"]: row["decision"] for row in active if row["decision"] is not None}
    failures = trial.get("planning_failures", [])
    checks.equal(len(batch_records), len(decisions)+len(failures), "batch", trial_id+":attempts_including_unpaid_exception")
    checks.equal(len({record.get("active_index") for record in batch_records}), len(batch_records),
                 "batch", trial_id+":unique_macro_attempts")
    if complete:
        checks.equal(sorted(decisions), list(range(0, 2000, 10)) if name in MODELS else [],
                     "batch", trial_id+":complete_control_macro_population")
    for record in batch_records:
        index = record.get("active_index")
        require(type(index) is int and index in range(0, 2000, 10), "fixed_batch_macro_index")
        ledger["MPC_decision_attempts"] += 1
        for key in ("stage_batches", "feature_batch_rows", "original_scalar_dot_calls", "serial_fallback_selections"):
            value = record.get(key)
            require(type(value) is int and value >= 0, "nonnegative_batch_counter")
            ledger["planning_batch_"+key] += value
        checks.check(record["stage_batches"] <= 150, "batch", "bounded_stage_batches")
        decision = decisions.get(index)
        if decision is not None and record["serial_fallback_selections"] == 0:
            checks.equal(record["feature_batch_rows"], decision.get("pair_prediction_attempts"), "batch", "returned_feature_rows_pair_attempts")
            checks.equal(record["original_scalar_dot_calls"], decision.get("scalar_prediction_attempts"), "batch", "returned_original_dot_scalar_attempts")
            checks.equal(decision.get("pd_request_returns"),
                         1+decision.get("pair_prediction_attempts", 0)-decision.get("residual_candidate_attempts", 0),
                         "batch", "returned_supported_batch_PD_request_population")
        elif record["serial_fallback_selections"]:
            checks.equal([record[key] for key in ("stage_batches", "feature_batch_rows", "original_scalar_dot_calls")], [0, 0, 0], "batch", "serial_fallback_separate_logical_work")
    for failure in failures:
        ledger["MPC_decision_exceptions"] += 1
        accounting = failure.get("pair_planning_accounting", {})
        for key in ("pd_request_attempts", "pd_request_returns", "residual_candidate_attempts"):
            if key in accounting:
                ledger["planning_"+key] += accounting[key]
            else:
                ledger["planning_"+key+"_unknown_failure_count"] += 1
    return {"complete": complete, "domain": domain, "active": active, "tracking": tracking}


def conditional_recheck(raw, seed_rows, trial_info, models, checks, cost):
    groups, path_steps = defaultdict(dict), 0
    for row in iter_records(raw/"predictions.jsonl.gz", cost, record_limit=MAX_PREDICTION_RECORDS, decoded_limit=MAX_PREDICTION_DECODED_BYTES):
        trial_id, seed, model, horizon, origin = (row.get(key) for key in ("trial_id", "seed", "model", "horizon", "origin_active_index"))
        require(seed in SEEDS and trial_id in {f"FR4_{seed}_control_{name}" for name in MODELS}
            and model in MODELS and horizon in HORIZONS and type(origin) is int and origin in range(0, 2000-horizon+1, 10), "fixed_conditional_group_origin")
        group = (trial_id, model, horizon)
        require(origin not in groups[group], "duplicate_conditional_origin")
        groups[group][origin] = {"available": row.get("available") is True, "dq": None, "dv": None}
        checks.equal(row.get("scope"), "control_conditional_prediction", "conditional", "new_conditional_scope")
        qp, vp = row.get("predicted_q_path", []), row.get("predicted_v_path", [])
        require(len(qp) <= horizon and len(vp) <= horizon, "conditional_path_bound")
        path_steps += max(len(qp), len(vp))
        require(path_steps <= MAX_SAVED_PAIR_PATH_STEPS, "conditional_pair_path_budget")
        info = trial_info.get(trial_id, {"active": [], "complete": False, "domain": False})
        segment = info["active"][origin:origin+horizon]
        saved = row.get("model_input")
        if saved is not None and len(segment) == horizon:
            checks.check(close_tree(saved.get("q2"), segment[0]["bq"]) and close_tree(saved.get("v2"), segment[0]["bv"])
                and close_tree(saved.get("known_requests2"), [item["request"] for item in segment]), "conditional", "native_origin_and_actual_final_request_condition")
            checks.equal(row.get("model_parameter_fingerprint"), models[str(seed)][model].get("parameter_fingerprint"), "conditional", "same_new_saved_frozen_model")
        if row.get("available") is True:
            valid = len(qp) == len(vp) == horizon and len(segment) == horizon and all(item["telemetry"] for item in segment)
            valid &= all(vector(value, 2) is not None for value in qp+vp)
            checks.check(valid, "conditional", "full_finite_saved_path_and_native_label")
            if valid:
                aq, av = segment[-1]["aq"], segment[-1]["av"]
                dq, dv = [qp[-1][i]-aq[i] for i in range(2)], [vp[-1][i]-av[i] for i in range(2)]
                checks.check(close_tree(row.get("actual_endpoint_q2"), aq) and close_tree(row.get("actual_endpoint_v2"), av)
                    and close_tree(row.get("q_error_rad"), dq) and close_tree(row.get("v_error_rad_s"), dv),
                    "conditional", "saved_endpoint_minus_independent_native_label")
                groups[group][origin].update(dq=dq, dv=dv)
        else:
            checks.check(bool(row.get("unavailable_reason") or row.get("failure")), "conditional", "unavailable_origin_reason")
    cost["new_saved_conditional_pair_path_steps_no_model_calls"] = path_steps
    output = {}
    for seed in SEEDS:
        for source in MODELS:
            trial_id = f"FR4_{seed}_control_{source}"
            info = trial_info.get(trial_id, {"complete": False, "domain": False})
            saved_score = seed_rows.get(seed, {}).get("conditional_prediction_scores", {}).get(source, {})
            horizons = output[trial_id] = {}
            for horizon in HORIZONS:
                origins = list(range(0, 2000-horizon+1, 10))
                hrow = horizons[str(horizon)] = {}
                original_h = saved_score.get("horizons", {}).get(str(horizon), {})
                if original_h.get("models"):
                    checks.equal(original_h.get("planned_origin_count"), len(origins), "RMSE", "full_conditional_origin_population")
                for model in MODELS:
                    rows = groups[(trial_id, model, horizon)]
                    available = bool(info["complete"] and info["domain"] and set(rows) == set(origins)
                        and all(value["available"] and value["dq"] is not None and value["dv"] is not None for value in rows.values()))
                    q = v = None
                    if available:
                        ordered = [rows[origin] for origin in origins]
                        q = [math.sqrt(sum(value["dq"][i]**2 for value in ordered)/len(origins)) for i in range(2)]
                        v = [math.sqrt(sum(value["dv"][i]**2 for value in ordered)/len(origins)) for i in range(2)]
                    hrow[model] = {"available": available, "q_rmse_axis_rad": q, "v_rmse_axis_rad_s": v, "partial_subset_ranking": False}
                    original = original_h.get("models", {}).get(model, {})
                    checks.equal(bool(original.get("available")), available, "RMSE", trial_id+f":{horizon}:{model}:complete_qualified_priority")
                    checks.numeric(original.get("q_rmse_axis_rad"), q, "RMSE", trial_id+f":{horizon}:{model}:q_vector")
                    checks.numeric(original.get("v_rmse_axis_rad_s"), v, "RMSE", trial_id+f":{horizon}:{model}:v_vector")
                    if original:
                        checks.equal(original.get("partial_subset_ranking"), False, "RMSE", "no_partial_conditional_ranking")
                        checks.equal(original.get("observed_origin_count"), sum(value["available"] for value in rows.values()), "RMSE", "observed_conditional_origin_count")
    return output


def original_control_gate(seed_rows):
    def comparison(baseline, strict, threshold):
        checks, bases, candidates = [], [], []
        complete = set(seed_rows) == set(SEEDS)
        for seed in SEEDS:
            scores = seed_rows.get(seed, {}).get("tracking_scores", {})
            base, candidate = scores.get(baseline, {}), scores.get("learned", {})
            available = bool(base.get("available") and candidate.get("available"))
            if not available:
                complete = False
                checks.append({"seed": seed, "available": False, "passed": False})
                continue
            bases.append(base); candidates.append(candidate)
            bv, cv = [base["joint_rmse_rad"], *base["axis_rmse_rad"]], [candidate["joint_rmse_rad"], *candidate["axis_rmse_rad"]]
            checks.append({"seed": seed, "available": True, "strict": strict, "baseline_joint_axis": bv,
                "learned_joint_axis": cv, "passed": all(c < b if strict else c <= b for b, c in zip(bv, cv))})
        if len(bases) == 3:
            bv = [sum([row["joint_rmse_rad"], *row["axis_rmse_rad"]][i] for row in bases)/3 for i in range(3)]
            cv = [sum([row["joint_rmse_rad"], *row["axis_rmse_rad"]][i] for row in candidates)/3 for i in range(3)]
            fractions = [(b-c)/b if b > 0 else None for b, c in zip(bv, cv)]
            checks.append({"scope": "three_seed_raw_RMSE_mean", "baseline_joint_axis_mean": bv, "learned_joint_axis_mean": cv,
                "improvement_fractions": fractions, "required_improvement": threshold,
                "passed": all(fractions[i] is not None and fractions[i] >= threshold for i in ((0, 1, 2) if strict else (0,)))})
            for key in ("actual_absolute_two_axis_nm_s", "actual_squared_two_axis_nm2_s"):
                b, c = sum(row[key] for row in bases)/3, sum(row[key] for row in candidates)/3
                checks.append({"scope": "three_seed_actual_effort_mean", "signal": key, "baseline_mean": b,
                    "learned_mean": c, "maximum_ratio": 1.05, "passed": c <= 1.05*b if b > 0 else c == 0})
        return {"available": complete, "checks": checks, "passed": bool(complete and all(row["passed"] for row in checks))}
    contribution = comparison("cold", True, .20)
    pd = comparison("pd", False, .05) if contribution["passed"] else {"available": False, "passed": False,
        "reason": "model_contribution_gate_not_passed", "checks": []}
    return {"model_contribution": contribution, "pd_reference": pd,
        "fr4b_model_contribution_gate_passed": contribution["passed"], "fr4b_pd_reference_gate_passed": pd["passed"],
        "fr4_free_root_mechanism_validation": contribution["passed"] and pd["passed"]}


def run_audit(args, checks, cost):
    repo, raw = Path(args.repo).resolve(), Path(args.raw).resolve()
    require(raw == (repo/FR4B_RELATIVE).resolve(), "only_fixed_new_FR4B_raw_allowed")
    require(len(args.source_commit) == 40 and all(x in "0123456789abcdef" for x in args.source_commit), "exact_FR4B_source_commit")
    manifest = parse_json(read_small(raw/"manifest.json", cost), cost)
    loaded, pins = {}, {}
    for name in ("run.json", "metrics.json", "models.json"):
        data = read_small(raw/name, cost)
        pins[name] = identity(data)
        checks.equal(pins[name], manifest.get("files", {}).get(name), "payload", name)
        loaded[name] = parse_json(data, cost)
    for name in ("trace.jsonl.gz", "predictions.jsonl.gz"):
        pins[name] = hash_stream(raw/name, cost)
        checks.equal(pins[name], manifest.get("files", {}).get(name), "payload", name)
    run, metrics, models = (loaded[name] for name in ("run.json", "metrics.json", "models.json"))
    for value in (run, manifest):
        checks.equal((value.get("experiment_id"), value.get("stage")), ("FR4B", "control"), "boundary", "only_new_control_stage")
    checks.equal(run.get("status"), manifest.get("status"), "boundary", "run_manifest_status")
    checks.equal(run.get("seeds"), list(SEEDS), "boundary", "fixed_new_seed_bank")
    for value in (run, manifest, metrics):
        for flag in FLAGS:
            checks.equal(value.get(flag), False, "boundary", flag)
    checks.equal(metrics.get("fr4a_prediction_gate_passed"), False, "boundary", "FR4B_does_not_redeclare_FR4A_gate")
    checks.equal(run.get("planned_upper_bounds"), {"control_calls": 36000, "physics_substeps": 36000,
        "MPC_decisions": 1200, "planning_prediction_pairs": 14580000, "conditional_prediction_pairs": 526560}, "boundary", "frozen_FR4B_budget")
    source_ok = check_sources(repo, raw, run, manifest, args.source_commit, checks, cost)
    trials, seeds = run.get("trials", []), run.get("seed_results", [])
    require(len(trials) <= 12 and len(seeds) <= 3, "fixed_FR4B_matrix_bounds")
    seed_rows, by_id = {row["seed"]: row for row in seeds}, {row["trial_id"]: row for row in trials}
    require(len(seed_rows) == len(seeds) and set(seed_rows).issubset(SEEDS) and len(by_id) == len(trials), "unique_FR4B_seed_trial_matrix")
    for seed in models:
        require(seed in {str(value) for value in SEEDS}, "new_bank_models_only")
        checks.equal(set(models[seed]), set(MODELS), "models", "new_saved_frozen_pair")
        for name, count in (("cold", 0), ("learned", 4000)):
            snapshot_check(models[seed][name], checks, seed+":"+name, count=count, frozen=True)
    ledger, trace = Counter(), defaultdict(list)
    for ordinal, row in enumerate(iter_records(raw/"trace.jsonl.gz", cost, record_limit=MAX_TRACE_RECORDS, decoded_limit=MAX_TRACE_DECODED_BYTES)):
        trace[row["trial_id"]].append(capture_control(row, ordinal, ledger, checks))
    checks.check(set(trace).issubset(by_id), "trials", "trace_matches_saved_trial_matrix")
    info = {name: trial_recheck(trial, trace.get(name, []), models, run.get("source", {}).get("files", {}), ledger, checks) for name, trial in by_id.items()}
    for seed, row in seed_rows.items():
        for name, trial in row.get("controls", {}).items():
            require(name in CONTROLS, "fixed_control_methods_only")
            trial_id = trial["trial_id"]
            checks.equal(trial, by_id.get(trial_id), "trials", "seed_matrix_same_trial_payload")
            checks.numeric(row.get("tracking_scores", {}).get(name), info[trial_id]["tracking"], "tracking", trial_id+":tracking_and_active_effort")
    paid = run.get("cost", {})
    for key in ("control_call_attempts", "control_call_returns", "control_call_exceptions", "confirmed_physics_substeps",
        "captured_substep_endpoint_forward_returns", "captured_native_endpoints", "MPC_decision_attempts", "MPC_decision_returns",
        "MPC_decision_exceptions", "planning_pd_request_attempts", "planning_pd_request_returns", "planning_residual_candidate_attempts",
        "planning_returned_candidate_rejections", "planning_fallback_returns", "planning_batch_stage_batches", "planning_batch_feature_batch_rows",
        "planning_batch_original_scalar_dot_calls", "planning_batch_serial_fallback_selections"):
        checks.equal(paid.get(key, 0), ledger[key], "ledger", key)
    for key in ("invalid_trace_information_rows", "invalid_tracking_label_rows", "invalid_held_decision_rows", "invalid_literal_zero_fallback_rows"):
        checks.equal(ledger[key], 0, "information", key)
    for key in ("RLS_vector_update_attempts", "RLS_vector_update_returns", "RLS_vector_update_exceptions", "RLS_vector_update_commits",
                "RLS_scalar_update_commits", "teacher_calls", "batch_fit_calls", "task_policy_updates", "GPU_training_seconds"):
        checks.equal(paid.get(key), 0, "ledger", "no_FR4B_update_training:"+key)
    for key, bound in (("control_call_attempts", 36000), ("confirmed_physics_substeps", 36000), ("MPC_decision_attempts", 1200)):
        checks.check(type(paid.get(key)) is int and 0 <= paid[key] <= bound, "ledger", key+":budget_bound")
    checks.check(ledger["known_complete_contact_endpoints"] <= paid.get("audit_contact_snapshot_returns", 0) <= paid.get("audit_contact_snapshot_attempts", 0), "ledger", "audit_known_lower_bound")
    checks.check(ledger["known_audit_floor_pairs"] <= paid.get("audit_contact_force_query_returns", 0) <= paid.get("audit_contact_force_query_attempts", 0), "ledger", "force_query_known_lower_bound")
    # Logical forwards are distinct from batch kernels and recorded success steps.
    for key in ("planning_pair_prediction_attempts", "planning_pair_prediction_returns", "planning_scalar_prediction_attempts", "planning_scalar_prediction_returns"):
        if not ledger["MPC_decision_exceptions"]:
            checks.equal(paid.get(key, 0), ledger[key], "ledger", key+":returned_decisions")
    conditional = conditional_recheck(raw, seed_rows, info, models, checks, cost)
    if run.get("status") == "completed" and not run.get("failure"):
        checks.equal(paid.get("control_conditional_prediction_pair_prediction_returns"), cost["new_saved_conditional_pair_path_steps_no_model_calls"], "ledger", "new_conditional_pair_returns")
        checks.equal(paid.get("control_conditional_prediction_scalar_prediction_returns"), 2*cost["new_saved_conditional_pair_path_steps_no_model_calls"], "ledger", "new_conditional_two_head_returns")
    gate = original_control_gate(seed_rows)
    if metrics.get("model_contribution") is not None:
        checks.numeric(metrics.get("model_contribution"), gate["model_contribution"], "gate", "original_20pct_contribution_and_effort")
        checks.numeric(metrics.get("pd_reference"), gate["pd_reference"], "gate", "original_PD_precondition_5pct_and_effort")
    else:
        checks.check(run.get("failure") is not None, "gate", "absent_final_control_gate_requires_saved_failure")
    for key in ("fr4b_model_contribution_gate_passed", "fr4b_pd_reference_gate_passed", "fr4_free_root_mechanism_validation"):
        checks.equal(metrics.get(key), bool(gate[key] and source_ok and run.get("failure") is None), "gate", key+":execution_veto")
    checks.equal(run.get("unattempted_seeds"), [seed for seed in SEEDS if seed not in seed_rows], "trials", "unattempted_seed_preservation")
    for key in ("pd_anchor_grid_macro_checks", "pd_anchor_grid_first_request_pairs_checked",
                "selected_saved_request_path_steps_checked", "actual_saved_request_origins_checked",
                "clipped_PD_pair_expressions_on_saved_states", "PD_anchor_nominal_scalar_distances",
                "PD_anchor_axis_slot_replacements", "PD_anchor_pure_PD_delta_zero_checks", "PD_anchor_saved_spec_checks"):
        cost["new_saved_"+key] = ledger[key]
    return {"payload_pins": pins, "trace_ledger": dict(ledger), "new_tracking_and_active_effort": {key: value["tracking"] for key, value in info.items()},
        "new_conditional_RMSE": conditional, "original_saved_tracking_gate": gate,
        "trial_matrix_complete": len(info) == 12 and all(value["complete"] for value in info.values()),
        "zero_is_descriptive_no_extra_veto": True, "self_prediction_is_reported_no_posthoc_veto": True, "partial_subset_ranking": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".")
    parser.add_argument("--raw", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    raw, output = Path(args.raw).resolve(), Path(args.output).resolve()
    require(output != raw and not output.is_relative_to(raw) and not raw.is_relative_to(output), "audit_output_outside_immutable_raw")
    output.mkdir(parents=True, exist_ok=False)
    checks, cost, result, failure = Checks(), Counter(), None, None
    wall, cpu = time.perf_counter(), time.process_time()
    try:
        result = run_audit(args, checks, cost)
    except BaseException as exc:
        failure = {"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()}
    cost["wall_seconds"], cost["cpu_seconds"] = time.perf_counter()-wall, time.process_time()-cpu
    report = {"schema": "first_FR4B_saved_audit_v1", "raw": str(raw), "source_commit": args.source_commit,
        "auditor": identity(Path(__file__).read_bytes()), "status": "passed" if failure is None and not sum(checks.failed.values()) else "failed",
        "checks": dict(checks.counts), "failed_checks": dict(checks.failed), "first_128_failures": checks.failures,
        "first_failure": failure or (checks.failures[0] if checks.failures else None), "cost": dict(cost),
        "bounds": {"seeds": 3, "trials": 12, "trace_records": 36000, "prediction_records": 11772,
                   "conditional_model_H_groups": 60, "q_v_RMSE_vectors": 120, "tracking_populations": 12,
                   "active_two_axis_effort_vectors": 24, "saved_conditional_pair_path_steps": 526560, "batch_decisions": 1200,
                   "pd_anchor_grid_first_request_pairs_checked": 97200, "selected_saved_request_path_steps_checked": 180000,
                   "actual_saved_request_origins_checked": 18000, "clipped_PD_pair_expressions_on_saved_states": 198000,
                   "PD_anchor_nominal_scalar_distances": 21600, "PD_anchor_axis_slot_replacements": 2400,
                   "PD_anchor_pure_PD_delta_zero_checks": 1200, "PD_anchor_saved_spec_checks": 6},
        "execution": {"model_calls": 0, "model_restoration": 0, "fit": 0, "RLS": 0, "physics": 0,
                      "FR4A_or_old_raw_reads": 0, "old_scientific_recomputations": 0, "automatic_retry": 0,
                      "science_thresholds_changed": False, "controller_or_PD_method_invocations": 0,
                      "new_saved_request_checks": "bounded current PD-anchor arithmetic on saved native/predicted states; no rollout/cost/tie replay"}, "recheck": result}
    for name, value in (("audit.json", report), ("metric_recheck.json", result)):
        with (output/name).open("x", encoding="utf-8") as stream:
            json.dump(json_safe(value), stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
    if report["first_failure"] is not None:
        with (output/"first_failure.json").open("x", encoding="utf-8") as stream:
            json.dump(json_safe(report["first_failure"]), stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
    print(json.dumps({"audit_status": report["status"], "output": str(output), "checks": sum(checks.counts.values()),
                      "failed": sum(checks.failed.values()), "failure": failure}, ensure_ascii=False, allow_nan=False))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
