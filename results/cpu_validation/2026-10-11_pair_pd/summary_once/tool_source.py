"""Independent stdlib one-pass descriptive PD summary; no collector/audit imports."""
from collections import Counter, defaultdict
from datetime import datetime, timezone
import gzip
import hashlib
import io
import json
import math
from pathlib import Path
import sys
import time
import xml.etree.ElementTree as ET
import zipfile

ROOT=Path(__file__).resolve().parent.parent
RAW=ROOT/'external/pair_pd_20261011_first'
AUDIT=ROOT/'external/pair_pd_20261011_first_audit.json'
OUTPUT=ROOT/'external/pair_pd_20261011_summary_01'
COMMIT='f9f35fe9bb338aa398cc426e144eff048fde3746'
KD=((0.,1.),(0.,2.),(0.,4.),(1.,1.),(1.,2.),(1.,4.),(2.,1.),(2.,2.),(2.,4.))
PHASES=('prefix','control')
JOINTS=('left_shoulder','left_elbow','right_shoulder','right_elbow','left_hip','left_knee','right_hip','right_knee')
EFFORT=('requested_absolute_nm_s','requested_squared_nm2_s','actual_absolute_nm_s','actual_squared_nm2_s')
BUDGET=('control_calls_attempted','control_steps','physics_steps')

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
            d=abs(a-b);self.maximum_difference=max(d,self.maximum_difference);self.check(d<=1e-10+1e-10*abs(a),label)
        else:self.check(a==b,label)

def tracking(errors):
    if not errors:return None
    count=len(errors)
    return {'joint':math.sqrt(math.fsum(x*x for row in errors for x in row)/(2*count)),
        'per_axis':[math.sqrt(math.fsum(row[i]*row[i] for row in errors)/count) for i in (0,1)],
        'complete_endpoints':count}

def windows(endpoints):
    result={}
    for name,lower,upper in (('segment0',0,100),('segment1',100,200),('segment0_last20',80,100),('segment1_last20',180,200)):
        returned=[r for r in endpoints if lower<=r['active_index']<upper]
        errors=[r['error_rad'] for r in returned if r['complete_transition']]
        result[name]={'planned_active_index_start':lower,'planned_active_index_end_exclusive':upper,'planned_count':upper-lower,
            'returned_count':len(returned),'complete_count':len(errors),'partial_count':len(returned)-len(errors),
            'missing_returned_count':upper-lower-len(returned),'missing_complete_count':upper-lower-len(errors),
            'tracking':tracking(errors),'signed_mean_error_rad':None if not errors else [math.fsum(r[i] for r in errors)/len(errors) for i in (0,1)],
            'returned_endpoints':returned}
    return result

def risk():
    return {'peak_ground_force_n':0.,'ground_normal_impulse_ns':0.,'peak_kinetic_energy_j':0.,'minimum_contact_distance_m':0.,
        'max_native_speed_rad_s':0.,'guarded_substeps':0,'outside_public_limit_endpoint_count':0}

def add_risk(out,row,ranges,guarded):
    d=row['diagnostics'];after=row['observation_after']
    out['peak_ground_force_n']=max(out['peak_ground_force_n'],*d['substep_ground_normal_forces'],0.)
    out['ground_normal_impulse_ns']+=math.fsum(d['substep_ground_normal_forces'])*.002
    out['peak_kinetic_energy_j']=max(out['peak_kinetic_energy_j'],*d['substep_kinetic_energies'],0.)
    out['minimum_contact_distance_m']=min(out['minimum_contact_distance_m'],*d['substep_minimum_contact_distances'],0.)
    out['max_native_speed_rad_s']=max(out['max_native_speed_rad_s'],*[abs(v) for v in after['joint_velocity']])
    out['guarded_substeps']+=guarded
    out['outside_public_limit_endpoint_count']+=int(any(q<limits[0] or q>limits[1] for q,limits in zip(after['joint_position'],ranges)))

def study(row,ref):
    index=row['control_index']
    if index<100:return None
    q=row['observation_after']['joint_position'][:2];v=row['observation_after']['joint_velocity'][:2];triggers=[]
    for i in (0,1):
        if abs(q[i]-ref[i])>=.12:triggers.append({'joint_index':i,'signal':'absolute_q_minus_qref_rad'})
        if abs(v[i])>=1.:triggers.append({'joint_index':i,'signal':'absolute_velocity_rad_s'})
    return None if not triggers else {'type':'StudyAbort','triggers':triggers,'q_rad':q,'qref_rad':ref,'velocity_rad_s':v,
        'thresholds':{'absolute_q_minus_qref_rad':.12,'absolute_velocity_rad_s':1.},'feedback_action':None,
        'phase':'control','step_index':index,'active_index':index-100}

def summarize(raw,audit_bytes,checks):
    metadata=json.loads(raw['metadata.json']);episodes=json.loads(raw['episodes.json']);saved_selection=json.loads(raw['selection.json']);audit=json.loads(audit_bytes)
    checks.compare(COMMIT,metadata['source_commit'],'source_commit')
    checks.compare({'check_count':591017,'failed_checks':0,'validated_selection':True},audit,'existing_first_audit')
    checks.compare({'suite':'pair_pd_development','synthetic':False,'model_updates':0,'parameter_updates':{'body_model':0,'policy':0,'gains':0},
        'seeds':[0,1,2],'kp':[64.,64.],'kd_candidates':[list(k) for k in KD]},metadata,'fixed_scope')
    plans=[{'trial_id':f'seed{s}_candidate{i}','seed':s,'candidate':i,'kp':[64.,64.],'kd':list(k),'maximum_control_steps':300} for s in (0,1,2) for i,k in enumerate(KD)]
    checks.compare(plans,metadata['planned_episodes'],'fixed_plan');checks.compare([p['trial_id'] for p in plans],[e['trial_id'] for e in episodes],'episode_order')
    with zipfile.ZipFile(io.BytesIO(raw['source_snapshot.zip'])) as source:
        xml=ET.fromstring(source.read('src/developmental_physics/assets/ground_body.xml'))
    compiler=xml.find('compiler');factor=math.pi/180 if compiler is None or compiler.get('angle','degree')=='degree' else 1.
    asset_ranges={j.get('name'):[float(x)*factor for x in j.get('range').split()] for j in xml.findall('.//joint') if j.get('range')}
    ranges=[asset_ranges[j] for j in JOINTS]
    grouped=defaultdict(list)
    for line in gzip.decompress(raw['trace.jsonl.gz']).decode().splitlines():
        if line:
            row=json.loads(line);grouped[row['trial_id']].append(row)
    checks.compare({p['trial_id'] for p in plans},set(grouped),'raw_trial_groups')
    trials=[]
    for ep,plan in zip(episodes,plans):
        tid=ep['trial_id'];rows=grouped[tid];regular=[r for r in rows if 'collector_exception' not in r];exceptions=[r for r in rows if 'collector_exception' in r]
        checks.compare(plan,ep,tid+'/plan');checks.compare(ranges,ep['public_joint_ranges_rad'],tid+'/public_ranges')
        checks.compare(0,len(exceptions),tid+'/ordinary_formal_matrix_no_exception')
        budgets={p:dict.fromkeys(BUDGET,0) for p in PHASES};efforts={p:{k:[0.,0.] for k in EFFORT} for p in PHASES}
        risks={p:risk() for p in ('full',*PHASES)};complete_count=dict.fromkeys(PHASES,0);saturation=[0,0];endpoints=[];errors=[];partial=[]
        ref=None;directions=None;stop=None;environment=False;environment_reason=None;known_actual=dict.fromkeys(PHASES,0)
        for index,row in enumerate(regular):
            phase='prefix' if index<100 else 'control';d=row['diagnostics'];n=d['executed_substeps'];u=row['requested_torque'];h=d['applied_torque_history']
            before=row['observation_before'];after=row['observation_after'];label=tid+':'+str(index)
            checks.compare({'control_index':index,'phase':phase,'seed':plan['seed'],'candidate':plan['candidate'],'kd':plan['kd'],'kp':[64.,64.]},row,label+'/timing_identity')
            checks.compare(n,len(h),label+'/paid_actual_history');checks.check(0<=n<=10,label+'/paid_substep_range')
            budgets[phase]['control_calls_attempted']+=1
            budgets[phase]['control_steps']+=row['control_steps_after']-row['control_steps_before']
            budgets[phase]['physics_steps']+=row['physics_steps_after']-row['physics_steps_before']
            checks.compare(n,row['physics_steps_after']-row['physics_steps_before'],label+'/paid_delta')
            if index==100:
                ref=before['joint_position'][:2]
                directions=[1 if ranges[i][1]-ref[i]>=ref[i]-ranges[i][0] else -1 for i in (0,1)]
            expected=[0.]*8;raw_pd=None;target=None
            if phase=='control':
                target=[ref[i]+directions[i]*(.04 if index<200 else .08) for i in (0,1)]
                raw_pd=[64.*(target[i]-before['joint_position'][i])-plan['kd'][i]*before['joint_velocity'][i] for i in (0,1)]
                expected[:2]=[max(-.5,min(.5,x)) for x in raw_pd]
                error=[after['joint_position'][i]-target[i] for i in (0,1)]
                endpoint={'active_index':index-100,'error_rad':error,'complete_transition':n==10};endpoints.append(endpoint)
                if n==10:
                    errors.append(error)
                    for axis in (0,1):saturation[axis]+=int(abs(u[axis])==.5)
                else:partial.append({'active_index':index-100,'error_rad':error})
            checks.compare(expected,u,label+'/fixed_pd_request');checks.compare(raw_pd,row['raw_pd_torque_nm'],label+'/raw_pd')
            checks.compare(target,row['target_q_rad'],label+'/current_target');checks.compare(n==10,row['complete_transition'],label+'/metric_interval')
            expected_stop=study(row,ref);checks.compare(expected_stop,row['study_abort'],label+'/study')
            if expected_stop is not None:stop=expected_stop;checks.compare(len(regular)-1,index,tid+'/stop_last')
            environment=bool(row['environment_terminated']);environment_reason=row['environment_stop_reason']
            if n==10:complete_count[phase]+=1
            known_actual[phase]+=n
            guarded=sum(any(a[i]!=u[i] for i in range(8)) for a in h);checks.compare(guarded,d['guarded_substeps'],label+'/guard_count')
            for p in ('full',phase):add_risk(risks[p],row,ranges,guarded)
            for axis in (0,1):
                efforts[phase][EFFORT[0]][axis]+=abs(u[axis])*n*.002;efforts[phase][EFFORT[1]][axis]+=u[axis]**2*n*.002
                efforts[phase][EFFORT[2]][axis]+=math.fsum(abs(a[axis]) for a in h)*.002
                efforts[phase][EFFORT[3]][axis]+=math.fsum(a[axis]**2 for a in h)*.002
        budget={k:sum(b[k] for b in budgets.values()) for k in BUDGET}
        complete=bool(not exceptions and stop is None and not environment and budget=={'control_calls_attempted':300,'control_steps':300,'physics_steps':3000}
            and complete_count=={'prefix':100,'control':200} and len(regular)==300 and not partial)
        status='exception' if exceptions else 'terminated' if stop is not None or environment else 'completed'
        metrics=tracking(errors);tails=windows(endpoints);combined={p:{k:sum(efforts[p][k]) for k in EFFORT} for p in PHASES}
        checks.compare(budget,ep,tid+'/paid_budget');checks.compare(budgets,ep['phase_budgets'],tid+'/phase_budgets')
        checks.compare(efforts,ep['phase_effort'],tid+'/efforts');checks.compare(combined,ep['phase_effort_combined'],tid+'/combined_efforts')
        checks.compare(risks,ep['phase_risk'],tid+'/risks');checks.compare(metrics,ep['tracking'],tid+'/tracking');checks.compare(tails,ep['tracking_windows'],tid+'/windows')
        checks.compare(errors,ep['complete_tracking_errors_rad'],tid+'/complete_errors');checks.compare(partial,ep['partial_interval_target_errors_rad'],tid+'/partial_errors')
        checks.compare(complete_count,ep['phase_complete_transition_counts'],tid+'/full_intervals');checks.compare(saturation,ep['saturated_control_steps_per_axis'],tid+'/saturation')
        checks.compare({'complete':complete,'status':status,'study_abort':stop,'environment_terminated':environment,'environment_stop_reason':environment_reason,
            'metric_control_step_count':len(errors),'partial_interval_target_error_count':len(partial),'phase_actual_effort_substeps':known_actual,
            'actual_effort_complete':sum(known_actual.values())==budget['physics_steps'],'returned_control_steps':len(regular),'trace_rows_written':len(regular),
            'returned_unstored_control_steps':0,'unreturned_physics_steps':0,'collector_exception':None,'trace_write_failure':None},ep,tid+'/outcome')
        last=regular[-1];stop_detail=None if stop is None else {'step_index':stop['step_index'],'active_index':stop['active_index'],
            'trigger_axes':[JOINTS[t['joint_index']] for t in stop['triggers']],'before_q_rad':last['observation_before']['joint_position'][:2],
            'before_v_rad_s':last['observation_before']['joint_velocity'][:2],'after_q_rad':last['observation_after']['joint_position'][:2],
            'after_v_rad_s':last['observation_after']['joint_velocity'][:2],'requested_nm':last['requested_torque'][:2],
            'raw_pd_nm':last['raw_pd_torque_nm'],'actual_history_nm':[a[:2] for a in last['diagnostics']['applied_torque_history']]}
        trials.append({**plan,'status':status,'complete':complete,'eligible':complete and not ep.get('invalid_numeric_fields') and sum(known_actual.values())==budget['physics_steps'],
            'budget':budget,'phase_budgets':budgets,'tracking':metrics,'tracking_windows':tails,'phase_effort':efforts,'phase_effort_combined':combined,
            'phase_risk':risks,'phase_complete_transition_counts':complete_count,'partial_count':len(partial),'exception_count':len(exceptions),
            'study_abort':stop,'stop_detail':stop_detail,'saturated_control_steps_per_axis':saturation,'reference_q_rad':ref,'directions':directions,
            'final_q_rad':last['observation_after']['joint_position'][:2],'final_velocity_rad_s':last['observation_after']['joint_velocity'][:2]})
    candidates=[]
    for i,kd in enumerate(KD):
        group=[t for t in trials if t['candidate']==i]
        eligible=len(group)==3 and {t['seed'] for t in group}=={0,1,2} and all(t['eligible'] for t in group)
        key=None if not eligible else [math.fsum(t['tracking']['joint'] for t in group)/3,max(t['tracking']['joint'] for t in group),
            math.fsum(t['phase_effort_combined']['control']['actual_squared_nm2_s'] for t in group)/3,i]
        candidates.append({'candidate':i,'kp':[64.,64.],'kd':list(kd),'eligible':eligible,'sort_key':key,
            'paid_control_steps':sum(t['budget']['control_steps'] for t in group),'paid_physics_steps':sum(t['budget']['physics_steps'] for t in group)})
    eligible=[c for c in candidates if c['eligible']];picked=min(eligible,key=lambda c:c['sort_key']) if eligible else None
    selection={'status':'selected' if picked else 'blocked','picked':picked,'candidates':candidates}
    checks.compare(selection,saved_selection,'saved_selection');checks.compare(selection,audit['selection'],'existing_first_audit_selection')
    checks.compare(['mean_seed_joint_rmse','max_seed_joint_rmse','mean_seed_control_actual_squared_effort','candidate_index'],saved_selection['sort_order'],'sort_hierarchy')
    total={k:sum(t['budget'][k] for t in trials) for k in BUDGET};checks.compare(total,metadata,'total_paid_budget')
    checks.compare({'control_calls_attempted':4536,'control_steps':4536,'physics_steps':45360},total,'authorized_observed_budget')
    statuses=dict(Counter(t['status'] for t in trials));checks.compare({'completed':9,'terminated':18},statuses,'authorized_observed_status')
    # Only three finite arithmetic examples; no new dynamics/predictions.
    hand=[{'errors_rad':[[.03,.04],[.03,.04]],'joint_rmse':tracking([[.03,.04],[.03,.04]])['joint']},
        {'two_paid_substeps_at_half_nm_absolute':abs(.5)*2*.002,'squared':.5**2*2*.002},
        {'complete_trial_calls':9*300,'stopped_trial_calls':18*102,'sum_calls':9*300+18*102}]
    checks.compare(math.sqrt(.00125),hand[0]['joint_rmse'],'hand_paired_rmse');checks.compare(.002,hand[1]['two_paid_substeps_at_half_nm_absolute'],'hand_abs_effort')
    checks.compare(.001,hand[1]['squared'],'hand_square_effort');checks.compare(4536,hand[2]['sum_calls'],'hand_paid_total')
    return {'created_at_utc':datetime.now(timezone.utc).isoformat(),'source_commit':metadata['source_commit'],'original_source_sha256':metadata['source_sha256'],
        'protocol':metadata['protocol'],'dependencies':metadata.get('dependencies'),'backend':metadata['backend'],
        'checks':checks.count,'failed':checks.failed,'violations':checks.violations,'maximum_recomputation_difference':checks.maximum_difference,
        'trials':trials,'selection':selection,'eligible_ranked_candidates':sorted(eligible,key=lambda c:c['sort_key']),'saved_candidate_failure_reasons':[c.get('qualification_failures') for c in saved_selection['candidates']],
        'statuses':statuses,'total_paid_budget':total,'phase_total_budget':{p:{k:sum(t['phase_budgets'][p][k] for t in trials) for k in BUDGET} for p in PHASES},
        'partial_count':sum(t['partial_count'] for t in trials),'exception_count':sum(t['exception_count'] for t in trials),'model_updates':0,
        'existing_audit':{'check_count':audit['check_count'],'failed_checks':audit['failed_checks'],'validated_selection':audit['validated_selection'],
            'audit_sources_sha256':audit['audit_sources_sha256'],'maximum_numeric_difference':audit['maximum_numeric_difference'],
            'audit_wall_seconds':audit['audit_wall_seconds'],'audit_cpu_seconds':audit['audit_cpu_seconds']},
        'collector_timing':{'wall_seconds':metadata['wall_seconds'],'cpu_seconds':metadata['cpu_seconds']},'hand_calculations':hand,
        'cumulative_accounting':{'formal_control_calls':232184,'formal_physics_substeps':2321840,'scalar_model_updates':12852},
        'claim_boundary':'Finite fixed-Kp damping-grid development only; no global optimum, body-model advantage, skill, adaptation or safety proof.'}

def render(result):
    lines=['# Pair-PD one-pass independent descriptive summary','',f"Source `{result['source_commit']}`; {result['checks']:,} checks /{result['failed']} failures; maximum difference {result['maximum_recomputation_difference']:.17g}.",'',
        '| Candidate | Kd shoulder/elbow | Eligible | Paid calls/substeps | Mean/worst joint RMSE | Mean actual squared effort |',
        '|---|---|---|---|---|---|']
    for row in result['selection']['candidates']:
        key=row['sort_key'];metrics='—' if key is None else f'{key[0]:.12g} / {key[1]:.12g}';effort='—' if key is None else f'{key[2]:.12g}'
        lines.append(f"| {row['candidate']} | {row['kd']} | {row['eligible']} | {row['paid_control_steps']} / {row['paid_physics_steps']} | {metrics} | {effort} |")
    lines+=['',f"Statuses: {result['statuses']}. Paid budget: {result['total_paid_budget']}. Picked: {result['selection']['picked']}.",'',
        'Full/partial/missing windows retain original planned indices. Complete stopped endpoints can be scored but never qualify a truncated candidate. Per-axis effort, full-body risk, saturation, stopping q/v and all window endpoints are in summary.json.','',result['claim_boundary']]
    return '\n'.join(lines)+'\n'

def main():
    if sys.argv[1:]!=['--execute-once-after-first-audit']:
        raise RuntimeError('Explicit root first-audit-completed authorization flag required; no input read performed')
    wall,cpu=time.perf_counter(),time.process_time();OUTPUT.mkdir()
    own=Path(__file__).read_bytes();(OUTPUT/'tool_source.py').write_bytes(own)
    record={'started_at_utc':datetime.now(timezone.utc).isoformat(),'source_path':str(Path(__file__)),'source_sha256':sha(own),
        'source_snapshot':'tool_source.py','python':sys.version,'expected_source_commit':COMMIT,'raw_read_passes':0,
        'physical_calls':0,'model_updates':0,'new_predictions':0,'audit_executions':0,'input_sha256':{}}
    save(OUTPUT/'attempt.json',record);checks=Checks();code=1;result=None;stdout=''
    try:
        raw={name:(RAW/name).read_bytes() for name in ('metadata.json','episodes.json','selection.json','manifest.json','source_snapshot.zip','trace.jsonl.gz')}
        audit_bytes=AUDIT.read_bytes();record['raw_read_passes']=1;record['input_sha256']={n:sha(b) for n,b in raw.items()};record['existing_audit_sha256']=sha(audit_bytes)
        result=summarize(raw,audit_bytes,checks);save(OUTPUT/'summary.json',result)
        with (OUTPUT/'summary.md').open('x',encoding='utf-8',newline='\n') as f:f.write(render(result))
        code=int(checks.failed!=0)
        stdout=json.dumps({'checks':checks.count,'failed':checks.failed,'statuses':result['statuses'],'total_paid_budget':result['total_paid_budget'],
            'picked':result['selection']['picked'],'physical_calls':0,'audit_executions':0})+'\n'
    except BaseException as exc:
        record['exception']={'type':type(exc).__name__,'message':str(exc)};stdout=json.dumps({'exception':record['exception']})+'\n'
    finally:
        with (OUTPUT/'stdout.txt').open('x',encoding='utf-8',newline='\n') as f:f.write(stdout)
        record['source_after_sha256']=sha(Path(__file__).read_bytes());record['source_unchanged']=record['source_after_sha256']==record['source_sha256']
        if not record['source_unchanged']:code=1
        record.update(checks=checks.count,failed=checks.failed,maximum_recomputation_difference=checks.maximum_difference,
            output_sha256={p.name:sha(p.read_bytes()) for p in sorted(OUTPUT.iterdir()) if p.is_file()},
            wall_seconds=time.perf_counter()-wall,cpu_seconds=time.process_time()-cpu,exit_code=code)
        save(OUTPUT/'execution.json',record)
    print(stdout,end='');print(json.dumps({'wall_seconds':record['wall_seconds'],'cpu_seconds':record['cpu_seconds'],'exit_code':code}))
    return code

if __name__=='__main__':raise SystemExit(main())
