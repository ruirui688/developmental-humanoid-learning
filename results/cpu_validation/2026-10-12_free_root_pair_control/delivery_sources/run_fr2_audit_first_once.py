"""Run the reviewed new FR2 audit once, preserving its first stdio."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys
import time

root = Path(__file__).resolve().parents[1]
candidate = root / 'external/fr2_audit_candidate/audit_free_root_pair_control.py'
expected = 'bc8bb0ea6c233c790d728e7a18c19cd68c125bbbfd828555b83c1758330f5a5c'
source = candidate.read_bytes()
assert hashlib.sha256(source).hexdigest() == expected
capture = root / 'external/fr2_first_audit'
assert not capture.exists(), 'first audit capture exists; do not rerun'
capture.mkdir()
command = [sys.executable, str(candidate), '--repo', str(root), '--raw',
    str(root / 'results/cpu_validation/2026-10-12_free_root_pair_control/raw'),
    '--source-commit', 'f9a0e0062727fd756751e97f7aff850e2069340c',
    '--output', str(capture / 'result')]
start = time.perf_counter()
with (capture / 'stdout.log').open('xb') as stdout, (capture / 'stderr.log').open('xb') as stderr:
    process = subprocess.run(command, cwd=root, stdout=stdout, stderr=stderr, check=False)
receipt = {'first_attempt': True, 'automatic_retry': False, 'command': command,
    'candidate_sha256': expected, 'exit_code': process.returncode,
    'wall_seconds': time.perf_counter()-start}
(capture / 'first_execution_receipt.json').write_text(json.dumps(receipt, indent=2)+'\n', encoding='utf-8')
print(json.dumps(receipt))
print((capture / 'stdout.log').read_text(encoding='utf-8'))
raise SystemExit(process.returncode)
