"""Reproduce the independent, standard-library-only ground-body archive audit.

This checks recorded bytes, transitions, and accounting. It never imports the
project, calls a simulator/planner, regenerates random actions, or fits parameters.
The output must be outside both audited archives to preserve their input bytes.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import gzip
import hashlib
import json
import math
from pathlib import Path
import subprocess
import zipfile


def audit(archive: Path, prior: Path) -> dict:
    root = Path(__file__).resolve().parents[1]
    metadata = json.loads((archive / "metadata.json").read_text(encoding="utf-8"))
    trials = json.loads((archive / "trials.json").read_text(encoding="utf-8"))
    geometry = json.loads((archive / "geometry.json").read_text(encoding="utf-8"))
    manifest = json.loads((archive / "manifest.json").read_text(encoding="utf-8"))
    violations = []
    checks = finite_numbers = 0
    max_numeric_error = 0.0

    def check(condition, name, detail=None):
        nonlocal checks
        checks += 1
        if not condition:
            violations.append({"check": name, "detail": detail})

    def near(actual, expected, name, detail=None, tolerance=1e-11):
        nonlocal max_numeric_error
        error = abs(actual - expected)
        max_numeric_error = max(max_numeric_error, error)
        check(error <= tolerance, name, {
            "detail": detail, "actual": actual, "expected": expected, "error": error,
        })

    def finite(value, path):
        nonlocal finite_numbers
        if isinstance(value, float):
            finite_numbers += 1
            check(math.isfinite(value), "finite_number", path)
        elif isinstance(value, dict):
            for key, item in value.items():
                finite(item, path + "/" + str(key))
        elif isinstance(value, list):
            for index, item in enumerate(value):
                finite(item, path + "/" + str(index))

    def sha(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()

    manifest_digest = sha(archive / "manifest.json")
    for name, digest in manifest.items():
        check(sha(archive / name) == digest, "manifest_sha256", name)
    # An older manifest may cover only the original collector outputs. Report
    # that exact coverage; later audit/plot/statistic artifacts are not implied.
    unlisted = sorted(
        p.name for p in archive.iterdir()
        if p.is_file() and p.name != "manifest.json" and p.name not in manifest
    )
    source_checks = []
    with zipfile.ZipFile(archive / "source_snapshot.zip") as snapshot:
        check(set(snapshot.namelist()) == set(metadata["source_sha256"]), "snapshot_member_set")
        for name, digest in metadata["source_sha256"].items():
            data = snapshot.read(name)
            blob = subprocess.check_output(
                ["git", "show", metadata["source_commit"] + ":" + name], cwd=root,
            )
            raw_match = hashlib.sha256(data).hexdigest() == digest
            commit_match = data == blob
            check(raw_match, "snapshot_raw_sha256", name)
            check(commit_match, "snapshot_git_blob_raw_bytes", name)
            source_checks.append({
                "path": name, "raw_sha256_match": raw_match,
                "git_blob_raw_bytes_match": commit_match,
            })
    check(metadata["asset_sha256"] == metadata["source_sha256"]["src/developmental_physics/assets/ground_body.xml"], "asset_identity")
    check(metadata["source_dirty"] is False and metadata["source_status"] == "", "clean_source_record")
    check(metadata["complete"] is True and metadata["archive_status"] == "complete", "archive_complete")
    check(metadata["parameter_updates"] == {"model": 0, "policy": 0, "gate": 0}, "zero_parameter_updates_record")
    check(metadata["teacher_calls"] == 0 and metadata["external_demonstration_samples"] == 0, "zero_teacher_records")
    check(metadata["gpu"] is None and metadata["renderer"] is None, "cpu_renderer_records")
    finite(metadata, "metadata")
    finite(trials, "trials")
    finite(geometry, "geometry")
    check(len(trials) == metadata["trial_count"] == metadata["expected_trial_count"] == 24, "trial_count")
    trial_by_id = {trial["trial_id"]: trial for trial in trials}
    check(len(trial_by_id) == len(trials), "unique_trial_ids")
    expected_ids = {
        f"{pose}_seed{seed}_{mode}"
        for pose in metadata["poses"] for seed in metadata["seeds"]
        for mode in ("zero_torque", "smooth_random")
    }
    check(set(trial_by_id) == expected_ids, "full_factorial_ids")
    rows_by_trial = defaultdict(list)
    row_count = 0
    with gzip.open(archive / "trace.jsonl.gz", "rt", encoding="utf-8") as trace:
        for line in trace:
            row = json.loads(line)
            row_count += 1
            finite(row, f"trace/{row_count}")
            check(row.get("invalid_numeric_fields") == [], "no_invalid_trace_markers", row_count)
            check("collector_exception" not in row, "no_exception_trace", row_count)
            rows_by_trial[row["trial_id"]].append(row)
    check(row_count == 6000 == metadata["control_steps"], "trace_row_count")
    check(set(rows_by_trial) == expected_ids, "trace_trial_set")
    shapes = {
        "joint_position": 8, "joint_velocity": 8, "imu_gyro": 3,
        "imu_acceleration": 3, "actuator_torque": 8, "previous_command": 8,
    }
    limit = metadata["config"]["torque_limit"]
    dt = metadata["config"]["physics_dt"]
    substeps = metadata["config"]["control_substeps"]
    all_ground_steps = all_guarded = all_interventions = all_physics = 0
    per_trial = []
    for tid, trial in trial_by_id.items():
        rows = rows_by_trial[tid]
        check(len(rows) == trial["control_steps"] == trial["metric_samples"] == 250, "trial_rows", tid)
        check(trial["control_calls_attempted"] == len(rows), "trial_calls", tid)
        check(trial["status"] == "completed" and not trial["terminated"] and trial["reason"] is None and trial["collector_exception"] is None, "successful_trial_record", tid)
        check(trial["invalid_numeric_fields"] == [], "no_invalid_trial_markers", tid)
        check(trial["reset_seed"] != trial["exploration_seed"], "independent_stream_seed_ids", tid)
        check(trial["environment_fingerprint_before"] == trial["environment_fingerprint_after"], "environment_fingerprint_unchanged", tid)
        check(trial["explorer_fingerprint_before"] == trial["explorer_fingerprint_after"], "explorer_fingerprint_unchanged", tid)
        check(trial["model_updates"] == trial["policy_updates"] == trial["gate_updates"] == 0, "trial_no_update_records", tid)
        initial = trial["initial_qpos"]
        check(len(initial) == 15, "initial_qpos_shape", tid)
        check(rows[0]["observation_before"]["joint_position"] == initial[7:], "first_observation_initial_state", tid)
        check(rows[0]["observation_before"]["joint_velocity"] == [0.0] * 8, "zero_initial_joint_velocity", tid)
        check(rows[0]["observation_before"]["previous_command"] == [0.0] * 8, "zero_initial_command", tid)
        check(initial[2] < .6 and abs(initial[3]) < .8, "ground_non_upright_initial_record", tid)
        squared = 0.0
        speed_peak = torque_peak = force_peak = energy_peak = minimum_distance = 0.0
        ground_steps = guarded_steps = interventions = physical = 0
        previous_time = 0.0
        for index, row in enumerate(rows, 1):
            d = row["diagnostics"]
            before, after = row["observation_before"], row["observation_after"]
            for label, obs in (("before", before), ("after", after)):
                check(set(obs) == set(shapes), "native_observation_key_boundary", [tid, index, label])
                for key, size in shapes.items():
                    check(isinstance(obs[key], list) and len(obs[key]) == size and all(isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) for x in obs[key]), "native_observation_shape_finite", [tid, index, label, key])
            if index > 1:
                check(before == rows[index - 2]["observation_after"], "continuous_native_transition_no_reset", [tid, index])
            check(d["step_id"] == index, "step_sequence", [tid, index])
            check(d["executed_substeps"] == substeps, "executed_substeps", [tid, index])
            physical += d["executed_substeps"]
            check(d["physics_steps"] == physical, "physics_step_accumulation", [tid, index])
            check(d["time"] > previous_time, "monotonic_time", [tid, index])
            near(d["time"] - previous_time, dt * d["executed_substeps"], "substep_time_delta", [tid, index], tolerance=2e-12)
            previous_time = d["time"]
            check(not d["terminated"] and d["reason"] is None, "no_trace_stop", [tid, index])
            check(len(row["qpos"]) == 15 and len(row["qvel"]) == 14, "raw_state_shape", [tid, index])
            check(row["qpos"][7:] == after["joint_position"], "joint_positions_raw_match", [tid, index])
            check(row["qvel"][6:] == after["joint_velocity"], "joint_velocities_raw_match", [tid, index])
            check(d["root_position"] == row["qpos"][:3] and d["root_quaternion"] == row["qpos"][3:7], "root_diagnostics_raw_match", [tid, index])
            near(sum(v * v for v in row["qpos"][3:7]), 1.0, "unit_root_quaternion", [tid, index], tolerance=1e-10)
            requested, accepted, applied = d["requested_torque"], d["accepted_torque"], d["applied_torque"]
            history = d["applied_torque_history"]
            for name, torque in [("requested", requested), ("accepted", accepted), ("applied", applied)] + [("substep", a) for a in history]:
                check(len(torque) == 8 and all(math.isfinite(x) and abs(x) <= limit for x in torque), "torque_range", [tid, index, name])
            check(accepted == [min(limit, max(-limit, x)) for x in requested], "accepted_clipping", [tid, index])
            check(after["previous_command"] == accepted, "command_history_endpoint", [tid, index])
            check(len(history) == d["executed_substeps"], "torque_substep_count", [tid, index])
            check(applied == history[-1] and after["actuator_torque"] == applied, "final_substep_and_torque_feedback", [tid, index])
            observed_guards = sum(any(a != b for a, b in zip(action, accepted)) for action in history)
            for action in history:
                check(all(actual == command or actual == 0.0 for actual, command in zip(action, accepted)), "guard_only_blocks_outward_action", [tid, index])
            check(observed_guards == d["guarded_substeps"], "guarded_substep_recompute", [tid, index])
            guarded_steps += observed_guards
            interventions += int(observed_guards > 0 or requested != applied)
            if trial["mode"] == "zero_torque":
                check(requested == [0.0] * 8 and all(a == [0.0] * 8 for a in history), "zero_torque_group_actions", [tid, index])
            check(0 <= d["ground_contact_count"] <= d["contact_count"], "contact_count_bounds", [tid, index])
            check(d["ground_normal_force"] >= 0.0, "nonnegative_normal_force", [tid, index])
            if d["ground_contact_count"] == 0:
                check(d["ground_normal_force"] == 0.0, "no_ground_contact_no_force", [tid, index])
            ground_steps += int(d["ground_contact_count"] > 0)
            speed_peak = max(speed_peak, max(abs(x) for x in after["joint_velocity"]))
            torque_peak = max(torque_peak, max(abs(x) for x in after["actuator_torque"]))
            force_peak = max(force_peak, d["ground_normal_force"])
            energy_peak = max(energy_peak, d["kinetic_energy"])
            minimum_distance = min(minimum_distance, d["minimum_contact_distance"])
            squared += sum((a - b) ** 2 for a, b in zip(after["joint_position"], initial[7:])) / 8.0
        check(rows[-1]["qpos"] == trial["final_qpos"], "final_qpos_match", tid)
        check(physical == trial["physics_steps"] == 2500, "trial_physics_budget", tid)
        near(previous_time, trial["simulated_seconds"], "trial_time_match", tid)
        near(previous_time, 5.0, "trial_duration", tid)
        check(ground_steps == trial["ground_contact_steps"], "contact_summary", tid)
        check(ground_steps > 0 and force_peak > 0.0, "logged_ground_contact_occurred", tid)
        check(guarded_steps == trial["guarded_physics_substeps"], "guard_summary", tid)
        check(interventions == trial["command_intervention_steps"], "intervention_summary", tid)
        for metric, expected in [
            ("joint_excursion_rms_rad", math.sqrt(squared / len(rows))),
            ("peak_joint_speed_rad_s", speed_peak), ("peak_actuator_torque_nm", torque_peak),
            ("peak_ground_normal_force_n", force_peak), ("peak_kinetic_energy_j", energy_peak),
            ("minimum_contact_distance_m", minimum_distance),
        ]:
            near(trial[metric], expected, "recomputed_metric", [tid, metric])
        check(speed_peak <= metadata["config"]["joint_speed_limit"], "logged_speed_within_stop_threshold", tid)
        check(energy_peak <= metadata["config"]["kinetic_energy_limit"], "logged_energy_within_stop_threshold", tid)
        all_ground_steps += ground_steps
        all_guarded += guarded_steps
        all_interventions += interventions
        all_physics += physical
        per_trial.append({
            "trial_id": tid, "trace_rows": len(rows), "physics_steps": physical,
            "ground_contact_steps": ground_steps, "guarded_physics_substeps": guarded_steps,
            "command_intervention_steps": interventions,
        })
    check(all_physics == metadata["physics_steps"] == 60000, "total_physics_budget")
    check(metadata["control_calls_attempted"] == 6000, "total_control_call_budget")
    check(metadata["terminated_trials"] == metadata["exception_trials"] == 0, "total_stop_counts")
    pair_count = 0
    for pose in metadata["poses"]:
        for seed in metadata["seeds"]:
            left = trial_by_id[f"{pose}_seed{seed}_zero_torque"]
            right = trial_by_id[f"{pose}_seed{seed}_smooth_random"]
            check(left["initial_qpos"] == right["initial_qpos"], "paired_identical_initial_qpos", [pose, seed])
            check(rows_by_trial[left["trial_id"]][0]["observation_before"] == rows_by_trial[right["trial_id"]][0]["observation_before"], "paired_identical_initial_observation", [pose, seed])
            check(left["reset_seed"] == right["reset_seed"] and left["exploration_seed"] == right["exploration_seed"], "paired_shared_streams", [pose, seed])
            pair_count += 1
    check(len({t["environment_fingerprint_before"] for t in trials}) == 1, "shared_environment_fingerprint")
    check(len({t["explorer_fingerprint_before"] for t in trials}) == 1, "shared_explorer_parameters")
    check({g["trial_id"] for g in geometry} == expected_ids and len(geometry) == 24, "geometry_trial_set")
    for record in geometry:
        check(record["invalid_numeric_fields"] == [], "geometry_finite_markers", record["trial_id"])
        lowest = min(min(e[2] for e in item["endpoints"]) - item["radius"] for item in record["initial"])
        near(lowest, metadata["config"]["reset_clearance"], "initial_geometry_floor_clearance", record["trial_id"])

    recovery = json.loads((prior / "recovery.json").read_text(encoding="utf-8"))
    prior_manifest = json.loads((prior / "manifest.json").read_text(encoding="utf-8"))
    for name, digest in prior_manifest.items():
        check(sha(prior / name) == digest, "interrupted_archive_manifest_sha256", name)
    prior_rows = 0
    prior_groups = defaultdict(list)
    with gzip.open(prior / "trace.jsonl.gz", "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            prior_rows += 1
            prior_groups[row["trial_id"]].append(row)
    prior_physics = sum(rows[-1]["diagnostics"]["physics_steps"] for rows in prior_groups.values())
    check(prior_rows == recovery["observed_trace_control_steps"] == 2750, "interrupted_extra_control_budget")
    check(prior_physics == recovery["observed_trace_physics_steps"] == 27500, "interrupted_extra_physics_budget")
    check(len(prior_groups) == recovery["observed_trace_trials"] == 11, "interrupted_trace_trial_count")
    prior_trials = json.loads((prior / "trials.json").read_text(encoding="utf-8"))
    check(len(prior_trials) == recovery["saved_trial_summaries"] == 11, "interrupted_saved_trial_count")
    check(recovery["complete"] is False and recovery["archive_status"] == "interrupted_checkpoint_write", "interrupted_not_completed_matrix")
    check(recovery["parameter_updates"] == {"model": 0, "policy": 0, "gate": 0}, "interrupted_no_update_record")

    return {
        "schema_version": 1, "audit_type": "independent_offline_archive_consistency",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "pass" if not violations else "failed",
        "tools": "Python standard library only: JSON/gzip/hashlib/zipfile/math/subprocess git show. No project imports, simulator calls, planner calls, or parameter updates.",
        "auditor_script_sha256": sha(Path(__file__).resolve()),
        "audited_input_manifest_sha256": manifest_digest,
        "audited_input_manifest_entries": manifest,
        "manifest_coverage": {
            "checked_entries": len(manifest), "files_outside_manifest": unlisted,
            "covers_all_nonmanifest_files": not unlisted,
            "scope": "Only explicitly listed entries are verified against the input manifest. Unlisted additions are not claimed covered.",
        },
        "source_commit": metadata["source_commit"], "source_snapshot_members": source_checks,
        "checks": checks, "finite_float_values_checked": finite_numbers,
        "max_recomputed_numeric_difference": max_numeric_error,
        "verified_matrix": {
            "trials": len(trials), "trace_rows": row_count, "physics_steps": all_physics,
            "paired_initial_states": pair_count, "ground_contact_steps": all_ground_steps,
            "guarded_physics_substeps": all_guarded, "command_intervention_steps": all_interventions,
            "terminated_trials": metadata["terminated_trials"], "parameter_updates_record": metadata["parameter_updates"],
        },
        "per_trial": per_trial,
        "budget_ledger": {
            "completed_matrix_control_steps": row_count, "completed_matrix_physics_steps": all_physics,
            "completed_matrix_simulated_seconds": row_count * dt * substeps,
            "interrupted_archive": str(prior.resolve()),
            "interrupted_archive_source_commit": recovery["source_commit"],
            "interrupted_extra_control_steps": prior_rows, "interrupted_extra_physics_steps": prior_physics,
            "interrupted_extra_simulated_seconds": prior_physics * dt,
            "total_collector_control_steps_including_interrupted_attempt": row_count + prior_rows,
            "total_collector_physics_steps_including_interrupted_attempt": all_physics + prior_physics,
            "total_collector_simulated_seconds_including_interrupted_attempt": (all_physics + prior_physics) * dt,
            "scope": "Collector attempts only. Unit tests and other historical diagnostics are separate and not included in these totals.",
        },
        "evidence_boundaries": [
            "This is an archive consistency audit, not an independent physical solver or causal proof of contact dynamics.",
            "Contact diagnostics are logged separately from the native observation schema; trace data alone cannot prove that a solver generated them or establish absence of every possible hidden teacher.",
            "Unchanged fingerprints and recorded zero counters establish internal consistency; this audit does not re-execute program behavior.",
            "Different reset/exploration seed IDs and paired equality are checked; SeedSequence or random commands are not regenerated.",
            "No learned body model, competence development, acquired rolling/standing/walking, biological validity, G1 validity, sample efficiency, or hardware safety claim follows.",
            "The interrupted first attempt is retained as additional interaction budget and a checkpoint-write failure, not a physical dynamics failure or completed matrix.",
            "Force and kinetic-energy extrema are reconstructed only from logged control endpoints; they are not continuous or all-physics-substep peaks.",
        ],
        "violations": violations,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--interrupted-archive", type=Path)
    args = parser.parse_args()
    archive = args.archive.resolve()
    prior = (args.interrupted_archive or archive.with_name(archive.name.removesuffix("_verified"))).resolve()
    output = args.output.resolve()
    if any(output.is_relative_to(path) for path in (archive, prior)):
        parser.error("--output must be outside both audited archives to preserve input files")
    result = audit(archive, prior)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({key: result[key] for key in (
        "status", "checks", "finite_float_values_checked", "max_recomputed_numeric_difference",
        "manifest_coverage", "verified_matrix", "budget_ledger", "violations",
    )}, indent=2))
    if result["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
