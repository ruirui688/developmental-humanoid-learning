"""Auditable external support analogous to a harness, walker, or caregiver."""

from __future__ import annotations

from dataclasses import dataclass

import torch


@dataclass(frozen=True)
class AssistanceConfig:
    max_upward_force: float = 180.0
    max_horizontal_force: float = 60.0
    horizontal_stiffness: float = 80.0
    horizontal_damping: float = 25.0
    activation_height: float = 0.32
    full_support_height: float = 0.55

    def __post_init__(self) -> None:
        for name in (
            "max_upward_force",
            "max_horizontal_force",
            "horizontal_stiffness",
            "horizontal_damping",
        ):
            if getattr(self, name) < 0.0:
                raise ValueError(f"{name} cannot be negative")
        if not 0.0 <= self.activation_height < self.full_support_height:
            raise ValueError("assistance activation heights must be ordered")


def caregiver_force(
    *,
    base_position: torch.Tensor,
    base_velocity: torch.Tensor,
    anchor_xy: torch.Tensor,
    assistance_fraction: float | torch.Tensor,
    config: AssistanceConfig,
) -> torch.Tensor:
    """Compute bounded unloading and centering without prescribing joint motion."""

    if base_position.ndim != 2 or base_position.shape[1] != 3:
        raise ValueError("base_position must have shape [N, 3]")
    if base_velocity.shape != base_position.shape:
        raise ValueError("base_velocity must match base_position")
    if anchor_xy.shape != base_position[:, :2].shape:
        raise ValueError("anchor_xy must have shape [N, 2]")
    fraction = torch.as_tensor(
        assistance_fraction,
        device=base_position.device,
        dtype=base_position.dtype,
    ).clamp(0.0, 1.0)
    activation = (
        (base_position[:, 2] - config.activation_height)
        / (config.full_support_height - config.activation_height)
    ).clamp(0.0, 1.0)
    scale = activation * fraction
    horizontal = -config.horizontal_stiffness * (
        base_position[:, :2] - anchor_xy
    ) - config.horizontal_damping * base_velocity[:, :2]
    horizontal_norm = torch.linalg.vector_norm(horizontal, dim=1, keepdim=True)
    horizontal = horizontal * torch.clamp(
        config.max_horizontal_force / horizontal_norm.clamp_min(1e-6),
        max=1.0,
    )
    force = torch.zeros_like(base_position)
    force[:, :2] = horizontal * scale.unsqueeze(-1)
    force[:, 2] = config.max_upward_force * scale
    return force
