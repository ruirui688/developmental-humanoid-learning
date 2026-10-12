"""First necessary synthetic checks of EF1D algebra; no saved data is read."""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import redirect_stderr, redirect_stdout
import hashlib
import importlib.util
import json
from pathlib import Path
import time
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
    checks, cost, files, first_failure = [], Counter(), {}, None
    wall, cpu = time.perf_counter(), time.process_time()
    with (output / "first_stdout.log").open("x", encoding="utf-8") as stdout, (output / "first_stderr.log").open("x", encoding="utf-8") as stderr:
        with redirect_stdout(stdout), redirect_stderr(stderr):
            try:
                runner = repo / "scripts/diagnose_model_action_error.py"
                for path in (runner, Path(__file__).resolve()):
                    cost["source_file_read_attempts"] += 1
                    blob = path.read_bytes()
                    cost["source_file_read_returns"] += 1
                    cost["source_bytes_read"] += len(blob)
                    files[str(path)] = {"bytes": len(blob), "sha256": hashlib.sha256(blob).hexdigest()}
                if files[str(runner)]["sha256"] != args.runner_sha256:
                    raise ValueError("reviewed_runner_identity_differs")
                spec = importlib.util.spec_from_file_location("ef1d_standalone_synthetic", runner)
                module = importlib.util.module_from_spec(spec)
                cost["standalone_module_import_attempts"] += 1
                spec.loader.exec_module(module)
                cost["standalone_module_import_returns"] += 1
                def theta(b, h=None):
                    cost["synthetic_coefficient_array_builds"] += 1
                    value = np.zeros((2, 9))
                    value[:, 4:6] = b
                    if h is not None:
                        value[:, 6:8] = h
                    return value
                def call(coefficients, *, q=(0., 0.), u=(.1, .1), e=(0., 0.), svd=None):
                    return module.diagnose_row(q, (0., 0.), u, e, coefficients, ((-1., 1.), (-1., 1.)), cost=cost, svd=svd)
                def check(name, condition, detail):
                    checks.append({"name": name, "passed": bool(condition), "detail": detail})
                    if not condition:
                        raise AssertionError(name)
                full = call(theta([[2., 0.], [0., 4.]]), e=(.02, -.04))
                branch = full["branches"][0]
                check("full_rank_direct_2ms_theta_no_extra_dt", len(full["branches"]) == 1 and branch["rank"] == 2
                      and branch["mapping_available"] and np.allclose(branch["minimum_norm_delta_u_nm"], (-.01, .01), rtol=0., atol=1e-15), full)
                rank1 = call(theta([[1., 0.], [0., 0.]]), e=(.1, .2))
                branch = rank1["branches"][0]
                check("rank1_nonimage_keeps_residual_unavailable", branch["rank"] == 1 and not branch["mapping_available"]
                      and np.allclose(branch["unmapped_error_rad_s"], (0., .2), rtol=0., atol=1e-15), rank1)
                zero, nonzero = call(theta(np.zeros((2, 2)))), call(theta(np.zeros((2, 2))), e=(.1, 0.))
                check("rank0_zero_and_nonzero_error_are_distinct", zero["branches"][0]["rank"] == 0
                      and zero["branches"][0]["mapping_available"] and not nonzero["branches"][0]["mapping_available"]
                      and nonzero["branches"][0]["minimum_norm_delta_u_nm"] == [0., 0.], {"zero": zero, "nonzero": nonzero})
                hinge = call(theta([[2., 0.], [0., 2.]], [[1., 0.], [0., 0.]]), u=(.25, .1), e=(-.03, 0.))
                check("hinge_keeps_both_sides_and_direction", len(hinge["branches"]) == 2
                      and [item["jacobian"][0][0] for item in hinge["branches"]] == [2., 3.]
                      and [item["mapping_available"] for item in hinge["branches"]] == [False, True], hinge)
                guard = call(theta([[2., 0.], [0., 2.]]), q=(-.97, 0.), u=(0., .1), e=(-.02, 0.))
                check("guard_equality_zero_keeps_blocked_and_inward_sides", len(guard["branches"]) == 2
                      and [item["jacobian"][0][0] for item in guard["branches"]] == [0., 2.]
                      and [item["mapping_available"] for item in guard["branches"]] == [False, True], guard)
                outside = call(theta([[1., 0.], [0., 1.]]), u=(.4, .1), e=(-.2, 0.))
                endpoint = call(theta([[1., 0.], [0., 1.]]), u=(.5, .1), e=(-.1, 0.))
                cross = call(theta([[1., 0.], [0., 1.]]), q=(-.97, 0.), u=(.01, .1), e=(.05, 0.))
                check("permission_and_guard_crossing_never_clip_or_change_branch", not outside["branches"][0]["mapping_available"]
                      and outside["branches"][0]["candidate_request_nm"][0] > .5
                      and np.isclose(outside["branches"][0]["minimum_norm_delta_u_nm"][0], .2)
                      and len(endpoint["branches"]) == 1 and not endpoint["branches"][0]["mapping_available"]
                      and cross["branches"][0]["crossed_guard_sign_cut_axis"][0], {"outside": outside, "endpoint": endpoint, "cross": cross})
                line = call(theta([[1., 1.], [0., 0.]]), u=(.1, .2), e=(.3, 0.))
                branch = line["branches"][0]
                check("rank1_minimum_norm_crossbox_does_not_search_nullspace", branch["rank"] == 1
                      and branch["numeric_image_compatible"] and not branch["mapping_available"]
                      and branch["rank1_outside_box_does_not_exclude_other_nullspace_solutions"], line)
                def fault(*args, **kwargs):
                    raise RuntimeError("synthetic_SVD_fault")
                before = dict(cost)
                try:
                    call(theta([[1., 0.], [0., 1.]]), svd=fault)
                except RuntimeError as exc:
                    preserved = getattr(exc, "action_error_partial_record", None)
                    check("technical_SVD_error_raises_with_partial_cost_and_record", preserved is not None
                          and preserved["branches"][0]["status"] == "technical_failure"
                          and cost["svd_attempts"] == before.get("svd_attempts", 0)+1
                          and cost["svd_returns"] == before.get("svd_returns", 0), preserved)
                else:
                    raise AssertionError("technical_exception_was_hidden")
            except BaseException as exc:
                first_failure = {"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()}
                traceback.print_exc()
    cost["wall_seconds"], cost["cpu_seconds"] = time.perf_counter()-wall, time.process_time()-cpu
    report = {"status": "failed" if first_failure else "passed", "checks": checks, "first_failure": first_failure,
              "source_identities": files, "synthetic_only_cost": dict(cost), "saved_data_reads": 0,
              "model_predict_calls": 0, "physics_calls": 0, "fit_calls": 0, "RLS_updates": 0,
              "unmeasured_import_and_filesystem_IO": "unknown_not_zero",
              "timing_excludes": "final_result_JSON_encoding_and_report_writes"}
    (output / "checks.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "checks": len(checks), "output": str(output)}))
    return 1 if first_failure else 0


if __name__ == "__main__":
    raise SystemExit(main())
