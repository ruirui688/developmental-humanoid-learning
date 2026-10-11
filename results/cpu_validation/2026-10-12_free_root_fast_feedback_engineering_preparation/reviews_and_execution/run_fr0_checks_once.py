"""First six new FR0 pure checks; no old suite or physical experiments."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

repo = Path(__file__).resolve().parents[1]
out = repo / 'external/c4_fr0_checks_01'
out.mkdir(exist_ok=False)
pins = {}
for name in ('src/developmental_physics/free_root_fast_feedback_environment.py', 'scripts/validate_free_root_fast_feedback_engineering.py', 'tests/test_free_root_fast_feedback_engineering.py', 'docs/FREE_ROOT_FAST_FEEDBACK_ENGINEERING_PROTOCOL.md'):
    data = (repo / name).read_bytes()
    pins[name] = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
    path = out / 'source' / name
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(data)
env = dict(os.environ)
env['PYTHONPATH'] = str(repo / 'src')
argv = [str(repo / 'external/cpu_physics_env/Scripts/python.exe'), '-m', 'pytest', '-q', 'tests/test_free_root_fast_feedback_engineering.py']
began = time.perf_counter()
with (out / 'stdout').open('xb') as stdout, (out / 'stderr').open('xb') as stderr:
    process = subprocess.run(argv, cwd=repo, env=env, stdout=stdout, stderr=stderr, check=False)
record = {'argv': argv, 'source_files': pins, 'returncode': process.returncode, 'wall_seconds': time.perf_counter()-began, 'test_invocations': 1, 'scope': 'six new FR0 permission/completeness/contact/audit-failure/study-stop/inheritance cases only', 'real_physics_or_formal_learning_calls': 0, 'synthetic_fixture_calls': 'see saved test source; not claimed zero', 'old_tests_repeated': False, 'automatic_retry': False}
with (out / 'execution.json').open('x', encoding='utf-8') as stream:
    json.dump(record, stream, indent=2)
print((out / 'stdout').read_text())
print((out / 'stderr').read_text())
print(json.dumps(record))
raise SystemExit(process.returncode)
