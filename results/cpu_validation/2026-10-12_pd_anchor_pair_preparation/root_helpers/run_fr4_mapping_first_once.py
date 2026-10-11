"""Capture the only new FR4 mapping-contract attempt, without physical work."""
from pathlib import Path
import hashlib
import json
import subprocess
import time

root = Path(__file__).resolve().parents[1]
capture = root / 'external/fr4_first_mapping_contract'
assert not capture.exists(), 'first mapping attempt exists; do not rerun'
capture.mkdir()
command = [str(root / 'external/cpu_physics_env/Scripts/python.exe'), '-u',
           'external/fr4_controller_candidate/check_pd_anchor_mapping_once.py',
           '--repo', str(root), '--output', str(capture / 'contract.json')]
started = time.perf_counter()
with (capture / 'stdout.log').open('xb') as stdout, (capture / 'stderr.log').open('xb') as stderr:
    process = subprocess.run(command, cwd=root, stdout=stdout, stderr=stderr, check=False)
files = {}
for name in ('stdout.log', 'stderr.log', 'contract.json'):
    path = capture / name
    if path.is_file():
        data = path.read_bytes()
        files[name] = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
receipt = {'first_invocation': True, 'automatic_retry': False, 'command': command,
           'exit_code': process.returncode, 'wall_seconds': time.perf_counter() - started,
           'files': files, 'physical_interactions': 0, 'fit_or_RLS_updates': 0}
(capture / 'first_execution_receipt.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
print(json.dumps(receipt))
raise SystemExit(process.returncode)
