"""Seal only first FR4 audit/report delivery; no raw, navigation or metric calls."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import time
import traceback
from urllib.parse import unquote


def verify_zero_copy_missing_preparation(delivery, cost):
    """Bind the one declared first failure; no scientific archive input is read."""
    failed = delivery/"metadata_manifest.json"
    if failed.stat().st_size > 1024*1024:
        raise ValueError("first failed delivery metadata exceeds bounded size")
    data = failed.read_bytes()
    cost["input_file_reads"] += 1; cost["input_bytes"] += len(data); cost["hash_bytes"] += len(data)
    original = json.loads(data)
    expected_message = "required delivery files missing: external/fr4_report_candidate/preparation.json"
    failure = original.get("first_failure") or {}
    zero_keys = ("input_file_reads", "input_bytes", "output_file_writes", "output_bytes",
                 "hash_bytes", "markdown_reads", "local_link_checks")
    if not (original.get("stage") == "FR4A" and original.get("status") == "failed"
            and failure.get("type") == "FileNotFoundError" and failure.get("message") == expected_message
            and original.get("files") == {} and original.get("markdown_links") == []
            and all(type(original.get("engineering_cost", {}).get(key)) is int
                    and original["engineering_cost"][key] == 0 for key in zero_keys)
            and original.get("raw_reads") == 0 and original.get("scientific_recomputations") == 0
            and original.get("navigation_reads") == 0
            and original.get("raw_existing_manifest_report_inputs_modified") is False):
        raise ValueError("only exact zero-copy missing-preparation first failure may be completed")
    preserved_source = delivery/"first_failed_finalizer_source.py"
    if preserved_source.stat().st_size != 6715:
        raise ValueError("preserved first failed finalizer source size differs")
    source = preserved_source.read_bytes()
    cost["input_file_reads"] += 1; cost["input_bytes"] += len(source); cost["hash_bytes"] += len(source)
    source_pin = {"bytes": len(source), "sha256": hashlib.sha256(source).hexdigest()}
    if source_pin != {"bytes": 6715, "sha256": "6c24f174d656f515a487fc372eedca3f951db1380545f065d8d7fba0f59d115e"}:
        raise ValueError("preserved first failed finalizer source identity differs")
    return {"metadata_manifest.json": {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()},
            "first_failed_finalizer_source.py": source_pin, "exact_first_failure_message": expected_message,
            "original_zero_copy_and_read_counters_verified": True, "original_failure_preserved": True}



def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("prediction", "control"), required=True)
    parser.add_argument("--repo", default=".")
    parser.add_argument("--complete-after-zero-copy-missing-preparation", action="store_true")
    args = parser.parse_args()
    repo = Path(args.repo).resolve()
    prefix = "fr4a" if args.stage == "prediction" else "fr4b"
    archive = repo/f"results/cpu_validation/2026-10-12_pd_anchor_pair_{args.stage}"
    delivery, audit_dest = archive/"delivery_finalization", archive/"audit_first"
    supplemental = args.complete_after_zero_copy_missing_preparation
    metadata_name = "supplemental_metadata_manifest.json" if supplemental else "metadata_manifest.json"
    if supplemental:
        if args.stage != "prediction" or not archive.is_dir() or not delivery.is_dir():
            raise ValueError("supplemental completion requires existing first FR4A delivery directory")
        if (delivery/metadata_name).exists():
            raise FileExistsError("first supplemental completion metadata already exists")
    else:
        if not archive.is_dir() or delivery.exists():
            raise FileExistsError("existing stage archive and fresh delivery directory required")
        delivery.mkdir()
    wall, cpu = time.perf_counter(), time.process_time()
    cost = {"input_file_reads": 0, "input_bytes": 0, "output_file_writes": 0,
            "output_bytes": 0, "hash_bytes": 0, "markdown_reads": 0, "local_link_checks": 0}
    pins, links, failure = {}, [], None
    first_failed_delivery = None
    capture = f"external/{prefix}_first_audit"
    candidate = f"external/{prefix}_audit_candidate"
    pairs = [(f"{capture}/result/{name}", f"audit_first/{name}")
             for name in ("audit.json", "metric_recheck.json")]
    pairs += [(f"{capture}/{name}", f"audit_first/{name}")
              for name in ("stdout.log", "stderr.log", "first_execution_receipt.json")]
    pairs.append((f"{candidate}/audit_pd_anchor_pair_{args.stage}.py",
                  f"delivery_finalization/auditor/audit_pd_anchor_pair_{args.stage}.py"))
    pairs.append(("external/run_fr4_saved_audit_first_once.py",
                  "delivery_finalization/auditor/run_fr4_saved_audit_first_once.py"))
    audit_provenance = (
        "AUDIT_CONTRACT.md", "fr3a_to_fr4a_derivation.diff", "preparation_receipt.json",
        "first_preparation_document_lookup_failure.json") if args.stage == "prediction" else (
        "static_derivation_receipt.json",)
    pairs += [(f"{candidate}/{name}", f"delivery_finalization/auditor/{name}") for name in audit_provenance]
    writer_candidate = "external/fr4_report_candidate"
    writer_files = ((f"{writer_candidate}/fr4_report_common_candidate.py", "fr4_report_common_candidate.py"),
        (f"{writer_candidate}/write_{prefix}_report_candidate.py", f"write_{prefix}_report_candidate.py"),
        (f"{writer_candidate}/run_fr4_report_saved_once.py", "run_fr4_report_saved_once.py"),
        (f"{writer_candidate}/preparation.json", "preparation.json"),
        (f"{writer_candidate}/{prefix}_report_writing_receipt.json", "writing_receipt.json"))
    pairs += [(source, f"delivery_finalization/report_writer/{name}") for source, name in writer_files]
    pairs += [(f"external/{prefix}_report_captured_once/{name}", f"delivery_finalization/report_writer/capture/{name}")
              for name in ("stdout.log", "stderr.log", "first_execution_receipt.json")]
    pairs += [("external/fr4_delivery_finalizer_candidate/"+name, "delivery_finalization/finalizer/"+name)
              for name in ("finalize_fr4_stage_delivery_once.py", "preparation_receipt.json")]
    if supplemental:
        pairs.append(("external/fr4_delivery_finalizer_candidate/recovery_preparation_receipt.json",
                      "delivery_finalization/finalizer/recovery_preparation_receipt.json"))
    if (repo/f"{capture}/result/first_failure.json").is_file():
        pairs.append((f"{capture}/result/first_failure.json", "audit_first/first_failure.json"))
    try:
        if audit_dest.exists():
            raise FileExistsError("first audit delivery already exists")
        if supplemental:
            first_failed_delivery = verify_zero_copy_missing_preparation(delivery, cost)
            existing = [relative for _, relative in pairs if (archive/relative).exists()]
            if existing:
                raise FileExistsError("supplemental completion requires every planned copy destination absent: "+", ".join(existing))
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
        report = f"docs/PD_ANCHOR_PAIR_{'PREDICTION' if args.stage == 'prediction' else 'CONTROL'}_RESULTS.md"
        for name in (report,):
            data = (repo/name).read_bytes()
            cost["input_file_reads"] += 1; cost["input_bytes"] += len(data); cost["markdown_reads"] += 1
            for target in re.findall(r"\[[^\]\n]*\]\(([^)\n]+)\)", data.decode("utf-8-sig")):
                target = target.split(" ", 1)[0].strip("<>")
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
    metadata = {"stage": "FR4A" if args.stage == "prediction" else "FR4B", "status": "failed" if failure else "sealed",
        "files": pins, "markdown_links": links, "first_failure": failure, "engineering_cost": cost,
        "raw_reads": 0, "scientific_recomputations": 0, "raw_existing_manifest_report_inputs_modified": False,
        "navigation_reads": 0, "physics_or_archive_helper_files_copied": False,
        "report_writer_first_stdio_process_capture": True,
        "engineering_cost_scope": "completed delivery copies and Markdown reads/checks; final metadata write excluded",
        "timing_excludes_final_metadata_writes": True, "automatic_retry": False}
    if supplemental:
        metadata.update(supplemental_completion_after_zero_copy_missing_preparation=True,
                        first_failed_delivery_binding=first_failed_delivery,
                        recovery_validation_reads_included_in_engineering_cost=True)
    with (delivery/metadata_name).open("x", encoding="utf-8") as stream:
        json.dump(metadata, stream, indent=2, ensure_ascii=False, allow_nan=False); stream.write("\n")
    print(json.dumps({"stage": metadata["stage"], "status": metadata["status"], "copied_files": len(pins),
                      "checked_links": len(links), "failure": failure, "engineering_cost": cost}, ensure_ascii=False))
    return int(failure is not None)


if __name__ == "__main__":
    raise SystemExit(main())
