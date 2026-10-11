"""Preserve the first authorized new N synthetic check process."""
import json
from pathlib import Path
import subprocess
import sys
import time

root = Path(__file__).resolve().parents[1]
stage = root/'external/c4_scaled_native_staging'
output, stdout, stderr, execution = (stage/name for name in
    ('CHECK_01.json', 'CHECK_01.stdout.txt', 'CHECK_01.stderr.txt', 'CHECK_01.execution.json'))
assert all(not path.exists() for path in (output, stdout, stderr, execution))
command = [sys.executable, str(stage/'check_scaled_native_transition.py'), '--output', str(output)]
started = time.perf_counter()
with stdout.open('xb') as out, stderr.open('xb') as err:
    completed = subprocess.run(command, cwd=root, stdout=out, stderr=err, check=False)
record = {'command': command, 'returncode': completed.returncode,
          'wall_seconds': time.perf_counter()-started, 'first_attempt': True,
          'actual_payload_reads': 0, 'stdout': str(stdout), 'stderr': str(stderr)}
with execution.open('x', encoding='utf-8') as handle:
    json.dump(record, handle, indent=2)
    handle.write('\n')
print(json.dumps(record))
sys.exit(completed.returncode)
