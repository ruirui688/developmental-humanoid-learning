"""Seal only first FR3 stage delivery files; never read raw or recompute metrics."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import time
import traceback
from urllib.parse import unquote

NAVIGATION = ("AGENTS.md", "README.md", "docs/PROGRESS.md",
              "docs/CPU_VALIDATION_TARGET.md", "docs/CONTINUOUS_EXECUTION_PLAN.md")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("prediction", "control"), required=True)
    parser.add_argument("--repo", default=".")
    args = parser.parse_args()
    repo = Path(args.repo).resolve()
    prefix = "fr3a" if args.stage == "prediction" else "fr3b"
    archive = repo/f"results/cpu_validation/2026-10-12_full_request_pair_{args.stage}"
    delivery, audit_dest = archive/"delivery_finalization", archive/"audit_first"
    if not archive.is_dir() or delivery.exists():
        raise FileExistsError("existing stage archive and fresh delivery directory required")
    delivery.mkdir()
    wall, cpu = time.perf_counter(), time.process_time()
    cost = {"input_file_reads": 0, "input_bytes": 0, "output_file_writes": 0,
            "output_bytes": 0, "hash_bytes": 0, "markdown_reads": 0, "local_link_checks": 0}
    pins, links, failure = {}, [], None
    capture = f"external/{prefix}_first_audit"
    candidate = f"external/{prefix}_audit_candidate"
    pairs = [(f"{capture}/result/{name}", f"audit_first/{name}")
             for name in ("audit.json", "metric_recheck.json")]
    pairs += [(f"{capture}/{name}", f"audit_first/{name}")
              for name in ("stdout.log", "stderr.log", "first_execution_receipt.json")]
    pairs.append((f"{candidate}/audit_full_request_pair_{args.stage}.py",
                  f"delivery_finalization/auditor/audit_full_request_pair_{args.stage}.py"))
    audit_provenance = ("preparation.json",) if args.stage == "prediction" else (
        "AUDIT_CONTRACT.md", "fr2_to_fr3b_derivation.diff", "preparation_receipt.json")
    pairs += [(f"{candidate}/{name}", f"delivery_finalization/auditor/{name}") for name in audit_provenance]
    writer_files = (("external/fr3_report_writer_first_failure/first_shared_source.py", "first_shared_source.py"),
        ("external/fr3_report_writer_first_failure/first_failure_metadata.json", "first_failure_metadata.json"),
        ("external/fr3_report_writer_first_failure/root_first_stderr.txt", "root_first_stderr_tool_text.txt"),
        ("external/fr3_report_common_candidate.py", "repaired_shared_source.py"),
        (f"external/write_{prefix}_report_candidate.py", f"write_{prefix}_report_candidate.py"),
        ("external/fr3_report_writer_preparation.json", "preparation.json"),
        (f"external/{prefix}_report_writing_receipt.json", "writing_receipt.json"))
    pairs += [(source, f"delivery_finalization/report_writer/{name}") for source, name in writer_files]
    pairs += [(f"external/{prefix}_report_captured_once/{name}", f"delivery_finalization/report_writer/capture/{name}")
              for name in ("stdout.log", "stderr.log", "first_execution_receipt.json")]
    helpers = ["run_fr3_first_once.py", "archive_fr3_first_once.py", "run_fr3_saved_audit_first_once.py",
               "run_fr3_report_saved_once.py", "archive_fr3_control_source_failure_once.py"]
    if args.stage == "control":
        helpers.append("run_fr3_control_after_checkpoint_once.py")
    pairs += [(f"external/{name}", f"delivery_finalization/root_helpers/{name}") for name in helpers]
    pairs += [("external/fr3_delivery_finalizer_candidate/"+name, "delivery_finalization/finalizer/"+name)
              for name in ("finalize_fr3_stage_delivery_once.py", "preparation_receipt.json")]
    if (repo/f"{capture}/result/first_failure.json").is_file():
        pairs.append((f"{capture}/result/first_failure.json", "audit_first/first_failure.json"))
    try:
        if audit_dest.exists():
            raise FileExistsError("first audit delivery already exists")
        missing = [source for source, _ in pairs if not (repo/source).is_file()]
        if missing:
            raise FileNotFoundError("required delivery files missing: "+", ".join(missing))
        for source, relative in pairs:
            data = (repo/source).read_bytes()
            cost["input_file_reads"] += 1; cost["input_bytes"] += len(data); cost["hash_bytes"] += len(data)
            destination = archive/relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open("xb") as stream:
                stream.write(data)
            cost["output_file_writes"] += 1; cost["output_bytes"] += len(data)
            pins[relative] = {"source": source, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
        report = f"docs/FULL_REQUEST_PAIR_{'PREDICTION' if args.stage == 'prediction' else 'CONTROL'}_RESULTS.md"
        for name in (report, *NAVIGATION):
            data = (repo/name).read_bytes()
            cost["input_file_reads"] += 1; cost["input_bytes"] += len(data); cost["markdown_reads"] += 1
            for target in re.findall(r"\[[^\]\n]*\]\(([^)\n]+)\)", data.decode("utf-8-sig")):
                target = target.split(" ", 1)[0].strip("<>")
                if name != report and "FULL_REQUEST_PAIR_" not in target and "2026-10-12_full_request_pair_" not in target:
                    continue
                if target.startswith(("http:", "https:", "mailto:", "#", "codex:")):
                    continue
                target = unquote(target.split("#", 1)[0].split("?", 1)[0])
                exists = (repo/name).parent.joinpath(target).exists()
                cost["local_link_checks"] += 1
                links.append({"markdown": name, "target": target, "exists": exists})
        if any(not row["exists"] for row in links):
            raise FileNotFoundError("new stage Markdown contains missing local links")
    except BaseException as exc:
        failure = {"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()}
    cost.update(wall_seconds_before_metadata=time.perf_counter()-wall, cpu_seconds_before_metadata=time.process_time()-cpu)
    metadata = {"stage": "FR3A" if args.stage == "prediction" else "FR3B", "status": "failed" if failure else "sealed",
        "files": pins, "markdown_links": links, "first_failure": failure, "engineering_cost": cost,
        "raw_reads": 0, "scientific_recomputations": 0, "raw_existing_manifest_report_inputs_modified": False,
        "control_source_failure_modified": False, "root_first_stderr_is_tool_text_not_process_capture": True,
        "engineering_cost_scope": "completed delivery copies and Markdown reads/checks; final metadata write excluded",
        "timing_excludes_final_metadata_writes": True, "automatic_retry": False}
    with (delivery/"metadata_manifest.json").open("x", encoding="utf-8") as stream:
        json.dump(metadata, stream, indent=2, ensure_ascii=False, allow_nan=False); stream.write("\n")
    print(json.dumps({"stage": metadata["stage"], "status": metadata["status"], "copied_files": len(pins),
                      "checked_links": len(links), "failure": failure, "engineering_cost": cost}, ensure_ascii=False))
    return int(failure is not None)


if __name__ == "__main__":
    raise SystemExit(main())
