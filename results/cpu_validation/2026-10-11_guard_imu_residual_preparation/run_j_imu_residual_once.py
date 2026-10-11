"""Preserve first J process output and wrapper wall cost."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

root = Path(__file__).resolve().parents[1]
output = root / 'external/c4_j_imu_residual_01'
stdout = root / 'external/c4_j_imu_residual_01.stdout'
stderr = root / 'external/c4_j_imu_residual_01.stderr'
report = root / 'external/c4_j_imu_residual_01.execution.json'
assert not output.exists() and not report.exists()
commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root).decode().strip()
command = [sys.executable, 'scripts/develop_guard_imu_residual.py',
           '--source-commit', commit, '--output', str(output)]
started = time.perf_counter()
task_environment = os.environ.copy()
task_environment['PYTHONPATH'] = str(root / 'src')
with stdout.open('xb') as out, stderr.open('xb') as err:
    completed = subprocess.run(command, cwd=root, env=task_environment, stdout=out, stderr=err, check=False)
record = {'command': command, 'returncode': completed.returncode,
          'wall_seconds': time.perf_counter()-started, 'source_commit': commit,
          'stdout': str(stdout), 'stderr': str(stderr), 'first_attempt': True,
          'PYTHONPATH': task_environment['PYTHONPATH']}
with report.open('x', encoding='utf-8') as handle:
    json.dump(record, handle, indent=2)
    handle.write('\n')
print(json.dumps(record))
sys.exit(completed.returncode)
