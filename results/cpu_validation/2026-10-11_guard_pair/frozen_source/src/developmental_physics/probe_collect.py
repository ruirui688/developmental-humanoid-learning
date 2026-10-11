"""Fixed joint probes with a paid passive prefix and one shared zero reference."""

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
from .probes import FixedJointProbe, ProbeConfig


def collect_probes(output: Path, seeds: list[int], *, split: str = "development",
                   poses=POSES, joints=tuple(range(8)), amplitudes=(.125, .25, .5),
                   prefix_steps=100, pulse_steps=25, recovery_steps=75,
                   protocol_path: Path | None = None):
    if (not seeds or len(set(seeds)) != len(seeds)
            or any(type(s) is not int or s < 0 for s in seeds)):
        raise ValueError("unique nonnegative seeds required")
    if not poses or len(set(poses)) != len(poses) or any(p not in POSES for p in poses):
        raise ValueError("unique known poses required")
    if not joints or len(set(joints)) != len(joints):
        raise ValueError("unique joints required")
    if not amplitudes or len(set(amplitudes)) != len(amplitudes):
        raise ValueError("unique amplitudes required")
    configs = [ProbeConfig(joint_index=None, mode="zero", prefix_steps=prefix_steps,
                          pulse_steps=pulse_steps, recovery_steps=recovery_steps)]
    configs += [ProbeConfig(joint_index=j, amplitude_nm=a, mode="pulse", prefix_steps=prefix_steps,
                            pulse_steps=pulse_steps, recovery_steps=recovery_steps)
                for j in joints for a in amplitudes]
    output = Path(output)
    if output.exists():
        raise FileExistsError(f"archive already exists: {output}")
    root = Path(__file__).resolve().parents[2]
    sources = [*sorted(Path(__file__).parent.glob("*.py")), MODEL_PATH, root / "pyproject.toml"]
    if protocol_path is not None:
        protocol_path = protocol_path.resolve()
        if not protocol_path.is_file() or not protocol_path.is_relative_to(root):
            raise ValueError("protocol must be a repository file")
        sources.append(protocol_path)
    source_bytes = {p.relative_to(root).as_posix(): p.read_bytes() for p in sources}
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    status = subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=all"], cwd=root, text=True)
    total_steps = prefix_steps + pulse_steps + recovery_steps
    env_config = ExplorationConfig()
    metadata = {
        "schema_version": 1, "purpose": "fixed CPU joint probes, no parameter learning",
        "created_at_utc": datetime.now(timezone.utc).isoformat(), "split": split,
        "source_commit": commit, "source_dirty": bool(status), "source_status": status,
        "source_sha256": {n: hashlib.sha256(b).hexdigest() for n, b in source_bytes.items()},
        "asset_sha256": _hash(MODEL_PATH), "platform": platform.platform(),
        "python_version": sys.version, "python_executable": sys.executable,
        "dependencies": dict(sorted((d.metadata["Name"], d.version) for d in importlib.metadata.distributions())),
        "gpu": None, "dynamics_backend": "MuJoCo CPU", "mujoco_version": mujoco.__version__,
        "environment_config": asdict(env_config), "seeds": seeds, "poses": list(poses),
        "joints": list(joints), "amplitudes_nm": list(amplitudes),
        "prefix_steps": prefix_steps, "pulse_steps": pulse_steps, "recovery_steps": recovery_steps,
        "steps_per_trial_limit": total_steps, "expected_trial_count": len(seeds)*len(poses)*len(configs),
        "parameter_updates": {"model": 0, "policy": 0, "gate": 0},
        "teacher_calls": 0, "external_demonstration_samples": 0,
        "protocol": None if protocol_path is None else {"path": protocol_path.relative_to(root).as_posix(), "sha256": _hash(protocol_path)},
        "reference_policy": "One zero trial per pose/seed; reused pairs are dependent, not additional independent samples.",
        "action_inputs": "Encoder at prefix end and public joint ranges; no privileged contact or physics parameters.",
        "complete": False, "archive_status": "running",
    }
    output.mkdir(parents=True)
    with zipfile.ZipFile(output / "source_snapshot.zip", "w", zipfile.ZIP_DEFLATED) as snapshot:
        for name, data in source_bytes.items():
            snapshot.writestr(name, data)
    trials = []
    geometry = []
    started = time.perf_counter()

    def checkpoint():
        for key in ("control_steps", "control_calls_attempted", "physics_steps"):
            metadata[key] = sum(t[key] for t in trials)
        metadata["phase_budgets"] = {phase: {
            key: sum(t["phase_budgets"][phase][key] for t in trials)
            for key in ("control_calls_attempted", "control_steps", "physics_steps")}
            for phase in ("prefix", "probe", "recovery")}
        metadata.update(trial_count=len(trials),
                        terminated_trials=sum(t["terminated"] for t in trials),
                        exception_trials=sum(t["status"] == "exception" for t in trials),
                        wall_seconds=time.perf_counter()-started)
        _write_json(output / "trials.json", trials)
        _write_json(output / "geometry.json", geometry)
        _write_json(output / "metadata.json", _archive_record(metadata))

    checkpoint()
    try:
        with gzip.open(output / "trace.jsonl.gz", "wt", encoding="utf-8") as trace:
            for pose in poses:
                for seed in seeds:
                    reset_seed = int(np.random.SeedSequence(seed).spawn(2)[0].generate_state(1)[0])
                    for cfg in configs:
                        mode = "zero_torque" if cfg.mode == "zero" else "joint_probe"
                        suffix = "zero" if cfg.mode == "zero" else f"joint{cfg.joint_index}_amp{cfg.amplitude_nm:g}"
                        tid = f"{pose}_seed{seed}_{suffix}"
                        env = actor = None
                        observation = requested = previous = None
                        env_before = actor_before = None
                        phase = action_index = None
                        error = None
                        initial_geometry = None
                        budgets = {p: dict(control_calls_attempted=0, control_steps=0, physics_steps=0)
                                   for p in ("prefix", "probe", "recovery")}
                        try:
                            env = GroundBodyEnv(env_config)
                            observation = env.reset(seed=reset_seed, pose=pose)
                            initial_geometry = env.geometry_snapshot()
                            # Joint ranges are public body information, not a learned mapping.
                            ranges = np.array([env.model.joint(n).range for n in env.joint_names])
                            actor = FixedJointProbe(cfg, ranges)
                            env_before, actor_before = env.parameter_fingerprint(), actor.parameter_fingerprint()
                            for index in range(total_steps):
                                phase = actor.phase(index)
                                action_index = actor.action_index(index)
                                requested = actor.act(observation, index)
                                previous = observation
                                old_control, old_physics = env.step_id, env.physics_steps
                                budgets[phase]["control_calls_attempted"] += 1
                                try:
                                    result = env.step(requested)
                                finally:
                                    budgets[phase]["control_steps"] += env.step_id-old_control
                                    budgets[phase]["physics_steps"] += env.physics_steps-old_physics
                                observation = result.observation
                                trace.write(json.dumps(_archive_record({
                                    "trial_id": tid, "mode": mode, "pose": pose, "seed": seed,
                                    "joint_index": cfg.joint_index, "amplitude_nm": 0. if cfg.mode == "zero" else cfg.amplitude_nm,
                                    "phase": phase, "action_index": action_index,
                                    "observation_before": previous, "observation_after": observation,
                                    "diagnostics": result.diagnostics,
                                    "qpos": env.data.qpos, "qvel": env.data.qvel}), allow_nan=False)+"\n")
                                if result.terminated:
                                    break
                            if env_before != env.parameter_fingerprint() or actor_before != actor.parameter_fingerprint():
                                raise RuntimeError("fixed probe parameters changed")
                        except BaseException as exc:
                            error = {"type": type(exc).__name__, "message": str(exc)}
                            trace.write(json.dumps(_archive_record({"trial_id": tid, "collector_exception": error,
                                "phase": phase, "action_index": action_index, "requested_torque": requested,
                                "observation_before": previous, **_exception_snapshot(env)}), allow_nan=False)+"\n")
                            raise
                        finally:
                            record = None if actor is None else actor.selection_record
                            trials.append(_archive_record({
                                "trial_id": tid, "pose": pose, "seed": seed, "reset_seed": reset_seed,
                                "mode": mode, "joint_index": cfg.joint_index,
                                "amplitude_nm": 0. if cfg.mode == "zero" else cfg.amplitude_nm,
                                "selection_record": record, "selected_direction": None if record is None else record["direction"],
                                "probe_spec": None if actor is None else actor.spec(),
                                "status": "exception" if error else ("terminated" if env.terminated else "completed"),
                                "terminated": False if env is None else env.terminated,
                                "reason": error or (None if env is None else env.reason),
                                "control_steps": 0 if env is None else env.step_id,
                                "control_calls_attempted": sum(b["control_calls_attempted"] for b in budgets.values()),
                                "physics_steps": 0 if env is None else env.physics_steps,
                                "phase_budgets": budgets,
                                "environment_fingerprint_before": env_before,
                                "environment_fingerprint_after": None if env is None else env.parameter_fingerprint(),
                                "actor_fingerprint_before": actor_before,
                                "actor_fingerprint_after": None if actor is None else actor.parameter_fingerprint(),
                                "contact_configuration": None if env is None else env.contact_configuration(),
                            }))
                            geometry.append(_archive_record({"trial_id": tid, "initial": initial_geometry,
                                "final": None if env is None else env.geometry_snapshot()}))
                            checkpoint()
        metadata.update(complete=True, archive_status="completed")
    finally:
        checkpoint()
        _write_json(output / "manifest.json", {p.name: _hash(p) for p in sorted(output.iterdir())
                    if p.is_file() and p.name != "manifest.json"})
    return metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seeds", nargs="+", type=int, default=[0, 1, 2])
    parser.add_argument("--split", choices=["development", "holdout"], default="development")
    parser.add_argument("--protocol", type=Path)
    args = parser.parse_args()
    print(json.dumps(collect_probes(args.output, args.seeds, split=args.split, protocol_path=args.protocol), indent=2))


if __name__ == "__main__":
    main()
