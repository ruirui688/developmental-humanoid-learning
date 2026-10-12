"""Capture the first EF1B controlonly runner process once; no automatic retry."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time
import traceback


def require(condition, message):
    if not condition:
        raise ValueError(message)


def requested_path(repo, value):
    path = Path(value)
    return (path if path.is_absolute() else repo/path).resolve()


def file_identity(path):
    data = path.read_bytes()
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".")
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--capture", required=True, help="Fresh first stdout/stderr/receipt directory.")
    parser.add_argument("--raw", required=True, help="Fresh runner output directory; forwarded as --output.")
    args = parser.parse_args()
    require(len(args.source_commit) == 40 and all(x in "0123456789abcdef" for x in args.source_commit),
            "exact_lowercase_source_commit_required")
    repo = Path(args.repo).resolve()
    require(repo.is_dir(), "repository_directory_required")
    capture, raw = requested_path(repo, args.capture), requested_path(repo, args.raw)
    for path in (capture, raw):
        require(path != repo and not repo.is_relative_to(path), "fresh_path_cannot_contain_repository")
        require(not path.exists(), "first_path_exists_do_not_rerun:"+str(path))
    require(capture != raw and not capture.is_relative_to(raw), "raw_must_not_equal_or_contain_capture")
    interpreter = repo/"external/cpu_physics_env/Scripts/python.exe"
    runner_relative = "scripts/develop_equilibrium_feedforward.py"
    require(interpreter.is_file() and (repo/runner_relative).is_file(), "fixed_CPU_interpreter_and_new_runner_required")
    capture.mkdir(parents=True, exist_ok=False)
    command = [str(interpreter), "-u", runner_relative, "--stage", "controlonly", "--repo", str(repo),
               "--output", str(raw), "--source-commit", args.source_commit]
    wall = time.perf_counter()
    attempted, returned, exit_code, failure, process_wall = False, False, None, None, None
    try:
        with (capture/"stdout.log").open("xb") as stdout, (capture/"stderr.log").open("xb") as stderr:
            process_start = time.perf_counter()
            attempted = True
            process = subprocess.run(command, cwd=repo, stdout=stdout, stderr=stderr, check=False)
            process_wall = time.perf_counter()-process_start
            returned, exit_code = True, process.returncode
    except BaseException as exc:
        failure = {"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()}
        if attempted:
            process_wall = time.perf_counter()-process_start
    files = {name: file_identity(capture/name) if (capture/name).is_file() else None
             for name in ("stdout.log", "stderr.log")}
    receipt = {
        "schema": "ef1b_control_first_execution_receipt_v1", "experiment_id": "EF1B", "stage": "controlonly",
        "first_invocation": True, "automatic_retry": False, "command": command,
        "source_commit": args.source_commit, "capture": str(capture), "raw_output": str(raw),
        "source_validation": "The new runner verifies the exact clean source commit before physics.",
        "process_launch_attempted": attempted, "process_returned": returned, "exit_code": exit_code,
        "first_launcher_failure": failure, "process_wall_seconds": process_wall,
        "wall_seconds_before_receipt": time.perf_counter()-wall, "files": files,
        "old_raw_or_model_reads_by_launcher": 0, "production_imports_by_launcher": 0,
        "direct_physics_calls_by_launcher": 0,
    }
    with (capture/"first_execution_receipt.json").open("x", encoding="utf-8") as stream:
        json.dump(receipt, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps(receipt, ensure_ascii=False, allow_nan=False))
    return exit_code if returned else 1


if __name__ == "__main__":
    raise SystemExit(main())
