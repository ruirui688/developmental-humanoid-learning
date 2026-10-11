"""R saved-output contract; no model calls, scalar metrics or scientific gate calculation."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import time
import traceback

SEEDS, HORIZONS, PREDICTORS = (0,1,2), (1,2,5,15), ("R22","Q22","K22","D11")
FLAGS = ("scientific_adoption","c4_scientific_validation","c5_scientific_dependency_released")
FILES = ("parameters.json","predictions.jsonl","metrics.json","run.json")
SOURCE_PINS = {
    "scripts/develop_guard_kinematic_native_transition.py": (31640,"07a0135e6cd30e169f780f30eef09472fe857570fa0556f552dcdcbe258c693d"),
    "docs/GUARD_KINEMATIC_NATIVE_TRANSITION_DEVELOPMENT_PROTOCOL.md": (5202,"8f3c86ccfc4626dbf6219e904daa73b208d2cac044a855e050875aecd62e5c45"),
}
Q_ROOT = "results/cpu_validation/2026-10-12_guard_quadratic_native_transition"
Q_INPUT_PINS = {
    f"{Q_ROOT}/manifest.json": {"bytes":2366,"sha256":"327b38412bab68187c4195d12b4d4047dc6bffeffa0c18e0ea73271b870f25b5"},
    f"{Q_ROOT}/raw/manifest.json": {"bytes":646,"sha256":"5cc976083644a544b3395d028163f53d5e32645cdab7c05c2f10510346ea97f5"},
    f"{Q_ROOT}/raw/run.json": {"bytes":14222,"sha256":"98b0bff624b7feca68000b526306d7f58e8ab33bb3644966392a35c7225db6b1"},
    f"{Q_ROOT}/raw/parameters.json": {"bytes":3403882,"sha256":"6184bc6d89e2c0e2e53c9f09ca7f03a33e7990fe6e2a59f298c13617278ce7f4"},
}
Q_SOURCE_PINS = {
    "scripts/develop_guard_quadratic_native_transition.py": "6a8109ed9ba68b61674f9744ac0ea4ffce421ff8b4400abfe7cc081b5c16a147",
    "docs/GUARD_QUADRATIC_NATIVE_TRANSITION_DEVELOPMENT_PROTOCOL.md": "77cb47c42efad889f4d15cf64207b528ab2c7e29908d55d3f16441b0b7a6c5d3",
}
STATE = [f"q{i}-qref{i}" for i in range(8)]+[f"v{i}" for i in range(8)]+[f"gyro_{c}" for c in "xyz"]+[f"accel_{c}/9.81" for c in "xyz"]
PAIRS = [[i,j] for i in range(6) for j in range(i,6)]
FEATURES = STATE+["startG0","startG1","hinge_startG0_.25","hinge_startG1_.25","1","v0-previous_v0","v1-previous_v1"]+[f"z{i}*z{j}" for i,j in PAIRS]
ZERO_COSTS = ("fit_attempts","fit_returns","fit_failures","fit_shared_50x50_22rhs_solve_attempts",
              "fit_shared_50x50_22rhs_solve_returns","fit_shared_50x50_22rhs_solve_failures",
              "fit_scalar_labels_requested","fit_scalar_labels_returned","transition_scalar_coefficients_fitted",
              "Q22_refits","K22_refits","D11_updates","physics_calls","physics_substeps","RLS_updates","MPC_calls")


def vector(value,width):
    return isinstance(value,list) and len(value) == width


def matrix(value,rows,cols):
    return vector(value,rows) and all(vector(row,cols) for row in value)


def flags(value):
    return isinstance(value,dict) and all(value.get(key) is False for key in FLAGS)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw",required=True)
    parser.add_argument("--expected-source-commit",required=True)
    parser.add_argument("--output",required=True)
    args = parser.parse_args()
    raw,output = Path(args.raw).resolve(),Path(args.output).resolve()
    if raw == output or raw.is_relative_to(output) or output.is_relative_to(raw):
        raise ValueError("output_must_be_separate_from_input")
    output.mkdir(parents=True,exist_ok=False)
    wall,cpu = time.perf_counter(),time.process_time()
    cost,inputs,checks = Counter(),{},[]
    status,failure = "failed",None

    def require(condition,label):
        cost["group_check_attempts"] += 1
        checks.append({"group":label,"passed":bool(condition)})
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
        inputs[str(path)] = {"bytes":len(data),"sha256":hashlib.sha256(data).hexdigest()}
        return data

    def parse(data):
        cost["json_parse_attempts"] += 1
        value = json.loads(data,parse_constant=lambda token: (_ for _ in ()).throw(ValueError("invalid_nonfinite_JSON:"+token)))
        cost["json_parse_returns"] += 1
        return value

    try:
        (output/"checker.py").write_bytes(read(Path(__file__).resolve()))
        manifest = parse(read(raw/"manifest.json"))
        completed = manifest.get("status") == "completed"
        expected_files = set(FILES) if completed else set(FILES)|{"failure.json"}
        require(manifest.get("schema_version") == 1 and manifest.get("status") in ("completed","failed")
                and manifest.get("scientific_adoption") is False and set(manifest["files"]) == expected_files,
                "01_manifest_status_and_payload_population")
        blobs = {name:read(raw/name) for name in expected_files}
        require(all(manifest["files"][name] == inputs[str(raw/name)] for name in expected_files),"02_payload_byte_hash_bindings")
        docs = {name:parse(data) for name,data in blobs.items() if name.endswith(".json")}
        records = [parse(line) for line in blobs["predictions.jsonl"].splitlines() if line.strip()]
        parameters,metrics,run = docs["parameters.json"],docs["metrics.json"],docs["run.json"]
        require(run.get("status") == metrics.get("status") == manifest["status"] and run.get("self_check") is False
                and flags(run) and flags(metrics)
                and (run.get("failure") is None if completed else isinstance(run.get("failure"),dict) and docs["failure.json"] == run),
                "03_saved_run_status_flags_and_failed_partial")
        source = run["source"]
        require(len(args.expected_source_commit) == 40 and all(c in "0123456789abcdef" for c in args.expected_source_commit)
                and source.get("commit") == run.get("requested_source_commit") == args.expected_source_commit
                and all((name in source["files"] or not completed) and (name not in source["files"] or source["files"][name] == {"bytes":size,"sha256":sha})
                        for name,(size,sha) in SOURCE_PINS.items())
                and all((name in source["files"] or not completed) and (name not in source["files"] or source["files"][name].get("sha256") == sha)
                        for name,sha in Q_SOURCE_PINS.items())
                and (source.get("clean_committed_bytes_verified") is True if completed else type(source.get("clean_committed_bytes_verified")) is bool),
                "04_exact_R_source_and_frozen_Q_source_identity")
        require(isinstance(run.get("inputs"),dict)
                and all((name in run["inputs"] or not completed) and (name not in run["inputs"] or run["inputs"][name] == expected)
                        for name,expected in Q_INPUT_PINS.items()),"05_recorded_frozen_Q_input_pins_only")
        require(isinstance(parameters,list) and [p["seed"] for p in parameters] == (list(SEEDS) if completed else list(SEEDS[:len(parameters)]))
                and all(p.get("predictor") == "R22" and p.get("available") is True and p.get("refit") is False
                        and p.get("new_scalar_labels_fitted") == 0 and p.get("state_order") == STATE and p.get("feature_order") == FEATURES
                        and p.get("quadratic_public_scales") == [.12,.12,1,1,.5,.5] and p.get("quadratic_pair_order") == PAIRS
                        and vector(p.get("qref8"),8) and matrix(p.get("frozen_Q_weights50x22"),50,22)
                        and p.get("ignored_Q_position_heads") == [0,1] and p.get("half_dt_seconds") == .01
                        and p.get("kinematic_replacement") == "old_q2 + .01 * (old_v2 + next_Q_v2)"
                        and p.get("prediction_prefix_transition_id") == f"seed{p['seed']}_prediction:99"
                        and p.get("training_transition_ids") == [f"seed{p['seed']}_calibration_sparse:{i}" for i in range(100,500)]
                        and all(p.get(f"{name}_parameter_fingerprint") == run[f"{name}_fingerprints_before"][str(p["seed"])]
                                for name in ("Q22","K22","D11")) for p in parameters),
                "06_R_parameter_dimensions_mapping_provenance_and_no_new_fit")
        paid = run["cost"]
        inherited = run.get("frozen_Q_original_cost")
        require(isinstance(paid,dict) and all(paid.get(key) == 0 for key in ZERO_COSTS)
                and (not completed or paid.get("Q22_restoration_attempts") == paid.get("Q22_restoration_returns") == 3
                     and paid.get("Q22_restoration_failures",0) == 0 and paid.get("Q22_saved_weight_scalars_validated") == 3300
                     and isinstance(inherited,dict) and inherited.get("fit_scalar_labels_requested") == inherited.get("fit_scalar_labels_returned") == 26400
                     and inherited.get("fit_shared_50x50_22rhs_solve_attempts") == inherited.get("fit_shared_50x50_22rhs_solve_returns") == 3
                     and inherited.get("transition_scalar_coefficients_fitted") == 3300),
                "07_saved_zero_new_learning_interaction_and_inherited_Q_fit_cost")
        require(not completed or (run.get("source_active_counts") == {f"seed{s}_prediction":100 for s in SEEDS}
                and all(run.get(f"{name}_fingerprints_before") == run.get(f"{name}_fingerprints_after")
                        and set(run[f"{name}_fingerprints_before"]) == {str(s) for s in SEEDS} for name in ("Q22","K22","D11"))),
                "08_saved_source_population_and_unchanged_Q_K_D_fingerprints")
        expected_records = {(s,h,p,o) for s in SEEDS for h in HORIZONS for p in PREDICTORS for o in range(101-h)}
        identities = [(r["seed"],r["horizon"],r["predictor"],r["origin"]) for r in records]
        require(len(set(identities)) == len(identities) and set(identities) <= expected_records
                and (not completed or set(identities) == expected_records),"09_fixed_prediction_record_identities")
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
        require(all(context_ok(r) for r in records),"10_native_context_dimensions_and_same_trial_request_history")
        def outcome_ok(row):
            h,p,available = row["horizon"],row["predictor"],row["available"]
            if not available and not isinstance(row.get("reason"),str):
                return False
            if "initial_x22" not in row:
                return True
            path = row.get("predicted_path_qv" if p == "D11" else "predicted_path_x22")
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
        require(all(outcome_ok(r) for r in records),"11_saved_outcome_dimensions_unavailable_reason_and_scored_channels")
        def one_step_ok(saved):
            if not isinstance(saved,dict) or type(saved.get("available")) is not bool:
                return False
            path = saved.get("predicted_path_x22")
            if not isinstance(path,list) or len(path) > 1 or not all(vector(point,22) for point in path):
                return False
            if saved["available"]:
                return len(path) == 1 and vector(saved.get("terminal_x22"),22) and vector(saved.get("terminal_previous_v2"),2)
            return isinstance(saved.get("reason"),str) and isinstance(saved.get("failed_mapping"),dict) and isinstance(saved.get("failed_transition"),dict)
        def history_ok(row):
            if row["predictor"] not in ("R22","Q22") or "initial_x22" not in row:
                return True
            history = row.get("history_inputs")
            if not isinstance(history,list) or len(history) > row["horizon"] or (row["available"] and len(history) != row["horizon"]):
                return False
            if row["available"] and not vector(row.get("terminal_previous_v2"),2):
                return False
            if row["predictor"] == "R22" and row["available"] and row.get("ignored_Q_position_heads") != [0,1]:
                return False
            for item in history:
                if not vector(item.get("current_x22_before"),22) or not vector(item.get("previous_v2_before"),2):
                    return False
                if row["predictor"] == "R22":
                    if not isinstance(item.get("paid_Q_step_cost"),dict) or ("frozen_Q_one_step" in item and not one_step_ok(item["frozen_Q_one_step"])):
                        return False
                    if row["available"] and ("frozen_Q_one_step" not in item or item["frozen_Q_one_step"]["available"] is not True
                            or not vector(item.get("ignored_Q_q2"),2) or not vector(item.get("replacement_q2"),2)):
                        return False
                    if any(name in item and not vector(item[name],2) for name in ("ignored_Q_q2","replacement_q2")):
                        return False
            return True
        require(all(history_ok(r) for r in records),"12_R_Q_history_nested_step_dimensions_and_paid_partial_retention")
        groups = metrics["groups"]
        expected_groups = {(s,h,p,c) for s in SEEDS for h in HORIZONS for p in PREDICTORS for c in ((0,1,8,9) if p == "D11" else range(22))}
        group_ids = [(g["seed"],g["horizon"],g["predictor"],g["channel_index"]) for g in groups]
        require(len(set(group_ids)) == len(group_ids) and set(group_ids) <= expected_groups
                and (not completed or set(group_ids) == expected_groups)
                and all(g.get("channel") == STATE[g["channel_index"]] for g in groups),"13_fixed_channel_group_identities")
        population = Counter((r["seed"],r["horizon"],r["predictor"]) for r in records)
        usable = Counter((r["seed"],r["horizon"],r["predictor"]) for r in records if r["available"])
        require(all(g.get("fixed_origin_count") == 101-g["horizon"] and g.get("record_count") == population[g["seed"],g["horizon"],g["predictor"]]
                    and g.get("usable_count") == usable[g["seed"],g["horizon"],g["predictor"]]
                    and g.get("usable_count")+g.get("unavailable_count") == g.get("record_count")
                    and g.get("full_fixed_count") is (g["record_count"] == g["usable_count"] == g["fixed_origin_count"])
                    and (not completed or g.get("record_count") == g["fixed_origin_count"] and g.get("source_active_count") == 100)
                    and g.get("partial_subset_method_ranking") is False for g in groups),"14_saved_group_counts_match_availability_without_metrics")
        gate = metrics.get("development_gate")
        require(type(run.get("development_gate_passed")) is bool and run["development_gate_passed"] == metrics.get("development_gate_passed")
                and (flags(gate) and gate.get("Q22_descriptive_only") is True and set(gate["comparisons"]) == {"R22_vs_K22","R22_vs_D11"}
                     and gate.get("passed") == run["development_gate_passed"] and type(gate.get("passed")) is bool
                     and all(flags(item) and item.get("candidate_predictor") == "R22" and item.get("baseline_predictor") == baseline
                             and all(type(item.get(key)) is bool for key in ("passed","evaluated","all_fixed_usable_counts"))
                             for baseline,item in (("K22",gate["comparisons"]["R22_vs_K22"]),("D11",gate["comparisons"]["R22_vs_D11"]))) if completed else
                     gate is None and run["development_gate_passed"] is False),"15_saved_gate_adoption_and_Q_descriptive_boolean_consistency_only")
        cost.update(scientific_metric_recalculations=0,scientific_gate_recalculations=0,model_restorations=0,
                    prediction_records_inspected=len(records),channel_groups_inspected=len(groups),
                    prediction_population_count_entries=len(population),parameter_records_inspected=len(parameters))
        status = "completed"
    except Exception as exc:
        failure = {"type":type(exc).__name__,"message":str(exc),"traceback":traceback.format_exc()}
    cost["wall_seconds"],cost["cpu_seconds"] = time.perf_counter()-wall,time.process_time()-cpu
    report = {"status":status,"evidence_consistency_only":True,"expected_source_commit":args.expected_source_commit,
              "inputs":inputs,"checks":checks,"cost":dict(cost),"failure":failure,"scientific_adoption":False,
              "timing_excludes":"final report/stdout serialization and writes"}
    (output/"report.json").write_text(json.dumps(report,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    summary = json.dumps({"status":status,"output":str(output),"cost":dict(cost),"failure":failure and {key:failure[key] for key in ("type","message")}},allow_nan=False)+"\n"
    (output/"stdout.txt").write_text(summary,encoding="utf-8")
    print(summary,end="")
    return 0 if failure is None else 1


if __name__ == "__main__":
    raise SystemExit(main())
