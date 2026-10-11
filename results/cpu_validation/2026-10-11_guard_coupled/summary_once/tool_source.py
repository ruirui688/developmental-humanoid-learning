"""Thin stdlib C4 B descriptive summary; no model, fit, prediction or audit run."""
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

RAW = ("metadata.json", "episodes.json", "seed_results.json", "source_snapshot.zip", "manifest.json",
       "calibration_replay.jsonl.gz", "prediction_replay.jsonl.gz", "trace.jsonl.gz")
ROWS = RAW[5:]
GATES = ("coupled_contribution", "diagonal_increment", "selected_pd_comparison")
KEYS = ("control_calls_attempted", "control_steps", "physics_steps")
AUDITOR = "scripts/audit_guard_coupled_development.py"
PROTOCOL = "docs/GUARD_COUPLED_DEVELOPMENT_PROTOCOL.md"
COLLECTOR = "src/developmental_physics/guard_coupled_development.py"
SUPPORT = ("scripts/audit_local_frozen.py", "scripts/audit_pair_frozen.py", "scripts/audit_guard_pair_development.py")
A_ROOT = "results/cpu_validation/2026-10-11_guard_pair/"
A_RAW = ("metadata.json", "episodes.json", "seed_results.json", "trace.jsonl.gz", "source_snapshot.zip", "manifest.json")
A_MEMBERS = {A_ROOT + "manifest.json", A_ROOT + "first_audit.json", *(A_ROOT + "raw/" + n for n in A_RAW)}
REQUIRED = {AUDITOR, PROTOCOL, COLLECTOR, *SUPPORT, *A_MEMBERS,
            "src/developmental_physics/guard_coupled_pair_model.py", "src/developmental_physics/guard_pair_source_binding.py"}
SCOPE = {"suite": "guard_coupled_development", "pose": "supine", "seeds": [0, 1, 2], "joint_indices": [0, 1],
    "split": "development", "collector": COLLECTOR, "auditor": AUDITOR, "protocol": PROTOCOL,
    "synthetic_fixture": False, "scientific_gates_frozen": True, "prefix_steps": 100,
    "calibration_reuse_steps": 400, "prediction_reuse_steps": 100, "control_steps": 200,
    "structure": "coupled_hinge9", "input_basis": "known_angle_guard", "parameters_per_output": 9,
    "diagonal_parameters_per_output": 5, "prediction_velocity_ratio_max": .8,
    "own_tracking_mean_improvement_min": .2, "comparison_joint_mean_improvement_min": .05,
    "actual_effort_ratio_max": 1.05, "A_scientific_contribution_run_dependency": False}
BOUNDARY = ("Development reuse of previously paid A calibration/prediction and baselines. Offline coupled RLS is new "
    "computation, not new physical interaction or holdout. Truncated controls are descriptive only, never ranked. "
    "Integrity checks are separate from the three original scientific gates. No adaptation, skill, safety or final-generalization claim.")

def sha(blob): return hashlib.sha256(blob).hexdigest()
def utc(): return datetime.now(timezone.utc).isoformat()
def valid_hash(value): return type(value) is str and re.fullmatch("[0-9a-f]{64}", value) is not None
def equal(a, b):
    if type(a) is not type(b): return False
    if isinstance(a, dict): return set(a) == set(b) and all(equal(a[k], b[k]) for k in a)
    if isinstance(a, list): return len(a) == len(b) and all(equal(x, y) for x, y in zip(a, b))
    return a == b
def parse(blob):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result: raise ValueError("Duplicate JSON key: " + key)
            result[key] = value
        return result
    def constant(value): raise ValueError("Nonfinite JSON constant: " + value)
    return json.loads(blob, object_pairs_hook=pairs, parse_constant=constant)
def safe(name):
    return (type(name) is str and bool(name) and "\\" not in name and not PurePosixPath(name).is_absolute()
        and not PureWindowsPath(name).drive and all(p not in ("", ".", "..") for p in name.split("/")))
def save(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as out:
        json.dump(value, out, ensure_ascii=False, indent=2, allow_nan=False); out.write("\n")

class Checks:
    def __init__(self): self.count = 0; self.failed = 0; self.violations = []
    def require(self, condition, label):
        self.count += 1
        if not condition:
            self.failed += 1; self.violations.append(label); raise ValueError(label)
    def same(self, a, b, label): self.require(equal(a, b), label)
    def record(self): return {"checks": self.count, "failed": self.failed, "violations": self.violations,
        "scope": "Byte/source/schema bindings and saved-counter sums only; no numerical replay"}

class Reader:
    def __init__(self): self.records = {}
    def read(self, key, path):
        if key in self.records: raise ValueError("Second original read denied: " + key)
        entry = {"path": str(path.resolve()), "read_attempts": 1, "successful_reads": 0}; self.records[key] = entry
        began = time.perf_counter()
        try:
            blob = path.read_bytes(); entry.update(successful_reads=1, bytes=len(blob), sha256=sha(blob)); return blob
        except BaseException as error:
            entry["error"] = {"type": type(error).__name__, "message": str(error)}; raise
        finally: entry["wall_seconds"] = time.perf_counter() - began
    def record(self):
        return {"original_inputs": {n: self.records.get(n, {"read_attempts": 0, "successful_reads": 0}) for n in (*RAW, "first_audit")},
            "total_original_read_attempts": sum(r["read_attempts"] for r in self.records.values()),
            "physical_calls": 0, "model_updates": 0, "body_predictions": 0, "audit_executions": 0,
            "git_queries": 0, "A_or_PD_original_filesystem_reads": 0, "tests_included": False,
            "cache_semantics": "Each eight B raw files and first audit read once; embedded A bytes only from cached B ZIP"}

def zip_members(blob, expected, checks, label):
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        names = archive.namelist()
        checks.require(len(names) == len(set(names)), label + " unique names")
        checks.same(set(names), set(expected), label + " exact members")
        result = {}
        for name in names:
            checks.require(safe(name) and valid_hash(expected[name]), label + " safe member/hash " + name)
            result[name] = archive.read(name)
            checks.same(sha(result[name]), expected[name], label + " member bytes " + name)
        return result

def bind_a(members, metadata, archive, checks):
    """Embedded original identities only; do not parse A raw trace or perform A audit."""
    binding = metadata["a_binding"]
    checks.same(binding, archive["A_original_binding"], "Existing B audit A binding")
    checks.require(A_MEMBERS.issubset(members), "Embedded eight A identity members")
    hashes = {n: sha(members[A_ROOT + "raw/" + n]) for n in A_RAW}
    checks.same(binding["archive_root"], A_ROOT, "Fixed A archive root")
    for short, field in (("manifest.json", "manifest"), ("first_audit.json", "audit")):
        checks.same(binding[field], {"path": A_ROOT + short, "sha256": sha(members[A_ROOT + short])}, "Embedded A " + short + " identity")
    checks.same(binding["raw_hashes"], hashes, "Embedded A original six hashes")
    outer = parse(members[A_ROOT + "manifest.json"])["files"]
    checks.same({n[4:] for n in outer if n.startswith("raw/")}, set(A_RAW), "A outer manifest raw coverage")
    for name in (*("raw/" + n for n in A_RAW), "first_audit.json"):
        blob = members[A_ROOT + name]; record = outer[name]
        checks.same(record["sha256"], sha(blob), "A outer manifest digest " + name)
        checks.same(record["bytes"], len(blob), "A outer manifest bytes " + name)
    checks.same(parse(members[A_ROOT + "raw/manifest.json"]), {n: h for n, h in hashes.items() if n != "manifest.json"}, "A inner raw manifest")
    first = parse(members[A_ROOT + "first_audit.json"])
    checks.same(first["archive"]["input_hashes"], hashes, "Embedded A first-audit exact input hashes")
    checks.same(first["failed"], 0, "A original integrity succeeded")
    checks.same(first["final_gates"]["data_consistency_verified"], True, "A original integrity flag")
    checks.same(first["execution"]["source_git_verification_enabled"], True, "A original source Git verification")
    am = parse(members[A_ROOT + "raw/metadata.json"])
    for key, expected in {"suite": "guard_pair_development", "synthetic": False, "source_status": "", "source_dirty": False,
                          "seeds": [0, 1, 2], "pose": "supine", "joint_indices": [0, 1], "split": "development"}.items():
        checks.same(am.get(key), expected, "Embedded A fixed identity " + key)
    checks.same(binding["source_commit"], am["source_commit"], "A commit identity")
    checks.require(type(am["source_commit"]) is str and re.fullmatch("[0-9a-f]{40}", am["source_commit"]) is not None, "A full source commit")
    checks.same(binding["source_sha256"], am["source_sha256"], "A source hash map identity")
    a_protocol = "docs/GUARD_PAIR_DEVELOPMENT_PROTOCOL.md"
    checks.same(am["protocol"], {"path": a_protocol, "sha256": am["source_sha256"][a_protocol]}, "A original protocol identity")
    checks.same(am["independent_auditor"], {"path": SUPPORT[2], "sha256": am["source_sha256"][SUPPORT[2]],
        "pending": False, "required_for_formal": True}, "A original executing auditor declaration")
    checks.same(binding["runtime"], {k: metadata[k] for k in ("environment_config", "dependencies", "mujoco_version")}, "A/B bound runtime identity")
    for key, value in binding["runtime"].items(): checks.same(am.get(key), value, "A original runtime " + key)
    checks.same(am["source_snapshot_sha256"], hashes["source_snapshot.zip"], "A source ZIP original identity")
    inner = zip_members(members[A_ROOT + "raw/source_snapshot.zip"], am["source_sha256"], checks, "A source ZIP")
    for name, blob in inner.items(): checks.same(members.get(name), blob, "A/B shared original source bytes " + name)
    checks.same(first["audit_script_sha256"], am["source_sha256"][SUPPORT[2]], "A first-auditor source identity")
    checks.same(first["audit_dependency_sha256"], {n: am["source_sha256"][n] for n in SUPPORT[:2]}, "A first-auditor support identity")
    checks.same(binding["A_paid_budget"], first["archive"]["budget"], "Previously paid A budget")
    checks.same(archive["A_paid_budget"], binding["A_paid_budget"], "B first-audit previous A budget")
    for key in ("new_physical_calls", "new_model_updates"):
        checks.same(binding[key], 0, "A identity binding zero new work " + key)
    return binding

def summarize(raw, audit_blob, expected_sha, checks):
    checks.require(valid_hash(expected_sha), "Root explicit expected auditor SHA256 required")
    metadata, episodes, seeds = (parse(raw[n]) for n in RAW[:3])
    manifest, audit = parse(raw["manifest.json"]), parse(audit_blob)
    hashes = {n: sha(blob) for n, blob in raw.items()}
    checks.same(set(raw), set(RAW), "Eight B raw files")
    checks.same(manifest, {n: h for n, h in hashes.items() if n != "manifest.json"}, "B manifest exact seven hashes")
    checks.same(audit["schema_version"], 1, "B first-audit schema")
    checks.require(type(audit.get("checks")) is int and type(audit.get("failed")) is int
                   and 0 <= audit["failed"] <= audit["checks"], "B prior audit check counts")
    checks.same(audit["immutable_scope"], SCOPE, "B frozen production scope")
    checks.same(audit["audit_script_sha256"], expected_sha, "Root frozen auditor SHA")
    archive = audit["archive"]
    checks.require(isinstance(archive, dict), "First audit has reconstructed archive")
    checks.same(archive["input_hashes"], hashes, "First audit exact eight raw hashes")
    checks.same(archive["episodes"], episodes, "First audit original episode binding")
    checks.same(metadata["source_snapshot_sha256"], hashes["source_snapshot.zip"], "B source ZIP identity")
    checks.require(REQUIRED.issubset(metadata["source_sha256"]), "Required B/A original source coverage")
    members = zip_members(raw["source_snapshot.zip"], metadata["source_sha256"], checks, "B source ZIP")
    checks.same(sha(members[AUDITOR]), expected_sha, "Root frozen source auditor bytes")
    checks.same(audit["audit_dependency_sha256"], {n: sha(members[n]) for n in SUPPORT}, "B audit support source bytes")
    checks.same(metadata["independent_auditor"], {"path": AUDITOR, "sha256": expected_sha, "pending": False, "required_for_formal": True}, "B frozen auditor declaration")
    checks.same(metadata["protocol"], {"path": PROTOCOL, "sha256": sha(members[PROTOCOL])}, "B protocol original bytes")
    for key, expected in {"suite": "guard_coupled_development", "synthetic": False, "source_status": "", "source_dirty": False,
        "seeds": [0, 1, 2], "pose": "supine", "joint_indices": [0, 1], "split": "development", "gpu": None, "backend": "MuJoCo CPU"}.items():
        checks.same(metadata.get(key), expected, "B production metadata " + key)
    checks.require(type(metadata.get("source_commit")) is str and re.fullmatch("[0-9a-f]{40}", metadata["source_commit"]) is not None, "B full source commit")
    checks.same(audit["execution"]["source_git_verification_enabled"], True, "B first audit source Git verification")
    for key in ("physical_simulation_calls", "model_parameter_updates", "online_model_imports", "A_audit_reexecutions", "diagonal_model_refits"):
        checks.same(audit["execution"][key], 0, "B audit no new physical/online work " + key)
    a_binding = bind_a(members, metadata, archive, checks)
    gate = audit["final_gates"]
    checks.same(gate["data_consistency_verified"], audit["failed"] == 0, "Existing B integrity flag")
    for name in GATES:
        for flag in ("evaluated", "passed", "validated_pass"):
            checks.require(type(gate[name].get(flag)) is bool, "Explicit original scientific flag " + name + "/" + flag)
        checks.require(not gate[name]["passed"] or gate[name]["evaluated"], "Passing original gate was evaluated")
        checks.same(gate[name]["validated_pass"], gate[name]["passed"] and audit["failed"] == 0, "Original validated scientific gate flag")
    counts = {n: {str(seed): {"regular_rows": 0, "exception_rows": 0, "phases": Counter()} for seed in (0, 1, 2)} for n in ROWS}
    for name in ROWS:
        for line in gzip.decompress(raw[name]).decode("utf-8").splitlines():
            if not line: continue
            row = parse(line); seed = row["seed"]
            checks.require(type(seed) is int and seed in (0, 1, 2), "Saved B row seed")
            record = counts[name][str(seed)]
            record["exception_rows" if "collector_exception" in row else "regular_rows"] += 1
            record["phases"][row.get("phase", "unspecified")] += 1
    sr = {s["seed"]: s for s in seeds}; derived = {s["seed"]: s for s in archive["seeds"]}
    checks.require(set(sr).issubset({0, 1, 2}), "B original seed subset, including fatal unstarted trials")
    checks.same(set(derived), {0, 1, 2}, "Three B audited seeds")
    checks.same(len(seeds), len(sr), "B original seeds unique")
    checks.same(len(archive["seeds"]), 3, "B audited seeds unique")
    checks.same([e["trial_id"] for e in episodes], [f"seed{s}_coupled_guard" for s in (0, 1, 2)], "Three B planned control trials")
    per_seed = []
    for ep in episodes:
        seed = ep["seed"]; saved = sr.get(seed, {}); ev = derived[seed]["evaluations"]
        calibration, prediction, control = ev.get("calibration", {}), ev.get("prediction", {}), ev["coupled_guard"]
        cr, pr, ce = saved.get("calibration_replay", {}), saved.get("prediction_replay", {}), saved.get("evaluations", {}).get("coupled_guard", {})
        per_seed.append({"seed": seed, "calibration_replay": {"first_audit": calibration, "saved_status": cr.get("status"),
            "attempted_vector_updates": cr.get("attempted_vector_updates"), "committed_vector_updates": cr.get("committed_vector_updates"),
            "committed_scalar_updates": cr.get("committed_scalar_updates"), "source_transition_ids_count": len(cr.get("source_transition_ids", [])),
            "rls_prediction_accounting": cr.get("rls_prediction_accounting")},
            "prediction_replay": {"first_audit": prediction, "saved_status": pr.get("status"),
                "saved_position_rmse": pr.get("position_prediction_rmse"), "saved_velocity_rmse": pr.get("velocity_prediction_rmse"),
                "source_transition_ids_count": len(pr.get("source_transition_ids", [])), "prediction_accounting": pr.get("prediction_accounting")},
            "control": {"trial_id": ep["trial_id"], "status": ep["status"], "completed": control.get("completed", False),
                "eligible": control.get("eligible", False), "reason": ep.get("reason"), "study_abort": ce.get("study_abort"),
                "collector_exception": ep.get("collector_exception"), "paid_budget": {k: ep[k] for k in KEYS},
                "phase_budgets": ep.get("phase_budgets"), "planned_prefix_calls": 100, "planned_active_calls": 200,
                "complete_score_endpoints": control.get("complete_score_endpoints"), "partial_score_endpoints": control.get("partial_score_endpoints"),
                "unreconstructed_physics_substeps": control.get("unreconstructed_physics_substeps"),
                "tracking_joint_rmse_rad": control.get("tracking_rmse_rad"), "tracking_per_axis_rmse_rad": control.get("tracking_rmse_by_axis_rad"),
                "truncated_metrics_descriptive_only": not control.get("completed", False),
                "control_effort": control.get("control_effort"), "actual_effort_complete": control.get("actual_effort_complete"),
                "actual_effort_is_lower_bound": ce.get("actual_effort_is_lower_bound"),
                "planning_accounting": ce.get("planning_accounting"), "first_audit_planning_accounting": control.get("independent_planning_accounting"),
                "diagnostic_prediction_accounting": control.get("diagnostic_prediction_accounting"),
                "planner_fallbacks": ce.get("planner_fallbacks"), "failed_planner_attempts": ce.get("failed_planner_attempts"),
                "risk_from_first_audit_control": control.get("risk", {}).get("control")},
            "saved_row_counts": {n: counts[n][str(seed)] for n in ROWS}})
    paid = {k: sum(e[k] for e in episodes) for k in KEYS}
    checks.same(paid, {k: archive["budget"][k] for k in KEYS}, "B original paid physical budget sum")
    for key in ("model_updates", "vector_model_updates"):
        checks.same(metadata[key], archive["budget"][key], "B saved offline update budget " + key)
    return {"schema_version": 1, "created_at_utc": utc(), "summary_status": "bound_descriptive_summary", "binding_checks": checks.record(),
        "source_commit": metadata["source_commit"], "protocol": metadata["protocol"], "original_input_sha256": hashes,
        "existing_first_audit_sha256": sha(audit_blob), "expected_auditor_sha256": expected_sha,
        "existing_audit": {n: audit.get(n) for n in ("checks", "failed", "violations", "maximum_recomputation_difference", "execution")},
        "scientific_gates_from_first_audit": gate, "scientific_gates_recomputed": False, "control_ranking_computed": False,
        "statuses": dict(Counter(e["status"] for e in episodes)), "per_seed": per_seed,
        "A_prior_paid_budget": a_binding["A_paid_budget"], "A_original_identity_binding": a_binding,
        "B_new_paid_physical_budget": paid, "B_new_offline_replay_updates": {k: archive["budget"][k] for k in ("model_updates", "vector_model_updates")},
        "A_plus_B_paid_physical_budget": {k: a_binding["A_paid_budget"][k] + paid[k] for k in KEYS},
        "collector_timing": {k: metadata.get(k) for k in ("wall_seconds", "cpu_seconds")},
        "new_summary_work": {"physical_calls": 0, "model_updates": 0, "body_predictions": 0, "audit_executions": 0,
                             "diagonal_refits": 0, "RLS_MPC_replays": 0, "git_queries": 0}, "claim_boundary": BOUNDARY}

def execute(input_dir, audit_path, output, expected_sha):
    if not valid_hash(expected_sha): raise ValueError("Explicit root-frozen --expected-auditor-sha256 must be lowercase SHA256")
    wall, cpu = time.perf_counter(), time.process_time(); output = Path(output); output.mkdir(exist_ok=False)
    own = Path(__file__).read_bytes(); (output / "tool_source.py").write_bytes(own)
    record = {"started_at_utc": utc(), "tool_sha256": sha(own), "python": sys.version, "expected_auditor_sha256": expected_sha,
        "physical_calls": 0, "model_updates": 0, "body_predictions": 0, "audit_executions": 0, "git_queries": 0}
    save(output / "attempt.json", record); reader, checks, result, code = Reader(), Checks(), None, 1
    try:
        checks.same({p.name for p in Path(input_dir).iterdir() if p.is_file()}, set(RAW), "B raw directory exact file coverage")
        raw = {n: reader.read(n, Path(input_dir) / n) for n in RAW}
        audit_blob = reader.read("first_audit", Path(audit_path)); result = summarize(raw, audit_blob, expected_sha, checks); code = 0
    except BaseException as error:
        record["exception"] = {"type": type(error).__name__, "message": str(error)}
        result = {"summary_status": "binding_or_parse_failed", "binding_checks": checks.record(), "exception": record["exception"],
                  "scientific_interpretation_available": False, "claim_boundary": BOUNDARY}
    finally:
        save(output / "summary.json", result); save(output / "read_cost.json", reader.record())
        after = Path(__file__).read_bytes(); record["tool_source_unchanged"] = after == own
        if after != own: code = 1
        record.update(exit_code=code, wall_seconds=time.perf_counter()-wall, cpu_seconds=time.process_time()-cpu,
            binding_checks=checks.record(), output_sha256={p.name: sha(p.read_bytes()) for p in sorted(output.iterdir()) if p.is_file()})
        save(output / "execution.json", record)
    return code, result

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("input", "audit", "output"): parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--expected-auditor-sha256", required=True)
    args = parser.parse_args(); code, result = execute(args.input, args.audit, args.output, args.expected_auditor_sha256)
    print(json.dumps({"status": result["summary_status"], "exit_code": code, "checks": result["binding_checks"],
        "new_physical_budget": result.get("B_new_paid_physical_budget")}, ensure_ascii=False)); return code

if __name__ == "__main__": raise SystemExit(main())
