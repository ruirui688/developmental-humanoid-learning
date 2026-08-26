from developmental_g1.developmental_phase_gate import (
    DevelopmentalPhaseGate,
    PhaseEvidence,
    PhaseGateConfig,
)


def evidence(**overrides):
    values = dict(
        schema_accuracy=0.8,
        rolling=0.8,
        bracing=0.8,
        rolling_and_bracing=0.8,
        raised=0.8,
        upright=0.8,
        independent_standing=0.0,
        safe_fraction=0.95,
        low_saturation_fraction=0.95,
    )
    values.update(overrides)
    return PhaseEvidence(**values)


def test_gate_checks_only_current_developmental_capability():
    gate = DevelopmentalPhaseGate(PhaseGateConfig(confirmation_windows=1))
    transition = gate.observe(evidence(rolling=0.0, raised=0.0, upright=0.0))
    assert transition.advanced
    assert gate.stage == 1


def test_gate_requires_repeated_safe_evidence():
    gate = DevelopmentalPhaseGate(PhaseGateConfig(confirmation_windows=2))
    assert not gate.observe(evidence()).advanced
    assert gate.observe(evidence()).advanced
    assert not gate.observe(evidence(safe_fraction=0.2)).advanced
    assert gate.confirmation_streak == 0


def test_later_phase_cannot_skip_intermediate_phase():
    gate = DevelopmentalPhaseGate(PhaseGateConfig(confirmation_windows=1))
    transition = gate.observe(evidence(schema_accuracy=0.0, rolling=1.0, raised=1.0))
    assert not transition.advanced
    assert gate.stage == 0


def test_state_round_trip():
    first = DevelopmentalPhaseGate(PhaseGateConfig(confirmation_windows=1))
    first.observe(evidence())
    second = DevelopmentalPhaseGate(PhaseGateConfig(confirmation_windows=1))
    second.load_state_dict(first.state_dict())
    assert second.state_dict() == first.state_dict()
