"""One bounded FR3 parameterization contract; root executes once after static review.

Three declared cases only: non-grid PD, saturated PD, and literal-zero fallback.
No new physical collector import, snapshots, fitting, RLS, physics or old checks.
"""
from __future__ import annotations
import argparse
import ast
from collections import Counter
from dataclasses import asdict
import hashlib
import importlib.util
import json
from pathlib import Path
import platform
import sys
import time
import traceback


def identity(data):
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def class_node(data):
    return next(node for node in ast.parse(data).body if isinstance(node, ast.ClassDef) and node.name == "CountedGuardModel")


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--controller-source", type=Path, default=Path(__file__).resolve().with_name("full_request_pair_mpc.py"))
    parser.add_argument("--counted-adapter-source", type=Path, default=Path(__file__).resolve().with_name("full_request_pair_development.py"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
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
              "new_FR3_Counted_adapter_AST_equals_original")
        sys.path.insert(0, str(args.repo/"src"))
        import numpy as np
        from developmental_physics.fast_feedback_pair_model import FastFeedbackGuardCoupledPairBodyModel
        from developmental_physics.local_pair_model import _parameter_state
        from developmental_physics.fast_feedback_pair_mpc import public_pd_request
        runtime["numpy"] = np.__version__
        spec = importlib.util.spec_from_file_location("bounded_FR3_full_request_candidate", args.controller_source)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        # Define the exact new class alone, never import its physical collector.
        namespace = {"__name__": "synthetic_new_FR3_Counted_adapter", "Counter": Counter,
                     "FastFeedbackGuardCoupledPairBodyModel": FastFeedbackGuardCoupledPairBodyModel,
                     "_parameter_state": _parameter_state}
        exec(compile(ast.Module(body=[adapter_node], type_ignores=[]), str(args.counted_adapter_source), "exec"), namespace)
        NewCounted = namespace["CountedGuardModel"]
        Scalar, Batch = module.FullRequestResidualPDPairMPC, module.BatchedFullRequestResidualPDPairMPC
        grid = (-.5, -.375, -.25, -.125, 0., .125, .25, .375, .5)
        cases = (
            {"name": "non_grid_PD", "q": (.00125, -.00075), "v": (.015, -.02), "target": (.003, -.0025), "fallback": False},
            {"name": "saturated_PD", "q": (0., 0.), "v": (0., 0.), "target": (.04, -.04), "fallback": False},
            {"name": "literal_zero_fallback", "q": (.2, .2), "v": (0., 0.), "target": (0., 0.), "fallback": True},
        )
        for case in cases:
            row = {"case": case, "attempted_once": True, "controllers": [], "complete": False}
            results.append(row)
            try:
                p_current = public_pd_request(case["q"], case["v"], case["target"])
                check((all(p not in grid for p in p_current) if case["name"] == "non_grid_PD" else
                       p_current == (.5, -.5) if case["name"] == "saturated_PD" else True), case["name"]+":declared_PD_region")
                decisions, cost_records = [], []
                for Controller in (Scalar, Batch):
                    cost = Counter()
                    item = {"controller": Controller.__name__, "cost": {}, "returned": False}
                    row["controllers"].append(item)
                    try:
                        model = NewCounted((0., 0.), public_joint_ranges=((-2., 2.), (-2., 2.)),
                                           cost=cost, label="new_parameterization_contract", trainable=False)
                        model.scope = "new_mapping_contract"
                        before_state, before_model = model._state, model.parameter_fingerprint()
                        controller = Controller(model, ((-2., 2.), (-2., 2.)), counted_model_type=NewCounted) if Controller is Batch else Controller(model, ((-2., 2.), (-2., 2.)))
                        before_controller = controller.parameter_fingerprint()
                        if Controller is Batch:
                            check(controller._supported(), case["name"]+":new_batch_supported_before_select")
                        decision = controller.select(case["q"], case["v"], case["target"], previous_torque=(0., 0.))
                        item["returned"] = True
                        record = asdict(decision)
                        decisions.append(record)
                        check(model._state is before_state and model.update_count == 0 and model.parameter_fingerprint() == before_model,
                              case["name"]+":"+Controller.__name__+":frozen_prior_no_fit")
                        check(controller.parameter_fingerprint() == before_controller,
                              case["name"]+":"+Controller.__name__+":spec_fingerprint_independent_of_select_state")
                        check(len(record["candidate_records"]) == 81 and record["residual_candidate_attempts"] == 81,
                              case["name"]+":"+Controller.__name__+":fixed_81_population")
                        expected_first = [tuple(float(np.clip(p_current[i]+float(g[i]-p_current[i]), -.5, .5)) for i in range(2))
                                          for g in controller._candidates]
                        check([tuple(entry["torque"]) for entry in record["candidate_records"]] == expected_first,
                              case["name"]+":"+Controller.__name__+":all_81_grid_delta_roundtrip_first_requests")
                        check(all(abs(value) <= .5 for first in expected_first for value in first),
                              case["name"]+":"+Controller.__name__+":all_first_final_permissions")
                        check(record["fallback"] is case["fallback"], case["name"]+":"+Controller.__name__+":declared_fallback_mode")
                        if record["fallback"]:
                            check(record["torque"] == (0., 0.) and record["selected_residual_nm"] is None
                                  and record["cost"] is None and not record["trajectory_requested_torque"]
                                  and not record["predicted_q"] and not record["predicted_v"],
                                  case["name"]+":"+Controller.__name__+":literal_zero_not_residual_zero_PD")
                        else:
                            delta = record["selected_residual_nm"]
                            selected_grid = [g for g in controller._candidates
                                if tuple(float(g[i]-p_current[i]) for i in range(2)) == tuple(delta)]
                            check(len(selected_grid) == 1 and all(abs(x) <= 1. for x in delta),
                                  case["name"]+":"+Controller.__name__+":selected_dynamic_delta_membership")
                            check(len(record["trajectory_requested_torque"]) == len(record["predicted_q"]) == len(record["predicted_v"]) == 150,
                                  case["name"]+":"+Controller.__name__+":complete_150_path")
                            for stage, requested in enumerate(record["trajectory_requested_torque"]):
                                q, v = (case["q"], case["v"]) if stage == 0 else (record["predicted_q"][stage-1], record["predicted_v"][stage-1])
                                p = public_pd_request(q, v, case["target"])
                                expected = tuple(float(np.clip(p[i]+(delta[i] if stage < 10 else 0.), -.5, .5)) for i in range(2))
                                check(tuple(requested) == expected and all(abs(x) <= .5 for x in requested),
                                      case["name"]+":"+Controller.__name__+f":micro_{stage}_feedback_delta_and_final_permission")
                                if case["name"] == "non_grid_PD" and stage == 9:
                                    check(tuple(requested) != p, Controller.__name__+":micro9_dynamic_delta_still_active")
                                if stage == 10:
                                    check(tuple(requested) == p, case["name"]+":"+Controller.__name__+":micro10_PD_tail_starts")
                            check(tuple(record["torque"]) == tuple(record["trajectory_requested_torque"][0]),
                                  case["name"]+":"+Controller.__name__+":selected_first_roundtrip_matches_saved_prediction_first")
                        if Controller is Batch:
                            item["batch_execution"] = dict(controller.last_batch_execution)
                            check(item["batch_execution"]["serial_fallback_selections"] == 0
                                  and item["batch_execution"]["stage_batches"] > 0
                                  and item["batch_execution"]["feature_batch_rows"] == record["pair_prediction_attempts"]
                                  and item["batch_execution"]["original_scalar_dot_calls"] == record["scalar_prediction_attempts"],
                                  case["name"]+":real_supported_batch_not_silent_scalar")
                        item["decision"] = record
                    finally:
                        item["cost"] = dict(cost)
                        total_cost.update(cost)
                    cost_records.append(dict(cost))
                check(canonical(decisions[0]) == canonical(decisions[1]), case["name"]+":scalar_batch_exact_JSON_decision")
                check(canonical(cost_records[0]) == canonical(cost_records[1]), case["name"]+":scalar_batch_exact_Counter")
                row["complete"] = True
            except BaseException as exc:
                detail = {"case": case["name"], "type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()}
                row["failure"] = detail
                failures.append(detail)
    except BaseException as exc:
        failures.append({"phase": "source_binding_or_import", "type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()})
    report = {"schema": "first_FR3_parameterization_contract_v1", "status": "passed" if not failures else "failed",
              "source_pins": pins, "runtime": runtime, "checks": checks, "cases": results,
              "first_failure": failures[0] if failures else None, "failures": failures,
              "cost": dict(total_cost), "timing": {"wall_seconds": time.perf_counter()-wall, "cpu_seconds": time.process_time()-cpu},
              "bounds": {"declared_cases": 3, "selector_calls": 6, "maximum_pair_predictions": 72900, "maximum_scalar_predictions": 145800},
              "execution": {"physics": 0, "fit": 0, "RLS": 0, "snapshot_restoration": 0, "raw_or_saved_parameters_reads": 0,
                            "new_physical_collector_imports": 0, "old_check_executions": 0, "automatic_retry": 0}}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"status": report["status"], "output": str(args.output), "checks": len(checks),
                      "first_failure": report["first_failure"], "cost": report["cost"]}, ensure_ascii=False, allow_nan=False))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
