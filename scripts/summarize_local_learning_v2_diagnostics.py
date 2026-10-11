"""Derive secondary diagnostics from archives covered by an independent audit.

Read-only standard-library analysis, without physics, fitting or gate changes.
Copied archives are matched by recorded file hashes, never by machine paths.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import gzip
import hashlib
import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile

CORE_FILES = {"manifest.json", "metadata.json", "episodes.json", "seed_results.json", "trace.jsonl.gz", "source_snapshot.zip"}
JOINT_NAMES = ("left_shoulder", "left_elbow", "right_shoulder", "right_elbow", "left_hip", "left_knee", "right_hip", "right_knee")


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate_output_path(output, archives):
    output = Path(output).resolve()
    if output.exists():
        raise ValueError("Refusing to overwrite an existing output.")
    if any(output.is_relative_to(Path(path).resolve()) for path in archives):
        raise ValueError("Output must be outside every input archive.")
    return output


def match_archive(path, audit):
    path = Path(path).resolve()
    if not isinstance(audit.get("archives"), list) or audit.get("failed") != 0:
        raise ValueError("A successful independent data-consistency audit is required.")
    hashes = {name: file_hash(path / name) for name in sorted(CORE_FILES)}
    matches = [record for record in audit["archives"] if record.get("input_hashes") == hashes]
    if len(matches) != 1:
        raise ValueError(f"Archive files do not uniquely match the audit hashes: {path}")
    metadata = json.loads((path / "metadata.json").read_text(encoding="utf-8"))
    record = matches[0]
    if metadata.get("variant") != "hinge" or any(metadata.get(key) != record.get(key) for key in ("split", "pose", "joint_index", "source_commit")):
        raise ValueError(f"Archive labels do not match the audited hinge experiment: {path}")
    return record, hashes


def summarize_archive(path, archive):
    grouped = defaultdict(list)
    with gzip.open(path / "trace.jsonl.gz", "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            grouped[(row["seed"], row["kind"])].append(row)
    with zipfile.ZipFile(path / "source_snapshot.zip") as source:
        xml = ET.fromstring(source.read("src/developmental_physics/assets/ground_body.xml"))
    factor = math.pi / 180 if xml.find("compiler").get("angle") == "degree" else 1.
    ranges = {joint.get("name"): [float(value) * factor for value in joint.get("range").split()] for joint in xml.findall(".//joint") if joint.get("range")}
    reports = []
    for seed_result in archive["seeds"]:
        for kind, metrics in seed_result["evaluations"].items():
            rows = grouped[(seed_result["seed"], kind)]
            selected = archive["joint_index"]
            windows = {}
            for phase, window in (("all", rows), ("prefix", rows[:100]), ("active", rows[100:])):
                force, energy, distance, speed, overshoot = [], [], [], [], []
                blocked, nonzero, actual_abs, requested_abs = 0, 0, 0., 0.
                tracking_errors = []
                for row in window:
                    diag, requested = row["diagnostics"], row["requested_torque"]
                    force.extend(diag["substep_ground_normal_forces"])
                    energy.extend(diag["substep_kinetic_energies"])
                    distance.extend(diag["substep_minimum_contact_distances"])
                    for actual in diag["applied_torque_history"]:
                        if requested[selected] != 0:
                            nonzero += 1
                            blocked += actual[selected] == 0
                        actual_abs += abs(actual[selected]) * .002
                        requested_abs += abs(requested[selected]) * .002
                    speed.extend(abs(value) for value in row["observation_after"]["joint_velocity"])
                    for index, name in enumerate(JOINT_NAMES):
                        q = row["observation_after"]["joint_position"][index]
                        lower, upper = ranges[name]
                        overshoot.append(max(lower - q, q - upper, 0.))
                    if row["target_q"] is not None:
                        tracking_errors.append(row["observation_after"]["joint_position"][selected] - row["target_q"])
                windows[phase] = {"control_rows": len(window), "physics_substeps": sum(row["diagnostics"]["executed_substeps"] for row in window), "peak_ground_force_n": max(force, default=None), "peak_kinetic_energy_j": max(energy, default=None), "minimum_contact_distance_m": min(distance, default=None), "maximum_native_joint_speed_rad_s": max(speed, default=None), "maximum_native_joint_limit_overshoot_rad": max(overshoot, default=None), "nonzero_requested_target_substeps": nonzero, "blocked_target_substeps": blocked, "target_shield_fraction": None if nonzero == 0 else blocked / nonzero, "actual_absolute_torque_integral_nm_s": actual_abs, "requested_absolute_torque_integral_nm_s": requested_abs, "tracking_endpoint_error_rad": None if not tracking_errors else tracking_errors[-1], "maximum_absolute_tracking_error_rad": max((abs(value) for value in tracking_errors), default=None)}
            prediction = metrics["velocity_prediction_rmse"]
            ratio = None if prediction["frozen"] in (None, 0.) else prediction["learned"] / prediction["frozen"]
            reports.append({"split": archive["split"], "seed": seed_result["seed"], "kind": kind, "velocity_prediction_rmse": prediction, "learned_to_frozen_prediction_rmse_ratio": ratio, "position_prediction_rmse": metrics["position_prediction_rmse"], "persistence_velocity_rmse": metrics["persistence_velocity_rmse"], "tracking_rmse_rad": metrics["tracking_rmse_rad"], "planner_fallbacks": metrics["planner_fallbacks"], "mathematical_prediction_calls": metrics["mathematical_prediction_calls"], "windows": windows})
    return reports


def summarize(archives, audit_path):
    audit_path = Path(audit_path).resolve()
    audit_hash = file_hash(audit_path)
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    reports, inputs, seen = [], [], set()
    for value in archives:
        path = Path(value).resolve()
        archive, hashes = match_archive(path, audit)
        identity = (archive["split"], archive["source_commit"])
        if identity in seen:
            raise ValueError("The same audited archive was supplied more than once.")
        seen.add(identity)
        reports.extend(summarize_archive(path, archive))
        if any(file_hash(path / name) != expected for name, expected in hashes.items()):
            raise ValueError(f"Input files changed during analysis: {path}")
        inputs.append({"path": str(path), "split": archive["split"], "source_commit": archive["source_commit"], "input_hashes": hashes})
    if file_hash(audit_path) != audit_hash:
        raise ValueError("The input audit changed during analysis.")
    return {"schema_version": 1, "purpose": "Secondary descriptive diagnostics, separate from the predeclared fixed-input prediction and tracking gate.", "source_audit_path": str(audit_path), "source_audit_sha256": audit_hash, "diagnostic_script_sha256": file_hash(Path(__file__)), "input_archives": inputs, "source_audit_data_consistent": audit["failed"] == 0, "predeclared_gate_passed": audit["scientific_gate"]["validated_pass"], "notes": ["Predictions on different controller trajectories are not a common-input comparison; within each trajectory both predictors read the same native states and requested input.", "Zero-trajectory nominal error is close to floating-point scale, so large ratios are not physical failure probabilities.", "Full-time ground-force peaks include the paid initial prefix. Contact distance includes self-contact; these developer thresholds do not certify hardware safety.", "Fixed PD is one declared gain choice, not a tuned strong classical baseline.", "The stated gate belongs to the supplied audit; this report covers only the explicitly listed archive inputs."], "trial_diagnostics": reports}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archives", nargs="+", type=Path)
    parser.add_argument("--audit", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        output = validate_output_path(args.output, args.archives)
        report = summarize(args.archives, args.audit)
    except (OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile) as error:
        parser.error(str(error))
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(report, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"output": str(output), "trial_count": len(report["trial_diagnostics"]), "source_audit_sha256": report["source_audit_sha256"], "diagnostic_script_sha256": report["diagnostic_script_sha256"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
