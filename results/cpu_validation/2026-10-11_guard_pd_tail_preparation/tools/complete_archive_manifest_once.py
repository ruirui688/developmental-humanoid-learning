"""Finish only failed preparation-manifest schema checks; never recopy payloads."""
from pathlib import Path
import hashlib
import json
import time


BASE = Path(__file__).resolve().parents[1]
PRIOR_MANIFEST_SHA = "bd0674c731ae704598defd6097b7020c11af8809379e290050de66c1bcdbfcd8"


def main():
    started_wall, started_cpu = time.perf_counter(), time.process_time()
    if (BASE/"archive_attempt_01").exists():
        raise FileExistsError("one-attempt recovery must not repeat")
    fee = {"copied_record_opens": 0, "copied_record_binary_bytes_read": 0,
           "hash_operations": 0, "original_payload_reads": 0, "payload_recopies": 0,
           "model_calls": 0, "mathematical_replays": 0, "physical_queries": 0,
           "actual_E_C_D_F_reads": 0, "git_calls": 0}
    def read(name):
        blob = (BASE/name).read_bytes()
        fee["copied_record_opens"] += 1;fee["copied_record_binary_bytes_read"] += len(blob)
        identity = hashlib.sha256(blob).hexdigest();fee["hash_operations"] += 1
        return blob, {"bytes": len(blob), "sha256": identity}
    manifest_blob, manifest_record = read("manifest.json")
    if manifest_record["sha256"] != PRIOR_MANIFEST_SHA:
        raise ValueError("first failed manifest identity differs")
    prior = json.loads(manifest_blob)
    execution_blob, execution_record = read("archive_execution.json")
    execution = json.loads(execution_blob)
    assert prior["status"] == execution["status"] == "exception"
    assert execution["copied_file_count"] == 79
    copied_bytes = sum(item["bytes"] for item in execution["source_inventory"])
    assert execution_record == prior["files"]["archive_execution.json"]
    assert execution["exception"]["message"] == "expected sealed files list or mapping in auditor_staging/INTEGRITY.json"
    records = dict(prior["files"])
    checked = list(prior["checked_sealed_manifests"])
    assert checked == [{"path": "runner_staging/INTEGRITY.json", "payloads_checked": 20,
                        "failed": 0, "parsed_from_source_copy_memory": True}]
    for alias in ("auditor_staging", "limited_static_review", "first_execution_wrappers", "summary_tools"):
        name = alias+"/INTEGRITY.json"
        blob, identity = read(name)
        assert identity == records[name]
        doc = json.loads(blob)
        entries = doc.get("files", doc.get("payloads")) if isinstance(doc, dict) else doc
        if isinstance(entries, dict):
            entries = [{"path": path, **entry} for path, entry in entries.items()]
        if not isinstance(entries, list):
            raise ValueError("sealed file/payload list or mapping required: "+name)
        count = 0
        for entry in entries:
            relative = entry.get("path", entry.get("name"))
            if not isinstance(relative, str):
                raise ValueError("sealed payload path missing: "+name)
            item = records[alias+"/"+relative]
            expected_bytes = entry.get("bytes", entry.get("size_bytes", entry.get("binary_bytes")))
            assert item["sha256"] == entry["sha256"]
            assert expected_bytes is None or item["bytes"] == expected_bytes
            count += 1
        checked.append({"path": name, "payloads_checked": count, "failed": 0,
                        "scope": "only copied manifest parsed; raw copy identities reused from first attempt"})
    attempt = BASE/"archive_attempt_01"
    attempt.resolve().relative_to(BASE.resolve());attempt.mkdir()
    for name in ("manifest.json", "archive_execution.json"):
        source = (BASE/name).resolve();destination = (attempt/name).resolve()
        source.relative_to(BASE.resolve());destination.relative_to(BASE.resolve())
        source.rename(destination)
    records["archive_attempt_01/archive_execution.json"] = records.pop("archive_execution.json")
    records["archive_attempt_01/manifest.json"] = manifest_record
    for name in ("tools/archive_preparation_once.py", "tools/complete_archive_manifest_once.py", "archive_schema_inspection.json"):
        _, identity = read(name);records[name] = identity
    result = {"status": "completed", "first_attempt_status": "exception",
              "first_attempt_exception": execution["exception"], "first_manifest_sha256": PRIOR_MANIFEST_SHA,
              "copied_file_count": 79, "copied_payload_bytes": copied_bytes,
              "reused_successful_copy_verifications": 79, "reused_runner_manifest_checks": 20,
              "new_manifest_schemas_supported": ["files", "payloads", "list"],
              "checked_sealed_manifests": checked, "explicit_recovery_fee": fee,
              "wall_seconds": time.perf_counter()-started_wall, "cpu_seconds": time.process_time()-started_cpu,
              "timing_scope": "copied record parsing, necessary remaining manifest checks and failure preservation; excludes final record/manifest writing",
              "first_copy_fee": prior["copy_fee"], "first_final_record_fee": prior["final_execution_record_fee"],
              "first_manifest_write_bytes": len(manifest_blob), "prior_schema_inspection_fee": {
                  "copied_manifest_opens": 1, "binary_bytes": 1606, "hash_operations": 0},
              "physics_or_learning_executed": False}
    result_blob = (json.dumps(result, indent=2, ensure_ascii=False)+"\n").encode("utf-8")
    with (BASE/"archive_execution.json").open("xb") as writer:writer.write(result_blob)
    records["archive_execution.json"] = {"bytes": len(result_blob), "sha256": hashlib.sha256(result_blob).hexdigest()}
    final = {"schema_version": 1, "status": "completed", "archive_kind": "G engineering preparation originals",
             "files": records, "payload_count": len(records), "payload_bytes": sum(item["bytes"] for item in records.values()),
             "copied_file_count": 79, "copied_payload_bytes": copied_bytes,
             "first_attempt_status": "exception", "first_attempt_preserved": True,
             "checked_sealed_manifests": checked, "reused_successful_copy_verifications": 79,
             "first_copy_fee": prior["copy_fee"], "recovery_fee": fee,
             "recovery_final_record_fee": {"write_opens": 1, "bytes_written": len(result_blob), "in_memory_hash_operations": 1},
             "physics_or_learning_executed": False, "draft_and_production_sources_are_separately_disclosed": True}
    final_blob = (json.dumps(final, indent=2, ensure_ascii=False)+"\n").encode("utf-8")
    with (BASE/"manifest.json").open("xb") as writer:writer.write(final_blob)
    print(json.dumps({"manifest": str(BASE/"manifest.json"), "manifest_sha256": hashlib.sha256(final_blob).hexdigest(),
                      "manifest_bytes": len(final_blob), "payload_count": len(records), "payload_bytes": final["payload_bytes"],
                      "copied_file_count": 79, "raw_payload_recopies": 0, "first_attempt_preserved": True,
                      "recovery_fee": fee, "final_record_write_bytes": len(result_blob),
                      "final_in_memory_hash_operations": 2}, indent=2))


if __name__ == "__main__":
    main()
