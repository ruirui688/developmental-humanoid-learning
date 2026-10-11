"""Self-contained standard-library tests. Synthetic fixtures never formal-pass."""
import ast
import gzip
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile

ROOT=next(p for p in Path(__file__).resolve().parents if (p/'pyproject.toml').is_file())
LOCAL=Path(__file__).with_name('audit_pair_calibration_promotable.py')
AUDIT_PATH=LOCAL if LOCAL.is_file() else ROOT/'scripts/audit_pair_calibration.py'
spec=importlib.util.spec_from_file_location('self_contained_pair_auditor',AUDIT_PATH)
auditor=importlib.util.module_from_spec(spec);spec.loader.exec_module(auditor)

def sha(data):return hashlib.sha256(data).hexdigest()
def write_json(path,obj):path.write_text(json.dumps(obj,allow_nan=False,indent=2)+'\n',encoding='utf-8')
def manifest(path):
    write_json(path/'manifest.json',{p.name:sha(p.read_bytes()) for p in path.iterdir() if p.is_file() and p.name!='manifest.json'})

def synthetic_zero_cost_archive(path):
    """Schema fixture only: one declared setup failure and five blocked trials.

    No collector/environment import, no raw physics records and no claim that
    these records came from execution. Explicit formal-path synthetic ZIP binds
    current source bytes; Git provenance and formal acceptance remain disabled.
    """
    path.mkdir()
    sources={name:(AUDIT_PATH if name==auditor.AUDITOR else ROOT/name).read_bytes()
        for name in set(auditor.SHARED)|{auditor.COLLECTOR,auditor.PROTOCOL,auditor.AUDITOR}}
    with zipfile.ZipFile(path/'source_snapshot.zip','w') as z:
        for name,data in sources.items():z.writestr(name,data)
    plans=[{'trial_id':f'pulse{pulse}_seed{seed}_calibration','seed':seed,
        'reset_seed':{0:3757552657,1:1641411168,2:2001025171}[seed],'pulse_steps':pulse,
        'zero_steps_per_half':10-pulse,'maximum_control_steps':500} for pulse in (2,1) for seed in (0,1,2)]
    failure={'type':'SyntheticFixtureNoExecution','message':'Hand-created schema-only setup failure, zero physical calls'}
    budgets=lambda:{p:{'control_calls_attempted':0,'control_steps':0,'physics_steps':0} for p in ('prefix','calibration')}
    episodes=[{**p,'status':'blocked','completed':False,'study_abort':None,'reason':{'type':'ArchiveAborted','message':'Fatal before planned trial'},
        'control_calls_attempted':0,'control_steps':0,'physics_steps':0,'model_updates':0,'phase_budgets':budgets()} for p in plans]
    episodes[0].update(status='exception',reason=failure,collector_exception=failure,trace_write_failure=None,
        environment_terminated=False,environment_stop_reason=None,returned_steps=0,written_returned_steps=0,
        returned_unwritten_steps=0,unreturned_physics_steps=0,complete_active_endpoints=0,
        risk_telemetry_complete=False,actual_effort_complete=True,known_actual_effort_substeps=0,
        missing_actual_effort_substeps=0,actual_effort_is_lower_bound=False,reference_q=None,direction=None,selection_records=None,
        phase_effort={p:{k:[0.,0.] for k in ('requested_absolute_nm_s','requested_squared_nm2_s','actual_absolute_nm_s','actual_squared_nm2_s')}
            for p in ('prefix','calibration')},environment_fingerprint_before='synthetic',environment_fingerprint_after='synthetic',final_fingerprint_error=None)
    candidates={'candidates':[{'pulse_steps':pulse,'zero_steps_per_half':10-pulse,'eligible':False,
        'trial_ids':[p['trial_id'] for p in plans if p['pulse_steps']==pulse]} for pulse in (2,1)],'selected_pulse_steps':None,'status':'blocked'}
    metadata={'schema_version':1,'suite':'pair_calibration_feasibility','synthetic':True,'backend':'synthetic, no physics',
        'source_commit':'0'*40,'source_dirty':True,'source_status':'SYNTHETIC HAND FIXTURE - not a Git execution',
        'source_sha256':{name:sha(data) for name,data in sources.items()},
        'protocol':{'path':auditor.PROTOCOL,'sha256':sha(sources[auditor.PROTOCOL])},
        'environment_config':{'physics_dt':.002,'control_substeps':10,'torque_limit':.5,'joint_speed_limit':20.,
            'joint_limit_margin':.08,'kinetic_energy_limit':50.,'reset_clearance':.005,'ground_contact_profile':'baseline'},
        'gpu':None,'pose':'supine','joint_indices':[0,1],'native_joint_count':8,'development_seeds':[0,1,2],'pulses':[2,1],
        'prefix_steps':100,'active_steps':400,'amplitudes_nm':[.125,.25,.375,.5,.25],
        'maximum_control_steps':3000,'maximum_physics_steps':30000,'model_updates':0,'teacher_calls':0,
        'parameter_updates':0,'policy_parameter_updates':0,'gain_updates':0,
        'planned_requested_effort_per_axis':{'2':{'absolute_nm_s':.36,'squared_nm2_s':.1275},'1':{'absolute_nm_s':.18,'squared_nm2_s':.06375}},
        'planned_episodes':plans,'control_calls_attempted':0,'control_steps':0,'physics_steps':0,
        'statuses':{'exception':1,'blocked':5},'complete':False,'archive_status':'failed','archive_exception':failure,'candidate_selection':candidates}
    write_json(path/'episodes.json',episodes);write_json(path/'metadata.json',metadata)
    (path/'trace.jsonl.gz').write_bytes(gzip.compress(b''));manifest(path)

class AuditTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup);self.base=Path(temporary.name)
    def fixture(self):
        path=self.base/'archive';synthetic_zero_cost_archive(path);return path
    def audit_fixture(self,path,**kwargs):
        return auditor.audit(path,git_root=None,synthetic_fixture=True,synthetic_source_layout='formal',**kwargs)
    def test_no_external_imports(self):
        names=[]
        for node in ast.walk(ast.parse(AUDIT_PATH.read_text())):
            if isinstance(node,ast.Import):names.extend(x.name.split('.')[0] for x in node.names)
            elif isinstance(node,ast.ImportFrom):names.append((node.module or '').split('.')[0])
        self.assertFalse(set(names)&{'numpy','mujoco','developmental_physics','calibration_feasibility'})
    def test_command_slots_shapes_effort_by_hand(self):
        for pulse,absolute,squared in ((2,.36,.1275),(1,.18,.06375)):
            u=[auditor.command(i,pulse,[-1,1]) for i in range(400)]
            self.assertEqual([x[0] for x in u[:20]],[-.125]*pulse+[0.]*(10-pulse)+[.125]*pulse+[0.]*(10-pulse))
            self.assertEqual(u[100],[0.,.125]+[0.]*6);self.assertEqual(u[200],[-.125,.125]+[0.]*6);self.assertEqual(u[300],[-.125,-.125]+[0.]*6)
            for axis in (0,1):
                self.assertAlmostEqual(sum(abs(x[axis])*.02 for x in u),absolute)
                self.assertAlmostEqual(sum(x[axis]**2*.02 for x in u),squared)
        with self.assertRaises(ValueError):auditor.command(0,5,[1,1])
    def test_exact_guard_study_boundaries(self):
        q=[0.]*8;u=[.5]*8;q[0]=-.97;q[1]=.97;u[0]=-.5
        self.assertEqual(auditor.guard(q,u,[[-1.,1.]]*8),[0.,0.]+[.5]*6)
        self.assertIsNone(auditor.study([.12,0.],[1.,0.],[0.,0.],99))
        self.assertEqual(auditor.study([.12,0.],[1.,0.],[0.,0.],100)['triggers'],[
            {'joint_index':0,'signal':'absolute_q_minus_qref_rad'},{'joint_index':0,'signal':'absolute_velocity_rad_s'}])
    def test_public_xml_nonidentity_mapping(self):
        root=ET.fromstring((ROOT/auditor.ASSET).read_bytes());torso=root.find('worldbody/body');bodies=torso.findall('body')
        for b in bodies:torso.remove(b)
        for b in (bodies[1],bodies[0],bodies[2],bodies[3]):torso.append(b)
        checks=auditor.Checks();mapping,nq,nv=auditor.parse_asset(ET.tostring(root),checks)
        self.assertEqual(checks.failed,0);self.assertEqual((nq,nv),(15,14))
        self.assertEqual([m['qpos'] for m in mapping],[9,10,7,8,11,12,13,14]);self.assertAlmostEqual(mapping[4]['range'][1],math.pi/2)
    def test_paid_partial_unknown_actual_by_hand(self):
        effort=auditor.new_effort();effort[auditor.EFFORT[0]]=[.00075,0.];effort[auditor.EFFORT[1]]=[.00009375,0.]
        checks=auditor.Checks();result=auditor.reconcile_effort(effort,auditor.new_effort(),3,0,0,[[-.125]+[0.]*7],checks,'hand')
        self.assertEqual(checks.failed,0);self.assertEqual(result['unreconstructed_physics_substeps'],3)
        self.assertTrue(result['raw_actual_is_lower_bound']);self.assertFalse(result['raw_actual_reconstruction_complete'])
    def test_priority_requires_unique_three_complete_raw_seeds(self):
        rows=[{'pulse_steps':p,'seed':s,'trial_id':f'p{p}s{s}','independent_complete':True} for p in (2,1) for s in (0,1,2)]
        self.assertEqual(auditor.selection(rows)['selected_pulse_steps'],2);rows[1]['independent_complete']=False
        self.assertEqual(auditor.selection(rows)['selected_pulse_steps'],1);rows[4]['seed']=0
        self.assertIsNone(auditor.selection(rows)['selected_pulse_steps'])
    def test_schema_fixture_never_formally_accepted(self):
        result=self.audit_fixture(self.fixture());self.assertEqual(result['failed'],0,result['violations'])
        self.assertFalse(result['validated_eligible']);self.assertFalse(result['formal_execution_accepted'])
        self.assertEqual(result['archive']['budget'],{'control_calls_attempted':0,'control_steps':0,'physics_steps':0})
        self.assertEqual(result['execution']['physical_calls'],0);self.assertEqual(result['execution']['third_party_imports'],[])
    def test_source_scope_is_explicit_and_synthetic_only(self):
        path=self.fixture()
        implicit=auditor.audit(path,git_root=None,synthetic_fixture=True)
        self.assertGreater(implicit['failed'],0)
        formal_override=auditor.audit(path,git_root=None,synthetic_fixture=False,synthetic_source_layout='formal',expected_source_commit='0'*40)
        self.assertGreater(formal_override['failed'],0);self.assertFalse(formal_override['formal_execution_accepted'])
    def test_manifest_and_blocked_cost_mutations_rejected(self):
        path=self.fixture();episodes=json.loads((path/'episodes.json').read_text());episodes[1]['physics_steps']=2
        write_json(path/'episodes.json',episodes);manifest(path)
        cost=self.audit_fixture(path);self.assertGreater(cost['failed'],0);self.assertFalse(cost['formal_execution_accepted'])
        manifests=json.loads((path/'manifest.json').read_text());manifests['episodes.json']='0'*64
        write_json(path/'manifest.json',manifests)
        result=self.audit_fixture(path);self.assertGreater(result['failed'],cost['failed'])

if __name__=='__main__':unittest.main()
