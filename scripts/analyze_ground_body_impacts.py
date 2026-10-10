"""Audit substep contact telemetry and compare a fixed-action reference replay."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path

import numpy as np


def read_rows(folder: Path):
    with gzip.open(folder / "trace.jsonl.gz", "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream]


def analyze(folder: Path, reference: Path, early_seconds: float = .5):
    metadata = json.loads((folder / "metadata.json").read_text(encoding="utf-8"))
    reference_metadata = json.loads((reference / "metadata.json").read_text(encoding="utf-8"))
    if not metadata["complete"] or not reference_metadata["complete"]:
        raise ValueError("both matrices must be complete")
    if metadata["config"] != reference_metadata["config"]:
        raise ValueError("physical and control configurations differ")
    if metadata["asset_sha256"] != reference_metadata["asset_sha256"]:
        raise ValueError("body assets differ")
    rows = read_rows(folder)
    original = read_rows(reference)
    if len(rows) != len(original):
        raise ValueError("matrix lengths differ")
    by_trial = {}
    maximum_state_difference = 0.
    physics_dt = metadata["config"]["physics_dt"]
    checks = 0
    for row, old in zip(rows, original):
        assert row["trial_id"] == old["trial_id"]
        assert not row["invalid_numeric_fields"]
        for name in ("qpos", "qvel"):
            difference = float(np.max(np.abs(np.array(row[name]) - old[name])))
            maximum_state_difference = max(maximum_state_difference, difference)
            assert difference == 0., "telemetry changed physical state"
            checks += len(row[name])
        for name in row["observation_after"]:
            np.testing.assert_array_equal(row["observation_after"][name], old["observation_after"][name])
            checks += len(row["observation_after"][name])
        diagnostic = row["diagnostics"]
        np.testing.assert_array_equal(diagnostic["applied_torque_history"], old["diagnostics"]["applied_torque_history"])
        n = diagnostic["executed_substeps"]
        force = np.asarray(diagnostic["substep_ground_normal_forces"])
        energy = np.asarray(diagnostic["substep_kinetic_energies"])
        distance = np.asarray(diagnostic["substep_minimum_contact_distances"])
        assert len(force) == len(energy) == len(distance) == n
        assert np.isfinite(force).all() and np.isfinite(energy).all() and np.isfinite(distance).all()
        assert np.all(force >= 0)
        np.testing.assert_allclose(np.sum(force) * physics_dt, diagnostic["ground_normal_impulse_ns"], atol=1e-10, rtol=1e-12)
        assert max(force, default=0.) == diagnostic["peak_substep_ground_normal_force"]
        assert max(energy, default=0.) == diagnostic["peak_substep_kinetic_energy"]
        assert min(distance, default=0.) == diagnostic["minimum_substep_contact_distance"]
        times = diagnostic["time"] - np.arange(n - 1, -1, -1) * physics_dt
        group = by_trial.setdefault(row["trial_id"], {"force": [], "energy": [], "distance": [], "time": [], "endpoint_force": []})
        for name, values in (("force", force), ("energy", energy), ("distance", distance), ("time", times)):
            group[name].extend(values)
        group["endpoint_force"].append(diagnostic["ground_normal_force"])
        checks += 3 * n
    summaries = []
    for trial_id, group in by_trial.items():
        force = np.array(group["force"])
        energy = np.array(group["energy"])
        distance = np.array(group["distance"])
        times = np.array(group["time"])
        early = times <= early_seconds + 1e-10
        index = int(np.argmax(force))
        pose, seed_and_mode = trial_id.split("_seed", 1)
        seed, mode = seed_and_mode.split("_", 1)
        substep_peak = float(force[index])
        endpoint_peak = float(max(group["endpoint_force"]))
        summaries.append({
            "trial_id": trial_id, "pose": pose, "seed": int(seed), "mode": mode,
            "physics_samples": len(force),
            "peak_substep_ground_normal_force_n": substep_peak,
            "peak_time_seconds": float(times[index]),
            "peak_control_endpoint_ground_normal_force_n": endpoint_peak,
            "endpoint_peak_miss_percent": 0. if substep_peak == 0 else 100 * (1 - endpoint_peak / substep_peak),
            "early_ground_normal_force_peak_n": float(np.max(force[early], initial=0.)),
            "late_ground_normal_force_peak_n": float(np.max(force[~early], initial=0.)),
            "early_ground_normal_impulse_ns": float(np.sum(force[early]) * physics_dt),
            "late_ground_normal_impulse_ns": float(np.sum(force[~early]) * physics_dt),
            "ground_normal_impulse_ns": float(np.sum(force) * physics_dt),
            "peak_substep_kinetic_energy_j": float(np.max(energy, initial=0.)),
            "minimum_substep_contact_distance_m": float(np.min(distance, initial=0.)),
        })
    return {
        "schema_version": 1, "analysis_type": "fixed-parameter replay and substep telemetry consistency",
        "source_commit": metadata["source_commit"], "reference_source_commit": reference_metadata["source_commit"],
        "analysis_script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "input_sha256": {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in (folder / "trace.jsonl.gz", reference / "trace.jsonl.gz")},
        "early_window_seconds": early_seconds, "trial_count": len(summaries),
        "matched_control_steps": len(rows), "physics_samples": sum(t["physics_samples"] for t in summaries),
        "maximum_qpos_qvel_replay_difference": maximum_state_difference,
        "numeric_values_checked": checks, "trials": summaries,
        "parameter_updates": metadata["parameter_updates"],
        "claim_boundary": "Contact force is sampled after each 2 ms integration step; not a continuous-time bound or a hardware safety guarantee. Normal impulse includes gravity-support exposure, not only collision impulse. Early/late windows are descriptive; no body model or policy fitting.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = analyze(args.archive, args.reference)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("trial_count", "matched_control_steps", "physics_samples", "maximum_qpos_qvel_replay_difference", "parameter_updates")}, indent=2))


if __name__ == "__main__":
    main()
