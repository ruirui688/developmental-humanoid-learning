"""DRAFT C4 A raw/guard paired-body development collector.

Real execution is disabled. Synthetic execution replaces the environment and
uses an explicit fixture provenance; it never queries Git or a simulator.
Public guard information is matched within each nominal/learned comparison.
No scientific gate or physical conclusion is implemented by this collector.
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
from developmental_physics.local_pair_model import (
    FixedPairMPC, PairPredictionError, update_shared_models,
)
from developmental_physics.probes import direction_record
from developmental_physics.guard_pair_model import InputMappedDiagonalPairBodyModel
from developmental_physics.pd_selection_binding import load_pd_binding


FORMAL_EXECUTION_FROZEN = False
_REAL_ENV = GroundBodyEnv
DEVELOPMENT_SEEDS = (0, 1, 2)
JOINT_INDICES = (0, 1)
KINDS = ("calibration", "prediction", "nominal_raw", "learned_raw",
         "nominal_guard", "learned_guard", "PDselected", "zero")
MPC_KINDS = ("nominal_raw", "learned_raw", "nominal_guard", "learned_guard")
MODEL_BASES = {"nominal_raw": "raw_request", "learned_raw": "raw_request",
               "nominal_guard": "known_angle_guard", "learned_guard": "known_angle_guard"}
PREFIX_STEPS = 100
CALIBRATION_STEPS = 400
PREDICTION_STEPS = 100
CONTROL_STEPS = 200
PD_SELECTION_PATH = "results/cpu_validation/2026-10-11_pair_pd/selection.json"
PD_MANIFEST_PATH = "results/cpu_validation/2026-10-11_pair_pd/manifest.json"
PD_AUDIT_PATH = "results/cpu_validation/2026-10-11_pair_pd/first_audit.json"
PD_PROTOCOL_PATH = "docs/PAIR_PD_DEVELOPMENT_PROTOCOL.md"
SOURCE_PATH = "src/developmental_physics/guard_pair_development.py"
AUDITOR_PATH = "scripts/audit_guard_pair_development.py"
AUDITOR_SUPPORT_PATHS = ("scripts/audit_local_frozen.py", "scripts/audit_pair_frozen.py")
CALIBRATION_AMPLITUDES = (.125, .25, .375, .5, .25)
PREDICTION_SHAPES = ((1., 0.), (0., 1.), (1., 1.), (1., -1.), (1., 1.))
PROTOCOL_PATH = "docs/GUARD_PAIR_DEVELOPMENT_PROTOCOL.md"
PHASES = ("prefix", "calibration", "prediction", "control")
EFFORT_KEYS = ("requested_absolute_nm_s", "requested_squared_nm2_s",
               "actual_absolute_nm_s", "actual_squared_nm2_s")
PLANNING_KEYS = ("pair_prediction_attempts", "pair_prediction_successes",
                 "scalar_prediction_attempts", "scalar_prediction_successes",
                 "failed_pair_prediction_attempts", "unknown_scalar_failure_count")


def _directions(value):
    a = np.asarray(value, dtype=float)
    if a.shape != (2,) or not np.isfinite(a).all() or any(x not in (-1., 1.) for x in a):
        raise ValueError("two fixed directions in {-1,+1} required")
    return a


def _pulse(active):
    slot = active % 20
    return 1. if slot == 0 else (-1. if slot == 10 else 0.)


def calibration_request(active, directions):
    if type(active) is not int or not 0 <= active < 400:
        raise ValueError("fixed calibration active index [0,400) required")
    s = _directions(directions)
    block = active // 20
    amplitude = CALIBRATION_AMPLITUDES[block % 5]
    shape = ((1., 0.) if block < 5 else ((0., 1.) if block < 10 else
             ((1., 1.) if block < 15 else (1., -1.))))
    return tuple(s * amplitude * np.asarray(shape) * _pulse(active))


def prediction_request(active, directions):
    if type(active) is not int or not 0 <= active < 100:
        raise ValueError("fixed full-shape active index [0,100) required")
    amplitude = (.125, .25, .375, .5, .375)[active // 20]
    return tuple(_directions(directions) * amplitude * np.asarray(PREDICTION_SHAPES[active // 20]) * _pulse(active))


def native_pair(observation):
    result = []
    for key in ("joint_position", "joint_velocity"):
        full = np.asarray(observation[key], dtype=float)
        if full.shape != (8,) or not np.isfinite(full).all():
            raise ValueError("finite original eight-axis encoders required")
        result.append(tuple(float(full[i]) for i in JOINT_INDICES))
    return tuple(result)


def native_study_abort(q, v, qref):
    triggers = []
    for axis, joint in enumerate(JOINT_INDICES):
        if abs(q[axis] - qref[axis]) >= .12:
            triggers.append({"joint_index": joint, "signal": "absolute_q_minus_qref_rad"})
        if abs(v[axis]) >= 1.:
            triggers.append({"joint_index": joint, "signal": "absolute_velocity_rad_s"})
    return None if not triggers else {"type": "StudyAbort", "triggers": triggers,
        "q_rad": list(q), "qref_rad": list(qref), "velocity_rad_s": list(v),
        "thresholds": {"absolute_q_minus_qref_rad": .12, "absolute_velocity_rad_s": 1.},
        "feedback_action": None}


def _error(exc):
    return {"type": type(exc).__name__, "message": str(exc)}


def _rmse(errors):
    if not errors:
        return None
    values = np.asarray(errors, dtype=float)
    return {"joint": float(np.sqrt(np.mean(values ** 2))),
            "per_axis": np.sqrt(np.mean(values ** 2, axis=0)).tolist(), "complete_endpoints": len(errors)}


def _fingerprints(models):
    return {name: model.parameter_fingerprint() for name, model in models.items()}


def _counts(record):
    return {key: int(record.get(key, 0)) for key in PLANNING_KEYS}


def _formal_provenance(root, protocol_path):
    """Read each source once after clean HEAD and tracked byte verification."""
    if Path(__file__).resolve() != (root / SOURCE_PATH).resolve():
        raise RuntimeError("formal collector must run from its frozen tracked path")
    if protocol_path != (root / PROTOCOL_PATH).resolve() or not protocol_path.is_file():
        raise ValueError("exact declared protocol required")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    status = subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=all"], cwd=root, text=True)
    if status:
        raise RuntimeError("formal execution requires clean Git before constructing an environment")
    tracked = set(subprocess.check_output(["git", "ls-files"], cwd=root, text=True).splitlines())
    pd_protocol_bytes = (root / PD_PROTOCOL_PATH).read_bytes()
    pd = load_pd_binding(root, expected_selection_path=PD_SELECTION_PATH,
        expected_manifest_path=PD_MANIFEST_PATH, expected_audit_path=PD_AUDIT_PATH,
        expected_protocol={"path": PD_PROTOCOL_PATH,
                           "sha256": hashlib.sha256(pd_protocol_bytes).hexdigest()},
        tracked_paths=tracked)
    paths = [*sorted((root / "src/developmental_physics").glob("*.py")),
        MODEL_PATH, root / "pyproject.toml", root / SOURCE_PATH, protocol_path,
        root / AUDITOR_PATH, *(root / name for name in AUDITOR_SUPPORT_PATHS)]
    source_bytes = dict(pd.archive_source_bytes())
    source_bytes[PD_PROTOCOL_PATH] = pd_protocol_bytes
    for path in paths:
        name = path.relative_to(root).as_posix()
        if name not in tracked or not path.is_file():
            raise RuntimeError(f"required frozen dependency is missing or untracked: {name}")
        source_bytes[name] = path.read_bytes()
    for name, data in source_bytes.items():
        if name not in tracked:
            raise RuntimeError(f"PD dependency is not tracked: {name}")
        committed = subprocess.check_output(["git", "show", f"{commit}:{name}"], cwd=root)
        if data != committed:
            raise RuntimeError(f"source differs from clean HEAD: {name}")
    return commit, status, pd, source_bytes


class PredictionMeter:
    """Count existing mathematical calls; never perform a reporting prediction."""
    def __init__(self):
        self.counts = {key: 0 for key in PLANNING_KEYS}

    def call(self, callback, *args):
        self.counts["pair_prediction_attempts"] += 1
        try:
            prediction = callback(*args)
        except BaseException as exc:
            self.counts["failed_pair_prediction_attempts"] += 1
            if isinstance(exc, PairPredictionError):
                record = {"scalar_prediction_attempts": exc.scalar_prediction_attempts,
                          "scalar_prediction_successes": exc.scalar_prediction_successes}
            else:
                record = getattr(exc, "pair_prediction_accounting", None)
            if record is None:
                self.counts["unknown_scalar_failure_count"] += 1
            else:
                for key in ("scalar_prediction_attempts", "scalar_prediction_successes"):
                    self.counts[key] += int(record[key])
            raise
        self.counts["pair_prediction_successes"] += 1
        self.counts["scalar_prediction_attempts"] += 2
        self.counts["scalar_prediction_successes"] += 2
        return prediction

    def bind_rls(self, model):
        # Instrument only this instance's existing _predict_state call, keeping
        # model source, parameter state, update and clone mathematics untouched.
        original = model._predict_state
        model._predict_state = lambda *args: self.call(original, *args)

    def snapshot(self):
        unknown = self.counts["unknown_scalar_failure_count"] > 0
        return {**self.counts, "scalar_counts_complete": not unknown,
                "scalar_counts_is_lower_bound": unknown}


def run_guard_pair_development(output, *, protocol_path, synthetic=False,
                               synthetic_source_bytes=None, synthetic_pd_binding=None):
    if synthetic:
        if GroundBodyEnv is _REAL_ENV:
            raise RuntimeError("synthetic execution requires an explicitly replaced environment")
        if synthetic_source_bytes is None or synthetic_pd_binding is None:
            raise RuntimeError("synthetic execution requires explicit source and PD fixtures; no Git fallback")
    elif not FORMAL_EXECUTION_FROZEN:
        # This guard precedes Git, PD/source reads, output creation and physics.
        raise RuntimeError("draft real physics is disabled until root freezes and accepts it")
    output = Path(output)
    if output.exists():
        raise FileExistsError(output)
    root = next(p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file())
    protocol_path = Path(protocol_path).resolve()
    if synthetic:
        source_bytes = dict(synthetic_source_bytes)
        if not source_bytes or any(not isinstance(name, str) or not isinstance(data, bytes)
                                   for name, data in source_bytes.items()):
            raise ValueError("explicit nonempty bytes source fixture required")
        if PROTOCOL_PATH not in source_bytes:
            raise ValueError("fixture must include the exact protocol archive path")
        pd = synthetic_pd_binding
        if pd.get("status") != "selected" or not pd.get("selected_id"):
            raise ValueError("synthetic PD fixture must explicitly identify its selected candidate")
        for key in ("kp", "kd"):
            gains = np.asarray(pd.get(key), dtype=float)
            if gains.shape != (2,) or not np.isfinite(gains).all() or np.any(gains < 0):
                raise ValueError("fixture must supply two finite nonnegative PD gains")
        commit, status = "synthetic-fixture-no-git", ""
    else:
        commit, status, pd, source_bytes = _formal_provenance(root, protocol_path)
    pd_kp, pd_kd = tuple(pd["kp"]), tuple(pd["kd"])
    plans = [{"trial_id": f"seed{seed}_{kind}", "seed": seed, "kind": kind,
              "maximum_control_steps": PREFIX_STEPS + (CALIBRATION_STEPS if kind == "calibration" else
                  (PREDICTION_STEPS if kind == "prediction" else CONTROL_STEPS))}
             for seed in DEVELOPMENT_SEEDS for kind in KINDS]
    episodes = [{**plan, "status": "planned", "reason": None, "collector_exception": None,
                 "control_calls_attempted": 0, "control_steps": 0, "physics_steps": 0,
                 "phase_budgets": {phase: dict(control_calls_attempted=0, control_steps=0, physics_steps=0)
                                   for phase in PHASES}} for plan in plans]
    metadata = {"schema_version": 1, "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "purpose": __doc__, "suite": "guard_pair_development", "synthetic": synthetic,
        "seeds": list(DEVELOPMENT_SEEDS), "split": "development", "pose": "supine",
        "joint_indices": list(JOINT_INDICES), "native_joint_count": 8,
        "source_commit": commit, "source_status": status,
        "source_sha256": {n: hashlib.sha256(b).hexdigest() for n, b in source_bytes.items()},
        "protocol": {"path": PROTOCOL_PATH,
                     "sha256": hashlib.sha256(source_bytes[PROTOCOL_PATH]).hexdigest()},
        "platform": sys.platform if synthetic else platform.platform(),
        "python_executable": sys.executable, "python_version": sys.version,
        "dependencies": dict(sorted((d.metadata["Name"], d.version) for d in importlib.metadata.distributions())),
        "gpu": None, "backend": "synthetic, no physics" if synthetic else "MuJoCo CPU",
        "mujoco_version": mujoco.__version__, "environment_config": asdict(ExplorationConfig()),
        "prefix_steps": PREFIX_STEPS, "calibration_steps": CALIBRATION_STEPS,
        "prediction_steps": PREDICTION_STEPS, "control_steps_per_trial": CONTROL_STEPS,
        "structures": ["diagonal_hinge5"], "model_input_bases": MODEL_BASES,
        "integration": "endpoint_euler", "guard_recomputed_on_each_predicted_start": True,
        "model_input": "current original encoders q/v, already known u and public ranges only; no future actual torque, contact or hidden dynamics",
        "model_label": "next original encoder velocity on complete 20 ms calibration transitions only",
        "guard_interval_boundary": "public G at control start is not realized interval average; physical guard executes every 2 ms",
        "target_information": "current two-axis qref+s*.04 then qref+s*.08 only, no switch preview; infeasible target fails, no clipping",
        "study_abort_spec": {"active_only": True, "absolute_q_minus_qref_rad": .12,
                             "absolute_velocity_rad_s": 1., "comparison": ">=", "any_axis": True,
                             "feedback_action": None, "last_complete_terminal_update_and_score": True},
        "calibration_block_amplitudes_nm": list(CALIBRATION_AMPLITUDES),
        "calibration_schedule": "20 blocks of 20: five shoulder, five elbow, five same-direction, five opposite; 1+/9zero/1-/9zero",
        "schedule_selection": "fixed after previously archived 2/8 stops and 1/9 completion; those zero-update costs remain separately paid",
        "prediction_block_shapes": PREDICTION_SHAPES,
        "prediction_block_amplitudes_nm": [.125, .25, .375, .5, .375],
        "prediction_trajectory_count_per_seed": 1,
        "update_order": ["learned_raw", "learned_guard"],
        "update_cost_unit": "committed scalar next-velocity heads",
        "calibration_planned_request_effort_per_axis": {"absolute_nm_s": [.18, .18], "squared_nm2_s": [.06375, .06375]},
        "prediction_accounting_scope": "diagnostic, RLS-internal and MPC-select counts reported separately; no reporting-time repeat predictions",
        "pd_binding": dict(pd), "pd_gains": {"kp": pd_kp, "kd": pd_kd},
        "pd_boundary": "selected finite two-axis development grid, bound to independent tracked selection/audit/manifest; no legacy fallback",
        "teacher_calls": 0, "external_demonstration_samples": 0, "policy_parameter_updates": 0,
        "gain_updates": 0, "gate_updates": 0, "planned_episodes": plans, "planned_episode_count": len(plans),
        "maximum_control_steps": sum(p["maximum_control_steps"] for p in plans),
        "maximum_physics_steps": 10 * sum(p["maximum_control_steps"] for p in plans),
        "maximum_scalar_updates": len(DEVELOPMENT_SEEDS)*CALIBRATION_STEPS*4,
        "maximum_vector_updates": len(DEVELOPMENT_SEEDS)*CALIBRATION_STEPS*2,
        "maximum_independent_prediction_pair_calls": len(DEVELOPMENT_SEEDS)*PREDICTION_STEPS*4,
        "maximum_mpc_prediction_pair_calls": len(DEVELOPMENT_SEEDS)*CONTROL_STEPS*4*81*15,
        "scientific_gates": "draft; separate independent auditor and root freeze required before real execution",
        "claim_boundary": "development-only two-joint diagnostic; no final/generalization/safety/task-skill claim",
        "complete": False, "archive_status": "running"}
    metadata["source_dirty"] = bool(metadata["source_status"])
    output.mkdir(parents=True)
    with zipfile.ZipFile(output / "source_snapshot.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in source_bytes.items():
            archive.writestr(name, data)
    metadata["source_snapshot_sha256"] = _hash(output / "source_snapshot.zip")
    metadata["independent_auditor"] = {"path": AUDITOR_PATH,
        "sha256": metadata["source_sha256"].get(AUDITOR_PATH),
        "pending": synthetic, "required_for_formal": True}
    seed_results = []
    by_id = {e["trial_id"]: e for e in episodes}
    started, cpu_started = time.perf_counter(), time.process_time()
    fatal = None

    def checkpoint():
        metadata.update({key: sum(e[key] for e in episodes) for key in ("control_calls_attempted", "control_steps", "physics_steps")})
        metadata.update(model_updates=sum(s["calibration_scalar_updates"] for s in seed_results),
            vector_model_updates=sum(s["calibration_vector_updates"] for s in seed_results),
            completed_trials=sum(e["status"] == "completed" for e in episodes),
            terminated_trials=sum(e["status"] == "terminated" for e in episodes),
            exception_trials=sum(e["status"] == "exception" for e in episodes),
            blocked_trials=sum(e["status"] == "blocked" for e in episodes),
            wall_seconds=time.perf_counter()-started, cpu_seconds=time.process_time()-cpu_started)
        errors = []
        for name, data in (("seed_results.json", seed_results), ("episodes.json", episodes), ("metadata.json", metadata)):
            try:
                _write_json(output / name, _archive_record(data) if isinstance(data, dict) else [_archive_record(x) for x in data])
            except BaseException as exc:
                errors.append(exc)
        if errors:
            raise errors[0]

    def block(episode, reason, result=None):
        episode.update(status="blocked", reason=reason)
        if result is not None:
            result["evaluations"][episode["kind"]] = {"completed": False, "status": "blocked", "reason": reason}

    try:
        checkpoint()
        with gzip.open(output / "trace.jsonl.gz", "wt", encoding="utf-8") as trace:
            for seed in DEVELOPMENT_SEEDS:
                reset_seed = int(np.random.SeedSequence(seed).spawn(2)[0].generate_state(1)[0])
                models, calibrators, rls_meters = {}, {}, {}
                reference = directions = None
                calibrated = False
                result = {"seed": seed, "reset_seed": reset_seed, "evaluations": {},
                          "initial_models": {}, "learned_models": {}, "calibration_models": {},
                          "calibration_completed": False, "calibration_scalar_updates": 0,
                          "calibration_vector_updates": 0, "rls_prediction_accounting": {}}
                seed_results.append(result)
                for kind in KINDS:
                    episode = by_id[f"seed{seed}_{kind}"]
                    is_cal, is_pred = kind == "calibration", kind == "prediction"
                    if (is_pred or kind in ("learned_raw", "learned_guard")) and not calibrated:
                        block(episode, {"type": "DependencyBlocked", "dependencies": [f"seed{seed}_calibration"]}, result)
                        checkpoint()
                        continue
                    env = observation = previous = requested = stepped = None
                    index = target = raw_pd = decision = update = None
                    study = error = trace_failure = planner = None
                    phase = "prefix"
                    calls = unreturned_physics = written_steps = returned_steps = 0
                    env_before = None
                    predicted = {}
                    q_errors, partial_errors = [], []
                    prediction_errors = {}
                    diagnostic_meter = PredictionMeter()
                    input_diagnostics = {}
                    effort = {p: {key: np.zeros(2) for key in EFFORT_KEYS} for p in PHASES}
                    known_actual = {p: 0 for p in PHASES}
                    planning = {key: 0 for key in PLANNING_KEYS}
                    planning_unknown_failed_calls = failed_planners = 0
                    planning_seconds, pd_seconds = [], []
                    before_models = _fingerprints(models)
                    fallbacks = 0
                    saturation = np.zeros(2, dtype=int)
                    duration = CALIBRATION_STEPS if is_cal else (PREDICTION_STEPS if is_pred else CONTROL_STEPS)

                    def sync_calibration():
                        result["calibration_models"] = {n: m.snapshot() for n, m in calibrators.items()}
                        result["calibration_scalar_updates"] = sum(m.scalar_update_count for m in calibrators.values())
                        result["calibration_vector_updates"] = sum(m.update_count for m in calibrators.values())
                        result["rls_prediction_accounting"] = {n: meter.snapshot() for n, meter in rls_meters.items()}

                    try:
                        env = GroundBodyEnv(ExplorationConfig())
                        observation = env.reset(seed=reset_seed, pose="supine")
                        native_pair(observation)
                        env_before = env.parameter_fingerprint()
                        previous_torque = (0., 0.)
                        for index in range(PREFIX_STEPS + duration):
                            phase = "prefix" if index < PREFIX_STEPS else ("calibration" if is_cal else ("prediction" if is_pred else "control"))
                            requested = np.zeros(8)
                            target = raw_pd = decision = update = None
                            predicted = {}
                            stepped = None
                            if index == PREFIX_STEPS:
                                q0, _ = native_pair(observation)
                                limits = [env.model.joint(name).range for name in env.joint_names]
                                selections = [direction_record(j, observation["joint_position"], limits) for j in JOINT_INDICES]
                                selected_directions = tuple(record["direction"] for record in selections)
                                if reference is None:
                                    reference, directions = q0, selected_directions
                                    result.update(reference_q=reference, direction=directions, selection_records=selections)
                                elif reference != q0 or directions != selected_directions:
                                    raise RuntimeError("paired native prefix differs; no qref clipping or cached prefix")
                                pair_ranges = tuple(tuple(float(x) for x in limits[j]) for j in JOINT_INDICES)
                                if "nominal_raw" not in models:
                                    for name in ("nominal_raw", "nominal_guard"):
                                        models[name] = InputMappedDiagonalPairBodyModel(q0,
                                            public_joint_ranges=pair_ranges, input_basis=MODEL_BASES[name], trainable=False)
                                    result["nominal_models"] = {n: models[n].snapshot() for n in ("nominal_raw", "nominal_guard")}
                                if is_cal:
                                    calibrators = {name: InputMappedDiagonalPairBodyModel(q0,
                                        public_joint_ranges=pair_ranges, input_basis=MODEL_BASES[name])
                                        for name in ("learned_raw", "learned_guard")}
                                    rls_meters = {name: PredictionMeter() for name in calibrators}
                                    for name, model in calibrators.items():
                                        rls_meters[name].bind_rls(model)
                                    result["initial_models"] = {n: m.snapshot() for n, m in calibrators.items()}
                                else:
                                    before_models = _fingerprints(models)
                                if kind in MPC_KINDS:
                                    planner = FixedPairMPC(models[kind], pair_ranges)
                            q, v = native_pair(observation)
                            if index >= PREFIX_STEPS:
                                active = index - PREFIX_STEPS
                                if is_cal:
                                    command = calibration_request(active, directions)
                                elif is_pred:
                                    command = prediction_request(active, directions)
                                else:
                                    target = tuple(reference[i] + directions[i]*(.04 if active < 100 else .08) for i in range(2))
                                    limits = [env.model.joint(env.joint_names[j]).range for j in JOINT_INDICES]
                                    if any(not limits[i][0]+.03 <= target[i] <= limits[i][1]-.03 for i in range(2)):
                                        raise ValueError("predeclared pair target infeasible; do not clip")
                                    command = (0., 0.)
                                    if planner is not None:
                                        timer = time.perf_counter()
                                        try:
                                            decision = planner.select(q, v, target, previous_torque=previous_torque)
                                        except BaseException as exc:
                                            failed_planners += 1
                                            cost = getattr(exc, "pair_planning_accounting", None)
                                            if cost is None:
                                                planning_unknown_failed_calls += 1
                                            else:
                                                for key, value in _counts(cost).items():
                                                    planning[key] += value
                                            raise
                                        finally:
                                            planning_seconds.append(time.perf_counter()-timer)
                                        for key, value in _counts(decision.to_dict()).items():
                                            planning[key] += value
                                        command = decision.torque
                                        fallbacks += int(decision.fallback)
                                    elif kind == "PDselected":
                                        timer = time.perf_counter()
                                        try:
                                            pairs = [pd_request(q[i], v[i], target[i], pd_kp[i], pd_kd[i]) for i in range(2)]
                                            command, raw_pd = tuple(x[0] for x in pairs), tuple(x[1] for x in pairs)
                                        finally:
                                            pd_seconds.append(time.perf_counter()-timer)
                                requested[list(JOINT_INDICES)] = command
                                if not np.isfinite(requested).all() or np.max(np.abs(requested)) > .5:
                                    raise ValueError("pair request violates shared per-axis permission")
                                # Cal uses the RLS call's returned preupdate prediction:
                                # calling predict here would duplicate that work.
                                active_models = (models if is_pred else
                                    ({kind: models[kind]} if kind in MPC_KINDS else {}))
                                for name, model in active_models.items():
                                    predicted[name] = diagnostic_meter.call(model.predict, q, v, command)
                                if is_pred or kind in MPC_KINDS:
                                    predicted["persistence"] = (tuple(q[i]+.02*v[i] for i in range(2)), v)
                                input_diagnostics = {name: model.describe_input(q, command)
                                    for name, model in (calibrators if is_cal else active_models).items()}
                            previous = observation
                            calls += 1
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
                            if index >= PREFIX_STEPS:
                                study = native_study_abort(next_q, next_v, reference)
                                if study is not None:
                                    study.update(phase=phase, step_index=index)
                            executed = stepped.diagnostics["executed_substeps"]
                            if type(executed) is not int or executed != env.physics_steps-old_physics:
                                raise RuntimeError("returned substep count differs from paid physics")
                            realized = np.asarray(stepped.diagnostics["applied_torque_history"], dtype=float)
                            if executed == 0 and realized.size == 0:
                                realized = realized.reshape((0, 8))
                            if realized.shape != (executed, 8) or not np.isfinite(realized).all() or np.max(np.abs(realized), initial=0.) > .5:
                                raise RuntimeError("full native applied history invalid; actual effort remains unknown")
                            selected = realized[:, list(JOINT_INDICES)]
                            effort[phase]["actual_absolute_nm_s"] += np.sum(np.abs(selected), axis=0)*env.config.physics_dt
                            effort[phase]["actual_squared_nm2_s"] += np.sum(selected**2, axis=0)*env.config.physics_dt
                            known_actual[phase] += executed
                            if index >= PREFIX_STEPS:
                                if executed != 10:
                                    if target is not None:
                                        partial_errors.append({"step_index": index, "target_q": target,
                                            "errors_rad": [next_q[i]-target[i] for i in range(2)], "executed_substeps": executed})
                                    update = {"updated": False, "phase": "partial_calibration_interval", "executed_substeps": executed} if is_cal else None
                                else:
                                    if is_cal:
                                        try:
                                            update = update_shared_models(calibrators, q, v, command, next_v,
                                                transition_id=f"seed{seed}_{kind}:{index}")
                                        finally:
                                            sync_calibration()
                                        predicted = {name: (tuple(record["preupdate_prediction"]["next_q_rad"]),
                                                            tuple(record["preupdate_prediction"]["next_v_rad_s"]))
                                            for name, record in update.items()}
                                    for name, prediction in predicted.items():
                                        errors = prediction_errors.setdefault(name, {"q": [], "v": []})
                                        errors["q"].append([next_q[i]-prediction[0][i] for i in range(2)])
                                        errors["v"].append([next_v[i]-prediction[1][i] for i in range(2)])
                                    if target is not None:
                                        q_errors.append([next_q[i]-target[i] for i in range(2)])
                                        saturation += np.asarray([abs(command[i]) == .5 for i in range(2)], dtype=int)
                            row = {"trial_id": episode["trial_id"], "seed": seed, "kind": kind,
                                "joint_indices": JOINT_INDICES, "shared_transition_id": f"seed{seed}_{kind}:{index}",
                                "step_index": index, "phase": phase, "study_abort": study, "target_q": target,
                                "partial_interval_target_error_rad": None if executed == 10 or target is None else [next_q[i]-target[i] for i in range(2)],
                                "requested_torque": requested, "raw_pd_torque_nm": raw_pd,
                                "observation_before": previous, "observation_after": observation,
                                "predicted_next_qv": predicted, "model_input_diagnostics": input_diagnostics,
                                "model_update": update, "diagnostics": stepped.diagnostics,
                                "planner_decision": None if decision is None else decision.to_dict(),
                                "qpos": env.data.qpos, "qvel": env.data.qvel}
                            try:
                                trace.write(json.dumps(_archive_record(row), allow_nan=False)+"\n")
                            except BaseException as exc:
                                trace_failure = exc
                                raise
                            written_steps += 1
                            previous_torque = tuple(requested[j] for j in JOINT_INDICES)
                            if stepped.terminated or study is not None:
                                break
                        if env_before != env.parameter_fingerprint():
                            raise RuntimeError("physical parameters changed")
                        if not is_cal and before_models != _fingerprints(models):
                            raise RuntimeError("evaluation changed frozen body models")
                    except BaseException as exc:
                        error = _error(exc)
                        failure_record = {name: getattr(exc, name, None) for name in
                            ("pair_update_accounting", "shared_pair_update_accounting", "pair_planning_accounting", "pair_prediction_accounting")}
                        if hasattr(exc, "to_dict"):
                            failure_record["structured_failure"] = exc.to_dict()
                        episode["failure_accounting"] = failure_record
                        try:
                            trace.write(json.dumps(_archive_record({"trial_id": episode["trial_id"], "seed": seed,
                                "kind": kind, "joint_indices": JOINT_INDICES, "phase": phase, "step_index": index,
                                "shared_transition_id": None if index is None else f"seed{seed}_{kind}:{index}",
                                "collector_exception": error, "study_abort": study, "requested_torque": requested,
                                "observation_before": previous, "observation_after": observation,
                                "target_q": target, "raw_pd_torque_nm": raw_pd, "predicted_next_qv": predicted,
                                "model_update": update, "model_input_diagnostics": input_diagnostics,
                                "diagnostic_prediction_accounting": diagnostic_meter.snapshot(),
                                "rls_prediction_accounting": {n: meter.snapshot() for n, meter in rls_meters.items()} if is_cal else {},
                                "failure_accounting": failure_record,
                                "partial_model_snapshots": {n: m.snapshot() for n, m in calibrators.items()} if is_cal else {},
                                "returned_step_diagnostics": None if stepped is None else stepped.diagnostics,
                                "planner_decision": None if decision is None else decision.to_dict(),
                                **_exception_snapshot(env)}), allow_nan=False)+"\n")
                        except BaseException as write_exc:
                            trace_failure = trace_failure or write_exc
                            episode["exception_trace_write_error"] = _error(write_exc)
                        if isinstance(exc, (KeyboardInterrupt, SystemExit, OSError)) or trace_failure is not None:
                            fatal = exc
                    finally:
                        full_intervals = (env is not None and env.step_id == PREFIX_STEPS+duration
                            and env.physics_steps == 10*(PREFIX_STEPS+duration))
                        if is_cal:
                            sync_calibration()
                            calibrated = (error is None and full_intervals and not env.terminated and study is None
                                and len(calibrators) == 2 and all(m.update_count == duration for m in calibrators.values()))
                            result["calibration_completed"] = calibrated
                            if calibrated:
                                models.update({n: m.clone_frozen() for n, m in calibrators.items()})
                                result["learned_models"] = {n: models[n].snapshot() for n in calibrators}
                            else:
                                # Keep failed parameters and actual commits in the
                                # calibration ledger, outside independent baselines.
                                for name in calibrators:
                                    models.pop(name, None)
                        terminated = env is not None and (env.terminated or study is not None)
                        completed = error is None and full_intervals and not terminated
                        status = "exception" if error is not None else ("terminated" if terminated else ("completed" if completed else "incomplete"))
                        reason = env.reason if env is not None and env.terminated else (study if study is not None else error)
                        known = {p: known_actual[p] == episode["phase_budgets"][p]["physics_steps"] for p in PHASES}
                        missing = {p: episode["phase_budgets"][p]["physics_steps"]-known_actual[p] for p in PHASES}
                        episode.update(_archive_record({"control_calls_attempted": calls,
                            "control_steps": 0 if env is None else env.step_id, "physics_steps": 0 if env is None else env.physics_steps,
                            "status": status, "completed": completed, "reason": reason, "collector_exception": error,
                            "study_abort": study, "environment_terminated": None if env is None else env.terminated,
                            "environment_stop_reason": None if env is None else env.reason,
                            "trace_write_failure": None if trace_failure is None else _error(trace_failure),
                            "unreturned_physics_steps": unreturned_physics, "returned_steps": returned_steps,
                            "written_returned_steps": written_steps, "returned_unwritten_steps": returned_steps-written_steps,
                            "risk_telemetry_complete": error is None and unreturned_physics == 0 and trace_failure is None,
                            "environment_fingerprint_before": env_before,
                            "environment_fingerprint_after": None if env is None else env.parameter_fingerprint()}))
                        result["evaluations"][kind] = _archive_record({
                            "completed": completed, "status": status, "reason": reason, "collector_exception": error,
                            "study_abort": study, "environment_terminated": episode["environment_terminated"],
                            "environment_stop_reason": episode["environment_stop_reason"],
                            "tracking_rmse": _rmse(q_errors), "metric_control_step_count": len(q_errors),
                            "position_prediction_rmse": {n: _rmse(x["q"]) for n, x in prediction_errors.items()},
                            "velocity_prediction_rmse": {n: _rmse(x["v"]) for n, x in prediction_errors.items()},
                            "metric_prediction_step_count": {n: len(x["v"]) for n, x in prediction_errors.items()},
                            "partial_interval_target_errors_rad": partial_errors,
                            "phase_effort": effort, "control_effort": effort["control"],
                            "phase_effort_combined": {p: {key: float(values.sum()) for key, values in effort[p].items()} for p in PHASES},
                            "phase_actual_effort_substeps": known_actual, "phase_actual_effort_complete": known,
                            "phase_missing_actual_effort_substeps": missing,
                            "actual_effort_complete": known["control"], "actual_effort_is_lower_bound": not known["control"],
                            "actual_control_effort_substeps": known_actual["control"],
                            "missing_control_effort_substeps": missing["control"],
                            "diagnostic_prediction_accounting": diagnostic_meter.snapshot(),
                            "planning_accounting": {**planning,
                                "scalar_counts_complete": planning_unknown_failed_calls == 0 and planning["unknown_scalar_failure_count"] == 0,
                                "scalar_counts_is_lower_bound": planning_unknown_failed_calls > 0 or planning["unknown_scalar_failure_count"] > 0,
                                "unknown_failed_planner_calls": planning_unknown_failed_calls},
                            "failed_planner_attempts": failed_planners, "planner_attempt_count": len(planning_seconds),
                            "planner_decision_count": len(planning_seconds)-failed_planners,
                            "planner_fallbacks": fallbacks, "saturated_control_steps_per_axis": saturation,
                            "controller_seconds_total": sum(planning_seconds), "pd_seconds_total": sum(pd_seconds),
                            "planner_spec": None if planner is None else planner.spec(),
                            "models_before": before_models, "models_after": _fingerprints(models)})
                        try:
                            checkpoint()
                        except BaseException as exc:
                            fatal = fatal or exc
                            metadata["checkpoint_exception"] = _error(exc)
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
                block(episode, {"type": "ArchiveAborted", "message": "fatal before planned episode"})
        metadata["all_trials_successful"] = all(e["status"] == "completed" for e in episodes)
        try:
            checkpoint()
            _write_json(output / "manifest.json", {p.name: _hash(p) for p in sorted(output.iterdir()) if p.is_file() and p.name != "manifest.json"})
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
        parser.error("real execution disabled: root has not frozen and accepted the guard pair protocol and PD binding")
    print(json.dumps(run_guard_pair_development(args.output, protocol_path=args.protocol), indent=2))


if __name__ == "__main__":
    main()
