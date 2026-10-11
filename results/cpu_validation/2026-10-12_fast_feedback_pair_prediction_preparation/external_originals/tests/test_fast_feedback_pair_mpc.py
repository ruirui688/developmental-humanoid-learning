"""Two new Z planning fixtures; fake predictors never call body-model math."""
import numpy as np
import pytest

from developmental_physics.fast_feedback_pair_mpc import FastFeedbackResidualPDPairMPC
from developmental_physics.local_model import MPCConfig
from developmental_physics.local_pair_model import PairBodyModel


class AdvancingFakePredictor(PairBodyModel):
    """Only the public type/qref/dt contract and a synthetic state progression."""
    def __init__(self):
        self._qref = (0., 0.)
        self._dt = .002
        self.calls = []

    def predict(self, q, v, u):
        self.calls.append((tuple(q), tuple(v), tuple(u)))
        return (q[0] + 1e-5, q[1] - 1e-5), (0., 0.)


class OutOfBoundsFakePredictor(PairBodyModel):
    """Successful fake return that immediately makes each candidate infeasible."""
    def __init__(self):
        self._qref = (0., 0.)
        self._dt = .002
        self.calls = []

    def predict(self, q, v, u):
        self.calls.append((tuple(q), tuple(v), tuple(u)))
        return (.2, 0.), (0., 0.)


def test_new_micro_rollout_holds_nonzero_residual_then_recomputes_pd_with_scaled_cost():
    model = AdvancingFakePredictor()
    controller = FastFeedbackResidualPDPairMPC(model, ((-2., 2.), (-2., 2.)))
    # One synthetic candidate isolates timing/cost; formal source still uses 81.
    residual = (.125, -.125)
    controller._candidates = (residual,)
    previous = (.05, -.025)
    decision = controller.select((0., 0.), (0., 0.), (0., 0.), previous_torque=previous)

    assert decision.fallback is False
    assert decision.selected_residual_nm == residual
    assert decision.feasible_candidates == 1
    assert len(model.calls) == len(decision.predicted_q) == len(decision.trajectory_requested_torque) == 150
    assert len(model.calls) * model.dt == pytest.approx(.3)
    assert controller.config.horizon == 150
    assert decision.pair_prediction_attempts == decision.pair_prediction_successes == 150
    assert decision.scalar_prediction_attempts == decision.scalar_prediction_successes == 300
    assert decision.pd_request_attempts == decision.pd_request_returns == 150
    assert decision.residual_candidate_attempts == 1

    expected_requests = []
    for stage in range(150):
        # The fake q advances independently of u; expected feedback uses its
        # current predicted q, including stage 9 versus the stage 10 boundary.
        offset = residual if stage < 10 else (0., 0.)
        request = (-64. * stage * 1e-5 + offset[0],
                   64. * stage * 1e-5 + offset[1])
        expected_requests.append(request)
        np.testing.assert_allclose(model.calls[stage][0], (stage * 1e-5, -stage * 1e-5), atol=1e-15)
        np.testing.assert_allclose(model.calls[stage][2], request, atol=1e-15)
    np.testing.assert_allclose(decision.trajectory_requested_torque, expected_requests, atol=1e-15)
    np.testing.assert_allclose(decision.torque, expected_requests[0], atol=1e-15)

    macro = MPCConfig()
    assert controller.config.position_weight == pytest.approx(.1 * macro.position_weight)
    assert controller.config.velocity_weight == pytest.approx(.1 * macro.velocity_weight)
    assert controller.config.effort_weight == pytest.approx(.1 * macro.effort_weight)
    assert controller.config.change_weight == macro.change_weight
    position_cost = sum(2. * ((stage + 1) * 1e-5) ** 2 for stage in range(150))
    request_cost = sum(u0 * u0 + u1 * u1 for u0, u1 in expected_requests)
    first_change = sum((expected_requests[0][i] - previous[i]) ** 2 for i in range(2))
    expected_cost = (.1 * (macro.position_weight * position_cost + macro.effort_weight * request_cost)
                     + macro.change_weight * first_change)
    assert decision.cost == pytest.approx(expected_cost)
    assert decision.candidate_records[0].cost == pytest.approx(expected_cost)


def test_new_infeasible_micro_rollouts_return_literal_zero_fallback():
    model = OutOfBoundsFakePredictor()
    controller = FastFeedbackResidualPDPairMPC(model, ((-2., 2.), (-2., 2.)))
    decision = controller.select((0., 0.), (0., 0.), (.04, .04), previous_torque=(.1, -.1))

    assert decision.fallback is True
    assert decision.torque == (0., 0.)
    assert decision.selected_residual_nm is None
    assert decision.cost is None
    assert decision.predicted_q == decision.predicted_v == decision.trajectory_requested_torque == ()
    assert decision.feasible_candidates == 0
    assert len(model.calls) == len(decision.candidate_records) == 81
    assert decision.pair_prediction_attempts == decision.pair_prediction_successes == 81
    assert decision.scalar_prediction_attempts == decision.scalar_prediction_successes == 162
    assert decision.pd_request_attempts == decision.pd_request_returns == 1
    assert decision.residual_candidate_attempts == 81
    assert all(not record.feasible and record.rejection_reason == "forecast_position_bounds"
               and record.completed_prediction_steps == 0 for record in decision.candidate_records)
