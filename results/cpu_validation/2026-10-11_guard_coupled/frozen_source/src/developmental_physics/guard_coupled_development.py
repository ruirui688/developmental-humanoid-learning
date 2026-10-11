"""Frozen C4 B: replay public-guard calibration, then fresh coupled control.

Formal execution requires clean tracked HEAD. A uses one strict source binding;
its diagonal/nominal/PD/zero controls are reused, never fitted or recollected.
Artificial-fixture execution must replace the environment explicitly. No
scientific gate is implemented here: a separate auditor must derive them.
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
from developmental_physics.guard_pair_development import (
    PredictionMeter, native_pair, native_study_abort, _rmse, _counts, _error,
)
from developmental_physics.guard_coupled_pair_model import GuardCoupledPairBodyModel
from developmental_physics.guard_pair_source_binding import (
    ASourceBinding, SHARED_SOURCE_PATHS, load_a_source_binding,
)
from developmental_physics.local_pair_model import FixedPairMPC
from developmental_physics.probes import direction_record


FORMAL_EXECUTION_FROZEN = True
_REAL_ENV = GroundBodyEnv
DEVELOPMENT_SEEDS = (0, 1, 2)
JOINT_INDICES = (0, 1)
PREFIX_STEPS = 100
CALIBRATION_STEPS = 400
PREDICTION_STEPS = 100
CONTROL_STEPS = 200
SOURCE_PATH = "src/developmental_physics/guard_coupled_development.py"
PROTOCOL_PATH = "docs/GUARD_COUPLED_DEVELOPMENT_PROTOCOL.md"
AUDITOR_PATH = "scripts/audit_guard_coupled_development.py"
AUDITOR_SUPPORT_PATHS = ("scripts/audit_local_frozen.py", "scripts/audit_pair_frozen.py")
MODEL_NAME = "coupled_guard"
PHASES = ("prefix", "control")
EFFORT_KEYS = ("requested_absolute_nm_s", "requested_squared_nm2_s",
               "actual_absolute_nm_s", "actual_squared_nm2_s")
PLANNING_KEYS = ("pair_prediction_attempts", "pair_prediction_successes",
                 "scalar_prediction_attempts", "scalar_prediction_successes",
                 "failed_pair_prediction_attempts", "unknown_scalar_failure_count")


def _runtime():
    return {"environment_config": asdict(ExplorationConfig()),
            "dependencies": dict(sorted((d.metadata["Name"], d.version)
                                         for d in importlib.metadata.distributions())),
            "mujoco_version": mujoco.__version__}


def _formal_provenance(root, protocol_path):
    """Caller verifies clean tracked bytes before reading A or creating physics."""
    if Path(__file__).resolve() != (root / SOURCE_PATH).resolve():
        raise RuntimeError("formal runner must execute from its frozen tracked path")
    if protocol_path != (root / PROTOCOL_PATH).resolve() or not protocol_path.is_file():
        raise ValueError("exact frozen B protocol path required")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    status = subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=all"],
                                     cwd=root, text=True)
    if status:
        raise RuntimeError("formal execution requires clean HEAD before reading A or creating physics")
    tracked = set(subprocess.check_output(["git", "ls-files"], cwd=root, text=True).splitlines())
    paths = [*sorted((root / "src/developmental_physics").glob("*.py")), MODEL_PATH,
             root / "pyproject.toml", protocol_path, root / AUDITOR_PATH,
             *(root / name for name in (*AUDITOR_SUPPORT_PATHS, *sorted(SHARED_SOURCE_PATHS)))]
    sources = {}
    for path in paths:
        name = path.relative_to(root).as_posix()
        if name not in tracked or not path.is_file():
            raise RuntimeError(f"frozen dependency missing or untracked: {name}")
        data = path.read_bytes()
        if data != subprocess.check_output(["git", "show", f"{commit}:{name}"], cwd=root):
            raise RuntimeError(f"source differs from clean HEAD: {name}")
        sources[name] = data
    binding = load_a_source_binding(root, synthetic=False, tracked_paths=tracked,
                                   current_source_bytes=sources, expected_runtime=_runtime())
    return commit, status, sources, binding


def _failure(exc):
    record = {"error": _error(exc)}
    for name in ("pair_update_accounting", "shared_pair_update_accounting",
                 "pair_prediction_accounting", "pair_planning_accounting"):
        if hasattr(exc, name):
            record[name] = getattr(exc, name)
    if hasattr(exc, "to_dict"):
        record["structured_failure"] = exc.to_dict()
    return record


def _emit(writer, row):
    writer.write(json.dumps(_archive_record(row), allow_nan=False) + "\n")


def replay_calibration(seed_data, writer, result):
    """Only new coupled RLS; every source transition is prior paid A data.

    Synchronize committed counts in finally, including an interrupt after the
    single two-head publish. There is no extra reporting predict. Prefix and
    incomplete/blocked A calibration contribute no update and no new physics.
    """
    replay = result["calibration_replay"] = {
        "status": "blocked", "completed": False, "source_trial_id": f"seed{seed_data['seed']}_calibration",
        "source_transition_ids": [], "attempted_vector_updates": 0,
        "committed_vector_updates": 0, "committed_scalar_updates": 0,
        "new_physical_calls": 0, "new_physics_substeps": 0,
        "update_classification": "offline reuse of complete native A calibration transitions",
        "reason": seed_data.get("calibration_block_reason"),
        "model_snapshot": None, "rls_prediction_accounting": PredictionMeter().snapshot(),
    }
    if not seed_data["calibration_ready"]:
        return None
    model = GuardCoupledPairBodyModel(seed_data["reference_q"],
                                     public_joint_ranges=seed_data["public_joint_ranges"])
    replay["initial_model"] = model.snapshot()
    meter = PredictionMeter()
    meter.bind_rls(model)
    replay["status"] = "running"
    rows = seed_data["calibration_transitions"]
    try:
        if len(rows) != CALIBRATION_STEPS:
            raise ValueError("source binding must supply exactly 400 complete calibration transitions")
        for row in rows:
            source_id = row["shared_transition_id"]
            q, v = native_pair(row["observation_before"])
            _, next_v = native_pair(row["observation_after"])
            command = tuple(float(row["requested_torque"][j]) for j in JOINT_INDICES)
            if row["diagnostics"]["executed_substeps"] != 10:
                raise ValueError("offline RLS refuses incomplete source intervals")
            replay["attempted_vector_updates"] += 1
            replay["source_transition_ids"].append(source_id)
            update = None
            try:
                # The core's one internal old-state prediction is returned in
                # update; next_v is a label only, never a model input.
                update = model.update(q, v, command, next_v,
                                      transition_id=source_id, phase="identification")
                _emit(writer, {"seed": seed_data["seed"], "source_shared_transition_id": source_id,
                    "phase": "offline_calibration_replay", "new_physical_calls": 0,
                    "new_physics_substeps": 0, "observation_before": row["observation_before"],
                    "requested_torque": row["requested_torque"],
                    "source_complete_next_velocity_label": next_v,
                    "model_input_diagnostics": model.describe_input(q, command),
                    "model_update": update, "model_snapshot_after": model.snapshot()})
            except BaseException as exc:
                replay["failure_accounting"] = _failure(exc)
                # A successful commit preceding a write failure is retained.
                try:
                    _emit(writer, {"seed": seed_data["seed"], "source_shared_transition_id": source_id,
                        "phase": "offline_calibration_replay", "collector_exception": _error(exc),
                        "model_update": update, "failure_accounting": _failure(exc),
                        "model_snapshot_after": model.snapshot(), "new_physical_calls": 0,
                        "new_physics_substeps": 0, "rls_prediction_accounting": meter.snapshot()})
                except BaseException as write_exc:
                    replay["exception_trace_write_error"] = _error(write_exc)
                    if not isinstance(exc, (KeyboardInterrupt, SystemExit, OSError)):
                        raise write_exc from exc
                raise
            finally:
                replay.update(committed_vector_updates=model.update_count,
                              committed_scalar_updates=model.scalar_update_count,
                              model_snapshot=model.snapshot(), rls_prediction_accounting=meter.snapshot())
        if model.update_count != CALIBRATION_STEPS:
            raise RuntimeError("replay must publish exactly 400 atomic vector updates")
        frozen = model.clone_frozen()
        replay.update(status="completed", completed=True, reason=None,
                      frozen_model=frozen.snapshot())
        result["learned_model"] = frozen.snapshot()
        return frozen
    except BaseException as exc:
        replay.update(status="exception", completed=False, reason=_error(exc))
        if isinstance(exc, (KeyboardInterrupt, SystemExit, OSError)):
            raise
        return None
    finally:
        replay.update(committed_vector_updates=model.update_count,
                      committed_scalar_updates=model.scalar_update_count,
                      model_snapshot=model.snapshot(), rls_prediction_accounting=meter.snapshot())


def replay_prediction(seed_data, model, writer, result):
    """Exactly one causal frozen prediction per returned A active start."""
    before = model.parameter_fingerprint()
    meter = PredictionMeter()
    q_errors, v_errors, partial = [], [], []
    record = result["prediction_replay"] = {
        "status": "running", "completed": False, "source_trial_id": f"seed{seed_data['seed']}_prediction",
        "source_transition_ids": [], "new_physical_calls": 0, "new_physics_substeps": 0,
        "committed_scalar_updates": 0, "committed_vector_updates": 0,
        "source_episode": seed_data["prediction_episode"], "partial_endpoint_scores": partial,
        "model_fingerprint_before": before, "model_fingerprint_after": before,
        "prediction_accounting": meter.snapshot(),
        "boundary": "A development prediction replay; no new holdout, no evaluation fit",
    }
    try:
        for row in seed_data["prediction_transitions"]:
            source_id = row["shared_transition_id"]
            q, v = native_pair(row["observation_before"])
            command = tuple(float(row["requested_torque"][j]) for j in JOINT_INDICES)
            record["source_transition_ids"].append(source_id)
            prediction = meter.call(model.predict, q, v, command)
            # Labels are examined only after the causally restricted call.
            next_q, next_v = native_pair(row["observation_after"])
            dq = [next_q[i] - prediction[0][i] for i in range(2)]
            dv = [next_v[i] - prediction[1][i] for i in range(2)]
            complete = row["diagnostics"]["executed_substeps"] == 10
            if complete:
                q_errors.append(dq)
                v_errors.append(dv)
            else:
                partial.append({"source_shared_transition_id": source_id,
                    "executed_substeps": row["diagnostics"]["executed_substeps"],
                    "position_error_rad": dq, "velocity_error_rad_s": dv})
            _emit(writer, {"seed": seed_data["seed"], "source_shared_transition_id": source_id,
                "phase": "offline_prediction_replay", "new_physical_calls": 0,
                "new_physics_substeps": 0, "model_updates": 0,
                "observation_before": row["observation_before"], "requested_torque": row["requested_torque"],
                "predicted_next_qv": {MODEL_NAME: prediction},
                "model_input_diagnostics": model.describe_input(q, command),
                "source_observation_after_for_score_only": row["observation_after"],
                "source_executed_substeps": row["diagnostics"]["executed_substeps"],
                "complete_endpoint_score": complete, "source_study_abort": row.get("study_abort"),
                "position_error_rad": dq, "velocity_error_rad_s": dv})
        source_episode = seed_data["prediction_episode"]
        record.update(status=source_episode["status"],
            completed=source_episode.get("completed") is True and len(v_errors) == PREDICTION_STEPS,
            reason=source_episode.get("reason"))
    except BaseException as exc:
        record.update(status="exception", completed=False, reason=_error(exc), failure_accounting=_failure(exc))
        try:
            _emit(writer, {"seed": seed_data["seed"], "phase": "offline_prediction_replay",
                "collector_exception": _error(exc), "failure_accounting": _failure(exc),
                "prediction_accounting": meter.snapshot(), "model_fingerprint": model.parameter_fingerprint(),
                "new_physical_calls": 0, "new_physics_substeps": 0, "model_updates": 0})
        except BaseException as write_exc:
            record["exception_trace_write_error"] = _error(write_exc)
            raise write_exc from exc
        if isinstance(exc, (KeyboardInterrupt, SystemExit, OSError)):
            raise
    finally:
        record.update(position_prediction_rmse=_rmse(q_errors), velocity_prediction_rmse=_rmse(v_errors),
            metric_complete_endpoints=len(v_errors), prediction_accounting=meter.snapshot(),
            model_fingerprint_after=model.parameter_fingerprint())
        if before != model.parameter_fingerprint() or model.trainable:
            raise RuntimeError("prediction replay changed or unfroze the coupled model")


def run_fresh_control(seed_data, model, episode, writer, result):
    """The only new physical trial: paid zero prefix plus fixed coupled MPC."""
    env = previous = observation = requested = stepped = None
    phase, index = "prefix", None
    target = decision = study = error = trace_failure = None
    planner = None
    predicted, inputs = {}, {}
    before_model = model.parameter_fingerprint()
    env_before = None
    returned_steps = written_steps = unreturned_physics = 0
    q_errors, partial_errors = [], []
    prediction_errors = {MODEL_NAME: {"q": [], "v": []}, "persistence": {"q": [], "v": []}}
    meter = PredictionMeter()
    effort = {p: {key: np.zeros(2) for key in EFFORT_KEYS} for p in PHASES}
    known_actual = {p: 0 for p in PHASES}
    planning = {key: 0 for key in PLANNING_KEYS}
    unknown_planners = failed_planners = fallbacks = 0
    saturation = np.zeros(2, dtype=int)
    planner_seconds = []
    fatal = None
    try:
        env = GroundBodyEnv(ExplorationConfig())
        observation = env.reset(seed=seed_data["reset_seed"], pose="supine")
        native_pair(observation)
        env_before = env.parameter_fingerprint()
        if env_before != seed_data["environment_fingerprint_before"]:
            raise RuntimeError("fresh B plant differs from A; no repair or recalibration")
        previous_torque = (0., 0.)
        for index in range(PREFIX_STEPS + CONTROL_STEPS):
            previous = observation
            phase = "prefix" if index < PREFIX_STEPS else "control"
            requested = np.zeros(8)
            target = decision = stepped = None
            predicted, inputs = {}, {}
            if index == PREFIX_STEPS:
                q0, v0 = native_pair(observation)
                limits = [env.model.joint(name).range for name in env.joint_names]
                selections = [direction_record(j, observation["joint_position"], limits) for j in JOINT_INDICES]
                directions = tuple(r["direction"] for r in selections)
                ranges = tuple(tuple(float(x) for x in limits[j]) for j in JOINT_INDICES)
                expected_native = native_pair(seed_data["native_prefix_observation"])
                if (q0 != tuple(seed_data["reference_q"]) or directions != tuple(seed_data["direction"])
                        or ranges != tuple(tuple(r) for r in seed_data["public_joint_ranges"])
                        or (q0, v0) != expected_native):
                    raise RuntimeError("fresh native prefix qref/v/s/public ranges differ from A; do not clip or repair")
                if model.qref != q0 or model.trainable:
                    raise RuntimeError("model frozen reference differs from bound A reference")
                planner = FixedPairMPC(model, ranges)
                result["fresh_prefix_binding"] = {"reference_q": q0, "native_velocity": v0,
                    "direction": directions, "selection_records": selections,
                    "public_joint_ranges": ranges, "environment_fingerprint": env_before,
                    "source_native_pair_exact": True}
            q, v = native_pair(observation)
            if phase == "control":
                active = index - PREFIX_STEPS
                target = tuple(seed_data["reference_q"][i] + seed_data["direction"][i]
                               * (.04 if active < 100 else .08) for i in range(2))
                ranges = seed_data["public_joint_ranges"]
                if any(not ranges[i][0] + .03 <= target[i] <= ranges[i][1] - .03 for i in range(2)):
                    raise ValueError("predeclared target infeasible; qref and target cannot be clipped")
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
                    planner_seconds.append(time.perf_counter() - timer)
                for key, value in _counts(decision.to_dict()).items():
                    planning[key] += value
                requested[list(JOINT_INDICES)] = decision.torque
                if not np.isfinite(requested).all() or np.max(np.abs(requested)) > .5:
                    raise ValueError("coupled request violates shared .5 Nm permission")
                fallbacks += int(decision.fallback)
                command = tuple(float(requested[j]) for j in JOINT_INDICES)
                predicted[MODEL_NAME] = meter.call(model.predict, q, v, command)
                predicted["persistence"] = (tuple(q[i] + .02*v[i] for i in range(2)), v)
                inputs[MODEL_NAME] = model.describe_input(q, command)
            old_control, old_physics = env.step_id, env.physics_steps
            budget = episode["phase_budgets"][phase]
            budget["control_calls_attempted"] += 1
            try:
                stepped = env.step(requested)
            except BaseException:
                unreturned_physics += env.physics_steps - old_physics
                raise
            finally:
                paid = env.physics_steps - old_physics
                budget["control_steps"] += env.step_id - old_control
                budget["physics_steps"] += paid
                command = requested[list(JOINT_INDICES)]
                effort[phase]["requested_absolute_nm_s"] += np.abs(command)*paid*env.config.physics_dt
                effort[phase]["requested_squared_nm2_s"] += command**2*paid*env.config.physics_dt
            observation = stepped.observation
            returned_steps += 1
            next_q, next_v = native_pair(observation)
            if phase == "control":
                study = native_study_abort(next_q, next_v, seed_data["reference_q"])
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
                raise RuntimeError("native actual effort history invalid; missing effort remains unknown")
            selected = realized[:, list(JOINT_INDICES)]
            effort[phase]["actual_absolute_nm_s"] += np.sum(np.abs(selected), axis=0)*env.config.physics_dt
            effort[phase]["actual_squared_nm2_s"] += np.sum(selected**2, axis=0)*env.config.physics_dt
            known_actual[phase] += executed
            if phase == "control":
                dq = [next_q[i] - target[i] for i in range(2)]
                if executed == 10:
                    q_errors.append(dq)
                    saturation += np.asarray([abs(requested[j]) == .5 for j in JOINT_INDICES], dtype=int)
                    for name, prediction in predicted.items():
                        prediction_errors[name]["q"].append([next_q[i] - prediction[0][i] for i in range(2)])
                        prediction_errors[name]["v"].append([next_v[i] - prediction[1][i] for i in range(2)])
                else:
                    partial_errors.append({"step_index": index, "target_q": target,
                        "errors_rad": dq, "executed_substeps": executed})
            row = {"trial_id": episode["trial_id"], "seed": seed_data["seed"], "kind": MODEL_NAME,
                "joint_indices": JOINT_INDICES, "shared_transition_id": f"{episode['trial_id']}:{index}",
                "step_index": index, "phase": phase, "study_abort": study,
                "requested_torque": requested, "target_q": target,
                "observation_before": previous, "observation_after": observation,
                "predicted_next_qv": predicted, "model_input_diagnostics": inputs,
                "model_update": None, "diagnostics": stepped.diagnostics,
                "planner_decision": None if decision is None else decision.to_dict(),
                "partial_interval_target_error_rad": None if executed == 10 or target is None
                                                     else [next_q[i]-target[i] for i in range(2)],
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
        if env.parameter_fingerprint() != env_before:
            raise RuntimeError("plant changed during fresh coupled control")
        if model.parameter_fingerprint() != before_model:
            raise RuntimeError("control changed frozen coupled parameters")
    except BaseException as exc:
        error = _error(exc)
        episode["failure_accounting"] = _failure(exc)
        try:
            _emit(writer, {"trial_id": episode["trial_id"], "seed": seed_data["seed"], "kind": MODEL_NAME,
                "phase": phase, "step_index": index, "collector_exception": error,
                "study_abort": study, "requested_torque": requested, "target_q": target,
                "observation_before": previous, "observation_after": observation,
                "predicted_next_qv": predicted, "model_input_diagnostics": inputs,
                "model_update": None, "failure_accounting": _failure(exc),
                "diagnostic_prediction_accounting": meter.snapshot(),
                "returned_step_diagnostics": None if stepped is None else stepped.diagnostics,
                "planner_decision": None if decision is None else decision.to_dict(),
                "frozen_model_snapshot": model.snapshot(), **_exception_snapshot(env)})
        except BaseException as write_exc:
            trace_failure = trace_failure or write_exc
            episode["exception_trace_write_error"] = _error(write_exc)
        if isinstance(exc, (KeyboardInterrupt, SystemExit, OSError)) or trace_failure is not None:
            fatal = exc
    finally:
        full = (env is not None and env.step_id == PREFIX_STEPS+CONTROL_STEPS
                and env.physics_steps == 10*(PREFIX_STEPS+CONTROL_STEPS))
        terminated = env is not None and (env.terminated or study is not None)
        completed = error is None and full and not terminated
        status = "exception" if error is not None else ("terminated" if terminated else
                                                     ("completed" if completed else "incomplete"))
        reason = env.reason if env is not None and env.terminated else (study if study is not None else error)
        known = {p: known_actual[p] == episode["phase_budgets"][p]["physics_steps"] for p in PHASES}
        missing = {p: episode["phase_budgets"][p]["physics_steps"]-known_actual[p] for p in PHASES}
        episode.update(_archive_record({"status": status, "completed": completed, "reason": reason,
            "collector_exception": error, "study_abort": study,
            "environment_terminated": None if env is None else env.terminated,
            "environment_stop_reason": None if env is None else env.reason,
            "control_calls_attempted": sum(b["control_calls_attempted"] for b in episode["phase_budgets"].values()),
            "control_steps": sum(b["control_steps"] for b in episode["phase_budgets"].values()),
            "physics_steps": sum(b["physics_steps"] for b in episode["phase_budgets"].values()),
            "returned_steps": returned_steps, "written_returned_steps": written_steps,
            "returned_unwritten_steps": returned_steps-written_steps,
            "unreturned_physics_steps": unreturned_physics,
            "trace_write_failure": None if trace_failure is None else _error(trace_failure),
            "risk_telemetry_complete": error is None and unreturned_physics == 0 and trace_failure is None,
            "environment_fingerprint_before": env_before,
            "environment_fingerprint_after": None if env is None else env.parameter_fingerprint()}))
        result["evaluations"][MODEL_NAME] = _archive_record({
            "status": status, "completed": completed, "reason": reason, "collector_exception": error,
            "study_abort": study, "environment_terminated": episode["environment_terminated"],
            "environment_stop_reason": episode["environment_stop_reason"],
            "tracking_rmse": _rmse(q_errors), "metric_control_step_count": len(q_errors),
            "position_prediction_rmse": {n: _rmse(e["q"]) for n, e in prediction_errors.items()},
            "velocity_prediction_rmse": {n: _rmse(e["v"]) for n, e in prediction_errors.items()},
            "partial_interval_target_errors_rad": partial_errors, "phase_effort": effort,
            "control_effort": effort["control"],
            "phase_effort_combined": {p: {k: float(v.sum()) for k, v in effort[p].items()} for p in PHASES},
            "phase_actual_effort_substeps": known_actual, "phase_actual_effort_complete": known,
            "phase_missing_actual_effort_substeps": missing,
            "actual_effort_complete": known["control"], "actual_effort_is_lower_bound": not known["control"],
            "missing_control_effort_substeps": missing["control"],
            "actual_control_effort_substeps": known_actual["control"],
            "diagnostic_prediction_accounting": meter.snapshot(),
            "planning_accounting": {**planning,
                "scalar_counts_complete": unknown_planners == 0 and planning["unknown_scalar_failure_count"] == 0,
                "scalar_counts_is_lower_bound": unknown_planners > 0 or planning["unknown_scalar_failure_count"] > 0,
                "unknown_failed_planner_calls": unknown_planners},
            "planner_attempt_count": len(planner_seconds), "failed_planner_attempts": failed_planners,
            "planner_decision_count": len(planner_seconds)-failed_planners,
            "planner_fallbacks": fallbacks, "saturated_control_steps_per_axis": saturation,
            "controller_seconds_total": sum(planner_seconds),
            "planner_spec": None if planner is None else planner.spec(),
            "model_fingerprint_before": before_model, "model_fingerprint_after": model.parameter_fingerprint(),
            "model_updates": 0})
    if fatal is not None:
        raise fatal


def run_guard_coupled_development(output, *, protocol_path, synthetic=False,
                                   synthetic_source_bytes=None, binding=None):
    # The real guard precedes Git, A/source reads, output creation and physics.
    if not synthetic and not FORMAL_EXECUTION_FROZEN:
        raise RuntimeError("draft B real execution disabled until root freezes protocol, source and auditor")
    if synthetic:
        if GroundBodyEnv is _REAL_ENV:
            raise RuntimeError("synthetic execution requires an explicitly replaced environment")
        if not isinstance(binding, ASourceBinding) or binding.record().get("synthetic") is not True:
            raise RuntimeError("synthetic execution requires an explicit strict artificial A binding")
        if not isinstance(synthetic_source_bytes, dict) or not synthetic_source_bytes:
            raise RuntimeError("synthetic sources required; no Git or source-read fallback")
        if any(not isinstance(n, str) or not isinstance(b, bytes) for n, b in synthetic_source_bytes.items()):
            raise ValueError("synthetic source mapping requires string names and original bytes")
        if PROTOCOL_PATH not in synthetic_source_bytes:
            raise ValueError("explicit fixture must include the literal B protocol path")
    elif binding is not None or synthetic_source_bytes is not None:
        raise ValueError("formal A binding must be created internally from verified sources")
    output = Path(output)
    if output.exists():
        raise FileExistsError(output)
    root = next(p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file())
    protocol_path = Path(protocol_path).resolve()
    if synthetic:
        commit, status, sources = "synthetic-fixture-no-git", "", dict(synthetic_source_bytes)
    else:
        commit, status, sources, binding = _formal_provenance(root, protocol_path)
    for name, data in binding.source_bytes().items():
        if name in sources and sources[name] != data:
            raise RuntimeError("bound A provenance would overwrite current source bytes")
        sources[name] = data
    plans = [{"trial_id": f"seed{seed}_{MODEL_NAME}", "seed": seed, "kind": MODEL_NAME,
              "maximum_control_steps": PREFIX_STEPS+CONTROL_STEPS} for seed in DEVELOPMENT_SEEDS]
    episodes = [{**plan, "status": "planned", "completed": False, "reason": None,
                 "control_calls_attempted": 0, "control_steps": 0, "physics_steps": 0,
                 "phase_budgets": {p: {"control_calls_attempted": 0, "control_steps": 0, "physics_steps": 0}
                                   for p in PHASES}} for plan in plans]
    metadata = {"schema_version": 1, "suite": "guard_coupled_development", "synthetic": synthetic,
        "created_at_utc": datetime.now(timezone.utc).isoformat(), "purpose": __doc__,
        "seeds": list(DEVELOPMENT_SEEDS), "split": "development", "pose": "supine",
        "joint_indices": list(JOINT_INDICES), "native_joint_count": 8,
        "source_commit": commit, "source_status": status, "source_dirty": bool(status),
        "source_sha256": {n: hashlib.sha256(b).hexdigest() for n, b in sources.items()},
        "protocol": {"path": PROTOCOL_PATH, "sha256": hashlib.sha256(sources[PROTOCOL_PATH]).hexdigest()},
        "platform": sys.platform if synthetic else platform.platform(),
        "python_executable": sys.executable, "python_version": sys.version, **_runtime(),
        "gpu": None, "backend": "synthetic, no physics" if synthetic else "MuJoCo CPU",
        "a_binding": binding.record(), "a_data_reuse": "previously paid A controls/calibration/prediction; no repeated A physical trial or diagonal fit",
        "structures": ["coupled_hinge9"], "model_input_basis": "known_angle_guard",
        "parameter_count_per_output": 9, "reused_diagonal_parameter_count_per_output": 5,
        "model_input": "current original q/v, known requested command, public ranges; guard recomputed on each own predicted start",
        "label": "next native A velocity on complete calibration intervals; offline reuse, not new interaction",
        "guard_interval_boundary": "start G(q,u), never future actual torque or interval guard average",
        "target_information": "current qref+s*.04 then qref+s*.08 only; no preview/clipping",
        "study_abort_spec": {"active_only": True, "absolute_q_minus_qref_rad": .12,
            "absolute_velocity_rad_s": 1., "comparison": ">=", "any_axis": True,
            "feedback_action": None, "complete_terminal_scored_not_complete": True},
        "prefix_steps": PREFIX_STEPS, "calibration_reuse_steps": CALIBRATION_STEPS,
        "prediction_reuse_steps": PREDICTION_STEPS, "control_steps_per_trial": CONTROL_STEPS,
        "planned_episodes": plans, "maximum_control_steps": len(plans)*(PREFIX_STEPS+CONTROL_STEPS),
        "maximum_physics_steps": len(plans)*10*(PREFIX_STEPS+CONTROL_STEPS),
        "maximum_offline_replay_scalar_updates": len(plans)*CALIBRATION_STEPS*2,
        "maximum_offline_replay_vector_updates": len(plans)*CALIBRATION_STEPS,
        "maximum_independent_prediction_pair_calls": len(plans)*PREDICTION_STEPS,
        "maximum_rls_internal_prediction_pair_calls": len(plans)*CALIBRATION_STEPS,
        "maximum_mpc_prediction_pair_calls": len(plans)*CONTROL_STEPS*81*15,
        "maximum_control_diagnostic_prediction_pair_calls": len(plans)*CONTROL_STEPS,
        "prediction_accounting_scope": "offline RLS internal, offline A prediction replay, new MPC and new control diagnostics separately",
        "policy_parameter_updates": 0, "gain_updates": 0, "gate_updates": 0,
        "teacher_calls": 0, "external_demonstration_samples": 0,
        "scientific_gates": "frozen; separate independent auditor required; A contribution is not a prerequisite",
        "claim_boundary": "development-only pair mechanism test; no new holdout, adaptation, skill, safety or generalization claim",
        "archive_status": "running", "complete": False}
    output.mkdir(parents=True)
    with zipfile.ZipFile(output / "source_snapshot.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in sources.items():
            archive.writestr(name, data)
    metadata["source_snapshot_sha256"] = _hash(output / "source_snapshot.zip")
    metadata["independent_auditor"] = {"path": AUDITOR_PATH,
        "sha256": metadata["source_sha256"].get(AUDITOR_PATH), "pending": synthetic, "required_for_formal": True}
    seed_results = []
    fatal = None
    started, cpu_started = time.perf_counter(), time.process_time()

    def block(episode, reason):
        episode.update(status="blocked", completed=False, reason=reason)

    def checkpoint():
        metadata.update({k: sum(e[k] for e in episodes)
                         for k in ("control_calls_attempted", "control_steps", "physics_steps")})
        metadata.update(model_updates=sum(s.get("calibration_replay", {}).get("committed_scalar_updates", 0) for s in seed_results),
            vector_model_updates=sum(s.get("calibration_replay", {}).get("committed_vector_updates", 0) for s in seed_results),
            update_budget_classification="offline coupled RLS replay of previously paid A calibration",
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
        with gzip.open(output / "calibration_replay.jsonl.gz", "wt", encoding="utf-8") as calibration_trace, \
             gzip.open(output / "prediction_replay.jsonl.gz", "wt", encoding="utf-8") as prediction_trace, \
             gzip.open(output / "trace.jsonl.gz", "wt", encoding="utf-8") as control_trace:
            for seed, episode in zip(DEVELOPMENT_SEEDS, episodes):
                source = binding.seed(seed)
                result = {"seed": seed, "reset_seed": source["reset_seed"],
                    "reference_q": source["reference_q"], "direction": source["direction"],
                    "public_joint_ranges": source["public_joint_ranges"], "evaluations": {},
                    "reused_baselines": source["reused_baselines"],
                    "reused_audit_metrics": source["reused_audit_metrics"],
                    "reuse_cost_classification": "paid in original A ledger; excluded from new B physical budget"}
                seed_results.append(result)
                model = replay_calibration(source, calibration_trace, result)
                checkpoint()
                if model is None:
                    reason = {"type": "DependencyBlocked", "dependencies": [f"seed{seed}_calibration"],
                              "details": result["calibration_replay"]["reason"]}
                    block(episode, reason)
                    result["prediction_replay"] = {"status": "blocked", "completed": False, "reason": reason,
                        "new_physical_calls": 0, "new_physics_substeps": 0, "committed_scalar_updates": 0}
                    result["evaluations"][MODEL_NAME] = {"status": "blocked", "completed": False, "reason": reason}
                    checkpoint()
                    continue
                replay_prediction(source, model, prediction_trace, result)
                checkpoint()
                run_fresh_control(source, model, episode, control_trace, result)
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
                block(episode, {"type": "ArchiveAborted", "message": "fatal before planned fresh control"})
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
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--protocol", required=True, type=Path)
    args = parser.parse_args()
    if not FORMAL_EXECUTION_FROZEN:
        parser.error("real execution disabled: B source, protocol and independent auditor are not frozen")
    print(json.dumps(run_guard_coupled_development(args.output, protocol_path=args.protocol), indent=2))


if __name__ == "__main__":
    main()
