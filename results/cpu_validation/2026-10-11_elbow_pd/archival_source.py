"""Exact-byte C4-A evidence archival, without experiment/audit/summary replay."""
import hashlib
import json
from pathlib import Path
import subprocess
import time
import zipfile

ROOT = Path(__file__).resolve().parents[1]
EXT = ROOT/"external"
DEST = ROOT/"results/cpu_validation/2026-10-11_elbow_pd"
COMMIT = "91223b39c86fbeb09f7bc399229789b1e00ce181"
AUDIT_SHA = "d84ad31b28f7fcc4ded8003b2503138a3cacc9f9b2fed33bf675758e43100571"
SUMMARY_SHA = "5aaefe21d6aa8314673a5560522e8865123acda318e833b4951f4c5d00efc3e8"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    started, cpu = time.perf_counter(), time.process_time()
    if DEST.exists():
        raise ValueError("Archive destination already exists; no overwrite or replay permitted.")
    files = {
        "elbow_pd_20261011_audit.json": "audit.json",
        "elbow_pd_20261011_first_audit_stdout.txt": "audit_stdout.txt",
        "elbow_pd_20261011_collection_stdout.txt": "collection_stdout.txt",
        "elbow_pd_20261011_summary_01_summary.json": "summary.json",
        "elbow_pd_20261011_summary_01_summary_executed.py": "summary_source.py",
        "elbow_pd_20261011_summary_01_wrapper_executed.py": "summary_wrapper.py",
        "elbow_pd_20261011_summary_01_stdout.txt": "summary_stdout.txt",
        "elbow_pd_20261011_summary_01_execution.json": "summary_execution.json",
        "elbow_pd_20261011_summary_01_attempt.json": "summary_attempt_lock.json",
        "elbow_pd_summary_prepare.py": "summary_preparation_source.py",
        "elbow_pd_summary_wrapper.py": "summary_preparation_wrapper.py",
        "elbow_pd_20261011_summary_delivery.md": "result_delivery.md",
        "elbow_pd_summary_report.py": "report_source.py",
        "elbow_pd_20261011_report_execution.json": "report_execution.json",
        "elbow_pd_protocol_cross_review.md": "reviews/protocol_cross_review.md",
        "c4a_pd_full_regression_stdout.txt": "tests/full_regression_stdout.txt",
        "c4a_feedback_staging/TECHNICAL_PLAN.md": "reviews/technical_plan.md",
        "c4a_feedback_staging/selection_probe.py": "preparation/selection_probe.py",
        "c4a_feedback_staging/elbow_feedback_validate.py": "preparation/collector_staged.py",
        "c4a_feedback_staging/audit_elbow_feedback.py": "preparation/audit_staged.py",
        "c4a_feedback_staging/test_elbow_feedback_validate.py": "preparation/test_collector_staged.py",
        "c4a_feedback_staging/test_elbow_feedback_audit.py": "preparation/test_audit_staged.py",
        "c4a_feedback_staging/conftest.py": "preparation/conftest_staged.py",
        "archive_elbow_pd.py": "archival_source.py",
    }
    git_files = {
        "scripts/audit_elbow_feedback.py": "audit_source.py",
        "src/developmental_physics/elbow_feedback_validate.py": "collector_source.py",
        "tests/test_elbow_feedback_validate.py": "tests/test_elbow_feedback_validate.py",
        "tests/test_elbow_feedback_audit.py": "tests/test_elbow_feedback_audit.py",
        "docs/ELBOW_PD_DEVELOPMENT_PROTOCOL.md": "protocol.md",
    }
    # Assemble all bytes before creating the destination. Root's concurrent
    # edits to unrelated current sources cannot affect clean-commit originals.
    payload, origins = {}, {}
    raw = EXT/"elbow_pd_20261011_development"
    for path in sorted(raw.rglob("*")):
        if path.is_file():
            name = "development/"+path.relative_to(raw).as_posix()
            payload[name] = path.read_bytes()
            origins[name] = {"kind": "exact_filesystem_copy", "source": path.relative_to(ROOT).as_posix()}
    for source, target in files.items():
        payload[target] = (EXT/source).read_bytes()
        origins[target] = {"kind": "exact_filesystem_copy", "source": "external/"+source}
    for source, target in git_files.items():
        payload[target] = subprocess.check_output(["git", "show", COMMIT+":"+source], cwd=ROOT)
        origins[target] = {"kind": "exact_git_blob", "source": source, "source_commit": COMMIT}
    assert sha(payload["audit.json"]) == AUDIT_SHA
    assert sha(payload["summary.json"]) == SUMMARY_SHA
    audit, summary = json.loads(payload["audit.json"]), json.loads(payload["summary.json"])
    metadata = json.loads(payload["development/metadata.json"])
    original_manifest = json.loads(payload["development/manifest.json"])
    assert metadata["source_commit"] == COMMIT and metadata["source_status"] == "" and metadata["source_dirty"] is False
    assert audit["failed"] == summary["failed"] == 0
    assert audit["checks"] == 352833 and summary["checks"] == 84356
    assert sha(payload["audit_source.py"]) == audit["audit_script_sha256"]
    assert audit["archive"]["source_commit"] == summary["source_commit"] == COMMIT
    assert summary["selected"]["candidate"] == audit["archive"]["selection"]["selected"]["candidate"] == 8
    assert summary["budget"]["control_calls_attempted"] == 7521 and summary["budget"]["physics_steps"] == 75210
    assert summary["outcome_counts"] == {"completed": 24, "terminated": 3}
    execution = json.loads(payload["summary_execution.json"])
    assert execution["exit_code"] == 0
    for key, name in (("summary_executed_source", "summary_source.py"), ("wrapper_executed_source", "summary_wrapper.py")):
        assert execution["source"][key]["sha256"] == sha(payload[name])
    assert execution["stdout"]["sha256"] == sha(payload["summary_stdout.txt"])
    assert execution["summary"]["sha256"] == sha(payload["summary.json"])
    assert payload["summary_source.py"] == payload["summary_preparation_source.py"]
    assert payload["summary_wrapper.py"] == payload["summary_preparation_wrapper.py"]
    for name, expected in original_manifest.items():
        assert sha(payload["development/"+name]) == expected, name
    assert set(original_manifest) == {n.removeprefix("development/") for n in payload if n.startswith("development/")} - {"manifest.json"}
    for name, expected in audit["archive"]["input_hashes"].items():
        assert sha(payload["development/"+name]) == expected
    for name, expected in summary["input_hashes"].items():
        assert sha(payload["audit.json"] if name == "first_audit_json" else payload["development/"+name]) == expected
    source_count = 0
    # ZIP verification checks original source bytes, not a new model/audit run.
    with zipfile.ZipFile(raw/"source_snapshot.zip") as snapshot:
        assert set(snapshot.namelist()) == set(metadata["source_sha256"])
        assert len(snapshot.namelist()) == len(set(snapshot.namelist()))
        for name, expected in metadata["source_sha256"].items():
            data = snapshot.read(name)
            assert sha(data) == expected, name
            assert subprocess.check_output(["git", "show", COMMIT+":"+name], cwd=ROOT) == data, name
            source_count += 1
    readme = """# C4-A left-elbow classical PD development evidence

2026-10-11. Exact-byte archive of one clean-source collection and its first audit and one independent summary. No physical, audit, summary, prediction or fitting replay was performed during archival.

- Frozen source: `91223b39c86fbeb09f7bc399229789b1e00ce181`; supine / j1, development0/1/2, nine fixed PD candidates.
- 27 attempted trials: 24 complete, 3 native StudyAbort; 7,521 calls /75,210 substeps /0 parameter updates. All gain-development costs and paid prefixes remain included.
- Candidate8 Kp64/Kd1 selected; raw three-seed RMSE mean0.006209216810408326rad. Candidate6 Kp64/Kd0 failed in all seeds and cannot be ranked by its truncated RMSE.
- First audit352,833 checks /0 failures; independent summary84,356 /0. These are consistency and development evidence, not safety, body-learning, full-body or unseen-seed claims.

## Files

- [Raw development archive](development/manifest.json): metadata, all27 outcome records, compressed native traces and original-byte source ZIP.
- [First audit](audit.json), [audit source](audit_source.py), [audit stdout](audit_stdout.txt), [collection stdout](collection_stdout.txt).
- [Independent summary](summary.json), [executed source](summary_source.py), [wrapper](summary_wrapper.py), [permanent attempt lock](summary_attempt_lock.json), [stdout](summary_stdout.txt), [execution provenance](summary_execution.json).
- [Delivery report](result_delivery.md), its [formatting source](report_source.py) and [execution](report_execution.json). Formatting reads only the saved summary; it does not redo the raw summary.
- [Protocol](protocol.md), [static protocol review](reviews/protocol_cross_review.md), [technical preparation plan](reviews/technical_plan.md).
- [Pre-collection full regression stdout](tests/full_regression_stdout.txt): 880passed /13skipped /119.00s. The two test sources in tests/ are exact Git blobs from the collection commit. preparation/ retains the earlier staged source bytes and is not presented as the final executed implementation.
- [Final manifest](manifest.json) covers every file except itself, with byte count, SHA256 and exact copying source. [Archival source](archival_source.py), [stdout](archival_stdout.txt) and [execution record](archival_execution.json) describe read-only copying and verification.

[Results and scientific limits](../../../docs/ELBOW_PD_DEVELOPMENT_RESULTS.md). Source ZIP content is this repository's own code/assets; no external datasets or pretrained checkpoints are added. Git `-text` protects original bytes.
""".encode("utf-8")
    payload["README.md"] = readme
    origins["README.md"] = {"kind": "generated_archive_index", "source": "external/archive_elbow_pd.py"}
    DEST.mkdir(parents=True, exist_ok=False)
    for name, data in payload.items():
        target = DEST/name
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as stream:
            stream.write(data)
        assert target.read_bytes() == data, name
    archival_cost = {"wall_seconds": time.perf_counter()-started, "cpu_seconds": time.process_time()-cpu,
        "scope": "archive entry through exact-byte copies, raw/first-audit/summary hashes and ZIP/Git verification; excludes final manifest construction/write",
        "new_physical_control_calls": 0, "new_physics_substeps": 0, "audit_reexecutions": 0,
        "summary_reexecutions": 0, "model_prediction_or_update_calls": 0}
    archival_execution = {"purpose": __doc__, "source_sha256": sha(payload["archival_source.py"]),
        "verified_git_source_files": source_count, "verified_exact_copy_files": len(payload),
        "archive_source_commit": COMMIT, "read_only_costs": archival_cost}
    payload["archival_execution.json"] = (json.dumps(archival_execution, indent=2, ensure_ascii=False)+"\n").encode("utf-8")
    payload["archival_stdout.txt"] = (json.dumps({"copied_files_before_execution_records": len(payload)-1,
        "verified_git_sources": source_count, "first_audit_failed": audit["failed"], "summary_failed": summary["failed"],
        "selected": summary["selected"], "archival_cost": archival_cost}, ensure_ascii=False)+"\n").encode("utf-8")
    for name in ("archival_execution.json", "archival_stdout.txt"):
        origins[name] = {"kind": "generated_archival_provenance", "source": "external/archive_elbow_pd.py"}
        with (DEST/name).open("xb") as stream:
            stream.write(payload[name])
    entries = {name: {**origins[name], "bytes": len(data), "sha256": sha(data),
        "destination_bytes_verified": (DEST/name).read_bytes() == data} for name, data in sorted(payload.items())}
    manifest = {"purpose": "Final exact-byte evidence manifest; only manifest.json is excluded from self-hashing",
        "source_commit": COMMIT, "source_dirty": False, "files": entries,
        "file_sha256": {name: record["sha256"] for name, record in entries.items()},
        "raw_manifest": original_manifest, "verified_git_source_files": source_count,
        "first_audit_sha256": AUDIT_SHA, "first_audit_checks": audit["checks"], "first_audit_failed": audit["failed"],
        "first_audit_maximum_difference": audit["maximum_recomputation_difference"],
        "summary_sha256": SUMMARY_SHA, "summary_checks": summary["checks"], "summary_failed": summary["failed"],
        "selected": summary["selected"], "physical_budget": summary["budget"], "phase_budget": summary["phase_budget"],
        "outcome_counts": summary["outcome_counts"],
        "cumulative_formal_physics": {"control_calls": 216371, "physics_substeps": 2163710, "rls_updates": 9900},
        "read_only_costs": {"first_audit": audit["analysis_runtime"], "summary": summary["summary_runtime"],
            "summary_wrapper": {k: execution[k] for k in ("wrapper_wall_seconds", "wrapper_cpu_seconds")}, "archival": archival_cost},
        "claim_boundary": summary["claim_boundary"],
        "coverage": "Every destination file, including README and archival execution/stdout, except manifest.json itself"}
    with (DEST/"manifest.json").open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(manifest, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write("\n")
    assert set(entries) == {p.relative_to(DEST).as_posix() for p in DEST.rglob("*") if p.is_file()} - {"manifest.json"}
    assert all(sha((DEST/name).read_bytes()) == record["sha256"] for name, record in entries.items())
    print(payload["archival_stdout.txt"].decode("utf-8"), end="")
    print(json.dumps({"manifest_sha256": sha((DEST/"manifest.json").read_bytes()), "files_covered": len(entries),
        "archive": str(DEST), "manifest_coverage_verified": True,
        "first_audit_maximum_difference": manifest["first_audit_maximum_difference"]}))


if __name__ == "__main__":
    main()
