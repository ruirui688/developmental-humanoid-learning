"""Learning/evaluation boundaries and CPU-only local mathematical control."""

from dataclasses import FrozenInstanceError
import json

import numpy as np
import pytest

from developmental_physics.local_model import FixedLocalMPC, LocalBodyModel, MPCConfig


def test_initial_prior_and_pure_prediction_are_disclosed():
    model = LocalBodyModel(.3)
    before = model.snapshot()
    assert model.predict(.32, .1, .25) == pytest.approx((.3221, .105))
    assert np.array_equal(model.coefficients, [1., 0., .02, 0.])
    assert np.array_equal(model.covariance, np.eye(4) * 100.)
    assert model.snapshot() == before
    assert before["forgetting_factor"] == 1.
    assert before["dtype"] == "float64"
    assert "not identified" in before["initial_prior"]
    json.dumps(before, allow_nan=False)


def test_excited_synthetic_arx_data_improves_unseen_prediction():
    rng = np.random.default_rng(25)
    model = LocalBodyModel(.2)
    truth = np.asarray([.9, -.3, .08, .001])
    test_features = np.column_stack((rng.uniform(-.2, .2, 200),
                                    rng.uniform(-.1, .1, 200),
                                    rng.uniform(-.5, .5, 200), np.ones(200)))
    before = np.mean((test_features @ model.coefficients - test_features @ truth) ** 2)
    for _ in range(1500):
        v, relative_q, torque = rng.uniform([-.2, -.1, -.5], [.2, .1, .5])
        next_v = np.asarray([v, relative_q, torque, 1.]) @ truth
        model.update(.2 + relative_q, v, torque, float(next_v))
    after = np.mean((test_features @ model.coefficients - test_features @ truth) ** 2)
    assert after < before * 1e-4
    assert np.max(np.abs(model.coefficients - truth)) < .002
    assert model.update_count == 1500
    assert np.allclose(model.covariance, model.covariance.T)
    assert np.min(np.linalg.eigvalsh(model.covariance)) > 0


def test_update_records_preupdate_prediction_not_refitted_prediction():
    model = LocalBodyModel(0.)
    before = model.parameter_fingerprint()
    prediction = model.predict(.1, .2, .5)
    record = model.update(.1, .2, .5, .12)
    assert record["preupdate_prediction"] == {
        "next_q_rad": prediction[0], "next_v_rad_s": prediction[1],
    }
    assert record["preupdate_error_rad_s"] == pytest.approx(.12 - prediction[1])
    assert record["parameter_fingerprint_before"] == before
    assert record["parameter_fingerprint_after"] == model.parameter_fingerprint() != before
    assert record["update_count"] == 1 and record["updated"]
    assert model.predict(.1, .2, .5) != prediction


def test_prefix_prediction_does_not_claim_an_update_or_change_parameters():
    model = LocalBodyModel(0.)
    before = model.snapshot()
    for _ in range(100):
        record = model.update(.1, .2, 0., .1, phase="prefix")
        assert not record["updated"] and record["update_count"] == 0
        assert record["parameter_fingerprint_before"] == record["parameter_fingerprint_after"]
    assert model.snapshot() == before


def test_frozen_clone_preserves_parameters_and_cannot_update():
    trained = LocalBodyModel(.1)
    trained.update(.12, .2, .5, .1)
    frozen = trained.clone_frozen()
    assert frozen.parameter_fingerprint() == trained.parameter_fingerprint()
    assert np.array_equal(frozen.coefficients, trained.coefficients)
    assert np.array_equal(frozen.covariance, trained.covariance)
    assert frozen.update_count == trained.update_count == 1
    before = frozen.snapshot()
    frozen.predict(.1, .2, .5)
    with pytest.raises(RuntimeError, match="cannot update"):
        frozen.update(.1, .2, .5, .1)
    assert frozen.snapshot() == before
    trained.update(.13, .1, -.5, -.2)
    assert frozen.snapshot() == before


def test_snapshot_and_parameter_access_are_independent_copies():
    model = LocalBodyModel(0.)
    before = model.snapshot()
    model.coefficients[:] = 100
    model.covariance[:] = 0
    snapshot = model.snapshot()
    snapshot["coefficients"][0] = 100
    snapshot["covariance"][0][0] = 0
    assert model.snapshot() == before


def test_frozen_permission_reference_and_update_count_are_read_only():
    model = LocalBodyModel(0., trainable=False)
    for name, value in (("trainable", True), ("qref", .1), ("dt", .1), ("update_count", 100)):
        with pytest.raises(AttributeError):
            setattr(model, name, value)
    assert not model.trainable and model.update_count == 0


@pytest.mark.parametrize("key", ["q", "v", "torque", "next_v"])
@pytest.mark.parametrize("invalid", [np.nan, np.inf, -np.inf, True, "1"])
def test_nonfinite_or_non_numeric_update_is_atomic(key, invalid):
    model = LocalBodyModel(0.)
    before = model.snapshot()
    sample = {"q": .1, "v": .2, "torque": .3, "next_v": .4}
    sample[key] = invalid
    with pytest.raises(ValueError):
        model.update(**sample)
    assert model.snapshot() == before


def test_finite_but_overflowing_sample_is_rejected_atomically():
    model = LocalBodyModel(0.)
    before = model.snapshot()
    with pytest.raises(ValueError):
        model.update(1e308, 0., 0., 0.)
    assert model.snapshot() == before


@pytest.mark.parametrize("kwargs", [{"qref": np.nan}, {"qref": True},
                                   {"qref": 0., "dt": 0}, {"qref": 0., "dt": np.inf},
                                   {"qref": 0., "trainable": "false"}])
def test_invalid_model_initialization_rejected(kwargs):
    with pytest.raises(ValueError):
        LocalBodyModel(**kwargs)


def test_mpc_uses_only_fixed_grid_mathematical_predictions_without_mutation(monkeypatch):
    model = LocalBodyModel(0., trainable=False)
    controller = FixedLocalMPC(model, [-1., 1.])
    before = model.snapshot()
    controller_before = controller.parameter_fingerprint()
    predictions = []
    original = model.predict

    def predict(q, v, torque):
        predictions.append(torque)
        return original(q, v, torque)

    def forbidden(*args, **kwargs):
        raise AssertionError("MPC attempted learning")

    monkeypatch.setattr(model, "predict", predict)
    monkeypatch.setattr(model, "update", forbidden)
    decision = controller.select(0., 0., .05)
    assert not decision.fallback and decision.feasible_candidates == 9
    assert decision.torque > 0 and decision.torque <= .5
    assert decision.torque in controller.spec()["candidates_nm"]
    assert len(predictions) == decision.mathematical_prediction_calls == 9 * 15
    assert set(predictions) == set(np.linspace(-.5, .5, 9))
    assert len(decision.predicted_q) == len(decision.predicted_v) == 15
    assert model.snapshot() == before
    assert controller.parameter_fingerprint() == controller_before
    json.dumps(decision.to_dict(), allow_nan=False)


def test_mpc_forecast_tolerance_allows_soft_limit_start_but_target_stays_inside():
    model = LocalBodyModel(-.01, trainable=False)
    controller = FixedLocalMPC(model, [0., 1.])
    assert controller.forecast_bounds[0] == -.03
    assert controller.target_bounds[0] == .03
    decision = controller.select(-.01, 0., .04)
    assert not decision.fallback and decision.torque > 0
    assert all(-.03 <= q <= .14 for q in decision.predicted_q)
    with pytest.raises(ValueError, match="target"):
        controller.select(-.01, 0., -.01)


def test_mpc_rejects_candidates_that_leave_predicted_limits():
    model = LocalBodyModel(0., trainable=False)
    controller = FixedLocalMPC(model, [-.1, .1])
    decision = controller.select(.129, 0., .02)
    assert not decision.fallback
    assert 0 < decision.feasible_candidates < 9
    assert decision.torque <= 0
    assert all(-.13 <= q <= .13 for q in decision.predicted_q)
    assert all(abs(v) <= 1.5 for v in decision.predicted_v)


def test_no_feasible_velocity_candidate_returns_zero_without_safety_claim():
    controller = FixedLocalMPC(LocalBodyModel(0., trainable=False), [-1., 1.])
    decision = controller.select(0., 2., 0.)
    assert decision.fallback and decision.feasible_candidates == 0
    assert decision.torque == 0 and decision.cost is None
    assert decision.predicted_q == decision.predicted_v == ()


def test_mpc_config_is_frozen_and_zero_target_prefers_zero_effort():
    config = MPCConfig()
    with pytest.raises(FrozenInstanceError):
        config.horizon = 50
    controller = FixedLocalMPC(LocalBodyModel(0.), [-1., 1.], config)
    assert controller.select(0., 0., 0.).torque == 0


@pytest.mark.parametrize("kwargs", [
    {"horizon": 0}, {"horizon": True}, {"candidate_count": 8},
    {"candidate_count": 1}, {"torque_limit_nm": .51}, {"torque_limit_nm": 0},
    {"position_weight": -1}, {"velocity_weight": np.nan}, {"effort_weight": True},
    {"prediction_limit_tolerance_rad": .08}, {"prediction_limit_tolerance_rad": -1},
    {"local_position_radius_rad": 0}, {"target_limit_margin_rad": 0},
    {"velocity_limit_rad_s": np.inf},
])
def test_invalid_mpc_config_rejected(kwargs):
    with pytest.raises(ValueError):
        MPCConfig(**kwargs)


@pytest.mark.parametrize("joint_range", [[], [0, 0], [1, -1], [np.nan, 1], [0, np.inf]])
def test_invalid_public_limits_rejected(joint_range):
    with pytest.raises(ValueError):
        FixedLocalMPC(LocalBodyModel(0.), joint_range)


@pytest.mark.parametrize("kwargs", [{"q": np.nan}, {"v": np.inf},
                                   {"target_q": .2}, {"previous_torque": .6}])
def test_invalid_mpc_state_target_or_previous_permission_rejected(kwargs):
    controller = FixedLocalMPC(LocalBodyModel(0.), [-1., 1.])
    call = {"q": 0., "v": 0., "target_q": .05, **kwargs}
    with pytest.raises(ValueError):
        controller.select(**call)
