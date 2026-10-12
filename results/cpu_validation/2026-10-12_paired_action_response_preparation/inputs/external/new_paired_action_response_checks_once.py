"""Six first synthetic PAR1 checks; never construct a physical environment."""
from collections import Counter
from contextlib import redirect_stdout, redirect_stderr
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import time
import traceback
from types import SimpleNamespace

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
    cost, checks, files, failure = Counter(), [], {}, None
    wall, cpu = time.perf_counter(), time.process_time()
    with (output / "first_stdout.log").open("x", encoding="utf-8") as stdout, (output / "first_stderr.log").open("x", encoding="utf-8") as stderr:
        with redirect_stdout(stdout), redirect_stderr(stderr):
            try:
                runner = repo / "scripts/diagnose_paired_action_response.py"
                for path in (runner, Path(__file__).resolve()):
                    cost["source_file_reads"] += 1
                    blob = path.read_bytes()
                    cost["source_bytes_read"] += len(blob)
                    files[str(path)] = {"bytes": len(blob), "sha256": hashlib.sha256(blob).hexdigest()}
                if files[str(runner)]["sha256"] != args.runner_sha256:
                    raise ValueError("reviewed_runner_identity_differs")
                spec = importlib.util.spec_from_file_location("par1_synthetic_runner", runner)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                def check(name, condition, detail):
                    checks.append({"name": name, "passed": bool(condition), "detail": module.safe(detail)})
                    if not condition:
                        raise AssertionError(name)
                theta = np.zeros((2, 9))
                cost["synthetic_theta_builds"] += 1
                theta[:, 4:6] = [[.002, .001], [-.003, .004]]
                theta[:, 6:8] = [[.001, 0.], [0., .003]]
                ranges = ((-1., 1.), (-1., 1.))
                effect = module.model_effect((0., 0.), (.2, -.2), (.325, -.2), ranges, theta, cost)
                check("finite_hinge_crossing_direct_2ms_coefficients", np.allclose(effect, (.000325, -.000375), rtol=0., atol=1e-16), effect)
                effect = module.model_effect((-.97, 0.), (-.1, .1), (.025, .1), ranges, theta, cost)
                blocked = module.model_effect((-.97, 0.), (-.1, .1), (-.225, .1), ranges, theta, cost)
                check("guard_equality_and_zero_effective_input", np.allclose(effect, (.00005, -.000075), rtol=0., atol=1e-16)
                      and np.array_equal(blocked, np.zeros(2)), {"outward_to_inward": effect, "blocked": blocked})
                illegal, permission = module.side_request((.475, .1), 0, 1)
                legal, allowed = module.side_request((.475, .1), 0, -1)
                check("fixed_dose_permission_never_clips", not permission and allowed and np.isclose(illegal[0], .6)
                      and np.isclose(legal[0], .35), {"illegal": illegal, "legal": legal})
                weak = module.effect_summary((.2, .4), (.2, .4), {"cold": (0., 0.), "learned": (.01, 0.)}, cost)
                signal = module.effect_summary((.2, .4), (.201, .4), {"cold": (.002, 0.), "learned": (.001, 0.)}, cost)
                check("signal_floor_and_signed_model_response_error", weak["weak_signal"] and not signal["weak_signal"]
                      and np.allclose(signal["model_error_v2"]["cold"], (.001, 0.), rtol=0., atol=1e-15), {"weak": weak, "signal": signal})
                fake = SimpleNamespace(last_command=np.arange(8.), step_id=10, physics_steps=10, _reset_done=True,
                                       terminated=False, reason=None)
                snapshot = module.python_state(fake)
                fake.last_command[:] = -1
                fake.physics_steps = 999
                cost["global_paid_marker"] = 7
                module.restore_python(fake, snapshot)
                observation = {"joint_position": [.12, 0., 0., 0., 0., 0., 0., 0.], "joint_velocity": [0., 1., 0., 0., 0., 0., 0., 0.]}
                abort = module.study_abort(observation, np.zeros(2))
                check("python_state_copy_independent_global_cost_and_original_stop", module.same_python(module.python_state(fake), snapshot)
                      and cost["global_paid_marker"] == 7 and len(abort["triggers"]) == 2, {"state": snapshot, "abort": abort})
                failed = False
                try:
                    module.model_effect((0., 0.), (.1, .1), (float("nan"), .1), ranges, theta, cost)
                except ValueError:
                    failed = True
                outside_failed = False
                try:
                    module.model_effect((0., 0.), (.1, .1), (.6, .1), ranges, theta, cost)
                except ValueError:
                    outside_failed = True
                check("technical_nonfinite_and_illegal_model_input_raise", failed and outside_failed
                      and cost["model_response_pair_exceptions"] == 2, dict(cost))
            except BaseException as exc:
                failure = {"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()}
                traceback.print_exc()
    cost["wall_seconds"], cost["cpu_seconds"] = time.perf_counter()-wall, time.process_time()-cpu
    report = {"status": "failed" if failure else "passed", "checks": checks, "first_failure": failure,
              "source_identities": files, "synthetic_only_cost": dict(cost), "saved_raw_reads": 0,
              "environment_constructions": 0, "physics_calls": 0, "model_predict_calls": 0, "fit_calls": 0,
              "RLS_updates": 0, "unmeasured_import_IO": "unknown_not_zero"}
    (output / "checks.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "checks": len(checks), "output": str(output)}))
    return 1 if failure else 0


if __name__ == "__main__":
    raise SystemExit(main())
