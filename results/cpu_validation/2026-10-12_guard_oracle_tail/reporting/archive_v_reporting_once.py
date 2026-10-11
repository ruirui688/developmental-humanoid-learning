"""Stage and seal V reporting attachments without changing raw/root manifests."""
import argparse
import hashlib
import json
from pathlib import Path
import time


REPO = Path(__file__).resolve().parents[1]
ROOT = REPO / "results/cpu_validation/2026-10-12_guard_oracle_tail"
REPORTING = ROOT / "reporting"
STAGE_MANIFEST = REPORTING / "reporting_stage_manifest.json"
FINAL_MANIFEST = REPORTING / "reporting_manifest.json"
REFERENCE_REVIEW = {
    "path": "external/archive_u_reporting_once.py",
    "content_reads": 1,
    "known_source_content_bytes": 2495,
    "sha256": "342dcf5ea4d50ecef88e3d082d4be751da8ce75364b018fa075ddc2eb7269dac",
    "underlying_filesystem_io_bytes": None,
    "underlying_filesystem_io_measured": False,
    "no_payload_read_or_helper_execution_during_preparation": True,
}
STAGE_FILES = (
    "c4_v_reporting_reads.json",
    "c4_v_reporting_summary.json",
    "c4_v_output_contract_static_review.json",
    "check_v_output_once.py",
    "read_v_reporting_once.py",
    "archive_v_reporting_once.py",
)


def encoded(value):
    return (json.dumps(value, indent=2, allow_nan=False) + "\n").encode("utf-8")


def identity(data):
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    phase = parser.add_mutually_exclusive_group(required=True)
    phase.add_argument("--stage", action="store_true")
    phase.add_argument("--seal", action="store_true")
    args = parser.parse_args()
    began_wall, began_cpu = time.perf_counter(), time.process_time()
    cost = {"file_reads": 0, "content_read_bytes": 0,
            "file_write_attempts": 0, "file_write_returns": 0, "file_write_bytes": 0}
    files = {}
    base_before = None

    def read(path):
        data = path.read_bytes()
        cost["file_reads"] += 1
        cost["content_read_bytes"] += len(data)
        return data

    def write_new(path, data):
        cost["file_write_attempts"] += 1
        with path.open("xb") as stream:
            stream.write(data)
        cost["file_write_returns"] += 1
        cost["file_write_bytes"] += len(data)

    def bind_base():
        # Bind exact bytes only; do not infer a schema or parse scientific payloads.
        return {name: identity(read(ROOT / name))
                for name in ("manifest.json", "raw/manifest.json")}

    def copy(source, target):
        if source.is_symlink() or not source.is_file():
            raise ValueError("regular reporting source required: " + str(source))
        data = read(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        write_new(target, data)
        if read(target) != data:
            raise ValueError("reporting copy mismatch: " + str(target))
        files[target.relative_to(ROOT).as_posix()] = {
            **identity(data), "source": source.relative_to(REPO).as_posix()}

    def record(status, base_after, **extra):
        return {
            "phase": "stage" if args.stage else "seal", "status": status,
            "root": ROOT.relative_to(REPO).as_posix(),
            "base_manifests": base_before, "base_manifests_after": base_after,
            "root_raw_manifests_unchanged": base_before is not None and base_before == base_after,
            "files": files, "reference_review": REFERENCE_REVIEW,
            "paid_cost_snapshot_before_manifest_write": dict(cost),
            "wall_seconds_before_manifest_write": time.perf_counter() - began_wall,
            "cpu_seconds_before_manifest_write": time.process_time() - began_cpu,
            "underlying_filesystem_io_bytes": None,
            "underlying_filesystem_io_measured": False,
            "no_scientific_recalculation": True, "automatic_retry": False,
            "no_checker_or_link_checker_invocation": True,
            **extra,
        }

    try:
        if args.stage:
            # Directory creation is the one-shot stage boundary; never merge an old stage.
            REPORTING.mkdir(parents=False, exist_ok=False)
            base_before = bind_base()
            for name in STAGE_FILES:
                copy(REPO / "external" / name, REPORTING / name)
            source_contract = REPO / "external/c4_v_output_contract_01"
            if not source_contract.is_dir() or source_contract.is_symlink():
                raise ValueError("regular V output contract directory required")
            contract_files = sorted(path for path in source_contract.rglob("*") if path.is_file())
            if not contract_files:
                raise ValueError("V output contract has no files")
            for source in contract_files:
                copy(source, REPORTING / "output_contract" / source.relative_to(source_contract))
            base_after = bind_base()
            if base_after != base_before:
                raise ValueError("root/raw manifest changed during stage")
            result = record("staged", base_after)
            write_new(STAGE_MANIFEST, encoded(result))
        else:
            if FINAL_MANIFEST.exists():
                raise FileExistsError("V reporting already sealed")
            stage_data = read(STAGE_MANIFEST)
            stage = json.loads(stage_data, parse_constant=lambda token: (_ for _ in ()).throw(
                ValueError("nonfinite stage JSON: " + token)))
            if stage.get("status") != "staged" or stage.get("root_raw_manifests_unchanged") is not True:
                raise ValueError("completed immutable V reporting stage required")
            base_before = bind_base()
            if base_before != stage["base_manifests"] or base_before != stage["base_manifests_after"]:
                raise ValueError("root/raw manifest identity differs from stage")
            files.update(stage["files"])
            for relative, expected in files.items():
                target = (ROOT / relative).resolve()
                if not target.is_relative_to(REPORTING.resolve()) or target.is_symlink():
                    raise ValueError("stage file is outside regular reporting scope")
                if identity(read(target)) != {"bytes": expected["bytes"], "sha256": expected["sha256"]}:
                    raise ValueError("staged attachment identity differs: " + relative)
            # Link validation ran independently. This helper only copies its first saved result.
            copy(REPO / "external/c4_v_results_links_01.json", REPORTING / "c4_v_results_links_01.json")
            base_after = bind_base()
            if base_after != base_before:
                raise ValueError("root/raw manifest changed during seal")
            stage_paid_after_write = dict(stage["paid_cost_snapshot_before_manifest_write"])
            stage_paid_after_write["file_write_attempts"] += 1
            stage_paid_after_write["file_write_returns"] += 1
            stage_paid_after_write["file_write_bytes"] += len(stage_data)
            result = record("sealed", base_after,
                            stage_manifest=identity(stage_data),
                            stage_paid_cost_after_stage_manifest_write=stage_paid_after_write,
                            stage_manifest_unchanged=True)
            write_new(FINAL_MANIFEST, encoded(result))
        print(json.dumps({
            "phase": "stage" if args.stage else "seal", "status": result["status"],
            "manifest": (STAGE_MANIFEST if args.stage else FINAL_MANIFEST).relative_to(REPO).as_posix(),
            "paid_cost_after_manifest_write": cost,
            "wall_seconds": time.perf_counter() - began_wall,
            "cpu_seconds": time.process_time() - began_cpu,
            "root_raw_manifests_unchanged": True, "automatic_retry": False,
        }, allow_nan=False))
    except BaseException as exc:
        # Leave first copied bytes intact; root retains this first stdout/stderr, with no retry.
        print(json.dumps({"phase": "stage" if args.stage else "seal", "status": "failed",
                          "failure": {"type": type(exc).__name__, "message": str(exc)},
                          "paid_cost": cost, "base_manifests_before": base_before,
                          "retained_files": files, "automatic_retry": False,
                          "wall_seconds": time.perf_counter() - began_wall,
                          "cpu_seconds": time.process_time() - began_cpu}, allow_nan=False))
        raise


if __name__ == "__main__":
    main()
