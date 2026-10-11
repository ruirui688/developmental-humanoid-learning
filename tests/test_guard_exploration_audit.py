"""Explicit artificial standard-library C math/scope tests; no archive/physics."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import sys
import unittest

ROOT=next(p for p in Path(__file__).resolve().parents if (p/'pyproject.toml').is_file())
AUDIT=Path(__file__).with_name('audit_guard_exploration_development.py')
if not AUDIT.is_file(): AUDIT=ROOT/'scripts/audit_guard_exploration_development.py'
loader=importlib.util.spec_from_file_location('c_audit_under_test',AUDIT)
c=importlib.util.module_from_spec(loader);sys.modules[loader.name]=c;loader.loader.exec_module(c)

def snapshot(state,qref,trainable=True):
    record=c.b.parameter_record(qref,state)
    return {**record,'parameter_fingerprint':c.digest(record),'vector_update_count':state['count'],
        'scalar_update_count':2*state['count'],'output_update_counts':[state['count']]*2,'trainable':trainable,
        'initial_prior':'generic velocity continuity and torque response; zero cross coefficients',
        'input_boundary':'current native q/v and already known requested u; no actual future torque or simulator state',
        'update_commit':'single immutable state reference for both outputs, covariance and counts'}

def artificial_seeds():
    result=[]
    for seed in range(3):
        def control(value,effort=1.):
            return {'eligible':True,'completed':True,'status':'completed','tracking_rmse_rad':value,
                'tracking_rmse_by_axis_rad':[value,value],'actual_effort_complete':True,
                'control_effort':{k:[effort,effort] for k in c.EFFORT_KEYS}}
        ev={name:{'eligible':True,'completed':True,'status':'completed'} for name in c.KINDS}
        ev.update(nominal_guard=control(10.),learned_sparse=control(7.),learned_continuation=control(4.,1.04),
            PDselected=control(5.),zero=control(12.))
        ev['prediction']['velocity_prediction_rmse']={'nominal_guard':[10.,10.],
            'learned_sparse':[7.,7.],'learned_continuation':[5.,5.]}
        result.append({'seed':seed,'evaluations':ev})
    return result

class ExplorationAuditTests(unittest.TestCase):
    def test_frozen_scope_cannot_shorten(self):
        meta={'schema_version':1,'suite':'guard_exploration_development','synthetic':True,'seeds':[0,1,2],
            'split':'development','pose':'supine','joint_indices':[0,1],'native_joint_count':8,'gpu':None,
            'prefix_steps':100,'calibration_steps':400,'prediction_steps':100,'control_steps_per_trial':200,
            'structures':['coupled_hinge9'],'model_input_basis':'known_angle_guard','pd_gains':{'kp':[64.,64.],'kd':[0.,4.]},
            'policy_parameter_updates':0,'gain_updates':0,'gate_updates':0,'teacher_calls':0,
            'external_demonstration_samples':0,'protocol':{'path':c.PROTOCOL}}
        self.assertIs(c.require_scope(meta,c.SYNTHETIC_SPEC),meta)
        meta['control_steps_per_trial']=1
        with self.assertRaises(ValueError): c.require_scope(meta,c.SYNTHETIC_SPEC)
        with self.assertRaises(ValueError): c.ExplorationAuditSpec(True,True)
        with self.assertRaises(ValueError): c.require_scope(meta,object())

    def test_veto_equalities_axis_independence(self):
        request,diag=c.exploration_command('calibration_continuation',200,[1,1],[.06,0.],[0.,0.],[0.,0.])
        self.assertEqual(request,[0.,.125]);self.assertEqual(diag['command_vetoed'],[True,False])
        self.assertTrue(all(type(x) is float for x in diag['shape']))
        request,diag=c.exploration_command('calibration_continuation',200,[1,1],[0.,0.],[.5,0.],[0.,0.])
        self.assertEqual(request,[0.,.125]);self.assertEqual(diag['velocity_veto'],[True,False])
        request,diag=c.exploration_command('calibration_sparse',200,[1,1],[1.,1.],[9.,9.],[0.,0.])
        self.assertEqual(request,[.125,.125]);self.assertEqual(diag['command_vetoed'],[False,False])

    def test_natural_zero_not_command_veto(self):
        request,diag=c.exploration_command('prediction',3,[1,1],[1.,1.],[9.,9.],[0.,0.])
        self.assertEqual(request,[0.,0.]);self.assertEqual(diag['command_vetoed'],[False,False])
        self.assertEqual(diag['planned_nonzero'],[False,False])

    def test_minimum_excitation(self):
        dose={'nonzero_start_guard_intervals_per_axis':[1,1],'actual_absolute_nm_s':[1.,.1]}
        self.assertTrue(c.excitation_qualified(dose,calibration=True))
        dose['actual_absolute_nm_s'][1]=0.
        self.assertFalse(c.excitation_qualified(dose,calibration=True))
        self.assertTrue(c.excitation_qualified(dose,calibration=False))
        dose['nonzero_start_guard_intervals_per_axis'][1]=0
        self.assertFalse(c.excitation_qualified(dose,calibration=False))
        self.assertFalse(c.excitation_qualified({},calibration=False))

    def test_strict_scientific_gates(self):
        seeds=artificial_seeds();g=c.scientific_gates(seeds)
        self.assertTrue(g['body_contribution']['sparse']['passed'])
        self.assertTrue(g['body_contribution']['continuation']['passed'])
        self.assertTrue(g['exploration_intervention']['passed'])
        self.assertTrue(g['selected_pd_comparison']['continuation']['passed'])
        self.assertFalse(g['selected_pd_comparison']['sparse']['passed'])
        seeds[1]['evaluations']['learned_continuation']['tracking_rmse_by_axis_rad'][1]=7.
        self.assertFalse(c.scientific_gates(seeds)['exploration_intervention']['passed'])

    def test_effort_both_channels_and_zero_rule(self):
        seeds=artificial_seeds()
        seeds[0]['evaluations']['learned_continuation']['control_effort'][c.EFFORT_KEYS[3]]=[1.5,1.5]
        self.assertFalse(c.scientific_gates(seeds)['exploration_intervention']['passed'])
        seeds=artificial_seeds()
        for seed in seeds:
            for name in ('learned_sparse','learned_continuation'):
                seed['evaluations'][name]['control_effort'][c.EFFORT_KEYS[2]]=[0.,0.]
        self.assertTrue(c.scientific_gates(seeds)['exploration_intervention']['passed'])
        seeds[0]['evaluations']['learned_continuation']['control_effort'][c.EFFORT_KEYS[2]]=[.00001,0.]
        self.assertFalse(c.scientific_gates(seeds)['exploration_intervention']['passed'])

    def test_stopped_calibration_cannot_open_gates(self):
        seeds=artificial_seeds();ev=seeds[0]['evaluations']
        ev['calibration_continuation'].update(status='terminated',completed=False,eligible=False)
        gates=c.scientific_gates(seeds)
        self.assertFalse(gates['body_contribution']['continuation']['passed'])
        self.assertFalse(gates['exploration_intervention']['passed'])
        self.assertFalse(gates['selected_pd_comparison']['continuation']['passed'])

    def test_control_view_preserves_archive_and_globals(self):
        kind='learned_sparse';ep={'seed':0,'trial_id':'seed0_'+kind,'kind':kind,
            'phase_budgets':{p:{'physics_steps':0} for p in c.PHASES}}
        sr={'seed':0,'reference_q':[0.,0.],'direction':[1,1],'public_joint_ranges':[[-2.,2.]]*2,
            'native_prefix_observation':{'joint_velocity':[0.]*8},'environment_fingerprint_before':'test',
            'evaluations':{kind:{field:{kind:[1.,2.],'persistence':[2.,3.]}
                for field in ('position_prediction_rmse','velocity_prediction_rmse','metric_prediction_step_count')}},
            'fresh_prefix_bindings':{kind:{'reference_q':[0.,0.]}}}
        row={'trial_id':ep['trial_id'],'kind':kind,'step_index':100,'shared_transition_id':ep['trial_id']+':100',
            'predicted_next_qv':{kind:[[1.,2.],[3.,4.]],'persistence':[[0.,0.],[0.,0.]]},
            'model_input_diagnostics':{kind:{'model_feature_command_nm':[.125,0.]}}}
        original=deepcopy((sr,ep,row));source,view,episode,rows=c.canonical_control_view(sr,ep,[row],kind)
        self.assertEqual((sr,ep,row),original);self.assertEqual(c.b.MODEL,'coupled_guard')
        self.assertEqual(c.b.PHASES,('prefix','control'));self.assertEqual(set(episode['phase_budgets']),set(c.b.PHASES))
        self.assertEqual(rows[0]['predicted_next_qv']['coupled_guard'],row['predicted_next_qv'][kind])

    def test_failed_atomic_proposal_is_not_commit(self):
        state=c.b.initial_state([[-2.,2.],[-2.,2.]]);qref=[0.,0.];checks=c.Checks()
        snap=snapshot(state,qref);c.b.verify_snapshot(snap,state,qref,checks,'initial',True)
        source={'shared_transition_id':'seed0_calibration_sparse:100','step_index':100,
            'observation_before':{'joint_position':[0.]*8,'joint_velocity':[0.]*8},
            'observation_after':{'joint_position':[0.]*8,'joint_velocity':[.02,.01]+[0.]*6},
            'requested_torque':[.125,.125]+[0.]*6,'returned_step_diagnostics':{'executed_substeps':10},
            'model_update':None,'model_snapshot_after':snap}
        x=c.b.features(qref,[0.,0.],[0.,0.],[.125,.125],state['ranges'])
        theta,cov,residual=c.b.pair_support.replay_rls(state['theta'][0],state['covariance'][0],x[0],.02)
        source['failure_accounting']={'pair_update_accounting':{'committed_scalar_updates':0,'snapshot_after_attempt':snap,
            'proposed_outputs':[{'output_index':0,'features':x[0],'observed_next_v_rad_s':.02,
                'preupdate_error_rad_s':residual,'proposed_coefficients':theta,'proposed_covariance':cov,'committed':False}]}}
        regular=[{'shared_transition_id':f'prefix:{i}','diagnostics':{'executed_substeps':10}} for i in range(100)]
        delta,full=c.replay_failed_atomic_update(source,regular,{'control_steps':101,'physics_steps':1010},state,qref,checks,'failed')
        self.assertTrue(full);self.assertEqual(delta,0);self.assertEqual(state['count'],0);self.assertEqual(checks.failed,0)
        source['failure_accounting']['pair_update_accounting']['committed_scalar_updates']=1
        c.replay_failed_atomic_update(source,regular,{'control_steps':101,'physics_steps':1010},state,qref,checks,'invalid')
        self.assertGreater(checks.failed,0)

if __name__=='__main__': unittest.main(verbosity=2)
