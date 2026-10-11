"""First FR4A prediction / FR4B control entry, blocked until the protocol is pinned.

Only standard-library source and new-gate validation precedes production imports.
This candidate requires root publication and a final protocol pin. No import-time experiment,
retry, previous Z snapshot loading, gain search or fixture execution is provided.
The parent launcher must retain the first process stdout, stderr and exit status.
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


SOURCE_PATH = "scripts/develop_pd_anchor_pair.py"
MODULE_PATH = "src/developmental_physics/pd_anchor_pair_development.py"
PROTOCOL_PATH = "docs/PD_ANCHOR_PAIR_LEARNING_PROTOCOL.md"
ENGINEERING_PROTOCOL_PATH = "docs/FREE_ROOT_FAST_FEEDBACK_ENGINEERING_PROTOCOL.md"
PROTOCOL_PIN = {"bytes": 14616, "sha256": "ae9b8ea0515d3ff71ac8c636e08542fa7b19725c5746613acd5d619284978b1f"}
ENGINEERING_PROTOCOL_PIN = {
    "bytes": 9189,
    "sha256": "5bb40312c37418b639f11ea32da007c3e5835a74ace19defe9c235e29bfe2c86",
}
FR0_RAW = "results/cpu_validation/2026-10-12_free_root_fast_feedback_engineering/raw"
FR0_SOURCE_COMMIT = "e5466d326773c9565aa98f0e7063314a32eba5d4"
FR4A_RAW = "results/cpu_validation/2026-10-12_pd_anchor_pair_prediction/raw"
FR0_REQUIRED_DEPENDENCIES = (
    "scripts/validate_free_root_fast_feedback_engineering.py",
    "src/developmental_physics/free_root_fast_feedback_environment.py",
    ENGINEERING_PROTOCOL_PATH,
    "src/developmental_physics/environment.py",
    "src/developmental_physics/assets/ground_body.xml",
    "src/developmental_physics/__init__.py",
    "pyproject.toml",
)
DEPENDENCY_PATHS = (
    SOURCE_PATH, MODULE_PATH, PROTOCOL_PATH,
    *FR0_REQUIRED_DEPENDENCIES,
    "src/developmental_physics/fast_feedback_pair_model.py",
    "src/developmental_physics/guard_coupled_pair_model.py",
    "src/developmental_physics/guard_pair_model.py",
    "src/developmental_physics/local_pair_model.py",
    "src/developmental_physics/local_model.py",
    "src/developmental_physics/fast_feedback_pair_mpc.py",
    "src/developmental_physics/batched_fast_feedback_pair_mpc.py",
    "src/developmental_physics/pd_anchor_pair_mpc.py",
    "src/developmental_physics/fast_feedback_pair_development.py",
)
SEEDS = [8101, 8102, 8103]
FLAGS = {
    "scientific_adoption": False,
    "old_free_root_C4_validation": False,
    "c4_scientific_validation": False,
    "c5_scientific_dependency_released": False,
    "c4_contact_scientific_validation": False,
}
GATE_FLAGS = (
    "fr4a_prediction_gate_passed", "fr4b_model_contribution_gate_passed",
    "fr4b_pd_reference_gate_passed", "fr4_free_root_mechanism_validation",
)


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
        raise ValueError("final_published_FR_learning_protocol_pin_required")
    if (not isinstance(PROTOCOL_PIN, dict) or set(PROTOCOL_PIN) != {"bytes", "sha256"}
            or type(PROTOCOL_PIN["bytes"]) is not int or PROTOCOL_PIN["bytes"] <= 0
            or not isinstance(PROTOCOL_PIN["sha256"], str) or len(PROTOCOL_PIN["sha256"]) != 64
            or any(c not in "0123456789abcdef" for c in PROTOCOL_PIN["sha256"])):
        raise ValueError("exact_published_protocol_identity_required")
    if Path(__file__).resolve() != (repo / SOURCE_PATH).resolve():
        raise ValueError("canonical_frozen_FR_learning_runner_required")
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
        raise ValueError("clean_exact_FR_learning_HEAD_required")
    for name in DEPENDENCY_PATHS:
        data = read_bytes(repo / name, cost, "source")
        files[name] = identity(data)
        source_bytes[name] = data
        expected = (PROTOCOL_PIN if name == PROTOCOL_PATH else
                    ENGINEERING_PROTOCOL_PIN if name == ENGINEERING_PROTOCOL_PATH else None)
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


def _require_fr0(loaded, manifest, files):
    run, metrics = loaded["run.json"], loaded["metrics.json"]
    source, trial, cost = run.get("source", {}), run.get("trial", {}), run.get("cost", {})
    if (run.get("experiment_id") != "FR0" or manifest.get("experiment_id") != "FR0"
            or run.get("stage") != "free_root_fast_feedback_engineering"
            or manifest.get("stage") != run.get("stage")
            or source.get("commit") != FR0_SOURCE_COMMIT
            or set(source.get("files", {})) != set(FR0_REQUIRED_DEPENDENCIES)
            or any(source["files"][name] != files[name] for name in FR0_REQUIRED_DEPENDENCIES)):
        raise ValueError("exact_first_FR0_source_subset_required")
    if (run.get("seed") != 7800 or run.get("pose") != "supine"
            or trial.get("complete") is not True or trial.get("stop") is not None
            or trial.get("failure") is not None or metrics.get("complete_population") is not True
            or metrics.get("metadata_stable") is not True
            or metrics.get("engineering_qualification_passed") is not True
            or cost.get("control_call_returns") != 3000 or cost.get("confirmed_physics_substeps") != 3000
            or cost.get("captured_native_endpoints") != 3000
            or cost.get("captured_complete_endpoints") != 3000
            or cost.get("control_call_exceptions") != 0):
        raise ValueError("first_complete_FR0_engineering_qualification_required")
    if any(cost.get(key) != 0 for key in (
        "model_calls", "fit_calls", "RLS_updates", "MPC_decisions", "teacher_calls",
        "task_policy_updates", "GPU_training_seconds",
    )):
        raise ValueError("FR0_must_be_zero_learning_engineering")
    windows = metrics.get("windows", [])
    if (len(windows) != 2 or {row.get("target") for row in windows} != {"A", "B"}
            or any(row.get("available") is not True or row.get("planned_count") != 200
                   or row.get("observed_count") != 200 or row.get("full_trial_required") is not True
                   or row.get("threshold_rad") != .01 or row.get("passed_axis") != [True, True]
                   for row in windows)):
        raise ValueError("both_original_complete_FR0_tracking_windows_required")
    expected_phases = {"prefix", "target_A", "target_B"}
    phases = metrics.get("phase_effort_and_contacts", {})
    checks = metrics.get("left_arm_contact_checks", {})
    if (set(phases) != expected_phases or set(checks) != expected_phases
            or any(checks[name] is not True for name in expected_phases)):
        raise ValueError("all_three_FR0_contact_phases_required")
    for name in expected_phases:
        phase = phases[name]
        count = phase.get("classes", {}).get("left_arm", {}).get("positive_contact_endpoint_count")
        if (phase.get("confirmed_substeps") != 1000 or phase.get("observed_contact_endpoints") != 1000
                or phase.get("observed_native_endpoints") != 1000
                or phase.get("missing_contact_endpoint_substeps") != 0
                or phase.get("actual_effort_complete") is not True
                or type(count) is not int or count < 1):
            raise ValueError("complete_FR0_left_arm_contact_required:" + name)
    support = trial.get("metadata_before", {}).get("support", {})
    if (support.get("root") != "original_asset_freejoint" or support.get("mount") is not None
            or support.get("external_support") is not False or support.get("initial_pose") != "supine"):
        raise ValueError("original_free_root_no_mount_FR0_required")


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
    if any(metrics.get(key) is not False for key in GATE_FLAGS if key != "fr4a_prediction_gate_passed"):
        raise ValueError("FR4A_prediction_cannot_predeclare_control_mechanism_success")


def read_gate(repo, relative, cost, files, runtime, *, stage):
    """Read only first FR0 evidence, or new FR4A snapshots; never Z results."""
    fixed = FR0_RAW if stage == "FR0" else FR4A_RAW if stage == "FR4A" else None
    if fixed is None or relative != fixed:
        raise ValueError("fixed_new_FR_gate_path_required")
    raw = (repo / relative).resolve()
    if not raw.is_relative_to(repo.resolve()):
        raise ValueError("fixed_gate_path_outside_repository")
    data = read_bytes(raw / "manifest.json", cost, "gate")
    manifest = json.loads(data)
    cost["gate_json_parses"] += 1
    binding = {"relative_raw_path": relative, "manifest": identity(data), "files": {}}
    loaded = {}
    for name in ("run.json", "metrics.json", *(("models.json",) if stage == "FR4A" else ())):
        data = read_bytes(raw / name, cost, "gate")
        pin = identity(data)
        binding["files"][name] = pin
        if manifest.get("files", {}).get(name) != pin:
            raise ValueError("new_gate_payload_hash_differs:" + stage + ":" + name)
        loaded[name] = json.loads(data)
        cost["gate_json_parses"] += 1
    run, metrics = loaded["run.json"], loaded["metrics.json"]
    source = run.get("source", {})
    if (manifest.get("status") != "completed" or run.get("status") != "completed"
            or source.get("clean_committed_bytes_verified") is not True
            or not isinstance(source.get("commit"), str) or len(source["commit"]) != 40):
        raise ValueError("completed_clean_new_gate_required:" + stage)
    if any(run.get("runtime", {}).get(key) != runtime[key] for key in ("python", "numpy", "mujoco")):
        raise ValueError("new_gate_runtime_differs:" + stage)
    _all_old_flags_false(run, metrics, stage)
    if stage == "FR0":
        _require_fr0(loaded, manifest, files)
    else:
        if run.get("failure") is not None:
            raise ValueError("new_FR4A_failure_cannot_release_control")
        _require_fr4a(loaded, manifest, files)
    binding.update(source_commit=source["commit"], gate_stage=stage, verified=True)
    return loaded, binding


def summary_only(value):
    if isinstance(value, dict):
        return {key: summary_only(item) for key, item in value.items()
                if key not in ("records", "installed_xml_utf8")}
    if isinstance(value, (list, tuple)):
        return [summary_only(item) for item in value]
    return value


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
        "batch_fit_calls", "task_policy_updates", "GPU_training_seconds",
    )})
    files, source_bytes, bindings = {}, {}, {}
    result = {"trace": [], "predictions": [], "trials": [], "seed_results": [], "models": {},
              "metrics": {"complete_population": False, **{key: False for key in GATE_FLAGS}, **FLAGS}}
    verified, status, collector_failure = False, "failed", None
    paid_journal = None
    execution_phase = "source_validation"
    runtime = {"python": sys.version, "python_version": platform.python_version(), "platform": platform.platform()}
    try:
        verify_sources(repo, args.source_commit, cost, files, source_bytes)
        verified = True
        runtime.update(numpy=importlib.metadata.version("numpy"), mujoco=importlib.metadata.version("mujoco"))
        execution_phase = "FR0_gate_validation"
        _, bindings["FR0"] = read_gate(repo, FR0_RAW, cost, files, runtime, stage="FR0")
        saved_fr4a = None
        if args.stage == "control":
            execution_phase = "FR4A_gate_validation"
            saved_fr4a, bindings["FR4A"] = read_gate(repo, FR4A_RAW, cost, files, runtime, stage="FR4A")
        execution_phase = "production_import"
        sys.path.insert(0, str(repo / "src"))
        from developmental_physics import pd_anchor_pair_development as production
        if Path(production.__file__).resolve() != (repo / MODULE_PATH).resolve():
            raise ValueError("exact_new_FR_production_module_required")
        if production.FLAGS != FLAGS or list(production.SEEDS) != SEEDS:
            raise ValueError("new_FR_seed_and_scientific_boundary_contract_differs")
        result = production.new_result(args.stage)
        result["cost"].update(cost)
        cost = result["cost"]
        paid_journal = gzip.open(output / "paid_intervals.jsonl.gz", "xb")

        def write_paid(row):
            # Preserve paid native data before study helpers or RLS submission.
            cost["paid_interval_write_attempts"] += 1
            data = (json.dumps(safe(row), ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
            paid_journal.write(data)
            paid_journal.flush()
            cost["paid_interval_write_returns"] += 1
            cost["paid_interval_serialized_bytes"] += len(data)

        result["paid_writer"] = write_paid
        execution_phase = "production_" + args.stage
        if args.stage == "prediction":
            production.run_prediction(result)
        else:
            production.run_control(result, saved_fr4a["models.json"], saved_fr4a["run.json"]["seed_results"])
        failures = [trial.get("failure") for trial in result["trials"] if trial.get("failure")]
        if failures:
            collector_failure = {"type": "CollectedTrialFailure", "trial_failures": failures}
            status = "failed"
        elif (len(result["trials"]) == (6 if args.stage == "prediction" else 12)
              and all(trial.get("complete") is True for trial in result["trials"])):
            status = "completed"
        else:
            status = "stopped"
    except BaseException as exc:
        collector_failure = {"type": type(exc).__name__, "message": str(exc),
                             "phase": execution_phase, "traceback": traceback.format_exc()}
        status = "failed"
    finally:
        if paid_journal is not None:
            try:
                paid_journal.close()
            except BaseException as exc:
                collector_failure = collector_failure or {
                    "type": type(exc).__name__, "message": str(exc), "phase": "paid_journal_close"}
                status = "failed"
        normalize_metrics_boundary(result["metrics"], failed=collector_failure is not None)
        if collector_failure is not None:
            result["metrics"].update(
                execution_failed=True,
                collector_failed=execution_phase in ("production_prediction", "production_control"),
                failure_phase=execution_phase, **{key: False for key in GATE_FLAGS},
            )

    journal_pin = None
    if (output / "paid_intervals.jsonl.gz").exists():
        journal_data = read_bytes(output / "paid_intervals.jsonl.gz", cost, "output_manifest")
        journal_pin = identity(journal_data)
    cost["wall_seconds"], cost["cpu_seconds"] = time.perf_counter() - wall, time.process_time() - cpu
    budgets = ({"control_calls": 21000, "physics_substeps": 21000, "RLS_vector_commits": 12000,
                "RLS_scalar_commits": 24000, "independent_prediction_pairs": 124680} if args.stage == "prediction" else
               {"control_calls": 36000, "physics_substeps": 36000, "MPC_decisions": 1200,
                "planning_prediction_pairs": 14580000, "conditional_prediction_pairs": 526560})
    experiment = "FR4A" if args.stage == "prediction" else "FR4B"
    run = {
        "experiment_id": experiment, "stage": args.stage, "status": status, "seeds": SEEDS,
        "source": {"commit": args.source_commit, "files": files, "clean_committed_bytes_verified": verified,
                   "controller_candidate_definition": {
                       "nominal_axis_grid_nm": [-.5, -.375, -.25, -.125, 0., .125, .25, .375, .5],
                       "anchor": "current_clipped_public_PD_request_per_axis",
                       "replacement": "first_original_slot_minimizing_absolute_distance_to_anchor",
                       "axis_slot_count": 9, "pair_candidate_count": 81,
                       "enumeration": "original_slot_order_axis0_outer_axis1_inner",
                       "pure_PD_first_request_candidate_included": True,
                       "dynamic_held_residual": "first_request_candidate_minus_current_PD",
                       "controller_spec_policy": "static_not_mutated_by_select",
                       "nominal_grid_coverage_change": "one_nearest_nominal_slot_replaced_per_axis",
                   }},
        "runtime": runtime, "source_gate_bindings": bindings, "planned_upper_bounds": budgets,
        "cost": dict(cost), "seed_results": summary_only(result["seed_results"]),
        "unattempted_seeds": [seed for seed in SEEDS if seed not in {row["seed"] for row in result["seed_results"]}],
        "trials": summary_only(result["trials"]), "failure": collector_failure,
        "no_reset_retry_or_mount_search": True, "learning_updates_only_calibration": True,
        "constructor_internal_model_builds": "unmeasured_unknown_not_zero",
        "constructor_and_reset_internal_forward_attempts": "unmeasured_unknown_not_zero",
        "unconfirmed_integrator_and_forward_attempts": "unknown_if_collector_exception",
        "inherited_execution_fingerprint_asset_IO": "unknown_not_zero",
        "unmeasured_filesystem_IO": "unknown_not_zero",
        "timing_excludes": "final_serialization_compression_and_output_writes",
        **FLAGS,
    }
    payloads = {
        "run.json": encoded(run), "metrics.json": encoded(result["metrics"]),
        "models.json": encoded(result["models"]),
        "trace.jsonl.gz": gzip.compress(b"".join(
            (json.dumps(safe(row), ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
            for row in result["trace"]), mtime=0),
        "predictions.jsonl.gz": gzip.compress(b"".join(
            (json.dumps(safe(row), ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
            for row in result["predictions"]), mtime=0),
    }
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
            payloads["installed/" + trial["trial_id"] + ".xml"] = trial["installed_xml_utf8"].encode("utf-8")
    output_files = {}
    if journal_pin is not None:
        output_files["paid_intervals.jsonl.gz"] = journal_pin
    for name, data in payloads.items():
        destination = output / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("xb") as stream:
            stream.write(data)
        output_files[name] = identity(data)
    with (output / "manifest.json").open("xb") as stream:
        stream.write(encoded({"schema_version": 1, "experiment_id": experiment,
                              "stage": args.stage, "status": status, "files": output_files, **FLAGS}))
    print(json.dumps(safe({
        "experiment_id": experiment, "stage": args.stage, "status": status,
        "output": str(output), "cost": dict(cost), "failure": collector_failure,
        **{key: result["metrics"].get(key, False) for key in GATE_FLAGS}, **FLAGS,
    }), ensure_ascii=False, allow_nan=False))
    return 1 if collector_failure is not None else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("prediction", "control"), required=True)
    parser.add_argument("--repo", default=".")
    parser.add_argument("--output", required=True)
    parser.add_argument("--source-commit", required=True)
    return main_run(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
