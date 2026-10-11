"""Native-only mathematical unit checks; no simulation or real labels."""
import dis
import inspect
import sys

import numpy as np
import pytest

from developmental_physics.local_model import HingeBodyModel,FixedLocalMPC,MPCConfig
from developmental_physics import local_pair_model as core


def test_cold_diagonal_coupled_and_scalar_priors_are_exactly_equivalent():
    qref=(.09739774391333796,-.0005762480149995581)
    diagonal=core.DiagonalPairBodyModel(qref)
    coupled=core.CoupledPairBodyModel(qref)
    scalar=[HingeBodyModel(q) for q in qref]
    assert coupled.coefficients.shape == (2,9) and diagonal.coefficients.shape == (2,5)
    assert coupled.coefficients[0].tolist() == [1.,0.,0.,0.,.02,0.,0.,0.,0.]
    assert coupled.coefficients[1].tolist() == [0.,1.,0.,0.,0.,.02,0.,0.,0.]
    assert np.array_equal(coupled.covariance,np.repeat((100*np.eye(9))[None,:,:],2,axis=0))
    rng=np.random.default_rng(0)
    for _ in range(20):
        q=rng.normal(0,.1,2)
        v=rng.normal(0,.2,2)
        u=rng.uniform(-.5,.5,2)
        left=diagonal.predict(q,v,u)
        assert left == coupled.predict(q,v,u)
        scalar_predictions=[scalar[i].predict(q[i],v[i],u[i]) for i in range(2)]
        assert left == (tuple(p[0] for p in scalar_predictions),tuple(p[1] for p in scalar_predictions))
    assert diagonal.qref[1] < 0. and coupled.qref[1] < 0.


def test_diagonal_updates_match_both_existing_hinge_heads_on_all_shared_labels():
    qref=(.1,-.0005)
    pair=core.DiagonalPairBodyModel(qref)
    scalar=[HingeBodyModel(q) for q in qref]
    transitions=[((.1,-.0005),(.04,.02),(.375,0.),(.07,.06)),
                 ((.103,.004),(.06,.08),(0.,.5),(.12,.15)),
                 ((.104,.005),(.12,.15),(-.25,-.125),(.08,.1))]
    for index,(q,v,u,label) in enumerate(transitions):
        record=pair.update(q,v,u,label,transition_id=f"synthetic:{index}")
        assert record["committed_scalar_updates"] == 2
        for i in range(2):
            scalar[i].update(q[i],v[i],u[i],label[i])
            assert np.array_equal(pair.coefficients[i],scalar[i].coefficients)
            assert np.array_equal(pair.covariance[i],scalar[i].covariance)
    assert pair.update_count == 3 and pair.scalar_update_count == 6


def test_coupled_features_and_native_cross_input_response_after_one_label():
    model=core.CoupledPairBodyModel((.1,-.0005))
    q=(.12,.0395); v=(.03,.04); u=(.375,-.5)
    record=model.update(q,v,u,(.3,-.2),transition_id="same_vector")
    expected=[.03,.04,.01999999999999999,.04,.375,-.5,.125,-.25,1.]
    assert np.array_equal(record["features_per_output"][0],expected)
    assert record["features_per_output"][0] == record["features_per_output"][1]
    assert model.coefficients[0,1] != 0. and model.coefficients[0,5] != 0.
    before=model.predict(q,v,(0.,0.))[1][0]
    assert model.predict(q,v,(0.,.25))[1][0] != before
    assert list(inspect.signature(model.predict).parameters) == ["q","v","u"]
    with pytest.raises(TypeError):
        model.predict(q,v,u,next_v=(999.,999.))


def test_two_output_rls_is_atomic_and_uncommitted_proposals_are_preserved(monkeypatch):
    model=core.CoupledPairBodyModel((0.,0.))
    before=model.snapshot()
    original=model._propose_update
    def fail(index,*args):
        if index == 1:
            raise ValueError("synthetic second-head proposal failure")
        return original(index,*args)
    monkeypatch.setattr(model,"_propose_update",fail)
    with pytest.raises(core.PairUpdateError) as outcome:
        model.update((0.,0.),(.1,.2),(.5,.25),(.2,.4),transition_id="vector")
    assert model.snapshot() == before and model.scalar_update_count == 0
    ledger=outcome.value.to_dict()
    assert ledger["committed_scalar_updates"] == 0 and len(ledger["proposed_outputs"]) == 1
    assert ledger["proposed_outputs"][0]["committed"] is False
    assert ledger["proposed_outputs"][0]["proposed_coefficients"] != before["coefficients"][0]


@pytest.mark.parametrize("fatal",[False,True])
def test_later_model_failure_retains_earlier_committed_model_and_original_io_semantics(monkeypatch,fatal):
    diagonal=core.DiagonalPairBodyModel((0.,0.))
    coupled=core.CoupledPairBodyModel((0.,0.))
    def fail(*args):
        if fatal:
            raise OSError("synthetic IO")
        raise ValueError("synthetic proposal")
    monkeypatch.setattr(coupled,"_propose_update",fail)
    with pytest.raises(OSError if fatal else core.SharedPairUpdateError) as outcome:
        core.update_shared_models({"diagonal":diagonal,"coupled":coupled},
            (0.,0.),(.1,.2),(.5,.25),(.2,.4),transition_id="shared")
    assert diagonal.scalar_update_count == 2 and coupled.scalar_update_count == 0
    ledger=(outcome.value.shared_pair_update_accounting if fatal else outcome.value.to_dict())
    assert ledger["shared_transition_id"] == "shared"
    assert ledger["completed_model_records"]["diagonal"]["committed_scalar_updates"] == 2
    assert ledger["snapshots_after_attempt"]["diagonal"]["scalar_update_count"] == 2


def test_second_head_io_preserves_uncommitted_proposal_in_nested_shared_ledger(monkeypatch):
    diagonal=core.DiagonalPairBodyModel((0.,0.))
    coupled=core.CoupledPairBodyModel((0.,0.))
    original=coupled._propose_update
    def fail(index,*args):
        if index == 1:
            raise OSError("synthetic second-head IO")
        return original(index,*args)
    monkeypatch.setattr(coupled,"_propose_update",fail)
    with pytest.raises(OSError) as outcome:
        core.update_shared_models({"diagonal":diagonal,"coupled":coupled},
            (0.,0.),(.1,.2),(.5,.25),(.2,.4),transition_id="shared")
    shared=outcome.value.shared_pair_update_accounting
    assert shared["failure_record"] == outcome.value.pair_update_accounting
    assert len(shared["failure_record"]["proposed_outputs"]) == 1
    assert shared["failure_record"]["proposed_outputs"][0]["committed"] is False
    assert shared["snapshots_after_attempt"]["diagonal"]["scalar_update_count"] == 2
    assert shared["snapshots_after_attempt"]["coupled"]["scalar_update_count"] == 0


def _interrupt_state_commit(model, boundary, action):
    """Inject exactly before/after the sole state-publishing bytecode."""
    code=core.PairBodyModel.update.__code__
    instructions=list(dis.get_instructions(code))
    stores=[i for i,item in enumerate(instructions)
            if item.opname == "STORE_ATTR" and item.argval == "_state"]
    assert len(stores) == 1
    offset=instructions[stores[0]+(boundary == "after")].offset
    def trace(frame,event,arg):
        if frame.f_code is code and frame.f_locals.get("self") is model:
            frame.f_trace_opcodes=True
            if event == "opcode" and frame.f_lasti == offset:
                raise KeyboardInterrupt(f"synthetic {boundary} state commit")
        return trace
    previous=sys.gettrace()
    try:
        sys.settrace(trace)
        action()
    finally:
        sys.settrace(previous)


@pytest.mark.parametrize("boundary",["before","after"])
def test_commit_boundary_interrupt_leaves_complete_old_or_new_state_and_exact_ledger(boundary):
    model=core.CoupledPairBodyModel((0.,0.))
    before=model.snapshot()
    inputs=((0.,0.),(.1,.2),(.5,.25),(.2,.4))
    expected=core.CoupledPairBodyModel((0.,0.))
    expected.update(*inputs,transition_id="vector")
    expected_snapshot=expected.snapshot() if boundary == "after" else before
    with pytest.raises(KeyboardInterrupt) as outcome:
        _interrupt_state_commit(model,boundary,
            lambda:model.update(*inputs,transition_id="vector"))
    assert model.snapshot() == expected_snapshot
    assert not hasattr(model,"_theta") and not hasattr(model,"_covariance") and not hasattr(model,"_update_count")
    ledger=outcome.value.pair_update_accounting
    assert ledger["snapshot_after_attempt"] == expected_snapshot
    assert ledger["committed_scalar_updates"] == (2 if boundary == "after" else 0)
    assert len(ledger["proposed_outputs"]) == 2
    assert all(p["committed"] == (boundary == "after") for p in ledger["proposed_outputs"])
    assert not model._state.theta.flags.writeable and not model._state.covariance.flags.writeable


@pytest.mark.parametrize("boundary",["before","after"])
def test_shared_commit_boundary_ledger_keeps_actual_failed_model_commit(boundary):
    diagonal=core.DiagonalPairBodyModel((0.,0.))
    coupled=core.CoupledPairBodyModel((0.,0.))
    with pytest.raises(KeyboardInterrupt) as outcome:
        _interrupt_state_commit(coupled,boundary,lambda:core.update_shared_models(
            {"diagonal":diagonal,"coupled":coupled},
            (0.,0.),(.1,.2),(.5,.25),(.2,.4),transition_id="shared"))
    shared=outcome.value.shared_pair_update_accounting
    assert shared["failed_model"] == "coupled"
    assert shared["completed_model_records"]["diagonal"]["committed_scalar_updates"] == 2
    assert "coupled" not in shared["completed_model_records"]
    assert shared["snapshots_after_attempt"]["diagonal"]["scalar_update_count"] == 2
    assert shared["snapshots_after_attempt"]["coupled"] == coupled.snapshot()
    assert shared["snapshots_after_attempt"]["coupled"]["scalar_update_count"] == (2 if boundary == "after" else 0)
    assert shared["failure_record"]["committed_scalar_updates"] == (2 if boundary == "after" else 0)
    assert shared["failure_record"] == outcome.value.pair_update_accounting


def test_snapshot_binds_record_fingerprint_and_counts_to_one_state(monkeypatch):
    model=core.CoupledPairBodyModel((0.,0.))
    before=model.snapshot()
    updated=core.CoupledPairBodyModel((0.,0.))
    updated.update((0.,0.),(.1,.2),(.5,.25),(.2,.4))
    original=model._parameter_record
    def swap_during_record(state=None):
        model._state=updated._state
        return original(state)
    monkeypatch.setattr(model,"_parameter_record",swap_during_record)
    assert model.snapshot() == before
    assert model.snapshot() == updated.snapshot()


def test_prediction_binds_both_heads_to_one_captured_state(monkeypatch):
    model=core.CoupledPairBodyModel((0.,0.))
    inputs=((0.,0.),(.1,.2),(.5,.25))
    before=model.predict(*inputs)
    updated=core.CoupledPairBodyModel((0.,0.))
    updated.update(*inputs,(.2,.4))
    original=model._predict_output
    def swap_during_first_head(index,features,state=None):
        if index == 0:
            model._state=updated._state
        return original(index,features,state)
    monkeypatch.setattr(model,"_predict_output",swap_during_first_head)
    assert model.predict(*inputs) == before
    assert model.predict(*inputs) == updated.predict(*inputs)


def test_prefix_skip_frozen_clone_and_copy_isolation():
    model=core.CoupledPairBodyModel((0.,0.))
    before=model.parameter_fingerprint()
    record=model.update((0.,0.),(.1,.2),(.5,.25),(.2,.4),phase="prefix")
    assert not record["updated"] and record["committed_scalar_updates"] == 0
    assert model.parameter_fingerprint() == before
    model.update((0.,0.),(.1,.2),(.5,.25),(.2,.4))
    frozen=model.clone_frozen()
    assert not frozen.trainable and frozen.parameter_fingerprint() == model.parameter_fingerprint()
    assert frozen.scalar_update_count == 2
    copy=frozen.coefficients
    copy[:]=999.
    assert not np.array_equal(copy,frozen.coefficients)
    with pytest.raises(RuntimeError,match="frozen"):
        frozen.update((0.,0.),(.1,.2),(.5,.25),(.2,.4))
    with pytest.raises(ValueError,match="two finite"):
        frozen.predict([0.,0.,123.],[0.,0.],[0.,0.])


def test_shared_transition_cannot_silently_double_update_an_alias():
    model=core.CoupledPairBodyModel((0.,0.))
    before=model.snapshot()
    with pytest.raises(ValueError,match="distinct"):
        core.update_shared_models({"first":model,"alias":model},(0.,0.),(.1,.2),(.5,.25),(.2,.4),transition_id="same")
    assert model.snapshot() == before


def test_default_pair_mpc_cost_and_selected_actions_equal_two_scalar_mpc_costs():
    qref=(.09739774391333796,-.0005762480149995581)
    model=core.DiagonalPairBodyModel(qref,trainable=False)
    limits=((-1.7453292519943295,1.7453292519943295),(0.,2.356194490192345))
    target=(qref[0]-.04,qref[1]+.04)
    pair=core.FixedPairMPC(model,limits)
    before=model.parameter_fingerprint()
    result=pair.select(qref,(0.,0.),target)
    scalars=[FixedLocalMPC(HingeBodyModel(qref[i],trainable=False),limits[i]).select(qref[i],0.,target[i]) for i in range(2)]
    assert result.torque == tuple(s.torque for s in scalars)
    assert result.cost == sum(s.cost for s in scalars)
    assert result.pair_prediction_attempts == result.pair_prediction_successes == 81*15
    assert result.scalar_prediction_attempts == result.scalar_prediction_successes == 2*81*15
    assert result.failed_pair_prediction_attempts == 0 and result.scalar_counts_complete
    assert result.feasible_candidates == 81 and len(result.candidate_records) == 81
    for index in range(15):
        assert result.predicted_q[index] == tuple(s.predicted_q[index] for s in scalars)
    assert model.parameter_fingerprint() == before
    assert pair.spec()["physical_queries"] == 0


def test_constant_vector_free_rollout_uses_predicted_state_and_only_current_target(monkeypatch):
    model=core.CoupledPairBodyModel((0.,0.),trainable=False)
    original=model.predict
    inputs=[]
    def record(q,v,u):
        inputs.append((tuple(q),tuple(v),tuple(u)))
        return original(q,v,u)
    monkeypatch.setattr(model,"predict",record)
    cfg=MPCConfig(horizon=3,candidate_count=3)
    planner=core.FixedPairMPC(model,((-1.,1.),(-1.,1.)),cfg)
    planner.select((0.,0.),(.02,-.01),(.04,.04))
    assert len(inputs) == 9*3
    for offset in range(0,len(inputs),3):
        assert inputs[offset][:2] == ((0.,0.),(.02,-.01))
        assert len({row[2] for row in inputs[offset:offset+3]}) == 1
        for index in (offset+1,offset+2):
            assert inputs[index][:2] == original(*inputs[index-1])
    with pytest.raises(ValueError,match="two finite"):
        planner.select((0.,0.),(0.,0.),[(.04,.04),(.08,.04)])


def test_exact_ties_choose_sum_absolute_then_signed_u0_u1_and_zero_fallback(monkeypatch):
    model=core.CoupledPairBodyModel((0.,0.),trainable=False)
    cfg=MPCConfig(position_weight=0.,velocity_weight=0.,effort_weight=0.,change_weight=0.)
    planner=core.FixedPairMPC(model,((-1.,1.),(-1.,1.)),cfg)
    # Zero axes are infeasible; all other candidates have exact equal cost.
    monkeypatch.setattr(model,"predict",lambda q,v,u: (((.3,.3) if 0. in u else (0.,0.)),(0.,0.)))
    result=planner.select((0.,0.),(0.,0.),(0.,0.))
    assert result.torque == (-.125,-.125) and result.cost == 0.
    monkeypatch.setattr(model,"predict",lambda q,v,u: ((.3,.3),(0.,0.)))
    failed=planner.select((0.,0.),(0.,0.),(0.,0.))
    assert failed.fallback and failed.torque == (0.,0.) and failed.cost is None
    assert failed.pair_prediction_attempts == 81 and failed.scalar_prediction_attempts == 162


@pytest.mark.parametrize("failed_head",[0,1])
def test_failed_head_attempts_are_counted_exactly(monkeypatch,failed_head):
    model=core.CoupledPairBodyModel((0.,0.),trainable=False)
    original=model._predict_output
    def fail(index,x,state=None):
        if index == failed_head:
            raise ValueError("synthetic head failure")
        return original(index,x,state)
    monkeypatch.setattr(model,"_predict_output",fail)
    result=core.FixedPairMPC(model,((-1.,1.),(-1.,1.))).select((0.,0.),(0.,0.),(.04,.04))
    assert result.fallback and result.failed_pair_prediction_attempts == 81
    assert result.scalar_prediction_attempts == 81*(1+failed_head)
    assert result.scalar_prediction_successes == 81*failed_head
    assert result.scalar_counts_complete and not result.scalar_counts_is_lower_bound


def test_unknown_prediction_failure_is_an_explicit_scalar_lower_bound(monkeypatch):
    model=core.CoupledPairBodyModel((0.,0.),trainable=False)
    def fail(*args):
        raise ValueError("synthetic uninstrumented adapter failure")
    monkeypatch.setattr(model,"predict",fail)
    result=core.FixedPairMPC(model,((-1.,1.),(-1.,1.))).select((0.,0.),(0.,0.),(.04,.04))
    assert result.pair_prediction_attempts == result.unknown_scalar_failure_count == 81
    assert result.scalar_prediction_attempts == 0 and not result.scalar_counts_complete
    assert result.scalar_counts_is_lower_bound


def test_original_unexpected_failure_keeps_exact_head_cost_ledger(monkeypatch):
    model=core.CoupledPairBodyModel((0.,0.),trainable=False)
    original=model._predict_output
    def fail(index,x,state=None):
        if index == 1:
            raise OSError("synthetic head IO")
        return original(index,x,state)
    monkeypatch.setattr(model,"_predict_output",fail)
    with pytest.raises(OSError) as outcome:
        core.FixedPairMPC(model,((-1.,1.),(-1.,1.))).select((0.,0.),(0.,0.),(.04,.04))
    ledger=outcome.value.pair_planning_accounting
    assert ledger["pair_prediction_attempts"] == 1 and ledger["pair_prediction_successes"] == 0
    assert ledger["scalar_prediction_attempts"] == 2 and ledger["scalar_prediction_successes"] == 1
    assert ledger["scalar_counts_complete"]


def test_target_interior_and_forecast_velocity_limits_remain_per_axis(monkeypatch):
    model=core.DiagonalPairBodyModel((.1,-.0005),trainable=False)
    planner=core.FixedPairMPC(model,((-1.,1.),(0.,2.3)))
    with pytest.raises(ValueError,match="public limit margin"):
        planner.select(model.qref,(0.,0.),(.1,model.qref[1]))
    with pytest.raises(ValueError,match="per-axis"):
        planner.select(model.qref,(0.,0.),(.1,.04),previous_torque=(0.,.501))
    monkeypatch.setattr(model,"predict",lambda q,v,u: ((.1,.04),(0.,1.500001)))
    result=planner.select(model.qref,(0.,0.),(.1,.04))
    assert result.fallback and all(r.rejection_reason == "forecast_velocity_bound" for r in result.candidate_records)
