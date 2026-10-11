"""FR3A/FR3B native-only collection; no execution occurs on import.

Original free-root supine domain; no suspended snapshots. The existing atomic coupled RLS and the
body-model learning math is retained. Control uses the frozen full-first-request
9x9 grid and its dynamic held residual; no older snapshots are restored. This module
adds paid-first native/audit capture, exact forward counters, and complete-population
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
from .free_root_fast_feedback_environment import FreeRootFastFeedbackGroundBodyEnv
from .environment import MODEL_PATH
from .fast_feedback_pair_mpc import public_pd_request
from .full_request_pair_mpc import BatchedFullRequestResidualPDPairMPC

SEEDS = (8001, 8002, 8003)
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
    for key in ("pair_update_accounting", "pair_prediction_accounting", "pair_planning_accounting", "batch_execution_cost"):
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
        raise ValueError("frozen_FR3A_micro_coupled_guard_snapshot_required")
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
    if row.get("contact_audit_complete") is not True:
        return False
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


def collect_trial(trial, trace, cost, *, seed, active_steps, kind,
                  expected_qref=None, expected_installation=None, after_prefix=None,
                  actor=None, after_transition=None, paid_writer=None):
    """Original supine free-root physics; save paid native before audit or learning."""
    trial.update(trial_id=f"FR3_{seed}_{kind}", seed=seed, kind=kind, status="failed", complete=False,
                 planned_prefix=PREFIX, planned_active=active_steps, record_start=len(trace), stop=None,
                 failure=None, qref2=None, public_joint_ranges2=None, records=[])
    records, env, row, qref = trial["records"], None, None, None
    before_metadata = None
    def journal(entry_kind, item):
        if paid_writer is not None:
            paid_writer({"entry_kind": entry_kind, "record": item})
    try:
        cost["environment_constructor_attempts"] += 1
        env = FreeRootFastFeedbackGroundBodyEnv(audit_cost=cost)
        cost["environment_constructor_returns"] += 1
        cost["reset_attempts"] += 1
        observation = env.reset(seed=seed, pose="supine")
        cost["reset_returns"] += 1
        before_metadata = safe(env.frozen_metadata())
        trial["support"] = before_metadata["support"]
        asset = MODEL_PATH.read_bytes()
        cost["collector_asset_reads"] += 1
        cost["collector_asset_read_bytes"] += len(asset)
        trial["installed_xml_utf8"] = asset.decode("utf-8")
        trial["installed_xml_identity"] = identity(asset)
        trial["original_asset_unchanged_no_mount"] = True
        trial["physical_fingerprint_before"] = before_metadata["physical_fingerprint"]
        trial["execution_fingerprint_before"] = before_metadata["execution_fingerprint"]
        interface = dict(before_metadata["action_interface"])
        interface.update(actor_inputs=["current_native_qv2", "known_previous_request2", "current_target",
                                      "public_limits_and_initialized_or_learned_body_model"],
                         residual_decision_microsteps=MACRO_HOLD, predictive_horizon_microsteps=150,
                         pulse_schedule="declared_only_in_calibration_or_independent_prediction")
        trial["action_interface"] = interface
        trial["interface_fingerprint"] = hashlib.sha256(json.dumps(interface, sort_keys=True).encode()).hexdigest()
        if expected_installation is not None and any(trial[key] != expected_installation[key] for key in
                ("installed_xml_identity", "physical_fingerprint_before", "execution_fingerprint_before", "interface_fingerprint")):
            raise ValueError("same_seed_original_free_root_installation_differs_no_retry")
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
                   "returned": False, "study_abort": None, "diagnostics": None,
                   "contact_audit_complete": False, "complete_native_endpoint": False, **safe(info)}
            records.append(row)
            trace.append(row)
            before_steps = env.physics_steps
            cost["control_call_attempts"] += 1
            try:
                stepped = env.step(request)
                row["returned"] = True
                cost["control_call_returns"] += 1
            except BaseException as exc:
                cost["control_call_exceptions"] += 1
                row["collector_exception"] = failure(exc)
                raise
            finally:
                delta = env.physics_steps-before_steps
                if type(delta) is not int or delta < 0:
                    raise ValueError("invalid_substep_delta_unknown")
                row["confirmed_completed_substeps"] = delta
                cost["confirmed_physics_substeps"] += delta
            observation = stepped.observation
            row.update(observation_after=safe(observation), diagnostics=safe(stepped.diagnostics),
                       environment_terminated=bool(stepped.terminated), environment_reason=stepped.reason)
            journal("paid_native_endpoint", row)
            if delta not in (0, 1) or stepped.diagnostics.get("executed_substeps") != delta:
                raise ValueError("unexpected_paid_substep_count_preserved")
            complete = delta == 1
            if complete:
                # Preserve actual effort even if a subsequent contact query fails.
                sample = {"physics_step": env.physics_steps, "time": float(env.data.time),
                          "observation": safe(observation),
                          "actual_actuator_torque8": safe(observation["actuator_torque"]),
                          "applied_command8": safe(stepped.diagnostics["applied_torque"]),
                          "floor_contacts": [], "contact_audit_complete": False}
                row["diagnostics"]["substep_native_and_contact_records"] = [sample]
                native(observation)
                row["complete_native_endpoint"] = True
                cost["captured_native_endpoints"] += 1
                contacts = safe(env.audit_floor_pairs())
                if abs(contacts["time_s"]-(index+1)*.002) > 1e-9:
                    raise ValueError("fixed_endpoint_time_mismatch")
                row["audit_contacts"] = contacts
                sample["floor_contacts"] = [{"contact_class": pair["category"],
                    "left_arm": pair["category"] == "left_arm", "other_geom_name": pair["other_geom_name"],
                    "normal_force_n": pair["positive_normal_force_n"],
                    "signed_normal_force_n": pair["signed_normal_force_n"],
                    "distance_m": pair["distance_m"]} for pair in contacts["floor_pairs"]]
                sample["contact_audit_complete"] = row["contact_audit_complete"] = True
                row["study_abort"] = study_abort(observation, qref) if phase == "active" else None
                if row.get("current_target_q2") is not None:
                    q, _ = native(observation)
                    row["target_error_rad"] = [q[i]-row["current_target_q2"][i] for i in range(2)]
            journal("endpoint_audit_annotation", row)
            if stepped.terminated or not complete or row["study_abort"] is not None:
                trial["stop"] = {"transition_id": row["transition_id"], "environment_reason": stepped.reason,
                    "environment_terminated": bool(stepped.terminated), "study_abort": row["study_abort"],
                    "executed_substeps": delta,
                    "primary_reason": stepped.reason or ("partial_interval" if not complete else "StudyAbort")}
                break
            if not complete_telemetry(row):
                raise ValueError("complete_interval_native_effort_or_contact_telemetry_missing")
            if phase == "active" and after_transition is not None:
                after_transition(row)
            if phase == "active" and phase_index % 100 == 99:
                print(json.dumps(safe({"progress": "paid_active_block_complete", "seed": seed,
                    "phase": kind, "active_returns": phase_index+1,
                    "control_returns_total": cost["control_call_returns"],
                    "confirmed_substeps_total": cost["confirmed_physics_substeps"]}), allow_nan=False), flush=True)
        trial["status"] = "stopped" if trial["stop"] else "completed"
    except BaseException as exc:
        trial["failure"] = failure(exc)
        trial["status"] = "failed"
        if row is not None:
            try:
                journal("collector_failure_annotation", row)
            except BaseException as journal_exc:
                trial["failure"]["failure_annotation_write_failure"] = failure(journal_exc)
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
    finally:
        if env is not None:
            try:
                after_metadata = safe(env.frozen_metadata())
                trial["physical_fingerprint_after"] = after_metadata["physical_fingerprint"]
                trial["execution_fingerprint_after"] = after_metadata["execution_fingerprint"]
                trial["metadata_stable"] = before_metadata is not None and before_metadata == after_metadata
                if not trial["metadata_stable"]:
                    raise ValueError("original_free_root_configuration_changed")
            except BaseException as exc:
                trial.setdefault("finalization_failures", []).append(failure(exc))
                trial["failure"] = trial["failure"] or failure(exc)
                trial["status"] = "failed"
        trial["record_end"] = len(trace)
        trial["returned_intervals"] = sum(item.get("returned") is True for item in records)
        trial["actual_effort"], trial["floor_contact_classes"] = effort(records)
        captured = sum(values["captured_substeps"] for values in trial["actual_effort"].values())
        cost["captured_substep_endpoint_forward_returns"] += captured
        trial["complete"] = bool(len(records) == PREFIX+active_steps and trial["failure"] is None
            and trial["stop"] is None and trial.get("metadata_stable") is True
            and all(complete_telemetry(item) for item in records))
        trial["actual_effort"]["active"]["complete"] &= trial["complete"]
        trial["contact_population"] = free_root_contact_population(trial)
        trial["free_root_domain_qualification_passed"] = trial["contact_population"]["qualification_passed"]
        trial["native_execution_complete"] = trial["complete"]
        for phase, values in trial["actual_effort"].items():
            paid = sum(item.get("confirmed_completed_substeps", 0) for item in records if item["phase"] == phase)
            values["confirmed_paid_substeps"] = paid
            values["unknown_actual_effort_substeps"] = paid-values["captured_substeps"]
            values["actual_effort_population_complete"] = paid == values["captured_substeps"] and not values.get("nonfinite_or_missing_effort", False)
        trial["constructor_model_builds_and_reset_forward_attempts"] = "unmeasured_unknown_not_zero"
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
    return {"complete_population": bool(complete), "checks": checks, "fr3a_prediction_gate_passed": bool(passed),
            "mean_type": "arithmetic mean of original per_seed axis RMSE", "partial_subset_ranking": False,
            "fr3b_model_contribution_gate_passed": False, "fr3b_pd_reference_gate_passed": False,
            "fr3_free_root_mechanism_validation": False, **FLAGS}


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
    return {"model_contribution": contribution, "pd_reference": pd, "fr3a_prediction_gate_passed": False,
            "fr3b_model_contribution_gate_passed": contribution["passed"],
            "fr3b_pd_reference_gate_passed": pd["passed"],
            "fr3_free_root_mechanism_validation": bool(contribution["passed"] and pd["passed"]), **FLAGS}


def native_input_ranges(records):
    """Descriptive known input bounds; incomplete populations stay explicit."""
    bounds = {}
    for name in ("q2", "v2", "requested2", "public_guarded_applied2"):
        values = []
        for row in records:
            try:
                if name in ("q2", "v2"):
                    field = "joint_position" if name == "q2" else "joint_velocity"
                    value = np.asarray(row["observation_before"][field], dtype=float)[:2]
                elif name == "requested2":
                    value = np.asarray(row["requested_torque"], dtype=float)[:2]
                else:
                    value = np.asarray(row["diagnostics"]["applied_torque"], dtype=float)[:2]
                if value.shape == (2,) and np.isfinite(value).all():
                    values.append(value)
            except (KeyError, TypeError, ValueError):
                continue
        bounds[name] = {"planned_record_count": len(records), "known_record_count": len(values),
                        "missing_record_count": len(records)-len(values),
                        "minimum_axis": np.min(values, axis=0).tolist() if values else None,
                        "maximum_axis": np.max(values, axis=0).tolist() if values else None}
    return bounds


def free_root_contact_population(trial):
    """Count positive endpoints separately from pairs, retaining unknown samples."""
    records, active_steps = trial["records"], trial["planned_active"]
    control = trial["kind"].startswith("control_")
    spans = [("prefix", "prefix", 0, PREFIX)]
    spans += ([("target_A", "active", 0, 1000), ("target_B", "active", 1000, 2000)]
              if control else [("active", "active", 0, active_steps)])
    def summarize(name, phase, start, end, gate):
        selected = [row for row in records if row["phase"] == phase and start <= row["phase_index"] < end]
        observed = [row for row in selected if row.get("contact_audit_complete") is True]
        paid = sum(row.get("confirmed_completed_substeps", 0) for row in selected)
        result = {"name": name, "planned_count": end-start, "record_count": len(selected),
                  "confirmed_substeps": paid, "observed_contact_endpoints": len(observed),
                  "unknown_paid_contact_substeps": paid-len(observed), "classes": {},
                  "native_input_ranges": native_input_ranges(selected), "is_qualification_phase": gate}
        for category in ("left_arm", "feet", "other"):
            sums = [sum(pair["positive_normal_force_n"] for pair in row["audit_contacts"]["floor_pairs"]
                        if pair["category"] == category) for row in observed]
            positives = sum(value > 0 for value in sums)
            result["classes"][category] = {
                "positive_contact_endpoint_count": positives,
                "known_positive_fraction_of_paid_substeps": positives/paid if paid else None,
                "positive_count_unknown_if_missing": len(observed) != paid,
                "sampled_positive_duration_s": positives*.002,
                "endpoint_sample_normal_impulse_ns": sum(sums)*.002,
                "maximum_endpoint_normal_force_n": max(sums) if sums else None,
                "maximum_scope": "observed_endpoints_only_partial_is_not_full_maximum"}
        result["qualification_passed"] = bool(gate and trial["complete"] and len(selected) == end-start
            and paid == len(observed) == end-start and result["classes"]["left_arm"]["positive_contact_endpoint_count"] >= 1)
        return result
    phases = {name: summarize(name, phase, start, end, True) for name, phase, start, end in spans}
    blocks = []
    for phase, count in (("prefix", PREFIX), ("active", active_steps)):
        for start in range(0, count, 200):
            blocks.append(summarize(f"{phase}_{start}_{min(start+200, count)-1}", phase,
                                    start, min(start+200, count), False))
    return {"phases": phases, "blocks_0_4s_report_only": blocks,
            "qualification_passed": all(row["qualification_passed"] for row in phases.values()),
            "contact_causality_or_continuous_support_demonstrated": False,
            "no_contact_based_training_selection": True}


def score_qualified_population(trial, models, predictions, cost, *, scope):
    view = dict(trial)
    view["complete"] = bool(trial["complete"] and trial.get("free_root_domain_qualification_passed"))
    start = len(predictions)
    result = score_population(view, models, predictions, cost, scope=scope)
    result.update(native_execution_complete=trial["complete"],
                  free_root_domain_qualification_passed=trial.get("free_root_domain_qualification_passed", False))
    if not trial.get("free_root_domain_qualification_passed"):
        result["unavailable_reason"] = "complete_free_root_contact_domain_required"
        for row in predictions[start:]:
            row["domain_qualification_unavailable"] = True
    return result


def tracking_score_qualified(trial, *, required):
    view = dict(trial)
    view["complete"] = bool(trial["complete"] and (not required or trial.get("free_root_domain_qualification_passed")))
    result = tracking_score(view)
    result.update(native_execution_complete=trial["complete"],
                  free_root_domain_qualification_required=required,
                  free_root_domain_qualification_passed=trial.get("free_root_domain_qualification_passed", False))
    return result


def control_origin_domain(trial, calibration):
    """All active origins compared to the calibration's input q/v bounds; no selection."""
    active = [row for row in trial["records"] if row["phase"] == "active"]
    reference = calibration["contact_population"]["phases"]["active"]["native_input_ranges"]
    output = {}
    for signal, field in (("q2", "joint_position"), ("v2", "joint_velocity")):
        bounds = reference[signal]
        known, outside = 0, [0, 0]
        for row in active:
            try:
                value = np.asarray(row["observation_before"][field], dtype=float)[:2]
                if value.shape != (2,) or not np.isfinite(value).all() or bounds["minimum_axis"] is None:
                    continue
                known += 1
                for axis in range(2):
                    outside[axis] += not (bounds["minimum_axis"][axis] <= value[axis] <= bounds["maximum_axis"][axis])
            except (KeyError, TypeError, ValueError):
                continue
        output[signal] = {"planned_origins": CONTROL, "paid_origin_records": len(active),
                          "known_origins": known, "unknown_or_unattempted_origins": CONTROL-known,
                          "outside_axis_counts": outside,
                          "outside_axis_fractions_of_full_population": [n/CONTROL for n in outside] if known == CONTROL else None,
                          "not_used_to_select_origins_or_train": True}
    return output


def run_prediction(result):
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
                      kind="calibration", after_prefix=initialized, after_transition=update,
                      paid_writer=result.get("paid_writer"))
        if "learned" in models:
            seed_row["learned_snapshot_after_calibration"] = models["learned"].snapshot()
            seed_row["calibration_model_forward_accounting"] = {name: dict(model.forward_counts) for name, model in models.items()}
        if not seed_row["calibration"]["complete"] or not seed_row["calibration"].get("free_root_domain_qualification_passed") or models.get("learned") is None or models["learned"].update_count != CALIBRATION:
            seed_row["prediction"].update(status="blocked", complete=False, reason="calibration_incomplete_or_contact_domain_unqualified_or_not_4000_atomic_updates")
            continue
        frozen = models["learned"].clone_frozen()
        models["learned"] = frozen
        result["models"][str(seed)] = {"cold": models["cold"].snapshot(), "learned": frozen.snapshot()}
        trials.append(seed_row["prediction"])
        collect_trial(seed_row["prediction"], trace, cost, seed=seed, active_steps=PREDICTION,
                      kind="prediction", expected_qref=frozen.qref,
                      expected_installation=seed_row["calibration"],
                      paid_writer=result.get("paid_writer"))
        seed_row["prediction_scores"] = score_qualified_population(seed_row["prediction"], models, predictions, cost,
                                                         scope="independent_prediction")
        seed_row["prediction_scores"]["seed"] = seed
        seed_row["prediction_model_forward_accounting"] = {name: dict(model.forward_counts) for name, model in models.items()}
    result["metrics"] = prediction_gate(result["seed_results"])


def run_control(result, saved_models, saved_seed_results):
    cost, trace, trials, predictions = (result[key] for key in ("cost", "trace", "trials", "predictions"))
    result.update(seed_results=[], models=saved_models)
    references = {row["seed"]: row["calibration"] for row in saved_seed_results}
    if set(references) != set(SEEDS) or any(not row.get("complete") or not row.get("free_root_domain_qualification_passed") for row in references.values()):
        raise ValueError("complete_FR3A_per_seed_installation_references_required")
    for seed in SEEDS:
        models = {name: restore_model(saved_models[str(seed)][name], cost, f"{seed}_{name}") for name in ("cold", "learned")}
        if models["cold"].update_count != 0 or models["learned"].update_count != CALIBRATION or models["cold"].qref != models["learned"].qref:
            raise ValueError("exact_FR3A_cold_and_4000_update_learned_snapshots_required")
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
                    raise ValueError("fresh_public_ranges_differ_from_FR3A_snapshot")
                selection, targets, feasible = direction_targets(current["qref2"], current["public_joint_ranges2"])
                current.update(direction_selection=selection, targets_q2=targets)
                if feasible and name in models:
                    models[name].scope = "planning"
                    controller = BatchedFullRequestResidualPDPairMPC(models[name], current["public_joint_ranges2"],
                                                              counted_model_type=CountedGuardModel)
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
                        finally:
                            batch = dict(getattr(controller, "last_batch_execution", {}))
                            current.setdefault("batch_execution_records", []).append(
                                {"active_index": index, **batch})
                            for key, value in batch.items():
                                cost["planning_batch_"+key] += value
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
                          expected_qref=models["cold"].qref,
                          expected_installation=references[seed],
                          after_prefix=prepared, actor=actor, paid_writer=result.get("paid_writer"))
            trial["model_fingerprints_after_control"] = {n: m.parameter_fingerprint() for n, m in models.items()}
            trial["control_origin_domain"] = control_origin_domain(trial, references[seed])
            seed_row["tracking_scores"][name] = tracking_score_qualified(trial, required=name != "zero")
            if name in models:
                seed_row["conditional_prediction_scores"][name] = score_qualified_population(trial, models, predictions, cost,
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
        "metrics": {"complete_population": False, "fr3a_prediction_gate_passed": False,
                    "fr3b_model_contribution_gate_passed": False, "fr3b_pd_reference_gate_passed": False,
                    "fr3_free_root_mechanism_validation": False, **FLAGS}}
