"""One bounded EF1B saved-evidence audit; never import production or a model.

Read only the new EF1B raw directory, its archived source, and exact Git source
blobs. Old PD/zero are source-declared references: their raw/math/audits are not
opened or replayed. Scientific gates are not recomputed or required to pass.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from contextlib import redirect_stdout, redirect_stderr
from datetime import datetime, timezone
import gzip
import hashlib
import io
import json
import math
from pathlib import Path
import subprocess
import sys
import traceback
import zipfile

import numpy as np


RAW_RELATIVE = "external/ef1b_control_first/raw"
SOURCE_COMMIT = "f9f500706364aab32bd18047266d4b06358e4473"
PROTOCOL = "docs/EQUILIBRIUM_FEEDFORWARD_CONTROL_PROTOCOL.md"
PROTOCOL_PIN = {"bytes": 12884, "sha256": "cf51c5a7500a57c0306bf7a06effddb09b85b984433d6baaa81097de7fc893bf"}
FR4B_COMMIT = "490fcffa0080125e7c2a8b887c99cc2743dcc01f"
FR4B_MANIFEST = {"bytes": 3154, "sha256": "ee66a39474fe6716af90a7671452a95a53541ec676ee7125e07416eed3153d9d"}
FR4B_AUDIT = {"bytes": 41990, "sha256": "639fc31e3ff6792a8313765ec0a4244f513f50db8b3fa76017f9e7b6830e0b53"}
SEEDS, METHODS, HORIZONS = (8101, 8102, 8103), ("cold", "learned"), (1, 10, 20, 50, 150)
FLAGS = ("scientific_adoption", "old_free_root_C4_validation", "c4_scientific_validation",
         "c5_scientific_dependency_released", "c4_contact_scientific_validation")
GATES = ("ef1b_model_contribution_gate_passed", "ef1b_pd_reference_gate_passed", "ef1_free_root_mechanism_validation")
FILE_LIMIT, SHARD_LIMIT, TOTAL_STORED_LIMIT, TOTAL_DECODED_LIMIT = 100_000_000, 64_000_000, 1_073_741_824, 2_147_483_648
STREAM_CAPS = {"trace": 18000, "predictions": 11772, "paid_intervals": 36006}
PLANNED_UPPER_BOUNDS = {
    "new_control_calls": 18000, "new_physics_substeps": 18000,
    "new_RLS_vector_commits": 0, "new_RLS_scalar_commits": 0, "new_fit_calls": 0,
    "MPC_decisions": 1200, "single_forecast_pair_forwards": 180000,
    "single_forecast_scalar_forwards": 360000, "root_solve_attempts": 12,
    "root_branch_SVDs": 192, "root_model_pair_forwards_maximum": 192,
    "root_model_scalar_forwards_maximum": 384, "conditional_prediction_records": 11772,
    "conditional_prediction_pairs": 526560, "conditional_prediction_scalars": 1053120,
    "reused_PD_zero_new_controls": 0, "reused_PD_zero_new_predictions": 0,
}
SOURCE_PATHS = (
    "scripts/develop_equilibrium_feedforward.py", "src/developmental_physics/equilibrium_feedforward_development.py",
    "src/developmental_physics/equilibrium_feedforward_pair.py", PROTOCOL,
    "scripts/develop_pd_anchor_pair.py", "src/developmental_physics/pd_anchor_pair_development.py",
    "docs/PD_ANCHOR_PAIR_LEARNING_PROTOCOL.md", "scripts/validate_free_root_fast_feedback_engineering.py",
    "src/developmental_physics/free_root_fast_feedback_environment.py", "docs/FREE_ROOT_FAST_FEEDBACK_ENGINEERING_PROTOCOL.md",
    "src/developmental_physics/environment.py", "src/developmental_physics/assets/ground_body.xml",
    "src/developmental_physics/__init__.py", "pyproject.toml", "src/developmental_physics/fast_feedback_pair_model.py",
    "src/developmental_physics/guard_coupled_pair_model.py", "src/developmental_physics/guard_pair_model.py",
    "src/developmental_physics/local_pair_model.py", "src/developmental_physics/local_model.py",
    "src/developmental_physics/fast_feedback_pair_mpc.py", "src/developmental_physics/batched_fast_feedback_pair_mpc.py",
    "src/developmental_physics/pd_anchor_pair_mpc.py", "src/developmental_physics/fast_feedback_pair_development.py",
)


def pin(blob):
    return {"bytes": len(blob), "sha256": hashlib.sha256(blob).hexdigest()}


def finite(value, shape):
    try:
        array = np.asarray(value, dtype=float)
        return array.shape == shape and bool(np.isfinite(array).all())
    except (TypeError, ValueError):
        return False


def same(first, second):
    if isinstance(first, dict):
        return isinstance(second, dict) and set(first) == set(second) and all(same(first[key], second[key]) for key in first)
    if isinstance(first, (list, tuple)):
        return isinstance(second, (list, tuple)) and len(first) == len(second) and all(same(a, b) for a, b in zip(first, second))
    if type(first) is bool or first is None or isinstance(first, str):
        return type(first) is type(second) and first == second
    if isinstance(first, (int, float)) and isinstance(second, (int, float)) and type(second) is not bool:
        return math.isfinite(first) and math.isfinite(second) and math.isclose(first, second, rel_tol=1e-11, abs_tol=1e-12)
    return first == second


def native(observation):
    if not all(finite(observation.get(key), (8,)) for key in ("joint_position", "joint_velocity")):
        raise ValueError("missing_finite_saved_native_qv8")
    return np.asarray(observation["joint_position"][:2], dtype=float), np.asarray(observation["joint_velocity"][:2], dtype=float)


def complete(row):
    try:
        if row.get("contact_audit_complete") is not True or row.get("returned") is not True or row["diagnostics"]["executed_substeps"] != 1:
            return False
        native(row["observation_before"])
        native(row["observation_after"])
        samples = row["diagnostics"]["substep_native_and_contact_records"]
        if len(samples) != 1:
            return False
        sample = samples[0]
        if sample["physics_step"] != row["control_index"]+1 or not math.isfinite(sample["time"]):
            return False
        fields = [(sample.get(key), (8,)) for key in ("applied_command8", "actual_actuator_torque8")]
        fields += [(sample["observation"].get(key), (size,)) for key, size in
                   (("joint_position", 8), ("joint_velocity", 8), ("imu_gyro", 3), ("imu_acceleration", 3), ("actuator_torque", 8), ("previous_command", 8))]
        return all(finite(value, shape) for value, shape in fields) and all(
            math.isfinite(contact[key]) for contact in sample["floor_contacts"] for key in ("normal_force_n", "distance_m"))
    except (KeyError, TypeError, ValueError):
        return False


class Audit:
    def __init__(self, repo, raw):
        self.repo, self.raw = repo, raw
        self.cost, self.contracts, self.rechecks, self.population = Counter(), [], [], []
        self.inputs, self.issues = {}, defaultdict(lambda: {"count": 0, "examples": []})

    def check(self, name, condition, detail=None, available=True):
        self.contracts.append({"name": name, "available": available, "passed": bool(condition) if available else None, "detail": detail})

    def issue(self, group, detail):
        item = self.issues[group]
        item["count"] += 1
        if len(item["examples"]) < 5:
            item["examples"].append(detail)

    def require(self, name, condition):
        self.check(name, condition)
        if not condition:
            raise ValueError(name)

    def read(self, relative, expected=None):
        path = (self.raw / relative).resolve()
        self.require("path_within_new_raw:"+relative, path.is_relative_to(self.raw) and path != self.raw)
        self.cost["file_read_attempts"] += 1
        size = path.stat().st_size
        self.require("stored_file_bound:"+relative, size < FILE_LIMIT)
        blob = path.read_bytes()
        self.cost["file_read_returns"] += 1
        self.cost["stored_bytes_read"] += len(blob)
        self.require("total_stored_bound", self.cost["stored_bytes_read"] <= TOTAL_STORED_LIMIT)
        identity = pin(blob)
        self.inputs[relative] = identity
        if expected is not None:
            self.check("stored_identity:"+relative, identity == expected)
        return blob

    def json(self, blob):
        self.cost["JSON_parse_attempts"] += 1
        result = json.loads(blob)
        self.cost["JSON_parse_returns"] += 1
        return result

    def stream(self, name, binding, files, handler):
        self.require("stream_format:"+name, binding.get("format") == "ordered_intact_JSONL_gzip_shards")
        self.require("stream_limits:"+name, binding.get("decoded_shard_limit") == SHARD_LIMIT and binding.get("stored_file_limit_exclusive") == FILE_LIMIT)
        total_hash, total_bytes, total_rows = hashlib.sha256(), 0, 0
        parts = binding.get("parts", [])
        self.require("bounded_stream_parts:"+name, len(parts) <= 64)
        for index, part in enumerate(parts):
            expected_path = name+("" if index == 0 else f".{index:05d}")+".jsonl.gz"
            self.require("ordered_stream_path:"+name+":"+str(index), part.get("path") == expected_path and files.get(expected_path) == part.get("stored"))
            blob = self.read(expected_path, part["stored"])
            self.cost["gzip_decode_attempts"] += 1
            part_hash, part_bytes, part_rows, largest_line = hashlib.sha256(), 0, 0, 0
            with gzip.GzipFile(fileobj=io.BytesIO(blob)) as stream:
                while True:
                    line = stream.readline(SHARD_LIMIT+1)
                    if not line:
                        break
                    self.cost["decoded_bytes_read"] += len(line)
                    part_bytes += len(line)
                    largest_line = max(largest_line, len(line))
                    if len(line) > SHARD_LIMIT or part_bytes > SHARD_LIMIT or self.cost["decoded_bytes_read"] > TOTAL_DECODED_LIMIT:
                        self.require("decoded_bounds:"+name+":"+str(index), False)
                    if not line.endswith(b"\n"):
                        self.issue("JSONL_line_integrity", {"stream": name, "part": index, "row": part_rows})
                    part_hash.update(line)
                    total_hash.update(line)
                    part_rows += 1
                    total_rows += 1
                    if total_rows > STREAM_CAPS[name]:
                        self.require("stream_record_cap:"+name, False)
                    self.cost["JSONL_records_parsed"] += 1
                    handler(self.json(line))
            self.cost["gzip_decode_returns"] += 1
            total_bytes += part_bytes
            self.check("decoded_part_bounds:"+expected_path, True,
                       {"largest_line_bytes": largest_line, "decoded_bytes": part_bytes,
                        "stream_records_so_far": total_rows, "stream_record_cap": STREAM_CAPS[name]})
            self.check("decoded_part_identity:"+expected_path,
                       part.get("records") == part_rows and part.get("decoded") == {"bytes": part_bytes, "sha256": part_hash.hexdigest()})
        self.check("decoded_stream_identity:"+name,
                   binding.get("records") == total_rows and binding.get("decoded") == {"bytes": total_bytes, "sha256": total_hash.hexdigest()})
        return total_rows

    def sources(self, archive_blob, run):
        source = run["source"]
        established = source.get("clean_committed_bytes_verified") is True
        self.check("exact_requested_commit", source.get("commit") == SOURCE_COMMIT)
        self.check("clean_source_declaration", established, available=established or run["status"] != "failed")
        files = source.get("files", {})
        self.check("complete_source_population", set(files) == set(SOURCE_PATHS), available=established)
        if archive_blob is None:
            self.check("source_archive_available", False, available=False)
            return
        with zipfile.ZipFile(io.BytesIO(archive_blob)) as archive:
            names = archive.namelist()
            self.require("source_archive_unique_canonical_names", len(names) == len(set(names)) and set(names) == set(files) and set(names) <= set(SOURCE_PATHS))
            archive_bytes = 0
            for name in names:
                self.require("source_member_bound:"+name, archive.getinfo(name).file_size <= 4_194_304)
                self.cost["source_archive_member_read_attempts"] += 1
                data = archive.read(name)
                self.cost["source_archive_member_read_returns"] += 1
                self.cost["source_archive_decoded_bytes"] += len(data)
                archive_bytes += len(data)
                self.require("source_archive_total_bound", archive_bytes <= 16_777_216)
                self.check("archived_source_pin:"+name, pin(data) == files[name])
                if name == PROTOCOL:
                    self.check("frozen_protocol_identity", pin(data) == PROTOCOL_PIN)
                self.cost["git_source_query_attempts"] += 1
                query = subprocess.run(["git", "show", SOURCE_COMMIT+":"+name], cwd=self.repo, capture_output=True, check=False)
                self.cost["git_source_query_returns"] += 1
                self.cost["git_source_return_bytes"] += len(query.stdout)+len(query.stderr)
                self.check("exact_commit_blob:"+name, query.returncode == 0 and query.stdout == data, available=established)

    def run(self):
        manifest = self.json(self.read("manifest.json"))
        self.require("new_EF1B_manifest_identity", manifest.get("experiment_id") == "EF1B" and manifest.get("stage") == "controlonly" and manifest.get("schema_version") == 2)
        files, bindings = manifest["files"], manifest["streams"]
        self.require("bounded_manifest_files", isinstance(files, dict) and len(files) <= 128)
        self.require("known_stream_names", set(bindings) <= set(STREAM_CAPS) and {"trace", "predictions"} <= set(bindings))
        stream_paths = [part["path"] for binding in bindings.values() for part in binding["parts"]]
        self.require("unique_stream_file_population", len(stream_paths) == len(set(stream_paths)) and set(stream_paths) <= set(files))
        payloads, archive = {}, None
        for name in files:
            if name in stream_paths:
                continue
            self.require("known_new_payload:"+name, name in {"run.json", "metrics.json", "models.json", "source.zip", "failure.json"} or name.startswith("installed/EF1B_") and name.endswith(".xml"))
            blob = self.read(name, files[name])
            if name.endswith(".json"):
                payloads[name] = self.json(blob)
            elif name == "source.zip":
                archive = blob
        self.require("required_JSON_payloads", {"run.json", "metrics.json", "models.json"} <= set(payloads))
        run, metrics, models = (payloads[name] for name in ("run.json", "metrics.json", "models.json"))
        self.check("run_manifest_stage_status_stream_binding", run.get("experiment_id") == "EF1B" and run.get("stage") == "controlonly" and run.get("seeds") == list(SEEDS) and run.get("status") == manifest.get("status") and run.get("JSONL_streams") == bindings)
        self.check("scientific_boundary_flags", all(obj.get(key) is False for obj in (run, manifest, metrics) for key in FLAGS))
        self.check("failure_not_scientific_success", not run.get("failure") or run["status"] == "failed" and all(metrics.get(key) is False for key in GATES))
        self.check("failure_payload_binding", payloads.get("failure.json") == run.get("failure"))
        self.sources(archive, run)
        cost, fresh = run["cost"], run.get("trials", [])
        refs, seed_rows = run.get("reused_baseline_trials", []), run.get("seed_results", [])
        expected_fresh = [f"EF1B_{seed}_control_{method}" for seed in SEEDS for method in METHODS]
        expected_reused = [f"FR4_{seed}_control_{method}" for seed in SEEDS for method in ("pd", "zero")]
        fresh_map = {trial.get("trial_id"): trial for trial in fresh}
        ref_map = {trial.get("trial_id"): trial for trial in refs}
        attempted = [trial.get("trial_id") for trial in fresh]
        self.check("fresh_fixed_population_and_order", len(fresh_map) == len(fresh) and attempted == expected_fresh[:len(attempted)] and (len(fresh) == 6 or run["status"] == "failed"))
        self.check("six_reused_source_population", len(ref_map) == len(refs) and set(ref_map) == set(expected_reused), available=bool(refs) or cost.get("control_call_attempts", 0) > 0)
        self.check("zero_new_fit_RLS_and_no_old_rescore", run.get("new_learning_updates") == 0 and run.get("old_metric_recomputation") is False and run.get("old_trace_predictions_paid_reads") is False and all(cost.get(key, 0) == 0 for key in ("RLS_vector_update_attempts", "RLS_vector_update_commits", "RLS_scalar_update_commits", "batch_fit_calls", "task_policy_updates", "teacher_calls", "GPU_training_seconds")))
        self.check("frozen_planned_upper_bounds", run.get("planned_upper_bounds") == PLANNED_UPPER_BOUNDS)
        limits = {"control_call_attempts": 18000, "control_call_returns": 18000, "confirmed_physics_substeps": 18000,
                  "MPC_decision_attempts": 1200, "equilibrium_root_solve_attempts": 12,
                  "equilibrium_branch_svd_attempts": 192, "equilibrium_root_model_pair_prediction_attempts": 192,
                  "equilibrium_root_model_scalar_prediction_attempts": 384, "equilibrium_forecast_pair_prediction_attempts": 180000,
                  "equilibrium_forecast_scalar_prediction_attempts": 360000,
                  "control_conditional_prediction_pair_prediction_attempts": 526560,
                  "control_conditional_prediction_scalar_prediction_attempts": 1053120}
        self.check("actual_new_budget_limits", all(type(cost.get(key, 0)) is int and 0 <= cost.get(key, 0) <= limit for key, limit in limits.items()), limits)
        self.check("history_costs_retained_not_readded", all(value.get("not_added_to_new_cost") is True for value in run.get("source_history_costs", {}).values()))
        for seed in SEEDS:
            for method in ("pd", "zero"):
                trial_id = f"FR4_{seed}_control_{method}"
                ref = ref_map.get(trial_id)
                self.population.append({"seed": seed, "method": method, "origin": "reused_FR4B", "trial_id": trial_id, "present": ref is not None})
                if ref is None:
                    continue
                origin = ref.get("source_origin", {})
                self.check("reused_reference_identity:"+trial_id,
                           ref.get("reused_baseline") is True and ref.get("new_physics") is False and ref.get("conditional_prediction_not_rescored") is True and all(ref.get(key) == 0 for key in ("new_control_calls", "new_physics_substeps", "new_learning_updates")) and origin.get("experiment_id") == "FR4B" and origin.get("source_commit") == FR4B_COMMIT and origin.get("manifest") == FR4B_MANIFEST and {key: origin.get("first_audit", {}).get(key) for key in FR4B_AUDIT} == FR4B_AUDIT and origin.get("source_trial_id") == trial_id and origin.get("new_controls") == 0)
        model_fps = {}
        for seed in SEEDS:
            pair = models.get(str(seed), {})
            for method in METHODS:
                snapshot = pair.get(method)
                if snapshot is None:
                    continue
                record = {key: value for key, value in snapshot.items() if key not in {"parameter_fingerprint", "trainable", "vector_update_count", "scalar_update_count", "output_update_counts", "update_commit", "initial_prior", "input_boundary"}}
                self.cost["new_snapshot_fingerprint_recomputations"] += 1
                fingerprint = hashlib.sha256(json.dumps(record, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
                model_fps[(seed, method)] = fingerprint
                self.check(f"frozen_model_snapshot:{seed}:{method}", fingerprint == snapshot.get("parameter_fingerprint") and snapshot.get("trainable") is False and snapshot.get("vector_update_count") == (0 if method == "cold" else 4000) and snapshot.get("scalar_update_count") == (0 if method == "cold" else 8000) and snapshot.get("dt_seconds") == .002 and finite(snapshot.get("coefficients"), (2, 9)))
        trace = defaultdict(list)
        def trace_row(row):
            self.cost["fresh_trace_rows_inspected"] += 1
            trial_id = row.get("trial_id")
            if trial_id not in fresh_map:
                self.issue("fresh_trace_population", trial_id)
                return
            index = len(trace[trial_id])
            if row.get("control_index") != index or row.get("phase") != ("prefix" if index < 1000 else "active") or row.get("phase_index") != (index if index < 1000 else index-1000) or row.get("seed") != fresh_map[trial_id].get("seed") or row.get("transition_id") != f"{trial_id}:{index}":
                self.issue("fresh_trace_population", {"trial": trial_id, "index": index})
            row["_audit_complete"] = complete(row)
            trace[trial_id].append(row)
        trace_count = self.stream("trace", bindings["trace"], files, trace_row)
        returned = sum(row.get("returned") is True for rows in trace.values() for row in rows)
        paid = sum(row.get("confirmed_completed_substeps", 0) for rows in trace.values() for row in rows)
        trace_full = trace_count == cost.get("control_call_attempts", 0)
        self.check("fresh_paid_trace_cost_binding", trace_count <= cost.get("control_call_attempts", 0) and returned <= cost.get("control_call_returns", 0) and paid <= cost.get("confirmed_physics_substeps", 0) and (run["status"] == "failed" or trace_full and returned == cost.get("control_call_returns", 0) and paid == cost.get("confirmed_physics_substeps", 0)))
        tracking_by_seed = {row["seed"]: row for row in seed_rows}
        complete_by_trial, qualified_by_trial = {}, {}
        for seed in SEEDS:
            for method in METHODS:
                trial_id = f"EF1B_{seed}_control_{method}"
                trial, rows = fresh_map.get(trial_id), trace[trial_id]
                self.population.append({"seed": seed, "method": method, "origin": "fresh_new", "trial_id": trial_id, "present": trial is not None, "saved_control_attempts": len(rows), "planned_control_attempts": 3000})
                if trial is None:
                    continue
                expected_fps = {name: model_fps.get((seed, name)) for name in METHODS}
                for key in ("model_fingerprints_before", "model_fingerprints_after_control", "model_fingerprints_after"):
                    self.check(key+":"+trial_id, trial.get(key) == expected_fps, available=key in trial)
                trial_trace_full = len(rows) == trial.get("record_end", len(rows))-trial.get("record_start", 0)
                self.check("saved_trial_trace_coverage:"+trial_id, trial_trace_full, available=trace_full)
                ref = ref_map.get(f"FR4_{seed}_control_pd")
                keys = ("installed_xml_identity", "physical_fingerprint_before", "execution_fingerprint_before", "interface_fingerprint", "support", "qref2", "public_joint_ranges2", "direction_selection", "targets_q2")
                self.check("fresh_reference_initialization:"+trial_id, ref is not None and all(trial.get(key) == ref.get(key) for key in keys), available=all(key in trial and trial[key] is not None for key in keys))
                if not trial_trace_full:
                    self.check("fresh_metrics_saved_trace_available:"+trial_id, False, available=False)
                    continue
                completion = {"saved_records": len(rows), "no_failure": trial.get("failure") is None,
                              "no_stop": trial.get("stop") is None, "metadata_stable": trial.get("metadata_stable") is True,
                              "all_complete_telemetry": all(row["_audit_complete"] for row in rows)}
                trial_complete = bool(len(rows) == 3000 and all(completion[key] for key in
                    ("no_failure", "no_stop", "metadata_stable", "all_complete_telemetry")))
                complete_by_trial[trial_id] = trial_complete
                self.check("fresh_trial_complete_definition:"+trial_id, trial.get("complete") is trial_complete,
                           completion, available=trace_full)
                audited_trial = dict(trial, complete=trial_complete)
                recomputed_effort = self.effort(rows, audited_trial)
                saved_effort = trial.get("actual_effort", {})
                self.check("fresh_actual_effort:"+trial_id, all(same(values, {key: saved_effort.get(phase, {}).get(key) for key in values}) for phase, values in recomputed_effort.items()))
                qualified = self.contact_qualified(rows, audited_trial)
                qualified_by_trial[trial_id] = qualified
                self.check("fresh_contact_qualification:"+trial_id, qualified == trial.get("free_root_domain_qualification_passed", False))
                active = [row for row in rows if row["phase"] == "active"]
                errors = []
                for row in active:
                    if not finite(row.get("current_target_q2"), (2,)) or not row.get("observation_after"):
                        continue
                    q, _ = native(row["observation_after"])
                    difference = q-np.asarray(row["current_target_q2"])
                    if not same(difference.tolist(), row.get("target_error_rad")):
                        self.issue("fresh_tracking_row_error", row["transition_id"])
                    errors.append(difference)
                available = bool(trial_complete and qualified and len(active) == 2000 and len(errors) == 2000 and recomputed_effort["active"]["complete"])
                score = {"available": available, "planned_active_count": 2000, "observed_active_count": len(active), "partial_subset_ranking": False,
                         "axis_rmse_rad": None, "joint_rmse_rad": None, "actual_absolute_two_axis_nm_s": None, "actual_squared_two_axis_nm2_s": None}
                if available:
                    self.cost["fresh_tracking_axis_RMSE_vector_computations"] += 1
                    self.cost["fresh_tracking_joint_RMSE_scalar_computations"] += 1
                    squared = np.asarray(errors)**2
                    score.update(axis_rmse_rad=np.sqrt(np.mean(squared, axis=0)).tolist(), joint_rmse_rad=float(np.sqrt(np.mean(squared))),
                                 **{key: recomputed_effort["active"][key] for key in ("actual_absolute_two_axis_nm_s", "actual_squared_two_axis_nm2_s")})
                saved = tracking_by_seed.get(seed, {}).get("tracking_scores", {}).get(method)
                self.check("fresh_tracking_score:"+trial_id, saved is not None and same(score, {key: saved.get(key) for key in score}), available=saved is not None)
                self.rechecks.append({"trial_id": trial_id, "tracking": score, "actual_effort": recomputed_effort})
        groups = defaultdict(lambda: {"rows": {}, "q": [], "v": [], "errors": 0})
        def prediction(row):
            self.cost["fresh_prediction_rows_inspected"] += 1
            trial_id, model, horizon, origin = (row.get(key) for key in ("trial_id", "model", "horizon", "origin_active_index"))
            if trial_id not in fresh_map or model not in METHODS or horizon not in HORIZONS or type(origin) is not int or origin not in range(0, 2000-horizon+1, 10):
                self.issue("fresh_prediction_population", {"trial": trial_id, "model": model, "H": horizon, "origin": origin})
                return
            group = groups[(trial_id, model, horizon)]
            if origin in group["rows"]:
                self.issue("fresh_prediction_population", "duplicate_origin")
            group["rows"][origin] = row.get("available")
            if row.get("available") is not True:
                if row.get("available") is not False or not (row.get("unavailable_reason") or row.get("failure")):
                    self.issue("fresh_prediction_unavailability", {"trial": trial_id, "H": horizon, "origin": origin})
                return
            active = trace[trial_id][1000:]
            segment = active[origin:origin+horizon]
            if len(segment) != horizon or not all(item["_audit_complete"] for item in segment):
                self.issue("fresh_prediction_saved_segment", {"trial": trial_id, "origin": origin})
                return
            q0, v0 = native(segment[0]["observation_before"])
            aq, av = native(segment[-1]["observation_after"])
            expected_input = {"q2": q0.tolist(), "v2": v0.tolist(), "known_requests2": [item["requested_torque"][:2] for item in segment]}
            paths_ok = finite(row.get("predicted_q_path"), (horizon, 2)) and finite(row.get("predicted_v_path"), (horizon, 2))
            if not paths_ok:
                self.issue("fresh_prediction_finite_paths", {"trial": trial_id, "origin": origin})
                return
            dq, dv = np.asarray(row["predicted_q_path"][-1])-aq, np.asarray(row["predicted_v_path"][-1])-av
            self.cost["fresh_saved_endpoint_error_pair_computations"] += 1
            valid = row.get("scope") == "control_conditional_prediction" and row.get("seed") == fresh_map[trial_id]["seed"] and row.get("model_parameter_fingerprint") == model_fps.get((row["seed"], model)) and same(expected_input, row.get("model_input")) and same(aq.tolist(), row.get("actual_endpoint_q2")) and same(av.tolist(), row.get("actual_endpoint_v2")) and same(dq.tolist(), row.get("q_error_rad")) and same(dv.tolist(), row.get("v_error_rad_s"))
            if not valid:
                self.issue("fresh_prediction_binding_or_error", {"trial": trial_id, "H": horizon, "origin": origin})
            group["q"].append(dq)
            group["v"].append(dv)
        prediction_count = self.stream("predictions", bindings["predictions"], files, prediction)
        prediction_rechecks = []
        for seed in SEEDS:
            for source_method in METHODS:
                trial_id = f"EF1B_{seed}_control_{source_method}"
                trial = fresh_map.get(trial_id)
                if trial is None:
                    continue
                summary = tracking_by_seed.get(seed, {}).get("conditional_prediction_scores", {}).get(source_method)
                for horizon in HORIZONS:
                    planned = len(range(0, 2000-horizon+1, 10))
                    for model in METHODS:
                        group = groups[(trial_id, model, horizon)]
                        saved = (summary or {}).get("horizons", {}).get(str(horizon), {}).get("models", {}).get(model)
                        available = bool(complete_by_trial.get(trial_id) and qualified_by_trial.get(trial_id) and len(group["q"]) == planned)
                        actual = {"available": available, "observed_origin_count": len(group["q"]), "q_rmse_axis_rad": None, "v_rmse_axis_rad_s": None, "partial_subset_ranking": False}
                        if available:
                            self.cost["fresh_self_RMSE_vector_computations"] += 2
                            actual.update(q_rmse_axis_rad=np.sqrt(np.mean(np.asarray(group["q"])**2, axis=0)).tolist(), v_rmse_axis_rad_s=np.sqrt(np.mean(np.asarray(group["v"])**2, axis=0)).tolist())
                        self.check(f"fresh_self_score:{trial_id}:{model}:H{horizon}", saved is not None and same(actual, saved), available=saved is not None and trace_full)
                        if saved is not None:
                            self.check(f"fresh_self_origin_population:{trial_id}:{model}:H{horizon}", len(group["rows"]) == planned, available=run["status"] != "failed" or len(group["rows"]) == planned)
                        prediction_rechecks.append({"trial_id": trial_id, "model": model, "horizon": horizon, "planned_origin_count": planned, "saved_records": len(group["rows"]), **actual})
        paid_kinds = Counter()
        def paid_row(row):
            self.cost["new_paid_journal_rows_inspected"] += 1
            paid_kinds[row.get("entry_kind")] += 1
            if row.get("entry_kind") not in {"paid_native_endpoint", "endpoint_audit_annotation", "collector_failure_annotation"} or row.get("record", {}).get("trial_id") not in fresh_map:
                self.issue("new_paid_journal_population", row.get("entry_kind"))
        if "paid_intervals" in bindings:
            self.stream("paid_intervals", bindings["paid_intervals"], files, paid_row)
        self.check("new_paid_endpoint_coverage", paid_kinds["paid_native_endpoint"] == cost.get("control_call_returns", 0), available=run["status"] != "failed" or paid_kinds["paid_native_endpoint"] == cost.get("control_call_returns", 0))
        if run["status"] == "completed":
            self.check("completed_fixed_population", len(fresh) == len(refs) == 6 and trace_count == 18000 and prediction_count == 11772)
        for name, item in self.issues.items():
            self.check(name, item["count"] == 0, item)
        return {"run_status": run["status"], "run_failure": run.get("failure"), "fixed_population": self.population,
                "fresh_metric_rechecks": self.rechecks, "fresh_self_rechecks": prediction_rechecks,
                "new_paid_entry_counts": dict(paid_kinds), "saved_scientific_gate_values": {key: metrics.get(key) for key in GATES},
                "scientific_gates_recomputed": False, "old_metrics_recomputed": False}

    def effort(self, rows, trial):
        result = {}
        for phase in ("prefix", "active"):
            selected = [row for row in rows if row["phase"] == phase]
            values = {key: [0., 0.] for key in ("actual_absolute_axis_nm_s", "actual_squared_axis_nm2_s", "applied_absolute_axis_nm_s", "applied_squared_axis_nm2_s")}
            values.update(all8_actual_absolute_nm_s=0., all8_actual_squared_nm2_s=0., captured_substeps=0)
            missing = False
            for row in selected:
                for sample in (row.get("diagnostics") or row.get("saved_partial") or {}).get("substep_native_and_contact_records", []):
                    if not all(finite(sample.get(key), (8,)) for key in ("actual_actuator_torque8", "applied_command8")):
                        missing = True
                        continue
                    actual, applied = (np.asarray(sample[key], dtype=float) for key in ("actual_actuator_torque8", "applied_command8"))
                    self.cost["fresh_effort_sample_computations"] += 1
                    for index in range(2):
                        for signal, vector in (("actual", actual), ("applied", applied)):
                            values[signal+"_absolute_axis_nm_s"][index] += abs(float(vector[index]))*.002
                            values[signal+"_squared_axis_nm2_s"][index] += float(vector[index])**2*.002
                    values["all8_actual_absolute_nm_s"] += float(np.sum(np.abs(actual))*.002)
                    values["all8_actual_squared_nm2_s"] += float(np.sum(actual**2)*.002)
                    values["captured_substeps"] += 1
            complete_effort = bool(selected and all(row["_audit_complete"] for row in selected) and values["captured_substeps"] == len(selected) and not missing)
            if phase == "active":
                complete_effort = complete_effort and trial.get("complete") is True
            paid = sum(row.get("confirmed_completed_substeps", 0) for row in selected)
            values.update(complete=complete_effort, actual_absolute_two_axis_nm_s=sum(values["actual_absolute_axis_nm_s"]), actual_squared_two_axis_nm2_s=sum(values["actual_squared_axis_nm2_s"]),
                          confirmed_paid_substeps=paid, unknown_actual_effort_substeps=paid-values["captured_substeps"], actual_effort_population_complete=paid == values["captured_substeps"] and not missing)
            result[phase] = values
        return result

    def contact_qualified(self, rows, trial):
        qualified = True
        for phase, start, end in (("prefix", 0, 1000), ("active", 0, 1000), ("active", 1000, 2000)):
            selected = [row for row in rows if row["phase"] == phase and start <= row["phase_index"] < end]
            observed = [row for row in selected if row.get("contact_audit_complete") is True]
            paid = sum(row.get("confirmed_completed_substeps", 0) for row in selected)
            positives = sum(sum(pair["positive_normal_force_n"] for pair in row["audit_contacts"]["floor_pairs"] if pair["category"] == "left_arm") > 0 for row in observed)
            qualified &= bool(trial.get("complete") and len(selected) == paid == len(observed) == 1000 and positives >= 1)
        return qualified


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.source_commit != SOURCE_COMMIT:
        parser.error("only the first exact EF1B source commit is accepted")
    repo, output = args.repo.resolve(), args.output.resolve()
    raw = (repo / RAW_RELATIVE).resolve()
    if output.exists() or output == raw or output.is_relative_to(raw) or raw.is_relative_to(output):
        parser.error("existing/overlapping first audit output is refused")
    output.mkdir(parents=True, exist_ok=False)
    audit, result, failure, exit_code = Audit(repo, raw), None, None, 1
    with (output / "stdout.log").open("x", encoding="utf-8") as stdout, (output / "stderr.log").open("x", encoding="utf-8") as stderr:
        with redirect_stdout(stdout), redirect_stderr(stderr):
            try:
                result = audit.run()
            except BaseException as exc:
                failure = {"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()}
                traceback.print_exc()
    failed = [check for check in audit.contracts if check["available"] and check["passed"] is not True]
    unavailable = [check for check in audit.contracts if not check["available"]]
    status = "failed" if failure or failed else "partial" if unavailable else "passed"
    report = {"schema": "EF1B_first_saved_audit_v1", "status": status, "checks": len(audit.contracts), "failures": len(failed),
              "unavailable_contracts": len(unavailable), "first_failure": failure or (failed[0] if failed else None), "contracts": audit.contracts,
              "input_identities": audit.inputs, "actual_audit_cost": dict(audit.cost), "result": result,
              "partial_metric_rechecks": audit.rechecks if result is None else None, "partial_population": audit.population if result is None else None,
              "issues": dict(audit.issues), "source_commit": SOURCE_COMMIT, "completed_utc": datetime.now(timezone.utc).isoformat(),
              "production_imports": 0, "physics_calls": 0, "model_calls": 0, "fit_calls": 0, "old_raw_reads": 0, "old_audit_replays": 0,
              "scientific_gate_recomputations": 0, "scientific_adoption": False}
    with (output / "audit.json").open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, allow_nan=False, indent=2)
        stream.write("\n")
    if status == "passed":
        exit_code = 0
    print(json.dumps({"status": status, "checks": len(audit.contracts), "failures": len(failed), "output": str(output)}))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
