import pytest
import torch

from developmental_g1.assistive_support import AssistanceConfig, caregiver_force


def force(height, fraction=1.0, xy=(0.0, 0.0), velocity=(0.0, 0.0, 0.0)):
    return caregiver_force(
        base_position=torch.tensor([[xy[0], xy[1], height]]),
        base_velocity=torch.tensor([velocity]),
        anchor_xy=torch.zeros(1, 2),
        assistance_fraction=fraction,
        config=AssistanceConfig(),
    )[0]


def test_assistance_does_not_lift_motionless_robot_from_floor():
    assert torch.allclose(force(0.25), torch.zeros(3))


def test_assistance_engages_only_after_robot_begins_rising():
    partial = force(0.40)
    full = force(0.60)
    assert 0.0 < partial[2] < full[2]
    assert full[2].item() == pytest.approx(180.0)


def test_zero_assistance_fraction_is_exactly_unassisted():
    assert torch.allclose(
        force(0.60, fraction=0.0, xy=(1.0, 1.0)), torch.zeros(3)
    )


def test_horizontal_caregiver_force_is_bounded_and_recenters():
    result = force(0.60, xy=(2.0, 0.0))
    assert result[0].item() == pytest.approx(-60.0)
    assert result[1].item() == pytest.approx(0.0)


def test_bad_shapes_are_rejected():
    with pytest.raises(ValueError, match="base_position"):
        caregiver_force(
            base_position=torch.zeros(3),
            base_velocity=torch.zeros(3),
            anchor_xy=torch.zeros(1, 2),
            assistance_fraction=1.0,
            config=AssistanceConfig(),
        )
