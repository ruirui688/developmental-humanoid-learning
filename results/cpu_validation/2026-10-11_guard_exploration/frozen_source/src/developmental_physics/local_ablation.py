"""C2-A: unchanged velocity models crossed with two position integration rules.

Development only, one shared 300-update calibration per seed. All evaluations
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
from .local_model import HingeBodyModel, FixedLocalMPC
from .local_integration import FrozenIntegrationModel
from .probes import direction_record


def run_ablation(output: Path, seeds: list[int], *,
                 pose="supine", joint=0, split="development", protocol_path: Path):
    if pose != "supine" or type(joint) is not int or joint != 0:
        raise ValueError("C2-A requires supine / left_shoulder joint 0")
    if split != "development":
        raise ValueError("C2-A accepts development only; do not access held-out seeds")
    if seeds != [0, 1, 2] or any(type(seed) is not int for seed in seeds):
        raise ValueError("C2-A development requires the frozen seeds 0/1/2 in order")
    calibration_amplitudes = [.125, .25, .5, .125, .25, .5, .125, .25, .5, .125]
    output = Path(output)
    if output.exists():
        raise FileExistsError(output)
    root = Path(__file__).resolve().parents[2]
    sources = [*sorted((root / "src/developmental_physics").glob("*.py")),
               Path(__file__), Path(__file__).with_name("local_integration.py"), MODEL_PATH, root / "pyproject.toml"]
    protocol_path = Path(protocol_path).resolve()
    if not protocol_path.is_file() or not protocol_path.is_relative_to(root):
        raise ValueError("repository protocol required")
    sources.append(protocol_path)
    source_bytes = {p.relative_to(root).as_posix(): p.read_bytes() for p in sources}
    metadata = {
        "schema_version": 1, "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "purpose": "C2-A frozen 2x2 velocity-model / position-integration ablation",
        "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
        "source_status": subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=all"], cwd=root, text=True),
        "source_sha256": {n: hashlib.sha256(b).hexdigest() for n,b in source_bytes.items()},
        "platform": platform.platform(), "python_executable": sys.executable, "python_version": sys.version,
        "dependencies": dict(sorted((d.metadata["Name"], d.version) for d in importlib.metadata.distributions())),
        "gpu": None, "backend": "MuJoCo CPU", "mujoco_version": mujoco.__version__,
        "environment_config": asdict(ExplorationConfig()),
        "pose": pose, "joint_index": joint, "seeds": seeds, "split": split,
        "variant": "hinge", "integrations": ["endpoint_euler", "trapezoid"], "calibration_block_amplitudes_nm": calibration_amplitudes,
        "prefix_steps": 100, "calibration_steps": 300, "prediction_steps": 100, "control_steps_per_trial": 200,
        "teacher_calls": 0, "external_demonstration_samples": 0, "policy_parameter_updates": 0,
        "model_input": "current encoder position/velocity and requested torque known before integration",
        "model_label": "next encoder velocity; no hidden mass, contact or future actual torque features",
        "factorial": {"model": ["frozen", "learned"], "position_integration": ["endpoint_euler", "trapezoid"]},
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
    kinds = ("calibration", "prediction", "frozen_euler_mpc", "learned_euler_mpc",
             "frozen_trapezoid_mpc", "learned_trapezoid_mpc")
    planned = [{"trial_id": f"seed{seed}_{kind}", "seed": seed, "kind": kind,
                "model_scope": "frozen" if kind.startswith("frozen") else ("learned" if kind.startswith("learned") else "shared"),
                "integration": "trapezoid" if "trapezoid" in kind else ("endpoint_euler" if "euler" in kind else None),
                "maximum_control_steps": 100 + (300 if kind == "calibration" else
                                                (100 if kind == "prediction" else 200))}
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

    def fingerprints(nominal, learned):
        return [None if model is None else model.parameter_fingerprint()
                for model in (nominal, learned)]

    def block(episode, reason):
        episode.update(status="blocked", reason=reason)

    fatal = None
    try:
        checkpoint()
        with gzip.open(output/"trace.jsonl.gz", "wt", encoding="utf-8") as trace:
            for seed in seeds:
                reset_seed = int(np.random.SeedSequence(seed).spawn(2)[0].generate_state(1)[0])
                learned = nominal = None
                views = {}
                direction = None
                reference = None
                calibration_complete = False
                result_seed = {"seed": seed, "reset_seed": reset_seed, "evaluations": {},
                               "calibration_updates": 0, "calibration_completed": False,
                               "initial_model": None, "learned_model": None}
                seed_results.append(result_seed)
                for kind in kinds:
                    episode = by_id[f"seed{seed}_{kind}"]
                    if kind != "calibration" and not calibration_complete:
                        reason = {"type": "DependencyBlocked", "message": "calibration did not complete",
                                  "dependency": f"seed{seed}_calibration"}
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
                    before_models = None if kind == "calibration" else fingerprints(nominal, learned)
                    before_views = {name: view.integration_fingerprint() for name,view in views.items()}
                    q_errors = []
                    predictions_v = {n: [] for n in (views or {"frozen": None, "learned": None})}
                    predictions_q = {n: [] for n in predictions_v}
                    effort = {"requested_absolute_nm_s": 0., "requested_squared_nm2_s": 0.,
                              "actual_absolute_nm_s": 0., "actual_squared_nm2_s": 0.}
                    saturated = fallbacks = mathematical_calls = 0
                    failed_planner_attempts = 0
                    unreturned_physics_steps = actual_control_effort_substeps = 0
                    action_times = []
                    phase_budget = episode["phase_budgets"]
                    planner = None
                    trace_failure = None
                    duration = 300 if kind == "calibration" else (100 if kind == "prediction" else 200)
                    try:
                        env = GroundBodyEnv()
                        observation = env.reset(seed=reset_seed, pose=pose)
                        env_before = env.parameter_fingerprint()
                        previous_torque = 0.
                        for index in range(100+duration):
                            phase = "prefix" if index < 100 else (kind if kind in ("calibration", "prediction") else "control")
                            requested = np.zeros(8)
                            target = None
                            predicted = {}
                            update = None
                            decision = None
                            if index == 100:
                                record = direction_record(joint, observation["joint_position"],
                                    [env.model.joint(n).range for n in env.joint_names])
                                q0 = float(observation["joint_position"][joint])
                                if kind == "calibration":
                                    reference, direction = q0, record["direction"]
                                    learned = HingeBodyModel(qref=q0)
                                    nominal = learned.clone_frozen()
                                    result_seed.update(reference_q=q0, direction=direction, selection_record=record,
                                                       initial_model=nominal.snapshot())
                                else:
                                    assert q0 == reference and record["direction"] == direction
                                    if kind.endswith("mpc"):
                                        model = views[kind]
                                        planner = FixedLocalMPC(model, env.model.joint(env.joint_names[joint]).range)
                            q, v = (float(observation[key][joint]) for key in ("joint_position", "joint_velocity"))
                            if index >= 100:
                                active = index-100
                                if kind == "calibration":
                                    slot = active % 30
                                    amplitude = calibration_amplitudes[active//30]
                                    requested[joint] = direction*(amplitude if slot < 5 else (-amplitude if 15 <= slot < 20 else 0.))
                                elif kind == "prediction":
                                    slot = active % 20
                                    requested[joint] = direction*(.25 if slot < 7 else (-.25 if 10 <= slot < 17 else 0.))
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
                                if kind == "calibration":
                                    predicted = {"frozen": nominal.predict(q,v,requested[joint]),
                                                 "learned": learned.predict(q,v,requested[joint])}
                                else:
                                    predicted = {name: view.predict(q,v,requested[joint]) for name,view in views.items()}
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
                                if phase == "control":
                                    paid_dt = (env.physics_steps-old_physics)*env.config.physics_dt
                                    effort["requested_absolute_nm_s"] += abs(float(requested[joint]))*paid_dt
                                    effort["requested_squared_nm2_s"] += float(requested[joint])**2*paid_dt
                            observation = stepped.observation
                            if stepped.diagnostics["executed_substeps"] != env.physics_steps-old_physics:
                                raise RuntimeError("returned substep count differs from paid physics cost")
                            next_v = float(observation["joint_velocity"][joint])
                            if index >= 100:
                                if kind == "calibration":
                                    if stepped.diagnostics["executed_substeps"] == 10:
                                        update = learned.update(q, v, float(requested[joint]), next_v)
                                        update["coefficients_after"] = learned.coefficients.tolist()
                                        update["covariance_after"] = learned.covariance.tolist()
                                        result_seed["calibration_updates"] = learned.update_count
                                    else:
                                        update = {"updated": False, "phase": "partial_calibration_interval",
                                                  "executed_substeps": stepped.diagnostics["executed_substeps"],
                                                  "reason": "velocity model requires a complete 20 ms interval",
                                                  "update_count": learned.update_count}
                                for name, prediction in predicted.items():
                                    predictions_v[name].append(next_v-float(prediction[1]))
                                    predictions_q[name].append(float(observation["joint_position"][joint])-float(prediction[0]))
                                if target is not None:
                                    q_errors.append(float(observation["joint_position"][joint])-target)
                                    executed = stepped.diagnostics["executed_substeps"]
                                    realized = np.asarray(stepped.diagnostics["applied_torque_history"], dtype=float)
                                    if executed == 0 and realized.size == 0:
                                        realized = realized.reshape(0, 8)
                                    if realized.shape != (executed, 8):
                                        raise RuntimeError("applied torque history differs from paid substeps")
                                    if not np.isfinite(realized).all() or np.max(np.abs(realized),initial=0.) > .5:
                                        raise RuntimeError("applied torque history violates the shared permission")
                                    effort["actual_absolute_nm_s"] += float(np.sum(np.abs(realized[:,joint])))*env.config.physics_dt
                                    effort["actual_squared_nm2_s"] += float(np.sum(realized[:,joint]**2))*env.config.physics_dt
                                    actual_control_effort_substeps += executed
                                    saturated += int(abs(float(requested[joint])) == .5)
                            row = json.dumps(_archive_record({
                                "trial_id": f"seed{seed}_{kind}", "seed": seed, "kind": kind,
                                "model_scope": episode["model_scope"], "integration": episode["integration"],
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
                        if kind != "calibration" and before_models != fingerprints(nominal, learned):
                            raise RuntimeError("evaluation changed a model")
                        if before_views != {name:view.integration_fingerprint() for name,view in views.items()}:
                            raise RuntimeError("evaluation changed a frozen integration view")
                    except BaseException as exc:
                        error = {"type": type(exc).__name__, "message": str(exc)}
                        try:
                            trace.write(json.dumps(_archive_record({"trial_id": f"seed{seed}_{kind}", "phase": phase,
                                "collector_exception": error, "observation_before": previous, "requested_torque": requested,
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
                        if kind == "calibration":
                            if learned is not None:
                                learned = learned.clone_frozen()
                                result_seed["learned_model"] = learned.snapshot()
                                result_seed["calibration_updates"] = learned.update_count
                            calibration_complete = (error is None and env is not None
                                                    and env.step_id == 100+duration and not env.terminated)
                            result_seed["calibration_completed"] = calibration_complete
                            if calibration_complete:
                                views = {name: FrozenIntegrationModel(nominal if name.startswith("frozen") else learned,
                                         "trapezoid" if "trapezoid" in name else "endpoint_euler")
                                         for name in kinds[2:]}
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
                            "models_before": before_models, "models_after": fingerprints(nominal, learned),
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
    args = parser.parse_args()
    result = run_ablation(args.output, [0, 1, 2], protocol_path=args.protocol)
    keys=("source_commit", "source_dirty", "complete", "all_trials_successful",
          "control_calls_attempted", "control_steps", "physics_steps", "model_updates", "wall_seconds")
    print(json.dumps({k:result[k] for k in keys}, indent=2))


if __name__ == "__main__":
    main()
