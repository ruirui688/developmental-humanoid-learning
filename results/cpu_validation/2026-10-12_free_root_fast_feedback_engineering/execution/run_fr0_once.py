"""First FR0 invocation and exact source snapshot, without automatic retry."""
import hashlib
import json
from pathlib import Path
import subprocess
import time

repo = Path(__file__).resolve().parents[1]
out = repo / 'external/c4_fr0_engineering_01'
out.mkdir(exist_ok=False)
pins = {}
for name in ('scripts/validate_free_root_fast_feedback_engineering.py', 'src/developmental_physics/free_root_fast_feedback_environment.py', 'docs/FREE_ROOT_FAST_FEEDBACK_ENGINEERING_PROTOCOL.md', 'src/developmental_physics/environment.py', 'src/developmental_physics/assets/ground_body.xml', 'src/developmental_physics/__init__.py', 'pyproject.toml'):
    data = (repo / name).read_bytes()
    pins[name] = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
    path = out / 'source' / name
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(data)
commit = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=repo, capture_output=True, text=True, check=True).stdout.strip()
argv = [str(repo / 'external/cpu_physics_env/Scripts/python.exe'), 'scripts/validate_free_root_fast_feedback_engineering.py', '--repo', str(repo), '--output', str(out / 'raw'), '--source-commit', commit]
began, started = time.perf_counter(), time.time()
stdout_bytes = 0
with (out / 'stdout').open('xb') as stdout, (out / 'stderr').open('xb') as stderr:
    process = subprocess.Popen(argv, cwd=repo, stdout=subprocess.PIPE, stderr=stderr)
    for line in process.stdout:
        stdout.write(line)
        stdout.flush()
        stdout_bytes += len(line)
        print(line.decode('utf-8', errors='replace').rstrip(), flush=True)
    returncode = process.wait()
record = {'argv': argv, 'source_commit': commit, 'source_files': pins, 'returncode': returncode, 'wall_seconds': time.perf_counter()-began, 'started_unix': started, 'ended_unix': time.time(), 'source_snapshot_reads': len(pins), 'source_snapshot_read_bytes': sum(p['bytes'] for p in pins.values()), 'stdout_bytes': stdout_bytes, 'stderr_bytes': (out / 'stderr').stat().st_size, 'subprocess_invocations': 1, 'automatic_retry': False}
with (out / 'execution.json').open('x', encoding='utf-8') as stream:
    json.dump(record, stream, indent=2)
print(json.dumps(record))
if record['stderr_bytes']:
    print((out / 'stderr').read_text(encoding='utf-8', errors='replace'))
raise SystemExit(returncode)
