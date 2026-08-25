"""Episode-level held-out competence metrics for G1 maturation decisions."""

from __future__ import annotations

from dataclasses import dataclass

import torch

from .maturation import CompetenceSample


@dataclass(frozen=True)
class CompetenceWindowResult:
    """A gate sample plus auditable counts from one fixed evaluation bank."""

    sample: CompetenceSample
    episodes: int
    successful_episodes: int
    fallen_episodes: int
    evaluation_steps: int


class CompetenceWindow:
    """Accumulate fixed-horizon evaluation signals without training rollouts."""

    def __init__(self, required_episodes: int) -> None:
        if required_episodes < 1:
            raise ValueError("required_episodes must be positive")
        self.required_episodes = required_episodes
        self.episodes = 0
        self.successful_episodes = 0
        self.fallen_episodes = 0
        self.evaluation_steps = 0
        self.upright_sum = 0.0
        self.low_risk_sum = 0.0
        self.low_saturation_sum = 0.0
        self.schema_accuracy_sum = 0.0
        self.schema_count = 0
        self.signal_count = 0

    @property
    def complete(self) -> bool:
        return self.episodes >= self.required_episodes

    def record_step(
        self,
        *,
        episode_done: torch.Tensor,
        episode_fell: torch.Tensor,
        upright: torch.Tensor,
        low_risk: torch.Tensor,
        low_saturation: torch.Tensor,
        schema_accuracy: torch.Tensor,
        schema_valid: torch.Tensor,
    ) -> None:
        """Record one vectorized step from a deterministic evaluation rollout."""

        tensors = (
            episode_done,
            episode_fell,
            upright,
            low_risk,
            low_saturation,
            schema_accuracy,
            schema_valid,
        )
        if any(tensor.ndim != 1 for tensor in tensors):
            raise ValueError("competence signals must be one-dimensional")
        batch_size = episode_done.numel()
        if any(tensor.numel() != batch_size for tensor in tensors):
            raise ValueError("competence signals must share a batch size")
        if episode_done.dtype != torch.bool or episode_fell.dtype != torch.bool:
            raise ValueError("episode_done and episode_fell must be boolean")
        if schema_valid.dtype != torch.bool:
            raise ValueError("schema_valid must be boolean")
        if torch.any(episode_fell & ~episode_done):
            raise ValueError("a fall must also end its evaluation episode")
        for name, tensor in (
            ("upright", upright),
            ("low_risk", low_risk),
            ("low_saturation", low_saturation),
            ("schema_accuracy", schema_accuracy),
        ):
            if not torch.all(torch.isfinite(tensor)):
                raise ValueError(f"{name} contains a non-finite value")
            if torch.any((tensor < 0.0) | (tensor > 1.0)):
                raise ValueError(f"{name} must be normalized to [0, 1]")

        remaining = self.required_episodes - self.episodes
        done_indices = episode_done.nonzero(as_tuple=False).flatten()[:remaining]
        accepted_falls = episode_fell[done_indices]
        completed = int(done_indices.numel())
        falls = int(accepted_falls.sum().item())
        self.episodes += completed
        self.fallen_episodes += falls
        self.successful_episodes += completed - falls

        self.evaluation_steps += batch_size
        self.signal_count += batch_size
        self.upright_sum += float(upright.sum().item())
        self.low_risk_sum += float(low_risk.sum().item())
        self.low_saturation_sum += float(low_saturation.sum().item())
        self.schema_accuracy_sum += float(schema_accuracy[schema_valid].sum().item())
        self.schema_count += int(schema_valid.sum().item())

    def result(self) -> CompetenceWindowResult:
        if not self.complete:
            raise RuntimeError(
                f"competence window incomplete: {self.episodes}/{self.required_episodes} episodes"
            )
        if self.signal_count == 0 or self.schema_count == 0:
            raise RuntimeError("competence window contains no step signals")
        survival = self.successful_episodes / self.episodes
        fall_rate = self.fallen_episodes / self.episodes
        sample = CompetenceSample(
            survival=survival,
            upright=self.upright_sum / self.signal_count,
            low_risk=self.low_risk_sum / self.signal_count,
            low_saturation=self.low_saturation_sum / self.signal_count,
            schema_accuracy=self.schema_accuracy_sum / self.schema_count,
            fall_rate=fall_rate,
        )
        return CompetenceWindowResult(
            sample=sample,
            episodes=self.episodes,
            successful_episodes=self.successful_episodes,
            fallen_episodes=self.fallen_episodes,
            evaluation_steps=self.evaluation_steps,
        )
