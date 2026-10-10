"""Permission and hysteresis checks; no policy or model training is run."""

from dataclasses import replace
import json

import numpy as np
import pytest

from developmental_control.maturation import (
    ActionEnvelope, CompetenceGate, GateConfig, GateEvidence, StagePermission,
)


STAGES = (
    StagePermission("one joint", (True, False), (0.2, 0.0)),
    StagePermission("both joints", (True, True), (0.4, 0.2)),
    StagePermission("expanded", (True, True), (0.6, 0.4)),
)
GOOD = GateEvidence(0.001, 0.01, 0.2, 0.005, True, True)


def test_gate_requires_consecutive_success_and_dwell_after_each_transition():
    gate = CompetenceGate(STAGES, GateConfig(pass_windows=2, min_dwell_windows=4))
    assert [gate.observe(GOOD) for _ in range(3)] == ["hold"] * 3
    assert gate.level == 0
    assert gate.observe(GOOD) == "promote"
    assert gate.permission == STAGES[1]
    assert gate.observe(GOOD) == "hold"
    assert gate.observe(replace(GOOD, recovered=False)) == "hold"
    assert gate.observe(GOOD) == "hold"
    assert gate.observe(GOOD) == "promote"
    assert gate.level == 2
    assert [gate.observe(GOOD) for _ in range(4)] == ["hold"] * 4
    assert len(gate.events) == 12
    assert gate.events[3]["level_before"] == 0
    assert gate.events[3]["level_after"] == 1


@pytest.mark.parametrize("bad", [
    replace(GOOD, safe=False),
    replace(GOOD, prediction_rmse=0.006),
    replace(GOOD, model_error_bound=0.021),
    replace(GOOD, tracking_rmse=np.nan),
    replace(GOOD, peak_speed=np.inf),
])
def test_risk_and_model_mismatch_withdraw_one_level_without_immediate_repromotion(bad):
    gate = CompetenceGate(STAGES, GateConfig())
    for _ in range(6):
        gate.observe(GOOD)
    assert gate.level == 2
    assert gate.observe(bad) == "retreat"
    assert gate.level == 1
    assert [gate.observe(GOOD) for _ in range(2)] == ["hold", "hold"]
    assert gate.observe(GOOD) == "promote"
    for expected_level in (1, 0):
        assert gate.observe(bad) == "retreat"
        assert gate.level == expected_level
    assert gate.observe(bad) == "hold"
    assert gate.level == 0
    json.dumps(gate.events, allow_nan=False)


def test_normal_failure_breaks_success_streak_but_counts_toward_dwell():
    gate = CompetenceGate(STAGES, GateConfig(pass_windows=2, min_dwell_windows=4))
    gate.observe(GOOD)
    gate.observe(replace(GOOD, tracking_rmse=0.05))
    assert gate.dwell_windows == 2
    assert gate.pass_count == 0
    assert gate.observe(GOOD) == "hold"
    assert gate.observe(GOOD) == "promote"


def test_envelope_enforces_mask_and_limits_without_changing_input():
    envelope = ActionEnvelope((0.6, 0.4))
    action = np.array([100.0, -100.0])
    np.testing.assert_array_equal(envelope.apply(action, STAGES[0]), [0.2, 0.0])
    np.testing.assert_array_equal(envelope.apply(action, STAGES[2]), [0.6, -0.4])
    np.testing.assert_array_equal(action, [100.0, -100.0])
    locked = StagePermission("locked", (False, False), (0.6, 0.4))
    np.testing.assert_array_equal(envelope.apply(action, locked), [0.0, 0.0])
    too_much = StagePermission("invalid authority", (True, True), (0.7, 0.4))
    with pytest.raises(ValueError, match="hard torque"):
        envelope.apply(action, too_much)


@pytest.mark.parametrize("action", [
    np.array([np.nan, 0.0]), np.array([np.inf, 0.0]),
    np.array([0.0]), np.zeros((1, 2)), np.array([1j, 0j]),
    np.array(["1", "2"]), np.array([True, False]),
])
def test_invalid_actions_are_rejected_before_execution(action):
    with pytest.raises(ValueError):
        ActionEnvelope((0.6, 0.4)).apply(action, STAGES[0])


@pytest.mark.parametrize("kwargs", [
    {"max_prediction_rmse": np.nan}, {"max_model_error_bound": np.inf},
    {"max_tracking_rmse": -0.1}, {"max_peak_speed": True},
    {"pass_windows": 0}, {"pass_windows": 1.5},
    {"min_dwell_windows": -1}, {"min_dwell_windows": True},
])
def test_invalid_gate_configuration_is_rejected(kwargs):
    with pytest.raises(ValueError):
        GateConfig(**kwargs)


@pytest.mark.parametrize("name,mask,limits", [
    ("", (True,), (0.2,)), ("x", (), ()),
    ("x", (1,), (0.2,)), ("x", (True,), (-0.2,)),
    ("x", (True,), (np.nan,)), ("x", (True,), (np.inf,)),
    ("x", (True,), (True,)), ("x", (True, False), (0.2,)),
    ("x", [True], (0.2,)),
])
def test_invalid_stage_definitions_are_rejected(name, mask, limits):
    with pytest.raises(ValueError):
        StagePermission(name, mask, limits)


def test_stage_sequence_cannot_silently_reduce_permissions_or_change_dimensions():
    bad_sequences = (
        (),
        (STAGES[1], STAGES[0]),
        (STAGES[0], StagePermission("lower torque", (True, True), (0.1, 0.2))),
        (STAGES[0], StagePermission("wrong size", (True,), (0.4,))),
    )
    for stages in bad_sequences:
        with pytest.raises(ValueError):
            CompetenceGate(stages, GateConfig())
    with pytest.raises(ValueError):
        ActionEnvelope((np.nan,))
    with pytest.raises(ValueError):
        ActionEnvelope((0.6,)).apply(np.array([0.0]), STAGES[0])
