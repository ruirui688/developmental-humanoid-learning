"""Independent standard-library audit of finite no-learning pair calibration.

Never imports collector, environment, MuJoCo, NumPy or a body model. Synthetic
records can verify bookkeeping contracts but never receive formal acceptance.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import gzip
import hashlib
import io
import json
import math
from pathlib import Path
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
import zipfile

ROOT=next(p for p in Path(__file__).resolve().parents if (p/'pyproject.toml').is_file())
COLLECTOR='src/developmental_physics/pair_calibration_development.py'
AUDITOR='scripts/audit_pair_calibration.py'
PROTOCOL='docs/PAIR_CALIBRATION_DEVELOPMENT_PROTOCOL.md'
STAGING_COLLECTOR='external/c4d_pair_calibration_staging/calibration_feasibility.py'
STAGING_PROTOCOL='external/c4d_pair_calibration_staging/CALIBRATION_FEASIBILITY_PROTOCOL_DRAFT.md'
ASSET='src/developmental_physics/assets/ground_body.xml'
SHARED=('src/developmental_physics/environment.py','src/developmental_physics/probes.py',
        'src/developmental_physics/collect.py','pyproject.toml',ASSET)
JOINTS=('left_shoulder','left_elbow','right_shoulder','right_elbow','left_hip','left_knee','right_hip','right_knee')
NATIVE={'joint_position':8,'joint_velocity':8,'actuator_torque':8,'previous_command':8,'imu_gyro':3,'imu_acceleration':3}
SEEDS=(0,1,2)
RESET_SEEDS={0:3757552657,1:1641411168,2:2001025171}
PULSES=(2,1)
PHASES=('prefix','calibration')
AMPLITUDES=(.125,.25,.375,.5,.25)
EFFORT=('requested_absolute_nm_s','requested_squared_nm2_s','actual_absolute_nm_s','actual_squared_nm2_s')
CONFIG={'physics_dt':.002,'control_substeps':10,'torque_limit':.5,'joint_speed_limit':20.,
        'joint_limit_margin':.08,'kinetic_energy_limit':50.,'reset_clearance':.005,'ground_contact_profile':'baseline'}


def sha(data):return hashlib.sha256(data).hexdigest()
def file_hash(path):return sha(Path(path).read_bytes())
def finite(x):return type(x) in (int,float) and math.isfinite(x)


class Checks:
    def __init__(self):self.count=0;self.failed=0;self.violations=[];self.maximum_difference=0.
    def check(self,condition,label,detail=None):
        self.count+=1
        if not condition:
            self.failed+=1
            if len(self.violations)<100:self.violations.append({'label':label,'detail':detail})
    def compare(self,a,b,label):
        if isinstance(a,dict):
            self.check(isinstance(b,dict),label+'/dict')
            if isinstance(b,dict):
                for k,v in a.items():
                    self.check(k in b,label+'/'+k+'/present')
                    if k in b:self.compare(v,b[k],label+'/'+k)
        elif isinstance(a,list):
            self.check(isinstance(b,list) and len(a)==len(b),label+'/list')
            if isinstance(b,list) and len(a)==len(b):
                for i,(x,y) in enumerate(zip(a,b)):self.compare(x,y,label+'/'+str(i))
        elif finite(a) and finite(b):
            d=abs(a-b);self.maximum_difference=max(d,self.maximum_difference)
            self.check(d<=1e-10+1e-10*abs(a),label,{'expected':a,'recorded':b})
        else:self.check(a==b,label)


def vector(value,width):
    if not isinstance(value,list) or len(value)!=width or not all(finite(v) for v in value):raise ValueError('Finite vector width '+str(width)+' required')
    return value


def command(active,pulse,directions):
    if type(active) is not int or not 0<=active<400 or type(pulse) is not int or pulse not in PULSES:raise ValueError('Invalid frozen pulse/index')
    if not isinstance(directions,list) or len(directions)!=2 or any(type(s) is not int or s not in (-1,1) for s in directions):raise ValueError('Two integer signed directions required')
    block,slot=divmod(active,20)
    sign=1 if slot<pulse else -1 if 10<=slot<10+pulse else 0
    shape=(1,0) if block<5 else (0,1) if block<10 else (1,1) if block<15 else (1,-1)
    return [directions[i]*shape[i]*AMPLITUDES[block%5]*sign for i in range(2)]+[0.]*6


def guard(q,u,ranges):
    return [0. if ((q[i]<=ranges[i][0]+.03 and u[i]<0) or (q[i]>=ranges[i][1]-.03 and u[i]>0)) else u[i] for i in range(8)]


def study(q,v,qref,index):
    if index<100:return None
    t=[]
    for i in range(2):
        if abs(q[i]-qref[i])>=.12:t.append({'joint_index':i,'signal':'absolute_q_minus_qref_rad'})
        if abs(v[i])>=1.:t.append({'joint_index':i,'signal':'absolute_velocity_rad_s'})
    return None if not t else {'type':'StudyAbort','triggers':t,'q_rad':q[:2],'qref_rad':qref,
        'velocity_rad_s':v[:2],'thresholds':{'absolute_q_minus_qref_rad':.12,'absolute_velocity_rad_s':1.},
        'feedback_action':None,'phase':'calibration','step_index':index}


def new_effort():return {k:[0.,0.] for k in EFFORT}


def add_effort(e,row):
    n=row['diagnostics']['executed_substeps'];u=row['requested_torque']
    for i in range(2):
        e[EFFORT[0]][i]+=abs(u[i])*n*.002;e[EFFORT[1]][i]+=u[i]**2*n*.002
        e[EFFORT[2]][i]+=sum(abs(a[i]) for a in row['diagnostics']['applied_torque_history'])*.002
        e[EFFORT[3]][i]+=sum(a[i]**2 for a in row['diagnostics']['applied_torque_history'])*.002


def parse_asset(data,checks):
    root=ET.fromstring(data);compiler=root.find('compiler');degrees=compiler is None or compiler.get('angle','degree')=='degree'
    mapping={};qpos=0;qvel=0
    for node in root.find('worldbody').iter():
        if node.tag=='freejoint':qpos+=7;qvel+=6
        elif node.tag=='joint':
            kind=node.get('type','hinge');checks.check(kind=='hinge','asset_single_dof/'+str(node.get('name')))
            rr=[float(x) for x in node.get('range').split()]
            if degrees:rr=[math.radians(x) for x in rr]
            mapping[node.get('name')]={'qpos':qpos,'qvel':qvel,'range':rr}
            qpos+=4 if kind=='ball' else 1;qvel+=3 if kind=='ball' else 1
    checks.compare(set(JOINTS),set(mapping),'asset_native_joint_set')
    public_degrees=((-100,100),(0,135),(-100,100),(0,135),(-90,90),(0,135),(-90,90),(0,135))
    for name,limits in zip(JOINTS,public_degrees):checks.compare([math.radians(x) for x in limits],mapping[name]['range'],'asset_frozen_public_range/'+name)
    motors=list(root.find('actuator'));checks.compare(list(JOINTS),[m.get('joint') for m in motors],'asset_motor_native_order')
    default=root.find('default/motor')
    for motor in motors:
        checks.check(motor.tag=='motor','asset_unit_motor_type')
        gear=[float(x) for x in motor.get('gear',default.get('gear','1')).split()]
        ctrl=[float(x) for x in motor.get('ctrlrange',default.get('ctrlrange')).split()]
        checks.compare([1.],gear,'asset_unit_gear');checks.compare([-.5,.5],ctrl,'asset_shared_permission')
    return [mapping[n] for n in JOINTS],qpos,qvel


def direction_records(q,ranges):
    out=[]
    for i in (0,1):
        lower,upper=ranges[i];positive=upper-q[i];negative=q[i]-lower
        out.append({'joint_index':i,'joint_position_rad':q[i],'lower_limit_rad':lower,'upper_limit_rad':upper,
            'positive_room_rad':positive,'negative_room_rad':negative,'direction':1 if positive>=negative else -1,
            'rule':'larger distance to the public joint limit; ties choose positive'})
    return out


def selection(derived):
    groups=[]
    for pulse in PULSES:
        rows=[e for e in derived if e['pulse_steps']==pulse]
        eligible=len(rows)==3 and {r['seed'] for r in rows}==set(SEEDS) and all(r['independent_complete'] for r in rows)
        groups.append({'pulse_steps':pulse,'zero_steps_per_half':10-pulse,'eligible':eligible,'trial_ids':[r['trial_id'] for r in rows]})
    selected=next((g['pulse_steps'] for g in groups if g['eligible']),None)
    return {'candidates':groups,'selected_pulse_steps':selected,'status':'eligible' if selected is not None else 'blocked'}


def reconcile_effort(recorded,observed,paid,raw_substeps,measured,exception_commands,checks,label):
    missing=paid-raw_substeps;expected={k:v.copy() for k,v in observed.items()}
    recoverable=missing==0 or (0<missing<=10 and len(exception_commands)==1)
    if missing>0 and recoverable:
        u=vector(exception_commands[0],8)
        for i in range(2):expected[EFFORT[0]][i]+=abs(u[i])*missing*.002;expected[EFFORT[1]][i]+=u[i]**2*missing*.002
    checks.check(type(measured) is int and raw_substeps<=measured<=paid,label+'/measured_bounds')
    checks.compare(set(EFFORT),set(recorded),label+'/exact_keys')
    for key in EFFORT:
        vector(recorded[key],2);checks.check(all(v>=0 for v in recorded[key]),label+'/'+key+'/nonnegative')
    if recoverable:
        for key in EFFORT[:2]:checks.compare(expected[key],recorded[key],label+'/'+key)
    for key,bound in zip(EFFORT[2:],(.5,.25)):
        for i in range(2):
            extra=max(0,measured-raw_substeps)
            checks.check(expected[key][i]-1e-10<=recorded[key][i]<=expected[key][i]+bound*extra*.002+1e-10,label+'/'+key+'/'+str(i)+'/actual_bound')
            if missing==0:checks.compare(expected[key][i],recorded[key][i],label+'/'+key+'/'+str(i))
    return {'raw_effort':expected,'requested_reconstruction_complete':recoverable,'raw_actual_reconstruction_complete':missing==0,
            'raw_actual_is_lower_bound':missing>0,'unreconstructed_physics_substeps':missing,'collector_measured_substeps':measured}


def verify_native(observation,checks,label):
    checks.compare(set(NATIVE),set(observation),label+'/native_whitelist')
    for key,width in NATIVE.items():vector(observation[key],width)


def verify_encoder(observation,qpos,qvel,mapping,nq,nv,checks,label):
    qpos,qvel=vector(qpos,nq),vector(qvel,nv)
    for i,m in enumerate(mapping):
        checks.compare(qpos[m['qpos']],observation['joint_position'][i],label+'/encoder_q/'+str(i))
        checks.compare(qvel[m['qvel']],observation['joint_velocity'][i],label+'/encoder_v/'+str(i))


def verify_row(row,previous,counters,mapping,nq,nv,checks,label,synthetic_fixture):
    before,after=row['observation_before'],row['observation_after']
    for obs in (before,after):verify_native(obs,checks,label)
    if previous is not None:checks.compare(previous,before,label+'/native_continuity')
    verify_encoder(after,row['qpos'],row['qvel'],mapping,nq,nv,checks,label)
    u=vector(row['requested_torque'],8);checks.check(all(abs(x)<=.5 for x in u[:2]) and all(x==0. for x in u[2:]),label+'/shared_permissions')
    d=row['diagnostics'];n=d['executed_substeps']
    checks.check(type(n) is int and 0<=n<=10,label+'/paid_interval')
    checks.check(type(d.get('terminated')) is bool,label+'/environment_stop_boolean')
    checks.check((d.get('reason') is not None)==d.get('terminated'),label+'/environment_stop_reason_latched')
    if not synthetic_fixture:checks.check(n==10 or d['terminated'],label+'/physical_partial_stop_latched')
    counters['physics']+=n
    checks.compare(row['step_index']+1,d.get('step_id'),label+'/step_counter')
    checks.compare(counters['physics'],d.get('physics_steps'),label+'/physics_counter')
    checks.compare(counters['physics']*.002,d.get('time'),label+'/physical_time')
    checks.compare(u,d.get('requested_torque'),label+'/diagnostic_request');checks.compare(u,d.get('accepted_torque'),label+'/accepted')
    h=d['applied_torque_history'];checks.compare(n,len(h),label+'/history_length')
    for a in h:
        vector(a,8);checks.check(all(v in (0.,u[i]) for i,v in enumerate(a)),label+'/shield_preserves_or_zeroes')
    screened=sum(any(a[i]!=u[i] for i in range(8)) for a in h)
    checks.compare(screened,d.get('guarded_substeps'),label+'/guard_count')
    if h:
        checks.compare(guard(before['joint_position'],u,[m['range'] for m in mapping]),h[0],label+'/first_substep_public_guard')
        checks.compare(h[-1],d.get('applied_torque'),label+'/last_actual')
        checks.compare(h[-1],after['actuator_torque'],label+'/native_torque_feedback')
        checks.compare(u,after['previous_command'],label+'/known_accepted_history')
    else:checks.compare(before['previous_command'],after['previous_command'],label+'/zero_paid_no_new_acceptance')
    for key in ('substep_ground_normal_forces','substep_kinetic_energies','substep_minimum_contact_distances'):vector(d[key],n)
    force,energy,dist=d['substep_ground_normal_forces'],d['substep_kinetic_energies'],d['substep_minimum_contact_distances']
    checks.check(all(v>=0 for v in force+energy),label+'/nonnegative_force_energy')
    checks.compare(max(force,default=0.),d.get('peak_substep_ground_normal_force'),label+'/force_peak')
    checks.compare(sum(force)*.002,d.get('ground_normal_impulse_ns'),label+'/impulse')
    checks.compare(max(energy,default=0.),d.get('peak_substep_kinetic_energy'),label+'/energy_peak')
    checks.compare(min(dist,default=0.),d.get('minimum_substep_contact_distance'),label+'/penetration')
    return n


def audit_archive(path,checks,*,git_root,synthetic_fixture,expected_source_commit,synthetic_source_layout):
    path=Path(path);files={p.name:p.read_bytes() for p in path.iterdir() if p.is_file()}
    required={'metadata.json','episodes.json','manifest.json','source_snapshot.zip','trace.jsonl.gz'}
    checks.compare(required,set(files),'archive_exact_files')
    m=json.loads(files['metadata.json']);episodes=json.loads(files['episodes.json']);manifest=json.loads(files['manifest.json'])
    hashes={name:sha(b) for name,b in files.items()}
    checks.compare(required-{'manifest.json'},set(manifest),'manifest_exact_members')
    for name,value in manifest.items():checks.compare(value,hashes[name],'manifest/'+name)
    checks.compare(synthetic_fixture,m['synthetic'],'declared_synthetic_fixture')
    checks.compare('synthetic, no physics' if synthetic_fixture else 'MuJoCo CPU',m['backend'],'backend')
    checks.compare(CONFIG,m['environment_config'],'frozen_config')
    checks.compare(set(CONFIG),set(m['environment_config']),'exact_environment_config_fields')
    for key,value in {'suite':'pair_calibration_feasibility','gpu':None,'pose':'supine','joint_indices':[0,1],
            'native_joint_count':8,'development_seeds':list(SEEDS),'pulses':list(PULSES),'prefix_steps':100,'active_steps':400,
            'amplitudes_nm':list(AMPLITUDES),'maximum_control_steps':3000,'maximum_physics_steps':30000,
            'model_updates':0,'teacher_calls':0,'parameter_updates':0,'policy_parameter_updates':0,'gain_updates':0}.items():checks.compare(value,m[key],'metadata/'+key)
    source_commit=m['source_commit'];checks.check(bool(re.fullmatch('[0-9a-f]{40}',source_commit)),'source_commit_sha')
    if expected_source_commit is not None:checks.compare(expected_source_commit,source_commit,'expected_preregistered_commit')
    if not synthetic_fixture:
        checks.check(expected_source_commit is not None,'formal_commit_predeclared')
        checks.check(git_root is not None,'formal_git_verification_enabled')
        checks.compare(False,m['source_dirty'],'formal_clean');checks.compare('',m['source_status'],'formal_status')
    if synthetic_source_layout not in ('staging','formal'):
        raise ValueError('Synthetic source layout must be staging or formal')
    if not synthetic_fixture and synthetic_source_layout!='staging':
        raise ValueError('Source-layout override is synthetic-only')
    use_formal_paths=not synthetic_fixture or synthetic_source_layout=='formal'
    collector=COLLECTOR if use_formal_paths else STAGING_COLLECTOR
    protocol=PROTOCOL if use_formal_paths else STAGING_PROTOCOL
    expected_sources=set(SHARED)|{collector,protocol}
    if use_formal_paths:expected_sources.add(AUDITOR)
    with zipfile.ZipFile(io.BytesIO(files['source_snapshot.zip'])) as z:
        checks.check(len(z.namelist())==len(set(z.namelist())),'source_zip_unique_names')
        checks.compare(expected_sources,set(z.namelist()),'source_zip_exact_source_set')
        checks.compare(set(m['source_sha256']),set(z.namelist()),'source_zip_metadata_members')
        members={name:z.read(name) for name in z.namelist()}
        for name,b in members.items():
            checks.check(not Path(name).is_absolute() and '..' not in Path(name).parts,'source_safe_path/'+name)
            checks.compare(m['source_sha256'][name],sha(b),'source_zip_hash/'+name)
            if git_root is not None:
                committed=subprocess.check_output(['git','show',source_commit+':'+name],cwd=git_root)
                checks.compare(sha(committed),sha(b),'source_git_blob/'+name)
        checks.compare({'path':protocol,'sha256':sha(members[protocol])},m['protocol'],'protocol_binding')
        if use_formal_paths:checks.compare(file_hash(__file__),sha(members[AUDITOR]),'executed_auditor_matches_frozen_source')
        mapping,nq,nv=parse_asset(members[ASSET],checks)
    planned=[]
    for pulse in PULSES:
        directions=[1,1];e=new_effort()
        for active in range(400):
            u=command(active,pulse,directions)
            for i in range(2):e[EFFORT[0]][i]+=abs(u[i])*.02;e[EFFORT[1]][i]+=u[i]**2*.02
        expected={'absolute_nm_s':.36 if pulse==2 else .18,'squared_nm2_s':.1275 if pulse==2 else .06375}
        checks.compare(expected,m['planned_requested_effort_per_axis'][str(pulse)],'planned_effort_metadata/'+str(pulse))
        for i in range(2):checks.compare(expected['absolute_nm_s'],e[EFFORT[0]][i],'planned_abs/'+str(pulse)+'/'+str(i));checks.compare(expected['squared_nm2_s'],e[EFFORT[1]][i],'planned_sq/'+str(pulse)+'/'+str(i))
        for seed in SEEDS:planned.append({'trial_id':f'pulse{pulse}_seed{seed}_calibration','seed':seed,'reset_seed':RESET_SEEDS[seed],
            'pulse_steps':pulse,'zero_steps_per_half':10-pulse,'maximum_control_steps':500})
    checks.compare(planned,m['planned_episodes'],'planned_matrix');checks.compare([p['trial_id'] for p in planned],[e['trial_id'] for e in episodes],'episode_order')
    raw=[json.loads(line) for line in gzip.decompress(files['trace.jsonl.gz']).decode().splitlines() if line]
    grouped=defaultdict(list)
    for row in raw:grouped[row['trial_id']].append(row)
    checks.check(set(grouped)<=set(p['trial_id'] for p in planned),'no_unplanned_interactions')
    derived=[];fatal_seen=False
    for ep,plan in zip(episodes,planned):
        tid=ep['trial_id'];checks.compare(plan,ep,tid+'/plan');rows=grouped.get(tid,[])
        regular=[r for r in rows if 'observation_before' in r];exceptions=[r for r in rows if 'collector_exception' in r]
        checks.check(len(exceptions)<=1,tid+'/one_exception_record')
        for key in ('control_calls_attempted','control_steps','physics_steps'):
            checks.check(type(ep[key]) is int and 0<=ep[key]<=(5000 if key=='physics_steps' else 500),tid+'/budget_cap/'+key)
        checks.compare(0,ep['model_updates'],tid+'/zero_learning')
        if ep['status']=='blocked':
            checks.check(fatal_seen,tid+'/blocked_only_after_fatal');checks.compare(0,len(rows),tid+'/blocked_no_raw')
            checks.compare({'control_calls_attempted':0,'control_steps':0,'physics_steps':0},ep,tid+'/blocked_zero_cost')
            checks.compare(False,ep['completed'],tid+'/blocked_not_complete');checks.compare(None,ep['study_abort'],tid+'/blocked_no_study')
            for phase in PHASES:checks.compare({'control_calls_attempted':0,'control_steps':0,'physics_steps':0},ep['phase_budgets'][phase],tid+'/blocked_phase/'+phase)
            derived.append({**plan,'independent_complete':False,'status':'blocked','reason':ep['reason']});continue
        checks.check(not fatal_seen,tid+'/no_execution_after_fatal')
        if ep['status']=='exception':fatal_seen=True
        checks.compare(list(range(len(regular))),[r['step_index'] for r in regular],tid+'/contiguous_returned')
        checks.compare(len(regular),ep['written_returned_steps'],tid+'/written_count')
        checks.compare(ep['returned_steps']-len(regular),ep['returned_unwritten_steps'],tid+'/returned_unwritten')
        checks.check(len(regular)<=ep['returned_steps']<=ep['control_steps']<=ep['control_calls_attempted']<=len(regular)+1,tid+'/attempted_returned_gap')
        previous=None;counters={'physics':0};phase_counts=Counter();phase_physics=Counter();efforts={p:new_effort() for p in PHASES}
        full_active=0;terminal_seen=False;stop=None;reference=None;directions=None
        for row in regular:
            index=row['step_index'];phase='prefix' if index<100 else 'calibration';label=tid+':'+str(index)
            checks.compare({'trial_id':tid,'seed':ep['seed'],'pulse_steps':ep['pulse_steps'],'phase':phase,'joint_indices':[0,1],'model_update':None},row,label+'/labels')
            checks.check(not terminal_seen,label+'/no_step_after_terminal')
            n=verify_row(row,previous,counters,mapping,nq,nv,checks,label,synthetic_fixture)
            if index==100:
                reference=row['observation_before']['joint_position'][:2]
                selections=direction_records(row['observation_before']['joint_position'],[x['range'] for x in mapping])
                directions=[s['direction'] for s in selections]
                checks.compare(reference,ep['reference_q'],tid+'/native_qref_no_clip');checks.compare(directions,ep['direction'],tid+'/native_directions')
                checks.compare(selections,ep['selection_records'],tid+'/public_selection')
            request=[0.]*8 if index<100 else command(index-100,ep['pulse_steps'],directions)
            checks.compare(request,row['requested_torque'],label+'/fixed_command')
            checks.compare(None if index<100 else reference,row['reference_q'],label+'/row_qref')
            checks.compare(None if index<100 else directions,row['directions'],label+'/row_directions')
            expected_stop=None if index<100 else study(row['observation_after']['joint_position'],row['observation_after']['joint_velocity'],reference,index)
            checks.compare(expected_stop,row['study_abort'],label+'/study')
            if expected_stop is not None:stop=expected_stop
            terminal_seen=bool(expected_stop is not None or row['diagnostics'].get('terminated') or n!=10)
            phase_counts[phase]+=1;phase_physics[phase]+=n;add_effort(efforts[phase],row)
            if phase=='calibration' and n==10:full_active+=1
            previous=row['observation_after']
        if reference is None and ep.get('reference_q') is not None:
            checks.check(len(regular)==100 and previous is not None,tid+'/native_reference_available_before_failed_active')
            reference=previous['joint_position'][:2]
            selections=direction_records(previous['joint_position'],[x['range'] for x in mapping])
            directions=[s['direction'] for s in selections]
            checks.compare(reference,ep['reference_q'],tid+'/failed_native_qref_no_clip')
            checks.compare(directions,ep['direction'],tid+'/failed_native_directions')
            checks.compare(selections,ep['selection_records'],tid+'/failed_public_selection')
        missing=ep['physics_steps']-counters['physics'];checks.check(0<=missing<=10,tid+'/missing_paid_bounds')
        checks.check(ep['unreturned_physics_steps']<=missing and ep['unreturned_physics_steps']>=0,tid+'/unreturned_paid_bounds')
        checks.compare(missing if ep['returned_unwritten_steps']==0 else 0,ep['unreturned_physics_steps'],tid+'/paid_unreturned_reconciliation')
        measured=ep['known_actual_effort_substeps'];checks.check(counters['physics']<=measured<=ep['physics_steps'],tid+'/known_actual_bounds')
        checks.compare(ep['physics_steps']-measured,ep['missing_actual_effort_substeps'],tid+'/missing_actual')
        checks.compare(measured==ep['physics_steps'],ep['actual_effort_complete'],tid+'/actual_complete')
        checks.compare(measured!=ep['physics_steps'],ep['actual_effort_is_lower_bound'],tid+'/actual_lower_bound')
        missing_full_measured=bool(ep['returned_unwritten_steps']==1 and missing==10 and measured-counters['physics']==10
            and ep.get('trace_write_failure') is not None and len(regular)>=100)
        full_active+=int(missing_full_measured)
        checks.compare(full_active,ep['complete_active_endpoints'],tid+'/complete_active_count')
        checks.check(type(ep['environment_terminated']) is bool,tid+'/environment_stop_boolean')
        if exceptions:
            excrow=exceptions[0];index=excrow['step_index'];phase='prefix' if index<100 else 'calibration'
            checks.compare({'trial_id':tid,'seed':ep['seed'],'pulse_steps':ep['pulse_steps'],'phase':phase},excrow,tid+'/exception_labels')
            checks.check(index in (len(regular)-1,len(regular)),tid+'/exception_index_matches_latest_call')
            request=[0.]*8 if index<100 else command(index-100,ep['pulse_steps'],directions)
            checks.compare(request,excrow['requested_torque'],tid+'/exception_fixed_request')
            if 'observation_after' in excrow:
                obs=excrow['observation_after'];verify_native(obs,checks,tid+'/exception_endpoint')
                if 'qpos' in excrow and 'qvel' in excrow:verify_encoder(obs,excrow['qpos'],excrow['qvel'],mapping,nq,nv,checks,tid+'/exception_endpoint')
                if ep['returned_unwritten_steps']==1 and index>=100:stop=study(obs['joint_position'],obs['joint_velocity'],reference,index)
                if index==len(regular)-1 and previous is not None:checks.compare(previous,obs,tid+'/exception_duplicates_last_endpoint')
            if 'diagnostics' in excrow:
                d=excrow['diagnostics']
                checks.compare(ep['control_steps'],d.get('step_id'),tid+'/exception_control_counter')
                checks.compare(ep['physics_steps'],d.get('physics_steps'),tid+'/exception_physics_counter')
                checks.compare(ep['physics_steps']*.002,d.get('time'),tid+'/exception_physical_time')
            checks.compare(stop,excrow['study_abort'],tid+'/exception_study')
        checks.compare(stop,ep['study_abort'],tid+'/study_endpoint')
        risk_read_complete=bool((ep.get('collector_exception') is None or (ep.get('checkpoint_write_failure') is not None
            and not exceptions and len(regular)==500)) and ep.get('trace_write_failure') is None and ep['unreturned_physics_steps']==0)
        checks.compare(risk_read_complete,
            ep['risk_telemetry_complete'],tid+'/risk_raw_complete')
        if regular and missing==0:
            checks.compare(regular[-1]['diagnostics']['terminated'],ep['environment_terminated'],tid+'/final_environment_stop')
            checks.compare(regular[-1]['diagnostics']['reason'],ep['environment_stop_reason'],tid+'/final_environment_stop_reason')
        rec=[]
        for phase in PHASES:
            b=ep['phase_budgets'][phase];cap=100 if phase=='prefix' else 400
            checks.check(all(type(b[k]) is int and 0<=b[k]<=(cap*10 if k=='physics_steps' else cap) for k in ('control_calls_attempted','control_steps','physics_steps')),tid+'/phase_cap/'+phase)
            checks.check(phase_counts[phase]<=b['control_steps']<=b['control_calls_attempted']<=phase_counts[phase]+1,tid+'/phase_counts/'+phase)
            missing_phase=b['physics_steps']-phase_physics[phase];checks.check(0<=missing_phase<=10,tid+'/phase_missing/'+phase)
            cmds=[r['requested_torque'] for r in exceptions if r['phase']==phase and missing_phase>0]
            rec.append(reconcile_effort(ep['phase_effort'][phase],efforts[phase],b['physics_steps'],phase_physics[phase],
                phase_physics[phase]+(measured-counters['physics'] if missing_phase else 0),cmds,checks,tid+'/effort/'+phase))
        for key in ('control_calls_attempted','control_steps','physics_steps'):checks.compare(ep[key],sum(b[key] for b in ep['phase_budgets'].values()),tid+'/phase_total/'+key)
        exception=ep.get('collector_exception')
        if exception is not None:checks.check(ep['status']=='exception',tid+'/exception_status')
        if exceptions:
            checks.compare(exception,exceptions[0]['collector_exception'],tid+'/primary_exception_preserved')
            checks.compare(None,exceptions[0]['model_update'],tid+'/exception_no_learning')
        complete=bool(len(regular)==500 and full_active==400 and counters['physics']==5000 and not terminal_seen
            and exception is None and ep.get('trace_write_failure') is None and ep.get('checkpoint_write_failure') is None
            and ep.get('environment_terminated') is False and ep.get('risk_telemetry_complete') is True
            and measured==5000 and ep.get('environment_fingerprint_before') is not None
            and ep.get('environment_fingerprint_before')==ep.get('environment_fingerprint_after'))
        checks.compare(complete,ep['completed'],tid+'/completion')
        expected_status='exception' if exception is not None else 'terminated' if stop is not None or ep.get('environment_terminated') else 'completed' if complete else 'incomplete'
        checks.compare(expected_status,ep['status'],tid+'/status')
        if ep.get('environment_terminated'):checks.compare(ep['environment_stop_reason'],ep['reason'],tid+'/environment_reason_priority')
        elif stop is not None:checks.compare(stop,ep['reason'],tid+'/study_reason')
        derived.append({**plan,'status':ep['status'],'independent_complete':complete,'study_abort':stop,
            'paid_budget':{k:ep[k] for k in ('control_calls_attempted','control_steps','physics_steps')},
            'complete_active_endpoints':full_active,'raw_returned_rows':len(regular),'raw_physics_substeps':counters['physics'],
            'unreconstructed_physics_substeps':missing,'effort_audit':rec,
            'guard_validation':'First returned substep exact from native start q/public XML limits; later command-domain and guard-count checks. No pre-substep-q telemetry for full angle replay.'})
    totals={k:sum(e[k] for e in episodes) for k in ('control_calls_attempted','control_steps','physics_steps')}
    for k,v in totals.items():checks.compare(v,m[k],'batch_budget/'+k)
    checks.compare(dict(Counter(e['status'] for e in episodes)),m['statuses'],'batch_statuses')
    checks.compare(not fatal_seen,m['complete'],'archive_executed_all_predeclared_trials')
    if fatal_seen:
        checks.check(m['archive_status'] in ('failed','interrupted'),'fatal_archive_status')
        checks.check(m.get('archive_exception') is not None,'fatal_archive_original_exception')
    else:checks.compare('complete',m['archive_status'],'complete_archive_status')
    independent=selection(derived)
    checks.compare(independent,m['candidate_selection'],'candidate_selection')
    return {'budget':totals,'episodes':derived,'candidate_selection':independent,'input_hashes':hashes,
        'source_commit':source_commit,'native_joint_order':list(JOINTS),'asset_native_mapping':mapping,
        'synthetic_fixture':synthetic_fixture,'source_git_verification_enabled':git_root is not None,
        'archive_complete':m['complete'],'model_updates':0,'actual_physical_calls_in_audit':0}


def audit(path,*,git_root=ROOT,synthetic_fixture=False,expected_source_commit=None,synthetic_source_layout='staging'):
    wall,cpu=time.perf_counter(),time.process_time();checks=Checks();result=None
    try:result=audit_archive(path,checks,git_root=git_root,synthetic_fixture=synthetic_fixture,expected_source_commit=expected_source_commit,synthetic_source_layout=synthetic_source_layout)
    except (OSError,ValueError,KeyError,TypeError,IndexError,AttributeError,OverflowError,zipfile.BadZipFile,ET.ParseError,subprocess.CalledProcessError) as exc:
        checks.check(False,'archive_schema_or_read_error',{'type':type(exc).__name__,'message':str(exc)})
    verified=checks.failed==0
    validated=bool(verified and result is not None and not synthetic_fixture and git_root is not None
        and expected_source_commit is not None and result['archive_complete'] and result['candidate_selection']['selected_pulse_steps'] is not None)
    return {'schema_version':1,'created_at_utc':datetime.now(timezone.utc).isoformat(),'audit_script_sha256':file_hash(__file__),
        'audit_spec':{'collector':COLLECTOR,'auditor':AUDITOR,'protocol':PROTOCOL,'pulses':list(PULSES),'seeds':list(SEEDS),
            'max_calls':3000,'max_substeps':30000,'expected_source_commit':expected_source_commit,'synthetic_fixture':synthetic_fixture,'synthetic_source_layout':synthetic_source_layout},
        'checks':checks.count,'failed':checks.failed,'violations':checks.violations,'violations_truncated':checks.failed>len(checks.violations),
        'maximum_recomputation_difference':checks.maximum_difference,'archive':result,
        'data_consistency_verified':verified,'validated_eligible':validated,'formal_execution_accepted':validated,
        'claim_boundary':'Finite fixed calibration executability only. Synthetic is never formally accepted; no model learning, safety or skill claim.',
        'execution':{'wall_seconds':time.perf_counter()-wall,'cpu_seconds':time.process_time()-cpu,'physical_calls':0,
            'model_updates':0,'new_predictions':0,'third_party_imports':[],'python':sys.version}}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('archive',type=Path);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--source-commit');parser.add_argument('--synthetic-fixture',action='store_true');parser.add_argument('--no-git-verification',action='store_true')
    parser.add_argument('--synthetic-source-layout',choices=('staging','formal'),default='staging',help='Explicit synthetic ZIP member layout; formal verification unchanged')
    args=parser.parse_args()
    if args.output.exists():raise FileExistsError(args.output)
    result=audit(args.archive,git_root=None if args.no_git_verification else ROOT,synthetic_fixture=args.synthetic_fixture,expected_source_commit=args.source_commit,synthetic_source_layout=args.synthetic_source_layout)
    with args.output.open('x',encoding='utf-8',newline='\n') as f:json.dump(result,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')
    print(json.dumps({'checks':result['checks'],'failed':result['failed'],'validated_eligible':result['validated_eligible'],'audit_sha256':result['audit_script_sha256']}))
    return int(result['failed']!=0)


if __name__=='__main__':raise SystemExit(main())
