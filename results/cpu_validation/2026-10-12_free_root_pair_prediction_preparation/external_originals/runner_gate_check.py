"""Exactly six first-use stdlib synthetic FR1 gate cases; no production import."""
from __future__ import annotations
import ast
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import traceback

CANDIDATE = Path("external/c4_free_learning_candidate/develop_free_root_pair.py")
EXPECTED_SHA256 = "24ba8ff3853af16081077da7ccb5acc3b527908d7cb5ed6d661631bde79f8c15"
OUTPUT = Path("external/c4_free_learning_candidate")
RECEIPT = OUTPUT / "runner_gate_check_first.json"
ALLOWED_FUNCTIONS = {"normalize_metrics_boundary", "_require_fr1_trial", "_require_fr1"}
ALLOWED_CONSTANTS = {"FLAGS", "GATE_FLAGS", "SEEDS"}


def identity(data):
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def main():
    if RECEIPT.exists():
        raise FileExistsError("first gate receipt exists; no rerun or overwrite")
    receipt = {"schema": "FR1_gate_first_stdlib_synthetic_v1", "created_at_utc": datetime.now(timezone.utc).isoformat(),
               "status": "failed", "fixed_cases": 6, "cases": [], "production_imports": 0,
               "raw_reads": 0, "saved_weight_or_snapshot_file_reads": 0,
               "new_physics": 0, "model_or_prediction_calls": 0, "fit": 0, "RLS": 0,
               "old_check_or_batch_fixture_runs": 0, "filesystem_IO": "unmeasured_not_zero"}
    try:
        data = CANDIDATE.read_bytes()
        receipt["runner"] = {"path": str(CANDIDATE), **identity(data)}
        if hashlib.sha256(data).hexdigest() != EXPECTED_SHA256:
            raise ValueError("first_gate_check_runner_identity_differs")
        tree = ast.parse(data.decode("utf-8"), filename=str(CANDIDATE))
        namespace, functions = {}, []
        for node in tree.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id in ALLOWED_CONSTANTS:
                        namespace[target.id] = ast.literal_eval(node.value)
            elif isinstance(node, ast.FunctionDef) and node.name in ALLOWED_FUNCTIONS:
                functions.append(node)
        if set(namespace) != ALLOWED_CONSTANTS or {node.name for node in functions} != ALLOWED_FUNCTIONS:
            raise ValueError("only_exact_three_new_stdlib_gate_functions_required")
        exec(compile(ast.Module(body=functions, type_ignores=[]), str(CANDIDATE), "exec"), namespace)
        receipt["executed_functions"] = sorted(ALLOWED_FUNCTIONS)
        flags, seeds = namespace["FLAGS"], namespace["SEEDS"]
        normalize, require = namespace["normalize_metrics_boundary"], namespace["_require_fr1"]
        files = {"scripts/develop_free_root_pair.py": {"bytes": 1, "sha256": "0" * 64},
                 "src/developmental_physics/assets/ground_body.xml": {"bytes": 2, "sha256": "1" * 64}}

        def trial(seed, kind, active):
            phases = {}
            for name, count in (("prefix", 1000), ("active", active)):
                phases[name] = {"qualification_passed": True, "planned_count": count, "record_count": count,
                                "confirmed_substeps": count, "observed_contact_endpoints": count,
                                "unknown_paid_contact_substeps": 0,
                                "classes": {"left_arm": {"positive_contact_endpoint_count": 1}}}
            return {"seed": seed, "kind": kind, "trial_id": f"synthetic_FR_{seed}_{kind}",
                    "complete": True, "native_execution_complete": True, "status": "completed",
                    "stop": None, "failure": None, "metadata_stable": True, "planned_prefix": 1000,
                    "planned_active": active, "returned_intervals": 1000 + active,
                    "free_root_domain_qualification_passed": True, "original_asset_unchanged_no_mount": True,
                    "installed_xml_identity": deepcopy(files["src/developmental_physics/assets/ground_body.xml"]),
                    "support": {"root": "original_asset_freejoint", "mount": None, "external_support": False,
                                "initial_pose": "supine"},
                    "contact_population": {"qualification_passed": True, "no_contact_based_training_selection": True,
                                           "contact_causality_or_continuous_support_demonstrated": False,
                                           "phases": phases},
                    "actual_effort": {name: {"complete": True, "actual_effort_population_complete": True,
                                             "unknown_actual_effort_substeps": 0} for name in ("prefix", "active")}}

        rows = [{"seed": seed, "calibration": trial(seed, "calibration", 4000),
                 "prediction": trial(seed, "prediction", 1000),
                 "prediction_scores": {"complete_population": True, "native_execution_complete": True,
                                       "free_root_domain_qualification_passed": True}} for seed in seeds]
        base = {"run.json": {"experiment_id": "FR1", "stage": "prediction", "seeds": seeds,
                             "source": {"files": deepcopy(files)}, "unattempted_seeds": [],
                             "cost": {"control_call_returns": 21000, "confirmed_physics_substeps": 21000,
                                      "RLS_vector_update_commits": 12000, "RLS_scalar_update_commits": 24000},
                             "seed_results": rows, "trials": [row[kind] for row in rows for kind in ("calibration", "prediction")]},
                "metrics.json": {"fr1_prediction_gate_passed": True, "complete_population": True, **flags},
                "models.json": {str(seed): {"cold": {"vector_update_count": 0, "trainable": False},
                                            "learned": {"vector_update_count": 4000, "trainable": False}}
                                for seed in seeds}}
        manifest = {"experiment_id": "FR1", "stage": "prediction"}

        def execute_case(name, edit, expected_error=None):
            loaded = deepcopy(base)
            normalize(loaded["metrics.json"])
            edit(loaded)
            outcome = {"name": name, "expected": "accept" if expected_error is None else "reject"}
            try:
                require(loaded, deepcopy(manifest), deepcopy(files))
                if expected_error is not None:
                    raise AssertionError("invalid_fixture_accepted")
                if any(loaded["metrics.json"][key] is not False for key in namespace["GATE_FLAGS"] if key != "fr1_prediction_gate_passed"):
                    raise AssertionError("omitted_control_gate_defaults_not_false")
                if loaded["metrics.json"]["fr1_prediction_gate_passed"] is not True:
                    raise AssertionError("valid_prediction_success_erased")
                failed = normalize(deepcopy(loaded["metrics.json"]), failed=True)
                if any(failed[key] is not False for key in namespace["GATE_FLAGS"]):
                    raise AssertionError("exception_boundary_did_not_veto_all_gates")
                outcome.update(passed=True, actual="accept")
            except ValueError as exc:
                outcome.update(passed=expected_error is not None and expected_error in str(exc),
                               actual="reject", error_type=type(exc).__name__, error=str(exc))
            except BaseException as exc:
                outcome.update(passed=False, error_type=type(exc).__name__, error=str(exc))
            receipt["cases"].append(outcome)
            print(json.dumps(outcome, ensure_ascii=False, allow_nan=False), flush=True)

        execute_case("valid_FR1_with_stage_false_defaults", lambda loaded: None)
        execute_case("prediction_domain_qualification_missing", lambda loaded: loaded["run.json"]["seed_results"][0]["prediction"].update(free_root_domain_qualification_passed=False), "complete_new_FR1_native_contact_domain_trial_required")
        execute_case("calibration_partial_paid_population", lambda loaded: loaded["run.json"]["seed_results"][0]["calibration"].update(returned_intervals=4999), "complete_new_FR1_native_contact_domain_trial_required")
        execute_case("learned_snapshot_count_drift", lambda loaded: loaded["models.json"][str(seeds[0])]["learned"].update(vector_update_count=4001), "new_FR1_zero_and_4000_atomic_frozen_counts_required")
        execute_case("source_pin_drift", lambda loaded: loaded["run.json"]["source"]["files"]["scripts/develop_free_root_pair.py"].update(sha256="2" * 64), "all_new_FR1_frozen_dependencies_required_for_FR2")
        execute_case("premature_control_success_flag", lambda loaded: loaded["metrics.json"].update(fr2_model_contribution_gate_passed=True), "FR1_prediction_cannot_predeclare_control_mechanism_success")
        receipt.update(case_count=len(receipt["cases"]), failed_count=sum(row.get("passed") is not True for row in receipt["cases"]))
        receipt["status"] = "passed" if receipt["case_count"] == 6 and receipt["failed_count"] == 0 else "failed"
    except BaseException as exc:
        receipt["failure"] = {"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()}
    with RECEIPT.open("x", encoding="utf-8") as stream:
        json.dump(receipt, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"status": receipt["status"], "case_count": len(receipt["cases"]),
                      "failed_count": receipt.get("failed_count"), "output": str(RECEIPT)}, ensure_ascii=False), flush=True)
    return 0 if receipt["status"] == "passed" else 1

if __name__ == "__main__":
    raise SystemExit(main())
