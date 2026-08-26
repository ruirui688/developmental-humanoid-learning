import pytest
import torch

from developmental_g1.ground_development import (
    blend_pose_sampling_probabilities,
    competence_weighted_pose_probabilities,
    frontier_preserving_score,
    noncompensatory_pair_score,
    normalized_torque_headroom_cost,
    rehearsal_bounded_pose_probabilities,
    rise_progress_score,
    rise_subskill_chain_score,
    safety_refined_skill_score,
    stage_goal_score,
)


def score(height, gravity, speed, upright_weight=0.0, exploration_weight=0.0):
    return stage_goal_score(
        base_height=torch.tensor([height]),
        gravity_error=torch.tensor([gravity]),
        joint_speed=torch.tensor([speed]),
        target_height=0.5,
        upright_weight=upright_weight,
        exploration_weight=exploration_weight,
        target_joint_speed=0.3,
        height_scale=0.05,
        upright_sigma=0.2,
        joint_speed_sigma=0.08,
    ).item()


def test_height_goal_rewards_incremental_rising():
    assert score(0.65, 1.0, 0.0) > score(0.50, 1.0, 0.0)
    assert score(0.50, 1.0, 0.0) > score(0.35, 1.0, 0.0)


def test_rise_progress_has_gradient_well_below_final_target():
    height = torch.tensor([0.20], requires_grad=True)
    result = rise_progress_score(
        base_height=height,
        gravity_error=torch.ones(1),
        joint_speed=torch.tensor([0.2]),
        floor_height=0.12,
        target_height=0.50,
        upright_weight=0.30,
        exploration_weight=0.15,
        target_joint_speed=0.22,
        upright_sigma=0.20,
        joint_speed_sigma=0.08,
    )
    result.backward()
    assert result.item() > 0.0
    assert height.grad.item() > 1.0


def test_rise_refinements_cannot_reward_floor_height():
    result = rise_progress_score(
        base_height=torch.tensor([0.12]),
        gravity_error=torch.zeros(1),
        joint_speed=torch.tensor([0.22]),
        floor_height=0.12,
        target_height=0.50,
        upright_weight=0.30,
        exploration_weight=0.15,
        target_joint_speed=0.22,
        upright_sigma=0.20,
        joint_speed_sigma=0.08,
    )
    assert result.item() == 0.0


def test_rise_subskills_are_noncompensatory_and_cannot_replace_height():
    signals = dict(
        orientation_target=0.35,
        required_support_count=2,
        knee_flexion_target=0.60,
    )
    prepared_floor = rise_subskill_chain_score(
        rise_score=torch.tensor([0.0]),
        orientation_change=torch.tensor([1.0]),
        support_count=torch.tensor([2.0]),
        mean_knee_flexion=torch.tensor([1.0]),
        **signals,
    )
    missing_brace = rise_subskill_chain_score(
        rise_score=torch.tensor([0.0]),
        orientation_change=torch.tensor([1.0]),
        support_count=torch.tensor([0.0]),
        mean_knee_flexion=torch.tensor([1.0]),
        **signals,
    )
    unprepared_half_rise = rise_subskill_chain_score(
        rise_score=torch.tensor([0.5]),
        orientation_change=torch.tensor([0.0]),
        support_count=torch.tensor([0.0]),
        mean_knee_flexion=torch.tensor([0.0]),
        **signals,
    )
    assert missing_brace.item() < prepared_floor.item()
    assert prepared_floor.item() <= 0.25
    assert unprepared_half_rise.item() > prepared_floor.item()


def test_rise_subskills_reward_preparation_at_equal_height():
    common = dict(
        rise_score=torch.tensor([0.35]),
        orientation_target=0.35,
        required_support_count=2,
        knee_flexion_target=0.60,
    )
    prepared = rise_subskill_chain_score(
        orientation_change=torch.tensor([1.0]),
        support_count=torch.tensor([2.0]),
        mean_knee_flexion=torch.tensor([1.0]),
        **common,
    )
    flat = rise_subskill_chain_score(
        orientation_change=torch.tensor([0.0]),
        support_count=torch.tensor([0.0]),
        mean_knee_flexion=torch.tensor([0.0]),
        **common,
    )
    assert prepared.item() > flat.item()


def test_early_stage_prefers_controlled_exploration_not_stillness():
    target = score(0.5, 1.0, 0.3, exploration_weight=0.6)
    motionless = score(0.5, 1.0, 0.0, exploration_weight=0.6)
    violent = score(0.5, 1.0, 1.2, exploration_weight=0.6)
    assert target > motionless
    assert target > violent


def test_late_stage_prefers_upright_pose():
    upright = score(0.75, 0.0, 0.05, upright_weight=0.85)
    lying = score(0.75, 1.0, 0.05, upright_weight=0.85)
    assert upright > lying


def test_invalid_weights_and_shapes_are_rejected():
    with pytest.raises(ValueError, match="weights"):
        score(0.5, 0.0, 0.3, upright_weight=0.8, exploration_weight=0.3)
    with pytest.raises(ValueError, match="shape"):
        stage_goal_score(
            base_height=torch.zeros(2),
            gravity_error=torch.zeros(1),
            joint_speed=torch.zeros(2),
            target_height=0.5,
            upright_weight=0.0,
            exploration_weight=0.0,
            target_joint_speed=0.3,
            height_scale=0.05,
            upright_sigma=0.2,
            joint_speed_sigma=0.08,
        )


def test_frontier_score_cannot_trade_height_away_for_exploration():
    collapsed = frontier_preserving_score(
        height_goal_score=torch.tensor([0.05]),
        upright_goal_score=torch.tensor([0.0]),
        exploration_score=torch.tensor([1.0]),
    )
    retained = frontier_preserving_score(
        height_goal_score=torch.tensor([0.50]),
        upright_goal_score=torch.tensor([0.2]),
        exploration_score=torch.tensor([0.2]),
    )
    assert retained.item() > collapsed.item() * 5.0


def test_pose_sampling_focuses_weak_pose_but_rehearses_mastered_pose():
    weights = competence_weighted_pose_probabilities(
        torch.tensor([1.0, 0.0, 0.5, 0.9])
    )
    assert torch.isclose(weights.sum(), torch.tensor(1.0))
    assert weights[1] > weights[2] > weights[3] > weights[0] > 0.0


def test_pair_score_does_not_allow_one_skill_to_replace_the_other():
    paired = noncompensatory_pair_score(
        torch.tensor([1.0, 1.0, 0.5]), torch.tensor([0.0, 1.0, 0.5])
    )
    assert paired[0] < paired[2] < paired[1]


def test_pose_sampling_update_is_damped_against_curriculum_oscillation():
    current = torch.tensor([0.25, 0.25, 0.25, 0.25])
    target = torch.tensor([0.70, 0.10, 0.10, 0.10])
    blended = blend_pose_sampling_probabilities(current, target)
    assert torch.allclose(blended, torch.tensor([0.3625, 0.2125, 0.2125, 0.2125]))


def test_pose_sampling_keeps_uniform_rehearsal_dominant():
    bounded = rehearsal_bounded_pose_probabilities(
        torch.tensor([1.0, 0.0, 0.0, 0.0])
    )
    assert torch.allclose(bounded, torch.tensor([0.55, 0.15, 0.15, 0.15]))


def test_unsafe_execution_cannot_buy_full_skill_reward():
    refined = safety_refined_skill_score(
        skill_score=torch.ones(2),
        impact_force=torch.tensor([100.0, 500.0]),
        angular_speed=torch.tensor([2.0, 8.0]),
        peak_torque_ratio=torch.tensor([0.5, 1.0]),
        safe_support_force=220.0,
        safe_angular_speed=4.0,
    )
    assert refined[0] == 1.0
    assert 0.25 <= refined[1] < 0.35


def test_torque_headroom_cost_is_normalized_across_actuator_sizes():
    cost = normalized_torque_headroom_cost(
        torque=torch.tensor([[9.0, 90.0], [7.0, 70.0]]),
        torque_limit=torch.tensor([10.0, 100.0]),
    )
    assert torch.allclose(cost, torch.tensor([0.02, 0.0]))


def test_torque_headroom_rejects_invalid_limits():
    with pytest.raises(ValueError, match="positive"):
        normalized_torque_headroom_cost(
            torque=torch.ones(1, 2), torque_limit=torch.tensor([1.0, 0.0])
        )
