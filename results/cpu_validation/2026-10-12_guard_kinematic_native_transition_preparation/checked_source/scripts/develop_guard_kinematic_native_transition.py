"""R: one frozen-Q trapezoidal replacement of the two controlled q outputs."""
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

SOURCE_PATH = "scripts/develop_guard_kinematic_native_transition.py"
PROTOCOL_PATH = "docs/GUARD_KINEMATIC_NATIVE_TRANSITION_DEVELOPMENT_PROTOCOL.md"
SUPPORT_PATH = "scripts/develop_guard_scaled_native_transition.py"
Q_SOURCE_PATH = "scripts/develop_guard_quadratic_native_transition.py"
Q_PROTOCOL_PATH = "docs/GUARD_QUADRATIC_NATIVE_TRANSITION_DEVELOPMENT_PROTOCOL.md"
C_ROOT = "results/cpu_validation/2026-10-11_guard_exploration/raw"
D_ROOT = "results/cpu_validation/2026-10-11_guard_lag_offline"
K_ROOT = "results/cpu_validation/2026-10-11_guard_native_transition/raw"
Q_ROOT = "results/cpu_validation/2026-10-12_guard_quadratic_native_transition"
Q_COMMIT = "20fa0321c84eb766eeafb9f8d906f554bca60622"
SEEDS, HORIZONS, PREDICTORS = (0,1,2), (1,2,5,15), ("R22","Q22","K22","D11")
RIDGE, HALF_DT = .01, .01
Q_INPUT_PINS = {
    f"{Q_ROOT}/manifest.json": {"bytes":2366,"sha256":"327b38412bab68187c4195d12b4d4047dc6bffeffa0c18e0ea73271b870f25b5"},
    f"{Q_ROOT}/raw/manifest.json": {"bytes":646,"sha256":"5cc976083644a544b3395d028163f53d5e32645cdab7c05c2f10510346ea97f5"},
    f"{Q_ROOT}/raw/run.json": {"bytes":14222,"sha256":"98b0bff624b7feca68000b526306d7f58e8ab33bb3644966392a35c7225db6b1"},
    f"{Q_ROOT}/raw/parameters.json": {"bytes":3403882,"sha256":"6184bc6d89e2c0e2e53c9f09ca7f03a33e7990fe6e2a59f298c13617278ce7f4"},
}
HELPER_PINS = {'scripts/develop_guard_scaled_native_transition.py': 'df0833d08e722391f98de1bc2cbf81e2d0a866a3ea65def24e9b216d25787518', 'docs/GUARD_SCALED_NATIVE_TRANSITION_DEVELOPMENT_PROTOCOL.md': '0027650441b59159b407e21b687057e816c61c127ca6f5f4f06b6ac44b8b87b7', 'scripts/develop_guard_native_transition.py': 'f910bb6fd9f01ebf5fd52426b40b43414e50bebcfe6460cf6132bccb1a2192bb', 'docs/GUARD_NATIVE_TRANSITION_DEVELOPMENT_PROTOCOL.md': '7be868a3215dc0e29dd6e96f4f19635259fda15e3a54545194513e11a892ce56', 'src/developmental_physics/__init__.py': 'd2ee9d572836752f5f8404bfdf1fca8add0d62b9858f4c6dcd9cf7ddc6c53ea2', 'src/developmental_physics/guard_lag_pair_model.py': 'f3bcedf05b2c956357929e51dcab026ec13311428fa3c6c3383db114da3f7e57', 'src/developmental_physics/guard_pair_model.py': '2b8ae6f17aa12f1230daf38d8858f24bde3a3c21342e46a5b8fa6e91dc3da3b3', 'src/developmental_physics/local_pair_model.py': '81e0c9147bbfd7f825f14ad7439e6752c021bc08922abd04589a89b59fc509df', 'src/developmental_physics/local_model.py': 'f51a43c36675980cddd0cbf1fcba576469dd015e0850833ae58ffc32479de2b1', 'scripts/develop_guard_quadratic_native_transition.py': '6a8109ed9ba68b61674f9744ac0ea4ffce421ff8b4400abfe7cc081b5c16a147', 'docs/GUARD_QUADRATIC_NATIVE_TRANSITION_DEVELOPMENT_PROTOCOL.md': '77cb47c42efad889f4d15cf64207b528ab2c7e29908d55d3f16441b0b7a6c5d3'}


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
        raise ValueError("canonical_R_path_required")
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
            raise ValueError("exact_R_commit_required")
        if git("rev-parse", "HEAD").decode().strip() != commit or git("status", "--porcelain").strip():
            raise ValueError("clean_exact_R_HEAD_required")
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
    spec = importlib.util.spec_from_file_location("fixed_N_pure_support_for_R", repo/SUPPORT_PATH)
    support = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(support)
    cost["helper_module_load_returns"] += 1
    cost["helper_module_load_attempts"] += 1
    core = support.load_core(repo)
    cost["helper_module_load_returns"] += 1
    cost["helper_module_load_attempts"] += 1
    spec = importlib.util.spec_from_file_location("fixed_Q_pure_step_for_R", repo/Q_SOURCE_PATH)
    q_support = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(q_support)
    cost["helper_module_load_returns"] += 1
    return support, core, q_support


def read_Q_inputs(repo, support, inputs, source_files, cost):
    docs = {}
    for name, expected in Q_INPUT_PINS.items():
        cost["input_file_read_attempts"] += 1
        data = (repo/name).read_bytes()
        cost["input_file_read_returns"] += 1
        cost["input_raw_bytes"] += len(data)
        cost["input_hash_bytes"] += len(data)
        inputs[name] = identity(data)
        if inputs[name] != expected:
            raise ValueError(f"frozen_Q_input_differs:{name}")
        cost["json_parse_attempts"] += 1
        docs[name] = json.loads(data)
        cost["json_parse_returns"] += 1
    root, raw, run, parameters = (docs[f"{Q_ROOT}/{name}"] for name in ("manifest.json","raw/manifest.json","raw/run.json","raw/parameters.json"))
    if raw.get("status") != "completed" or raw.get("scientific_adoption") is not False:
        raise ValueError("frozen_Q_raw_status_differs")
    for name in ("raw/manifest.json","raw/run.json","raw/parameters.json"):
        if not support.same_identity(root["files"][name], inputs[f"{Q_ROOT}/{name}"]):
            raise ValueError("frozen_Q_root_manifest_binding_differs")
    for name in ("run.json","parameters.json"):
        if not support.same_identity(raw["files"][name], inputs[f"{Q_ROOT}/raw/{name}"]):
            raise ValueError("frozen_Q_raw_manifest_binding_differs")
    if (run.get("status") != "completed" or run.get("self_check") is not False
            or run["source"].get("commit") != Q_COMMIT or run["source"].get("clean_committed_bytes_verified") is not True
            or run.get("original_source_commits") != support.COMMITS):
        raise ValueError("frozen_Q_clean_source_identity_differs")
    for name in support.PINS:
        if not support.same_identity(run["inputs"][name], inputs[name]):
            raise ValueError("frozen_Q_original_C_D_K_inputs_differ")
    for name in HELPER_PINS:
        if not support.same_identity(run["source"]["files"][name], source_files[name]):
            raise ValueError("frozen_Q_pure_source_identity_differs")
    return run, parameters


def Q_parameter_fingerprint(core, q_support, qref, weights):
    return identity(q_support.json_bytes({"qref8":qref,"feature_order":(*core.FEATURE_NAMES,*q_support.QUADRATIC_NAMES),
        "lambda":RIDGE,"quadratic_phi29_indices":q_support.Z_PHI_INDICES,"quadratic_public_scales":q_support.Z_SCALES,
        "quadratic_pair_order":q_support.QUADRATIC_PAIRS,"weights50x22":weights.tolist()}))["sha256"]


def restore_Q(core, q_support, payload, restored_K, before_D, cost, records):
    if not isinstance(payload,list) or len(payload) != 3:
        raise ValueError("exact_three_frozen_Q_records_required")
    if core.DT != .02 or q_support.RIDGE != RIDGE:
        raise ValueError("fixed_Q_interval_or_lambda_differs")
    restored = {}
    for seed in SEEDS:
        event = {"seed":seed,"attempted":True,"returned":False,"refit":False}
        records.append(event)
        cost["Q22_restoration_attempts"] += 1
        try:
            matches = [row for row in payload if row.get("seed") == seed]
            if len(matches) != 1:
                raise ValueError("one_frozen_Q_record_per_seed_required")
            row, saved = matches[0], restored_K[seed]
            if (row.get("predictor") != "Q22" or row.get("available") is not True or row.get("fixed_lambda") != RIDGE
                    or row.get("state_order") != list(core.STATE_NAMES)
                    or row.get("feature_order") != [*core.FEATURE_NAMES,*q_support.QUADRATIC_NAMES]
                    or row.get("quadratic_z_names") != list(q_support.Z_NAMES)
                    or row.get("quadratic_phi29_indices") != list(q_support.Z_PHI_INDICES)
                    or row.get("quadratic_public_scales") != list(q_support.Z_SCALES)
                    or row.get("quadratic_pair_order") != [list(pair) for pair in q_support.QUADRATIC_PAIRS]
                    or row.get("quadratic_prior_coefficients") != "all_zero_21x22"
                    or row.get("training_fixed_count") != 400 or row.get("training_usable_count") != 400
                    or row.get("training_source_active_count") != 400 or row.get("training_transition_ids") != saved["ids"]
                    or row.get("qref_source_transition_id") != saved["qref_source_transition_id"]
                    or row.get("prediction_prefix_transition_id") != f"seed{seed}_prediction:99"
                    or row.get("K22_parameter_fingerprint") != saved["fingerprint"]
                    or row.get("D11_parameter_fingerprint") != before_D[seed]
                    or row.get("fit",{}).get("status") != "returned"):
                raise ValueError("fixed_Q_schema_mapping_counts_IDs_or_baselines_differ")
            qref = core.vector(row["qref8"],8)
            if qref != saved["qref8"]:
                raise ValueError("frozen_Q_K_qref_differs")
            weights = core.finite_array(row["fit"]["weights50x22"],(50,22)).copy()
            fingerprint = Q_parameter_fingerprint(core,q_support,qref,weights)
            if fingerprint != row.get("parameter_fingerprint"):
                raise ValueError("frozen_Q_parameter_fingerprint_differs")
            cost["Q22_saved_weight_scalars_validated"] += 1100
            restored[seed] = {"qref8":qref,"weights":weights,"fingerprint":fingerprint}
            event.update(returned=True,parameter_fingerprint=fingerprint,training_provenance_rows=400,training_provenance_scalar_labels=8800)
            cost["Q22_restoration_returns"] += 1
        except BaseException as exc:
            cost["Q22_restoration_failures"] += 1
            event["failure"] = {"type":type(exc).__name__,"message":str(exc)}
            raise
    return restored


def q_step50(core, q_support, state, previous_v, request, qref, guard, weights, cost, record):
    paid = Counter()
    try:
        result = q_support.rollout50(core,state,previous_v,[request],qref,guard,weights,paid)
        record["frozen_Q_one_step"] = result
        if not result["available"]:
            raise ValueError("frozen_Q_step_unavailable:"+result["reason"])
        return core.finite_array(result["terminal_x22"],(22,)), core.finite_array(result["terminal_previous_v2"],(2,))
    finally:
        for key,value in paid.items():
            mapped = key.replace("Q22_transition_","R22_Q_candidate_",1) if key.startswith("Q22_transition_") else key.replace("Q22_","R22_",1) if key.startswith("Q22_") else key
            cost[mapped] += value
        record["paid_Q_step_cost"] = dict(paid)


def kinematic_override(core, old_state, Q_candidate, cost, record=None):
    evidence = record if record is not None else {}
    cost["R22_kinematic_override_attempts"] += 1
    try:
        old, candidate = core.finite_array(old_state,(22,)), core.finite_array(Q_candidate,(22,))
        evidence["ignored_Q_q2"] = candidate[:2].tolist()
        cost["R22_ignored_Q_position_outputs"] += 2
        cost["R22_kinematic_scalar_additions_requested"] += 4
        cost["R22_kinematic_scalar_multiplications_requested"] += 2
        with np.errstate(over="ignore",invalid="ignore"):
            replacement = old[:2]+HALF_DT*(old[8:10]+candidate[8:10])
        cost["R22_kinematic_scalar_additions_returned"] += 4
        cost["R22_kinematic_scalar_multiplications_returned"] += 2
        evidence["replacement_q2"] = replacement.tolist()
        replacement = core.finite_array(replacement,(2,))
        result = candidate.copy()
        cost["R22_position_overwrites_requested"] += 2
        result[:2] = replacement
        result = core.finite_array(result,(22,))
        cost["R22_position_overwrites_returned"] += 2
        cost["R22_kinematic_override_returns"] += 1
        return result
    except BaseException as exc:
        cost["R22_kinematic_override_failures"] += 1
        evidence["failure"] = {"type":type(exc).__name__,"message":str(exc)}
        raise


def rollout_R(core,q_support,initial,previous_v,requests,qref,guard,weights,cost):
    x, previous = core.finite_array(initial,(22,)).copy(), core.finite_array(previous_v,(2,)).copy()
    weights = core.finite_array(weights,(50,22))
    path,history = [],[]
    for request in requests:
        cost["R22_transition_attempts"] += 1
        record = {"current_x22_before":x.tolist(),"previous_v2_before":previous.tolist()}
        history.append(record)
        try:
            candidate, old_v = q_step50(core,q_support,x,previous,request,qref,guard,weights,cost,record)
            x = kinematic_override(core,x,candidate,cost,record)
            previous = old_v.copy()
            path.append(x.tolist())
            cost["R22_transition_returns"] += 1
        except Exception as exc:
            cost["R22_transition_failures"] += 1
            return {"available":False,"reason":f"{type(exc).__name__}:{exc}","predicted_path_x22":path,"history_inputs":history}
    return {"available":True,"predicted_path_x22":path,"terminal_x22":x.tolist(),"history_inputs":history,"terminal_previous_v2":previous.tolist(),"ignored_Q_position_heads":[0,1]}


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
        mapping = {"R22":"learned22",baseline:"D11"}
        gate = core.development_gate([{**group,"predictor":mapping.get(group["predictor"],"cold22")} for group in groups])
        gate.update(candidate_predictor="R22",baseline_predictor=baseline,scope="new_seen_C_common_prediction_kinematic_development_subgate")
        for check in gate["checks"]:
            for row in check["seed_records"]:
                row["R22_rmse"],row[f"{baseline}_rmse"] = row.pop("learned22_rmse"),row.pop("D11_rmse")
        gates[f"R22_vs_{baseline}"] = gate
    return {"scope":"single_seen_C_frozen_Q_kinematic_development","Q22_descriptive_only":True,"comparisons":gates,
        **{key:all(g[key] for g in gates.values()) for key in ("all_fixed_usable_counts","evaluated","passed")},
        "scientific_adoption":False,"c4_scientific_validation":False,"c5_scientific_dependency_released":False}


def self_check(core,output,cost,cases):
    from unittest.mock import patch
    def attempt(name):
        event = {"case":name,"status":"attempted"}
        cases.append(event)
        return event
    old = np.zeros(22); old[:2] = (.02,-.04); old[8:10] = (.5,-.25)
    candidate = old.copy(); candidate[:2] = (999.,-777.)
    cost["synthetic_state_fixture_scalars_generated"] += 44
    event = attempt("equal_endpoint_velocities_reduce_to_Euler")
    result = kinematic_override(core,old,candidate,cost)
    assert np.allclose(result[:2],[.03,-.045],rtol=0.,atol=1e-15)
    event["status"] = "passed"
    event = attempt("changed_endpoint_velocities_trapezoidal_q")
    old[8:10], candidate[8:10] = (.2,-.3),(.8,.1)
    result = kinematic_override(core,old,candidate,cost)
    assert np.allclose(result[:2],[.03,-.042],rtol=0.,atol=1e-15)
    event["status"] = "passed"
    event = attempt("ignored_two_Q_position_heads_other20_preserved")
    changed = candidate.copy(); changed[:2] = (-333.,444.)
    cost["synthetic_state_fixture_scalars_copied"] += 22
    altered = kinematic_override(core,old,changed,cost)
    assert np.array_equal(altered,result) and np.array_equal(altered[2:],candidate[2:])
    event["status"] = "passed"
    event = attempt("two_step_self_closure_old_current_v_with_mock_Q_only")
    weights = np.zeros((50,22))
    cost["synthetic_weight_placeholder_scalars_generated"] += 1100
    seen = []
    def mock_step(core,q_support,state,previous_v,request,qref,guard,weights,cost,record):
        cost["synthetic_mock_Q_step_attempts"] += 1
        seen.append({"state":state.tolist(),"previous_v":previous_v.tolist()})
        mock = state.copy(); mock[:2] = (999.,-777.)
        cost["synthetic_mock_Q_velocity_scalar_additions"] += 2
        mock[8:10] += (1.,-.5)
        cost["synthetic_mock_Q_gyro_scalar_additions"] += 1
        mock[16] += 3.
        cost["synthetic_mock_Q_step_returns"] += 1
        return mock,state[8:10].copy()
    with patch(__name__+".q_step50",side_effect=mock_step):
        result = rollout_R(core,None,old,(.1,.15),[np.zeros(8),np.zeros(8)],np.zeros(8),None,weights,cost)
    assert result["available"] and len(result["predicted_path_x22"]) == 2
    assert seen[1]["state"] == result["predicted_path_x22"][0] and seen[1]["previous_v"] == old[8:10].tolist()
    assert result["terminal_previous_v2"] == result["predicted_path_x22"][0][8:10]
    assert np.allclose(result["predicted_path_x22"][0][:2],[.034,-.051],rtol=0.,atol=1e-15)
    assert np.allclose(result["predicted_path_x22"][1][:2],[.068,-.072],rtol=0.,atol=1e-15)
    assert result["predicted_path_x22"][1][16] == 6. and all(len(row) == 22 for row in result["predicted_path_x22"])
    event["status"] = "passed"


def write_outputs(output, parameters, predictions, metrics, run):
    encode = failure_json_safe if run["status"] == "failed" else lambda value: value
    payloads = {"parameters.json": json_bytes(encode(parameters)), "metrics.json": json_bytes(encode(metrics)), "run.json": json_bytes(encode(run)),
        "predictions.jsonl": b"".join((json.dumps(failure_json_safe(row) if row.get("available") is False else encode(row), ensure_ascii=False, allow_nan=False)+"\n").encode() for row in predictions)}
    if run.get("failure"):
        payloads["failure.json"] = json_bytes(encode(run))
    files = {}
    for name, data in payloads.items():
        (output/name).write_bytes(data)
        files[name] = identity(data)
    (output/"manifest.json").write_bytes(json_bytes({"schema_version": 1, "status": run["status"], "scientific_adoption": False, "files": files}))

def main_run(args):
    repo, output = Path(args.repo).resolve(), Path(args.output).resolve()
    if any((repo/root).resolve().is_relative_to(output) for root in (C_ROOT, D_ROOT, K_ROOT, Q_ROOT)):
        raise ValueError("output_must_not_contain_original_inputs")
    output.mkdir(parents=True, exist_ok=False)
    wall, cpu = time.perf_counter(), time.process_time()
    cost = Counter({key: 0 for key in ("fit_attempts", "fit_returns", "fit_failures", "fit_shared_50x50_22rhs_solve_attempts", "fit_shared_50x50_22rhs_solve_returns", "fit_shared_50x50_22rhs_solve_failures", "fit_scalar_labels_requested", "fit_scalar_labels_returned", "transition_scalar_coefficients_fitted", "Q22_refits", "physics_calls", "physics_substeps", "RLS_updates", "MPC_calls", "K22_refits", "D11_updates")})
    files, inputs, parameters, predictions, cases = {}, {}, [], [], []
    source_verified, cmeta, failure, status, support = False, None, None, "failed", None
    counts, groups, gate, restorations = {}, [], None, {"K22": [], "D11": []}
    before_K, before_D, after_K, after_D = {}, {}, {}, {}
    before_Q, after_Q, frozen_Q_run = {}, {}, None
    restorations["Q22"] = []
    try:
        sources(repo, args.source_commit, cost, files, args.self_check)
        source_verified = not args.self_check
        support, core, q_support = load_helpers(repo, cost)
        if args.self_check:
            self_check(core, output, cost, cases)
            status = "self_check_passed"
        else:
            blobs, docs, cmeta = support.read_inputs(repo, inputs, cost, {"files": files})
            frozen_Q_run, Q_payload = read_Q_inputs(repo,support,inputs,files,cost)
            restored = support.restore_K(core, docs[f"{K_ROOT}/parameters.json"], cost, restorations["K22"])
            models = core.restore_models(docs[f"{D_ROOT}/raw/diagnostics.json"], repo, cost, restorations["D11"])
            before_K = {seed: row["fingerprint"] for seed, row in restored.items()}
            before_D = {seed: model.parameter_fingerprint() for seed, model in models.items()}
            restored_Q = restore_Q(core,q_support,Q_payload,restored,before_D,cost,restorations["Q22"])
            before_Q = {seed:row["fingerprint"] for seed,row in restored_Q.items()}
            trials, counts = support.parse_prediction(core, blobs[f"{C_ROOT}/trace.jsonl.gz"], cost)
            for seed in SEEDS:
                saved = restored[seed]
                qref,prefix_id = core.prefix_qref(trials[f"seed{seed}_prediction"])
                if qref != saved["qref8"] or tuple(qref[:2]) != models[seed].qref or counts.get(f"seed{seed}_prediction") != 100:
                    raise ValueError("fixed_C_prediction_prefix_qref_or_full_counts_differ")
                parameters.append({"seed":seed,"predictor":"R22","available":True,"refit":False,"new_scalar_labels_fitted":0,
                    "state_order":core.STATE_NAMES,"feature_order":(*core.FEATURE_NAMES,*q_support.QUADRATIC_NAMES),
                    "quadratic_public_scales":q_support.Z_SCALES,"quadratic_pair_order":q_support.QUADRATIC_PAIRS,
                    "qref8":qref,"prediction_prefix_transition_id":prefix_id,"training_transition_ids":saved["ids"],
                    "Q22_parameter_fingerprint":before_Q[seed],"K22_parameter_fingerprint":before_K[seed],"D11_parameter_fingerprint":before_D[seed],
                    "frozen_Q_weights50x22":restored_Q[seed]["weights"].tolist(),"ignored_Q_position_heads":[0,1],
                    "kinematic_replacement":"old_q2 + .01 * (old_v2 + next_Q_v2)","half_dt_seconds":HALF_DT})
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
                            if predictor == "R22":
                                outcome = rollout_R(core,q_support,initial,previous_v,requests,saved["qref8"],models[seed].public_guard,restored_Q[seed]["weights"],cost)
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
            after_K = {seed: support.parameter_fingerprint(core, row["qref8"], row["weights"]) for seed, row in restored.items()}
            after_D = {seed: model.parameter_fingerprint() for seed, model in models.items()}
            after_Q = {seed:Q_parameter_fingerprint(core,q_support,row["qref8"],row["weights"]) for seed,row in restored_Q.items()}
            if before_K != after_K or before_D != after_D or before_Q != after_Q:
                raise ValueError("frozen_Q_K_D_baseline_mutated")
            groups = summarize(core, predictions, counts)
            gate = dual_gate(core, groups)
            status = "completed"
    except BaseException as exc:
        failure = {"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()}
    cost["wall_seconds"], cost["cpu_seconds"] = time.perf_counter()-wall, time.process_time()-cpu
    passed = bool(status == "completed" and gate and gate["passed"])
    flags = {"scientific_adoption": False, "c4_scientific_validation": False, "c5_scientific_dependency_released": False}
    run = {"status": status, "self_check": args.self_check,
        "source": {"commit": args.source_commit, "files": files, "clean_committed_bytes_verified": source_verified},
        "inputs": inputs, "inputs_without_returned_read_record": {path: "unknown_before_read_return" for path in ((*support.PINS,*Q_INPUT_PINS) if support else Q_INPUT_PINS) if path not in inputs},
        "original_source_commits": support.COMMITS if support else "unknown_before_support_load", "requested_source_commit": args.source_commit,
        "runtime": {"python": platform.python_version(), "numpy": np.__version__, "platform": platform.platform()},
        "original_C_dependencies": cmeta.get("dependencies") if cmeta else "unknown_before_C_metadata_return", "source_active_counts": counts,
        "baseline_restorations": restorations, "K22_fingerprints_before": before_K, "K22_fingerprints_after": after_K or "unknown_before_return",
        "D11_fingerprints_before": before_D, "D11_fingerprints_after": after_D or "unknown_before_return", "self_check_cases": cases,
        "Q22_fingerprints_before":before_Q,"Q22_fingerprints_after":after_Q or "unknown_before_return",
        "frozen_Q_original_cost":frozen_Q_run.get("cost") if frozen_Q_run else "unknown_before_Q_run_return",
        "internal_pure_metric_aliases":{"candidate":"R22_to_learned22","chosen_baseline":"to_D11","others":"to_unused_cold22"},
        "Q_one_step_cost_alias":{"Q22_transition":"R22_Q_candidate","other_Q22":"R22"}, "cost": dict(cost), "failure": failure,
        "development_gate_passed": passed, **flags, "timing_excludes": "final output serialization and write"}
    metrics = {"status": status, "groups": groups, "development_gate": gate, "development_gate_passed": passed, **flags}
    write_outputs(output, parameters, predictions, metrics, run)
    print(json.dumps({"status": status, "output": str(output), "cost": dict(cost), "development_gate_passed": passed,
        "failure": failure and {key: failure[key] for key in ("type", "message")}}))
    return 0 if failure is None else 1

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".")
    parser.add_argument("--source-commit")
    parser.add_argument("--output", required=True)
    parser.add_argument("--self-check", action="store_true")
    args = parser.parse_args()
    if not args.self_check and not args.source_commit:
        parser.error("--source-commit required for formal execution")
    raise SystemExit(main_run(args))
