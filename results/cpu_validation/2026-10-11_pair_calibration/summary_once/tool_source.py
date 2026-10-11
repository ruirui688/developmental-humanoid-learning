"""One standard-library descriptive recomputation; no audit/model/physics calls."""
from collections import Counter, defaultdict
from datetime import datetime, timezone
import gzip
import hashlib
import json
import math
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parent.parent
RAW=ROOT/'external/pair_calibration_20261011_first'
AUDIT=ROOT/'external/pair_calibration_20261011_first_audit.json'
OUTPUT=ROOT/'external/pair_calibration_20261011_summary_01'
SOURCE_COMMIT='86453c1280c986748717ca79ae4d4d3d45b52973'
EFFORT=('requested_absolute_nm_s','requested_squared_nm2_s','actual_absolute_nm_s','actual_squared_nm2_s')
JOINTS=('left_shoulder','left_elbow')
PHASES=('prefix','calibration')

def sha(data):return hashlib.sha256(data).hexdigest()
def save(path,obj):
    with path.open('x',encoding='utf-8',newline='\n') as f:
        json.dump(obj,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')

class Checks:
    def __init__(self):self.count=0;self.failed=0;self.violations=[];self.maximum_difference=0.
    def check(self,condition,label):
        self.count+=1
        if not condition:
            self.failed+=1
            if len(self.violations)<100:self.violations.append(label)
    def compare(self,a,b,label):
        if isinstance(a,dict):
            self.check(isinstance(b,dict),label+'/dict')
            if isinstance(b,dict):
                for k,v in a.items():self.check(k in b,label+'/'+k+'/present');self.compare(v,b.get(k),label+'/'+k)
        elif isinstance(a,list):
            self.check(isinstance(b,list) and len(a)==len(b),label+'/list')
            if isinstance(b,list) and len(a)==len(b):
                for i,(x,y) in enumerate(zip(a,b)):self.compare(x,y,label+'/'+str(i))
        elif type(a) in (int,float) and type(b) in (int,float) and math.isfinite(a) and math.isfinite(b):
            diff=abs(a-b);self.maximum_difference=max(diff,self.maximum_difference);self.check(diff<=1e-10+abs(a)*1e-10,label)
        else:self.check(a==b,label)

def command(index,pulse,directions):
    if index<100:return [0.]*8
    block,slot=divmod(index-100,20)
    sign=1 if slot<pulse else -1 if 10<=slot<10+pulse else 0
    shape=(1,0) if block<5 else (0,1) if block<10 else (1,1) if block<15 else (1,-1)
    amp=(.125,.25,.375,.5,.25)[block%5]
    return [directions[i]*shape[i]*amp*sign for i in (0,1)]+[0.]*6

def stopped(row):
    if row['step_index']<100:return None
    q=row['observation_after']['joint_position'][:2];v=row['observation_after']['joint_velocity'][:2];ref=row['reference_q']
    triggers=[]
    for i in (0,1):
        if abs(q[i]-ref[i])>=.12:triggers.append({'joint_index':i,'signal':'absolute_q_minus_qref_rad'})
        if abs(v[i])>=1.:triggers.append({'joint_index':i,'signal':'absolute_velocity_rad_s'})
    return None if not triggers else {'type':'StudyAbort','triggers':triggers,'q_rad':q,'qref_rad':ref,'velocity_rad_s':v,
        'thresholds':{'absolute_q_minus_qref_rad':.12,'absolute_velocity_rad_s':1.},'feedback_action':None,
        'phase':'calibration','step_index':row['step_index']}

def new_effort():return {key:[0.,0.] for key in EFFORT}

def summarize(files,audit_bytes,checks):
    metadata=json.loads(files['metadata.json']);episodes=json.loads(files['episodes.json']);audit=json.loads(audit_bytes)
    checks.compare(SOURCE_COMMIT,metadata['source_commit'],'source_commit')
    checks.compare({'failed':0,'data_consistency_verified':True},audit,'existing_audit_claim')
    checks.compare(0,metadata['model_updates'],'no_updates')
    planned=[f'pulse{p}_seed{s}_calibration' for p in (2,1) for s in (0,1,2)]
    checks.compare(planned,[e['trial_id'] for e in episodes],'six_trial_order')
    rows=[json.loads(line) for line in gzip.decompress(files['trace.jsonl.gz']).decode().splitlines() if line]
    grouped=defaultdict(list)
    for row in rows:grouped[row['trial_id']].append(row)
    checks.compare(set(planned),set(grouped),'six_trial_raw_groups')
    summary=[]
    for ep in episodes:
        tid=ep['trial_id'];regular=[r for r in grouped[tid] if 'observation_before' in r]
        exception_rows=[r for r in grouped[tid] if 'collector_exception' in r]
        checks.compare(0,len(exception_rows),tid+'/raw_no_exception')
        phases={p:{'control_calls_attempted':0,'control_steps':0,'physics_steps':0} for p in PHASES}
        efforts={p:new_effort() for p in PHASES};guards=0;screened=[0,0];nonzero_requested=[0,0];nonzero_actual=[0,0]
        complete_active=partial=0;stop=None
        for index,row in enumerate(regular):
            phase='prefix' if index<100 else 'calibration';n=row['diagnostics']['executed_substeps']
            checks.compare({'step_index':index,'phase':phase},row,tid+':'+str(index)+'/timing')
            checks.compare(command(index,ep['pulse_steps'],row['directions']),row['requested_torque'],tid+':'+str(index)+'/fixed_command')
            checks.compare(n,len(row['diagnostics']['applied_torque_history']),tid+':'+str(index)+'/paid_history')
            phases[phase]['control_calls_attempted']+=1;phases[phase]['control_steps']+=1;phases[phase]['physics_steps']+=n
            screened_any=sum(any(a[i]!=row['requested_torque'][i] for i in range(8)) for a in row['diagnostics']['applied_torque_history'])
            checks.compare(screened_any,row['diagnostics']['guarded_substeps'],tid+':'+str(index)+'/screened_count');guards+=screened_any
            for axis in (0,1):
                u=row['requested_torque'][axis];a=[x[axis] for x in row['diagnostics']['applied_torque_history']]
                efforts[phase][EFFORT[0]][axis]+=abs(u)*n*.002;efforts[phase][EFFORT[1]][axis]+=u*u*n*.002
                efforts[phase][EFFORT[2]][axis]+=sum(abs(x) for x in a)*.002;efforts[phase][EFFORT[3]][axis]+=sum(x*x for x in a)*.002
                screened[axis]+=sum(x!=u for x in a);nonzero_requested[axis]+=n if u!=0 else 0;nonzero_actual[axis]+=sum(x!=0 for x in a)
            if phase=='calibration' and n==10:complete_active+=1
            if n!=10:partial+=1
            expected_stop=stopped(row);checks.compare(expected_stop,row['study_abort'],tid+':'+str(index)+'/study')
            if expected_stop is not None:
                checks.compare(len(regular)-1,index,tid+'/stop_is_last');stop=expected_stop
        checks.compare(phases,ep['phase_budgets'],tid+'/phase_budgets');checks.compare(efforts,ep['phase_effort'],tid+'/phase_effort')
        budget={key:sum(v[key] for v in phases.values()) for key in ('control_calls_attempted','control_steps','physics_steps')}
        checks.compare(budget,ep,tid+'/budget');checks.compare(stop,ep['study_abort'],tid+'/stop')
        checks.compare(complete_active,ep['complete_active_endpoints'],tid+'/full_active')
        checks.compare(0,ep['returned_unwritten_steps'],tid+'/no_missing_returned');checks.compare(0,ep['unreturned_physics_steps'],tid+'/no_unreturned')
        checks.compare(None,ep['collector_exception'],tid+'/no_exception');checks.compare(False,ep['environment_terminated'],tid+'/no_environment_stop')
        complete=bool(len(regular)==500 and complete_active==400 and partial==0 and stop is None)
        checks.compare(complete,ep['completed'],tid+'/complete')
        status='completed' if complete else 'terminated' if stop is not None else 'incomplete';checks.compare(status,ep['status'],tid+'/status')
        final=regular[-1];q=final['observation_after']['joint_position'][:2];v=final['observation_after']['joint_velocity'][:2];ref=final['reference_q']
        stop_info=None
        if stop is not None:
            active=final['step_index']-100;block,slot=divmod(active,20)
            stop_info={'control_step_index':final['step_index'],'active_step_index':active,'block_index':block,'slot_index':slot,
                'block_type':('shoulder','elbow','same_direction','opposite_direction')[block//5],
                'trigger_axes':[JOINTS[t['joint_index']] for t in stop['triggers']],
                'triggers':stop['triggers'],'before_q_rad':final['observation_before']['joint_position'][:2],
                'before_velocity_rad_s':final['observation_before']['joint_velocity'][:2],
                'requested_torque_nm':final['requested_torque'][:2],
                'actual_torque_history_nm':[x[:2] for x in final['diagnostics']['applied_torque_history']],
                'study_thresholds':{'absolute_q_minus_qref_rad':.12,'absolute_velocity_rad_s':1.}}
        summary.append({'trial_id':tid,'pulse_steps':ep['pulse_steps'],'zero_steps_per_half':10-ep['pulse_steps'],'seed':ep['seed'],
            'status':status,'completed':complete,'budget':budget,'phase_budgets':phases,'complete_active_endpoints':complete_active,
            'partial_intervals':partial,'exception_raw_rows':len(exception_rows),'study_abort':stop,'stop_detail':stop_info,
            'final_q_rad':q,'reference_q_rad':ref,'final_q_minus_reference_rad':[q[i]-ref[i] for i in (0,1)],
            'final_velocity_rad_s':v,'guarded_physics_substeps_any_axis':guards,'screened_substeps_per_pair_axis':screened,
            'nonzero_requested_substeps_per_pair_axis':nonzero_requested,'nonzero_actual_substeps_per_pair_axis':nonzero_actual,
            'phase_effort':efforts,'directions':ep['direction']})
    total={k:sum(s['budget'][k] for s in summary) for k in ('control_calls_attempted','control_steps','physics_steps')}
    checks.compare(total,metadata,'total_budget');checks.compare({'control_calls_attempted':2586,'control_steps':2586,'physics_steps':25860},total,'preregistered_observed_cost')
    candidates=[]
    for pulse in (2,1):
        subset=[s for s in summary if s['pulse_steps']==pulse]
        candidates.append({'pulse_steps':pulse,'zero_steps_per_half':10-pulse,
            'eligible':len(subset)==3 and {s['seed'] for s in subset}=={0,1,2} and all(s['completed'] for s in subset),
            'trial_ids':[s['trial_id'] for s in subset]})
    selected=next((c['pulse_steps'] for c in candidates if c['eligible']),None)
    choice={'candidates':candidates,'selected_pulse_steps':selected,'status':'eligible' if selected is not None else 'blocked'}
    checks.compare(choice,metadata['candidate_selection'],'raw_candidate_priority');checks.compare(choice,audit['archive']['candidate_selection'],'existing_audit_selection')
    math_examples=[]
    for pulse,absolute,squared in ((2,.36,.1275),(1,.18,.06375)):
        # Per axis occurs in15 blocks; sum amplitudes=1.5, sum squares=.53125.
        value={'pulse_steps':pulse,'absolute_nm_s':3*1.5*(2*pulse)*.02,'squared_nm2_s':3*.53125*(2*pulse)*.02}
        checks.compare({'absolute_nm_s':absolute,'squared_nm2_s':squared},value,'hand_effort_pulse'+str(pulse));math_examples.append(value)
    checks.compare(3*500+sum(s['budget']['control_steps'] for s in summary if s['pulse_steps']==2),2586,'hand_total_cost')
    math_examples.append({'pulse1_three_full_calls':1500,'pulse2_paid_calls':1086,'sum_calls':2586,'substeps':25860})
    return {'created_at_utc':datetime.now(timezone.utc).isoformat(),'source_commit':metadata['source_commit'],
        'original_source_sha256':metadata['source_sha256'],'protocol':metadata['protocol'],'dependency_versions':metadata.get('dependencies'),
        'source_status':metadata['source_status'],'source_dirty':metadata['source_dirty'],'backend':metadata['backend'],
        'checks':checks.count,'failed':checks.failed,'violations':checks.violations,'maximum_recomputation_difference':checks.maximum_difference,
        'total_paid_budget':total,'phase_total_budget':{p:{k:sum(s['phase_budgets'][p][k] for s in summary) for k in ('control_calls_attempted','control_steps','physics_steps')} for p in PHASES},
        'statuses':dict(Counter(s['status'] for s in summary)),'trials':summary,'candidate_selection':choice,
        'model_updates':0,'partial_intervals':sum(s['partial_intervals'] for s in summary),'exception_raw_rows':sum(s['exception_raw_rows'] for s in summary),
        'guarded_physics_substeps_any_axis':sum(s['guarded_physics_substeps_any_axis'] for s in summary),
        'existing_audit':{'checks':audit['checks'],'failed':audit['failed'],'audit_script_sha256':audit['audit_script_sha256'],
            'validated_eligible':audit['validated_eligible'],'formal_execution_accepted':audit['formal_execution_accepted']},
        'hand_calculations':math_examples,'claim_boundary':'Fixed short-pulse executability only; no new model learning, predictions, controller evaluations, safety or skill evidence.'}

def render(summary):
    lines=['# Pair calibration finite descriptive summary','',
        f"Source commit: `{summary['source_commit']}`. Independent descriptive checks: {summary['checks']:,}, failures {summary['failed']}; maximum difference {summary['maximum_recomputation_difference']:.17g}.",'',
        'This reads each original input once, recomputes finite facts, and does not execute the auditor, physics, fitting or predictions.','',
        '| Trial | Status | Calls / substeps | Full active endpoints | Stop active / block / slot | Final shoulder v | Final elbow v | Guarded substeps |',
        '|---|---|---|---|---|---|---|---|']
    for row in summary['trials']:
        stop=row['stop_detail'];where='—' if stop is None else f"{stop['active_step_index']} / {stop['block_index']} / {stop['slot_index']}"
        lines.append(f"| {row['trial_id']} | {row['status']} | {row['budget']['control_steps']} / {row['budget']['physics_steps']} | {row['complete_active_endpoints']} | {where} | {row['final_velocity_rad_s'][0]:.12g} | {row['final_velocity_rad_s'][1]:.12g} | {row['guarded_physics_substeps_any_axis']} |")
    lines+=['',f"Selected pulse: {summary['candidate_selection']['selected_pulse_steps']}; both candidates were executed, and selection uses all three complete trials rather than truncated effort.",'',
        'All per-axis requested/actual absolute and squared efforts, prefix/calibration budgets, exact stop q/v/reference, command histories and input/source hashes are retained in summary.json and execution.json.','',
        'These results establish finite calibration executability for the selected short schedule. They do not establish safe exploration, learned coupled dynamics, controller improvement or locomotion.']
    return '\n'.join(lines)+'\n'

def main():
    wall,cpu=time.perf_counter(),time.process_time()
    OUTPUT.mkdir()
    own=Path(__file__).read_bytes();(OUTPUT/'tool_source.py').write_bytes(own)
    record={'started_at_utc':datetime.now(timezone.utc).isoformat(),'python':sys.version,
        'source_path':str(Path(__file__)),'source_sha256':sha(own),'source_snapshot':'tool_source.py',
        'raw_directory':str(RAW),'audit_path':str(AUDIT),'expected_source_commit':SOURCE_COMMIT,
        'physical_calls':0,'model_updates':0,'new_predictions':0,'audit_executions':0,'raw_read_passes':0,'input_sha256':{}}
    save(OUTPUT/'attempt.json',record)
    checks=Checks();code=1;summary=None
    try:
        files={name:(RAW/name).read_bytes() for name in ('metadata.json','episodes.json','manifest.json','source_snapshot.zip','trace.jsonl.gz')}
        audit_bytes=AUDIT.read_bytes();record['raw_read_passes']=1
        record['input_sha256']={name:sha(data) for name,data in files.items()};record['existing_audit_sha256']=sha(audit_bytes)
        summary=summarize(files,audit_bytes,checks);save(OUTPUT/'summary.json',summary)
        with (OUTPUT/'summary.md').open('x',encoding='utf-8',newline='\n') as f:f.write(render(summary))
        code=int(checks.failed!=0)
    except BaseException as exc:
        record['exception']={'type':type(exc).__name__,'message':str(exc)};raise
    finally:
        record['source_after_sha256']=sha(Path(__file__).read_bytes());record['source_unchanged']=record['source_after_sha256']==record['source_sha256']
        if not record['source_unchanged']:code=1
        record.update(checks=checks.count,failed=checks.failed,maximum_recomputation_difference=checks.maximum_difference,
            output_sha256={p.name:sha(p.read_bytes()) for p in sorted(OUTPUT.iterdir()) if p.is_file()},
            wall_seconds=time.perf_counter()-wall,cpu_seconds=time.process_time()-cpu,exit_code=code)
        save(OUTPUT/'execution.json',record)
    print(json.dumps({'checks':checks.count,'failed':checks.failed,'wall_seconds':record['wall_seconds'],'cpu_seconds':record['cpu_seconds'],
        'statuses':summary['statuses'],'total_paid_budget':summary['total_paid_budget'],'selected_pulse_steps':summary['candidate_selection']['selected_pulse_steps'],'physical_calls':0}))
    return code

if __name__=='__main__':raise SystemExit(main())
