"""F fixed native-context description from sealed E saved predictions only.

Standard library only. No body-model, simulator, runner or prior auditor is
imported. Formal execution is disabled until root freezes the source binding.
"""
from __future__ import annotations

import argparse
from collections import Counter
import gzip
import hashlib
import json
import math
from pathlib import Path
import platform
import re
import subprocess
import sys
import time
import traceback


FORMAL_DIAGNOSTIC_ENABLED = False
CANONICAL_SOURCE = "scripts/diagnose_guard_native_context.py"
SEEDS = (0, 1, 2)
KINDS = ("cold11", "learned_sparse11", "PDselected", "zero")
PREDICTORS = ("cold11", "learned_sparse11")
SCORES = ("body6", "gyro", "acc_delta")
SEGMENTS = ("A", "B")
BINS = ((0., .5), (.5, 1.), (1., None))
ZERO_WORK = ("physical_queries", "model_predict_calls", "rls_updates",
             "policy_updates", "gain_updates", "gate_updates", "C_D_raw_reads")
NATIVE_FIELDS = ("joint_position", "joint_velocity", "imu_gyro", "imu_acceleration")


def new_fee():
    return Counter({key: 0 for key in ZERO_WORK})


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def vector(value, count):
    if not isinstance(value, (list, tuple)) or len(value) != count or not all(finite(x) for x in value):
        return None
    return tuple(float(x) for x in value)


def sub(a, b, fee):
    fee["scalar_subtractions"] += 1
    return a-b


def mul(a, b, fee):
    fee["scalar_products"] += 1
    return a*b


def div(a, b, fee):
    fee["scalar_divisions"] += 1
    return a/b


def total(values, fee):
    values = tuple(values)
    fee["fsum_calls"] += 1
    fee["fsum_terms"] += len(values)
    return math.fsum(values)


def square(a, fee):
    fee["scalar_squares"] += 1
    return a*a


def root(a, fee):
    fee["square_root_calls"] += 1
    return math.sqrt(a)


def norm(values, fee, mean_denominator=1):
    fee["native_norm_calls"] += 1
    try:
        value = total((square(x, fee) for x in values), fee)
        if mean_denominator != 1:
            value = div(value, mean_denominator, fee)
        if not math.isfinite(value):
            return None
        return root(value, fee)
    except (OverflowError, ValueError):
        return None


def native_equal(first, second):
    return isinstance(first, dict) and isinstance(second, dict) and all(
        first.get(key) == second.get(key) for key in NATIVE_FIELDS)


def native_scores(before, qref8, previous_before, fee):
    result = {key: None for key in SCORES}
    reasons = {}
    q = vector(before.get("joint_position"), 8)
    v = vector(before.get("joint_velocity"), 8)
    if q is None or v is None or qref8 is None:
        reasons["body6"] = "missing_finite_native_q_v_or_prefix99_qref"
    else:
        terms = [div(sub(q[j], qref8[j], fee), .15, fee) for j in range(2, 8)]
        terms.extend(div(v[j], 1., fee) for j in range(2, 8))
        result["body6"] = norm(terms, fee, mean_denominator=12)
    gyro = vector(before.get("imu_gyro"), 3)
    if gyro is None:
        reasons["gyro"] = "missing_finite_current_native_gyro"
    else:
        result["gyro"] = norm(gyro, fee)
    acc = vector(before.get("imu_acceleration"), 3)
    prev_acc = None if previous_before is None else vector(previous_before.get("imu_acceleration"), 3)
    if acc is None or prev_acc is None:
        reasons["acc_delta"] = "missing_finite_contiguous_native_acceleration"
    else:
        result["acc_delta"] = norm([sub(acc[i], prev_acc[i], fee) for i in range(3)], fee)
    for name, value in result.items():
        if value is None and name not in reasons:
            reasons[name] = "nonfinite_norm_arithmetic"
    return result, reasons


def saved_errors(row, complete, fee):
    result, reasons = {}, {}
    after = row.get("observation_after") or {}
    predictions = row.get("predicted_next_qv") or {}
    for predictor in PREDICTORS:
        result[predictor], reasons[predictor] = {}, {}
        prediction = predictions.get(predictor)
        for channel, index, field in (("q", 0, "joint_position"), ("v", 1, "joint_velocity")):
            label = vector(after.get(field), 8)
            pred = None if not isinstance(prediction, (list, tuple)) or len(prediction) != 2 else vector(prediction[index], 2)
            if not complete:
                value, reason = None, "not_complete_20ms_interval"
            elif label is None or pred is None:
                value, reason = None, "missing_finite_saved_prediction_or_native_label"
            else:
                value = [sub(label[i], pred[i], fee) for i in range(2)]
                if not all(finite(x) for x in value):
                    value, reason = None, "nonfinite_saved_difference"
                else:
                    reason = None
            result[predictor][channel] = value
            if reason is not None:
                reasons[predictor][channel] = reason
    return result, reasons


def input_quality_flags(row, qref8, previous_before, native_history_valid,
                        complete, original_error_reasons, fee):
    """Independent provenance flags; never alter score/error eligibility."""
    flags = []

    def check(label, value, length):
        if value is None:
            flags.append(label+":missing")
        elif not isinstance(value, (list, tuple)) or len(value) != length:
            flags.append(label+":wrong_shape")
        elif any(type(x) not in (int, float) for x in value):
            flags.append(label+":invalid_scalar_type")
        elif any(not math.isfinite(x) for x in value):
            flags.append(label+":nonfinite")

    before, after = row.get("observation_before") or {}, row.get("observation_after") or {}
    for field, length in (("joint_position", 8), ("joint_velocity", 8),
                          ("imu_gyro", 3), ("imu_acceleration", 3)):
        check("current_native_"+field, before.get(field), length)
    if previous_before is None:
        flags.append("previous_native_endpoint:unavailable_or_discontinuous")
    else:
        check("previous_native_acceleration", previous_before.get("imu_acceleration"), 3)
    if qref8 is None:
        flags.append("prefix99_native_qref:unavailable")
    check("current_target", row.get("target_q"), 2)
    if not native_history_valid:
        flags.append("prediction_native_history:missing" if not isinstance(row.get("history"), dict)
                     else "prediction_native_history:invalid_or_discontinuous")
    if not complete:
        flags.append("interval:not_complete_20ms")
    for channel, index, field in (("q", 0, "joint_position"), ("v", 1, "joint_velocity")):
        check("observed_next_"+channel+"_label", after.get(field), 8)
        for predictor in PREDICTORS:
            prediction = (row.get("predicted_next_qv") or {}).get(predictor)
            if prediction is None:
                flags.append("saved_"+predictor+"_"+channel+"_prediction:missing")
            elif not isinstance(prediction, (list, tuple)) or len(prediction) != 2:
                flags.append("saved_"+predictor+"_"+channel+"_prediction:wrong_container_shape")
            else:
                check("saved_"+predictor+"_"+channel+"_prediction", prediction[index], 2)
            if original_error_reasons[predictor].get(channel) == "nonfinite_saved_difference":
                flags.append("saved_"+predictor+"_"+channel+"_difference:nonfinite")
    for flag in flags:
        fee["input_quality_flag:"+flag] += 1
    fee["input_quality_rows_classified"] += 1
    return flags


def quality_counts(derived, episodes):
    """Ancillary counts only; fixed statistical/native formulas are unchanged."""
    result = []
    for episode in episodes:
        for segment in SEGMENTS:
            rows = [row for row in derived[episode["trial_id"]] if row["target_segment"] == segment]
            result.append({"trial_id": episode["trial_id"], "seed": episode["seed"],
                "kind": episode["kind"], "target_segment": segment, "saved_active_records": len(rows),
                "rows_with_any_quality_flag": sum(bool(row["input_quality_flags"]) for row in rows),
                "independent_flag_counts": dict(Counter(flag for row in rows for flag in row["input_quality_flags"])),
                "count_semantics": "each flag is counted independently; multiple flags may apply to one row"})
    return result


def derive_rows(rows, episodes, fee):
    """One pass over already verified E rows; only source-native arithmetic."""
    plans = {item["trial_id"]: item for item in episodes}
    if len(plans) != len(episodes):
        fee["plan_duplicate_identity_failures"] += 1
        raise ValueError("duplicate planned trial identity")
    output = {name: [] for name in plans}
    notifications = {name: [] for name in plans}
    state = {name: {"last_index": None, "before": None, "after": None,
                    "last_complete": False, "last_contiguous": False, "last_stopped": False,
                    "qref8": None, "seen": set(), "regular_returned": 0} for name in plans}
    for row in rows:
        fee["source_trace_rows_parsed"] += 1
        tid = row.get("trial_id")
        if tid not in plans:
            fee["source_undeclared_trial_identity_failures"] += 1
            raise ValueError("undeclared source trial")
        episode, history = plans[tid], state[tid]
        exception = "collector_exception" in row
        index = row.get("step_index")
        if row.get("seed") != episode["seed"] or row.get("kind") != episode["kind"]:
            fee["source_seed_kind_identity_failures"] += 1
            raise ValueError("source row seed/kind differs from planned trial")
        identity = row.get("shared_transition_id")
        if exception:
            notice = {"trial_id": tid, "step_index": index, "transition_id": identity,
                      "collector_exception": row["collector_exception"],
                      "source_failure_accounting": row.get("failure_accounting"),
                      "diagnostic_prediction_accounting": row.get("diagnostic_prediction_accounting"),
                      "identity_status": "duplicate_notification" if isinstance(identity, str) and identity in history["seen"] else "unique",
                      "new_returned_endpoint_proven_by_ledger": False}
            notifications[tid].append(notice)
            fee["source_exception_notifications"] += 1
            if type(index) is not int or not 0 <= index < 300 or identity != f"{tid}:{index}":
                notice["identity_status"] = "missing_or_invalid_notification_identity"
                fee["exception_notification_invalid_identity"] += 1
                continue
            if identity in history["seen"]:
                fee["exception_notification_duplicate_identity"] += 1
                continue
        elif type(index) is not int or not 0 <= index < 300:
            fee["regular_invalid_step_index_failures"] += 1
            raise ValueError("invalid original step_index")
        if identity != f"{tid}:{index}" or identity in history["seen"]:
            category = "regular_missing_transition_identity_failures" if identity is None else (
                "regular_duplicate_transition_identity_failures" if identity in history["seen"]
                else "regular_wrong_transition_identity_failures")
            fee[category] += 1
            raise ValueError("missing, wrong or duplicated original transition ID")
        history["seen"].add(identity)
        if history["last_index"] is not None and index <= history["last_index"]:
            fee["source_endpoint_order_identity_failures"] += 1
            raise ValueError("source endpoint order is not increasing")
        diagnostics = row.get("returned_step_diagnostics") if exception else row.get("diagnostics")
        exception_return_proven = (exception and episode.get("returned_unwritten_steps") == 1
            and episode.get("returned_steps") == history["regular_returned"]+1)
        returned = isinstance(diagnostics, dict) and (not exception or exception_return_proven)
        if exception:
            notice["new_returned_endpoint_proven_by_ledger"] = returned
        if returned and not exception:
            history["regular_returned"] += 1
        executed = diagnostics.get("executed_substeps") if returned else None
        if returned and (type(executed) is not int or not 0 <= executed <= 10):
            fee["source_returned_substep_identity_failures"] += 1
            raise ValueError("returned substep count is invalid")
        complete = returned and executed == 10
        before, after = row.get("observation_before") or {}, row.get("observation_after") or {}
        adjacent = (history["last_index"] == index-1 and history["last_complete"]
                      and not history["last_stopped"]
                      and native_equal(history["after"], before))
        contiguous = adjacent and history["last_contiguous"]
        previous_before = history["before"] if contiguous else None
        expected_phase = "prefix" if index < 100 else "control"
        if row.get("phase") != expected_phase:
            fee["source_phase_timing_identity_failures"] += 1
            raise ValueError("source phase differs from fixed prefix/control timing")
        if index == 99 and complete:
            history["qref8"] = vector(after.get("joint_position"), 8)
        if index >= 100:
            active = index-100
            declared_history = row.get("history") or {}
            current_v = vector(before.get("joint_velocity"), 8)
            preceding_v = None if previous_before is None else vector(previous_before.get("joint_velocity"), 8)
            native_history_valid = (contiguous and current_v is not None and preceding_v is not None
                and declared_history.get("native_contiguous") is True
                and declared_history.get("history_transition_ids") == [f"{tid}:{index-2}", f"{tid}:{index-1}"]
                and vector(declared_history.get("current_v_rad_s"), 2) == current_v[:2]
                and vector(declared_history.get("previous_v_rad_s"), 2) == preceding_v[:2])
            scores, score_reasons = native_scores(before, history["qref8"], previous_before, fee)
            errors, error_reasons = saved_errors(row, complete, fee)
            target = vector(row.get("target_q"), 2)
            quality_flags = input_quality_flags(row, history["qref8"], previous_before,
                native_history_valid, complete, error_reasons, fee)
            if target is None or not native_history_valid:
                reason = "missing_finite_current_target" if target is None else "missing_or_invalid_contiguous_native_prediction_history"
                errors = {name: {channel: None for channel in ("q", "v")} for name in PREDICTORS}
                error_reasons = {name: {channel: reason for channel in ("q", "v")} for name in PREDICTORS}
            record = {"trial_id": tid, "transition_id": identity, "seed": episode["seed"],
                      "kind": episode["kind"], "step_index": index, "active": active,
                      "target_segment": "A" if active < 100 else "B", "target_q": target,
                      "returned_endpoint": returned, "executed_substeps": executed,
                      "complete_20ms": complete, "partial_interval": returned and not complete,
                      "exception_record": exception, "contiguous_previous_native_endpoint": contiguous,
                      "native_prediction_history_valid": native_history_valid,
                      "input_quality_flags": quality_flags,
                      "scores": scores, "score_missing_reasons": score_reasons,
                      "saved_errors": errors, "error_missing_reasons": error_reasons,
                      "study_abort": row.get("study_abort")}
            output[tid].append(record)
            fee["active_derived_records"] += 1
        stopped = row.get("study_abort") is not None or returned and diagnostics.get("terminated") is True
        history.update(last_index=index, before=before, after=after, last_complete=complete,
                       last_contiguous=adjacent, last_stopped=stopped)
    return output, notifications


def describe(values, fee):
    n = len(values)
    fee["descriptive_series"] += 1
    if not n:
        return {"n": 0, "min": None, "max": None, "mean": None, "centered_square_sum": None, "numerical_reason": None}
    mean = ss = None
    reason = None
    try:
        mean = div(total(values, fee), n, fee)
        centered = [sub(value, mean, fee) for value in values]
        ss = total([square(value, fee) for value in centered], fee)
        if not finite(mean) or not finite(ss) or ss == 0 and min(values) != max(values):
            raise ValueError("overflow or nonconstant-series square underflow")
    except (ValueError, OverflowError):
        mean = mean if finite(mean) else None
        ss = None
        reason = "numerical_unavailable"
    return {"n": n, "min": min(values), "max": max(values), "mean": mean,
            "centered_square_sum": ss, "numerical_reason": reason}


def safe_mean(values, fee):
    if not values:
        return None
    try:
        value = div(total(values, fee), len(values), fee)
        return value if finite(value) else None
    except (ValueError, OverflowError):
        return None


def pearson(xs, ys, xd, yd, fee):
    fee["correlation_descriptions"] += 1
    n = len(xs)
    if n < 3:
        return {"n": n, "r": None, "reason": "too_few_pairs"}
    if xd["numerical_reason"] or yd["numerical_reason"]:
        return {"n": n, "r": None, "reason": "numerical_unavailable"}
    if xd["centered_square_sum"] == 0 or yd["centered_square_sum"] == 0:
        return {"n": n, "r": None, "reason": "zero_variance"}
    try:
        denominator = root(mul(xd["centered_square_sum"], yd["centered_square_sum"], fee), fee)
        if denominator == 0 or not finite(denominator):
            raise ValueError("unavailable denominator")
        numerator = total([mul(sub(x, xd["mean"], fee), sub(y, yd["mean"], fee), fee)
                           for x, y in zip(xs, ys)], fee)
        value = div(numerator, denominator, fee)
        if not finite(value) or abs(value) > 1.+1e-12:
            raise ValueError("unavailable correlation")
        clipped = abs(value) > 1.
        return {"n": n, "r": max(-1., min(1., value)), "reason": None,
                "unit_interval_roundoff_clipped": clipped}
    except (ValueError, OverflowError):
        return {"n": n, "r": None, "reason": "numerical_unavailable"}


def score_statistics(records, predictor, axis, channel, score, fee):
    eligible = [row for row in records if row["complete_20ms"] and row["saved_errors"][predictor][channel] is not None]
    paired = [row for row in eligible if row["scores"][score] is not None]
    xs = [row["scores"][score] for row in paired]
    ys = [row["saved_errors"][predictor][channel][axis] for row in paired]
    fee["scalar_absolute_values"] += len(ys)
    ay = [abs(value) for value in ys]
    xd, yd, ad = describe(xs, fee), describe(ys, fee), describe(ay, fee)
    bins = []
    for low, high in BINS:
        values = [y for x, y in zip(xs, ys) if x >= low and (high is None or x < high)]
        fee["histogram_value_tests"] += len(xs)
        fee["scalar_absolute_values"] += len(values)
        absolutes = [abs(value) for value in values]
        bins.append({"lower_inclusive": low, "upper_exclusive": high, "n": len(values),
                     "fraction_of_valid_score_error_pairs": div(len(values), len(xs), fee) if xs else None,
                     "signed_error_mean": safe_mean(values, fee),
                     "mean_absolute_error": safe_mean(absolutes, fee),
                     "max_absolute_error": max(absolutes) if values else None})
    return {"score": score, "valid_error_n": len(eligible), "paired_n": len(paired),
            "score_missing_with_valid_error_n": len(eligible)-len(paired),
            "score_description": xd, "signed_error_description": yd, "absolute_error_description": ad,
            "pearson_signed": pearson(xs, ys, xd, yd, fee),
            "pearson_absolute": pearson(xs, ay, xd, ad, fee), "fixed_bins": bins}


def summarize_records(derived, episodes, fee):
    groups, events = [], []
    for episode in episodes:
        tid = episode["trial_id"]
        records = derived[tid]
        returned = [row for row in records if row["returned_endpoint"]]
        declared_stop = episode.get("study_abort") is not None or episode.get("environment_terminated") is True
        source_stop = episode["status"] == "terminated" and declared_stop
        tail_ids = {row["transition_id"] for row in returned[-20:]} if source_stop else set()
        earlier_ids = {row["transition_id"] for row in returned[:-20]} if source_stop else set()
        windows = {"all": records}
        if source_stop:
            windows.update(tail20=[row for row in returned if row["transition_id"] in tail_ids],
                           earlier=[row for row in returned if row["transition_id"] in earlier_ids])
        def counts(rows):
            result = {"saved_active_records": len(rows),
            "returned_endpoint_n": sum(row["returned_endpoint"] for row in rows),
            "complete_interval_n": sum(row["complete_20ms"] for row in rows),
            "partial_interval_n": sum(row["partial_interval"] for row in rows),
            "exception_record_n": sum(row["exception_record"] for row in rows),
            "unreturned_saved_record_n": sum(not row["returned_endpoint"] for row in rows)}
            result["score_valid_n"] = {score: sum(row["scores"][score] is not None for row in rows) for score in SCORES}
            result["score_missing_n"] = {score: len(rows)-result["score_valid_n"][score] for score in SCORES}
            result["score_missing_reasons"] = {score: dict(Counter(row["score_missing_reasons"].get(score)
                for row in rows if row["scores"][score] is None)) for score in SCORES}
            result["error_missing_reasons"] = {predictor: {channel: dict(Counter(
                row["error_missing_reasons"][predictor].get(channel)
                for row in rows if row["saved_errors"][predictor][channel] is None)) for channel in ("q", "v")}
                for predictor in PREDICTORS}
            result["diagnostic_denominators"] = []
            for predictor in PREDICTORS:
                for axis in (0, 1):
                    for channel in ("q", "v"):
                        eligible = [row for row in rows if row["complete_20ms"] and row["saved_errors"][predictor][channel] is not None]
                        result["diagnostic_denominators"].append({"predictor": predictor, "axis": axis,
                            "error_channel": channel, "valid_error_n": len(eligible),
                            "score_error_pair_n": {score: sum(row["scores"][score] is not None for row in eligible) for score in SCORES}})
            fee["denominator_description_blocks"] += 1
            return result
        events.append({"trial_id": tid, "seed": episode["seed"], "kind": episode["kind"],
            "source_status": episode["status"], "source_stop": source_stop,
            "declared_source_stop_flags_present": declared_stop,
            "stop_flags_in_exception": episode["status"] == "exception" and declared_stop,
            "event_windows_status": "available" if source_stop else "not_applicable",
            "stop_reason": episode.get("study_abort") or episode.get("environment_stop_reason"),
            "terminal_returned_id": returned[-1]["transition_id"] if source_stop and returned else None,
            "all_counts": counts(records),
            "tail20_counts": counts(windows["tail20"]) if source_stop else None,
            "earlier_counts": counts(windows["earlier"]) if source_stop else None,
            "earlier_empty_reason": "empty_window" if source_stop and len(returned) <= 20 else None,
            "source_phase_budgets": episode.get("phase_budgets"),
            "source_returned_unwritten_steps": episode.get("returned_unwritten_steps"),
            "source_returned_steps": episode.get("returned_steps"),
            "source_written_returned_steps": episode.get("written_returned_steps"),
            "source_unreturned_physics_steps": episode.get("unreturned_physics_steps"),
            "source_collector_exception": episode.get("collector_exception"),
            "partial_interval_records": [{"transition_id": row["transition_id"],
                "executed_substeps": row["executed_substeps"], "target_segment": row["target_segment"],
                "exception_record": row["exception_record"]} for row in records if row["partial_interval"]]})
        for window, window_rows in windows.items():
            for segment in SEGMENTS:
                selected = [row for row in window_rows if row["target_segment"] == segment]
                for predictor in PREDICTORS:
                    for axis in (0, 1):
                        for channel in ("q", "v"):
                            valid_errors = sum(row["complete_20ms"] and row["saved_errors"][predictor][channel] is not None for row in selected)
                            statistics = [score_statistics(selected, predictor, axis, channel, score, fee) for score in SCORES]
                            if window == "earlier" and not window_rows:
                                for item in statistics:
                                    for key in ("pearson_signed", "pearson_absolute"):
                                        item[key]["reason"] = "empty_window"
                            groups.append({"seed": episode["seed"], "kind": episode["kind"],
                                "trial_id": tid, "axis": axis, "predictor": predictor, "error_channel": channel,
                                "target_segment": segment, "window": window,
                                "empty_window_reason": "empty_window" if window == "earlier" and not window_rows else None,
                                "planned_active_n": 100 if window == "all" else None,
                                "counts": counts(selected), "valid_error_n": valid_errors,
                                "complete_error_missing_n": sum(row["complete_20ms"] for row in selected)-valid_errors,
                                "unobserved_planned_endpoint_n": 100-sum(row["returned_endpoint"] for row in selected) if window == "all" else None,
                                "statistics": statistics})
    return {"groups": groups, "events": events,
            "scientific_adoption": {"evaluated": False, "passed": False,
                "reason": "descriptive associations only; original prediction/control/PD gates and C4/C5 dependencies unchanged"}}


def diagnose_rows(rows, episodes, fee=None):
    """Engineering core: supplied rows only; this API does not read any files."""
    fee = new_fee() if fee is None else fee
    derived, notifications = derive_rows(rows, episodes, fee)
    report = summarize_records(derived, episodes, fee)
    report["independent_input_quality_counts"] = quality_counts(derived, episodes)
    report["exception_notifications"] = notifications
    report["derived_by_trial"] = derived
    report["descriptive_fee"] = dict(fee)
    return report


def digest(blob):
    return hashlib.sha256(blob).hexdigest()


def sha256_text(value):
    if not isinstance(value, str) or re.fullmatch("[0-9a-f]{64}", value) is None:
        raise ValueError("expected full lowercase SHA256 required")
    return value


def safe_relative(value):
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError("canonical relative POSIX path required")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or ":" in value:
        raise ValueError("source path must remain inside its declared root")
    return value


def parse(blob):
    return json.loads(blob, parse_constant=lambda value: (_ for _ in ()).throw(ValueError("nonfinite JSON token")))


def read_f_local(path, label, fee):
    fee["f_local_file_opens"] += 1
    fee["f_local_"+label+"_opens"] += 1
    blob = path.read_bytes()
    fee["f_local_binary_bytes_read"] += len(blob)
    fee["f_local_"+label+"_binary_bytes_read"] += len(blob)
    return blob


def clean_f_provenance(binding_path, fee):
    root_path = next(path for path in Path(__file__).resolve().parents if (path/"pyproject.toml").is_file())
    def git(*arguments):
        fee["f_git_read_commands"] += 1
        response = subprocess.run(["git", *arguments], cwd=root_path, capture_output=True, check=True)
        fee["f_git_return_bytes"] += len(response.stdout)
        return response.stdout
    commit = git("rev-parse", "HEAD").decode("ascii").strip()
    if git("status", "--porcelain", "--untracked-files=no"):
        raise ValueError("formal F requires clean tracked working tree")
    source_bytes = read_f_local(Path(__file__), "source", fee)
    if source_bytes != git("show", f"HEAD:{CANONICAL_SOURCE}"):
        raise ValueError("executing F source differs from clean committed canonical source")
    relative_binding = binding_path.resolve().relative_to(root_path).as_posix()
    binding_bytes = read_f_local(binding_path, "binding", fee)
    if binding_bytes != git("show", f"HEAD:{relative_binding}"):
        raise ValueError("runtime source binding is not frozen in clean HEAD")
    binding = parse(binding_bytes)
    protocol = binding["protocol"]
    protocol_name = safe_relative(protocol["path"])
    protocol_bytes = read_f_local(root_path/protocol_name, "protocol", fee)
    if digest(protocol_bytes) != sha256_text(protocol["sha256"]) or protocol_bytes != git("show", f"HEAD:{protocol_name}"):
        raise ValueError("F protocol differs from clean committed runtime freeze")
    return root_path, binding, {"source_commit": commit, "source_sha256": digest(source_bytes),
        "binding_path": relative_binding, "binding_sha256": digest(binding_bytes),
        "protocol": protocol, "source_dirty": False}


class SourceReader:
    """Hash one source read into task cache; parse/decompress that cache only."""
    def __init__(self, archive, cache, fee):
        self.archive, self.cache, self.fee = archive.resolve(), cache, fee
        self.records = {}

    def fetch(self, relative, expected_sha, expected_bytes=None):
        relative = safe_relative(relative)
        expected_sha = sha256_text(expected_sha)
        source = (self.archive/relative).resolve()
        source.relative_to(self.archive)
        target = self.cache/relative
        target.parent.mkdir(parents=True, exist_ok=True)
        hasher, size = hashlib.sha256(), 0
        self.fee["e_source_file_opens"] += 1
        with source.open("rb") as reader, target.open("xb") as writer:
            while True:
                chunk = reader.read(1024*1024)
                if not chunk:
                    break
                writer.write(chunk)
                hasher.update(chunk)
                size += len(chunk)
                self.fee["e_source_binary_bytes_read"] += len(chunk)
        actual_sha = hasher.hexdigest()
        self.records[relative] = {"sha256": actual_sha, "bytes": size}
        if actual_sha != expected_sha or expected_bytes is not None and size != expected_bytes:
            raise ValueError(f"sealed source byte identity mismatch: {relative}")
        return target

    def json(self, relative, expected_sha, expected_bytes=None):
        path = self.fetch(relative, expected_sha, expected_bytes)
        blob = path.read_bytes()
        self.fee["task_cache_json_opens"] += 1
        self.fee["task_cache_json_bytes_read"] += len(blob)
        try:
            return parse(blob)
        except (ValueError, TypeError):
            self.fee["source_json_identity_parse_failures"] += 1
            raise


def sealed_e_inputs(archive, binding, expected_manifest_sha, output, fee, run=None):
    expected_manifest_sha = sha256_text(expected_manifest_sha)
    if binding.get("schema_version") != 1:
        raise ValueError("frozen F runtime binding schema must be one")
    if expected_manifest_sha != sha256_text(binding["source_manifest_sha256"]):
        raise ValueError("CLI manifest identity differs from frozen F binding")
    if re.fullmatch("[0-9a-f]{40}", binding["e_source_commit"]) is None:
        raise ValueError("full E source commit required")
    reader = SourceReader(archive, output/"source_cache", fee)
    if run is not None:
        run["source_records"] = reader.records
    manifest = reader.json("manifest.json", expected_manifest_sha)
    if manifest.get("schema_version") != 1 or manifest.get("failed") != 0 or manifest.get("source_commit") != binding["e_source_commit"]:
        raise ValueError("E sealed outer manifest identity/consistency failed")
    entries = manifest["files"]
    if (manifest.get("payload_count") != len(entries)
            or any(type(entry.get("bytes")) is not int or entry["bytes"] < 0 for entry in entries.values())
            or manifest.get("payload_bytes") != sum(entry["bytes"] for entry in entries.values())):
        raise ValueError("E sealed manifest payload size/count inconsistent")
    for name in ("first_audit.json", "summary_once/summary.json", "raw/manifest.json",
                 "raw/metadata.json", "raw/episodes.json", "raw/trace.jsonl.gz"):
        safe_relative(name)
        if name not in entries:
            raise ValueError("required E sealed input absent")
    def outer_json(name, binding_key=None):
        entry = entries[name]
        if binding_key is not None and entry["sha256"] != sha256_text(binding[binding_key]):
            raise ValueError("outer manifest differs from separately frozen source identity")
        return reader.json(name, entry["sha256"], entry["bytes"])
    first = outer_json("first_audit.json", "first_audit_sha256")
    summary = outer_json("summary_once/summary.json", "summary_sha256")
    raw_manifest = outer_json("raw/manifest.json", "raw_manifest_sha256")
    if first.get("failed") != 0 or first.get("data_consistency_verified") is not True or first.get("archive", {}).get("source_commit") != binding["e_source_commit"]:
        raise ValueError("original E first audit is not consistent with frozen source")
    if (summary.get("source_commit") != binding["e_source_commit"]
            or summary.get("data_consistency_verified") is not True
            or summary.get("binding_checks", {}).get("failed") != 0
            or summary.get("first_audit_sha256") != binding["first_audit_sha256"]
            or summary.get("raw_manifest_sha256") != binding["raw_manifest_sha256"]
            or summary.get("seeds") != first["archive"].get("seeds")
            or summary.get("episodes") != first["archive"].get("episodes")
            or summary.get("paid_prediction_accounting") != first["archive"].get("paid_prediction_accounting")
            or summary.get("restoration_and_cloning") != first["archive"].get("restoration_and_cloning")
            or summary.get("final_gates") != first.get("final_gates")):
        raise ValueError("once-saved E summary identity/consistency failed")
    raw_names = {"metadata.json", "episodes.json", "seed_results.json", "trace.jsonl.gz", "source_snapshot.zip"}
    input_hashes = first["archive"].get("input_hashes", {})
    if (raw_manifest.get("schema_version") != 1 or set(raw_manifest.get("files", {})) != raw_names
            or set(input_hashes) != raw_names | {"manifest.json"}
            or input_hashes["manifest.json"] != binding["raw_manifest_sha256"]):
        raise ValueError("original E first-audit/raw-manifest file identity coverage failed")
    for name in sorted(raw_names):
        if raw_manifest["files"].get(name) != {"sha256": entries["raw/"+name]["sha256"], "bytes": entries["raw/"+name]["bytes"]}:
            raise ValueError("E raw/outer manifest member identity disagrees")
        if input_hashes[name] != raw_manifest["files"][name]["sha256"]:
            raise ValueError("original E first-audit input hash differs from sealed member")
    metadata, episodes = outer_json("raw/metadata.json"), outer_json("raw/episodes.json")
    if (raw_manifest.get("status") != metadata.get("status")
            or metadata.get("suite") != "guard_lag_control_development" or metadata.get("synthetic_fixture") is not False
            or metadata.get("source_commit") != binding["e_source_commit"] or metadata.get("source_dirty") is not False
            or metadata.get("source_status") != "" or metadata.get("seeds") != list(SEEDS)
            or metadata.get("kinds") != list(KINDS) or metadata.get("prefix_steps") != 100
            or metadata.get("control_steps_per_trial") != 200 or metadata.get("joint_indices") != [0, 1]
            or metadata.get("environment_config", {}).get("physics_dt") != .002
            or metadata.get("environment_config", {}).get("control_substeps") != 10
            or any(metadata.get(key) != 0 for key in ("model_updates", "policy_parameter_updates", "gain_updates", "gate_updates", "D_refits", "D_prediction_reexecutions"))):
        raise ValueError("E metadata differs from frozen experiment/zero-update contract")
    if episodes != first["archive"].get("episodes"):
        raise ValueError("source episode ledger differs from original E first audit copy")
    for key in ("control_calls_attempted", "control_steps", "physics_steps"):
        if metadata.get(key) != first["archive"].get("budget", {}).get(key):
            raise ValueError("source paid budget differs from saved original E first audit")
    if summary.get("physics_budget") != first["archive"].get("budget"):
        raise ValueError("saved E summary physics budget is not exact original audit copy")
    outcome_keys = ("completed_trials", "terminated_trials", "exception_trials", "blocked_trials")
    if summary.get("outcomes") != {key: metadata.get(key) for key in outcome_keys}:
        raise ValueError("saved E summary outcomes differ from original metadata copy")
    expected = [(seed, kind, f"seed{seed}_{kind}") for seed in SEEDS for kind in KINDS]
    if [(item["seed"], item["kind"], item["trial_id"]) for item in episodes] != expected:
        raise ValueError("E twelve planned episode identities/order changed")
    if any(item.get("maximum_control_steps") != 300 or item.get("status") not in ("completed", "terminated", "exception", "blocked", "incomplete") for item in episodes):
        raise ValueError("E planned episode outcome/length invalid")
    entry = entries["raw/trace.jsonl.gz"]
    trace_cache = reader.fetch("raw/trace.jsonl.gz", entry["sha256"], entry["bytes"])
    return reader, metadata, episodes, summary, trace_cache


class CountedBinaryCache:
    def __init__(self, stream, fee):
        self.stream, self.fee = stream, fee

    def read(self, size=-1):
        value = self.stream.read(size)
        self.fee["task_cache_gzip_compressed_binary_bytes_read"] += len(value)
        return value

    def seek(self, offset, whence=0):
        return self.stream.seek(offset, whence)

    def tell(self):
        return self.stream.tell()


def cached_trace_rows(path, fee):
    fee["task_cache_gzip_opens"] += 1
    with path.open("rb") as binary, gzip.GzipFile(fileobj=CountedBinaryCache(binary, fee), mode="rb") as stream:
        for blob in stream:
            fee["trace_decompressed_binary_bytes"] += len(blob)
            fee["trace_decompressed_binary_lines"] += 1
            try:
                yield parse(blob)
            except (ValueError, TypeError):
                fee["source_trace_json_identity_parse_failures"] += 1
                raise


def write_json(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as writer:
        json.dump(value, writer, ensure_ascii=False, indent=2, allow_nan=False)
        writer.write("\n")


def run_diagnostic(archive, binding_path, source_manifest_sha256, output):
    if not FORMAL_DIAGNOSTIC_ENABLED:
        raise RuntimeError("F formal saved-data diagnostic is disabled until root freeze")
    archive, binding_path, output = Path(archive), Path(binding_path), Path(output)
    fee, started_wall, started_cpu = new_fee(), time.perf_counter(), time.process_time()
    if output.exists():
        raise FileExistsError("one-attempt F output must not exist")
    output.mkdir(parents=True)
    run = {"status": "preflight", "scientific_adoption": {"evaluated": False, "passed": False}}
    try:
        root_path, binding, provenance = clean_f_provenance(binding_path, fee)
        run["f_provenance"] = provenance
        expected_archive = (root_path/safe_relative(binding["archive_relative_path"])).resolve()
        if archive.resolve() != expected_archive:
            raise ValueError("runtime E archive path differs from frozen binding")
        reader, metadata, episodes, summary, trace = sealed_e_inputs(archive, binding, source_manifest_sha256, output, fee, run)
        run.update(f_provenance=provenance, e_source_commit=metadata["source_commit"], source_records=reader.records,
                   original_e_physics_budget=summary.get("physics_budget"), original_e_gates=summary["final_gates"],
                   original_e_paid_prediction_accounting=summary["paid_prediction_accounting"],
                   original_e_restoration_and_cloning=summary["restoration_and_cloning"])
        report = diagnose_rows(cached_trace_rows(trace, fee), episodes, fee)
        derived = report.pop("derived_by_trial")
        with (output/"derived.jsonl").open("x", encoding="utf-8", newline="\n") as writer:
            for episode in episodes:
                for row in derived[episode["trial_id"]]:
                    writer.write(json.dumps(row, ensure_ascii=False, allow_nan=False)+"\n")
        write_json(output/"description.json", report)
        run["status"] = "completed"
        return run
    except BaseException as exc:
        run.update(status="exception", exception={"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()})
        raise
    finally:
        run.update(descriptive_fee=dict(fee), wall_seconds=time.perf_counter()-started_wall,
                   cpu_seconds=time.process_time()-started_cpu, python=sys.version, platform=platform.platform(),
                   timing_scope="entry through descriptive output writing and this snapshot; excludes run/manifest writing and output-integrity reads/hash")
        final_record_wall, final_record_cpu = time.perf_counter(), time.process_time()
        write_json(output/"run.json", run)
        payloads = {}
        integrity_bytes = 0
        for name in ("run.json", "description.json", "derived.jsonl"):
            path = output/name
            if path.is_file():
                blob = path.read_bytes()
                integrity_bytes += len(blob)
                payloads[name] = {"sha256": digest(blob), "bytes": len(blob)}
        write_json(output/"manifest.json", {"schema_version": 1, "status": run["status"],
            "files": payloads, "source_cache_records": run.get("source_records", {}),
            "output_integrity_reads": {"opens": len(payloads), "bytes": integrity_bytes,
                "hash_operations": len(payloads)},
            "final_record_timing": {"wall_seconds": time.perf_counter()-final_record_wall,
                "cpu_seconds": time.process_time()-final_record_cpu,
                "scope": "run JSON write and output-integrity read/hash; excludes final manifest serialization/write"},
            "scientific_adoption": {"evaluated": False, "passed": False}})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--binding", required=True, type=Path)
    parser.add_argument("--source-manifest-sha256", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = run_diagnostic(args.archive, args.binding, args.source_manifest_sha256, args.output)
    print(json.dumps({"status": result["status"], "scientific_adoption": result["scientific_adoption"]}))


if __name__ == "__main__":
    main()
