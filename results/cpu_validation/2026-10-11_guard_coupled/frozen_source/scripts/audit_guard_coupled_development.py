"""Independent C4 B standard-library replay audit; no simulator or online code.

A has already been paid and audited. This program verifies those exact embedded
bytes and independently replays only B's coupled mathematical operations. It
never executes the A auditor, refits a diagonal model or fabricates missing data.
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
from pathlib import Path
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
guard=_load('_coupled_guard_audit_support',ROOT/'scripts/audit_guard_pair_development.py')
common,pair_support=guard.common,guard.pair_support
Checks,vector,finite=common.Checks,common.vector,common.finite
digest,file_hash,rmse=common.digest,common.file_hash,common.rmse
pair,load_json,parse_json=guard.pair,guard.load_json,guard.parse_json
strict_equal=guard.strict_equal
DT,PHYSICS_DT=.02,.002
PHASES=('prefix','control')
MODEL='coupled_guard'
SOURCE='src/developmental_physics/guard_coupled_development.py'
CORE='src/developmental_physics/guard_coupled_pair_model.py'
BINDING='src/developmental_physics/guard_pair_source_binding.py'
AUDITOR='scripts/audit_guard_coupled_development.py'
PROTOCOL='docs/GUARD_COUPLED_DEVELOPMENT_PROTOCOL.md'
SUPPORT=('scripts/audit_local_frozen.py','scripts/audit_pair_frozen.py','scripts/audit_guard_pair_development.py')
A_ROOT='results/cpu_validation/2026-10-11_guard_pair/'
A_MANIFEST=A_ROOT+'manifest.json';A_AUDIT=A_ROOT+'first_audit.json'
A_RAW=('metadata.json','episodes.json','seed_results.json','trace.jsonl.gz','source_snapshot.zip','manifest.json')
A_INPUTS={A_MANIFEST,A_AUDIT}|{A_ROOT+'raw/'+name for name in A_RAW}
SHARED=common.BASE_REQUIRED_SOURCES|{guard.SOURCE,guard.PROTOCOL,*SUPPORT,
    'src/developmental_physics/guard_pair_model.py','src/developmental_physics/local_pair_model.py',
    'src/developmental_physics/pd_selection_binding.py',guard.PD_PROTOCOL}
CURRENT_SHARED={common.ASSET,'pyproject.toml',guard.SOURCE,guard.PROTOCOL,*SUPPORT}|{
    'src/developmental_physics/'+n for n in ('environment.py','collect.py','probes.py','local_model.py','local_pair_model.py','guard_pair_model.py')}
RESET={0:3757552657,1:1641411168,2:2001025171}
PLANNING_KEYS=guard.PLANNING_KEYS
EFFORT_KEYS=common.EFFORT_KEYS

@dataclass(frozen=True)
class CoupledAuditSpec:
    synthetic_fixture: bool=False
    scientific_gates_frozen: bool=True
    def __post_init__(self):
        if (type(self.synthetic_fixture) is not bool or type(self.scientific_gates_frozen) is not bool
                or self.synthetic_fixture is self.scientific_gates_frozen):
            raise ValueError('Exact immutable production or engineering fixture scope required.')
    def record(self):
        return {'suite':'guard_coupled_development','pose':'supine','seeds':[0,1,2],
            'joint_indices':[0,1],'split':'development','collector':SOURCE,'auditor':AUDITOR,'protocol':PROTOCOL,
            'synthetic_fixture':self.synthetic_fixture,'scientific_gates_frozen':self.scientific_gates_frozen,
            'prefix_steps':100,'calibration_reuse_steps':400,'prediction_reuse_steps':100,'control_steps':200,
            'structure':'coupled_hinge9','input_basis':'known_angle_guard','parameters_per_output':9,
            'diagonal_parameters_per_output':5,'prediction_velocity_ratio_max':.8,
            'own_tracking_mean_improvement_min':.20,'comparison_joint_mean_improvement_min':.05,
            'actual_effort_ratio_max':1.05,'A_scientific_contribution_run_dependency':False}
PRODUCTION_SPEC=CoupledAuditSpec()
SYNTHETIC_SPEC=CoupledAuditSpec(synthetic_fixture=True,scientific_gates_frozen=False)

def sha(blob): return hashlib.sha256(blob).hexdigest()
def _assert(ok,label):
    if not ok: raise ValueError(label)
def _equal(actual,expected,label): _assert(strict_equal(actual,expected),label)
def _maps(items,key,expected,label):
    _assert(type(items) is list,label+' array required')
    result={}
    for item in items:
        value=item[key]
        _assert(type(value) is type(next(iter(expected))) and value in expected and value not in result,label+' identity')
        result[value]=item
    _assert(set(result)==set(expected),label+' complete coverage')
    return result
def read_rows(blob):
    return [parse_json(line) for line in gzip.decompress(blob).decode('utf-8').splitlines() if line]
def source_members(blob):
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        names=z.namelist()
        _assert(len(names)==len(set(names)),'Duplicate source ZIP member')
        for name in names: guard._path(name)
        return {name:z.read(name) for name in names}
def public_ranges(blob):
    xml=ET.fromstring(blob);compiler=xml.find('compiler')
    factor=math.pi/180. if compiler is None or compiler.get('angle','degree')=='degree' else 1.
    entries={}
    for joint in xml.findall('.//joint'):
        name=joint.get('name')
        if name in common.JOINTS:
            _assert(name not in entries,'Duplicate asset joint')
            value=[float(x)*factor for x in joint.get('range','').split()]
            pair(value);_assert(value[0]<value[1],'Ordered asset range required');entries[name]=value
    _assert(all(n in entries for n in common.JOINTS),'Eight asset joint ranges required')
    return [entries[n] for n in common.JOINTS]

def verify_sources(path,metadata,checks,git_root,spec):
    manifest=load_json(path/'manifest.json')
    names={p.name for p in path.iterdir() if p.is_file() and p.name!='manifest.json'}
    checks.check(set(manifest)==names,'manifest_exact_coverage')
    checks.check({'metadata.json','episodes.json','seed_results.json','trace.jsonl.gz','source_snapshot.zip',
        'calibration_replay.jsonl.gz','prediction_replay.jsonl.gz'}.issubset(manifest),'manifest_core_files')
    for name,value in manifest.items():
        _assert(guard._path(name)==Path(name).name,'Local manifest name required')
        checks.check(file_hash(path/name)==guard._hash(value),'manifest_hash',name)
    commit=metadata.get('source_commit');valid=type(commit) is str and re.fullmatch('[0-9a-f]{40}',commit) is not None
    checks.check(metadata.get('source_status')=='' and metadata.get('source_dirty') is False,'clean_source')
    checks.check(commit=='synthetic-fixture-no-git' if spec.synthetic_fixture else valid,'source_commit')
    hashes=metadata['source_sha256'];members=source_members((path/'source_snapshot.zip').read_bytes())
    checks.check(set(members)==set(hashes),'unique_exact_source_zip_coverage')
    required=SHARED|{SOURCE,CORE,BINDING,AUDITOR,PROTOCOL}|A_INPUTS
    checks.check(required.issubset(hashes),'required_source_coverage')
    checks.compare(metadata['source_snapshot_sha256'],file_hash(path/'source_snapshot.zip'),'source_zip_hash')
    for name,value in hashes.items():
        guard._path(name);guard._hash(value)
        checks.check(sha(members[name])==value,'source_hash',name)
        if git_root is not None and not spec.synthetic_fixture and valid:
            response=subprocess.run(['git','show',f'{commit}:{name}'],cwd=git_root,capture_output=True,check=False)
            checks.check(response.returncode==0 and response.stdout==members[name],'source_git_blob_bytes',name)
    checks.compare(metadata['protocol'],{'path':PROTOCOL,'sha256':hashes[PROTOCOL]},'protocol_identity')
    if not spec.synthetic_fixture:
        checks.compare(metadata['independent_auditor'],{'path':AUDITOR,'sha256':file_hash(__file__),
            'pending':False,'required_for_formal':True},'executing_auditor_identity')
        checks.check(members[AUDITOR]==Path(__file__).read_bytes(),'executing_auditor_matches_archive')
        for name in SUPPORT: checks.check(members[name]==(ROOT/name).read_bytes(),'support_matches_archive',name)
        if git_root is not None and valid:
            tree=subprocess.run(['git','ls-tree','-r','--name-only',commit,'src/developmental_physics'],cwd=git_root,capture_output=True,text=True,check=False)
            py={n for n in tree.stdout.splitlines() if n.endswith('.py') and n.count('/')==2}
            checks.check(tree.returncode==0 and py.issubset(hashes),'all_physics_sources_archived')
    return members,public_ranges(members[common.ASSET]),{**manifest,'manifest.json':file_hash(path/'manifest.json')}

def reconstruct_a(members,metadata,spec):
    """Independent source identity reconstruction, never execute the A auditor."""
    _assert(A_INPUTS.issubset(members),'Embedded A inputs required')
    manifest,audit=parse_json(members[A_MANIFEST]),parse_json(members[A_AUDIT])
    files=manifest['files'];raw={};hashes={}
    for name,record in files.items():
        guard._path(name);guard._exact(record,{'kind','source','bytes','sha256'});guard._hash(record['sha256'])
        _assert(type(record['bytes']) is int and record['bytes']>=0,'Outer A file byte count')
        if name.startswith('raw/'):
            _assert(name[4:] in A_RAW and '/' not in name[4:],'Exact A raw names')
            blob=members[A_ROOT+name];raw[name[4:]]=blob;hashes[name[4:]]=sha(blob)
            _assert(len(blob)==record['bytes'] and sha(blob)==record['sha256'],'A outer raw original bytes')
    _assert(set(raw)==set(A_RAW),'Exact six A raw inputs')
    record=files['first_audit.json']
    _assert(len(members[A_AUDIT])==record['bytes'] and sha(members[A_AUDIT])==record['sha256'],'A first audit bytes')
    a_spec=guard.SYNTHETIC_SPEC if spec.synthetic_fixture else guard.PRODUCTION_SPEC
    _equal(audit['immutable_scope'],a_spec.record(),'A immutable scope')
    _assert(type(audit['failed']) is int and audit['failed']==0 and audit['violations']==[],'A independent audit zero data failures')
    _assert(audit['final_gates']['data_consistency_verified'] is True,'A verified data required')
    _assert(audit['execution']['source_git_verification_enabled'] is (not spec.synthetic_fixture),'A Git verification scope')
    _equal(audit['archive']['input_hashes'],hashes,'A audit exact input hashes')
    _equal(parse_json(raw['manifest.json']),{k:v for k,v in hashes.items() if k!='manifest.json'},'A raw manifest')
    am=parse_json(raw['metadata.json'])
    expected={'suite':'guard_pair_development','synthetic':spec.synthetic_fixture,'seeds':[0,1,2],
        'split':'development','pose':'supine','joint_indices':[0,1],'native_joint_count':8,
        'prefix_steps':100,'calibration_steps':400,'prediction_steps':100,'control_steps_per_trial':200,
        'source_status':'','source_dirty':False,'gpu':None}
    for key,value in expected.items(): _equal(am.get(key),value,'A metadata scope '+key)
    if not spec.synthetic_fixture:
        _assert(type(am['source_commit']) is str and re.fullmatch('[0-9a-f]{40}',am['source_commit']) is not None,'A clean commit')
        _equal(am.get('backend'),'MuJoCo CPU','A CPU backend')
    runtime={key:metadata[key] for key in ('environment_config','dependencies','mujoco_version')}
    for key,value in runtime.items(): _equal(am.get(key),value,'A runtime '+key)
    src=source_members(raw['source_snapshot.zip'])
    _equal(set(src)==set(am['source_sha256']),True,'A source ZIP exact metadata coverage')
    required=SHARED|(set() if spec.synthetic_fixture else set(guard.PD_SOURCE_FILES))
    _assert(required.issubset(src),'A source coverage')
    for name,blob in src.items():
        _assert(sha(blob)==guard._hash(am['source_sha256'][name]),'A source hash')
        _assert(members.get(name)==blob,'Embedded A source identity '+name)
    for name in CURRENT_SHARED: _assert(name in src and members[name]==src[name],'Public A/B source identity')
    _equal(am['source_snapshot_sha256'],sha(raw['source_snapshot.zip']),'A ZIP SHA identity')
    _equal(am['protocol'],{'path':guard.PROTOCOL,'sha256':am['source_sha256'][guard.PROTOCOL]},'A protocol identity')
    _equal(am['independent_auditor'],{'path':guard.AUDITOR,'sha256':am['source_sha256'][guard.AUDITOR],
        'pending':spec.synthetic_fixture,'required_for_formal':True},'A executing auditor identity')
    _equal(audit['audit_script_sha256'],am['source_sha256'][guard.AUDITOR],'A audit script bytes')
    _equal(audit['audit_dependency_sha256'],{n:am['source_sha256'][n] for n in SUPPORT[:2]},'A audit dependency bytes')
    ranges=public_ranges(src[common.ASSET])[:2]
    saved=_maps(parse_json(raw['seed_results.json']),'seed',RESET,'A saved seeds')
    derived=_maps(audit['archive']['seeds'],'seed',RESET,'A audited seeds')
    episode_ids={f'seed{s}_{k}' for s in RESET for k in guard.KINDS}
    episodes=_maps(parse_json(raw['episodes.json']),'trial_id',episode_ids,'A episodes')
    rows={};ids=set()
    for row in read_rows(raw['trace.jsonl.gz']):
        seed,kind,index=row['seed'],row['kind'],row.get('step_index')
        _assert(type(seed) is int and seed in RESET and kind in guard.KINDS and row['trial_id']==f'seed{seed}_{kind}','A row identity')
        if 'collector_exception' in row: continue
        _assert(type(index) is int and 0<=index<100+guard.duration(kind),'A index')
        identity=f'seed{seed}_{kind}:{index}'
        _assert(row['shared_transition_id']==identity and identity not in ids,'A unique transition')
        ids.add(identity);rows.setdefault(row['trial_id'],[]).append(row)
    seeds={}
    for seed in RESET:
        sr=saved[seed];_equal(sr['reset_seed'],RESET[seed],'A reset seed')
        qref=sr.get('reference_q');directions=sr.get('direction')
        if qref is not None:
            pair(qref);_assert(type(directions) is list and len(directions)==2 and all(type(x) is int and x in (-1,1) for x in directions),'A directions')
            _equal(directions,[1 if ranges[i][1]-qref[i]>=qref[i]-ranges[i][0] else -1 for i in range(2)],'A direction rule')
        prefix=None
        for kind in ('calibration','prediction'):
            regular=rows.get(f'seed{seed}_{kind}',[]);stopped=False
            for i,row in enumerate(regular):
                _assert(row['step_index']==i and not stopped,'A contiguous causal source order')
                for field in ('observation_before','observation_after'):
                    vector(row[field]['joint_position'],8);vector(row[field]['joint_velocity'],8)
                if i: _equal(row['observation_before'],regular[i-1]['observation_after'],'A native chain')
                n=row['diagnostics']['executed_substeps'];term=row['diagnostics']['terminated']
                _assert(type(n) is int and 0<=n<=10 and type(term) is bool and (n==10 or term),'A interval completeness')
                vector(row['requested_torque'],8)
                if i<100:
                    _equal(row['phase'],'prefix','A prefix phase');_equal(row['requested_torque'],[0.]*8,'A prefix zeros')
                    _assert(row['model_update'] is None,'A no prefix update')
                else:
                    _equal(row['phase'],kind,'A active phase')
                    command=guard.calibration_request(i-100,directions) if kind=='calibration' else guard.prediction_request(kind,i-100,directions)
                    _equal(row['requested_torque'],command+[0.]*6,'A fixed pulse schedule')
                    if i==100:
                        _equal(row['observation_before']['joint_position'][:2],qref,'A native qref')
                        if kind=='calibration': prefix=row['observation_before']
                    if kind=='prediction': _assert(row['model_update'] is None,'No A evaluation fitting')
                stopped=term or row.get('study_abort') is not None
        cal=rows.get(f'seed{seed}_calibration',[]);ep=episodes[f'seed{seed}_calibration']
        ready=(sr['calibration_completed'] is True and ep['completed'] is True and ep['status']=='completed'
            and len(cal)==500 and all(r['diagnostics']['executed_substeps']==10 and not r['diagnostics']['terminated'] and r.get('study_abort') is None for r in cal))
        _assert(type(sr['calibration_completed']) is bool and (not sr['calibration_completed'] or ready),'A honest calibration completion')
        if ready:
            _equal(sr['calibration_vector_updates'],800,'A two basis vector count');_equal(sr['calibration_scalar_updates'],1600,'A scalar count')
            _assert('learned_guard' in sr.get('learned_models',{}),'A published guard model')
        plant=ep.get('environment_fingerprint_before')
        if plant is not None: guard._hash(plant)
        for other in episodes.values():
            if other['seed']==seed and other.get('environment_fingerprint_before') is not None:
                _equal(other['environment_fingerprint_before'],plant,'A common plant')
                _equal(other.get('environment_fingerprint_after'),plant,'A fixed plant')
        seeds[seed]={'seed':seed,'reset_seed':RESET[seed],'reference_q':qref,'direction':directions,
            'public_joint_ranges':ranges,'environment_fingerprint_before':plant,'native_prefix_observation':prefix,
            'calibration_ready':ready,'calibration_transitions':[r for r in cal if r['step_index']>=100],
            'prediction_transitions':[r for r in rows.get(f'seed{seed}_prediction',[]) if r['step_index']>=100],
            'prediction_episode':episodes[f'seed{seed}_prediction'],'calibration_episode':ep,
            'reused_baselines':{k:sr.get('evaluations',{}).get(k) for k in ('nominal_guard','learned_guard','PDselected','zero')},
            'reused_audit_metrics':{k:derived[seed]['evaluations'].get(k) for k in ('prediction','nominal_guard','learned_guard','PDselected','zero')},
            'A_original_seed_result':sr}
    record={'schema':'c4-a-source-binding-v1','synthetic':spec.synthetic_fixture,'synthetic_fixture':spec.synthetic_fixture,
        'archive_root':A_ROOT,'manifest':{'path':A_MANIFEST,'sha256':sha(members[A_MANIFEST])},
        'audit':{'path':A_AUDIT,'sha256':sha(members[A_AUDIT])},'raw_hashes':hashes,'source_commit':am['source_commit'],
        'source_sha256':am['source_sha256'],'runtime':runtime,'A_paid_budget':audit['archive']['budget'],
        'calibration_ready':{str(s):seeds[s]['calibration_ready'] for s in RESET},'new_physical_calls':0,
        'new_model_updates':0,'scientific_A_contribution_required':False,'source_git_verified_by_binding':False}
    _equal(metadata['a_binding'],record,'B independently reconstructed A binding')
    return seeds,record

def initial_state(ranges):
    state=pair_support.initial_state('coupled_hinge9');state['ranges']=ranges
    return state
def features(qref,q,v,u,ranges):
    mapped=guard.describe_input(q,u,('known_angle_guard',ranges))['model_feature_command_nm']
    return pair_support.features('coupled_hinge9',qref,q,v,mapped)
def parameter_record(qref,state,observed=False):
    record=pair_support.parameter_record(qref,state,observed=observed)
    row=['v0','v1','q0-qref0','q1-qref1','start_G0(q0,u0)','start_G1(q1,u1)',
         'h(start_G0(q0,u0))','h(start_G1(q1,u1))','1']
    record['features_per_output']=[row.copy(),row.copy()]
    record['feature_roles_per_output']=[{'output_index':i,'own_columns':[i,2+i,4+i,6+i],
        'cross_columns':[1-i,3-i,5-i,7-i],'constant_column':8} for i in range(2)]
    record['input_mapping']={'basis':'known_angle_guard','feature_command':'G(current q, original requested u) at control start',
        'public_guard':guard.guard_spec(state['ranges']),'guard_used_by_model':True,
        'recompute':'same causal mapping on every RLS and mathematical prediction call'}
    record['model_definition']={'feature_order_source':'unchanged PairBodyModel coupled_hinge9 global column order',
        'rls_source':'unchanged PairBodyModel atomic two-head update','guard_source':'KnownAngleGuard public control-start rule',
        'own_prior':'same [1,0,.02,0] as matching guard diagonal; constant zero',
        'cross_prior':'all four cross coefficients zero for each output','parameter_count_per_output':9,
        'matching_diagonal_parameter_count_per_output':5,'physical_queries':0}
    return record
def verify_snapshot(saved,state,qref,checks,location,trainable=None):
    keys=set(parameter_record(qref,state))|{'parameter_fingerprint','vector_update_count','scalar_update_count',
        'output_update_counts','trainable','initial_prior','input_boundary','update_commit'}
    checks.check(set(saved)==keys,'exact_snapshot_whitelist',location)
    checks.compare(saved,parameter_record(qref,state),location+'/parameters')
    checks.compare(saved,{'vector_update_count':state['count'],'scalar_update_count':2*state['count'],
        'output_update_counts':[state['count']]*2,'update_commit':'single immutable state reference for both outputs, covariance and counts',
        'initial_prior':'generic velocity continuity and torque response; zero cross coefficients',
        'input_boundary':'current native q/v and already known requested u; no actual future torque or simulator state'},location+'/atomic')
    checks.compare(saved['parameter_fingerprint'],digest({k:saved[k] for k in parameter_record(qref,state)}),location+'/raw_hash')
    if trainable is not None: checks.compare(saved['trainable'],trainable,location+'/trainable')
    state['observed_theta'],state['observed_covariance']=saved['coefficients'],saved['covariance']
def predict(theta,ranges,qref,q,v,u):
    try: x=features(qref,q,v,u,ranges)
    except ValueError as exc: raise pair_support.PredictionError(0,0) from exc
    if len(theta)!=2 or any(len(row)!=9 or not all(finite(t) for t in row) for row in theta):
        raise ValueError('Finite 9D two-head coefficients required')
    nv=[]
    for i in range(2):
        value=sum(t*f for t,f in zip(theta[i],x[i]))
        if not finite(value): raise pair_support.PredictionError(i+1,i)
        nv.append(value)
    nq=[q[i]+DT*nv[i] for i in range(2)]
    if not all(finite(x) for x in nq): raise pair_support.PredictionError(2,2)
    return nq,nv
def replay_update(saved,source,state,qref,checks,location):
    q,v=[source['observation_before'][k][:2] for k in ('joint_position','joint_velocity')]
    u=source['requested_torque'][:2];labels=source['observation_after']['joint_velocity'][:2]
    x=features(qref,q,v,u,state['ranges'])
    proposals=[pair_support.replay_rls(state['theta'][i],state['covariance'][i],x[i],labels[i]) for i in range(2)]
    pq,pv=predict(state['observed_theta'],state['ranges'],qref,q,v,u)
    checks.compare(saved,{'phase':'identification','updated':True,'shared_transition_id':source['shared_transition_id'],
        'features_per_output':x,'preupdate_prediction':{'next_q_rad':pq,'next_v_rad_s':pv},
        'observed_next_v_rad_s':labels,'parameter_fingerprint_before':digest(parameter_record(qref,state,True)),
        'vector_update_count':state['count']+1,'scalar_update_count':2*(state['count']+1),'committed_scalar_updates':2},location+'/causality')
    checks.check(len(saved['output_records'])==2,'atomic_two_head_proposals',location)
    for i,(theta,cov,residual) in enumerate(proposals):
        checks.compare(saved['output_records'][i],{'output_index':i,'features':x[i],'observed_next_v_rad_s':labels[i],
            'preupdate_error_rad_s':residual,'proposed_coefficients':theta,'proposed_covariance':cov,'committed':True},location+f'/head{i}')
    state['theta']=[p[0] for p in proposals];state['covariance']=[p[1] for p in proposals];state['count']+=1
    state['observed_theta']=[r['proposed_coefficients'] for r in saved['output_records']]
    state['observed_covariance']=[r['proposed_covariance'] for r in saved['output_records']]
    checks.compare(saved['parameter_fingerprint_after'],digest(parameter_record(qref,state,True)),location+'/after_hash')


def replay_mpc(theta,ranges,qref,q,v,target,previous,limits):
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
            try: pq,pv=predict(theta,ranges,qref,pq,pv,list(torque))
            except pair_support.PredictionError as exc:
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

def successful_meter(count):
    values=guard.empty_meter()
    values.update(pair_prediction_attempts=count,pair_prediction_successes=count,
        scalar_prediction_attempts=2*count,scalar_prediction_successes=2*count)
    return guard.meter_record(values)

def failed_meter(base,failure,checks,location):
    """Retain a single paid prediction failure; never infer missing heads as zero."""
    values={k:base[k] for k in PLANNING_KEYS}
    record=failure.get('pair_prediction_accounting')
    structured=failure.get('structured_failure')
    if record is None and type(structured) is dict and structured.get('type')=='PairPredictionError':
        guard._exact(structured,{'type','message','scalar_prediction_attempts','scalar_prediction_successes','failure_stage'})
        stage={'native_features':(0,0),'velocity_output_0':(1,0),'velocity_output_1':(2,1),'endpoint_euler':(2,2)}
        counts=(structured['scalar_prediction_attempts'],structured['scalar_prediction_successes'])
        _assert(all(type(x) is int for x in counts) and stage.get(structured['failure_stage'])==counts,'Known prediction failure stage/head counts')
        record=structured
    values['pair_prediction_attempts']+=1;values['failed_pair_prediction_attempts']+=1
    if record is None: values['unknown_scalar_failure_count']+=1
    else:
        a,s=record['scalar_prediction_attempts'],record['scalar_prediction_successes']
        checks.check(type(a) is int and type(s) is int and 0<=s<=a<=2,'failed_head_bounds',location)
        values['scalar_prediction_attempts']+=a;values['scalar_prediction_successes']+=s
    return guard.meter_record(values)

def audit_calibration(source,sr,rows,checks):
    seed=source['seed'];tid=f'seed{seed}_calibration_replay';record=sr['calibration_replay']
    checks.compare(record,{'new_physical_calls':0,'new_physics_substeps':0,
        'source_trial_id':f'seed{seed}_calibration'},tid+'/reuse')
    regular=[r for r in rows if 'collector_exception' not in r]
    exceptions=[r for r in rows if 'collector_exception' in r]
    checks.check(len(exceptions)<=1 and (not exceptions or rows[-1] is exceptions[0]),'one_final_replay_failure',tid)
    if not source['calibration_ready']:
        checks.check(not rows and record['status']=='blocked' and record['completed'] is False,'A_incomplete_calibration_blocks_without_fit',tid)
        checks.compare(record,{'attempted_vector_updates':0,'committed_vector_updates':0,'committed_scalar_updates':0,
            'model_snapshot':None,'source_transition_ids':[],'rls_prediction_accounting':successful_meter(0)},tid+'/blocked')
        return None,{'eligible':False,'completed':False,'status':'blocked','new_vector_updates':0,'new_scalar_updates':0}
    qref=source['reference_q'];state=initial_state(source['public_joint_ranges'])
    verify_snapshot(record['initial_model'],state,qref,checks,tid+'/cold',True)
    originals={r['shared_transition_id']:r for r in source['calibration_transitions']}
    ids=[]
    for index,row in enumerate(regular):
        source_id=row['source_shared_transition_id'];ids.append(source_id)
        checks.compare(source_id,source['calibration_transitions'][index]['shared_transition_id'],tid+'/source_order')
        original=originals[source_id]
        checks.compare(row,{'seed':seed,'phase':'offline_calibration_replay','new_physical_calls':0,'new_physics_substeps':0,
            'observation_before':original['observation_before'],'requested_torque':original['requested_torque'],
            'source_complete_next_velocity_label':original['observation_after']['joint_velocity'][:2],
            'model_input_diagnostics':guard.describe_input(original['observation_before']['joint_position'][:2],original['requested_torque'][:2],('known_angle_guard',source['public_joint_ranges']))},tid+f'/{index}/causal_binding')
        replay_update(row['model_update'],original,state,qref,checks,tid+f'/{index}/atomic_rls')
        verify_snapshot(row['model_snapshot_after'],state,qref,checks,tid+f'/{index}/published',True)
    attempted=len(regular);meter=successful_meter(attempted)
    if exceptions:
        ex=exceptions[0];source_id=ex['source_shared_transition_id']
        duplicate=source_id in ids
        _assert(source_id in originals,'Failed replay retains source transition ID')
        original=originals[source_id];delta=ex['model_snapshot_after']['vector_update_count']-state['count']
        checks.check(type(delta) is int and delta in (0,1),'failure_atomic_zero_or_two_heads',tid)
        failure=ex.get('failure_accounting',{});update=ex.get('model_update')
        ledger=failure.get('pair_update_accounting')
        if ledger is None and type(failure.get('structured_failure')) is dict and failure['structured_failure'].get('type')=='PairUpdateError':
            ledger=failure['structured_failure']
        if not duplicate:
            checks.compare(source_id,source['calibration_transitions'][len(regular)]['shared_transition_id'],tid+'/failure_next_id')
            ids.append(source_id);attempted+=1
            if delta==1:
                if update is not None: replay_update(update,original,state,qref,checks,tid+'/failure_after_commit')
                else:
                    x=features(qref,original['observation_before']['joint_position'][:2],original['observation_before']['joint_velocity'][:2],original['requested_torque'][:2],state['ranges'])
                    proposals=[pair_support.replay_rls(state['theta'][i],state['covariance'][i],x[i],original['observation_after']['joint_velocity'][i]) for i in range(2)]
                    state['theta']=[p[0] for p in proposals];state['covariance']=[p[1] for p in proposals];state['count']+=1
            elif update is not None: checks.check(update.get('updated') is not True,'no_unpublished_success_record',tid)
            # Update's existing old-state prediction precedes proposal failures.
            if ledger is not None or update is not None or delta==1:
                meter=successful_meter(attempted)
            else:
                saved=record['rls_prediction_accounting']
                if saved['pair_prediction_attempts']==attempted:
                    meter=failed_meter(successful_meter(attempted-1),failure,checks,tid+'/failed_internal_prediction')
                else:
                    checks.compare(saved['pair_prediction_attempts'],attempted-1,tid+'/before_internal_prediction')
        if ledger is not None:
            checks.compare(ledger['committed_scalar_updates'],2*delta,tid+'/ledger_atomic_commit')
            checks.compare(ledger['snapshot_after_attempt'],ex['model_snapshot_after'],tid+'/ledger_snapshot')
            proposals=ledger.get('proposed_outputs',[])
            checks.check(type(proposals) is list and len(proposals)<=2 and (delta==0 or len(proposals)==2),'failure_two_head_proposal_bound',tid)
            # Reconstruct from the last pre-attempt state; every saved proposal
            # is checked separately, even when no model was published.
            pre_state=initial_state(source['public_joint_ranges'])
            for previous in regular:
                pre_state['theta']=previous['model_snapshot_after']['coefficients'];pre_state['covariance']=previous['model_snapshot_after']['covariance']
            if not duplicate:
                x=features(qref,original['observation_before']['joint_position'][:2],original['observation_before']['joint_velocity'][:2],original['requested_torque'][:2],pre_state['ranges'])
                for i,item in enumerate(proposals):
                    theta,cov,residual=pair_support.replay_rls(pre_state['theta'][i],pre_state['covariance'][i],x[i],original['observation_after']['joint_velocity'][i])
                    checks.compare(item,{'output_index':i,'features':x[i],'observed_next_v_rad_s':original['observation_after']['joint_velocity'][i],
                        'preupdate_error_rad_s':residual,'proposed_coefficients':theta,'proposed_covariance':cov,'committed':delta==1},tid+f'/failed_proposal{i}')
        verify_snapshot(ex['model_snapshot_after'],state,qref,checks,tid+'/failure_snapshot',True)
    checks.compare(record['source_transition_ids'],ids,tid+'/exact_source_ids')
    checks.compare(record['attempted_vector_updates'],attempted,tid+'/attempts')
    checks.compare(record['committed_vector_updates'],state['count'],tid+'/vector_commits')
    checks.compare(record['committed_scalar_updates'],2*state['count'],tid+'/scalar_commits')
    guard.validate_meter(record['rls_prediction_accounting'],checks,tid+'/internal_prediction_meter',400)
    checks.compare(record['rls_prediction_accounting'],meter,tid+'/paid_internal_prediction')
    verify_snapshot(record['model_snapshot'],state,qref,checks,tid+'/final_published',True)
    complete=not exceptions and len(regular)==400 and state['count']==400 and record['status']=='completed'
    checks.compare(record['completed'],complete,tid+'/completion')
    if complete:
        verify_snapshot(record['frozen_model'],state,qref,checks,tid+'/frozen',False)
        verify_snapshot(sr['learned_model'],state,qref,checks,tid+'/published_to_control',False)
    else:
        checks.check('learned_model' not in sr,'no_failed_replay_publication',tid)
    return state if complete else None,{'eligible':complete,'completed':complete,'status':record['status'],
        'new_vector_updates':state['count'],'new_scalar_updates':2*state['count'],'rls_prediction_accounting':meter}

def audit_prediction(source,sr,rows,state,checks):
    seed=source['seed'];tid=f'seed{seed}_prediction_replay';record=sr['prediction_replay']
    checks.compare(record,{'new_physical_calls':0,'new_physics_substeps':0,'committed_scalar_updates':0},tid+'/no_new_collect_or_fit')
    if state is None:
        checks.check(not rows and record['status']=='blocked' and record['completed'] is False,'failed_calibration_blocks_prediction',tid)
        return {'eligible':False,'completed':False,'status':'blocked'}
    qref=source['reference_q'];fingerprint=digest(parameter_record(qref,state,True))
    checks.compare(record['source_episode'],source['prediction_episode'],tid+'/preserve_A_outcome')
    checks.compare(record['model_fingerprint_before'],fingerprint,tid+'/frozen_before')
    checks.compare(record['model_fingerprint_after'],fingerprint,tid+'/frozen_after')
    originals=source['prediction_transitions'];regular=[r for r in rows if 'collector_exception' not in r]
    exceptions=[r for r in rows if 'collector_exception' in r]
    checks.check(len(exceptions)<=1 and (not exceptions or rows[-1] is exceptions[0]),'one_final_prediction_failure',tid)
    q_errors=[];v_errors=[];partial=[];ids=[]
    for i,row in enumerate(regular):
        original=originals[i];identity=original['shared_transition_id'];ids.append(identity)
        q,v=[original['observation_before'][k][:2] for k in ('joint_position','joint_velocity')]
        prediction=predict(state['observed_theta'],state['ranges'],qref,q,v,original['requested_torque'][:2])
        nq,nv=[original['observation_after'][k][:2] for k in ('joint_position','joint_velocity')]
        dq=[nq[j]-prediction[0][j] for j in range(2)];dv=[nv[j]-prediction[1][j] for j in range(2)]
        n=original['diagnostics']['executed_substeps'];full=n==10
        checks.compare(row,{'seed':seed,'phase':'offline_prediction_replay','source_shared_transition_id':identity,
            'new_physical_calls':0,'new_physics_substeps':0,'model_updates':0,'observation_before':original['observation_before'],
            'requested_torque':original['requested_torque'],'predicted_next_qv':{MODEL:prediction},
            'model_input_diagnostics':guard.describe_input(q,original['requested_torque'][:2],('known_angle_guard',state['ranges'])),
            'source_observation_after_for_score_only':original['observation_after'],'source_executed_substeps':n,
            'complete_endpoint_score':full,'source_study_abort':original.get('study_abort'),
            'position_error_rad':dq,'velocity_error_rad_s':dv},tid+f'/{i}/causal_prediction')
        if full: q_errors.append(dq);v_errors.append(dv)
        else: partial.append({'source_shared_transition_id':identity,'executed_substeps':n,'position_error_rad':dq,'velocity_error_rad_s':dv})
    meter=successful_meter(len(regular))
    if exceptions:
        ex=exceptions[0];checks.compare(ex['model_fingerprint'],fingerprint,tid+'/exception_frozen')
        checks.compare(ex['new_physical_calls'],0,tid+'/exception_no_physics')
        saved=ex['prediction_accounting']
        extra=saved['pair_prediction_attempts']-len(regular)
        checks.check(type(extra) is int and extra in (0,1),'one_unwritten_or_failed_prediction',tid)
        if extra==1:
            original=originals[len(regular)];identity=original['shared_transition_id'];ids.append(identity)
            if saved['pair_prediction_successes']==len(regular)+1:
                # Prediction and score were computed before trace emission.
                # A write failure pays one successful causal call, not a
                # failed head; reconstruct the unwritten score from A bytes.
                q,v=[original['observation_before'][k][:2] for k in ('joint_position','joint_velocity')]
                prediction=predict(state['observed_theta'],state['ranges'],qref,q,v,original['requested_torque'][:2])
                nq,nv=[original['observation_after'][k][:2] for k in ('joint_position','joint_velocity')]
                dq=[nq[j]-prediction[0][j] for j in range(2)];dv=[nv[j]-prediction[1][j] for j in range(2)]
                n=original['diagnostics']['executed_substeps']
                if n==10: q_errors.append(dq);v_errors.append(dv)
                else: partial.append({'source_shared_transition_id':identity,'executed_substeps':n,'position_error_rad':dq,'velocity_error_rad_s':dv})
                meter=successful_meter(len(regular)+1)
            else: meter=failed_meter(meter,ex.get('failure_accounting',{}),checks,tid+'/failure')
        checks.compare(saved,meter,tid+'/failure_time_meter')
    else: checks.compare(record['status'],source['prediction_episode']['status'],tid+'/exact_source_status')
    checks.compare(record['source_transition_ids'],ids,tid+'/single_causal_prediction_ids')
    checks.compare(record['partial_endpoint_scores'],partial,tid+'/partial_scores_separate')
    checks.compare(record['position_prediction_rmse'],guard.paired_rmse(q_errors),tid+'/position_metrics')
    checks.compare(record['velocity_prediction_rmse'],guard.paired_rmse(v_errors),tid+'/velocity_metrics')
    checks.compare(record['metric_complete_endpoints'],len(v_errors),tid+'/score_count')
    guard.validate_meter(record['prediction_accounting'],checks,tid+'/meter',100)
    checks.compare(record['prediction_accounting'],meter,tid+'/one_call_per_source_start')
    completed=(not exceptions and len(regular)==len(originals) and len(v_errors)==100
        and source['prediction_episode']['status']=='completed' and source['prediction_episode'].get('completed') is True)
    checks.compare(record['completed'],completed,tid+'/completion')
    metrics=guard.paired_rmse(v_errors)
    return {'eligible':completed,'completed':completed,'status':record['status'],
        'velocity_prediction_rmse':{MODEL:None if metrics is None else metrics['per_axis']},
        'prediction_accounting':meter,'complete_score_endpoints':len(v_errors),'partial_score_endpoints':len(partial)}

def control_diagnostic_meter(regular,exceptions,checks,tid):
    count=sum(r['step_index']>=100 for r in regular);meter=successful_meter(count)
    if exceptions:
        ex=exceptions[0]
        duplicate=any(r['step_index']==ex.get('step_index') for r in regular)
        if not duplicate and ex.get('step_index') is not None and ex['step_index']>=100:
            if MODEL in ex.get('predicted_next_qv',{}): meter=successful_meter(count+1)
            elif ex.get('planner_decision') is not None:
                saved=ex['diagnostic_prediction_accounting']
                if saved['pair_prediction_attempts']==count+1:
                    meter=failed_meter(meter,ex.get('failure_accounting',{}),checks,tid+'/diagnostic_failure')
                else: checks.compare(saved['pair_prediction_attempts'],count,tid+'/before_diagnostic_call')
    return meter

def audit_control(source,sr,episode,rows,state,ranges,checks):
    seed=source['seed'];tid=f'seed{seed}_{MODEL}';ev=sr['evaluations'].get(MODEL,{})
    trial_failures=checks.failed
    checks.compare(episode,{'trial_id':tid,'seed':seed,'kind':MODEL,'maximum_control_steps':300},tid+'/plan')
    regular=[r for r in rows if 'collector_exception' not in r];exceptions=[r for r in rows if 'collector_exception' in r]
    checks.check(len(exceptions)<=1 and (not exceptions or rows[-1] is exceptions[0]),'one_final_control_failure',tid)
    checks.check(episode['status'] in ('blocked','completed','terminated','exception','incomplete'),'known_outcome',tid)
    if episode['status']=='blocked':
        checks.check(not rows,'blocked_no_physical_trace',tid)
        checks.compare(episode,{'completed':False,'control_calls_attempted':0,'control_steps':0,'physics_steps':0},tid+'/zero_cost')
        for phase in PHASES:
            checks.compare(episode['phase_budgets'][phase],{'control_calls_attempted':0,'control_steps':0,'physics_steps':0},tid+'/'+phase+'/zero_cost')
        checks.check(state is None or episode.get('reason',{}).get('type')=='ArchiveAborted','genuine_blocked_dependency_or_archive_abort',tid)
        checks.compare(ev,{'completed':False,'status':'blocked'},tid+'/blocked_eval')
        return {'eligible':False,'completed':False,'status':'blocked'}
    _assert(state is not None,'No control before complete calibration')
    qref=source['reference_q'];directions=source['direction'];fingerprint=digest(parameter_record(qref,state,True))
    for key in ('model_fingerprint_before','model_fingerprint_after'): checks.compare(ev[key],fingerprint,tid+'/'+key)
    checks.compare(ev['model_updates'],0,tid+'/no_control_fit')
    for phase,cap in (('prefix',100),('control',200)):
        budget=episode['phase_budgets'][phase]
        checks.check(all(type(budget[k]) is int and 0<=budget[k]<=cap for k in ('control_calls_attempted','control_steps'))
            and type(budget['physics_steps']) is int and 0<=budget['physics_steps']<=10*cap,'phase_cost_bounds',tid+'/'+phase)
    checks.compare([r['step_index'] for r in regular],list(range(len(regular))),tid+'/contiguous_indices')
    checks.check(len(regular)<=300,'control_duration_cap',tid)
    counter={'physics':0};previous=None;previous_u=[0.,0.]
    phase_rows={p:0 for p in PHASES};phase_physics={p:0 for p in PHASES}
    effort={p:guard.new_effort() for p in PHASES};risk={p:common.new_risk() for p in ('full',*PHASES)}
    tracking=[];partial=[];errors={n:{'q':[],'v':[]} for n in (MODEL,'persistence')}
    planning=guard.empty_meter();fallback=0;saturation=[0,0];study=False;terminal=False
    for row in regular:
        index=row['step_index'];location=tid+':'+str(index);phase='prefix' if index<100 else 'control'
        checks.compare(row,{'trial_id':tid,'seed':seed,'kind':MODEL,'joint_indices':[0,1],
            'shared_transition_id':location,'phase':phase},location+'/labels')
        checks.check(not study and not terminal,'no_rows_after_terminal',location)
        n=guard.verify_transition(row,previous,counter,ranges,checks,location)
        phase_rows[phase]+=1;phase_physics[phase]+=n;guard.add_effort(effort[phase],row)
        for p in ('full',phase): common.record_risk(risk[p],row,ranges,joint_index=0)
        previous=row['observation_after'];terminal=row['diagnostics']['terminated']
        checks.compare(row['model_update'],None,location+'/frozen_update')
        if index<100:
            checks.compare(row['requested_torque'],[0.]*8,location+'/zero_prefix')
            checks.compare(row['target_q'],None,location+'/prefix_target')
            checks.compare(row['predicted_next_qv'],{},location+'/prefix_predictions')
            checks.compare(row['model_input_diagnostics'],{},location+'/prefix_inputs')
            checks.compare(row['planner_decision'],None,location+'/prefix_planner')
            checks.compare(row['study_abort'],None,location+'/prefix_study')
            continue
        q,v=[row['observation_before'][k][:2] for k in ('joint_position','joint_velocity')]
        if index==100:
            checks.compare(row['observation_before']['joint_position'][:2],qref,location+'/native_qref')
            checks.compare(row['observation_before']['joint_velocity'][:2],source['native_prefix_observation']['joint_velocity'][:2],location+'/native_prefix_velocity')
        target=[qref[i]+directions[i]*(.04 if index<200 else .08) for i in range(2)]
        decision=replay_mpc(state['observed_theta'],state['ranges'],qref,q,v,target,previous_u,ranges[:2])
        checks.check(set(row['planner_decision'])==set(decision),'exact_planner_decision_whitelist',location)
        checks.compare(row['planner_decision'],decision,location+'/all_81_candidates')
        checks.compare(row['requested_torque'],decision['torque']+[0.]*6,location+'/first_action')
        checks.compare(row['target_q'],target,location+'/current_target_only')
        for key in PLANNING_KEYS: planning[key]+=decision[key]
        fallback+=decision['fallback'];u=row['requested_torque'][:2];previous_u=u
        prediction=predict(state['observed_theta'],state['ranges'],qref,q,v,u)
        persistence=([q[i]+DT*v[i] for i in range(2)],v)
        checks.check(set(row['predicted_next_qv'])=={MODEL,'persistence'},'exact_causal_diagnostic_model_set',location)
        checks.compare(row['predicted_next_qv'],{MODEL:prediction,'persistence':persistence},location+'/single_causal_diagnostic')
        checks.compare(row['model_input_diagnostics'],{MODEL:guard.describe_input(q,u,('known_angle_guard',state['ranges']))},location+'/guard_current_q')
        study=guard.verify_study(row,qref,checks,location)
        nq,nv=[row['observation_after'][k][:2] for k in ('joint_position','joint_velocity')]
        if n==10:
            tracking.append([nq[i]-target[i] for i in range(2)])
            for name,pred in ((MODEL,prediction),('persistence',persistence)):
                errors[name]['q'].append([nq[i]-pred[0][i] for i in range(2)])
                errors[name]['v'].append([nv[i]-pred[1][i] for i in range(2)])
            for i in range(2): saturation[i]+=abs(u[i])==.5
        else: partial.append({'step_index':index,'target_q':target,'errors_rad':[nq[i]-target[i] for i in range(2)],'executed_substeps':n})
    if len(regular)>=100:
        checks.compare(regular[99]['observation_after']['joint_position'][:2],qref,tid+'/paid_prefix_qref')
        binding=sr.get('fresh_prefix_binding')
        if len(regular)>100 or exceptions and exceptions[0].get('step_index',-1)>=100:
            checks.compare(binding,{'reference_q':qref,'native_velocity':source['native_prefix_observation']['joint_velocity'][:2],
                'direction':directions,'public_joint_ranges':source['public_joint_ranges'],
                'environment_fingerprint':source['environment_fingerprint_before'],'source_native_pair_exact':True},tid+'/prefix_binding')
            selections=[]
            for i in range(2):
                low,high=ranges[i];positive,negative=high-qref[i],qref[i]-low
                selections.append({'joint_index':i,'joint_position_rad':qref[i],'lower_limit_rad':low,'upper_limit_rad':high,
                    'positive_room_rad':positive,'negative_room_rad':negative,'direction':1 if positive>=negative else -1,
                    'rule':'larger distance to the public joint limit; ties choose positive'})
            checks.compare(binding['selection_records'],selections,tid+'/public_direction')
    for ex in exceptions:
        checks.compare(ex,{'trial_id':tid,'seed':seed,'kind':MODEL,'model_update':None},tid+'/exception_identity')
        for field in ('observation_before','observation_after'):
            obs=ex.get(field)
            if obs is not None:
                checks.check(set(obs)==set(common.NATIVE),'exception_native_whitelist',tid)
                for key,width in common.NATIVE.items(): vector(obs[key],width)
        guard.verify_exception_native_mapping(ex,checks,tid)
        guard.verify_exception_paid_counters(ex,episode,checks,tid)
        verify_snapshot(ex['frozen_model_snapshot'],state,qref,checks,tid+'/exception_frozen',False)
        if ex.get('step_index') is not None and ex['step_index']>=100:
            expected=[qref[i]+directions[i]*(.04 if ex['step_index']<200 else .08) for i in range(2)]
            checks.compare(ex.get('target_q'),expected,tid+'/exception_current_target')
            duplicate=any(r['step_index']==ex.get('step_index') for r in regular)
            if not duplicate and ex.get('planner_decision') is not None:
                q,v=[ex['observation_before'][k][:2] for k in ('joint_position','joint_velocity')]
                # Current-entry encoders, not the preceding interval's origin.
                if regular: checks.compare(ex['observation_before'],regular[-1]['observation_after'],tid+'/exception_current_entry')
                decision=replay_mpc(state['observed_theta'],state['ranges'],qref,q,v,expected,previous_u,ranges[:2])
                checks.compare(ex['planner_decision'],decision,tid+'/exception_paid_mpc')
                checks.compare(ex['requested_torque'],decision['torque']+[0.]*6,tid+'/exception_requested_action')
                for key in PLANNING_KEYS: planning[key]+=decision[key]
                fallback+=decision['fallback']
            failed=ex.get('failure_accounting',{}).get('pair_planning_accounting')
            if failed is not None:
                for key in PLANNING_KEYS:
                    checks.check(type(failed[key]) is int and failed[key]>=0,'known_failed_planning_count',tid+'/'+key)
                    planning[key]+=failed[key]
                checks.check(failed['pair_prediction_attempts']<=1215 and failed['scalar_prediction_attempts']<=2430
                    and failed['pair_prediction_successes']<=failed['pair_prediction_attempts']
                    and failed['scalar_prediction_successes']<=failed['scalar_prediction_attempts'],'failed_mpc_horizon_bounds',tid)
    for phase in PHASES:
        budget=episode['phase_budgets'][phase]
        checks.check(budget['control_calls_attempted']>=budget['control_steps']>=phase_rows[phase]
            and phase_physics[phase]<=budget['physics_steps']<=10*budget['control_calls_attempted'],'paid_vs_saved_phase',tid+'/'+phase)
    for key in ('control_calls_attempted','control_steps','physics_steps'):
        checks.compare(episode[key],sum(b[key] for b in episode['phase_budgets'].values()),tid+'/sum/'+key)
    missing=episode['physics_steps']-counter['physics']
    checks.check(0<=missing<=10 and 0<=episode['control_steps']-len(regular)<=1,'single_failed_interval_cost_cap',tid)
    checks.check(type(episode['returned_steps']) is int and type(episode['written_returned_steps']) is int
        and 0<=episode['written_returned_steps']<=episode['returned_steps']<=episode['control_steps']
        and len(regular)<=episode['returned_steps']<=len(regular)+1,'returned_written_paid_partition',tid)
    checks.compare(episode['returned_unwritten_steps'],episode['returned_steps']-episode['written_returned_steps'],tid+'/unwritten')
    checks.check(type(episode['unreturned_physics_steps']) is int and 0<=episode['unreturned_physics_steps']<=missing,'unreturned_physics_not_zeroed',tid)
    full=(episode['status']=='completed' and len(regular)==300 and episode['control_calls_attempted']==episode['control_steps']==300
        and episode['physics_steps']==3000 and not exceptions and not study and not terminal
        and all(r['diagnostics']['executed_substeps']==10 for r in regular))
    checks.check(episode['status']!='completed' or full,'honest_full_completion',tid)
    checks.compare(episode['completed'],full,tid+'/episode_completion');checks.compare(ev['completed'],full,tid+'/eval_completion')
    for key in ('status','study_abort','environment_terminated','environment_stop_reason','collector_exception'):
        checks.compare(ev[key],episode[key],tid+'/outcome/'+key)
    checks.compare(episode['reason'],episode['environment_stop_reason'] if episode['environment_terminated'] else
        episode['study_abort'] if episode['study_abort'] is not None else episode['collector_exception'],tid+'/reason_precedence')
    if not exceptions:
        checks.compare(episode['returned_steps'],len(regular),tid+'/returned_count')
        checks.compare(episode['written_returned_steps'],len(regular),tid+'/written_count')
        checks.compare(episode['study_abort'],regular[-1].get('study_abort') if regular else None,tid+'/terminal_study')
        checks.compare(episode['environment_terminated'],terminal,tid+'/environment_terminal')
    if episode.get('environment_fingerprint_before') is not None:
        checks.compare(episode['environment_fingerprint_before'],source['environment_fingerprint_before'],tid+'/A_plant_binding')
        checks.compare(episode['environment_fingerprint_after'],episode['environment_fingerprint_before'],tid+'/fixed_plant')
    checks.compare(ev['tracking_rmse'],guard.paired_rmse(tracking),tid+'/tracking')
    checks.compare(ev['metric_control_step_count'],len(tracking),tid+'/complete_score_count')
    for field,key in (('position_prediction_rmse','q'),('velocity_prediction_rmse','v')):
        checks.compare(ev[field],{n:guard.paired_rmse(e[key]) for n,e in errors.items()},tid+'/'+field)
    checks.compare(ev['partial_interval_target_errors_rad'],partial,tid+'/partial_scores')
    checks.compare(ev['saturated_control_steps_per_axis'],saturation,tid+'/saturation')
    effort_audit={p:guard.reconcile_effort(ev,p,effort[p],episode['phase_budgets'][p]['physics_steps'],phase_physics[p],exceptions,checks,tid+'/effort/'+p) for p in PHASES}
    checks.compare(ev['control_effort'],ev['phase_effort']['control'],tid+'/effort_alias')
    paid=episode['phase_budgets']['control']['physics_steps'];measured=ev['phase_actual_effort_substeps']['control']
    checks.compare(ev['actual_effort_complete'],measured==paid,tid+'/effort_complete')
    checks.compare(ev['actual_effort_is_lower_bound'],measured<paid,tid+'/effort_lower_bound')
    checks.compare(ev['missing_control_effort_substeps'],paid-measured,tid+'/missing_effort_substeps')
    checks.compare(ev['actual_control_effort_substeps'],measured,tid+'/measured_effort_substeps')
    accounting=ev['planning_accounting'];failed=ev['failed_planner_attempts']
    checks.check(type(failed) is int and 0<=failed<=1 and (not failed or bool(exceptions)),'one_failed_planner_call',tid)
    successful=sum(r['step_index']>=100 for r in regular)
    if exceptions and exceptions[0].get('planner_decision') is not None and not any(r['step_index']==exceptions[0].get('step_index') for r in regular): successful+=1
    unknown=failed if exceptions and exceptions[0].get('failure_accounting',{}).get('pair_planning_accounting') is None else 0
    checks.compare({k:accounting[k] for k in PLANNING_KEYS},planning,tid+'/planning_paid_counts')
    checks.compare(accounting['unknown_failed_planner_calls'],unknown,tid+'/unknown_planner_cost')
    incomplete=unknown>0 or planning['unknown_scalar_failure_count']>0
    checks.compare(accounting['scalar_counts_complete'],not incomplete,tid+'/planning_complete')
    checks.compare(accounting['scalar_counts_is_lower_bound'],incomplete,tid+'/planning_lower_bound')
    checks.compare(ev['planner_attempt_count'],successful+failed,tid+'/planner_invocations')
    checks.check(ev['planner_attempt_count']<=200,'planner_call_cap',tid)
    checks.compare(ev['planner_decision_count'],successful,tid+'/planner_successes')
    checks.compare(ev['planner_fallbacks'],fallback,tid+'/fallbacks')
    diagnostic=control_diagnostic_meter(regular,exceptions,checks,tid)
    guard.validate_meter(ev['diagnostic_prediction_accounting'],checks,tid+'/diagnostic_meter',200)
    checks.compare(ev['diagnostic_prediction_accounting'],diagnostic,tid+'/single_control_diagnostic')
    if ev['planner_spec'] is not None: checks.compare(ev['planner_spec'],guard.planner_spec(qref,ranges[:2]),tid+'/exact_fixed_planner')
    if full: checks.check(ev['planner_spec'] is not None,'full_control_requires_planner',tid)
    checks.check(not episode.get('risk_telemetry_complete',False) or missing==0 and not exceptions,'risk_missing_not_declared_complete',tid)
    for phase in risk:
        absent=missing if phase=='full' else episode['phase_budgets'][phase]['physics_steps']-phase_physics[phase]
        risk[phase].update(telemetry_missing_paid_substeps=absent,reconstruction_complete=absent==0,
            request_applied_mismatch_count_is_lower_bound=absent>0)
    metric=guard.paired_rmse(tracking)
    return {'eligible':full and checks.failed==trial_failures,'completed':full,'status':episode['status'],
        'tracking_rmse_rad':None if metric is None else metric['joint'],
        'tracking_rmse_by_axis_rad':None if metric is None else metric['per_axis'],
        'velocity_prediction_rmse':{n:guard.paired_rmse(e['v'])['per_axis'] for n,e in errors.items() if e['v']},
        'control_effort':ev['control_effort'],'actual_effort_complete':ev['actual_effort_complete'],
        'effort_audit':effort_audit,'risk':risk,'independent_planning_accounting':planning,
        'diagnostic_prediction_accounting':diagnostic,'complete_score_endpoints':len(tracking),
        'partial_score_endpoints':len(partial),'unreconstructed_physics_substeps':missing,
        'paid_budget':{k:episode[k] for k in ('control_calls_attempted','control_steps','physics_steps')}}

def nonnegative_pair(value): return type(value) is list and len(value)==2 and all(finite(z) and z>=0 for z in value)
def complete(ev): return type(ev) is dict and ev.get('eligible') is True and ev.get('completed') is True and ev.get('status')=='completed'
def complete_matrix(seeds,kinds):
    return len(seeds)==3 and {s['seed'] for s in seeds}==set(RESET) and all(complete(s.get('evaluations',{}).get(k)) for s in seeds for k in kinds)
def contribution_gate(seeds):
    kinds=('calibration','prediction','nominal_guard',MODEL)
    eligible=complete_matrix(seeds,kinds);rows=[]
    for sr in seeds:
        ev=sr.get('evaluations',{});n=ev.get('nominal_guard',{});c=ev.get(MODEL,{})
        a,b=n.get('tracking_rmse_rad'),c.get('tracking_rmse_rad')
        ax,bx=n.get('tracking_rmse_by_axis_rad'),c.get('tracking_rmse_by_axis_rad')
        pm=ev.get('prediction',{}).get('velocity_prediction_rmse',{})
        pn,pc=pm.get('nominal_guard'),pm.get(MODEL)
        valid=eligible and all(nonnegative_pair(v) for v in (ax,bx,pn,pc)) and all(finite(v) and v>=0 for v in (a,b))
        rows.append({'seed':sr['seed'],'eligible':bool(valid),'nominal_tracking':a,'coupled_tracking':b,
            'nominal_axis_tracking':ax,'coupled_axis_tracking':bx,'nominal_velocity_prediction':pn,'coupled_velocity_prediction':pc,
            'prediction_axes_passed':[valid and pc[i]<=.8*pn[i] for i in range(2)],
            'strict_joint_tracking':valid and b<a,'strict_axis_tracking':[valid and bx[i]<ax[i] for i in range(2)]})
    evaluated=eligible and all(r['eligible'] for r in rows)
    na=sum(r['nominal_tracking'] for r in rows)/3 if evaluated else None
    cb=sum(r['coupled_tracking'] for r in rows)/3 if evaluated else None
    change=guard.improvement(cb,na) if evaluated else None;axis=[]
    for i in range(2):
        a=sum(r['nominal_axis_tracking'][i] for r in rows)/3 if evaluated else None
        b=sum(r['coupled_axis_tracking'][i] for r in rows)/3 if evaluated else None
        delta=guard.improvement(b,a) if evaluated else None
        axis.append({'axis':i,'nominal_raw_mean':a,'coupled_raw_mean':b,'improvement':delta,
            'passed':bool(evaluated and delta is not None and delta>=.20 and all(r['strict_axis_tracking'][i] for r in rows))})
    passed=evaluated and change is not None and change>=.20 and all(g['passed'] for g in axis) and all(r['strict_joint_tracking'] and all(r['prediction_axes_passed']) for r in rows)
    return {'evaluated':bool(evaluated),'passed':bool(passed),'required_trials':list(kinds),
        'required_trials_complete':eligible,'per_seed':rows,'nominal_raw_tracking_mean':na,
        'coupled_raw_tracking_mean':cb,'joint_tracking_mean_improvement':change,'axis_tracking_gates':axis,
        'prediction_boundary':'Paid A development reuse, not a new holdout.'}

def comparison_gate(seeds,baseline,own):
    _assert(baseline in ('learned_guard','PDselected'),'Fixed comparison baseline')
    kinds=('calibration','prediction','nominal_guard',MODEL,baseline)
    eligible=complete_matrix(seeds,kinds);rows=[]
    for sr in seeds:
        ev=sr.get('evaluations',{});a=ev.get(baseline,{});b=ev.get(MODEL,{})
        x,y=a.get('tracking_rmse_rad'),b.get('tracking_rmse_rad')
        ax,bx=a.get('tracking_rmse_by_axis_rad'),b.get('tracking_rmse_by_axis_rad')
        valid=eligible and all(nonnegative_pair(v) for v in (ax,bx)) and all(finite(v) and v>=0 for v in (x,y))
        prediction=[True,True]
        if baseline=='learned_guard':
            pm=ev.get('prediction',{}).get('velocity_prediction_rmse',{})
            px,py=pm.get('learned_guard'),pm.get(MODEL)
            valid=valid and nonnegative_pair(px) and nonnegative_pair(py)
            prediction=[valid and py[i]<=px[i] for i in range(2)]
        efforts={}
        for key in EFFORT_KEYS[2:]:
            first=a.get('control_effort',{}).get(key);second=b.get('control_effort',{}).get(key)
            okay=a.get('actual_effort_complete') is True and b.get('actual_effort_complete') is True and nonnegative_pair(first) and nonnegative_pair(second)
            valid=valid and okay;efforts[key]={'baseline':sum(first) if okay else None,'coupled':sum(second) if okay else None}
        rows.append({'seed':sr['seed'],'eligible':bool(valid),'baseline_tracking':x,'coupled_tracking':y,
            'tracking_non_worse':valid and y<=x,'axis_tracking_non_worse':[valid and bx[i]<=ax[i] for i in range(2)],
            'prediction_axes_non_worse':prediction,'efforts':efforts})
    evaluated=bool(own['passed'] and eligible and all(r['eligible'] for r in rows))
    x=sum(r['baseline_tracking'] for r in rows)/3 if evaluated else None
    y=sum(r['coupled_tracking'] for r in rows)/3 if evaluated else None
    change=guard.improvement(y,x) if evaluated else None;effort_gates={}
    for key in EFFORT_KEYS[2:]:
        first=sum(r['efforts'][key]['baseline'] for r in rows)/3 if evaluated else None
        second=sum(r['efforts'][key]['coupled'] for r in rows)/3 if evaluated else None
        effort_gates[key]={'baseline_mean':first,'coupled_mean':second,
            'passed':bool(evaluated and (second==0 if first==0 else second<=1.05*first))}
    passed=evaluated and change is not None and change>=.05 and all(r['tracking_non_worse'] and all(r['axis_tracking_non_worse']) and all(r['prediction_axes_non_worse']) for r in rows) and all(g['passed'] for g in effort_gates.values())
    return {'baseline':baseline,'evaluated':evaluated,'passed':bool(passed),'own_model_contribution_passed':own['passed'],
        'required_trials':list(kinds),'required_trials_complete':eligible,'per_seed':rows,
        'baseline_raw_tracking_mean':x,'coupled_raw_tracking_mean':y,'joint_tracking_mean_improvement':change,
        'actual_effort_gates':effort_gates,'incomplete_baseline_not_scored':not eligible}
def scientific_gates(seeds):
    own=contribution_gate(seeds)
    return {'coupled_contribution':own,'diagonal_increment':comparison_gate(seeds,'learned_guard',own),
        'selected_pd_comparison':comparison_gate(seeds,'PDselected',own)}

def require_scope(metadata,spec):
    if type(spec) is not CoupledAuditSpec: raise ValueError('Trusted immutable scope required')
    expected={'schema_version':1,'suite':'guard_coupled_development','synthetic':spec.synthetic_fixture,
        'seeds':[0,1,2],'split':'development','pose':'supine','joint_indices':[0,1],'native_joint_count':8,
        'gpu':None,'prefix_steps':100,'calibration_reuse_steps':400,'prediction_reuse_steps':100,
        'control_steps_per_trial':200,'structures':['coupled_hinge9'],'model_input_basis':'known_angle_guard',
        'parameter_count_per_output':9,'reused_diagonal_parameter_count_per_output':5,
        'policy_parameter_updates':0,'gain_updates':0,'gate_updates':0,'teacher_calls':0,'external_demonstration_samples':0}
    for key,value in expected.items(): _equal(metadata.get(key),value,'Immutable scope before replay '+key)
    _equal(metadata['protocol']['path'],PROTOCOL,'Immutable B protocol')
    if not spec.synthetic_fixture:
        _equal(metadata.get('backend'),'MuJoCo CPU','Production CPU backend')
        _equal(metadata.get('environment_config'),common.ENVIRONMENT,'Fixed public environment')
    return metadata

def audit_archive(path,checks,git_root,spec):
    metadata=require_scope(load_json(path/'metadata.json'),spec)
    members,ranges,input_hashes=verify_sources(path,metadata,checks,git_root,spec)
    sources,a_record=reconstruct_a(members,metadata,spec)
    checks.check(True,'independently_bound_A_original_bytes')
    plans=[{'trial_id':f'seed{s}_{MODEL}','seed':s,'kind':MODEL,'maximum_control_steps':300} for s in RESET]
    checks.compare(metadata['planned_episodes'],plans,'exact_three_plans')
    for field,value in {'maximum_control_steps':900,'maximum_physics_steps':9000,
        'maximum_offline_replay_scalar_updates':2400,'maximum_offline_replay_vector_updates':1200,
        'maximum_independent_prediction_pair_calls':300,'maximum_rls_internal_prediction_pair_calls':1200,
        'maximum_mpc_prediction_pair_calls':729000,'maximum_control_diagnostic_prediction_pair_calls':600}.items():
        checks.compare(metadata[field],value,'maximum_cost/'+field)
    checks.compare(metadata['study_abort_spec'],{'active_only':True,'absolute_q_minus_qref_rad':.12,
        'absolute_velocity_rad_s':1.,'comparison':'>=','any_axis':True,'feedback_action':None,
        'complete_terminal_scored_not_complete':True},'fixed_research_stop')
    episodes=load_json(path/'episodes.json');epmap=_maps(episodes,'trial_id',{p['trial_id'] for p in plans},'B episodes')
    raw_seeds=load_json(path/'seed_results.json')
    # Fatal interruptions may checkpoint a prefix of the planned seed array;
    # their remaining zero-cost blocked episodes remain visible.
    saved={}
    for sr in raw_seeds:
        seed=sr['seed'];_assert(type(seed) is int and seed in RESET and seed not in saved,'Unique B saved seed')
        saved[seed]=sr
    _assert(list(saved)==list(RESET)[:len(saved)],'B saved seed order')
    groups=[]
    for name in ('calibration_replay.jsonl.gz','prediction_replay.jsonl.gz','trace.jsonl.gz'):
        grouped={s:[] for s in RESET}
        for row in read_rows((path/name).read_bytes()):
            seed=row['seed'];_assert(type(seed) is int and seed in RESET,'Known trace seed')
            grouped[seed].append(row)
        groups.append(grouped)
    derived=[];total_vector=total_scalar=0
    for seed in RESET:
        source=sources[seed];sr=saved.get(seed);episode=epmap[f'seed{seed}_{MODEL}']
        if sr is None:
            checks.check(episode['status']=='blocked' and not any(g[seed] for g in groups),'fatal_remaining_plan_blocked',seed)
            checks.compare(episode,{'control_calls_attempted':0,'control_steps':0,'physics_steps':0},f'seed{seed}/fatal_zero_cost')
            derived.append({'seed':seed,'evaluations':{MODEL:{'eligible':False,'completed':False,'status':'blocked'}}})
            continue
        checks.compare(sr,{'seed':seed,'reset_seed':RESET[seed],'reference_q':source['reference_q'],
            'direction':source['direction'],'public_joint_ranges':source['public_joint_ranges'],
            'reused_baselines':source['reused_baselines'],'reused_audit_metrics':source['reused_audit_metrics']},f'seed{seed}/immutable_A_reuse')
        state,cal=audit_calibration(source,sr,groups[0][seed],checks)
        total_vector+=cal['new_vector_updates'];total_scalar+=cal['new_scalar_updates']
        pred=audit_prediction(source,sr,groups[1][seed],state,checks)
        control=audit_control(source,sr,episode,groups[2][seed],state,ranges,checks)
        original_prediction=source['reused_audit_metrics'].get('prediction') or {}
        pm=dict(original_prediction.get('velocity_prediction_rmse',{}));pm.update(pred.get('velocity_prediction_rmse',{}))
        pred=dict(pred,velocity_prediction_rmse=pm)
        evaluations={'calibration':cal,'prediction':pred,MODEL:control}
        for key in ('nominal_guard','learned_guard','PDselected','zero'):
            evaluations[key]=source['reused_audit_metrics'].get(key) or {'eligible':False,'completed':False,'status':'missing'}
        # B's scientific prediction gate also requires A's whole prediction
        # trial, never merely 100 complete scores before a terminal interval.
        pred['eligible']=pred['eligible'] and complete(original_prediction)
        derived.append({'seed':seed,'evaluations':evaluations})
    budget={key:sum(ep[key] for ep in episodes) for key in ('control_calls_attempted','control_steps','physics_steps')}
    for key,value in budget.items(): checks.compare(metadata[key],value,'batch_ledger/'+key)
    checks.compare(metadata['model_updates'],total_scalar,'batch_scalar_replay_commits')
    checks.compare(metadata['vector_model_updates'],total_vector,'batch_vector_replay_commits')
    checks.compare(metadata['all_trials_successful'],all(ep['status']=='completed' for ep in episodes),'batch_success')
    for label,status in (('completed_trials','completed'),('terminated_trials','terminated'),('exception_trials','exception'),('blocked_trials','blocked')):
        checks.compare(metadata[label],sum(ep['status']==status for ep in episodes),'batch_outcome/'+label)
    return {'seeds':derived,'episodes':episodes,'input_hashes':input_hashes,
        'budget':{**budget,'model_updates':total_scalar,'vector_model_updates':total_vector},
        'A_paid_budget':a_record['A_paid_budget'],'A_original_binding':a_record,
        'sample_semantics':'Only B cold coupled9 replay creates new updates; A diagonal snapshots and first-audit baseline metrics reused unchanged. A prediction is development reuse.'}

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
    for gate in gates.values(): gate['validated_pass']=bool(gate['passed'] and eligibility)
    gates['data_consistency_verified']=checks.failed==0
    return {'schema_version':1,'created_at_utc':datetime.now(timezone.utc).isoformat(),
        'audit_script_sha256':file_hash(__file__),'audit_dependency_sha256':{n:file_hash(ROOT/n) for n in SUPPORT},
        'immutable_scope':spec.record(),'checks':checks.count,'failed':checks.failed,'violations':checks.violations,
        'maximum_recomputation_difference':checks.maximum_difference,'archive':result,'final_gates':gates,
        'reported_paid_budget_if_replay_incomplete':reported,
        'execution':{'wall_seconds':time.perf_counter()-wall,'cpu_seconds':time.process_time()-cpu,
            'timing_scope':'Entry through report assembly, excludes imports and final JSON writing',
            'python':sys.version,'platform':sys.platform if spec.synthetic_fixture else platform.platform(),
            'source_git_verification_enabled':git_root is not None and not spec.synthetic_fixture,
            'physical_simulation_calls':0,'model_parameter_updates':0,'online_model_imports':0,
            'A_audit_reexecutions':0,'diagonal_model_refits':0}}
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
