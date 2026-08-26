import pytest

from developmental_g1.capability_frontier import (
    CapabilityFrontier,
    FrontierConfig,
    FrontierEvidence,
)


def evidence(**overrides):
    values = dict(
        height_quantile=0.30,
        upright_quantile=0.10,
        height_target_success_fraction=0.8,
        upright_target_success_fraction=0.8,
        safe_fraction=0.95,
        saturation_fraction=0.02,
        schema_accuracy=0.8,
        episodes=1024,
    )
    values.update(overrides)
    return FrontierEvidence(**values)


def test_passive_calibration_places_goal_just_beyond_observed_frontier():
    frontier = CapabilityFrontier()
    update = frontier.calibrate(evidence())
    assert update.height_target == pytest.approx(0.33)
    assert update.upright_target == pytest.approx(0.14)
    assert frontier.progress > 0.0


def test_frontier_requires_repeated_safe_held_out_evidence():
    frontier = CapabilityFrontier(FrontierConfig(confirmation_windows=2))
    frontier.calibrate(evidence())
    first = frontier.observe(evidence(height_quantile=0.36, upright_quantile=0.18))
    second = frontier.observe(evidence(height_quantile=0.36, upright_quantile=0.18))
    assert not first.advanced
    assert second.advanced
    assert second.height_target == pytest.approx(0.39)
    assert second.upright_target == pytest.approx(0.22)


def test_risky_or_saturated_progress_does_not_move_frontier():
    frontier = CapabilityFrontier(FrontierConfig(confirmation_windows=1))
    frontier.calibrate(evidence())
    unsafe = frontier.observe(evidence(height_quantile=0.60, safe_fraction=0.4))
    saturated = frontier.observe(
        evidence(height_quantile=0.60, saturation_fraction=0.5)
    )
    assert not unsafe.advanced
    assert not saturated.advanced
    assert frontier.height_target == pytest.approx(0.33)


def test_frontier_is_monotone_and_capped_by_final_goal():
    frontier = CapabilityFrontier(FrontierConfig(confirmation_windows=1))
    frontier.calibrate(evidence(height_quantile=0.9, upright_quantile=1.0))
    assert frontier.height_target == pytest.approx(0.76)
    assert frontier.upright_target == pytest.approx(0.95)
    update = frontier.observe(
        evidence(height_quantile=0.2, upright_quantile=0.0)
    )
    assert not update.advanced
    assert frontier.progress == pytest.approx(1.0)


def test_frontier_state_round_trip_preserves_targets():
    first = CapabilityFrontier()
    first.calibrate(evidence())
    second = CapabilityFrontier()
    second.load_state_dict(first.state_dict())
    assert second.state_dict() == first.state_dict()


def test_height_only_frontier_ignores_future_upright_and_schema_requirements():
    frontier = CapabilityFrontier(FrontierConfig(confirmation_windows=2))
    frontier.calibrate(evidence(height_quantile=0.25))
    low_future_skill = evidence(
        height_quantile=0.32,
        upright_target_success_fraction=0.0,
        schema_accuracy=0.0,
    )
    first = frontier.observe_height_only(low_future_skill, ceiling=0.50)
    second = frontier.observe_height_only(low_future_skill, ceiling=0.50)
    assert not first.advanced
    assert second.advanced
    assert second.height_target == pytest.approx(0.31)


def test_height_only_frontier_still_rejects_saturation():
    frontier = CapabilityFrontier(FrontierConfig(confirmation_windows=1))
    frontier.calibrate(evidence(height_quantile=0.25))
    update = frontier.observe_height_only(
        evidence(height_quantile=0.40, saturation_fraction=0.5), ceiling=0.50
    )
    assert not update.advanced


def test_height_only_frontier_caps_each_increment_to_one_margin():
    frontier = CapabilityFrontier(FrontierConfig(confirmation_windows=1))
    frontier.calibrate(evidence(height_quantile=0.25))
    update = frontier.observe_height_only(
        evidence(height_quantile=0.60), ceiling=0.70
    )
    assert update.height_target == pytest.approx(0.31)


def test_height_only_frontier_accepts_a_stage_specific_success_threshold():
    frontier = CapabilityFrontier(FrontierConfig(confirmation_windows=1))
    frontier.calibrate(evidence(height_quantile=0.25))
    update = frontier.observe_height_only(
        evidence(height_quantile=0.32, height_target_success_fraction=0.4),
        ceiling=0.50,
        required_success_fraction=0.4,
    )
    assert update.advanced
