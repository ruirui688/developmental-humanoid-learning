"""New Y braking corner: pure native feedback, no physics or old MPC rerun."""
import importlib.util
from pathlib import Path

import pytest

from developmental_physics.damped_residual_pd_pair_mpc import public_pd_request


def load_engineering_feedback():
    path = Path(__file__).resolve().parents[1] / "scripts/validate_damped_suspended_pair_engineering.py"
    spec = importlib.util.spec_from_file_location("y_engineering_feedback", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_shoulder_velocity_changes_saturated_acceleration_to_braking():
    module = load_engineering_feedback()
    raw, request = module.pd_request((0., .1), (.8, .8), (.04, .14))
    assert raw == pytest.approx((-.64, -.64))
    assert request == [-.5, -.5]
    assert public_pd_request((0., .1), (.8, .8), (.04, .14)) == (-.5, -.5)


def test_new_gain_preserves_zero_velocity_permission_and_reverses_braking():
    module = load_engineering_feedback()
    for velocity, expected in (((0., 0.), (.5, .5)), ((-.8, -.8), (.5, .5))):
        _, request = module.pd_request((0., .1), velocity, (.04, .14))
        assert request == list(expected)
        assert public_pd_request((0., .1), velocity, (.04, .14)) == expected
