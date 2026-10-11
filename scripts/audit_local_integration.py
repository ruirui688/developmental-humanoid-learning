"""Independent C2-A arithmetic; standard library, no simulator or fitting imports.

Replays recorded RLS, both integrators and MPC without importing experiment
code. Only development inputs are accepted. Data integrity, historical exact
replay and the predeclared development adoption gate are separate results.
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

DT = .02
HORIZONS = (1, 5, 15, 50)
INITIAL = [1., 0., .02, 0., 0.]
INTEGRATIONS = ("endpoint_euler", "trapezoid")


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def feature_vector(qref, q, v, torque):
    if not all(finite(value) for value in (qref, q, v, torque)):
        raise ValueError("Native states, reference and request must be finite.")
    sign = 1. if torque > 0 else (-1. if torque < 0 else 0.)
    return [v, q-qref, torque, sign*max(abs(torque)-.25, 0.), 1.]


def predict(theta, qref, q, v, torque, integration):
    if integration not in INTEGRATIONS:
        raise ValueError("Unknown frozen integration rule.")
    if len(theta) != 5 or not all(finite(value) for value in theta):
        raise ValueError("Five finite endpoint-velocity coefficients required.")
    features = feature_vector(qref, q, v, torque)
    next_v = sum(a*b for a, b in zip(theta, features))
    next_q = q + DT*(next_v if integration == "endpoint_euler" else .5*(v+next_v))
    if not finite(next_q) or not finite(next_v):
        raise ValueError("Prediction became nonfinite.")
    return next_q, next_v


def replay_rls(theta, covariance, features, native_next_v):
    """One logged no-forgetting, symmetrized five-dimensional RLS update."""
    if (len(theta) != 5 or len(features) != 5 or len(covariance) != 5
            or any(len(row) != 5 for row in covariance)
            or not all(finite(x) for x in theta+features+[native_next_v])
            or not all(finite(x) for row in covariance for x in row)):
        raise ValueError("Malformed RLS record.")
    projected = [sum(covariance[i][j]*features[j] for j in range(5)) for i in range(5)]
    denominator = 1. + sum(features[i]*projected[i] for i in range(5))
    if not finite(denominator) or denominator <= 0:
        raise ValueError("Invalid RLS denominator.")
    gain = [value/denominator for value in projected]
    residual = native_next_v - sum(theta[i]*features[i] for i in range(5))
    new_theta = [theta[i]+gain[i]*residual for i in range(5)]
    matrix = [[covariance[i][j]-gain[i]*projected[j] for j in range(5)] for i in range(5)]
    new_covariance = [[.5*(matrix[i][j]+matrix[j][i]) for j in range(5)] for i in range(5)]
    if not all(finite(x) for x in new_theta+[x for row in new_covariance for x in row]):
        raise ValueError("RLS replay became nonfinite.")
    return new_theta, new_covariance


def replay_mpc(theta, qref, q, v, target, previous, limits, integration):
    """Independent nine-candidate, fifteen-step constant-request planner."""
    if not all(finite(x) for x in [target, previous, *limits]):
        raise ValueError("Planner's public target, previous command and limits must be finite.")
    lower, upper = max(qref-.15, limits[0]-.03), min(qref+.15, limits[1]+.03)
    feasible, calls = [], 0
    for index in range(9):
        torque = -.5 + index*.125
        pq, pv = q, v
        qs, vs = [], []
        cost = .00002*(torque-previous)**2
        for _ in range(15):
            calls += 1
            try:
                pq, pv = predict(theta, qref, pq, pv, torque, integration)
            except (ValueError, OverflowError):
                break
            if not lower <= pq <= upper or abs(pv) > 1.5:
                break
            qs.append(pq)
            vs.append(pv)
            cost += (pq-target)**2 + .002*pv*pv + .00002*torque*torque
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


def free_rollout(theta, qref, q, v, recorded_requests, integration="endpoint_euler"):
    """Initial native q/v only; future requests condition this offline diagnosis."""
    path = []
    for torque in recorded_requests:
        if theta is None:
            q += DT*v  # Independent constant-velocity persistence baseline.
        else:
            q, v = predict(theta, qref, q, v, torque, integration)
        path.append((q, v))
    return path


def valid_window(indexed, start, horizon, joint=0):
    """Do not advance past a stop; a final full terminal interval is allowed.

    Phases, missing intervals and partial physical intervals cannot be crossed.
    A complete 20 ms terminal transition is a physical endpoint, not success.
    """
    segment = []
    for index in range(start, start+horizon):
        row = indexed.get(index)
        if row is None:
            return None, "missing_control_row"
        if "collector_exception" in row:
            return None, "collector_exception"
        before, after = row["observation_before"], row["observation_after"]
        if not all(finite(observation[key][joint]) for observation in (before, after)
                   for key in ("joint_position", "joint_velocity")):
            return None, "invalid_native_state"
        if not finite(row["requested_torque"][joint]):
            return None, "invalid_request"
        diagnostic = row["diagnostics"]
        if diagnostic["executed_substeps"] != 10:
            return None, "partial_physics_interval"
        if segment:
            previous = segment[-1]
            if previous["phase"] != row["phase"]:
                return None, "crossed_phase_boundary"
            if previous["diagnostics"]["terminated"]:
                return None, "continued_after_termination"
            if previous["observation_after"] != before:
                return None, "native_state_discontinuity"
            if abs(diagnostic["time"]-previous["diagnostics"]["time"]-DT) > 1e-10:
                return None, "time_discontinuity"
        segment.append(row)
    return segment, None


def window_denominators(indexed, planned_active_steps, horizon, joint=0, prefix=100):
    expected = max(planned_active_steps-horizon+1, 0)
    excluded = Counter()
    valid = ending_in_termination = 0
    for start in range(prefix, prefix+expected):
        segment, reason = valid_window(indexed, start, horizon, joint)
        if reason:
            excluded[reason] += 1
        else:
            valid += 1
            ending_in_termination += int(segment[-1]["diagnostics"]["terminated"])
    return {"expected_windows_from_planned_active_duration": expected,
            "valid_physical_windows": valid, "excluded_windows": expected-valid,
            "valid_windows_ending_in_termination": ending_in_termination,
            "exclusion_reasons": dict(excluded)}


def factorial_effects(metrics):
    """Signed differences of raw per-seed RMSE; negative means improvement.

    No statistical significance or causal extrapolation is assigned here.
    Never pool different trajectories as if they were independent seed counts.
    """
    expected = {(model, rule) for model in ("nominal", "learned") for rule in INTEGRATIONS}
    if set(metrics) != expected or not all(finite(value) for value in metrics.values()):
        raise ValueError("Complete finite two-by-two metric matrix required.")
    model_effect = {rule: metrics[("learned", rule)]-metrics[("nominal", rule)] for rule in INTEGRATIONS}
    integration_effect = {model: metrics[(model, "trapezoid")]-metrics[(model, "endpoint_euler")]
                          for model in ("nominal", "learned")}
    return {"learned_minus_nominal": model_effect,
            "trapezoid_minus_endpoint": integration_effect,
            "difference_of_differences": model_effect["trapezoid"]-model_effect["endpoint_euler"]}


ROOT = Path(__file__).resolve().parents[1]
SEEDS = [0, 1, 2]
KINDS = ("calibration", "prediction", "frozen_euler_mpc", "learned_euler_mpc",
         "frozen_trapezoid_mpc", "learned_trapezoid_mpc")
CONTROL_KINDS = KINDS[2:]
CALIBRATION_AMPLITUDES = [.125, .25, .5, .125, .25, .5, .125, .25, .5, .125]
JOINTS = ("left_shoulder", "left_elbow", "right_shoulder", "right_elbow",
          "left_hip", "left_knee", "right_hip", "right_knee")
NATIVE = {"joint_position": 8, "joint_velocity": 8, "imu_gyro": 3,
          "imu_acceleration": 3, "actuator_torque": 8, "previous_command": 8}
MODEL_FIELDS = ("qref_rad", "dt_seconds", "features", "initial_coefficients",
                "initial_covariance_scale", "forgetting_factor", "coefficients",
                "covariance", "dtype", "hinge_threshold_nm", "hinge_threshold_updates",
                "hinge_structure_prior")
ENVIRONMENT = {"physics_dt": .002, "control_substeps": 10, "torque_limit": .5,
               "joint_speed_limit": 20., "joint_limit_margin": .08,
               "kinetic_energy_limit": 50., "reset_clearance": .005,
               "ground_contact_profile": "baseline"}
MPC_CONFIG = {"horizon": 15, "candidate_count": 9, "torque_limit_nm": .5,
              "position_weight": 1., "velocity_weight": .002, "effort_weight": .00002,
              "change_weight": .00002, "local_position_radius_rad": .15,
              "prediction_limit_tolerance_rad": .03, "target_limit_margin_rad": .03,
              "velocity_limit_rad_s": 1.5}
PROTOCOL = "docs/LOCAL_INTEGRATION_ABLATION_PROTOCOL.md"
ASSET = "src/developmental_physics/assets/ground_body.xml"
REQUIRED_SOURCES = {PROTOCOL, ASSET, "pyproject.toml"} | {
    "src/developmental_physics/"+name for name in
    ("__init__.py", "environment.py", "collect.py", "probes.py", "local_model.py",
     "local_integration.py", "local_ablation.py")}


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
    return {"qref_rad": qref, "dt_seconds": .02,
            "features": ["v", "q-qref", "requested_torque", "sign(u)*max(abs(u)-0.25,0)", "1"],
            "initial_coefficients": INITIAL, "initial_covariance_scale": 100.,
            "forgetting_factor": 1., "coefficients": theta, "covariance": covariance,
            "dtype": "float64", "hinge_threshold_nm": .25, "hinge_threshold_updates": 0,
            "hinge_structure_prior": "fixed signed torque hinge; structural prior, not a learned threshold or physics label"}


def integration_spec(mode, fingerprint):
    return {"mode": mode, "dt_seconds": .02,
            "rule": "q + dt * predicted_next_v" if mode == "endpoint_euler" else "q + dt * (current_v + predicted_next_v) / 2",
            "endpoint_velocity_rule_unchanged": True, "dynamics_parameter_fingerprint": fingerprint}


def scope(kind):
    return "frozen" if kind.startswith("frozen") else ("learned" if kind.startswith("learned") else "shared")


def mode(kind):
    return "trapezoid" if "trapezoid" in kind else ("endpoint_euler" if "euler" in kind else None)


def planned_matrix():
    return [{"trial_id": f"seed{seed}_{kind}", "seed": seed, "kind": kind,
             "model_scope": scope(kind), "integration": mode(kind),
             "maximum_control_steps": 400 if kind == "calibration" else (200 if kind == "prediction" else 300)}
            for seed in SEEDS for kind in KINDS]


def require_development(path):
    metadata = load_json(Path(path)/"metadata.json")
    if (metadata.get("split") != "development" or metadata.get("seeds") != SEEDS
            or metadata.get("pose") != "supine" or metadata.get("joint_index") != 0):
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
    checks.check(metadata.get("source_status") == "" and metadata.get("source_dirty") is False,
                 "clean_collection_source", str(path))
    hashes = metadata["source_sha256"]
    checks.check(required.issubset(hashes), "required_source_coverage", str(path))
    with zipfile.ZipFile(path/"source_snapshot.zip") as archive:
        checks.check(len(archive.namelist()) == len(set(archive.namelist())) and set(archive.namelist()) == set(hashes),
                     "source_zip_exact_unique_coverage", str(path))
        for name, expected in hashes.items():
            blob = archive.read(name)
            checks.check(hashlib.sha256(blob).hexdigest() == expected, "source_zip_hash", name)
            if git_root is not None and valid_commit:
                result = subprocess.run(["git", "show", f"{commit}:{name}"], cwd=git_root,
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
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


def diagnose_windows(rows, planned_steps, qref, final_theta):
    indexed = {row["step_index"]: row for row in rows if "collector_exception" not in row}
    reports = []
    predictors = {kind: (INITIAL if scope(kind) == "frozen" else final_theta, mode(kind)) for kind in CONTROL_KINDS}
    predictors["velocity_persistence"] = (None, "endpoint_euler")
    for horizon in HORIZONS:
        denominator = window_denominators(indexed, planned_steps-100, horizon)
        errors = {name: {"q": [], "v": [], "path_q": [], "path_v": [], "invalid": 0} for name in predictors}
        for start in range(100, planned_steps-horizon+1):
            segment, reason = valid_window(indexed, start, horizon)
            if reason:
                continue
            first = segment[0]["observation_before"]
            q, v = first["joint_position"][0], first["joint_velocity"][0]
            requests = [row["requested_torque"][0] for row in segment]
            truth = [(row["observation_after"]["joint_position"][0], row["observation_after"]["joint_velocity"][0]) for row in segment]
            for name, (theta, integration) in predictors.items():
                values = errors[name]
                try:
                    predicted = free_rollout(theta, qref, q, v, requests, integration)
                    qe, ve = predicted[-1][0]-truth[-1][0], predicted[-1][1]-truth[-1][1]
                    if not finite(qe) or not finite(ve):
                        raise ValueError("Invalid error.")
                    values["q"].append(qe)
                    values["v"].append(ve)
                    values["path_q"].extend(p[0]-t[0] for p, t in zip(predicted, truth))
                    values["path_v"].extend(p[1]-t[1] for p, t in zip(predicted, truth))
                except (ValueError, OverflowError):
                    values["invalid"] += 1
        reports.append({"horizon_control_steps": horizon, **denominator,
                        "predictors": {name: {"valid_prediction_windows": len(e["q"]),
                            "invalid_prediction_windows": e["invalid"], "path_endpoint_samples": len(e["path_q"]),
                            "terminal_position_rmse_rad": rmse(e["q"]), "terminal_velocity_rmse_rad_s": rmse(e["v"]),
                            "path_position_rmse_rad": rmse(e["path_q"]), "path_velocity_rmse_rad_s": rmse(e["path_v"])}
                            for name, e in errors.items()}})
    return reports


def trace_payload(row):
    return {key: row[key] for key in ("phase", "target_q", "requested_torque", "observation_before",
                                     "observation_after", "qpos", "qvel", "diagnostics")}


def historical_anchor(path, grouped, metadata, checks, git_root):
    if path is None:
        return {"provided": False, "exact_replay_verified": False}
    path = Path(path).resolve()
    old = require_development(path)
    checks.compare(old.get("variant"), "hinge", "historical/v2_variant")
    checks.compare(old["environment_config"], metadata["environment_config"], "historical/environment")
    _, hashes = verify_sources(path, old, checks, git_root, {ASSET, "src/developmental_physics/local_model.py", "docs/LOCAL_BODY_LEARNING_V2_PROTOCOL.md"})
    for name in (ASSET, "src/developmental_physics/environment.py", "src/developmental_physics/local_model.py", "src/developmental_physics/probes.py"):
        checks.check(old["source_sha256"].get(name) == metadata["source_sha256"].get(name), "historical_unchanged_core_source", name)
    pairs = {"calibration": "calibration", "prediction": "prediction", "frozen_mpc": "frozen_euler_mpc", "learned_mpc": "learned_euler_mpc"}
    existing = {(seed, kind): hashlib.sha256() for seed in SEEDS for kind in pairs}
    lengths = Counter()
    with gzip.open(path/"trace.jsonl.gz", "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            key = (row.get("seed"), row.get("kind"))
            if key not in existing:
                continue
            if "collector_exception" in row:
                raise ValueError("Historical anchor contains an exception.")
            checks.compare(row["step_index"], lengths[key], "historical/control_index")
            existing[key].update(json.dumps(trace_payload(row), sort_keys=True, separators=(",", ":"), allow_nan=False).encode()+b"\n")
            lengths[key] += 1
    reports = []
    for (seed, old_kind), hasher in existing.items():
        new_kind = pairs[old_kind]
        rows = [r for r in grouped.get(f"seed{seed}_{new_kind}", []) if "collector_exception" not in r]
        current = hashlib.sha256()
        for row in rows:
            current.update(json.dumps(trace_payload(row), sort_keys=True, separators=(",", ":"), allow_nan=False).encode()+b"\n")
        expected = 400 if old_kind == "calibration" else (200 if old_kind == "prediction" else 300)
        exact = len(rows) == lengths[(seed, old_kind)] == expected and current.digest() == hasher.digest()
        # A real failed C2-A trajectory has a shorter legal prefix; it is not
        # silently promoted to an exact complete historical replay.
        checks.check(exact or len(rows) < expected, "complete_historical_trajectory_exact_replay", f"seed{seed}/{new_kind}")
        reports.append({"seed": seed, "historical_kind": old_kind, "new_kind": new_kind,
                        "historical_rows": lengths[(seed, old_kind)], "new_rows": len(rows), "exact_replay": exact,
                        "historical_trace_sha256": hasher.hexdigest(), "new_trace_sha256": current.hexdigest()})
    checks.check(all(file_hash(path/name) == expected for name, expected in hashes.items()), "historical_inputs_unchanged")
    return {"provided": True, "path": str(path), "input_hashes": hashes, "pairs": reports,
            "exact_replay_verified": all(r["exact_replay"] for r in reports), "extra_independent_samples": 0}


def new_risk():
    return {"ground_force_peak_n": 0., "kinetic_energy_peak_j": 0., "minimum_contact_distance_m": 0.,
            "native_joint_speed_peak_rad_s": 0., "guarded_substeps": 0, "target_guarded_substeps": 0,
            "soft_limit_excursion_peak_rad": 0., "physical_substeps": 0}


def record_risk(risk, row, ranges):
    diagnostic = row["diagnostics"]
    risk["ground_force_peak_n"] = max(risk["ground_force_peak_n"], *diagnostic["substep_ground_normal_forces"], 0.)
    risk["kinetic_energy_peak_j"] = max(risk["kinetic_energy_peak_j"], *diagnostic["substep_kinetic_energies"], 0.)
    risk["minimum_contact_distance_m"] = min(risk["minimum_contact_distance_m"], *diagnostic["substep_minimum_contact_distances"], 0.)
    risk["native_joint_speed_peak_rad_s"] = max(risk["native_joint_speed_peak_rad_s"], *(abs(v) for v in row["observation_after"]["joint_velocity"]))
    risk["guarded_substeps"] += diagnostic["guarded_substeps"]
    risk["target_guarded_substeps"] += sum(actual[0] != row["requested_torque"][0] for actual in diagnostic["applied_torque_history"])
    risk["physical_substeps"] += diagnostic["executed_substeps"]
    for q, (lower, upper) in zip(row["observation_after"]["joint_position"], ranges):
        risk["soft_limit_excursion_peak_rad"] = max(risk["soft_limit_excursion_peak_rad"], lower-q, q-upper)


def reconcile_effort(ev, observed, paid_substeps, observed_substeps, exceptions, checks, location):
    """Recover paid requests without inventing missing realized torque history.

    A post-return error can lose the regular row while unreturned_physics_steps
    is zero. The phase ledger, not that field, determines missing paid cost.
    Collector-reported actual effort remains unverified when raw history lacks
    those substeps, even if the collector measured it before a write failure.
    """
    missing = paid_substeps-observed_substeps
    known = dict(observed)
    commands = [row.get("requested_torque") for row in exceptions if row.get("phase") == "control"]
    recoverable = (missing == 0 or missing <= 10 and len(commands) == 1
                   and isinstance(commands[0], list) and len(commands[0]) == 8
                   and all(finite(u) and abs(u) <= .5 for u in commands[0]))
    if missing > 0 and recoverable:
        u = commands[0][0]
        known["requested_absolute_nm_s"] += abs(u)*missing*.002
        known["requested_squared_nm2_s"] += u*u*missing*.002
    recorded = ev["control_effort"]
    if recoverable:
        for key in ("requested_absolute_nm_s", "requested_squared_nm2_s"):
            checks.compare(recorded[key], known[key], location+"/"+key)
    measured = ev["actual_control_effort_substeps"]
    checks.check(type(measured) is int and observed_substeps <= measured <= paid_substeps,
                 "measured_actual_effort_substep_bounds", location)
    checks.compare(ev["missing_control_effort_substeps"], paid_substeps-measured, location+"/collector_missing_actual")
    checks.compare(ev["actual_effort_complete"], measured == paid_substeps, location+"/collector_actual_completeness")
    checks.compare(ev["actual_effort_is_lower_bound"], measured < paid_substeps, location+"/collector_actual_lower_bound")
    for key, maximum in (("actual_absolute_nm_s", .5), ("actual_squared_nm2_s", .25)):
        if missing == 0:
            checks.compare(recorded[key], known[key], location+"/"+key)
        else:
            value = recorded[key]
            # These bounds validate accounting consistency only. They never
            # certify the absent torque history or fill it with guessed values.
            checks.check(finite(value) and known[key]-1e-10 <= value <= known[key]+maximum*(measured-observed_substeps)*.002+1e-10,
                         "unreconstructed_actual_effort_within_permission_bounds", location+"/"+key)
    return {"independent_effort": known, "requested_effort_reconstruction_complete": recoverable,
            "actual_effort_reconstruction_complete": missing == 0,
            "unreconstructed_actual_effort_substeps": missing,
            "collector_reported_effort": recorded,
            "collector_reported_actual_measured_substeps": measured,
            "actual_effort_semantics": "exact raw-history reconstruction" if missing == 0 else "known-history lower bound; collector-reported remainder is not independently verified"}


def verify_budget_bounds(ep, checks, location):
    kind = ep["kind"]
    caps = {"prefix": 100, "calibration": 300 if kind == "calibration" else 0,
            "prediction": 100 if kind == "prediction" else 0,
            "control": 200 if kind in CONTROL_KINDS else 0}
    for phase, cap in caps.items():
        budget = ep["phase_budgets"][phase]
        checks.check(0 <= budget["control_calls_attempted"] <= cap
                     and 0 <= budget["control_steps"] <= cap and 0 <= budget["physics_steps"] <= cap*10,
                     "frozen_phase_budget_cap", location+"/"+phase)
    maximum = ep["maximum_control_steps"]
    checks.check(ep["control_calls_attempted"] <= maximum and ep["control_steps"] <= maximum
                 and ep["physics_steps"] <= maximum*10, "frozen_trial_budget_cap", location)


def audit_archive(path, checks, git_root=ROOT):
    path = Path(path).resolve()
    metadata = require_development(path)
    ranges, input_hashes = verify_sources(path, metadata, checks, git_root)
    checks.compare(metadata["protocol"]["path"], PROTOCOL, "frozen_protocol")
    checks.compare(metadata["protocol"]["sha256"], metadata["source_sha256"][PROTOCOL], "protocol_hash")
    checks.compare(metadata["environment_config"], ENVIRONMENT, "environment_and_permission")
    checks.compare(metadata["variant"], "hinge", "fixed_velocity_structure")
    checks.compare(metadata["integrations"], list(INTEGRATIONS), "frozen_integrators")
    checks.compare(metadata["calibration_block_amplitudes_nm"], CALIBRATION_AMPLITUDES, "unchanged_calibration")
    checks.compare({key: metadata[key] for key in ("gpu", "prefix_steps", "calibration_steps", "prediction_steps", "control_steps_per_trial", "teacher_calls", "external_demonstration_samples", "policy_parameter_updates")},
                   {"gpu": None, "prefix_steps": 100, "calibration_steps": 300, "prediction_steps": 100, "control_steps_per_trial": 200, "teacher_calls": 0, "external_demonstration_samples": 0, "policy_parameter_updates": 0}, "frozen_metadata")
    plans = planned_matrix()
    checks.compare(metadata["planned_episodes"], plans, "frozen_full_plan")
    checks.compare(metadata["planned_episode_count"], 18, "planned_trials")
    checks.compare(metadata["maximum_control_steps"], 5400, "planned_budget")
    episodes = load_json(path/"episodes.json")
    checks.compare([ep["trial_id"] for ep in episodes], [p["trial_id"] for p in plans], "complete_outcome_ledger")
    episode_map = {ep["trial_id"]: ep for ep in episodes}
    if len(episode_map) != len(episodes):
        raise ValueError("Duplicate episode IDs.")
    results = load_json(path/"seed_results.json")
    by_seed = {row["seed"]: row for row in results}
    checks.check(len(by_seed) == len(results) and set(by_seed).issubset(SEEDS), "unique_known_seed_snapshots")
    grouped = {}
    with gzip.open(path/"trace.jsonl.gz", "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            checks.check(row.get("trial_id") in episode_map, "known_trace_trial", row.get("trial_id"))
            grouped.setdefault(row["trial_id"], []).append(row)
    derived_seeds = []
    for seed in SEEDS:
        sr = by_seed.get(seed)
        if sr is None:
            checks.check(all(episode_map[f"seed{seed}_{kind}"]["status"] == "blocked" for kind in KINDS), "unstarted_seed_all_blocked", seed)
            derived_seeds.append({"seed": seed, "complete": False, "evaluations": {}})
            continue
        checks.check(type(sr["calibration_updates"]) is int and 0 <= sr["calibration_updates"] <= 300,
                     "frozen_seed_update_cap", seed)
        qref = sr.get("reference_q")
        theta, covariance = INITIAL.copy(), [[100. if i == j else 0. for j in range(5)] for i in range(5)]
        observed_theta, observed_covariance = theta.copy(), [r.copy() for r in covariance]
        observed_hash = None if qref is None else digest(model_record(qref, observed_theta, observed_covariance))
        initial_hash = observed_hash
        updates = 0
        view_hashes = {}
        if qref is not None:
            checks.compare(sr["initial_model"], {**model_record(qref, theta, covariance), "trainable": False, "update_count": 0,
                                                "parameter_fingerprint": initial_hash}, f"seed{seed}/nominal_initialization")
            direction = 1 if ranges[0][1]-qref >= qref-ranges[0][0] else -1
            checks.compare(sr["direction"], direction, f"seed{seed}/public_direction")
            checks.compare(sr["selection_record"], {"joint_index": 0, "joint_position_rad": qref,
                "lower_limit_rad": ranges[0][0], "upper_limit_rad": ranges[0][1], "positive_room_rad": ranges[0][1]-qref,
                "negative_room_rad": qref-ranges[0][0], "direction": direction,
                "rule": "larger distance to the public joint limit; ties choose positive"}, f"seed{seed}/direction_record")
        else:
            direction = None
        derived, prefix_reference = {}, None
        for kind in KINDS:
            tid = f"seed{seed}_{kind}"
            plan, ep = next(p for p in plans if p["trial_id"] == tid), episode_map[tid]
            checks.compare(ep, plan, tid+"/plan")
            rows = grouped.get(tid, [])
            regular = [row for row in rows if "collector_exception" not in row]
            exceptions = [row for row in rows if "collector_exception" in row]
            failure_start = checks.failed
            checks.check(ep["status"] in ("completed", "terminated", "exception", "blocked"), "recorded_outcome", tid)
            checks.check(not exceptions or ep["status"] == "exception", "exception_outcome", tid)
            checks.check(ep.get("environment_fingerprint_before") == ep.get("environment_fingerprint_after") or ep["status"] != "completed",
                         "fixed_environment_parameters", tid)
            prefix = [trace_payload(r) for r in regular if r["step_index"] < 100]
            if len(prefix) == 100:
                if prefix_reference is None:
                    prefix_reference = prefix
                else:
                    checks.check(prefix == prefix_reference, "exact_paid_prefix_all_six_trials", tid)
            scores_v = {name: [] for name in (("frozen", "learned") if kind == "calibration" else CONTROL_KINDS)}
            scores_q = {name: [] for name in scores_v}
            tracking, actual_physics, previous_after, previous_request = [], 0, None, 0.
            phase_rows, phase_physics = Counter(), Counter()
            effort = {"requested_absolute_nm_s": 0., "requested_squared_nm2_s": 0., "actual_absolute_nm_s": 0., "actual_squared_nm2_s": 0.}
            planner_calls = fallbacks = saturated = 0
            risk_full, risk_control = new_risk(), new_risk()
            for index, row in enumerate(regular):
                location = tid+"/"+str(index)
                checks.compare(row["step_index"], index, location+"/index")
                phase = "prefix" if index < 100 else (kind if kind in ("calibration", "prediction") else "control")
                checks.compare({key: row[key] for key in ("seed", "kind", "phase", "model_scope", "integration")},
                               {"seed": seed, "kind": kind, "phase": phase, "model_scope": scope(kind), "integration": mode(kind)}, location+"/identity")
                before, after = row["observation_before"], row["observation_after"]
                for key, width in NATIVE.items():
                    vector(before[key], width)
                    vector(after[key], width)
                checks.check(previous_after is None or previous_after == before, "native_continuity", location)
                previous_after = after
                qpos, qvel = vector(row["qpos"], 15), vector(row["qvel"], 14)
                checks.check(after["joint_position"] == qpos[7:] and after["joint_velocity"] == qvel[6:], "native_encoder_mapping", location)
                request = vector(row["requested_torque"], 8)
                checks.check(abs(request[0]) <= .5 and request[1:] == [0.]*7, "shared_permission_and_other_joint_zero", location)
                q, v, u = before["joint_position"][0], before["joint_velocity"][0], request[0]
                diagnostic = row["diagnostics"]
                n = diagnostic["executed_substeps"]
                checks.check(type(n) is int and 0 <= n <= 10 and (n == 10 or diagnostic["terminated"]), "legal_partial_substeps", location)
                actual_physics += n
                phase_rows[phase] += 1
                phase_physics[phase] += n
                checks.compare(diagnostic["step_id"], index+1, location+"/step_counter")
                checks.compare(diagnostic["physics_steps"], actual_physics, location+"/physics_counter")
                checks.compare(diagnostic["time"], actual_physics*.002, location+"/physical_time")
                checks.compare(diagnostic["requested_torque"], request, location+"/diagnostic_request")
                checks.compare(diagnostic["accepted_torque"], request, location+"/accepted_request")
                history = diagnostic["applied_torque_history"]
                checks.check(len(history) == n, "returned_torque_substeps", location)
                guarded = 0
                for actual in history:
                    vector(actual, 8)
                    checks.check(all(a in (0., requested) for a, requested in zip(actual, request)), "shield_preserves_or_zeroes_only", location)
                    guarded += any(a != requested for a, requested in zip(actual, request))
                # guarded_substeps can include a zero request flagged at a limit;
                # mismatch-count is a lower bound, never invent a shielding event.
                checks.check(guarded <= diagnostic["guarded_substeps"] <= n, "guarded_substep_bounds", location)
                if history:
                    checks.compare(diagnostic["applied_torque"], history[-1], location+"/last_applied")
                    checks.compare(after["actuator_torque"], history[-1], location+"/native_actuator")
                checks.compare(after["previous_command"], request, location+"/known_command_history")
                for name in ("substep_ground_normal_forces", "substep_kinetic_energies", "substep_minimum_contact_distances"):
                    vector(diagnostic[name], n)
                checks.compare(diagnostic["peak_substep_ground_normal_force"], max(diagnostic["substep_ground_normal_forces"], default=0.), location+"/force_peak")
                checks.compare(diagnostic["ground_normal_impulse_ns"], sum(diagnostic["substep_ground_normal_forces"])*.002, location+"/force_impulse")
                checks.compare(diagnostic["peak_substep_kinetic_energy"], max(diagnostic["substep_kinetic_energies"], default=0.), location+"/energy_peak")
                checks.compare(diagnostic["minimum_substep_contact_distance"], min(diagnostic["substep_minimum_contact_distances"], default=0.), location+"/contact_distance")
                record_risk(risk_full, row, ranges)
                if phase == "control":
                    record_risk(risk_control, row, ranges)
                checks.check(not diagnostic["terminated"] or index == len(regular)-1 and ep["status"] in ("terminated", "exception"), "terminal_is_final_row", location)
                if index < 100:
                    checks.compare(request, [0.]*8, location+"/paid_zero_prefix")
                    checks.compare(row["predicted_next_qv"], {}, location+"/prefix_no_prediction")
                    checks.compare(row["model_update"], None, location+"/prefix_no_update")
                    checks.compare(row["target_q"], None, location+"/prefix_no_target")
                    continue
                if qref is None:
                    raise ValueError("Active transition lacks its reference and model.")
                if index == 100:
                    checks.check(q == qref, "prefix_reference_exact", location)
                active = index-100
                if kind in ("calibration", "prediction"):
                    slot = active % (30 if kind == "calibration" else 20)
                    amplitude = CALIBRATION_AMPLITUDES[active//30] if kind == "calibration" else .25
                    positive_end, negative_start, negative_end = (5, 15, 20) if kind == "calibration" else (7, 10, 17)
                    prescribed = direction*(amplitude if slot < positive_end else (-amplitude if negative_start <= slot < negative_end else 0.))
                    checks.compare(u, prescribed, location+"/fixed_request_schedule")
                    checks.compare(row["target_q"], None, location+"/no_task_target")
                    checks.compare(row["planner_decision"], None, location+"/no_planning")
                else:
                    target = qref+direction*(.04 if active < 100 else .08)
                    checks.compare(row["target_q"], target, location+"/current_target_only")
                    checks.check(ranges[0][0]+.03 <= target <= ranges[0][1]-.03, "target_public_interior", location)
                    chosen_theta = INITIAL if scope(kind) == "frozen" else observed_theta
                    decision = replay_mpc(chosen_theta, qref, q, v, target, previous_request, ranges[0], mode(kind))
                    checks.compare(row["planner_decision"], decision, location+"/independent_all_candidate_planning")
                    checks.compare(u, decision["torque"], location+"/selected_request")
                    planner_calls += decision["mathematical_prediction_calls"]
                    fallbacks += int(decision["fallback"])
                    tracking.append(after["joint_position"][0]-target)
                    effort["requested_absolute_nm_s"] += abs(u)*n*.002
                    effort["requested_squared_nm2_s"] += u*u*n*.002
                    effort["actual_absolute_nm_s"] += sum(abs(a[0]) for a in history)*.002
                    effort["actual_squared_nm2_s"] += sum(a[0]*a[0] for a in history)*.002
                    saturated += int(abs(u) == .5)
                previous_request = u
                if kind == "calibration":
                    predictions = {"frozen": predict(INITIAL, qref, q, v, u, "endpoint_euler"),
                                   "learned": predict(observed_theta, qref, q, v, u, "endpoint_euler")}
                else:
                    predictions = {name: predict(INITIAL if scope(name) == "frozen" else observed_theta,
                                                   qref, q, v, u, mode(name)) for name in CONTROL_KINDS}
                    checks.check(row["predicted_next_qv"]["frozen_euler_mpc"][1] == row["predicted_next_qv"]["frozen_trapezoid_mpc"][1]
                                 and row["predicted_next_qv"]["learned_euler_mpc"][1] == row["predicted_next_qv"]["learned_trapezoid_mpc"][1], "same_one_step_endpoint_velocity_between_integrators", location)
                checks.compare(row["predicted_next_qv"], predictions, location+"/causal_preupdate_predictions")
                next_v, next_q = after["joint_velocity"][0], after["joint_position"][0]
                for name, (pq, pv) in predictions.items():
                    scores_q[name].append(next_q-pq)
                    scores_v[name].append(next_v-pv)
                update = row["model_update"]
                if kind == "calibration" and n == 10:
                    features = feature_vector(qref, q, v, u)
                    checks.compare(update, {"features": features, "observed_next_v_rad_s": next_v,
                        "preupdate_prediction": {"next_q_rad": predictions["learned"][0], "next_v_rad_s": predictions["learned"][1]},
                        "preupdate_error_rad_s": next_v-predictions["learned"][1], "parameter_fingerprint_before": observed_hash,
                        "phase": "identification", "updated": True}, location+"/RLS_causality")
                    theta, covariance = replay_rls(theta, covariance, features, next_v)
                    updates += 1
                    checks.compare(update["coefficients_after"], theta, location+"/independent_theta")
                    checks.compare(update["covariance_after"], covariance, location+"/independent_P")
                    checks.compare(update["update_count"], updates, location+"/update_count")
                    observed_theta, observed_covariance = update["coefficients_after"], update["covariance_after"]
                    observed_hash = digest(model_record(qref, observed_theta, observed_covariance))
                    checks.compare(update["parameter_fingerprint_after"], observed_hash, location+"/exact_hash_chain")
                elif kind == "calibration":
                    checks.compare(update, {"updated": False, "phase": "partial_calibration_interval", "executed_substeps": n, "update_count": updates}, location+"/no_partial_interval_update")
                else:
                    checks.compare(update, None, location+"/no_evaluation_updates")
            # Legal failures keep paid-but-unstored steps separate from returned
            # telemetry. They never acquire complete metrics or pass adoption.
            observed_calls = len(regular)
            for phase in ("prefix", "calibration", "prediction", "control"):
                budget = ep["phase_budgets"][phase]
                checks.check(all(type(budget[k]) is int and budget[k] >= 0 for k in ("control_calls_attempted", "control_steps", "physics_steps")), "integer_phase_budget", tid+"/"+phase)
                checks.check(budget["control_calls_attempted"] >= budget["control_steps"] >= phase_rows[phase]
                             and budget["physics_steps"] >= phase_physics[phase]
                             and budget["physics_steps"] <= budget["control_calls_attempted"]*10, "paid_vs_observed_phase_budget", tid+"/"+phase)
            for key in ("control_calls_attempted", "control_steps", "physics_steps"):
                checks.compare(ep[key], sum(b[key] for b in ep["phase_budgets"].values()), tid+"/"+key)
            missing_physics = ep["physics_steps"]-actual_physics
            verify_budget_bounds(ep, checks, tid)
            complete = (ep["status"] == "completed" and observed_calls == plan["maximum_control_steps"]
                        and ep["control_calls_attempted"] == ep["control_steps"] == observed_calls
                        and ep["physics_steps"] == 10*observed_calls and not exceptions
                        and all(not r["diagnostics"]["terminated"] and r["diagnostics"]["executed_substeps"] == 10 for r in regular))
            checks.check(ep["status"] != "completed" or complete, "claimed_completion_has_full_valid_trajectory", tid)
            if ep["status"] == "blocked":
                checks.check(not rows and ep["control_calls_attempted"] == ep["control_steps"] == ep["physics_steps"] == 0, "blocked_has_zero_physical_cost", tid)
            ev = sr["evaluations"].get(kind)
            effort_audit = {"independent_effort": effort, "requested_effort_reconstruction_complete": False,
                            "actual_effort_reconstruction_complete": False, "unreconstructed_actual_effort_substeps": 0}
            missing_rows = ep["control_steps"]-len(regular)
            if ep["status"] != "blocked":
                checks.compare(ev["completed"], complete, tid+"/completion")
                if complete:
                    checks.compare(ev, {"tracking_rmse_rad": rmse(tracking),
                        "velocity_prediction_rmse": {name: rmse(values) for name, values in scores_v.items()},
                        "position_prediction_rmse": {name: rmse(values) for name, values in scores_q.items()},
                        "metric_control_step_count": len(tracking), "saturated_control_steps": saturated}, tid+"/independent_complete_metrics")
                effort_audit = reconcile_effort(ev, effort, ep["phase_budgets"]["control"]["physics_steps"],
                                                phase_physics["control"], exceptions, checks, tid+"/effort")
                effort = effort_audit["independent_effort"]
                checks.check(not ep["risk_telemetry_complete"] or missing_physics == 0, "risk_completeness_not_overclaimed", tid)
                attempts, failed_attempts, decisions = ev["planner_attempt_count"], ev["failed_planner_attempts"], ev["planner_decision_count"]
                checks.check(all(type(n) is int and n >= 0 for n in (attempts, failed_attempts, decisions))
                             and failed_attempts <= attempts <= (200 if kind in CONTROL_KINDS else 0), "planner_attempt_budget", tid)
                checks.compare(decisions, attempts-failed_attempts, tid+"/successful_vs_failed_planning")
                checks.compare(ev["mathematical_prediction_calls_complete"], failed_attempts == 0, tid+"/collector_mathcall_completeness")
                checks.compare(ev["mathematical_prediction_calls_is_lower_bound"], failed_attempts > 0, tid+"/failed_planning_lower_bound")
                known_decisions = len(tracking)
                checks.check(decisions >= known_decisions, "paid_planning_decisions_not_dropped", tid)
                checks.check(planner_calls <= ev["mathematical_prediction_calls"] <= 135*decisions,
                             "successful_planning_prediction_cost_bounds", tid)
                checks.check(finite(ev["controller_seconds_total"]) and ev["controller_seconds_total"] >= 0,
                             "nonnegative_planning_wall_cost", tid)
                if complete:
                    checks.compare(ev["mathematical_prediction_calls"], planner_calls, tid+"/planning_computation")
                    checks.compare(ev["planner_fallbacks"], fallbacks, tid+"/fallback_count")
                    checks.compare(ev["planner_decision_count"], 200 if kind in CONTROL_KINDS else 0, tid+"/planning_decision_count")
                    checks.compare(failed_attempts, 0, tid+"/no_completed_failed_planning")
                else:
                    checks.check(ev["mathematical_prediction_calls"] >= planner_calls, "failed_step_planning_cost_retained", tid)
                if kind != "calibration":
                    final_hashes = [initial_hash, observed_hash]
                    checks.compare(ev["models_before"], final_hashes, tid+"/models_before")
                    checks.compare(ev["models_after"], final_hashes, tid+"/models_after")
                    checks.compare(ev["integration_models_before"], view_hashes, tid+"/view_hashes_before")
                    checks.compare(ev["integration_models_after"], view_hashes, tid+"/view_hashes_after")
                if kind in CONTROL_KINDS and ev["planner_spec"] is not None:
                    spec = ev["planner_spec"]
                    checks.compare(spec, {"config": MPC_CONFIG, "qref_rad": qref, "joint_range_rad": ranges[0],
                        "candidates_nm": [-.5+i*.125 for i in range(9)], "physical_queries": 0,
                        "forecast_bounds_rad": [max(qref-.15, ranges[0][0]-.03), min(qref+.15, ranges[0][1]+.03)],
                        "target_bounds_rad": [max(qref-.15, ranges[0][0]+.03), min(qref+.15, ranges[0][1]-.03)],
                        "integration": integration_spec(mode(kind), initial_hash if scope(kind) == "frozen" else observed_hash),
                        "integration_fingerprint": view_hashes[kind]}, tid+"/fixed_planner_spec")
            if kind == "calibration" and qref is not None:
                saved = sr["learned_model"]
                checks.check(digest({field: saved[field] for field in MODEL_FIELDS}) == saved["parameter_fingerprint"],
                             "saved_model_self_consistent_fingerprint", tid)
                reconstruction_complete = saved["update_count"] == updates
                if reconstruction_complete:
                    checks.compare(saved, {**model_record(qref, theta, covariance), "trainable": False, "update_count": updates}, tid+"/final_RLS_snapshot")
                    checks.compare(saved["parameter_fingerprint"], observed_hash, tid+"/final_hash")
                checks.check(sr["calibration_updates"] >= updates, "retained_update_cost", tid)
                checks.check(type(sr["calibration_updates"]) is int and sr["calibration_updates"] <= 300,
                             "frozen_calibration_update_cap", tid)
                if complete:
                    checks.compare(ev["models_before"], None, tid+"/no_preexisting_calibration_models")
                    checks.compare(ev["models_after"], [initial_hash, observed_hash], tid+"/calibration_final_models")
                    checks.compare(updates, 300, tid+"/fixed_update_budget")
                    checks.compare(sr["calibration_completed"], True, tid+"/calibration_completion")
                    for name in CONTROL_KINDS:
                        model = sr["integration_models"][name]
                        selected = sr["initial_model"] if scope(name) == "frozen" else saved
                        base_record = {field: selected[field] for field in MODEL_FIELDS}
                        fingerprint = selected["parameter_fingerprint"]
                        integration = integration_spec(mode(name), fingerprint)
                        checks.check(digest(base_record) == fingerprint, "shared_model_snapshot_exact_hash", name)
                        checks.compare(model, {**base_record, "parameter_fingerprint": fingerprint,
                            "update_count": selected["update_count"], "trainable": False, "frozen_view": True,
                            "integration": integration, "integration_fingerprint": digest(integration)}, tid+"/shared_frozen_view/"+name)
                        view_hashes[name] = digest(integration)
                    checks.compare(ev["integration_models_before"], {}, tid+"/views_do_not_exist_before_fit")
                    checks.compare(ev["integration_models_after"], view_hashes, tid+"/views_created_after_fit")
            integrity = checks.failed == failure_start
            derived[kind] = {"completed": complete, "eligible": complete and integrity, "status": ep["status"],
                "tracking_rmse_rad": rmse(tracking), "control_effort": effort,
                "actual_effort_complete": effort_audit["actual_effort_reconstruction_complete"], "effort_audit": effort_audit,
                "metric_reconstruction_complete": missing_rows == 0 and missing_physics == 0,
                "unreconstructed_transition_rows": missing_rows,
                "collector_reported_metrics": None if ev is None else {key:ev.get(key) for key in
                    ("tracking_rmse_rad", "metric_control_step_count", "velocity_prediction_rmse", "position_prediction_rmse")},
                "full_risk": risk_full, "control_risk": risk_control, "missing_risk_substeps": missing_physics,
                "risk_telemetry_complete": missing_physics == 0 and ep.get("risk_telemetry_complete", False), "saturated_control_steps": saturated,
                "mathematical_prediction_calls": ev.get("mathematical_prediction_calls", 0) if ev else 0,
                "independently_replayed_mathematical_prediction_calls": planner_calls,
                "planner_cost_reconstruction_complete": bool(ev) and ev.get("failed_planner_attempts") == 0 and ev.get("planner_decision_count") == len(tracking),
                "unreconstructed_successful_planner_decisions": 0 if not ev else ev.get("planner_decision_count", 0)-len(tracking),
                "failed_planner_attempts": 0 if not ev else ev.get("failed_planner_attempts", 0),
                "planner_fallbacks": ev.get("planner_fallbacks", 0) if ev else 0,
                "returned_control_rows": len(tracking), "returned_physics_steps": actual_physics,
                "paid_budget": {key: ep[key] for key in ("control_calls_attempted", "control_steps", "physics_steps")}}
        for kind in KINDS:
            if qref is not None and sr.get("learned_model") is not None:
                regular = [r for r in grouped.get(f"seed{seed}_{kind}", []) if "collector_exception" not in r]
                derived[kind]["free_rollouts"] = diagnose_windows(regular, 400 if kind == "calibration" else (200 if kind == "prediction" else 300), qref, sr["learned_model"]["coefficients"])
                derived[kind]["final_model_calibration_in_sample"] = kind == "calibration"
        effects = None
        if all(derived[k]["eligible"] for k in CONTROL_KINDS):
            effects = factorial_effects({("nominal" if scope(k) == "frozen" else "learned", mode(k)): derived[k]["tracking_rmse_rad"] for k in CONTROL_KINDS})
        derived_seeds.append({"seed": seed, "complete": all(v["eligible"] for v in derived.values()),
                              "model_updates": sr["calibration_updates"], "independently_replayed_updates": updates,
                              "unreconstructed_updates": sr["calibration_updates"]-updates,
                              "evaluations": derived, "tracking_factorial_effects": effects})
    for key in ("control_calls_attempted", "control_steps", "physics_steps"):
        checks.compare(metadata[key], sum(ep[key] for ep in episodes), "metadata_"+key)
    checks.check(metadata["control_calls_attempted"] <= 5400 and metadata["control_steps"] <= 5400
                 and metadata["physics_steps"] <= 54000 and metadata["model_updates"] <= 900, "frozen_batch_budget_cap")
    checks.compare(metadata["model_updates"], sum(sr["calibration_updates"] for sr in results), "metadata_update_budget")
    for status in ("completed", "terminated", "exception", "blocked", "planned"):
        key = "unprocessed_trials" if status == "planned" else status+"_trials"
        checks.compare(metadata[key], sum(ep["status"] == status for ep in episodes), "metadata_"+key)
    checks.compare(metadata["all_trials_successful"], all(ep["status"] == "completed" for ep in episodes), "all_outcomes_success")
    checks.compare(metadata["failed_trials"], metadata["exception_trials"]+metadata["terminated_trials"], "all_failed_outcomes")
    checks.compare(metadata["skipped_trials"], metadata["blocked_trials"], "all_blocked_outcomes")
    checks.compare(metadata["complete"], metadata["archive_status"] == "complete", "archive_completion_is_not_adoption")
    checks.check(all(file_hash(path/name) == expected for name, expected in input_hashes.items()), "input_archive_unchanged")
    return {"path": str(path), "source_commit": metadata["source_commit"], "split": "development",
            "input_hashes": input_hashes, "seeds": derived_seeds,
            "budget": {key: metadata[key] for key in ("control_calls_attempted", "control_steps", "physics_steps", "model_updates")}}, grouped, metadata


def ratio_change(new, old):
    if old == 0.:
        return 0. if new == 0. else None
    return new/old-1.


def adoption_gate(seeds):
    """Frozen 5% development adoption rule, distinct from data integrity."""
    pairs = []
    unique = len(seeds) == 3 and {row["seed"] for row in seeds} == set(SEEDS)
    for row in seeds:
        ev = row["evaluations"]
        euler, trap = ev.get("learned_euler_mpc", {}), ev.get("learned_trapezoid_mpc", {})
        valid = (euler.get("eligible") is True and trap.get("eligible") is True
                 and euler.get("actual_effort_complete") is True and trap.get("actual_effort_complete") is True
                 and finite(euler.get("tracking_rmse_rad")) and finite(trap.get("tracking_rmse_rad"))
                 and euler["tracking_rmse_rad"] >= 0 and trap["tracking_rmse_rad"] >= 0
                 and all(finite(group.get("control_effort", {}).get(key))
                         and group["control_effort"][key] >= 0
                         for group in (euler, trap)
                         for key in ("actual_absolute_nm_s", "actual_squared_nm2_s")))
        pairs.append({"seed": row["seed"], "complete_pair": valid,
                      "euler_tracking_rmse_rad": euler.get("tracking_rmse_rad"),
                      "trapezoid_tracking_rmse_rad": trap.get("tracking_rmse_rad"),
                      "non_worse": valid and trap["tracking_rmse_rad"] <= euler["tracking_rmse_rad"],
                      "euler_actual_effort": euler.get("control_effort"), "trapezoid_actual_effort": trap.get("control_effort")})
    valid = unique and all(row["complete_pair"] for row in pairs)
    em = sum(row["euler_tracking_rmse_rad"] for row in pairs)/3 if valid else None
    tm = sum(row["trapezoid_tracking_rmse_rad"] for row in pairs)/3 if valid else None
    improvement = 1.-tm/em if valid and em > 0 else None
    efforts = {}
    for key in ("actual_absolute_nm_s", "actual_squared_nm2_s"):
        old = sum(row["euler_actual_effort"][key] for row in pairs)/3 if valid else None
        new = sum(row["trapezoid_actual_effort"][key] for row in pairs)/3 if valid else None
        change = ratio_change(new, old) if valid else None
        efforts[key] = {"euler_mean": old, "trapezoid_mean": new, "relative_increase": change,
                        "passed": valid and new <= 1.05*old}
    passed = (valid and all(row["non_worse"] for row in pairs) and improvement is not None
              and improvement >= .05 and all(row["passed"] for row in efforts.values()))
    return {"evaluated": valid, "passed": passed, "per_seed": pairs, "euler_raw_rmse_mean": em,
            "trapezoid_raw_rmse_mean": tm, "tracking_mean_improvement": improvement, "actual_effort_gates": efforts,
            "default_if_not_passed": "endpoint_euler", "claim_boundary": "Development default only; no unseen method advantage, skill acquisition or safety claim."}


def aggregate_factorial(seeds):
    complete = (len(seeds) == 3 and {row["seed"] for row in seeds} == set(SEEDS)
                and all(all(row["evaluations"].get(kind, {}).get("eligible") is True for kind in CONTROL_KINDS) for row in seeds))
    groups = {kind: {"per_seed_raw_tracking_rmse_rad": [row["evaluations"].get(kind, {}).get("tracking_rmse_rad") for row in seeds],
                     "three_seed_raw_rmse_mean": None if not complete else sum(row["evaluations"][kind]["tracking_rmse_rad"] for row in seeds)/3}
              for kind in CONTROL_KINDS}
    effects = None if not complete else factorial_effects({("nominal" if scope(kind) == "frozen" else "learned", mode(kind)):
                                                        groups[kind]["three_seed_raw_rmse_mean"] for kind in CONTROL_KINDS})
    return {"complete_four_group_three_seed_matrix": complete, "groups": groups,
            "raw_rmse_mean_factorial_effects": effects,
            "semantics": "Raw complete per-seed RMSE means, not pooled samples, mean percentages or a statistical significance test."}


def audit(path, *, reference=None, git_root=ROOT):
    wall_start, cpu_start = time.perf_counter(), time.process_time()
    checks = Checks()
    result = None
    reported_budget = None
    anchor = {"provided": reference is not None, "exact_replay_verified": False}
    try:
        initial_metadata = require_development(path)
        reported_budget = {key: initial_metadata.get(key) for key in
                           ("control_calls_attempted", "control_steps", "physics_steps", "model_updates")}
        result, grouped, metadata = audit_archive(path, checks, git_root)
        anchor = historical_anchor(reference, grouped, metadata, checks, git_root)
    except (OSError, ValueError, KeyError, TypeError, IndexError, AttributeError, OverflowError, zipfile.BadZipFile) as error:
        checks.check(False, "archive_schema_or_read_error", {"type": type(error).__name__, "message": str(error)})
    gate = adoption_gate([] if result is None else result["seeds"])
    gate["data_consistency_verified"] = checks.failed == 0
    gate["historical_replay_verified"] = anchor["exact_replay_verified"]
    gate["validated_pass"] = gate["passed"] and checks.failed == 0 and anchor["exact_replay_verified"] and git_root is not None
    return {"schema_version": 1, "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "purpose": __doc__, "audit_script_sha256": file_hash(Path(__file__)),
            "checks": checks.count, "failed": checks.failed, "maximum_recomputation_difference": checks.maximum_difference,
            "violations": checks.violations, "archive": result, "historical_anchor": anchor, "development_adoption_gate": gate,
            "reported_paid_budget_if_replay_incomplete": reported_budget,
            "reported_budget_semantics": "Collector-reported counters stay visible if data reconstruction fails; independently checked budget is archive.budget when available.",
            "four_group_factorial_summary": aggregate_factorial([] if result is None else result["seeds"]),
            "rollout_semantics": "Recorded future requests condition each offline free rollout; only initial native q/v is read. No future true states are fed back. Overlapping windows are denominators, not independent seeds. A fully executed terminal interval may end a physical window, counted separately; no window advances past a stop, and partial terminal intervals are excluded. Failed trials cannot pass adoption. Final calibration scores are in-sample post-fit.",
            "execution": {"wall_seconds": time.perf_counter()-wall_start, "cpu_seconds": time.process_time()-cpu_start,
                "timing_scope": "audit entry through report assembly; excludes import and final JSON writing",
                "python": sys.version, "platform": platform.platform(), "third_party_dependencies": [],
                "physical_simulation_calls": 0, "model_parameter_updates": 0, "replayed_updates_are_frozen_log_audits": True}}


def validate_output_path(output, inputs):
    output = Path(output).resolve()
    if output.exists():
        raise ValueError("Refusing to overwrite an existing audit output.")
    if any(output.is_relative_to(Path(path).resolve()) for path in inputs if path is not None):
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
                      "adoption_pass": report["development_adoption_gate"]["validated_pass"]}))
    return 1 if report["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
