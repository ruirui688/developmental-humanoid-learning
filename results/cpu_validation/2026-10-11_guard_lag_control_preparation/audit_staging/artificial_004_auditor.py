"""Independent standard-library E frozen explicit-history control audit.

The D six selected identity payloads are read only as byte-bound saved states.
No D/C mathematics, refitting, physics or online helper imports are executed.
Formal execution is disabled in ignored staging until root freezes this source.
"""
from __future__ import annotations
from collections import Counter
from dataclasses import dataclass
from datetime import datetime,timezone
import argparse
import gzip
import hashlib
import importlib.util
from itertools import product
import math
from pathlib import Path
import io
import json
import platform
import re
import subprocess
import sys
import time
import zipfile

ROOT=next(p for p in Path(__file__).resolve().parents if (p/'pyproject.toml').is_file())
LAG_SUPPORT='scripts/audit_guard_lag_offline.py'
LAG_SUPPORT_SHA='bede59d0984edddf6d7384b6d11c0beddae711dfcc616571f4bfd9ee8ce3211b'
if hashlib.sha256((ROOT/LAG_SUPPORT).read_bytes()).hexdigest()!=LAG_SUPPORT_SHA:
    raise ValueError('Original independent lag math source identity changed')
spec=importlib.util.spec_from_file_location('_E_original_lag_math',ROOT/LAG_SUPPORT)
lag=importlib.util.module_from_spec(spec);sys.modules[spec.name]=lag;spec.loader.exec_module(lag)
pair,finite=lag.pair,lag.finite
HORIZON=15
AXIS_CANDIDATES=tuple(-.5+.125*i for i in range(9))
CANDIDATES=tuple(product(AXIS_CANDIDATES,repeat=2))
COUNTS=Counter()

def validate(qref,q,v,previous_v,target,previous_torque,ranges):
    try:qref,q,v,previous_v,target,previous_torque=(pair(x) for x in (qref,q,v,previous_v,target,previous_torque))
    except (ValueError,TypeError) as exc:raise ValueError('Explicit finite current and preceding native velocity pairs required') from exc
    if len(ranges)!=2 or any(len(r)!=2 or not all(finite(x) for x in r) or r[0]>=r[1] for r in ranges):
        raise ValueError('Two finite ordered public joint ranges required')
    if any(abs(x)>.5 for x in previous_torque):raise ValueError('Previous torque exceeds fixed permission')
    target_bounds=[(max(qref[i]-.15,ranges[i][0]+.03),min(qref[i]+.15,ranges[i][1]-.03)) for i in range(2)]
    if any(not target_bounds[i][0]<=target[i]<=target_bounds[i][1] for i in range(2)):
        raise ValueError('Current target must be local and within public margin')
    bounds=[(max(qref[i]-.15,ranges[i][0]-.03),min(qref[i]+.15,ranges[i][1]+.03)) for i in range(2)]
    return qref,q,v,previous_v,target,previous_torque,bounds

def candidate_math(theta,ranges,qref,q,v,previous_v,target,previous_torque,torque):
    """Exactly H15 at most. Every candidate starts from the same native history.

    Returns an original candidate record plus diagnostic caller history and
    accounting. Rejected endpoints were computed and paid, but never enter
    approved prediction trajectories or tracking/effort running cost.
    """
    qref,q,v,pv,target,previous,bounds=validate(qref,q,v,previous_v,target,previous_torque,ranges)
    torque=pair(torque)
    if tuple(torque) not in CANDIDATES:raise ValueError('One of the fixed 81 constant vector candidates required')
    q=q.copy();v=v.copy();pv=pv.copy();qs=[];vs=[];history=[]
    costs=[.00002*(torque[i]-previous[i])**2 for i in range(2)]
    attempts=successes=scalar_attempts=scalar_successes=0;reason=None
    COUNTS['candidate_replays']+=1
    for h in range(1,HORIZON+1):
        attempts+=1;COUNTS['planning_pair_attempts']+=1;before=Counter(lag.MATH_COST)
        old_q,old_v,old_pv=q.copy(),v.copy(),pv.copy();step={'h':h,'q':old_q,'v':old_v,'previous_v':old_pv,'constant_requested_nm':torque.copy()}
        try:nq,nv=lag.predict11(theta,ranges,qref,q,v,torque,pv)
        except (ValueError,OverflowError):
            delta=lag.MATH_COST-before;scalar_attempts+=delta['lag_scalar_prediction_attempts'];scalar_successes+=delta['lag_scalar_prediction_successes']
            COUNTS['planning_scalar_attempts']+=delta['lag_scalar_prediction_attempts'];COUNTS['planning_scalar_successes']+=delta['lag_scalar_prediction_successes']
            reason='prediction_error:PairPredictionError';step['failure']=reason;history.append(step);break
        successes+=1;scalar_attempts+=2;scalar_successes+=2
        COUNTS['planning_pair_successes']+=1;COUNTS['planning_scalar_attempts']+=2;COUNTS['planning_scalar_successes']+=2
        step.update(predicted_q=nq,predicted_v=nv,accepted=False);history.append(step)
        if any(not bounds[i][0]<=nq[i]<=bounds[i][1] for i in range(2)):reason='forecast_position_bounds';break
        if any(abs(z)>1.5 for z in nv):reason='forecast_velocity_bound';break
        qs.append(nq.copy());vs.append(nv.copy());step['accepted']=True
        for i in range(2):costs[i]+=(nq[i]-target[i])**2+.002*nv[i]**2+.00002*torque[i]**2
        if not all(finite(z) for z in costs) or not finite(sum(costs)):reason='nonfinite_cost';break
        # Advance from this candidate's old current v, not fixed initial history
        # or a observed future endpoint. No history survives to the next candidate.
        pv,q,v=old_v,nq,nv
    feasible=reason is None and len(qs)==HORIZON
    record={'torque':torque,'feasible':feasible,'cost':sum(costs) if feasible else None,
        'rejection_reason':reason,'completed_prediction_steps':len(qs),'pair_prediction_attempts':attempts,
        'scalar_prediction_attempts':scalar_attempts,'scalar_counts_complete':True}
    accounting={'pair_prediction_attempts':attempts,'pair_prediction_successes':successes,
        'scalar_prediction_attempts':scalar_attempts,'scalar_prediction_successes':scalar_successes,
        'failed_pair_prediction_attempts':attempts-successes,'scalar_counts_complete':True,
        'scalar_counts_is_lower_bound':False,'unknown_scalar_failure_count':0}
    return {'candidate_record':record,'accounting':accounting,'predicted_q':qs,'predicted_v':vs,
        'history_diagnostics':history,'axis_costs':costs}

def choose_feasible(items):
    feasible=[]
    for item in items:
        record=item['candidate_record'];torque=record['torque']
        if record['feasible']:
            feasible.append((record['cost'],sum(abs(u) for u in torque),*torque,item['predicted_q'],item['predicted_v']))
    if not feasible:return {'torque':[0.,0.],'feasible_candidates':0,'fallback':True,'cost':None,'predicted_q':[],'predicted_v':[]}
    cost,_,u0,u1,qs,vs=min(feasible)
    return {'torque':[u0,u1],'feasible_candidates':len(feasible),'fallback':False,'cost':cost,'predicted_q':qs,'predicted_v':vs}

def replay_mpc(theta,ranges,qref,q,v,previous_v,target,previous_torque):
    """All 81 candidates in original product order; no native-state mutations."""
    validate(qref,q,v,previous_v,target,previous_torque,ranges)
    COUNTS['planner_replays']+=1
    items=[candidate_math(theta,ranges,qref,q,v,previous_v,target,previous_torque,list(torque)) for torque in CANDIDATES]
    result=choose_feasible(items);accounting=Counter()
    for item in items:
        accounting.update({key:value for key,value in item['accounting'].items() if type(value) is int})
    result.update(dict(accounting),scalar_counts_complete=True,scalar_counts_is_lower_bound=False,
        candidate_records=[item['candidate_record'] for item in items])
    return result

guard,common=lag.guard,lag.common
Checks=lag.Checks
SOURCE='src/developmental_physics/guard_lag_control_development.py'
MPC='src/developmental_physics/guard_lag_pair_mpc.py'
CORE='src/developmental_physics/guard_lag_pair_model.py'
AUDITOR='scripts/audit_guard_lag_control.py'
PROTOCOL='docs/GUARD_LAG_CONTROL_DEVELOPMENT_PROTOCOL.md'
SUPPORT=(LAG_SUPPORT,*lag.SUPPORT)
KINDS=('cold11','learned_sparse11','PDselected','zero')
MODEL_NAMES=('cold11','learned_sparse11')
PHASES=('prefix','control')
PLANNING_KEYS=guard.PLANNING_KEYS
FORMAL_AUDIT_ENABLED=False
D_ROOT='results/cpu_validation/2026-10-11_guard_lag_offline/'
D_MANIFEST_SHA='38df6b99e15c3667a33d6c9995a8efd664f70ce59be8a511fa49def59727a4d7'
D_FIRST_AUDIT_SHA='668e6ec65c949f4d7a87349e5b6076dcfeae1d53e9f770364ae4fec943b15da5'
D_RECONCILIATION_SHA='5b9fe0a4b443cab5bcc97dc4b735caef42655780ca39ed061f0560c7a87c46d0'

@dataclass(frozen=True)
class AuditSpec:
    def record(self):
        return {'suite':'guard_lag_control_development','pose':'supine','split':'development',
            'hypothesis_scope':'new development control subhypothesis after sealed D',
            'seeds':[0,1,2],'kinds':list(KINDS),'joint_indices':[0,1],
            'prefix_steps':100,'control_steps':200,'horizon':15,'vector_candidates':81,
            'model_updates':0,'diagnostic_pair_cap':4800,'planning_pair_cap':1458000,
            'physical_control_cap':3600,'physical_substep_cap':36000,
            'c4_scientifically_validated':False,'D_first_audit_failed':1,
            'absolute_tolerance':lag.ABS_TOL,'relative_tolerance':lag.REL_TOL}
PRODUCTION_SPEC=AuditSpec()

def exact(checks,actual,expected,loc):lag.exact(checks,actual,expected,loc)
def sha(blob):return hashlib.sha256(blob).hexdigest()
def parse(blob):return guard.parse_json(blob)
def load(path):return parse(Path(path).read_bytes())

def physical_base(sr,episode,rows,ranges,checks):
    """Only generic E native/effort/stop accounting; actor math is separate."""
    seed,kind=episode['seed'],episode['kind'];tid=f'seed{seed}_{kind}';ev=sr['evaluations'][kind]
    checks.compare(episode,{'trial_id':tid,'maximum_control_steps':300},tid+'/fixed_plan')
    exact(checks,set(episode['phase_budgets']),set(PHASES),tid+'/exact_phase_partition')
    regular=[r for r in rows if 'collector_exception' not in r];exceptions=[r for r in rows if 'collector_exception' in r]
    checks.check(len(exceptions)<=1 and (not exceptions or rows[-1] is exceptions[0]),'one_final_exception_record',tid)
    checks.check(episode['status'] in ('completed','terminated','exception','blocked','incomplete'),'known_outcome_status',tid)
    if episode['status']=='blocked':
        checks.check(not rows,'blocked_trial_has_no_saved_physics',tid)
        for key in ('control_calls_attempted','control_steps','physics_steps'):exact(checks,episode[key],0,tid+'/blocked/'+key)
        for phase in PHASES:exact(checks,episode['phase_budgets'][phase],{'control_calls_attempted':0,'control_steps':0,'physics_steps':0},tid+'/blocked/'+phase)
        checks.compare(ev,{'status':'blocked','completed':False},tid+'/blocked_evaluation')
        return {'eligible':False,'completed':False,'status':'blocked'},regular,exceptions
    counter={'physics':0};previous=None;study=terminal=False
    phase_rows={p:0 for p in PHASES};phase_physics={p:0 for p in PHASES}
    effort={p:guard.new_effort() for p in PHASES};risk={p:common.new_risk() for p in ('full',*PHASES)}
    tracking=[];partial=[];saturation=[0,0]
    exact(checks,[r['step_index'] for r in regular],list(range(len(regular))),tid+'/contiguous_regular_indices')
    checks.check(len(regular)<=300,'fixed_total_duration',tid)
    for row in regular:
        index=row['step_index'];where=tid+':'+str(index);phase='prefix' if index<100 else 'control'
        checks.compare(row,{'trial_id':tid,'seed':seed,'kind':kind,'joint_indices':[0,1],'phase':phase,'shared_transition_id':where},where+'/identity')
        checks.check(not study and not terminal,'no_saved_interaction_after_stop',where)
        n=guard.verify_transition(row,previous,counter,ranges,checks,where)
        phase_rows[phase]+=1;phase_physics[phase]+=n;guard.add_effort(effort[phase],row)
        for p in ('full',phase):common.record_risk(risk[p],row,ranges,joint_index=0)
        previous=row['observation_after'];terminal=row['diagnostics']['terminated']
        exact(checks,row['model_update'],None,where+'/all_control_models_frozen')
        exact(checks,row.get('model_snapshot_after'),None,where+'/no_online_snapshot_publication')
        if index<100:
            exact(checks,row['requested_torque'],[0.]*8,where+'/zero_prefix_request')
            exact(checks,row['planned_torque'],[0.]*8,where+'/zero_prefix_plan')
            for field in ('target_q','exploration_diagnostics','planner_decision'):exact(checks,row[field],None,where+'/prefix/'+field)
            exact(checks,row['predicted_next_qv'],{},where+'/no_prefix_prediction')
            exact(checks,row['model_input_diagnostics'],{},where+'/no_prefix_model_input')
            continue
        exact(checks,row['exploration_diagnostics'],None,where+'/no_control_veto')
        study=guard.verify_study(row,sr['reference_q'],checks,where)
        target=[sr['reference_q'][i]+sr['direction'][i]*(.04 if index<200 else .08) for i in range(2)]
        exact(checks,row['target_q'],target,where+'/current_target_only')
        exact(checks,row['planned_torque'],row['requested_torque'],where+'/no_extra_feedback_or_veto')
        checks.check(row['requested_torque'][2:]==[0.]*6,'only_two_selected_axes_requested',where)
        if n==10:
            tracking.append([row['observation_after']['joint_position'][i]-target[i] for i in range(2)])
            for i in range(2):saturation[i]+=abs(row['requested_torque'][i])==.5
        else:partial.append({'step_index':index,'target_q':target,'errors_rad':[row['observation_after']['joint_position'][i]-target[i] for i in range(2)],'executed_substeps':n})
    recovered=0
    for ex in exceptions:
        returned=ex.get('returned_step_diagnostics');phase=ex.get('phase');index=ex.get('step_index')
        unique=not any(row['step_index']==index for row in regular)
        # The first exception remains original. Only a uniquely returned, paid
        # native endpoint with actual telemetry already counted by the collector
        # can reconstruct the unwritten physical row; never an unreturned state.
        if unique and isinstance(returned,dict) and phase in PHASES and ex.get('observation_after_retrieval_error') is None:
            n=returned.get('executed_substeps')
            measured=ev['phase_actual_effort_substeps'][phase]
            if type(n) is int and measured==phase_physics[phase]+n and n>0 and all(ex.get(k) is not None for k in ('observation_before','observation_after','qpos','qvel','requested_torque')):
                view={**ex,'diagnostics':returned}
                actual=guard.verify_transition(view,previous,counter,ranges,checks,tid+'/returned_unwritten_native')
                phase_physics[phase]+=actual;guard.add_effort(effort[phase],view)
                for p in ('full',phase):common.record_risk(risk[p],view,ranges,joint_index=0)
                recovered+=1
                if phase=='control' and view['target_q'] is not None:
                    errors=[view['observation_after']['joint_position'][i]-view['target_q'][i] for i in range(2)]
                    if actual==10 and ev['metric_control_step_count']==len(tracking)+1:
                        tracking.append(errors)
                        for i in range(2):saturation[i]+=abs(view['requested_torque'][i])==.5
                    elif actual!=10 and len(ev['partial_interval_target_errors_rad'])==len(partial)+1:
                        partial.append({'step_index':index,'target_q':view['target_q'],'errors_rad':errors,'executed_substeps':actual})
    for phase in PHASES:
        cap=100 if phase=='prefix' else 200;budget=episode['phase_budgets'][phase]
        checks.check(all(type(budget[k]) is int and 0<=budget[k]<=cap for k in ('control_calls_attempted','control_steps')) and
            type(budget['physics_steps']) is int and 0<=budget['physics_steps']<=10*cap,'paid_phase_caps',tid+'/'+phase)
        checks.check(budget['control_calls_attempted']>=budget['control_steps']>=phase_rows[phase] and
            phase_physics[phase]<=budget['physics_steps']<=10*budget['control_calls_attempted'],'paid_budget_keeps_missing_rows',tid+'/'+phase)
    for key in ('control_calls_attempted','control_steps','physics_steps'):exact(checks,episode[key],sum(x[key] for x in episode['phase_budgets'].values()),tid+'/paid_sum/'+key)
    missing=episode['physics_steps']-counter['physics']
    checks.check(0<=missing<=10 and 0<=episode['control_steps']-len(regular)<=1,'one_failed_physical_interval_bound',tid)
    checks.check(type(episode['returned_steps']) is int and type(episode['written_returned_steps']) is int and
        0<=episode['written_returned_steps']<=episode['returned_steps']<=episode['control_steps'] and
        len(regular)<=episode['returned_steps']<=len(regular)+1,'saved_returned_paid_partition',tid)
    exact(checks,episode['returned_unwritten_steps'],episode['returned_steps']-episode['written_returned_steps'],tid+'/paid_unwritten_returns')
    checks.check(type(episode['unreturned_physics_steps']) is int and 0<=episode['unreturned_physics_steps']<=missing,'unreturned_substeps_not_zeroed',tid)
    for ex in exceptions:
        checks.compare(ex,{'trial_id':tid,'seed':seed,'kind':kind},tid+'/exception_identity')
        guard.verify_exception_native_mapping(ex,checks,tid+'/exception')
        guard.verify_exception_paid_counters(ex,episode,checks,tid+'/exception')
    full=(episode['status']=='completed' and len(regular)==300 and not exceptions and not study and not terminal and
        episode['control_calls_attempted']==episode['control_steps']==300 and episode['physics_steps']==3000 and
        all(r['diagnostics']['executed_substeps']==10 for r in regular))
    checks.check(episode['status']!='completed' or full,'completion_requires_all_nonterminal_paid_intervals',tid)
    exact(checks,episode['completed'],full,tid+'/episode_complete');exact(checks,ev['completed'],full,tid+'/evaluation_complete')
    for field in ('status','study_abort','environment_terminated','environment_stop_reason','collector_exception'):exact(checks,ev[field],episode[field],tid+'/outcome/'+field)
    exact(checks,episode['reason'],episode['environment_stop_reason'] if episode['environment_terminated'] else episode['study_abort'] if episode['study_abort'] is not None else episode['collector_exception'],tid+'/reason_precedence')
    if not exceptions:
        exact(checks,episode['returned_steps'],len(regular),tid+'/returned_count');exact(checks,episode['written_returned_steps'],len(regular),tid+'/written_count')
        exact(checks,episode['study_abort'],regular[-1].get('study_abort') if regular else None,tid+'/saved_final_study')
        exact(checks,episode['environment_terminated'],terminal,tid+'/saved_environment_stop')
    if episode.get('environment_fingerprint_before') is not None:
        exact(checks,episode['environment_fingerprint_after'],episode['environment_fingerprint_before'],tid+'/fixed_environment')
        exact(checks,episode['environment_fingerprint_before'],ENVIRONMENT_FINGERPRINT,tid+'/original_public_environment')
        if 'environment_fingerprint_before' in sr:exact(checks,episode['environment_fingerprint_before'],sr['environment_fingerprint_before'],tid+'/shared_environment')
    metric=guard.paired_rmse(tracking);checks.compare(ev['tracking_rmse'],metric,tid+'/native_tracking_error')
    exact(checks,ev['metric_control_step_count'],len(tracking),tid+'/complete_metric_endpoints')
    checks.compare(ev['partial_interval_target_errors_rad'],partial,tid+'/partial_metrics_separate')
    exact(checks,ev['saturated_control_steps_per_axis'],saturation,tid+'/saturation')
    efforts={p:guard.reconcile_effort(ev,p,effort[p],episode['phase_budgets'][p]['physics_steps'],phase_physics[p],exceptions,checks,tid+'/effort/'+p) for p in PHASES}
    exact(checks,ev['control_effort'],ev['phase_effort']['control'],tid+'/control_effort_alias')
    paid=episode['phase_budgets']['control']['physics_steps'];actual=ev['phase_actual_effort_substeps']['control']
    exact(checks,ev['actual_effort_complete'],actual==paid,tid+'/effort_complete');exact(checks,ev['actual_effort_is_lower_bound'],actual<paid,tid+'/effort_lower_bound')
    exact(checks,ev['actual_control_effort_substeps'],actual,tid+'/measured_effort_steps');exact(checks,ev['missing_control_effort_substeps'],paid-actual,tid+'/missing_effort_steps')
    checks.check(not episode.get('risk_telemetry_complete',False) or missing==0 and not exceptions,'risk_not_complete_after_missing_telemetry',tid)
    for phase in risk:
        absent=missing if phase=='full' else episode['phase_budgets'][phase]['physics_steps']-phase_physics[phase]
        risk[phase].update(telemetry_missing_paid_substeps=absent,reconstruction_complete=absent==0,request_applied_mismatch_count_is_lower_bound=absent>0)
    return {'eligible':full,'completed':full,'status':episode['status'],'tracking_rmse_rad':None if metric is None else metric['joint'],
        'tracking_rmse_by_axis_rad':None if metric is None else metric['per_axis'],'control_effort':ev['control_effort'],
        'actual_effort_complete':ev['actual_effort_complete'],'risk':risk,'effort_audit':efforts,
        'complete_score_endpoints':len(tracking),'partial_score_endpoints':len(partial),'unreconstructed_physics_substeps':missing,
        'reconstructed_returned_unwritten_endpoints':recovered,
        'paid_budget':{k:episode[k] for k in ('control_calls_attempted','control_steps','physics_steps')}},regular,exceptions

def complete(ev):return isinstance(ev,dict) and ev.get('eligible') is True and ev.get('completed') is True and ev.get('status')=='completed'
def nonnegative_pair(value):return isinstance(value,list) and len(value)==2 and all(finite(z) and z>=0. for z in value)
def fixed_complete(seeds,kinds):
    return len(seeds)==3 and {r['seed'] for r in seeds}=={0,1,2} and all(complete(sr.get('evaluations',{}).get(kind)) for sr in seeds for kind in kinds)

def development_comparison(seeds,baseline,*,threshold,strict,dependency=True):
    candidate='learned_sparse11';rows=[]
    evaluated=dependency and fixed_complete(seeds,(baseline,candidate))
    for sr in seeds:
        ev=sr.get('evaluations',{});old,new=ev.get(baseline,{}),ev.get(candidate,{})
        a,z=old.get('tracking_rmse_rad'),new.get('tracking_rmse_rad');ax,zx=old.get('tracking_rmse_by_axis_rad'),new.get('tracking_rmse_by_axis_rad')
        valid=(complete(old) and complete(new) and old.get('actual_effort_complete') is True and new.get('actual_effort_complete') is True and
            finite(a) and finite(z) and a>=0. and z>=0. and nonnegative_pair(ax) and nonnegative_pair(zx))
        efforts={}
        for key in ('actual_absolute_nm_s','actual_squared_nm2_s'):
            aa=old.get('control_effort',{}).get(key);zz=new.get('control_effort',{}).get(key)
            available=nonnegative_pair(aa) and nonnegative_pair(zz)
            valid=valid and available
            efforts[key]={'baseline_joint':sum(aa) if available else None,'candidate_joint':sum(zz) if available else None}
        rows.append({'seed':sr['seed'],'eligible':bool(valid),'baseline_tracking':a,'candidate_tracking':z,
            'baseline_axis_tracking':ax,'candidate_axis_tracking':zx,'efforts':efforts,
            'joint_order_passed':bool(valid and (z<a if strict else z<=a)),
            'axis_order_passed':[bool(valid and (zx[i]<ax[i] if strict else zx[i]<=ax[i])) for i in range(2)]})
    evaluated=bool(evaluated and all(r['eligible'] for r in rows))
    joint_a=sum(r['baseline_tracking'] for r in rows)/3 if evaluated else None
    joint_z=sum(r['candidate_tracking'] for r in rows)/3 if evaluated else None
    joint_change=guard.improvement(joint_z,joint_a) if evaluated else None
    axes=[]
    for axis in range(2):
        aa=sum(r['baseline_axis_tracking'][axis] for r in rows)/3 if evaluated else None
        zz=sum(r['candidate_axis_tracking'][axis] for r in rows)/3 if evaluated else None
        change=guard.improvement(zz,aa) if evaluated else None
        axes.append({'axis':axis,'baseline_raw_mean':aa,'candidate_raw_mean':zz,'mean_improvement':change,
            'threshold_applies':strict,'threshold_passed':bool(evaluated and change is not None and change>=threshold) if strict else None})
    efforts={}
    for key in ('actual_absolute_nm_s','actual_squared_nm2_s'):
        aa=sum(r['efforts'][key]['baseline_joint'] for r in rows)/3 if evaluated else None
        zz=sum(r['efforts'][key]['candidate_joint'] for r in rows)/3 if evaluated else None
        efforts[key]={'baseline_raw_mean_joint':aa,'candidate_raw_mean_joint':zz,'ratio_max':1.05,
            'passed':bool(evaluated and zz<=1.05*aa)}
    order=all(r['joint_order_passed'] and all(r['axis_order_passed']) for r in rows)
    threshold_pass=bool(evaluated and joint_change is not None and joint_change>=threshold and (not strict or all(a['threshold_passed'] for a in axes)))
    passed=bool(evaluated and order and threshold_pass and all(e['passed'] for e in efforts.values()))
    changes=[guard.improvement(r['candidate_tracking'],r['baseline_tracking']) for r in rows] if evaluated else []
    return {'evaluated':evaluated,'passed':passed,'baseline':baseline,'candidate':candidate,'prerequisite_passed':dependency,
        'rows':rows,'baseline_raw_mean_joint_rmse':joint_a,'candidate_raw_mean_joint_rmse':joint_z,
        'joint_mean_improvement':joint_change,'joint_improvement_min':threshold,'axes':axes,'efforts':efforts,
        'worst_seed_joint_improvement':min(changes) if changes and all(z is not None for z in changes) else None,
        'complete_control_only':True,'aggregation':'arithmetic means of per-seed raw joint/axis metrics; never pooled endpoints',
        'scientific_validation':False}

def development_gates(seeds):
    hypothesis=development_comparison(seeds,'cold11',threshold=.20,strict=True)
    pd=development_comparison(seeds,'PDselected',threshold=.05,strict=False,dependency=hypothesis['passed'])
    return {'control_hypothesis':hypothesis,'pd_reference':pd,'matrix_complete':fixed_complete(seeds,KINDS),
        'c4_scientific_validation':{'evaluated':False,'passed':False,
            'reason':'D selected sparse11 failed the unchanged independent 20-percent prediction condition; E is a development control subhypothesis'},
        }

def planner_spec(qref,ranges):
    return {**guard.planner_spec(qref,ranges),'history':{
        'argument':'previous_v','stored_in_model_or_controller':False,
        'native_initialization':'immediately preceding native endpoint, 20 ms apart',
        'unknown_or_reset_history':'must not call select; never substitute zero',
        'candidate_initialization':'each candidate independently starts from supplied previous_v',
        'rollout_advance':'predict first, then previous_v becomes old current v'}}

def native_history(regular,index,row=None):
    """Return only previously paid, native, uninterrupted velocity endpoints."""
    if type(index) is not int or index<100 or index>len(regular) or index==len(regular) and row is None:
        raise ValueError('Active source row with its paid prefix required')
    row=regular[index] if row is None else row;older,previous=regular[index-2],regular[index-1]
    if older['step_index']!=index-2 or previous['step_index']!=index-1 or row['step_index']!=index:
        raise ValueError('Contiguous original step indices required')
    if not lag.continuous(older,previous) or previous.get('study_abort') is not None or previous['diagnostics']['terminated'] or lag.native(previous['observation_after'])!=lag.native(row['observation_before']):
        raise ValueError('Native history cannot cross missing/partial/terminal endpoints')
    if index==100 and (older['phase']!='prefix' or previous['phase']!='prefix'):
        raise ValueError('First active history must be prefix98/99 endpoints')
    q,v=lag.native(row['observation_before']);previous_v=lag.native(older['observation_after'])[1]
    COUNTS['native_history_origins_verified']+=1
    return {'q':q,'v':v,'previous_v':previous_v,
        'history_transition_ids':[older['shared_transition_id'],previous['shared_transition_id']]}

D_COMMIT='f7710c7b048dccab3e436d1fa16432f881a35992'
C_COMMIT='5ea8df42b09588845760daf0dc1f270aef2a87f1'
ENVIRONMENT_FINGERPRINT='102adc9d013aec72db9355eecfd21031a7868ad5129817c6157ae65542ac225e'
RESET={0:3757552657,1:1641411168,2:2001025171}
D_HASHES={
    'manifest.json':D_MANIFEST_SHA,'first_audit.json':D_FIRST_AUDIT_SHA,
    'read_accounting_reconciliation/first_reconciliation.json':D_RECONCILIATION_SHA,
    'summary_once/summary.json':'dbcfcb53194f2bfa6a634cecb5c5df72a69f9892a42d828fbdf44d08b2930016',
    'raw/diagnostics.json':'9307f3f37d5a3c23ef6f9097d8c352a9fc7f2e34e562b5cf4e7075e20bbbe130',
    'raw/manifest.json':'f5d6e0fc017d708a8c8b2b03a6876704248afee92266985ebd5d137267acb3c6'}
FILES=('metadata.json','episodes.json','seed_results.json','trace.jsonl.gz','source_snapshot.zip','manifest.json')
READ_COST=Counter()

def planned_matrix():
    return [{'trial_id':f'seed{seed}_{kind}','seed':seed,'kind':kind,'maximum_control_steps':300} for seed in RESET for kind in KINDS]

def required_sources():
    return {SOURCE,MPC,CORE,AUDITOR,PROTOCOL,'pyproject.toml',common.ASSET,*SUPPORT,
        *guard.PD_SOURCE_FILES,guard.PD_PROTOCOL,*{D_ROOT+n for n in D_HASHES}}

def source_name_allowed(name):
    return (name in required_sources() or
        name.startswith('src/developmental_physics/') and name.endswith('.py') and name.count('/')==2)

def read_inputs(path,checks):
    exact(checks,{p.name for p in path.iterdir() if p.is_file()},set(FILES),'exact_six_output_file_coverage')
    files={}
    for name in FILES:
        files[name]=(path/name).read_bytes();READ_COST['physical_archive_file_reads']+=1
        READ_COST['physical_archive_raw_bytes']+=len(files[name])
    manifest=parse(files['manifest.json']);metadata=parse(files['metadata.json'])
    exact(checks,manifest['schema_version'],1,'manifest_schema')
    exact(checks,manifest['status'],metadata['status'],'manifest_outcome_status')
    exact(checks,set(manifest['files']),set(FILES)-{'manifest.json'},'manifest_exact_member_coverage')
    for name,blob in files.items():
        if name!='manifest.json':exact(checks,manifest['files'][name],{'sha256':sha(blob),'bytes':len(blob)},'manifest/'+name)
    return files,metadata

def verify_sources(files,metadata,checks,git_root,auditor_bytes,support_bytes):
    members=lag.b.source_members(files['source_snapshot.zip']);hashes=metadata['source_sha256'];commit=metadata['source_commit']
    valid=type(commit) is str and re.fullmatch('[0-9a-f]{40}',commit) is not None
    checks.check(valid,'clean_full_source_commit')
    exact(checks,metadata['source_dirty'],False,'clean_source_dirty');exact(checks,metadata['source_status'],'','clean_source_status')
    checks.check(required_sources().issubset(hashes),'complete_E_D_PD_support_source_coverage')
    checks.check(all(source_name_allowed(name) for name in hashes),'no_undeclared_source_dependency')
    exact(checks,set(members),set(hashes),'unique_exact_source_zip_coverage')
    exact(checks,metadata['source_snapshot_sha256'],sha(files['source_snapshot.zip']),'source_zip_byte_identity')
    for name,expected in hashes.items():
        guard._path(name);guard._hash(expected);exact(checks,sha(members[name]),expected,'frozen_source/'+name)
        if git_root is not None and valid:
            response=subprocess.run(['git','show',f'{commit}:{name}'],cwd=git_root,capture_output=True,check=False)
            READ_COST['frozen_git_blob_queries']+=1;READ_COST['frozen_git_blob_return_bytes']+=len(response.stdout)
            checks.check(response.returncode==0 and response.stdout==members[name],'frozen_git_blob_original_bytes',name)
    if git_root is not None and valid:
        tree=subprocess.run(['git','ls-tree','-r','--name-only',commit,'src/developmental_physics'],cwd=git_root,capture_output=True,text=True,check=False)
        READ_COST['frozen_git_tree_queries']+=1
        sources={n for n in tree.stdout.splitlines() if n.endswith('.py') and n.count('/')==2}
        checks.check(tree.returncode==0 and sources.issubset(hashes),'all_current_physics_sources_archived')
    exact(checks,metadata['protocol'],{'path':PROTOCOL,'sha256':hashes[PROTOCOL]},'frozen_protocol_identity')
    exact(checks,metadata['independent_auditor'],{'path':AUDITOR,'sha256':sha(auditor_bytes),'required_for_formal':True},'executing_E_auditor_identity')
    exact(checks,members[AUDITOR],auditor_bytes,'executing_E_auditor_original_bytes')
    for name in SUPPORT:exact(checks,members[name],support_bytes[name],'executing_support_original_bytes/'+name)
    pd_sources={n:members[n] for n in (*guard.PD_SOURCE_FILES,guard.PD_PROTOCOL)}
    pd=guard.reconstruct_pd_binding(pd_sources)
    exact(checks,metadata['pd_binding'],pd,'independent_original_PD_binding')
    exact(checks,metadata['pd_gains'],{'kp':[64.,64.],'kd':[0.,4.]},'frozen_selected_PD_gains')
    exact(checks,metadata['pd_gains'],{'kp':pd['kp'],'kd':pd['kd']},'archived_PD_gains')
    return members,lag.b.public_ranges(members[common.ASSET]),pd

def state_from_snapshot(snapshot,ranges,count,checks,loc):
    if not isinstance(snapshot,dict):raise ValueError('Complete immutable lag snapshot required')
    theta,covariance=snapshot['coefficients'],snapshot['covariance']
    if len(theta)!=2 or any(len(row)!=11 or not all(finite(z) for z in row) for row in theta):
        raise ValueError('Two finite eleven-column snapshot heads required')
    if len(covariance)!=2 or any(len(matrix)!=11 or any(len(row)!=11 or not all(finite(z) for z in row) for row in matrix) for matrix in covariance):
        raise ValueError('Two finite eleven-square covariance matrices required')
    state={'theta':theta,'covariance':covariance,'count':count,'ranges':ranges,
        'observed_theta':theta,'observed_covariance':covariance}
    lag.verify_snapshot(snapshot,state,snapshot['qref_rad'],checks,loc,False)
    COUNTS['immutable_snapshot_structure_verifications']+=1
    return state

def bind_d_states(members,metadata,ranges,checks):
    """Saved snapshot identity only. Never invoke fit, D audit or D rollouts."""
    docs,records={},{}
    for relative,expected in D_HASHES.items():
        blob=members[D_ROOT+relative]
        exact(checks,sha(blob),expected,'sealed_D_pin/'+relative)
        docs[relative]=parse(blob);records[relative]={'sha256':sha(blob),'bytes':len(blob)}
        READ_COST['D_selected_zip_payloads_parsed']+=1;READ_COST['D_selected_zip_payload_bytes']+=len(blob)
    manifest=docs['manifest.json']
    for relative in D_HASHES:
        if relative!='manifest.json':exact(checks,{k:manifest['files'][relative][k] for k in ('sha256','bytes')},records[relative],'D_outer_manifest/'+relative)
    first=docs['first_audit.json'];reconciliation=docs['read_accounting_reconciliation/first_reconciliation.json'];summary=docs['summary_once/summary.json']
    exact(checks,first['failed'],1,'D_original_first_failed_count_preserved')
    exact(checks,first['violations'],[{'check':'exact_source_or_causal_identity','location':'runner_original_read_accounting'}],'D_original_unique_violation_preserved')
    exact(checks,reconciliation['checks'],50,'D_byte_reconciliation_checks');exact(checks,reconciliation['failed'],0,'D_byte_reconciliation_failed')
    exact(checks,reconciliation['first_audit_sha256'],D_FIRST_AUDIT_SHA,'D_reconciliation_original_first_binding')
    for key in ('byte_only_reconciliation_verified','effective_data_consistency_verified'):
        exact(checks,reconciliation[key],True,'D_reconciliation/'+key)
    exact(checks,summary['source_commit'],D_COMMIT,'D_saved_summary_source_commit')
    exact(checks,summary['binding_checks'],{'checks':51,'failed':0},'D_saved_summary_binding_checks')
    exact(checks,summary['effective_data_consistency_verified'],True,'D_saved_summary_data_status')
    raw_manifest=docs['raw/manifest.json'];exact(checks,raw_manifest['status'],'completed','D_original_raw_completed')
    exact(checks,{k:raw_manifest['files']['diagnostics.json'][k] for k in ('sha256','bytes')},records['raw/diagnostics.json'],'D_original_diagnostics_byte_binding')
    expected_binding={'root':D_ROOT.rstrip('/'),'collection_commit':D_COMMIT,'original_C_commit':C_COMMIT,
        'records':records,'first_audit_failed':1,'reconciliation_checks':50,'effective_data_consistency_verified':True,
        'refits':0,'predictions':0,'offline_updates':0,'restored_models':3,'cold_model_initializations':3,
        'restore_initialization_compute':'nonzero object construction, array copying, complete snapshot and fingerprint checks; no predict/update calls',
        'selected_snapshot_path':'raw/diagnostics.json:[seed,sparse].lag11_final_snapshot',
        'payload_bytes_read':sum(v['bytes'] for v in records.values())}
    exact(checks,metadata['D_binding'],expected_binding,'exact_D_restoration_identity_and_no_replay')
    result={}
    for seed in RESET:
        selected=[r for r in docs['raw/diagnostics.json'] if r['seed']==seed and r['calibration']=='sparse']
        original=[r for r in summary['calibrations'] if r['seed']==seed and r.get('kind',r.get('calibration'))=='sparse']
        if len(selected)!=1 or len(original)!=1:raise ValueError('One saved original sparse D model per seed required')
        exact(checks,original[0]['completed'],True,f'D_seed{seed}/complete_calibration')
        original_snapshot=selected[0]['lag11_final_snapshot']
        exact(checks,original_snapshot['trainable'],True,f'D_seed{seed}/original_trainable_state')
        learned={**original_snapshot,'trainable':False};qref=pair(learned['qref_rad'])
        exact(checks,learned['input_mapping']['public_guard']['public_joint_ranges_rad'],ranges[:2],f'D_seed{seed}/public_morphology')
        learned_state=state_from_snapshot(learned,ranges[:2],400,checks,f'D_seed{seed}/frozen_complete_state')
        cold=lag.initial_state(ranges[:2]);parameter=lag.parameter_record(qref,cold)
        cold_snapshot={**parameter,'parameter_fingerprint':lag.digest(parameter),'trainable':False,
            'vector_update_count':0,'scalar_update_count':0,'output_update_counts':[0,0],
            'update_commit':'single immutable state reference for both outputs, covariance and counts',
            'input_boundary':'native current/previous velocities, current q and already known u; no future actual torque'}
        result[seed]={'qref':qref,'ranges':ranges[:2],
            'snapshots':{'cold11':cold_snapshot,'learned_sparse11':learned},
            'states':{'cold11':cold,'learned_sparse11':learned_state}}
    return result,expected_binding

def history_record(origin):
    return {'current_v_rad_s':origin['v'],'previous_v_rad_s':origin['previous_v'],
        'history_transition_ids':origin['history_transition_ids'],'native_contiguous':True}

def verify_reference(sr,episode,regular,models,ranges,checks):
    tid=episode['trial_id'];binding=sr.get('fresh_prefix_bindings',{}).get(episode['kind'])
    if binding is None:
        checks.check(len(regular)<=100,'no_active_physics_without_exact_prefix_binding',tid)
        return
    if len(regular)<100:raise ValueError('Published fresh binding requires 100 saved paid prefix rows')
    older,previous=regular[98],regular[99]
    if not lag.continuous(older,previous) or previous['diagnostics']['terminated'] or previous.get('study_abort') is not None:
        raise ValueError('Binding requires uninterrupted nonterminal complete prefix98/99')
    q,v=lag.native(previous['observation_after']);pv=lag.native(older['observation_after'])[1]
    directions=[];selection=[]
    for i in range(2):
        lower,upper=ranges[i];positive,negative=upper-q[i],q[i]-lower;direction=1 if positive>=negative else -1
        directions.append(direction);selection.append({'joint_index':i,'joint_position_rad':q[i],
            'lower_limit_rad':lower,'upper_limit_rad':upper,'positive_room_rad':positive,'negative_room_rad':negative,
            'direction':direction,'rule':'larger distance to the public joint limit; ties choose positive'})
    history={'current_v_rad_s':v,'previous_v_rad_s':pv,
        'history_transition_ids':[older['shared_transition_id'],previous['shared_transition_id']],'native_contiguous':True}
    expected={'reference_q':q,'native_velocity':v,'direction':directions,'selection_records':selection,
        'public_joint_ranges':ranges[:2],'environment_fingerprint':ENVIRONMENT_FINGERPRINT,'source_native_pair_exact':True,
        'initial_history':history,'prefix98_endpoint':older['observation_after'],'prefix99_endpoint':previous['observation_after']}
    exact(checks,binding,expected,tid+'/fresh_native_prefix_exact')
    exact(checks,sr['reference_q'],q,tid+'/native_qref');exact(checks,q,models['qref'],tid+'/original_D_qref_never_reset')
    exact(checks,sr['native_prefix_velocity'],v,tid+'/native_prefix_velocity')
    exact(checks,sr['direction'],directions,tid+'/public_native_direction');exact(checks,sr['selection_records'],selection,tid+'/public_selection')
    exact(checks,sr['public_joint_ranges'],ranges[:2],tid+'/original_public_ranges')
    exact(checks,sr['environment_fingerprint_before'],ENVIRONMENT_FINGERPRINT,tid+'/original_C_D_environment')
    if len(regular)>100:exact(checks,regular[100]['observation_before'],previous['observation_after'],tid+'/prefix_control_boundary')
    COUNTS['fresh_prefix_bindings_verified']+=1

def add_meter(target,source):
    for key in PLANNING_KEYS:target[key]+=source[key]

def prediction_math(state,qref,ranges,q,v,pv,u,saved,checks,loc):
    before=Counter(lag.MATH_COST)
    expected=lag.predict11(state['theta'],ranges,qref,q,v,u,pv)
    checks.compare(saved,[*expected],loc+'/independent_before_return_prediction')
    delta=lag.MATH_COST-before
    COUNTS['diagnostic_pair_attempts']+=delta['lag_pair_prediction_attempts']
    COUNTS['diagnostic_pair_successes']+=delta['lag_pair_prediction_successes']
    COUNTS['diagnostic_scalar_attempts']+=delta['lag_scalar_prediction_attempts']
    COUNTS['diagnostic_scalar_successes']+=delta['lag_scalar_prediction_successes']
    return expected

def input_record(q,v,pv,u,ranges,ids):
    return {**guard.describe_input(q,u,('known_angle_guard',ranges)),
        'native_v_rad_s':v,'previous_v_rad_s':pv,'history_transition_ids':ids}

def successful_one_meter():return lag.b.successful_meter(1)

def verify_active_inputs(row,origin,sr,model_data,checks,loc,*,required_complete):
    q,v,pv=origin['q'],origin['v'],origin['previous_v'];ids=origin['history_transition_ids']
    exact(checks,row['history'],history_record(origin),loc+'/only_contiguous_past_native_history')
    u=pair(row['requested_torque'][:2]);predictions=row['predicted_next_qv'];inputs=row['model_input_diagnostics']
    checks.check(list(predictions)==list(MODEL_NAMES)[:len(predictions)],'diagnostic_fixed_head_order',loc)
    checks.check(list(inputs)==list(MODEL_NAMES)[:len(inputs)],'projection_fixed_head_order',loc)
    if required_complete:
        exact(checks,set(predictions),set(MODEL_NAMES),loc+'/both_same_permission_diagnostics')
        exact(checks,set(inputs),set(MODEL_NAMES),loc+'/both_before_return_inputs')
    for name in inputs:
        exact(checks,inputs[name],input_record(q,v,pv,u,model_data['ranges'],ids),loc+'/causal_projection/'+name)
    computed={}
    for name,saved in predictions.items():
        checks.check(name in inputs,'prediction_requires_saved_known_command_projection',loc+'/'+name)
        computed[name]=prediction_math(model_data['states'][name],model_data['qref'],model_data['ranges'],q,v,pv,u,saved,checks,loc+'/'+name)
    return computed

def failed_diagnostic_meter(base,exception,checks,loc):
    failure=exception.get('failure_accounting',{})
    return lag.b.failed_meter(base,failure,checks,loc)

def validate_failed_planning(record,checks,loc):
    if not isinstance(record,dict):raise ValueError('Explicit known failed-planner ledger required')
    guard.validate_meter(record,checks,loc,81*15)
    checks.check(record['failed_pair_prediction_attempts']>=1,'failed_planner_keeps_failed_pair_cost',loc)
    COUNTS['failed_planner_saved_accounting_verifications']+=1
    return {k:record[k] for k in PLANNING_KEYS}

def metric_maps(errors):
    return {n:guard.paired_rmse(values) for n,values in errors.items() if values}

def actor_and_diagnostics(sr,episode,regular,exceptions,models,checks):
    """Replay E only. D states are immutable inputs, never fitted here."""
    kind,tid=episode['kind'],episode['trial_id'];ev=sr['evaluations'][kind]
    if episode['status']=='blocked':return {'diagnostic_pair_attempts':0,'planning_pair_attempts':0,'model_updates':0}
    fingerprints={n:s['parameter_fingerprint'] for n,s in models['snapshots'].items()}
    exact(checks,ev['model_updates'],0,tid+'/no_new_model_update')
    exact(checks,ev['frozen_model_snapshots'],models['snapshots'],tid+'/full_frozen_model_state_after')
    for key in ('models_before','models_after'):exact(checks,ev[key],fingerprints,tid+'/'+key)
    for key in ('model_fingerprint_before','model_fingerprint_after'):exact(checks,ev[key],fingerprints.get(kind),tid+'/'+key)
    diag=guard.empty_meter();per_model={n:guard.empty_meter() for n in MODEL_NAMES};planning=guard.empty_meter()
    qerrors={};verrors={};partials=[];previous=[0.,0.]
    plan_attempts=plan_decisions=failed_plans=unknown_plans=fallbacks=projections=0
    def decision_at(row,origin,loc):
        nonlocal plan_attempts,plan_decisions,fallbacks
        q,v,pv=origin['q'],origin['v'],origin['previous_v'];target=row['target_q']
        exact(checks,row['planner_input'],{'q':q,'v':v,'previous_v':pv,'target_q':target,'previous_torque':previous},loc+'/explicit_planner_inputs_no_privilege')
        expected=replay_mpc(models['states'][kind]['theta'],models['ranges'],models['qref'],q,v,pv,target,previous)
        checks.compare(row['planner_decision'],expected,loc+'/all_81_original_candidate_records')
        exact(checks,row['requested_torque'][:2],row['planner_decision']['torque'],loc+'/selected_request_applied_without_veto')
        add_meter(planning,expected);plan_attempts+=1;plan_decisions+=1;fallbacks+=int(expected['fallback'])
        return expected
    def scores_at(row,predictions,loc,*,exception=False):
        after=row['observation_after'];n=(row['returned_step_diagnostics'] if exception else row['diagnostics'])['executed_substeps']
        if after is None:return
        nq,nv=lag.native(after)
        for name,(pq,pv) in predictions.items():
            if n==10:
                qerrors.setdefault(name,[]).append([nq[i]-pq[i] for i in range(2)])
                verrors.setdefault(name,[]).append([nv[i]-pv[i] for i in range(2)])
            else:partials.append({'step_index':row['step_index'],'model':name,'executed_substeps':n,
                'position_error_rad':[nq[i]-pq[i] for i in range(2)],'velocity_error_rad_s':[nv[i]-pv[i] for i in range(2)]})
    for row in regular:
        loc=tid+':'+str(row['step_index']);index=row['step_index']
        exact(checks,row['model_fingerprints'],fingerprints,loc+'/immutable_model_fingerprints')
        if index<100:
            for field in ('history','planner_input','raw_pd_torque_nm','study_abort'):exact(checks,row[field],None,loc+'/prefix/'+field)
            exact(checks,row['diagnostic_prediction_accounting'],guard.meter_record(diag),loc+'/prefix_zero_diagnostic_cost')
            continue
        origin=native_history(regular,index)
        if kind in MODEL_NAMES:
            decision_at(row,origin,loc);exact(checks,row['raw_pd_torque_nm'],None,loc+'/no_PD_residual')
        else:
            exact(checks,row['planner_input'],None,loc+'/no_planner_input');exact(checks,row['planner_decision'],None,loc+'/no_planner_call')
            if kind=='PDselected':
                raw=[64.*(row['target_q'][i]-origin['q'][i])-[0.,4.][i]*origin['v'][i] for i in range(2)]
                checks.compare(row['raw_pd_torque_nm'],raw,loc+'/selected_PD_native_feedback')
                command=[max(-.5,min(.5,z)) for z in raw]
                exact(checks,row['requested_torque'][:2],command,loc+'/original_PD_permission')
                COUNTS['PD_native_arithmetic_recomputations']+=2
            else:
                exact(checks,row['requested_torque'],[0.]*8,loc+'/zero_group');exact(checks,row['raw_pd_torque_nm'],None,loc+'/zero_no_PD')
        predictions=verify_active_inputs(row,origin,sr,models,checks,loc,required_complete=True)
        projections+=len(row['model_input_diagnostics'])
        for name in predictions:
            add_meter(diag,successful_one_meter());add_meter(per_model[name],successful_one_meter())
        exact(checks,row['diagnostic_prediction_accounting'],guard.meter_record(diag),loc+'/cumulative_diagnostic_cost')
        scores_at(row,predictions,loc);previous=row['requested_torque'][:2]
    for ex in exceptions:
        loc=tid+'/exception';index=ex.get('step_index');duplicate=any(row['step_index']==index for row in regular)
        exact(checks,ex['frozen_model_snapshots'],models['snapshots'],loc+'/complete_frozen_exception_states')
        exact(checks,ex.get('model_update'),None,loc+'/exception_no_model_update')
        exact(checks,ex['exploration_diagnostics'],None,loc+'/exception_no_veto')
        if duplicate:
            exact(checks,ex['diagnostic_prediction_accounting'],guard.meter_record(diag),loc+'/no_double_charge_duplicate_exception')
            continue
        active=type(index) is int and index>=100
        if active and ex.get('history') is not None:
            origin=native_history(regular,index,row=ex)
            exact(checks,ex['history'],history_record(origin),loc+'/causal_exception_history')
            if kind in MODEL_NAMES and ex.get('planner_decision') is not None:
                decision_at(ex,origin,loc)
            elif kind in MODEL_NAMES and ex.get('planner_input') is not None:
                exact(checks,ex['planner_input'],{'q':origin['q'],'v':origin['v'],'previous_v':origin['previous_v'],
                    'target_q':ex['target_q'],'previous_torque':previous},loc+'/failed_planner_causal_inputs')
                plan_attempts+=1;failed_plans+=1;record=ex.get('failure_accounting',{}).get('pair_planning_accounting')
                if record is None:unknown_plans+=1
                else:add_meter(planning,validate_failed_planning(record,checks,loc+'/paid_failed_planning'))
            elif kind not in MODEL_NAMES:
                exact(checks,ex.get('planner_input'),None,loc+'/no_exception_planner')
            if ex.get('requested_torque') is not None:
                computed=verify_active_inputs(ex,origin,sr,models,checks,loc,required_complete=False)
                projections+=len(ex['model_input_diagnostics'])
                for name in computed:
                    add_meter(diag,successful_one_meter());add_meter(per_model[name],successful_one_meter())
                saved=ex['diagnostic_prediction_accounting'];delta=saved['pair_prediction_attempts']-diag['pair_prediction_attempts']
                if delta:
                    exact(checks,delta,1,loc+'/one_failed_diagnostic_attempt')
                    absent=[n for n in MODEL_NAMES if n in ex['model_input_diagnostics'] and n not in computed]
                    exact(checks,len(absent),1,loc+'/failed_diagnostic_is_only_saved_input_without_prediction')
                    diag=failed_diagnostic_meter(guard.meter_record(diag),ex,checks,loc+'/retained_failed_pair')
                    if len(absent)==1:per_model[absent[0]]=failed_diagnostic_meter(guard.meter_record(per_model[absent[0]]),ex,checks,loc+'/failed_head_model')
                returned=ex.get('returned_step_diagnostics')
                # The collector scores only after valid actual torque telemetry.
                # A returned but unwritten endpoint preserves its paid score.
                if returned is not None and ex.get('observation_after_retrieval_error') is None:
                    predicted_count=ev['metric_prediction_step_count']
                    if returned['executed_substeps']==10 and any(predicted_count.get(n,0)>len(qerrors.get(n,[])) for n in computed):
                        scores_at(ex,computed,loc,exception=True)
                    elif returned['executed_substeps']!=10 and len(ev['partial_endpoint_prediction_errors'])>len(partials):
                        scores_at(ex,computed,loc,exception=True)
        exact(checks,ex['diagnostic_prediction_accounting'],guard.meter_record(diag),loc+'/exception_retains_all_prediction_attempts')
    checks.compare(ev['position_prediction_rmse'],metric_maps(qerrors),tid+'/saved_position_prediction_metrics')
    checks.compare(ev['velocity_prediction_rmse'],metric_maps(verrors),tid+'/saved_velocity_prediction_metrics')
    exact(checks,ev['metric_prediction_step_count'],{n:len(values) for n,values in verrors.items() if values},tid+'/complete_prediction_endpoint_counts')
    checks.compare(ev['partial_endpoint_prediction_errors'],partials,tid+'/partial_predictions_never_complete_score')
    guard.validate_meter(ev['diagnostic_prediction_accounting'],checks,tid+'/diagnostic_bounds',400)
    exact(checks,ev['diagnostic_prediction_accounting'],guard.meter_record(diag),tid+'/total_diagnostic_cost')
    exact(checks,set(ev['diagnostic_prediction_accounting_per_model']),set(MODEL_NAMES),tid+'/exact_two_diagnostic_model_ledgers')
    for name in MODEL_NAMES:
        guard.validate_meter(ev['diagnostic_prediction_accounting_per_model'][name],checks,tid+'/model_meter/'+name,200)
        exact(checks,ev['diagnostic_prediction_accounting_per_model'][name],guard.meter_record(per_model[name]),tid+'/exact_model_meter/'+name)
    exact(checks,ev['diagnostic_input_projection_pair_calls'],projections,tid+'/explicit_public_projection_cost')
    expected_planning={**planning,'scalar_counts_complete':unknown_plans==0 and planning['unknown_scalar_failure_count']==0,
        'scalar_counts_is_lower_bound':unknown_plans>0 or planning['unknown_scalar_failure_count']>0,
        'unknown_failed_planner_calls':unknown_plans}
    exact(checks,ev['planning_accounting'],expected_planning,tid+'/paid_planning_cost')
    checks.check(planning['pair_prediction_attempts']<=200*81*15 and planning['scalar_prediction_attempts']<=2*200*81*15,'original_per_trial_planning_caps',tid)
    for field,expected in (('planner_attempt_count',plan_attempts),('planner_decision_count',plan_decisions),
        ('failed_planner_attempts',failed_plans),('planner_fallbacks',fallbacks)):
        exact(checks,ev[field],expected,tid+'/'+field)
    present=kind in MODEL_NAMES and episode['kind'] in sr.get('fresh_prefix_bindings',{})
    spec=planner_spec(models['qref'],models['ranges']) if present else None
    exact(checks,ev['planner_spec'],spec,tid+'/original_configuration_with_explicit_history')
    fingerprint=lag.digest(spec) if present else None
    for key in ('planner_fingerprint_before','planner_fingerprint_after'):exact(checks,ev[key],fingerprint,tid+'/'+key)
    for field in ('controller_seconds_total','pd_seconds_total'):
        checks.check(finite(ev[field]) and ev[field]>=0.,'finite_nonzero_or_zero_compute_time',tid+'/'+field)
    return {'model_updates':0,'diagnostic_accounting':guard.meter_record(diag),
        'diagnostic_pair_attempts':diag['pair_prediction_attempts'],'diagnostic_scalar_attempts':diag['scalar_prediction_attempts'],
        'diagnostic_accounting_per_model':{n:guard.meter_record(per_model[n]) for n in MODEL_NAMES},
        'planning_accounting':expected_planning,'planning_pair_attempts':planning['pair_prediction_attempts'],
        'planning_scalar_attempts':planning['scalar_prediction_attempts'],
        'planning_attempts':plan_attempts,'planning_decisions':plan_decisions,'failed_planning_attempts':failed_plans,
        'planning_fallbacks':fallbacks,'diagnostic_input_projection_pair_calls':projections,
        'position_prediction_rmse':metric_maps(qerrors),'velocity_prediction_rmse':metric_maps(verrors),
        'metric_prediction_step_count':{n:len(v) for n,v in verrors.items() if v},'partial_prediction_endpoints':partials,
        'exception_math_accounting_semantics':'saved unknown scalar/planning failures are explicit lower bounds, never zero computation'}

def verify_metadata(metadata,checks):
    fixed={'schema_version':1,'suite':'guard_lag_control_development','synthetic_fixture':False,
        'seeds':[0,1,2],'kinds':list(KINDS),'pose':'supine','joint_indices':[0,1],
        'prefix_steps':100,'control_steps_per_trial':200,'maximum_control_calls':3600,'maximum_physics_steps':36000,
        'maximum_diagnostic_pair_predictions':4800,'maximum_diagnostic_scalar_predictions':9600,
        'maximum_planning_pair_predictions':1458000,'maximum_planning_scalar_predictions':2916000,
        'model_updates':0,'policy_parameter_updates':0,'gain_updates':0,'gate_updates':0,'D_refits':0,'D_prediction_reexecutions':0,
        'gpu':None,'backend':'MuJoCo CPU','split':'development','native_joint_count':8,'parameter_count_per_output':11,
        'integration':'endpoint_euler','model_input_basis':'known_angle_guard','planned_episode_count':12,
        'planned_episodes':planned_matrix(),'c4_scientifically_validated':False,
        'study_abort_spec':{'active_only':True,'absolute_q_minus_qref_rad':.12,'absolute_velocity_rad_s':1.,'comparison':'>=',
            'any_axis':True,'feedback_action':None,'complete_terminal_scored_not_complete':True},
        'environment_config':common.ENVIRONMENT,
        'cloning_compute':'nonzero object construction and immutable parameter copying; not predictions or RLS'}
    for field,value in fixed.items():exact(checks,metadata[field],value,'frozen_metadata/'+field)
    checks.check(metadata['status'] in ('completed','exception'),'batch_known_final_status')
    for field in ('wall_seconds','cpu_seconds'):
        checks.check(finite(metadata[field]) and metadata[field]>=0.,'finite_batch_compute_cost',field)
    checks.check(isinstance(metadata['dependencies'],dict) and isinstance(metadata['mujoco_version'],str),
        'dependency_and_MuJoCo_version_recorded')
    versions={str(k).lower():str(v) for k,v in metadata['dependencies'].items()}
    exact(checks,versions.get('mujoco'),metadata['mujoco_version'],'MuJoCo_distribution_version_identity')

def validate_trace_order(rows,plans,checks):
    groups={p['trial_id']:[] for p in plans};order={p['trial_id']:i for i,p in enumerate(plans)};previous=-1
    for row in rows:
        tid=row['trial_id'];index=order.get(tid,-1)
        if tid not in groups:raise ValueError('Only fixed E trial identities permitted')
        checks.check(index>=previous,'original_seed_group_trace_order',tid);previous=index
        exact(checks,tid,f"seed{row['seed']}_{row['kind']}",'trace_identity/'+tid)
        checks.check(type(row['seed']) is int and row['seed'] in RESET and row['kind'] in KINDS,'declared_trace_seed_kind',tid)
        groups[tid].append(row)
    return groups

def blocked_result(sr,ep,rows,ranges,checks):
    if sr is not None and ep['kind'] in sr.get('evaluations',{}):
        result,_,_=physical_base(sr,ep,rows,ranges,checks)
        exact(checks,sr['evaluations'][ep['kind']].get('model_updates'),0,ep['trial_id']+'/blocked_no_updates')
        exact(checks,sr['evaluations'][ep['kind']]['reason'],ep['reason'],ep['trial_id']+'/blocked_reason')
    else:
        checks.check(ep['status']=='blocked' and not rows,'missing_seed_only_fatal_blocked',ep['trial_id'])
        for key in ('control_calls_attempted','control_steps','physics_steps'):exact(checks,ep[key],0,ep['trial_id']+'/blocked/'+key)
        for phase in PHASES:exact(checks,ep['phase_budgets'][phase],{'control_calls_attempted':0,'control_steps':0,'physics_steps':0},ep['trial_id']+'/blocked/'+phase)
        result={'eligible':False,'completed':False,'status':'blocked'}
    exact(checks,ep['reason'],'earlier_fatal_or_source_failure',ep['trial_id']+'/only_fatal_dependency_block')
    return {**result,'model_updates':0,'diagnostic_pair_attempts':0,'diagnostic_scalar_attempts':0,
        'planning_pair_attempts':0,'planning_scalar_attempts':0,'diagnostic_input_projection_pair_calls':0}

def audit_archive(path,checks,git_root,auditor_bytes,support_bytes,read_context=None):
    files,metadata=read_inputs(Path(path),checks)
    if read_context is not None:read_context['metadata']=metadata;read_context['input_hashes']={n:sha(z) for n,z in files.items()}
    verify_metadata(metadata,checks)
    members,ranges,pd=verify_sources(files,metadata,checks,git_root,auditor_bytes,support_bytes)
    restored,d_binding=bind_d_states(members,metadata,ranges,checks)
    episodes=parse(files['episodes.json']);plans=planned_matrix()
    if not isinstance(episodes,list):raise ValueError('Bare fixed E episode list required')
    epmap=lag.b._maps(episodes,'trial_id',{p['trial_id'] for p in plans},'exact_E_episode_matrix')
    exact(checks,[ep['trial_id'] for ep in episodes],[p['trial_id'] for p in plans],'fixed_E_plan_execution_order')
    raw_seeds=parse(files['seed_results.json'])
    if not isinstance(raw_seeds,list):raise ValueError('Bare E seed result list required')
    saved=lag.b._maps(raw_seeds,'seed',set(RESET),'exact_E_seed_matrix')
    exact(checks,[r['seed'] for r in raw_seeds],list(RESET),'fixed_E_seed_order')
    blob=gzip.decompress(files['trace.jsonl.gz'])
    READ_COST['E_trace_gzip_decompressions']+=1;READ_COST['E_trace_uncompressed_binary_bytes']+=len(blob)
    trace=[]
    for line in blob.splitlines():
        if line.strip():trace.append(parse(line));READ_COST['E_trace_json_lines_parsed']+=1
    groups=validate_trace_order(trace,plans,checks)
    derived=[];totals=Counter();executed_trials=0
    for seed in RESET:
        sr=saved[seed];model_data=restored[seed];evaluations={}
        exact(checks,sr['seed'],seed,f'seed{seed}/identity');exact(checks,sr['reset_seed'],RESET[seed],f'seed{seed}/fixed_reset')
        exact(checks,set(sr['evaluations']),set(KINDS),f'seed{seed}/exact_four_outcomes')
        actual=any(epmap[f'seed{seed}_{kind}']['status']!='blocked' for kind in KINDS)
        if actual:
            exact(checks,sr['expected_environment_fingerprint'],ENVIRONMENT_FINGERPRINT,f'seed{seed}/original_physical_condition')
            exact(checks,sr['frozen_models'],model_data['snapshots'],f'seed{seed}/saved_D_and_generic_cold_snapshots')
            exact(checks,sr['model_source'],{'D_commit':D_COMMIT,'snapshot_binding':d_binding['selected_snapshot_path'],'new_updates':0},f'seed{seed}/only_restored_D_model_source')
        for kind in KINDS:
            ep=epmap[f'seed{seed}_{kind}'];items=groups[ep['trial_id']];before=checks.failed
            if ep['status']=='blocked':result=blocked_result(sr,ep,items,ranges,checks)
            else:
                executed_trials+=1
                result,regular,exceptions=physical_base(sr,ep,items,ranges,checks)
                verify_reference(sr,ep,regular,model_data,ranges,checks)
                actor=actor_and_diagnostics(sr,ep,regular,exceptions,model_data,checks)
                result.update(actor)
                result['outcome_reason']=ep['reason'];result['study_abort']=ep['study_abort']
                result['environment_terminated']=ep['environment_terminated'];result['environment_stop_reason']=ep['environment_stop_reason']
                result['collector_exception']=ep['collector_exception']
            result['eligible']=bool(result['eligible'] and checks.failed==before)
            evaluations[kind]=result
            for field in ('diagnostic_pair_attempts','diagnostic_scalar_attempts','planning_pair_attempts','planning_scalar_attempts','diagnostic_input_projection_pair_calls'):
                totals[field]+=result.get(field,0)
        checks.check(set(sr['fresh_prefix_bindings']).issubset(KINDS),'only_declared_fresh_prefix_bindings',f'seed{seed}')
        derived.append({'seed':seed,'reset_seed':RESET[seed],'evaluations':evaluations})
    budget={key:sum(ep[key] for ep in episodes) for key in ('control_calls_attempted','control_steps','physics_steps')}
    for key,value in budget.items():exact(checks,metadata[key],value,'batch_paid_ledger/'+key)
    checks.check(budget['control_calls_attempted']<=3600 and budget['control_steps']<=3600 and budget['physics_steps']<=36000,
        'unchanged_total_physical_caps')
    for key,cap in (('diagnostic_pair_attempts',4800),('diagnostic_scalar_attempts',9600),('planning_pair_attempts',1458000),('planning_scalar_attempts',2916000)):
        checks.check(totals[key]<=cap,'unchanged_total_math_caps',key)
    for field,status in (('completed_trials','completed'),('terminated_trials','terminated'),('exception_trials','exception'),('blocked_trials','blocked')):
        exact(checks,metadata[field],sum(ep['status']==status for ep in episodes),'batch_outcome_count/'+field)
    checks.check(metadata['status']!='completed' or not any(ep['status']=='blocked' for ep in episodes),'ordinary_stops_continue_all_planned_trials')
    attempts,returns=metadata['frozen_model_clone_attempts'],metadata['frozen_model_clone_returns']
    checks.check(type(attempts) is int and type(returns) is int and 2*executed_trials<=returns<=attempts<=24 and attempts-returns<=1,
        'nonzero_clone_construction_and_failure_ledger')
    return {'seeds':derived,'episodes':episodes,'input_hashes':{n:sha(data) for n,data in files.items()},
        'source_commit':metadata['source_commit'],'source_sha256':metadata['source_sha256'],
        'D_binding':d_binding,'pd_binding':pd,'physical_fingerprint':ENVIRONMENT_FINGERPRINT,
        'budget':{**budget,'model_updates':0,'policy_parameter_updates':0,'gain_updates':0,'gate_updates':0},
        'paid_prediction_accounting':dict(totals),
        'restoration_and_cloning':{'restored_models':3,'cold_initializations':3,'clone_attempts':attempts,'clone_returns':returns,
            'description':'nonzero saved-state construction/copying; no prediction, fit or RLS update'},
        'sample_semantics':'E fresh native physical control only; D identity saved states only; all seeds kept, complete endpoints and partial/failed costs separate',
        'c4_scientifically_validated':False,'zero_comparison_is_adoption_gate':False,
        'risk_value_semantics':'Missing paid raw substeps give lower bounds for peaks, impulse and mismatch counts, upper bounds for minimum contact distance; endpoints alone do not prove safety.'}

def audit(path,*,git_root=ROOT):
    if not FORMAL_AUDIT_ENABLED or Path(__file__).resolve()!=(ROOT/AUDITOR).resolve():
        raise RuntimeError('Ignored E auditor staging has no formal archive execution permission')
    wall,cpu=time.perf_counter(),time.process_time();checks=Checks();result=None;read_context={}
    before_math=Counter(lag.MATH_COST);before_counts=Counter(COUNTS);before_reads=Counter(READ_COST)
    auditor_bytes=Path(__file__).read_bytes();support_bytes={n:(ROOT/n).read_bytes() for n in SUPPORT}
    READ_COST['executing_auditor_source_reads']+=1;READ_COST['executing_auditor_source_bytes']+=len(auditor_bytes)
    READ_COST['executing_support_source_reads']+=len(support_bytes);READ_COST['executing_support_source_bytes']+=sum(len(z) for z in support_bytes.values())
    try:
        result=audit_archive(Path(path),checks,git_root,auditor_bytes,support_bytes,read_context)
    except (OSError,ValueError,KeyError,TypeError,IndexError,AttributeError,OverflowError,zipfile.BadZipFile,EOFError) as exc:
        checks.check(False,'E_archive_schema_or_read_error',{'type':type(exc).__name__,'message':str(exc)})
    gates=development_gates([] if result is None else result['seeds'])
    consistency=checks.failed==0;validation=consistency and git_root is not None
    for key in ('control_hypothesis','pd_reference'):
        gates[key]['validated_pass']=bool(gates[key]['passed'] and validation)
    return {'schema_version':1,'created_at_utc':datetime.now(timezone.utc).isoformat(),
        'audit_script_sha256':sha(auditor_bytes),'audit_dependency_sha256':{n:sha(z) for n,z in support_bytes.items()},
        'immutable_scope':PRODUCTION_SPEC.record(),'checks':checks.count,'failed':checks.failed,'violations':checks.violations,
        'maximum_recomputation_difference':checks.maximum_difference,'archive':result,'final_gates':gates,
        'input_file_sha256':read_context.get('input_hashes'),
        'reported_paid_budget_if_replay_incomplete':{k:read_context.get('metadata',{}).get(k) for k in ('control_calls_attempted','control_steps','physics_steps','model_updates')},
        'data_consistency_verified':consistency,'development_validation_eligible':validation,
        'c4_scientifically_validated':False,'zero_comparison_is_adoption_gate':False,
        'execution':{'wall_seconds':time.perf_counter()-wall,'cpu_seconds':time.process_time()-cpu,
            'timing_scope':'entry through report assembly; excludes imports and final JSON writing',
            'python':sys.version,'platform':platform.platform(),'source_git_verification_enabled':git_root is not None,
            'independent_math_cost':dict(lag.MATH_COST-before_math),'independent_E_replay_counts':dict(COUNTS-before_counts),
            'read_accounting':dict(READ_COST-before_reads),'new_physics_control_calls':0,'new_physics_substeps':0,
            'online_helper_imports':0,'old_C_D_audit_reexecutions':0,'old_C_D_prediction_reexecutions':0,
            'D_refits':0,'model_policy_gain_gate_updates':0,'real_robot_calls':0}}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',required=True,type=Path);parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    if not FORMAL_AUDIT_ENABLED:parser.error('Formal E audit disabled in ignored staging')
    if args.output.exists():parser.error('Refuse to overwrite the one first E audit')
    result=audit(args.input)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps({'checks':result['checks'],'failed':result['failed'],'data_consistency_verified':result['data_consistency_verified'],
        'matrix_complete':result['final_gates']['matrix_complete'],'c4_scientifically_validated':False},allow_nan=False))
    return 0 if result['failed']==0 else 1

if __name__=='__main__':raise SystemExit(main())
