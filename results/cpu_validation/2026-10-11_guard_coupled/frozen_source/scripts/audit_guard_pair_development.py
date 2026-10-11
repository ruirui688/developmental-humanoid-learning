"""Independent C4 A guard-input frozen-log audit (standard library only).

Production scope and gates are immutable code declarations. Synthetic fixtures
can establish engineering consistency but can never validate scientific claims.
No collector, online model, NumPy or simulator is imported or called.
"""
from __future__ import annotations
import argparse
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
import gzip
import hashlib
import importlib.util
import io
from itertools import product
import json
import math
from pathlib import Path, PurePosixPath, PureWindowsPath
import platform
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
import zipfile

ROOT = next(p for p in Path(__file__).resolve().parents if (p/'pyproject.toml').is_file())
def _load(name,path):
    loader=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(loader)
    sys.modules[name]=module;loader.loader.exec_module(module)
    return module
common=_load('_guard_common_audit',ROOT/'scripts/audit_local_frozen.py')
pair_support=_load('_guard_pair_audit_support',ROOT/'scripts/audit_pair_frozen.py')
Checks,vector,finite=common.Checks,common.vector,common.finite
file_hash,digest,rmse=common.file_hash,common.digest,common.rmse
DT,PHYSICS_DT=.02,.002
PHASES=('prefix','calibration','prediction','control')
KINDS=('calibration','prediction','nominal_raw','learned_raw','nominal_guard','learned_guard','PDselected','zero')
MPC_KINDS=KINDS[2:6];CONTROL_KINDS=KINDS[2:]
NOMINAL=('nominal_raw','nominal_guard');LEARNED=('learned_raw','learned_guard')
STRUCTURES={name:('raw_request' if name.endswith('_raw') else 'known_angle_guard') for name in (*NOMINAL,*LEARNED)}
EFFORT_KEYS,NATIVE,ENVIRONMENT=common.EFFORT_KEYS,common.NATIVE,common.ENVIRONMENT
MPC_CONFIG=dict(common.MPC_CONFIG)
CAL_AMPLITUDES=(.125,.25,.375,.5,.25)
PRED_AMPLITUDES=(.125,.25,.375,.5,.375)
PRED_DIRECTIONS=((1.,0.),(0.,1.),(1.,1.),(1.,-1.),(1.,1.))
PLANNING_KEYS=pair_support.PLANNING_KEYS
SOURCE='src/developmental_physics/guard_pair_development.py'
AUDITOR='scripts/audit_guard_pair_development.py'
PROTOCOL='docs/GUARD_PAIR_DEVELOPMENT_PROTOCOL.md'
PD_DIR='results/cpu_validation/2026-10-11_pair_pd/'
PD_SELECTION=PD_DIR+'selection.json';PD_MANIFEST=PD_DIR+'manifest.json';PD_AUDIT=PD_DIR+'first_audit.json'
PD_PROTOCOL='docs/PAIR_PD_DEVELOPMENT_PROTOCOL.md'
PD_RAW_METADATA=PD_DIR+'raw/metadata.json';PD_RAW_ZIP=PD_DIR+'raw/source_snapshot.zip'
PD_SOURCE_FILES=(PD_SELECTION,PD_MANIFEST,PD_AUDIT,PD_RAW_METADATA,PD_RAW_ZIP)
KD_CANDIDATES=[[s,e] for s in (0.,1.,2.) for e in (1.,2.,4.)]

@dataclass(frozen=True)
class GuardPairAuditSpec:
    synthetic_fixture: bool=False
    scientific_gates_frozen: bool=True
    suite: str='guard_pair_development'
    pose: str='supine'
    seeds: tuple[int,...]=(0,1,2)
    joint_indices: tuple[int,...]=(0,1)
    split: str='development'
    protocol: str=PROTOCOL
    prefix_steps: int=100
    calibration_steps: int=400
    prediction_steps: int=100
    control_steps: int=200
    def __post_init__(self):
        if (type(self.synthetic_fixture) is not bool or type(self.scientific_gates_frozen) is not bool
            or self.scientific_gates_frozen is self.synthetic_fixture
            or self.suite!='guard_pair_development' or self.pose!='supine' or self.seeds!=(0,1,2)
            or self.joint_indices!=(0,1) or any(type(x) is not int for x in self.seeds+self.joint_indices)
            or self.split!='development' or self.protocol!=PROTOCOL
            or any(type(x) is not int for x in (self.prefix_steps,self.calibration_steps,self.prediction_steps,self.control_steps))
            or (self.prefix_steps,self.calibration_steps,self.prediction_steps,self.control_steps)!=(100,400,100,200)):
            raise ValueError('Immutable declared guard pair scope required; metadata cannot redefine it.')
    @property
    def reset_seeds(self): return {0:3757552657,1:1641411168,2:2001025171}
    @property
    def required_sources(self):
        return common.BASE_REQUIRED_SOURCES|{SOURCE,AUDITOR,PROTOCOL,'scripts/audit_pair_frozen.py',
            'scripts/audit_local_frozen.py','src/developmental_physics/local_pair_model.py',
            'src/developmental_physics/guard_pair_model.py','src/developmental_physics/pd_selection_binding.py',PD_PROTOCOL}|set(PD_SOURCE_FILES)
    def record(self):
        return {'suite':self.suite,'pose':self.pose,'seeds':list(self.seeds),'joint_indices':list(self.joint_indices),
            'split':self.split,'protocol':self.protocol,'collector':SOURCE,'auditor':AUDITOR,
            'synthetic_fixture':self.synthetic_fixture,'scientific_gates_frozen':self.scientific_gates_frozen,
            'prefix_steps':100,'calibration_steps':400,'prediction_steps':100,'control_steps':200,
            'input_bases':dict(STRUCTURES),'pd_selection':PD_SELECTION,'calibration_pulse_zero':[1,9],
            'prediction_velocity_ratio_max':.8,'contribution_tracking_mean_improvement_min':.20,
            'pd_tracking_mean_improvement_min':.05,'pd_actual_effort_ratio_max':1.05}
PRODUCTION_SPEC=GuardPairAuditSpec()
SYNTHETIC_SPEC=GuardPairAuditSpec(synthetic_fixture=True,scientific_gates_frozen=False)

def pair(value): return vector(list(value) if type(value) is tuple else value,2)
def _path(value):
    if (type(value) is not str or not value or value!=value.strip() or '\\' in value or ':' in value
        or '\x00' in value or PurePosixPath(value).is_absolute() or PureWindowsPath(value).drive
        or any(p in ('','.','..') for p in value.split('/'))): raise ValueError('Canonical relative POSIX path required.')
    return value
def _hash(value):
    if type(value) is not str or re.fullmatch('[0-9a-f]{64}',value) is None: raise ValueError('SHA-256 required.')
    return value
def _exact(value,keys):
    if type(value) is not dict or set(value)!=set(keys): raise ValueError('Exact object keys required.')
    return value
def _pairs(items):
    out={}
    for k,v in items:
        if k in out: raise ValueError('Duplicate JSON key.')
        out[k]=v
    return out
def parse_json(raw):
    return json.loads(raw.decode('utf-8') if isinstance(raw,bytes) else raw,object_pairs_hook=_pairs,
        parse_constant=lambda v:(_ for _ in ()).throw(ValueError('Nonstandard JSON constant.')))
def load_json(path): return parse_json(Path(path).read_bytes())
def strict_equal(a,b):
    return (type(a) is type(b) and (set(a)==set(b) and all(strict_equal(a[k],b[k]) for k in a) if type(a) is dict
        else len(a)==len(b) and all(strict_equal(x,y) for x,y in zip(a,b)) if type(a) is list
        else finite(a) and a==b if type(a) is float else a==b))
def guard_spec(ranges):
    return {'rule':'known_angle_guard_control_start_v1','public_joint_ranges_rad':[list(r) for r in ranges],
        'angle_margin_rad':.03,'request_clip_per_axis_nm':.5,
        'outward_block_comparison':'q <= lower + margin or q >= upper - margin','zero_is_blocked':False,
        'q_clipped':False,'evaluation_time':'current control-start q and already known request',
        'interval_semantics':'start-only projection; not realized 20 ms average input','future_actual_input':False,'physical_queries':0}
def describe_input(q,u,structure):
    basis,ranges=structure
    q,u=pair(q),pair(u)
    clipped=[max(-.5,min(.5,x)) for x in u]
    blocked=[bool((q[i]<=r[0]+.03 and clipped[i]<0.) or (q[i]>=r[1]-.03 and clipped[i]>0.)) for i,r in enumerate(ranges)]
    projected=[0. if blocked[i] else clipped[i] for i in range(2)]
    return {'native_q_rad':q,'requested_nm':u,'clipped_request_nm':clipped,'projected_start_nm':projected,
        'start_blocked':blocked,'input_basis':basis,'model_feature_command_nm':u if basis=='raw_request' else projected}
def features(structure,qref,q,v,u):
    qref,q,v,u=(pair(x) for x in (qref,q,v,u))
    mapped=describe_input(q,u,structure)['model_feature_command_nm']
    h=[(1. if x>0 else -1. if x<0 else 0.)*max(abs(x)-.25,0.) for x in mapped]
    result=[[v[i],q[i]-qref[i],mapped[i],h[i],1.] for i in range(2)]
    if not all(finite(x) for row in result for x in row): raise ValueError('Finite causal features required.')
    return result
def initial_state(basis,ranges):
    if basis not in ('raw_request','known_angle_guard'): raise ValueError('Declared input basis required.')
    for limits in ranges: pair(limits)
    if len(ranges)!=2 or any(l[0]>=l[1] for l in ranges): raise ValueError('Ordered public ranges required.')
    state=pair_support.initial_state('diagonal_hinge5');state['structure']=(basis,tuple(tuple(x) for x in ranges))
    return state
def parameter_record(qref,state,*,observed=False):
    basis,ranges=state['structure']
    base=dict(state,structure='diagonal_hinge5')
    record=pair_support.parameter_record(qref,base,observed=observed)
    if basis=='known_angle_guard':
        record['features_per_output']=[[f'v{i}',f'q{i}-qref{i}',f'start_G{i}(q{i},u{i})',f'h(start_G{i}(q{i},u{i}))','1'] for i in range(2)]
    record['input_mapping']={'basis':basis,'feature_command':('original requested u without model-side clip' if basis=='raw_request'
        else 'G(current q, original requested u) at control start'),'public_guard':guard_spec(ranges),
        'guard_used_by_model':basis=='known_angle_guard','recompute':'same causal mapping on every RLS and mathematical prediction call'}
    return record
PredictionError=pair_support.PredictionError
replay_rls=pair_support.replay_rls

def predict(theta,structure,qref,q,v,u):
    try: x=features(structure,qref,q,v,u)
    except ValueError as exc: raise PredictionError(0,0) from exc
    if len(theta)!=2 or any(len(row)!=5 or not all(finite(t) for t in row) for row in theta): raise ValueError('Finite two-head model required.')
    next_v=[]
    for i in range(2):
        value=sum(t*f for t,f in zip(theta[i],x[i]))
        if not finite(value): raise PredictionError(i+1,i)
        next_v.append(value)
    next_q=[q[i]+DT*next_v[i] for i in range(2)]
    if not all(finite(z) for z in next_q): raise PredictionError(2,2)
    return next_q,next_v

def propose_pair(state,qref,q,v,u,labels):
    x=features(state['structure'],qref,q,v,u)
    return x,[replay_rls(state['theta'][i],state['covariance'][i],x[i],pair(labels)[i]) for i in range(2)]
def replay_update(item,row,state,qref,checks,location):
    q,v=[row['observation_before'][k][:2] for k in ('joint_position','joint_velocity')]
    u,labels=row['requested_torque'][:2],row['observation_after']['joint_velocity'][:2]
    x,proposals=propose_pair(state,qref,q,v,u,labels)
    pq,pv=predict(state['observed_theta'],state['structure'],qref,q,v,u)
    expected={'phase':'identification','updated':True,'shared_transition_id':row['shared_transition_id'],
        'features_per_output':x,'preupdate_prediction':{'next_q_rad':pq,'next_v_rad_s':pv},
        'observed_next_v_rad_s':labels,'parameter_fingerprint_before':digest(parameter_record(qref,state,observed=True)),
        'vector_update_count':state['count']+1,'scalar_update_count':2*(state['count']+1),'committed_scalar_updates':2}
    checks.compare(item,expected,location+'/causality')
    checks.check(type(item.get('updated')) is bool and item['updated'] is True,'atomic_pair_update',location)
    checks.check(len(item['output_records'])==2,'exact_two_output_proposals',location)
    for i,(theta,covariance,residual) in enumerate(proposals):
        checks.compare(item['output_records'][i],{'output_index':i,'features':x[i],'observed_next_v_rad_s':labels[i],
            'preupdate_error_rad_s':residual,'proposed_coefficients':theta,'proposed_covariance':covariance,'committed':True},location+f'/output{i}')
    state['theta']=[p[0] for p in proposals];state['covariance']=[p[1] for p in proposals];state['count']+=1
    state['observed_theta']=[r['proposed_coefficients'] for r in item['output_records']]
    state['observed_covariance']=[r['proposed_covariance'] for r in item['output_records']]
    checks.compare(item['parameter_fingerprint_after'],digest(parameter_record(qref,state,observed=True)),location+'/hash_chain')
def verify_snapshot(saved,state,qref,checks,location):
    checks.check(set(saved)==set(parameter_record(qref,state))|{'parameter_fingerprint','vector_update_count','scalar_update_count','output_update_counts','trainable','initial_prior','input_boundary','update_commit'},'exact_snapshot_parameter_whitelist',location)
    checks.compare(saved,parameter_record(qref,state),location+'/parameters')
    checks.compare(saved,{'update_commit':'single immutable state reference for both outputs, covariance and counts',
        'initial_prior':'generic velocity continuity and torque response; zero cross coefficients',
        'input_boundary':'current native q/v and already known requested u; no actual future torque or simulator state',
        'vector_update_count':state['count'],'scalar_update_count':2*state['count'],
        'output_update_counts':[state['count']]*2},location+'/atomic_counts')
    checks.compare(saved['parameter_fingerprint'],digest({key:saved[key] for key in parameter_record(qref,state)}),location+'/raw_hash')
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
    if type(active) is not int or not 0<=active<400: raise ValueError('Fixed calibration index required.')
    if not isinstance(directions,(list,tuple)) or len(directions)!=2 or any(type(x) is not int or x not in (-1,1) for x in directions): raise ValueError('Fixed signed directions required.')
    block,slot=divmod(active,20);sign=1 if slot==0 else -1 if slot==10 else 0
    shape=(1,0) if block<5 else (0,1) if block<10 else (1,1) if block<15 else (1,-1)
    return [directions[i]*shape[i]*sign*CAL_AMPLITUDES[block%5] for i in range(2)]
def prediction_request(kind,active,directions):
    if kind!='prediction' or type(active) is not int or not 0<=active<100: raise ValueError('Fixed prediction index required.')
    block,slot=divmod(active,20);sign=1 if slot==0 else -1 if slot==10 else 0
    return [directions[i]*PRED_DIRECTIONS[block][i]*sign*PRED_AMPLITUDES[block] for i in range(2)]
study_condition=pair_support.study_condition

def duration(kind,control_steps=200):
    if kind not in KINDS: raise ValueError('Declared kind required.')
    return 400 if kind=='calibration' else 100 if kind=='prediction' else control_steps

def planned_matrix(spec=PRODUCTION_SPEC):
    return [{'trial_id':f'seed{seed}_{kind}','seed':seed,'kind':kind,'maximum_control_steps':100+duration(kind)} for seed in spec.seeds for kind in KINDS]
def require_pair(path,spec=PRODUCTION_SPEC):
    if type(spec) is not GuardPairAuditSpec: raise ValueError('Trusted immutable scope required.')
    metadata=load_json(Path(path)/'metadata.json')
    expected={'suite':spec.suite,'pose':spec.pose,'joint_indices':[0,1],'seeds':[0,1,2],
        'split':'development','synthetic':spec.synthetic_fixture,'native_joint_count':8,'model_input_bases':dict(STRUCTURES)}
    if (any(not strict_equal(metadata.get(k),v) for k,v in expected.items())
        or type(metadata.get('protocol')) is not dict or metadata['protocol'].get('path')!=spec.protocol):
        raise ValueError('Only exact declared scope accepted before trace or ZIP reads.')
    gains=metadata.get('pd_gains',{})
    pair(gains.get('kp'));pair(gains.get('kd'))
    if gains['kp']!=[64.,64.] or gains['kd'] not in KD_CANDIDATES: raise ValueError('Validated finite-grid PD gains required.')
    return metadata

def verify_sources(path,metadata,checks,git_root,spec):
    manifest=load_json(path/'manifest.json')
    names={p.name for p in path.iterdir() if p.is_file() and p.name!='manifest.json'}
    checks.check(set(manifest)==names,'manifest_exact_coverage')
    checks.check({'metadata.json','episodes.json','seed_results.json','trace.jsonl.gz','source_snapshot.zip'}.issubset(manifest),'manifest_core_files')
    for name,expected in manifest.items():
        if _path(name)!=Path(name).name: raise ValueError('Local manifest filenames required.')
        checks.check(file_hash(path/name)==_hash(expected),'manifest_hash',name)
    commit=metadata.get('source_commit');valid_commit=type(commit) is str and re.fullmatch('[0-9a-f]{40}',commit) is not None
    checks.check(metadata.get('source_status')=='' and metadata.get('source_dirty') is False,'clean_collection_source')
    checks.check(commit=='synthetic-fixture-no-git' if spec.synthetic_fixture else valid_commit,'source_commit_identity')
    hashes=metadata['source_sha256']
    checks.check((spec.required_sources-set(PD_SOURCE_FILES)).issubset(hashes),'required_source_coverage')
    if not spec.synthetic_fixture: checks.check(set(PD_SOURCE_FILES).issubset(hashes),'formal_pd_five_source_coverage')
    checks.compare(metadata['source_snapshot_sha256'],file_hash(path/'source_snapshot.zip'),'source_zip_byte_binding')
    with zipfile.ZipFile(path/'source_snapshot.zip') as archive:
        checks.check(len(archive.namelist())==len(set(archive.namelist())) and set(archive.namelist())==set(hashes),'source_zip_exact_unique_coverage')
        for name,digest_value in hashes.items():
            _path(name);_hash(digest_value)
            blob=archive.read(name)
            checks.check(hashlib.sha256(blob).hexdigest()==digest_value,'source_zip_hash',name)
            if git_root is not None and not spec.synthetic_fixture and valid_commit:
                result=subprocess.run(['git','show',f'{commit}:{name}'],cwd=git_root,capture_output=True,check=False)
                checks.check(result.returncode==0 and result.stdout==blob,'source_git_blob_bytes',name)
        xml=ET.fromstring(archive.read(common.ASSET))
        if not spec.synthetic_fixture:
            checks.compare(metadata['independent_auditor'],{'path':AUDITOR,'sha256':file_hash(__file__),
                'pending':False,'required_for_formal':True},'executing_auditor_identity')
            checks.check(archive.read(AUDITOR)==Path(__file__).read_bytes(),'executing_auditor_matches_archive')
            for support in ('scripts/audit_local_frozen.py','scripts/audit_pair_frozen.py'):
                checks.check(archive.read(support)==(ROOT/support).read_bytes(),'executing_support_matches_archive',support)
    if git_root is not None and not spec.synthetic_fixture and valid_commit:
        tree=subprocess.run(['git','ls-tree','-r','--name-only',commit,'src/developmental_physics'],cwd=git_root,capture_output=True,text=True,check=False)
        sources={n for n in tree.stdout.splitlines() if n.endswith('.py') and n.count('/')==2}
        checks.check(tree.returncode==0 and sources.issubset(hashes),'all_physics_python_sources_archived')
    compiler=xml.find('compiler');factor=math.pi/180. if compiler is not None and compiler.get('angle','degree')=='degree' else 1.
    ranges={j.get('name'):[float(x)*factor for x in j.get('range').split()] for j in xml.findall('.//joint') if j.get('range')}
    return [ranges[name] for name in common.JOINTS],{**manifest,'manifest.json':file_hash(path/'manifest.json')}

PD_SCOPE={'synthetic_fixture':False,'scientific_frozen':True,'suite':'pair_pd_development','protocol':PD_PROTOCOL,
    'collector':'src/developmental_physics/pair_pd_development.py','auditor':'scripts/audit_pair_pd.py',
    'seeds':[0,1,2],'kp':[64.,64.],'kd_candidates':KD_CANDIDATES,'prefix_steps':100,'control_steps':200,
    'joint_indices':[0,1],'pose':'supine','split':'development'}
PD_METADATA={'suite':'pair_pd_development','synthetic':False,'backend':'MuJoCo CPU','gpu':None,
    'pose':'supine','joint_indices':[0,1],'native_joint_count':8,'seeds':[0,1,2],'split':'development',
    'kp':[64.,64.],'kd_candidates':KD_CANDIDATES,'prefix_steps':100,'control_steps_per_trial':200,
    'target_offsets_rad':[.04,.08],'target_information':'own paid native qref plus direction; current target only; no preview or clipping',
    'study_abort_spec':{'active_only':True,'absolute_q_minus_qref_rad':.12,'absolute_velocity_rad_s':1.,'comparison':'>=',
        'any_axis':True,'feedback_action':None,'complete_terminal_scored_not_complete':True},
    'pd_controller_spec':{'implementation':'feedback_validate.pd_request per original j0/j1','permission_nm':.5,'body_model_input':False,'gain_updates':0},
    'parameter_updates':{'body_model':0,'policy':0,'gains':0},'model_updates':0,'teacher_calls':0,'external_demonstration_samples':0}

def reconstruct_pd_binding(source_bytes):
    """Independently bind five archived original identity files, no raw trace reads."""
    if not set(PD_SOURCE_FILES).issubset(source_bytes): raise ValueError('All five PD identity sources required.')
    selection=parse_json(source_bytes[PD_SELECTION]);_exact(selection,{'schema','status','selected','protocol','sources'})
    if selection['schema']!='c4-pd-selection-v1' or selection['status']!='selected': raise ValueError('Selected PD schema required.')
    selected=_exact(selection['selected'],{'candidate_id','joint_indices','kp','kd'});index=selected['candidate_id']
    if type(index) is not int or not 0<=index<9 or not strict_equal(selected['joint_indices'],[0,1]): raise ValueError('PD candidate identity invalid.')
    if not strict_equal(selected['kp'],[64.,64.]) or not strict_equal(selected['kd'],KD_CANDIDATES[index]): raise ValueError('PD candidate gains invalid.')
    protocol=_exact(selection['protocol'],{'path','sha256'});_hash(protocol['sha256'])
    if protocol['path']!=PD_PROTOCOL or hashlib.sha256(source_bytes[PD_PROTOCOL]).hexdigest()!=protocol['sha256']: raise ValueError('PD protocol source mismatch.')
    sources=_exact(selection['sources'],{'manifest','audit'})
    for label,name in (('manifest',PD_MANIFEST),('audit',PD_AUDIT)):
        record=_exact(sources[label],{'path','sha256'})
        if record['path']!=name or hashlib.sha256(source_bytes[name]).hexdigest()!=_hash(record['sha256']): raise ValueError('PD selected source hash mismatch.')
    manifest=parse_json(source_bytes[PD_MANIFEST]);audit=parse_json(source_bytes[PD_AUDIT])
    if not strict_equal(manifest.get('protocol'),protocol): raise ValueError('PD manifest protocol mismatch.')
    if (audit.get('validated_selection') is not True or audit.get('source_git_verification_enabled') is not True
        or type(audit.get('failed_checks')) is not int or audit['failed_checks']!=0 or not strict_equal(audit.get('immutable_scope'),PD_SCOPE)):
        raise ValueError('PD independent original audit is not formally validated.')
    sel=audit.get('selection',{})
    if sel.get('status')!='selected': raise ValueError('PD original audit lacks selected result.')
    picked=_exact(sel.get('picked'),{'candidate','kp','kd','eligible','sort_key','paid_control_steps','paid_physics_steps'})
    if (type(picked['candidate']) is not int or picked['candidate']!=index or picked['eligible'] is not True
        or not strict_equal(picked['kp'],selected['kp']) or not strict_equal(picked['kd'],selected['kd'])
        or type(picked['paid_control_steps']) is not int or picked['paid_control_steps']!=900
        or type(picked['paid_physics_steps']) is not int or picked['paid_physics_steps']!=9000): raise ValueError('PD audit chosen identity mismatch.')
    key=picked['sort_key']
    if type(key) is not list or len(key)!=4 or any(not finite(x) or x<0 for x in key[:3]) or type(key[3]) is not int or key[3]!=index: raise ValueError('PD sort key invalid.')
    files=manifest.get('files');raw_records={}
    if type(files) is not dict or not files: raise ValueError('PD files mapping required.')
    for name,record in files.items():
        _path(name);_exact(record,{'kind','source','bytes','sha256'});_hash(record['sha256'])
        if type(record['bytes']) is not int or record['bytes']<0 or type(record['kind']) is not str or not record['kind'] or type(record['source']) is not str or not record['source']: raise ValueError('PD manifest file metadata invalid.')
        if name.startswith('raw/'):
            local=name[4:]
            if '/' in local: raise ValueError('PD raw names must be local.')
            raw_records[local]=record['sha256']
    if not strict_equal(audit.get('input_hashes'),raw_records) or not {'metadata.json','source_snapshot.zip','manifest.json','episodes.json','selection.json','trace.jsonl.gz'}.issubset(raw_records): raise ValueError('PD original input hash mapping mismatch.')
    for name,local in ((PD_RAW_METADATA,'metadata.json'),(PD_RAW_ZIP,'source_snapshot.zip')):
        if hashlib.sha256(source_bytes[name]).hexdigest()!=raw_records[local] or len(source_bytes[name])!=files['raw/'+local]['bytes']: raise ValueError('PD raw identity byte mismatch.')
    metadata=parse_json(source_bytes[PD_RAW_METADATA])
    if (any(not strict_equal(metadata.get(k),v) for k,v in PD_METADATA.items()) or not strict_equal(metadata.get('environment_config'),ENVIRONMENT)
        or not strict_equal(metadata.get('protocol'),protocol) or metadata.get('source_snapshot_sha256')!=raw_records['source_snapshot.zip']): raise ValueError('PD original metadata scope mismatch.')
    hashes=metadata.get('source_sha256');members={}
    if type(hashes) is not dict: raise ValueError('PD original source member hashes required.')
    with zipfile.ZipFile(io.BytesIO(source_bytes[PD_RAW_ZIP])) as archive:
        names=archive.namelist()
        if len(names)!=len(set(names)) or set(names)!=set(hashes): raise ValueError('PD original source ZIP coverage mismatch.')
        for name in names: _path(name);_hash(hashes[name])
        for name in (PD_PROTOCOL,'scripts/audit_pair_pd.py','scripts/audit_local_frozen.py'):
            value=hashlib.sha256(archive.read(name)).hexdigest()
            if value!=hashes[name]: raise ValueError('PD required source member hash mismatch.')
            members[name]=value
    if members[PD_PROTOCOL]!=protocol['sha256'] or not strict_equal(audit.get('audit_sources_sha256'),{'auditor':members['scripts/audit_pair_pd.py'],'common':members['scripts/audit_local_frozen.py']}): raise ValueError('PD validated auditor source identity mismatch.')
    return {'schema':'c4-pd-source-binding-v1','status':'selected','selected_id':index,'joint_indices':[0,1],
        'kp':selected['kp'],'kd':selected['kd'],'selection_path':PD_SELECTION,
        'selection_sha256':hashlib.sha256(source_bytes[PD_SELECTION]).hexdigest(),
        'selection_tracking_evidence':'caller_verified_tracked_paths','sources':sources,
        'source_records':{name:hashlib.sha256(source_bytes[name]).hexdigest() for name in PD_SOURCE_FILES},
        'protocol':protocol,'archive_member_records':members,'audit_selection_confirmed':True,'audit_reexecuted':False,
        'raw_trace_or_episodes_read':False,'remaining_original_bytes':'not reread; manifest hashes matched existing independent audit input_hashes'}

def verify_pd_binding(path,metadata,checks,spec):
    binding=metadata.get('pd_binding')
    if spec.synthetic_fixture and not set(PD_SOURCE_FILES).issubset(metadata['source_sha256']):
        if type(binding) is not dict or binding.get('status')!='selected' or type(binding.get('selected_id')) is not int or not 0<=binding['selected_id']<9: raise ValueError('Explicit synthetic PD identity required.')
        checks.compare(metadata['pd_gains'],{'kp':list(binding['kp']),'kd':list(binding['kd'])},'synthetic_pd_gains')
        checks.compare(metadata['pd_gains'],{'kp':[64.,64.],'kd':KD_CANDIDATES[binding['selected_id']]},'synthetic_pd_grid_identity')
        return
    with zipfile.ZipFile(path/'source_snapshot.zip') as archive:
        blobs={name:archive.read(name) for name in (*PD_SOURCE_FILES,PD_PROTOCOL)}
    reconstructed=reconstruct_pd_binding(blobs)
    checks.check(strict_equal(binding,reconstructed),'independent_pd_binding_exact_identity')
    checks.compare(metadata['pd_gains'],{'kp':reconstructed['kp'],'kd':reconstructed['kd']},'validated_pd_source_gains')

def empty_meter(): return {key:0 for key in PLANNING_KEYS}
def meter_record(values):
    unknown=values['unknown_scalar_failure_count']>0
    return {**values,'scalar_counts_complete':not unknown,'scalar_counts_is_lower_bound':unknown}
def validate_meter(saved,checks,location,cap):
    for key in PLANNING_KEYS: checks.check(type(saved.get(key)) is int and 0<=saved[key]<=2*cap,'nonnegative_prediction_count',location+'/'+key)
    a,s=saved['pair_prediction_attempts'],saved['pair_prediction_successes']
    checks.check(a<=cap and s<=a and saved['failed_pair_prediction_attempts']==a-s,'pair_prediction_partition',location)
    checks.check(saved['scalar_prediction_successes']<=saved['scalar_prediction_attempts']<=2*a
        and saved['scalar_prediction_successes']>=2*s,'scalar_prediction_count_bounds',location)
    unknown=saved['unknown_scalar_failure_count']>0
    checks.compare(saved['scalar_counts_complete'],not unknown,location+'/complete')
    checks.compare(saved['scalar_counts_is_lower_bound'],unknown,location+'/lower_bound')

def verify_diagnostic_accounting(ev,regular,exceptions,kind,checks,tid,prefix):
    expected=empty_meter()
    for row in regular:
        if row['step_index']>=prefix and kind!='calibration':
            count=sum(name!='persistence' for name in row['predicted_next_qv'])
            expected['pair_prediction_attempts']+=count;expected['pair_prediction_successes']+=count
            expected['scalar_prediction_attempts']+=2*count;expected['scalar_prediction_successes']+=2*count
    saved=ev['diagnostic_prediction_accounting'];cap=400 if kind=='prediction' else 200 if kind in MPC_KINDS else 0
    validate_meter(saved,checks,tid+'/diagnostic_prediction_meter',cap)
    if not exceptions:
        checks.compare(saved,meter_record(expected),tid+'/diagnostic_exact_call_cost')
        return
    checks.compare(exceptions[0].get('diagnostic_prediction_accounting'),saved,tid+'/exception_diagnostic_meter')
    ex=exceptions[0];duplicate=any(r['shared_transition_id']==ex['shared_transition_id'] for r in regular)
    if not duplicate and kind!='calibration' and ex.get('step_index') is not None and ex['step_index']>=prefix:
        count=sum(name!='persistence' for name in ex.get('predicted_next_qv',{}))
        for key in ('pair_prediction_attempts','pair_prediction_successes'): expected[key]+=count
        for key in ('scalar_prediction_attempts','scalar_prediction_successes'): expected[key]+=2*count
        failed=ex.get('failure_accounting',{}).get('pair_prediction_accounting')
        structured=ex.get('failure_accounting',{}).get('structured_failure')
        if failed is None and type(structured) is dict and structured.get('type')=='PairPredictionError':
            _exact(structured,{'type','message','scalar_prediction_attempts','scalar_prediction_successes','failure_stage'})
            stages={'native_features':(0,0),'velocity_output_0':(1,0),'velocity_output_1':(2,1),'endpoint_euler':(2,2)}
            counts=(structured['scalar_prediction_attempts'],structured['scalar_prediction_successes'])
            if (structured['failure_stage'] not in stages or any(type(x) is not int for x in counts)
                or counts!=stages[structured['failure_stage']] or type(structured['message']) is not str):
                raise ValueError('Exact known PairPredictionError stage/head accounting required.')
            failed=structured
        if failed is not None:
            expected['pair_prediction_attempts']+=1;expected['failed_pair_prediction_attempts']+=1
            for key in ('scalar_prediction_attempts','scalar_prediction_successes'): expected[key]+=failed[key]
    # An arbitrary callback error may not carry head-level accounting. The
    # wrapper must retain one failed pair attempt and mark scalar lower bounds.
    if saved['pair_prediction_attempts']>expected['pair_prediction_attempts']:
        checks.check(saved['pair_prediction_attempts']==expected['pair_prediction_attempts']+1 and saved['unknown_scalar_failure_count']==1,
            'single_explicit_unknown_diagnostic_failure',tid)
        expected['pair_prediction_attempts']+=1;expected['failed_pair_prediction_attempts']+=1;expected['unknown_scalar_failure_count']=1
    checks.compare(saved,meter_record(expected),tid+'/retained_diagnostic_call_cost')

def verify_rls_accounting(sr,regular,exceptions,states,checks,tid,prefix):
    for name in LEARNED:
        if name not in states:
            checks.check(name not in sr['rls_prediction_accounting'],'uncreated_rls_has_no_calls',tid+'/'+name);continue
        saved=sr['rls_prediction_accounting'][name];validate_meter(saved,checks,tid+'/rls/'+name,400)
        if not exceptions:
            count=states[name]['count'];expected=empty_meter()
            expected.update(pair_prediction_attempts=count,pair_prediction_successes=count,
                scalar_prediction_attempts=2*count,scalar_prediction_successes=2*count)
            checks.compare(saved,meter_record(expected),tid+'/rls_exact_internal_cost/'+name)
        else:
            checks.compare(exceptions[0].get('rls_prediction_accounting',{}).get(name),saved,tid+'/exception_rls_meter/'+name)
            complete_rows=sum(r['step_index']>=prefix and r['diagnostics']['executed_substeps']==10 for r in regular)
            committed=states[name]['count']
            checks.check(complete_rows<=committed<=complete_rows+1,'rls_saved_atomic_update_cost',tid+'/'+name)
            checks.check(committed<=saved['pair_prediction_successes']<=complete_rows+1
                and complete_rows<=saved['pair_prediction_attempts']<=complete_rows+1,'rls_successes_cover_atomic_commits',tid+'/'+name)

def complete(ev): return pair_support.complete(ev)
def complete_trials(seeds,kinds,spec=PRODUCTION_SPEC): return pair_support.complete_trials(seeds,kinds,spec)
def improvement(new,old): return None if old==0 else 1.-new/old

def contribution_gate(seeds,basis,spec=PRODUCTION_SPEC):
    if basis not in ('raw','guard'): raise ValueError('Fixed basis required.')
    nominal,learned='nominal_'+basis,'learned_'+basis
    required=('calibration','prediction',nominal,learned)
    eligible=complete_trials(seeds,required,spec);rows=[]
    for sr in seeds:
        ev=sr.get('evaluations',{});n,l=ev.get(nominal,{}),ev.get(learned,{})
        a,b=n.get('tracking_rmse_rad'),l.get('tracking_rmse_rad')
        ax,bx=n.get('tracking_rmse_by_axis_rad'),l.get('tracking_rmse_by_axis_rad')
        metrics=ev.get('prediction',{}).get('velocity_prediction_rmse',{})
        pn,pl=metrics.get(nominal),metrics.get(learned)
        available=all(type(vals) is list and len(vals)==2 and all(finite(x) and x>=0 for x in vals) for vals in (ax,bx,pn,pl))
        valid=eligible and available and all(finite(x) and x>=0 for x in (a,b))
        rows.append({'seed':sr['seed'],'eligible':bool(valid),'nominal_tracking':a,'learned_tracking':b,
            'nominal_axis_tracking':ax,'learned_axis_tracking':bx,'nominal_velocity_prediction':pn,
            'learned_velocity_prediction':pl,'prediction_axes_passed':[valid and pl[i]<=.8*pn[i] for i in range(2)],
            'strict_joint_tracking':valid and b<a,'strict_axis_tracking':[valid and bx[i]<ax[i] for i in range(2)]})
    evaluated=eligible and all(r['eligible'] for r in rows)
    na=sum(r['nominal_tracking'] for r in rows)/3 if evaluated else None
    lb=sum(r['learned_tracking'] for r in rows)/3 if evaluated else None
    imp=improvement(lb,na) if evaluated else None;axis=[]
    for i in range(2):
        a=sum(r['nominal_axis_tracking'][i] for r in rows)/3 if evaluated else None
        b=sum(r['learned_axis_tracking'][i] for r in rows)/3 if evaluated else None
        change=improvement(b,a) if evaluated else None
        axis.append({'axis':i,'nominal_raw_mean':a,'learned_raw_mean':b,'improvement':change,
            'passed':evaluated and change is not None and change>=.20 and all(r['strict_axis_tracking'][i] for r in rows)})
    passed=(evaluated and imp is not None and imp>=.20 and all(g['passed'] for g in axis)
        and all(r['strict_joint_tracking'] and all(r['prediction_axes_passed']) for r in rows))
    return {'basis':basis,'evaluated':evaluated,'passed':bool(passed),'required_trials':list(required),
        'required_trials_complete':eligible,'per_seed':rows,'nominal_raw_tracking_mean':na,'learned_raw_tracking_mean':lb,
        'joint_tracking_mean_improvement':imp,'axis_tracking_gates':axis,
        'prediction_boundary':'One new 1/9 development trajectory; not a reproduction of prior low/full gates.'}

def pd_comparison_gate(seeds,basis,contribution=None,spec=PRODUCTION_SPEC):
    contribution=contribution_gate(seeds,basis,spec) if contribution is None else contribution
    name='learned_'+basis;required=('calibration','prediction','nominal_'+basis,name,'PDselected')
    eligible=complete_trials(seeds,required,spec);rows=[]
    for sr in seeds:
        ev=sr.get('evaluations',{});pd,l=ev.get('PDselected',{}),ev.get(name,{})
        a,b=pd.get('tracking_rmse_rad'),l.get('tracking_rmse_rad')
        ax,bx=pd.get('tracking_rmse_by_axis_rad'),l.get('tracking_rmse_by_axis_rad')
        available=all(type(x) is list and len(x)==2 and all(finite(z) and z>=0 for z in x) for x in (ax,bx))
        valid=eligible and available and all(finite(x) and x>=0 for x in (a,b));efforts={}
        for key in EFFORT_KEYS[2:]:
            av,bv=pd.get('control_effort',{}).get(key),l.get('control_effort',{}).get(key)
            okay=(pd.get('actual_effort_complete') is True and l.get('actual_effort_complete') is True
                and all(type(vals) is list and len(vals)==2 and all(finite(z) and z>=0 for z in vals) for vals in (av,bv)))
            valid=valid and okay;efforts[key]={'pd':sum(av) if okay else None,'learned':sum(bv) if okay else None}
        rows.append({'seed':sr['seed'],'eligible':bool(valid),'pd_tracking':a,'learned_tracking':b,
            'tracking_non_worse':valid and b<=a,'axis_tracking_non_worse':[valid and bx[i]<=ax[i] for i in range(2)],'efforts':efforts})
    evaluated=eligible and all(r['eligible'] for r in rows)
    a=sum(r['pd_tracking'] for r in rows)/3 if evaluated else None
    b=sum(r['learned_tracking'] for r in rows)/3 if evaluated else None
    change=improvement(b,a) if evaluated else None;effort_gates={}
    for key in EFFORT_KEYS[2:]:
        x=sum(r['efforts'][key]['pd'] for r in rows)/3 if evaluated else None
        y=sum(r['efforts'][key]['learned'] for r in rows)/3 if evaluated else None
        effort_gates[key]={'pd_mean':x,'learned_mean':y,'passed':evaluated and (y==0 if x==0 else y<=1.05*x)}
    passed=(contribution['passed'] and evaluated and change is not None and change>=.05
        and all(r['tracking_non_worse'] and all(r['axis_tracking_non_worse']) for r in rows)
        and all(g['passed'] for g in effort_gates.values()))
    return {'basis':basis,'evaluated':evaluated,'passed':bool(passed),'model_contribution_passed':contribution['passed'],
        'required_trials':list(required),'required_trials_complete':eligible,'per_seed':rows,
        'pd_raw_tracking_mean':a,'learned_raw_tracking_mean':b,'joint_tracking_mean_improvement':change,'actual_effort_gates':effort_gates}

def public_rule_diagnostic(seeds,spec=PRODUCTION_SPEC):
    eligible=complete_trials(seeds,NOMINAL,spec);rows=[]
    for sr in seeds:
        ev=sr.get('evaluations',{});a=ev.get('nominal_raw',{});b=ev.get('nominal_guard',{})
        x,y=a.get('tracking_rmse_rad'),b.get('tracking_rmse_rad')
        valid=eligible and all(finite(z) and z>=0 for z in (x,y))
        rows.append({'seed':sr['seed'],'available':bool(valid),'nominal_raw_tracking':x,'nominal_guard_tracking':y,
            'guard_relative_improvement':improvement(y,x) if valid else None})
    return {'available':eligible and all(r['available'] for r in rows),'per_seed':rows,
        'learning_updates_compared':0,'claim_boundary':'Public-rule-only nominal comparison; raw-to-guard total difference is not RLS learning contribution.'}

def scientific_gates(seeds,spec=PRODUCTION_SPEC):
    contribution={basis:contribution_gate(seeds,basis,spec) for basis in ('raw','guard')}
    return {'model_contribution':contribution,'selected_pd_comparison':{basis:pd_comparison_gate(seeds,basis,contribution[basis],spec) for basis in ('raw','guard')},
        'public_rule_diagnostic':public_rule_diagnostic(seeds,spec),'complete_matrix':complete_trials(seeds,KINDS,spec),
        'thresholds_frozen':spec.scientific_gates_frozen,
        'claim_boundary':'Development-only local shoulder/elbow contribution; no independent final generalization, adaptation, maturation, safety or motor-skill success.'}

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

def conditional_rollouts(rows,states,qref,horizons=(2,5,15),*,prefix_steps=100,active_steps=200):
    regular={r['step_index']:r for r in rows if 'collector_exception' not in r}
    exception_indices={r.get('step_index') for r in rows if 'collector_exception' in r}
    result={}
    for name,state in [*states.items(),('persistence',None)]:
        output={}
        for horizon in horizons:
            endpoint_q,endpoint_v,path_q,path_v=[],[],[],[];excluded=Counter();terminal=0
            planned=max(active_steps-horizon+1,0)
            for start in range(prefix_steps,prefix_steps+planned):
                window=[regular.get(i) for i in range(start,start+horizon)]
                if any(i in exception_indices for i in range(start,start+horizon)):
                    excluded['collector_exception']+=1;continue
                if any(r is None for r in window): excluded['missing_endpoint']+=1;continue
                if any(r['diagnostics']['executed_substeps']!=10 for r in window): excluded['partial_interval']+=1;continue
                if any(r.get('study_abort') is not None or r['diagnostics']['terminated'] for r in window[:-1]):
                    excluded['crosses_terminal']+=1;continue
                if any(window[i-1]['observation_after']!=window[i]['observation_before'] for i in range(1,horizon)):
                    excluded['native_discontinuity']+=1;continue
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
            output[str(horizon)]={'expected_windows_from_planned_active_duration':planned,
                'available_saved_active_starts':sum(i>=prefix_steps for i in regular),'valid_windows':len(endpoint_q),
                'excluded_windows':sum(excluded.values()),'exclusion_reasons':dict(excluded),
                'windows_ending_in_terminal':terminal,'endpoint_q_rmse':paired_rmse(endpoint_q),
                'endpoint_v_rmse':paired_rmse(endpoint_v),'path_q_rmse':paired_rmse(path_q),'path_v_rmse':paired_rmse(path_v)}
        result[name]=output
    return {'models':result,'horizons':list(horizons),'recorded_future_requests_are_offline_labels':True,
        'online_future_information':False,'rule':'Free recursive prediction from one current native endpoint; no future true-state feedback.'}

def state_coverage(calibration_rows,rows,qref):
    return {str(i):common.state_coverage(calibration_rows,rows,qref[i],joint_index=i) for i in range(2)}

def verify_exception_updates(exception,ep,regular,states,qref,checks,location,*,prefix_steps=100):
    snapshots=exception.get('partial_model_snapshots',{})
    if not snapshots: return
    checks.check(set(snapshots)=={'learned_raw','learned_guard'},'exception_exact_model_set',location)
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
        checks.check(shared.get('failed_model') in ('learned_raw','learned_guard'),'known_failed_model',location)
    updated=exception.get('model_update') or {}
    original_counts={name:state['count'] for name,state in states.items()}
    original_parameters={name:{'structure':state['structure'],'theta':[row.copy() for row in state['theta']],
        'covariance':[[row.copy() for row in matrix] for matrix in state['covariance']]} for name,state in states.items()}
    for name in ('learned_raw','learned_guard'):
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

def verify_exception_native_mapping(exception,checks,location):
    endpoint=exception.get('observation_after');qpos,qvel=exception.get('qpos'),exception.get('qvel')
    if qpos is not None: vector(qpos,15)
    if qvel is not None: vector(qvel,14)
    returned=exception.get('returned_step_diagnostics') is not None
    retrieval_error=exception.get('observation_after_retrieval_error')
    if retrieval_error is not None:
        checks.check(type(retrieval_error) is dict and type(retrieval_error.get('type')) is str
            and type(retrieval_error.get('message')) is str,'explicit_native_snapshot_retrieval_failure',location)
    current_snapshot=retrieval_error is None
    if endpoint is not None and qpos is not None and qvel is not None and current_snapshot:
        checks.check(endpoint['joint_position']==qpos[7:] and endpoint['joint_velocity']==qvel[6:],
            'current_exception_native_encoder_mapping',location)
    return {'physical_interval_returned':returned,'native_after_current_failure_snapshot':current_snapshot,
        'native_after_fallback_to_last_confirmed_endpoint':not current_snapshot,
        'qpos_qvel_are_failure_time_snapshot':qpos is not None and qvel is not None,
        'unreturned_snapshot_is_not_a_native_learning_label':not returned}

def verify_exception_paid_counters(exception,ep,checks,location):
    diagnostics=exception.get('diagnostics')
    available=type(diagnostics) is dict and all(key in diagnostics for key in ('step_id','physics_steps','time'))
    if available:
        checks.compare(diagnostics['step_id'],ep['control_steps'],location+'/failure_control_counter')
        checks.compare(diagnostics['physics_steps'],ep['physics_steps'],location+'/failure_physics_counter')
        checks.compare(diagnostics['time'],ep['physics_steps']*PHYSICS_DT,location+'/failure_physical_time')
        if 'terminated' in diagnostics:
            checks.compare(diagnostics['terminated'],ep['environment_terminated'],location+'/failure_environment_stop')
    return {'failure_time_counters_available':available,
        'paid_budget_bound_to_saved_failure_time_counters':available,
        'missing_failure_time_counters_make_remaining_cost_not_independently_reconstructed':not available}

def audit_archive(path,checks,git_root=ROOT,spec=PRODUCTION_SPEC):
    path=Path(path).resolve()
    prefix_steps=spec.prefix_steps
    def trial_duration(kind): return spec.calibration_steps if kind=='calibration' else spec.prediction_steps if kind=='prediction' else spec.control_steps
    metadata=require_pair(path,spec)
    ranges,input_hashes=verify_sources(path,metadata,checks,git_root,spec)
    checks.compare(metadata['protocol'],{'path':spec.protocol,'sha256':metadata['source_sha256'][spec.protocol]},'protocol_byte_binding')
    checks.compare(metadata['environment_config'],ENVIRONMENT,'shared_environment')
    checks.compare(metadata,{'prefix_steps':prefix_steps,'calibration_steps':spec.calibration_steps,'prediction_steps':spec.prediction_steps,'control_steps_per_trial':spec.control_steps,
        'structures':['diagonal_hinge5'],'integration':'endpoint_euler',
        'update_order':['learned_raw','learned_guard'],'gpu':None,'teacher_calls':0,'external_demonstration_samples':0,
        'policy_parameter_updates':0,'gain_updates':0,'gate_updates':0,'planned_episode_count':8*len(spec.seeds),
        'maximum_physics_steps':75000,'maximum_vector_updates':2400,
        'maximum_independent_prediction_pair_calls':1200,'maximum_mpc_prediction_pair_calls':2916000,
        'model_input_bases':dict(STRUCTURES),'guard_recomputed_on_each_predicted_start':True,
        'maximum_control_steps':(8*prefix_steps+spec.calibration_steps+spec.prediction_steps+6*spec.control_steps)*len(spec.seeds),
        'maximum_scalar_updates':4*spec.calibration_steps*len(spec.seeds),'native_joint_count':8},'frozen_metadata')
    checks.check(metadata['control_calls_attempted']<=7500 and metadata['control_steps']<=7500 and metadata['physics_steps']<=75000 and metadata['model_updates']<=4800,'batch_paid_budget_caps')
    checks.compare(metadata['backend'],'synthetic, no physics' if spec.synthetic_fixture else 'MuJoCo CPU','cpu_backend')
    checks.compare(metadata['calibration_block_amplitudes_nm'],list(CAL_AMPLITUDES),'calibration_doses')
    checks.compare(metadata['prediction_block_amplitudes_nm'],list(PRED_AMPLITUDES),'prediction_doses')
    checks.compare(metadata['prediction_block_shapes'],[list(x) for x in PRED_DIRECTIONS],'prediction_shapes')
    verify_pd_binding(path,metadata,checks,spec)
    checks.compare(metadata['update_cost_unit'],'committed scalar next-velocity heads','committed_update_unit')
    checks.compare(metadata['calibration_schedule'],'20 blocks of 20: five shoulder, five elbow, five same-direction, five opposite; 1+/9zero/1-/9zero','frozen_1pulse_schedule')
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
            dependent=kind=='prediction' or kind in LEARNED
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
                  'prediction':spec.prediction_steps if kind=='prediction' else 0,'control':spec.control_steps if kind in CONTROL_KINDS else 0}
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
                phase='prefix' if index<prefix_steps else 'calibration' if kind=='calibration' else 'prediction' if kind=='prediction' else 'control'
                checks.compare(row,{'trial_id':tid,'seed':seed,'kind':kind,'joint_indices':[0,1],
                    'phase':phase,'shared_transition_id':location},location+'/labels')
                checks.check(not study_seen and not environment_seen,'no_rows_after_any_stop',location)
                n=verify_transition(row,previous,counters,ranges,checks,location)
                phase_rows[phase]+=1;phase_physics[phase]+=n;add_effort(effort[phase],row)
                common.record_risk(risk['full'],row,ranges,joint_index=0);common.record_risk(risk[phase],row,ranges,joint_index=0)
                previous=row['observation_after'];environment_seen=row['diagnostics']['terminated']
                if index==prefix_steps:
                    if not states: states.update({name:initial_state(STRUCTURES[name],ranges[:2]) for name in ('nominal_raw','nominal_guard')})
                    for name in NOMINAL:
                        verify_snapshot(sr['nominal_models'][name],states[name],qref,checks,tid+'/nominal/'+name)
                        checks.compare(sr['nominal_models'][name]['trainable'],False,tid+'/nominal_frozen/'+name)
                    if kind=='calibration':
                        states.update({name:initial_state(STRUCTURES[name],ranges[:2]) for name in ('learned_raw','learned_guard')})
                        checks.check(set(sr['initial_models'])=={'learned_raw','learned_guard'},'exact_cold_model_set',tid)
                        for name in ('learned_raw','learned_guard'): verify_snapshot(sr['initial_models'][name],states[name],qref,checks,tid+'/initial/'+name)
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
                elif kind=='prediction': expected_u=prediction_request(kind,active,directions)
                else:
                    target=[qref[i]+directions[i]*(.04 if active<100 else .08) for i in range(2)]
                    checks.check(all(ranges[i][0]+.03<=target[i]<=ranges[i][1]-.03 for i in range(2)),'public_target_interior',location)
                    if kind in MPC_KINDS:
                        name=kind;state=states[name]
                        decision=replay_mpc(state['observed_theta'],state['structure'],qref,q,v,target,previous_u,ranges[:2])
                        checks.compare(row['planner_decision'],decision,location+'/independent_mpc')
                        expected_u=decision['torque'];fallback+=int(decision['fallback'])
                        for key in PLANNING_KEYS: planning[key]+=decision[key]
                    elif kind=='PDselected':
                        raw=[64.*(target[i]-q[i])-metadata['pd_gains']['kd'][i]*v[i] for i in range(2)]
                        expected_u=[max(-.5,min(.5,x)) for x in raw]
                        checks.compare(row['raw_pd_torque_nm'],raw,location+'/raw_combined_pd')
                        checks.compare(row['planner_decision'],None,location+'/pd_no_model_plan')
                    else:
                        expected_u=[0.,0.]
                        checks.compare(row['planner_decision'],None,location+'/zero_no_plan')
                checks.compare(u,expected_u,location+'/fixed_request')
                checks.compare(row['target_q'],target,location+'/current_target')
                if kind!='PDselected': checks.compare(row['raw_pd_torque_nm'],None,location+'/no_pd')
                active_states=({name:states[name] for name in LEARNED} if kind=='calibration' else states if kind=='prediction' else {kind:states[kind]} if kind in MPC_KINDS else {})
                predictions={name:predict(s['observed_theta'],s['structure'],qref,q,v,u) for name,s in active_states.items()} if kind!='calibration' or n==10 else {}
                checks.compare(row['model_input_diagnostics'],{name:describe_input(q,u,s['structure']) for name,s in active_states.items()},location+'/causal_input_projection')
                if kind=='prediction' or kind in MPC_KINDS: predictions['persistence']=([q[i]+DT*v[i] for i in range(2)],v)
                checks.check(set(row['predicted_next_qv'])==set(predictions),'exact_prediction_model_set',location)
                checks.compare(row['predicted_next_qv'],predictions,location+'/preupdate_predictions')
                partial=None if target is None or n==10 else [nq[i]-target[i] for i in range(2)]
                checks.compare(row['partial_interval_target_error_rad'],partial,location+'/partial_target')
                if partial is not None: partial_errors.append({'step_index':index,'target_q':target,'errors_rad':partial,'executed_substeps':n})
                if kind=='calibration':
                    if n==10:
                        checks.check(set(row['model_update'])=={'learned_raw','learned_guard'},'same_two_model_transition',location)
                        for name in ('learned_raw','learned_guard'): replay_update(row['model_update'][name],row,states[name],qref,checks,location+'/'+name)
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
                    states={name:initial_state(STRUCTURES[name],ranges[:2]) for name in STRUCTURES}
                    for name in ('learned_raw','learned_guard'): verify_snapshot(sr['initial_models'][name],states[name],qref,checks,tid+'/exception_initial/'+name)
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
                verify_exception_native_mapping(exception,checks,tid)
                verify_exception_paid_counters(exception,ep,checks,tid)
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
                    state=states[kind]
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
            verify_diagnostic_accounting(ev,regular,exceptions,kind,checks,tid,prefix_steps)
            if ev['planner_spec'] is not None:
                checks.check(kind in MPC_KINDS,'planner_spec_only_mpc',tid)
                checks.compare(ev['planner_spec'],planner_spec(qref,ranges[:2]),tid+'/exact_fixed_planner_spec')
            if is_complete and kind in MPC_KINDS:
                checks.check(ev['planner_spec'] is not None,'complete_mpc_requires_planner_spec',tid)
            if kind=='calibration':
                calibrated=is_complete
                checks.compare(sr['calibration_completed'],calibrated,tid+'/calibrated')
                for name in ('learned_raw','learned_guard'):
                    if name in states:
                        verify_snapshot(sr['calibration_models'][name],states[name],qref,checks,tid+'/saved/'+name)
                        if calibrated:
                            verify_snapshot(sr['learned_models'][name],states[name],qref,checks,tid+'/frozen/'+name)
                            checks.compare(sr['learned_models'][name]['trainable'],False,tid+'/not_trainable/'+name)
                            checks.compare(states[name]['count'],spec.calibration_steps,tid+'/complete_vector_updates/'+name)
                if not calibrated: checks.compare(sr['learned_models'],{},tid+'/no_failed_model_publication')
                verify_rls_accounting(sr,regular,exceptions,states,checks,tid,prefix_steps)
                final_vector=sum(s['count'] for name,s in states.items() if name.startswith('learned_'))
                checks.compare(sr['calibration_vector_updates'],final_vector,tid+'/vector_ledger')
                checks.compare(sr['calibration_scalar_updates'],2*final_vector,tid+'/scalar_ledger')
                total_vector+=final_vector;total_scalar+=2*final_vector
            elif states:
                hashes={name:digest(parameter_record(qref,state,observed=True)) for name,state in states.items()}
                checks.compare(ev['models_before'],hashes,tid+'/frozen_before')
                checks.compare(ev['models_after'],hashes,tid+'/frozen_after')
            checks.check(not ep.get('risk_telemetry_complete',False) or missing_physics==0 and not exceptions,'risk_completeness_not_overclaimed',tid)
            for phase in risk:
                risk[phase]['telemetry_missing_paid_substeps']=missing_physics if phase=='full' else ep['phase_budgets'][phase]['physics_steps']-phase_physics[phase]
                risk[phase]['request_applied_mismatch_count_is_lower_bound']=risk[phase]['telemetry_missing_paid_substeps']>0
                risk[phase]['target_guarded_substeps_by_axis']=risk[phase]['permission_screened_substeps_by_joint'][:2]
                risk[phase]['reconstruction_complete']=risk[phase]['telemetry_missing_paid_substeps']==0
                risk[phase]['risk_semantics']='Substep force/energy/impulse/penetration and request/applied screening; native speed/limit excursion from returned endpoints. Missing telemetry makes peaks/impulse/counts lower bounds, minimum contact distance an upper bound.'
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
                'complete_score_endpoints':len(tracking),'partial_score_endpoints':len(partial_errors),
                'exception_native_time_semantics':[verify_exception_native_mapping(ex,checks,tid+'/derived_exception') for ex in exceptions],
                'exception_failure_time_paid_counters':[verify_exception_paid_counters(ex,ep,checks,tid+'/derived_failure_counter') for ex in exceptions]}
            if kind in CONTROL_KINDS and qref is not None:
                derived_ev['target_segments_and_planned_tails']=planned_tail_metrics(regular,qref,directions)
                derived_ev['calibration_support']=state_coverage([r for r in grouped.get(f'seed{seed}_calibration',[]) if 'collector_exception' not in r],regular,qref)
            if states and qref is not None:
                derived_ev['conditional_rollouts']=conditional_rollouts(rows,states,qref,prefix_steps=prefix_steps,active_steps=trial_duration(kind))
                derived_ev['conditional_rollouts']['calibration_in_sample']=kind=='calibration'
                derived_ev['conditional_rollouts']['uses_final_frozen_parameters']=True
            seed_derived[kind]=derived_ev
            if kind=='calibration' and not calibrated:
                states={name:state for name,state in states.items() if name.startswith('nominal_')}
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


def audit(path,*,git_root=ROOT,spec=PRODUCTION_SPEC):
    wall,cpu=time.perf_counter(),time.process_time();checks=Checks();result=None;reported=None
    try:
        metadata=require_pair(path,spec)
        reported={k:metadata.get(k) for k in ('control_calls_attempted','control_steps','physics_steps','model_updates','vector_model_updates')}
        result=audit_archive(path,checks,git_root,spec)
    except (OSError,ValueError,KeyError,TypeError,IndexError,AttributeError,OverflowError,zipfile.BadZipFile,ET.ParseError) as exc:
        checks.check(False,'archive_schema_or_read_error',{'type':type(exc).__name__,'message':str(exc)})
    gates=scientific_gates([] if result is None else result['seeds'],spec)
    eligible=checks.failed==0 and git_root is not None and spec.scientific_gates_frozen and not spec.synthetic_fixture
    gates['data_consistency_verified']=checks.failed==0
    for group in ('model_contribution','selected_pd_comparison'):
        for gate in gates[group].values(): gate['validated_pass']=bool(gate['passed'] and eligible)
    return {'schema_version':1,'created_at_utc':datetime.now(timezone.utc).isoformat(),
        'audit_script_sha256':file_hash(__file__),'audit_dependency_sha256':{name:file_hash(ROOT/name) for name in ('scripts/audit_local_frozen.py','scripts/audit_pair_frozen.py')},
        'immutable_scope':spec.record(),'checks':checks.count,'failed':checks.failed,'violations':checks.violations,
        'maximum_recomputation_difference':checks.maximum_difference,'archive':result,'final_gates':gates,
        'reported_paid_budget_if_replay_incomplete':reported,
        'execution':{'wall_seconds':time.perf_counter()-wall,'cpu_seconds':time.process_time()-cpu,
            'timing_scope':'Entry through report assembly, excludes imports and final JSON writing',
            'python':sys.version,'platform':sys.platform if spec.synthetic_fixture else platform.platform(),
            'third_party_dependencies':[],'physical_simulation_calls':0,'model_parameter_updates':0,
            'replayed_updates_are_frozen_log_audits':True,'source_git_verification_enabled':git_root is not None and not spec.synthetic_fixture,
            'reconstructed_scalar_updates':0 if result is None else result['budget']['model_updates'],
            'reconstructed_vector_updates':0 if result is None else result['budget']['vector_model_updates']}}
def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--input',required=True,type=Path);parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    try:
        output=common.validate_output_path(args.output,[args.input]);require_pair(args.input,PRODUCTION_SPEC)
    except (OSError,ValueError,KeyError,TypeError) as exc: parser.error(str(exc))
    report=audit(args.input)
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x',encoding='utf-8',newline='\n') as stream: json.dump(report,stream,ensure_ascii=False,indent=2,allow_nan=False);stream.write('\n')
    print(json.dumps({'report':str(output),'checks':report['checks'],'failed':report['failed'],'gates':report['final_gates']}))
    return 1 if report['failed'] else 0
if __name__=='__main__': raise SystemExit(main())
