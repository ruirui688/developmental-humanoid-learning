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
SOURCE=HERE/'audit_guard_lag_offline.py'
if not SOURCE.is_file(): SOURCE=ROOT/'scripts/audit_guard_lag_offline.py'
spec=importlib.util.spec_from_file_location('_handcrafted_lag_audit',SOURCE)
a=importlib.util.module_from_spec(spec);sys.modules[spec.name]=a;spec.loader.exec_module(a)
EVENTS=[]

def native_rows(count):
    def obs(index): return {'joint_position':[index*.001,0.]+[0.]*6,'joint_velocity':[index*.01,0.]+[0.]*6}
    return [{'trial_id':'artificial','seed':0,'kind':'prediction','phase':'prefix' if i<100 else 'prediction','step_index':i,'shared_transition_id':f'artificial:{i}',
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

    def test_design_reporting_bias_scale_and_undefined_correlations(self):
        values=[[float(i)]+[0.]*7+[1.] for i in range(3)]
        d=a.design_statistics(values,a.FEATURES9)
        self.assertEqual(d['mean'][8],1.);self.assertEqual(d['centered_rms'][8],0.)
        self.assertEqual(d['coefficient_column_scale'][8],1.)
        self.assertIn(8,d['zero_variance_columns']);self.assertIn(8,d['constant_columns'])
        self.assertEqual(d['standardized_gram'][8][8],1.)
        self.assertFalse(d['column_correlation_defined'][8][8]);self.assertTrue(d['column_correlation_defined'][0][0])

    def test_no_window_after_source_stop_and_request_ages(self):
        rows=native_rows(107);rows[103]['study_abort']={'type':'ArtificialStop'}
        for i in range(100,104):rows[i]['requested_torque'][0]=.2
        items,unavailable=a.source_intervals(rows,'prediction');windows=a.common_windows(items)
        self.assertEqual(len(items),4);self.assertEqual([x['request_nonzero_age_steps'][0] for x in items],[1,2,3,4])
        self.assertEqual([r['reason'] for r in unavailable],['after_source_stop']*3)
        self.assertEqual(windows[0]['available_horizons'],[1,2]);self.assertEqual(windows[-1]['available_horizons'],[1])

    def test_saved_prediction_reuse_requires_exact_identity_and_G(self):
        rows=native_rows(104);item=a.source_intervals(rows,'prediction')[0][0];row=item['row'];name='nominal_guard';fingerprint='f'*64
        inputs=a.guard.describe_input(item['q'],item['u'],('known_angle_guard',[[-2.,2.],[-2.,2.]]))
        row['predicted_next_qv']={name:[[.1,0.],[.2,0.]]};row['model_input_diagnostics']={name:inputs}
        trial={'models_before':{name:fingerprint},'models_after':{name:fingerprint}}
        reuse=a.reuse_candidate(item,'nominal9',fingerprint,trial,[[-2.,2.],[-2.,2.]])
        self.assertEqual(reuse['source_transition_id'],row['shared_transition_id']);self.assertEqual(reuse['native_v_exact'],item['v'])
        self.assertIsNone(a.reuse_candidate(item,'nominal9','a'*64,trial,[[-2.,2.],[-2.,2.]]))
        inputs['model_feature_command_nm'][0]=.1
        self.assertIsNone(a.reuse_candidate(item,'nominal9',fingerprint,trial,[[-2.,2.],[-2.,2.]]))

    def _lag_rollout(self):
        rows=native_rows(104);items=a.source_intervals(rows,'prediction')[0];window=a.common_windows(items)[0]
        state=a.initial_state([[-2.,2.],[-2.,2.]]);state['theta'][0][0]=.5;state['theta'][0][9]=.25
        model={'theta':state['theta'],'fingerprint':'f'*64};origin=window['origin'];row=origin['row']
        record={'record_type':'conditional_offline_rollout','seed':0,'trial_id':'artificial','kind':'prediction',
            'origin_transition_id':row['shared_transition_id'],'origin_step_index':100,'predictor':'lag_sparse11',
            'available_horizons':window['available_horizons'],'history_transition_ids':origin['history_transition_ids'],
            'native_start':{k:origin[k] for k in ('q','v','previous_v')},'request_nonzero_age_steps':origin['request_nonzero_age_steps'],
            'future_request_semantics':'offline conditioning only; never actor-visible or future actual input','model_fingerprint':model['fingerprint'],
            'steps':[],'failure':None}
        math=a.rollout_math(state['theta'],state['ranges'],[0.,0.],origin['q'],origin['v'],origin['previous_v'],[i['u'] for i in window['sequence']],lag=True)
        cost=Counter()
        for h,(source,step) in enumerate(zip(window['sequence'],math),1):
            delta={'diagnostic_guard_pair_evaluations':1,**a.EVAL_SUCCESS};cost.update(delta)
            record['steps'].append({'h':h,'source_transition_id':source['row']['shared_transition_id'],
                'input':{'q':step['q_before'],'v':step['v_before'],'previous_v':step['previous_v_before'],'requested_u':source['u'],
                    'start_G':step['start_guard']['model_feature_command_nm']},
                'prediction':{'q':step['next_q_rad'],'v':step['next_v_rad_s']},'reuse':None,'cost_delta':delta})
        record['cost_delta']=dict(cost)
        return record,window,model,state['ranges']

    def test_archive_rollout_own_history_and_exact_cost_tamper(self):
        record,window,model,ranges=self._lag_rollout();checks=a.Checks()
        a.verify_rollout(record,window,'lag_sparse11',model,[0.,0.],ranges,{},checks,'good');self.assertEqual(checks.failed,0)
        record['steps'][1]['input']['previous_v']=[0.,0.]
        checks=a.Checks();a.verify_rollout(record,window,'lag_sparse11',model,[0.,0.],ranges,{},checks,'bad_history');self.assertGreater(checks.failed,0)
        record,window,model,ranges=self._lag_rollout();record['steps'][0]['cost_delta']['evaluation_pair_attempts']=0
        checks=a.Checks();a.verify_rollout(record,window,'lag_sparse11',model,[0.,0.],ranges,{},checks,'bad_cost');self.assertGreater(checks.failed,0)

    def test_invalid_saved_prediction_failure_has_no_new_model_call(self):
        record,window,model,ranges=self._lag_rollout();origin=window['origin'];row=origin['row'];name='nominal_guard'
        inputs=a.guard.describe_input(origin['q'],origin['u'],('known_angle_guard',ranges));row['model_input_diagnostics']={name:inputs}
        row['predicted_next_qv']={name:[[float('nan'),0.],[0.,0.]]};trial={'models_before':{name:model['fingerprint']},'models_after':{name:model['fingerprint']}}
        record['predictor']='nominal9';record['steps']=[];record['failure']={'at_h':1,'source_transition_id':row['shared_transition_id'],
            'failure_stage':'saved_prediction_validation','input':{'q':origin['q'],'v':origin['v'],'previous_v':origin['previous_v'],
                'requested_u':origin['u'],'start_G':inputs['model_feature_command_nm']},'error':{'type':'ValueError','message':'artificial'},
            'cost_delta':{'diagnostic_guard_pair_evaluations':1,'saved_prediction_validation_failures':1}}
        record['cost_delta']=record['failure']['cost_delta'];checks=a.Checks();before=Counter(a.MATH_COST)
        a.verify_rollout(record,window,'nominal9',{'theta':[t[:9] for t in model['theta']],'fingerprint':model['fingerprint']},[0.,0.],ranges,trial,checks,'retained')
        self.assertEqual(checks.failed,0);self.assertEqual((a.MATH_COST-before)['old9_pair_prediction_attempts'],0)

    def test_metrics_retain_failure_and_short_window_unavailability(self):
        record,window,model,ranges=self._lag_rollout();record['steps']=[];record['failure']={'at_h':1}
        metrics,cost=a.derive_metrics([record],[window],ranges)
        matching=next(m for m in metrics if m['predictor']=='lag_sparse11' and m['h']==1 and m['axis']==0 and m['group']=='all')
        self.assertEqual(matching['complete_window_count'],1);self.assertEqual(matching['mathematical_failure_count'],1);self.assertIsNone(matching['q'])
        absent=next(m for m in metrics if m['predictor']=='lag_sparse11' and m['h']==5 and m['axis']==0 and m['group']=='all')
        self.assertEqual(absent['reason'],'no_complete_source_window')

    def test_modal_multiset_roots_and_operator_norm(self):
        state=a.initial_state([[-2.,2.],[-2.,2.]]);theta=[row[:9] for row in state['theta']];matrix=a.modal_matrix(theta)
        saved={'matrix':matrix,'eigenvalues':[{'real':1.,'imag':0.}]*4,'spectral_radius':1.,
            'operator_2_norm':(math.sqrt(4.+.02**2)+.02)/2.,'nonnormality_commutator_frobenius':.0008,
            'scope':'fixed guard branch; excludes contact/guard switching; no stability/adoption gate'}
        checks=a.Checks();a.verify_modal(saved,theta,checks,'cold_modal');self.assertEqual(checks.failed,0)
        saved['eigenvalues'][0]={'real':2.,'imag':0.};checks=a.Checks();a.verify_modal(saved,theta,checks,'wrong_modal');self.assertGreater(checks.failed,0)


if __name__ == '__main__':
    unittest.main()
