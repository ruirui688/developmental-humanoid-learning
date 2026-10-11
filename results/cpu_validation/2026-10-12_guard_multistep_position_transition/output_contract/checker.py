"""S thin saved-output contract; no scientific imports, restoration, metrics or gate recalculation."""
import argparse
from collections import Counter
import hashlib
import math
import re
import json
from pathlib import Path
import time
import traceback

SEEDS, HORIZONS, PREDICTORS = (0,1,2), (1,2,5,15), ("S22","Q22","K22","D11")
FLAGS = ("scientific_adoption","c4_scientific_validation","c5_scientific_dependency_released")
FILES = ("parameters.json","predictions.jsonl","metrics.json","run.json")
SOURCE_PINS = {
    "scripts/develop_guard_multistep_position_transition.py": (50910,"22097d00bbb884e29b9d0e6cd060b53e0448beb72321685c11e7942762acfe7e"),
    "docs/GUARD_MULTISTEP_POSITION_TRANSITION_DEVELOPMENT_PROTOCOL.md": (9226,"ce5e8f0d3d6b5580406dd73a5b6f8a9928f56c5b13ad4056d1d05145659d944d"),
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
ZERO_COSTS = ("fit_shared_50x50_22rhs_solve_attempts","fit_shared_50x50_22rhs_solve_returns",
    "fit_scalar_labels_requested","fit_scalar_labels_returned","transition_scalar_coefficients_fitted",
    "Q22_refits","K22_refits","D11_updates","physics_calls","physics_substeps","RLS_updates","MPC_calls")
ORIGINS = {1:400,2:399,5:396,15:386}
OPTIONS = {"maxiter":30,"maxfun":60,"maxls":10,"ftol":1e-12,"gtol":1e-8}
LOSS = "mean_h(mean_origins_and_two_axes(((q_pred_end-q_actual_end)/.12)^2))+.01*sum((U-UQ)^2)"


def vector(value,width):
    return isinstance(value,list) and len(value) == width


def matrix(value,rows,cols):
    return vector(value,rows) and all(vector(row,cols) for row in value)


def flags(value):
    return isinstance(value,dict) and all(value.get(key) is False for key in FLAGS)


def finite(value):
    return isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value)


def finite_matrix(value,rows,cols):
    return matrix(value,rows,cols) and all(finite(x) for row in value for x in row)


def training_ok(p):
    seed=p["seed"]; ids=[f"seed{seed}_calibration_sparse:{i}" for i in range(100,500)]
    if "training_trial_id" not in p:
        return p["available"] is False and not p.get("fit")
    if (p["training_trial_id"]!=f"seed{seed}_calibration_sparse" or p.get("qref_source_transition_id")!=f"seed{seed}_calibration_sparse:99"
            or p.get("training_transition_ids")!=ids or p.get("unique_terminal_q_label_transition_ids")!=ids
            or p.get("training_fixed_count")!=400 or p.get("training_usable_count") not in (0,400)):
        return False
    labels=p.get("unique_terminal_q_labels400x2")
    if not isinstance(labels,list) or len(labels)>400 or not all(vector(row,2) for row in labels):
        return False
    windows=p.get("training_windows",{})
    if not isinstance(windows,dict) or not set(windows)<={str(h) for h in HORIZONS}:
        return False
    full=p.get("training_usable_count")==400
    if full and (len(labels)!=400 or set(windows)!={str(h) for h in HORIZONS}
            or [p.get(k) for k in ("unique_terminal_q_label_scalars","objective_fixed_windows","objective_fixed_label_uses","objective_fixed_transitions")]!=[800,1581,3162,8968]):
        return False
    for hs,batch in windows.items():
        h=int(hs); rows=batch.get("windows")
        if not isinstance(rows,list) or len(rows)>ORIGINS[h] or batch.get("fixed_origin_count")!=ORIGINS[h]:
            return False
        n=len(rows)
        if (not matrix(batch.get("initial_x22"),n,22) or not matrix(batch.get("previous_v2"),n,2)
                or not matrix(batch.get("terminal_label_qrel2"),n,2)
                or not vector(batch.get("known_requests8"),n)
                or not all(matrix(commands,h,8) for commands in batch["known_requests8"])):
            return False
        if full and (n!=ORIGINS[h] or batch.get("usable_origin_count")!=n):
            return False
        for origin,row in enumerate(rows):
            active=ids[origin:origin+h]
            if (row.get("origin")!=origin or row.get("requested_transition_ids")!=active
                    or row.get("history_transition_ids")!=[f"seed{seed}_calibration_sparse:{98+origin}",f"seed{seed}_calibration_sparse:{99+origin}"]
                    or row.get("terminal_label_transition_id")!=active[-1] or type(row.get("source_stopped_at_endpoint")) is not bool
                    or origin+h-1>=len(labels) or batch["terminal_label_qrel2"][origin]!=labels[origin+h-1]):
                return False
    return True


def fit_budget_ok(p):
    fit=p.get("fit",{})
    if not fit:
        return p["available"] is False
    budget=fit.get("budget")
    if (not isinstance(budget,dict) or budget.get("hard_objective_call_limit")!=100 or budget.get("time_boundary_seconds")!=120.
            or budget.get("timer_start")!="before_initial_objective"
            or fit.get("status") not in ("returned","budget_exhausted","failed")
            or any(type(fit.get(k)) is not bool for k in ("budget_exhausted","optimizer_failed","fit_failed","optimizer_invocation_attempted","optimizer_invocation_returned"))
            or fit.get("optimizer_invocation_returned") and not fit.get("optimizer_invocation_attempted")):
        return False
    events=fit.get("objective_events"); calls=fit.get("objective_calls_started")
    if type(calls) is not int or not 0<=calls<=100 or not isinstance(events,list) or len(events)>calls:
        return False
    if fit["status"]!="failed" and len(events)!=calls:
        return False
    for index,event in enumerate(events,1):
        if (event.get("objective_id")!=index or event.get("status") not in ("attempted","returned","failed")
                or not matrix(event.get("trial_U50x2"),50,2)):
            return False
        if event["status"]=="returned":
            if (event.get("finite") is not True or not finite(event.get("loss"))
                    or not finite_matrix(event.get("gradient50x2"),50,2)
                    or not finite(event.get("gradient_l2_norm")) or not finite(event.get("gradient_inf_norm"))
                    or not finite(event.get("exit_elapsed_seconds"))):
                return False
    if fit.get("objective_partial_count")!=sum(event.get("status")!="returned" for event in events):
        return False
    if not finite(fit.get("elapsed_wall_seconds")) or not finite(fit.get("overrun_seconds")) or fit["overrun_seconds"]<0.:
        return False
    result=fit.get("optimizer_result")
    if result is not None and (not isinstance(result,dict) or type(result.get("success")) is not bool
            or result.get("result_x_selected") is not False or result.get("result_fun_selected") is not False
            or any(type(result.get(k)) is not int or result[k]<0 for k in ("nit","nfev","njev"))
            or result.get("nit",31)>30):
        return False
    if fit["optimizer_failed"] and not fit["optimizer_invocation_attempted"]:
        return False
    return True


def accepted_ok(p,checkpoint_docs,manifest):
    fit=p.get("fit",{})
    if not fit:
        return p["available"] is False
    accepted=fit.get("accepted_checkpoints")
    files=fit.get("checkpoint_files")
    if not isinstance(accepted,list) or not isinstance(files,dict):
        return False
    iterations=[item.get("iteration") for item in accepted]
    if iterations!=list(range(len(accepted))) or len(accepted)>31 or fit.get("accepted_updates")!=max(0,len(accepted)-1):
        return False
    events={event["objective_id"]:event for event in fit["objective_events"]}
    all_checkpoints=[*accepted,*fit.get("unregistered_checkpoint_overruns",[])]
    if set(files)!={f"fit_checkpoints/seed{p['seed']}/iteration{item['iteration']:02d}.json" for item in all_checkpoints}:
        return False
    for item in all_checkpoints:
        rel=f"fit_checkpoints/seed{p['seed']}/iteration{item['iteration']:02d}.json"
        event=events.get(item.get("objective_id"))
        if (files[rel]!=manifest["files"].get(rel) or checkpoint_docs.get(rel)!=item
                or not finite_matrix(item.get("U50x2"),50,2) or not isinstance(event,dict)
                or event.get("status")!="returned" or event.get("outside_time_boundary")
                or item["U50x2"]!=event["trial_U50x2"]
                or item.get("loss")!=event.get("loss") or item.get("gradient_l2_norm")!=event.get("gradient_l2_norm")):
            return False
    if any(not finite(item.get("elapsed_seconds")) or item["elapsed_seconds"]>=120. for item in accepted):
        return False
    if accepted and (accepted[0]["U50x2"]!=fit.get("initial_UQ50x2")
            or accepted[0]["U50x2"]!=[row[:2] for row in p["frozen_Q_weights50x22"]]):
        return False
    if fit["fit_failed"]:
        return (p["available"] is False and fit.get("selected_snapshot") is None
                and "selected_weights50x22" not in p and fit.get("status")=="failed"
                and fit.get("accepted_snapshot_retained_as_evidence_only")==(
                    accepted[-1]["U50x2"] if accepted else None))
    if (not accepted or p["available"] is not True or fit.get("selected_snapshot")!=accepted[-1]["U50x2"]
            or fit.get("selection")!="last_finite_callback_or_validated_iteration0_only"
            or not matrix(p.get("selected_weights50x22"),50,22)
            or p.get("frozen_twenty_head_coefficients_equal") is not True):
        return False
    return all(row[:2]==chosen and row[2:]==frozen[2:] for row,chosen,frozen in zip(
        p["selected_weights50x22"],fit["selected_snapshot"],p["frozen_Q_weights50x22"]))


def context_ok(row):
    s,h,o=row["seed"],row["horizon"],row["origin"]
    if row.get("trial_id")!=f"seed{s}_prediction" or row.get("offline_saved_future_requests") is not True or type(row.get("available")) is not bool:
        return False
    if "initial_x22" not in row:
        return row["available"] is False and isinstance(row.get("reason"),str) and row["reason"].startswith("window_unavailable:")
    return (vector(row["initial_x22"],22) and vector(row.get("previous_v2"),2) and matrix(row.get("requested_sequence8"),h,8)
        and row.get("history_transition_ids")==[f"seed{s}_prediction:{98+o}",f"seed{s}_prediction:{99+o}"]
        and row.get("requested_transition_ids")==[f"seed{s}_prediction:{100+o+i}" for i in range(h)]
        and type(row.get("source_stopped_at_endpoint")) is bool)


def outcome_ok(row,params):
    h,p,available=row["horizon"],row["predictor"],row["available"]
    if not available and not isinstance(row.get("reason"),str):
        return False
    if "initial_x22" not in row:
        return True
    if p=="S22" and params.get(row["seed"],{}).get("available") is False:
        return not available and row.get("scored") is False and row.get("reason")=="fit_failed_no_S_candidate"
    if row.get("reason")=="fit_failed_no_S_candidate":
        return p=="S22" and not available and row.get("scored") is False and params.get(row["seed"],{}).get("available") is False
    path=row.get("predicted_path_qv" if p=="D11" else "predicted_path_x22")
    if not isinstance(path,list) or len(path)>h or available and len(path)!=h:
        return False
    if p=="D11":
        if not all(matrix(point,2,2) for point in path) or available and not matrix(row.get("terminal_qv"),2,2):
            return False
    elif not all(vector(point,22) for point in path) or available and not vector(row.get("terminal_x22"),22):
        return False
    if p in ("S22","Q22"):
        history=row.get("history_inputs")
        if (not isinstance(history,list) or len(history)>h or available and len(history)!=h
                or not all(vector(item.get("current_x22_before"),22) and vector(item.get("previous_v2_before"),2) for item in history)
                or available and not vector(row.get("terminal_previous_v2"),2)):
            return False
    if row.get("scored") is True:
        return vector(row.get("actual_endpoint_x22"),22) and set(row.get("terminal_errors_x22",{}))==({"0","1","8","9"} if p=="D11" else {str(i) for i in range(22)})
    return not available


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw",required=True)
    parser.add_argument("--expected-source-commit",required=True)
    parser.add_argument("--output",required=True)
    args=parser.parse_args()
    raw,output=Path(args.raw).resolve(),Path(args.output).resolve()
    if raw==output or raw.is_relative_to(output) or output.is_relative_to(raw):
        raise ValueError("output_must_be_separate_from_input")
    output.mkdir(parents=True,exist_ok=False)
    wall,cpu=time.perf_counter(),time.process_time()
    cost,inputs,checks=Counter(),{},[]
    status,failure="failed",None
    def require(condition,label):
        cost["group_check_attempts"]+=1
        checks.append({"group":label,"passed":bool(condition)})
        if not condition:
            cost["group_check_failures"]+=1
            raise ValueError(label)
        cost["group_check_returns"]+=1
    def read(path):
        cost["file_read_attempts"]+=1
        data=path.read_bytes()
        cost["file_read_returns"]+=1
        cost["raw_bytes_read"]+=len(data);cost["sha256_input_bytes"]+=len(data)
        inputs[str(path)]={"bytes":len(data),"sha256":hashlib.sha256(data).hexdigest()}
        return data
    def parse(data):
        cost["json_parse_attempts"]+=1
        value=json.loads(data,parse_constant=lambda token:(_ for _ in ()).throw(ValueError("invalid_nonfinite_JSON:"+token)))
        cost["json_parse_returns"]+=1
        return value
    try:
        (output/"checker.py").write_bytes(read(Path(__file__).resolve()))
        manifest=parse(read(raw/"manifest.json"))
        completed=manifest.get("status")=="completed"
        base=set(FILES)|({"failure.json"} if manifest.get("status")=="failed" else set())
        names=set(manifest.get("files",{}))
        extras=names-base
        require(manifest.get("schema_version")==1 and manifest.get("status") in ("completed","failed")
            and manifest.get("scientific_adoption") is False and base<=names
            and all(re.fullmatch(r"fit_checkpoints/seed[0-2]/iteration[0-9]{2}\.json",name) for name in extras),
            "01_manifest_status_base_payload_and_checkpoint_paths")
        for name in sorted(names):
            if not (raw/name).resolve().is_relative_to(raw):
                raise ValueError("manifest_path_escapes_input")
        blobs={name:read(raw/name) for name in sorted(names)}
        require(all(manifest["files"][name]==inputs[str(raw/name)] for name in names),"02_payload_and_checkpoint_byte_hash_bindings")
        docs={name:parse(data) for name,data in blobs.items() if name.endswith(".json")}
        records=[parse(line) for line in blobs["predictions.jsonl"].splitlines() if line.strip()]
        parameters,metrics,run=docs["parameters.json"],docs["metrics.json"],docs["run.json"]
        evaluation_complete=completed or isinstance(run.get("failure"),dict) and run["failure"].get("type")=="SFitFailed"
        checkpoint_docs={name:docs[name] for name in extras}
        require(run.get("status")==metrics.get("status")==manifest["status"] and run.get("self_check") is False
            and flags(run) and flags(metrics)
            and (run.get("failure") is None if completed else isinstance(run.get("failure"),dict) and docs["failure.json"]==run),
            "03_saved_run_flags_and_failed_partial_status")
        source=run["source"]
        require(len(args.expected_source_commit)==40 and all(c in "0123456789abcdef" for c in args.expected_source_commit)
            and source.get("commit")==run.get("requested_source_commit")==args.expected_source_commit
            and all((name in source["files"] or not completed) and (name not in source["files"] or source["files"][name]=={"bytes":size,"sha256":sha}) for name,(size,sha) in SOURCE_PINS.items())
            and all((name in source["files"] or not completed) and (name not in source["files"] or source["files"][name].get("sha256")==sha) for name,sha in Q_SOURCE_PINS.items())
            and (source.get("clean_committed_bytes_verified") is True if completed else type(source.get("clean_committed_bytes_verified")) is bool),
            "04_recorded_S_and_frozen_Q_source_identity")
        require(isinstance(run.get("inputs"),dict) and all((name in run["inputs"] or not completed)
            and (name not in run["inputs"] or run["inputs"][name]==expected) for name,expected in Q_INPUT_PINS.items()),
            "05_recorded_frozen_Q_input_pins_only")
        require(isinstance(parameters,list) and len(parameters)<=3 and [p.get("seed") for p in parameters]==list(SEEDS[:len(parameters)])
            and (not evaluation_complete or len(parameters)==3)
            and all(p.get("predictor")=="S22" and type(p.get("available")) is bool
                and p.get("state_order")==STATE and p.get("feature_order")==FEATURES
                and p.get("quadratic_public_scales")==[.12,.12,1.,1.,.5,.5] and p.get("quadratic_pair_order")==PAIRS
                and vector(p.get("qref8"),8) and matrix(p.get("frozen_Q_weights50x22"),50,22)
                and p.get("optimized_heads")==[0,1] and p.get("frozen_head_indices")==list(range(2,22))
                and p.get("optimized_parameter_count")==100 and p.get("frozen_parameter_count")==1000
                and p.get("prediction_prefix_transition_id")==f"seed{p['seed']}_prediction:99"
                and all(p.get(f"{name}_parameter_fingerprint")==run[f"{name}_fingerprints_before"][str(p["seed"])] for name in ("Q22","K22","D11")) for p in parameters),
            "06_parameter_dimensions_frozen_heads_and_saved_provenance")
        require(all(training_ok(p) for p in parameters),"07_fixed_training_population_dimensions_terminal_label_bindings_and_partial")
        runtime=run.get("runtime",{})
        runtime_ok=(runtime.get("torch")=="2.2.2+cpu" and runtime.get("torch_distribution")=="2.2.2"
            and runtime.get("torch_git_version")=="39901f229520a5256505ec24782f716ee7ddc843"
            and runtime.get("scipy_git_revision")=="e29dcb65a2040f04819b426a04b60d44a8f69c04"
            and runtime.get("scipy")=="1.15.3" and runtime.get("numpy")=="1.26.4" and runtime.get("torch_cuda") is None
            and runtime.get("device")=="cpu" and runtime.get("dtype")=="float64" and runtime.get("torch_num_threads")==1)
        require((runtime_ok or not completed and "torch" not in runtime)
            and all(p.get("loss_spec")==LOSS and p.get("optimizer")=={"method":"L-BFGS-B","jac":True,"bounds":None,"options":OPTIONS}
                and p.get("hard_objective_call_limit")==100 and p.get("time_boundary_seconds")==120. and fit_budget_ok(p) for p in parameters),
            "08_saved_fixed_recipe_runtime_objective_budget_and_partial_status")
        union={name:ident for p in parameters for name,ident in p.get("fit",{}).get("checkpoint_files",{}).items()}
        require(set(union)==extras and all(accepted_ok(p,checkpoint_docs,manifest) for p in parameters),
            "09_saved_accepted_checkpoint_bindings_last_selection_and_failed_isolation")
        paid=run["cost"]; inherited=run.get("frozen_Q_original_cost")
        fits=[p["fit"] for p in parameters if p.get("fit")]
        counts=run.get("source_active_counts",{})
        expected_counts={**{f"seed{s}_prediction":100 for s in SEEDS},**{f"seed{s}_calibration_sparse":400 for s in SEEDS}}
        fingerprints_ok=all(run.get(f"{name}_fingerprints_before")==run.get(f"{name}_fingerprints_after")
            and set(run.get(f"{name}_fingerprints_before",{}))=={str(s) for s in SEEDS} for name in ("Q22","K22","D11"))
        partial_fingerprints_ok=all(
            isinstance(run.get(f"{name}_fingerprints_before"),dict)
            and (run.get(f"{name}_fingerprints_after")=="unknown_before_return"
                 or run.get(f"{name}_fingerprints_after")==run.get(f"{name}_fingerprints_before"))
            for name in ("Q22","K22","D11"))
        inherited_ok=(isinstance(inherited,dict) and inherited.get("fit_scalar_labels_requested")==inherited.get("fit_scalar_labels_returned")==26400
            and inherited.get("fit_shared_50x50_22rhs_solve_attempts")==inherited.get("fit_shared_50x50_22rhs_solve_returns")==3
            and inherited.get("transition_scalar_coefficients_fitted")==3300)
        require(isinstance(paid,dict) and all(paid.get(key)==0 for key in ZERO_COSTS)
            and paid.get("fit_attempts",0)==len(fits)
            and paid.get("objective_calculation_attempts",0)==sum(fit["objective_calls_started"] for fit in fits)
            and paid.get("fit_returns",0)==sum(not fit["fit_failed"] for fit in fits)
            and paid.get("fit_failures",0)==sum(fit["fit_failed"] for fit in fits)
            and paid.get("position_scalar_coefficients_optimized",0)==100*sum(not fit["fit_failed"] for fit in fits)
            and (inherited_ok or not completed and not isinstance(inherited,dict))
            and partial_fingerprints_ok
            and isinstance(counts,dict) and set(counts)<=set(expected_counts)
            and all(type(value) is int and 0<=value<=expected_counts[name] for name,value in counts.items())
            and (not evaluation_complete or counts==expected_counts and fingerprints_ok),
            "10_zero_interaction_inherited_Q_cost_and_actual_fit_call_metadata")
        expected_records={(s,h,p,o) for s in SEEDS for h in HORIZONS for p in PREDICTORS for o in range(101-h)}
        identities=[(r["seed"],r["horizon"],r["predictor"],r["origin"]) for r in records]
        require(len(set(identities))==len(identities) and set(identities)<=expected_records
            and (not evaluation_complete or set(identities)==expected_records) and all(context_ok(r) for r in records),
            "11_fixed_prediction_identities_native_dimensions_and_continuous_request_IDs")
        params={p["seed"]:p for p in parameters}
        require(all(outcome_ok(r,params) for r in records),"12_saved_outcome_dimensions_history_partial_and_no_candidate_reasons")
        groups=metrics["groups"]
        expected_groups={(s,h,p,c) for s in SEEDS for h in HORIZONS for p in PREDICTORS for c in ((0,1,8,9) if p=="D11" else range(22))}
        group_ids=[(g["seed"],g["horizon"],g["predictor"],g["channel_index"]) for g in groups]
        require(len(set(group_ids))==len(group_ids) and set(group_ids)<=expected_groups
            and (not evaluation_complete or set(group_ids)==expected_groups) and all(g.get("channel")==STATE[g["channel_index"]] for g in groups),
            "13_fixed_channel_group_identities_allow_partial_failure")
        population=Counter((r["seed"],r["horizon"],r["predictor"]) for r in records)
        usable=Counter((r["seed"],r["horizon"],r["predictor"]) for r in records if r["available"])
        require(all(g.get("fixed_origin_count")==101-g["horizon"]
            and g.get("record_count")==population[g["seed"],g["horizon"],g["predictor"]]
            and g.get("usable_count")==usable[g["seed"],g["horizon"],g["predictor"]]
            and g.get("usable_count")+g.get("unavailable_count")==g.get("record_count")
            and g.get("full_fixed_count") is (g["record_count"]==g["usable_count"]==g["fixed_origin_count"])
            and g.get("partial_subset_method_ranking") is False for g in groups),
            "14_saved_population_counts_match_availability_without_metrics")
        gate=metrics.get("development_gate")
        gate_ok=(isinstance(gate,dict) and flags(gate) and gate.get("Q22_descriptive_only") is True
            and set(gate.get("comparisons",{}))=={"S22_vs_K22","S22_vs_D11"}
            and type(gate.get("passed")) is bool
            and all(flags(item) and item.get("candidate_predictor")=="S22" and item.get("baseline_predictor")==baseline
                and all(type(item.get(key)) is bool for key in ("passed","evaluated","all_fixed_usable_counts"))
                for baseline,item in (("K22",gate["comparisons"]["S22_vs_K22"]),("D11",gate["comparisons"]["S22_vs_D11"]))))
        require(type(run.get("development_gate_passed")) is bool
            and run["development_gate_passed"]==metrics.get("development_gate_passed")
            and (gate_ok if gate is not None else not completed)
            and (run["development_gate_passed"]==gate.get("passed") if completed else run["development_gate_passed"] is False),
            "15_saved_gate_Q_descriptive_flags_boolean_consistency_only")
        cost.update(scientific_metric_recalculations=0,scientific_gate_recalculations=0,model_restorations=0,
            prediction_records_inspected=len(records),channel_groups_inspected=len(groups),
            parameter_records_inspected=len(parameters),checkpoint_records_inspected=len(checkpoint_docs))
        status="completed"
    except Exception as exc:
        failure={"type":type(exc).__name__,"message":str(exc),"traceback":traceback.format_exc()}
    cost["wall_seconds"],cost["cpu_seconds"]=time.perf_counter()-wall,time.process_time()-cpu
    report={"status":status,"evidence_consistency_only":True,"expected_source_commit":args.expected_source_commit,
        "inputs":inputs,"checks":checks,"cost":dict(cost),"failure":failure,"scientific_adoption":False,
        "timing_excludes":"final report/stdout serialization and writes"}
    (output/"report.json").write_text(json.dumps(report,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    summary=json.dumps({"status":status,"output":str(output),"cost":dict(cost),
        "failure":failure and {key:failure[key] for key in ("type","message")}},allow_nan=False)+"\n"
    (output/"stdout.txt").write_text(summary,encoding="utf-8")
    print(summary,end="")
    return 0 if failure is None else 1


if __name__=="__main__":
    raise SystemExit(main())
