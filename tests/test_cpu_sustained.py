"""Tests for the explicitly separate persistent-failure gate variant."""

from dataclasses import replace

import pytest

from developmental_control.maturation import CompetenceGate, GateConfig, GateEvidence
from developmental_control.sustained import SustainedCompetenceGate
from developmental_control.validate import STAGES


GOOD = GateEvidence(0.001, 0.01, 0.2, 0.005, True, True)
BAD_TRACKING = replace(GOOD, tracking_rmse=0.05)


def promoted(gate):
    for _ in range(6):
        gate.observe(GOOD)
    assert gate.level == 2
    return gate


def test_persistent_tracking_failure_withdraws_only_opt_in_variant():
    original = promoted(CompetenceGate(STAGES, GateConfig()))
    variant = promoted(SustainedCompetenceGate(STAGES))
    for index in range(3):
        assert original.observe(BAD_TRACKING) == "hold"
        assert variant.observe(BAD_TRACKING) == ("retreat" if index == 2 else "hold")
    assert original.level == 2
    assert variant.level == 1
    assert variant.events[-1]["reason"] == "sustained_competence_failure"
    assert variant.events[-1]["performance_failure_count"] == 3
    assert variant.performance_failure_count == variant.pass_count == variant.dwell_windows == 0
    assert [variant.observe(GOOD) for _ in range(3)] == ["hold", "hold", "promote"]


def test_success_interrupts_failure_streak_and_does_not_reduce_permissions():
    gate = promoted(SustainedCompetenceGate(STAGES))
    for evidence in (BAD_TRACKING, BAD_TRACKING, GOOD, BAD_TRACKING, BAD_TRACKING):
        assert gate.observe(evidence) == "hold"
    assert gate.level == 2
    assert gate.performance_failure_count == 2
    assert gate.observe(BAD_TRACKING) == "retreat"


def test_original_critical_withdrawal_remains_immediate_and_resets_streak():
    gate = promoted(SustainedCompetenceGate(STAGES))
    gate.observe(BAD_TRACKING)
    gate.observe(BAD_TRACKING)
    assert gate.observe(replace(GOOD, prediction_rmse=0.006)) == "retreat"
    assert gate.events[-1]["reason"] == "prediction_mismatch"
    assert not gate.events[-1]["sustained_failure_triggered"]
    assert gate.performance_failure_count == 0
    assert [gate.observe(BAD_TRACKING) for _ in range(3)] == ["hold", "hold", "retreat"]
    assert gate.level == 0


@pytest.mark.parametrize("failed", [BAD_TRACKING, replace(GOOD, recovered=False), replace(GOOD, peak_speed=1.1)])
def test_lowest_level_failure_is_recorded_without_fabricating_a_retreat(failed):
    gate = SustainedCompetenceGate(STAGES)
    assert [gate.observe(failed) for _ in range(3)] == ["hold"] * 3
    assert gate.level == 0
    assert gate.events[-1]["sustained_failure_triggered"]
    assert gate.events[-1]["level_before"] == gate.events[-1]["level_after"] == 0


@pytest.mark.parametrize("value", [True, 0, -1, 1.5, None])
def test_invalid_failure_window_count_is_rejected(value):
    with pytest.raises(ValueError, match="positive integer"):
        SustainedCompetenceGate(STAGES, failure_windows=value)
