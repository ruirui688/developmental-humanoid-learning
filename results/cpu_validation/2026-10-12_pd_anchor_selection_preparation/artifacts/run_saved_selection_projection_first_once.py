"""Capture one explicitly frozen FR4D process; no raw or protocol file reads."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import traceback


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".")
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--protocol-sha256", required=True)
    parser.add_argument("--capture", required=True)
    args = parser.parse_args()
    repo, capture = Path(args.repo).resolve(), Path(args.capture).resolve()
    raw = (repo/"results/cpu_validation/2026-10-12_pd_anchor_pair_control/raw").resolve()
    if capture == repo or repo.is_relative_to(capture) or capture == raw or capture.is_relative_to(raw) or raw.is_relative_to(capture):
        raise ValueError("fresh_capture_must_not_modify_or_contain_repository_or_raw")
    capture.mkdir(parents=True, exist_ok=False)
    wall, cpu = time.perf_counter(), time.process_time()
    tool = Path(__file__).resolve().with_name("project_saved_pd_anchor_selection_once.py")
    pins, source_bytes, exit_code, failure = {}, 0, None, None
    started = False
    command = [sys.executable, str(tool), "--repo", str(repo), "--source-commit", args.source_commit,
               "--protocol-sha256", args.protocol_sha256, "--output", str(capture/"result")]
    try:
        for path in (Path(__file__).resolve(), tool):
            data = path.read_bytes()
            source_bytes += len(data)
            pins[path.name] = {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
        with (capture/"stdout.log").open("xb") as stdout, (capture/"stderr.log").open("xb") as stderr:
            started = True
            returned = subprocess.run(command, cwd=repo, stdout=stdout, stderr=stderr, check=False)
            exit_code = returned.returncode
    except BaseException as exc:
        failure = {"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()}
    receipt = {"schema": "fr4_saved_selection_first_execution_receipt_v1", "command": command,
               "declared_source_commit": args.source_commit, "declared_frozen_protocol_sha256": args.protocol_sha256,
               "source_pins": pins, "source_read_returns": len(pins), "source_read_bytes": source_bytes,
               "process_started": started, "exit_code": exit_code, "first_launcher_failure": failure,
               "raw_reads_by_launcher": 0, "protocol_file_reads_by_launcher": 0, "automatic_retry": False,
               "wall_seconds_before_receipt": time.perf_counter()-wall, "cpu_seconds_before_receipt": time.process_time()-cpu}
    with (capture/"first_execution_receipt.json").open("x", encoding="utf-8") as stream:
        json.dump(receipt, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"capture": str(capture), "exit_code": exit_code, "first_launcher_failure": failure}, ensure_ascii=False))
    return exit_code if exit_code is not None else 1


if __name__ == "__main__":
    raise SystemExit(main())
