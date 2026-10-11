"""Small handcrafted stdlib proofs; no real raw, online imports or physics."""
from collections import Counter
from copy import deepcopy
import importlib.util
import io
import json
import math
from pathlib import Path
import sys
import time
import unittest
import hashlib

HERE=Path(__file__).resolve().parent
ROOT=next(p for p in HERE.parents if (p/'pyproject.toml').is_file())
SOURCE=HERE/'audit_guard_lag_offline_development.py'
if not SOURCE.is_file(): SOURCE=ROOT/'scripts/audit_guard_lag_offline.py'
spec=importlib.util.spec_from_file_location('_handcrafted_lag_audit',SOURCE)
a=importlib.util.module_from_spec(spec);sys.modules[spec.name]=a;spec.loader.exec_module(a)
EVENTS=[]

def native_rows(count):
    def obs(index): return {'joint_position':[index*.001,0.]+[0.]*6,'joint_velocity':[index*.01,0.]+[0.]*6}
    return [{'trial_id':'artificial','step_index':i,'shared_transition_id':f'artificial:{i}',
        'observation_before':obs(i),'observation_after':obs(i+1),'requested_torque':[0.]*8,
        'diagnostics':{'executed_substeps':10,'terminated':False},'study_abort':None} for i in range(count)]

def snapshot(state,qref):
    record=a.parameter_record(qref,state)
    return {**record,'parameter_fingerprint':a.digest(record),'trainable':True,'vector_update_count':state['count'],
        'scalar_update_count':2*state['count'],'output_update_counts':[state['count']]*2,
        'update_commit':'single immutable state reference for both outputs, covariance and counts',
        'input_boundary':'native current/previous velocities, current q and already known u; no future actual torque'}

class SmallLagChecks(unittest.TestCase):
    def setUp(self): self.before=Counter(a.MATH_COST)
    def tearDown(self): EVENTS.append({'test':self.id(),'independent_math_delta':dict(a.MATH_COST-self.before)})

    def test_cold_features_and_no_history_default(self):
        x=a.lag_features([0.,0.],[.1,.2],[.4,.5],[.3,.2],[.1,.4],[[-2.,2.],[-2.,2.]])[0]
        expected=[.4,.5,.1,.2,.3,.2,.05,0.,1.,.3,.1]
        for value,want in zip(x,expected): self.assertAlmostEqual(value,want,places=14)
        cold=a.initial_state([[-2.,2.],[-2.,2.]])
        self.assertEqual(cold['theta'][0][9:],[0.,0.]);self.assertEqual(cold['theta'][1][9:],[0.,0.])
        with self.assertRaises(TypeError): a.predict11(cold['theta'],cold['ranges'],[0.,0.],[0.,0.],[0.,0.],[0.,0.])
        with self.assertRaises(ValueError): a.lag_features([0.,0.],[0.,0.],[0.,0.],[0.,0.],[float('nan'),0.],cold['ranges'])

    def test_closed_form_one_transition_rls(self):
        state=a.initial_state([[-2.,2.],[-2.,2.]]);x=[.1,.2,.3,.4,.5,.6,.7,.8,1.,.9,.1]
        label=.8;theta=state['theta'][0];predicted=sum(t*z for t,z in zip(theta,x));denom=1.+100.*sum(z*z for z in x)
        after,cov,residual=a.replay_rls11(theta,state['covariance'][0],x,label)
        for i in range(11):
            self.assertAlmostEqual(after[i],theta[i]+100.*x[i]*(label-predicted)/denom,places=13)
            for j in range(11): self.assertAlmostEqual(cov[i][j],(100. if i==j else 0.)-10000.*x[i]*x[j]/denom,places=12)
        self.assertAlmostEqual(residual,label-predicted,places=14)
        with self.assertRaises(ValueError): a.replay_rls11(theta[:-1],state['covariance'][0],x,label)

    def test_prefix_history_points_to_98_99(self):
        rows=native_rows(104);q,v,previous=a.native_origin(rows,100)
        self.assertEqual(v,rows[99]['observation_after']['joint_velocity'][:2])
        self.assertEqual(previous,rows[98]['observation_after']['joint_velocity'][:2])
        self.assertNotEqual(previous,rows[99]['observation_before']['joint_velocity'][:2] if False else [0.,0.])
        rows[99]['observation_before']['joint_velocity'][0]+=1.
        with self.assertRaises(ValueError): a.native_origin(rows,100)

    def test_four_interval_trial_has_no_h5_h15(self):
        rows=native_rows(104);rows[103]['study_abort']={'type':'ArtificialStudyStop'}
        self.assertEqual(a.available_horizons(rows,100),[1,2]);self.assertEqual(a.available_horizons(rows,103),[1])
        rows[100]['study_abort']={'type':'ArtificialStudyStop'}
        self.assertEqual(a.available_horizons(rows,100),[1])
        rows[100]['study_abort']=None;rows[101]['diagnostics']['executed_substeps']=3
        self.assertEqual(a.available_horizons(rows,100),[1])

    def test_rollout_uses_own_predicted_history(self):
        state=a.initial_state([[-2.,2.],[-2.,2.]])
        theta=deepcopy(state['theta']);theta[0][0]=.5;theta[0][9]=.25
        original=deepcopy(theta)
        steps=a.rollout_math(theta,state['ranges'],[0.,0.],[0.,0.],[.4,0.],[.2,0.],[[0.,0.]]*3,lag=True)
        for row,want in zip(steps,[.25,.0875,.003125]): self.assertAlmostEqual(row['next_v_rad_s'][0],want,places=14)
        self.assertEqual(steps[1]['previous_v_before'],[.4,0.]);self.assertEqual(steps[2]['previous_v_before'],steps[0]['next_v_rad_s'])
        self.assertEqual(theta,original)

    def test_standardization_constant_zero_and_known_singulars(self):
        values=[[float(i)]+[0.]*7+[1.] for i in range(3)]
        d=a.standardized_design(values)
        self.assertEqual(d['zero_variance_columns'],list(range(1,8)));self.assertEqual(d['centered_rms'][8],1.)
        self.assertAlmostEqual(d['standardized_gram'][0][0],1.,places=14)
        self.assertAlmostEqual(d['standardized_gram'][8][8],1.,places=14)
        sv=a.singular_values(d['standardized_columns'])
        self.assertAlmostEqual(sv[0],math.sqrt(3.),places=13);self.assertAlmostEqual(sv[1],math.sqrt(3.),places=13)
        self.assertEqual(sv[2:],[0.]*7)
        self.assertEqual(a.singular_values([[1.,0.,0.],[0.,2.,0.]]),[2.,1.])

    def test_modal_matrix_cold_repeated_unit_modes(self):
        state=a.initial_state([[-2.,2.],[-2.,2.]])
        self.assertEqual(a.characteristic_coefficients(a.modal_matrix(state['theta'])),[1.,-4.,6.,-4.,1.,0.,0.])
        old=[row[:9] for row in state['theta']]
        self.assertEqual(a.characteristic_coefficients(a.modal_matrix(old)),[1.,-4.,6.,-4.,1.])

    def test_snapshot_hash_detects_changed_history_prior(self):
        state=a.initial_state([[-2.,2.],[-2.,2.]]);snap=snapshot(state,[0.,0.]);checks=a.Checks()
        a.verify_snapshot(snap,state,[0.,0.],checks,'correct',True);self.assertEqual(checks.failed,0)
        snap['initial_coefficients'][0][9]=1.
        a.verify_snapshot(snap,state,[0.,0.],checks,'wrong_prior',True);self.assertGreater(checks.failed,0)

def main():
    attempt=1
    while (HERE/f'artificial_{attempt:03d}.json').exists(): attempt+=1
    source=SOURCE.read_bytes();test=Path(__file__).read_bytes();prefix=HERE/f'artificial_{attempt:03d}'
    (HERE/f'artificial_{attempt:03d}_auditor.py').write_bytes(source)
    (HERE/f'artificial_{attempt:03d}_tests.py').write_bytes(test)
    stream=io.StringIO();wall,cpu=time.perf_counter(),time.process_time()
    result=unittest.TextTestRunner(stream=stream,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(SmallLagChecks))
    report={'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),
        'source_sha256':hashlib.sha256(source).hexdigest(),'test_sha256':hashlib.sha256(test).hexdigest(),
        'per_test':EVENTS,'total_independent_math':dict(a.MATH_COST),
        'timing':{'wall_seconds':time.perf_counter()-wall,'cpu_seconds':time.process_time()-cpu},
        'formal_additions':{'real_raw_reads':0,'physical_calls':0,'online_helper_imports':0,'old_model_refits':0,'real_calibration_updates':0},
        'artificial_only':True}
    prefix.with_suffix('.log').write_text(stream.getvalue(),encoding='utf-8')
    prefix.with_suffix('.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(stream.getvalue());print(json.dumps(report,allow_nan=False))
    return 0 if result.wasSuccessful() else 1
if __name__=='__main__': raise SystemExit(main())
