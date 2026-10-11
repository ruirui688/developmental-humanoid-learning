"""T: one finite gradient trust/Armijo revision of pinned S, starting from frozen Q."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import platform
import subprocess
import time
import traceback
import numpy as np
import importlib.metadata
import sys

SOURCE_PATH = "scripts/develop_guard_trust_position_transition.py"
PROTOCOL_PATH = "docs/GUARD_TRUST_POSITION_TRANSITION_DEVELOPMENT_PROTOCOL.md"
SUPPORT_PATH = "scripts/develop_guard_scaled_native_transition.py"
Q_SOURCE_PATH = "scripts/develop_guard_quadratic_native_transition.py"
Q_PROTOCOL_PATH = "docs/GUARD_QUADRATIC_NATIVE_TRANSITION_DEVELOPMENT_PROTOCOL.md"
C_ROOT = "results/cpu_validation/2026-10-11_guard_exploration/raw"
D_ROOT = "results/cpu_validation/2026-10-11_guard_lag_offline"
K_ROOT = "results/cpu_validation/2026-10-11_guard_native_transition/raw"
Q_ROOT = "results/cpu_validation/2026-10-12_guard_quadratic_native_transition"
Q_COMMIT = "20fa0321c84eb766eeafb9f8d906f554bca60622"
SEEDS, HORIZONS, PREDICTORS = (0,1,2), (1,2,5,15), ("T22","Q22","K22","D11")
RIDGE, POSITION_SCALE = .01, .12
Q_INPUT_PINS = {
    f"{Q_ROOT}/manifest.json": {"bytes":2366,"sha256":"327b38412bab68187c4195d12b4d4047dc6bffeffa0c18e0ea73271b870f25b5"},
    f"{Q_ROOT}/raw/manifest.json": {"bytes":646,"sha256":"5cc976083644a544b3395d028163f53d5e32645cdab7c05c2f10510346ea97f5"},
    f"{Q_ROOT}/raw/run.json": {"bytes":14222,"sha256":"98b0bff624b7feca68000b526306d7f58e8ab33bb3644966392a35c7225db6b1"},
    f"{Q_ROOT}/raw/parameters.json": {"bytes":3403882,"sha256":"6184bc6d89e2c0e2e53c9f09ca7f03a33e7990fe6e2a59f298c13617278ce7f4"},
}
HELPER_PINS = {'scripts/develop_guard_scaled_native_transition.py': 'df0833d08e722391f98de1bc2cbf81e2d0a866a3ea65def24e9b216d25787518', 'docs/GUARD_SCALED_NATIVE_TRANSITION_DEVELOPMENT_PROTOCOL.md': '0027650441b59159b407e21b687057e816c61c127ca6f5f4f06b6ac44b8b87b7', 'scripts/develop_guard_native_transition.py': 'f910bb6fd9f01ebf5fd52426b40b43414e50bebcfe6460cf6132bccb1a2192bb', 'docs/GUARD_NATIVE_TRANSITION_DEVELOPMENT_PROTOCOL.md': '7be868a3215dc0e29dd6e96f4f19635259fda15e3a54545194513e11a892ce56', 'src/developmental_physics/__init__.py': 'd2ee9d572836752f5f8404bfdf1fca8add0d62b9858f4c6dcd9cf7ddc6c53ea2', 'src/developmental_physics/guard_lag_pair_model.py': 'f3bcedf05b2c956357929e51dcab026ec13311428fa3c6c3383db114da3f7e57', 'src/developmental_physics/guard_pair_model.py': '2b8ae6f17aa12f1230daf38d8858f24bde3a3c21342e46a5b8fa6e91dc3da3b3', 'src/developmental_physics/local_pair_model.py': '81e0c9147bbfd7f825f14ad7439e6752c021bc08922abd04589a89b59fc509df', 'src/developmental_physics/local_model.py': 'f51a43c36675980cddd0cbf1fcba576469dd015e0850833ae58ffc32479de2b1', 'scripts/develop_guard_quadratic_native_transition.py': '6a8109ed9ba68b61674f9744ac0ea4ffce421ff8b4400abfe7cc081b5c16a147', 'docs/GUARD_QUADRATIC_NATIVE_TRANSITION_DEVELOPMENT_PROTOCOL.md': '77cb47c42efad889f4d15cf64207b528ab2c7e29908d55d3f16441b0b7a6c5d3'}



R_SOURCE_PATH = "scripts/develop_guard_kinematic_native_transition.py"
HELPER_PINS.update({
    R_SOURCE_PATH: "07a0135e6cd30e169f780f30eef09472fe857570fa0556f552dcdcbe258c693d",
    "docs/GUARD_KINEMATIC_NATIVE_TRANSITION_DEVELOPMENT_PROTOCOL.md": "8f3c86ccfc4626dbf6219e904daa73b208d2cac044a855e050875aecd62e5c45",
})

S_SOURCE_PATH = "scripts/develop_guard_multistep_position_transition.py"
S_PROTOCOL_PATH = "docs/GUARD_MULTISTEP_POSITION_TRANSITION_DEVELOPMENT_PROTOCOL.md"
S_ROOT = "results/cpu_validation/2026-10-12_guard_multistep_position_transition"
S_COMMIT = "fcab231a511996de83e28d93ce6749326b38308f"
HELPER_PINS.update({
    S_SOURCE_PATH: "22097d00bbb884e29b9d0e6cd060b53e0448beb72321685c11e7942762acfe7e",
    S_PROTOCOL_PATH: "ce5e8f0d3d6b5580406dd73a5b6f8a9928f56c5b13ad4056d1d05145659d944d",
})
S_METADATA_PINS = {
    f"{S_ROOT}/manifest.json": {"bytes":3373,"sha256":"febf8fb37098659957b67f711bad6b21bdb64b18c030d2f8fc8a787a43a0e112"},
    f"{S_ROOT}/raw/manifest.json": {"bytes":1255,"sha256":"66e5599416535db5b4c07bca322510d87a7e2333376db178c6f53f6d16333ca5"},
    f"{S_ROOT}/raw/run.json": {"bytes":38617,"sha256":"977b6913f586e8978f5c9bc8bd2904273096b14ddd7c024b0ca23785ded9a0ce"},
}
MAX_OBJECTIVE_CALLS, TIME_BOUNDARY_SECONDS = 100, 120.
OPTIMIZER_OPTIONS = {"initial_alpha":1e-3,"Armijo_c":1e-4,"beta":.5,
    "max_trials_per_update":10,"max_accepted_updates":30,
    "direction":"negative_true_gradient_normalized_by_L2",
    "alpha_reset":"1e-3_at_each_accepted_iteration","convergence":"exact_zero_gradient_only"}
TRAINING_ORIGINS = {1:400, 2:399, 5:396, 15:386}
FLAGS = {"scientific_adoption":False, "c4_scientific_validation":False, "c5_scientific_dependency_released":False}

def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+"\n").encode("utf-8")


def failure_json_safe(value):
    """Reuse the P failed-payload contract; do not replace invalid evidence by zero."""
    if isinstance(value, (float, np.floating)) and not np.isfinite(value):
        return {"nonfinite_float": "NaN" if np.isnan(value) else "+Infinity" if value > 0 else "-Infinity"}
    if isinstance(value, dict):
        return {key: failure_json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [failure_json_safe(item) for item in value]
    return value


def identity(data):
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def sources(repo, commit, cost, journal, synthetic=False):
    if Path(__file__).resolve() != (repo/SOURCE_PATH).resolve():
        raise ValueError("canonical_T_path_required")
    def git(*args):
        cost["git_query_attempts"] += 1
        result = subprocess.run(["git", *args], cwd=repo, capture_output=True, check=False)
        cost["git_return_bytes"] += len(result.stdout)+len(result.stderr)
        if result.returncode:
            raise ValueError("read_only_source_verification_failed")
        cost["git_query_returns"] += 1
        return result.stdout
    if not synthetic:
        if not commit or len(commit) != 40 or any(c not in "0123456789abcdef" for c in commit):
            raise ValueError("exact_T_commit_required")
        if git("rev-parse", "HEAD").decode().strip() != commit or git("status", "--porcelain").strip():
            raise ValueError("clean_exact_T_HEAD_required")
    for name in (SOURCE_PATH, PROTOCOL_PATH, *HELPER_PINS):
        cost["source_file_read_attempts"] += 1
        data = (repo/name).read_bytes()
        cost["source_file_read_returns"] += 1
        cost["source_raw_bytes"] += len(data)
        journal[name] = identity(data)
        if name in HELPER_PINS and journal[name]["sha256"] != HELPER_PINS[name]:
            raise ValueError(f"frozen_helper_hash_differs:{name}")
        if not synthetic and git("show", f"{commit}:{name}") != data:
            raise ValueError(f"committed_bytes_differ:{name}")


def load_helpers(repo, cost):
    cost["helper_module_load_attempts"] += 1
    spec = importlib.util.spec_from_file_location("frozen_S_scientific_core_for_T", repo/S_SOURCE_PATH)
    scientific = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(scientific)
    cost["helper_module_load_returns"] += 1
    restoration,support,core,q_support = scientific.load_helpers(repo,cost)
    return scientific,restoration,support,core,q_support


def read_S_metadata(repo,support,inputs,source_files,cost):
    """Read only the three pinned S metadata documents, never its candidate payload."""
    docs = {}
    for name,expected in S_METADATA_PINS.items():
        cost["input_file_read_attempts"] += 1
        data = (repo/name).read_bytes()
        cost["input_file_read_returns"] += 1
        cost["input_raw_bytes"] += len(data)
        cost["input_hash_bytes"] += len(data)
        inputs[name] = identity(data)
        if inputs[name] != expected:
            raise ValueError("frozen_S_metadata_differs:"+name)
        cost["json_parse_attempts"] += 1
        docs[name] = json.loads(data,parse_constant=lambda token: (_ for _ in ()).throw(ValueError("invalid_nonfinite_JSON:"+token)))
        cost["json_parse_returns"] += 1
    root,raw,run = (docs[f"{S_ROOT}/{name}"] for name in ("manifest.json","raw/manifest.json","raw/run.json"))
    for name in ("raw/manifest.json","raw/run.json"):
        if not support.same_identity(root["files"][name],inputs[f"{S_ROOT}/{name}"]):
            raise ValueError("frozen_S_root_metadata_binding_differs")
    if not support.same_identity(raw["files"]["run.json"],inputs[f"{S_ROOT}/raw/run.json"]):
        raise ValueError("frozen_S_raw_metadata_binding_differs")
    if (raw.get("status") != "failed"
            or raw.get("scientific_adoption") is not False or run.get("status") != "failed"
            or run.get("self_check") is not False or run["source"].get("commit") != S_COMMIT
            or run["source"].get("clean_committed_bytes_verified") is not True
            or run.get("original_source_commits") != support.COMMITS):
        raise ValueError("frozen_S_failed_clean_source_identity_differs")
    for name in HELPER_PINS:
        if not support.same_identity(run["source"]["files"][name],source_files[name]):
            raise ValueError("frozen_S_source_identity_differs:"+name)
    for name in (*support.PINS,*Q_INPUT_PINS):
        if not support.same_identity(run["inputs"][name],inputs[name]):
            raise ValueError("frozen_S_shared_original_inputs_differ:"+name)
    return run


class BudgetExhausted(RuntimeError):
    pass


class NonFiniteTrial(ArithmeticError):
    """Only an actual numerical nonfinite result; structural errors remain fatal."""
    pass


S_NUMERICAL_ERRORS = frozenset("nonfinite_tensor:"+name for name in (
    "absolute_q","phi29","prior22",
    "normalized_z6","quadratic21","phi50","residual22","candidate22",
    "normalized_terminal_q_error","horizon_loss","total_loss"))


def true_kernel(scientific,torch,q_support,U,UQ,frozen_other,batches,ref,ranges,cost,event):
    try:
        return scientific.objective_kernel(torch,q_support,U,UQ,frozen_other,batches,ref,ranges,cost,event,"T_training")
    except ValueError as exc:
        if type(exc) is ValueError and str(exc) in S_NUMERICAL_ERRORS:
            raise NonFiniteTrial(str(exc)) from exc
        raise



def fit_positions(torch,frozen_weights,kernel,cost,record,checkpoint_dir,
                  max_calls=MAX_OBJECTIVE_CALLS,seconds=TIME_BOUNDARY_SECONDS,
                  clock=time.perf_counter,max_accepted=30):
    """One Q initialization; rejected trials pay; only registered accepted T updates publish."""
    cost["fit_attempts"] += 1
    began = clock()
    record.update(status="attempted",budget={"hard_objective_call_limit":max_calls,
        "time_boundary_seconds":seconds,"timer_start":"before_initial_objective",
        "checks":"objective entry/exit; checkpoint entry/post-persistence registration; optimizer exit; no preemption"},
        objective_events=[],accepted_checkpoints=[],checkpoint_evidence=[],checkpoint_files={},
        objective_calls_started=0,accepted_updates=0,budget_exhausted=False,
        optimizer_invocation_attempted=False,optimizer_invocation_returned=False,
        optimizer_failed=False,fit_failed=False,selected_snapshot=None,
        initial_checkpoint=None,optimizer_converged=False)
    events = record["objective_events"]
    UQ = np.asarray(frozen_weights[:,:2],dtype=np.float64).copy()
    record["initial_UQ50x2"] = UQ.tolist()
    last = None
    def elapsed():
        return clock()-began
    def budget(reason):
        record.update(budget_exhausted=True,budget_reason=reason)
        cost["fit_budget_exhaustions"] += 1
        raise BudgetExhausted(reason)
    def persist(U,event,iteration):
        nonlocal last
        cost["checkpoint_registration_entry_requests"] += 1
        if elapsed() >= seconds:
            budget("time_boundary_at_checkpoint_entry")
        if U.shape != (50,2) or not np.isfinite(U).all():
            raise ValueError("finite_50x2_checkpoint_required")
        checkpoint = {"iteration":iteration,"objective_id":event["objective_id"],
            "entry_elapsed_seconds":elapsed(),"U50x2":U.tolist(),"loss":event["loss"],
            "gradient_l2_norm":event["gradient_l2_norm"],
            "parameter_sha256":identity(U.tobytes())["sha256"],
            "paid_cost_at_persistence_entry":dict(cost),"iteration0_evidence_only":iteration==0}
        name = f"iteration{iteration:02d}.json"
        data = json_bytes(checkpoint)
        cost["accepted_checkpoint_write_attempts"] += 1
        (checkpoint_dir/name).write_bytes(data)
        cost["accepted_checkpoint_write_returns"] += 1
        cost["accepted_checkpoint_write_bytes"] += len(data)
        relative = str((checkpoint_dir/name).relative_to(checkpoint_dir.parent.parent)).replace("\\","/")
        record["checkpoint_files"][relative] = identity(data)
        evidence = {**checkpoint,"file":relative,"file_identity":identity(data),
            "post_persistence_elapsed_seconds":elapsed(),"registered_accepted_update":False}
        record["checkpoint_evidence"].append(evidence)
        if evidence["post_persistence_elapsed_seconds"] >= seconds:
            evidence["outside_time_boundary"] = True
            budget("time_boundary_at_post_persistence_registration")
        if iteration == 0:
            record["initial_checkpoint"] = evidence
        else:
            evidence["registered_accepted_update"] = True
            record["accepted_checkpoints"].append(evidence)
            record["accepted_updates"] = iteration
            last = U.copy()
        cost["checkpoint_registration_returns"] += 1
    def evaluate(array,role,iteration,trial_index,alpha=None,origin_objective_id=None):
        cost["objective_function_entry_requests"] += 1
        if record["objective_calls_started"] >= max_calls:
            budget("hard_objective_call_limit")
        if elapsed() >= seconds:
            budget("time_boundary_at_objective_entry")
        if array.shape != (50,2):
            raise ValueError("fixed_objective_parameter_shape_required")
        record["objective_calls_started"] += 1
        event = {"objective_id":record["objective_calls_started"],"status":"attempted",
            "role":role,"accepted_iteration_requested":iteration,"trial_index":trial_index,
            "origin_objective_id":origin_objective_id,
            "alpha":alpha,"entry_elapsed_seconds":elapsed(),"trial_U50x2":array.tolist(),
            "loss":None,"gradient50x2":None,"finite":False}
        events.append(event)
        cost["objective_calculation_attempts"] += 1
        try:
            if not np.isfinite(array).all():
                raise NonFiniteTrial("nonfinite_objective_parameters")
            U = torch.tensor(array,dtype=torch.float64,device="cpu",requires_grad=True)
            cost["objective_forward_attempts"] += 1
            loss = kernel(U,event)
            if loss.ndim != 0:
                raise ValueError("scalar_objective_required")
            event["loss"] = float(loss.detach())
            if not bool(torch.isfinite(loss)):
                raise NonFiniteTrial("nonfinite_objective_loss")
            cost["objective_forward_returns"] += 1
            cost["objective_backward_attempts"] += 1
            loss.backward()
            cost["objective_backward_returns"] += 1
            if U.grad is None:
                raise ValueError("missing_position_head_gradient")
            gradient = U.grad.detach().cpu().numpy().copy()
            if gradient.shape != (50,2):
                raise ValueError("fixed_objective_gradient_shape_required")
            event["gradient50x2"] = gradient.tolist()
            if not np.isfinite(gradient).all():
                raise NonFiniteTrial("nonfinite_objective_gradient")
            event["gradient_l2_norm"] = float(np.linalg.norm(gradient))
            event["gradient_inf_norm"] = float(np.max(np.abs(gradient)))
            if not np.isfinite(event["gradient_l2_norm"]):
                raise NonFiniteTrial("nonfinite_gradient_norm")
            event.update(status="returned",exit_elapsed_seconds=elapsed(),finite=True)
            cost["objective_calculation_returns"] += 1
            event["paid_cost_at_exit"] = dict(cost)
            if event["exit_elapsed_seconds"] >= seconds:
                event["outside_time_boundary"] = True
                event.update(acceptance="rejected_outside_time_boundary",rejection_reason="objective_exit_time_boundary")
                budget("time_boundary_at_objective_exit")
            return event,gradient
        except BudgetExhausted:
            raise
        except BaseException as exc:
            event.update(status="numerical_nonfinite" if isinstance(exc,NonFiniteTrial) else "failed",
                exit_elapsed_seconds=elapsed(),failure={"type":type(exc).__name__,"message":str(exc)})
            cost["objective_calculation_failures"] += 1
            event["paid_cost_at_exit"] = dict(cost)
            if isinstance(exc,NonFiniteTrial) and role == "trial" and event["exit_elapsed_seconds"] >= seconds:
                event["outside_time_boundary"] = True
                event.update(acceptance="rejected_outside_time_boundary",rejection_reason="objective_exit_time_boundary")
                budget("time_boundary_at_failed_objective_exit")
            raise
    try:
        checkpoint_dir.mkdir(parents=True,exist_ok=False)
        current = UQ.copy()
        current_event,gradient = evaluate(current,"initial",0,0)
        persist(current,current_event,0)
        cost["optimizer_invocation_attempts"] += 1
        record["optimizer_invocation_attempted"] = True
        while True:
            norm = current_event["gradient_l2_norm"]
            if norm == 0.:
                if record["accepted_updates"] == 0:
                    raise RuntimeError("exact_zero_initial_gradient_no_T_update")
                record["optimizer_converged"] = True
                break
            if record["accepted_updates"] >= max_accepted:
                budget("maximum_accepted_update_limit")
            direction = -gradient/norm
            directional_derivative = float(np.sum(gradient*direction))
            if not np.isfinite(direction).all() or not np.isfinite(directional_derivative) or directional_derivative >= 0.:
                raise ValueError("finite_descent_direction_required")
            iteration = record["accepted_updates"]+1
            alpha = OPTIMIZER_OPTIONS["initial_alpha"]
            accepted = False
            for trial in range(1,OPTIMIZER_OPTIONS["max_trials_per_update"]+1):
                candidate = current+alpha*direction
                try:
                    event,new_gradient = evaluate(candidate,"trial",iteration,trial,alpha,current_event["objective_id"])
                except NonFiniteTrial:
                    event = events[-1]
                    event.update(acceptance="rejected",rejection_reason="numerical_nonfinite")
                    cost["optimizer_nonfinite_trial_rejections"] += 1
                    alpha *= OPTIMIZER_OPTIONS["beta"]
                    continue
                threshold = current_event["loss"]+OPTIMIZER_OPTIONS["Armijo_c"]*alpha*directional_derivative
                event.update(armijo_threshold=threshold,directional_derivative=directional_derivative,
                    origin_objective_id=current_event["objective_id"])
                if event["loss"] <= threshold:
                    event["acceptance"] = "Armijo_passed_pending_registration"
                    persist(candidate,event,iteration)
                    event["acceptance"] = "accepted_and_registered"
                    cost["optimizer_accepted_updates"] += 1
                    current,current_event,gradient = candidate,event,new_gradient
                    accepted = True
                    break
                event.update(acceptance="rejected",rejection_reason="Armijo_insufficient_decrease")
                cost["optimizer_Armijo_trial_rejections"] += 1
                alpha *= OPTIMIZER_OPTIONS["beta"]
            if not accepted:
                raise RuntimeError("line_search_stalled_all_10_trials_rejected")
        if elapsed() >= seconds:
            budget("time_boundary_at_optimizer_exit")
        cost["optimizer_invocation_returns"] += 1
        record["optimizer_invocation_returned"] = True
        record.update(status="returned",selected_snapshot=last.tolist(),
            selection="last_registered_accepted_T_update_only")
        cost["fit_returns"] += 1
    except BudgetExhausted as exc:
        record.update(budget_exhausted=True,budget_reason=str(exc),optimizer_converged=False)
        if last is None:
            record.update(status="failed",fit_failed=True,selected_snapshot=None,
                failure={"type":"NoAcceptedTUpdate","message":"budget_with_zero_registered_T_updates"})
            cost["fit_failures"] += 1
        else:
            record.update(status="budget_exhausted",selected_snapshot=last.tolist(),
                selection="last_registered_accepted_T_update_only")
            cost["fit_returns"] += 1
    except BaseException as exc:
        record.update(status="failed",fit_failed=True,optimizer_failed=record["optimizer_invocation_attempted"],
            optimizer_converged=False,selected_snapshot=None,
            failure_stage="optimizer_or_checkpoint" if record["optimizer_invocation_attempted"] else "initial_objective_or_checkpoint",
            failure={"type":type(exc).__name__,"message":str(exc),"traceback":traceback.format_exc()})
        cost["fit_failures"] += 1
        cost["optimizer_nonbudget_failures" if record["optimizer_invocation_attempted"] else "initial_nonbudget_failures"] += 1
    record["accepted_snapshot_retained_as_evidence_only"] = last.tolist() if record["fit_failed"] and last is not None else None
    record["elapsed_wall_seconds"] = elapsed()
    record["overrun_seconds"] = max(0.,record["elapsed_wall_seconds"]-seconds)
    record["objective_partial_count"] = sum(event.get("status")!="returned" for event in events)
    if record["fit_failed"]:
        return None
    if record["accepted_updates"] < 1 or last is None or not np.isfinite(last).all():
        raise ValueError("publish_requires_real_finite_registered_T_update")
    selected = np.asarray(frozen_weights,dtype=np.float64).copy()
    selected[:,:2] = last
    if not np.isfinite(selected).all() or not np.array_equal(selected[:,2:],frozen_weights[:,2:]):
        raise ValueError("finite_candidate_and_frozen_twenty_heads_required")
    cost["position_scalar_coefficients_optimized"] += 100
    cost["position_heads_published"] += 2
    return selected


def rollout_T(core,q_support,initial,previous,requests,qref,guard,weights,cost):
    paid = Counter()
    try:
        return q_support.rollout50(core,initial,previous,requests,qref,guard,weights,paid)
    finally:
        cost.update({key.replace("Q22","T22"):value for key,value in paid.items()})



def summarize(core,records,counts):
    groups = []
    for seed in SEEDS:
        for horizon in HORIZONS:
            expected = 101-horizon
            for name in PREDICTORS:
                own = [row for row in records if row["seed"] == seed and row["horizon"] == horizon and row["predictor"] == name]
                good = [row for row in own if row["available"]]
                for channel in range(22) if name != "D11" else (0,1,8,9):
                    groups.append({"seed":seed,"horizon":horizon,"predictor":name,"channel_index":channel,"channel":core.STATE_NAMES[channel],
                        "fixed_origin_count":expected,"record_count":len(own),"usable_count":len(good),"unavailable_count":len(own)-len(good),
                        "source_active_count":counts.get(f"seed{seed}_prediction",0),"full_fixed_count":len(own) == len(good) == expected,
                        "metric":core.metric([row["terminal_errors_x22"][str(channel)] for row in good]),"partial_subset_method_ranking":False})
    return groups


def dual_gate(core,groups):
    gates = {}
    for baseline in ("K22","D11"):
        mapping = {"T22":"learned22",baseline:"D11"}
        gate = core.development_gate([{**group,"predictor":mapping.get(group["predictor"],"cold22")} for group in groups])
        gate.update(candidate_predictor="T22",baseline_predictor=baseline,scope="new_seen_C_common_prediction_multistep_position_development_subgate")
        for check in gate["checks"]:
            for row in check["seed_records"]:
                row["T22_rmse"],row[f"{baseline}_rmse"] = row.pop("learned22_rmse"),row.pop("D11_rmse")
        gates[f"T22_vs_{baseline}"] = gate
    return {"scope":"single_seen_C_frozen_Q_trust_position_development","Q22_descriptive_only":True,"comparisons":gates,
        **{key:all(g[key] for g in gates.values()) for key in ("all_fixed_usable_counts","evaluated","passed")},
        "scientific_adoption":False,"c4_scientific_validation":False,"c5_scientific_dependency_released":False}

def write_outputs(output, parameters, predictions, metrics, run):
    encode = failure_json_safe
    payloads = {"parameters.json":json_bytes(encode(parameters)),"metrics.json":json_bytes(encode(metrics)),
        "run.json":json_bytes(encode(run)),
        "predictions.jsonl":b"".join((json.dumps(failure_json_safe(row) if row.get("available") is False else encode(row),
            ensure_ascii=False,allow_nan=False)+"\n").encode() for row in predictions)}
    if run.get("failure"):
        payloads["failure.json"] = json_bytes(encode(run))
    files = {}
    for row in parameters:
        files.update(row.get("fit",{}).get("checkpoint_files",{}))
    for name,data in payloads.items():
        (output/name).write_bytes(data)
        files[name] = identity(data)
    (output/"manifest.json").write_bytes(json_bytes({"schema_version":1,"status":run["status"],
        "scientific_adoption":False,"files":files}))


def self_check(torch,output,cost,cases):
    """Only new optimizer synthetic fixtures; no saved C/Q/S payload or old math tests."""
    weights = np.zeros((50,22),dtype=np.float64)
    weights[:,2:] = np.arange(1000,dtype=np.float64).reshape(50,20)*1e-6
    def quadratic(target):
        def kernel(U,event):
            expected = torch.zeros((50,2),dtype=torch.float64,device="cpu")
            expected[0,0] = target
            return torch.sum((U-expected).square())
        return kernel
    class Clock:
        def __init__(self): self.value = 0.
        def __call__(self): return self.value
    def exercise(name,kernel,max_calls=100,seconds=120.,max_accepted=30,clock=None,kind=None):
        root = output/("optimizer_fixture_"+name)
        root.mkdir()
        paid,record = Counter(),{}
        if callable(kernel) and kind == "factory":
            kernel,clock = kernel(paid)
        selected = fit_positions(torch,weights.copy(),kernel,paid,record,root/"fit_checkpoints"/"seed0",
            max_calls=max_calls,seconds=seconds,max_accepted=max_accepted,clock=clock or time.perf_counter)
        assert paid["objective_calculation_attempts"]==record["objective_calls_started"]<=max_calls
        assert record["selected_snapshot"] is None if selected is None else record["accepted_updates"]>=1
        if selected is not None:
            assert np.isfinite(selected).all() and np.array_equal(selected[:,2:],weights[:,2:])
            assert np.array_equal(selected[:,:2],record["accepted_checkpoints"][-1]["U50x2"])
        fixture_run = {"status":"failed" if record["fit_failed"] else "completed","self_check":True,
            "cost":dict(paid),"failure":record.get("failure"),**FLAGS}
        write_outputs(root,[{"seed":0,"fit":record}],[],{"status":fixture_run["status"],**FLAGS},fixture_run)
        cost.update(paid)
        case = {"case":name,"status":"passed","fit_status":record["status"],"selected":selected is not None,
            "accepted_updates":record["accepted_updates"],"objective_calls_started":record["objective_calls_started"],
            "paid_cost":dict(paid),"synthetic_only":True}
        cases.append(case)
        return selected,record,paid
    selected,r,_ = exercise("finite_Armijo_backtracking",quadratic(.0001),max_accepted=1)
    assert selected is not None and r["budget_exhausted"] and r["accepted_updates"]==1
    assert r["objective_calls_started"]==5
    assert [e["alpha"] for e in r["objective_events"][1:]]==[.001,.0005,.00025,.000125]
    assert abs(selected[0,0]-.000125)<1e-18
    def nonfinite(U,event):
        if float(U[0,0].detach())>.00075:
            event["synthetic_nonfinite_partial"] = {"value":float("inf")}
            raise NonFiniteTrial("synthetic_numerical_trial")
        return quadratic(.003)(U,event)
    selected,r,_ = exercise("nonfinite_rejection_smaller_finite_acceptance",nonfinite,max_accepted=1)
    assert selected is not None and abs(selected[0,0]-.0005)<1e-18 and r["objective_calls_started"]==3
    assert r["objective_events"][1]["status"]=="numerical_nonfinite"
    assert r["objective_events"][1]["rejection_reason"]=="numerical_nonfinite"
    def stalled(U,event):
        loss = quadratic(.0001)(U,event)
        return loss+10. if event["objective_id"]>=6 else loss
    selected,r,_ = exercise("ten_rejections_after_accepted_evidence_only",stalled)
    assert selected is None and r["accepted_updates"]==1 and not r["budget_exhausted"]
    assert r["accepted_snapshot_retained_as_evidence_only"] is not None and r["objective_calls_started"]==15
    def structural(U,event):
        if event["role"]=="trial": raise ValueError("synthetic_shape_or_internal_error")
        return quadratic(.003)(U,event)
    selected,r,_ = exercise("structural_ValueError_fatal",structural)
    assert selected is None and not r["budget_exhausted"] and r["failure"]["type"]=="ValueError"
    assert r["objective_events"][-1]["status"]=="failed"
    selected,r,_ = exercise("call_budget_zero_update_no_candidate",quadratic(.003),max_calls=1)
    assert selected is None and r["budget_exhausted"] and r["accepted_updates"]==0 and r["initial_checkpoint"]
    selected,r,_ = exercise("call_budget_real_update_publish",quadratic(.003),max_calls=2)
    assert selected is not None and r["budget_exhausted"] and r["accepted_updates"]==1
    def time_factory(cross_call):
        def factory(paid):
            timer = Clock()
            def kernel(U,event):
                if event["objective_id"]==cross_call: timer.value=2.
                return quadratic(.003)(U,event)
            return kernel,timer
        return factory
    selected,r,_ = exercise("objective_exit_time_zero_update_no_candidate",time_factory(2),seconds=1.,kind="factory")
    assert selected is None and r["budget_exhausted"] and r["accepted_updates"]==0 and r["overrun_seconds"]==1.
    selected,r,_ = exercise("objective_exit_time_real_update_publish",time_factory(3),seconds=1.,kind="factory")
    assert selected is not None and r["accepted_updates"]==1 and r["objective_events"][-1]["outside_time_boundary"]
    def fatal_time_factory(paid):
        timer = Clock()
        def kernel(U,event):
            if event["objective_id"]==3:
                timer.value=2.
                raise ValueError("synthetic_internal_error_at_time_boundary")
            return quadratic(.003)(U,event)
        return kernel,timer
    selected,r,_ = exercise("structural_error_over_time_stays_fatal",fatal_time_factory,seconds=1.,kind="factory")
    assert selected is None and r["accepted_updates"]==1 and not r["budget_exhausted"]
    assert r["failure"]["type"]=="ValueError" and r["accepted_snapshot_retained_as_evidence_only"] is not None
    def persist_factory(cross_write):
        def factory(paid):
            timer = Clock()
            def clock():
                if paid["accepted_checkpoint_write_returns"]>=cross_write: timer.value=2.
                return timer()
            return quadratic(.003),clock
        return factory
    selected,r,_ = exercise("post_persistence_crossing_zero_update_isolation",persist_factory(2),seconds=1.,kind="factory")
    assert selected is None and r["accepted_updates"]==0 and r["checkpoint_evidence"][-1]["outside_time_boundary"]
    selected,r,_ = exercise("post_persistence_crossing_preserves_previous_update",persist_factory(3),seconds=1.,kind="factory")
    assert selected is not None and r["accepted_updates"]==1 and len(r["accepted_checkpoints"])==1
    assert r["checkpoint_evidence"][-1]["outside_time_boundary"]
    selected,r,_ = exercise("exact_zero_initial_gradient_no_candidate",quadratic(0.))
    assert selected is None and r["accepted_updates"]==0 and not r["budget_exhausted"]


def main_run(args):
    repo,output = Path(args.repo).resolve(),Path(args.output).resolve()
    if any((repo/root).resolve().is_relative_to(output) for root in (C_ROOT,D_ROOT,K_ROOT,Q_ROOT,S_ROOT)):
        raise ValueError("output_must_not_contain_original_inputs")
    output.mkdir(parents=True,exist_ok=False)
    wall,cpu = time.perf_counter(),time.process_time()
    zero_keys = ("fit_attempts","fit_returns","fit_failures","fit_shared_50x50_22rhs_solve_attempts",
        "fit_shared_50x50_22rhs_solve_returns","fit_scalar_labels_requested","fit_scalar_labels_returned",
        "transition_scalar_coefficients_fitted","Q22_refits","physics_calls","physics_substeps","RLS_updates",
        "MPC_calls","K22_refits","D11_updates","objective_calculation_attempts","objective_calculation_returns")
    cost = Counter({key:0 for key in zero_keys})
    files,inputs,parameters,predictions,cases = {},{},[],[],[]
    counts,groups,gate = {},[],None
    restorations = {"K22":[],"Q22":[],"D11":[]}
    before_K,before_Q,before_D,after_K,after_Q,after_D = {},{},{},{},{},{}
    source_verified,status,failure,cmeta,frozen_Q_run,frozen_S_run = False,"failed",None,None,None,None
    scientific,support,restoration,runtime = None,None,None,{}
    fit_failures = []
    try:
        sources(repo,args.source_commit,cost,files,args.self_check)
        source_verified = not args.self_check
        scientific,restoration,support,core,q_support = load_helpers(repo,cost)
        torch,unused_minimize,runtime = scientific.load_runtime(cost)
        if args.self_check:
            self_check(torch,output,cost,cases)
            status = "self_check_passed"
        else:
            blobs,docs,cmeta = support.read_inputs(repo,inputs,cost,{"files":files})
            frozen_Q_run,Q_payload = restoration.read_Q_inputs(repo,support,inputs,files,cost)
            frozen_S_run = read_S_metadata(repo,support,inputs,files,cost)
            restored = support.restore_K(core,docs[f"{K_ROOT}/parameters.json"],cost,restorations["K22"])
            models = core.restore_models(docs[f"{D_ROOT}/raw/diagnostics.json"],repo,cost,restorations["D11"])
            before_K = {seed:row["fingerprint"] for seed,row in restored.items()}
            before_D = {seed:model.parameter_fingerprint() for seed,model in models.items()}
            restored_Q = restoration.restore_Q(core,q_support,Q_payload,restored,before_D,cost,restorations["Q22"])
            before_Q = {seed:row["fingerprint"] for seed,row in restored_Q.items()}
            trials,counts = core.parse_trials(blobs[f"{C_ROOT}/trace.jsonl.gz"],cost)
            T_weights = {}
            for seed in SEEDS:
                saved,Q = restored[seed],restored_Q[seed]
                pred_rows = trials[f"seed{seed}_prediction"]
                cal_rows = trials[f"seed{seed}_calibration_sparse"]
                qref,prefix_id = core.prefix_qref(pred_rows)
                if (qref!=saved["qref8"] or tuple(qref[:2])!=models[seed].qref or set(pred_rows)!=set(range(200))
                        or counts.get(f"seed{seed}_prediction")!=100 or counts.get(f"seed{seed}_calibration_sparse")!=400):
                    raise ValueError("fixed_C_population_prefix_qref_or_counts_differ")
                record = {"seed":seed,"predictor":"T22","available":False,"fit":{},
                    "state_order":core.STATE_NAMES,"feature_order":(*core.FEATURE_NAMES,*q_support.QUADRATIC_NAMES),
                    "quadratic_public_scales":q_support.Z_SCALES,"quadratic_pair_order":q_support.QUADRATIC_PAIRS,
                    "qref8":qref,"prediction_prefix_transition_id":prefix_id,
                    "Q22_parameter_fingerprint":before_Q[seed],"K22_parameter_fingerprint":before_K[seed],
                    "D11_parameter_fingerprint":before_D[seed],"frozen_Q_weights50x22":Q["weights"].tolist(),
                    "optimized_heads":[0,1],"frozen_head_indices":list(range(2,22)),
                    "optimized_parameter_count":100,"frozen_parameter_count":1000,
                    "loss_spec":"mean_h(mean_origins_and_two_axes(((q_pred_end-q_actual_end)/.12)^2))+.01*sum((U-UQ)^2)",
                    "optimizer":{"method":"finite_gradient_L2_trust_Armijo","true_full_gradient":True,"options":OPTIMIZER_OPTIONS},
                    "hard_objective_call_limit":MAX_OBJECTIVE_CALLS,"time_boundary_seconds":TIME_BOUNDARY_SECONDS}
                parameters.append(record)
                batches = scientific.make_training_data(torch,core,seed,cal_rows,saved,Q,models[seed],cost,record)
                UQ = torch.tensor(Q["weights"][:,:2].copy(),dtype=torch.float64,device="cpu")
                frozen_other = torch.tensor(Q["weights"][:,2:].copy(),dtype=torch.float64,device="cpu")
                ref = torch.tensor(qref,dtype=torch.float64,device="cpu")
                ranges = torch.tensor(models[seed].public_guard.public_joint_ranges,dtype=torch.float64,device="cpu")
                def kernel(U,event):
                    return true_kernel(scientific,torch,q_support,U,UQ,frozen_other,batches,ref,ranges,cost,event)
                T_weights[seed] = fit_positions(torch,Q["weights"],kernel,cost,record["fit"],
                    output/"fit_checkpoints"/f"seed{seed}")
                if T_weights[seed] is None:
                    fit_failures.append({"seed":seed,"failure":record["fit"].get("failure"),
                        "budget_exhausted":record["fit"]["budget_exhausted"],"optimizer_failed":record["fit"]["optimizer_failed"]})
                else:
                    record.update(available=True,selected_weights50x22=T_weights[seed].tolist(),
                        parameter_fingerprint=restoration.Q_parameter_fingerprint(core,q_support,qref,T_weights[seed]),
                        frozen_twenty_head_coefficients_equal=True)
            for seed in SEEDS:
                saved, rows = restored[seed], trials[f"seed{seed}_prediction"]
                for horizon in HORIZONS:
                    for origin in range(101-horizon):
                        common = {"seed": seed, "trial_id": f"seed{seed}_prediction", "origin": origin, "horizon": horizon,
                            "offline_saved_future_requests": True}
                        try:
                            active, past, requests, previous_v = core.window(rows, origin, horizon)
                            observation = active[0]["observation_before"]
                            initial = core.encode_state(observation, saved["qref8"], cost)
                            q, v = core.native(observation)[:2]
                            common.update(initial_x22=initial.tolist(), previous_v2=previous_v,
                                history_transition_ids=[row["shared_transition_id"] for row in past],
                                requested_transition_ids=[row["shared_transition_id"] for row in active], requested_sequence8=requests,
                                source_stopped_at_endpoint=core.stopped(active[-1]))
                        except (KeyError, TypeError, ValueError) as exc:
                            predictions.extend({**common, "predictor": predictor, "available": False,
                                "reason": f"window_unavailable:{type(exc).__name__}:{exc}"} for predictor in PREDICTORS)
                            continue
                        current = []
                        for predictor in PREDICTORS:
                            if predictor == "T22":
                                outcome = (rollout_T(core,q_support,initial,previous_v,requests,saved["qref8"],
                                    models[seed].public_guard,T_weights[seed],cost) if T_weights[seed] is not None else
                                    {"available":False,"reason":"fit_failed_no_T_candidate"})
                            elif predictor == "Q22":
                                outcome = q_support.rollout50(core,initial,previous_v,requests,saved["qref8"],models[seed].public_guard,restored_Q[seed]["weights"],cost)
                            elif predictor == "K22":
                                outcome = core.rollout22(initial, previous_v, requests, saved["qref8"], models[seed].public_guard, saved["weights"], cost, predictor)
                            else:
                                outcome = core.rollout11(models[seed], q, v, previous_v, requests, cost)
                            record = {**common, "predictor": predictor, **outcome, "scored": False}
                            predictions.append(record); current.append(record)
                        actual = core.encode_state(active[-1]["observation_after"], saved["qref8"], cost)
                        actual_q, actual_v = core.native(active[-1]["observation_after"])[:2]
                        for record in current:
                            if record["available"]:
                                if record["predictor"] == "D11":
                                    predicted_q, predicted_v = record["terminal_qv"]
                                    errors = {**{str(i): actual_q[i]-predicted_q[i] for i in range(2)},
                                              **{str(8+i): actual_v[i]-predicted_v[i] for i in range(2)}}
                                else:
                                    errors = {str(i): float(actual[i]-record["terminal_x22"][i]) for i in range(22)}
                                if not all(np.isfinite(value) for value in errors.values()):
                                    record.update(available=False, reason="nonfinite_terminal_error")
                                else:
                                    cost["score_scalar_error_calculations"] += len(errors)
                                    record.update(scored=True, actual_endpoint_x22=actual.tolist(), terminal_errors_x22=errors)
            after_K = {seed:support.parameter_fingerprint(core,row["qref8"],row["weights"]) for seed,row in restored.items()}
            after_D = {seed:model.parameter_fingerprint() for seed,model in models.items()}
            after_Q = {seed:restoration.Q_parameter_fingerprint(core,q_support,row["qref8"],row["weights"]) for seed,row in restored_Q.items()}
            if before_K!=after_K or before_D!=after_D or before_Q!=after_Q:
                raise ValueError("frozen_Q_K_D_baseline_mutated")
            groups = summarize(core,predictions,counts)
            gate = dual_gate(core,groups)
            if fit_failures:
                failure = {"type":"TFitFailed","message":"one_or_more_seeds_have_no_publishable_T_candidate","seeds":fit_failures}
                status = "failed"
            else:
                status = "completed"
    except BaseException as exc:
        failure = {"type":type(exc).__name__,"message":str(exc),"traceback":traceback.format_exc()}
    cost["wall_seconds"],cost["cpu_seconds"] = time.perf_counter()-wall,time.process_time()-cpu
    passed = bool(status=="completed" and gate and gate["passed"])
    all_input_paths = (*support.PINS,*restoration.Q_INPUT_PINS,*S_METADATA_PINS) if support and restoration else ()
    run = {"status":status,"self_check":args.self_check,
        "source":{"commit":args.source_commit,"files":files,"clean_committed_bytes_verified":source_verified},
        "inputs":inputs,"inputs_without_returned_read_record":{name:"unknown_before_read_return" for name in all_input_paths if name not in inputs},
        "original_source_commits":support.COMMITS if support else "unknown_before_support_load",
        "requested_source_commit":args.source_commit,
        "runtime":{"python":platform.python_version(),"numpy":np.__version__,"platform":platform.platform(),**runtime},
        "dependency_note":"preinstalled CPU packages, no download or install in T; SciPy identity imported by pinned S runtime helper, optimizer unused",
        "original_C_dependencies":cmeta.get("dependencies") if cmeta else "unknown_before_C_metadata_return",
        "source_active_counts":counts,"baseline_restorations":restorations,
        "K22_fingerprints_before":before_K,"K22_fingerprints_after":after_K or "unknown_before_return",
        "D11_fingerprints_before":before_D,"D11_fingerprints_after":after_D or "unknown_before_return",
        "Q22_fingerprints_before":before_Q,"Q22_fingerprints_after":after_Q or "unknown_before_return",
        "frozen_Q_original_cost":frozen_Q_run["cost"] if frozen_Q_run else "unknown_before_Q_run_return",
        "frozen_S_original_cost":frozen_S_run["cost"] if frozen_S_run else "unknown_before_S_metadata_return",
        "self_check_cases":cases,"fit_failures":fit_failures,"cost":dict(cost),"failure":failure,
        "development_gate_passed":passed,**FLAGS,"timing_excludes":"final output serialization and write"}
    metrics = {"status":status,"groups":groups,"development_gate":gate,"development_gate_passed":passed,**FLAGS}
    write_outputs(output,parameters,predictions,metrics,run)
    print(json.dumps(failure_json_safe({"status":status,"output":str(output),"cost":dict(cost),"development_gate_passed":passed,
        "failure":failure and {key:failure[key] for key in ("type","message")}}),allow_nan=False))
    return 0 if failure is None else 1

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo",default=".")
    parser.add_argument("--source-commit")
    parser.add_argument("--output",required=True)
    parser.add_argument("--self-check",action="store_true")
    args = parser.parse_args()
    if not args.self_check and not args.source_commit:
        parser.error("--source-commit required for formal execution")
    raise SystemExit(main_run(args))
