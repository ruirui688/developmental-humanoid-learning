"""Save first Y invocation and exact source snapshot; no assembly repetition."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time

parser = argparse.ArgumentParser()
parser.add_argument("stage", choices=("engineering",))
args = parser.parse_args()
repo = Path(__file__).resolve().parents[1]
prefix = "c4_z0_engineering_01"
output = repo / "external" / prefix
output.mkdir(exist_ok=False)
source_paths = [
    "src/developmental_physics/fast_feedback_environment.py",
    "src/developmental_physics/suspended_environment.py",
    "scripts/validate_fast_feedback_engineering.py",
    "docs/FAST_FEEDBACK_ENGINEERING_PROTOCOL.md",
    "src/developmental_physics/supported_environment.py",
    "scripts/validate_supported_pair_engineering.py",
    "src/developmental_physics/environment.py",
    "src/developmental_physics/assets/ground_body.xml",
    "src/developmental_physics/__init__.py",
]
sources = {}
for name in dict.fromkeys(source_paths):
    data = (repo / name).read_bytes()
    dest = output / "source" / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("xb") as stream:
        stream.write(data)
    sources[name] = {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
argv = [str(repo / "external/cpu_physics_env/Scripts/python.exe")]
argv += ["scripts/validate_fast_feedback_engineering.py", "--repo", str(repo),
         "--output", str(output / "raw")]
commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True,
                        text=True, check=True).stdout.strip()
argv += ["--source-commit", commit]
started, began = time.time(), time.perf_counter()
stdout_bytes = 0
with (output / "stdout").open("xb") as stdout_log, (output / "stderr").open("xb") as stderr_log:
    process = subprocess.Popen(argv, cwd=repo, stdout=subprocess.PIPE, stderr=stderr_log)
    for line in process.stdout:
        stdout_log.write(line)
        stdout_log.flush()
        stdout_bytes += len(line)
        print(line.decode("utf-8", errors="replace").rstrip(), flush=True)
    returncode = process.wait()
elapsed = time.perf_counter() - began
stderr_bytes = (output / "stderr").stat().st_size
record = {"argv": argv, "source_commit": commit, "returncode": returncode,
          "source_files": sources, "source_snapshot_reads": len(sources),
          "source_snapshot_read_bytes": sum(v["bytes"] for v in sources.values()),
          "started_unix": started, "ended_unix": time.time(), "wall_seconds": elapsed,
          "stdout_bytes": stdout_bytes, "stderr_bytes": stderr_bytes,
          "subprocess_invocations": 1, "automatic_retry": False}
(output / "execution.json").write_text(json.dumps(record, indent=2)+"\n", encoding="utf-8")
print(json.dumps(record))
if stderr_bytes:
    print((output / "stderr").read_text(encoding="utf-8", errors="replace"))
raise SystemExit(returncode)
