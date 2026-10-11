"""Independently audit five-parameter hinge local-learning archives.

Replays recorded arithmetic, never runs physics or acquires training samples.
Data consistency and the predeclared scientific gate are separate results.
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
import re
import subprocess
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
KINDS = ("calibration", "prediction", "frozen_mpc", "learned_mpc", "fixed_pd", "zero_torque")
JOINTS = ("left_shoulder", "left_elbow", "right_shoulder", "right_elbow", "left_hip", "left_knee", "right_hip", "right_knee")
NATIVE = {"joint_position": 8, "joint_velocity": 8, "imu_gyro": 3, "imu_acceleration": 3, "actuator_torque": 8, "previous_command": 8}
INITIAL = [1.0, 0.0, 0.02, 0.0, 0.0]
CALIBRATION_AMPLITUDES = [.125, .25, .5, .125, .25, .5, .125, .25, .5, .125]
FEATURE_NAMES = ["v", "q-qref", "requested_torque", "sign(u)*max(abs(u)-0.25,0)", "1"]
MODEL_FIELDS = ("qref_rad", "dt_seconds", "features", "initial_coefficients", "initial_covariance_scale", "forgetting_factor", "coefficients", "covariance", "dtype", "hinge_threshold_nm", "hinge_threshold_updates", "hinge_structure_prior")
MPC_CONFIG = {"horizon": 15, "candidate_count": 9, "torque_limit_nm": .5, "position_weight": 1., "velocity_weight": .002, "effort_weight": .00002, "change_weight": .00002, "local_position_radius_rad": .15, "prediction_limit_tolerance_rad": .03, "target_limit_margin_rad": .03, "velocity_limit_rad_s": 1.5}
ENVIRONMENT_CONFIG = {"physics_dt": .002, "control_substeps": 10, "torque_limit": .5, "joint_speed_limit": 20., "joint_limit_margin": .08, "kinetic_energy_limit": 50., "reset_clearance": .005, "ground_contact_profile": "baseline"}
REQUIRED_SOURCES = {f"src/developmental_physics/{name}" for name in ("__init__.py", "environment.py", "collect.py", "probes.py", "local_model.py", "local_learning.py", "assets/ground_body.xml")}
REQUIRED_SOURCES.update(("pyproject.toml", "docs/LOCAL_BODY_LEARNING_V2_PROTOCOL.md"))


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


class Checks:
    def __init__(self):
        self.count = self.failed = 0
        self.maximum_difference = 0.
        self.violations = []

    def check(self, condition, label, location=None):
        self.count += 1
        if not condition:
            self.failed += 1
            if len(self.violations) < 200:
                self.violations.append({"check": label, "location": location})

    def near(self, actual, expected, label, location=None):
        valid = type(actual) in (int, float) and type(expected) in (int, float) and math.isfinite(actual) and math.isfinite(expected)
        difference = abs(actual - expected) if valid else None
        if valid:
            self.maximum_difference = max(self.maximum_difference, difference)
        self.check(valid and difference <= 1e-10, label, {"location": location, "actual": actual, "expected": expected, "difference": difference})

    def compare(self, actual, expected, label):
        if isinstance(expected, dict):
            self.check(isinstance(actual, dict), "object_shape", label)
            if isinstance(actual, dict):
                for key, value in expected.items():
                    self.check(key in actual, "required_field", label + "/" + key)
                    self.compare(actual.get(key), value, label + "/" + key)
        elif isinstance(expected, (list, tuple)):
            self.check(isinstance(actual, (list, tuple)) and len(actual) == len(expected), "array_shape", label)
            if isinstance(actual, (list, tuple)):
                for index, (left, right) in enumerate(zip(actual, expected)):
                    self.compare(left, right, label + "/" + str(index))
        elif type(expected) is float:
            self.near(actual, expected, "scalar_recomputation", label)
        else:
            self.check(actual == expected, "label_or_count", label)

    def finite(self, value, label):
        if isinstance(value, dict):
            for key, item in value.items():
                self.finite(item, label + "/" + key)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                self.finite(item, label + "/" + str(index))
        elif type(value) is float:
            self.check(math.isfinite(value), "finite_numeric", label)


def hinge(torque):
    sign = 1. if torque > 0 else (-1. if torque < 0 else 0.)
    return sign * max(abs(torque) - .25, 0.)


def predict(theta, qref, q, v, torque):
    x = [v, q - qref, torque, hinge(torque), 1.]
    next_v = sum(a * b for a, b in zip(theta, x))
    return [q + .02 * next_v, next_v]


def rls_replay(theta, covariance, features, label):
    projected = [sum(covariance[i][j] * features[j] for j in range(5)) for i in range(5)]
    denominator = 1. + sum(features[i] * projected[i] for i in range(5))
    if not math.isfinite(denominator) or denominator <= 0:
        raise ValueError("invalid independent RLS denominator")
    gain = [value / denominator for value in projected]
    residual = label - sum(theta[i] * features[i] for i in range(5))
    coefficients = [theta[i] + gain[i] * residual for i in range(5)]
    updated = [[covariance[i][j] - gain[i] * projected[j] for j in range(5)] for i in range(5)]
    updated = [[.5 * (updated[i][j] + updated[j][i]) for j in range(5)] for i in range(5)]
    return coefficients, updated


def model_record(qref, coefficients, covariance):
    return {"qref_rad": qref, "dt_seconds": .02, "features": FEATURE_NAMES, "initial_coefficients": INITIAL, "initial_covariance_scale": 100., "forgetting_factor": 1., "coefficients": coefficients, "covariance": covariance, "dtype": "float64", "hinge_threshold_nm": .25, "hinge_threshold_updates": 0, "hinge_structure_prior": "fixed signed torque hinge; structural prior, not a learned threshold or physics label"}


def rmse(errors):
    return None if not errors else math.sqrt(sum(value * value for value in errors) / len(errors))


def replay_mpc(theta, qref, q, v, target, previous, limits):
    lower = max(qref - .15, limits[0] - .03)
    upper = min(qref + .15, limits[1] + .03)
    feasible, calls = [], 0
    for index in range(9):
        torque = -.5 + index * .125
        pq, pv = q, v
        qs, vs = [], []
        cost = .00002 * (torque - previous) ** 2
        for _ in range(15):
            calls += 1
            pq, pv = predict(theta, qref, pq, pv, torque)
            if not math.isfinite(pq) or not math.isfinite(pv) or not lower <= pq <= upper or abs(pv) > 1.5:
                break
            qs.append(pq)
            vs.append(pv)
            cost += (pq - target) ** 2 + .002 * pv * pv + .00002 * torque * torque
            if not math.isfinite(cost):
                break
        else:
            feasible.append((cost, abs(torque), torque, qs, vs))
    if not feasible:
        return {"torque": 0., "feasible_candidates": 0, "fallback": True, "cost": None, "predicted_q": [], "predicted_v": [], "mathematical_prediction_calls": calls}
    cost, _, torque, qs, vs = min(feasible)
    return {"torque": torque, "feasible_candidates": len(feasible), "fallback": False, "cost": cost, "predicted_q": qs, "predicted_v": vs, "mathematical_prediction_calls": calls}


def audit_sources(path, metadata, checks, git_root):
    manifest = load_json(path / "manifest.json")
    actual = {p.name for p in path.iterdir() if p.is_file() and p.name != "manifest.json"}
    checks.check(set(manifest) == actual, "manifest_complete_file_coverage", str(path))
    checks.check({"metadata.json", "episodes.json", "seed_results.json", "source_snapshot.zip", "trace.jsonl.gz"}.issubset(manifest), "manifest_core_files", str(path))
    for name, expected in manifest.items():
        checks.check(Path(name).name == name, "manifest_local_filename", name)
        if Path(name).name == name:
            checks.check((path / name).is_file() and file_hash(path / name) == expected, "manifest_hash", name)
    commit = metadata.get("source_commit", "")
    checks.check(bool(re.fullmatch(r"[0-9a-f]{40}", commit)), "source_commit_format", commit)
    checks.check(metadata.get("source_status") == "", "clean_collection_source", str(path))
    hashes = metadata["source_sha256"]
    checks.check(REQUIRED_SOURCES.issubset(hashes), "required_source_hashes", str(path))
    protocol = metadata.get("protocol")
    checks.check(isinstance(protocol, dict), "protocol_record", str(path))
    if isinstance(protocol, dict):
        checks.check(hashes.get(protocol.get("path")) == protocol.get("sha256"), "protocol_hash", str(path))
    with zipfile.ZipFile(path / "source_snapshot.zip") as archive:
        checks.check(len(archive.namelist()) == len(set(archive.namelist())), "source_zip_unique_names", str(path))
        checks.check(set(archive.namelist()) == set(hashes), "source_zip_exact_coverage", str(path))
        for name, expected in hashes.items():
            blob = archive.read(name)
            checks.check(hashlib.sha256(blob).hexdigest() == expected, "source_zip_hash", name)
            if git_root is not None and re.fullmatch(r"[0-9a-f]{40}", commit):
                result = subprocess.run(["git", "show", f"{commit}:{name}"], cwd=git_root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
                checks.check(result.returncode == 0 and result.stdout == blob, "source_git_blob_bytes", name)
        xml = ET.fromstring(archive.read("src/developmental_physics/assets/ground_body.xml"))
        factor = math.pi / 180. if xml.find("compiler").get("angle") == "degree" else 1.
        ranges = {joint.get("name"): [float(value) * factor for value in joint.get("range").split()] for joint in xml.findall(".//joint") if joint.get("range")}
    return [ranges[name] for name in JOINTS]


def audit_archive(path, checks, git_root=ROOT):
    path = Path(path).resolve()
    metadata = load_json(path / "metadata.json")
    episodes = load_json(path / "episodes.json")
    results = load_json(path / "seed_results.json")
    for name, item in (("metadata", metadata), ("episodes", episodes), ("seed_results", results)):
        checks.finite(item, name)
    ranges = audit_sources(path, metadata, checks, git_root)
    split = metadata["split"]
    checks.check(split in ("development", "holdout"), "known_split", split)
    expected_seeds = [0, 1, 2] if split == "development" else [10, 11, 12]
    checks.compare(metadata["seeds"], expected_seeds, "predeclared_seeds")
    checks.compare({key: metadata.get(key) for key in ("gpu", "prefix_steps", "calibration_steps", "prediction_steps", "control_steps_per_trial", "teacher_calls", "external_demonstration_samples", "policy_parameter_updates")}, {"gpu": None, "prefix_steps": 100, "calibration_steps": 300, "prediction_steps": 100, "control_steps_per_trial": 200, "teacher_calls": 0, "external_demonstration_samples": 0, "policy_parameter_updates": 0}, "metadata_protocol")
    checks.compare(metadata["fixed_pd"], {"kp": 4., "kd": .2, "torque_limit_nm": .5}, "fixed_pd_spec")
    checks.compare(metadata["variant"], "hinge", "model_variant")
    checks.compare(metadata["calibration_block_amplitudes_nm"], CALIBRATION_AMPLITUDES, "calibration_multidose_protocol")
    checks.compare(metadata["protocol"]["path"], "docs/LOCAL_BODY_LEARNING_V2_PROTOCOL.md", "v2_frozen_protocol_path")
    checks.compare(metadata["environment_config"], ENVIRONMENT_CONFIG, "unchanged_body_permissions")
    checks.compare(metadata["source_dirty"], False, "clean_source_dirty_flag")
    checks.compare(metadata["archive_status"], "complete", "archive_execution_status")
    checks.compare({key: metadata[key] for key in ("exception_trials", "terminated_trials", "completed_trials", "blocked_trials", "unprocessed_trials", "failed_trials", "skipped_trials")}, {"exception_trials": 0, "terminated_trials": 0, "completed_trials": 18, "blocked_trials": 0, "unprocessed_trials": 0, "failed_trials": 0, "skipped_trials": 0}, "all_planned_outcomes_accounted")
    planned = [{"trial_id": f"seed{seed}_{kind}", "seed": seed, "kind": kind, "maximum_control_steps": 400 if kind == "calibration" else (200 if kind == "prediction" else 300)} for seed in expected_seeds for kind in KINDS]
    checks.compare(metadata["planned_episodes"], planned, "complete_predeclared_episode_ledger")
    checks.compare(metadata["planned_episode_count"], 18, "planned_episode_count")
    checks.compare(metadata["maximum_control_steps"], 5400, "planned_maximum_budget")
    joint = metadata["joint_index"]
    checks.check(type(joint) is int and 0 <= joint < 8, "joint_index", joint)
    grouped, trial_order = defaultdict(list), []
    with gzip.open(path / "trace.jsonl.gz", "rt", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            row = json.loads(line)
            checks.finite(row, f"trace/{line_number}")
            checks.check(not row.get("invalid_numeric_fields"), "no_invalid_numeric_markers", line_number)
            tid = row["trial_id"]
            if not trial_order or trial_order[-1] != tid:
                trial_order.append(tid)
            grouped[tid].append(row)
    expected_order = [f"seed{seed}_{kind}" for seed in expected_seeds for kind in KINDS]
    checks.compare(trial_order, expected_order, "complete_trial_order")
    episode_map = {(episode["seed"], episode["kind"]): episode for episode in episodes}
    result_map = {item["seed"]: item for item in results}
    checks.check(len(episode_map) == len(episodes) == 18, "unique_episode_matrix", str(path))
    checks.check(len(result_map) == len(results) == 3, "unique_seed_results", str(path))
    archive_seeds = []
    for seed in expected_seeds:
        sr = result_map[seed]
        qref, direction = sr["reference_q"], sr["direction"]
        selection = sr["selection_record"]
        limits = ranges[joint]
        expected_direction = 1 if limits[1] - qref >= qref - limits[0] else -1
        checks.compare(direction, expected_direction, f"seed{seed}/direction")
        checks.compare({key: selection[key] for key in ("joint_index", "joint_position_rad", "lower_limit_rad", "upper_limit_rad", "direction")}, {"joint_index": joint, "joint_position_rad": qref, "lower_limit_rad": limits[0], "upper_limit_rad": limits[1], "direction": direction}, f"seed{seed}/direction_record")
        theta = INITIAL.copy()
        covariance = [[100. if i == j else 0. for j in range(5)] for i in range(5)]
        initial_record = model_record(qref, theta.copy(), [row.copy() for row in covariance])
        checks.compare(sr["initial_model"], {**initial_record, "update_count": 0, "trainable": False, "parameter_fingerprint": digest(initial_record)}, f"seed{seed}/initial_model")
        observed_theta, observed_covariance = theta.copy(), [row.copy() for row in covariance]
        observed_hash = digest(initial_record)
        updates, physical, controls, attempts = 0, 0, 0, 0
        prefix_reference = None
        derived = {}
        seed_complete = True
        for kind in KINDS:
            location = f"seed{seed}/{kind}"
            ep = episode_map[(seed, kind)]
            rows = grouped[f"seed{seed}_{kind}"]
            count = 400 if kind == "calibration" else (200 if kind == "prediction" else 300)
            checks.check(len(rows) == count, "complete_trial_rows", location)
            checks.check(ep["environment_fingerprint_before"] == ep["environment_fingerprint_after"], "environment_parameter_freeze", location)
            checks.check(ep["environment_fingerprint_before"] == episode_map[(seed, "calibration")]["environment_fingerprint_before"], "shared_environment_configuration", location)
            checks.compare(ep["status"], "completed", location + "/status")
            checks.compare(ep["reason"], None, location + "/reason")
            checks.compare(ep["collector_exception"], None, location + "/no_collector_exception")
            checks.compare(ep["trial_id"], f"seed{seed}_{kind}", location + "/planned_trial_id")
            checks.compare(ep["maximum_control_steps"], count, location + "/planned_trial_budget")
            prefix = [{"before": row.get("observation_before"), "after": row.get("observation_after")} for row in rows[:100]]
            if prefix_reference is None:
                prefix_reference = prefix
            else:
                checks.check(prefix == prefix_reference, "prefix_native_exact_replay", location)
            velocity_errors = {"frozen": [], "learned": []}
            position_errors = {"frozen": [], "learned": []}
            persistence_errors, tracking_errors = [], []
            budgets = {phase: {key: 0 for key in ("control_calls_attempted", "control_steps", "physics_steps")} for phase in ("prefix", "calibration", "prediction", "control")}
            previous_native, previous_torque = None, 0.
            planner_calls = planner_fallbacks = 0
            for index, row in enumerate(rows):
                rowloc = location + f"/{index}"
                if "collector_exception" in row:
                    checks.check(False, "formal_trial_exception", rowloc)
                    continue
                phase = "prefix" if index < 100 else (kind if kind in ("calibration", "prediction") else "control")
                checks.compare(row["step_index"], index, rowloc + "/step")
                checks.compare(row["phase"], phase, rowloc + "/phase")
                checks.compare(row["seed"], seed, rowloc + "/seed")
                checks.compare(row["kind"], kind, rowloc + "/kind")
                before, after = row["observation_before"], row["observation_after"]
                for native_name, size in NATIVE.items():
                    checks.check(len(before[native_name]) == len(after[native_name]) == size, "native_shape", rowloc + "/" + native_name)
                if previous_native is not None:
                    checks.check(before == previous_native, "native_transition_continuity", rowloc)
                previous_native = after
                command = row["requested_torque"]
                checks.check(len(command) == 8 and all(type(value) in (int, float) and math.isfinite(value) and abs(value) <= .5 for value in command), "command_permissions", rowloc)
                checks.check(all(value == 0. for j, value in enumerate(command) if j != joint), "nontarget_joint_zero", rowloc)
                q, v, torque = before["joint_position"][joint], before["joint_velocity"][joint], command[joint]
                diag = row["diagnostics"]
                checks.compare(diag["requested_torque"], command, rowloc + "/diagnostic_request")
                checks.compare(diag["accepted_torque"], command, rowloc + "/accepted_permission")
                checks.compare(diag["executed_substeps"], 10, rowloc + "/substeps")
                checks.compare(diag["step_id"], index + 1, rowloc + "/endpoint_step")
                checks.compare(diag["physics_steps"], (index + 1) * 10, rowloc + "/endpoint_physics")
                checks.near(diag["time"], (index + 1) * .02, "physical_time", rowloc)
                checks.compare(diag["terminated"], False, rowloc + "/terminated")
                checks.compare(diag["reason"], None, rowloc + "/stop_reason")
                history = diag["applied_torque_history"]
                checks.check(len(history) == 10, "actual_torque_history_size", rowloc)
                guarded = 0
                for actual in history:
                    checks.check(len(actual) == 8, "actual_torque_vector_size", rowloc)
                    checks.check(all(a == 0. or a == u for a, u in zip(actual, command)), "shield_only_preserves_or_zeroes_request", rowloc)
                    guarded += any(a != u for a, u in zip(actual, command))
                checks.compare(diag["guarded_substeps"], guarded, rowloc + "/guarded_substeps")
                if history:
                    checks.compare(diag["applied_torque"], history[-1], rowloc + "/last_applied")
                    checks.compare(after["actuator_torque"], history[-1], rowloc + "/native_actual_torque")
                checks.compare(after["previous_command"], command, rowloc + "/native_command_history")
                budgets[phase]["control_calls_attempted"] += 1
                budgets[phase]["control_steps"] += 1
                budgets[phase]["physics_steps"] += 10
                if index < 100:
                    checks.compare(command, [0.] * 8, rowloc + "/prefix_zero")
                    checks.compare(row["predicted_next_qv"], {}, rowloc + "/prefix_no_prediction")
                    checks.compare(row["model_update"], None, rowloc + "/prefix_no_update")
                    checks.compare(row["target_q"], None, rowloc + "/prefix_no_target")
                    continue
                active = index - 100
                if active == 0:
                    checks.near(q, qref, "reference_at_paid_prefix", rowloc)
                if kind == "calibration":
                    slot = active % 30
                    amplitude = CALIBRATION_AMPLITUDES[active // 30]
                    prescribed = direction * (amplitude if slot < 5 else (-amplitude if 15 <= slot < 20 else 0.))
                    checks.near(torque, prescribed, "calibration_schedule", rowloc)
                elif kind == "prediction":
                    slot = active % 20
                    prescribed = direction * (.25 if slot < 7 else (-.25 if 10 <= slot < 17 else 0.))
                    checks.near(torque, prescribed, "prediction_schedule", rowloc)
                elif kind == "zero_torque":
                    checks.near(torque, 0., "zero_control", rowloc)
                if kind not in ("calibration", "prediction"):
                    target = qref + direction * (.04 if active < 100 else .08)
                    checks.near(row["target_q"], target, "fixed_task_target", rowloc)
                    checks.check(limits[0] + .03 <= target <= limits[1] - .03, "target_public_interior", rowloc)
                    tracking_errors.append(after["joint_position"][joint] - target)
                    if kind == "fixed_pd":
                        checks.near(torque, max(-.5, min(.5, 4. * (target - q) - .2 * v)), "fixed_pd_command", rowloc)
                    if kind.endswith("mpc"):
                        planning_theta = INITIAL if kind == "frozen_mpc" else observed_theta
                        decision = replay_mpc(planning_theta, qref, q, v, target, previous_torque, limits)
                        checks.compare(row["planner_decision"], decision, rowloc + "/mpc_independent_replay")
                        checks.near(torque, decision["torque"], "mpc_selected_request", rowloc)
                        planner_calls += decision["mathematical_prediction_calls"]
                        planner_fallbacks += decision["fallback"]
                else:
                    checks.compare(row["target_q"], None, rowloc + "/no_task_target")
                previous_torque = torque
                predictions = {"frozen": predict(INITIAL, qref, q, v, torque), "learned": predict(theta, qref, q, v, torque)}
                checks.compare(row["predicted_next_qv"], predictions, rowloc + "/causal_prediction")
                next_v, next_q = after["joint_velocity"][joint], after["joint_position"][joint]
                for name, value in predictions.items():
                    velocity_errors[name].append(next_v - value[1])
                    position_errors[name].append(next_q - value[0])
                persistence_errors.append(next_v - v)
                update = row["model_update"]
                if kind == "calibration":
                    features = [v, q - qref, torque, hinge(torque), 1.]
                    checks.compare(update["features"], features, rowloc + "/causal_features")
                    checks.near(update["observed_next_v_rad_s"], next_v, "native_future_label", rowloc)
                    checks.compare(update["preupdate_prediction"], {"next_q_rad": predictions["learned"][0], "next_v_rad_s": predictions["learned"][1]}, rowloc + "/preupdate_prediction")
                    checks.near(update["preupdate_error_rad_s"], next_v - predictions["learned"][1], "preupdate_residual", rowloc)
                    checks.compare(update["parameter_fingerprint_before"], observed_hash, rowloc + "/update_hash_chain_before")
                    theta, covariance = rls_replay(theta, covariance, features, next_v)
                    updates += 1
                    checks.compare(update["updated"], True, rowloc + "/updated_flag")
                    checks.compare(update["update_count"], updates, rowloc + "/update_count")
                    checks.compare(update["coefficients_after"], theta, rowloc + "/rls_coefficients")
                    checks.compare(update["covariance_after"], covariance, rowloc + "/rls_covariance")
                    observed_theta, observed_covariance = update["coefficients_after"], update["covariance_after"]
                    observed_hash = digest(model_record(qref, observed_theta, observed_covariance))
                    checks.compare(update["parameter_fingerprint_after"], observed_hash, rowloc + "/update_hash_chain_after")
                else:
                    checks.compare(update, None, rowloc + "/frozen_eval_no_update")
            checks.compare(ep["phase_budgets"], budgets, location + "/phase_budget")
            checks.compare(ep["control_calls_attempted"], len(rows), location + "/calls")
            checks.compare(ep["control_steps"], len(rows), location + "/controls")
            checks.compare(ep["physics_steps"], len(rows) * 10, location + "/physics")
            ev = sr["evaluations"][kind]
            metrics = {"tracking_rmse_rad": rmse(tracking_errors), "velocity_prediction_rmse": {name: rmse(values) for name, values in velocity_errors.items()}}
            checks.compare(ev, metrics, location + "/recorded_metrics")
            completed = len(rows) == count and ep["status"] == "completed"
            checks.compare(ev["completed"], completed, location + "/completion")
            seed_complete = seed_complete and completed
            final_hashes = [digest(initial_record), observed_hash]
            if kind != "calibration":
                checks.compare(ev["models_before"], final_hashes, location + "/models_before")
                checks.compare(ev["models_after"], final_hashes, location + "/models_after")
            if kind.endswith("mpc"):
                spec = ev["planner_spec"]
                checks.compare(spec["config"], MPC_CONFIG, location + "/planner_config")
                checks.compare(spec["candidates_nm"], [-.5 + i * .125 for i in range(9)], location + "/candidate_grid")
                checks.compare(spec["forecast_bounds_rad"], [max(qref - .15, limits[0] - .03), min(qref + .15, limits[1] + .03)], location + "/forecast_domain")
                checks.compare(spec["target_bounds_rad"], [max(qref - .15, limits[0] + .03), min(qref + .15, limits[1] - .03)], location + "/target_domain")
                checks.compare(spec["physical_queries"], 0, location + "/no_oracle_simulation")
            derived[kind] = {**metrics, "position_prediction_rmse": {name: rmse(values) for name, values in position_errors.items()}, "persistence_velocity_rmse": rmse(persistence_errors), "completed": completed, "mathematical_prediction_calls": planner_calls, "planner_fallbacks": planner_fallbacks}
            physical += ep["physics_steps"]
            controls += ep["control_steps"]
            attempts += ep["control_calls_attempted"]
        checks.compare(sr["calibration_updates"], updates, f"seed{seed}/calibration_updates")
        checks.compare(updates, 300, f"seed{seed}/fixed_update_budget")
        final_model = sr["learned_model"]
        checks.compare(final_model, {**model_record(qref, theta, covariance), "update_count": 300, "trainable": False}, f"seed{seed}/final_model")
        checks.compare(final_model["parameter_fingerprint"], observed_hash, f"seed{seed}/final_model_hash")
        checks.check(digest({key: final_model[key] for key in MODEL_FIELDS}) == observed_hash, "final_snapshot_exact_hash", seed)
        checks.compare([attempts, controls, physical], [1800, 1800, 18000], f"seed{seed}/total_budget")
        archive_seeds.append({"seed": seed, "complete": seed_complete, "control_calls_attempted": attempts, "control_steps": controls, "physics_steps": physical, "model_updates": updates, "evaluations": derived})
    checks.compare(metadata["complete"], True, "archive_complete")
    checks.compare(metadata["control_calls_attempted"], sum(item["control_calls_attempted"] for item in archive_seeds), "metadata_calls")
    checks.compare(metadata["control_steps"], sum(item["control_steps"] for item in archive_seeds), "metadata_controls")
    checks.compare(metadata["physics_steps"], sum(item["physics_steps"] for item in archive_seeds), "metadata_physics")
    checks.compare(metadata["model_updates"], sum(item["model_updates"] for item in archive_seeds), "metadata_model_updates")
    return {"path": str(path), "split": split, "pose": metadata["pose"], "joint_index": joint, "source_commit": metadata["source_commit"], "input_hashes": {name: file_hash(path / name) for name in ("manifest.json", "metadata.json", "episodes.json", "seed_results.json", "trace.jsonl.gz", "source_snapshot.zip")}, "seeds": archive_seeds}


def scientific_gate(archives):
    held = [archive for archive in archives if archive["split"] == "holdout"]
    if len(held) != 1:
        return {"evaluated": False, "passed": False, "reason": "Exactly one complete holdout archive is required."}
    rows = held[0]["seeds"]
    comparisons = []
    for row in rows:
        ev = row["evaluations"]
        nominal = ev["prediction"]["velocity_prediction_rmse"]["frozen"]
        learned = ev["prediction"]["velocity_prediction_rmse"]["learned"]
        improvement = None if nominal is None or nominal <= 0 else 1. - learned / nominal
        tracking_frozen = ev["frozen_mpc"]["tracking_rmse_rad"]
        tracking_learned = ev["learned_mpc"]["tracking_rmse_rad"]
        comparisons.append({"seed": row["seed"], "prediction_improvement": improvement, "prediction_gate": improvement is not None and improvement >= .2, "tracking_frozen": tracking_frozen, "tracking_learned": tracking_learned, "tracking_pd": ev["fixed_pd"]["tracking_rmse_rad"], "tracking_seed_improved": tracking_frozen is not None and tracking_learned is not None and tracking_learned < tracking_frozen, "complete": row["complete"]})
    valid = len(comparisons) == 3 and {row["seed"] for row in comparisons} == {10, 11, 12}
    numeric = all(row["tracking_frozen"] is not None and row["tracking_learned"] is not None for row in comparisons)
    frozen_mean = sum(row["tracking_frozen"] for row in comparisons) / len(comparisons) if numeric and comparisons else None
    learned_mean = sum(row["tracking_learned"] for row in comparisons) / len(comparisons) if numeric and comparisons else None
    improvement = None if frozen_mean is None or frozen_mean <= 0 else 1. - learned_mean / frozen_mean
    passed = valid and all(row["complete"] and row["prediction_gate"] and row["tracking_seed_improved"] for row in comparisons) and improvement is not None and improvement >= .2
    return {"evaluated": True, "passed": passed, "per_seed": comparisons, "tracking_frozen_mean": frozen_mean, "tracking_learned_mean": learned_mean, "tracking_mean_improvement": improvement, "claim_boundary": "Local body-model contribution relative to the same initially frozen MPC; report PD even if it is stronger. No rolling, standing, walking or real-robot claim."}


def audit(archives, *, git_root=ROOT):
    checks = Checks()
    results = []
    for archive in archives:
        try:
            results.append(audit_archive(Path(archive), checks, git_root))
        except (OSError, ValueError, KeyError, IndexError, TypeError, AttributeError, zipfile.BadZipFile) as error:
            checks.check(False, "archive_schema_or_read_error", {"path": str(archive), "type": type(error).__name__, "message": str(error)})
    checks.check(len(results) == len(archives), "all_archives_audited")
    if len(results) > 1:
        checks.check(len({archive["split"] for archive in results}) == len(results), "unique_archive_splits")
        checks.check(len({(archive["pose"], archive["joint_index"], archive["source_commit"]) for archive in results}) == 1, "same_frozen_experiment_across_splits")
    gate = scientific_gate(results)
    gate["data_consistency_verified"] = checks.failed == 0
    gate["validated_pass"] = gate["passed"] and checks.failed == 0
    return {"schema_version": 1, "created_at_utc": datetime.now(timezone.utc).isoformat(), "purpose": "Independent standard-library arithmetic and archive integrity audit; no physics or new learning experiment.", "audit_script_sha256": file_hash(Path(__file__)), "checks": checks.count, "failed": checks.failed, "maximum_recomputation_difference": checks.maximum_difference, "violations": checks.violations, "archives": results, "scientific_gate": gate}


def validate_output_path(output, archives):
    output = Path(output).resolve()
    if output.exists():
        raise ValueError("Refusing to overwrite an existing audit output.")
    if any(output.is_relative_to(Path(archive).resolve()) for archive in archives):
        raise ValueError("Audit output must be outside every input archive.")
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archives", nargs="+", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        output = validate_output_path(args.output, args.archives)
    except ValueError as error:
        parser.error(str(error))
    report = audit(args.archives)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(report, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"checks": report["checks"], "failed": report["failed"], "scientific_gate": report["scientific_gate"]["passed"], "report": str(output)}, ensure_ascii=False))
    return 1 if report["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
