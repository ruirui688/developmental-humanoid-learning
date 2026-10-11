"""One P saved-output contract check; no models or scientific recomputation."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import time
import traceback

SEEDS = (0, 1, 2)
HORIZONS = (1, 2, 5, 15)
PREDICTORS = ("P22", "K22", "D11")
FLAGS = ("scientific_adoption", "c4_scientific_validation", "c5_scientific_dependency_released")
FILES = ("parameters.json", "predictions.jsonl", "metrics.json", "run.json")
SOURCE_PINS = {
    "scripts/develop_guard_request_memory_transition.py": (30497, "cae9a9fdd4dd2c1563f2163e40bd8edcb8906ce2743e5c90960d5fa20d50491c"),
    "docs/GUARD_REQUEST_MEMORY_TRANSITION_DEVELOPMENT_PROTOCOL.md": (6203, "cbb04927f77fc43cc0539b7acc23c4a9e9366866e867d1963cd2f86cb658375a"),
}


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
    cost, inputs = Counter(), {}
    status, failure = "failed", None

    def require(condition, label):
        cost["contract_check_attempts"] += 1
        if not condition:
            cost["contract_check_failures"] += 1
            raise ValueError(label)
        cost["contract_check_returns"] += 1

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
        value = json.loads(data, parse_constant=lambda token: (_ for _ in ()).throw(ValueError("nonfinite_JSON:"+token)))
        cost["json_parse_returns"] += 1
        return value

    def vector(value, width, label):
        require(isinstance(value, list) and len(value) == width, label)

    def matrix(value, rows, cols, label):
        vector(value, rows, label+":rows")
        for row in value:
            vector(row, cols, label+":columns")
        cost["structural_matrix_rows_checked"] += rows

    def flags(value, label):
        for name in FLAGS:
            require(value.get(name) is False, label+":"+name)

    try:
        own = read(Path(__file__).resolve())
        (output/"checker.py").write_bytes(own)
        manifest = parse(read(raw/"manifest.json"))
        require(manifest.get("status") == "completed" and manifest.get("scientific_adoption") is False, "manifest_status")
        require(set(manifest["files"]) == set(FILES), "manifest_payload_set")
        blobs = {}
        for name in FILES:
            blobs[name] = read(raw/name)
            recorded = manifest["files"][name]
            observed = inputs[str(raw/name)]
            require(recorded.get("bytes") == observed["bytes"] and recorded.get("sha256") == observed["sha256"], "manifest_hash:"+name)
        parameters, metrics, run = (parse(blobs[name]) for name in ("parameters.json", "metrics.json", "run.json"))
        require(run.get("status") == metrics.get("status") == "completed" and run.get("self_check") is False and run.get("failure") is None, "formal_completed_status")
        flags(run, "run"); flags(metrics, "metrics")
        require(run["source"]["commit"] == run["requested_source_commit"] == args.expected_source_commit, "expected_source_commit")
        require(run["source"]["clean_committed_bytes_verified"] is True, "clean_source_claim")
        for name, (size, digest) in SOURCE_PINS.items():
            saved = run["source"]["files"][name]
            require(saved.get("bytes") == size and saved.get("sha256") == digest, "frozen_source_pin:"+name)
        for baseline in ("K22", "D11"):
            before, after = run[baseline+"_fingerprints_before"], run[baseline+"_fingerprints_after"]
            require(set(before) == {str(s) for s in SEEDS} and before == after, "baseline_fingerprints:"+baseline)
        expected_costs = {
            "fit_attempts": 3, "fit_returns": 3, "fit_failures": 0,
            "fit_shared_31x31_22rhs_solve_attempts": 3,
            "fit_shared_31x31_22rhs_solve_returns": 3,
            "fit_shared_31x31_22rhs_solve_failures": 0,
            "fit_scalar_labels_requested": 26400, "fit_scalar_labels_returned": 26400,
            "transition_scalar_coefficients_fitted": 2046, "transition_heads_published": 66,
            "physics_calls": 0, "physics_substeps": 0, "RLS_updates": 0,
            "MPC_calls": 0, "K22_refits": 0, "D11_updates": 0,
        }
        for name, expected in expected_costs.items():
            require(run["cost"].get(name) == expected, "declared_cost:"+name)
        require(isinstance(parameters, list) and len(parameters) == 3, "three_parameter_records")
        seen_seeds = set()
        for record in parameters:
            seed = record["seed"]
            require(type(seed) is int and seed in SEEDS and seed not in seen_seeds, "unique_parameter_seed")
            seen_seeds.add(seed)
            require(record.get("predictor") == "P22" and record.get("available") is True and record.get("fixed_lambda") == .01, "P_parameter_identity")
            require(record.get("training_fixed_count") == record.get("training_usable_count") == 400, "fixed_complete_C400")
            require(record["training_transition_ids"] == [f"seed{seed}_calibration_sparse:{i}" for i in range(100, 500)], "C400_row_IDs")
            require(record["past_request_source_transition_ids"] == [f"seed{seed}_calibration_sparse:{i}" for i in range(99, 499)], "C400_past_request_IDs")
            matrix(record["past_requests400x2"], 400, 2, "C400_request_history")
            cost["training_history_entries_checked"] += 400
            vector(record["state_order"], 22, "state_order22")
            vector(record["feature_order"], 31, "feature_order31")
            require(record["feature_order"][-2:] == ["past_requested0_nm", "past_requested1_nm"] and record["past_request_extra_clip"] is None, "raw_request_columns")
            matrix(record["past_request_prior_coefficients2x22"], 2, 22, "past_request_prior_shape")
            for baseline in ("K22", "D11"):
                require(record[baseline+"_parameter_fingerprint"] == run[baseline+"_fingerprints_before"][str(seed)], "record_baseline_fingerprint:"+baseline)
            fit = record["fit"]
            require(fit["status"] == "returned", "fit_returned")
            for name, rows, cols in (("phi400x31", 400, 31), ("delta_labels400x22", 400, 22), ("gram31x31", 31, 31), ("cross31x22", 31, 22), ("ridge_normal31x31", 31, 31), ("weights31x22", 31, 22)):
                matrix(fit[name], rows, cols, name)
            require(run["source_active_counts"][f"seed{seed}_calibration_sparse"] == 400 and run["source_active_counts"][f"seed{seed}_prediction"] == 100, "source_active_counts")
        expected_records = {(s, h, o, p) for s in SEEDS for h in HORIZONS for o in range(101-h) for p in PREDICTORS}
        seen = set()
        for line in blobs["predictions.jsonl"].splitlines():
            cost["prediction_record_attempts"] += 1
            row = parse(line)
            key = (row["seed"], row["horizon"], row["origin"], row["predictor"])
            require(key in expected_records and key not in seen, "fixed_prediction_identity")
            seen.add(key)
            seed, horizon, origin, predictor = key
            require(row.get("available") is True and row.get("scored") is True and row.get("offline_saved_future_requests") is True and row.get("source_stopped_at_endpoint") is False, "complete_prediction_record")
            require(row["trial_id"] == f"seed{seed}_prediction" and row["past_request_transition_id"] == f"seed{seed}_prediction:{99+origin}", "prediction_past_ID")
            vector(row["initial_x22"], 22, "initial_x22")
            vector(row["actual_endpoint_x22"], 22, "actual_endpoint_x22")
            vector(row["previous_v2"], 2, "previous_v2")
            vector(row["past_requested2"], 2, "past_requested2")
            matrix(row["requested_sequence8"], horizon, 8, "requested_sequence8")
            if predictor == "D11":
                vector(row["predicted_path_qv"], horizon, "D_path_horizon")
                for point in [*row["predicted_path_qv"], row["terminal_qv"]]:
                    matrix(point, 2, 2, "D_qv_shape")
                require(set(row["terminal_errors_x22"]) == {"0", "1", "8", "9"}, "D_error_channels")
            else:
                matrix(row["predicted_path_x22"], horizon, 22, "native_path22")
                vector(row["terminal_x22"], 22, "native_terminal22")
                require(set(row["terminal_errors_x22"]) == {str(i) for i in range(22)}, "native_error22")
                if predictor == "P22":
                    vector(row["history_inputs"], horizon, "P_history_horizon")
                    for point in row["history_inputs"]:
                        for name in ("past_request2_before", "previous_v2_before", "known_request2_this_step"):
                            vector(point[name], 2, "P_history2:"+name)
                    vector(row["terminal_past_request2"], 2, "P_terminal_request2")
                    vector(row["terminal_previous_v2"], 2, "P_terminal_previous_v2")
            cost["prediction_record_returns"] += 1
        require(seen == expected_records and len(seen) == 3429, "all_3429_fixed_records")
        groups = metrics["groups"]
        require(isinstance(groups, list) and len(groups) == 576, "all_576_groups")
        expected_groups = {(s, h, p, c) for s in SEEDS for h in HORIZONS for p in PREDICTORS for c in ((0, 1, 8, 9) if p == "D11" else range(22))}
        seen_groups = set()
        for group in groups:
            key = (group["seed"], group["horizon"], group["predictor"], group["channel_index"])
            require(key in expected_groups and key not in seen_groups, "unique_group_identity")
            seen_groups.add(key)
            count = 101-group["horizon"]
            require(group["fixed_origin_count"] == group["record_count"] == group["usable_count"] == count and group["unavailable_count"] == 0 and group["source_active_count"] == 100 and group["full_fixed_count"] is True and group["partial_subset_method_ranking"] is False, "complete_fixed_group")
        require(seen_groups == expected_groups, "fixed_group_set")
        gate = metrics["development_gate"]
        flags(gate, "development_gate")
        require(set(gate["comparisons"]) == {"P22_vs_K22", "P22_vs_D11"}, "two_saved_gate_records")
        require(type(gate["passed"]) is bool and gate["passed"] == metrics["development_gate_passed"] == run["development_gate_passed"], "saved_gate_boolean_consistency_only")
        cost["scientific_metric_recalculations"] = 0
        cost["scientific_gate_recalculations"] = 0
        cost["model_restorations"] = 0
        status = "completed"
    except Exception as exc:
        failure = {"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()}
    cost["wall_seconds"], cost["cpu_seconds"] = time.perf_counter()-wall, time.process_time()-cpu
    report = {"status": status, "evidence_consistency_only": True, "expected_source_commit": args.expected_source_commit, "inputs": inputs, "cost": dict(cost), "failure": failure, "scientific_adoption": False, "timing_excludes": "final report/stdout serialization and writes"}
    report_bytes = (json.dumps(report, indent=2, allow_nan=False)+"\n").encode()
    (output/"report.json").write_bytes(report_bytes)
    summary = json.dumps({"status": status, "output": str(output), "cost": dict(cost), "failure": failure and {k: failure[k] for k in ("type", "message")}}, allow_nan=False)+"\n"
    (output/"stdout.txt").write_bytes(summary.encode())
    print(summary, end="")
    return 0 if failure is None else 1


if __name__ == "__main__":
    raise SystemExit(main())
