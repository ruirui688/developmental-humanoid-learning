"""First new interface fake/one-step evidence checks; no physical assembly."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

repo = Path(__file__).resolve().parents[1]
output = repo / "external/c4_z_interface_checks_01"
output.mkdir(exist_ok=False)
names = ["src/developmental_physics/fast_feedback_environment.py",
         "scripts/validate_fast_feedback_engineering.py",
         "tests/test_fast_feedback_environment.py", "tests/test_fast_feedback_engineering.py",
         "docs/FAST_FEEDBACK_ENGINEERING_PROTOCOL.md"]
files = {}
for name in names:
    data = (repo / name).read_bytes()
    target = output / "source" / name
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as stream:
        stream.write(data)
    files[name] = {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
environment = dict(os.environ)
environment["PYTHONPATH"] = str(repo / "src")
argv = [str(repo / "external/cpu_physics_env/Scripts/python.exe"), "-m", "pytest", "-q",
        "tests/test_fast_feedback_environment.py", "tests/test_fast_feedback_engineering.py"]
began = time.perf_counter()
with (output / "stdout").open("xb") as stdout, (output / "stderr").open("xb") as stderr:
    process = subprocess.run(argv, cwd=repo, env=environment, stdout=stdout, stderr=stderr, check=False)
record = {"argv": argv, "source_files": files, "returncode": process.returncode,
          "wall_seconds": time.perf_counter()-began, "test_invocations": 1,
          "scope": "New config/hash boundaries with monkeypatched constructors and one-substep evidence; no original physics/math fixtures",
          "real_physics_builds_forwards_steps": 0, "old_MPC_or_RLS_tests": 0, "automatic_retry": False}
with (output / "execution.json").open("x", encoding="utf-8") as stream:
    json.dump(record, stream, indent=2)
print((output / "stdout").read_text())
print((output / "stderr").read_text())
print(json.dumps(record))
raise SystemExit(process.returncode)
