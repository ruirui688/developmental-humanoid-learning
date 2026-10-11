"""Archive ground-body physics checks with zero parameter updates.

This is sensor collection, not an RL or system-identification training entry.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import gzip
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path
import platform
import subprocess
import sys
import time
import zipfile

import mujoco
import numpy as np

from .environment import ExplorationConfig, GroundBodyEnv, MODEL_PATH, POSES
from .exploration import SmoothRandomExplorer


def _jsonable(value):
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    raise TypeError(type(value).__name__)


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _archive_record(record: dict[str, object]) -> dict[str, object]:
    """Keep JSON valid while retaining the location and kind of invalid values.

    Paths use JSON Pointer. Finite numbers are neither rounded nor replaced.
    A null with an accompanying marker means an invalid measurement, not zero.
    """
    invalid = []

    def convert(value, path):
        if isinstance(value, np.ndarray):
            value = value.tolist()
        elif isinstance(value, np.generic):
            value = value.item()
        if isinstance(value, float) and not math.isfinite(value):
            invalid.append({"path": path, "value": "nan" if math.isnan(value) else ("+inf" if value > 0 else "-inf")})
            return None
        if isinstance(value, dict):
            return {
                key: convert(item, path + "/" + str(key).replace("~", "~0").replace("/", "~1"))
                for key, item in value.items()
            }
        if isinstance(value, (list, tuple)):
            return [convert(item, path + "/" + str(index)) for index, item in enumerate(value)]
        return value

    result = convert(record, "")
    result["invalid_numeric_fields"] = invalid
    return result


def _write_json(path: Path, content) -> None:
    """Replace a completed checkpoint, without leaving a half-written JSON file."""
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(content, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    # Windows scanners/readers can briefly hold a file without delete sharing.
    # Keep the prior checkpoint intact and retry only permission/sharing errors.
    for attempt in range(10):
        try:
            temporary.replace(path)
            return
        except PermissionError:
            if attempt == 9:
                raise
            time.sleep(.05 * (attempt + 1))


def _peak(previous: float, value: float) -> float:
    # Preserve the fact of an invalid measurement rather than max(0, nan) == 0.
    if not np.isfinite(previous) or not np.isfinite(value):
        return value if np.isfinite(previous) else previous
    return max(previous, value)


def _exception_snapshot(env) -> dict[str, object]:
    """Best-effort raw endpoint; retrieval errors must not hide the first error."""
    result = {}
    if env is None:
        return result
    for name, getter in (
        ("observation_after", env.observation),
        ("diagnostics", env.diagnostics),
        ("qpos", lambda: env.data.qpos.copy()),
        ("qvel", lambda: env.data.qvel.copy()),
    ):
        try:
            result[name] = getter()
        except Exception as error:
            result[name + "_retrieval_error"] = {"type": type(error).__name__, "message": str(error)}
    return result


def collect(output: Path, seeds: list[int], steps: int, *,
            contact_profiles: list[str] | None = None,
            prefix_steps: list[int] | None = None,
            protocol_path: Path | None = None) -> dict[str, object]:
    if (type(steps) is not int or steps < 1 or not seeds or len(set(seeds)) != len(seeds)
            or any(type(seed) is not int or seed < 0 for seed in seeds)):
        raise ValueError("steps must be positive and seeds must be unique and nonempty")
    expanded_conditions = contact_profiles is not None or prefix_steps is not None
    profiles = ["baseline"] if contact_profiles is None else list(contact_profiles)
    prefixes = [0] if prefix_steps is None else list(prefix_steps)
    if (not profiles or any(profile not in ("baseline", "compliant") for profile in profiles)
            or len(set(profiles)) != len(profiles)):
        raise ValueError("contact profiles must be unique baseline/compliant names")
    if (not prefixes or any(type(n) is not int or not 0 <= n < steps for n in prefixes)
            or len(set(prefixes)) != len(prefixes)):
        raise ValueError("prefix lengths must be unique integers in [0, steps)")
    conditions = [(profile, prefix, mode) for profile in profiles for prefix in prefixes
                  for mode in ("zero_torque", "smooth_random")]
    if output.exists():
        raise FileExistsError(f"archive already exists: {output}")
    root = Path(__file__).resolve().parents[2]
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    status = subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=all"], cwd=root, text=True)
    source_paths = [*sorted(Path(__file__).parent.glob("*.py")), MODEL_PATH, root / "pyproject.toml"]
    if protocol_path is not None:
        protocol_path = protocol_path.resolve()
        if not protocol_path.is_file() or not protocol_path.is_relative_to(root):
            raise ValueError("protocol must be an existing file inside this repository")
        source_paths.append(protocol_path)
    source_bytes = {p.relative_to(root).as_posix(): p.read_bytes() for p in source_paths}
    source_hashes = {name: hashlib.sha256(content).hexdigest() for name, content in source_bytes.items()}
    config = ExplorationConfig()
    profile_configs = {profile: ExplorationConfig(ground_contact_profile=profile) for profile in profiles}
    output.mkdir(parents=True)
    with zipfile.ZipFile(output / "source_snapshot.zip", "w", compression=zipfile.ZIP_DEFLATED) as snapshot:
        for name, content in source_bytes.items():
            snapshot.writestr(name, content)
    trials = []
    snapshots = []
    start = time.perf_counter()
    metadata = {
        "schema_version": 3,
        "purpose": "CPU no-training ground-body physics and sensor collection",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_commit": commit, "source_dirty": bool(status), "source_status": status,
        "source_sha256": source_hashes, "asset_sha256": _hash(MODEL_PATH),
        "platform": platform.platform(), "processor": platform.processor(),
        "python_version": sys.version, "python_executable": sys.executable,
        "dependencies": dict(sorted((d.metadata['Name'], d.version) for d in importlib.metadata.distributions())),
        "dynamics_backend": "MuJoCo CPU", "mujoco_version": mujoco.__version__,
        "gpu": None, "renderer": None,
        "config": asdict(config), "seeds": seeds, "poses": POSES,
        "contact_profiles": profiles, "prefix_steps": prefixes,
        "profile_configs": {profile: asdict(cfg) for profile, cfg in profile_configs.items()},
        "protocol": None if protocol_path is None else {
            "path": protocol_path.relative_to(root).as_posix(), "sha256": _hash(protocol_path)},
        "steps_per_trial_limit": steps, "expected_trial_count": len(POSES) * len(seeds) * len(conditions),
        "maximum_control_steps": steps * len(POSES) * len(seeds) * len(conditions),
        "maximum_physics_steps": steps * config.control_substeps * len(POSES) * len(seeds) * len(conditions),
        "archive_status": "running", "complete": False,
        "parameter_updates": {"model": 0, "policy": 0, "gate": 0},
        "teacher_calls": 0, "external_demonstration_samples": 0,
        "exploration": {"distribution": "independent uniform per joint", "smoothing": .9, "feedback_used_for_action_selection": False},
        "random_streams": "SeedSequence(root_seed).spawn(2): separate reset and exploration seeds, recorded per trial",
        "prefix_schedule": "Fixed zero-torque prefix; no hidden settling or actor RNG consumption. Remaining steps form the exploration phase, including zero-torque controls.",
        "measurement_assumptions": "ideal joint encoders, torso gyro/accelerometer and actuator torque",
        "privileged_fields": ["qpos", "qvel", "diagnostics", "geometry snapshots"],
        "claim_boundary": "No learned body model, competence promotion, acquired rolling/standing/walking, biological or G1 validity.",
    }

    def checkpoint():
        metadata.update({
            "trial_count": len(trials),
            "control_steps": sum(t["control_steps"] for t in trials),
            "control_calls_attempted": sum(t["control_calls_attempted"] for t in trials),
            "prefix_control_calls_attempted": sum(t["prefix_control_calls_attempted"] for t in trials),
            "exploration_control_calls_attempted": sum(t["exploration_control_calls_attempted"] for t in trials),
            "physics_steps": sum(t["physics_steps"] for t in trials),
            "prefix_control_steps": sum(t["prefix_control_steps"] for t in trials),
            "prefix_physics_steps": sum(t["prefix_physics_steps"] for t in trials),
            "exploration_control_steps": sum(t["exploration_control_steps"] for t in trials),
            "exploration_physics_steps": sum(t["exploration_physics_steps"] for t in trials),
            "terminated_trials": sum(t["terminated"] for t in trials),
            "exception_trials": sum(t["status"] == "exception" for t in trials),
            "wall_seconds": time.perf_counter() - start,
        })
        _write_json(output / "trials.json", trials)
        _write_json(output / "geometry.json", snapshots)
        _write_json(output / "metadata.json", _archive_record(metadata))

    checkpoint()
    try:
        with gzip.open(output / "trace.jsonl.gz", "wt", encoding="utf-8") as trace:
            for pose in POSES:
                for seed in seeds:
                    for contact_profile, prefix_length, mode in conditions:
                        config = profile_configs[contact_profile]
                        env = actor = None
                        observation = previous = requested = None
                        phase = action_index = None
                        initial_qpos = initial_angles = initial_geometry = None
                        env_before = actor_before = None
                        trial_id = f"{pose}_seed{seed}_{mode}"
                        if expanded_conditions:
                            trial_id = f"{contact_profile}_prefix{prefix_length}_{trial_id}"
                        reset_stream, exploration_stream = np.random.SeedSequence(seed).spawn(2)
                        reset_seed = int(reset_stream.generate_state(1)[0])
                        exploration_seed = int(exploration_stream.generate_state(1)[0])
                        trial_start = time.perf_counter()
                        speed_peak = torque_peak = force_peak = energy_peak = 0.
                        contact_steps = interventions = guarded_substeps = calls = samples = 0
                        squared_excursion = 0.
                        minimum_distance = 0.
                        exception = None
                        try:
                            env = GroundBodyEnv(config)
                            observation = env.reset(seed=reset_seed, pose=pose)
                            actor = SmoothRandomExplorer(env.action_limits, seed=exploration_seed)
                            env_before = env.parameter_fingerprint()
                            actor_before = actor.parameter_fingerprint()
                            initial_qpos = env.data.qpos.copy()
                            initial_angles = observation["joint_position"].copy()
                            initial_geometry = env.geometry_snapshot()
                            for step_index in range(steps):
                                phase = "prefix" if step_index < prefix_length else "exploration"
                                action_index = None if phase == "prefix" else step_index - prefix_length
                                requested = np.zeros(8) if mode == "zero_torque" or phase == "prefix" else actor.act(observation)
                                previous = observation
                                calls += 1
                                result = env.step(requested)
                                observation = result.observation
                                diagnostics = result.diagnostics
                                trace.write(json.dumps(_archive_record({
                                    "trial_id": trial_id,
                                    "contact_profile": contact_profile, "prefix_steps": prefix_length,
                                    "phase": phase, "action_index": action_index,
                                    "observation_before": previous,
                                    "observation_after": observation,
                                    "diagnostics": diagnostics,
                                    "qpos": env.data.qpos,
                                    "qvel": env.data.qvel,
                                }), allow_nan=False) + "\n")
                                samples += 1
                                speed_peak = _peak(speed_peak, float(np.max(np.abs(observation["joint_velocity"]))))
                                torque_peak = _peak(torque_peak, float(np.max(np.abs(observation["actuator_torque"]))))
                                force_peak = _peak(force_peak, diagnostics["ground_normal_force"])
                                energy_peak = _peak(energy_peak, diagnostics["kinetic_energy"])
                                distance = diagnostics["minimum_contact_distance"]
                                minimum_distance = min(minimum_distance, distance) if np.isfinite(distance) else distance
                                contact_steps += int(diagnostics["ground_contact_count"] > 0)
                                guarded = diagnostics.get("guarded_substeps", 0)
                                guarded_substeps += guarded
                                interventions += int(guarded > 0 or not np.array_equal(requested, diagnostics["applied_torque"]))
                                squared_excursion += float(np.mean((observation["joint_position"] - initial_angles) ** 2))
                                if result.terminated:
                                    break
                            if env_before != env.parameter_fingerprint() or actor_before != actor.parameter_fingerprint():
                                raise RuntimeError("configuration changed during no-training collection")
                        except BaseException as error:
                            exception = {"type": type(error).__name__, "message": str(error)}
                            trace.write(json.dumps(_archive_record({
                                "trial_id": trial_id, "collector_exception": exception,
                                "contact_profile": contact_profile, "prefix_steps": prefix_length,
                                "phase": phase, "action_index": action_index,
                                "control_calls_attempted": calls,
                                "requested_torque": requested, "observation_before": previous,
                                **_exception_snapshot(env),
                            }), allow_nan=False) + "\n")
                            raise
                        finally:
                            # Include the environment counters even if step() raised
                            # after integrating, before returning a StepResult.
                            endpoint = _exception_snapshot(env)
                            try:
                                final_geometry = None if env is None else env.geometry_snapshot()
                            except Exception as error:
                                final_geometry = {"retrieval_error": {"type": type(error).__name__, "message": str(error)}}
                            trial = {
                                "trial_id": trial_id, "pose": pose, "seed": seed, "mode": mode,
                                "contact_profile": contact_profile, "prefix_steps": prefix_length,
                                "environment_config": asdict(config),
                                "contact_configuration": None if env is None else env.contact_configuration(),
                                "reset_seed": reset_seed, "exploration_seed": exploration_seed,
                                "status": "exception" if exception else ("terminated" if env.terminated else "completed"),
                                "control_steps": 0 if env is None else env.step_id,
                                "control_calls_attempted": calls,
                                "prefix_control_calls_attempted": min(calls, prefix_length),
                                "exploration_control_calls_attempted": max(0, calls - prefix_length),
                                "physics_steps": 0 if env is None else env.physics_steps,
                                "prefix_control_steps": 0 if env is None else min(env.step_id, prefix_length),
                                "prefix_physics_steps": 0 if env is None else min(env.physics_steps, prefix_length * config.control_substeps),
                                "exploration_control_steps": 0 if env is None else max(0, env.step_id - prefix_length),
                                "exploration_physics_steps": 0 if env is None else max(0, env.physics_steps - prefix_length * config.control_substeps),
                                "simulated_seconds": 0. if env is None else float(env.data.time),
                                "wall_seconds": time.perf_counter() - trial_start,
                                "terminated": False if env is None else env.terminated,
                                "reason": "collector_exception" if exception else env.reason,
                                "collector_exception": exception,
                                "metric_samples": samples,
                                "joint_excursion_rms_rad": None if not samples else float(np.sqrt(squared_excursion / samples)),
                                "peak_joint_speed_rad_s": speed_peak, "peak_actuator_torque_nm": torque_peak,
                                "peak_ground_normal_force_n": force_peak, "peak_kinetic_energy_j": energy_peak,
                                "minimum_contact_distance_m": minimum_distance,
                                "ground_contact_steps": contact_steps, "command_intervention_steps": interventions,
                                "guarded_physics_substeps": guarded_substeps,
                                "initial_qpos": initial_qpos, "final_qpos": endpoint.get("qpos"),
                                "final_endpoint": endpoint if exception else None,
                                "environment_fingerprint_before": env_before,
                                "environment_fingerprint_after": None if env is None else env.parameter_fingerprint(),
                                "explorer_fingerprint_before": actor_before,
                                "explorer_fingerprint_after": None if actor is None else actor.parameter_fingerprint(),
                                "model_updates": 0, "policy_updates": 0, "gate_updates": 0,
                            }
                            trials.append(_archive_record(trial))
                            snapshots.append(_archive_record({
                                "trial_id": trial_id, "pose": pose, "seed": seed, "mode": mode,
                                "contact_profile": contact_profile, "prefix_steps": prefix_length,
                                "initial": initial_geometry, "final": final_geometry,
                            }))
                            trace.flush()
                            checkpoint()
    except BaseException as error:
        metadata.update({"archive_status": "failed", "complete": False,
                         "collector_exception": {"type": type(error).__name__, "message": str(error)}})
        raise
    else:
        metadata.update({"archive_status": "complete", "complete": True})
    finally:
        # The gzip stream is closed here, so the manifest hashes finalized bytes.
        checkpoint()
        manifest = {p.name: _hash(p) for p in sorted(output.iterdir()) if p.is_file() and p.name != "manifest.json"}
        _write_json(output / "manifest.json", manifest)
    return metadata


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seeds", type=int, nargs="+", default=[0, 1, 2])
    parser.add_argument("--steps", type=int, default=250)
    parser.add_argument("--contact-profiles", nargs="+", choices=("baseline", "compliant"))
    parser.add_argument("--prefix-steps", type=int, nargs="+")
    parser.add_argument("--protocol", type=Path)
    args = parser.parse_args()
    metadata = collect(args.output, args.seeds, args.steps,
                       contact_profiles=args.contact_profiles, prefix_steps=args.prefix_steps,
                       protocol_path=args.protocol)
    print(json.dumps({k: metadata[k] for k in ("trial_count", "control_steps", "physics_steps", "terminated_trials", "wall_seconds", "source_commit", "source_dirty", "parameter_updates")}, indent=2))


if __name__ == "__main__":
    main()
