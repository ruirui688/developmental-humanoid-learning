"""One stdlib-only FR2 projection; no model/PD replay or scientific recomputation."""
import argparse
from collections import Counter
import gzip
import hashlib
import io
import json
import math
from pathlib import Path
import platform
import sys
import time
import traceback

SEEDS, METHODS = (7901, 7902, 7903), ("cold", "learned", "pd", "zero")
PLANNED = {"A": 1000, "B": 1000, "full": 2000}
FLAGS = ("scientific_adoption", "old_free_root_C4_validation", "c4_scientific_validation",
         "c4_contact_scientific_validation", "c5_scientific_dependency_released")
DIRECTIONS = ("delta_zero", "nonzero_delta_zero_effect", "effect_with_delta", "effect_against_delta",
              "effect_with_PD", "effect_against_PD", "nonzero_effect_PD_zero", "final_request_opposes_PD")


def reject_nonfinite_constant(value):
    raise ValueError("nonfinite_JSON_constant:"+value)


def finite_json_float(value):
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("nonfinite_JSON_number:"+value)
    return number


def pair(value):
    return tuple(float(x) for x in value) if isinstance(value, list) and len(value) == 2 and all(
        type(x) in (int, float) and math.isfinite(x) for x in value) else None


def phase():
    return {"rows": 0, "native": 0, "paid_known": 0, "paid_substeps": 0,
            "fallback_known": 0, "fallback": 0, "pd_known": 0, "pd_missing_fallback": 0,
            "pd_missing_other": 0, "pd_sat": [0, 0], "request_known": 0, "request_sat": [0, 0],
            "effect_known": 0, "effect_missing_nonfallback": 0, "effect_sum": [0., 0.],
            "effect_max": [None, None], "clip_loss_sum": [0., 0.],
            "directions": {key: [0, 0] for key in DIRECTIONS}, "macro_returns": 0,
            "macro_fallback_known": 0, "macro_fallback": 0, "macro_feasible": [],
            "macro_unique": Counter(), "macro_unique_unknown": 0, "candidate_records": 0,
            "rejection_reasons": Counter(), "macro_selected_known": 0,
            "macro_selected_zero": [0, 0], "macro_selected_boundary": [0, 0]}


def macro_projection(decision):
    records = decision.get("candidate_records")
    if not isinstance(records, list) or len(records) > 81:
        raise ValueError("bounded_candidate_records_required")
    torques, reasons = [], Counter()
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("candidate_record_object_required")
        torque = pair(record.get("torque"))
        if torque is not None:
            torques.append(torque)
        reason = "feasible_record" if record.get("feasible") is True else record.get("rejection_reason")
        reasons[reason if isinstance(reason, str) else "missing_reason"] += 1
    feasible = decision.get("feasible_candidates")
    return {"records": len(records), "reasons": reasons,
            "unique": len(set(torques)) if len(torques) == len(records) == 81 else None,
            "feasible": feasible if type(feasible) is int and 0 <= feasible <= 81 else None,
            "fallback": decision.get("fallback"), "selected": pair(decision.get("selected_residual_nm"))}


def update(stats, row, method, pd, request, delta, macro):
    stats["rows"] += 1
    stats["native"] += row.get("complete_native_endpoint") is True
    paid = row.get("confirmed_completed_substeps")
    if type(paid) is int and paid in (0, 1):
        stats["paid_known"] += 1; stats["paid_substeps"] += paid
    fallback = row.get("held_fallback")
    model_control = method in ("cold", "learned")
    if model_control and type(fallback) is bool:
        stats["fallback_known"] += 1; stats["fallback"] += fallback
    if pd is not None:
        stats["pd_known"] += 1
        for axis in range(2):
            stats["pd_sat"][axis] += abs(pd[axis]) == .5
    elif method != "zero":
        stats["pd_missing_fallback" if fallback is True else "pd_missing_other"] += 1
    if request is not None:
        stats["request_known"] += 1
        for axis in range(2):
            stats["request_sat"][axis] += abs(request[axis]) == .5
    if model_control and fallback is False:
        if pd is None or request is None or delta is None:
            stats["effect_missing_nonfallback"] += 1
        else:
            stats["effect_known"] += 1
            for axis, (p, u, d) in enumerate(zip(pd, request, delta)):
                effect = u-p
                stats["effect_sum"][axis] += abs(effect)
                stats["effect_max"][axis] = max(stats["effect_max"][axis] or 0., abs(effect))
                stats["clip_loss_sum"][axis] += abs((p+d)-u)
                directions = stats["directions"]
                directions["delta_zero"][axis] += d == 0.
                directions["nonzero_delta_zero_effect"][axis] += d != 0. and effect == 0.
                directions["final_request_opposes_PD"][axis] += p != 0. and u != 0. and (p > 0.) != (u > 0.)
                if effect != 0.:
                    if d != 0.:
                        directions["effect_with_delta" if (effect > 0.) == (d > 0.) else "effect_against_delta"][axis] += 1
                    directions["nonzero_effect_PD_zero" if p == 0. else
                               "effect_with_PD" if (effect > 0.) == (p > 0.) else "effect_against_PD"][axis] += 1
    if macro is not None:
        stats["macro_returns"] += 1
        if type(macro["fallback"]) is bool:
            stats["macro_fallback_known"] += 1; stats["macro_fallback"] += macro["fallback"]
        if macro["feasible"] is not None:
            stats["macro_feasible"].append(macro["feasible"])
        if macro["unique"] is None:
            stats["macro_unique_unknown"] += 1
        else:
            stats["macro_unique"][str(macro["unique"])] += 1
        stats["candidate_records"] += macro["records"]; stats["rejection_reasons"].update(macro["reasons"])
        if macro["selected"] is not None:
            stats["macro_selected_known"] += 1
            for axis, value in enumerate(macro["selected"]):
                stats["macro_selected_zero"][axis] += value == 0.
                stats["macro_selected_boundary"][axis] += abs(value) == .125


def describe(stats, planned, complete, method):
    def saturation(prefix, applicable=True):
        known, counts = stats[prefix+"_known"], stats[prefix+"_sat"]
        return {"applicable": applicable, "known_origins": known if applicable else None,
                "missing_observed_origins": stats["rows"]-known if applicable else None,
                "counts_axis": counts if applicable else None,
                "fractions_of_known_axis": [n/known for n in counts] if known and applicable else None,
                "fractions_of_full_planned_phase_axis": [n/planned for n in counts]
                    if applicable and complete and stats["rows"] == known == planned else None}
    known, model_control = stats["effect_known"], method in ("cold", "learned")
    feasible = stats["macro_feasible"]
    return {"planned_origins": planned, "observed_origins": stats["rows"],
            "unknown_or_unattempted_origins": planned-stats["rows"], "whole_trial_complete": complete,
            "native_endpoints": stats["native"], "paid_count_known_origins": stats["paid_known"],
            "confirmed_substeps_transcribed": stats["paid_substeps"],
            "saved_PD": {**saturation("pd", method != "zero"),
                         "missing_fallback": stats["pd_missing_fallback"] if method != "zero" else None,
                         "missing_other": stats["pd_missing_other"] if method != "zero" else None},
            "final_requested_torque": saturation("request"),
            "fallback": {"applicable": model_control, "known_origins": stats["fallback_known"] if model_control else None,
                         "true_origins": stats["fallback"] if model_control else None,
                         "unknown_observed_origins": stats["rows"]-stats["fallback_known"] if model_control else None},
            "residual_effect": {"applicable": model_control, "known_nonfallback_origins": known if model_control else None,
                "missing_nonfallback_fields": stats["effect_missing_nonfallback"] if model_control else None,
                "mean_absolute_effect_axis_nm": [n/known for n in stats["effect_sum"]] if known else None,
                "maximum_absolute_effect_axis_nm": stats["effect_max"] if known else None,
                "mean_final_clip_loss_axis_nm": [n/known for n in stats["clip_loss_sum"]] if known else None,
                "direction_counts_axis": stats["directions"] if known else None},
            "macro": {"applicable": model_control, "planned_decisions": planned//10 if model_control else 0,
                "returned_decisions": stats["macro_returns"], "fallback_known": stats["macro_fallback_known"] if model_control else None,
                "unreturned_or_unattempted_decisions": planned//10-stats["macro_returns"] if model_control else None,
                "fallback_true": stats["macro_fallback"] if model_control else None, "saved_feasible_count_known": len(feasible),
                "fallback_unknown_returned_decisions": stats["macro_returns"]-stats["macro_fallback_known"] if model_control else None,
                "saved_feasible_count_min_max": [min(feasible), max(feasible)] if feasible else None,
                "unique_first_request_count_histogram": dict(stats["macro_unique"]),
                "unique_first_request_count_unknown_decisions": stats["macro_unique_unknown"],
                "planned_candidate_records": planned//10*81 if model_control else None,
                "candidate_records_observed": stats["candidate_records"], "rejection_reasons": dict(stats["rejection_reasons"]),
                "selected_residual_known": stats["macro_selected_known"],
                "selected_zero_counts_axis": stats["macro_selected_zero"] if stats["macro_selected_known"] else None,
                "selected_boundary_counts_axis": stats["macro_selected_boundary"] if stats["macro_selected_known"] else None}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, required=True); parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    wall, cpu = time.perf_counter(), time.process_time()
    identities, read_attempts, errors, rows = {}, [], [], 0
    groups = {f"FR_{seed}_control_{method}": {"seed": seed, "method": method, "trial": None,
              "prefix_rows": 0, "active_indices": set(), "phases": {name: phase() for name in PLANNED}}
              for seed in SEEDS for method in METHODS}
    macro_count = candidate_count = 0

    def read_once(name):
        if name in read_attempts:
            raise RuntimeError("input_read_twice")
        read_attempts.append(name)
        data = (args.raw/name).read_bytes()
        identities[name] = {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
        return data

    manifest = run = None
    try:
        manifest = json.loads(read_once("manifest.json"), parse_constant=reject_nonfinite_constant, parse_float=finite_json_float)
        if manifest.get("experiment_id") != "FR2" or manifest.get("stage") != "control":
            raise ValueError("new_FR2_control_only")
        run_data = read_once("run.json")
        if manifest.get("files", {}).get("run.json") != identities["run.json"]:
            raise ValueError("manifest_run_identity_differs")
        run = json.loads(run_data, parse_constant=reject_nonfinite_constant, parse_float=finite_json_float)
        if (run.get("experiment_id") != "FR2" or run.get("stage") != "control"
                or run.get("status") != manifest.get("status")
                or any(value.get(flag) is not False for value in (manifest, run) for flag in FLAGS)):
            raise ValueError("saved_FR2_identity_status_or_flags_differ")
        seen_seeds = set()
        for seed_row in run.get("seed_results", []):
            seed = seed_row.get("seed")
            if seed not in SEEDS or seed in seen_seeds:
                raise ValueError("unexpected_or_duplicate_seed")
            seen_seeds.add(seed)
            for method, trial in seed_row.get("controls", {}).items():
                key = f"FR_{seed}_control_{method}"
                if key not in groups or not isinstance(trial, dict):
                    raise ValueError("unexpected_control_summary")
                groups[key]["trial"] = trial
        compressed = read_once("trace.jsonl.gz")
        for name in ("run.json", "trace.jsonl.gz"):
            if manifest.get("files", {}).get(name) != identities[name]:
                raise ValueError("manifest_payload_identity_differs:"+name)
        with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as stream:
            for line in stream:
                rows += 1
                if rows > 36000:
                    raise ValueError("trace_row_cap_exceeded")
                row = json.loads(line, parse_constant=reject_nonfinite_constant, parse_float=finite_json_float); group = groups.get(row.get("trial_id"))
                if group is None or row.get("seed") != group["seed"]:
                    raise ValueError("unexpected_trace_trial")
                if row.get("phase") == "prefix":
                    group["prefix_rows"] += 1
                    if group["prefix_rows"] > 1000:
                        raise ValueError("prefix_cap_exceeded")
                    continue
                index = row.get("phase_index")
                if row.get("phase") != "active" or type(index) is not int or not 0 <= index < 2000 or index in group["active_indices"]:
                    raise ValueError("bounded_unique_active_origin_required")
                group["active_indices"].add(index)
                pd, delta = pair(row.get("public_pd_request2")), pair(row.get("held_residual2"))
                torque = row.get("requested_torque")
                request = pair(torque[:2]) if isinstance(torque, list) else None
                decision, macro = row.get("planning_decision"), None
                if decision is not None:
                    if not isinstance(decision, dict) or group["method"] not in ("cold", "learned") or index % 10:
                        raise ValueError("macro_scope_differs")
                    macro = macro_projection(decision); macro_count += 1; candidate_count += macro["records"]
                    if macro_count > 1200 or candidate_count > 97200:
                        raise ValueError("macro_or_candidate_cap_exceeded")
                for name in ("A" if index < 1000 else "B", "full"):
                    update(group["phases"][name], row, group["method"], pd, request, delta, macro)
    except BaseException as exc:
        errors.append({"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()})
    matrix = []
    for key, group in groups.items():
        trial = group["trial"] or {}; domain = trial.get("control_origin_domain", {})
        matrix.append({"trial_id": key, "seed": group["seed"], "method": group["method"],
            "summary_available": group["trial"] is not None, "saved_status": trial.get("status"),
            "saved_complete": trial.get("complete"), "saved_stop": trial.get("stop"), "saved_failure": trial.get("failure"),
            "prefix_rows": group["prefix_rows"], "qv_whole_2000_saved_summary_transcribed":
                {signal: domain.get(signal) for signal in ("q2", "v2")} if isinstance(domain, dict) else {"q2": None, "v2": None},
            "phases": {name: describe(stats, PLANNED[name],
                       trial.get("complete") if type(trial.get("complete")) is bool and not errors else None, group["method"])
                       for name, stats in group["phases"].items()}})
    result = {"status": "saved_FR2_described" if not errors else "first_projection_failed_preserved", "failures": errors,
        "matrix": matrix, "input_identities": identities, "explicit_file_read_attempts": len(read_attempts),
        "explicit_file_read_names": read_attempts, "explicit_file_reads": len(identities),
        "failed_IO_partial_bytes": "unknown_if_IO_exception_not_zero",
        "explicit_input_bytes_read": sum(pin["bytes"] for pin in identities.values()), "trace_rows_decoded": rows,
        "saved_macro_decisions_projected": macro_count, "candidate_records_projected": candidate_count,
        "scope": "fixed 12 trials; A[0,999]/B[1000,1999]/full[0,1999]; qv summary full2000 only",
        "model_parameter_prediction_journal_or_source_ZIP_reads": 0, "model_PD_replay_fit_physics_calls": 0,
        "RMSE_effort_contact_or_scientific_gate_recomputed": False, "partial_subset_ranking": False,
        "causal_inference": False, "same_first_request_proves_whole_path_equivalence": False, "automatic_retry": False,
        "saved_scientific_flags": {flag: run.get(flag) for flag in FLAGS} if isinstance(run, dict) else None,
        "runtime": {"python": sys.version, "platform": platform.platform()},
        "wall_seconds_before_output": time.perf_counter()-wall, "cpu_seconds_before_output": time.process_time()-cpu}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as output:
        json.dump(result, output, indent=2, allow_nan=False); output.write("\n")
    print(json.dumps({"status": result["status"], "rows": rows, "macro_decisions": macro_count, "failures": len(errors)}))
    return bool(errors)


if __name__ == "__main__":
    raise SystemExit(main())
