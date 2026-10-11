"""Copy sealed G engineering originals only; no runner/audit/model execution."""
from pathlib import Path
import hashlib
import json
import time
import traceback


ROOT = Path(__file__).resolve().parents[4]
OUTPUT = ROOT/"results/cpu_validation/2026-10-11_guard_pd_tail_preparation"
DIRECTORIES = (
    ("external/c4_pd_tail_mpc_staging", "planner_staging"),
    ("external/c4_pd_tail_control_runner_staging", "runner_staging"),
    ("external/c4_pd_tail_control_audit_staging", "auditor_staging"),
    ("external/c4_pd_tail_api_review_staging", "api_review"),
    ("external/c4_pd_tail_control_review_staging", "limited_static_review"),
    ("external/c4_pd_tail_protocol_staging", "protocol_draft"),
    ("external/c4_g_first_wrapper_staging", "first_execution_wrappers"),
    ("external/c4_g_summary_tools_staging", "summary_tools"),
)
SINGLES = (
    ("external/verify_guard_native_result_once.py", "f_postdelivery/verify_guard_native_result_once.py"),
    ("external/c4_f_result_delivery_01.json", "f_postdelivery/c4_f_result_delivery_01.json"),
    ("external/c4_g_promotion_01/promotion.json", "promotion/promotion.json"),
    ("external/c4_g_promotion_01/promotion_source.py", "promotion/promotion_source.py"),
    ("docs/GUARD_PD_TAIL_CONTROL_DEVELOPMENT_PROTOCOL.md", "production_protocol_snapshot.md"),
    ("external/archive_guard_pd_tail_control_once.py", "tools/archive_guard_pd_tail_control_once.py"),
)
FROZEN = {
    "planner_staging/pd_tail_pair_mpc.py": "6d1af186eb02e033a31fcc294eedd38fa743a418a69d16744350fa02aec3beed",
    "runner_staging/pd_tail_control_development.py": "47407917ff7ac184ab7f0859a6fb63d30946805e3ad23cc4268d3eae4b115720",
    "auditor_staging/audit_guard_pd_tail_control.py": "38322b00e04782a640f989ddc568d06e27c6fc8e5e18b68bfe0f9807cf38483a",
    "protocol_draft/G_PROTOCOL_DRAFT.md": "e69d1453d3d70a37e9685f593f7ff6da182fbd3bb471b145a3c4d475e8a56167",
    "first_execution_wrappers/run_pd_tail_control_once.py": "1bbcb4bd8d1dbb15c86c729a6d0c0e576e00c2673ac0a3604396b646de92775e",
}


def digest(blob):
    return hashlib.sha256(blob).hexdigest()


def safe_archive_name(name):
    path = Path(name)
    if not isinstance(name, str) or not name or path.is_absolute() or ".." in path.parts or ":" in name or "\\" in name:
        raise ValueError("archive name must remain inside the preparation root")
    target = (OUTPUT/path).resolve()
    target.relative_to(OUTPUT.resolve())
    return target


def write_exclusive(path, blob):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as writer:
        writer.write(blob)


def main():
    if (OUTPUT/"manifest.json").exists() or (OUTPUT/"archive_execution.json").exists():
        raise FileExistsError("one-attempt preparation archive must not have prior final records")
    started_wall, started_cpu = time.perf_counter(), time.process_time()
    fee = {"source_opens": 0, "source_binary_bytes_read": 0, "destination_verification_opens": 0,
           "destination_binary_bytes_read": 0, "payload_write_opens": 0, "payload_binary_bytes_written": 0,
           "hash_operations": 0, "helper_source_opens": 0, "helper_source_binary_bytes_read": 0,
           "model_calls": 0, "physical_queries": 0, "mathematical_replays": 0, "actual_E_C_D_F_reads": 0,
           "fixture_reexecutions": 0, "parameter_updates": 0, "git_calls": 0}
    records, blobs, inventory, skipped, checked_manifests = {}, {}, [], [], []
    run = {"status": "started", "operation": "sealed G engineering original-byte copy only",
           "source_directory_aliases": list(DIRECTORIES), "explicit_single_sources": list(SINGLES),
           "no_actual_experiment_payloads": True, "scope": "all declared source/destination/helper content reads; excludes interpreter/import reads and final generated record/manifest serialization"}
    try:
        plans = []
        for directory, alias in DIRECTORIES:
            base = (ROOT/directory).resolve()
            base.relative_to(ROOT.resolve())
            if not base.is_dir():
                raise FileNotFoundError("sealed directory not delivered: "+directory)
            for source in sorted(base.rglob("*")):
                if not source.is_file():
                    continue
                relative = source.relative_to(base).as_posix()
                if "__pycache__" in source.relative_to(base).parts or source.suffix == ".pyc":
                    skipped.append({"source": source.relative_to(ROOT).as_posix(), "bytes": source.stat().st_size,
                                    "reason": "unsealed interpreter cache; no content read"})
                    continue
                plans.append((source, alias+"/"+relative, directory))
        for source_name, archive_name in SINGLES:
            source = (ROOT/source_name).resolve();source.relative_to(ROOT.resolve())
            if not source.is_file():
                raise FileNotFoundError(source_name)
            plans.append((source, archive_name, "explicit_single"))
        if len({name for _, name, _ in plans}) != len(plans):
            raise ValueError("duplicate archive destination")
        for source, name, group in plans:
            target = safe_archive_name(name)
            fee["source_opens"] += 1
            blob = source.read_bytes();fee["source_binary_bytes_read"] += len(blob)
            identity = digest(blob);fee["hash_operations"] += 1
            if name in FROZEN and identity != FROZEN[name]:
                raise ValueError("sealed source identity changed: "+name)
            write_exclusive(target, blob)
            fee["payload_write_opens"] += 1;fee["payload_binary_bytes_written"] += len(blob)
            fee["destination_verification_opens"] += 1
            copied = target.read_bytes();fee["destination_binary_bytes_read"] += len(copied)
            copied_sha = digest(copied);fee["hash_operations"] += 1
            if copied != blob or copied_sha != identity:
                raise ValueError("destination byte copy differs: "+name)
            records[name] = {"sha256": identity, "bytes": len(blob)}
            blobs[name] = blob
            inventory.append({"source": source.relative_to(ROOT).as_posix(), "destination": name,
                              "group": group, "bytes": len(blob), "sha256": identity})
        for directory, alias in DIRECTORIES:
            name = alias+"/INTEGRITY.json"
            if name not in blobs:
                continue
            manifest = json.loads(blobs[name])
            entries = manifest.get("files")
            if isinstance(entries, dict):
                entries = [{"path": path, **entry} for path, entry in entries.items()]
            if not isinstance(entries, list):
                raise ValueError("expected sealed files list or mapping in "+name)
            matched = 0
            for entry in entries:
                relative = entry.get("path", entry.get("name"))
                if not isinstance(relative, str):
                    raise ValueError("sealed payload path missing in "+name)
                if relative.startswith(directory+"/"):
                    relative = relative[len(directory)+1:]
                archived = alias+"/"+relative
                if archived not in records:
                    raise ValueError("sealed payload absent from copy: "+archived)
                expected_bytes = entry.get("bytes", entry.get("size_bytes", entry.get("binary_bytes")))
                if records[archived]["sha256"] != entry["sha256"] or (expected_bytes is not None and records[archived]["bytes"] != expected_bytes):
                    raise ValueError("sealed payload manifest identity differs: "+archived)
                matched += 1
            checked_manifests.append({"path": name, "payloads_checked": matched, "failed": 0,
                                      "parsed_from_source_copy_memory": True})
        helper = Path(__file__).resolve();fee["helper_source_opens"] += 1
        helper_blob = helper.read_bytes();fee["helper_source_binary_bytes_read"] += len(helper_blob)
        helper_name = helper.relative_to(OUTPUT).as_posix()
        records[helper_name] = {"sha256": digest(helper_blob), "bytes": len(helper_blob)}
        fee["hash_operations"] += 1
        run.update(status="completed", copied_file_count=len(inventory), copied_payload_bytes=sum(item["bytes"] for item in inventory),
                   source_inventory=inventory, skipped_interpreter_caches=skipped,
                   checked_sealed_manifests=checked_manifests, frozen_source_checks=FROZEN,
                   protocol_snapshots={"draft": records["protocol_draft/G_PROTOCOL_DRAFT.md"],
                                       "production": records["production_protocol_snapshot.md"]})
    except BaseException as exc:
        run.update(status="exception", exception={"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()},
                   copied_file_count=len(inventory), source_inventory=inventory, skipped_interpreter_caches=skipped)
        raise
    finally:
        run.update(explicit_copy_fee=fee, wall_seconds=time.perf_counter()-started_wall,
                   cpu_seconds=time.process_time()-started_cpu,
                   timing_scope="inventory, original-byte copy, destination verification and in-memory source-manifest checking; excludes final run/manifest writing")
        run_blob = (json.dumps(run, indent=2, ensure_ascii=False, allow_nan=False)+"\n").encode("utf-8")
        write_exclusive(OUTPUT/"archive_execution.json", run_blob)
        records["archive_execution.json"] = {"sha256": digest(run_blob), "bytes": len(run_blob)}
        final_fee = {"generated_execution_write_opens": 1, "generated_execution_binary_bytes_written": len(run_blob),
                     "generated_execution_in_memory_hash_operations": 1,
                     "scope": "final execution record serialized once and hash from the same in-memory bytes; no extra source reads"}
        manifest = {"schema_version": 1, "status": run["status"], "archive_kind": "G engineering preparation originals",
                    "files": records, "payload_count": len(records), "payload_bytes": sum(item["bytes"] for item in records.values()),
                    "copy_fee": fee, "final_execution_record_fee": final_fee,
                    "checked_sealed_manifests": checked_manifests, "physics_or_learning_executed": False,
                    "draft_and_production_sources_are_separately_disclosed": True}
        manifest_blob = (json.dumps(manifest, indent=2, ensure_ascii=False, allow_nan=False)+"\n").encode("utf-8")
        write_exclusive(OUTPUT/"manifest.json", manifest_blob)
        print(json.dumps({"status": run["status"], "manifest_sha256": digest(manifest_blob),
                          "manifest_bytes": len(manifest_blob), "manifest_in_memory_receipt_hash_operations": 1,
                          "copied_file_count": len(inventory), "payload_count": len(records),
                          "copy_fee": fee, "final_execution_record_fee": final_fee,
                          "manifest_write_opens": 1, "manifest_binary_bytes_written": len(manifest_blob)}, indent=2))


if __name__ == "__main__":
    main()
