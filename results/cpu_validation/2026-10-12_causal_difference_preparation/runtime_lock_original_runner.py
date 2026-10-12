"""CFD1 first-only whole-trial cross-fitted action-difference prediction."""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import redirect_stderr, redirect_stdout
import copy
from datetime import datetime, timezone
import gzip
import hashlib
import importlib
import io
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import time
import traceback
import zipfile

import numpy as np

SOURCE_PATH = "scripts/develop_causal_difference_prediction.py"
PROTOCOL_PATH = "docs/CAUSAL_DIFFERENCE_PREDICTION_PROTOCOL.md"
PROTOCOL_PIN = {"bytes": 8831, "sha256": "b339c25574ee2350b494921232a3408eb43c187ba61d4c1cf0f5ceae9245fd89"}
MODEL_PATH = "src/developmental_physics/causal_incremental_pair_model.py"
SOURCE_PATHS = (SOURCE_PATH, PROTOCOL_PATH, MODEL_PATH,
    "src/developmental_physics/instrumental_action_model.py", "src/developmental_physics/__init__.py")
EXACT_REUSED_SOURCE_PINS = {
    MODEL_PATH: {"bytes": 10782, "sha256": "e719bf097d5f16624f504d794ad6c1ad1b170306120fdb5baedb4868432d0619"},
    "src/developmental_physics/instrumental_action_model.py": {"bytes": 9302, "sha256": "cb0d3f6314682553fabe2f37b56764bd8098551221e14cbe8f3aece14b014c51"},
    "src/developmental_physics/__init__.py": {"bytes": 162, "sha256": "d2ee9d572836752f5f8404bfdf1fca8add0d62b9858f4c6dcd9cf7ddc6c53ea2"}}
INPUT_BASE = "results/cpu_validation/2026-10-12_causal_incremental_prediction/raw"
INPUT_SOURCE = "bb7e4b8fa744b4ec7c76855cfe6730ebbca26421"
REQUIRED_NUMPY_VERSION = "2.2.6"
INPUT_PINS = {
    "run.json": {"bytes": 813956, "sha256": "1dd1a1c329c268d095f90bb49bb95a6e85bbc3fa1c918c794a3cfecd1329b19b"},
    "models.json": {"bytes": 9975, "sha256": "e8948ddc1f88c3552912fae1f6741528796c17c41dd504436988c1d7b1038b56"},
    "native_source.jsonl.gz": {"bytes": 884195, "sha256": "63f2b0cf315353e55a3ef93893a65f78db14ae0939a91c2852e0c16cd521b530"}}
SEEDS = (8101, 8102, 8103)
HORIZONS = (1, 2, 5, 10, 20, 50, 150)
ORIGINS = {h: tuple(range(0, 2000-h+1, 20)) for h in HORIZONS}
FLAGS = {"scientific_adoption": False, "old_free_root_C4_validation": False,
    "c4_scientific_validation": False, "c4_contact_scientific_validation": False,
    "c5_scientific_dependency_released": False, "control_candidate_opened": False}
BOUNDS = {"new_physics_controls": 0, "new_physics_substeps": 0, "RLS": 0, "teacher": 0,
    "source_native_intervals": 9000, "unique_training_difference_rows": 5997,
    "unique_transformed_Y_scalars": 11994, "fold_training_rows": 11994, "fold_Y_scalar_uses": 23988,
    "OLS_attempts": 3, "fitted_B_scalar_outputs": 24, "new_prediction_records": 2073,
    "new_pair_predictions": 67950, "new_velocity_heads": 135900, "new_scoring_label_uses": 8292,
    "cold_RMSE_scalar_transcriptions": 84, "cold_H1v_mean_scalar_transcriptions": 2,
    "cold_prediction_or_RMSE_recomputations": 0}


def safe(value):
    if isinstance(value, dict):
        return {str(key): safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [safe(item) for item in value]
    if isinstance(value, np.ndarray):
        return safe(value.tolist())
    if isinstance(value, np.generic):
        return safe(value.item())
    if isinstance(value, float) and not np.isfinite(value):
        return {"nonfinite_float": str(value)}
    return value


def pin(blob):
    return {"bytes": len(blob), "sha256": hashlib.sha256(blob).hexdigest()}


def source_gate(repo, commit, cost):
    if Path(__file__).resolve() != (repo / SOURCE_PATH).resolve() or not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("canonical_runner_and_exact_source_commit_required")
    def git(args):
        cost["source_git_attempts"] += 1
        result = subprocess.run(["git", *args], cwd=repo, capture_output=True, check=False)
        cost["source_git_returns"] += 1
        cost["source_git_bytes"] += len(result.stdout)+len(result.stderr)
        if result.returncode:
            raise ValueError("source_git_query_failed")
        return result.stdout
    if git(["rev-parse", "HEAD"]).decode().strip() != commit or git(["status", "--porcelain"]):
        raise ValueError("exact_clean_source_HEAD_required")
    blobs = {}
    for name in SOURCE_PATHS:
        cost["source_file_read_attempts"] += 1
        blobs[name] = (repo / name).read_bytes()
        cost["source_file_read_returns"] += 1
        cost["source_bytes_read"] += len(blobs[name])
        if blobs[name] != git(["show", commit+":"+name]):
            raise ValueError("source_bytes_differ:"+name)
    identities = {name: pin(blob) for name, blob in blobs.items()}
    cost["source_identity_hash_attempts"] += len(blobs)
    cost["source_identity_hash_returns"] += len(blobs)
    cost["source_identity_bytes_hashed"] += sum(len(blob) for blob in blobs.values())
    if PROTOCOL_PIN is None or identities[PROTOCOL_PATH] != PROTOCOL_PIN:
        raise ValueError("frozen_protocol_identity_required")
    if any(identities[name] != expected for name, expected in EXACT_REUSED_SOURCE_PINS.items()):
        raise ValueError("exact_CF1_pure_prediction_formula_source_required")
    return {"commit": commit, "clean_committed_bytes_verified": True, "files": identities}, blobs


def difference_sample(previous, current, ranges, body, cost=None):
    """The current causal one-step velocity error is Y minus B @ X."""
    body.count(cost, "difference_sample_attempts")
    if (previous["seed"] != current["seed"] or previous["trial_id"] != current["trial_id"]
            or previous["control_index"]+1 != current["control_index"]):
        raise ValueError("same_trial_adjacent_active_training_intervals_required")
    pq, pv = body.finite("training_previous_q2", previous["q"], (2,)), body.finite("training_previous_v2", previous["v"], (2,))
    q, v = body.finite("training_current_q2", current["q"], (2,)), body.finite("training_current_v2", current["v"], (2,))
    next_v = body.finite("training_current_next_v2", current["next_v"], (2,))
    if (body.finite("training_previous_endpoint_q2", previous["next_q"], (2,)).tobytes() != q.tobytes()
            or body.finite("training_previous_endpoint_v2", previous["next_v"], (2,)).tobytes() != v.tobytes()):
        raise ValueError("training_interval_endpoints_must_be_continuous")
    phi_previous, _ = body.action_features(pq, previous["request"], ranges, cost)
    phi_current, _ = body.action_features(q, current["request"], ranges, cost)
    with np.errstate(over="raise", invalid="raise"):
        x = body.finite("difference_phi4", phi_current-phi_previous, (4,))
        y = body.finite("difference_velocity_increment2", (next_v-v)-(v-pv), (2,))
    body.count(cost, "training_native_velocity_scalar_operand_uses", 6)
    body.count(cost, "difference_design_scalar_outputs", 4)
    body.count(cost, "transformed_Y_scalar_constructions", 2)
    body.count(cost, "difference_sample_returns")
    return x, y


def fold_training_seeds(eval_seed, seeds=SEEDS):
    if eval_seed not in seeds or len(seeds) != 3 or len(set(seeds)) != 3:
        raise ValueError("declared_three_seed_leave_one_trial_out_required")
    return tuple(seed for seed in seeds if seed != eval_seed)


def difference_design(rows_by_seed, eval_seed, ranges, body, cost=None, seeds=SEEDS,
                      active_indices=range(1, 2000), prefix_count=1000):
    train_seeds = fold_training_seeds(eval_seed, seeds)
    xs, ys, provenance = [], [], []
    for seed in train_seeds:
        rows = rows_by_seed[seed]  # Never retrieve the evaluation trial here.
        for active in active_indices:
            current, previous = rows[prefix_count+active], rows[prefix_count+active-1]
            if current["seed"] != seed or previous["seed"] != seed or current["active_index"] != active or previous["active_index"] != active-1:
                raise ValueError("declared_other_trial_active_training_indices_required")
            x, y = difference_sample(previous, current, ranges, body, cost)
            xs.append(x)
            ys.append(y)
            provenance.append({"training_seed": seed, "active_index": active, "previous_control_index": previous["control_index"],
                               "current_control_index": current["control_index"]})
    return np.asarray(xs, dtype=np.float64), np.asarray(ys, dtype=np.float64), provenance


class Collector:
    def __init__(self, repo, output):
        self.repo, self.output, self.cost = repo, output, Counter()
        self.source, self.context, self.input_run, self.body, self.ranges = None, None, None, None, None
        self.input_identities, self.models, self.fingerprints, self.source_trials = {}, {}, {}, {}
        self.native_rows, self.native_counts = {seed: [] for seed in SEEDS}, {seed: 0 for seed in SEEDS}
        self.handles, self.streams, self.seed_results, self.fit_records = {}, {}, [], {}
        self.cold_transcribed, self.old_transcribed, self.cold_mean = {}, {}, None
        self.decoded_source_identity = None
        self.fits = [{"seed": seed, "training_seeds": fold_training_seeds(seed), "planned_rows": 3998,
            "status": "not_attempted", "available": False, "rcond": None} for seed in SEEDS]
        self.predictions = [{"seed": seed, "model": "CFDlearn", "horizon": h, "origin_active_index": origin,
            "status": "not_attempted", "available": False, "partial_subset_ranking": False}
            for seed in SEEDS for h in HORIZONS for origin in ORIGINS[h]]
        self.metrics = {"complete_population": False, "cfd1_prediction_gate_passed": False, "checks": [], **FLAGS}

    def open_streams(self):
        self.handles["predictions"] = gzip.open(self.output / "predictions.jsonl.gz", "xb")
        self.streams["predictions"] = {"records": 0, "bytes": 0, "hash": hashlib.sha256()}

    def write(self, row):
        self.cost["JSONL_encode_attempts"] += 1
        blob = (json.dumps(safe(row), ensure_ascii=False, allow_nan=False)+"\n").encode()
        self.cost["JSONL_encode_returns"] += 1
        self.cost["JSONL_write_attempts"] += 1
        self.handles["predictions"].write(blob)
        self.handles["predictions"].flush()
        self.cost["JSONL_write_returns"] += 1
        self.cost["JSONL_decoded_bytes_written"] += len(blob)
        stream = self.streams["predictions"]
        stream["records"] += 1
        stream["bytes"] += len(blob)
        stream["hash"].update(blob)

    def load_inputs(self):
        blobs = {}
        for name, expected in INPUT_PINS.items():
            self.context = {"stage": "compact_CF1_input_read_hash", "file": name}
            self.cost["CF1_input_read_attempts"] += 1
            blobs[name] = (self.repo / INPUT_BASE / name).read_bytes()
            self.cost["CF1_input_read_returns"] += 1
            self.cost["CF1_input_bytes_read"] += len(blobs[name])
            self.cost["CF1_input_hash_attempts"] += 1
            self.input_identities[name] = pin(blobs[name])
            self.cost["CF1_input_hash_returns"] += 1
            self.cost["CF1_input_bytes_hashed"] += len(blobs[name])
            if self.input_identities[name] != expected:
                raise ValueError("exact_compact_CF1_input_identity_required:"+name)
        self.cost["CF1_JSON_parse_attempts"] += 2
        run, snapshots = json.loads(blobs["run.json"]), json.loads(blobs["models.json"])
        self.cost["CF1_JSON_parse_returns"] += 2
        self.input_run = run
        if np.__version__ != REQUIRED_NUMPY_VERSION or run.get("runtime", {}).get("numpy") != REQUIRED_NUMPY_VERSION:
            raise ValueError("locked_NumPy_2_2_6_default_rcond_runtime_required")
        expected_origins = {str(h): list(ORIGINS[h]) for h in HORIZONS}
        config = run.get("config", {})
        if (run.get("experiment_id") != "CF1" or run.get("status") != "completed" or run.get("first_failure") is not None
                or run.get("source", {}).get("commit") != INPUT_SOURCE or run.get("source", {}).get("clean_committed_bytes_verified") is not True
                or run.get("metrics", {}).get("complete_population") is not True or config.get("seeds") != list(SEEDS)
                or config.get("models") != ["CFcold", "CFlearn"] or config.get("H") != list(HORIZONS)
                or config.get("prefix") != 1000 or config.get("active") != 2000 or config.get("prediction_stride") != 20
                or config.get("origins") != expected_origins or config.get("dt_seconds") != .002
                or config.get("history") != "previous_same_trial_complete_interval_start_qv_known_request"
                or config.get("first_active_history") != "real_prefix_control_999"
                or config.get("recursive_history") != "own_predicted_qv_known_request_only"):
            raise ValueError("completed_exact_same_formula_and_population_CF1_source_required")
        if any(run["source"]["files"].get(name) != expected for name, expected in EXACT_REUSED_SOURCE_PINS.items()):
            raise ValueError("CF1_source_must_use_exact_current_pure_formula_dependencies")
        expected_slots = {(seed, name, h, origin) for seed in SEEDS for name in ("CFcold", "CFlearn") for h in HORIZONS for origin in ORIGINS[h]}
        slots = run["complete_prediction_population"]
        actual_slots = {(slot["seed"], slot["model"], slot["horizon"], slot["origin_active_index"]) for slot in slots}
        if len(slots) != 4146 or actual_slots != expected_slots or any(slot.get("status") != "completed" or slot.get("available") is not True for slot in slots):
            raise ValueError("complete_unique_original_cold_population_required_no_prediction_decode")
        self.cost["source_prediction_slot_qualification_transcriptions"] += 4146
        sys.path.insert(0, str(self.repo / "src"))
        self.body = importlib.import_module("developmental_physics.causal_incremental_pair_model")
        if Path(self.body.__file__).resolve() != (self.repo / MODEL_PATH).resolve():
            raise ValueError("canonical_exact_CF1_pure_model_required")
        trials = run["source_trials_transcribed"]
        if set(trials) != {str(seed) for seed in SEEDS} or run["native_source_counts"] != {str(seed): 3000 for seed in SEEDS}:
            raise ValueError("three_complete_CF1_native_trials_required")
        qrefs, trial_ids = {}, {}
        for seed in SEEDS:
            self.context = {"stage": "cold_public_metadata_and_saved_scores", "seed": seed}
            trial, cold = trials[str(seed)], snapshots[str(seed)]["CFcold"]
            if (trial.get("seed") != seed or trial.get("kind") != "identification" or trial.get("trial_id") != "s"+str(seed)+"_identification"
                    or trial.get("status") != "completed" or trial.get("planned_controls") != 3000 or trial.get("stop") is not None
                    or trial.get("failure") is not None or trial.get("metadata_before") != trial.get("metadata_after")
                    or trial.get("contact_qualification", {}).get("passed") is not True
                    or trial.get("contact_qualification", {}).get("required_stages") != ["prefix", "A", "B"]):
                raise ValueError("original_complete_protected_contact_trial_qualification_required")
            self.source_trials[seed] = copy.deepcopy(trial)
            self.cost["saved_source_trial_qualification_transcriptions"] += 1
            ranges = self.body.finite("cold_shared_public_ranges2", cold["public_joint_ranges_rad"], (2, 2))
            if self.ranges is None:
                self.ranges = ranges.copy()
            elif ranges.tobytes() != self.ranges.tobytes():
                raise ValueError("all_three_seed_public_ranges_must_be_exactly_shared")
            if (self.body.finite("source_trial_public_ranges2", trial["public_ranges2"], (2, 2)).tobytes() != self.ranges.tobytes()
                    or cold.get("structure") != "causal_incremental_action8" or cold.get("dt_seconds") != .002
                    or cold.get("action_order") != ["G0", "G1", "h0", "h1"] or cold.get("integration") != "endpoint_euler"
                    or cold.get("guard_margin_rad") != .03 or cold.get("request_limit_nm") != .5 or cold.get("hinge_threshold_nm") != .25
                    or cold.get("trainable") is not False or cold.get("physical_queries") != 0 or cold.get("state_head_used") is not False
                    or cold.get("history") != "previous_complete_same_trial_interval_start_qv_known_request"
                    or cold.get("drift") != "(current_v-previous_v)-f_B(previous_q,previous_known_request)"
                    or cold.get("recursive_history") != "own_current_qv_request_and_predicted_endpoint_only"
                    or cold.get("parameter_fingerprint") != run["model_fingerprints"][str(seed)]["CFcold"]
                    or self.body.finite("frozen_cold_action8", cold["action8"], (2, 4)).tobytes() != np.asarray([[.002, 0., 0., 0.], [0., .002, 0., 0.]]).tobytes()):
                raise ValueError("exact_generic_cold_record_and_public_formula_required")
            qrefs[seed] = self.body.finite("source_fresh_qref2", trial["qref2"], (2,))
            trial_ids[seed] = trial["trial_id"]
            saved_scores = next(item for item in run["seed_results"] if item["seed"] == seed)["prediction_scores"]
            cold_scores = {"source_experiment": "CF1", "source_model": "CFcold", "source_commit": INPUT_SOURCE,
                "source_parameter_fingerprint_transcribed": cold["parameter_fingerprint"],
                "public_joint_ranges_rad": self.ranges.tolist(), "horizons": {}}
            for h in HORIZONS:
                saved = saved_scores["horizons"][str(h)]
                item = saved["models"]["CFcold"]
                if (saved["planned_origin_count"] != len(ORIGINS[h]) or item.get("available") is not True
                        or item.get("observed_origin_count") != len(ORIGINS[h]) or item.get("partial_subset_ranking") is not False):
                    raise ValueError("saved_cold_RMSE_must_match_complete_same_origin_population")
                self.body.finite("saved_cold_q_RMSE", item["q_rmse_axis_rad"], (2,))
                self.body.finite("saved_cold_v_RMSE", item["v_rmse_axis_rad_s"], (2,))
                cold_scores["horizons"][str(h)] = {**copy.deepcopy(item), "transcribed_not_recomputed": True}
                self.cost["cold_RMSE_scalar_transcriptions"] += 4
            self.cold_transcribed[str(seed)] = cold_scores
            self.old_transcribed[str(seed)] = copy.deepcopy(cold_scores)
        saved_mean = next(item for item in run["metrics"]["checks"] if item.get("scope") == "three_seed_raw_RMSE_mean"
                          and item["horizon"] == 1 and item["signal"] == "v")
        self.cold_mean = self.body.finite("saved_same_population_cold_H1v_mean2", saved_mean["CFcold_axis_mean"], (2,)).copy()
        self.cost["cold_H1v_mean_scalar_transcriptions"] += 2
        self.cold_transcribed["H1v_axis_mean_transcribed_not_recomputed"] = self.cold_mean.tolist()
        self.old_transcribed["original_CF1_metrics_transcribed_not_recomputed"] = copy.deepcopy(run["metrics"])
        decoded_hash, decoded_bytes, decoded_lines = hashlib.sha256(), 0, 0
        previous = {}
        with gzip.GzipFile(fileobj=io.BytesIO(blobs["native_source.jsonl.gz"]), mode="rb") as stream:
            for line_index, line in enumerate(stream):
                self.context = {"stage": "complete_compact_native_decode", "decoded_line_index": line_index}
                decoded_lines += 1
                decoded_bytes += len(line)
                decoded_hash.update(line)
                self.cost["native_source_decoded_lines"] += 1
                self.cost["native_source_decoded_bytes"] += len(line)
                self.cost["native_source_JSON_parse_attempts"] += 1
                row = json.loads(line)
                self.cost["native_source_JSON_parse_returns"] += 1
                if not isinstance(row, dict) or line_index >= 9000:
                    raise ValueError("exact_complete_compact_native_records_required")
                seed, index = row.get("seed"), row.get("control_index")
                if seed != SEEDS[line_index//3000] or type(index) is not int or index != self.native_counts[seed] or row.get("trial_id") != trial_ids[seed]:
                    raise ValueError("compact_native_same_trial_order_required_no_missing_duplicate_or_reordering")
                active = index-1000
                if row.get("active_index") != active or row.get("stage") != ("prefix" if active < 0 else "A" if active < 1000 else "B"):
                    raise ValueError("original_compact_stage_and_indices_required")
                selected = {key: self.body.finite("compact_"+key, row[key], (2,)).copy() for key in ("q", "v", "request", "next_q", "next_v")}
                if np.any(np.abs(selected["request"]) > .5) or (active < 0 and np.any(selected["request"] != 0.)):
                    raise ValueError("original_known_pair_permission_and_zero_prefix_required")
                if seed in previous and (selected["q"].tobytes(), selected["v"].tobytes()) != previous[seed]:
                    raise ValueError("exact_complete_compact_native_continuity_required")
                if active >= 0 and (np.any(np.abs(selected["next_q"]-qrefs[seed]) >= .12) or np.any(np.abs(selected["next_v"]) >= 1.)):
                    raise ValueError("source_original_active_StudyAbort_must_be_untriggered")
                selected.update(seed=seed, trial_id=row["trial_id"], control_index=index, active_index=active,
                                stage=row["stage"], source_decoded_line_index=row["source_decoded_line_index"], compact_decoded_line_index=line_index)
                self.native_rows[seed].append(selected)
                self.native_counts[seed] += 1
                previous[seed] = (selected["next_q"].tobytes(), selected["next_v"].tobytes())
                self.cost["compact_native_selection_returns"] += 1
                self.cost["compact_native_qv_request_scalar_reads"] += 10
        self.decoded_source_identity = {"records": decoded_lines, "bytes": decoded_bytes, "sha256": decoded_hash.hexdigest()}
        expected = run["streams"]["native_source"]
        if any(self.decoded_source_identity[key] != expected[key] for key in ("records", "bytes", "sha256")) or self.native_counts != {seed: 3000 for seed in SEEDS}:
            raise ValueError("complete_original_compact_decoded_identity_required")
        if any(self.native_rows[seed][1000]["q"].tobytes() != qrefs[seed].tobytes() for seed in SEEDS):
            raise ValueError("original_active0_fresh_qref_required")

    def fit_all(self):
        for slot in self.fits:
            seed = slot["seed"]
            self.context = {"stage": "single_other_trial_difference_OLS", "eval_seed": seed, "training_seeds": slot["training_seeds"]}
            slot["status"] = "attempted"
            x, y, provenance = difference_design(self.native_rows, seed, self.ranges, self.body, self.cost)
            record = self.fit_records[seed] = {"eval_seed_excluded": seed, "training_seeds": slot["training_seeds"],
                "active_training_indices": [1, 1999], "X_difference_phi4": x, "Y_difference_dv2": y, "provenance": provenance,
                "rcond": None, "intercept": False, "regularization": None, "scale": None, "solution": None}
            self.body.finite("complete_fold_X_3998x4", x, (3998, 4))
            self.body.finite("complete_fold_Y_3998x2", y, (3998, 2))
            if any(item["training_seed"] == seed for item in provenance) or len(provenance) != 3998:
                raise ValueError("entire_eval_trial_excluded_from_own_design_and_Y")
            self.cost["fold_training_trial_uses"] += 2
            self.cost["fold_training_rows"] += 3998
            self.cost["fold_X_scalar_uses"] += 15992
            self.cost["fold_Y_scalar_uses"] += 7996
            self.cost["OLS_attempts"] += 1
            try:
                solution, residuals, rank, singular = np.linalg.lstsq(x, y, rcond=None)
            except BaseException:
                self.cost["OLS_exceptions"] += 1
                slot["status"] = "failed"
                raise
            self.cost["OLS_returns"] += 1
            self.cost["OLS_solution_scalar_outputs"] += solution.size
            record.update(solution=solution, residuals=residuals, rank=int(rank), singular_values=singular)
            slot.update(rank=int(rank), observed_rows=len(provenance))
            if rank != 4 or not np.isfinite(solution).all() or not np.isfinite(residuals).all() or not np.isfinite(singular).all():
                slot["status"] = "failed"
                raise ValueError("finite_full_rank4_difference_OLS_required_no_completion_or_fallback")
            b = self.body.finite("single_fold_B2x4", solution.T, (2, 4))
            model = self.body.CausalIncrementalPairModel(self.ranges, b)
            self.models[seed] = model
            self.fingerprints[seed] = model.parameter_fingerprint()
            self.cost["fitted_B_scalar_outputs"] += 8
            slot.update(status="completed", available=True, parameter_fingerprint=self.fingerprints[seed])
        if any(slot["status"] != "completed" for slot in self.fits):
            raise ValueError("all_three_complete_finite_fits_required_before_any_prediction")

    def score(self):
        for seed in SEEDS:
            summary = {"horizons": {}, "condition": "same_CF1_origins_requests_formula_cold_transcribed;own_trial_crossfit_learn"}
            model = self.models[seed]
            for h in HORIZONS:
                errors_q, errors_v = [], []
                for slot in (item for item in self.predictions if item["seed"] == seed and item["horizon"] == h):
                    self.context = {key: slot[key] for key in ("seed", "model", "horizon", "origin_active_index")}
                    index = 1000+slot["origin_active_index"]
                    segment = self.native_rows[seed][index:index+h]
                    if len(segment) != h:
                        raise ValueError("complete_same_population_future_request_path_required")
                    q, v = segment[0]["q"].copy(), segment[0]["v"].copy()
                    memory = self.body.interval_memory(self.native_rows[seed][index-1])
                    requests = [item["request"].copy() for item in segment]
                    slot.update(status="attempted", model_fingerprint=self.fingerprints[seed], training_seeds=fold_training_seeds(seed),
                        model_input={"q2": q, "v2": v, "history": memory.record(), "known_requests2": requests},
                        first_history_source_control_index=index-1, predicted_q_path=[], predicted_v_path=[], predicted_drift_path=[])
                    self.cost["saved_origin_qv_scalar_uses"] += 4
                    self.cost["saved_real_past_qv_request_scalar_uses"] += 6
                    self.cost["saved_future_known_request_scalar_uses"] += 2*h
                    original_error = None
                    try:
                        for step, request in enumerate(requests):
                            q, v, memory, drift = model.predict(q, v, request, memory, segment[0]["trial_id"], index+step, self.cost)
                            slot["predicted_q_path"].append(q.tolist())
                            slot["predicted_v_path"].append(v.tolist())
                            slot["predicted_drift_path"].append(drift.tolist())
                        aq, av = segment[-1]["next_q"], segment[-1]["next_v"]
                        with np.errstate(over="raise", invalid="raise"):
                            dq, dv = self.body.finite("new_endpoint_q_error", q-aq, (2,)), self.body.finite("new_endpoint_v_error", v-av, (2,))
                        self.cost["seen_saved_scoring_scalar_label_uses"] += 4
                        slot.update(status="completed", available=True, actual_endpoint_q2=aq, actual_endpoint_v2=av,
                                    q_error_rad=dq, v_error_rad_s=dv)
                        errors_q.append(dq)
                        errors_v.append(dv)
                    except BaseException as exc:
                        original_error = exc
                        slot.update(status="failed", available=False, failure={"type": type(exc).__name__, "message": str(exc)})
                        raise
                    finally:
                        try:
                            self.write(slot)
                        except BaseException as write_exc:
                            if original_error is None:
                                raise
                            original_error.partial_write_failure = {"type": type(write_exc).__name__, "message": str(write_exc)}
                with np.errstate(over="raise", invalid="raise"):
                    rq, rv = (self.body.finite("new_full_population_RMSE", np.sqrt(np.mean(np.square(errors), axis=0)), (2,)) for errors in (errors_q, errors_v))
                self.cost["new_axis_RMSE_vector_computations"] += 2
                summary["horizons"][str(h)] = {"planned_origin_count": len(ORIGINS[h]), "models": {
                    "CFDcold": copy.deepcopy(self.cold_transcribed[str(seed)]["horizons"][str(h)]),
                    "CFDlearn": {"available": True, "observed_origin_count": len(errors_q), "q_rmse_axis_rad": rq.tolist(),
                        "v_rmse_axis_rad_s": rv.tolist(), "partial_subset_ranking": False}}}
            self.seed_results.append({"seed": seed, "prediction_scores": summary})

    def gate(self):
        if len(self.seed_results) != 3 or any(not item["available"] for item in self.predictions):
            raise ValueError("all_complete_new_prediction_paths_required_before_gate")
        checks = []
        for h in HORIZONS:
            for signal in ("q", "v"):
                key = "q_rmse_axis_rad" if signal == "q" else "v_rmse_axis_rad_s"
                strict, gated = (h, signal) == (1, "v"), h in (2, 5) or (h, signal) == (1, "v")
                for result in self.seed_results:
                    models = result["prediction_scores"]["horizons"][str(h)]["models"]
                    base, candidate = models["CFDcold"][key], models["CFDlearn"][key]
                    checks.append({"seed": result["seed"], "horizon": h, "signal": signal, "available": True,
                        "CFDcold_axis_transcribed": base, "CFDlearn_axis": candidate, "strict": strict, "gated": gated,
                        "passed": bool(all(candidate[i] < base[i] if strict else candidate[i] <= base[i] for i in range(2)))})
                    self.cost["new_per_seed_axis_metric_comparisons"] += 2
        with np.errstate(over="raise", invalid="raise"):
            learned_mean = self.body.finite("new_learned_H1v_raw_RMSE_mean2", np.mean([
                item["prediction_scores"]["horizons"]["1"]["models"]["CFDlearn"]["v_rmse_axis_rad_s"] for item in self.seed_results], axis=0), (2,))
        fractions = [(float(self.cold_mean[i]-learned_mean[i])/float(self.cold_mean[i]) if self.cold_mean[i] > 0. else None) for i in range(2)]
        if any(value is not None and not np.isfinite(value) for value in fractions):
            raise ValueError("finite_new_improvement_fraction_required")
        self.cost["new_learned_axis_mean_computations"] += 2
        self.cost["new_mean_gate_axis_comparisons"] += 2
        checks.append({"scope": "three_seed_raw_RMSE_mean", "horizon": 1, "signal": "v", "gated": True,
            "CFDcold_axis_mean_transcribed": self.cold_mean.tolist(), "CFDlearn_axis_mean": learned_mean.tolist(),
            "improvement_fractions": fractions, "required_improvement": .20, "available": all(value is not None for value in fractions),
            "passed": all(value is not None and value >= .20 for value in fractions)})
        self.metrics = {"complete_population": True, "cfd1_prediction_gate_passed": all(item["passed"] for item in checks if item["gated"]),
            "checks": checks, "mean_type": "arithmetic mean of original per_seed axis RMSE", "evaluation_seen_development": True,
            "cold_same_population_transcribed_not_recomputed": True, "crossfit_is_new_unseen_holdout": False, **FLAGS}

    def run(self):
        self.load_inputs()
        self.fit_all()
        self.score()
        for seed, model in self.models.items():
            self.cost["final_frozen_model_fingerprint_checks"] += 1
            if model.parameter_fingerprint() != self.fingerprints[seed]:
                raise ValueError("frozen_learned_difference_B_changed")
        if (len(self.predictions) != 2073 or self.cost["pair_prediction_returns"] != 67950 or self.cost["scalar_velocity_head_returns"] != 135900
                or self.cost["seen_saved_scoring_scalar_label_uses"] != 8292 or self.cost["OLS_returns"] != 3
                or self.cost["fold_training_rows"] != 11994 or self.cost["fold_Y_scalar_uses"] != 23988
                or self.cost["fitted_B_scalar_outputs"] != 24 or self.cost["new_axis_RMSE_vector_computations"] != 42):
            raise ValueError("complete_fixed_crossfit_and_new_prediction_budget_required")
        self.gate()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repo, output = args.repo.resolve(), args.output.resolve()
    if output.exists() or output == repo or repo.is_relative_to(output) or (repo / INPUT_BASE).resolve().is_relative_to(output):
        parser.error("existing_or_repository_or_input_containing_output_refused")
    output.mkdir(parents=True, exist_ok=False)
    collector, failure, status = Collector(repo, output), None, "failed"
    wall, cpu = time.perf_counter(), time.process_time()
    def payload_failure(exc, stage):
        nonlocal failure, status
        collector.metrics.update(complete_population=False, cfd1_prediction_gate_passed=False)
        detail = {"stage": stage, "type": type(exc).__name__, "message": str(exc)}
        if failure is None:
            failure, status = {**detail, "context": collector.context}, "failed"
        else:
            failure.setdefault("secondary_payload_failures", []).append(detail)
    with (output / "first_stdout.log").open("x", encoding="utf-8") as stdout, (output / "first_stderr.log").open("x", encoding="utf-8") as stderr:
        with redirect_stdout(stdout), redirect_stderr(stderr):
            try:
                collector.open_streams()
                collector.source, blobs = source_gate(repo, args.source_commit, collector.cost)
                with zipfile.ZipFile(output / "source.zip", "x", compression=zipfile.ZIP_DEFLATED) as archive:
                    for name, blob in blobs.items():
                        archive.writestr(name, blob)
                collector.cost["source_archive_bytes_written"] = (output / "source.zip").stat().st_size
                collector.run()
                status = "completed"
            except BaseException as exc:
                failure = {"type": type(exc).__name__, "message": str(exc), "context": collector.context,
                    "traceback": traceback.format_exc(), "partial_write_failure": getattr(exc, "partial_write_failure", None)}
                traceback.print_exc()
            finally:
                for handle in collector.handles.values():
                    try:
                        handle.close()
                    except BaseException as exc:
                        payload_failure(exc, "stream_close")
                        traceback.print_exc()
    collector.cost["wall_seconds"], collector.cost["cpu_seconds"] = time.perf_counter()-wall, time.process_time()-cpu
    models = {str(seed): {"CFDlearn": {**model.record(), "parameter_fingerprint": collector.fingerprints[seed],
        "training_seeds": fold_training_seeds(seed), "eval_trial_excluded": seed, "rank": 4, "rcond": None}}
        for seed, model in collector.models.items()}
    for name, data in (("models.json", models), ("fits.json", collector.fit_records), ("cold_transcribed.json", collector.cold_transcribed),
                       ("old_scores_transcribed.json", collector.old_transcribed), ("metrics.json", collector.metrics)):
        try:
            (output / name).write_text(json.dumps(safe(data), ensure_ascii=False, allow_nan=False, indent=2)+"\n", encoding="utf-8")
        except BaseException as exc:
            payload_failure(exc, name+"_write")
    report = {"experiment_id": "CFD1", "status": status, "first_failure": failure, "source": collector.source,
        "input_source": {"base": INPUT_BASE, "CF1_source_commit": INPUT_SOURCE, "required_pins": INPUT_PINS,
            "actual_identities": collector.input_identities, "decoded_source_identity": collector.decoded_source_identity},
        "config": {"seeds": SEEDS, "models": ["CFDcold_transcribed", "CFDlearn"], "prefix": 1000, "active": 2000,
            "H": HORIZONS, "prediction_stride": 20, "origins": {str(h): ORIGINS[h] for h in HORIZONS}, "dt_seconds": .002,
            "training": "each_own_map_other_two_complete_trials_active1..1999_difference_OLS",
            "rcond": None, "numpy_version_locked": REQUIRED_NUMPY_VERSION, "intercept": False, "regularization": None, "scale": None,
            "new_gate": "H1v_each_seed_strict_and_axis_raw_RMSE_mean_20%;H2_H5_qv_each_seed_noninferior",
            "evaluation": "seen_development_whole_trial_crossfit_not_new_unseen_holdout", "cold_forward_or_RMSE_recomputed": False},
        "planned_upper_bounds": BOUNDS, "cost": dict(collector.cost), "fits": collector.fits,
        "source_trials_transcribed": collector.source_trials, "native_source_counts": collector.native_counts,
        "seed_results": collector.seed_results, "metrics": collector.metrics,
        "complete_prediction_population": [{key: slot[key] for key in ("seed", "model", "horizon", "origin_active_index", "status", "available")} for slot in collector.predictions],
        "model_fingerprints": {str(seed): {"CFDlearn": value} for seed, value in collector.fingerprints.items()},
        "streams": {name: {"path": name+".jsonl.gz", "format": "gzip_jsonl", "identity_scope": "decoded_jsonl",
            "records": item["records"], "bytes": item["bytes"], "sha256": item["hash"].hexdigest()} for name, item in collector.streams.items()},
        "unique_training_difference_rows": 5997 if all(item["available"] for item in collector.fits) else None,
        "unique_transformed_Y_scalars": 11994 if all(item["available"] for item in collector.fits) else None,
        "own_fold_evaluation_trial_fit_label_uses": 0, "global_cross_fold_evaluation_labels_are_training_labels_in_other_maps": True,
        "new_physics_control_calls": 0, "new_physics_substeps": 0, "RLS_updates": 0, "new_physical_training_labels": 0,
        "cold_model_prediction_calls": 0, "cold_RMSE_recomputations": 0, "old_gate_recomputations": 0,
        "old_model_prediction_calls": 0, "fit_calls": collector.cost["OLS_attempts"], "OLS_calls": collector.cost["OLS_attempts"],
        "seen_evaluation_development_only": True, "heldout_validation": False,
        "prior_physics_control_calls": 544345, "prior_physics_substeps": 2824018, "historical_RLS_scalar_updates": 125652,
        "prior_IV3_new_OLS_scalar_labels": 12000, "prior_IV3_OLS_solves": 3, "prior_IV3_state_coefficients": 30,
        "runtime": {"python": sys.version, "numpy": np.__version__, "platform": platform.platform(), "cpu": platform.processor() or "unknown",
            "logical_cpu_count": os.cpu_count(), "GPU_used": False, "mujoco_imported_or_used": False},
        "unmeasured_lstsq_import_internal_and_IO_work": "unknown_not_zero", "timing_excludes": "final_JSON_encoding_and_payload_writes",
        "completed_utc": datetime.now(timezone.utc).isoformat(), **FLAGS}
    try:
        (output / "run.json").write_text(json.dumps(safe(report), ensure_ascii=False, allow_nan=False, indent=2)+"\n", encoding="utf-8")
    except BaseException as exc:
        payload_failure(exc, "run_JSON_write")
    print(json.dumps({"experiment_id": "CFD1", "status": status, "output": str(output), "cost": dict(collector.cost), "failure": failure}))
    return 0 if status == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
