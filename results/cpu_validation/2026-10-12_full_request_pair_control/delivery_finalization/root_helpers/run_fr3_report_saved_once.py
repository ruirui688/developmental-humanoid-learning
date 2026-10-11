"""Capture the repaired A report or first B report without a retry loop."""
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
parser.add_argument('--audit-checks', type=int, required=True)
parser.add_argument('--audit-rmse-vectors', type=int, required=True)
parser.add_argument('--audit-status', choices=('passed', 'failed'), required=True)
parser.add_argument('--audit-failed', type=int, required=True)
args = parser.parse_args()
shared = root/'external/fr3_report_common_candidate.py'
assert hashlib.sha256(shared.read_bytes()).hexdigest() == '3d7fe5081fc71ee71ad66b0b5e43b4c0fad971f008e808b01d89efa4238d79cf'
prefix = 'fr3a' if args.stage == 'prediction' else 'fr3b'
capture = root/f'external/{prefix}_report_captured_once'
assert not capture.exists(), 'report capture exists; no rerun'
if args.stage == 'prediction':
    assert (root/'external/fr3_report_writer_first_failure/root_first_stderr.txt').is_file()
capture.mkdir()
command = [sys.executable, str(root/f'external/write_{prefix}_report_candidate.py'), '--write',
           '--audit-status', args.audit_status, '--audit-checks', str(args.audit_checks),
           '--audit-failed', str(args.audit_failed), '--audit-rmse-vectors', str(args.audit_rmse_vectors)]
if args.stage == 'control':
    command += ['--base-control', '394297', '--base-substeps', '2673970',
                '--base-online-scalar', '94452', '--base-offline-scalar', '7200']
start = time.perf_counter()
with (capture/'stdout.log').open('xb') as out, (capture/'stderr.log').open('xb') as err:
    result = subprocess.run(command, cwd=root, stdout=out, stderr=err, check=False)
receipt = {'stage': args.stage, 'first_A_identity_failure_preserved': True,
           'first_repaired_A_report' if args.stage == 'prediction' else 'first_B_report': True,
           'automatic_retry': False, 'command': command, 'exit_code': result.returncode,
           'wall_seconds': time.perf_counter()-start}
with (capture/'first_execution_receipt.json').open('x', encoding='utf-8') as stream:
    json.dump(receipt, stream, indent=2)
    stream.write('\n')
print(json.dumps(receipt))
print((capture/'stdout.log').read_text(encoding='utf-8'))
if result.returncode:
    print((capture/'stderr.log').read_text(encoding='utf-8'))
raise SystemExit(result.returncode)
