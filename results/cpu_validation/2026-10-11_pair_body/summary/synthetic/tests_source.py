"""Finite hand-computed pure-data checks; never open formal raw/audit files."""
import importlib.util
import math
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('pair_summary_under_test', Path(__file__).with_name('pair_body_summary_prepare.py'))
summary = importlib.util.module_from_spec(spec)
spec.loader.exec_module(summary)


def row(index, request, history, q=None, target=None):
    q = list(q or [0.]*8)
    return {'step_index': index, 'requested_torque': list(request), 'target_q': target,
            'diagnostics': {'executed_substeps': len(history), 'applied_torque_history': history},
            'observation_after': {'joint_position': q}}


class SummaryTests(unittest.TestCase):
    def test_rmse_joint_denominator_and_per_axis(self):
        result = summary.paired_rmse([[3., 4.], [0., 0.]])
        self.assertAlmostEqual(result['joint'], 2.5)
        self.assertAlmostEqual(result['per_axis'][0], math.sqrt(4.5))
        self.assertAlmostEqual(result['per_axis'][1], math.sqrt(8.))
        self.assertEqual(result['complete_endpoints'], 2)
        self.assertIsNone(summary.paired_rmse([]))

    def test_full_pulse_slots_exact_5_5_5_5(self):
        self.assertEqual([summary.pulse(i) for i in range(20)], [1]*5+[0]*5+[-1]*5+[0]*5)

    def test_calibration_block8_negative_first_step(self):
        self.assertEqual(summary.calibration_command(160, [1,1]), [0., .5])
        self.assertEqual(summary.calibration_command(169, [1,1]), [0., 0.])
        self.assertEqual(summary.calibration_command(170, [1,1]), [0., -.5])
        self.assertEqual(summary.calibration_command(174, [1,1]), [0., -.5])
        self.assertEqual(summary.calibration_command(175, [1,1]), [0., 0.])

    def test_calibration_phase_shapes_and_direction(self):
        self.assertEqual(summary.calibration_command(0, [-1,1]), [-.125,0.])
        self.assertEqual(summary.calibration_command(100, [-1,1]), [0.,.125])
        self.assertEqual(summary.calibration_command(200, [-1,1]), [-.125,.125])
        self.assertEqual(summary.calibration_command(300, [-1,1]), [-.125,-.125])
        with self.assertRaises(ValueError): summary.calibration_command(400,[1,1])

    def test_full_schedule_hand_computed_effort(self):
        commands = [summary.calibration_command(i,[1,1])+[0.]*6 for i in range(400)]
        records = [row(100+i,u,[u]*10) for i,u in enumerate(commands)]
        effort = summary.add_effort(records)
        for i in range(2):
            self.assertAlmostEqual(effort['per_axis']['requested_absolute_nm_s'][i], .9)
            self.assertAlmostEqual(effort['per_axis']['requested_squared_nm2_s'][i], .31875)
        self.assertEqual(effort['physics_substeps'],4000)
        self.assertAlmostEqual(effort['combined']['actual_absolute_nm_s'],1.8)

    def test_partial_effort_and_guard_count_not_ten(self):
        request = [.5,-.25]+[0.]*6
        history = [[.5,0.]+[0.]*6,[.5,-.25]+[0.]*6,[0.,-.25]+[0.]*6]
        value = summary.add_effort([row(0,request,history)])
        self.assertEqual(value['physics_substeps'],3)
        self.assertEqual(value['permission_screened_substeps_native8'],[1,1]+[0]*6)
        self.assertAlmostEqual(value['per_axis']['requested_absolute_nm_s'][0],.003)
        self.assertAlmostEqual(value['per_axis']['actual_absolute_nm_s'][0],.002)
        self.assertAlmostEqual(value['per_axis']['actual_squared_nm2_s'][1],.00025)

    def test_abs_velocity_stop_equal_and_cross_axis(self):
        self.assertEqual(summary.triggers([0.,0.], [.999, -1.], [0.,0.]),
                         [{'joint_index':1,'signal':'absolute_velocity_rad_s'}])
        self.assertEqual(summary.triggers([.12,0.], [0.,0.], [0.,0.]),
                         [{'joint_index':0,'signal':'absolute_q_minus_qref_rad'}])
        self.assertEqual(summary.triggers([0.,0.],[0.,0.],[0.,0.]),[])

    def test_planned_tail_missing_and_partial_not_scored(self):
        records = [row(180,[0.]*8,[[0.]*8]*10,q=[.1,-.1]+[0.]*6,target=[0.,0.]),
                   row(181,[0.]*8,[[0.]*8]*3,q=[3.,3.]+[0.]*6,target=[0.,0.])]
        value = summary.tracking(records)
        self.assertEqual(value['rmse']['complete_endpoints'],1)
        self.assertAlmostEqual(value['rmse']['joint'],.1)
        self.assertEqual(value['target_segments'][0]['missing_tail_endpoints'],19)
        self.assertIsNone(value['target_segments'][1]['tail']['rmse'])
        self.assertEqual(value['target_segments'][1]['missing_tail_endpoints'],20)

    def test_xml_mapping_native_order_is_not_xml_order(self):
        joints = ''.join('<body><joint name="'+name+'" range="-90 90"/></body>' for name in reversed(summary.JOINTS))
        data = ('<mujoco><worldbody><body><freejoint/>'+joints+'</body></worldbody></mujoco>').encode()
        mapping = summary.xml_mapping(data)
        self.assertEqual(mapping[0]['qpos_index'],14)
        self.assertEqual(mapping[0]['qvel_index'],13)
        self.assertEqual(mapping[-1]['qpos_index'],7)
        self.assertAlmostEqual(mapping[0]['range_rad'][1],math.pi/2)

    def test_comparison_missing_is_failure_not_zero(self):
        c = summary.Checks()
        c.compare({'a':None},{},'missing')
        self.assertEqual(c.failures,['missing/a/present'])
        c.compare(None,None,'null-preserved')
        self.assertEqual(len(c.failures),1)


if __name__ == '__main__':
    unittest.main()
