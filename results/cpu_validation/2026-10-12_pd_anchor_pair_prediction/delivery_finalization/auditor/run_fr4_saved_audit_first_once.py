"""Capture one pinned new FR4 saved audit; no automatic retry."""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess
import sys
import time

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--stage', choices=('prediction', 'control'), required=True)
parser.add_argument('--source-commit', required=True)
parser.add_argument('--candidate-sha', required=True)
args = parser.parse_args()
prefix = 'fr4a' if args.stage == 'prediction' else 'fr4b'
candidate = root / f'external/{prefix}_audit_candidate/audit_pd_anchor_pair_{args.stage}.py'
assert hashlib.sha256(candidate.read_bytes()).hexdigest() == args.candidate_sha
capture = root / f'external/{prefix}_first_audit'
assert not capture.exists(), 'first audit exists; do not rerun'
capture.mkdir()
command = [sys.executable, str(candidate), '--repo', str(root), '--raw',
    str(root / f'results/cpu_validation/2026-10-12_pd_anchor_pair_{args.stage}/raw'),
    '--source-commit', args.source_commit, '--output', str(capture / 'result')]
started = time.perf_counter()
with (capture / 'stdout.log').open('xb') as stdout, (capture / 'stderr.log').open('xb') as stderr:
    process = subprocess.run(command, cwd=root, stdout=stdout, stderr=stderr, check=False)
receipt = {'first_attempt': True, 'automatic_retry': False, 'command': command,
    'candidate_sha256': args.candidate_sha, 'exit_code': process.returncode, 'wall_seconds': time.perf_counter()-started}
(capture / 'first_execution_receipt.json').write_text(json.dumps(receipt, indent=2)+'\n', encoding='utf-8')
print(json.dumps(receipt))
print((capture / 'stdout.log').read_text(encoding='utf-8'))
if process.returncode:
    print((capture / 'stderr.log').read_text(encoding='utf-8'))
raise SystemExit(process.returncode)
