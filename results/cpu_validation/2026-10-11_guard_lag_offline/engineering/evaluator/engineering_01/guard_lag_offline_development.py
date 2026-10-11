"""Source-bound C4 single-lag development diagnosis; no simulator or controller.

The public entry is intentionally disabled in ignored staging. Only root may
promote/freeze it and execute the fixed C data once. Internal functions support
small hand-written engineering fixtures, never an alternative research recipe.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import platform
import sys
import time
import zipfile

import numpy as np


FORMAL_OFFLINE_ENABLED = False
CANONICAL_RUNNER = "src/developmental_physics/guard_lag_offline_development.py"
COLLECTION_COMMIT = "5ea8df42b09588845760daf0dc1f270aef2a87f1"
SUMMARY_SHA = "dbc368dc628cb5785415c8b27416215e628a892cf550284a681447f9867aa4af"
AUDIT_SHA = "985137b28d9ee6eb19c98c80e807c815d0d79273a46c938b5f1e4c59be3f33ac"
ORIGINAL_AUDITOR_SHA = "962a928b5d643ed2a3d4da20da2940a9a4e17932818c859beb204f11bf59ffa3"
PREDICTORS = ("nominal9", "sparse9", "continuation9", "lag_sparse11", "lag_continuation11")
SAVED_NAMES = {"nominal9": "nominal_guard", "sparse9": "learned_sparse",
               "continuation9": "learned_continuation"}
TRIAL_KINDS = ("prediction", "nominal_guard", "learned_sparse", "learned_continuation", "PDselected", "zero")
HORIZONS = (1, 2, 5, 15)
FEATURES9 = ("v0", "v1", "q0-qref0", "q1-qref1", "start_G0", "start_G1", "hG0", "hG1", "1")
FEATURES11 = (*FEATURES9, "v0-previous_v0", "v1-previous_v1")


def _clean(value):
    if isinstance(value, np.ndarray):
        return _clean(value.tolist())
    if isinstance(value, np.generic):
        return _clean(value.item())
    if isinstance(value, float) and not np.isfinite(value):
        return "infinite" if value > 0 else "negative_infinite" if value < 0 else "nonfinite"
    if isinstance(value, dict):
        return {str(k): _clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value]
    return value


def _json(path, value):
    Path(path).write_text(json.dumps(_clean(value), ensure_ascii=False, indent=2, allow_nan=False)+"\n", encoding="utf-8")


def _emit(writer, value):
    writer.write(json.dumps(_clean(value), ensure_ascii=False, allow_nan=False)+"\n")
    writer.flush()


def _sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest() if hasattr(hashlib, "file_digest") else hashlib.sha256(stream.read()).hexdigest()


def _error(exc):
    record = exc.to_dict() if hasattr(exc, "to_dict") else {"type": type(exc).__name__, "message": str(exc)}
    for key in ("pair_update_accounting", "pair_prediction_accounting"):
        if hasattr(exc, key):
            record[key] = getattr(exc, key)
    return _clean(record)


def _native(observation):
    q = tuple(float(x) for x in observation["joint_position"][:2])
    v = tuple(float(x) for x in observation["joint_velocity"][:2])
    if len(q) != 2 or len(v) != 2 or not np.isfinite([q, v]).all():
        raise ValueError("two finite original encoder positions/velocities required")
    return q, v


def _complete(row):
    return (isinstance(row.get("diagnostics"), dict)
            and row["diagnostics"].get("executed_substeps") == 10
            and "observation_before" in row and "observation_after" in row)


def _request(row):
    values = tuple(float(x) for x in row["requested_torque"][:2])
    if len(values) != 2 or not np.isfinite(values).all():
        raise ValueError("finite saved final request required")
    return values


def _continuous(previous, current):
    return (previous["trial_id"] == current["trial_id"]
            and previous["step_index"]+1 == current["step_index"]
            and _complete(previous) and _complete(current)
            and _native(previous["observation_after"]) == _native(current["observation_before"])
            and previous.get("study_abort") is None
            and not previous["diagnostics"].get("terminated", False))


def native_intervals(rows, *, phase):
    """Keep source-valid native windows, plus explicit unavailable reasons.

    Initial history is prefix98/99's two returned endpoints. Every later origin
    uses the immediately preceding returned native endpoint, never future v.
    """
    by_step = {r["step_index"]: r for r in rows if "step_index" in r}
    if len(by_step) != len(rows):
        raise ValueError("duplicate or missing step index in trial")
    prefix98, prefix99 = by_step.get(98), by_step.get(99)
    history_ready = (prefix98 is not None and prefix99 is not None
                     and prefix98.get("phase") == prefix99.get("phase") == "prefix"
                     and _continuous(prefix98, prefix99))
    intervals, unavailable = [], []
    ages = [0, 0]
    last_active = None
    for row in sorted(rows, key=lambda r: r["step_index"]):
        if row.get("phase") != phase:
            continue
        step = row["step_index"]
        previous = by_step.get(step-1)
        reason = None
        if not _complete(row):
            reason = "not_a_complete_returned_20ms_interval"
        elif step == 100:
            if not history_ready or not _continuous(prefix99, row):
                reason = "prefix98_99_history_not_complete_native_continuous"
        elif previous is None or previous.get("phase") != phase or not _continuous(previous, row):
            reason = "previous_active_native_endpoint_unavailable_or_discontinuous"
        if reason:
            unavailable.append({"transition_id": row.get("shared_transition_id"), "step_index": step, "reason": reason})
            ages = [0, 0]
            last_active = None
            continue
        q, v = _native(row["observation_before"])
        # At active0, current v is prefix99 endpoint, prior v prefix98 endpoint.
        prior = prefix98 if step == 100 else by_step.get(step-2)
        if prior is None or not _complete(prior) or not _continuous(prior, previous):
            unavailable.append({"transition_id": row.get("shared_transition_id"), "step_index": step,
                                "reason": "immediately_prior_velocity_endpoint_unavailable"})
            continue
        previous_v = _native(prior["observation_after"])[1]
        u = _request(row)
        if last_active is None or last_active+1 != step:
            ages = [0, 0]
        ages = [ages[i]+1 if u[i] != 0. else 0 for i in range(2)]
        intervals.append({"row": row, "q": q, "v": v, "u": u, "previous_v": previous_v,
                          "history_transition_ids": [prior["shared_transition_id"], previous["shared_transition_id"]],
                          "request_nonzero_age_steps": ages.copy()})
        last_active = step
    return intervals, unavailable


def windows(intervals):
    """Every predictor shares these windows, independent of its predictions."""
    output = []
    for origin, interval in enumerate(intervals):
        sequence = []
        for item in intervals[origin:origin+max(HORIZONS)]:
            if sequence and not _continuous(sequence[-1]["row"], item["row"]):
                break
            sequence.append(item)
            if item["row"].get("study_abort") is not None or item["row"]["diagnostics"].get("terminated", False):
                break
        available = [h for h in HORIZONS if h <= len(sequence)]
        output.append({"origin": interval, "sequence": sequence[:max(available)], "available_horizons": available})
    return output


def start_guard(q, u, ranges, ledger):
    ledger["diagnostic_guard_pair_evaluations"] += 1
    clipped = [max(-.5, min(.5, x)) for x in u]
    return tuple(0. if ((q[i] <= ranges[i][0]+.03 and clipped[i] < 0.)
                       or (q[i] >= ranges[i][1]-.03 and clipped[i] > 0.)) else clipped[i] for i in range(2))


def design_row(interval, qref, ranges, lag, ledger):
    g = start_guard(interval["q"], interval["u"], ranges, ledger)
    hinges = [np.sign(x)*max(abs(x)-.25, 0.) for x in g]
    result = [*interval["v"], *(interval["q"][i]-qref[i] for i in range(2)), *g, *hinges, 1.]
    if lag:
        result += [interval["v"][i]-interval["previous_v"][i] for i in range(2)]
    ledger["design_feature_rows_11" if lag else "design_feature_rows_9"] += 1
    return result


def design_diagnostics(matrix, names, ledger):
    x = np.asarray(matrix, dtype=np.float64)
    n, p = x.shape
    means = np.mean(x, axis=0)
    centered = x-means
    rms = np.sqrt(np.mean(centered**2, axis=0))
    constant = np.all(x == x[0], axis=0)
    z = np.zeros_like(x)
    for col in range(p):
        if constant[col]:
            if np.all(x[:, col] == 1.):
                z[:, col] = 1.
        else:
            z[:, col] = centered[:, col]/rms[col]
    gram = z.T @ z/n
    correlation = (z-z.mean(axis=0)).T @ (z-z.mean(axis=0))/n
    ledger["design_gram_matrix_products"] += 2
    singular = np.linalg.svd(z, compute_uv=False)
    ledger["design_svd_calls"] += 1
    tolerance = np.finfo(np.float64).eps*max(n, p)*singular[0]
    rank = int(np.count_nonzero(singular > tolerance))
    condition = float(singular[0]/singular[-1]) if rank == p else float("inf")
    coefficient_scale = rms.copy()
    for col in range(p):
        if np.all(x[:, col] == 1.):
            coefficient_scale[col] = 1.
    ledger["design_statistic_passes"] += 1
    return {"columns": list(names), "rows": n, "minimum": x.min(axis=0), "maximum": x.max(axis=0),
            "mean": means, "variance": np.mean(centered**2, axis=0), "centered_rms": rms,
            "coefficient_column_scale": coefficient_scale,
            "constant_columns": np.flatnonzero(constant), "zero_variance_columns": np.flatnonzero(rms == 0.),
            "normalization": "nonconstant centered/RMS; identically-one column kept one; other constant columns kept zero",
            "standardized_gram": gram, "column_correlation": correlation,
            "standardized_design_singular_values": singular, "gram_singular_values": singular**2/n,
            "rank_tolerance": tolerance, "numerical_rank": rank, "rank_is_an_adoption_gate": False,
            "standardized_design_condition": condition, "standardized_gram_condition": condition**2,
            "condition_reason": None if rank == p else "numerical_rank_less_than_column_count"}


def modal_diagnostics(theta, lag, ledger):
    theta = np.asarray(theta, dtype=np.float64)
    a, b = theta[:, :2], theta[:, 2:4]
    identity = np.eye(2)
    if lag:
        c = theta[:, 9:11]
        f = np.block([[identity+.02*b, .02*(a+c), -.02*c], [b, a+c, -c], [np.zeros((2, 2)), identity, np.zeros((2, 2))]])
    else:
        f = np.block([[identity+.02*b, .02*a], [b, a]])
    eigen = np.linalg.eigvals(f)
    singular = np.linalg.svd(f, compute_uv=False)
    commutator = f.T @ f-f @ f.T
    ledger["modal_eigenvalue_calls"] += 1
    ledger["modal_svd_calls"] += 1
    ledger["modal_matrix_products"] += 2
    ledger["modal_frobenius_norm_calls"] += 1
    return {"matrix": f, "eigenvalues": [{"real": float(x.real), "imag": float(x.imag)} for x in eigen],
            "spectral_radius": float(np.max(np.abs(eigen))), "operator_2_norm": float(singular[0]),
            "nonnormality_commutator_frobenius": float(np.linalg.norm(commutator, ord="fro")),
            "scope": "fixed guard branch; excludes contact/guard switching; no stability/adoption gate"}


def snapshot_drift(snapshots, scales, lag, ledger):
    records, previous = [], None
    for count in (100, 200, 300, 400):
        snapshot = snapshots.get(count)
        if snapshot is None:
            records.append({"vector_update_count": count, "available": False, "reason": "not_published"})
            continue
        coefficients = np.asarray(snapshot["coefficients"], dtype=np.float64)
        change = None if previous is None else coefficients-previous
        raw = weighted = None
        if change is not None:
            raw = np.linalg.norm(change, axis=1)
            weighted = np.linalg.norm(change*np.asarray(scales), axis=1)
            ledger["coefficient_change_head_l2_norms"] += 4
        records.append({"vector_update_count": count, "available": True, "snapshot": snapshot,
                        "coefficient_change": change, "raw_change_l2_per_head": raw,
                        "centered_column_rms_weighted_change_l2_per_head": weighted,
                        "modal_diagnostics": modal_diagnostics(coefficients, lag, ledger)})
        previous = coefficients
    return records


def _prediction_counts(exc):
    record = getattr(exc, "pair_prediction_accounting", None)
    if record is None and hasattr(exc, "scalar_prediction_attempts"):
        record = {"scalar_prediction_attempts": exc.scalar_prediction_attempts,
                  "scalar_prediction_successes": exc.scalar_prediction_successes}
    return record


def _predict(model, q, v, u, previous_v, lag, ledger, scope):
    ledger[f"{scope}_pair_attempts"] += 1
    try:
        result = model.predict(q, v, u, previous_v) if lag else model.predict(q, v, u)
    except BaseException as exc:
        ledger[f"{scope}_pair_failures"] += 1
        counts = _prediction_counts(exc)
        if counts is None:
            ledger[f"{scope}_unknown_scalar_failure_count"] += 1
        else:
            ledger[f"{scope}_scalar_attempts"] += counts["scalar_prediction_attempts"]
            ledger[f"{scope}_scalar_successes"] += counts["scalar_prediction_successes"]
        raise
    ledger[f"{scope}_scalar_attempts"] += 2
    ledger[f"{scope}_scalar_successes"] += 2
    if not np.isfinite(result).all() or np.asarray(result).shape != (2, 2):
        ledger[f"{scope}_pair_failures"] += 1
        raise ValueError("nonfinite or invalid-shaped returned pair prediction")
    ledger[f"{scope}_pair_successes"] += 1
    return tuple(result[0]), tuple(result[1])


def instrument_calibrator(model, ledger):
    original_predict, original_propose, original_features = model._predict_state, model._propose_update, model._features

    def predict_state(*args, **kwargs):
        ledger["rls_internal_pair_attempts"] += 1
        try:
            result = original_predict(*args, **kwargs)
        except BaseException as exc:
            ledger["rls_internal_pair_failures"] += 1
            counts = _prediction_counts(exc)
            if counts is None:
                ledger["rls_internal_unknown_scalar_failure_count"] += 1
            else:
                ledger["rls_internal_scalar_attempts"] += counts["scalar_prediction_attempts"]
                ledger["rls_internal_scalar_successes"] += counts["scalar_prediction_successes"]
            raise
        ledger["rls_internal_pair_successes"] += 1
        ledger["rls_internal_scalar_attempts"] += 2
        ledger["rls_internal_scalar_successes"] += 2
        return result

    def propose(*args, **kwargs):
        ledger["rls_scalar_proposal_attempts"] += 1
        result = original_propose(*args, **kwargs)
        ledger["rls_scalar_proposal_successes"] += 1
        return result

    def features(*args, **kwargs):
        ledger["rls_model_feature_pair_attempts"] += 1
        result = original_features(*args, **kwargs)
        ledger["rls_model_feature_pair_successes"] += 1
        return result

    model._predict_state, model._propose_update, model._features = predict_state, propose, features


def fit_calibration(model, intervals, writer, ledger, *, expected_count=400):
    if len(intervals) != expected_count or [x["row"]["step_index"] for x in intervals] != list(range(100, 100+expected_count)):
        raise ValueError("calibration must contain its full fixed native sequence; no cropped refit")
    instrument_calibrator(model, ledger)
    snapshots, failure, attempted = {}, None, 0
    initial = model.snapshot()
    for item in intervals:
        row = item["row"]
        before_count, before_ledger = model.update_count, dict(ledger)
        ledger["offline_vector_update_attempts"] += 1
        attempted += 1
        update, error = None, None
        try:
            update = model.update(item["q"], item["v"], item["u"], _native(row["observation_after"])[1],
                                  item["previous_v"], transition_id=row["shared_transition_id"])
            ledger["offline_vector_update_returns"] += 1
        except Exception as exc:
            error = _error(exc)
            ledger["offline_vector_update_failures"] += 1
            failure = error
        finally:
            committed = model.update_count-before_count
            ledger["offline_vector_updates_committed"] += committed
            ledger["offline_scalar_updates_committed"] += 2*committed
            snapshot = model.snapshot()
            if model.update_count in (100, 200, 300, 400):
                snapshots[model.update_count] = snapshot
            _emit(writer, {"record_type": "lag_calibration_update", "trial_id": row["trial_id"], "seed": row["seed"],
                           "kind": row["kind"], "transition_id": row["shared_transition_id"], "step_index": row["step_index"],
                           "input": {"q": item["q"], "v": item["v"], "u": item["u"], "previous_v": item["previous_v"],
                                     "next_v_label": _native(row["observation_after"])[1]},
                           "history_transition_ids": item["history_transition_ids"], "update": update, "failure": error,
                           "committed_vector_updates": committed, "fingerprint_after": snapshot["parameter_fingerprint"],
                           "snapshot_at_fixed_count": snapshot if model.update_count in (100, 200, 300, 400) else None,
                           "cost_delta": {k: ledger[k]-before_ledger.get(k, 0) for k in ledger if ledger[k] != before_ledger.get(k, 0)}})
        if failure:
            break
    completed = model.update_count == expected_count and failure is None
    return {"initial_snapshot": initial, "final_snapshot": model.snapshot(), "snapshots": snapshots,
            "completed": completed, "failure": failure, "attempted_vector_updates": attempted,
            "unexecuted_planned_updates": expected_count-attempted,
            "remaining_uncommitted_updates": expected_count-model.update_count,
            "frozen_model": model.clone_frozen() if completed else None}


def saved_one_step(item, name, model, trial_fingerprints):
    saved_name = SAVED_NAMES.get(name)
    if saved_name is None:
        return None
    row = item["row"]
    prediction = row.get("predicted_next_qv", {}).get(saved_name)
    inputs = row.get("model_input_diagnostics", {}).get(saved_name)
    fingerprint = row.get("model_fingerprints", {}).get(saved_name)
    provenance = "saved_row_model_fingerprint"
    if fingerprint is None:
        before, after = trial_fingerprints.get("models_before", {}), trial_fingerprints.get("models_after", {})
        if before.get(saved_name) == after.get(saved_name) and saved_name in before:
            fingerprint = before[saved_name]
            provenance = "bound_saved_trial_equal_before_after_fingerprints"
        elif (row["kind"] == saved_name
              and trial_fingerprints.get("model_fingerprint_before") == trial_fingerprints.get("model_fingerprint_after")
              and trial_fingerprints.get("model_fingerprint_before") is not None):
            fingerprint = trial_fingerprints["model_fingerprint_before"]
            provenance = "bound_saved_actor_equal_before_after_fingerprints"
    if prediction is None or inputs is None or fingerprint != model.parameter_fingerprint():
        return None
    if (tuple(inputs.get("native_q_rad", ())) != item["q"]
            or tuple(inputs.get("requested_nm", ())) != item["u"]
            or tuple(inputs.get("model_feature_command_nm", ())) != tuple(inputs.get("projected_start_nm", ()))
            or inputs.get("input_basis") != "known_angle_guard"):
        return None
    # Fingerprint binds qref, guard and coefficients; original source-native v
    # comes from this exact row. No truth endpoint is used as predicted v.
    if np.asarray(prediction).shape != (2, 2) or not np.isfinite(prediction).all():
        raise ValueError("bound saved one-step prediction is invalid")
    return {"q": tuple(prediction[0]), "v": tuple(prediction[1]), "fingerprint": fingerprint,
            "provenance": provenance, "source_transition_id": row["shared_transition_id"],
            "native_v_exact": item["v"], "saved_input": inputs}


def rollout(window, name, model, ranges, trial_fingerprints, ledger):
    item, sequence = window["origin"], window["sequence"]
    before_ledger = dict(ledger)
    row = item["row"]
    record = {"record_type": "conditional_offline_rollout", "seed": row["seed"], "trial_id": row["trial_id"],
              "kind": row["kind"], "origin_transition_id": row["shared_transition_id"], "origin_step_index": row["step_index"],
              "predictor": name, "available_horizons": window["available_horizons"],
              "history_transition_ids": item["history_transition_ids"], "native_start": {"q": item["q"], "v": item["v"], "previous_v": item["previous_v"]},
              "request_nonzero_age_steps": item["request_nonzero_age_steps"], "steps": [], "failure": None,
              "future_request_semantics": "offline conditioning only; never actor-visible or future actual input"}
    if model is None:
        record["unavailable_reason"] = "lag_calibration_failed_or_unavailable"
        record["cost_delta"] = {}
        return record
    lag = name.startswith("lag_")
    fingerprint = model.parameter_fingerprint()
    record["model_fingerprint"] = fingerprint
    q, v, previous_v = item["q"], item["v"], item["previous_v"]
    for step, source in enumerate(sequence, start=1):
        command = source["u"]
        g = start_guard(q, command, ranges, ledger)
        call_before = dict(ledger)
        reuse = saved_one_step(item, name, model, trial_fingerprints) if step == 1 else None
        try:
            if reuse is not None:
                predicted_q, predicted_v = reuse["q"], reuse["v"]
                ledger["reused_saved_pair_predictions"] += 1
            else:
                predicted_q, predicted_v = _predict(model, q, v, command, previous_v, lag, ledger, "evaluation")
            record["steps"].append({"h": step, "source_transition_id": source["row"]["shared_transition_id"],
                                     "input": {"q": q, "v": v, "previous_v": previous_v, "requested_u": command, "start_G": g},
                                     "prediction": {"q": predicted_q, "v": predicted_v}, "reuse": reuse,
                                     "cost_delta": {k: ledger[k]-call_before.get(k, 0) for k in ledger if ledger[k] != call_before.get(k, 0)}})
            previous_v, q, v = v, predicted_q, predicted_v
        except Exception as exc:
            record["failure"] = {"at_h": step, "source_transition_id": source["row"]["shared_transition_id"],
                                 "input": {"q": q, "v": v, "previous_v": previous_v, "requested_u": command, "start_G": g},
                                 "error": _error(exc), "cost_delta": {k: ledger[k]-call_before.get(k, 0) for k in ledger if ledger[k] != call_before.get(k, 0)}}
            break
    if model.parameter_fingerprint() != fingerprint:
        raise RuntimeError("frozen predictor mutated during rollout")
    record["cost_delta"] = {k: ledger[k]-before_ledger.get(k, 0) for k in ledger if ledger[k] != before_ledger.get(k, 0)}
    return record


def _age_group(age):
    return "zero" if age == 0 else "1" if age == 1 else "2" if age == 2 else "3-5" if age <= 5 else "6+"


def metrics(records, trial_windows, ranges, ledger):
    results = []
    for name in PREDICTORS:
        own = [r for r in records if r["predictor"] == name]
        for h in HORIZONS:
            valid = [w for w in trial_windows if h in w["available_horizons"]]
            common = {w["origin"]["row"]["shared_transition_id"]: w for w in valid}
            eligible = [r for r in own if r["origin_transition_id"] in common]
            for axis in range(2):
                grouped = {"all": eligible}
                for sign in ("negative", "zero", "positive"):
                    grouped[f"native_start_G:{sign}"] = []
                for age in ("zero", "1", "2", "3-5", "6+"):
                    grouped[f"request_nonzero_age:{age}"] = []
                for r in eligible:
                    origin = common[r["origin_transition_id"]]["origin"]
                    g = start_guard(origin["q"], origin["u"], ranges, ledger)[axis]
                    sign = "negative" if g < 0 else "positive" if g > 0 else "zero"
                    grouped[f"native_start_G:{sign}"].append(r)
                    grouped[f"request_nonzero_age:{_age_group(origin['request_nonzero_age_steps'][axis])}"].append(r)
                for group, members in grouped.items():
                    failed = [r for r in members if r.get("failure") is not None and r["failure"]["at_h"] <= h]
                    unavailable = [r for r in members if r.get("unavailable_reason")]
                    errors = {"q": [], "v": []}
                    for r in members:
                        if len(r["steps"]) < h:
                            continue
                        truth = _native(common[r["origin_transition_id"]]["sequence"][h-1]["row"]["observation_after"])
                        for index, key in enumerate(("q", "v")):
                            errors[key].append(r["steps"][h-1]["prediction"][key][axis]-truth[index][axis])
                    result = {"predictor": name, "h": h, "axis": axis, "group": group,
                              "complete_window_count": len(members), "mathematical_failure_count": len(failed),
                              "unavailable_model_window_count": len(unavailable), "successful_endpoint_count": len(errors["q"]),
                              "available": bool(members) and not failed and not unavailable,
                              "reason": "no_complete_source_window" if not members else "mathematical_failure_retained" if failed else "predictor_unavailable" if unavailable else None,
                              "sample_size_note": "single_window_descriptive_only" if len(members) == 1 else "empty" if not members else None}
                    for key in ("q", "v"):
                        error = np.asarray(errors[key], dtype=np.float64)
                        result[key] = ({"rmse": float(np.sqrt(np.mean(error**2))), "signed_bias_prediction_minus_observation": float(np.mean(error)),
                                        "maximum_absolute_error": float(np.max(np.abs(error)))} if result["available"] else None)
                    results.append(result)
    return results


def _binding(source_root, freeze_path, protocol_path, execution_context, repository_root):
    root, repository_root = Path(source_root), Path(repository_root)
    summary_path, audit_path = root/"summary_once/summary.json", root/"first_audit.json"
    if _sha(summary_path) != SUMMARY_SHA or _sha(audit_path) != AUDIT_SHA:
        raise ValueError("sealed original summary/first-audit identity mismatch")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    if (summary["source_commit"] != COLLECTION_COMMIT or summary["binding_checks"]["failed"] != 0
            or audit["failed"] != 0 or summary["expected_auditor_sha256"] != ORIGINAL_AUDITOR_SHA
            or audit["audit_script_sha256"] != ORIGINAL_AUDITOR_SHA):
        raise ValueError("C sealed provenance/certification mismatch")
    identities = {}
    for name, expected in summary["original_input_sha256"].items():
        path = root/"raw"/name
        actual = _sha(path)
        if actual != expected:
            raise ValueError(f"original raw byte identity mismatch: {name}")
        identities[name] = {"sha256": actual, "bytes": path.stat().st_size}
    if set(identities) != {"metadata.json", "episodes.json", "seed_results.json", "trace.jsonl.gz", "source_snapshot.zip", "manifest.json"}:
        raise ValueError("exact six original raw inputs required")
    freeze = json.loads(Path(freeze_path).read_text(encoding="utf-8"))
    if (execution_context.get("verified_source_commit") != freeze["source_commit"]
            or execution_context.get("verified_clean_worktree") is not True):
        raise ValueError("root verified clean source execution context required")
    if CANONICAL_RUNNER not in freeze["source_sha256"] or str(Path(__file__).resolve()) != str((repository_root/CANONICAL_RUNNER).resolve()):
        raise ValueError("only promoted canonical source may execute formally")
    if not freeze["source_sha256"] or not any("guard_lag_pair_model.py" in p for p in freeze["source_sha256"]):
        raise ValueError("frozen helper source identity missing")
    for name, expected in freeze["source_sha256"].items():
        path = (repository_root/name).resolve()
        if not path.is_relative_to(repository_root.resolve()) or _sha(path) != expected:
            raise ValueError(f"frozen runtime source mismatch: {name}")
    protocol_relative = str(Path(protocol_path).resolve().relative_to(repository_root.resolve())).replace("\\", "/")
    if protocol_relative not in freeze["source_sha256"]:
        raise ValueError("exact current offline protocol must be in source freeze")
    return {"collection_commit": COLLECTION_COMMIT, "original_inputs": identities,
            "summary": {"sha256": SUMMARY_SHA, "bytes": summary_path.stat().st_size},
            "first_audit": {"sha256": AUDIT_SHA, "bytes": audit_path.stat().st_size},
            "source_freeze": freeze, "source_freeze_sha256": _sha(freeze_path),
            "execution_context": execution_context, "protocol_path": protocol_relative}, summary


def _restore9(snapshot):
    from developmental_physics.guard_coupled_pair_model import GuardCoupledPairBodyModel
    from developmental_physics.local_pair_model import _parameter_state
    model = GuardCoupledPairBodyModel(snapshot["qref_rad"], public_joint_ranges=snapshot["input_mapping"]["public_guard"]["public_joint_ranges_rad"], trainable=False)
    model._state = _parameter_state(np.asarray(snapshot["coefficients"], dtype=np.float64), np.asarray(snapshot["covariance"], dtype=np.float64), snapshot["vector_update_count"])
    if model.parameter_fingerprint() != snapshot["parameter_fingerprint"] or model.snapshot()["coefficients"] != snapshot["coefficients"]:
        raise ValueError("published original9 snapshot restoration mismatch")
    return model


def instrument_evaluation_model(model, ledger):
    original = model._features

    def features(*args, **kwargs):
        ledger["evaluation_model_feature_pair_attempts"] += 1
        result = original(*args, **kwargs)
        ledger["evaluation_model_feature_pair_successes"] += 1
        return result

    model._features = features


def run_single_lag_offline(output, *, source_root, protocol_path, source_freeze_path, execution_context):
    if not FORMAL_OFFLINE_ENABLED:
        raise RuntimeError("ignored staging offline evaluator is not authorized for real data arithmetic")
    repository_root = Path(__file__).resolve().parents[2]
    output = Path(output)
    if output.exists():
        raise FileExistsError("one-attempt output must not exist; never overwrite failures")
    output.mkdir(parents=True)
    started_wall, started_cpu = time.perf_counter(), time.process_time()
    ledger = defaultdict(int)
    run = {"schema_version": 1, "status": "started", "created_at_utc": datetime.now(timezone.utc).isoformat(),
           "execution_context": execution_context, "calibrations": [], "failure": None,
           "scope": "fixed same-development-data single-lag offline diagnosis; no selection/science pass",
           "new_physics_control_calls": 0, "new_physics_substeps": 0, "original9_refits": 0,
           "mpc_select_calls": 0, "policy_gain_gate_updates": 0, "pd_teacher_calls": 0, "real_robot_calls": 0}
    _json(output/"attempt.json", run)
    try:
        binding, summary = _binding(source_root, source_freeze_path, protocol_path, execution_context, repository_root)
        with zipfile.ZipFile(output/"source_snapshot.zip", "w", zipfile.ZIP_DEFLATED) as archive:
            for name in binding["source_freeze"]["source_sha256"]:
                archive.write(repository_root/name, name)
            archive.writestr("runtime_source_freeze.json", Path(source_freeze_path).read_bytes())
        binding["source_snapshot_sha256"] = _sha(output/"source_snapshot.zip")
        root = Path(source_root)/"raw"
        seed_results = json.loads((root/"seed_results.json").read_text(encoding="utf-8"))
        grouped = defaultdict(list)
        consumed_rows, decoded_bytes = 0, 0
        with gzip.open(root/"trace.jsonl.gz", "rt", encoding="utf-8") as stream:
            for line in stream:
                consumed_rows += 1
                decoded_bytes += len(line.encode("utf-8"))
                row = json.loads(line)
                grouped[(row["seed"], row["kind"])].append(row)
        binding["read_cost"] = {"identity_sha_reads": 8+len(binding["source_freeze"]["source_sha256"])+1,
                                "trace_rows_parsed": consumed_rows, "trace_decompressed_bytes": decoded_bytes,
                                "raw_seed_results_bytes": (root/"seed_results.json").stat().st_size}
        _json(output/"source_binding.json", binding)
        from developmental_physics.guard_lag_pair_model import GuardLagPairBodyModel
        diagnostics, summary_trials, prepared, models_by_seed = [], [], {}, {}
        with gzip.open(output/"calibration_updates.jsonl.gz", "wt", encoding="utf-8") as cal_writer, gzip.open(output/"rollouts.jsonl.gz", "wt", encoding="utf-8") as rollout_writer:
            # ALL original designs/coefficient snapshots are diagnosed before
            # any fresh fit; no historical nine-dimensional model is updated.
            for seed in (0, 1, 2):
                result = next(x for x in seed_results if x["seed"] == seed)
                qref, ranges = tuple(result["reference_q"]), result["public_joint_ranges"]
                models_by_seed[seed] = {"nominal9": _restore9(result["nominal_model"]), "sparse9": _restore9(result["learned_models"]["learned_sparse"]),
                                        "continuation9": _restore9(result["learned_models"]["learned_continuation"])}
                for kind in ("sparse", "continuation"):
                    intervals, unavailable = native_intervals(grouped[(seed, f"calibration_{kind}")], phase="calibration")
                    if unavailable or len(intervals) != 400:
                        raise ValueError("certified full C calibration history unavailable; no repair")
                    x9 = [design_row(x, qref, ranges, False, ledger) for x in intervals]
                    d9 = design_diagnostics(x9, FEATURES9, ledger)
                    saved = {x["row"]["model_snapshot_after"]["vector_update_count"]: x["row"]["model_snapshot_after"]
                             for x in intervals if x["row"]["model_snapshot_after"]["vector_update_count"] in (100, 200, 300, 400)}
                    old_drift = snapshot_drift(saved, d9["coefficient_column_scale"], False, ledger)
                    g = np.asarray(x9)[:, 4:6]
                    x11 = [design_row(x, qref, ranges, True, ledger) for x in intervals]
                    d11 = design_diagnostics(x11, FEATURES11, ledger)
                    diag = {"seed": seed, "calibration": kind, "design9": d9, "design11": d11,
                        "start_G_negative_counts": np.sum(g < 0., axis=0), "start_G_zero_counts": np.sum(g == 0., axis=0),
                        "start_G_positive_counts": np.sum(g > 0., axis=0), "hinge_nonzero_counts": np.sum(np.asarray(x9)[:, 6:8] != 0., axis=0),
                        "saved_actual_dose": result["evaluations"][f"calibration_{kind}"]["excitation"],
                        "original9_saved_coefficient_drift": old_drift}
                    prepared[(seed, kind)] = {"intervals": intervals, "record": diag}
                    diagnostics.append(diag)
            run["phase_sequence"] = ["all_six_native_design9_design11_and_original9_saved_drift_complete"]
            _json(output/"diagnostics.json", diagnostics)
            for seed in (0, 1, 2):
                result = next(x for x in seed_results if x["seed"] == seed)
                qref, ranges = tuple(result["reference_q"]), result["public_joint_ranges"]
                models = models_by_seed[seed]
                for kind in ("sparse", "continuation"):
                    intervals, diag = prepared[(seed, kind)]["intervals"], prepared[(seed, kind)]["record"]
                    fitted = fit_calibration(GuardLagPairBodyModel(qref, public_joint_ranges=ranges), intervals, cal_writer, ledger)
                    models[f"lag_{kind}11"] = fitted.pop("frozen_model")
                    diag.update(lag11_coefficient_drift=snapshot_drift(fitted["snapshots"], diag["design11"]["coefficient_column_scale"], True, ledger),
                                lag11_final_snapshot=fitted["final_snapshot"])
                    run["calibrations"].append({"seed": seed, "kind": kind, "completed": fitted["completed"], "failure": fitted["failure"],
                                                 "attempted_vector_updates": fitted["attempted_vector_updates"],
                                                 "committed_vector_updates": fitted["final_snapshot"]["vector_update_count"],
                                                 "unexecuted_planned_updates": fitted["unexecuted_planned_updates"],
                                                 "remaining_uncommitted_updates": fitted["remaining_uncommitted_updates"]})
                    run["cost_ledger"] = dict(ledger)
                    _json(output/"run.json", run)
                    _json(output/"diagnostics.json", diagnostics)
            run["phase_sequence"].append("all_six_single_pass_fresh_lag11_fits_complete_or_failure_retained")
            for seed in (0, 1, 2):
                result = next(x for x in seed_results if x["seed"] == seed)
                ranges, models = result["public_joint_ranges"], models_by_seed[seed]
                for model in models.values():
                    if model is not None:
                        instrument_evaluation_model(model, ledger)
                for kind in TRIAL_KINDS:
                    phase = "prediction" if kind == "prediction" else "control"
                    intervals, unavailable = native_intervals(grouped[(seed, kind)], phase=phase)
                    trial_windows = windows(intervals)
                    trial_saved = result["evaluations"][kind]
                    records = []
                    for window in trial_windows:
                        for name in PREDICTORS:
                            record = rollout(window, name, models.get(name), ranges, trial_saved, ledger)
                            _emit(rollout_writer, record)
                            records.append(record)
                    summary_trials.append({"seed": seed, "kind": kind, "original_status": trial_saved["status"],
                        "original_completed": trial_saved["completed"], "source_unavailable_intervals": unavailable,
                        "source_complete_interval_count": len(intervals),
                        "source_complete_windows_per_h": {str(h): sum(h in w["available_horizons"] for w in trial_windows) for h in HORIZONS},
                        "metrics": metrics(records, trial_windows, ranges, ledger)})
                    _json(output/"summary.json", {"schema_version": 1, "predictors": PREDICTORS, "horizons": HORIZONS, "trials": summary_trials,
                        "no_scientific_gates_or_ranking": True, "same_development_data": True})
            run["phase_sequence"].append("all_fixed_common_source_windows_conditionally_evaluated")
        run["status"] = "completed_with_retained_calibration_failures" if any(not c["completed"] for c in run["calibrations"]) else "completed"
    except BaseException as exc:
        run["status"], run["failure"] = "exception", _error(exc)
        raise
    finally:
        run["cost_ledger"] = dict(ledger)
        run["execution"] = {"wall_seconds": time.perf_counter()-started_wall, "cpu_seconds": time.process_time()-started_cpu,
                            "timing_scope": "entry through final records; excludes final run/manifest write", "python": sys.version,
                            "numpy": np.__version__, "platform": platform.platform()}
        _json(output/"run.json", run)
        _json(output/"manifest.json", {"schema_version": 1, "status": run["status"],
            "files": {p.name: {"sha256": _sha(p), "bytes": p.stat().st_size} for p in sorted(output.iterdir()) if p.is_file() and p.name != "manifest.json"}})
    return run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--protocol", required=True)
    parser.add_argument("--source-freeze", required=True)
    parser.add_argument("--execution-context", required=True)
    args = parser.parse_args()
    run_single_lag_offline(args.output, source_root=args.source_root, protocol_path=args.protocol,
                          source_freeze_path=args.source_freeze, execution_context=json.loads(Path(args.execution_context).read_text(encoding="utf-8")))


if __name__ == "__main__":
    main()
