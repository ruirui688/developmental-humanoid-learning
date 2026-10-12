"""First-only CFD1 synthetic difference-target and whole-trial exclusion checks."""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import redirect_stderr, redirect_stdout
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import traceback

import numpy as np


def identity(blob):
    return {"bytes": len(blob), "sha256": hashlib.sha256(blob).hexdigest()}


def transition(seed, index, v, next_v, request):
    return {"seed": seed, "trial_id": "synthetic_"+str(seed), "control_index": index, "active_index": index-1,
            "q": np.zeros(2), "v": np.asarray(v, dtype=np.float64), "request": np.asarray(request, dtype=np.float64),
            "next_q": np.zeros(2), "next_v": np.asarray(next_v, dtype=np.float64)}


def pair(seed):
    previous = transition(seed, 1, [.1, .2], [.15, .19], [.1, -.2])
    current = transition(seed, 2, [.15, .19], [.22, .17], [.3, -.1])
    return previous, current


def check_difference_target(runner, body):
    cost = Counter()
    ranges = np.asarray([[-1., 1.], [-1., 1.]])
    previous, current = pair(1)
    x, y = runner.difference_sample(previous, current, ranges, body, cost)
    np.testing.assert_allclose(x, np.asarray([.2, .1, .05, 0.]), rtol=0., atol=1e-14)
    np.testing.assert_allclose(y, np.asarray([.02, -.01]), rtol=0., atol=1e-14)
    b = np.asarray([[.4, -.1, .2, 0.], [.05, .3, 0., -.2]])
    action_difference = b @ x
    predicted_next_v = current["v"]+(current["v"]-previous["v"])+action_difference
    regression_error = y-action_difference
    direct_one_step_error = current["next_v"]-predicted_next_v
    np.testing.assert_allclose(regression_error, np.asarray([-.06, -.05]), rtol=0., atol=1e-14)
    np.testing.assert_allclose(regression_error, direct_one_step_error, rtol=0., atol=1e-14)
    return {"case": "difference_sign_and_causal_one_step_target_alignment", "passed": True,
            "X": x.tolist(), "Y": y.tolist(), "regression_error": regression_error.tolist(),
            "cost": dict(cost), "synthetic_fixed_B_matvec_calls": 1,
            "pair_prediction_calls": 0, "OLS_or_fit_calls": 0}


class ForbiddenEvaluationRows:
    def __getitem__(self, key):
        raise AssertionError("own_evaluation_trial_entered_difference_design")


def check_fold_exclusion(runner, body):
    ranges, cost = np.asarray([[-1., 1.], [-1., 1.]]), Counter()
    rows = {1: ForbiddenEvaluationRows()}
    for seed in (2, 3):
        previous, current = pair(seed)
        rows[seed] = [None, previous, current]
    x, y, provenance = runner.difference_design(rows, 1, ranges, body, cost,
        seeds=(1, 2, 3), active_indices=(1,), prefix_count=1)
    assert runner.fold_training_seeds(1, (1, 2, 3)) == (2, 3)
    assert x.shape == (2, 4) and y.shape == (2, 2)
    assert [item["training_seed"] for item in provenance] == [2, 3]
    assert all(item["active_index"] == 1 and item["previous_control_index"] == 1
               and item["current_control_index"] == 2 for item in provenance)
    assert cost["difference_sample_returns"] == 2
    return {"case": "whole_trial_design_and_Y_exclude_own_eval_seed", "passed": True,
            "training_seeds": [2, 3], "X_shape": list(x.shape), "Y_shape": list(y.shape),
            "provenance": provenance, "own_trial_reads": 0, "cost": dict(cost),
            "pair_prediction_calls": 0, "OLS_or_fit_calls": 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repo, output = args.repo.resolve(), args.output.resolve()
    if output.exists() or output == repo or repo.is_relative_to(output):
        parser.error("first_new_output_directory_required")
    output.mkdir(parents=True, exist_ok=False)
    script_blob = Path(__file__).read_bytes()
    (output / "check_script.py").write_bytes(script_blob)
    result = {"status": "running", "checks": [], "first_failure": None, "script": identity(script_blob),
              "old_data_reads": 0, "new_physics_calls": 0, "old_model_calls": 0,
              "pair_prediction_calls": 0, "OLS_or_fit_calls": 0,
              "scope": "difference_target_and_fold_exclusion_only_no_CF1_history_retest"}
    def seal():
        (output / "checks.json").write_text(json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2)+"\n", encoding="utf-8")
    seal()
    with (output / "first_stdout.log").open("x", encoding="utf-8") as stdout, (output / "first_stderr.log").open("x", encoding="utf-8") as stderr:
        with redirect_stdout(stdout), redirect_stderr(stderr):
            try:
                sys.path.insert(0, str(repo / "src"))
                import developmental_physics.causal_incremental_pair_model as body
                runner_path = repo / "scripts/develop_causal_difference_prediction.py"
                spec = importlib.util.spec_from_file_location("_new_causal_difference_check_runner", runner_path)
                runner = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(runner)
                result["source"] = {name: identity((repo / name).read_bytes()) for name in runner.SOURCE_PATHS}
                result["runtime"] = {"python": sys.version, "numpy": np.__version__}
                seal()
                for check in (check_difference_target, check_fold_exclusion):
                    case = check(runner, body)
                    result["checks"].append(case)
                    with (output / "case_results.jsonl").open("a", encoding="utf-8") as history:
                        history.write(json.dumps(case, ensure_ascii=False, allow_nan=False)+"\n")
                        history.flush()
                    seal()
                result["status"] = "passed"
            except BaseException as exc:
                result["status"] = "failed"
                result["first_failure"] = {"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()}
                traceback.print_exc()
            finally:
                seal()
    print(json.dumps(result))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
