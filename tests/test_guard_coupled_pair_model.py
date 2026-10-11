"""Artificial mathematical evidence only; zero simulator or real-data reads."""
import dis
import inspect
import math
import sys
from dataclasses import FrozenInstanceError

import numpy as np
import pytest

from developmental_physics import local_pair_model as core
from developmental_physics.guard_pair_model import InputMappedDiagonalPairBodyModel, KnownAngleGuard
from developmental_physics.guard_coupled_pair_model import GuardCoupledPairBodyModel


RANGES = ((-1., 1.), (0., 2.3))
QREF = (.1, -.0005)
INPUTS = (QREF, (.1, .2), (.375, -.5), (.3, -.1))


def model(*, trainable=True):
    return GuardCoupledPairBodyModel(QREF, public_joint_ranges=RANGES, trainable=trainable)


def diagonal(*, trainable=True):
    return InputMappedDiagonalPairBodyModel(
        QREF, public_joint_ranges=RANGES, input_basis="known_angle_guard", trainable=trainable,
    )


def manual_features(q, v, u, *, qref=QREF, ranges=RANGES):
    """Independent scalar calculation, not a call to either model or guard."""
    g = []
    for index in range(2):
        command = min(.5, max(-.5, u[index]))
        lower, upper = ranges[index]
        if ((q[index] <= lower+.03 and command < 0.) or
                (q[index] >= upper-.03 and command > 0.)):
            command = 0.
        g.append(command)
    h = [math.copysign(max(abs(x)-.25, 0.), x) for x in g]
    return [*v, q[0]-qref[0], q[1]-qref[1], *g, *h, 1.]


def test_cold_prior_and_global_order_preserve_matching_own_zero_cross():
    body, reference = model(), diagonal()
    assert isinstance(body, core.PairBodyModel)
    assert body.structure == "coupled_hinge9" and body.input_basis == "known_angle_guard"
    assert body.coefficients.tolist() == [
        [1., 0., 0., 0., .02, 0., 0., 0., 0.],
        [0., 1., 0., 0., 0., .02, 0., 0., 0.],
    ]
    for index in range(2):
        assert body.coefficients[index, [index, 2+index, 4+index, 6+index, 8]].tolist() == reference.coefficients[index].tolist()
        assert body.coefficients[index, [1-index, 3-index, 5-index, 7-index]].tolist() == [0.] * 4
    assert np.array_equal(body.covariance, np.repeat((100*np.eye(9))[None, :, :], 2, axis=0))
    snap = body.snapshot()
    assert snap["initial_covariance_scale"] == 100. and snap["forgetting_factor"] == 1.
    assert snap["hinge_threshold_nm"] == .25 and snap["integration"] == "endpoint_euler"
    assert snap["features_per_output"][0] == snap["features_per_output"][1]
    assert snap["feature_roles_per_output"] == [
        {"output_index": 0, "own_columns": [0, 2, 4, 6], "cross_columns": [1, 3, 5, 7], "constant_column": 8},
        {"output_index": 1, "own_columns": [1, 3, 5, 7], "cross_columns": [0, 2, 4, 6], "constant_column": 8},
    ]


@pytest.mark.parametrize("q,v,u", [
    (QREF, (.1, .2), (.375, -.5)),
    ((-.97, .03), (.01, -.02), (-.5, -.5)),
    ((.97, 2.27), (-.01, .02), (.5, .5)),
    ((0., 1.), (.1, -.1), (2., -2.)),
    ((-1.01, -.0005), (-.1, .2), (.125, -.125)),
    ((0., .2), (0., 0.), (0., -0.)),
])
def test_cross_zero_prediction_matches_guard_diagonal_at_edges_and_clip(q, v, u):
    body, reference = model(trainable=False), diagonal(trainable=False)
    before = body.snapshot()
    assert body.predict(q, v, u) == reference.predict(q, v, u)
    positions, features = body._features(q, v, u)
    assert positions == q
    assert features.tolist() == [manual_features(q, v, u)] * 2
    assert body.snapshot() == before


def test_one_rls_update_matches_scalar_hand_computation_and_atomic_record():
    body = model()
    q, v, u, labels = INPUTS
    feature = manual_features(q, v, u)
    initial = body.coefficients.tolist()
    denominator = 1.+100.*sum(x*x for x in feature)
    expected_theta, expected_covariance = [], []
    for head in range(2):
        prediction = sum(a*b for a, b in zip(initial[head], feature))
        residual = labels[head]-prediction
        expected_theta.append([initial[head][j]+100.*feature[j]*residual/denominator for j in range(9)])
        expected_covariance.append([
            [100.*(i == j)-10000.*feature[i]*feature[j]/denominator for j in range(9)]
            for i in range(9)
        ])
    record = body.update(*INPUTS, transition_id="artificial:hand-update")
    assert np.allclose(body.coefficients, expected_theta, atol=1e-14, rtol=0.)
    assert np.allclose(body.covariance, expected_covariance, atol=3e-14, rtol=0.)
    assert record["features_per_output"] == [feature] * 2
    assert record["committed_scalar_updates"] == 2 and body.update_count == 1
    assert all(row["committed"] for row in record["output_records"])
    assert record["shared_transition_id"] == "artificial:hand-update"
    assert record["preupdate_prediction"]["next_v_rad_s"] == pytest.approx([.1075, .2], abs=1e-15, rel=0.)


def artificial_dataset(seed, count):
    rng = np.random.default_rng(seed)
    truth = (
        (.82, .18, -.07, .09, .22, -.13, .06, -.04, .01),
        (-.16, .87, .11, -.08, -.19, .24, .03, .07, -.015),
    )
    levels = (-.75, -.5, -.375, -.25, -.125, 0., .125, .25, .375, .5, .75)
    rows = []
    for _ in range(count):
        q = (float(rng.uniform(-1.04, 1.04)), float(rng.uniform(-.04, 2.34)))
        v = tuple(float(x) for x in rng.uniform(-.5, .5, 2))
        u = tuple(float(x) for x in rng.choice(levels, 2))
        x = manual_features(q, v, u)
        labels = tuple(sum(a*b for a, b in zip(head, x)) for head in truth)
        rows.append((q, v, u, labels, x))
    return rows, truth


def test_identifiable_artificial_coupling_is_learned_on_fixed_disjoint_label_holdout():
    body, reference = model(), diagonal()
    train, truth = artificial_dataset(70230, 128)
    holdout, _ = artificial_dataset(70231, 32)
    assert np.linalg.matrix_rank(np.asarray([row[4] for row in train])) == 9
    cold = body.clone_frozen()
    for index, (q, v, u, labels, _) in enumerate(train):
        body.update(q, v, u, labels, transition_id=f"artificial:calibration:{index}")
        reference.update(q, v, u, labels, transition_id=f"artificial:calibration:{index}")
    frozen = body.clone_frozen()
    snapshots = [item.snapshot() for item in (body, reference, frozen, cold)]
    sums = [0., 0., 0.]
    for q, v, u, labels, _ in holdout:
        for index, item in enumerate((frozen, reference, cold)):
            predicted = item.predict(q, v, u)[1]
            sums[index] += sum((predicted[head]-labels[head])**2 for head in range(2))
    rmse = [math.sqrt(value/64) for value in sums]
    assert rmse[0] < .02*rmse[1] and rmse[0] < .02*rmse[2]
    assert np.max(np.abs(body.coefficients-np.asarray(truth))) < .02
    assert [item.snapshot() for item in (body, reference, frozen, cold)] == snapshots
    assert body.update_count == reference.update_count == 128
    assert body.scalar_update_count == reference.scalar_update_count == 256
    # A cross-only probe changes head 0 through axis 1's command, with own
    # state/input identical and both guards interior. No holdout fitting.
    a = frozen.predict((.1, .2), (.1, -.1), (0., 0.))[1][0]
    b = frozen.predict((.1, .2), (.1, -.1), (0., .5))[1][0]
    expected_cross = truth[0][5]*.5+truth[0][7]*.25
    assert b-a == pytest.approx(expected_cross, abs=.004)


def test_prefix_skips_learning_and_clone_preserves_guard_identity_and_isolation():
    body = model()
    before = body.snapshot()
    prefix = body.update(*INPUTS, phase="prefix", transition_id="artificial:prefix")
    assert body.snapshot() == before and prefix["committed_scalar_updates"] == 0
    body.update(*INPUTS, transition_id="artificial:calibration")
    frozen = body.clone_frozen()
    assert type(frozen) is GuardCoupledPairBodyModel and not frozen.trainable
    assert frozen.input_basis == "known_angle_guard" and frozen.structure == "coupled_hinge9"
    assert frozen.public_guard == body.public_guard and frozen.public_guard is not body.public_guard
    assert frozen.parameter_fingerprint() == body.parameter_fingerprint()
    snap = frozen.snapshot()
    assert snap["features_per_output"] == body.snapshot()["features_per_output"]
    assert snap["model_definition"]["parameter_count_per_output"] == 9
    assert not frozen._state.theta.flags.writeable and not frozen._state.covariance.flags.writeable
    assert not np.shares_memory(frozen._state.theta, body._state.theta)
    assert not np.shares_memory(frozen._state.covariance, body._state.covariance)
    with pytest.raises(RuntimeError, match="frozen"):
        frozen.update(*INPUTS)
    body.update(QREF, (.2, .1), (.5, .5), (.1, .3))
    frozen.coefficients[:] = 999.
    frozen.covariance[:] = 999.
    assert frozen.snapshot() == snap


def test_public_guard_and_snapshot_sources_are_owned_and_bound_by_fingerprint():
    caller = [[-1., 1.], [0., 2.3]]
    body = GuardCoupledPairBodyModel(QREF, public_joint_ranges=caller)
    caller[0][0] = -99.
    assert body.public_guard.public_joint_ranges == RANGES
    with pytest.raises(FrozenInstanceError):
        body.public_guard.margin_rad = .1
    snap = body.snapshot()
    snap["input_mapping"]["public_guard"]["public_joint_ranges_rad"][0][0] = -99.
    snap["features_per_output"][0][0] = "actual_future"
    assert body.snapshot()["features_per_output"][0][0] == "v0"
    other = GuardCoupledPairBodyModel(QREF, public_joint_ranges=((-1.1, 1.), (0., 2.3)))
    assert body.parameter_fingerprint() != other.parameter_fingerprint()
    assert body.parameter_fingerprint() != diagonal().parameter_fingerprint()
    assert body.snapshot()["model_definition"]["physical_queries"] == 0


@pytest.mark.parametrize("bad", [(0.,), (0., 0., 0.), [[0., 0.]], (True, 0.),
                                  ("0", 0.), (np.nan, 0.), (np.inf, 0.), (0j, 0.)])
def test_invalid_native_pair_rejected_before_parameters_change(bad):
    body = model()
    before = body.snapshot()
    for position in range(4):
        inputs = list(INPUTS)
        inputs[position] = bad
        with pytest.raises(ValueError):
            body.update(*inputs)
        if position < 3:
            with pytest.raises(core.PairPredictionError) as outcome:
                body.predict(*inputs[:3])
            assert outcome.value.scalar_prediction_attempts == 0
    assert body.snapshot() == before


@pytest.mark.parametrize("kwargs", [
    {"dt": .01}, {"dt": True}, {"dt": np.nan}, {"trainable": 1},
    {"public_joint_ranges": ((0., 0.), (0., 1.))},
    {"public_joint_ranges": ((0., np.inf), (0., 1.))},
    {"public_joint_ranges": ((0., 1.),)},
    {"public_joint_ranges": ((False, 1.), (0., 1.))},
])
def test_invalid_initialization_is_rejected(kwargs):
    args = {"public_joint_ranges": RANGES, **kwargs}
    with pytest.raises(ValueError):
        GuardCoupledPairBodyModel(QREF, **args)


@pytest.mark.parametrize("fatal", [False, True])
def test_second_head_proposal_failure_preserves_atomic_parameters_and_ledger(monkeypatch, fatal):
    body = model()
    before = body.snapshot()
    original = body._propose_update
    def fail(index, *args):
        if index == 1:
            raise OSError("artificial second-head IO") if fatal else ValueError("artificial second-head rejection")
        return original(index, *args)
    monkeypatch.setattr(body, "_propose_update", fail)
    with pytest.raises(OSError if fatal else core.PairUpdateError) as outcome:
        body.update(*INPUTS, transition_id="artificial:failed-second-head")
    ledger = outcome.value.pair_update_accounting if fatal else outcome.value.to_dict()
    assert body.snapshot() == before
    assert ledger["committed_scalar_updates"] == 0 and ledger["snapshot_after_attempt"] == before
    assert len(ledger["proposed_outputs"]) == 1 and not ledger["proposed_outputs"][0]["committed"]


def interrupt_commit(body, boundary, action):
    # The wrapper installed by the evidence harness exposes the original
    # unchanged implementation for exact sole-commit bytecode injection.
    update = inspect.unwrap(core.PairBodyModel.update)
    code = update.__code__
    instructions = list(dis.get_instructions(code))
    stores = [i for i, item in enumerate(instructions) if item.opname == "STORE_ATTR" and item.argval == "_state"]
    assert len(stores) == 1
    offset = instructions[stores[0]+(boundary == "after")].offset
    def trace(frame, event, arg):
        if frame.f_code is code and frame.f_locals.get("self") is body:
            frame.f_trace_opcodes = True
            if event == "opcode" and frame.f_lasti == offset:
                raise KeyboardInterrupt(f"artificial {boundary} atomic commit")
        return trace
    old = sys.gettrace()
    try:
        sys.settrace(trace)
        action()
    finally:
        sys.settrace(old)


@pytest.mark.parametrize("boundary", ["before", "after"])
def test_interrupt_single_commit_is_wholly_old_or_new_with_exact_cost(boundary):
    body, expected = model(), model()
    if boundary == "after":
        expected.update(*INPUTS)
    with pytest.raises(KeyboardInterrupt) as outcome:
        interrupt_commit(body, boundary, lambda: body.update(*INPUTS))
    assert body.snapshot() == expected.snapshot()
    ledger = outcome.value.pair_update_accounting
    assert ledger["committed_scalar_updates"] == (2 if boundary == "after" else 0)
    assert ledger["snapshot_after_attempt"] == body.snapshot()
    assert all(row["committed"] == (boundary == "after") for row in ledger["proposed_outputs"])


def test_overflowing_displacement_is_rejected_without_any_output_or_update():
    body = GuardCoupledPairBodyModel((1e308, 0.), public_joint_ranges=RANGES)
    before = body.snapshot()
    with pytest.raises(core.PairPredictionError) as outcome:
        body.predict((-1e308, 0.), (0., 0.), (0., 0.))
    assert outcome.value.failure_stage == "native_features" and outcome.value.scalar_prediction_attempts == 0
    with pytest.raises(ValueError):
        body.update((-1e308, 0.), (0., 0.), (0., 0.), (0., 0.))
    assert body.snapshot() == before


def test_finite_huge_feature_can_predict_but_rls_proposal_overflow_is_atomic():
    body = model()
    before = body.snapshot()
    with pytest.raises(core.PairUpdateError) as outcome:
        body.update(QREF, (1e308, 0.), (0., 0.), (0., 0.))
    assert outcome.value.committed_scalar_updates == 0 and body.snapshot() == before


def test_causal_interface_has_no_actual_future_or_privileged_arguments():
    body = model()
    assert list(inspect.signature(body.predict).parameters) == ["q", "v", "u"]
    assert list(inspect.signature(body.describe_input).parameters) == ["q", "u"]
    before = body.snapshot()
    for forbidden in ("actual_torque", "next_q", "contact", "environment", "hidden_gain"):
        with pytest.raises(TypeError):
            body.predict(*INPUTS[:3], **{forbidden: object()})
        with pytest.raises(TypeError):
            body.describe_input(INPUTS[0], INPUTS[2], **{forbidden: object()})
    assert body.snapshot() == before
    assert body.snapshot()["input_mapping"]["public_guard"]["future_actual_input"] is False


def test_future_self_predictions_recompute_both_guards_after_boundary_crossing():
    body = GuardCoupledPairBodyModel(
        (.0299, .9701), public_joint_ranges=((0., 1.), (0., 1.)), trainable=False,
    )
    command = (-.5, .5)
    first = body.predict(body.qref, (.01, -.01), command)
    assert first[1] == (.01, -.01)
    assert body.describe_input(body.qref, command)["start_blocked"] == (True, True)
    assert body.describe_input(first[0], command)["start_blocked"] == (False, False)
    second = body.predict(*first, command)
    assert second[1] == (0., 0.)


def test_unchanged_mpc_uses_predicted_guard_each_step_and_retains_requested_effort(monkeypatch):
    body = GuardCoupledPairBodyModel(
        (.0299, .06), public_joint_ranges=((0., 1.), (0., 1.)), trainable=False,
    )
    planner = core.FixedPairMPC(body, body.public_guard.public_joint_ranges)
    original = body.predict
    calls = []
    def record(q, v, u):
        answer = original(q, v, u)
        calls.append((tuple(q), tuple(v), tuple(u), answer))
        return answer
    monkeypatch.setattr(body, "predict", record)
    before = body.snapshot()
    target = (.08, .08)
    decision = planner.select(body.qref, (.01, 0.), target)
    assert decision.feasible_candidates == 81 and not decision.fallback
    assert len(calls) == decision.pair_prediction_attempts == decision.pair_prediction_successes == 81*15
    assert decision.scalar_prediction_attempts == decision.scalar_prediction_successes == 2*81*15
    for offset in range(0, len(calls), 15):
        assert calls[offset][:2] == (body.qref, (.01, 0.))
        for index in range(offset+1, offset+15):
            assert calls[index][:2] == calls[index-1][3]
            assert calls[index][2] == calls[offset][2]
    candidate_index = next(i for i, row in enumerate(decision.candidate_records) if row.torque == (-.5, 0.))
    candidate = decision.candidate_records[candidate_index]
    rows = calls[candidate_index*15:(candidate_index+1)*15]
    assert body.public_guard.project(rows[0][0], candidate.torque).start_blocked[0]
    assert not body.public_guard.project(rows[1][0], candidate.torque).start_blocked[0]
    config = planner.config
    requested = config.change_weight*sum(x*x for x in candidate.torque)
    projected = requested
    for q, v, u, (next_q, next_v) in rows:
        g = manual_features(q, v, u, qref=body.qref, ranges=body.public_guard.public_joint_ranges)[4:6]
        for head in range(2):
            state_cost = config.position_weight*(next_q[head]-target[head])**2+config.velocity_weight*next_v[head]**2
            requested += state_cost+config.effort_weight*u[head]**2
            projected += state_cost+config.effort_weight*g[head]**2
    assert candidate.cost == pytest.approx(requested, abs=1e-12, rel=0.)
    assert candidate.cost != pytest.approx(projected, abs=1e-12, rel=0.)
    assert body.snapshot() == before and planner.spec()["physical_queries"] == 0
