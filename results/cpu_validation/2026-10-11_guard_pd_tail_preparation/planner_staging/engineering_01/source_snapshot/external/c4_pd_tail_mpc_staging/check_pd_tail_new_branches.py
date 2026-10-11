"""Small new-tail-only mathematical checks, with an explicit synthetic double.

Never imports or calls the old MPC select fixture. Never reads any experiment
archive, fits a body model, runs physics, or allows a formal experiment.
"""
from __future__ import annotations

import importlib.util
import json
import math
from pathlib import Path
import sys
import time

import numpy as np

from developmental_physics.guard_lag_pair_model import GuardLagPairBodyModel
from developmental_physics.local_model import MPCConfig


module_path = Path(__file__).with_name("pd_tail_pair_mpc.py")
module_spec = importlib.util.spec_from_file_location("draft_pd_tail_new_math", module_path)
draft = importlib.util.module_from_spec(module_spec)
sys.modules[module_spec.name] = draft
module_spec.loader.exec_module(draft)


Q = (.005, -.009)
V = (.012, -.016)
PREVIOUS_V = (.009, -.010)
TARGET = (.010, -.012)
PREVIOUS_TORQUE = (.125, -.125)
RANGES = ((-1., 1.), (-1., 1.))
LEDGER = {"synthetic_model_pair_calls": 0, "synthetic_model_scalar_outputs": 0,
          "independent_H1_reference_pair_calculations": 0,
          "independent_H1_reference_scalar_calculations": 0,
          "independent_tail_request_vector_calculations": 0,
          "independent_stage_cost_endpoint_calculations": 0,
          "parameter_fingerprint_calls": 0,
          "physics_steps": 0, "archive_reads": 0, "model_updates": 0,
          "old_MPC_select_calls": 0, "old_fixture_runs": 0}


class SyntheticLagDouble(GuardLagPairBodyModel):
    """No fitted dynamics; record a modest deterministic recurrence for checks."""

    def __init__(self):
        super().__init__((0., 0.), public_joint_ranges=RANGES, trainable=False)
        self.calls = []

    def predict(self, q, v, u, previous_v):
        LEDGER["synthetic_model_pair_calls"] += 1
        LEDGER["synthetic_model_scalar_outputs"] += 2
        next_v = (.6*v[0]+.01*u[0]+.05*(v[1]-previous_v[1]),
                  .7*v[1]+.012*u[1]+.04*(v[0]-previous_v[0]))
        next_q = (q[0]+.02*next_v[0], q[1]+.02*next_v[1])
        self.calls.append({"q": tuple(q), "v": tuple(v), "u": tuple(u),
                           "previous_v": tuple(previous_v),
                           "next_q": next_q, "next_v": next_v})
        return next_q, next_v

    def update(self, *args, **kwargs):
        raise AssertionError("new-tail checks must never update any model")


def close(actual, expected):
    assert math.isclose(actual, expected, rel_tol=0., abs_tol=1.e-12), (actual, expected)


def reference_H1(q, v, u, previous_v):
    LEDGER["independent_H1_reference_pair_calculations"] += 1
    LEDGER["independent_H1_reference_scalar_calculations"] += 2
    # Independent expression for the synthetic recurrence; no controller/model call.
    velocity0 = .6*v[0]+.01*u[0]+.05*(v[1]-previous_v[1])
    velocity1 = .7*v[1]+.012*u[1]+.04*(v[0]-previous_v[0])
    return (q[0]+.02*velocity0, q[1]+.02*velocity1), (velocity0, velocity1)


def reference_tail(q, v):
    LEDGER["independent_tail_request_vector_calculations"] += 1
    raw = (64.*(TARGET[0]-q[0]), 64.*(TARGET[1]-q[1])-4.*v[1])
    return tuple(max(-.5, min(.5, x)) for x in raw)


def reference_cost(first, qv_requests, cfg):
    costs = [cfg.change_weight*(first[i]-PREVIOUS_TORQUE[i])**2 for i in range(2)]
    for q, v, request in qv_requests:
        LEDGER["independent_stage_cost_endpoint_calculations"] += 1
        for i in range(2):
            costs[i] += (cfg.position_weight*(q[i]-TARGET[i])**2
                         +cfg.velocity_weight*v[i]**2+cfg.effort_weight*request[i]**2)
    return costs[0]+costs[1]


def evaluate(horizon):
    model = SyntheticLagDouble()
    cfg = MPCConfig(horizon=horizon)
    controller = draft.FixedPDTailGuardLagPairMPC(model, RANGES, cfg)
    LEDGER["parameter_fingerprint_calls"] += 1
    fingerprint = model.parameter_fingerprint()
    decision = controller.select(Q, V, TARGET, PREVIOUS_V, previous_torque=PREVIOUS_TORQUE)
    LEDGER["parameter_fingerprint_calls"] += 1
    assert fingerprint == model.parameter_fingerprint()
    assert model.update_count == 0
    assert not decision.fallback and decision.feasible_candidates == 81
    assert len(model.calls) == 81*horizon
    assert decision.pair_prediction_attempts == len(model.calls)
    assert decision.scalar_prediction_attempts == 2*len(model.calls)
    return controller, model, decision


def inspect_candidate_history(controller, model, horizon):
    for index, first in enumerate(controller._candidates):
        calls = model.calls[index*horizon:(index+1)*horizon]
        assert calls[0]["q"] == Q and calls[0]["v"] == V
        assert calls[0]["previous_v"] == PREVIOUS_V and calls[0]["u"] == first
        for stage in range(1, horizon):
            current, prior = calls[stage], calls[stage-1]
            assert current["q"] == prior["next_q"] and current["v"] == prior["next_v"]
            assert current["previous_v"] == prior["v"]
            assert current["u"] == reference_tail(current["q"], current["v"])


def inspect_selected_cost(controller, model, decision, horizon):
    index = controller._candidates.index(decision.torque)
    calls = model.calls[index*horizon:(index+1)*horizon]
    assert decision.trajectory_requested_torque == tuple(c["u"] for c in calls)
    assert decision.predicted_q == tuple(c["next_q"] for c in calls)
    assert decision.predicted_v == tuple(c["next_v"] for c in calls)
    expected = reference_cost(decision.torque,
        [(c["next_q"], c["next_v"], c["u"]) for c in calls], controller.config)
    close(decision.cost, expected)
    # Discriminate stage effort from incorrectly charging the first request at every stage.
    wrong = reference_cost(decision.torque,
        [(c["next_q"], c["next_v"], decision.torque) for c in calls], controller.config)
    assert abs(expected-wrong) > 1.e-12
    assert decision.trajectory_requested_torque[0] == decision.torque
    assert all(abs(x) <= .5 for u in decision.trajectory_requested_torque for x in u)
    assert decision.to_dict()["trajectory_requested_torque"] == decision.trajectory_requested_torque


def check_H1_degenerates():
    controller, model, decision = evaluate(1)
    expected = []
    for first in controller._candidates:
        q, v = reference_H1(Q, V, first, PREVIOUS_V)
        cost = reference_cost(first, [(q, v, first)], controller.config)
        expected.append((cost, abs(first[0])+abs(first[1]), first[0], first[1]))
    selected = min(expected)
    assert decision.torque == (selected[2], selected[3])
    close(decision.cost, selected[0])
    assert decision.trajectory_requested_torque == (decision.torque,)
    assert LEDGER["independent_tail_request_vector_calculations"] == 0
    assert all(c["q"] == Q and c["v"] == V and c["previous_v"] == PREVIOUS_V for c in model.calls)


CHECKS = []


def checked(name, function):
    try:
        function()
    except BaseException as exc:
        CHECKS.append({"name": name, "passed": False, "error": f"{type(exc).__name__}: {exc}"})
        raise
    else:
        CHECKS.append({"name": name, "passed": True})


def main():
    assert draft.FORMAL_PD_TAIL_CONTROL_ENABLED is False
    assert draft.TAIL_KP == (64., 64.) and draft.TAIL_KD == (0., 4.)
    checked("H1_new_tail_degenerates_to_first_request_only_manual_reference", check_H1_degenerates)
    for horizon in (2, 15):
        controller, model, decision = evaluate(horizon)
        checked(f"H{horizon}_candidate_own_history_and_candidate_isolation",
                lambda: inspect_candidate_history(controller, model, horizon))
        checked(f"H{horizon}_selected_request_trajectory_stage_effort_and_first_only_change",
                lambda: inspect_selected_cost(controller, model, decision, horizon))
    return {"schema_version": 1, "checks": CHECKS,
            "check_count": len(CHECKS), "failed": sum(not x["passed"] for x in CHECKS),
            "fixture": "three synthetic evaluations only: H1/H2/H15, 81 candidates each",
            "candidate_selected": False, "formal_experiment_enabled": False,
            "cost": LEDGER}


if __name__ == "__main__":
    started_wall, started_cpu = time.perf_counter(), time.process_time()
    try:
        report = main()
    except BaseException:
        print(json.dumps({"schema_version": 1, "checks": CHECKS, "cost": LEDGER,
            "execution": {"wall_seconds": time.perf_counter()-started_wall,
                          "cpu_seconds": time.process_time()-started_cpu}}, indent=2))
        raise
    report["execution"] = {"wall_seconds": time.perf_counter()-started_wall,
                           "cpu_seconds": time.process_time()-started_cpu,
                           "python": sys.version, "numpy": np.__version__}
    print(json.dumps(report, indent=2))
