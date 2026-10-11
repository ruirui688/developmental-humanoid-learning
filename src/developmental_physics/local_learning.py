"""Small causal RLS body-model experiment, followed by frozen physical evaluations."""

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
from .local_model import LocalBodyModel, FixedLocalMPC
from .probes import direction_record


def run_learning(output: Path, pose: str, joint: int, seeds: list[int], *,
                 split="development", protocol_path: Path | None = None):
    if pose not in POSES or type(joint) is not int or not 0 <= joint < 8:
        raise ValueError("known pose and joint required")
    if not seeds or len(set(seeds)) != len(seeds) or any(type(s) is not int or s < 0 for s in seeds):
        raise ValueError("unique nonnegative seeds required")
    output = Path(output)
    if output.exists():
        raise FileExistsError(output)
    root = Path(__file__).resolve().parents[2]
    sources = [*sorted(Path(__file__).parent.glob("*.py")), MODEL_PATH, root / "pyproject.toml"]
    if protocol_path is not None:
        protocol_path = protocol_path.resolve()
        if not protocol_path.is_file() or not protocol_path.is_relative_to(root):
            raise ValueError("repository protocol required")
        sources.append(protocol_path)
    source_bytes = {p.relative_to(root).as_posix(): p.read_bytes() for p in sources}
    metadata = {
        "schema_version": 1, "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "purpose": "CPU local body learning and frozen causal prediction/control evaluation",
        "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
        "source_status": subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=all"], cwd=root, text=True),
        "source_sha256": {n: hashlib.sha256(b).hexdigest() for n,b in source_bytes.items()},
        "platform": platform.platform(), "python_executable": sys.executable, "python_version": sys.version,
        "dependencies": dict(sorted((d.metadata["Name"], d.version) for d in importlib.metadata.distributions())),
        "gpu": None, "backend": "MuJoCo CPU", "mujoco_version": mujoco.__version__,
        "environment_config": asdict(ExplorationConfig()),
        "pose": pose, "joint_index": joint, "seeds": seeds, "split": split,
        "prefix_steps": 100, "calibration_steps": 300, "prediction_steps": 100, "control_steps_per_trial": 200,
        "teacher_calls": 0, "external_demonstration_samples": 0, "policy_parameter_updates": 0,
        "model_input": "current encoder position/velocity and requested torque known before integration",
        "model_label": "next encoder velocity; no hidden mass, contact or future actual torque features",
        "fixed_pd": {"kp": 4., "kd": .2, "torque_limit_nm": .5},
        "protocol": None if protocol_path is None else {"path": protocol_path.relative_to(root).as_posix(), "sha256": _hash(protocol_path)},
        "claim_boundary": "Local single-joint learning only; no rolling, standing, walking or real robot result.",
        "complete": False,
    }
    metadata["source_dirty"] = bool(metadata["source_status"])
    output.mkdir(parents=True)
    with zipfile.ZipFile(output/"source_snapshot.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in source_bytes.items():
            archive.writestr(name, data)
    episodes, seed_results = [], []
    started = time.perf_counter()

    def checkpoint():
        metadata.update(control_calls_attempted=sum(e["control_calls_attempted"] for e in episodes),
                        control_steps=sum(e["control_steps"] for e in episodes),
                        physics_steps=sum(e["physics_steps"] for e in episodes),
                        model_updates=sum(s["calibration_updates"] for s in seed_results),
                        exception_trials=sum(e["status"] == "exception" for e in episodes),
                        terminated_trials=sum(e["status"] == "terminated" for e in episodes),
                        wall_seconds=time.perf_counter()-started)
        _write_json(output/"metadata.json", metadata)
        _write_json(output/"episodes.json", episodes)
        _write_json(output/"seed_results.json", seed_results)

    checkpoint()
    try:
        with gzip.open(output/"trace.jsonl.gz", "wt", encoding="utf-8") as trace:
            for seed in seeds:
                reset_seed = int(np.random.SeedSequence(seed).spawn(2)[0].generate_state(1)[0])
                learned = nominal = None
                direction = None
                reference = None
                calibr_updates = 0
                result_seed = {"seed": seed, "reset_seed": reset_seed, "evaluations": {}, "calibration_updates": 0}
                seed_results.append(result_seed)
                for kind in ("calibration", "prediction", "frozen_mpc", "learned_mpc", "fixed_pd", "zero_torque"):
                    env = None
                    observation = previous = None
                    calls = 0
                    phase = "prefix"
                    error = None
                    env_before = None
                    before_models = None
                    q_errors, predictions = [], {"frozen": [], "learned": []}
                    action_times = []
                    phase_budget = {p: dict(control_calls_attempted=0, control_steps=0, physics_steps=0)
                                    for p in ("prefix", "calibration", "prediction", "control")}
                    try:
                        env = GroundBodyEnv()
                        observation = env.reset(seed=reset_seed, pose=pose)
                        env_before = env.parameter_fingerprint()
                        duration = 300 if kind == "calibration" else (100 if kind == "prediction" else 200)
                        planner = None
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
                                    learned = LocalBodyModel(qref=q0)
                                    nominal = learned.clone_frozen()
                                    result_seed.update(reference_q=q0, direction=direction, selection_record=record,
                                                       initial_model=nominal.snapshot())
                                else:
                                    assert q0 == reference and record["direction"] == direction
                                    before_models = (nominal.parameter_fingerprint(), learned.parameter_fingerprint())
                                    if kind.endswith("mpc"):
                                        model = nominal if kind == "frozen_mpc" else learned
                                        planner = FixedLocalMPC(model, env.model.joint(env.joint_names[joint]).range)
                            q, v = (float(observation[key][joint]) for key in ("joint_position", "joint_velocity"))
                            if index >= 100:
                                active = index-100
                                if kind == "calibration":
                                    slot = active % 30
                                    requested[joint] = direction*(.5 if slot < 5 else (-.5 if 15 <= slot < 20 else 0.))
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
                                        decision = planner.select(q, v, target, previous_torque=previous_torque)
                                        requested[joint] = decision.torque
                                        action_times.append(time.perf_counter()-timer)
                                    elif kind == "fixed_pd":
                                        requested[joint] = np.clip(4*(target-q)-.2*v, -.5, .5)
                                predicted = {"frozen": nominal.predict(q,v,requested[joint]),
                                             "learned": learned.predict(q,v,requested[joint])}
                            previous = observation
                            calls += 1
                            old_control, old_physics = env.step_id, env.physics_steps
                            phase_budget[phase]["control_calls_attempted"] += 1
                            try:
                                stepped = env.step(requested)
                            finally:
                                phase_budget[phase]["control_steps"] += env.step_id-old_control
                                phase_budget[phase]["physics_steps"] += env.physics_steps-old_physics
                            observation = stepped.observation
                            next_v = float(observation["joint_velocity"][joint])
                            if index >= 100:
                                if kind == "calibration":
                                    update = learned.update(q, v, float(requested[joint]), next_v)
                                    update["coefficients_after"] = learned.coefficients.tolist()
                                    update["covariance_after"] = learned.covariance.tolist()
                                    calibr_updates += 1
                                    result_seed["calibration_updates"] = calibr_updates
                                for name, prediction in predicted.items():
                                    predictions[name].append(next_v-float(prediction[1]))
                                if target is not None:
                                    q_errors.append(float(observation["joint_position"][joint])-target)
                            trace.write(json.dumps(_archive_record({
                                "trial_id": f"seed{seed}_{kind}", "seed": seed, "kind": kind,
                                "step_index": index, "phase": phase, "target_q": target,
                                "requested_torque": requested, "observation_before": previous,
                                "observation_after": observation, "predicted_next_qv": predicted,
                                "model_update": update, "diagnostics": stepped.diagnostics,
                                "planner_decision": None if decision is None else decision.to_dict(),
                                "qpos": env.data.qpos, "qvel": env.data.qvel,
                            }), allow_nan=False)+"\n")
                            previous_torque = float(requested[joint])
                            if stepped.terminated:
                                break
                        if env_before != env.parameter_fingerprint():
                            raise RuntimeError("physical parameters changed")
                        if kind == "calibration":
                            learned = learned.clone_frozen()
                            result_seed["learned_model"] = learned.snapshot()
                        elif before_models != (nominal.parameter_fingerprint(), learned.parameter_fingerprint()):
                            raise RuntimeError("evaluation changed a model")
                        result_seed["evaluations"][kind] = {
                            "tracking_rmse_rad": None if not q_errors else float(np.sqrt(np.mean(np.square(q_errors)))),
                            "velocity_prediction_rmse": {n: None if not errors else float(np.sqrt(np.mean(np.square(errors)))) for n,errors in predictions.items()},
                            "controller_seconds_p95": None if not action_times else float(np.quantile(action_times,.95)),
                            "completed": env.step_id == 100+duration and not env.terminated,
                            "models_before": before_models, "models_after": [nominal.parameter_fingerprint(), learned.parameter_fingerprint()],
                            "planner_spec": None if planner is None else planner.spec(),
                        }
                    except BaseException as exc:
                        error = {"type": type(exc).__name__, "message": str(exc)}
                        trace.write(json.dumps(_archive_record({"trial_id": f"seed{seed}_{kind}", "phase": phase,
                            "collector_exception": error, "observation_before": previous, **_exception_snapshot(env)}), allow_nan=False)+"\n")
                        raise
                    finally:
                        episodes.append(_archive_record({"seed": seed, "kind": kind,
                            "control_calls_attempted": calls, "control_steps": 0 if env is None else env.step_id,
                            "physics_steps": 0 if env is None else env.physics_steps, "phase_budgets": phase_budget,
                            "status": "exception" if error else ("terminated" if env.terminated else "completed"),
                            "reason": error or (None if env is None else env.reason),
                            "environment_fingerprint_before": env_before,
                            "environment_fingerprint_after": None if env is None else env.parameter_fingerprint()}))
                        checkpoint()
                    if env.terminated:
                        raise RuntimeError("predeclared trial stopped; preserve and do not replace")
        metadata["complete"] = True
    finally:
        checkpoint()
        _write_json(output/"manifest.json", {p.name: _hash(p) for p in sorted(output.iterdir())
                    if p.is_file() and p.name != "manifest.json"})
    return metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--pose", required=True, choices=POSES)
    parser.add_argument("--joint", required=True, type=int)
    parser.add_argument("--seeds", type=int, nargs="+", default=[0,1,2])
    parser.add_argument("--split", choices=["development", "holdout"], default="development")
    parser.add_argument("--protocol", type=Path)
    args = parser.parse_args()
    print(json.dumps(run_learning(args.output,args.pose,args.joint,args.seeds,
                                 split=args.split,protocol_path=args.protocol), indent=2))


if __name__ == "__main__":
    main()
