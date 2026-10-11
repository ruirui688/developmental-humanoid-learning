"""Unpromoted E stdlib planning mathematics with explicit causal history.

No raw-data loader, CLI, simulator, model fitting or online helper imports.
Formal archive interfaces remain pending the root's frozen E protocol.
"""
from __future__ import annotations
from collections import Counter
import hashlib
import importlib.util
from itertools import product
import math
from pathlib import Path
import sys

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
