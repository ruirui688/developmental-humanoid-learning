"""Preserve the first M matrix diagnostic process and its outer wall cost."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

root = Path(__file__).resolve().parents[1]
output = root/'external/c4_m_design_geometry_01'
report = root/'external/c4_m_design_geometry_01.execution.json'
assert not output.exists() and not report.exists()
commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root).decode().strip()
command = [sys.executable, 'scripts/diagnose_guard_design_geometry.py', '--source-commit', commit, '--output', str(output)]
environment = os.environ.copy()
stdout = root/'external/c4_m_design_geometry_01.stdout'
stderr = root/'external/c4_m_design_geometry_01.stderr'
started = time.perf_counter()
with stdout.open('xb') as out, stderr.open('xb') as err:
    completed = subprocess.run(command, cwd=root, env=environment, stdout=out, stderr=err, check=False)
record = {'command': command, 'returncode': completed.returncode, 'wall_seconds': time.perf_counter()-started,
          'source_commit': commit, 'stdout': str(stdout), 'stderr': str(stderr), 'first_process_attempt': True}
with report.open('x', encoding='utf-8') as handle:
    json.dump(record, handle, indent=2)
    handle.write('\n')
print(json.dumps(record))
sys.exit(completed.returncode)
