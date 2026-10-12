"""Prepare the frozen FR4D protocol and source archive once, only when explicitly run.

No experiment payload, model, metric, fixture, or production module is opened.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
import traceback


ARCHIVE_RELATIVE = "results/cpu_validation/2026-10-12_pd_anchor_selection_preparation"
DOC_RELATIVE = "docs/PD_ANCHOR_SELECTION_DIAGNOSTIC_PROTOCOL.md"
START_RELATIVE = "external/fr4d_preparation_freeze_first_started.json"
FAILURE_RELATIVE = "external/fr4d_preparation_freeze_first_failure.json"
FINAL_PROTOCOL_RELATIVE = "external/fr4_selection_diagnostic_protocol_candidate.md"
SOURCE_PINS = {
    FINAL_PROTOCOL_RELATIVE: (11109, "8075b168b5037fff11e03047e224e56c4e5b3f63ea19d1bdc6e7bfbcc67c0b1a"),
    "external/fr4_selection_diagnostic_protocol_candidate.before_saved_field_budget.md":
        (10115, "70cb23d755a9a8cf300d78d797ca401e9763db8273ce0cf926cc37abd658fda3"),
    "external/fr4_selection_diagnostic_candidate/project_saved_pd_anchor_selection_once.py":
        (19311, "e0cce0111b05c5b5e9514d38f5095b9dff922dfeddec226848426acf5fd44322"),
    "external/fr4_selection_diagnostic_candidate/run_saved_selection_projection_first_once.py":
        (3126, "c6475566eef013323589c64de249dc714471d111adb0b4deec4da6b8575ecadf"),
    "external/fr4_selection_diagnostic_candidate/SCHEMA_AND_BUDGET.md":
        (4710, "11d18ea66a1a5fd84fd1c98411aa88b5ab4d89089904049f0fd7a3418b34f7ae"),
    "external/fr4_selection_diagnostic_candidate/preparation_receipt.json":
        (2795, "3ee4a91534702ff95b3fc319d90e556d3693bebb7ca477478d8619d655d8c12a"),
    "external/fr4_selection_diagnostic_candidate/first_static_scope_gap_source.py":
        (18353, "b7951b5ccbc2b59155565316147fccfe255c248c0e1c217d402e7c69c8b074f7"),
    "external/fr4_selection_diagnostic_candidate/first_schema_and_budget.md":
        (4196, "542e1b3e22d44fddb6c3273d2ef39660b0bd0c2590a1ab46ac0a8c3b776aa019"),
    "external/fr4_selection_diagnostic_candidate/first_preparation_receipt.json":
        (2059, "1b20061f4ed1296911cd020f2ad0c7f1cb0565943c136db6235fdae4ba46d0a7"),
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def identity(data):
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def write_bytes_once(path, data):
    with path.open("xb") as stream:
        written = stream.write(data)
        require(written == len(data), "short_source_copy:"+str(path))


def write_json_once(path, value):
    data = (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+"\n").encode("utf-8")
    write_bytes_once(path, data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".")
    parser.add_argument("--execute-freeze", action="store_true", help="Explicitly perform this one frozen source copy.")
    args = parser.parse_args()
    if not args.execute_freeze:
        parser.error("--execute-freeze is required; no files were changed")
    repo = Path(args.repo).resolve()
    archive, document = repo/ARCHIVE_RELATIVE, repo/DOC_RELATIVE
    started_path, failure_path = repo/START_RELATIVE, repo/FAILURE_RELATIVE
    wall, cpu = time.perf_counter(), time.process_time()
    source_reads_attempted, source_reads_returned, source_bytes = 0, 0, 0
    source_identities, copied_files, first_failure = {}, {}, None
    started = False
    try:
        require(repo.is_dir(), "repository_directory_required")
        for destination in (archive, document, started_path, failure_path):
            require(destination.resolve().is_relative_to(repo), "fixed_destination_outside_repository")
            require(not destination.exists(), "fresh_destination_required:"+str(destination))
        require(document.parent.is_dir() and started_path.parent.is_dir(), "existing_docs_and_external_directories_required")
        write_json_once(started_path, {
            "schema": "fr4d_preparation_freeze_first_started_v1",
            "started_utc": datetime.now(timezone.utc).isoformat(),
            "archive": ARCHIVE_RELATIVE, "document": DOC_RELATIVE,
            "automatic_retry": False, "explicit_execute_freeze": True,
        })
        started = True
        buffers = {}
        for relative, (expected_bytes, expected_sha256) in SOURCE_PINS.items():
            source = (repo/relative).resolve()
            require(source.is_relative_to(repo) and source.is_file(), "fixed_source_file_required:"+relative)
            source_reads_attempted += 1
            data = source.read_bytes()
            source_reads_returned += 1
            source_bytes += len(data)
            actual = identity(data)
            require(actual == {"bytes": expected_bytes, "sha256": expected_sha256}, "fixed_source_pin_differs:"+relative)
            source_identities[relative], buffers[relative] = actual, data
        own_source = Path(__file__).resolve()
        require(own_source == (repo/"external/freeze_fr4d_preparation_once.py").resolve(), "fixed_archival_script_location_required")
        source_reads_attempted += 1
        own_bytes = own_source.read_bytes()
        source_reads_returned += 1
        source_bytes += len(own_bytes)
        source_identities["external/freeze_fr4d_preparation_once.py"] = identity(own_bytes)
        archive.mkdir(parents=True, exist_ok=False)
        artifacts = archive/"artifacts"
        artifacts.mkdir(exist_ok=False)
        for relative, data in buffers.items():
            name = "PD_ANCHOR_SELECTION_DIAGNOSTIC_PROTOCOL.md" if relative == FINAL_PROTOCOL_RELATIVE else Path(relative).name
            destination = artifacts/name
            write_bytes_once(destination, data)
            copied_files[destination.relative_to(repo).as_posix()] = identity(data)
        write_bytes_once(artifacts/own_source.name, own_bytes)
        copied_files[(artifacts/own_source.name).relative_to(repo).as_posix()] = identity(own_bytes)
        write_bytes_once(document, buffers[FINAL_PROTOCOL_RELATIVE])
        copied_files[DOC_RELATIVE] = identity(buffers[FINAL_PROTOCOL_RELATIVE])
        manifest = {
            "schema": "fr4d_preparation_freeze_manifest_v1", "status": "frozen_source_copy_complete",
            "eligibility_from_published_FR4B": {
                "source_commit": "490fcffa0080125e7c2a8b887c99cc2743dcc01f",
                "published_checkpoint": "3b0f7e0a3869c0b3ef89e9f93dacf0ecf7081cab",
                "report": "docs/PD_ANCHOR_PAIR_CONTROL_RESULTS.md",
                "model_contribution_passed": True, "PD_reference_passed": False,
                "identity_source": "root transcribed published first result; no gate recalculation",
                "grid_family_closed_after_single_projection": True,
            },
            "explicit_execute_freeze": True, "automatic_retry": False,
            "document": DOC_RELATIVE, "source_pins": source_identities, "copied_files": copied_files,
            "historical_preparation_protocol_identity": {
                "bytes": 10115, "sha256": "70cb23d755a9a8cf300d78d797ca401e9763db8273ce0cf926cc37abd658fda3",
                "meaning": "Both historical preparation receipts retain their original protocol declaration; neither was rewritten.",
            },
            "final_protocol_identity": source_identities[FINAL_PROTOCOL_RELATIVE],
            "runtime_tool_location": "external/fr4_selection_diagnostic_candidate/project_saved_pd_anchor_selection_once.py",
            "source_read_attempts": source_reads_attempted, "source_read_returns": source_reads_returned,
            "source_read_bytes": source_bytes, "copied_file_count": len(copied_files),
            "experiment_payload_metric_model_reads": 0, "physics_model_fit_RLS_calls": 0,
            "diagnostic_fixture_test_or_audit_executions": 0, "production_or_navigation_writes": 0,
            "first_failure": None, "wall_seconds_before_manifest": time.perf_counter()-wall,
            "cpu_seconds_before_manifest": time.process_time()-cpu,
        }
        write_json_once(archive/"freeze_manifest.json", manifest)
    except BaseException as exc:
        first_failure = {
            "schema": "fr4d_preparation_freeze_first_failure_v1", "status": "failed",
            "type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc(),
            "started_marker_created": started, "source_read_attempts": source_reads_attempted,
            "source_read_returns": source_reads_returned, "source_read_bytes": source_bytes,
            "source_pins_observed_before_failure": source_identities, "copied_files_before_failure": copied_files,
            "automatic_retry": False, "experiment_payload_metric_model_reads": 0,
            "physics_model_fit_RLS_calls": 0, "diagnostic_fixture_test_or_audit_executions": 0,
        }
        if failure_path.resolve().is_relative_to(repo) and failure_path.parent.is_dir() and not failure_path.exists():
            write_json_once(failure_path, first_failure)
    print(json.dumps({"status": "failed" if first_failure else "frozen_source_copy_complete",
                      "archive": str(archive), "document": str(document),
                      "source_read_attempts": source_reads_attempted, "source_read_returns": source_reads_returned,
                      "source_read_bytes": source_bytes, "copied_file_count": len(copied_files),
                      "first_failure": first_failure}, ensure_ascii=False, allow_nan=False))
    return int(first_failure is not None)


if __name__ == "__main__":
    raise SystemExit(main())
