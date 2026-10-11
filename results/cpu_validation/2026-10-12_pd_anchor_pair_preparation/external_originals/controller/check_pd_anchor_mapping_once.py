"""Bounded new FR4 parameterization contract; root executes once.

Four direct mappings and two synthetic scalar/batch selections only. No old
checks, physical collector import, saved parameters, fitting, RLS or physics.
"""
from __future__ import annotations

import argparse
import ast
from collections import Counter
from dataclasses import asdict
import hashlib
import importlib.util
from itertools import product
import json
from pathlib import Path
import platform
import sys
import time
import traceback


def identity(data):
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def class_node(data):
    return next(node for node in ast.parse(data).body
                if isinstance(node, ast.ClassDef) and node.name == "CountedGuardModel")


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--controller-source", type=Path)
    parser.add_argument("--counted-adapter-source", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.controller_source = args.controller_source or args.repo/"src/developmental_physics/pd_anchor_pair_mpc.py"
    args.counted_adapter_source = args.counted_adapter_source or args.repo/"src/developmental_physics/pd_anchor_pair_development.py"
    if args.output.exists():
        raise FileExistsError(args.output)
    wall, cpu = time.perf_counter(), time.process_time()
    checks, results, failures, pins, total_cost = [], [], [], {}, Counter()
    runtime = {"python": platform.python_version(), "numpy": None}

    def check(condition, label):
        checks.append({"label": label, "passed": bool(condition)})
        if not condition:
            raise AssertionError(label)

    try:
        paths = [args.controller_source, args.counted_adapter_source, Path(__file__).resolve()]
        paths += [args.repo/name for name in (
            "src/developmental_physics/fast_feedback_pair_development.py",
            "src/developmental_physics/fast_feedback_pair_mpc.py",
            "src/developmental_physics/fast_feedback_pair_model.py",
            "src/developmental_physics/guard_coupled_pair_model.py",
            "src/developmental_physics/guard_pair_model.py",
            "src/developmental_physics/local_pair_model.py",
            "src/developmental_physics/local_model.py")]
        source_bytes = {str(path.resolve()): path.read_bytes() for path in paths}
        pins = {path: identity(data) for path, data in source_bytes.items()}
        adapter_node = class_node(source_bytes[str(args.counted_adapter_source.resolve())])
        original_node = class_node(source_bytes[str((args.repo/"src/developmental_physics/fast_feedback_pair_development.py").resolve())])
        check(ast.dump(adapter_node, include_attributes=False) == ast.dump(original_node, include_attributes=False),
              "FR4_Counted_adapter_AST_equals_original")
        sys.path.insert(0, str(args.repo/"src"))
        import numpy as np
        from developmental_physics.fast_feedback_pair_model import FastFeedbackGuardCoupledPairBodyModel
        from developmental_physics.local_pair_model import _parameter_state
        from developmental_physics.fast_feedback_pair_mpc import public_pd_request
        runtime["numpy"] = np.__version__
        spec = importlib.util.spec_from_file_location("bounded_FR4_PD_anchor_candidate", args.controller_source)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        # Instantiate the exact new class alone, without importing its collector.
        namespace = {"__name__": "synthetic_new_FR4_Counted_adapter", "Counter": Counter,
                     "FastFeedbackGuardCoupledPairBodyModel": FastFeedbackGuardCoupledPairBodyModel,
                     "_parameter_state": _parameter_state}
        exec(compile(ast.Module(body=[adapter_node], type_ignores=[]), str(args.counted_adapter_source), "exec"), namespace)
        NewCounted = namespace["CountedGuardModel"]
        Scalar, Batch = module.PDAnchorResidualPDPairMPC, module.BatchedPDAnchorResidualPDPairMPC
        grid = (-.5, -.375, -.25, -.125, 0., .125, .25, .375, .5)
        nominal = tuple(product(grid, repeat=2))
        mapping_cases = (
            {"name": "already_nominal", "p": (.125, -.375), "indices": (5, 1)},
            {"name": "non_grid", "p": (.1, -.1), "indices": (5, 3)},
            {"name": "clipped_endpoints", "p": (.5, -.5), "indices": (8, 0)},
            {"name": "exact_distance_tie_original_index", "p": (.0625, -.4375), "indices": (4, 0)},
        )
        for case in mapping_cases:
            row = {"kind": "direct_mapping", "case": case, "attempted_once": True, "complete": False}
            results.append(row)
            try:
                expected_axes = []
                for axis, index in enumerate(case["indices"]):
                    values = list(grid)
                    values[index] = case["p"][axis]
                    expected_axes.append(tuple(values))
                expected = tuple(product(*expected_axes))
                actual = module.pd_anchor_first_request_candidates(case["p"])
                row["points"] = actual
                check(actual == expected, case["name"]+":original_slot_order_exact")
                check(len(actual) == len(set(actual)) == 81, case["name"]+":nine_by_nine_no_expand_duplicate_or_sort")
                check(tuple(case["p"]) in actual, case["name"]+":pure_PD_pair_present")
                deltas = tuple(tuple(float(point[i]-case["p"][i]) for i in range(2)) for point in actual)
                check(deltas.count((0., 0.)) == 1, case["name"]+":exactly_one_delta_zero_pair")
                check(module.FULL_REQUEST_AXIS_GRID_NM == grid, case["name"]+":nominal_constant_unchanged")
                if case["name"] in ("already_nominal", "clipped_endpoints"):
                    check(actual == nominal, case["name"]+":on_grid_replacement_identity")
                row["complete"] = True
            except BaseException as exc:
                detail = {"case": case["name"], "type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()}
                row["failure"] = detail
                failures.append(detail)

        selector_cases = (
            {"name": "new_non_grid_PD", "q": (.0005, -.001), "v": (.004, -.003), "target": (.002, -.002)},
            {"name": "new_exact_nearest_tie_PD", "q": (0., 0.), "v": (0., 0.), "target": (.0009765625, -.0068359375)},
        )
        for case in selector_cases:
            row = {"kind": "synthetic_selector", "case": case, "attempted_once": True, "controllers": [], "complete": False}
            results.append(row)
            try:
                p_current = public_pd_request(case["q"], case["v"], case["target"])
                check(all(p not in grid for p in p_current), case["name"]+":declared_non_grid_PD")
                if case["name"] == "new_exact_nearest_tie_PD":
                    check(p_current == (.0625, -.4375), case["name"]+":declared_binary_exact_midpoints")
                points = module.pd_anchor_first_request_candidates(p_current)
                expected_first = [tuple(float(np.clip(p_current[i]+float(point[i]-p_current[i]), -.5, .5))
                                        for i in range(2)) for point in points]
                pd_index = points.index(tuple(p_current))
                decisions, cost_records = [], []
                for Controller in (Scalar, Batch):
                    cost = Counter()
                    item = {"controller": Controller.__name__, "cost": {}, "returned": False}
                    row["controllers"].append(item)
                    try:
                        model = NewCounted((0., 0.), public_joint_ranges=((-2., 2.), (-2., 2.)),
                                           cost=cost, label="new_PD_anchor_parameterization_contract", trainable=False)
                        model.scope = "new_PD_anchor_mapping_contract"
                        before_state, before_model = model._state, model.parameter_fingerprint()
                        controller = (Controller(model, ((-2., 2.), (-2., 2.)), counted_model_type=NewCounted)
                                      if Controller is Batch else Controller(model, ((-2., 2.), (-2., 2.))))
                        before_controller = controller.parameter_fingerprint()
                        if Controller is Batch:
                            check(controller._supported(), case["name"]+":new_collector_Counted_class_supported")
                        decision = controller.select(case["q"], case["v"], case["target"], previous_torque=(0., 0.))
                        item["returned"] = True
                        record = asdict(decision)
                        decisions.append(record)
                        check(model._state is before_state and model.update_count == 0 and model.parameter_fingerprint() == before_model,
                              case["name"]+":"+Controller.__name__+":no_fit_or_parameter_mutation")
                        check(controller.parameter_fingerprint() == before_controller and controller._candidates == nominal,
                              case["name"]+":"+Controller.__name__+":static_spec_fingerprint_and_nominal_grid")
                        check(len(record["candidate_records"]) == record["residual_candidate_attempts"] == 81,
                              case["name"]+":"+Controller.__name__+":fixed_81_population")
                        check([tuple(entry["torque"]) for entry in record["candidate_records"]] == expected_first,
                              case["name"]+":"+Controller.__name__+":all_dynamic_slot_roundtrip_first_requests")
                        check(tuple(record["candidate_records"][pd_index]["torque"]) == tuple(p_current),
                              case["name"]+":"+Controller.__name__+":delta_zero_record_first_equals_current_PD")
                        check(controller.spec()["pure_PD_candidate_guaranteed"] is True
                              and controller.spec()["PD_anchor_replacement"]["pure_PD_feasibility_or_selection_guaranteed"] is False,
                              case["name"]+":"+Controller.__name__+":expression_guarantee_has_no_feasible_or_chosen_claim")
                        if Controller is Batch:
                            item["batch_execution"] = dict(controller.last_batch_execution)
                            check(item["batch_execution"]["serial_fallback_selections"] == 0
                                  and item["batch_execution"]["stage_batches"] > 0
                                  and item["batch_execution"]["feature_batch_rows"] == record["pair_prediction_attempts"]
                                  and item["batch_execution"]["original_scalar_dot_calls"] == record["scalar_prediction_attempts"],
                                  case["name"]+":real_Counted_batch_path")
                        item["decision"] = record
                    finally:
                        item["cost"] = dict(cost)
                        total_cost.update(cost)
                    cost_records.append(dict(cost))
                check(canonical(decisions[0]) == canonical(decisions[1]), case["name"]+":scalar_batch_exact_full_decision")
                check(canonical(cost_records[0]) == canonical(cost_records[1]), case["name"]+":scalar_batch_exact_Counted_cost")
                row["complete"] = True
            except BaseException as exc:
                detail = {"case": case["name"], "type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()}
                row["failure"] = detail
                failures.append(detail)
    except BaseException as exc:
        failures.append({"phase": "source_binding_or_import", "type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()})
    report = {"schema": "first_FR4_PD_anchor_parameterization_contract_v1", "status": "passed" if not failures else "failed",
              "source_pins": pins, "runtime": runtime, "checks": checks, "cases": results,
              "first_failure": failures[0] if failures else None, "failures": failures,
              "cost": dict(total_cost), "timing": {"wall_seconds": time.perf_counter()-wall, "cpu_seconds": time.process_time()-cpu},
              "bounds": {"direct_mapping_cases": 4, "synthetic_selector_cases": 2, "selector_calls": 4,
                         "maximum_pair_predictions": 48600, "maximum_scalar_predictions": 97200},
              "execution": {"physics": 0, "fit": 0, "RLS": 0, "snapshot_restoration": 0,
                            "raw_or_saved_parameters_reads": 0, "new_physical_collector_imports": 0,
                            "old_check_executions": 0, "automatic_retry": 0}}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"status": report["status"], "output": str(args.output), "checks": len(checks),
                      "first_failure": report["first_failure"], "cost": report["cost"]}, ensure_ascii=False, allow_nan=False))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
