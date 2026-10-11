"""Frozen finite shoulder/elbow damping-grid development.

Real execution requires clean source. Synthetic execution must replace the
environment. No body model, fit, policy or online gain update is performed.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import gzip
import hashlib
import importlib.metadata
from itertools import product
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
from developmental_physics.elbow_feedback_validate import _risk, _risk_add
from developmental_physics.feedback_validate import pd_request
from developmental_physics.probes import direction_record


FORMAL_EXECUTION_FROZEN = True
_REAL_ENV = GroundBodyEnv
DEVELOPMENT_SEEDS = (0, 1, 2)
JOINT_INDICES = (0, 1)
KP = (64., 64.)
FIXED_KD = tuple(product((0., 1., 2.), (1., 2., 4.)))
PREFIX_STEPS, CONTROL_STEPS = 100, 200
PHASES = ("prefix", "control")
EFFORT_KEYS = ("requested_absolute_nm_s", "requested_squared_nm2_s",
               "actual_absolute_nm_s", "actual_squared_nm2_s")
PROTOCOL_PATH = "docs/PAIR_PD_DEVELOPMENT_PROTOCOL.md"
AUDITOR_PATH = "scripts/audit_pair_pd.py"
AUDITOR_SUPPORT_PATHS = ("scripts/audit_local_frozen.py",)
SYNTHETIC_FIXTURE_PATH = "tests/test_pair_pd_development.py"
SYNTHETIC_SUPPORT_PATHS = ()


def _error(exc):
    return {"type": type(exc).__name__, "message": str(exc)}


def _native_pair(observation):
    result = []
    for key in ("joint_position", "joint_velocity"):
        full = np.asarray(observation[key], dtype=float)
        if full.shape != (8,) or not np.isfinite(full).all():
            raise ValueError("finite original eight-axis encoders required")
        result.append(tuple(float(full[j]) for j in JOINT_INDICES))
    return tuple(result)


def _study_abort(q, v, qref):
    triggers = []
    for axis, joint in enumerate(JOINT_INDICES):
        if abs(q[axis]-qref[axis]) >= .12:
            triggers.append({"joint_index": joint, "signal": "absolute_q_minus_qref_rad"})
        if abs(v[axis]) >= 1.:
            triggers.append({"joint_index": joint, "signal": "absolute_velocity_rad_s"})
    return None if not triggers else {
        "type": "StudyAbort", "triggers": triggers, "q_rad": list(q),
        "qref_rad": list(qref), "velocity_rad_s": list(v),
        "thresholds": {"absolute_q_minus_qref_rad": .12, "absolute_velocity_rad_s": 1.},
        "feedback_action": None,
    }


def pd_pair_request(q, v, current_target, kd):
    """Same scalar PD math on each current encoder; no target preview."""
    for name, value in (("q", q), ("v", v), ("current_target", current_target), ("kd", kd)):
        if len(value) != 2:
            raise ValueError(f"{name} must contain exactly two scalars")
    outputs = [pd_request(q[i], v[i], current_target[i], KP[i], kd[i]) for i in range(2)]
    return tuple(item[0] for item in outputs), tuple(item[1] for item in outputs)


def _rmse(errors):
    if not errors:
        return None
    values = np.asarray(errors, dtype=float)
    if values.ndim != 2 or values.shape[1] != 2 or not np.isfinite(values).all():
        raise ValueError("finite paired tracking errors required")
    return {"joint": float(np.sqrt(np.mean(values**2))),
            "per_axis": np.sqrt(np.mean(values**2, axis=0)).tolist(),
            "complete_endpoints": len(errors)}


def tracking_windows(endpoints):
    """Keep original planned indices when early stops leave missing windows."""
    windows = {}
    for name, lower, upper in (("segment0", 0, 100), ("segment1", 100, 200),
                               ("segment0_last20", 80, 100), ("segment1_last20", 180, 200)):
        returned = [row for row in endpoints if lower <= row["active_index"] < upper]
        complete = [row for row in returned if row["complete_transition"]]
        errors = [row["error_rad"] for row in complete]
        windows[name] = {
            "planned_active_index_start": lower, "planned_active_index_end_exclusive": upper,
            "planned_count": upper-lower, "returned_count": len(returned),
            "complete_count": len(complete), "partial_count": len(returned)-len(complete),
            "missing_returned_count": upper-lower-len(returned),
            "missing_complete_count": upper-lower-len(complete),
            "tracking": _rmse(errors),
            "signed_mean_error_rad": None if not errors else np.mean(errors, axis=0).tolist(),
            "returned_endpoints": returned,
        }
    return windows


def _selection(episodes):
    """Development selection only; all candidates and failures remain visible."""
    records = []
    for candidate, kd in enumerate(FIXED_KD):
        trials, failures = [], []
        for seed in DEVELOPMENT_SEEDS:
            matches = [e for e in episodes if e["candidate"] == candidate and e["seed"] == seed]
            if len(matches) != 1:
                failures.append({"seed": seed, "reason": "missing or duplicate trial"})
                continue
            trial = matches[0]
            reasons = []
            if not trial.get("complete", False) or trial["status"] != "completed":
                reasons.append("trial is not complete without stop/error")
            if not trial.get("actual_effort_complete", False):
                reasons.append("actual history does not cover all paid substeps")
            if trial.get("metric_control_step_count") != CONTROL_STEPS:
                reasons.append("full planned tracking endpoints missing")
            if trial.get("phase_complete_transition_counts") != {"prefix": PREFIX_STEPS, "control": CONTROL_STEPS}:
                reasons.append("full paid prefix/control transitions missing")
            tracking = trial.get("tracking")
            if tracking is None:
                reasons.append("tracking unavailable")
            else:
                values = np.asarray([tracking["joint"], *tracking["per_axis"]], dtype=float)
                if values.shape != (3,) or not np.isfinite(values).all() or np.any(values < 0.):
                    reasons.append("tracking is not finite nonnegative")
            if trial.get("collector_exception") is not None or trial.get("study_abort") is not None or trial.get("environment_terminated"):
                reasons.append("stop or exception recorded")
            if trial.get("invalid_numeric_fields"):
                reasons.append("invalid numeric fields recorded")
            if reasons:
                failures.append({"seed": seed, "trial_id": trial["trial_id"], "reasons": reasons})
            trials.append(trial)
        eligible = not failures and len(trials) == len(DEVELOPMENT_SEEDS)
        sort_key = None
        if eligible:
            joint_mean = float(np.mean([e["tracking"]["joint"] for e in trials]))
            worst_seed_joint = max(e["tracking"]["joint"] for e in trials)
            squared_mean = float(np.mean([e["phase_effort_combined"]["control"]["actual_squared_nm2_s"] for e in trials]))
            if not np.isfinite(squared_mean) or squared_mean < 0.:
                eligible = False
                failures.append({"reason": "actual squared effort not finite nonnegative"})
            else:
                sort_key = [joint_mean, float(worst_seed_joint), squared_mean, candidate]
        records.append({"candidate": candidate, "kp": list(KP), "kd": list(kd),
                        "eligible": eligible, "qualification_failures": failures,
                        "sort_key": sort_key,
                        "paid_control_steps": sum(e["control_steps"] for e in trials),
                        "paid_physics_steps": sum(e["physics_steps"] for e in trials)})
    eligible = [r for r in records if r["eligible"]]
    picked = min(eligible, key=lambda r: r["sort_key"]) if eligible else None
    return {"status": "selected" if picked else "blocked", "picked": picked,
            "candidates": records, "selection_kind": "finite fixed-Kp damping-grid development",
            "sort_order": ["mean_seed_joint_rmse", "max_seed_joint_rmse",
                           "mean_seed_control_actual_squared_effort", "candidate_index"],
            "claim_boundary": "not global gain optimality or body-method advantage"}


def _source_git_record(root, source_bytes, *, synthetic):
    if synthetic:
        return {"source_commit": None, "source_status": None, "source_dirty": None,
                "source_git_blobs": {}, "source_git_binding": "not resolved; synthetic draft made no Git calls"}
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    status = subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=all"], cwd=root, text=True)
    if status:
        raise RuntimeError("formal collection requires clean tracked source")
    blobs = {}
    for name, data in source_bytes.items():
        committed = subprocess.check_output(["git", "rev-parse", f"{commit}:{name}"], cwd=root, text=True).strip()
        archived = hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()
        if committed != archived:
            raise RuntimeError(f"source snapshot differs from committed Git blob: {name}")
        blobs[name] = committed
    return {"source_commit": commit, "source_status": status, "source_dirty": False,
            "source_git_blobs": blobs, "source_git_binding": "every ZIP source matches exact committed blob"}


def run_pair_pd(output, *, protocol_path, synthetic=False):
    if type(synthetic) is not bool:
        raise ValueError("synthetic must be boolean")
    if synthetic:
        if GroundBodyEnv is _REAL_ENV:
            raise RuntimeError("synthetic execution requires an explicitly replaced environment")
    elif not FORMAL_EXECUTION_FROZEN:
        raise RuntimeError("draft real physics is disabled until root freezes and accepts it")
    root = next(p for p in Path(__file__).resolve().parents if (p/"pyproject.toml").is_file())
    output, protocol_path = Path(output), Path(protocol_path).resolve()
    if output.exists():
        raise FileExistsError(output)
    if protocol_path != (root/PROTOCOL_PATH).resolve() or not protocol_path.is_file():
        raise ValueError("exact declared pair-PD protocol required")
    auditor = root/AUDITOR_PATH
    if not synthetic and not auditor.is_file():
        raise RuntimeError("formal collection requires the independent pair-PD auditor in source ZIP")
    sources = [*sorted((root/"src/developmental_physics").glob("*.py")), MODEL_PATH,
               root/"pyproject.toml", Path(__file__), protocol_path,
               *(root/name for name in AUDITOR_SUPPORT_PATHS)]
    if auditor.is_file():
        sources.append(auditor)
    if synthetic:
        sources.append(root/SYNTHETIC_FIXTURE_PATH)
        sources.extend(root/name for name in SYNTHETIC_SUPPORT_PATHS if (root/name).is_file())
    source_bytes = {p.relative_to(root).as_posix(): p.read_bytes() for p in sources}
    git_record = _source_git_record(root, source_bytes, synthetic=synthetic)
    plans = [{"trial_id": f"seed{seed}_candidate{i}", "seed": seed, "candidate": i,
              "kp": list(KP), "kd": list(kd), "maximum_control_steps": PREFIX_STEPS+CONTROL_STEPS}
             for seed in DEVELOPMENT_SEEDS for i, kd in enumerate(FIXED_KD)]
    episodes = [{**p, "status": "planned", "reason": None, "collector_exception": None,
                 "complete": False, "control_calls_attempted": 0, "control_steps": 0, "physics_steps": 0,
                 "phase_budgets": {phase: dict(control_calls_attempted=0, control_steps=0, physics_steps=0)
                                   for phase in PHASES}} for p in plans]
    config = ExplorationConfig()
    metadata = {
        "schema_version": 1, "suite": "pair_pd_development", "synthetic": synthetic,
        "created_at_utc": datetime.now(timezone.utc).isoformat(), **git_record,
        "source_sha256": {name: hashlib.sha256(data).hexdigest() for name, data in source_bytes.items()},
        "protocol": {"path": PROTOCOL_PATH, "sha256": _hash(protocol_path)},
        "auditor": {"path": AUDITOR_PATH, "sha256": _hash(auditor) if auditor.is_file() else None,
                    "pending": not auditor.is_file(), "required_for_formal": True},
        "platform": platform.platform(), "python_version": sys.version, "python_executable": sys.executable,
        "dependencies": dict(sorted((d.metadata["Name"], d.version) for d in importlib.metadata.distributions())),
        "backend": "synthetic, no physics" if synthetic else "MuJoCo CPU", "gpu": None,
        "mujoco_version": mujoco.__version__, "environment_config": asdict(config),
        "pose": "supine", "joint_indices": list(JOINT_INDICES), "native_joint_count": 8,
        "seeds": list(DEVELOPMENT_SEEDS), "split": "development", "kp": list(KP),
        "kd_candidates": [list(kd) for kd in FIXED_KD], "prefix_steps": PREFIX_STEPS,
        "control_steps_per_trial": CONTROL_STEPS, "target_offsets_rad": [.04, .08],
        "target_information": "own paid native qref plus direction; current target only; no preview or clipping",
        "study_abort_spec": {"active_only": True, "absolute_q_minus_qref_rad": .12,
                             "absolute_velocity_rad_s": 1., "comparison": ">=", "any_axis": True,
                             "feedback_action": None, "complete_terminal_scored_not_complete": True},
        "parameter_updates": {"body_model": 0, "policy": 0, "gains": 0}, "model_updates": 0,
        "teacher_calls": 0, "external_demonstration_samples": 0,
        "pd_controller_spec": {"implementation": "feedback_validate.pd_request per original j0/j1",
                               "permission_nm": .5, "body_model_input": False, "gain_updates": 0},
        "grid_reason": "root-supplied first combined64/(0,1) three-seed active1 velocity stops; no raw reread here",
        "initial_controller_capability": "classical position-target PD using current original encoders",
        "planned_episodes": plans, "planned_episode_count": len(plans),
        "maximum_control_steps": len(plans)*(PREFIX_STEPS+CONTROL_STEPS),
        "maximum_physics_steps": len(plans)*(PREFIX_STEPS+CONTROL_STEPS)*10,
        "cpu_seconds_scope": "current process, timed after source snapshot/setup; physical and audit costs separate",
        "claim_boundary": "fixed-Kp damping development only; no global optimum/method advantage/skill/safety claim",
        "complete": False, "archive_status": "running",
    }
    output.mkdir(parents=True)
    with zipfile.ZipFile(output/"source_snapshot.zip", "w", zipfile.ZIP_DEFLATED) as snapshot:
        for name, data in source_bytes.items():
            snapshot.writestr(name, data)
    metadata["source_snapshot_sha256"] = _hash(output/"source_snapshot.zip")
    started, cpu_started, fatal = time.perf_counter(), time.process_time(), None

    def checkpoint():
        for key in ("control_calls_attempted", "control_steps", "physics_steps"):
            metadata[key] = sum(e[key] for e in episodes)
        metadata.update(wall_seconds=time.perf_counter()-started, cpu_seconds=time.process_time()-cpu_started)
        for status in ("completed", "terminated", "exception", "blocked"):
            metadata[status+"_trials"] = sum(e["status"] == status for e in episodes)
        errors = []
        for name, data in (("episodes.json", episodes), ("metadata.json", metadata), ("selection.json", _selection(episodes))):
            try:
                _write_json(output/name, [_archive_record(e) for e in data]
                            if isinstance(data, list) else _archive_record(data))
            except BaseException as exc:
                errors.append(exc)
        if errors:
            raise errors[0]

    try:
        checkpoint()
        with gzip.open(output/"trace.jsonl.gz", "wt", encoding="utf-8") as trace:
            for episode in episodes:
                env = observation = previous = requested = stepped = None
                index = raw = target = qref = selections = study = env_before = None
                old_control = old_physics = partial_error = None
                error = trace_failure = None
                phase = "prefix"
                endpoints, tracking, partial, history_issues = [], [], [], []
                effort = {p: {key: np.zeros(2) for key in EFFORT_KEYS} for p in PHASES}
                actual_substeps, complete_transitions = ({p: 0 for p in PHASES} for _ in range(2))
                phase_risk = {p: _risk() for p in ("full", *PHASES)}
                returned = written = unreturned = telemetry = pd_calls = pd_failed = 0
                saturation = np.zeros(2, dtype=int)
                pd_seconds = 0.
                try:
                    env = GroundBodyEnv(config)
                    reset_seed = int(np.random.SeedSequence(episode["seed"]).spawn(2)[0].generate_state(1)[0])
                    episode["reset_seed"] = reset_seed
                    observation = env.reset(seed=reset_seed, pose="supine")
                    _native_pair(observation)
                    env_before = env.parameter_fingerprint()
                    ranges = np.asarray([env.model.joint(name).range for name in env.joint_names], dtype=float)
                    if ranges.shape != (8, 2) or not np.isfinite(ranges).all() or np.any(ranges[:, 0] >= ranges[:, 1]):
                        raise ValueError("original eight ordered public joint ranges required")
                    episode["public_joint_ranges_rad"] = ranges.tolist()
                    for index in range(PREFIX_STEPS+CONTROL_STEPS):
                        phase = "prefix" if index < PREFIX_STEPS else "control"
                        requested, raw, target = np.zeros(8), None, None
                        stepped = partial_error = old_control = old_physics = None
                        previous = observation
                        q, v = _native_pair(observation)
                        if index == PREFIX_STEPS:
                            qref = q
                            selections = [direction_record(j, observation["joint_position"], ranges) for j in JOINT_INDICES]
                            directions = tuple(s["direction"] for s in selections)
                            targets = [tuple(qref[i]+directions[i]*offset for i in range(2)) for offset in (.04, .08)]
                            if not all(ranges[j, 0]+.03 <= t[i] <= ranges[j, 1]-.03
                                       for t in targets for i, j in enumerate(JOINT_INDICES)):
                                raise ValueError("declared target is infeasible; do not clip it")
                        if phase == "control":
                            target = targets[0 if index-PREFIX_STEPS < 100 else 1]
                            pd_calls += 1
                            action_started = time.perf_counter()
                            try:
                                command, raw = pd_pair_request(q, v, target, episode["kd"])
                                requested[list(JOINT_INDICES)] = command
                            except BaseException:
                                pd_failed += 1
                                raise
                            finally:
                                pd_seconds += time.perf_counter()-action_started
                        old_control, old_physics = env.step_id, env.physics_steps
                        budget = episode["phase_budgets"][phase]
                        budget["control_calls_attempted"] += 1
                        try:
                            stepped = env.step(requested)
                        except BaseException:
                            unreturned += env.physics_steps-old_physics
                            raise
                        finally:
                            budget["control_steps"] += env.step_id-old_control
                            budget["physics_steps"] += env.physics_steps-old_physics
                            paid_dt = (env.physics_steps-old_physics)*env.config.physics_dt
                            effort[phase]["requested_absolute_nm_s"] += np.abs(requested[:2])*paid_dt
                            effort[phase]["requested_squared_nm2_s"] += requested[:2]**2*paid_dt
                            for key in ("control_calls_attempted", "control_steps", "physics_steps"):
                                episode[key] = sum(b[key] for b in episode["phase_budgets"].values())
                        returned += 1
                        observation = stepped.observation
                        after_q, after_v = _native_pair(observation)
                        if phase == "control":
                            study = _study_abort(after_q, after_v, qref)
                            if study is not None:
                                study.update(phase=phase, step_index=index, active_index=index-PREFIX_STEPS)
                        n = stepped.diagnostics["executed_substeps"]
                        if type(n) is not int or not 0 <= n <= 10 or n != env.physics_steps-old_physics:
                            raise RuntimeError("returned substep count differs from paid physics cost")
                        if env.step_id-old_control != 1:
                            raise RuntimeError("returned control count differs from one attempted call")
                        if n == 10:
                            complete_transitions[phase] += 1
                        if phase == "control":
                            endpoint_error = [after_q[i]-target[i] for i in range(2)]
                            endpoints.append({"active_index": index-PREFIX_STEPS, "error_rad": endpoint_error,
                                              "complete_transition": n == 10})
                            if n == 10:
                                tracking.append(endpoint_error)
                                saturation += np.abs(requested[:2]) == .5
                            else:
                                partial_error = endpoint_error
                                partial.append({"active_index": index-PREFIX_STEPS, "error_rad": endpoint_error})
                        history = stepped.diagnostics.get("applied_torque_history")
                        actual_issue = None
                        if history is None:
                            actual_issue = {"type": "ActualHistoryMissing", "phase": phase,
                                            "control_index": index, "missing_substeps": n}
                            history_issues.append(actual_issue)
                        else:
                            realized = np.asarray(history, dtype=float)
                            if n == 0 and realized.size == 0:
                                realized = realized.reshape(0, 8)
                            if realized.shape != (n, 8) or not np.isfinite(realized).all() or np.max(np.abs(realized), initial=0.) > .5:
                                raise RuntimeError("applied torque history differs from paid substeps or permission")
                            effort[phase]["actual_absolute_nm_s"] += np.sum(np.abs(realized[:, :2]), axis=0)*env.config.physics_dt
                            effort[phase]["actual_squared_nm2_s"] += np.sum(realized[:, :2]**2, axis=0)*env.config.physics_dt
                            actual_substeps[phase] += n
                        for p in ("full", phase):
                            _risk_add(phase_risk[p], stepped.diagnostics, observation, ranges, env.config.physics_dt)
                        telemetry += n
                        try:
                            trace.write(json.dumps(_archive_record({
                                "trial_id": episode["trial_id"], "seed": episode["seed"], "candidate": episode["candidate"],
                                "control_index": index, "phase": phase, "kp": episode["kp"], "kd": episode["kd"],
                                "control_steps_before": old_control, "physics_steps_before": old_physics,
                                "control_steps_after": env.step_id, "physics_steps_after": env.physics_steps,
                                "requested_torque": requested, "raw_pd_torque_nm": raw, "target_q_rad": target,
                                "study_abort": study, "environment_terminated": bool(env.terminated),
                                "environment_stop_reason": env.reason, "complete_transition": n == 10,
                                "actual_history_issue": actual_issue, "partial_interval_target_error_rad": partial_error,
                                "observation_before": previous, "observation_after": observation,
                                "diagnostics": stepped.diagnostics, "qpos": env.data.qpos, "qvel": env.data.qvel,
                            }), allow_nan=False)+"\n")
                            written += 1
                        except BaseException as exc:
                            trace_failure = exc
                            raise
                        if stepped.terminated or study is not None:
                            break
                        if n != 10:
                            raise RuntimeError("partial return without an environment stop")
                    if env_before != env.parameter_fingerprint():
                        raise RuntimeError("environment parameters changed")
                except BaseException as exc:
                    error = _error(exc)
                    if isinstance(exc, (KeyboardInterrupt, SystemExit, OSError)) or trace_failure is not None:
                        fatal = exc
                    try:
                        trace.write(json.dumps(_archive_record({
                            "trial_id": episode["trial_id"], "seed": episode["seed"], "candidate": episode["candidate"],
                            "control_index": index, "phase": phase, "kp": episode["kp"], "kd": episode["kd"],
                            "collector_exception": error, "study_abort": study, "requested_torque": requested,
                            "raw_pd_torque_nm": raw, "target_q_rad": target, "observation_before": previous,
                            "control_steps_before": old_control, "physics_steps_before": old_physics,
                            "control_steps_after": None if env is None else env.step_id,
                            "physics_steps_after": None if env is None else env.physics_steps,
                            "returned_step_diagnostics": None if stepped is None else stepped.diagnostics,
                            "returned_observation_after": None if stepped is None else stepped.observation,
                            "partial_interval_target_error_rad": partial_error,
                            "unreturned_physics_steps": unreturned, "returned_control_steps": returned,
                            "trace_rows_written": written, **_exception_snapshot(env),
                        }), allow_nan=False)+"\n")
                    except BaseException as write_exc:
                        trace_failure = trace_failure or write_exc
                        episode["exception_trace_write_error"] = _error(write_exc)
                        fatal = fatal or write_exc
                finally:
                    terminated = env is not None and (env.terminated or study is not None)
                    expected_calls = PREFIX_STEPS+CONTROL_STEPS
                    complete = (error is None and env is not None and not terminated
                                and env.step_id == expected_calls and env.physics_steps == expected_calls*10
                                and complete_transitions == {"prefix": PREFIX_STEPS, "control": CONTROL_STEPS}
                                and returned == written == expected_calls and telemetry == expected_calls*10)
                    reason = env.reason if env is not None and env.terminated else (study if study is not None else error)
                    observed = sum(actual_substeps.values())
                    episode.update(_archive_record({
                        "status": "exception" if error else ("terminated" if terminated else "completed"),
                        "reason": reason, "collector_exception": error, "complete": complete,
                        "trace_write_failure": None if trace_failure is None else _error(trace_failure),
                        "study_abort": study, "environment_terminated": None if env is None else bool(env.terminated),
                        "environment_stop_reason": None if env is None else env.reason,
                        "environment_fingerprint_before": env_before,
                        "environment_fingerprint_after": None if env is None else env.parameter_fingerprint(),
                        "prefix_end_q_rad": qref, "selection_records": selections,
                        "metric_control_step_count": len(tracking), "tracking": _rmse(tracking),
                        "complete_tracking_errors_rad": tracking, "tracking_windows": tracking_windows(endpoints),
                        "partial_interval_target_errors_rad": partial, "partial_interval_target_error_count": len(partial),
                        "phase_complete_transition_counts": complete_transitions,
                        "phase_effort": effort,
                        "phase_effort_combined": {p: {key: float(value.sum()) for key, value in effort[p].items()} for p in PHASES},
                        "phase_actual_effort_substeps": actual_substeps,
                        "phase_actual_effort_complete": {p: actual_substeps[p] == episode["phase_budgets"][p]["physics_steps"] for p in PHASES},
                        "phase_actual_effort_missing_substeps": {p: episode["phase_budgets"][p]["physics_steps"]-actual_substeps[p] for p in PHASES},
                        "actual_effort_complete": observed == episode["physics_steps"],
                        "actual_effort_is_lower_bound": observed < episode["physics_steps"], "actual_history_issues": history_issues,
                        "returned_control_steps": returned, "trace_rows_written": written,
                        "returned_unstored_control_steps": returned-written, "unreturned_physics_steps": unreturned,
                        "saturated_control_steps_per_axis": saturation, "phase_risk": phase_risk,
                        "observed_diagnostic_substeps": telemetry,
                        "telemetry_complete_for_paid_substeps": telemetry == episode["physics_steps"],
                        "risk_telemetry_complete": error is None and trace_failure is None and unreturned == 0 and telemetry == episode["physics_steps"],
                        "pd_action_calls": pd_calls, "failed_pd_attempts": pd_failed, "pd_action_seconds": pd_seconds,
                    }))
                    try:
                        checkpoint()
                    except BaseException as save_exc:
                        fatal = fatal or save_exc
                        metadata["checkpoint_exception"] = _error(save_exc)
                    if fatal is not None:
                        raise fatal
        metadata.update(complete=True, archive_status="complete")
    except BaseException as exc:
        fatal = fatal or exc
        metadata.update(complete=False, archive_status="interrupted" if isinstance(exc, (KeyboardInterrupt, SystemExit)) else "failed",
                        collector_exception=_error(exc))
        raise
    finally:
        for episode in episodes:
            if episode["status"] == "planned":
                episode.update(status="blocked", reason={"type": "ArchiveAborted", "message": "not attempted after fatal archive failure"})
        metadata["all_trials_successful"] = all(e["complete"] for e in episodes)
        try:
            checkpoint()
            _write_json(output/"manifest.json", {p.name: _hash(p) for p in sorted(output.iterdir())
                                                if p.is_file() and p.name != "manifest.json"})
        except BaseException:
            if fatal is None:
                raise
    return metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run_pair_pd(args.output, protocol_path=args.protocol), indent=2))


if __name__ == "__main__":
    main()
