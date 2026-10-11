"""Pure fake-backend contract tests. No MjModel/MjData construction or mj_step."""
import importlib.util
import json
import io
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
import tempfile
from unittest.mock import patch

if importlib.util.find_spec("numpy") is None or importlib.util.find_spec("mujoco") is None:
    raise unittest.SkipTest("Optional NumPy/MuJoCo dependency required for fake collector contract tests")
import numpy as np

DRAFT_PATH=Path(__file__).with_name('calibration_feasibility.py')
EARLY_ROOT=next(p for p in Path(__file__).resolve().parents if (p/'pyproject.toml').is_file())
if (EARLY_ROOT/'src/developmental_physics/pair_calibration_development.py').is_file():
    from developmental_physics import pair_calibration_development as draft
elif DRAFT_PATH.is_file():
    spec=importlib.util.spec_from_file_location('calibration_feasibility_under_test',DRAFT_PATH)
    draft=importlib.util.module_from_spec(spec);spec.loader.exec_module(draft)
else:
    from developmental_physics import pair_calibration_development as draft
ROOT=next(p for p in Path(__file__).resolve().parents if (p/'pyproject.toml').is_file())
OUTPUT_ROOT=os.environ.get('PAIR_CALIBRATION_SYNTHETIC_OUTPUT_ROOT')
PROTOCOL=ROOT/draft.PROTOCOL_PATH


class FakeEnv:
    instances=[]
    mode='normal'
    def __init__(self,config):
        self.config=config;self.instance_id=len(type(self).instances);type(self).instances.append(self)
        self.joint_names=('left_shoulder','left_elbow','right_shoulder','right_elbow','left_hip','left_knee','right_hip','right_knee')
        self.ranges=np.array([(-1.7453292519943295,1.7453292519943295),(0.,2.356194490192345),
            (-1.7453292519943295,1.7453292519943295),(0.,2.356194490192345),
            (-1.5707963267948966,1.5707963267948966),(0.,2.356194490192345),
            (-1.5707963267948966,1.5707963267948966),(0.,2.356194490192345)])
        self.model=SimpleNamespace(joint=lambda name:SimpleNamespace(range=self.ranges[self.joint_names.index(name)]))
        self.data=SimpleNamespace(qpos=np.zeros(15),qvel=np.zeros(14),time=0.)
        self.last_command=np.zeros(8);self.last_actual=np.zeros(8);self.q=np.zeros(8);self.v=np.zeros(8)
        self.step_id=self.physics_steps=self.calls=0;self.terminated=False;self.reason=None
    def reset(self,seed=0,pose='supine'):
        self.q[1]=-.001;self.q[0]=.1;self.data.qpos[7:]=self.q
        self.reset_seed=seed;self.reset_pose=pose
        return self.observation()
    def observation(self):
        return {'joint_position':self.q.copy(),'joint_velocity':self.v.copy(),
            'actuator_torque':self.last_actual.copy(),'previous_command':self.last_command.copy(),
            'imu_gyro':np.zeros(3),'imu_acceleration':np.zeros(3)}
    def parameter_fingerprint(self):
        if self.mode=='interrupt_fingerprint' and self.calls>100:raise OSError('after fingerprint unavailable')
        return 'changed' if self.mode=='plant_change' and self.calls>100 else 'fake-fixed-plant'
    def diagnostics(self):
        return {'synthetic':True,'step_id':self.step_id,'physics_steps':self.physics_steps,'time':self.data.time,
            'contact_count':0,'ground_contact_count':0,'ground_normal_force':0.,'kinetic_energy':0.,
            'minimum_contact_distance':0.,'root_position':self.data.qpos[:3].tolist(),
            'root_quaternion':self.data.qpos[3:7].tolist(),'center_of_mass':[0.,0.,0.]}
    def step(self,u):
        self.calls+=1;self.last_command[:]=u;active=self.calls-101
        screened=((self.q<=self.ranges[:,0]+.03)&(u<0))|((self.q>=self.ranges[:,1]-.03)&(u>0))
        actual=np.where(screened,0.,u);self.last_actual[:]=actual
        n=10
        if self.mode in ('interrupt','interrupt_fingerprint') and active==0:
            self.physics_steps+=3;self.data.time+=.006;raise KeyboardInterrupt('paid fake interrupt')
        if self.mode=='partial' and self.instance_id<3 and active==0:n=3
        self.physics_steps+=n;self.step_id+=1;self.data.time+=n*.002
        if self.mode=='stop_first' and self.instance_id<3 and active==0:self.v[1]=1.
        if self.mode=='stop_all' and active==0:self.v[1]=1.
        if self.mode=='last_stop' and self.instance_id<3 and active==399:self.v[1]=1.
        if self.mode=='environment_stop' and active==0:self.terminated=True;self.reason='fake_environment_stop'
        if self.mode=='shoulder_stop' and active==0:self.v[0]=1.
        self.data.qpos[7:]=self.q;self.data.qvel[6:]=self.v
        history=[list(actual)]*n
        if self.mode=='bad_history' and active==0:history=[list(u[:7])]*n
        d={**self.diagnostics(),'executed_substeps':n,'applied_torque_history':history,
            'requested_torque':list(u),'accepted_torque':list(u),'applied_torque':list(actual),
            'guarded_substeps':n if np.any(screened) else 0,'terminated':self.terminated,'reason':self.reason,
            'substep_ground_normal_forces':[0.]*n,'substep_kinetic_energies':[0.]*n,
            'substep_minimum_contact_distances':[0.]*n,'synthetic':True,'peak_substep_ground_normal_force':0.,
            'ground_normal_impulse_ns':0.,'peak_substep_kinetic_energy':0.,'minimum_substep_contact_distance':0.}
        if self.mode=='bad_telemetry' and active==0:d['substep_ground_normal_forces']=[]
        return SimpleNamespace(observation=self.observation(),diagnostics=d,terminated=self.terminated,reason=self.reason)


class DraftTests(unittest.TestCase):
    def setUp(self):
        FakeEnv.instances=[];FakeEnv.mode='normal'
        if OUTPUT_ROOT is None:
            temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup);base=Path(temporary.name)
        else:base=Path(OUTPUT_ROOT)
        self.out=base/self.id().split('.')[-1]
    def run_draft(self,mode='normal'):
        FakeEnv.mode=mode
        with patch.object(draft,'GroundBodyEnv',FakeEnv),patch.object(draft,'FORMAL_EXECUTION_FROZEN',False):
            return draft.run_validation(self.out,protocol_path=PROTOCOL,synthetic=True)
    def episodes(self):return json.loads((self.out/'episodes.json').read_text())
    def metadata(self):return json.loads((self.out/'metadata.json').read_text())
    def test_full_six_trials_no_learning_choose_pulse2(self):
        m=self.run_draft();self.assertEqual((m['control_calls_attempted'],m['physics_steps'],m['model_updates']),(3000,30000,0))
        self.assertEqual(m['candidate_selection']['selected_pulse_steps'],2)
        self.assertEqual(m['statuses'],{'completed':6})
        for e in self.episodes():
            self.assertEqual(e['complete_active_endpoints'],400)
            self.assertLess(e['reference_q'][1],0.)
            self.assertEqual(e['direction'],[-1,1])
            expected=.36 if e['pulse_steps']==2 else .18
            self.assertAlmostEqual(e['phase_effort']['calibration']['requested_absolute_nm_s'][0],expected)
            self.assertAlmostEqual(e['phase_effort']['calibration']['requested_absolute_nm_s'][1],expected)
    def test_stop_first_candidate_then_predeclared_pulse1(self):
        m=self.run_draft('stop_first')
        self.assertEqual(m['candidate_selection']['selected_pulse_steps'],1)
        self.assertEqual(m['control_calls_attempted'],1803)
        self.assertEqual(m['statuses'],{'terminated':3,'completed':3})
        self.assertEqual(len(FakeEnv.instances),6)
    def test_both_candidates_stopped_none_selected(self):
        m=self.run_draft('stop_all')
        self.assertIsNone(m['candidate_selection']['selected_pulse_steps'])
        self.assertEqual(m['candidate_selection']['status'],'blocked')
        self.assertEqual((m['control_calls_attempted'],m['physics_steps']),(606,6060))
    def test_final_planned_step_stop_is_not_complete(self):
        m=self.run_draft('last_stop')
        self.assertEqual(m['control_calls_attempted'],3000)
        self.assertFalse(m['candidate_selection']['candidates'][0]['eligible'])
        self.assertEqual(m['candidate_selection']['selected_pulse_steps'],1)
        self.assertEqual(self.episodes()[0]['complete_active_endpoints'],400)
        self.assertFalse(self.episodes()[0]['completed'])
    def test_partial_without_stop_not_eligible_no_extension(self):
        m=self.run_draft('partial')
        self.assertEqual(m['control_calls_attempted'],1803)
        self.assertEqual(self.episodes()[0]['status'],'incomplete')
        self.assertEqual(self.episodes()[0]['physics_steps'],1003)
        self.assertEqual(self.episodes()[0]['complete_active_endpoints'],0)
        self.assertEqual(m['candidate_selection']['selected_pulse_steps'],1)
    def test_interrupt_paid_partial_and_remaining_blocked(self):
        with self.assertRaises(KeyboardInterrupt):self.run_draft('interrupt')
        e=self.episodes()[0]
        self.assertEqual((e['control_calls_attempted'],e['control_steps'],e['physics_steps']),(101,100,1003))
        self.assertEqual(e['missing_actual_effort_substeps'],3)
        self.assertEqual(e['unreturned_physics_steps'],3)
        self.assertFalse(e['actual_effort_complete'])
        self.assertTrue(all(x['status']=='blocked' for x in self.episodes()[1:]))
    def test_primary_interrupt_survives_after_fingerprint_failure(self):
        with self.assertRaises(KeyboardInterrupt):self.run_draft('interrupt_fingerprint')
        e=self.episodes()[0]
        self.assertEqual(e['collector_exception']['type'],'KeyboardInterrupt')
        self.assertEqual(e['final_fingerprint_error']['type'],'OSError')
        self.assertEqual(e['physics_steps'],1003)
    def test_invalid_native_history_keeps_request_cost_actual_unknown(self):
        with self.assertRaisesRegex(RuntimeError,'Invalid native actual history'):self.run_draft('bad_history')
        e=self.episodes()[0]
        self.assertEqual(e['physics_steps'],1010)
        self.assertEqual(e['missing_actual_effort_substeps'],10)
        self.assertAlmostEqual(e['phase_effort']['calibration']['requested_absolute_nm_s'][0],.0025)
        self.assertEqual(e['phase_effort']['calibration']['actual_absolute_nm_s'],[0.,0.])
    def test_missing_raw_telemetry_fatal_no_adoption(self):
        with self.assertRaisesRegex(RuntimeError,'Missing finite raw telemetry'):self.run_draft('bad_telemetry')
        self.assertFalse(self.episodes()[0]['risk_telemetry_complete'])
        self.assertEqual(self.episodes()[0]['physics_steps'],1010)
    def test_environment_stop_ordinary_continues_no_candidate(self):
        m=self.run_draft('environment_stop')
        self.assertEqual(m['statuses'],{'terminated':6})
        self.assertIsNone(m['candidate_selection']['selected_pulse_steps'])
        self.assertEqual(self.episodes()[0]['reason'],'fake_environment_stop')
    def test_shoulder_stop_triggers_native_j0(self):
        self.run_draft('shoulder_stop')
        self.assertEqual(self.episodes()[0]['study_abort']['triggers'],[{'joint_index':0,'signal':'absolute_velocity_rad_s'}])
    def test_trace_failure_after_paid_endpoint_is_fatal(self):
        original=draft.gzip.open
        class BrokenTrace:
            def __init__(self,stream):self.stream=stream;self.failed=False
            def __enter__(self):self.stream.__enter__();return self
            def __exit__(self,*args):return self.stream.__exit__(*args)
            def write(self,value):
                if not self.failed and '"step_index": 100' in value:self.failed=True;raise OSError('synthetic trace write failure')
                return self.stream.write(value)
        with patch.object(draft.gzip,'open',lambda *a,**k:BrokenTrace(original(*a,**k))):
            with self.assertRaises(OSError):self.run_draft()
        e=self.episodes()[0]
        self.assertEqual((e['control_calls_attempted'],e['physics_steps']),(101,1010))
        self.assertEqual(e['returned_unwritten_steps'],1)
        self.assertEqual(e['written_returned_steps'],100)
        self.assertEqual(self.metadata()['statuses'],{'exception':1,'blocked':5})
    def test_checkpoint_io_failure_keeps_full_paid_first_trial(self):
        original=draft._write_json;failed=[False]
        def writer(path,obj):
            if path.name=='episodes.json' and obj[0]['control_calls_attempted'] and not failed[0]:
                failed[0]=True;raise OSError('synthetic checkpoint I/O failure')
            return original(path,obj)
        with patch.object(draft,'_write_json',writer):
            with self.assertRaises(OSError):self.run_draft()
        self.assertEqual(self.metadata()['control_calls_attempted'],500)
        self.assertEqual(self.metadata()['physics_steps'],5000)
        self.assertEqual(self.episodes()[0]['status'],'exception')
        self.assertTrue(all(e['status']=='blocked' for e in self.episodes()[1:]))
    def test_fixed_plant_change_fatal_after_paid_trial(self):
        with self.assertRaisesRegex(RuntimeError,'Fixed plant fingerprint changed'):self.run_draft('plant_change')
        self.assertEqual(self.episodes()[0]['physics_steps'],5000)
        self.assertFalse(self.episodes()[0]['completed'])
    def test_existing_output_refuses_before_backend_construction(self):
        self.out.mkdir()
        with self.assertRaises(FileExistsError):self.run_draft()
        self.assertEqual(FakeEnv.instances,[])
    def test_real_entry_disabled(self):
        with patch.object(draft,'FORMAL_EXECUTION_FROZEN',False),self.assertRaisesRegex(RuntimeError,'Real physics disabled'):
            draft.run_validation(self.out,protocol_path=PROTOCOL)
        self.assertFalse(self.out.exists())
    def test_pulse_slots_and_unrun_5_refused(self):
        for pulse in (2,1):
            commands=[draft.pulse_request(i,pulse,[-1,1]) for i in range(20)]
            self.assertEqual([u[0] for u in commands],[-.125]*pulse+[0.]*(10-pulse)+[.125]*pulse+[0.]*(10-pulse))
            self.assertEqual(draft.pulse_request(300,pulse,[-1,1]),(-.125,-.125))
        with self.assertRaises(ValueError):draft.pulse_request(0,5,[-1,1])
    def test_formal_cli_forwards_paths_without_physical_execution(self):
        if not hasattr(draft,'main'):self.skipTest('Draft has no CLI; promoted collector does')
        record={'source_commit':'0'*40,'archive_status':'complete','statuses':{'completed':6},
            'control_calls_attempted':3000,'control_steps':3000,'physics_steps':30000,'model_updates':0,
            'candidate_selection':{'selected_pulse_steps':None},'complete':True}
        with patch.object(draft,'run_validation',return_value=record) as run,patch('sys.stdout',io.StringIO()):
            result=draft.main(['--output',str(self.out),'--protocol',str(PROTOCOL)])
        self.assertEqual(result,1)
        run.assert_called_once_with(self.out,protocol_path=PROTOCOL)
        self.assertEqual(FakeEnv.instances,[])
    def test_pulse2_truncated_low_effort_cannot_win(self):
        m=self.run_draft('stop_first')
        e=self.episodes()
        self.assertLess(e[0]['phase_effort']['calibration']['actual_absolute_nm_s'][0],e[3]['phase_effort']['calibration']['actual_absolute_nm_s'][0])
        self.assertEqual(m['candidate_selection']['selected_pulse_steps'],1)


if __name__=='__main__':unittest.main()
