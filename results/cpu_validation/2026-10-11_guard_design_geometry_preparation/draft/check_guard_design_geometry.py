"""New M-only synthetic contract checks; never read archived matrices or run main."""
from __future__ import annotations

import argparse
from collections import Counter
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import platform
from types import SimpleNamespace
import time
import traceback
from unittest.mock import patch

import numpy as np


ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("M_synthetic_only", ROOT/"diagnose_guard_design_geometry.py")
core = importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def fixture_record(seed, label):
    count = 400 if label == "K" else 600
    ids = [f"seed{seed}_calibration_sparse:{i}" for i in range(100, 500)]
    if label == "L":
        ids += [f"seed{seed}_PDselected:{i}" for i in range(100, 300)]
    record = {"seed": seed, "available": True, "fixed_lambda": .01,
        "state_order": list(core.STATE_NAMES), "feature_order": list(core.FEATURE_NAMES),
        "qref8": [0.]*8, "training_transition_ids": ids,
        "fit": {"weights29x22": np.zeros((29, 22)).tolist()}}
    phi, delta = np.zeros((count, 29)).tolist(), np.zeros((count, 22)).tolist()
    if label == "K":
        record.update(training_usable_count=400, training_source_active_count=400)
        record["fit"].update(phi400x29=phi, delta_labels400x22=delta)
    else:
        record.update(qualified_training_count=600, training_collection_labels=["C"]*400+["G"]*200,
                      phi600x29=phi, delta_labels600x22=delta)
    return record


def eligibility():
    docs = {f"{root}/parameters.json": [fixture_record(s, label) for s in core.SEEDS]
            for label, root in (("K", core.K_ROOT), ("L", core.L_ROOT))}
    accepted_cost, rejected_cost = Counter(), Counter()
    selected = core.datasets(docs, accepted_cost)
    require([(r["seed"], r["collection"]) for r in selected] ==
            [(s, label) for s in core.SEEDS for label in ("K", "L")], "fixed six-set order")
    require(accepted_cost["validated_archived_native_label_scalars"] == 66000, "validation labels")
    require(accepted_cost["validated_archived_weight_scalars"] == 3828, "saved W count")
    changed = copy.deepcopy(docs)
    changed[f"{core.L_ROOT}/parameters.json"][1]["phi600x29"][0][0] = .0001
    try:
        core.datasets(changed, rejected_cost)
    except ValueError as exc:
        require("K400 and L first400 differ" in str(exc), "exact C mismatch rejection")
    else:
        raise AssertionError("single-element source mismatch accepted")
    return {"accepted_cost": dict(accepted_cost), "rejected_cost": dict(rejected_cost),
            "actual_svd_calls": 0, "actual_matmul_attempts": 0}


def synthetic_dataset(label):
    count = 400 if label == "K" else 600
    return {"seed": 0, "collection": label, "count": count, "ids": [f"synthetic:{i}" for i in range(count)],
            "phi": np.zeros((count, 29)), "delta": np.zeros((count, 22)), "weights": np.zeros((29, 22))}


def run_diagnostic(dataset):
    cost, operations, result = Counter(), [], {}
    with np.errstate(over="raise", invalid="raise", divide="raise"):
        core.diagnose(dataset, cost, operations, result)
    require(cost["svd_returns"] == 3 and cost["matmul_returns"] == 6, "full-dataset operations")
    require(cost["native_projection_estimation_returns"] == 1, "complete native estimate")
    require(cost["command_projection_estimation_returns"] == 1, "complete command estimate")
    return cost, operations, result


def zero_rank():
    dataset = synthetic_dataset("K")
    dataset["delta"][0, 0], dataset["delta"][1, 8] = 2., 3.
    cost, operations, result = run_diagnostic(dataset)
    for key in ("full_design_spectrum", "context_spectrum", "conditional_action_spectrum"):
        require(result[key]["rank"] == 0 and result[key]["tolerance"] == 0., "zero rank/tolerance")
    require(np.array_equal(np.asarray(result["floor"]), dataset["delta"]), "zero design floor")
    require(not np.count_nonzero(result["shrink"]), "zero design shrink")
    require(all(r["conditional_energy_retained_ratio"] is None for r in result["action_column_energies"]),
            "zero raw action ratio undefined")
    require(len(result["output_summaries"]) == 44, "all22 ALL/C outputs")
    require(cost["native_projection_label_scalar_uses_returned"] == 8800, "zero-rank labels still used")
    require(cost["command_projection_response_scalar_uses_returned"] == 1600, "zero-rank command responses")
    require(cost["archived_ridge_forward_output_scalars_returned"] == 8800, "archived forward output")
    return {"cost": dict(cost), "operations": operations, "actual_svd_calls": 3, "actual_matmul_attempts": 6}


def subgroup_and_action():
    dataset = synthetic_dataset("L")
    phi, delta = dataset["phi"], dataset["delta"]
    phi[:, 26] = 1.
    phi[:, 22] = np.tile([-1., 1.], 300)
    phi[:, 23] = np.tile([-1., -1., 1., 1.], 150)
    phi[:, 24], phi[:, 25] = 2*phi[:, 22], 3*phi[:, 23]
    delta[:400, 0], delta[:, 8] = 1., phi[:, 22]
    cost, operations, result = run_diagnostic(dataset)
    require(result["conditional_action_spectrum"]["rank"] == 2, "four basis columns may have rank2")
    require(np.allclose(result["conditional_action"], phi[:, core.A_COLUMNS], atol=1e-12, rtol=1e-12),
            "constant context leaves zero-mean synthetic actions")
    rows = {r["subset"]: r for r in result["output_summaries"] if r["output_index"] == 0}
    require(rows["C400"]["twice_floor_shrink_cross_term"] > 1e-4, "C cross term retained")
    require(rows["G200"]["twice_floor_shrink_cross_term"] < -1e-4, "G cross term retained")
    require(abs(rows["ALL"]["twice_floor_shrink_cross_term"]) < 1e-12, "full orthogonality")
    for row in result["output_summaries"]:
        expected = row["floor_squared_energy"]+row["shrink_squared_energy"]+row["twice_floor_shrink_cross_term"]
        require(np.isclose(expected, row["reconstructed_squared_energy"], atol=1e-10, rtol=1e-12),
                "subgroup residual identity includes cross term")
    require(rows["ALL"]["max_abs_residual_identity_discrepancy"] > .5,
            "synthetic non-ridge W discrepancy preserved without pass gate")
    require(len(result["output_summaries"]) == 66, "all22 ALL/C/G outputs")
    return {"cost": dict(cost), "operations": operations, "focus_output0_summaries": rows,
            "actual_svd_calls": 3, "actual_matmul_attempts": 6, "ridge_solves": 0}


def failure_accounting(fixture_root):
    cost, operations, result = Counter(), [], {}
    original_multiply = core.multiply
    def fake_svd(matrix, full_matrices):
        require(full_matrices is False, "fixed SVD option")
        rows, columns = matrix.shape
        size = min(rows, columns)
        return np.zeros((rows, size)), np.zeros(size), np.zeros((size, columns))
    def second_product_failure(left, right, name, counter, events, response_kind=None):
        if name.endswith(":Ur_coordinates"):
            right = np.zeros((1, 22))  # incompatible with rank0 left; real matmul raises
        return original_multiply(left, right, name, counter, events, response_kind)
    with patch.object(core.np.linalg, "svd", fake_svd), patch.object(core, "multiply", second_product_failure):
        try:
            core.diagnose(synthetic_dataset("K"), cost, operations, result)
        except ValueError:
            pass
        else:
            raise AssertionError("injected second-product failure did not stop")
    require(cost["native_projection_label_scalar_uses_returned"] == 8800, "first-product labels really returned")
    require(cost["native_projection_estimation_attempts"] == 1 and
            cost["native_projection_estimation_returns"] == 0 and
            cost["native_projection_estimation_failures"] == 1, "incomplete full estimate retained")
    require(cost["matmul_attempts"] == 2 and cost["matmul_returns"] == 1 and cost["matmul_failures"] == 1,
            "failed product costs retained")
    def unreturned_source(repo, commit, counter):
        counter["source_file_read_attempts"] += 1
        raise RuntimeError("synthetic source verifier did not return")
    args = SimpleNamespace(repo=str(ROOT), source_commit="0"*40, output=str(fixture_root/"source_failure"))
    with patch.object(core, "frozen_sources", unreturned_source):
        require(core.main_run(args) == 1, "source failure returns failed status")
    output = Path(args.output)
    run = json.loads((output/"run.json").read_text(encoding="utf-8"))
    require(run["source"]["status"] == "unknown", "unreturned verifier unknown")
    require(run["inputs"] == {} and len(run["inputs_without_returned_read_record"]) == 7, "unread inputs unknown")
    require(run["cost"]["svd_attempts"] == 0, "source failure no projections")
    before = (output/"manifest.json").read_bytes()
    try:
        core.main_run(args)
    except FileExistsError:
        pass
    else:
        raise AssertionError("existing output accepted")
    require((output/"manifest.json").read_bytes() == before, "existing first artifact unchanged")
    return {"projection_failure_cost": dict(cost), "projection_failure_operations": operations,
            "source_failure_cost": run["cost"], "actual_svd_calls": 0, "mock_svd_calls": 1,
            "actual_matmul_attempts": 2, "actual_archived_input_reads": 0}


def main():
    wall_started, cpu_started = time.perf_counter(), time.process_time()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--only", choices=("eligibility", "zero_rank", "subgroup_and_action", "failure_accounting"))
    args = parser.parse_args()
    output = Path(args.output).resolve()
    if output.exists():
        raise FileExistsError(output)
    cases = {"eligibility": eligibility, "zero_rank": zero_rank, "subgroup_and_action": subgroup_and_action,
             "failure_accounting": lambda: failure_accounting(output.with_suffix(".fixtures"))}
    records = []
    for name, function in cases.items():
        if args.only and args.only != name:
            continue
        try:
            records.append({"case": name, "status": "passed", "detail": function()})
        except BaseException as exc:
            records.append({"case": name, "status": "failed", "failure": {
                "type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()}})
    passed = all(r["status"] == "passed" for r in records)
    report = {"passed": passed, "synthetic_only": True, "actual_archived_input_reads": 0, "physics": 0, "ridge_solves": 0,
              "runtime": {"python": platform.python_version(), "numpy": np.__version__},
              "wall_seconds_before_serialization": time.perf_counter()-wall_started,
              "cpu_process_seconds_before_serialization": time.process_time()-cpu_started,
              "source_sha256": {name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
                  for name in ("diagnose_guard_design_geometry.py", "GUARD_DESIGN_GEOMETRY_DIAGNOSTIC_PROTOCOL.md",
                               "check_guard_design_geometry.py")}, "cases": records}
    output.write_bytes(core.json_bytes(report))
    print(json.dumps({"output": str(output), "cases": [{"case": r["case"], "status": r["status"]} for r in records]}))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
