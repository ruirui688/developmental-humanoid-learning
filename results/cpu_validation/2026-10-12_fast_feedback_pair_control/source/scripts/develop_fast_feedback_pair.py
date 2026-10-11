"""First Z1 prediction or Z2 control run, gated by pinned new support evidence.

Only standard-library source/gate verification precedes production imports.
No retry, fixture, fitting or physics runs at import time.
"""
from __future__ import annotations

import argparse
from collections import Counter
import gzip
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import subprocess
import sys
import time
import traceback
import zipfile
import io

SOURCE_PATH = "scripts/develop_fast_feedback_pair.py"
MODULE_PATH = "src/developmental_physics/fast_feedback_pair_development.py"
Z0_RAW = "results/cpu_validation/2026-10-12_fast_feedback_engineering/raw"
Z1_RAW = "results/cpu_validation/2026-10-12_fast_feedback_pair_prediction/raw"
PROTOCOL_PATH = "docs/FAST_FEEDBACK_LEARNING_PROTOCOL.md"
ENGINEERING_PROTOCOL_PATH = "docs/FAST_FEEDBACK_ENGINEERING_PROTOCOL.md"
PROTOCOL_PIN = {"bytes": 12655, "sha256": "2370f7b76f627936e18bd609d67f785e6a090bde3c7dea0097deda237b42305b"}
ENGINEERING_PROTOCOL_PIN = {"bytes": 9430, "sha256": "5b71ac014786ebbc464becc8579c36df906360e256d47232612ddc141b8bcee4"}
DEPENDENCY_PATHS = (
    SOURCE_PATH, MODULE_PATH, PROTOCOL_PATH, ENGINEERING_PROTOCOL_PATH,
    "src/developmental_physics/fast_feedback_pair_model.py",
    "src/developmental_physics/fast_feedback_environment.py",
    "scripts/validate_fast_feedback_engineering.py", "docs/SUSPENDED_PAIR_DOMAIN_DESIGN.md",
    "src/developmental_physics/suspended_environment.py",
    "scripts/validate_supported_pair_engineering.py", "docs/SUPPORTED_PAIR_DOMAIN_DESIGN.md",
    "src/developmental_physics/supported_environment.py", "src/developmental_physics/environment.py",
    "src/developmental_physics/assets/ground_body.xml", "src/developmental_physics/__init__.py",
    "src/developmental_physics/guard_coupled_pair_model.py", "src/developmental_physics/guard_pair_model.py",
    "src/developmental_physics/local_pair_model.py", "src/developmental_physics/local_model.py",
    "src/developmental_physics/fast_feedback_pair_mpc.py", "pyproject.toml",
)
SEEDS = [7701, 7702, 7703]
FLAGS = {"scientific_adoption": False, "old_free_root_C4_validation": False,
         "c4_scientific_validation": False, "c5_scientific_dependency_released": False,
         "c4_contact_scientific_validation": False}


def identity(data):
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+"\n").encode("utf-8")


def read_bytes(path, cost, scope):
    cost[scope+"_file_read_attempts"] += 1
    data = path.read_bytes()
    cost[scope+"_file_read_returns"] += 1
    cost[scope+"_read_and_hash_bytes"] += len(data)
    return data


def verify_sources(repo, commit, cost, files, source_bytes):
    if Path(__file__).resolve() != (repo/SOURCE_PATH).resolve():
        raise ValueError("canonical_frozen_Z_learning_runner_required")
    if not commit or len(commit) != 40 or any(c not in "0123456789abcdef" for c in commit):
        raise ValueError("exact_source_commit_required")
    def git(*args):
        cost["git_query_attempts"] += 1
        result = subprocess.run(["git", *args], cwd=repo, capture_output=True, check=False)
        cost["git_return_bytes"] += len(result.stdout)+len(result.stderr)
        if result.returncode:
            raise ValueError("source_git_query_failed")
        return result.stdout
    if git("rev-parse", "HEAD").decode().strip() != commit or git("status", "--porcelain", "--untracked-files=all").strip():
        raise ValueError("clean_exact_Z_learning_HEAD_required")
    for name in DEPENDENCY_PATHS:
        data = read_bytes(repo/name, cost, "source")
        files[name] = identity(data)
        expected = PROTOCOL_PIN if name == PROTOCOL_PATH else ENGINEERING_PROTOCOL_PIN if name == ENGINEERING_PROTOCOL_PATH else None
        if expected is not None and files[name] != expected:
            raise ValueError("fixed_Z_protocol_bytes_differ:"+name)
        source_bytes[name] = data
        if git("show", f"{commit}:{name}") != data:
            raise ValueError("committed_dependency_bytes_differ:"+name)


def read_gate(repo, relative, cost, files, runtime, *, stage):
    """Only new gate manifest/run/metrics (and Z1 snapshots for Z2), once each."""
    raw = (repo/relative).resolve()
    if not raw.is_relative_to(repo.resolve()):
        raise ValueError("fixed_new_gate_path_outside_repository")
    manifest_bytes = read_bytes(raw/"manifest.json", cost, "gate")
    manifest = json.loads(manifest_bytes)
    cost["gate_json_parses"] += 1
    binding = {"relative_raw_path": relative, "manifest": identity(manifest_bytes), "files": {}}
    loaded = {}
    for name in ("run.json", "metrics.json", *(("models.json",) if stage == "Z1" else ())):
        data = read_bytes(raw/name, cost, "gate")
        pin = identity(data)
        binding["files"][name] = pin
        if manifest.get("files", {}).get(name) != pin:
            raise ValueError("new_gate_payload_hash_differs:"+stage+":"+name)
        loaded[name] = json.loads(data)
        cost["gate_json_parses"] += 1
    run, metrics = loaded["run.json"], loaded["metrics.json"]
    source = run.get("source", {})
    if (manifest.get("status") != "completed" or run.get("status") != "completed" or run.get("failure") is not None
            or source.get("clean_committed_bytes_verified") is not True
            or len(source.get("commit", "")) != 40):
        raise ValueError("completed_clean_new_gate_required:"+stage)
    for name, pin in source.get("files", {}).items():
        if name not in files or files[name] != pin:
            raise ValueError("new_gate_frozen_source_combination_differs:"+stage+":"+name)
    if not source.get("files"):
        raise ValueError("new_gate_source_pins_missing:"+stage)
    if any(run.get("runtime", {}).get(key) != runtime[key] for key in ("python", "numpy", "mujoco")):
        raise ValueError("new_gate_runtime_differs:"+stage)
    if any(run.get(key) is not False or metrics.get(key) is not False for key in FLAGS):
        raise ValueError("old_C4_or_privileged_adoption_flag_must_remain_false:"+stage)
    if stage == "Z0":
        required = {"scripts/validate_fast_feedback_engineering.py", ENGINEERING_PROTOCOL_PATH,
                    "src/developmental_physics/fast_feedback_environment.py",
                    "src/developmental_physics/suspended_environment.py", "src/developmental_physics/supported_environment.py",
                    "src/developmental_physics/environment.py", "src/developmental_physics/assets/ground_body.xml"}
        if not required.issubset(source["files"]):
            raise ValueError("complete_Z0_source_dependency_pins_required")
        if (run.get("seed") != 7600 or run.get("self_check") is not False
                or run.get("engineering_qualification_passed") is not True
                or metrics.get("engineering_qualification_passed") is not True
                or metrics.get("full_1000_prefix_2000_active") is not True
                or run.get("cost", {}).get("control_call_returns") != 3000
                or run.get("cost", {}).get("confirmed_physics_substeps") != 3000):
            raise ValueError("first_Z0_engineering_qualification_not_passed")
    else:
        if manifest.get("stage") != "prediction":
            raise ValueError("exact_Z1_prediction_manifest_required")
        if set(source["files"]) != set(files) or any(source["files"][name] != files[name] for name in files):
            raise ValueError("all_Z1_frozen_dependencies_required_for_Z2")
        if (run.get("stage") != "prediction" or run.get("seeds") != SEEDS
                or metrics.get("z1_prediction_gate_passed") is not True
                or metrics.get("complete_population") is not True
                or run.get("cost", {}).get("RLS_vector_update_commits") != 12000
                or run.get("cost", {}).get("RLS_scalar_update_commits") != 24000
                or set(loaded["models.json"]) != {str(seed) for seed in SEEDS}):
            raise ValueError("complete_Z1_prediction_gate_and_three_snapshots_required")
        seed_results = run.get("seed_results", [])
        if (len(seed_results) != 3 or {row.get("seed") for row in seed_results} != set(SEEDS)
                or any(row.get("calibration", {}).get("complete") is not True
                       or row.get("prediction", {}).get("complete") is not True for row in seed_results)):
            raise ValueError("complete_Z1_calibration_and_prediction_installations_required")
        for snapshots in loaded["models.json"].values():
            if set(snapshots) != {"cold", "learned"}:
                raise ValueError("both_exact_Z1_frozen_models_required")
            if (snapshots["cold"].get("vector_update_count") != 0
                    or snapshots["learned"].get("vector_update_count") != 4000
                    or any(snapshot.get("trainable") is not False for snapshot in snapshots.values())):
                raise ValueError("exact_zero_and_4000_atomic_Z1_frozen_counts_required")
    binding.update(source_commit=source["commit"], gate_stage=stage, verified=True)
    return loaded, binding


def summary_only(value):
    if isinstance(value, dict):
        return {key: summary_only(item) for key, item in value.items() if key not in ("records", "installed_xml_utf8")}
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
        "batch_fit_calls", "task_policy_updates", "GPU_training_seconds")})
    files, source_bytes, bindings = {}, {}, {}
    result = {"trace": [], "predictions": [], "trials": [], "seed_results": [], "models": {}, "metrics": {
        "complete_population": False, "z1_prediction_gate_passed": False,
        "z2_model_contribution_gate_passed": False, "z2_pd_reference_gate_passed": False, **FLAGS}}
    verified, status, collector_failure = False, "failed", None
    paid_journal = None
    execution_phase = "source_validation"
    runtime = {"python": platform.python_version(), "platform": platform.platform()}
    safe = lambda value: value
    try:
        verify_sources(repo, args.source_commit, cost, files, source_bytes)
        verified = True
        runtime.update(numpy=importlib.metadata.version("numpy"), mujoco=importlib.metadata.version("mujoco"))
        execution_phase = "Z0_gate_validation"
        _, bindings["Z0"] = read_gate(repo, Z0_RAW, cost, files, runtime, stage="Z0")
        if args.stage == "control":
            execution_phase = "Z1_gate_validation"
            saved_z1, bindings["Z1"] = read_gate(repo, Z1_RAW, cost, files, runtime, stage="Z1")
        execution_phase = "production_import"
        sys.path.insert(0, str(repo/"src"))
        from developmental_physics.fast_feedback_environment import FastFeedbackGroundBodyEnv
        from developmental_physics.fast_feedback_pair_development import (
            safe, new_result, run_prediction, run_control,
        )
        result = new_result(args.stage)
        result["cost"].update(cost)
        cost = result["cost"]
        paid_journal = gzip.open(output/"paid_intervals.jsonl.gz", "wb")
        def write_paid(row):
            # Immediate journal retains returned/partial native data before
            # any study helper, error computation or RLS submission.
            cost["paid_interval_write_attempts"] += 1
            data = (json.dumps(safe(row), ensure_ascii=False, allow_nan=False)+"\n").encode("utf-8")
            paid_journal.write(data)
            paid_journal.flush()
            cost["paid_interval_write_returns"] += 1
            cost["paid_interval_serialized_bytes"] += len(data)
        result["paid_writer"] = write_paid
        execution_phase = "production_"+args.stage
        if args.stage == "prediction":
            run_prediction(result, FastFeedbackGroundBodyEnv)
        else:
            run_control(result, FastFeedbackGroundBodyEnv, saved_z1["models.json"], saved_z1["run.json"]["seed_results"])
        failures = [trial.get("failure") for trial in result["trials"] if trial.get("failure")]
        if failures:
            collector_failure = {"type": "CollectedTrialFailure", "trial_failures": failures}
            status = "failed"
        elif all(trial.get("complete") for trial in result["trials"]):
            status = "completed"
        else:
            status = "stopped"
    except BaseException as exc:
        collector_failure = {"type": type(exc).__name__, "message": str(exc), "phase": execution_phase,
                             "traceback": traceback.format_exc()}
        status = "failed"
    finally:
        if paid_journal is not None:
            try:
                paid_journal.close()
            except BaseException as exc:
                collector_failure = collector_failure or {"type": type(exc).__name__, "message": str(exc), "stage": "paid_journal_close"}
                status = "failed"
        if collector_failure is not None:
            result["metrics"].update(execution_failed=True,
                collector_failed=execution_phase in ("production_prediction", "production_control"),
                failure_phase=execution_phase, z1_prediction_gate_passed=False,
                z2_model_contribution_gate_passed=False, z2_pd_reference_gate_passed=False,
                suspended_mechanism_validation=False)
    journal_pin = None
    if (output/"paid_intervals.jsonl.gz").exists():
        journal_data = read_bytes(output/"paid_intervals.jsonl.gz", cost, "output_manifest")
        journal_pin = identity(journal_data)
    cost["wall_seconds"], cost["cpu_seconds"] = time.perf_counter()-wall, time.process_time()-cpu
    budgets = ({"control_calls": 21000, "physics_substeps": 21000, "RLS_vector_commits": 12000,
                "RLS_scalar_commits": 24000, "independent_prediction_pairs": 124680} if args.stage == "prediction" else
               {"control_calls": 36000, "physics_substeps": 36000, "MPC_decisions": 1200,
                "planning_prediction_pairs": 14580000, "conditional_prediction_pairs": 526560})
    run = {"stage": args.stage, "status": status, "seeds": SEEDS, "source": {
        "commit": args.source_commit, "files": files, "clean_committed_bytes_verified": verified},
        "runtime": runtime, "source_gate_bindings": bindings, "planned_upper_bounds": budgets,
        "cost": dict(cost), "seed_results": summary_only(result["seed_results"]),
        "unattempted_seeds": [seed for seed in SEEDS if seed not in {row["seed"] for row in result["seed_results"]}],
        "trials": summary_only(result["trials"]), "failure": collector_failure,
        "no_reset_retry_or_mount_search": True, "learning_updates_only_calibration": True,
        "unconfirmed_environment_build_attempts": "unknown_if_constructor_exception",
        "unconfirmed_integrator_and_forward_attempts": "unknown_if_collector_exception",
        "unmeasured_filesystem_IO": "unknown_not_zero", "timing_excludes": "final_serialization_compression_and_output_writes", **FLAGS}
    payloads = {"run.json": encoded(safe(run)), "metrics.json": encoded(safe(result["metrics"])),
        "models.json": encoded(safe(result["models"])),
        "trace.jsonl.gz": gzip.compress(b"".join((json.dumps(safe(row), ensure_ascii=False, allow_nan=False)+"\n").encode("utf-8") for row in result["trace"]), mtime=0),
        "predictions.jsonl.gz": gzip.compress(b"".join((json.dumps(safe(row), ensure_ascii=False, allow_nan=False)+"\n").encode("utf-8") for row in result["predictions"]), mtime=0)}
    if source_bytes:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, data in sorted(source_bytes.items()):
                info = zipfile.ZipInfo(name)
                info.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(info, data)
        payloads["source.zip"] = buffer.getvalue()
    if collector_failure is not None:
        payloads["failure.json"] = encoded(safe(collector_failure))
    for trial in result["trials"]:
        if "installed_xml_utf8" in trial:
            payloads["installed/"+trial["trial_id"]+".xml"] = trial["installed_xml_utf8"].encode("utf-8")
    output_files = {}
    if journal_pin is not None:
        output_files["paid_intervals.jsonl.gz"] = journal_pin
    for name, data in payloads.items():
        destination = output/name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        output_files[name] = identity(data)
    (output/"manifest.json").write_bytes(encoded({"schema_version": 1, "stage": args.stage,
        "status": status, "files": output_files, **FLAGS}))
    print(json.dumps(safe({"stage": args.stage, "status": status, "output": str(output), "cost": dict(cost),
        "z1_prediction_gate_passed": result["metrics"].get("z1_prediction_gate_passed", False),
        "z2_model_contribution_gate_passed": result["metrics"].get("z2_model_contribution_gate_passed", False),
        "z2_pd_reference_gate_passed": result["metrics"].get("z2_pd_reference_gate_passed", False),
        "failure": collector_failure, **FLAGS}), ensure_ascii=False, allow_nan=False))
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
