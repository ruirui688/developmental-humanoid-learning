"""Frozen finite pair-calibration executability development; zero learning.

Real execution requires clean source. Synthetic entry requires backend replacement.
Two predeclared pulse schedules, six trials, no retries or adaptive extension.
"""
from __future__ import annotations

from collections import Counter
import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import gzip
import hashlib
import importlib.metadata
import json
from pathlib import Path
import subprocess
import time
import zipfile

import numpy as np

from developmental_physics.collect import _archive_record, _exception_snapshot, _hash, _write_json
from developmental_physics.environment import ExplorationConfig, GroundBodyEnv, MODEL_PATH
from developmental_physics.probes import direction_record

FORMAL_EXECUTION_FROZEN = True
_REAL_ENV = GroundBodyEnv
SEEDS = (0, 1, 2)
PULSES = (2, 1)
RESET_SEEDS = {0:3757552657, 1:1641411168, 2:2001025171}
PREFIX = 100
ACTIVE = 400
AMPLITUDES = (.125,.25,.375,.5,.25)
PHASES = ('prefix','calibration')
EFFORT_KEYS = ('requested_absolute_nm_s','requested_squared_nm2_s','actual_absolute_nm_s','actual_squared_nm2_s')
PROTOCOL_PATH = 'docs/PAIR_CALIBRATION_DEVELOPMENT_PROTOCOL.md'
AUDITOR_PATH = 'scripts/audit_pair_calibration.py'


def pulse_request(active, pulse_steps, directions):
    if type(active) is not int or not 0<=active<400 or type(pulse_steps) is not int or pulse_steps not in PULSES:
        raise ValueError('Fixed active[0,400) and pulse2/1 required')
    s=np.asarray(directions,dtype=float)
    if s.shape!=(2,) or not np.isfinite(s).all() or any(x not in (-1.,1.) for x in s):
        raise ValueError('Two fixed native signed directions required')
    block,slot=divmod(active,20)
    sign=1. if slot<pulse_steps else (-1. if 10<=slot<10+pulse_steps else 0.)
    shape=(1.,0.) if block<5 else (0.,1.) if block<10 else (1.,1.) if block<15 else (1.,-1.)
    return tuple(s*AMPLITUDES[block%5]*np.asarray(shape)*sign)


def native(observation):
    for key,size in (('joint_position',8),('joint_velocity',8),('actuator_torque',8),('previous_command',8),('imu_gyro',3),('imu_acceleration',3)):
        a=np.asarray(observation[key],dtype=float)
        if a.shape!=(size,) or not np.isfinite(a).all():raise ValueError('Invalid native observation '+key)
    return (tuple(float(x) for x in observation['joint_position'][:2]),
            tuple(float(x) for x in observation['joint_velocity'][:2]))


def study_abort(q,v,qref):
    items=[]
    for i in range(2):
        if abs(q[i]-qref[i])>=.12:items.append({'joint_index':i,'signal':'absolute_q_minus_qref_rad'})
        if abs(v[i])>=1.:items.append({'joint_index':i,'signal':'absolute_velocity_rad_s'})
    return None if not items else {'type':'StudyAbort','triggers':items,'q_rad':list(q),
        'qref_rad':list(qref),'velocity_rad_s':list(v),
        'thresholds':{'absolute_q_minus_qref_rad':.12,'absolute_velocity_rad_s':1.},'feedback_action':None}


def choose_candidate(episodes):
    candidates=[]
    for pulse in PULSES:
        rows=[e for e in episodes if e['pulse_steps']==pulse]
        eligible=(len(rows)==3 and {e['seed'] for e in rows}==set(SEEDS) and all(
            e.get('status')=='completed' and e.get('completed') is True
            and e.get('study_abort') is None and e.get('environment_terminated') is False
            and e.get('collector_exception') is None and e.get('trace_write_failure') is None
            and e.get('risk_telemetry_complete') is True and e.get('actual_effort_complete') is True
            and e.get('control_calls_attempted')==500 and e.get('control_steps')==500
            and e.get('physics_steps')==5000 and e.get('written_returned_steps')==500
            and e.get('complete_active_endpoints')==400
            and e.get('environment_fingerprint_before')==e.get('environment_fingerprint_after')
            for e in rows))
        candidates.append({'pulse_steps':pulse,'zero_steps_per_half':10-pulse,'eligible':eligible,
            'trial_ids':[e['trial_id'] for e in rows]})
    selected=next((c['pulse_steps'] for c in candidates if c['eligible']),None)
    return {'candidates':candidates,'selected_pulse_steps':selected,
        'status':'eligible' if selected is not None else 'blocked',
        'selection_rule':'pulse2 if all three complete with no stop and complete raw telemetry, otherwise pulse1; no truncated-effort ranking',
        'claim_boundary':'Fixed excitation executability only; no learning benefit, safety, skill or holdout claim'}


def error_record(exc):return {'type':type(exc).__name__,'message':str(exc)}


def run_validation(output,*,protocol_path,synthetic=False):
    if synthetic:
        if GroundBodyEnv is _REAL_ENV:raise RuntimeError('Synthetic requires explicitly replaced backend')
    elif not FORMAL_EXECUTION_FROZEN:raise RuntimeError('Real physics disabled until root freezes this draft')
    output=Path(output)
    if output.exists():raise FileExistsError(output)
    root=next(p for p in Path(__file__).resolve().parents if (p/'pyproject.toml').is_file())
    protocol_path=Path(protocol_path).resolve()
    if protocol_path!=(root/PROTOCOL_PATH).resolve() or not protocol_path.is_file():raise ValueError('Exact declared protocol required')
    plans=[{'trial_id':f'pulse{pulse}_seed{seed}_calibration','seed':seed,'reset_seed':RESET_SEEDS[seed],
            'pulse_steps':pulse,'zero_steps_per_half':10-pulse,'maximum_control_steps':500}
           for pulse in PULSES for seed in SEEDS]
    episodes=[{**p,'status':'planned','completed':False,'reason':None,'study_abort':None,
        'control_calls_attempted':0,'control_steps':0,'physics_steps':0,'model_updates':0,
        'phase_budgets':{phase:dict(control_calls_attempted=0,control_steps=0,physics_steps=0) for phase in PHASES}} for p in plans]
    sources=[Path(__file__),protocol_path,MODEL_PATH,root/'src/developmental_physics/environment.py',
             root/'src/developmental_physics/probes.py',root/'src/developmental_physics/collect.py',root/'pyproject.toml']
    if not synthetic:sources.append(root/AUDITOR_PATH)
    source_bytes={p.relative_to(root).as_posix():p.read_bytes() for p in sources}
    metadata={'schema_version':1,'created_at_utc':datetime.now(timezone.utc).isoformat(),
        'suite':'pair_calibration_feasibility','purpose':__doc__,'synthetic':synthetic,
        'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),
        'source_status':subprocess.check_output(['git','status','--porcelain','--untracked-files=all'],cwd=root,text=True),
        'source_sha256':{n:hashlib.sha256(b).hexdigest() for n,b in source_bytes.items()},
        'protocol':{'path':protocol_path.relative_to(root).as_posix(),'sha256':_hash(protocol_path)},
        'backend':'synthetic, no physics' if synthetic else 'MuJoCo CPU','gpu':None,
        'dependencies':dict(sorted((d.metadata['Name'],d.version) for d in importlib.metadata.distributions())),
        'environment_config':asdict(ExplorationConfig()),'pose':'supine','joint_indices':[0,1],
        'native_joint_count':8,'development_seeds':list(SEEDS),'pulses':list(PULSES),
        'reset_seed_semantics':'Same fixed previously disclosed SeedSequence-derived reset per seed, fresh environment per trial',
        'prefix_steps':100,'active_steps':400,'amplitudes_nm':list(AMPLITUDES),
        'calibration_schedule':'20 blocks: five shoulder, five elbow, five same-direction, five opposite; pulse/zero/pulse/zero in each 20-step block',
        'maximum_control_steps':3000,'maximum_physics_steps':30000,'model_updates':0,
        'planned_requested_effort_per_axis':{'2':{'absolute_nm_s':.36,'squared_nm2_s':.1275},
                                            '1':{'absolute_nm_s':.18,'squared_nm2_s':.06375}},
        'teacher_calls':0,'parameter_updates':0,'policy_parameter_updates':0,'gain_updates':0,
        'selection_rule':'Both predeclared schedules run, no new candidates; select pulse2 if eligible, otherwise pulse1, otherwise blocked',
        'planned_episodes':plans,'complete':False,'archive_status':'running'}
    metadata['source_dirty']=bool(metadata['source_status'])
    if not synthetic:
        if metadata['source_dirty']:raise ValueError('Clean current HEAD required before physical construction')
        for name,data in source_bytes.items():
            if data!=subprocess.check_output(['git','show','HEAD:'+name],cwd=root):
                raise ValueError('Executed source bytes must match clean HEAD: '+name)
    output.mkdir(parents=True)
    with zipfile.ZipFile(output/'source_snapshot.zip','w',zipfile.ZIP_DEFLATED) as z:
        for name,data in source_bytes.items():z.writestr(name,data)
    wall,cpu=time.perf_counter(),time.process_time()
    fatal=None
    def checkpoint():
        metadata.update({key:sum(e[key] for e in episodes) for key in ('control_calls_attempted','control_steps','physics_steps')})
        metadata.update(statuses=dict(Counter(e['status'] for e in episodes)),
            wall_seconds=time.perf_counter()-wall,cpu_seconds=time.process_time()-cpu,
            candidate_selection=choose_candidate(episodes))
        write_errors=[]
        for name,obj in (('episodes.json',episodes),('metadata.json',metadata)):
            try:_write_json(output/name,_archive_record(obj) if isinstance(obj,dict) else [_archive_record(x) for x in obj])
            except BaseException as exc:write_errors.append(exc)
        if write_errors:raise write_errors[0]
    try:
        checkpoint()
        with gzip.open(output/'trace.jsonl.gz','xt',encoding='utf-8') as trace:
            for episode in episodes:
                env=observation=requested=step=qref=directions=None
                phase='prefix';index=None
                calls=returned=written=unreturned=complete_active=known_actual=0
                full_intervals=True;study=error=trace_failure=None
                effort={p:{k:np.zeros(2) for k in EFFORT_KEYS} for p in PHASES}
                selections=None;before_fingerprint=None
                try:
                    env=GroundBodyEnv(ExplorationConfig())
                    observation=env.reset(seed=episode['reset_seed'],pose='supine');native(observation)
                    before_fingerprint=env.parameter_fingerprint()
                    for index in range(500):
                        phase='prefix' if index<100 else 'calibration';step=None
                        requested=np.zeros(8)
                        if index==100:
                            qref,_=native(observation)
                            limits=[env.model.joint(name).range for name in env.joint_names]
                            selections=[direction_record(j,observation['joint_position'],limits) for j in (0,1)]
                            directions=tuple(r['direction'] for r in selections)
                        if index>=100:requested[:2]=pulse_request(index-100,episode['pulse_steps'],directions)
                        previous=observation;calls+=1
                        old_control,old_physics=env.step_id,env.physics_steps
                        b=episode['phase_budgets'][phase];b['control_calls_attempted']+=1
                        try:step=env.step(requested)
                        except BaseException:
                            unreturned+=env.physics_steps-old_physics;raise
                        finally:
                            paid=env.physics_steps-old_physics
                            b['control_steps']+=env.step_id-old_control;b['physics_steps']+=paid
                            effort[phase]['requested_absolute_nm_s']+=np.abs(requested[:2])*paid*env.config.physics_dt
                            effort[phase]['requested_squared_nm2_s']+=requested[:2]**2*paid*env.config.physics_dt
                        observation=step.observation;returned+=1
                        q,v=native(observation)
                        if index>=100:
                            study=study_abort(q,v,qref)
                            if study is not None:study.update(phase=phase,step_index=index)
                        n=step.diagnostics['executed_substeps']
                        if type(n) is not int or n!=paid or not 0<=n<=10:raise RuntimeError('Invalid paid substeps')
                        history=np.asarray(step.diagnostics['applied_torque_history'],dtype=float)
                        if n==0 and history.size==0:history=history.reshape(0,8)
                        if history.shape!=(n,8) or not np.isfinite(history).all() or np.max(np.abs(history),initial=0.)>.5:raise RuntimeError('Invalid native actual history; effort unknown')
                        for key in ('substep_ground_normal_forces','substep_kinetic_energies','substep_minimum_contact_distances'):
                            values=np.asarray(step.diagnostics[key],dtype=float)
                            if values.shape!=(n,) or not np.isfinite(values).all():raise RuntimeError('Missing finite raw telemetry '+key)
                        effort[phase]['actual_absolute_nm_s']+=np.sum(np.abs(history[:,:2]),axis=0)*env.config.physics_dt
                        effort[phase]['actual_squared_nm2_s']+=np.sum(history[:,:2]**2,axis=0)*env.config.physics_dt
                        known_actual+=n
                        full_intervals=full_intervals and n==10
                        if index>=100 and n==10:complete_active+=1
                        row={'trial_id':episode['trial_id'],'seed':episode['seed'],'pulse_steps':episode['pulse_steps'],
                            'step_index':index,'phase':phase,'joint_indices':[0,1],'reference_q':qref,
                            'directions':directions,'requested_torque':requested,'observation_before':previous,
                            'observation_after':observation,'study_abort':study,'diagnostics':step.diagnostics,
                            'qpos':env.data.qpos,'qvel':env.data.qvel,'model_update':None}
                        try:trace.write(json.dumps(_archive_record(row),allow_nan=False)+'\n')
                        except BaseException as exc:trace_failure=exc;raise
                        written+=1
                        if step.terminated or study is not None or n!=10:break
                    if before_fingerprint!=env.parameter_fingerprint():raise RuntimeError('Fixed plant fingerprint changed')
                except BaseException as exc:
                    error=error_record(exc)
                    try:
                        trace.write(json.dumps(_archive_record({'trial_id':episode['trial_id'],'seed':episode['seed'],
                            'pulse_steps':episode['pulse_steps'],'step_index':index,'phase':phase,'collector_exception':error,
                            'requested_torque':requested,'study_abort':study,'model_update':None,
                            **_exception_snapshot(env)}),allow_nan=False)+'\n')
                    except BaseException as write_exc:trace_failure=trace_failure or write_exc
                    fatal=exc
                finally:
                    environment_stop=None if env is None else env.terminated
                    terminated=bool(environment_stop or study is not None)
                    completed=bool(error is None and full_intervals and not terminated and calls==500 and complete_active==400 and written==500)
                    paid_physics=0 if env is None else env.physics_steps
                    final_fingerprint=None;fingerprint_error=None
                    try:final_fingerprint=None if env is None else env.parameter_fingerprint()
                    except BaseException as exc:
                        fingerprint_error=error_record(exc)
                        if fatal is None:fatal=exc;error=error_record(exc);completed=False
                    episode.update(_archive_record({'status':'exception' if error else 'terminated' if terminated else 'completed' if completed else 'incomplete',
                        'completed':completed,'reason':(env.reason if environment_stop else study if study is not None else error),
                        'study_abort':study,'collector_exception':error,'trace_write_failure':None if trace_failure is None else error_record(trace_failure),
                        'environment_terminated':environment_stop,'environment_stop_reason':None if env is None else env.reason,
                        'control_calls_attempted':calls,'control_steps':0 if env is None else env.step_id,'physics_steps':paid_physics,
                        'returned_steps':returned,'written_returned_steps':written,'returned_unwritten_steps':returned-written,
                        'unreturned_physics_steps':unreturned,'complete_active_endpoints':complete_active,
                        'risk_telemetry_complete':error is None and trace_failure is None and unreturned==0,
                        'actual_effort_complete':known_actual==paid_physics,'known_actual_effort_substeps':known_actual,
                        'missing_actual_effort_substeps':paid_physics-known_actual,'actual_effort_is_lower_bound':known_actual!=paid_physics,
                        'reference_q':qref,'direction':directions,'selection_records':selections,'phase_effort':effort,
                        'environment_fingerprint_before':before_fingerprint,
                        'environment_fingerprint_after':final_fingerprint,'final_fingerprint_error':fingerprint_error}))
                    try:checkpoint()
                    except BaseException as exc:
                        metadata['checkpoint_exception']=error_record(exc)
                        episode.update(completed=False,status='exception',checkpoint_write_failure=error_record(exc))
                        if episode.get('collector_exception') is None:episode.update(collector_exception=error_record(exc),reason=error_record(exc))
                        if fatal is None:fatal=exc
                if fatal is not None:raise fatal
        metadata.update(complete=True,archive_status='complete')
    except BaseException as exc:
        fatal=fatal or exc;metadata.update(complete=False,archive_status='interrupted' if isinstance(fatal,(KeyboardInterrupt,SystemExit)) else 'failed',archive_exception=error_record(fatal))
    finally:
        for e in episodes:
            if e['status']=='planned':e.update(status='blocked',reason={'type':'ArchiveAborted','message':'Fatal before planned trial'})
        try:checkpoint()
        except BaseException as exc:
            metadata['final_checkpoint_exception']=error_record(exc)
            if fatal is None:fatal=exc
        try:_write_json(output/'manifest.json',{p.name:_hash(p) for p in sorted(output.iterdir()) if p.is_file() and p.name!='manifest.json'})
        except BaseException as exc:
            metadata['manifest_exception']=error_record(exc)
            if fatal is None:fatal=exc
    if fatal is not None:raise fatal
    return metadata


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--protocol',type=Path,default=Path(PROTOCOL_PATH))
    args=parser.parse_args(argv)
    record=run_validation(args.output,protocol_path=args.protocol)
    print(json.dumps({key:record[key] for key in ('source_commit','archive_status','statuses',
        'control_calls_attempted','control_steps','physics_steps','model_updates','candidate_selection')},indent=2))
    return 0 if record['complete'] and record['candidate_selection']['selected_pulse_steps'] is not None else 1


if __name__=='__main__':raise SystemExit(main())
