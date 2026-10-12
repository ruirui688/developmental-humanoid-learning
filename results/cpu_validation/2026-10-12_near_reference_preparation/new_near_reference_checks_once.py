"""One IV3 synthetic command/template check; no old fit, prediction or physics."""
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
    cost, identities, checks, failure = Counter(), {}, [], None
    with (output / "first_stdout.log").open("x", encoding="utf-8") as stdout, (output / "first_stderr.log").open("x", encoding="utf-8") as stderr:
        with redirect_stdout(stdout), redirect_stderr(stderr):
            try:
                runner = repo / "scripts/run_near_reference_identification.py"
                helper = repo / "scripts/refit_instrumental_state.py"
                paid_helper = repo / "scripts/develop_instrumental_action_response.py"
                for path in (runner, helper, paid_helper, Path(__file__).resolve()):
                    blob = path.read_bytes()
                    cost["source_file_reads"] += 1
                    cost["source_bytes_read"] += len(blob)
                    identities[str(path)] = {"bytes": len(blob), "sha256": hashlib.sha256(blob).hexdigest()}
                if identities[str(runner)]["sha256"] != args.runner_sha256:
                    raise ValueError("reviewed_IV3_runner_identity_differs")
                spec = importlib.util.spec_from_file_location("iv3_first_synthetic", runner)
                module = importlib.util.module_from_spec(spec)
                sys.modules[spec.name] = module
                spec.loader.exec_module(module)
                if (Path(module.__file__).resolve() != runner or Path(module.iv2.__file__).resolve() != helper
                    or Path(module.iv2.iv1.__file__).resolve() != paid_helper):
                    raise ValueError("canonical_pure_helper_import_required")
                qref = np.asarray((.13, -.07))
                q, v = np.asarray((.2, -.2)), np.asarray((.1, -.2))
                commands = []
                passed = True
                for bits, expected in (((0, 0), (-.5, .25)), ((0, 1), (-.5, .5)),
                                       ((1, 0), (-.25, .25)), ((1, 1), (-.25, .5))):
                    command = module.near_reference_request(q, v, qref, bits)
                    cost["new_synthetic_command_calls"] += 1
                    passed = passed and (command["current_target_q2"].tobytes() == qref.tobytes()
                        and np.array_equal(command["known_base2"], (-.375, .375))
                        and np.array_equal(command["request2"], expected)
                        and np.all(np.abs(command["request2"]) <= .5))
                    commands.append(module.safe(command))
                native_command = module.near_reference_request(qref, (0., 0.), qref, (1, 0))
                cost["new_synthetic_command_calls"] += 1
                passed = passed and np.array_equal(native_command["known_base2"], (0., 0.)) and np.array_equal(native_command["request2"], (.125, -.125))
                poison = {"model": "oldlearned", "actual_endpoint_q2": "must_not_be_read", "actual_endpoint_v2": "must_not_be_read"}
                ignored = module.saved_cold_template(poison)
                cold = {"seed": 8101, "model": "cold", "horizon": 10, "origin_active_index": 0,
                    "status": "completed", "available": True, "model_fingerprint": "synthetic_cold",
                    "model_input": {"q2": [.13, -.07], "v2": [.1, -.2], "known_requests2": [[.125, -.125]]*10},
                    "actual_endpoint_q2": [.14, -.08], "actual_endpoint_v2": [.2, -.3]}
                template = module.saved_cold_template(cold)
                incomplete_rejected = False
                try:
                    module.saved_cold_template({**cold, "available": False})
                except ValueError:
                    incomplete_rejected = True
                cost["new_synthetic_template_calls"] += 3
                passed = passed and ignored is None and incomplete_rejected and template["known_requests2"].shape == (10, 2)
                passed = passed and np.array_equal(template["q2"], qref) and np.array_equal(template["actual_endpoint_v2"], (.2, -.3))
                checks.append({"name": "constant_qref_PD_clip_independent_dither_permission_and_cold_template_selection",
                    "passed": bool(passed), "detail": {"commands": commands, "native_qref_command": module.safe(native_command),
                        "noncold_poison_excluded": ignored is None, "incomplete_rejected": incomplete_rejected, "cold_template": module.safe(template)}})
                if not passed:
                    raise AssertionError(checks[-1]["name"])
            except BaseException as exc:
                failure = {"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()}
                traceback.print_exc()
    report = {"status": "failed" if failure else "passed", "first_failure": failure, "checks": checks,
        "source_identities": identities, "synthetic_only_cost": dict(cost), "saved_raw_reads": 0,
        "fit_attempts": 0, "model_predict_calls": 0, "physics_calls": 0, "RLS_updates": 0,
        "unmeasured_pure_import_IO": "unknown_not_zero"}
    (output / "checks.json").write_text(json.dumps(report, ensure_ascii=False, allow_nan=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "checks": len(checks), "output": str(output)}))
    return 1 if failure else 0


if __name__ == "__main__":
    raise SystemExit(main())
