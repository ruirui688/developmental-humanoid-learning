"""Save the first invocation and exact source snapshot for each new X stage."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time

parser = argparse.ArgumentParser()
parser.add_argument("stage", choices=("assembly", "prediction", "control", "engineering"))
args = parser.parse_args()
repo = Path(__file__).resolve().parents[1]
prefix = {"assembly": "c4_x0_assembly_01", "engineering": "c4_x0_engineering_01",
          "prediction": "c4_x1_prediction_01", "control": "c4_x2_control_01"}[args.stage]
output = repo / "external" / prefix
output.mkdir(exist_ok=False)
source_paths = [
    "src/developmental_physics/suspended_environment.py",
    "scripts/validate_suspended_pair_engineering.py",
    "docs/SUSPENDED_PAIR_DOMAIN_DESIGN.md",
    "src/developmental_physics/supported_environment.py",
    "scripts/validate_supported_pair_engineering.py",
    "src/developmental_physics/environment.py",
    "src/developmental_physics/assets/ground_body.xml",
    "src/developmental_physics/__init__.py",
]
if args.stage in ("prediction", "control"):
    source_paths += [
        "src/developmental_physics/suspended_pair_development.py",
        "scripts/develop_suspended_pair.py", "docs/SUSPENDED_PAIR_LEARNING_PROTOCOL.md",
        "src/developmental_physics/residual_pd_pair_mpc.py",
        "src/developmental_physics/guard_coupled_pair_model.py",
        "src/developmental_physics/guard_pair_model.py",
        "src/developmental_physics/local_pair_model.py", "src/developmental_physics/local_model.py",
    ]
sources = {}
for name in source_paths:
    data = (repo / name).read_bytes()
    dest = output / "source" / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("xb") as stream:
        stream.write(data)
    sources[name] = {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
argv = [str(repo / "external/cpu_physics_env/Scripts/python.exe")]
if args.stage in ("assembly", "engineering"):
    argv += ["scripts/validate_suspended_pair_engineering.py", "--repo", str(repo),
             "--output", str(output / "raw")]
else:
    argv += ["scripts/develop_suspended_pair.py", "--repo", str(repo),
             "--output", str(output / "raw"), "--stage", args.stage]
if args.stage == "assembly":
    commit = None
    argv.append("--self-check")
else:
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
