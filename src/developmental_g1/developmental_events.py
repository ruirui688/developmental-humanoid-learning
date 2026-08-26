"""Sustained, assistance-aware milestones for ground-start development.

These events are evaluation labels, not actor observations or reward shortcuts.
They prevent a one-frame height spike from being reported as rolling, rising, or
standing competence.
"""

from __future__ import annotations

from dataclasses import dataclass

import torch


@dataclass(frozen=True)
class DevelopmentalEventConfig:
    roll_angle_rad: float = 1.0472
    bracing_min_orientation_change_rad: float = 0.3491
    rolling_min_height: float = 0.11
    raised_height: float = 0.45
    bracing_min_height: float = 0.11
    standing_height: float = 0.72
    standing_upright_score: float = 0.95
    standing_max_speed: float = 0.20
    support_contact_count: int = 2
    foot_contact_count: int = 2
    roll_steps: int = 25
    brace_steps: int = 25
    raised_steps: int = 25
    upright_steps: int = 50
    independent_standing_steps: int = 1000

    def __post_init__(self) -> None:
        if not 0.0 < self.roll_angle_rad <= 3.141593:
            raise ValueError("roll angle must be in (0, pi]")
        if not 0.0 < self.bracing_min_orientation_change_rad <= self.roll_angle_rad:
            raise ValueError(
                "bracing orientation change must be positive and no larger than roll angle"
            )
        if not (
            0.0
            < self.rolling_min_height
            <= self.bracing_min_height
            < self.raised_height
            < self.standing_height
        ):
            raise ValueError("event heights must be positive and ordered")
        if not 0.0 <= self.standing_upright_score <= 1.0:
            raise ValueError("standing upright score must be in [0, 1]")
        if self.standing_max_speed < 0.0:
            raise ValueError("standing maximum speed cannot be negative")
        integer_fields = (
            self.support_contact_count,
            self.foot_contact_count,
            self.roll_steps,
            self.brace_steps,
            self.raised_steps,
            self.upright_steps,
            self.independent_standing_steps,
        )
        if any(value < 1 for value in integer_fields):
            raise ValueError("event counts and durations must be positive")


@dataclass(frozen=True)
class DevelopmentalEventState:
    rolling: torch.Tensor
    bracing: torch.Tensor
    raised: torch.Tensor
    upright: torch.Tensor
    independent_standing: torch.Tensor


class SustainedDevelopmentalEvents:
    """Track milestones only after their conditions persist continuously."""

    event_names = (
        "rolling",
        "bracing",
        "raised",
        "upright",
        "independent_standing",
    )

    def __init__(
        self,
        num_envs: int,
        device: torch.device | str,
        config: DevelopmentalEventConfig | None = None,
    ) -> None:
        if num_envs < 1:
            raise ValueError("event tracker needs at least one environment")
        self.config = config or DevelopmentalEventConfig()
        self.num_envs = num_envs
        self.device = torch.device(device)
        self.counts = {
            name: torch.zeros(num_envs, dtype=torch.long, device=self.device)
            for name in self.event_names
        }
        self.achieved = {
            name: torch.zeros(num_envs, dtype=torch.bool, device=self.device)
            for name in self.event_names
        }

    def reset(self, env_ids: torch.Tensor) -> None:
        for name in self.event_names:
            self.counts[name][env_ids] = 0
            self.achieved[name][env_ids] = False

    def _accumulate(self, name: str, condition: torch.Tensor, required: int) -> torch.Tensor:
        if condition.shape != (self.num_envs,):
            raise ValueError(f"{name} condition must have shape ({self.num_envs},)")
        self.counts[name] = torch.where(
            condition,
            self.counts[name] + 1,
            torch.zeros_like(self.counts[name]),
        )
        self.achieved[name] |= self.counts[name] >= required
        return self.achieved[name]

    def update(
        self,
        *,
        orientation_change_rad: torch.Tensor,
        support_contact_count: torch.Tensor,
        foot_contact_count: torch.Tensor,
        base_height: torch.Tensor,
        upright_score: torch.Tensor,
        base_speed: torch.Tensor,
        assistance_fraction: float | torch.Tensor,
    ) -> DevelopmentalEventState:
        cfg = self.config
        shape = (self.num_envs,)
        signals = (
            orientation_change_rad,
            support_contact_count,
            foot_contact_count,
            base_height,
            upright_score,
            base_speed,
        )
        if any(signal.shape != shape for signal in signals):
            raise ValueError(f"all event signals must have shape {shape}")
        assistance = torch.as_tensor(
            assistance_fraction, device=self.device, dtype=base_height.dtype
        )
        rolling = self._accumulate(
            "rolling",
            (orientation_change_rad >= cfg.roll_angle_rad)
            & (base_height >= cfg.rolling_min_height),
            cfg.roll_steps,
        )
        bracing = self._accumulate(
            "bracing",
            (support_contact_count >= cfg.support_contact_count)
            & (base_height >= cfg.bracing_min_height)
            & (
                orientation_change_rad
                >= cfg.bracing_min_orientation_change_rad
            ),
            # Contact that was already present in the sampled reset pose is not
            # evidence of learned bracing. Require a small, sustained body
            # reorientation, but keep this milestone distinct from a full roll.
            # This makes ground-level elbow/foot support measurable without
            # accidentally turning it into the later raised-body milestone.
            cfg.brace_steps,
        )
        raised = self._accumulate(
            "raised", base_height >= cfg.raised_height, cfg.raised_steps
        )
        upright_condition = (
            (base_height >= cfg.standing_height)
            & (upright_score >= cfg.standing_upright_score)
        )
        upright = self._accumulate("upright", upright_condition, cfg.upright_steps)
        independent = self._accumulate(
            "independent_standing",
            upright_condition
            & (base_speed <= cfg.standing_max_speed)
            & (foot_contact_count >= cfg.foot_contact_count)
            & (assistance <= 0.0),
            cfg.independent_standing_steps,
        )
        return DevelopmentalEventState(rolling, bracing, raised, upright, independent)

    def fractions(self) -> dict[str, torch.Tensor]:
        return {
            name: achieved.float().mean()
            for name, achieved in self.achieved.items()
        }
