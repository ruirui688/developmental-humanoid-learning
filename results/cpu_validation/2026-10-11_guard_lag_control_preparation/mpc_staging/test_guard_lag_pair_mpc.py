"""Small handwritten MPC engineering checks; no physics, fits or stored data.

Run once with --output to retain the source snapshot, complete outcomes and
the exact artificial prediction budget, including failures and references.
Production H15/81 is checked as metadata only, never used in a fake matrix.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, fields
import hashlib
import inspect
import json
from pathlib import Path
import platform
import shutil
import sys
import time
import traceback

import numpy as np

from developmental_physics.guard_lag_pair_model import GuardLagPairBodyModel
from developmental_physics.local_model import MPCConfig
from developmental_physics.local_pair_model import PairMPCDecision, PairPredictionError
from guard_lag_pair_mpc import FixedGuardLagPairMPC


RANGES = ((-1., 1.), (-1., 1.))
BUDGET = {
    "artificial_model_pair_attempts": 0, "artificial_model_pair_successes": 0,
    "artificial_scalar_attempts": 0, "artificial_scalar_successes": 0,
    "unknown_scalar_failures": 0, "hand_reference_pair_steps": 0,
    "hand_reference_scalar_velocity_steps": 0, "cost_reference_steps": 0,
    "real_model_pair_attempts": 0, "real_model_pair_successes": 0,
    "real_model_scalar_attempts": 0, "real_model_scalar_successes": 0,
    "physical_queries": 0, "rls_updates": 0, "raw_data_reads": 0,
}


class RecordingLag(GuardLagPairBodyModel):
    def __init__(self, mode="history"):
        super().__init__((0., 0.), public_joint_ranges=RANGES, trainable=False)
        self.mode = mode
        self.calls = []

    def predict(self, q, v, u, previous_v):
        self.calls.append({"q": tuple(q), "v": tuple(v), "u": tuple(u),
                           "previous_v": tuple(previous_v)})
        BUDGET["artificial_model_pair_attempts"] += 1
        if self.mode == "mixed_errors" and u[0] < 0:
            BUDGET["unknown_scalar_failures"] += 1
            raise ValueError("handwritten unknown output accounting")
        if self.mode == "mixed_errors" and u[0] > 0:
            BUDGET["artificial_scalar_attempts"] += 2
            BUDGET["artificial_scalar_successes"] += 1
            raise PairPredictionError(ValueError("handwritten second-head rejection"), 2, 1, "head_1")
        if self.mode in ("fatal_known", "fatal_unknown") and u[0] > 0:
            exc = OSError("handwritten IO failure")
            if self.mode == "fatal_known":
                BUDGET["artificial_scalar_attempts"] += 2
                BUDGET["artificial_scalar_successes"] += 1
                exc.pair_prediction_accounting = {
                    "scalar_prediction_attempts": 2, "scalar_prediction_successes": 1}
            else:
                BUDGET["unknown_scalar_failures"] += 1
            raise exc
        BUDGET["artificial_model_pair_successes"] += 1
        BUDGET["artificial_scalar_attempts"] += 2
        BUDGET["artificial_scalar_successes"] += 2
        if self.mode == "bounds":
            return ((.2, 0.), (0., 0.)) if u[0] < 0 else ((0., 0.), (2., 0.))
        if self.mode != "history":
            return tuple(q), tuple(v)
        next_v = tuple(v[i]+.5*(v[i]-previous_v[i])+.02*u[i] for i in range(2))
        next_q = tuple(q[i]+.02*next_v[i] for i in range(2))
        return next_q, next_v


class CountedRealLag(GuardLagPairBodyModel):
    def predict(self, q, v, u, previous_v):
        BUDGET["real_model_pair_attempts"] += 1
        try:
            result = super().predict(q, v, u, previous_v)
        except PairPredictionError as exc:
            BUDGET["real_model_scalar_attempts"] += exc.scalar_prediction_attempts
            BUDGET["real_model_scalar_successes"] += exc.scalar_prediction_successes
            raise
        BUDGET["real_model_pair_successes"] += 1
        BUDGET["real_model_scalar_attempts"] += 2
        BUDGET["real_model_scalar_successes"] += 2
        return result


def controller(model, candidates, horizon=1, **config):
    result = FixedGuardLagPairMPC(model, RANGES, MPCConfig(horizon=horizon, **config))
    result._candidates = tuple(candidates)  # tiny artificial fixtures only
    return result


def expect_error(kind, call):
    try:
        call()
    except kind:
        return
    raise AssertionError(f"expected {kind.__name__}")


def metadata_check():
    model = GuardLagPairBodyModel((0., 0.), public_joint_ranges=RANGES, trainable=False)
    before = model.parameter_fingerprint()
    mpc = FixedGuardLagPairMPC(model, RANGES)
    spec = mpc.spec()
    assert spec["config_per_axis"] == asdict(MPCConfig())
    assert mpc.config.horizon == 15 and len(mpc._candidates) == 81
    axis = (-.5, -.375, -.25, -.125, 0., .125, .25, .375, .5)
    assert mpc._axis_candidates == axis
    assert mpc._candidates == tuple((u0, u1) for u0 in axis for u1 in axis)
    assert mpc.forecast_bounds == ((-.15, .15), (-.15, .15))
    assert mpc.target_bounds == ((-.15, .15), (-.15, .15))
    assert spec["history"]["stored_in_model_or_controller"] is False
    assert str(inspect.signature(mpc.select)) == "(q, v, target_q, previous_v, *, previous_torque=(0.0, 0.0))"
    assert model.parameter_fingerprint() == before and model.update_count == 0
    return {"spec": spec, "model_unchanged": True, "prediction_calls": 0}


def history_cost_check():
    model = RecordingLag()
    candidates = ((.125, -.125), (-.125, .125))
    mpc = controller(model, candidates, horizon=3)
    q, v, history, target, previous_u = (.001, -.001), (.01, -.01), (.006, -.004), (.008, -.005), (.125, 0.)
    decision = mpc.select(q, v, target, history, previous_torque=previous_u)
    expected = []
    for index, u in enumerate(candidates):
        ref_q, ref_v, ref_prev = q, v, history
        path_q, path_v = [], []
        axis_cost = [mpc.config.change_weight*(u[i]-previous_u[i])**2 for i in range(2)]
        for step in range(3):
            call = model.calls[3*index+step]
            assert call["u"] == u
            for key, expected_pair in (("q", ref_q), ("v", ref_v), ("previous_v", ref_prev)):
                assert np.allclose(call[key], expected_pair, atol=1e-16, rtol=0)
            old_v = ref_v
            # Independent scalar arithmetic for this tiny hand fixture.
            ref_v = (1.5*ref_v[0]-.5*ref_prev[0]+.02*u[0],
                     1.5*ref_v[1]-.5*ref_prev[1]+.02*u[1])
            ref_q = (ref_q[0]+.02*ref_v[0], ref_q[1]+.02*ref_v[1])
            ref_prev = old_v
            BUDGET["hand_reference_pair_steps"] += 1
            BUDGET["hand_reference_scalar_velocity_steps"] += 2
            path_q.append(ref_q)
            path_v.append(ref_v)
            for i in range(2):
                axis_cost[i] += (mpc.config.position_weight*(ref_q[i]-target[i])**2
                                +mpc.config.velocity_weight*ref_v[i]**2
                                +mpc.config.effort_weight*u[i]**2)
            BUDGET["cost_reference_steps"] += 1
        expected.append((sum(axis_cost), sum(abs(x) for x in u), *u, tuple(path_q), tuple(path_v)))
        assert np.isclose(decision.candidate_records[index].cost, sum(axis_cost), atol=1e-18, rtol=0)
    chosen = min(expected)
    assert decision.torque == chosen[2:4]
    assert np.allclose(decision.predicted_q, chosen[4], atol=1e-16, rtol=0)
    assert np.allclose(decision.predicted_v, chosen[5], atol=1e-16, rtol=0)
    assert decision.pair_prediction_attempts == decision.pair_prediction_successes == 6
    assert decision.scalar_prediction_attempts == decision.scalar_prediction_successes == 12
    assert decision.feasible_candidates == 2 and not decision.fallback
    assert model.calls[0]["previous_v"] == model.calls[3]["previous_v"] == history
    assert tuple(decision.to_dict()) == tuple(item.name for item in fields(PairMPCDecision))
    return {"decision": decision.to_dict(), "calls": model.calls, "hand_reference": expected}


def tie_check():
    model = RecordingLag("stationary")
    mpc = controller(model, ((.125, 0.), (-.125, 0.), (0., .125), (0., -.125)),
                     effort_weight=0., change_weight=0.)
    signed = mpc.select((0., 0.), (0., 0.), (.01, 0.), (.01, -.01))
    assert signed.torque == (-.125, 0.) and signed.feasible_candidates == 4
    mpc._candidates = ((-.125, 0.), (-.0625, 0.))
    magnitude = mpc.select((0., 0.), (0., 0.), (.01, 0.), (.01, -.01))
    assert magnitude.torque == (-.0625, 0.)
    assert signed.pair_prediction_attempts == 4 and magnitude.pair_prediction_attempts == 2
    return {"signed": signed.to_dict(), "magnitude": magnitude.to_dict()}


def bounds_check():
    mpc = controller(RecordingLag("bounds"), ((-.125, 0.), (.125, 0.)), horizon=2)
    decision = mpc.select((0., 0.), (0., 0.), (0., 0.), (.01, -.01))
    assert decision.fallback and decision.torque == (0., 0.) and decision.cost is None
    assert not decision.predicted_q and not decision.predicted_v
    assert [x.rejection_reason for x in decision.candidate_records] == [
        "forecast_position_bounds", "forecast_velocity_bound"]
    assert all(x.completed_prediction_steps == 0 for x in decision.candidate_records)
    assert decision.pair_prediction_attempts == decision.pair_prediction_successes == 2
    assert decision.scalar_prediction_attempts == decision.scalar_prediction_successes == 4
    return decision.to_dict()


def mixed_failure_check():
    mpc = controller(RecordingLag("mixed_errors"), ((-.125, 0.), (.125, 0.), (0., 0.)))
    decision = mpc.select((0., 0.), (0., 0.), (0., 0.), (.01, -.01))
    assert decision.torque == (0., 0.) and not decision.fallback
    assert (decision.pair_prediction_attempts, decision.pair_prediction_successes) == (3, 1)
    assert (decision.scalar_prediction_attempts, decision.scalar_prediction_successes) == (4, 3)
    assert decision.failed_pair_prediction_attempts == 2
    assert not decision.scalar_counts_complete and decision.scalar_counts_is_lower_bound
    assert decision.unknown_scalar_failure_count == 1
    assert [x.scalar_counts_complete for x in decision.candidate_records] == [False, True, True]
    return decision.to_dict()


def fatal_failure_check(mode):
    mpc = controller(RecordingLag(mode), ((0., 0.), (.125, 0.)))
    try:
        mpc.select((0., 0.), (0., 0.), (0., 0.), (.01, -.01))
    except OSError as exc:
        ledger = exc.pair_planning_accounting
    else:
        raise AssertionError("original OSError must propagate")
    known = mode == "fatal_known"
    assert ledger == {
        "pair_prediction_attempts": 2, "pair_prediction_successes": 1,
        "scalar_prediction_attempts": 4 if known else 2,
        "scalar_prediction_successes": 3 if known else 2,
        "failed_pair_prediction_attempts": 1, "scalar_counts_complete": known,
        "scalar_counts_is_lower_bound": not known, "unknown_scalar_failure_count": 0 if known else 1}
    return ledger


def input_validation_check():
    model = RecordingLag()
    mpc = controller(model, ((0., 0.),))
    call = lambda history: mpc.select((0., 0.), (0., 0.), (0., 0.), history)
    for invalid in (None, (0.,), (float("nan"), 0.), (True, 0.)):
        expect_error(ValueError, lambda value=invalid: call(value))
    expect_error(TypeError, lambda: mpc.select((0., 0.), (0., 0.), (0., 0.)))
    expect_error(ValueError, lambda: mpc.select((0., 0.), (0., 0.), (0., 0.), (0., 0.), previous_torque=(.51, 0.)))
    expect_error(ValueError, lambda: mpc.select((0., 0.), (0., 0.), (.151, 0.), (0., 0.)))
    expect_error(TypeError, lambda: FixedGuardLagPairMPC(object(), RANGES))
    expect_error(ValueError, lambda: FixedGuardLagPairMPC(model, ((1., -1.), (-1., 1.))))
    assert model.calls == []
    return {"rejected_inputs": 9, "prediction_calls": 0}


def real_frozen_prior_check():
    model = CountedRealLag((0., 0.), public_joint_ranges=RANGES, trainable=False)
    before = model.parameter_fingerprint()
    mpc = controller(model, ((.125, -.125),), horizon=2)
    decision = mpc.select((0., 0.), (.01, -.01), (.005, -.005), (.008, -.006))
    assert decision.pair_prediction_attempts == decision.pair_prediction_successes == 2
    assert decision.scalar_prediction_attempts == decision.scalar_prediction_successes == 4
    assert decision.torque == (.125, -.125)
    assert np.allclose(decision.predicted_v, ((.0125, -.0125), (.015, -.015)), atol=1e-16, rtol=0)
    assert model.parameter_fingerprint() == before and model.update_count == 0
    return {"decision": decision.to_dict(), "model_unchanged": True, "fingerprint": before}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    sources = {}
    for source in (Path(__file__), Path(__file__).with_name("guard_lag_pair_mpc.py")):
        copied = args.output/source.name
        shutil.copyfile(source, copied)
        sources[source.name] = hashlib.sha256(copied.read_bytes()).hexdigest()
    started_wall, started_cpu = time.perf_counter(), time.process_time()
    outcomes = []
    checks = (
        ("default_metadata_no_math", metadata_check),
        ("history_candidate_reset_and_original_cost", history_cost_check),
        ("exact_cost_signed_and_magnitude_tie", tie_check),
        ("forecast_limits_and_fallback", bounds_check),
        ("known_and_unknown_prediction_failure", mixed_failure_check),
        ("fatal_known_accounting", lambda: fatal_failure_check("fatal_known")),
        ("fatal_unknown_accounting", lambda: fatal_failure_check("fatal_unknown")),
        ("required_history_and_input_validation", input_validation_check),
        ("real_zero_lag_frozen_prior", real_frozen_prior_check),
    )
    for name, check in checks:
        before = BUDGET.copy()
        try:
            detail = check()
            outcome = {"name": name, "passed": True, "detail": detail}
        except BaseException as exc:
            outcome = {"name": name, "passed": False, "error_type": type(exc).__name__,
                       "message": str(exc), "traceback": traceback.format_exc()}
        outcome["new_budget"] = {key: BUDGET[key]-before[key] for key in BUDGET}
        outcomes.append(outcome)
    report = {"source_sha256": sources, "python": sys.version,
              "platform": platform.platform(), "numpy": np.__version__,
              "wall_seconds": time.perf_counter()-started_wall,
              "cpu_seconds": time.process_time()-started_cpu,
              "passed": sum(x["passed"] for x in outcomes),
              "failed": sum(not x["passed"] for x in outcomes),
              "budget": BUDGET, "outcomes": outcomes}
    (args.output/"run.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("passed", "failed", "budget", "wall_seconds", "cpu_seconds")}, indent=2))
    return int(report["failed"] != 0)


if __name__ == "__main__":
    raise SystemExit(main())
