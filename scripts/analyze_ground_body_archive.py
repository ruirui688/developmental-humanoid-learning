"""Describe action excitation and passive-response controls without fitting."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path

import numpy as np


def analyze(archive: Path) -> dict[str, object]:
    metadata = json.loads((archive / "metadata.json").read_text(encoding="utf-8"))
    if not metadata["complete"] or metadata["archive_status"] != "complete":
        raise ValueError("analysis requires a completed archive")
    trials = json.loads((archive / "trials.json").read_text(encoding="utf-8"))
    rows = {t["trial_id"]: [] for t in trials}
    with gzip.open(archive / "trace.jsonl.gz", "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if row["invalid_numeric_fields"]:
                raise ValueError("nonfinite rows require a separate failure analysis")
            rows[row["trial_id"]].append(row)
    by_pose = []
    for pose in metadata["poses"]:
        groups = {mode: [t for t in trials if t["pose"] == pose and t["mode"] == mode]
                  for mode in ("zero_torque", "smooth_random")}
        paired_rms = []
        paired_per_joint = []
        for seed in metadata["seeds"]:
            first = rows[f"{pose}_seed{seed}_smooth_random"]
            second = rows[f"{pose}_seed{seed}_zero_torque"]
            if len(first) != len(second):
                raise ValueError("unequal trajectory lengths require explicit censoring")
            active = np.array([r["observation_after"]["joint_position"] for r in first])
            passive = np.array([r["observation_after"]["joint_position"] for r in second])
            paired_per_joint.append(np.sqrt(np.mean((active - passive) ** 2, axis=0)))
            paired_rms.append(float(np.sqrt(np.mean((active - passive) ** 2))))
        by_pose.append({
            "pose": pose,
            "zero_torque_joint_excursion_rms_rad_mean": float(np.mean([t["joint_excursion_rms_rad"] for t in groups["zero_torque"]])),
            "smooth_random_joint_excursion_rms_rad_mean": float(np.mean([t["joint_excursion_rms_rad"] for t in groups["smooth_random"]])),
            "paired_trajectory_difference_rms_rad_mean": float(np.mean(paired_rms)),
            "paired_trajectory_difference_rms_rad_by_joint": np.mean(paired_per_joint, axis=0).tolist(),
            "paired_values_by_seed": dict(zip(map(str, metadata["seeds"]), paired_rms)),
        })
    active_rows = [r for t in trials if t["mode"] == "smooth_random" for r in rows[t["trial_id"]]]
    active_commands = np.array([r["diagnostics"]["accepted_torque"] for r in active_rows])
    actual_substeps = []
    blocked_by_joint = np.zeros(8, dtype=int)
    for row, command in zip(active_rows, active_commands):
        applied = np.array(row["diagnostics"]["applied_torque_history"])
        actual_substeps.extend(applied)
        blocked_by_joint += np.sum(applied != command[None, :], axis=0)
    actual_substeps = np.array(actual_substeps)
    return {
        "source_commit": metadata["source_commit"],
        "analysis_script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "input_sha256": {name: hashlib.sha256((archive / name).read_bytes()).hexdigest()
                         for name in ("metadata.json", "trials.json", "trace.jsonl.gz")},
        "analysis_type": "descriptive statistics only; no model fitting or policy updates",
        "joint_order": ["left_shoulder", "left_elbow", "right_shoulder", "right_elbow", "left_hip", "left_knee", "right_hip", "right_knee"],
        "by_pose": by_pose,
        "exploration_control_steps": len(active_rows),
        "exploration_physics_steps": len(actual_substeps),
        "exploration_command_rms_nm_by_joint": np.sqrt(np.mean(active_commands ** 2, axis=0)).tolist(),
        "exploration_applied_torque_rms_nm_by_joint": np.sqrt(np.mean(actual_substeps ** 2, axis=0)).tolist(),
        "exploration_blocked_substep_fraction_by_joint": (blocked_by_joint / len(actual_substeps)).tolist(),
        "exploration_substeps_with_any_limit_guard": sum(t["guarded_physics_substeps"] for t in trials),
        "exploration_control_steps_with_intervention": sum(t["command_intervention_steps"] for t in trials),
        "peak_ground_normal_force_n": max(t["peak_ground_normal_force_n"] for t in trials),
        "peak_joint_speed_rad_s": max(t["peak_joint_speed_rad_s"] for t in trials),
        "peak_actuator_torque_nm": max(t["peak_actuator_torque_nm"] for t in trials),
        "minimum_contact_distance_m": min(t["minimum_contact_distance_m"] for t in trials),
        "claim_boundary": "Paired motion differences show response under these fixed exploratory commands; they do not establish identifiability, learning, competence or safety. Contact force peaks are sampled at control endpoints, not maxima over all physical substeps.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = analyze(args.archive)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("exploration_control_steps", "exploration_physics_steps", "peak_ground_normal_force_n", "exploration_substeps_with_any_limit_guard")}, indent=2))


if __name__ == "__main__":
    main()
