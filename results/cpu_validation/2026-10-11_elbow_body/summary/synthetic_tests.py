"""Finite synthetic boundaries only; never reads formal body inputs."""
import ast
import copy
import importlib.util
from pathlib import Path
import unittest

SOURCE = Path(__file__).with_name('elbow_body_summary_prepare.py')
spec = importlib.util.spec_from_file_location('elbow_summary_synthetic', SOURCE)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def synthetic_trial(*, partial=False, study=False, missing=0):
    rows = []
    qref, q, v = .02, .02, .2
    for index in range(101):
        active = index == 100
        before_q, before_v = [9., q, 0., 0., 0., 0., 0., 0.], [8., v, 0., 0., 0., 0., 0., 0.]
        if active and study:
            q = .14
        after_q, after_v = [9., q, 0., 0., 0., 0., 0., 0.], [8., v, 0., 0., 0., 0., 0., 0.]
        request = [0., .5 if active else 0., 0., 0., 0., 0., 0., 0.]
        torque = [7. if active else 0., .25 if active else 0., 0., 0., 0., 0., 0., 0.]
        n = 3 if active and partial else 10
        obs_before = {'joint_position': before_q, 'joint_velocity': before_v,
                      'actuator_torque': [0.]*8, 'previous_command': [0.]*8}
        obs_after = {'joint_position': after_q, 'joint_velocity': after_v,
                     'actuator_torque': [0.]*8, 'previous_command': [0.]*8}
        row = {'trial_id': 'seed0_learned_mpc', 'kind': 'learned_mpc', 'step_index': index,
            'phase': 'control' if active else 'prefix', 'requested_torque': request,
            'observation_before': obs_before, 'observation_after': obs_after,
            'predicted_next_qv': {'learned_mpc': [.05, .6]} if active else {},
            'target_q': .04 if active else None, 'model_update': None,
            'partial_interval_target_error_rad': q-.04 if active and partial else None,
            'diagnostics': {'executed_substeps': n, 'applied_torque_history': [torque.copy() for _ in range(n)],
                            'requested_torque': request, 'terminated': active and not study},
            'qpos': [0.]*7+after_q, 'qvel': [0.]*6+after_v,
            'study_abort': None, 'invalid_numeric_fields': []}
        if active and study:
            row['study_abort'] = {'type': 'StudyAbort', 'message': 'predeclared native active envelope reached',
                'stage': 'endpoint', 'triggers': ['absolute_q_minus_qref_rad'], 'q_rad': q, 'qref_rad': qref,
                'q_minus_qref_rad': q-qref, 'velocity_rad_s': v,
                'thresholds': {'absolute_q_minus_qref_rad': .12, 'absolute_velocity_rad_s': 1.},
                'feedback_action': None, 'phase': 'control', 'step_index': index}
        rows.append(row)
    control_physics = rows[-1]['diagnostics']['executed_substeps']+missing
    ep = {'trial_id': 'seed0_learned_mpc', 'kind': 'learned_mpc', 'status': 'terminated',
        'control_calls_attempted': len(rows)+int(missing > 0), 'control_steps': len(rows),
        'physics_steps': 1000+control_physics, 'study_abort': rows[-1]['study_abort'],
        'environment_terminated': not study,
        'phase_budgets': {p: {'physics_steps': 1000 if p == 'prefix' else control_physics if p == 'control' else 0}
                         for p in m.PHASES}}
    if missing:
        rows.append({'collector_exception': {'type': 'OSError'}, 'phase': 'control', 'requested_torque': [0., .5]+[0.]*6})
    return ep, rows, qref


def gate_seeds():
    template = {'eligible': True, 'completed': True, 'status': 'completed', 'study_aborted': False,
                'environment_terminated': False, 'tracking_rmse_rad': .79,
                'velocity_prediction_rmse': {'nominal_mpc': 1., 'learned_mpc': .8},
                'actual_effort_complete': True, 'control_effort': {k: 0. for k in m.EFFORT}}
    result = []
    for seed in m.SEEDS:
        ev = {k: copy.deepcopy(template) for k in m.KINDS}
        ev['nominal_mpc']['tracking_rmse_rad'] = 1.
        ev['tuned_pd']['tracking_rmse_rad'] = .9
        result.append({'seed': seed, 'evaluations': ev})
    return result


def cold_fixture():
    qref = -.0005
    initial = {'qref_rad': qref, 'dt_seconds': .02,
        'features': ['v', 'q-qref', 'requested_torque', 'sign(u)*max(abs(u)-0.25,0)', '1'],
        'initial_coefficients': [1., 0., .02, 0., 0.], 'initial_covariance_scale': 100.,
        'forgetting_factor': 1., 'coefficients': [1., 0., .02, 0., 0.],
        'covariance': [[100. if i == j else 0. for j in range(5)] for i in range(5)], 'dtype': 'float64',
        'hinge_threshold_nm': .25, 'hinge_threshold_updates': 0,
        'hinge_structure_prior': 'fixed signed torque hinge; structural prior, not a learned threshold or physics label',
        'update_count': 0, 'trainable': False}
    initial['parameter_fingerprint'] = m.digest(m.parameter_record(initial))
    sr = {'seed': 0, 'reference_q': qref, 'direction': 1,
        'selection_record': {'joint_index': 1, 'joint_position_rad': qref, 'lower_limit_rad': 0.,
            'upper_limit_rad': 2., 'positive_room_rad': 2.-qref, 'negative_room_rad': qref, 'direction': 1},
        'initial_models': {'short_hinge5': initial}, 'learned_models': {}, 'evaluations': {},
        'calibration_completed': {'short': False}}
    ep = {k: {'status': 'blocked' if k in ('prediction_low', 'prediction_full', 'learned_mpc') else 'terminated'}
          for k in m.KINDS}
    return sr, ep, {k: [] for k in m.KINDS}


class Boundaries(unittest.TestCase):
    def test_standard_library_and_no_physical_imports(self):
        tree = ast.parse(SOURCE.read_text(encoding='utf-8'))
        names = [a.name.split('.')[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names]
        names += [n.module.split('.')[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module]
        self.assertFalse(set(names) & {'numpy', 'mujoco', 'developmental_physics', 'audit_local_frozen'})

    def test_real_native_j1_metrics_not_j0(self):
        ep, rows, qref = synthetic_trial()
        checks = m.Checks()
        result, _ = m.rebuild_trial(ep, rows, checks, qref)
        self.assertEqual(checks.failures, [])
        self.assertAlmostEqual(result['tracking_rmse_rad'], .02)
        self.assertAlmostEqual(result['position_prediction_rmse']['learned_mpc'], .03)
        self.assertAlmostEqual(result['velocity_prediction_rmse']['learned_mpc'], .4)
        self.assertAlmostEqual(result['control_effort']['actual_absolute_nm_s'], .005)
        self.assertAlmostEqual(result['control_effort']['actual_squared_nm2_s'], .00125)
        self.assertFalse(result['completed'])

    def test_partial_cost_kept_but_not_scored(self):
        ep, rows, qref = synthetic_trial(partial=True)
        checks = m.Checks()
        result, _ = m.rebuild_trial(ep, rows, checks, qref)
        self.assertEqual(checks.failures, [])
        self.assertIsNone(result['tracking_rmse_rad'])
        self.assertIsNone(result['velocity_prediction_rmse']['learned_mpc'])
        self.assertEqual(result['partial_interval_target_errors_rad'], [-.02])
        self.assertAlmostEqual(result['control_effort']['actual_absolute_nm_s'], .0015)

    def test_study_stop_is_separate_from_environment(self):
        ep, rows, qref = synthetic_trial(study=True)
        checks = m.Checks()
        result, _ = m.rebuild_trial(ep, rows, checks, qref)
        self.assertEqual(checks.failures, [])
        self.assertTrue(result['study_aborted'])
        self.assertFalse(result['environment_terminated'])
        self.assertFalse(result['eligible'])
        self.assertEqual(result['study_abort_payload']['triggers'], ['absolute_q_minus_qref_rad'])

    def test_missing_actual_is_lower_bound_request_recovers(self):
        ep, rows, qref = synthetic_trial(missing=2)
        checks = m.Checks()
        result, _ = m.rebuild_trial(ep, rows, checks, qref)
        self.assertEqual(checks.failures, [])
        detail = result['phase_effort']['control']
        self.assertTrue(detail['actual_effort_is_lower_bound'])
        self.assertFalse(result['actual_effort_complete'])
        self.assertTrue(detail['requested_effort_reconstruction_complete'])
        self.assertAlmostEqual(detail['independent_effort']['requested_absolute_nm_s'], .012)
        self.assertAlmostEqual(detail['independent_effort']['actual_absolute_nm_s'], .005)

    def test_five_six_seven_gates_independent(self):
        seeds = gate_seeds()
        contribution = m.independent_model_gate(seeds)
        self.assertTrue(contribution['passed'])
        self.assertTrue(m.independent_classical_gate(seeds, contribution)['passed'])
        seeds[0]['evaluations']['zero_torque']['completed'] = False
        self.assertFalse(m.complete_trials(seeds, m.KINDS))
        self.assertTrue(m.independent_model_gate(seeds)['passed'])
        seeds[0]['evaluations']['prediction_full']['completed'] = False
        self.assertFalse(m.independent_model_gate(seeds)['evaluated'])
        self.assertFalse(m.independent_classical_gate(seeds, contribution)['evaluated'])

    def test_zero_denominators_and_no_threshold_epsilon(self):
        seeds = gate_seeds()
        seeds[0]['evaluations']['prediction_low']['velocity_prediction_rmse']['learned_mpc'] = .800000000001
        self.assertFalse(m.independent_model_gate(seeds)['passed'])
        for seed in seeds:
            seed['evaluations']['nominal_mpc']['tracking_rmse_rad'] = 0.
            seed['evaluations']['learned_mpc']['tracking_rmse_rad'] = 0.
            seed['evaluations']['prediction_low']['velocity_prediction_rmse'] = {'nominal_mpc': 0., 'learned_mpc': 0.}
        gate = m.independent_model_gate(seeds)
        self.assertIsNone(gate['tracking_mean_improvement'])
        self.assertIsNone(gate['per_seed'][0]['prediction_gates']['prediction_low']['relative_improvement'])
        self.assertFalse(gate['passed'])

    def test_native_domain_and_cold_freeze_faults(self):
        ep, rows, qref = synthetic_trial()
        cal = [copy.deepcopy(rows[-1])]
        cal[0]['observation_before']['joint_position'][1] = qref
        control = [copy.deepcopy(rows[-1])]
        control[0]['observation_before']['joint_position'][1] = qref+.01
        control[0]['observation_before']['joint_velocity'][1] += .01
        cov = m.coverage(cal, control, qref)
        self.assertEqual((cov['q_outside_count'], cov['v_outside_count'], cov['either_outside_count']), (1, 1, 1))
        sr, episodes, regular = cold_fixture()
        checks = m.Checks()
        out = m.cold_frozen_checks(sr, episodes, regular, checks)
        self.assertEqual(checks.failures, [])
        self.assertEqual(out['selection']['joint_position_rad'], -.0005)
        sr['initial_models']['short_hinge5']['coefficients'][0] = .9
        m.cold_frozen_checks(sr, episodes, regular, checks)
        self.assertTrue(any('fresh_initial' in f for f in checks.failures))
        sr, episodes, regular = cold_fixture()
        sr['evaluations']['zero_torque'] = {'models_before': {}, 'models_after': {'evil': 'changed'},
            'integration_models_before': {}, 'integration_models_after': {}}
        checks = m.Checks()
        m.cold_frozen_checks(sr, episodes, regular, checks)
        self.assertTrue(any('frozen_parameters' in f for f in checks.failures))


if __name__ == '__main__':
    unittest.main(verbosity=2)
