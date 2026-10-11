"""P: one raw-scale C400 native ridge with two legal past-request columns."""
from __future__ import annotations

import argparse
from collections import Counter
import gzip
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import platform
import subprocess
import time
import traceback
import numpy as np

SOURCE_PATH = "scripts/develop_guard_request_memory_transition.py"
PROTOCOL_PATH = "docs/GUARD_REQUEST_MEMORY_TRANSITION_DEVELOPMENT_PROTOCOL.md"
SUPPORT_PATH = "scripts/develop_guard_scaled_native_transition.py"
HELPER_PINS = {
    SUPPORT_PATH: "df0833d08e722391f98de1bc2cbf81e2d0a866a3ea65def24e9b216d25787518",
    "docs/GUARD_SCALED_NATIVE_TRANSITION_DEVELOPMENT_PROTOCOL.md": "0027650441b59159b407e21b687057e816c61c127ca6f5f4f06b6ac44b8b87b7",
    "scripts/develop_guard_native_transition.py": "f910bb6fd9f01ebf5fd52426b40b43414e50bebcfe6460cf6132bccb1a2192bb",
    "docs/GUARD_NATIVE_TRANSITION_DEVELOPMENT_PROTOCOL.md": "7be868a3215dc0e29dd6e96f4f19635259fda15e3a54545194513e11a892ce56",
    "src/developmental_physics/__init__.py": "d2ee9d572836752f5f8404bfdf1fca8add0d62b9858f4c6dcd9cf7ddc6c53ea2",
    "src/developmental_physics/guard_lag_pair_model.py": "f3bcedf05b2c956357929e51dcab026ec13311428fa3c6c3383db114da3f7e57",
    "src/developmental_physics/guard_pair_model.py": "2b8ae6f17aa12f1230daf38d8858f24bde3a3c21342e46a5b8fa6e91dc3da3b3",
    "src/developmental_physics/local_pair_model.py": "81e0c9147bbfd7f825f14ad7439e6752c021bc08922abd04589a89b59fc509df",
    "src/developmental_physics/local_model.py": "f51a43c36675980cddd0cbf1fcba576469dd015e0850833ae58ffc32479de2b1",
}
C_ROOT = "results/cpu_validation/2026-10-11_guard_exploration/raw"
D_ROOT = "results/cpu_validation/2026-10-11_guard_lag_offline"
K_ROOT = "results/cpu_validation/2026-10-11_guard_native_transition/raw"
SEEDS, HORIZONS, PREDICTORS = (0, 1, 2), (1, 2, 5, 15), ("P22", "K22", "D11")
RIDGE = .01


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+"\n").encode("utf-8")


def failure_json_safe(value):
    """Keep invalid numeric evidence explicit while strict failure JSON remains writable."""
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
        raise ValueError("canonical_P_path_required")
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
            raise ValueError("exact_P_commit_required")
        if git("rev-parse", "HEAD").decode().strip() != commit or git("status", "--porcelain").strip():
            raise ValueError("clean_exact_P_HEAD_required")
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
    spec = importlib.util.spec_from_file_location("fixed_N_pure_support_for_P", repo/SUPPORT_PATH)
    support = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(support)
    cost["helper_module_load_returns"] += 1
    cost["helper_module_load_attempts"] += 1
    core = support.load_core(repo)
    cost["helper_module_load_returns"] += 1
    return support, core


def parse_trials(blob, cost):
    """Native endpoints for continuity only; never regenerate K fit labels."""
    trials = {f"seed{s}_{kind}": {} for s in SEEDS for kind in ("calibration_sparse", "prediction")}
    counts = Counter()
    with gzip.GzipFile(fileobj=io.BytesIO(blob), mode="rb") as stream:
        for line in stream:
            cost["C_trace_uncompressed_bytes"] += len(line)
            cost["C_trace_json_parse_attempts"] += 1
            row = json.loads(line)
            cost["C_trace_json_parse_returns"] += 1
            seed, kind, step = row.get("seed"), row.get("kind"), row.get("step_index")
            if seed not in SEEDS or kind not in ("calibration_sparse", "prediction"):
                continue
            trial = f"seed{seed}_{kind}"
            limit = 500 if kind == "calibration_sparse" else 200
            phase = "prefix" if type(step) is int and step < 100 else "calibration" if kind == "calibration_sparse" else "prediction"
            if (type(step) is not int or not 0 <= step < limit or row.get("trial_id") != trial or step in trials[trial]
                    or row.get("shared_transition_id") != f"{trial}:{step}" or row.get("phase") != phase):
                raise ValueError("C_selected_trial_phase_index_identity_differs")
            keys = ("joint_position", "joint_velocity", "imu_gyro", "imu_acceleration")
            diagnostics = row.get("diagnostics", {})
            trials[trial][step] = {"trial_id": trial, "seed": seed, "kind": kind, "step_index": step, "phase": phase,
                "shared_transition_id": row["shared_transition_id"], "requested_torque": row.get("requested_torque"),
                "study_abort": row.get("study_abort"), "diagnostics": {k: diagnostics.get(k) for k in ("executed_substeps", "terminated")},
                **{name: {k: row[name][k] for k in keys} for name in ("observation_before", "observation_after")}}
            if step >= 100:
                counts[trial] += 1
    return trials, dict(counts)


def past_request(core, rows, step, cost):
    cost["past_request_history_attempts"] += 1
    previous, current = rows.get(step-1), rows.get(step)
    if (previous is None or current is None or not core.continuous(previous, current)
            or not core.complete(previous) or not core.complete(current) or core.stopped(previous)):
        cost["past_request_history_failures"] += 1
        raise ValueError("legal_continuous_same_trial_request_history_required")
    value = core.vector(previous["requested_torque"], 8)[:2]
    cost["past_request_history_returns"] += 1
    cost["past_requested_scalar_uses"] += 2
    return value, previous["shared_transition_id"]


def features31(core, state, previous_v, request, previous_request, qref, guard, cost):
    cost["P22_memory_feature_attempts"] += 1
    memory = core.finite_array(previous_request, (2,))
    phi, prior = core.feature_and_prior(state, previous_v, request, qref, guard, cost, "P22")
    phi31 = core.finite_array(np.concatenate((phi, memory)), (31,))
    cost["P22_memory_feature_returns"] += 1
    cost["P22_memory_feature_scalar_uses"] += 2
    return phi31, prior


def fit31(core, phi, delta, cost, record):
    cost["fit_attempts"] += 1
    record["status"] = "attempted"
    try:
        phi, delta = core.finite_array(phi, (400, 31)), core.finite_array(delta, (400, 22))
        record.update(phi400x31=phi.tolist(), delta_labels400x22=delta.tolist())
        matrices = {}
        for name, left, right in (("gram", phi.T, phi), ("cross", phi.T, delta)):
            cost[f"fit_{name}_matrix_attempts"] += 1
            cost["fit_logical_multiply_requests"] += left.shape[0]*left.shape[1]*right.shape[1]
            cost["fit_logical_add_requests"] += left.shape[0]*(left.shape[1]-1)*right.shape[1]
            if name == "cross":
                cost["fit_scalar_labels_requested"] += 8800
            try:
                with np.errstate(over="ignore", invalid="ignore"):
                    matrix = left @ right
            except BaseException:
                cost[f"fit_{name}_matrix_failures"] += 1
                raise
            cost[f"fit_{name}_matrix_returns"] += 1
            if name == "cross":
                cost["fit_scalar_labels_returned"] += 8800
            record[f"{name}31x{31 if name == 'gram' else 22}"] = matrix.tolist()
            try:
                matrices[name] = core.finite_array(matrix, (31, 31 if name == "gram" else 22))
            except ValueError:
                cost[f"fit_{name}_validation_failures"] += 1
                raise
        cost["ridge_identity_matrix_entry_additions_requested"] += 961
        with np.errstate(over="ignore", invalid="ignore"):
            normal = matrices["gram"]+RIDGE*np.eye(31)
        record["ridge_normal31x31"] = normal.tolist()
        normal = core.finite_array(normal, (31, 31))
        cost["ridge_identity_matrix_entry_additions_returned"] += 961
        cost["fit_shared_31x31_22rhs_solve_attempts"] += 1
        try:
            weights = np.linalg.solve(normal, matrices["cross"])
        except BaseException:
            cost["fit_shared_31x31_22rhs_solve_failures"] += 1
            raise
        cost["fit_shared_31x31_22rhs_solve_returns"] += 1
        record["weights31x22"] = weights.tolist()
        weights = core.finite_array(weights, (31, 22))
        cost["transition_scalar_coefficients_fitted"] += 682
        cost["transition_heads_published"] += 22
        cost["fit_returns"] += 1
        record["status"] = "returned"
        return weights
    except BaseException as exc:
        cost["fit_failures"] += 1
        record.update(status="failed", failure={"type": type(exc).__name__, "message": str(exc)})
        raise


def rollout31(core, initial, previous_v, previous_request, requests, qref, guard, weights, cost):
    x, previous = core.finite_array(initial, (22,)).copy(), core.finite_array(previous_v, (2,)).copy()
    memory, weights = core.finite_array(previous_request, (2,)).copy(), core.finite_array(weights, (31, 22))
    path, history = [], []
    for request in requests:
        cost["P22_transition_attempts"] += 1
        try:
            old_v, old_request = x[8:10].copy(), core.finite_array(request, (8,))[:2].copy()
            history.append({"past_request2_before": memory.tolist(), "previous_v2_before": previous.tolist(), "known_request2_this_step": old_request.tolist()})
            phi, prior = features31(core, x, previous, request, memory, qref, guard, cost)
            cost["P22_residual_vector_attempts"] += 1
            cost["P22_residual_scalar_head_attempts"] += 22
            with np.errstate(over="ignore", invalid="ignore"):
                residual = phi @ weights
            cost["P22_residual_vector_returns"] += 1
            cost["P22_residual_scalar_head_returns"] += 22
            residual = core.finite_array(residual, (22,))
            with np.errstate(over="ignore", invalid="ignore"):
                x = core.finite_array(prior+residual, (22,)).copy()
            previous, memory = old_v, old_request
            cost["P22_history_advance_scalar_copies"] += 4
            path.append(x.tolist())
            cost["P22_transition_returns"] += 1
        except Exception as exc:
            cost["P22_transition_failures"] += 1
            return {"available": False, "reason": f"{type(exc).__name__}:{exc}", "predicted_path_x22": path, "history_inputs": history}
    return {"available": True, "predicted_path_x22": path, "terminal_x22": x.tolist(), "history_inputs": history,
            "terminal_past_request2": memory.tolist(), "terminal_previous_v2": previous.tolist()}


def summarize(core, records, counts):
    aliases = {"P22": "learned22", "K22": "cold22", "D11": "D11"}
    inverse = {v: k for k, v in aliases.items()}
    groups = core.summarize([{**r, "predictor": aliases[r["predictor"]]} for r in records], counts)
    return [{**g, "predictor": inverse[g["predictor"]]} for g in groups]


def dual_gate(core, groups):
    gates = {}
    for baseline in ("K22", "D11"):
        mapping = {"P22": "learned22", baseline: "D11"}
        gate = core.development_gate([{**g, "predictor": mapping.get(g["predictor"], "cold22")} for g in groups])
        gate.update(candidate_predictor="P22", baseline_predictor=baseline, scope="new_seen_C_common_prediction_request_memory_development_subgate")
        for check in gate["checks"]:
            for row in check["seed_records"]:
                row["P22_rmse"], row[f"{baseline}_rmse"] = row.pop("learned22_rmse"), row.pop("D11_rmse")
        gates[f"P22_vs_{baseline}"] = gate
    return {"scope": "single_seen_C_raw_scale_request_memory_development", "comparisons": gates,
        **{k: all(g[k] for g in gates.values()) for k in ("all_fixed_usable_counts", "evaluated", "passed")},
        "scientific_adoption": False, "c4_scientific_validation": False, "c5_scientific_dependency_released": False}


def write_outputs(output, parameters, predictions, metrics, run):
    encode = failure_json_safe if run["status"] == "failed" else lambda value: value
    payloads = {"parameters.json": json_bytes(encode(parameters)), "metrics.json": json_bytes(encode(metrics)), "run.json": json_bytes(encode(run)),
        "predictions.jsonl": b"".join((json.dumps(encode(r), ensure_ascii=False, allow_nan=False)+"\n").encode() for r in predictions)}
    if run.get("failure"):
        payloads["failure.json"] = json_bytes(encode(run))
    files = {}
    for name, data in payloads.items():
        (output/name).write_bytes(data)
        files[name] = identity(data)
    (output/"manifest.json").write_bytes(json_bytes({"schema_version": 1, "status": run["status"], "scientific_adoption": False, "files": files}))


def self_check(core, output, cost, cases):
    from types import SimpleNamespace
    from unittest.mock import patch
    guard = SimpleNamespace(project=lambda q, u: SimpleNamespace(projected_start_nm=np.clip(u, -.5, .5)))
    def attempt(name):
        event = {"case": name, "status": "attempted"}
        cases.append(event)
        return event
    event = attempt("feature31_and_legal_history_advance")
    weights = np.zeros((31, 22)); weights[29, 8] = weights[30, 9] = 1.
    phi, prior = features31(core, np.zeros(22), (.2, .3), [.7, -.8, 0., 0., 0., 0., 0., 0.], (.9, -.9), np.zeros(8), guard, cost)
    assert tuple(phi[-2:]) == (.9, -.9) and phi.shape == (31,) and prior.shape == (22,)
    result = rollout31(core, np.zeros(22), (.2, .3), (.9, -.9), [[.7, -.8, 0., 0., 0., 0., 0., 0.], [-.2, .3, 0., 0., 0., 0., 0., 0.]], np.zeros(8), guard, weights, cost)
    assert result["available"] and result["history_inputs"][1]["past_request2_before"] == [.7, -.8]
    assert result["history_inputs"][1]["previous_v2_before"] == [0., 0.] and result["terminal_previous_v2"] == result["predicted_path_x22"][0][8:10]
    assert result["terminal_past_request2"] == [-.2, .3]
    event["status"] = "passed"
    event = attempt("missing_history_rejected")
    for function in (lambda: past_request(core, {}, 100, cost), lambda: features31(core, np.zeros(22), (0., 0.), np.zeros(8), None, np.zeros(8), guard, cost)):
        try:
            function()
        except (ValueError, TypeError):
            continue
        raise AssertionError("missing_history_accepted")
    event["status"] = "passed"
    base, delta = np.zeros((400, 29)), np.zeros((400, 22))
    base[:29] = np.eye(29)
    delta[:29] = np.arange(638).reshape(29, 22)/1000.
    phi31 = np.column_stack((base, np.zeros((400, 2))))
    cost["synthetic_design_scalars_generated"] += 12400
    cost["synthetic_label_scalars_generated"] += 8800
    event = attempt("zero_memory_columns_analytic_equivalence")
    record = {}
    weights = fit31(core, phi31, delta, cost, record)
    cost["synthetic_reference_scalar_divisions"] += 638
    expected = delta[:29]/1.01
    assert np.max(np.abs(weights[:29]-expected)) <= 1e-12 and np.array_equal(weights[29:], np.zeros((2, 22)))
    event["status"] = "passed"
    event = attempt("solve_failure_paid_partial_saved")
    paid, partial = Counter(), {}
    try:
        try:
            with patch.object(np.linalg, "solve", side_effect=np.linalg.LinAlgError("synthetic_injected_solve_failure")):
                fit31(core, phi31, delta, paid, partial)
        finally:
            cost.update(paid)
            event["paid_cost"] = dict(paid)
    except np.linalg.LinAlgError as exc:
        fixture = output/"solve_failure_fixture"
        fixture.mkdir()
        run = {"status": "failed", "self_check": True, "cost": dict(paid), "failure": {"type": type(exc).__name__, "message": str(exc)}, "scientific_adoption": False}
        write_outputs(fixture, [{"predictor": "P22", "fit": partial}], [], {"status": "failed"}, run)
        event["saved_fixture_files"] = ["parameters.json", "metrics.json", "run.json", "predictions.jsonl", "failure.json", "manifest.json"]
        assert paid["fit_shared_31x31_22rhs_solve_attempts"] == 1 and paid["fit_shared_31x31_22rhs_solve_failures"] == 1
        assert paid["fit_scalar_labels_returned"] == 8800 and partial["status"] == "failed" and "ridge_normal31x31" in partial
    else:
        raise AssertionError("injected_solve_failure_not_seen")
    event["status"] = "passed"
    event = attempt("failed_nonfinite_payload_serialization_saved")
    fixture = output/"nonfinite_failure_fixture"
    fixture.mkdir()
    failure = {"type": "ValueError", "message": "synthetic_nonfinite_fit_evidence", "traceback": "synthetic_original_failure_location"}
    run = {"status": "failed", "self_check": True, "cost": {}, "failure": failure, "scientific_adoption": False}
    cost["synthetic_nonfinite_payload_serialization_attempts"] += 1
    write_outputs(fixture, [{"predictor": "P22", "fit": {"invalid_numeric_sample": [[float("nan"), float("inf"), float("-inf")]]}}], [], {"status": "failed"}, run)
    cost["synthetic_nonfinite_payload_serialization_returns"] += 1
    event["saved_fixture_files"] = ["parameters.json", "metrics.json", "run.json", "predictions.jsonl", "failure.json", "manifest.json"]
    saved = {}
    for name in ("parameters.json", "failure.json"):
        cost["synthetic_fixture_read_attempts"] += 1
        data = (fixture/name).read_bytes()
        cost["synthetic_fixture_read_returns"] += 1
        cost["synthetic_fixture_raw_bytes"] += len(data)
        cost["synthetic_fixture_json_parse_attempts"] += 1
        saved[name] = json.loads(data)
        cost["synthetic_fixture_json_parse_returns"] += 1
    assert saved["parameters.json"][0]["fit"]["invalid_numeric_sample"] == [[{"nonfinite_float": "NaN"}, {"nonfinite_float": "+Infinity"}, {"nonfinite_float": "-Infinity"}]]
    assert saved["failure.json"]["failure"] == failure
    event["status"] = "passed"


def main_run(args):
    repo, output = Path(args.repo).resolve(), Path(args.output).resolve()
    if any((repo/root).resolve().is_relative_to(output) for root in (C_ROOT, D_ROOT, K_ROOT)):
        raise ValueError("output_must_not_contain_original_inputs")
    output.mkdir(parents=True, exist_ok=False)
    wall, cpu = time.perf_counter(), time.process_time()
    cost = Counter({k: 0 for k in ("fit_attempts", "fit_returns", "fit_failures", "fit_shared_31x31_22rhs_solve_attempts", "fit_shared_31x31_22rhs_solve_returns", "fit_shared_31x31_22rhs_solve_failures", "physics_calls", "physics_substeps", "RLS_updates", "MPC_calls", "K22_refits", "D11_updates")})
    files, inputs, parameters, predictions, cases = {}, {}, [], [], []
    source_verified, cmeta, failure, status, support = False, None, None, "failed", None
    counts, groups, gate, restorations = {}, [], None, {"K22": [], "D11": []}
    before_K, before_D, after_K, after_D = {}, {}, {}, {}
    try:
        sources(repo, args.source_commit, cost, files, args.self_check)
        source_verified = not args.self_check
        support, core = load_helpers(repo, cost)
        if args.self_check:
            self_check(core, output, cost, cases)
            status = "self_check_passed"
        else:
            blobs, docs, cmeta = support.read_inputs(repo, inputs, cost, {"files": files})
            restored = support.restore_K(core, docs[f"{K_ROOT}/parameters.json"], cost, restorations["K22"])
            models = core.restore_models(docs[f"{D_ROOT}/raw/diagnostics.json"], repo, cost, restorations["D11"])
            before_K = {seed: row["fingerprint"] for seed, row in restored.items()}
            before_D = {seed: model.parameter_fingerprint() for seed, model in models.items()}
            trials, counts = parse_trials(blobs[f"{C_ROOT}/trace.jsonl.gz"], cost)
            weights = {}
            for seed in SEEDS:
                saved = restored[seed]
                calibration, prediction = trials[f"seed{seed}_calibration_sparse"], trials[f"seed{seed}_prediction"]
                qref, prefix_id = core.prefix_qref(prediction)
                cref, calibration_prefix_id = core.prefix_qref(calibration)
                if (qref != saved["qref8"] or cref != qref or tuple(qref[:2]) != models[seed].qref
                        or calibration_prefix_id != saved["qref_source_transition_id"]
                        or counts.get(f"seed{seed}_calibration_sparse") != 400 or counts.get(f"seed{seed}_prediction") != 100):
                    raise ValueError("fixed_C_prefix_qref_or_full_counts_differ")
                record = {"seed": seed, "predictor": "P22", "available": False, "fixed_lambda": RIDGE, "state_order": core.STATE_NAMES,
                    "feature_order": (*core.FEATURE_NAMES, "past_requested0_nm", "past_requested1_nm"), "qref8": qref,
                    "qref_source_transition_id": calibration_prefix_id, "prediction_prefix_transition_id": prefix_id,
                    "training_transition_ids": saved["ids"], "training_fixed_count": 400, "training_usable_count": 0, "past_request_extra_clip": None,
                    "past_request_prior_coefficients2x22": [[0.]*22, [0.]*22], "K22_parameter_fingerprint": before_K[seed],
                    "D11_parameter_fingerprint": before_D[seed], "fit": {}}
                parameters.append(record)
                history, history_ids = [], []
                record.update(past_requests400x2=history, past_request_source_transition_ids=history_ids)
                for step in range(100, 500):
                    previous_request, transition_id = past_request(core, calibration, step, cost)
                    history.append(previous_request); history_ids.append(transition_id)
                    record["training_usable_count"] = len(history)
                cost["saved_K_design_scalar_copy_requests"] += 11600
                cost["new_past_request_design_scalar_copy_requests"] += 800
                phi31 = core.finite_array(np.column_stack((saved["phi"], history)), (400, 31))
                cost["saved_K_design_scalar_copy_returns"] += 11600
                cost["new_past_request_design_scalar_copy_returns"] += 800
                weights[seed] = fit31(core, phi31, saved["delta"], cost, record["fit"])
                record.update(available=True, parameter_fingerprint=identity(json_bytes({"qref8": qref, "feature_order": record["feature_order"], "lambda": RIDGE, "weights31x22": weights[seed].tolist()}))["sha256"])
            for seed in SEEDS:
                saved, rows = restored[seed], trials[f"seed{seed}_prediction"]
                for horizon in HORIZONS:
                    for origin in range(101-horizon):
                        common = {"seed": seed, "trial_id": f"seed{seed}_prediction", "origin": origin, "horizon": horizon, "offline_saved_future_requests": True}
                        try:
                            active, past, requests, previous_v = core.window(rows, origin, horizon)
                            previous_request, history_id = past_request(core, rows, 100+origin, cost)
                            observation = active[0]["observation_before"]
                            initial = core.encode_state(observation, saved["qref8"], cost)
                            q, v = core.native(observation)[:2]
                            common.update(initial_x22=initial.tolist(), previous_v2=previous_v, past_requested2=previous_request,
                                past_request_transition_id=history_id, history_transition_ids=[r["shared_transition_id"] for r in past],
                                requested_transition_ids=[r["shared_transition_id"] for r in active], requested_sequence8=requests,
                                source_stopped_at_endpoint=core.stopped(active[-1]))
                        except (KeyError, TypeError, ValueError) as exc:
                            predictions.extend({**common, "predictor": p, "available": False, "reason": f"window_unavailable:{type(exc).__name__}:{exc}"} for p in PREDICTORS)
                            continue
                        current = []
                        for p in PREDICTORS:
                            if p == "P22":
                                outcome = rollout31(core, initial, previous_v, previous_request, requests, saved["qref8"], models[seed].public_guard, weights[seed], cost)
                            elif p == "K22":
                                outcome = core.rollout22(initial, previous_v, requests, saved["qref8"], models[seed].public_guard, saved["weights"], cost, p)
                            else:
                                outcome = core.rollout11(models[seed], q, v, previous_v, requests, cost)
                            record = {**common, "predictor": p, **outcome, "scored": False}
                            predictions.append(record); current.append(record)
                        actual = core.encode_state(active[-1]["observation_after"], saved["qref8"], cost)
                        actual_q, actual_v = core.native(active[-1]["observation_after"])[:2]
                        for record in current:
                            if record["available"]:
                                if record["predictor"] == "D11":
                                    pq, pv = record["terminal_qv"]
                                    errors = {**{str(i): actual_q[i]-pq[i] for i in range(2)}, **{str(8+i): actual_v[i]-pv[i] for i in range(2)}}
                                else:
                                    errors = {str(i): float(actual[i]-record["terminal_x22"][i]) for i in range(22)}
                                if not all(np.isfinite(x) for x in errors.values()):
                                    record.update(available=False, reason="nonfinite_terminal_error")
                                else:
                                    cost["score_scalar_error_calculations"] += len(errors)
                                    record.update(scored=True, actual_endpoint_x22=actual.tolist(), terminal_errors_x22=errors)
            after_K = {seed: support.parameter_fingerprint(core, r["qref8"], r["weights"]) for seed, r in restored.items()}
            after_D = {seed: m.parameter_fingerprint() for seed, m in models.items()}
            if before_K != after_K or before_D != after_D:
                raise ValueError("frozen_K_D_baseline_mutated")
            groups = summarize(core, predictions, counts)
            gate = dual_gate(core, groups)
            status = "completed"
    except BaseException as exc:
        failure = {"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()}
    cost["wall_seconds"], cost["cpu_seconds"] = time.perf_counter()-wall, time.process_time()-cpu
    passed = bool(status == "completed" and gate and gate["passed"])
    flags = {"scientific_adoption": False, "c4_scientific_validation": False, "c5_scientific_dependency_released": False}
    run = {"status": status, "self_check": args.self_check, "source": {"commit": args.source_commit, "files": files, "clean_committed_bytes_verified": source_verified},
        "inputs": inputs, "inputs_without_returned_read_record": {p: "unknown_before_read_return" for p in (support.PINS if support else []) if p not in inputs},
        "original_source_commits": support.COMMITS if support else "unknown_before_support_load", "requested_source_commit": args.source_commit,
        "runtime": {"python": platform.python_version(), "numpy": np.__version__, "platform": platform.platform()},
        "original_C_dependencies": cmeta.get("dependencies") if cmeta else "unknown_before_C_metadata_return", "source_active_counts": counts,
        "baseline_restorations": restorations, "K22_fingerprints_before": before_K, "K22_fingerprints_after": after_K or "unknown_before_return",
        "D11_fingerprints_before": before_D, "D11_fingerprints_after": after_D or "unknown_before_return", "self_check_cases": cases,
        "internal_pure_metric_aliases": {"P22": "learned22", "K22": "cold22", "D11": "D11"}, "cost": dict(cost), "failure": failure,
        "development_gate_passed": passed, **flags, "timing_excludes": "final output serialization and write"}
    metrics = {"status": status, "groups": groups, "development_gate": gate, "development_gate_passed": passed, **flags}
    write_outputs(output, parameters, predictions, metrics, run)
    print(json.dumps({"status": status, "output": str(output), "cost": dict(cost), "development_gate_passed": passed, "failure": failure and {k: failure[k] for k in ("type", "message")}}))
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
