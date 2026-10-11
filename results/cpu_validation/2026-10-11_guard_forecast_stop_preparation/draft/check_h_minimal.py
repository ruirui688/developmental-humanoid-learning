"""Only new H small branches; never reads actual G or executes run()."""
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import time

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "diagnose_guard_pd_tail_forecast_stop.py"
wall, cpu = time.perf_counter(), time.process_time()
blob = SOURCE.read_bytes()
spec = importlib.util.spec_from_file_location("h_draft", SOURCE)
h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)
checks = []


def check(name, condition):
    checks.append({"name": name, "passed": bool(condition)})


# Two tiny selected decisions, not a collector/environment fixture.
q = [[0., 0.] for _ in range(15)]
v = [[0., 0.] for _ in range(15)]
q[0][0] = .12
v[1][1] = 1.
d = {"fallback": False, "feasible_candidates": 1, "predicted_q": q,
     "predicted_v": v, "trajectory_requested_torque": [[0., 0.] for _ in range(15)]}
f = h.forecast(d, [0., 0.])
check("boundary_inclusive_and_stage_split", f["segments"]["stage0"][0]["q_violation_stages"] == [0]
      and f["segments"]["tail"][1]["v_violation_stages"] == [1]
      and f["segments"]["tail"][0]["first_violation_stage"] is None)
group = h.empty_group(0, "cold11", "A")
h.add_group(group, f)
h.add_group(group, f)
check("fixed_stage_and_decision_denominators", group["saved_active_count"] == 2
      and group["stage0"][0]["stage_comparison_count"] == 2
      and group["tail"][1]["stage_comparison_count"] == 28
      and group["tail"][1]["v_violating_stage_count"] == 2
      and group["tail"][1]["decisions_with_either_violation"] == 2)
fallback = h.forecast({**d, "fallback": True}, [0., 0.])
h.add_group(group, fallback)
check("fallback_never_becomes_selected_or_safe", fallback == {"category": "fallback", "segments": None}
      and group["saved_active_count"] == 3 and group["stage0"][0]["stage_comparison_count"] == 2)
check("missing_and_invalid_selected_are_separate", h.forecast(None, [0., 0.])["category"] == "missing_decision"
      and h.forecast({**d, "trajectory_requested_torque": []}, [0., 0.])["category"] == "missing_or_invalid_selected_h15")
empty = [h.empty_group(seed, kind, segment) for seed, kind in h.TRIALS for segment in ("A", "B")]
check("all_twelve_empty_segments_are_explicit", len(empty) == 12
      and all(g["empty_target_segment"] and g["tail"][0]["max_abs_v_rad_s"] is None for g in empty))
partial = h.endpoint_error([[.1, .2], [.3, .4]], [.2, .1], [.5, .1], False, "missing")
check("partial_preserves_forecast_but_nulls_main_error", partial["prediction_available"] is True
      and partial["saved_prediction_qv"] == [[.1, .2], [.3, .4]]
      and partial["signed_actual_minus_prediction_qv"] is None
      and partial["error_reason"] == "partial_interval_not_a_complete_20ms_prediction_endpoint")
complete = h.endpoint_error([[0., 0.], [0., 0.]], [.2, -.1], [.5, -.1], True, "missing")
check("signed_and_absolute_complete_errors", complete["signed_actual_minus_prediction_qv"] == [[.2, -.1], [.5, -.1]]
      and complete["absolute_error_qv"] == [[.2, .1], [.5, .1]])
effort = h.interval_effort({"executed_substeps": 2, "applied_torque_history": [[.5, -.25, 0., 0., 0., 0., 0., 0.]]*2}, .002)
missing = h.interval_effort({"executed_substeps": 2}, .002)
check("partial_effort_paid_and_missing_not_zero", effort["actual_absolute_nm_s_by_axis"] == [.002, .001]
      and effort["actual_squared_nm2_s_by_axis"] == [.001, .00025]
      and not effort["complete_20ms_interval"] and missing["actual_absolute_nm_s_by_axis"] is None)
tree = ast.parse(blob)
imports = {n.name for node in ast.walk(tree) if isinstance(node, ast.Import) for n in node.names}
from_imports = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]
forbidden_calls = {"predict", "fit", "update", "step", "select", "audit_archive", "audit"}
forbidden_keys = {"candidate_records", "qpos", "qvel", "root", "ground_contact", "coefficients", "covariance"}
literal_keys = {node.value for node in ast.walk(tree) if isinstance(node, ast.Constant) and isinstance(node.value, str)}
check("standard_library_and_saved_information_only", imports <= {"argparse", "gzip", "hashlib", "json", "math", "subprocess", "sys", "time"}
      and from_imports <= {"__future__", "pathlib"}
      and not any(isinstance(c.func, ast.Attribute) and c.func.attr in forbidden_calls for c in calls)
      and not (literal_keys & forbidden_keys))
check("draft_disabled_and_separate_source_pins", h.FORMAL_DIAGNOSTIC_ENABLED is False
      and h.G_COMMIT == "91dcf6c111a87427c8f3fdd8b959d4792b1bb5a2"
      and h.G_MANIFEST_SHA256 == "7eff4abb7cbe9c42a66d59615939a63a491c56fe87b5271d4ff4836d7b220a4c"
      and h.G_FIRST_AUDIT_SHA256 == "ad98a41ea342808521945fac998a864eff9709d1593fbb3c3c459ce2d48d60bc"
      and "expected_diagnostic_commit" in blob.decode() and "head+\":\"+name" in blob.decode())
result = {"checks": checks, "passed": sum(x["passed"] for x in checks), "failed": sum(not x["passed"] for x in checks),
          "source": {"sha256": hashlib.sha256(blob).hexdigest(), "bytes": len(blob)},
          "scope": "new H small branches and static isolation; no run(), actual G, model or physics",
          "actual_G_file_reads": 0, "model_calls": 0, "physics_calls": 0,
          "wall_seconds": time.perf_counter()-wall, "cpu_seconds": time.process_time()-cpu}
out = HERE / "CHECK_01.json"
with out.open("x", encoding="utf-8") as stream:
    json.dump(result, stream, indent=2)
print(json.dumps({"passed": result["passed"], "failed": result["failed"], "source_sha256": result["source"]["sha256"]}))
