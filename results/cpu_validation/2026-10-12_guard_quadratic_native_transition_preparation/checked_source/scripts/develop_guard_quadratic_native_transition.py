"""Q: one fixed public-scale local quadratic extension of frozen K C400."""
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

SOURCE_PATH = "scripts/develop_guard_quadratic_native_transition.py"
PROTOCOL_PATH = "docs/GUARD_QUADRATIC_NATIVE_TRANSITION_DEVELOPMENT_PROTOCOL.md"
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
SEEDS, HORIZONS, PREDICTORS = (0, 1, 2), (1, 2, 5, 15), ("Q22", "K22", "D11")
RIDGE = .01
Z_PHI_INDICES = (0, 1, 8, 9, 22, 23)
Z_SCALES = (.12, .12, 1., 1., .5, .5)
Z_NAMES = ("(q0-qref0)/.12", "(q1-qref1)/.12", "v0/1", "v1/1", "startG0/.5", "startG1/.5")
QUADRATIC_PAIRS = tuple((i, j) for i in range(6) for j in range(i, 6))
QUADRATIC_NAMES = tuple(f"z{i}*z{j}" for i, j in QUADRATIC_PAIRS)


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
        raise ValueError("canonical_Q_path_required")
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
            raise ValueError("exact_Q_commit_required")
        if git("rev-parse", "HEAD").decode().strip() != commit or git("status", "--porcelain").strip():
            raise ValueError("clean_exact_Q_HEAD_required")
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
    spec = importlib.util.spec_from_file_location("fixed_N_pure_support_for_Q", repo/SUPPORT_PATH)
    support = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(support)
    cost["helper_module_load_returns"] += 1
    cost["helper_module_load_attempts"] += 1
    core = support.load_core(repo)
    cost["helper_module_load_returns"] += 1
    return support, core


def append_quadratic50(core, phi29, cost, owner, record=None):
    """One shared saved-design/current-prediction mapping; phi29 stays unchanged."""
    cost[f"{owner}_quadratic_mapping_attempts"] += 1
    evidence = record if record is not None else {}
    evidence["status"] = "attempted"
    try:
        phi = core.finite_array(phi29, (29,))
        evidence["phi29"] = phi.tolist()
        cost[f"{owner}_scale_scalar_divisions_requested"] += 6
        with np.errstate(over="ignore", invalid="ignore"):
            z = phi[np.asarray(Z_PHI_INDICES)]/np.asarray(Z_SCALES)
        cost[f"{owner}_scale_scalar_divisions_returned"] += 6
        evidence["normalized_z6"] = z.tolist()
        z = core.finite_array(z, (6,))
        cost[f"{owner}_quadratic_scalar_products_requested"] += 21
        with np.errstate(over="ignore", invalid="ignore"):
            terms = np.asarray([z[i]*z[j] for i, j in QUADRATIC_PAIRS])
        cost[f"{owner}_quadratic_scalar_products_returned"] += 21
        evidence["quadratic21"] = terms.tolist()
        terms = core.finite_array(terms, (21,))
        cost[f"{owner}_feature_scalar_materializations_requested"] += 50
        if owner == "Q_training":
            cost["saved_K_design_scalar_copy_requests"] += 29
        phi50 = np.concatenate((phi, terms))
        evidence["phi50"] = phi50.tolist()
        phi50 = core.finite_array(phi50, (50,))
        cost[f"{owner}_feature_scalar_materializations_returned"] += 50
        if owner == "Q_training":
            cost["saved_K_design_scalar_copy_returns"] += 29
        cost[f"{owner}_quadratic_mapping_returns"] += 1
        evidence["status"] = "returned"
        return phi50
    except BaseException as exc:
        cost[f"{owner}_quadratic_mapping_failures"] += 1
        evidence.update(status="failed", failure={"type": type(exc).__name__, "message": str(exc)})
        raise


def features50(core, state, previous_v, request, qref, guard, cost, record=None):
    phi29, prior = core.feature_and_prior(state, previous_v, request, qref, guard, cost, "Q22")
    return append_quadratic50(core, phi29, cost, "Q22", record), prior


def build_design50(core, saved_phi, cost, record, parameter_record):
    rows = []
    record.update(status="design_building", phi400x50=rows)
    try:
        base = core.finite_array(saved_phi, (400, 29))
        for index, phi29 in enumerate(base):
            partial = {"row_index": index, "training_transition_id": parameter_record["training_transition_ids"][index]}
            record["last_design_mapping"] = partial
            phi50 = append_quadratic50(core, phi29, cost, "Q_training", partial)
            rows.append(phi50.tolist())
            parameter_record["training_usable_count"] = len(rows)
        record["status"] = "design_returned"
        return core.finite_array(rows, (400, 50))
    except BaseException as exc:
        record.update(status="design_failed", failure={"type": type(exc).__name__, "message": str(exc)})
        raise


def fit50(core, phi, delta, cost, record):
    cost["fit_attempts"] += 1
    record["status"] = "attempted"
    try:
        phi, delta = core.finite_array(phi, (400, 50)), core.finite_array(delta, (400, 22))
        record.update(phi400x50=phi.tolist(), delta_labels400x22=delta.tolist())
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
            record[f"{name}50x{50 if name == 'gram' else 22}"] = matrix.tolist()
            try:
                matrices[name] = core.finite_array(matrix, (50, 50 if name == "gram" else 22))
            except ValueError:
                cost[f"fit_{name}_validation_failures"] += 1
                raise
        cost["ridge_identity_matrix_entry_additions_requested"] += 2500
        with np.errstate(over="ignore", invalid="ignore"):
            normal = matrices["gram"]+RIDGE*np.eye(50)
        record["ridge_normal50x50"] = normal.tolist()
        normal = core.finite_array(normal, (50, 50))
        cost["ridge_identity_matrix_entry_additions_returned"] += 2500
        cost["fit_shared_50x50_22rhs_solve_attempts"] += 1
        try:
            weights = np.linalg.solve(normal, matrices["cross"])
        except BaseException:
            cost["fit_shared_50x50_22rhs_solve_failures"] += 1
            raise
        cost["fit_shared_50x50_22rhs_solve_returns"] += 1
        record["weights50x22"] = weights.tolist()
        weights = core.finite_array(weights, (50, 22))
        cost["transition_scalar_coefficients_fitted"] += 1100
        cost["transition_heads_published"] += 22
        cost["fit_returns"] += 1
        record["status"] = "returned"
        return weights
    except BaseException as exc:
        cost["fit_failures"] += 1
        record.update(status="failed", failure={"type": type(exc).__name__, "message": str(exc)})
        raise


def rollout50(core, initial, previous_v, requests, qref, guard, weights, cost):
    x, previous = core.finite_array(initial, (22,)).copy(), core.finite_array(previous_v, (2,)).copy()
    weights = core.finite_array(weights, (50, 22))
    path, history = [], []
    for request in requests:
        cost["Q22_transition_attempts"] += 1
        mapping, partial = {}, {}
        try:
            old_v = x[8:10].copy()
            history.append({"previous_v2_before": previous.tolist(), "current_x22_before": x.tolist()})
            phi, prior = features50(core, x, previous, request, qref, guard, cost, mapping)
            cost["Q22_residual_vector_attempts"] += 1
            cost["Q22_residual_scalar_head_attempts"] += 22
            with np.errstate(over="ignore", invalid="ignore"):
                residual = phi @ weights
            cost["Q22_residual_vector_returns"] += 1
            cost["Q22_residual_scalar_head_returns"] += 22
            partial["residual_x22"] = residual.tolist()
            residual = core.finite_array(residual, (22,))
            with np.errstate(over="ignore", invalid="ignore"):
                candidate = prior+residual
            partial["candidate_x22"] = candidate.tolist()
            x = core.finite_array(candidate, (22,)).copy()
            previous = old_v
            cost["Q22_history_advance_scalar_copies"] += 2
            path.append(x.tolist())
            cost["Q22_transition_returns"] += 1
        except Exception as exc:
            cost["Q22_transition_failures"] += 1
            return {"available": False, "reason": f"{type(exc).__name__}:{exc}", "predicted_path_x22": path,
                "history_inputs": history, "failed_mapping": mapping, "failed_transition": partial}
    return {"available": True, "predicted_path_x22": path, "terminal_x22": x.tolist(),
        "history_inputs": history, "terminal_previous_v2": previous.tolist()}


def summarize(core, records, counts):
    aliases = {"Q22": "learned22", "K22": "cold22", "D11": "D11"}
    inverse = {v: k for k, v in aliases.items()}
    groups = core.summarize([{**r, "predictor": aliases[r["predictor"]]} for r in records], counts)
    return [{**g, "predictor": inverse[g["predictor"]]} for g in groups]


def dual_gate(core, groups):
    gates = {}
    for baseline in ("K22", "D11"):
        mapping = {"Q22": "learned22", baseline: "D11"}
        gate = core.development_gate([{**g, "predictor": mapping.get(g["predictor"], "cold22")} for g in groups])
        gate.update(candidate_predictor="Q22", baseline_predictor=baseline, scope="new_seen_C_common_prediction_quadratic_development_subgate")
        for check in gate["checks"]:
            for row in check["seed_records"]:
                row["Q22_rmse"], row[f"{baseline}_rmse"] = row.pop("learned22_rmse"), row.pop("D11_rmse")
        gates[f"Q22_vs_{baseline}"] = gate
    return {"scope": "single_seen_C_fixed_public_scale_quadratic_development", "comparisons": gates,
        **{key: all(g[key] for g in gates.values()) for key in ("all_fixed_usable_counts", "evaluated", "passed")},
        "scientific_adoption": False, "c4_scientific_validation": False, "c5_scientific_dependency_released": False}


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


def self_check(core, output, cost, cases):
    from types import SimpleNamespace
    from unittest.mock import patch
    guard = SimpleNamespace(project=lambda q, u: SimpleNamespace(projected_start_nm=np.clip(u, -.5, .5)))
    def attempt(name):
        event = {"case": name, "status": "attempted"}
        cases.append(event)
        return event
    event = attempt("quadratic_order_public_scales_zero_columns_and_mapping_parity")
    expected_pairs = ((0,0),(0,1),(0,2),(0,3),(0,4),(0,5),(1,1),(1,2),(1,3),(1,4),(1,5),
                      (2,2),(2,3),(2,4),(2,5),(3,3),(3,4),(3,5),(4,4),(4,5),(5,5))
    assert QUADRATIC_PAIRS == expected_pairs and Z_PHI_INDICES == (0,1,8,9,22,23) and Z_SCALES == (.12,.12,1.,1.,.5,.5)
    x = np.zeros(22); x[0:2] = (.24, -.12); x[8:10] = (.5, -.25)
    saved_phi = np.asarray([*x, .25, -.5, 0., -.25, 1., .5, -.25])
    training_map = {}
    training = append_quadratic50(core, saved_phi, cost, "synthetic_training", training_map)
    prediction, prior = features50(core, x, (0.,0.), (.25,-.5,0.,0.,0.,0.,0.,0.), np.zeros(8), guard, cost)
    expected = [4.,-2.,1.,-.5,1.,-2.,1.,-.5,.25,-.5,1.,.25,-.125,.25,-.5,.0625,-.125,.25,.25,-.5,1.]
    assert training_map["normalized_z6"] == [2.,-1.,.5,-.25,.5,-1.]
    assert np.array_equal(training[:29], saved_phi) and training[29:].tolist() == expected
    assert np.array_equal(training, prediction) and prior.shape == (22,)
    zero = append_quadratic50(core, np.zeros(29), cost, "synthetic_training")
    assert zero.shape == (50,) and np.array_equal(zero[29:], np.zeros(21))
    event["status"] = "passed"
    event = attempt("zero_quadratic_columns_analytic_equivalence")
    phi, delta = np.zeros((400,50)), np.zeros((400,22))
    phi[:29,:29] = np.eye(29)
    delta[:29] = np.arange(638).reshape(29,22)/1000.
    cost["synthetic_design_scalars_generated"] += 20000
    cost["synthetic_label_scalars_generated"] += 8800
    partial = {}
    weights = fit50(core, phi, delta, cost, partial)
    cost["synthetic_reference_scalar_divisions"] += 638
    expected = delta[:29]/1.01
    assert np.max(np.abs(weights[:29]-expected)) <= 1e-12 and np.array_equal(weights[29:], np.zeros((21,22)))
    event["status"] = "passed"
    event = attempt("closed_x22_and_previous_v_advance")
    weights = np.zeros((50,22)); weights[29,8] = .1; weights[49,9] = -.2; weights[29,16] = .5; weights[16,16] = .1
    initial = np.zeros(22); initial[:2] = (.06,-.03)
    result = rollout50(core, initial, (.2,.3), [[.5,.25,0.,0.,0.,0.,0.,0.],[-.25,.5,0.,0.,0.,0.,0.,0.]], np.zeros(8), guard, weights, cost)
    assert result["available"] and len(result["predicted_path_x22"]) == 2 and all(len(row) == 22 for row in result["predicted_path_x22"])
    assert result["history_inputs"][1]["current_x22_before"] == result["predicted_path_x22"][0]
    assert result["history_inputs"][1]["previous_v2_before"] == [0.,0.] and result["terminal_previous_v2"] == result["predicted_path_x22"][0][8:10]
    assert result["predicted_path_x22"][0][16] != 0. and result["history_inputs"][1]["current_x22_before"][16] != initial[16]
    event["status"] = "passed"
    event = attempt("new_fit50_solve_failure_paid_partial_saved")
    paid, partial = Counter(), {}
    try:
        try:
            with patch.object(np.linalg, "solve", side_effect=np.linalg.LinAlgError("synthetic_injected_fit50_solve_failure")):
                fit50(core, phi, delta, paid, partial)
        finally:
            cost.update(paid)
            event["paid_cost"] = dict(paid)
    except np.linalg.LinAlgError as exc:
        fixture = output/"fit50_failure_fixture"
        fixture.mkdir()
        run = {"status": "failed", "self_check": True, "cost": dict(paid), "failure": {"type": type(exc).__name__, "message": str(exc)}, "scientific_adoption": False}
        write_outputs(fixture, [{"predictor": "Q22", "fit": partial}], [], {"status": "failed"}, run)
        event["saved_fixture_files"] = ["parameters.json", "metrics.json", "run.json", "predictions.jsonl", "failure.json", "manifest.json"]
        assert paid["fit_shared_50x50_22rhs_solve_attempts"] == 1 and paid["fit_shared_50x50_22rhs_solve_failures"] == 1
        assert paid["fit_scalar_labels_returned"] == 8800 and partial["status"] == "failed" and "ridge_normal50x50" in partial
    else:
        raise AssertionError("injected_new_fit50_solve_failure_not_seen")
    event["status"] = "passed"


def main_run(args):
    repo, output = Path(args.repo).resolve(), Path(args.output).resolve()
    if any((repo/root).resolve().is_relative_to(output) for root in (C_ROOT, D_ROOT, K_ROOT)):
        raise ValueError("output_must_not_contain_original_inputs")
    output.mkdir(parents=True, exist_ok=False)
    wall, cpu = time.perf_counter(), time.process_time()
    cost = Counter({key: 0 for key in ("fit_attempts", "fit_returns", "fit_failures", "fit_shared_50x50_22rhs_solve_attempts", "fit_shared_50x50_22rhs_solve_returns", "fit_shared_50x50_22rhs_solve_failures", "physics_calls", "physics_substeps", "RLS_updates", "MPC_calls", "K22_refits", "D11_updates")})
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
            trials, counts = support.parse_prediction(core, blobs[f"{C_ROOT}/trace.jsonl.gz"], cost)
            weights = {}
            for seed in SEEDS:
                saved = restored[seed]
                qref, prefix_id = core.prefix_qref(trials[f"seed{seed}_prediction"])
                if qref != saved["qref8"] or tuple(qref[:2]) != models[seed].qref or counts.get(f"seed{seed}_prediction") != 100:
                    raise ValueError("fixed_C_prediction_prefix_qref_or_full_counts_differ")
                record = {"seed": seed, "predictor": "Q22", "available": False, "fixed_lambda": RIDGE,
                    "state_order": core.STATE_NAMES, "feature_order": (*core.FEATURE_NAMES, *QUADRATIC_NAMES),
                    "quadratic_z_names": Z_NAMES, "quadratic_phi29_indices": Z_PHI_INDICES, "quadratic_public_scales": Z_SCALES,
                    "quadratic_pair_order": QUADRATIC_PAIRS, "quadratic_prior_coefficients": "all_zero_21x22",
                    "qref8": qref, "qref_source_transition_id": saved["qref_source_transition_id"],
                    "prediction_prefix_transition_id": prefix_id, "training_transition_ids": saved["ids"],
                    "training_fixed_count": 400, "training_usable_count": 0, "training_source_active_count": 400,
                    "K22_parameter_fingerprint": before_K[seed], "D11_parameter_fingerprint": before_D[seed], "fit": {}}
                parameters.append(record)
                phi50 = build_design50(core, saved["phi"], cost, record["fit"], record)
                weights[seed] = fit50(core, phi50, saved["delta"], cost, record["fit"])
                record.update(available=True, parameter_fingerprint=identity(json_bytes({"qref8": qref,
                    "feature_order": record["feature_order"], "lambda": RIDGE, "quadratic_phi29_indices": Z_PHI_INDICES,
                    "quadratic_public_scales": Z_SCALES, "quadratic_pair_order": QUADRATIC_PAIRS,
                    "weights50x22": weights[seed].tolist()}))["sha256"])
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
                            if predictor == "Q22":
                                outcome = rollout50(core, initial, previous_v, requests, saved["qref8"], models[seed].public_guard, weights[seed], cost)
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
    run = {"status": status, "self_check": args.self_check,
        "source": {"commit": args.source_commit, "files": files, "clean_committed_bytes_verified": source_verified},
        "inputs": inputs, "inputs_without_returned_read_record": {path: "unknown_before_read_return" for path in (support.PINS if support else []) if path not in inputs},
        "original_source_commits": support.COMMITS if support else "unknown_before_support_load", "requested_source_commit": args.source_commit,
        "runtime": {"python": platform.python_version(), "numpy": np.__version__, "platform": platform.platform()},
        "original_C_dependencies": cmeta.get("dependencies") if cmeta else "unknown_before_C_metadata_return", "source_active_counts": counts,
        "baseline_restorations": restorations, "K22_fingerprints_before": before_K, "K22_fingerprints_after": after_K or "unknown_before_return",
        "D11_fingerprints_before": before_D, "D11_fingerprints_after": after_D or "unknown_before_return", "self_check_cases": cases,
        "internal_pure_metric_aliases": {"Q22": "learned22", "K22": "cold22", "D11": "D11"}, "cost": dict(cost), "failure": failure,
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
