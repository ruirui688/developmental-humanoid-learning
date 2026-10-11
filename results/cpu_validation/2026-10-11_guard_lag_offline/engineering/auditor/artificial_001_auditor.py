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
