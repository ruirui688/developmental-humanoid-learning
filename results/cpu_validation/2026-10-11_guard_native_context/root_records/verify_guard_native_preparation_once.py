"""Verify staged F preparation bytes and only changed documentation links."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time
from urllib.parse import unquote
root = Path(__file__).resolve().parents[1]
target = root / 'external/c4_f_preparation_delivery_01.json'
assert not target.exists()
wall, cpu = time.perf_counter(), time.process_time()
base = 'results/cpu_validation/2026-10-11_guard_native_context_preparation'
blob = (root / base / 'manifest.json').read_bytes()
manifest = json.loads(blob)
reads, read_bytes = 1, len(blob)
records = {base + '/' + key: value for key, value in manifest['files'].items()}
names = [base + '/manifest.json', 'scripts/diagnose_guard_native_context.py',
    'docs/GUARD_NATIVE_CONTEXT_DIAGNOSTIC_PROTOCOL.md', 'configs/cpu/guard_native_context_binding.json']
for name in names:
    data = (root / name).read_bytes()
    reads += 1; read_bytes += len(data)
    records[name] = {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}
checks = 0; failures = []; git_bytes = 0
for name, item in records.items():
    data = subprocess.check_output(['git', 'show', ':' + name], cwd=root)
    git_bytes += len(data); checks += 1
    if len(data) != item['bytes'] or hashlib.sha256(data).hexdigest() != item['sha256']:
        failures.append(name)
for name in ['README.md', 'docs/CONTINUOUS_EXECUTION_PLAN.md', 'docs/PROGRESS.md',
             'docs/GUARD_NATIVE_CONTEXT_DIAGNOSTIC_PROTOCOL.md']:
    path = root / name
    data = path.read_bytes(); reads += 1; read_bytes += len(data)
    for match in re.finditer(r'!?\[[^\]]*\]\(([^\)]+)\)', data.decode('utf-8')):
        destination = match.group(1).strip().split(' "')[0].strip('<>')
        if destination.startswith(('https:', 'http:', '#', 'app:', 'codex:')):
            continue
        checks += 1
        if not (path.parent / unquote(destination.split('#', 1)[0])).exists():
            failures.append(name + ':' + destination)
report = {'checks': checks, 'failed': len(failures), 'failures': failures,
    'execution': {'local_binary_reads': reads, 'local_binary_bytes': read_bytes,
        'git_blob_reads': len(records), 'git_binary_bytes': git_bytes,
        'wall_seconds': time.perf_counter()-wall, 'cpu_seconds': time.process_time()-cpu,
        'timing_scope': 'checks through report assembly; excludes report write',
        'statistics_runs': 0, 'model_calls': 0, 'physics': 0, 'updates': 0}}
with target.open('x', encoding='utf-8') as stream:
    json.dump(report, stream, indent=2); stream.write('\n')
print(json.dumps(report, indent=2))
raise SystemExit(int(bool(failures)))
