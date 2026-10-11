"""Read-only development diagnostics for the audited PD grid and E1 v2.

Standard-library only: no simulator imports, physics, fitting, or access to
holdout archives. Risk windows retain both paid prefix and active control.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
import math
from pathlib import Path
import platform
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
KINDS = ("frozen_mpc", "learned_mpc", "fixed_pd", "zero_torque")
SEEDS = [0, 1, 2]
JOINTS = ("left_shoulder", "left_elbow", "right_shoulder", "right_elbow",
          "left_hip", "left_knee", "right_hip", "right_knee")
ASSET = "src/developmental_physics/assets/ground_body.xml"


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def finite_tree(value):
    if isinstance(value, dict):
        if value.get("invalid_numeric_fields"):
            raise ValueError("Invalid numeric markers are not valid diagnostic samples.")
        for item in value.values():
            finite_tree(item)
    elif isinstance(value, list):
        for item in value:
            finite_tree(item)
    elif isinstance(value, float) and not math.isfinite(value):
        raise ValueError("Nonfinite diagnostic sample.")


def vector(value, width):
    if not isinstance(value, list) or len(value) != width or any(
        type(v) not in (int, float) or not math.isfinite(v) for v in value
    ):
        raise ValueError("Incorrect diagnostic vector dimensions or values.")
    return value


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def archive_identity(path):
    path = Path(path).resolve()
    metadata = load_json(path/"metadata.json")
    # Check split before opening trajectories, source snapshots or seed metrics.
    if metadata.get("split") != "development" or metadata.get("seeds") != SEEDS:
        raise ValueError("Only development seeds 0/1/2 may be summarized.")
    if (metadata.get("pose") != "supine" or metadata.get("joint_index") != 0
            or metadata.get("prefix_steps") != 100 or metadata.get("control_steps_per_trial") != 200):
        raise ValueError("Expected the original supine/left-shoulder local task and time protocol.")
    manifest = load_json(path/"manifest.json")
    actual = {p.name for p in path.iterdir() if p.is_file() and p.name != "manifest.json"}
    if set(manifest) != actual:
        raise ValueError("Manifest does not cover exactly the archive files.")
    for name, expected in manifest.items():
        if Path(name).name != name or name in (".", "..") or file_hash(path/name) != expected:
            raise ValueError("Invalid manifest member or mismatched file hash.")
    with zipfile.ZipFile(path/"source_snapshot.zip") as source:
        names = source.namelist()
        if len(names) != len(set(names)) or set(names) != set(metadata["source_sha256"]):
            raise ValueError("Source snapshot coverage is not exact and unique.")
        for name, expected in metadata["source_sha256"].items():
            if hashlib.sha256(source.read(name)).hexdigest() != expected:
                raise ValueError("Source snapshot hash mismatch.")
        xml = ET.fromstring(source.read(ASSET))
    compiler = xml.find("compiler")
    factor = math.pi/180. if compiler is not None and compiler.get("angle", "degree") == "degree" else 1.
    ranges = {j.get("name"): [float(x)*factor for x in j.get("range").split()]
              for j in xml.findall(".//joint") if j.get("range")}
    core = {name: file_hash(path/name) for name in sorted(manifest)}
    core["manifest.json"] = file_hash(path/"manifest.json")
    return metadata, core, [ranges[name] for name in JOINTS]


def empty_window():
    return {"control_calls": 0, "physics_substeps": 0, "errors": [], "saturated": [],
            "requested_absolute": 0., "requested_square": 0., "actual_absolute": 0.,
            "actual_square": 0., "request_variation": 0., "nonzero_requested_substeps": 0,
            "blocked_substeps": 0, "ground_force_peak": None, "ground_force_impulse": 0.,
            "energy_peak": None, "minimum_distance": None, "maximum_native_speed": None,
            "maximum_selected_speed": None, "maximum_limit_overshoot": None}


def consume_window(window, row, target, ranges, previous_request):
    diag = row["diagnostics"]
    requested = vector(row["requested_torque"], 8)
    n = diag["executed_substeps"]
    if type(n) is not int or not 0 <= n <= 10:
        raise ValueError("Invalid physics substep count.")
    history = diag["applied_torque_history"]
    if not isinstance(history, list) or len(history) != n:
        raise ValueError("Actual torque history does not cover executed substeps.")
    for actual in history:
        vector(actual, 8)
    forces = vector(diag["substep_ground_normal_forces"], n)
    energies = vector(diag["substep_kinetic_energies"], n)
    distances = vector(diag["substep_minimum_contact_distances"], n)
    velocities = vector(row["observation_after"]["joint_velocity"], 8)
    positions = vector(row["observation_after"]["joint_position"], 8)
    if any(v < 0 for v in forces+energies):
        raise ValueError("Force and kinetic energy must be nonnegative.")
    window["control_calls"] += 1
    window["physics_substeps"] += n
    window["requested_absolute"] += abs(requested[0])*n*.002
    window["requested_square"] += requested[0]**2*n*.002
    window["actual_absolute"] += math.fsum(abs(a[0]) for a in history)*.002
    window["actual_square"] += math.fsum(a[0]**2 for a in history)*.002
    window["request_variation"] += abs(requested[0]-previous_request)
    window["nonzero_requested_substeps"] += n if requested[0] != 0. else 0
    window["blocked_substeps"] += sum(requested[0] != 0. and a[0] == 0. for a in history)
    window["saturated"].append(int(abs(requested[0]) == .5))
    if target is not None:
        window["errors"].append(positions[0]-target)
    if n:
        force_peak, energy_peak, minimum = max(forces), max(energies), min(distances)
        window["ground_force_peak"] = max(force_peak, window["ground_force_peak"] or 0.)
        window["energy_peak"] = max(energy_peak, window["energy_peak"] or 0.)
        window["minimum_distance"] = minimum if window["minimum_distance"] is None else min(minimum, window["minimum_distance"])
        window["ground_force_impulse"] += math.fsum(forces)*.002
    speed, selected = max(abs(v) for v in velocities), abs(velocities[0])
    overshoot = max(max(lower-q, q-upper, 0.) for q, (lower, upper) in zip(positions, ranges))
    window["maximum_native_speed"] = max(speed, window["maximum_native_speed"] or 0.)
    window["maximum_selected_speed"] = max(selected, window["maximum_selected_speed"] or 0.)
    window["maximum_limit_overshoot"] = max(overshoot, window["maximum_limit_overshoot"] or 0.)


def finish_window(window):
    errors, saturated = window["errors"], window["saturated"]
    last = errors[-25:]
    nonzero = window["nonzero_requested_substeps"]
    return {"control_calls": window["control_calls"], "physics_substeps": window["physics_substeps"],
            "tracking_sample_count": len(errors),
            "tracking_rmse_rad": math.sqrt(math.fsum(x*x for x in errors)/len(errors)) if errors else None,
            "tracking_endpoint_error_rad": errors[-1] if errors else None,
            "tracking_maximum_absolute_error_rad": max(abs(x) for x in errors) if errors else None,
            "tail_25_mean_signed_error_rad": math.fsum(last)/len(last) if last else None,
            "tail_25_mean_absolute_error_rad": math.fsum(abs(x) for x in last)/len(last) if last else None,
            "tail_25_saturated_fraction": math.fsum(saturated[-25:])/min(25, len(saturated)) if saturated else None,
            "requested_absolute_effort_nms": window["requested_absolute"],
            "requested_squared_effort_nm2s": window["requested_square"],
            "actual_absolute_effort_nms": window["actual_absolute"],
            "actual_squared_effort_nm2s": window["actual_square"],
            "requested_torque_total_variation_nm": window["request_variation"],
            "saturated_control_calls": sum(saturated),
            "saturated_control_fraction": sum(saturated)/len(saturated) if saturated else None,
            "nonzero_requested_target_substeps": nonzero, "blocked_target_substeps": window["blocked_substeps"],
            "target_shield_fraction": window["blocked_substeps"]/nonzero if nonzero else None,
            "peak_ground_force_n": window["ground_force_peak"], "ground_force_impulse_ns": window["ground_force_impulse"],
            "peak_kinetic_energy_j": window["energy_peak"], "minimum_contact_distance_m": window["minimum_distance"],
            "maximum_contact_penetration_m": max(-window["minimum_distance"], 0.) if window["minimum_distance"] is not None else None,
            "maximum_native_endpoint_joint_speed_rad_s": window["maximum_native_speed"],
            "maximum_selected_endpoint_joint_speed_rad_s": window["maximum_selected_speed"],
            "maximum_native_endpoint_joint_limit_overshoot_rad": window["maximum_limit_overshoot"]}


def summarize_archive(path, metadata, ranges, *, pd):
    episodes = load_json(path/"episodes.json")
    plans = [ep for ep in episodes if pd or ep.get("kind") in KINDS]
    if len({ep["trial_id"] for ep in plans}) != len(plans):
        raise ValueError("Duplicate trial outcomes.")
    states = {ep["trial_id"]: {"ep": ep, "rows": 0, "exception": False, "previous_request": 0.,
        "prefix": hashlib.sha256(), "windows": {name: empty_window() for name in
        ("full", "prefix", "control", "target_0_04", "target_0_08")}} for ep in plans}
    with gzip.open(path/"trace.jsonl.gz", "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if not pd and row.get("kind") not in KINDS:
                continue
            if row.get("trial_id") not in states:
                raise ValueError("Unexpected diagnostic trial.")
            state = states[row["trial_id"]]
            if "collector_exception" in row:
                state["exception"] = True
                continue
            finite_tree(row)
            index = state["rows"]
            if row["seed"] != state["ep"]["seed"] or row.get("control_index" if pd else "step_index") != index:
                raise ValueError("Trial seed or control time mismatch.")
            if row["phase"] != ("prefix" if index < 100 else "control"):
                raise ValueError("Unexpected diagnostic phase.")
            target = row["target_q_rad" if pd else "target_q"]
            windows = ["full", "prefix" if index < 100 else "control"]
            if index >= 100:
                windows.append("target_0_04" if index < 200 else "target_0_08")
            for name in windows:
                consume_window(state["windows"][name], row, target, ranges, state["previous_request"])
            if index < 100:
                state["prefix"].update(canonical({key: row[key] for key in
                    ("observation_before", "observation_after", "diagnostics", "qpos", "qvel")}))
                state["prefix"].update(b"\n")
            state["previous_request"] = row["requested_torque"][0]
            state["rows"] += 1
    trials = []
    for state in states.values():
        ep = state["ep"]
        windows = {name: finish_window(window) for name, window in state["windows"].items()}
        complete = (ep["status"] == "completed" and not state["exception"] and state["rows"] == 300
                    and windows["control"]["tracking_sample_count"] == 200
                    and windows["full"]["physics_substeps"] == ep["physics_steps"] == 3000)
        if pd:
            complete = complete and ep["complete"] is True
            if complete and abs(windows["control"]["tracking_rmse_rad"]-ep["tracking_rmse_rad"]) > 1e-10:
                raise ValueError("Recomputed PD tracking disagrees with the recorded episode.")
        trials.append({"trial_id": ep["trial_id"], "seed": ep["seed"], "method": f'candidate{ep["candidate"]}' if pd else ep["kind"],
                       "candidate": ep.get("candidate"), "kp": ep.get("kp"), "kd": ep.get("kd"),
                       "status": ep["status"], "complete": complete, "prefix_sha256": state["prefix"].hexdigest(),
                       "risk_scope": "all paid substeps" if complete else "available logged substeps only; lower bound",
                       "windows": windows, "paid_budget": {k: ep[k] for k in ("control_calls_attempted", "control_steps", "physics_steps")}})
    return trials


def aggregate_groups(trials):
    groups = []
    for method in dict.fromkeys(t["method"] for t in trials):
        rows = [t for t in trials if t["method"] == method]
        complete = len(rows) == 3 and {r["seed"] for r in rows} == set(SEEDS) and all(r["complete"] for r in rows)
        aggregates = {name: {} for name in ("mean", "minimum", "maximum")}
        if complete:
            for window in rows[0]["windows"]:
                for name in aggregates:
                    aggregates[name][window] = {}
                for metric in rows[0]["windows"][window]:
                    values = [row["windows"][window][metric] for row in rows]
                    for name, function in (("mean", lambda xs: math.fsum(xs)/len(xs)), ("minimum", min), ("maximum", max)):
                        aggregates[name][window][metric] = None if any(v is None for v in values) else function(values)
        groups.append({"method": method, "candidate": rows[0]["candidate"], "kp": rows[0]["kp"], "kd": rows[0]["kd"],
                       "all_three_seeds_complete": complete, "per_seed": rows,
                       "mean_metrics": aggregates["mean"] if complete else None,
                       "minimum_metrics": aggregates["minimum"] if complete else None,
                       "maximum_metrics": aggregates["maximum"] if complete else None})
    return groups


def relative(value, reference):
    return None if reference in (None, 0.) or value is None else value/reference-1.


def compare_selected(selected, baseline):
    if not selected["all_three_seeds_complete"] or not baseline["all_three_seeds_complete"]:
        return {"baseline": baseline["method"], "available": False}
    rows = []
    for label, p, b in [("mean", selected["mean_metrics"], baseline["mean_metrics"])] + [
        (str(seed), next(t["windows"] for t in selected["per_seed"] if t["seed"] == seed),
         next(t["windows"] for t in baseline["per_seed"] if t["seed"] == seed)) for seed in SEEDS]:
        track_change = relative(p["control"]["tracking_rmse_rad"], b["control"]["tracking_rmse_rad"])
        rows.append({"seed_or_mean": label, "selected_pd_tracking_rmse_rad": p["control"]["tracking_rmse_rad"],
                     "baseline_tracking_rmse_rad": b["control"]["tracking_rmse_rad"],
                     "selected_pd_tracking_reduction": None if track_change is None else -track_change,
                     "selected_pd_actual_absolute_effort_change": relative(p["control"]["actual_absolute_effort_nms"], b["control"]["actual_absolute_effort_nms"]),
                     "selected_pd_actual_squared_effort_change": relative(p["control"]["actual_squared_effort_nm2s"], b["control"]["actual_squared_effort_nm2s"]),
                     "selected_pd_control_force_peak_change": relative(p["control"]["peak_ground_force_n"], b["control"]["peak_ground_force_n"]),
                     "selected_pd_control_energy_peak_change": relative(p["control"]["peak_kinetic_energy_j"], b["control"]["peak_kinetic_energy_j"])})
    return {"baseline": baseline["method"], "available": True, "comparisons": rows,
            "ratio_definition": "Tracking reduction=1-PD/baseline; effort/risk change=PD/baseline-1; mean ratios use raw metric means."}


def summarize(archive, reference, audit_path):
    started = time.perf_counter()
    archive, reference, audit_path = Path(archive).resolve(), Path(reference).resolve(), Path(audit_path).resolve()
    audit_hash = file_hash(audit_path)
    audit = load_json(audit_path)
    if audit.get("failed") != 0 or not audit.get("archive", {}).get("selection", {}).get("validated_selection"):
        raise ValueError("A successful independently audited PD development selection is required.")
    pd_meta, pd_hashes, pd_ranges = archive_identity(archive)
    e1_meta, e1_hashes, e1_ranges = archive_identity(reference)
    record = audit["archive"]
    if record["input_hashes"] != pd_hashes or record["source_commit"] != pd_meta["source_commit"]:
        raise ValueError("PD archive does not match the supplied independent audit hashes.")
    historical = record.get("reference", {})
    if (not historical.get("exact_replay_verified") or historical.get("input_hashes") !=
            {name: e1_hashes[name] for name in ("metadata.json", "trace.jsonl.gz")}):
        raise ValueError("The development reference does not match the audited historical anchor.")
    if (e1_meta.get("variant") != "hinge" or pd_meta["environment_config"] != e1_meta["environment_config"]
            or pd_meta.get("mujoco_version") != e1_meta.get("mujoco_version") or pd_ranges != e1_ranges):
        raise ValueError("Environment, engine, ranges or reference variant differ.")
    common_sources = (ASSET, "src/developmental_physics/environment.py", "src/developmental_physics/probes.py")
    if any(pd_meta["source_sha256"][name] != e1_meta["source_sha256"][name] for name in common_sources):
        raise ValueError("Common body, physics or direction code changed.")
    pd_trials = summarize_archive(archive, pd_meta, pd_ranges, pd=True)
    e1_trials = summarize_archive(reference, e1_meta, e1_ranges, pd=False)
    for seed in SEEDS:
        rows = [t for t in pd_trials+e1_trials if t["seed"] == seed]
        if len({t["prefix_sha256"] for t in rows}) != 1:
            raise ValueError("Paid prefixes do not exactly replay across PD/MPC/reference controls.")
    pd_groups, baseline_groups = aggregate_groups(pd_trials), aggregate_groups(e1_trials)
    selected_id = record["selection"]["selected"]["candidate"]
    selected = next(group for group in pd_groups if group["candidate"] == selected_id)
    for path, hashes in ((archive, pd_hashes), (reference, e1_hashes)):
        if any(file_hash(path/name) != expected for name, expected in hashes.items()):
            raise ValueError("An input changed during read-only analysis.")
    if file_hash(audit_path) != audit_hash:
        raise ValueError("The independent input audit changed during analysis.")
    source_status = subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=all"], cwd=ROOT, text=True)
    return {"schema_version": 1, "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "purpose": "Descriptive development-only PD strong-baseline diagnostics and old E1 v2 comparison.",
            "summary_script_sha256": file_hash(Path(__file__)),
            "analysis_source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
            "analysis_source_status": source_status, "analysis_source_dirty": bool(source_status),
            "analysis_wall_seconds": time.perf_counter()-started,
            "analysis_runtime": {"python": sys.version, "platform": platform.platform(), "third_party_dependencies": []},
            "analysis_physical_interactions": 0, "analysis_parameter_updates": 0,
            "input_audit": {"path": str(audit_path), "sha256": audit_hash, "checks": audit["checks"], "failed": audit["failed"]},
            "input_archives": [{"path": str(path), "split": "development", "source_commit": meta["source_commit"],
                                "source_sha256": meta["source_sha256"], "input_hashes": hashes,
                                "paid_budget": {k: meta[k] for k in ("control_calls_attempted", "control_steps", "physics_steps")},
                                "collection_wall_seconds": meta["wall_seconds"]}
                               for path, meta, hashes in ((archive, pd_meta, pd_hashes), (reference, e1_meta, e1_hashes))],
            "selected_candidate": record["selection"]["selected"], "pd_candidates": pd_groups,
            "e1_v2_development_controls": baseline_groups,
            "selected_pd_vs_e1_development": [compare_selected(selected, baseline) for baseline in baseline_groups],
            "notes": ["All results are observed development seeds 0/1/2; no holdout data are read or evaluated.",
                      "PD gain selection cost includes all 27 trials, not only the selected three trials.",
                      "Each risk metric has full, paid-prefix and active-control windows; full peaks can mask active differences.",
                      "Native speed and limit overshoot are control-endpoint samples; force, energy and contact distance use physics substeps.",
                      "Contact distance/penetration includes self-contact, not solely ground penetration.",
                      "Actual torque integrals are effort proxies, not mechanical energy; no substep angular-velocity history is available.",
                      "Means are computed only when all three planned seeds complete; undefined ratios remain null.",
                      "Current matched development comparisons do not establish unseen controller superiority, general skill or hardware safety."]}


def validate_output_path(output, inputs):
    output = Path(output).resolve()
    if output.exists():
        raise ValueError("Refusing to overwrite an existing summary output.")
    if any(output.is_relative_to(Path(path).resolve()) or output == Path(path).resolve() for path in inputs):
        raise ValueError("Summary output must be outside input archives and audit.")
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--reference", required=True, type=Path)
    parser.add_argument("--audit", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        output = validate_output_path(args.output, [args.archive, args.reference, args.audit])
        report = summarize(args.archive, args.reference, args.audit)
    except (OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile) as error:
        parser.error(str(error))
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(report, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"output": str(output), "selected_candidate": report["selected_candidate"],
                      "analysis_wall_seconds": report["analysis_wall_seconds"], "analysis_physical_interactions": 0}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
