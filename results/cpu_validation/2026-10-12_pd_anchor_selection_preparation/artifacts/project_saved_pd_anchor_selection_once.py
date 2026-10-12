"""FR4D candidate: one saved-selection projection, never a model or gate replay."""
from __future__ import annotations

import argparse
from collections import Counter
import gzip
import hashlib
import io
from itertools import product
import json
import math
from pathlib import Path
import platform
import time
import traceback

RAW_RELATIVE = "results/cpu_validation/2026-10-12_pd_anchor_pair_control/raw"
SEEDS = (8101, 8102, 8103)
METHODS = ("learned", "cold")
ALL_METHODS = ("cold", "learned", "pd", "zero")
SCOPES = {"A": (0, 1000), "B": (1000, 2000)}
GRID = (-.5, -.375, -.25, -.125, 0., .125, .25, .375, .5)
PRODUCTION_PINS = {
    "src/developmental_physics/pd_anchor_pair_mpc.py": {"bytes": 26614, "sha256": "d9053b7ae5a8eabca342d29558df7a67fae6cf21f60d6e18110256988f04b3e3"},
    "src/developmental_physics/pd_anchor_pair_development.py": {"bytes": 56106, "sha256": "59de8ff3127bcdb683f325b11e5df88262bf8eda3e5a9f093de6bb9a204e1d64"},
    "scripts/develop_pd_anchor_pair.py": {"bytes": 29329, "sha256": "7b7f9fda0bc98111b78dcefa5535e5e7efa563a6a2f0e827178dc80cf71f1a28"},
    "docs/PD_ANCHOR_PAIR_LEARNING_PROTOCOL.md": {"bytes": 14616, "sha256": "ae9b8ea0515d3ff71ac8c636e08542fa7b19725c5746613acd5d619284978b1f"},
}
MAX_ROWS = 36000
MAX_LINE_BYTES = 2*1024*1024
MAX_DECODED_BYTES = 2*1024*1024*1024


def require(condition, message):
    if not condition:
        raise ValueError(message)


def identity(data):
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def pair(value, *, native=False):
    size = 8 if native else 2
    if isinstance(value, list) and len(value) == size and all(finite(x) for x in value):
        return tuple(float(x) for x in value[:2])
    return None


def parse(data):
    def unique(items):
        result = {}
        for key, value in items:
            require(key not in result, "duplicate_json_key:"+key)
            result[key] = value
        return result
    return json.loads(data, object_pairs_hook=unique,
                      parse_constant=lambda token: (_ for _ in ()).throw(ValueError("nonfinite_json:"+token)))


def origin(seed, method, active_index):
    return {"seed": seed, "method": method, "role": "primary" if method == "learned" else "declared_descriptive_comparator",
            "scope": "A" if active_index < 1000 else "B", "origin_active_index": active_index,
            "trial_id": f"FR4_{seed}_control_{method}", "origin_present": False,
            "q2": None, "v2": None, "current_target_q2": None, "restored_current_PD2": None,
            "saved_public_PD_field_present": None, "saved_public_PD_request2": None,
            "restored_PD_matches_saved_public_PD": None,
            "nearest_original_indices": None, "anchor_candidate_index": None,
            "decision_present": False, "anchor_present_in_expected_slot": None,
            "anchor_feasibility_evaluable": False, "anchor_feasible": None, "anchor_saved_cost": None,
            "anchor_saved_rejection_reason": None,
            "anchor_chosen": None, "selected_delta2": None, "selected_torque2": None,
            "selected_saved_cost": None, "saved_fallback": None, "selected_minus_anchor_saved_cost": None,
            "NA_reasons": ["missing_saved_macro_origin"]}


def project_macro(row, item, cost):
    item["origin_present"] = True
    item["NA_reasons"] = []
    observation = row.get("observation_before") or {}
    q = pair(observation.get("joint_position"), native=True)
    v = pair(observation.get("joint_velocity"), native=True)
    target = pair(row.get("current_target_q2"))
    item.update(q2=q, v2=v, current_target_q2=target)
    cost["saved_public_PD_field_inspections"] += 1
    item["saved_public_PD_field_present"] = "public_pd_request2" in row
    item["saved_public_PD_request2"] = pair(row.get("public_pd_request2"))
    decision = row.get("planning_decision")
    if not isinstance(decision, dict):
        item["NA_reasons"].append("missing_saved_planning_decision")
    else:
        item["decision_present"] = True
        item["selected_delta2"] = pair(decision.get("selected_residual_nm"))
        item["selected_torque2"] = pair(decision.get("torque"))
        item["selected_saved_cost"] = decision.get("cost") if finite(decision.get("cost")) else None
        item["saved_fallback"] = decision.get("fallback") if type(decision.get("fallback")) is bool else None
    if q is None or v is None or target is None:
        item["NA_reasons"].append("missing_finite_current_native_q_v_or_target")
        return
    cost["public_PD_pair_restoration_attempts"] += 1
    cost["public_PD_axis_gain_expressions"] += 2
    command = tuple(64.*(target[i]-q[i])-4.*v[i] for i in range(2))
    if any(math.isnan(x) for x in command):
        item["NA_reasons"].append("nonfinite_public_PD_restoration")
        return
    p = tuple(float(min(.5, max(-.5, x))) for x in command)
    cost["public_PD_pair_restoration_returns"] += 1
    axes, indices = [], []
    for value in p:
        distances = tuple(abs(point-value) for point in GRID)
        cost["nearest_scalar_distances"] += 9
        index = min(range(9), key=lambda j: (distances[j], j))
        cost["nearest_original_index_selections"] += 1
        axis = list(GRID)
        axis[index] = value
        axes.append(tuple(axis))
        indices.append(index)
    points = tuple(product(*axes))
    cost["first_request_pair_enumerations"] += len(points)
    anchor_index = indices[0]*9+indices[1]
    require(len(points) == 81 and points[anchor_index] == p, "fixed_anchor_slot_enumeration_error")
    item.update(restored_current_PD2=p, nearest_original_indices=indices, anchor_candidate_index=anchor_index)
    if item["saved_public_PD_request2"] is not None:
        cost["saved_public_PD_comparisons"] += 1
        item["restored_PD_matches_saved_public_PD"] = item["saved_public_PD_request2"] == p
    if not item["decision_present"]:
        return
    records = decision.get("candidate_records")
    if not isinstance(records, list) or len(records) != 81:
        item["NA_reasons"].append("missing_complete_81_candidate_records")
        return
    record = records[anchor_index]
    cost["anchor_candidate_records_inspected"] += 1
    if not isinstance(record, dict) or pair(record.get("torque")) is None:
        item["NA_reasons"].append("missing_expected_anchor_record_or_finite_first_torque")
        return
    present = pair(record["torque"]) == p
    item["anchor_present_in_expected_slot"] = present
    if not present:
        item["NA_reasons"].append("expected_anchor_slot_first_torque_differs_from_restored_PD")
        return
    feasible = record.get("feasible")
    item["anchor_feasible"] = feasible if type(feasible) is bool else None
    item["anchor_feasibility_evaluable"] = type(feasible) is bool
    item["anchor_saved_cost"] = record.get("cost") if finite(record.get("cost")) else None
    cost["anchor_rejection_field_inspections"] += 1
    item["anchor_saved_rejection_reason"] = record.get("rejection_reason")
    if type(feasible) is not bool:
        item["NA_reasons"].append("missing_saved_anchor_feasible_flag")
    fallback, delta, selected = item["saved_fallback"], item["selected_delta2"], item["selected_torque2"]
    if fallback is True:
        item["anchor_chosen"] = False
    elif fallback is False and delta is not None and selected is not None:
        if delta != (0., 0.):
            item["anchor_chosen"] = False
        elif selected == p:
            item["anchor_chosen"] = True
        else:
            item["NA_reasons"].append("saved_zero_delta_first_torque_mismatch")
    else:
        item["NA_reasons"].append("missing_saved_selection_fields")
    if feasible is True and fallback is False and finite(item["anchor_saved_cost"]) and finite(item["selected_saved_cost"]):
        cost["saved_cost_difference_attempts"] += 1
        difference = item["selected_saved_cost"]-item["anchor_saved_cost"]
        if math.isfinite(difference):
            item["selected_minus_anchor_saved_cost"] = difference
            cost["saved_cost_difference_returns"] += 1
        else:
            item["NA_reasons"].append("nonfinite_saved_cost_difference")
    else:
        item["NA_reasons"].append("saved_selected_minus_anchor_cost_unavailable")


def cell_summary(items, parent, cost):
    fields = ("anchor_present_in_expected_slot", "anchor_feasible", "anchor_chosen", "saved_fallback",
              "saved_public_PD_field_present", "restored_PD_matches_saved_public_PD")
    result = {"seed": items[0]["seed"], "method": items[0]["method"], "scope": items[0]["scope"],
              "role": items[0]["role"], "planned_origins": 100,
              "observed_origins": sum(x["origin_present"] for x in items),
              "parent_trial_metadata_transcribed": parent,
              "full_fixed_origin_population_retained": len(items) == 100,
              "restored_PD_known": sum(x["restored_current_PD2"] is not None for x in items),
              "saved_decision_known": sum(x["decision_present"] for x in items),
              "anchor_feasibility_evaluable": sum(x["anchor_feasibility_evaluable"] for x in items)}
    for field in fields:
        result[field] = {"true": sum(x[field] is True for x in items),
                         "false": sum(x[field] is False for x in items),
                         "NA": sum(x[field] is None for x in items), "fixed_denominator": 100}
    values = sorted(x["selected_minus_anchor_saved_cost"] for x in items
                    if x["selected_minus_anchor_saved_cost"] is not None)
    cost["saved_difference_values_sorted"] += len(values)
    cost["descriptive_distribution_cells"] += 1
    n = len(values)
    quantile = lambda fraction: values[max(0, math.ceil(fraction*n)-1)] if n else None
    result["selected_minus_anchor_saved_cost_distribution"] = {
        "available": bool(n), "known": n, "NA": 100-n, "fixed_denominator": 100,
        "minimum": values[0] if n else None, "q25": quantile(.25), "q50": quantile(.5),
        "q75": quantile(.75), "maximum": values[-1] if n else None,
        "negative": sum(x < 0. for x in values), "exact_zero": sum(x == 0. for x in values),
        "positive": sum(x > 0. for x in values), "quantile_rule": "nearest-rank empirical order statistic; no interpolation",
        "meaning": "difference of two saved model-forecast costs at one origin; no counterfactual actual PD performance"}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".")
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--protocol-sha256", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    for value, size in ((args.source_commit, 40), (args.protocol_sha256, 64)):
        require(len(value) == size and all(x in "0123456789abcdef" for x in value), "exact_frozen_commit_and_protocol_SHA_required")
    repo, output = Path(args.repo).resolve(), Path(args.output).resolve()
    raw = (repo/RAW_RELATIVE).resolve()
    require(output != raw and not output.is_relative_to(raw) and not raw.is_relative_to(output), "fresh_output_must_not_modify_or_contain_raw")
    require(output != repo and not repo.is_relative_to(output), "output_must_not_contain_repository")
    output.mkdir(parents=True, exist_ok=False)
    wall, cpu = time.perf_counter(), time.process_time()
    cost, pins, parent_trials, rows_by_trial, failure = Counter(), {}, {}, Counter(), None
    all_origins = {(seed, method, index): origin(seed, method, index)
                   for seed in SEEDS for method in METHODS for index in range(0, 2000, 10)}
    expected_trials = {f"FR4_{seed}_control_{method}" for seed in SEEDS for method in ALL_METHODS}
    seen = set()
    try:
        buffers = {}
        for name in ("manifest.json", "run.json", "trace.jsonl.gz"):
            path = raw/name
            require(path.stat().st_size <= (512*1024*1024 if name.endswith(".gz") else 16*1024*1024), "fixed_input_size_bound:"+name)
            cost["input_read_attempts"] += 1
            data = path.read_bytes()
            cost["input_read_returns"] += 1
            cost["input_bytes"] += len(data)
            buffers[name], pins[name] = data, identity(data)
        manifest, run = parse(buffers["manifest.json"]), parse(buffers["run.json"])
        cost["small_json_parses"] += 2
        for name in ("run.json", "trace.jsonl.gz"):
            require(manifest.get("files", {}).get(name) == pins[name], "fixed_new_payload_pin_differs:"+name)
        for item in (manifest, run):
            require(item.get("experiment_id") == "FR4B" and item.get("stage") == "control", "fixed_new_FR4B_control_required")
        require(manifest.get("status") == run.get("status"), "fixed_new_manifest_run_status_differs")
        require(run.get("seeds") == list(SEEDS), "fixed_8101_8102_8103_bank_required")
        source = run.get("source") or {}
        require(source.get("commit") == args.source_commit and source.get("clean_committed_bytes_verified") is True,
                "exact_clean_new_FR4B_source_commit_required")
        require(all(source.get("files", {}).get(path) == pin for path, pin in PRODUCTION_PINS.items()),
                "fixed_four_new_production_source_pins_required")
        trials = run.get("trials")
        require(isinstance(trials, list) and len(trials) <= 12, "bounded_fixed_trial_matrix_required")
        for trial in trials:
            name = trial.get("trial_id")
            require(name in expected_trials and name not in parent_trials, "unique_fixed_new_trial_identity_required")
            parent_trials[name] = {key: trial.get(key) for key in ("complete", "status", "stop", "failure")}
        cost["gzip_decode_attempts"] += 1
        with gzip.GzipFile(fileobj=io.BytesIO(buffers["trace.jsonl.gz"]), mode="rb") as stream:
            while line := stream.readline(MAX_LINE_BYTES+1):
                require(len(line) <= MAX_LINE_BYTES and line.endswith(b"\n") and line.strip(), "complete_bounded_trace_line_required")
                cost["decoded_bytes"] += len(line)
                cost["trace_rows"] += 1
                require(cost["trace_rows"] <= MAX_ROWS and cost["decoded_bytes"] <= MAX_DECODED_BYTES, "fixed_decode_population_bound")
                row = parse(line)
                cost["trace_json_parses"] += 1
                require(isinstance(row, dict), "trace_dictionary_required")
                seed, name, index = row.get("seed"), row.get("trial_id"), row.get("control_index")
                require(seed in SEEDS and name in expected_trials and name.startswith(f"FR4_{seed}_control_"), "fixed_trace_trial_identity_required")
                require(type(index) is int and 0 <= index < 3000 and (name, index) not in seen, "unique_bounded_trial_control_index_required")
                seen.add((name, index))
                phase, active_index = ("prefix", index) if index < 1000 else ("active", index-1000)
                require(row.get("phase") == phase and row.get("phase_index") == active_index, "fixed_phase_identity_required")
                rows_by_trial[name+":"+phase] += 1
                if phase == "active" and active_index % 10 == 0:
                    method = name.rsplit("_", 1)[-1]
                    if method in METHODS:
                        cost["observed_selection_origins"] += 1
                        project_macro(row, all_origins[(seed, method, active_index)], cost)
        cost["gzip_decode_returns"] += 1
    except BaseException as exc:
        failure = {"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()}
    records = list(all_origins.values())
    cells = []
    for seed in SEEDS:
        for method in METHODS:
            for scope, (start, end) in SCOPES.items():
                items = [all_origins[(seed, method, index)] for index in range(start, end, 10)]
                cells.append(cell_summary(items, parent_trials.get(items[0]["trial_id"]), cost))
    tool_bytes = Path(__file__).read_bytes()
    cost["tool_source_reads"] += 1
    cost["tool_source_bytes"] += len(tool_bytes)
    report = {"schema": "fr4_saved_selection_projection_v1", "experiment_id": "FR4D",
              "status": "saved_selection_projection_complete" if failure is None else "failed",
              "first_failure": failure, "input_identities": pins,
              "source_commit": args.source_commit, "declared_frozen_protocol_sha256": args.protocol_sha256,
              "bound_production_pins": PRODUCTION_PINS, "tool_source_identity": identity(tool_bytes),
              "scopes_half_open": SCOPES, "planned_origins_by_method": {"learned": 600, "cold": 600},
              "matrix": cells, "origin_records": records, "all_decoded_trial_phase_counts": dict(rows_by_trial),
              "cost": dict(cost), "bounds": {"trace_rows": 36000, "origins": 1200, "cells": 12,
                  "public_PD_pair_restorations": 1200, "public_PD_axis_gain_expressions": 2400,
                  "nearest_scalar_distances": 21600, "nearest_original_index_selections": 2400, "pair_enumerations": 97200,
                  "anchor_candidate_records_inspected": 1200, "saved_cost_differences": 1200,
                  "anchor_rejection_field_inspections": 1200, "saved_public_PD_field_inspections": 1200,
                  "saved_public_PD_comparisons": 1200,
                  "saved_difference_values_sorted": 1200, "distribution_cells": 12},
              "anchor_presence_definition": "saved expected original-slot record has finite first torque equal to restored current PD; no scan for relocated anchors",
              "saved_cost_difference_condition": "anchor present and saved feasible, saved selection nonfallback, both costs finite",
              "counterfactual_actual_PD_performance": False, "causal_inference": False,
              "model_rollout_cost_tie_RMSE_gate_recomputations": 0, "physics_fit_RLS_updates": 0,
              "other_candidate_cost_or_feasible_inspections": 0, "old_results_or_saved_parameter_reads": 0,
              "automatic_retry": False, "partial_subset_ranking": False,
              "scientific_adoption": False, "old_free_root_C4_validation": False,
              "c4_scientific_validation": False, "c4_contact_scientific_validation": False,
              "c5_scientific_dependency_released": False,
              "runtime": {"python": platform.python_version()},
              "wall_seconds_before_output": time.perf_counter()-wall, "cpu_seconds_before_output": time.process_time()-cpu}
    with (output/"projection.json").open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    if failure is not None:
        with (output/"first_failure.json").open("x", encoding="utf-8") as stream:
            json.dump(failure, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
    print(json.dumps({"status": report["status"], "output": str(output), "cost": dict(cost), "first_failure": failure}, ensure_ascii=False, allow_nan=False))
    return int(failure is not None)


if __name__ == "__main__":
    raise SystemExit(main())
