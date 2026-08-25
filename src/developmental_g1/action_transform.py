"""Tensor action maturation applied before PBHC's residual PD controller."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import torch

from .maturation import MaturationStage


class MaturationTransform:
    """Resolve named joint groups and constrain normalized residual actions."""

    def __init__(self, joint_names: Sequence[str], groups: Mapping[str, Sequence[str]]) -> None:
        self.joint_names = tuple(joint_names)
        if len(self.joint_names) != len(set(self.joint_names)):
            raise ValueError("joint names must be unique")
        name_to_index = {name: index for index, name in enumerate(self.joint_names)}
        resolved: dict[str, tuple[int, ...]] = {}
        for group_name, names in groups.items():
            if not names:
                raise ValueError(f"joint group {group_name!r} is empty")
            try:
                indices = tuple(name_to_index[name] for name in names)
            except KeyError as error:
                raise ValueError(f"unknown joint {error.args[0]!r} in group {group_name!r}") from error
            if len(indices) != len(set(indices)):
                raise ValueError(f"joint group {group_name!r} contains duplicates")
            resolved[group_name] = indices
        self.groups = resolved

    def parameters(
        self, stage: MaturationStage, *, device: torch.device | str, dtype: torch.dtype
    ) -> tuple[torch.Tensor, torch.Tensor]:
        mask = torch.zeros(len(self.joint_names), device=device, dtype=dtype)
        for group_name in stage.enabled_groups:
            if group_name not in self.groups:
                raise ValueError(f"stage {stage.name!r} references unknown group {group_name!r}")
            mask[list(self.groups[group_name])] = 1.0
        action_range = mask * stage.action_range
        return mask, action_range

    def apply(
        self, raw_actions: torch.Tensor, stage: MaturationStage
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        if raw_actions.ndim != 2 or raw_actions.shape[1] != len(self.joint_names):
            raise ValueError(
                f"expected [batch, {len(self.joint_names)}] actions, got {tuple(raw_actions.shape)}"
            )
        mask, action_range = self.parameters(
            stage, device=raw_actions.device, dtype=raw_actions.dtype
        )
        executed = torch.tanh(raw_actions) * action_range
        return executed, mask, action_range
