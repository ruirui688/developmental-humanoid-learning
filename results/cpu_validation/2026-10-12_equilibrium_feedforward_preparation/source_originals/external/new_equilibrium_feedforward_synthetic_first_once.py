"""Prepare-only until root explicitly executes this bounded new-math check.

No raw/results/checkpoints are read. Cases use synthetic coefficient fixtures;
there is no simulator, physics, fitting, RLS or old experiment/audit replay.
An existing capture directory is always refused, including a failed first run.
"""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import traceback


def run_cases(repo):
    import numpy as np
    sys.path.insert(0, str(repo / "src"))
    from developmental_physics.equilibrium_feedforward_pair import (
        EquilibriumFeedforwardPairMPC, ROOT_ACCOUNTING_KEYS, FORECAST_ACCOUNTING_KEYS,
        equilibrium_feedback_request, solve_equilibrium_root,
    )
    from developmental_physics.fast_feedback_pair_model import FastFeedbackGuardCoupledPairBodyModel
    from developmental_physics.guard_pair_model import KnownAngleGuard
    from developmental_physics.local_pair_model import PairPredictionError, _parameter_state

    ranges, reference = ((-1., 1.), (-1., 1.)), (0., 0.)
    root_totals = Counter({key: 0 for key in ROOT_ACCOUNTING_KEYS})
    forecast_totals = Counter({key: 0 for key in FORECAST_ACCOUNTING_KEYS})
    initialization_totals, checks, cases = Counter(), [], []
    fixture_builds, fixture_assignments = 0, 0

    def progress():
        return {"cases": list(cases), "checks": list(checks),
                "root_accounting": dict(root_totals), "forecast_accounting": dict(forecast_totals),
                "initialization_accounting": dict(initialization_totals),
                "fixture_model_builds": fixture_builds, "fixture_parameter_assignments": fixture_assignments,
                "numpy_version": np.__version__, "physics_calls": 0, "fit_calls": 0, "RLS_updates": 0,
                "raw_or_result_reads": 0, "checkpoint_reads": 0, "old_case_replays": 0}

    def check(name, condition):
        checks.append({"name": name, "passed": bool(condition)})
        if not condition:
            failure = AssertionError(name)
            failure.synthetic_partial_result = progress()
            raise failure

    def close(name, actual, expected):
        check(name, np.allclose(actual, expected, rtol=0., atol=2e-12))

    def theta(action=None, constant=(0., 0.), hinge=None):
        values = np.zeros((2, 9))
        values[0, 0], values[1, 1] = 1., 1.
        if action is not None:
            values[:, 4:6] = action
        if hinge is not None:
            values[:, 6:8] = hinge
        values[:, 8] = constant
        return values

    def fixture(coefficients, cls=FastFeedbackGuardCoupledPairBodyModel):
        nonlocal fixture_builds, fixture_assignments
        fixture_builds += 1
        model = cls(reference, public_joint_ranges=ranges, trainable=False)
        model._state = _parameter_state(np.asarray(coefficients, dtype=float).copy(),
                                        model._state.covariance.copy(), 0)
        fixture_assignments += 1
        return model

    def solve(values, target=(.04, .04), predictor=None):
        try:
            result = solve_equilibrium_root(values, reference, ranges, target, predictor=predictor)
        except BaseException as exc:
            root_totals.update(getattr(exc, "equilibrium_root_accounting", {}))
            raise
        root_totals.update(result.accounting)
        check("solve_complete_sixteen_branches", len(result.records) == 16)
        check("solve_svd_count_sixteen", result.accounting["branch_svd_attempts"] == 16)
        check("solve_model_verification_bounded", result.accounting["root_model_pair_prediction_attempts"] <= 16)
        return result

    def controller(model):
        result = EquilibriumFeedforwardPairMPC(model, ranges)
        initialization_totals.update(result.initialization_accounting)
        return result

    def select(control, q=(0., 0.), v=(0., 0.), target=(.04, .04)):
        try:
            decision = control.select(q, v, target)
        except BaseException as exc:
            attached = getattr(exc, "equilibrium_accounting", {})
            root_totals.update(attached.get("root", {}))
            forecast_totals.update(attached.get("forecast", {}))
            raise
        root_totals.update(decision.root_accounting)
        forecast_totals.update(decision.forecast_accounting)
        check("decision_root_forecast_pair_sum", decision.pair_prediction_attempts ==
              decision.root_accounting["root_model_pair_prediction_attempts"]+
              decision.forecast_accounting["pair_prediction_attempts"])
        check("decision_root_forecast_scalar_sum", decision.scalar_prediction_attempts ==
              decision.root_accounting["root_model_scalar_prediction_attempts"]+
              decision.forecast_accounting["scalar_prediction_attempts"])
        check("decision_no_cost_optimization", decision.cost is None)
        check("decision_one_forecast_record", len(decision.candidate_records) == 1)
        return decision

    def case(name, function):
        start = len(checks)
        try:
            function()
        except BaseException as exc:
            cases.append({"name": name, "passed": False, "checks": len(checks)-start})
            exc.synthetic_partial_result = progress()
            raise
        cases.append({"name": name, "passed": True, "checks": len(checks)-start})
        print(name+": passed", flush=True)

    def cold_zero_cache():
        model = fixture(theta(np.eye(2)*.002))
        result = solve(model.coefficients, predictor=model.predict)
        check("cold_has_zero_root", result.has_root)
        close("cold_root_exact_zero", result.request_nm, (0., 0.))
        control = controller(model)
        first, cached = select(control), select(control)
        switched = select(control, target=(.08, .08))
        check("cold_forecast_feasible", not first.fallback)
        close("cold_hold_zero", first.selected_residual_nm, (0., 0.))
        check("cache_latest_target_hit", cached.root_cache_hit)
        check("cache_no_repeated_root_charge", cached.root_accounting["root_solve_attempts"] == 0)
        check("changed_target_new_inverse", not switched.root_cache_hit and switched.root_accounting["root_solve_attempts"] == 1)
        close("single_final_clip_semantics", equilibrium_feedback_request((0., 0.), (0., 0.), (.04, .04), (-.2, -.2)), (.5, .5))
        check("cached_forecast_still_charged", cached.forecast_accounting["pair_prediction_attempts"] == 150)

    def coupled_full_rank():
        action, expected = np.asarray(((1., .5), (.25, 2.))), np.asarray((.1, -.2))
        values = theta(action, -(action @ expected))
        model = fixture(values)
        result = solve(values, predictor=model.predict)
        check("coupled_has_root", result.has_root)
        close("coupled_joint_inverse", result.request_nm, expected)
        check("coupled_rank2_all", result.accounting["branch_rank2"] == 16)

    def rank_one_box():
        action = np.asarray(((1., 2.), (2., 4.)))
        values = theta(action, (-1.4, -2.8))
        result = solve(values)
        check("rank1_intersects_box", result.has_root)
        close("rank1_box_constrained_minimum", result.request_nm, (.4, .5))
        check("rank1_sixteen", result.accounting["branch_rank1"] == 16)
        continuous = solve(theta(((1., 1.), (2., 2.)), (-.5, -1.)))
        close("rank1_continuous_global_minimum", continuous.request_nm, (.25, .25))

    def rank_zero():
        all_roots = solve(theta())
        check("rank0_complete_continuous_roots", all_roots.has_root and all_roots.accounting["branch_rank0"] == 16)
        close("rank0_minimum_norm_zero", all_roots.request_nm, (0., 0.))
        absent = solve(theta(constant=(.01, -.02)))
        check("rank0_no_root", not absent.has_root and absent.request_nm is None)
        check("rank0_no_zero_residual_fabricated", absent.accounting["root_feasible_branch_roots"] == 0)

    def hinge_boundary():
        values = theta(np.eye(2)*.5, (-.125, .125), np.eye(2))
        model = fixture(values)
        result = solve(values, predictor=model.predict)
        close("hinge_quarter_boundary", result.request_nm, (.25, -.25))
        check("hinge_repeated_boundary_roots_retained", result.accounting["root_feasible_branch_roots"] >= 2)
        check("hinge_complete_model_return_accounting", result.accounting["root_model_pair_prediction_returns"] ==
              result.accounting["root_model_pair_prediction_attempts"])

    def guard_equality():
        equal = (-.97, .97)
        values = theta(np.eye(2), (.1, -.1))
        absent = solve(values, target=equal)
        check("guard_equality_outward_root_blocked", not absent.has_root)
        inside = (float(np.nextafter(equal[0], np.inf)), float(np.nextafter(equal[1], -np.inf)))
        result = solve(values, target=inside)
        close("guard_just_inside_outward_root", result.request_nm, (-.1, .1))
        check("guard_equal_projection", KnownAngleGuard(ranges).project(equal, (-.1, .1)).projected_start_nm == (0., 0.))
        check("guard_blocked_branch_rank_retained", absent.accounting["branch_rank0"] > 0)

    def no_root_hold_zero():
        model = fixture(theta(constant=(.002, .002)))
        decision = select(controller(model))
        check("no_root_still_finite_PD_forecast", not decision.root_result.has_root and not decision.fallback)
        close("no_root_held_request_zero", decision.selected_residual_nm, (0., 0.))
        close("no_root_actor_PD", decision.torque, (.5, .5))
        check("no_root_not_partial_population", len(decision.root_result.records) == 16)

    def finite_forecast_fallback():
        model = fixture(theta(np.eye(2), (2., 0.)))
        decision = select(controller(model))
        check("forecast_velocity_fallback", decision.fallback and decision.candidate_records[0].rejection_reason == "forecast_velocity_bound")
        check("forecast_literal_zero", decision.torque == (0., 0.) and decision.selected_residual_nm is None)
        check("forecast_paid_first_prediction", decision.forecast_accounting["pair_prediction_attempts"] == 1)
        check("forecast_no_partial_trajectory", decision.predicted_q == () and decision.predicted_v == ())

    def nonfinite_and_technical():
        bad = theta(np.eye(2))
        bad[0, 4] = np.nan
        for name, values, target, predictor in (
            ("nonfinite_coefficients", bad, (.04, .04), None),
            ("nonfinite_target", theta(np.eye(2)), (np.nan, .04), None),
            ("nonfinite_predictor_return", theta(np.eye(2)), (.04, .04), lambda q, v, u: (q, (np.inf, 0.))),
        ):
            try:
                solve(values, target=target, predictor=predictor)
            except ValueError as exc:
                check(name+"_raises", True)
                check(name+"_keeps_root_failure", exc.equilibrium_root_accounting["root_solve_failures"] == 1)
            else:
                check(name+"_raises", False)

        class BrokenForecast(FastFeedbackGuardCoupledPairBodyModel):
            def predict(self, q, v, u):
                if tuple(q) == (0., 0.):
                    raise PairPredictionError(ValueError("synthetic_nonfinite_forecast"), 1, 0, "velocity_output_0")
                return super().predict(q, v, u)

        control = controller(fixture(theta(np.eye(2)*.002), cls=BrokenForecast))
        try:
            select(control)
        except PairPredictionError as exc:
            check("forecast_technical_error_not_fallback", True)
            accounting = exc.equilibrium_accounting["forecast"]
            check("forecast_technical_failure_pair_charged", accounting["pair_prediction_attempts"] == 1 and accounting["pair_prediction_failures"] == 1)
            check("forecast_technical_failure_scalar_charged", accounting["scalar_prediction_attempts"] == 1 and accounting["scalar_prediction_returns"] == 0)
        else:
            check("forecast_technical_error_not_fallback", False)
        try:
            equilibrium_feedback_request((np.inf, 0.), (0., 0.), (.04, .04), (0., 0.))
        except ValueError:
            check("nonfinite_native_feedback_raises", True)
        else:
            check("nonfinite_native_feedback_raises", False)

    for name, function in (
        ("cold_zero_and_current_target_cache", cold_zero_cache),
        ("coupled_full_rank", coupled_full_rank),
        ("rank_one_box_and_continuous_minimum", rank_one_box),
        ("rank_zero_root_and_absence", rank_zero),
        ("hinge_quarter_boundaries", hinge_boundary),
        ("guard_equalities_and_adjacent_interior", guard_equality),
        ("finite_no_root_zero_hold", no_root_hold_zero),
        ("finite_forecast_literal_zero", finite_forecast_fallback),
        ("nonfinite_and_prediction_technical_errors", nonfinite_and_technical),
    ):
        case(name, function)
    check("bounded_root_attempts", root_totals["root_solve_attempts"] <= 24)
    check("bounded_branch_attempts", root_totals["branch_affine_build_attempts"] <= 384)
    check("bounded_root_model_verifications", root_totals["root_model_pair_prediction_attempts"] <= 384)
    check("bounded_forecast_pair_attempts", forecast_totals["pair_prediction_attempts"] <= 900)
    return {"schema": "equilibrium_feedforward_synthetic_first_v1", "status": "passed", "cases": cases,
            "checks": checks, "root_accounting": dict(root_totals), "forecast_accounting": dict(forecast_totals),
            "initialization_accounting": dict(initialization_totals),
            "fixture_model_builds": fixture_builds, "fixture_parameter_assignments": fixture_assignments,
            "numpy_version": np.__version__, "physics_calls": 0, "fit_calls": 0, "RLS_updates": 0,
            "raw_or_result_reads": 0, "checkpoint_reads": 0, "old_case_replays": 0}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if not args.execute:
        parser.error("explicit --execute is required; preparation never executes this check")
    repo, capture = args.repo.resolve(), args.capture.resolve()
    if capture.exists():
        parser.error("existing first capture is preserved; overwrite/retry is refused")
    capture.mkdir(parents=True, exist_ok=False)
    receipt = {"started_utc": datetime.now(timezone.utc).isoformat(), "source_files": [],
               "source_identity_reads": 0, "source_identity_bytes": 0, "status": "running"}
    result, exit_code = None, 1
    with (capture / "stdout.log").open("x", encoding="utf-8") as stdout, (capture / "stderr.log").open("x", encoding="utf-8") as stderr:
        with redirect_stdout(stdout), redirect_stderr(stderr):
            try:
                for source in (Path(__file__).resolve(), repo / "src/developmental_physics/equilibrium_feedforward_pair.py"):
                    receipt["source_identity_reads"] += 1
                    blob = source.read_bytes()
                    receipt["source_identity_bytes"] += len(blob)
                    receipt["source_files"].append({"path": str(source), "bytes": len(blob), "sha256": hashlib.sha256(blob).hexdigest()})
                result = run_cases(repo)
                receipt["status"], exit_code = "passed", 0
            except BaseException as exc:
                traceback.print_exc()
                receipt["status"] = "failed"
                result = {"schema": "equilibrium_feedforward_synthetic_first_v1", "status": "failed",
                          "exception_type": type(exc).__name__, "exception": str(exc),
                          "equilibrium_root_accounting": getattr(exc, "equilibrium_root_accounting", None),
                          "equilibrium_accounting": getattr(exc, "equilibrium_accounting", None),
                          "synthetic_partial_result": getattr(exc, "synthetic_partial_result", None),
                          "equilibrium_root_records": [asdict(value) for value in getattr(exc, "equilibrium_root_records", ())]}
    receipt["completed_utc"] = datetime.now(timezone.utc).isoformat()
    receipt["python_version"] = sys.version
    for name, content in (("result.json", result), ("first_execution_receipt.json", receipt)):
        with (capture / name).open("x", encoding="utf-8") as output:
            json.dump(content, output, ensure_ascii=False, allow_nan=False, indent=2)
            output.write("\n")
    print(json.dumps({"status": receipt["status"], "capture": str(capture)}, ensure_ascii=False))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
