"""C2-B: calibration dose coverage crossed with linear/hinge velocity models.

Development only, two 300-step calibrations fitting both structures per seed. All evaluations
freeze model parameters, integration modes, MPC settings and actuator permission.
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


FROZEN_INTEGRATION = "endpoint_euler"


def phase_budget_names():
    return ("prefix", "calibration", "prediction", "control")


def run_ablation(output: Path, seeds: list[int], *, integration: str,
                 pose="supine", joint=0, split="development", protocol_path: Path):
    if integration != FROZEN_INTEGRATION:
        raise ValueError("C2-B frozen integration must be endpoint_euler")
    if pose != "supine" or type(joint) is not int or joint != 0:
        raise ValueError("C2-B requires supine / left_shoulder joint 0")
    if split != "development":
        raise ValueError("C2-B accepts development only; do not access held-out seeds")
    if seeds != [0, 1, 2] or any(type(seed) is not int for seed in seeds):
        raise ValueError("C2-B development requires the frozen seeds 0/1/2 in order")
    calibration_amplitudes = {
        "old": [.125, .25, .5, .125, .25, .5, .125, .25, .5, .125],
        "new": [.125, .25, .5, .375, .25, .5, .375, .25, .5, .375],
    }
    prediction_amplitudes = {"low": [.25]*5, "full": [.125, .25, .375, .5, .375]}
    output = Path(output)
    if output.exists():
        raise FileExistsError(output)
    root = next(p for p in Path(__file__).resolve().parents
                if (p/"pyproject.toml").is_file() and (p/"src/developmental_physics").is_dir())
    sources = [*sorted((root / "src/developmental_physics").glob("*.py")),
               Path(__file__), root / "src/developmental_physics/local_integration.py", MODEL_PATH, root / "pyproject.toml"]
    protocol_path = Path(protocol_path).resolve()
    if not protocol_path.is_file() or not protocol_path.is_relative_to(root):
        raise ValueError("repository protocol required")
    sources.append(protocol_path)
    source_bytes = {p.relative_to(root).as_posix(): p.read_bytes() for p in sources}
    metadata = {
        "schema_version": 1, "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "purpose": "C2-B frozen 2x2 calibration-dose / velocity-model-structure ablation",
        "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
        "source_status": subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=all"], cwd=root, text=True),
        "source_sha256": {n: hashlib.sha256(b).hexdigest() for n,b in source_bytes.items()},
        "platform": platform.platform(), "python_executable": sys.executable, "python_version": sys.version,
        "dependencies": dict(sorted((d.metadata["Name"], d.version) for d in importlib.metadata.distributions())),
        "gpu": None, "backend": "MuJoCo CPU", "mujoco_version": mujoco.__version__,
        "environment_config": asdict(ExplorationConfig()),
        "pose": pose, "joint_index": joint, "seeds": seeds, "split": split,
        "structures": ["linear4", "hinge5"], "integration": integration,
        "calibration_block_amplitudes_nm": calibration_amplitudes,
        "prediction_block_amplitudes_nm": prediction_amplitudes,
        "prefix_steps": 100, "calibration_steps": 300, "prediction_steps": 100, "control_steps_per_trial": 200,
        "teacher_calls": 0, "external_demonstration_samples": 0, "policy_parameter_updates": 0,
        "model_input": "current encoder position/velocity and requested torque known before integration",
        "model_label": "next encoder velocity; no hidden mass, contact or future actual torque features",
        "factorial": {"calibration_dose": ["old", "new"], "model_structure": ["linear4", "hinge5"]},
        "nominal_model": "shared frozen linear4; hinge5 initial zero-hinge predictions are equivalent",
        "rls_preupdate_position_diagnostic": "endpoint_euler; unchanged raw model_update diagnostic",
        "evaluation_prediction_integration": integration,
        "fixed_mpc_config": "Existing FixedLocalMPC defaults unchanged; full spec archived per evaluation",
        "protocol": {"path": protocol_path.relative_to(root).as_posix(), "sha256": _hash(protocol_path)},
        "claim_boundary": "Local single-joint learning only; no rolling, standing, walking or real robot result.",
        "completion_definition": "Every planned episode has a recorded outcome; no scientific benefit gate is implied.",
        "trial_success_definition": "Episode completed without exception or stop; not a model/control benefit criterion.",
        "complete": False,
    }
    metadata["source_dirty"] = bool(metadata["source_status"])
    output.mkdir(parents=True)
    with zipfile.ZipFile(output/"source_snapshot.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in source_bytes.items():
            archive.writestr(name, data)
    kinds = ("calibration_old", "calibration_new", "prediction_low", "prediction_full",
             "old_linear4_mpc", "old_hinge5_mpc", "new_linear4_mpc", "new_hinge5_mpc", "nominal_mpc")
    planned = [{"trial_id": f"seed{seed}_{kind}", "seed": seed, "kind": kind,
                "model_scope": "nominal" if kind == "nominal_mpc" else ("learned" if kind.endswith("mpc") else "shared"),
                "calibration_dose": (kind.split("_")[1] if kind.startswith("calibration_") else
                                     (kind.split("_")[0] if kind.endswith("mpc") and kind != "nominal_mpc" else None)),
                "model_structure": kind.split("_")[1] if kind.endswith("mpc") and kind != "nominal_mpc" else ("linear4" if kind == "nominal_mpc" else None),
                "integration": integration,
                "maximum_control_steps": 100 + (300 if kind.startswith("calibration_") else
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
                        wall_seconds=time.perf_counter()-started)
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
                calibration_complete = {"old": False, "new": False}
                result_seed = {"seed": seed, "reset_seed": reset_seed, "evaluations": {},
                               "calibration_updates": 0, "calibration_completed": dict(calibration_complete),
                               "calibration_models": {}, "initial_models": {}, "learned_models": {}}
                seed_results.append(result_seed)
                for kind in kinds:
                    episode = by_id[f"seed{seed}_{kind}"]
                    is_calibration = kind.startswith("calibration_")
                    is_prediction = kind.startswith("prediction_")
                    dose = kind.split("_")[1] if is_calibration else (kind.split("_")[0] if kind.endswith("mpc") and kind != "nominal_mpc" else None)
                    dependencies = (["old", "new"] if is_prediction else ([dose] if kind.endswith("mpc") and dose else []))
                    missing = [d for d in dependencies if not calibration_complete[d]]
                    if missing:
                        reason = {"type": "DependencyBlocked", "message": "required calibration did not complete",
                                  "dependencies": [f"seed{seed}_calibration_{d}" for d in missing]}
                        block(episode, reason)
                        result_seed["evaluations"][kind] = {"completed": False, "status": "blocked", "reason": reason}
                        checkpoint()
                        continue
                    env = None
                    observation = previous = requested = None
                    calls = 0
                    phase = "prefix"
                    error = None
                    env_before = None
                    before_models = None if is_calibration else fingerprints(models)
                    before_views = {name: view.integration_fingerprint() for name,view in views.items()}
                    if is_calibration:
                        calibrators = {}
                    index = target = decision = update = None
                    predicted = {}
                    q_errors = []
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
                                    calibrators = {"linear4": LocalBodyModel(qref=q0), "hinge5": HingeBodyModel(qref=q0)}
                                    for structure, calibrator in calibrators.items():
                                        name = f"{dose}_{structure}"
                                        models[name] = calibrator
                                        result_seed["initial_models"][name] = calibrator.clone_frozen().snapshot()
                                    predictions_v = {n: [] for n in ("linear4", "hinge5")}
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
                                    slot = active % 30
                                    amplitude = calibration_amplitudes[dose][active//30]
                                    requested[joint] = direction*(amplitude if slot < 5 else (-amplitude if 15 <= slot < 20 else 0.))
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
                                if is_calibration:
                                    predicted = {name: model.predict(q,v,requested[joint]) for name,model in calibrators.items()}
                                    if integration == "trapezoid":
                                        predicted = {name:(q + .02*(v + pred[1])/2, pred[1]) for name,pred in predicted.items()}
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
                                        item["model_id"] = f"{dose}_{structure}"
                                        item["shared_transition_id"] = f"seed{seed}_{kind}:{index}"
                                        update[structure] = item
                                        result_seed["calibration_updates"] = sum(m.update_count for n,m in models.items() if n != "nominal")
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
                                "step_index": index, "phase": phase, "target_q": target,
                                "requested_torque": requested, "observation_before": previous,
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
                            if stepped.terminated:
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
                                "collector_exception": error, "observation_before": previous, "requested_torque": requested,
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
                            for structure in ("linear4", "hinge5"):
                                name = f"{dose}_{structure}"
                                if name in models:
                                    models[name] = models[name].clone_frozen()
                                    result_seed["learned_models"][name] = models[name].snapshot()
                            result_seed["calibration_updates"] = sum(m.update_count for n,m in models.items() if n != "nominal")
                            calibration_complete[dose] = (error is None and env is not None
                                                          and env.step_id == 100+duration and not env.terminated)
                            result_seed["calibration_completed"] = dict(calibration_complete)
                            result_seed["calibration_models"][dose] = {n: models[f"{dose}_{n}"].snapshot() for n in ("linear4", "hinge5") if f"{dose}_{n}" in models}
                            if calibration_complete[dose]:
                                for structure in ("linear4", "hinge5"):
                                    name = f"{dose}_{structure}"
                                    views[f"{name}_mpc"] = FrozenIntegrationModel(models[name], integration)
                            result_seed["integration_models"] = {name:view.snapshot() for name,view in views.items()}
                        terminated = env is not None and env.terminated
                        completed = error is None and env is not None and env.step_id == 100+duration and not terminated
                        status = "exception" if error else ("terminated" if terminated else "completed")
                        # A stop latch keeps its original reason even if an
                        # additional archive error follows the stopped step.
                        reason = env.reason if terminated else error
                        episode.update(_archive_record({
                            "control_calls_attempted": calls, "control_steps": 0 if env is None else env.step_id,
                            "physics_steps": 0 if env is None else env.physics_steps, "phase_budgets": phase_budget,
                            "status": status, "reason": reason, "collector_exception": error,
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
                            "controller_seconds_p95": None if not action_times else float(np.quantile(action_times,.95)),
                            "controller_seconds_total": sum(action_times), "planner_attempt_count": len(action_times),
                            "planner_decision_count": len(action_times)-failed_planner_attempts,
                            "completed": completed, "status": status, "reason": reason,
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
    parser.add_argument("--integration", required=True, choices=(FROZEN_INTEGRATION,))
    args = parser.parse_args()
    result = run_ablation(args.output, [0, 1, 2], integration=args.integration, protocol_path=args.protocol)
    keys=("source_commit", "source_dirty", "complete", "all_trials_successful",
          "control_calls_attempted", "control_steps", "physics_steps", "model_updates", "wall_seconds")
    print(json.dumps({k:result[k] for k in keys}, indent=2))


if __name__ == "__main__":
    main()
