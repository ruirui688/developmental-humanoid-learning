"""Small handwritten E archive contracts; no archive matrix or old raw data."""
from __future__ import annotations
import ast
from collections import Counter
import copy
import importlib.util
import json
from pathlib import Path
import sys
import unittest

SOURCE=Path(__file__).resolve().parents[1]/'scripts/audit_guard_lag_control.py'
spec=importlib.util.spec_from_file_location('_E_handwritten_contract',SOURCE)
m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)

def ev(joint,axes=None,effort=1.):
    return {'eligible':True,'completed':True,'status':'completed','tracking_rmse_rad':joint,
        'tracking_rmse_by_axis_rad':[joint,joint] if axes is None else axes,'actual_effort_complete':True,
        'control_effort':{'actual_absolute_nm_s':[effort,effort],'actual_squared_nm2_s':[effort,effort]}}

def seeds():
    return [{'seed':s,'evaluations':{'cold11':ev(1.),'learned_sparse11':ev(.7),'PDselected':ev(.8),'zero':ev(2.)}} for s in (0,1,2)]

def native():
    return {k:[0.]*n for k,n in m.common.NATIVE.items()}

def diagnostic(index=0,n=10):
    return {'step_id':index+1,'physics_steps':(index+1)*10,'time':(index+1)*.02,'executed_substeps':n,
        'terminated':False,'requested_torque':[0.]*8,'accepted_torque':[0.]*8,'applied_torque':[0.]*8,
        'applied_torque_history':[[0.]*8 for _ in range(n)],'guarded_substeps':0,
        'substep_ground_normal_forces':[0.]*n,'substep_kinetic_energies':[0.]*n,
        'substep_minimum_contact_distances':[0.]*n,'peak_substep_ground_normal_force':0.,
        'ground_normal_impulse_ns':0.,'peak_substep_kinetic_energy':0.,'minimum_substep_contact_distance':0.}

class ContractChecks(unittest.TestCase):
    def test_formal_staging_rejects_before_reads(self):
        before=Counter(m.READ_COST)
        prior=m.FORMAL_AUDIT_ENABLED
        try:
            m.FORMAL_AUDIT_ENABLED=False
            with self.assertRaises(RuntimeError):m.audit(Path('never-read-existing-or-original-archive'))
        finally:
            m.FORMAL_AUDIT_ENABLED=prior
        self.assertEqual(m.READ_COST,before)
    def test_declared_source_whitelist(self):
        self.assertTrue(all(m.source_name_allowed(n) for n in m.required_sources()))
        self.assertFalse(m.source_name_allowed('results/cpu_validation/original_C/raw/trace.jsonl.gz'))
        self.assertFalse(m.source_name_allowed('src/developmental_physics/hidden/submodule.py'))
        self.assertFalse(m.source_name_allowed('scripts/audit_guard_exploration_development.py'))
    def test_gates_keep_four_keys_and_C4_false(self):
        g=m.development_gates(seeds())
        self.assertEqual(set(g),{'control_hypothesis','pd_reference','matrix_complete','c4_scientific_validation'})
        self.assertTrue(g['control_hypothesis']['passed']);self.assertTrue(g['pd_reference']['passed'])
        self.assertTrue(g['matrix_complete']);self.assertFalse(g['c4_scientific_validation']['evaluated'])
        self.assertFalse(g['c4_scientific_validation']['passed'])
    def test_failed_seed_and_axis_and_effort_never_pass(self):
        stopped=seeds();stopped[1]['evaluations']['learned_sparse11'].update(eligible=False,completed=False,status='terminated',tracking_rmse_rad=.0001)
        g=m.development_gates(stopped)
        self.assertFalse(g['control_hypothesis']['evaluated']);self.assertFalse(g['pd_reference']['evaluated']);self.assertFalse(g['matrix_complete'])
        axis=seeds();axis[0]['evaluations']['learned_sparse11']['tracking_rmse_by_axis_rad'][1]=1.1
        self.assertFalse(m.development_gates(axis)['control_hypothesis']['passed'])
        effort=seeds();effort[0]['evaluations']['learned_sparse11']['control_effort']['actual_squared_nm2_s']=[2.,2.]
        self.assertFalse(m.development_gates(effort)['control_hypothesis']['passed'])
    def test_raw_seed_mean_not_pooled_or_average_percent(self):
        rows=seeds()
        for sr,a,z in zip(rows,(1.,10.,100.),(.7,7.,70.)):
            sr['evaluations']['cold11']=ev(a);sr['evaluations']['learned_sparse11']=ev(z)
        gate=m.development_gates(rows)['control_hypothesis']
        self.assertAlmostEqual(gate['baseline_raw_mean_joint_rmse'],37.)
        self.assertAlmostEqual(gate['candidate_raw_mean_joint_rmse'],25.9)
        self.assertAlmostEqual(gate['joint_mean_improvement'],.3)
        zero=seeds()
        for sr in zero:
            sr['evaluations']['cold11']=ev(0.,effort=0.);sr['evaluations']['learned_sparse11']=ev(0.,effort=0.)
        self.assertFalse(m.development_gates(zero)['control_hypothesis']['passed'])
    def test_partial_current_keeps_paid_past_history(self):
        rows=[None]*98
        for i in range(98,101):
            obs=native();obs['joint_velocity'][:2]=[i*.001,-i*.001]
            before=native();before['joint_velocity'][:2]=[(i-1)*.001,-(i-1)*.001]
            rows.append({'trial_id':'tiny','step_index':i,'phase':'prefix' if i<100 else 'control',
                'shared_transition_id':f'tiny:{i}','observation_before':before,'observation_after':obs,
                'diagnostics':{'executed_substeps':10 if i<100 else 3,'terminated':i==100},'study_abort':None})
        result=m.native_history(rows,100)
        self.assertEqual(result['previous_v'],rows[98]['observation_after']['joint_velocity'][:2])
        self.assertEqual(result['history_transition_ids'],['tiny:98','tiny:99'])
        bad=copy.deepcopy(rows);bad[98]['diagnostics']['executed_substeps']=9
        with self.assertRaises(ValueError):m.native_history(bad,100)
        bad=copy.deepcopy(rows);bad[99]['observation_before']['joint_velocity'][0]=99.
        with self.assertRaises(ValueError):m.native_history(bad,100)
    def test_failed_head_ledger_retained_with_lower_bound(self):
        checks=m.Checks();base=m.guard.empty_meter()
        failure={'failure_accounting':{'structured_failure':{'type':'PairPredictionError','message':'artificial first head overflow',
            'scalar_prediction_attempts':1,'scalar_prediction_successes':0,'failure_stage':'velocity_output_0'}}}
        ledger=m.failed_diagnostic_meter(base,failure,checks,'manual-known')
        self.assertEqual(checks.failed,0);self.assertEqual(ledger['pair_prediction_attempts'],1)
        self.assertEqual(ledger['scalar_prediction_attempts'],1);self.assertEqual(ledger['scalar_prediction_successes'],0)
        unknown=m.failed_diagnostic_meter(base,{'failure_accounting':{}},checks,'manual-unknown')
        self.assertTrue(unknown['scalar_counts_is_lower_bound']);self.assertEqual(unknown['unknown_scalar_failure_count'],1)
    def test_one_returned_unwritten_prefix_is_paid_and_ineligible(self):
        checks=m.Checks();tid='seed0_zero';error={'type':'OSError','message':'handwritten writer failure'}
        episode={'trial_id':tid,'seed':0,'kind':'zero','maximum_control_steps':300,'status':'exception','completed':False,
            'reason':error,'collector_exception':error,'study_abort':None,'environment_terminated':False,'environment_stop_reason':None,
            'control_calls_attempted':1,'control_steps':1,'physics_steps':10,'returned_steps':1,'written_returned_steps':0,
            'returned_unwritten_steps':1,'unreturned_physics_steps':0,'risk_telemetry_complete':False,
            'phase_budgets':{'prefix':{'control_calls_attempted':1,'control_steps':1,'physics_steps':10},
                'control':{'control_calls_attempted':0,'control_steps':0,'physics_steps':0}}}
        evaluation={'status':'exception','completed':False,'study_abort':None,'environment_terminated':False,
            'environment_stop_reason':None,'collector_exception':error,'tracking_rmse':None,'metric_control_step_count':0,
            'partial_interval_target_errors_rad':[],'saturated_control_steps_per_axis':[0,0],
            'phase_effort':{p:m.guard.new_effort() for p in m.PHASES},'control_effort':m.guard.new_effort(),
            'phase_effort_combined':{p:{k:0. for k in m.guard.EFFORT_KEYS} for p in m.PHASES},
            'phase_actual_effort_substeps':{'prefix':10,'control':0},'phase_actual_effort_complete':{'prefix':True,'control':True},
            'phase_missing_actual_effort_substeps':{'prefix':0,'control':0},'actual_effort_complete':True,
            'actual_effort_is_lower_bound':False,'actual_control_effort_substeps':0,'missing_control_effort_substeps':0}
        ex={'trial_id':tid,'seed':0,'kind':'zero','step_index':0,'phase':'prefix','collector_exception':error,
            'requested_torque':[0.]*8,'target_q':None,'observation_before':native(),'observation_after':native(),
            'qpos':[0.]*15,'qvel':[0.]*14,'returned_step_diagnostics':diagnostic(),'diagnostics':diagnostic()}
        result,regular,exceptions=m.physical_base({'evaluations':{'zero':evaluation}},episode,[ex],[[-1.,1.]]*8,checks)
        self.assertEqual(checks.failed,0,checks.violations)
        self.assertEqual(result['reconstructed_returned_unwritten_endpoints'],1)
        self.assertEqual(result['unreconstructed_physics_substeps'],0)
        self.assertFalse(result['eligible']);self.assertEqual(len(regular),0);self.assertEqual(len(exceptions),1)

if __name__=='__main__':unittest.main()
