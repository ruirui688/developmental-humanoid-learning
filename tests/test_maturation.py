import pytest
import torch

from developmental_g1.maturation import (
    CompetenceSample,
    MaturationConfig,
    MaturationController,
    MaturationStage,
)
from developmental_g1.action_transform import MaturationTransform


STAGES = (
    MaturationStage("protected_exploration", ("arms", "waist"), 0.15, 0.25),
    MaturationStage("postural_control", ("arms", "waist", "legs"), 0.30, 0.45),
    MaturationStage("full_body", ("arms", "waist", "legs"), 1.00, 1.00),
)


def sample(score: float, fall_rate: float = 0.0) -> CompetenceSample:
    return CompetenceSample(
        survival=score,
        upright=score,
        low_risk=score,
        low_saturation=score,
        schema_accuracy=score,
        fall_rate=fall_rate,
    )


def test_promotes_only_after_dwell_and_consecutive_windows():
    controller = MaturationController(
        STAGES,
        MaturationConfig(minimum_dwell_windows=3, promotion_windows=2),
    )
    assert controller.observe(sample(0.9)) is None
    assert controller.observe(sample(0.9)) is None
    transition = controller.observe(sample(0.9))
    assert transition is not None
    assert transition.direction == "promotion"
    assert controller.stage.name == "postural_control"


def test_fall_rate_blocks_promotion_even_with_high_score():
    controller = MaturationController(
        STAGES,
        MaturationConfig(minimum_dwell_windows=1, promotion_windows=1),
    )
    assert controller.observe(sample(0.95, fall_rate=0.1)) is None
    assert controller.stage_index == 0


def test_forced_demotion_uses_hysteresis():
    controller = MaturationController(
        STAGES,
        MaturationConfig(
            minimum_dwell_windows=1,
            promotion_windows=1,
            demotion_windows=2,
        ),
    )
    controller.observe(sample(0.9))
    assert controller.stage_index == 1
    assert controller.observe(sample(0.9, fall_rate=0.3)) is None
    transition = controller.observe(sample(0.9, fall_rate=0.3))
    assert transition is not None
    assert transition.direction == "demotion"
    assert controller.stage_index == 0


def test_state_round_trip_preserves_gate_progress():
    first = MaturationController(STAGES)
    first.observe(sample(0.9))
    state = first.state_dict()
    second = MaturationController(STAGES)
    second.load_state_dict(state)
    assert second.state_dict() == state


def test_rejects_invalid_metrics_and_weights():
    with pytest.raises(ValueError):
        sample(1.1)
    with pytest.raises(ValueError):
        MaturationConfig(survival_weight=0.5)


def test_action_transform_masks_closed_joints_and_limits_open_joints():
    transform = MaturationTransform(
        ("left_leg", "right_leg", "waist", "arm"),
        {"legs": ("left_leg", "right_leg"), "waist": ("waist",), "arms": ("arm",)},
    )
    actions = torch.tensor([[100.0, -100.0, 2.0, -2.0]], requires_grad=True)
    executed, mask, action_range = transform.apply(actions, STAGES[0])
    assert torch.equal(mask, torch.tensor([0.0, 0.0, 1.0, 1.0]))
    assert torch.equal(action_range, torch.tensor([0.0, 0.0, 0.15, 0.15]))
    assert torch.all(executed[:, :2] == 0.0)
    assert torch.all(executed.abs() <= action_range + 1e-7)
    executed.sum().backward()
    assert torch.all(actions.grad[:, :2] == 0.0)


def test_fixed_schedule_uses_cumulative_environment_steps():
    controller = MaturationController(STAGES)
    assert controller.follow_fixed_schedule(99, (100, 200)) is None
    transition = controller.follow_fixed_schedule(100, (100, 200))
    assert transition is not None
    assert transition.direction == "fixed_schedule"
    assert controller.stage_index == 1
    transition = controller.follow_fixed_schedule(250, (100, 200))
    assert transition is not None
    assert controller.stage_index == 2


def test_fixed_schedule_rejects_ambiguous_thresholds():
    controller = MaturationController(STAGES)
    with pytest.raises(ValueError):
        controller.follow_fixed_schedule(0, (100,))
    with pytest.raises(ValueError):
        controller.follow_fixed_schedule(0, (100, 100))
