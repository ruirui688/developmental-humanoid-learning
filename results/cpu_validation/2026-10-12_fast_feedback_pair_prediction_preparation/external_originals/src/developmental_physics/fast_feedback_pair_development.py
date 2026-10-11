"""Z1/Z2 native-only collection; no execution occurs on import.

New support-domain protocol only. The existing atomic coupled RLS and the
residual-PD controller retain their mathematical implementations. This module
adds paid-interval capture, exact forward counters, and complete-population
gates; it never loads an earlier free-root experiment.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict
import hashlib
import json
import traceback

import numpy as np

from .fast_feedback_pair_model import FastFeedbackGuardCoupledPairBodyModel
from .local_pair_model import _parameter_state
from .fast_feedback_pair_mpc import FastFeedbackResidualPDPairMPC, public_pd_request

SEEDS = (7701, 7702, 7703)
PREFIX = 1000
CALIBRATION = 4000
PREDICTION = 1000
CONTROL = 2000
HORIZONS = (1, 10, 20, 50, 150)
SCORING_STRIDE = 10
MACRO_HOLD = 10
FLAGS = {"scientific_adoption": False, "old_free_root_C4_validation": False,
         "c4_scientific_validation": False, "c5_scientific_dependency_released": False,
         "c4_contact_scientific_validation": False}


def safe(value):
    if isinstance(value, np.ndarray):
        return safe(value.tolist())
    if isinstance(value, (float, np.floating)) and not np.isfinite(value):
        return {"nonfinite_float": str(value)}
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, dict):
        return {str(k): safe(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [safe(v) for v in value]
    return value


def identity(data):
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def failure(exc):
    row = {"type": type(exc).__name__, "message": str(exc),
           "traceback": traceback.format_exc()}
    for key in ("pair_update_accounting", "pair_prediction_accounting", "pair_planning_accounting"):
        if hasattr(exc, key):
            row[key] = safe(getattr(exc, key))
    if hasattr(exc, "to_dict"):
        try:
            row["structured_failure"] = safe(exc.to_dict())
        except BaseException as detail_exc:
            row["structured_failure_reporting_failure"] = {
                "type": type(detail_exc).__name__, "message": str(detail_exc)}
    return row


def native(observation):
    q, v = (np.asarray(observation[key], dtype=float) for key in
            ("joint_position", "joint_velocity"))
    if q.shape != (8,) or v.shape != (8,) or not np.isfinite(q).all() or not np.isfinite(v).all():
        raise ValueError("eight finite native positions/velocities required")
    return tuple(q[:2]), tuple(v[:2])


def study_abort(observation, qref):
    q, v = native(observation)
    triggers = [{"joint_index": i, "signal": signal} for i in range(2)
                for signal, condition in (("absolute_q_minus_qref_rad", abs(q[i]-qref[i]) >= .12),
                                          ("absolute_velocity_rad_s", abs(v[i]) >= 1.)) if condition]
    return None if not triggers else {"type": "StudyAbort", "triggers": triggers,
        "q_rad": q, "qref_rad": qref, "velocity_rad_s": v,
        "thresholds": {"absolute_q_minus_qref_rad": .12, "absolute_velocity_rad_s": 1.},
        "evaluation_time": "after_complete_control_interval", "feedback_action": None}


def direction_targets(qref, ranges):
    selection = []
    for i, (lower, upper) in enumerate(ranges):
        positive, negative = upper-qref[i], qref[i]-lower
        selection.append({"joint_index": i, "direction": 1 if positive >= negative else -1,
            "positive_room_rad": positive, "negative_room_rad": negative,
            "rule": "larger_public_limit_distance_tie_positive"})
    targets = [tuple(qref[i]+selection[i]["direction"]*delta for i in range(2)) for delta in (.04, .08)]
    feasible = all(all(ranges[i][0]+.03 <= target[i] <= ranges[i][1]-.03 for i in range(2))
                   for target in targets)
    return selection, targets, feasible


def pulse(index, kind):
    block, slot = divmod(index // MACRO_HOLD, 20)
    if kind == "calibration":
        group, amplitude_index = divmod(block, 5)
        axes = ((1., 0.), (0., 1.), (1., 1.), (1., -1.))[group]
        amplitude = (.125, .25, .375, .5, .25)[amplitude_index]
        sign = 1. if slot == 0 else -1. if slot == 10 else 0.
    elif kind == "prediction":
        axes = ((1., 0.), (0., 1.), (1., 1.), (1., -1.), (1., 1.))[block]
        amplitude = (.125, .25, .375, .5, .375)[block]
        sign = 1. if slot == 1 else -1. if slot == 9 else 0.
    else:
        raise ValueError("declared calibration/prediction schedule required")
    return tuple(sign*amplitude*x for x in axes)


def counted_pd(q, v, target, cost, scope):
    cost[scope+"_pd_request_attempts"] += 1
    request = public_pd_request(q, v, target)
    cost[scope+"_pd_request_returns"] += 1
    return request


class CountedGuardModel(FastFeedbackGuardCoupledPairBodyModel):
    """Instrumentation around original math, including RLS preupdate heads."""
    def __init__(self, qref, *, public_joint_ranges, cost, label, trainable=True):
        self.cost, self.label, self.scope = cost, label, "unclassified"
        self.forward_counts = Counter()
        cost["body_model_build_attempts"] += 1
        super().__init__(qref, public_joint_ranges=public_joint_ranges, trainable=trainable)
        cost["body_model_build_returns"] += 1

    def _count(self, key):
        self.cost[self.scope+"_"+key] += 1
        self.forward_counts[self.scope+"_"+key] += 1

    def snapshot(self):
        self.cost["body_model_snapshot_attempts"] += 1
        result = super().snapshot()
        self.cost["body_model_snapshot_returns"] += 1
        return result

    def parameter_fingerprint(self):
        self.cost["body_model_fingerprint_attempts"] += 1
        result = super().parameter_fingerprint()
        self.cost["body_model_fingerprint_returns"] += 1
        return result

    def _predict_state(self, q, v, u, state):
        self._count("pair_prediction_attempts")
        try:
            result = super()._predict_state(q, v, u, state)
        except BaseException:
            self._count("pair_prediction_failures")
            raise
        self._count("pair_prediction_returns")
        return result

    def _predict_output(self, index, features, state=None):
        self._count("scalar_prediction_attempts")
        try:
            result = super()._predict_output(index, features, state)
        except BaseException:
            self._count("scalar_prediction_failures")
            raise
        self._count("scalar_prediction_returns")
        return result

    def _features(self, q, v, u):
        self._count("feature_guard_projection_attempts")
        result = super()._features(q, v, u)
        self._count("feature_guard_projection_returns")
        return result

    def clone_frozen(self):
        self.cost["body_model_clone_attempts"] += 1
        clone = CountedGuardModel(self.qref, public_joint_ranges=self.public_guard.public_joint_ranges,
                                 cost=self.cost, label=self.label+"_frozen", trainable=False)
        clone._state = _parameter_state(self._state.theta.copy(), self._state.covariance.copy(), self.update_count)
        if clone.parameter_fingerprint() != self.parameter_fingerprint():
            raise ValueError("frozen_clone_fingerprint_differs")
        self.cost["body_model_clone_returns"] += 1
        return clone


def restore_model(snapshot, cost, label):
    """Strict restoration; constructing a prior is not fitting or RLS replay."""
    cost["body_model_restoration_attempts"] += 1
    if (snapshot.get("structure") != "coupled_hinge9" or snapshot.get("trainable") is not False
            or snapshot.get("integration") != "endpoint_euler" or snapshot.get("dt_seconds") != .002
            or snapshot.get("initial_covariance_scale") != 100. or snapshot.get("forgetting_factor") != 1.
            or snapshot.get("hinge_threshold_nm") != .25):
        raise ValueError("frozen_Z_micro_coupled_guard_snapshot_required")
    ranges = snapshot["input_mapping"]["public_guard"]["public_joint_ranges_rad"]
    model = CountedGuardModel(snapshot["qref_rad"], public_joint_ranges=ranges,
                              cost=cost, label=label, trainable=False)
    theta, covariance = (np.asarray(snapshot[key], dtype=float) for key in ("coefficients", "covariance"))
    count = snapshot["vector_update_count"]
    if (theta.shape != (2, 9) or covariance.shape != (2, 9, 9) or type(count) is not int or count < 0
            or not np.isfinite(theta).all() or not np.isfinite(covariance).all()
            or snapshot.get("scalar_update_count") != 2*count
            or snapshot.get("output_update_counts") != [count, count]):
        raise ValueError("complete_finite_atomic_snapshot_required")
    model._state = _parameter_state(theta.copy(), covariance.copy(), count)
    if model.snapshot() != snapshot:
        raise ValueError("restored_snapshot_or_fingerprint_differs")
    cost["body_model_restoration_returns"] += 1
    return model


def complete_telemetry(row):
    try:
        if row.get("returned") is not True or row["diagnostics"]["executed_substeps"] != 1:
            return False
        native(row["observation_before"])
        native(row["observation_after"])
        samples = row["diagnostics"]["substep_native_and_contact_records"]
        if len(samples) != 1:
            return False
        for i, sample in enumerate(samples):
            if sample["physics_step"] != row["control_index"]+i+1 or not np.isfinite(sample["time"]):
                return False
            values = [(sample["applied_command8"], 8), (sample["actual_actuator_torque8"], 8)]
            values += [(sample["observation"][key], size) for key, size in
                       (("joint_position", 8), ("joint_velocity", 8), ("imu_gyro", 3),
                        ("imu_acceleration", 3), ("actuator_torque", 8), ("previous_command", 8))]
            if any(np.asarray(value).shape != (size,) or not np.isfinite(np.asarray(value, dtype=float)).all()
                   for value, size in values):
                return False
            if any(not np.isfinite(contact[key]) for contact in sample["floor_contacts"]
                   for key in ("normal_force_n", "distance_m")):
                return False
        return True
    except (KeyError, TypeError, ValueError):
        return False


def effort(records):
    result = {phase: {"actual_absolute_axis_nm_s": [0., 0.], "actual_squared_axis_nm2_s": [0., 0.],
                     "all8_actual_absolute_nm_s": 0., "all8_actual_squared_nm2_s": 0.,
                     "applied_absolute_axis_nm_s": [0., 0.], "applied_squared_axis_nm2_s": [0., 0.],
                     "captured_substeps": 0, "complete": False} for phase in ("prefix", "active")}
    contacts = Counter()
    for row in records:
        target = result[row["phase"]]
        samples = (row.get("diagnostics") or row.get("saved_partial") or {}).get("substep_native_and_contact_records", [])
        for sample in samples:
            try:
                actual, applied = (np.asarray(sample[k], dtype=float) for k in
                                   ("actual_actuator_torque8", "applied_command8"))
            except (KeyError, TypeError, ValueError):
                target["nonfinite_or_missing_effort"] = True
                continue
            if actual.shape != (8,) or applied.shape != (8,) or not np.isfinite(actual).all() or not np.isfinite(applied).all():
                target["nonfinite_or_missing_effort"] = True
                continue
            for i in range(2):
                target["actual_absolute_axis_nm_s"][i] += abs(float(actual[i]))*.002
                target["actual_squared_axis_nm2_s"][i] += float(actual[i])**2*.002
                target["applied_absolute_axis_nm_s"][i] += abs(float(applied[i]))*.002
                target["applied_squared_axis_nm2_s"][i] += float(applied[i])**2*.002
            target["all8_actual_absolute_nm_s"] += float(np.sum(np.abs(actual))*.002)
            target["all8_actual_squared_nm2_s"] += float(np.sum(actual**2)*.002)
            target["captured_substeps"] += 1
            for contact in sample.get("floor_contacts", []):
                contacts[contact.get("contact_class", "left_arm" if contact.get("left_arm") else "other")] += 1
    for phase, values in result.items():
        selected = [row for row in records if row["phase"] == phase]
        values["complete"] = bool(selected and all(complete_telemetry(row) for row in selected)
                                   and values["captured_substeps"] == len(selected)
                                   and not values.get("nonfinite_or_missing_effort", False))
        values["actual_absolute_two_axis_nm_s"] = sum(values["actual_absolute_axis_nm_s"])
        values["actual_squared_two_axis_nm2_s"] = sum(values["actual_squared_axis_nm2_s"])
        values["counts_are_lower_bounds_if_incomplete"] = not values["complete"]
    return result, dict(contacts)


def collect_trial(trial, trace, cost, *, seed, active_steps, kind, env_factory,
                  expected_qref=None, expected_installation=None, after_prefix=None,
                  actor=None, after_transition=None, paid_writer=None):
    """Fresh trajectory, preserving paid records before study/update helpers."""
    trial.update(trial_id=f"Z_{seed}_{kind}", seed=seed, kind=kind, status="failed", complete=False,
                 planned_prefix=PREFIX, planned_active=active_steps, record_start=len(trace), stop=None,
                 failure=None, qref2=None, public_joint_ranges2=None, records=[])
    records, env = trial["records"], None
    qref = None
    try:
        cost["environment_constructor_attempts"] += 1
        env = env_factory()
        cost["environment_constructor_returns"] += 1
        cost["reset_attempts"] += 1
        observation = env.reset(seed=seed, pose="upright")
        cost["reset_returns"] += 1
        trial["support"] = env.support_configuration()
        trial["installed_xml_utf8"] = env._installed_xml.decode("utf-8")
        trial["installed_xml_identity"] = identity(env._installed_xml)
        cost["physical_fingerprint_attempts"] += 1
        trial["physical_fingerprint_before"] = env.physical_configuration_fingerprint()
        cost["physical_fingerprint_returns"] += 1
        cost["execution_fingerprint_attempts"] += 1
        trial["execution_fingerprint_before"] = env.parameter_fingerprint()
        cost["execution_fingerprint_returns"] += 1
        cost["action_interface_metadata_calls"] += 1
        trial["action_interface"] = env.action_interface_configuration()
        cost["interface_fingerprint_calls"] += 1
        trial["interface_fingerprint"] = env.interface_fingerprint()
        if expected_installation is not None and (
                trial["installed_xml_identity"] != expected_installation["installed_xml_identity"]
                or trial["physical_fingerprint_before"] != expected_installation["physical_fingerprint_before"]
                or trial["execution_fingerprint_before"] != expected_installation["execution_fingerprint_before"]
                or trial["interface_fingerprint"] != expected_installation["interface_fingerprint"]):
            raise ValueError("same_seed_fixed_installation_differs_from_calibration_no_remount")
        ranges = np.asarray(env.model.jnt_range[env._joint_ids], dtype=float)[:2]
        if ranges.shape != (2, 2) or not np.isfinite(ranges).all():
            raise ValueError("finite_public_two_joint_ranges_required")
        trial["public_joint_ranges2"] = ranges.tolist()
        for index in range(PREFIX+active_steps):
            phase, phase_index = ("prefix", index) if index < PREFIX else ("active", index-PREFIX)
            if phase == "active" and qref is None:
                qref = native(observation)[0]
                trial["qref2"] = list(qref)
                if expected_qref is not None and any(abs(qref[i]-expected_qref[i]) > 1e-12 for i in range(2)):
                    trial["stop"] = {"primary_reason": "fresh_prefix_reference_mismatch_no_retry",
                                     "expected_qref2": expected_qref, "actual_qref2": qref}
                    break
                if after_prefix is not None and after_prefix(trial) is False:
                    trial["stop"] = {"primary_reason": "infeasible_fixed_target_no_clipping_or_direction_retry"}
                    break
            request = [0.]*8
            info = {"current_target_q2": None}
            if phase == "active":
                if actor is not None:
                    command, info = actor(observation, phase_index, trial)
                else:
                    q, v = native(observation)
                    pd = counted_pd(q, v, qref, cost, kind)
                    excitation = pulse(phase_index, kind)
                    command = tuple(float(np.clip(pd[i]+excitation[i], -.5, .5)) for i in range(2))
                    info = {"current_target_q2": qref, "public_pd_request2": pd, "pulse2": excitation}
                if len(command) != 2 or not np.isfinite(command).all() or any(abs(u) > .5 for u in command):
                    raise ValueError("finite_final_request_with_shared_permission_required")
                request[:2] = command
            row = {"seed": seed, "trial_id": trial["trial_id"], "transition_id": f"{trial['trial_id']}:{index}",
                   "control_index": index, "phase": phase, "phase_index": phase_index,
                   "observation_before": safe(observation), "requested_torque": list(request),
                   "returned": False, "study_abort": None, "diagnostics": None, **safe(info)}
            records.append(row)
            trace.append(row)
            before = env.physics_steps
            cost["control_call_attempts"] += 1
            try:
                result = env.step(request)
            except BaseException as exc:
                cost["control_call_exceptions"] += 1
                row.update(collector_exception={"type": type(exc).__name__, "message": str(exc)},
                           confirmed_completed_substeps=env.physics_steps-before,
                           saved_partial=safe(env.last_step_partial))
                if paid_writer is not None:
                    paid_writer(row)
                row["collector_exception"] = failure(exc)
                raise
            finally:
                cost["confirmed_physics_substeps"] += env.physics_steps-before
            cost["control_call_returns"] += 1
            observation = result.observation
            row.update(returned=True, observation_after=safe(observation), diagnostics=safe(result.diagnostics),
                       environment_terminated=bool(result.terminated), environment_reason=result.reason)
            # Above is the paid return. Everything below may fail without losing it.
            if paid_writer is not None:
                paid_writer(row)
            complete = result.diagnostics["executed_substeps"] == 1
            row["study_abort"] = study_abort(observation, qref) if phase == "active" and complete else None
            if row.get("current_target_q2") is not None:
                q, _ = native(observation)
                row["target_error_rad"] = [q[i]-row["current_target_q2"][i] for i in range(2)]
            if result.terminated or not complete or row["study_abort"] is not None:
                trial["stop"] = {"transition_id": row["transition_id"], "environment_reason": result.reason,
                    "environment_terminated": bool(result.terminated), "study_abort": row["study_abort"],
                    "executed_substeps": result.diagnostics["executed_substeps"],
                    "primary_reason": result.reason or ("partial_interval" if not complete else "StudyAbort")}
                break
            if not complete_telemetry(row):
                raise ValueError("complete_interval_native_effort_or_contact_telemetry_missing")
            if phase == "active" and after_transition is not None:
                after_transition(row)
            if phase == "active" and phase_index % 100 == 99:
                print(json.dumps(safe({"progress": "paid_active_block_complete", "seed": seed,
                    "phase": kind, "active_returns": phase_index+1,
                    "control_returns_total": cost["control_call_returns"],
                    "confirmed_substeps_total": cost["confirmed_physics_substeps"]}),
                    allow_nan=False), flush=True)
        trial["status"] = "stopped" if trial["stop"] else "completed"
    except BaseException as exc:
        trial["failure"] = failure(exc)
        trial["status"] = "failed"
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
    finally:
        if env is not None:
            trial["engineering_operations"] = safe(env.engineering_operations)
            for key in ("model_builds", "reset_forward_attempts", "reset_forward_returns"):
                cost["environment_"+key] += env.engineering_operations.get(key, 0)
            try:
                cost["physical_fingerprint_attempts"] += 1
                trial["physical_fingerprint_after"] = env.physical_configuration_fingerprint()
                cost["physical_fingerprint_returns"] += 1
                if trial.get("physical_fingerprint_before") != trial["physical_fingerprint_after"] and trial.get("physical_fingerprint_before") is not None:
                    raise ValueError("fixed_physical_parameters_changed")
                cost["execution_fingerprint_attempts"] += 1
                trial["execution_fingerprint_after"] = env.parameter_fingerprint()
                cost["execution_fingerprint_returns"] += 1
                if trial.get("execution_fingerprint_before") != trial["execution_fingerprint_after"] and trial.get("execution_fingerprint_before") is not None:
                    raise ValueError("fixed_action_interface_or_execution_parameters_changed")
            except BaseException as exc:
                trial.setdefault("finalization_failures", []).append(failure(exc))
                trial["failure"] = trial["failure"] or failure(exc)
                trial["status"] = "failed"
        trial["record_end"] = len(trace)
        trial["returned_intervals"] = sum(row.get("returned") is True for row in records)
        trial["actual_effort"], trial["floor_contact_classes"] = effort(records)
        captured = sum(values["captured_substeps"] for values in trial["actual_effort"].values())
        cost["captured_substep_endpoint_forward_returns"] += captured
        trial["complete"] = bool(len(records) == PREFIX+active_steps and trial["failure"] is None
            and trial["stop"] is None and all(complete_telemetry(row) for row in records))
        trial["actual_effort"]["active"]["complete"] &= trial["complete"]
        print(json.dumps(safe({"progress": "trial_finished", "seed": seed, "phase": kind,
            "status": trial["status"], "returned_intervals": trial["returned_intervals"],
            "control_attempts_total": cost["control_call_attempts"],
            "confirmed_substeps_total": cost["confirmed_physics_substeps"], "stop": trial["stop"]}),
            allow_nan=False), flush=True)


def score_population(trial, models, predictions, cost, *, scope):
    """One scoring pass. Future requests condition rollouts; states only label."""
    active = [row for row in trial["records"] if row["phase"] == "active"]
    planned = trial["planned_active"]
    summary = {"trial_id": trial["trial_id"], "complete_population": trial["complete"],
               "condition": "saved future known requests offline; recursively predicted own q/v",
               "horizons": {}, "model_fingerprints": {name: model.parameter_fingerprint() for name, model in models.items()}}
    for horizon in HORIZONS:
        origin_indices = tuple(range(0, planned-horizon+1, SCORING_STRIDE))
        origins = len(origin_indices)
        horizon_row = summary["horizons"][str(horizon)] = {"planned_origin_count": origins, "models": {}}
        for name, model in models.items():
            q_errors, v_errors = [], []
            model.scope = scope
            for origin in origin_indices:
                row = {"trial_id": trial["trial_id"], "seed": trial["seed"], "scope": scope,
                       "model": name, "horizon": horizon, "origin_active_index": origin,
                       "available": False, "predicted_q_path": [], "predicted_v_path": []}
                predictions.append(row)
                segment = active[origin:origin+horizon]
                if len(segment) != horizon or not all(complete_telemetry(step) for step in segment):
                    row["unavailable_reason"] = "missing_complete_saved_population"
                    continue
                q, v = native(segment[0]["observation_before"])
                requests = [tuple(step["requested_torque"][:2]) for step in segment]
                row.update(model_input={"q2": q, "v2": v, "known_requests2": requests},
                           model_parameter_fingerprint=summary["model_fingerprints"][name])
                try:
                    for request in requests:
                        q, v = model.predict(q, v, request)
                        row["predicted_q_path"].append(q)
                        row["predicted_v_path"].append(v)
                except BaseException as exc:
                    row["failure"] = failure(exc)
                    raise
                actual_q, actual_v = native(segment[-1]["observation_after"])
                dq, dv = [q[i]-actual_q[i] for i in range(2)], [v[i]-actual_v[i] for i in range(2)]
                row.update(available=True, actual_endpoint_q2=actual_q, actual_endpoint_v2=actual_v,
                           q_error_rad=dq, v_error_rad_s=dv)
                q_errors.append(dq)
                v_errors.append(dv)
            available = bool(trial["complete"] and len(q_errors) == origins and len(v_errors) == origins)
            rmse_q, rmse_v = None, None
            if available:
                cost[scope+"_axis_RMSE_vector_computations"] += 2
                with np.errstate(over="ignore", invalid="ignore"):
                    rmse_q, rmse_v = (np.sqrt(np.mean(np.square(errors), axis=0)) for errors in (q_errors, v_errors))
                available = bool(np.isfinite(rmse_q).all() and np.isfinite(rmse_v).all())
            horizon_row["models"][name] = {"available": available, "observed_origin_count": len(q_errors),
                "q_rmse_axis_rad": rmse_q.tolist() if available else None,
                "v_rmse_axis_rad_s": rmse_v.tolist() if available else None,
                "partial_subset_ranking": False}
    summary["model_fingerprints_after"] = {name: model.parameter_fingerprint() for name, model in models.items()}
    if summary["model_fingerprints_after"] != summary["model_fingerprints"]:
        raise ValueError("frozen_conditional_prediction_model_changed")
    return summary


def prediction_gate(scores):
    checks = []
    complete = len(scores) == 3 and {row["seed"] for row in scores} == set(SEEDS)
    for horizon in HORIZONS:
        for signal in ("q", "v"):
            key = "q_rmse_axis_rad" if signal == "q" else "v_rmse_axis_rad_s"
            bases, candidates = [], []
            strict = (horizon, signal) in ((10, "v"), (150, "q"))
            gated = horizon != 1 and (horizon, signal) != (10, "q")
            for row in scores:
                hrow = row["prediction_scores"]["horizons"][str(horizon)]["models"]
                cold, learned = hrow.get("cold", {}), hrow.get("learned", {})
                available = bool(cold.get("available") and learned.get("available"))
                if not available:
                    if gated:
                        complete = False
                    checks.append({"seed": row["seed"], "horizon": horizon, "signal": signal,
                                   "available": False, "gated": gated, "passed": False})
                    continue
                base, candidate = cold[key], learned[key]
                bases.append(base)
                candidates.append(candidate)
                # Native H1 and physical-20ms H10q report only; no extra veto.
                passed = all(candidate[i] < base[i] if strict else candidate[i] <= base[i] for i in range(2))
                checks.append({"seed": row["seed"], "horizon": horizon, "signal": signal,
                    "available": True, "gated": gated, "strict": strict, "passed": bool(passed),
                    "cold_axis": base, "learned_axis": candidate})
            if strict:
                available = len(bases) == 3 and np.isfinite(bases).all() and np.isfinite(candidates).all()
                base_mean = np.mean(bases, axis=0) if available else None
                candidate_mean = np.mean(candidates, axis=0) if available else None
                fractions = [(float(base_mean[i]-candidate_mean[i])/float(base_mean[i]) if base_mean[i] > 0. else None)
                             for i in range(2)] if available else None
                checks.append({"scope": "three_seed_raw_RMSE_mean", "horizon": horizon, "signal": signal,
                    "available": bool(available), "cold_axis_mean": safe(base_mean), "learned_axis_mean": safe(candidate_mean),
                    "improvement_fractions": fractions, "required_improvement": .20,
                    "passed": bool(available and all(value is not None and value >= .20 for value in fractions))})
    passed = complete and all(row["passed"] for row in checks if row.get("gated", True))
    return {"complete_population": bool(complete), "checks": checks, "z1_prediction_gate_passed": bool(passed),
            "mean_type": "arithmetic mean of original per_seed axis RMSE", "partial_subset_ranking": False, **FLAGS}


def tracking_score(trial):
    active = [row for row in trial["records"] if row["phase"] == "active"]
    available = bool(trial["complete"] and len(active) == CONTROL and trial["actual_effort"]["active"]["complete"])
    errors = np.asarray([row.get("target_error_rad") for row in active], dtype=float) if available else None
    if available and (errors.shape != (CONTROL, 2) or not np.isfinite(errors).all()):
        available = False
    return {"available": available, "planned_active_count": CONTROL, "observed_active_count": len(active),
        "axis_rmse_rad": np.sqrt(np.mean(errors**2, axis=0)).tolist() if available else None,
        "joint_rmse_rad": float(np.sqrt(np.mean(errors**2))) if available else None,
        "actual_absolute_two_axis_nm_s": trial["actual_effort"]["active"]["actual_absolute_two_axis_nm_s"] if available else None,
        "actual_squared_two_axis_nm2_s": trial["actual_effort"]["active"]["actual_squared_two_axis_nm2_s"] if available else None,
        "partial_subset_ranking": False}


def control_gate(seed_results):
    def comparison(baseline, strict, threshold):
        checks, bases, candidates = [], [], []
        complete = len(seed_results) == 3 and {row["seed"] for row in seed_results} == set(SEEDS)
        for seed in seed_results:
            base, candidate = seed["tracking_scores"][baseline], seed["tracking_scores"]["learned"]
            available = bool(base["available"] and candidate["available"])
            if not available:
                complete = False
                checks.append({"seed": seed["seed"], "available": False, "passed": False})
                continue
            bases.append(base)
            candidates.append(candidate)
            bv, cv = [base["joint_rmse_rad"], *base["axis_rmse_rad"]], [candidate["joint_rmse_rad"], *candidate["axis_rmse_rad"]]
            checks.append({"seed": seed["seed"], "available": True, "strict": strict,
                           "baseline_joint_axis": bv, "learned_joint_axis": cv,
                           "passed": all(c < b if strict else c <= b for b, c in zip(bv, cv))})
        if len(bases) == 3:
            bv = np.mean([[row["joint_rmse_rad"], *row["axis_rmse_rad"]] for row in bases], axis=0)
            cv = np.mean([[row["joint_rmse_rad"], *row["axis_rmse_rad"]] for row in candidates], axis=0)
            fractions = [(float(b-c)/float(b) if b > 0. else None) for b, c in zip(bv, cv)]
            required_indices = (0, 1, 2) if strict else (0,)
            checks.append({"scope": "three_seed_raw_RMSE_mean", "baseline_joint_axis_mean": bv.tolist(),
                           "learned_joint_axis_mean": cv.tolist(), "improvement_fractions": fractions,
                           "required_improvement": threshold,
                           "passed": all(fractions[i] is not None and fractions[i] >= threshold for i in required_indices)})
            for key in ("actual_absolute_two_axis_nm_s", "actual_squared_two_axis_nm2_s"):
                b, c = float(np.mean([row[key] for row in bases])), float(np.mean([row[key] for row in candidates]))
                checks.append({"scope": "three_seed_actual_effort_mean", "signal": key,
                               "baseline_mean": b, "learned_mean": c, "maximum_ratio": 1.05,
                               "passed": c <= 1.05*b if b > 0. else c == 0.})
        return {"available": bool(complete), "checks": checks,
                "passed": bool(complete and all(row["passed"] for row in checks))}
    contribution = comparison("cold", True, .20)
    pd = comparison("pd", False, .05) if contribution["passed"] else {"available": False, "passed": False,
        "reason": "model_contribution_gate_not_passed", "checks": []}
    return {"model_contribution": contribution, "pd_reference": pd,
            "z2_model_contribution_gate_passed": contribution["passed"],
            "z2_pd_reference_gate_passed": pd["passed"],
            "suspended_mechanism_validation": bool(contribution["passed"] and pd["passed"]), **FLAGS}


def run_prediction(result, env_factory):
    cost, trace, trials, predictions = (result[key] for key in ("cost", "trace", "trials", "predictions"))
    result.update(seed_results=[], models={})
    for seed in SEEDS:
        seed_row = {"seed": seed, "calibration": {}, "prediction": {}, "prediction_scores": {
            "horizons": {str(h): {"models": {}} for h in HORIZONS}}}
        result["seed_results"].append(seed_row)
        trials.append(seed_row["calibration"])
        models = {}
        def initialized(trial):
            models["cold"] = CountedGuardModel(trial["qref2"], public_joint_ranges=trial["public_joint_ranges2"], cost=cost, label=f"{seed}_cold", trainable=False)
            models["learned"] = CountedGuardModel(trial["qref2"], public_joint_ranges=trial["public_joint_ranges2"], cost=cost, label=f"{seed}_learned")
            seed_row["cold_initial_snapshot"] = models["cold"].snapshot()
            seed_row["learned_initial_snapshot"] = models["learned"].snapshot()
            if models["cold"].parameter_fingerprint() != models["learned"].parameter_fingerprint():
                raise ValueError("matching_initial_model_fingerprints_required")
        def update(row):
            model = models["learned"]
            model.scope = "rls_preupdate"
            before_count = model.update_count
            cost["RLS_vector_update_attempts"] += 1
            try:
                q, v = native(row["observation_before"])
                _, next_v = native(row["observation_after"])
                row["model_update"] = model.update(q, v, row["requested_torque"][:2], next_v,
                                                    transition_id=row["transition_id"], phase="identification")
                cost["RLS_vector_update_returns"] += 1
            except BaseException as exc:
                cost["RLS_vector_update_exceptions"] += 1
                row["model_update_failure"] = failure(exc)
                raise
            finally:
                committed = model.update_count-before_count
                cost["RLS_vector_update_commits"] += committed
                cost["RLS_scalar_update_commits"] += 2*committed
                row["committed_vector_updates_this_attempt"] = committed
                row["model_snapshot_after_attempt"] = model.snapshot()
        collect_trial(seed_row["calibration"], trace, cost, seed=seed, active_steps=CALIBRATION,
                      kind="calibration", env_factory=env_factory, after_prefix=initialized, after_transition=update,
                      paid_writer=result.get("paid_writer"))
        if "learned" in models:
            seed_row["learned_snapshot_after_calibration"] = models["learned"].snapshot()
            seed_row["calibration_model_forward_accounting"] = {name: dict(model.forward_counts) for name, model in models.items()}
        if not seed_row["calibration"]["complete"] or models.get("learned") is None or models["learned"].update_count != CALIBRATION:
            seed_row["prediction"].update(status="blocked", complete=False, reason="calibration_incomplete_or_not_4000_atomic_updates")
            continue
        frozen = models["learned"].clone_frozen()
        models["learned"] = frozen
        result["models"][str(seed)] = {"cold": models["cold"].snapshot(), "learned": frozen.snapshot()}
        trials.append(seed_row["prediction"])
        collect_trial(seed_row["prediction"], trace, cost, seed=seed, active_steps=PREDICTION,
                      kind="prediction", env_factory=env_factory, expected_qref=frozen.qref,
                      expected_installation=seed_row["calibration"],
                      paid_writer=result.get("paid_writer"))
        seed_row["prediction_scores"] = score_population(seed_row["prediction"], models, predictions, cost,
                                                         scope="independent_prediction")
        seed_row["prediction_scores"]["seed"] = seed
        seed_row["prediction_model_forward_accounting"] = {name: dict(model.forward_counts) for name, model in models.items()}
    result["metrics"] = prediction_gate(result["seed_results"])


def run_control(result, env_factory, saved_models, saved_seed_results):
    cost, trace, trials, predictions = (result[key] for key in ("cost", "trace", "trials", "predictions"))
    result.update(seed_results=[], models=saved_models)
    references = {row["seed"]: row["calibration"] for row in saved_seed_results}
    if set(references) != set(SEEDS) or any(not row.get("complete") for row in references.values()):
        raise ValueError("complete_Z1_per_seed_installation_references_required")
    for seed in SEEDS:
        models = {name: restore_model(saved_models[str(seed)][name], cost, f"{seed}_{name}") for name in ("cold", "learned")}
        if models["cold"].update_count != 0 or models["learned"].update_count != CALIBRATION or models["cold"].qref != models["learned"].qref:
            raise ValueError("exact_Z1_cold_and_4000_update_learned_snapshots_required")
        seed_row = {"seed": seed, "controls": {}, "tracking_scores": {}, "conditional_prediction_scores": {}}
        result["seed_results"].append(seed_row)
        for name in ("cold", "learned", "pd", "zero"):
            trial = seed_row["controls"][name] = {}
            trials.append(trial)
            controller = None
            held_residual, held_fallback = None, True
            model_before = {n: m.parameter_fingerprint() for n, m in models.items()}
            trial["model_fingerprints_before"] = model_before
            def prepared(current):
                nonlocal controller
                if current["public_joint_ranges2"] != [list(row) for row in models["cold"].public_guard.public_joint_ranges]:
                    raise ValueError("fresh_public_ranges_differ_from_Z1_snapshot")
                selection, targets, feasible = direction_targets(current["qref2"], current["public_joint_ranges2"])
                current.update(direction_selection=selection, targets_q2=targets)
                if feasible and name in models:
                    models[name].scope = "planning"
                    controller = FastFeedbackResidualPDPairMPC(models[name], current["public_joint_ranges2"])
                    current["controller_spec"] = controller.spec()
                    current["controller_fingerprint"] = controller.parameter_fingerprint()
                return feasible
            def actor(observation, index, current):
                nonlocal held_residual, held_fallback
                q, v = native(observation)
                target = current["targets_q2"][0 if index < 1000 else 1]
                info = {"current_target_q2": target}
                if name in models:
                    if index % MACRO_HOLD == 0:
                        cost["MPC_decision_attempts"] += 1
                        try:
                            decision = controller.select(q, v, target, previous_torque=tuple(observation["previous_command"][:2]))
                        except BaseException as exc:
                            cost["MPC_decision_exceptions"] += 1
                            ledger = getattr(exc, "pair_planning_accounting", {})
                            for key in ("pd_request_attempts", "pd_request_returns", "residual_candidate_attempts"):
                                if key in ledger:
                                    cost["planning_"+key] += ledger[key]
                                else:
                                    cost["planning_"+key+"_unknown_failure_count"] += 1
                            current.setdefault("planning_failures", []).append(failure(exc))
                            raise
                        cost["MPC_decision_returns"] += 1
                        for key in ("pd_request_attempts", "pd_request_returns", "residual_candidate_attempts"):
                            cost["planning_"+key] += getattr(decision, key)
                        cost["planning_returned_candidate_rejections"] += sum(not row.feasible for row in decision.candidate_records)
                        cost["planning_fallback_returns"] += int(decision.fallback)
                        info["planning_decision"] = asdict(decision)
                        held_residual, held_fallback = decision.selected_residual_nm, decision.fallback
                    info.update(held_residual2=held_residual, held_fallback=held_fallback,
                                residual_hold_micro_index=index % MACRO_HOLD, macro_decision_index=index // MACRO_HOLD)
                    if held_fallback:
                        command = (0., 0.)
                    else:
                        base = counted_pd(q, v, target, cost, "control_"+name)
                        command = tuple(float(np.clip(base[i]+held_residual[i], -.5, .5)) for i in range(2))
                        info["public_pd_request2"] = base
                elif name == "pd":
                    command = counted_pd(q, v, target, cost, "control_pd")
                    info["public_pd_request2"] = command
                else:
                    command = (0., 0.)
                return command, info
            collect_trial(trial, trace, cost, seed=seed, active_steps=CONTROL, kind="control_"+name,
                          env_factory=env_factory, expected_qref=models["cold"].qref,
                          expected_installation=references[seed],
                          after_prefix=prepared, actor=actor, paid_writer=result.get("paid_writer"))
            trial["model_fingerprints_after_control"] = {n: m.parameter_fingerprint() for n, m in models.items()}
            seed_row["tracking_scores"][name] = tracking_score(trial)
            if name in models:
                seed_row["conditional_prediction_scores"][name] = score_population(trial, models, predictions, cost,
                                                                                   scope="control_conditional_prediction")
            model_after = {n: m.parameter_fingerprint() for n, m in models.items()}
            trial.update(model_fingerprints_before=model_before, model_fingerprints_after=model_after)
            if model_before != model_after:
                raise ValueError("frozen_control_model_changed")
        seed_row["model_forward_accounting"] = {name: dict(model.forward_counts) for name, model in models.items()}
    result["metrics"] = control_gate(result["seed_results"])


def new_result(stage):
    return {"stage": stage, "cost": Counter({key: 0 for key in (
        "control_call_attempts", "control_call_returns", "control_call_exceptions", "confirmed_physics_substeps",
        "captured_substep_endpoint_forward_returns", "RLS_vector_update_attempts", "RLS_vector_update_returns",
        "RLS_vector_update_exceptions", "RLS_vector_update_commits", "RLS_scalar_update_commits",
        "MPC_decision_attempts", "MPC_decision_returns", "MPC_decision_exceptions", "teacher_calls",
        "batch_fit_calls", "task_policy_updates", "GPU_training_seconds")}),
        "trace": [], "predictions": [], "trials": [], "seed_results": [], "models": {},
        "metrics": {"complete_population": False, "z1_prediction_gate_passed": False,
                    "z2_model_contribution_gate_passed": False, "z2_pd_reference_gate_passed": False, **FLAGS}}
