"""H: describe only the five pinned G saved inputs; no model or physics calls."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import time

FORMAL_DIAGNOSTIC_ENABLED = True
G_COMMIT = "91dcf6c111a87427c8f3fdd8b959d4792b1bb5a2"
G_MANIFEST_SHA256 = "7eff4abb7cbe9c42a66d59615939a63a491c56fe87b5271d4ff4836d7b220a4c"
G_FIRST_AUDIT_SHA256 = "ad98a41ea342808521945fac998a864eff9709d1593fbb3c3c459ce2d48d60bc"
SCRIPT = "scripts/diagnose_guard_pd_tail_forecast_stop.py"
PROTOCOL = "docs/GUARD_PD_TAIL_FORECAST_STOP_DIAGNOSTIC_PROTOCOL.md"
PUBLIC = "results/cpu_validation/2026-10-11_guard_pd_tail_control"
KINDS = ("cold11", "learned_sparse11")
TRIALS = tuple((seed, kind) for seed in (0, 1, 2) for kind in KINDS)
Q_STOP, V_STOP, HORIZON, SUBSTEPS = .12, 1., 15, 10


def sha(blob):
    return hashlib.sha256(blob).hexdigest()


def parse(blob):
    def invalid(value):
        raise ValueError("nonfinite JSON constant: " + value)
    return json.loads(blob, parse_constant=invalid)


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def pair(value):
    return isinstance(value, (list, tuple)) and len(value) == 2 and all(finite(x) for x in value)


def trajectory(value):
    return isinstance(value, list) and len(value) == HORIZON and all(pair(x) for x in value)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def forecast(decision, qref):
    """Only selected saved trajectories; never inspect candidate_records."""
    if not isinstance(decision, dict):
        return {"category": "missing_decision", "segments": None}
    if decision.get("fallback") is True:
        return {"category": "fallback", "segments": None}
    if (decision.get("fallback") is not False
            or type(decision.get("feasible_candidates")) is not int
            or decision["feasible_candidates"] <= 0):
        return {"category": "invalid_decision", "segments": None}
    qs, vs, us = (decision.get(key) for key in
                  ("predicted_q", "predicted_v", "trajectory_requested_torque"))
    if not all(trajectory(x) for x in (qs, vs, us)):
        return {"category": "missing_or_invalid_selected_h15", "segments": None}
    segments = {}
    for name, stages in (("stage0", range(1)), ("tail", range(1, HORIZON))):
        axes = []
        for axis in (0, 1):
            qbad = [h for h in stages if abs(qs[h][axis]-qref[axis]) >= Q_STOP]
            vbad = [h for h in stages if abs(vs[h][axis]) >= V_STOP]
            bad = sorted(set(qbad) | set(vbad))
            axes.append({"q_violation_stages": qbad, "v_violation_stages": vbad,
                         "either_violation_stages": bad,
                         "first_violation_stage": bad[0] if bad else None,
                         "max_abs_q_minus_qref_rad": max(abs(qs[h][axis]-qref[axis]) for h in stages),
                         "max_abs_v_rad_s": max(abs(vs[h][axis]) for h in stages)})
        segments[name] = axes
    return {"category": "valid_selected_h15", "segments": segments}


def endpoint_error(prediction, actual_q, actual_v, complete, missing_reason):
    valid = isinstance(prediction, (list, tuple)) and len(prediction) == 2 and all(pair(x) for x in prediction)
    result = {"saved_prediction_qv": prediction, "prediction_available": valid,
              "error_reason": None, "signed_actual_minus_prediction_qv": None,
              "absolute_error_qv": None}
    if not valid:
        result["error_reason"] = missing_reason
    elif not complete:
        result["error_reason"] = "partial_interval_not_a_complete_20ms_prediction_endpoint"
    else:
        errors = [[actual_q[i]-prediction[0][i] for i in (0, 1)],
                  [actual_v[i]-prediction[1][i] for i in (0, 1)]]
        result["signed_actual_minus_prediction_qv"] = errors
        result["absolute_error_qv"] = [[abs(x) for x in row] for row in errors]
    return result


def interval_effort(diagnostics, dt):
    count = diagnostics.get("executed_substeps")
    require(type(count) is int and 0 <= count <= SUBSTEPS, "invalid executed_substeps")
    history = diagnostics.get("applied_torque_history")
    valid = (isinstance(history, list) and len(history) == count
             and all(isinstance(row, list) and len(row) == 8 and all(finite(x) for x in row) for row in history))
    result = {"executed_substeps": count, "complete_20ms_interval": count == SUBSTEPS,
              "effort_known_substeps": count if valid else None,
              "actual_absolute_nm_s_by_axis": None, "actual_squared_nm2_s_by_axis": None,
              "effort_reason": None if valid else "missing_or_invalid_actual_torque_history"}
    if valid:
        result["actual_absolute_nm_s_by_axis"] = [sum(abs(row[i]) for row in history)*dt for i in (0, 1)]
        result["actual_squared_nm2_s_by_axis"] = [sum(row[i]**2 for row in history)*dt for i in (0, 1)]
    return result


def empty_group(seed, kind, segment):
    axes = [{"stage_comparison_count": 0, "q_violating_stage_count": 0,
             "v_violating_stage_count": 0, "either_violating_stage_count": 0,
             "decisions_with_q_violation": 0, "decisions_with_v_violation": 0,
             "decisions_with_either_violation": 0, "first_violation_stage": None,
             "max_abs_q_minus_qref_rad": None, "max_abs_v_rad_s": None} for _ in (0, 1)]
    return {"seed": seed, "kind": kind, "target_segment": segment, "saved_active_count": 0,
            "category_counts": {}, "empty_target_segment": True,
            "stage0": [dict(x) for x in axes], "tail": [dict(x) for x in axes]}


def add_group(group, detail):
    group["saved_active_count"] += 1
    group["empty_target_segment"] = False
    category = detail["category"]
    group["category_counts"][category] = group["category_counts"].get(category, 0)+1
    if category != "valid_selected_h15":
        return
    for segment in ("stage0", "tail"):
        for axis in (0, 1):
            saved, out = detail["segments"][segment][axis], group[segment][axis]
            out["stage_comparison_count"] += 1 if segment == "stage0" else 14
            for field, prefix in (("q_violation_stages", "q"), ("v_violation_stages", "v"), ("either_violation_stages", "either")):
                out[prefix+"_violating_stage_count"] += len(saved[field])
                out["decisions_with_"+prefix+"_violation"] += int(bool(saved[field]))
            first = saved["first_violation_stage"]
            if first is not None:
                out["first_violation_stage"] = first if out["first_violation_stage"] is None else min(first, out["first_violation_stage"])
            for field in ("max_abs_q_minus_qref_rad", "max_abs_v_rad_s"):
                out[field] = saved[field] if out[field] is None else max(out[field], saved[field])


def write_json(path, document):
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2, allow_nan=False)+"\n", encoding="utf-8")


def run(args):
    require(FORMAL_DIAGNOSTIC_ENABLED, "draft H execution disabled: freeze and promote before first diagnostic")
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    wall, cpu = time.perf_counter(), time.process_time()
    cost = {"G_input_file_reads": 0, "G_input_raw_bytes": 0, "sha256_input_bytes": 0,
            "G_json_documents_parsed": 0, "trace_lines_parsed": 0, "trace_uncompressed_bytes": 0,
            "selected_active_records_described": 0, "own_source_file_reads": 0,
            "own_source_raw_bytes": 0, "git_queries": 0, "git_return_bytes": 0,
            "model_predictions": 0, "model_updates": 0, "physics_calls": 0}
    identity, inputs = {}, {}
    outcome = {"status": "started", "scientific_adoption": False, "cost": cost,
               "G_physics_source_commit": G_COMMIT, "diagnostic_source": identity, "inputs": inputs}

    def git(*arguments):
        cost["git_queries"] += 1
        result = subprocess.run(["git", *arguments], cwd=args.git_root, capture_output=True, check=False)
        cost["git_return_bytes"] += len(result.stdout)+len(result.stderr)
        require(result.returncode == 0, "H provenance git command failed")
        return result.stdout

    def read(path, name, expected=None):
        blob = Path(path).read_bytes()
        cost["G_input_file_reads"] += 1
        cost["G_input_raw_bytes"] += len(blob)
        cost["sha256_input_bytes"] += len(blob)
        inputs[name] = {"path": str(path), "bytes": len(blob), "sha256": sha(blob)}
        if expected is not None:
            require(inputs[name]["sha256"] == expected, "pinned source SHA256 mismatch: "+name)
        return blob

    def document(blob):
        cost["G_json_documents_parsed"] += 1
        return parse(blob)

    try:
        head = git("rev-parse", "HEAD").decode().strip()
        identity["commit"] = head
        require(head == args.expected_diagnostic_commit, "H frozen HEAD differs from requested commit")
        require(git("status", "--porcelain") == b"", "H source checkout is dirty")
        for name, path in ((SCRIPT, Path(__file__)), (PROTOCOL, Path(args.git_root)/PROTOCOL)):
            blob = path.read_bytes()
            cost["own_source_file_reads"] += 1
            cost["own_source_raw_bytes"] += len(blob)
            identity[name] = {"bytes": len(blob), "sha256": sha(blob)}
            require(git("show", head+":"+name) == blob, "H source differs from clean committed bytes: "+name)
        identity["clean_committed_bytes_verified"] = True
        raw = Path(args.raw)
        manifest = document(read(raw/"manifest.json", "manifest.json", G_MANIFEST_SHA256))
        audit = document(read(args.first_audit, "first_audit.json", G_FIRST_AUDIT_SHA256))
        require(audit.get("failed") == 0 and audit.get("data_consistency_verified") is True, "G first audit not verified")
        require(audit["archive"]["source_commit"] == G_COMMIT, "G first audit source differs")
        blobs = {}
        for name in ("metadata.json", "seed_results.json", "trace.jsonl.gz"):
            record = manifest["files"][name]
            blobs[name] = read(raw/name, name, record["sha256"])
            require(len(blobs[name]) == record["bytes"], "G manifest byte count mismatch: "+name)
        for name in ("manifest.json", "metadata.json", "seed_results.json", "trace.jsonl.gz"):
            require(audit["input_file_sha256"][name] == inputs[name]["sha256"], "G first audit input binding mismatch: "+name)
            require(audit["archive"]["input_hashes"][name] == inputs[name]["sha256"], "G first audit archive binding mismatch: "+name)
        metadata, seeds = (document(blobs[name]) for name in ("metadata.json", "seed_results.json"))
        require(metadata["suite"] == "pd_tail_control_development" and metadata["source_commit"] == G_COMMIT
                and metadata["source_dirty"] is False, "wrong G suite/source")
        require(metadata["exception_trials"] == 0 and metadata["blocked_trials"] == 0, "H fixed G scope requires no exception/blocked trials")
        require(all(metadata[key] == 0 for key in ("model_updates", "policy_parameter_updates", "gain_updates", "gate_updates")), "G unexpected update")
        spec = metadata["study_abort_spec"]
        require(spec["absolute_q_minus_qref_rad"] == Q_STOP and spec["absolute_velocity_rad_s"] == V_STOP and spec["comparison"] == ">=", "G stop spec mismatch")
        dt = metadata["environment_config"]["physics_dt"]
        require(dt == .002, "H expects original G 2ms substep")
        seed_map = {item["seed"]: item for item in seeds}
        require(len(seeds) == 3 and set(seed_map) == {0, 1, 2}, "G seed binding mismatch")
        rows = {f"seed{seed}_{kind}": [] for seed, kind in TRIALS}
        groups = {(seed, kind, segment): empty_group(seed, kind, segment) for seed, kind in TRIALS for segment in ("A", "B")}
        with (output/"intervals.jsonl").open("x", encoding="utf-8") as intervals:
            expanded = gzip.decompress(blobs["trace.jsonl.gz"])
            cost["trace_uncompressed_bytes"] = len(expanded)
            for line in expanded.splitlines():
                cost["trace_lines_parsed"] += 1
                row = parse(line)
                require("collector_exception" not in row, "unexpected exception notice in pinned zero-exception G")
                if row.get("phase") != "control" or row.get("kind") not in KINDS:
                    continue
                seed, kind, tid = row["seed"], row["kind"], row["trial_id"]
                require(tid == f"seed{seed}_{kind}" and tid in rows, "unexpected selected trial identity")
                active = row["step_index"]-100
                require(type(row["step_index"]) is int and active == len(rows[tid]) and active < 200, "noncontiguous saved active records")
                qref = seed_map[seed]["fresh_prefix_bindings"][kind]["reference_q"]
                require(pair(qref), "invalid native qref")
                detail = forecast(row.get("planner_decision"), qref)
                segment = "A" if active < 100 else "B"
                saved = {"trial_id": tid, "active_index": active, "step_index": row["step_index"],
                         "target_segment": segment, "reference_q": qref, **detail}
                intervals.write(json.dumps(saved, allow_nan=False)+"\n")
                add_group(groups[seed, kind, segment], detail)
                rows[tid].append((row, detail))
                cost["selected_active_records_described"] += 1
        trial_descriptions = []
        with (output/"last20.jsonl").open("x", encoding="utf-8") as last20:
            for seed, kind in TRIALS:
                tid = f"seed{seed}_{kind}"
                saved = rows[tid]
                evaluation = seed_map[seed]["evaluations"][kind]
                full_count = sum(row["diagnostics"]["executed_substeps"] == SUBSTEPS for row, _ in saved)
                require(full_count == evaluation["metric_control_step_count"], "complete saved interval count differs from original G metric count")
                require(evaluation["status"] in ("completed", "terminated"), "unexpected fixed G trial status")
                trial_descriptions.append({"trial_id": tid, "status": evaluation["status"], "completed": evaluation["completed"],
                    "study_abort": evaluation.get("study_abort"), "saved_active_count": len(saved),
                    "last20_count": min(20, len(saved)), "last20_empty_reason": "no_saved_active_records" if not saved else None,
                    "partial_trial_not_ranked": evaluation["status"] != "completed"})
                for row, detail in saved[-20:]:
                    after = row["observation_after"]
                    aq, av = after["joint_position"][:2], after["joint_velocity"][:2]
                    require(pair(aq) and pair(av), "invalid native actual endpoint")
                    effort = interval_effort(row["diagnostics"], dt)
                    selected = None
                    if detail["category"] == "valid_selected_h15":
                        decision = row["planner_decision"]
                        selected = [decision["predicted_q"][0], decision["predicted_v"][0]]
                    independent = row["predicted_next_qv"].get(kind)
                    record = {"trial_id": tid, "step_index": row["step_index"], "active_index": row["step_index"]-100,
                        "actual_next_qv": [aq, av], "requested_torque_nm": row["requested_torque"][:2],
                        "interval_effort": effort, "forecast_category": detail["category"],
                        "independent_current_request_prediction": endpoint_error(independent, aq, av, effort["complete_20ms_interval"], "missing_or_invalid_independent_prediction"),
                        "selected_stage0_prediction": endpoint_error(selected, aq, av, effort["complete_20ms_interval"], "no_valid_selected_h15_trajectory")}
                    last20.write(json.dumps(record, allow_nan=False)+"\n")
        write_json(output/"description.json", {"schema_version": 1, "diagnostic": "H_saved_forecast_stop",
            "scientific_adoption": False, "thresholds": {"q_rad": Q_STOP, "v_rad_s": V_STOP, "comparison": ">="},
            "window": "last min(20,actual saved active count) per fixed trial; no ranking partial trials",
            "groups": list(groups.values()), "trials": trial_descriptions,
            "original_G_final_gates": audit["final_gates"], "original_G_budget": audit["archive"]["budget"]})
        outcome["status"] = "completed"
    except BaseException as exc:
        outcome["status"] = "failed"
        outcome["error"] = {"type": type(exc).__name__, "message": str(exc)}
    finally:
        cost["wall_seconds"] = time.perf_counter()-wall
        cost["cpu_seconds"] = time.process_time()-cpu
        write_json(output/"run.json", outcome)
        records = {p.name: {"bytes": p.stat().st_size, "sha256": sha(p.read_bytes())}
                   for p in output.iterdir() if p.is_file() and p.name != "manifest.json"}
        write_json(output/"manifest.json", {"schema_version": 1, "status": outcome["status"],
                   "scientific_adoption": False, "files": records})
    return 0 if outcome["status"] == "completed" else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", default=PUBLIC+"/raw")
    parser.add_argument("--first-audit", default=PUBLIC+"/first_audit.json")
    parser.add_argument("--git-root", default=".")
    parser.add_argument("--expected-diagnostic-commit", required=True)
    parser.add_argument("--output", required=True)
    return run(parser.parse_args())


if __name__ == "__main__":
    sys.exit(main())
