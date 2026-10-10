from dataclasses import FrozenInstanceError, asdict
from itertools import product

import numpy as np
import pytest

from developmental_control.history_planning import HistoryCandidatePlanner, HistoryPlannerConfig
from developmental_control.joints import FixedBodyModel, JointParameters
from developmental_control.maturation import ActionEnvelope, StagePermission
from developmental_control.planning import CandidatePlanner, PlannerConfig


FULL = StagePermission("full", (True, True), (0.6, 0.6))
ENVELOPE = ActionEnvelope((1.2, 1.2))


class RecordingModel:
    def __init__(self, model=FixedBodyModel()):
        self.model = model
        self.calls = []

    def predict(self, states, actions):
        result = self.model.predict(states, actions)
        self.calls.append((states.copy(), actions.copy(), result.copy()))
        return result


def manual_step(state, applied, model):
    """Independent scalar Euler calculation, rather than calling advance."""
    p, dt = model.parameters, model.dt
    q, v = state[:2].copy(), state[2:].copy()
    next_v = np.empty(2)
    for j in range(2):
        acceleration = (p.actuator_gain[j] * applied[j] - p.damping[j] * v[j]
                        - p.stiffness[j] * q[j] - p.coupling * (q[j] - q[1-j])) / p.inertia[j]
        next_v[j] = v[j] + dt * acceleration
    return np.concatenate((q + dt * next_v, next_v))


def test_history_rollout_uses_exact_indices_and_hand_calculated_dynamics():
    model = RecordingModel()
    config = PlannerConfig(horizon_steps=5, candidates_per_joint=3)
    planner = HistoryCandidatePlanner(model, ENVELOPE, config, HistoryPlannerConfig(3))
    history = np.array([[0.8, -0.7], [0.4, 0.1]])
    observation = np.array([0.03, -0.04, 0.02, -0.01])
    target, previous = np.array([0.06, -0.02]), np.array([0.2, -0.1])
    result = planner.plan(observation, target, FULL, previous, history)
    candidates = np.array(list(product([-0.6, 0.0, 0.6], repeat=2)))
    costs = config.change_weight * np.sum((candidates - previous) ** 2, axis=1)
    for index, candidate in enumerate(candidates):
        state = observation.copy()
        for offset, applied in enumerate((np.zeros(2), history[0], history[1], candidate, candidate)):
            np.testing.assert_array_equal(model.calls[offset][1][index], applied)
            state = manual_step(state, applied, model.model)
            np.testing.assert_allclose(model.calls[offset][2][index], state, rtol=0, atol=1e-16)
            costs[index] += (config.position_weight * np.sum((state[:2] - target) ** 2)
                             + config.velocity_weight * np.sum(state[2:] ** 2)
                             + config.effort_weight * np.sum(candidate ** 2))
    np.testing.assert_array_equal(result.action, candidates[np.argmin(costs)])
    assert result.feasible_candidates == 9 and not result.fallback


@pytest.mark.parametrize("assumed_delay,use_history", [(0, True), (0, False), (8, False)])
@pytest.mark.parametrize("state,permission", [
    ([0, 0, 0, 0], FULL),
    ([0.25, -0.24, 0.05, 0.03], FULL),
    ([0.1, -0.02, 0.1, 0], StagePermission("one", (True, False), (0.3, 0.2))),
    ([2, 2, 0, 0], FULL),
])
def test_effective_zero_delay_is_exactly_original_planner(assumed_delay, use_history, state, permission):
    model = FixedBodyModel()
    config = PlannerConfig(horizon_steps=8, candidates_per_joint=3)
    old = CandidatePlanner(model, ENVELOPE, config)
    new = HistoryCandidatePlanner(model, ENVELOPE, config,
                                  HistoryPlannerConfig(assumed_delay, use_history))
    target, previous = [0.08, -0.06], [0.2, -0.1]
    expected = old.plan(state, target, permission, previous)
    actual = new.plan(state, target, permission, previous, [[0.7, -0.9]])
    np.testing.assert_array_equal(actual.action, expected.action)
    assert actual.feasible_candidates == expected.feasible_candidates
    assert actual.fallback == expected.fallback
    np.testing.assert_array_equal(new.assumed_applied_action([0.2, -0.1], [[0.7, -0.9]]), previous)


@pytest.mark.parametrize("horizon", [1, 3])
def test_horizon_at_or_below_delay_has_no_candidate_dynamics_effect(horizon):
    model = RecordingModel()
    planner = HistoryCandidatePlanner(model, ENVELOPE,
                                      PlannerConfig(horizon_steps=horizon, candidates_per_joint=3),
                                      HistoryPlannerConfig(3))
    history = [[0.2, -0.2], [0.1, -0.1], [0.0, 0.0]]
    first = planner.plan(np.zeros(4), [0.2, -0.2], FULL, [0, 0], history)
    second = planner.plan(np.zeros(4), [-0.2, 0.2], FULL, [0, 0], history)
    np.testing.assert_array_equal(first.action, [0, 0])
    np.testing.assert_array_equal(second.action, first.action)
    for _, _, states in model.calls:
        np.testing.assert_array_equal(states, np.broadcast_to(states[0], states.shape))
    assert first.feasible_candidates == second.feasible_candidates == 9


def test_historical_high_permission_actions_are_not_reclamped_and_inputs_stay_unchanged():
    model = RecordingModel()
    planner = HistoryCandidatePlanner(model, ENVELOPE,
                                      PlannerConfig(horizon_steps=2, candidates_per_joint=3),
                                      HistoryPlannerConfig(1))
    permission = StagePermission("withdrawn", (True, False), (0.1, 0.1))
    history = np.array([[0.9, -0.8]])
    original = history.copy()
    result = planner.plan(np.zeros(4), [0.1, -0.1], permission, [0.9, -0.8], history)
    np.testing.assert_array_equal(model.calls[0][1], np.broadcast_to(history[0], (3, 2)))
    assert abs(result.action[0]) <= 0.1 and result.action[1] == 0
    helper_action = planner.assumed_applied_action(result.action, history)
    np.testing.assert_array_equal(helper_action, [0.9, -0.8])
    helper_action[:] = 42
    np.testing.assert_array_equal(history, original)


def test_every_intermediate_state_is_checked_and_fallback_cannot_cancel_history():
    model = FixedBodyModel(JointParameters(inertia=(1., 1.), damping=(0.1, 0.1),
                                          stiffness=(2., 2.), coupling=0.), dt=1.)
    permission = StagePermission("locked", (False, False), (0., 0.))
    config = PlannerConfig(horizon_steps=2, candidates_per_joint=3, position_limit=0.95, speed_limit=2.)
    planner = HistoryCandidatePlanner(model, ENVELOPE, config, HistoryPlannerConfig(1))
    first = manual_step(np.zeros(4), np.array([1., 0.]), model)
    final = manual_step(first, np.zeros(2), model)
    assert first[0] > config.position_limit and final[0] < config.position_limit
    result = planner.plan(np.zeros(4), [0, 0], permission, [1, 0], [[1, 0]])
    assert result.fallback and result.feasible_candidates == 0
    np.testing.assert_array_equal(result.action, [0, 0])
    np.testing.assert_array_equal(planner.assumed_applied_action(result.action, [[1, 0]]), [1, 0])


@pytest.mark.parametrize("delay,history,expected", [
    (0, [], [0.3, -0.2]),
    (1, [], [0., 0.]),
    (3, [[0.8, -0.7], [0.4, 0.1]], [0., 0.]),
    (2, [[0.8, -0.7], [0.4, 0.1]], [0.8, -0.7]),
    (1, [[0.8, -0.7], [0.4, 0.1]], [0.4, 0.1]),
])
def test_assumed_next_action_history_indices(delay, history, expected):
    planner = HistoryCandidatePlanner(FixedBodyModel(), ENVELOPE,
                                      history_config=HistoryPlannerConfig(delay))
    np.testing.assert_array_equal(planner.assumed_applied_action([0.3, -0.2], history), expected)


@pytest.mark.parametrize("delay", [-1, 1.0, True, np.int64(1), "1", None])
def test_invalid_delay_types_and_values_are_rejected(delay):
    with pytest.raises(ValueError):
        HistoryPlannerConfig(delay)


@pytest.mark.parametrize("use_history", [0, 1, "true", None, np.bool_(True)])
def test_history_flag_requires_boolean(use_history):
    with pytest.raises(ValueError):
        HistoryPlannerConfig(use_history=use_history)


@pytest.mark.parametrize("history", [
    [0.1, 0.2], [[0.1]], np.zeros((0, 4)), np.zeros((2, 2, 1)),
    [[np.nan, 0]], [[np.inf, 0]], [[0j, 1j]], [["1", "2"]],
    [[True, False]], [[0, 0], [0]], None,
])
def test_invalid_history_is_rejected_even_in_immediate_ablation(history):
    planner = HistoryCandidatePlanner(FixedBodyModel(), ENVELOPE,
                                      history_config=HistoryPlannerConfig(5, False))
    with pytest.raises(ValueError):
        planner.plan(np.zeros(4), [0, 0], FULL, [0, 0], history)
    with pytest.raises(ValueError):
        planner.assumed_applied_action([0, 0], history)


@pytest.mark.parametrize("field,value", [
    ("observation", [0, 0, 0]), ("observation", [np.nan, 0, 0, 0]),
    ("target", [0]), ("target", [np.inf, 0]),
    ("previous_action", [[0, 0]]), ("previous_action", [0, np.nan]),
])
def test_invalid_planning_vectors_are_rejected(field, value):
    planner = HistoryCandidatePlanner(FixedBodyModel(), ENVELOPE)
    values = dict(observation=np.zeros(4), target=[0, 0], previous_action=[0, 0])
    values[field] = value
    with pytest.raises(ValueError):
        planner.plan(**values, permission=FULL, command_history=[])


@pytest.mark.parametrize("command", [[0], [[0, 0]], [np.nan, 0], [np.inf, 0], [1j, 0], [True, False]])
def test_invalid_single_step_command_is_rejected(command):
    planner = HistoryCandidatePlanner(FixedBodyModel(), ENVELOPE)
    with pytest.raises(ValueError):
        planner.assumed_applied_action(command, [])


def test_parameters_remain_frozen_across_planning_and_helper_calls():
    model, config, history_config = FixedBodyModel(), PlannerConfig(horizon_steps=3), HistoryPlannerConfig(2)
    planner = HistoryCandidatePlanner(model, ENVELOPE, config, history_config)
    before = model.fingerprint(), asdict(config), asdict(history_config)
    planner.plan(np.zeros(4), [0.08, -0.06], FULL, [0, 0], [[0.3, -0.2]])
    planner.assumed_applied_action([0.1, -0.1], [[0.3, -0.2]])
    assert before == (model.fingerprint(), asdict(config), asdict(history_config))
    for instance, field, value in ((model, "dt", 0.1), (config, "horizon_steps", 4),
                                    (history_config, "assumed_delay_steps", 3),
                                    (history_config, "use_history", False)):
        with pytest.raises(FrozenInstanceError):
            setattr(instance, field, value)
    with pytest.raises(ValueError):
        HistoryCandidatePlanner(model, ENVELOPE, config, history_config={})
