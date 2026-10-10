"""Read-only, zero-fitting contact/prefix and applied-action diagnostics.

The JSON output must be outside the input archive. Every trial and seed stays in
the report, including stopped, invalid and missing runs. Contact grouping uses
control endpoints only and has no causal or stable-contact interpretation.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import gzip
import hashlib
import json
from pathlib import Path
import platform
import sys

import numpy as np


JOINT_NAMES = (
    "left_shoulder", "left_elbow", "right_shoulder", "right_elbow",
    "left_hip", "left_knee", "right_hip", "right_knee",
)
DEFAULT_REFERENCE = Path(__file__).resolve().parents[1] / "results/cpu_validation/2026-10-10_ground_impacts"


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def read_rows(folder):
    groups = defaultdict(list)
    with gzip.open(folder / "trace.jsonl.gz", "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            groups[row["trial_id"]].append(row)
    return groups


def finite_array(value, shape=None):
    # numpy converts JSON null to NaN; explicitly reject it as a measurement.
    result = np.asarray(value, dtype=float)
    if not np.isfinite(result).all() or (shape is not None and result.shape != shape):
        raise ValueError(f"invalid measurement array, expected shape {shape}")
    return result


def rms(values):
    return np.sqrt(np.mean(np.square(values), axis=0)).tolist() if len(values) else None


def scalar_rms(values):
    return float(np.sqrt(np.mean(np.square(values)))) if len(values) else None


def action_metrics(rows, physics_dt):
    """Use actual executed substeps, including partial-stop steps, as exposure."""
    requested, applied, increments = [], [], []
    for row in rows:
        diagnostic = row["diagnostics"]
        n = diagnostic["executed_substeps"]
        command = finite_array(diagnostic["requested_torque"], (8,))
        history = finite_array(diagnostic["applied_torque_history"])
        if n == 0 and history.size == 0:
            history = history.reshape(0, 8)
        if history.shape != (n, 8):
            raise ValueError("applied history does not match executed substeps")
        requested.extend(np.tile(command, (n, 1)))
        applied.extend(history)
        increments.append(finite_array(row["observation_after"]["joint_position"], (8,))
                          - finite_array(row["observation_before"]["joint_position"], (8,)))
    requested = np.asarray(requested, dtype=float).reshape(-1, 8)
    applied = np.asarray(applied, dtype=float).reshape(-1, 8)
    nonzero = requested != 0.
    blocked = nonzero & (applied == 0.)
    denominator = np.sum(nonzero, axis=0)
    blocked_count = np.sum(blocked, axis=0)
    return {
        "control_rows": len(rows), "executed_physics_substeps": len(applied),
        "executed_seconds": len(applied) * physics_dt,
        "requested_torque_rms_nm_per_joint": rms(requested),
        "applied_torque_rms_nm_per_joint": rms(applied),
        "applied_torque_rms_nm_all_joints": scalar_rms(applied),
        "requested_signed_torque_integral_nms_per_joint": (np.sum(requested, axis=0) * physics_dt).tolist(),
        "applied_signed_torque_integral_nms_per_joint": (np.sum(applied, axis=0) * physics_dt).tolist(),
        "requested_absolute_torque_integral_nms_per_joint": (np.sum(np.abs(requested), axis=0) * physics_dt).tolist(),
        "applied_absolute_torque_integral_nms_per_joint": (np.sum(np.abs(applied), axis=0) * physics_dt).tolist(),
        "nonzero_requested_substeps_per_joint": denominator.tolist(),
        "blocked_nonzero_request_substeps_per_joint": blocked_count.tolist(),
        "blocked_fraction_of_nonzero_requested_substeps_per_joint": [
            None if count == 0 else float(blocked_count[j] / count) for j, count in enumerate(denominator)
        ],
        "blocked_fraction_of_all_executed_substeps_per_joint": (
            (blocked_count / len(applied)).tolist() if len(applied) else None
        ),
        "native_position_step_increment_rms_rad_per_joint": rms(increments),
        "native_position_step_increment_rms_rad_all_joints": scalar_rms(increments),
        "denominator_note": "RMS and torque integrals use executed physics substeps, not requested control calls. Blocking means a nonzero request with an exactly zero applied command; it is not the fraction of all joint commands and does not identify a cause. Position increments use native control-endpoint encoders.",
    }


def substep_metrics(rows, physics_dt):
    force, energy, distance, times = [], [], [], []
    for row in rows:
        diagnostic = row["diagnostics"]
        n = diagnostic["executed_substeps"]
        f = finite_array(diagnostic["substep_ground_normal_forces"], (n,))
        e = finite_array(diagnostic["substep_kinetic_energies"], (n,))
        d = finite_array(diagnostic["substep_minimum_contact_distances"], (n,))
        if np.any(f < 0) or np.any(e < 0):
            raise ValueError("negative ground normal force or kinetic energy")
        np.testing.assert_allclose(np.sum(f) * physics_dt, diagnostic["ground_normal_impulse_ns"], atol=1e-10, rtol=1e-12)
        if (max(f, default=0.) != diagnostic["peak_substep_ground_normal_force"]
                or max(e, default=0.) != diagnostic["peak_substep_kinetic_energy"]
                or min(d, default=0.) != diagnostic["minimum_substep_contact_distance"]):
            raise ValueError("substep scalar summaries disagree with stored samples")
        force.extend(f)
        energy.extend(e)
        distance.extend(d)
        times.extend(diagnostic["time"] - np.arange(n - 1, -1, -1) * physics_dt)
    if not force:
        return {"physics_samples": 0, "peak_ground_normal_force_n": None,
                "ground_normal_impulse_ns": None, "peak_kinetic_energy_j": None,
                "minimum_contact_distance_m": None, "peak_force_time_seconds": None}
    index = int(np.argmax(force))
    return {
        "physics_samples": len(force), "peak_ground_normal_force_n": float(force[index]),
        "peak_force_time_seconds": float(times[index]),
        "ground_normal_impulse_ns": float(np.sum(force) * physics_dt),
        "peak_kinetic_energy_j": float(max(energy)),
        "minimum_contact_distance_m": float(min(distance)),
    }


def prefix_endpoint(rows, prefix_steps):
    if prefix_steps == 0 and rows:
        observation = rows[0]["observation_before"]
        return {
            "available": True, "control_steps": 0, "time_seconds": 0.,
            "kinetic_energy_j": 0.,
            "joint_speed_rad_s_per_joint": finite_array(observation["joint_velocity"], (8,)).tolist(),
            "maximum_joint_speed_rad_s": float(np.max(np.abs(observation["joint_velocity"]))),
            "native_gyro_rad_s": finite_array(observation["imu_gyro"], (3,)).tolist(),
            "native_gyro_norm_rad_s": float(np.linalg.norm(observation["imu_gyro"])),
            "measurement_note": "No prefix: the collector resets all generalized velocities to zero. KE=0 is a declared initial condition; joint speed and gyro are the first native observation before action.",
            "stability_decision": None,
        }
    if len(rows) < prefix_steps or prefix_steps == 0:
        return {"available": False, "missing_reason": "prefix endpoint not reached", "stability_decision": None}
    row = rows[prefix_steps - 1]
    observation = row["observation_after"]
    return {
        "available": True, "control_steps": prefix_steps,
        "time_seconds": row["diagnostics"]["time"],
        "kinetic_energy_j": row["diagnostics"]["kinetic_energy"],
        "joint_speed_rad_s_per_joint": finite_array(observation["joint_velocity"], (8,)).tolist(),
        "maximum_joint_speed_rad_s": float(np.max(np.abs(observation["joint_velocity"]))),
        "native_gyro_rad_s": finite_array(observation["imu_gyro"], (3,)).tolist(),
        "native_gyro_norm_rad_s": float(np.linalg.norm(observation["imu_gyro"])),
        "measurement_note": "Fixed-duration zero command prefix, fully charged to interaction budget. These endpoint values do not assert stable contact or settled dynamics.",
        "stability_decision": None,
    }


def summarize_trial(trial, raw_rows, metadata, shared_steps):
    result = {key: trial.get(key) for key in (
        "trial_id", "contact_profile", "prefix_steps", "pose", "seed", "mode",
        "status", "terminated", "reason", "control_steps", "control_calls_attempted",
        "physics_steps", "reset_seed", "exploration_seed",
        "prefix_control_calls_attempted", "exploration_control_calls_attempted",
        "prefix_control_steps", "prefix_physics_steps", "exploration_control_steps", "exploration_physics_steps",
    )}
    result["trace_rows"] = len(raw_rows)
    rows = [row for row in raw_rows if "collector_exception" not in row]
    invalid = [i for i, row in enumerate(raw_rows) if row.get("invalid_numeric_fields")]
    result["invalid_trace_row_indices"] = invalid
    result["collector_exception_rows"] = len(raw_rows) - len(rows)
    result["metrics_available"] = False
    try:
        if invalid or trial.get("invalid_numeric_fields"):
            raise ValueError("invalid numeric values retained in raw archive")
        if result["collector_exception_rows"]:
            raise ValueError("collector exception retained: an interrupted control call may have executed physics without storing every substep; whole-trial diagnostics are missing, budget retained")
        prefix_steps = trial["prefix_steps"]
        if not rows:
            raise ValueError("no recorded control rows; diagnostic metrics are missing")
        if len(rows) != trial["control_steps"]:
            raise ValueError("trial control-step count differs from trace")
        for index, row in enumerate(rows):
            if row["contact_profile"] != trial["contact_profile"] or row["prefix_steps"] != prefix_steps:
                raise ValueError("trial identity differs from trace")
            expected_phase = "prefix" if index < prefix_steps else "exploration"
            expected_action = None if expected_phase == "prefix" else index - prefix_steps
            if row["phase"] != expected_phase or row["action_index"] != expected_action:
                raise ValueError("phase/action index does not match fixed prefix")
            if expected_phase == "prefix" and np.any(finite_array(row["diagnostics"]["requested_torque"], (8,)) != 0):
                raise ValueError("nonzero requested command in zero prefix")
        physics_dt = metadata["config"]["physics_dt"]
        active = [row for row in rows if row["phase"] == "exploration"]
        result.update({
            "metrics_available": True, "missing_reason": None,
            "planned_prefix_steps": prefix_steps, "executed_prefix_steps": min(len(rows), prefix_steps),
            "planned_active_steps": metadata["steps_per_trial_limit"] - prefix_steps,
            "executed_active_steps": len(active),
            "whole_trial": substep_metrics(rows, physics_dt),
            "prefix_phase": substep_metrics(rows[:prefix_steps], physics_dt),
            "active_phase": substep_metrics(active, physics_dt),
            "prefix_endpoint": prefix_endpoint(rows, prefix_steps),
            "active_action_metrics": action_metrics(active, physics_dt),
            "shared_active_window": {
                "requested_control_steps": shared_steps, "available_control_steps": min(shared_steps, len(active)),
                "complete": len(active) >= shared_steps,
                "action_metrics": action_metrics(active[:shared_steps], physics_dt),
                "substep_metrics": substep_metrics(active[:shared_steps], physics_dt),
            },
            "contact_endpoint_groups": [],
        })
        for count in sorted({row["diagnostics"]["ground_contact_count"] for row in active}):
            group = [row for row in active if row["diagnostics"]["ground_contact_count"] == count]
            result["contact_endpoint_groups"].append({
                "endpoint_ground_contact_count": count,
                "action_metrics": action_metrics(group, physics_dt),
            })
    except (ValueError, KeyError, TypeError, AssertionError) as error:
        result["metrics_available"] = False
        result["missing_reason"] = f"{type(error).__name__}: {error}"
    return result


def paired_response(random_trial, zero_trial, groups, shared_steps, physics_dt):
    result = {key: random_trial[key] for key in ("contact_profile", "prefix_steps", "pose", "seed")}
    result.update({"random_trial_id": random_trial["trial_id"], "zero_trial_id": zero_trial["trial_id"],
                   "requested_shared_active_steps": shared_steps, "complete": False})
    if not random_trial["metrics_available"] or not zero_trial["metrics_available"]:
        result["missing_reason"] = "paired trial has invalid/missing diagnostic metrics"
        return result
    active = [[row for row in groups[t["trial_id"]] if row.get("phase") == "exploration"
               and "collector_exception" not in row] for t in (random_trial, zero_trial)]
    n = min(shared_steps, *(len(rows) for rows in active))
    result["available_shared_active_steps"] = n
    result["random_total_active_steps"] = len(active[0])
    result["zero_total_active_steps"] = len(active[1])
    if n < shared_steps:
        result["missing_reason"] = "fewer than the frozen shared number of active commands"
        return result
    a, b = (rows[:shared_steps] for rows in active)
    if any(row["action_index"] != index for rows in (a, b) for index, row in enumerate(rows)):
        result["missing_reason"] = "active action indices do not align"
        return result
    differences = [finite_array(x["observation_after"]["joint_position"], (8,))
                   - finite_array(y["observation_after"]["joint_position"], (8,)) for x, y in zip(a, b)]
    result.update({
        "complete": True, "missing_reason": None,
        "native_position_trajectory_difference_rms_rad_per_joint": rms(differences),
        "native_position_trajectory_difference_rms_rad_all_joints": scalar_rms(differences),
        "random_shared_action_metrics": action_metrics(a, physics_dt),
        "zero_shared_action_metrics": action_metrics(b, physics_dt),
        "random_shared_substep_metrics": substep_metrics(a, physics_dt),
        "zero_shared_substep_metrics": substep_metrics(b, physics_dt),
    })
    return result


def matched_effect(left, right, kind):
    result = {"comparison": kind, "left_trial_id": left["trial_id"], "right_trial_id": right["trial_id"],
              "pose": left["pose"], "seed": left["seed"], "mode": left["mode"],
              "left_contact_profile": left["contact_profile"], "right_contact_profile": right["contact_profile"],
              "left_prefix_steps": left["prefix_steps"], "right_prefix_steps": right["prefix_steps"],
              "available": left["metrics_available"] and right["metrics_available"]}
    if not result["available"]:
        result["missing_reason"] = "matched trial has invalid/missing metrics"
        return result
    keys = ("peak_ground_normal_force_n", "ground_normal_impulse_ns", "peak_kinetic_energy_j", "minimum_contact_distance_m")
    result["whole_trial_right_minus_left"] = {
        key: None if left["whole_trial"][key] is None or right["whole_trial"][key] is None
        else right["whole_trial"][key] - left["whole_trial"][key] for key in keys
    }
    result["shared_active_window_complete"] = left["shared_active_window"]["complete"] and right["shared_active_window"]["complete"]
    result["shared_active_applied_torque_rms_nm_right_minus_left_per_joint"] = None
    if result["shared_active_window_complete"]:
        result["shared_active_applied_torque_rms_nm_right_minus_left_per_joint"] = (
            np.asarray(right["shared_active_window"]["action_metrics"]["applied_torque_rms_nm_per_joint"])
            - left["shared_active_window"]["action_metrics"]["applied_torque_rms_nm_per_joint"]
        ).tolist()
        result["shared_active_right_minus_left"] = {
            key: right["shared_active_window"]["substep_metrics"][key] - left["shared_active_window"]["substep_metrics"][key]
            for key in keys
        }
    return result


def reference_replay(trials, groups, reference):
    old_groups = read_rows(reference)
    result = {"reference_path": str(reference.resolve()), "matched_trials": 0, "matched_control_rows": 0,
              "exact": True, "missing_trial_ids": [], "differences": []}
    for trial in trials:
        if trial["contact_profile"] != "baseline" or trial["prefix_steps"] != 0:
            continue
        old_id = f"{trial['pose']}_seed{trial['seed']}_{trial['mode']}"
        rows, original = groups.get(trial["trial_id"], []), old_groups.get(old_id, [])
        if not original or len(rows) != len(original):
            result["missing_trial_ids"].append(trial["trial_id"])
            result["exact"] = False
            continue
        result["matched_trials"] += 1
        for index, (row, old) in enumerate(zip(rows, original)):
            result["matched_control_rows"] += 1
            for key in ("qpos", "qvel", "observation_before", "observation_after"):
                if row.get(key) != old.get(key):
                    result["exact"] = False
                    result["differences"].append({"trial_id": trial["trial_id"], "control_index": index, "field": key})
            for key, value in old.get("diagnostics", {}).items():
                if row.get("diagnostics", {}).get(key) != value:
                    result["exact"] = False
                    result["differences"].append({"trial_id": trial["trial_id"], "control_index": index, "field": "diagnostics/" + key})
    return result


def prefix_invariance(raw_trials, by_case, groups, shared_steps):
    """Audit repeated passive trajectories and unconsumed exploration streams."""
    raw_by_id = {trial["trial_id"]: trial for trial in raw_trials}
    zero_checks, random_checks = [], []
    for key, first in by_case.items():
        contact, prefix, pose, seed, mode = key
        if prefix != 0:
            continue
        second = by_case.get((contact, 100, pose, seed, mode))
        if second is None:
            continue
        result = {"contact_profile": contact, "pose": pose, "seed": seed,
                  "prefix0_trial_id": first["trial_id"], "prefix100_trial_id": second["trial_id"],
                  "exact": True, "available": first["metrics_available"] and second["metrics_available"],
                  "mismatches": []}
        x, y = raw_by_id[first["trial_id"]], raw_by_id[second["trial_id"]]
        for name in ("initial_qpos", "reset_seed", "exploration_seed"):
            if x.get(name) != y.get(name):
                result["exact"] = False
                result["mismatches"].append(name)
        a, b = groups.get(first["trial_id"], []), groups.get(second["trial_id"], [])
        if mode == "zero_torque":
            result["matched_control_rows"] = min(len(a), len(b))
            if len(a) != len(b):
                result["exact"] = False
                result["mismatches"].append("control row count")
            for index, (left, right) in enumerate(zip(a, b)):
                for name in ("qpos", "qvel", "observation_before", "observation_after", "diagnostics"):
                    if left.get(name) != right.get(name):
                        result["exact"] = False
                        result["mismatches"].append(f"row {index}: {name}")
            result["sample_note"] = "Prefix labels do not alter zero-torque runs. Identical repeated trajectories are not independent samples. Both executions remain charged to the budget."
            zero_checks.append(result)
        else:
            a, b = ([row for row in rows if row.get("phase") == "exploration"
                     and "collector_exception" not in row][:shared_steps] for rows in (a, b))
            result["matched_active_request_rows"] = min(len(a), len(b))
            result["available"] = result["available"] and len(a) == len(b) == shared_steps
            for index, (left, right) in enumerate(zip(a, b)):
                if left["diagnostics"]["requested_torque"] != right["diagnostics"]["requested_torque"]:
                    result["exact"] = False
                    result["mismatches"].append(f"active request {index}")
            random_checks.append(result)
    return {
        "zero_prefix_duplicate_trajectory_checks": zero_checks,
        "random_prefix_shared_request_checks": random_checks,
        "all_available_and_exact": bool(zero_checks and random_checks) and all(
            row["available"] and row["exact"] for row in zero_checks + random_checks
        ),
    }


def analyze(folder, reference=DEFAULT_REFERENCE, shared_steps=150):
    if type(shared_steps) is not int or shared_steps < 1:
        raise ValueError("shared active steps must be a positive integer")
    metadata = read_json(folder / "metadata.json")
    raw_trials = read_json(folder / "trials.json")
    groups = read_rows(folder)
    summaries = [summarize_trial(trial, groups.get(trial["trial_id"], []), metadata, shared_steps) for trial in raw_trials]
    by_case = {(t["contact_profile"], t["prefix_steps"], t["pose"], t["seed"], t["mode"]): t for t in summaries}
    responses, contact_effects, prefix_effects, missing = [], [], [], []
    physics_dt = metadata["config"]["physics_dt"]
    contacts, prefixes = ("baseline", "compliant"), (0, 100)
    for contact in contacts:
        for prefix in prefixes:
            for pose in metadata["poses"]:
                for seed in metadata["seeds"]:
                    for mode in ("zero_torque", "smooth_random"):
                        key = (contact, prefix, pose, seed, mode)
                        if key not in by_case:
                            missing.append(f"{contact}_prefix{prefix}_{pose}_seed{seed}_{mode}")
                    pair = [by_case.get((contact, prefix, pose, seed, mode)) for mode in ("smooth_random", "zero_torque")]
                    if all(pair):
                        responses.append(paired_response(*pair, groups, shared_steps, physics_dt))
    for trial in summaries:
        if trial["contact_profile"] == "baseline":
            partner = by_case.get(("compliant", trial["prefix_steps"], trial["pose"], trial["seed"], trial["mode"]))
            if partner:
                contact_effects.append(matched_effect(trial, partner, "compliant minus baseline, same prefix/pose/seed/mode"))
        if trial["prefix_steps"] == 0:
            partner = by_case.get((trial["contact_profile"], 100, trial["pose"], trial["seed"], trial["mode"]))
            if partner:
                prefix_effects.append(matched_effect(trial, partner, "prefix100 minus prefix0, same contact/pose/seed/mode"))
    paths = [folder / name for name in ("metadata.json", "trials.json", "trace.jsonl.gz", "source_snapshot.zip")]
    paths.extend(reference / name for name in ("metadata.json", "trials.json", "trace.jsonl.gz"))
    return {
        "schema_version": 1, "analysis_type": "CPU fixed-contact/fixed-prefix descriptive analysis; zero fitting",
        "source_commit": metadata["source_commit"], "source_dirty": metadata["source_dirty"],
        "analysis_script_sha256": sha256(Path(__file__)),
        "input_sha256": {str(path.resolve()): sha256(path) for path in paths},
        "analysis_runtime": {"python": sys.version, "numpy": np.__version__, "platform": platform.platform()},
        "joint_order": list(JOINT_NAMES), "physics_dt_seconds": physics_dt,
        "planned_control_steps_per_trial": metadata["steps_per_trial_limit"],
        "nominal_control_dt_seconds": physics_dt * metadata["config"]["control_substeps"],
        "shared_active_steps": shared_steps, "archive_complete": metadata["complete"],
        "trial_count": len(summaries), "expected_trial_count": metadata["expected_trial_count"],
        "missing_trial_ids": missing,
        "orphan_trace_trial_ids": sorted(set(groups) - {t["trial_id"] for t in raw_trials}),
        "metrics_unavailable_trial_ids": [t["trial_id"] for t in summaries if not t["metrics_available"]],
        "terminated_trial_ids": [t["trial_id"] for t in summaries if t["terminated"]],
        "budget": {key: metadata.get(key) for key in (
            "control_steps", "control_calls_attempted", "physics_steps", "wall_seconds",
            "prefix_control_calls_attempted", "exploration_control_calls_attempted",
            "prefix_control_steps", "prefix_physics_steps", "exploration_control_steps", "exploration_physics_steps",
        )},
        "parameter_updates": metadata["parameter_updates"], "analysis_parameter_updates": 0,
        "trials": summaries, "paired_active_responses": responses,
        "matched_contact_effects": contact_effects, "matched_prefix_effects": prefix_effects,
        "prefix_invariance": prefix_invariance(raw_trials, by_case, groups, shared_steps),
        "baseline_prefix0_reference_replay": reference_replay(summaries, groups, reference),
        "contact_endpoint_grouping_note": "All executed substeps in a control row are grouped by that row's endpoint ground_contact_count. The count can change inside the row; groups do not establish a persistent contact pattern or isolate a causal contact effect.",
        "claim_boundary": "Descriptive fixed-action simulation only. No learning or inferred body model. Soft-contact and passive-prefix benefits belong to initial/environment conditions. Prefix0 has 250 active commands and prefix100 has 150 within the same 250-step total; paired response comparisons use the first shared 150 active commands. Ground normal-force integral includes sustained support. Samples every 2 ms do not bound continuous-time impact or hardware safety. Contact-count grouping uses a control endpoint and is neither a stable contact state nor a causal intervention. No significance tests or stability thresholds are used; all seeds and failures remain visible.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--reference", type=Path, default=DEFAULT_REFERENCE)
    parser.add_argument("--shared-active-steps", type=int, default=150)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if any(args.output.resolve().is_relative_to(path.resolve()) for path in (args.archive, args.reference)):
        parser.error("analysis output must be outside both read-only input and reference archives")
    if args.output.exists():
        parser.error("output already exists; preserve existing analysis")
    result = analyze(args.archive, args.reference, args.shared_active_steps)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({key: result[key] for key in (
        "trial_count", "missing_trial_ids", "metrics_unavailable_trial_ids", "terminated_trial_ids",
        "budget", "parameter_updates", "baseline_prefix0_reference_replay",
    )}, indent=2))


if __name__ == "__main__":
    main()
