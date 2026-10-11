"""Exclusive C first-run byte seal; no Git/model/physics/audit/summary execution."""
import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import sys
import time
import zipfile

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "results/cpu_validation/2026-10-11_guard_exploration"
RAW_DIR = ROOT / "external/guard_exploration_20261011_first"
SUMMARY_DIR = ROOT / "external/guard_exploration_20261011_summary_01"
AUDITOR = "scripts/audit_guard_exploration_development.py"
AUDITOR_SHA = "962a928b5d643ed2a3d4da20da2940a9a4e17932818c859beb204f11bf59ffa3"
SUMMARY_SHA = "440645b9433cb1b20b7b54fa5a00934395e0aeb7256607621b2203c21cb1705e"
PROTOCOL = "docs/GUARD_EXPLORATION_DEVELOPMENT_PROTOCOL.md"
PD_ROOT = "results/cpu_validation/2026-10-11_pair_pd/"
PD_NAMES = ("selection.json", "manifest.json", "first_audit.json", "raw/metadata.json", "raw/source_snapshot.zip")
RAW_NAMES = {"metadata.json", "episodes.json", "seed_results.json", "trace.jsonl.gz", "source_snapshot.zip", "manifest.json"}
KEYS = ("control_calls_attempted", "control_steps", "physics_steps")
PHASES = ("prefix", "calibration", "prediction", "control")
STAGES = ("c4_guard_exploration_staging", "c4_guard_exploration_audit_staging", "c4_guard_exploration_summary_staging",
          "c5_adaptation_design_staging", "c5_adaptation_core_staging",
          "guard_exploration_covariance_01", "c4_lag_diagnostic_design_staging")
LOOSE = ("c5_clone_core_01_stdout.txt", "run_c5_clone_core_once.py", "analyze_c_saved_covariance_once.py",
         "archive_guard_exploration_20261011_DELIVERY.md")
EXECUTION_INPUTS = {
    "execution/first_execution.json": "external/guard_exploration_20261011_first_execution.json",
    "execution/first_stdout.txt": "external/guard_exploration_20261011_first_stdout.txt",
    "execution/first_audit_stdout.txt": "external/guard_exploration_20261011_first_audit_stdout.txt",
    "execution/run_guard_exploration_once.py": "external/run_guard_exploration_once.py",
    "execution/postprocess_execution.json": "external/guard_exploration_20261011_postprocess_execution.json",
    "execution/audit_and_summarize_guard_exploration_once.py": "external/audit_and_summarize_guard_exploration_once.py",
}


def sha(blob): return hashlib.sha256(blob).hexdigest()
def encoded(value): return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode()
def safe(name):
    return (type(name) is str and bool(name) and "\\" not in name and not PurePosixPath(name).is_absolute()
        and not PureWindowsPath(name).drive and all(p not in ("", ".", "..") for p in name.split("/")))
def parsed(blob):
    def pairs(items):
        out = {}
        for key, value in items:
            if key in out: raise ValueError("Duplicate JSON key: " + key)
            out[key] = value
        return out
    def constant(value): raise ValueError("Nonfinite JSON constant: " + value)
    return json.loads(blob, object_pairs_hook=pairs, parse_constant=constant)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-source-commit", required=True)
    args = parser.parse_args(); commit = args.expected_source_commit
    if re.fullmatch("[0-9a-f]{40}", commit) is None: parser.error("Full root-fixed original C source commit required")
    wall, cpu = time.perf_counter(), time.process_time()
    OUTPUT.mkdir(parents=True, exist_ok=False)
    files, bundles, input_hashes, cache, violations, classifications = {}, {}, {}, {}, [], {}
    count = 0
    def check(ok, label):
        nonlocal count
        count += 1
        if not ok: violations.append(label)
    def read(path):
        path = Path(path).resolve(); key = path.relative_to(ROOT).as_posix()
        if key in cache: return cache[key]
        if key in input_hashes: raise ValueError("Second failed original read denied: " + key)
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
    store("attempt.json", encoded({"expected_source_commit": commit, "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "Cached byte copies/hash/ZIP only; no current source or Git reconstruction; exclusive output",
        "physical_calls": 0, "model_updates": 0, "new_predictions": 0, "audit_executions": 0,
        "summary_executions": 0, "git_queries": 0}), "archival_attempt", "This exclusive invocation")
    error, protocol, accounting, original_outcomes, first_source_verification = None, None, None, None, None
    try:
        check({p.name for p in RAW_DIR.iterdir() if p.is_file()} == RAW_NAMES, "C_raw_exact_six_files")
        raw = {n: copy("raw/" + n, RAW_DIR / n, "original_first_C_raw") for n in sorted(RAW_NAMES)}
        metadata, episodes, manifest = parsed(raw["metadata.json"]), parsed(raw["episodes.json"]), parsed(raw["manifest.json"])
        hashes = {n: sha(b) for n, b in raw.items()}
        check(manifest == {n: h for n, h in hashes.items() if n != "manifest.json"}, "C_raw_exact_five_manifest_hashes")
        check(metadata["source_commit"] == commit and metadata["source_status"] == "" and metadata["source_dirty"] is False,
              "C_original_clean_root_fixed_source_commit")
        protocol = metadata["protocol"]; check(protocol["path"] == PROTOCOL, "C_original_protocol_path")
        audit_blob = copy("first_audit.json", ROOT / "external/guard_exploration_20261011_first_audit.json", "original_first_C_stdlib_audit")
        audit = parsed(audit_blob); archive = audit["archive"]
        check(audit["failed"] == 0, "C_original_first_audit_integrity_succeeded")
        check(archive["input_hashes"] == hashes, "C_first_audit_exact_six_raw_binding")
        check(archive["episodes"] == episodes, "C_first_audit_original_episode_binding")
        check(audit["execution"]["source_git_verification_enabled"] is True, "C_first_audit_preexisting_source_Git_verification")
        first_source_verification = {"original_execution": audit["execution"],
            "verified_source_git_blobs": audit.get("verified_source_git_blobs", audit["execution"].get("verified_source_git_blobs")),
            "source_commit": commit, "source_sha256": metadata["source_sha256"], "archival_Git_queries": 0,
            "scope": "Preserves first-audit source verification; no new Git verification or invented blob counter"}
        for name, path in EXECUTION_INPUTS.items(): copy(name, ROOT / path, "original_C_execution_wrapper_stdout_or_postprocess")
        first = parsed(cache["external/guard_exploration_20261011_first_execution.json"])
        check(first["source_commit"] == commit and first["repeated"] is False, "C_original_execution_not_repeated")
        post = parsed(cache["external/guard_exploration_20261011_postprocess_execution.json"])
        check(len(post["executions"]) == 2 and all(r["repeated"] is False for r in post["executions"]),
              "C_first_audit_and_once_summary_original_wrapper")
        summary_bytes = {}
        for path in sorted(SUMMARY_DIR.rglob("*")):
            if path.is_file():
                name = path.relative_to(SUMMARY_DIR).as_posix()
                summary_bytes[name] = copy("summary_once/" + name, path, "original_once_C_descriptive_summary")
        sx, summary = parsed(summary_bytes["execution.json"]), parsed(summary_bytes["summary.json"])
        check(sx["exit_code"] == 0 and sx["binding_checks"]["failed"] == 0, "C_original_once_summary_success")
        check(sha(summary_bytes["tool_source.py"]) == SUMMARY_SHA == sx["tool_sha256"], "C_once_summary_frozen_tool_identity")
        check(all(sx[k] == 0 for k in ("physical_calls", "model_updates", "body_predictions", "audit_executions", "git_queries")),
              "C_once_summary_zero_new_model_or_physics")
        for name, expected in sx["output_sha256"].items():
            check(files["summary_once/" + name]["sha256"] == expected, "C_summary_output_SHA/" + name)
        check(summary["original_input_sha256"] == hashes and summary["existing_first_audit_sha256"] == sha(audit_blob),
              "C_once_summary_original_seven_input_identity")
        check(summary["expected_auditor_sha256"] == AUDITOR_SHA, "C_summary_root_explicit_auditor_SHA")
        check(summary["scientific_gates_from_first_audit"] == audit["final_gates"], "C_original_scientific_gates_preserved_exactly")
        check(summary["scientific_gates_recomputed"] is False and summary["control_ranking_computed"] is False,
              "C_summary_no_gate_recompute_or_truncated_ranking")
        reads = parsed(summary_bytes["read_cost.json"])["original_inputs"]
        check(set(reads) == RAW_NAMES | {"first_audit"} and all(r["read_attempts"] == r["successful_reads"] == 1 for r in reads.values()),
              "C_once_summary_original_seven_inputs_read_once")
        copy("summary_once/stdout.txt", ROOT / "external/guard_exploration_20261011_summary_01_stdout.txt", "original_C_summary_stdout")
        check(metadata["source_snapshot_sha256"] == hashes["source_snapshot.zip"], "C_source_ZIP_original_identity")
        with zipfile.ZipFile(io.BytesIO(raw["source_snapshot.zip"])) as source:
            names = source.namelist()
            check(len(names) == len(set(names)) and set(names) == set(metadata["source_sha256"]), "C_source_unique_exact_coverage")
            pd_metadata_blob = source.read(PD_ROOT + "raw/metadata.json")
            pd_metadata = parsed(pd_metadata_blob)
            pd_original_sources = pd_metadata["source_sha256"]
            for name in names:
                if not safe(name): raise ValueError("Unsafe original C source member: " + name)
                blob = pd_metadata_blob if name == PD_ROOT + "raw/metadata.json" else source.read(name)
                check(sha(blob) == metadata["source_sha256"][name], "C_source_SHA/" + name)
                if name.startswith(PD_ROOT): kind = "embedded_original_selected_PD_identity_evidence"
                elif name.startswith("results/"): kind = "embedded_prior_evidence_snapshot"
                elif name in pd_original_sources and sha(blob) == pd_original_sources[name]: kind = "shared_C_PD_frozen_source_bytes"
                else: kind = "current_C_frozen_source_snapshot_bytes"
                identity = {"kind": kind, "C_source_commit_verified_by_first_audit": commit,
                    "Git_reverified_by_archival_tool": False}
                classifications[name] = identity
                store("frozen_source/" + name, blob, kind, "Original C source_snapshot.zip member " + name,
                      **{k: v for k, v in identity.items() if k != "kind"})
        check(protocol["sha256"] == files["frozen_source/" + PROTOCOL]["sha256"], "C_protocol_frozen_source_SHA")
        check(audit["audit_script_sha256"] == AUDITOR_SHA == files["frozen_source/" + AUDITOR]["sha256"], "C_executing_auditor_source_SHA")
        for name, expected in audit["audit_dependency_sha256"].items():
            check(files["frozen_source/" + name]["sha256"] == expected, "C_executing_support_identity/" + name)
        pd_binding = metadata["pd_binding"]
        check(summary["PD_original_identity_binding"] == pd_binding, "C_summary_original_embedded_PD_binding")
        check(set(pd_binding["source_records"]) == {PD_ROOT + n for n in PD_NAMES}, "C_embedded_PD_five_original_identities")
        for name, expected in pd_binding["source_records"].items():
            check(files["frozen_source/" + name]["sha256"] == expected, "C_embedded_PD_original_SHA/" + name)
        paid = {k: sum(ep[k] for ep in episodes) for k in KEYS}
        check(all(paid[k] == metadata[k] == archive["budget"][k] for k in KEYS), "C_original_paid_physical_ledger_binding")
        check(summary["C_new_paid_physical_budget"] == paid, "C_summary_original_physical_budget_binding")
        updates = summary["C_new_online_calibration_updates"]
        check(all(updates[k] == metadata[k] == archive["budget"][k] for k in ("model_updates", "vector_model_updates")),
              "C_new_online_calibration_updates_binding")
        check(updates["offline_replay_updates"] == updates["control_or_prediction_updates"] == 0,
              "C_original_calibration_not_offline_replay_or_control_learning")
        check(updates["maximum_scalar_updates"] == 4800 and updates["maximum_vector_updates"] == 2400,
              "C_original_online_update_caps_preserved")
        all_completed = len(episodes) == 24 and all(ep["status"] == "completed" for ep in episodes)
        check(metadata["all_trials_successful"] is all_completed, "C_original_all_24_statuses_successful_flag")
        original_outcomes = {"statuses": summary["statuses"], "all_trials_successful": metadata["all_trials_successful"],
            "matrix_complete_from_first_audit": audit["final_gates"]["matrix_complete"],
            "distinction": "All24 completed statuses is separate from audited matrix completeness including minimum excitation",
            "scientific_gates_from_first_audit": audit["final_gates"], "phase_paid_budget": summary["phase_total_paid_budget"],
            "paid_pair_prediction_attempts": archive["paid_pair_prediction_attempts"]}
        accounting = {"prior_formal_control_calls": 239120, "this_C_control_calls": paid["control_calls_attempted"],
            "formal_control_calls": 239120 + paid["control_calls_attempted"], "prior_formal_control_steps": 239120,
            "this_C_control_steps": paid["control_steps"], "formal_control_steps": 239120 + paid["control_steps"],
            "formal_physics_substeps": 2391200 + paid["physics_steps"],
            "prior_online_scalar_model_updates": 17652, "this_C_online_scalar_updates": metadata["model_updates"],
            "online_scalar_model_updates": 17652 + metadata["model_updates"], "prior_B_offline_scalar_updates": 2400,
            "this_C_offline_scalar_updates": 0, "total_algorithm_scalar_updates_including_offline": 20052 + metadata["model_updates"]}
        for source_dir, destination in (
            (ROOT / 'external/c4_guard_exploration_staging/domain_diagnostics/actual_C_readonly_01', 'saved_domain_diagnostic'),
            (ROOT / 'external/guard_exploration_covariance_01', 'saved_covariance_algebra'),
        ):
            check(source_dir.is_dir(), 'original_saved_diagnostic_exists/' + destination)
            for path in sorted(source_dir.iterdir()):
                if path.is_file():
                    copy(destination + '/' + path.name, path, 'original_development_diagnostic_without_refitting_or_new_predictions')
        buffer, bundle_members, paths = io.BytesIO(), {}, []
        for dirname in STAGES:
            directory = ROOT / "external" / dirname; check(directory.is_dir(), "C_preparation_stage_exists/" + dirname)
            paths.extend((dirname + "/" + p.relative_to(directory).as_posix(), p) for p in sorted(directory.rglob("*"))
                         if p.is_file() and "__pycache__" not in p.parts)
        paths.extend(("loose/" + name, ROOT / "external" / name) for name in LOOSE)
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
            for name, path in paths:
                if not safe(name): raise ValueError("Unsafe C preparation bundle member: " + name)
                blob = read(path); bundle.writestr(name, blob)
                bundle_members[name] = {"source": path.relative_to(ROOT).as_posix(), "bytes": len(blob), "sha256": sha(blob)}
        blob = buffer.getvalue()
        store("staging_evidence.zip", blob, "all_C_preparation_attempts_and_C5_prospective_clone_handmade_materials",
              "C runner/auditor/summary stages, all failures/fake engineering/preflight01+02, C5 design/clone; excludes transient __pycache__")
        with zipfile.ZipFile(io.BytesIO(blob)) as bundle:
            check(len(bundle.namelist()) == len(set(bundle.namelist())) == len(bundle_members), "C_preparation_bundle_unique_exact_coverage")
            for name in bundle.namelist(): check(sha(bundle.read(name)) == bundle_members[name]["sha256"], "C_preparation_bundle_member_SHA/" + name)
        for required in ("c4_guard_exploration_staging/production_preflight_01/result.json",
                         "c4_guard_exploration_staging/production_preflight_02/result.json",
                         "c5_adaptation_design_staging/C5_ADAPTATION_PROSPECTIVE_PROTOCOL.md",
                         "c5_adaptation_core_staging/attempt01/execution.json"):
            check(required in bundle_members, "C_original_preflight_and_C5_preparation_preserved/" + required)
        bundles["staging_evidence.zip"] = {"member_count": len(bundle_members), "bytes": len(blob), "sha256": sha(blob),
            "members": bundle_members, "initial_and_failed_attempts_preserved": True,
            "C5_material_claim_boundary": "Prospective design and clone handmade mathematics only, not scientific adaptation or new C physical evidence"}
    except BaseException as exc:
        error = {"type": type(exc).__name__, "message": str(exc)}
    finally:
        check(Path(__file__).read_bytes() == own, "C_archival_tool_unchanged")
        record = {"created_at_utc": datetime.now(timezone.utc).isoformat(), "source_commit": commit, "protocol": protocol,
            "files": files, "bundles": bundles, "input_hashes": input_hashes, "source_classification": classifications,
            "first_source_verification_preserved": first_source_verification, "original_C_outcomes": original_outcomes,
            "verification": {"checks": count, "failed": len(violations), "violations": violations, "exception": error},
            "cumulative_accounting": accounting, "source_provenance": {"source": "Cached original C source ZIP",
                "prior_PD": "Embedded original identities, not regenerated working-tree content",
                "archival_Git_queries": 0, "archival_current_worktree_source_reads": 0},
            "execution": {"python": sys.version, "wall_seconds": time.perf_counter()-wall, "cpu_seconds": time.process_time()-cpu,
                "exit_code": int(bool(violations) or error is not None), "physical_calls": 0, "model_updates": 0,
                "new_predictions": 0, "audit_executions": 0, "summary_executions": 0, "git_queries": 0},
            "manifest_self_hash_excluded": True,
            "claim_boundary": "Byte integrity only; original C gates/outcomes untouched; stopped scores never ranked; C5 materials are preparation."}
        with (OUTPUT / "manifest.json").open("xb") as out: out.write(encoded(record))
    print(json.dumps({"output": str(OUTPUT), "files": len(files), "checks": count, "failed": len(violations), "exception": error,
        "manifest_sha256": sha((OUTPUT / "manifest.json").read_bytes()), "execution": record["execution"]}))
    return record["execution"]["exit_code"]


if __name__ == "__main__": raise SystemExit(main())
