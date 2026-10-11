"""Run only the repaired N fixture; retain CHECK_01 and its passed branches."""
import json
from pathlib import Path
import subprocess
import sys
import time

root = Path(__file__).resolve().parents[1]
stage = root/'external/c4_scaled_native_staging'
output, stdout, stderr, execution = (stage/name for name in
    ('CHECK_02.json', 'CHECK_02.stdout.txt', 'CHECK_02.stderr.txt', 'CHECK_02.execution.json'))
assert all(not path.exists() for path in (output, stdout, stderr, execution))
command = [sys.executable, str(stage/'check_scaled_native_transition.py'),
           '--only', 'failure_partial', '--output', str(output)]
started = time.perf_counter()
with stdout.open('xb') as out, stderr.open('xb') as err:
    completed = subprocess.run(command, cwd=root, stdout=out, stderr=err, check=False)
record = {'command': command, 'returncode': completed.returncode,
          'wall_seconds': time.perf_counter()-started, 'first_repaired_fixture_attempt': True,
          'previous_three_passed_cases_repeated': False, 'actual_payload_reads': 0,
          'stdout': str(stdout), 'stderr': str(stderr)}
with execution.open('x', encoding='utf-8') as handle:
    json.dump(record, handle, indent=2)
    handle.write('\n')
print(json.dumps(record))
sys.exit(completed.returncode)
