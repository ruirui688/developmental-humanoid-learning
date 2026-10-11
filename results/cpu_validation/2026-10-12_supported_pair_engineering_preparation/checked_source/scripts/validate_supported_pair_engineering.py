"""W0: one fixed seed, fixed supported domain and bounded PD engineering qualification."""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict
import gzip
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys
import time
import traceback

import numpy as np

SOURCE_PATH = "scripts/validate_supported_pair_engineering.py"
ENV_PATH = "src/developmental_physics/supported_environment.py"
PROTOCOL_PATH = "docs/SUPPORTED_PAIR_DOMAIN_DESIGN.md"
SHARED_PATHS = ("src/developmental_physics/environment.py",
                "src/developmental_physics/assets/ground_body.xml",
                "src/developmental_physics/__init__.py")
PROTOCOL_PIN = {"bytes": 16400, "sha256": "cf7e9b39a7dc95b6b592fa64aed39a8dd3324c9a50e0cc80452dc3a89237db9a"}
SEED, PREFIX, ACTIVE = 7300, 100, 200
KP, KD = (64., 64.), (0., 4.)
FLAGS = {"scientific_adoption": False, "old_free_root_C4_validation": False,
         "c4_scientific_validation": False, "c5_scientific_dependency_released": False}


def identity(data):
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def safe(value):
    if isinstance(value, np.ndarray):
        return safe(value.tolist())
    if isinstance(value, (float, np.floating)) and not np.isfinite(value):
        return {"nonfinite_float": "NaN" if np.isnan(value) else "+Infinity" if value > 0 else "-Infinity"}
    if isinstance(value, dict):
        return {key: safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [safe(item) for item in value]
    if isinstance(value, np.integer):
        return int(value)
    return value


def encoded(value):
    return (json.dumps(safe(value), ensure_ascii=False, indent=2, allow_nan=False)+"\n").encode("utf-8")


def sources(repo, commit, synthetic, cost, files):
    if Path(__file__).resolve() != (repo/SOURCE_PATH).resolve():
        raise ValueError("canonical_W0_runner_required")
    def git(*args):
        cost["git_query_attempts"] += 1
        result = subprocess.run(["git", *args], cwd=repo, capture_output=True, check=False)
        cost["git_return_bytes"] += len(result.stdout)+len(result.stderr)
        if result.returncode:
            raise ValueError("source_git_query_failed")
        return result.stdout
    if not synthetic:
        if not commit or len(commit) != 40 or any(c not in "0123456789abcdef" for c in commit):
            raise ValueError("exact_W0_commit_required")
        if git("rev-parse", "HEAD").decode().strip() != commit or git("status", "--porcelain").strip():
            raise ValueError("clean_exact_W0_HEAD_required")
    for name in (SOURCE_PATH, ENV_PATH, PROTOCOL_PATH, *SHARED_PATHS):
        data = (repo/name).read_bytes()
        cost["source_file_reads"] += 1
        cost["source_read_and_hash_bytes"] += len(data)
        files[name] = identity(data)
        if name == PROTOCOL_PATH and files[name] != PROTOCOL_PIN:
            raise ValueError("fixed_W0_protocol_differs")
        if not synthetic and git("show", f"{commit}:{name}") != data:
            raise ValueError("committed_source_bytes_differ:"+name)


def study_abort(observation, qref):
    q = np.asarray(observation["joint_position"], dtype=float)[:2]
    v = np.asarray(observation["joint_velocity"], dtype=float)[:2]
    triggers = []
    for i in range(2):
        if abs(q[i]-qref[i]) >= .12:
            triggers.append({"joint_index": i, "signal": "absolute_q_minus_qref_rad"})
        if abs(v[i]) >= 1.:
            triggers.append({"joint_index": i, "signal": "absolute_velocity_rad_s"})
    return None if not triggers else {"type": "StudyAbort", "triggers": triggers,
        "q_rad": q.tolist(), "qref_rad": list(qref), "velocity_rad_s": v.tolist(),
        "thresholds": {"absolute_q_minus_qref_rad": .12, "absolute_velocity_rad_s": 1.},
        "evaluation_time": "after_complete_control_interval", "feedback_action": None}


def targets_and_direction(observation, public_ranges):
    qref = np.asarray(observation["joint_position"], dtype=float)[:2].copy()
    ranges = np.asarray(public_ranges, dtype=float)
    if qref.shape != (2,) or ranges.shape != (8, 2) or not np.isfinite(qref).all() or not np.isfinite(ranges).all():
        raise ValueError("finite_native_qref_and_public_ranges_required")
    selection = []
    for i in range(2):
        lower, upper = ranges[i]
        positive, negative = upper-qref[i], qref[i]-lower
        selection.append({"joint_index": i, "joint_position_rad": float(qref[i]),
                          "lower_limit_rad": float(lower), "upper_limit_rad": float(upper),
                          "positive_room_rad": float(positive), "negative_room_rad": float(negative),
                          "direction": 1 if positive >= negative else -1,
                          "rule": "larger_public_limit_distance_tie_positive"})
    directions = np.asarray([item["direction"] for item in selection])
    targets = [qref+directions*offset for offset in (.04, .08)]
    feasible = all(np.isfinite(target).all() and np.all(target >= ranges[:2, 0]+.03)
                   and np.all(target <= ranges[:2, 1]-.03) for target in targets)
    return qref.tolist(), selection, [target.tolist() for target in targets], bool(feasible)


def complete_substep_telemetry(row):
    samples = (row.get("diagnostics") or {}).get("substep_native_and_contact_records", [])
    if len(samples) != 10:
        return False
    for i, sample in enumerate(samples):
        if sample.get("physics_step") != row["control_index"]*10+i+1:
            return False
        values = [(sample.get("applied_command8"), 8), (sample.get("actual_actuator_torque8"), 8)]
        observation = sample.get("observation", {})
        values.extend((observation.get(key), size) for key, size in (("joint_position", 8), ("joint_velocity", 8),
                      ("imu_gyro", 3), ("imu_acceleration", 3), ("actuator_torque", 8), ("previous_command", 8)))
        if any(np.asarray(value).shape != (size,) or not np.isfinite(np.asarray(value, dtype=float)).all()
               for value, size in values):
            return False
        if not np.isfinite(sample.get("time", float("nan"))):
            return False
        for contact in sample.get("floor_contacts", []):
            if not np.isfinite(contact.get("normal_force_n", float("nan"))) or not np.isfinite(contact.get("distance_m", float("nan"))):
                return False
    return True


def qualification(records):
    full = (len(records) == PREFIX+ACTIVE and all(row.get("returned") is True and
            (row.get("diagnostics") or {}).get("executed_substeps") == 10 and
            row.get("environment_terminated") is False and row.get("study_abort") is None and complete_substep_telemetry(row)
            for row in records))
    contacts = []
    for row in records:
        if row.get("phase") != "prefix" or not 80 <= row["phase_index"] < 100:
            continue
        for substep in (row.get("diagnostics") or {}).get("substep_native_and_contact_records", []):
            for pair in substep.get("floor_contacts", []):
                normal = pair.get("normal_force_n")
                names = pair.get("geom_names", [])
                if ("floor" in names and any(name in ("left_upper_arm_geom", "left_forearm_geom") for name in names)
                        and isinstance(normal, (int, float)) and np.isfinite(normal) and normal > 0.):
                    contacts.append({"transition_id": row["transition_id"], "physics_step": substep["physics_step"],
                                     "time": substep["time"], "contact": pair})
    windows = []
    for segment, lower, upper in ((0, 80, 100), (1, 180, 200)):
        selected = [row for row in records if row.get("phase") == "active" and lower <= row["phase_index"] < upper]
        available = full and len(selected) == 20 and all(row.get("target_error_rad") is not None for row in selected)
        errors = np.asarray([row["target_error_rad"] for row in selected], dtype=float) if available else None
        if available and (errors.shape != (20, 2) or not np.isfinite(errors).all()):
            available = False
        mae = np.mean(np.abs(errors), axis=0).tolist() if available else None
        windows.append({"segment": segment, "active_indices": [lower, upper-1], "planned_count": 20,
                        "observed_count": len(selected), "full_trial_required": True, "available": available,
                        "per_axis_mae_rad": mae, "threshold_rad": .01,
                        "passed": bool(available and all(value <= .01 for value in mae))})
    passed = full and bool(contacts) and all(window["passed"] for window in windows)
    return {"full_100_prefix_200_active": full, "complete_finite_substep_native_effort_required": True,
            "fixed_prefix_last20_left_arm_positive_floor_contact": bool(contacts),
            "qualifying_contact_events": contacts, "last20_post_step_windows": windows,
            "engineering_qualification_passed": bool(passed), "partial_subset_gate": False,
            "meaning": "supported_domain_engineering_only", **FLAGS}


def main_run(args):
    repo, output = Path(args.repo).resolve(), Path(args.output).resolve()
    if output == repo or repo.is_relative_to(output):
        raise ValueError("output_cannot_contain_repository")
    output.mkdir(parents=True, exist_ok=False)
    wall, cpu = time.perf_counter(), time.process_time()
    cost = Counter({key: 0 for key in ("control_call_attempts", "control_call_returns", "control_call_exceptions",
                    "confirmed_physics_substeps", "RLS_updates", "body_model_fits", "body_model_restorations",
                    "MPC_calls", "teacher_calls", "reset_attempts", "reset_returns")})
    files, records, cases = {}, [], []
    env, observation, support, fingerprint_before, fingerprint_after = None, None, None, None, None
    qref, selection, targets = None, None, None
    status, failure, stop, verified = "failed", None, None, False
    runtime = {"python": platform.python_version(), "numpy": np.__version__, "platform": platform.platform()}
    try:
        sources(repo, args.source_commit, args.self_check, cost, files)
        verified = not args.self_check
        sys.path.insert(0, str(repo/"src"))
        import mujoco
        from developmental_physics.supported_environment import SupportedGroundBodyEnv
        runtime["mujoco"] = mujoco.__version__
        env = SupportedGroundBodyEnv()
        cost["reset_attempts"] += 1
        observation = env.reset(seed=SEED, pose="supine")
        cost["reset_returns"] += 1
        support = env.support_configuration()
        (output/"supported_body_installed.xml").write_bytes(env._installed_xml)
        fingerprint_before = env.parameter_fingerprint()
        if args.self_check:
            event = {"case": "new_fixed_root_assembly_name_mapping_reset_world_diagnostics", "status": "attempted"}
            cases.append(event)
            diag = env.diagnostics()
            assert (env.model.nq, env.model.nv, env.model.nu) == (8, 8, 8)
            assert env._joint_qpos.tolist() == list(range(8)) and env._joint_dof.tolist() == list(range(8))
            assert np.array_equal(observation["joint_position"], env.data.qpos[env._joint_qpos])
            assert np.array_equal(observation["joint_velocity"], np.zeros(8))
            assert diag["root_position"] == env.data.xpos[env._torso_id].tolist()
            assert diag["root_quaternion"] == env.data.xquat[env._torso_id].tolist()
            assert env.physics_steps == env.step_id == 0 and env.data.time == 0.
            assert env.engineering_operations["reset_forward_attempts"] == env.engineering_operations["reset_forward_returns"] == 2
            from developmental_physics.environment import GroundBodyEnv, JOINT_NAMES
            original = GroundBodyEnv()
            cost["preparation_original_model_builds"] += 1
            original.reset(seed=SEED, pose="supine")
            cost["preparation_original_reset_forward_calls"] += 2
            event["compiled_topology"] = {
                "original": {"nq": original.model.nq, "nv": original.model.nv, "njnt": original.model.njnt,
                             "named_body_weld_ids": [{"body_name": original.model.body(i).name,
                                "body_id": i, "weld_id": int(original.model.body_weldid[i])} for i in range(original.model.nbody)]},
                "supported": {"nq": env.model.nq, "nv": env.model.nv, "njnt": env.model.njnt,
                              "named_body_weld_ids": support["named_body_weld_ids"]},
                "root_dofs_removed": 6, "free_root_qpos_removed": 7,
                "effective_static_collision_filtering_changed": True,
            }
            event["public_parameter_difference_fields"] = []
            def exact_public(label, before, after):
                if not np.array_equal(before, after):
                    event["public_parameter_difference_fields"].append({"field": label, "original": safe(before), "supported": safe(after)})
                    raise ValueError("new_supported_public_parameter_differs:"+label)
            geometry_position_maxdiff, geometry_matrix_maxdiff = 0., 0.
            for name in JOINT_NAMES:
                old_joint, new_joint = original.model.joint(name).id, env.model.joint(name).id
                exact_public(name+".jnt_range", original.model.jnt_range[old_joint], env.model.jnt_range[new_joint])
                old_dof, new_dof = original.model.jnt_dofadr[old_joint], env.model.jnt_dofadr[new_joint]
                for field in ("dof_damping", "dof_armature"):
                    exact_public(name+"."+field, getattr(original.model, field)[old_dof], getattr(env.model, field)[new_dof])
            for gid in range(original.model.ngeom):
                name = original.model.geom(gid).name
                new_gid = env.model.geom(name).id
                geometry_position_maxdiff = max(geometry_position_maxdiff, float(np.max(np.abs(original.data.geom_xpos[gid]-env.data.geom_xpos[new_gid]))))
                geometry_matrix_maxdiff = max(geometry_matrix_maxdiff, float(np.max(np.abs(original.data.geom_xmat[gid]-env.data.geom_xmat[new_gid]))))
                event.update(geometry_position_maxdiff_m=geometry_position_maxdiff, geometry_rotation_matrix_maxdiff=geometry_matrix_maxdiff)
                assert np.allclose(original.data.geom_xpos[gid], env.data.geom_xpos[new_gid], rtol=0., atol=1e-12)
                assert np.allclose(original.data.geom_xmat[gid], env.data.geom_xmat[new_gid], rtol=0., atol=1e-12)
                for field in ("geom_size", "geom_friction", "geom_solref", "geom_solimp", "geom_priority", "geom_condim",
                              "geom_contype", "geom_conaffinity"):
                    exact_public(name+"."+field, getattr(original.model, field)[gid], getattr(env.model, field)[new_gid])
            for field in ("actuator_gainprm", "actuator_biasprm", "actuator_gear", "actuator_ctrlrange",
                          "body_mass", "body_inertia"):
                exact_public(field, getattr(original.model, field), getattr(env.model, field))
            exact_public("gravity", original.model.opt.gravity, env.model.opt.gravity)
            exact_public("timestep", original.model.opt.timestep, env.model.opt.timestep)
            assert original.physics_steps == original.step_id == 0 and original.data.time == 0.
            event.update(original_model_builds=1, original_reset_forward_calls=2,
                         supported_model_builds=1, supported_reset_forward_calls=2,
                         geometry_tolerance_m_and_matrix=1e-12, geometry_and_public_parameter_equivalence=True,
                         public_parameters_compared=["named_joint_range/damping/armature", "named_geom_size/friction/solref/solimp/priority/condim/contype/conaffinity",
                                                     "actuator_gain/bias/gear/ctrlrange", "body_mass/inertia", "gravity/timestep"])
            event["status"] = "passed"
            status = "self_check_passed"
        else:
            ranges = env.model.jnt_range[env._joint_ids].copy()
            for index in range(PREFIX+ACTIVE):
                phase = "prefix" if index < PREFIX else "active"
                active = index-PREFIX
                target, raw = None, None
                request = np.zeros(8)
                if phase == "active":
                    if qref is None:
                        qref, selection, targets, feasible = targets_and_direction(observation, ranges)
                        if not feasible:
                            stop = {"primary_reason": "infeasible_fixed_target_no_clipping_or_direction_retry",
                                    "complete_prefix_calls": PREFIX, "active_calls": 0}
                            break
                    target = targets[0 if active < 100 else 1]
                    q = np.asarray(observation["joint_position"])[:2]
                    v = np.asarray(observation["joint_velocity"])[:2]
                    raw = (np.asarray(KP)*(np.asarray(target)-q)-np.asarray(KD)*v).tolist()
                    request[:2] = np.clip(raw, -.5, .5)
                record = {"seed": SEED, "trial_id": "W0_seed7300", "transition_id": f"W0_seed7300:{index}",
                          "control_index": index, "phase": phase, "phase_index": index if phase == "prefix" else active,
                          "observation_before": safe(observation), "requested_torque": request.tolist(),
                          "current_target_q2": target, "raw_PD_request2": raw, "returned": False,
                          "study_abort": None, "environment_terminated": None, "diagnostics": None}
                records.append(record)
                before_steps = env.physics_steps
                cost["control_call_attempts"] += 1
                try:
                    result = env.step(request)
                except BaseException as exc:
                    cost["control_call_exceptions"] += 1
                    record.update(collector_exception={"type": type(exc).__name__, "message": str(exc)},
                                  confirmed_completed_substeps=env.physics_steps-before_steps,
                                  saved_partial=env.last_step_partial)
                    raise
                finally:
                    cost["confirmed_physics_substeps"] += env.physics_steps-before_steps
                cost["control_call_returns"] += 1
                observation = result.observation
                record.update(returned=True, observation_after=safe(observation), diagnostics=result.diagnostics,
                              environment_terminated=bool(result.terminated), environment_reason=result.reason)
                complete = result.diagnostics["executed_substeps"] == 10
                study = study_abort(observation, qref) if phase == "active" and complete else None
                error = (np.asarray(observation["joint_position"])[:2]-np.asarray(target)).tolist() if target is not None else None
                record.update(study_abort=study, target_error_rad=error)
                if result.terminated or not complete or study is not None:
                    stop = {"transition_id": record["transition_id"], "environment_reason": result.reason,
                            "environment_terminated": bool(result.terminated), "study_abort": study,
                            "executed_substeps": result.diagnostics["executed_substeps"],
                            "primary_reason": result.reason or ("partial_interval" if not complete else "StudyAbort")}
                    break
            status = "stopped" if stop is not None else "completed"
        fingerprint_after = env.parameter_fingerprint()
        if fingerprint_after != fingerprint_before:
            raise ValueError("fixed_supported_physical_parameters_changed")
    except BaseException as exc:
        failure = {"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()}
        status = "failed"
    metrics = qualification(records) if not args.self_check else {"engineering_qualification_passed": False, "self_check_only": True, **FLAGS}
    if failure is not None:
        metrics.update(engineering_qualification_passed=False, collector_failed=True)
    effort = {"actual_sum_abs_tau_dt_nm_s": 0., "actual_sum_tau_squared_dt_nm2_s": 0.,
              "applied_command_sum_abs_dt_nm_s": 0., "applied_command_sum_squared_dt_nm2_s": 0., "substep_samples": 0}
    for record in records:
        samples = (record.get("diagnostics") or record.get("saved_partial") or {}).get("substep_native_and_contact_records", [])
        for sample in samples:
            actual = np.asarray(sample["actual_actuator_torque8"], dtype=float)
            command = np.asarray(sample["applied_command8"], dtype=float)
            effort["actual_sum_abs_tau_dt_nm_s"] += float(np.sum(np.abs(actual))*.002)
            effort["actual_sum_tau_squared_dt_nm2_s"] += float(np.sum(actual**2)*.002)
            effort["applied_command_sum_abs_dt_nm_s"] += float(np.sum(np.abs(command))*.002)
            effort["applied_command_sum_squared_dt_nm2_s"] += float(np.sum(command**2)*.002)
            effort["substep_samples"] += 1
    cost["confirmed_substep_endpoint_forward_returns"] = effort["substep_samples"]
    cost["wall_seconds"], cost["cpu_seconds"] = time.perf_counter()-wall, time.process_time()-cpu
    run = {"status": status, "self_check": args.self_check, "source": {"commit": args.source_commit, "files": files,
           "clean_committed_bytes_verified": verified}, "runtime": runtime, "seed": SEED,
           "planned_calls": 300, "planned_substeps": 3000, "control_substeps": 10, "physics_dt": .002,
           "prefix_steps": PREFIX, "active_steps": ACTIVE, "pd": {"kp": KP, "kd": KD, "gain_source": "existing_public_PD64_Kd0_4_development_prior"},
           "qref2": qref, "direction_selection": selection, "targets_q2": targets,
           "qref_source": "complete_prefix99_after_native_q_only" if qref is not None else "unavailable",
           "support": support, "engineering_operations": env.engineering_operations if env else None,
           "physical_fingerprint_before": fingerprint_before, "physical_fingerprint_after": fingerprint_after,
           "cost": dict(cost), "actual_effort": effort, "stop": stop, "failure": failure, "self_check_cases": cases,
           "engineering_qualification_passed": metrics["engineering_qualification_passed"],
           "no_reset_retry_or_mount_search": True, "collector_exception_unconfirmed_integrator_attempts": "unknown_if_exception",
           "unconfirmed_endpoint_forward_attempts": "unknown_if_integration_or_forward_exception",
           "timing_excludes": "final_serialization_compression_and_output_writes",
           "unmeasured_filesystem_IO": "unknown_not_zero", **FLAGS}
    payloads = {"run.json": encoded(run), "metrics.json": encoded(metrics),
                "trace.jsonl.gz": gzip.compress(b"".join((json.dumps(safe(record), ensure_ascii=False, allow_nan=False)+"\n").encode("utf-8")
                                                      for record in records), mtime=0)}
    if failure is not None:
        payloads["failure.json"] = encoded(failure)
    output_files = {}
    if (output/"supported_body_installed.xml").exists():
        output_files["supported_body_installed.xml"] = identity(env._installed_xml)
    for name, data in payloads.items():
        (output/name).write_bytes(data)
        output_files[name] = identity(data)
    (output/"manifest.json").write_bytes(encoded({"schema_version": 1, "status": status, "files": output_files, **FLAGS}))
    print(json.dumps(safe({"status": status, "output": str(output), "cost": dict(cost), "stop": stop,
                          "engineering_qualification_passed": metrics["engineering_qualification_passed"],
                          "failure": failure and {key: failure[key] for key in ("type", "message")}, **FLAGS}), allow_nan=False))
    return 0 if failure is None else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".")
    parser.add_argument("--output", required=True)
    parser.add_argument("--source-commit")
    parser.add_argument("--self-check", action="store_true")
    args = parser.parse_args()
    if not args.self_check and not args.source_commit:
        parser.error("--source-commit required for first formal engineering run")
    raise SystemExit(main_run(args))
