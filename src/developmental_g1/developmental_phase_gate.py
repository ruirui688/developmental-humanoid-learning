"""Evidence gate for sequential, ground-start motor development."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PhaseGateConfig:
    metric_names: tuple[str, ...] = (
        "schema_accuracy",
        "rolling_and_bracing",
        "raised",
        "upright",
        "independent_standing",
    )
    metric_thresholds: tuple[float, ...] = (0.15, 0.50, 0.50, 0.70, 1.0)
    required_safe_fraction: float = 0.90
    required_low_saturation_fraction: float = 0.90
    confirmation_windows: int = 3

    def __post_init__(self) -> None:
        if len(self.metric_names) != len(self.metric_thresholds):
            raise ValueError("phase metric names and thresholds must align")
        if any(not 0.0 <= value <= 1.0 for value in self.metric_thresholds):
            raise ValueError("phase metric thresholds must be in [0, 1]")
        if not 0.0 <= self.required_safe_fraction <= 1.0:
            raise ValueError("safe fraction must be in [0, 1]")
        if not 0.0 <= self.required_low_saturation_fraction <= 1.0:
            raise ValueError("low-saturation fraction must be in [0, 1]")
        if self.confirmation_windows < 1:
            raise ValueError("confirmation windows must be positive")


@dataclass(frozen=True)
class PhaseEvidence:
    schema_accuracy: float
    rolling: float
    bracing: float
    rolling_and_bracing: float
    raised: float
    upright: float
    independent_standing: float
    safe_fraction: float
    low_saturation_fraction: float

    def __post_init__(self) -> None:
        for name, value in self.__dict__.items():
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be in [0, 1]")


@dataclass(frozen=True)
class PhaseTransition:
    previous_stage: int
    stage: int
    advanced: bool
    metric_name: str
    metric_value: float
    threshold: float
    confirmation_streak: int
    reason: str


class DevelopmentalPhaseGate:
    """Advance one phase only after repeated safe phase-specific evidence."""

    def __init__(self, config: PhaseGateConfig | None = None) -> None:
        self.config = config or PhaseGateConfig()
        self.stage = 0
        self.confirmation_streak = 0

    def observe(self, evidence: PhaseEvidence) -> PhaseTransition:
        cfg = self.config
        metric_name = cfg.metric_names[self.stage]
        threshold = cfg.metric_thresholds[self.stage]
        metric_value = float(getattr(evidence, metric_name))
        competent = (
            metric_value >= threshold
            and evidence.safe_fraction >= cfg.required_safe_fraction
            and evidence.low_saturation_fraction
            >= cfg.required_low_saturation_fraction
        )
        self.confirmation_streak = self.confirmation_streak + 1 if competent else 0
        previous_stage = self.stage
        if (
            self.confirmation_streak >= cfg.confirmation_windows
            and self.stage < len(cfg.metric_names) - 1
        ):
            self.stage += 1
            self.confirmation_streak = 0
        advanced = self.stage > previous_stage
        return PhaseTransition(
            previous_stage=previous_stage,
            stage=self.stage,
            advanced=advanced,
            metric_name=metric_name,
            metric_value=metric_value,
            threshold=threshold,
            confirmation_streak=self.confirmation_streak,
            reason=(
                "repeated safe phase competence"
                if advanced
                else "insufficient phase-specific competence evidence"
            ),
        )

    def state_dict(self) -> dict[str, int]:
        return {"stage": self.stage, "confirmation_streak": self.confirmation_streak}

    def load_state_dict(self, state: dict) -> None:
        stage = int(state["stage"])
        if not 0 <= stage < len(self.config.metric_names):
            raise ValueError("phase gate checkpoint stage is invalid")
        self.stage = stage
        self.confirmation_streak = int(state.get("confirmation_streak", 0))
