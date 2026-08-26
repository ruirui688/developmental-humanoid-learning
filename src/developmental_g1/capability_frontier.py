"""Adaptive capability frontier for self-paced ground-start development.

The frontier never prescribes a get-up trajectory. It freezes goals just beyond
what the current policy has demonstrated on held-out episodes, and advances
only after repeated low-risk evidence.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class FrontierConfig:
    floor_height: float = 0.20
    final_height: float = 0.76
    initial_upright_score: float = 0.0
    final_upright_score: float = 0.95
    height_margin: float = 0.03
    upright_margin: float = 0.04
    required_success_fraction: float = 0.70
    required_safe_fraction: float = 0.90
    maximum_saturation_fraction: float = 0.10
    required_schema_accuracy: float = 0.60
    confirmation_windows: int = 3

    def __post_init__(self) -> None:
        if not 0.0 <= self.floor_height < self.final_height:
            raise ValueError("frontier heights must be ordered")
        if not 0.0 <= self.initial_upright_score < self.final_upright_score <= 1.0:
            raise ValueError("frontier upright scores must be ordered in [0, 1]")
        if self.height_margin <= 0.0 or self.upright_margin <= 0.0:
            raise ValueError("frontier margins must be positive")
        for name in (
            "required_success_fraction",
            "required_safe_fraction",
            "maximum_saturation_fraction",
            "required_schema_accuracy",
        ):
            if not 0.0 <= getattr(self, name) <= 1.0:
                raise ValueError(f"{name} must be in [0, 1]")
        if self.confirmation_windows < 1:
            raise ValueError("confirmation_windows must be positive")


@dataclass(frozen=True)
class FrontierEvidence:
    """Held-out distribution summary; quantiles are not training-rollout maxima."""

    height_quantile: float
    upright_quantile: float
    height_target_success_fraction: float
    upright_target_success_fraction: float
    safe_fraction: float
    saturation_fraction: float
    schema_accuracy: float
    episodes: int

    def __post_init__(self) -> None:
        if self.height_quantile < 0.0:
            raise ValueError("height_quantile cannot be negative")
        for name in (
            "upright_quantile",
            "height_target_success_fraction",
            "upright_target_success_fraction",
            "safe_fraction",
            "saturation_fraction",
            "schema_accuracy",
        ):
            if not 0.0 <= getattr(self, name) <= 1.0:
                raise ValueError(f"{name} must be in [0, 1]")
        if self.episodes < 1:
            raise ValueError("frontier evidence needs at least one episode")


@dataclass(frozen=True)
class FrontierUpdate:
    previous_height_target: float
    height_target: float
    previous_upright_target: float
    upright_target: float
    advanced: bool
    reason: str


class CapabilityFrontier:
    """Monotone, evidence-gated targets immediately beyond demonstrated ability."""

    def __init__(self, config: FrontierConfig | None = None) -> None:
        self.config = config or FrontierConfig()
        self.height_target = self.config.floor_height
        self.upright_target = self.config.initial_upright_score
        self.confirmation_streak = 0
        self.calibrated = False

    @property
    def progress(self) -> float:
        cfg = self.config
        height_progress = (self.height_target - cfg.floor_height) / (
            cfg.final_height - cfg.floor_height
        )
        upright_progress = (
            self.upright_target - cfg.initial_upright_score
        ) / (cfg.final_upright_score - cfg.initial_upright_score)
        return max(0.0, min(1.0, 0.5 * (height_progress + upright_progress)))

    def calibrate(self, evidence: FrontierEvidence) -> FrontierUpdate:
        """Set the first challenge from passive/random-policy reachable states."""

        if self.calibrated:
            raise RuntimeError("capability frontier is already calibrated")
        previous_height = self.height_target
        previous_upright = self.upright_target
        self.height_target = min(
            max(self.config.floor_height, evidence.height_quantile + self.config.height_margin),
            self.config.final_height,
        )
        self.upright_target = min(
            max(
                self.config.initial_upright_score,
                evidence.upright_quantile + self.config.upright_margin,
            ),
            self.config.final_upright_score,
        )
        self.calibrated = True
        return FrontierUpdate(
            previous_height,
            self.height_target,
            previous_upright,
            self.upright_target,
            True,
            "passive calibration plus one margin",
        )

    def observe(self, evidence: FrontierEvidence) -> FrontierUpdate:
        if not self.calibrated:
            raise RuntimeError("calibrate the capability frontier before training")
        previous_height = self.height_target
        previous_upright = self.upright_target
        cfg = self.config
        competent = (
            evidence.height_target_success_fraction >= cfg.required_success_fraction
            and evidence.upright_target_success_fraction >= cfg.required_success_fraction
            and evidence.safe_fraction >= cfg.required_safe_fraction
            and evidence.saturation_fraction <= cfg.maximum_saturation_fraction
            and evidence.schema_accuracy >= cfg.required_schema_accuracy
        )
        self.confirmation_streak = self.confirmation_streak + 1 if competent else 0
        if self.confirmation_streak < cfg.confirmation_windows:
            return FrontierUpdate(
                previous_height,
                self.height_target,
                previous_upright,
                self.upright_target,
                False,
                "insufficient repeated low-risk competence evidence",
            )
        self.confirmation_streak = 0
        self.height_target = min(
            max(self.height_target, evidence.height_quantile + cfg.height_margin),
            cfg.final_height,
        )
        self.upright_target = min(
            max(self.upright_target, evidence.upright_quantile + cfg.upright_margin),
            cfg.final_upright_score,
        )
        advanced = (
            self.height_target > previous_height
            or self.upright_target > previous_upright
        )
        return FrontierUpdate(
            previous_height,
            self.height_target,
            previous_upright,
            self.upright_target,
            advanced,
            "held-out capability quantile plus one margin" if advanced else "final frontier reached",
        )

    def observe_height_only(
        self,
        evidence: FrontierEvidence,
        *,
        ceiling: float,
        required_success_fraction: float | None = None,
    ) -> FrontierUpdate:
        """Advance a rise subgoal without demanding later upright competence."""

        if not self.calibrated:
            raise RuntimeError("calibrate the capability frontier before training")
        if not self.config.floor_height < ceiling <= self.config.final_height:
            raise ValueError("height-only frontier ceiling is out of bounds")
        required_success = (
            self.config.required_success_fraction
            if required_success_fraction is None
            else float(required_success_fraction)
        )
        if not 0.0 <= required_success <= 1.0:
            raise ValueError("height-only required success fraction must be in [0, 1]")
        previous_height = self.height_target
        previous_upright = self.upright_target
        cfg = self.config
        competent = (
            evidence.height_target_success_fraction >= required_success
            and evidence.safe_fraction >= cfg.required_safe_fraction
            and evidence.saturation_fraction <= cfg.maximum_saturation_fraction
        )
        self.confirmation_streak = self.confirmation_streak + 1 if competent else 0
        if self.confirmation_streak < cfg.confirmation_windows:
            return FrontierUpdate(
                previous_height,
                self.height_target,
                previous_upright,
                self.upright_target,
                False,
                "insufficient repeated safe height competence evidence",
            )
        self.confirmation_streak = 0
        evidence_target = evidence.height_quantile + cfg.height_margin
        one_step_target = self.height_target + cfg.height_margin
        self.height_target = min(
            max(self.height_target, min(evidence_target, one_step_target)),
            ceiling,
        )
        advanced = self.height_target > previous_height
        return FrontierUpdate(
            previous_height,
            self.height_target,
            previous_upright,
            self.upright_target,
            advanced,
            "held-out height quantile plus one margin"
            if advanced
            else "rise frontier ceiling reached",
        )

    def state_dict(self) -> dict[str, float | int | bool]:
        return {
            "height_target": self.height_target,
            "upright_target": self.upright_target,
            "confirmation_streak": self.confirmation_streak,
            "calibrated": self.calibrated,
            "config": asdict(self.config),
        }

    def load_state_dict(self, state: dict) -> None:
        saved_config = state.get("config")
        if saved_config is not None and saved_config != asdict(self.config):
            raise ValueError("capability frontier config does not match checkpoint")
        height_target = float(state["height_target"])
        upright_target = float(state["upright_target"])
        if not self.config.floor_height <= height_target <= self.config.final_height:
            raise ValueError("checkpoint height frontier is out of bounds")
        if not (
            self.config.initial_upright_score
            <= upright_target
            <= self.config.final_upright_score
        ):
            raise ValueError("checkpoint upright frontier is out of bounds")
        self.height_target = height_target
        self.upright_target = upright_target
        self.confirmation_streak = int(state.get("confirmation_streak", 0))
        self.calibrated = bool(state.get("calibrated", False))
