"""Paid development/evaluation trials for a finite classical PD grid.

Gain selection is offline controller development, with every physical trial
charged. No body-model updates, privileged inputs, or task policy training.
The historical E1 collectors and results are left unchanged.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import gzip
import hashlib
import importlib.metadata
import json
from numbers import Real
from pathlib import Path
import platform
import subprocess
import sys
import time
import zipfile

import mujoco
import numpy as np

from .collect import _archive_record, _exception_snapshot, _hash, _peak, _write_json
from .environment import ExplorationConfig, GroundBodyEnv, MODEL_PATH, POSES
from .probes import direction_record


def _gain(value):
    if isinstance(value, bool) or not isinstance(value, Real) or not np.isfinite(value) or value < 0:
        raise ValueError("gains must be finite nonnegative real values")
    return float(value)


def pd_request(q, v, target, kp, kd):
    """Measured encoder velocity damping and the common 0.5 N m cap."""
    scalars = (q, v, target)
    if any(isinstance(x, bool) or not isinstance(x, Real) or not np.isfinite(x) for x in scalars):
        raise ValueError("PD inputs must be finite real scalars")
    kp, kd = _gain(kp), _gain(kd)
    with np.errstate(over="raise", invalid="raise"):
        try:
            raw = float(np.float64(kp) * (np.float64(target)-q) - np.float64(kd)*v)
        except FloatingPointError as error:
            raise ValueError("PD arithmetic overflowed") from error
    if not np.isfinite(raw):
        raise ValueError("PD arithmetic overflowed")
    return float(np.clip(raw, -.5, .5)), raw


def run_feedback(output: Path, seeds: list[int], gains: list[tuple[float, float]], *,
                 pose="supine", joint=0, split="development", protocol_path: Path):
    if (not seeds or any(type(s) is not int or s < 0 for s in seeds)
            or len(set(seeds)) != len(seeds)):
        raise ValueError("unique nonnegative seeds required")
    if pose not in POSES or type(joint) is not int or not 0 <= joint < 8:
        raise ValueError("known pose and joint required")
    if split not in ("development", "holdout"):
        raise ValueError("split must be development or holdout")
    gains = [(_gain(kp), _gain(kd)) for kp, kd in gains]
    if not gains or len(set(gains)) != len(gains):
        raise ValueError("unique gain pairs required")
    output = Path(output)
    if output.exists():
        raise FileExistsError(output)
    root = Path(__file__).resolve().parents[2]
    protocol_path = Path(protocol_path).resolve()
    if not protocol_path.is_file() or not protocol_path.is_relative_to(root):
        raise ValueError("repository protocol required")
    sources = [*sorted(Path(__file__).parent.glob("*.py")), MODEL_PATH,
               root/'pyproject.toml', protocol_path]
    source_bytes = {p.relative_to(root).as_posix(): p.read_bytes() for p in sources}
    planned = [{"trial_id": f"seed{s}_candidate{i}", "seed": s, "candidate": i,
                "kp": kp, "kd": kd, "maximum_control_steps": 300}
               for s in seeds for i, (kp, kd) in enumerate(gains)]
    episodes = [{**p, "status": "planned", "reason": None,
                 "control_calls_attempted": 0, "control_steps": 0, "physics_steps": 0,
                 "phase_budgets": {phase: dict(control_calls_attempted=0, control_steps=0, physics_steps=0)
                                   for phase in ("prefix", "control")}}
                for p in planned]
    config = ExplorationConfig()
    metadata = {
        "schema_version": 1, "purpose": "Finite classical PD development grid / frozen evaluation",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_commit": subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),
        "source_status": subprocess.check_output(['git','status','--porcelain','--untracked-files=all'],cwd=root,text=True),
        "source_sha256": {n: hashlib.sha256(b).hexdigest() for n,b in source_bytes.items()},
        "protocol": {"path": protocol_path.relative_to(root).as_posix(), "sha256": _hash(protocol_path)},
        "platform": platform.platform(), "python_version": sys.version, "python_executable": sys.executable,
        "dependencies": dict(sorted((d.metadata['Name'],d.version) for d in importlib.metadata.distributions())),
        "backend": "MuJoCo CPU", "mujoco_version": mujoco.__version__, "gpu": None,
        "pose": pose, "joint_index": joint, "seeds": seeds, "split": split,
        "gains": [list(pair) for pair in gains], "environment_config": asdict(config),
        "prefix_steps": 100, "control_steps_per_trial": 200, "target_offsets_rad": [.04,.08],
        "parameter_updates": {"body_model": 0, "policy": 0},
        "gain_selection": "All trials count as controller development when split=development; no within-trial updates.",
        "teacher_calls": 0, "external_demonstration_samples": 0,
        "planned_episodes": planned, "maximum_control_steps": 300*len(planned),
        "complete": False, "archive_status": "running",
        "claim_boundary": "Classical local PD comparison only, no full-body skills or hardware safety proof.",
    }
    metadata['source_dirty'] = bool(metadata['source_status'])
    output.mkdir(parents=True)
    with zipfile.ZipFile(output/'source_snapshot.zip','w',zipfile.ZIP_DEFLATED) as snapshot:
        for name,data in source_bytes.items():
            snapshot.writestr(name,data)
    started = time.perf_counter()
    fatal = None

    def checkpoint():
        for key in ('control_calls_attempted','control_steps','physics_steps'):
            metadata[key] = sum(e[key] for e in episodes)
        metadata.update(wall_seconds=time.perf_counter()-started,
                        completed_trials=sum(e['status']=='completed' for e in episodes),
                        terminated_trials=sum(e['status']=='terminated' for e in episodes),
                        exception_trials=sum(e['status']=='exception' for e in episodes),
                        blocked_trials=sum(e['status']=='blocked' for e in episodes))
        errors = []
        for path,data in ((output/'episodes.json',episodes),(output/'metadata.json',metadata)):
            try:
                _write_json(path, [_archive_record(e) for e in data] if isinstance(data,list) else _archive_record(data))
            except BaseException as error:
                errors.append(error)
        if errors:
            raise errors[0]

    try:
        checkpoint()
        with gzip.open(output/'trace.jsonl.gz','wt',encoding='utf-8') as trace:
            for episode in episodes:
                env = observation = previous = requested = None
                phase = 'prefix'
                error = None
                trace_failure = None
                prefix_end = selection = target = None
                errors, effort, peak, speed = [], 0., 0., 0.
                saturated = 0
                observed_diagnostic_substeps = 0
                try:
                    env = GroundBodyEnv(config)
                    reset_seed = int(np.random.SeedSequence(episode['seed']).spawn(2)[0].generate_state(1)[0])
                    observation = env.reset(seed=reset_seed,pose=pose)
                    episode['reset_seed'] = reset_seed
                    before = env.parameter_fingerprint()
                    for index in range(300):
                        phase = 'prefix' if index < 100 else 'control'
                        requested = np.zeros(8)
                        raw = None
                        q, v = (float(observation[k][joint]) for k in ('joint_position','joint_velocity'))
                        if index == 100:
                            selection = direction_record(joint,observation['joint_position'],
                                [env.model.joint(n).range for n in env.joint_names])
                            prefix_end = q
                            targets = [q+selection['direction']*offset for offset in (.04,.08)]
                            lower,upper = env.model.joint(env.joint_names[joint]).range
                            if not all(lower+.03 <= t <= upper-.03 for t in targets):
                                raise ValueError('declared target is infeasible; do not clip it')
                        if index >= 100:
                            target = targets[0 if index < 200 else 1]
                            requested[joint], raw = pd_request(q,v,target,episode['kp'],episode['kd'])
                        previous = observation
                        old_control,old_physics = env.step_id,env.physics_steps
                        budget = episode['phase_budgets'][phase]
                        budget['control_calls_attempted'] += 1
                        try:
                            result = env.step(requested)
                        finally:
                            budget['control_steps'] += env.step_id-old_control
                            budget['physics_steps'] += env.physics_steps-old_physics
                            if phase == 'control':
                                # A stop/exception can execute less than 20 ms.
                                # Charge requested effort only for paid substeps.
                                effort += float(requested[joint]**2)*(env.physics_steps-old_physics)*config.physics_dt
                            for key in ('control_calls_attempted','control_steps','physics_steps'):
                                episode[key] = sum(b[key] for b in episode['phase_budgets'].values())
                        observation = result.observation
                        try:
                            trace.write(json.dumps(_archive_record({
                                'trial_id':episode['trial_id'],'seed':episode['seed'],'candidate':episode['candidate'],
                                'control_index':index,'phase':phase,'kp':episode['kp'],'kd':episode['kd'],
                                'requested_torque':requested,'raw_pd_torque_nm':raw,'target_q_rad':target,
                                'observation_before':previous,'observation_after':observation,
                                'diagnostics':result.diagnostics,'qpos':env.data.qpos,'qvel':env.data.qvel,
                            }),allow_nan=False)+'\n')
                        except BaseException as write_error:
                            trace_failure = write_error
                            raise
                        if phase == 'control':
                            errors.append(float(observation['joint_position'][joint])-target)
                            saturated += int(abs(requested[joint])==.5)
                            speed = _peak(speed,float(np.max(np.abs(observation['joint_velocity']))))
                        for force in result.diagnostics['substep_ground_normal_forces']:
                            peak = _peak(peak,float(force))
                        observed_diagnostic_substeps += len(result.diagnostics['substep_ground_normal_forces'])
                        if result.terminated:
                            break
                    if before != env.parameter_fingerprint():
                        raise RuntimeError('environment parameters changed')
                except BaseException as exc:
                    error = {'type':type(exc).__name__,'message':str(exc)}
                    if isinstance(exc,(KeyboardInterrupt,SystemExit,OSError)) or trace_failure is not None:
                        fatal = exc
                    try:
                        trace.write(json.dumps(_archive_record({'trial_id':episode['trial_id'],
                            'collector_exception':error,'phase':phase,'observation_before':previous,
                            'requested_torque':requested,**_exception_snapshot(env)}),allow_nan=False)+'\n')
                    except BaseException as write_error:
                        fatal = fatal or write_error
                finally:
                    terminated = env is not None and env.terminated
                    complete = error is None and env is not None and env.step_id==300 and not terminated
                    episode.update(status='exception' if error else ('terminated' if terminated else 'completed'),
                        reason=env.reason if terminated else error,collector_exception=error,
                        complete=complete,prefix_end_q_rad=prefix_end,selection_record=selection,
                        metric_control_step_count=len(errors),
                        tracking_rmse_rad=None if not errors else float(np.sqrt(np.mean(np.square(errors)))),
                        requested_squared_effort_nm2s=effort,saturated_control_steps=saturated,
                        max_native_control_speed_rad_s=speed,peak_full_ground_force_n=peak,
                        observed_diagnostic_substeps=observed_diagnostic_substeps,
                        telemetry_complete_for_paid_substeps=(error is None and observed_diagnostic_substeps==episode['physics_steps']),
                        force_peak_scope=('all paid substeps' if error is None and observed_diagnostic_substeps==episode['physics_steps']
                                          else 'available returned-step telemetry only; incomplete, lower bound'))
                    try:
                        checkpoint()
                    except BaseException as save_error:
                        fatal = fatal or save_error
                        metadata['checkpoint_exception'] = {'type':type(save_error).__name__,'message':str(save_error)}
                    if fatal is not None:
                        raise fatal
        metadata.update(complete=True,archive_status='complete')
    except BaseException as exc:
        fatal = fatal or exc
        metadata.update(complete=False,archive_status='interrupted' if isinstance(exc,(KeyboardInterrupt,SystemExit)) else 'failed',
                        collector_exception={'type':type(exc).__name__,'message':str(exc)})
        raise
    finally:
        for episode in episodes:
            if episode['status']=='planned':
                episode.update(status='blocked',reason={'type':'ArchiveAborted','message':'not attempted after interruption'})
        metadata['all_trials_successful'] = all(e['status']=='completed' for e in episodes)
        try:
            checkpoint()
            _write_json(output/'manifest.json',{p.name:_hash(p) for p in sorted(output.iterdir()) if p.is_file() and p.name!='manifest.json'})
        except BaseException:
            if fatal is None:
                raise
    return metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--protocol',type=Path,required=True)
    parser.add_argument('--seeds',type=int,nargs='+',default=[0,1,2])
    parser.add_argument('--kp',type=float,nargs='+',default=[4.,16.,64.])
    parser.add_argument('--kd',type=float,nargs='+',default=[0.,.2,1.])
    parser.add_argument('--split',choices=['development','holdout'],default='development')
    parser.add_argument('--pose',choices=POSES,default='supine')
    parser.add_argument('--joint',type=int,default=0)
    args = parser.parse_args()
    print(json.dumps(run_feedback(args.output,args.seeds,[(kp,kd) for kp in args.kp for kd in args.kd],
        pose=args.pose,joint=args.joint,split=args.split,protocol_path=args.protocol),indent=2))


if __name__=='__main__':
    main()
