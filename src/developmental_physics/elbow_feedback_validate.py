"""Fixed C4-A left-elbow classical PD development; no parameter learning."""
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

from .collect import _archive_record, _exception_snapshot, _hash, _peak, _write_json
from .environment import ExplorationConfig, GroundBodyEnv, MODEL_PATH
from .feedback_validate import pd_request
from .local_coverage_ablation import native_study_abort, study_abort_spec
from .probes import direction_record


DEVELOPMENT_SEEDS = (0, 1, 2)
FIXED_GAINS = tuple((kp, kd) for kp in (4., 16., 64.) for kd in (0., .2, 1.))
JOINT = 1
PROTOCOL_PATH = "docs/ELBOW_PD_DEVELOPMENT_PROTOCOL.md"
PHASES = ("prefix", "control")


def _effort():
    return dict(requested_absolute_nm_s=0., requested_squared_nm2_s=0.,
                actual_absolute_nm_s=0., actual_squared_nm2_s=0.)


def _risk():
    return dict(peak_ground_force_n=0., ground_normal_impulse_ns=0.,
                peak_kinetic_energy_j=0., minimum_contact_distance_m=0.,
                max_native_speed_rad_s=0., guarded_substeps=0,
                outside_public_limit_endpoint_count=0)


def _risk_add(risk, diagnostics, observation, ranges, dt):
    n = diagnostics["executed_substeps"]
    arrays = [np.asarray(diagnostics[k], dtype=float) for k in (
        "substep_ground_normal_forces", "substep_kinetic_energies", "substep_minimum_contact_distances")]
    if any(a.shape != (n,) or not np.isfinite(a).all() for a in arrays):
        raise RuntimeError("risk telemetry differs from executed substeps")
    q, v = (np.asarray(observation[k], dtype=float) for k in ("joint_position", "joint_velocity"))
    if q.shape != (8,) or v.shape != (8,) or not np.isfinite(q).all() or not np.isfinite(v).all():
        raise RuntimeError("native joint endpoint is not finite length eight")
    force, energy, distance = arrays
    if np.any(force < 0.) or np.any(energy < 0.):
        raise RuntimeError("negative contact force or kinetic energy")
    risk["peak_ground_force_n"] = _peak(risk["peak_ground_force_n"], float(np.max(force, initial=0.)))
    risk["ground_normal_impulse_ns"] += float(np.sum(force))*dt
    risk["peak_kinetic_energy_j"] = _peak(risk["peak_kinetic_energy_j"], float(np.max(energy, initial=0.)))
    risk["minimum_contact_distance_m"] = min(risk["minimum_contact_distance_m"], float(np.min(distance, initial=0.)))
    risk["max_native_speed_rad_s"] = _peak(risk["max_native_speed_rad_s"], float(np.max(np.abs(v))))
    risk["guarded_substeps"] += diagnostics["guarded_substeps"]
    risk["outside_public_limit_endpoint_count"] += int(np.any((q < ranges[:,0]) | (q > ranges[:,1])))


def run_feedback(output: Path, *, protocol_path: Path):
    """Only output and the exact frozen protocol are configurable."""
    root = next(p for p in Path(__file__).resolve().parents
                if (p/"pyproject.toml").is_file() and (p/"src/developmental_physics").is_dir())
    output, protocol_path = Path(output), Path(protocol_path).resolve()
    if output.exists():
        raise FileExistsError(output)
    if protocol_path != (root/PROTOCOL_PATH).resolve() or not protocol_path.is_file():
        raise ValueError("exact frozen left-elbow development protocol required")
    sources = [*sorted((root/"src/developmental_physics").glob("*.py")),
               Path(__file__), MODEL_PATH, root/"pyproject.toml", protocol_path]
    source_bytes = {p.relative_to(root).as_posix(): p.read_bytes() for p in sources}
    planned = [dict(trial_id=f"seed{s}_candidate{i}", seed=s, candidate=i,
                    kp=kp, kd=kd, maximum_control_steps=300)
               for s in DEVELOPMENT_SEEDS for i, (kp, kd) in enumerate(FIXED_GAINS)]
    episodes = [{**p, "status":"planned", "reason":None, "complete":False,
                 "control_calls_attempted":0, "control_steps":0, "physics_steps":0,
                 "phase_budgets":{phase:dict(control_calls_attempted=0, control_steps=0, physics_steps=0)
                                  for phase in PHASES}} for p in planned]
    config = ExplorationConfig()
    metadata = {
        "schema_version":1, "purpose":"Fixed C4-A left-elbow classical PD development",
        "created_at_utc":datetime.now(timezone.utc).isoformat(),
        "source_commit":subprocess.check_output(["git","rev-parse","HEAD"],cwd=root,text=True).strip(),
        "source_status":subprocess.check_output(["git","status","--porcelain","--untracked-files=all"],cwd=root,text=True),
        "source_sha256":{n:hashlib.sha256(b).hexdigest() for n,b in source_bytes.items()},
        "protocol":{"path":PROTOCOL_PATH,"sha256":_hash(protocol_path)},
        "platform":platform.platform(), "python_version":sys.version, "python_executable":sys.executable,
        "dependencies":dict(sorted((d.metadata["Name"],d.version) for d in importlib.metadata.distributions())),
        "backend":"MuJoCo CPU", "mujoco_version":mujoco.__version__, "gpu":None,
        "pose":"supine", "joint_index":JOINT, "seeds":list(DEVELOPMENT_SEEDS), "split":"development",
        "gains":[list(p) for p in FIXED_GAINS], "environment_config":asdict(config),
        "prefix_steps":100, "control_steps_per_trial":200, "target_offsets_rad":[.04,.08],
        "study_abort_spec":study_abort_spec(), "parameter_updates":{"body_model":0,"policy":0,"gains":0},
        "teacher_calls":0, "external_demonstration_samples":0, "model_updates":0,
        "initial_controller_capability":"Classical target-position PD from public encoders and current task target",
        "pd_controller_spec":{"implementation":"feedback_validate.pd_request","permission_nm":.5,
                              "body_model_input":False,"gain_updates":0},
        "gain_selection":"Offline development; all nine candidates and all paid prefixes count; independent audit selects",
        "target_information":"Current target only; no future switch preview; paid qref is not clipped",
        "planned_episodes":planned, "planned_episode_count":len(planned),
        "maximum_control_steps":300*len(planned), "maximum_physics_steps":3000*len(planned),
        "cpu_seconds_scope":"Current process; same start/checkpoint scope as wall_seconds; excludes imports, initial source snapshot and pre-timer setup",
        "completion_definition":"Every planned trial has an outcome; no scientific or safety acceptance implied",
        "claim_boundary":"Classical local PD only; no full-body skill, online learning or hardware safety proof",
        "complete":False, "archive_status":"running",
    }
    metadata["source_dirty"] = bool(metadata["source_status"])
    output.mkdir(parents=True)
    with zipfile.ZipFile(output/"source_snapshot.zip","w",zipfile.ZIP_DEFLATED) as snapshot:
        for name,data in source_bytes.items():
            snapshot.writestr(name,data)
    started, cpu_started, fatal = time.perf_counter(), time.process_time(), None

    def checkpoint():
        for key in ("control_calls_attempted","control_steps","physics_steps"):
            metadata[key] = sum(e[key] for e in episodes)
        metadata.update(wall_seconds=time.perf_counter()-started, cpu_seconds=time.process_time()-cpu_started)
        for status in ("completed","terminated","exception","blocked"):
            metadata[status+"_trials"] = sum(e["status"] == status for e in episodes)
        errors = []
        for filename,data in (("episodes.json",episodes),("metadata.json",metadata)):
            try:
                _write_json(output/filename, [_archive_record(e) for e in data]
                            if isinstance(data,list) else _archive_record(data))
            except BaseException as exc:
                errors.append(exc)
        if errors:
            raise errors[0]

    try:
        checkpoint()
        with gzip.open(output/"trace.jsonl.gz","wt",encoding="utf-8") as trace:
            for episode in episodes:
                env = observation = previous = requested = None
                index = raw = target = qref = selection = study = env_before = None
                result = old_control = old_physics = partial_error = None
                error = trace_failure = None
                phase = "prefix"
                tracking, partial = [], []
                phase_effort = {p:_effort() for p in PHASES}
                actual_substeps = {p:0 for p in PHASES}
                complete_transitions = {p:0 for p in PHASES}
                phase_risk = {p:_risk() for p in ("full",*PHASES)}
                returned = written = unreturned = telemetry = saturated = pd_calls = pd_failed = 0
                pd_seconds = 0.
                try:
                    env = GroundBodyEnv(config)
                    reset_seed = int(np.random.SeedSequence(episode["seed"]).spawn(2)[0].generate_state(1)[0])
                    episode["reset_seed"] = reset_seed
                    observation = env.reset(seed=reset_seed,pose="supine")
                    env_before = env.parameter_fingerprint()
                    ranges = np.asarray([env.model.joint(n).range for n in env.joint_names])
                    for index in range(300):
                        phase = "prefix" if index < 100 else "control"
                        requested, raw, target = np.zeros(8), None, None
                        result = partial_error = old_control = old_physics = None
                        previous = observation
                        q, v = (float(observation[k][JOINT]) for k in ("joint_position","joint_velocity"))
                        if index == 100:
                            selection = direction_record(JOINT,observation["joint_position"],ranges)
                            qref = q
                            targets = [qref+selection["direction"]*offset for offset in (.04,.08)]
                            if not all(ranges[JOINT,0]+.03 <= t <= ranges[JOINT,1]-.03 for t in targets):
                                raise ValueError("declared target is infeasible; do not clip it")
                        if phase == "control":
                            target = targets[0 if index < 200 else 1]
                            pd_calls += 1
                            action_started = time.perf_counter()
                            try:
                                requested[JOINT],raw = pd_request(q,v,target,episode["kp"],episode["kd"])
                            except BaseException:
                                pd_failed += 1
                                raise
                            finally:
                                pd_seconds += time.perf_counter()-action_started
                        previous = observation
                        old_control,old_physics = env.step_id,env.physics_steps
                        budget = episode["phase_budgets"][phase]
                        budget["control_calls_attempted"] += 1
                        try:
                            result = env.step(requested)
                        except BaseException:
                            unreturned += env.physics_steps-old_physics
                            raise
                        finally:
                            budget["control_steps"] += env.step_id-old_control
                            budget["physics_steps"] += env.physics_steps-old_physics
                            paid_dt = (env.physics_steps-old_physics)*env.config.physics_dt
                            phase_effort[phase]["requested_absolute_nm_s"] += abs(float(requested[JOINT]))*paid_dt
                            phase_effort[phase]["requested_squared_nm2_s"] += float(requested[JOINT])**2*paid_dt
                            for key in ("control_calls_attempted","control_steps","physics_steps"):
                                episode[key] = sum(b[key] for b in episode["phase_budgets"].values())
                        returned += 1
                        observation = result.observation
                        if phase == "control":
                            study = native_study_abort(observation["joint_position"][JOINT],
                                observation["joint_velocity"][JOINT],qref,stage="endpoint")
                            if study is not None:
                                study.update(phase=phase,step_index=index)
                        n = result.diagnostics["executed_substeps"]
                        if type(n) is not int or not 0 <= n <= 10 or n != env.physics_steps-old_physics:
                            raise RuntimeError("returned substep count differs from paid physics cost")
                        if env.step_id-old_control != 1:
                            raise RuntimeError("returned control count differs from one attempted call")
                        if phase == "control" and n != 10:
                            partial_error = float(observation["joint_position"][JOINT])-target
                            partial.append(partial_error)
                        realized = np.asarray(result.diagnostics["applied_torque_history"],dtype=float)
                        if n == 0 and realized.size == 0:
                            realized = realized.reshape(0,8)
                        if realized.shape != (n,8) or not np.isfinite(realized).all() or np.max(np.abs(realized),initial=0.) > .5:
                            raise RuntimeError("applied torque history differs from paid substeps or permission")
                        phase_effort[phase]["actual_absolute_nm_s"] += float(np.sum(np.abs(realized[:,JOINT])))*env.config.physics_dt
                        phase_effort[phase]["actual_squared_nm2_s"] += float(np.sum(realized[:,JOINT]**2))*env.config.physics_dt
                        actual_substeps[phase] += n
                        for p in ("full",phase):
                            _risk_add(phase_risk[p],result.diagnostics,observation,ranges,env.config.physics_dt)
                        telemetry += n
                        if n == 10:
                            complete_transitions[phase] += 1
                        if phase == "control":
                            endpoint_error = float(observation["joint_position"][JOINT])-target
                            if n == 10:
                                tracking.append(endpoint_error)
                                saturated += int(abs(float(requested[JOINT])) == .5)
                        try:
                            trace.write(json.dumps(_archive_record({
                                "trial_id":episode["trial_id"],"seed":episode["seed"],"candidate":episode["candidate"],
                                "control_index":index,"phase":phase,"kp":episode["kp"],"kd":episode["kd"],
                                "control_steps_before":old_control,"physics_steps_before":old_physics,
                                "control_steps_after":env.step_id,"physics_steps_after":env.physics_steps,
                                "requested_torque":requested,"raw_pd_torque_nm":raw,"target_q_rad":target,
                                "study_abort":study,"environment_terminated":bool(env.terminated),
                                "environment_stop_reason":env.reason,"complete_transition":n == 10,
                                "partial_interval_target_error_rad":partial_error,
                                "observation_before":previous,"observation_after":observation,
                                "diagnostics":result.diagnostics,"qpos":env.data.qpos,"qvel":env.data.qvel,
                            }),allow_nan=False)+"\n")
                            written += 1
                        except BaseException as exc:
                            trace_failure = exc
                            raise
                        if result.terminated or study is not None:
                            break
                        if n != 10:
                            raise RuntimeError("partial return without an environment stop")
                    if env_before != env.parameter_fingerprint():
                        raise RuntimeError("environment parameters changed")
                except BaseException as exc:
                    error = {"type":type(exc).__name__,"message":str(exc)}
                    if isinstance(exc,(KeyboardInterrupt,SystemExit,OSError)) or trace_failure is not None:
                        fatal = exc
                    try:
                        trace.write(json.dumps(_archive_record({
                            "trial_id":episode["trial_id"],"seed":episode["seed"],"candidate":episode["candidate"],
                            "control_index":index,"phase":phase,"kp":episode["kp"],"kd":episode["kd"],
                            "collector_exception":error,"study_abort":study,"requested_torque":requested,
                            "raw_pd_torque_nm":raw,"target_q_rad":target,"observation_before":previous,
                            "control_steps_before":old_control,"physics_steps_before":old_physics,
                            "control_steps_after":None if env is None else env.step_id,
                            "physics_steps_after":None if env is None else env.physics_steps,
                            "returned_step_diagnostics":None if result is None else result.diagnostics,
                            "returned_observation_after":None if result is None else result.observation,
                            "partial_interval_target_error_rad":partial_error,
                            "unreturned_physics_steps":unreturned,"returned_control_steps":returned,
                            "trace_rows_written":written,**_exception_snapshot(env),
                        }),allow_nan=False)+"\n")
                    except BaseException as write_exc:
                        trace_failure = trace_failure or write_exc
                        episode["exception_trace_write_error"] = {"type":type(write_exc).__name__,"message":str(write_exc)}
                        fatal = fatal or write_exc
                finally:
                    terminated = env is not None and (env.terminated or study is not None)
                    complete = (error is None and env is not None and not terminated
                                and env.step_id == 300 and env.physics_steps == 3000
                                and complete_transitions == {"prefix":100,"control":200}
                                and returned == written == 300 and telemetry == 3000)
                    reason = env.reason if env is not None and env.terminated else (study if study is not None else error)
                    observed = sum(actual_substeps.values())
                    episode.update(_archive_record({
                        "status":"exception" if error else ("terminated" if terminated else "completed"),
                        "reason":reason,"collector_exception":error,"complete":complete,
                        "trace_write_failure":None if trace_failure is None else
                            {"type":type(trace_failure).__name__,"message":str(trace_failure)},
                        "study_abort":study,"environment_terminated":None if env is None else bool(env.terminated),
                        "environment_stop_reason":None if env is None else env.reason,
                        "environment_fingerprint_before":env_before,
                        "environment_fingerprint_after":None if env is None else env.parameter_fingerprint(),
                        "prefix_end_q_rad":qref,"selection_record":selection,
                        "metric_control_step_count":len(tracking),
                        "tracking_rmse_rad":None if not tracking else float(np.sqrt(np.mean(np.square(tracking)))),
                        "partial_interval_target_errors_rad":partial,"partial_interval_target_error_count":len(partial),
                        "phase_complete_transition_counts":complete_transitions,
                        "requested_squared_effort_nm2s":phase_effort["control"]["requested_squared_nm2_s"],
                        "phase_effort":phase_effort,"phase_actual_effort_substeps":actual_substeps,
                        "phase_actual_effort_complete":{p:actual_substeps[p] == episode["phase_budgets"][p]["physics_steps"] for p in PHASES},
                        "phase_actual_effort_missing_substeps":{p:episode["phase_budgets"][p]["physics_steps"]-actual_substeps[p] for p in PHASES},
                        "actual_effort_complete":observed == episode["physics_steps"],
                        "actual_effort_is_lower_bound":observed < episode["physics_steps"],
                        "returned_control_steps":returned,"trace_rows_written":written,
                        "returned_unstored_control_steps":returned-written,"unreturned_physics_steps":unreturned,
                        "saturated_control_steps":saturated,"phase_risk":phase_risk,
                        "max_native_control_speed_rad_s":phase_risk["control"]["max_native_speed_rad_s"],
                        "peak_full_ground_force_n":phase_risk["full"]["peak_ground_force_n"],
                        "observed_diagnostic_substeps":telemetry,
                        "telemetry_complete_for_paid_substeps":telemetry == episode["physics_steps"],
                        "risk_telemetry_complete":error is None and trace_failure is None and unreturned == 0 and telemetry == episode["physics_steps"],
                        "pd_action_calls":pd_calls,"failed_pd_attempts":pd_failed,"pd_action_seconds":pd_seconds,
                    }))
                    try:
                        checkpoint()
                    except BaseException as save_exc:
                        fatal = fatal or save_exc
                        metadata["checkpoint_exception"] = {"type":type(save_exc).__name__,"message":str(save_exc)}
                    if fatal is not None:
                        raise fatal
        metadata.update(complete=True,archive_status="complete")
    except BaseException as exc:
        fatal = fatal or exc
        metadata.update(complete=False,archive_status="interrupted" if isinstance(exc,(KeyboardInterrupt,SystemExit)) else "failed",
                        collector_exception={"type":type(exc).__name__,"message":str(exc)})
        raise
    finally:
        for episode in episodes:
            if episode["status"] == "planned":
                episode.update(status="blocked",reason={"type":"ArchiveAborted","message":"not attempted after fatal archive failure"})
        metadata["all_trials_successful"] = all(e["complete"] for e in episodes)
        try:
            checkpoint()
            _write_json(output/"manifest.json",{p.name:_hash(p) for p in sorted(output.iterdir())
                                               if p.is_file() and p.name != "manifest.json"})
        except BaseException:
            if fatal is None:
                raise
    return metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--protocol",type=Path,required=True)
    args = parser.parse_args()
    print(json.dumps(run_feedback(args.output,protocol_path=args.protocol),indent=2))


if __name__ == "__main__":
    main()
