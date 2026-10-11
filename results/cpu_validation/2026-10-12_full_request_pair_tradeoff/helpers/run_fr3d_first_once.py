"""Capture one pinned saved-value projection, without a retry loop."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys
import time

root = Path(__file__).resolve().parents[1]
candidate = root/'external/fr3d_candidate/describe_fr3_control_tradeoff_once.py'
prep = json.loads((root/'external/fr3d_candidate/preparation_receipt.json').read_bytes())
assert hashlib.sha256(candidate.read_bytes()).hexdigest() == prep['candidate']['sha256']
assert hashlib.sha256((root/'external/fr3d_candidate/frozen_design.md').read_bytes()).hexdigest() == prep['design']['sha256']
head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
assert head == 'e589c17d1b331b48162c117f9581825ff6fafd54'
assert not subprocess.check_output(['git', 'status', '--porcelain'], cwd=root)
capture = root/'external/fr3d_first'
assert not capture.exists(), 'first capture exists; no rerun'
capture.mkdir()
command = [sys.executable, '-u', str(candidate), '--repo', str(root), '--output', str(capture/'result')]
start = time.perf_counter()
with (capture/'stdout.log').open('xb') as out, (capture/'stderr.log').open('xb') as err:
    result = subprocess.run(command, cwd=root, stdout=out, stderr=err, check=False)
receipt = {'first_execution': True, 'automatic_retry': False, 'source_checkpoint': head,
           'candidate_sha256': prep['candidate']['sha256'], 'command': command,
           'wall_seconds': time.perf_counter()-start, 'exit_code': result.returncode}
(capture/'first_execution_receipt.json').write_text(json.dumps(receipt, indent=2)+'\n', encoding='utf-8')
print(json.dumps(receipt))
print((capture/'stdout.log').read_text(encoding='utf-8'))
if result.returncode:
    print((capture/'stderr.log').read_text(encoding='utf-8'))
raise SystemExit(result.returncode)
