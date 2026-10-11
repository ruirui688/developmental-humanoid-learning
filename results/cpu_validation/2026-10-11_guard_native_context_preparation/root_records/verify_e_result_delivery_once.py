"""Verify E staged byte identities and current documentation links once."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time
from urllib.parse import unquote

root = Path(__file__).resolve().parents[1]
output = root / 'external/c4_e_result_delivery_01.json'
assert not output.exists()
wall, cpu = time.perf_counter(), time.process_time()
base = 'results/cpu_validation/2026-10-11_guard_lag_control'
manifest_bytes = (root / base / 'manifest.json').read_bytes()
manifest = json.loads(manifest_bytes)
records = {base + '/' + name: item for name, item in manifest['files'].items()}
records[base + '/manifest.json'] = {'sha256': hashlib.sha256(manifest_bytes).hexdigest(), 'bytes': len(manifest_bytes)}
checks, failures, git_bytes = [], [], 0
for name, record in records.items():
    data = subprocess.check_output(['git', 'show', ':' + name], cwd=root)
    git_bytes += len(data)
    ok = len(data) == record['bytes'] and hashlib.sha256(data).hexdigest() == record['sha256']
    checks.append({'kind': 'staged_bytes', 'path': name, 'passed': ok})
    if not ok:
        failures.append(name)
docs = ['README.md', 'AGENTS.md', 'docs/PROGRESS.md', 'docs/CONTINUOUS_EXECUTION_PLAN.md',
        'docs/GUARD_LAG_CONTROL_DEVELOPMENT_RESULTS.md']
doc_bytes = 0
for name in docs:
    path = root / name
    data = path.read_bytes()
    doc_bytes += len(data)
    for match in re.finditer(r'!?\[[^\]]*\]\(([^\)]+)\)', data.decode('utf-8')):
        destination = match.group(1).strip().split(' "')[0].strip('<>')
        if destination.startswith(('https:', 'http:', '#', 'app:', 'codex:')):
            continue
        destination = unquote(destination.split('#', 1)[0])
        ok = (path.parent / destination).exists()
        checks.append({'kind': 'local_link', 'source': name, 'target': destination, 'passed': ok})
        if not ok:
            failures.append(name + ':' + destination)
report = {'checks': len(checks), 'failed': len(failures), 'failures': failures,
    'outer_manifest_sha256': hashlib.sha256(manifest_bytes).hexdigest(),
    'summary_sha256': records[base + '/summary_once/summary.json']['sha256'],
    'execution': {'staged_blob_reads': len(records), 'staged_blob_binary_bytes': git_bytes,
        'local_binary_reads': 1 + len(docs), 'local_binary_bytes': len(manifest_bytes) + doc_bytes,
        'wall_seconds': time.perf_counter()-wall, 'cpu_seconds': time.process_time()-cpu,
        'timing_scope': 'checks through report assembly; excludes final report writing',
        'new_physics': 0, 'model_predictions': 0, 'updates': 0, 'old_audit_or_summary_runs': 0}}
with output.open('x', encoding='utf-8') as stream:
    json.dump(report, stream, indent=2)
    stream.write('\n')
print(json.dumps(report, indent=2))
raise SystemExit(int(bool(failures)))
