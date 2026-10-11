"""Small handwritten candidate/history checks; no formal 81-candidate replay."""
from collections import Counter
from copy import deepcopy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import time
import unittest

HERE=Path(__file__).resolve().parent
SOURCE=HERE/'lag_control_audit_math.py'
spec=importlib.util.spec_from_file_location('_handwritten_E_math',SOURCE)
a=importlib.util.module_from_spec(spec);sys.modules[spec.name]=a;spec.loader.exec_module(a)
EVENTS=[]

def cold():return a.lag.initial_state([[-2.,2.],[-2.,2.]])['theta']
def run(theta,*,q=(0.,0.),v=(0.,0.),pv=(0.,0.),qref=(0.,0.),target=(0.,0.),torque=(0.,0.),ranges=((-2.,2.),(-2.,2.))):
    return a.candidate_math(theta,[list(r) for r in ranges],list(qref),list(q),list(v),list(pv),list(target),[0.,0.],list(torque))

class SmallHistoryChecks(unittest.TestCase):
    def setUp(self):self.before=Counter(a.COUNTS);self.math_before=Counter(a.lag.MATH_COST)
    def tearDown(self):EVENTS.append({'test':self.id(),'planner_math_delta':dict(a.COUNTS-self.before),'original_lag_math_delta':dict(a.lag.MATH_COST-self.math_before)})

    def test_history_is_explicit_and_missing_history_costs_zero(self):
        before=Counter(a.lag.MATH_COST)
        with self.assertRaises(ValueError):a.candidate_math(cold(),[[-2.,2.],[-2.,2.]],[0.,0.],[0.,0.],[0.,0.],None,[0.,0.],[0.,0.],[0.,0.])
        self.assertEqual(a.lag.MATH_COST,before)

    def test_own_history_recursive_values_and_immutable_input(self):
        theta=cold();theta[0][0]=.5;theta[0][9]=.25;original=deepcopy(theta)
        result=run(theta,v=(.4,0.),pv=(.2,0.));history=result['history_diagnostics']
        for item,want in zip(history,[.25,.0875,.003125]):self.assertAlmostEqual(item['predicted_v'][0],want,places=14)
        self.assertEqual(history[1]['previous_v'],[.4,0.]);self.assertEqual(history[2]['previous_v'],history[0]['predicted_v'])
        self.assertEqual(theta,original);self.assertEqual(result['accounting']['pair_prediction_attempts'],15)

    def test_each_candidate_reinitializes_same_native_history(self):
        theta=cold();theta[0][0]=.5;theta[0][9]=.25
        positive=run(theta,v=(.4,0.),pv=(.2,0.),torque=(.125,0.));negative=run(theta,v=(.4,0.),pv=(.2,0.),torque=(-.125,0.))
        self.assertEqual(positive['history_diagnostics'][0]['v'],negative['history_diagnostics'][0]['v'])
        self.assertEqual(positive['history_diagnostics'][0]['previous_v'],negative['history_diagnostics'][0]['previous_v'])
        self.assertNotEqual(negative['history_diagnostics'][0]['previous_v'],positive['history_diagnostics'][-1]['previous_v'])

    def test_guard_switch_uses_own_predicted_positions(self):
        result=run(cold(),qref=(.16,0.),q=(.16,0.),v=(.2,0.),pv=(.2,0.),target=(.16,0.),torque=(.5,0.),ranges=((-2.,.2),(-2.,2.)))
        self.assertTrue(result['candidate_record']['feasible']);history=result['history_diagnostics']
        for item,want in zip(history[:4],[.21,.22,.23,.23]):self.assertAlmostEqual(item['predicted_v'][0],want,places=14)
        self.assertGreater(history[3]['q'][0],.17);self.assertEqual(history[3]['previous_v'],history[1]['predicted_v'])

    def test_position_rejected_endpoint_is_paid_but_not_scored(self):
        theta=cold();theta[0]=[0.]*11;theta[0][8]=.8
        result=run(theta);record=result['candidate_record']
        self.assertEqual(record['rejection_reason'],'forecast_position_bounds');self.assertEqual(record['completed_prediction_steps'],9)
        self.assertEqual(result['accounting']['pair_prediction_attempts'],10);self.assertEqual(result['accounting']['scalar_prediction_attempts'],20)
        self.assertAlmostEqual(result['axis_costs'][0],.016**2*285+9*.002*.8**2,places=14)
        self.assertFalse(result['history_diagnostics'][-1]['accepted'])

    def test_velocity_rejection_has_two_paid_successful_heads(self):
        theta=cold();theta[0]=[0.]*11;theta[0][8]=1.6
        result=run(theta);record=result['candidate_record']
        self.assertEqual(record['rejection_reason'],'forecast_velocity_bound');self.assertEqual(record['completed_prediction_steps'],0)
        self.assertEqual(result['accounting']['pair_prediction_successes'],1);self.assertEqual(result['accounting']['scalar_prediction_successes'],2)

    def test_nonfinite_first_head_has_exact_lower_level_cost(self):
        theta=cold();theta[0][0]=1e308;result=run(theta,v=(2.,0.))
        self.assertEqual(result['candidate_record']['rejection_reason'],'prediction_error:PairPredictionError')
        self.assertEqual(result['accounting']['pair_prediction_attempts'],1);self.assertEqual(result['accounting']['pair_prediction_successes'],0)
        self.assertEqual(result['accounting']['scalar_prediction_attempts'],1);self.assertEqual(result['accounting']['scalar_prediction_successes'],0)

    def test_original_candidate_order_exact_tie_and_zero_fallback(self):
        self.assertEqual(len(a.CANDIDATES),81);self.assertEqual(a.CANDIDATES[0],(-.5,-.5));self.assertEqual(a.CANDIDATES[40],(0.,0.));self.assertEqual(a.CANDIDATES[-1],(.5,.5))
        def item(torque,cost):return {'candidate_record':{'torque':torque,'cost':cost,'feasible':True},'predicted_q':[],'predicted_v':[]}
        chosen=a.choose_feasible([item([.125,0.],1.),item([-.125,0.],1.),item([.5,0.],1.)])
        self.assertEqual(chosen['torque'],[-.125,0.]);self.assertEqual(a.choose_feasible([])['torque'],[0.,0.])

def main():
    attempt=1
    while (HERE/f'artificial_{attempt:03d}.json').exists():attempt+=1
    prefix=HERE/f'artificial_{attempt:03d}';source=SOURCE.read_bytes();test=Path(__file__).read_bytes()
    (HERE/f'artificial_{attempt:03d}_math.py').write_bytes(source);(HERE/f'artificial_{attempt:03d}_tests.py').write_bytes(test)
    stream=io.StringIO();wall,cpu=time.perf_counter(),time.process_time()
    result=unittest.TextTestRunner(stream=stream,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(SmallHistoryChecks))
    report={'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),
        'source_sha256':hashlib.sha256(source).hexdigest(),'test_sha256':hashlib.sha256(test).hexdigest(),
        'original_lag_auditor_sha256':a.LAG_SUPPORT_SHA,'per_test':EVENTS,'planner_math_totals':dict(a.COUNTS),
        'original_lag_math_totals':dict(a.lag.MATH_COST),'timing':{'wall_seconds':time.perf_counter()-wall,'cpu_seconds':time.process_time()-cpu},
        'formal_additions':{'D_raw_reads':0,'real_fit':0,'real_prediction':0,'physics':0,'online_helper_imports':0,'git':0,'formal_full_81_candidate_replays':0},
        'artificial_only':True,'formal_archive_audit_ready':False}
    prefix.with_suffix('.log').write_text(stream.getvalue(),encoding='utf-8');prefix.with_suffix('.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(stream.getvalue());print(json.dumps(report,allow_nan=False));return 0 if result.wasSuccessful() else 1
if __name__=='__main__':raise SystemExit(main())
