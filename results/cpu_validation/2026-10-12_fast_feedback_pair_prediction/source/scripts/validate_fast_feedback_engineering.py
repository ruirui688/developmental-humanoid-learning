"""Z0: 2ms feedback, unchanged physical durations and gains; no body learning."""
from __future__ import annotations

import argparse
from collections import Counter
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import platform
import subprocess
import sys
import time
import traceback

import numpy as np

SOURCE_PATH = "scripts/validate_fast_feedback_engineering.py"
ENV_PATH = "src/developmental_physics/fast_feedback_environment.py"
PROTOCOL_PATH = "docs/FAST_FEEDBACK_ENGINEERING_PROTOCOL.md"
HELPER_PATH = "scripts/validate_supported_pair_engineering.py"
DEPENDENCY_PINS = {
    "src/developmental_physics/suspended_environment.py": {"bytes": 7076, "sha256": "f5154b7e059ed9939ed130d9a5c9eda2af455b9f660a4e843c72b996a44d81f8"},
    "src/developmental_physics/supported_environment.py": {"bytes": 11642, "sha256": "c10c72659fe5234febcaed78f04312f1913e494ce2533274b52baccf7c970cb0"},
    HELPER_PATH: {"bytes": 24683, "sha256": "5c75e5db6f8721180bbbb17158f29ed736b0e10554672e585867f433b3766825"},
    "src/developmental_physics/environment.py": {"bytes": 15822, "sha256": "0543b14e176e3ae11d9cf56862f11a05f7522d9909e6ec20176abef4e4556e70"},
    "src/developmental_physics/assets/ground_body.xml": {"bytes": 3430, "sha256": "23869692a531a1bf18613aecb604d29e0d5cf888e509f6861c4fb3da13f8412c"},
    "src/developmental_physics/__init__.py": {"bytes": 162, "sha256": "d2ee9d572836752f5f8404bfdf1fca8add0d62b9858f4c6dcd9cf7ddc6c53ea2"},
}
PROTOCOL_PIN = {"bytes": 9430, "sha256": "5b71ac014786ebbc464becc8579c36df906360e256d47232612ddc141b8bcee4"}
SEED, PREFIX, ACTIVE = 7600, 1000, 2000
KP, KD = (64., 64.), (4., 4.)
FLAGS = {"scientific_adoption": False, "old_free_root_C4_validation": False,
         "c4_scientific_validation": False, "c5_scientific_dependency_released": False,
         "c4_contact_scientific_validation": False}


def identity(data):
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def sources(repo, commit, cost, files):
    if Path(__file__).resolve() != (repo/SOURCE_PATH).resolve():
        raise ValueError("canonical_Z0_runner_required")

    def git(*args):
        cost["git_query_attempts"] += 1
        result = subprocess.run(["git", *args], cwd=repo, capture_output=True, check=False)
        cost["git_return_bytes"] += len(result.stdout)+len(result.stderr)
        if result.returncode:
            raise ValueError("Z0_source_git_query_failed")
        return result.stdout

    if not commit or len(commit) != 40 or any(c not in "0123456789abcdef" for c in commit):
        raise ValueError("exact_Z0_commit_required")
    if git("rev-parse", "HEAD").decode().strip() != commit or git("status", "--porcelain").strip():
        raise ValueError("clean_exact_Z0_HEAD_required")
    for name in (SOURCE_PATH, ENV_PATH, PROTOCOL_PATH, *DEPENDENCY_PINS):
        data = (repo/name).read_bytes()
        cost["source_file_reads"] += 1
        cost["source_read_and_hash_bytes"] += len(data)
        files[name] = identity(data)
        expected = PROTOCOL_PIN if name == PROTOCOL_PATH else DEPENDENCY_PINS.get(name)
        if expected is not None and files[name] != expected:
            raise ValueError("fixed_Z0_dependency_or_protocol_differs:"+name)
        if git("show", f"{commit}:{name}") != data:
            raise ValueError("Z0_committed_source_bytes_differ:"+name)


def load_helpers(repo, cost):
    """Load verified W0 pure helpers, never its collector or source verifier."""
    cost["shared_helper_module_load_attempts"] += 1
    spec = importlib.util.spec_from_file_location("_Z0_frozen_W0_pure_helpers", repo/HELPER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    cost["shared_helper_module_load_returns"] += 1
    return module


def contact_summary(records):
    summary = {scope: {kind: {"pair_events": 0, "finite_positive_normal_force_events": 0}
                         for kind in ("left_arm", "feet", "other")}
               for scope in ("all_retained_substeps", "prefix_last200")}
    for row in records:
        scopes = ["all_retained_substeps"]
        if row["phase"] == "prefix" and 800 <= row["phase_index"] < 1000:
            scopes.append("prefix_last200")
        samples = (row.get("diagnostics") or row.get("saved_partial") or {}).get("substep_native_and_contact_records", [])
        for sample in samples:
            for pair in sample.get("floor_contacts", []):
                kind = pair["contact_class"]
                if kind not in ("left_arm", "feet", "other"):
                    raise ValueError("unexpected_Z0_floor_contact_class")
                normal = pair["normal_force_n"]
                positive = isinstance(normal, (int, float)) and np.isfinite(normal) and normal > 0.
                for scope in scopes:
                    summary[scope][kind]["pair_events"] += 1
                    summary[scope][kind]["finite_positive_normal_force_events"] += int(positive)
    return {"counts": summary, "required_for_engineering_pass": False,
            "scope": "saved_substep_pairs_only_not_unobserved_contacts",
            "controlled_arm_contact_learning_proven": False,
            "feet_contact_implies_arm_contact": False}


def complete_fast_telemetry(row):
    samples = (row.get("diagnostics") or {}).get("substep_native_and_contact_records", [])
    if len(samples) != 1:
        return False
    sample = samples[0]
    if not isinstance(sample.get("floor_contacts"), list):
        return False
    step = row["control_index"] + 1
    if sample.get("physics_step") != step or not np.isfinite(sample.get("time", float("nan"))):
        return False
    if abs(sample["time"] - step * .002) > 1e-10:
        return False
    values = [(sample.get("applied_command8"), 8), (sample.get("actual_actuator_torque8"), 8)]
    observation = sample.get("observation", {})
    values.extend((observation.get(key), size) for key, size in (("joint_position", 8), ("joint_velocity", 8),
                  ("imu_gyro", 3), ("imu_acceleration", 3), ("actuator_torque", 8), ("previous_command", 8)))
    if any(np.asarray(value).shape != (size,) or not np.isfinite(np.asarray(value, dtype=float)).all()
           for value, size in values):
        return False
    for pair in sample.get("floor_contacts", []):
        if not np.isfinite(pair.get("normal_force_n", float("nan"))) or not np.isfinite(pair.get("distance_m", float("nan"))):
            return False
    return True


def qualification(records, support, helpers):
    """New one-substep population; old 20ms qualification is never called."""
    full = (len(records) == PREFIX+ACTIVE and all(
        row.get("control_index") == index and row.get("seed") == SEED
        and row.get("phase") == ("prefix" if index < PREFIX else "active")
        and row.get("phase_index") == (index if index < PREFIX else index-PREFIX)
        and row.get("returned") is True and (row.get("diagnostics") or {}).get("executed_substeps") == 1
        and row.get("environment_terminated") is False and row.get("study_abort") is None
        and complete_fast_telemetry(row) for index, row in enumerate(records)))
    mount = (support or {}).get("installation") or {}
    samples = [sample for row in records for sample in
               (row.get("diagnostics") or row.get("saved_partial") or {}).get("substep_native_and_contact_records", [])]
    fixed = bool(mount) and len(samples) == 3000 and all(
        sample["diagnostics"]["root_position"] == mount["fixed_torso_world_position"]
        and sample["diagnostics"]["root_quaternion"] == mount["fixed_torso_world_quaternion"]
        for sample in samples)
    windows = []
    for segment, lower, upper in ((0, 800, 1000), (1, 1800, 2000)):
        selected = [row for row in records if row.get("phase") == "active" and lower <= row["phase_index"] < upper]
        available = full and len(selected) == 200 and all(row.get("target_error_rad") is not None for row in selected)
        errors = np.asarray([row["target_error_rad"] for row in selected], dtype=float) if available else None
        if available and (errors.shape != (200, 2) or not np.isfinite(errors).all()):
            available = False
        mae = np.mean(np.abs(errors), axis=0).tolist() if available else None
        windows.append({"segment": segment, "active_indices": [lower, upper-1], "planned_count": 200,
                        "observed_count": len(selected), "duration_seconds": .4,
                        "full_trial_required": True, "available": available, "per_axis_mae_rad": mae,
                        "threshold_rad": .01, "passed": bool(available and all(value <= .01 for value in mae))})
    passed = full and fixed and all(window["passed"] for window in windows)
    return {"full_1000_prefix_2000_active": full, "complete_finite_substep_native_effort_required": True,
            "fixed_upright_mount_observed_all_3000_substeps": fixed, "last200_post_step_windows": windows,
            "contact_observations": contact_summary(records), "contact_required_for_pass": False,
            "engineering_qualification_passed": bool(passed), "partial_subset_gate": False,
            "meaning": "fast_feedback_suspended_noncontact_engineering_only", **FLAGS}


def effort_summary(records, helpers):
    result = {phase: {"actual_absolute_per_axis_nm_s": [0., 0.],
                      "actual_squared_per_axis_nm2_s": [0., 0.],
                      "actual_all8_absolute_nm_s": 0., "actual_all8_squared_nm2_s": 0.,
                      "applied_command_all8_absolute_nm_s": 0., "applied_command_all8_squared_nm2_s": 0.,
                      "saved_substeps": 0, "valid_effort_substeps": 0, "unavailable_effort_substeps": 0}
              for phase in ("prefix", "active")}
    for row in records:
        out = result[row["phase"]]
        for sample in (row.get("diagnostics") or row.get("saved_partial") or {}).get("substep_native_and_contact_records", []):
            out["saved_substeps"] += 1
            actual, command = (np.asarray(sample.get(key), dtype=float) for key in ("actual_actuator_torque8", "applied_command8"))
            if actual.shape != (8,) or command.shape != (8,) or not np.isfinite(actual).all() or not np.isfinite(command).all():
                out["unavailable_effort_substeps"] += 1
                continue
            out["valid_effort_substeps"] += 1
            for i in range(2):
                out["actual_absolute_per_axis_nm_s"][i] += float(abs(actual[i])*.002)
                out["actual_squared_per_axis_nm2_s"][i] += float(actual[i]**2*.002)
            out["actual_all8_absolute_nm_s"] += float(np.sum(np.abs(actual))*.002)
            out["actual_all8_squared_nm2_s"] += float(np.sum(actual**2)*.002)
            out["applied_command_all8_absolute_nm_s"] += float(np.sum(np.abs(command))*.002)
            out["applied_command_all8_squared_nm2_s"] += float(np.sum(command**2)*.002)
    return helpers.safe(result)


def pd_request(q, v, target):
    """Z0 native feedback: unchanged Y gains, now every 2ms, no feedforward model."""
    raw = np.asarray(KP)*(np.asarray(target)-np.asarray(q))-np.asarray(KD)*np.asarray(v)
    return raw.tolist(), np.clip(raw, -.5, .5).tolist()


def main_run(args):
    repo, output = Path(args.repo).resolve(), Path(args.output).resolve()
    if output == repo or repo.is_relative_to(output):
        raise ValueError("Z0_output_cannot_contain_repository")
    output.mkdir(parents=True, exist_ok=False)
    wall, cpu = time.perf_counter(), time.process_time()
    cost = Counter({key: 0 for key in ("control_call_attempts", "control_call_returns", "control_call_exceptions",
                    "confirmed_physics_substeps", "body_model_forward_calls", "RLS_updates", "body_model_fits",
                    "body_model_restorations", "MPC_calls", "teacher_calls", "PD_vector_evaluations",
                    "environment_constructor_attempts", "environment_constructor_returns", "reset_attempts", "reset_returns")})
    files, records, cases, saved_XML_files = {}, [], [], {}
    helpers = env = observation = support = fingerprint_before = fingerprint_after = None
    physical_before = physical_after = interface_configuration = None
    qref = selection = targets = None
    status, failure, stop, verified = "failed", None, None, False
    runtime = {"python": platform.python_version(), "numpy": np.__version__, "platform": platform.platform()}
    try:
        sources(repo, args.source_commit, cost, files)
        verified = True
        helpers = load_helpers(repo, cost)
        sys.path.insert(0, str(repo/"src"))
        import mujoco
        from developmental_physics.fast_feedback_environment import FastFeedbackGroundBodyEnv
        runtime["mujoco"] = mujoco.__version__
        cost["environment_constructor_attempts"] += 1
        env = FastFeedbackGroundBodyEnv()
        cost["environment_constructor_returns"] += 1
        (output/"suspended_body_before_height.xml").write_bytes(env._derived_xml)
        saved_XML_files["suspended_body_before_height.xml"] = identity(env._derived_xml)
        cost["reset_attempts"] += 1
        observation = env.reset(seed=SEED, pose="upright")
        cost["reset_returns"] += 1
        support = env.support_configuration()
        (output/"suspended_body_installed.xml").write_bytes(env._installed_xml)
        saved_XML_files["suspended_body_installed.xml"] = identity(env._installed_xml)
        cost["parameter_fingerprint_attempts"] += 1
        fingerprint_before = env.parameter_fingerprint()
        cost["parameter_fingerprint_returns"] += 1
        cost["physical_configuration_fingerprint_attempts"] += 1
        physical_before = env.physical_configuration_fingerprint()
        cost["physical_configuration_fingerprint_returns"] += 1
        interface_configuration = env.action_interface_configuration()
        ranges = env.model.jnt_range[env._joint_ids].copy()
        for index in range(PREFIX+ACTIVE):
            phase, active = ("prefix" if index < PREFIX else "active"), index-PREFIX
            target = raw = None
            request = np.zeros(8)
            if phase == "active":
                if qref is None:
                    qref, selection, targets, feasible = helpers.targets_and_direction(observation, ranges)
                    if not feasible:
                        stop = {"primary_reason": "infeasible_fixed_target_no_clipping_or_direction_retry",
                                "complete_prefix_calls": PREFIX, "active_calls": 0}
                        break
                target = targets[0 if active < 1000 else 1]
                q, v = (np.asarray(observation[key])[:2] for key in ("joint_position", "joint_velocity"))
                cost["PD_vector_evaluations"] += 1
                raw, final_pair = pd_request(q, v, target)
                request[:2] = final_pair
            row = {"seed": SEED, "trial_id": "Z0_seed7600", "transition_id": f"Z0_seed7600:{index}",
                   "control_index": index, "phase": phase, "phase_index": index if phase == "prefix" else active,
                   "observation_before": helpers.safe(observation), "requested_torque": request.tolist(),
                   "current_target_q2": target, "raw_PD_request2": raw, "returned": False,
                   "study_abort": None, "environment_terminated": None, "diagnostics": None}
            records.append(row)
            before_steps = env.physics_steps
            cost["control_call_attempts"] += 1
            try:
                result = env.step(request)
            except BaseException as exc:
                cost["control_call_exceptions"] += 1
                row.update(collector_exception={"type": type(exc).__name__, "message": str(exc)},
                           confirmed_completed_substeps=env.physics_steps-before_steps,
                           saved_partial=env.last_step_partial)
                raise
            finally:
                cost["confirmed_physics_substeps"] += env.physics_steps-before_steps
            cost["control_call_returns"] += 1
            observation = result.observation
            row.update(returned=True, observation_after=helpers.safe(observation), diagnostics=result.diagnostics,
                       environment_terminated=bool(result.terminated), environment_reason=result.reason)
            complete = result.diagnostics["executed_substeps"] == 1
            study = helpers.study_abort(observation, qref) if phase == "active" and complete else None
            error = (np.asarray(observation["joint_position"])[:2]-np.asarray(target)).tolist() if target is not None else None
            row.update(study_abort=study, target_error_rad=error)
            if result.terminated or not complete or study is not None:
                stop = {"transition_id": row["transition_id"], "environment_reason": result.reason,
                        "environment_terminated": bool(result.terminated), "study_abort": study,
                        "executed_substeps": result.diagnostics["executed_substeps"],
                        "primary_reason": result.reason or ("partial_interval" if not complete else "StudyAbort")}
                break
        status = "stopped" if stop is not None else "completed"
        cost["parameter_fingerprint_attempts"] += 1
        fingerprint_after = env.parameter_fingerprint()
        cost["parameter_fingerprint_returns"] += 1
        cost["physical_configuration_fingerprint_attempts"] += 1
        physical_after = env.physical_configuration_fingerprint()
        cost["physical_configuration_fingerprint_returns"] += 1
        if fingerprint_after != fingerprint_before or physical_before != physical_after:
            raise ValueError("Z0_fixed_execution_or_physical_parameters_changed")
    except BaseException as exc:
        failure = {"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()}
        status = "failed"
        if cases and cases[-1]["status"] == "attempted":
            cases[-1]["status"] = "failed"

    metrics = {"engineering_qualification_passed": False, **FLAGS}
    effort = None
    if helpers is not None:
        try:
            metrics = qualification(records, support, helpers)
            effort = effort_summary(records, helpers)
        except BaseException as exc:
            metrics.update(engineering_qualification_passed=False, reporting_failed=True)
            secondary = {"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()}
            failure = {"primary": failure, "reporting": secondary} if failure else secondary
            status = "failed"
    if failure is not None:
        metrics.update(engineering_qualification_passed=False, collector_failed=True)
    cost["wall_seconds"], cost["cpu_seconds"] = time.perf_counter()-wall, time.process_time()-cpu
    run = {"status": status, "self_check": False,
           "source": {"commit": args.source_commit, "files": files, "clean_committed_bytes_verified": verified},
           "runtime": runtime, "domain": "Z_fast_feedback_suspended_fixed_upright_torso", "seed": SEED,
           "planned_calls": 3000, "planned_substeps": 3000, "control_substeps": 1, "physics_dt": .002, "control_dt": .002,
           "prefix_duration_seconds": 2., "active_duration_seconds": 4.,
           "research_stop_observation_cadence_seconds": .002,
           "prefix_steps": PREFIX, "active_steps": ACTIVE,
           "pd": {"kp": KP, "kd": KD, "gain_source": "Z_shared_Y_PD64_Kd4_4_no_gain_change_or_scan"},
           "qref2": qref, "direction_selection": selection, "targets_q2": targets,
           "qref_source": "complete_prefix999_after_native_q_only" if qref is not None else "unavailable",
           "support": support, "engineering_operations": env.engineering_operations if env else None,
           "execution_fingerprint_before": fingerprint_before, "execution_fingerprint_after": fingerprint_after,
           "physical_configuration_fingerprint_before": physical_before,
           "physical_configuration_fingerprint_after": physical_after,
           "action_interface": interface_configuration,
           "cost": dict(cost), "actual_effort_by_phase": effort, "stop": stop, "failure": failure,
           "self_check_cases": cases, "engineering_qualification_passed": metrics["engineering_qualification_passed"],
           "contact_required_for_pass": False, "no_reset_retry_or_mount_search": True,
           "incomplete_or_missing_substep_cost_and_effort": "unknown_unobserved_portion_not_zero; saved_samples_are_lower_bound_if_incomplete",
           "constructor_accounting_if_no_env_returned": "unknown; constructor_attempt_is_counted",
           "parameter_fingerprint_asset_read_bytes_per_return": DEPENDENCY_PINS["src/developmental_physics/assets/ground_body.xml"]["bytes"],
           "explicit_physical_fingerprint_asset_read_bytes_per_return": DEPENDENCY_PINS["src/developmental_physics/assets/ground_body.xml"]["bytes"],
           "timing_excludes": "process_startup_and_global_imports; final_serialization_compression_and_output_writes",
           "unmeasured_filesystem_IO_and_import_backend_bytes": "unknown_not_zero", **FLAGS}
    # Failure before helper import still receives a valid evidence manifest.
    def encoded(value):
        if helpers is not None:
            return helpers.encoded(value)
        return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+"\n").encode("utf-8")

    payloads = {"run.json": encoded(run), "metrics.json": encoded(metrics)}
    safe_rows = (helpers.safe(row) for row in records) if helpers is not None else records
    payloads["trace.jsonl.gz"] = gzip.compress(b"".join(
        (json.dumps(row, ensure_ascii=False, allow_nan=False)+"\n").encode("utf-8") for row in safe_rows), mtime=0)
    if failure is not None:
        payloads["failure.json"] = encoded(failure)
    output_files = dict(saved_XML_files)
    for name, data in payloads.items():
        (output/name).write_bytes(data)
        output_files[name] = identity(data)
    (output/"manifest.json").write_bytes(encoded({"schema_version": 1, "status": status, "files": output_files, **FLAGS}))
    brief = {"status": status, "output": str(output), "cost": dict(cost), "stop": stop,
             "engineering_qualification_passed": metrics["engineering_qualification_passed"],
             "failure": failure and {"detail": "see preserved failure.json"}, **FLAGS}
    print(json.dumps(helpers.safe(brief) if helpers is not None else brief, allow_nan=False))
    return 0 if failure is None else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".")
    parser.add_argument("--output", required=True)
    parser.add_argument("--source-commit")
    args = parser.parse_args()
    if not args.source_commit:
        parser.error("--source-commit required for the first formal engineering run")
    raise SystemExit(main_run(args))
