"""Handwritten mechanism/provenance fixtures; no physics, online model or fit."""
from copy import deepcopy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import zipfile

import pytest

HERE=Path(__file__).resolve().parent
ROOT=next(p for p in HERE.parents if (p/'pyproject.toml').is_file())
SOURCE=HERE/'audit_guard_coupled_development.py'
if not SOURCE.exists(): SOURCE=ROOT/'scripts/audit_guard_coupled_development.py'
spec=importlib.util.spec_from_file_location('coupled_audit_under_test',SOURCE)
audit=importlib.util.module_from_spec(spec);sys.modules[spec.name]=audit;spec.loader.exec_module(audit)

def metric(x,axes=None):
    axes=[x,x] if axes is None else axes
    return {'eligible':True,'completed':True,'status':'completed','tracking_rmse_rad':x,
        'tracking_rmse_by_axis_rad':axes,'actual_effort_complete':True,
        'control_effort':{key:[.5,.5] for key in audit.EFFORT_KEYS[2:]}}
def scientific_fixture():
    records=[]
    for seed in (0,1,2):
        ev={'calibration':metric(0.),'prediction':metric(0.),'nominal_guard':metric(1.),
            'learned_guard':metric(.70),'PDselected':metric(.72),'coupled_guard':metric(.65)}
        ev['prediction']['velocity_prediction_rmse']={'nominal_guard':[1.,1.],
            'learned_guard':[.75,.75],'coupled_guard':[.7,.7]}
        records.append({'seed':seed,'evaluations':ev})
    return records

def test_manual_global_features_guard_and_zero_cross_prior():
    ranges=[[-1.7,1.7],[0.,2.36]];state=audit.initial_state(ranges)
    x=audit.features([0.,.04],[.1,.02],[.3,-.2],[.5,-.5],ranges)
    assert x==[[.3,-.2,.1,-.02,.5,0.,.25,0.,1.]]*2
    assert state['theta']==[[1.,0.,0.,0.,.02,0.,0.,0.,0.],
                           [0.,1.,0.,0.,0.,.02,0.,0.,0.]]
    q,v=audit.predict(state['theta'],ranges,[0.,.04],[.1,.02],[.3,-.2],[.5,-.5])
    assert v==pytest.approx([.31,-.2]);assert q==pytest.approx([.1062,.016])

def test_manual_rls_nine_dimension_single_coordinate():
    state=audit.initial_state([[-1.7,1.7],[0.,2.36]])
    x=[0.]*8+[1.]
    theta,cov,residual=audit.pair_support.replay_rls(state['theta'][0],state['covariance'][0],x,2.)
    assert residual==2.;assert theta[8]==pytest.approx(200./101)
    assert cov[8][8]==pytest.approx(100./101)
    assert all(theta[i]==state['theta'][0][i] for i in range(8))
    assert all(cov[i][i]==100. for i in range(8))

@pytest.mark.parametrize('q,u,expected',[(.03,-.5,0.),(.03,.5,.5),(2.33,.5,0.),(2.33,-.5,-.5),(.04,-.5,-.5)])
def test_guard_equality_and_inward_request(q,u,expected):
    x=audit.features([0.,.04],[0.,q],[0.,0.],[0.,u],[[-1.7,1.7],[0.,2.36]])
    assert x[0][5]==expected

def test_mpc_original_81_order_tie_break_and_effort():
    state=audit.initial_state([[-1.7,1.7],[0.,2.36]])
    decision=audit.replay_mpc(state['theta'],state['ranges'],[0.,.04],[0.,.04],[0.,0.],[0.,.04],[0.,0.],state['ranges'])
    assert decision['torque']==[0.,0.]
    assert decision['cost']==0.
    assert decision['feasible_candidates']==81
    assert decision['pair_prediction_attempts']==1215
    assert decision['scalar_prediction_attempts']==2430
    assert [r['torque'] for r in decision['candidate_records']][:3]==[[-.5,-.5],[-.5,-.375],[-.5,-.25]]

def test_all_three_scientific_gates_are_independent():
    gates=audit.scientific_gates(scientific_fixture())
    assert all(g['passed'] and g['evaluated'] for g in gates.values())

def test_diagonal_stop_not_false_victory_pd_can_still_pass():
    seeds=scientific_fixture()
    for sr in seeds:
        sr['evaluations']['learned_guard'].update(status='terminated',completed=False,eligible=False,
            tracking_rmse_rad=1e9,tracking_rmse_by_axis_rad=[1e9,1e9])
    gates=audit.scientific_gates(seeds)
    assert gates['coupled_contribution']['passed']
    assert gates['diagonal_increment']['evaluated'] is False
    assert gates['diagonal_increment']['passed'] is False
    assert gates['diagonal_increment']['baseline_raw_tracking_mean'] is None
    assert gates['selected_pd_comparison']['passed']

@pytest.mark.parametrize('kind',['calibration','prediction','nominal_guard','coupled_guard'])
def test_any_required_stop_blocks_all_claims(kind):
    seeds=scientific_fixture();seeds[1]['evaluations'][kind].update(status='terminated',completed=False)
    gates=audit.scientific_gates(seeds)
    assert not any(g['passed'] or g['evaluated'] for g in gates.values())

@pytest.mark.parametrize('case',['prediction','joint','axis','mean_axis'])
def test_coupled_own_twenty_percent_and_each_axis_required(case):
    seeds=scientific_fixture()
    if case=='prediction': seeds[0]['evaluations']['prediction']['velocity_prediction_rmse']['coupled_guard'][1]=.81
    elif case=='joint': seeds[0]['evaluations']['coupled_guard']['tracking_rmse_rad']=1.
    elif case=='axis': seeds[0]['evaluations']['coupled_guard']['tracking_rmse_by_axis_rad'][1]=1.
    else:
        for sr in seeds: sr['evaluations']['coupled_guard']['tracking_rmse_by_axis_rad'][1]=.81
    assert audit.contribution_gate(seeds)['passed'] is False

@pytest.mark.parametrize('case',['prediction','joint','axis','mean','effort_abs','effort_square','unknown_actual'])
def test_diagonal_increment_is_strict_and_effort_limited(case):
    seeds=scientific_fixture()
    if case=='prediction': seeds[0]['evaluations']['prediction']['velocity_prediction_rmse']['coupled_guard'][0]=.76
    elif case=='joint': seeds[0]['evaluations']['coupled_guard']['tracking_rmse_rad']=.71
    elif case=='axis': seeds[0]['evaluations']['coupled_guard']['tracking_rmse_by_axis_rad'][0]=.71
    elif case=='mean':
        for sr in seeds: sr['evaluations']['coupled_guard']['tracking_rmse_rad']=.68
    elif case=='unknown_actual': seeds[0]['evaluations']['coupled_guard']['actual_effort_complete']=False
    else:
        key='actual_absolute_nm_s' if case=='effort_abs' else 'actual_squared_nm2_s'
        for sr in seeds: sr['evaluations']['coupled_guard']['control_effort'][key]=[.53,.53]
    gates=audit.scientific_gates(seeds)
    assert gates['coupled_contribution']['passed']
    assert gates['diagonal_increment']['passed'] is False

def test_zero_denominator_effort_zero_zero_only():
    seeds=scientific_fixture()
    for sr in seeds:
        for name in ('learned_guard','coupled_guard'):
            sr['evaluations'][name]['control_effort']={key:[0.,0.] for key in audit.EFFORT_KEYS[2:]}
    assert audit.scientific_gates(seeds)['diagonal_increment']['passed']
    seeds[0]['evaluations']['coupled_guard']['control_effort']['actual_absolute_nm_s']=[0.,.001]
    assert not audit.scientific_gates(seeds)['diagonal_increment']['passed']

def test_each_three_seed_required_duplicates_do_not_count():
    seeds=scientific_fixture();seeds[2]['seed']=1
    assert not audit.contribution_gate(seeds)['evaluated']

@pytest.mark.parametrize('stage,counts',[('native_features',(0,0)),('velocity_output_0',(1,0)),('velocity_output_1',(2,1)),('endpoint_euler',(2,2))])
def test_known_prediction_failure_paid_head_counts(stage,counts):
    result=audit.failed_meter(audit.successful_meter(3),{'structured_failure':{'type':'PairPredictionError',
        'message':'artificial failure','failure_stage':stage,'scalar_prediction_attempts':counts[0],
        'scalar_prediction_successes':counts[1]}},audit.Checks(),'fixture')
    assert result['pair_prediction_attempts']==4 and result['pair_prediction_successes']==3
    assert result['scalar_prediction_attempts']==6+counts[0]
    assert result['scalar_prediction_successes']==6+counts[1]
    assert result['scalar_counts_complete'] is True

def test_unknown_prediction_failure_lower_bound():
    result=audit.failed_meter(audit.successful_meter(2),{'error':{'type':'RuntimeError','message':'opaque'}},audit.Checks(),'fixture')
    assert result['unknown_scalar_failure_count']==1
    assert result['scalar_counts_is_lower_bound'] is True
    assert result['scalar_prediction_attempts']==4

def snap(state,qref,trainable=True):
    record=audit.parameter_record(qref,state,True)
    return {**deepcopy(record),'parameter_fingerprint':audit.digest(record),'trainable':trainable,
        'vector_update_count':state['count'],'scalar_update_count':state['count']*2,'output_update_counts':[state['count']]*2,
        'update_commit':'single immutable state reference for both outputs, covariance and counts',
        'initial_prior':'generic velocity continuity and torque response; zero cross coefficients',
        'input_boundary':'current native q/v and already known requested u; no actual future torque or simulator state'}

def atomic_failure_fixture(committed=False):
    qref=[0.,.04];ranges=[[-1.7,1.7],[0.,2.36]];state=audit.initial_state(ranges)
    before=snap(state,qref);obs={'joint_position':qref+[0.]*6,'joint_velocity':[0.]*8}
    after={**obs,'joint_velocity':[2.,3.]+[0.]*6}
    source={'seed':0,'reference_q':qref,'public_joint_ranges':ranges,'calibration_ready':True,
        'calibration_transitions':[{'shared_transition_id':'seed0_calibration:100','observation_before':obs,
            'observation_after':after,'requested_torque':[0.]*8}]}
    x=[0.]*8+[1.];proposals=[]
    for i,label in enumerate((2.,3.)):
        theta=state['theta'][i].copy();theta[8]=label*100./101
        covariance=deepcopy(state['covariance'][i]);covariance[8][8]=100./101
        proposals.append({'output_index':i,'features':x,'observed_next_v_rad_s':label,'preupdate_error_rad_s':label,
            'proposed_coefficients':theta,'proposed_covariance':covariance,'committed':committed})
    if committed:
        state['theta']=[p['proposed_coefficients'] for p in proposals];state['observed_theta']=deepcopy(state['theta'])
        state['covariance']=[p['proposed_covariance'] for p in proposals];state['observed_covariance']=deepcopy(state['covariance']);state['count']=1
    final=snap(state,qref)
    update=None
    if committed:
        update={'phase':'identification','updated':True,'shared_transition_id':'seed0_calibration:100',
            'features_per_output':[x,x],'preupdate_prediction':{'next_q_rad':qref,'next_v_rad_s':[0.,0.]},
            'observed_next_v_rad_s':[2.,3.],'parameter_fingerprint_before':before['parameter_fingerprint'],
            'vector_update_count':1,'scalar_update_count':2,'committed_scalar_updates':2,
            'output_records':proposals,'parameter_fingerprint_after':final['parameter_fingerprint']}
    failure={'pair_update_accounting':{'committed_scalar_updates':2 if committed else 0,
        'snapshot_after_attempt':final,'proposed_outputs':proposals if committed else proposals[:1]}}
    ex={'seed':0,'source_shared_transition_id':'seed0_calibration:100','collector_exception':{'type':'PairUpdateError','message':'artificial'},
        'model_update':update,'model_snapshot_after':final,'failure_accounting':failure}
    record={'status':'exception','completed':False,'source_trial_id':'seed0_calibration','new_physical_calls':0,
        'new_physics_substeps':0,'initial_model':before,'model_snapshot':final,'source_transition_ids':['seed0_calibration:100'],
        'attempted_vector_updates':1,'committed_vector_updates':1 if committed else 0,'committed_scalar_updates':2 if committed else 0,
        'rls_prediction_accounting':audit.successful_meter(1)}
    return source,{'calibration_replay':record},[ex]

@pytest.mark.parametrize('committed',[False,True])
def test_atomic_failed_second_head_and_after_publish_interrupt(committed):
    source,sr,rows=atomic_failure_fixture(committed)
    checks=audit.Checks();state,derived=audit.audit_calibration(source,sr,rows,checks)
    assert checks.failed==0,checks.violations
    assert state is None and not derived['completed']
    assert derived['new_scalar_updates']==(2 if committed else 0)
    assert derived['rls_prediction_accounting']['pair_prediction_attempts']==1

@pytest.mark.parametrize('field',['coefficients','committed','scalar_count','proposal'])
def test_atomic_failed_proposal_cannot_publish_one_head(field):
    source,sr,rows=atomic_failure_fixture(False)
    if field=='coefficients': rows[0]['model_snapshot_after']['coefficients'][0][8]=1.
    elif field=='committed': rows[0]['failure_accounting']['pair_update_accounting']['committed_scalar_updates']=1
    elif field=='scalar_count': sr['calibration_replay']['committed_scalar_updates']=1
    else: rows[0]['failure_accounting']['pair_update_accounting']['proposed_outputs'][0]['proposed_coefficients'][7]=.2
    checks=audit.Checks();audit.audit_calibration(source,sr,rows,checks)
    assert checks.failed>0

def test_successful_prediction_then_write_failure_is_success_not_failed_head():
    qref=[0.,.04];state=audit.initial_state([[-1.7,1.7],[0.,2.36]])
    before={'joint_position':qref+[0.]*6,'joint_velocity':[0.]*8}
    after={'joint_position':[.01,.06]+[0.]*6,'joint_velocity':[.1,.2]+[0.]*6}
    original={'shared_transition_id':'seed0_prediction:100','observation_before':before,
        'observation_after':after,'requested_torque':[0.]*8,'diagnostics':{'executed_substeps':10},'study_abort':None}
    source={'seed':0,'reference_q':qref,'prediction_episode':{'status':'completed','completed':True},'prediction_transitions':[original]}
    fingerprint=audit.digest(audit.parameter_record(qref,state,True));meter=audit.successful_meter(1)
    record={'status':'exception','completed':False,'source_episode':source['prediction_episode'],
        'new_physical_calls':0,'new_physics_substeps':0,'committed_scalar_updates':0,
        'model_fingerprint_before':fingerprint,'model_fingerprint_after':fingerprint,
        'source_transition_ids':['seed0_prediction:100'],'partial_endpoint_scores':[],
        'position_prediction_rmse':audit.guard.paired_rmse([[.01,.02]]),
        'velocity_prediction_rmse':audit.guard.paired_rmse([[.1,.2]]),'metric_complete_endpoints':1,'prediction_accounting':meter}
    rows=[{'seed':0,'collector_exception':{'type':'OSError','message':'after prediction write failure'},
        'model_fingerprint':fingerprint,'new_physical_calls':0,'failure_accounting':{},'prediction_accounting':meter}]
    checks=audit.Checks();result=audit.audit_prediction(source,{'prediction_replay':record},rows,state,checks)
    assert checks.failed==0,checks.violations
    assert result['prediction_accounting']['pair_prediction_successes']==1
    assert result['prediction_accounting']['failed_pair_prediction_attempts']==0
    assert result['completed'] is False and result['complete_score_endpoints']==1

@pytest.mark.parametrize('mutate',[lambda r:r.update(failure_stage='invented'),lambda r:r.update(scalar_prediction_attempts=2),lambda r:r.update(scalar_prediction_successes=True)])
def test_forged_failure_stage_heads_rejected(mutate):
    record={'type':'PairPredictionError','message':'test','failure_stage':'native_features',
        'scalar_prediction_attempts':0,'scalar_prediction_successes':0};mutate(record)
    with pytest.raises(ValueError): audit.failed_meter(audit.successful_meter(0),{'structured_failure':record},audit.Checks(),'fixture')

def test_metadata_short_schema_rejected_before_zip(tmp_path):
    record={'schema_version':1,'suite':'guard_coupled_development','synthetic':True,
        'seeds':[0,1,2],'split':'development','pose':'supine','joint_indices':[0,1],'native_joint_count':8,
        'gpu':None,'prefix_steps':100,'calibration_reuse_steps':400,'prediction_reuse_steps':100,
        'control_steps_per_trial':1}
    (tmp_path/'metadata.json').write_text(json.dumps(record),encoding='utf-8')
    result=audit.audit(tmp_path,git_root=None,spec=audit.SYNTHETIC_SPEC)
    assert result['failed']==1
    assert result['archive'] is None
    assert result['violations'][0]['location']['message'].endswith('control_steps_per_trial')

def test_module_uses_standard_library_support_only():
    source=SOURCE.read_text(encoding='utf-8')
    assert 'from developmental_physics' not in source
    assert 'import numpy' not in source and 'import mujoco' not in source
    assert 'load_a_source_binding' not in source
    assert 'guard.audit(' not in source and 'guard.audit_archive(' not in source

@pytest.fixture
def artificial_a(tmp_path):
    joints=''.join(f'<joint name="{name}" range="{low} {high}"/>' for name,(low,high)
        in zip(audit.common.JOINTS,[[-1.7,1.7],[0.,2.36],[-1.7,1.7],[0.,2.36],[-1.5,1.5],[0.,2.36],[-1.5,1.5],[0.,2.36]]))
    asset=('<mujoco><compiler angle="radian"/><worldbody><body>'+joints+'</body></worldbody></mujoco>').encode()
    sources={n:('handwritten source assertion '+n).encode() for n in audit.SHARED}
    sources[audit.common.ASSET]=asset
    runtime={'environment_config':{'fixture_only':True},'dependencies':{'fixture':'0'},'mujoco_version':'fixture'}
    def encode(value): return json.dumps(value,sort_keys=True,allow_nan=False).encode()
    def zipbytes(values):
        buffer=io.BytesIO()
        with zipfile.ZipFile(buffer,'w',zipfile.ZIP_DEFLATED) as z:
            for name,blob in values.items(): z.writestr(name,blob)
        return buffer.getvalue()
    source_zip=zipbytes(sources);hashes={n:audit.sha(b) for n,b in sources.items()}
    am={'suite':'guard_pair_development','synthetic':True,'seeds':[0,1,2],'split':'development','pose':'supine',
        'joint_indices':[0,1],'native_joint_count':8,'prefix_steps':100,'calibration_steps':400,'prediction_steps':100,
        'control_steps_per_trial':200,'source_status':'','source_dirty':False,'gpu':None,'source_commit':'synthetic-fixture-no-git',
        **runtime,'source_sha256':hashes,'source_snapshot_sha256':audit.sha(source_zip),
        'protocol':{'path':audit.guard.PROTOCOL,'sha256':hashes[audit.guard.PROTOCOL]},
        'independent_auditor':{'path':audit.guard.AUDITOR,'sha256':hashes[audit.guard.AUDITOR],'pending':True,'required_for_formal':True}}
    plant=audit.sha(b'artificial source plant');episodes=[];seeds=[];rows=[];derived=[]
    for seed in (0,1,2):
        snapshots={'learned_guard':{'fixture_only':'No diagonal fit', 'qref_rad':[0.,.04]}}
        baselines={k:metric(.03) for k in ('nominal_guard','learned_guard','PDselected','zero')}
        baselines['learned_guard'].update(status='terminated',completed=False,eligible=False)
        seeds.append({'seed':seed,'reset_seed':audit.RESET[seed],'reference_q':[0.,.04],'direction':[1,1],
            'calibration_completed':True,'calibration_vector_updates':800,'calibration_scalar_updates':1600,
            'learned_models':snapshots,'evaluations':deepcopy(baselines)})
        derived.append({'seed':seed,'evaluations':{'prediction':metric(0.),**deepcopy(baselines)}})
        for kind in audit.guard.KINDS:
            episodes.append({'seed':seed,'kind':kind,'trial_id':f'seed{seed}_{kind}','completed':kind!='learned_guard',
                'status':'terminated' if kind=='learned_guard' else 'completed',
                'environment_fingerprint_before':plant,'environment_fingerprint_after':plant})
            if kind not in ('calibration','prediction'): continue
            obs={'joint_position':[0.,.04]+[0.]*6,'joint_velocity':[0.]*8}
            for index in range(500 if kind=='calibration' else 200):
                command=[0.,0.] if index<100 else audit.guard.calibration_request(index-100,[1,1]) if kind=='calibration' else audit.guard.prediction_request('prediction',index-100,[1,1])
                rows.append({'trial_id':f'seed{seed}_{kind}','seed':seed,'kind':kind,'step_index':index,
                    'shared_transition_id':f'seed{seed}_{kind}:{index}','phase':'prefix' if index<100 else kind,
                    'observation_before':obs,'observation_after':obs,'requested_torque':command+[0.]*6,
                    'study_abort':None,'model_update':None,'diagnostics':{'executed_substeps':10,'terminated':False}})
    raw={'source_snapshot.zip':source_zip,'metadata.json':encode(am),'episodes.json':encode(episodes),
        'seed_results.json':encode(seeds),'trace.jsonl.gz':audit.gzip.compress(b'\n'.join(encode(r) for r in rows)+b'\n',mtime=0)}
    raw['manifest.json']=encode({n:audit.sha(b) for n,b in raw.items()});raw_hashes={n:audit.sha(b) for n,b in raw.items()}
    paid={'fixture_only':'handwritten paid history; zero actual physics','control_calls_attempted':0,'control_steps':0,'physics_steps':0,'model_updates':0}
    aa={'immutable_scope':audit.guard.SYNTHETIC_SPEC.record(),'failed':0,'violations':[],
        'final_gates':{'data_consistency_verified':True},'execution':{'source_git_verification_enabled':False},
        'audit_script_sha256':hashes[audit.guard.AUDITOR],'audit_dependency_sha256':{n:hashes[n] for n in audit.SUPPORT[:2]},
        'archive':{'seeds':derived,'budget':paid,'input_hashes':raw_hashes}}
    audit_blob=encode(aa)
    files={'raw/'+n:{'kind':'synthetic','source':'handwritten/'+n,'bytes':len(b),'sha256':audit.sha(b)} for n,b in raw.items()}
    files['first_audit.json']={'kind':'synthetic','source':'handwritten/audit','bytes':len(audit_blob),'sha256':audit.sha(audit_blob)}
    outer=encode({'files':files,'synthetic_fixture':True})
    members={**sources,audit.A_MANIFEST:outer,audit.A_AUDIT:audit_blob,**{audit.A_ROOT+'raw/'+n:b for n,b in raw.items()}}
    record={'schema':'c4-a-source-binding-v1','synthetic':True,'synthetic_fixture':True,'archive_root':audit.A_ROOT,
        'manifest':{'path':audit.A_MANIFEST,'sha256':audit.sha(outer)},'audit':{'path':audit.A_AUDIT,'sha256':audit.sha(audit_blob)},
        'raw_hashes':raw_hashes,'source_commit':'synthetic-fixture-no-git','source_sha256':hashes,'runtime':runtime,
        'A_paid_budget':paid,'calibration_ready':{str(s):True for s in (0,1,2)},'new_physical_calls':0,'new_model_updates':0,
        'scientific_A_contribution_required':False,'source_git_verified_by_binding':False}
    return None,members,{**deepcopy(runtime),'a_binding':record}

def test_independent_embedded_a_identity_and_stopped_diagonal(artificial_a):
    fixture,members,metadata=artificial_a
    seeds,record=audit.reconstruct_a(members,metadata,audit.SYNTHETIC_SPEC)
    assert all(s['calibration_ready'] for s in seeds.values())
    assert len(seeds[0]['calibration_transitions'])==400
    assert len(seeds[0]['prediction_transitions'])==100
    assert seeds[0]['reused_baselines']['learned_guard']['status']=='terminated'
    assert record==metadata['a_binding']

@pytest.mark.parametrize('field',['scope','data','failed','hashes','runtime','shared','raw','audit_dependency','duplicate_zip'])
def test_a_original_identity_tampering_rejected(artificial_a,field):
    fixture,members,metadata=artificial_a
    if field in ('scope','data','failed','hashes','audit_dependency'):
        original=audit.parse_json(members[audit.A_AUDIT])
        if field=='scope': original['immutable_scope']['control_steps']=1
        elif field=='data': original['final_gates']['data_consistency_verified']=False
        elif field=='failed': original['failed']=1
        elif field=='hashes': original['archive']['input_hashes']['trace.jsonl.gz']='0'*64
        else: original['audit_dependency_sha256']['scripts/audit_pair_frozen.py']='0'*64
        blob=json.dumps(original).encode();members[audit.A_AUDIT]=blob
        outer=audit.parse_json(members[audit.A_MANIFEST]);outer['files']['first_audit.json'].update(bytes=len(blob),sha256=audit.sha(blob))
        members[audit.A_MANIFEST]=json.dumps(outer).encode()
    elif field=='runtime': metadata['mujoco_version']='wrong'
    elif field=='shared': members['src/developmental_physics/environment.py']=b'changed'
    elif field=='raw': members[audit.A_ROOT+'raw/trace.jsonl.gz']=b'changed'
    else:
        original=members[audit.A_ROOT+'raw/source_snapshot.zip'];buffer=io.BytesIO(original)
        with zipfile.ZipFile(buffer,'a') as z:
            with pytest.warns(UserWarning): z.writestr('pyproject.toml',b'duplicate')
        blob=buffer.getvalue();members[audit.A_ROOT+'raw/source_snapshot.zip']=blob
        outer=audit.parse_json(members[audit.A_MANIFEST]);outer['files']['raw/source_snapshot.zip'].update(bytes=len(blob),sha256=audit.sha(blob))
        members[audit.A_MANIFEST]=json.dumps(outer).encode()
    with pytest.raises((ValueError,KeyError)): audit.reconstruct_a(members,metadata,audit.SYNTHETIC_SPEC)

def test_duplicate_json_and_nonfinite_never_accepted():
    with pytest.raises(ValueError): audit.parse_json(b'{"seed":0,"seed":1}')
    with pytest.raises(ValueError): audit.parse_json(b'{"x":NaN}')

@pytest.mark.parametrize('path',['../evil','/abs','C:/abs','a\\b','a//b',' a','a/./b'])
def test_source_paths_canonical(path):
    with pytest.raises(ValueError): audit.guard._path(path)
