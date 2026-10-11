"""Standard-library offline diagnostics of fixed joint pulses and shared zeros.

No fitting, simulator calls, policy updates, or inference of a body model. The
1 mrad measurement gate is a frozen simulation observation criterion, not a
hardware safety threshold or proof of skill acquisition.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import gzip
import hashlib
import json
import math
from pathlib import Path
import platform
import sys


JOINT_NAMES = ("left_shoulder", "left_elbow", "right_shoulder", "right_elbow",
               "left_hip", "left_knee", "right_hip", "right_knee")
PHASES = ("prefix", "probe", "recovery")
AMPLITUDES = (.125, .25, .5)
MEASUREMENT_THRESHOLD_RAD = .001
NATIVE_FIELDS = {"joint_position": 8, "joint_velocity": 8, "imu_gyro": 3, "imu_acceleration": 3}


def _hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _finite_tree(value):
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("nonfinite numeric value")
    if isinstance(value, dict):
        for item in value.values():
            _finite_tree(item)
    elif isinstance(value, list):
        for item in value:
            _finite_tree(item)


def _vector(value, length):
    if not isinstance(value, list) or len(value) != length or any(
        isinstance(item, bool) or not isinstance(item, (int, float)) or not math.isfinite(item) for item in value
    ):
        raise ValueError(f"expected {length} finite measurements")
    return value


def _count(value):
    if type(value) is not int or value < 0:
        raise ValueError("expected a nonnegative integer count")
    return value


def _rms_vectors(values):
    if not values:
        return {"per_component": None, "all_components": None}
    width = len(values[0])
    squared = [math.fsum(row[j] ** 2 for row in values) for j in range(width)]
    return {"per_component": [math.sqrt(item / len(values)) for item in squared],
            "all_components": math.sqrt(math.fsum(squared) / (width * len(values)))}


def _empty_phase():
    return {"control_rows": 0, "physics_samples": 0, "force_peak": None,
            "energy_peak": None, "minimum_distance": None, "force_sum": 0.,
            "requested_square": [0.] * 8, "accepted_square": [0.] * 8, "applied_square": [0.] * 8,
            "requested_signed": [0.] * 8, "requested_absolute": [0.] * 8,
            "accepted_signed": [0.] * 8, "accepted_absolute": [0.] * 8,
            "applied_signed": [0.] * 8, "applied_absolute": [0.] * 8,
            "nonzero_requested": [0] * 8, "blocked_requested": [0] * 8,
            "native": {name: [] for name in NATIVE_FIELDS}, "first_before": None,
            "last_after": None, "endpoint_times": []}


def _phase_summary(state, physics_dt):
    n = state["physics_samples"]
    requested_rms = [math.sqrt(value / n) for value in state["requested_square"]] if n else None
    accepted_rms = [math.sqrt(value / n) for value in state["accepted_square"]] if n else None
    applied_rms = [math.sqrt(value / n) for value in state["applied_square"]] if n else None
    return {
        "control_rows": state["control_rows"], "physics_samples": n,
        "ground_normal_force_peak_n": state["force_peak"],
        "ground_normal_force_integral_ns": state["force_sum"] * physics_dt,
        "kinetic_energy_peak_j": state["energy_peak"],
        "minimum_contact_distance_m": state["minimum_distance"],
        "requested_torque_rms_nm_per_joint": requested_rms,
        "accepted_torque_rms_nm_per_joint": accepted_rms,
        "applied_torque_rms_nm_per_joint": applied_rms,
        "requested_signed_torque_integral_nms_per_joint": [item * physics_dt for item in state["requested_signed"]],
        "requested_absolute_torque_integral_nms_per_joint": [item * physics_dt for item in state["requested_absolute"]],
        "accepted_signed_torque_integral_nms_per_joint": [item * physics_dt for item in state["accepted_signed"]],
        "accepted_absolute_torque_integral_nms_per_joint": [item * physics_dt for item in state["accepted_absolute"]],
        "applied_signed_torque_integral_nms_per_joint": [item * physics_dt for item in state["applied_signed"]],
        "applied_absolute_torque_integral_nms_per_joint": [item * physics_dt for item in state["applied_absolute"]],
        "nonzero_requested_substeps_per_joint": state["nonzero_requested"],
        "blocked_nonzero_request_substeps_per_joint": state["blocked_requested"],
        "blocked_fraction_of_nonzero_requested_substeps_per_joint": [
            None if count == 0 else state["blocked_requested"][j] / count
            for j, count in enumerate(state["nonzero_requested"])
        ],
        "native_endpoint_rms": {name: _rms_vectors(values) for name, values in state["native"].items()},
    }


def _new_state(trial):
    return {"trial": trial, "rows": 0, "exception_rows": 0, "errors": [], "invalid_rows": [],
            "prefix_hash": hashlib.sha256(), "prefix_rows": 0,
            "prefix_fields": None,
            "physics_observed": 0, "phases": {phase: _empty_phase() for phase in PHASES},
            "previous_after": None}


def _consume(state, row, metadata):
    if "collector_exception" in row:
        state["exception_rows"] += 1
        return
    index = state["rows"]
    state["rows"] += 1
    diagnostic = row.get("diagnostics", {})
    if type(diagnostic.get("executed_substeps")) is int:
        state["physics_observed"] += diagnostic["executed_substeps"]
    if row.get("invalid_numeric_fields"):
        state["invalid_rows"].append({"control_index": index, "fields": row["invalid_numeric_fields"]})
        state["errors"].append(f"row {index}: invalid numeric markers")
        return
    try:
        _finite_tree(row)
        trial = state["trial"]
        for name in ("mode", "pose", "seed", "joint_index", "amplitude_nm"):
            if row[name] != trial[name]:
                raise ValueError("row/trial identity mismatch: " + name)
        prefix, pulse = metadata["prefix_steps"], metadata["pulse_steps"]
        expected = "prefix" if index < prefix else ("probe" if index < prefix + pulse else "recovery")
        if row["phase"] != expected:
            raise ValueError("phase differs from fixed schedule")
        if row["action_index"] != (index - prefix if expected == "probe" else None):
            raise ValueError("action index differs from fixed pulse schedule")
        observation, before = row["observation_after"], row["observation_before"]
        for name, width in NATIVE_FIELDS.items():
            _vector(observation[name], width)
            _vector(before[name], width)
        if state["previous_after"] is not None and before != state["previous_after"]:
            raise ValueError("native observation chain is discontinuous")
        state["previous_after"] = observation
        request = _vector(diagnostic["requested_torque"], 8)
        accepted = _vector(diagnostic["accepted_torque"], 8)
        command = [0.] * 8
        if expected == "probe" and trial["mode"] == "joint_probe":
            if trial["selected_direction"] not in (-1, 1):
                raise ValueError("missing frozen selected direction")
            command[trial["joint_index"]] = trial["selected_direction"] * trial["amplitude_nm"]
        if request != command:
            raise ValueError("requested torque differs from declared pulse or zero schedule")
        if accepted != request:
            raise ValueError("accepted command differs despite fixed in-range request")
        n = _count(diagnostic["executed_substeps"])
        if n > metadata["environment_config"]["control_substeps"]:
            raise ValueError("too many physics substeps")
        if not math.isclose(diagnostic["time"], state["physics_observed"] * metadata["environment_config"]["physics_dt"],
                            rel_tol=1e-12, abs_tol=1e-10):
            raise ValueError("endpoint time differs from executed physics exposure")
        history = diagnostic["applied_torque_history"]
        if not isinstance(history, list) or len(history) != n:
            raise ValueError("applied command history length mismatch")
        for values in history:
            _vector(values, 8)
            if any(value not in (0., request[j]) for j, value in enumerate(values)):
                raise ValueError("applied command differs from requested-or-shielded torque")
        forces = _vector(diagnostic["substep_ground_normal_forces"], n)
        energies = _vector(diagnostic["substep_kinetic_energies"], n)
        distances = _vector(diagnostic["substep_minimum_contact_distances"], n)
        if any(value < 0 for value in forces + energies):
            raise ValueError("negative force or kinetic energy")
        if (max(forces, default=0.) != diagnostic["peak_substep_ground_normal_force"]
                or max(energies, default=0.) != diagnostic["peak_substep_kinetic_energy"]
                or min(distances, default=0.) != diagnostic["minimum_substep_contact_distance"]
                or not math.isclose(math.fsum(forces) * metadata["environment_config"]["physics_dt"],
                                    diagnostic["ground_normal_impulse_ns"], rel_tol=1e-12, abs_tol=1e-10)):
            raise ValueError("substep scalar summaries do not match samples")
        phase = state["phases"][expected]
        phase["control_rows"] += 1
        phase["physics_samples"] += n
        phase["first_before"] = before if phase["first_before"] is None else phase["first_before"]
        phase["last_after"] = observation
        phase["endpoint_times"].append(diagnostic["time"])
        for name in NATIVE_FIELDS:
            phase["native"][name].append(observation[name])
        if n:
            phase["force_peak"] = max(max(forces), phase["force_peak"] or 0.)
            phase["energy_peak"] = max(max(energies), phase["energy_peak"] or 0.)
            phase["minimum_distance"] = min(min(distances), phase["minimum_distance"] if phase["minimum_distance"] is not None else min(distances))
        phase["force_sum"] += math.fsum(forces)
        for j in range(8):
            phase["requested_square"][j] += n * request[j] ** 2
            phase["accepted_square"][j] += n * accepted[j] ** 2
            phase["requested_signed"][j] += n * request[j]
            phase["requested_absolute"][j] += n * abs(request[j])
            phase["accepted_signed"][j] += n * accepted[j]
            phase["accepted_absolute"][j] += n * abs(accepted[j])
            phase["applied_square"][j] += math.fsum(values[j] ** 2 for values in history)
            phase["applied_signed"][j] += math.fsum(values[j] for values in history)
            phase["applied_absolute"][j] += math.fsum(abs(values[j]) for values in history)
            phase["nonzero_requested"][j] += n if request[j] != 0 else 0
            phase["blocked_requested"][j] += sum(request[j] != 0 and values[j] == 0 for values in history)
        if expected == "prefix":
            compared = {name: row[name] for name in ("observation_before", "observation_after", "diagnostics")}
            for name, width in (("qpos", 15), ("qvel", 14)):
                if name in row:
                    compared[name] = _vector(row[name], width)
            fields = sorted(compared)
            if state["prefix_fields"] is not None and fields != state["prefix_fields"]:
                raise ValueError("prefix comparison fields changed within trial")
            state["prefix_fields"] = fields
            state["prefix_hash"].update(json.dumps(compared, sort_keys=True, separators=(",", ":"), allow_nan=False).encode())
            state["prefix_hash"].update(b"\n")
            state["prefix_rows"] += 1
    except (ValueError, TypeError, KeyError, IndexError) as error:
        state["errors"].append(f"row {index}: {type(error).__name__}: {error}")


def _finalize(state, metadata):
    trial = state["trial"]
    errors = state["errors"]
    try:
        _finite_tree(trial)
        if trial.get("invalid_numeric_fields"):
            raise ValueError("invalid trial numeric markers")
        if state["exception_rows"] or trial["status"] == "exception":
            raise ValueError("collector exception: interrupted physics may lack stored substep telemetry; budget retained")
        if trial["terminated"] or trial["status"] != "completed":
            raise ValueError("trial terminated or did not complete; excluded from response gate")
        if trial["mode"] not in ("zero_torque", "joint_probe"):
            raise ValueError("unknown trial mode")
        if trial["mode"] == "zero_torque" and (trial["joint_index"] is not None or trial["amplitude_nm"] != 0):
            raise ValueError("shared zero must have no selected joint and zero amplitude")
        if trial["mode"] == "joint_probe":
            j = trial["joint_index"]
            if type(j) is not int or not 0 <= j < 8 or trial["amplitude_nm"] not in AMPLITUDES:
                raise ValueError("probe joint/amplitude outside frozen specification")
            selection = trial["selection_record"]
            if selection is None or selection["direction"] != trial["selected_direction"]:
                raise ValueError("missing or inconsistent direction record")
            observed = state["phases"]["probe"]["first_before"]["joint_position"][j]
            if selection["joint_position_rad"] != observed or selection["selection_step"] != metadata["prefix_steps"]:
                raise ValueError("direction selection did not use the paid prefix endpoint")
            lower, upper = selection["lower_limit_rad"], selection["upper_limit_rad"]
            if not lower < upper or selection["direction"] != (1 if upper - observed >= observed - lower else -1):
                raise ValueError("direction does not follow fixed public-limit rule")
        for owner in ("environment", "actor"):
            before, after = trial[owner + "_fingerprint_before"], trial[owner + "_fingerprint_after"]
            if not isinstance(before, str) or not before or before != after:
                raise ValueError(owner + " parameters changed or fingerprint is missing")
        spec = trial["probe_spec"]
        if any(spec[key] != 0 for key in ("model_updates", "policy_updates", "gate_updates", "direction_updates_after_selection")):
            raise ValueError("probe specification reports parameter or direction updates")
        actor_digest = hashlib.sha256(json.dumps(spec, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
        if actor_digest != trial["actor_fingerprint_before"]:
            raise ValueError("actor fingerprint does not match archived fixed specification")
        config = spec["config"]
        if (config["mode"] != ("zero" if trial["mode"] == "zero_torque" else "pulse")
                or config["joint_index"] != trial["joint_index"]
                or any(config[key] != metadata[key] for key in ("prefix_steps", "pulse_steps", "recovery_steps"))):
            raise ValueError("archived actor specification differs from experiment schedule")
        if trial["mode"] == "joint_probe" and (
                config["amplitude_nm"] != trial["amplitude_nm"]
                or spec["joint_ranges_rad"][trial["joint_index"]] != [trial["selection_record"]["lower_limit_rad"], trial["selection_record"]["upper_limit_rad"]]):
            raise ValueError("probe amplitude/public limit record differs from fixed specification")
        if trial["control_steps"] != state["rows"] or trial["physics_steps"] != state["physics_observed"]:
            raise ValueError("recorded trace exposure differs from trial budget")
        total = metadata["prefix_steps"] + metadata["pulse_steps"] + metadata["recovery_steps"]
        if trial["control_steps"] != total or trial["control_calls_attempted"] != total:
            raise ValueError("fixed total control budget was not completed")
        for phase, expected in zip(PHASES, (metadata["prefix_steps"], metadata["pulse_steps"], metadata["recovery_steps"])):
            observed, budget = state["phases"][phase], trial["phase_budgets"][phase]
            if (observed["control_rows"] != expected or budget["control_steps"] != observed["control_rows"]
                    or budget["control_calls_attempted"] != expected or budget["physics_steps"] != observed["physics_samples"]
                    or observed["physics_samples"] != expected * metadata["environment_config"]["control_substeps"]):
                raise ValueError(phase + " exposure does not match frozen phase budget")
    except (ValueError, TypeError, KeyError, IndexError) as error:
        errors.append(f"trial: {type(error).__name__}: {error}")
    result = {name: trial.get(name) for name in ("trial_id", "pose", "seed", "mode", "joint_index", "amplitude_nm",
               "selected_direction", "selection_record", "status", "terminated", "reason", "control_steps",
               "control_calls_attempted", "physics_steps", "phase_budgets")}
    result.update(metrics_available=not errors, validity_errors=errors,
                  completed_trace_rows=state["rows"], observed_trace_physics_steps=state["physics_observed"],
                  collector_exception_rows=state["exception_rows"], invalid_trace_rows=state["invalid_rows"],
                  prefix_canonical_sha256=state["prefix_hash"].hexdigest(), prefix_rows=state["prefix_rows"])
    result["prefix_comparison_fields"] = state["prefix_fields"]
    if not errors:
        result["phases"] = {phase: _phase_summary(state["phases"][phase], metadata["environment_config"]["physics_dt"]) for phase in PHASES}
        result["whole_trial"] = {
            "physics_samples": sum(phase["physics_samples"] for phase in result["phases"].values()),
            "ground_normal_force_peak_n": max(phase["ground_normal_force_peak_n"] for phase in result["phases"].values()),
            "ground_normal_force_integral_ns": math.fsum(phase["ground_normal_force_integral_ns"] for phase in result["phases"].values()),
            "kinetic_energy_peak_j": max(phase["kinetic_energy_peak_j"] for phase in result["phases"].values()),
            "minimum_contact_distance_m": min(phase["minimum_contact_distance_m"] for phase in result["phases"].values()),
        }
        if trial["mode"] == "joint_probe":
            j, direction = trial["joint_index"], trial["selected_direction"]
            for phase in result["phases"].values():
                for kind in ("requested", "accepted", "applied"):
                    phase["target_directed_" + kind + "_torque_integral_nms"] = direction * phase[kind + "_signed_torque_integral_nms_per_joint"][j]
        for name in ("environment_fingerprint_before", "environment_fingerprint_after", "actor_fingerprint_before", "actor_fingerprint_after"):
            result[name] = trial[name]
    return result


def _paired_rms(probe_state, zero_state, phases):
    result = {}
    for name in NATIVE_FIELDS:
        a = [row for phase in phases for row in probe_state["phases"][phase]["native"][name]]
        b = [row for phase in phases for row in zero_state["phases"][phase]["native"][name]]
        result[name] = _rms_vectors([[x - y for x, y in zip(left, right)] for left, right in zip(a, b)])
    return result


def _pair(probe, zero, states, metadata):
    result = {name: probe[name] for name in ("trial_id", "pose", "seed", "joint_index", "amplitude_nm", "selected_direction")}
    result.update(zero_trial_id=None if zero is None else zero["trial_id"], available=False,
                  exact_prefix_replay=False, missing_reason=None)
    if zero is None:
        result["missing_reason"] = "shared zero reference is missing"
        return result
    if not probe["metrics_available"] or not zero["metrics_available"]:
        result["missing_reason"] = "probe or shared zero is incomplete, invalid, interrupted or changed parameters"
        return result
    exact = (probe["prefix_rows"] == zero["prefix_rows"] == metadata["prefix_steps"]
             and probe["prefix_canonical_sha256"] == zero["prefix_canonical_sha256"])
    result["exact_prefix_replay"] = exact
    if not exact:
        result["missing_reason"] = "paid zero prefix differs from shared reference"
        return result
    pstate, zstate = states[probe["trial_id"]], states[zero["trial_id"]]
    if any(pstate["phases"][phase]["endpoint_times"] != zstate["phases"][phase]["endpoint_times"] for phase in PHASES):
        result["missing_reason"] = "probe/reference endpoints differ in actual executed physical time"
        return result
    j, direction = probe["joint_index"], probe["selected_direction"]
    for phase, label in (("probe", "pulse_end"), ("recovery", "recovery_end")):
        before = pstate["phases"]["probe"]["first_before"]["joint_position"]
        after = pstate["phases"][phase]["last_after"]["joint_position"]
        reference = zstate["phases"][phase]["last_after"]["joint_position"]
        paired = [x - y for x, y in zip(after, reference)]
        result[label] = {"native_trial_position_change_rad_per_joint": [x - y for x, y in zip(after, before)],
                         "paired_position_delta_rad_per_joint": paired,
                         "target_joint_paired_delta_rad": paired[j], "target_joint_directed_paired_delta_rad": direction * paired[j]}
    pulse_deltas = [a[j] - b[j] for a, b in zip(pstate["phases"]["probe"]["native"]["joint_position"],
                                                zstate["phases"]["probe"]["native"]["joint_position"])]
    recovery_deltas = [a[j] - b[j] for a, b in zip(pstate["phases"]["recovery"]["native"]["joint_position"],
                                                   zstate["phases"]["recovery"]["native"]["joint_position"])]
    prefix_seconds = metadata["prefix_steps"] * metadata["environment_config"]["control_substeps"] * metadata["environment_config"]["physics_dt"]
    crossing = next((index for index, delta in enumerate(pulse_deltas) if direction * delta >= MEASUREMENT_THRESHOLD_RAD), None)
    result.update(available=True,
                  target_maximum_absolute_paired_delta_during_pulse_rad=max(map(abs, pulse_deltas)),
                  target_maximum_absolute_paired_delta_during_recovery_rad=max(map(abs, recovery_deltas)),
                  target_maximum_absolute_paired_delta_after_prefix_rad=max(map(abs, pulse_deltas + recovery_deltas)),
                  first_recorded_pulse_threshold_crossing={
                      "reached": crossing is not None,
                      "pulse_action_index": crossing,
                      "elapsed_from_pulse_start_seconds": None if crossing is None else pstate["phases"]["probe"]["endpoint_times"][crossing] - prefix_seconds,
                      "threshold_rad": MEASUREMENT_THRESHOLD_RAD,
                      "meaning": "First observed control endpoint during the pulse; not a pure actuator delay. Recovery is not searched.",
                  },
                  paired_native_rms={"probe": _paired_rms(pstate, zstate, ("probe",)),
                                     "recovery": _paired_rms(pstate, zstate, ("recovery",)),
                                     "probe_and_recovery": _paired_rms(pstate, zstate, ("probe", "recovery"))},
                  pulse_action_metrics=probe["phases"]["probe"])
    return result


def _gates_and_doses(pairs, metadata, protocol_valid):
    by_case = {(p["pose"], p["joint_index"], p["amplitude_nm"], p["seed"]): p for p in pairs}
    gates, doses = [], []
    for pose in metadata["poses"]:
        for joint in metadata["joints"]:
            dose = {"pose": pose, "joint_index": joint, "joint_name": JOINT_NAMES[joint], "amplitudes": [], "seed_curves": []}
            for amplitude in AMPLITUDES:
                rows = [by_case.get((pose, joint, amplitude, seed)) for seed in metadata["seeds"]]
                available = len(rows) == 3 and all(row is not None and row["available"] for row in rows)
                gate = {"pose": pose, "joint_index": joint, "joint_name": JOINT_NAMES[joint], "amplitude_nm": amplitude,
                        "seeds": metadata["seeds"], "available": available, "passes": False,
                        "threshold_rad": MEASUREMENT_THRESHOLD_RAD, "threshold_comparator": ">=",
                        "scope": "within split; development and holdout must be combined separately",
                        "hardware_safety_standard": False}
                if available:
                    directed = [row["pulse_end"]["target_joint_directed_paired_delta_rad"] for row in rows]
                    raw = [row["pulse_end"]["target_joint_paired_delta_rad"] for row in rows]
                    directions = [row["selected_direction"] for row in rows]
                    direction_consistency = len(set(directions)) == 1 and all(value * directions[0] > 0 for value in raw)
                    gate.update(directed_pulse_end_deltas_rad=directed, selected_directions=directions,
                                response_direction_consistent_across_seeds=direction_consistency,
                                minimum_directed_pulse_end_delta_rad=min(directed),
                                mean_directed_pulse_end_delta_rad=math.fsum(directed) / 3,
                                selected_direction_consistent_across_seeds=len(set(directions)) == 1,
                                response_along_request_consistent_across_seeds=all(value > 0 for value in directed),
                                passes=protocol_valid and min(directed) >= MEASUREMENT_THRESHOLD_RAD)
                    dose["amplitudes"].append({"amplitude_nm": amplitude, "available": True,
                                              "mean_directed_pulse_end_delta_rad": math.fsum(directed) / 3,
                                              "minimum_directed_pulse_end_delta_rad": min(directed),
                                              "maximum_directed_pulse_end_delta_rad": max(directed)})
                else:
                    gate["missing_reason"] = "requires all three declared seeds and a complete valid shared-zero pair at this amplitude"
                    dose["amplitudes"].append({"amplitude_nm": amplitude, "available": False})
                gates.append(gate)
            for seed in metadata["seeds"]:
                rows = [by_case.get((pose, joint, amplitude, seed)) for amplitude in AMPLITUDES]
                curve = {"seed": seed, "amplitudes_nm": list(AMPLITUDES),
                         "available": all(row is not None and row["available"] for row in rows)}
                if curve["available"]:
                    directed = [row["pulse_end"]["target_joint_directed_paired_delta_rad"] for row in rows]
                    curve.update(directed_pulse_end_deltas_rad=directed,
                                 selected_directions=[row["selected_direction"] for row in rows],
                                 applied_directed_torque_integrals_nms=[row["pulse_action_metrics"]["target_directed_applied_torque_integral_nms"] for row in rows],
                                 target_nonzero_request_blocked_fractions=[row["pulse_action_metrics"]["blocked_fraction_of_nonzero_requested_substeps_per_joint"][joint] for row in rows],
                                 direction_consistent_across_amplitudes=len({row["selected_direction"] for row in rows}) == 1,
                                 nondecreasing_directed_dose_response=all(a <= b for a, b in zip(directed, directed[1:])))
                dose["seed_curves"].append(curve)
            doses.append(dose)
    return gates, doses


def analyze(folder):
    metadata = json.loads((folder / "metadata.json").read_text(encoding="utf-8"))
    trials = json.loads((folder / "trials.json").read_text(encoding="utf-8"))
    ids = [trial["trial_id"] for trial in trials]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate trial IDs: ambiguous probe/reference archive")
    states = {trial["trial_id"]: _new_state(trial) for trial in trials}
    orphan_rows = defaultdict(int)
    with gzip.open(folder / "trace.jsonl.gz", "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if row["trial_id"] in states:
                _consume(states[row["trial_id"]], row, metadata)
            else:
                orphan_rows[row["trial_id"]] += 1
    summaries = [_finalize(states[trial["trial_id"]], metadata) for trial in trials]
    zeros = {}
    for trial in summaries:
        if trial["mode"] == "zero_torque":
            key = (trial["pose"], trial["seed"])
            if key in zeros:
                raise ValueError("duplicate shared zero for a pose/seed case")
            zeros[key] = trial
    pairs = [_pair(trial, zeros.get((trial["pose"], trial["seed"])), states, metadata)
             for trial in summaries if trial["mode"] == "joint_probe"]
    seen = {(t["pose"], t["seed"], t["mode"], t["joint_index"], t["amplitude_nm"]) for t in summaries}
    missing = []
    for pose in metadata["poses"]:
        for seed in metadata["seeds"]:
            if (pose, seed, "zero_torque", None, 0.) not in seen:
                missing.append({"pose": pose, "seed": seed, "mode": "zero_torque", "joint_index": None, "amplitude_nm": 0.})
            for joint in metadata["joints"]:
                for amplitude in metadata["amplitudes_nm"]:
                    if (pose, seed, "joint_probe", joint, amplitude) not in seen:
                        missing.append({"pose": pose, "seed": seed, "mode": "joint_probe", "joint_index": joint, "amplitude_nm": amplitude})
    budget_checks = {key: {"metadata": metadata[key], "sum_trials": sum(trial[key] for trial in trials),
                          "equal": metadata[key] == sum(trial[key] for trial in trials)}
                     for key in ("control_steps", "control_calls_attempted", "physics_steps")}
    phase_checks = {phase: {key: {"metadata": metadata["phase_budgets"][phase][key],
                                          "sum_trials": sum(trial["phase_budgets"][phase][key] for trial in trials),
                                          "equal": metadata["phase_budgets"][phase][key] == sum(trial["phase_budgets"][phase][key] for trial in trials)}
                           for key in ("control_steps", "control_calls_attempted", "physics_steps")} for phase in PHASES}
    zero_updates = metadata["parameter_updates"] == {"model": 0, "policy": 0, "gate": 0}
    protocol_valid = (metadata["complete"] and zero_updates and not orphan_rows and not missing
                      and len(trials) == metadata["expected_trial_count"]
                      and all(check["equal"] for check in budget_checks.values())
                      and all(check["equal"] for checks in phase_checks.values() for check in checks.values()))
    gates, doses = _gates_and_doses(pairs, metadata, protocol_valid)
    paths = [folder / name for name in ("metadata.json", "trials.json", "trace.jsonl.gz", "source_snapshot.zip")]
    return {
        "schema_version": 1, "analysis_type": "standard-library fixed joint-pulse diagnostics; zero fitting",
        "source_commit": metadata["source_commit"], "source_dirty": metadata["source_dirty"], "split": metadata["split"],
        "analysis_script_sha256": _hash(Path(__file__)),
        "input_sha256": {str(path.resolve()): _hash(path) for path in paths},
        "analysis_runtime": {"python": sys.version, "platform": platform.platform(), "third_party_analysis_dependencies": []},
        "archive_complete": metadata["complete"], "protocol_valid": protocol_valid,
        "trial_count": len(trials), "expected_trial_count": metadata["expected_trial_count"],
        "seeds": metadata["seeds"], "joint_order": list(JOINT_NAMES), "amplitudes_nm": metadata["amplitudes_nm"],
        "phase_steps": {phase: metadata[key] for phase, key in zip(PHASES, ("prefix_steps", "pulse_steps", "recovery_steps"))},
        "parameter_updates": metadata["parameter_updates"], "analysis_parameter_updates": 0,
        "budget_checks": budget_checks, "phase_budget_checks": phase_checks,
        "missing_trial_cases": missing, "orphan_trace_trial_row_counts": dict(orphan_rows),
        "unavailable_trial_ids": [trial["trial_id"] for trial in summaries if not trial["metrics_available"]],
        "shared_zero_trial_count": len(zeros), "probe_pair_count": len(pairs),
        "unique_pose_seed_case_count": len({(trial["pose"], trial["seed"]) for trial in summaries}),
        "trials": summaries, "pairs": pairs, "measurement_gates": gates, "dose_response": doses,
        "claim_boundary": "Shared zero trajectories are reused across joint/amplitude pairs; reuse does not add independent samples. Every prefix, pulse, recovery and interrupted physics step remains in the raw budget. Gates require three complete valid paired seeds and minimum directed pulse-end encoder difference >= 1 mrad. Raw direction consistency across seeds is reported descriptively; the gate uses each trial's selected direction. This is a fixed ideal-sensor simulation measurement criterion, not a hardware safety standard, identifiability result, learned body model or acquired skill. Dose response is descriptive; no fit, significance test or optimized amplitude. Actual command metrics use executed physics-substep exposure; blocking counts nonzero requests whose applied command is exactly zero. Force integrals include sustained support, contact distance includes self-contacts, and 2 ms telemetry does not bound continuous-time impact.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.resolve().is_relative_to(args.archive.resolve()):
        parser.error("analysis output must be outside the read-only input archive")
    if args.output.exists():
        parser.error("output already exists; preserve prior analysis")
    result = analyze(args.archive)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"trial_count": result["trial_count"], "protocol_valid": result["protocol_valid"],
                      "unavailable_trials": len(result["unavailable_trial_ids"]),
                      "missing_cases": len(result["missing_trial_cases"]),
                      "measurement_gate_passes": sum(gate["passes"] for gate in result["measurement_gates"]),
                      "analysis_parameter_updates": 0}, indent=2))


if __name__ == "__main__":
    main()
