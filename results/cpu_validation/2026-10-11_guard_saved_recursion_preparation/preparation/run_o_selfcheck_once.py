"""Preserve first synthetic-only O check and the exact checked draft bytes."""
import hashlib
import json
from pathlib import Path
import subprocess
import time

repo = Path(__file__).resolve().parents[1]
output = repo / "external/c4_o_selfcheck_01"
if output.exists():
    raise SystemExit("first synthetic output already exists; do not rerun it")
output.mkdir()
sources = {}
source_names = ("scripts/diagnose_guard_saved_recursion.py", "docs/GUARD_SAVED_RECURSION_DIAGNOSTIC_PROTOCOL.md")
for name in source_names:
    raw = (repo/name).read_bytes()
    dest = output / "checked_source" / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(raw)
    sources[name] = {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
argv = ["D:/Python3.10/python.exe", "scripts/diagnose_guard_saved_recursion.py", "--self-check", "--repo", str(repo), "--output", str(output/"raw")]
wall = time.perf_counter()
proc = subprocess.run(argv, cwd=repo, capture_output=True, check=False)
elapsed = time.perf_counter() - wall
(output/"stdout").write_bytes(proc.stdout)
(output/"stderr").write_bytes(proc.stderr)
record = {"argv": argv, "returncode": proc.returncode, "wall_seconds": elapsed,
          "checked_sources": sources, "source_snapshot_reads": len(sources),
          "source_snapshot_read_bytes": sum(x["bytes"] for x in sources.values()),
          "subprocess_invocations": 1, "automatic_retry": False}
(output/"execution.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
print(json.dumps(record))
print(proc.stdout.decode("utf-8", errors="replace"))
print(proc.stderr.decode("utf-8", errors="replace"))
raise SystemExit(proc.returncode)
