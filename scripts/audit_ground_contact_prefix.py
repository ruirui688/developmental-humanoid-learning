"""Audit the frozen 96-case contact/prefix archive with scalar standard-library math.

No project imports, random-action generation, NumPy, simulation or fitting.
Only listed manifest entries are covered; the audit output stays outside inputs.
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
import xml.etree.ElementTree as ET
import zipfile


ROOT = Path(__file__).resolve().parents[1]
HISTORY = ROOT / "results/cpu_validation"
DEFAULT_REFERENCE = HISTORY / "2026-10-10_ground_impacts"
POSES = ("supine", "prone", "left_side", "right_side")
MODES = ("zero_torque", "smooth_random")
JOINTS = ("left_shoulder", "left_elbow", "right_shoulder", "right_elbow",
          "left_hip", "left_knee", "right_hip", "right_knee")
CONFIG = {"physics_dt": .002, "control_substeps": 10, "torque_limit": .5,
          "joint_speed_limit": 20., "joint_limit_margin": .08,
          "kinetic_energy_limit": 50., "reset_clearance": .005,
          "ground_contact_profile": "baseline"}
NATIVE = {"joint_position": 8, "joint_velocity": 8, "imu_gyro": 3,
          "imu_acceleration": 3, "actuator_torque": 8, "previous_command": 8}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def read_rows(path):
    groups, order = defaultdict(list), []
    with gzip.open(path / "trace.jsonl.gz", "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            tid = row["trial_id"]
            if not order or order[-1] != tid:
                order.append(tid)
            groups[tid].append(row)
    return groups, order


class Checks:
    def __init__(self):
        self.count = self.failed = self.numbers = 0
        self.maximum_difference = 0.
        self.violations = []

    def check(self, condition, name, detail=None):
        self.count += 1
        if not condition:
            self.failed += 1
            if len(self.violations) < 200:
                self.violations.append({"check": name, "detail": detail})

    def near(self, actual, expected, name, detail=None):
        valid = (type(actual) in (int, float) and math.isfinite(actual)
                 and type(expected) in (int, float) and math.isfinite(expected))
        error = abs(actual - expected) if valid else None
        if valid:
            self.maximum_difference = max(self.maximum_difference, error)
        self.check(valid and error <= 1e-10 + 1e-12 * abs(expected), name,
                   {"location": detail, "actual": actual, "expected": expected, "difference": error})

    def compare(self, actual, expected, path):
        if isinstance(expected, dict):
            self.check(isinstance(actual, dict), "metric_object", path)
            if isinstance(actual, dict):
                self.check(set(expected).issubset(actual), "metric_fields", path)
                for key, value in expected.items():
                    self.compare(actual.get(key), value, path + "/" + key)
        elif isinstance(expected, list):
            self.check(isinstance(actual, list) and len(actual) == len(expected), "metric_list_shape", path)
            if isinstance(actual, list):
                for index, (a, b) in enumerate(zip(actual, expected)):
                    self.compare(a, b, path + "/" + str(index))
        elif type(expected) is float:
            self.near(actual, expected, "scalar_metric_recomputation", path)
        else:
            self.check(actual == expected, "metric_label_or_count", path)

    def finite(self, value, path):
        if type(value) is float:
            self.numbers += 1
            self.check(math.isfinite(value), "finite_number", path)
        elif isinstance(value, dict):
            for key, item in value.items():
                self.finite(item, path + "/" + str(key))
        elif isinstance(value, list):
            for index, item in enumerate(value):
                self.finite(item, path + "/" + str(index))


def action_metrics(rows):
    n = 0
    sums = {key: [0.] * 8 for key in ("request_sq", "apply_sq", "request_signed",
                                     "apply_signed", "request_abs", "apply_abs", "increment_sq")}
    nonzero, blocked = [0] * 8, [0] * 8
    for row in rows:
        diagnostic = row["diagnostics"]
        command = diagnostic["requested_torque"]
        history = diagnostic["applied_torque_history"]
        n += len(history)
        for j in range(8):
            delta = row["observation_after"]["joint_position"][j] - row["observation_before"]["joint_position"][j]
            sums["increment_sq"][j] += delta * delta
            for applied in history:
                request, actual = command[j], applied[j]
                sums["request_sq"][j] += request * request
                sums["apply_sq"][j] += actual * actual
                sums["request_signed"][j] += request
                sums["apply_signed"][j] += actual
                sums["request_abs"][j] += abs(request)
                sums["apply_abs"][j] += abs(actual)
                nonzero[j] += int(request != 0.)
                blocked[j] += int(request != 0. and actual == 0.)
    result = {"control_rows": len(rows), "executed_physics_substeps": n,
              "executed_seconds": n * .002,
              "requested_torque_rms_nm_per_joint": [math.sqrt(x / n) for x in sums["request_sq"]] if n else None,
              "applied_torque_rms_nm_per_joint": [math.sqrt(x / n) for x in sums["apply_sq"]] if n else None,
              "applied_torque_rms_nm_all_joints": math.sqrt(sum(sums["apply_sq"]) / (8 * n)) if n else None,
              "nonzero_requested_substeps_per_joint": nonzero,
              "blocked_nonzero_request_substeps_per_joint": blocked,
              "blocked_fraction_of_nonzero_requested_substeps_per_joint": [None if not den else num / den for num, den in zip(blocked, nonzero)],
              "blocked_fraction_of_all_executed_substeps_per_joint": [num / n for num in blocked] if n else None,
              "native_position_step_increment_rms_rad_per_joint": [math.sqrt(x / len(rows)) for x in sums["increment_sq"]] if rows else None,
              "native_position_step_increment_rms_rad_all_joints": math.sqrt(sum(sums["increment_sq"]) / (8 * len(rows))) if rows else None}
    for side, prefix in (("requested", "request"), ("applied", "apply")):
        for kind in ("signed", "absolute"):
            result[f"{side}_{kind}_torque_integral_nms_per_joint"] = [x * .002 for x in sums[prefix + ("_abs" if kind == "absolute" else "_signed")]]
    return result


def substep_metrics(rows):
    force, energy, distance, times = [], [], [], []
    for row in rows:
        d = row["diagnostics"]
        n = d["executed_substeps"]
        force.extend(d["substep_ground_normal_forces"])
        energy.extend(d["substep_kinetic_energies"])
        distance.extend(d["substep_minimum_contact_distances"])
        times.extend(d["time"] - (n - 1 - i) * .002 for i in range(n))
    if not force:
        return {"physics_samples": 0, "peak_ground_normal_force_n": None,
                "ground_normal_impulse_ns": None, "peak_kinetic_energy_j": None,
                "minimum_contact_distance_m": None, "peak_force_time_seconds": None}
    index = max(range(len(force)), key=lambda i: force[i])
    return {"physics_samples": len(force), "peak_ground_normal_force_n": force[index],
            "peak_force_time_seconds": times[index], "ground_normal_impulse_ns": sum(force) * .002,
            "peak_kinetic_energy_j": max(energy), "minimum_contact_distance_m": min(distance)}


def audit(archive, reference=DEFAULT_REFERENCE, profile_path=None):
    profile_path = profile_path or archive / "contact_prefix_profile.json"
    c = Checks()
    inputs = {}

    def load(path):
        inputs[str(path.resolve())] = sha(path)
        return read_json(path)

    metadata, trials = load(archive / "metadata.json"), load(archive / "trials.json")
    geometry = load(archive / "geometry.json")
    profile = load(profile_path)
    inputs[str((archive / "trace.jsonl.gz").resolve())] = sha(archive / "trace.jsonl.gz")
    inputs[str((archive / "source_snapshot.zip").resolve())] = sha(archive / "source_snapshot.zip")
    manifests = []
    for folder in (archive, reference):
        for filename in ("collection_manifest.json", "manifest.json"):
            path = folder / filename
            if not path.exists():
                continue
            manifest = load(path)
            c.check({"metadata.json", "trials.json", "geometry.json", "source_snapshot.zip", "trace.jsonl.gz"}.issubset(manifest),
                    "manifest_core_coverage", str(path))
            for name, digest in manifest.items():
                target = (folder / name).resolve()
                c.check(target.is_relative_to(folder.resolve()) and target.is_file(), "manifest_local_file", name)
                if target.is_file():
                    c.check(sha(target) == digest, "manifest_sha256", [str(folder), name])
            manifests.append({"path": str(path.resolve()), "entries": manifest,
                              "files_not_listed_at_read": sorted(p.name for p in folder.iterdir() if p.is_file() and p.name != filename and p.name not in manifest)})
    c.check(any(item["path"] == str((archive / "manifest.json").resolve()) for item in manifests), "new_manifest_present")
    source_records = []
    with zipfile.ZipFile(archive / "source_snapshot.zip") as snapshot:
        names = snapshot.namelist()
        c.check(len(names) == len(set(names)) and set(names) == set(metadata["source_sha256"]), "source_member_set")
        expected_sources = {"src/developmental_physics/" + name for name in (
            "__init__.py", "collect.py", "environment.py", "exploration.py", "assets/ground_body.xml"
        )} | {"pyproject.toml", "docs/GROUND_CONTACT_PREFIX_PROTOCOL.md"}
        c.check(set(names) == expected_sources, "frozen_seven_source_members")
        source_bytes = {name: snapshot.read(name) for name in names}
        for name, content in source_bytes.items():
            digest = hashlib.sha256(content).hexdigest()
            blob = subprocess.check_output(["git", "show", metadata["source_commit"] + ":" + name], cwd=ROOT)
            c.check(digest == metadata["source_sha256"][name], "source_sha256", name)
            c.check(content == blob, "source_git_blob_exact_bytes", name)
            source_records.append({"path": name, "sha256": digest, "git_blob_sha256": hashlib.sha256(blob).hexdigest(), "exact_bytes": content == blob})
    asset_name = "src/developmental_physics/assets/ground_body.xml"
    c.check(metadata["asset_sha256"] == metadata["source_sha256"][asset_name], "asset_identity")
    protocol = metadata["protocol"]
    c.check(protocol["path"] == "docs/GROUND_CONTACT_PREFIX_PROTOCOL.md" and protocol["sha256"] == metadata["source_sha256"][protocol["path"]], "protocol_snapshot_identity")
    c.check(not metadata["source_dirty"] and metadata["source_status"] == "", "clean_source_record")
    c.check(metadata["complete"] and metadata["archive_status"] == "complete", "completed_archive")
    c.check(metadata.get("invalid_numeric_fields") == [], "metadata_invalid_markers")
    c.check(metadata["schema_version"] == 3 and metadata["config"] == CONFIG, "frozen_config")
    c.check(metadata["poses"] == list(POSES) and metadata["seeds"] == [0, 1, 2], "frozen_poses_seeds")
    c.check(metadata["contact_profiles"] == ["baseline", "compliant"] and metadata["prefix_steps"] == [0, 100], "frozen_conditions")
    c.check(metadata["steps_per_trial_limit"] == 250, "trial_step_limit")
    c.check(metadata["mujoco_version"] == "3.15.0" and metadata["dynamics_backend"] == "MuJoCo CPU" and metadata["gpu"] is None, "backend_record")
    c.check(metadata["parameter_updates"] == {"model": 0, "policy": 0, "gate": 0} and metadata["teacher_calls"] == metadata["external_demonstration_samples"] == 0, "zero_learning_prior_records")
    c.check(metadata["exploration"]["smoothing"] == .9 and metadata["exploration"]["feedback_used_for_action_selection"] is False, "fixed_exploration")
    for contact in ("baseline", "compliant"):
        expected = dict(CONFIG, ground_contact_profile=contact)
        c.check(metadata["profile_configs"][contact] == expected, "profile_config", contact)

    expected_cases = [(contact, prefix, pose, seed, mode) for pose in POSES for seed in (0, 1, 2)
                      for contact in ("baseline", "compliant") for prefix in (0, 100) for mode in MODES]
    expected_ids = [f"{contact}_prefix{prefix}_{pose}_seed{seed}_{mode}" for contact, prefix, pose, seed, mode in expected_cases]
    by_id = {t["trial_id"]: t for t in trials}
    c.check(len(trials) == len(by_id) == metadata["trial_count"] == metadata["expected_trial_count"] == 96, "unique_96_trials")
    c.check([t["trial_id"] for t in trials] == expected_ids, "frozen_trial_order_and_cases")
    c.check([item["trial_id"] for item in geometry] == expected_ids, "geometry_trial_identity")
    groups, trace_order = read_rows(archive)
    c.check(trace_order == expected_ids and set(groups) == set(expected_ids), "trace_full_case_blocks")
    c.finite(metadata, "metadata")
    c.finite(trials, "trials")
    c.finite(geometry, "geometry")
    c.finite(profile, "profile")

    asset = ET.fromstring(source_bytes[asset_name])
    default_geom = asset.find("./default/geom").attrib
    original_solref = [float(x) for x in default_geom["solref"].split()]
    original_solimp = [float(x) for x in default_geom["solimp"].split()] + [.5, 2.]
    original_friction = [float(x) for x in default_geom["friction"].split()]
    geometry_names = [g.attrib["name"] for g in asset.findall("./worldbody//geom")]
    c.check(original_solref == [.01, 1.] and original_solimp == [.9, .95, .001, .5, 2.] and original_friction == [.8, .02, .002], "frozen_asset_contact_defaults")
    baseline_body = None
    sums = defaultdict(int)
    computed = {}
    environment_hashes, actor_hashes = defaultdict(set), set()
    for tid, trial in by_id.items():
        rows = groups.get(tid, [])
        prefix, contact, mode = trial["prefix_steps"], trial["contact_profile"], trial["mode"]
        c.check(tid == f"{contact}_prefix{prefix}_{trial['pose']}_seed{trial['seed']}_{mode}", "trial_identity", tid)
        c.check(trial["environment_config"] == dict(CONFIG, ground_contact_profile=contact), "actual_trial_config", tid)
        c.check(len(rows) == trial["control_steps"] == trial["metric_samples"] == trial["control_calls_attempted"] == 250, "trial_control_attempt_budget", tid)
        c.check(trial["status"] == "completed" and not trial["terminated"] and trial["reason"] is None and trial["collector_exception"] is None, "trial_complete_without_hidden_failure", tid)
        c.check(trial.get("invalid_numeric_fields") == [], "trial_invalid_markers", tid)
        c.check(trial["environment_fingerprint_before"] == trial["environment_fingerprint_after"] and bool(trial["environment_fingerprint_before"]), "fixed_environment_fingerprint", tid)
        c.check(trial["explorer_fingerprint_before"] == trial["explorer_fingerprint_after"] and bool(trial["explorer_fingerprint_before"]), "fixed_explorer_fingerprint", tid)
        c.check(trial["model_updates"] == trial["policy_updates"] == trial["gate_updates"] == 0, "trial_zero_updates", tid)
        environment_hashes[contact].add(trial["environment_fingerprint_before"])
        actor_hashes.add(trial["explorer_fingerprint_before"])
        c.check(trial["reset_seed"] != trial["exploration_seed"], "separate_random_stream_ids", tid)
        cc = trial["contact_configuration"]
        floor = cc["floor"]
        c.check(cc["profile"] == contact and floor["name"] == "floor" and floor["geom_id"] == 0, "actual_floor_identity", tid)
        c.check([floor["name"]] + [g["name"] for g in cc["body_geoms"]] == geometry_names, "all_contact_geometries", tid)
        for geom in [floor] + cc["body_geoms"]:
            is_floor = geom["name"] == "floor"
            c.check(geom["solref"] == ([.05, 1.] if is_floor and contact == "compliant" else original_solref), "actual_geom_solref", [tid, geom["name"]])
            c.check(geom["priority"] == (1 if is_floor and contact == "compliant" else 0) and geom["condim"] == 3 and geom["solmix"] == 1., "actual_contact_selection_parameters", [tid, geom["name"]])
            c.check(geom["solimp"] == original_solimp and geom["friction"] == original_friction, "unchanged_impedance_friction", [tid, geom["name"]])
        if baseline_body is None:
            baseline_body = cc["body_geoms"]
        c.check(cc["body_geoms"] == baseline_body, "identical_body_contact_parameters", tid)
        changes = cc["changes_from_asset"]
        expected_changes = [] if contact == "baseline" else [
            {"geom_id": 0, "name": "floor", "field": "priority", "asset": 0, "actual": 1},
            {"geom_id": 0, "name": "floor", "field": "solref", "asset": [.01, 1.], "actual": [.05, 1.]},
        ]
        c.check(changes == expected_changes and cc["change_scope"]["fields"] == ([] if contact == "baseline" else ["solref[0]", "priority"]), "only_declared_floor_changes", tid)
        c.check(cc["change_scope"]["geometry"] == "floor", "declared_change_geometry", tid)
        initial = trial["initial_qpos"]
        c.check(len(initial) == 15 and rows and rows[0]["observation_before"]["joint_position"] == initial[7:], "initial_native_pose", tid)
        if rows:
            c.check(rows[0]["observation_before"]["joint_velocity"] == [0.] * 8 and rows[0]["observation_before"]["previous_command"] == [0.] * 8, "zero_initial_velocity_command", tid)
        physical = guarded = interventions = ground = 0
        previous_time = 0.
        for index, row in enumerate(rows):
            d = row["diagnostics"]
            location = [tid, index]
            c.finite(row, tid + "/row" + str(index))
            c.check(row.get("invalid_numeric_fields") == [] and "collector_exception" not in row, "valid_trace_record", location)
            phase = "prefix" if index < prefix else "exploration"
            c.check(row["contact_profile"] == contact and row["prefix_steps"] == prefix and row["phase"] == phase and row["action_index"] == (None if phase == "prefix" else index - prefix), "phase_action_index", location)
            for label in ("observation_before", "observation_after"):
                observation = row[label]
                c.check(set(observation) == set(NATIVE), "native_schema", location + [label])
                for key, size in NATIVE.items():
                    values = observation[key]
                    c.check(isinstance(values, list) and len(values) == size and all(type(x) in (int, float) and math.isfinite(x) for x in values), "native_finite_shape", location + [label, key])
            if index:
                c.check(row["observation_before"] == rows[index - 1]["observation_after"], "continuous_observation_no_reset", location)
            c.check(len(row["qpos"]) == 15 and len(row["qvel"]) == 14, "physical_state_shapes", location)
            c.check(row["qpos"][7:] == row["observation_after"]["joint_position"] and row["qvel"][6:] == row["observation_after"]["joint_velocity"], "native_state_alignment", location)
            c.check(d["step_id"] == index + 1 and not d["terminated"] and d["reason"] is None, "step_result_record", location)
            n = d["executed_substeps"]
            c.check(n == 10, "full_control_substeps", location)
            physical += n
            c.check(d["physics_steps"] == physical, "physics_counter", location)
            c.near(d["time"] - previous_time, n * .002, "physical_time_delta", location)
            previous_time = d["time"]
            history = d["applied_torque_history"]
            c.check(len(history) == n and all(len(x) == 8 for x in history), "actual_action_substep_exposure", location)
            request, accepted = d["requested_torque"], d["accepted_torque"]
            c.check(len(request) == len(accepted) == 8 and accepted == [max(-.5, min(.5, x)) for x in request], "declared_torque_clip", location)
            if phase == "prefix" or mode == "zero_torque":
                c.check(request == [0.] * 8 and all(x == [0.] * 8 for x in history), "zero_command_prefix_or_control", location)
            blocked_steps = sum(any(a != b for a, b in zip(applied, accepted)) for applied in history)
            c.check(d["guarded_substeps"] == blocked_steps and all(a == 0. or a == accepted[j] for applied in history for j, a in enumerate(applied)), "guarded_actual_command_accounting", location)
            c.check(d["applied_torque"] == (history[-1] if history else [0.] * 8), "last_applied_history_alignment", location)
            c.check(row["observation_after"]["previous_command"] == accepted, "native_previous_command", location)
            guarded += blocked_steps
            interventions += int(blocked_steps > 0 or request != d["applied_torque"])
            ground += int(d["ground_contact_count"] > 0)
            arrays = [d[key] for key in ("substep_ground_normal_forces", "substep_kinetic_energies", "substep_minimum_contact_distances")]
            c.check(all(len(values) == n for values in arrays), "telemetry_substep_exposure", location)
            f, e, dist = arrays
            c.check(all(x >= 0 for x in f + e), "nonnegative_force_energy", location)
            c.check(d["peak_substep_ground_normal_force"] == max(f, default=0.) and d["peak_substep_kinetic_energy"] == max(e, default=0.) and d["minimum_substep_contact_distance"] == min(dist, default=0.), "substep_extrema", location)
            c.near(d["ground_normal_impulse_ns"], sum(f) * .002, "substep_force_integral", location)
            if n:
                c.check(f[-1] == d["ground_normal_force"] and e[-1] == d["kinetic_energy"] and dist[-1] == d["minimum_contact_distance"], "telemetry_endpoint_alignment", location)
        c.check(physical == trial["physics_steps"] == 2500, "trial_physics_budget", tid)
        c.near(trial["simulated_seconds"], physical * .002, "trial_physical_time", tid)
        c.check(trial["final_qpos"] == rows[-1]["qpos"] if rows else False, "final_pose_alignment", tid)
        c.check(trial["guarded_physics_substeps"] == guarded and trial["command_intervention_steps"] == interventions and trial["ground_contact_steps"] == ground, "trial_intervention_counts", tid)
        expected_budget = {"control_steps": len(rows), "control_calls_attempted": len(rows), "physics_steps": physical,
                           "prefix_control_steps": min(len(rows), prefix), "prefix_control_calls_attempted": min(len(rows), prefix),
                           "prefix_physics_steps": sum(r["diagnostics"]["executed_substeps"] for r in rows[:prefix]),
                           "exploration_control_steps": max(0, len(rows) - prefix), "exploration_control_calls_attempted": max(0, len(rows) - prefix),
                           "exploration_physics_steps": sum(r["diagnostics"]["executed_substeps"] for r in rows[prefix:])}
        for key, value in expected_budget.items():
            c.check(trial[key] == value, "trial_phase_budget", [tid, key])
            sums[key] += value
        active = rows[prefix:]
        computed[tid] = {"whole_trial": substep_metrics(rows), "prefix_phase": substep_metrics(rows[:prefix]),
                         "active_phase": substep_metrics(active), "active_action_metrics": action_metrics(active),
                         "shared_active_window": {"requested_control_steps": 150, "available_control_steps": min(150, len(active)),
                                                  "complete": len(active) >= 150, "action_metrics": action_metrics(active[:150]),
                                                  "substep_metrics": substep_metrics(active[:150])}}
    c.check(all(len(values) == 1 for values in environment_hashes.values()) and len(actor_hashes) == 1, "shared_fixed_parameter_hashes")
    c.check(environment_hashes["baseline"].isdisjoint(environment_hashes["compliant"]), "different_environment_condition_hashes")
    expected_totals = {"control_steps": 24000, "control_calls_attempted": 24000, "physics_steps": 240000,
                       "prefix_control_steps": 4800, "prefix_control_calls_attempted": 4800, "prefix_physics_steps": 48000,
                       "exploration_control_steps": 19200, "exploration_control_calls_attempted": 19200, "exploration_physics_steps": 192000}
    for key, value in expected_totals.items():
        c.check(sums[key] == metadata[key] == value, "matrix_phase_budget", key)
    c.check(metadata["maximum_control_steps"] == 24000 and metadata["maximum_physics_steps"] == 240000 and metadata["terminated_trials"] == metadata["exception_trials"] == 0, "frozen_maximum_and_outcomes")

    analyzed = {t["trial_id"]: t for t in profile["trials"]}
    c.check(len(analyzed) == len(profile["trials"]) == profile["trial_count"] == profile["expected_trial_count"] == 96 and set(analyzed) == set(by_id), "analysis_96_unique_trials")
    c.check(profile["shared_active_steps"] == 150 and profile["joint_order"] == list(JOINTS) and profile["source_commit"] == metadata["source_commit"] and not profile["source_dirty"], "analysis_frozen_identity")
    c.check(profile["missing_trial_ids"] == profile["orphan_trace_trial_ids"] == profile["metrics_unavailable_trial_ids"] == profile["terminated_trial_ids"] == [], "analysis_complete_cases")
    c.check(profile["parameter_updates"] == {"model": 0, "policy": 0, "gate": 0} and profile["analysis_parameter_updates"] == 0, "analysis_zero_updates")
    c.check(profile["analysis_script_sha256"] == sha(ROOT / "scripts/analyze_ground_contact_prefix.py"), "analysis_script_hash")
    expected_analysis_inputs = {path.resolve() for path in (
        *(archive / name for name in ("metadata.json", "trials.json", "trace.jsonl.gz", "source_snapshot.zip")),
        *(reference / name for name in ("metadata.json", "trials.json", "trace.jsonl.gz")),
    )}
    c.check({Path(name).resolve() for name in profile["input_sha256"]} == expected_analysis_inputs, "analysis_input_hash_coverage")
    for name, digest in profile["input_sha256"].items():
        c.check(sha(Path(name)) == digest, "analysis_input_hash", name)
    c.compare(profile["budget"], dict(sums), "analysis/budget")
    for tid, summary in computed.items():
        stored = analyzed[tid]
        copied_fields = ("trial_id", "contact_profile", "prefix_steps", "pose", "seed", "mode", "status",
                         "terminated", "reason", "control_steps", "control_calls_attempted", "physics_steps",
                         "reset_seed", "exploration_seed", "prefix_control_calls_attempted",
                         "exploration_control_calls_attempted", "prefix_control_steps", "prefix_physics_steps",
                         "exploration_control_steps", "exploration_physics_steps")
        c.compare(stored, {key: by_id[tid][key] for key in copied_fields}, "analysis/trial_identity_budget/" + tid)
        c.check(stored["trace_rows"] == 250 and stored["invalid_trace_row_indices"] == [] and stored["collector_exception_rows"] == 0,
                "analysis_trial_valid_exposure", tid)
        c.check(stored["metrics_available"] is True and stored["missing_reason"] is None, "available_trial_metrics", tid)
        c.compare(stored, summary, "analysis/trials/" + tid)
        endpoint_row = groups[tid][by_id[tid]["prefix_steps"] - 1] if by_id[tid]["prefix_steps"] else None
        obs = endpoint_row["observation_after"] if endpoint_row else groups[tid][0]["observation_before"]
        endpoint = {"available": True, "control_steps": by_id[tid]["prefix_steps"],
                    "time_seconds": endpoint_row["diagnostics"]["time"] if endpoint_row else 0.,
                    "kinetic_energy_j": endpoint_row["diagnostics"]["kinetic_energy"] if endpoint_row else 0.,
                    "joint_speed_rad_s_per_joint": obs["joint_velocity"], "maximum_joint_speed_rad_s": max(abs(x) for x in obs["joint_velocity"]),
                    "native_gyro_rad_s": obs["imu_gyro"], "native_gyro_norm_rad_s": math.sqrt(sum(x*x for x in obs["imu_gyro"])), "stability_decision": None}
        c.compare(stored["prefix_endpoint"], endpoint, "prefix_endpoint/" + tid)
        counts = sorted({r["diagnostics"]["ground_contact_count"] for r in groups[tid][by_id[tid]["prefix_steps"]:]})
        expected_groups = [{"endpoint_ground_contact_count": count, "action_metrics": action_metrics([r for r in groups[tid][by_id[tid]["prefix_steps"]:] if r["diagnostics"]["ground_contact_count"] == count])} for count in counts]
        c.compare(stored["contact_endpoint_groups"], expected_groups, "contact_endpoint_groups/" + tid)

    old_metadata, old_trials = load(reference / "metadata.json"), load(reference / "trials.json")
    inputs[str((reference / "trace.jsonl.gz").resolve())] = sha(reference / "trace.jsonl.gz")
    old_groups, _ = read_rows(reference)
    maximum_replay_difference = 0.
    replay_trials = replay_rows = duplicate_rows = request_rows = 0
    for contact in ("baseline", "compliant"):
        for pose in POSES:
            for seed in (0, 1, 2):
                ids = {mode: [f"{contact}_prefix{prefix}_{pose}_seed{seed}_{mode}" for prefix in (0, 100)] for mode in MODES}
                for mode, tids in ids.items():
                    a, b = (by_id[tid] for tid in tids)
                    c.check(a["initial_qpos"] == b["initial_qpos"] and a["reset_seed"] == b["reset_seed"] and a["exploration_seed"] == b["exploration_seed"], "prefix_shared_initial_state_and_streams", tids)
                    left, right = (groups[tid] for tid in tids)
                    if mode == "zero_torque":
                        for index, (x, y) in enumerate(zip(left, right)):
                            for key in ("qpos", "qvel", "observation_before", "observation_after", "diagnostics"):
                                c.check(x[key] == y[key], "zero_prefix_duplicate_full_trajectory", [tids, index, key])
                            duplicate_rows += 1
                    else:
                        for index in range(150):
                            c.check(left[index]["diagnostics"]["requested_torque"] == right[index + 100]["diagnostics"]["requested_torque"], "random_prefix_shared_first150_requests", [tids, index])
                            request_rows += 1
                    if contact == "baseline":
                        original_id = f"{pose}_seed{seed}_{mode}"
                        original = old_groups[original_id]
                        c.check(len(original) == len(left) == 250, "reference_trial_rows", tids[0])
                        replay_trials += 1
                        for index, (row, old) in enumerate(zip(left, original)):
                            for key in ("qpos", "qvel", "observation_before", "observation_after"):
                                c.check(row[key] == old[key], "baseline_prefix0_exact_replay", [tids[0], index, key])
                            for key, value in old["diagnostics"].items():
                                c.check(row["diagnostics"].get(key) == value, "baseline_prefix0_all_shared_diagnostics", [tids[0], index, key])
                            for key in ("qpos", "qvel"):
                                maximum_replay_difference = max(maximum_replay_difference, *(abs(x-y) for x, y in zip(row[key], old[key])))
                            replay_rows += 1
    c.check(replay_trials == 24 and replay_rows == duplicate_rows == 6000 and request_rows == 3600, "exact_comparison_exposure_counts")
    c.check(profile["baseline_prefix0_reference_replay"]["exact"] is True and profile["baseline_prefix0_reference_replay"]["matched_trials"] == 24 and profile["baseline_prefix0_reference_replay"]["matched_control_rows"] == 6000, "analysis_reference_replay_record")
    c.check(profile["baseline_prefix0_reference_replay"]["missing_trial_ids"] == [] and profile["baseline_prefix0_reference_replay"]["differences"] == [], "analysis_no_replay_mismatch_records")
    invariance = profile["prefix_invariance"]
    for key, count_key, count in (("zero_prefix_duplicate_trajectory_checks", "matched_control_rows", 250), ("random_prefix_shared_request_checks", "matched_active_request_rows", 150)):
        records = invariance[key]
        expected_invariance_cases = {(contact, pose, seed) for contact in ("baseline", "compliant") for pose in POSES for seed in (0, 1, 2)}
        c.check(len(records) == 24 and {(r["contact_profile"], r["pose"], r["seed"]) for r in records} == expected_invariance_cases, "prefix_invariance_complete_records", key)
        c.check(all(r["available"] and r["exact"] and r[count_key] == count and r["mismatches"] == [] for r in records), "prefix_invariance_record_values", key)
        mode = "zero_torque" if count == 250 else "smooth_random"
        for record in records:
            for prefix in (0, 100):
                c.check(record[f"prefix{prefix}_trial_id"] == f"{record['contact_profile']}_prefix{prefix}_{record['pose']}_seed{record['seed']}_{mode}",
                        "prefix_invariance_trial_id_binding", key)
    c.check(invariance["all_available_and_exact"] is True, "analysis_prefix_invariance")

    paired = profile["paired_active_responses"]
    c.check(len(paired) == 48 and len({(r["contact_profile"], r["prefix_steps"], r["pose"], r["seed"]) for r in paired}) == 48, "48_unique_active_pairs")
    recomputed_pairs = []
    for record in paired:
        a, b = (by_id[record[key]] for key in ("random_trial_id", "zero_trial_id"))
        c.check(a["mode"] == "smooth_random" and b["mode"] == "zero_torque" and all(a[key] == b[key] == record[key] for key in ("contact_profile", "prefix_steps", "pose", "seed")), "paired_case_identity", record["random_trial_id"])
        c.check(a["initial_qpos"] == b["initial_qpos"] and a["reset_seed"] == b["reset_seed"] and a["exploration_seed"] == b["exploration_seed"], "paired_shared_initial_conditions", record["random_trial_id"])
        active_a, active_b = (groups[t["trial_id"]][t["prefix_steps"]:] for t in (a, b))
        x, y = active_a[:150], active_b[:150]
        squares = [0.] * 8
        for left, right in zip(x, y):
            for j in range(8):
                delta = left["observation_after"]["joint_position"][j] - right["observation_after"]["joint_position"][j]
                squares[j] += delta * delta
        expected = {"complete": True, "missing_reason": None, "requested_shared_active_steps": 150, "available_shared_active_steps": 150,
                    "random_total_active_steps": len(active_a), "zero_total_active_steps": len(active_b),
                    "native_position_trajectory_difference_rms_rad_per_joint": [math.sqrt(s / 150) for s in squares],
                    "native_position_trajectory_difference_rms_rad_all_joints": math.sqrt(sum(squares) / 1200),
                    "random_shared_action_metrics": action_metrics(x), "zero_shared_action_metrics": action_metrics(y),
                    "random_shared_substep_metrics": substep_metrics(x), "zero_shared_substep_metrics": substep_metrics(y)}
        c.compare(record, expected, "paired/" + a["trial_id"])
        recomputed_pairs.append({"random_trial_id": a["trial_id"], "zero_trial_id": b["trial_id"],
                                 "trajectory_rms_rad_per_joint": expected["native_position_trajectory_difference_rms_rad_per_joint"],
                                 "trajectory_rms_rad_all_joints": expected["native_position_trajectory_difference_rms_rad_all_joints"],
                                 "applied_torque_rms_nm_per_joint": expected["random_shared_action_metrics"]["applied_torque_rms_nm_per_joint"]})
    metric_keys = ("peak_ground_normal_force_n", "ground_normal_impulse_ns", "peak_kinetic_energy_j", "minimum_contact_distance_m")
    for field, kind in (("matched_contact_effects", "contact"), ("matched_prefix_effects", "prefix")):
        records = profile[field]
        c.check(len(records) == len({r["left_trial_id"] for r in records}) == 48, "48_unique_effect_pairs", field)
        for record in records:
            a, b = (by_id[record[key]] for key in ("left_trial_id", "right_trial_id"))
            equal = ("prefix_steps", "pose", "seed", "mode") if kind == "contact" else ("contact_profile", "pose", "seed", "mode")
            c.check(all(a[key] == b[key] for key in equal) and ((a["contact_profile"], b["contact_profile"]) == ("baseline", "compliant") if kind == "contact" else (a["prefix_steps"], b["prefix_steps"]) == (0, 100)), "matched_effect_identity", field)
            c.check(a["initial_qpos"] == b["initial_qpos"] and a["reset_seed"] == b["reset_seed"] and a["exploration_seed"] == b["exploration_seed"],
                    "matched_effect_initial_conditions", [field, a["trial_id"]])
            for index in range(150):
                c.check(groups[a["trial_id"]][a["prefix_steps"] + index]["diagnostics"]["requested_torque"]
                        == groups[b["trial_id"]][b["prefix_steps"] + index]["diagnostics"]["requested_torque"],
                        "matched_effect_shared_requested_commands", [field, a["trial_id"], index])
            c.compare(record, {"pose": a["pose"], "seed": a["seed"], "mode": a["mode"],
                               "left_contact_profile": a["contact_profile"], "right_contact_profile": b["contact_profile"],
                               "left_prefix_steps": a["prefix_steps"], "right_prefix_steps": b["prefix_steps"]},
                      field + "/labels/" + a["trial_id"])
            left, right = computed[a["trial_id"]], computed[b["trial_id"]]
            expected = {"available": True, "shared_active_window_complete": True,
                        "whole_trial_right_minus_left": {key: right["whole_trial"][key] - left["whole_trial"][key] for key in metric_keys},
                        "shared_active_right_minus_left": {key: right["shared_active_window"]["substep_metrics"][key] - left["shared_active_window"]["substep_metrics"][key] for key in metric_keys},
                        "shared_active_applied_torque_rms_nm_right_minus_left_per_joint": [y-x for x, y in zip(left["shared_active_window"]["action_metrics"]["applied_torque_rms_nm_per_joint"], right["shared_active_window"]["action_metrics"]["applied_torque_rms_nm_per_joint"])]}
            c.compare(record, expected, field + "/" + a["trial_id"])

    interrupted = HISTORY / "2026-10-10_ground_body"
    first_complete = HISTORY / "2026-10-10_ground_body_verified"
    recovery, first_trials = load(interrupted / "recovery.json"), load(interrupted / "trials.json")
    stale_metadata = load(interrupted / "metadata.json")
    first_groups, _ = read_rows(interrupted)
    inputs[str((interrupted / "trace.jsonl.gz").resolve())] = sha(interrupted / "trace.jsonl.gz")
    first_controls = sum(len(rows) for rows in first_groups.values())
    first_physics = sum(rows[-1]["diagnostics"]["physics_steps"] for rows in first_groups.values())
    first_attempts = sum(t["control_calls_attempted"] for t in first_trials)
    c.check(first_controls == recovery["observed_trace_control_steps"] == first_attempts == 2750 and first_physics == recovery["observed_trace_physics_steps"] == 27500, "interrupted_actual_budget_recovered")
    ledger = [{"archive": str(interrupted.resolve()), "status": recovery["archive_status"], "control_steps": first_controls,
               "control_calls_attempted": first_attempts, "physics_steps": first_physics,
               "stale_metadata_control_calls_attempted": stale_metadata["control_calls_attempted"],
               "note": "Recovery/closed trace and saved trials supersede the stale metadata checkpoint; write failure is retained."}]
    for folder in (first_complete, reference):
        old = load(folder / "metadata.json")
        old_t = load(folder / "trials.json")
        old_g, _ = read_rows(folder)
        inputs[str((folder / "trace.jsonl.gz").resolve())] = sha(folder / "trace.jsonl.gz")
        controls, physical = sum(len(r) for r in old_g.values()), sum(r[-1]["diagnostics"]["physics_steps"] for r in old_g.values())
        attempts = sum(t["control_calls_attempted"] for t in old_t)
        c.check(old["complete"] and controls == old["control_steps"] == attempts == old["control_calls_attempted"] == 6000 and physical == old["physics_steps"] == 60000, "historical_full_matrix_budget", str(folder))
        ledger.append({"archive": str(folder.resolve()), "status": old["archive_status"], "control_steps": controls, "control_calls_attempted": attempts, "physics_steps": physical})
    ledger.append({"archive": str(archive.resolve()), "status": metadata["archive_status"], **dict(sums)})
    total_controls = sum(item["control_steps"] for item in ledger)
    total_attempts = sum(item["control_calls_attempted"] for item in ledger)
    total_physics = sum(item["physics_steps"] for item in ledger)
    c.check(total_controls == total_attempts == 38750 and total_physics == 387500, "four_attempt_cumulative_budget")
    return {"schema_version": 1, "audit_type": "frozen_contact_prefix_independent_scalar_archive_audit",
            "created_at_utc": datetime.now(timezone.utc).isoformat(), "status": "pass" if not c.failed else "failed",
            "auditor_script_sha256": sha(Path(__file__).resolve()), "source_commit": metadata["source_commit"],
            "input_archives": {"archive": str(archive.resolve()), "reference": str(reference.resolve()), "profile": str(profile_path.resolve())},
            "input_sha256": inputs, "source_snapshot_checks": source_records, "manifest_coverage": manifests,
            "manifest_scope": "Only the supplied manifests' listed entries are verified; later files and this externally written audit are not implicitly covered.",
            "checks": c.count, "failed_checks": c.failed, "finite_scalar_numbers_checked": c.numbers,
            "maximum_scalar_recomputation_difference": c.maximum_difference, "maximum_qpos_qvel_replay_difference": maximum_replay_difference,
            "counts": {"trials": len(trials), "trace_rows": sum(len(rows) for rows in groups.values()), "paired_active_responses": len(paired),
                       "baseline_reference_trials": replay_trials, "baseline_reference_rows": replay_rows, "zero_duplicate_rows": duplicate_rows, "random_shared_request_rows": request_rows},
            "matrix_budget": dict(sums), "independently_recomputed_pairs": recomputed_pairs,
            "budget_ledger": {"attempts": ledger, "collector_attempt_count": 4, "total_control_steps": total_controls,
                              "total_control_calls_attempted": total_attempts, "total_physics_steps": total_physics,
                              "total_simulated_seconds": total_physics * .002, "scope": "All four collector attempts; CPU tests and other historical diagnostics excluded; no cumulative wall-time claim."},
            "parameter_updates": {"model": 0, "policy": 0, "gate": 0}, "auditor_parameter_updates": 0,
            "evidence_boundaries": ["Offline scalar consistency is not an independent dynamics solver or hardware safety proof.",
                                    "Force/energy/distance samples occur every 2 ms and do not bound between-step extrema; the normal-force integral includes sustained support.",
                                    "Changing contact or waiting changes initial/environment conditions, not learned skill. A 2 s zero prefix has no stability-success interpretation.",
                                    "Paired native trajectories describe fixed-action response, not body-model identifiability, predictive accuracy or learning benefit.",
                                    "Zero-prefix duplicate trajectories are not independent seeds. Prefix exposure is charged; matching 150 active commands does not equate overall active budgets."],
            "violations": c.violations, "violations_truncated": c.failed > len(c.violations)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--reference", type=Path, default=DEFAULT_REFERENCE)
    parser.add_argument("--profile", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    archive, reference, output = args.archive.resolve(), args.reference.resolve(), args.output.resolve()
    forbidden = (archive, reference, HISTORY / "2026-10-10_ground_body", HISTORY / "2026-10-10_ground_body_verified")
    if any(output.is_relative_to(folder.resolve()) for folder in forbidden):
        parser.error("--output must be outside all audited archives")
    if output.exists():
        parser.error("output already exists; preserve previous audits")
    try:
        result = audit(archive, reference, args.profile.resolve() if args.profile else None)
    except Exception as error:
        result = {"status": "failed", "auditor_script_sha256": sha(Path(__file__).resolve()),
                  "fatal_error": {"type": type(error).__name__, "message": str(error)},
                  "evidence_boundary": "Audit could not complete; no validation pass or experiment result is implied."}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("status", "checks", "failed_checks", "counts", "matrix_budget", "budget_ledger", "maximum_scalar_recomputation_difference", "fatal_error") if key in result}, indent=2))
    raise SystemExit(0 if result["status"] == "pass" else 1)


if __name__ == "__main__":
    main()
