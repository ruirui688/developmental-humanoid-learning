"""Independent two-joint frozen-log audit: standard library, no physics/fitting imports.

Only archived native measurements are inputs to independent mathematical replay.
Scientific gates are fixed by the committed native-only development protocol.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
import gzip
import hashlib
import importlib.util
from itertools import product
import json
import math
from pathlib import Path
import platform
import sys
import time
import xml.etree.ElementTree as ET
import zipfile

ROOT = next(p for p in Path(__file__).resolve().parents if (p/'pyproject.toml').is_file())
_loader = importlib.util.spec_from_file_location('_pair_common_audit', ROOT/'scripts/audit_local_frozen.py')
common = importlib.util.module_from_spec(_loader)
sys.modules[_loader.name] = common
_loader.loader.exec_module(common)
Checks, vector, finite = common.Checks, common.vector, common.finite
digest, file_hash, load_json, rmse = common.digest, common.file_hash, common.load_json, common.rmse
DT, PHYSICS_DT = .02, .002
PHASES = ('prefix', 'calibration', 'prediction', 'control')
KINDS = ('calibration', 'prediction_low', 'prediction_full', 'nominal_mpc',
         'diagonal_mpc', 'coupled_mpc', 'combined_pd', 'zero_torque')
CONTROL_KINDS, MPC_KINDS = KINDS[3:], KINDS[3:6]
STRUCTURES = {'nominal':'diagonal_hinge5', 'diagonal':'diagonal_hinge5', 'coupled':'coupled_hinge9'}
EFFORT_KEYS, NATIVE, ENVIRONMENT = common.EFFORT_KEYS, common.NATIVE, common.ENVIRONMENT
MPC_CONFIG = dict(common.MPC_CONFIG)
CAL_AMPLITUDES = (.125, .25, .375, .5, .25)
PRED_AMPLITUDES = {'low':(.25,)*5, 'full':(.125,.25,.375,.5,.375)}
PRED_DIRECTIONS = ((1.,0.),(0.,1.),(1.,1.),(1.,-1.),(1.,1.))
PLANNING_KEYS = ('pair_prediction_attempts','pair_prediction_successes','scalar_prediction_attempts',
                 'scalar_prediction_successes','failed_pair_prediction_attempts','unknown_scalar_failure_count')

@dataclass(frozen=True)
class PairAuditSpec:
    suite: str = 'pair_development'
    pose: str = 'supine'
    joint_indices: tuple[int,int] = (0,1)
    seeds: tuple[int,...] = (0,1,2)
    reset_seed_pairs: tuple[tuple[int,int],...] = ((0,3757552657),(1,1641411168),(2,2001025171))
    protocol: str = 'docs/PAIR_BODY_DEVELOPMENT_PROTOCOL.md'
    split: str = 'development'
    pd_gains: tuple[tuple[float,float],...] = ((64.,0.),(64.,1.))
    scientific_gates_frozen: bool = True
    tracking_per_axis: bool = True
    synthetic_fixture: bool = False
    control_steps: int = 200
    prefix_steps: int = 100
    calibration_steps: int = 400
    prediction_steps: int = 100
    fixture_source: str | None = None

    def __post_init__(self):
        if (type(self.joint_indices) is not tuple or self.joint_indices != (0,1)
            or any(type(i) is not int for i in self.joint_indices)
            or type(self.seeds) is not tuple or (self.seeds != (0,1,2) and not
                (self.synthetic_fixture and self.seeds and self.seeds==tuple(i for i in (0,1,2) if i in self.seeds)))
            or any(type(i) is not int for i in self.seeds)
            or type(self.reset_seed_pairs) is not tuple or len(self.reset_seed_pairs)!=len(self.seeds)
            or any(type(p) is not tuple or len(p)!=2 or any(type(i) is not int for i in p) for p in self.reset_seed_pairs)
            or len(set(k for k,v in self.reset_seed_pairs))!=len(self.seeds) or set(k for k,v in self.reset_seed_pairs)!=set(self.seeds)
            or any(not 0<=v<2**32 for k,v in self.reset_seed_pairs)
            or type(self.pd_gains) is not tuple or self.pd_gains != ((64.,0.),(64.,1.))
            or any(type(p) is not tuple or len(p)!=2 or not all(finite(v) for v in p) for p in self.pd_gains)
            or type(self.scientific_gates_frozen) is not bool or type(self.tracking_per_axis) is not bool or type(self.synthetic_fixture) is not bool
            or type(self.control_steps) is not int or not 1<=self.control_steps<=200
            or self.control_steps!=200 and not self.synthetic_fixture
            or any(type(v) is not int or not 1<=v<=cap for v,cap in
                ((self.prefix_steps,100),(self.calibration_steps,400),(self.prediction_steps,100)))
            or not self.synthetic_fixture and (self.prefix_steps,self.calibration_steps,self.prediction_steps)!=(100,400,100)
            or self.fixture_source is not None and not (self.synthetic_fixture
                and self.fixture_source=='external/c4b_pair_staging/pair_frozen_validation.py')
            or any(type(x) is not str or not x for x in (self.suite,self.pose,self.protocol,self.split))
            or Path(self.protocol).is_absolute() or '..' in Path(self.protocol).parts):
            raise ValueError('Immutable exact pair scope, gains and protocol required.')

    @property
    def reset_seeds(self): return dict(self.reset_seed_pairs)

    @property
    def required_sources(self):
        runner=self.fixture_source or 'src/developmental_physics/pair_frozen_validation.py'
        auditor='scripts/audit_pair_frozen.py'
        return common.BASE_REQUIRED_SOURCES | {self.protocol,
            'src/developmental_physics/local_pair_model.py',
            runner,'scripts/audit_local_frozen.py',auditor}

    def record(self):
        return {'suite':self.suite,'pose':self.pose,'joint_indices':list(self.joint_indices),
                'seeds':list(self.seeds),'reset_seeds':self.reset_seeds,'protocol':self.protocol,
                'split':self.split,'pd_gains':[{'kp':kp,'kd':kd} for kp,kd in self.pd_gains],
                'scientific_gates_frozen':self.scientific_gates_frozen,'tracking_per_axis':self.tracking_per_axis,
                'synthetic_fixture':self.synthetic_fixture,'control_steps':self.control_steps,
                'prefix_steps':self.prefix_steps,'calibration_steps':self.calibration_steps,'prediction_steps':self.prediction_steps,
                'fixture_source':self.fixture_source}

PAIR_DEVELOPMENT_SPEC = PairAuditSpec()

def pair(value): return vector(list(value) if type(value) is tuple else value,2)

def features(structure,qref,q,v,u):
    qref,q,v,u=(pair(x) for x in (qref,q,v,u))
    h=[(1. if x>0 else -1. if x<0 else 0.)*max(abs(x)-.25,0.) for x in u]
    if structure=='diagonal_hinge5':
        result=[[v[i],q[i]-qref[i],u[i],h[i],1.] for i in range(2)]
    elif structure=='coupled_hinge9':
        row=[*v,*[q[i]-qref[i] for i in range(2)],*u,*h,1.]
        result=[row.copy(),row.copy()]
    else: raise ValueError('Declared pair structure required.')
    if not all(finite(x) for row in result for x in row): raise ValueError('Nonfinite pair features.')
    return result

def initial_state(structure):
    n={'diagonal_hinge5':5,'coupled_hinge9':9}[structure]
    theta=[[0.]*n for i in range(2)]
    for i in range(2):
        theta[i][0 if n==5 else i]=1.
        theta[i][2 if n==5 else 4+i]=.02
    covariance=[[[100. if i==j else 0. for j in range(n)] for i in range(n)] for output in range(2)]
    return {'structure':structure,'theta':theta,'covariance':covariance,'count':0,
            'observed_theta':[row.copy() for row in theta],
            'observed_covariance':[[row.copy() for row in matrix] for matrix in covariance]}

def parameter_record(qref,state,*,observed=False):
    structure=state['structure']
    names=([[f'v{i}',f'q{i}-qref{i}',f'u{i}',f'h(u{i})','1'] for i in range(2)]
           if structure=='diagonal_hinge5' else
           [['v0','v1','q0-qref0','q1-qref1','u0','u1','h(u0)','h(u1)','1'] for i in range(2)])
    return {'structure':structure,'qref_rad':list(qref),'dt_seconds':DT,'features_per_output':names,
            'coefficients':state['observed_theta' if observed else 'theta'],
            'covariance':state['observed_covariance' if observed else 'covariance'],
            'initial_coefficients':initial_state(structure)['theta'],
            'initial_covariance_scale':100.,'forgetting_factor':1.,'hinge_threshold_nm':.25,
            'hinge_threshold_updates':0,'integration':'endpoint_euler','dtype':'float64'}

class PredictionError(ValueError):
    def __init__(self,attempts,successes):
        super().__init__('Nonfinite independent pair prediction.')
        self.attempts,self.successes=attempts,successes

def predict(theta,structure,qref,q,v,u):
    try: x=features(structure,qref,q,v,u)
    except ValueError as exc: raise PredictionError(0,0) from exc
    n=5 if structure=='diagonal_hinge5' else 9
    if len(theta)!=2 or any(len(row)!=n or not all(finite(t) for t in row) for row in theta):
        raise ValueError('Two finite declared velocity heads required.')
    next_v=[]
    for i in range(2):
        value=sum(t*f for t,f in zip(theta[i],x[i]))
        if not finite(value): raise PredictionError(i+1,i)
        next_v.append(value)
    next_q=[q[i]+DT*next_v[i] for i in range(2)]
    if not all(finite(z) for z in next_q): raise PredictionError(2,2)
    return next_q,next_v

def replay_rls(theta,covariance,x,label):
    n=len(theta)
    if n not in (5,9) or len(x)!=n or len(covariance)!=n or any(len(row)!=n for row in covariance):
        raise ValueError('Declared 5/9-dimensional RLS shape required.')
    if not all(finite(v) for v in [*theta,*x,label,*[v for row in covariance for v in row]]):
        raise ValueError('Finite RLS inputs required.')
    projected=[sum(covariance[i][j]*x[j] for j in range(n)) for i in range(n)]
    denominator=1.+sum(x[i]*projected[i] for i in range(n))
    if not finite(denominator) or denominator<=0: raise ValueError('Invalid RLS denominator.')
    residual=label-sum(theta[i]*x[i] for i in range(n))
    gain=[v/denominator for v in projected]
    after=[theta[i]+gain[i]*residual for i in range(n)]
    raw=[[covariance[i][j]-gain[i]*projected[j] for j in range(n)] for i in range(n)]
    matrix=[[.5*(raw[i][j]+raw[j][i]) for j in range(n)] for i in range(n)]
    if not all(finite(v) for v in [*after,*[v for row in matrix for v in row]]): raise ValueError('Nonfinite RLS proposal.')
    return after,matrix,residual

def propose_pair(state,qref,q,v,u,labels):
    x=features(state['structure'],qref,q,v,u)
    proposals=[replay_rls(state['theta'][i],state['covariance'][i],x[i],pair(labels)[i]) for i in range(2)]
    return x,proposals

def replay_update(item,row,state,qref,checks,location):
    q,v=[row['observation_before'][k][:2] for k in ('joint_position','joint_velocity')]
    u,labels=row['requested_torque'][:2],row['observation_after']['joint_velocity'][:2]
    x,proposals=propose_pair(state,qref,q,v,u,labels)
    before=digest(parameter_record(qref,state,observed=True))
    pq,pv=predict(state['observed_theta'],state['structure'],qref,q,v,u)
    expected={'phase':'identification','updated':True,'shared_transition_id':row['shared_transition_id'],
              'features_per_output':x,'preupdate_prediction':{'next_q_rad':pq,'next_v_rad_s':pv},
              'observed_next_v_rad_s':labels,'parameter_fingerprint_before':before,
              'vector_update_count':state['count']+1,'scalar_update_count':2*(state['count']+1),'committed_scalar_updates':2}
    checks.compare(item,expected,location+'/causality')
    checks.check(type(item.get('updated')) is bool and item['updated'] is True,'successful_atomic_pair_update',location)
    checks.check(len(item['output_records'])==2,'exact_two_output_proposals',location)
    for i,(theta,covariance,residual) in enumerate(proposals):
        checks.compare(item['output_records'][i],{'output_index':i,'features':x[i],
            'observed_next_v_rad_s':labels[i],'preupdate_error_rad_s':residual,
            'proposed_coefficients':theta,'proposed_covariance':covariance,'committed':True},location+f'/output{i}')
    state['theta']=[p[0] for p in proposals]
    state['covariance']=[p[1] for p in proposals]
    state['count']+=1
    state['observed_theta']=[r['proposed_coefficients'] for r in item['output_records']]
    state['observed_covariance']=[r['proposed_covariance'] for r in item['output_records']]
    checks.compare(item['parameter_fingerprint_after'],digest(parameter_record(qref,state,observed=True)),location+'/hash_chain')

def verify_snapshot(saved,state,qref,checks,location):
    checks.compare(saved,parameter_record(qref,state),location+'/parameters')
    checks.compare(saved,{'vector_update_count':state['count'],'scalar_update_count':2*state['count'],
                         'output_update_counts':[state['count']]*2},location+'/committed_counts')
    raw={key:saved[key] for key in parameter_record(qref,state)}
    checks.compare(saved['parameter_fingerprint'],digest(raw),location+'/raw_hash')
    state['observed_theta'],state['observed_covariance']=saved['coefficients'],saved['covariance']

def replay_mpc(theta,structure,qref,q,v,target,previous,limits):
    qref,q,v,target,previous=(pair(x) for x in (qref,q,v,target,previous))
    if len(limits)!=2 or any(len(row)!=2 or not all(finite(x) for x in row) or row[0]>=row[1] for row in limits):
        raise ValueError('Two ordered finite public joint ranges required.')
    if any(abs(u)>.5 for u in previous): raise ValueError('Previous command exceeds permission.')
    target_bounds=[(max(qref[i]-.15,limits[i][0]+.03),min(qref[i]+.15,limits[i][1]-.03)) for i in range(2)]
    if any(not target_bounds[i][0]<=target[i]<=target_bounds[i][1] for i in range(2)):
        raise ValueError('Current target must be local and inside each public limit margin.')
    bounds=[(max(qref[i]-.15,limits[i][0]-.03),min(qref[i]+.15,limits[i][1]+.03)) for i in range(2)]
    axis=[-.5+i*.125 for i in range(9)]
    feasible,records=[],[]
    attempts=successes=scalar_attempts=scalar_successes=0
    for torque in product(axis,repeat=2):
        pq,pv=list(q),list(v)
        qs,vs=[],[]
        costs=[.00002*(torque[i]-previous[i])**2 for i in range(2)]
        reason=None
        cp=cs=0
        for _ in range(15):
            attempts+=1;cp+=1
            try: pq,pv=predict(theta,structure,qref,pq,pv,list(torque))
            except PredictionError as exc:
                scalar_attempts+=exc.attempts;cs+=exc.attempts;scalar_successes+=exc.successes
                reason='prediction_error:PairPredictionError'
                break
            successes+=1;scalar_attempts+=2;scalar_successes+=2;cs+=2
            if any(not bounds[i][0]<=pq[i]<=bounds[i][1] for i in range(2)):
                reason='forecast_position_bounds';break
            if any(abs(z)>1.5 for z in pv): reason='forecast_velocity_bound';break
            qs.append(pq.copy());vs.append(pv.copy())
            for i in range(2): costs[i]+=(pq[i]-target[i])**2+.002*pv[i]**2+.00002*torque[i]**2
            if not all(finite(c) for c in costs) or not finite(sum(costs)): reason='nonfinite_cost';break
        else: feasible.append((sum(costs),sum(abs(u) for u in torque),*torque,qs,vs))
        ok=reason is None and len(qs)==15
        records.append({'torque':list(torque),'feasible':ok,'cost':sum(costs) if ok else None,
            'rejection_reason':reason,'completed_prediction_steps':len(qs),
            'pair_prediction_attempts':cp,'scalar_prediction_attempts':cs,'scalar_counts_complete':True})
    if feasible:
        cost,_,u0,u1,qs,vs=min(feasible);torque=[u0,u1]
    else: cost=None;torque=[0.,0.];qs=vs=[]
    return {'torque':torque,'feasible_candidates':len(feasible),'fallback':not feasible,'cost':cost,
        'predicted_q':qs,'predicted_v':vs,'pair_prediction_attempts':attempts,
        'pair_prediction_successes':successes,'scalar_prediction_attempts':scalar_attempts,
        'scalar_prediction_successes':scalar_successes,'failed_pair_prediction_attempts':attempts-successes,
        'scalar_counts_complete':True,'scalar_counts_is_lower_bound':False,'unknown_scalar_failure_count':0,
        'candidate_records':records}

def planner_spec(qref,ranges):
    axis=[-.5+i*.125 for i in range(9)]
    return {'config_per_axis':MPC_CONFIG,'qref_rad':list(qref),'joint_ranges_rad':[list(r) for r in ranges],
        'forecast_bounds_rad':[[max(qref[i]-.15,ranges[i][0]-.03),min(qref[i]+.15,ranges[i][1]+.03)] for i in range(2)],
        'target_bounds_rad':[[max(qref[i]-.15,ranges[i][0]+.03),min(qref[i]+.15,ranges[i][1]-.03)] for i in range(2)],
        'axis_candidates_nm':axis,'vector_candidate_count':81,'vector_candidates_nm':[list(u) for u in product(axis,repeat=2)],
        'action_rollout':'same constant two-axis vector over the full horizon; apply first command',
        'target_information':'current two-axis target only; no transition preview or future target input',
        'cost':'original scalar cost per axis, summed across axes; change at first step only',
        'tie_break':'exact cost, sum(abs(u)), signed u0, signed u1','fallback_nm':[0.,0.],
        'prediction_count_units':'one pair attempt calls up to two scalar velocity heads; failures explicitly counted','physical_queries':0}

def calibration_request(active,directions):
    if type(active) is not int or not 0<=active<400: raise ValueError('Calibration index in [0,400) required.')
    if not isinstance(directions,(tuple,list)) or len(directions)!=2 or any(type(s) is not int or s not in (-1,1) for s in directions):
        raise ValueError('Two fixed signed public directions required.')
    block,slot=divmod(active,20)
    sign=1 if slot<5 else -1 if 10<=slot<15 else 0
    shape=(1,0) if block<5 else (0,1) if block<10 else (1,1) if block<15 else (1,-1)
    amplitude=CAL_AMPLITUDES[block%5]
    return [directions[i]*shape[i]*sign*amplitude for i in range(2)]

def prediction_request(kind,active,directions):
    if kind not in ('prediction_low','prediction_full') or type(active) is not int or not 0<=active<100:
        raise ValueError('Declared prediction kind/index required.')
    block,slot=divmod(active,20)
    sign=1 if slot<5 else -1 if 10<=slot<15 else 0
    amplitude=PRED_AMPLITUDES[kind.split('_')[1]][block]
    return [directions[i]*PRED_DIRECTIONS[block][i]*sign*amplitude for i in range(2)]

def study_condition(qref,q,v,phase):
    qref,q,v=(pair(x) for x in (qref,q,v))
    position=[phase!='prefix' and abs(q[i]-qref[i])>=.12 for i in range(2)]
    velocity=[phase!='prefix' and abs(v[i])>=1. for i in range(2)]
    return {'triggered':any(position+velocity),'position_triggered':position,'velocity_triggered':velocity}

def duration(kind,control_steps=200):
    if kind not in KINDS: raise ValueError('Declared pair trial kind required.')
    return 400 if kind=='calibration' else 100 if kind.startswith('prediction_') else control_steps

def planned_matrix(spec=PAIR_DEVELOPMENT_SPEC):
    return [{'trial_id':f'seed{seed}_{kind}','seed':seed,'kind':kind,'maximum_control_steps':spec.prefix_steps+
        (spec.calibration_steps if kind=='calibration' else spec.prediction_steps if kind.startswith('prediction_') else spec.control_steps)}
            for seed in spec.seeds for kind in KINDS]

def complete(ev):
    return (ev.get('eligible') is True and ev.get('completed') is True and ev.get('status')=='completed'
        and ev.get('study_aborted') is False and ev.get('environment_terminated') is False)

def complete_trials(seeds,kinds,spec):
    return (len(seeds)==3 and all(type(row.get('seed')) is int for row in seeds)
        and {row['seed'] for row in seeds}==set(spec.seeds)
        and all(all(complete(row.get('evaluations',{}).get(k,{})) for k in kinds) for row in seeds))

def improvement(new,old): return None if old==0 else 1.-new/old

def model_gate(seeds,name,spec):
    kinds=('calibration','prediction_low','prediction_full','nominal_mpc',name+'_mpc')
    eligible=complete_trials(seeds,kinds,spec)
    rows=[]
    for sr in seeds:
        ev=sr.get('evaluations',{})
        nm,learned=ev.get('nominal_mpc',{}),ev.get(name+'_mpc',{})
        a,b=nm.get('tracking_rmse_rad'),learned.get('tracking_rmse_rad')
        axis_a,axis_b=nm.get('tracking_rmse_by_axis_rad'),learned.get('tracking_rmse_by_axis_rad')
        valid=eligible and all(finite(x) and x>=0 for x in (a,b))
        preds={}
        for kind in ('prediction_low','prediction_full'):
            metrics=ev.get(kind,{}).get('velocity_prediction_rmse',{})
            na,lb=metrics.get('nominal'),metrics.get(name)
            available=(isinstance(na,list) and isinstance(lb,list) and len(na)==len(lb)==2
                and all(finite(x) and x>=0 for x in na+lb))
            preds[kind]={'available':available,'nominal_rmse':na,'candidate_rmse':lb,
                'passed':available and all(lb[i]<=.8*na[i] for i in range(2))}
            valid=valid and available
        valid=valid and isinstance(axis_a,list) and isinstance(axis_b,list) and len(axis_a)==len(axis_b)==2 and all(finite(x) and x>=0 for x in axis_a+axis_b)
        rows.append({'seed':sr['seed'],'eligible':bool(valid),'nominal_tracking':a,'candidate_tracking':b,
            'nominal_axis_tracking':axis_a,'candidate_axis_tracking':axis_b,'prediction_gates':preds,
            'strict_joint_tracking':valid and b<a,
            'strict_axis_tracking':[valid and axis_b[i]<axis_a[i] for i in range(2)]})
    evaluated=eligible and all(r['eligible'] for r in rows)
    na=sum(r['nominal_tracking'] for r in rows)/3 if evaluated else None
    lb=sum(r['candidate_tracking'] for r in rows)/3 if evaluated else None
    axis_gates=[]
    for i in range(2):
        aa=sum(r['nominal_axis_tracking'][i] for r in rows)/3 if evaluated else None
        bb=sum(r['candidate_axis_tracking'][i] for r in rows)/3 if evaluated else None
        imp=improvement(bb,aa) if evaluated else None
        axis_gates.append({'axis':i,'mean_improvement':imp,'passed':evaluated and imp is not None and imp>=.20 and all(r['strict_axis_tracking'][i] for r in rows)})
    imp=improvement(lb,na) if evaluated else None
    passed=(evaluated and imp is not None and imp>=.20 and all(r['strict_joint_tracking'] and all(p['passed'] for p in r['prediction_gates'].values()) for r in rows)
            and (not spec.tracking_per_axis or all(g['passed'] for g in axis_gates)))
    return {'evaluated':evaluated,'passed':bool(passed),'all_five_required_trials_complete':eligible,
        'per_seed':rows,'tracking_mean_improvement':imp,'tracking_per_axis_required':spec.tracking_per_axis,'axis_tracking_gates':axis_gates}

def comparison_gate(seeds,baseline,candidate,spec,*,require_predictions=False):
    kinds=('calibration','prediction_low','prediction_full','nominal_mpc','diagonal_mpc','coupled_mpc') if baseline=='diagonal_mpc' else ('calibration','prediction_low','prediction_full','nominal_mpc',candidate,baseline)
    eligible=complete_trials(seeds,kinds,spec)
    rows=[]
    for sr in seeds:
        ev=sr.get('evaluations',{})
        a,b=ev.get(baseline,{}),ev.get(candidate,{})
        ar,br=a.get('tracking_rmse_rad'),b.get('tracking_rmse_rad')
        valid=eligible and all(finite(v) and v>=0 for v in (ar,br))
        axis_a,axis_b=a.get('tracking_rmse_by_axis_rad'),b.get('tracking_rmse_by_axis_rad')
        axis_available=(isinstance(axis_a,list) and isinstance(axis_b,list) and len(axis_a)==len(axis_b)==2
            and all(finite(v) and v>=0 for v in axis_a+axis_b))
        valid=valid and axis_available
        efforts={}
        for key in EFFORT_KEYS[2:]:
            av,bv=a.get('control_effort',{}).get(key),b.get('control_effort',{}).get(key)
            valid=valid and a.get('actual_effort_complete') is True and b.get('actual_effort_complete') is True
            available=isinstance(av,list) and isinstance(bv,list) and len(av)==len(bv)==2 and all(finite(v) and v>=0 for v in av+bv)
            valid=valid and available
            efforts[key]={'baseline':sum(av) if available else None,'candidate':sum(bv) if available else None}
        prediction_ok=True
        if require_predictions:
            axis_a,axis_b=a.get('tracking_rmse_by_axis_rad'),b.get('tracking_rmse_by_axis_rad')
            prediction_ok=(isinstance(axis_a,list) and isinstance(axis_b,list)
                and len(axis_a)==len(axis_b)==2 and all(finite(v) and v>=0 for v in axis_a+axis_b)
                and all(axis_b[i]<=axis_a[i] for i in range(2)))
            for kind in ('prediction_low','prediction_full'):
                vals=ev.get(kind,{}).get('velocity_prediction_rmse',{})
                da,cb=vals.get('diagonal'),vals.get('coupled')
                prediction_ok=prediction_ok and isinstance(da,list) and isinstance(cb,list) and len(da)==len(cb)==2 and all(finite(v) and v>=0 for v in da+cb) and all(cb[i]<=da[i] for i in range(2))
        rows.append({'seed':sr['seed'],'eligible':bool(valid),'baseline_tracking':ar,'candidate_tracking':br,
            'tracking_non_worse':valid and br<=ar,'axis_tracking_non_worse':valid and all(axis_b[i]<=axis_a[i] for i in range(2)),
            'predictions_non_worse':bool(prediction_ok),'efforts':efforts})
    evaluated=eligible and all(r['eligible'] for r in rows)
    a=sum(r['baseline_tracking'] for r in rows)/3 if evaluated else None
    b=sum(r['candidate_tracking'] for r in rows)/3 if evaluated else None
    imp=improvement(b,a) if evaluated else None
    effort_gates={key:{'passed':evaluated and sum(r['efforts'][key]['candidate'] for r in rows)<=1.05*sum(r['efforts'][key]['baseline'] for r in rows)} for key in EFFORT_KEYS[2:]}
    passed=evaluated and imp is not None and imp>=.05 and all(r['tracking_non_worse'] and r['axis_tracking_non_worse']
        and r['predictions_non_worse'] for r in rows) and all(e['passed'] for e in effort_gates.values())
    return {'evaluated':evaluated,'passed':bool(passed),'required_trials_complete':eligible,'per_seed':rows,
            'tracking_mean_improvement':imp,'effort_gates':effort_gates}

def scientific_gates(seeds,spec=PAIR_DEVELOPMENT_SPEC):
    diagonal,coupled=model_gate(seeds,'diagonal',spec),model_gate(seeds,'coupled',spec)
    increment=comparison_gate(seeds,'diagonal_mpc','coupled_mpc',spec,require_predictions=True)
    increment['passed']=increment['passed'] and coupled['passed']
    combined={name:comparison_gate(seeds,'combined_pd',name+'_mpc',spec) for name in ('diagonal','coupled')}
    for name,contribution in (('diagonal',diagonal),('coupled',coupled)):
        combined[name]['model_contribution_passed']=contribution['passed']
        combined[name]['passed']=combined[name]['passed'] and contribution['passed']
    return {'diagonal_contribution':diagonal,'coupled_contribution':coupled,'coupled_increment':increment,
        'combined_pd_comparison':combined,
        'complete_matrix':complete_trials(seeds,KINDS,spec),'thresholds_frozen':spec.scientific_gates_frozen,
        'claim_boundary':'Development recipe transfer and specified local two-joint model contribution only; combined single-axis PD is not a tuned pair strong baseline; no holdout, unknown dynamics, safety, locomotion or real-robot claim.'}


def verify_transition(row, previous, counters, ranges, checks, location):
    """Validate native fields and every saved physical-substep diagnostic."""
    before, after = row["observation_before"], row["observation_after"]
    for obs in (before, after):
        checks.check(set(obs) == set(NATIVE), "native_observation_whitelist", location)
        for key, width in NATIVE.items():
            vector(obs[key], width)
    checks.check(previous is None or previous == before, "native_continuity", location)
    qpos, qvel = vector(row["qpos"], 15), vector(row["qvel"], 14)
    checks.check(after["joint_position"] == qpos[7:] and after["joint_velocity"] == qvel[6:], "native_encoder_mapping", location)
    request = vector(row["requested_torque"], 8)
    checks.check(all(abs(u) <= .5 for u in request[:2]) and all(u == 0. for u in request[2:]), "shared_permission_other_joints_zero", location)
    diagnostic, index = row["diagnostics"], row["step_index"]
    n = diagnostic["executed_substeps"]
    checks.check(type(diagnostic.get("terminated")) is bool, "boolean_environment_stop", location)
    checks.check(type(n) is int and 0 <= n <= 10 and (n == 10 or diagnostic["terminated"]), "legal_partial_substeps", location)
    counters["physics"] += n
    checks.compare(diagnostic["step_id"], index+1, location+"/step_counter")
    checks.compare(diagnostic["physics_steps"], counters["physics"], location+"/physics_counter")
    checks.compare(diagnostic["time"], counters["physics"]*PHYSICS_DT, location+"/physical_time")
    checks.compare(diagnostic["requested_torque"], request, location+"/diagnostic_request")
    checks.compare(diagnostic["accepted_torque"], request, location+"/accepted_request")
    history = diagnostic["applied_torque_history"]
    checks.check(len(history) == n, "returned_torque_substeps", location)
    guarded = 0
    for actual in history:
        vector(actual, 8)
        checks.check(all(a in (0., u) for a, u in zip(actual, request)), "shield_preserves_or_zeroes", location)
        guarded += any(a != u for a, u in zip(actual, request))
    checks.check(type(diagnostic["guarded_substeps"]) is int and guarded <= diagnostic["guarded_substeps"] <= n, "guarded_substep_bounds", location)
    if history:
        checks.compare(diagnostic["applied_torque"], history[-1], location+"/last_applied")
        # A stop zeros actuator control after the final integration; its native
        # actuator_force is still the last physically realized torque.
        checks.compare(after["actuator_torque"], history[-1], location+"/native_actuator")
    checks.compare(after["previous_command"], request, location+"/known_command")
    for name in ("substep_ground_normal_forces", "substep_kinetic_energies", "substep_minimum_contact_distances"):
        vector(diagnostic[name], n)
    checks.check(all(x >= 0 for x in diagnostic["substep_ground_normal_forces"]+diagnostic["substep_kinetic_energies"]),
                 "nonnegative_force_energy", location)
    checks.compare(diagnostic["peak_substep_ground_normal_force"], max(diagnostic["substep_ground_normal_forces"], default=0.), location+"/force_peak")
    checks.compare(diagnostic["ground_normal_impulse_ns"], sum(diagnostic["substep_ground_normal_forces"])*PHYSICS_DT, location+"/force_impulse")
    checks.compare(diagnostic["peak_substep_kinetic_energy"], max(diagnostic["substep_kinetic_energies"], default=0.), location+"/energy_peak")
    checks.compare(diagnostic["minimum_substep_contact_distance"], min(diagnostic["substep_minimum_contact_distances"], default=0.), location+"/contact_distance")
    return n

def verify_study(row,qref,checks,location):
    q,v=[row['observation_after'][k][:2] for k in ('joint_position','joint_velocity')]
    condition=study_condition(qref,q,v,row['phase'])
    expected=None
    if condition['triggered']:
        triggers=[]
        for i in range(2):
            if condition['position_triggered'][i]: triggers.append({'joint_index':i,'signal':'absolute_q_minus_qref_rad'})
            if condition['velocity_triggered'][i]: triggers.append({'joint_index':i,'signal':'absolute_velocity_rad_s'})
        expected={'type':'StudyAbort','triggers':triggers,'q_rad':q,'qref_rad':list(qref),'velocity_rad_s':v,
            'thresholds':{'absolute_q_minus_qref_rad':.12,'absolute_velocity_rad_s':1.},'feedback_action':None,
            'phase':row['phase'],'step_index':row['step_index']}
    checks.compare(row.get('study_abort'),expected,location+'/study')
    return condition['triggered']

def new_effort(): return {key:[0.,0.] for key in EFFORT_KEYS}

def add_effort(effort,row):
    n=row['diagnostics']['executed_substeps']
    for i,u in enumerate(row['requested_torque'][:2]):
        effort['requested_absolute_nm_s'][i]+=abs(u)*n*PHYSICS_DT
        effort['requested_squared_nm2_s'][i]+=u*u*n*PHYSICS_DT
        effort['actual_absolute_nm_s'][i]+=sum(abs(a[i]) for a in row['diagnostics']['applied_torque_history'])*PHYSICS_DT
        effort['actual_squared_nm2_s'][i]+=sum(a[i]**2 for a in row['diagnostics']['applied_torque_history'])*PHYSICS_DT

def reconcile_effort(ev,phase,observed,paid,raw,exceptions,checks,location):
    missing=paid-raw
    commands=[r.get('requested_torque') for r in exceptions if r.get('phase')==phase]
    recoverable=missing==0 or (0<missing<=10 and len(commands)==1 and isinstance(commands[0],list)
        and len(commands[0])==8 and all(finite(u) and abs(u)<=.5 for u in commands[0]) and all(u==0. for u in commands[0][2:]))
    known={key:values.copy() for key,values in observed.items()}
    if missing>0 and recoverable:
        for i,u in enumerate(commands[0][:2]):
            known[EFFORT_KEYS[0]][i]+=abs(u)*missing*PHYSICS_DT
            known[EFFORT_KEYS[1]][i]+=u*u*missing*PHYSICS_DT
    measured=ev['phase_actual_effort_substeps'][phase]
    checks.check(type(measured) is int and raw<=measured<=paid,'actual_effort_measured_bounds',location)
    checks.compare(ev['phase_actual_effort_complete'][phase],measured==paid,location+'/complete')
    checks.compare(ev['phase_missing_actual_effort_substeps'][phase],paid-measured,location+'/missing')
    for key,values in ev['phase_effort'][phase].items():
        pair(values)
        checks.check(all(z>=0 for z in values),'nonnegative_pair_effort',location+'/'+key)
        if key in EFFORT_KEYS[:2] and recoverable:
            checks.compare(values,known[key],location+'/'+key)
        elif key in EFFORT_KEYS[2:]:
            maximum=.5 if key==EFFORT_KEYS[2] else .25
            if missing==0: checks.compare(values,known[key],location+'/'+key)
            else:
                checks.check(all(known[key][i]-1e-10<=values[i]<=known[key][i]+maximum*(measured-raw)*PHYSICS_DT+1e-10 for i in range(2)),
                             'missing_actual_effort_within_per_axis_permission',location+'/'+key)
        checks.compare(ev['phase_effort_combined'][phase][key],sum(values),location+'/sum/'+key)
    return {'independent_lower_bound':known,'paid_substeps':paid,'stored_substeps':raw,
        'requested_reconstruction_complete':recoverable,'actual_reconstruction_complete':missing==0,
        'unreconstructed_actual_substeps':missing,'collector_measured_substeps':measured}

def paired_rmse(values):
    if not values: return None
    return {'joint':rmse([x for row in values for x in row]),
            'per_axis':[rmse([row[i] for row in values]) for i in range(2)],'complete_endpoints':len(values)}

def planned_tail_metrics(rows,qref,directions):
    result=[]
    indexed={r['step_index']:r for r in rows if 'collector_exception' not in r}
    for low,high in ((100,199),(200,299)):
        target=[qref[i]+directions[i]*(.04 if low==100 else .08) for i in range(2)]
        for label,a,b in (('segment',low,high),('planned_tail',high-19,high)):
            returned=[indexed[j] for j in range(a,b+1) if j in indexed]
            full=[r for r in returned if r['diagnostics']['executed_substeps']==10]
            errors=[[r['observation_after']['joint_position'][i]-target[i] for i in range(2)] for r in full]
            result.append({'label':label,'active_interval':[a-100,b-100],'planned_endpoints':b-a+1,
                'returned_endpoints':len(returned),'complete_endpoints':len(full),'partial_endpoints':len(returned)-len(full),
                'missing_endpoints':b-a+1-len(returned),'tracking_rmse':paired_rmse(errors),
                'signed_error_mean_by_axis_rad':[sum(row[i] for row in errors)/len(errors) if errors else None for i in range(2)],
                'maximum_absolute_error_by_axis_rad':[max((abs(row[i]) for row in errors),default=None) for i in range(2)],
                'any_terminal':any(r.get('study_abort') is not None or r['diagnostics']['terminated'] for r in returned),
                'complete_window':len(full)==b-a+1 and not any(r.get('study_abort') is not None or r['diagnostics']['terminated'] for r in returned)})
    return result

def conditional_rollouts(rows,states,qref,horizons=(2,5,15),*,prefix_steps=100):
    regular={r['step_index']:r for r in rows if 'collector_exception' not in r}
    result={}
    starts=sorted(i for i in regular if i>=prefix_steps)
    for name,state in [*states.items(),('persistence',None)]:
        output={}
        for horizon in horizons:
            endpoint_q,endpoint_v,path_q,path_v=[],[],[],[]
            excluded=Counter();terminal=0
            for start in starts:
                window=[regular.get(i) for i in range(start,start+horizon)]
                if any(r is None for r in window): excluded['missing_endpoint']+=1;continue
                if any(r['diagnostics']['executed_substeps']!=10 for r in window): excluded['partial_interval']+=1;continue
                if any(r.get('study_abort') is not None or r['diagnostics']['terminated'] for r in window[:-1]):
                    excluded['crosses_terminal']+=1;continue
                q,v=[window[0]['observation_before'][k][:2] for k in ('joint_position','joint_velocity')]
                paths=[]
                try:
                    for row in window:
                        u=row['requested_torque'][:2]
                        if state is None: q=[q[i]+DT*v[i] for i in range(2)]
                        else: q,v=predict(state['observed_theta'],state['structure'],qref,q,v,u)
                        if not all(finite(x) for x in q+v): raise ValueError('Nonfinite rollout.')
                        paths.append((q.copy(),v.copy()))
                except ValueError: excluded['nonfinite_rollout']+=1;continue
                eq=[];ev=[]
                for row,(pq,pv) in zip(window,paths):
                    eq.append([row['observation_after']['joint_position'][i]-pq[i] for i in range(2)])
                    ev.append([row['observation_after']['joint_velocity'][i]-pv[i] for i in range(2)])
                endpoint_q.append(eq[-1]);endpoint_v.append(ev[-1]);path_q.extend(eq);path_v.extend(ev)
                terminal+=window[-1].get('study_abort') is not None or window[-1]['diagnostics']['terminated']
            output[str(horizon)]={'available_starts':len(starts),'valid_windows':len(endpoint_q),'excluded_windows':sum(excluded.values()),
                'exclusion_reasons':dict(excluded),'windows_ending_in_terminal':terminal,'endpoint_q_rmse':paired_rmse(endpoint_q),
                'endpoint_v_rmse':paired_rmse(endpoint_v),'path_q_rmse':paired_rmse(path_q),'path_v_rmse':paired_rmse(path_v)}
        result[name]=output
    return {'models':result,'horizons':list(horizons),'recorded_future_requests_are_offline_labels':True,
        'online_future_information':False,'rule':'Free recursive prediction from one current native endpoint; no future true-state feedback.'}

def state_coverage(calibration_rows,rows,qref):
    return {str(i):common.state_coverage(calibration_rows,rows,qref[i],joint_index=i) for i in range(2)}

def require_pair(path,spec=PAIR_DEVELOPMENT_SPEC):
    if type(spec) is not PairAuditSpec: raise ValueError('Trusted immutable PairAuditSpec required.')
    metadata=load_json(Path(path)/'metadata.json')
    expected={'suite':spec.suite,'pose':spec.pose,'joint_indices':list(spec.joint_indices),'seeds':list(spec.seeds),
              'split':spec.split,'pd_gains':{'kp':[64.,64.],'kd':[0.,1.]}}
    if (any(metadata.get(k)!=v for k,v in expected.items())
        or any(type(i) is not int for i in metadata.get('joint_indices',[])+metadata.get('seeds',[]))
        or any(not finite(x) for key in ('kp','kd') for x in metadata.get('pd_gains',{}).get(key,[]))
        or metadata.get('synthetic') is not spec.synthetic_fixture or metadata.get('native_joint_count')!=8
        or not isinstance(metadata.get('protocol'),dict) or metadata['protocol'].get('path')!=spec.protocol):
        raise ValueError('Only native declared real pair scope, seeds, gains and exact protocol accepted before ZIP/trace reads.')
    return metadata

def verify_exception_updates(exception,ep,regular,states,qref,checks,location,*,prefix_steps=100):
    snapshots=exception.get('partial_model_snapshots',{})
    if not snapshots: return
    checks.check(set(snapshots)=={'diagonal','coupled'},'exception_exact_model_set',location)
    already=any(r['shared_transition_id']==exception['shared_transition_id'] for r in regular)
    returned=exception.get('returned_step_diagnostics')
    full=(not already and type(exception.get('step_index')) is int
        and exception['step_index']==len(regular) and exception['step_index']>=prefix_steps
        and returned is not None and returned.get('executed_substeps')==10
        and returned.get('step_id')==ep['control_steps']
        and ep['control_steps']==len(regular)+1
        and ep['physics_steps']-sum(r['diagnostics']['executed_substeps'] for r in regular)==10)
    accounting=exception.get('failure_accounting',{})
    shared=accounting.get('shared_pair_update_accounting') or accounting.get('structured_failure') or {}
    completed=shared.get('completed_model_records',{})
    if 'snapshots_after_attempt' in shared:
        checks.compare(shared['snapshots_after_attempt'],snapshots,location+'/shared_snapshot_binding')
        checks.compare(shared['shared_transition_id'],exception['shared_transition_id'],location+'/shared_id')
        checks.check(shared.get('failed_model') in ('diagonal','coupled'),'known_failed_model',location)
    updated=exception.get('model_update') or {}
    original_counts={name:state['count'] for name,state in states.items()}
    original_parameters={name:{'structure':state['structure'],'theta':[row.copy() for row in state['theta']],
        'covariance':[[row.copy() for row in matrix] for matrix in state['covariance']]} for name,state in states.items()}
    for name in ('diagonal','coupled'):
        if name not in snapshots or name not in states: continue
        state,snapshot=states[name],snapshots[name]
        count=snapshot.get('vector_update_count')
        checks.check(type(count) is int and count-state['count'] in (0,1),'exception_single_atomic_count_delta',location+'/'+name)
        item=completed.get(name) or (updated.get(name) if isinstance(updated,dict) else None)
        if count==state['count']+1:
            checks.check(full,'committed_exception_requires_full_returned_native_transition',location+'/'+name)
            if full:
                replay=dict(exception,diagnostics=returned)
                if item is not None: replay_update(item,replay,state,qref,checks,location+'/'+name)
                else:
                    q,v=[exception['observation_before'][k][:2] for k in ('joint_position','joint_velocity')]
                    x,proposals=propose_pair(state,qref,q,v,exception['requested_torque'][:2],exception['observation_after']['joint_velocity'][:2])
                    state['theta']=[p[0] for p in proposals];state['covariance']=[p[1] for p in proposals];state['count']+=1
        elif count==state['count'] and item is not None and item.get('updated') is True:
            checks.check(already,'duplicate_update_requires_saved_regular_transition',location+'/'+name)
            if already:
                original=next(r for r in regular if r['shared_transition_id']==exception['shared_transition_id'])
                checks.compare(item,original['model_update'][name],location+'/'+name+'/duplicate_record')
        verify_snapshot(snapshot,state,qref,checks,location+'/'+name+'/final_snapshot')
    failure=shared.get('failure_record') or accounting.get('pair_update_accounting')
    failed_model=shared.get('failed_model')
    if isinstance(failure,dict) and failed_model in states and 'committed_scalar_updates' in failure:
        committed=failure['committed_scalar_updates']
        checks.check(type(committed) is int and committed in (0,2),'failure_model_atomic_committed_heads',location)
        checks.compare(committed,2*(snapshots[failed_model]['vector_update_count']-original_counts[failed_model]),location+'/failure_committed_from_final_state')
        checks.compare(failure.get('snapshot_after_attempt'),snapshots[failed_model],location+'/failed_model_snapshot')
        proposals=failure.get('proposed_outputs',[])
        checks.check(isinstance(proposals,list) and len(proposals)<=2,'failure_proposal_count',location)
        checks.check(committed==0 or len(proposals)==2,'committed_failure_has_two_proposals',location)
        for i,proposal in enumerate(proposals):
            checks.compare(proposal.get('output_index'),i,location+'/proposal_index')
            checks.compare(proposal.get('committed'),committed==2,location+'/proposal_committed')
            if full:
                q,v=[exception['observation_before'][k][:2] for k in ('joint_position','joint_velocity')]
                inputs,expected_proposals=propose_pair(original_parameters[failed_model],qref,q,v,
                    exception['requested_torque'][:2],exception['observation_after']['joint_velocity'][:2])
                theta,covariance,residual=expected_proposals[i]
                checks.compare(proposal,{'features':inputs[i],'observed_next_v_rad_s':exception['observation_after']['joint_velocity'][i],
                    'preupdate_error_rad_s':residual,'proposed_coefficients':theta,'proposed_covariance':covariance},location+'/failure_proposal'+str(i))

def audit_archive(path,checks,git_root=ROOT,spec=PAIR_DEVELOPMENT_SPEC):
    path=Path(path).resolve()
    prefix_steps=spec.prefix_steps
    def trial_duration(kind): return spec.calibration_steps if kind=='calibration' else spec.prediction_steps if kind.startswith('prediction_') else spec.control_steps
    metadata=require_pair(path,spec)
    ranges,input_hashes=common.verify_sources(path,metadata,checks,git_root,required=spec.required_sources)
    checks.compare(metadata['protocol'],{'path':spec.protocol,'sha256':metadata['source_sha256'][spec.protocol]},'protocol_byte_binding')
    checks.compare(metadata['environment_config'],ENVIRONMENT,'shared_environment')
    checks.compare(metadata,{'prefix_steps':prefix_steps,'calibration_steps':spec.calibration_steps,'prediction_steps':spec.prediction_steps,'control_steps_per_trial':spec.control_steps,
        'structures':['diagonal_hinge5','coupled_hinge9'],'integration':'endpoint_euler',
        'update_order':['diagonal','coupled'],'gpu':None,'teacher_calls':0,'external_demonstration_samples':0,
        'policy_parameter_updates':0,'gain_updates':0,'planned_episode_count':8*len(spec.seeds),
        'maximum_control_steps':(8*prefix_steps+spec.calibration_steps+2*spec.prediction_steps+5*spec.control_steps)*len(spec.seeds),
        'maximum_scalar_updates':4*spec.calibration_steps*len(spec.seeds),'native_joint_count':8},'frozen_metadata')
    checks.compare(metadata['backend'],'synthetic, no physics' if spec.synthetic_fixture else 'MuJoCo CPU','cpu_backend')
    checks.compare(metadata['calibration_block_amplitudes_nm'],list(CAL_AMPLITUDES),'calibration_doses')
    checks.compare(metadata['prediction_block_amplitudes_nm'],{k:list(v) for k,v in PRED_AMPLITUDES.items()},'prediction_doses')
    checks.compare(metadata['prediction_block_shapes'],[list(x) for x in PRED_DIRECTIONS],'prediction_shapes')
    checks.compare(metadata['pd_boundary'],'combination of separately tuned single-axis gains; not a tuned two-axis strong baseline','combined_pd_boundary')
    checks.compare(metadata['update_cost_unit'],'committed scalar next-velocity heads','committed_update_unit')
    checks.compare(metadata['calibration_schedule'],'20 blocks of 20: five shoulder, five elbow, five same-direction, five opposite; 5+/5zero/5-/5zero','frozen_5pulse_schedule')
    plans=planned_matrix(spec)
    checks.compare(metadata['planned_episodes'],plans,'complete_fixed_plan')
    episodes=load_json(path/'episodes.json');seed_results=load_json(path/'seed_results.json')
    checks.compare([ep['trial_id'] for ep in episodes],[p['trial_id'] for p in plans],'exact_outcome_ledger')
    epmap={ep['trial_id']:ep for ep in episodes}
    checks.check(len(epmap)==len(episodes),'unique_trial_ids')
    status=metadata.get('archive_status')
    checks.check(status in ('complete','failed','interrupted'),'final_archive_status')
    checks.compare(metadata.get('complete'),status=='complete','complete_archive_flag')
    checks.check(status!='complete' or not any(ep.get('reason',{}).get('type')=='ArchiveAborted' for ep in episodes if isinstance(ep.get('reason'),dict)),
                 'complete_archive_has_no_fatal_unexecuted_trials')
    if status in ('failed','interrupted'):
        checks.check(isinstance(metadata.get('collector_exception'),dict),'failed_archive_retains_exception')
    fatal_positions=[i for i,ep in enumerate(episodes) if ep.get('trace_write_failure') is not None
        or (ep.get('collector_exception') or {}).get('type') in ('KeyboardInterrupt','SystemExit','OSError')]
    if fatal_positions:
        checks.check(status in ('failed','interrupted'),'fatal_archive_not_complete')
        for ep in episodes[min(fatal_positions)+1:]:
            checks.check(ep['status']=='blocked' and ep.get('reason',{}).get('type')=='ArchiveAborted','fatal_future_trials_blocked',ep['trial_id'])
    by_seed={sr['seed']:sr for sr in seed_results}
    checks.check(len(by_seed)==len(seed_results) and set(by_seed).issubset(spec.seeds)
        and all(type(sr['seed']) is int for sr in seed_results),'unique_known_seed_snapshots')
    grouped={};trace_order=[]
    with gzip.open(path/'trace.jsonl.gz','rt',encoding='utf-8') as stream:
        for line in stream:
            row=json.loads(line);tid=row['trial_id']
            checks.check(tid in epmap,'known_trace_trial',tid)
            if not trace_order or trace_order[-1]!=tid: trace_order.append(tid)
            grouped.setdefault(tid,[]).append(row)
    checks.compare(trace_order,[p['trial_id'] for p in plans if p['trial_id'] in grouped],'trace_fixed_trial_order')
    derived=[];total_scalar=total_vector=0
    for seed in spec.seeds:
        sr=by_seed.get(seed)
        if sr is None:
            checks.check(all(epmap[f'seed{seed}_{kind}']['status']=='blocked' for kind in KINDS),'unstarted_seed_all_blocked',seed)
            derived.append({'seed':seed,'evaluations':{}});continue
        checks.compare(sr['reset_seed'],spec.reset_seeds[seed],f'seed{seed}/reset_seed')
        qref=sr.get('reference_q');directions=sr.get('direction')
        states={};prefix_reference=None;calibrated=False;seed_derived={}
        if qref is not None:
            pair(qref)
            checks.check(isinstance(directions,list) and len(directions)==2 and all(type(s) is int and s in (-1,1) for s in directions),'signed_native_directions',seed)
            for i in range(2):
                positive,negative=ranges[i][1]-qref[i],qref[i]-ranges[i][0]
                expected=1 if positive>=negative else -1
                checks.compare(directions[i],expected,f'seed{seed}/direction{i}')
                checks.compare(sr['selection_records'][i],{'joint_index':i,'joint_position_rad':qref[i],
                    'lower_limit_rad':ranges[i][0],'upper_limit_rad':ranges[i][1],'positive_room_rad':positive,
                    'negative_room_rad':negative,'direction':expected,'rule':'larger distance to the public joint limit; ties choose positive'},f'seed{seed}/selection{i}')
        for kind in KINDS:
            tid=f'seed{seed}_{kind}';ep=epmap[tid];ev=sr['evaluations'].get(kind,{})
            trial_start_failures=checks.failed
            rows=grouped.get(tid,[])
            regular=[r for r in rows if 'collector_exception' not in r]
            exceptions=[r for r in rows if 'collector_exception' in r]
            checks.compare(ep,next(p for p in plans if p['trial_id']==tid),tid+'/plan')
            checks.check(ep['status'] in ('completed','terminated','exception','blocked','incomplete'),'known_outcome',tid)
            checks.check(len(exceptions)<=1 and (not exceptions or rows[-1] is exceptions[-1] and ep['status']=='exception'),'single_final_exception',tid)
            dependent=kind.startswith('prediction_') or kind in ('diagonal_mpc','coupled_mpc')
            checks.check(ep['status']=='blocked' or not dependent or calibrated,'calibration_dependencies',tid)
            if ep['status']=='blocked':
                checks.check(not rows and all(type(ep[k]) is int and ep[k]==0 for k in ('control_calls_attempted','control_steps','physics_steps')),'blocked_zero_physical_cost',tid)
                checks.check(all(type(ep['phase_budgets'][phase][key]) is int and ep['phase_budgets'][phase][key]==0
                    for phase in PHASES for key in ('control_calls_attempted','control_steps','physics_steps')),'blocked_zero_phase_costs',tid)
                if ep.get('reason',{}).get('type')=='DependencyBlocked':
                    checks.check(dependent and not calibrated,'genuine_dependency_failure',tid)
                    checks.compare(ep['reason']['dependencies'],[f'seed{seed}_calibration'],tid+'/dependencies')
                seed_derived[kind]={'eligible':False,'completed':False,'status':'blocked','study_aborted':False,'environment_terminated':False}
                continue
            caps={'prefix':prefix_steps,'calibration':spec.calibration_steps if kind=='calibration' else 0,
                  'prediction':spec.prediction_steps if kind.startswith('prediction_') else 0,'control':spec.control_steps if kind in CONTROL_KINDS else 0}
            for phase,cap in caps.items():
                b=ep['phase_budgets'][phase]
                checks.check(all(type(b[k]) is int and 0<=b[k]<=cap for k in ('control_calls_attempted','control_steps'))
                    and type(b['physics_steps']) is int and 0<=b['physics_steps']<=cap*10,'phase_cost_cap',tid+'/'+phase)
            checks.check(all(type(ep[k]) is int and 0<=ep[k]<=prefix_steps+trial_duration(kind) for k in ('control_calls_attempted','control_steps'))
                and type(ep['physics_steps']) is int and 0<=ep['physics_steps']<=10*(prefix_steps+trial_duration(kind)),'trial_cost_cap',tid)
            checks.compare([r['step_index'] for r in regular],list(range(len(regular))),tid+'/contiguous_saved_indices')
            prefix=[common.trace_payload(r) for r in regular if r['step_index']<prefix_steps]
            if len(prefix)==prefix_steps:
                checks.compare(regular[prefix_steps-1]['observation_after']['joint_position'][:2],qref,tid+'/paid_prefix_reference')
                if prefix_reference is None: prefix_reference=prefix
                else: checks.check(prefix==prefix_reference,'exact_native_paid_prefix_all_trials',tid)
            counters={'physics':0};previous=None;previous_u=[0.,0.]
            phase_rows={p:0 for p in PHASES};phase_physics={p:0 for p in PHASES}
            effort={p:new_effort() for p in PHASES};risk={p:common.new_risk() for p in ('full',*PHASES)}
            errors={};tracking=[];partial_errors=[];planning={k:0 for k in PLANNING_KEYS}
            fallback=0;saturation=[0,0];study_seen=False;environment_seen=False
            for row in regular:
                index=row['step_index'];location=tid+':'+str(index)
                phase='prefix' if index<prefix_steps else 'calibration' if kind=='calibration' else 'prediction' if kind.startswith('prediction_') else 'control'
                checks.compare(row,{'trial_id':tid,'seed':seed,'kind':kind,'joint_indices':[0,1],
                    'phase':phase,'shared_transition_id':location},location+'/labels')
                checks.check(not study_seen and not environment_seen,'no_rows_after_any_stop',location)
                n=verify_transition(row,previous,counters,ranges,checks,location)
                phase_rows[phase]+=1;phase_physics[phase]+=n;add_effort(effort[phase],row)
                common.record_risk(risk['full'],row,ranges,joint_index=0);common.record_risk(risk[phase],row,ranges,joint_index=0)
                previous=row['observation_after'];environment_seen=row['diagnostics']['terminated']
                if index==prefix_steps:
                    if not states: states['nominal']=initial_state('diagonal_hinge5')
                    if kind=='calibration':
                        states.update({name:initial_state(STRUCTURES[name]) for name in ('diagonal','coupled')})
                        checks.check(set(sr['initial_models'])=={'diagonal','coupled'},'exact_cold_model_set',tid)
                        for name in ('diagonal','coupled'): verify_snapshot(sr['initial_models'][name],states[name],qref,checks,tid+'/initial/'+name)
                if index<prefix_steps:
                    checks.compare(row['requested_torque'],[0.]*8,location+'/zero_prefix')
                    checks.compare(row['target_q'],None,location+'/prefix_target')
                    checks.compare(row['predicted_next_qv'],{},location+'/prefix_predictions')
                    checks.compare(row['model_update'],None,location+'/no_prefix_update')
                    checks.compare(row.get('study_abort'),None,location+'/no_prefix_study')
                    continue
                q,v=[row['observation_before'][k][:2] for k in ('joint_position','joint_velocity')]
                nq,nv=[row['observation_after'][k][:2] for k in ('joint_position','joint_velocity')]
                u=row['requested_torque'][:2];active=index-prefix_steps
                study_seen=verify_study(row,qref,checks,location)
                target=None
                if kind=='calibration': expected_u=calibration_request(active,directions)
                elif kind.startswith('prediction_'): expected_u=prediction_request(kind,active,directions)
                else:
                    target=[qref[i]+directions[i]*(.04 if active<100 else .08) for i in range(2)]
                    checks.check(all(ranges[i][0]+.03<=target[i]<=ranges[i][1]-.03 for i in range(2)),'public_target_interior',location)
                    if kind in MPC_KINDS:
                        name=kind.removesuffix('_mpc');state=states[name]
                        decision=replay_mpc(state['observed_theta'],state['structure'],qref,q,v,target,previous_u,ranges[:2])
                        checks.compare(row['planner_decision'],decision,location+'/independent_mpc')
                        expected_u=decision['torque'];fallback+=int(decision['fallback'])
                        for key in PLANNING_KEYS: planning[key]+=decision[key]
                    elif kind=='combined_pd':
                        raw=[64.*(target[i]-q[i])-spec.pd_gains[i][1]*v[i] for i in range(2)]
                        expected_u=[max(-.5,min(.5,x)) for x in raw]
                        checks.compare(row['raw_pd_torque_nm'],raw,location+'/raw_combined_pd')
                        checks.compare(row['planner_decision'],None,location+'/pd_no_model_plan')
                    else:
                        expected_u=[0.,0.]
                        checks.compare(row['planner_decision'],None,location+'/zero_no_plan')
                checks.compare(u,expected_u,location+'/fixed_request')
                checks.compare(row['target_q'],target,location+'/current_target')
                if kind!='combined_pd': checks.compare(row['raw_pd_torque_nm'],None,location+'/no_pd')
                active_states={name:states[name] for name in ('diagonal','coupled')} if kind=='calibration' else states
                predictions={name:predict(s['observed_theta'],s['structure'],qref,q,v,u) for name,s in active_states.items()}
                if kind!='calibration': predictions['persistence']=([q[i]+DT*v[i] for i in range(2)],v)
                checks.check(set(row['predicted_next_qv'])==set(predictions),'exact_prediction_model_set',location)
                checks.compare(row['predicted_next_qv'],predictions,location+'/preupdate_predictions')
                partial=None if target is None or n==10 else [nq[i]-target[i] for i in range(2)]
                checks.compare(row['partial_interval_target_error_rad'],partial,location+'/partial_target')
                if partial is not None: partial_errors.append({'step_index':index,'target_q':target,'errors_rad':partial,'executed_substeps':n})
                if kind=='calibration':
                    if n==10:
                        checks.check(set(row['model_update'])=={'diagonal','coupled'},'same_two_model_transition',location)
                        for name in ('diagonal','coupled'): replay_update(row['model_update'][name],row,states[name],qref,checks,location+'/'+name)
                    else: checks.compare(row['model_update'],{'updated':False,'phase':'partial_calibration_interval','executed_substeps':n},location+'/partial_no_fit')
                else: checks.compare(row['model_update'],None,location+'/frozen_evaluation')
                if n==10:
                    for name,(pq,pv) in predictions.items():
                        e=errors.setdefault(name,{'q':[],'v':[]})
                        e['q'].append([nq[i]-pq[i] for i in range(2)]);e['v'].append([nv[i]-pv[i] for i in range(2)])
                    if target is not None:
                        tracking.append([nq[i]-target[i] for i in range(2)])
                        for i in range(2): saturation[i]+=abs(u[i])==.5
                previous_u=u
            if exceptions and kind=='calibration' and qref is not None:
                if not states and sr.get('initial_models'):
                    states={'nominal':initial_state('diagonal_hinge5'),**{name:initial_state(STRUCTURES[name]) for name in ('diagonal','coupled')}}
                    for name in ('diagonal','coupled'): verify_snapshot(sr['initial_models'][name],states[name],qref,checks,tid+'/exception_initial/'+name)
                verify_exception_updates(exceptions[0],ep,regular,states,qref,checks,tid+'/exception',prefix_steps=prefix_steps)
            for exception in exceptions:
                checks.compare(exception,{'trial_id':tid,'seed':seed,'kind':kind,'joint_indices':[0,1]},tid+'/exception_labels')
                returned=exception.get('returned_step_diagnostics')
                if returned is not None and exception.get('step_index') is not None and exception['step_index']>=prefix_steps:
                    study_seen=verify_study(exception,qref,checks,tid+'/exception_returned_study') or study_seen
                for observation_key in ('observation_before','observation_after'):
                    observation=exception.get(observation_key)
                    if observation is not None:
                        checks.check(set(observation)==set(NATIVE),'exception_native_whitelist',tid)
                        for key,width in NATIVE.items(): vector(observation[key],width)
                endpoint=exception.get('observation_after')
                if endpoint is not None and exception.get('qpos') is not None and exception.get('qvel') is not None:
                    checks.check(endpoint['joint_position']==vector(exception['qpos'],15)[7:]
                        and endpoint['joint_velocity']==vector(exception['qvel'],14)[6:],'exception_native_encoder_mapping',tid)
            for phase in PHASES:
                b=ep['phase_budgets'][phase]
                checks.check(b['control_calls_attempted']>=b['control_steps']>=phase_rows[phase]
                    and phase_physics[phase]<=b['physics_steps']<=b['control_calls_attempted']*10,'paid_vs_saved_phase',tid+'/'+phase)
            for key in ('control_calls_attempted','control_steps','physics_steps'):
                checks.compare(ep[key],sum(b[key] for b in ep['phase_budgets'].values()),tid+'/ledger/'+key)
            missing_physics=ep['physics_steps']-counters['physics'];missing_rows=ep['control_steps']-len(regular)
            checks.check(0<=missing_physics<=10 and 0<=missing_rows<=1,'single_failure_missing_cost_bounds',tid)
            returned,written=ep['returned_steps'],ep['written_returned_steps']
            checks.check(type(returned) is int and type(written) is int and 0<=written<=returned<=ep['control_steps']
                and len(regular)<=returned<=len(regular)+1,'returned_vs_confirmed_written_costs',tid)
            checks.compare(ep['returned_unwritten_steps'],returned-written,tid+'/unconfirmed_returned_steps')
            checks.check(type(ep['unreturned_physics_steps']) is int and 0<=ep['unreturned_physics_steps']<=missing_physics,'unreturned_physics_not_lost',tid)
            is_complete=(ep['status']=='completed' and len(regular)==prefix_steps+trial_duration(kind)
                and ep['control_calls_attempted']==ep['control_steps']==len(regular)
                and ep['physics_steps']==10*len(regular) and not exceptions
                and all(r['diagnostics']['executed_substeps']==10 and not r['diagnostics']['terminated'] and r.get('study_abort') is None for r in regular))
            checks.check(ep['status']!='completed' or is_complete,'complete_claim_requires_full_nonterminal_trajectory',tid)
            checks.compare(ep.get('completed'),is_complete,tid+'/episode_completion')
            checks.compare(ev['completed'],is_complete,tid+'/collector_completion')
            checks.compare(ev['status'],ep['status'],tid+'/collector_status')
            checks.compare(ev['study_abort'],ep['study_abort'],tid+'/collector_study')
            checks.compare(ev['environment_terminated'],ep['environment_terminated'],tid+'/collector_environment')
            checks.compare(ev['environment_stop_reason'],ep['environment_stop_reason'],tid+'/collector_environment_reason')
            expected_reason=(ep['environment_stop_reason'] if ep['environment_terminated'] else
                ep['study_abort'] if ep['study_abort'] is not None else ep['collector_exception'])
            checks.compare(ep['reason'],expected_reason,tid+'/stop_reason_precedence')
            if not exceptions:
                checks.compare(returned,len(regular),tid+'/all_returned_endpoints_saved')
                checks.compare(written,len(regular),tid+'/all_writes_confirmed')
                checks.compare(ep['environment_fingerprint_before'],ep['environment_fingerprint_after'],tid+'/fixed_physical_parameters')
                checks.compare(ep['study_abort'],regular[-1].get('study_abort') if regular else None,tid+'/stop_preserved')
                checks.compare(ep['environment_terminated'],environment_seen,tid+'/environment_stop')
                checks.compare(ev['tracking_rmse'],paired_rmse(tracking),tid+'/tracking_metrics')
                for field,key in (('position_prediction_rmse','q'),('velocity_prediction_rmse','v')):
                    checks.compare(ev[field],{name:paired_rmse(e[key]) for name,e in errors.items()},tid+'/'+field)
                checks.compare(ev['metric_prediction_step_count'],{name:len(e['v']) for name,e in errors.items()},tid+'/prediction_counts')
                checks.compare(ev['metric_control_step_count'],len(tracking),tid+'/control_count')
                checks.compare(ev['partial_interval_target_errors_rad'],partial_errors,tid+'/partial_errors')
                checks.compare(ev['saturated_control_steps_per_axis'],saturation,tid+'/saturation')
            effort_audit={p:reconcile_effort(ev,p,effort[p],ep['phase_budgets'][p]['physics_steps'],phase_physics[p],exceptions,checks,tid+'/effort/'+p) for p in PHASES}
            checks.compare(ev['control_effort'],ev['phase_effort']['control'],tid+'/control_effort_alias')
            paid_control=ep['phase_budgets']['control']['physics_steps'];measured=ev['phase_actual_effort_substeps']['control']
            checks.compare(ev['actual_effort_complete'],measured==paid_control,tid+'/actual_complete')
            checks.compare(ev['actual_effort_is_lower_bound'],measured<paid_control,tid+'/actual_lower_bound')
            checks.compare(ev['actual_control_effort_substeps'],measured,tid+'/actual_control_substeps')
            checks.compare(ev['missing_control_effort_substeps'],paid_control-measured,tid+'/missing_control_substeps')
            if not exceptions:
                checks.compare(ev['planning_accounting'],{**planning,'scalar_counts_complete':True,'scalar_counts_is_lower_bound':False,'unknown_failed_planner_calls':0},tid+'/planning_paid_math')
                checks.compare(ev['planner_attempt_count'],sum(r['step_index']>=prefix_steps for r in regular) if kind in MPC_KINDS else 0,tid+'/planner_calls')
                checks.compare(ev['planner_decision_count'],sum(r['step_index']>=prefix_steps for r in regular) if kind in MPC_KINDS else 0,tid+'/planner_decisions')
                checks.compare(ev['failed_planner_attempts'],0,tid+'/failed_planners')
                checks.compare(ev['planner_fallbacks'],fallback,tid+'/fallbacks')
            else:
                accounting=ev['planning_accounting']
                original=exceptions[0]
                duplicate=any(r['shared_transition_id']==original['shared_transition_id'] for r in regular)
                extra_decision=original.get('planner_decision')
                successful=sum(r['step_index']>=prefix_steps for r in regular) if kind in MPC_KINDS else 0
                if kind in MPC_KINDS and extra_decision is not None and not duplicate:
                    state=states[kind.removesuffix('_mpc')]
                    q,v=[original['observation_before'][k][:2] for k in ('joint_position','joint_velocity')]
                    decision=replay_mpc(state['observed_theta'],state['structure'],qref,q,v,original['target_q'],previous_u,ranges[:2])
                    checks.compare(extra_decision,decision,tid+'/exception_successful_mpc')
                    for key in PLANNING_KEYS: planning[key]+=decision[key]
                    successful+=1
                failed=ev['failed_planner_attempts']
                checks.check(type(failed) is int and 0<=failed<=1 and (kind in MPC_KINDS or failed==0),'one_failed_planner_call',tid)
                failed_ledger=original.get('failure_accounting',{}).get('pair_planning_accounting')
                if failed_ledger is not None:
                    checks.check(failed==1,'failed_math_ledger_requires_failed_call',tid)
                    for key in PLANNING_KEYS:
                        checks.check(type(failed_ledger[key]) is int and failed_ledger[key]>=0,'known_failed_math_count',tid+'/'+key)
                        planning[key]+=failed_ledger[key]
                    checks.check(failed_ledger['pair_prediction_attempts']<=1215
                        and failed_ledger['scalar_prediction_attempts']<=2430
                        and failed_ledger['pair_prediction_successes']<=failed_ledger['pair_prediction_attempts']
                        and failed_ledger['scalar_prediction_successes']<=failed_ledger['scalar_prediction_attempts'],
                        'failed_math_fixed_candidate_horizon_bounds',tid)
                checks.compare({key:accounting[key] for key in PLANNING_KEYS},planning,tid+'/retained_failed_math_cost')
                checks.compare(accounting['unknown_failed_planner_calls'],failed if failed_ledger is None else 0,tid+'/unknown_failed_calls')
                checks.compare(ev['planner_attempt_count'],successful+failed,tid+'/planner_invocations')
                checks.check(type(ev['planner_attempt_count']) is int and ev['planner_attempt_count']<=spec.control_steps,'planner_attempt_cap',tid)
                checks.compare(ev['planner_decision_count'],ev['planner_attempt_count']-ev['failed_planner_attempts'],tid+'/planner_count_partition')
                unknown=accounting['unknown_failed_planner_calls']>0 or accounting['unknown_scalar_failure_count']>0
                checks.compare(accounting['scalar_counts_complete'],not unknown,tid+'/scalar_complete')
                checks.compare(accounting['scalar_counts_is_lower_bound'],unknown,tid+'/scalar_lower_bound')
            if ev['planner_spec'] is not None:
                checks.check(kind in MPC_KINDS,'planner_spec_only_mpc',tid)
                checks.compare(ev['planner_spec'],planner_spec(qref,ranges[:2]),tid+'/exact_fixed_planner_spec')
            if is_complete and kind in MPC_KINDS:
                checks.check(ev['planner_spec'] is not None,'complete_mpc_requires_planner_spec',tid)
            if kind=='calibration':
                calibrated=is_complete
                checks.compare(sr['calibration_completed'],calibrated,tid+'/calibrated')
                for name in ('diagonal','coupled'):
                    if name in states:
                        verify_snapshot(sr['calibration_models'][name],states[name],qref,checks,tid+'/saved/'+name)
                        if calibrated:
                            verify_snapshot(sr['learned_models'][name],states[name],qref,checks,tid+'/frozen/'+name)
                            checks.compare(sr['learned_models'][name]['trainable'],False,tid+'/not_trainable/'+name)
                            checks.compare(states[name]['count'],spec.calibration_steps,tid+'/complete_vector_updates/'+name)
                if not calibrated: checks.compare(sr['learned_models'],{},tid+'/no_failed_model_publication')
                final_vector=sum(s['count'] for name,s in states.items() if name!='nominal')
                checks.compare(sr['calibration_vector_updates'],final_vector,tid+'/vector_ledger')
                checks.compare(sr['calibration_scalar_updates'],2*final_vector,tid+'/scalar_ledger')
                total_vector+=final_vector;total_scalar+=2*final_vector
            elif states:
                hashes={name:digest(parameter_record(qref,state,observed=True)) for name,state in states.items()}
                checks.compare(ev['models_before'],hashes,tid+'/frozen_before')
                checks.compare(ev['models_after'],hashes,tid+'/frozen_after')
            checks.check(not ep.get('risk_telemetry_complete',False) or missing_physics==0 and not exceptions,'risk_completeness_not_overclaimed',tid)
            for phase in risk:
                risk[phase]['target_guarded_substeps_by_axis']=risk[phase]['permission_screened_substeps_by_joint'][:2]
                risk[phase]['reconstruction_complete']=missing_physics==0 and not exceptions
            tmetrics=paired_rmse(tracking)
            derived_ev={'eligible':is_complete and checks.failed==trial_start_failures,'completed':is_complete,'status':ep['status'],
                'study_aborted':study_seen or ep.get('study_abort') is not None,'environment_terminated':ep.get('environment_terminated') is True,
                'tracking_rmse_rad':None if tmetrics is None else tmetrics['joint'],
                'tracking_rmse_by_axis_rad':None if tmetrics is None else tmetrics['per_axis'],
                'velocity_prediction_rmse':{name:paired_rmse(e['v'])['per_axis'] for name,e in errors.items() if e['v']},
                'position_prediction_rmse':{name:paired_rmse(e['q'])['per_axis'] for name,e in errors.items() if e['q']},
                'control_effort':ev['control_effort'],'actual_effort_complete':ev['actual_effort_complete'],
                'risk':risk,'effort_audit':effort_audit,'paid_budget':{k:ep[k] for k in ('control_calls_attempted','control_steps','physics_steps')},
                'independent_planning_accounting':planning,
                'stored_returned_endpoints':len(regular),'collector_confirmed_written_endpoints':written,
                'collector_returned_endpoints':returned,'unreconstructed_physics_substeps':missing_physics,
                'complete_score_endpoints':len(tracking),'partial_score_endpoints':len(partial_errors)}
            if kind in CONTROL_KINDS and qref is not None:
                derived_ev['target_segments_and_planned_tails']=planned_tail_metrics(regular,qref,directions)
                derived_ev['calibration_support']=state_coverage(grouped.get(f'seed{seed}_calibration',[]),regular,qref)
            if states and qref is not None:
                derived_ev['conditional_rollouts']=conditional_rollouts(rows,states,qref,prefix_steps=prefix_steps)
                derived_ev['conditional_rollouts']['calibration_in_sample']=kind=='calibration'
                derived_ev['conditional_rollouts']['uses_final_frozen_parameters']=True
            seed_derived[kind]=derived_ev
            if kind=='calibration' and not calibrated:
                states={name:state for name,state in states.items() if name=='nominal'}
        derived.append({'seed':seed,'evaluations':seed_derived,'calibration_vector_updates':sr['calibration_vector_updates'],
                        'calibration_scalar_updates':sr['calibration_scalar_updates']})
    budget={key:sum(ep[key] for ep in episodes) for key in ('control_calls_attempted','control_steps','physics_steps')}
    for key,value in budget.items(): checks.compare(metadata[key],value,'batch_ledger/'+key)
    checks.compare(metadata['model_updates'],total_scalar,'batch_committed_scalar_updates')
    checks.compare(metadata['vector_model_updates'],total_vector,'batch_committed_vector_updates')
    checks.compare(metadata['all_trials_successful'],all(ep['status']=='completed' for ep in episodes),'batch_success_flag')
    for label,status in (('completed_trials','completed'),('terminated_trials','terminated'),('exception_trials','exception'),('blocked_trials','blocked')):
        checks.compare(metadata[label],sum(ep['status']==status for ep in episodes),'batch_outcomes/'+label)
    return {'seeds':derived,'budget':{**budget,'model_updates':total_scalar,'vector_model_updates':total_vector},
            'input_hashes':input_hashes,'episodes':episodes,'native_joint_order':list(common.JOINTS),
            'sample_semantics':'One complete shared physical vector transition supplies two native velocity labels; each model consumes two scalar updates only when its atomic state committed. The two models are not one transaction.'}

def audit(path,*,git_root=ROOT,spec=PAIR_DEVELOPMENT_SPEC):
    wall,cpu=time.perf_counter(),time.process_time()
    checks=Checks();result=None;reported=None
    try:
        metadata=require_pair(path,spec)
        reported={key:metadata.get(key) for key in ('control_calls_attempted','control_steps','physics_steps','model_updates','vector_model_updates')}
        result=audit_archive(path,checks,git_root,spec)
    except (OSError,ValueError,KeyError,TypeError,IndexError,AttributeError,OverflowError,zipfile.BadZipFile,ET.ParseError) as exc:
        checks.check(False,'archive_schema_or_read_error',{'type':type(exc).__name__,'message':str(exc)})
    gates=scientific_gates([] if result is None else result['seeds'],spec)
    gates['data_consistency_verified']=checks.failed==0
    for name in ('diagonal_contribution','coupled_contribution','coupled_increment'):
        gates[name]['validated_pass']=bool(gates[name]['passed'] and checks.failed==0 and git_root is not None and spec.scientific_gates_frozen and not spec.synthetic_fixture)
    for gate in gates['combined_pd_comparison'].values():
        gate['validated_pass']=bool(gate['passed'] and checks.failed==0 and git_root is not None and spec.scientific_gates_frozen and not spec.synthetic_fixture)
    return {'schema_version':1,'created_at_utc':datetime.now(timezone.utc).isoformat(),'audit_script_sha256':file_hash(__file__),
        'audit_dependency_sha256':{'scripts/audit_local_frozen.py':file_hash(ROOT/'scripts/audit_local_frozen.py')},
        'audit_spec':spec.record(),'checks':checks.count,'failed':checks.failed,'violations':checks.violations,
        'maximum_recomputation_difference':checks.maximum_difference,'archive':result,'final_gates':gates,
        'reported_paid_budget_if_replay_incomplete':reported,'execution':{'wall_seconds':time.perf_counter()-wall,
        'cpu_seconds':time.process_time()-cpu,'timing_scope':'Entry through report assembly; excludes imports and final output writing',
        'python':sys.version,'platform':platform.platform(),'third_party_dependencies':[],
        'physical_simulation_calls':0,'model_parameter_updates':0,'replayed_updates_are_frozen_log_audits':True,
        'independent_reconstructed_scalar_updates':0 if result is None else result['budget']['model_updates'],
        'independent_reconstructed_vector_updates':0 if result is None else result['budget']['vector_model_updates'],
        'source_git_verification_enabled':git_root is not None}}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive',type=Path);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    try:
        output=common.validate_output_path(args.output,[args.archive]);require_pair(args.archive)
    except (OSError,ValueError,KeyError,TypeError) as exc: parser.error(str(exc))
    result=audit(args.archive)
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x',encoding='utf-8',newline='\n') as stream: json.dump(result,stream,indent=2,sort_keys=True,allow_nan=False)
    print(json.dumps({'checks':result['checks'],'failed':result['failed'],'gates':result['final_gates']},indent=2,allow_nan=False))
    return 1 if result['failed'] else 0

if __name__=='__main__': raise SystemExit(main())
