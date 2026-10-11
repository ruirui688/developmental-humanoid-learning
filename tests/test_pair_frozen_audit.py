"""Synthetic standard-library audit checks; no simulator, real archives or fit calls."""
from copy import deepcopy
from dataclasses import replace
import importlib.util
import math
from pathlib import Path
import sys

import pytest

ROOT=next(p for p in Path(__file__).resolve().parents if (p/'pyproject.toml').is_file())
PATH=ROOT/'scripts/audit_pair_frozen.py'
if not PATH.is_file(): PATH=Path(__file__).with_name('audit_pair_frozen.py')
loader=importlib.util.spec_from_file_location('_pair_audit_synthetic',PATH)
a=importlib.util.module_from_spec(loader)
sys.modules[loader.name]=a
loader.loader.exec_module(a)

def snapshot(state,qref=(0.,0.),trainable=True):
    record=a.parameter_record(qref,state)
    return {**deepcopy(record),'parameter_fingerprint':a.digest(record),'trainable':trainable,
            'vector_update_count':state['count'],'scalar_update_count':2*state['count'],'output_update_counts':[state['count']]*2}

def update_record(state,row,qref=(0.,0.)):
    q=row['observation_before']['joint_position'][:2];v=row['observation_before']['joint_velocity'][:2]
    u=row['requested_torque'][:2];labels=row['observation_after']['joint_velocity'][:2]
    x,proposals=a.propose_pair(state,qref,q,v,u,labels)
    pq,pv=a.predict(state['theta'],state['structure'],qref,q,v,u)
    next_state=deepcopy(state);next_state['theta']=[p[0] for p in proposals];next_state['covariance']=[p[1] for p in proposals];next_state['count']+=1
    record={'phase':'identification','updated':True,'shared_transition_id':row['shared_transition_id'],
        'features_per_output':x,'preupdate_prediction':{'next_q_rad':pq,'next_v_rad_s':pv},
        'observed_next_v_rad_s':labels,'parameter_fingerprint_before':a.digest(a.parameter_record(qref,state)),
        'parameter_fingerprint_after':a.digest(a.parameter_record(qref,next_state)),
        'vector_update_count':next_state['count'],'scalar_update_count':2*next_state['count'],'committed_scalar_updates':2,
        'output_records':[{'output_index':i,'features':x[i],'observed_next_v_rad_s':labels[i],
            'preupdate_error_rad_s':p[2],'proposed_coefficients':p[0],'proposed_covariance':p[1],'committed':True} for i,p in enumerate(proposals)]}
    return record,next_state

def native(q=(0.,0.),v=(0.,0.),command=(0.,0.)):
    return {'joint_position':[*q,*[0.]*6],'joint_velocity':[*v,*[0.]*6],
            'imu_gyro':[0.]*3,'imu_acceleration':[0.]*3,'actuator_torque':[*command,*[0.]*6],
            'previous_command':[*command,*[0.]*6]}

def row(index=100,command=(.25,-.25),n=10,terminal=False):
    before=native();after=native((.0002,-.0004),(.01,-.02),command)
    request=[*command,*[0.]*6]
    d={'executed_substeps':n,'terminated':terminal,'step_id':index+1,'physics_steps':index*10+n,
       'time':(index*10+n)*.002,'requested_torque':request,'accepted_torque':request,
       'applied_torque_history':[request.copy() for _ in range(n)],'guarded_substeps':0,
       'applied_torque':request.copy(),'substep_ground_normal_forces':[1.]*n,'substep_kinetic_energies':[.1]*n,
       'substep_minimum_contact_distances':[-.001]*n,'peak_substep_ground_normal_force':1. if n else 0.,
       'ground_normal_impulse_ns':n*.002,'peak_substep_kinetic_energy':.1 if n else 0.,
       'minimum_substep_contact_distance':-.001 if n else 0.}
    return {'trial_id':'seed0_calibration','shared_transition_id':f'seed0_calibration:{index}','step_index':index,
        'phase':'calibration','joint_indices':[0,1],'requested_torque':request,'observation_before':before,
        'observation_after':after,'qpos':[0.]*7+after['joint_position'],'qvel':[0.]*6+after['joint_velocity'],
        'target_q':None,'study_abort':None,'diagnostics':d,'model_update':None}

@pytest.mark.parametrize('structure,n',[('diagonal_hinge5',5),('coupled_hinge9',9)])
def test_cold_heads_and_shape(structure,n):
    s=a.initial_state(structure)
    q,v=a.predict(s['theta'],structure,[.1,.2],[.12,.22],[.3,-.4],[.25,-.5])
    assert v==pytest.approx([.305,-.41])
    assert q==pytest.approx([.1261,.2118])
    assert len(s['theta'][0])==n and s['count']==0
    assert all(s['covariance'][head][i][i]==100. for head in range(2) for i in range(n))

def test_coupling_features_keep_both_original_axes():
    features=a.features('coupled_hinge9',[.1,.2],[.3,.5],[.7,-.8],[.5,-.5])
    assert features[0]==pytest.approx([.7,-.8,.2,.3,.5,-.5,.25,-.25,1.])
    assert features[0]==features[1]
    assert a.features('diagonal_hinge5',[.1,.2],[.3,.5],[.7,-.8],[.5,-.5])[1]==pytest.approx([-.8,.3,-.5,-.25,1.])

@pytest.mark.parametrize('n',[5,9])
def test_rls_analytic_label_update(n):
    theta=[0.]*n;cov=[[100. if i==j else 0. for j in range(n)] for i in range(n)]
    x=[0.]*(n-1)+[1.]
    after,p,res=a.replay_rls(theta,cov,x,2.)
    assert after[-1]==pytest.approx(200/101)
    assert p[-1][-1]==pytest.approx(100/101)
    assert res==2. and theta==[0.]*n and cov[-1][-1]==100.

def test_propose_does_not_commit_first_head_on_second_bad_label():
    s=a.initial_state('coupled_hinge9');before=deepcopy(s)
    with pytest.raises(ValueError): a.propose_pair(s,[0.,0.],[0.,0.],[0.,0.],[.25,.25],[.1,float('inf')])
    assert s==before

@pytest.mark.parametrize('structure',['diagonal_hinge5','coupled_hinge9'])
def test_replay_atomic_record_and_count(structure):
    s=a.initial_state(structure);r=row();item,after=update_record(s,r)
    checks=a.Checks();a.replay_update(item,r,s,[0.,0.],checks,'synthetic')
    assert checks.failed==0 and s['count']==1 and s['theta']==after['theta']

@pytest.mark.parametrize('field',['vector_update_count','scalar_update_count','committed_scalar_updates'])
def test_bool_counts_do_not_match_integer_record(field):
    s=a.initial_state('diagonal_hinge5');r=row();item,_=update_record(s,r);item[field]=True
    checks=a.Checks();a.replay_update(item,r,s,[0.,0.],checks,'synthetic')
    assert checks.failed>0

def test_native_pair_permission_and_unchanged_layout():
    r=row(index=0);checks=a.Checks()
    a.verify_transition(r,None,{'physics':0},[[-1.,1.]]*8,checks,'synthetic')
    assert checks.failed==0
    r['requested_torque'][2]=.1
    checks=a.Checks();a.verify_transition(r,None,{'physics':0},[[-1.,1.]]*8,checks,'synthetic')
    assert any(x['check']=='shared_permission_other_joints_zero' for x in checks.violations)

def test_reordering_native_encoders_is_rejected():
    r=row(index=0);r['qpos'][7],r['qpos'][8]=r['qpos'][8],r['qpos'][7]
    checks=a.Checks();a.verify_transition(r,None,{'physics':0},[[-1.,1.]]*8,checks,'synthetic')
    assert any(x['check']=='native_encoder_mapping' for x in checks.violations)

def test_partial_interval_requires_environment_stop():
    r=row(index=0,n=5,terminal=False);checks=a.Checks()
    a.verify_transition(r,None,{'physics':0},[[-1.,1.]]*8,checks,'synthetic')
    assert any(x['check']=='legal_partial_substeps' for x in checks.violations)

def test_five_pulse_schedule_and_exact_planned_effort():
    commands=[a.calibration_request(i,[1,-1]) for i in range(400)]
    assert commands[4]==[.125,0.] and commands[5]==[0.,0.] and commands[10]==[-.125,0.] and commands[15]==[0.,0.]
    assert commands[300]==[.125,.125]
    assert [sum(abs(u[i]) for u in commands)*.02 for i in range(2)]==pytest.approx([.9,.9])
    assert [sum(u[i]**2 for u in commands)*.02 for i in range(2)]==pytest.approx([.31875,.31875])
    assert a.prediction_request('prediction_full',5,[1,1])==[0.,0.]
    assert a.prediction_request('prediction_full',14,[1,1])==[-.125,0.]

@pytest.mark.parametrize('index',[True,-1,400])
def test_calibration_bad_index(index):
    with pytest.raises(ValueError): a.calibration_request(index,[1,1])

def test_exact_complete_budget_is_7200_not_7500():
    plan=a.planned_matrix()
    assert len(plan)==24 and sum(x['maximum_control_steps'] for x in plan)==7200
    assert sum(x['maximum_control_steps'] for x in plan if x['seed']==0)==2400

def test_mpc_all_81_grid_candidates_and_scalar_head_costs():
    s=a.initial_state('diagonal_hinge5')
    d=a.replay_mpc(s['theta'],s['structure'],[0.,0.],[0.,0.],[0.,0.],[0.,0.],[0.,0.],[[-1.,1.]]*2)
    assert d['torque']==[0.,0.] and d['feasible_candidates']==81 and len(d['candidate_records'])==81
    assert d['pair_prediction_attempts']==1215 and d['scalar_prediction_attempts']==2430
    assert d['candidate_records'][0]['torque']==[-.5,-.5] and d['candidate_records'][-1]['torque']==[.5,.5]
    assert not d['fallback'] and d['scalar_counts_complete']

def test_mpc_fallback_keeps_attempts_and_permission():
    s=a.initial_state('diagonal_hinge5')
    d=a.replay_mpc(s['theta'],s['structure'],[0.,0.],[0.,0.],[10.,10.],[0.,0.],[0.,0.],[[-1.,1.]]*2)
    assert d['fallback'] and d['torque']==[0.,0.] and d['pair_prediction_attempts']==81
    assert d['scalar_prediction_attempts']==162 and all(x['rejection_reason']=='forecast_position_bounds' for x in d['candidate_records'])

@pytest.mark.parametrize('target,previous', [([.16,0.],[0.,0.]),([0.,.99],[0.,0.]),([0.,0.],[.5001,0.])])
def test_mpc_rejects_infeasible_target_without_clipping(target,previous):
    s=a.initial_state('diagonal_hinge5')
    with pytest.raises(ValueError): a.replay_mpc(s['theta'],s['structure'],[0.,0.],[0.,0.],[0.,0.],target,previous,[[-1.,1.]]*2)

@pytest.mark.parametrize('axis',[0,1])
def test_study_any_axis_equal_threshold_and_prefix_exception(axis):
    q=[0.,0.];q[axis]=.12
    assert a.study_condition([0.,0.],q,[0.,0.],'control')['triggered']
    assert not a.study_condition([0.,0.],q,[1.,1.],'prefix')['triggered']
    v=[0.,0.];v[axis]=-1.
    assert a.study_condition([0.,0.],[0.,0.],v,'calibration')['triggered']

def test_partial_effort_and_lost_history_are_not_zero():
    r=row(index=0,n=5,terminal=True);effort=a.new_effort();a.add_effort(effort,r)
    assert effort['requested_absolute_nm_s']==pytest.approx([.0025,.0025])
    ev={'phase_effort':{'calibration':{key:[value*.5 for value in vals] if key in a.EFFORT_KEYS[2:] else [value*2 for value in vals] for key,vals in effort.items()}},
        'phase_actual_effort_substeps':{'calibration':5},'phase_actual_effort_complete':{'calibration':False},
        'phase_missing_actual_effort_substeps':{'calibration':5}}
    # Five recorded substeps and another five paid without saved history.
    ev['phase_effort']['calibration'][a.EFFORT_KEYS[2]]=effort[a.EFFORT_KEYS[2]].copy()
    ev['phase_effort']['calibration'][a.EFFORT_KEYS[3]]=effort[a.EFFORT_KEYS[3]].copy()
    ev['phase_effort_combined']={'calibration':{k:sum(v) for k,v in ev['phase_effort']['calibration'].items()}}
    checks=a.Checks();result=a.reconcile_effort(ev,'calibration',effort,10,5,[dict(r,phase='calibration')],checks,'synthetic')
    assert checks.failed==0 and result['unreconstructed_actual_substeps']==5 and not result['actual_reconstruction_complete']
    assert result['independent_lower_bound'][a.EFFORT_KEYS[2]]==pytest.approx([.0025,.0025])

def test_exception_later_model_failure_retains_earlier_commit():
    states={name:a.initial_state(a.STRUCTURES[name]) for name in ('diagonal','coupled')}
    regular=[row(index=i,command=(0.,0.)) for i in range(100)]
    last=row();item,updated=update_record(states['diagonal'],last)
    snapshots={'diagonal':snapshot(updated),'coupled':snapshot(states['coupled'])}
    exception={**last,'collector_exception':{'type':'SyntheticFailure'},'returned_step_diagnostics':last['diagnostics'],
        'partial_model_snapshots':snapshots,'model_update':None,'failure_accounting':{'structured_failure':{
        'failed_model':'coupled','completed_model_records':{'diagonal':item},'snapshots_after_attempt':snapshots,
        'shared_transition_id':last['shared_transition_id'],'failure_record':{'committed_scalar_updates':0,
            'proposed_outputs':[],'snapshot_after_attempt':snapshots['coupled']}}}}
    ep={'control_steps':101,'physics_steps':1010};checks=a.Checks()
    a.verify_exception_updates(exception,ep,regular,states,[0.,0.],checks,'synthetic')
    assert checks.failed==0 and states['diagonal']['count']==1 and states['coupled']['count']==0

def test_exception_after_commit_without_returned_record_is_reconstructed():
    states={name:a.initial_state(a.STRUCTURES[name]) for name in ('diagonal','coupled')}
    regular=[row(index=i,command=(0.,0.)) for i in range(100)];last=row()
    _,updated=update_record(states['diagonal'],last)
    exception={**last,'collector_exception':{'type':'KeyboardInterrupt'},'returned_step_diagnostics':last['diagnostics'],
        'partial_model_snapshots':{'diagonal':snapshot(updated),'coupled':snapshot(states['coupled'])},'model_update':None}
    checks=a.Checks();a.verify_exception_updates(exception,{'control_steps':101,'physics_steps':1010},regular,states,[0.,0.],checks,'synthetic')
    assert checks.failed==0 and states['diagonal']['count']==1

def test_partial_exception_cannot_claim_committed_update():
    states={name:a.initial_state(a.STRUCTURES[name]) for name in ('diagonal','coupled')}
    last=row(n=5,terminal=True);_,updated=update_record(states['diagonal'],last)
    exception={**last,'collector_exception':{'type':'SyntheticFailure'},'returned_step_diagnostics':last['diagnostics'],
        'partial_model_snapshots':{'diagonal':snapshot(updated),'coupled':snapshot(states['coupled'])},'model_update':None}
    checks=a.Checks();a.verify_exception_updates(exception,{'control_steps':101,'physics_steps':1005},[],states,[0.,0.],checks,'synthetic')
    assert checks.failed>0 and states['diagonal']['count']==0

def test_failure_committed_zero_cannot_hide_after_publish_two_heads():
    states={name:a.initial_state(a.STRUCTURES[name]) for name in ('diagonal','coupled')}
    regular=[row(index=i,command=(0.,0.)) for i in range(100)];last=row()
    _,updated=update_record(states['diagonal'],last)
    snapshots={'diagonal':snapshot(updated),'coupled':snapshot(states['coupled'])}
    exception={**last,'returned_step_diagnostics':last['diagnostics'],'partial_model_snapshots':snapshots,'model_update':None,
        'failure_accounting':{'structured_failure':{'failed_model':'diagonal','completed_model_records':{},
        'snapshots_after_attempt':snapshots,'shared_transition_id':last['shared_transition_id'],
        'failure_record':{'committed_scalar_updates':0,'proposed_outputs':[],'snapshot_after_attempt':snapshots['diagonal']}}}}
    checks=a.Checks();a.verify_exception_updates(exception,{'control_steps':101,'physics_steps':1010},regular,states,[0.,0.],checks,'synthetic')
    assert any(v['check']=='exact_label_or_count' and v['location']=='synthetic/failure_committed_from_final_state' for v in checks.violations)

def test_failed_model_proposal_numeric_tamper_rejected():
    states={name:a.initial_state(a.STRUCTURES[name]) for name in ('diagonal','coupled')}
    regular=[row(index=i,command=(0.,0.)) for i in range(100)];last=row()
    item,_=update_record(states['coupled'],last)
    proposal=deepcopy(item['output_records'][0]);proposal['committed']=False;proposal['proposed_coefficients'][0]+=1.
    snapshots={name:snapshot(state) for name,state in states.items()}
    exception={**last,'returned_step_diagnostics':last['diagnostics'],'partial_model_snapshots':snapshots,'model_update':None,
        'failure_accounting':{'structured_failure':{'failed_model':'coupled','completed_model_records':{},
        'snapshots_after_attempt':snapshots,'shared_transition_id':last['shared_transition_id'],
        'failure_record':{'committed_scalar_updates':0,'proposed_outputs':[proposal],'snapshot_after_attempt':snapshots['coupled']}}}}
    checks=a.Checks();a.verify_exception_updates(exception,{'control_steps':101,'physics_steps':1010},regular,states,[0.,0.],checks,'synthetic')
    assert any(v['check']=='numeric_recomputation' for v in checks.violations)

def successful_seed(seed):
    ev={k:{'eligible':True,'completed':True,'status':'completed','study_aborted':False,'environment_terminated':False} for k in a.KINDS}
    for k,err in [('nominal_mpc',1.),('diagonal_mpc',.7),('coupled_mpc',.6),('combined_pd',.8),('zero_torque',2.)]:
        ev[k].update(tracking_rmse_rad=err,tracking_rmse_by_axis_rad=[err,err],actual_effort_complete=True,
            control_effort={key:[1.,1.] for key in a.EFFORT_KEYS})
    for k in ('prediction_low','prediction_full'):
        ev[k]['velocity_prediction_rmse']={'nominal':[1.,1.],'diagonal':[.7,.7],'coupled':[.6,.6]}
    return {'seed':seed,'evaluations':ev}

def test_independent_contribution_increment_and_matrix_gates():
    seeds=[successful_seed(i) for i in (0,1,2)]
    seeds[0]['evaluations']['zero_torque']['completed']=False
    seeds[1]['evaluations']['combined_pd']['completed']=False
    gates=a.scientific_gates(seeds)
    assert gates['diagonal_contribution']['passed'] and gates['coupled_contribution']['passed'] and gates['coupled_increment']['passed']
    assert not gates['complete_matrix'] and not gates['combined_pd_comparison']['coupled']['passed']
    assert gates['thresholds_frozen']
    assert not a.scientific_gates(seeds, replace(a.PAIR_DEVELOPMENT_SPEC, scientific_gates_frozen=False))['thresholds_frozen']

def test_shoulder_gain_cannot_hide_elbow_tracking_regression():
    seeds=[successful_seed(i) for i in (0,1,2)]
    for sr in seeds: sr['evaluations']['coupled_mpc']['tracking_rmse_by_axis_rad']=[.1,1.1]
    gates=a.scientific_gates(seeds)
    assert not gates['coupled_contribution']['passed'] and not gates['coupled_increment']['passed']

def test_increment_per_axis_non_degradation_even_when_joint_improves():
    seeds=[successful_seed(i) for i in (0,1,2)]
    seeds[0]['evaluations']['coupled_mpc']['tracking_rmse_by_axis_rad']=[.1,.71]
    assert not a.comparison_gate(seeds,'diagonal_mpc','coupled_mpc',a.PAIR_DEVELOPMENT_SPEC,require_predictions=True)['passed']

def test_combined_pd_comparison_cannot_hide_one_axis_regression():
    seeds=[successful_seed(i) for i in (0,1,2)]
    seeds[0]['evaluations']['coupled_mpc']['tracking_rmse_by_axis_rad']=[.1,.81]
    assert not a.scientific_gates(seeds)['combined_pd_comparison']['coupled']['passed']

def test_combined_pd_comparison_requires_own_model_contribution():
    seeds=[successful_seed(i) for i in (0,1,2)]
    seeds[0]['evaluations']['prediction_low']['velocity_prediction_rmse']['coupled']=[.81,.6]
    gates=a.scientific_gates(seeds)
    assert not gates['coupled_contribution']['passed']
    assert not gates['combined_pd_comparison']['coupled']['passed']
    assert gates['combined_pd_comparison']['diagonal']['passed']

def test_synthetic_default_sources_are_tracked_and_legacy_override_is_exact():
    spec=replace(a.PAIR_DEVELOPMENT_SPEC,synthetic_fixture=True)
    assert 'src/developmental_physics/pair_frozen_validation.py' in spec.required_sources
    assert 'scripts/audit_pair_frozen.py' in spec.required_sources
    assert 'scripts/audit_local_frozen.py' in spec.required_sources
    assert all(not name.startswith('external/') for name in spec.required_sources)
    with pytest.raises(ValueError): replace(spec,fixture_source='external/unregistered.py')
    legacy=replace(spec,fixture_source='external/c4b_pair_staging/pair_frozen_validation.py')
    assert legacy.fixture_source in legacy.required_sources

def test_tracking_zero_denominator_fails_mean_improvement():
    seeds=[successful_seed(i) for i in (0,1,2)]
    for sr in seeds:
        sr['evaluations']['nominal_mpc'].update(tracking_rmse_rad=0.,tracking_rmse_by_axis_rad=[0.,0.])
    assert not a.model_gate(seeds,'coupled',a.PAIR_DEVELOPMENT_SPEC)['passed']

def test_protocol_scope_and_bool_zero_gains_rejected_before_trace(monkeypatch):
    metadata={'suite':'pair_development','pose':'supine','joint_indices':[0,1],'seeds':[0,1,2],
        'split':'development','pd_gains':{'kp':[64.,64.],'kd':[False,1.]},'synthetic':False,'native_joint_count':8,
        'protocol':{'path':'docs/PAIR_BODY_DEVELOPMENT_PROTOCOL.md'}}
    monkeypatch.setattr(a,'load_json',lambda _:metadata)
    with pytest.raises(ValueError): a.require_pair(Path('synthetic_only'))

def test_synthetic_never_formal_and_audit_dependencies_are_reported(monkeypatch):
    metadata={'suite':'pair_development','pose':'supine','joint_indices':[0,1],'seeds':[0,1,2],
        'split':'development','pd_gains':{'kp':[64.,64.],'kd':[0.,1.]},'synthetic':True,'native_joint_count':8,
        'protocol':{'path':'docs/PAIR_BODY_DEVELOPMENT_PROTOCOL.md'}}
    monkeypatch.setattr(a,'load_json',lambda _:metadata)
    def forbidden(*args,**kwargs): raise AssertionError('No ZIP/trace read before scope binding.')
    monkeypatch.setattr(a.common.zipfile,'ZipFile',forbidden);monkeypatch.setattr(a.gzip,'open',forbidden)
    result=a.audit(Path('synthetic_only'),spec=replace(a.PAIR_DEVELOPMENT_SPEC,scientific_gates_frozen=True))
    assert result['checks']==result['failed']==1
    assert not result['final_gates']['coupled_contribution']['validated_pass']
    assert result['audit_dependency_sha256']=={'scripts/audit_local_frozen.py':a.file_hash(a.ROOT/'scripts/audit_local_frozen.py')}

@pytest.mark.parametrize('kwargs',[{'seeds':(0,), 'reset_seed_pairs':((0,3757552657),)}, {'prefix_steps':2}, {'control_steps':2}])
def test_fixture_shortcuts_require_explicit_synthetic_scope(kwargs):
    with pytest.raises(ValueError): replace(a.PAIR_DEVELOPMENT_SPEC,**kwargs)

@pytest.mark.parametrize('field,value',[('joint_indices',[1,0]),('seeds',[20,21,22]),('synthetic',True),('native_joint_count',2)])
def test_wrong_scope_rejected(field,value,monkeypatch):
    metadata={'suite':'pair_development','pose':'supine','joint_indices':[0,1],'seeds':[0,1,2],
        'split':'development','pd_gains':{'kp':[64.,64.],'kd':[0.,1.]},'synthetic':False,'native_joint_count':8,
        'protocol':{'path':'docs/PAIR_BODY_DEVELOPMENT_PROTOCOL.md'}}
    metadata[field]=value;monkeypatch.setattr(a,'load_json',lambda _:metadata)
    with pytest.raises(ValueError): a.require_pair(Path('synthetic_only'))

def test_conditional_rollout_future_requests_are_offline_labels():
    rows=[row(index=i,command=(0.,0.)) for i in range(100,103)]
    result=a.conditional_rollouts(rows,{'nominal':a.initial_state('diagonal_hinge5')},[0.,0.],horizons=(2,))
    assert result['recorded_future_requests_are_offline_labels'] and result['online_future_information'] is False
    assert result['models']['nominal']['2']['valid_windows']==2
    rows[0]['diagnostics']['executed_substeps']=5
    assert a.conditional_rollouts(rows,{},[0.,0.],horizons=(2,))['models']['persistence']['2']['exclusion_reasons']['partial_interval']==1

def test_conditional_rollout_cross_terminal_excluded_but_terminal_endpoint_kept():
    rows=[row(index=i,command=(0.,0.)) for i in range(100,103)]
    rows[1]['diagnostics']['terminated']=True
    result=a.conditional_rollouts(rows,{},[0.,0.],horizons=(2,))['models']['persistence']['2']
    assert result['valid_windows']==1 and result['windows_ending_in_terminal']==1 and result['exclusion_reasons']['crosses_terminal']==1

def test_planned_tail_uses_plan_denominator_and_marks_last_stop():
    rows=[row(index=i,command=(0.,0.)) for i in range(180,200)]
    rows[-1]['diagnostics']['terminated']=True
    tails=a.planned_tail_metrics(rows,[0.,0.],[1,1])
    tail=next(r for r in tails if r['label']=='planned_tail' and r['active_interval']==[80,99])
    assert tail['planned_endpoints']==20 and tail['complete_endpoints']==20 and not tail['complete_window']
