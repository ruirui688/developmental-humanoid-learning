"""Competence-gated motor maturation independent of any simulator.

The controller changes software action capability only. Mechanical joint,
velocity, and torque limits remain the simulator/hardware controller's job.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from bisect import bisect_right
from typing import Sequence


@dataclass(frozen=True)
class MaturationStage:
    """Software capability available at one developmental stage."""

    name: str
    enabled_groups: tuple[str, ...]
    action_range: float
    exploration_scale: float

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("stage name must not be empty")
        if not self.enabled_groups:
            raise ValueError(f"stage {self.name!r} must enable at least one joint group")
        for field_name in ("action_range", "exploration_scale"):
            value = getattr(self, field_name)
            if not 0.0 < value <= 1.0:
                raise ValueError(f"{field_name} must be in (0, 1], got {value}")


@dataclass(frozen=True)
class CompetenceSample:
    """Normalized metrics accumulated over one evaluation window."""

    survival: float
    upright: float
    low_risk: float
    low_saturation: float
    schema_accuracy: float
    fall_rate: float

    def __post_init__(self) -> None:
        for field_name, value in asdict(self).items():
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{field_name} must be in [0, 1], got {value}")


@dataclass(frozen=True)
class MaturationConfig:
    """Transition thresholds with hysteresis and dwell-time protection."""

    promotion_score: float = 0.78
    demotion_score: float = 0.52
    promotion_windows: int = 3
    demotion_windows: int = 2
    minimum_dwell_windows: int = 5
    maximum_promotion_fall_rate: float = 0.08
    forced_demotion_fall_rate: float = 0.25
    promotion_survival: float = 0.80
    promotion_upright: float = 0.85
    promotion_low_risk: float = 0.85
    promotion_low_saturation: float = 0.90
    promotion_schema_accuracy: float = 0.70
    demotion_survival: float = 0.45
    demotion_upright: float = 0.55
    demotion_low_risk: float = 0.55
    demotion_low_saturation: float = 0.60
    demotion_schema_accuracy: float = 0.35
    survival_weight: float = 0.25
    upright_weight: float = 0.25
    low_risk_weight: float = 0.20
    low_saturation_weight: float = 0.10
    schema_accuracy_weight: float = 0.20

    def __post_init__(self) -> None:
        if not 0.0 <= self.demotion_score < self.promotion_score <= 1.0:
            raise ValueError("scores must satisfy 0 <= demotion < promotion <= 1")
        if self.promotion_windows < 1 or self.demotion_windows < 1:
            raise ValueError("transition windows must be positive")
        if self.minimum_dwell_windows < 0:
            raise ValueError("minimum_dwell_windows must be non-negative")
        if not 0.0 <= self.maximum_promotion_fall_rate <= self.forced_demotion_fall_rate <= 1.0:
            raise ValueError("fall thresholds are inconsistent")
        threshold_pairs = (
            (self.demotion_survival, self.promotion_survival),
            (self.demotion_upright, self.promotion_upright),
            (self.demotion_low_risk, self.promotion_low_risk),
            (self.demotion_low_saturation, self.promotion_low_saturation),
            (self.demotion_schema_accuracy, self.promotion_schema_accuracy),
        )
        if any(not 0.0 <= down < up <= 1.0 for down, up in threshold_pairs):
            raise ValueError("each metric must have 0 <= demotion < promotion <= 1")
        weights = (
            self.survival_weight,
            self.upright_weight,
            self.low_risk_weight,
            self.low_saturation_weight,
            self.schema_accuracy_weight,
        )
        if any(weight < 0.0 for weight in weights) or abs(sum(weights) - 1.0) > 1e-9:
            raise ValueError("competence weights must be non-negative and sum to one")


@dataclass(frozen=True)
class StageTransition:
    previous_stage: str
    next_stage: str
    direction: str
    competence_score: float
    fall_rate: float


class MaturationController:
    """Global stage controller updated from held-out competence windows."""

    def __init__(
        self,
        stages: Sequence[MaturationStage],
        config: MaturationConfig | None = None,
    ) -> None:
        if not stages:
            raise ValueError("at least one maturation stage is required")
        names = [stage.name for stage in stages]
        if len(names) != len(set(names)):
            raise ValueError("maturation stage names must be unique")
        self.stages = tuple(stages)
        self.config = config or MaturationConfig()
        self.stage_index = 0
        self.windows_in_stage = 0
        self.promotion_streak = 0
        self.demotion_streak = 0
        self.last_score = 0.0

    @property
    def stage(self) -> MaturationStage:
        return self.stages[self.stage_index]

    @property
    def normalized_stage(self) -> float:
        if len(self.stages) == 1:
            return 1.0
        return self.stage_index / (len(self.stages) - 1)

    def competence_score(self, sample: CompetenceSample) -> float:
        cfg = self.config
        return (
            cfg.survival_weight * sample.survival
            + cfg.upright_weight * sample.upright
            + cfg.low_risk_weight * sample.low_risk
            + cfg.low_saturation_weight * sample.low_saturation
            + cfg.schema_accuracy_weight * sample.schema_accuracy
        )

    def observe(self, sample: CompetenceSample) -> StageTransition | None:
        """Consume one evaluation window and possibly change capability stage."""

        cfg = self.config
        score = self.competence_score(sample)
        self.last_score = score
        self.windows_in_stage += 1

        can_promote = (
            self.stage_index < len(self.stages) - 1
            and score >= cfg.promotion_score
            and sample.fall_rate <= cfg.maximum_promotion_fall_rate
            and sample.survival >= cfg.promotion_survival
            and sample.upright >= cfg.promotion_upright
            and sample.low_risk >= cfg.promotion_low_risk
            and sample.low_saturation >= cfg.promotion_low_saturation
            and sample.schema_accuracy >= cfg.promotion_schema_accuracy
        )
        should_demote = (
            self.stage_index > 0
            and (
                score <= cfg.demotion_score
                or sample.fall_rate >= cfg.forced_demotion_fall_rate
                or sample.survival <= cfg.demotion_survival
                or sample.upright <= cfg.demotion_upright
                or sample.low_risk <= cfg.demotion_low_risk
                or sample.low_saturation <= cfg.demotion_low_saturation
                or sample.schema_accuracy <= cfg.demotion_schema_accuracy
            )
        )
        self.promotion_streak = self.promotion_streak + 1 if can_promote else 0
        self.demotion_streak = self.demotion_streak + 1 if should_demote else 0

        if self.windows_in_stage < cfg.minimum_dwell_windows:
            return None
        if self.demotion_streak >= cfg.demotion_windows:
            return self._transition(-1, score, sample.fall_rate)
        if self.promotion_streak >= cfg.promotion_windows:
            return self._transition(1, score, sample.fall_rate)
        return None

    def follow_fixed_schedule(
        self, environment_steps: int, transition_steps: Sequence[int]
    ) -> StageTransition | None:
        """Select the stage from pre-registered cumulative environment steps."""

        if environment_steps < 0:
            raise ValueError("environment_steps must be non-negative")
        thresholds = tuple(int(step) for step in transition_steps)
        if len(thresholds) != len(self.stages) - 1:
            raise ValueError("fixed schedule needs exactly one threshold per transition")
        if any(step <= 0 for step in thresholds) or any(
            left >= right for left, right in zip(thresholds, thresholds[1:])
        ):
            raise ValueError("fixed schedule thresholds must be positive and increasing")
        target_index = bisect_right(thresholds, environment_steps)
        if target_index == self.stage_index:
            return None
        previous = self.stage.name
        self.stage_index = target_index
        self.windows_in_stage = 0
        self.promotion_streak = 0
        self.demotion_streak = 0
        return StageTransition(
            previous_stage=previous,
            next_stage=self.stage.name,
            direction="fixed_schedule",
            competence_score=self.last_score,
            fall_rate=0.0,
        )

    def _transition(self, delta: int, score: float, fall_rate: float) -> StageTransition:
        previous = self.stage.name
        self.stage_index += delta
        self.windows_in_stage = 0
        self.promotion_streak = 0
        self.demotion_streak = 0
        return StageTransition(
            previous_stage=previous,
            next_stage=self.stage.name,
            direction="promotion" if delta > 0 else "demotion",
            competence_score=score,
            fall_rate=fall_rate,
        )

    def state_dict(self) -> dict[str, int | float]:
        return {
            "stage_index": self.stage_index,
            "windows_in_stage": self.windows_in_stage,
            "promotion_streak": self.promotion_streak,
            "demotion_streak": self.demotion_streak,
            "last_score": self.last_score,
        }

    def load_state_dict(self, state: dict[str, int | float]) -> None:
        stage_index = int(state["stage_index"])
        if not 0 <= stage_index < len(self.stages):
            raise ValueError(f"invalid stage_index {stage_index}")
        self.stage_index = stage_index
        self.windows_in_stage = int(state["windows_in_stage"])
        self.promotion_streak = int(state["promotion_streak"])
        self.demotion_streak = int(state["demotion_streak"])
        self.last_score = float(state["last_score"])
