"""Independent C2-B log audit: standard library only, no simulator/fitting imports.

Four independent RLS chains, paired native transitions, frozen MPC and the
predeclared dose/structure development gate are reconstructed from saved data.
Arithmetic replay is an audit of already paid updates, not another learning run.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path
import platform
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SEEDS = [0, 1, 2]
DT, PHYSICS_DT = .02, .002
HORIZONS = (1, 5, 15, 50)
INTEGRATION = "endpoint_euler"
STRUCTURES = ("linear4", "hinge5")
INITIAL = {"linear4": [1., 0., .02, 0.], "hinge5": [1., 0., .02, 0., 0.]}
CANDIDATES = ("old_linear4", "old_hinge5", "new_linear4", "new_hinge5")
ANCHOR = "old_hinge5"
KINDS = ("calibration_old", "calibration_new", "prediction_low", "prediction_full",
         *[name+"_mpc" for name in CANDIDATES], "nominal_mpc")
CONTROL_KINDS = KINDS[4:]
PHASES = ("prefix", "calibration", "prediction", "control")
CALIBRATION_AMPLITUDES = {
    "old": [.125, .25, .5, .125, .25, .5, .125, .25, .5, .125],
    "new": [.125, .25, .5, .375, .25, .5, .375, .25, .5, .375]}
PREDICTION_AMPLITUDES = {"low": [.25]*5, "full": [.125, .25, .375, .5, .375]}
JOINTS = ("left_shoulder", "left_elbow", "right_shoulder", "right_elbow",
          "left_hip", "left_knee", "right_hip", "right_knee")
NATIVE = {"joint_position": 8, "joint_velocity": 8, "imu_gyro": 3,
          "imu_acceleration": 3, "actuator_torque": 8, "previous_command": 8}
ENVIRONMENT = {"physics_dt": .002, "control_substeps": 10, "torque_limit": .5,
               "joint_speed_limit": 20., "joint_limit_margin": .08,
               "kinetic_energy_limit": 50., "reset_clearance": .005,
               "ground_contact_profile": "baseline"}
MPC_CONFIG = {"horizon": 15, "candidate_count": 9, "torque_limit_nm": .5,
              "position_weight": 1., "velocity_weight": .002, "effort_weight": .00002,
              "change_weight": .00002, "local_position_radius_rad": .15,
              "prediction_limit_tolerance_rad": .03, "target_limit_margin_rad": .03,
              "velocity_limit_rad_s": 1.5}
PROTOCOL = "docs/LOCAL_DOSE_ABLATION_PROTOCOL.md"
ASSET = "src/developmental_physics/assets/ground_body.xml"
REQUIRED_SOURCES = {PROTOCOL, ASSET, "pyproject.toml"} | {
    "src/developmental_physics/"+name for name in
    ("__init__.py", "environment.py", "collect.py", "probes.py", "local_model.py",
     "local_integration.py", "local_dose_ablation.py")}
EFFORT_KEYS = ("requested_absolute_nm_s", "requested_squared_nm2_s",
               "actual_absolute_nm_s", "actual_squared_nm2_s")


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def feature_vector(qref, q, v, torque, structure):
    if structure not in STRUCTURES or not all(finite(x) for x in (qref, q, v, torque)):
        raise ValueError("Known structure and finite native inputs required.")
    sign = 1. if torque > 0 else (-1. if torque < 0 else 0.)
    return [v, q-qref, torque, 1.] if structure == "linear4" else [
        v, q-qref, torque, sign*max(abs(torque)-.25, 0.), 1.]


def predict(theta, qref, q, v, torque):
    structure = {4: "linear4", 5: "hinge5"}.get(len(theta))
    if structure is None or not all(finite(x) for x in theta):
        raise ValueError("Four/five finite coefficients required.")
    features = feature_vector(qref, q, v, torque, structure)
    next_v = sum(a*b for a, b in zip(theta, features))
    next_q = q+DT*next_v
    if not finite(next_q) or not finite(next_v):
        raise ValueError("Nonfinite prediction.")
    return next_q, next_v


def replay_rls(theta, covariance, features, native_next_v):
    """Independent no-forgetting update, with covariance symmetrization."""
    n = len(theta)
    if (n not in (4, 5) or len(features) != n or len(covariance) != n
            or any(len(row) != n for row in covariance)
            or not all(finite(x) for x in theta+features+[native_next_v])
            or not all(finite(x) for row in covariance for x in row)):
        raise ValueError("Malformed RLS record.")
    projected = [sum(covariance[i][j]*features[j] for j in range(n)) for i in range(n)]
    denominator = 1.+sum(features[i]*projected[i] for i in range(n))
    if not finite(denominator) or denominator <= 0:
        raise ValueError("Invalid RLS denominator.")
    gain = [x/denominator for x in projected]
    residual = native_next_v-sum(theta[i]*features[i] for i in range(n))
    new_theta = [theta[i]+gain[i]*residual for i in range(n)]
    matrix = [[covariance[i][j]-gain[i]*projected[j] for j in range(n)] for i in range(n)]
    new_covariance = [[.5*(matrix[i][j]+matrix[j][i]) for j in range(n)] for i in range(n)]
    if not all(finite(x) for x in new_theta+[x for row in new_covariance for x in row]):
        raise ValueError("Nonfinite RLS replay.")
    return new_theta, new_covariance


def replay_mpc(theta, qref, q, v, target, previous, limits):
    """All nine H15 constant candidates; deterministic public tie break."""
    if not all(finite(x) for x in [target, previous, *limits]):
        raise ValueError("Finite planner inputs required.")
    lower, upper = max(qref-.15, limits[0]-.03), min(qref+.15, limits[1]+.03)
    feasible, calls = [], 0
    for index in range(9):
        torque, pq, pv = -.5+index*.125, q, v
        qs, vs = [], []
        cost = .00002*(torque-previous)**2
        for _ in range(15):
            calls += 1
            try:
                pq, pv = predict(theta, qref, pq, pv, torque)
            except (ValueError, OverflowError):
                break
            if not lower <= pq <= upper or abs(pv) > 1.5:
                break
            qs.append(pq)
            vs.append(pv)
            cost += (pq-target)**2+.002*pv*pv+.00002*torque*torque
            if not finite(cost):
                break
        else:
            feasible.append((cost, abs(torque), torque, qs, vs))
    if not feasible:
        return {"torque": 0., "feasible_candidates": 0, "fallback": True,
                "cost": None, "predicted_q": [], "predicted_v": [],
                "mathematical_prediction_calls": calls}
    cost, _, torque, qs, vs = min(feasible)
    return {"torque": torque, "feasible_candidates": len(feasible), "fallback": False,
            "cost": cost, "predicted_q": qs, "predicted_v": vs,
            "mathematical_prediction_calls": calls}


def free_rollout(theta, qref, q, v, recorded_requests):
    path = []
    for torque in recorded_requests:
        if theta is None:
            q += DT*v
        else:
            q, v = predict(theta, qref, q, v, torque)
        if not finite(q) or not finite(v):
            raise ValueError("Nonfinite free rollout.")
        path.append((q, v))
    return path


def valid_window(indexed, start, horizon):
    segment = []
    for index in range(start, start+horizon):
        row = indexed.get(index)
        if row is None:
            return None, "missing_control_row"
        if "collector_exception" in row:
            return None, "collector_exception"
        before, after = row["observation_before"], row["observation_after"]
        if not all(finite(obs[key][0]) for obs in (before, after) for key in ("joint_position", "joint_velocity")):
            return None, "invalid_native_state"
        if not finite(row["requested_torque"][0]):
            return None, "invalid_request"
        diagnostic = row["diagnostics"]
        if diagnostic["executed_substeps"] != 10:
            return None, "partial_physics_interval"
        if segment:
            previous = segment[-1]
            if previous["phase"] != row["phase"] or previous["trial_id"] != row["trial_id"]:
                return None, "crossed_phase_or_trial_boundary"
            if previous["diagnostics"]["terminated"]:
                return None, "continued_after_termination"
            if previous["observation_after"] != before:
                return None, "native_state_discontinuity"
            if abs(diagnostic["time"]-previous["diagnostics"]["time"]-DT) > 1e-10:
                return None, "time_discontinuity"
        segment.append(row)
    return segment, None


def window_denominators(indexed, active_steps, horizon):
    expected, valid, terminal = max(active_steps-horizon+1, 0), 0, 0
    excluded = Counter()
    for start in range(100, 100+expected):
        segment, reason = valid_window(indexed, start, horizon)
        if reason:
            excluded[reason] += 1
        else:
            valid += 1
            terminal += int(segment[-1]["diagnostics"]["terminated"])
    return {"expected_windows_from_planned_active_duration": expected,
            "valid_physical_windows": valid, "excluded_windows": expected-valid,
            "valid_windows_ending_in_termination": terminal, "exclusion_reasons": dict(excluded)}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


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

    def compare(self, actual, expected, location):
        if isinstance(expected, dict):
            self.check(isinstance(actual, dict), "object_shape", location)
            if isinstance(actual, dict):
                for key, value in expected.items():
                    self.check(key in actual, "required_field", location+"/"+key)
                    self.compare(actual.get(key), value, location+"/"+key)
        elif isinstance(expected, (tuple, list)):
            self.check(isinstance(actual, (tuple, list)) and len(actual) == len(expected), "array_shape", location)
            if isinstance(actual, (tuple, list)):
                for i, (a, b) in enumerate(zip(actual, expected)):
                    self.compare(a, b, location+"/"+str(i))
        elif type(expected) is float:
            valid = finite(actual) and finite(expected)
            difference = abs(actual-expected) if valid else None
            if valid:
                self.maximum_difference = max(self.maximum_difference, difference)
            self.check(valid and difference <= 1e-10, "numeric_recomputation",
                       {"location": location, "actual": actual, "expected": expected, "difference": difference})
        else:
            self.check(type(actual) is type(expected) and actual == expected, "exact_label_or_count", location)


def vector(value, length):
    if not isinstance(value, list) or len(value) != length or not all(finite(x) for x in value):
        raise ValueError(f"Expected {length} finite numeric measurements.")
    return value


def model_record(qref, theta, covariance):
    structure = {4: "linear4", 5: "hinge5"}[len(theta)]
    record = {"qref_rad": qref, "dt_seconds": DT,
              "features": ["v", "q-qref", "requested_torque", "1"],
              "initial_coefficients": INITIAL[structure], "initial_covariance_scale": 100.,
              "forgetting_factor": 1., "coefficients": theta, "covariance": covariance, "dtype": "float64"}
    if structure == "hinge5":
        record.update(features=["v", "q-qref", "requested_torque", "sign(u)*max(abs(u)-0.25,0)", "1"],
                      hinge_threshold_nm=.25, hinge_threshold_updates=0,
                      hinge_structure_prior="fixed signed torque hinge; structural prior, not a learned threshold or physics label")
    return record


def initial_state(structure):
    n = len(INITIAL[structure])
    return {"theta": INITIAL[structure].copy(), "covariance": [[100. if i == j else 0. for j in range(n)] for i in range(n)],
            "observed_theta": INITIAL[structure].copy(), "observed_covariance": [[100. if i == j else 0. for j in range(n)] for i in range(n)],
            "updates": 0, "exception_replayed_updates": 0, "unreconstructed_updates": 0}


def state_hash(qref, state):
    return digest(model_record(qref, state["observed_theta"], state["observed_covariance"]))


def integration_spec(fingerprint):
    return {"mode": INTEGRATION, "dt_seconds": DT, "rule": "q + dt * predicted_next_v",
            "endpoint_velocity_rule_unchanged": True, "dynamics_parameter_fingerprint": fingerprint}


def duration(kind):
    return 300 if kind.startswith("calibration_") else (100 if kind.startswith("prediction_") else 200)


def planned_matrix():
    return [{"trial_id": f"seed{seed}_{kind}", "seed": seed, "kind": kind,
             "model_scope": "nominal" if kind == "nominal_mpc" else ("learned" if kind.endswith("mpc") else "shared"),
             "calibration_dose": kind.split("_")[1] if kind.startswith("calibration_") else
                 (kind.split("_")[0] if kind.endswith("mpc") and kind != "nominal_mpc" else None),
             "model_structure": kind.split("_")[1] if kind.endswith("mpc") and kind != "nominal_mpc" else
                 ("linear4" if kind == "nominal_mpc" else None),
             "integration": INTEGRATION, "maximum_control_steps": 100+duration(kind)}
            for seed in SEEDS for kind in KINDS]


def require_development(path):
    metadata = load_json(Path(path)/"metadata.json")
    if (metadata.get("split") != "development" or metadata.get("seeds") != SEEDS
            or any(type(seed) is not int for seed in metadata.get("seeds", []))
            or metadata.get("pose") != "supine" or type(metadata.get("joint_index")) is not int
            or metadata["joint_index"] != 0):
        raise ValueError("Only supine joint 0 development seeds 0/1/2 may be read.")
    return metadata


def verify_sources(path, metadata, checks, git_root, required=REQUIRED_SOURCES):
    manifest = load_json(path/"manifest.json")
    names = {p.name for p in path.iterdir() if p.is_file() and p.name != "manifest.json"}
    checks.check(set(manifest) == names, "manifest_exact_coverage", str(path))
    checks.check({"metadata.json", "episodes.json", "seed_results.json", "trace.jsonl.gz", "source_snapshot.zip"}.issubset(manifest),
                 "manifest_core_files", str(path))
    for name, expected in manifest.items():
        local = Path(name).name == name and name not in (".", "..")
        checks.check(local, "manifest_local_filename", name)
        if local:
            checks.check((path/name).is_file() and file_hash(path/name) == expected, "manifest_hash", name)
    commit = metadata.get("source_commit", "")
    valid_commit = isinstance(commit, str) and bool(re.fullmatch(r"[0-9a-f]{40}", commit))
    checks.check(valid_commit, "source_commit_format", str(path))
    checks.check(metadata.get("source_status") == "" and metadata.get("source_dirty") is False, "clean_collection_source", str(path))
    hashes = metadata["source_sha256"]
    checks.check(required.issubset(hashes), "required_source_coverage", str(path))
    if git_root is not None and valid_commit:
        tree = subprocess.run(["git", "ls-tree", "-r", "--name-only", commit, "src/developmental_physics"],
                              cwd=git_root, capture_output=True, text=True, check=False)
        python_sources = {n for n in tree.stdout.splitlines() if n.endswith(".py") and n.count("/") == 2}
        checks.check(tree.returncode == 0 and python_sources.issubset(hashes), "all_package_sources_archived", str(path))
    with zipfile.ZipFile(path/"source_snapshot.zip") as archive:
        checks.check(len(archive.namelist()) == len(set(archive.namelist())) and set(archive.namelist()) == set(hashes),
                     "source_zip_exact_unique_coverage", str(path))
        for name, expected in hashes.items():
            checks.check(not Path(name).is_absolute() and ".." not in Path(name).parts, "source_relative_path", name)
            blob = archive.read(name)
            checks.check(hashlib.sha256(blob).hexdigest() == expected, "source_zip_hash", name)
            if git_root is not None and valid_commit:
                result = subprocess.run(["git", "show", f"{commit}:{name}"], cwd=git_root, capture_output=True, check=False)
                checks.check(result.returncode == 0 and result.stdout == blob, "source_git_blob_bytes", name)
        xml = ET.fromstring(archive.read(ASSET))
    compiler = xml.find("compiler")
    factor = math.pi/180. if compiler is not None and compiler.get("angle", "degree") == "degree" else 1.
    ranges = {j.get("name"): [float(x)*factor for x in j.get("range").split()]
              for j in xml.findall(".//joint") if j.get("range")}
    return [ranges[name] for name in JOINTS], {**manifest, "manifest.json": file_hash(path/"manifest.json")}


def rmse(values):
    if not values:
        return None
    scale = max(abs(x) for x in values)
    return 0. if scale == 0 else scale*math.sqrt(sum((x/scale)**2 for x in values)/len(values))


def trace_payload(row):
    return {key: row[key] for key in ("phase", "target_q", "requested_torque", "observation_before",
                                     "observation_after", "qpos", "qvel", "diagnostics")}


def new_effort():
    return {key: 0. for key in EFFORT_KEYS}


def new_risk():
    return {"ground_force_peak_n": 0., "ground_normal_impulse_ns": 0., "kinetic_energy_peak_j": 0.,
            "minimum_contact_distance_m": 0., "maximum_penetration_m": 0., "native_joint_speed_peak_rad_s": [0.]*8,
            "soft_limit_excursion_peak_rad": [0.]*8, "guard_margin_intrusion_peak_rad": [0.]*8,
            "permission_screened_substeps_by_joint": [0]*8, "guarded_substeps": 0,
            "target_guarded_substeps": 0, "physical_substeps": 0, "returned_endpoint_samples": 0}


def record_risk(risk, row, ranges):
    d = row["diagnostics"]
    risk["ground_force_peak_n"] = max(risk["ground_force_peak_n"], *d["substep_ground_normal_forces"], 0.)
    risk["ground_normal_impulse_ns"] += sum(d["substep_ground_normal_forces"])*PHYSICS_DT
    risk["kinetic_energy_peak_j"] = max(risk["kinetic_energy_peak_j"], *d["substep_kinetic_energies"], 0.)
    risk["minimum_contact_distance_m"] = min(risk["minimum_contact_distance_m"], *d["substep_minimum_contact_distances"], 0.)
    risk["maximum_penetration_m"] = -risk["minimum_contact_distance_m"]
    for j, (q, v, limits) in enumerate(zip(row["observation_after"]["joint_position"], row["observation_after"]["joint_velocity"], ranges)):
        risk["native_joint_speed_peak_rad_s"][j] = max(risk["native_joint_speed_peak_rad_s"][j], abs(v))
        risk["soft_limit_excursion_peak_rad"][j] = max(risk["soft_limit_excursion_peak_rad"][j], limits[0]-q, q-limits[1])
        risk["guard_margin_intrusion_peak_rad"][j] = max(risk["guard_margin_intrusion_peak_rad"][j], limits[0]+.08-q, q-limits[1]+.08)
        risk["permission_screened_substeps_by_joint"][j] += sum(a[j] != row["requested_torque"][j] for a in d["applied_torque_history"])
    risk["guarded_substeps"] += d["guarded_substeps"]
    risk["target_guarded_substeps"] += sum(a[0] != row["requested_torque"][0] for a in d["applied_torque_history"])
    risk["physical_substeps"] += d["executed_substeps"]
    risk["returned_endpoint_samples"] += 1


def verify_budget_bounds(ep, checks, location):
    kind = ep["kind"]
    caps = {"prefix": 100, "calibration": 300 if kind.startswith("calibration_") else 0,
            "prediction": 100 if kind.startswith("prediction_") else 0,
            "control": 200 if kind in CONTROL_KINDS else 0}
    for phase, cap in caps.items():
        b = ep["phase_budgets"][phase]
        checks.check(all(type(b[k]) is int and 0 <= b[k] <= cap for k in ("control_calls_attempted", "control_steps"))
                     and type(b["physics_steps"]) is int and 0 <= b["physics_steps"] <= cap*10,
                     "frozen_phase_budget_cap", location+"/"+phase)
    maximum = 100+duration(kind)
    checks.check(all(type(ep[k]) is int and 0 <= ep[k] <= maximum for k in ("control_calls_attempted", "control_steps"))
                 and type(ep["physics_steps"]) is int and 0 <= ep["physics_steps"] <= maximum*10,
                 "frozen_trial_budget_cap", location)


def reconcile_effort(ev, phase, observed, paid, raw_substeps, exceptions, checks, location):
    """Recover known paid requests; absent realized history remains a lower bound."""
    missing, known = paid-raw_substeps, dict(observed)
    commands = [r.get("requested_torque") for r in exceptions if r.get("phase") == phase]
    recoverable = missing == 0 or (0 < missing <= 10 and len(commands) == 1
        and isinstance(commands[0], list) and len(commands[0]) == 8
        and all(finite(u) and abs(u) <= .5 for u in commands[0]) and commands[0][1:] == [0.]*7)
    if missing > 0 and recoverable:
        u = commands[0][0]
        known["requested_absolute_nm_s"] += abs(u)*missing*PHYSICS_DT
        known["requested_squared_nm2_s"] += u*u*missing*PHYSICS_DT
    recorded, measured = ev["phase_effort"][phase], ev["phase_actual_effort_substeps"][phase]
    checks.check(type(measured) is int and raw_substeps <= measured <= paid, "measured_actual_effort_bounds", location)
    checks.compare(ev["phase_actual_effort_complete"][phase], measured == paid, location+"/collector_complete")
    for key in EFFORT_KEYS:
        checks.check(finite(recorded[key]) and recorded[key] >= 0, "nonnegative_effort", location+"/"+key)
    if recoverable:
        for key in EFFORT_KEYS[:2]:
            checks.compare(recorded[key], known[key], location+"/"+key)
    for key, maximum in zip(EFFORT_KEYS[2:], (.5, .25)):
        if missing == 0:
            checks.compare(recorded[key], known[key], location+"/"+key)
        else:
            checks.check(known[key]-1e-10 <= recorded[key] <= known[key]+maximum*(measured-raw_substeps)*PHYSICS_DT+1e-10,
                         "unreconstructed_actual_within_permission", location+"/"+key)
    return {"independent_effort": known, "requested_effort_reconstruction_complete": recoverable,
            "actual_effort_reconstruction_complete": missing == 0, "actual_effort_is_lower_bound": missing > 0,
            "unreconstructed_actual_effort_substeps": missing, "collector_reported_effort": recorded,
            "collector_reported_actual_measured_substeps": measured,
            "semantics": "raw-history actual lower bound when telemetry is absent; collector measurement completeness is separate"}


def verify_transition(row, previous, counters, ranges, checks, location):
    """Validate native fields and every saved physical-substep diagnostic."""
    before, after = row["observation_before"], row["observation_after"]
    for obs in (before, after):
        checks.check(set(obs) == set(NATIVE), "native_observation_whitelist", location)
        for key, width in NATIVE.items():
            vector(obs[key], width)
    checks.check(previous is None or previous == before, "native_continuity", location)
    qpos, qvel = vector(row["qpos"], 15), vector(row["qvel"], 14)
    checks.check(after["joint_position"] == qpos[7:] and after["joint_velocity"] == qvel[6:], "native_encoder_mapping", location)
    request = vector(row["requested_torque"], 8)
    checks.check(abs(request[0]) <= .5 and request[1:] == [0.]*7, "shared_permission_other_joints_zero", location)
    diagnostic, index = row["diagnostics"], row["step_index"]
    n = diagnostic["executed_substeps"]
    checks.check(type(n) is int and 0 <= n <= 10 and (n == 10 or diagnostic["terminated"]), "legal_partial_substeps", location)
    counters["physics"] += n
    checks.compare(diagnostic["step_id"], index+1, location+"/step_counter")
    checks.compare(diagnostic["physics_steps"], counters["physics"], location+"/physics_counter")
    checks.compare(diagnostic["time"], counters["physics"]*PHYSICS_DT, location+"/physical_time")
    checks.compare(diagnostic["requested_torque"], request, location+"/diagnostic_request")
    checks.compare(diagnostic["accepted_torque"], request, location+"/accepted_request")
    history = diagnostic["applied_torque_history"]
    checks.check(len(history) == n, "returned_torque_substeps", location)
    guarded = 0
    for actual in history:
        vector(actual, 8)
        checks.check(all(a in (0., u) for a, u in zip(actual, request)), "shield_preserves_or_zeroes", location)
        guarded += any(a != u for a, u in zip(actual, request))
    checks.check(type(diagnostic["guarded_substeps"]) is int and guarded <= diagnostic["guarded_substeps"] <= n, "guarded_substep_bounds", location)
    if history:
        checks.compare(diagnostic["applied_torque"], history[-1], location+"/last_applied")
        # A stop zeros actuator control after the final integration; its native
        # actuator_force is still the last physically realized torque.
        checks.compare(after["actuator_torque"], history[-1], location+"/native_actuator")
    checks.compare(after["previous_command"], request, location+"/known_command")
    for name in ("substep_ground_normal_forces", "substep_kinetic_energies", "substep_minimum_contact_distances"):
        vector(diagnostic[name], n)
    checks.check(all(x >= 0 for x in diagnostic["substep_ground_normal_forces"]+diagnostic["substep_kinetic_energies"]),
                 "nonnegative_force_energy", location)
    checks.compare(diagnostic["peak_substep_ground_normal_force"], max(diagnostic["substep_ground_normal_forces"], default=0.), location+"/force_peak")
    checks.compare(diagnostic["ground_normal_impulse_ns"], sum(diagnostic["substep_ground_normal_forces"])*PHYSICS_DT, location+"/force_impulse")
    checks.compare(diagnostic["peak_substep_kinetic_energy"], max(diagnostic["substep_kinetic_energies"], default=0.), location+"/energy_peak")
    checks.compare(diagnostic["minimum_substep_contact_distance"], min(diagnostic["substep_minimum_contact_distances"], default=0.), location+"/contact_distance")
    return n


def replay_update(item, row, structure, state, qref, checks, location, *, exception=False):
    """Only an explicitly recorded successful atomic update consumes one replay."""
    q, v = (row["observation_before"][k][0] for k in ("joint_position", "joint_velocity"))
    u, next_v = row["requested_torque"][0], row["observation_after"]["joint_velocity"][0]
    features = feature_vector(qref, q, v, u, structure)
    before_hash = state_hash(qref, state)
    predicted = predict(state["observed_theta"], qref, q, v, u)
    checks.compare(item, {"model_id": row["calibration_dose"]+"_"+structure,
        "shared_transition_id": row["shared_transition_id"], "phase": "identification", "updated": True,
        "features": features, "observed_next_v_rad_s": next_v,
        "preupdate_prediction": {"next_q_rad": predicted[0], "next_v_rad_s": predicted[1]},
        "preupdate_error_rad_s": next_v-predicted[1], "parameter_fingerprint_before": before_hash}, location+"/causality")
    state["theta"], state["covariance"] = replay_rls(state["theta"], state["covariance"], features, next_v)
    state["updates"] += 1
    state["exception_replayed_updates"] += int(exception)
    checks.compare(item["coefficients_after"], state["theta"], location+"/theta")
    checks.compare(item["covariance_after"], state["covariance"], location+"/P")
    checks.compare(item["update_count"], state["updates"], location+"/count")
    state["observed_theta"], state["observed_covariance"] = item["coefficients_after"], item["covariance_after"]
    checks.compare(item["parameter_fingerprint_after"], state_hash(qref, state), location+"/hash_chain")


def verify_snapshot(saved, state, qref, checks, location):
    n = len(state["theta"])
    vector(saved["coefficients"], n)
    if len(saved["covariance"]) != n:
        raise ValueError("Malformed saved covariance.")
    for row in saved["covariance"]:
        vector(row, n)
    record = model_record(qref, saved["coefficients"], saved["covariance"])
    checks.compare(saved, record, location+"/configuration")
    checks.compare(saved["parameter_fingerprint"], digest(record), location+"/self_hash")
    count = saved["update_count"]
    checks.check(type(count) is int and state["updates"] <= count <= 300, "saved_atomic_update_cap", location)
    checks.compare(saved["trainable"], False, location+"/frozen")
    if count == state["updates"]:
        checks.compare(saved["coefficients"], state["theta"], location+"/final_theta")
        checks.compare(saved["covariance"], state["covariance"], location+"/final_P")
        checks.compare(saved["parameter_fingerprint"], state_hash(qref, state), location+"/final_hash")
    state["unreconstructed_updates"] = count-state["updates"]
    return count == state["updates"]


def diagnose_windows(rows, active_steps, qref, models):
    indexed = {r["step_index"]: r for r in rows if "collector_exception" not in r}
    predictors = {**models, "persistence": None}
    reports = []
    for horizon in HORIZONS:
        denominator = window_denominators(indexed, active_steps, horizon)
        errors = {name: {"q": [], "v": [], "path_q": [], "path_v": [], "invalid": 0} for name in predictors}
        for start in range(100, 100+max(active_steps-horizon+1, 0)):
            segment, reason = valid_window(indexed, start, horizon)
            if reason:
                continue
            first = segment[0]["observation_before"]
            q, v = first["joint_position"][0], first["joint_velocity"][0]
            requests = [r["requested_torque"][0] for r in segment]
            truth = [(r["observation_after"]["joint_position"][0], r["observation_after"]["joint_velocity"][0]) for r in segment]
            for name, theta in predictors.items():
                values = errors[name]
                try:
                    path = free_rollout(theta, qref, q, v, requests)
                    qe, ve = [p[0]-t[0] for p, t in zip(path, truth)], [p[1]-t[1] for p, t in zip(path, truth)]
                    if not all(finite(x) for x in qe+ve):
                        raise ValueError("Nonfinite rollout error.")
                    values["q"].append(qe[-1])
                    values["v"].append(ve[-1])
                    values["path_q"].extend(qe)
                    values["path_v"].extend(ve)
                except (ValueError, OverflowError):
                    values["invalid"] += 1
        reports.append({"horizon_control_steps": horizon, **denominator,
            "predictors": {name: {"valid_prediction_windows": len(e["q"]), "invalid_prediction_windows": e["invalid"],
                "path_endpoint_samples": len(e["path_q"]), "terminal_position_rmse_rad": rmse(e["q"]),
                "terminal_velocity_rmse_rad_s": rmse(e["v"]), "path_position_rmse_rad": rmse(e["path_q"]),
                "path_velocity_rmse_rad_s": rmse(e["path_v"])} for name, e in errors.items()}})
    return reports


def conditional_metrics(rows):
    """Every amplitude/block and control switch/hold is reported, including zero."""
    groups = {}
    for r in rows:
        if r["step_index"] < 100 or "collector_exception" in r:
            continue
        index, u = r["step_index"]-100, r["requested_torque"][0]
        labels = ["abs_u="+str(abs(u)), "signed_u="+str(u)]
        if r["phase"] in ("calibration", "prediction"):
            width = 30 if r["phase"] == "calibration" else 20
            labels.append("block="+str(index//width))
        if r["phase"] == "control":
            labels.extend(["target="+("first" if index < 100 else "second"), "switch" if index in (0, 100) else "hold"])
        for label in labels:
            values = groups.setdefault(label, {"count": 0, "q": {}, "v": {}, "tracking": [], "effort": new_effort()})
            values["count"] += 1
            for name, (pq, pv) in r["predicted_next_qv"].items():
                values["q"].setdefault(name, []).append(r["observation_after"]["joint_position"][0]-pq)
                values["v"].setdefault(name, []).append(r["observation_after"]["joint_velocity"][0]-pv)
            if r["target_q"] is not None:
                values["tracking"].append(r["observation_after"]["joint_position"][0]-r["target_q"])
            n, history = r["diagnostics"]["executed_substeps"], r["diagnostics"]["applied_torque_history"]
            values["effort"][EFFORT_KEYS[0]] += abs(u)*n*PHYSICS_DT
            values["effort"][EFFORT_KEYS[1]] += u*u*n*PHYSICS_DT
            values["effort"][EFFORT_KEYS[2]] += sum(abs(a[0]) for a in history)*PHYSICS_DT
            values["effort"][EFFORT_KEYS[3]] += sum(a[0]*a[0] for a in history)*PHYSICS_DT
    return {label: {"returned_transition_count": e["count"], "position_prediction_rmse": {n: rmse(v) for n, v in e["q"].items()},
        "velocity_prediction_rmse": {n: rmse(v) for n, v in e["v"].items()}, "tracking_rmse_rad": rmse(e["tracking"]),
        "known_substep_effort": e["effort"]} for label, e in sorted(groups.items())}


def state_coverage(calibration_rows, control_rows, qref):
    """Public q/v support and nearest distances; envelope is not a safety set."""
    calibration = [(r["observation_before"]["joint_position"][0]-qref, r["observation_before"]["joint_velocity"][0])
        for r in calibration_rows if r["step_index"] >= 100 and r["diagnostics"]["executed_substeps"] == 10]
    control = [(r["observation_before"]["joint_position"][0]-qref, r["observation_before"]["joint_velocity"][0])
        for r in control_rows if r["step_index"] >= 100 and r["diagnostics"]["executed_substeps"] == 10]
    if not calibration:
        return {"calibration_native_samples": 0, "control_native_samples": len(control), "available": False}
    lower = [min(x[i] for x in calibration) for i in range(2)]
    upper = [max(x[i] for x in calibration) for i in range(2)]
    q_out = sum(not lower[0] <= q <= upper[0] for q, v in control)
    v_out = sum(not lower[1] <= v <= upper[1] for q, v in control)
    union = sum(not (lower[0] <= q <= upper[0] and lower[1] <= v <= upper[1]) for q, v in control)
    nearest_q = []
    for q, v in control:
        nearest_q.append(min(abs(q-cq) for cq, cv in calibration))
    return {"available": True, "calibration_native_samples": len(calibration), "control_native_samples": len(control),
        "q_offset_envelope_rad": [lower[0], upper[0]], "velocity_envelope_rad_s": [lower[1], upper[1]],
        "q_outside_count": q_out, "v_outside_count": v_out, "either_outside_count": union,
        "q_outside_fraction": q_out/len(control) if control else None, "v_outside_fraction": v_out/len(control) if control else None,
        "either_outside_fraction": union/len(control) if control else None,
        "nearest_q_distance_mean_rad": sum(nearest_q)/len(control) if control else None,
        "nearest_q_distance_max_rad": max(nearest_q, default=None),
        "semantics": "Nearest min abs(q-q_i) over complete calibration inputs, in rad; position only, not a joint q/v distance. Strict outside bounds; equality is inside. Descriptive envelope is not safe and does not enter adoption."}


def audit_archive(path, checks, git_root=ROOT):
    path = Path(path).resolve()
    metadata = require_development(path)
    ranges, input_hashes = verify_sources(path, metadata, checks, git_root)
    checks.compare(metadata["protocol"], {"path": PROTOCOL, "sha256": metadata["source_sha256"][PROTOCOL]}, "frozen_protocol")
    checks.compare(metadata["environment_config"], ENVIRONMENT, "environment_and_permission")
    checks.compare(metadata["integration"], INTEGRATION, "frozen_integration")
    checks.compare(metadata["evaluation_prediction_integration"], INTEGRATION, "evaluation_integration")
    checks.compare(metadata["structures"], list(STRUCTURES), "frozen_structures")
    checks.compare(metadata["factorial"], {"calibration_dose": ["old", "new"], "model_structure": list(STRUCTURES)}, "frozen_factorial")
    checks.compare(metadata["calibration_block_amplitudes_nm"], CALIBRATION_AMPLITUDES, "calibration_doses")
    checks.compare(metadata["prediction_block_amplitudes_nm"], PREDICTION_AMPLITUDES, "prediction_doses")
    checks.compare(metadata, {"gpu": None, "prefix_steps": 100, "calibration_steps": 300,
        "prediction_steps": 100, "control_steps_per_trial": 200, "teacher_calls": 0,
        "external_demonstration_samples": 0, "policy_parameter_updates": 0}, "frozen_metadata")
    plans = planned_matrix()
    checks.compare(metadata["planned_episodes"], plans, "frozen_full_plan")
    checks.compare(metadata["planned_episode_count"], 27, "planned_trials")
    checks.compare(metadata["maximum_control_steps"], 8100, "planned_budget")
    episodes, results = load_json(path/"episodes.json"), load_json(path/"seed_results.json")
    checks.compare([ep["trial_id"] for ep in episodes], [p["trial_id"] for p in plans], "complete_outcome_ledger")
    episode_map = {ep["trial_id"]: ep for ep in episodes}
    if len(episode_map) != len(episodes):
        raise ValueError("Duplicate episode IDs.")
    by_seed = {r["seed"]: r for r in results}
    checks.check(len(by_seed) == len(results) and set(by_seed).issubset(SEEDS), "unique_known_seed_snapshots")
    grouped = {}
    trace_order = []
    with gzip.open(path/"trace.jsonl.gz", "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            checks.check(row.get("trial_id") in episode_map, "known_trace_trial", row.get("trial_id"))
            if not trace_order or trace_order[-1] != row["trial_id"]:
                trace_order.append(row["trial_id"])
            grouped.setdefault(row["trial_id"], []).append(row)
    expected_order = [p["trial_id"] for p in plans if p["trial_id"] in grouped]
    checks.compare(trace_order, expected_order, "trace_trial_order")
    derived_seeds = []
    for seed in SEEDS:
        sr = by_seed.get(seed)
        if sr is None:
            checks.check(all(episode_map[f"seed{seed}_{k}"]["status"] == "blocked" for k in KINDS), "unstarted_seed_all_blocked", seed)
            derived_seeds.append({"seed": seed, "complete": False, "evaluations": {}})
            continue
        checks.compare(sr["reset_seed"], [3757552657, 1641411168, 2001025171][seed], f"seed{seed}/fixed_reset_derivation")
        checks.check(type(sr["calibration_updates"]) is int and 0 <= sr["calibration_updates"] <= 1200, "seed_update_cap", seed)
        qref, direction = sr.get("reference_q"), sr.get("direction")
        states, hashes, view_hashes, final_models, derived = {}, {}, {}, {}, {}
        prefix_reference, calibration_complete = None, {"old": False, "new": False}
        if qref is not None:
            if not finite(qref):
                raise ValueError("Nonfinite reference.")
            positive, negative = ranges[0][1]-qref, qref-ranges[0][0]
            checks.compare(direction, 1 if positive >= negative else -1, f"seed{seed}/public_direction")
            checks.compare(sr["selection_record"], {"joint_index": 0, "joint_position_rad": qref,
                "lower_limit_rad": ranges[0][0], "upper_limit_rad": ranges[0][1],
                "positive_room_rad": positive, "negative_room_rad": negative, "direction": direction,
                "rule": "larger distance to the public joint limit; ties choose positive"}, f"seed{seed}/direction_record")
        for kind in KINDS:
            tid, is_cal = f"seed{seed}_{kind}", kind.startswith("calibration_")
            ep, plan = episode_map[tid], next(p for p in plans if p["trial_id"] == tid)
            ev = sr["evaluations"].get(kind)
            failure_start = checks.failed
            checks.compare(ep, plan, tid+"/plan")
            verify_budget_bounds(ep, checks, tid)
            rows = grouped.get(tid, [])
            regular = [r for r in rows if "collector_exception" not in r]
            exceptions = [r for r in rows if "collector_exception" in r]
            checks.check(ep["status"] in ("completed", "terminated", "exception", "blocked"), "recorded_outcome", tid)
            checks.check(len(exceptions) <= 1 and (not exceptions or rows[-1] is exceptions[-1] and ep["status"] == "exception"), "single_final_exception", tid)
            dependencies = ["old", "new"] if kind.startswith("prediction_") else ([plan["calibration_dose"]] if kind in CONTROL_KINDS and kind != "nominal_mpc" else [])
            missing_dependencies = [d for d in dependencies if not calibration_complete[d]]
            if ep["status"] != "blocked":
                checks.check(not missing_dependencies, "failed_calibration_dependents_blocked", tid)
            elif ep.get("reason", {}).get("type") == "DependencyBlocked":
                checks.compare(ep["reason"].get("dependencies"), [f"seed{seed}_calibration_{d}" for d in missing_dependencies], tid+"/dependencies")
                checks.check(bool(missing_dependencies), "dependency_block_requires_failure", tid)
                checks.check(kind != "nominal_mpc", "nominal_independent_of_fit", tid)
            prefix = [trace_payload(r) for r in regular if r["step_index"] < 100]
            if len(prefix) == 100:
                if prefix_reference is None:
                    prefix_reference = prefix
                else:
                    checks.check(prefix == prefix_reference, "exact_paid_prefix_all_nine_trials", tid)
            scores_q, scores_v, tracking = {}, {}, []
            observed_effort = {p: new_effort() for p in PHASES}
            phase_rows, phase_physics = Counter(), Counter()
            phase_risk, risk_full = {p: new_risk() for p in PHASES}, new_risk()
            previous_after, previous_request = None, 0.
            counters = {"physics": 0}
            planner_calls = fallbacks = saturated = 0
            before_views, before_hashes = dict(view_hashes), dict(hashes)

            def establish_models():
                if qref is None:
                    raise ValueError("Active trial lacks native reference.")
                if "nominal" not in hashes:
                    nominal = initial_state("linear4")
                    hashes["nominal"] = state_hash(qref, nominal)
                    view_hashes["nominal_mpc"] = digest(integration_spec(hashes["nominal"]))
                    final_models["nominal_mpc"] = INITIAL["linear4"]
                if is_cal:
                    for structure in STRUCTURES:
                        name = plan["calibration_dose"]+"_"+structure
                        if name not in states:
                            states[name] = initial_state(structure)
                            hashes[name] = state_hash(qref, states[name])
                            checks.compare(sr["initial_models"][name], {**model_record(qref, states[name]["theta"], states[name]["covariance"]),
                                "parameter_fingerprint": hashes[name], "update_count": 0, "trainable": False}, tid+"/initial/"+structure)

            for index, row in enumerate(regular):
                loc = tid+"/"+str(index)
                checks.compare(row["step_index"], index, loc+"/index")
                phase = "prefix" if index < 100 else ("calibration" if is_cal else ("prediction" if kind.startswith("prediction_") else "control"))
                checks.compare(row, {"seed": seed, "kind": kind, "phase": phase, "model_scope": plan["model_scope"],
                    "calibration_dose": plan["calibration_dose"], "model_structure": plan["model_structure"],
                    "integration": INTEGRATION, "shared_transition_id": tid+":"+str(index)}, loc+"/identity")
                n = verify_transition(row, previous_after, counters, ranges, checks, loc)
                previous_after = row["observation_after"]
                phase_rows[phase] += 1
                phase_physics[phase] += n
                record_risk(risk_full, row, ranges)
                record_risk(phase_risk[phase], row, ranges)
                checks.check(not row["diagnostics"]["terminated"] or index == len(regular)-1 and ep["status"] in ("terminated", "exception"), "terminal_final_row", loc)
                q, v = (row["observation_before"][key][0] for key in ("joint_position", "joint_velocity"))
                next_q, next_v = (row["observation_after"][key][0] for key in ("joint_position", "joint_velocity"))
                u, history = row["requested_torque"][0], row["diagnostics"]["applied_torque_history"]
                effort = observed_effort[phase]
                effort[EFFORT_KEYS[0]] += abs(u)*n*PHYSICS_DT
                effort[EFFORT_KEYS[1]] += u*u*n*PHYSICS_DT
                effort[EFFORT_KEYS[2]] += sum(abs(a[0]) for a in history)*PHYSICS_DT
                effort[EFFORT_KEYS[3]] += sum(a[0]*a[0] for a in history)*PHYSICS_DT
                if index < 100:
                    checks.compare(row, {"requested_torque": [0.]*8, "predicted_next_qv": {},
                        "model_update": None, "target_q": None, "planner_decision": None}, loc+"/paid_prefix")
                    continue
                if index == 100:
                    checks.compare(q, qref, loc+"/prefix_reference")
                    establish_models()
                    if not is_cal:
                        before_hashes, before_views = dict(hashes), dict(view_hashes)
                active = index-100
                if phase in ("calibration", "prediction"):
                    width, ends = (30, (5, 15, 20)) if is_cal else (20, (7, 10, 17))
                    amplitudes = CALIBRATION_AMPLITUDES[plan["calibration_dose"]] if is_cal else PREDICTION_AMPLITUDES[kind.split("_")[1]]
                    slot, amplitude = active % width, amplitudes[active//width]
                    prescribed = direction*(amplitude if slot < ends[0] else (-amplitude if ends[1] <= slot < ends[2] else 0.))
                    checks.compare(row, {"requested_torque": [prescribed]+[0.]*7, "target_q": None, "planner_decision": None}, loc+"/fixed_schedule")
                else:
                    target = qref+direction*(.04 if active < 100 else .08)
                    checks.compare(row["target_q"], target, loc+"/current_target")
                    checks.check(ranges[0][0]+.03 <= target <= ranges[0][1]-.03, "public_target_interior", loc)
                    decision = replay_mpc(final_models[kind], qref, q, v, target, previous_request, ranges[0])
                    checks.compare(row["planner_decision"], decision, loc+"/all_candidate_planning")
                    checks.compare(u, decision["torque"], loc+"/selected_request")
                    planner_calls += decision["mathematical_prediction_calls"]
                    fallbacks += int(decision["fallback"])
                    tracking.append(next_q-target)
                    saturated += int(abs(u) == .5)
                if is_cal:
                    predictions = {s: predict(states[plan["calibration_dose"]+"_"+s]["observed_theta"], qref, q, v, u) for s in STRUCTURES}
                else:
                    predictions = {name: predict(theta, qref, q, v, u) for name, theta in final_models.items()}
                    predictions["persistence"] = (q+DT*v, v)
                checks.check(set(row["predicted_next_qv"]) == set(predictions), "exact_prediction_model_set", loc)
                checks.compare(row["predicted_next_qv"], predictions, loc+"/preupdate_predictions")
                for name, (pq, pv) in predictions.items():
                    scores_q.setdefault(name, []).append(next_q-pq)
                    scores_v.setdefault(name, []).append(next_v-pv)
                if is_cal:
                    checks.check(set(row["model_update"]) == set(STRUCTURES), "two_independent_update_records", loc)
                    for structure in STRUCTURES:
                        state, item = states[plan["calibration_dose"]+"_"+structure], row["model_update"][structure]
                        if n == 10:
                            replay_update(item, row, structure, state, qref, checks, loc+"/"+structure)
                        else:
                            checks.compare(item, {"updated": False, "phase": "partial_calibration_interval", "executed_substeps": n,
                                "update_count": state["updates"], "model_id": plan["calibration_dose"]+"_"+structure,
                                "shared_transition_id": row["shared_transition_id"]}, loc+"/no_partial_update")
                else:
                    checks.compare(row["model_update"], None, loc+"/evaluation_no_update")
                previous_request = u
            # Exceptional endpoints are not regular rows or rollout windows.
            # Successful atomic updates may nonetheless be fully reconstructible.
            for exception in exceptions:
                if is_cal and exception.get("step_index", -1) is not None and exception["step_index"] >= 100:
                    establish_models()
                    checks.compare(exception["shared_transition_id"], tid+":"+str(exception["step_index"]), tid+"/exception_id")
                    native_endpoint = exception.get("observation_after")
                    update_items = exception.get("model_update") or {}
                    for structure in STRUCTURES:
                        state = states[plan["calibration_dose"]+"_"+structure]
                        item = update_items.get(structure)
                        already_recorded = any(r["shared_transition_id"] == exception["shared_transition_id"] for r in regular)
                        full_exception_interval = (exception["step_index"] == len(regular)
                            and ep["physics_steps"]-counters["physics"] == 10
                            and ep["phase_budgets"]["calibration"]["physics_steps"]-phase_physics["calibration"] == 10
                            and exception.get("diagnostics", {}).get("physics_steps") == ep["physics_steps"])
                        if already_recorded and item is not None:
                            original = next(r for r in regular if r["shared_transition_id"] == exception["shared_transition_id"])
                            checks.compare(item, original["model_update"][structure], tid+"/duplicate_exception_snapshot/"+structure)
                        elif item is not None and item.get("updated") is True:
                            checks.check(native_endpoint is not None and full_exception_interval, "exception_update_full_native_interval", tid)
                            if native_endpoint is not None and full_exception_interval:
                                for observation in (exception["observation_before"], native_endpoint):
                                    checks.check(set(observation) == set(NATIVE), "exception_native_whitelist", tid)
                                    for key, width in NATIVE.items():
                                        vector(observation[key], width)
                                checks.check(previous_after == exception["observation_before"], "exception_native_continuity", tid)
                                replay_update(item, exception, structure, state, qref, checks, tid+"/exception/"+structure, exception=True)
                        snapshot = exception.get("partial_model_snapshots", {}).get(structure)
                        if snapshot is not None:
                            # A throw after atomic update but before its return can
                            # be recovered from the raw endpoint and saved snapshot.
                            if (not already_recorded and snapshot["update_count"] == state["updates"]+1 and item is None
                                    and native_endpoint is not None and full_exception_interval):
                                q, v = (exception["observation_before"][k][0] for k in ("joint_position", "joint_velocity"))
                                u, nv = exception["requested_torque"][0], native_endpoint["joint_velocity"][0]
                                state["theta"], state["covariance"] = replay_rls(state["theta"], state["covariance"], feature_vector(qref, q, v, u, structure), nv)
                                state["updates"] += 1
                                state["exception_replayed_updates"] += 1
                                state["observed_theta"], state["observed_covariance"] = snapshot["coefficients"], snapshot["covariance"]
                            checks.compare(snapshot["update_count"], state["updates"], tid+"/exception_snapshot_count/"+structure)
                            checks.compare(snapshot["coefficients"], state["theta"], tid+"/exception_snapshot_theta/"+structure)
                            checks.compare(snapshot["covariance"], state["covariance"], tid+"/exception_snapshot_P/"+structure)
                            checks.compare(snapshot["parameter_fingerprint"], state_hash(qref, state), tid+"/exception_snapshot_hash/"+structure)
            for phase in PHASES:
                b = ep["phase_budgets"][phase]
                checks.check(b["control_calls_attempted"] >= b["control_steps"] >= phase_rows[phase]
                    and phase_physics[phase] <= b["physics_steps"] <= b["control_calls_attempted"]*10,
                    "paid_vs_returned_phase", tid+"/"+phase)
            for key in ("control_calls_attempted", "control_steps", "physics_steps"):
                checks.compare(ep[key], sum(b[key] for b in ep["phase_budgets"].values()), tid+"/ledger_"+key)
            missing_physics, missing_rows = ep["physics_steps"]-counters["physics"], ep["control_steps"]-len(regular)
            checks.check(missing_physics >= 0 and missing_rows >= 0 and missing_physics <= 10 and missing_rows <= 1,
                         "single_failure_missing_cost_bounds", tid)
            complete = (ep["status"] == "completed" and len(regular) == plan["maximum_control_steps"]
                and ep["control_calls_attempted"] == ep["control_steps"] == len(regular)
                and ep["physics_steps"] == 10*len(regular) and not exceptions
                and all(not r["diagnostics"]["terminated"] and r["diagnostics"]["executed_substeps"] == 10 for r in regular))
            checks.check(ep["status"] != "completed" or complete, "claimed_complete_full_valid_trajectory", tid)
            if ep["status"] == "blocked":
                checks.check(not rows and ep["control_calls_attempted"] == ep["control_steps"] == ep["physics_steps"] == 0, "blocked_zero_physical_cost", tid)
            if is_cal:
                dose = plan["calibration_dose"]
                calibration_complete[dose] = complete
                checks.compare(sr["calibration_completed"][dose], complete, tid+"/calibration_complete")
                for structure in STRUCTURES:
                    name = dose+"_"+structure
                    if name in states:
                        saved = sr["calibration_models"][dose][structure]
                        reconstructed = verify_snapshot(saved, states[name], qref, checks, tid+"/final/"+structure)
                        checks.compare(sr["learned_models"][name], saved, tid+"/consistent_frozen_clone/"+structure)
                        hashes[name] = saved["parameter_fingerprint"]
                        if complete:
                            checks.check(reconstructed, "complete_model_fully_replayed", tid+"/"+structure)
                            checks.compare(states[name]["updates"], 300, tid+"/fixed_updates/"+structure)
                            view_hashes[name+"_mpc"] = digest(integration_spec(hashes[name]))
                            final_models[name+"_mpc"] = saved["coefficients"]
                    else:
                        checks.check(structure not in sr["calibration_models"].get(dose, {}), "no_model_before_active", tid)
            effort_audits = {}
            if ep["status"] != "blocked":
                checks.compare(ev["completed"], complete, tid+"/completion")
                checks.compare(ev["status"], ep["status"], tid+"/status")
                if complete:
                    checks.compare(ev, {"tracking_rmse_rad": rmse(tracking), "metric_control_step_count": len(tracking),
                        "position_prediction_rmse": {n: rmse(v) for n, v in scores_q.items()},
                        "velocity_prediction_rmse": {n: rmse(v) for n, v in scores_v.items()}, "saturated_control_steps": saturated}, tid+"/complete_metrics")
                    checks.check(ep["environment_fingerprint_before"] == ep["environment_fingerprint_after"], "fixed_physical_parameters", tid)
                for phase in PHASES:
                    effort_audits[phase] = reconcile_effort(ev, phase, observed_effort[phase], ep["phase_budgets"][phase]["physics_steps"],
                        phase_physics[phase], exceptions, checks, tid+"/effort/"+phase)
                checks.compare(ev["control_effort"], ev["phase_effort"]["control"], tid+"/control_effort_alias")
                measured = ev["phase_actual_effort_substeps"]["control"]
                checks.compare(ev["actual_control_effort_substeps"], measured, tid+"/measured_control")
                paid_control = ep["phase_budgets"]["control"]["physics_steps"]
                checks.compare(ev["missing_control_effort_substeps"], paid_control-measured, tid+"/collector_missing_actual")
                checks.compare(ev["actual_effort_complete"], measured == paid_control, tid+"/collector_actual_complete")
                checks.compare(ev["actual_effort_is_lower_bound"], measured < paid_control, tid+"/collector_actual_lower_bound")
                checks.check(not ep.get("risk_telemetry_complete", False) or missing_physics == 0, "risk_completeness_not_overclaimed", tid)
                attempts, failed_attempts, decisions = (ev[k] for k in ("planner_attempt_count", "failed_planner_attempts", "planner_decision_count"))
                checks.check(all(type(x) is int and x >= 0 for x in (attempts, failed_attempts, decisions))
                    and failed_attempts <= attempts <= (200 if kind in CONTROL_KINDS else 0), "planner_attempt_cap", tid)
                checks.compare(decisions, attempts-failed_attempts, tid+"/planner_decisions")
                checks.compare(ev["mathematical_prediction_calls_complete"], failed_attempts == 0, tid+"/mathcall_complete")
                checks.compare(ev["mathematical_prediction_calls_is_lower_bound"], failed_attempts > 0, tid+"/mathcall_lower_bound")
                checks.check(decisions >= len(tracking) and planner_calls <= ev["mathematical_prediction_calls"] <= 135*decisions,
                             "paid_planner_cost_retained", tid)
                checks.check(finite(ev["controller_seconds_total"]) and ev["controller_seconds_total"] >= 0, "nonnegative_planning_time", tid)
                if complete:
                    checks.compare(ev["mathematical_prediction_calls"], planner_calls, tid+"/mathcalls")
                    checks.compare(ev["planner_fallbacks"], fallbacks, tid+"/fallbacks")
                    checks.compare(decisions, 200 if kind in CONTROL_KINDS else 0, tid+"/decision_count")
                checks.compare(ev["models_before"], None if is_cal else before_hashes, tid+"/model_hashes_before")
                checks.compare(ev["models_after"], hashes, tid+"/model_hashes_after")
                checks.compare(ev["integration_models_before"], before_views, tid+"/view_hashes_before")
                checks.compare(ev["integration_models_after"], view_hashes, tid+"/view_hashes_after")
                if kind in CONTROL_KINDS and ev["planner_spec"] is not None:
                    fingerprint = hashes["nominal" if kind == "nominal_mpc" else kind.removesuffix("_mpc")]
                    checks.compare(ev["planner_spec"], {"config": MPC_CONFIG, "qref_rad": qref, "joint_range_rad": ranges[0],
                        "candidates_nm": [-.5+i*.125 for i in range(9)], "physical_queries": 0,
                        "forecast_bounds_rad": [max(qref-.15, ranges[0][0]-.03), min(qref+.15, ranges[0][1]+.03)],
                        "target_bounds_rad": [max(qref-.15, ranges[0][0]+.03), min(qref+.15, ranges[0][1]-.03)],
                        "integration": integration_spec(fingerprint), "integration_fingerprint": digest(integration_spec(fingerprint))}, tid+"/fixed_planner_spec")
            control_effort = effort_audits.get("control", {"independent_effort": new_effort(), "actual_effort_reconstruction_complete": False})
            derived[kind] = {"completed": complete, "eligible": complete and checks.failed == failure_start, "status": ep["status"],
                "tracking_rmse_rad": rmse(tracking), "velocity_prediction_rmse": {n: rmse(v) for n, v in scores_v.items()},
                "position_prediction_rmse": {n: rmse(v) for n, v in scores_q.items()}, "phase_effort": effort_audits,
                "control_effort": control_effort["independent_effort"], "actual_effort_complete": control_effort["actual_effort_reconstruction_complete"],
                "metric_reconstruction_complete": missing_rows == 0 and missing_physics == 0,
                "unreconstructed_transition_rows": missing_rows, "full_risk": risk_full, "phase_risk": phase_risk,
                "control_risk": phase_risk["control"], "missing_risk_substeps": missing_physics,
                "risk_telemetry_complete": missing_physics == 0 and ep.get("risk_telemetry_complete", False),
                "phase_risk_missing_substeps": {p: ep["phase_budgets"][p]["physics_steps"]-phase_physics[p] for p in PHASES},
                "risk_value_semantics": "When raw substeps are missing, saved peaks, impulse, penetration and screening counts are lower bounds; minimum contact distance is an upper bound. Native speed/limit values use endpoints only. Screening counts measure request/applied mismatches, not unobservable zero-request shield flags.",
                "saturated_control_steps": saturated, "planner_fallbacks": 0 if ev is None else ev.get("planner_fallbacks", 0),
                "mathematical_prediction_calls": 0 if ev is None else ev.get("mathematical_prediction_calls", 0),
                "independently_replayed_mathematical_prediction_calls": planner_calls,
                "planner_cost_reconstruction_complete": bool(ev) and ev.get("failed_planner_attempts") == 0 and ev.get("planner_decision_count") == len(tracking),
                "failed_planner_attempts": 0 if ev is None else ev.get("failed_planner_attempts", 0),
                "controller_seconds_total": None if ev is None else ev.get("controller_seconds_total"),
                "collector_reported_metrics": None if ev is None else {k: ev.get(k) for k in ("tracking_rmse_rad", "metric_control_step_count", "velocity_prediction_rmse", "position_prediction_rmse")},
                "returned_physics_steps": counters["physics"], "paid_budget": {k: ep[k] for k in ("control_calls_attempted", "control_steps", "physics_steps")}}
        if "nominal" in hashes:
            nominal = initial_state("linear4")
            checks.compare(sr["nominal_model"], {**model_record(qref, nominal["theta"], nominal["covariance"]),
                "parameter_fingerprint": hashes["nominal"], "update_count": 0, "trainable": False}, f"seed{seed}/nominal_independent_prior")
        checks.check(set(sr["integration_models"]) == set(view_hashes) if "integration_models" in sr else not view_hashes,
                     "exact_available_view_set", seed)
        for name, fingerprint in view_hashes.items():
            saved = sr["integration_models"][name]
            base = sr["nominal_model"] if name == "nominal_mpc" else sr["learned_models"][name.removesuffix("_mpc")]
            checks.compare(saved, {**base, "integration": integration_spec(base["parameter_fingerprint"]),
                "integration_fingerprint": fingerprint, "frozen_view": True}, f"seed{seed}/frozen_view/"+name)
        for kind in KINDS:
            regular = [r for r in grouped.get(f"seed{seed}_{kind}", []) if "collector_exception" not in r]
            derived[kind]["conditional_metrics"] = conditional_metrics(regular)
            if qref is not None:
                diagnostic_models = {n+"_mpc": s["coefficients"] for n, s in sr["learned_models"].items()}
                diagnostic_models["nominal_mpc"] = INITIAL["linear4"]
                derived[kind]["free_rollouts"] = diagnose_windows(regular, duration(kind), qref, diagnostic_models)
                derived[kind]["final_model_calibration_in_sample"] = kind.startswith("calibration_")
                derived[kind]["rollout_model_in_sample_on_this_calibration"] = {
                    n: kind == "calibration_"+n.split("_")[0] for n in diagnostic_models}
                if kind in CONTROL_KINDS and kind != "nominal_mpc":
                    cal = [r for r in grouped.get(f"seed{seed}_calibration_"+kind.split("_")[0], []) if "collector_exception" not in r]
                    derived[kind]["state_coverage"] = state_coverage(cal, regular, qref)
        old_rows = [r for r in grouped.get(f"seed{seed}_calibration_old", []) if "collector_exception" not in r and r["step_index"] < 190]
        new_rows = [r for r in grouped.get(f"seed{seed}_calibration_new", []) if "collector_exception" not in r and r["step_index"] < 190]
        paired = len(old_rows) == len(new_rows) == 190 and [trace_payload(r) for r in old_rows] == [trace_payload(r) for r in new_rows]
        checks.check(paired or not (calibration_complete["old"] and calibration_complete["new"]), "paired_prefix_plus_first90_calibration", seed)
        replayed = sum(s["updates"] for s in states.values())
        saved_total = sum(s["update_count"] for s in sr["learned_models"].values())
        checks.check(set(sr["learned_models"]) == set(states) and set(sr["initial_models"]) == set(states), "exact_created_model_set", seed)
        checks.compare(sr["calibration_updates"], saved_total, f"seed{seed}/saved_update_cost")
        checks.check(replayed <= saved_total <= 1200, "independent_update_cost_bounds", seed)
        derived_seeds.append({"seed": seed, "complete": all(v["eligible"] for v in derived.values()),
            "model_updates": saved_total, "independently_replayed_updates": replayed,
            "exception_snapshot_replayed_updates": sum(s["exception_replayed_updates"] for s in states.values()),
            "unreconstructed_updates": saved_total-replayed, "paired_prefix_first90": paired,
            "models": {n: {"reported_updates": sr["learned_models"][n]["update_count"], "replayed_updates": s["updates"],
                "exception_replayed_updates": s["exception_replayed_updates"], "unreconstructed_updates": s["unreconstructed_updates"]} for n, s in states.items()},
            "evaluations": derived})
    for key in ("control_calls_attempted", "control_steps", "physics_steps"):
        checks.compare(metadata[key], sum(ep[key] for ep in episodes), "metadata_"+key)
    checks.check(metadata["control_calls_attempted"] <= 8100 and metadata["control_steps"] <= 8100
        and metadata["physics_steps"] <= 81000 and metadata["model_updates"] <= 3600, "frozen_batch_budget_cap")
    checks.compare(metadata["model_updates"], sum(sr["calibration_updates"] for sr in results), "metadata_update_budget")
    for status in ("completed", "terminated", "exception", "blocked", "planned"):
        key = "unprocessed_trials" if status == "planned" else status+"_trials"
        checks.compare(metadata[key], sum(ep["status"] == status for ep in episodes), "metadata_"+key)
    checks.compare(metadata["all_trials_successful"], all(ep["status"] == "completed" for ep in episodes), "all_outcomes_success")
    checks.compare(metadata["failed_trials"], metadata["exception_trials"]+metadata["terminated_trials"], "all_failed_outcomes")
    checks.compare(metadata["skipped_trials"], metadata["blocked_trials"], "all_blocked_outcomes")
    checks.compare(metadata["complete"], metadata["archive_status"] == "complete", "archive_completion_not_adoption")
    checks.check(all(file_hash(path/name) == expected for name, expected in input_hashes.items()), "input_archive_unchanged")
    return {"path": str(path), "source_commit": metadata["source_commit"], "split": "development", "input_hashes": input_hashes,
        "seeds": derived_seeds, "budget": {k: metadata[k] for k in ("control_calls_attempted", "control_steps", "physics_steps", "model_updates")},
        "phase_budget": {p: {k: sum(e["phase_budgets"][p][k] for e in episodes) for k in ("control_calls_attempted", "control_steps", "physics_steps")} for p in PHASES},
        "physical_calibration_transfers": sum(e["phase_budgets"]["calibration"]["control_steps"] for e in episodes),
        "sample_semantics": "Shared native transfers give two independent parameter updates; 3600 updates are not 3600 independent physical samples."}, grouped, metadata


def historical_anchor(path, grouped, metadata, checks, git_root):
    if path is None:
        return {"provided": False, "exact_replay_verified": False}
    path = Path(path).resolve()
    old = require_development(path)
    old_protocol = old["protocol"]["path"]
    is_a = old_protocol == "docs/LOCAL_INTEGRATION_ABLATION_PROTOCOL.md"
    is_e1 = old_protocol == "docs/LOCAL_BODY_LEARNING_V2_PROTOCOL.md" and old.get("variant") == "hinge"
    if not is_a and not is_e1:
        raise ValueError("Reference must be C2-A or E1-v2 development archive.")
    checks.compare(old["environment_config"], metadata["environment_config"], "historical/environment")
    _, hashes = verify_sources(path, old, checks, git_root, {ASSET, old_protocol, "src/developmental_physics/local_model.py"})
    checks.compare(old["protocol"]["sha256"], old["source_sha256"][old_protocol], "historical/protocol_hash")
    for name in (ASSET, "src/developmental_physics/environment.py", "src/developmental_physics/local_model.py", "src/developmental_physics/probes.py"):
        checks.check(old["source_sha256"].get(name) == metadata["source_sha256"].get(name), "historical_unchanged_core", name)
    pairs = {"calibration": "calibration_old", "prediction": "prediction_low",
             ("frozen_euler_mpc" if is_a else "frozen_mpc"): "nominal_mpc",
             ("learned_euler_mpc" if is_a else "learned_mpc"): "old_hinge5_mpc"}
    previous = {(seed, kind): hashlib.sha256() for seed in SEEDS for kind in pairs}
    lengths = Counter()
    with gzip.open(path/"trace.jsonl.gz", "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            key = (row.get("seed"), row.get("kind"))
            if key not in previous:
                continue
            if "collector_exception" in row:
                raise ValueError("Historical anchor contains exception.")
            checks.compare(row["step_index"], lengths[key], "historical/control_index")
            previous[key].update(json.dumps(trace_payload(row), sort_keys=True, separators=(",", ":"), allow_nan=False).encode()+b"\n")
            lengths[key] += 1
    reports = []
    for (seed, old_kind), hasher in previous.items():
        new_kind = pairs[old_kind]
        rows = [r for r in grouped.get(f"seed{seed}_{new_kind}", []) if "collector_exception" not in r]
        current = hashlib.sha256()
        for row in rows:
            current.update(json.dumps(trace_payload(row), sort_keys=True, separators=(",", ":"), allow_nan=False).encode()+b"\n")
        expected = 400 if old_kind == "calibration" else (200 if old_kind == "prediction" else 300)
        exact = len(rows) == lengths[(seed, old_kind)] == expected and current.digest() == hasher.digest()
        checks.check(exact or len(rows) < expected, "complete_historical_exact_replay", f"seed{seed}/{new_kind}")
        reports.append({"seed": seed, "historical_kind": old_kind, "new_kind": new_kind,
            "historical_rows": lengths[(seed, old_kind)], "new_rows": len(rows), "exact_replay": exact,
            "historical_trace_sha256": hasher.hexdigest(), "new_trace_sha256": current.hexdigest()})
    checks.check(all(file_hash(path/name) == expected for name, expected in hashes.items()), "historical_inputs_unchanged")
    return {"provided": True, "path": str(path), "input_hashes": hashes, "pairs": reports,
        "exact_replay_verified": all(r["exact_replay"] for r in reports), "extra_independent_samples": 0}


def factorial_effects(metrics):
    if set(metrics) != set(CANDIDATES) or not all(finite(v) for v in metrics.values()):
        raise ValueError("Complete finite 2x2 raw metric matrix required.")
    structure = {d: metrics[d+"_hinge5"]-metrics[d+"_linear4"] for d in ("old", "new")}
    dose = {s: metrics["new_"+s]-metrics["old_"+s] for s in STRUCTURES}
    return {"hinge_minus_linear": structure, "new_minus_old": dose,
            "difference_of_differences": dose["hinge5"]-dose["linear4"]}


def ratio_change(new, old):
    return (0. if new == 0. else None) if old == 0. else new/old-1.


def adoption_gate(seeds):
    """Frozen development choice; raw RMSE means, exact deterministic tie break."""
    unique = len(seeds) == 3 and {r["seed"] for r in seeds} == set(SEEDS)
    reports = []
    for candidate_id, candidate in enumerate(CANDIDATES):
        pairs = []
        for row in seeds:
            ev = row["evaluations"]
            base, other = ev.get(ANCHOR+"_mpc", {}), ev.get(candidate+"_mpc", {})
            valid = (base.get("eligible") is True and other.get("eligible") is True
                and base.get("actual_effort_complete") is True and other.get("actual_effort_complete") is True
                and all(finite(g.get("tracking_rmse_rad")) and g["tracking_rmse_rad"] >= 0
                    and all(finite(g.get("control_effort", {}).get(k)) and g["control_effort"][k] >= 0 for k in EFFORT_KEYS[2:])
                    for g in (base, other)))
            prediction_gates = {}
            for kind in ("prediction_low", "prediction_full"):
                trial = ev.get(kind, {})
                metrics = trial.get("velocity_prediction_rmse", {})
                a, b = metrics.get(ANCHOR+"_mpc"), metrics.get(candidate+"_mpc")
                available = trial.get("eligible") is True and finite(a) and finite(b) and a >= 0 and b >= 0
                prediction_gates[kind] = {"complete": available, "anchor_rmse": a, "candidate_rmse": b,
                                          "passed": available and b <= a}
                valid = valid and available
            pairs.append({"seed": row["seed"], "complete_pair": valid,
                "tracking_non_worse": valid and other["tracking_rmse_rad"] <= base["tracking_rmse_rad"],
                "anchor_tracking_rmse_rad": base.get("tracking_rmse_rad"), "candidate_tracking_rmse_rad": other.get("tracking_rmse_rad"),
                "prediction_gates": prediction_gates, "anchor_actual_effort": base.get("control_effort"),
                "candidate_actual_effort": other.get("control_effort")})
        valid = unique and all(p["complete_pair"] for p in pairs)
        am = sum(p["anchor_tracking_rmse_rad"] for p in pairs)/3 if valid else None
        cm = sum(p["candidate_tracking_rmse_rad"] for p in pairs)/3 if valid else None
        improvement = 1.-cm/am if valid and am > 0 else None
        efforts = {}
        for key in EFFORT_KEYS[2:]:
            a = sum(p["anchor_actual_effort"][key] for p in pairs)/3 if valid else None
            b = sum(p["candidate_actual_effort"][key] for p in pairs)/3 if valid else None
            efforts[key] = {"anchor_mean": a, "candidate_mean": b,
                "relative_increase": ratio_change(b, a) if valid else None, "passed": valid and b <= 1.05*a}
        passed = (candidate != ANCHOR and valid and all(p["tracking_non_worse"] for p in pairs)
            and all(g["passed"] for p in pairs for g in p["prediction_gates"].values())
            and improvement is not None and improvement >= .05 and all(g["passed"] for g in efforts.values()))
        reports.append({"candidate_id": candidate_id, "candidate": candidate, "dimension": 4 if "linear4" in candidate else 5,
            "evaluated": valid, "passed": passed, "per_seed": pairs, "anchor_raw_tracking_mean": am,
            "candidate_raw_tracking_mean": cm, "tracking_mean_improvement": improvement, "actual_effort_gates": efforts})
    winners = [r for r in reports if r["passed"]]
    winner = min(winners, key=lambda r: (r["candidate_raw_tracking_mean"],
        r["actual_effort_gates"]["actual_squared_nm2_s"]["candidate_mean"], r["dimension"], r["candidate_id"])) if winners else None
    return {"anchor": ANCHOR, "candidate_order": list(CANDIDATES), "candidates": reports,
        "passed": winner is not None, "selected_candidate": ANCHOR if winner is None else winner["candidate"],
        "tie_break": "exact raw tracking mean, actual square effort mean, dimension, candidate id",
        "claim_boundary": "Development default only. No unseen method advantage, safety, or whole-body skill claim."}


def numeric_leaves(value, prefix=""):
    if isinstance(value, dict):
        for key, item in value.items():
            yield from numeric_leaves(item, prefix+"/"+key)
    elif isinstance(value, list):
        for i, item in enumerate(value):
            yield from numeric_leaves(item, prefix+"/"+str(i))
    elif finite(value):
        yield prefix, value


def seed_factorial_metrics(row):
    ev, matrices = row["evaluations"], {}
    if not all(ev.get(c+"_mpc", {}).get("eligible") is True for c in CANDIDATES):
        return matrices
    for candidate in CANDIDATES:
        trial = ev[candidate+"_mpc"]
        values = {"tracking_rmse_rad": trial["tracking_rmse_rad"], **trial["control_effort"],
            "own_velocity_prediction_rmse": trial["velocity_prediction_rmse"].get(candidate+"_mpc"),
            "own_position_prediction_rmse": trial["position_prediction_rmse"].get(candidate+"_mpc"),
            "saturated_control_steps": trial["saturated_control_steps"], "planner_fallbacks": trial["planner_fallbacks"],
            "full_risk": trial["full_risk"], "phase_risk": trial["phase_risk"]}
        for prediction_kind in ("prediction_low", "prediction_full"):
            prediction = ev.get(prediction_kind, {})
            if prediction.get("eligible"):
                values[prediction_kind] = {"q_rmse_rad": prediction["position_prediction_rmse"].get(candidate+"_mpc"),
                                           "v_rmse_rad_s": prediction["velocity_prediction_rmse"].get(candidate+"_mpc")}
        for label, value in numeric_leaves(values):
            matrices.setdefault(label.lstrip("/"), {})[candidate] = value
    return {label: matrix for label, matrix in matrices.items() if set(matrix) == set(CANDIDATES)}


def aggregate_factorial(seeds):
    matrices = {row["seed"]: seed_factorial_metrics(row) for row in seeds}
    unique = len(seeds) == 3 and set(matrices) == set(SEEDS)
    common = set.intersection(*(set(m) for m in matrices.values())) if unique else set()
    summaries = {}
    for label in sorted(common):
        means = {c: sum(matrices[s][label][c] for s in SEEDS)/3 for c in CANDIDATES}
        summaries[label] = {"per_seed_raw_values": {str(s): matrices[s][label] for s in SEEDS},
            "per_seed_effects": {str(s): factorial_effects(matrices[s][label]) for s in SEEDS},
            "raw_three_seed_means": means, "raw_mean_factorial_effects": factorial_effects(means)}
    return {"complete_four_group_three_seed_matrix": unique and bool(common), "metrics": summaries,
        "semantics": "Raw per-seed arithmetic means; no pooled independent samples, mean percentages or significance. Shared-prediction inputs are paired; control trajectories differ."}


def audit(path, *, reference=None, git_root=ROOT):
    wall_start, cpu_start = time.perf_counter(), time.process_time()
    checks, result, reported_budget = Checks(), None, None
    anchor = {"provided": reference is not None, "exact_replay_verified": False}
    try:
        # Both metadata gates precede source or trace reads.
        initial_metadata = require_development(path)
        if reference is not None:
            require_development(reference)
        reported_budget = {k: initial_metadata.get(k) for k in ("control_calls_attempted", "control_steps", "physics_steps", "model_updates")}
        result, grouped, metadata = audit_archive(path, checks, git_root)
        anchor = historical_anchor(reference, grouped, metadata, checks, git_root)
    except (OSError, ValueError, KeyError, TypeError, IndexError, AttributeError, OverflowError, zipfile.BadZipFile) as error:
        checks.check(False, "archive_schema_or_read_error", {"type": type(error).__name__, "message": str(error)})
    gate = adoption_gate([] if result is None else result["seeds"])
    gate["data_consistency_verified"] = checks.failed == 0
    gate["historical_replay_verified"] = anchor["exact_replay_verified"]
    gate["validated_pass"] = gate["passed"] and checks.failed == 0 and anchor["exact_replay_verified"] and git_root is not None
    gate["validated_selected_candidate"] = gate["selected_candidate"] if gate["validated_pass"] else ANCHOR
    return {"schema_version": 1, "created_at_utc": datetime.now(timezone.utc).isoformat(), "purpose": __doc__,
        "audit_script_sha256": file_hash(Path(__file__)), "checks": checks.count, "failed": checks.failed,
        "maximum_recomputation_difference": checks.maximum_difference, "violations": checks.violations,
        "archive": result, "historical_anchor": anchor, "development_adoption_gate": gate,
        "reported_paid_budget_if_replay_incomplete": reported_budget,
        "reported_budget_semantics": "Collector paid counters stay visible on schema failure; archive.budget is independently checked when available.",
        "four_group_factorial_summary": aggregate_factorial([] if result is None else result["seeds"]),
        "rollout_semantics": "Recorded future requests are offline conditional inputs. Initial native q/v only; future true states never fed back. Windows never cross reset, phase, missing, partial or stop. Full terminal endpoints are counted separately. Final-model calibration is in-sample, overlapping windows are not independent samples.",
        "execution": {"wall_seconds": time.perf_counter()-wall_start, "cpu_seconds": time.process_time()-cpu_start,
            "timing_scope": "audit entry through report assembly; excludes import and final JSON writing",
            "python": sys.version, "platform": platform.platform(), "third_party_dependencies": [],
            "source_git_verification_enabled": git_root is not None,
            "physical_simulation_calls": 0, "model_parameter_updates": 0, "replayed_updates_are_frozen_log_audits": True}}


def validate_output_path(output, inputs):
    output = Path(output).resolve()
    if output.exists():
        raise ValueError("Refusing to overwrite existing audit output.")
    if any(output.is_relative_to(Path(p).resolve()) for p in inputs if p is not None):
        raise ValueError("Audit output must be outside every input archive and reference.")
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--reference", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        output = validate_output_path(args.output, [args.archive, args.reference])
        require_development(args.archive)
        if args.reference is not None:
            require_development(args.reference)
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.error(str(error))
    report = audit(args.archive, reference=args.reference)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"report": str(output), "checks": report["checks"], "failed": report["failed"],
                      "selected": report["development_adoption_gate"]["validated_selected_candidate"]}))
    return 1 if report["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
