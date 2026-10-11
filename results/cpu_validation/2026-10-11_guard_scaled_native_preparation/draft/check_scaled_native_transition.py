"""New N-only synthetic scale contracts; no archived inputs, old fits or rollout."""
from __future__ import annotations

import argparse
from collections import Counter
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
REPO = ROOT.parents[1]
spec = importlib.util.spec_from_file_location("N_synthetic_only", ROOT/"develop_guard_scaled_native_transition.py")
code = importlib.util.module_from_spec(spec)
spec.loader.exec_module(code)
core = code.load_core(REPO)  # definitions only; no old main, input reads, fit or prediction


def require(value, message):
    if not value:
        raise AssertionError(message)


def fixture():
    generator = np.random.default_rng(321)
    phi = generator.normal(size=(400, 29))*np.geomspace(.1, 10., 29)
    phi[:, 26] = 1.
    delta = generator.normal(size=(400, 22))
    return phi, delta


def reference_product(left, right, cost):
    cost["matrix_attempts"] += 1
    try:
        result = left @ right
    except BaseException:
        cost["matrix_failures"] += 1
        raise
    cost["matrix_returns"] += 1
    return result


def scale_equivalence(journal):
    phi, delta = fixture()
    cost, record = Counter(), {}
    journal["cost"] = cost
    reference_cost = Counter()
    journal["reference_cost"] = reference_cost
    weights = code.fit_scaled(core, phi, delta, cost, record)
    scale = np.asarray(record["scale29"])
    require(scale[26] == 1., "uncentered constant scale unchanged")
    # New N objective equivalence, not a rerun of K's isotropic ridge test.
    reference_gram = reference_product(phi.T, phi, reference_cost)
    reference_cost["scalar_labels_requested"] += int(delta.size)
    reference_cross = reference_product(phi.T, delta, reference_cost)
    reference_cost["scalar_labels_returned"] += int(delta.size)
    reference_cost["solve_attempts"] += 1
    try:
        reference = np.linalg.solve(reference_gram+.01*np.diag(scale**2), reference_cross)
    except BaseException:
        reference_cost["solve_failures"] += 1
        raise
    reference_cost["solve_returns"] += 1
    reference_cost["scalar_coefficients_estimated"] += int(reference.size)
    require(np.allclose(weights, reference, rtol=1e-10, atol=1e-10), "diagonal penalty equivalence")
    query = np.linspace(-.7, .9, 29)
    journal["forward_vector_products_requested"] = 1
    raw = query @ weights
    journal["forward_vector_products_returned"] = 1
    journal["forward_output_scalars_returned"] = int(raw.size)
    journal["forward_vector_products_requested"] += 1
    scaled = (query/scale) @ np.asarray(record["normalized_weights29x22"])
    journal["forward_vector_products_returned"] += 1
    journal["forward_output_scalars_returned"] += int(scaled.size)
    require(np.allclose(raw, scaled, rtol=1e-12, atol=1e-12), "all22 raw/scaled forward equivalence")
    require(cost["fit_returns"] == 1 and cost["fit_scalar_labels_returned"] == 8800, "fit usage")
    require(cost["transition_scalar_coefficients_fitted"] == 638, "independent fitted coefficients")
    return {"cost": dict(cost), "reference_cost": dict(reference_cost),
        "new_N_solve_returns": 1, "forward_vector_products": 2, "forward_output_scalars": 44}


def zero_rejection(journal):
    phi, delta = fixture()
    phi[:, 3] = 0.
    cost, record = Counter(), {}
    journal["cost"] = cost
    try:
        code.fit_scaled(core, phi, delta, cost, record)
    except ValueError as exc:
        require("strictly positive" in str(exc), "zero scale explicit rejection")
    else:
        raise AssertionError("zero RMS accepted or replaced")
    require(record["scale29"][3] == 0., "rejected finite scale partial retained")
    require(cost["fit_attempts"] == 1 and cost["fit_returns"] == 0 and cost["fit_failures"] == 1, "failed fit accounting")
    require(cost["scale_input_scalar_uses_requested"] == 11600 and cost["scale_input_scalar_uses_returned"] == 11600,
            "already-computed scale usage retained")
    require(cost["scale_validation_failures"] == 1 and cost["fit_shared_29x29_22rhs_solve_attempts"] == 0,
            "zero rejects before solve")
    require(cost["fit_scalar_labels_requested"] == 0, "no labels enter rejected fit")
    return {"cost": dict(cost), "zero_column": 3, "new_N_solve_returns": 0}


def near_zero_risk(journal):
    phi, _ = fixture()
    phi[:, 0] *= 1e-11  # original .1 scale becomes approximately 1e-12
    delta = np.zeros((400, 22))
    delta[:, 9] = phi[:, 0]/1e-12
    cost, record = Counter(), {}
    journal["cost"] = cost
    weights = code.fit_scaled(core, phi, delta, cost, record)
    require(0 < record["scale29"][0] < 1e-11, "tiny positive scale not silently floored")
    require(abs(weights[0, 9]) > 1e10, "mapped raw coefficient can amplify weak feature")
    journal["sensitivity_scalar_multiplications_requested"] = 22
    response_change = 1e-8*weights[0, :]
    journal["sensitivity_scalar_multiplications_returned"] = int(response_change.size)
    require(abs(response_change[9]) > 100., "small raw perturbation can amplify output")
    require(np.isfinite(weights).all(), "finite coefficients do not establish robustness")
    return {"cost": dict(cost), "tiny_scale": record["scale29"][0],
        "raw_coefficient_output9": float(weights[0, 9]), "output9_change_for_raw_1e_minus8": float(response_change[9]),
        "new_N_solve_returns": 1, "sensitivity_scalar_multiplications": 22}


def failure_partial(fixture_root, journal):
    phi, delta = fixture()
    qref = (0.,)*8
    restored = {s: {"qref8": qref, "weights": np.zeros((29, 22)), "phi": phi, "delta": delta,
        "ids": [f"synthetic_C:{i}" for i in range(400)], "qref_source_transition_id": "synthetic_C:99",
        "fingerprint": "synthetic_frozen_K"} for s in code.SEEDS}
    models = {s: SimpleNamespace(qref=(0., 0.), parameter_fingerprint=lambda: "synthetic_frozen_D") for s in code.SEEDS}
    trials = {f"seed{s}_prediction": {} for s in code.SEEDS}
    counts = {name: 100 for name in trials}
    args = SimpleNamespace(repo=str(REPO), source_commit="0"*40, output=str(fixture_root/"solve_failure"))
    journal["fixture_directory"] = args.output
    journal["cost"] = "unknown_before_main_fit_counter_bound"
    original_fit = code.fit_scaled
    def journaled_fit(helper, design, labels, counter, record):
        journal["cost"] = counter
        return original_fit(helper, design, labels, counter, record)
    with patch.object(code, "frozen_sources", return_value={"status": "synthetic_source_only"}), \
         patch.object(code, "load_core", return_value=core), \
         patch.object(code, "read_inputs", return_value=({f"{code.C_ROOT}/trace.jsonl.gz": b""}, {f"{code.K_ROOT}/parameters.json": [],
             f"{code.D_ROOT}/raw/diagnostics.json": []}, {"dependencies": {"synthetic": True}})), \
         patch.object(code, "restore_K", return_value=restored), \
         patch.object(core, "restore_models", return_value=models), \
         patch.object(code, "parse_prediction", return_value=(trials, counts)), \
         patch.object(code, "fit_scaled", side_effect=journaled_fit), \
         patch.object(core, "prefix_qref", return_value=(qref, "synthetic_prediction:99")), \
         patch.object(code.np.linalg, "solve", side_effect=np.linalg.LinAlgError("synthetic solve failure")):
        require(code.main_run(args) == 1, "injected failure archived")
    output = Path(args.output)
    run = json.loads((output/"run.json").read_text(encoding="utf-8"))
    parameters = json.loads((output/"parameters.json").read_text(encoding="utf-8"))
    failure = json.loads((output/"failure.json").read_text(encoding="utf-8"))
    require(run["status"] == failure["status"] == "failed" and not run["development_gate_passed"], "failure closes gate")
    require(len(parameters) == 1 and not parameters[0]["available"], "first failed seed partial not retried")
    partial = parameters[0]["fit"]
    require(all(key in partial for key in ("scale29", "normalized_phi400x29", "gram29x29", "cross29x22", "ridge_normal29x29")),
            "paid partial arrays retained")
    cost = run["cost"]
    require(cost["fit_attempts"] == 1 and cost["fit_returns"] == 0 and cost["fit_failures"] == 1, "whole fit failed once")
    require(cost["fit_shared_29x29_22rhs_solve_attempts"] == 1 and cost["fit_shared_29x29_22rhs_solve_returns"] == 0 and
            cost["fit_shared_29x29_22rhs_solve_failures"] == 1, "solve attempt/failure retained")
    require(cost["fit_scalar_labels_returned"] == 8800 and cost["fit_gram_matrix_returns"] == cost["fit_cross_matrix_returns"] == 1,
            "paid labels and products before failed solve retained")
    require(run["original_C_dependencies"] == {"synthetic": True}, "read metadata retained")
    require(len(run["inputs_without_returned_read_record"]) == 9, "unread real payloads unknown")
    require((output/"predictions.jsonl").read_bytes() == b"", "fit failure no rollout")
    return {"cost": cost, "new_N_solve_returns": 0, "mock_solve_attempts": 1, "mock_solve_failures": 1,
            "actual_archived_payload_reads": 0, "fixture": str(output)}


def main():
    wall_started, cpu_started = time.perf_counter(), time.process_time()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--only", choices=("scale_equivalence", "zero_rejection", "near_zero_risk", "failure_partial"))
    args = parser.parse_args()
    output = Path(args.output).resolve()
    if output.exists():
        raise FileExistsError(output)
    cases = {"scale_equivalence": scale_equivalence, "zero_rejection": zero_rejection,
             "near_zero_risk": near_zero_risk,
             "failure_partial": lambda journal: failure_partial(output.with_suffix(".fixtures"), journal)}
    records = []
    for name, function in cases.items():
        if args.only and args.only != name:
            continue
        journal = {"cost": "unknown_before_case_counter_registered", "function_returned": False}
        try:
            detail = function(journal)
            journal["function_returned"] = True
            records.append({"case": name, "status": "passed", "detail": detail, "journal": journal})
        except BaseException as exc:
            records.append({"case": name, "status": "failed", "journal": journal, "failure": {
                "type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()}})
    passed = all(row["status"] == "passed" for row in records)
    report = {"passed": passed, "synthetic_only": True, "actual_archived_payload_reads": 0,
        "physics_calls": 0, "RLS_updates": 0, "MPC_calls": 0, "old_checks_repeated": False,
        "runtime": {"python": platform.python_version(), "numpy": np.__version__},
        "wall_seconds_before_serialization": time.perf_counter()-wall_started,
        "cpu_seconds_before_serialization": time.process_time()-cpu_started,
        "source_sha256": {name: code.digest((ROOT/name).read_bytes()) for name in
            ("develop_guard_scaled_native_transition.py", "GUARD_SCALED_NATIVE_TRANSITION_DEVELOPMENT_PROTOCOL.md",
             "check_scaled_native_transition.py")}, "cases": records}
    output.write_bytes(code.json_bytes(report))
    print(json.dumps({"output": str(output), "passed": passed,
        "cases": [{"case": row["case"], "status": row["status"]} for row in records]}))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
