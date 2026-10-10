from dataclasses import FrozenInstanceError
import json

import numpy as np
import pytest

from developmental_control.joints import FixedBodyModel, JointParameters, JointPlant
from developmental_control.maturation import ActionEnvelope, StagePermission
from developmental_control.planning import CandidatePlanner, PlannerConfig
from developmental_control.validate import ValidationConfig, run_validation


def test_joint_response_has_expected_direction_and_delay():
    params = JointParameters(delay_steps=2)
    plant = JointPlant(params, np.zeros(4))
    for _ in range(2):
        np.testing.assert_array_equal(plant.step([0.2, 0.0]), np.zeros(4))
    observation = plant.step([0.0, 0.0])
    assert observation[0] > 0 and observation[2] > 0
    assert plant.executed_steps == 3
    observation[:] = 42
    assert np.max(plant.observation) < 1  # observations do not mutate the plant


def test_fixture_does_not_hide_state_limit_crossings():
    plant = JointPlant(JointParameters(), [0.4, 0.0, 0.0, 0.0])
    assert plant.step([0.0, 0.0])[0] > 0.35


def test_fixed_model_and_controller_move_toward_target_without_fitting():
    model = FixedBodyModel()
    signature = model.fingerprint()
    plant = JointPlant(JointParameters(), np.zeros(4))
    envelope = ActionEnvelope((1.2, 1.2))
    permission = StagePermission("full", (True, True), (1.0, 1.0))
    planner = CandidatePlanner(model, envelope)
    target, previous = np.array([0.08, -0.06]), np.zeros(2)
    for _ in range(100):
        obs = plant.observation
        plan = planner.plan(obs, target, permission, previous)
        prediction = model.predict(obs, plan.action)
        np.testing.assert_allclose(plant.step(plan.action), prediction)
        assert not plan.fallback
        previous = plan.action
    assert np.linalg.norm(plant.observation[:2] - target) < 0.04
    assert model.fingerprint() == signature
    with pytest.raises(FrozenInstanceError):
        model.dt = 0.1


def test_planning_respects_locked_joint_and_has_explicit_infeasibility():
    model = FixedBodyModel()
    planner = CandidatePlanner(model, ActionEnvelope((1.2, 1.2)))
    permission = StagePermission("one", (True, False), (0.4, 0.4))
    plan = planner.plan(np.zeros(4), [0.08, -0.06], permission, np.zeros(2))
    assert plan.action[0] > 0 and plan.action[1] == 0
    failed = planner.plan([2, 2, 0, 0], [0, 0], permission, np.zeros(2))
    assert failed.fallback and failed.feasible_candidates == 0
    np.testing.assert_array_equal(failed.action, np.zeros(2))


def test_invalid_physics_and_planning_inputs_are_rejected():
    with pytest.raises(ValueError):
        JointParameters(inertia=(0.0, 1.0))
    with pytest.raises(ValueError):
        FixedBodyModel(parameters=JointParameters(delay_steps=1))
    with pytest.raises(ValueError):
        PlannerConfig(candidates_per_joint=4)
    with pytest.raises(ValueError):
        CandidatePlanner(FixedBodyModel(), ActionEnvelope((1.2, 1.2))).plan(
            [np.nan, 0, 0, 0], [0, 0], StagePermission("full", (True, True), (1, 1)), [0, 0]
        )


def test_validation_reports_zero_updates_and_counts_both_phases():
    config = ValidationConfig(seeds=(0,), rollout_steps=3, evaluation_steps=3,
                              window_steps=1, fixed_stage_steps=1)
    report, trace, _ = run_validation(config)
    assert report["model_parameter_updates"] == report["policy_parameter_updates"] == 0
    assert report["model_fingerprint_before"] == report["model_fingerprint_after"]
    assert report["fixed_parameters_before"] == report["fixed_parameters_after"]
    assert report["total_executed_steps"] == len(trace) == 90
    assert report["common_evaluation_same_planner_identical"]
    assert any(r["scenario"] == "unmodeled_delay" for r in report["records"])
    with pytest.raises(ValueError):
        ValidationConfig(seeds=(0, 0))


def test_nonfinite_simulation_failure_is_reported_without_dropping_runs(monkeypatch):
    original_step = JointPlant.step

    def broken_step(self, command, external_torque=None):
        original_step(self, command, external_torque)
        return np.full(4, np.nan)

    monkeypatch.setattr(JointPlant, "step", broken_step)
    config = ValidationConfig(seeds=(0,), rollout_steps=3, evaluation_steps=3,
                              window_steps=1, fixed_stage_steps=1)
    report, trace, _ = run_validation(config)
    assert len(report["records"]) == 15
    assert report["total_executed_steps"] == len(trace) == 30
    for record in report["records"]:
        for phase in ("mechanism", "common_evaluation"):
            assert record[phase]["termination_reason"] == "nonfinite_state"
            assert record[phase]["tracking_rmse"] is None
    json.dumps(report, allow_nan=False)
