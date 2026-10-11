"""Frozen local-body validation with declared classical/zero baselines.

Only calibration learns. Current native encoder signals and fixed target drive
all controllers; independent baselines do not require successful calibration.
No task teacher, physical-model features or simulator query enters an action.
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

from .collect import _archive_record, _exception_snapshot, _hash, _write_json
from .environment import ExplorationConfig, GroundBodyEnv, MODEL_PATH, POSES
from .local_model import LocalBodyModel, HingeBodyModel, FixedLocalMPC
from .local_integration import FrozenIntegrationModel
from .probes import direction_record
from .feedback_validate import pd_request


FROZEN_INTEGRATION = "endpoint_euler"
# C2-C coverage and performance gates failed; retain the original short recipe.
FROZEN_FINAL_SCHEDULE = "short"
SUITES = {
    "shoulder_final": {"pose": "supine", "joint": 0, "seeds": [20, 21, 22],
                       "split": "final_holdout", "pd_kp": 64., "pd_kd": 0.},
    "elbow_development": {"pose": "supine", "joint": 1, "seeds": [0, 1, 2],
                          "split": "development", "pd_kp": 64., "pd_kd": 1.},
}

SUITE_PROTOCOLS = {
    "shoulder_final": "docs/LOCAL_FROZEN_VALIDATION_PROTOCOL.md",
    "elbow_development": "docs/ELBOW_BODY_DEVELOPMENT_PROTOCOL.md",
}
PD_SELECTION_SOURCES = {
    "elbow_development": (
        ("source_commit", "91223b39c86fbeb09f7bc399229789b1e00ce181"),
        ("audit_sha256", "d84ad31b28f7fcc4ded8003b2503138a3cacc9f9b2fed33bf675758e43100571"),
        ("summary_sha256", "5aaefe21d6aa8314673a5560522e8865123acda318e833b4951f4c5d00efc3e8"),
        ("candidate", 8), ("development_control_calls", 7521),
        ("development_physics_substeps", 75210), ("body_model_updates", 0),
    ),
}

FROZEN_CALIBRATION_DOSE = "old"
FROZEN_MODEL_STRUCTURE = "hinge5"
CALIBRATION_AMPLITUDES_NM = (.125, .25, .5, .125, .25, .5, .125, .25, .5, .125)


def calibration_schedule_spec():
    return {
        "short": "ten 30-step blocks: +A*5, zero*10, -A*5, zero*10",
        "reordered": "+A repeated five in original order*50, zero*100, -A in same order*50, zero*100",
        "same_full_command_histogram": True,
        "short_switch_count_from_zero": 40,
        "reordered_switch_count_from_zero": 22,
        "causal_claim": "Total temporal-reordering effect; not isolated position exposure",
    }


def calibration_request(schedule, active, direction):
    """Index-only fixed request; q, v, target and contact are not inputs."""
    if schedule not in ("short", "reordered") or type(active) is not int or not 0 <= active < 300:
        raise ValueError("predeclared schedule and active integer in [0,300) required")
    amplitudes = CALIBRATION_AMPLITUDES_NM
    if schedule == "short":
        slot = active % 30
        return direction * amplitudes[active//30] * (1 if slot < 5 else (-1 if 15 <= slot < 20 else 0))
    if active < 50:
        return direction * amplitudes[active//5]
    if 150 <= active < 200:
        return -direction * amplitudes[(active-150)//5]
    return 0.


def study_abort_spec():
    return {"phase": "every trial active only; never prefix", "absolute_q_minus_qref_rad": .12,
            "absolute_velocity_rad_s": 1., "comparison": ">=",
            "checks": ["every returned active endpoint"],
            "action": "end episode; no corrective command, continuation or replacement",
            "environment_protection": "unchanged; independent environment stop reason takes precedence",
            "last_complete_transition": "RLS update and endpoint metrics retained before stop",
            "claim_boundary": "Native research stop is not a proof of safety or real-world braking"}


def native_study_abort(q, v, qref, *, stage):
    """Stop verdict from current encoders only, never a feedback action."""
    displacement = float(q)-float(qref)
    triggers = []
    if abs(displacement) >= .12:
        triggers.append("absolute_q_minus_qref_rad")
    if abs(float(v)) >= 1.:
        triggers.append("absolute_velocity_rad_s")
    return None if not triggers else {
        "type": "StudyAbort", "message": "predeclared native active envelope reached",
        "stage": stage, "triggers": triggers, "q_rad": float(q), "qref_rad": float(qref),
        "q_minus_qref_rad": displacement, "velocity_rad_s": float(v),
        "thresholds": {"absolute_q_minus_qref_rad": .12, "absolute_velocity_rad_s": 1.},
        "feedback_action": None,
    }


def phase_budget_names():
    return ("prefix", "calibration", "prediction", "control")


def run_validation(output: Path, seeds: list[int] | None = None, *, suite="shoulder_final",
                   calibration_schedule: str, protocol_path: Path,
                   integration=FROZEN_INTEGRATION,
                   calibration_dose=FROZEN_CALIBRATION_DOSE,
                   model_structure=FROZEN_MODEL_STRUCTURE, pd_kp=None, pd_kd=None):
    if type(suite) is not str or suite not in SUITES:
        raise ValueError("predeclared suite required")
    spec = dict(SUITES[suite])
    if spec["pd_kp"] is None or spec["pd_kd"] is None:
        raise ValueError("suite PD gains have not been frozen by a separate development protocol")
    seeds = list(spec["seeds"]) if seeds is None else seeds
    if seeds != spec["seeds"] or any(type(seed) is not int for seed in seeds):
        raise ValueError("suite requires its exact predeclared seeds in order")
    pose, joint, split = spec["pose"], spec["joint"], spec["split"]
    pd_kp = spec["pd_kp"] if pd_kp is None else pd_kp
    pd_kd = spec["pd_kd"] if pd_kd is None else pd_kd
    for name, supplied in (("pd_kp",pd_kp),("pd_kd",pd_kd)):
        if isinstance(supplied,bool) or not isinstance(supplied,(int,float)) or not np.isfinite(supplied) or supplied != spec[name]:
            raise ValueError("PD gains must equal the precise frozen suite declaration")
    if integration != FROZEN_INTEGRATION:
        raise ValueError("frozen integration must be endpoint_euler")
    if type(calibration_schedule) is not str or calibration_schedule not in ("short","reordered"):
        raise ValueError("predeclared short/reordered schedule required")
    if FROZEN_FINAL_SCHEDULE is not None and calibration_schedule != FROZEN_FINAL_SCHEDULE:
        raise ValueError("schedule must equal root's frozen final declaration")
    if type(calibration_dose) is not str or calibration_dose != FROZEN_CALIBRATION_DOSE:
        raise ValueError("frozen calibration dose must be old")
    if type(model_structure) is not str or model_structure != FROZEN_MODEL_STRUCTURE:
        raise ValueError("frozen model structure must be hinge5")
    prediction_amplitudes = {"low": [.25]*5, "full": [.125, .25, .375, .5, .375]}
    output = Path(output)
    if output.exists():
        raise FileExistsError(output)
    root = next(p for p in Path(__file__).resolve().parents
                if (p/"pyproject.toml").is_file() and (p/"src/developmental_physics").is_dir())
    sources = [*sorted((root / "src/developmental_physics").glob("*.py")),
               Path(__file__), root / "src/developmental_physics/local_integration.py", MODEL_PATH, root / "pyproject.toml"]
    protocol_path = Path(protocol_path).resolve()
    if not protocol_path.is_file() or protocol_path != (root/SUITE_PROTOCOLS[suite]).resolve():
        raise ValueError("exact frozen suite protocol required")
    sources.append(protocol_path)
    source_bytes = {p.relative_to(root).as_posix(): p.read_bytes() for p in sources}
    metadata = {
        "schema_version": 1, "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "purpose": "Frozen local-body validation against nominal MPC, tuned PD and zero torque",
        "suite": suite, "suite_spec": spec, "calibration_schedule": calibration_schedule,
        "pd_selection_source": dict(PD_SELECTION_SOURCES.get(suite, ())),
        "pd_gains": {"kp":pd_kp,"kd":pd_kd},
        "pd_gains_source": "Exact predeclared suite constants; no gain development in this archive",
        "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
        "source_status": subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=all"], cwd=root, text=True),
        "source_sha256": {n: hashlib.sha256(b).hexdigest() for n,b in source_bytes.items()},
        "platform": platform.platform(), "python_executable": sys.executable, "python_version": sys.version,
        "dependencies": dict(sorted((d.metadata["Name"], d.version) for d in importlib.metadata.distributions())),
        "gpu": None, "backend": "MuJoCo CPU", "mujoco_version": mujoco.__version__,
        "environment_config": asdict(ExplorationConfig()),
        "pose": pose, "joint_index": joint, "seeds": seeds, "split": split,
        "structures": [model_structure], "integration": integration,
        "calibration_dose": calibration_dose, "model_structure": model_structure,
        "calibration_schedules": [calibration_schedule],
        "calibration_block_amplitudes_nm": CALIBRATION_AMPLITUDES_NM,
        "calibration_schedule_definition": calibration_schedule_spec(),
        "study_abort_spec": study_abort_spec(),
        "prediction_block_amplitudes_nm": prediction_amplitudes,
        "prefix_steps": 100, "calibration_steps": 300, "prediction_steps": 100, "control_steps_per_trial": 200,
        "teacher_calls": 0, "external_demonstration_samples": 0, "policy_parameter_updates": 0,
        "model_input": "current encoder position/velocity and requested torque known before integration",
        "model_label": "next encoder velocity; no hidden mass, contact or future actual torque features",
        "comparison": {"methods": ["nominal_mpc","learned_mpc","tuned_pd","zero_torque"],
                       "single_schedule": calibration_schedule,
                       "single_fixed_dose": calibration_dose, "single_fixed_structure": model_structure},
        "nominal_model": "shared frozen linear4; hinge5 initial zero-hinge predictions are equivalent",
        "rls_preupdate_position_diagnostic": "endpoint_euler; unchanged raw model_update diagnostic",
        "evaluation_prediction_integration": integration,
        "fixed_mpc_config": "Existing FixedLocalMPC defaults unchanged; full spec archived per evaluation",
        "initial_controller_capability": "Existing MPC and frozen PD have public target-position control capability; PD actions read encoders/target and frozen gains only; zero-torque reads no model",
        "pd_controller_spec": {"implementation":"feedback_validate.pd_request", "kp":pd_kp,"kd":pd_kd,
                               "input":"current encoder q/v and currently disclosed target", "permission_nm":.5,
                               "body_model_input":False,"gain_updates":0},
        "zero_torque_spec": "Fixed zero request; shared target is used solely for scoring",
        "target_information": "Current qref+s*0.04 or qref+s*0.08 target only; no preview of switch",
        "native_study_abort_boundary": "Research endpoint stop is not a physical braking action or a safety proof",
        "protocol": {"path": protocol_path.relative_to(root).as_posix(), "sha256": _hash(protocol_path)},
        "claim_boundary": "Local single-joint learning only; no rolling, standing, walking or real robot result.",
        "completion_definition": "Every planned episode has a recorded outcome; no scientific benefit gate is implied.",
        "trial_success_definition": "Episode completed without exception or stop; not a model/control benefit criterion.",
        "cpu_seconds_scope": "Current process only; same timer-start/checkpoint scope as wall_seconds; excludes imports, initial source snapshot and setup before timers",
        "complete": False,
    }
    metadata["source_dirty"] = bool(metadata["source_status"])
    output.mkdir(parents=True)
    with zipfile.ZipFile(output/"source_snapshot.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in source_bytes.items():
            archive.writestr(name, data)
    kinds = ("calibration", "prediction_low", "prediction_full", "nominal_mpc",
             "learned_mpc", "tuned_pd", "zero_torque")
    planned = [{"trial_id": f"seed{seed}_{kind}", "seed": seed, "kind": kind,
                "model_scope": ("nominal" if kind == "nominal_mpc" else ("learned" if kind == "learned_mpc" else
                                ("controller_only" if kind in ("tuned_pd","zero_torque") else "shared"))),
                "calibration_dose": calibration_dose if kind == "calibration" or kind == "learned_mpc" else None,
                "calibration_schedule": calibration_schedule if kind == "calibration" or kind == "learned_mpc" else None,
                "model_structure": model_structure if kind == "calibration" or kind == "learned_mpc" else ("linear4" if kind == "nominal_mpc" else None),
                "integration": integration,
                "maximum_control_steps": 100 + (300 if kind == "calibration" else
                                                (100 if kind.startswith("prediction_") else 200))}
               for seed in seeds for kind in kinds]
    metadata.update(planned_episodes=planned, planned_episode_count=len(planned),
                    maximum_control_steps=sum(p["maximum_control_steps"] for p in planned),
                    archive_status="running")
    episodes = [{**plan, "status": "planned", "reason": None, "collector_exception": None,
                 "control_calls_attempted": 0, "control_steps": 0, "physics_steps": 0,
                 "phase_budgets": {p: dict(control_calls_attempted=0, control_steps=0, physics_steps=0)
                                   for p in ("prefix", "calibration", "prediction", "control")}}
                for plan in planned]
    by_id = {episode["trial_id"]: episode for episode in episodes}
    seed_results = []
    started = time.perf_counter()
    cpu_started = time.process_time()

    def checkpoint():
        metadata.update(control_calls_attempted=sum(e["control_calls_attempted"] for e in episodes),
                        control_steps=sum(e["control_steps"] for e in episodes),
                        physics_steps=sum(e["physics_steps"] for e in episodes),
                        model_updates=sum(s["calibration_updates"] for s in seed_results),
                        exception_trials=sum(e["status"] == "exception" for e in episodes),
                        terminated_trials=sum(e["status"] == "terminated" for e in episodes),
                        completed_trials=sum(e["status"] == "completed" for e in episodes),
                        blocked_trials=sum(e["status"] == "blocked" for e in episodes),
                        unprocessed_trials=sum(e["status"] == "planned" for e in episodes),
                        wall_seconds=time.perf_counter()-started,
                        cpu_seconds=time.process_time()-cpu_started)
        metadata["failed_trials"] = metadata["exception_trials"] + metadata["terminated_trials"]
        metadata["skipped_trials"] = metadata["blocked_trials"]
        # Save parameters and costs first. Attempt every checkpoint file even
        # when one write fails; a secondary failure must not hide the model.
        errors = []
        for filename, record in (("seed_results.json", seed_results),
                                 ("episodes.json", episodes), ("metadata.json", metadata)):
            try:
                archived = (_archive_record(record) if isinstance(record, dict)
                            else [_archive_record(item) for item in record])
                _write_json(output / filename, archived)
            except Exception as exc:
                errors.append(exc)
        if errors:
            raise errors[0]

    def fingerprints(models):
        return {name: model.parameter_fingerprint() for name, model in models.items()}

    def block(episode, reason):
        episode.update(status="blocked", reason=reason)

    fatal = None
    try:
        checkpoint()
        with gzip.open(output/"trace.jsonl.gz", "wt", encoding="utf-8") as trace:
            for seed in seeds:
                reset_seed = int(np.random.SeedSequence(seed).spawn(2)[0].generate_state(1)[0])
                models = {}
                views = {}
                calibrators = {}
                direction = None
                reference = None
                calibration_complete = {calibration_schedule: False}
                result_seed = {"seed": seed, "reset_seed": reset_seed, "evaluations": {},
                               "calibration_updates": 0, "calibration_completed": dict(calibration_complete),
                               "calibration_models": {}, "initial_models": {}, "learned_models": {}}
                seed_results.append(result_seed)
                for kind in kinds:
                    episode = by_id[f"seed{seed}_{kind}"]
                    is_calibration = kind == "calibration"
                    is_prediction = kind.startswith("prediction_")
                    schedule = calibration_schedule if is_calibration or kind == "learned_mpc" else None
                    dependencies = [calibration_schedule] if is_prediction or kind == "learned_mpc" else []
                    missing = [d for d in dependencies if not calibration_complete[d]]
                    if missing:
                        reason = {"type": "DependencyBlocked", "message": "required calibration did not complete",
                                  "dependencies": [f"seed{seed}_calibration" for d in missing]}
                        block(episode, reason)
                        result_seed["evaluations"][kind] = {"completed": False, "status": "blocked", "reason": reason}
                        checkpoint()
                        continue
                    env = None
                    observation = previous = requested = None
                    calls = 0
                    phase = "prefix"
                    error = None
                    study_reason = None
                    env_before = None
                    before_models = None if is_calibration else fingerprints(models)
                    before_views = {name: view.integration_fingerprint() for name,view in views.items()}
                    if is_calibration:
                        calibrators = {}
                    index = target = decision = update = None
                    predicted = {}
                    q_errors = []
                    partial_interval_target_errors = []
                    predictions_v = {}
                    predictions_q = {n: [] for n in predictions_v}
                    phase_effort = {name: {"requested_absolute_nm_s": 0., "requested_squared_nm2_s": 0.,
                                          "actual_absolute_nm_s": 0., "actual_squared_nm2_s": 0.}
                                    for name in phase_budget_names()}
                    effort = phase_effort["control"]
                    actual_effort_substeps = {name: 0 for name in phase_effort}
                    saturated = fallbacks = mathematical_calls = 0
                    failed_planner_attempts = 0
                    unreturned_physics_steps = actual_control_effort_substeps = 0
                    action_times = []
                    pd_times = []
                    failed_pd_attempts = 0
                    raw_pd = None
                    phase_budget = episode["phase_budgets"]
                    planner = None
                    trace_failure = None
                    duration = 300 if is_calibration else (100 if is_prediction else 200)
                    try:
                        env = GroundBodyEnv()
                        observation = env.reset(seed=reset_seed, pose=pose)
                        env_before = env.parameter_fingerprint()
                        previous_torque = 0.
                        for index in range(100+duration):
                            phase = "prefix" if index < 100 else ("calibration" if is_calibration else ("prediction" if is_prediction else "control"))
                            requested = np.zeros(8)
                            target = None
                            predicted = {}
                            update = None
                            decision = None
                            raw_pd = None
                            if index == 100:
                                record = direction_record(joint, observation["joint_position"],
                                    [env.model.joint(n).range for n in env.joint_names])
                                q0 = float(observation["joint_position"][joint])
                                if reference is None:
                                    reference, direction = q0, record["direction"]
                                    models["nominal"] = LocalBodyModel(qref=q0, trainable=False)
                                    views["nominal_mpc"] = FrozenIntegrationModel(models["nominal"], integration)
                                    result_seed.update(reference_q=q0, direction=direction, selection_record=record,
                                                       nominal_model=models["nominal"].snapshot())
                                elif q0 != reference or record["direction"] != direction:
                                    raise RuntimeError("paired prefix reference or direction differs")
                                if kind == "nominal_mpc":
                                    # Reconstruct the generic prior from this branch's
                                    # own paid prefix; no successful fit is required.
                                    models["nominal"] = LocalBodyModel(qref=q0, trainable=False)
                                    views["nominal_mpc"] = FrozenIntegrationModel(models["nominal"], integration)
                                    result_seed["nominal_model"] = models["nominal"].snapshot()
                                if is_calibration:
                                    calibrators = {model_structure: HingeBodyModel(qref=q0)}
                                    for structure, calibrator in calibrators.items():
                                        name = f"{schedule}_{structure}"
                                        models[name] = calibrator
                                        result_seed["initial_models"][name] = calibrator.clone_frozen().snapshot()
                                    predictions_v = {n: [] for n in calibrators}
                                    predictions_q = {n: [] for n in predictions_v}
                                else:
                                    # The nominal branch is independent even when both
                                    # calibration prefixes failed before a reference existed.
                                    before_models = fingerprints(models)
                                    before_views = {name:view.integration_fingerprint() for name,view in views.items()}
                                    result_seed["integration_models"] = {name:view.snapshot() for name,view in views.items()}
                                    predictions_v = {name: [] for name in [*views, "persistence"]}
                                    predictions_q = {name: [] for name in predictions_v}
                                    if kind.endswith("mpc"):
                                        planner = FixedLocalMPC(views[kind], env.model.joint(env.joint_names[joint]).range)
                            q, v = (float(observation[key][joint]) for key in ("joint_position", "joint_velocity"))
                            if index >= 100:
                                active = index-100
                                if is_calibration:
                                    requested[joint] = calibration_request(schedule, active, direction)
                                elif is_prediction:
                                    slot = active % 20
                                    amplitude = prediction_amplitudes[kind.split("_")[1]][active//20]
                                    requested[joint] = direction*(amplitude if slot < 7 else (-amplitude if 10 <= slot < 17 else 0.))
                                else:
                                    target = reference + direction*(.04 if active < 100 else .08)
                                    limits = env.model.joint(env.joint_names[joint]).range
                                    if not limits[0]+.03 <= target <= limits[1]-.03:
                                        raise ValueError("predeclared target outside public interior; do not clip")
                                    if planner is not None:
                                        timer = time.perf_counter()
                                        try:
                                            decision = planner.select(q, v, target, previous_torque=previous_torque)
                                        except BaseException:
                                            failed_planner_attempts += 1
                                            raise
                                        finally:
                                            action_times.append(time.perf_counter()-timer)
                                        requested[joint] = decision.torque
                                        fallbacks += int(decision.fallback)
                                        mathematical_calls += decision.mathematical_prediction_calls
                                    elif kind == "tuned_pd":
                                        timer = time.perf_counter()
                                        try:
                                            requested[joint], raw_pd = pd_request(q,v,target,pd_kp,pd_kd)
                                        except BaseException:
                                            failed_pd_attempts += 1
                                            raise
                                        finally:
                                            pd_times.append(time.perf_counter()-timer)
                                    # zero_torque leaves every joint request at zero.
                                if is_calibration:
                                    predicted = {name: model.predict(q,v,requested[joint]) for name,model in calibrators.items()}
                                else:
                                    predicted = {name: view.predict(q,v,requested[joint]) for name,view in views.items()}
                                    predicted["persistence"] = (q + .02*v, v)
                            previous = observation
                            calls += 1
                            old_control, old_physics = env.step_id, env.physics_steps
                            phase_budget[phase]["control_calls_attempted"] += 1
                            try:
                                stepped = env.step(requested)
                            except BaseException:
                                lost = env.physics_steps-old_physics
                                unreturned_physics_steps += lost
                                raise
                            finally:
                                phase_budget[phase]["control_steps"] += env.step_id-old_control
                                phase_budget[phase]["physics_steps"] += env.physics_steps-old_physics
                                paid_dt = (env.physics_steps-old_physics)*env.config.physics_dt
                                phase_effort[phase]["requested_absolute_nm_s"] += abs(float(requested[joint]))*paid_dt
                                phase_effort[phase]["requested_squared_nm2_s"] += float(requested[joint])**2*paid_dt
                            observation = stepped.observation
                            if index >= 100:
                                study_reason = native_study_abort(
                                    float(observation["joint_position"][joint]),
                                    float(observation["joint_velocity"][joint]), reference,
                                    stage="endpoint")
                                if study_reason is not None:
                                    study_reason.update(phase=phase, step_index=index)
                            if stepped.diagnostics["executed_substeps"] != env.physics_steps-old_physics:
                                raise RuntimeError("returned substep count differs from paid physics cost")
                            executed = stepped.diagnostics["executed_substeps"]
                            realized = np.asarray(stepped.diagnostics["applied_torque_history"], dtype=float)
                            if executed == 0 and realized.size == 0:
                                realized = realized.reshape(0, 8)
                            if realized.shape != (executed, 8):
                                raise RuntimeError("applied torque history differs from paid substeps")
                            if not np.isfinite(realized).all() or np.max(np.abs(realized),initial=0.) > .5:
                                raise RuntimeError("applied torque history violates the shared permission")
                            phase_effort[phase]["actual_absolute_nm_s"] += float(np.sum(np.abs(realized[:,joint])))*env.config.physics_dt
                            phase_effort[phase]["actual_squared_nm2_s"] += float(np.sum(realized[:,joint]**2))*env.config.physics_dt
                            actual_effort_substeps[phase] += executed
                            actual_control_effort_substeps = actual_effort_substeps["control"]
                            next_v = float(observation["joint_velocity"][joint])
                            if index >= 100:
                                if executed != 10 and target is not None:
                                    partial_interval_target_errors.append(float(observation["joint_position"][joint])-target)
                                if is_calibration:
                                    update = {}
                                    for structure, calibrator in calibrators.items():
                                        if stepped.diagnostics["executed_substeps"] == 10:
                                            item = calibrator.update(q, v, float(requested[joint]), next_v)
                                            item["coefficients_after"] = calibrator.coefficients.tolist()
                                            item["covariance_after"] = calibrator.covariance.tolist()
                                        else:
                                            item = {"updated": False, "phase": "partial_calibration_interval",
                                                    "executed_substeps": stepped.diagnostics["executed_substeps"],
                                                    "reason": "velocity model requires a complete 20 ms interval",
                                                    "update_count": calibrator.update_count}
                                        item["model_id"] = f"{schedule}_{structure}"
                                        item["shared_transition_id"] = f"seed{seed}_{kind}:{index}"
                                        update[structure] = item
                                        result_seed["calibration_updates"] = sum(m.update_count for n,m in models.items() if n != "nominal")
                                # A shorter protected interval cannot be scored as a
                                # complete 20 ms prediction/control transition.
                                if executed == 10:
                                    for name, prediction in predicted.items():
                                        predictions_v[name].append(next_v-float(prediction[1]))
                                        predictions_q[name].append(float(observation["joint_position"][joint])-float(prediction[0]))
                                    if target is not None:
                                        q_errors.append(float(observation["joint_position"][joint])-target)
                                        saturated += int(abs(float(requested[joint])) == .5)
                            row = json.dumps(_archive_record({
                                "trial_id": f"seed{seed}_{kind}", "seed": seed, "kind": kind,
                                "shared_transition_id": f"seed{seed}_{kind}:{index}",
                                "model_scope": episode["model_scope"], "integration": integration,
                                "calibration_dose": episode["calibration_dose"], "model_structure": episode["model_structure"],
                                "calibration_schedule": schedule, "study_abort": study_reason,
                                "step_index": index, "phase": phase, "target_q": target,
                                "partial_interval_target_error_rad": (None if target is None or executed == 10 else float(observation["joint_position"][joint])-target),
                                "requested_torque": requested, "raw_pd_torque_nm": raw_pd,
                                "pd_gains": None if kind != "tuned_pd" else {"kp":pd_kp,"kd":pd_kd},
                                "observation_before": previous,
                                "observation_after": observation, "predicted_next_qv": predicted,
                                "model_update": update, "diagnostics": stepped.diagnostics,
                                "planner_decision": None if decision is None else decision.to_dict(),
                                "qpos": env.data.qpos, "qvel": env.data.qvel,
                            }), allow_nan=False)+"\n"
                            try:
                                trace.write(row)
                            except BaseException as exc:
                                trace_failure = exc
                                raise
                            previous_torque = float(requested[joint])
                            if stepped.terminated or study_reason is not None:
                                break
                        if env_before != env.parameter_fingerprint():
                            raise RuntimeError("physical parameters changed")
                        if not is_calibration and before_models != fingerprints(models):
                            raise RuntimeError("evaluation changed a model")
                        if not is_calibration and before_views != {name:view.integration_fingerprint() for name,view in views.items()}:
                            raise RuntimeError("evaluation changed a frozen integration view")
                    except BaseException as exc:
                        error = {"type": type(exc).__name__, "message": str(exc)}
                        try:
                            trace.write(json.dumps(_archive_record({"trial_id": f"seed{seed}_{kind}", "phase": phase,
                                "seed": seed, "kind": kind, "step_index": index,
                                "shared_transition_id": None if index is None else f"seed{seed}_{kind}:{index}",
                                "integration": integration, "calibration_dose": episode["calibration_dose"],
                                "calibration_schedule": schedule, "study_abort": study_reason,
                                "collector_exception": error, "observation_before": previous,
                                "requested_torque": requested, "raw_pd_torque_nm": raw_pd,
                                "pd_gains": None if kind != "tuned_pd" else {"kp":pd_kp,"kd":pd_kd},
                                "predicted_next_qv": predicted, "model_update": update,
                                "target_q": target, "planner_decision": None if decision is None else decision.to_dict(),
                                "partial_model_snapshots": {name:model.snapshot() for name,model in calibrators.items()} if is_calibration else {},
                                "unreturned_physics_steps": unreturned_physics_steps,
                                "failed_planner_attempts": failed_planner_attempts,
                                **_exception_snapshot(env)}), allow_nan=False)+"\n")
                        except BaseException as write_exc:
                            trace_failure = trace_failure or write_exc
                            episode["exception_trace_write_error"] = {
                                "type": type(write_exc).__name__, "message": str(write_exc)}
                        if isinstance(exc, (KeyboardInterrupt, SystemExit, OSError)) or trace_failure is not None:
                            fatal = exc
                    finally:
                        # Save partial parameters after any successful update,
                        # including a later trace write failure or interruption.
                        if is_calibration:
                            for structure in (model_structure,):
                                name = f"{schedule}_{structure}"
                                if name in models:
                                    models[name] = models[name].clone_frozen()
                                    result_seed["learned_models"][name] = models[name].snapshot()
                            result_seed["calibration_updates"] = sum(m.update_count for n,m in models.items() if n != "nominal")
                            calibration_complete[schedule] = (error is None and env is not None
                                                          and env.step_id == 100+duration and not env.terminated and study_reason is None)
                            result_seed["calibration_completed"] = dict(calibration_complete)
                            result_seed["calibration_models"][schedule] = {n: models[f"{schedule}_{n}"].snapshot() for n in (model_structure,) if f"{schedule}_{n}" in models}
                            if calibration_complete[schedule]:
                                for structure in (model_structure,):
                                    name = f"{schedule}_{structure}"
                                    views["learned_mpc"] = FrozenIntegrationModel(models[name], integration)
                            result_seed["integration_models"] = {name:view.snapshot() for name,view in views.items()}
                        terminated = env is not None and (env.terminated or study_reason is not None)
                        completed = error is None and env is not None and env.step_id == 100+duration and not terminated
                        status = "exception" if error else ("terminated" if terminated else "completed")
                        # A stop latch keeps its original reason even if an
                        # additional archive error follows the stopped step.
                        reason = env.reason if env is not None and env.terminated else (study_reason if study_reason is not None else error)
                        episode.update(_archive_record({
                            "control_calls_attempted": calls, "control_steps": 0 if env is None else env.step_id,
                            "physics_steps": 0 if env is None else env.physics_steps, "phase_budgets": phase_budget,
                            "status": status, "reason": reason, "study_abort": study_reason, "collector_exception": error,
                            "environment_terminated": None if env is None else bool(env.terminated),
                            "environment_stop_reason": None if env is None else env.reason,
                            "unreturned_physics_steps": unreturned_physics_steps,
                            "risk_telemetry_complete": error is None and unreturned_physics_steps == 0 and trace_failure is None,
                            "environment_fingerprint_before": env_before,
                            "environment_fingerprint_after": None if env is None else env.parameter_fingerprint()}))
                        result_seed["evaluations"][kind] = {
                            "tracking_rmse_rad": None if not q_errors else float(np.sqrt(np.mean(np.square(q_errors)))),
                            "velocity_prediction_rmse": {n: None if not errors else float(np.sqrt(np.mean(np.square(errors)))) for n,errors in predictions_v.items()},
                            "position_prediction_rmse": {n: None if not errors else float(np.sqrt(np.mean(np.square(errors)))) for n,errors in predictions_q.items()},
                            "control_effort": effort, "saturated_control_steps": saturated,
                            "phase_effort": phase_effort,
                            "phase_actual_effort_substeps": actual_effort_substeps,
                            "phase_actual_effort_complete": {name:actual_effort_substeps[name] == phase_budget[name]["physics_steps"] for name in phase_effort},
                            "actual_effort_complete": actual_control_effort_substeps == phase_budget["control"]["physics_steps"],
                            "actual_effort_is_lower_bound": actual_control_effort_substeps < phase_budget["control"]["physics_steps"],
                            "actual_control_effort_substeps": actual_control_effort_substeps,
                            "missing_control_effort_substeps": phase_budget["control"]["physics_steps"]-actual_control_effort_substeps,
                            "planner_fallbacks": fallbacks, "mathematical_prediction_calls": mathematical_calls,
                            "mathematical_prediction_calls_complete": failed_planner_attempts == 0,
                            "mathematical_prediction_calls_is_lower_bound": failed_planner_attempts > 0,
                            "failed_planner_attempts": failed_planner_attempts,
                            "metric_control_step_count": len(q_errors),
                            "metric_prediction_step_count": {n:len(errors) for n,errors in predictions_v.items()},
                            "partial_interval_target_errors_rad": partial_interval_target_errors,
                            "partial_interval_target_error_count": len(partial_interval_target_errors),
                            "controller_seconds_p95": None if not action_times else float(np.quantile(action_times,.95)),
                            "controller_seconds_total": sum(action_times), "planner_attempt_count": len(action_times),
                            "planner_decision_count": len(action_times)-failed_planner_attempts,
                            "controller_latency_scope": "MPC selection timings; PD invocation time separately reported",
                            "pd_seconds_total": sum(pd_times),
                            "pd_seconds_p95": None if not pd_times else float(np.quantile(pd_times,.95)),
                            "pd_calls_attempted": len(pd_times), "failed_pd_attempts": failed_pd_attempts,
                            "pd_calls_successful": len(pd_times)-failed_pd_attempts,
                            "controller_spec": ({"method":"tuned_pd", "kp":pd_kp,"kd":pd_kd,
                                                 "body_model_input":False,"permission_nm":.5}
                                                if kind == "tuned_pd" else ({"method":"zero_torque"}
                                                                           if kind == "zero_torque" else None)),
                            "completed": completed, "status": status, "reason": reason, "study_abort": study_reason,
                            "environment_terminated": None if env is None else bool(env.terminated),
                            "environment_stop_reason": None if env is None else env.reason,
                            "models_before": before_models, "models_after": fingerprints(models),
                            "integration_models_before": before_views,
                            "integration_models_after": {name:view.integration_fingerprint() for name,view in views.items()},
                            "planner_spec": None if planner is None else {**planner.spec(),
                                "integration": views[kind].integration_spec(),
                                "integration_fingerprint": views[kind].integration_fingerprint()},
                        }
                        try:
                            checkpoint()
                        except BaseException as save_exc:
                            if fatal is None:
                                fatal = save_exc
                            metadata["checkpoint_exception"] = {
                                "type": type(save_exc).__name__, "message": str(save_exc)}
                    if fatal is not None:
                        raise fatal
        metadata["complete"] = True
        metadata["archive_status"] = "complete"
    except BaseException as exc:
        fatal = fatal or exc
        metadata.update(complete=False, archive_status="interrupted" if isinstance(exc, (KeyboardInterrupt, SystemExit)) else "failed",
                        collector_exception={"type": type(exc).__name__, "message": str(exc)})
        raise
    finally:
        for episode in episodes:
            if episode["status"] == "planned":
                block(episode, {"type": "ArchiveAborted", "message": "run interrupted before planned episode"})
        metadata["all_trials_successful"] = all(e["status"] == "completed" for e in episodes)
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
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--protocol", required=True, type=Path)
    parser.add_argument("--suite", required=True, choices=tuple(SUITES))
    args = parser.parse_args()
    if FROZEN_FINAL_SCHEDULE is None:
        parser.error("Final schedule has not been frozen; draft cannot execute")
    result = run_validation(args.output, suite=args.suite,
                            calibration_schedule=FROZEN_FINAL_SCHEDULE,
                            protocol_path=args.protocol)
    keys=("source_commit", "source_dirty", "complete", "all_trials_successful",
          "control_calls_attempted", "control_steps", "physics_steps", "model_updates", "wall_seconds", "cpu_seconds")
    print(json.dumps({k:result[k] for k in keys}, indent=2))


if __name__ == "__main__":
    main()
