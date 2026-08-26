"""Policy network with an auxiliary one-step body-schema prediction head."""

from __future__ import annotations

from collections.abc import Sequence

import torch
from torch import nn
from torch.distributions import Normal


def _activation(name: str) -> nn.Module:
    try:
        return getattr(nn, name)()
    except AttributeError as error:
        raise ValueError(f"unknown PyTorch activation {name!r}") from error


class BodySchemaActor(nn.Module):
    """Gaussian actor whose latent predicts the next deployable body state."""

    def __init__(
        self,
        observation_dim: int,
        num_actions: int,
        schema_target_dim: int,
        hidden_dims: Sequence[int],
        schema_hidden_dim: int,
        activation: str,
        init_noise_std: float,
        min_noise_std: float = 0.05,
        max_noise_std: float = 0.5,
    ) -> None:
        super().__init__()
        if not hidden_dims:
            raise ValueError("hidden_dims must not be empty")
        layers: list[nn.Module] = []
        previous = observation_dim
        for hidden in hidden_dims:
            layers.extend((nn.Linear(previous, hidden), _activation(activation)))
            previous = hidden
        self.encoder = nn.Sequential(*layers)
        self.action_head = nn.Linear(previous, num_actions)
        self.schema_head = nn.Sequential(
            nn.Linear(previous + num_actions, schema_hidden_dim),
            _activation(activation),
            nn.Linear(schema_hidden_dim, schema_target_dim),
        )
        self.raw_std = nn.Parameter(init_noise_std * torch.ones(num_actions))
        if not 0.0 < min_noise_std <= max_noise_std:
            raise ValueError("noise std bounds must be positive and ordered")
        self.min_noise_std = min_noise_std
        self.max_noise_std = max_noise_std
        self.noise_scale = 1.0
        self.distribution: Normal | None = None
        Normal.set_default_validate_args = False

    def latent(self, actor_obs: torch.Tensor) -> torch.Tensor:
        return self.encoder(actor_obs)

    def update_distribution(self, actor_obs: torch.Tensor) -> None:
        mean = self.action_head(self.latent(actor_obs))
        std = mean * 0.0 + self.std
        self.distribution = Normal(mean, std)

    def act(self, actor_obs: torch.Tensor, **_kwargs) -> torch.Tensor:
        self.update_distribution(actor_obs)
        assert self.distribution is not None
        return self.distribution.sample()

    def act_inference(self, actor_obs: torch.Tensor) -> torch.Tensor:
        return self.action_head(self.latent(actor_obs))

    def predict_body_schema(
        self, actor_obs: torch.Tensor, executed_actions: torch.Tensor
    ) -> torch.Tensor:
        return self.schema_head(torch.cat((self.latent(actor_obs), executed_actions), dim=-1))

    def reset(self, dones=None) -> None:
        del dones

    @property
    def action_mean(self) -> torch.Tensor:
        assert self.distribution is not None
        return self.distribution.mean

    @property
    def std(self) -> torch.Tensor:
        """Effective exploration std after the current maturation scale."""

        return (self.raw_std * self.noise_scale).clamp(
            min=self.min_noise_std, max=self.max_noise_std
        )

    @property
    def action_std(self) -> torch.Tensor:
        assert self.distribution is not None
        return self.distribution.stddev

    @property
    def entropy(self) -> torch.Tensor:
        assert self.distribution is not None
        return self.distribution.entropy().sum(dim=-1)

    def get_actions_log_prob(self, actions: torch.Tensor) -> torch.Tensor:
        assert self.distribution is not None
        return self.distribution.log_prob(actions).sum(dim=-1)
