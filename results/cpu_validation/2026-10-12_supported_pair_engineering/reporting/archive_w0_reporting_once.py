"""Copy first W0 reporting records and bind unchanged raw manifests once."""
import hashlib
import json
from pathlib import Path
import time


def main():
    repo = Path(__file__).resolve().parents[1]
    root = repo / "results/cpu_validation/2026-10-12_supported_pair_engineering"
    target = root / "reporting"
    began, cpu = time.perf_counter(), time.process_time()
    cost = {"file_reads": 0, "read_bytes": 0, "file_writes": 0, "write_bytes": 0}

    def read(path):
        data = path.read_bytes()
        cost["file_reads"] += 1
        cost["read_bytes"] += len(data)
        return data

    def identity(data):
        return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}

    def base():
        return {name: identity(read(root / name))
                for name in ("manifest.json", "raw/manifest.json")}

    before = base()
    target.mkdir(exist_ok=False)
    sources = [
        "c4_w0_reporting_reads.json", "c4_w0_reporting_summary.json",
        "c4_w0_output_review.json", "c4_w0_results_links_01.json",
        "read_w0_reporting_once.py", "check_w0_engineering_once.py",
        "check_w0_links_once.py", "archive_w0_reporting_once.py",
        "c4_w0_output_contract_01/report.json", "c4_w0_output_contract_01/checker.py",
    ]
    files = {}
    for name in sources:
        source = repo / "external" / name
        if source.is_symlink() or not source.is_file():
            raise ValueError("regular reporting file required: " + name)
        data = read(source)
        relative = name.replace("c4_w0_output_contract_01/", "output_contract/")
        dest = target / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open("xb") as stream:
            stream.write(data)
        cost["file_writes"] += 1
        cost["write_bytes"] += len(data)
        if read(dest) != data:
            raise ValueError("copy mismatch: " + name)
        files[dest.relative_to(root).as_posix()] = {
            **identity(data), "source": source.relative_to(repo).as_posix()}
    after = base()
    if before != after:
        raise ValueError("raw/root manifest changed")
    record = {"status": "sealed", "files": files, "base_manifests": before,
              "base_manifests_after": after, "root_raw_manifests_unchanged": True,
              "cost_before_manifest_write": dict(cost),
              "wall_seconds_before_manifest_write": time.perf_counter() - began,
              "cpu_seconds_before_manifest_write": time.process_time() - cpu,
              "model_physics_or_scientific_metric_calls": 0,
              "checker_or_link_checker_executions": 0, "automatic_retry": False,
              "underlying_filesystem_io_measured": False}
    data = (json.dumps(record, indent=2, allow_nan=False) + "\n").encode()
    with (target / "reporting_manifest.json").open("xb") as stream:
        stream.write(data)
    cost["file_writes"] += 1
    cost["write_bytes"] += len(data)
    print(json.dumps({"status": "sealed", "cost_after_manifest_write": cost,
                      "wall_seconds": time.perf_counter() - began,
                      "cpu_seconds": time.process_time() - cpu,
                      "root_raw_manifests_unchanged": True}))


if __name__ == "__main__":
    main()
