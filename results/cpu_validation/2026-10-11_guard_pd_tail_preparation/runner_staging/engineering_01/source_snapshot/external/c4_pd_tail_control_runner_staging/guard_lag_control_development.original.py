"""Independent E collector: restored frozen lag models, explicit native history.

Formal collection requires a clean byte-bound source commit. Engineering callers must
explicitly supply a hand-written environment and planner; no old runner patches.
Scientific gates belong to the independent auditor, never this collector.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import gzip
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import subprocess
import sys
import time
import zipfile

import mujoco
import numpy as np

from developmental_physics.collect import _archive_record, _exception_snapshot, _write_json
from developmental_physics.environment import ExplorationConfig, GroundBodyEnv, MODEL_PATH
from developmental_physics.feedback_validate import pd_request
from developmental_physics.guard_pair_development import (
    PredictionMeter, native_pair, native_study_abort, _rmse, _counts, _error,
    PD_SELECTION_PATH, PD_MANIFEST_PATH, PD_AUDIT_PATH, PD_PROTOCOL_PATH,
)
from developmental_physics.guard_lag_pair_model import GuardLagPairBodyModel
from developmental_physics.local_pair_model import _parameter_state
from developmental_physics.pd_selection_binding import load_pd_binding
from developmental_physics.probes import direction_record


FORMAL_CONTROL_ENABLED = True
SOURCE_PATH = "src/developmental_physics/guard_lag_control_development.py"
MPC_SOURCE_PATH = "src/developmental_physics/guard_lag_pair_mpc.py"
PROTOCOL_PATH = "docs/GUARD_LAG_CONTROL_DEVELOPMENT_PROTOCOL.md"
AUDITOR_PATH = "scripts/audit_guard_lag_control.py"
AUDITOR_SUPPORT_PATHS = ("scripts/audit_guard_lag_offline.py",
    "scripts/audit_guard_coupled_development.py", "scripts/audit_guard_pair_development.py",
    "scripts/audit_pair_frozen.py", "scripts/audit_local_frozen.py")
D_ROOT = "results/cpu_validation/2026-10-11_guard_lag_offline"
D_COMMIT = "f7710c7b048dccab3e436d1fa16432f881a35992"
C_COMMIT = "5ea8df42b09588845760daf0dc1f270aef2a87f1"
C_ENVIRONMENT_FINGERPRINT = "102adc9d013aec72db9355eecfd21031a7868ad5129817c6157ae65542ac225e"
D_HASHES = {
    "manifest.json": "38df6b99e15c3667a33d6c9995a8efd664f70ce59be8a511fa49def59727a4d7",
    "first_audit.json": "668e6ec65c949f4d7a87349e5b6076dcfeae1d53e9f770364ae4fec943b15da5",
    "read_accounting_reconciliation/first_reconciliation.json": "5b9fe0a4b443cab5bcc97dc4b735caef42655780ca39ed061f0560c7a87c46d0",
    "summary_once/summary.json": "dbcfcb53194f2bfa6a634cecb5c5df72a69f9892a42d828fbdf44d08b2930016",
    "raw/diagnostics.json": "9307f3f37d5a3c23ef6f9097d8c352a9fc7f2e34e562b5cf4e7075e20bbbe130",
    "raw/manifest.json": "f5d6e0fc017d708a8c8b2b03a6876704248afee92266985ebd5d137267acb3c6",
}
SEEDS = (0, 1, 2)
RESET_SEEDS = {0: 3757552657, 1: 1641411168, 2: 2001025171}
KINDS = ("cold11", "learned_sparse11", "PDselected", "zero")
MODEL_NAMES = ("cold11", "learned_sparse11")
PREFIX_STEPS, CONTROL_STEPS = 100, 200
JOINT_INDICES = (0, 1)
PHASES = ("prefix", "control")
EFFORT_KEYS = ("requested_absolute_nm_s", "requested_squared_nm2_s",
              "actual_absolute_nm_s", "actual_squared_nm2_s")
PLANNING_KEYS = ("pair_prediction_attempts", "pair_prediction_successes",
                 "scalar_prediction_attempts", "scalar_prediction_successes",
                 "failed_pair_prediction_attempts", "unknown_scalar_failure_count")


def _emit(writer, row):
    writer.write(json.dumps(_archive_record(row), allow_nan=False)+"\n")
    writer.flush()


def _failure(exc):
    record = {"error": _error(exc)}
    for key in ("pair_prediction_accounting", "pair_planning_accounting"):
        if hasattr(exc, key):
            record[key] = getattr(exc, key)
    if hasattr(exc, "to_dict"):
        record["structured_failure"] = exc.to_dict()
    return record


def target_pair(active, qref, directions, ranges):
    if type(active) is not int or not 0 <= active < CONTROL_STEPS:
        raise ValueError("active index outside fixed 200-step target task")
    target = tuple(qref[i]+directions[i]*(.04 if active < 100 else .08) for i in range(2))
    if any(not ranges[i][0]+.03 <= target[i] <= ranges[i][1]-.03 for i in range(2)):
        raise ValueError("predeclared target infeasible; no clipping")
    return target


def restore_lag_snapshot(snapshot):
    """Restore bytes of a published D state; no predict/update/refit calls."""
    if (snapshot.get("vector_update_count") != 400 or snapshot.get("scalar_update_count") != 800
            or snapshot.get("output_update_counts") != [400, 400]):
        raise ValueError("D sparse complete 400-vector state required")
    ranges = snapshot["input_mapping"]["public_guard"]["public_joint_ranges_rad"]
    model = GuardLagPairBodyModel(snapshot["qref_rad"], public_joint_ranges=ranges, trainable=False)
    theta, covariance = np.asarray(snapshot["coefficients"], dtype=np.float64), np.asarray(snapshot["covariance"], dtype=np.float64)
    if (theta.shape != (2, 11) or covariance.shape != (2, 11, 11)
            or not np.isfinite(theta).all() or not np.isfinite(covariance).all()):
        raise ValueError("finite complete 11D state required")
    model._state = _parameter_state(theta.copy(), covariance.copy(), 400)
    expected = dict(snapshot)
    expected["trainable"] = False
    if model.snapshot() != expected:
        raise ValueError("D full snapshot/fingerprint/constants differ; no repair")
    return model


def load_d_models(repository_root):
    """Read only six pinned E dependencies; never D rollout/fit/audit replay."""
    root = Path(repository_root)/D_ROOT
    blobs, records, docs = {}, {}, {}
    for relative, expected in D_HASHES.items():
        data = (root/relative).read_bytes()
        actual = hashlib.sha256(data).hexdigest()
        if actual != expected:
            raise ValueError(f"sealed D byte binding mismatch: {relative}")
        blobs[f"{D_ROOT}/{relative}"] = data
        records[relative] = {"sha256": actual, "bytes": len(data)}
        docs[relative] = json.loads(data)
    manifest = docs["manifest.json"]
    for relative in D_HASHES:
        if relative == "manifest.json":
            continue
        if any(manifest["files"][relative].get(k) != records[relative][k] for k in ("sha256", "bytes")):
            raise ValueError("D root manifest disagrees with pinned selected payload")
    first = docs["first_audit.json"]
    rec = docs["read_accounting_reconciliation/first_reconciliation.json"]
    summary = docs["summary_once/summary.json"]
    if (first.get("failed") != 1 or first.get("violations") != [
            {"check": "exact_source_or_causal_identity", "location": "runner_original_read_accounting"}]
            or rec.get("checks") != 50 or rec.get("failed") != 0
            or rec.get("first_audit_sha256") != D_HASHES["first_audit.json"]
            or rec.get("byte_only_reconciliation_verified") is not True
            or rec.get("effective_data_consistency_verified") is not True
            or summary.get("source_commit") != D_COMMIT
            or summary.get("binding_checks") != {"checks": 51, "failed": 0}
            or summary.get("effective_data_consistency_verified") is not True
            or docs["raw/manifest.json"].get("status") != "completed"):
        raise ValueError("original D failed1/reconciliation/summary evidence required")
    diagnostic_record = docs["raw/manifest.json"]["files"]["diagnostics.json"]
    if diagnostic_record["sha256"] != D_HASHES["raw/diagnostics.json"]:
        raise ValueError("D raw diagnostics identity mismatch")
    models, snapshots = {}, {}
    for seed in SEEDS:
        matches = [x for x in docs["raw/diagnostics.json"] if x["seed"] == seed and x["calibration"] == "sparse"]
        completed = [x for x in summary["calibrations"] if x["seed"] == seed and x.get("kind", x.get("calibration")) == "sparse"]
        if len(matches) != 1 or len(completed) != 1 or completed[0].get("completed") is not True:
            raise ValueError("one complete D sparse model per declared seed required")
        learned = restore_lag_snapshot(matches[0]["lag11_final_snapshot"])
        cold = GuardLagPairBodyModel(learned.qref, public_joint_ranges=learned.public_guard.public_joint_ranges, trainable=False)
        models[seed] = {"cold11": cold, "learned_sparse11": learned}
        snapshots[seed] = {k: v.snapshot() for k, v in models[seed].items()}
    binding = {"root": D_ROOT, "collection_commit": D_COMMIT, "original_C_commit": C_COMMIT,
               "records": records, "first_audit_failed": 1, "reconciliation_checks": 50,
               "effective_data_consistency_verified": True, "refits": 0, "predictions": 0,
               "offline_updates": 0, "restored_models": 3, "cold_model_initializations": 3,
               "restore_initialization_compute": "nonzero object construction, array copying, complete snapshot and fingerprint checks; no predict/update calls",
               "selected_snapshot_path": "raw/diagnostics.json:[seed,sparse].lag11_final_snapshot",
               "payload_bytes_read": sum(x["bytes"] for x in records.values())}
    return models, snapshots, binding, blobs


def episode_plan(seed, kind):
    return {"trial_id": f"seed{seed}_{kind}", "seed": seed, "kind": kind,
            "maximum_control_steps": PREFIX_STEPS+CONTROL_STEPS, "status": "planned", "completed": False,
            "reason": None, "control_calls_attempted": 0, "control_steps": 0, "physics_steps": 0,
            "phase_budgets": {p: {"control_calls_attempted": 0, "control_steps": 0, "physics_steps": 0} for p in PHASES}}


def native_history(endpoints, observation, trial_id, step_index):
    """Only two complete consecutive past returned native endpoints qualify."""
    if len(endpoints) != 2:
        raise ValueError("two real native history endpoints required; no zero fill")
    prior, current = endpoints
    if (any(x["trial_id"] != trial_id or x["executed_substeps"] != 10 or x["stopped"] for x in endpoints)
            or [x["step_index"] for x in endpoints] != [step_index-2, step_index-1]
            or native_pair(prior["observation_after"]) != native_pair(current["observation_before"])
            or native_pair(current["observation_after"]) != native_pair(observation)):
        raise ValueError("native history incomplete/discontinuous/stopped; no repair")
    return {"current_v_rad_s": native_pair(observation)[1],
            "previous_v_rad_s": native_pair(prior["observation_after"])[1],
            "history_transition_ids": [x["transition_id"] for x in endpoints], "native_contiguous": True}


def bind_prefix(result, models, episode, env, observation, plant, endpoints):
    q, v = native_pair(observation)
    limits = [env.model.joint(name).range for name in env.joint_names]
    selections = [direction_record(j, observation["joint_position"], limits) for j in JOINT_INDICES]
    directions = tuple(x["direction"] for x in selections)
    ranges = tuple(tuple(float(x) for x in limits[j]) for j in JOINT_INDICES)
    for model in models.values():
        if model.trainable or model.qref != q or model.public_guard.public_joint_ranges != ranges:
            raise ValueError("fresh prefix differs from bound D qref/ranges or model not frozen; no repair")
    if plant != result["expected_environment_fingerprint"]:
        raise ValueError("fresh plant differs from original C/D condition")
    history = native_history(endpoints, observation, episode["trial_id"], PREFIX_STEPS)
    binding = {"reference_q": q, "native_velocity": v, "direction": directions,
               "selection_records": selections, "public_joint_ranges": ranges,
               "environment_fingerprint": plant, "source_native_pair_exact": True,
               "initial_history": history,
               "prefix98_endpoint": endpoints[0]["observation_after"],
               "prefix99_endpoint": endpoints[1]["observation_after"]}
    if "reference_q" in result:
        if (q, v, directions, ranges, plant) != (tuple(result["reference_q"]), tuple(result["native_prefix_velocity"]),
                tuple(result["direction"]), tuple(tuple(x) for x in result["public_joint_ranges"]), result["environment_fingerprint_before"]):
            raise ValueError("fresh E prefixes differ; no auto alignment")
    else:
        result.update(reference_q=q, native_prefix_velocity=v, direction=directions,
                      public_joint_ranges=ranges, selection_records=selections, environment_fingerprint_before=plant)
    result["fresh_prefix_bindings"][episode["kind"]] = binding
    return ranges


def run_trial(result, models, episode, writer, pd, *, env_factory, mpc_factory=None):
    """One fresh fixed trial; explicit injection is for small engineering fixtures."""
    if tuple(models) != MODEL_NAMES or episode["kind"] not in KINDS:
        raise ValueError("exact two fixed predictors and one declared control group required")
    if tuple(pd["kp"]) != (64., 64.) or tuple(pd["kd"]) != (0., 4.):
        raise ValueError("original selected PD gains required")
    kind, seed, trial_id = episode["kind"], result["seed"], episode["trial_id"]
    env = previous = observation = requested = stepped = None
    index = target = raw_pd = decision = history = planner_input = None
    phase, plant = "prefix", None
    study = error = trace_failure = fatal = planner = None
    planner_fingerprint_before = None
    predicted, inputs, endpoints = {}, {}, []
    returned_steps = written_steps = unreturned_physics = 0
    q_errors, partial_errors, partial_prediction = [], [], []
    prediction_errors = {}
    meter = PredictionMeter()
    per_model_meter = {n: PredictionMeter() for n in MODEL_NAMES}
    before_models = {n: m.parameter_fingerprint() for n, m in models.items()}
    effort = {p: {key: np.zeros(2) for key in EFFORT_KEYS} for p in PHASES}
    known_actual = {p: 0 for p in PHASES}
    planning = {key: 0 for key in PLANNING_KEYS}
    failed_planners = unknown_planners = fallbacks = input_projection_calls = 0
    saturation = np.zeros(2, dtype=int)
    planner_seconds, pd_seconds = [], []
    try:
        env = env_factory(ExplorationConfig())
        observation = env.reset(seed=result["reset_seed"], pose="supine")
        native_pair(observation)
        plant = env.parameter_fingerprint()
        previous_torque = (0., 0.)
        for index in range(PREFIX_STEPS+CONTROL_STEPS):
            previous = observation
            phase = "prefix" if index < PREFIX_STEPS else "control"
            requested = np.zeros(8)
            target = raw_pd = decision = stepped = history = planner_input = None
            predicted, inputs = {}, {}
            if index == PREFIX_STEPS:
                ranges = bind_prefix(result, models, episode, env, observation, plant, endpoints)
                if kind in MODEL_NAMES:
                    if mpc_factory is None:
                        raise ValueError("explicit lag-aware MPC factory required")
                    planner = mpc_factory(models[kind], ranges)
                    planner_fingerprint_before = planner.parameter_fingerprint()
            q, v = native_pair(observation)
            if phase == "control":
                history = native_history(endpoints, observation, trial_id, index)
                previous_v = tuple(history["previous_v_rad_s"])
                target = target_pair(index-PREFIX_STEPS, result["reference_q"], result["direction"], result["public_joint_ranges"])
                if planner is not None:
                    planner_input = {"q": q, "v": v, "previous_v": previous_v,
                                     "target_q": target, "previous_torque": previous_torque}
                    timer = time.perf_counter()
                    try:
                        decision = planner.select(q, v, target, previous_v, previous_torque=previous_torque)
                    except BaseException as exc:
                        failed_planners += 1
                        counts = getattr(exc, "pair_planning_accounting", None)
                        if counts is None:
                            unknown_planners += 1
                        else:
                            for key, value in _counts(counts).items():
                                planning[key] += value
                        raise
                    finally:
                        planner_seconds.append(time.perf_counter()-timer)
                    for key, value in _counts(decision.to_dict()).items():
                        planning[key] += value
                    requested[list(JOINT_INDICES)] = decision.torque
                    fallbacks += int(decision.fallback)
                elif kind == "PDselected":
                    timer = time.perf_counter()
                    try:
                        pairs = [pd_request(q[i], v[i], target[i], pd["kp"][i], pd["kd"][i]) for i in range(2)]
                        requested[list(JOINT_INDICES)] = tuple(x[0] for x in pairs)
                        raw_pd = tuple(x[1] for x in pairs)
                    finally:
                        pd_seconds.append(time.perf_counter()-timer)
                if not np.isfinite(requested).all() or np.max(np.abs(requested)) > .5:
                    raise ValueError("request violates original per-axis .5 Nm permission")
                command = tuple(float(requested[j]) for j in JOINT_INDICES)
                for name, model in models.items():
                    projection = model.public_guard.project(q, command)
                    input_projection_calls += 1
                    inputs[name] = {**projection.to_dict(), "input_basis": "known_angle_guard",
                                    "model_feature_command_nm": projection.projected_start_nm,
                                    "native_v_rad_s": v, "previous_v_rad_s": previous_v,
                                    "history_transition_ids": history["history_transition_ids"]}
                    prediction = meter.call(per_model_meter[name].call, model.predict, q, v, command, previous_v)
                    if np.asarray(prediction).shape != (2, 2) or not np.isfinite(prediction).all():
                        raise ValueError("invalid returned independent diagnostic prediction")
                    predicted[name] = prediction
            old_control, old_physics = env.step_id, env.physics_steps
            budget = episode["phase_budgets"][phase]
            budget["control_calls_attempted"] += 1
            try:
                stepped = env.step(requested)
            except BaseException:
                unreturned_physics += env.physics_steps-old_physics
                raise
            finally:
                paid = env.physics_steps-old_physics
                budget["control_steps"] += env.step_id-old_control
                budget["physics_steps"] += paid
                u = requested[list(JOINT_INDICES)]
                effort[phase]["requested_absolute_nm_s"] += np.abs(u)*paid*env.config.physics_dt
                effort[phase]["requested_squared_nm2_s"] += u**2*paid*env.config.physics_dt
            observation = stepped.observation
            returned_steps += 1
            next_q, next_v = native_pair(observation)
            if phase == "control":
                study = native_study_abort(next_q, next_v, result["reference_q"])
                if study is not None:
                    study.update(phase=phase, step_index=index)
            executed = stepped.diagnostics["executed_substeps"]
            if type(executed) is not int or executed != env.physics_steps-old_physics:
                raise RuntimeError("returned substeps differ from paid physics")
            realized = np.asarray(stepped.diagnostics["applied_torque_history"], dtype=float)
            if executed == 0 and realized.size == 0:
                realized = realized.reshape((0, 8))
            if (realized.shape != (executed, 8) or not np.isfinite(realized).all()
                    or np.max(np.abs(realized), initial=0.) > .5):
                raise RuntimeError("actual history invalid; missing effort remains unknown")
            selected = realized[:, list(JOINT_INDICES)]
            effort[phase]["actual_absolute_nm_s"] += np.sum(np.abs(selected), axis=0)*env.config.physics_dt
            effort[phase]["actual_squared_nm2_s"] += np.sum(selected**2, axis=0)*env.config.physics_dt
            known_actual[phase] += executed
            if phase == "control":
                if executed == 10:
                    q_errors.append([next_q[i]-target[i] for i in range(2)])
                    saturation += np.asarray([abs(requested[j]) == .5 for j in JOINT_INDICES], dtype=int)
                    for name, prediction in predicted.items():
                        scores = prediction_errors.setdefault(name, {"q": [], "v": []})
                        scores["q"].append([next_q[i]-prediction[0][i] for i in range(2)])
                        scores["v"].append([next_v[i]-prediction[1][i] for i in range(2)])
                else:
                    partial_errors.append({"step_index": index, "target_q": target, "executed_substeps": executed,
                                           "errors_rad": [next_q[i]-target[i] for i in range(2)]})
                    for name, prediction in predicted.items():
                        partial_prediction.append({"step_index": index, "model": name, "executed_substeps": executed,
                            "position_error_rad": [next_q[i]-prediction[0][i] for i in range(2)],
                            "velocity_error_rad_s": [next_v[i]-prediction[1][i] for i in range(2)]})
            row = {"trial_id": trial_id, "seed": seed, "kind": kind, "joint_indices": JOINT_INDICES,
                "shared_transition_id": f"{trial_id}:{index}", "step_index": index, "phase": phase,
                "study_abort": study, "target_q": target, "history": history,
                "partial_interval_target_error_rad": None if executed == 10 or target is None else [next_q[i]-target[i] for i in range(2)],
                "requested_torque": requested, "planned_torque": requested.copy(), "raw_pd_torque_nm": raw_pd,
                "exploration_diagnostics": None,
                "observation_before": previous, "observation_after": observation,
                "predicted_next_qv": predicted, "model_input_diagnostics": inputs, "model_update": None,
                "model_fingerprints": {n: m.parameter_fingerprint() for n, m in models.items()},
                "diagnostics": stepped.diagnostics, "planner_input": planner_input,
                "planner_decision": None if decision is None else decision.to_dict(),
                "diagnostic_prediction_accounting": meter.snapshot(),
                "qpos": env.data.qpos, "qvel": env.data.qvel}
            try:
                _emit(writer, row)
            except BaseException as exc:
                trace_failure = exc
                raise
            written_steps += 1
            endpoints = (endpoints+[{"trial_id": trial_id, "step_index": index, "transition_id": row["shared_transition_id"],
                "executed_substeps": executed, "stopped": stepped.terminated or study is not None,
                "observation_before": previous, "observation_after": observation}])[-2:]
            previous_torque = tuple(float(requested[j]) for j in JOINT_INDICES)
            if stepped.terminated or study is not None:
                break
            if executed != 10:
                raise RuntimeError("partial source endpoint cannot continue planning")
        if env.parameter_fingerprint() != plant:
            raise RuntimeError("plant changed during trial")
        if before_models != {n: m.parameter_fingerprint() for n, m in models.items()}:
            raise RuntimeError("evaluation changed frozen model parameters")
        if planner is not None and planner.parameter_fingerprint() != planner_fingerprint_before:
            raise RuntimeError("evaluation changed frozen planner")
    except BaseException as exc:
        error = _error(exc)
        episode["failure_accounting"] = _failure(exc)
        try:
            _emit(writer, {"trial_id": trial_id, "seed": seed, "kind": kind,
                "shared_transition_id": None if index is None else f"{trial_id}:{index}", "phase": phase,
                "step_index": index, "collector_exception": error, "study_abort": study,
                "requested_torque": requested, "planned_torque": requested, "target_q": target,
                "raw_pd_torque_nm": raw_pd, "exploration_diagnostics": None, "history": history, "planner_input": planner_input,
                "observation_before": previous, "observation_after": observation,
                "predicted_next_qv": predicted, "model_input_diagnostics": inputs,
                "frozen_model_snapshots": {n: m.snapshot() for n, m in models.items()},
                "failure_accounting": _failure(exc), "diagnostic_prediction_accounting": meter.snapshot(),
                "returned_step_diagnostics": None if stepped is None else stepped.diagnostics,
                "planner_decision": None if decision is None else decision.to_dict(),
                **_exception_snapshot(env)})
        except BaseException as write_exc:
            trace_failure = trace_failure or write_exc
            episode["exception_trace_write_error"] = _error(write_exc)
        if isinstance(exc, (KeyboardInterrupt, SystemExit, OSError)) or trace_failure is not None:
            fatal = exc
    finally:
        full = env is not None and env.step_id == 300 and env.physics_steps == 3000
        terminated = env is not None and (env.terminated or study is not None)
        completed = error is None and full and not terminated
        status = "exception" if error else "terminated" if terminated else "completed" if completed else "incomplete"
        reason = env.reason if env is not None and env.terminated else study if study is not None else error
        known = {p: known_actual[p] == episode["phase_budgets"][p]["physics_steps"] for p in PHASES}
        missing = {p: episode["phase_budgets"][p]["physics_steps"]-known_actual[p] for p in PHASES}
        after_models = {n: m.parameter_fingerprint() for n, m in models.items()}
        episode.update(_archive_record({"status": status, "completed": completed, "reason": reason,
            "collector_exception": error, "study_abort": study,
            "environment_terminated": None if env is None else env.terminated,
            "environment_stop_reason": None if env is None else env.reason,
            **{key: sum(b[key] for b in episode["phase_budgets"].values()) for key in ("control_calls_attempted", "control_steps", "physics_steps")},
            "returned_steps": returned_steps, "written_returned_steps": written_steps,
            "returned_unwritten_steps": returned_steps-written_steps, "unreturned_physics_steps": unreturned_physics,
            "trace_write_failure": None if trace_failure is None else _error(trace_failure),
            "risk_telemetry_complete": error is None and unreturned_physics == 0 and trace_failure is None,
            "environment_fingerprint_before": plant, "environment_fingerprint_after": None if env is None else env.parameter_fingerprint()}))
        result["evaluations"][kind] = _archive_record({
            "status": status, "completed": completed, "reason": reason, "collector_exception": error,
            "study_abort": study, "environment_terminated": episode["environment_terminated"],
            "environment_stop_reason": episode["environment_stop_reason"],
            "tracking_rmse": _rmse(q_errors), "metric_control_step_count": len(q_errors),
            "position_prediction_rmse": {n: _rmse(x["q"]) for n, x in prediction_errors.items()},
            "velocity_prediction_rmse": {n: _rmse(x["v"]) for n, x in prediction_errors.items()},
            "metric_prediction_step_count": {n: len(x["v"]) for n, x in prediction_errors.items()},
            "partial_interval_target_errors_rad": partial_errors, "partial_endpoint_prediction_errors": partial_prediction,
            "phase_effort": effort, "control_effort": effort["control"],
            "phase_effort_combined": {p: {key: float(value.sum()) for key, value in effort[p].items()} for p in PHASES},
            "phase_actual_effort_substeps": known_actual, "phase_actual_effort_complete": known,
            "phase_missing_actual_effort_substeps": missing, "actual_effort_complete": known["control"],
            "actual_effort_is_lower_bound": not known["control"], "actual_control_effort_substeps": known_actual["control"],
            "missing_control_effort_substeps": missing["control"],
            "diagnostic_prediction_accounting": meter.snapshot(),
            "diagnostic_prediction_accounting_per_model": {n: x.snapshot() for n, x in per_model_meter.items()},
            "diagnostic_input_projection_pair_calls": input_projection_calls,
            "planning_accounting": {**planning, "scalar_counts_complete": unknown_planners == 0 and planning["unknown_scalar_failure_count"] == 0,
                "scalar_counts_is_lower_bound": unknown_planners > 0 or planning["unknown_scalar_failure_count"] > 0,
                "unknown_failed_planner_calls": unknown_planners},
            "failed_planner_attempts": failed_planners, "planner_attempt_count": len(planner_seconds),
            "planner_decision_count": len(planner_seconds)-failed_planners, "planner_fallbacks": fallbacks,
            "saturated_control_steps_per_axis": saturation, "controller_seconds_total": sum(planner_seconds),
            "pd_seconds_total": sum(pd_seconds), "planner_spec": None if planner is None else planner.spec(),
            "planner_fingerprint_before": planner_fingerprint_before,
            "planner_fingerprint_after": None if planner is None else planner.parameter_fingerprint(),
            "models_before": before_models, "models_after": after_models,
            "model_fingerprint_before": before_models.get(kind), "model_fingerprint_after": after_models.get(kind),
            "model_updates": 0, "frozen_model_snapshots": {n: m.snapshot() for n, m in models.items()}})
    if fatal is not None:
        raise fatal


def _formal_provenance(root, protocol_path):
    if Path(__file__).resolve() != (root/SOURCE_PATH).resolve() or protocol_path != (root/PROTOCOL_PATH).resolve():
        raise RuntimeError("exact frozen tracked E runner and protocol required")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    status = subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=all"], cwd=root, text=True)
    if status:
        raise RuntimeError("clean tracked HEAD required before D/PD reads or physics")
    tracked = set(subprocess.check_output(["git", "ls-files"], cwd=root, text=True).splitlines())
    pd_bytes = (root/PD_PROTOCOL_PATH).read_bytes()
    pd = load_pd_binding(root, expected_selection_path=PD_SELECTION_PATH, expected_manifest_path=PD_MANIFEST_PATH,
        expected_audit_path=PD_AUDIT_PATH, expected_protocol={"path": PD_PROTOCOL_PATH, "sha256": hashlib.sha256(pd_bytes).hexdigest()}, tracked_paths=tracked)
    sources = pd.archive_source_bytes()
    sources[PD_PROTOCOL_PATH] = pd_bytes
    paths = [*sorted((root/"src/developmental_physics").glob("*.py")), MODEL_PATH, root/"pyproject.toml", protocol_path,
             root/AUDITOR_PATH, *(root/name for name in AUDITOR_SUPPORT_PATHS)]
    for path in paths:
        name = path.relative_to(root).as_posix()
        if name not in tracked:
            raise RuntimeError(f"required E dependency untracked: {name}")
        sources[name] = path.read_bytes()
    if MPC_SOURCE_PATH not in sources:
        raise RuntimeError("independent lag-aware MPC source missing")
    for name, data in sources.items():
        if data != subprocess.check_output(["git", "show", f"{commit}:{name}"], cwd=root):
            raise RuntimeError(f"E source differs from HEAD: {name}")
    return commit, sources, pd


def run_guard_lag_control_development(output, *, protocol_path=None):
    if not FORMAL_CONTROL_ENABLED:
        raise RuntimeError("ignored staging E collector is not authorized for formal physical execution")
    root = Path(__file__).resolve().parents[2]
    protocol_path = (root/PROTOCOL_PATH).resolve() if protocol_path is None else Path(protocol_path).resolve()
    output = Path(output)
    if output.exists():
        raise FileExistsError("one-attempt E output must not exist; failures are never overwritten")
    output.mkdir(parents=True)
    started_wall, started_cpu = time.perf_counter(), time.process_time()
    episodes = [episode_plan(seed, kind) for seed in SEEDS for kind in KINDS]
    results = [{"seed": seed, "reset_seed": RESET_SEEDS[seed], "evaluations": {}, "fresh_prefix_bindings": {}} for seed in SEEDS]
    fatal = None
    metadata = {"schema_version": 1, "suite": "guard_lag_control_development", "synthetic_fixture": False,
        "status": "started", "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "seeds": SEEDS, "kinds": KINDS, "pose": "supine", "joint_indices": JOINT_INDICES,
        "prefix_steps": 100, "control_steps_per_trial": 200,
        "maximum_control_calls": 3600, "maximum_physics_steps": 36000,
        "maximum_diagnostic_pair_predictions": 4800, "maximum_diagnostic_scalar_predictions": 9600,
        "maximum_planning_pair_predictions": 1458000, "maximum_planning_scalar_predictions": 2916000,
        "model_updates": 0, "policy_parameter_updates": 0, "gain_updates": 0, "gate_updates": 0,
        "D_refits": 0, "D_prediction_reexecutions": 0, "gpu": None, "backend": "MuJoCo CPU",
        "frozen_model_clone_attempts": 0, "frozen_model_clone_returns": 0,
        "cloning_compute": "nonzero object construction and immutable parameter copying; not predictions or RLS",
        "split": "development", "native_joint_count": 8, "parameter_count_per_output": 11,
        "integration": "endpoint_euler", "model_input_basis": "known_angle_guard",
        "planned_episode_count": 12, "planned_episodes": [{k: x[k] for k in ("trial_id", "seed", "kind", "maximum_control_steps")} for x in episodes],
        "study_abort_spec": {"active_only": True, "absolute_q_minus_qref_rad": .12,
            "absolute_velocity_rad_s": 1., "comparison": ">=", "any_axis": True,
            "feedback_action": None, "complete_terminal_scored_not_complete": True},
        "c4_scientifically_validated": False}

    def save():
        metadata.update({key: sum(x.get(key, 0) for x in episodes) for key in ("control_calls_attempted", "control_steps", "physics_steps")})
        metadata.update(completed_trials=sum(x["status"] == "completed" for x in episodes),
            terminated_trials=sum(x["status"] == "terminated" for x in episodes),
            exception_trials=sum(x["status"] == "exception" for x in episodes),
            blocked_trials=sum(x["status"] == "blocked" for x in episodes))
        errors = []
        for name, payload in (("episodes.json", episodes), ("seed_results.json", results), ("metadata.json", metadata)):
            try:
                _write_json(output/name, _archive_record(payload) if isinstance(payload, dict) else [_archive_record(x) for x in payload])
            except BaseException as exc:
                errors.append(exc)
        if errors:
            raise errors[0]

    try:
        save()
        commit, sources, pd_binding = _formal_provenance(root, protocol_path)
        models_by_seed, snapshots, d_binding, d_blobs = load_d_models(root)
        for result in results:
            seed = result["seed"]
            result.update(expected_environment_fingerprint=C_ENVIRONMENT_FINGERPRINT, frozen_models=snapshots[seed],
                model_source={"D_commit": D_COMMIT, "snapshot_binding": d_binding["selected_snapshot_path"], "new_updates": 0})
        # D byte sources are pinned separately; clean provenance also covers
        # their tracked source bytes before any environment is constructed.
        for name, data in d_blobs.items():
            if data != subprocess.check_output(["git", "show", f"{commit}:{name}"], cwd=root):
                raise RuntimeError(f"sealed D dependency differs from E HEAD: {name}")
        sources.update(d_blobs)
        metadata.update(source_commit=commit, source_dirty=False, source_status="", protocol={"path": PROTOCOL_PATH, "sha256": hashlib.sha256(sources[PROTOCOL_PATH]).hexdigest()},
            source_sha256={name: hashlib.sha256(data).hexdigest() for name, data in sources.items()},
            D_binding=d_binding, pd_binding=dict(pd_binding), pd_gains={"kp": pd_binding["kp"], "kd": pd_binding["kd"]},
            environment_config=asdict(ExplorationConfig()), mujoco_version=mujoco.__version__,
            dependencies=dict(sorted((x.metadata["Name"], x.version) for x in importlib.metadata.distributions())))
        with zipfile.ZipFile(output/"source_snapshot.zip", "w", zipfile.ZIP_DEFLATED) as archive:
            for name, data in sources.items():
                archive.writestr(name, data)
        snapshot_zip = (output/"source_snapshot.zip").read_bytes()
        metadata["source_snapshot_sha256"] = hashlib.sha256(snapshot_zip).hexdigest()
        metadata["independent_auditor"] = {"path": AUDITOR_PATH, "sha256": metadata["source_sha256"][AUDITOR_PATH], "required_for_formal": True}
        pd = {"kp": pd_binding["kp"], "kd": pd_binding["kd"]}
        from developmental_physics.guard_lag_pair_mpc import FixedGuardLagPairMPC
        with gzip.open(output/"trace.jsonl.gz", "wt", encoding="utf-8") as writer:
            for seed in SEEDS:
                result = next(x for x in results if x["seed"] == seed)
                for episode in [x for x in episodes if x["seed"] == seed]:
                    # Independent immutable copies prevent an exceptional
                    # engineering caller from contaminating another trial.
                    trial_models = {}
                    for name, model in models_by_seed[seed].items():
                        metadata["frozen_model_clone_attempts"] += 1
                        trial_models[name] = model.clone_frozen()
                        metadata["frozen_model_clone_returns"] += 1
                    run_trial(result, trial_models, episode, writer, pd, env_factory=GroundBodyEnv, mpc_factory=FixedGuardLagPairMPC)
                    save()
        metadata["status"] = "completed"
    except BaseException as exc:
        fatal = exc
        metadata.update(status="exception", collector_exception=_error(exc), failure_accounting=_failure(exc))
        for episode in episodes:
            if episode["status"] == "planned":
                episode.update(status="blocked", reason="earlier_fatal_or_source_failure", completed=False)
                result = next(x for x in results if x["seed"] == episode["seed"])
                result["evaluations"][episode["kind"]] = {"status": "blocked", "completed": False,
                    "reason": episode["reason"], "model_updates": 0, "control_calls_attempted": 0,
                    "control_steps": 0, "physics_steps": 0}
        raise
    finally:
        metadata.update(wall_seconds=time.perf_counter()-started_wall, cpu_seconds=time.process_time()-started_cpu,
                        python=sys.version, platform=platform.platform())
        try:
            save()
            records = {}
            for path in output.iterdir():
                if path.is_file() and path.name != "manifest.json":
                    data = path.read_bytes()
                    records[path.name] = {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
            _write_json(output/"manifest.json", {"schema_version": 1, "status": metadata["status"], "files": records})
        except BaseException as exc:
            metadata["final_checkpoint_exception"] = _error(exc)
            if fatal is None:
                raise
    return metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run_guard_lag_control_development(args.output), indent=2))


if __name__ == "__main__":
    main()
