"""Independent declared frozen local-joint audit; standard library, no physics/fitting imports.
Native research stops and all paid costs are independently reconstructed.
"""
from __future__ import annotations
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
import argparse
import gzip
import platform
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
import zipfile
import hashlib
import json
import math
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / 'pyproject.toml').is_file())
SEEDS = [20, 21, 22]
RESET_SEEDS = {20: 1822509288, 21: 2605417566, 22: 1950464737}
FROZEN_FINAL_SCHEDULE = "short"
PD_GAINS = {"kp": 64., "kd": 0.}
DT, PHYSICS_DT = .02, .002
INTEGRATION = 'endpoint_euler'
HORIZONS = (1, 5, 15, 50)
STRUCTURES = ('linear4', 'hinge5')
INITIAL = {'linear4': [1., 0., .02, 0.], 'hinge5': [1., 0., .02, 0., 0.]}
PHASES = ('prefix', 'calibration', 'prediction', 'control')
KINDS = ("calibration", "prediction_low", "prediction_full", "nominal_mpc", "learned_mpc", "tuned_pd", "zero_torque")
CONTROL_KINDS = KINDS[3:]
MPC_KINDS = ("nominal_mpc", "learned_mpc")
MODEL_REQUIRED = KINDS[:5]
CALIBRATION_AMPLITUDES = [.125, .25, .5, .125, .25, .5, .125, .25, .5, .125]
NATIVE = {'joint_position': 8, 'joint_velocity': 8, 'imu_gyro': 3, 'imu_acceleration': 3, 'actuator_torque': 8, 'previous_command': 8}
EFFORT_KEYS = ('requested_absolute_nm_s', 'requested_squared_nm2_s', 'actual_absolute_nm_s', 'actual_squared_nm2_s')
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
PROTOCOL = "docs/LOCAL_FROZEN_VALIDATION_PROTOCOL.md"
ASSET = "src/developmental_physics/assets/ground_body.xml"
REQUIRED_SOURCES = frozenset({PROTOCOL, ASSET, "pyproject.toml"} | {
    "src/developmental_physics/"+name for name in
    ("__init__.py", "environment.py", "collect.py", "probes.py", "local_model.py",
     "local_integration.py", "local_frozen_validation.py", "feedback_validate.py")})
BASE_REQUIRED_SOURCES = REQUIRED_SOURCES - {PROTOCOL}

@dataclass(frozen=True)
class AuditSpec:
    """Trusted source declaration, never inferred from archive metadata.

    Tuple fields are intentional: a frozen dataclass with mutable lists or dicts
    would still permit changing the accepted experiment after construction.
    None PD gains permit an explicit unfinished declaration, but block reads.
    """
    suite: str
    pose: str
    joint_index: int
    split: str
    seeds: tuple[int, ...]
    reset_seed_pairs: tuple[tuple[int, int], ...]
    protocol: str
    pd_kp: float | None
    pd_kd: float | None
    calibration_schedule: str = "short"
    claim_boundary: str = "Declared local protocol only; no task acquisition, real robot or unknown-dynamics generalization."
    pd_selection_source: tuple[tuple[str, str | int], ...] = ()

    def __post_init__(self):
        if (type(self.joint_index) is not int or not 0 <= self.joint_index < 8
            or type(self.seeds) is not tuple or len(self.seeds) != 3
            or any(type(seed) is not int for seed in self.seeds)
            or len(set(self.seeds)) != 3
            or type(self.reset_seed_pairs) is not tuple
            or any(type(pair) is not tuple or len(pair) != 2
                   or any(type(x) is not int for x in pair) for pair in self.reset_seed_pairs)
            or len(self.reset_seed_pairs) != 3
            or {pair[0] for pair in self.reset_seed_pairs} != set(self.seeds)
            or any(not 0 <= pair[1] < 2**32 for pair in self.reset_seed_pairs)
            or any(type(x) is not str or not x for x in
                   (self.suite, self.pose, self.split, self.protocol, self.claim_boundary))):
            raise ValueError("Immutable complete joint/seed/protocol declaration required.")
        if Path(self.protocol).is_absolute() or ".." in Path(self.protocol).parts:
            raise ValueError("Repository-relative protocol path required.")
        if (type(self.pd_selection_source) is not tuple
            or any(type(pair) is not tuple or len(pair) != 2
                   or type(pair[0]) is not str or type(pair[1]) not in (str, int)
                   for pair in self.pd_selection_source)
            or len({pair[0] for pair in self.pd_selection_source}) != len(self.pd_selection_source)):
            raise ValueError("Immutable unique PD selection provenance required.")

    @property
    def reset_seeds(self):
        return dict(self.reset_seed_pairs)

    @property
    def pd_gains(self):
        return {"kp": self.pd_kp, "kd": self.pd_kd}

    @property
    def required_sources(self):
        return BASE_REQUIRED_SOURCES | {self.protocol}

    def require_frozen(self):
        if (self.calibration_schedule not in ("short", "reordered")
            or not all(finite(x) and x >= 0 for x in (self.pd_kp, self.pd_kd))):
            raise ValueError("Schedule and PD gains must be frozen before archive metadata or trace is read.")

    def record(self):
        return {"suite": self.suite, "pose": self.pose, "joint_index": self.joint_index,
                "split": self.split, "seeds": list(self.seeds),
                "reset_seeds": self.reset_seeds, "protocol": self.protocol,
                "pd_gains": self.pd_gains, "calibration_schedule": self.calibration_schedule,
                "claim_boundary": self.claim_boundary,
                "pd_selection_source": dict(self.pd_selection_source)}


SHOULDER_FINAL_SPEC = AuditSpec(
    suite="shoulder_final", pose="supine", joint_index=0, split="final_holdout",
    seeds=(20, 21, 22),
    reset_seed_pairs=((20, 1822509288), (21, 2605417566), (22, 1950464737)),
    protocol="docs/LOCAL_FROZEN_VALIDATION_PROTOCOL.md", pd_kp=64., pd_kd=0.,
    claim_boundary="Frozen single-shoulder protocol only; no task acquisition, real robot or unknown-dynamics generalization.")
ELBOW_DEVELOPMENT_SPEC = AuditSpec(
    suite="elbow_development", pose="supine", joint_index=1, split="development",
    seeds=(0, 1, 2),
    reset_seed_pairs=((0, 3757552657), (1, 1641411168), (2, 2001025171)),
    protocol="docs/ELBOW_BODY_DEVELOPMENT_PROTOCOL.md", pd_kp=64., pd_kd=1.,
    claim_boundary="Elbow recipe-transfer development only; no new holdout, full-body or real-robot claim.",
    pd_selection_source=(
        ("source_commit", "91223b39c86fbeb09f7bc399229789b1e00ce181"),
        ("audit_sha256", "d84ad31b28f7fcc4ded8003b2503138a3cacc9f9b2fed33bf675758e43100571"),
        ("summary_sha256", "5aaefe21d6aa8314673a5560522e8865123acda318e833b4951f4c5d00efc3e8"),
        ("candidate", 8), ("development_control_calls", 7521),
        ("development_physics_substeps", 75210), ("body_model_updates", 0),
    ))


STUDY_POSITION_LIMIT = .12
STUDY_VELOCITY_LIMIT = 1.0

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
    if len(limits) != 2 or not all(finite(x) for x in [qref, q, v, target, previous, *limits]):
        raise ValueError("Finite planner inputs required.")
    target_lower, target_upper = max(qref-.15, limits[0]+.03), min(qref+.15, limits[1]-.03)
    if not target_lower <= target <= target_upper:
        raise ValueError("target must be local and inside the public limit margin")
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


def rmse(values):
    if not values:
        return None
    scale = max(abs(x) for x in values)
    return 0. if scale == 0 else scale*math.sqrt(sum((x/scale)**2 for x in values)/len(values))


def new_effort():
    return {key: 0. for key in EFFORT_KEYS}


def new_risk():
    return {"ground_force_peak_n": 0., "ground_normal_impulse_ns": 0., "kinetic_energy_peak_j": 0.,
            "minimum_contact_distance_m": 0., "maximum_penetration_m": 0., "native_joint_speed_peak_rad_s": [0.]*8,
            "soft_limit_excursion_peak_rad": [0.]*8, "guard_margin_intrusion_peak_rad": [0.]*8,
            "permission_screened_substeps_by_joint": [0]*8, "guarded_substeps": 0,
            "target_guarded_substeps": 0, "physical_substeps": 0, "returned_endpoint_samples": 0}


def record_risk(risk, row, ranges, *, joint_index=0):
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
    risk["target_guarded_substeps"] += sum(a[joint_index] != row["requested_torque"][joint_index] for a in d["applied_torque_history"])
    risk["physical_substeps"] += d["executed_substeps"]
    risk["returned_endpoint_samples"] += 1


def verify_budget_bounds(ep, checks, location):
    kind = ep["kind"]
    caps = {"prefix": 100, "calibration": 300 if kind == "calibration" else 0,
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


def reconcile_effort(ev, phase, observed, paid, raw_substeps, exceptions, checks, location, *, joint_index=0):
    """Recover known paid requests; absent realized history remains a lower bound."""
    missing, known = paid-raw_substeps, dict(observed)
    commands = [r.get("requested_torque") for r in exceptions if r.get("phase") == phase]
    recoverable = missing == 0 or (0 < missing <= 10 and len(commands) == 1
        and isinstance(commands[0], list) and len(commands[0]) == 8
        and all(finite(u) and abs(u) <= .5 for u in commands[0]) and all(u == 0. for j, u in enumerate(commands[0]) if j != joint_index))
    if missing > 0 and recoverable:
        u = commands[0][joint_index]
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


def verify_transition(row, previous, counters, ranges, checks, location, *, joint_index=0):
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
    checks.check(abs(request[joint_index]) <= .5 and all(u == 0. for j, u in enumerate(request) if j != joint_index), "shared_permission_other_joints_zero", location)
    diagnostic, index = row["diagnostics"], row["step_index"]
    n = diagnostic["executed_substeps"]
    checks.check(type(diagnostic.get("terminated")) is bool, "boolean_environment_stop", location)
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


def state_coverage(calibration_rows, control_rows, qref, *, joint_index=0):
    """Public q/v support and nearest distances; envelope is not a safety set."""
    calibration = [(r["observation_before"]["joint_position"][joint_index]-qref, r["observation_before"]["joint_velocity"][joint_index])
        for r in calibration_rows if r["step_index"] >= 100 and r["diagnostics"]["executed_substeps"] == 10]
    control = [(r["observation_before"]["joint_position"][joint_index]-qref, r["observation_before"]["joint_velocity"][joint_index])
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
        "semantics": "Nearest min abs(q-q_i) over complete calibration inputs, in rad; position only, not a joint q/v distance. Strict outside bounds; equality is inside. All support envelopes and nearest q distances are descriptive in this final evaluation, not safety sets or additional gates."}


def ratio_change(new, old):
    return None if old == 0. else new/old-1.


def numeric_leaves(value, prefix=""):
    if isinstance(value, dict):
        for key, item in value.items():
            yield from numeric_leaves(item, prefix+"/"+key)
    elif isinstance(value, list):
        for i, item in enumerate(value):
            yield from numeric_leaves(item, prefix+"/"+str(i))
    elif finite(value):
        yield prefix, value


def validate_output_path(output, inputs):
    output = Path(output).resolve()
    if output.exists():
        raise ValueError("Refusing to overwrite existing audit output.")
    if any(output.is_relative_to(Path(p).resolve()) for p in inputs if p is not None):
        raise ValueError("Audit output must be outside every input archive and reference.")
    return output


def duration(kind):
    if kind not in KINDS:
        raise ValueError('Unknown C2-C trial kind.')
    return 300 if kind == 'calibration' else 100 if kind.startswith('prediction_') else 200


def calibration_request(kind, active, direction):
    if kind not in ('short', 'reordered') or type(active) is not int or not 0 <= active < 300:
        raise ValueError('Frozen calibration kind and active index required.')
    if type(direction) is not int or direction not in (-1, 1):
        raise ValueError('Fixed public direction must be +1 or -1.')
    if kind == 'short':
        amplitude, slot = CALIBRATION_AMPLITUDES[active//30], active % 30
        return direction*(amplitude if slot < 5 else -amplitude if 15 <= slot < 20 else 0.)
    if active < 50:
        return direction*CALIBRATION_AMPLITUDES[active//5]
    if 150 <= active < 200:
        return -direction*CALIBRATION_AMPLITUDES[(active-150)//5]
    return 0.


def study_condition(qref, q, v, phase):
    """Formal protocol: post-return native endpoint only, all active phases."""
    if phase not in PHASES:
        raise ValueError('Known phase required for StudyAbort.')
    if phase == 'prefix':
        return {'applicable': False, 'triggered': False, 'position_triggered': False, 'velocity_triggered': False}
    if not all(finite(x) for x in (qref, q, v)):
        raise ValueError('A nonfinite native value is invalid, not a non-triggered monitor.')
    position, velocity = abs(q-qref) >= STUDY_POSITION_LIMIT, abs(v) >= STUDY_VELOCITY_LIMIT
    return {'applicable': True, 'triggered': position or velocity,
            'position_triggered': position, 'velocity_triggered': velocity,
            'q_rad': q, 'qref_rad': qref, 'q_offset_rad': q-qref, 'velocity_rad_s': v,
            'absolute_position_limit_rad': STUDY_POSITION_LIMIT, 'absolute_velocity_limit_rad_s': STUDY_VELOCITY_LIMIT}


def stop_flags(row):
    """Auditor normalization is computed from native fields, not a trusted flag.

    Archive adapter must compare the raw monitor payload to study_condition,
    then attach audited_study_abort_triggered. It must not modify raw input.
    """
    study = row.get('audited_study_abort_triggered', False)
    env = row['diagnostics']['terminated']
    if type(study) is not bool or type(env) is not bool:
        raise ValueError('Boolean independently reconstructed stop flags required.')
    return {'study': study, 'environment': env, 'any': study or env}


def valid_window(indexed, start, horizon, *, joint_index=0):
    segment = []
    for index in range(start, start+horizon):
        row = indexed.get(index)
        if row is None:
            return None, 'missing_control_row'
        if 'collector_exception' in row:
            return None, 'collector_exception'
        if row['step_index'] != index:
            return None, 'nonconsecutive_step_index'
        before, after = row['observation_before'], row['observation_after']
        if not all(finite(obs[key][joint_index]) for obs in (before, after) for key in ('joint_position', 'joint_velocity')):
            return None, 'invalid_native_state'
        if not finite(row['requested_torque'][joint_index]):
            return None, 'invalid_request'
        diagnostic = row['diagnostics']
        if type(diagnostic['executed_substeps']) is not int or diagnostic['executed_substeps'] != 10:
            return None, 'partial_physics_interval'
        if segment:
            previous = segment[-1]
            if previous['phase'] != row['phase'] or previous['trial_id'] != row['trial_id']:
                return None, 'crossed_phase_or_trial_boundary'
            if stop_flags(previous)['any']:
                return None, 'continued_after_study_or_environment_stop'
            if previous['observation_after'] != before:
                return None, 'native_state_discontinuity'
            if abs(diagnostic['time']-previous['diagnostics']['time']-DT) > 1e-10:
                return None, 'time_discontinuity'
        stop_flags(row)
        segment.append(row)
    return segment, None


def window_denominators(indexed, active_steps, horizon, *, joint_index=0):
    expected, valid, terminal, study, env, both = max(active_steps-horizon+1, 0), 0, 0, 0, 0, 0
    excluded = Counter()
    for start in range(100, 100+expected):
        segment, reason = valid_window(indexed, start, horizon, joint_index=joint_index)
        if reason:
            excluded[reason] += 1
        else:
            valid += 1
            flags = stop_flags(segment[-1])
            terminal += int(flags['any'])
            study += int(flags['study'])
            env += int(flags['environment'])
            both += int(flags['study'] and flags['environment'])
    return {'expected_windows_from_planned_active_duration': expected, 'valid_physical_windows': valid,
        'excluded_windows': expected-valid, 'valid_windows_ending_in_termination': terminal,
        'valid_windows_ending_in_study_abort': study, 'valid_windows_ending_in_environment_termination': env,
        'valid_windows_ending_in_both_stop_conditions': both, 'exclusion_reasons': dict(excluded),
        'stop_count_semantics': 'Union terminal count is unique; study/environment counts can overlap.'}


def trial_is_complete(evaluation):
    return (evaluation.get('eligible') is True and evaluation.get('completed') is True
        and evaluation.get('status') == 'completed' and evaluation.get('study_aborted') is False
        and evaluation.get('environment_terminated') is False)











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

def trace_payload(row):
    return {key: row[key] for key in ("phase", "target_q", "requested_torque", "observation_before",
                                     "observation_after", "qpos", "qvel", "diagnostics")}

def replay_update(item, row, structure, state, qref, checks, location, *, exception=False, joint_index=0):
    """Only an explicitly recorded successful atomic update consumes one replay."""
    q, v = (row["observation_before"][k][joint_index] for k in ("joint_position", "joint_velocity"))
    u, next_v = row["requested_torque"][joint_index], row["observation_after"]["joint_velocity"][joint_index]
    features = feature_vector(qref, q, v, u, structure)
    before_hash = state_hash(qref, state)
    predicted = predict(state["observed_theta"], qref, q, v, u)
    checks.compare(item, {"model_id": row["calibration_schedule"]+"_"+structure,
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

def diagnose_windows(rows, active_steps, qref, models, *, joint_index=0):
    indexed = {r["step_index"]: r for r in rows if "collector_exception" not in r}
    predictors = {**models, "persistence": None}
    reports = []
    for horizon in HORIZONS:
        denominator = window_denominators(indexed, active_steps, horizon, joint_index=joint_index)
        errors = {name: {"q": [], "v": [], "path_q": [], "path_v": [], "invalid": 0} for name in predictors}
        for start in range(100, 100+max(active_steps-horizon+1, 0)):
            segment, reason = valid_window(indexed, start, horizon, joint_index=joint_index)
            if reason:
                continue
            first = segment[0]["observation_before"]
            q, v = first["joint_position"][joint_index], first["joint_velocity"][joint_index]
            requests = [r["requested_torque"][joint_index] for r in segment]
            truth = [(r["observation_after"]["joint_position"][joint_index], r["observation_after"]["joint_velocity"][joint_index]) for r in segment]
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

def conditional_metrics(rows, *, joint_index=0):
    """Every amplitude/block and control switch/hold is reported, including zero."""
    groups = {}
    for r in rows:
        if r["step_index"] < 100 or "collector_exception" in r:
            continue
        index, u = r["step_index"]-100, r["requested_torque"][joint_index]
        labels = ["abs_u="+str(abs(u)), "signed_u="+str(u)]
        if r["phase"] in ("calibration", "prediction"):
            width = 30 if r["phase"] == "calibration" else 20
            labels.append("block="+str(index//width))
        if r["phase"] == "control":
            labels.extend(["target="+("first" if index < 100 else "second"), "switch" if index in (0, 100) else "hold"])
        for label in labels:
            values = groups.setdefault(label, {"count": 0, "q": {}, "v": {}, "tracking": [], "effort": new_effort()})
            values["count"] += 1
            complete_interval = r["diagnostics"]["executed_substeps"] == 10
            for name, (pq, pv) in (r["predicted_next_qv"].items() if complete_interval else []):
                values["q"].setdefault(name, []).append(r["observation_after"]["joint_position"][joint_index]-pq)
                values["v"].setdefault(name, []).append(r["observation_after"]["joint_velocity"][joint_index]-pv)
            if r["target_q"] is not None and complete_interval:
                values["tracking"].append(r["observation_after"]["joint_position"][joint_index]-r["target_q"])
            n, history = r["diagnostics"]["executed_substeps"], r["diagnostics"]["applied_torque_history"]
            values["effort"][EFFORT_KEYS[0]] += abs(u)*n*PHYSICS_DT
            values["effort"][EFFORT_KEYS[1]] += u*u*n*PHYSICS_DT
            values["effort"][EFFORT_KEYS[2]] += sum(abs(a[joint_index]) for a in history)*PHYSICS_DT
            values["effort"][EFFORT_KEYS[3]] += sum(a[joint_index]*a[joint_index] for a in history)*PHYSICS_DT
    return {label: {"returned_transition_count": e["count"], "position_prediction_rmse": {n: rmse(v) for n, v in e["q"].items()},
        "velocity_prediction_rmse": {n: rmse(v) for n, v in e["v"].items()}, "tracking_rmse_rad": rmse(e["tracking"]),
        "known_substep_effort": e["effort"]} for label, e in sorted(groups.items())}


def control_tail_metrics(rows, *, joint_index=0):
    """Fixed last twenty planned endpoints of each target; descriptive only."""
    result = {}
    for name, first in (("first", 80), ("second", 180)):
        selected = [r for r in rows if r.get("phase") == "control"
                    and "collector_exception" not in r
                    and 100+first <= r["step_index"] < 120+first]
        complete = [r for r in selected if r["diagnostics"]["executed_substeps"] == 10
                    and r["target_q"] is not None]
        errors = [r["observation_after"]["joint_position"][joint_index]-r["target_q"] for r in complete]
        stopped = any(stop_flags(r)["any"] for r in selected)
        full_indices = {r["step_index"] for r in complete}
        result[name] = {
            "active_indices_inclusive": [first, first+19], "planned_endpoints": 20,
            "returned_endpoints": len(selected), "scored_complete_endpoints": len(complete),
            "partial_endpoints": len(selected)-len(complete),
            "missing_planned_endpoints": 20-len(selected), "contains_stop": stopped,
            "complete_without_stop": full_indices == set(range(100+first, 120+first)) and not stopped,
            "tracking_rmse_rad": rmse(errors),
            "mean_signed_error_rad": sum(errors)/len(errors) if errors else None,
            "maximum_absolute_error_rad": max(map(abs, errors)) if errors else None,
            "semantics": "Complete 20ms native endpoints only; fixed planned denominator20; full terminal scored but stop blocks window completion. Trial completion is reported separately.",
        }
    return result





def study_abort_spec():
    return {"phase": "every trial active only; never prefix", "absolute_q_minus_qref_rad": .12,
        "absolute_velocity_rad_s": 1., "comparison": ">=", "checks": ["every returned active endpoint"],
        "action": "end episode; no corrective command, continuation or replacement",
        "environment_protection": "unchanged; independent environment stop reason takes precedence",
        "last_complete_transition": "RLS update and endpoint metrics retained before stop",
        "claim_boundary": "Native research stop is not a proof of safety or real-world braking"}


def calibration_schedule_spec():
    return {"short": "ten 30-step blocks: +A*5, zero*10, -A*5, zero*10",
        "reordered": "+A repeated five in original order*50, zero*100, -A in same order*50, zero*100",
        "same_full_command_histogram": True, "short_switch_count_from_zero": 40,
        "reordered_switch_count_from_zero": 22,
        "causal_claim": "Total temporal-reordering effect; not isolated position exposure"}


def normalize_study_row(row, qref, checks, location, *, joint_index=0):
    """Reconstruct endpoint condition; raw flag cannot establish stop truth."""
    q, v = (row["observation_after"][key][joint_index] for key in ("joint_position", "joint_velocity"))
    condition = study_condition(qref, q, v, row["phase"])
    expected = None
    if condition["triggered"]:
        triggers = []
        if condition["position_triggered"]:
            triggers.append("absolute_q_minus_qref_rad")
        if condition["velocity_triggered"]:
            triggers.append("absolute_velocity_rad_s")
        expected = {"type": "StudyAbort", "message": "predeclared native active envelope reached", "stage": "endpoint",
            "triggers": triggers, "q_rad": q, "qref_rad": qref, "q_minus_qref_rad": q-qref,
            "velocity_rad_s": v, "thresholds": {"absolute_q_minus_qref_rad": .12, "absolute_velocity_rad_s": 1.},
            "feedback_action": None, "phase": row["phase"], "step_index": row["step_index"]}
    checks.compare(row.get("study_abort"), expected, location+"/independent_study_abort")
    # This is only an in-memory audit copy loaded from JSON; source bytes stay unchanged.
    row["audited_study_abort_triggered"] = condition["triggered"]
    return condition










def audit_archive(path, checks, git_root=ROOT, *, spec=SHOULDER_FINAL_SPEC):
    joint_index = spec.joint_index
    path = Path(path).resolve()
    metadata = require_final(path, spec=spec)
    ranges, input_hashes = verify_sources(path, metadata, checks, git_root, required=spec.required_sources)
    checks.compare(metadata["protocol"], {"path": spec.protocol, "sha256": metadata["source_sha256"][spec.protocol]}, "frozen_protocol")
    if spec.pd_selection_source:
        checks.compare(metadata.get("pd_selection_source"), dict(spec.pd_selection_source), "frozen_pd_selection_source")
    checks.compare(metadata["environment_config"], ENVIRONMENT, "environment_and_permission")
    checks.compare(metadata["integration"], INTEGRATION, "frozen_integration")
    checks.compare(metadata["evaluation_prediction_integration"], INTEGRATION, "evaluation_integration")
    checks.compare(metadata["structures"], ["hinge5"], "frozen_structures")
    checks.compare(metadata, {"calibration_dose": "old", "model_structure": "hinge5", "calibration_schedules": [spec.calibration_schedule]}, "frozen_recipe")
    checks.compare(metadata["comparison"], {"methods": list(CONTROL_KINDS), "single_schedule": spec.calibration_schedule, "single_fixed_dose": "old", "single_fixed_structure": "hinge5"}, "frozen_comparison")
    checks.compare(metadata["pd_gains"], spec.pd_gains, "fixed_pd_gains")
    checks.compare(metadata["pd_controller_spec"], {"implementation": "feedback_validate.pd_request", "kp": spec.pd_gains["kp"], "kd": spec.pd_gains["kd"], "input": "current encoder q/v and currently disclosed target", "permission_nm": .5, "body_model_input": False, "gain_updates": 0}, "fixed_pd_controller_spec")
    checks.compare(metadata["suite_spec"], {"pose": spec.pose, "joint": joint_index, "seeds": spec.seeds, "split": spec.split, "pd_kp": spec.pd_gains["kp"], "pd_kd": spec.pd_gains["kd"]}, "fixed_final_suite")
    checks.compare(metadata["study_abort_spec"], study_abort_spec(), "frozen_study_abort")
    checks.compare(metadata["calibration_schedule_definition"], calibration_schedule_spec(), "frozen_schedule_definition")
    checks.check(finite(metadata.get("cpu_seconds")) and metadata["cpu_seconds"] >= 0 and finite(metadata.get("wall_seconds")) and metadata["wall_seconds"] >= 0, "finite_process_wall_timing")
    checks.compare(metadata["cpu_seconds_scope"], "Current process only; same timer-start/checkpoint scope as wall_seconds; excludes imports, initial source snapshot and setup before timers", "timing_scope")
    checks.compare(metadata["calibration_block_amplitudes_nm"], CALIBRATION_AMPLITUDES, "calibration_doses")
    checks.compare(metadata["prediction_block_amplitudes_nm"], PREDICTION_AMPLITUDES, "prediction_doses")
    checks.compare(metadata, {"gpu": None, "prefix_steps": 100, "calibration_steps": 300,
        "prediction_steps": 100, "control_steps_per_trial": 200, "teacher_calls": 0,
        "external_demonstration_samples": 0, "policy_parameter_updates": 0}, "frozen_metadata")
    plans = planned_matrix(spec=spec)
    checks.compare(metadata["planned_episodes"], plans, "frozen_full_plan")
    checks.compare(metadata["planned_episode_count"], 21, "planned_trials")
    checks.compare(metadata["maximum_control_steps"], 6000, "planned_budget")
    episodes, results = load_json(path/"episodes.json"), load_json(path/"seed_results.json")
    checks.compare([ep["trial_id"] for ep in episodes], [p["trial_id"] for p in plans], "complete_outcome_ledger")
    episode_map = {ep["trial_id"]: ep for ep in episodes}
    if len(episode_map) != len(episodes):
        raise ValueError("Duplicate episode IDs.")
    by_seed = {r["seed"]: r for r in results}
    checks.check(len(by_seed) == len(results) and set(by_seed).issubset(spec.seeds), "unique_known_seed_snapshots")
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
    for seed in spec.seeds:
        sr = by_seed.get(seed)
        if sr is None:
            checks.check(all(episode_map[f"seed{seed}_{k}"]["status"] == "blocked" for k in KINDS), "unstarted_seed_all_blocked", seed)
            derived_seeds.append({"seed": seed, "complete": False, "evaluations": {}})
            continue
        checks.compare(sr["reset_seed"], spec.reset_seeds[seed], f"seed{seed}/fixed_reset_derivation")
        checks.check(type(sr["calibration_updates"]) is int and 0 <= sr["calibration_updates"] <= 300, "seed_update_cap", seed)
        qref, direction = sr.get("reference_q"), sr.get("direction")
        states, hashes, view_hashes, final_models, derived = {}, {}, {}, {}, {}
        prefix_reference, calibration_complete = None, {spec.calibration_schedule: False}
        if qref is not None:
            if not finite(qref):
                raise ValueError("Nonfinite reference.")
            positive, negative = ranges[joint_index][1]-qref, qref-ranges[joint_index][0]
            checks.compare(direction, 1 if positive >= negative else -1, f"seed{seed}/public_direction")
            checks.compare(sr["selection_record"], {"joint_index": joint_index, "joint_position_rad": qref,
                "lower_limit_rad": ranges[joint_index][0], "upper_limit_rad": ranges[joint_index][1],
                "positive_room_rad": positive, "negative_room_rad": negative, "direction": direction,
                "rule": "larger distance to the public joint limit; ties choose positive"}, f"seed{seed}/direction_record")
        for kind in KINDS:
            tid, is_cal = f"seed{seed}_{kind}", kind == "calibration"
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
            dependencies = [spec.calibration_schedule] if kind.startswith("prediction_") or kind == "learned_mpc" else []
            missing_dependencies = [d for d in dependencies if not calibration_complete[d]]
            if ep["status"] != "blocked":
                checks.check(not missing_dependencies, "failed_calibration_dependents_blocked", tid)
            elif ep.get("reason", {}).get("type") == "DependencyBlocked":
                checks.compare(ep["reason"].get("dependencies"), [f"seed{seed}_calibration" for d in missing_dependencies], tid+"/dependencies")
                checks.check(bool(missing_dependencies), "dependency_block_requires_failure", tid)
                checks.check(kind not in ("nominal_mpc", "tuned_pd", "zero_torque"), "baseline_independent_of_fit", tid)
            prefix = [trace_payload(r) for r in regular if r["step_index"] < 100]
            if len(prefix) == 100:
                if prefix_reference is None:
                    prefix_reference = prefix
                else:
                    checks.check(prefix == prefix_reference, "exact_paid_prefix_all_seven_trials", tid)
            scores_q, scores_v, tracking = {}, {}, []
            observed_effort = {p: new_effort() for p in PHASES}
            phase_rows, phase_physics = Counter(), Counter()
            phase_risk, risk_full = {p: new_risk() for p in PHASES}, new_risk()
            previous_after, previous_request = None, 0.
            counters = {"physics": 0}
            planner_calls = fallbacks = saturated = 0
            before_views, before_hashes = dict(view_hashes), dict(hashes)
            partial_target_errors = []
            last_study = None
            last_environment_stop = False

            def establish_models():
                if qref is None:
                    raise ValueError("Active trial lacks native reference.")
                if "nominal" not in hashes:
                    nominal = initial_state("linear4")
                    hashes["nominal"] = state_hash(qref, nominal)
                    view_hashes["nominal_mpc"] = digest(integration_spec(hashes["nominal"]))
                    final_models["nominal_mpc"] = INITIAL["linear4"]
                if is_cal:
                    for structure in ("hinge5",):
                        name = plan["calibration_schedule"]+"_"+structure
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
                    "calibration_dose": plan["calibration_dose"], "calibration_schedule": plan["calibration_schedule"], "model_structure": plan["model_structure"],
                    "integration": INTEGRATION, "shared_transition_id": tid+":"+str(index)}, loc+"/identity")
                checks.compare(row.get("pd_gains"), spec.pd_gains if kind == "tuned_pd" else None, loc+"/frozen_row_pd_gains")
                n = verify_transition(row, previous_after, counters, ranges, checks, loc, joint_index=joint_index)
                condition = normalize_study_row(row, qref, checks, loc, joint_index=joint_index)
                last_study = row.get("study_abort") if condition["triggered"] else last_study
                last_environment_stop = bool(row["diagnostics"]["terminated"]) or last_environment_stop
                checks.check(not condition["triggered"] or index == len(regular)-1 and ep["status"] in ("terminated", "exception"), "study_terminal_final_row", loc)
                previous_after = row["observation_after"]
                phase_rows[phase] += 1
                phase_physics[phase] += n
                record_risk(risk_full, row, ranges, joint_index=joint_index)
                record_risk(phase_risk[phase], row, ranges, joint_index=joint_index)
                checks.check(not row["diagnostics"]["terminated"] or index == len(regular)-1 and ep["status"] in ("terminated", "exception"), "terminal_final_row", loc)
                q, v = (row["observation_before"][key][joint_index] for key in ("joint_position", "joint_velocity"))
                next_q, next_v = (row["observation_after"][key][joint_index] for key in ("joint_position", "joint_velocity"))
                u, history = row["requested_torque"][joint_index], row["diagnostics"]["applied_torque_history"]
                effort = observed_effort[phase]
                effort[EFFORT_KEYS[0]] += abs(u)*n*PHYSICS_DT
                effort[EFFORT_KEYS[1]] += u*u*n*PHYSICS_DT
                effort[EFFORT_KEYS[2]] += sum(abs(a[joint_index]) for a in history)*PHYSICS_DT
                effort[EFFORT_KEYS[3]] += sum(a[joint_index]*a[joint_index] for a in history)*PHYSICS_DT
                if row["target_q"] is not None and n != 10:
                    partial_target_errors.append(next_q-row["target_q"])
                checks.compare(row.get("partial_interval_target_error_rad"), None if row["target_q"] is None or n == 10 else next_q-row["target_q"], loc+"/partial_target_error")
                if index < 100:
                    checks.compare(row, {"requested_torque": [0.]*8, "predicted_next_qv": {},
                        "model_update": None, "target_q": None, "planner_decision": None, "raw_pd_torque_nm": None}, loc+"/paid_prefix")
                    continue
                if index == 100:
                    checks.compare(q, qref, loc+"/prefix_reference")
                    establish_models()
                    if not is_cal:
                        before_hashes, before_views = dict(hashes), dict(view_hashes)
                active = index-100
                if phase in ("calibration", "prediction"):
                    if is_cal:
                        prescribed = calibration_request(plan["calibration_schedule"], active, direction)
                    else:
                        slot, amplitude = active % 20, PREDICTION_AMPLITUDES[kind.split("_")[1]][active//20]
                        prescribed = direction*(amplitude if slot < 7 else -amplitude if 10 <= slot < 17 else 0.)
                    checks.compare(row, {"requested_torque": [prescribed if j == joint_index else 0. for j in range(8)], "target_q": None, "planner_decision": None, "raw_pd_torque_nm": None}, loc+"/fixed_schedule")
                else:
                    target = qref+direction*(.04 if active < 100 else .08)
                    checks.compare(row["target_q"], target, loc+"/current_target")
                    checks.check(ranges[joint_index][0]+.03 <= target <= ranges[joint_index][1]-.03, "public_target_interior", loc)
                    if kind in MPC_KINDS:
                        decision = replay_mpc(final_models[kind], qref, q, v, target, previous_request, ranges[joint_index])
                        checks.compare(row["planner_decision"], decision, loc+"/all_candidate_planning")
                        checks.compare(u, decision["torque"], loc+"/selected_request")
                        planner_calls += decision["mathematical_prediction_calls"]
                        fallbacks += int(decision["fallback"])
                        checks.compare(row.get("raw_pd_torque_nm"), None, loc+"/not_pd")
                    elif kind == "tuned_pd":
                        raw = spec.pd_gains["kp"]*(target-q)-spec.pd_gains["kd"]*v
                        checks.compare(row.get("raw_pd_torque_nm"), raw, loc+"/raw_native_pd")
                        checks.compare(u, max(-.5, min(.5, raw)), loc+"/continuous_pd_permission")
                        checks.compare(row["planner_decision"], None, loc+"/pd_no_mpc")
                    else:
                        checks.compare(u, 0., loc+"/fixed_zero_request")
                        checks.compare(row["planner_decision"], None, loc+"/zero_no_mpc")
                        checks.compare(row.get("raw_pd_torque_nm"), None, loc+"/zero_no_pd")
                    if n == 10:
                        tracking.append(next_q-target)
                        saturated += int(abs(u) == .5)
                if is_cal:
                    predictions = {s: predict(states[plan["calibration_schedule"]+"_"+s]["observed_theta"], qref, q, v, u) for s in ("hinge5",)}
                else:
                    predictions = {name: predict(theta, qref, q, v, u) for name, theta in final_models.items()}
                    predictions["persistence"] = (q+DT*v, v)
                checks.check(set(row["predicted_next_qv"]) == set(predictions), "exact_prediction_model_set", loc)
                checks.compare(row["predicted_next_qv"], predictions, loc+"/preupdate_predictions")
                for name in predictions:
                    scores_q.setdefault(name, [])
                    scores_v.setdefault(name, [])
                for name, (pq, pv) in (predictions.items() if n == 10 else []):
                    scores_q.setdefault(name, []).append(next_q-pq)
                    scores_v.setdefault(name, []).append(next_v-pv)
                if is_cal:
                    checks.check(set(row["model_update"]) == {"hinge5"}, "single_hinge_update_record", loc)
                    for structure in ("hinge5",):
                        state, item = states[plan["calibration_schedule"]+"_"+structure], row["model_update"][structure]
                        if n == 10:
                            replay_update(item, row, structure, state, qref, checks, loc+"/"+structure, joint_index=joint_index)
                        else:
                            checks.compare(item, {"updated": False, "phase": "partial_calibration_interval", "executed_substeps": n,
                                "update_count": state["updates"], "model_id": plan["calibration_schedule"]+"_"+structure,
                                "shared_transition_id": row["shared_transition_id"]}, loc+"/no_partial_update")
                else:
                    checks.compare(row["model_update"], None, loc+"/evaluation_no_update")
                previous_request = u
            # Exceptional endpoints are not regular rows or rollout windows.
            # Successful atomic updates may nonetheless be fully reconstructible.
            for exception in exceptions:
                if (exception.get("observation_after") is not None and exception.get("step_index") is not None
                    and (any(r["step_index"] == exception["step_index"] for r in regular) or (ep["control_steps"] > len(regular) and exception.get("unreturned_physics_steps", 0) == 0))):
                    exc_condition = normalize_study_row(exception, qref, checks, tid+"/exception_monitor", joint_index=joint_index)
                    if exc_condition["triggered"]:
                        last_study = exception.get("study_abort")
                if (is_cal and exception.get("step_index", -1) is not None and exception["step_index"] >= 100
                    and plan["calibration_schedule"]+"_hinge5" in sr.get("initial_models", {})):
                    checks.check(set(exception.get("partial_model_snapshots", {})) == {"hinge5"}, "exception_snapshot_exact_structure_set", tid)
                    establish_models()
                    checks.compare(exception["shared_transition_id"], tid+":"+str(exception["step_index"]), tid+"/exception_id")
                    native_endpoint = exception.get("observation_after")
                    update_items = exception.get("model_update") or {}
                    for structure in ("hinge5",):
                        state = states[plan["calibration_schedule"]+"_"+structure]
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
                                replay_update(item, exception, structure, state, qref, checks, tid+"/exception/"+structure, exception=True, joint_index=joint_index)
                        snapshot = exception.get("partial_model_snapshots", {}).get(structure)
                        checks.check(snapshot is not None, "exception_active_model_snapshot_required", tid+"/"+structure)
                        if snapshot is not None:
                            # A throw after atomic update but before its return can
                            # be recovered from the raw endpoint and saved snapshot.
                            if (not already_recorded and snapshot["update_count"] == state["updates"]+1 and item is None
                                    and native_endpoint is not None and full_exception_interval):
                                q, v = (exception["observation_before"][k][joint_index] for k in ("joint_position", "joint_velocity"))
                                u, nv = exception["requested_torque"][joint_index], native_endpoint["joint_velocity"][joint_index]
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
                and all(not stop_flags(r)["any"] and r["diagnostics"]["executed_substeps"] == 10 for r in regular))
            checks.check(ep["status"] != "completed" or complete, "claimed_complete_full_valid_trajectory", tid)
            if ep["status"] == "blocked":
                checks.check(not rows and ep["control_calls_attempted"] == ep["control_steps"] == ep["physics_steps"] == 0, "blocked_zero_physical_cost", tid)
            if is_cal:
                dose = plan["calibration_schedule"]
                calibration_complete[dose] = complete
                checks.compare(sr["calibration_completed"][dose], complete, tid+"/calibration_complete")
                for structure in ("hinge5",):
                    name = dose+"_"+structure
                    if name in states:
                        saved = sr["calibration_models"][dose][structure]
                        reconstructed = verify_snapshot(saved, states[name], qref, checks, tid+"/final/"+structure)
                        checks.compare(sr["learned_models"][name], saved, tid+"/consistent_frozen_clone/"+structure)
                        hashes[name] = saved["parameter_fingerprint"]
                        if complete:
                            checks.check(reconstructed, "complete_model_fully_replayed", tid+"/"+structure)
                            checks.compare(states[name]["updates"], 300, tid+"/fixed_updates/"+structure)
                            view_hashes["learned_mpc"] = digest(integration_spec(hashes[name]))
                            final_models["learned_mpc"] = saved["coefficients"]
                    else:
                        checks.check(structure not in sr["calibration_models"].get(dose, {}), "no_model_before_active", tid)
            effort_audits = {}
            if ep["status"] != "blocked":
                checks.compare(ep.get("study_abort"), last_study, tid+"/study_abort_outcome")
                checks.compare(ev.get("study_abort"), ep.get("study_abort"), tid+"/study_abort_evaluation")
                checks.compare(ev.get("environment_terminated"), ep.get("environment_terminated"), tid+"/environment_stop_evaluation")
                checks.check(type(ep.get("environment_terminated")) is bool or ep["status"] == "exception" and ep.get("environment_terminated") is None, "environment_stop_boolean", tid)
                if not exceptions:
                    checks.compare(ep.get("environment_terminated"), last_environment_stop, tid+"/environment_native_stop")
                    checks.compare(ep.get("environment_stop_reason"), regular[-1]["diagnostics"].get("reason") if regular else None, tid+"/environment_native_reason")
                if ep.get("environment_terminated"):
                    checks.compare(ep.get("reason"), ep.get("environment_stop_reason"), tid+"/environment_reason_precedence")
                elif last_study is not None:
                    checks.compare(ep.get("reason"), last_study, tid+"/study_reason_precedence")
                checks.compare(ev.get("partial_interval_target_errors_rad"), partial_target_errors, tid+"/partial_errors")
                checks.compare(ev.get("partial_interval_target_error_count"), len(partial_target_errors), tid+"/partial_count")
            if ep["status"] != "blocked":
                checks.compare(ev["completed"], complete, tid+"/completion")
                checks.compare(ev["status"], ep["status"], tid+"/status")
                if missing_rows == 0 and missing_physics == 0 and not exceptions:
                    checks.compare(ev, {"tracking_rmse_rad": rmse(tracking), "metric_control_step_count": len(tracking),
                        "position_prediction_rmse": {n: rmse(v) for n, v in scores_q.items()},
                        "velocity_prediction_rmse": {n: rmse(v) for n, v in scores_v.items()}, "saturated_control_steps": saturated, "metric_prediction_step_count": {n: len(v) for n, v in scores_v.items()}}, tid+"/reconstructed_metrics")
                    checks.check(ep["environment_fingerprint_before"] == ep["environment_fingerprint_after"], "fixed_physical_parameters", tid)
                for phase in PHASES:
                    effort_audits[phase] = reconcile_effort(ev, phase, observed_effort[phase], ep["phase_budgets"][phase]["physics_steps"],
                        phase_physics[phase], exceptions, checks, tid+"/effort/"+phase, joint_index=joint_index)
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
                    and failed_attempts <= attempts <= (200 if kind in MPC_KINDS else 0), "planner_attempt_cap", tid)
                checks.compare(decisions, attempts-failed_attempts, tid+"/planner_decisions")
                checks.compare(ev["mathematical_prediction_calls_complete"], failed_attempts == 0, tid+"/mathcall_complete")
                checks.compare(ev["mathematical_prediction_calls_is_lower_bound"], failed_attempts > 0, tid+"/mathcall_lower_bound")
                checks.check(decisions >= (len(tracking) if kind in MPC_KINDS else 0) and planner_calls <= ev["mathematical_prediction_calls"] <= 135*decisions,
                             "paid_planner_cost_retained", tid)
                checks.check(finite(ev["controller_seconds_total"]) and ev["controller_seconds_total"] >= 0, "nonnegative_planning_time", tid)
                if complete:
                    checks.compare(ev["mathematical_prediction_calls"], planner_calls, tid+"/mathcalls")
                    checks.compare(ev["planner_fallbacks"], fallbacks, tid+"/fallbacks")
                    checks.compare(decisions, 200 if kind in MPC_KINDS else 0, tid+"/decision_count")
                checks.compare(ev["models_before"], None if is_cal else before_hashes, tid+"/model_hashes_before")
                checks.compare(ev["models_after"], hashes, tid+"/model_hashes_after")
                checks.compare(ev["integration_models_before"], before_views, tid+"/view_hashes_before")
                checks.compare(ev["integration_models_after"], view_hashes, tid+"/view_hashes_after")
                if kind in MPC_KINDS and ev["planner_spec"] is not None:
                    fingerprint = hashes["nominal" if kind == "nominal_mpc" else spec.calibration_schedule+"_hinge5"]
                    checks.compare(ev["planner_spec"], {"config": MPC_CONFIG, "qref_rad": qref, "joint_range_rad": ranges[joint_index],
                        "candidates_nm": [-.5+i*.125 for i in range(9)], "physical_queries": 0,
                        "forecast_bounds_rad": [max(qref-.15, ranges[joint_index][0]-.03), min(qref+.15, ranges[joint_index][1]+.03)],
                        "target_bounds_rad": [max(qref-.15, ranges[joint_index][0]+.03), min(qref+.15, ranges[joint_index][1]-.03)],
                        "integration": integration_spec(fingerprint), "integration_fingerprint": digest(integration_spec(fingerprint))}, tid+"/fixed_planner_spec")
            if ep["status"] != "blocked":
                pd_attempts, pd_failed, pd_success = (ev[k] for k in ("pd_calls_attempted", "failed_pd_attempts", "pd_calls_successful"))
                checks.check(all(type(x) is int and x >= 0 for x in (pd_attempts, pd_failed, pd_success)) and pd_failed <= pd_attempts <= (200 if kind == "tuned_pd" else 0), "pd_attempt_cap", tid)
                checks.compare(pd_success, pd_attempts-pd_failed, tid+"/pd_success_cost")
                checks.check(finite(ev["pd_seconds_total"]) and ev["pd_seconds_total"] >= 0, "finite_pd_seconds", tid)
                checks.compare(ev["controller_spec"], {"method": "tuned_pd", "kp": spec.pd_gains["kp"], "kd": spec.pd_gains["kd"], "body_model_input": False, "permission_nm": .5} if kind == "tuned_pd" else {"method": "zero_torque"} if kind == "zero_torque" else None, tid+"/fixed_controller_spec")
                if kind not in MPC_KINDS:
                    checks.compare(ev["planner_spec"], None, tid+"/non_mpc_no_planner")
                if complete:
                    checks.compare(pd_success, 200 if kind == "tuned_pd" else 0, tid+"/complete_pd_calls")
            control_effort = effort_audits.get("control", {"independent_effort": new_effort(), "actual_effort_reconstruction_complete": False})
            derived[kind] = {"completed": complete, "eligible": complete and checks.failed == failure_start, "status": ep["status"],
                "study_aborted": last_study is not None, "environment_terminated": ep.get("environment_terminated") is True,
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
                "planner_cost_reconstruction_complete": bool(ev) and ev.get("failed_planner_attempts") == 0 and ev.get("planner_decision_count") == (len(tracking) if kind in MPC_KINDS else 0),
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
            base = sr["nominal_model"] if name == "nominal_mpc" else sr["learned_models"][spec.calibration_schedule+"_hinge5"]
            checks.compare(saved, {**base, "integration": integration_spec(base["parameter_fingerprint"]),
                "integration_fingerprint": fingerprint, "frozen_view": True}, f"seed{seed}/frozen_view/"+name)
        for kind in KINDS:
            regular = [r for r in grouped.get(f"seed{seed}_{kind}", []) if "collector_exception" not in r]
            derived[kind]["conditional_metrics"] = conditional_metrics(regular, joint_index=joint_index)
            if kind in CONTROL_KINDS:
                derived[kind]["tail_tracking"] = control_tail_metrics(regular, joint_index=joint_index)
            if qref is not None:
                diagnostic_models = {"learned_mpc": s["coefficients"] for n, s in sr["learned_models"].items()}
                diagnostic_models["nominal_mpc"] = INITIAL["linear4"]
                derived[kind]["free_rollouts"] = diagnose_windows(regular, duration(kind), qref, diagnostic_models, joint_index=joint_index)
                derived[kind]["final_model_calibration_in_sample"] = kind == "calibration"
                derived[kind]["rollout_model_in_sample_on_this_calibration"] = {
                    n: kind == "calibration" and n == "learned_mpc" for n in diagnostic_models}
                if kind in CONTROL_KINDS:
                    derived[kind]["state_coverage"] = state_coverage(
                        [r for r in grouped.get(f"seed{seed}_calibration", []) if "collector_exception" not in r], regular, qref, joint_index=joint_index)
        replayed = sum(s["updates"] for s in states.values())
        saved_total = sum(s["update_count"] for s in sr["learned_models"].values())
        checks.check(set(sr["learned_models"]) == set(states) and set(sr["initial_models"]) == set(states), "exact_created_model_set", seed)
        checks.compare(sr["calibration_updates"], saved_total, f"seed{seed}/saved_update_cost")
        checks.check(replayed <= saved_total <= 300, "independent_update_cost_bounds", seed)
        derived_seeds.append({"seed": seed, "complete": all(v["eligible"] for v in derived.values()),
            "model_updates": saved_total, "independently_replayed_updates": replayed,
            "exception_snapshot_replayed_updates": sum(s["exception_replayed_updates"] for s in states.values()),
            "unreconstructed_updates": saved_total-replayed,
            "models": {n: {"reported_updates": sr["learned_models"][n]["update_count"], "replayed_updates": s["updates"],
                "exception_replayed_updates": s["exception_replayed_updates"], "unreconstructed_updates": s["unreconstructed_updates"]} for n, s in states.items()},
            "evaluations": derived})
    for key in ("control_calls_attempted", "control_steps", "physics_steps"):
        checks.compare(metadata[key], sum(ep[key] for ep in episodes), "metadata_"+key)
    checks.check(metadata["control_calls_attempted"] <= 6000 and metadata["control_steps"] <= 6000
        and metadata["physics_steps"] <= 60000 and metadata["model_updates"] <= 900, "frozen_batch_budget_cap")
    checks.compare(metadata["model_updates"], sum(sr["calibration_updates"] for sr in results), "metadata_update_budget")
    for status in ("completed", "terminated", "exception", "blocked", "planned"):
        key = "unprocessed_trials" if status == "planned" else status+"_trials"
        checks.compare(metadata[key], sum(ep["status"] == status for ep in episodes), "metadata_"+key)
    checks.compare(metadata["all_trials_successful"], all(ep["status"] == "completed" for ep in episodes), "all_outcomes_success")
    checks.compare(metadata["failed_trials"], metadata["exception_trials"]+metadata["terminated_trials"], "all_failed_outcomes")
    checks.compare(metadata["skipped_trials"], metadata["blocked_trials"], "all_blocked_outcomes")
    checks.compare(metadata["complete"], metadata["archive_status"] == "complete", "archive_completion_not_adoption")
    checks.check(all(file_hash(path/name) == expected for name, expected in input_hashes.items()), "input_archive_unchanged")
    return {"path": str(path), "source_commit": metadata["source_commit"], "split": spec.split, "input_hashes": input_hashes,
        "seeds": derived_seeds, "budget": {k: metadata[k] for k in ("control_calls_attempted", "control_steps", "physics_steps", "model_updates")},
        "phase_budget": {p: {k: sum(e["phase_budgets"][p][k] for e in episodes) for k in ("control_calls_attempted", "control_steps", "physics_steps")} for p in PHASES},
        "physical_calibration_transfers": sum(e["phase_budgets"]["calibration"]["control_steps"] for e in episodes),
        "sample_semantics": "Each complete calibration transition supplies one single-model RLS update; replay audits add no physical samples.",
        "stops": {"study": sum(e.get("study_abort") is not None for e in episodes), "environment": sum(e.get("environment_terminated") is True for e in episodes), "both": sum(e.get("study_abort") is not None and e.get("environment_terminated") is True for e in episodes)},
        "collector_timing": {k: metadata[k] for k in ("wall_seconds", "cpu_seconds", "cpu_seconds_scope")}}, grouped, metadata


def pd_source_matches(metadata, spec):
    if not spec.pd_selection_source:
        return True
    actual = metadata.get("pd_selection_source")
    expected = dict(spec.pd_selection_source)
    return (type(actual) is dict and actual == expected
            and all(type(actual[key]) is type(value) for key, value in expected.items()))


def require_final(path, *, spec=SHOULDER_FINAL_SPEC):
    """Reject undeclared scope/gains before any ZIP or trace is opened."""
    if type(spec) is not AuditSpec:
        raise ValueError("Explicit immutable AuditSpec required.")
    spec.require_frozen()
    metadata = load_json(Path(path)/"metadata.json")
    expected_suite = {"pose": spec.pose, "joint": spec.joint_index,
        "seeds": list(spec.seeds), "split": spec.split,
        "pd_kp": spec.pd_kp, "pd_kd": spec.pd_kd}
    gain_records = (metadata.get("pd_gains", {}), metadata.get("suite_spec", {}))
    gain_numbers_valid = (all(isinstance(record, dict) for record in gain_records)
        and all(finite(gain_records[0].get(key)) for key in ("kp", "kd"))
        and all(finite(gain_records[1].get(key)) for key in ("pd_kp", "pd_kd")))
    if (metadata.get("suite") != spec.suite or metadata.get("split") != spec.split
        or metadata.get("seeds") != list(spec.seeds)
        or any(type(seed) is not int for seed in metadata.get("seeds", []))
        or metadata.get("pose") != spec.pose
        or type(metadata.get("joint_index")) is not int
        or metadata["joint_index"] != spec.joint_index
        or not gain_numbers_valid or metadata.get("suite_spec") != expected_suite
        or type(metadata.get("suite_spec", {}).get("joint")) is not int
        or metadata.get("calibration_schedule") != spec.calibration_schedule
        or metadata.get("pd_gains") != spec.pd_gains
        or not pd_source_matches(metadata, spec)
        or not isinstance(metadata.get("protocol"), dict)
        or metadata["protocol"].get("path") != spec.protocol):
        raise ValueError("Only the explicitly declared frozen suite, protocol and gains are accepted.")
    return metadata


def planned_matrix(*, spec=SHOULDER_FINAL_SPEC):
    return [{"trial_id": f"seed{seed}_{kind}", "seed": seed, "kind": kind,
        "model_scope": "nominal" if kind == "nominal_mpc" else "learned" if kind == "learned_mpc" else "controller_only" if kind in ("tuned_pd", "zero_torque") else "shared",
        "calibration_dose": "old" if kind in ("calibration", "learned_mpc") else None,
        "calibration_schedule": spec.calibration_schedule if kind in ("calibration", "learned_mpc") else None,
        "model_structure": "hinge5" if kind in ("calibration", "learned_mpc") else "linear4" if kind == "nominal_mpc" else None,
        "integration": INTEGRATION, "maximum_control_steps": 100+duration(kind)} for seed in spec.seeds for kind in KINDS]


def complete_trials(seeds, kinds, *, spec=SHOULDER_FINAL_SPEC):
    unique = len(seeds) == 3 and all(type(r.get("seed")) is int for r in seeds) and {r["seed"] for r in seeds} == set(spec.seeds)
    return unique and all(all(trial_is_complete(r.get("evaluations", {}).get(k, {})) for k in kinds) for r in seeds)


def model_contribution_gate(seeds, *, spec=SHOULDER_FINAL_SPEC):
    complete = complete_trials(seeds, MODEL_REQUIRED, spec=spec)
    pairs = []
    for row in seeds:
        ev = row.get("evaluations", {})
        nominal, learned = ev.get("nominal_mpc", {}), ev.get("learned_mpc", {})
        a, b = nominal.get("tracking_rmse_rad"), learned.get("tracking_rmse_rad")
        valid = complete and finite(a) and finite(b) and a >= 0 and b >= 0
        predictions = {}
        for kind in ("prediction_low", "prediction_full"):
            values = ev.get(kind, {}).get("velocity_prediction_rmse", {})
            n, l = values.get("nominal_mpc"), values.get("learned_mpc")
            available = finite(n) and finite(l) and n >= 0 and l >= 0 and trial_is_complete(ev.get(kind, {}))
            predictions[kind] = {"available": available, "nominal_velocity_rmse": n, "learned_velocity_rmse": l,
                "relative_improvement": None if not available or n == 0 else 1.-l/n,
                "passed": available and l <= .8*n}
            valid = valid and available
        pairs.append({"seed": row["seed"], "complete_pair": valid, "nominal_tracking_rmse_rad": a, "learned_tracking_rmse_rad": b,
            "strict_tracking_improvement": valid and b < a, "prediction_gates": predictions})
    evaluated = complete and all(p["complete_pair"] for p in pairs)
    nm = sum(p["nominal_tracking_rmse_rad"] for p in pairs)/3 if evaluated else None
    lm = sum(p["learned_tracking_rmse_rad"] for p in pairs)/3 if evaluated else None
    improvement = 1.-lm/nm if evaluated and nm > 0 else None
    passed = evaluated and all(p["strict_tracking_improvement"] and all(g["passed"] for g in p["prediction_gates"].values()) for p in pairs) and improvement is not None and improvement >= .20
    return {"evaluated": evaluated, "passed": passed, "all_five_required_trials_complete": complete, "per_seed": pairs,
        "nominal_raw_tracking_mean": nm, "learned_raw_tracking_mean": lm, "tracking_mean_improvement": improvement,
        "claim_boundary": "Specified local v prediction and same-MPC body-model contribution; no energy, safety, all-state prediction or task-skill claim."}


def classical_comparison_gate(seeds, contribution=None, *, spec=SHOULDER_FINAL_SPEC):
    contribution = model_contribution_gate(seeds, spec=spec) if contribution is None else contribution
    complete = complete_trials(seeds, (*MODEL_REQUIRED, "tuned_pd"), spec=spec)
    pairs = []
    for row in seeds:
        ev = row.get("evaluations", {})
        learned, pd = ev.get("learned_mpc", {}), ev.get("tuned_pd", {})
        a, b = pd.get("tracking_rmse_rad"), learned.get("tracking_rmse_rad")
        valid = complete and finite(a) and finite(b) and a >= 0 and b >= 0 and all(
            t.get("actual_effort_complete") is True and all(finite(t.get("control_effort", {}).get(k)) and t["control_effort"][k] >= 0 for k in EFFORT_KEYS[2:]) for t in (learned, pd))
        pairs.append({"seed": row["seed"], "complete_pair": valid, "pd_tracking_rmse_rad": a, "learned_tracking_rmse_rad": b,
            "tracking_non_worse": valid and b <= a, "pd_actual_effort": pd.get("control_effort"), "learned_actual_effort": learned.get("control_effort")})
    evaluated = complete and all(p["complete_pair"] for p in pairs)
    pm = sum(p["pd_tracking_rmse_rad"] for p in pairs)/3 if evaluated else None
    lm = sum(p["learned_tracking_rmse_rad"] for p in pairs)/3 if evaluated else None
    improvement = 1.-lm/pm if evaluated and pm > 0 else None
    efforts = {}
    for key in EFFORT_KEYS[2:]:
        a = sum(p["pd_actual_effort"][key] for p in pairs)/3 if evaluated else None
        b = sum(p["learned_actual_effort"][key] for p in pairs)/3 if evaluated else None
        efforts[key] = {"pd_mean": a, "learned_mean": b, "relative_increase": ratio_change(b,a) if evaluated else None,
            "passed": evaluated and b <= 1.05*a}
    passed = contribution["passed"] and evaluated and all(p["tracking_non_worse"] for p in pairs) and improvement is not None and improvement >= .05 and all(g["passed"] for g in efforts.values())
    return {"evaluated": evaluated, "passed": passed, "same_mpc_contribution_passed": contribution["passed"],
        "all_six_required_trials_complete": complete, "per_seed": pairs, "pd_raw_tracking_mean": pm, "learned_raw_tracking_mean": lm,
        "tracking_mean_improvement": improvement, "actual_effort_gates": efforts}


def final_gates(seeds, *, spec=SHOULDER_FINAL_SPEC):
    model = model_contribution_gate(seeds, spec=spec)
    classical = classical_comparison_gate(seeds, model, spec=spec)
    return {"model_contribution_gate": model, "classical_comparison_gate": classical,
        "complete_matrix": complete_trials(seeds, KINDS, spec=spec), "claim_boundary": spec.claim_boundary}


def audit(path, *, git_root=ROOT, spec=SHOULDER_FINAL_SPEC):
    wall_start, cpu_start = time.perf_counter(), time.process_time()
    checks, result, reported_budget = Checks(), None, None
    try:
        initial = require_final(path, spec=spec)
        reported_budget = {k: initial.get(k) for k in ("control_calls_attempted", "control_steps", "physics_steps", "model_updates")}
        result, _, metadata = audit_archive(path, checks, git_root, spec=spec)
    except (OSError, ValueError, KeyError, TypeError, IndexError, AttributeError, OverflowError, zipfile.BadZipFile, ET.ParseError) as error:
        checks.check(False, "archive_schema_or_read_error", {"type": type(error).__name__, "message": str(error)})
    gates = final_gates([] if result is None else result["seeds"], spec=spec)
    gates["data_consistency_verified"] = checks.failed == 0
    for key in ("model_contribution_gate", "classical_comparison_gate"):
        gates[key]["validated_pass"] = gates[key]["passed"] and checks.failed == 0 and git_root is not None
    return {"schema_version": 1, "created_at_utc": datetime.now(timezone.utc).isoformat(), "purpose": __doc__,
        "audit_script_sha256": file_hash(Path(__file__)), "audit_spec": spec.record(),
        "checks": checks.count, "failed": checks.failed,
        "maximum_recomputation_difference": checks.maximum_difference, "violations": checks.violations, "archive": result,
        "final_gates": gates, "reported_paid_budget_if_replay_incomplete": reported_budget,
        "execution": {"wall_seconds": time.perf_counter()-wall_start, "cpu_seconds": time.process_time()-cpu_start,
            "timing_scope": "audit entry through report assembly; excludes imports/final JSON writing", "python": sys.version,
            "platform": platform.platform(), "third_party_dependencies": [], "source_git_verification_enabled": git_root is not None,
            "physical_simulation_calls": 0, "model_parameter_updates": 0, "replayed_updates_are_frozen_log_audits": True}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--suite", choices=("shoulder_final", "elbow_development"), default="shoulder_final")
    args = parser.parse_args()
    spec = {"shoulder_final": SHOULDER_FINAL_SPEC, "elbow_development": ELBOW_DEVELOPMENT_SPEC}[args.suite]
    try:
        output = validate_output_path(args.output, [args.archive])
        require_final(args.archive, spec=spec)
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.error(str(error))
    report = audit(args.archive, spec=spec)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"report": str(output), "checks": report["checks"], "failed": report["failed"], "gates": report["final_gates"]}))
    return 1 if report["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
