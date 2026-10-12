"""First EF1B control-only entry; refused until its published protocol is pinned.

Only source-bound FR4A run/metrics/models and FR4B run/metrics plus a hash-bound
first audit are read. Old trace, predictions and paid ledgers are never read or
rescored. The parent launcher retains first stdout, stderr and process status.
"""
from __future__ import annotations

import argparse
from collections import Counter
import gzip
import hashlib
import importlib.metadata
import io
import json
import math
from pathlib import Path
import platform
import subprocess
import sys
import time
import traceback
import zipfile

SOURCE_PATH = "scripts/develop_equilibrium_feedforward.py"
MODULE_PATH = "src/developmental_physics/equilibrium_feedforward_development.py"
CONTROLLER_PATH = "src/developmental_physics/equilibrium_feedforward_pair.py"
PROTOCOL_PATH = "docs/EQUILIBRIUM_FEEDFORWARD_CONTROL_PROTOCOL.md"
PROTOCOL_PIN = {'bytes': 12884, 'sha256': 'cf51c5a7500a57c0306bf7a06effddb09b85b984433d6baaa81097de7fc893bf'}  # Frozen before the first physical invocation.
ENGINEERING_PROTOCOL_PATH = "docs/FREE_ROOT_FAST_FEEDBACK_ENGINEERING_PROTOCOL.md"
ENGINEERING_PROTOCOL_PIN = {"bytes": 9189, "sha256": "5bb40312c37418b639f11ea32da007c3e5835a74ace19defe9c235e29bfe2c86"}
FR4_PROTOCOL_PATH = "docs/PD_ANCHOR_PAIR_LEARNING_PROTOCOL.md"
FR4_PROTOCOL_PIN = {"bytes": 14616, "sha256": "ae9b8ea0515d3ff71ac8c636e08542fa7b19725c5746613acd5d619284978b1f"}
FR4A_RAW = "results/cpu_validation/2026-10-12_pd_anchor_pair_prediction/raw"
FR4A_SOURCE_COMMIT = "f4fca3f4236acddc92a25c6707f9c29150ee3ca6"
FR4A_MANIFEST_PIN = {"bytes": 2209, "sha256": "776cd4abbb69b5c6189c0d015ba4868cffa1713f5c43f388377ff868da9228d9"}
FR4B_RAW = "results/cpu_validation/2026-10-12_pd_anchor_pair_control/raw"
FR4B_SOURCE_COMMIT = "490fcffa0080125e7c2a8b887c99cc2743dcc01f"
FR4B_MANIFEST_PIN = {"bytes": 3154, "sha256": "ee66a39474fe6716af90a7671452a95a53541ec676ee7125e07416eed3153d9d"}
FR4B_AUDIT_PATH = "results/cpu_validation/2026-10-12_pd_anchor_pair_control/audit_first/audit.json"
FR4B_AUDIT_PIN = {"bytes": 41990, "sha256": "639fc31e3ff6792a8313765ec0a4244f513f50db8b3fa76017f9e7b6830e0b53"}
FR4B_FIRST_AUDIT_DECLARATION = {"status": "passed", "checks": 674441, "failures": 0,
                                "origin": "root_publicly_reported_first_saved_audit"}
OLD_DEPENDENCY_PATHS = (
    "scripts/develop_pd_anchor_pair.py",
    "src/developmental_physics/pd_anchor_pair_development.py", FR4_PROTOCOL_PATH,
    "scripts/validate_free_root_fast_feedback_engineering.py",
    "src/developmental_physics/free_root_fast_feedback_environment.py", ENGINEERING_PROTOCOL_PATH,
    "src/developmental_physics/environment.py", "src/developmental_physics/assets/ground_body.xml",
    "src/developmental_physics/__init__.py", "pyproject.toml",
    "src/developmental_physics/fast_feedback_pair_model.py",
    "src/developmental_physics/guard_coupled_pair_model.py",
    "src/developmental_physics/guard_pair_model.py", "src/developmental_physics/local_pair_model.py",
    "src/developmental_physics/local_model.py", "src/developmental_physics/fast_feedback_pair_mpc.py",
    "src/developmental_physics/batched_fast_feedback_pair_mpc.py",
    "src/developmental_physics/pd_anchor_pair_mpc.py",
    "src/developmental_physics/fast_feedback_pair_development.py",
)
DEPENDENCY_PATHS = (SOURCE_PATH, MODULE_PATH, CONTROLLER_PATH, PROTOCOL_PATH, *OLD_DEPENDENCY_PATHS)
SEEDS = [8101, 8102, 8103]
FLAGS = {"scientific_adoption": False, "old_free_root_C4_validation": False,
         "c4_scientific_validation": False, "c5_scientific_dependency_released": False,
         "c4_contact_scientific_validation": False}
GATE_FLAGS = ("ef1b_model_contribution_gate_passed", "ef1b_pd_reference_gate_passed",
              "ef1_free_root_mechanism_validation")
OLD_GATE_FLAGS = ("fr4a_prediction_gate_passed", "fr4b_model_contribution_gate_passed",
                  "fr4b_pd_reference_gate_passed", "fr4_free_root_mechanism_validation")
MAX_FILE_BYTES = 100_000_000
JSONL_DECODED_SHARD_BYTES = 64_000_000


def identity(data):
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def safe(value):
    """Serialize arrays/scalars without importing a physical or learning module."""
    if isinstance(value, dict):
        return {str(key): safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [safe(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        return {"nonfinite_float": str(value)}
    if hasattr(value, "tolist"):
        return safe(value.tolist())
    return value


def encoded(value):
    return (json.dumps(safe(value), ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def read_bytes(path, cost, scope):
    cost[scope + "_file_read_attempts"] += 1
    data = path.read_bytes()
    cost[scope + "_file_read_returns"] += 1
    cost[scope + "_read_and_hash_bytes"] += len(data)
    return data


def verify_sources(repo, commit, cost, files, source_bytes):
    if PROTOCOL_PIN is None:
        raise ValueError("final_published_EF1B_protocol_pin_required")
    if (not isinstance(PROTOCOL_PIN, dict) or set(PROTOCOL_PIN) != {"bytes", "sha256"}
            or type(PROTOCOL_PIN["bytes"]) is not int or PROTOCOL_PIN["bytes"] <= 0
            or not isinstance(PROTOCOL_PIN["sha256"], str) or len(PROTOCOL_PIN["sha256"]) != 64
            or any(c not in "0123456789abcdef" for c in PROTOCOL_PIN["sha256"])):
        raise ValueError("exact_published_protocol_identity_required")
    if Path(__file__).resolve() != (repo / SOURCE_PATH).resolve():
        raise ValueError("canonical_frozen_EF1B_runner_required")
    if (not isinstance(commit, str) or len(commit) != 40
            or any(c not in "0123456789abcdef" for c in commit)):
        raise ValueError("exact_source_commit_required")

    def git(*args):
        cost["git_query_attempts"] += 1
        returned = subprocess.run(["git", *args], cwd=repo, capture_output=True, check=False)
        cost["git_return_bytes"] += len(returned.stdout) + len(returned.stderr)
        if returned.returncode:
            raise ValueError("source_git_query_failed")
        return returned.stdout

    if (git("rev-parse", "HEAD").decode().strip() != commit
            or git("status", "--porcelain", "--untracked-files=all").strip()):
        raise ValueError("clean_exact_EF1B_HEAD_required")
    for name in DEPENDENCY_PATHS:
        data = read_bytes(repo / name, cost, "source")
        files[name] = identity(data)
        source_bytes[name] = data
        expected = (PROTOCOL_PIN if name == PROTOCOL_PATH else
                    ENGINEERING_PROTOCOL_PIN if name == ENGINEERING_PROTOCOL_PATH else
                    FR4_PROTOCOL_PIN if name == FR4_PROTOCOL_PATH else None)
        if expected is not None and files[name] != expected:
            raise ValueError("fixed_FR_protocol_bytes_differ:" + name)
        if git("show", f"{commit}:{name}") != data:
            raise ValueError("committed_dependency_bytes_differ:" + name)


def normalize_metrics_boundary(metrics, *, failed=False):
    """Explicit false stage defaults; a production exception vetoes all gates."""
    for key in GATE_FLAGS:
        metrics.setdefault(key, False)
    metrics.update(FLAGS)
    if failed:
        metrics.update({key: False for key in GATE_FLAGS})
    return metrics


def _all_old_flags_false(run, metrics, stage):
    if any(run.get(key) is not False or metrics.get(key) is not False for key in FLAGS):
        raise ValueError("C4_C5_adoption_flags_must_remain_false:" + stage)


def _require_fr4a_trial(trial, seed, kind, active_count, files):
    expected = 1000 + active_count
    support = trial.get("support", {})
    if (trial.get("seed") != seed or trial.get("kind") != kind
            or trial.get("complete") is not True or trial.get("native_execution_complete") is not True
            or trial.get("status") != "completed" or trial.get("stop") is not None
            or trial.get("failure") is not None or trial.get("metadata_stable") is not True
            or trial.get("planned_prefix") != 1000 or trial.get("planned_active") != active_count
            or trial.get("returned_intervals") != expected
            or trial.get("free_root_domain_qualification_passed") is not True
            or trial.get("original_asset_unchanged_no_mount") is not True
            or trial.get("installed_xml_identity") != files["src/developmental_physics/assets/ground_body.xml"]
            or support.get("root") != "original_asset_freejoint" or support.get("mount") is not None
            or support.get("external_support") is not False or support.get("initial_pose") != "supine"):
        raise ValueError("complete_new_FR4A_native_contact_domain_trial_required:" + kind)
    contact = trial.get("contact_population", {})
    phases = contact.get("phases", {})
    if (contact.get("qualification_passed") is not True
            or contact.get("no_contact_based_training_selection") is not True
            or contact.get("contact_causality_or_continuous_support_demonstrated") is not False
            or set(phases) != {"prefix", "active"}):
        raise ValueError("complete_FR4A_contact_population_metadata_required:" + kind)
    for name, planned in (("prefix", 1000), ("active", active_count)):
        phase = phases[name]
        positive = phase.get("classes", {}).get("left_arm", {}).get("positive_contact_endpoint_count")
        if (phase.get("qualification_passed") is not True or phase.get("planned_count") != planned
                or phase.get("record_count") != planned or phase.get("confirmed_substeps") != planned
                or phase.get("observed_contact_endpoints") != planned
                or phase.get("unknown_paid_contact_substeps") != 0
                or type(positive) is not int or not 1 <= positive <= planned):
            raise ValueError("all_complete_FR4A_contact_phases_required:" + kind + ":" + name)
    effort = trial.get("actual_effort", {})
    if any(effort.get(name, {}).get("complete") is not True
           or effort[name].get("actual_effort_population_complete") is not True
           or effort[name].get("unknown_actual_effort_substeps") != 0 for name in ("prefix", "active")):
        raise ValueError("complete_FR4A_known_actual_effort_population_required:" + kind)


def _require_fr4a(loaded, manifest, files):
    run, metrics, models = loaded["run.json"], loaded["metrics.json"], loaded["models.json"]
    source, cost = run.get("source", {}), run.get("cost", {})
    if (run.get("experiment_id") != "FR4A" or manifest.get("experiment_id") != "FR4A"
            or run.get("stage") != "prediction" or manifest.get("stage") != "prediction"
            or set(source.get("files", {})) != set(files)
            or any(source["files"][name] != files[name] for name in files)):
        raise ValueError("all_new_FR4A_frozen_dependencies_required_for_FR4B")
    if (run.get("seeds") != SEEDS or metrics.get("fr4a_prediction_gate_passed") is not True
            or metrics.get("complete_population") is not True
            or cost.get("control_call_returns") != 21000 or cost.get("confirmed_physics_substeps") != 21000
            or cost.get("RLS_vector_update_commits") != 12000
            or cost.get("RLS_scalar_update_commits") != 24000
            or run.get("unattempted_seeds") != []
            or set(models) != {str(seed) for seed in SEEDS}):
        raise ValueError("complete_new_FR4A_prediction_gate_and_three_snapshots_required")
    rows = run.get("seed_results", [])
    if (len(rows) != 3 or {row.get("seed") for row in rows} != set(SEEDS)
            or any(row.get("calibration", {}).get("complete") is not True
                   or row.get("prediction", {}).get("complete") is not True
                   or row.get("calibration", {}).get("stop") is not None
                   or row.get("prediction", {}).get("stop") is not None
                   or row.get("calibration", {}).get("failure") is not None
                   or row.get("prediction", {}).get("failure") is not None for row in rows)):
        raise ValueError("complete_FR4A_calibration_prediction_installations_required")
    if len(run.get("trials", [])) != 6:
        raise ValueError("six_complete_FR4A_trials_required")
    trial_ids = set()
    for row in rows:
        for kind, active_count in (("calibration", 4000), ("prediction", 1000)):
            trial = row[kind]
            _require_fr4a_trial(trial, row["seed"], kind, active_count, files)
            if trial.get("trial_id") != f"FR4_{row['seed']}_{kind}" or trial["trial_id"] in trial_ids:
                raise ValueError("unique_FR4A_trial_id_required")
            trial_ids.add(trial["trial_id"])
        score = row.get("prediction_scores", {})
        if (score.get("complete_population") is not True
                or score.get("native_execution_complete") is not True
                or score.get("free_root_domain_qualification_passed") is not True):
            raise ValueError("FR4A_score_complete_domain_metadata_required")
    if {trial.get("trial_id") for trial in run["trials"]} != trial_ids:
        raise ValueError("FR4A_trial_matrix_and_seed_installations_differ")
    by_id = {trial["trial_id"]: trial for trial in run["trials"]}
    if any(by_id[row[kind]["trial_id"]] != row[kind]
           for row in rows for kind in ("calibration", "prediction")):
        raise ValueError("FR4A_saved_trial_matrix_payload_differs")
    for snapshots in models.values():
        if set(snapshots) != {"cold", "learned"}:
            raise ValueError("both_exact_new_FR4A_frozen_models_required")
        if (snapshots["cold"].get("vector_update_count") != 0
                or snapshots["learned"].get("vector_update_count") != 4000
                or any(snapshot.get("trainable") is not False for snapshot in snapshots.values())):
            raise ValueError("new_FR4A_zero_and_4000_atomic_frozen_counts_required")
    if any(metrics.get(key) is not False for key in OLD_GATE_FLAGS if key != "fr4a_prediction_gate_passed"):
        raise ValueError("FR4A_prediction_cannot_predeclare_control_mechanism_success")


def summary_only(value):
    if isinstance(value, dict):
        return {key: summary_only(item) for key, item in value.items()
                if key not in ("records", "installed_xml_utf8")}
    if isinstance(value, (list, tuple)):
        return [summary_only(item) for item in value]
    return value


def finite_shape(value, shape):
    if not shape:
        return type(value) in (int, float) and math.isfinite(value)
    return (isinstance(value, list) and len(value) == shape[0]
            and all(finite_shape(item, shape[1:]) for item in value))


def snapshot_before_construction(snapshot, count, reference):
    guard = snapshot.get("input_mapping", {}).get("public_guard", {})
    if (snapshot.get("structure") != "coupled_hinge9" or snapshot.get("trainable") is not False
            or snapshot.get("dt_seconds") != .002 or snapshot.get("integration") != "endpoint_euler"
            or snapshot.get("initial_covariance_scale") != 100. or snapshot.get("forgetting_factor") != 1.
            or snapshot.get("hinge_threshold_nm") != .25 or snapshot.get("dtype") != "float64"
            or snapshot.get("hinge_threshold_updates") != 0
            or snapshot.get("vector_update_count") != count or snapshot.get("scalar_update_count") != 2*count
            or snapshot.get("output_update_counts") != [count, count]
            or not finite_shape(snapshot.get("coefficients"), (2, 9))
            or not finite_shape(snapshot.get("covariance"), (2, 9, 9))
            or not finite_shape(snapshot.get("initial_coefficients"), (2, 9))
            or not finite_shape(snapshot.get("qref_rad"), (2,))
            or snapshot["qref_rad"] != reference["qref2"]
            or guard.get("public_joint_ranges_rad") != reference["public_joint_ranges2"]
            or guard.get("rule") != "known_angle_guard_control_start_v1"
            or guard.get("angle_margin_rad") != .03 or guard.get("request_clip_per_axis_nm") != .5
            or snapshot.get("input_mapping", {}).get("guard_used_by_model") is not True
            or not finite_shape(guard.get("public_joint_ranges_rad"), (2, 2))):
        raise ValueError("complete_lawful_frozen_snapshot_required_before_constructor")
    excluded = {"parameter_fingerprint", "trainable", "vector_update_count", "scalar_update_count",
                "output_update_counts", "update_commit", "initial_prior", "input_boundary"}
    record = {key: value for key, value in snapshot.items() if key not in excluded}
    fingerprint = hashlib.sha256(json.dumps(record, sort_keys=True, separators=(",", ":"),
                                            allow_nan=False).encode("utf-8")).hexdigest()
    if fingerprint != snapshot.get("parameter_fingerprint"):
        raise ValueError("saved_snapshot_parameter_fingerprint_mismatch_before_constructor")


def read_fixed_gate(repo, cost, files, runtime, stage):
    if stage == "FR4A":
        relative, manifest_pin, source_commit, payload_names = (
            FR4A_RAW, FR4A_MANIFEST_PIN, FR4A_SOURCE_COMMIT, ("run.json", "metrics.json", "models.json"))
    elif stage == "FR4B":
        relative, manifest_pin, source_commit, payload_names = (
            FR4B_RAW, FR4B_MANIFEST_PIN, FR4B_SOURCE_COMMIT, ("run.json", "metrics.json"))
    else:
        raise ValueError("fixed_FR4A_FR4B_gate_only")
    raw = (repo / relative).resolve()
    if not raw.is_relative_to(repo):
        raise ValueError("fixed_source_gate_outside_repository")
    data = read_bytes(raw / "manifest.json", cost, "gate")
    if identity(data) != manifest_pin:
        raise ValueError("fixed_first_manifest_identity_differs:"+stage)
    manifest = json.loads(data)
    cost["gate_json_parses"] += 1
    binding = {"relative_raw_path": relative, "manifest": identity(data), "files": {}}
    loaded = {}
    for name in payload_names:
        data = read_bytes(raw / name, cost, "gate")
        pin = identity(data)
        if manifest.get("files", {}).get(name) != pin:
            raise ValueError("fixed_manifest_payload_identity_differs:"+stage+":"+name)
        binding["files"][name] = pin
        loaded[name] = json.loads(data)
        cost["gate_json_parses"] += 1
    run, metrics = loaded["run.json"], loaded["metrics.json"]
    source = run.get("source", {})
    old_files = {name: files[name] for name in OLD_DEPENDENCY_PATHS}
    if (manifest.get("status") != "completed" or run.get("status") != "completed"
            or manifest.get("experiment_id") != stage or run.get("experiment_id") != stage
            or source.get("commit") != source_commit
            or source.get("clean_committed_bytes_verified") is not True
            or source.get("files") != old_files
            or any(run.get("runtime", {}).get(key) != runtime[key] for key in ("python", "numpy", "mujoco"))
            or run.get("failure") is not None):
        raise ValueError("fixed_completed_clean_exact_source_runtime_gate_required:"+stage)
    _all_old_flags_false(run, metrics, stage)
    if stage == "FR4A":
        _require_fr4a(loaded, manifest, old_files)
        for row in run["seed_results"]:
            snapshots = loaded["models.json"][str(row["seed"])]
            reference = row["calibration"]
            for name, count in (("cold", 0), ("learned", 4000)):
                snapshot_before_construction(snapshots[name], count, reference)
                if row["prediction_scores"]["model_fingerprints"].get(name) != snapshots[name]["parameter_fingerprint"]:
                    raise ValueError("FR4A_snapshot_score_fingerprint_provenance_differs")
    else:
        if (run.get("stage") != "control" or manifest.get("stage") != "control"
                or run.get("seeds") != SEEDS or run.get("unattempted_seeds") != []
                or run.get("cost", {}).get("control_call_returns") != 36000
                or run.get("cost", {}).get("confirmed_physics_substeps") != 36000
                or run.get("cost", {}).get("RLS_vector_update_commits") != 0
                or run.get("cost", {}).get("RLS_scalar_update_commits") != 0
                or metrics.get("fr4_free_root_mechanism_validation") is not False):
            raise ValueError("fixed_FR4B_controlonly_history_required")
        audit_data = read_bytes(repo / FR4B_AUDIT_PATH, cost, "gate")
        if identity(audit_data) != FR4B_AUDIT_PIN:
            raise ValueError("fixed_first_FR4B_audit_identity_differs")
        binding["first_audit"] = {"path": FR4B_AUDIT_PATH, **FR4B_AUDIT_PIN,
                                  "declared_result": FR4B_FIRST_AUDIT_DECLARATION,
                                  "hash_binding_only_no_reaudit_or_metric_recomputation": True}
    binding.update(source_commit=source_commit, gate_stage=stage, verified=True)
    return loaded, binding


def require_baseline_source_trial(trial, score, reference, snapshots, seed, name, files):
    if (trial.get("trial_id") != f"FR4_{seed}_control_{name}" or trial.get("seed") != seed
            or trial.get("kind") != "control_"+name):
        raise ValueError("unique_source_baseline_trial_required")
    for key in ("installed_xml_identity", "physical_fingerprint_before", "execution_fingerprint_before",
                "interface_fingerprint", "support", "qref2", "public_joint_ranges2"):
        if name == "pd" and key not in trial:
            raise ValueError("complete_PD_initialization_provenance_required:"+key)
        if key in trial and trial[key] is not None and trial[key] != reference[key]:
            raise ValueError("known_baseline_initialization_mismatch:"+key)
    if name == "pd":
        if (trial.get("complete") is not True or trial.get("status") != "completed"
                or trial.get("native_execution_complete") is not True
                or trial.get("stop") is not None or trial.get("failure") is not None
                or trial.get("metadata_stable") is not True
                or trial.get("planned_prefix") != 1000 or trial.get("planned_active") != 2000
                or trial.get("returned_intervals") != 3000
                or trial.get("free_root_domain_qualification_passed") is not True
                or trial.get("original_asset_unchanged_no_mount") is not True
                or trial.get("installed_xml_identity") != files["src/developmental_physics/assets/ground_body.xml"]):
            raise ValueError("full_audited_strong_PD_baseline_required")
        phases = trial.get("contact_population", {}).get("phases", {})
        if set(phases) != {"prefix", "target_A", "target_B"}:
            raise ValueError("three_PD_contact_phases_required")
        for phase in phases.values():
            positive = phase.get("classes", {}).get("left_arm", {}).get("positive_contact_endpoint_count")
            if (phase.get("qualification_passed") is not True or phase.get("planned_count") != 1000
                    or phase.get("record_count") != 1000 or phase.get("confirmed_substeps") != 1000
                    or phase.get("observed_contact_endpoints") != 1000
                    or phase.get("unknown_paid_contact_substeps") != 0
                    or type(positive) is not int or not 1 <= positive <= 1000):
                raise ValueError("full_PD_known_contact_population_required")
        effort = trial.get("actual_effort", {})
        if any(effort.get(phase, {}).get("complete") is not True
               or effort[phase].get("actual_effort_population_complete") is not True
               or effort[phase].get("unknown_actual_effort_substeps") != 0 for phase in ("prefix", "active")):
            raise ValueError("full_PD_known_actual_effort_required")
        if (score.get("available") is not True or score.get("native_execution_complete") is not True
                or score.get("free_root_domain_qualification_required") is not True
                or score.get("free_root_domain_qualification_passed") is not True
                or score.get("planned_active_count") != 2000 or score.get("observed_active_count") != 2000
                or score.get("partial_subset_ranking") is not False):
            raise ValueError("full_saved_PD_tracking_score_required")
    if score.get("available") is True:
        if (not finite_shape(score.get("axis_rmse_rad"), (2,))
                or any(not finite_shape(score.get(key), ()) for key in
                       ("joint_rmse_rad", "actual_absolute_two_axis_nm_s", "actual_squared_two_axis_nm2_s"))
                or any(value < 0 for value in score["axis_rmse_rad"])
                or any(score[key] < 0 for key in ("joint_rmse_rad", "actual_absolute_two_axis_nm_s", "actual_squared_two_axis_nm2_s"))):
            raise ValueError("finite_source_baseline_scores_required_no_rescoring")
    expected_fingerprints = {key: value["parameter_fingerprint"] for key, value in snapshots.items()}
    for key in ("model_fingerprints_before", "model_fingerprints_after_control", "model_fingerprints_after"):
        if name == "pd" and trial.get(key) != expected_fingerprints:
            raise ValueError("PD_source_frozen_model_provenance_differs")
        if key in trial and trial[key] is not None and trial[key] != expected_fingerprints:
            raise ValueError("known_baseline_model_provenance_differs")
    qref, ranges = reference["qref2"], reference["public_joint_ranges2"]
    selection = []
    for index, (lower, upper) in enumerate(ranges):
        positive, negative = upper-qref[index], qref[index]-lower
        selection.append({"joint_index": index, "direction": 1 if positive >= negative else -1,
                          "positive_room_rad": positive, "negative_room_rad": negative,
                          "rule": "larger_public_limit_distance_tie_positive"})
    targets = [[qref[i]+selection[i]["direction"]*delta for i in range(2)] for delta in (.04, .08)]
    if not all(ranges[i][0]+.03 <= target[i] <= ranges[i][1]-.03 for target in targets for i in range(2)):
        raise ValueError("fixed_public_targets_infeasible_no_retry")
    for key, value in (("direction_selection", selection), ("targets_q2", targets)):
        if name == "pd" and trial.get(key) != value:
            raise ValueError("audited_PD_fixed_task_mismatch:"+key)
        if key in trial and trial[key] is not None and trial[key] != value:
            raise ValueError("known_zero_fixed_task_mismatch:"+key)


def source_bound_baselines(saved_a, saved_b, binding_b, files):
    run_a, run_b = saved_a["run.json"], saved_b["run.json"]
    refs = {row["seed"]: row["calibration"] for row in run_a["seed_results"]}
    rows = run_b.get("seed_results", [])
    if len(rows) != 3 or {row.get("seed") for row in rows} != set(SEEDS):
        raise ValueError("all_three_source_PD_zero_seed_rows_required")
    trial_map = {trial["trial_id"]: trial for trial in run_b.get("trials", [])}
    if len(trial_map) != 12 or len(run_b.get("trials", [])) != 12:
        raise ValueError("original_FR4B_complete_trial_matrix_required")
    result = {}
    for index, row in enumerate(rows):
        seed = row["seed"]
        result[seed] = {}
        for name in ("pd", "zero"):
            trial = row.get("controls", {}).get(name)
            score = row.get("tracking_scores", {}).get(name)
            if (not isinstance(trial, dict) or not isinstance(score, dict)
                    or trial_map.get(trial.get("trial_id")) != trial):
                raise ValueError("saved_source_baseline_summary_and_matrix_binding_required")
            require_baseline_source_trial(trial, score, refs[seed], saved_a["models.json"][str(seed)], seed, name, files)
            result[seed][name] = {"trial": trial, "tracking_score": score,
                "source_origin": {"experiment_id": "FR4B", "source_commit": FR4B_SOURCE_COMMIT,
                    "raw_path": FR4B_RAW, "manifest": binding_b["manifest"],
                    "run_pin": binding_b["files"]["run.json"], "metrics_pin": binding_b["files"]["metrics.json"],
                    "first_audit": binding_b["first_audit"], "source_trial_id": trial["trial_id"],
                    "trial_key_path": f"seed_results[{index}].controls.{name}",
                    "score_key_path": f"seed_results[{index}].tracking_scores.{name}",
                    "historical_returned_intervals": trial.get("returned_intervals"),
                    "original_cost_retained_in_history": True, "new_controls": 0,
                    "no_old_trace_predictions_paid_reads_or_metric_recomputation": True}}
    return result


class JSONLShards:
    """Intact rows, bounded decoded chunks, preserved first partial shard."""
    def __init__(self, output, prefix, cost):
        self.output, self.prefix, self.cost = output, prefix, cost
        self.parts, self.stream, self.filename = [], None, None
        self.total_records = self.total_decoded_bytes = 0
        self.total_hash = hashlib.sha256()
        self.current_records = self.current_bytes = 0
        self.current_hash = hashlib.sha256()

    def write(self, row):
        data = (json.dumps(safe(row), ensure_ascii=False, allow_nan=False)+"\n").encode("utf-8")
        if len(data) > JSONL_DECODED_SHARD_BYTES:
            raise ValueError("single_JSONL_row_exceeds_frozen_decoded_shard_limit")
        if self.stream is not None and self.current_bytes+len(data) > JSONL_DECODED_SHARD_BYTES:
            self._finish()
        if self.stream is None:
            index = len(self.parts)
            self.filename = self.prefix+("" if index == 0 else f".{index:05d}")+".jsonl.gz"
            self.stream = gzip.open(self.output / self.filename, "xb")
            self.current_records = self.current_bytes = 0
            self.current_hash = hashlib.sha256()
        self.cost[self.prefix+"_write_attempts"] += 1
        self.stream.write(data)
        self.stream.flush()
        self.cost[self.prefix+"_write_returns"] += 1
        self.current_bytes += len(data)
        self.current_records += 1
        self.current_hash.update(data)
        self.total_decoded_bytes += len(data)
        self.total_records += 1
        self.total_hash.update(data)
        self.cost[self.prefix+"_serialized_bytes"] += len(data)

    def _finish(self):
        if self.stream is None:
            return
        self.stream.close()
        self.stream = None
        data = read_bytes(self.output / self.filename, self.cost, "output_manifest")
        if len(data) >= MAX_FILE_BYTES:
            raise ValueError("stored_shard_exceeds_frozen_file_limit")
        self.parts.append({"path": self.filename, "records": self.current_records,
                           "stored": identity(data),
                           "decoded": {"bytes": self.current_bytes, "sha256": self.current_hash.hexdigest()}})

    def close(self):
        self._finish()
        return {"format": "ordered_intact_JSONL_gzip_shards", "parts": self.parts,
                "records": self.total_records,
                "decoded": {"bytes": self.total_decoded_bytes, "sha256": self.total_hash.hexdigest()},
                "decoded_shard_limit": JSONL_DECODED_SHARD_BYTES, "stored_file_limit_exclusive": MAX_FILE_BYTES}


def main_run(args):
    repo, output = Path(args.repo).resolve(), Path(args.output).resolve()
    if output == repo or repo.is_relative_to(output):
        raise ValueError("output_cannot_contain_repository")
    output.mkdir(parents=True, exist_ok=False)
    wall, cpu = time.perf_counter(), time.process_time()
    cost = Counter({key: 0 for key in (
        "control_call_attempts", "control_call_returns", "control_call_exceptions", "confirmed_physics_substeps",
        "captured_substep_endpoint_forward_returns", "environment_constructor_attempts", "environment_constructor_returns",
        "reset_attempts", "reset_returns", "RLS_vector_update_attempts", "RLS_vector_update_returns",
        "RLS_vector_update_exceptions", "RLS_vector_update_commits", "RLS_scalar_update_commits",
        "MPC_decision_attempts", "MPC_decision_returns", "MPC_decision_exceptions", "teacher_calls",
        "batch_fit_calls", "task_policy_updates", "GPU_training_seconds")})
    files, source_bytes, bindings, history = {}, {}, {}, {}
    result = {"trace": [], "predictions": [], "trials": [], "seed_results": [], "models": {},
              "reused_baseline_trials": [],
              "metrics": {"complete_population": False, **{key: False for key in GATE_FLAGS}, **FLAGS}}
    verified, status, collector_failure = False, "failed", None
    paid_journal, stream_bindings = None, {}
    execution_phase = "source_validation"
    runtime = {"python": sys.version, "python_version": platform.python_version(), "platform": platform.platform()}
    try:
        verify_sources(repo, args.source_commit, cost, files, source_bytes)
        verified = True
        runtime.update(numpy=importlib.metadata.version("numpy"), mujoco=importlib.metadata.version("mujoco"))
        execution_phase = "FR4A_gate_validation"
        saved_a, bindings["FR4A"] = read_fixed_gate(repo, cost, files, runtime, "FR4A")
        execution_phase = "FR4B_baseline_gate_validation"
        saved_b, bindings["FR4B"] = read_fixed_gate(repo, cost, files, runtime, "FR4B")
        execution_phase = "source_bound_baseline_validation"
        baselines = source_bound_baselines(saved_a, saved_b, bindings["FR4B"], files)
        history = {stage: {"source_commit": loaded["run.json"]["source"]["commit"],
                           "source_cost": loaded["run.json"]["cost"], "not_added_to_new_cost": True}
                   for stage, loaded in (("FR4A", saved_a), ("FR4B", saved_b))}
        execution_phase = "production_import"
        sys.path.insert(0, str(repo / "src"))
        from developmental_physics import equilibrium_feedforward_development as production
        if Path(production.__file__).resolve() != (repo / MODULE_PATH).resolve():
            raise ValueError("exact_EF1B_production_module_required")
        if production.FLAGS != FLAGS or list(production.SEEDS) != SEEDS:
            raise ValueError("EF1B_seed_and_scientific_boundary_contract_differs")
        result = production.new_result(args.stage)
        result["cost"].update(cost)
        cost = result["cost"]
        paid_journal = JSONLShards(output, "paid_intervals", cost)
        result["paid_writer"] = paid_journal.write
        execution_phase = "production_controlonly"
        production.run_control(result, saved_a["models.json"], saved_a["run.json"]["seed_results"], baselines)
        failures = [trial.get("failure") for trial in result["trials"] if trial.get("failure")]
        if failures:
            collector_failure = {"type": "CollectedTrialFailure", "trial_failures": failures}
            status = "failed"
        elif len(result["trials"]) == 6 and all(trial.get("complete") is True for trial in result["trials"]):
            status = "completed"
        else:
            status = "stopped"
    except BaseException as exc:
        collector_failure = {"type": type(exc).__name__, "message": str(exc),
                             "phase": execution_phase, "traceback": traceback.format_exc()}
        for key in ("equilibrium_accounting", "equilibrium_initialization_accounting", "pair_planning_accounting", "pair_prediction_accounting"):
            if hasattr(exc, key):
                collector_failure[key] = safe(getattr(exc, key))
        status = "failed"
    finally:
        if paid_journal is not None:
            try:
                stream_bindings["paid_intervals"] = paid_journal.close()
            except BaseException as exc:
                collector_failure = collector_failure or {
                    "type": type(exc).__name__, "message": str(exc), "phase": "paid_journal_close"}
                status = "failed"
        normalize_metrics_boundary(result["metrics"], failed=collector_failure is not None)
        if collector_failure is not None:
            result["metrics"].update(execution_failed=True,
                collector_failed=execution_phase == "production_controlonly", failure_phase=execution_phase,
                **{key: False for key in GATE_FLAGS})

    for name, rows in (("trace", result["trace"]), ("predictions", result["predictions"])):
        writer = JSONLShards(output, name, cost)
        try:
            for row in rows:
                writer.write(row)
        except BaseException as exc:
            collector_failure = collector_failure or {
                "type": type(exc).__name__, "message": str(exc), "phase": name+"_serialization",
                "records_saved_before_failure": writer.total_records,
                "records_planned_to_serialize": len(rows), "traceback": traceback.format_exc()}
            status = "failed"
        finally:
            try:
                stream_bindings[name] = writer.close()
            except BaseException as exc:
                collector_failure = collector_failure or {
                    "type": type(exc).__name__, "message": str(exc), "phase": name+"_serialization_close"}
                status = "failed"
    normalize_metrics_boundary(result["metrics"], failed=collector_failure is not None)
    cost["wall_seconds"], cost["cpu_seconds"] = time.perf_counter()-wall, time.process_time()-cpu
    budgets = {"new_control_calls": 18000, "new_physics_substeps": 18000,
               "new_RLS_vector_commits": 0, "new_RLS_scalar_commits": 0,
               "new_fit_calls": 0, "MPC_decisions": 1200,
               "single_forecast_pair_forwards": 180000, "single_forecast_scalar_forwards": 360000,
               "root_solve_attempts": 12, "root_branch_SVDs": 192,
               "root_model_pair_forwards_maximum": 192, "root_model_scalar_forwards_maximum": 384,
               "conditional_prediction_records": 11772,
               "conditional_prediction_pairs": 526560, "conditional_prediction_scalars": 1053120,
               "reused_PD_zero_new_controls": 0, "reused_PD_zero_new_predictions": 0}
    run = {"experiment_id": "EF1B", "stage": args.stage, "status": status, "seeds": SEEDS,
        "source": {"commit": args.source_commit, "files": files, "clean_committed_bytes_verified": verified,
                   "controller_candidate_definition": {"one_current_target_model_equilibrium_hold": True,
                       "branches": 16, "forecast_trajectories_per_decision": 1,
                       "forecast_horizon_microsteps": 150, "optimization_cost": None,
                       "actor_law": "clip(64*(target-current_q)-4*current_v+hold_request,-.5,.5)",
                       "finite_no_root": "zero_hold_still_forecast_PD", "forecast_veto": "literal_zero_ten_microsteps"}},
        "runtime": runtime, "source_gate_bindings": bindings, "source_history_costs": history,
        "planned_upper_bounds": budgets, "cost": dict(cost),
        "seed_results": summary_only(result["seed_results"]),
        "unattempted_seeds": [seed for seed in SEEDS if seed not in {row["seed"] for row in result["seed_results"]}],
        "trials": summary_only(result["trials"]),
        "reused_baseline_trials": summary_only(result["reused_baseline_trials"]), "failure": collector_failure,
        "six_new_trials_only": True, "reused_PD_zero_preserve_original_trial_ids": True,
        "old_metric_recomputation": False, "old_trace_predictions_paid_reads": False,
        "no_reset_retry_or_mount_search": True, "new_learning_updates": 0,
        "constructor_internal_model_builds": "unmeasured_unknown_not_zero",
        "constructor_and_reset_internal_forward_attempts": "unmeasured_unknown_not_zero",
        "unconfirmed_integrator_and_forward_attempts": "unknown_if_collector_exception",
        "inherited_execution_fingerprint_asset_IO": "unknown_not_zero",
        "unmeasured_filesystem_IO": "unknown_not_zero",
        "timing_excludes": "final_JSON_encoding_source_zip_and_output_writes",
        "JSONL_streams": stream_bindings, **FLAGS}
    payloads = {"run.json": encoded(run), "metrics.json": encoded(result["metrics"]),
                "models.json": encoded(result["models"])}
    if source_bytes:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, data in sorted(source_bytes.items()):
                info = zipfile.ZipInfo(name)
                info.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(info, data)
        payloads["source.zip"] = buffer.getvalue()
    if collector_failure is not None:
        payloads["failure.json"] = encoded(collector_failure)
    for trial in result["trials"]:
        if "installed_xml_utf8" in trial:
            payloads["installed/"+trial["trial_id"]+".xml"] = trial["installed_xml_utf8"].encode("utf-8")
    output_files = {part["path"]: part["stored"] for stream in stream_bindings.values() for part in stream["parts"]}
    for name, data in payloads.items():
        if len(data) >= MAX_FILE_BYTES:
            raise ValueError("output_payload_exceeds_frozen_file_limit:"+name)
        destination = output / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("xb") as stream:
            stream.write(data)
        output_files[name] = identity(data)
    manifest = encoded({"schema_version": 2, "experiment_id": "EF1B", "stage": args.stage,
                        "status": status, "files": output_files, "streams": stream_bindings, **FLAGS})
    if len(manifest) >= MAX_FILE_BYTES:
        raise ValueError("manifest_exceeds_frozen_file_limit")
    with (output / "manifest.json").open("xb") as stream:
        stream.write(manifest)
    print(json.dumps(safe({"experiment_id": "EF1B", "stage": args.stage, "status": status,
        "output": str(output), "cost": dict(cost), "failure": collector_failure,
        **{key: result["metrics"].get(key, False) for key in GATE_FLAGS}, **FLAGS}),
        ensure_ascii=False, allow_nan=False))
    return 1 if collector_failure is not None else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("controlonly",), required=True)
    parser.add_argument("--repo", default=".")
    parser.add_argument("--output", required=True)
    parser.add_argument("--source-commit", required=True)
    return main_run(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
