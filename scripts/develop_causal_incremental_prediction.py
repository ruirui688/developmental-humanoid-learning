"""CF1 first-only saved native causal-incremental prediction; no fit or physics."""
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

SOURCE_PATH = "scripts/develop_causal_incremental_prediction.py"
PROTOCOL_PATH = "docs/CAUSAL_INCREMENTAL_PREDICTION_PROTOCOL.md"
PROTOCOL_PIN = {"bytes": 7757, "sha256": "54a85bf9ac4da234cfd7d8e887fe64f7c6ac325f53cd889f49e24c03ec053446"}
SOURCE_PATHS = (SOURCE_PATH, PROTOCOL_PATH,
    "src/developmental_physics/causal_incremental_pair_model.py",
    "src/developmental_physics/instrumental_action_model.py",
    "src/developmental_physics/__init__.py")
INPUT_BASE = "results/cpu_validation/2026-10-12_near_reference_identification/raw"
INPUT_SOURCE = "dec307a49cd6ad883b7f6016b2634dd3730a8d7d"
INPUT_PINS = {
    "run.json": {"bytes": 342682, "sha256": "599308e788d9c293d2b9ac53b5d17284a0547b1c8d261840fa02a3b9aaadcc6d"},
    "models.json": {"bytes": 25865, "sha256": "5ff8f01698c0ddc6b3cd92fc61002f7a58f4e214565d0b2d5bf682bc1fe03f52"},
    "source_trace.jsonl.gz": {"bytes": 9570465, "sha256": "6d4b62b70edd19e9f42f6f040215f531ca14c9fe0ee6e8381ee6804c71047d35"}}
SEEDS = (8101, 8102, 8103)
MODEL_NAMES = ("CFcold", "CFlearn")
OLD_NAMES = ("cold", "oldlearned", "IV1", "IV2", "IV3")
HORIZONS = (1, 2, 5, 10, 20, 50, 150)
OLD_HORIZONS = (1, 10, 20, 50, 150)
ORIGINS = {h: tuple(range(0, 2000-h+1, 20)) for h in HORIZONS}
FLAGS = {"scientific_adoption": False, "old_free_root_C4_validation": False,
         "c4_scientific_validation": False, "c4_contact_scientific_validation": False,
         "c5_scientific_dependency_released": False, "control_candidate_opened": False}
BOUNDS = {"new_physics_controls": 0, "new_physics_substeps": 0, "fit": 0, "OLS": 0, "RLS": 0,
          "teacher": 0, "fork": 0, "source_top_level_intervals": 9000,
          "prediction_records": 4146, "pair_predictions": 135900, "velocity_heads": 271800,
          "new_model_B_scalar_coefficients": 48, "archived_IV1_action8_scalar_reads": 24,
          "old_model_predictions": 0, "old_fit_RMSE_gate_recomputations": 0}


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
    cost["protocol_hash_attempts"] += 1
    identity = pin(blobs[PROTOCOL_PATH])
    cost["protocol_hash_returns"] += 1
    cost["protocol_bytes_hashed"] += len(blobs[PROTOCOL_PATH])
    if identity != PROTOCOL_PIN:
        raise ValueError("frozen_protocol_identity_required")
    cost["source_identity_hash_attempts"] += len(blobs)
    identities = {name: pin(blob) for name, blob in blobs.items()}
    cost["source_identity_hash_returns"] += len(blobs)
    cost["source_identity_bytes_hashed"] += sum(len(blob) for blob in blobs.values())
    return {"commit": commit, "clean_committed_bytes_verified": True, "files": identities}, blobs


class Collector:
    def __init__(self, repo, output):
        self.repo, self.output, self.cost = repo, output, Counter()
        self.source, self.context, self.input_run, self.body = None, None, None, None
        self.input_identities, self.source_trials, self.models, self.fingerprints = {}, {}, {}, {}
        self.archived_action_source, self.seed_results, self.old_transcribed = {}, [], {}
        self.native_rows, self.native_counts = {seed: [] for seed in SEEDS}, {seed: 0 for seed in SEEDS}
        self.handles, self.streams = {}, {}
        self.predictions = [{"seed": seed, "model": name, "horizon": h, "origin_active_index": origin,
            "status": "not_attempted", "available": False, "partial_subset_ranking": False}
            for seed in SEEDS for h in HORIZONS for name in MODEL_NAMES for origin in ORIGINS[h]]
        self.metrics = {"complete_population": False, "cf1_prediction_gate_passed": False, "checks": [], **FLAGS}
        self.decoded_source_identity = None

    def open_streams(self):
        for name in ("native_source", "predictions"):
            self.handles[name] = gzip.open(self.output / (name+".jsonl.gz"), "xb")
            self.streams[name] = {"records": 0, "bytes": 0, "hash": hashlib.sha256()}

    def write(self, name, row):
        self.cost["JSONL_encode_attempts"] += 1
        blob = (json.dumps(safe(row), ensure_ascii=False, allow_nan=False)+"\n").encode()
        self.cost["JSONL_encode_returns"] += 1
        self.cost["JSONL_write_attempts"] += 1
        self.handles[name].write(blob)
        self.handles[name].flush()
        self.cost["JSONL_write_returns"] += 1
        self.cost["JSONL_decoded_bytes_written"] += len(blob)
        stream = self.streams[name]
        stream["records"] += 1
        stream["bytes"] += len(blob)
        stream["hash"].update(blob)

    def load_inputs(self):
        blobs = {}
        for name, expected in INPUT_PINS.items():
            self.context = {"stage": "input_read_hash", "file": name}
            self.cost["IV3_input_read_attempts"] += 1
            blobs[name] = (self.repo / INPUT_BASE / name).read_bytes()
            self.cost["IV3_input_read_returns"] += 1
            self.cost["IV3_input_bytes_read"] += len(blobs[name])
            self.cost["IV3_input_hash_attempts"] += 1
            self.input_identities[name] = pin(blobs[name])
            self.cost["IV3_input_hash_returns"] += 1
            self.cost["IV3_input_bytes_hashed"] += len(blobs[name])
            if self.input_identities[name] != expected:
                raise ValueError("exact_IV3_input_identity_required:"+name)
        self.cost["IV3_JSON_parse_attempts"] += 2
        run, snapshots = json.loads(blobs["run.json"]), json.loads(blobs["models.json"])
        self.cost["IV3_JSON_parse_returns"] += 2
        self.input_run = run
        if (run.get("experiment_id") != "IV3" or run.get("status") != "completed" or run.get("first_failure") is not None
                or run.get("source", {}).get("commit") != INPUT_SOURCE or run.get("source", {}).get("clean_committed_bytes_verified") is not True
                or run.get("metrics", {}).get("complete_population") is not True or run.get("config", {}).get("seeds") != list(SEEDS)
                or run.get("config", {}).get("prefix") != 1000 or run.get("config", {}).get("identification_active") != 2000
                or run.get("config", {}).get("dt_seconds") != .002 or run.get("config", {}).get("study_q_rad") != .12
                or run.get("config", {}).get("study_v_rad_s") != 1. or run.get("config", {}).get("final_permission_nm") != .5):
            raise ValueError("complete_original_frozen_IV3_source_required")
        trials = run.get("trials", [])
        if len(trials) != 3 or [trial.get("seed") for trial in trials] != list(SEEDS):
            raise ValueError("exact_three_original_training_trials_required")
        sys.path.insert(0, str(self.repo / "src"))
        self.body = importlib.import_module("developmental_physics.causal_incremental_pair_model")
        if Path(self.body.__file__).resolve() != (self.repo / SOURCE_PATHS[2]).resolve():
            raise ValueError("canonical_pure_model_module_required")
        qrefs, trial_ids = {}, {}
        for trial in trials:
            seed = trial["seed"]
            self.context = {"stage": "source_trial_and_action_metadata", "seed": seed}
            qualification = trial.get("contact_qualification", {})
            if (trial.get("kind") != "identification" or trial.get("trial_id") != "s"+str(seed)+"_identification"
                    or trial.get("planned_controls") != 3000 or trial.get("status") != "completed" or trial.get("stop") is not None
                    or trial.get("failure") is not None or trial.get("metadata_before") != trial.get("metadata_after")
                    or not isinstance(trial.get("metadata_before"), dict) or qualification.get("passed") is not True
                    or qualification.get("required_stages") != ["prefix", "A", "B"]):
                raise ValueError("original_complete_trial_protection_and_contact_qualification_required")
            # These saved contact qualifications are transcribed only. Contact
            # arrays or forces are never decoded or passed to the model.
            self.source_trials[seed] = copy.deepcopy(trial)
            self.cost["saved_trial_qualification_transcriptions"] += 1
            telemetry = trial.get("stage_telemetry", {})
            if set(telemetry) != {"prefix", "A", "B"}:
                raise ValueError("three_original_complete_contact_stages_required")
            for stage in ("prefix", "A", "B"):
                saved = telemetry[stage]
                if saved.get("captured_substeps") != 1000 or saved.get("positive_contact_endpoints", {}).get("left_arm", 0) < 1:
                    raise ValueError("saved_complete_original_contact_stage_qualification_required")
                self.cost["saved_contact_stage_qualification_transcriptions"] += 1
            ranges = self.body.finite("source_public_ranges2", trial["public_ranges2"], (2, 2))
            qrefs[seed] = self.body.finite("source_fresh_qref2", trial["qref2"], (2,))
            trial_ids[seed] = trial["trial_id"]
            item = snapshots[str(seed)]["IV1"]
            if (item.get("structure") != "coupled_hinge9" or item.get("dt_seconds") != .002
                    or item.get("feature_order") != ["v0", "v1", "qrel0", "qrel1", "G0", "G1", "h0", "h1", "1"]
                    or item.get("integration") != "endpoint_euler" or item.get("guard_margin_rad") != .03
                    or item.get("request_limit_nm") != .5 or item.get("hinge_threshold_nm") != .25
                    or item.get("trainable") is not False or item.get("physical_queries") != 0
                    or item.get("parameter_fingerprint") != item.get("fingerprint_before_prediction")
                    or item.get("parameter_fingerprint") != run["model_fingerprints"][str(seed)]["IV1"]
                    or not re.fullmatch(r"[0-9a-f]{64}", item.get("parameter_fingerprint", ""))):
                raise ValueError("archived_IV1_public_action_metadata_required")
            snap_ranges = self.body.finite("archived_public_ranges2", item["public_joint_ranges_rad"], (2, 2))
            snap_qref = self.body.finite("archived_public_qref2", item["qref_rad"], (2,))
            if snap_ranges.tobytes() != ranges.tobytes() or snap_qref.tobytes() != qrefs[seed].tobytes():
                raise ValueError("archived_public_ranges_and_qref_must_match_source_trial")
            theta = item["coefficients"]
            if not isinstance(theta, list) or len(theta) != 2 or any(not isinstance(row, list) or len(row) != 9 for row in theta):
                raise ValueError("archived_action_columns_must_exist_in_original_order")
            action8 = self.body.finite("only_archived_IV1_action8", [row[4:8] for row in theta], (2, 4))
            self.cost["archived_IV1_action8_scalar_reads"] += 8
            self.archived_action_source[seed] = {"snapshot_model": "IV1", "original_parameter_fingerprint_transcribed": item["parameter_fingerprint"],
                "action_columns_only": [4, 5, 6, 7], "action8": action8.tolist(), "state_head_read_or_restored": False}
            for name, coefficient in (("CFcold", [[.002, 0., 0., 0.], [0., .002, 0., 0.]]), ("CFlearn", action8)):
                model = self.body.CausalIncrementalPairModel(ranges, coefficient)
                self.models[(seed, name)] = model
                self.fingerprints[(seed, name)] = model.parameter_fingerprint()
                self.cost["new_native_model_builds"] += 1
                self.cost["new_model_B_scalar_coefficients"] += 8
            old = next(result for result in run["seed_results"] if result["seed"] == seed)["prediction_scores"]
            if set(old["horizons"]) != {str(h) for h in OLD_HORIZONS} or any(set(old["horizons"][str(h)]["models"]) != set(OLD_NAMES) for h in OLD_HORIZONS):
                raise ValueError("complete_saved_old_five_model_five_horizon_table_required")
            self.old_transcribed[str(seed)] = copy.deepcopy(old)
            self.cost["old_RMSE_scalar_transcriptions"] += 100
        self.old_transcribed["old_metrics_transcribed_not_recomputed"] = copy.deepcopy(run["metrics"])
        self.old_transcribed["population_comparison"] = "different_old_population_no_matched_diff_or_old_model_calls"
        selector = self.body.NativeCausalTraceStream(SEEDS, trial_ids, qrefs, self.cost)
        decoded_hash, decoded_bytes, decoded_lines = hashlib.sha256(), 0, 0
        with gzip.GzipFile(fileobj=io.BytesIO(blobs["source_trace.jsonl.gz"]), mode="rb") as stream:
            for line_index, line in enumerate(stream):
                self.context = {"stage": "full_native_source_decode", "decoded_line_index": line_index}
                decoded_lines += 1
                decoded_bytes += len(line)
                decoded_hash.update(line)
                self.cost["IV3_trace_decoded_lines"] += 1
                self.cost["IV3_trace_decoded_bytes"] += len(line)
                self.cost["IV3_trace_JSON_parse_attempts"] += 1
                row = json.loads(line)
                self.cost["IV3_trace_JSON_parse_returns"] += 1
                if not isinstance(row, dict):
                    raise ValueError("source_trace_object_required")
                if set(row) == {"paid_native_endpoint"} or set(row) == {"IV3_native_fit_annotation"}:
                    self.cost["nested_paid_or_fit_rows_skipped_no_model_use"] += 1
                    continue
                selected = selector.accept(row)
                selected["source_decoded_line_index"] = line_index
                self.native_rows[selected["seed"]].append(selected)
                self.native_counts = dict(selector.counts)
                self.write("native_source", selected)
        self.decoded_source_identity = {"records": decoded_lines, "bytes": decoded_bytes, "sha256": decoded_hash.hexdigest()}
        expected = run["streams"]["source_trace"]
        if any(self.decoded_source_identity[key] != expected[key] for key in ("records", "bytes", "sha256")):
            raise ValueError("complete_original_decoded_source_identity_required")
        self.native_counts = selector.finish()
        for seed in SEEDS:
            if self.native_rows[seed][1000]["q"].tobytes() != qrefs[seed].tobytes():
                raise ValueError("active0_native_origin_must_equal_fresh_source_qref")

    def score(self):
        for seed in SEEDS:
            summary = {"horizons": {}, "condition": "seen_IV3_native_origins_with_real_previous_interval_then_own_recursive_memory"}
            for h in HORIZONS:
                hrow = summary["horizons"][str(h)] = {"planned_origin_count": len(ORIGINS[h]), "models": {}}
                for name in MODEL_NAMES:
                    model, errors_q, errors_v = self.models[(seed, name)], [], []
                    for slot in (item for item in self.predictions if item["seed"] == seed and item["horizon"] == h and item["model"] == name):
                        self.context = {key: slot[key] for key in ("seed", "model", "horizon", "origin_active_index")}
                        index = 1000+slot["origin_active_index"]
                        segment = self.native_rows[seed][index:index+h]
                        if len(segment) != h:
                            raise ValueError("entire_declared_future_request_path_required")
                        q, v = segment[0]["q"].copy(), segment[0]["v"].copy()
                        memory = self.body.interval_memory(self.native_rows[seed][index-1])
                        requests = [transition["request"].copy() for transition in segment]
                        slot.update(status="attempted", model_fingerprint=self.fingerprints[(seed, name)],
                            model_input={"q2": q, "v2": v, "history": memory.record(), "known_requests2": requests},
                            source_origin_decoded_line_index=segment[0]["source_decoded_line_index"],
                            first_history_source_control_index=index-1, recursive_memory_source="own_predicted_qv_and_known_request_only",
                            predicted_q_path=[], predicted_v_path=[], predicted_drift_path=[])
                        self.cost["real_origin_history_memory_builds"] += 1
                        self.cost["saved_prediction_origin_qv_scalar_uses"] += 4
                        self.cost["saved_prediction_known_request_scalar_uses"] += 2*h
                        self.cost["saved_prediction_real_past_qv_request_scalar_uses"] += 6
                        original_error = None
                        try:
                            for step_index, request in enumerate(requests):
                                q, v, memory, drift = model.predict(q, v, request, memory, segment[0]["trial_id"], index+step_index, self.cost)
                                slot["predicted_q_path"].append(q.tolist())
                                slot["predicted_v_path"].append(v.tolist())
                                slot["predicted_drift_path"].append(drift.tolist())
                            aq, av = segment[-1]["next_q"], segment[-1]["next_v"]
                            with np.errstate(over="raise", invalid="raise"):
                                dq, dv = self.body.finite("new_endpoint_q_error", q-aq, (2,)), self.body.finite("new_endpoint_v_error", v-av, (2,))
                            self.cost["seen_saved_scoring_scalar_label_uses"] += 4
                            self.cost["prediction_endpoint_error_scalar_outputs"] += 4
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
                                self.write("predictions", slot)
                            except BaseException as write_exc:
                                if original_error is None:
                                    raise
                                original_error.partial_write_failure = {"type": type(write_exc).__name__, "message": str(write_exc)}
                    with np.errstate(over="raise", invalid="raise"):
                        rq, rv = (self.body.finite("new_full_population_RMSE", np.sqrt(np.mean(np.square(errors), axis=0)), (2,))
                                  for errors in (errors_q, errors_v))
                    self.cost["new_axis_RMSE_vector_computations"] += 2
                    hrow["models"][name] = {"available": True, "observed_origin_count": len(errors_q),
                        "q_rmse_axis_rad": rq.tolist(), "v_rmse_axis_rad_s": rv.tolist(), "partial_subset_ranking": False}
            self.seed_results.append({"seed": seed, "prediction_scores": summary})

    def gate(self):
        if len(self.seed_results) != 3 or any(not slot["available"] for slot in self.predictions):
            raise ValueError("complete_finite_new_population_required_before_gate")
        checks = []
        for h in HORIZONS:
            for signal in ("q", "v"):
                key = "q_rmse_axis_rad" if signal == "q" else "v_rmse_axis_rad_s"
                strict, gated = (h, signal) == (1, "v"), h in (2, 5) or (h, signal) == (1, "v")
                for result in self.seed_results:
                    models = result["prediction_scores"]["horizons"][str(h)]["models"]
                    base, candidate = models["CFcold"][key], models["CFlearn"][key]
                    checks.append({"seed": result["seed"], "horizon": h, "signal": signal, "available": True,
                        "CFcold_axis": base, "CFlearn_axis": candidate, "strict": strict, "gated": gated,
                        "passed": bool(all(candidate[i] < base[i] if strict else candidate[i] <= base[i] for i in range(2)))})
                    self.cost["new_per_seed_axis_metric_comparisons"] += 2
        with np.errstate(over="raise", invalid="raise"):
            means = {name: self.body.finite("new_H1v_raw_RMSE_mean", np.mean([
                result["prediction_scores"]["horizons"]["1"]["models"][name]["v_rmse_axis_rad_s"]
                for result in self.seed_results], axis=0), (2,)) for name in MODEL_NAMES}
        fractions = [(float(means["CFcold"][i]-means["CFlearn"][i])/float(means["CFcold"][i])
                      if means["CFcold"][i] > 0. else None) for i in range(2)]
        if any(value is not None and not np.isfinite(value) for value in fractions):
            raise ValueError("finite_new_mean_improvement_required")
        self.cost["new_H1v_axis_mean_computations"] += 4
        self.cost["new_mean_gate_axis_comparisons"] += 2
        checks.append({"scope": "three_seed_raw_RMSE_mean", "horizon": 1, "signal": "v", "gated": True,
            "CFcold_axis_mean": means["CFcold"].tolist(), "CFlearn_axis_mean": means["CFlearn"].tolist(),
            "improvement_fractions": fractions, "required_improvement": .20, "available": all(value is not None for value in fractions),
            "passed": all(value is not None and value >= .20 for value in fractions)})
        self.metrics = {"complete_population": True, "cf1_prediction_gate_passed": all(item["passed"] for item in checks if item["gated"]),
            "checks": checks, "mean_type": "arithmetic mean of original per_seed axis RMSE", "evaluation_seen_development": True,
            "old_population_matched_comparison": False, **FLAGS}

    def run(self):
        self.load_inputs()
        if len(self.predictions) != BOUNDS["prediction_records"] or sum(len(ORIGINS[h])*h for h in HORIZONS)*6 != BOUNDS["pair_predictions"]:
            raise ValueError("declared_full_range_population_budget_required")
        self.score()
        for key, model in self.models.items():
            self.cost["final_frozen_model_fingerprint_checks"] += 1
            if model.parameter_fingerprint() != self.fingerprints[key]:
                raise ValueError("frozen_new_action_model_changed")
        if (self.cost["saved_native_selection_returns"] != 9000 or self.cost["pair_prediction_returns"] != 135900
                or self.cost["scalar_velocity_head_returns"] != 271800 or self.cost["new_axis_RMSE_vector_computations"] != 84
                or self.cost["archived_IV1_action8_scalar_reads"] != 24 or self.cost["new_model_B_scalar_coefficients"] != 48):
            raise ValueError("complete_fixed_CF1_cost_and_population_required")
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
        collector.metrics.update(complete_population=False, cf1_prediction_gate_passed=False)
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
    models = {str(seed): {name: {**model.record(), "parameter_fingerprint": collector.fingerprints[(seed, name)],
        "archived_action_source": collector.archived_action_source.get(seed) if name == "CFlearn" else
        {"source": "shared_generic_2ms_diagonal_prior_zero_hinge"}}
        for (model_seed, name), model in collector.models.items() if model_seed == seed} for seed in SEEDS}
    for name, data in (("models.json", models), ("old_scores_transcribed.json", collector.old_transcribed), ("metrics.json", collector.metrics)):
        try:
            (output / name).write_text(json.dumps(safe(data), ensure_ascii=False, allow_nan=False, indent=2)+"\n", encoding="utf-8")
        except BaseException as exc:
            payload_failure(exc, name+"_write")
    report = {"experiment_id": "CF1", "status": status, "first_failure": failure, "source": collector.source,
        "input_source": {"base": INPUT_BASE, "IV3_source_commit": INPUT_SOURCE, "required_pins": INPUT_PINS,
                         "actual_identities": collector.input_identities, "decoded_source_identity": collector.decoded_source_identity},
        "config": {"seeds": SEEDS, "models": MODEL_NAMES, "prefix": 1000, "active": 2000, "H": HORIZONS,
            "prediction_stride": 20, "origins": {str(h): ORIGINS[h] for h in HORIZONS}, "dt_seconds": .002,
            "history": "previous_same_trial_complete_interval_start_qv_known_request", "first_active_history": "real_prefix_control_999",
            "recursive_history": "own_predicted_qv_known_request_only", "evaluation": "seen_IV3_development_not_new_holdout",
            "new_gate": "H1v_each_seed_strict_and_axis_raw_RMSE_mean_20%;H2_H5_qv_each_seed_noninferior",
            "H150_planning_opened": False, "old_population_diff_or_gate_recomputation": False},
        "planned_upper_bounds": BOUNDS, "cost": dict(collector.cost), "source_trials_transcribed": collector.source_trials,
        "native_source_counts": collector.native_counts, "seed_results": collector.seed_results, "metrics": collector.metrics,
        "model_fingerprints": {str(seed): {name: fingerprint for (model_seed, name), fingerprint in collector.fingerprints.items() if model_seed == seed} for seed in SEEDS},
        "complete_prediction_population": [{key: slot[key] for key in ("seed", "model", "horizon", "origin_active_index", "status", "available")} for slot in collector.predictions],
        "streams": {name: {"path": name+".jsonl.gz", "format": "gzip_jsonl", "identity_scope": "decoded_jsonl",
            "records": item["records"], "bytes": item["bytes"], "sha256": item["hash"].hexdigest()} for name, item in collector.streams.items()},
        "new_physics_control_calls": 0, "new_physics_substeps": 0, "fit_calls": 0, "OLS_calls": 0, "RLS_updates": 0,
        "new_training_scalar_labels": 0, "evaluation_fit_label_uses": 0, "old_model_prediction_calls": 0,
        "old_fit_RMSE_gate_recomputations": 0, "seen_evaluation_development_only": True, "heldout_validation": False,
        "prior_physics_control_calls": 544345, "prior_physics_substeps": 2824018, "historical_RLS_scalar_updates": 125652,
        "prior_IV3_new_OLS_scalar_labels": 12000, "prior_IV3_OLS_solves": 3, "prior_IV3_state_coefficients": 30,
        "runtime": {"python": sys.version, "numpy": np.__version__, "platform": platform.platform(),
            "cpu": platform.processor() or "unknown", "logical_cpu_count": os.cpu_count(), "GPU_used": False,
            "mujoco_imported_or_used": False}, "unmeasured_import_internal_and_IO_work": "unknown_not_zero",
        "timing_excludes": "final_JSON_encoding_and_payload_writes", "completed_utc": datetime.now(timezone.utc).isoformat(), **FLAGS}
    try:
        (output / "run.json").write_text(json.dumps(safe(report), ensure_ascii=False, allow_nan=False, indent=2)+"\n", encoding="utf-8")
    except BaseException as exc:
        payload_failure(exc, "run_JSON_write")
    print(json.dumps({"experiment_id": "CF1", "status": status, "output": str(output), "cost": dict(collector.cost), "failure": failure}))
    return 0 if status == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
