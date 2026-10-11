"""Stdlib once-only descriptive C4 A summary of already first-audited evidence.

No simulator, collector, model, planner or auditor is imported or executed.
Source ZIP members are hashed from cached bytes, never imported or extracted.
Saved predictions, RLS records and first-auditor diagnostics are not replayed.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import gzip
import hashlib
import io
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import sys
import time
import zipfile

RAW_NAMES = ("metadata.json", "episodes.json", "seed_results.json",
             "trace.jsonl.gz", "source_snapshot.zip", "manifest.json")
KINDS = ("calibration", "prediction", "nominal_raw", "learned_raw",
         "nominal_guard", "learned_guard", "PDselected", "zero")
PHASES = ("prefix", "calibration", "prediction", "control")
BUDGET_KEYS = ("control_calls_attempted", "control_steps", "physics_steps")
MATH_KEYS = ("pair_prediction_attempts", "pair_prediction_successes", "scalar_prediction_attempts",
             "scalar_prediction_successes", "failed_pair_prediction_attempts", "unknown_scalar_failure_count")
JOINTS = ("left_shoulder", "left_elbow", "right_shoulder", "right_elbow",
          "left_hip", "left_knee", "right_hip", "right_knee")
PROTOCOL = "docs/GUARD_PAIR_DEVELOPMENT_PROTOCOL.md"
AUDITOR = "scripts/audit_guard_pair_development.py"
COLLECTOR = "src/developmental_physics/guard_pair_development.py"
SUPPORTS = ("scripts/audit_local_frozen.py", "scripts/audit_pair_frozen.py")
PD_DIR = "results/cpu_validation/2026-10-11_pair_pd/"
EXPECTED_AUDITOR_SHA256 = "393a2f3673bab952c34ea09a4d79d7d88e78c448e141a4ab83d865ab164dda93"
EXPECTED_SCOPE = {
    "suite": "guard_pair_development", "pose": "supine", "seeds": [0, 1, 2],
    "joint_indices": [0, 1], "split": "development", "protocol": PROTOCOL,
    "collector": COLLECTOR, "auditor": AUDITOR, "synthetic_fixture": False,
    "scientific_gates_frozen": True, "prefix_steps": 100,
    "calibration_steps": 400, "prediction_steps": 100, "control_steps": 200,
    "input_bases": {"nominal_raw": "raw_request", "nominal_guard": "known_angle_guard",
                    "learned_raw": "raw_request", "learned_guard": "known_angle_guard"},
    "pd_selection": PD_DIR + "selection.json", "calibration_pulse_zero": [1, 9],
    "prediction_velocity_ratio_max": .8, "contribution_tracking_mean_improvement_min": .2,
    "pd_tracking_mean_improvement_min": .05, "pd_actual_effort_ratio_max": 1.05,
}
REQUIRED_MEMBERS = {PROTOCOL, COLLECTOR, AUDITOR, *SUPPORTS,
    "src/developmental_physics/guard_pair_model.py",
    "src/developmental_physics/local_pair_model.py",
    "src/developmental_physics/pd_selection_binding.py",
    "src/developmental_physics/assets/ground_body.xml", "pyproject.toml",
    "docs/PAIR_PD_DEVELOPMENT_PROTOCOL.md",
    *(PD_DIR + name for name in ("selection.json", "manifest.json", "first_audit.json",
                               "raw/metadata.json", "raw/source_snapshot.zip"))}
BOUNDARY = (
    "Development-only two-joint evidence. First-audit integrity and physical scientific "
    "gates are separate. Truncated RMSE is descriptive and does not qualify a stopped "
    "trial or support control improvement. Public-rule differences are not RLS learning "
    "contributions. No independent-final generalization, adaptation, maturation, safety, "
    "whole-body motor skill or real-robot claim."
)


class EvidenceError(ValueError):
    """Failure to bind or parse original evidence, not physical trial failure."""


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def utc():
    return datetime.now(timezone.utc).isoformat()


def _pairs(items):
    result = {}
    for name, value in items:
        if name in result:
            raise EvidenceError("Duplicate JSON key: " + name)
        result[name] = value
    return result


def parse_json(data):
    def reject(value):
        raise EvidenceError("Nonfinite JSON constant: " + value)
    return json.loads(data, object_pairs_hook=_pairs, parse_constant=reject)


def strict_equal(first, second):
    if type(first) is not type(second):
        return False
    if isinstance(first, dict):
        return set(first) == set(second) and all(strict_equal(first[k], second[k]) for k in first)
    if isinstance(first, list):
        return len(first) == len(second) and all(strict_equal(a, b) for a, b in zip(first, second))
    return first == second


class Bindings:
    def __init__(self):
        self.checks = 0
        self.failed = 0
        self.violations = []

    def require(self, condition, description):
        self.checks += 1
        if not condition:
            self.failed += 1
            self.violations.append(description)
            raise EvidenceError(description)

    def equal(self, first, second, description):
        self.require(strict_equal(first, second), description)

    def record(self):
        return {"checks": self.checks, "failed": self.failed, "violations": self.violations,
                "scope": "Byte/source/declared-schema binding only; no new physics or numerical audit"}


class OnceReader:
    """Count attempts and successes even when a read fails; never reread input."""
    def __init__(self):
        self.records = {}

    def read(self, key, path):
        if key in self.records:
            raise EvidenceError("Second original-file read denied: " + key)
        entry = {"path": str(path.resolve()), "read_attempts": 1, "successful_reads": 0}
        self.records[key] = entry
        started = time.perf_counter()
        try:
            data = path.read_bytes()
            entry.update(successful_reads=1, byte_count=len(data), sha256=sha256(data))
            return data
        except BaseException as error:
            entry["error"] = {"type": type(error).__name__, "message": str(error)}
            raise
        finally:
            entry["wall_seconds"] = time.perf_counter() - started

    def record(self):
        entries = {name: self.records.get(name, {"read_attempts": 0, "successful_reads": 0})
                   for name in (*RAW_NAMES, "first_audit")}
        return {"schema_version": 1, "original_inputs": entries,
                "total_original_read_attempts": sum(r["read_attempts"] for r in entries.values()),
                "total_successful_original_reads": sum(r["successful_reads"] for r in entries.values()),
                "cache_semantics": "One filesystem read per original. Hash/JSON/gzip/ZIP use cached bytes.",
                "test_costs_included": False, "physical_calls": 0, "parameter_updates": 0,
                "new_body_predictions": 0, "auditor_executions": 0,
                "git_queries": 0, "pd_raw_filesystem_reads": 0}


def _valid_member(name):
    return (type(name) is str and bool(name) and "\\" not in name
            and not PurePosixPath(name).is_absolute() and not PureWindowsPath(name).drive
            and all(part not in ("", ".", "..") for part in name.split("/")))


def _valid_hash(value):
    return type(value) is str and re.fullmatch("[a-f0-9]{64}", value) is not None


def bind_evidence(raw, audit_bytes, checks):
    """Bind cached raw originals to the cached first audit without repeating its work."""
    checks.equal(set(raw), set(RAW_NAMES), "Exactly six cached original raw files required")
    metadata = parse_json(raw["metadata.json"])
    episodes = parse_json(raw["episodes.json"])
    seeds = parse_json(raw["seed_results.json"])
    manifest = parse_json(raw["manifest.json"])
    audit = parse_json(audit_bytes)
    hashes = {name: sha256(data) for name, data in raw.items()}
    checks.equal(set(manifest), set(RAW_NAMES) - {"manifest.json"}, "Manifest exact five-file coverage")
    for name, expected in manifest.items():
        checks.require(_valid_hash(expected), "Manifest SHA256 syntax: " + name)
        checks.equal(hashes[name], expected, "Manifest original-byte binding: " + name)
    checks.equal(audit.get("schema_version"), 1, "First-audit schema version")
    checks.equal(audit.get("immutable_scope"), EXPECTED_SCOPE, "Frozen production first-audit scope")
    archive = audit.get("archive")
    checks.require(isinstance(archive, dict), "First audit must contain completed archive reconstruction")
    checks.equal(archive.get("input_hashes"), hashes, "First-audit archive.input_hashes exact six-byte binding")
    checks.equal(audit.get("audit_script_sha256"), EXPECTED_AUDITOR_SHA256, "Frozen first-auditor SHA256 identity")
    checks.equal(metadata.get("source_status"), "", "Clean collection source status")
    checks.equal(metadata.get("source_dirty"), False, "Clean collection source flag")
    checks.require(type(metadata.get("source_commit")) is str and
                   re.fullmatch("[0-9a-f]{40}", metadata["source_commit"]) is not None,
                   "Full original source commit identity")
    for key, expected in {"suite": "guard_pair_development", "synthetic": False, "gpu": None,
                          "backend": "MuJoCo CPU", "seeds": [0, 1, 2], "pose": "supine",
                          "joint_indices": [0, 1], "split": "development", "native_joint_count": 8,
                          "model_input_bases": EXPECTED_SCOPE["input_bases"]}.items():
        checks.equal(metadata.get(key), expected, "Metadata fixed scope: " + key)
    checks.equal(metadata.get("source_snapshot_sha256"), hashes["source_snapshot.zip"], "Source ZIP original-byte binding")
    source_hashes = metadata.get("source_sha256")
    checks.require(isinstance(source_hashes, dict) and REQUIRED_MEMBERS.issubset(source_hashes), "Required archived source member coverage")
    member_hashes = {}
    with zipfile.ZipFile(io.BytesIO(raw["source_snapshot.zip"])) as source:
        names = source.namelist()
        checks.require(len(names) == len(set(names)), "No duplicate source ZIP names")
        checks.equal(set(names), set(source_hashes), "Source ZIP exact metadata member coverage")
        for name in names:
            checks.require(_valid_member(name) and _valid_hash(source_hashes[name]), "Safe source member and SHA256: " + name)
            member_hashes[name] = sha256(source.read(name))
            checks.equal(member_hashes[name], source_hashes[name], "Archived member-byte binding: " + name)
    checks.equal(member_hashes[AUDITOR], audit["audit_script_sha256"], "First audit matches archived auditor bytes")
    checks.equal(audit.get("audit_dependency_sha256"), {n: member_hashes[n] for n in SUPPORTS}, "First audit matches archived support bytes")
    checks.equal(metadata.get("independent_auditor"), {"path": AUDITOR, "sha256": member_hashes[AUDITOR],
                 "pending": False, "required_for_formal": True}, "Collector archived auditor declaration")
    checks.equal(metadata.get("protocol"), {"path": PROTOCOL, "sha256": member_hashes[PROTOCOL]}, "Protocol source binding")
    checks.equal(archive.get("episodes"), episodes, "First-audit episodes bound to original episode records")
    checks.equal(archive.get("native_joint_order"), list(JOINTS), "First-audit native joint order")
    checks.require(type(audit.get("checks")) is int and type(audit.get("failed")) is int
                   and 0 <= audit["failed"] <= audit["checks"], "Prior audit check counts")
    execution = audit.get("execution", {})
    for name in ("physical_simulation_calls", "model_parameter_updates"):
        checks.equal(execution.get(name), 0, "Existing audit zero extra interaction: " + name)
    checks.equal(execution.get("source_git_verification_enabled"), True, "Existing audit performed original-source Git verification")
    gates = audit.get("final_gates", {})
    checks.equal(gates.get("thresholds_frozen"), True, "Existing scientific thresholds frozen")
    checks.equal(gates.get("data_consistency_verified"), audit["failed"] == 0, "Existing integrity flag separate from scientific gates")
    for group in ("model_contribution", "selected_pd_comparison"):
        checks.equal(set(gates.get(group, {})), {"raw", "guard"}, "Both matching scientific bases: " + group)
        for basis, gate in gates[group].items():
            for flag in ("evaluated", "passed", "validated_pass"):
                checks.require(type(gate.get(flag)) is bool, "Explicit original gate flag: " + group + "/" + basis + "/" + flag)
            checks.require(not gate["passed"] or gate["evaluated"], "Passing original gate was evaluated")
            checks.equal(gate["validated_pass"], gate["passed"] and audit["failed"] == 0, "Original validated scientific flag binding")
    return metadata, episodes, seeds, audit, hashes, member_hashes


def _last_endpoint(row):
    if row is None:
        return None
    return {name: row.get(name) for name in ("step_index", "phase", "target_q", "requested_torque",
            "observation_before", "observation_after", "study_abort", "environment_terminated")}


def prediction_description(saved, derived):
    """Arithmetic descriptions of saved complete prediction metrics, no new gates."""
    result = {"completed": derived.get("completed", False),
              "eligible_from_first_audit": derived.get("eligible", False),
              "saved_complete_endpoint_counts": saved.get("metric_prediction_step_count"),
              "planned_active_calls": 100, "comparisons": {},
              "interpretation": "Saved independent prediction error comparison only; does not establish control contribution and adds no acceptance threshold"}
    for basis in ("raw", "guard"):
        nominal, learned = "nominal_" + basis, "learned_" + basis
        comparison = {}
        for quantity in ("velocity", "position"):
            values = saved.get(quantity + "_prediction_rmse", {})
            a, b = values.get(nominal), values.get(learned)
            available = (isinstance(a, dict) and isinstance(b, dict)
                         and isinstance(a.get("per_axis"), list) and len(a["per_axis"]) == 2
                         and isinstance(b.get("per_axis"), list) and len(b["per_axis"]) == 2)
            comparison[quantity] = {"nominal": a, "learned": b,
                "descriptive_axis_relative_error_reduction": [None if x == 0 else 1 - y / x
                    for x, y in zip(a["per_axis"], b["per_axis"])] if available else None,
                "descriptive_joint_relative_error_reduction": None if not available or a.get("joint") in (None, 0) else 1 - b["joint"] / a["joint"]}
        result["comparisons"][basis] = comparison
    return result


def cost_totals(records):
    counters = {key: sum(r.get(key, 0) for r in records) for key in MATH_KEYS}
    return {**counters, "accounting_records": len(records),
            "scalar_counts_complete": all(r.get("scalar_counts_complete") is True for r in records),
            "scalar_counts_is_lower_bound": any(r.get("scalar_counts_is_lower_bound") is True for r in records),
            "unknown_failed_planner_calls": sum(r.get("unknown_failed_planner_calls", 0) for r in records),
            "semantics": "Simple sum of original saved counters, not a replay"}


def summarize(raw, audit_bytes, checks):
    metadata, episodes, seeds, audit, hashes, members = bind_evidence(raw, audit_bytes, checks)
    raw_seed_map = {s["seed"]: s for s in seeds}
    audit_seed_map = {s["seed"]: s for s in audit["archive"]["seeds"]}
    checks.equal(set(raw_seed_map), {0, 1, 2}, "Three original seed rows")
    checks.equal(len(seeds), 3, "Original seed rows unique")
    checks.equal(set(audit_seed_map), {0, 1, 2}, "Three first-audit seed rows")
    checks.equal(len(audit["archive"]["seeds"]), 3, "First-audit seed rows unique")
    expected_order = [f"seed{seed}_{kind}" for seed in (0, 1, 2) for kind in KINDS]
    checks.equal([ep["trial_id"] for ep in episodes], expected_order, "Original fixed 24-trial order")
    grouped = {tid: {"regular_rows": 0, "exception_rows": 0, "phase_rows": Counter(),
                     "last_regular": None, "last_exception": None} for tid in expected_order}
    trace_count = 0
    for line in gzip.decompress(raw["trace.jsonl.gz"]).decode("utf-8").splitlines():
        if not line:
            continue
        row = parse_json(line)
        tid = row.get("trial_id")
        checks.require(tid in grouped, "Trace row belongs to planned trial")
        group = grouped[tid]
        is_exception = "collector_exception" in row
        group["exception_rows" if is_exception else "regular_rows"] += 1
        group["last_exception" if is_exception else "last_regular"] = row
        group["phase_rows"][row.get("phase", "unspecified")] += 1
        trace_count += 1
    trials = []
    costs = {"diagnostic_prediction_accounting": [], "planning_accounting": [],
             "calibration_rls_prediction_accounting": []}
    for ep in episodes:
        seed, kind, tid = ep["seed"], ep["kind"], ep["trial_id"]
        saved = raw_seed_map[seed]["evaluations"].get(kind, {})
        derived = audit_seed_map[seed]["evaluations"].get(kind, {})
        trace = grouped[tid]
        checks.equal(derived.get("stored_returned_endpoints", 0), trace["regular_rows"], "First-audit saved endpoint count: " + tid)
        maximum_active = 400 if kind == "calibration" else 100 if kind == "prediction" else 200
        trials.append({"trial_id": tid, "seed": seed, "kind": kind,
            "status": ep["status"], "completed": saved.get("completed", False),
            "eligible_from_first_audit": derived.get("eligible", False),
            "scientific_comparison_usable": derived.get("eligible", False) and saved.get("completed", False),
            "reason": ep.get("reason"), "collector_exception": ep.get("collector_exception"),
            "study_abort": ep.get("study_abort", saved.get("study_abort")),
            "environment_terminated": ep.get("environment_terminated"),
            "environment_stop_reason": ep.get("environment_stop_reason"),
            "planned_prefix_calls": 100, "planned_active_calls": maximum_active,
            "planned_total_calls": ep["maximum_control_steps"],
            "paid_budget": {k: ep[k] for k in BUDGET_KEYS}, "phase_budgets": ep.get("phase_budgets"),
            "endpoint_coverage": {"stored_returned_endpoints": trace["regular_rows"],
                "collector_confirmed_written_endpoints": derived.get("collector_confirmed_written_endpoints"),
                "collector_returned_endpoints": derived.get("collector_returned_endpoints"),
                "complete_score_endpoints": derived.get("complete_score_endpoints"),
                "partial_score_endpoints": derived.get("partial_score_endpoints"),
                "unreconstructed_physics_substeps": derived.get("unreconstructed_physics_substeps"),
                "trace_exception_rows": trace["exception_rows"], "trace_phase_rows": dict(trace["phase_rows"]),
                "returned_unwritten_steps": ep.get("returned_unwritten_steps"),
                "unreturned_physics_steps": ep.get("unreturned_physics_steps")},
            "tracking": {"joint_rmse_rad": derived.get("tracking_rmse_rad"),
                "per_axis_rmse_rad": derived.get("tracking_rmse_by_axis_rad"),
                "scoring_source": "Existing first audit, complete transitions only",
                "truncated_descriptive_only": not saved.get("completed", False)},
            "original_position_prediction_rmse": saved.get("position_prediction_rmse"),
            "original_velocity_prediction_rmse": saved.get("velocity_prediction_rmse"),
            "original_prediction_endpoint_counts": saved.get("metric_prediction_step_count"),
            "first_audit_diagnostics": derived,
            "phase_effort": saved.get("phase_effort"), "phase_effort_combined": saved.get("phase_effort_combined"),
            "actual_effort_complete": saved.get("actual_effort_complete"),
            "actual_effort_is_lower_bound": saved.get("actual_effort_is_lower_bound"),
            "phase_missing_actual_effort_substeps": saved.get("phase_missing_actual_effort_substeps"),
            "diagnostic_prediction_accounting": saved.get("diagnostic_prediction_accounting"),
            "planning_accounting": saved.get("planning_accounting"),
            "failed_planner_attempts": saved.get("failed_planner_attempts"),
            "planner_attempt_count": saved.get("planner_attempt_count"),
            "planner_decision_count": saved.get("planner_decision_count"),
            "planner_fallbacks": saved.get("planner_fallbacks"),
            "saturated_control_steps_per_axis": saved.get("saturated_control_steps_per_axis"),
            "controller_seconds_total": saved.get("controller_seconds_total"),
            "pd_seconds_total": saved.get("pd_seconds_total"),
            "last_saved_returned_endpoint": _last_endpoint(trace["last_regular"]),
            "saved_exception_record": trace["last_exception"]})
        for cost_name in ("diagnostic_prediction_accounting", "planning_accounting"):
            costs[cost_name].append({"trial_id": tid, "saved_accounting": saved.get(cost_name)})
    per_seed = []
    for seed in (0, 1, 2):
        sr, ar = raw_seed_map[seed], audit_seed_map[seed]
        costs["calibration_rls_prediction_accounting"].append({"seed": seed, "saved_accounting": sr.get("rls_prediction_accounting")})
        per_seed.append({"seed": seed, "reset_seed": sr.get("reset_seed"),
            "reference_q": sr.get("reference_q"), "direction": sr.get("direction"),
            "calibration_completed": sr.get("calibration_completed"),
            "calibration_scalar_updates": ar["calibration_scalar_updates"],
            "calibration_vector_updates": ar["calibration_vector_updates"],
            "independent_prediction": prediction_description(sr["evaluations"].get("prediction", {}), ar["evaluations"].get("prediction", {})),
            "independent_prediction_first_audit_diagnostics": ar["evaluations"].get("prediction"),
            "model_contribution": {b: next((r for r in audit["final_gates"]["model_contribution"][b]["per_seed"] if r["seed"] == seed), None) for b in ("raw", "guard")},
            "selected_pd_comparison": {b: next((r for r in audit["final_gates"]["selected_pd_comparison"][b]["per_seed"] if r["seed"] == seed), None) for b in ("raw", "guard")}})
    paid = {k: sum(ep[k] for ep in episodes) for k in BUDGET_KEYS}
    paid.update(model_updates=metadata["model_updates"], vector_model_updates=metadata["vector_model_updates"])
    checks.equal(paid, audit["archive"]["budget"], "Existing audit budget matches descriptive original episode sum")
    gate_flags = {group: {basis: {key: audit["final_gates"][group][basis][key]
                  for key in ("evaluated", "passed", "validated_pass")} for basis in ("raw", "guard")}
                  for group in ("model_contribution", "selected_pd_comparison")}
    math_totals = {name: cost_totals([entry["saved_accounting"] for entry in costs[name]
                  if isinstance(entry["saved_accounting"], dict)])
                  for name in ("diagnostic_prediction_accounting", "planning_accounting")}
    math_totals["calibration_rls_prediction_accounting"] = cost_totals([
        record for entry in costs["calibration_rls_prediction_accounting"]
        for record in (entry.get("saved_accounting") or {}).values() if isinstance(record, dict)])
    return {"schema_version": 1, "created_at_utc": utc(), "summary_status": "bound_descriptive_summary",
        "descriptive_binding_checks": checks.record(), "source_commit": metadata["source_commit"],
        "original_input_sha256": hashes, "existing_first_audit_sha256": sha256(audit_bytes),
        "archived_source_sha256": members, "protocol": metadata["protocol"],
        "dependencies": metadata.get("dependencies"), "backend": metadata["backend"], "gpu": metadata["gpu"],
        "pd_gains": metadata.get("pd_gains"), "pd_binding": metadata.get("pd_binding"),
        "native_joint_order": list(JOINTS), "scored_joint_indices": [0, 1],
        "existing_first_audit": {k: audit.get(k) for k in ("checks", "failed", "violations", "maximum_recomputation_difference", "execution", "immutable_scope")},
        "prior_audit_data_consistency_verified": audit["failed"] == 0,
        "scientific_gate_flags": gate_flags, "final_gates_from_first_audit": audit["final_gates"],
        "scientific_gates_recomputed": False, "control_ranking_computed": False,
        "statuses": dict(Counter(ep["status"] for ep in episodes)), "trace_rows": trace_count,
        "paid_budget": paid, "planned_budget": {k: metadata.get(k) for k in (
            "planned_episode_count", "maximum_control_steps", "maximum_physics_steps", "maximum_scalar_updates", "maximum_vector_updates",
            "maximum_independent_prediction_pair_calls", "maximum_mpc_prediction_pair_calls")},
        "phase_total_paid_budget": {phase: {key: sum(ep.get("phase_budgets", {}).get(phase, {}).get(key, 0) for ep in episodes) for key in BUDGET_KEYS} for phase in PHASES},
        "cost_ledgers": costs, "cost_totals": math_totals,
        "cost_semantics": "Copied saved counters, not new predictions/replays; incomplete and lower-bound flags retained per trial",
        "per_seed": per_seed, "trials": trials,
        "collector_timing": {"wall_seconds": metadata.get("wall_seconds"), "cpu_seconds": metadata.get("cpu_seconds")},
        "summary_new_computation_cost": {"physics_calls": 0, "model_updates": 0, "body_predictions": 0,
             "mpc_candidate_predictions": 0, "audit_executions": 0, "git_queries": 0},
        "claim_boundary": BOUNDARY}


def save(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def execute(input_dir, audit_path, output_dir):
    wall, cpu = time.perf_counter(), time.process_time()
    input_dir, audit_path, output_dir = Path(input_dir), Path(audit_path), Path(output_dir)
    output_dir.mkdir(parents=False, exist_ok=False)
    own = Path(__file__).read_bytes()
    (output_dir / "tool_source.py").write_bytes(own)
    record = {"schema_version": 1, "started_at_utc": utc(), "tool_source_sha256": sha256(own),
        "source_snapshot": "tool_source.py", "python": sys.version,
        "expected_first_auditor_sha256": EXPECTED_AUDITOR_SHA256,
        "input_directory": str(input_dir.resolve()), "first_audit_path": str(audit_path.resolve()),
        "output_directory": str(output_dir.resolve()), "tests_included": False,
        "physical_calls": 0, "model_parameter_updates": 0, "new_body_predictions": 0,
        "audit_executions": 0, "git_queries": 0}
    save(output_dir / "attempt.json", record)
    checks, reader = Bindings(), OnceReader()
    result, code = None, 1
    try:
        checks.equal({p.name for p in input_dir.iterdir() if p.is_file()}, set(RAW_NAMES), "Original raw directory exact file coverage")
        raw = {name: reader.read(name, input_dir / name) for name in RAW_NAMES}
        audit_bytes = reader.read("first_audit", audit_path)
        result = summarize(raw, audit_bytes, checks)
        code = 0
    except BaseException as error:
        record["exception"] = {"type": type(error).__name__, "message": str(error)}
        result = {"schema_version": 1, "created_at_utc": utc(), "summary_status": "binding_or_parse_failed",
                  "descriptive_binding_checks": checks.record(), "exception": record["exception"],
                  "scientific_interpretation_available": False, "claim_boundary": BOUNDARY}
    finally:
        save(output_dir / "summary.json", result)
        save(output_dir / "read_cost.json", reader.record())
        source_after = Path(__file__).read_bytes()
        record["tool_source_after_sha256"] = sha256(source_after)
        record["tool_source_unchanged"] = source_after == own
        if not record["tool_source_unchanged"]:
            code = 1
        record.update(finished_at_utc=utc(), wall_seconds=time.perf_counter() - wall,
                      cpu_seconds=time.process_time() - cpu, exit_code=code,
                      descriptive_binding_checks=checks.record(),
                      output_sha256={p.name: sha256(p.read_bytes()) for p in sorted(output_dir.iterdir()) if p.is_file()})
        save(output_dir / "execution.json", record)
    return code, result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    code, result = execute(args.input, args.audit, args.output)
    print(json.dumps({"summary_status": result["summary_status"], "exit_code": code,
                      "binding_checks": result["descriptive_binding_checks"],
                      "scientific_gate_flags": result.get("scientific_gate_flags"),
                      "paid_budget": result.get("paid_budget")}, ensure_ascii=False))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
