"""Frozen C4 C: independent same-model calibrations with two fixed exploration rules.

Formal execution requires clean tracked source/protocol/auditor at HEAD.
Artificial fixtures replace the environment explicitly; no A/B replay or raw reads.
Scientific gates belong to the separate independent auditor, never this runner.
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

from developmental_physics.collect import _archive_record, _exception_snapshot, _hash, _write_json
from developmental_physics.environment import ExplorationConfig, GroundBodyEnv, MODEL_PATH
from developmental_physics.feedback_validate import pd_request
from developmental_physics.guard_pair_development import (
    PredictionMeter, native_pair, native_study_abort, _rmse, _counts, _error,
    PD_SELECTION_PATH, PD_MANIFEST_PATH, PD_AUDIT_PATH, PD_PROTOCOL_PATH,
)
from developmental_physics.guard_coupled_pair_model import GuardCoupledPairBodyModel
from developmental_physics.local_pair_model import FixedPairMPC
from developmental_physics.pd_selection_binding import load_pd_binding
from developmental_physics.probes import direction_record

FORMAL_EXECUTION_FROZEN = True
_REAL_ENV = GroundBodyEnv
DEVELOPMENT_SEEDS = (0, 1, 2)
RESET_SEEDS = {0: 3757552657, 1: 1641411168, 2: 2001025171}
JOINT_INDICES = (0, 1)
KINDS = ("calibration_sparse", "calibration_continuation", "prediction", "nominal_guard",
         "learned_sparse", "learned_continuation", "PDselected", "zero")
MPC_KINDS = ("nominal_guard", "learned_sparse", "learned_continuation")
PREFIX_STEPS, CALIBRATION_STEPS, PREDICTION_STEPS, CONTROL_STEPS = 100, 400, 100, 200
SOURCE_PATH = "src/developmental_physics/guard_exploration_development.py"
PROTOCOL_PATH = "docs/GUARD_EXPLORATION_DEVELOPMENT_PROTOCOL.md"
AUDITOR_PATH = "scripts/audit_guard_exploration_development.py"
AUDITOR_SUPPORT_PATHS = ("scripts/audit_guard_coupled_development.py",
    "scripts/audit_guard_pair_development.py", "scripts/audit_pair_frozen.py",
    "scripts/audit_local_frozen.py")
PHASES = ("prefix", "calibration", "prediction", "control")
EFFORT_KEYS = ("requested_absolute_nm_s", "requested_squared_nm2_s",
               "actual_absolute_nm_s", "actual_squared_nm2_s")
PLANNING_KEYS = ("pair_prediction_attempts", "pair_prediction_successes",
    "scalar_prediction_attempts", "scalar_prediction_successes",
    "failed_pair_prediction_attempts", "unknown_scalar_failure_count")


def exploration_command(kind, active, directions, native_q, native_v, qref):
    """Pure pre-step schedule and per-axis veto; never query physics or a model."""
    if kind not in KINDS[:3]:
        raise ValueError("exploration is restricted to calibration or prediction")
    duration = PREDICTION_STEPS if kind == "prediction" else CALIBRATION_STEPS
    if type(active) is not int or not 0 <= active < duration:
        raise ValueError("active index outside predeclared exploration")
    s, q, v, ref = (np.asarray(value, dtype=float) for value in
                    (directions, native_q, native_v, qref))
    if any(value.shape != (2,) or not np.isfinite(value).all() for value in (s, q, v, ref)):
        raise ValueError("finite original two-axis values required")
    if not np.isin(s, (-1., 1.)).all():
        raise ValueError("each public direction must be -1 or 1")
    block, slot = divmod(active, 20)
    if kind == "prediction":
        shape = ((1., 0.), (0., 1.), (1., 1.), (1., -1.), (1., 1.))[block]
        amplitude = (.125, .25, .375, .5, .375)[block]
    else:
        shape = ((1., 0.), (0., 1.), (1., 1.), (1., -1.))[block//5]
        amplitude = (.125, .25, .375, .5, .25)[block % 5]
    continuation = kind != "calibration_sparse"
    pulse = (1. if slot in ((0, 1) if continuation else (0,)) else
             (-1. if slot in ((10, 11) if continuation else (10,)) else 0.))
    planned_pair = amplitude*pulse*s*np.asarray(shape)
    velocity_veto = np.abs(v) >= .5 if continuation else np.zeros(2, dtype=bool)
    position_veto = np.abs(q-ref) >= .06 if continuation else np.zeros(2, dtype=bool)
    nonzero = planned_pair != 0.
    vetoed = nonzero & (velocity_veto | position_veto)
    requested_pair = np.where(vetoed, 0., planned_pair)
    planned, requested = np.zeros(8), np.zeros(8)
    planned[list(JOINT_INDICES)], requested[list(JOINT_INDICES)] = planned_pair, requested_pair
    diagnostic = {"schema": "c4-exploration-command-v1",
        "rule": "continuation_2_8_native_veto" if continuation else "sparse_1_9",
        "active_index": active, "block_index": block, "slot_index": slot,
        "amplitude_nm": amplitude, "shape": list(shape), "native_q_rad": q.tolist(),
        "native_v_rad_s": v.tolist(), "qref_rad": ref.tolist(),
        "planned_nm": planned_pair.tolist(), "requested_nm": requested_pair.tolist(),
        "planned_nonzero": nonzero.tolist(), "velocity_veto": velocity_veto.tolist(),
        "position_veto": position_veto.tolist(), "command_vetoed": vetoed.tolist(),
        "velocity_threshold_rad_s": .5 if continuation else None,
        "position_threshold_rad": .06 if continuation else None,
        "comparison": ">=" if continuation else None, "physical_queries": 0,
        "future_actual_input": False, "learned_gate": False}
    return planned, requested, diagnostic


def _runtime():
    return {"environment_config": asdict(ExplorationConfig()),
        "dependencies": dict(sorted((d.metadata["Name"], d.version)
                                     for d in importlib.metadata.distributions())),
        "mujoco_version": mujoco.__version__}


def _formal_provenance(root, protocol_path):
    if Path(__file__).resolve() != (root / SOURCE_PATH).resolve():
        raise RuntimeError("formal collector must run from its frozen tracked path")
    if protocol_path != (root / PROTOCOL_PATH).resolve() or not protocol_path.is_file():
        raise ValueError("exact frozen C protocol required")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    status = subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=all"],
                                     cwd=root, text=True)
    if status:
        raise RuntimeError("formal execution requires clean tracked HEAD before PD reads or physics")
    tracked = set(subprocess.check_output(["git", "ls-files"], cwd=root, text=True).splitlines())
    pd_protocol_bytes = (root / PD_PROTOCOL_PATH).read_bytes()
    pd = load_pd_binding(root, expected_selection_path=PD_SELECTION_PATH,
        expected_manifest_path=PD_MANIFEST_PATH, expected_audit_path=PD_AUDIT_PATH,
        expected_protocol={"path": PD_PROTOCOL_PATH,
                           "sha256": hashlib.sha256(pd_protocol_bytes).hexdigest()},
        tracked_paths=tracked)
    sources = pd.archive_source_bytes()
    sources[PD_PROTOCOL_PATH] = pd_protocol_bytes
    paths = [*sorted((root / "src/developmental_physics").glob("*.py")), MODEL_PATH,
        root / "pyproject.toml", protocol_path, root / AUDITOR_PATH,
        *(root / name for name in AUDITOR_SUPPORT_PATHS)]
    for path in paths:
        name = path.relative_to(root).as_posix()
        if name not in tracked or not path.is_file():
            raise RuntimeError(f"required frozen dependency missing or untracked: {name}")
        sources[name] = path.read_bytes()
    for name, data in sources.items():
        if name not in tracked or data != subprocess.check_output(["git", "show", f"{commit}:{name}"], cwd=root):
            raise RuntimeError(f"source differs from clean HEAD: {name}")
    return commit, status, sources, pd


def _failure(exc):
    record = {"error": _error(exc)}
    for name in ("pair_update_accounting", "pair_prediction_accounting", "pair_planning_accounting"):
        if hasattr(exc, name):
            record[name] = getattr(exc, name)
    if hasattr(exc, "to_dict"):
        record["structured_failure"] = exc.to_dict()
    return record


def _emit(writer, row):
    writer.write(json.dumps(_archive_record(row), allow_nan=False)+"\n")


def _bind_prefix(result, models, episode, env, observation, plant):
    q, v = native_pair(observation)
    limits = [env.model.joint(name).range for name in env.joint_names]
    selections = [direction_record(j, observation["joint_position"], limits) for j in JOINT_INDICES]
    directions = tuple(r["direction"] for r in selections)
    ranges = tuple(tuple(float(x) for x in limits[j]) for j in JOINT_INDICES)
    binding = {"reference_q": q, "native_velocity": v, "direction": directions,
        "selection_records": selections, "public_joint_ranges": ranges,
        "environment_fingerprint": plant, "source_native_pair_exact": True}
    if "reference_q" not in result:
        result.update(reference_trial_id=episode["trial_id"], reference_q=q,
            native_prefix_velocity=v, native_prefix_observation=observation,
            direction=directions, selection_records=selections, public_joint_ranges=ranges,
            environment_fingerprint_before=plant)
        models["nominal_guard"] = GuardCoupledPairBodyModel(q, public_joint_ranges=ranges, trainable=False)
        result["nominal_model"] = models["nominal_guard"].snapshot()
    else:
        expected = (tuple(result["reference_q"]), tuple(result["native_prefix_velocity"]),
            tuple(result["direction"]), tuple(tuple(r) for r in result["public_joint_ranges"]),
            result["environment_fingerprint_before"])
        if (q, v, directions, ranges, plant) != expected:
            raise RuntimeError("fresh native prefix qref/v/direction/ranges/plant differs; no repair")
    result["fresh_prefix_bindings"][episode["kind"]] = binding
    return q, ranges


def run_trial(result, models, episode, writer, pd):
    """One paid fresh trial; independent calibration failures remain local."""
    kind, seed = episode["kind"], result["seed"]
    is_cal, is_pred = kind.startswith("calibration_"), kind == "prediction"
    learning_name = kind.removeprefix("calibration_") if is_cal else None
    model_name = f"learned_{learning_name}" if is_cal else kind
    duration = CALIBRATION_STEPS if is_cal else (PREDICTION_STEPS if is_pred else CONTROL_STEPS)
    env = previous = observation = requested = planned = stepped = None
    index = target = raw_pd = decision = update = exploration = None
    study = error = trace_failure = planner = calibrator = None
    phase, plant, fatal = "prefix", None, None
    predicted, inputs = {}, {}
    returned_steps = written_steps = unreturned_physics = 0
    q_errors, partial_errors, partial_prediction = [], [], []
    prediction_errors = {}
    meter, rls_meter = PredictionMeter(), PredictionMeter()
    before_models = {n: m.parameter_fingerprint() for n, m in models.items()}
    effort = {p: {key: np.zeros(2) for key in EFFORT_KEYS} for p in PHASES}
    known_actual = {p: 0 for p in PHASES}
    planning = {key: 0 for key in PLANNING_KEYS}
    unknown_planners = failed_planners = fallbacks = 0
    saturation, veto_count = np.zeros(2, dtype=int), np.zeros(2, dtype=int)
    planner_seconds, pd_seconds = [], []
    available = []
    excitation = {"complete_intervals": 0, "nonzero_start_guard_intervals_per_axis": np.zeros(2, dtype=int),
        "planned_absolute_nm_s": np.zeros(2), "planned_squared_nm2_s": np.zeros(2),
        "requested_absolute_nm_s": np.zeros(2), "requested_squared_nm2_s": np.zeros(2),
        "start_guard_absolute_nm_s": np.zeros(2), "start_guard_squared_nm2_s": np.zeros(2),
        "actual_absolute_nm_s": np.zeros(2), "actual_squared_nm2_s": np.zeros(2)}
    cal = None
    if is_cal:
        cal = result["calibrations"][learning_name] = {"status": "running", "completed": False,
            "reason": None, "initial_model": None, "model_snapshot": None, "frozen_model": None,
            "source_transition_ids": [], "attempted_vector_updates": 0,
            "committed_vector_updates": 0, "committed_scalar_updates": 0,
            "rls_prediction_accounting": rls_meter.snapshot()}

    def sync_calibration():
        if cal is not None:
            cal.update(model_snapshot=None if calibrator is None else calibrator.snapshot(),
                committed_vector_updates=0 if calibrator is None else calibrator.update_count,
                committed_scalar_updates=0 if calibrator is None else calibrator.scalar_update_count,
                rls_prediction_accounting=rls_meter.snapshot())

    try:
        env = GroundBodyEnv(ExplorationConfig())
        observation = env.reset(seed=result["reset_seed"], pose="supine")
        native_pair(observation)
        plant = env.parameter_fingerprint()
        previous_torque = (0., 0.)
        for index in range(PREFIX_STEPS+duration):
            previous = observation
            phase = "prefix" if index < PREFIX_STEPS else ("calibration" if is_cal else
                    ("prediction" if is_pred else "control"))
            requested, planned = np.zeros(8), np.zeros(8)
            target = raw_pd = decision = update = exploration = stepped = None
            predicted, inputs = {}, {}
            if index == PREFIX_STEPS:
                q0, ranges = _bind_prefix(result, models, episode, env, observation, plant)
                if is_cal:
                    calibrator = GuardCoupledPairBodyModel(q0, public_joint_ranges=ranges)
                    rls_meter.bind_rls(calibrator)
                    cal["initial_model"] = calibrator.snapshot()
                    sync_calibration()
                else:
                    before_models = {n: m.parameter_fingerprint() for n, m in models.items()}
                available = [n for n in MPC_KINDS if n in models] if is_pred else []
                if kind in MPC_KINDS:
                    if models[kind].trainable or models[kind].qref != q0:
                        raise RuntimeError("control requires its own matching frozen model")
                    planner = FixedPairMPC(models[kind], ranges)
            q, v = native_pair(observation)
            if phase != "prefix":
                active = index-PREFIX_STEPS
                if is_cal or is_pred:
                    planned, requested, exploration = exploration_command(kind, active,
                        result["direction"], q, v, result["reference_q"])
                    veto_count += np.asarray(exploration["command_vetoed"], dtype=int)
                else:
                    target = tuple(result["reference_q"][i]+result["direction"][i]
                                   * (.04 if active < 100 else .08) for i in range(2))
                    ranges = result["public_joint_ranges"]
                    if any(not ranges[i][0]+.03 <= target[i] <= ranges[i][1]-.03 for i in range(2)):
                        raise ValueError("predeclared target infeasible; no clipping")
                    if planner is not None:
                        timer = time.perf_counter()
                        try:
                            decision = planner.select(q, v, target, previous_torque=previous_torque)
                        except BaseException as exc:
                            failed_planners += 1
                            cost = getattr(exc, "pair_planning_accounting", None)
                            if cost is None:
                                unknown_planners += 1
                            else:
                                for key, value in _counts(cost).items():
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
                    planned = requested.copy()
                if not np.isfinite(requested).all() or np.max(np.abs(requested)) > .5:
                    raise ValueError("request violates shared per-axis .5 Nm permission")
                command = tuple(float(requested[j]) for j in JOINT_INDICES)
                active_models = ({n: models[n] for n in available} if is_pred else
                                 ({kind: models[kind]} if kind in MPC_KINDS else {}))
                for name, model in active_models.items():
                    predicted[name] = meter.call(model.predict, q, v, command)
                if is_pred or kind in MPC_KINDS:
                    predicted["persistence"] = (tuple(q[i]+.02*v[i] for i in range(2)), v)
                input_models = {model_name: calibrator} if is_cal else active_models
                inputs = {n: m.describe_input(q, command) for n, m in input_models.items()}
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
            if phase != "prefix":
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
                raise RuntimeError("native actual history invalid; missing effort remains unknown")
            selected = realized[:, list(JOINT_INDICES)]
            effort[phase]["actual_absolute_nm_s"] += np.sum(np.abs(selected), axis=0)*env.config.physics_dt
            effort[phase]["actual_squared_nm2_s"] += np.sum(selected**2, axis=0)*env.config.physics_dt
            known_actual[phase] += executed
            if phase != "prefix":
                if executed == 10:
                    if is_cal or is_pred:
                        start_g = np.asarray(next(iter(inputs.values()))["model_feature_command_nm"])
                        excitation["complete_intervals"] += 1
                        excitation["nonzero_start_guard_intervals_per_axis"] += (start_g != 0.).astype(int)
                        for label, values in (("planned", planned[list(JOINT_INDICES)]),
                                              ("requested", requested[list(JOINT_INDICES)]), ("start_guard", start_g)):
                            excitation[f"{label}_absolute_nm_s"] += np.abs(values)*.02
                            excitation[f"{label}_squared_nm2_s"] += values**2*.02
                        excitation["actual_absolute_nm_s"] += np.sum(np.abs(selected), axis=0)*env.config.physics_dt
                        excitation["actual_squared_nm2_s"] += np.sum(selected**2, axis=0)*env.config.physics_dt
                    if is_cal:
                        transition_id = f"{episode['trial_id']}:{index}"
                        cal["attempted_vector_updates"] += 1
                        cal["source_transition_ids"].append(transition_id)
                        try:
                            update = calibrator.update(q, v, command, next_v,
                                transition_id=transition_id, phase="identification")
                        finally:
                            sync_calibration()
                        pre = update["preupdate_prediction"]
                        predicted[model_name] = (tuple(pre["next_q_rad"]), tuple(pre["next_v_rad_s"]))
                    for name, prediction in predicted.items():
                        scores = prediction_errors.setdefault(name, {"q": [], "v": []})
                        scores["q"].append([next_q[i]-prediction[0][i] for i in range(2)])
                        scores["v"].append([next_v[i]-prediction[1][i] for i in range(2)])
                    if target is not None:
                        q_errors.append([next_q[i]-target[i] for i in range(2)])
                        saturation += np.asarray([abs(requested[j]) == .5 for j in JOINT_INDICES], dtype=int)
                else:
                    if target is not None:
                        partial_errors.append({"step_index": index, "target_q": target,
                            "errors_rad": [next_q[i]-target[i] for i in range(2)], "executed_substeps": executed})
                    for name, prediction in predicted.items():
                        partial_prediction.append({"step_index": index, "model": name, "executed_substeps": executed,
                            "position_error_rad": [next_q[i]-prediction[0][i] for i in range(2)],
                            "velocity_error_rad_s": [next_v[i]-prediction[1][i] for i in range(2)]})
                    if is_cal:
                        update = {"updated": False, "phase": "partial_calibration_interval", "executed_substeps": executed}
            row = {"trial_id": episode["trial_id"], "seed": seed, "kind": kind,
                "joint_indices": JOINT_INDICES, "shared_transition_id": f"{episode['trial_id']}:{index}",
                "step_index": index, "phase": phase, "study_abort": study, "target_q": target,
                "partial_interval_target_error_rad": None if executed == 10 or target is None
                    else [next_q[i]-target[i] for i in range(2)],
                "requested_torque": requested, "planned_torque": planned, "raw_pd_torque_nm": raw_pd,
                "exploration_diagnostics": exploration, "observation_before": previous,
                "observation_after": observation, "predicted_next_qv": predicted,
                "model_input_diagnostics": inputs, "model_update": update,
                "model_snapshot_after": None if calibrator is None else calibrator.snapshot(),
                "available_models": available if is_pred else [],
                "model_fingerprints": {n: models[n].parameter_fingerprint() for n in available},
                "diagnostics": stepped.diagnostics,
                "planner_decision": None if decision is None else decision.to_dict(),
                "qpos": env.data.qpos, "qvel": env.data.qvel}
            try:
                _emit(writer, row)
            except BaseException as exc:
                trace_failure = exc
                raise
            written_steps += 1
            previous_torque = tuple(float(requested[j]) for j in JOINT_INDICES)
            if stepped.terminated or study is not None:
                break
        if env.parameter_fingerprint() != plant:
            raise RuntimeError("plant changed during trial")
        if not is_cal and before_models != {n: m.parameter_fingerprint() for n, m in models.items()}:
            raise RuntimeError("evaluation changed frozen model parameters")
    except BaseException as exc:
        error = _error(exc)
        episode["failure_accounting"] = _failure(exc)
        try:
            _emit(writer, {"trial_id": episode["trial_id"], "seed": seed, "kind": kind,
                "shared_transition_id": None if index is None else f"{episode['trial_id']}:{index}",
                "phase": phase, "step_index": index, "collector_exception": error,
                "study_abort": study, "requested_torque": requested, "planned_torque": planned,
                "exploration_diagnostics": exploration, "target_q": target, "raw_pd_torque_nm": raw_pd,
                "observation_before": previous, "observation_after": observation,
                "predicted_next_qv": predicted, "model_input_diagnostics": inputs,
                "model_update": update, "model_snapshot_after": None if calibrator is None else calibrator.snapshot(),
                "frozen_model_snapshot": models[kind].snapshot() if kind in models else None,
                "failure_accounting": _failure(exc), "diagnostic_prediction_accounting": meter.snapshot(),
                "rls_prediction_accounting": rls_meter.snapshot() if is_cal else {},
                "available_models": available, "model_fingerprints": {n: models[n].parameter_fingerprint() for n in available},
                "returned_step_diagnostics": None if stepped is None else stepped.diagnostics,
                "planner_decision": None if decision is None else decision.to_dict(), **_exception_snapshot(env)})
        except BaseException as write_exc:
            trace_failure = trace_failure or write_exc
            episode["exception_trace_write_error"] = _error(write_exc)
        if isinstance(exc, (KeyboardInterrupt, SystemExit, OSError)) or trace_failure is not None:
            fatal = exc
    finally:
        full = (env is not None and env.step_id == PREFIX_STEPS+duration
                and env.physics_steps == 10*(PREFIX_STEPS+duration))
        terminated = env is not None and (env.terminated or study is not None)
        completed = error is None and full and not terminated
        status = "exception" if error is not None else ("terminated" if terminated else
                 ("completed" if completed else "incomplete"))
        reason = env.reason if env is not None and env.terminated else (study if study is not None else error)
        known = {p: known_actual[p] == episode["phase_budgets"][p]["physics_steps"] for p in PHASES}
        missing = {p: episode["phase_budgets"][p]["physics_steps"]-known_actual[p] for p in PHASES}
        sync_calibration()
        if is_cal:
            calibrated = completed and calibrator is not None and calibrator.update_count == CALIBRATION_STEPS
            cal.update(status=status, completed=calibrated, reason=reason,
                excitation=excitation, command_veto_count_per_axis=veto_count)
            if calibrated:
                models[model_name] = calibrator.clone_frozen()
                cal["frozen_model"] = models[model_name].snapshot()
                result["learned_models"][model_name] = models[model_name].snapshot()
        episode.update(_archive_record({"status": status, "completed": completed, "reason": reason,
            "collector_exception": error, "study_abort": study,
            "environment_terminated": None if env is None else env.terminated,
            "environment_stop_reason": None if env is None else env.reason,
            "control_calls_attempted": sum(b["control_calls_attempted"] for b in episode["phase_budgets"].values()),
            "control_steps": sum(b["control_steps"] for b in episode["phase_budgets"].values()),
            "physics_steps": sum(b["physics_steps"] for b in episode["phase_budgets"].values()),
            "returned_steps": returned_steps, "written_returned_steps": written_steps,
            "returned_unwritten_steps": returned_steps-written_steps, "unreturned_physics_steps": unreturned_physics,
            "trace_write_failure": None if trace_failure is None else _error(trace_failure),
            "risk_telemetry_complete": error is None and unreturned_physics == 0 and trace_failure is None,
            "environment_fingerprint_before": plant,
            "environment_fingerprint_after": None if env is None else env.parameter_fingerprint()}))
        after_models = {n: m.parameter_fingerprint() for n, m in models.items()}
        result["evaluations"][kind] = _archive_record({
            "status": status, "completed": completed, "reason": reason, "collector_exception": error,
            "study_abort": study, "environment_terminated": episode["environment_terminated"],
            "environment_stop_reason": episode["environment_stop_reason"],
            "tracking_rmse": _rmse(q_errors), "metric_control_step_count": len(q_errors),
            "position_prediction_rmse": {n: _rmse(x["q"]) for n, x in prediction_errors.items()},
            "velocity_prediction_rmse": {n: _rmse(x["v"]) for n, x in prediction_errors.items()},
            "metric_prediction_step_count": {n: len(x["v"]) for n, x in prediction_errors.items()},
            "partial_interval_target_errors_rad": partial_errors,
            "partial_endpoint_prediction_errors": partial_prediction, "phase_effort": effort,
            "control_effort": effort["control"],
            "phase_effort_combined": {p: {key: float(values.sum()) for key, values in effort[p].items()} for p in PHASES},
            "phase_actual_effort_substeps": known_actual, "phase_actual_effort_complete": known,
            "phase_missing_actual_effort_substeps": missing, "actual_effort_complete": known["control"],
            "actual_effort_is_lower_bound": not known["control"], "actual_control_effort_substeps": known_actual["control"],
            "missing_control_effort_substeps": missing["control"],
            "diagnostic_prediction_accounting": meter.snapshot(),
            "planning_accounting": {**planning, "scalar_counts_complete": unknown_planners == 0 and planning["unknown_scalar_failure_count"] == 0,
                "scalar_counts_is_lower_bound": unknown_planners > 0 or planning["unknown_scalar_failure_count"] > 0,
                "unknown_failed_planner_calls": unknown_planners},
            "failed_planner_attempts": failed_planners, "planner_attempt_count": len(planner_seconds),
            "planner_decision_count": len(planner_seconds)-failed_planners, "planner_fallbacks": fallbacks,
            "saturated_control_steps_per_axis": saturation, "controller_seconds_total": sum(planner_seconds),
            "pd_seconds_total": sum(pd_seconds), "planner_spec": None if planner is None else planner.spec(),
            "models_before": before_models, "models_after": after_models,
            "model_fingerprint_before": before_models.get(kind), "model_fingerprint_after": after_models.get(kind),
            "model_updates": 0 if not is_cal or calibrator is None else calibrator.scalar_update_count,
            "available_models": available if is_pred else [],
            "model_availability": {n: ("available" if n in available else "unavailable") for n in MPC_KINDS} if is_pred else {},
            "excitation": excitation if is_cal or is_pred else None,
            "command_veto_count_per_axis": veto_count if is_cal or is_pred else None})
    if fatal is not None:
        raise fatal


def run_guard_exploration_development(output, *, protocol_path, synthetic=False,
                                      synthetic_source_bytes=None, synthetic_pd_binding=None):
    if not synthetic and not FORMAL_EXECUTION_FROZEN:
        raise RuntimeError("draft C real execution disabled until root freezes protocol, source and auditor")
    if synthetic:
        if GroundBodyEnv is _REAL_ENV:
            raise RuntimeError("synthetic execution requires an explicitly replaced environment")
        if not isinstance(synthetic_source_bytes, dict) or not synthetic_source_bytes:
            raise RuntimeError("explicit source fixture required; no Git/source fallback")
        if any(not isinstance(n, str) or not isinstance(b, bytes) for n, b in synthetic_source_bytes.items()):
            raise ValueError("synthetic sources require string names and original bytes")
        if PROTOCOL_PATH not in synthetic_source_bytes:
            raise ValueError("explicit fixture must include literal C protocol path")
        pd = synthetic_pd_binding
        if not isinstance(pd, dict) or pd.get("status") != "selected" or pd.get("selected_id") is None:
            raise ValueError("synthetic PD selection fixture required")
        for key in ("kp", "kd"):
            values = np.asarray(pd.get(key), dtype=float)
            if values.shape != (2,) or not np.isfinite(values).all() or np.any(values < 0):
                raise ValueError("fixture must supply two finite nonnegative selected PD gains")
    elif synthetic_source_bytes is not None or synthetic_pd_binding is not None:
        raise ValueError("formal PD/sources must be verified internally")
    output = Path(output)
    if output.exists():
        raise FileExistsError(output)
    root = next(p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file())
    protocol_path = Path(protocol_path).resolve()
    if synthetic:
        commit, status, sources = "synthetic-fixture-no-git", "", dict(synthetic_source_bytes)
    else:
        commit, status, sources, pd = _formal_provenance(root, protocol_path)
    plans = [{"trial_id": f"seed{seed}_{kind}", "seed": seed, "kind": kind,
        "maximum_control_steps": PREFIX_STEPS+(CALIBRATION_STEPS if kind.startswith("calibration_") else
                                              (PREDICTION_STEPS if kind == "prediction" else CONTROL_STEPS))}
        for seed in DEVELOPMENT_SEEDS for kind in KINDS]
    episodes = [{**p, "status": "planned", "completed": False, "reason": None,
        "control_calls_attempted": 0, "control_steps": 0, "physics_steps": 0,
        "phase_budgets": {phase: {"control_calls_attempted": 0, "control_steps": 0, "physics_steps": 0}
                          for phase in PHASES}} for p in plans]
    metadata = {"schema_version": 1, "suite": "guard_exploration_development", "synthetic": synthetic,
        "created_at_utc": datetime.now(timezone.utc).isoformat(), "purpose": __doc__,
        "seeds": list(DEVELOPMENT_SEEDS), "reset_seeds": RESET_SEEDS, "split": "development", "pose": "supine",
        "joint_indices": list(JOINT_INDICES), "native_joint_count": 8, "source_commit": commit,
        "source_status": status, "source_dirty": bool(status),
        "source_sha256": {n: hashlib.sha256(b).hexdigest() for n, b in sources.items()},
        "protocol": {"path": PROTOCOL_PATH, "sha256": hashlib.sha256(sources[PROTOCOL_PATH]).hexdigest()},
        "platform": sys.platform if synthetic else platform.platform(),
        "python_executable": sys.executable, "python_version": sys.version, **_runtime(),
        "gpu": None, "backend": "synthetic, no physics" if synthetic else "MuJoCo CPU",
        "structures": ["coupled_hinge9"], "model_input_basis": "known_angle_guard",
        "parameter_count_per_output": 9, "integration": "endpoint_euler",
        "model_input": "current original q/v, final known request and public ranges only; own-start G recomputed",
        "model_label": "next original encoder velocity on complete own calibration intervals only",
        "calibration_data_shared": False, "prior_a_b_raw_replayed": False,
        "guard_interval_boundary": "start G is not future actual torque or interval guard average",
        "target_information": "current qref+s*.04 then qref+s*.08 only; no preview/clipping",
        "study_abort_spec": {"active_only": True, "absolute_q_minus_qref_rad": .12,
            "absolute_velocity_rad_s": 1., "comparison": ">=", "any_axis": True,
            "feedback_action": None, "complete_terminal_scored_not_complete": True},
        "exploration_rules": {"sparse": "1+/9zero/1-/9zero", "continuation": "2+/8zero/2-/8zero + native q/v veto"},
        "exploration_veto_spec": {"velocity_rad_s": .5, "q_minus_qref_rad": .06, "comparison": ">=",
            "per_axis": True, "applied_kinds": ["calibration_continuation", "prediction"], "control_applied": False},
        "minimum_excitation_qualification": {"calibration_each_axis_nonzero_start_G_count_min": 1,
            "calibration_each_axis_actual_absolute_effort_strictly_positive": True,
            "prediction_each_axis_nonzero_start_G_count_min": 1, "rank_threshold": None},
        "prefix_steps": PREFIX_STEPS, "calibration_steps": CALIBRATION_STEPS,
        "prediction_steps": PREDICTION_STEPS, "control_steps_per_trial": CONTROL_STEPS,
        "planned_episodes": plans, "planned_episode_count": 24,
        "maximum_control_steps": 8100, "maximum_physics_steps": 81000,
        "maximum_vector_updates": 2400, "maximum_scalar_updates": 4800,
        "maximum_rls_internal_prediction_pair_calls": 2400,
        "maximum_independent_prediction_pair_calls": 900,
        "maximum_control_diagnostic_prediction_pair_calls": 1800,
        "maximum_mpc_prediction_pair_calls": 2187000,
        "prediction_accounting_scope": "RLS-internal, common prediction, control diagnostic and MPC separately; no reporting repeat",
        "pd_binding": dict(pd), "pd_gains": {"kp": pd["kp"], "kd": pd["kd"]},
        "policy_parameter_updates": 0, "gain_updates": 0, "gate_updates": 0,
        "teacher_calls": 0, "external_demonstration_samples": 0,
        "scientific_gates": "strict predeclared C scope; separate independent auditor required",
        "claim_boundary": "development-only exploration mechanism; no new holdout, skill, adaptation, safety or true-robot claim",
        "archive_status": "running", "complete": False}
    output.mkdir(parents=True)
    with zipfile.ZipFile(output / "source_snapshot.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in sources.items():
            archive.writestr(name, data)
    metadata["source_snapshot_sha256"] = _hash(output / "source_snapshot.zip")
    metadata["independent_auditor"] = {"path": AUDITOR_PATH,
        "sha256": metadata["source_sha256"].get(AUDITOR_PATH), "pending": synthetic, "required_for_formal": True}
    seed_results, fatal = [], None
    started, cpu_started = time.perf_counter(), time.process_time()

    def block(episode, reason, result=None):
        episode.update(status="blocked", completed=False, reason=reason)
        if result is not None:
            result["evaluations"][episode["kind"]] = {"status": "blocked", "completed": False, "reason": reason}

    def checkpoint():
        metadata.update({k: sum(e[k] for e in episodes)
            for k in ("control_calls_attempted", "control_steps", "physics_steps")})
        metadata.update(model_updates=sum(c.get("committed_scalar_updates", 0)
                            for s in seed_results for c in s["calibrations"].values()),
            vector_model_updates=sum(c.get("committed_vector_updates", 0)
                            for s in seed_results for c in s["calibrations"].values()),
            update_budget_classification="new independent C physical calibration RLS; no offline A/B replay",
            completed_trials=sum(e["status"] == "completed" for e in episodes),
            terminated_trials=sum(e["status"] == "terminated" for e in episodes),
            exception_trials=sum(e["status"] == "exception" for e in episodes),
            blocked_trials=sum(e["status"] == "blocked" for e in episodes),
            wall_seconds=time.perf_counter()-started, cpu_seconds=time.process_time()-cpu_started)
        errors = []
        for name, data in (("seed_results.json", seed_results), ("episodes.json", episodes), ("metadata.json", metadata)):
            try:
                _write_json(output / name, _archive_record(data) if isinstance(data, dict)
                            else [_archive_record(x) for x in data])
            except BaseException as exc:
                errors.append(exc)
        if errors:
            raise errors[0]

    try:
        checkpoint()
        with gzip.open(output / "trace.jsonl.gz", "wt", encoding="utf-8") as trace:
            for seed in DEVELOPMENT_SEEDS:
                result = {"seed": seed, "reset_seed": RESET_SEEDS[seed], "evaluations": {},
                    "calibrations": {}, "learned_models": {}, "fresh_prefix_bindings": {}}
                seed_results.append(result)
                models = {}
                for kind in KINDS:
                    episode = next(e for e in episodes if e["seed"] == seed and e["kind"] == kind)
                    dependencies = ([f"seed{seed}_calibration_{kind.removeprefix('learned_')}"]
                                    if kind.startswith("learned_") else [])
                    if (kind == "prediction" and not result["learned_models"] or
                            kind.startswith("learned_") and kind not in models):
                        if kind == "prediction":
                            dependencies = [f"seed{seed}_calibration_sparse", f"seed{seed}_calibration_continuation"]
                        block(episode, {"type": "DependencyBlocked", "dependencies": dependencies}, result)
                    else:
                        run_trial(result, models, episode, trace, pd)
                    checkpoint()
        metadata.update(complete=True, archive_status="complete")
    except BaseException as exc:
        fatal = exc
        metadata.update(complete=False, archive_status="interrupted" if isinstance(exc, (KeyboardInterrupt, SystemExit)) else "failed",
                        collector_exception=_error(exc))
        raise
    finally:
        for episode in episodes:
            if episode["status"] == "planned":
                block(episode, {"type": "ArchiveAborted", "message": "fatal before planned fresh trial"})
        metadata["all_trials_successful"] = all(e["status"] == "completed" for e in episodes)
        try:
            checkpoint()
            _write_json(output / "manifest.json", {p.name: _hash(p) for p in sorted(output.iterdir())
                if p.is_file() and p.name != "manifest.json"})
        except BaseException as exc:
            metadata["final_checkpoint_exception"] = _error(exc)
            if fatal is None:
                raise
    return metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, required=True)
    args = parser.parse_args()
    run_guard_exploration_development(args.output, protocol_path=args.protocol)


if __name__ == "__main__":
    main()
