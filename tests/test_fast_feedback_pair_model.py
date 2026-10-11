"""Only new time-adapter initialization/clone metadata; no predict or RLS."""
import numpy as np
import pytest

from developmental_physics.fast_feedback_pair_model import FastFeedbackGuardCoupledPairBodyModel


def test_new_micro_prior_preserves_velocity_identity_and_scales_increment():
    model = FastFeedbackGuardCoupledPairBodyModel((0., .12), public_joint_ranges=((-2., 2.), (-2., 2.)))
    snapshot = model.snapshot()
    expected = np.zeros((2, 9))
    expected[0, 0] = expected[1, 1] = 1.
    expected[0, 4] = expected[1, 5] = .002
    np.testing.assert_allclose(model.coefficients, expected, rtol=0., atol=1e-18)
    assert model.dt == .002 and model.update_count == 0
    assert snapshot["time_adaptation"]["reference_constructor_dt_seconds"] == .02
    assert snapshot["time_adaptation"]["active_dt_seconds"] == .002
    assert snapshot["forgetting_factor"] == 1. and snapshot["initial_covariance_scale"] == 100.
    clone = model.clone_frozen()
    assert clone.trainable is False and clone.dt == .002 and clone.update_count == 0
    assert clone.parameter_fingerprint() == model.parameter_fingerprint()
    assert clone.snapshot()["time_adaptation"] == snapshot["time_adaptation"]


def test_new_adapter_rejects_macro_dt_before_original_constructor(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("reference constructor must not run after invalid new dt")
    monkeypatch.setattr(FastFeedbackGuardCoupledPairBodyModel.__bases__[0], "__init__", forbidden)
    with pytest.raises(ValueError, match="complete_interval_at_2ms"):
        FastFeedbackGuardCoupledPairBodyModel((0., .12), public_joint_ranges=((-2., 2.), (-2., 2.)), dt=.02)
