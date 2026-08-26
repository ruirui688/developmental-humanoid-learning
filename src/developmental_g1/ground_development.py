"""Simulator-independent scoring for ground-start motor development."""

from __future__ import annotations

import torch


def normalized_torque_headroom_cost(
    torque: torch.Tensor,
    torque_limit: torch.Tensor,
    soft_ratio: float = 0.80,
) -> torch.Tensor:
    """Penalize relative, not absolute, actuator-limit consumption.

    Absolute torque excess underweights low-capacity shoulder and elbow
    motors even though reaching their limit is just as unsafe as saturating a
    larger hip motor. The squared relative excess provides equal headroom
    pressure per actuator and a continuous gradient before hard saturation.
    """

    if torque.ndim != 2 or torque_limit.shape not in {
        torque.shape,
        (torque.shape[1],),
    }:
        raise ValueError("torque limits must align with the actuator dimension")
    if not 0.0 < soft_ratio < 1.0:
        raise ValueError("soft torque ratio must be in (0, 1)")
    if bool(torch.any(torque_limit <= 0.0)):
        raise ValueError("torque limits must be positive")
    ratio = torch.abs(torque) / torque_limit.clamp_min(1e-6)
    return torch.sum(torch.square(torch.clamp(ratio - soft_ratio, min=0.0)), dim=1)


def competence_weighted_pose_probabilities(
    pose_competence: torch.Tensor, rehearsal_floor: float = 0.10
) -> torch.Tensor:
    """Turn per-pose competence into normalized hard-example reset weights."""

    if pose_competence.ndim != 1 or pose_competence.numel() < 1:
        raise ValueError("pose competence must be a non-empty vector")
    if not torch.isfinite(pose_competence).all():
        raise ValueError("pose competence must be finite")
    if rehearsal_floor <= 0.0:
        raise ValueError("rehearsal floor must be positive")
    difficulty = rehearsal_floor + 1.0 - pose_competence.clamp(0.0, 1.0)
    return difficulty / difficulty.sum()


def blend_pose_sampling_probabilities(
    current: torch.Tensor, target: torch.Tensor, update_rate: float = 0.25
) -> torch.Tensor:
    """Damp curriculum changes so hard-example mining does not cause forgetting."""

    if current.shape != target.shape or current.ndim != 1:
        raise ValueError("current and target pose weights must be aligned vectors")
    if not 0.0 < update_rate <= 1.0:
        raise ValueError("pose-weight update rate must be in (0, 1]")
    if not torch.isfinite(current).all() or not torch.isfinite(target).all():
        raise ValueError("pose weights must be finite")
    if bool(torch.any(current < 0.0)) or bool(torch.any(target < 0.0)):
        raise ValueError("pose weights cannot be negative")
    blended = (1.0 - update_rate) * current + update_rate * target
    return blended / blended.sum()


def rehearsal_bounded_pose_probabilities(
    weights: torch.Tensor, focus_fraction: float = 0.40
) -> torch.Tensor:
    """Keep uniform rehearsal dominant while retaining a hard-pose bias."""

    if weights.ndim != 1 or weights.numel() < 1:
        raise ValueError("pose weights must be a non-empty vector")
    if not 0.0 <= focus_fraction <= 1.0:
        raise ValueError("focus fraction must be in [0, 1]")
    if not torch.isfinite(weights).all() or bool(torch.any(weights < 0.0)):
        raise ValueError("pose weights must be finite and non-negative")
    normalized = weights / weights.sum().clamp_min(1e-8)
    uniform = torch.full_like(normalized, 1.0 / normalized.numel())
    return (1.0 - focus_fraction) * uniform + focus_fraction * normalized


def noncompensatory_pair_score(
    first: torch.Tensor, second: torch.Tensor
) -> torch.Tensor:
    """Score two prerequisites without allowing either one to buy off the other."""

    if first.shape != second.shape:
        raise ValueError("paired developmental scores must share a shape")
    if bool(torch.any((first < 0.0) | (first > 1.0))) or bool(
        torch.any((second < 0.0) | (second > 1.0))
    ):
        raise ValueError("paired developmental scores must be in [0, 1]")
    harmonic = 2.0 * first * second / (first + second).clamp_min(1e-6)
    rehearsal = 0.5 * (first + second)
    return (0.80 * harmonic + 0.20 * rehearsal).clamp(0.0, 1.0)


def safety_refined_skill_score(
    *,
    skill_score: torch.Tensor,
    impact_force: torch.Tensor,
    angular_speed: torch.Tensor,
    peak_torque_ratio: torch.Tensor,
    safe_support_force: float,
    safe_angular_speed: float,
) -> torch.Tensor:
    """Make safe execution a prerequisite rather than an additive tradeoff."""

    if not (
        skill_score.shape
        == impact_force.shape
        == angular_speed.shape
        == peak_torque_ratio.shape
    ):
        raise ValueError("skill and safety signals must share a shape")
    if safe_support_force <= 0.0 or safe_angular_speed <= 0.0:
        raise ValueError("safety scales must be positive")
    impact_excess = torch.clamp(
        (impact_force - safe_support_force) / safe_support_force,
        min=0.0,
        max=3.0,
    )
    angular_excess = torch.clamp(
        (angular_speed - safe_angular_speed) / safe_angular_speed,
        min=0.0,
        max=3.0,
    )
    torque_excess = torch.clamp(
        (peak_torque_ratio - 0.80) / 0.20,
        min=0.0,
        max=3.0,
    )
    safety = torch.exp(
        -torch.square(impact_excess)
        -torch.square(angular_excess)
        -torch.square(torque_excess)
    )
    return skill_score * (0.25 + 0.75 * safety)


def frontier_preserving_score(
    *,
    height_goal_score: torch.Tensor,
    upright_goal_score: torch.Tensor,
    exploration_score: torch.Tensor,
) -> torch.Tensor:
    """Reward exploration only while preserving the current height frontier."""

    if not (
        height_goal_score.shape
        == upright_goal_score.shape
        == exploration_score.shape
    ):
        raise ValueError("frontier score signals must share a shape")
    for signal in (height_goal_score, upright_goal_score, exploration_score):
        if bool(torch.any((signal < 0.0) | (signal > 1.0))):
            raise ValueError("frontier score signals must be in [0, 1]")
    # A weighted sum allowed policies to discard all height for easy joint
    # motion. Height is now the necessary factor; uprightness and safe motion
    # only refine a state that preserves the current capability frontier.
    refinement = 0.65 + 0.20 * upright_goal_score + 0.15 * exploration_score
    return (height_goal_score * refinement).clamp(0.0, 1.0)


def stage_goal_score(
    *,
    base_height: torch.Tensor,
    gravity_error: torch.Tensor,
    joint_speed: torch.Tensor,
    target_height: float | torch.Tensor,
    upright_weight: float | torch.Tensor,
    exploration_weight: float | torch.Tensor,
    target_joint_speed: float | torch.Tensor,
    height_scale: float,
    upright_sigma: float,
    joint_speed_sigma: float,
) -> torch.Tensor:
    """Return a normalized blend of rising, uprightness and safe movement."""

    if base_height.shape != gravity_error.shape or base_height.shape != joint_speed.shape:
        raise ValueError("ground-development signals must share a shape")
    if min(height_scale, upright_sigma, joint_speed_sigma) <= 0.0:
        raise ValueError("ground-development score scales must be positive")
    upright_weight_tensor = torch.as_tensor(
        upright_weight, device=base_height.device, dtype=base_height.dtype
    )
    exploration_weight_tensor = torch.as_tensor(
        exploration_weight, device=base_height.device, dtype=base_height.dtype
    )
    height_weight = 1.0 - upright_weight_tensor - exploration_weight_tensor
    if bool(
        torch.any(upright_weight_tensor < 0.0)
        or torch.any(exploration_weight_tensor < 0.0)
        or torch.any(height_weight < 0.0)
    ):
        raise ValueError("score weights must be non-negative and sum to <= 1")
    height_score = torch.sigmoid(
        (base_height - target_height) / height_scale
    )
    upright_score = torch.exp(-gravity_error / upright_sigma)
    exploration_score = torch.exp(
        -torch.square(joint_speed - target_joint_speed) / joint_speed_sigma
    )
    return (
        height_weight * height_score
        + upright_weight_tensor * upright_score
        + exploration_weight_tensor * exploration_score
    ).clamp(0.0, 1.0)


def rise_progress_score(
    *,
    base_height: torch.Tensor,
    gravity_error: torch.Tensor,
    joint_speed: torch.Tensor,
    floor_height: float,
    target_height: float | torch.Tensor,
    upright_weight: float | torch.Tensor,
    exploration_weight: float | torch.Tensor,
    target_joint_speed: float | torch.Tensor,
    upright_sigma: float,
    joint_speed_sigma: float,
) -> torch.Tensor:
    """Reward every safe height increment while making rising indispensable.

    A sigmoid centred on the final rise height has very little gradient near a
    ground start.  This score supplies a constant height gradient between the
    floor and the current stage target.  Uprightness and controlled motion can
    refine that progress, but cannot replace it.
    """

    if base_height.shape != gravity_error.shape or base_height.shape != joint_speed.shape:
        raise ValueError("ground-development signals must share a shape")
    if min(upright_sigma, joint_speed_sigma) <= 0.0:
        raise ValueError("ground-development score scales must be positive")
    target = torch.as_tensor(
        target_height, device=base_height.device, dtype=base_height.dtype
    )
    if bool(torch.any(target <= floor_height)):
        raise ValueError("rise target height must exceed floor height")
    upright_weight_tensor = torch.as_tensor(
        upright_weight, device=base_height.device, dtype=base_height.dtype
    )
    exploration_weight_tensor = torch.as_tensor(
        exploration_weight, device=base_height.device, dtype=base_height.dtype
    )
    height_weight = 1.0 - upright_weight_tensor - exploration_weight_tensor
    if bool(
        torch.any(upright_weight_tensor < 0.0)
        or torch.any(exploration_weight_tensor < 0.0)
        or torch.any(height_weight < 0.0)
    ):
        raise ValueError("score weights must be non-negative and sum to <= 1")
    height_progress = ((base_height - floor_height) / (target - floor_height)).clamp(
        0.0, 1.0
    )
    upright_score = torch.exp(-gravity_error / upright_sigma)
    exploration_score = torch.exp(
        -torch.square(joint_speed - target_joint_speed) / joint_speed_sigma
    )
    refinement = (
        height_weight
        + upright_weight_tensor * upright_score
        + exploration_weight_tensor * exploration_score
    )
    return (height_progress * refinement).clamp(0.0, 1.0)
