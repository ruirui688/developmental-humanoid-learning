"""First bounded synthetic check, to be run once by root after freezing sources."""
import argparse
import ast
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import platform
import sys
import time
import traceback


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--counted-adapter-source", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    wall, cpu = time.perf_counter(), time.process_time()
    paths = (
        "external/batch_fast_feedback_candidate/batched_fast_feedback_pair_mpc.py",
        "external/batch_fast_feedback_candidate/check_batched_fast_feedback_equivalence.py",
        "external/batch_fast_feedback_candidate/EQUIVALENCE_CHECK_DESIGN.md",
        "src/developmental_physics/fast_feedback_pair_mpc.py",
        "src/developmental_physics/fast_feedback_pair_model.py",
        "src/developmental_physics/fast_feedback_pair_development.py",
        "src/developmental_physics/guard_coupled_pair_model.py",
        "src/developmental_physics/guard_pair_model.py",
        "src/developmental_physics/local_pair_model.py",
        "src/developmental_physics/local_model.py", "pyproject.toml")
    source_pins, source_bytes = {}, {}
    for name in paths:
        data = (args.repo / name).read_bytes()
        source_bytes[name] = data
        source_pins[name] = {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    adapter_path = args.counted_adapter_source or args.repo / "external/c4_free_learning_candidate/free_root_pair_development.py"
    adapter_bytes = adapter_path.read_bytes()
    source_pins[str(adapter_path)] = {"bytes": len(adapter_bytes), "sha256": hashlib.sha256(adapter_bytes).hexdigest()}
    sys.path.insert(0, str(args.repo / "src"))
    import numpy as np
    from developmental_physics.fast_feedback_pair_development import CountedGuardModel
    from developmental_physics.fast_feedback_pair_model import FastFeedbackGuardCoupledPairBodyModel
    from developmental_physics.fast_feedback_pair_mpc import FastFeedbackResidualPDPairMPC
    from developmental_physics.local_pair_model import PairBodyModel, _parameter_state
    spec = importlib.util.spec_from_file_location("batch_fast_feedback_candidate", args.repo / paths[0])
    candidate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(candidate)
    Batch = candidate.BatchedFastFeedbackResidualPDPairMPC
    def counted_class(data):
        return next(node for node in ast.parse(data).body if isinstance(node, ast.ClassDef) and node.name == "CountedGuardModel")
    original_class = counted_class(source_bytes["src/developmental_physics/fast_feedback_pair_development.py"])
    adapter_class = counted_class(adapter_bytes)
    assert ast.dump(original_class, include_attributes=False) == ast.dump(adapter_class, include_attributes=False), "new_Counted_class_AST_differs"
    # Define the identical class alone; do not import the physical collector/module.
    adapter_namespace = {"__name__": "synthetic_new_domain_counted_adapter", "Counter": Counter,
                         "FastFeedbackGuardCoupledPairBodyModel": FastFeedbackGuardCoupledPairBodyModel,
                         "_parameter_state": _parameter_state}
    exec(compile(ast.Module(body=[adapter_class], type_ignores=[]), str(adapter_path), "exec"), adapter_namespace)
    NewCountedGuardModel = adapter_namespace["CountedGuardModel"]

    # These matrices are declared synthetic coefficients, never learned/restored from data.
    def declared(kind):
        theta = np.zeros((2, 9), dtype=np.float64)
        if kind == "coupled":
            theta[0] = (.8, .03, -.02, .01, .02, .005, .003, -.002, .001)
            theta[1] = (-.02, .82, .005, -.02, .003, .018, -.001, .002, -.001)
        elif kind == "mixed_prune":
            theta[0, 4] = theta[1, 5] = 4.
        elif kind == "head0_overflow":
            theta[0, 0] = 1e308
        elif kind == "head1_overflow":
            theta[1, 1] = 1e308
        elif kind == "exact_tie":
            theta[0, 4] = theta[1, 5] = -64.
            theta[:, 8] = 32.
        elif kind != "zero":
            raise ValueError(kind)
        return theta

    boundary = .1 - .03
    fixtures = (
        {"name": "generic_prior", "kind": None, "q": (0., 0.), "v": (0., 0.), "target": (.04, .04)},
        {"name": "finite_coupled", "kind": "coupled", "q": (.003, -.004), "v": (.02, -.015),
         "target": (.04, -.04), "previous": (.05, -.025)},
        {"name": "mixed_early_pruning", "kind": "mixed_prune", "q": (0., 0.), "v": (0., 0.), "target": (.04, .04)},
        {"name": "head0_overflow", "kind": "head0_overflow", "q": (0., 0.), "v": (2., 0.), "target": (0., 0.)},
        {"name": "head1_overflow", "kind": "head1_overflow", "q": (0., 0.), "v": (0., 2.), "target": (0., 0.)},
        {"name": "forecast_equality", "kind": "zero", "q": (.15, .15), "v": (0., 0.), "target": (.04, .04)},
        {"name": "one_ulp_outside_forecast", "kind": "zero", "q": (float(np.nextafter(.15, np.inf)), .15),
         "v": (0., 0.), "target": (.04, .04)},
        {"name": "public_guard_equality", "kind": None, "qref": (boundary, boundary),
         "ranges": ((-.1, .1), (-.1, .1)), "q": (boundary, boundary), "v": (0., 0.), "target": (boundary, boundary)},
        {"name": "exact_residual_tie", "kind": "exact_tie", "q": (0., 0.), "v": (0., 0.), "target": (.04, .04)},
        {"name": "unknown_predictor_serial_fallback", "fake": True, "q": (0., 0.), "v": (0., 0.), "target": (.04, .04)},
        {"name": "new_domain_counted_adapter", "kind": "coupled", "new_adapter": True,
         "q": (.003, -.004), "v": (.02, -.015), "target": (.04, -.04), "previous": (.05, -.025)},
    )

    class UnknownFake(PairBodyModel):
        def __init__(self):
            self._qref, self._dt, self.calls = (0., 0.), .002, 0

        def predict(self, q, v, u):
            self.calls += 1
            return (q[0]+1e-6, q[1]-1e-6), (0., 0.)

    def canonical(value):
        # JSON float repr distinguishes every finite float and signed zero.
        return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)

    results, errors = [], []
    totals = Counter()
    for fixture in fixtures:
        row = {"fixture": fixture["name"], "attempted_once": True}
        try:
            outputs, forward_costs, elapsed = [], [], []
            for Controller in (FastFeedbackResidualPDPairMPC, Batch):
                cost = Counter()
                if fixture.get("fake"):
                    model = UnknownFake()
                    before = None
                else:
                    Model = NewCountedGuardModel if fixture.get("new_adapter") else CountedGuardModel
                    model = Model(fixture.get("qref", (0., 0.)),
                        public_joint_ranges=fixture.get("ranges", ((-2., 2.), (-2., 2.))),
                        cost=cost, label="synthetic", trainable=False)
                    model.scope = "synthetic_planning"
                    if fixture["kind"] is not None:
                        original = model._state
                        model._state = _parameter_state(declared(fixture["kind"]), original.covariance.copy(), 0)
                    before = model._state
                adapter_kwargs = {"counted_model_type": NewCountedGuardModel} if Controller is Batch and fixture.get("new_adapter") else {}
                controller = Controller(model, fixture.get("ranges", ((-2., 2.), (-2., 2.))), **adapter_kwargs)
                started_wall, started_cpu = time.perf_counter(), time.process_time()
                decision = controller.select(fixture["q"], fixture["v"], fixture["target"],
                                              previous_torque=fixture.get("previous", (0., 0.)))
                elapsed.append({"wall_seconds": time.perf_counter()-started_wall,
                                "cpu_seconds": time.process_time()-started_cpu})
                outputs.append(decision.to_dict())
                forward_costs.append({"cost": dict(cost), "forward_counts": dict(getattr(model, "forward_counts", {})),
                                      "fake_calls": getattr(model, "calls", None)})
                if before is not None:
                    assert model._state is before and model.update_count == 0, "synthetic_parameters_changed"
                totals["pair_attempts"] += decision.pair_prediction_attempts
                totals["scalar_attempts"] += decision.scalar_prediction_attempts
                totals["PD_attempts"] += decision.pd_request_attempts
                totals["candidate_attempts"] += decision.residual_candidate_attempts
                if Controller is Batch:
                    row["batch_execution"] = dict(controller.last_batch_execution)
                    assert controller.last_batch_execution["serial_fallback_selections"] == int(bool(fixture.get("fake")))
                    if not fixture.get("fake"):
                        assert controller.last_batch_execution["feature_batch_rows"] == decision.pair_prediction_attempts
                        assert controller.last_batch_execution["original_scalar_dot_calls"] == decision.scalar_prediction_attempts
            assert canonical(outputs[0]) == canonical(outputs[1]), "complete_decision_or_float_representation_differs"
            assert canonical(forward_costs[0]) == canonical(forward_costs[1]), "CountedGuardModel_counters_differ"
            selected = outputs[1]
            assert selected["residual_candidate_attempts"] == 81
            if fixture["name"] == "mixed_early_pruning":
                assert selected["fallback"] and selected["pair_prediction_attempts"] == 82
                assert selected["pair_prediction_successes"] == 82 and selected["pd_request_returns"] == 2
            if fixture["name"] in ("head0_overflow", "head1_overflow"):
                first_head = fixture["name"] == "head0_overflow"
                assert selected["fallback"] and selected["pair_prediction_successes"] == 0
                assert selected["scalar_prediction_attempts"] == (81 if first_head else 162)
                assert selected["scalar_prediction_successes"] == (0 if first_head else 81)
            if fixture["name"] == "forecast_equality":
                assert not selected["fallback"] and selected["feasible_candidates"] == 81
            if fixture["name"] == "one_ulp_outside_forecast":
                assert selected["fallback"] and selected["pair_prediction_attempts"] == 81
            if fixture["name"] == "exact_residual_tie":
                assert selected["selected_residual_nm"] == (0., 0.) and selected["feasible_candidates"] == 25
            row.update(passed=True, complete_decision_bitwise_float_repr_equal=True,
                       counted_model_costs_equal=True, timing=elapsed,
                       selected_residual_nm=selected["selected_residual_nm"],
                       pair_attempts_per_implementation=selected["pair_prediction_attempts"])
        except BaseException as exc:
            row.update(passed=False, failure={"type": type(exc).__name__, "message": str(exc),
                                             "traceback": traceback.format_exc()})
            errors.append(fixture["name"])
            results.append(row)
            break
        results.append(row)
    receipt = {
        "status": "bounded_synthetic_equivalence_passed" if not errors and len(results) == 11 else "first_check_failed_preserved",
        "fixtures_planned": 11, "fixtures_attempted": len(results), "failures": errors, "results": results,
        "upper_bounds": {"controller_selections": 22, "pair_attempts": 267300, "scalar_attempts": 534600,
                         "formal_physics_controls": 0, "RLS_updates": 0, "snapshot_restores": 0},
        "logical_work_total": dict(totals), "source_pins": source_pins,
        "explicit_source_reads": len(source_pins), "explicit_source_bytes_read": sum(x["bytes"] for x in source_pins.values()),
        "runtime": {"python": sys.version, "platform": platform.platform(), "numpy": np.__version__},
        "raw_saved_model_or_trajectory_reads": 0, "physical_model_or_teacher_calls": 0,
        "synthetic_coefficient_assignments": "declared constants only; no fit or data snapshot",
        "new_counted_adapter": {"source": str(adapter_path), "full_class_AST_matches": True,
                                "class_defined_without_importing_physical_collector": True},
        "Z2_rejudged": False, "scientific_adoption": False, "realtime_20ms_demonstrated": False,
        "automatic_retry": False, "timing_scope": "one reference then one candidate per fixture; includes decision construction",
        "wall_seconds_before_receipt": time.perf_counter()-wall, "cpu_seconds_before_receipt": time.process_time()-cpu}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(receipt, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"status": receipt["status"], "fixtures": len(results), "failures": errors,
                      "pair_attempts": totals["pair_attempts"]}))
    return bool(errors)


if __name__ == "__main__":
    raise SystemExit(main())
