"""J: fixed six-channel native IMU one-step residual development, no control."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
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


SOURCE_PATH = "scripts/develop_guard_imu_residual.py"
PROTOCOL_PATH = "docs/GUARD_IMU_RESIDUAL_DEVELOPMENT_PROTOCOL.md"
HELPERS = ("src/developmental_physics/__init__.py", "src/developmental_physics/guard_lag_pair_model.py",
           "src/developmental_physics/guard_pair_model.py", "src/developmental_physics/local_pair_model.py",
           "src/developmental_physics/local_model.py")
C_ROOT = "results/cpu_validation/2026-10-11_guard_exploration/raw"
D_ROOT = "results/cpu_validation/2026-10-11_guard_lag_offline"
G_ROOT = "results/cpu_validation/2026-10-11_guard_pd_tail_control/raw"
C_COMMIT = "5ea8df42b09588845760daf0dc1f270aef2a87f1"
D_COMMIT = "f7710c7b048dccab3e436d1fa16432f881a35992"
G_COMMIT = "91dcf6c111a87427c8f3fdd8b959d4792b1bb5a2"
PINS = {
    f"{C_ROOT}/manifest.json": "fa7fb57c5b996ae77862c1e7d59d22af72376947af38409601444f25139f042e",
    f"{C_ROOT}/metadata.json": "2c0be03255858d7511d1e238b5eb491a6618f197f12810ea9e0b00a64d279b57",
    f"{C_ROOT}/trace.jsonl.gz": "1b299c9bc7a91f8ff9dfef3f77ac1b6fea923dea6057327bb3f9aa1ce6f56ad0",
    f"{D_ROOT}/manifest.json": "38df6b99e15c3667a33d6c9995a8efd664f70ce59be8a511fa49def59727a4d7",
    f"{D_ROOT}/raw/manifest.json": "f5d6e0fc017d708a8c8b2b03a6876704248afee92266985ebd5d137267acb3c6",
    f"{D_ROOT}/raw/diagnostics.json": "9307f3f37d5a3c23ef6f9097d8c352a9fc7f2e34e562b5cf4e7075e20bbbe130",
    f"{G_ROOT}/manifest.json": "7eff4abb7cbe9c42a66d59615939a63a491c56fe87b5271d4ff4836d7b220a4c",
    f"{G_ROOT}/metadata.json": "8699b496287d80bdfb418e24625636c6b588e580869f40b17bcc345baab79f0a",
    f"{G_ROOT}/trace.jsonl.gz": "d7318127751270401198a5e2764a5b70faea2e4d881223fe38f20200828b526d",
}
SEEDS = (0, 1, 2)
G_KINDS = ("cold11", "learned_sparse11", "PDselected", "zero")
FEATURES = ("gyro_x/1", "gyro_y/1", "gyro_z/1", "accel_x/9.81", "accel_y/9.81", "accel_z/9.81")
RIDGE, DT = .01, .02


def digest(data):
    return hashlib.sha256(data).hexdigest()


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+"\n").encode("utf-8")


def vector(value, size):
    if not isinstance(value, (list, tuple)) or len(value) != size:
        raise ValueError(f"expected finite vector of length {size}")
    if any(type(x) not in (int, float) or not math.isfinite(x) for x in value):
        raise ValueError("nonfinite or nonnumeric native vector")
    return tuple(float(x) for x in value)


def native(observation):
    return tuple(vector(observation[key], 8)[:2] for key in ("joint_position", "joint_velocity"))


def imu_feature(observation_before):
    """Exactly six current channels; no labels, centering, filter or bias."""
    gyro = vector(observation_before["imu_gyro"], 3)
    acceleration = vector(observation_before["imu_acceleration"], 3)
    return np.asarray([*(x/1. for x in gyro), *(x/9.81 for x in acceleration)], dtype=np.float64)


def complete(row):
    return row.get("diagnostics", {}).get("executed_substeps") == 10


def stopped(row):
    return row.get("study_abort") is not None or row.get("diagnostics", {}).get("terminated", False)


def continuous(previous, current):
    return (previous["trial_id"] == current["trial_id"]
            and previous["step_index"]+1 == current["step_index"]
            and complete(previous) and complete(current) and not stopped(previous)
            and native(previous["observation_after"]) == native(current["observation_before"]))


def extract_sample(row, past, collection):
    """Pure native extraction. Current after endpoint is only a label."""
    if not complete(row):
        raise ValueError("partial_interval")
    if len(past) != 2 or not continuous(past[0], past[1]) or not continuous(past[1], row):
        raise ValueError("missing_or_discontinuous_past_two_native_endpoints")
    q, v = native(row["observation_before"])
    previous_v = native(past[0]["observation_after"])[1]
    phi = imu_feature(row["observation_before"])
    actual = native(row["observation_after"])
    request = vector(row["requested_torque"], 8)[:2]
    step = row["step_index"]
    if type(step) is not int or step < 100:
        raise ValueError("invalid_active_index")
    return {"collection": collection, "trial_id": row["trial_id"], "seed": row["seed"],
            "kind": row["kind"], "step_index": step, "active_index": step-100,
            "transition_id": row["shared_transition_id"], "history_transition_ids": [r["shared_transition_id"] for r in past],
            "q": q, "v": v, "previous_v": previous_v, "requested_u": request,
            "phi": phi.tolist(), "actual_qv": actual, "source_stopped_here": bool(stopped(row)),
            "available": True}


def collect_samples(blob, collection, fingerprints, cost):
    histories, latched, samples, unavailable = {}, set(), [], []
    source_counts = Counter()
    with gzip.GzipFile(fileobj=io.BytesIO(blob), mode="rb") as stream:
        for line in stream:
            cost[f"{collection}_trace_uncompressed_bytes"] += len(line)
            row = json.loads(line)
            cost[f"{collection}_trace_lines_parsed"] += 1
            kind, trial = row.get("kind"), row.get("trial_id")
            if row.get("seed") not in SEEDS or (collection == "C" and kind not in ("calibration_sparse", "prediction")) or (collection == "G" and kind not in G_KINDS):
                continue
            if trial != f"seed{row['seed']}_{kind}":
                raise ValueError("fixed trial identity mismatch")
            active_phase = "calibration" if kind == "calibration_sparse" else "prediction" if kind == "prediction" else "control"
            past = histories.setdefault(trial, [])
            if row.get("phase") == active_phase:
                source_counts[trial] += 1
                try:
                    if trial in latched:
                        raise ValueError("after_source_stop")
                    item = extract_sample(row, past, collection)
                    cost["imu_feature_vectors"] += 1
                    cost["imu_feature_scalar_divisions"] += 6
                    if collection == "G":
                        name = "learned_sparse11"
                        inputs = row.get("model_input_diagnostics", {}).get(name, {})
                        if (row.get("model_fingerprints", {}).get(name) != fingerprints[row["seed"]]
                                or tuple(inputs.get("native_q_rad", ())) != item["q"]
                                or tuple(inputs.get("native_v_rad_s", ())) != item["v"]
                                or tuple(inputs.get("requested_nm", ())) != item["requested_u"]
                                or tuple(inputs.get("previous_v_rad_s", ())) != item["previous_v"]
                                or inputs.get("history_transition_ids") != item["history_transition_ids"]):
                            raise ValueError("G_saved_base_fingerprint_or_current_input_mismatch")
                        saved = row.get("predicted_next_qv", {}).get(name)
                        item["base_qv"] = tuple(vector(pair, 2) for pair in saved) if saved is not None and len(saved) == 2 else None
                        if item["base_qv"] is None:
                            raise ValueError("G_saved_independent_base_prediction_missing")
                        cost["saved_base_prediction_reuses"] += 1
                    samples.append(item)
                except (KeyError, TypeError, ValueError) as exc:
                    unavailable.append({"collection": collection, "trial_id": trial, "seed": row["seed"],
                                        "kind": kind, "step_index": row.get("step_index"), "reason": str(exc),
                                        "source_stopped_here": bool(stopped(row)), "available": False})
            if stopped(row):
                latched.add(trial)
            # Never repair partial/missing native history with zero or another trial.
            try:
                native(row["observation_before"]), native(row["observation_after"])
                histories[trial] = (past+[row])[-2:] if complete(row) else []
            except (KeyError, TypeError, ValueError):
                histories[trial] = []
    return samples, unavailable, dict(source_counts)


def fit_residual(phi, labels, cost):
    """One batch ridge solve, shared design and two right-hand sides."""
    phi, labels = np.asarray(phi, dtype=np.float64), np.asarray(labels, dtype=np.float64)
    if phi.shape != (400, 6) or labels.shape != (400, 2) or not np.isfinite(phi).all() or not np.isfinite(labels).all():
        raise ValueError("exact finite 400x6 design and 400x2 labels required")
    cost["fit_scalar_labels"] += labels.size
    cost["fit_gram_matrix_products"] += 1
    gram = phi.T @ phi
    cost["fit_cross_matrix_products"] += 1
    cross = phi.T @ labels
    cost["ridge_identity_matrix_additions"] += 1
    normal = gram + RIDGE*np.eye(6, dtype=np.float64)
    cost["fit_shared_6x6_two_rhs_solve_attempts"] += 1
    try:
        weights = np.linalg.solve(normal, cross)
    except Exception:
        cost["fit_shared_6x6_two_rhs_solve_failures"] += 1
        raise
    cost["fit_shared_6x6_two_rhs_solve_returns"] += 1
    if weights.shape != (6, 2) or not np.isfinite(weights).all():
        raise ValueError("nonfinite residual parameters")
    cost["residual_heads_published"] += 2
    cost["residual_scalar_coefficients_fitted"] += 12
    return weights, {"phi": phi.tolist(), "labels_actual_minus_frozen_base_v": labels.tolist(),
                     "gram": gram.tolist(), "cross": cross.tolist(), "ridge_normal_matrix": normal.tolist(),
                     "weights_6x2": weights.tolist(), "zero_prior": True, "extra_intercept": False}


def apply_residual(base_qv, phi, weights, cost):
    cost["residual_forward_vector_evaluations"] += 1
    cost["residual_forward_scalar_heads"] += 2
    residual = np.asarray(phi, dtype=np.float64) @ weights
    corrected = [[base_qv[0][i]+DT*float(residual[i]) for i in range(2)],
                 [base_qv[1][i]+float(residual[i]) for i in range(2)]]
    if not np.isfinite(corrected).all():
        raise ValueError("nonfinite residual prediction")
    cost["corrected_v_scalar_additions"] += 2
    cost["corrected_q_scalar_multiplications"] += 2
    cost["corrected_q_scalar_additions"] += 2
    return residual.tolist(), corrected


def metric(errors):
    if not errors:
        return {"count": 0, "rmse": None, "mae": None, "bias": None}
    n = len(errors)
    return {"count": n, "rmse": math.sqrt(math.fsum(x*x for x in errors)/n),
            "mae": math.fsum(abs(x) for x in errors)/n, "bias": math.fsum(errors)/n}


def summarize(scored, source_counts):
    groups = []
    fixed = [("C", f"seed{s}_{k}", s, k, "ALL") for s in SEEDS for k in ("calibration_sparse", "prediction")]
    fixed += [("G", f"seed{s}_{k}", s, k, segment) for s in SEEDS for k in G_KINDS for segment in ("ALL", "A", "B")]
    for collection, trial, seed, kind, segment in fixed:
        own = [r for r in scored if r["collection"] == collection and r["trial_id"] == trial and
               (segment == "ALL" or ("A" if r["active_index"] < 100 else "B") == segment)]
        for signal_index, signal in enumerate(("q", "v")):
            for axis in range(2):
                base, corrected = [metric([r["errors"][name][signal_index][axis] for r in own]) for name in ("base", "corrected")]
                improvement = None if base["rmse"] in (None, 0) else (base["rmse"]-corrected["rmse"])/base["rmse"]
                groups.append({"collection": collection, "trial_id": trial, "seed": seed, "kind": kind,
                               "segment": segment, "signal": signal, "axis": axis, "pair_count": len(own),
                               "source_active_count_ALL": source_counts.get(trial, 0), "base": base, "corrected": corrected,
                               "rmse_relative_improvement": improvement,
                               "mae_relative_improvement": None if base["mae"] in (None, 0) else (base["mae"]-corrected["mae"])/base["mae"],
                               "empty_reason": "no_complete_matched_predictions" if not own else None,
                               "method_ranking": False, "in_sample_fit_description": kind == "calibration_sparse"})
    return groups


def development_gate(groups):
    axes = []
    for axis in range(2):
        records = [next(g for g in groups if g["collection"] == "C" and g["kind"] == "prediction" and g["seed"] == seed and g["signal"] == "v" and g["axis"] == axis) for seed in SEEDS]
        valid = all(g["pair_count"] == 100 and g["source_active_count_ALL"] == 100 and g["rmse_relative_improvement"] is not None and math.isfinite(g["rmse_relative_improvement"]) for g in records)
        mean = math.fsum(g["rmse_relative_improvement"] for g in records)/3 if valid else None
        strict = valid and all(g["corrected"]["rmse"] < g["base"]["rmse"] for g in records)
        axes.append({"axis": axis, "evaluated": valid, "each_seed_strictly_improved": strict,
                     "mean_relative_improvement": mean, "passed": bool(strict and mean >= .20),
                     "reason": None if valid else "missing_full_100_or_zero_base_or_undefined",
                     "seed_records": records})
    return {"scope": "seen_C_common_prediction_only", "metric": "velocity_RMSE",
            "axes": axes, "evaluated": all(a["evaluated"] for a in axes),
            "passed": all(a["passed"] for a in axes), "scientific_adoption": False}


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
    cmeta, gmeta = docs[f"{C_ROOT}/metadata.json"], docs[f"{G_ROOT}/metadata.json"]
    for metadata, commit in ((cmeta, C_COMMIT), (gmeta, G_COMMIT)):
        if metadata.get("source_commit") != commit or metadata.get("source_dirty") is not False or metadata.get("seeds") != list(SEEDS):
            raise ValueError("original collection source identity mismatch")
    if cmeta.get("synthetic") is not False or gmeta.get("synthetic_fixture") is not False or gmeta.get("model_updates") != 0:
        raise ValueError("formal existing frozen input required")
    if gmeta.get("D_binding", {}).get("collection_commit") != D_COMMIT:
        raise ValueError("G published D source identity mismatch")
    for root in (C_ROOT, G_ROOT):
        manifest = docs[f"{root}/manifest.json"]
        for name in ("metadata.json", "trace.jsonl.gz"):
            expected = manifest[name] if root == C_ROOT else manifest["files"][name]["sha256"]
            if expected != records[f"{root}/{name}"]["sha256"]:
                raise ValueError("original raw manifest payload mismatch")
    if docs[f"{D_ROOT}/raw/manifest.json"].get("status") != "completed":
        raise ValueError("D published raw status incomplete")
    for relative in ("raw/manifest.json", "raw/diagnostics.json"):
        record = docs[f"{D_ROOT}/manifest.json"]["files"][relative]
        if any(record[k] != records[f"{D_ROOT}/{relative}"][k] for k in ("bytes", "sha256")):
            raise ValueError("D root manifest payload mismatch")
    return blobs, docs, cmeta, gmeta


def frozen_sources(repo, commit, cost):
    if len(commit) != 40 or any(c not in "0123456789abcdef" for c in commit) or Path(__file__).resolve() != (repo/SOURCE_PATH).resolve():
        raise ValueError("exact J commit and canonical source path required")
    def git(*args):
        result = subprocess.run(["git", *args], cwd=repo, capture_output=True, check=False)
        cost["git_queries"] += 1
        cost["git_return_bytes"] += len(result.stdout)+len(result.stderr)
        if result.returncode:
            raise ValueError("Git read-only source verification failed")
        return result.stdout
    if git("rev-parse", "HEAD").decode().strip() != commit or git("status", "--porcelain", "--untracked-files=no").strip():
        raise ValueError("clean exact J HEAD required")
    sources = {}
    for name in (SOURCE_PATH, PROTOCOL_PATH, *HELPERS):
        data = (repo/name).read_bytes()
        cost["source_file_reads"] += 1
        cost["source_raw_bytes"] += len(data)
        sources[name] = {"bytes": len(data), "sha256": digest(data)}
        if git("show", f"{commit}:{name}") != data:
            raise ValueError(f"J source byte mismatch: {name}")
    return {"commit": commit, "files": sources, "clean_committed_bytes_verified": True}


def restore_models(diagnostics, repo, cost):
    sys.path.insert(0, str(repo/"src"))
    from developmental_physics.guard_lag_pair_model import GuardLagPairBodyModel
    from developmental_physics.local_pair_model import _parameter_state
    models = {}
    for seed in SEEDS:
        cost["frozen_base_restoration_attempts"] += 1
        matches = [r for r in diagnostics if r.get("seed") == seed and r.get("calibration") == "sparse"]
        if len(matches) != 1:
            raise ValueError("exactly one D sparse snapshot per seed required")
        snapshot = matches[0]["lag11_final_snapshot"]
        if snapshot.get("vector_update_count") != 400 or snapshot.get("scalar_update_count") != 800:
            raise ValueError("D complete 400-vector base required")
        model = GuardLagPairBodyModel(snapshot["qref_rad"], public_joint_ranges=snapshot["input_mapping"]["public_guard"]["public_joint_ranges_rad"], trainable=False)
        theta, covariance = (np.asarray(snapshot[key], dtype=np.float64) for key in ("coefficients", "covariance"))
        if theta.shape != (2, 11) or covariance.shape != (2, 11, 11) or not np.isfinite(theta).all() or not np.isfinite(covariance).all():
            raise ValueError("D complete finite base state required")
        model._state = _parameter_state(theta.copy(), covariance.copy(), 400)
        expected = dict(snapshot)
        expected["trainable"] = False
        if model.snapshot() != expected:
            raise ValueError("D snapshot/fingerprint/constants mismatch")
        models[seed] = model
        cost["frozen_base_restoration_returns"] += 1
        cost["frozen_base_restorations"] += 1
    return models


def main_run(args):
    output = Path(args.output).resolve()
    if output.exists():
        raise FileExistsError("new J output required; no overwrite/rerun")
    output.mkdir(parents=True)
    start_wall, start_cpu = time.perf_counter(), time.process_time()
    cost = Counter({key: 0 for key in (
        "physics_calls", "MPC_calls", "base_model_updates", "RLS_updates", "input_file_reads",
        "input_raw_bytes", "input_hash_bytes", "json_documents_parsed", "source_file_reads",
        "source_raw_bytes", "git_queries", "git_return_bytes", "frozen_base_restorations",
        "frozen_base_restoration_attempts", "frozen_base_restoration_returns",
        "C_trace_uncompressed_bytes", "G_trace_uncompressed_bytes", "C_trace_lines_parsed",
        "G_trace_lines_parsed", "imu_feature_vectors", "imu_feature_scalar_divisions",
        "base_model_pair_attempts", "base_model_pair_returns", "base_model_pair_failures",
        "base_model_scalar_attempts", "base_model_scalar_returns", "base_model_unknown_scalar_failures",
        "saved_base_prediction_reuses", "fit_scalar_labels", "fit_gram_matrix_products",
        "fit_cross_matrix_products", "ridge_identity_matrix_additions",
        "fit_shared_6x6_two_rhs_solve_attempts", "fit_shared_6x6_two_rhs_solve_returns",
        "fit_shared_6x6_two_rhs_solve_failures", "residual_heads_published",
        "residual_scalar_coefficients_fitted", "seed_fit_failures", "residual_forward_vector_evaluations",
        "residual_forward_scalar_heads", "corrected_v_scalar_additions",
        "corrected_q_scalar_multiplications", "corrected_q_scalar_additions", "score_scalar_error_calculations")})
    inputs, sources, payloads = {}, None, {}
    def write(name, data):
        (output/name).write_bytes(data)
        payloads[name] = {"bytes": len(data), "sha256": digest(data)}
    try:
        repo = Path(args.repo).resolve()
        sources = frozen_sources(repo, args.source_commit, cost)
        blobs, docs, cmeta, gmeta = read_inputs(repo, inputs, cost)
        models = restore_models(docs[f"{D_ROOT}/raw/diagnostics.json"], repo, cost)
        fingerprints = {s: m.parameter_fingerprint() for s, m in models.items()}
        samples, unavailable, source_counts = [], [], {}
        for collection, root in (("C", C_ROOT), ("G", G_ROOT)):
            items, missing, counts = collect_samples(blobs[f"{root}/trace.jsonl.gz"], collection, fingerprints, cost)
            samples.extend(items)
            unavailable.extend(missing)
            source_counts.update(counts)
        for item in samples:
            if item["collection"] != "C":
                continue
            cost["base_model_pair_attempts"] += 1
            try:
                prediction = models[item["seed"]].predict(item["q"], item["v"], item["requested_u"], item["previous_v"])
                cost["base_model_pair_returns"] += 1
                cost["base_model_scalar_attempts"] += 2
                cost["base_model_scalar_returns"] += 2
            except Exception as exc:
                cost["base_model_pair_failures"] += 1
                if hasattr(exc, "scalar_prediction_attempts"):
                    cost["base_model_scalar_attempts"] += exc.scalar_prediction_attempts
                    cost["base_model_scalar_returns"] += exc.scalar_prediction_successes
                else:
                    cost["base_model_unknown_scalar_failures"] += 1
                item.update(available=False, reason=f"base_prediction_failure:{type(exc).__name__}:{exc}")
                continue
            try:
                if len(prediction) != 2:
                    raise ValueError("base must return q_pair/v_pair")
                item["base_qv"] = tuple(vector(pair, 2) for pair in prediction)
            except (TypeError, ValueError) as exc:
                cost["base_prediction_output_validation_failures"] += 1
                item.update(available=False, reason=f"base_output_validation_failure:{exc}")
        parameters, weights = [], {}
        for seed in SEEDS:
            train = [r for r in samples if r["collection"] == "C" and r["kind"] == "calibration_sparse" and r["seed"] == seed and r["available"]]
            record = {"seed": seed, "available": False, "training_pair_count": len(train),
                      "fixed_lambda": RIDGE, "feature_order": FEATURES,
                      "same_400_data_already_used_by_D_base": True, "base_fingerprint": fingerprints[seed]}
            try:
                if len(train) != 400 or source_counts.get(f"seed{seed}_calibration_sparse") != 400:
                    raise ValueError("complete fixed training400 unavailable")
                labels = [[r["actual_qv"][1][i]-r["base_qv"][1][i] for i in range(2)] for r in train]
                weights[seed], fit_record = fit_residual([r["phi"] for r in train], labels, cost)
                record.update(available=True, fit=fit_record, training_transition_ids=[r["transition_id"] for r in train])
            except Exception as exc:
                record["failure"] = f"{type(exc).__name__}:{exc}"
                cost["seed_fit_failures"] += 1
            parameters.append(record)
        scored, prediction_records = [], []
        for item in samples:
            record = dict(item)
            if not item["available"] or item["seed"] not in weights:
                record.update(corrected_available=False, correction_unavailable_reason=item.get("reason", "seed_residual_parameters_unavailable"))
            else:
                residual, corrected = apply_residual(item["base_qv"], item["phi"], weights[item["seed"]], cost)
                errors = {name: [[item["actual_qv"][signal][axis]-pred[signal][axis] for axis in range(2)] for signal in range(2)]
                          for name, pred in (("base", item["base_qv"]), ("corrected", corrected))}
                cost["score_scalar_error_calculations"] += 8
                record.update(corrected_available=True, imu_residual_v=residual, corrected_qv=corrected, errors=errors)
                scored.append(record)
            prediction_records.append(record)
        if {s: m.parameter_fingerprint() for s, m in models.items()} != fingerprints:
            raise ValueError("frozen D base mutated")
        groups = summarize(scored, source_counts)
        gate = development_gate(groups)
        write("parameters.json", json_bytes(parameters))
        write("predictions.jsonl", b"".join((json.dumps(r, ensure_ascii=False, allow_nan=False)+"\n").encode("utf-8") for r in prediction_records))
        write("unavailable.json", json_bytes(unavailable))
        write("metrics.json", json_bytes({"groups": groups, "development_gate": gate,
              "scientific_adoption": False, "G_method_ranking": False, "c4_scientific_validation": False,
              "c5_scientific_dependency_released": False}))
        cost["wall_seconds"] = time.perf_counter()-start_wall
        cost["cpu_seconds"] = time.process_time()-start_cpu
        run = {"status": "completed", "scientific_adoption": False, "development_gate_passed": gate["passed"],
               "inputs": inputs, "diagnostic_source": sources, "original_source_commits": {"C": C_COMMIT, "D": D_COMMIT, "G": G_COMMIT},
               "original_dependencies": {"C": cmeta.get("dependencies"), "G_saved_predictions": gmeta.get("dependencies")},
               "runtime": {"python": sys.version, "numpy": np.__version__, "platform": platform.platform()},
               "base_fingerprints": fingerprints, "cost": dict(cost),
               "timing_excludes": "final run and manifest serialization/write",
               "compute_classification": "new batch ridge residual learning from reused paid C400 data; frozen base; G saved independent predictions reused, not numerically recomputed"}
        write("run.json", json_bytes(run))
        (output/"manifest.json").write_bytes(json_bytes({"schema_version": 1, "status": "completed", "scientific_adoption": False, "files": payloads}))
        return run
    except BaseException as exc:
        cost["wall_seconds"] = time.perf_counter()-start_wall
        cost["cpu_seconds"] = time.process_time()-start_cpu
        write("failure.json", json_bytes({"status": "failed", "exception_type": type(exc).__name__, "message": str(exc),
              "requested_J_source_commit": args.source_commit,
              "expected_original_source_commits": {"C": C_COMMIT, "D": D_COMMIT, "G": G_COMMIT},
              "expected_input_pins": PINS, "inputs_already_read": inputs,
              "inputs_without_returned_read_record": {name: "unknown_before_input_record_returned" for name in PINS if name not in inputs},
              "source_already_verified": sources if sources is not None else {
                  "status": "unknown", "reason": "source verifier did not return a verified binding"},
              "cost": dict(cost), "scientific_adoption": False}))
        (output/"manifest.json").write_bytes(json_bytes({"schema_version": 1, "status": "failed", "files": payloads}))
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".")
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--output", required=True)
    print(json.dumps(main_run(parser.parse_args()), ensure_ascii=False, indent=2, allow_nan=False))
