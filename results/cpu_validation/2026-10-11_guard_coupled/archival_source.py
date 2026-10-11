"""Exclusive B first-run byte archive. No Git, physics, model or audit execution."""
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
import sys
import time
import zipfile

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "results/cpu_validation/2026-10-11_guard_coupled"
RAW_DIR = ROOT / "external/guard_coupled_20261011_first"
SUMMARY_DIR = ROOT / "external/guard_coupled_20261011_summary_01"
COMMIT = "f68c485e383b071ebe534465d3c17f65e5600a62"
PROTOCOL = "docs/GUARD_COUPLED_DEVELOPMENT_PROTOCOL.md"
AUDITOR = "scripts/audit_guard_coupled_development.py"
AUDITOR_SHA = "c77a1c2a5cfeed08774dab20a6ef5d4e4833264621e37832b3888001182cc10a"
A_ROOT = "results/cpu_validation/2026-10-11_guard_pair/"
RAW_NAMES = {"metadata.json", "episodes.json", "seed_results.json", "source_snapshot.zip", "manifest.json",
             "calibration_replay.jsonl.gz", "prediction_replay.jsonl.gz", "trace.jsonl.gz"}
STAGES = ("c4_guard_coupled_staging", "c4_guard_coupled_runner_staging", "c4_guard_coupled_audit_staging",
          "c4_guard_coupled_summary_staging", "c4_guard_coupled_core_promoted_01", "c4_guard_coupled_promoted_01",
          "c4_coupled_real_binding_01", "c4_after_pair_failure_read_01", "c4_c_exploration_design_staging")
LOOSE = ("c4_guard_coupled_core_promoted_01_stdout.txt", "c4_coupled_real_binding_01_stdout.txt",
         "promote_guard_coupled_once.py", "c4_after_pair_failures_design.md", "read_c4_after_pair_failures_once.py",
         "extract_coupled_saved_failure_once.py", "archive_guard_coupled_20261011_DELIVERY.md")
EXECUTION_INPUTS = {
    "execution/first_execution.json": "external/guard_coupled_20261011_first_execution.json",
    "execution/first_stdout.txt": "external/guard_coupled_20261011_first_stdout.txt",
    "execution/first_audit_stdout.txt": "external/guard_coupled_20261011_first_audit_stdout.txt",
    "execution/run_guard_coupled_once.py": "external/run_guard_coupled_once.py",
    "execution/postprocess_execution.json": "external/guard_coupled_20261011_postprocess_execution.json",
    "execution/audit_and_summarize_guard_coupled_once.py": "external/audit_and_summarize_guard_coupled_once.py",
}
TEST_SNAPSHOTS = {
    "tests/test_guard_coupled_pair_model.py": "c4_guard_coupled_core_promoted_01",
    **{n: "c4_guard_coupled_promoted_01" for n in ("tests/test_guard_coupled_development.py",
        "tests/test_guard_pair_source_binding.py", "tests/test_audit_guard_coupled_development.py",
        "tests/synthetic_a_fixture.py", "tests/synthetic_a_source_fixture.py")},
}

def sha(blob): return hashlib.sha256(blob).hexdigest()
def encoded(value): return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode()
def safe(name):
    return (type(name) is str and bool(name) and "\\" not in name and not PurePosixPath(name).is_absolute()
        and not PureWindowsPath(name).drive and all(p not in ("", ".", "..") for p in name.split("/")))

def main():
    wall, cpu = time.perf_counter(), time.process_time()
    OUTPUT.mkdir(parents=True, exist_ok=False)
    files, bundles, input_hashes, cache, violations = {}, {}, {}, {}, []
    count = 0
    def check(ok, label):
        nonlocal count
        count += 1
        if not ok: violations.append(label)
    def read(path):
        path = Path(path).resolve(); key = path.relative_to(ROOT).as_posix()
        if key in cache: return cache[key]
        record = {"read_attempts": 1, "successful_reads": 0}; input_hashes[key] = record
        try:
            blob = path.read_bytes(); cache[key] = blob
            record.update(successful_reads=1, bytes=len(blob), sha256=sha(blob)); return blob
        except BaseException as error:
            record["exception"] = {"type": type(error).__name__, "message": str(error)}; raise
    def store(name, blob, kind, source, **identity):
        if not safe(name): raise ValueError("Unsafe archive path: " + name)
        path = OUTPUT / name; path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as out: out.write(blob)
        files[name] = {"kind": kind, "source": source, "bytes": len(blob), "sha256": sha(blob), **identity}
        check(path.read_bytes() == blob, "exact_copy/" + name)
        return blob
    def copy(name, path, kind):
        return store(name, read(path), kind, Path(path).resolve().relative_to(ROOT).as_posix())
    own = read(Path(__file__))
    store("archival_source.py", own, "archival_tool_source", Path(__file__).relative_to(ROOT).as_posix())
    store("attempt.json", encoded({"source_commit": COMMIT, "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "Byte copy/hash/ZIP only; exclusive output; current B snapshots and prior original evidence labeled separately",
        "physical_calls": 0, "model_updates": 0, "new_predictions": 0, "audit_executions": 0,
        "summary_executions": 0, "git_queries": 0}), "archival_attempt", "This exclusive invocation")
    error, protocol = None, None
    source_classification = {}
    try:
        check({p.name for p in RAW_DIR.iterdir() if p.is_file()} == RAW_NAMES, "raw_exact_eight_files")
        raw = {n: copy("raw/" + n, RAW_DIR / n, "original_first_B_raw") for n in sorted(RAW_NAMES)}
        metadata, manifest = json.loads(raw["metadata.json"]), json.loads(raw["manifest.json"])
        check(manifest == {n: sha(b) for n, b in raw.items() if n != "manifest.json"}, "raw_exact_seven_manifest_hashes")
        check(metadata["source_commit"] == COMMIT and metadata["source_status"] == "" and metadata["source_dirty"] is False, "original_B_clean_source_commit")
        check([metadata[k] for k in ("control_calls_attempted", "control_steps", "physics_steps", "model_updates", "vector_model_updates")]
              == [618, 618, 6180, 2400, 1200], "first_B_paid_physical_and_offline_costs")
        check([metadata[k] for k in ("completed_trials", "terminated_trials", "exception_trials", "blocked_trials")]
              == [0, 3, 0, 0], "first_B_stops_preserved")
        protocol = metadata["protocol"]; check(protocol["path"] == PROTOCOL, "B_protocol_path")
        audit_blob = copy("first_audit.json", ROOT / "external/guard_coupled_20261011_first_audit.json", "original_first_B_stdlib_audit")
        audit = json.loads(audit_blob)
        check(audit["checks"] == 1642786 and audit["failed"] == 0, "original_first_audit_preserved")
        check(audit["archive"]["input_hashes"] == {n: sha(b) for n, b in raw.items()}, "first_audit_exact_eight_raw_binding")
        check(audit["execution"]["source_git_verification_enabled"] is True, "first_audit_preexisting_Git_verification")
        for gate in ("coupled_contribution", "diagonal_increment", "selected_pd_comparison"):
            check(audit["final_gates"][gate]["passed"] is False and audit["final_gates"][gate]["validated_pass"] is False, "scientific_failure_preserved/" + gate)
        execution_data = {}
        for name, path in EXECUTION_INPUTS.items(): execution_data[name] = copy(name, ROOT / path, "original_first_B_execution_or_postprocess")
        first = json.loads(execution_data["execution/first_execution.json"])
        check(first["source_commit"] == COMMIT and first["repeated"] is False, "first_B_process_once")
        post = json.loads(execution_data["execution/postprocess_execution.json"])
        check(len(post["executions"]) == 2 and all(r["repeated"] is False and r["exit_code"] == 0 for r in post["executions"]), "first_audit_and_summary_wrapper_once")
        summary_bytes = {}
        for path in sorted(SUMMARY_DIR.rglob("*")):
            if path.is_file():
                name = path.relative_to(SUMMARY_DIR).as_posix()
                summary_bytes[name] = copy("summary_once/" + name, path, "original_once_B_descriptive_summary")
        sx = json.loads(summary_bytes["execution.json"])
        check(sx["exit_code"] == 0 and sx["binding_checks"]["checks"] == 2436 and sx["binding_checks"]["failed"] == 0, "original_once_summary_success")
        check(all(sx[k] == 0 for k in ("physical_calls", "model_updates", "body_predictions", "audit_executions", "git_queries")), "summary_zero_new_model_or_physics")
        for name, expected in sx["output_sha256"].items(): check(files["summary_once/" + name]["sha256"] == expected, "summary_output_sha/" + name)
        copy("summary_once/stdout.txt", ROOT / "external/guard_coupled_20261011_summary_01_stdout.txt", "original_summary_stdout")
        reads = json.loads(summary_bytes["read_cost.json"])["original_inputs"]
        check(set(reads) == RAW_NAMES | {"first_audit"} and all(r["read_attempts"] == 1 and r["successful_reads"] == 1 for r in reads.values()), "summary_original_nine_inputs_read_once")
        diagnostic_dir = ROOT / "external/guard_coupled_20261011_failure_diagnostic_01"
        for path in sorted(diagnostic_dir.iterdir()):
            if path.is_file(): copy("saved_failure_diagnostic/" + path.name, path, "saved_decision_prediction_extraction_no_new_model_calls")
        check(files["saved_failure_diagnostic/saved_failed_controls.json"]["sha256"] == "3116b7b1b554e7d420c675db787bfa26763c6fe123995eea6c95e50bbd6daac4", "saved_failure_extraction_identity")
        copy("saved_failure_diagnostic/stdout.txt", ROOT / "external/guard_coupled_20261011_failure_diagnostic_01_stdout.txt", "original_saved_extraction_stdout")
        check(metadata["source_snapshot_sha256"] == sha(raw["source_snapshot.zip"]), "B_source_ZIP_identity")
        with zipfile.ZipFile(io.BytesIO(raw["source_snapshot.zip"])) as source:
            names = source.namelist()
            check(len(names) == len(set(names)) and set(names) == set(metadata["source_sha256"]), "B_source_unique_exact_coverage")
            am_blob = source.read(A_ROOT + "raw/metadata.json")
            am = json.loads(am_blob); a_sources = am["source_sha256"]
            binding = metadata["a_binding"]
            check(binding == audit["archive"]["A_original_binding"], "A_original_binding_preserved")
            check(binding["source_sha256"] == a_sources and binding["source_commit"] == am["source_commit"], "A_prior_original_source_identity")
            for name in names:
                if not safe(name): raise ValueError("Unsafe original source member: " + name)
                blob = am_blob if name == A_ROOT + "raw/metadata.json" else source.read(name)
                check(sha(blob) == metadata["source_sha256"][name], "B_source_SHA/" + name)
                origin = None
                if name.startswith(A_ROOT):
                    kind = "embedded_original_A_evidence"; origin = binding["source_commit"]
                elif name.startswith("results/") and name in a_sources:
                    kind = "embedded_prior_evidence_from_A_source_snapshot"; origin = binding["source_commit"]
                elif name in a_sources:
                    kind = "shared_A_B_source_snapshot_bytes"; origin = binding["source_commit"]
                else: kind = "current_B_frozen_source_snapshot_bytes"
                if name in a_sources: check(sha(blob) == a_sources[name], "original_A_shared_source_SHA/" + name)
                source_classification[name] = {"kind": kind, "B_source_commit_verified_by_first_audit": COMMIT,
                    "A_origin_commit": origin, "Git_reverified_by_archival_tool": False}
                store("frozen_source/" + name, blob, kind, "Original B source_snapshot.zip member " + name,
                      **{key: value for key, value in source_classification[name].items() if key != "kind"})
        check(protocol["sha256"] == files["frozen_source/" + PROTOCOL]["sha256"], "B_protocol_frozen_snapshot_SHA")
        check(audit["audit_script_sha256"] == AUDITOR_SHA == files["frozen_source/" + AUDITOR]["sha256"], "executing_B_auditor_source_identity")
        for name, expected in audit["audit_dependency_sha256"].items(): check(files["frozen_source/" + name]["sha256"] == expected, "executing_B_support_identity/" + name)
        for name, stage in TEST_SNAPSHOTS.items():
            copy("frozen_check_source/" + name, ROOT / "external" / stage / "source" / name,
                 "original_promoted_test_source_snapshot_not_new_Git_query")
        buffer, bundle_members = io.BytesIO(), {}
        paths = []
        for dirname in STAGES:
            directory = ROOT / "external" / dirname
            check(directory.is_dir(), "original_stage_exists/" + dirname)
            paths.extend((dirname + "/" + p.relative_to(directory).as_posix(), p) for p in sorted(directory.rglob("*"))
                         if p.is_file() and "__pycache__" not in p.parts)
        paths.extend(("loose/" + name, ROOT / "external" / name) for name in LOOSE)
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
            for name, path in paths:
                if not safe(name): raise ValueError("Unsafe bundle member: " + name)
                blob = read(path); bundle.writestr(name, blob)
                bundle_members[name] = {"source": path.relative_to(ROOT).as_posix(), "bytes": len(blob), "sha256": sha(blob)}
        blob = buffer.getvalue()
        store("staging_evidence.zip", blob, "all_original_core_runner_audit_summary_checks_and_C_design_attempts",
              "Four staging trees, promoted/binding checks and C proposal/cache; all files except transient __pycache__")
        with zipfile.ZipFile(io.BytesIO(blob)) as bundle:
            check(len(bundle.namelist()) == len(set(bundle.namelist())) == len(bundle_members), "staging_bundle_unique_exact_coverage")
            for name in bundle.namelist(): check(sha(bundle.read(name)) == bundle_members[name]["sha256"], "staging_bundle_member_SHA/" + name)
        bundles["staging_evidence.zip"] = {"member_count": len(bundle_members), "bytes": len(blob), "sha256": sha(blob),
            "members": bundle_members, "initial_and_failed_attempts_preserved": True}
    except BaseException as exc:
        error = {"type": type(exc).__name__, "message": str(exc)}
    finally:
        check(Path(__file__).read_bytes() == own, "archival_tool_unchanged")
        record = {"created_at_utc": datetime.now(timezone.utc).isoformat(), "source_commit": COMMIT, "protocol": protocol,
            "files": files, "bundles": bundles, "input_hashes": input_hashes, "source_classification": source_classification,
            "source_provenance": {"current_B_source": "Cached original source ZIP; original B first-audit Git verification preserved",
                "prior_A_evidence": "Embedded original identities, not regenerated current working-tree content",
                "archival_Git_queries": 0, "archival_current_worktree_source_reads": 0},
            "verification": {"checks": count, "failed": len(violations), "violations": violations, "exception": error},
            "cumulative_accounting": {"prior_formal_control_calls": 238502, "this_B_control_calls": 618,
                "formal_control_calls": 239120, "formal_physics_substeps": 2391200,
                "online_scalar_model_updates": 17652, "this_B_offline_replay_scalar_updates": 2400,
                "total_algorithm_scalar_updates_including_new_offline_replay": 20052,
                "new_B_offline_updates_are_not_new_physical_calls": True},
            "execution": {"python": sys.version, "wall_seconds": time.perf_counter()-wall, "cpu_seconds": time.process_time()-cpu,
                "exit_code": int(bool(violations) or error is not None), "physical_calls": 0, "model_updates": 0,
                "new_predictions": 0, "audit_executions": 0, "summary_executions": 0, "git_queries": 0},
            "manifest_self_hash_excluded": True, "claim_boundary": "Byte integrity only; B scientific failures preserved; online/offline costs separated."}
        with (OUTPUT / "manifest.json").open("xb") as out: out.write(encoded(record))
    print(json.dumps({"output": str(OUTPUT), "files": len(files), "checks": count, "failed": len(violations), "exception": error,
        "manifest_sha256": sha((OUTPUT / "manifest.json").read_bytes()), "execution": record["execution"]}))
    return record["execution"]["exit_code"]

if __name__ == "__main__": raise SystemExit(main())
