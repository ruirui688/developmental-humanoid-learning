"""Pure synthetic C5 engineering tests: no MuJoCo import/factory or real Git."""
from copy import deepcopy
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import zipfile

import pytest

if Path(__file__).with_name('engineering_runner.py').exists():
    spec=importlib.util.spec_from_file_location('c5_engineering_draft',Path(__file__).with_name('engineering_runner.py'))
    core=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(core)
else:
    from developmental_physics import c5_engineering as core


class FakeData:
    def __init__(self):
        self.qpos=[0.]*15;self.qvel=[0.]*14;self.ctrl=[0.]*8
        self.time=0.;self._force=[0.]*8;self._force_unreadable=False;self.sensordata=[0.]*6

    @property
    def actuator_force(self):
        if self._force_unreadable:
            raise OSError('post-return force read failure')
        return self._force.copy()


class FakeEnv:
    """Small deterministic arithmetic stub, not a physical simulator."""
    def __init__(self,backend,kind):
        self.backend=backend;self.kind=kind;self.fault=backend.faults.get(kind,{})
        self._joint_ids=[4,1,7,0,6,2,5,3]
        dof=[9,6,11,7,13,8,10,12]
        qadr=[x+1 for x in dof]
        self._joint_dof=[dof[j] for j in self._joint_ids]
        self._joint_qpos=[qadr[j] for j in self._joint_ids]
        self.model=SimpleNamespace(jnt_dofadr=dof,jnt_qposadr=qadr,
            dof_armature=[0.]*6+[.01]*8,nv=14,opt=SimpleNamespace(timestep=.002),
            jnt_range=[[-2.,2.] for _ in range(8)],
            actuator_gainprm=[[1.]+[0.]*9 for _ in range(8)],
            actuator_biasprm=[[0.]*10 for _ in range(8)],
            actuator_gear=[[1.]+[0.]*5 for _ in range(8)],
            actuator_trnid=[[j,-1] for j in self._joint_ids],
            actuator_ctrlrange=[[-.5,.5] for _ in range(8)],
            actuator_ctrllimited=[True]*8,actuator_forcelimited=[False]*8,
            actuator_dyntype=[0]*8,actuator_gaintype=[0]*8,
            actuator_biastype=[0]*8,actuator_trntype=[0]*8)
        self.model.joint=lambda name: SimpleNamespace(id=self._joint_ids[core.JOINTS.index(name)])
        self.config=SimpleNamespace(physics_dt=.002,control_substeps=10)
        self.data=FakeData();self.action_limits=[.5]*8;self.last_command=[0.]*8
        self.physics_steps=self.step_id=0;self.gains=[1.]*8
        self.events=[];self.kernel_calls=0;self.request_history=[]
        if self.fault.get('bad_asset'):
            self.model.actuator_gainprm[0][0]=2.

    def reset(self,seed=0,pose='supine'):
        self.backend.reset_calls.append((self.kind,seed,pose))
        if self.fault.get('reset_paid'):
            self.physics_steps=7;self.step_id=2;self.data.time=.014
        return self.observation()

    def parameter_fingerprint(self):
        return hashlib.sha256(json.dumps([self.gains,self.model.dof_armature]).encode()).hexdigest()

    def base_model_fingerprint(self):
        return hashlib.sha256(json.dumps(self.model.dof_armature).encode()).hexdigest()

    def observation(self):
        result={'joint_position':[self.data.qpos[i] for i in self._joint_qpos],
            'joint_velocity':[self.data.qvel[i] for i in self._joint_dof],
            'actuator_torque':self.data._force.copy(),'previous_command':self.last_command.copy(),
            'imu_gyro':[0.]*3,'imu_acceleration':[0.,0.,9.81]}
        if self.fault.get('bad_observation_after')==self.step_id:
            result['joint_velocity'][0]=float('nan')
        return result

    def set_channel_gains(self,gains):
        self.events.append(('gain',self.step_id,list(gains)));self.gains=list(gains)
        if self.fault.get('event_ctrl_mutation'):
            self.data.ctrl[0]+=.1
        return {'event_type':'channel_gains','status':'applied','proposal':list(gains)}

    def change_armature(self,indices,values):
        self.events.append(('armature',self.step_id,list(indices),list(values)))
        for i,value in zip(indices,values): self.model.dof_armature[self._joint_dof[i]]=value
        if self.fault.get('event_failure'):
            exc=RuntimeError('assigned armature then forward failed')
            exc.parameter_event_record={'status':'failed','parameter_assignment_completed':True}
            raise exc
        return {'event_type':'armature','status':'applied','dof_indices':[self._joint_dof[i] for i in indices]}

    def step(self,requested):
        self.request_history.append(list(requested))
        accepted=[max(-limit,min(limit,u)) for limit,u in zip(self.action_limits,requested)]
        self.last_command=accepted.copy();scaled=[a*g for a,g in zip(accepted,self.gains)]
        terminated=False;executed=0
        for substep in range(10):
            angles=[self.data.qpos[q] for q in self._joint_qpos]
            ranges=[self.model.jnt_range[j] for j in self._joint_ids]
            guard=[(q<=r[0]+.03 and u<0.) or (q>=r[1]-.03 and u>0.) for q,r,u in zip(angles,ranges,scaled)]
            self.data.ctrl=[0. if stop else u for stop,u in zip(guard,scaled)]
            if self.fault.get('wrong_ctrl') and self.step_id==100:
                self.data.ctrl[0]+=.1
            self.backend.module.mj_step(self.model,self.data)
            self.physics_steps+=1;executed+=1
            if self.fault.get('environment_stop')==self.step_id and substep==2:
                terminated=True;break
        self.step_id+=1
        if self.fault.get('study_stop') and self.step_id==101:
            self.data.qvel[self._joint_dof[0]]=1.
        return SimpleNamespace(observation=self.observation(),terminated=terminated,
            diagnostics={'executed_substeps':executed,'physics_steps':self.physics_steps})


class FakeBackend:
    synthetic=True
    versions={'backend':'pure arithmetic fixture','mujoco':'NOT IMPORTED','device':'cpu'}
    source_bytes={}

    def __init__(self,faults=None):
        self.faults=faults or {};self.environments=[];self.reset_calls=[];self.mass_calls=0
        self.module=SimpleNamespace(mj_step=self.original_step)
        self.original=self.module.mj_step

    def fresh(self,kind):
        env=FakeEnv(self,kind);self.environments.append(env);return env

    def original_step(self,model,data):
        env=next(e for e in self.environments if e.data is data)
        env.kernel_calls+=1
        if env.fault.get('kernel_exception')==env.kernel_calls:
            data.time+=.001  # Unknown partial internal work; caller cannot certify one full step.
            raise RuntimeError('original kernel did not return')
        data._force=data.ctrl.copy()
        if env.fault.get('wrong_force') and env.step_id==100: data._force[0]+=.01
        for i,(q,d) in enumerate(zip(env._joint_qpos,env._joint_dof)):
            data.qvel[d]+=data.ctrl[i]*.002
            data.qpos[q]+=data.qvel[d]*.002
        data.time+=.002
        if env.fault.get('postforce_exception')==env.kernel_calls:
            data._force_unreadable=True

    def mass_matrix(self,env):
        self.mass_calls+=1
        matrix=[[0.]*14 for _ in range(14)]
        for i in range(14): matrix[i][i]=1.+env.model.dof_armature[i]
        if env.fault.get('wrong_mass') and env.model.dof_armature[env._joint_dof[0]]==.02:
            matrix[0][0]+=.1
        return {'qpos':env.data.qpos.copy(),'matrix':matrix,'diagnostic_only':True,'physics_substeps_added':0}


def run(tmp_path,backend=None,name='run'):
    backend=backend or FakeBackend()
    metadata=core.run_engineering(tmp_path/name,backend,synthetic=True)
    return metadata,backend,tmp_path/name


def read_rows(output):
    with gzip.open(output/'trace.jsonl.gz','rt',encoding='utf-8') as stream:
        return [json.loads(line) for line in stream]


def test_fixed_full_plan_fresh_environment_events_identity_and_effort(tmp_path):
    metadata,backend,output=run(tmp_path)
    assert metadata['all_four_complete'] and metadata['fatal'] is None
    assert metadata['actual_budget']=={'control_calls_attempted':480,'control_steps':480,
        'known_physics_substeps_lower_bound':4800,'unknown_original_step_attempts':0,
        'returned_endpoints':480,'model_parameter_updates':0}
    assert metadata['identity_check']['validated_identity']
    assert metadata['identity_check']['serialized_native_state_history_exact']
    assert metadata['identity_check']['maximum_absolute_difference']==0.
    assert backend.module.mj_step is backend.original
    assert backend.reset_calls==[(k,3757552657,'supine') for k in core.KINDS]
    assert backend.mass_calls==8
    for env in backend.environments:
        assert env.request_history[:100]==[[0.]*8]*100
        assert env.request_history[100:]==[[.25,.25]+[0.]*6]*5+[[0.]*8]*5+[[-.25,-.25]+[0.]*6]*5+[[0.]*8]*5
        assert env.kernel_calls==1200
        assert all(event[1]==100 for event in env.events)
    outcomes=json.loads((output/'trial_outcomes.json').read_text())
    assert outcomes[0]['known_requested_effort_by_joint'][0]['absolute_nm_s']==pytest.approx(.05)
    assert outcomes[2]['known_actual_force_effort_by_joint'][0]['absolute_nm_s']==pytest.approx(.025)
    assert outcomes[0]['known_actual_force_effort_by_joint'][0]['absolute_nm_s']==pytest.approx(.05)
    events=json.loads((output/'parameter_events.json').read_text())
    assert len(events)==4
    changed=events[3]['mass_matrix_change']
    assert changed['selected_native_dof_indices']==backend.environments[3]._joint_dof[:2]
    assert changed['maximum_absolute_error_from_expected_delta']<=1e-12
    assert all(e['before_live']['ctrl']==e['after_live']['ctrl'] for e in events)
    with zipfile.ZipFile(output/'source_snapshot.zip') as archive:
        for name,value in metadata['source_sha256'].items():
            assert hashlib.sha256(archive.read(name)).hexdigest()==value
    manifest=json.loads((output/'manifest.json').read_text())
    assert all(hashlib.sha256((output/name).read_bytes()).hexdigest()==value for name,value in manifest.items())
    rows=read_rows(output)
    assert len(rows)==480 and all(set(row['observation_after'])==set(core.OBS_FIELDS) for row in rows)
    assert all(len(row['actual_substep_history'])==10 for row in rows)


def test_native_lookup_mapping_not_numeric_joint_ids(tmp_path):
    _,backend,output=run(tmp_path)
    outcome=json.loads((output/'armature_double_outcome.json').read_text())
    mapping=outcome['initial_native_mapping']
    assert mapping['joint_ids']==[4,1,7,0,6,2,5,3]
    assert mapping['dof_indices']==[13,6,12,9,10,11,8,7]
    assert mapping['qpos_indices']==[14,7,13,10,11,12,9,8]
    env=backend.environments[3]
    assert env.model.dof_armature[13]==env.model.dof_armature[6]==.02
    assert all(value==.01 for i,value in enumerate(env.model.dof_armature) if i>=6 and i not in (13,6))


def test_gain_event_keeps_nonzero_held_ctrl_and_next_request_scaling():
    backend=FakeBackend();env=backend.fresh('gain_half');env.reset()
    env.data.ctrl=[.4,-.3]+[.2]*6;env.last_command=[.4]*8
    snapshot=core.live_snapshot(env);mapping=core.asset_audit(env)
    event=core.boundary_event('gain_half',env,mapping,backend.mass_matrix)
    assert event['before_live']['ctrl']==event['after_live']['ctrl']==snapshot['ctrl']
    assert env.last_command==snapshot['last_command'] and env.kernel_calls==0
    meter=core.SubstepMeter(backend.module,env,mapping);meter.accepted=[.25,.25]+[0.]*6;meter.gains=env.gains
    with meter.installed(): env.step([.25,.25]+[0.]*6)
    assert all(record['before_ctrl_nm'][:2]==[.125,.125] for record in meter.records)
    assert env.observation()['previous_command'][:2]==[.25,.25]


def test_guard_uses_scaled_request_pre_angle_and_actual_unit_force():
    backend=FakeBackend();env=backend.fresh('gain_half');env.reset();env.gains=[.5,.5]+[1.]*6
    env.data.qpos[env._joint_qpos[0]]=1.98
    mapping=core.asset_audit(env);meter=core.SubstepMeter(backend.module,env,mapping)
    meter.accepted=[.25,.25]+[0.]*6;meter.gains=env.gains
    with meter.installed(): env.step([.25,.25]+[0.]*6)
    assert all(record['independently_expected_guard'][0] for record in meter.records)
    assert all(record['before_ctrl_nm'][:2]==[0.,.125] for record in meter.records)
    assert all(record['unit_motor_force_match'] for record in meter.records)


@pytest.mark.parametrize('fault,expected_calls,expected_known,expected_unknown',[('kernel_exception',1,0,1),('postforce_exception',1,1,0)])
def test_kernel_failure_or_post_force_failure_preserves_paid_gap_and_restores_api(tmp_path,fault,expected_calls,expected_known,expected_unknown):
    metadata,backend,output=run(tmp_path,FakeBackend({'base_identity':{fault:1}}))
    assert len(backend.environments)==1
    assert backend.module.mj_step is backend.original
    assert metadata['actual_budget']['control_calls_attempted']==expected_calls
    assert metadata['actual_budget']['known_physics_substeps_lower_bound']==expected_known
    assert metadata['actual_budget']['unknown_original_step_attempts']==expected_unknown
    assert metadata['outcome_counts']=={'exception':1,'blocked':3}
    outcome=json.loads((output/'base_identity_outcome.json').read_text())
    assert outcome['actual_history_is_lower_bound'] and outcome['actual_budget_is_lower_bound']
    assert outcome['known_actual_force_substeps']==0
    assert len(outcome['partial_instrumentation'])==1
    record=outcome['partial_instrumentation'][0]
    assert record['original_mj_step_attempted'] and record['original_mj_step_returned']==bool(expected_known)
    assert backend.environments[0].physics_steps==0  # post-force read precedes env increment.
    for kind in core.KINDS[1:]:
        blocked=json.loads((output/(kind+'_outcome.json')).read_text())
        assert blocked['status']=='blocked' and blocked['control_calls_attempted']==0


@pytest.mark.parametrize('fault',['wrong_ctrl','wrong_force'])
def test_instrumentation_mismatch_fatal_with_correct_pre_kernel_or_post_kernel_cost(tmp_path,fault):
    metadata,backend,output=run(tmp_path,FakeBackend({'base_identity':{fault:True}}))
    assert metadata['actual_budget']['control_calls_attempted']==101
    expected=1000 if fault=='wrong_ctrl' else 1001
    assert metadata['actual_budget']['known_physics_substeps_lower_bound']==expected
    assert len(backend.environments)==1 and backend.module.mj_step is backend.original
    partial=json.loads((output/'base_identity_outcome.json').read_text())['partial_instrumentation']
    assert len(partial)==1 and partial[0]['original_mj_step_attempted']==(fault=='wrong_force')


def test_returned_endpoint_observation_failure_counts_all_ten_paid_substeps(tmp_path):
    metadata,_,output=run(tmp_path,FakeBackend({'base_identity':{'bad_observation_after':1}}))
    assert metadata['actual_budget']['known_physics_substeps_lower_bound']==10
    assert metadata['actual_budget']['control_steps']==1
    assert metadata['actual_budget']['returned_endpoints']==0
    assert len(read_rows(output))==0 and metadata['outcome_counts']=={'exception':1,'blocked':3}


def test_bad_reset_does_not_get_free_known_interactions(tmp_path):
    metadata,_,_=run(tmp_path,FakeBackend({'base_identity':{'reset_paid':True}}))
    assert metadata['actual_budget']['control_calls_attempted']==0
    assert metadata['actual_budget']['control_steps']==2
    assert metadata['actual_budget']['known_physics_substeps_lower_bound']==7
    assert metadata['outcome_counts']=={'exception':1,'blocked':3}


@pytest.mark.parametrize('fault',['study_stop','environment_stop'])
def test_ordinary_stop_only_ends_current_trial_next_fresh_continues(tmp_path,fault):
    value=True if fault=='study_stop' else 3
    metadata,backend,output=run(tmp_path,FakeBackend({'base_identity':{fault:value}}))
    assert len(backend.environments)==4 and metadata['fatal'] is None
    assert metadata['outcome_counts']=={'terminated':1,'completed':3}
    outcome=json.loads((output/'base_identity_outcome.json').read_text())
    assert outcome['control_calls_attempted']==(101 if fault=='study_stop' else 4)
    assert outcome['known_physics_substeps_lower_bound']==(1010 if fault=='study_stop' else 33)
    assert outcome['stop_step_index']==(100 if fault=='study_stop' else 3)
    assert not metadata['identity_check']['validated_identity']


@pytest.mark.parametrize('signal,value,expect_stop',[('q',.12,True),('q',-.12,True),('q',.119,False),('v',1.,True),('v',-1.,True),('v',.999,False)])
def test_study_exact_thresholds_and_prefix_exemption(signal,value,expect_stop):
    obs={k:[0.]*n for k,n in core.OBS_FIELDS.items()}
    obs['joint_position' if signal=='q' else 'joint_velocity'][1]=value
    assert (core.study_stop(obs,[0.,0.],100) is not None)==expect_stop
    assert core.study_stop(obs,[0.,0.],99) is None


@pytest.mark.parametrize('fault,kind',[('bad_asset','base_identity'),('event_ctrl_mutation','gain_half'),('event_failure','armature_double'),('wrong_mass','armature_double')])
def test_asset_event_and_same_q_mass_mismatch_are_fatal_without_retry(tmp_path,fault,kind):
    metadata,backend,output=run(tmp_path,FakeBackend({kind:{fault:True}}))
    assert len(backend.environments)==core.KINDS.index(kind)+1
    assert metadata['fatal']['kind']==kind
    outcome=json.loads((output/(kind+'_outcome.json')).read_text())
    assert outcome['known_physics_substeps_lower_bound']==(0 if fault=='bad_asset' else 1000)
    if fault!='bad_asset':
        assert outcome['failed_request'] is None and outcome['exception']['phase']=='event'
        assert outcome['parameter_event']['status']=='failed'
    if fault=='event_failure':
        assert outcome['parameter_event']['environment_event']['parameter_assignment_completed']
        assert outcome['final_live_state']['armature'][backend.environments[-1]._joint_dof[0]]==.02
    assert backend.module.mj_step is backend.original


@pytest.mark.parametrize('key,replacement',[('joint_position',[0.]*7),('imu_gyro',[float('inf')]*3),('joint_velocity',[True]*8)])
def test_native_finite_length_and_numeric_schema(key,replacement):
    obs={k:[0.]*n for k,n in core.OBS_FIELDS.items()};obs[key]=replacement
    with pytest.raises(ValueError): core.native_observation(obs)


def test_hidden_observation_key_refused():
    obs={k:[0.]*n for k,n in core.OBS_FIELDS.items()};obs['hidden_gain']=[.5]*8
    with pytest.raises(ValueError,match='hidden fields'): core.native_observation(obs)


def test_identity_checks_all_numeric_leaves_after_first_mismatch():
    row={'observation_before':[0.,0.,0.],'observation_after':[], 'qpos':[], 'qvel':[], 'actual_substep_history':[]}
    other=deepcopy(row);other['observation_before']=[1.,20.,3.]
    result=core.identity_check({'base_identity':[row],'wrapper_identity':[other]})
    assert result['maximum_absolute_difference']==20.
    assert result['numeric_leaf_comparisons']==3 and not result['common_native_state_history_match']


def test_output_is_exclusive_no_old_attempt_overwrite(tmp_path):
    _,backend,_=run(tmp_path)
    old=len(backend.environments)
    with pytest.raises(FileExistsError): run(tmp_path,backend)
    assert len(backend.environments)==old


def test_trace_write_failure_preserves_paid_outcome_and_blocks_new_trial(tmp_path,monkeypatch):
    original=core.gzip.open
    class FailingTrace:
        def __init__(self,*args,**kwargs): self.stream=original(*args,**kwargs)
        def write(self,text): raise OSError('synthetic trace disk failure')
        def flush(self): self.stream.flush()
        def close(self): self.stream.close()
    monkeypatch.setattr(core.gzip,'open',FailingTrace)
    metadata,backend,output=run(tmp_path)
    assert len(backend.environments)==1 and metadata['actual_budget']['known_physics_substeps_lower_bound']==10
    assert metadata['actual_budget']['returned_endpoints']==1
    assert metadata['outcome_counts']=={'exception':1,'blocked':3}
    assert json.loads((output/'base_identity_outcome.json').read_text())['partial_instrumentation']


def test_outcome_write_failure_preserves_stdout_paid_and_blocks_future_trials(tmp_path,monkeypatch,capsys):
    original=core.write_json
    def fail(path,value):
        if Path(path).name=='base_identity_outcome.json': raise OSError('synthetic outcome disk failure')
        original(path,value)
    monkeypatch.setattr(core,'write_json',fail)
    metadata,backend,_=run(tmp_path)
    assert len(backend.environments)==1 and metadata['actual_budget']['known_physics_substeps_lower_bound']==1200
    assert metadata['outcome_counts']=={'exception':1,'blocked':3}
    assert 'paid_outcomes' in capsys.readouterr().out and metadata['artifact_failures']


@pytest.mark.parametrize('name',['parameter_events.json','metadata_final.json','manifest.json'])
def test_final_storage_failure_cannot_claim_complete_success(tmp_path,monkeypatch,capsys,name):
    original=core.write_json
    def fail(path,value):
        if Path(path).name==name: raise OSError('synthetic final disk failure')
        original(path,value)
    monkeypatch.setattr(core,'write_json',fail)
    metadata,_,_=run(tmp_path)
    assert metadata['actual_budget']['known_physics_substeps_lower_bound']==4800
    assert metadata['fatal'] is not None and not metadata['all_four_complete']
    assert 'final_paid_metadata' in capsys.readouterr().out


def test_draft_real_guard_precedes_lazy_import_factory_and_output(tmp_path,monkeypatch):
    # Remains a pure guard test after root promotes the runner with DRAFT=False.
    monkeypatch.setattr(core,'DRAFT',True)
    class NeverBackend:
        synthetic=False
        @property
        def versions(self): raise AssertionError('optional imports must not happen')
        def fresh(self,kind): raise AssertionError('real factory must not happen')
    with pytest.raises(RuntimeError,match='DRAFT'):
        core.run_engineering(tmp_path/'never',NeverBackend())
    assert not (tmp_path/'never').exists()
    backend=core.RealBackend(tmp_path)
    assert not backend._loaded
    with pytest.raises(RuntimeError,match='DRAFT'):
        core.main(['--project-root',str(tmp_path),'--output',str(tmp_path/'main_never')])
    assert not (tmp_path/'main_never').exists()


def test_backend_labels_cannot_bypass_real_freeze(tmp_path,monkeypatch):
    with pytest.raises(ValueError): core.run_engineering(tmp_path/'real_as_fake',core.RealBackend(tmp_path),synthetic=True)
    monkeypatch.setattr(core,'DRAFT',False)
    with pytest.raises(ValueError,match='cannot bypass'): core.run_engineering(tmp_path/'fake_as_real',FakeBackend())
    assert not list(tmp_path.iterdir())


def test_real_binding_failure_precedes_backend_metadata_and_factory(tmp_path,monkeypatch):
    monkeypatch.setattr(core,'DRAFT',False)
    def rejected(*args,**kwargs): raise ValueError('stub rejected frozen binding')
    monkeypatch.setattr(core,'load_frozen_binding',rejected)
    class NeverBackend:
        synthetic=False
        @property
        def versions(self): raise AssertionError('backend loaded before freeze')
        def fresh(self,kind): raise AssertionError('factory before freeze')
    with pytest.raises(ValueError,match='stub rejected'):
        core.run_engineering(tmp_path/'never',NeverBackend())
    assert not (tmp_path/'never').exists()


def binding_fixture(tmp_path,monkeypatch):
    blobs={name:('fixture source '+name).encode() for name in core.REQUIRED_SOURCE_PATHS}
    for name,value in blobs.items():
        path=tmp_path/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(value)
    binding={'schema_version':1,'draft':False,'protocol_path':core.FROZEN_PROTOCOL_PATH,
        'protocol_sha256':hashlib.sha256(blobs[core.FROZEN_PROTOCOL_PATH]).hexdigest(),
        'source_sha256':{name:hashlib.sha256(value).hexdigest() for name,value in blobs.items()},
        'plan':deepcopy(core.PLAN)}
    path=tmp_path/core.FROZEN_BINDING_PATH;path.write_text(json.dumps(binding),encoding='utf-8')
    blobs[core.FROZEN_BINDING_PATH]=path.read_bytes();calls=[];state={'dirty':False}
    def fake_git(args,cwd,text=False):
        calls.append(list(args));assert Path(cwd)==tmp_path and args[0]=='git'
        if args[1:] == ['rev-parse','HEAD']: return 'a'*40+'\n'
        if args[1]=='status': return ' M fixture\n' if state['dirty'] else ''
        if args[1]=='show': return blobs[args[2][5:]]
        raise AssertionError('unexpected subprocess')
    monkeypatch.setattr(core.subprocess,'check_output',fake_git)
    return binding,blobs,state,calls


def test_frozen_binding_fixture_exact_current_head_sources_and_protocol(tmp_path,monkeypatch):
    _,blobs,_,calls=binding_fixture(tmp_path,monkeypatch)
    metadata,sources=core.load_frozen_binding(tmp_path,runner_path=tmp_path/core.FROZEN_RUNNER_PATH)
    assert metadata['source_commit']=='a'*40 and not metadata['source_dirty']
    assert sources==blobs and len(calls)==10  # HEAD/status + binding + seven sources.
    assert not any(args[1] in ('fetch','push','commit') for args in calls)


@pytest.mark.parametrize('fault',['dirty','binding_bytes','source_bytes','source_hash','draft','plan','protocol_path','protocol_hash','self_hash','missing_source','escaping_source','runner_path'])
def test_frozen_binding_fixture_rejects_every_corruption_without_real_git(tmp_path,monkeypatch,fault):
    binding,blobs,state,_=binding_fixture(tmp_path,monkeypatch)
    runner=tmp_path/core.FROZEN_RUNNER_PATH
    if fault=='dirty': state['dirty']=True
    elif fault=='binding_bytes': (tmp_path/core.FROZEN_BINDING_PATH).write_text('{}')
    elif fault=='source_bytes': (tmp_path/core.FROZEN_RUNNER_PATH).write_text('changed bytes')
    elif fault=='source_hash': binding['source_sha256'][core.FROZEN_RUNNER_PATH]='0'*64
    elif fault=='draft': binding['draft']=True
    elif fault=='plan': binding['plan']['active_steps']=21
    elif fault=='protocol_path': binding['protocol_path']=core.FROZEN_RUNNER_PATH
    elif fault=='protocol_hash': binding['protocol_sha256']='0'*64
    elif fault=='self_hash': binding['source_sha256'][core.FROZEN_BINDING_PATH]='0'*64
    elif fault=='missing_source': binding['source_sha256'].pop('src/developmental_physics/environment.py')
    elif fault=='escaping_source': binding['source_sha256']['../outside.py']='0'*64
    elif fault=='runner_path': runner=tmp_path/'different.py'
    if fault not in ('dirty','binding_bytes','source_bytes','runner_path'):
        path=tmp_path/core.FROZEN_BINDING_PATH;path.write_text(json.dumps(binding),encoding='utf-8')
        blobs[core.FROZEN_BINDING_PATH]=path.read_bytes()
    with pytest.raises((ValueError,FileNotFoundError)):
        core.load_frozen_binding(tmp_path,runner_path=runner)


def test_lazy_real_mass_diagnostic_uses_scratch_q_no_live_integrator():
    backend=FakeBackend();env=backend.fresh('armature_double');env.reset()
    original=core.live_snapshot(env);calls=[]
    class Matrix(list):
        def tolist(self): return list(self)
    def data(model): return SimpleNamespace(qpos=[0.]*15,qvel=[0.]*14,ctrl=[0.]*8,act=[],qM=[])
    def forward(model,scratch):
        assert scratch is not env.data;calls.append('forward')
        scratch.qM=[1.+a for a in model.dof_armature]
    def full(model,scratch,matrix):
        calls.append('fullM')
        for i in range(14): matrix[i][i]=scratch.qM[i]
    real=core.RealBackend('.');real._loaded=True
    real.module=SimpleNamespace(MjData=data,mj_forward=forward,mj_fullM=full)
    real.np=SimpleNamespace(empty=lambda shape: Matrix([[0.]*shape[1] for _ in range(shape[0])]))
    result=real.mass_matrix(env)
    assert calls==['forward','fullM'] and result['qpos']==env.data.qpos
    assert result['matrix'][13][13]==1.01 and core.live_snapshot(env)==original
    assert backend.environments[0].kernel_calls==0


@pytest.mark.parametrize('fault',['duplicate_dof','wrong_permission','ctrl_limit','force_limit','wrong_transmission','wrong_dt'])
def test_asset_rejects_malformed_mapping_permissions_or_motor_timing(fault):
    backend=FakeBackend();env=backend.fresh('base_identity')
    if fault=='duplicate_dof': env._joint_dof[1]=env._joint_dof[0]
    elif fault=='wrong_permission': env.action_limits[0]=.4
    elif fault=='ctrl_limit': env.model.actuator_ctrlrange[0]=[-.4,.4]
    elif fault=='force_limit': env.model.actuator_forcelimited[0]=True
    elif fault=='wrong_transmission': env.model.actuator_trnid[0][0]=env._joint_ids[1]
    elif fault=='wrong_dt': env.model.opt.timestep=.004
    with pytest.raises(ValueError): core.asset_audit(env)


@pytest.mark.parametrize('complete,expected_exit',[(True,0),(False,1)])
def test_cli_completion_requires_complete_identity_in_addition_to_no_fatal(monkeypatch,capsys,complete,expected_exit):
    def stub(*args,**kwargs):
        return {'actual_budget':{'known_physics_substeps_lower_bound':4800 if complete else 1000},
            'fatal':None,'all_four_complete':complete,'identity_check':{'validated_identity':complete}}
    monkeypatch.setattr(core,'run_engineering',stub)
    assert core.main(['--output','uncreated_cli_fixture'])==expected_exit
    assert 'actual_budget' in capsys.readouterr().out
