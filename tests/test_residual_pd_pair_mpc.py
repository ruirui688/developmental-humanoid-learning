"""New residual/PD rollout contract only; no physics or old RLS revalidation."""
from dataclasses import replace

import pytest

from developmental_physics.local_model import MPCConfig
from developmental_physics.local_pair_model import PairBodyModel, PairPredictionError
from developmental_physics.residual_pd_pair_mpc import ResidualPDPairMPC, public_pd_request


class LoggedModel(PairBodyModel):
    def __init__(self, fail=None):
        super().__init__((0., .1), structure="coupled_hinge9", trainable=False)
        self.calls = []
        self.fail = fail

    def predict(self, q, v, u):
        self.calls.append((tuple(q), tuple(v), tuple(u)))
        if self.fail is not None:
            raise self.fail
        next_v = tuple(.02*x for x in u)
        return tuple(q[i]+.02*next_v[i] for i in range(2)), next_v


def planner(model, horizon=2):
    return ResidualPDPairMPC(model, ((-1., 1.), (0., 2.)), replace(MPCConfig(), horizon=horizon))


def test_residual_authority_and_candidate_specific_pd_tail():
    model = LoggedModel()
    decision = planner(model).select((0., .1), (0., 0.), (.001, .101))
    assert len(decision.candidate_records) == 81
    assert len(model.calls) == 162
    assert decision.pd_request_attempts == decision.pd_request_returns == 82
    assert decision.residual_candidate_attempts == 81
    for i in range(81):
        first, tail = model.calls[2*i:2*i+2]
        assert max(abs(x) for x in first[2]) <= .5
        assert tail[2] == public_pd_request(tail[0], tail[1], (.001, .101))
        assert tail[0] == pytest.approx(tuple(first[0][j]+.0004*first[2][j] for j in range(2)), rel=0., abs=1e-18)
    assert model.calls[80][2] == public_pd_request((0., .1), (0., 0.), (.001, .101))
    assert model.calls[1][0] != model.calls[-1][0]


def test_cost_charges_complete_request_and_actual_first_change():
    model = LoggedModel()
    controller = planner(model)
    decision = controller.select((0., .1), (0., 0.), (.04, .14), previous_torque=(.1, -.1))
    cfg = controller.config
    manual = sum(cfg.change_weight*(decision.torque[i]-(.1, -.1)[i])**2 for i in range(2))
    for q, v, u in zip(decision.predicted_q, decision.predicted_v, decision.trajectory_requested_torque):
        manual += sum(cfg.position_weight*(q[i]-(.04, .14)[i])**2
                      +cfg.velocity_weight*v[i]**2+cfg.effort_weight*u[i]**2 for i in range(2))
    assert decision.cost == pytest.approx(manual)
    assert any(abs(x) > .125 for x in decision.torque)
    assert max(abs(x) for row in decision.trajectory_requested_torque for x in row) <= .5


def test_failed_head_is_paid_and_falls_back_without_physics():
    decision = planner(LoggedModel(PairPredictionError(ValueError("head2"), 2, 1, "velocity"))).select(
        (0., .1), (0., 0.), (.04, .14))
    assert decision.fallback and decision.torque == (0., 0.)
    assert decision.pair_prediction_attempts == 81 and decision.pair_prediction_successes == 0
    assert decision.scalar_prediction_attempts == 162 and decision.scalar_prediction_successes == 81
    assert decision.scalar_counts_complete


def test_interrupt_exposes_paid_lower_bound_and_preserves_exception():
    error = OSError("fixture interruption")
    with pytest.raises(OSError) as caught:
        planner(LoggedModel(error)).select((0., .1), (0., 0.), (.04, .14))
    assert caught.value is error
    cost = error.pair_planning_accounting
    assert cost["pair_prediction_attempts"] == 1 and cost["pair_prediction_successes"] == 0
    assert cost["scalar_counts_is_lower_bound"] and cost["unknown_scalar_failure_count"] == 1
    assert cost["pd_request_attempts"] == cost["pd_request_returns"] == 1
    assert cost["residual_candidate_attempts"] == 1


def test_pd_failure_is_paid_before_any_model_or_candidate(monkeypatch):
    import developmental_physics.residual_pd_pair_mpc as module
    error = OSError("public PD failure")

    def fail(*args):
        raise error

    model = LoggedModel()
    monkeypatch.setattr(module, "public_pd_request", fail)
    with pytest.raises(OSError) as caught:
        planner(model).select((0., .1), (0., 0.), (.04, .14))
    assert caught.value is error and model.calls == []
    cost = error.pair_planning_accounting
    assert cost["pair_prediction_attempts"] == cost["residual_candidate_attempts"] == 0
    assert cost["pd_request_attempts"] == 1 and cost["pd_request_returns"] == 0
