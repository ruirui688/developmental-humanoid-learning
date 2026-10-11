"""Independent standard-library C4 single-lag offline audit.

No online helper imports, physics, old-model refit, C full-audit execution,
MPC replay or scientific adoption gates. Formal replay follows root freeze.
"""
from __future__ import annotations
import argparse
from collections import Counter
from dataclasses import dataclass
from datetime import datetime,timezone
import gzip
import hashlib
import importlib.util
import io
import json
import math
from pathlib import Path
import platform
import re
import subprocess
import sys
import time
import zipfile

ROOT=next(p for p in Path(__file__).resolve().parents if (p/'pyproject.toml').is_file())
def _load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module)
    return module
b=_load('_lag_offline_independent_support',ROOT/'scripts/audit_guard_coupled_development.py')
guard,common=b.guard,b.common
Checks,finite,pair,vector,digest=b.Checks,b.finite,b.pair,b.vector,b.digest
SUPPORT=('scripts/audit_guard_coupled_development.py',*b.SUPPORT)
SOURCE='src/developmental_physics/guard_lag_offline_development.py'
CORE='src/developmental_physics/guard_lag_pair_model.py'
AUDITOR='scripts/audit_guard_lag_offline.py'
PROTOCOL='docs/GUARD_LAG_OFFLINE_DEVELOPMENT_PROTOCOL.md'
C_COMMIT='5ea8df42b09588845760daf0dc1f270aef2a87f1'
C_SUMMARY_SHA='dbc368dc628cb5785415c8b27416215e628a892cf550284a681447f9867aa4af'
C_AUDIT_SHA='985137b28d9ee6eb19c98c80e807c815d0d79273a46c938b5f1e4c59be3f33ac'
C_AUDITOR_SHA='962a928b5d643ed2a3d4da20da2940a9a4e17932818c859beb204f11bf59ffa3'
C_RAW=('metadata.json','episodes.json','seed_results.json','trace.jsonl.gz','source_snapshot.zip','manifest.json')
PREDICTORS=('nominal9','sparse9','continuation9','lag_sparse11','lag_continuation11')
OLD_MODELS={'nominal9':'nominal_guard','sparse9':'learned_sparse','continuation9':'learned_continuation'}
GROUPS=('sparse','continuation')
HORIZONS=(1,2,5,15)
TRIAL_KINDS=('prediction','nominal_guard','learned_sparse','learned_continuation','PDselected','zero')
FEATURE_NAMES=('v0','v1','q0-qref0','q1-qref1','start_G0(q0,u0)','start_G1(q1,u1)',
    'h(start_G0(q0,u0))','h(start_G1(q1,u1))','1','v0-previous_v0','v1-previous_v1')
MATH_COST=Counter()
ABS_TOL=1e-10
REL_TOL=5e-10
MODAL_POLYNOMIAL_TOL=1e-8

class Checks(Checks):
    """Bounded float/BLAS tolerance; labels, provenance and hashes stay exact."""
    def compare(self,actual,expected,location):
        if type(expected) is float:
            valid=finite(actual) and finite(expected)
            difference=abs(actual-expected) if valid else None
            if valid:self.maximum_difference=max(self.maximum_difference,difference)
            bound=ABS_TOL+REL_TOL*max(abs(actual),abs(expected)) if valid else None
            self.check(valid and difference<=bound,'bounded_numeric_recomputation',
                {'location':location,'actual':actual,'expected':expected,'difference':difference,'bound':bound})
        else:super().compare(actual,expected,location)

@dataclass(frozen=True)
class AuditSpec:
    def record(self):
        return {'suite':'guard_lag_offline_development','split':'same_development_data',
            'seeds':[0,1,2],'calibrations':['sparse','continuation'],'predictors':list(PREDICTORS),
            'trial_kinds':list(TRIAL_KINDS),'horizons':list(HORIZONS),'parameters_per_head':11,
            'calibration_intervals_per_model':400,'original9_refits':0,'new_physics_calls':0,
            'no_scientific_gates_or_ranking':True,'absolute_tolerance':ABS_TOL,
            'relative_tolerance':REL_TOL,'modal_polynomial_scaled_tolerance':MODAL_POLYNOMIAL_TOL}
PRODUCTION_SPEC=AuditSpec()

def exact(checks,actual,expected,loc):
    checks.check(guard.strict_equal(actual,expected),'exact_source_or_causal_identity',loc)

def valid_counter(value):
    if not isinstance(value,dict) or any(type(v) is not int or v<0 for v in value.values()):
        raise ValueError('Nonnegative integer sparse mathematical ledger required')
    return Counter(value)

def clean(value):
    if isinstance(value,float) and not finite(value):
        return 'infinite' if value>0 else 'negative_infinite' if value<0 else 'nonfinite'
    if isinstance(value,dict):return {k:clean(v) for k,v in value.items()}
    if isinstance(value,(tuple,list)):return [clean(v) for v in value]
    return value

def sha(blob): return hashlib.sha256(blob).hexdigest()
def json_blob(blob): return json.loads(blob.decode('utf-8'))
def rows_blob(blob):
    with gzip.GzipFile(fileobj=io.BytesIO(blob)) as stream:
        return [json_blob(line) for line in stream if line.strip()]

def initial_state(ranges):
    theta=[[0.]*11 for _ in range(2)]
    for i in range(2): theta[i][i]=1.;theta[i][4+i]=.02
    return {'theta':theta,'covariance':[[[100. if i==j else 0. for j in range(11)] for i in range(11)] for _ in range(2)],
        'count':0,'ranges':ranges,'observed_theta':deep_rows(theta),
        'observed_covariance':[[row.copy() for row in matrix] for matrix in
            [[[100. if i==j else 0. for j in range(11)] for i in range(11)] for _ in range(2)]]}
def deep_rows(rows): return [row.copy() for row in rows]

def lag_features(qref,q,v,u,previous_v,ranges):
    MATH_COST['lag_feature_attempts']+=1
    qref,q,v,u,previous_v=(pair(x) for x in (qref,q,v,u,previous_v))
    mapped=guard.describe_input(q,u,('known_angle_guard',ranges))['model_feature_command_nm']
    x=[*v,*[q[i]-qref[i] for i in range(2)],*mapped,
       *[math.copysign(max(abs(z)-.25,0.),z) for z in mapped],1.,
       *[v[i]-previous_v[i] for i in range(2)]]
    if not all(finite(z) for z in x): raise ValueError('Finite explicit native-history features required')
    MATH_COST['lag_feature_successes']+=1
    return [x.copy(),x.copy()]

def parameter_record(qref,state,observed=False):
    cold=initial_state(state['ranges'])['theta']
    return {'structure':'guard_coupled_hinge9_velocity_increment11','qref_rad':list(qref),'dt_seconds':.02,
        'features_per_output':[list(FEATURE_NAMES),list(FEATURE_NAMES)],
        'coefficients':state['observed_theta'] if observed else state['theta'],
        'covariance':state['observed_covariance'] if observed else state['covariance'],
        'initial_coefficients':cold,'initial_covariance_scale':100.,'forgetting_factor':1.,
        'hinge_threshold_nm':.25,'hinge_threshold_updates':0,'integration':'endpoint_euler','dtype':'float64',
        'input_mapping':{'basis':'known_angle_guard','public_guard':guard.guard_spec(state['ranges']),
            'feature_command':'G(current q, already known original requested u) at control start'},
        'history':{'stored_in_model':False,'argument':'previous_v',
            'native_initialization':'two consecutive observed native velocity endpoints, 20 ms apart',
            'unknown_or_reset_history':'must not call predict/update; never substitute zero',
            'rollout_advance':'caller assigns old current v to previous_v after each predicted step'},
        'model_definition':{'parameter_count_per_output':11,'base_columns':list(range(9)),'added_columns':[9,10],
            'added_prior':'zero in both outputs','prediction_arithmetic':'single ordinary float64 11-column dot per output',
            'rls_arithmetic_source':'unchanged PairBodyModel._propose_update','physical_queries':0}}

def verify_snapshot(saved,state,qref,checks,loc,trainable):
    expected=parameter_record(qref,state)
    keys=set(expected)|{'parameter_fingerprint','trainable','vector_update_count','scalar_update_count','output_update_counts','update_commit','input_boundary'}
    checks.check(set(saved)==keys,'exact_lag_snapshot_fields',loc)
    checks.compare(saved,expected,loc+'/independent_parameters')
    checks.compare(saved,{'vector_update_count':state['count'],'scalar_update_count':2*state['count'],
        'output_update_counts':[state['count']]*2,'trainable':trainable,
        'update_commit':'single immutable state reference for both outputs, covariance and counts',
        'input_boundary':'native current/previous velocities, current q and already known u; no future actual torque'},loc+'/atomic')
    checks.compare(saved['parameter_fingerprint'],digest({k:saved[k] for k in expected}),loc+'/exact_parameter_hash')
    state['observed_theta']=saved['coefficients'];state['observed_covariance']=saved['covariance']

def predict11(theta,ranges,qref,q,v,u,previous_v):
    MATH_COST['lag_pair_prediction_attempts']+=1
    x=lag_features(qref,q,v,u,previous_v,ranges)
    if len(theta)!=2 or any(len(row)!=11 or not all(finite(t) for t in row) for row in theta): raise ValueError('Two finite eleven-column heads required')
    nv=[]
    for i in range(2):
        MATH_COST['lag_scalar_prediction_attempts']+=1
        z=sum(t*f for t,f in zip(theta[i],x[i]))
        if not finite(z): raise ValueError('Nonfinite lag velocity prediction')
        nv.append(z);MATH_COST['lag_scalar_prediction_successes']+=1
    nq=[q[i]+.02*nv[i] for i in range(2)]
    if not all(finite(z) for z in nq): raise ValueError('Nonfinite lag endpoint Euler prediction')
    MATH_COST['lag_pair_prediction_successes']+=1
    return nq,nv

def replay_rls11(theta,covariance,x,label):
    MATH_COST['lag_scalar_rls_proposal_attempts']+=1;n=11
    if len(theta)!=n or len(x)!=n or len(covariance)!=n or any(len(row)!=n for row in covariance): raise ValueError('Exact eleven-column RLS shape required')
    if not all(finite(z) for z in [*theta,*x,label,*[z for row in covariance for z in row]]): raise ValueError('Finite RLS inputs required')
    px=[sum(covariance[i][j]*x[j] for j in range(n)) for i in range(n)]
    denominator=1.+sum(x[i]*px[i] for i in range(n))
    if not finite(denominator) or denominator<=0: raise ValueError('Positive finite RLS denominator required')
    residual=label-sum(theta[i]*x[i] for i in range(n));gain=[z/denominator for z in px]
    theta_after=[theta[i]+gain[i]*residual for i in range(n)]
    raw=[[covariance[i][j]-gain[i]*px[j] for j in range(n)] for i in range(n)]
    covariance_after=[[.5*(raw[i][j]+raw[j][i]) for j in range(n)] for i in range(n)]
    if not all(finite(z) for z in [*theta_after,*[z for row in covariance_after for z in row]]): raise ValueError('Finite RLS proposals required')
    MATH_COST['lag_scalar_rls_proposal_successes']+=1
    return theta_after,covariance_after,residual

def replay_update(saved,state,qref,q,v,u,previous_v,label,transition_id,checks,loc):
    x=lag_features(qref,q,v,u,previous_v,state['ranges'])
    prediction=predict11(state['observed_theta'],state['ranges'],qref,q,v,u,previous_v)
    proposals=[replay_rls11(state['theta'][i],state['covariance'][i],x[i],label[i]) for i in range(2)]
    checks.compare(saved,{'updated':True,'shared_transition_id':transition_id,'features_per_output':x,
        'preupdate_prediction':{'next_q_rad':prediction[0],'next_v_rad_s':prediction[1]},
        'observed_next_v_rad_s':label,'parameter_fingerprint_before':digest(parameter_record(qref,state,True)),
        'vector_update_count':state['count']+1,'scalar_update_count':2*(state['count']+1),'committed_scalar_updates':2},loc+'/causal_atomic_update')
    checks.check(len(saved['output_records'])==2,'exact_two_head_publish',loc)
    for i,(theta,cov,residual) in enumerate(proposals):
        checks.compare(saved['output_records'][i],{'output_index':i,'features':x[i],'observed_next_v_rad_s':label[i],
            'preupdate_error_rad_s':residual,'proposed_coefficients':theta,'proposed_covariance':cov,'committed':True},loc+f'/head{i}')
    state['theta']=[p[0] for p in proposals];state['covariance']=[p[1] for p in proposals];state['count']+=1
    state['observed_theta']=[r['proposed_coefficients'] for r in saved['output_records']]
    state['observed_covariance']=[r['proposed_covariance'] for r in saved['output_records']]
    checks.compare(saved['parameter_fingerprint_after'],digest(parameter_record(qref,state,True)),loc+'/after_exact_hash')

def native_origin(rows,index):
    if type(index) is not int or index<100 or index>=len(rows): raise ValueError('Original active index with paid prefix required')
    current=rows[index];previous,current_endpoint=rows[index-2],rows[index-1]
    if any(r['step_index']!=j or r['diagnostics']['executed_substeps']!=10 for r,j in
        ((previous,index-2),(current_endpoint,index-1))): raise ValueError('Two contiguous complete native history endpoints required')
    if any(r['trial_id']!=current['trial_id'] for r in (previous,current_endpoint)) or \
        current_endpoint['observation_before']!=previous['observation_after'] or current['observation_before']!=current_endpoint['observation_after']:
        raise ValueError('Same uninterrupted original native history required')
    q,v=[pair(current['observation_before'][k][:2]) for k in ('joint_position','joint_velocity')]
    return q,v,pair(previous['observation_after']['joint_velocity'][:2])

def available_horizons(rows,index):
    native_origin(rows,index)
    result=[]
    for horizon in HORIZONS:
        if index+horizon>len(rows): continue
        block=rows[index:index+horizon]
        valid=all(r['trial_id']==rows[index]['trial_id'] and r['step_index']==index+j and
            r['diagnostics']['executed_substeps']==10 and
            (j==0 or r['observation_before']==block[j-1]['observation_after']) and
            (j==horizon-1 or not (r['diagnostics']['terminated'] or r.get('study_abort'))) for j,r in enumerate(block))
        if valid: result.append(horizon)
    return result

def old_state(snapshot,qref,ranges,checks,loc,trainable=False):
    state=b.initial_state(ranges)
    state.update(theta=snapshot['coefficients'],covariance=snapshot['covariance'],count=snapshot['vector_update_count'])
    b.verify_snapshot(snapshot,state,qref,checks,loc,trainable)
    return state

def rollout_math(theta,ranges,qref,q,v,previous_v,commands,*,lag):
    """One conditional trajectory; no future observed endpoint corrects it."""
    q,v,previous_v=(pair(x) for x in (q,v,previous_v));result=[]
    for u in commands:
        command=pair(u);before=(q.copy(),v.copy(),previous_v.copy())
        nq,nv=predict11(theta,ranges,qref,q,v,command,previous_v) if lag else b.predict(theta,ranges,qref,q,v,command)
        mapped=guard.describe_input(q,command,('known_angle_guard',ranges))
        result.append({'q_before':q.copy(),'v_before':v.copy(),'previous_v_before':previous_v.copy(),
            'requested_nm':command,'start_guard':mapped,'next_q_rad':nq,'next_v_rad_s':nv})
        previous_v=v;v=nv;q=nq
    return result

def mm(a,z): return [[sum(a[i][k]*z[k][j] for k in range(len(z))) for j in range(len(z[0]))] for i in range(len(a))]
def modal_matrix(theta):
    lag=len(theta[0])==11;a=[row[:2] for row in theta];bb=[row[2:4] for row in theta]
    c=[row[9:11] for row in theta] if lag else [[0.,0.],[0.,0.]]
    if not lag:
        return [[(1. if i==j else 0.)+.02*bb[i][j] for j in range(2)]+[.02*a[i][j] for j in range(2)] for i in range(2)]+[bb[i]+a[i] for i in range(2)]
    first=[[(1. if i==j else 0.)+.02*bb[i][j] for j in range(2)]+[.02*(a[i][j]+c[i][j]) for j in range(2)]+[-.02*c[i][j] for j in range(2)] for i in range(2)]
    return first+[bb[i]+[a[i][j]+c[i][j] for j in range(2)]+[-c[i][j] for j in range(2)] for i in range(2)]+[[0.,0.]+[1. if i==j else 0. for j in range(2)]+[0.,0.] for i in range(2)]

def characteristic_coefficients(matrix):
    n=len(matrix);work=[[1. if i==j else 0. for j in range(n)] for i in range(n)];coeff=[1.]
    for k in range(1,n+1):
        work=mm(matrix,work);c=-sum(work[i][i] for i in range(n))/k;coeff.append(c)
        for i in range(n): work[i][i]+=c
    return coeff

def standardized_design(values):
    if not values or any(len(row)!=len(values[0]) or not all(finite(x) for x in row) for row in values): raise ValueError('Finite nonempty design required')
    n,p=len(values),len(values[0]);columns=list(map(list,zip(*values)));means=[];rms=[];z=[];zero=[]
    for i,column in enumerate(columns):
        if i==8: means.append(0.);rms.append(1.);z.append(column.copy());continue
        mean=math.fsum(column)/n;centered=[x-mean for x in column];scale=math.sqrt(math.fsum(x*x for x in centered)/n)
        means.append(mean);rms.append(scale)
        if scale==0.: zero.append(i);z.append([0.]*n)
        else: z.append([x/scale for x in centered])
    gram=[[math.fsum(z[i][k]*z[j][k] for k in range(n))/n for j in range(p)] for i in range(p)]
    return {'count':n,'dimension':p,'column_mean':means,'centered_rms':rms,'zero_variance_columns':zero,
        'standardized_columns':z,'standardized_gram':gram}

def singular_values(columns):
    """Small one-sided Jacobi SVD avoids squaring the condition number."""
    work=[col.copy() for col in columns];p=len(work);eps=sys.float_info.epsilon
    for _ in range(60):
        changed=False
        for j in range(p):
            for k in range(j+1,p):
                aa=math.fsum(x*x for x in work[j]);bb=math.fsum(x*x for x in work[k]);gg=math.fsum(x*y for x,y in zip(work[j],work[k]))
                if aa==0. or bb==0. or abs(gg)<=eps*math.sqrt(aa*bb): continue
                tau=(bb-aa)/(2.*gg);t=math.copysign(1.,tau)/(abs(tau)+math.hypot(1.,tau));cs=1./math.sqrt(1.+t*t);sn=cs*t
                oldj,oldk=work[j],work[k];work[j]=[cs*x-sn*y for x,y in zip(oldj,oldk)];work[k]=[sn*x+cs*y for x,y in zip(oldj,oldk)];changed=True
        if not changed: break
    return sorted((math.sqrt(math.fsum(x*x for x in col)) for col in work),reverse=True)

def complete(row):
    return isinstance(row.get('diagnostics'),dict) and row['diagnostics'].get('executed_substeps')==10 and 'observation_before' in row and 'observation_after' in row

def native(observation):return pair(observation['joint_position'][:2]),pair(observation['joint_velocity'][:2])

def continuous(previous,current):
    return previous['trial_id']==current['trial_id'] and previous['step_index']+1==current['step_index'] and complete(previous) and complete(current) and \
        native(previous['observation_after'])==native(current['observation_before']) and previous.get('study_abort') is None and not previous['diagnostics'].get('terminated',False)

def source_intervals(rows,phase):
    by_step={r['step_index']:r for r in rows}
    if len(by_step)!=len(rows):raise ValueError('Unique original trial step indices required')
    prefix98,prefix99=by_step.get(98),by_step.get(99)
    ready=prefix98 is not None and prefix99 is not None and prefix98.get('phase')==prefix99.get('phase')=='prefix' and continuous(prefix98,prefix99)
    result=[];unavailable=[];ages=[0,0];last=None
    stop_step=next((r['step_index'] for r in sorted(rows,key=lambda x:x['step_index']) if r.get('study_abort') is not None or r.get('diagnostics',{}).get('terminated',False)),None)
    for row in sorted(rows,key=lambda x:x['step_index']):
        if row.get('phase')!=phase:continue
        step=row['step_index'];previous=by_step.get(step-1);reason=None
        if stop_step is not None and step>stop_step:reason='after_source_stop'
        elif not complete(row):reason='not_a_complete_returned_20ms_interval'
        elif step==100:
            if not ready or not continuous(prefix99,row):reason='prefix98_99_history_not_complete_native_continuous'
        elif previous is None or previous.get('phase')!=phase or not continuous(previous,row):reason='previous_active_native_endpoint_unavailable_or_discontinuous'
        if reason:
            unavailable.append({'transition_id':row.get('shared_transition_id'),'step_index':step,'reason':reason});ages=[0,0];last=None;continue
        prior=prefix98 if step==100 else by_step.get(step-2)
        if prior is None or not complete(prior) or not continuous(prior,previous):
            unavailable.append({'transition_id':row.get('shared_transition_id'),'step_index':step,'reason':'immediately_prior_velocity_endpoint_unavailable'});continue
        q,v=native(row['observation_before']);u=pair(row['requested_torque'][:2]);pv=native(prior['observation_after'])[1]
        if last is None or last+1!=step:ages=[0,0]
        ages=[ages[i]+1 if u[i]!=0. else 0 for i in range(2)]
        result.append({'row':row,'q':q,'v':v,'u':u,'previous_v':pv,
            'history_transition_ids':[prior['shared_transition_id'],previous['shared_transition_id']],
            'request_nonzero_age_steps':ages.copy()});last=step
    return result,unavailable

def common_windows(intervals):
    result=[]
    for index,origin in enumerate(intervals):
        sequence=[]
        for item in intervals[index:index+15]:
            if sequence and not continuous(sequence[-1]['row'],item['row']):break
            sequence.append(item)
            if item['row'].get('study_abort') is not None or item['row']['diagnostics'].get('terminated',False):break
        available=[h for h in HORIZONS if h<=len(sequence)]
        result.append({'origin':origin,'sequence':sequence[:max(available)],'available_horizons':available})
    return result

def design_statistics(values,names):
    n,p=len(values),len(values[0]);columns=[list(c) for c in zip(*values)]
    means=[math.fsum(c)/n for c in columns]
    variance=[math.fsum((x-m)**2 for x in c)/n for c,m in zip(columns,means)]
    rms=[math.sqrt(z) for z in variance];constant=[i for i,c in enumerate(columns) if all(x==c[0] for x in c)]
    scales=[1. if all(x==1. for x in c) else rms[i] for i,c in enumerate(columns)]
    z=[[1.]*n if all(x==1. for x in c) else [0.]*n if i in constant else [(x-means[i])/rms[i] for x in c] for i,c in enumerate(columns)]
    gram=[[math.fsum(a*b for a,b in zip(ci,cj))/n for cj in z] for ci in z]
    zm=[math.fsum(c)/n for c in z]
    correlation=[[math.fsum((a-zm[i])*(bb-zm[j]) for a,bb in zip(z[i],z[j]))/n for j in range(p)] for i in range(p)]
    sv=singular_values(z);tolerance=sys.float_info.epsilon*max(n,p)*sv[0];rank=sum(v>tolerance for v in sv)
    MATH_COST['design_feature_rows']+=n;MATH_COST['design_svd_calls']+=1;MATH_COST['design_gram_products']+=2
    return {'columns':list(names),'rows':n,'minimum':[min(c) for c in columns],'maximum':[max(c) for c in columns],
        'mean':means,'variance':variance,'centered_rms':rms,'coefficient_column_scale':scales,
        'constant_columns':constant,'zero_variance_columns':[i for i,v in enumerate(rms) if v==0.],
        'normalization':'nonconstant centered/RMS; identically-one column kept one; other constant columns kept zero',
        'standardized_gram':gram,'column_correlation':correlation,'standardized_design_singular_values':sv,
        'column_correlation_defined':[[i not in constant and j not in constant for j in range(p)] for i in range(p)],
        'constant_correlation_semantics':'zero matrix cells involving constant columns are undefined placeholders',
        'rank_tolerance':tolerance,'numerical_rank':rank,'rank_is_an_adoption_gate':False,
        'condition_reason':None if rank==p else 'numerical_rank_less_than_column_count'}

def verify_design(saved,values,names,checks,loc):
    expected=design_statistics(values,names);checks.compare(saved,expected,loc+'/independent_design')
    # The independently checked singular spectrum is used to recompute reported
    # ratios, whose last tiny singular value can be ill-conditioned numerically.
    sv=vector(saved['standardized_design_singular_values'],len(names));n=len(values)
    condition=sv[0]/sv[-1] if expected['numerical_rank']==len(names) else float('inf')
    checks.compare(saved,clean({'gram_singular_values':[v*v/n for v in sv],
        'standardized_design_condition':condition,'standardized_gram_condition':condition**2}),loc+'/checked_spectrum_ratios')
    return expected['coefficient_column_scale']

def verify_modal(saved,theta,checks,loc):
    matrix=modal_matrix(theta);checks.compare(saved['matrix'],matrix,loc+'/causal_F')
    roots=[complex(r['real'],r['imag']) for r in saved['eigenvalues']]
    checks.check(len(roots)==len(matrix) and all(finite(z.real) and finite(z.imag) for z in roots),'all_finite_modal_roots',loc)
    expected=characteristic_coefficients(matrix);polynomial=[1.+0j]
    for root in roots:
        next_coeff=[0j]*(len(polynomial)+1)
        for i,c in enumerate(polynomial):next_coeff[i]+=c;next_coeff[i+1]-=c*root
        polynomial=next_coeff
    for i,(got,want) in enumerate(zip(polynomial,expected)):
        scale=max(1.,abs(want),sum(abs(c) for c in polynomial))
        checks.check(abs(got-want)<=MODAL_POLYNOMIAL_TOL*scale,'modal_root_multiset_characteristic_polynomial',loc+f'/coefficient{i}')
    for i,z in enumerate(roots):
        residual=0j;scale=0.
        for c in expected:residual=residual*z+c;scale=scale*abs(z)+abs(c)
        checks.check(abs(residual)<=MODAL_POLYNOMIAL_TOL*max(1.,scale),'modal_root_scaled_residual',loc+f'/root{i}')
    trans=[list(c) for c in zip(*matrix)];a,c=mm(trans,matrix),mm(matrix,trans)
    norm=math.sqrt(math.fsum((a[i][j]-c[i][j])**2 for i in range(len(a)) for j in range(len(a))))
    checks.compare(saved,{'spectral_radius':max(abs(z) for z in roots),'operator_2_norm':singular_values(trans)[0],
        'nonnormality_commutator_frobenius':norm,
        'scope':'fixed guard branch; excludes contact/guard switching; no stability/adoption gate'},loc+'/independent_modal_properties')
    MATH_COST['modal_characteristic_calculations']+=1;MATH_COST['modal_svd_calls']+=1;MATH_COST['modal_commutator_products']+=2

def verify_drift(records,snapshots,scales,lag,qref,ranges,checks,loc):
    checks.check(len(records)==4,'fixed_four_checkpoints',loc);previous=None;previous_count=None;cost=Counter()
    first=next((snapshots[n] for n in (100,200,300,400) if n in snapshots),None)
    if first is not None:previous=first['initial_coefficients'];previous_count=0
    for record,count in zip(records,(100,200,300,400)):
        snapshot=snapshots.get(count);checks.compare(record,{'vector_update_count':count,'available':snapshot is not None},loc+f'/{count}')
        if snapshot is None:
            exact(checks,record,{'vector_update_count':count,'available':False,'reason':'not_published'},loc+f'/{count}/unavailable');continue
        exact(checks,record['snapshot'],snapshot,loc+f'/{count}/saved_snapshot')
        if not lag:old_state(snapshot,qref,ranges,checks,loc+f'/{count}/old_read_only',True)
        theta=snapshot['coefficients'];change=None if previous is None else [[theta[i][j]-previous[i][j] for j in range(len(scales))] for i in range(2)]
        raw=weighted=None
        if change is not None:
            raw=[math.sqrt(math.fsum(x*x for x in head)) for head in change]
            weighted=[math.sqrt(math.fsum((head[j]*scales[j])**2 for j in range(len(scales)))) for head in change]
            cost['coefficient_change_head_l2_norms']+=4
        checks.compare(record,{'change_from_vector_update_count':previous_count,
            'coefficient_change':change,'raw_change_l2_per_head':raw,
            'column_scale_weighted_change_l2_per_head':weighted},loc+f'/{count}/drift')
        verify_modal(record['modal_diagnostics'],theta,checks,loc+f'/{count}/modal');previous=theta;previous_count=count
        cost.update(modal_eigenvalue_calls=1,modal_svd_calls=1,modal_matrix_products=2,modal_frobenius_norm_calls=1)
    return cost

FILES=('attempt.json','source_binding.json','source_snapshot.zip','calibration_updates.jsonl.gz',
       'diagnostics.json','rollouts.jsonl.gz','summary.json','run.json','manifest.json')

def verify_sources(path,source_root,checks,git_root):
    files={name:(path/name).read_bytes() for name in FILES}
    exact(checks,{p.name for p in path.iterdir() if p.is_file()},set(FILES),'output_exact_file_coverage')
    manifest=json_blob(files['manifest.json']);binding=json_blob(files['source_binding.json']);run=json_blob(files['run.json'])
    checks.compare(manifest,{'schema_version':1,'status':run['status']},'manifest_scope')
    exact(checks,set(manifest['files']),set(FILES)-{'manifest.json'},'manifest_exact_member_coverage')
    for name,blob in files.items():
        if name!='manifest.json':exact(checks,manifest['files'][name],{'sha256':sha(blob),'bytes':len(blob)},'manifest/'+name)
    freeze=binding['source_freeze'];commit=freeze['source_commit']
    checks.check(type(commit) is str and re.fullmatch('[0-9a-f]{40}',commit) is not None,'new_frozen_commit')
    exact(checks,binding['collection_commit'],C_COMMIT,'original_collection_commit')
    checks.compare(binding['execution_context'],{'verified_source_commit':commit,'verified_clean_worktree':True},'root_execution_context')
    exact(checks,run['execution_context'],binding['execution_context'],'run_execution_context')
    exact(checks,binding['protocol_path'],PROTOCOL,'canonical_protocol_path')
    members=b.source_members(files['source_snapshot.zip']);hashes=freeze['source_sha256']
    required={SOURCE,CORE,AUDITOR,PROTOCOL,*SUPPORT,'src/developmental_physics/local_model.py',
        'src/developmental_physics/local_pair_model.py','src/developmental_physics/guard_pair_model.py',
        'src/developmental_physics/guard_coupled_pair_model.py','pyproject.toml'}
    checks.check(required.issubset(hashes),'complete_frozen_runtime_source_coverage')
    exact(checks,set(members),set(hashes)|{'runtime_source_freeze.json'},'new_unique_source_zip_coverage')
    exact(checks,json_blob(members['runtime_source_freeze.json']),freeze,'runtime_freeze_record')
    exact(checks,sha(members['runtime_source_freeze.json']),binding['source_freeze_sha256'],'runtime_freeze_bytes')
    exact(checks,sha(files['source_snapshot.zip']),binding['source_snapshot_sha256'],'new_source_zip_identity')
    for name,expected in hashes.items():
        guard._path(name);guard._hash(expected);exact(checks,sha(members[name]),expected,'new_frozen_source/'+name)
        if git_root is not None:
            response=subprocess.run(['git','show',f'{commit}:{name}'],cwd=git_root,capture_output=True,check=False)
            checks.check(response.returncode==0 and response.stdout==members[name],'new_frozen_git_blob_bytes',name)
    exact(checks,members[AUDITOR],Path(__file__).read_bytes(),'executing_auditor_exact_identity')
    for name in SUPPORT:exact(checks,members[name],(ROOT/name).read_bytes(),'executing_support_exact_identity/'+name)
    raw={name:(source_root/'raw'/name).read_bytes() for name in C_RAW}
    summary_blob=(source_root/'summary_once/summary.json').read_bytes();audit_blob=(source_root/'first_audit.json').read_bytes()
    exact(checks,sha(summary_blob),C_SUMMARY_SHA,'original_sealed_summary_pin');exact(checks,sha(audit_blob),C_AUDIT_SHA,'original_sealed_first_audit_pin')
    exact(checks,binding['summary'],{'sha256':C_SUMMARY_SHA,'bytes':len(summary_blob)},'bound_original_summary')
    exact(checks,binding['first_audit'],{'sha256':C_AUDIT_SHA,'bytes':len(audit_blob)},'bound_original_first_audit')
    summary,audit=json_blob(summary_blob),json_blob(audit_blob);original_hashes={n:sha(z) for n,z in raw.items()}
    exact(checks,set(summary['original_input_sha256']),set(C_RAW),'exact_six_original_summary_inputs')
    exact(checks,summary['original_input_sha256'],original_hashes,'original_six_raw_bytes')
    exact(checks,binding['original_inputs'],{n:{'sha256':sha(z),'bytes':len(z)} for n,z in raw.items()},'bound_six_original_input_bytes')
    exact(checks,summary['source_commit'],C_COMMIT,'original_summary_commit')
    exact(checks,summary['expected_auditor_sha256'],C_AUDITOR_SHA,'original_summary_auditor')
    exact(checks,summary['binding_checks']['failed'],0,'original_summary_binding_checks')
    exact(checks,audit['failed'],0,'original_first_audit_checks');exact(checks,audit['violations'],[],'original_first_audit_violations')
    exact(checks,audit['audit_script_sha256'],C_AUDITOR_SHA,'original_first_audit_script')
    exact(checks,audit['final_gates']['data_consistency_verified'],True,'original_certified_data')
    exact(checks,audit['archive']['input_hashes'],original_hashes,'original_audit_certified_input_bytes')
    exact(checks,json_blob(raw['manifest.json']),{n:sha(z) for n,z in raw.items() if n!='manifest.json'},'original_raw_manifest')
    metadata=json_blob(raw['metadata.json']);exact(checks,metadata['source_commit'],C_COMMIT,'original_metadata_collection')
    old_members=b.source_members(raw['source_snapshot.zip']);old_hashes=metadata['source_sha256']
    exact(checks,set(old_members),set(old_hashes),'original_source_zip_unique_coverage')
    for name,value in old_hashes.items():exact(checks,sha(old_members[name]),value,'original_archived_source_identity/'+name)
    exact(checks,sha(old_members['scripts/audit_guard_exploration_development.py']),C_AUDITOR_SHA,'original_zip_certified_auditor')
    # This verifies archived C identities only: no old Git, physics/MPC audit,
    # original RLS refit or online module executes.
    return files,binding,raw,run,metadata

FIT_SUCCESS={'offline_vector_update_attempts':1,'offline_vector_update_returns':1,
    'offline_vector_updates_committed':1,'offline_scalar_updates_committed':2,
    'rls_internal_pair_attempts':1,'rls_internal_pair_successes':1,
    'rls_internal_scalar_attempts':2,'rls_internal_scalar_successes':2,
    'rls_scalar_proposal_attempts':2,'rls_scalar_proposal_successes':2,
    'rls_model_feature_pair_attempts':2,'rls_model_feature_pair_successes':2}

def replay_calibration(items,saved_rows,qref,ranges,checks,loc):
    state=initial_state(ranges);snapshots={};cost=Counter();failure=None
    checks.check(len(items)==400 and [i['row']['step_index'] for i in items]==list(range(100,500)),'full_fixed_calibration_sequence',loc)
    checks.check(1<=len(saved_rows)<=400,'single_pass_saved_calibration_length',loc)
    for index,saved in enumerate(saved_rows):
        item=items[index];row=item['row'];where=loc+f'/transition{index}'
        expected={'record_type':'lag_calibration_update','trial_id':row['trial_id'],'seed':row['seed'],'kind':row['kind'],
            'transition_id':row['shared_transition_id'],'step_index':row['step_index'],
            'input':{'q':item['q'],'v':item['v'],'u':item['u'],'previous_v':item['previous_v'],'next_v_label':native(row['observation_after'])[1]},
            'history_transition_ids':item['history_transition_ids']}
        for key,value in expected.items():exact(checks,saved[key],value,where+'/'+key)
        if saved['failure'] is not None:
            # Every retained failure must be reproducible; otherwise audit fails,
            # rather than silently treating a cropped fit as usable.
            caught=None
            try:
                x=lag_features(qref,item['q'],item['v'],item['u'],item['previous_v'],ranges)
                predict11(state['observed_theta'],ranges,qref,item['q'],item['v'],item['u'],item['previous_v'])
                for head in range(2):replay_rls11(state['theta'][head],state['covariance'][head],x[head],native(row['observation_after'])[1][head])
            except (ValueError,OverflowError) as exc:caught=exc
            checks.check(caught is not None,'retained_fit_failure_independently_reproducible',where)
            checks.check(index==len(saved_rows)-1,'no_updates_after_fit_failure',where)
            exact(checks,saved['update'],None,where+'/no_failed_update_publish');exact(checks,saved['committed_vector_updates'],0,where+'/atomic_failure_no_commit')
            failure=saved['failure'];cost.update(valid_counter(saved['cost_delta']));break
        replay_update(saved['update'],state,qref,item['q'],item['v'],item['u'],item['previous_v'],native(row['observation_after'])[1],row['shared_transition_id'],checks,where)
        exact(checks,saved['committed_vector_updates'],1,where+'/one_atomic_vector_commit')
        exact(checks,dict(valid_counter(saved['cost_delta'])),FIT_SUCCESS,where+'/exact_update_mathematical_cost');cost.update(FIT_SUCCESS)
        exact(checks,saved['fingerprint_after'],digest(parameter_record(qref,state,True)),where+'/exact_state_hash')
        checkpoint=saved['snapshot_at_fixed_count']
        if state['count'] in (100,200,300,400):
            verify_snapshot(checkpoint,state,qref,checks,where+'/checkpoint',True);snapshots[state['count']]=checkpoint
        else:exact(checks,checkpoint,None,where+'/only_fixed_checkpoints')
    complete_fit=state['count']==400 and failure is None
    checks.check(complete_fit or failure is not None,'no_silent_cropped_calibration',loc)
    return state,snapshots,cost,complete_fit,failure

def reuse_candidate(item,name,fingerprint,trial,ranges):
    if name not in OLD_MODELS:return None
    row=item['row'];saved_name=OLD_MODELS[name];prediction=row.get('predicted_next_qv',{}).get(saved_name)
    inputs=row.get('model_input_diagnostics',{}).get(saved_name)
    bound=row.get('model_fingerprints',{}).get(saved_name);provenance='saved_row_model_fingerprint'
    if bound is None:
        before,after=trial.get('models_before',{}),trial.get('models_after',{})
        if saved_name in before and before[saved_name]==after.get(saved_name):bound=before[saved_name];provenance='bound_saved_trial_equal_before_after_fingerprints'
        elif row['kind']==saved_name and trial.get('model_fingerprint_before') is not None and trial['model_fingerprint_before']==trial.get('model_fingerprint_after'):
            bound=trial['model_fingerprint_before'];provenance='bound_saved_actor_equal_before_after_fingerprints'
    if prediction is None or inputs is None or bound!=fingerprint:return None
    expected_g=guard.describe_input(item['q'],item['u'],('known_angle_guard',ranges))['model_feature_command_nm']
    if inputs.get('native_q_rad')!=item['q'] or inputs.get('requested_nm')!=item['u'] or inputs.get('model_feature_command_nm')!=inputs.get('projected_start_nm') or inputs.get('model_feature_command_nm')!=expected_g or inputs.get('input_basis')!='known_angle_guard':return None
    if not isinstance(prediction,(list,tuple)) or len(prediction)!=2:raise ValueError('Bound saved pair prediction must have two endpoints')
    q,v=pair(prediction[0]),pair(prediction[1])
    return {'q':q,'v':v,'fingerprint':bound,'provenance':provenance,'source_transition_id':row['shared_transition_id'],
        'native_v_exact':item['v'],'saved_input':inputs}

EVAL_SUCCESS={'evaluation_pair_attempts':1,'evaluation_pair_successes':1,
    'evaluation_scalar_attempts':2,'evaluation_scalar_successes':2,
    'evaluation_model_feature_pair_attempts':1,'evaluation_model_feature_pair_successes':1}

def audit_prediction(theta,ranges,qref,q,v,u,pv,lag):
    if lag:return predict11(theta,ranges,qref,q,v,u,pv)
    MATH_COST['old9_pair_prediction_attempts']+=1
    try:result=b.predict(theta,ranges,qref,q,v,u)
    except BaseException as exc:
        MATH_COST['old9_pair_prediction_failures']+=1
        if hasattr(exc,'attempts'):
            MATH_COST['old9_scalar_prediction_attempts']+=exc.attempts;MATH_COST['old9_scalar_prediction_successes']+=exc.successes
        else:MATH_COST['old9_unknown_scalar_failure_count']+=1
        raise
    MATH_COST['old9_pair_prediction_successes']+=1;MATH_COST['old9_scalar_prediction_attempts']+=2;MATH_COST['old9_scalar_prediction_successes']+=2
    return result

def verify_rollout(saved,window,name,model,qref,ranges,trial,checks,loc):
    item=window['origin'];row=item['row'];cost=Counter()
    expected={'record_type':'conditional_offline_rollout','seed':row['seed'],'trial_id':row['trial_id'],'kind':row['kind'],
        'origin_transition_id':row['shared_transition_id'],'origin_step_index':row['step_index'],'predictor':name,
        'available_horizons':window['available_horizons'],'history_transition_ids':item['history_transition_ids'],
        'native_start':{k:item[k] for k in ('q','v','previous_v')},'request_nonzero_age_steps':item['request_nonzero_age_steps'],
        'future_request_semantics':'offline conditioning only; never actor-visible or future actual input'}
    for key,value in expected.items():exact(checks,saved[key],value,loc+'/'+key)
    if model is None:
        exact(checks,saved['steps'],[],loc+'/unavailable_steps');exact(checks,saved['failure'],None,loc+'/unavailable_failure')
        exact(checks,saved['unavailable_reason'],'lag_calibration_failed_or_unavailable',loc+'/unavailable_reason')
        exact(checks,saved['cost_delta'],{'unavailable_model_rollout_records':1},loc+'/unavailable_cost')
        return Counter(unavailable_model_rollout_records=1)
    fingerprint=model['fingerprint'];exact(checks,saved['model_fingerprint'],fingerprint,loc+'/frozen_model_identity')
    checks.check('unavailable_reason' not in saved,'published_model_available',loc)
    q,v,pv=(item[k].copy() for k in ('q','v','previous_v'));lag=name.startswith('lag_');failed=saved['failure']
    expected_steps=len(window['sequence']) if failed is None else failed['at_h']-1
    checks.check(type(expected_steps) is int and 0<=expected_steps<=len(window['sequence']),'valid_mathematical_stop_position',loc)
    checks.check(len(saved['steps'])==expected_steps,'exact_completed_rollout_steps',loc)
    for index,source in enumerate(window['sequence']):
        h=index+1;command=source['u'];g=None;stage='diagnostic_start_guard'
        cost['diagnostic_guard_pair_evaluations']+=1;reuse=None
        prediction=None;error=None;math_before=Counter(MATH_COST)
        try:
            g=guard.describe_input(q,command,('known_angle_guard',ranges))['model_feature_command_nm']
            stage='saved_prediction_validation';reuse=reuse_candidate(item,name,fingerprint,trial,ranges) if h==1 else None
            stage='model_prediction'
            if reuse is not None:
                prediction=(reuse['q'],reuse['v']);MATH_COST['saved_one_step_identity_reuses']+=1
            else:prediction=audit_prediction(model['theta'],ranges,qref,q,v,command,pv,lag)
        except (ValueError,OverflowError) as exc:error=exc
        input_record={'q':q,'v':v,'previous_v':pv,'requested_u':command,'start_G':g}
        if h>len(saved['steps']):
            checks.check(failed is not None and failed['at_h']==h and error is not None,'saved_math_failure_reproduced_at_exact_horizon',loc+f'/h{h}')
            if failed is not None:
                exact(checks,failed['source_transition_id'],source['row']['shared_transition_id'],loc+'/failure_source')
                exact(checks,failed['input'],input_record,loc+'/failure_causal_input')
                exact(checks,failed['failure_stage'],stage,loc+'/failure_stage')
                delta=valid_counter(failed['cost_delta'])
                # Failure counters are checked against the independent output
                # stage, without inventing unpublished NumPy proposals.
                independent=MATH_COST-math_before
                expected_delta={'diagnostic_guard_pair_evaluations':1}
                if stage=='diagnostic_start_guard':expected_delta['diagnostic_start_guard_failures']=1
                elif stage=='saved_prediction_validation':expected_delta['saved_prediction_validation_failures']=1
                else:
                    expected_delta.update(evaluation_pair_attempts=1,evaluation_pair_failures=1,evaluation_model_feature_pair_attempts=1)
                    prefix='lag' if lag else 'old9'
                    attempts=independent[prefix+'_scalar_prediction_attempts'];successes=independent[prefix+'_scalar_prediction_successes']
                    if attempts:expected_delta['evaluation_scalar_attempts']=attempts
                    if successes:expected_delta['evaluation_scalar_successes']=successes
                    feature_success=independent['lag_feature_successes'] if lag else int(attempts>0)
                    if feature_success:expected_delta['evaluation_model_feature_pair_successes']=1
                    if independent[prefix+'_unknown_scalar_failure_count']:expected_delta['evaluation_unknown_scalar_failure_count']=1
                exact(checks,dict(delta),expected_delta,loc+'/exact_failed_stage_cost')
                cost.update({key:value for key,value in delta.items() if key!='diagnostic_guard_pair_evaluations'})
            break
        step=saved['steps'][index]
        exact(checks,step['h'],h,loc+f'/h{h}/index');exact(checks,step['source_transition_id'],source['row']['shared_transition_id'],loc+f'/h{h}/source')
        exact(checks,step['input'],input_record,loc+f'/h{h}/own_predicted_input')
        checks.check(error is None,'saved_success_independently_finite',loc+f'/h{h}')
        if prediction is not None:checks.compare(step['prediction'],{'q':prediction[0],'v':prediction[1]},loc+f'/h{h}/independent_math')
        exact(checks,step['reuse'],reuse,loc+f'/h{h}/exact_saved_prediction_reuse')
        delta={'reused_saved_pair_predictions':1} if reuse is not None else EVAL_SUCCESS
        exact(checks,step['cost_delta'],{'diagnostic_guard_pair_evaluations':1,**delta},loc+f'/h{h}/mathematical_cost');cost.update(delta)
        # Raw saved prediction is the sole next caller state. Its independent
        # arithmetic was checked above; observed source endpoints are never read
        # as an intermediate correction.
        pv,q,v=v,pair(step['prediction']['q']),pair(step['prediction']['v'])
    exact(checks,saved['cost_delta'],dict(cost),loc+'/total_rollout_cost')
    return cost

METRIC_GROUPS=('all','native_start_G:negative','native_start_G:zero','native_start_G:positive',
    'request_nonzero_age:zero','request_nonzero_age:1','request_nonzero_age:2','request_nonzero_age:3-5','request_nonzero_age:6+')
def age_group(age):return 'zero' if age==0 else '1' if age==1 else '2' if age==2 else '3-5' if age<=5 else '6+'

def derive_metrics(records,windows,ranges):
    metrics=[];cost=Counter()
    for name in PREDICTORS:
        own=[r for r in records if r['predictor']==name]
        for h in HORIZONS:
            common={w['origin']['row']['shared_transition_id']:w for w in windows if h in w['available_horizons']}
            eligible=[r for r in own if r['origin_transition_id'] in common]
            for axis in range(2):
                grouped={group:[] for group in METRIC_GROUPS};grouped['all']=eligible
                for r in eligible:
                    origin=common[r['origin_transition_id']]['origin'];g=guard.describe_input(origin['q'],origin['u'],('known_angle_guard',ranges))['model_feature_command_nm'][axis]
                    cost['diagnostic_guard_pair_evaluations']+=1
                    grouped['native_start_G:'+('negative' if g<0. else 'positive' if g>0. else 'zero')].append(r)
                    grouped['request_nonzero_age:'+age_group(origin['request_nonzero_age_steps'][axis])].append(r)
                for group,members in grouped.items():
                    failures=sum(r['failure'] is not None and r['failure']['at_h']<=h for r in members)
                    unavailable=sum(bool(r.get('unavailable_reason')) for r in members);errors={'q':[],'v':[]}
                    for r in members:
                        if len(r['steps'])<h:continue
                        truth=native(common[r['origin_transition_id']]['sequence'][h-1]['row']['observation_after'])
                        for index,key in enumerate(('q','v')):errors[key].append(r['steps'][h-1]['prediction'][key][axis]-truth[index][axis])
                    available=bool(members) and not failures and not unavailable
                    result={'predictor':name,'h':h,'axis':axis,'group':group,'complete_window_count':len(members),
                        'mathematical_failure_count':failures,'unavailable_model_window_count':unavailable,'successful_endpoint_count':len(errors['q']),
                        'available':available,'reason':'no_complete_source_window' if not members else 'mathematical_failure_retained' if failures else 'predictor_unavailable' if unavailable else None,
                        'sample_size_note':'single_window_descriptive_only' if len(members)==1 else 'empty' if not members else None}
                    for key,e in errors.items():
                        result[key]={'rmse':math.sqrt(math.fsum(x*x for x in e)/len(e)),
                            'signed_bias_prediction_minus_observation':math.fsum(e)/len(e),'maximum_absolute_error':max(abs(x) for x in e)} if available else None
                    metrics.append(clean(result))
    return metrics,cost

COST_KEYS=('offline_vector_update_attempts','offline_vector_update_returns','offline_vector_update_failures',
    'offline_vector_updates_committed','offline_scalar_updates_committed','rls_internal_pair_attempts','rls_internal_pair_successes','rls_internal_pair_failures',
    'rls_internal_scalar_attempts','rls_internal_scalar_successes','rls_internal_unknown_scalar_failure_count',
    'rls_scalar_proposal_attempts','rls_scalar_proposal_successes','rls_model_feature_pair_attempts','rls_model_feature_pair_successes',
    'evaluation_pair_attempts','evaluation_pair_successes','evaluation_pair_failures','evaluation_scalar_attempts','evaluation_scalar_successes',
    'evaluation_unknown_scalar_failure_count','evaluation_model_feature_pair_attempts','evaluation_model_feature_pair_successes',
    'reused_saved_pair_predictions','unavailable_model_rollout_records','saved_prediction_validation_failures','diagnostic_start_guard_failures','diagnostic_guard_pair_evaluations','design_feature_rows_9','design_feature_rows_11',
    'design_gram_matrix_products','design_svd_calls','design_statistic_passes','modal_eigenvalue_calls','modal_svd_calls','modal_matrix_products',
    'modal_frobenius_norm_calls','coefficient_change_head_l2_norms')
FEATURES9=('v0','v1','q0-qref0','q1-qref1','start_G0','start_G1','hG0','hG1','1')
FEATURES11=(*FEATURES9,'v0-previous_v0','v1-previous_v1')
PHASE_SEQUENCE=('all_six_native_design9_design11_and_original9_saved_drift_complete',
    'all_six_single_pass_fresh_lag11_fits_complete_or_failure_retained','all_fixed_common_source_windows_conditionally_evaluated')

def unique_map(records,keys,expected,label):
    result={}
    for record in records:
        identity=tuple(record[k] for k in keys)
        if identity not in expected or identity in result:raise ValueError(label+' unique fixed identity required')
        result[identity]=record
    if set(result)!=set(expected):raise ValueError(label+' full fixed coverage required')
    return result

def audit_archive(path,source_root,checks,git_root):
    files,binding,raw,run,metadata=verify_sources(path,source_root,checks,git_root)
    seeds=json_blob(raw['seed_results.json']);seed_map=unique_map(seeds,('seed',),{(i,) for i in (0,1,2)},'original seed results')
    trace_bytes=gzip.decompress(raw['trace.jsonl.gz']);lines=trace_bytes.splitlines(keepends=True);trace=[json_blob(line) for line in lines if line.strip()]
    exact(checks,binding['read_cost'],{'identity_sha_reads':9+len(binding['source_freeze']['source_sha256']),
        'trace_rows_parsed':len(trace),'trace_decompressed_bytes':len(trace_bytes),'raw_seed_results_bytes':len(raw['seed_results.json'])},'runner_original_read_accounting')
    groups={};transition_ids=set()
    for row in trace:
        identity=(row['seed'],row['kind']);groups.setdefault(identity,[]).append(row)
        checks.check(row['shared_transition_id'] not in transition_ids,'original_unique_transition_identity',row['shared_transition_id']);transition_ids.add(row['shared_transition_id'])
    expected_groups={(seed,kind) for seed in (0,1,2) for kind in ('calibration_sparse','calibration_continuation',*TRIAL_KINDS)}
    exact(checks,set(groups),expected_groups,'original_fixed_trial_coverage')
    diag=json_blob(files['diagnostics.json']);diag_map=unique_map(diag,('seed','calibration'),{(seed,kind) for seed in (0,1,2) for kind in GROUPS},'six diagnostics')
    cal_rows=rows_blob(files['calibration_updates.jsonl.gz']);cal_groups={};cal_order=[]
    for row in cal_rows:
        identity=(row['seed'],row['kind'].removeprefix('calibration_'));cal_groups.setdefault(identity,[]).append(row);cal_order.append(identity)
    fit_order=[(seed,kind) for seed in (0,1,2) for kind in GROUPS]
    exact(checks,set(cal_groups),set(fit_order),'six_independent_cold_calibrations')
    exact(checks,cal_order,[identity for identity in fit_order for _ in cal_groups[identity]],'fixed_single_pass_fit_order')
    costs=Counter();prepared={};models={}
    # All old design and drift checks precede any new RLS replay here too.
    for seed in (0,1,2):
        sr=seed_map[(seed,)];qref=pair(sr['reference_q']);ranges=sr['public_joint_ranges'];models[seed]={}
        for name,snapshot in (('nominal9',sr['nominal_model']),('sparse9',sr['learned_models']['learned_sparse']),('continuation9',sr['learned_models']['learned_continuation'])):
            old_state(snapshot,qref,ranges,checks,f'seed{seed}/{name}/saved_frozen9',False)
            models[seed][name]={'theta':snapshot['coefficients'],'fingerprint':snapshot['parameter_fingerprint']}
        for kind in GROUPS:
            loc=f'seed{seed}/{kind}';record=diag_map[(seed,kind)]
            intervals,unavailable=source_intervals(groups[(seed,'calibration_'+kind)],'calibration')
            exact(checks,unavailable,[],loc+'/source_history_available');checks.check(len(intervals)==400,'full400_original_calibration',loc)
            x9=[b.features(qref,i['q'],i['v'],i['u'],ranges)[0] for i in intervals]
            x11=[[*x9[index],i['v'][0]-i['previous_v'][0],i['v'][1]-i['previous_v'][1]] for index,i in enumerate(intervals)]
            scales9=verify_design(record['design9'],x9,FEATURES9,checks,loc+'/design9')
            scales11=verify_design(record['design11'],x11,FEATURES11,checks,loc+'/design11')
            costs.update(diagnostic_guard_pair_evaluations=800,design_feature_rows_9=400,design_feature_rows_11=400,
                design_gram_matrix_products=4,design_svd_calls=2,design_statistic_passes=2)
            checks.compare(record,{'start_G_negative_counts':[sum(x[4+i]<0. for x in x9) for i in range(2)],
                'start_G_zero_counts':[sum(x[4+i]==0. for x in x9) for i in range(2)],
                'start_G_positive_counts':[sum(x[4+i]>0. for x in x9) for i in range(2)],
                'hinge_nonzero_counts':[sum(x[6+i]!=0. for x in x9) for i in range(2)]},loc+'/fixed_excitation_description')
            exact(checks,record['saved_actual_dose'],sr['evaluations']['calibration_'+kind]['excitation'],loc+'/unmodified_saved_actual_dose')
            snapshots={i['row']['model_snapshot_after']['vector_update_count']:i['row']['model_snapshot_after'] for i in intervals if i['row']['model_snapshot_after']['vector_update_count'] in (100,200,300,400)}
            exact(checks,set(snapshots),{100,200,300,400},loc+'/original_published_checkpoints')
            costs.update(verify_drift(record['original9_saved_coefficient_drift'],snapshots,scales9,False,qref,ranges,checks,loc+'/old9_drift'))
            prepared[(seed,kind)]={'intervals':intervals,'qref':qref,'ranges':ranges,'scales11':scales11}
    calibrations=[]
    for seed,kind in fit_order:
        loc=f'seed{seed}/{kind}';item=prepared[(seed,kind)];record=diag_map[(seed,kind)]
        state,snapshots,cost,completed,failure=replay_calibration(item['intervals'],cal_groups[(seed,kind)],item['qref'],item['ranges'],checks,loc+'/fresh_lag11_replay')
        costs.update(cost);verify_snapshot(record['lag11_final_snapshot'],state,item['qref'],checks,loc+'/final_lag11',True)
        costs.update(verify_drift(record['lag11_coefficient_drift'],snapshots,item['scales11'],True,item['qref'],item['ranges'],checks,loc+'/lag11_drift'))
        models[seed]['lag_'+kind+'11']={'theta':state['observed_theta'],'fingerprint':record['lag11_final_snapshot']['parameter_fingerprint']} if completed else None
        calibrations.append({'seed':seed,'kind':kind,'completed':completed,'failure':failure,
            'attempted_vector_updates':len(cal_groups[(seed,kind)]),'committed_vector_updates':state['count'],
            'unexecuted_planned_updates':400-len(cal_groups[(seed,kind)]),'remaining_uncommitted_updates':400-state['count']})
    exact(checks,run['calibrations'],calibrations,'run_fixed_calibration_accounting')
    rollout_rows=rows_blob(files['rollouts.jsonl.gz']);summary=json_blob(files['summary.json'])
    checks.compare(summary,{'schema_version':1,'predictors':list(PREDICTORS),'horizons':list(HORIZONS),
        'no_scientific_gates_or_ranking':True,'same_development_data':True},'summary_immutable_scope')
    summary_map=unique_map(summary['trials'],('seed','kind'),{(seed,kind) for seed in (0,1,2) for kind in TRIAL_KINDS},'eighteen evaluation trials')
    position=0;windows_count=0
    for seed in (0,1,2):
        sr=seed_map[(seed,)];qref=pair(sr['reference_q']);ranges=sr['public_joint_ranges']
        for kind in TRIAL_KINDS:
            loc=f'seed{seed}/{kind}';intervals,unavailable=source_intervals(groups[(seed,kind)],'prediction' if kind=='prediction' else 'control');windows=common_windows(intervals)
            records=[];trial=sr['evaluations'][kind];windows_count+=len(windows)
            for window in windows:
                for name in PREDICTORS:
                    if position>=len(rollout_rows):raise ValueError('Missing fixed source window predictor record')
                    record=rollout_rows[position];position+=1;records.append(record)
                    costs.update(verify_rollout(record,window,name,models[seed].get(name),qref,ranges,trial,checks,loc+f'/origin{window["origin"]["row"]["step_index"]}/{name}'))
            metrics,metric_cost=derive_metrics(records,windows,ranges);costs.update(metric_cost)
            counts={str(h):sum(h in w['available_horizons'] for w in windows) for h in HORIZONS}
            expected={'seed':seed,'kind':kind,'original_status':trial['status'],'original_completed':trial['completed'],
                'source_unavailable_intervals':unavailable,'source_complete_interval_count':len(intervals),
                'source_complete_windows_per_h':counts,'source_unavailable_windows_per_h':{str(h):len(intervals)-counts[str(h)] for h in HORIZONS},
                'unobserved_original_planned_active_intervals':(100 if kind=='prediction' else 200)-len(intervals)-len(unavailable),'metrics':metrics}
            checks.compare(summary_map[(seed,kind)],expected,loc+'/independent_summary')
    exact(checks,position,len(rollout_rows),'no_extra_or_missing_rollout_records')
    ledger={key:costs[key] for key in COST_KEYS};exact(checks,run['cost_ledger'],ledger,'independent_complete_mathematical_ledger')
    checks.check(set(costs).issubset(COST_KEYS),'no_undeclared_mathematical_cost_keys')
    exact(checks,run['phase_sequence'],list(PHASE_SEQUENCE),'all_old_diagnostics_before_new_fits_and_evaluation')
    expected_status='completed_with_retained_calibration_failures' if any(not c['completed'] for c in calibrations) else 'completed'
    checks.compare(run,{'schema_version':1,'status':expected_status,'failure':None,
        'scope':'fixed same-development-data single-lag offline diagnosis; no selection/science pass',
        'new_physics_control_calls':0,'new_physics_substeps':0,'original9_refits':0,'mpc_select_calls':0,
        'policy_gain_gate_updates':0,'pd_teacher_calls':0,'real_robot_calls':0},'run_fixed_zero_interaction_scope')
    checks.check(ledger['offline_vector_update_attempts']<=2400 and ledger['offline_vector_updates_committed']<=2400 and ledger['offline_scalar_updates_committed']<=4800,
        'fixed_new_offline_fit_caps')
    checks.check(ledger['rls_internal_pair_attempts']<=2400 and ledger['rls_internal_scalar_attempts']<=4800 and ledger['evaluation_pair_attempts']<=247500 and ledger['evaluation_scalar_attempts']<=495000,
        'fixed_prediction_math_caps')
    exact(checks,ledger['offline_vector_update_attempts'],ledger['offline_vector_update_returns']+ledger['offline_vector_update_failures'],'fit_attempt_return_failure_balance')
    exact(checks,ledger['evaluation_pair_attempts'],ledger['evaluation_pair_successes']+ledger['evaluation_pair_failures'],'evaluation_attempt_success_failure_balance')
    attempt=json_blob(files['attempt.json']);checks.compare(attempt,{'schema_version':1,'status':'started','calibrations':[],'failure':None},'original_attempt_record')
    exact(checks,attempt['created_at_utc'],run['created_at_utc'],'attempt_creation_identity')
    for key in ('wall_seconds','cpu_seconds'):checks.check(finite(run['execution'][key]) and run['execution'][key]>=0.,'finite_nonnegative_runtime',key)
    return {'input_file_sha256':{n:sha(blob) for n,blob in files.items()},'original_input_sha256':{n:sha(blob) for n,blob in raw.items()},
        'source_commit':binding['source_freeze']['source_commit'],'collection_commit':C_COMMIT,'derived_cost_ledger':ledger,
        'calibrations':calibrations,'source_origin_windows':windows_count,'rollout_records':len(rollout_rows),
        'summary_metrics_verified':len(summary['trials'])*len(PREDICTORS)*len(HORIZONS)*2*len(METRIC_GROUPS),
        'no_scientific_gates_or_ranking':True,'same_development_data':True}

def audit(path,source_root,*,git_root=ROOT):
    wall,cpu=time.perf_counter(),time.process_time();checks=Checks();result=None;before=Counter(MATH_COST)
    file_hashes={};source_root=Path(source_root);path=Path(path)
    try:
        file_hashes={n:sha((path/n).read_bytes()) for n in FILES if (path/n).is_file()}
        result=audit_archive(path,source_root,checks,git_root)
    except (OSError,ValueError,KeyError,TypeError,IndexError,AttributeError,OverflowError,zipfile.BadZipFile,EOFError) as exc:
        checks.check(False,'offline_archive_schema_or_read_error',{'type':type(exc).__name__,'message':str(exc)})
    return {'schema_version':1,'created_at_utc':datetime.now(timezone.utc).isoformat(),
        'audit_script_sha256':sha(Path(__file__).read_bytes()),'audit_dependency_sha256':{n:sha((ROOT/n).read_bytes()) for n in SUPPORT},
        'immutable_scope':PRODUCTION_SPEC.record(),'checks':checks.count,'failed':checks.failed,'violations':checks.violations,
        'maximum_recomputation_difference':checks.maximum_difference,'input_file_sha256':file_hashes,'archive':result,
        'data_consistency_verified':checks.failed==0,'no_scientific_gates_or_ranking':True,
        'execution':{'wall_seconds':time.perf_counter()-wall,'cpu_seconds':time.process_time()-cpu,
            'timing_scope':'entry through report assembly; excludes imports/final JSON writing',
            'python':sys.version,'platform':platform.platform(),'source_git_verification_enabled':git_root is not None,
            'independent_math_cost':dict(MATH_COST-before),'new_physics_control_calls':0,'new_physics_substeps':0,
            'online_helper_imports':0,'prior_C_full_audit_reexecutions':0,'original9_refits':0,'mpc_select_calls':0,
            'policy_gain_gate_updates':0,'pd_teacher_calls':0,'real_robot_calls':0}}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',required=True,type=Path);parser.add_argument('--source-root',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path);parser.add_argument('--git-root',type=Path,default=ROOT)
    args=parser.parse_args()
    if args.output.exists():parser.error('Refuse to overwrite first audit')
    result=audit(args.input,args.source_root,git_root=args.git_root)
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps({'checks':result['checks'],'failed':result['failed'],'data_consistency_verified':result['data_consistency_verified'],
        'no_scientific_gates_or_ranking':True},allow_nan=False))
    return 0 if result['failed']==0 else 1
if __name__=='__main__':raise SystemExit(main())
