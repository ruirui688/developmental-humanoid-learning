"""One-attempt provenance wrapper; explicit root first-audit notification received."""
import contextlib
from datetime import datetime, timezone
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import platform
import subprocess
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT/"external/elbow_pd_20261011_development"
AUDIT = ROOT/"external/elbow_pd_20261011_audit.json"
EXPECTED_AUDIT_SHA = "d84ad31b28f7fcc4ded8003b2503138a3cacc9f9b2fed33bf675758e43100571"
SOURCE = ROOT/"external/elbow_pd_summary_prepare.py"
PREFIX = ROOT/"external/elbow_pd_20261011_summary_01"


def sha_bytes(data):
    return hashlib.sha256(data).hexdigest()


def save_json(path, obj):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(obj, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write("\n")


def main():
    wall, cpu = time.perf_counter(), time.process_time()
    utc = datetime.now(timezone.utc).isoformat()
    # Atomic permanent marker: failure also consumes this execution attempt.
    save_json(Path(str(PREFIX)+"_attempt.json"), {"started_at_utc": utc,
        "authorization": "Root confirmed first collection and independent audit complete; one summary execution authorized.",
        "expected_audit_sha256": EXPECTED_AUDIT_SHA})
    source_bytes, wrapper_bytes = SOURCE.read_bytes(), Path(__file__).read_bytes()
    copies = {"summary_executed_source": Path(str(PREFIX)+"_summary_executed.py"),
              "wrapper_executed_source": Path(str(PREFIX)+"_wrapper_executed.py")}
    for path, data in ((copies["summary_executed_source"], source_bytes), (copies["wrapper_executed_source"], wrapper_bytes)):
        with path.open("xb") as stream:
            stream.write(data)
    record = {"started_at_utc": utc, "argv": sys.argv, "python": sys.version,
        "platform": platform.platform(), "source": {k: {"path": str(v), "sha256": sha_bytes(v.read_bytes())} for k, v in copies.items()},
        "git_head_at_summary": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "git_status_at_summary": subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=all"], cwd=ROOT, text=True),
        "archive": str(ARCHIVE), "first_audit": str(AUDIT), "expected_first_audit_sha256": EXPECTED_AUDIT_SHA,
        "physical_control_calls": 0, "physics_substeps": 0, "parameter_updates": 0, "audit_reexecutions": 0,
        "attempt_is_consumed_even_on_failure": True}
    output, stdout, code = None, io.StringIO(), 1
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stdout):
        try:
            if sha_bytes(AUDIT.read_bytes()) != EXPECTED_AUDIT_SHA:
                raise ValueError("First-audit bytes differ from root's completed-audit notification.")
            spec = importlib.util.spec_from_file_location("executed_elbow_pd_readonly_summary", copies["summary_executed_source"])
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            output = module.summarize(ARCHIVE, AUDIT)
            save_json(Path(str(PREFIX)+"_summary.json"), output)
            print(json.dumps({"checks": output["checks"], "failed": output["failed"],
                "selected": output["selected"], "budget": output["budget"],
                "outcome_counts": output["outcome_counts"], "summary_runtime": output["summary_runtime"]}, ensure_ascii=False))
            code = int(output["failed"] != 0)
        except BaseException as error:
            record["exception"] = {"type": type(error).__name__, "message": str(error)}
            traceback.print_exc()
    stdout_bytes = stdout.getvalue().encode("utf-8")
    stdout_path = Path(str(PREFIX)+"_stdout.txt")
    with stdout_path.open("xb") as stream:
        stream.write(stdout_bytes)
    record.update(finished_at_utc=datetime.now(timezone.utc).isoformat(), exit_code=code,
        wrapper_wall_seconds=time.perf_counter()-wall, wrapper_cpu_seconds=time.process_time()-cpu,
        stdout={"path": str(stdout_path), "sha256": sha_bytes(stdout_bytes)},
        summary=None if output is None else {"path": str(Path(str(PREFIX)+"_summary.json")),
            "sha256": sha_bytes(Path(str(PREFIX)+"_summary.json").read_bytes())})
    save_json(Path(str(PREFIX)+"_execution.json"), record)
    print(stdout.getvalue(), end="")
    print(json.dumps({"exit_code": code, "provenance": str(Path(str(PREFIX)+"_execution.json")),
        "wrapper_wall_seconds": record["wrapper_wall_seconds"], "wrapper_cpu_seconds": record["wrapper_cpu_seconds"]}))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
