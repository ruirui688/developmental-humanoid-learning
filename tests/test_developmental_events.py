import torch

from developmental_g1.developmental_events import (
    DevelopmentalEventConfig,
    SustainedDevelopmentalEvents,
)


def signals(**overrides):
    values = dict(
        orientation_change_rad=torch.tensor([1.2, 0.0]),
        support_contact_count=torch.tensor([2, 0]),
        foot_contact_count=torch.tensor([2, 2]),
        base_height=torch.tensor([0.75, 0.30]),
        upright_score=torch.tensor([0.98, 0.10]),
        base_speed=torch.tensor([0.05, 0.0]),
        assistance_fraction=0.0,
    )
    values.update(overrides)
    return values


def short_config():
    return DevelopmentalEventConfig(
        roll_steps=2,
        brace_steps=2,
        raised_steps=2,
        upright_steps=2,
        independent_standing_steps=3,
    )


def test_milestones_require_continuous_evidence():
    tracker = SustainedDevelopmentalEvents(2, "cpu", short_config())
    first = tracker.update(**signals())
    assert not first.rolling.any()
    assert not first.upright.any()
    second = tracker.update(**signals())
    assert second.rolling.tolist() == [True, False]
    assert second.bracing.tolist() == [True, False]
    assert second.raised.tolist() == [True, False]
    assert second.upright.tolist() == [True, False]
    assert not second.independent_standing.any()
    third = tracker.update(**signals())
    assert third.independent_standing.tolist() == [True, False]


def test_one_bad_frame_resets_duration_but_not_past_achievement():
    tracker = SustainedDevelopmentalEvents(2, "cpu", short_config())
    tracker.update(**signals())
    tracker.update(**signals(orientation_change_rad=torch.zeros(2)))
    assert not tracker.achieved["rolling"].any()
    tracker.update(**signals())
    tracker.update(**signals())
    assert tracker.achieved["rolling"].tolist() == [True, False]
    tracker.update(**signals(orientation_change_rad=torch.zeros(2)))
    assert tracker.achieved["rolling"].tolist() == [True, False]


def test_assistance_disqualifies_independent_standing_only():
    tracker = SustainedDevelopmentalEvents(2, "cpu", short_config())
    for _ in range(3):
        state = tracker.update(**signals(assistance_fraction=0.25))
    assert state.upright.tolist() == [True, False]
    assert not state.independent_standing.any()


def test_reset_contact_without_body_reorientation_is_not_bracing():
    tracker = SustainedDevelopmentalEvents(2, "cpu", short_config())
    unchanged = signals(
        orientation_change_rad=torch.zeros(2),
        support_contact_count=torch.tensor([2, 2]),
        base_height=torch.tensor([0.12, 0.12]),
    )
    tracker.update(**unchanged)
    state = tracker.update(**unchanged)
    assert not state.bracing.any()


def test_ground_level_reoriented_support_counts_as_bracing():
    tracker = SustainedDevelopmentalEvents(2, "cpu", short_config())
    ground_brace = signals(
        orientation_change_rad=torch.tensor([0.50, 0.0]),
        support_contact_count=torch.tensor([2, 2]),
        base_height=torch.tensor([0.12, 0.12]),
    )
    tracker.update(**ground_brace)
    state = tracker.update(**ground_brace)
    assert state.bracing.tolist() == [True, False]


def test_reset_clears_only_selected_environments():
    tracker = SustainedDevelopmentalEvents(2, "cpu", short_config())
    both_standing = signals(
        orientation_change_rad=torch.tensor([1.2, 1.2]),
        support_contact_count=torch.tensor([2, 2]),
        base_height=torch.tensor([0.75, 0.75]),
        upright_score=torch.tensor([0.98, 0.98]),
        base_speed=torch.tensor([0.05, 0.05]),
    )
    for _ in range(3):
        tracker.update(**both_standing)
    tracker.reset(torch.tensor([0]))
    assert not tracker.achieved["independent_standing"][0]
    assert tracker.achieved["independent_standing"][1]
