"""K: fixed closed 22-channel native transition, reused C data, offline only."""
from __future__ import annotations

import argparse
from collections import Counter
import gzip
import hashlib
import io
import json
import math
from pathlib import Path
import platform
import subprocess
import sys
import time

import numpy as np


SOURCE_PATH = "scripts/develop_guard_native_transition.py"
PROTOCOL_PATH = "docs/GUARD_NATIVE_TRANSITION_DEVELOPMENT_PROTOCOL.md"
HELPERS = ("src/developmental_physics/__init__.py",
           "src/developmental_physics/guard_lag_pair_model.py",
           "src/developmental_physics/guard_pair_model.py",
           "src/developmental_physics/local_pair_model.py",
           "src/developmental_physics/local_model.py")
C_ROOT = "results/cpu_validation/2026-10-11_guard_exploration/raw"
D_ROOT = "results/cpu_validation/2026-10-11_guard_lag_offline"
C_COMMIT = "5ea8df42b09588845760daf0dc1f270aef2a87f1"
D_COMMIT = "f7710c7b048dccab3e436d1fa16432f881a35992"
PINS = {
    f"{C_ROOT}/manifest.json": "fa7fb57c5b996ae77862c1e7d59d22af72376947af38409601444f25139f042e",
    f"{C_ROOT}/metadata.json": "2c0be03255858d7511d1e238b5eb491a6618f197f12810ea9e0b00a64d279b57",
    f"{C_ROOT}/trace.jsonl.gz": "1b299c9bc7a91f8ff9dfef3f77ac1b6fea923dea6057327bb3f9aa1ce6f56ad0",
    f"{D_ROOT}/manifest.json": "38df6b99e15c3667a33d6c9995a8efd664f70ce59be8a511fa49def59727a4d7",
    f"{D_ROOT}/raw/manifest.json": "f5d6e0fc017d708a8c8b2b03a6876704248afee92266985ebd5d137267acb3c6",
    f"{D_ROOT}/raw/diagnostics.json": "9307f3f37d5a3c23ef6f9097d8c352a9fc7f2e34e562b5cf4e7075e20bbbe130",
}
SEEDS, HORIZONS = (0, 1, 2), (1, 2, 5, 15)
PREDICTORS = ("cold22", "learned22", "D11")
DT, RIDGE = .02, .01
STATE_NAMES = tuple([f"q{i}-qref{i}" for i in range(8)] + [f"v{i}" for i in range(8)]
                    + [f"gyro_{c}" for c in "xyz"] + [f"accel_{c}/9.81" for c in "xyz"])
FEATURE_NAMES = (*STATE_NAMES, "startG0", "startG1", "hinge_startG0_.25",
                 "hinge_startG1_.25", "1", "v0-previous_v0", "v1-previous_v1")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+"\n").encode("utf-8")


def vector(value, size):
    if not isinstance(value, (list, tuple)) or len(value) != size:
        raise ValueError(f"expected finite native vector length {size}")
    if any(type(x) not in (int, float) or not math.isfinite(x) for x in value):
        raise ValueError("nonfinite or nonnumeric native vector")
    return tuple(float(x) for x in value)


def finite_array(value, shape):
    array = np.asarray(value, dtype=np.float64)
    if array.shape != shape or not np.isfinite(array).all():
        raise ValueError(f"expected finite array shape {shape}")
    return array


def native(observation):
    """Whitelist only eight q/v and current six native IMU readings."""
    return tuple(vector(observation[key], size) for key, size in (
        ("joint_position", 8), ("joint_velocity", 8),
        ("imu_gyro", 3), ("imu_acceleration", 3)))


def encode_state(observation, qref, cost):
    cost["native_state_encoding_attempts"] += 1
    q, v, gyro, acceleration = native(observation)
    ref = finite_array(qref, (8,))
    with np.errstate(over="ignore", invalid="ignore"):
        result = np.asarray([*(np.asarray(q)-ref), *v, *gyro,
                             *(np.asarray(acceleration)/9.81)], dtype=np.float64)
    if not np.isfinite(result).all():
        raise ValueError("nonfinite normalized native state")
    cost["native_state_encoding_returns"] += 1
    cost["native_acceleration_scalar_divisions"] += 3
    return result


def complete(row):
    return row.get("diagnostics", {}).get("executed_substeps") == 10


def stopped(row):
    return row.get("study_abort") is not None or bool(row.get("diagnostics", {}).get("terminated", False))


def continuous(previous, current):
    return (previous["trial_id"] == current["trial_id"]
            and previous["step_index"]+1 == current["step_index"]
            and complete(previous) and complete(current) and not stopped(previous)
            and native(previous["observation_after"]) == native(current["observation_before"]))


def parse_trials(blob, cost):
    """Parse C once; immediately discard every unapproved field/trial."""
    trials = {f"seed{s}_{kind}": {} for s in SEEDS for kind in ("calibration_sparse", "prediction")}
    source_counts = Counter()
    with gzip.GzipFile(fileobj=io.BytesIO(blob), mode="rb") as stream:
        for line in stream:
            cost["C_trace_uncompressed_bytes"] += len(line)
            row = json.loads(line)
            cost["C_trace_lines_parsed"] += 1
            seed, kind = row.get("seed"), row.get("kind")
            if seed not in SEEDS or kind not in ("calibration_sparse", "prediction"):
                continue
            trial = f"seed{seed}_{kind}"
            if row.get("trial_id") != trial or type(row.get("step_index")) is not int:
                raise ValueError("fixed C trial identity/index mismatch")
            step = row["step_index"]
            if step in trials[trial]:
                raise ValueError("duplicate C selected transition")
            phase = "prefix" if step < 100 else "calibration" if kind == "calibration_sparse" else "prediction"
            if step < 0 or row.get("phase") != phase or row.get("shared_transition_id") != f"{trial}:{step}":
                raise ValueError("C selected phase/transition identity mismatch")
            # Keep the explicit whitelist only. Never consume update or saved rollout logs.
            observation_keys = ("joint_position", "joint_velocity", "imu_gyro", "imu_acceleration")
            observations = {name: {key: row[name][key] for key in observation_keys}
                            for name in ("observation_before", "observation_after")}
            diagnostics = row.get("diagnostics", {})
            trials[trial][step] = {"trial_id": trial, "seed": seed, "kind": kind,
                "step_index": step, "phase": phase, "shared_transition_id": row["shared_transition_id"],
                "requested_torque": row.get("requested_torque"), **observations,
                "study_abort": row.get("study_abort"),
                "diagnostics": {key: diagnostics.get(key) for key in ("executed_substeps", "terminated")}}
            if phase != "prefix":
                source_counts[trial] += 1
    return trials, dict(source_counts)


def prefix_qref(rows):
    """All eight coordinates from this trial's last complete prefix after."""
    prefix = [rows.get(i) for i in range(100)]
    if any(row is None or row["phase"] != "prefix" or not complete(row) or stopped(row) for row in prefix):
        raise ValueError("full100_unstopped_prefix_required")
    for row in prefix:
        native(row["observation_before"]), native(row["observation_after"])
    if not all(continuous(prefix[i], prefix[i+1]) for i in range(99)):
        raise ValueError("discontinuous_full_native_prefix")
    return native(prefix[-1]["observation_after"])[0], prefix[-1]["shared_transition_id"]


def window(rows, origin, horizon):
    """Availability check only; no future native value is passed to rollout."""
    step = 100+origin
    if any(stopped(row) for index, row in rows.items() if index < step):
        raise ValueError("after_source_stop")
    past = [rows.get(step-2), rows.get(step-1)]
    active = [rows.get(step+i) for i in range(horizon)]
    if any(row is None for row in (*past, *active)):
        raise ValueError("missing_fixed_native_window_or_history")
    if not continuous(past[0], past[1]) or not continuous(past[1], active[0]):
        raise ValueError("discontinuous_past_two_native_endpoints")
    if any(not complete(row) for row in active):
        raise ValueError("partial_interval")
    if any(not continuous(active[i], active[i+1]) for i in range(horizon-1)):
        raise ValueError("discontinuous_or_after_source_stop")
    native(active[-1]["observation_after"])
    requests = [vector(row["requested_torque"], 8) for row in active]
    previous_v = native(past[0]["observation_after"])[1][:2]
    return active, past, requests, previous_v


def feature_and_prior(state, previous_v, request, qref, guard, cost, owner):
    """Pure current-start mapping and current-velocity position prior."""
    cost[f"{owner}_feature_prior_attempts"] += 1
    x = finite_array(state, (22,))
    ref, previous = finite_array(qref, (8,)), finite_array(previous_v, (2,))
    command = finite_array(request, (8,))
    with np.errstate(over="ignore", invalid="ignore"):
        native_q = x[:8]+ref
    if not np.isfinite(native_q).all():
        raise ValueError("predicted absolute q overflow")
    cost[f"{owner}_start_guard_attempts"] += 1
    g = np.asarray(guard.project(native_q[:2], command[:2]).projected_start_nm, dtype=np.float64)
    cost[f"{owner}_start_guard_returns"] += 1
    with np.errstate(over="ignore", invalid="ignore"):
        hinge = np.sign(g)*np.maximum(np.abs(g)-.25, 0.)
        phi = np.asarray([*x, *g, *hinge, 1., *(x[8:10]-previous)], dtype=np.float64)
        prior = x.copy()
        prior[:8] = x[:8]+DT*x[8:16]
        prior[8:10] = x[8:10]+DT*g
    if not np.isfinite(phi).all() or not np.isfinite(prior).all():
        raise ValueError("nonfinite features29 or prior22")
    cost[f"{owner}_feature_prior_returns"] += 1
    cost[f"{owner}_prior_scalar_outputs"] += 22
    return phi, prior


def fit_transition(phi, delta, cost):
    """Exactly one fixed 29x29 solve, with 22 right-hand sides."""
    phi, delta = finite_array(phi, (400, 29)), finite_array(delta, (400, 22))
    cost["fit_scalar_labels"] += delta.size
    cost["fit_gram_matrix_products"] += 1
    with np.errstate(over="ignore", invalid="ignore"):
        gram = phi.T @ phi
    cost["fit_cross_matrix_products"] += 1
    with np.errstate(over="ignore", invalid="ignore"):
        cross = phi.T @ delta
    cost["ridge_identity_matrix_additions"] += 1
    normal = gram+RIDGE*np.eye(29, dtype=np.float64)
    finite_array(normal, (29, 29)), finite_array(cross, (29, 22))
    cost["fit_shared_29x29_22rhs_solve_attempts"] += 1
    try:
        weights = np.linalg.solve(normal, cross)
    except BaseException:
        cost["fit_shared_29x29_22rhs_solve_failures"] += 1
        raise
    cost["fit_shared_29x29_22rhs_solve_returns"] += 1
    try:
        weights = finite_array(weights, (29, 22))
    except ValueError:
        cost["fit_parameter_validation_failures"] += 1
        raise
    cost["transition_heads_published"] += 22
    cost["transition_scalar_coefficients_fitted"] += weights.size
    return weights, {"phi400x29": phi.tolist(), "delta_labels400x22": delta.tolist(),
                     "gram29x29": gram.tolist(), "cross29x22": cross.tolist(),
                     "ridge_normal29x29": normal.tolist(), "weights29x22": weights.tolist()}


def rollout22(initial, previous_v, requests, qref, guard, weights, cost, name):
    """No native future arguments: all 22 channels close recursively."""
    x, previous = finite_array(initial, (22,)).copy(), finite_array(previous_v, (2,)).copy()
    path = []
    for request in requests:
        cost[f"{name}_transition_attempts"] += 1
        try:
            old_v = x[8:10].copy()
            phi, next_x = feature_and_prior(x, previous, request, qref, guard, cost, name)
            if weights is not None:
                cost[f"{name}_residual_vector_attempts"] += 1
                cost[f"{name}_residual_scalar_head_attempts"] += 22
                with np.errstate(over="ignore", invalid="ignore"):
                    residual = phi @ weights
                cost[f"{name}_residual_vector_returns"] += 1
                cost[f"{name}_residual_scalar_head_returns"] += 22
                finite_array(residual, (22,))
                with np.errstate(over="ignore", invalid="ignore"):
                    next_x = next_x+residual
            x = finite_array(next_x, (22,)).copy()
            previous = old_v  # Never future actual v or the just-predicted next v.
            path.append(x.tolist())
            cost[f"{name}_transition_returns"] += 1
        except Exception as exc:
            cost[f"{name}_transition_failures"] += 1
            return {"available": False, "reason": f"{type(exc).__name__}:{exc}", "predicted_path_x22": path}
    return {"available": True, "predicted_path_x22": path, "terminal_x22": x.tolist()}


def rollout11(model, q, v, previous_v, requests, cost):
    """Matched D baseline recursively advances only its own pair/history."""
    q, v, previous = tuple(q[:2]), tuple(v[:2]), tuple(previous_v)
    path = []
    for request in requests:
        cost["D11_pair_prediction_attempts"] += 1
        try:
            prediction = model.predict(q, v, request[:2], previous)
            cost["D11_pair_prediction_returns"] += 1
            cost["D11_scalar_prediction_attempts"] += 2
            cost["D11_scalar_prediction_returns"] += 2
        except Exception as exc:
            cost["D11_pair_prediction_failures"] += 1
            if hasattr(exc, "scalar_prediction_attempts"):
                cost["D11_scalar_prediction_attempts"] += exc.scalar_prediction_attempts
                cost["D11_scalar_prediction_returns"] += exc.scalar_prediction_successes
            else:
                cost["D11_unknown_scalar_prediction_failures"] += 1
            return {"available": False, "reason": f"{type(exc).__name__}:{exc}", "predicted_path_qv": path}
        try:
            if len(prediction) != 2:
                raise ValueError("D11 must return q_pair/v_pair")
            next_q, next_v = (vector(pair, 2) for pair in prediction)
        except (TypeError, ValueError) as exc:
            cost["D11_output_validation_failures"] += 1
            return {"available": False, "reason": f"{type(exc).__name__}:{exc}", "predicted_path_qv": path}
        previous, q, v = v, next_q, next_v
        path.append([list(q), list(v)])
    return {"available": True, "predicted_path_qv": path, "terminal_qv": [list(q), list(v)]}


def metric(errors):
    if not errors:
        return {"count": 0, "rmse": None, "mae": None, "bias": None}
    n = len(errors)
    return {"count": n, "rmse": math.hypot(*(x/math.sqrt(n) for x in errors)),
            "mae": math.fsum(abs(x)/n for x in errors), "bias": math.fsum(x/n for x in errors)}


def summarize(records, source_counts):
    groups = []
    for seed in SEEDS:
        for horizon in HORIZONS:
            expected = 101-horizon
            for name in PREDICTORS:
                own = [r for r in records if r["seed"] == seed and r["horizon"] == horizon and r["predictor"] == name]
                good = [r for r in own if r["available"]]
                channels = range(22) if name != "D11" else (0, 1, 8, 9)
                for channel in channels:
                    groups.append({"seed": seed, "horizon": horizon, "predictor": name,
                        "channel_index": channel, "channel": STATE_NAMES[channel],
                        "fixed_origin_count": expected, "record_count": len(own), "usable_count": len(good),
                        "unavailable_count": len(own)-len(good),
                        "source_active_count": source_counts.get(f"seed{seed}_prediction", 0),
                        "full_fixed_count": len(own) == len(good) == expected,
                        "metric": metric([r["terminal_errors_x22"][str(channel)] for r in good]),
                        "partial_subset_method_ranking": False})
    return groups


def development_gate(groups):
    lookup = {(r["seed"], r["horizon"], r["predictor"], r["channel_index"]): r for r in groups}
    counts_ok = all(r["full_fixed_count"] and r["source_active_count"] == 100 for r in groups)
    checks = []
    for horizon in HORIZONS:
        for signal, channels in (("q", (0, 1)), ("v", (8, 9))):
            if horizon == 1 and signal == "q":
                continue
            strict20 = (horizon == 1 and signal == "v") or (horizon == 15 and signal == "q")
            for axis, channel in enumerate(channels):
                pairs, improvements = [], []
                valid = counts_ok
                for seed in SEEDS:
                    learned, base = [lookup[seed, horizon, name, channel] for name in ("learned22", "D11")]
                    lrmse, brmse = learned["metric"]["rmse"], base["metric"]["rmse"]
                    usable = (learned["full_fixed_count"] and base["full_fixed_count"] and
                              lrmse is not None and brmse is not None and brmse > 0 and
                              math.isfinite(lrmse) and math.isfinite(brmse))
                    improvement = (brmse-lrmse)/brmse if usable else None
                    if improvement is not None and not math.isfinite(improvement):
                        usable, improvement = False, None
                    valid = valid and usable
                    if usable:
                        improvements.append(improvement)
                    pairs.append({"seed": seed, "learned22_rmse": lrmse, "D11_rmse": brmse,
                                  "relative_improvement": improvement, "complete": usable})
                mean = math.fsum(value/3 for value in improvements) if valid else None
                condition = valid and all(p["learned22_rmse"] < p["D11_rmse"] if strict20 else
                                          p["learned22_rmse"] <= p["D11_rmse"] for p in pairs)
                passed = bool(condition and (not strict20 or mean >= .20))
                checks.append({"horizon": horizon, "signal": signal, "axis": axis,
                    "rule": "each_seed_strict_and_mean_relative_ge_.20" if strict20 else "each_seed_no_worse",
                    "evaluated": bool(valid), "mean_relative_improvement": mean,
                    "passed": passed, "seed_records": pairs,
                    "unavailable_reason": None if valid else "missing_fixed_count_or_zero_D11_or_undefined"})
    return {"scope": "new_seen_C_common_prediction_development_subgate", "all_fixed_usable_counts": counts_ok,
        "evaluated": all(r["evaluated"] for r in checks), "passed": all(r["passed"] for r in checks),
        "checks": checks, "scientific_adoption": False, "D_old_gate_reinterpreted": False,
        "c4_scientific_validation": False, "c5_scientific_dependency_released": False}


def read_inputs(repo, records, cost):
    blobs = {}
    for relative, expected in PINS.items():
        data = (repo/relative).read_bytes()
        cost["input_file_reads"] += 1
        cost["input_raw_bytes"] += len(data)
        cost["input_hash_bytes"] += len(data)
        records[relative] = {"bytes": len(data), "sha256": digest(data)}
        if records[relative]["sha256"] != expected:
            raise ValueError(f"pinned input mismatch: {relative}")
        blobs[relative] = data
    docs = {name: json.loads(data) for name, data in blobs.items() if name.endswith(".json")}
    cost["json_documents_parsed"] += len(docs)
    metadata = docs[f"{C_ROOT}/metadata.json"]
    if (metadata.get("source_commit") != C_COMMIT or metadata.get("source_dirty") is not False or
            metadata.get("synthetic") is not False or metadata.get("seeds") != list(SEEDS) or
            [metadata.get(key) for key in ("prefix_steps", "calibration_steps", "prediction_steps")] != [100, 400, 100]):
        raise ValueError("C original source identity/length mismatch")
    for name in ("metadata.json", "trace.jsonl.gz"):
        if docs[f"{C_ROOT}/manifest.json"][name] != records[f"{C_ROOT}/{name}"]["sha256"]:
            raise ValueError("C raw flat manifest payload mismatch")
    if docs[f"{D_ROOT}/raw/manifest.json"].get("status") != "completed":
        raise ValueError("D raw status incomplete")
    for relative in ("raw/manifest.json", "raw/diagnostics.json"):
        binding = docs[f"{D_ROOT}/manifest.json"]["files"][relative]
        if any(binding[key] != records[f"{D_ROOT}/{relative}"][key] for key in ("bytes", "sha256")):
            raise ValueError("D root manifest payload mismatch")
    raw_binding = docs[f"{D_ROOT}/raw/manifest.json"]["files"]["diagnostics.json"]
    if any(raw_binding[key] != records[f"{D_ROOT}/raw/diagnostics.json"][key] for key in ("bytes", "sha256")):
        raise ValueError("D raw diagnostics payload mismatch")
    return blobs, docs, metadata


def frozen_sources(repo, commit, cost):
    if len(commit) != 40 or any(c not in "0123456789abcdef" for c in commit) or Path(__file__).resolve() != (repo/SOURCE_PATH).resolve():
        raise ValueError("exact K commit and canonical source path required")
    def git(*args):
        result = subprocess.run(["git", *args], cwd=repo, capture_output=True, check=False)
        cost["git_queries"] += 1
        cost["git_return_bytes"] += len(result.stdout)+len(result.stderr)
        if result.returncode:
            raise ValueError("Git read-only source verification failed")
        return result.stdout
    if git("rev-parse", "HEAD").decode().strip() != commit or git("status", "--porcelain", "--untracked-files=no").strip():
        raise ValueError("clean exact K HEAD required")
    sources = {}
    for name in (SOURCE_PATH, PROTOCOL_PATH, *HELPERS):
        data = (repo/name).read_bytes()
        cost["source_file_reads"] += 1
        cost["source_raw_bytes"] += len(data)
        sources[name] = {"bytes": len(data), "sha256": digest(data)}
        if git("show", f"{commit}:{name}") != data:
            raise ValueError(f"K source byte mismatch: {name}")
    return {"commit": commit, "files": sources, "clean_committed_bytes_verified": True}


def restore_models(diagnostics, repo, cost, restoration_records):
    sys.path.insert(0, str(repo/"src"))
    from developmental_physics.guard_lag_pair_model import GuardLagPairBodyModel
    from developmental_physics.local_pair_model import _parameter_state
    models = {}
    for seed in SEEDS:
        record = {"seed": seed, "attempted": True, "returned": False}
        restoration_records.append(record)
        cost["D11_restoration_attempts"] += 1
        matches = [r for r in diagnostics if r.get("seed") == seed and r.get("calibration") == "sparse"]
        if len(matches) != 1:
            raise ValueError("exactly one D sparse snapshot per seed required")
        snapshot = matches[0]["lag11_final_snapshot"]
        if snapshot.get("vector_update_count") != 400 or snapshot.get("scalar_update_count") != 800:
            raise ValueError("D complete400vector/800scalar snapshot required")
        model = GuardLagPairBodyModel(snapshot["qref_rad"],
            public_joint_ranges=snapshot["input_mapping"]["public_guard"]["public_joint_ranges_rad"], trainable=False)
        theta, covariance = (finite_array(snapshot[key], shape) for key, shape in
                             (("coefficients", (2, 11)), ("covariance", (2, 11, 11))))
        model._state = _parameter_state(theta.copy(), covariance.copy(), 400)
        expected = dict(snapshot)
        expected["trainable"] = False
        if model.snapshot() != expected:
            raise ValueError("D snapshot/fingerprint/constants mismatch")
        models[seed] = model
        record.update(returned=True, parameter_fingerprint=model.parameter_fingerprint(),
                      public_guard=model.public_guard.spec())
        cost["D11_restoration_returns"] += 1
    return models


def main_run(args):
    output = Path(args.output).resolve()
    if output.exists():
        raise FileExistsError("new K output required; no overwrite/rerun")
    output.mkdir(parents=True)
    start_wall, start_cpu = time.perf_counter(), time.process_time()
    cost = Counter({key: 0 for key in (
        "physics_calls", "physics_substeps", "MPC_calls", "RLS_updates", "D11_updates",
        "fit_scalar_labels", "fit_shared_29x29_22rhs_solve_attempts",
        "fit_shared_29x29_22rhs_solve_returns", "fit_shared_29x29_22rhs_solve_failures",
        "transition_scalar_coefficients_fitted", "transition_heads_published",
        "D11_restoration_attempts", "D11_restoration_returns",
        "D11_pair_prediction_attempts", "D11_pair_prediction_returns", "D11_pair_prediction_failures",
        "D11_scalar_prediction_attempts", "D11_scalar_prediction_returns",
        "D11_unknown_scalar_prediction_failures", "seed_fit_failures",
        "cold22_transition_attempts", "cold22_transition_returns", "cold22_transition_failures",
        "learned22_transition_attempts", "learned22_transition_returns", "learned22_transition_failures")})
    inputs, sources, payloads = {}, None, {}
    parameters, prediction_records, unavailable, restorations = [], [], [], []
    source_counts, fingerprints = {}, {}
    def write(name, data):
        (output/name).write_bytes(data)
        payloads[name] = {"bytes": len(data), "sha256": digest(data)}
    def flush_records():
        write("parameters.json", json_bytes(parameters))
        write("D11_restorations.json", json_bytes(restorations))
        write("predictions.jsonl", b"".join((json.dumps(r, ensure_ascii=False, allow_nan=False)+"\n").encode("utf-8") for r in prediction_records))
        write("unavailable.json", json_bytes(unavailable))
    try:
        repo = Path(args.repo).resolve()
        sources = frozen_sources(repo, args.source_commit, cost)
        blobs, docs, cmeta = read_inputs(repo, inputs, cost)
        models = restore_models(docs[f"{D_ROOT}/raw/diagnostics.json"], repo, cost, restorations)
        fingerprints = {s: model.parameter_fingerprint() for s, model in models.items()}
        trials, source_counts = parse_trials(blobs[f"{C_ROOT}/trace.jsonl.gz"], cost)
        qrefs, weights = {}, {}
        for seed in SEEDS:
            qref, qref_id = prefix_qref(trials[f"seed{seed}_calibration_sparse"])
            prediction_ref, prediction_ref_id = prefix_qref(trials[f"seed{seed}_prediction"])
            if tuple(qref[:2]) != models[seed].qref or prediction_ref != qref:
                raise ValueError("calibration eight-axis qref/D pair/prediction prefix mismatch")
            qrefs[seed] = qref
            record = {"seed": seed, "available": False, "fixed_lambda": RIDGE,
                "state_order": STATE_NAMES, "feature_order": FEATURE_NAMES, "qref8": qref,
                "qref_source_transition_id": qref_id, "prediction_prefix_check_transition_id": prediction_ref_id,
                "D11_parameter_fingerprint": fingerprints[seed], "same_C400_already_used_by_D": True,
                "training_transition_ids": [], "training_prior400x22": [],
                "prior_position_integration": "current_velocity", "learning_class": "batch_ridge_not_RLS"}
            parameters.append(record)
            # Retain generated labels/design even if fitting is interrupted.
            design, labels = [], []
            record["generated_phi_rows29"], record["generated_delta_label_rows22"] = design, labels
            try:
                rows = trials[f"seed{seed}_calibration_sparse"]
                for origin in range(400):
                    try:
                        active, past, requests, previous_v = window(rows, origin, 1)
                        row = active[0]
                        x = encode_state(row["observation_before"], qref, cost)
                        phi, prior = feature_and_prior(x, previous_v, requests[0], qref, models[seed].public_guard, cost, "fit")
                        actual = encode_state(row["observation_after"], qref, cost)
                        with np.errstate(over="ignore", invalid="ignore"):
                            delta = actual-prior
                        finite_array(delta, (22,))
                        design.append(phi.tolist())
                        labels.append(delta.tolist())
                        cost["generated_fit_scalar_labels"] += 22
                        record["training_prior400x22"].append(prior.tolist())
                        record["training_transition_ids"].append(row["shared_transition_id"])
                    except (KeyError, TypeError, ValueError) as exc:
                        unavailable.append({"seed": seed, "kind": "calibration_sparse", "origin": origin,
                                            "reason": f"{type(exc).__name__}:{exc}"})
                record["training_usable_count"] = len(design)
                record["training_source_active_count"] = source_counts.get(f"seed{seed}_calibration_sparse", 0)
                if len(design) != 400 or record["training_source_active_count"] != 400:
                    raise ValueError("complete_fixed_training400_unavailable")
                weights[seed], fit_record = fit_transition(design, labels, cost)
                record.update(available=True, fit=fit_record,
                    parameter_fingerprint=digest(json_bytes({"qref8": qref, "weights29x22": weights[seed].tolist(),
                                                             "lambda": RIDGE, "feature_order": FEATURE_NAMES})))
            except Exception as exc:
                cost["seed_fit_failures"] += 1
                record["failure"] = f"{type(exc).__name__}:{exc}"
            flush_records()
        for seed in SEEDS:
            rows, qref = trials[f"seed{seed}_prediction"], qrefs[seed]
            for horizon in HORIZONS:
                for origin in range(101-horizon):
                    common = {"seed": seed, "trial_id": f"seed{seed}_prediction", "origin": origin,
                              "horizon": horizon, "offline_saved_future_requests": True}
                    try:
                        active, past, requests, previous_v = window(rows, origin, horizon)
                        observation = active[0]["observation_before"]
                        initial = encode_state(observation, qref, cost)
                        q, v = native(observation)[:2]
                        common.update(initial_x22=initial.tolist(), previous_v2=previous_v,
                            history_transition_ids=[r["shared_transition_id"] for r in past],
                            requested_transition_ids=[r["shared_transition_id"] for r in active],
                            requested_sequence8=requests, source_stopped_at_endpoint=stopped(active[-1]))
                    except (KeyError, TypeError, ValueError) as exc:
                        reason = f"window_unavailable:{type(exc).__name__}:{exc}"
                        unavailable.append({**common, "reason": reason})
                        prediction_records.extend({**common, "predictor": name, "available": False, "reason": reason} for name in PREDICTORS)
                        continue
                    outcomes = {}
                    current_records = []
                    for name in PREDICTORS:
                        if name == "D11":
                            outcome = rollout11(models[seed], q, v, previous_v, requests, cost)
                        elif name == "learned22" and seed not in weights:
                            outcome = {"available": False, "reason": "seed_transition_parameters_unavailable"}
                        else:
                            outcome = rollout22(initial, previous_v, requests, qref, models[seed].public_guard,
                                                weights.get(seed) if name == "learned22" else None, cost, name)
                        outcomes[name] = outcome
                        record = {**common, "predictor": name, **outcome, "scored": False}
                        prediction_records.append(record)
                        current_records.append(record)
                    # This is the first scoring use of the future endpoint, after every rollout.
                    actual = encode_state(active[-1]["observation_after"], qref, cost)
                    actual_q, actual_v = native(active[-1]["observation_after"])[:2]
                    for record in current_records:
                        name = record["predictor"]
                        if record["available"]:
                            if name == "D11":
                                predicted_q, predicted_v = record["terminal_qv"]
                                errors = {str(i): actual_q[i]-predicted_q[i] for i in range(2)}
                                errors.update({str(8+i): actual_v[i]-predicted_v[i] for i in range(2)})
                            else:
                                errors = {str(i): float(actual[i]-record["terminal_x22"][i]) for i in range(22)}
                            if not all(math.isfinite(error) for error in errors.values()):
                                cost["terminal_score_validation_failures"] += 1
                                record.update(available=False, reason="nonfinite_terminal_error")
                            else:
                                cost["score_scalar_error_calculations"] += len(errors)
                                record.update(scored=True, actual_endpoint_x22=actual.tolist(), terminal_errors_x22=errors)
                flush_records()
        after_fingerprints = {s: model.parameter_fingerprint() for s, model in models.items()}
        if after_fingerprints != fingerprints:
            raise ValueError("frozen_D11_mutated")
        groups = summarize(prediction_records, source_counts)
        gate = development_gate(groups)
        write("metrics.json", json_bytes({"groups": groups, "development_gate": gate,
            "scientific_adoption": False, "c4_scientific_validation": False,
            "c5_scientific_dependency_released": False, "no_IMU_causal_attribution": True}))
        cost["wall_seconds"], cost["cpu_seconds"] = time.perf_counter()-start_wall, time.process_time()-start_cpu
        run = {"status": "completed", "scientific_adoption": False, "development_gate_passed": gate["passed"],
            "inputs": inputs, "source": sources, "original_source_commits": {"C": C_COMMIT, "D": D_COMMIT},
            "original_C_dependencies": cmeta.get("dependencies"), "source_active_counts": source_counts,
            "runtime": {"python": sys.version, "numpy": np.__version__, "platform": platform.platform()},
            "D11_fingerprints_before": fingerprints, "D11_fingerprints_after": after_fingerprints,
            "cost": dict(cost), "timing_excludes": "final run/manifest serialization and write",
            "compute_classification": "new batch ridge closed native transition from reused paid C400; D11 restored frozen and recursively re-predicted; zero new physics/RLS"}
        write("run.json", json_bytes(run))
        (output/"manifest.json").write_bytes(json_bytes({"schema_version": 1, "status": "completed",
            "scientific_adoption": False, "files": payloads}))
        return run
    except BaseException as exc:
        flush_records()
        cost["wall_seconds"], cost["cpu_seconds"] = time.perf_counter()-start_wall, time.process_time()-start_cpu
        write("failure.json", json_bytes({"status": "failed", "exception_type": type(exc).__name__, "message": str(exc),
            "requested_K_source_commit": args.source_commit, "expected_original_source_commits": {"C": C_COMMIT, "D": D_COMMIT},
            "expected_input_pins": PINS, "inputs_already_read": inputs,
            "inputs_without_returned_read_record": {name: "unknown_before_input_record_returned" for name in PINS if name not in inputs},
            "source_already_verified": sources if sources is not None else {
                "status": "unknown", "reason": "source verifier did not return verified binding"},
            "source_active_counts": source_counts, "D11_fingerprints_before": fingerprints,
            "cost": dict(cost), "scientific_adoption": False, "development_gate_passed": False,
            "c4_scientific_validation": False, "c5_scientific_dependency_released": False}))
        (output/"manifest.json").write_bytes(json_bytes({"schema_version": 1, "status": "failed",
                                                        "scientific_adoption": False, "files": payloads}))
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".")
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--output", required=True)
    print(json.dumps(main_run(parser.parse_args()), ensure_ascii=False, indent=2, allow_nan=False))
