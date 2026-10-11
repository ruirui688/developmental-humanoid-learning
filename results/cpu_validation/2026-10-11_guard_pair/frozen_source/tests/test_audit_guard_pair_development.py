"""Pure synthetic audit tests; no raw experiments, Git or physical calls."""
import ast
import copy
import importlib.util
import io
import json
from pathlib import Path
import sys
import zipfile
import pytest
ROOT=next(p for p in Path(__file__).resolve().parents if (p/'pyproject.toml').is_file())
source=Path(__file__).with_name('audit_guard_pair_development.py')
if not source.exists(): source=ROOT/'scripts/audit_guard_pair_development.py'
spec=importlib.util.spec_from_file_location('guard_independent_audit_test',source)
a=importlib.util.module_from_spec(spec);sys.modules[spec.name]=a;spec.loader.exec_module(a)

@pytest.fixture(autouse=True)
def forbid_git(monkeypatch):
    def forbidden(*args,**kwargs): raise AssertionError('Pure audit tests must not execute subprocess/Git.')
    monkeypatch.setattr(a.subprocess,'run',forbidden)
    monkeypatch.setattr(a.subprocess,'check_output',forbidden)

@pytest.mark.parametrize('basis',['raw_request','known_angle_guard'])
def test_initial_prior_endpoint_euler(basis):
    state=a.initial_state(basis,[[-1.,1.],[0.,2.]])
    q,v=a.predict(state['theta'],state['structure'],[0.,.4],[0.,.4],[.1,-.1],[.5,-.5])
    assert v==pytest.approx([.11,-.11]);assert q==pytest.approx([.0022,.3978])

@pytest.mark.parametrize('q,u,expected,blocked',[
    ([0.,.03],[0.,-.5],[0.,0.],[False,True]),
    ([0.,.0300001],[0.,-.5],[0.,-.5],[False,False]),
    ([0.,1.97],[0.,.5],[0.,0.],[False,True]),
    ([0.,1.97],[0.,-.5],[0.,-.5],[False,False]),
    ([0.,-.1],[0.,0.],[0.,0.],[False,False]),
    ([0.,1.],[3.,-3.],[.5,-.5],[False,False]),
])
def test_guard_equality_direction_clip(q,u,expected,blocked):
    got=a.describe_input(q,u,('known_angle_guard',((-1.,1.),(0.,2.))))
    assert got['projected_start_nm']==expected and got['start_blocked']==blocked and got['native_q_rad']==q


def test_raw_features_not_guarded_or_model_clipped():
    raw=a.features(('raw_request',((-1.,1.),(0.,2.))),[0.,0.],[0.,-.1],[0.,0.],[2.,-.5])
    guard=a.features(('known_angle_guard',((-1.,1.),(0.,2.))),[0.,0.],[0.,-.1],[0.,0.],[2.,-.5])
    assert raw[0][2:4]==[2.,1.75] and raw[1][2:4]==[-.5,-.25]
    assert guard[0][2:4]==[.5,.25] and guard[1][2:4]==[0.,0.]


def test_prediction_recomputes_guard_on_own_forecast_state():
    state=a.initial_state('known_angle_guard',[[-1.,1.],[0.,2.]])
    state['theta'][1]=[1.,0.,.2,0.,0.]
    q,v=[0.,.031],[0.,-.2]
    q1,v1=a.predict(state['theta'],state['structure'],[0.,.031],q,v,[0.,-.5])
    q2,v2=a.predict(state['theta'],state['structure'],[0.,.031],q1,v1,[0.,-.5])
    assert v1[1]==pytest.approx(-.3) and q1[1]<.03
    assert v2[1]==pytest.approx(-.3) # second request is blocked at predicted q


def test_rls_closed_form_zero_state_velocity_label():
    s=a.initial_state('raw_request',[[-1.,1.],[0.,2.]])
    x,p=a.propose_pair(s,[0.,.5],[0.,.5],[0.,0.],[0.,0.],[.2,-.2])
    assert x==[[0.,0.,0.,0.,1.]]*2
    assert p[0][0][-1]==pytest.approx(20/101)
    assert p[0][1][-1][-1]==pytest.approx(100/101)
    assert p[1][0][-1]==pytest.approx(-20/101)


def test_mpc_exhaustive_tie_and_count_zero_error():
    s=a.initial_state('raw_request',[[-1.,1.],[0.,2.]])
    d=a.replay_mpc(s['theta'],s['structure'],[0.,.5],[0.,.5],[0.,0.],[0.,.5],[0.,0.],[[-1.,1.],[0.,2.]])
    assert d['torque']==[0.,0.] and d['cost']==0. and d['feasible_candidates']==81
    assert d['pair_prediction_attempts']==81*15 and d['scalar_prediction_attempts']==2*81*15
    assert len(d['candidate_records'])==81


def test_mpc_all_infeasible_fallback_keeps_prediction_cost():
    s=a.initial_state('raw_request',[[-1.,1.],[0.,2.]])
    s['theta']=[[0.,0.,0.,0.,100.]]*2
    d=a.replay_mpc(s['theta'],s['structure'],[0.,.5],[0.,.5],[0.,0.],[0.,.5],[0.,0.],[[-1.,1.],[0.,2.]])
    assert d['fallback'] and d['torque']==[0.,0.] and d['pair_prediction_attempts']==81


def test_1_9_calibration_schedule_and_cost():
    commands=[a.calibration_request(k,[1,1]) for k in range(400)]
    assert commands[0]==[.125,0.] and commands[1]==[0.,0.] and commands[10]==[-.125,0.]
    assert commands[200]==[.125,.125] and commands[300]==[.125,-.125]
    assert [sum(abs(u[i]) for u in commands)*.02 for i in range(2)]==pytest.approx([.18,.18])
    assert [sum(u[i]**2 for u in commands)*.02 for i in range(2)]==pytest.approx([.06375,.06375])

@pytest.mark.parametrize('bad',[-1,400,True,1.])
def test_schedule_rejects_invalid_index(bad):
    with pytest.raises(ValueError): a.calibration_request(bad,[1,1])

def fake_seeds():
    rows=[]
    for seed in (0,1,2):
        ev={k:{'eligible':True,'completed':True,'status':'completed','study_aborted':False,'environment_terminated':False} for k in a.KINDS}
        for name,val in [('nominal_raw',1.),('nominal_guard',.9),('learned_raw',.7),('learned_guard',.6),('PDselected',.8),('zero',2.)]:
            ev[name].update(tracking_rmse_rad=val,tracking_rmse_by_axis_rad=[val,val],actual_effort_complete=True,
                control_effort={'actual_absolute_nm_s':[.01,.01],'actual_squared_nm2_s':[.01,.01]})
        ev['prediction']['velocity_prediction_rmse']={'nominal_raw':[1.,1.],'nominal_guard':[1.,1.],'learned_raw':[.7,.7],'learned_guard':[.7,.7]}
        rows.append({'seed':seed,'evaluations':ev})
    return rows


def test_scientific_contribution_and_pd_gates_known_positive():
    gates=a.scientific_gates(fake_seeds())
    assert all(v['passed'] for group in ('model_contribution','selected_pd_comparison') for v in gates[group].values())
    assert gates['public_rule_diagnostic']['learning_updates_compared']==0

@pytest.mark.parametrize('axis',[0,1])
def test_axis_degradation_cannot_hide_in_joint_mean(axis):
    rows=fake_seeds();rows[1]['evaluations']['learned_raw']['tracking_rmse_by_axis_rad'][axis]=1.
    assert not a.contribution_gate(rows,'raw')['passed'] and a.contribution_gate(rows,'guard')['passed']


def test_zero_tracking_denominator_fails_improvement_gate():
    rows=fake_seeds()
    for row in rows:
        row['evaluations']['nominal_raw'].update(tracking_rmse_rad=0.,tracking_rmse_by_axis_rad=[0.,0.])
        row['evaluations']['learned_raw'].update(tracking_rmse_rad=0.,tracking_rmse_by_axis_rad=[0.,0.])
    assert not a.contribution_gate(rows,'raw')['passed']


def test_zero_pd_effort_requires_zero_learned_effort():
    rows=fake_seeds()
    for row in rows: row['evaluations']['PDselected']['control_effort']['actual_absolute_nm_s']=[0.,0.]
    assert not a.pd_comparison_gate(rows,'guard')['passed']
    for row in rows: row['evaluations']['learned_guard']['control_effort']['actual_absolute_nm_s']=[0.,0.]
    assert a.pd_comparison_gate(rows,'guard')['passed']

@pytest.mark.parametrize('kind',['calibration','prediction','nominal_guard','learned_guard','PDselected'])
def test_incomplete_required_trial_blocks_validated_claim(kind):
    rows=fake_seeds();rows[0]['evaluations'][kind]['status']='terminated';rows[0]['evaluations'][kind]['eligible']=False
    assert not a.pd_comparison_gate(rows,'guard')['passed']

@pytest.mark.parametrize('change',[{'seeds':(20,21,22)},{'control_steps':2},{'joint_indices':(0,2)},{'protocol':'docs/other.md'}, {'scientific_gates_frozen':False}])
def test_production_scope_cannot_be_redefined(change):
    with pytest.raises(ValueError): a.GuardPairAuditSpec(**change)


def test_planned_budget_24_7500_75000_4800():
    plans=a.planned_matrix()
    assert len(plans)==24 and sum(p['maximum_control_steps'] for p in plans)==7500
    assert 10*sum(p['maximum_control_steps'] for p in plans)==75000 and 3*400*4==4800


def test_synthetic_scope_never_scientifically_frozen():
    assert not a.SYNTHETIC_SPEC.scientific_gates_frozen
    with pytest.raises(ValueError): a.GuardPairAuditSpec(synthetic_fixture=True,scientific_gates_frozen=True)

@pytest.mark.parametrize('bad',['{"x":1,"x":2}','{"x":NaN}','{"x":Infinity}'])
def test_strict_json_rejects_duplicate_nonstandard(bad):
    with pytest.raises(ValueError): a.parse_json(bad)


def test_auditor_has_no_online_or_third_party_imports():
    parsed=ast.parse(source.read_text(encoding='utf-8'))
    names=[]
    for node in ast.walk(parsed):
        if isinstance(node,ast.Import): names.extend(alias.name for alias in node.names)
        if isinstance(node,ast.ImportFrom): names.append(node.module or '')
    assert not any(name.startswith(('numpy','mujoco','developmental_physics')) for name in names)


def pd_identity_fixture():
    members={a.PD_PROTOCOL:b'synthetic protocol', 'scripts/audit_pair_pd.py':b'synthetic auditor', 'scripts/audit_local_frozen.py':b'synthetic support'}
    buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,'w') as archive:
        for name,raw in members.items(): archive.writestr(name,raw)
    sha=lambda raw:a.hashlib.sha256(raw).hexdigest()
    protocol={'path':a.PD_PROTOCOL,'sha256':sha(members[a.PD_PROTOCOL])}
    metadata=copy.deepcopy(a.PD_METADATA)
    metadata.update(environment_config=copy.deepcopy(a.ENVIRONMENT),protocol=protocol,source_snapshot_sha256=sha(buffer.getvalue()),source_sha256={name:sha(raw) for name,raw in members.items()})
    raw={'metadata.json':json.dumps(metadata).encode(),'source_snapshot.zip':buffer.getvalue(),
        'manifest.json':b'placeholder','episodes.json':b'forbidden','selection.json':b'forbidden','trace.jsonl.gz':b'forbidden'}
    audit={'validated_selection':True,'failed_checks':0,'source_git_verification_enabled':True,'immutable_scope':copy.deepcopy(a.PD_SCOPE),
        'selection':{'status':'selected','picked':{'candidate':4,'kp':[64.,64.],'kd':[1.,2.],'eligible':True,
            'sort_key':[.02,.03,.01,4],'paid_control_steps':900,'paid_physics_steps':9000}},
        'input_hashes':{name:sha(data) for name,data in raw.items()},
        'audit_sources_sha256':{'auditor':sha(members['scripts/audit_pair_pd.py']),'common':sha(members['scripts/audit_local_frozen.py'])}}
    manifest={'protocol':protocol,'files':{'raw/'+name:{'kind':'raw','source':'fixture/'+name,'bytes':len(data),'sha256':sha(data)} for name,data in raw.items()}}
    sources={a.PD_PROTOCOL:members[a.PD_PROTOCOL],a.PD_RAW_METADATA:raw['metadata.json'],a.PD_RAW_ZIP:raw['source_snapshot.zip'],
        a.PD_MANIFEST:json.dumps(manifest).encode(),a.PD_AUDIT:json.dumps(audit).encode()}
    selection={'schema':'c4-pd-selection-v1','status':'selected','selected':{'candidate_id':4,'joint_indices':[0,1],'kp':[64.,64.],'kd':[1.,2.]},
        'protocol':protocol,'sources':{label:{'path':name,'sha256':sha(sources[name])} for label,name in (('manifest',a.PD_MANIFEST),('audit',a.PD_AUDIT))}}
    sources[a.PD_SELECTION]=json.dumps(selection).encode();return sources


def test_pd_identity_independently_binds_five_archived_files():
    files=pd_identity_fixture();got=a.reconstruct_pd_binding(files)
    assert got['selected_id']==4 and got['kd']==[1.,2.] and got['audit_selection_confirmed']
    assert len(got['source_records'])==5 and not got['raw_trace_or_episodes_read']

@pytest.mark.parametrize('path',[a.PD_SELECTION,a.PD_MANIFEST,a.PD_AUDIT,a.PD_RAW_METADATA,a.PD_RAW_ZIP])
def test_pd_changed_source_bytes_rejected(path):
    files=pd_identity_fixture();files[path]+=b'x'
    with pytest.raises((ValueError,a.zipfile.BadZipFile)): a.reconstruct_pd_binding(files)

def native_row(index,*,n=10,stop=False):
    obs={'joint_position':[0.,.5]+[0.]*6,'joint_velocity':[0.]*8}
    return {'step_index':index,'observation_before':copy.deepcopy(obs),'observation_after':copy.deepcopy(obs),
        'requested_torque':[0.]*8,'diagnostics':{'executed_substeps':n,'terminated':stop},'study_abort':None}


def test_free_rollout_planned_denominator_retains_missing_windows():
    state=a.initial_state('raw_request',[[-1.,1.],[0.,2.]])
    rows=[native_row(100),native_row(101)]
    got=a.conditional_rollouts(rows,{'nominal_raw':state},[0.,.5],horizons=(2,),active_steps=5)
    out=got['models']['nominal_raw']['2']
    assert out['expected_windows_from_planned_active_duration']==4
    assert out['valid_windows']==1 and out['excluded_windows']==3 and out['exclusion_reasons']=={'missing_endpoint':3}


def test_partial_interval_does_not_enter_recursive_or_complete_metrics():
    state=a.initial_state('raw_request',[[-1.,1.],[0.,2.]])
    got=a.conditional_rollouts([native_row(100),native_row(101,n=3)],{'n':state},[0.,.5],horizons=(2,),active_steps=2)
    assert got['models']['n']['2']['valid_windows']==0
    assert got['models']['n']['2']['exclusion_reasons']=={'partial_interval':1}


def test_terminal_can_end_window_but_cannot_be_crossed():
    state=a.initial_state('raw_request',[[-1.,1.],[0.,2.]])
    rows=[native_row(100),native_row(101,stop=True),native_row(102)]
    got=a.conditional_rollouts(rows,{'n':state},[0.,.5],horizons=(2,),active_steps=3)['models']['n']['2']
    assert got['valid_windows']==1 and got['windows_ending_in_terminal']==1
    assert got['exclusion_reasons']=={'crosses_terminal':1}


def test_exception_diagnostic_cost_retains_success_before_failed_scalar():
    meter=a.empty_meter();meter.update(pair_prediction_attempts=2,pair_prediction_successes=1,
        scalar_prediction_attempts=3,scalar_prediction_successes=2,failed_pair_prediction_attempts=1)
    saved=a.meter_record(meter)
    exception={'shared_transition_id':'seed0_prediction:100','step_index':100,
        'predicted_next_qv':{'nominal_raw':[[0.,0.],[0.,0.]]},'diagnostic_prediction_accounting':saved,
        'failure_accounting':{'pair_prediction_accounting':{'scalar_prediction_attempts':1,'scalar_prediction_successes':0}}}
    checks=a.Checks();a.verify_diagnostic_accounting({'diagnostic_prediction_accounting':saved},[],[exception],'prediction',checks,'t',100)
    assert checks.failed==0


def test_unknown_failed_diagnostic_marks_scalar_lower_bound():
    meter=a.empty_meter();meter.update(pair_prediction_attempts=1,failed_pair_prediction_attempts=1,unknown_scalar_failure_count=1)
    saved=a.meter_record(meter)
    ex={'shared_transition_id':'x','step_index':100,'predicted_next_qv':{},'diagnostic_prediction_accounting':saved,'failure_accounting':{}}
    checks=a.Checks();a.verify_diagnostic_accounting({'diagnostic_prediction_accounting':saved},[],[ex],'nominal_raw',checks,'t',100)
    assert checks.failed==0 and saved['scalar_counts_is_lower_bound']

@pytest.mark.parametrize('change',[{'validated_selection':False},{'failed_checks':True},{'source_git_verification_enabled':False},{'immutable_scope':{'seeds':[0,1,2]}}])
def test_pd_semantic_tamper_rejected_after_all_outer_hashes_rebound(change):
    files=pd_identity_fixture();report=json.loads(files[a.PD_AUDIT]);report.update(change)
    files[a.PD_AUDIT]=json.dumps(report).encode()
    sel=json.loads(files[a.PD_SELECTION]);sel['sources']['audit']['sha256']=a.hashlib.sha256(files[a.PD_AUDIT]).hexdigest()
    files[a.PD_SELECTION]=json.dumps(sel).encode()
    with pytest.raises(ValueError): a.reconstruct_pd_binding(files)


def test_scope_mismatch_rejected_before_zip_trace_reads(tmp_path):
    (tmp_path/'metadata.json').write_text(json.dumps({'suite':'arbitrary','seeds':[0,1,2]}))
    with pytest.raises(ValueError,match='before trace or ZIP'): a.require_pair(tmp_path)
    assert list(tmp_path.iterdir())==[tmp_path/'metadata.json']

def test_exact_snapshot_whitelist_includes_core_informational_fields():
    state=a.initial_state('raw_request',[[-1.,1.],[0.,2.]])
    saved=a.parameter_record([0.,.5],state)
    saved.update(parameter_fingerprint=a.digest(saved),vector_update_count=0,scalar_update_count=0,output_update_counts=[0,0],trainable=True,
        initial_prior='generic velocity continuity and torque response; zero cross coefficients',
        input_boundary='current native q/v and already known requested u; no actual future torque or simulator state',
        update_commit='single immutable state reference for both outputs, covariance and counts')
    checks=a.Checks();a.verify_snapshot(saved,state,[0.,.5],checks,'s');assert checks.failed==0
    saved['privileged_hidden_feature']=1.
    bad=a.Checks();a.verify_snapshot(saved,state,[0.,.5],bad,'s');assert bad.failed>0

def test_native_retrieval_failure_can_preserve_last_confirmed_endpoint():
    endpoint={'joint_position':[0.]*8,'joint_velocity':[0.]*8}
    ex={'observation_after':endpoint,'qpos':[0.]*7+[.123]*8,'qvel':[0.]*6+[.2]*8,'returned_step_diagnostics':None,
        'observation_after_retrieval_error':{'type':'ValueError','message':'fixture current getter unavailable'}}
    checks=a.Checks();semantics=a.verify_exception_native_mapping(ex,checks,'e')
    assert checks.failed==0 and semantics['native_after_fallback_to_last_confirmed_endpoint']
    assert semantics['unreturned_snapshot_is_not_a_native_learning_label']
    ex.pop('observation_after_retrieval_error')
    current_checks=a.Checks();a.verify_exception_native_mapping(ex,current_checks,'e')
    assert current_checks.failed==1

def test_unreturned_paid_counters_bind_saved_failure_snapshot():
    ep={'control_steps':100,'physics_steps':1003,'environment_terminated':False}
    ex={'diagnostics':{'step_id':100,'physics_steps':1003,'time':2.006,'terminated':False}}
    checks=a.Checks();result=a.verify_exception_paid_counters(ex,ep,checks,'e')
    assert checks.failed==0 and result['paid_budget_bound_to_saved_failure_time_counters']
    bad_ep=dict(ep,physics_steps=1004)
    bad=a.Checks();a.verify_exception_paid_counters(ex,bad_ep,bad,'e');assert bad.failed==2

def test_unreturned_native_snapshot_can_be_current_but_is_not_rls_label():
    ex={'observation_after':{'joint_position':[.1]*8,'joint_velocity':[.2]*8},
        'qpos':[0.]*7+[.1]*8,'qvel':[0.]*6+[.2]*8,'returned_step_diagnostics':None}
    checks=a.Checks();result=a.verify_exception_native_mapping(ex,checks,'e')
    assert checks.failed==0 and result['native_after_current_failure_snapshot'] and result['unreturned_snapshot_is_not_a_native_learning_label']

@pytest.mark.parametrize('stage,attempts,successes',[('native_features',0,0),('velocity_output_0',1,0),('velocity_output_1',2,1),('endpoint_euler',2,2)])
def test_exact_known_pair_error_structured_failure_preserves_head_cost(stage,attempts,successes):
    meter=a.empty_meter();meter.update(pair_prediction_attempts=1,failed_pair_prediction_attempts=1,
        scalar_prediction_attempts=attempts,scalar_prediction_successes=successes)
    saved=a.meter_record(meter)
    ex={'shared_transition_id':'x','step_index':100,'predicted_next_qv':{},'diagnostic_prediction_accounting':saved,
        'failure_accounting':{'pair_prediction_accounting':None,'structured_failure':{'type':'PairPredictionError',
            'message':'fixture','scalar_prediction_attempts':attempts,'scalar_prediction_successes':successes,'failure_stage':stage}}}
    checks=a.Checks();a.verify_diagnostic_accounting({'diagnostic_prediction_accounting':saved},[],[ex],'prediction',checks,'e',100)
    assert checks.failed==0 and not saved['scalar_counts_is_lower_bound']
