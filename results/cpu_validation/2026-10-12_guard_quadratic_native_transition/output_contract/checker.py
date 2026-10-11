"""Thin Q saved-output contract: identities, shapes, paid counts and saved flags only."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import time
import traceback

SEEDS = (0, 1, 2)
HORIZONS = (1, 2, 5, 15)
PREDICTORS = ("Q22", "K22", "D11")
FLAGS = ("scientific_adoption", "c4_scientific_validation", "c5_scientific_dependency_released")
FILES = ("parameters.json", "predictions.jsonl", "metrics.json", "run.json")
SOURCE_PINS = {
    "scripts/develop_guard_quadratic_native_transition.py": (29407, "6a8109ed9ba68b61674f9744ac0ea4ffce421ff8b4400abfe7cc081b5c16a147"),
    "docs/GUARD_QUADRATIC_NATIVE_TRANSITION_DEVELOPMENT_PROTOCOL.md": (5230, "77cb47c42efad889f4d15cf64207b528ab2c7e29908d55d3f16441b0b7a6c5d3"),
}
STATE = [f"q{i}-qref{i}" for i in range(8)]+[f"v{i}" for i in range(8)]+[f"gyro_{c}" for c in "xyz"]+[f"accel_{c}/9.81" for c in "xyz"]
PAIRS = [[i, j] for i in range(6) for j in range(i, 6)]
FEATURES = STATE+["startG0", "startG1", "hinge_startG0_.25", "hinge_startG1_.25", "1", "v0-previous_v0", "v1-previous_v1"]+[f"z{i}*z{j}" for i, j in PAIRS]
Z_NAMES = ["(q0-qref0)/.12", "(q1-qref1)/.12", "v0/1", "v1/1", "startG0/.5", "startG1/.5"]


def vector(value, width):
    return isinstance(value, list) and len(value) == width


def matrix(value, rows, cols):
    return vector(value, rows) and all(vector(row, cols) for row in value)


def flags(value):
    return isinstance(value, dict) and all(value.get(name) is False for name in FLAGS)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", required=True)
    parser.add_argument("--expected-source-commit", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    raw, output = Path(args.raw).resolve(), Path(args.output).resolve()
    if raw == output or raw.is_relative_to(output) or output.is_relative_to(raw):
        raise ValueError("output_must_be_separate_from_input")
    output.mkdir(parents=True, exist_ok=False)
    wall, cpu = time.perf_counter(), time.process_time()
    cost, inputs, checks = Counter(), {}, []
    status, failure = "failed", None

    def require(condition, label):
        cost["group_check_attempts"] += 1
        checks.append({"group": label, "passed": bool(condition)})
        if not condition:
            cost["group_check_failures"] += 1
            raise ValueError(label)
        cost["group_check_returns"] += 1

    def read(path):
        cost["file_read_attempts"] += 1
        data = path.read_bytes()
        cost["file_read_returns"] += 1
        cost["raw_bytes_read"] += len(data)
        cost["sha256_input_bytes"] += len(data)
        inputs[str(path)] = {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
        return data

    def parse(data):
        cost["json_parse_attempts"] += 1
        value = json.loads(data, parse_constant=lambda token: (_ for _ in ()).throw(ValueError("invalid_nonfinite_JSON:"+token)))
        cost["json_parse_returns"] += 1
        return value

    try:
        (output/"checker.py").write_bytes(read(Path(__file__).resolve()))
        manifest = parse(read(raw/"manifest.json"))
        completed = manifest.get("status") == "completed"
        expected_files = set(FILES) if completed else set(FILES)|{"failure.json"}
        require(manifest.get("schema_version") == 1 and manifest.get("status") in ("completed", "failed")
                and manifest.get("scientific_adoption") is False and set(manifest["files"]) == expected_files,
                "01_manifest_status_and_payload_population")
        blobs = {name: read(raw/name) for name in expected_files}
        require(all(manifest["files"][name] == inputs[str(raw/name)] for name in expected_files), "02_payload_byte_hash_bindings")
        docs = {name: parse(data) for name, data in blobs.items() if name.endswith(".json")}
        records = [parse(line) for line in blobs["predictions.jsonl"].splitlines() if line.strip()]
        parameters, metrics, run = docs["parameters.json"], docs["metrics.json"], docs["run.json"]
        require(run.get("status") == metrics.get("status") == manifest["status"] and run.get("self_check") is False
                and flags(run) and flags(metrics)
                and (run.get("failure") is None if completed else isinstance(run.get("failure"), dict) and docs["failure.json"] == run),
                "03_saved_run_status_flags_and_failed_partial")
        source = run["source"]
        require(source.get("commit") == run.get("requested_source_commit") == args.expected_source_commit
                and all((name in source["files"] or not completed) and (name not in source["files"] or source["files"][name] == {"bytes": size, "sha256": sha})
                        for name, (size, sha) in SOURCE_PINS.items())
                and (source.get("clean_committed_bytes_verified") is True if completed else type(source.get("clean_committed_bytes_verified")) is bool),
                "04_exact_Q_source_identity_and_clean_completion")
        parameter_seeds = [p["seed"] for p in parameters]
        require(parameter_seeds == (list(SEEDS) if completed else list(SEEDS[:len(parameters)]))
                and all(p.get("predictor") == "Q22" and p.get("fixed_lambda") == .01
                        and p.get("state_order") == STATE and p.get("feature_order") == FEATURES
                        and p.get("quadratic_z_names") == Z_NAMES and p.get("quadratic_phi29_indices") == [0,1,8,9,22,23]
                        and p.get("quadratic_public_scales") == [.12,.12,1,1,.5,.5]
                        and p.get("quadratic_pair_order") == PAIRS and p.get("quadratic_prior_coefficients") == "all_zero_21x22"
                        and vector(p.get("qref8"), 8) for p in parameters),
                "05_parameter_population_and_fixed_50_22_mapping")
        shapes = {"phi400x50": (400,50), "delta_labels400x22": (400,22), "gram50x50": (50,50),
                  "cross50x22": (50,22), "ridge_normal50x50": (50,50), "weights50x22": (50,22)}
        require(all(p.get("training_fixed_count") == p.get("training_source_active_count") == 400
                    and p.get("training_transition_ids") == [f"seed{p['seed']}_calibration_sparse:{i}" for i in range(100,500)]
                    and (p.get("available") is True and p.get("training_usable_count") == 400 and p["fit"].get("status") == "returned"
                         and all(matrix(p["fit"].get(name), *shape) for name, shape in shapes.items()) if completed else
                         all(matrix(value, len(value), shapes[name][1]) and len(value) <= shapes[name][0]
                             for name, value in p["fit"].items() if name in shapes)) for p in parameters),
                "06_training_identity_dimensions_and_retained_partial")
        paid = run["cost"]
        exact_budget = {"fit_attempts":3,"fit_returns":3,"fit_failures":0,"fit_shared_50x50_22rhs_solve_attempts":3,
                        "fit_shared_50x50_22rhs_solve_returns":3,"fit_shared_50x50_22rhs_solve_failures":0,
                        "fit_scalar_labels_requested":26400,"fit_scalar_labels_returned":26400,
                        "transition_scalar_coefficients_fitted":3300,"transition_heads_published":66,
                        "Q_training_scale_scalar_divisions_requested":7200,"Q_training_scale_scalar_divisions_returned":7200,
                        "Q_training_quadratic_scalar_products_requested":25200,"Q_training_quadratic_scalar_products_returned":25200,
                        "saved_K_design_scalar_copy_requests":34800,"saved_K_design_scalar_copy_returns":34800}
        require(isinstance(paid, dict) and all(paid.get(key) == 0 for key in ("physics_calls","physics_substeps","RLS_updates","MPC_calls","K22_refits","D11_updates"))
                and (all(paid.get(key) == value for key, value in exact_budget.items()) if completed else
                     all(type(paid.get(key)) in (int,float) and 0 <= paid[key] <= value for key,value in exact_budget.items() if key in paid)),
                "07_saved_paid_fit_budget_and_zero_extra_interaction")
        require(not completed or (run.get("source_active_counts") == {f"seed{s}_prediction":100 for s in SEEDS}
                and all(run.get(f"{p}_fingerprints_before") == run.get(f"{p}_fingerprints_after")
                        and set(run[f"{p}_fingerprints_before"]) == {str(s) for s in SEEDS} for p in ("K22","D11"))
                and all(p.get("K22_parameter_fingerprint") == run["K22_fingerprints_before"][str(p["seed"])]
                        and p.get("D11_parameter_fingerprint") == run["D11_fingerprints_before"][str(p["seed"])] for p in parameters)),
                "08_saved_source_counts_and_unchanged_baseline_fingerprints")
        expected_records = {(s,h,p,o) for s in SEEDS for h in HORIZONS for p in PREDICTORS for o in range(101-h)}
        identities = [(r["seed"],r["horizon"],r["predictor"],r["origin"]) for r in records]
        require(len(set(identities)) == len(identities) and set(identities) <= expected_records
                and (not completed or set(identities) == expected_records), "09_fixed_prediction_record_identities")
        def context_ok(row):
            s,h,o = row["seed"],row["horizon"],row["origin"]
            if row.get("trial_id") != f"seed{s}_prediction" or row.get("offline_saved_future_requests") is not True or type(row.get("available")) is not bool:
                return False
            if "initial_x22" not in row:
                return row["available"] is False and isinstance(row.get("reason"),str) and row["reason"].startswith("window_unavailable:")
            return (vector(row["initial_x22"],22) and vector(row.get("previous_v2"),2) and matrix(row.get("requested_sequence8"),h,8)
                    and row.get("history_transition_ids") == [f"seed{s}_prediction:{i}" for i in (98+o,99+o)]
                    and row.get("requested_transition_ids") == [f"seed{s}_prediction:{100+o+i}" for i in range(h)]
                    and type(row.get("source_stopped_at_endpoint")) is bool)
        require(all(context_ok(r) for r in records), "10_native_context_shapes_and_same_trial_request_history")
        def outcome_ok(row):
            h,p = row["horizon"],row["predictor"]
            available = row["available"]
            if not available and not isinstance(row.get("reason"),str):
                return False
            if "initial_x22" not in row:
                return True
            path_name = "predicted_path_qv" if p == "D11" else "predicted_path_x22"
            path = row.get(path_name)
            if not isinstance(path,list) or len(path) > h or (available and len(path) != h):
                return False
            if p == "D11":
                if not all(matrix(point,2,2) for point in path) or (available and not matrix(row.get("terminal_qv"),2,2)):
                    return False
            elif not all(vector(point,22) for point in path) or (available and not vector(row.get("terminal_x22"),22)):
                return False
            if available and completed and row.get("scored") is not True:
                return False
            if row.get("scored") is True:
                return vector(row.get("actual_endpoint_x22"),22) and set(row.get("terminal_errors_x22",{})) == ({"0","1","8","9"} if p == "D11" else {str(i) for i in range(22)})
            return True
        require(all(outcome_ok(r) for r in records), "11_saved_outcome_shapes_unavailable_reason_and_scored_channels")
        def history_ok(row):
            if row["predictor"] != "Q22" or "initial_x22" not in row:
                return True
            history = row.get("history_inputs")
            return (isinstance(history,list) and len(history) <= row["horizon"]
                    and (not row["available"] or len(history) == row["horizon"] and vector(row.get("terminal_previous_v2"),2))
                    and all(vector(item.get("previous_v2_before"),2) and vector(item.get("current_x22_before"),22) for item in history)
                    and (row["available"] or row.get("reason") == "nonfinite_terminal_error" or
                         isinstance(row.get("failed_mapping"),dict) and isinstance(row.get("failed_transition"),dict)))
        require(all(history_ok(r) for r in records), "12_Q_closed_history_and_failed_mapping_retention")
        groups = metrics["groups"]
        expected_groups = {(s,h,p,c) for s in SEEDS for h in HORIZONS for p in PREDICTORS for c in ((0,1,8,9) if p == "D11" else range(22))}
        group_ids = [(g["seed"],g["horizon"],g["predictor"],g["channel_index"]) for g in groups]
        require(len(set(group_ids)) == len(group_ids) and set(group_ids) <= expected_groups
                and (not completed or set(group_ids) == expected_groups)
                and all(g.get("channel") == STATE[g["channel_index"]] for g in groups), "13_fixed_channel_group_identities")
        population = Counter((r["seed"],r["horizon"],r["predictor"]) for r in records)
        usable = Counter((r["seed"],r["horizon"],r["predictor"]) for r in records if r["available"])
        require(all(g.get("fixed_origin_count") == 101-g["horizon"] and g.get("record_count") == population[g["seed"],g["horizon"],g["predictor"]]
                    and g.get("usable_count") == usable[g["seed"],g["horizon"],g["predictor"]]
                    and g.get("usable_count")+g.get("unavailable_count") == g.get("record_count")
                    and g.get("full_fixed_count") is (g["record_count"] == g["usable_count"] == g["fixed_origin_count"])
                    and (not completed or g.get("record_count") == g["fixed_origin_count"] and g.get("source_active_count") == 100)
                    and g.get("partial_subset_method_ranking") is False for g in groups), "14_saved_group_counts_match_availability_without_metrics")
        gate = metrics.get("development_gate")
        require(type(run.get("development_gate_passed")) is bool and run["development_gate_passed"] == metrics.get("development_gate_passed")
                and (flags(gate) and set(gate["comparisons"]) == {"Q22_vs_K22","Q22_vs_D11"}
                     and gate.get("passed") == run["development_gate_passed"] and type(gate.get("passed")) is bool
                     and all(flags(item) and item.get("candidate_predictor") == "Q22" and item.get("baseline_predictor") == baseline
                             and all(type(item.get(key)) is bool for key in ("passed","evaluated","all_fixed_usable_counts"))
                             for baseline,item in (("K22",gate["comparisons"]["Q22_vs_K22"]),("D11",gate["comparisons"]["Q22_vs_D11"]))) if completed else
                     gate is None and run["development_gate_passed"] is False), "15_saved_gate_and_adoption_boolean_consistency_only")
        cost.update(scientific_metric_recalculations=0, scientific_gate_recalculations=0, model_restorations=0,
                    prediction_records_inspected=len(records), channel_groups_inspected=len(groups),
                    prediction_population_count_entries=len(population), parameter_records_inspected=len(parameters))
        status = "completed"
    except Exception as exc:
        failure = {"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()}
    cost["wall_seconds"],cost["cpu_seconds"] = time.perf_counter()-wall,time.process_time()-cpu
    report = {"status":status,"evidence_consistency_only":True,"expected_source_commit":args.expected_source_commit,
              "inputs":inputs,"checks":checks,"cost":dict(cost),"failure":failure,"scientific_adoption":False,
              "timing_excludes":"final report/stdout serialization and writes"}
    (output/"report.json").write_text(json.dumps(report,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    summary = json.dumps({"status":status,"output":str(output),"cost":dict(cost),"failure":failure and {k:failure[k] for k in ("type","message")}},allow_nan=False)+"\n"
    (output/"stdout.txt").write_text(summary,encoding="utf-8")
    print(summary,end="")
    return 0 if failure is None else 1


if __name__ == "__main__":
    raise SystemExit(main())
