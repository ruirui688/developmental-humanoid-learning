"""Independently audit substep impact telemetry with scalar standard-library math.

No project imports, NumPy, simulation, planning, training, or new interactions.
Output must remain outside every audited input directory.
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


def audit(archive: Path, reference: Path, interrupted: Path, base_audit_path: Path) -> dict:
    root = Path(__file__).resolve().parents[1]
    base_audit = json.loads(base_audit_path.read_text(encoding="utf-8"))
    metadata = json.loads((archive / "metadata.json").read_text(encoding="utf-8"))
    old_metadata = json.loads((reference / "metadata.json").read_text(encoding="utf-8"))
    profile = json.loads((archive / "impact_profile.json").read_text(encoding="utf-8"))
    manifest = json.loads((archive / "manifest.json").read_text(encoding="utf-8"))
    checks = scalar_numbers = 0
    max_difference = max_state_difference = 0.0
    violations = []

    def check(condition, name, detail=None):
        nonlocal checks
        checks += 1
        if not condition:
            violations.append({"check": name, "detail": detail})

    def near(actual, expected, name, detail=None, tolerance=1e-10):
        nonlocal max_difference
        difference = abs(actual - expected)
        max_difference = max(max_difference, difference)
        check(difference <= tolerance, name, {
            "detail": detail, "difference": difference,
            "recorded": actual, "recomputed": expected,
        })

    def finite(values, name, detail):
        nonlocal scalar_numbers
        for index, value in enumerate(values):
            scalar_numbers += 1
            check(isinstance(value, (int, float)) and not isinstance(value, bool)
                  and math.isfinite(value), name, [detail, index])

    def sha(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def read_rows(folder):
        with gzip.open(folder / "trace.jsonl.gz", "rt", encoding="utf-8") as stream:
            return [json.loads(line) for line in stream]

    rows, old_rows = read_rows(archive), read_rows(reference)
    check(base_audit["status"] == "pass", "base_consistency_audit_pass")
    check(metadata["complete"] and old_metadata["complete"], "both_matrices_complete")
    check(metadata["config"] == old_metadata["config"], "same_physical_config")
    check(metadata["asset_sha256"] == old_metadata["asset_sha256"], "same_body_asset")
    check(metadata["source_commit"] == "9772b3e93f35aaaaf63ad213247e1684b4e94690", "declared_new_source")
    check(profile["source_commit"] == metadata["source_commit"]
          and profile["reference_source_commit"] == old_metadata["source_commit"], "profile_source_records")
    check(len(rows) == len(old_rows) == 6000 == profile["matched_control_steps"], "matched_control_rows")
    check(profile["early_window_seconds"] == 0.5, "declared_fixed_window")
    check(profile["analysis_script_sha256"] == sha(root / "scripts/analyze_ground_body_impacts.py"), "analysis_script_bytes")
    for filename, digest in manifest.items():
        check(sha(archive / filename) == digest, "listed_manifest_sha256", filename)
    for filename, digest in profile["input_sha256"].items():
        path = root / Path(filename.replace("\\", "/"))
        check(sha(path) == digest, "profile_input_sha256", filename)

    by_trial = defaultdict(lambda: {
        "force": [], "energy": [], "distance": [], "time": [], "endpoint_force": [],
    })
    dt = metadata["config"]["physics_dt"]
    check(dt == .002, "physics_sampling_interval")
    for index, (row, old) in enumerate(zip(rows, old_rows), 1):
        tid, d, old_d = row["trial_id"], row["diagnostics"], old["diagnostics"]
        check(tid == old["trial_id"], "paired_row_trial_identity", index)
        for key in ("qpos", "qvel"):
            check(row[key] == old[key], "exact_physical_replay", [tid, index, key])
            for a, b in zip(row[key], old[key]):
                max_state_difference = max(max_state_difference, abs(a - b))
        check(row["observation_before"] == old["observation_before"], "exact_native_before_replay", [tid, index])
        check(row["observation_after"] == old["observation_after"], "exact_native_after_replay", [tid, index])
        for key in ("requested_torque", "accepted_torque", "applied_torque", "applied_torque_history"):
            check(d[key] == old_d[key], "exact_command_replay", [tid, index, key])
        for key, value in old_d.items():
            check(d[key] == value, "all_shared_diagnostics_exact", [tid, index, key])
        n = d["executed_substeps"]
        force = d["substep_ground_normal_forces"]
        energy = d["substep_kinetic_energies"]
        distance = d["substep_minimum_contact_distances"]
        check(len(force) == len(energy) == len(distance) == n, "substep_array_lengths", [tid, index])
        finite(force, "finite_substep_force", [tid, index])
        finite(energy, "finite_substep_energy", [tid, index])
        finite(distance, "finite_substep_distance", [tid, index])
        check(all(v >= 0 for v in force), "nonnegative_substep_force", [tid, index])
        check(all(v >= 0 for v in energy), "nonnegative_substep_energy", [tid, index])
        near(d["ground_normal_impulse_ns"], sum(force) * dt, "per_control_force_integral", [tid, index])
        check(d["peak_substep_ground_normal_force"] == max(force), "per_control_force_max", [tid, index])
        check(d["peak_substep_kinetic_energy"] == max(energy), "per_control_energy_max", [tid, index])
        check(d["minimum_substep_contact_distance"] == min(distance), "per_control_distance_min", [tid, index])
        check(force[-1] == d["ground_normal_force"], "force_endpoint_alignment", [tid, index])
        check(energy[-1] == d["kinetic_energy"], "energy_endpoint_alignment", [tid, index])
        check(distance[-1] == d["minimum_contact_distance"], "distance_endpoint_alignment", [tid, index])
        group = by_trial[tid]
        for i in range(n):
            sample_time = d["time"] - (n - 1 - i) * dt
            near(sample_time, (len(group["time"]) + 1) * dt, "physics_sample_clock", [tid, index, i], tolerance=2e-12)
            if group["time"]:
                check(sample_time > group["time"][-1], "monotonic_substep_clock", [tid, index, i])
            group["time"].append(sample_time)
        group["force"].extend(force)
        group["energy"].extend(energy)
        group["distance"].extend(distance)
        group["endpoint_force"].append(d["ground_normal_force"])

    recorded = {t["trial_id"]: t for t in profile["trials"]}
    check(len(recorded) == len(profile["trials"]) == len(by_trial) == 24 == profile["trial_count"], "profile_trial_identity")
    recomputed = []
    for tid, group in by_trial.items():
        force, energy, distance, times = (
            group["force"], group["energy"], group["distance"], group["time"],
        )
        peak_index = max(range(len(force)), key=lambda i: force[i])
        peak = force[peak_index]
        endpoint_peak = max(group["endpoint_force"])
        early = [v for v, t in zip(force, times) if t <= .5 + 1e-10]
        late = [v for v, t in zip(force, times) if t > .5 + 1e-10]
        check(len(force) == len(energy) == len(distance) == len(times) == 2500, "full_trial_physics_samples", tid)
        check(len(early) == 250 and len(late) == 2250, "preset_window_sample_counts", tid)
        pose, tail = tid.split("_seed", 1)
        seed, mode = tail.split("_", 1)
        result = {
            "trial_id": tid, "pose": pose, "seed": int(seed), "mode": mode,
            "physics_samples": len(force), "peak_substep_ground_normal_force_n": peak,
            "peak_time_seconds": times[peak_index],
            "peak_control_endpoint_ground_normal_force_n": endpoint_peak,
            "endpoint_peak_miss_percent": 0.0 if peak == 0 else 100 * (1 - endpoint_peak / peak),
            "early_ground_normal_force_peak_n": max(early, default=0.0),
            "late_ground_normal_force_peak_n": max(late, default=0.0),
            "early_ground_normal_impulse_ns": sum(early) * dt,
            "late_ground_normal_impulse_ns": sum(late) * dt,
            "ground_normal_impulse_ns": sum(force) * dt,
            "peak_substep_kinetic_energy_j": max(energy, default=0.0),
            "minimum_substep_contact_distance_m": min(distance, default=0.0),
        }
        stored = recorded[tid]
        check(set(result) == set(stored), "profile_field_set", tid)
        for key, value in result.items():
            if isinstance(value, float):
                near(stored[key], value, "independent_scalar_profile_value", [tid, key])
            else:
                check(stored[key] == value, "independent_scalar_profile_label", [tid, key])
        near(result["early_ground_normal_impulse_ns"] + result["late_ground_normal_impulse_ns"], result["ground_normal_impulse_ns"], "window_impulse_partition", tid)
        result["early_physics_samples"] = len(early)
        result["late_physics_samples"] = len(late)
        recomputed.append(result)

    check(profile["physics_samples"] == sum(len(g["force"]) for g in by_trial.values()) == 60000, "total_impact_samples")
    check(profile["maximum_qpos_qvel_replay_difference"] == max_state_difference == 0, "zero_state_replay_difference")
    check(profile["numeric_values_checked"] == 6000 * (15 + 14 + 38 + 30) == 582000, "profile_counter_definition")
    check(profile["parameter_updates"] == metadata["parameter_updates"] == {"model": 0, "policy": 0, "gate": 0}, "zero_update_records")
    recovery = json.loads((interrupted / "recovery.json").read_text(encoding="utf-8"))
    first_rows = read_rows(interrupted)
    first_groups = defaultdict(list)
    for row in first_rows:
        first_groups[row["trial_id"]].append(row)
    first_physics = sum(g[-1]["diagnostics"]["physics_steps"] for g in first_groups.values())
    check(len(first_rows) == recovery["observed_trace_control_steps"] == 2750, "first_attempt_extra_control_budget")
    check(first_physics == recovery["observed_trace_physics_steps"] == 27500, "first_attempt_extra_physics_budget")
    old_physics = old_metadata["physics_steps"]
    check(old_physics == 60000 and old_metadata["control_steps"] == len(old_rows) == 6000, "reference_matrix_budget")
    side = [t for t in recomputed if t["pose"] in ("left_side", "right_side")]
    side_zero = [t for t in side if t["mode"] == "zero_torque"]
    findings = {
        "global_sampled_substep_force_max_n": max(t["peak_substep_ground_normal_force_n"] for t in recomputed),
        "global_control_endpoint_force_max_n": max(t["peak_control_endpoint_ground_normal_force_n"] for t in recomputed),
        "maximum_single_trial_endpoint_peak_miss_percent": max(t["endpoint_peak_miss_percent"] for t in recomputed),
        "global_sampled_substep_kinetic_energy_max_j": max(t["peak_substep_kinetic_energy_j"] for t in recomputed),
        "global_sampled_substep_minimum_contact_distance_m": min(t["minimum_substep_contact_distance_m"] for t in recomputed),
        "side_pose_global_peak_time_range_seconds": [min(t["peak_time_seconds"] for t in side), max(t["peak_time_seconds"] for t in side)],
        "side_pose_zero_torque_peak_time_range_seconds": [min(t["peak_time_seconds"] for t in side_zero), max(t["peak_time_seconds"] for t in side_zero)],
        "side_zero_torque_trials_with_peak_after_0_5_seconds": sum(t["peak_time_seconds"] > .5 for t in side_zero),
    }
    return {
        "schema_version": 1, "audit_type": "independent_standard_library_scalar_substep_consistency",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "pass" if not violations else "failed",
        "methods": "Standard-library scalar JSON/gzip/math/hashlib only; no project imports, NumPy, simulator/planner calls, parameter fitting or new physical interactions. Existing standalone base audit ran separately.",
        "auditor_script_sha256": sha(Path(__file__).resolve()),
        "input_archives": {
            "archive": str(archive.resolve()), "reference": str(reference.resolve()),
            "interrupted": str(interrupted.resolve()),
        },
        "input_sha256": {p.name: sha(p) for p in (
            archive / "metadata.json", archive / "trace.jsonl.gz", archive / "trials.json",
            archive / "source_snapshot.zip", archive / "impact_profile.json",
        )},
        "reference_trace_sha256": sha(reference / "trace.jsonl.gz"),
        "base_audit": {"path": str(base_audit_path.resolve()), "sha256": sha(base_audit_path), "status": base_audit["status"], "checks": base_audit["checks"]},
        "manifest_coverage": {
            "checked_entries": len(manifest), "audited_entries": manifest,
            "files_not_covered_by_manifest_at_read": sorted(
                p.name for p in archive.iterdir()
                if p.is_file() and p.name != "manifest.json" and p.name not in manifest
            ),
            "scope": "Only listed entries of the supplied manifest are checked. The profile is independently hashed above; unlisted additions are not claimed covered.",
        },
        "checks": checks, "substep_scalar_numbers_checked": scalar_numbers,
        "maximum_scalar_recomputation_difference": max_difference,
        "maximum_qpos_qvel_replay_difference": max_state_difference,
        "matched_control_rows": len(rows), "physics_samples": sum(len(g["force"]) for g in by_trial.values()),
        "window_definition": {
            "boundary_seconds": .5, "boundary_tolerance_seconds": 1e-10,
            "early_time_comparison": "sample_time <= 0.5 + 1e-10",
            "early_physics_samples_per_trial": 250, "late_physics_samples_per_trial": 2250,
        },
        "findings": findings, "independently_recomputed_trials": recomputed,
        "budget_ledger": {
            "interrupted_control_steps": len(first_rows), "interrupted_physics_steps": first_physics,
            "first_complete_control_steps": len(old_rows), "first_complete_physics_steps": old_physics,
            "substep_complete_control_steps": len(rows), "substep_complete_physics_steps": metadata["physics_steps"],
            "total_collector_control_steps": len(first_rows) + len(old_rows) + len(rows),
            "total_collector_physics_steps": first_physics + old_physics + metadata["physics_steps"],
            "total_collector_simulated_seconds": (first_physics + old_physics + metadata["physics_steps"]) * dt,
            "scope": "All three collector attempts; tests and other historical diagnostics excluded.",
        },
        "evidence_boundaries": [
            "Archive consistency and replay equality are established; this audit is not an independent physical solver, continuous-time force bound, or hardware safety proof.",
            "Substep samples are after each 2 ms integration step; maxima may still miss between-step peaks.",
            "A 0.5 s partition is a predefined descriptive clock window, not a causal separation of passive settling and active exploration. Zero-torque side trials also have large peaks after 0.5 s.",
            "Normal force integrals include gravity-support exposure and must not be described as pure collision impulse.",
            "All 0-termination and 0-update records do not establish learning benefit, safe exploration, skill acquisition, biological validity or G1 validity.",
        ],
        "violations": violations,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--reference", type=Path)
    parser.add_argument("--interrupted-archive", type=Path)
    parser.add_argument("--base-audit", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    archive = args.archive.resolve()
    if args.reference is None:
        if not archive.name.endswith("_ground_impacts"):
            parser.error("--reference is required when the archive name does not end in _ground_impacts")
        reference = archive.with_name(archive.name.removesuffix("_ground_impacts") + "_ground_body_verified")
    else:
        reference = args.reference.resolve()
    interrupted = (args.interrupted_archive or reference.with_name(reference.name.removesuffix("_verified"))).resolve()
    output = args.output.resolve()
    if any(output.is_relative_to(path) for path in (archive, reference, interrupted)):
        parser.error("--output must be outside all three audited input directories")
    base_audit_path = args.base_audit
    if base_audit_path is None:
        saved_base = archive / "audit.json"
        base_audit_path = saved_base if saved_base.exists() else Path(__file__).resolve().parents[1] / "external/ground_impacts_base_audit.json"
    result = audit(archive, reference, interrupted, base_audit_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({key: result[key] for key in (
        "status", "checks", "substep_scalar_numbers_checked", "maximum_scalar_recomputation_difference",
        "maximum_qpos_qvel_replay_difference", "findings", "budget_ledger", "manifest_coverage", "violations",
    )}, indent=2))
    if result["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
