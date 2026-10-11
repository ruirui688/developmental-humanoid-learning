"""S: one finite own-rollout position-head objective on frozen Q's x22/phi50."""
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

SOURCE_PATH = "scripts/develop_guard_multistep_position_transition.py"
PROTOCOL_PATH = "docs/GUARD_MULTISTEP_POSITION_TRANSITION_DEVELOPMENT_PROTOCOL.md"
SUPPORT_PATH = "scripts/develop_guard_scaled_native_transition.py"
Q_SOURCE_PATH = "scripts/develop_guard_quadratic_native_transition.py"
Q_PROTOCOL_PATH = "docs/GUARD_QUADRATIC_NATIVE_TRANSITION_DEVELOPMENT_PROTOCOL.md"
C_ROOT = "results/cpu_validation/2026-10-11_guard_exploration/raw"
D_ROOT = "results/cpu_validation/2026-10-11_guard_lag_offline"
K_ROOT = "results/cpu_validation/2026-10-11_guard_native_transition/raw"
Q_ROOT = "results/cpu_validation/2026-10-12_guard_quadratic_native_transition"
Q_COMMIT = "20fa0321c84eb766eeafb9f8d906f554bca60622"
SEEDS, HORIZONS, PREDICTORS = (0,1,2), (1,2,5,15), ("S22","Q22","K22","D11")
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
MAX_OBJECTIVE_CALLS, TIME_BOUNDARY_SECONDS = 100, 120.
OPTIMIZER_OPTIONS = {"maxiter":30, "maxfun":60, "maxls":10, "ftol":1e-12, "gtol":1e-8}
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
        raise ValueError("canonical_S_path_required")
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
            raise ValueError("exact_S_commit_required")
        if git("rev-parse", "HEAD").decode().strip() != commit or git("status", "--porcelain").strip():
            raise ValueError("clean_exact_S_HEAD_required")
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
    spec = importlib.util.spec_from_file_location("frozen_R_restoration_only_for_S", repo/R_SOURCE_PATH)
    restoration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(restoration)
    cost["helper_module_load_returns"] += 1
    support, core, q_support = restoration.load_helpers(repo, cost)
    sys.path.insert(0, str(repo/"src"))
    return restoration, support, core, q_support


def load_runtime(cost):
    cost["new_runtime_import_attempts"] += 2
    import torch
    import scipy
    from scipy.optimize import minimize
    cost["new_runtime_import_returns"] += 2
    versions = {"torch":torch.__version__, "torch_distribution":importlib.metadata.version("torch"),
        "torch_git_version":torch.version.git_version, "torch_cuda":torch.version.cuda,
        "scipy":scipy.__version__, "scipy_git_revision":scipy.version.git_revision,
        "numpy":np.__version__, "device":"cpu", "dtype":"float64", "torch_num_threads":1}
    if (versions["torch"] != "2.2.2+cpu" or versions["torch_distribution"] != "2.2.2"
            or versions["torch_git_version"] != "39901f229520a5256505ec24782f716ee7ddc843"
            or versions["torch_cuda"] is not None or versions["scipy"] != "1.15.3"
            or versions["scipy_git_revision"] != "e29dcb65a2040f04819b426a04b60d44a8f69c04"
            or versions["numpy"] != "1.26.4"):
        raise ValueError("fixed_preinstalled_CPU_runtime_identity_differs")
    torch.set_num_threads(1)
    return torch, minimize, versions


def tensor_finite(torch, value, name):
    if not bool(torch.isfinite(value).all()):
        raise ValueError("nonfinite_tensor:"+name)
    return value


def tensor_step50(torch, q_support, x, previous, command, ref, ranges, weights, cost, owner, partial=None, debug=None):
    """Vectorized original Q mapping; no state detach, clamp, smoothing or teacher forcing."""
    n = x.shape[0]
    evidence = partial if partial is not None else {}
    evidence.update(status="attempted", batch_count=n)
    cost[f"{owner}_transition_attempts"] += n
    phi = prior = candidate = z = quadratic = residual = None
    try:
        if x.shape != (n,22) or previous.shape != (n,2) or command.shape != (n,8) or weights.shape != (50,22):
            raise ValueError("fixed_tensor_step_shapes_required")
        for name,value in (("state",x),("previous_v",previous),("request",command),("qref",ref),("weights",weights)):
            tensor_finite(torch,value,name)
        cost[f"{owner}_feature_prior_attempts"] += n
        native_q = tensor_finite(torch,x[:,:8]+ref,"absolute_q")
        cost[f"{owner}_start_guard_attempts"] += n
        clipped = torch.clamp(command[:,:2], -.5, .5)
        blocked = ((native_q[:,:2] <= ranges[:,0]+.03) & (clipped < 0.)) | (
                   (native_q[:,:2] >= ranges[:,1]-.03) & (clipped > 0.))
        g = torch.where(blocked, torch.zeros_like(clipped), clipped)
        cost[f"{owner}_start_guard_returns"] += n
        hinge = torch.sign(g)*torch.clamp(torch.abs(g)-.25,min=0.)
        phi29 = torch.cat((x,g,hinge,torch.ones((n,1),dtype=torch.float64,device="cpu"),x[:,8:10]-previous),dim=1)
        prior = torch.cat((x[:,:8]+.02*x[:,8:16],x[:,8:10]+.02*g,x[:,10:]),dim=1)
        tensor_finite(torch,phi29,"phi29"); tensor_finite(torch,prior,"prior22")
        cost[f"{owner}_feature_prior_returns"] += n
        cost[f"{owner}_prior_scalar_outputs"] += 22*n
        cost[f"{owner}_quadratic_mapping_attempts"] += n
        cost[f"{owner}_scale_scalar_divisions_requested"] += 6*n
        scales = torch.tensor(q_support.Z_SCALES,dtype=torch.float64,device="cpu")
        z = phi29[:,list(q_support.Z_PHI_INDICES)]/scales
        cost[f"{owner}_scale_scalar_divisions_returned"] += 6*n
        tensor_finite(torch,z,"normalized_z6")
        cost[f"{owner}_quadratic_scalar_products_requested"] += 21*n
        quadratic = torch.stack([z[:,i]*z[:,j] for i,j in q_support.QUADRATIC_PAIRS],dim=1)
        cost[f"{owner}_quadratic_scalar_products_returned"] += 21*n
        tensor_finite(torch,quadratic,"quadratic21")
        cost[f"{owner}_feature_scalar_materializations_requested"] += 50*n
        phi = torch.cat((phi29,quadratic),dim=1)
        tensor_finite(torch,phi,"phi50")
        cost[f"{owner}_feature_scalar_materializations_returned"] += 50*n
        cost[f"{owner}_quadratic_mapping_returns"] += n
        cost[f"{owner}_residual_vector_attempts"] += n
        cost[f"{owner}_residual_scalar_head_attempts"] += 22*n
        residual = phi @ weights
        cost[f"{owner}_residual_vector_returns"] += n
        cost[f"{owner}_residual_scalar_head_returns"] += 22*n
        tensor_finite(torch,residual,"residual22")
        candidate = prior+residual
        tensor_finite(torch,candidate,"candidate22")
        old_v = x[:,8:10].clone()
        cost[f"{owner}_history_advance_scalar_copies"] += 2*n
        cost[f"{owner}_transition_returns"] += n
        if debug is not None:
            debug.update(phi50=phi,prior22=prior,g2=g,blocked2=blocked)
        evidence["status"] = "returned"
        return candidate, old_v
    except BaseException as exc:
        cost[f"{owner}_transition_failures"] += n
        evidence.update(status="failed", failure={"type":type(exc).__name__,"message":str(exc)},
            old_x22=x.detach().cpu().tolist(), previous_v2=previous.detach().cpu().tolist(),
            known_request8=command.detach().cpu().tolist())
        for name,value in (("phi50",phi),("prior22",prior),("normalized_z6",z),
                           ("quadratic21",quadratic),("residual22",residual),("candidate22",candidate)):
            if value is not None:
                evidence[name] = value.detach().cpu().tolist()
        raise


def make_training_data(torch, core, seed, rows, saved_K, saved_Q, D_model, cost, record):
    cost["training_population_attempts"] += 1
    trial = f"seed{seed}_calibration_sparse"
    if set(rows) != set(range(500)):
        raise ValueError("exact_full_C500_calibration_trial_required")
    qref,prefix_id = core.prefix_qref(rows)
    ids = [rows[i]["shared_transition_id"] for i in range(100,500)]
    if qref != saved_K["qref8"] or qref != saved_Q["qref8"] or tuple(qref[:2]) != D_model.qref:
        raise ValueError("C_calibration_K_Q_D_qref_differs")
    if prefix_id != saved_K["qref_source_transition_id"] or ids != saved_K["ids"]:
        raise ValueError("C_calibration_K_saved_source_IDs_differ")
    label_pool = []
    record.update(training_trial_id=trial,qref_source_transition_id=prefix_id,
        training_transition_ids=ids,training_fixed_count=400,training_usable_count=0,
        unique_terminal_q_label_transition_ids=ids,unique_terminal_q_labels400x2=label_pool,
        training_windows={})
    for step in range(100,500):
        q = core.native(rows[step]["observation_after"])[0]
        label_pool.append((np.asarray(q[:2])-np.asarray(qref[:2])).tolist())
        cost["training_unique_q_label_scalars_materialized"] += 2
    labels = core.finite_array(label_pool,(400,2))
    batches = {}
    for h in HORIZONS:
        initials,previous,requests,targets,windows = [],[],[],[],[]
        evidence = {"fixed_origin_count":TRAINING_ORIGINS[h],"windows":windows,
            "initial_x22":initials,"previous_v2":previous,"known_requests8":requests,"terminal_label_qrel2":targets}
        record["training_windows"][str(h)] = evidence
        for origin in range(TRAINING_ORIGINS[h]):
            cost["training_window_validation_attempts"] += 1
            active,past,commands,pv = core.window(rows,origin,h)
            expected = saved_K["ids"][origin:origin+h]
            if [row["shared_transition_id"] for row in active] != expected:
                raise ValueError("training_window_IDs_differ")
            initial = core.encode_state(active[0]["observation_before"],qref,cost)
            target = labels[origin+h-1]
            initials.append(initial.tolist()); previous.append(pv); requests.append(commands); targets.append(target.tolist())
            windows.append({"origin":origin,"history_transition_ids":[row["shared_transition_id"] for row in past],
                "requested_transition_ids":expected,"terminal_label_transition_id":expected[-1],
                "source_stopped_at_endpoint":core.stopped(active[-1])})
            cost["training_window_validation_returns"] += 1
            cost["training_window_state_scalars_materialized"] += 22
            cost["training_window_history_scalars_materialized"] += 2
            cost["training_window_request_scalars_materialized"] += 8*h
            cost["training_window_terminal_label_scalar_copies"] += 2
        batches[h] = {name:torch.tensor(values,dtype=torch.float64,device="cpu")
            for name,values in (("initial",initials),("previous",previous),("requests",requests),("target",targets))}
        cost["training_tensor_scalar_materializations"] += TRAINING_ORIGINS[h]*(22+2+8*h+2)
        evidence["usable_origin_count"] = len(windows)
    record.update(training_usable_count=400,unique_terminal_q_label_scalars=800,
        objective_fixed_windows=1581,objective_fixed_label_uses=3162,objective_fixed_transitions=8968)
    cost["training_population_returns"] += 1
    return batches


def objective_kernel(torch, q_support, U, UQ, frozen_other, batches, ref, ranges, cost, event, owner):
    weights = torch.cat((U,frozen_other),dim=1)
    parts = []
    for h,batch in batches.items():
        x,previous = batch["initial"],batch["previous"]
        cost[f"{owner}_window_attempts"] += x.shape[0]
        for step in range(h):
            partial = {"horizon":h,"step_index":step}
            event["last_transition"] = partial
            x,previous = tensor_step50(torch,q_support,x,previous,batch["requests"][:,step,:],ref,ranges,weights,cost,owner,partial)
        count = 2*x.shape[0]
        cost[f"{owner}_terminal_q_label_use_attempts"] += count
        error = tensor_finite(torch,(x[:,:2]-batch["target"])/POSITION_SCALE,"normalized_terminal_q_error")
        part = torch.mean(error.square())
        event.setdefault("horizon_mean_square_losses",{})[str(h)] = float(part.detach())
        tensor_finite(torch,part,"horizon_loss")
        cost[f"{owner}_terminal_q_label_use_returns"] += count
        cost[f"{owner}_window_returns"] += x.shape[0]
        parts.append(part)
    cost[f"{owner}_regularizer_scalar_requests"] += 100
    penalty = RIDGE*torch.sum((U-UQ).square())
    cost[f"{owner}_regularizer_scalar_returns"] += 100
    event["regularizer_sum_loss"] = float(penalty.detach())
    total = torch.stack(parts).mean()+penalty
    event["loss"] = float(total.detach())
    return tensor_finite(torch,total,"total_loss")


class BudgetExhausted(RuntimeError):
    pass


def fit_positions(torch, minimize, frozen_weights, kernel, cost, record, checkpoint_dir,
                  max_calls=MAX_OBJECTIVE_CALLS, seconds=TIME_BOUNDARY_SECONDS, clock=time.perf_counter):
    """Exactly one optimizer invocation; accepted callback order alone selects."""
    cost["fit_attempts"] += 1
    cost["position_scalar_coefficients_optimization_requested"] += 100
    began = clock()
    record.update(status="attempted",budget={"hard_objective_call_limit":max_calls,
        "time_boundary_seconds":seconds,"timer_start":"before_initial_objective",
        "checks":"objective entry/exit, callback entry, optimizer return; no preemption"},
        objective_events=[],accepted_checkpoints=[],checkpoint_files={},objective_calls_started=0,
        accepted_updates=0,budget_exhausted=False,optimizer_failed=False,fit_failed=False,
        selected_snapshot=None,optimizer_result=None)
    record["optimizer_invocation_attempted"] = False
    record["optimizer_invocation_returned"] = False
    last = None
    events = record["objective_events"]
    UQ = np.asarray(frozen_weights[:,:2],dtype=np.float64).copy()
    record["initial_UQ50x2"] = UQ.tolist()
    def elapsed():
        return clock()-began
    def budget(reason):
        record["budget_exhausted"] = True
        record["budget_reason"] = reason
        record["overrun_seconds"] = max(0.,elapsed()-seconds)
        cost["fit_budget_exhaustions"] += 1
        raise BudgetExhausted(reason)
    def save_snapshot(flat,event,iteration):
        nonlocal last
        if elapsed() >= seconds:
            budget("time_boundary_before_snapshot_registration")
        U = np.asarray(flat,dtype=np.float64).reshape(50,2).copy()
        if not np.isfinite(U).all():
            raise ValueError("nonfinite_accepted_parameters")
        checkpoint = {"iteration":iteration,"objective_id":event["objective_id"],"elapsed_seconds":elapsed(),
            "U50x2":U.tolist(),"loss":event["loss"],"gradient_l2_norm":event["gradient_l2_norm"],
            "parameter_sha256":identity(U.tobytes())["sha256"],"paid_cost_at_acceptance":dict(cost)}
        name = f"iteration{iteration:02d}.json"
        data = json_bytes(checkpoint)
        cost["accepted_checkpoint_write_attempts"] += 1
        (checkpoint_dir/name).write_bytes(data)
        cost["accepted_checkpoint_write_returns"] += 1
        cost["accepted_checkpoint_write_bytes"] += len(data)
        record["checkpoint_files"][str((checkpoint_dir/name).relative_to(checkpoint_dir.parent.parent)).replace("\\","/")] = identity(data)
        if elapsed() >= seconds:
            record.setdefault("unregistered_checkpoint_overruns",[]).append(checkpoint)
            budget("time_boundary_at_snapshot_registration_exit")
        record["accepted_checkpoints"].append(checkpoint)
        last = U.copy()
        record["accepted_updates"] = iteration
    def fun(flat):
        cost["objective_function_entry_requests"] += 1
        if record["objective_calls_started"] >= max_calls:
            budget("hard_objective_call_limit")
        if elapsed() >= seconds:
            budget("time_boundary_at_objective_entry")
        record["objective_calls_started"] += 1
        event = {"objective_id":record["objective_calls_started"],"status":"attempted",
            "entry_elapsed_seconds":elapsed(),"trial_U50x2":np.asarray(flat).reshape(50,2).tolist()}
        events.append(event)
        cost["objective_calculation_attempts"] += 1
        try:
            array = np.asarray(flat,dtype=np.float64).reshape(50,2)
            if not np.isfinite(array).all():
                raise ValueError("nonfinite_objective_parameters")
            U = torch.tensor(array,dtype=torch.float64,device="cpu",requires_grad=True)
            cost["objective_forward_attempts"] += 1
            loss = kernel(U,event)
            if loss.ndim != 0:
                raise ValueError("scalar_objective_required")
            event["loss"] = float(loss.detach())
            tensor_finite(torch,loss,"objective_loss")
            cost["objective_forward_returns"] += 1
            event["loss"] = float(loss.detach())
            cost["objective_backward_attempts"] += 1
            loss.backward()
            cost["objective_backward_returns"] += 1
            if U.grad is None:
                raise ValueError("missing_position_head_gradient")
            grad = U.grad.detach().cpu().numpy().copy()
            event["gradient50x2"] = grad.tolist()
            if not np.isfinite(grad).all():
                raise ValueError("nonfinite_objective_gradient")
            event["gradient_l2_norm"] = float(np.linalg.norm(grad))
            event["gradient_inf_norm"] = float(np.max(np.abs(grad)))
            if not np.isfinite(event["gradient_l2_norm"]):
                raise ValueError("nonfinite_gradient_norm")
            event.update(status="returned",exit_elapsed_seconds=elapsed(),finite=True)
            cost["objective_calculation_returns"] += 1
            if event["exit_elapsed_seconds"] >= seconds:
                event["outside_time_boundary"] = True
                budget("time_boundary_at_objective_exit")
            return event["loss"],grad.reshape(-1)
        except BudgetExhausted:
            raise
        except BaseException as exc:
            event.update(status="failed",exit_elapsed_seconds=elapsed(),
                failure={"type":type(exc).__name__,"message":str(exc)})
            cost["objective_calculation_failures"] += 1
            raise
    def callback(flat):
        cost["optimizer_callback_attempts"] += 1
        if elapsed() >= seconds:
            budget("time_boundary_at_callback_entry")
        value = np.asarray(flat,dtype=np.float64).reshape(50,2)
        if not np.isfinite(value).all():
            raise ValueError("nonfinite_callback_parameters")
        match = next((event for event in reversed(events) if event.get("status")=="returned"
            and not event.get("outside_time_boundary") and np.array_equal(value,np.asarray(event["trial_U50x2"]))),None)
        if match is None:
            raise ValueError("callback_without_same_finite_objective_return")
        save_snapshot(value,match,record["accepted_updates"]+1)
        cost["optimizer_callback_returns"] += 1
    try:
        checkpoint_dir.mkdir(parents=True,exist_ok=False)
        fun(UQ.reshape(-1))
        save_snapshot(UQ,events[-1],0)
        cost["optimizer_invocation_attempts"] += 1
        record["optimizer_invocation_attempted"] = True
        result = minimize(fun,UQ.reshape(-1).copy(),method="L-BFGS-B",jac=True,bounds=None,
            callback=callback,options=dict(OPTIMIZER_OPTIONS))
        cost["optimizer_invocation_returns"] += 1
        record["optimizer_invocation_returned"] = True
        message = str(result.message)
        record["optimizer_result"] = {"success":bool(result.success),"status":int(result.status),"message":message,
            "nit":int(result.nit),"nfev":int(result.nfev),"njev":int(result.njev),
            "result_x_selected":False,"result_fun_selected":False}
        if not bool(result.success):
            upper = message.upper()
            limit = int(result.status)==1 and ("ITERATIONS REACHED LIMIT" in upper or "EVALUATIONS EXCEEDS LIMIT" in upper)
            if limit:
                record.update(budget_exhausted=True,budget_reason="optimizer_limit:"+message)
                cost["fit_optimizer_limit_stops"] += 1
            else:
                raise RuntimeError("optimizer_failed:"+message)
        if elapsed() >= seconds:
            record.update(budget_exhausted=True,budget_reason="time_boundary_at_optimizer_return")
            cost["fit_time_boundary_return_stops"] += 1
        if last is None:
            raise ValueError("no_finite_accepted_snapshot")
        record.update(status="returned",selected_snapshot=last.tolist(),
            selection="last_finite_callback_or_validated_iteration0_only",optimizer_converged=bool(result.success))
        cost["fit_returns"] += 1
    except BudgetExhausted as exc:
        record.update(status="budget_exhausted",budget_exhausted=True,budget_reason=str(exc),optimizer_converged=False)
        if last is None:
            record.update(status="failed",fit_failed=True,
                failure={"type":"NoAcceptedSnapshot","message":"budget_before_finite_iteration0"})
            cost["fit_failures"] += 1
        else:
            record["selected_snapshot"] = last.tolist()
            record["selection"] = "last_finite_callback_or_validated_iteration0_only"
            cost["fit_returns"] += 1
    except BaseException as exc:
        record.update(status="failed",fit_failed=True,optimizer_failed=record["optimizer_invocation_attempted"],optimizer_converged=False,
            failure_stage="optimizer_or_callback" if record["optimizer_invocation_attempted"] else "initial_objective_or_checkpoint",
            failure={"type":type(exc).__name__,"message":str(exc),"traceback":traceback.format_exc()},
            selected_snapshot=None,accepted_snapshot_retained_as_evidence_only=last.tolist() if last is not None else None)
        cost["fit_failures"] += 1
        cost["optimizer_nonbudget_failures" if record["optimizer_invocation_attempted"] else "initial_nonbudget_failures"] += 1
    record["elapsed_wall_seconds"] = elapsed()
    record["overrun_seconds"] = max(0.,record["elapsed_wall_seconds"]-seconds)
    record["objective_partial_count"] = sum(event.get("status")!="returned" for event in events)
    if record["fit_failed"]:
        return None
    selected = frozen_weights.copy()
    selected[:,:2] = np.asarray(record["selected_snapshot"])
    if not np.array_equal(selected[:,2:],frozen_weights[:,2:]):
        raise ValueError("frozen_twenty_head_coefficients_mutated")
    cost["position_scalar_coefficients_optimized"] += 100
    cost["position_heads_published"] += 2
    return selected


def rollout_S(core,q_support,initial,previous,requests,qref,guard,weights,cost):
    paid = Counter()
    try:
        return q_support.rollout50(core,initial,previous,requests,qref,guard,weights,paid)
    finally:
        cost.update({key.replace("Q22","S22"):value for key,value in paid.items()})


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
        mapping = {"S22":"learned22",baseline:"D11"}
        gate = core.development_gate([{**group,"predictor":mapping.get(group["predictor"],"cold22")} for group in groups])
        gate.update(candidate_predictor="S22",baseline_predictor=baseline,scope="new_seen_C_common_prediction_multistep_position_development_subgate")
        for check in gate["checks"]:
            for row in check["seed_records"]:
                row["S22_rmse"],row[f"{baseline}_rmse"] = row.pop("learned22_rmse"),row.pop("D11_rmse")
        gates[f"S22_vs_{baseline}"] = gate
    return {"scope":"single_seen_C_frozen_Q_multistep_position_development","Q22_descriptive_only":True,"comparisons":gates,
        **{key:all(g[key] for g in gates.values()) for key in ("all_fixed_usable_counts","evaluated","passed")},
        "scientific_adoption":False,"c4_scientific_validation":False,"c5_scientific_dependency_released":False}

def write_outputs(output, parameters, predictions, metrics, run):
    encode = failure_json_safe if run["status"] == "failed" else lambda value: value
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


def self_check(torch, minimize, core, q_support, output, cost, cases):
    from types import SimpleNamespace
    from developmental_physics.guard_pair_model import KnownAngleGuard
    guard = KnownAngleGuard(((-1.,1.),(-2.,2.)))
    ref = np.zeros(8)
    weights = np.arange(1100,dtype=np.float64).reshape(50,22)*1e-6
    def T(value,grad=False):
        return torch.tensor(value,dtype=torch.float64,device="cpu",requires_grad=grad)
    ranges = T(guard.public_joint_ranges)
    event = {"case":"batched_torch_Q_step_guard_equality_clip_zero_hinge_quadratic_old_v_parity","status":"attempted"}
    cases.append(event)
    x = np.zeros((6,22)); x[:,8:10] = np.arange(12).reshape(6,2)/50.
    x[:,:2] = [[-.97,1.97],[-.97,1.97],[np.nextafter(-.97,np.inf),np.nextafter(1.97,-np.inf)],
        [0.,0.],[-1.1,2.1],[.2,-.4]]
    commands = np.zeros((6,8)); commands[:,:2] = [[-.7,.7],[.7,-.7],[-.5,.5],[.25,-.25],[0.,0.],[.2,-.3]]
    pv = np.arange(12,dtype=np.float64).reshape(6,2)/100.
    debug = {}
    actual,old = tensor_step50(torch,q_support,T(x),T(pv),T(commands),T(ref),ranges,T(weights),cost,"synthetic_S_step",debug=debug)
    expected = []
    for i in range(6):
        result = q_support.rollout50(core,x[i],pv[i],[commands[i]],ref,guard,weights,cost)
        assert result["available"]
        expected.append(result["terminal_x22"])
    assert np.allclose(actual.detach().numpy(),expected,rtol=0.,atol=2e-14)
    assert np.array_equal(old.numpy(),x[:,8:10])
    assert debug["blocked2"][0].tolist()==[True,True] and debug["blocked2"][4].tolist()==[False,False]
    assert debug["g2"][1].tolist()==[.5,-.5] and debug["g2"][2].tolist()==[-.5,.5]
    assert debug["phi50"][3,24:26].tolist()==[0.,-0.]
    event.update(status="passed",batch_count=6,absolute_tolerance=2e-14)
    event = {"case":"four_step_q_head_autograd_two_directions_previous_v_feedback_and_terminal_label_only","status":"attempted"}
    cases.append(event)
    base = np.zeros((3,22)); base[:,:2] = [[.03,-.02],[.01,.04],[-.04,.02]]
    base[:,8:10] = [[.1,-.1],[-.05,.08],[.02,.03]]
    histories = np.array([[.08,-.07],[-.04,.07],[.01,.02]])
    commands2 = np.zeros((3,4,8)); commands2[:,:,0] = .2; commands2[:,:,1] = -.15
    weights[0,8] = .12; weights[1,9] = -.08
    weights[27,8] = .07; weights[28,9] = .06
    target = T([[.03,-.02],[.01,.04],[-.04,.02]])
    UQ = T(weights[:,:2]); frozen = T(weights[:,2:])
    def small(U, terminal):
        state,previous = T(base),T(histories)
        paths = []
        all_weights = torch.cat((U,frozen),dim=1)
        for i in range(4):
            state,previous = tensor_step50(torch,q_support,state,previous,T(commands2[:,i,:]),T(ref),ranges,
                all_weights,cost,"synthetic_S_gradient")
            paths.append(state)
        loss = torch.mean(((state[:,:2]-terminal)/.12).square())+.01*torch.sum((U-UQ).square())
        return loss,paths,previous
    U = T(weights[:,:2],True)
    loss,paths,previous = small(U,target)
    cost["synthetic_autograd_attempts"] += 1
    gradient = torch.autograd.grad(loss,U)[0]
    cost["synthetic_autograd_returns"] += 1
    d0 = np.zeros((50,2)); d0[26,0]=1.; d0[29,1]=.2
    d1 = np.zeros((50,2)); d1[0,1]=.5; d1[49,0]=-.3
    comparisons = []
    for direction in (d0,d1):
        eps = 1e-6
        plus = float(small(T(weights[:,:2]+eps*direction),target)[0])
        minus = float(small(T(weights[:,:2]-eps*direction),target)[0])
        central = (plus-minus)/(2*eps)
        analytic = float(torch.sum(gradient*T(direction)))
        assert abs(analytic-central) <= 2e-7
        comparisons.append({"epsilon":eps,"analytic":analytic,"central_difference":central,"absolute_tolerance":2e-7})
    altered,other_paths,_ = small(T(weights[:,:2]),target+.5)
    assert all(torch.equal(a,b) for a,b in zip(paths,other_paths)) and float(altered)!=float(loss)
    assert torch.equal(previous,paths[-2][:,8:10]) and np.array_equal(frozen.numpy(),weights[:,2:])
    event.update(status="passed",directional_comparisons=comparisons,terminal_labels_not_recurrent_inputs=True)
    event = {"case":"accepted_snapshot_budget_boundary_and_line_search_failure_fixtures","status":"attempted","fixtures":[]}
    cases.append(event)
    def result(status=0,message="CONVERGENCE"):
        return SimpleNamespace(success=status==0,status=status,message=message,nit=1,nfev=2,njev=2,x=np.ones(100)*9.)
    def normal(fun,x,**kw):
        assert kw["method"]=="L-BFGS-B" and kw["jac"] is True and kw["bounds"] is None and kw["options"]==OPTIMIZER_OPTIONS
        fun(x); kw["callback"](x)
        accepted=x+.001; fun(accepted); kw["callback"](accepted)
        return result()
    def cap(fun,x,**kw):
        fun(x); kw["callback"](x)
        accepted=x+.001; fun(accepted); kw["callback"](accepted)
        while True:
            fun(x+.002)
    def abnormal(fun,x,**kw):
        fun(x); kw["callback"](x)
        return result(2,"ABNORMAL_TERMINATION_IN_LNSRCH")
    class Clock:
        value=0.
        def __call__(self): return self.value
    timer = Clock()
    clock_calls = [0]
    def kernel(U,e):
        return torch.sum((U-.001).square())
    def crossing(U,e):
        clock_calls[0] += 1
        if clock_calls[0] == 2: timer.value=2.
        return kernel(U,e)
    def overrun(fun,x,**kw):
        fun(x)
        raise AssertionError("exit_boundary_not_enforced")
    fixtures = [("normal",normal,kernel,100,120.,time.perf_counter),
        ("hard_call_cap",cap,kernel,4,120.,time.perf_counter),
        ("time_boundary",overrun,crossing,100,1.,timer),
        ("line_search_failed",abnormal,kernel,100,120.,time.perf_counter),
        ("initial_nonfinite",normal,lambda U,e:torch.sum(U*float("nan")),100,120.,time.perf_counter)]
    for name,optimizer,kern,limit,seconds,clock in fixtures:
        root = output/("optimizer_fixture_"+name); root.mkdir()
        paid,record = Counter(),{}
        selected = fit_positions(torch,optimizer,weights.copy(),kern,paid,record,root/"fit_checkpoints"/"seed0",
            max_calls=limit,seconds=seconds,clock=clock)
        cost.update(paid)
        assert paid["objective_calculation_attempts"]==record["objective_calls_started"]
        if name != "initial_nonfinite":
            assert record["accepted_checkpoints"]
        if name=="normal":
            assert selected is not None and np.array_equal(selected[:,:2],weights[:,:2]+.001)
        elif name=="hard_call_cap":
            assert selected is not None and record["budget_exhausted"] and record["objective_calls_started"]==4
            assert np.array_equal(selected[:,:2],weights[:,:2]+.001)
        elif name=="time_boundary":
            assert selected is not None and record["budget_exhausted"] and record["accepted_updates"]==0
            assert record["overrun_seconds"]==1. and np.array_equal(selected,weights)
        elif name=="line_search_failed":
            assert selected is None and record["fit_failed"] and record["optimizer_failed"] and not record["budget_exhausted"]
            assert record["selected_snapshot"] is None and record["accepted_snapshot_retained_as_evidence_only"] is not None
        else:
            assert selected is None and record["fit_failed"] and not record["optimizer_failed"]
            assert not record["accepted_checkpoints"] and not record["optimizer_invocation_attempted"]
        fixture_run = {"status":"failed" if record["fit_failed"] else "completed","self_check":True,"cost":dict(paid),
            "failure":record.get("failure"),**FLAGS}
        write_outputs(root,[{"seed":0,"fit":record}],[],{"status":fixture_run["status"],**FLAGS},fixture_run)
        event["fixtures"].append({"name":name,"fit_status":record["status"],"paid_cost":dict(paid),"selected":selected is not None})
    event["status"] = "passed"


def main_run(args):
    repo,output = Path(args.repo).resolve(),Path(args.output).resolve()
    if any((repo/root).resolve().is_relative_to(output) for root in (C_ROOT,D_ROOT,K_ROOT,Q_ROOT)):
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
    source_verified,status,failure,cmeta,frozen_Q_run = False,"failed",None,None,None
    support,restoration,runtime = None,None,{}
    fit_failures = []
    try:
        sources(repo,args.source_commit,cost,files,args.self_check)
        source_verified = not args.self_check
        restoration,support,core,q_support = load_helpers(repo,cost)
        torch,minimize,runtime = load_runtime(cost)
        if args.self_check:
            self_check(torch,minimize,core,q_support,output,cost,cases)
            status = "self_check_passed"
        else:
            blobs,docs,cmeta = support.read_inputs(repo,inputs,cost,{"files":files})
            frozen_Q_run,Q_payload = restoration.read_Q_inputs(repo,support,inputs,files,cost)
            restored = support.restore_K(core,docs[f"{K_ROOT}/parameters.json"],cost,restorations["K22"])
            models = core.restore_models(docs[f"{D_ROOT}/raw/diagnostics.json"],repo,cost,restorations["D11"])
            before_K = {seed:row["fingerprint"] for seed,row in restored.items()}
            before_D = {seed:model.parameter_fingerprint() for seed,model in models.items()}
            restored_Q = restoration.restore_Q(core,q_support,Q_payload,restored,before_D,cost,restorations["Q22"])
            before_Q = {seed:row["fingerprint"] for seed,row in restored_Q.items()}
            trials,counts = core.parse_trials(blobs[f"{C_ROOT}/trace.jsonl.gz"],cost)
            S_weights = {}
            for seed in SEEDS:
                saved,Q = restored[seed],restored_Q[seed]
                pred_rows = trials[f"seed{seed}_prediction"]
                cal_rows = trials[f"seed{seed}_calibration_sparse"]
                qref,prefix_id = core.prefix_qref(pred_rows)
                if (qref!=saved["qref8"] or tuple(qref[:2])!=models[seed].qref or set(pred_rows)!=set(range(200))
                        or counts.get(f"seed{seed}_prediction")!=100 or counts.get(f"seed{seed}_calibration_sparse")!=400):
                    raise ValueError("fixed_C_population_prefix_qref_or_counts_differ")
                record = {"seed":seed,"predictor":"S22","available":False,"fit":{},
                    "state_order":core.STATE_NAMES,"feature_order":(*core.FEATURE_NAMES,*q_support.QUADRATIC_NAMES),
                    "quadratic_public_scales":q_support.Z_SCALES,"quadratic_pair_order":q_support.QUADRATIC_PAIRS,
                    "qref8":qref,"prediction_prefix_transition_id":prefix_id,
                    "Q22_parameter_fingerprint":before_Q[seed],"K22_parameter_fingerprint":before_K[seed],
                    "D11_parameter_fingerprint":before_D[seed],"frozen_Q_weights50x22":Q["weights"].tolist(),
                    "optimized_heads":[0,1],"frozen_head_indices":list(range(2,22)),
                    "optimized_parameter_count":100,"frozen_parameter_count":1000,
                    "loss_spec":"mean_h(mean_origins_and_two_axes(((q_pred_end-q_actual_end)/.12)^2))+.01*sum((U-UQ)^2)",
                    "optimizer":{"method":"L-BFGS-B","jac":True,"bounds":None,"options":OPTIMIZER_OPTIONS},
                    "hard_objective_call_limit":MAX_OBJECTIVE_CALLS,"time_boundary_seconds":TIME_BOUNDARY_SECONDS}
                parameters.append(record)
                batches = make_training_data(torch,core,seed,cal_rows,saved,Q,models[seed],cost,record)
                UQ = torch.tensor(Q["weights"][:,:2].copy(),dtype=torch.float64,device="cpu")
                frozen_other = torch.tensor(Q["weights"][:,2:].copy(),dtype=torch.float64,device="cpu")
                ref = torch.tensor(qref,dtype=torch.float64,device="cpu")
                ranges = torch.tensor(models[seed].public_guard.public_joint_ranges,dtype=torch.float64,device="cpu")
                def kernel(U,event):
                    return objective_kernel(torch,q_support,U,UQ,frozen_other,batches,ref,ranges,cost,event,"S_training")
                S_weights[seed] = fit_positions(torch,minimize,Q["weights"],kernel,cost,record["fit"],
                    output/"fit_checkpoints"/f"seed{seed}")
                if S_weights[seed] is None:
                    fit_failures.append({"seed":seed,"failure":record["fit"].get("failure"),
                        "budget_exhausted":record["fit"]["budget_exhausted"],"optimizer_failed":record["fit"]["optimizer_failed"]})
                else:
                    record.update(available=True,selected_weights50x22=S_weights[seed].tolist(),
                        parameter_fingerprint=restoration.Q_parameter_fingerprint(core,q_support,qref,S_weights[seed]),
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
                            if predictor == "S22":
                                outcome = (rollout_S(core,q_support,initial,previous_v,requests,saved["qref8"],
                                    models[seed].public_guard,S_weights[seed],cost) if S_weights[seed] is not None else
                                    {"available":False,"reason":"fit_failed_no_S_candidate"})
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
                failure = {"type":"SFitFailed","message":"one_or_more_seeds_have_no_publishable_S_candidate","seeds":fit_failures}
                status = "failed"
            else:
                status = "completed"
    except BaseException as exc:
        failure = {"type":type(exc).__name__,"message":str(exc),"traceback":traceback.format_exc()}
    cost["wall_seconds"],cost["cpu_seconds"] = time.perf_counter()-wall,time.process_time()-cpu
    passed = bool(status=="completed" and gate and gate["passed"])
    all_input_paths = (*support.PINS,*restoration.Q_INPUT_PINS) if support and restoration else ()
    run = {"status":status,"self_check":args.self_check,
        "source":{"commit":args.source_commit,"files":files,"clean_committed_bytes_verified":source_verified},
        "inputs":inputs,"inputs_without_returned_read_record":{name:"unknown_before_read_return" for name in all_input_paths if name not in inputs},
        "original_source_commits":support.COMMITS if support else "unknown_before_support_load",
        "requested_source_commit":args.source_commit,
        "runtime":{"python":platform.python_version(),"numpy":np.__version__,"platform":platform.platform(),**runtime},
        "dependency_note":"preinstalled CPU packages, no download or install in S",
        "original_C_dependencies":cmeta.get("dependencies") if cmeta else "unknown_before_C_metadata_return",
        "source_active_counts":counts,"baseline_restorations":restorations,
        "K22_fingerprints_before":before_K,"K22_fingerprints_after":after_K or "unknown_before_return",
        "D11_fingerprints_before":before_D,"D11_fingerprints_after":after_D or "unknown_before_return",
        "Q22_fingerprints_before":before_Q,"Q22_fingerprints_after":after_Q or "unknown_before_return",
        "frozen_Q_original_cost":frozen_Q_run["cost"] if frozen_Q_run else "unknown_before_Q_run_return",
        "self_check_cases":cases,"fit_failures":fit_failures,"cost":dict(cost),"failure":failure,
        "development_gate_passed":passed,**FLAGS,"timing_excludes":"final output serialization and write"}
    metrics = {"status":status,"groups":groups,"development_gate":gate,"development_gate_passed":passed,**FLAGS}
    write_outputs(output,parameters,predictions,metrics,run)
    print(json.dumps({"status":status,"output":str(output),"cost":dict(cost),"development_gate_passed":passed,
        "failure":failure and {key:failure[key] for key in ("type","message")}}))
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
