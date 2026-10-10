"""Opt-in withdrawal after persistent performance failure; no model fitting.

The original competence gate remains the comparator. This variant uses its
existing competence thresholds and adds a fixed consecutive-failure rule.
"""

from __future__ import annotations

from numbers import Integral

from .maturation import CompetenceGate, GateConfig, GateEvidence, StagePermission


class SustainedCompetenceGate(CompetenceGate):
    def __init__(self, stages: tuple[StagePermission, ...],
                 config: GateConfig = GateConfig(), failure_windows: int = 3):
        if isinstance(failure_windows, bool) or not isinstance(failure_windows, Integral) or failure_windows < 1:
            raise ValueError("failure_windows must be a positive integer")
        super().__init__(stages, config)
        self.failure_windows = int(failure_windows)
        self.performance_failure_count = 0

    def observe(self, evidence: GateEvidence):
        super().observe(evidence)
        event = self.events[-1]
        # Critical failures already withdraw immediately in the original gate.
        # Only otherwise-valid, unsuccessful competence windows accumulate.
        if event["reason"] == "competence_failed":
            self.performance_failure_count += 1
        else:
            self.performance_failure_count = 0
        observed_count = self.performance_failure_count
        triggered = observed_count >= self.failure_windows
        if triggered:
            self.level = max(0, self.level - 1)
            self.pass_count = 0
            self.dwell_windows = 0
            self.performance_failure_count = 0
            event.update(
                level_after=self.level,
                decision="retreat" if self.level < event["level_before"] else "hold",
                reason="sustained_competence_failure",
                pass_count=0,
                dwell_windows=0,
            )
        event.update(
            performance_failure_count=observed_count,
            performance_failure_count_after=self.performance_failure_count,
            failure_windows=self.failure_windows,
            sustained_failure_triggered=triggered,
        )
        return event["decision"]
