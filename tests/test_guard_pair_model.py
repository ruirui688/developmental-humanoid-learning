"""Limited synthetic contracts. No physical calls, real labels or matrix."""
import dis
import inspect
import sys
from dataclasses import FrozenInstanceError

import numpy as np
import pytest

from developmental_physics import local_pair_model as core
from developmental_physics.guard_pair_model import InputMappedDiagonalPairBodyModel, KnownAngleGuard


RANGES = ((-1., 1.), (0., 2.3))
QREF = (.1, -.0005)


def model(basis="known_angle_guard", *, trainable=True):
    return InputMappedDiagonalPairBodyModel(
        QREF, public_joint_ranges=RANGES, input_basis=basis, trainable=trainable,
    )


@pytest.mark.parametrize("q,u,expected,blocked", [
    ((-.97, .03), (-.5, -.5), (0., 0.), (True, True)),
    ((.97, 2.27), (.5, .5), (0., 0.), (True, True)),
    ((-.97, .03), (.5, .5), (.5, .5), (False, False)),
    ((.97, 2.27), (-.5, -.5), (-.5, -.5), (False, False)),
    ((-.97, 2.27), (0., -0.), (0., -0.), (False, False)),
    ((-.969999, .030001), (-.5, -.5), (-.5, -.5), (False, False)),
    ((.969999, 2.269999), (.5, .5), (.5, .5), (False, False)),
    ((0., 1.), (2., -2.), (.5, -.5), (False, False)),
    ((-1.01, -.0005), (-2., 2.), (0., .5), (True, False)),
])
def test_public_rule_boundaries_zero_direction_and_clip(q, u, expected, blocked):
    result = KnownAngleGuard(RANGES).project(q, u)
    assert result.projected_start_nm == expected
    assert result.start_blocked == blocked
    assert result.native_q_rad == q and result.requested_nm == u
    assert all(type(x) is bool for x in result.start_blocked)
    assert all(type(x) is float for x in result.projected_start_nm)


def test_exact_computed_boundaries_and_nearest_interior_float_on_each_axis():
    guard = KnownAngleGuard(RANGES)
    lower = tuple(row[0] + guard.margin_rad for row in RANGES)
    upper = tuple(row[1] - guard.margin_rad for row in RANGES)
    assert guard.project(lower, (-.125, -.125)).start_blocked == (True, True)
    assert guard.project(upper, (.125, .125)).start_blocked == (True, True)
    lower_inside = tuple(float(np.nextafter(x, np.inf)) for x in lower)
    upper_inside = tuple(float(np.nextafter(x, -np.inf)) for x in upper)
    assert guard.project(lower_inside, (-.125, -.125)).start_blocked == (False, False)
    assert guard.project(upper_inside, (.125, .125)).start_blocked == (False, False)


@pytest.mark.parametrize("bad", [
    (0.,), (0., 0., 0.), [[0., 0.]], (True, 0.), ("0", 0.),
    (np.nan, 0.), (np.inf, 0.), (0j, 0.),
])
def test_guard_rejects_nonfinite_non_native_and_wrong_shape(bad):
    guard = KnownAngleGuard(RANGES)
    with pytest.raises(ValueError):
        guard.project(bad, (0., 0.))
    with pytest.raises(ValueError):
        guard.project((0., 0.), bad)


@pytest.mark.parametrize("bad", [
    ((0., 1.),), ((0., 0.), (0., 1.)), ((1., 0.), (0., 1.)),
    ((False, 1.), (0., 1.)), (("0", 1.), (0., 1.)),
    ((0., np.nan), (0., 1.)), ((0., np.inf), (0., 1.)),
])
def test_ranges_are_finite_native_ordered_pairs(bad):
    with pytest.raises(ValueError):
        KnownAngleGuard(bad)


def test_public_configuration_is_owned_immutable_and_diagnostics_are_copies():
    caller_ranges = [[-1., 1.], [0., 2.3]]
    guard = KnownAngleGuard(caller_ranges)
    caller_ranges[0][0] = -99.
    assert guard.public_joint_ranges == RANGES
    with pytest.raises(FrozenInstanceError):
        guard.margin_rad = .1
    with pytest.raises(FrozenInstanceError):
        guard.torque_clip_nm = 1.
    description = guard.spec()
    description["public_joint_ranges_rad"][0][0] = -99.
    assert guard.spec()["public_joint_ranges_rad"][0][0] == -1.


def test_guard_maps_axes_independently_without_reordering_or_qref_clipping():
    guard = KnownAngleGuard(RANGES)
    result = guard.project((-.97, -.0005), (.125, -.25))
    assert result.projected_start_nm == (.125, 0.)
    assert result.start_blocked == (False, True)
    body = model()
    assert body.qref == QREF and body.qref[1] < 0.
    positions, features = body._features(QREF, (.2, -.1), (-.125, -.5))
    assert positions == QREF
    assert features.tolist() == [[.2, 0., -.125, -0., 1.], [-.1, 0., 0., 0., 1.]]


def test_raw_preserves_original_uncapped_features_and_guard_has_matching_cold_coefficients():
    raw, guarded = model("raw_request"), model()
    original = core.DiagonalPairBodyModel(QREF)
    q, v, u = QREF, (.1, .2), (1., -.5)
    assert np.array_equal(raw._features(q, v, u)[1], original._features(q, v, u)[1])
    assert raw.predict(q, v, u) == original.predict(q, v, u)
    assert guarded._features(q, v, u)[1][:, 2].tolist() == [.5, 0.]
    assert np.array_equal(raw.coefficients, guarded.coefficients)
    assert raw.coefficients.tolist() == [[1., 0., .02, 0., 0.]] * 2
    assert raw.covariance.shape == guarded.covariance.shape == (2, 5, 5)
    assert np.array_equal(raw.covariance, np.repeat((100*np.eye(5))[None, :, :], 2, axis=0))


def test_guard_has_no_future_or_actual_input_interface():
    guard, body = KnownAngleGuard(RANGES), model()
    assert list(inspect.signature(guard.project).parameters) == ["q", "u"]
    assert list(inspect.signature(body.predict).parameters) == ["q", "v", "u"]
    before = guard.project(QREF, (-.5, -.5))
    for extra in ("actual_torque", "contact", "environment", "next_q"):
        with pytest.raises(TypeError):
            guard.project(QREF, (-.5, -.5), **{extra: object()})
        with pytest.raises(TypeError):
            body.predict(QREF, (0., 0.), (-.5, -.5), **{extra: object()})
    assert guard.project(QREF, (-.5, -.5)) == before
    assert guard.spec()["physical_queries"] == 0


@pytest.mark.parametrize("basis", ["raw_request", "known_angle_guard"])
def test_generated_rls_labels_use_same_basis_as_predictions_and_prefix_does_not_update(basis):
    body = model(basis)
    q, v, u, label = QREF, (.1, .2), (.375, -.5), (.3, -.1)
    before = body.snapshot()
    expected_features = body._features(q, v, u)[1].tolist()
    expected_prediction = body.predict(q, v, u)
    prefix = body.update(q, v, u, label, phase="prefix", transition_id="synthetic:prefix")
    assert body.snapshot() == before and prefix["committed_scalar_updates"] == 0
    record = body.update(q, v, u, label, transition_id="synthetic:label")
    assert record["features_per_output"] == expected_features
    assert [item["features"] for item in record["output_records"]] == expected_features
    assert record["preupdate_prediction"] == {
        "next_q_rad": list(expected_prediction[0]), "next_v_rad_s": list(expected_prediction[1]),
    }
    assert record["committed_scalar_updates"] == 2
    assert body.update_count == 1 and body.scalar_update_count == 2


@pytest.mark.parametrize("basis", ["raw_request", "known_angle_guard"])
def test_frozen_clone_retains_mapping_initial_coefficients_and_captured_learned_state(basis):
    body = model(basis)
    body.update(QREF, (.1, .2), (.375, -.5), (.3, -.1), transition_id="synthetic:label")
    frozen = body.clone_frozen()
    assert type(frozen) is InputMappedDiagonalPairBodyModel
    assert frozen.input_basis == basis and frozen.public_guard == body.public_guard
    assert not frozen.trainable
    assert frozen.parameter_fingerprint() == body.parameter_fingerprint()
    assert frozen.snapshot()["input_mapping"] == body.snapshot()["input_mapping"]
    assert frozen.snapshot()["initial_coefficients"] == [[1., 0., .02, 0., 0.]] * 2
    assert frozen.qref == QREF and frozen.scalar_update_count == 2
    before = frozen.snapshot()
    with pytest.raises(RuntimeError, match="frozen"):
        frozen.update(QREF, (.1, .2), (.375, -.5), (.3, -.1))
    assert frozen.snapshot() == before
    body.update(QREF, (.1, .2), (.25, .5), (.1, .2), transition_id="synthetic:second")
    assert frozen.snapshot() == before
    assert not frozen._state.theta.flags.writeable and not frozen._state.covariance.flags.writeable
    coefficients = frozen.coefficients
    coefficients[:] = 999.
    assert frozen.snapshot() == before


def test_fingerprints_distinguish_basis_and_public_limits_even_at_equal_parameters():
    raw, guarded = model("raw_request"), model()
    assert raw.parameter_fingerprint() != guarded.parameter_fingerprint()
    other_ranges = InputMappedDiagonalPairBodyModel(
        QREF, public_joint_ranges=((-1.1, 1.), (0., 2.3)), input_basis="known_angle_guard",
    )
    assert guarded.parameter_fingerprint() != other_ranges.parameter_fingerprint()
    for body in (raw, guarded):
        record = body.snapshot()
        guard_spec = record["input_mapping"]["public_guard"]
        assert guard_spec["public_joint_ranges_rad"] == [list(row) for row in RANGES]
        assert guard_spec["angle_margin_rad"] == .03
        assert guard_spec["request_clip_per_axis_nm"] == .5
    assert "start_G" in guarded.snapshot()["features_per_output"][0][2]
    assert raw.snapshot()["features_per_output"][0][2] == "u0"


@pytest.mark.parametrize("basis", ["raw_request", "known_angle_guard"])
@pytest.mark.parametrize("fatal", [False, True])
def test_second_head_failure_preserves_atomic_state_and_exact_ledger(monkeypatch, basis, fatal):
    body = model(basis)
    before = body.snapshot()
    original = body._propose_update
    def fail(index, *args):
        if index == 1:
            raise OSError("synthetic second-head IO") if fatal else ValueError("synthetic second-head proposal")
        return original(index, *args)
    monkeypatch.setattr(body, "_propose_update", fail)
    with pytest.raises(OSError if fatal else core.PairUpdateError) as outcome:
        body.update(QREF, (.1, .2), (.375, -.5), (.3, -.1), transition_id="synthetic:failure")
    ledger = outcome.value.pair_update_accounting if fatal else outcome.value.to_dict()
    assert body.snapshot() == before
    assert ledger["snapshot_after_attempt"] == before and ledger["committed_scalar_updates"] == 0
    assert len(ledger["proposed_outputs"]) == 1 and not ledger["proposed_outputs"][0]["committed"]
    assert ledger["proposed_outputs"][0]["proposed_coefficients"] != before["coefficients"][0]


def _interrupt_state_commit(body, boundary, action):
    code = core.PairBodyModel.update.__code__
    instructions = list(dis.get_instructions(code))
    stores = [i for i, item in enumerate(instructions)
              if item.opname == "STORE_ATTR" and item.argval == "_state"]
    assert len(stores) == 1
    offset = instructions[stores[0] + (boundary == "after")].offset
    def trace(frame, event, arg):
        if frame.f_code is code and frame.f_locals.get("self") is body:
            frame.f_trace_opcodes = True
            if event == "opcode" and frame.f_lasti == offset:
                raise KeyboardInterrupt(f"synthetic {boundary} state commit")
        return trace
    previous = sys.gettrace()
    try:
        sys.settrace(trace)
        action()
    finally:
        sys.settrace(previous)


@pytest.mark.parametrize("boundary", ["before", "after"])
def test_shared_raw_then_guard_commit_boundary_retains_actual_model_states(boundary):
    raw, guarded = model("raw_request"), model()
    inputs = (QREF, (.1, .2), (.375, -.5), (.3, -.1))
    expected_guard = model()
    if boundary == "after":
        expected_guard.update(*inputs, transition_id="synthetic:shared")
    with pytest.raises(KeyboardInterrupt) as outcome:
        _interrupt_state_commit(guarded, boundary, lambda: core.update_shared_models(
            {"raw": raw, "guard": guarded}, *inputs, transition_id="synthetic:shared",
        ))
    shared = outcome.value.shared_pair_update_accounting
    assert raw.scalar_update_count == 2
    assert guarded.snapshot() == expected_guard.snapshot()
    assert shared["failed_model"] == "guard"
    assert shared["completed_model_records"]["raw"]["committed_scalar_updates"] == 2
    assert "guard" not in shared["completed_model_records"]
    assert shared["snapshots_after_attempt"]["raw"] == raw.snapshot()
    assert shared["snapshots_after_attempt"]["guard"] == guarded.snapshot()
    assert shared["failure_record"] == outcome.value.pair_update_accounting
    assert shared["failure_record"]["committed_scalar_updates"] == (2 if boundary == "after" else 0)
    assert all(p["committed"] == (boundary == "after")
               for p in shared["failure_record"]["proposed_outputs"])


def test_recursive_predictions_recompute_start_guard_when_predicted_q_crosses_boundary():
    body = InputMappedDiagonalPairBodyModel(
        (.0299, .06), public_joint_ranges=((0., 1.), (0., 1.)),
        input_basis="known_angle_guard", trainable=False,
    )
    first = body.predict((.0299, .06), (.01, 0.), (-.5, 0.))
    assert first == ((.0301, .06), (.01, 0.))
    second = body.predict(*first, (-.5, 0.))
    assert second == ((.0301, .06), (0., 0.))
    assert body.describe_input((.0299, .06), (-.5, 0.))["start_blocked"] == (True, False)
    assert body.describe_input(first[0], (-.5, 0.))["start_blocked"] == (False, False)


def test_original_81_candidate_mpc_costs_attempts_and_causal_recompute(monkeypatch):
    body = InputMappedDiagonalPairBodyModel(
        (.0299, .06), public_joint_ranges=((0., 1.), (0., 1.)),
        input_basis="known_angle_guard", trainable=False,
    )
    planner = core.FixedPairMPC(body, body.public_guard.public_joint_ranges)
    original = body.predict
    calls = []
    def record(q, v, u):
        result = original(q, v, u)
        calls.append((tuple(q), tuple(v), tuple(u), result))
        return result
    monkeypatch.setattr(body, "predict", record)
    before = body.snapshot()
    target = (.08, .08)
    decision = planner.select(body.qref, (.01, 0.), target)
    assert decision.feasible_candidates == len(decision.candidate_records) == 81
    assert decision.pair_prediction_attempts == decision.pair_prediction_successes == 81*15
    assert decision.scalar_prediction_attempts == decision.scalar_prediction_successes == 2*81*15
    assert decision.failed_pair_prediction_attempts == 0 and decision.scalar_counts_complete
    assert not decision.fallback and len(calls) == 81*15
    for offset in range(0, len(calls), 15):
        assert calls[offset][:2] == (body.qref, (.01, 0.))
        for i in range(offset+1, offset+15):
            assert calls[i][:2] == calls[i-1][3]
            assert calls[i][2] == calls[offset][2]
    index = next(i for i, item in enumerate(decision.candidate_records) if item.torque == (-.5, 0.))
    candidate = decision.candidate_records[index]
    candidate_calls = calls[index*15:(index+1)*15]
    assert body.public_guard.project(candidate_calls[0][0], candidate.torque).start_blocked[0]
    assert not body.public_guard.project(candidate_calls[1][0], candidate.torque).start_blocked[0]
    cfg = planner.config
    requested_cost = sum(cfg.change_weight * x*x for x in candidate.torque)
    projected_cost = requested_cost
    for q, v, u, (next_q, next_v) in candidate_calls:
        projected = body.public_guard.project(q, u).projected_start_nm
        for i in range(2):
            state_cost = cfg.position_weight*(next_q[i]-target[i])**2 + cfg.velocity_weight*next_v[i]**2
            requested_cost += state_cost + cfg.effort_weight*u[i]**2
            projected_cost += state_cost + cfg.effort_weight*projected[i]**2
    assert candidate.cost == pytest.approx(requested_cost, rel=0., abs=1e-12)
    assert candidate.cost != pytest.approx(projected_cost, rel=0., abs=1e-12)
    assert body.snapshot() == before
    assert planner.spec()["physical_queries"] == 0
