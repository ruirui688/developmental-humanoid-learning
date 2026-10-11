"""N: one fixed uncentered C400 RMS-scaled native ridge; offline development."""
from __future__ import annotations

import argparse
from collections import Counter
import gzip
import hashlib
import importlib.util
import io
import json
import math
from pathlib import Path
import platform
import subprocess
import sys
import time
import traceback

import numpy as np


SOURCE_PATH = "scripts/develop_guard_scaled_native_transition.py"
PROTOCOL_PATH = "docs/GUARD_SCALED_NATIVE_TRANSITION_DEVELOPMENT_PROTOCOL.md"
CORE_PATH = "scripts/develop_guard_native_transition.py"
CORE_SHA = "f910bb6fd9f01ebf5fd52426b40b43414e50bebcfe6460cf6132bccb1a2192bb"
HELPERS = (CORE_PATH, "docs/GUARD_NATIVE_TRANSITION_DEVELOPMENT_PROTOCOL.md",
           "src/developmental_physics/__init__.py", "src/developmental_physics/guard_lag_pair_model.py",
           "src/developmental_physics/guard_pair_model.py", "src/developmental_physics/local_pair_model.py",
           "src/developmental_physics/local_model.py")
C_ROOT = "results/cpu_validation/2026-10-11_guard_exploration/raw"
D_ROOT = "results/cpu_validation/2026-10-11_guard_lag_offline"
K_ROOT = "results/cpu_validation/2026-10-11_guard_native_transition/raw"
COMMITS = {"C": "5ea8df42b09588845760daf0dc1f270aef2a87f1",
           "D": "f7710c7b048dccab3e436d1fa16432f881a35992",
           "K": "b46c6d37fddc8e6534384168fb76663bc2c5236c"}
PINS = {
    f"{C_ROOT}/manifest.json": "fa7fb57c5b996ae77862c1e7d59d22af72376947af38409601444f25139f042e",
    f"{C_ROOT}/metadata.json": "2c0be03255858d7511d1e238b5eb491a6618f197f12810ea9e0b00a64d279b57",
    f"{C_ROOT}/trace.jsonl.gz": "1b299c9bc7a91f8ff9dfef3f77ac1b6fea923dea6057327bb3f9aa1ce6f56ad0",
    f"{D_ROOT}/manifest.json": "38df6b99e15c3667a33d6c9995a8efd664f70ce59be8a511fa49def59727a4d7",
    f"{D_ROOT}/raw/manifest.json": "f5d6e0fc017d708a8c8b2b03a6876704248afee92266985ebd5d137267acb3c6",
    f"{D_ROOT}/raw/diagnostics.json": "9307f3f37d5a3c23ef6f9097d8c352a9fc7f2e34e562b5cf4e7075e20bbbe130",
    f"{K_ROOT}/manifest.json": "f8bf006eac1615e2a1bee801926c6157f265836011a847c24d19fe0f7341a588",
    f"{K_ROOT}/run.json": "1ea85a61e1b6ecbc43770c52ce6a3435c0e4d919d8af5fc91bc317b7abc84b3e",
    f"{K_ROOT}/parameters.json": "1a5c426cfece2fe099ba2e13bfe6229ef7189f59870183620fcb1e1aa14de0aa",
}
SEEDS, HORIZONS, PREDICTORS = (0, 1, 2), (1, 2, 5, 15), ("N22", "K22", "D11")
RIDGE = .01


def digest(data):
    return hashlib.sha256(data).hexdigest()


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+"\n").encode("utf-8")


def identity(data):
    return {"bytes": len(data), "sha256": digest(data)}


def same_identity(binding, actual):
    return isinstance(binding, dict) and all(binding.get(key) == actual[key] for key in ("bytes", "sha256"))


def frozen_sources(repo, commit, cost):
    if (len(commit) != 40 or any(c not in "0123456789abcdef" for c in commit)
            or Path(__file__).resolve() != (repo/SOURCE_PATH).resolve()):
        raise ValueError("exact N commit and canonical source path required")
    def git(*args):
        cost["git_query_attempts"] += 1
        result = subprocess.run(["git", *args], cwd=repo, capture_output=True, check=False)
        cost["git_query_returns"] += 1
        cost["git_return_bytes"] += len(result.stdout)+len(result.stderr)
        if result.returncode:
            raise ValueError("read-only source verification failed")
        return result.stdout
    if (git("rev-parse", "HEAD").decode().strip() != commit
            or git("status", "--porcelain", "--untracked-files=no").strip()):
        raise ValueError("clean exact N HEAD required")
    files = {}
    for name in (SOURCE_PATH, PROTOCOL_PATH, *HELPERS):
        cost["source_file_read_attempts"] += 1
        data = (repo/name).read_bytes()
        cost["source_file_read_returns"] += 1
        cost["source_raw_bytes"] += len(data)
        files[name] = identity(data)
        if git("show", f"{commit}:{name}") != data:
            raise ValueError(f"N frozen source bytes differ: {name}")
    if files[CORE_PATH]["sha256"] != CORE_SHA:
        raise ValueError("published K helper changed")
    return {"commit": commit, "files": files, "clean_committed_bytes_verified": True}


def load_core(repo):
    spec = importlib.util.spec_from_file_location("frozen_K_native_helpers", repo/CORE_PATH)
    core = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(core)
    return core


def read_inputs(repo, records, cost, source):
    blobs, docs = {}, {}
    for name, expected in PINS.items():
        cost["input_file_read_attempts"] += 1
        data = (repo/name).read_bytes()
        cost["input_file_read_returns"] += 1
        cost["input_raw_bytes"] += len(data)
        cost["input_hash_bytes"] += len(data)
        records[name] = identity(data)
        if records[name]["sha256"] != expected:
            raise ValueError(f"pinned input differs: {name}")
        if name.endswith(".json"):
            cost["json_parse_attempts"] += 1
            docs[name] = json.loads(data)
            cost["json_parse_returns"] += 1
        else:
            blobs[name] = data
    cmeta, krun = docs[f"{C_ROOT}/metadata.json"], docs[f"{K_ROOT}/run.json"]
    if (cmeta.get("source_commit") != COMMITS["C"] or cmeta.get("source_dirty") is not False
            or cmeta.get("synthetic") is not False or cmeta.get("seeds") != list(SEEDS)
            or [cmeta.get(k) for k in ("prefix_steps", "calibration_steps", "prediction_steps")] != [100, 400, 100]):
        raise ValueError("C original formal identity/length differs")
    for name in ("metadata.json", "trace.jsonl.gz"):
        if docs[f"{C_ROOT}/manifest.json"][name] != records[f"{C_ROOT}/{name}"]["sha256"]:
            raise ValueError("C flat manifest binding differs")
    if docs[f"{D_ROOT}/raw/manifest.json"].get("status") != "completed":
        raise ValueError("D raw incomplete")
    for name in ("raw/manifest.json", "raw/diagnostics.json"):
        if not same_identity(docs[f"{D_ROOT}/manifest.json"]["files"][name], records[f"{D_ROOT}/{name}"]):
            raise ValueError("D archive bytes/SHA binding differs")
    if not same_identity(docs[f"{D_ROOT}/raw/manifest.json"]["files"]["diagnostics.json"], records[f"{D_ROOT}/raw/diagnostics.json"]):
        raise ValueError("D raw diagnostics binding differs")
    kmanifest = docs[f"{K_ROOT}/manifest.json"]
    if (kmanifest.get("status") != "completed" or krun.get("status") != "completed"
            or krun.get("source", {}).get("commit") != COMMITS["K"]
            or krun["source"].get("clean_committed_bytes_verified") is not True
            or krun.get("original_source_commits") != {key: COMMITS[key] for key in ("C", "D")}):
        raise ValueError("K original clean completed identity differs")
    for name in ("run.json", "parameters.json"):
        if not same_identity(kmanifest["files"][name], records[f"{K_ROOT}/{name}"]):
            raise ValueError("K raw manifest binding differs")
    for name in PINS:
        if name.startswith(C_ROOT) or name.startswith(D_ROOT):
            if not same_identity(krun["inputs"][name], records[name]):
                raise ValueError("K original C/D inputs differ")
    for name in HELPERS:
        if not same_identity(krun["source"]["files"][name], source["files"][name]):
            raise ValueError("K pure helper bytes differ from original")
    return blobs, docs, cmeta


def restore_K(core, payload, cost, records):
    if not isinstance(payload, list) or len(payload) != 3:
        raise ValueError("exact three K records required")
    restored = {}
    for seed in SEEDS:
        event = {"seed": seed, "attempted": True, "returned": False}
        records.append(event)
        cost["K22_restoration_attempts"] += 1
        matches = [row for row in payload if row.get("seed") == seed]
        if len(matches) != 1:
            raise ValueError("one K record per seed required")
        row = matches[0]
        ids = [f"seed{seed}_calibration_sparse:{step}" for step in range(100, 500)]
        if (row.get("available") is not True or row.get("fixed_lambda") != RIDGE
                or row.get("state_order") != list(core.STATE_NAMES) or row.get("feature_order") != list(core.FEATURE_NAMES)
                or row.get("training_usable_count") != 400 or row.get("training_source_active_count") != 400
                or row.get("training_transition_ids") != ids):
            raise ValueError("fixed K C400 definition/count/IDs differ")
        qref = core.vector(row["qref8"], 8)
        weights = core.finite_array(row["fit"]["weights29x22"], (29, 22)).copy()
        fingerprint = parameter_fingerprint(core, qref, weights)
        if fingerprint != row.get("parameter_fingerprint"):
            raise ValueError("saved K parameter fingerprint differs")
        phi = core.finite_array(row["fit"]["phi400x29"], (400, 29))
        delta = core.finite_array(row["fit"]["delta_labels400x22"], (400, 22))
        cost["K22_saved_weight_scalars_validated"] += int(weights.size)
        cost["K22_saved_design_scalars_validated"] += int(phi.size)
        cost["K22_saved_label_scalars_validated"] += int(delta.size)
        restored[seed] = {"qref8": qref, "weights": weights, "phi": phi, "delta": delta, "ids": ids,
                          "qref_source_transition_id": row["qref_source_transition_id"], "fingerprint": fingerprint}
        event.update(returned=True, fingerprint=fingerprint, refit=False)
        cost["K22_restoration_returns"] += 1
    return restored


def parameter_fingerprint(core, qref, weights):
    return digest(core.json_bytes({"qref8": qref, "weights29x22": weights.tolist(),
                                  "lambda": RIDGE, "feature_order": core.FEATURE_NAMES}))


def parse_prediction(core, blob, cost):
    trials = {f"seed{s}_prediction": {} for s in SEEDS}
    counts = Counter()
    with gzip.GzipFile(fileobj=io.BytesIO(blob), mode="rb") as stream:
        for line in stream:
            cost["C_trace_uncompressed_bytes"] += len(line)
            cost["C_trace_json_parse_attempts"] += 1
            row = json.loads(line)
            cost["C_trace_json_parse_returns"] += 1
            seed = row.get("seed")
            if seed not in SEEDS or row.get("kind") != "prediction":
                continue
            trial, step = f"seed{seed}_prediction", row.get("step_index")
            if (row.get("trial_id") != trial or type(step) is not int or not 0 <= step < 200
                    or step in trials[trial] or row.get("shared_transition_id") != f"{trial}:{step}"
                    or row.get("phase") != ("prefix" if step < 100 else "prediction")):
                raise ValueError("C selected prediction identity/phase/index differs")
            keys = ("joint_position", "joint_velocity", "imu_gyro", "imu_acceleration")
            diagnostics = row.get("diagnostics", {})
            trials[trial][step] = {"trial_id": trial, "seed": seed, "kind": "prediction", "step_index": step,
                "phase": row["phase"], "shared_transition_id": row["shared_transition_id"],
                "requested_torque": row.get("requested_torque"), "study_abort": row.get("study_abort"),
                "diagnostics": {key: diagnostics.get(key) for key in ("executed_substeps", "terminated")},
                **{name: {key: row[name][key] for key in keys} for name in ("observation_before", "observation_after")}}
            if step >= 100:
                counts[trial] += 1
    return trials, dict(counts)


def fit_product(left, right, name, cost, record):
    event = {"name": name, "left_shape": list(left.shape), "right_shape": list(right.shape), "status": "attempted"}
    record.setdefault("matrix_operations", []).append(event)
    cost[f"fit_{name}_matrix_attempts"] += 1
    rows, inner, columns = left.shape[0], left.shape[1], right.shape[1]
    cost["fit_logical_multiply_requests"] += rows*inner*columns
    cost["fit_logical_add_requests"] += rows*columns*max(inner-1, 0)
    try:
        result = left @ right
    except BaseException as exc:
        cost[f"fit_{name}_matrix_failures"] += 1
        event["status"] = "failed_before_return"
        event["failure"] = {"type": type(exc).__name__, "message": str(exc)}
        raise
    event.update(status="returned", output_shape=list(result.shape), output_scalars=int(result.size))
    cost[f"fit_{name}_matrix_returns"] += 1
    if not np.isfinite(result).all():
        cost[f"fit_{name}_matrix_validation_failures"] += 1
        event["validation"] = "failed_nonfinite"
        raise ValueError("nonfinite scaled ridge matrix product")
    event["validation"] = "finite"
    return result


def fit_scaled(core, phi, delta, cost, record):
    """One candidate, no scale floor/centering/search; partial matrices preserved."""
    cost["fit_attempts"] += 1
    try:
        phi, delta = core.finite_array(phi, (400, 29)), core.finite_array(delta, (400, 22))
        cost["scale_estimation_attempts"] += 1
        cost["scale_input_scalar_uses_requested"] += int(phi.size)
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            try:
                scale = np.sqrt(np.mean(phi**2, axis=0))
            except BaseException:
                cost["scale_estimation_failures"] += 1
                raise
            cost["scale_estimation_returns"] += 1
            cost["scale_input_scalar_uses_returned"] += int(phi.size)
            cost["scale_output_scalars"] += int(scale.size)
            if not np.isfinite(scale).all():
                cost["scale_validation_failures"] += 1
                raise ValueError("nonfinite column RMS")
            record["scale29"] = scale.tolist()
            if not np.all(scale > 0):
                cost["scale_validation_failures"] += 1
                raise ValueError("finite strictly positive column RMS required; no replacement or floor")
            cost["normalized_design_scalar_divisions_requested"] += int(phi.size)
            normalized = phi/scale
            if not np.isfinite(normalized).all():
                raise ValueError("nonfinite scaled design")
            cost["normalized_design_scalar_divisions"] += int(phi.size)
            record["normalized_phi400x29"] = normalized.tolist()
            gram = fit_product(normalized.T, normalized, "gram", cost, record)
            record["gram29x29"] = gram.tolist()
            cost["fit_scalar_labels_requested"] += int(delta.size)
            cross = fit_product(normalized.T, delta, "cross", cost, record)
            cost["fit_scalar_labels_returned"] += int(delta.size)
            record["cross29x22"] = cross.tolist()
            normal = gram+RIDGE*np.eye(29, dtype=np.float64)
            record["ridge_normal29x29"] = normal.tolist()
            cost["fit_shared_29x29_22rhs_solve_attempts"] += 1
            try:
                normalized_weights = np.linalg.solve(normal, cross)
            except BaseException:
                cost["fit_shared_29x29_22rhs_solve_failures"] += 1
                raise
            cost["fit_shared_29x29_22rhs_solve_returns"] += 1
            normalized_weights = core.finite_array(normalized_weights, (29, 22))
            record["normalized_weights29x22"] = normalized_weights.tolist()
            cost["raw_weight_scalar_divisions_requested"] += int(normalized_weights.size)
            weights = core.finite_array(normalized_weights/scale[:, None], (29, 22))
            cost["raw_weight_scalar_divisions"] += int(weights.size)
            record["weights29x22"] = weights.tolist()
            cost["transition_scalar_coefficients_fitted"] += int(weights.size)
            cost["transition_heads_published"] += 22
            cost["fit_returns"] += 1
            return weights
    except BaseException as exc:
        cost["fit_failures"] += 1
        record["failure"] = {"type": type(exc).__name__, "message": str(exc)}
        raise


def summarize(core, records, counts):
    # K's metric definitions are reused; only predictor labels change.
    aliases = {"N22": "learned22", "K22": "cold22", "D11": "D11"}
    inverse = {value: key for key, value in aliases.items()}
    groups = core.summarize([{**row, "predictor": aliases[row["predictor"]]} for row in records], counts)
    return [{**group, "predictor": inverse[group["predictor"]]} for group in groups]


def dual_gate(core, groups):
    gates = {}
    for baseline in ("K22", "D11"):
        mapping = {"N22": "learned22", baseline: "D11"}
        aliased = [{**group, "predictor": mapping.get(group["predictor"], "cold22")} for group in groups]
        gate = core.development_gate(aliased)
        gate.update(candidate_predictor="N22", baseline_predictor=baseline,
                    scope="new_seen_C_common_prediction_RMS_scale_development_subgate")
        for check in gate["checks"]:
            for seed_record in check["seed_records"]:
                seed_record["N22_rmse"] = seed_record.pop("learned22_rmse")
                seed_record[f"{baseline}_rmse"] = seed_record.pop("D11_rmse")
        gates[f"N22_vs_{baseline}"] = gate
    return {"scope": "single_seen_C_RMS_scale_development", "comparisons": gates,
        "all_fixed_usable_counts": all(gate["all_fixed_usable_counts"] for gate in gates.values()),
        "evaluated": all(gate["evaluated"] for gate in gates.values()),
        "passed": all(gate["passed"] for gate in gates.values()),
        "scientific_adoption": False, "c4_scientific_validation": False, "c5_scientific_dependency_released": False}


def main_run(args):
    repo, output = Path(args.repo).resolve(), Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    wall_started, cpu_started = time.perf_counter(), time.process_time()
    cost = Counter({key: 0 for key in ("fit_attempts", "fit_returns", "fit_failures",
        "fit_scalar_labels_requested", "fit_scalar_labels_returned", "fit_shared_29x29_22rhs_solve_attempts",
        "fit_shared_29x29_22rhs_solve_returns", "fit_shared_29x29_22rhs_solve_failures",
        "transition_scalar_coefficients_fitted", "transition_heads_published", "scale_estimation_attempts",
        "scale_estimation_returns", "K22_restoration_attempts", "K22_restoration_returns",
        "D11_restoration_attempts", "D11_restoration_returns", "physics_calls", "physics_substeps",
        "RLS_updates", "MPC_calls", "K22_refits", "D11_updates")})
    inputs, source, parameters, predictions, restorations = {}, None, [], [], {"K22": [], "D11": []}
    cmeta = None
    counts, before_K, before_D, after_K, after_D, groups, gate = {}, {}, {}, {}, {}, [], None
    failure, status, core = None, "failed", None
    try:
        source = frozen_sources(repo, args.source_commit, cost)
        core = load_core(repo)
        blobs, docs, cmeta = read_inputs(repo, inputs, cost, source)
        restored = restore_K(core, docs[f"{K_ROOT}/parameters.json"], cost, restorations["K22"])
        models = core.restore_models(docs[f"{D_ROOT}/raw/diagnostics.json"], repo, cost, restorations["D11"])
        before_K = {seed: row["fingerprint"] for seed, row in restored.items()}
        before_D = {seed: model.parameter_fingerprint() for seed, model in models.items()}
        trials, counts = parse_prediction(core, blobs[f"{C_ROOT}/trace.jsonl.gz"], cost)
        weights = {}
        for seed in SEEDS:
            saved, rows = restored[seed], trials[f"seed{seed}_prediction"]
            qref, prefix_id = core.prefix_qref(rows)
            if qref != saved["qref8"] or tuple(qref[:2]) != models[seed].qref or counts.get(f"seed{seed}_prediction") != 100:
                raise ValueError("prediction full100 prefix/qref/active count differs from K/D")
            record = {"seed": seed, "available": False, "fixed_lambda": RIDGE,
                "state_order": core.STATE_NAMES, "feature_order": core.FEATURE_NAMES, "qref8": qref,
                "qref_source_transition_id": saved["qref_source_transition_id"], "prediction_prefix_transition_id": prefix_id,
                "training_transition_ids": saved["ids"], "training_usable_count": 400,
                "K22_parameter_fingerprint": before_K[seed], "D11_parameter_fingerprint": before_D[seed],
                "uncentered_column_RMS": True, "scale_floor": None, "scale_search": False,
                "prior_position_integration": "current_velocity", "fit": {}}
            parameters.append(record)
            weights[seed] = fit_scaled(core, saved["phi"], saved["delta"], cost, record["fit"])
            record.update(available=True, parameter_fingerprint=parameter_fingerprint(core, qref, weights[seed]))
        for seed in SEEDS:
            saved, rows = restored[seed], trials[f"seed{seed}_prediction"]
            for horizon in HORIZONS:
                for origin in range(101-horizon):
                    common = {"seed": seed, "trial_id": f"seed{seed}_prediction", "origin": origin,
                              "horizon": horizon, "offline_saved_future_requests": True}
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
                        predictions.extend({**common, "predictor": name, "available": False,
                            "reason": f"window_unavailable:{type(exc).__name__}:{exc}"} for name in PREDICTORS)
                        continue
                    current = []
                    for name in PREDICTORS:
                        if name == "D11":
                            outcome = core.rollout11(models[seed], q, v, previous_v, requests, cost)
                        else:
                            chosen = weights[seed] if name == "N22" else saved["weights"]
                            outcome = core.rollout22(initial, previous_v, requests, saved["qref8"], models[seed].public_guard,
                                                     chosen, cost, name)
                        record = {**common, "predictor": name, **outcome, "scored": False}
                        predictions.append(record)
                        current.append(record)
                    actual = core.encode_state(active[-1]["observation_after"], saved["qref8"], cost)
                    actual_q, actual_v = core.native(active[-1]["observation_after"])[:2]
                    for record in current:
                        if not record["available"]:
                            continue
                        if record["predictor"] == "D11":
                            pq, pv = record["terminal_qv"]
                            errors = {**{str(i): actual_q[i]-pq[i] for i in range(2)},
                                      **{str(8+i): actual_v[i]-pv[i] for i in range(2)}}
                        else:
                            errors = {str(i): float(actual[i]-record["terminal_x22"][i]) for i in range(22)}
                        if not all(math.isfinite(value) for value in errors.values()):
                            cost["terminal_score_validation_failures"] += 1
                            record.update(available=False, reason="nonfinite_terminal_error")
                        else:
                            cost["score_scalar_error_calculations"] += len(errors)
                            record.update(scored=True, actual_endpoint_x22=actual.tolist(), terminal_errors_x22=errors)
        after_K = {seed: parameter_fingerprint(core, row["qref8"], row["weights"]) for seed, row in restored.items()}
        after_D = {seed: model.parameter_fingerprint() for seed, model in models.items()}
        if before_K != after_K or before_D != after_D:
            raise ValueError("frozen K22/D11 baseline mutated")
        groups = summarize(core, predictions, counts)
        gate = dual_gate(core, groups)
        status = "completed"
    except BaseException as exc:
        failure = {"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()}
    cost["wall_seconds"], cost["cpu_seconds"] = time.perf_counter()-wall_started, time.process_time()-cpu_started
    passed = bool(status == "completed" and gate and gate["passed"])
    run = {"status": status, "source": source if source is not None else {"status": "unknown", "reason": "source verifier did not return"},
        "requested_source_commit": args.source_commit, "original_source_commits": COMMITS, "inputs": inputs,
        "inputs_without_returned_read_record": {name: "unknown_before_input_record_returned" for name in PINS if name not in inputs},
        "runtime": {"python": platform.python_version(), "numpy": np.__version__, "platform": platform.platform()},
        "original_C_dependencies": cmeta.get("dependencies") if cmeta is not None else "unknown_before_C_metadata_returned",
        "source_active_counts": counts, "baseline_restorations": restorations,
        "K22_fingerprints_before": before_K, "K22_fingerprints_after": after_K if after_K else "unknown_before_verifier_returned",
        "D11_fingerprints_before": before_D, "D11_fingerprints_after": after_D if after_D else "unknown_before_verifier_returned",
        "cost": dict(cost), "failure": failure, "development_gate_passed": passed, "scientific_adoption": False,
        "c4_scientific_validation": False, "c5_scientific_dependency_released": False,
        "timing_excludes": "final output serialization and write"}
    metrics = {"status": status, "groups": groups, "development_gate": gate,
        "development_gate_passed": passed, "scientific_adoption": False,
        "c4_scientific_validation": False, "c5_scientific_dependency_released": False}
    files = {}
    values = {"parameters.json": json_bytes(parameters), "metrics.json": json_bytes(metrics), "run.json": json_bytes(run),
        "predictions.jsonl": b"".join((json.dumps(row, ensure_ascii=False, allow_nan=False)+"\n").encode("utf-8") for row in predictions)}
    if failure:
        values["failure.json"] = json_bytes(run)
    for name, data in values.items():
        (output/name).write_bytes(data)
        files[name] = identity(data)
    (output/"manifest.json").write_bytes(json_bytes({"schema_version": 1, "status": status, "scientific_adoption": False, "files": files}))
    print(json.dumps({"status": status, "output": str(output), "cost": dict(cost), "development_gate_passed": passed,
        "gate_comparisons": {name: item["passed"] for name, item in gate["comparisons"].items()} if gate else None,
        "failure": {"type": failure["type"], "message": failure["message"]} if failure else None}, ensure_ascii=False))
    return 0 if status == "completed" else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".")
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--output", required=True)
    sys.exit(main_run(parser.parse_args()))
