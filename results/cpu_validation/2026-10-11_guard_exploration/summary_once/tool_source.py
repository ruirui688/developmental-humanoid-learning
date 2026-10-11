"""Thin C4 C once-only descriptive summary. Stdlib; no fit/predict/audit/Git/physics."""
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

RAW = ("metadata.json", "episodes.json", "seed_results.json", "trace.jsonl.gz", "source_snapshot.zip", "manifest.json")
KINDS = ("calibration_sparse", "calibration_continuation", "prediction", "nominal_guard",
         "learned_sparse", "learned_continuation", "PDselected", "zero")
GROUPS = ("sparse", "continuation")
PHASES = ("prefix", "calibration", "prediction", "control")
KEYS = ("control_calls_attempted", "control_steps", "physics_steps")
AUDITOR = "scripts/audit_guard_exploration_development.py"
PROTOCOL = "docs/GUARD_EXPLORATION_DEVELOPMENT_PROTOCOL.md"
COLLECTOR = "src/developmental_physics/guard_exploration_development.py"
SUPPORT = ("scripts/audit_guard_coupled_development.py", "scripts/audit_local_frozen.py",
           "scripts/audit_pair_frozen.py", "scripts/audit_guard_pair_development.py")
PD_ROOT = "results/cpu_validation/2026-10-11_pair_pd/"
PD_NAMES = ("selection.json", "manifest.json", "first_audit.json", "raw/metadata.json", "raw/source_snapshot.zip")
PD_PROTOCOL = "docs/PAIR_PD_DEVELOPMENT_PROTOCOL.md"
REQUIRED = {AUDITOR, PROTOCOL, COLLECTOR, *SUPPORT, PD_PROTOCOL, *(PD_ROOT + n for n in PD_NAMES),
            "src/developmental_physics/guard_coupled_pair_model.py", "src/developmental_physics/pd_selection_binding.py"}
BOUNDARY = ("Fresh C development exploration evidence, not A/B replay or holdout. "
    "Only first-audit metrics and gates are described. Truncated metrics never rank failed trials. "
    "2/8 plus native veto is one bundled intervention. Byte integrity is separate from scientific gates. "
    "No adaptation, skill, safety, real-robot or final-generalization claim.")

SCOPE = {'suite': 'guard_exploration_development', 'pose': 'supine', 'seeds': [0, 1, 2], 'joint_indices': [0, 1], 'split': 'development', 'collector': 'src/developmental_physics/guard_exploration_development.py', 'auditor': 'scripts/audit_guard_exploration_development.py', 'protocol': 'docs/GUARD_EXPLORATION_DEVELOPMENT_PROTOCOL.md', 'synthetic_fixture': False, 'scientific_gates_frozen': True, 'prefix_steps': 100, 'calibration_steps': 400, 'prediction_steps': 100, 'control_steps': 200, 'structure': 'coupled_hinge9', 'input_basis': 'known_angle_guard', 'parameters_per_output': 9, 'calibration_rules': {'sparse': 'sparse_1_9', 'continuation': 'continuation_2_8_native_veto'}, 'continuation_veto': {'absolute_velocity_rad_s': 0.5, 'absolute_q_minus_qref_rad': 0.06, 'comparison': '>='}, 'prediction_rule': 'continuation_2_8_native_veto', 'prediction_velocity_ratio_max': 0.8, 'body_tracking_mean_improvement_min': 0.2, 'exploration_prediction_ratio_max': 0.8, 'exploration_tracking_mean_improvement_min': 0.2, 'exploration_actual_effort_ratio_max': 1.05, 'pd_tracking_joint_mean_improvement_min': 0.05, 'pd_actual_effort_ratio_max': 1.05, 'minimum_calibration_nonzero_start_G_intervals_per_axis': 1, 'minimum_calibration_actual_absolute_effort_positive_per_axis': True, 'minimum_prediction_nonzero_start_G_intervals_per_axis': 1, 'pd_selected_id': 2, 'pd_kp': [64.0, 64.0], 'pd_kd': [0.0, 4.0]}

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

class Reader:

    def __init__(self):
        self.records = {}

    def read(self, key, path):
        if key in self.records:
            raise ValueError('Second original read denied: ' + key)
        entry = {'path': str(path.resolve()), 'read_attempts': 1, 'successful_reads': 0}
        self.records[key] = entry
        began = time.perf_counter()
        try:
            blob = path.read_bytes()
            entry.update(successful_reads=1, bytes=len(blob), sha256=sha(blob))
            return blob
        except BaseException as error:
            entry['error'] = {'type': type(error).__name__, 'message': str(error)}
            raise
        finally:
            entry['wall_seconds'] = time.perf_counter() - began

    def record(self):
        return {"original_inputs": {n: self.records.get(n, {"read_attempts": 0, "successful_reads": 0})
                    for n in (*RAW, "first_audit")},
            "total_original_read_attempts": sum(r["read_attempts"] for r in self.records.values()),
            "physical_calls": 0, "model_updates": 0, "body_predictions": 0, "audit_executions": 0,
            "git_queries": 0, "A_B_PD_original_filesystem_reads": 0, "tests_included": False,
            "cache_semantics": "Six C raw files and first audit each read once; embedded PD only from cached C ZIP"}


def bind_pd(members, metadata, checks):
    """Bind five embedded PD original identities; no trace, score replay or audit."""
    blobs = {n: members[PD_ROOT + n] for n in PD_NAMES}
    selection, outer, prior, pm = (parse(blobs[n]) for n in PD_NAMES[:4])
    checks.same(set(selection), {"schema", "status", "selected", "protocol", "sources"}, "PD selection schema fields")
    checks.same(selection["schema"], "c4-pd-selection-v1", "PD original selection schema")
    checks.same(selection["status"], "selected", "PD original selected status")
    checks.same(selection["selected"], {"candidate_id": 2, "joint_indices": [0, 1],
        "kp": [64., 64.], "kd": [0., 4.]}, "Frozen PD candidate2 gains and joints")
    protocol = {"path": PD_PROTOCOL, "sha256": sha(members[PD_PROTOCOL])}
    checks.same(selection["protocol"], protocol, "PD selection protocol bytes")
    checks.same(outer["protocol"], protocol, "PD original manifest protocol")
    sources = {key: {"path": PD_ROOT + filename, "sha256": sha(blobs[filename])}
        for key, filename in (("manifest", "manifest.json"), ("audit", "first_audit.json"))}
    checks.same(selection["sources"], sources, "PD original selected manifest/audit bytes")
    checks.same(prior["validated_selection"], True, "PD existing validated selection")
    checks.same(prior["source_git_verification_enabled"], True, "PD existing source verification preserved")
    checks.same(prior["failed_checks"], 0, "PD existing identity audit succeeded")
    checks.same(prior["selection"]["status"], "selected", "PD first-audit selected status")
    picked = prior["selection"]["picked"]
    for key, value in {"candidate": 2, "kp": [64., 64.], "kd": [0., 4.], "eligible": True,
            "paid_control_steps": 900, "paid_physics_steps": 9000}.items():
        checks.same(picked[key], value, "PD first-audit chosen identity " + key)
    originals = {}
    for name, record in outer["files"].items():
        checks.require(safe(name) and valid_hash(record["sha256"]) and type(record["bytes"]) is int
                       and record["bytes"] >= 0, "PD original manifest safe byte identity " + name)
        if name.startswith("raw/"):
            local = name[4:]
            checks.require("/" not in local, "PD raw names remain local")
            originals[local] = record["sha256"]
    checks.same(prior["input_hashes"], originals, "PD original manifest/first-audit raw identity map")
    checks.require({"metadata.json", "source_snapshot.zip", "manifest.json", "episodes.json", "selection.json",
                    "trace.jsonl.gz"}.issubset(originals), "PD original raw identity coverage")
    for name in ("metadata.json", "source_snapshot.zip"):
        blob = blobs["raw/" + name]
        checks.same(sha(blob), originals[name], "PD embedded original raw SHA " + name)
        checks.same(len(blob), outer["files"]["raw/" + name]["bytes"], "PD embedded original raw bytes " + name)
    checks.same(pm["protocol"], protocol, "PD original metadata protocol")
    checks.same(pm["source_snapshot_sha256"], originals["source_snapshot.zip"], "PD original source ZIP identity")
    inner = zip_members(blobs["raw/source_snapshot.zip"], pm["source_sha256"], checks, "PD original source ZIP")
    required = (PD_PROTOCOL, "scripts/audit_pair_pd.py", "scripts/audit_local_frozen.py")
    checks.require(set(required).issubset(inner), "PD original required source identity")
    archived = {n: sha(inner[n]) for n in required}
    checks.same(archived[PD_PROTOCOL], protocol["sha256"], "PD original nested protocol bytes")
    checks.same(prior["audit_sources_sha256"], {"auditor": archived[required[1]], "common": archived[required[2]]},
                "PD original executing auditor source identity")
    binding = {"schema": "c4-pd-source-binding-v1", "status": "selected", "selected_id": 2, "joint_indices": [0, 1],
        "kp": [64., 64.], "kd": [0., 4.], "selection_path": PD_ROOT + "selection.json",
        "selection_sha256": sha(blobs["selection.json"]), "selection_tracking_evidence": "caller_verified_tracked_paths",
        "sources": sources, "source_records": {PD_ROOT + n: sha(blobs[n]) for n in PD_NAMES},
        "protocol": protocol, "archive_member_records": archived, "audit_selection_confirmed": True,
        "audit_reexecuted": False, "raw_trace_or_episodes_read": False,
        "remaining_original_bytes": "not reread; manifest hashes matched existing independent audit input_hashes"}
    checks.same(metadata["pd_binding"], binding, "C frozen embedded PD original binding")
    checks.same(metadata["pd_gains"], {"kp": binding["kp"], "kd": binding["kd"]}, "C matched PD public gains")
    return binding


def gate_bindings(audit, checks):
    gates = audit["final_gates"]
    checks.same(gates["data_consistency_verified"], audit["failed"] == 0, "First-audit data consistency flag")
    for group in ("body_contribution", "selected_pd_comparison"):
        checks.same(set(gates[group]), set(GROUPS), "Both original C groups " + group)
    original = [("body_contribution/" + g, gates["body_contribution"][g]) for g in GROUPS]
    original += [("exploration_intervention", gates["exploration_intervention"])]
    original += [("selected_pd_comparison/" + g, gates["selected_pd_comparison"][g]) for g in GROUPS]
    for name, gate in original:
        for flag in ("evaluated", "passed", "validated_pass"):
            checks.require(type(gate.get(flag)) is bool, "Original C scientific flag " + name + "/" + flag)
        checks.require(not gate["passed"] or gate["evaluated"], "Passing original C gate was evaluated " + name)
        checks.same(gate["validated_pass"], gate["passed"] and audit["failed"] == 0, "Original C validated flag " + name)
    matrix = gates["matrix_complete"]
    checks.require(type(matrix["passed"]) is bool and type(matrix["validated_pass"]) is bool, "Original C matrix flags")
    checks.same(matrix["validated_pass"], matrix["passed"] and audit["failed"] == 0, "Original C validated matrix flag")
    return gates


def summarize(raw, audit_blob, expected_sha, checks):
    checks.require(valid_hash(expected_sha), "Root explicit expected auditor SHA256 required")
    checks.same(set(raw), set(RAW), "Exactly six cached C raw files")
    metadata, episodes, seeds = (parse(raw[n]) for n in RAW[:3])
    manifest, audit = parse(raw["manifest.json"]), parse(audit_blob)
    hashes = {n: sha(blob) for n, blob in raw.items()}
    checks.same(manifest, {n: h for n, h in hashes.items() if n != "manifest.json"}, "C raw exact five manifest hashes")
    checks.same(audit["schema_version"], 1, "C first-audit schema")
    checks.require(type(audit["checks"]) is int and type(audit["failed"]) is int and
                   0 <= audit["failed"] <= audit["checks"], "Existing C audit counts")
    checks.same(audit["immutable_scope"], SCOPE, "C fixed production audit scope")
    checks.same(audit["audit_script_sha256"], expected_sha, "Root explicit executing C auditor identity")
    archive = audit["archive"]
    checks.require(type(archive) is dict, "First C audit contains reconstructed archive")
    checks.same(archive["input_hashes"], hashes, "First C audit exact six raw identity hashes")
    checks.same(archive["episodes"], episodes, "First C audit original episodes")
    checks.same(metadata["source_snapshot_sha256"], hashes["source_snapshot.zip"], "C original source ZIP identity")
    checks.require(REQUIRED.issubset(metadata["source_sha256"]), "C frozen source and embedded PD identity coverage")
    members = zip_members(raw["source_snapshot.zip"], metadata["source_sha256"], checks, "C frozen source ZIP")
    checks.same(sha(members[AUDITOR]), expected_sha, "Root explicit C auditor source bytes")
    checks.same(audit["audit_dependency_sha256"], {n: sha(members[n]) for n in SUPPORT}, "C executing auditor support source bytes")
    checks.same(metadata["independent_auditor"], {"path": AUDITOR, "sha256": expected_sha,
        "pending": False, "required_for_formal": True}, "C frozen executing auditor declaration")
    checks.same(metadata["protocol"], {"path": PROTOCOL, "sha256": sha(members[PROTOCOL])}, "C frozen protocol identity")
    for name, value in {"schema_version": 1, "suite": "guard_exploration_development", "synthetic": False,
        "source_status": "", "source_dirty": False, "seeds": [0, 1, 2], "pose": "supine", "joint_indices": [0, 1],
        "split": "development", "native_joint_count": 8, "gpu": None, "backend": "MuJoCo CPU",
        "prefix_steps": 100, "calibration_steps": 400, "prediction_steps": 100, "control_steps_per_trial": 200,
        "maximum_control_steps": 8100, "maximum_physics_steps": 81000, "maximum_scalar_updates": 4800,
        "maximum_vector_updates": 2400, "calibration_data_shared": False, "prior_a_b_raw_replayed": False,
        "policy_parameter_updates": 0, "gain_updates": 0, "gate_updates": 0, "teacher_calls": 0}.items():
        checks.same(metadata.get(name), value, "C production metadata " + name)
    checks.require(type(metadata["source_commit"]) is str and re.fullmatch("[0-9a-f]{40}", metadata["source_commit"]) is not None,
                   "C full original source commit")
    checks.same(audit["execution"]["source_git_verification_enabled"], True, "C first-audit existing Git verification")
    for name in ("physical_simulation_calls", "model_parameter_updates", "online_model_imports",
                 "prior_A_B_audit_reexecutions", "diagonal_model_refits"):
        checks.same(audit["execution"][name], 0, "Existing C audit zero new online/physical work " + name)
    pd_binding = bind_pd(members, metadata, checks)
    gates = gate_bindings(audit, checks)
    plans = [f"seed{s}_{kind}" for s in (0, 1, 2) for kind in KINDS]
    checks.same([ep["trial_id"] for ep in episodes], plans, "C original fixed 24 plan order")
    saved = {sr["seed"]: sr for sr in seeds}
    derived = {sr["seed"]: sr for sr in archive["seeds"]}
    checks.same(len(saved), len(seeds), "C unique original saved seeds")
    checks.same(list(saved), [0, 1, 2][:len(saved)], "C original saved seed prefix including fatal-unstarted")
    checks.same(set(derived), {0, 1, 2}, "C first-audit three planned seeds")
    checks.same(len(archive["seeds"]), 3, "C unique first-audit seeds")
    row_counts = {tid: {"regular_rows": 0, "exception_rows": 0, "phases": Counter()} for tid in plans}
    for line in gzip.decompress(raw["trace.jsonl.gz"]).decode("utf-8").splitlines():
        if not line: continue
        row = parse(line); tid = row["trial_id"]
        checks.require(tid in row_counts and row["seed"] in (0, 1, 2) and row["kind"] in KINDS and
                       tid == f"seed{row['seed']}_{row['kind']}", "C saved trace row identity")
        rec = row_counts[tid]; rec["exception_rows" if "collector_exception" in row else "regular_rows"] += 1
        rec["phases"][row.get("phase", "unspecified")] += 1
    phase_paid = {p: {k: 0 for k in KEYS} for p in PHASES}; trials = []
    scalar = vector = 0
    for ep in episodes:
        seed, kind = ep["seed"], ep["kind"]
        ev = saved.get(seed, {}).get("evaluations", {}).get(kind, {})
        ae = derived[seed]["evaluations"][kind]
        checks.same(set(ep["phase_budgets"]), set(PHASES), "C exact phase paid ledger " + ep["trial_id"])
        for k in KEYS:
            for p in PHASES:
                value = ep["phase_budgets"][p][k]
                checks.require(type(value) is int and value >= 0, "C saved nonnegative phase counter")
                phase_paid[p][k] += value
            checks.same(ep[k], sum(ep["phase_budgets"][p][k] for p in PHASES), "C paid phase sum " + ep["trial_id"] + "/" + k)
        cal = None
        if kind.startswith("calibration_"):
            cr = saved.get(seed, {}).get("calibrations", {}).get(kind.removeprefix("calibration_"), {})
            cal = {n: cr.get(n) for n in ("status", "completed", "attempted_vector_updates", "committed_vector_updates",
                "committed_scalar_updates", "rls_prediction_accounting", "excitation", "command_veto_count_per_axis")}
            cal["source_transition_ids_count"] = len(cr.get("source_transition_ids", []))
            scalar += cr.get("committed_scalar_updates", 0); vector += cr.get("committed_vector_updates", 0)
        trials.append({"trial_id": ep["trial_id"], "seed": seed, "kind": kind,
            "original_episode": ep, "first_audit_evaluation": ae,
            "complete": ae.get("completed", False), "eligible": ae.get("eligible", False),
            "truncated_metrics_descriptive_only": not ae.get("completed", False),
            "saved_metrics": {n: ev.get(n) for n in ("tracking_rmse", "metric_control_step_count",
                "position_prediction_rmse", "velocity_prediction_rmse", "metric_prediction_step_count",
                "partial_interval_target_errors_rad", "partial_endpoint_prediction_errors")},
            "saved_cost_and_effort": {n: ev.get(n) for n in ("phase_effort", "phase_actual_effort_complete",
                "phase_actual_effort_substeps", "phase_missing_actual_effort_substeps", "control_effort",
                "actual_effort_complete", "actual_effort_is_lower_bound", "diagnostic_prediction_accounting",
                "planning_accounting", "failed_planner_attempts", "model_updates")},
            "saved_excitation": ev.get("excitation"), "saved_command_veto_count_per_axis": ev.get("command_veto_count_per_axis"),
            "saved_model_availability": ev.get("model_availability"), "saved_available_models": ev.get("available_models"),
            "saved_calibration": cal, "saved_trace_row_counts": row_counts[ep["trial_id"]]})
    paid = {k: sum(ep[k] for ep in episodes) for k in KEYS}
    for k in KEYS:
        checks.same(paid[k], metadata[k], "C original metadata paid sum " + k)
        checks.same(paid[k], archive["budget"][k], "C first-audit paid sum " + k)
    for k, value in (("model_updates", scalar), ("vector_model_updates", vector)):
        checks.same(metadata[k], value, "C original calibration committed update sum " + k)
        checks.same(archive["budget"][k], value, "C audited calibration committed updates " + k)
    statuses = dict(Counter(ep["status"] for ep in episodes))
    for name, status in (("completed_trials", "completed"), ("terminated_trials", "terminated"),
                         ("exception_trials", "exception"), ("blocked_trials", "blocked")):
        checks.same(metadata[name], statuses.get(status, 0), "C saved outcome sum " + name)
    return {"schema_version": 1, "created_at_utc": utc(), "summary_status": "bound_descriptive_summary",
        "binding_checks": checks.record(), "source_commit": metadata["source_commit"], "protocol": metadata["protocol"],
        "original_input_sha256": hashes, "existing_first_audit_sha256": sha(audit_blob), "expected_auditor_sha256": expected_sha,
        "existing_audit": {n: audit.get(n) for n in ("checks", "failed", "violations", "maximum_recomputation_difference", "execution")},
        "scientific_gates_from_first_audit": gates, "scientific_gates_recomputed": False, "control_ranking_computed": False,
        "statuses": statuses, "C_new_paid_physical_budget": paid, "phase_total_paid_budget": phase_paid,
        "C_new_online_calibration_updates": {"model_updates": scalar, "vector_model_updates": vector,
            "maximum_scalar_updates": 4800, "maximum_vector_updates": 2400, "offline_replay_updates": 0,
            "control_or_prediction_updates": 0, "classification": "New independent C physical calibration, not A/B replay"},
        "paid_pair_prediction_attempts_from_first_audit": archive["paid_pair_prediction_attempts"],
        "declared_prediction_caps": {"rls": 2400, "prediction": 900, "control_diagnostic": 1800, "mpc": 2187000},
        "PD_original_identity_binding": pd_binding, "trials": trials,
        "collector_timing": {n: metadata.get(n) for n in ("wall_seconds", "cpu_seconds")},
        "dependencies": metadata.get("dependencies"), "new_summary_work": {"physical_calls": 0, "model_updates": 0,
            "body_predictions": 0, "audit_executions": 0, "RLS_MPC_replays": 0, "git_queries": 0}, "claim_boundary": BOUNDARY}


def execute(input_dir, audit_path, output, expected_sha):
    if not valid_hash(expected_sha): raise ValueError("Explicit root-frozen --expected-auditor-sha256 required")
    wall, cpu = time.perf_counter(), time.process_time(); output = Path(output); output.mkdir(exist_ok=False)
    own = Path(__file__).read_bytes(); (output / "tool_source.py").write_bytes(own)
    record = {"started_at_utc": utc(), "tool_sha256": sha(own), "python": sys.version, "expected_auditor_sha256": expected_sha,
        "physical_calls": 0, "model_updates": 0, "body_predictions": 0, "audit_executions": 0, "git_queries": 0}
    save(output / "attempt.json", record); reader, checks, result, code = Reader(), Checks(), None, 1
    try:
        checks.same({p.name for p in Path(input_dir).iterdir() if p.is_file()}, set(RAW), "C raw exact six file coverage")
        raw = {n: reader.read(n, Path(input_dir) / n) for n in RAW}
        audit_blob = reader.read("first_audit", Path(audit_path))
        result = summarize(raw, audit_blob, expected_sha, checks); code = 0
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
        "new_physical_budget": result.get("C_new_paid_physical_budget")}, ensure_ascii=False)); return code


if __name__ == "__main__": raise SystemExit(main())
