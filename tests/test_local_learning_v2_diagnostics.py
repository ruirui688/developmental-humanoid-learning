"""Refusal and portability tests for read-only secondary diagnostics."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "summarize_local_learning_v2_diagnostics.py"
spec = importlib.util.spec_from_file_location("public_v2_diagnostics", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def fixture_archive(tmp_path):
    path = tmp_path / "copied_archive"
    path.mkdir()
    for name in module.CORE_FILES:
        (path / name).write_bytes(b"fixture")
    metadata = {"variant": "hinge", "split": "holdout", "pose": "supine", "joint_index": 0, "source_commit": "1" * 40}
    (path / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    record = {key: metadata[key] for key in ("split", "pose", "joint_index", "source_commit")}
    record.update(path="Z:/missing/original/archive", input_hashes={name: module.file_hash(path / name) for name in module.CORE_FILES})
    audit = {"failed": 0, "archives": [record], "scientific_gate": {"validated_pass": False}}
    return path, audit


def test_copied_archive_matches_hashes_without_original_machine_path(tmp_path):
    path, audit = fixture_archive(tmp_path)
    record, hashes = module.match_archive(path, audit)
    assert record["path"] == "Z:/missing/original/archive"
    assert set(hashes) == module.CORE_FILES


def test_tampered_input_is_rejected_before_diagnostics(tmp_path):
    path, audit = fixture_archive(tmp_path)
    (path / "trace.jsonl.gz").write_bytes(b"changed")
    with pytest.raises(ValueError, match="hashes"):
        module.match_archive(path, audit)


def test_failed_or_ambiguous_audit_is_rejected(tmp_path):
    path, audit = fixture_archive(tmp_path)
    audit["failed"] = 1
    with pytest.raises(ValueError, match="successful"):
        module.match_archive(path, audit)
    audit["failed"] = 0
    audit["archives"].append(audit["archives"][0].copy())
    with pytest.raises(ValueError, match="uniquely"):
        module.match_archive(path, audit)


def test_output_guard_refuses_input_directory_and_existing_output(tmp_path):
    path, _ = fixture_archive(tmp_path)
    with pytest.raises(ValueError, match="outside"):
        module.validate_output_path(path / "diagnostics.json", [path])
    existing = tmp_path / "preserved.json"
    existing.write_text("keep", encoding="utf-8")
    with pytest.raises(ValueError, match="overwrite"):
        module.validate_output_path(existing, [path])
    assert existing.read_text(encoding="utf-8") == "keep"


def test_cli_refuses_input_archive_write_before_reading_missing_audit(tmp_path):
    path, _ = fixture_archive(tmp_path)
    output = path / "diagnostics.json"
    result = subprocess.run([sys.executable, str(SCRIPT), str(path), "--audit", str(tmp_path / "missing_audit.json"), "--output", str(output)], capture_output=True, text=True)
    assert result.returncode == 2
    assert not output.exists()


def test_cli_rejects_hash_mismatch_without_writing_output(tmp_path):
    path, audit = fixture_archive(tmp_path)
    audit_path = tmp_path / "audit.json"
    audit_path.write_text(json.dumps(audit), encoding="utf-8")
    (path / "seed_results.json").write_bytes(b"corrupted")
    output = tmp_path / "output.json"
    result = subprocess.run([sys.executable, str(SCRIPT), str(path), "--audit", str(audit_path), "--output", str(output)], capture_output=True, text=True)
    assert result.returncode == 2
    assert "hashes" in result.stderr
    assert not output.exists()
