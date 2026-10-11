"""Retain the first N process, its exact clean source and outer wall cost."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

root = Path(__file__).resolve().parents[1]
base = root/'external/c4_n_scaled_native_01'
report = base.with_suffix('.execution.json')
stdout = base.with_suffix('.stdout')
stderr = base.with_suffix('.stderr')
assert all(not p.exists() for p in (base, report, stdout, stderr))
commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root).decode().strip()
assert not subprocess.check_output(['git', 'status', '--porcelain'], cwd=root).strip()
command = [sys.executable, 'scripts/develop_guard_scaled_native_transition.py',
           '--repo', str(root), '--source-commit', commit, '--output', str(base)]
started = time.perf_counter()
with stdout.open('xb') as out, stderr.open('xb') as err:
    completed = subprocess.run(command, cwd=root, env=os.environ.copy(),
                               stdout=out, stderr=err, check=False)
record = {'command': command, 'source_commit': commit, 'returncode': completed.returncode,
          'wall_seconds': time.perf_counter()-started, 'first_attempt': True,
          'stdout': str(stdout), 'stderr': str(stderr)}
with report.open('x', encoding='utf-8') as handle:
    json.dump(record, handle, indent=2)
    handle.write('\n')
print(json.dumps(record))
sys.exit(completed.returncode)
