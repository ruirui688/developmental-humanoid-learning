"""U: final bounded limited-memory BFGS geometry revision, from frozen Q."""
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

SOURCE_PATH = "scripts/develop_guard_bounded_lbfgs_position_transition.py"
PROTOCOL_PATH = "docs/GUARD_BOUNDED_LBFGS_POSITION_TRANSITION_DEVELOPMENT_PROTOCOL.md"
SUPPORT_PATH = "scripts/develop_guard_scaled_native_transition.py"
Q_SOURCE_PATH = "scripts/develop_guard_quadratic_native_transition.py"
Q_PROTOCOL_PATH = "docs/GUARD_QUADRATIC_NATIVE_TRANSITION_DEVELOPMENT_PROTOCOL.md"
C_ROOT = "results/cpu_validation/2026-10-11_guard_exploration/raw"
D_ROOT = "results/cpu_validation/2026-10-11_guard_lag_offline"
K_ROOT = "results/cpu_validation/2026-10-11_guard_native_transition/raw"
Q_ROOT = "results/cpu_validation/2026-10-12_guard_quadratic_native_transition"
Q_COMMIT = "20fa0321c84eb766eeafb9f8d906f554bca60622"
SEEDS, HORIZONS, PREDICTORS = (0,1,2), (1,2,5,15), ("U22","Q22","K22","D11")
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

T_SOURCE_PATH = "scripts/develop_guard_trust_position_transition.py"
T_PROTOCOL_PATH = "docs/GUARD_TRUST_POSITION_TRANSITION_DEVELOPMENT_PROTOCOL.md"
T_ROOT = "results/cpu_validation/2026-10-12_guard_trust_position_transition"
T_COMMIT = "585540fe8ba07c1149e61c4aa6e9638679ecabb3"
HELPER_PINS.update({
    T_SOURCE_PATH:"e4cd9e06d078e85ba82614f05b160e69e8b11bd6e66773d795646f5766759464",
    T_PROTOCOL_PATH:"79a18f3bc52ded3b650d00f0942d7dfc0d4584727c7c71a4a254860af8a59824",
})
T_METADATA_PINS = {
    f"{T_ROOT}/raw/run.json": {"bytes":31433,"sha256":"a8118fa893a38d307b63e4cd6c407b3b6439544e3516f08d14ed9ffe6501d38d"},
    f"{T_ROOT}/manifest.json": {"bytes":12884,"sha256":"b6d5399b3f670a58e228390af3c94f3db860c70ffb6d83ef0429ec4d0cf9fe8a"},
    f"{T_ROOT}/raw/manifest.json": {"bytes":6848,"sha256":"c3056852a2d5d5a6cd3f12b64cc6e0fb42ed8e60d2627a68df8fb61ddd711582"},
}

MAX_OBJECTIVE_CALLS, TIME_BOUNDARY_SECONDS = 100, 120.
OPTIMIZER_OPTIONS = {"max_step_l2":1e-3,"initial_line_scale":1.,"Armijo_c":1e-4,"beta":.5,
    "max_trials_per_update":10,"max_accepted_updates":30,"memory_pairs":5,
    "direction":"negative_limited_memory_inverse_BFGS_gradient_capped_without_enlargement",
    "curvature":"finite_s_dot_y_strictly_positive_only","initial_inverse":"identity",
    "gamma":"last_s_dot_y_divided_by_last_y_dot_y",
    "fallback":"clear_history_once_then_negative_true_gradient_same_L2_cap",
    "line_scale_reset":"1_each_accepted_iteration","convergence":"exact_zero_gradient_only"}
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
        raise ValueError("canonical_U_path_required")
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
            raise ValueError("exact_U_commit_required")
        if git("rev-parse", "HEAD").decode().strip() != commit or git("status", "--porcelain").strip():
            raise ValueError("clean_exact_U_HEAD_required")
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


def load_helpers(repo,cost):
    cost["helper_module_load_attempts"] += 1
    spec = importlib.util.spec_from_file_location("frozen_T_numerical_and_scientific_helpers_for_U",repo/T_SOURCE_PATH)
    numerical = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(numerical)
    cost["helper_module_load_returns"] += 1
    scientific,restoration,support,core,q_support = numerical.load_helpers(repo,cost)
    return numerical,scientific,restoration,support,core,q_support


def read_T_metadata(repo,support,inputs,source_files,cost):
    """Restore T cost only; never read T candidate parameters or predictions."""
    docs = {}
    for name,expected in T_METADATA_PINS.items():
        cost["input_file_read_attempts"] += 1
        data = (repo/name).read_bytes()
        cost["input_file_read_returns"] += 1
        cost["input_raw_bytes"] += len(data)
        cost["input_hash_bytes"] += len(data)
        inputs[name] = identity(data)
        if inputs[name] != expected:
            raise ValueError("frozen_T_metadata_differs:"+name)
        cost["json_parse_attempts"] += 1
        docs[name] = json.loads(data,parse_constant=lambda token: (_ for _ in ()).throw(ValueError("invalid_nonfinite_JSON:"+token)))
        cost["json_parse_returns"] += 1
    root,raw,run = (docs[f"{T_ROOT}/{name}"] for name in ("manifest.json","raw/manifest.json","raw/run.json"))
    for name in ("raw/manifest.json","raw/run.json"):
        if not support.same_identity(root["files"][name],inputs[f"{T_ROOT}/{name}"]):
            raise ValueError("frozen_T_root_metadata_binding_differs")
    if not support.same_identity(raw["files"]["run.json"],inputs[f"{T_ROOT}/raw/run.json"]):
        raise ValueError("frozen_T_raw_metadata_binding_differs")
    if (raw.get("status") != "completed" or raw.get("scientific_adoption") is not False
            or run.get("status") != "completed" or run.get("self_check") is not False
            or run["source"].get("commit") != T_COMMIT
            or run["source"].get("clean_committed_bytes_verified") is not True
            or run.get("original_source_commits") != support.COMMITS):
        raise ValueError("frozen_T_completed_clean_source_identity_differs")
    for name in HELPER_PINS:
        if not support.same_identity(run["source"]["files"][name],source_files[name]):
            raise ValueError("frozen_T_source_identity_differs:"+name)
    for name in (*support.PINS,*Q_INPUT_PINS,*S_METADATA_PINS):
        if not support.same_identity(run["inputs"][name],inputs[name]):
            raise ValueError("frozen_T_shared_original_inputs_differ:"+name)
    return run


class BudgetExhausted(RuntimeError):
    pass


class NonFiniteTrial(ArithmeticError):
    """Only an actual numerical nonfinite result; structural errors remain fatal."""
    pass


def true_kernel(numerical,scientific,torch,q_support,U,UQ,frozen_other,batches,ref,ranges,cost,event):
    paid = Counter()
    try:
        return numerical.true_kernel(scientific,torch,q_support,U,UQ,frozen_other,batches,ref,ranges,paid,event)
    except numerical.NonFiniteTrial as exc:
        raise NonFiniteTrial(str(exc)) from exc
    finally:
        cost.update({key.replace("T_training","U_training"):value for key,value in paid.items()})



class InvalidNumericalDirection(ArithmeticError):
    pass


def geometric_direction(gradient,history,cost,event):
    """Finite two-loop inverse BFGS; cap once, never enlarge; one fixed reset fallback."""
    cost["geometry_direction_attempts"] += 1
    g = np.asarray(gradient,dtype=np.float64)
    if g.shape != (50,2) or not np.isfinite(g).all():
        cost["geometry_direction_failures"] += 1
        event.update(status="failed",failure={"type":"ValueError","message":"finite_true_50x2_gradient_required"})
        raise ValueError("finite_true_50x2_gradient_required")
    event.update(status="attempted",gradient50x2=g.tolist(),
        history_pair_ids=[pair["pair_id"] for pair in history],history_size=len(history),
        fallback_used=False,history_cleared=False)
    def inner(a,b,label):
        cost["geometry_inner_product_attempts"] += 1
        value = float(np.sum(a*b))
        cost["geometry_inner_product_returns"] += 1
        event.setdefault("inner_products",[]).append({"label":label,"value":value})
        return value
    def cap_and_descent(p,label):
        event[label+"_uncapped50x2"] = p.tolist()
        if p.shape != (50,2):
            raise ValueError("fixed_direction_shape_required")
        if not np.isfinite(p).all():
            raise InvalidNumericalDirection("nonfinite_direction")
        cost["geometry_direction_norm_attempts"] += 1
        norm = float(np.linalg.norm(p))
        cost["geometry_direction_norm_returns"] += 1
        event[label+"_uncapped_l2"] = norm
        if not np.isfinite(norm):
            raise InvalidNumericalDirection("nonfinite_direction_norm")
        capped = norm>OPTIMIZER_OPTIONS["max_step_l2"]
        if capped:
            p = p*(OPTIMIZER_OPTIONS["max_step_l2"]/norm)
            cost["geometry_L2_cap_applications"] += 1
        event[label+"_capped"] = capped
        event[label+"_p50x2"] = p.tolist()
        if not np.isfinite(p).all():
            raise InvalidNumericalDirection("nonfinite_capped_direction")
        slope = inner(g,p,label+"_capped_gradient_dot_p")
        if not np.isfinite(slope) or slope>=0.:
            raise InvalidNumericalDirection("nonfinite_or_non_descent_capped_direction")
        return p,slope
    try:
        with np.errstate(over="ignore",invalid="ignore",divide="ignore",under="ignore"):
            try:
                q = g.copy()
                if len(history)>OPTIMIZER_OPTIONS["memory_pairs"]:
                    raise ValueError("fixed_five_pair_memory_required")
                for pair in history:
                    if (np.asarray(pair["s50x2"]).shape!=(50,2) or np.asarray(pair["y50x2"]).shape!=(50,2)):
                        raise ValueError("fixed_curvature_pair_shape_required")
                    if not np.isfinite(pair["s50x2"]).all() or not np.isfinite(pair["y50x2"]).all():
                        raise ValueError("finite_saved_curvature_pair_required")
                    if not np.isfinite(pair["s_dot_y"]) or pair["s_dot_y"]<=0.:
                        raise ValueError("strict_positive_saved_curvature_required")
                if history:
                    cost["geometry_gamma_division_attempts"] += 1
                    gamma = float(np.divide(history[-1]["s_dot_y"],history[-1]["y_dot_y"]))
                    cost["geometry_gamma_division_returns"] += 1
                    event["gamma"] = gamma
                    if not np.isfinite(gamma):
                        raise InvalidNumericalDirection("nonfinite_gamma")
                    if not np.isfinite(history[-1]["y_dot_y"]):
                        raise InvalidNumericalDirection("nonfinite_y_dot_y")
                else:
                    gamma = 1.
                    event["gamma"] = gamma
                    cost["geometry_identity_inverse_directions"] += 1
                reverse = []
                for pair in reversed(history):
                    cost["geometry_rho_division_attempts"] += 1
                    rho = float(np.divide(1.,pair["s_dot_y"]))
                    cost["geometry_rho_division_returns"] += 1
                    alpha = rho*inner(pair["s50x2"],q,"reverse_s_dot_q")
                    event.setdefault("reverse",[]).append({"pair_id":pair["pair_id"],"rho":rho,"alpha":alpha})
                    if not np.isfinite(rho) or not np.isfinite(alpha):
                        raise InvalidNumericalDirection("nonfinite_rho_or_reverse_alpha")
                    q = q-alpha*pair["y50x2"]
                    cost["geometry_axpy_vector_returns"] += 1
                    if not np.isfinite(q).all():
                        event["reverse_partial_q50x2"] = q.tolist()
                        raise InvalidNumericalDirection("nonfinite_reverse_q")
                    reverse.append((pair,rho,alpha))
                r = gamma*q
                cost["geometry_inverse_scale_vector_returns"] += 1
                for pair,rho,alpha in reversed(reverse):
                    beta = rho*inner(pair["y50x2"],r,"forward_y_dot_r")
                    event.setdefault("forward",[]).append({"pair_id":pair["pair_id"],"beta":beta})
                    if not np.isfinite(beta):
                        raise InvalidNumericalDirection("nonfinite_forward_beta")
                    r = r+pair["s50x2"]*(alpha-beta)
                    cost["geometry_axpy_vector_returns"] += 1
                    if not np.isfinite(r).all():
                        event["forward_partial_r50x2"] = r.tolist()
                        raise InvalidNumericalDirection("nonfinite_forward_r")
                p,slope = cap_and_descent(-r,"BFGS")
            except InvalidNumericalDirection as exc:
                cost["geometry_reset_fallback_attempts"] += 1
                event.update(fallback_used=True,history_cleared=True,
                    first_direction_failure={"type":type(exc).__name__,"message":str(exc)})
                history.clear()
                p,slope = cap_and_descent(-g.copy(),"fallback_negative_gradient")
                cost["geometry_reset_fallback_returns"] += 1
        event.update(status="returned",p50x2=p.tolist(),capped_gradient_dot_p=slope,
            history_size_after_direction=len(history),paid_cost_at_exit=dict(cost))
        cost["geometry_direction_returns"] += 1
        event["paid_cost_at_exit"] = dict(cost)
        return p,slope
    except BaseException as exc:
        cost["geometry_direction_failures"] += 1
        event.update(status="failed",failure={"type":type(exc).__name__,"message":str(exc)},
            paid_cost_at_exit=dict(cost))
        raise


def update_history(previous_U,previous_gradient,current_U,current_gradient,history,cost,event,pair_id,previous_objective_id,current_objective_id):
    """Called only after the new accepted checkpoint registered; initial Q is a legal left anchor."""
    cost["history_pair_attempts"] += 1
    old_U,new_U,old_g,new_g = (np.asarray(value,dtype=np.float64) for value in
        (previous_U,current_U,previous_gradient,current_gradient))
    if any(value.shape!=(50,2) or not np.isfinite(value).all() for value in (old_U,new_U,old_g,new_g)):
        cost["history_pair_failures"] += 1
        event.update(status="failed",failure={"type":"ValueError","message":"finite_50x2_registered_pair_endpoints_required"})
        raise ValueError("finite_50x2_registered_pair_endpoints_required")
    event.update(status="attempted",pair_id=pair_id,previous_objective_id=previous_objective_id,
        current_objective_id=current_objective_id,source="registered_accepted_update_with_validated_initial_or_registered_left_anchor",
        history_pair_ids_before=[pair["pair_id"] for pair in history])
    with np.errstate(over="ignore",invalid="ignore",divide="ignore",under="ignore"):
        s,y = new_U-old_U,new_g-old_g
        cost["history_endpoint_difference_vectors"] += 2
        sy,yy = float(np.sum(s*y)),float(np.sum(y*y))
        cost["history_curvature_inner_product_attempts"] += 2
        cost["history_curvature_inner_product_returns"] += 2
    event.update(s50x2=s.tolist(),y50x2=y.tolist(),s_dot_y=sy,y_dot_y=yy,added=False)
    if np.isfinite(s).all() and np.isfinite(y).all() and np.isfinite(sy) and sy>0.:
        history.append({"pair_id":pair_id,"s50x2":s.copy(),"y50x2":y.copy(),"s_dot_y":sy,"y_dot_y":yy})
        event["added"] = True
        cost["history_positive_curvature_additions"] += 1
        if len(history)>OPTIMIZER_OPTIONS["memory_pairs"]:
            event["evicted_pair_id"] = history.pop(0)["pair_id"]
            cost["history_oldest_pair_evictions"] += 1
    else:
        event["rejection_reason"] = "nonfinite_or_nonpositive_s_dot_y"
        cost["history_nonpositive_or_nonfinite_pair_rejections"] += 1
    cost["history_pair_returns"] += 1
    event.update(status="returned",history_pair_ids_after=[pair["pair_id"] for pair in history],
        paid_cost_at_exit=dict(cost))


def fit_positions(torch,frozen_weights,kernel,cost,record,checkpoint_dir,
                  max_calls=MAX_OBJECTIVE_CALLS,seconds=TIME_BOUNDARY_SECONDS,
                  clock=time.perf_counter,max_accepted=30):
    """One Q initialization; rejected trials pay; only registered accepted U updates publish."""
    cost["fit_attempts"] += 1
    began = clock()
    record.update(status="attempted",budget={"hard_objective_call_limit":max_calls,
        "time_boundary_seconds":seconds,"timer_start":"before_initial_objective",
        "checks":"objective entry/exit; checkpoint entry/post-persistence registration; optimizer exit; no preemption"},
        objective_events=[],accepted_checkpoints=[],checkpoint_evidence=[],checkpoint_files={},
        objective_calls_started=0,accepted_updates=0,budget_exhausted=False,
        optimizer_invocation_attempted=False,optimizer_invocation_returned=False,
        optimizer_failed=False,fit_failed=False,selected_snapshot=None,direction_events=[],history_events=[],
        initial_checkpoint=None,optimizer_converged=False)
    events = record["objective_events"]
    UQ = np.asarray(frozen_weights[:,:2],dtype=np.float64).copy()
    record["initial_UQ50x2"] = UQ.tolist()
    last = None
    history = []
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
            "alpha":alpha,"alpha_semantics":"dimensionless_t_for_already_L2_capped_p","entry_elapsed_seconds":elapsed(),"trial_U50x2":array.tolist(),
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
                    raise RuntimeError("exact_zero_initial_gradient_no_U_update")
                record["optimizer_converged"] = True
                break
            if record["accepted_updates"] >= max_accepted:
                budget("maximum_accepted_update_limit")
            iteration = record["accepted_updates"]+1
            direction_event = {"iteration_requested":iteration,"origin_objective_id":current_event["objective_id"]}
            record["direction_events"].append(direction_event)
            direction,directional_derivative = geometric_direction(gradient,history,cost,direction_event)
            alpha = OPTIMIZER_OPTIONS["initial_line_scale"]
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
                    pair_event = {}
                    record["history_events"].append(pair_event)
                    update_history(current,gradient,candidate,new_gradient,history,cost,pair_event,iteration,
                        current_event["objective_id"],event["objective_id"])
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
            selection="last_registered_accepted_U_update_only")
        cost["fit_returns"] += 1
    except BudgetExhausted as exc:
        record.update(budget_exhausted=True,budget_reason=str(exc),optimizer_converged=False)
        if last is None:
            record.update(status="failed",fit_failed=True,selected_snapshot=None,
                failure={"type":"NoAcceptedUUpdate","message":"budget_with_zero_registered_U_updates"})
            cost["fit_failures"] += 1
        else:
            record.update(status="budget_exhausted",selected_snapshot=last.tolist(),
                selection="last_registered_accepted_U_update_only")
            cost["fit_returns"] += 1
    except BaseException as exc:
        record.update(status="failed",fit_failed=True,optimizer_failed=record["optimizer_invocation_attempted"],
            optimizer_converged=False,selected_snapshot=None,
            failure_stage="optimizer_or_checkpoint" if record["optimizer_invocation_attempted"] else "initial_objective_or_checkpoint",
            failure={"type":type(exc).__name__,"message":str(exc),"traceback":traceback.format_exc()})
        cost["fit_failures"] += 1
        cost["optimizer_nonbudget_failures" if record["optimizer_invocation_attempted"] else "initial_nonbudget_failures"] += 1
    record["accepted_snapshot_retained_as_evidence_only"] = last.tolist() if record["fit_failed"] and last is not None else None
    record["final_history_pair_ids"] = [pair["pair_id"] for pair in history]
    record["elapsed_wall_seconds"] = elapsed()
    record["overrun_seconds"] = max(0.,record["elapsed_wall_seconds"]-seconds)
    record["objective_partial_count"] = sum(event.get("status")!="returned" for event in events)
    if record["fit_failed"]:
        return None
    if record["accepted_updates"] < 1 or last is None or not np.isfinite(last).all():
        raise ValueError("publish_requires_real_finite_registered_U_update")
    selected = np.asarray(frozen_weights,dtype=np.float64).copy()
    selected[:,:2] = last
    if not np.isfinite(selected).all() or not np.array_equal(selected[:,2:],frozen_weights[:,2:]):
        raise ValueError("finite_candidate_and_frozen_twenty_heads_required")
    cost["position_scalar_coefficients_optimized"] += 100
    cost["position_heads_published"] += 2
    return selected


def rollout_U(core,q_support,initial,previous,requests,qref,guard,weights,cost):
    paid = Counter()
    try:
        return q_support.rollout50(core,initial,previous,requests,qref,guard,weights,paid)
    finally:
        cost.update({key.replace("Q22","U22"):value for key,value in paid.items()})



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
        mapping = {"U22":"learned22",baseline:"D11"}
        gate = core.development_gate([{**group,"predictor":mapping.get(group["predictor"],"cold22")} for group in groups])
        gate.update(candidate_predictor="U22",baseline_predictor=baseline,scope="new_seen_C_common_prediction_multistep_position_development_subgate")
        for check in gate["checks"]:
            for row in check["seed_records"]:
                row["U22_rmse"],row[f"{baseline}_rmse"] = row.pop("learned22_rmse"),row.pop("D11_rmse")
        gates[f"U22_vs_{baseline}"] = gate
    return {"scope":"single_seen_C_frozen_Q_bounded_lbfgs_position_development","Q22_descriptive_only":True,"comparisons":gates,
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
    """Only new direction/history geometry; no T engineering fixture, model or science payload."""
    def vector(first=0.,second=0.):
        value = np.zeros((50,2),dtype=np.float64)
        value[0,0],value[0,1] = first,second
        return value
    def direction_case(name,g,history,expected,fallback=False):
        paid,event = Counter(),{}
        p,slope = geometric_direction(g,history,paid,event)
        assert np.allclose(p,expected,rtol=0.,atol=5e-19)
        assert slope<0. and event["fallback_used"] is fallback
        if fallback:
            assert np.array_equal(p,expected)
        cost.update(paid)
        cases.append({"case":name,"status":"passed","synthetic_only":True,"direction":event,"paid_cost":dict(paid)})
        return event
    event = direction_case("identity_inverse_large_gradient_caps_once",vector(.003),[],vector(-.001))
    assert event["BFGS_capped"] is True
    event = direction_case("identity_small_gradient_not_enlarged",vector(.0001),[],vector(-.0001))
    assert event["BFGS_capped"] is False
    def pair(s,y,pair_id):
        return {"pair_id":pair_id,"s50x2":s,"y50x2":y,"s_dot_y":float(np.sum(s*y)),"y_dot_y":float(np.sum(y*y))}
    event = direction_case("one_pair_Newton_small_amplitude_retained",vector(.0002),
        [pair(vector(.001),vector(.002),1)],vector(-.0001))
    assert event["gamma"]==.5 and event["BFGS_capped"] is False
    direction_case("two_loop_two_axis_diagonal_inverse",vector(.0003,.0005),
        [pair(vector(.001),vector(.003),1),pair(vector(0.,.001),vector(0.,.005),2)],vector(-.0001,-.0001))
    paid,history,events = Counter(),[],[]
    for i in range(1,7):
        event = {}
        update_history(vector(),vector(),vector(.001),vector(.002),history,paid,event,i,i-1,i)
        events.append(event)
    assert [p["pair_id"] for p in history]==[2,3,4,5,6] and events[-1]["evicted_pair_id"]==1
    for current_g in (vector(),vector(-.002)):
        event = {}
        update_history(vector(),vector(),vector(.001),current_g,history,paid,event,7,6,7)
        events.append(event)
        assert event["added"] is False and [p["pair_id"] for p in history]==[2,3,4,5,6]
    cost.update(paid)
    cases.append({"case":"registered_anchor_positive_curvature_only_memory5","status":"passed",
        "synthetic_only":True,"history_events":events,"paid_cost":dict(paid)})
    histories = [[pair(vector(.001),vector(1e-310),1)],[pair(vector(1e-310),vector(1.),1)]]
    for history,label,reason in zip(histories,("nonfinite_gamma_reset_once","nonfinite_rho_reset_once"),
            ("nonfinite_gamma","nonfinite_rho_or_reverse_alpha")):
        event = direction_case(label,vector(0.,.0001),history,vector(0.,-.0001),True)
        assert history==[] and event["first_direction_failure"]["message"]==reason
        assert event["fallback_negative_gradient_capped"] is False
    history = [pair(vector(1e-200),vector(1e100),1)]
    event = direction_case("finite_zero_descent_underflow_reset_once",vector(0.,1e-100),history,vector(0.,-1e-100),True)
    assert history==[] and event["first_direction_failure"]["message"]=="nonfinite_or_non_descent_capped_direction"
    paid,event = Counter(),{}
    try:
        geometric_direction(np.zeros(100),[],paid,event)
    except ValueError as exc:
        assert str(exc)=="finite_true_50x2_gradient_required" and paid["geometry_reset_fallback_attempts"]==0
    else:
        raise AssertionError("shape_error_must_stay_fatal")
    cost.update(paid)
    cases.append({"case":"structural_shape_error_stays_fatal_without_reset","status":"passed","synthetic_only":True,
        "paid_cost":dict(paid)})


def main_run(args):
    repo,output = Path(args.repo).resolve(),Path(args.output).resolve()
    if any((repo/root).resolve().is_relative_to(output) for root in (C_ROOT,D_ROOT,K_ROOT,Q_ROOT,S_ROOT,T_ROOT)):
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
    source_verified,status,failure,cmeta,frozen_Q_run,frozen_S_run,frozen_T_run = False,"failed",None,None,None,None,None
    numerical,scientific,support,restoration,runtime = None,None,None,None,{}
    fit_failures = []
    try:
        sources(repo,args.source_commit,cost,files,args.self_check)
        source_verified = not args.self_check
        numerical,scientific,restoration,support,core,q_support = load_helpers(repo,cost)
        torch,unused_minimize,runtime = scientific.load_runtime(cost)
        if args.self_check:
            self_check(torch,output,cost,cases)
            status = "self_check_passed"
        else:
            blobs,docs,cmeta = support.read_inputs(repo,inputs,cost,{"files":files})
            frozen_Q_run,Q_payload = restoration.read_Q_inputs(repo,support,inputs,files,cost)
            frozen_S_run = numerical.read_S_metadata(repo,support,inputs,files,cost)
            frozen_T_run = read_T_metadata(repo,support,inputs,files,cost)
            restored = support.restore_K(core,docs[f"{K_ROOT}/parameters.json"],cost,restorations["K22"])
            models = core.restore_models(docs[f"{D_ROOT}/raw/diagnostics.json"],repo,cost,restorations["D11"])
            before_K = {seed:row["fingerprint"] for seed,row in restored.items()}
            before_D = {seed:model.parameter_fingerprint() for seed,model in models.items()}
            restored_Q = restoration.restore_Q(core,q_support,Q_payload,restored,before_D,cost,restorations["Q22"])
            before_Q = {seed:row["fingerprint"] for seed,row in restored_Q.items()}
            trials,counts = core.parse_trials(blobs[f"{C_ROOT}/trace.jsonl.gz"],cost)
            U_weights = {}
            for seed in SEEDS:
                saved,Q = restored[seed],restored_Q[seed]
                pred_rows = trials[f"seed{seed}_prediction"]
                cal_rows = trials[f"seed{seed}_calibration_sparse"]
                qref,prefix_id = core.prefix_qref(pred_rows)
                if (qref!=saved["qref8"] or tuple(qref[:2])!=models[seed].qref or set(pred_rows)!=set(range(200))
                        or counts.get(f"seed{seed}_prediction")!=100 or counts.get(f"seed{seed}_calibration_sparse")!=400):
                    raise ValueError("fixed_C_population_prefix_qref_or_counts_differ")
                record = {"seed":seed,"predictor":"U22","available":False,"fit":{},
                    "state_order":core.STATE_NAMES,"feature_order":(*core.FEATURE_NAMES,*q_support.QUADRATIC_NAMES),
                    "quadratic_public_scales":q_support.Z_SCALES,"quadratic_pair_order":q_support.QUADRATIC_PAIRS,
                    "qref8":qref,"prediction_prefix_transition_id":prefix_id,
                    "Q22_parameter_fingerprint":before_Q[seed],"K22_parameter_fingerprint":before_K[seed],
                    "D11_parameter_fingerprint":before_D[seed],"frozen_Q_weights50x22":Q["weights"].tolist(),
                    "optimized_heads":[0,1],"frozen_head_indices":list(range(2,22)),
                    "optimized_parameter_count":100,"frozen_parameter_count":1000,
                    "loss_spec":"mean_h(mean_origins_and_two_axes(((q_pred_end-q_actual_end)/.12)^2))+.01*sum((U-UQ)^2)",
                    "optimizer":{"method":"bounded_memory5_inverse_LBFGS_true_gradient_Armijo","true_full_gradient":True,"options":OPTIMIZER_OPTIONS},
                    "hard_objective_call_limit":MAX_OBJECTIVE_CALLS,"time_boundary_seconds":TIME_BOUNDARY_SECONDS}
                parameters.append(record)
                batches = scientific.make_training_data(torch,core,seed,cal_rows,saved,Q,models[seed],cost,record)
                UQ = torch.tensor(Q["weights"][:,:2].copy(),dtype=torch.float64,device="cpu")
                frozen_other = torch.tensor(Q["weights"][:,2:].copy(),dtype=torch.float64,device="cpu")
                ref = torch.tensor(qref,dtype=torch.float64,device="cpu")
                ranges = torch.tensor(models[seed].public_guard.public_joint_ranges,dtype=torch.float64,device="cpu")
                def kernel(U,event):
                    return true_kernel(numerical,scientific,torch,q_support,U,UQ,frozen_other,batches,ref,ranges,cost,event)
                U_weights[seed] = fit_positions(torch,Q["weights"],kernel,cost,record["fit"],
                    output/"fit_checkpoints"/f"seed{seed}")
                if U_weights[seed] is None:
                    fit_failures.append({"seed":seed,"failure":record["fit"].get("failure"),
                        "budget_exhausted":record["fit"]["budget_exhausted"],"optimizer_failed":record["fit"]["optimizer_failed"]})
                else:
                    record.update(available=True,selected_weights50x22=U_weights[seed].tolist(),
                        parameter_fingerprint=restoration.Q_parameter_fingerprint(core,q_support,qref,U_weights[seed]),
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
                            if predictor == "U22":
                                outcome = (rollout_U(core,q_support,initial,previous_v,requests,saved["qref8"],
                                    models[seed].public_guard,U_weights[seed],cost) if U_weights[seed] is not None else
                                    {"available":False,"reason":"fit_failed_no_U_candidate"})
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
                failure = {"type":"UFitFailed","message":"one_or_more_seeds_have_no_publishable_U_candidate","seeds":fit_failures}
                status = "failed"
            else:
                status = "completed"
    except BaseException as exc:
        failure = {"type":type(exc).__name__,"message":str(exc),"traceback":traceback.format_exc()}
    cost["wall_seconds"],cost["cpu_seconds"] = time.perf_counter()-wall,time.process_time()-cpu
    passed = bool(status=="completed" and gate and gate["passed"])
    all_input_paths = (*support.PINS,*restoration.Q_INPUT_PINS,*S_METADATA_PINS,*T_METADATA_PINS) if support and restoration else ()
    run = {"status":status,"self_check":args.self_check,
        "source":{"commit":args.source_commit,"files":files,"clean_committed_bytes_verified":source_verified},
        "inputs":inputs,"inputs_without_returned_read_record":{name:"unknown_before_read_return" for name in all_input_paths if name not in inputs},
        "original_source_commits":support.COMMITS if support else "unknown_before_support_load",
        "requested_source_commit":args.source_commit,
        "runtime":{"python":platform.python_version(),"numpy":np.__version__,"platform":platform.platform(),**runtime},
        "dependency_note":"preinstalled CPU packages, no download or install in U; pinned T/S runtime identity reused; SciPy optimizer unused",
        "original_C_dependencies":cmeta.get("dependencies") if cmeta else "unknown_before_C_metadata_return",
        "source_active_counts":counts,"baseline_restorations":restorations,
        "K22_fingerprints_before":before_K,"K22_fingerprints_after":after_K or "unknown_before_return",
        "D11_fingerprints_before":before_D,"D11_fingerprints_after":after_D or "unknown_before_return",
        "Q22_fingerprints_before":before_Q,"Q22_fingerprints_after":after_Q or "unknown_before_return",
        "frozen_Q_original_cost":frozen_Q_run["cost"] if frozen_Q_run else "unknown_before_Q_run_return",
        "frozen_S_original_cost":frozen_S_run["cost"] if frozen_S_run else "unknown_before_S_metadata_return",
        "frozen_T_original_cost":frozen_T_run["cost"] if frozen_T_run else "unknown_before_T_metadata_return",
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
