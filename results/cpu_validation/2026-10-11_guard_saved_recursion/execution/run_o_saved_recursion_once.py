"""One invocation only; saved-output diagnostic, never refit or rerun a model."""
import hashlib
import json
from pathlib import Path
import subprocess
import time

repo = Path(__file__).resolve().parents[1]
output = repo / "external/c4_o_saved_recursion_01"
if output.exists():
    raise SystemExit("first output already exists; preserve it and do not rerun")
commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo,
                        capture_output=True, text=True, check=True).stdout.strip()
argv = ["D:/Python3.10/python.exe", "scripts/diagnose_guard_saved_recursion.py",
        "--repo", str(repo), "--source-commit", commit, "--output", str(output / "raw")]
output.mkdir()
started = time.time()
wall = time.perf_counter()
proc = subprocess.run(argv, cwd=repo, capture_output=True, check=False)
elapsed = time.perf_counter() - wall
(output / "stdout").write_bytes(proc.stdout)
(output / "stderr").write_bytes(proc.stderr)
record = {"argv": argv, "source_commit": commit, "started_unix": started,
          "ended_unix": time.time(), "wall_seconds": elapsed,
          "returncode": proc.returncode,
          "stdout": {"bytes": len(proc.stdout), "sha256": hashlib.sha256(proc.stdout).hexdigest()},
          "stderr": {"bytes": len(proc.stderr), "sha256": hashlib.sha256(proc.stderr).hexdigest()},
          "subprocess_invocations": 1, "automatic_retry": False}
(output / "execution.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
print(json.dumps(record))
raise SystemExit(proc.returncode)
