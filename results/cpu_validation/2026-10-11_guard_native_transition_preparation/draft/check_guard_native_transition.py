"""Only K's six new synthetic branches or one manual multi-output ridge case."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import numpy as np


STAGING = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("staged_K", STAGING/"develop_guard_native_transition.py")
K = importlib.util.module_from_spec(spec)
spec.loader.exec_module(K)
RIDGE_COST = Counter()


class SyntheticGuard:
    """Known interior synthetic q; records causal current inputs, no data reader."""
    def __init__(self):
        self.inputs = []

    def project(self, q, u):
        self.inputs.append((np.asarray(q).copy(), np.asarray(u).copy()))
        class Result:
            projected_start_nm = tuple(float(v) for v in np.clip(u, -.5, .5))
        return Result()


def observation(q, v, gyro=(.1, .2, .3), acceleration=(.981, 1.962, 2.943)):
    return {"joint_position": [float(x) for x in q], "joint_velocity": [float(x) for x in v],
            "imu_gyro": [float(x) for x in gyro], "imu_acceleration": [float(x) for x in acceleration]}


def branch_state_prior():
    cost, guard = Counter(), SyntheticGuard()
    qref, displacement, velocity = np.arange(8)/10, np.arange(1, 9)/100, np.arange(1, 9)/10
    obs = observation(qref+displacement, velocity)
    x = K.encode_state(obs, qref, cost)
    phi, prior = K.feature_and_prior(x, (.04, .05), (.4, -.3, 0, 0, 0, 0, 0, 0), qref, guard, cost, "synthetic")
    np.testing.assert_allclose(x, [*displacement, *velocity, .1, .2, .3, .1, .2, .3])
    np.testing.assert_allclose(phi, [*x, .4, -.3, .15, -.05, 1, velocity[0]-.04, velocity[1]-.05])
    np.testing.assert_allclose(prior[:8], displacement+.02*velocity)
    np.testing.assert_allclose(prior[8:10], velocity[:2]+.02*np.asarray((.4, -.3)))
    np.testing.assert_allclose(prior[10:], x[10:])
    assert len(K.STATE_NAMES) == 22 and len(K.FEATURE_NAMES) == 29
    assert cost["synthetic_prior_scalar_outputs"] == 22
    return dict(cost)


def branch_full_qref():
    qref, rows = tuple((i+1)/20 for i in range(8)), {}
    obs = observation(qref, np.arange(8)/100)
    for step in range(100):
        rows[step] = {"trial_id": "seed0_calibration_sparse", "step_index": step,
            "phase": "prefix", "shared_transition_id": f"seed0_calibration_sparse:{step}",
            "observation_before": obs, "observation_after": obs, "study_abort": None,
            "diagnostics": {"executed_substeps": 10, "terminated": False}}
    actual, source = K.prefix_qref(rows)
    assert actual == qref and source == "seed0_calibration_sparse:99" and actual[7] != 0
    del rows[42]
    try:
        K.prefix_qref(rows)
    except ValueError as exc:
        assert str(exc) == "full100_unstopped_prefix_required"
    else:
        raise AssertionError("unknown full eight-axis qref was accepted")
    return {"synthetic_prefix_rows": 100, "unknown_qref_rejected": True}


def branch_closed22():
    cost, guard = Counter(), SyntheticGuard()
    x = np.zeros(22)
    x[7], x[8], x[9], x[15], x[16], x[21] = .2, .3, -.1, .4, .5, .1
    previous = np.asarray((.25, -.15))
    weights = np.zeros((29, 22))
    weights[16, 8], weights[8, 16], weights[27, 9], weights[7, 21] = .1, .5, .2, .3
    request = (.1, -.1, 0, 0, 0, 0, 0, 0)
    outcome = K.rollout22(x, previous, [request]*3, np.zeros(8), guard, weights, cost, "learned22")
    manual, old_previous, expected = x.copy(), previous.copy(), []
    for _ in range(3):
        old = manual.copy()
        manual[:8] = old[:8]+.02*old[8:16]
        manual[8] = old[8]+.02*.1+.1*old[16]
        manual[9] = old[9]-.02*.1+.2*(old[8]-old_previous[0])
        manual[16] = old[16]+.5*old[8]
        manual[21] = old[21]+.3*old[7]
        old_previous = old[8:10].copy()
        expected.append(manual.copy())
    assert outcome["available"]
    np.testing.assert_allclose(outcome["predicted_path_x22"], expected)
    np.testing.assert_allclose(guard.inputs[1][0], expected[0][:2])
    assert outcome["terminal_x22"][7] != x[7] and outcome["terminal_x22"][21] != x[21]
    assert cost["learned22_transition_returns"] == 3 and cost["learned22_residual_scalar_head_returns"] == 66
    return dict(cost)


def branch_D11_own_history():
    class Pair:
        def __init__(self):
            self.inputs = []

        def predict(self, q, v, u, previous):
            self.inputs.append((tuple(q), tuple(v), tuple(previous)))
            next_v = [v[i]+.1*(v[i]-previous[i])+u[i] for i in range(2)]
            return [q[i]+.02*next_v[i] for i in range(2)], next_v
    pair, cost = Pair(), Counter()
    q, v, previous = (.2, -.2), (.3, -.1), (.25, -.15)
    requests = [( .01, -.02, 0, 0, 0, 0, 0, 0)]*3
    outcome = K.rollout11(pair, q, v, previous, requests, cost)
    manual_q, manual_v, manual_previous, expected = list(q), list(v), list(previous), []
    for _ in range(3):
        old_v = manual_v[:]
        manual_v = [old_v[i]+.1*(old_v[i]-manual_previous[i])+requests[0][i] for i in range(2)]
        manual_q = [manual_q[i]+.02*manual_v[i] for i in range(2)]
        manual_previous = old_v
        expected.append([manual_q[:], manual_v[:]])
    assert outcome["available"]
    np.testing.assert_allclose(outcome["predicted_path_qv"], expected)
    assert pair.inputs[1][2] == v and pair.inputs[2][2] == tuple(expected[0][1])
    assert cost["D11_pair_prediction_returns"] == 3 and cost["D11_scalar_prediction_returns"] == 6
    return dict(cost)


def branch_all_horizon_gate():
    groups = []
    for seed in K.SEEDS:
        for horizon in K.HORIZONS:
            for name in K.PREDICTORS:
                for channel in (range(22) if name != "D11" else (0, 1, 8, 9)):
                    groups.append({"seed": seed, "horizon": horizon, "predictor": name,
                        "channel_index": channel, "full_fixed_count": True, "source_active_count": 100,
                        "usable_count": 101-horizon,
                        "metric": {"rmse": .75 if name == "learned22" else 1.0}})
    assert K.development_gate(groups)["passed"]
    selected = next(g for g in groups if (g["seed"], g["horizon"], g["predictor"], g["channel_index"]) == (0, 5, "learned22", 9))
    selected["metric"]["rmse"] = 1.01
    assert not K.development_gate(groups)["passed"]
    selected["metric"]["rmse"] = .75
    selected["full_fixed_count"] = False
    gate = K.development_gate(groups)
    assert not gate["passed"] and not gate["evaluated"]
    selected["full_fixed_count"] = True
    base = next(g for g in groups if (g["seed"], g["horizon"], g["predictor"], g["channel_index"]) == (0, 1, "D11", 8))
    base["metric"]["rmse"] = 0.
    assert not K.development_gate(groups)["evaluated"]
    return {"fixed_horizons": list(K.HORIZONS), "no_worse_failure": True,
            "missing_count_failure": True, "zero_D11_undefined": True, "scientific_adoption": False}


def branch_transition_failure():
    cost, guard = Counter(), SyntheticGuard()
    x = np.zeros(22)
    x[16] = 2.
    weights = np.zeros((29, 22))
    weights[16, 8] = 1.e308
    outcome = K.rollout22(x, (0, 0), [(0,)*8], np.zeros(8), guard, weights, cost, "learned22")
    assert not outcome["available"] and outcome["predicted_path_x22"] == []
    assert cost["learned22_transition_attempts"] == cost["learned22_transition_failures"] == 1
    assert cost["learned22_transition_returns"] == 0
    assert cost["learned22_residual_vector_attempts"] == cost["learned22_residual_vector_returns"] == 1
    assert cost["learned22_prior_scalar_outputs"] == 22
    return {"prediction": outcome, "cost": dict(cost)}


def branch_checks(repair_only=False):
    checks = []
    functions = (branch_state_prior, branch_full_qref) if repair_only else (
        branch_state_prior, branch_full_qref, branch_closed22,
        branch_D11_own_history, branch_all_horizon_gate, branch_transition_failure)
    for function in functions:
        try:
            checks.append({"name": function.__name__, "passed": True, "result": function()})
        except Exception as exc:
            checks.append({"name": function.__name__, "passed": False,
                           "failure": f"{type(exc).__name__}:{exc}"})
    return {"synthetic_only": True, "branch_count": len(checks), "checks": checks,
            "repair_only": repair_only,
            "passed": all(r["passed"] for r in checks), "actual_ridge_solves": 0,
            "physics_calls": 0, "real_trace_or_snapshot_reads": 0, "RLS_updates": 0}


def ridge_check():
    """Orthogonal single-column rows: every expected coefficient is manual."""
    phi = np.zeros((400, 29))
    repetitions = [0]*29
    for row in range(400):
        column = row % 29
        phi[row, column] = (column+1)/10
        repetitions[column] += 1
    target = np.asarray([[(column+1)*(head+1)/1000 for head in range(22)] for column in range(29)])
    labels = phi @ target
    diagonal = np.asarray([repetitions[i]*((i+1)/10)**2 for i in range(29)])
    expected = (diagonal/(diagonal+.01))[:, None]*target
    cost = RIDGE_COST
    fitted, artifacts = K.fit_transition(phi, labels, cost)
    np.testing.assert_allclose(fitted, expected, atol=2.e-14, rtol=2.e-14)
    np.testing.assert_allclose(artifacts["gram29x29"], np.diag(diagonal), atol=3.e-13, rtol=2.e-14)
    assert cost["fit_shared_29x29_22rhs_solve_attempts"] == cost["fit_shared_29x29_22rhs_solve_returns"] == 1
    assert cost["fit_scalar_labels"] == 8800 and cost["transition_scalar_coefficients_fitted"] == 638
    return {"synthetic_only": True, "passed": True, "manual_design": "400 orthogonal single-column rows; diagonal_j=n_j*((j+1)/10)^2",
        "manual_coefficient_formula": "diagonal_j/(diagonal_j+.01)*target_jk",
        "max_absolute_coefficient_error": float(np.max(np.abs(fitted-expected))),
        "expected_weights29x22": expected.tolist(), "fit": artifacts, "cost": dict(cost),
        "actual_ridge_solves": 1, "physics_calls": 0, "real_trace_or_snapshot_reads": 0, "RLS_updates": 0}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("branches", "ridge", "repair_native_fixture"), required=True)
    args = parser.parse_args()
    names = {"branches": "CHECK_01.json", "ridge": "CHECK_RIDGE_01.json",
             "repair_native_fixture": "CHECK_NATIVE_FIXTURE_REPAIR_01.json"}
    path = STAGING/names[args.mode]
    if path.exists():
        raise FileExistsError("preserve first check output; no overwrite/rerun")
    hashes = {name: hashlib.sha256((STAGING/name).read_bytes()).hexdigest() for name in (
        "develop_guard_native_transition.py", "GUARD_NATIVE_TRANSITION_DEVELOPMENT_PROTOCOL.md", "check_guard_native_transition.py")}
    try:
        result = ridge_check() if args.mode == "ridge" else branch_checks(args.mode == "repair_native_fixture")
    except BaseException as exc:
        result = {"passed": False, "synthetic_only": True, "failure": f"{type(exc).__name__}:{exc}"}
        if args.mode == "ridge":
            result.update(cost=dict(RIDGE_COST), actual_ridge_solves=RIDGE_COST["fit_shared_29x29_22rhs_solve_attempts"],
                          physics_calls=0, real_trace_or_snapshot_reads=0, RLS_updates=0)
    result["source_sha256"] = hashes
    result["runtime"] = {"python": sys.version, "numpy": np.__version__}
    path.write_bytes(K.json_bytes(result))
    print(json.dumps({key: value for key, value in result.items() if key != "fit" and key != "expected_weights29x22"},
                     ensure_ascii=False, indent=2, allow_nan=False))
    if not result["passed"]:
        raise SystemExit(1)
