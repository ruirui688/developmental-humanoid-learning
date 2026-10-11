"""L: fixed C400 + saved G PD200 native-transition development, offline only."""
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

import numpy as np


SOURCE_PATH = "scripts/develop_guard_native_augmentation.py"
PROTOCOL_PATH = "docs/GUARD_NATIVE_AUGMENTATION_DEVELOPMENT_PROTOCOL.md"
CORE_PATH = "scripts/develop_guard_native_transition.py"
CORE_SHA = "f910bb6fd9f01ebf5fd52426b40b43414e50bebcfe6460cf6132bccb1a2192bb"
HELPERS = (CORE_PATH, "docs/GUARD_NATIVE_TRANSITION_DEVELOPMENT_PROTOCOL.md",
           "src/developmental_physics/__init__.py", "src/developmental_physics/guard_lag_pair_model.py",
           "src/developmental_physics/guard_pair_model.py", "src/developmental_physics/local_pair_model.py",
           "src/developmental_physics/local_model.py")
C_ROOT = "results/cpu_validation/2026-10-11_guard_exploration/raw"
D_ROOT = "results/cpu_validation/2026-10-11_guard_lag_offline"
G_ROOT = "results/cpu_validation/2026-10-11_guard_pd_tail_control/raw"
K_ROOT = "results/cpu_validation/2026-10-11_guard_native_transition/raw"
COMMITS = {"C": "5ea8df42b09588845760daf0dc1f270aef2a87f1",
           "D": "f7710c7b048dccab3e436d1fa16432f881a35992",
           "G": "91dcf6c111a87427c8f3fdd8b959d4792b1bb5a2",
           "K": "b46c6d37fddc8e6534384168fb76663bc2c5236c"}
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
    f"{K_ROOT}/manifest.json": "f8bf006eac1615e2a1bee801926c6157f265836011a847c24d19fe0f7341a588",
    f"{K_ROOT}/run.json": "1ea85a61e1b6ecbc43770c52ce6a3435c0e4d919d8af5fc91bc317b7abc84b3e",
    f"{K_ROOT}/parameters.json": "1a5c426cfece2fe099ba2e13bfe6229ef7189f59870183620fcb1e1aa14de0aa",
}
SEEDS, HORIZONS, PREDICTORS = (0, 1, 2), (1, 2, 5, 15), ("K22", "L22", "D11")
RIDGE = .01


def digest(data):
    return hashlib.sha256(data).hexdigest()


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+"\n").encode("utf-8")


def file_identity_matches(binding, actual):
    """Archive annotations are allowed; both byte count and SHA must match."""
    return isinstance(binding, dict) and all(
        key in binding and binding[key] == actual[key] for key in ("bytes", "sha256"))


def frozen_sources(repo, commit, cost):
    if len(commit) != 40 or any(c not in "0123456789abcdef" for c in commit) or Path(__file__).resolve() != (repo/SOURCE_PATH).resolve():
        raise ValueError("exact L commit/canonical path required")
    def git(*args):
        result = subprocess.run(["git", *args], cwd=repo, capture_output=True, check=False)
        cost["git_queries"] += 1
        cost["git_return_bytes"] += len(result.stdout)+len(result.stderr)
        if result.returncode:
            raise ValueError("read-only source verification failed")
        return result.stdout
    if git("rev-parse", "HEAD").decode().strip() != commit or git("status", "--porcelain", "--untracked-files=no").strip():
        raise ValueError("clean exact L HEAD required")
    files = {}
    for name in (SOURCE_PATH, PROTOCOL_PATH, *HELPERS):
        data = (repo/name).read_bytes()
        cost["source_file_reads"] += 1
        cost["source_raw_bytes"] += len(data)
        files[name] = {"bytes": len(data), "sha256": digest(data)}
        if git("show", f"{commit}:{name}") != data:
            raise ValueError(f"L source byte mismatch: {name}")
    if files[CORE_PATH]["sha256"] != CORE_SHA:
        raise ValueError("published K mathematics changed")
    return {"commit": commit, "files": files, "clean_committed_bytes_verified": True}


def load_core(repo):
    """Import definitions only; never call K main/read_inputs/source verifier."""
    spec = importlib.util.spec_from_file_location("frozen_K_native_math", repo/CORE_PATH)
    core = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(core)
    return core


def read_inputs(repo, records, cost, sources):
    blobs = {}
    for name, expected in PINS.items():
        data = (repo/name).read_bytes()
        cost["input_file_reads"] += 1
        cost["input_raw_bytes"] += len(data)
        cost["input_hash_bytes"] += len(data)
        records[name] = {"bytes": len(data), "sha256": digest(data)}
        if records[name]["sha256"] != expected:
            raise ValueError(f"pinned input mismatch: {name}")
        blobs[name] = data
    docs = {name: json.loads(data) for name, data in blobs.items() if name.endswith(".json")}
    cost["json_documents_parsed"] += len(docs)
    cmeta, gmeta, krun = (docs[f"{root}/{name}"] for root, name in
                          ((C_ROOT, "metadata.json"), (G_ROOT, "metadata.json"), (K_ROOT, "run.json")))
    for meta, label, synthetic_key in ((cmeta, "C", "synthetic"), (gmeta, "G", "synthetic_fixture")):
        if (meta.get("source_commit") != COMMITS[label] or meta.get("source_dirty") is not False or
                meta.get(synthetic_key) is not False or meta.get("seeds") != list(SEEDS)):
            raise ValueError("C/G original clean formal identity mismatch")
    if [cmeta.get(k) for k in ("prefix_steps", "calibration_steps", "prediction_steps")] != [100, 400, 100]:
        raise ValueError("C fixed lengths mismatch")
    if (gmeta.get("status") != "completed" or gmeta.get("prefix_steps") != 100 or
            gmeta.get("control_steps_per_trial") != 200 or gmeta.get("model_updates") != 0 or
            gmeta.get("D_binding", {}).get("collection_commit") != COMMITS["D"] or
            gmeta.get("D_binding", {}).get("original_C_commit") != COMMITS["C"]):
        raise ValueError("G original source/length/D binding mismatch")
    for key in ("environment_config", "pose", "joint_indices", "native_joint_count", "model_input_basis",
                "mujoco_version", "dependencies", "pd_gains", "pd_binding"):
        if cmeta.get(key) is None or cmeta[key] != gmeta.get(key):
            raise ValueError(f"C/G fixed physics/action/PD identity mismatch: {key}")
    for name in ("src/developmental_physics/assets/ground_body.xml",
                 "src/developmental_physics/environment.py", "src/developmental_physics/guard_pair_model.py"):
        if cmeta["source_sha256"].get(name) is None or cmeta["source_sha256"][name] != gmeta["source_sha256"].get(name):
            raise ValueError("C/G public physical source mismatch")
    for name in ("metadata.json", "trace.jsonl.gz"):
        if docs[f"{C_ROOT}/manifest.json"][name] != records[f"{C_ROOT}/{name}"]["sha256"]:
            raise ValueError("C flat raw manifest mismatch")
        if docs[f"{G_ROOT}/manifest.json"]["files"][name] != records[f"{G_ROOT}/{name}"]:
            raise ValueError("G raw manifest mismatch")
    if docs[f"{D_ROOT}/raw/manifest.json"].get("status") != "completed":
        raise ValueError("D raw incomplete")
    for name in ("raw/manifest.json", "raw/diagnostics.json"):
        if not file_identity_matches(docs[f"{D_ROOT}/manifest.json"]["files"][name], records[f"{D_ROOT}/{name}"]):
            raise ValueError("D root/raw binding mismatch")
    if not file_identity_matches(docs[f"{D_ROOT}/raw/manifest.json"]["files"]["diagnostics.json"], records[f"{D_ROOT}/raw/diagnostics.json"]):
        raise ValueError("D diagnostic raw binding mismatch")
    kmanifest = docs[f"{K_ROOT}/manifest.json"]
    if kmanifest.get("status") != "completed" or krun.get("status") != "completed":
        raise ValueError("K first formal output incomplete")
    for name in ("run.json", "parameters.json"):
        if kmanifest["files"][name] != records[f"{K_ROOT}/{name}"]:
            raise ValueError("K output manifest mismatch")
    if (krun.get("source", {}).get("commit") != COMMITS["K"] or
            krun["source"].get("clean_committed_bytes_verified") is not True or
            krun.get("original_source_commits") != {key: COMMITS[key] for key in ("C", "D")}):
        raise ValueError("K published clean source identity mismatch")
    for name in HELPERS:
        if krun["source"]["files"][name] != sources["files"][name]:
            raise ValueError("frozen K mathematics/helper changed")
    for name, expected in PINS.items():
        if name.startswith(C_ROOT) or name.startswith(D_ROOT):
            if krun["inputs"][name]["sha256"] != expected:
                raise ValueError("K original C/D input binding mismatch")
    return blobs, docs, cmeta, gmeta, krun


def parse_PD_trials(blob, cost):
    """Only native G PDselected rows, with all task/update fields discarded."""
    trials, counts = {f"seed{s}_PDselected": {} for s in SEEDS}, Counter()
    with gzip.GzipFile(fileobj=io.BytesIO(blob), mode="rb") as stream:
        for line in stream:
            cost["G_trace_uncompressed_bytes"] += len(line)
            row = json.loads(line)
            cost["G_trace_lines_parsed"] += 1
            seed = row.get("seed")
            if seed not in SEEDS or row.get("kind") != "PDselected":
                continue
            trial, step = f"seed{seed}_PDselected", row.get("step_index")
            if row.get("trial_id") != trial or type(step) is not int or step < 0 or step in trials[trial]:
                raise ValueError("fixed G PD identity/index mismatch")
            phase = "prefix" if step < 100 else "control"
            if row.get("phase") != phase or row.get("shared_transition_id") != f"{trial}:{step}":
                raise ValueError("fixed G PD phase/transition mismatch")
            keys = ("joint_position", "joint_velocity", "imu_gyro", "imu_acceleration")
            observations = {name: {key: row[name][key] for key in keys}
                            for name in ("observation_before", "observation_after")}
            diagnostic = row.get("diagnostics", {})
            trials[trial][step] = {"trial_id": trial, "seed": seed, "kind": "PDselected", "step_index": step,
                "phase": phase, "shared_transition_id": row["shared_transition_id"],
                "requested_torque": row.get("requested_torque"), **observations, "study_abort": row.get("study_abort"),
                "diagnostics": {key: diagnostic.get(key) for key in ("executed_substeps", "terminated")}}
            if phase == "control":
                counts[trial] += 1
    return trials, dict(counts)


def qualified_training_windows(core, selected, counts, seed):
    """Fixed ordered400+200; each trial builds history from its own dictionary."""
    windows = []
    for collection, kind, number in (("C", "calibration_sparse", 400), ("G", "PDselected", 200)):
        trial = f"seed{seed}_{kind}"
        if counts.get(trial) != number:
            raise ValueError(f"full_fixed_{collection}_{number}_source_count_required")
        rows = selected[collection][trial]
        core.prefix_qref(rows)
        for origin in range(number):
            active, past, requests, previous_v = core.window(rows, origin, 1)
            row = active[0]
            if row["trial_id"] != trial or row["kind"] != kind or row["seed"] != seed:
                raise ValueError("mixed_or_cross_trial_training_identity")
            if core.stopped(row):
                raise ValueError("full_unstopped_training_trial_required")
            windows.append((collection, row, past, requests[0], previous_v))
    if len(windows) != 600:
        raise ValueError("full_fixed_600_training_windows_required")
    return windows


def restore_K(core, parameters, cost, records):
    restored = {}
    for seed in SEEDS:
        cost["K22_restoration_attempts"] += 1
        record = {"seed": seed, "attempted": True, "returned": False}
        records.append(record)
        matches = [r for r in parameters if r.get("seed") == seed]
        if len(matches) != 1:
            raise ValueError("exactly one published K seed required")
        source = matches[0]
        if (source.get("available") is not True or source.get("fixed_lambda") != RIDGE or
                source.get("training_usable_count") != 400 or source.get("training_source_active_count") != 400 or
                source.get("state_order") != list(core.STATE_NAMES) or source.get("feature_order") != list(core.FEATURE_NAMES)):
            raise ValueError("published K parameter definition mismatch")
        qref = core.vector(source["qref8"], 8)
        weights = core.finite_array(source["fit"]["weights29x22"], (29, 22)).copy()
        fingerprint = digest(json_bytes({"qref8": qref, "weights29x22": weights.tolist(),
                                         "lambda": RIDGE, "feature_order": core.FEATURE_NAMES}))
        if fingerprint != source.get("parameter_fingerprint"):
            raise ValueError("K parameter fingerprint mismatch")
        weights.setflags(write=False)
        restored[seed] = {"qref8": qref, "weights": weights, "fingerprint": fingerprint}
        record.update(returned=True, parameter_fingerprint=fingerprint, copied_scalar_coefficients=638,
                      refit=False, qref_source_transition_id=source["qref_source_transition_id"])
        cost["K22_restoration_returns"] += 1
        cost["K22_scalar_coefficients_copied"] += 638
    return restored


def fit600(core, phi, delta, cost, journal):
    """Only shape qualification changes from K; ridge arithmetic stays fixed."""
    phi, delta = core.finite_array(phi, (600, 29)), core.finite_array(delta, (600, 22))
    cost["fit_scalar_labels"] += delta.size
    cost["fit_gram_matrix_products"] += 1
    with np.errstate(over="ignore", invalid="ignore"):
        gram = phi.T @ phi
    cost["fit_cross_matrix_products"] += 1
    with np.errstate(over="ignore", invalid="ignore"):
        cross = phi.T @ delta
    cost["ridge_identity_matrix_additions"] += 1
    normal = gram+RIDGE*np.eye(29, dtype=np.float64)
    core.finite_array(normal, (29, 29)), core.finite_array(cross, (29, 22))
    journal.update(gram29x29=gram.tolist(), cross29x22=cross.tolist(), ridge_normal29x29=normal.tolist())
    cost["fit_shared_29x29_22rhs_solve_attempts"] += 1
    try:
        weights = np.linalg.solve(normal, cross)
    except BaseException:
        cost["fit_shared_29x29_22rhs_solve_failures"] += 1
        raise
    cost["fit_shared_29x29_22rhs_solve_returns"] += 1
    try:
        weights = core.finite_array(weights, (29, 22))
    except ValueError:
        cost["fit_parameter_validation_failures"] += 1
        raise
    journal["weights29x22"] = weights.tolist()
    cost["transition_heads_published"] += 22
    cost["transition_scalar_coefficients_fitted"] += weights.size
    return weights


def summarize(core, records, source_counts):
    groups = []
    for seed in SEEDS:
        for horizon in HORIZONS:
            expected = 101-horizon
            for name in PREDICTORS:
                own = [r for r in records if (r["seed"], r["horizon"], r["predictor"]) == (seed, horizon, name)]
                good = [r for r in own if r["available"] and r.get("scored")]
                for channel in (range(22) if name != "D11" else (0, 1, 8, 9)):
                    groups.append({"seed": seed, "horizon": horizon, "predictor": name, "channel_index": channel,
                        "channel": core.STATE_NAMES[channel], "fixed_origin_count": expected,
                        "record_count": len(own), "usable_count": len(good), "unavailable_count": len(own)-len(good),
                        "full_fixed_count": len(own) == len(good) == expected,
                        "source_active_count": source_counts.get(f"seed{seed}_prediction", 0),
                        "metric": core.metric([r["terminal_errors_x22"][str(channel)] for r in good]),
                        "partial_subset_method_ranking": False})
    return groups


def development_gate(groups, baseline):
    if baseline not in ("K22", "D11"):
        raise ValueError("fixed K22/D11 gate baseline required")
    lookup = {(r["seed"], r["horizon"], r["predictor"], r["channel_index"]): r for r in groups}
    counts_ok = all(r["full_fixed_count"] and r["source_active_count"] == 100 for r in groups)
    checks = []
    for horizon in HORIZONS:
        for signal, channels in (("q", (0, 1)), ("v", (8, 9))):
            if horizon == 1 and signal == "q":
                continue
            strict20 = (horizon == 1 and signal == "v") or (horizon == 15 and signal == "q")
            for axis, channel in enumerate(channels):
                pairs, improvements, valid = [], [], counts_ok
                for seed in SEEDS:
                    learned, base = [lookup[seed, horizon, name, channel] for name in ("L22", baseline)]
                    lrmse, brmse = learned["metric"]["rmse"], base["metric"]["rmse"]
                    usable = (learned["full_fixed_count"] and base["full_fixed_count"] and
                        lrmse is not None and brmse is not None and brmse > 0 and math.isfinite(lrmse) and math.isfinite(brmse))
                    improvement = (brmse-lrmse)/brmse if usable else None
                    if improvement is not None and not math.isfinite(improvement):
                        usable, improvement = False, None
                    valid = valid and usable
                    if usable:
                        improvements.append(improvement)
                    pairs.append({"seed": seed, "L22_rmse": lrmse, f"{baseline}_rmse": brmse,
                                  "relative_improvement": improvement, "complete": usable})
                mean = math.fsum(value/3 for value in improvements) if valid else None
                condition = valid and all(p["L22_rmse"] < p[f"{baseline}_rmse"] if strict20 else
                                          p["L22_rmse"] <= p[f"{baseline}_rmse"] for p in pairs)
                checks.append({"horizon": horizon, "signal": signal, "axis": axis,
                    "rule": "each_seed_strict_and_mean_relative_ge_.20" if strict20 else "each_seed_no_worse",
                    "evaluated": bool(valid), "mean_relative_improvement": mean,
                    "passed": bool(condition and (not strict20 or mean >= .20)), "seed_records": pairs,
                    "unavailable_reason": None if valid else "missing_fixed_count_or_zero_baseline_or_undefined"})
    return {"name": "L22_vs_K22_data_augmentation" if baseline == "K22" else "L22_vs_D11_original_K_rules",
        "scope": "new_seen_C_common_prediction_development_subgate", "baseline": baseline,
        "all_fixed_usable_counts": counts_ok, "evaluated": all(r["evaluated"] for r in checks),
        "passed": all(r["passed"] for r in checks), "checks": checks,
        "scientific_adoption": False, "old_K_D_gates_reinterpreted": False}


def main_run(args):
    output = Path(args.output).resolve()
    if output.exists():
        raise FileExistsError("new L output required; no overwrite/rerun")
    output.mkdir(parents=True)
    start_wall, start_cpu = time.perf_counter(), time.process_time()
    cost = Counter({key: 0 for key in ("physics_calls", "physics_substeps", "MPC_calls", "RLS_updates", "D11_updates",
        "K22_refits", "fit_scalar_labels", "generated_fit_scalar_labels", "fit_shared_29x29_22rhs_solve_attempts",
        "fit_shared_29x29_22rhs_solve_returns", "fit_shared_29x29_22rhs_solve_failures",
        "transition_scalar_coefficients_fitted", "transition_heads_published", "seed_fit_failures",
        "K22_restoration_attempts", "K22_restoration_returns", "D11_restoration_attempts", "D11_restoration_returns")})
    inputs, sources, payloads, counts = {}, None, {}, {}
    parameters, predictions, unavailable, Krestorations, Drestorations = [], [], [], [], []
    Kfingerprints, Dfingerprints = {}, {}
    def write(name, data):
        (output/name).write_bytes(data)
        payloads[name] = {"bytes": len(data), "sha256": digest(data)}
    def flush():
        write("parameters.json", json_bytes(parameters))
        write("restorations.json", json_bytes({"K22": Krestorations, "D11": Drestorations}))
        write("predictions.jsonl", b"".join((json.dumps(r, ensure_ascii=False, allow_nan=False)+"\n").encode("utf-8") for r in predictions))
        write("unavailable.json", json_bytes(unavailable))
    try:
        repo = Path(args.repo).resolve()
        sources = frozen_sources(repo, args.source_commit, cost)
        blobs, docs, cmeta, gmeta, krun = read_inputs(repo, inputs, cost, sources)
        core = load_core(repo)
        restored = restore_K(core, docs[f"{K_ROOT}/parameters.json"], cost, Krestorations)
        models = core.restore_models(docs[f"{D_ROOT}/raw/diagnostics.json"], repo, cost, Drestorations)
        Kfingerprints = {s: restored[s]["fingerprint"] for s in SEEDS}
        Dfingerprints = {s: models[s].parameter_fingerprint() for s in SEEDS}
        if {str(s): value for s, value in Dfingerprints.items()} != krun["D11_fingerprints_before"]:
            raise ValueError("D11 baseline differs from matched K source")
        ctrials, ccounts = core.parse_trials(blobs[f"{C_ROOT}/trace.jsonl.gz"], cost)
        gtrials, gcounts = parse_PD_trials(blobs[f"{G_ROOT}/trace.jsonl.gz"], cost)
        selected, weights = {"C": ctrials, "G": gtrials}, {}
        counts = {**ccounts, **gcounts}
        for seed in SEEDS:
            qref = restored[seed]["qref8"]
            prefix_sources = {}
            for collection, kind in (("C", "calibration_sparse"), ("C", "prediction"), ("G", "PDselected")):
                trial = f"seed{seed}_{kind}"
                current_ref, current_id = core.prefix_qref(selected[collection][trial])
                if current_ref != qref or tuple(qref[:2]) != models[seed].qref:
                    raise ValueError("C/G full prefix eight-axis qref differs from frozen K/D; no repair")
                prefix_sources[f"{collection}:{trial}"] = current_id
            record = {"seed": seed, "available": False, "qref8": qref, "prefix_source_ids": prefix_sources,
                "state_order": core.STATE_NAMES, "feature_order": core.FEATURE_NAMES, "fixed_lambda": RIDGE,
                "K22_fingerprint": Kfingerprints[seed], "D11_fingerprint": Dfingerprints[seed],
                "learning_class": "batch_ridge_not_RLS", "PD_sampling_prior": True,
                "training_transition_ids": [], "training_collection_labels": [], "training_prior600x22": [],
                "phi600x29": [], "delta_labels600x22": [], "fit": {}}
            parameters.append(record)
            try:
                training = qualified_training_windows(core, selected, counts, seed)
                record["qualified_training_count"] = len(training)
                for collection, row, past, request, previous_v in training:
                    x = core.encode_state(row["observation_before"], qref, cost)
                    phi, prior = core.feature_and_prior(x, previous_v, request, qref, models[seed].public_guard, cost, "fit")
                    actual = core.encode_state(row["observation_after"], qref, cost)
                    with np.errstate(over="ignore", invalid="ignore"):
                        delta = actual-prior
                    core.finite_array(delta, (22,))
                    record["phi600x29"].append(phi.tolist())
                    record["delta_labels600x22"].append(delta.tolist())
                    record["training_prior600x22"].append(prior.tolist())
                    record["training_transition_ids"].append(row["shared_transition_id"])
                    record["training_collection_labels"].append(collection)
                    cost["generated_fit_scalar_labels"] += 22
                    cost[f"{collection}_generated_fit_scalar_labels"] += 22
                weights[seed] = fit600(core, record["phi600x29"], record["delta_labels600x22"], cost, record["fit"])
                record.update(available=True, parameter_fingerprint=digest(json_bytes({"qref8": qref,
                    "weights29x22": weights[seed].tolist(), "lambda": RIDGE, "feature_order": core.FEATURE_NAMES})))
            except Exception as exc:
                record["failure"] = f"{type(exc).__name__}:{exc}"
                cost["seed_fit_failures"] += 1
            flush()
        for seed in SEEDS:
            rows, qref = ctrials[f"seed{seed}_prediction"], restored[seed]["qref8"]
            for horizon in HORIZONS:
                for origin in range(101-horizon):
                    common = {"seed": seed, "trial_id": f"seed{seed}_prediction", "origin": origin,
                              "horizon": horizon, "offline_saved_future_requests": True}
                    try:
                        active, past, requests, previous_v = core.window(rows, origin, horizon)
                        obs = active[0]["observation_before"]
                        initial = core.encode_state(obs, qref, cost)
                        q, v = core.native(obs)[:2]
                        common.update(initial_x22=initial.tolist(), previous_v2=previous_v,
                            history_transition_ids=[r["shared_transition_id"] for r in past],
                            requested_transition_ids=[r["shared_transition_id"] for r in active],
                            requested_sequence8=requests, source_stopped_at_endpoint=core.stopped(active[-1]))
                    except (KeyError, TypeError, ValueError) as exc:
                        reason = f"window_unavailable:{type(exc).__name__}:{exc}"
                        unavailable.append({**common, "reason": reason})
                        predictions.extend({**common, "predictor": name, "available": False, "scored": False, "reason": reason} for name in PREDICTORS)
                        continue
                    current_records = []
                    for name in PREDICTORS:
                        if name == "D11":
                            outcome = core.rollout11(models[seed], q, v, previous_v, requests, cost)
                        elif name == "L22" and seed not in weights:
                            outcome = {"available": False, "reason": "seed_augmented_parameters_unavailable"}
                        else:
                            chosen = restored[seed]["weights"] if name == "K22" else weights[seed]
                            outcome = core.rollout22(initial, previous_v, requests, qref, models[seed].public_guard, chosen, cost, name)
                        record = {**common, "predictor": name, **outcome, "scored": False}
                        predictions.append(record)
                        current_records.append(record)
                    actual = core.encode_state(active[-1]["observation_after"], qref, cost)
                    actual_q, actual_v = core.native(active[-1]["observation_after"])[:2]
                    for record in current_records:
                        if not record["available"]:
                            continue
                        if record["predictor"] == "D11":
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
                flush()
        Kafter = {s: digest(json_bytes({"qref8": restored[s]["qref8"], "weights29x22": restored[s]["weights"].tolist(),
                                      "lambda": RIDGE, "feature_order": core.FEATURE_NAMES})) for s in SEEDS}
        Dafter = {s: models[s].parameter_fingerprint() for s in SEEDS}
        if Kafter != Kfingerprints or Dafter != Dfingerprints:
            raise ValueError("frozen_K22_or_D11_mutated")
        groups = summarize(core, predictions, counts)
        augmentation_gate, matched_D_gate = development_gate(groups, "K22"), development_gate(groups, "D11")
        both_passed = augmentation_gate["passed"] and matched_D_gate["passed"]
        write("metrics.json", json_bytes({"groups": groups, "data_augmentation_gate": augmentation_gate,
            "matched_D11_gate": matched_D_gate, "both_development_gates_passed": both_passed,
            "new_holdout_control_development_eligible": both_passed, "scientific_adoption": False,
            "c4_scientific_validation": False, "c5_scientific_dependency_released": False, "G_PD_method_ranking": False}))
        cost["wall_seconds"], cost["cpu_seconds"] = time.perf_counter()-start_wall, time.process_time()-start_cpu
        run = {"status": "completed", "scientific_adoption": False, "both_development_gates_passed": both_passed,
            "inputs": inputs, "source": sources, "original_source_commits": COMMITS, "source_active_counts": counts,
            "original_dependencies": {"C": cmeta.get("dependencies"), "G": gmeta.get("dependencies"), "K": krun.get("runtime")},
            "runtime": {"python": sys.version, "numpy": np.__version__, "platform": platform.platform()},
            "K22_fingerprints_before": Kfingerprints, "K22_fingerprints_after": Kafter,
            "D11_fingerprints_before": Dfingerprints, "D11_fingerprints_after": Dafter,
            "cost": dict(cost), "timing_excludes": "final run/manifest serialization and write",
            "historical_PD_data_reused": {"per_seed_active": 200, "per_seed_prefix": 100,
                "already_paid_control_calls": 900, "already_paid_substeps": 9000, "new_physics_calls": 0,
                "gain_development": "existing nine-configuration PD sweep/selection retained in historical ledger; not zeroed"},
            "claim_boundary": "sample quantity and PD sampling distribution jointly changed; no pure coverage causal claim, equal-budget efficiency or cold-start skill claim",
            "compute_classification": "new39,600 scalar-label batch ridge from reused C400+GPD200; restored K22/D11 re-predicted; zero new physics/RLS"}
        write("run.json", json_bytes(run))
        (output/"manifest.json").write_bytes(json_bytes({"schema_version": 1, "status": "completed",
                                                        "scientific_adoption": False, "files": payloads}))
        return run
    except BaseException as exc:
        flush()
        cost["wall_seconds"], cost["cpu_seconds"] = time.perf_counter()-start_wall, time.process_time()-start_cpu
        write("failure.json", json_bytes({"status": "failed", "exception_type": type(exc).__name__, "message": str(exc),
            "requested_L_source_commit": args.source_commit, "expected_original_source_commits": COMMITS,
            "expected_input_pins": PINS, "inputs_already_read": inputs,
            "inputs_without_returned_read_record": {name: "unknown_before_input_record_returned" for name in PINS if name not in inputs},
            "source_already_verified": sources if sources is not None else {
                "status": "unknown", "reason": "source verifier did not return verified binding"},
            "source_active_counts": counts, "K22_fingerprints_before": Kfingerprints, "D11_fingerprints_before": Dfingerprints,
            "cost": dict(cost), "scientific_adoption": False, "both_development_gates_passed": False,
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
