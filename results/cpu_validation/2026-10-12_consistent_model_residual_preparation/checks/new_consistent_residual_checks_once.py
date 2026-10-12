"""One new synthetic IV2D algebra/denominator/box check; no saved raw reads."""
import argparse
from collections import Counter
from contextlib import redirect_stdout, redirect_stderr
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import traceback

import numpy as np


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--runner-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repo, output = args.repo.resolve(), args.output.resolve()
    if output.exists() or output == repo or repo.is_relative_to(output):
        parser.error("existing_or_repository_containing_output_refused")
    output.mkdir(parents=True, exist_ok=False)
    cost, identity, checks, failure = Counter(), {}, [], None
    with (output / "first_stdout.log").open("x", encoding="utf-8") as stdout, (output / "first_stderr.log").open("x", encoding="utf-8") as stderr:
        with redirect_stdout(stdout), redirect_stderr(stderr):
            try:
                runner = repo / "scripts/diagnose_consistent_model_residual.py"
                for path in (runner, Path(__file__).resolve()):
                    blob = path.read_bytes()
                    identity[str(path)] = {"bytes": len(blob), "sha256": hashlib.sha256(blob).hexdigest()}
                    cost["source_file_reads"] += 1
                    cost["source_bytes_read"] += len(blob)
                if identity[str(runner)]["sha256"] != args.runner_sha256:
                    raise ValueError("reviewed_diagnostic_source_identity_differs")
                spec = importlib.util.spec_from_file_location("iv2d_first_synthetic", runner)
                module = importlib.util.module_from_spec(spec)
                sys.modules[spec.name] = module
                spec.loader.exec_module(module)
                psi = np.asarray(((0., 0., 0., 0., 1.), (1., 0., 0., 0., 1.), (0., 1., 0., 0., 1.)))
                state = np.asarray(((2., 0., 0., 0., 1.), (0., -2., 0., 0., -1.)))
                labels = np.asarray(((0., 0.), (1., -2.), (2., -2.)))
                residual = module.state_residual(psi, labels, state, cost)
                train = module.error_summary(residual, cost, training=True)
                saved = module.error_summary(residual, cost)
                bounds = np.asarray(((0., 0., 0., 0.), (1., 1., 1., 1.)))
                row = {"horizon": 3, "model_input": {"q2": [.13, -.07], "v2": [0., 0.]},
                    "predicted_q_path": [[.63, .43], [2.13, -.07], [99., 99.]],
                    "predicted_v_path": [[.5, .5], [1.5, -.1], [99., 99.]]}
                inputs = module.saved_recursive_inputs(row, [.13, -.07])
                box = module.box_summary(inputs, bounds, cost, "synthetic")
                expected = np.asarray(((1., -1.), (2., 1.), (-1., -1.)))
                passed = (np.array_equal(residual, expected) and train["count"] == 3 and saved["count"] == 3
                    and np.allclose(train["bias_axis"], [2./3., -1./3.], rtol=0., atol=1e-14)
                    and np.allclose(train["MAE_axis"], [4./3., 1.], rtol=0., atol=1e-14)
                    and np.allclose(train["population_std_axis"], [np.sqrt(14./9.), np.sqrt(8./9.)], rtol=0., atol=1e-14)
                    and np.allclose(train["training_RMSE_axis"], [np.sqrt(2.), 1.], rtol=0., atol=1e-14)
                    and "training_RMSE_axis" not in saved
                    and inputs.shape == (3, 4) and np.max(inputs) < 99.
                    and box["points"] == 3 and box["outside_any_coordinate_count"] == 1
                    and box["outside_count_each_coordinate"] == [1, 1, 1, 0]
                    and np.allclose(box["maximum_excess_each_coordinate"], [.5, .1, 1., 0.], rtol=0., atol=1e-14)
                    and cost["state_matmul_returns"] == 1 and cost["reused_training_Y_scalar_uses"] == 6
                    and cost["synthetic_input_points"] == 3 and cost["synthetic_box_scalar_uses"] == 12)
                checks.append({"name": "saved_residual_population_std_native_start_recursive_input_box_and_no_fresh_RMSE",
                    "passed": bool(passed), "detail": {"training": train, "saved": saved, "inputs": inputs.tolist(), "box": box}})
                if not passed:
                    raise AssertionError(checks[-1]["name"])
            except BaseException as exc:
                failure = {"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()}
                traceback.print_exc()
    report = {"status": "failed" if failure else "passed", "first_failure": failure, "checks": checks,
        "source_identities": identity, "synthetic_only_cost": dict(cost), "saved_raw_reads": 0,
        "real_data_algebra_calls": 0, "fit_attempts": 0, "model_predict_calls": 0, "physics_calls": 0, "RLS_updates": 0}
    (output / "checks.json").write_text(json.dumps(report, ensure_ascii=False, allow_nan=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "checks": len(checks), "output": str(output)}))
    return 1 if failure else 0


if __name__ == "__main__":
    raise SystemExit(main())
