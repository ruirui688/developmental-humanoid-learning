"""Independent standard-library audit of two frozen joint-probe archives.

Reads archive bytes, Git blobs and existing analysis profiles only. Does not
import project modules, NumPy or MuJoCo, execute snapshots, or fit a model.
Exit 0: all checks pass; 1: failed checks; 2: unsafe output/invalid arguments.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import gzip
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile

POSES = ("supine", "prone", "left_side", "right_side")
NAMES = ("left_shoulder", "left_elbow", "right_shoulder", "right_elbow",
         "left_hip", "left_knee", "right_hip", "right_knee")
AMPLITUDES = (.125, .25, .5)
PHASES = (("prefix", 0, 100), ("probe", 100, 125), ("recovery", 125, 200))
FIELDS = ("observation_before", "observation_after", "diagnostics", "qpos", "qvel")
CORE = ("src/developmental_physics/__init__.py", "src/developmental_physics/collect.py",
        "src/developmental_physics/environment.py", "src/developmental_physics/exploration.py",
        "src/developmental_physics/probe_collect.py", "src/developmental_physics/probes.py",
        "src/developmental_physics/assets/ground_body.xml", "pyproject.toml", "docs/JOINT_PROBE_PROTOCOL.md")
CONFIG = dict(physics_dt=.002, control_substeps=10, torque_limit=.5, joint_speed_limit=20.,
              joint_limit_margin=.08, kinetic_energy_limit=50., reset_clearance=.005,
              ground_contact_profile="baseline")


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


class Checks:
    def __init__(self):
        self.count = 0
        self.failed = 0
        self.failures = []
        self.maximum_numeric_difference = 0.

    def test(self, condition, label):
        self.count += 1
        if not condition:
            self.failed += 1
            if len(self.failures) < 100:
                self.failures.append(label)

    def equal(self, actual, expected, label):
        self.test(actual == expected, label)

    def numeric(self, actual, expected, label):
        if expected is None:
            self.equal(actual, None, label)
        elif isinstance(expected, list):
            self.test(isinstance(actual, list) and len(actual) == len(expected), label + " length")
            if isinstance(actual, list):
                for a, e in zip(actual, expected):
                    self.numeric(a, e, label)
        elif isinstance(expected, dict):
            self.test(isinstance(actual, dict), label + " object")
            if isinstance(actual, dict):
                for key, value in expected.items():
                    self.test(key in actual, label + " key " + key)
                    if key in actual:
                        self.numeric(actual[key], value, label + "/" + key)
        elif isinstance(expected, (int, float)) and not isinstance(expected, bool):
            valid = isinstance(actual, (int, float)) and not isinstance(actual, bool) and math.isfinite(actual)
            self.test(valid, label + " finite number")
            if valid:
                difference = abs(actual - expected)
                self.maximum_numeric_difference = max(self.maximum_numeric_difference, difference)
                self.test(math.isclose(actual, expected, rel_tol=1e-11, abs_tol=1e-12), label + " value")
        else:
            self.equal(actual, expected, label)

    def finite(self, value, label):
        if isinstance(value, dict):
            for v in value.values():
                self.finite(v, label)
        elif isinstance(value, list):
            for v in value:
                self.finite(v, label)
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            self.test(math.isfinite(value), label + " finite")


def rms(vectors):
    width = len(vectors[0])
    squares = [sum(row[j] ** 2 for row in vectors) for j in range(width)]
    return {"per_component": [math.sqrt(value / len(vectors)) for value in squares],
            "all_components": math.sqrt(sum(squares) / (len(vectors) * width))}


def phase_metrics(rows, joint, direction):
    diagnostics = [row["diagnostics"] for row in rows]
    forces = [v for d in diagnostics for v in d["substep_ground_normal_forces"]]
    energies = [v for d in diagnostics for v in d["substep_kinetic_energies"]]
    distances = [v for d in diagnostics for v in d["substep_minimum_contact_distances"]]
    size = len(forces)
    result = dict(control_rows=len(rows), physics_samples=size,
                  ground_normal_force_peak_n=max(forces),
                  ground_normal_force_integral_ns=sum(forces) * .002,
                  kinetic_energy_peak_j=max(energies), minimum_contact_distance_m=min(distances))
    sources = {
        "requested": [d["requested_torque"] for d in diagnostics for _ in range(d["executed_substeps"])],
        "accepted": [d["accepted_torque"] for d in diagnostics for _ in range(d["executed_substeps"])],
        "applied": [v for d in diagnostics for v in d["applied_torque_history"]],
    }
    for name, vectors in sources.items():
        result[name + "_torque_rms_nm_per_joint"] = rms(vectors)["per_component"]
        signed = [sum(v[j] for v in vectors) * .002 for j in range(8)]
        absolute = [sum(abs(v[j]) for v in vectors) * .002 for j in range(8)]
        result[name + "_signed_torque_integral_nms_per_joint"] = signed
        result[name + "_absolute_torque_integral_nms_per_joint"] = absolute
        if joint is not None:
            result["target_directed_" + name + "_torque_integral_nms"] = direction * signed[joint]
    nonzero = [sum(v[j] != 0 for v in sources["requested"]) for j in range(8)]
    blocked = [sum(r[j] != 0 and a[j] == 0 for r, a in zip(sources["requested"], sources["applied"]))
               for j in range(8)]
    result["nonzero_requested_substeps_per_joint"] = nonzero
    result["blocked_nonzero_request_substeps_per_joint"] = blocked
    result["blocked_fraction_of_nonzero_requested_substeps_per_joint"] = [
        None if n == 0 else b / n for n, b in zip(nonzero, blocked)]
    result["native_endpoint_rms"] = {key: rms([row["observation_after"][key] for row in rows])
                                     for key in ("joint_position", "joint_velocity", "imu_gyro", "imu_acceleration")}
    return result


def audit_archive(directory, profile_path, expected_split, expected_seeds, expected_commit, checks, root):
    before = checks.count
    metadata, trials, profile = read(directory / "metadata.json"), read(directory / "trials.json"), read(profile_path)
    manifest = read(directory / "manifest.json")
    files = {p.name for p in directory.iterdir() if p.is_file() and p.name != "manifest.json"}
    checks.equal(set(manifest), files, expected_split + " manifest full coverage")
    for name, digest in manifest.items():
        checks.test(Path(name).name == name, "manifest basename " + name)
        checks.equal(sha(directory / name), digest, expected_split + " file hash " + name)
    checks.equal(metadata["split"], expected_split, "split")
    checks.equal(metadata["seeds"], expected_seeds, "seeds")
    checks.test(metadata["source_commit"].startswith(expected_commit), "source commit")
    checks.equal(metadata["source_dirty"], False, "clean source")
    checks.equal(metadata["source_status"], "", "empty source status")
    checks.equal(metadata["complete"], True, "complete archive")
    checks.equal(metadata["archive_status"], "completed", "completed archive status")
    checks.equal(metadata["environment_config"], CONFIG, "fixed environment")
    checks.equal(metadata["poses"], list(POSES), "poses")
    checks.equal(metadata["joints"], list(range(8)), "joints")
    checks.equal(metadata["amplitudes_nm"], list(AMPLITUDES), "amplitudes")
    for key, value in dict(prefix_steps=100, pulse_steps=25, recovery_steps=75,
                           steps_per_trial_limit=200, expected_trial_count=300, trial_count=300,
                           control_steps=60000, control_calls_attempted=60000, physics_steps=600000,
                           terminated_trials=0, exception_trials=0, teacher_calls=0,
                           external_demonstration_samples=0).items():
        checks.equal(metadata[key], value, "metadata " + key)
    checks.equal(metadata["parameter_updates"], dict(model=0, policy=0, gate=0), "zero parameter updates")
    checks.equal(metadata["gpu"], None, "CPU only")
    checks.equal(metadata["invalid_numeric_fields"], [], "valid metadata numbers")
    hashes = metadata["source_sha256"]
    checks.test(set(CORE) <= set(hashes), "required source hashes")
    with zipfile.ZipFile(directory / "source_snapshot.zip") as snapshot:
        checks.equal(len(snapshot.namelist()), len(set(snapshot.namelist())), "unique snapshot members")
        checks.equal(set(snapshot.namelist()), set(hashes), "snapshot/hash coverage")
        for name, digest in hashes.items():
            data = snapshot.read(name)
            checks.equal(hashlib.sha256(data).hexdigest(), digest, "snapshot SHA " + name)
            blob = subprocess.check_output(["git", "show", metadata["source_commit"] + ":" + name], cwd=root)
            checks.equal(data, blob, "snapshot Git bytes " + name)
        asset = ET.fromstring(snapshot.read("src/developmental_physics/assets/ground_body.xml"))
        angle = asset.find("compiler").get("angle", "degree")
        joints = {node.get("name"): node for node in asset.iter("joint") if node.get("name")}
        limits = []
        for name in NAMES:
            pair = [float(v) for v in joints[name].get("range").split()]
            limits.append([math.radians(v) for v in pair] if angle == "degree" else pair)
        checks.equal([m.get("joint") for m in asset.find("actuator")], list(NAMES), "asset actuator mapping")
    checks.equal(metadata["asset_sha256"], hashes["src/developmental_physics/assets/ground_body.xml"], "asset identity")
    checks.equal(metadata["protocol"]["sha256"], hashes["docs/JOINT_PROBE_PROTOCOL.md"], "protocol identity")
    checks.equal(profile["source_commit"], metadata["source_commit"], "profile source commit")
    checks.equal(profile["source_dirty"], False, "profile source clean")
    checks.equal(profile["split"], expected_split, "profile split")
    checks.equal(profile["seeds"], expected_seeds, "profile seeds")
    checks.equal(profile["joint_order"], list(NAMES), "profile joint order")
    checks.equal(profile["archive_complete"], True, "profile archive complete")
    checks.equal(profile["protocol_valid"], True, "profile protocol valid")
    checks.equal(profile["analysis_parameter_updates"], 0, "analysis has no updates")
    checks.equal(profile["shared_zero_trial_count"], 12, "profile zero count")
    checks.equal(profile["probe_pair_count"], 288, "profile pair count")
    checks.equal(profile["missing_trial_cases"], [], "no missing trials")
    checks.equal(profile["unavailable_trial_ids"], [], "all trials available")
    checks.equal(profile["orphan_trace_trial_row_counts"], {}, "no orphan rows")
    profile_hashes = {Path(name).name: digest for name, digest in profile["input_sha256"].items()}
    checks.equal(set(profile_hashes), {"metadata.json", "trials.json", "trace.jsonl.gz", "source_snapshot.zip"}, "profile input coverage")
    for name, digest in profile_hashes.items():
        checks.equal(digest, sha(directory / name), "profile input identity " + name)
    expected_ids = []
    for pose in POSES:
        for seed in expected_seeds:
            expected_ids.append(f"{pose}_seed{seed}_zero")
            expected_ids.extend(f"{pose}_seed{seed}_joint{j}_amp{a:g}" for j in range(8) for a in AMPLITUDES)
    checks.equal([trial["trial_id"] for trial in trials], expected_ids, "full unique frozen matrix order")
    trial_map = {trial["trial_id"]: trial for trial in trials}
    profile_trials = {trial["trial_id"]: trial for trial in profile["trials"]}
    profile_pairs = {pair["trial_id"]: pair for pair in profile["pairs"]}
    checks.equal(set(profile_trials), set(expected_ids), "profile trial coverage")
    checks.equal(set(profile_pairs), {tid for tid in expected_ids if not tid.endswith("_zero")}, "profile paired coverage")
    zero_rows = {}
    responses = {}
    directions = {}
    phase_totals = {phase: Counter() for phase, _, _ in PHASES}
    nonzero_control_calls = 0
    trace_trial_order = []
    environment_hash = trials[0]["environment_fingerprint_before"]

    def audit_trial(tid, rows):
        nonlocal nonzero_control_calls
        trace_trial_order.append(tid)
        checks.test(tid in trial_map, "known trace trial")
        trial = trial_map[tid]
        p_trial = profile_trials[tid]
        joint, amplitude = trial["joint_index"], trial["amplitude_nm"]
        direction = trial["selected_direction"]
        pose_seed = (trial["pose"], trial["seed"])
        checks.equal(len(rows), 200, tid + " 200 trace rows")
        checks.equal(trial["status"], "completed", tid + " completed")
        checks.equal(trial["terminated"], False, tid + " no stop")
        checks.equal(trial["reason"], None, tid + " no reason")
        checks.equal(trial["invalid_numeric_fields"], [], tid + " finite trial")
        for key, value in dict(control_steps=200, control_calls_attempted=200, physics_steps=2000).items():
            checks.equal(trial[key], value, tid + " budget " + key)
        checks.equal(trial["environment_fingerprint_before"], environment_hash, tid + " common environment hash")
        checks.equal(trial["environment_fingerprint_after"], environment_hash, tid + " unchanged environment")
        checks.equal(trial["actor_fingerprint_before"], trial["actor_fingerprint_after"], tid + " unchanged actor")
        spec = trial["probe_spec"]
        checks.equal(spec["joint_ranges_rad"], limits, tid + " public ranges match asset")
        checks.equal(spec["config"]["joint_index"], joint, tid + " selected joint spec")
        checks.equal(spec["config"]["mode"], "zero" if joint is None else "pulse", tid + " mode spec")
        checks.equal(spec["config"]["amplitude_nm"], .5 if joint is None else amplitude, tid + " amplitude spec")
        for key, value in dict(prefix_steps=100, pulse_steps=25, recovery_steps=75).items():
            checks.equal(spec["config"][key], value, tid + " fixed schedule")
        actor_hash = hashlib.sha256(json.dumps(spec, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
        checks.equal(actor_hash, trial["actor_fingerprint_before"], tid + " independently hashed spec")
        checks.equal(trial["contact_configuration"]["profile"], "baseline", tid + " baseline contact")
        checks.equal(trial["contact_configuration"]["changes_from_asset"], [], tid + " unmodified contact")
        if joint is None:
            checks.equal(trial["mode"], "zero_torque", tid + " zero mode")
            checks.equal(amplitude, 0., tid + " zero amplitude")
            checks.equal(trial["selection_record"], None, tid + " no zero selection")
            checks.equal(direction, None, tid + " no zero direction")
            zero_rows[pose_seed] = rows
        else:
            checks.equal(trial["mode"], "joint_probe", tid + " pulse mode")
            q = rows[100]["observation_before"]["joint_position"][joint]
            lower, upper = limits[joint]
            expected_direction = 1 if upper - q >= q - lower else -1
            checks.equal(direction, expected_direction, tid + " public room direction")
            selection = dict(joint_index=joint, joint_position_rad=q, lower_limit_rad=lower,
                             upper_limit_rad=upper, positive_room_rad=upper-q, negative_room_rad=q-lower,
                             direction=expected_direction, selection_step=100,
                             rule="larger distance to the public joint limit; ties choose positive")
            checks.equal(trial["selection_record"], selection, tid + " exact selection record")
            key = (*pose_seed, joint)
            checks.equal(direction, directions.setdefault(key, direction), tid + " same direction across amplitudes")
            reference = zero_rows[pose_seed]
            for i in range(100):
                for field in FIELDS:
                    checks.equal(rows[i][field], reference[i][field], tid + " exact full prefix " + field)
            pair = profile_pairs[tid]
            checks.equal(pair["zero_trial_id"], f"{trial['pose']}_seed{trial['seed']}_zero", tid + " shared reference identity")
            checks.equal(pair["exact_prefix_replay"], True, tid + " profile exact prefix")
            checks.equal(pair["available"], True, tid + " pair available")
            checks.equal(pair["selected_direction"], direction, tid + " pair direction")
            for index, label in ((124, "pulse_end"), (199, "recovery_end")):
                delta = [rows[index]["observation_after"]["joint_position"][j]
                         - reference[index]["observation_after"]["joint_position"][j] for j in range(8)]
                changes = [rows[index]["observation_after"]["joint_position"][j]
                           - rows[99]["observation_after"]["joint_position"][j] for j in range(8)]
                checks.equal(pair[label]["paired_position_delta_rad_per_joint"], delta, tid + " exact paired endpoint " + label)
                checks.equal(pair[label]["native_trial_position_change_rad_per_joint"], changes, tid + " endpoint change " + label)
                checks.equal(pair[label]["target_joint_paired_delta_rad"], delta[joint], tid + " exact target delta " + label)
                checks.equal(pair[label]["target_joint_directed_paired_delta_rad"], direction * delta[joint], tid + " exact D " + label)
                if index == 124:
                    responses[(trial["pose"], joint, amplitude, trial["seed"])] = direction * delta[joint]
            differences = {phase: [rows[i]["observation_after"]["joint_position"][joint]
                                   - reference[i]["observation_after"]["joint_position"][joint]
                                   for i in range(start, end)] for phase, start, end in PHASES[1:]}
            for phase in ("probe", "recovery"):
                label = "pulse" if phase == "probe" else phase
                checks.equal(pair["target_maximum_absolute_paired_delta_during_" + label + "_rad"],
                             max(abs(d) for d in differences[phase]), tid + " maximum delta " + phase)
            checks.equal(pair["target_maximum_absolute_paired_delta_after_prefix_rad"],
                         max(abs(d) for phase in differences.values() for d in phase), tid + " overall maximum delta")
            crossing = next((i for i, d in enumerate(differences["probe"]) if direction * d >= .001), None)
            threshold = pair["first_recorded_pulse_threshold_crossing"]
            checks.equal(threshold["reached"], crossing is not None, tid + " threshold reached")
            checks.equal(threshold["pulse_action_index"], crossing, tid + " threshold index")
            checks.equal(threshold["threshold_rad"], .001, tid + " fixed threshold")
            expected_time = None if crossing is None else rows[100+crossing]["diagnostics"]["time"] - rows[99]["diagnostics"]["time"]
            checks.numeric(threshold["elapsed_from_pulse_start_seconds"], expected_time, tid + " threshold elapsed")
            for phase, start, end in PHASES[1:]:
                for sensor in ("joint_position", "joint_velocity", "imu_gyro", "imu_acceleration"):
                    vectors = [[a-b for a, b in zip(rows[i]["observation_after"][sensor], reference[i]["observation_after"][sensor])]
                               for i in range(start, end)]
                    checks.numeric(pair["paired_native_rms"][phase][sensor], rms(vectors), tid + " paired native RMS")
        for i, row in enumerate(rows):
            context = tid + f" row{i}"
            checks.finite(row, context)
            checks.equal(row.get("collector_exception"), None, context + " no exception")
            checks.equal(row["invalid_numeric_fields"], [], context + " valid values")
            for field in ("pose", "seed", "joint_index", "amplitude_nm", "mode"):
                checks.equal(row[field], trial[field], context + " label " + field)
            phase = "prefix" if i < 100 else ("probe" if i < 125 else "recovery")
            checks.equal(row["phase"], phase, context + " phase")
            checks.equal(row["action_index"], i-100 if phase == "probe" else None, context + " action index")
            d = row["diagnostics"]
            checks.equal(d["step_id"], i+1, context + " step")
            checks.equal(d["physics_steps"], (i+1)*10, context + " physical count")
            checks.equal(d["executed_substeps"], 10, context + " all substeps")
            checks.numeric(d["time"], .02*(i+1), context + " physical time")
            checks.equal(d["terminated"], False, context + " no stop")
            checks.equal(d["reason"], None, context + " no stop reason")
            requested = [0.] * 8
            if joint is not None and phase == "probe":
                requested[joint] = direction * amplitude
                nonzero_control_calls += 1
            checks.equal(d["requested_torque"], requested, context + " exact single-joint request")
            checks.equal(d["accepted_torque"], requested, context + " accepted request")
            history = d["applied_torque_history"]
            checks.equal(len(history), 10, context + " torque history length")
            for torque in history:
                checks.equal(len(torque), 8, context + " applied vector length")
                for j, value in enumerate(torque):
                    checks.test(abs(value) <= .5 and value in (0., requested[j]), context + " fixed permission")
            checks.equal(d["guarded_substeps"], sum(torque != requested for torque in history), context + " guard count")
            checks.equal(d["applied_torque"], history[-1], context + " last actual torque")
            checks.equal(row["observation_after"]["actuator_torque"], history[-1], context + " native actual torque")
            checks.equal(row["observation_after"]["previous_command"], requested, context + " native requested command")
            checks.equal(row["qpos"][7:], row["observation_after"]["joint_position"], context + " native encoder identity")
            checks.equal(row["qvel"][6:], row["observation_after"]["joint_velocity"], context + " native velocity identity")
            if i:
                checks.equal(row["observation_before"], rows[i-1]["observation_after"], context + " causal observation continuity")
            for key in ("substep_ground_normal_forces", "substep_kinetic_energies", "substep_minimum_contact_distances"):
                checks.equal(len(d[key]), 10, context + " telemetry length")
            checks.equal(d["peak_substep_ground_normal_force"], max(d["substep_ground_normal_forces"]), context + " force peak")
            checks.equal(d["peak_substep_kinetic_energy"], max(d["substep_kinetic_energies"]), context + " energy peak")
            checks.equal(d["minimum_substep_contact_distance"], min(d["substep_minimum_contact_distances"]), context + " minimum distance")
            checks.numeric(d["ground_normal_impulse_ns"], sum(d["substep_ground_normal_forces"])*.002, context + " force impulse")
        for phase, start, end in PHASES:
            expected_budget = dict(control_calls_attempted=end-start, control_steps=end-start, physics_steps=(end-start)*10)
            checks.equal(trial["phase_budgets"][phase], expected_budget, tid + " phase budget")
            phase_totals[phase].update(expected_budget)
            recomputed = phase_metrics(rows[start:end], joint, direction)
            checks.numeric(p_trial["phases"][phase], recomputed, tid + " independent phase metrics")
            if joint is not None and phase == "probe":
                checks.numeric(profile_pairs[tid]["pulse_action_metrics"], recomputed, tid + " pulse metrics")

    current_id, buffer = None, []
    with gzip.open(directory / "trace.jsonl.gz", "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            tid = row["trial_id"]
            if current_id is not None and current_id != tid:
                audit_trial(current_id, buffer)
                buffer = []
            current_id = tid
            buffer.append(row)
        if current_id is not None:
            audit_trial(current_id, buffer)
    checks.equal(trace_trial_order, expected_ids, "trace unique complete matrix order")
    checks.equal(len(zero_rows), 12, "12 actual zero references")
    checks.equal(len(responses), 288, "288 actual directed responses")
    checks.equal(nonzero_control_calls, 7200, "actual nonzero request calls")
    for phase, budget in phase_totals.items():
        checks.equal(dict(budget), metadata["phase_budgets"][phase], "aggregate phase budget " + phase)
    gates = {(g["pose"], g["joint_index"], g["amplitude_nm"]): g for g in profile["measurement_gates"]}
    checks.equal(len(gates), 96, "96 measurement gates")
    for (pose, joint, amplitude), gate in gates.items():
        values = [responses[(pose, joint, amplitude, seed)] for seed in expected_seeds]
        checks.equal(gate["seeds"], expected_seeds, "gate seed labels")
        checks.equal(gate["directed_pulse_end_deltas_rad"], values, "all exact gate D")
        checks.equal(gate["passes"], all(v >= .001 for v in values), "fixed >= threshold gate")
        checks.numeric(gate["minimum_directed_pulse_end_delta_rad"], min(values), "gate minimum")
        checks.numeric(gate["mean_directed_pulse_end_delta_rad"], sum(values)/3, "gate mean")
    checks.equal(len(profile["dose_response"]), 32, "32 dose-response curves")
    for curve in profile["dose_response"]:
        pose, joint = curve["pose"], curve["joint_index"]
        checks.equal([a["amplitude_nm"] for a in curve["amplitudes"]], list(AMPLITUDES), "dose amplitudes")
        for amplitude, summary in zip(AMPLITUDES, curve["amplitudes"]):
            values = [responses[(pose, joint, amplitude, seed)] for seed in expected_seeds]
            checks.numeric(summary["mean_directed_pulse_end_delta_rad"], sum(values)/3, "dose mean")
            checks.numeric(summary["minimum_directed_pulse_end_delta_rad"], min(values), "dose minimum")
            checks.numeric(summary["maximum_directed_pulse_end_delta_rad"], max(values), "dose maximum")
        checks.equal([c["seed"] for c in curve["seed_curves"]], expected_seeds, "dose all seed coverage")
        for seed_curve in curve["seed_curves"]:
            values = [responses[(pose, joint, a, seed_curve["seed"])] for a in AMPLITUDES]
            checks.equal(seed_curve["directed_pulse_end_deltas_rad"], values, "three exact per-seed D")
    return dict(split=expected_split, archive=str(directory), profile=str(profile_path),
                source_commit=metadata["source_commit"], input_sha256={**manifest, "manifest.json": sha(directory/"manifest.json"),
                "analysis_profile": sha(profile_path)}, checks=checks.count-before,
                trials=300, control_calls=60000, physics_steps=600000, source_sha256=hashes), responses


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--development", type=Path, required=True)
    parser.add_argument("--development-profile", type=Path, required=True)
    parser.add_argument("--holdout", type=Path, required=True)
    parser.add_argument("--holdout-profile", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    directories = [args.development.resolve(), args.holdout.resolve()]
    profiles = [args.development_profile.resolve(), args.holdout_profile.resolve()]
    output = args.output.resolve()
    if output.exists() or any(output.is_relative_to(d) for d in directories) or output in profiles:
        parser.error("output must not exist and must be outside all input archives/profiles")
    if not output.parent.is_dir():
        parser.error("output parent must already exist")
    for directory, profile in zip(directories, profiles):
        if not directory.is_dir() or not profile.is_file():
            parser.error("complete input archives and profile files are required")
    root = Path(__file__).resolve().parents[1]
    checks = Checks()
    reports, response_sets = [], []
    for directory, profile, split, seeds, commit in zip(directories, profiles,
            ("development", "holdout"), ([0,1,2], [10,11,12]), ("61df2d0", "fadef21")):
        try:
            report, responses = audit_archive(directory, profile, split, seeds, commit, checks, root)
            reports.append(report)
            response_sets.append(responses)
        except Exception as exc:
            checks.test(False, split + " structural audit exception: " + type(exc).__name__ + ": " + str(exc))
    combined = []
    if len(reports) == 2:
        left, right = (r["source_sha256"] for r in reports)
        checks.equal(set(left), set(right), "cross-split snapshot path identity")
        changed = [name for name in left if left[name] != right.get(name)]
        checks.equal(changed, ["src/developmental_physics/local_learning.py"], "only unused learning runner differs")
        for name in CORE:
            checks.equal(left[name], right[name], "identical active source across splits " + name)
        for pose in POSES:
            for joint in range(8):
                values = [response_sets[0][(pose,joint,.5,s)] for s in (0,1,2)] + [
                          response_sets[1][(pose,joint,.5,s)] for s in (10,11,12)]
                combined.append(dict(pose=pose, joint_index=joint, joint_name=NAMES[joint],
                    amplitude_nm=.5, seeds=[0,1,2,10,11,12], directed_pulse_end_deltas_rad=values,
                    minimum_directed_delta_rad=min(values), passes=all(v >= .001 for v in values)))
        checks.test(any(g["passes"] for g in combined), "at least one same pose/joint passes all six fixed gates")
    report = dict(schema_version=1, created_at_utc=datetime.now(timezone.utc).isoformat(),
        audit_type="Independent standard-library read-only probe audit; no project/NumPy/MuJoCo imports or fitting",
        audit_script_sha256=sha(__file__), python=sys.version, checks=checks.count,
        failed_checks=checks.failed, failures=checks.failures,
        maximum_numeric_difference=checks.maximum_numeric_difference, archives=reports,
        combined_half_nm_gates=combined, passed_same_pose_joint_count=sum(g["passes"] for g in combined),
        claim_boundary="Local repeatable native response gate only; not safety, learning or motion skill.")
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({key: report[key] for key in ("checks", "failed_checks", "maximum_numeric_difference", "passed_same_pose_joint_count")}))
    return 1 if checks.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
