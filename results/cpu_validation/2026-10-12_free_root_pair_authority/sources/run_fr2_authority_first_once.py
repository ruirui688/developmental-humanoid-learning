"""One new saved FR2 authority projection, with first stdio retained."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys
import time

root = Path(__file__).resolve().parents[1]
candidate = root/'external/fr2_authority_candidate/describe_fr2_authority_once.py'
expected = '1efbddb9dba64ce92d147ae091f0293cfdbe0b76082d7c8996acf38a8871560e'
assert hashlib.sha256(candidate.read_bytes()).hexdigest() == expected
capture = root/'external/fr2_authority_first'
assert not capture.exists(), 'first projection exists; do not rerun'
capture.mkdir()
command = [sys.executable, str(candidate), '--raw',
    str(root/'results/cpu_validation/2026-10-12_free_root_pair_control/raw'),
    '--output', str(capture/'description.json')]
start = time.perf_counter()
with (capture/'stdout.log').open('xb') as stdout, (capture/'stderr.log').open('xb') as stderr:
    process = subprocess.run(command, cwd=root, stdout=stdout, stderr=stderr, check=False)
receipt = {'first_attempt': True, 'automatic_retry': False, 'command':command,
    'candidate_sha256':expected, 'exit_code':process.returncode,
    'wall_seconds':time.perf_counter()-start}
(capture/'first_execution_receipt.json').write_text(json.dumps(receipt, indent=2)+'\n',encoding='utf-8')
print(json.dumps(receipt))
print((capture/'stdout.log').read_text(encoding='utf-8'))
raise SystemExit(process.returncode)
