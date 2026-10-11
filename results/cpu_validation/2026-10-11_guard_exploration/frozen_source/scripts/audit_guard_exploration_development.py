"""Independent fixed C4 C exploration audit; standard libraries only.

This audit reconstructs new C records, never imports online code, simulates,
executes an A/B audit or loads their old experimental data. Coupled9 mathematics
are shared with the previously frozen independent B audit helper library.
"""
from __future__ import annotations
import argparse
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import platform
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
import zipfile

ROOT=next(p for p in Path(__file__).resolve().parents if (p/'pyproject.toml').is_file())
def _load(name,path):
    loader=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(loader);sys.modules[name]=module;loader.loader.exec_module(module)
    return module
b=_load('_exploration_coupled_math_support',ROOT/'scripts/audit_guard_coupled_development.py')
guard,common=b.guard,b.common
Checks,vector,finite=b.Checks,b.vector,b.finite
pair,load_json,parse_json,digest,file_hash=b.pair,b.load_json,b.parse_json,b.digest,b.file_hash
SOURCE='src/developmental_physics/guard_exploration_development.py'
AUDITOR='scripts/audit_guard_exploration_development.py'
PROTOCOL='docs/GUARD_EXPLORATION_DEVELOPMENT_PROTOCOL.md'
SUPPORT=('scripts/audit_guard_coupled_development.py',*b.SUPPORT)
KINDS=('calibration_sparse','calibration_continuation','prediction','nominal_guard',
       'learned_sparse','learned_continuation','PDselected','zero')
CAL_GROUPS={'calibration_sparse':'sparse','calibration_continuation':'continuation'}
LEARNED={'sparse':'learned_sparse','continuation':'learned_continuation'}
MODELS=('nominal_guard','learned_sparse','learned_continuation')
MPC_KINDS=MODELS
CONTROL_KINDS=KINDS[3:]
PHASES=('prefix','calibration','prediction','control')
RESET=b.RESET
EFFORT_KEYS=common.EFFORT_KEYS
PLANNING_KEYS=guard.PLANNING_KEYS

@dataclass(frozen=True)
class ExplorationAuditSpec:
    synthetic_fixture: bool=False
    scientific_gates_frozen: bool=True
    def __post_init__(self):
        if type(self.synthetic_fixture) is not bool or type(self.scientific_gates_frozen) is not bool or self.synthetic_fixture is self.scientific_gates_frozen:
            raise ValueError('Exact immutable C production or artificial scope required')
    def record(self):
        return {'suite':'guard_exploration_development','pose':'supine','seeds':[0,1,2],'joint_indices':[0,1],
            'split':'development','collector':SOURCE,'auditor':AUDITOR,'protocol':PROTOCOL,
            'synthetic_fixture':self.synthetic_fixture,'scientific_gates_frozen':self.scientific_gates_frozen,
            'prefix_steps':100,'calibration_steps':400,'prediction_steps':100,'control_steps':200,
            'structure':'coupled_hinge9','input_basis':'known_angle_guard','parameters_per_output':9,
            'calibration_rules':{'sparse':'sparse_1_9','continuation':'continuation_2_8_native_veto'},
            'continuation_veto':{'absolute_velocity_rad_s':.5,'absolute_q_minus_qref_rad':.06,'comparison':'>='},
            'prediction_rule':'continuation_2_8_native_veto','prediction_velocity_ratio_max':.8,
            'body_tracking_mean_improvement_min':.20,'exploration_prediction_ratio_max':.8,
            'exploration_tracking_mean_improvement_min':.20,'exploration_actual_effort_ratio_max':1.05,
            'pd_tracking_joint_mean_improvement_min':.05,'pd_actual_effort_ratio_max':1.05,
            'minimum_calibration_nonzero_start_G_intervals_per_axis':1,
            'minimum_calibration_actual_absolute_effort_positive_per_axis':True,
            'minimum_prediction_nonzero_start_G_intervals_per_axis':1,
            'pd_selected_id':2,'pd_kp':[64.,64.],'pd_kd':[0.,4.]}
PRODUCTION_SPEC=ExplorationAuditSpec()
SYNTHETIC_SPEC=ExplorationAuditSpec(synthetic_fixture=True,scientific_gates_frozen=False)

def duration(kind): return 400 if kind in CAL_GROUPS else 100 if kind=='prediction' else 200
def phase_at(kind,index): return 'prefix' if index<100 else 'calibration' if kind in CAL_GROUPS else 'prediction' if kind=='prediction' else 'control'
def planned_matrix():
    return [{'trial_id':f'seed{s}_{k}','seed':s,'kind':k,'maximum_control_steps':100+duration(k)} for s in RESET for k in KINDS]
def require_scope(metadata,spec):
    if type(spec) is not ExplorationAuditSpec: raise ValueError('Trusted immutable C scope required')
    expected={'schema_version':1,'suite':'guard_exploration_development','synthetic':spec.synthetic_fixture,
        'seeds':[0,1,2],'split':'development','pose':'supine','joint_indices':[0,1],'native_joint_count':8,
        'gpu':None,'prefix_steps':100,'calibration_steps':400,'prediction_steps':100,'control_steps_per_trial':200,
        'structures':['coupled_hinge9'],'model_input_basis':'known_angle_guard','pd_gains':{'kp':[64.,64.],'kd':[0.,4.]},
        'policy_parameter_updates':0,'gain_updates':0,'gate_updates':0,'teacher_calls':0,'external_demonstration_samples':0}
    for key,value in expected.items(): b._equal(metadata.get(key),value,'Immutable C scope before trace/ZIP read '+key)
    b._equal(metadata['protocol']['path'],PROTOCOL,'Immutable C protocol')
    if not spec.synthetic_fixture:
        b._equal(metadata['backend'],'MuJoCo CPU','C CPU backend')
        b._equal(metadata['environment_config'],common.ENVIRONMENT,'C unchanged environment')
    return metadata

def verify_sources(path,metadata,checks,git_root,spec):
    manifest=load_json(path/'manifest.json')
    names={p.name for p in path.iterdir() if p.is_file() and p.name!='manifest.json'}
    checks.check(set(manifest)==names,'manifest_exact_coverage')
    checks.check({'metadata.json','episodes.json','seed_results.json','trace.jsonl.gz','source_snapshot.zip'}.issubset(manifest),'manifest_core_files')
    for name,value in manifest.items():
        b._assert(guard._path(name)==Path(name).name,'Local manifest filenames required')
        checks.check(file_hash(path/name)==guard._hash(value),'manifest_hash',name)
    commit=metadata['source_commit'];valid=type(commit) is str and re.fullmatch('[0-9a-f]{40}',commit) is not None
    checks.check(metadata.get('source_status')=='' and metadata.get('source_dirty') is False,'clean_collection_source')
    checks.check(commit=='synthetic-fixture-no-git' if spec.synthetic_fixture else valid,'source_commit_identity')
    hashes=metadata['source_sha256'];members=b.source_members((path/'source_snapshot.zip').read_bytes())
    checks.check(set(hashes)==set(members),'source_zip_exact_unique_coverage')
    required=common.BASE_REQUIRED_SOURCES|{SOURCE,AUDITOR,PROTOCOL,b.CORE,'src/developmental_physics/guard_pair_model.py',
        'src/developmental_physics/local_pair_model.py','src/developmental_physics/pd_selection_binding.py',guard.PD_PROTOCOL,*SUPPORT}
    if not spec.synthetic_fixture: required|=set(guard.PD_SOURCE_FILES)
    checks.check(required.issubset(hashes),'required_source_coverage')
    checks.compare(metadata['source_snapshot_sha256'],file_hash(path/'source_snapshot.zip'),'source_zip_hash')
    for name,value in hashes.items():
        guard._path(name);guard._hash(value)
        checks.check(b.sha(members[name])==value,'source_member_hash',name)
        if git_root is not None and not spec.synthetic_fixture and valid:
            result=subprocess.run(['git','show',f'{commit}:{name}'],cwd=git_root,capture_output=True,check=False)
            checks.check(result.returncode==0 and result.stdout==members[name],'source_git_blob_bytes',name)
    checks.compare(metadata['protocol'],{'path':PROTOCOL,'sha256':hashes[PROTOCOL]},'protocol_source_identity')
    if not spec.synthetic_fixture:
        checks.compare(metadata['independent_auditor'],{'path':AUDITOR,'sha256':file_hash(__file__),'pending':False,'required_for_formal':True},'executing_auditor_identity')
        checks.check(members[AUDITOR]==Path(__file__).read_bytes(),'executing_auditor_bytes')
        for name in SUPPORT: checks.check(members[name]==(ROOT/name).read_bytes(),'executing_support_bytes',name)
        if git_root is not None and valid:
            result=subprocess.run(['git','ls-tree','-r','--name-only',commit,'src/developmental_physics'],cwd=git_root,capture_output=True,text=True,check=False)
            py={n for n in result.stdout.splitlines() if n.endswith('.py') and n.count('/')==2}
            checks.check(result.returncode==0 and py.issubset(hashes),'all_physics_sources_archived')
    guard.verify_pd_binding(path,metadata,checks,spec)
    checks.compare(metadata['pd_gains'],{'kp':[64.,64.],'kd':[0.,4.]},'C_frozen_PD_candidate2')
    return b.public_ranges(members[common.ASSET]),{**manifest,'manifest.json':file_hash(path/'manifest.json')}

def exploration_command(kind,active,directions,q,v,qref):
    if kind not in (*CAL_GROUPS,'prediction') or type(active) is not int or not 0<=active<duration(kind):
        raise ValueError('Fixed C exploration kind and active index required')
    q,v,qref=pair(q),pair(v),pair(qref)
    b._assert(type(directions) in (list,tuple) and len(directions)==2 and all(type(x) is int and x in (-1,1) for x in directions),'Two fixed signed directions')
    block,slot=divmod(active,20);sparse=kind=='calibration_sparse'
    if kind=='prediction':
        amplitude=(.125,.25,.375,.5,.375)[block]
        shape=((1.,0.),(0.,1.),(1.,1.),(1.,-1.),(1.,1.))[block]
    else:
        amplitude=(.125,.25,.375,.5,.25)[block%5]
        shape=((1.,0.),(0.,1.),(1.,1.),(1.,-1.))[block//5]
    pulse=1 if sparse else 2
    sign=1 if slot<pulse else -1 if 10<=slot<10+pulse else 0
    planned=[directions[i]*shape[i]*sign*amplitude for i in range(2)]
    vv=[not sparse and abs(x)>=.5 for x in v]
    qq=[not sparse and abs(q[i]-qref[i])>=.06 for i in range(2)]
    nonzero=[x!=0. for x in planned];veto=[nonzero[i] and (vv[i] or qq[i]) for i in range(2)]
    requested=[0. if veto[i] else planned[i] for i in range(2)]
    diag={'schema':'c4-exploration-command-v1','rule':'sparse_1_9' if sparse else 'continuation_2_8_native_veto',
        'active_index':active,'block_index':block,'slot_index':slot,'amplitude_nm':amplitude,'shape':list(shape),
        'native_q_rad':q,'native_v_rad_s':v,'qref_rad':qref,'planned_nm':planned,'requested_nm':requested,
        'planned_nonzero':nonzero,'velocity_veto':vv,'position_veto':qq,'command_vetoed':veto,
        'velocity_threshold_rad_s':None if sparse else .5,'position_threshold_rad':None if sparse else .06,
        'comparison':None if sparse else '>=','physical_queries':0,'future_actual_input':False,'learned_gate':False}
    return requested,diag

def complete(ev): return b.complete(ev)
def complete_matrix(seeds,kinds): return b.complete_matrix(seeds,kinds)
def nonnegative_pair(value): return b.nonnegative_pair(value)
def body_gate(seeds,group):
    model=LEARNED[group];cal='calibration_'+group
    converted=[]
    for seed in seeds:
        ev=seed.get('evaluations',{});pred=deepcopy(ev.get('prediction',{}))
        pm=pred.get('velocity_prediction_rmse',{});pm[b.MODEL]=pm.get(model)
        converted.append({'seed':seed['seed'],'evaluations':{'calibration':ev.get(cal,{}),'prediction':pred,
            'nominal_guard':ev.get('nominal_guard',{}),b.MODEL:ev.get(model,{})}})
    gate=b.contribution_gate(converted);gate.update(group=group,required_trials=[cal,'prediction','nominal_guard',model])
    gate['prediction_boundary']='Fresh C common continuation/veto development trajectory; no reuse of A/B scores.'
    return gate
def effort_gates(rows,evaluated):
    result={}
    for key in EFFORT_KEYS[2:]:
        first=sum(r['efforts'][key]['baseline'] for r in rows)/3 if evaluated else None
        second=sum(r['efforts'][key]['candidate'] for r in rows)/3 if evaluated else None
        result[key]={'baseline_mean':first,'candidate_mean':second,'passed':bool(evaluated and (second==0 if first==0 else second<=1.05*first))}
    return result
def comparison_gate(seeds,candidate,baseline,own,*,exploration=False):
    required=['calibration_'+('continuation' if candidate=='learned_continuation' else 'sparse'),'prediction','nominal_guard',candidate,baseline]
    if exploration: required.insert(0,'calibration_sparse')
    eligible=complete_matrix(seeds,required);rows=[]
    for sr in seeds:
        ev=sr.get('evaluations',{});first=ev.get(baseline,{});second=ev.get(candidate,{})
        a,c=first.get('tracking_rmse_rad'),second.get('tracking_rmse_rad')
        ax,cx=first.get('tracking_rmse_by_axis_rad'),second.get('tracking_rmse_by_axis_rad')
        valid=eligible and all(nonnegative_pair(v) for v in (ax,cx)) and all(finite(x) and x>=0 for x in (a,c))
        prediction=[True,True]
        if exploration:
            pm=ev.get('prediction',{}).get('velocity_prediction_rmse',{});pn,pc=pm.get(baseline),pm.get(candidate)
            valid=valid and nonnegative_pair(pn) and nonnegative_pair(pc)
            prediction=[valid and pc[i]<=.8*pn[i] for i in range(2)]
        efforts={}
        for key in EFFORT_KEYS[2:]:
            x,y=first.get('control_effort',{}).get(key),second.get('control_effort',{}).get(key)
            okay=first.get('actual_effort_complete') is True and second.get('actual_effort_complete') is True and nonnegative_pair(x) and nonnegative_pair(y)
            valid=valid and okay;efforts[key]={'baseline':sum(x) if okay else None,'candidate':sum(y) if okay else None}
        rows.append({'seed':sr['seed'],'eligible':bool(valid),'baseline_tracking':a,'candidate_tracking':c,
            'baseline_axis_tracking':ax,'candidate_axis_tracking':cx,'prediction_axes_passed':prediction,
            'joint_tracking_passed':bool(valid and (c<a if exploration else c<=a)),
            'axis_tracking_passed':[bool(valid and (cx[i]<ax[i] if exploration else cx[i]<=ax[i])) for i in range(2)],'efforts':efforts})
    evaluated=bool(own['passed'] and eligible and all(r['eligible'] for r in rows))
    first=sum(r['baseline_tracking'] for r in rows)/3 if evaluated else None
    second=sum(r['candidate_tracking'] for r in rows)/3 if evaluated else None
    change=guard.improvement(second,first) if evaluated else None
    axis=[]
    for i in range(2):
        a=sum(r['baseline_axis_tracking'][i] for r in rows)/3 if evaluated else None
        c=sum(r['candidate_axis_tracking'][i] for r in rows)/3 if evaluated else None
        delta=guard.improvement(c,a) if evaluated else None
        axis.append({'axis':i,'baseline_raw_mean':a,'candidate_raw_mean':c,'improvement':delta,
            'passed':bool(evaluated and (delta is not None and delta>=.20 if exploration else all(r['axis_tracking_passed'][i] for r in rows)))})
    efforts=effort_gates(rows,evaluated)
    passed=evaluated and change is not None and change>=(.20 if exploration else .05) and all(r['joint_tracking_passed'] and all(r['axis_tracking_passed']) and all(r['prediction_axes_passed']) for r in rows) and all(g['passed'] for g in efforts.values()) and (not exploration or all(g['passed'] for g in axis))
    return {'candidate':candidate,'baseline':baseline,'evaluated':evaluated,'passed':bool(passed),'body_contribution_passed':own['passed'],
        'required_trials':required,'required_trials_complete':eligible,'per_seed':rows,'baseline_raw_tracking_mean':first,
        'candidate_raw_tracking_mean':second,'joint_tracking_mean_improvement':change,'axis_tracking_gates':axis,
        'actual_effort_gates':efforts,'intervention_boundary':'2/8 plus fixed native q/v veto bundle; no isolated pulse or threshold claim' if exploration else 'Selected PD candidate2, matched final task permission.'}
def scientific_gates(seeds):
    body={group:body_gate(seeds,group) for group in LEARNED}
    return {'body_contribution':body,'exploration_intervention':comparison_gate(seeds,'learned_continuation','learned_sparse',body['continuation'],exploration=True),
        'selected_pd_comparison':{group:comparison_gate(seeds,model,'PDselected',body[group]) for group,model in LEARNED.items()},
        'matrix_complete':complete_matrix(seeds,KINDS)}

def verify_row_identity(row,seed,kind,checks):
    index=row.get('step_index');tid=f'seed{seed}_{kind}'
    checks.compare(row,{'trial_id':tid,'seed':seed,'kind':kind},tid+'/identity')
    if 'collector_exception' not in row:
        checks.compare(row['joint_indices'],[0,1],tid+'/joint_identity')
        checks.check(type(index) is int and 0<=index<100+duration(kind),'fixed_trial_index',tid)
        checks.compare(row['shared_transition_id'],tid+':'+str(index),tid+'/original_transition_id')
        checks.compare(row['phase'],phase_at(kind,index),tid+'/original_phase')
    return tid

def audit_physical_base(sr,episode,rows,ranges,checks):
    """Non-MPC native, effort, study and actual paid interval reconstruction."""
    seed,kind=episode['seed'],episode['kind'];tid=f'seed{seed}_{kind}'
    checks.compare(episode,{'trial_id':tid,'maximum_control_steps':100+duration(kind)},tid+'/plan')
    regular=[r for r in rows if 'collector_exception' not in r];exceptions=[r for r in rows if 'collector_exception' in r]
    checks.check(len(exceptions)<=1 and (not exceptions or rows[-1] is exceptions[0]),'single_final_exception',tid)
    checks.check(episode['status'] in ('completed','terminated','exception','blocked','incomplete'),'known_status',tid)
    ev=sr['evaluations'].get(kind,{})
    if episode['status']=='blocked':
        checks.check(not rows,'blocked_no_native_rows',tid)
        for key in ('control_calls_attempted','control_steps','physics_steps'): checks.compare(episode[key],0,tid+'/zero/'+key)
        for phase in PHASES: checks.compare(episode['phase_budgets'][phase],{'control_calls_attempted':0,'control_steps':0,'physics_steps':0},tid+'/zero/'+phase)
        checks.compare(ev,{'status':'blocked','completed':False},tid+'/blocked_eval')
        return {'eligible':False,'completed':False,'status':'blocked'},regular,exceptions
    counter={'physics':0};previous=None;study=terminal=False
    phase_rows={p:0 for p in PHASES};phase_physics={p:0 for p in PHASES}
    effort={p:guard.new_effort() for p in PHASES};risk={p:common.new_risk() for p in ('full',*PHASES)}
    tracking=[];partial=[];saturation=[0,0]
    checks.compare([r['step_index'] for r in regular],list(range(len(regular))),tid+'/contiguous_rows')
    for row in regular:
        index=row['step_index'];location=tid+':'+str(index);phase=phase_at(kind,index)
        verify_row_identity(row,seed,kind,checks)
        checks.check(not study and not terminal,'no_rows_after_stop',location)
        n=guard.verify_transition(row,previous,counter,ranges,checks,location)
        phase_rows[phase]+=1;phase_physics[phase]+=n;guard.add_effort(effort[phase],row)
        for p in ('full',phase): common.record_risk(risk[p],row,ranges,joint_index=0)
        previous=row['observation_after'];terminal=row['diagnostics']['terminated']
        if index<100:
            checks.compare(row['requested_torque'],[0.]*8,location+'/zero_prefix')
            checks.compare(row['planned_torque'],[0.]*8,location+'/prefix_plan')
            for field in ('target_q','exploration_diagnostics','model_update','planner_decision'):
                checks.compare(row[field],None,location+'/prefix_'+field)
            checks.compare(row['predicted_next_qv'],{},location+'/no_prefix_prediction')
            continue
        study=guard.verify_study(row,sr['reference_q'],checks,location)
        if kind in CAL_GROUPS or kind=='prediction':
            q,v=[row['observation_before'][k][:2] for k in ('joint_position','joint_velocity')]
            command,diag=exploration_command(kind,index-100,sr['direction'],q,v,sr['reference_q'])
            checks.check(set(row['exploration_diagnostics'])==set(diag),'exact_public_exploration_fields',location)
            checks.compare(row['exploration_diagnostics'],diag,location+'/native_veto')
            checks.compare(row['planned_torque'],diag['planned_nm']+[0.]*6,location+'/original_plan')
            checks.compare(row['requested_torque'],command+[0.]*6,location+'/final_known_request')
            checks.compare(row['target_q'],None,location+'/no_exploration_target')
            checks.compare(row['planner_decision'],None,location+'/no_exploration_planner')
        else:
            checks.compare(row['exploration_diagnostics'],None,location+'/no_control_veto')
            target=[sr['reference_q'][i]+sr['direction'][i]*(.04 if index<200 else .08) for i in range(2)]
            checks.compare(row['target_q'],target,location+'/fixed_current_target')
            q,v=[row['observation_before'][k][:2] for k in ('joint_position','joint_velocity')]
            raw=[64.*(target[i]-q[i])-[0.,4.][i]*v[i] for i in range(2)] if kind=='PDselected' else None
            command=[max(-.5,min(.5,x)) for x in raw] if raw is not None else [0.,0.]
            checks.compare(row['requested_torque'],command+[0.]*6,location+'/feedback_request')
            checks.compare(row['planned_torque'],row['requested_torque'],location+'/control_plan_equal_request')
            checks.compare(row['raw_pd_torque_nm'],raw,location+'/PD_raw')
            checks.compare(row['model_update'],None,location+'/no_control_update')
            checks.compare(row['predicted_next_qv'],{},location+'/no_PD_zero_body_prediction')
            checks.compare(row['model_input_diagnostics'],{},location+'/no_PD_zero_model_input')
            if n==10:
                tracking.append([row['observation_after']['joint_position'][i]-target[i] for i in range(2)])
                for i in range(2): saturation[i]+=abs(command[i])==.5
            else: partial.append({'step_index':index,'target_q':target,'errors_rad':[row['observation_after']['joint_position'][i]-target[i] for i in range(2)],'executed_substeps':n})
    for phase in PHASES:
        cap=100 if phase=='prefix' else duration(kind) if phase==phase_at(kind,100) else 0
        budget=episode['phase_budgets'][phase]
        checks.check(all(type(budget[k]) is int and 0<=budget[k]<=cap for k in ('control_calls_attempted','control_steps'))
            and type(budget['physics_steps']) is int and 0<=budget['physics_steps']<=10*cap,'phase_cost_cap',tid+'/'+phase)
        checks.check(budget['control_calls_attempted']>=budget['control_steps']>=phase_rows[phase]
            and phase_physics[phase]<=budget['physics_steps']<=10*budget['control_calls_attempted'],'paid_not_replaced_by_saved_rows',tid+'/'+phase)
    for key in ('control_calls_attempted','control_steps','physics_steps'):
        checks.compare(episode[key],sum(budget[key] for budget in episode['phase_budgets'].values()),tid+'/ledger/'+key)
    missing=episode['physics_steps']-counter['physics']
    checks.check(0<=missing<=10 and 0<=episode['control_steps']-len(regular)<=1,'single_failed_interval_paid_cost',tid)
    checks.check(type(episode['returned_steps']) is int and type(episode['written_returned_steps']) is int
        and 0<=episode['written_returned_steps']<=episode['returned_steps']<=episode['control_steps']
        and len(regular)<=episode['returned_steps']<=len(regular)+1,'returned_written_partition',tid)
    checks.compare(episode['returned_unwritten_steps'],episode['returned_steps']-episode['written_returned_steps'],tid+'/unwritten')
    checks.check(type(episode['unreturned_physics_steps']) is int and 0<=episode['unreturned_physics_steps']<=missing,'unreturned_paid_cost',tid)
    for ex in exceptions:
        verify_row_identity(ex,seed,kind,checks)
        guard.verify_exception_native_mapping(ex,checks,tid+'/exception')
        guard.verify_exception_paid_counters(ex,episode,checks,tid+'/exception')
    full=(episode['status']=='completed' and len(regular)==100+duration(kind) and not exceptions and not study and not terminal
        and episode['control_calls_attempted']==episode['control_steps']==len(regular) and episode['physics_steps']==10*len(regular)
        and all(r['diagnostics']['executed_substeps']==10 for r in regular))
    checks.check(episode['status']!='completed' or full,'complete_claim_requires_full_nonterminal_trial',tid)
    checks.compare(episode['completed'],full,tid+'/episode_completed');checks.compare(ev['completed'],full,tid+'/eval_completed')
    for field in ('status','study_abort','environment_terminated','environment_stop_reason','collector_exception'):
        checks.compare(ev[field],episode[field],tid+'/outcome/'+field)
    checks.compare(episode['reason'],episode['environment_stop_reason'] if episode['environment_terminated'] else
        episode['study_abort'] if episode['study_abort'] is not None else episode['collector_exception'],tid+'/reason_precedence')
    if not exceptions:
        checks.compare(episode['returned_steps'],len(regular),tid+'/returned')
        checks.compare(episode['written_returned_steps'],len(regular),tid+'/written')
        checks.compare(episode['study_abort'],regular[-1].get('study_abort') if regular else None,tid+'/stop_saved')
        checks.compare(episode['environment_terminated'],terminal,tid+'/environment_terminal')
    if episode.get('environment_fingerprint_before') is not None:
        checks.compare(episode['environment_fingerprint_after'],episode['environment_fingerprint_before'],tid+'/fixed_plant')
        if sr.get('environment_fingerprint_before') is not None:
            checks.compare(episode['environment_fingerprint_before'],sr['environment_fingerprint_before'],tid+'/common_plant')
    if kind in ('PDselected','zero'):
        checks.compare(ev['tracking_rmse'],guard.paired_rmse(tracking),tid+'/tracking')
        checks.compare(ev['metric_control_step_count'],len(tracking),tid+'/tracking_complete_count')
        checks.compare(ev['partial_interval_target_errors_rad'],partial,tid+'/partial_scores')
        checks.compare(ev['saturated_control_steps_per_axis'],saturation,tid+'/saturation')
        checks.compare(ev['diagnostic_prediction_accounting'],b.successful_meter(0),tid+'/no_body_predict_cost')
        checks.compare(ev['planning_accounting'],{**guard.empty_meter(),'scalar_counts_complete':True,
            'scalar_counts_is_lower_bound':False,'unknown_failed_planner_calls':0},tid+'/no_MPC_cost')
        for key in ('planner_attempt_count','planner_decision_count','failed_planner_attempts','planner_fallbacks'):
            checks.compare(ev[key],0,tid+'/no_MPC/'+key)
    efforts={p:guard.reconcile_effort(ev,p,effort[p],episode['phase_budgets'][p]['physics_steps'],phase_physics[p],exceptions,checks,tid+'/effort/'+p) for p in PHASES}
    checks.compare(ev['control_effort'],ev['phase_effort']['control'],tid+'/control_effort_alias')
    paid=episode['phase_budgets']['control']['physics_steps'];actual=ev['phase_actual_effort_substeps']['control']
    checks.compare(ev['actual_effort_complete'],actual==paid,tid+'/actual_complete')
    checks.compare(ev['actual_effort_is_lower_bound'],actual<paid,tid+'/actual_lower_bound')
    checks.compare(ev['actual_control_effort_substeps'],actual,tid+'/actual_substeps')
    checks.compare(ev['missing_control_effort_substeps'],paid-actual,tid+'/unknown_actual')
    checks.check(not episode.get('risk_telemetry_complete',False) or missing==0 and not exceptions,'risk_not_complete_after_missing_telemetry',tid)
    for p in risk:
        absent=missing if p=='full' else episode['phase_budgets'][p]['physics_steps']-phase_physics[p]
        risk[p].update(telemetry_missing_paid_substeps=absent,reconstruction_complete=absent==0,
            request_applied_mismatch_count_is_lower_bound=absent>0)
    metric=guard.paired_rmse(tracking)
    derived={'eligible':full,'completed':full,'status':episode['status'],
        'tracking_rmse_rad':None if metric is None else metric['joint'],'tracking_rmse_by_axis_rad':None if metric is None else metric['per_axis'],
        'control_effort':ev['control_effort'],'actual_effort_complete':ev['actual_effort_complete'],'risk':risk,
        'effort_audit':efforts,'complete_score_endpoints':len(tracking),'partial_score_endpoints':len(partial),
        'unreconstructed_physics_substeps':missing,'paid_budget':{k:episode[k] for k in ('control_calls_attempted','control_steps','physics_steps')}}
    return derived,regular,exceptions

def reference_binding(sr,regular,episode,ranges,checks):
    if len(regular)<100: return
    tid=episode['trial_id'];endpoint=regular[99]['observation_after'];q,v=[endpoint[k][:2] for k in ('joint_position','joint_velocity')]
    if regular[99]['diagnostics']['terminated']: return
    directions=[1 if ranges[i][1]-q[i]>=q[i]-ranges[i][0] else -1 for i in range(2)]
    checks.compare(sr['reference_q'],q,tid+'/native_reference_q')
    checks.compare(sr['native_prefix_velocity'],v,tid+'/native_reference_velocity')
    checks.compare(sr['direction'],directions,tid+'/public_reference_direction')
    checks.compare(sr['public_joint_ranges'],ranges[:2],tid+'/public_reference_ranges')
    if len(regular)>100:
        checks.compare(regular[100]['observation_before'],endpoint,tid+'/prefix_active_native_boundary')
    bindings=sr.get('fresh_prefix_bindings',{});binding=bindings.get(episode['kind'])
    if binding is not None:
        checks.compare(binding,{'reference_q':q,'native_velocity':v,'direction':directions,
            'public_joint_ranges':ranges[:2],'environment_fingerprint':episode['environment_fingerprint_before'],
            'source_native_pair_exact':True},tid+'/fresh_prefix_binding')
    elif len(regular)>100: checks.check(False,'active_trial_requires_fresh_binding',tid)

def dose_record(regular,qref,ranges):
    result={'complete_intervals':0,'nonzero_start_guard_intervals_per_axis':[0,0],
        'planned_absolute_nm_s':[0.,0.],'planned_squared_nm2_s':[0.,0.],
        'requested_absolute_nm_s':[0.,0.],'requested_squared_nm2_s':[0.,0.],
        'start_guard_absolute_nm_s':[0.,0.],'start_guard_squared_nm2_s':[0.,0.],
        'actual_absolute_nm_s':[0.,0.],'actual_squared_nm2_s':[0.,0.]}
    for row in regular:
        if row['step_index']<100 or row['diagnostics']['executed_substeps']!=10: continue
        result['complete_intervals']+=1
        q=row['observation_before']['joint_position'][:2];u=row['requested_torque'][:2]
        mapped=guard.describe_input(q,u,('known_angle_guard',ranges))['projected_start_nm']
        plans=row['planned_torque'][:2];diag=row.get('exploration_diagnostics') or {}
        for i in range(2):
            result['nonzero_start_guard_intervals_per_axis'][i]+=mapped[i]!=0.
            for prefix,values in (('planned',plans),('requested',u),('start_guard',mapped)):
                result[prefix+'_absolute_nm_s'][i]+=abs(values[i])*.02
                result[prefix+'_squared_nm2_s'][i]+=values[i]**2*.02
            actual=[step[i] for step in row['diagnostics']['applied_torque_history']]
            result['actual_absolute_nm_s'][i]+=sum(abs(x) for x in actual)*.002
            result['actual_squared_nm2_s'][i]+=sum(x*x for x in actual)*.002
    return result

def excitation_qualified(dose,*,calibration):
    return (type(dose) is dict and all(type(x) is int and x>=1 for x in
        dose.get('nonzero_start_guard_intervals_per_axis',[])) and
        len(dose.get('nonzero_start_guard_intervals_per_axis',[]))==2 and
        (not calibration or nonnegative_pair(dose.get('actual_absolute_nm_s')) and
         all(x>0. for x in dose['actual_absolute_nm_s'])))

def metric_records(errors):
    return {field:{name:guard.paired_rmse(values[key]) for name,values in errors.items()}
            for field,key in (('position_prediction_rmse','q'),('velocity_prediction_rmse','v'))}

def add_prediction_errors(errors,partial,row,predictions):
    q,v=[row['observation_after'][key][:2] for key in ('joint_position','joint_velocity')]
    n=row['diagnostics']['executed_substeps']
    for name,pred in predictions.items():
        qe=[q[i]-pred[0][i] for i in range(2)];ve=[v[i]-pred[1][i] for i in range(2)]
        if n==10:
            values=errors.setdefault(name,{'q':[],'v':[]});values['q'].append(qe);values['v'].append(ve)
        else:
            partial.append({'step_index':row['step_index'],'model':name,'executed_substeps':n,
                'position_error_rad':qe,'velocity_error_rad_s':ve})

def audit_excitation(sr,episode,regular,exceptions,ranges,checks):
    kind=episode['kind'];tid=episode['trial_id'];ev=sr['evaluations'][kind]
    # Dose is calculated only on original complete returned active intervals.
    # On a write/update failure the last returned native interval may not have
    # a regular row; its independently retained telemetry is separately used.
    dose_rows=list(regular);veto=[0,0]
    for row in regular:
        if row['step_index']>=100:
            for i,x in enumerate(row['exploration_diagnostics']['command_vetoed']): veto[i]+=x
    if exceptions:
        ex=exceptions[0];duplicate=any(r['step_index']==ex.get('step_index') for r in regular)
        if not duplicate and ex.get('step_index') is not None and ex['step_index']>=100:
            q,v=[ex['observation_before'][key][:2] for key in ('joint_position','joint_velocity')]
            command,diag=exploration_command(kind,ex['step_index']-100,sr['direction'],q,v,sr['reference_q'])
            checks.compare(ex['exploration_diagnostics'],diag,tid+'/failed_public_exploration')
            checks.compare(ex['requested_torque'],command+[0.]*6,tid+'/failed_final_request')
            checks.compare(ex['planned_torque'],diag['planned_nm']+[0.]*6,tid+'/failed_planned_request')
            for i,x in enumerate(diag['command_vetoed']): veto[i]+=x
            returned=ex.get('returned_step_diagnostics')
            if returned is not None and returned.get('executed_substeps')==10 and ex.get('model_input_diagnostics'):
                # The dose is accumulated before a complete RLS attempt.
                dose_rows.append(dict(ex,diagnostics=returned))
    dose=dose_record(dose_rows,sr['reference_q'],ranges[:2])
    checks.compare(ev['excitation'],dose,tid+'/independent_original_dose')
    checks.compare(ev['command_veto_count_per_axis'],veto,tid+'/public_veto_count')
    if kind in CAL_GROUPS:
        record=sr['calibrations'][CAL_GROUPS[kind]]
        checks.compare(record['excitation'],dose,tid+'/calibration_dose_alias')
        checks.compare(record['command_veto_count_per_axis'],veto,tid+'/calibration_veto_alias')
    return dose

def replay_failed_atomic_update(ex,regular,episode,state,qref,checks,tid):
    """Verify one failed zero/two-head attempt from retained original labels."""
    duplicate=any(r['shared_transition_id']==ex.get('shared_transition_id') for r in regular)
    snapshot=ex.get('model_snapshot_after');update=ex.get('model_update')
    if snapshot is None: return 0,False
    delta=snapshot['vector_update_count']-state['count']
    checks.check(type(delta) is int and delta in (0,1),'failed_atomic_zero_or_two_heads',tid)
    returned=ex.get('returned_step_diagnostics')
    full=(not duplicate and type(ex.get('step_index')) is int and ex['step_index']==len(regular)
          and ex['step_index']>=100 and returned is not None and returned.get('executed_substeps')==10
          and episode['control_steps']==len(regular)+1
          and episode['physics_steps']-sum(r['diagnostics']['executed_substeps'] for r in regular)==10
          and ex.get('observation_after_retrieval_error') is None)
    before=deepcopy(state)
    if delta==1:
        checks.check(full,'commit_requires_original_complete_returned_label',tid)
        if full:
            if update is not None: b.replay_update(update,ex,state,qref,checks,tid+'/saved_commit')
            else:
                q,v=[ex['observation_before'][key][:2] for key in ('joint_position','joint_velocity')]
                x=b.features(qref,q,v,ex['requested_torque'][:2],state['ranges'])
                proposals=[b.pair_support.replay_rls(state['theta'][i],state['covariance'][i],x[i],
                    ex['observation_after']['joint_velocity'][i]) for i in range(2)]
                state['theta']=[p[0] for p in proposals];state['covariance']=[p[1] for p in proposals];state['count']+=1
    elif type(update) is dict and update.get('updated') is True:
        checks.check(duplicate,'duplicate_saved_update_only',tid)
        if duplicate:
            original=next(r for r in regular if r['shared_transition_id']==ex['shared_transition_id'])
            checks.compare(update,original['model_update'],tid+'/duplicate_update')
    failure=ex.get('failure_accounting',{});ledger=failure.get('pair_update_accounting')
    if ledger is None and type(failure.get('structured_failure')) is dict and failure['structured_failure'].get('type')=='PairUpdateError': ledger=failure['structured_failure']
    if ledger is not None:
        checks.compare(ledger['committed_scalar_updates'],2*delta,tid+'/failed_commit_heads')
        checks.compare(ledger['snapshot_after_attempt'],snapshot,tid+'/failed_ledger_snapshot')
        proposals=ledger.get('proposed_outputs',[])
        checks.check(type(proposals) is list and len(proposals)<=2 and (delta==0 or len(proposals)==2),
                     'failed_atomic_proposal_bound',tid)
        if full:
            q,v=[ex['observation_before'][key][:2] for key in ('joint_position','joint_velocity')]
            x=b.features(qref,q,v,ex['requested_torque'][:2],before['ranges'])
            for i,item in enumerate(proposals):
                theta,cov,residual=b.pair_support.replay_rls(before['theta'][i],before['covariance'][i],x[i],
                    ex['observation_after']['joint_velocity'][i])
                checks.compare(item,{'output_index':i,'features':x[i],'observed_next_v_rad_s':ex['observation_after']['joint_velocity'][i],
                    'preupdate_error_rad_s':residual,'proposed_coefficients':theta,'proposed_covariance':cov,
                    'committed':delta==1},tid+f'/failed_proposal{i}')
    b.verify_snapshot(snapshot,state,qref,checks,tid+'/failed_published_state',True)
    return delta,full

def audit_calibration(sr,episode,rows,ranges,checks):
    tid=episode['trial_id'];group=CAL_GROUPS[episode['kind']];model=LEARNED[group]
    base,regular,exceptions=audit_physical_base(sr,episode,rows,ranges,checks)
    reference_binding(sr,regular,episode,ranges,checks)
    record=sr['calibrations'][group];ev=sr['evaluations'][episode['kind']]
    checks.compare(record,{'status':episode['status'],'reason':episode['reason']},tid+'/calibration_outcome')
    state=None;ids=[];errors={};partial=[]
    if record['initial_model'] is not None:
        state=b.initial_state(ranges[:2]);qref=sr['reference_q']
        b.verify_snapshot(record['initial_model'],state,qref,checks,tid+'/cold_generic_prior',True)
        for row in regular:
            if row['step_index']<100:
                checks.compare(row['model_snapshot_after'],None,tid+'/no_prefix_model');continue
            q,v=[row['observation_before'][key][:2] for key in ('joint_position','joint_velocity')]
            inputs={model:guard.describe_input(q,row['requested_torque'][:2],('known_angle_guard',ranges[:2]))}
            checks.compare(row['model_input_diagnostics'],inputs,tid+'/own_start_guard')
            if row['diagnostics']['executed_substeps']==10:
                pq,pv=b.predict(state['observed_theta'],ranges[:2],qref,q,v,row['requested_torque'][:2])
                checks.compare(row['predicted_next_qv'],{model:[pq,pv]},tid+'/one_preupdate_prediction')
                ids.append(row['shared_transition_id'])
                b.replay_update(row['model_update'],row,state,qref,checks,tid+'/atomic_rls/'+str(row['step_index']))
                add_prediction_errors(errors,partial,row,{model:[pq,pv]})
            else:
                checks.compare(row['model_update'],{'updated':False,'phase':'partial_calibration_interval',
                    'executed_substeps':row['diagnostics']['executed_substeps']},tid+'/partial_no_update')
                checks.compare(row['predicted_next_qv'],{},tid+'/partial_no_rls_prediction')
            b.verify_snapshot(row['model_snapshot_after'],state,qref,checks,tid+'/published/'+str(row['step_index']),True)
        extra_attempt=0
        if exceptions:
            ex=exceptions[0];_,full=replay_failed_atomic_update(ex,regular,episode,state,qref,checks,tid)
            duplicate=ex.get('shared_transition_id') in ids
            if full and not duplicate:
                checks.check(record['attempted_vector_updates'] in (len(ids),len(ids)+1),'single_failed_update_attempt',tid)
                extra_attempt=record['attempted_vector_updates']-len(ids)
                if extra_attempt: ids.append(ex['shared_transition_id'])
        attempted=len(ids)
        meter=b.successful_meter(attempted)
        if exceptions:
            saved=record['rls_prediction_accounting'];failure=exceptions[0].get('failure_accounting',{})
            # An attempt may fail before the existing old-state prediction or
            # at its head; retain that explicit paid boundary instead of zero.
            success=attempted-extra_attempt
            if extra_attempt and saved['pair_prediction_successes']<attempted:
                if saved['pair_prediction_attempts']==attempted:
                    meter=b.failed_meter(b.successful_meter(success),failure,checks,tid+'/failed_internal_prediction')
                else:
                    checks.compare(saved['pair_prediction_attempts'],success,tid+'/failure_before_internal_prediction')
                    meter=b.successful_meter(success)
            checks.compare(exceptions[0]['rls_prediction_accounting'],saved,tid+'/failure_meter_binding')
        guard.validate_meter(record['rls_prediction_accounting'],checks,tid+'/rls_internal_meter',400)
        checks.compare(record['rls_prediction_accounting'],meter,tid+'/exact_internal_prediction_cost')
        checks.compare(record['source_transition_ids'],ids,tid+'/own_original_source_ids')
        checks.compare(record['attempted_vector_updates'],attempted,tid+'/attempted_vectors')
        checks.compare(record['committed_vector_updates'],state['count'],tid+'/committed_vectors')
        checks.compare(record['committed_scalar_updates'],2*state['count'],tid+'/committed_scalars')
        b.verify_snapshot(record['model_snapshot'],state,qref,checks,tid+'/final_trainable',True)
        ready=base['completed'] and state['count']==400
        checks.compare(record['completed'],ready,tid+'/publish_requires_full400')
        if ready:
            b.verify_snapshot(record['frozen_model'],state,qref,checks,tid+'/frozen',False)
            b.verify_snapshot(sr['learned_models'][model],state,qref,checks,tid+'/public_frozen_model',False)
        else:
            checks.compare(record['frozen_model'],None,tid+'/no_failed_frozen_model')
            checks.check(model not in sr['learned_models'],'no_failed_model_publication',tid)
        dose=audit_excitation(sr,episode,regular,exceptions,ranges,checks)
    else:
        checks.check(not any(r['step_index']>=100 for r in regular),'no_active_rows_without_cold_model',tid)
        for field in ('attempted_vector_updates','committed_vector_updates','committed_scalar_updates'):
            checks.compare(record[field],0,tid+'/uncreated/'+field)
        checks.compare(record['source_transition_ids'],[],tid+'/uncreated_sources')
        checks.compare(record['rls_prediction_accounting'],b.successful_meter(0),tid+'/uncreated_meter')
        checks.compare(record['model_snapshot'],None,tid+'/uncreated_snapshot')
        checks.compare(record['frozen_model'],None,tid+'/uncreated_frozen');ready=False;meter=b.successful_meter(0);dose=None
    checks.compare(ev['model_updates'],0 if state is None else 2*state['count'],tid+'/eval_scalar_updates')
    checks.compare(ev['diagnostic_prediction_accounting'],b.successful_meter(0),tid+'/no_extra_calibration_prediction')
    if not exceptions:
        checks.compare(ev,metric_records(errors),tid+'/preupdate_metrics')
        checks.compare(ev['metric_prediction_step_count'],{n:len(x['v']) for n,x in errors.items()},tid+'/preupdate_counts')
        checks.compare(ev['partial_endpoint_prediction_errors'],partial,tid+'/partial_prediction')
    qualified=excitation_qualified(dose,calibration=True)
    base.update(eligible=bool(ready and qualified),calibration_model_ready=ready,excitation=dose,
        excitation_qualified=qualified,new_vector_updates=0 if state is None else state['count'],
        new_scalar_updates=0 if state is None else 2*state['count'],rls_prediction_accounting=meter)
    return state if ready else None,base

def audit_prediction(sr,episode,rows,states,ranges,checks):
    tid=episode['trial_id'];ev=sr['evaluations']['prediction']
    base,regular,exceptions=audit_physical_base(sr,episode,rows,ranges,checks)
    if episode['status']=='blocked':
        checks.check(not any(name in states for name in LEARNED.values()) or
            episode['reason'].get('type')=='ArchiveAborted','only_dependency_or_archive_block',tid)
        return base
    checks.check(any(name in states for name in LEARNED.values()),'common_prediction_requires_learned_model',tid)
    reference_binding(sr,regular,episode,ranges,checks)
    available=[name for name in MODELS if name in states];qref=sr['reference_q']
    fingerprints={name:digest(b.parameter_record(qref,states[name],True)) for name in available}
    errors={};partial=[]
    for row in regular:
        active=row['step_index']>=100
        checks.compare(row['available_models'],available if active else [],tid+'/availability_from_complete_calibration')
        checks.compare(row['model_fingerprints'],fingerprints if active else {},tid+'/immutable_model_hashes')
        checks.compare(row['model_update'],None,tid+'/no_prediction_update')
        checks.compare(row['model_snapshot_after'],None,tid+'/no_prediction_calibrator')
        if not active:
            checks.compare(row['model_input_diagnostics'],{},tid+'/prefix_no_input');continue
        q,v=[row['observation_before'][key][:2] for key in ('joint_position','joint_velocity')]
        u=row['requested_torque'][:2]
        predicted={name:b.predict(states[name]['observed_theta'],ranges[:2],qref,q,v,u) for name in available}
        predicted['persistence']=([q[i]+.02*v[i] for i in range(2)],v)
        checks.check(set(row['predicted_next_qv'])==set(predicted),'exact_available_predictor_set',tid)
        checks.compare(row['predicted_next_qv'],predicted,tid+'/single_prediction_each')
        checks.compare(row['model_input_diagnostics'],{name:guard.describe_input(q,u,('known_angle_guard',ranges[:2]))
            for name in available},tid+'/causal_public_inputs')
        add_prediction_errors(errors,partial,row,predicted)
    for ex in exceptions:
        if ex.get('step_index') is not None and ex['step_index']>=100:
            checks.compare(ex['available_models'],available,tid+'/failed_available_models')
            checks.compare(ex['model_fingerprints'],fingerprints,tid+'/failed_frozen_hashes')
            saved=ex.get('predicted_next_qv',{});names=list(saved)
            checks.check(names==available[:len(names)] or names==[*available,'persistence'],
                'failed_predictions_are_causal_ordered_prefix',tid)
            q,v=[ex['observation_before'][key][:2] for key in ('joint_position','joint_velocity')]
            for name in names:
                predicted=([q[i]+.02*v[i] for i in range(2)],v) if name=='persistence' else \
                    b.predict(states[name]['observed_theta'],ranges[:2],qref,q,v,ex['requested_torque'][:2])
                checks.compare(saved[name],predicted,tid+'/failed_single_prediction/'+name)
        checks.compare(ex['model_update'],None,tid+'/failed_no_update')
    checks.compare(ev['available_models'],available,tid+'/evaluation_available_models')
    checks.compare(ev['model_availability'],{name:'available' if name in available else 'unavailable' for name in MODELS},tid+'/availability_status')
    checks.compare(ev['model_updates'],0,tid+'/frozen_prediction_zero_updates')
    guard.verify_diagnostic_accounting(ev,regular,exceptions,'prediction',checks,tid,100)
    if not exceptions:
        checks.compare(ev,metric_records(errors),tid+'/common_scores')
        checks.compare(ev['metric_prediction_step_count'],{name:len(x['v']) for name,x in errors.items()},tid+'/common_prediction_count')
        checks.compare(ev['partial_endpoint_prediction_errors'],partial,tid+'/partial_prediction_not_full_score')
    dose=audit_excitation(sr,episode,regular,exceptions,ranges,checks)
    qualified=excitation_qualified(dose,calibration=False)
    base.update(eligible=bool(base['completed'] and qualified),excitation=dose,excitation_qualified=qualified,
        velocity_prediction_rmse={name:guard.paired_rmse(values['v'])['per_axis'] for name,values in errors.items() if values['v']},
        diagnostic_prediction_accounting=ev['diagnostic_prediction_accounting'])
    return base

def canonical_control_view(sr,episode,rows,kind):
    """Explicit mathematical view, never changes a B scope/global or archive.

    B's fixed coupled9/H15/81-candidate verifier expects one model name and
    two phases. Only C's validated control identity and that model dictionary
    key are renamed; all original native observations/commands remain intact.
    """
    def rename(mapping):
        return {b.MODEL if name==kind else name:deepcopy(value) for name,value in mapping.items()}
    trial=f"seed{episode['seed']}_{b.MODEL}"
    view_episode=deepcopy(episode);view_episode.update(trial_id=trial,kind=b.MODEL)
    view_episode['phase_budgets']={p:deepcopy(episode['phase_budgets'][p]) for p in b.PHASES}
    view_rows=[]
    for original in rows:
        row=deepcopy(original);row.update(trial_id=trial,kind=b.MODEL)
        if row.get('step_index') is not None: row['shared_transition_id']=trial+':'+str(row['step_index'])
        for field in ('predicted_next_qv','model_input_diagnostics'): row[field]=rename(row.get(field,{}))
        view_rows.append(row)
    ev=deepcopy(sr['evaluations'][kind])
    for field in ('position_prediction_rmse','velocity_prediction_rmse','metric_prediction_step_count'):
        ev[field]=rename(ev[field])
    view_sr={'evaluations':{b.MODEL:ev},'fresh_prefix_binding':deepcopy(sr.get('fresh_prefix_bindings',{}).get(kind))}
    source={key:deepcopy(sr[key]) for key in ('seed','reference_q','direction','public_joint_ranges',
        'native_prefix_observation','environment_fingerprint_before')}
    return source,view_sr,view_episode,view_rows

def audit_control(sr,episode,rows,state,ranges,checks):
    kind=episode['kind'];tid=episode['trial_id'];ev=sr['evaluations'][kind]
    checks.check(set(episode['phase_budgets'])==set(PHASES),'exact_C_phase_ledger',tid)
    for phase in ('calibration','prediction'):
        checks.compare(episode['phase_budgets'][phase],{'control_calls_attempted':0,'control_steps':0,'physics_steps':0},tid+'/inactive_phase/'+phase)
        if 'phase_effort' in ev:
            checks.compare(ev['phase_effort'][phase],guard.new_effort(),tid+'/inactive_effort/'+phase)
            checks.compare(ev['phase_actual_effort_substeps'][phase],0,tid+'/inactive_actual/'+phase)
    for row in rows:
        verify_row_identity(row,episode['seed'],kind,checks)
        checks.compare(row['exploration_diagnostics'],None,tid+'/original_no_control_veto')
        checks.compare(row['planned_torque'],row['requested_torque'],tid+'/original_plan_equal_request')
        checks.compare(row['raw_pd_torque_nm'],None,tid+'/original_no_PD_request')
    if episode['status']=='blocked' and 'reference_q' not in sr:
        checks.check(not rows and state is None,'uncreated_model_blocks_control',tid)
        for key in ('control_calls_attempted','control_steps','physics_steps'): checks.compare(episode[key],0,tid+'/blocked_zero_cost')
        return {'eligible':False,'completed':False,'status':'blocked'}
    source,view_sr,view_episode,view_rows=canonical_control_view(sr,episode,rows,kind)
    result=b.audit_control(source,view_sr,view_episode,view_rows,state,ranges,checks)
    regular=[r for r in rows if 'collector_exception' not in r]
    reference_binding(sr,regular,episode,ranges,checks)
    if episode['status']!='blocked':
        errors={};partial=[]
        for row in regular:
            if row['step_index']>=100: add_prediction_errors(errors,partial,row,row['predicted_next_qv'])
        if not any('collector_exception' in r for r in rows):
            checks.compare(ev['metric_prediction_step_count'],{n:len(x['v']) for n,x in errors.items()},tid+'/original_prediction_counts')
            checks.compare(ev['partial_endpoint_prediction_errors'],partial,tid+'/original_partial_predictions')
        for row in regular:
            checks.compare(row['available_models'],[],tid+'/control_not_common_prediction')
            checks.compare(row['model_fingerprints'],{},tid+'/control_common_model_hashes_empty')
            checks.compare(row['model_snapshot_after'],None,tid+'/control_no_calibrator')
        # Rename only the derived current predictor name back for reporting.
        pm=result.get('velocity_prediction_rmse',{})
        result['velocity_prediction_rmse']={kind if name==b.MODEL else name:value for name,value in pm.items()}
    return result

def verify_model_registry(sr,episode,states,before,checks):
    ev=sr['evaluations'].get(episode['kind'],{});tid=episode['trial_id']
    if episode['status']=='blocked': return before
    after={name:digest(b.parameter_record(sr['reference_q'],state,True)) for name,state in states.items()} if 'reference_q' in sr else {}
    expected_before=before if episode['kind'] in CAL_GROUPS else after
    checks.compare(ev['models_before'],expected_before,tid+'/exact_frozen_registry_before')
    checks.compare(ev['models_after'],after,tid+'/exact_frozen_registry_after')
    if episode['kind'] not in CAL_GROUPS:
        checks.compare(ev['model_fingerprint_before'],after.get(episode['kind']),tid+'/current_frozen_before')
        checks.compare(ev['model_fingerprint_after'],after.get(episode['kind']),tid+'/current_frozen_after')
        checks.compare(ev['model_updates'],0,tid+'/no_eval_updates')
    return after

def audit_archive(path,checks,git_root,spec):
    path=Path(path);metadata=require_scope(load_json(path/'metadata.json'),spec)
    ranges,input_hashes=verify_sources(path,metadata,checks,git_root,spec)
    plans=planned_matrix();checks.compare(metadata['planned_episodes'],plans,'exact_24_fixed_plans')
    checks.compare(metadata['planned_episode_count'],24,'fixed_plan_count')
    checks.compare(metadata['reset_seeds'],{str(k):v for k,v in RESET.items()},'fixed_reset_seeds')
    for field,value in {'maximum_control_steps':8100,'maximum_physics_steps':81000,'maximum_vector_updates':2400,
        'maximum_scalar_updates':4800,'maximum_rls_internal_prediction_pair_calls':2400,
        'maximum_independent_prediction_pair_calls':900,'maximum_control_diagnostic_prediction_pair_calls':1800,
        'maximum_mpc_prediction_pair_calls':2187000,'parameter_count_per_output':9,'integration':'endpoint_euler',
        'calibration_data_shared':False,'prior_a_b_raw_replayed':False}.items(): checks.compare(metadata[field],value,'fixed_metadata/'+field)
    checks.compare(metadata['backend'],'synthetic, no physics' if spec.synthetic_fixture else 'MuJoCo CPU','cpu_backend')
    checks.compare(metadata['study_abort_spec'],{'active_only':True,'absolute_q_minus_qref_rad':.12,
        'absolute_velocity_rad_s':1.,'comparison':'>=','any_axis':True,'feedback_action':None,
        'complete_terminal_scored_not_complete':True},'unchanged_research_stop')
    checks.compare(metadata['exploration_veto_spec'],{'velocity_rad_s':.5,'q_minus_qref_rad':.06,'comparison':'>=',
        'per_axis':True,'applied_kinds':['calibration_continuation','prediction'],'control_applied':False},'fixed_exploration_veto')
    checks.compare(metadata['minimum_excitation_qualification'],{'calibration_each_axis_nonzero_start_G_count_min':1,
        'calibration_each_axis_actual_absolute_effort_strictly_positive':True,
        'prediction_each_axis_nonzero_start_G_count_min':1,'rank_threshold':None},'fixed_minimum_excitation')
    episodes=load_json(path/'episodes.json');epmap=b._maps(episodes,'trial_id',{p['trial_id'] for p in plans},'C episodes')
    checks.compare([ep['trial_id'] for ep in episodes],[p['trial_id'] for p in plans],'original_plan_execution_order')
    raw=load_json(path/'seed_results.json');saved={}
    for sr in raw:
        seed=sr['seed'];b._assert(type(seed) is int and seed in RESET and seed not in saved,'Unique C saved seed')
        saved[seed]=sr
    b._assert(list(saved)==list(RESET)[:len(saved)],'C saved seed prefix order')
    groups={p['trial_id']:[] for p in plans};last_order=-1
    order={p['trial_id']:i for i,p in enumerate(plans)}
    for row in b.read_rows((path/'trace.jsonl.gz').read_bytes()):
        tid=row['trial_id'];b._assert(tid in groups and order[tid]>=last_order,'Original fixed C trace trial order')
        b._assert(type(row['seed']) is int and row['seed'] in RESET and row['kind'] in KINDS and tid==f"seed{row['seed']}_{row['kind']}",'Original C trace identity')
        groups[tid].append(row);last_order=order[tid]
    derived=[];total_vector=total_scalar=0;meters={key:0 for key in ('rls','prediction','control_diagnostic','mpc')}
    for seed in RESET:
        sr=saved.get(seed);states={};evaluations={};registry={}
        if sr is None:
            for kind in KINDS:
                ep=epmap[f'seed{seed}_{kind}'];checks.check(ep['status']=='blocked' and not groups[ep['trial_id']],'fatal_remaining_blocked',ep['trial_id'])
                for key in ('control_calls_attempted','control_steps','physics_steps'): checks.compare(ep[key],0,ep['trial_id']+'/fatal_zero_cost')
                evaluations[kind]={'eligible':False,'completed':False,'status':'blocked'}
            derived.append({'seed':seed,'evaluations':evaluations});continue
        checks.compare(sr,{'seed':seed,'reset_seed':RESET[seed]},f'seed{seed}/reset')
        if 'nominal_model' in sr:
            nominal=b.initial_state(ranges[:2]);b.verify_snapshot(sr['nominal_model'],nominal,sr['reference_q'],checks,f'seed{seed}/nominal_generic_prior',False)
        else: nominal=None
        for kind in KINDS:
            ep=epmap[f'seed{seed}_{kind}'];rows=groups[ep['trial_id']];before=dict(registry);failure_start=checks.failed
            # The generic nominal model is created when the first paid native
            # prefix binds. Later calibration starts from the same cold prior.
            if nominal is not None and kind in sr.get('fresh_prefix_bindings',{}): states.setdefault('nominal_guard',nominal)
            if ep['status']=='blocked':
                if kind in MPC_KINDS: result=audit_control(sr,ep,rows,states.get(kind),ranges,checks)
                else: result,_,_=audit_physical_base(sr,ep,rows,ranges,checks)
                if ep['reason'].get('type')!='ArchiveAborted':
                    expected=([f'seed{seed}_calibration_sparse',f'seed{seed}_calibration_continuation'] if kind=='prediction' else
                        [f"seed{seed}_calibration_{kind.removeprefix('learned_')}"] if kind.startswith('learned_') else None)
                    checks.check(expected is not None,'only_actual_model_dependency_block',ep['trial_id'])
                    checks.compare(ep['reason'].get('dependencies'),expected,ep['trial_id']+'/dependency_identity')
                    checks.check(not any(name in states for name in LEARNED.values()) if kind=='prediction' else kind not in states,
                        'missing_dependency_reconstructed',ep['trial_id'])
            elif kind in CAL_GROUPS:
                state,result=audit_calibration(sr,ep,rows,ranges,checks)
                total_vector+=result['new_vector_updates'];total_scalar+=result['new_scalar_updates'];meters['rls']+=result['rls_prediction_accounting']['pair_prediction_attempts']
                if state is not None: states[LEARNED[CAL_GROUPS[kind]]]=state
            elif kind=='prediction':
                result=audit_prediction(sr,ep,rows,states,ranges,checks)
                meters['prediction']+=sr['evaluations'][kind]['diagnostic_prediction_accounting']['pair_prediction_attempts']
            elif kind in MPC_KINDS:
                result=audit_control(sr,ep,rows,states.get(kind),ranges,checks)
                meters['control_diagnostic']+=sr['evaluations'][kind]['diagnostic_prediction_accounting']['pair_prediction_attempts']
                meters['mpc']+=sr['evaluations'][kind]['planning_accounting']['pair_prediction_attempts']
            else:
                result,regular,_=audit_physical_base(sr,ep,rows,ranges,checks)
                reference_binding(sr,regular,ep,ranges,checks)
            registry=verify_model_registry(sr,ep,states,before,checks)
            result['eligible']=bool(result['eligible'] and checks.failed==failure_start)
            evaluations[kind]=result
        checks.check(set(sr['learned_models'])==set(states)&set(LEARNED.values()),'only_complete_models_published',f'seed{seed}')
        derived.append({'seed':seed,'evaluations':evaluations})
    budget={key:sum(ep[key] for ep in episodes) for key in ('control_calls_attempted','control_steps','physics_steps')}
    for key,value in budget.items(): checks.compare(metadata[key],value,'batch_paid_ledger/'+key)
    checks.compare(metadata['model_updates'],total_scalar,'batch_scalar_updates');checks.compare(metadata['vector_model_updates'],total_vector,'batch_vector_updates')
    checks.check(budget['control_calls_attempted']<=8100 and budget['control_steps']<=8100 and budget['physics_steps']<=81000
        and total_vector<=2400 and total_scalar<=4800,'total_fixed_budget_caps')
    for key,cap in (('rls',2400),('prediction',900),('control_diagnostic',1800),('mpc',2187000)):
        checks.check(meters[key]<=cap,'paid_prediction_scope_cap',key)
    checks.compare(metadata['all_trials_successful'],all(ep['status']=='completed' for ep in episodes),'batch_success')
    for label,status in (('completed_trials','completed'),('terminated_trials','terminated'),('exception_trials','exception'),('blocked_trials','blocked')):
        checks.compare(metadata[label],sum(ep['status']==status for ep in episodes),'batch_outcomes/'+label)
    return {'seeds':derived,'episodes':episodes,'input_hashes':input_hashes,
        'budget':{**budget,'model_updates':total_scalar,'vector_model_updates':total_vector},'paid_pair_prediction_attempts':meters,
        'sample_semantics':'New independent C native calibration and shared prediction; no A/B replay or repeated model reporting calls.'}

def audit(path,*,git_root=ROOT,spec=PRODUCTION_SPEC):
    wall,cpu=time.perf_counter(),time.process_time();checks=Checks();result=None;reported=None
    try:
        path=Path(path);metadata=require_scope(load_json(path/'metadata.json'),spec)
        reported={key:metadata.get(key) for key in ('control_calls_attempted','control_steps','physics_steps','model_updates','vector_model_updates')}
        result=audit_archive(path,checks,git_root,spec)
    except (OSError,ValueError,KeyError,TypeError,IndexError,AttributeError,OverflowError,zipfile.BadZipFile,ET.ParseError,EOFError) as exc:
        checks.check(False,'archive_schema_or_read_error',{'type':type(exc).__name__,'message':str(exc)})
    gates=scientific_gates([] if result is None else result['seeds'])
    eligibility=checks.failed==0 and git_root is not None and spec.scientific_gates_frozen and not spec.synthetic_fixture
    for gate in (*gates['body_contribution'].values(),gates['exploration_intervention'],*gates['selected_pd_comparison'].values()):
        gate['validated_pass']=bool(gate['passed'] and eligibility)
    gates['matrix_complete']={'passed':gates['matrix_complete'],'validated_pass':bool(gates['matrix_complete'] and eligibility)}
    gates['data_consistency_verified']=checks.failed==0
    return {'schema_version':1,'created_at_utc':datetime.now(timezone.utc).isoformat(),
        'audit_script_sha256':file_hash(__file__),'audit_dependency_sha256':{n:file_hash(ROOT/n) for n in SUPPORT},
        'immutable_scope':spec.record(),'checks':checks.count,'failed':checks.failed,'violations':checks.violations,
        'maximum_recomputation_difference':checks.maximum_difference,'archive':result,'final_gates':gates,
        'reported_paid_budget_if_replay_incomplete':reported,
        'execution':{'wall_seconds':time.perf_counter()-wall,'cpu_seconds':time.process_time()-cpu,
            'timing_scope':'Entry through report assembly; excludes imports/final JSON writing','python':sys.version,
            'platform':sys.platform if spec.synthetic_fixture else platform.platform(),
            'source_git_verification_enabled':git_root is not None and not spec.synthetic_fixture,
            'physical_simulation_calls':0,'model_parameter_updates':0,'online_model_imports':0,
            'prior_A_B_audit_reexecutions':0,'diagonal_model_refits':0}}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',required=True,type=Path);parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    if args.output.exists(): parser.error('Refuse to overwrite first audit')
    result=audit(args.input)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps({'checks':result['checks'],'failed':result['failed'],'gates':result['final_gates']},allow_nan=False))
    return 0 if result['failed']==0 else 1
if __name__=='__main__': raise SystemExit(main())
