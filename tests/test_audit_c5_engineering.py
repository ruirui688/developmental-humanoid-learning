"""Hand calculations and arithmetic-only archive integration; no physics calls."""
from copy import deepcopy
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
from types import SimpleNamespace

import pytest


def load(path, name):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ROOT=next(p for p in Path(__file__).resolve().parents if (p/'pyproject.toml').exists())
if Path(__file__).with_name('audit_c5_engineering.py').exists():
    audit=load(Path(__file__).with_name('audit_c5_engineering.py'),'c5_independent_audit')
    fixture=load(ROOT/'external/c5_engineering_staging/test_engineering_runner.py','c5_collector_fixture')
else:
    audit=load(ROOT/'scripts/audit_c5_engineering.py','c5_independent_audit')
    fixture=load(ROOT/'tests/test_c5_engineering.py','c5_collector_fixture')


class CanonicalEnv(fixture.FakeEnv):
    def __init__(self,backend,kind):
        super().__init__(backend,kind)
        self._joint_ids=list(range(1,9))
        self._joint_dof=list(range(6,14))
        self._joint_qpos=list(range(7,15))
        self.model.jnt_dofadr=[0]+self._joint_dof
        self.model.jnt_qposadr=[0]+self._joint_qpos
        self.model.jnt_range=[[0.,0.]]+deepcopy(audit.RANGES)
        self.model.actuator_trnid=[[j,-1] for j in self._joint_ids]
        self.model.joint=lambda name:SimpleNamespace(id=self._joint_ids[fixture.core.JOINTS.index(name)])

    def step(self,requested):
        start=len(self.backend.actual)
        result=super().step(requested)
        result.diagnostics.update(accepted_torque=list(requested),
            applied_torque_history=deepcopy(self.backend.actual[start:]))
        return result


class CanonicalBackend(fixture.FakeBackend):
    def __init__(self,faults=None):
        super().__init__(faults)
        self.actual=[]

    def fresh(self,kind):
        env=CanonicalEnv(self,kind)
        self.environments.append(env)
        return env

    def original_step(self,model,data):
        super().original_step(model,data)
        self.actual.append(data._force.copy())


def save_manifest(path):
    value={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in path.iterdir()
           if p.is_file() and p.name!='manifest.json'}
    (path/'manifest.json').write_text(json.dumps(value),encoding='utf-8')


@pytest.fixture(scope='module')
def complete_archive(tmp_path_factory):
    path=tmp_path_factory.mktemp('c5_arithmetic')/'complete'
    fixture.core.run_engineering(path,CanonicalBackend(),synthetic=True)
    result=audit.audit(path,synthetic_fixture=True)
    (path.parent/'first_independent_audit.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    assert result['failed']==0,result['violations']
    return path,result


def test_hand_fixed_commands_and_request_effort():
    commands=[audit.command(i) for i in range(120)]
    assert commands[:100]==[[0.]*8]*100
    assert commands[100:]==[[.25,.25]+[0.]*6]*5+[[0.]*8]*5+[[-.25,-.25]+[0.]*6]*5+[[0.]*8]*5
    assert sum(abs(u[0])*.02 for u in commands)==pytest.approx(.05)
    assert sum(u[0]**2*.02 for u in commands)==pytest.approx(.0125)
    with pytest.raises(ValueError):audit.command(120)


def test_hand_guard_scaling_before_protection():
    angles=[audit.RANGES[0][0]+.03,.02]+[0.]*6
    scaled,blocked,ctrl=audit.expected_guard(angles,[-.25,-.25]+[0.]*6,[.5,.5]+[1.]*6,audit.RANGES)
    assert scaled[:2]==[-.125,-.125] and blocked[:2]==[True,True]
    assert ctrl==[0.]*8
    assert audit.expected_guard(angles,[.25,.25]+[0.]*6,[.5,.5]+[1.]*6,audit.RANGES)[2][:2]==[.125,.125]


def test_boolean_cannot_masquerade_as_numeric():
    checks=audit.Checks()
    checks.compare(True,1,'strict');checks.compare(False,False,'bool');checks.compare(1.+5e-13,1.,'tol')
    assert checks.failed==1 and checks.count==3


def test_complete_synthetic_never_validates_physics_or_adaptation(complete_archive):
    _,result=complete_archive
    assert not result['engineering_pass'] and not result['learning_or_adaptation_validated']
    assert result['archive']['budget']['known_physics_substeps_lower_bound']==4800
    assert result['archive']['identity_rows_complete'] and result['archive']['identity_match']
    assert result['execution']['physical_calls']==result['execution']['model_updates']==0


@pytest.mark.parametrize('mutation',['command','gain','mass','budget'])
def test_independent_recomputation_rejects_mutation(complete_archive,tmp_path,mutation):
    path=tmp_path/mutation;shutil.copytree(complete_archive[0],path)
    if mutation in ('command','gain'):
        with gzip.open(path/'trace.jsonl.gz','rt',encoding='utf-8') as stream:
            rows=[json.loads(line) for line in stream]
        if mutation=='command':rows[100]['requested_torque'][0]=.125
        else:rows[340]['actual_substep_history'][0]['hidden_channel_gains'][0]=1.
        with gzip.open(path/'trace.jsonl.gz','wt',encoding='utf-8') as stream:
            for row in rows:stream.write(json.dumps(row)+'\n')
    elif mutation=='mass':
        events=json.loads((path/'parameter_events.json').read_text())
        events[3]['mass_matrix_after']['matrix'][6][6]+=.01
        (path/'parameter_events.json').write_text(json.dumps(events),encoding='utf-8')
    else:
        metadata=json.loads((path/'metadata_final.json').read_text())
        metadata['actual_budget']['known_physics_substeps_lower_bound']=4799
        (path/'metadata_final.json').write_text(json.dumps(metadata),encoding='utf-8')
    save_manifest(path)
    result=audit.audit(path,synthetic_fixture=True)
    assert result['failed']>0 and not result['engineering_pass']


@pytest.mark.parametrize('fault,expected_calls,expected_substeps',[
    ({'study_stop':True},461,4610),({'reset_paid':True},0,7),
    ({'kernel_exception':1},1,0),({'postforce_exception':1},1,1)])
def test_stop_and_exception_cost_is_retained(tmp_path,fault,expected_calls,expected_substeps):
    path=tmp_path/'failure'
    fixture.core.run_engineering(path,CanonicalBackend({'base_identity':fault}),synthetic=True)
    result=audit.audit(path,synthetic_fixture=True)
    # A base-only injected fault deliberately breaks identity at its last endpoint.
    expected_failures=2 if fault.get('study_stop') else 0
    assert result['failed']==expected_failures,result['violations']
    assert not result['engineering_pass']
    assert result['archive']['budget']['control_calls_attempted']==expected_calls
    assert result['archive']['budget']['known_physics_substeps_lower_bound']==expected_substeps

