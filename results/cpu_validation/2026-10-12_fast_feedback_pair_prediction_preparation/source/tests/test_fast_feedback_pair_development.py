"""New micro capture and physical-time gates only; no model fit or physics."""
from collections import Counter
from copy import deepcopy
from types import SimpleNamespace

import numpy as np

from developmental_physics.fast_feedback_pair_development import (
    HORIZONS, SEEDS, collect_trial, prediction_gate, pulse,
)


class OneMicroEnv:
    def __init__(self):
        self.physics_steps = self.step_id = 0
        self._joint_ids = np.arange(8)
        self.model = SimpleNamespace(jnt_range=np.repeat([[-2., 2.]], 8, axis=0))
        self.engineering_operations = {"model_builds": 0, "reset_forward_attempts": 0, "reset_forward_returns": 0}
        self._installed_xml = b"<synthetic-one-micro-fixture/>"

    def observation(self, boundary=False):
        return {"joint_position": [.1, .12, 0., 0., 0., 0., 0., 0.],
            "joint_velocity": [0., 1. if boundary else 0., 0., 0., 0., 0., 0., 0.],
            "imu_gyro": [0.]*3, "imu_acceleration": [0.]*3,
            "actuator_torque": [0.]*8, "previous_command": [0.]*8}

    def reset(self, seed, pose):
        assert seed == 7701 and pose == "upright"
        return self.observation()

    def support_configuration(self):
        return {"domain": "synthetic-new-micro-fixture"}

    def physical_configuration_fingerprint(self):
        return "synthetic-physical"

    def parameter_fingerprint(self):
        return "synthetic-execution"

    def interface_fingerprint(self):
        return "synthetic-interface"

    def action_interface_configuration(self):
        return {"active_control_dt_s": .002, "requested_control_substeps": 1}

    def step(self, request):
        boundary = self.step_id == 1000
        self.physics_steps += 1
        self.step_id += 1
        observation = self.observation(boundary)
        sample = {"physics_step": self.physics_steps, "time": .002*self.physics_steps,
            "observation": observation, "applied_command8": list(request),
            "actual_actuator_torque8": list(request), "floor_contacts": []}
        return SimpleNamespace(observation=observation, terminated=False, reason=None,
            diagnostics={"executed_substeps": 1, "substep_native_and_contact_records": [sample]})


def test_new_macro_pulses_keep_twenty_ms_slots_under_micro_feedback():
    assert [pulse(i, "calibration") for i in range(10)] == [(.125, 0.)]*10
    assert [pulse(i, "calibration") for i in range(100, 110)] == [(-.125, 0.)]*10
    assert pulse(10, "calibration") == pulse(99, "calibration") == (0., 0.)
    assert pulse(0, "prediction") == (0., 0.)
    assert [pulse(i, "prediction") for i in range(10, 20)] == [(.125, 0.)]*10
    assert [pulse(i, "prediction") for i in range(90, 100)] == [(-.125, 0.)]*10


def test_new_one_micro_paid_endpoint_precedes_study_stop_and_update():
    cost, trace, journal, trial, updates = Counter(), [], [], {}, []
    collect_trial(trial, trace, cost, seed=7701, active_steps=4000, kind="calibration",
                  env_factory=OneMicroEnv, after_transition=updates.append,
                  paid_writer=lambda row: journal.append(deepcopy(row)))
    assert len(trace) == len(journal) == 1001
    assert cost["control_call_returns"] == cost["confirmed_physics_substeps"] == 1001
    assert trace[-1]["diagnostics"]["executed_substeps"] == 1
    assert journal[-1]["study_abort"] is None and trace[-1]["study_abort"] is not None
    assert trial["stop"]["primary_reason"] == "StudyAbort" and trial["complete"] is False
    assert updates == []


def test_new_physical_time_gates_do_not_add_native_h1_veto():
    scores = []
    for seed in SEEDS:
        horizons = {}
        for horizon in HORIZONS:
            cold = {"available": True, "q_rmse_axis_rad": [1., 1.], "v_rmse_axis_rad_s": [1., 1.]}
            learned = deepcopy(cold)
            if horizon == 1:
                learned.update(available=False, q_rmse_axis_rad=None, v_rmse_axis_rad_s=None)
            elif horizon == 10:
                learned.update(q_rmse_axis_rad=[10., 10.], v_rmse_axis_rad_s=[.5, .5])
            elif horizon == 150:
                learned["q_rmse_axis_rad"] = [.5, .5]
            horizons[str(horizon)] = {"models": {"cold": cold, "learned": learned}}
        scores.append({"seed": seed, "prediction_scores": {"horizons": horizons}})
    assert prediction_gate(scores)["z1_prediction_gate_passed"] is True
    scores[0]["prediction_scores"]["horizons"]["20"]["models"]["learned"]["available"] = False
    assert prediction_gate(scores)["z1_prediction_gate_passed"] is False
