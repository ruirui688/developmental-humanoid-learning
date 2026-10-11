"""Check F archived staged bytes and documentation links; no statistics replay."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time
from urllib.parse import unquote
root = Path(__file__).resolve().parents[1]
output = root / 'external/c4_f_result_delivery_01.json'
assert not output.exists()
wall, cpu = time.perf_counter(), time.process_time()
base = 'results/cpu_validation/2026-10-11_guard_native_context'
blob = (root / base / 'manifest.json').read_bytes(); manifest = json.loads(blob)
reads = 1; read_bytes = len(blob)
records = {base + '/' + name: item for name, item in manifest['files'].items()}
records[base+'/manifest.json'] = {'bytes': len(blob), 'sha256': hashlib.sha256(blob).hexdigest()}
checks = 0; failures = []; git_bytes = 0
for name, record in records.items():
    saved = subprocess.check_output(['git', 'show', ':'+name], cwd=root)
    git_bytes += len(saved); checks += 1
    if len(saved) != record['bytes'] or hashlib.sha256(saved).hexdigest() != record['sha256']:
        failures.append(name)
for name in ['AGENTS.md', 'README.md', 'docs/CONTINUOUS_EXECUTION_PLAN.md',
             'docs/PROGRESS.md', 'docs/GUARD_NATIVE_CONTEXT_DIAGNOSTIC_RESULTS.md']:
    path = root / name; data = path.read_bytes(); reads += 1; read_bytes += len(data)
    for match in re.finditer(r'!?\[[^\]]*\]\(([^\)]+)\)', data.decode('utf-8')):
        destination = match.group(1).strip().split(' "')[0].strip('<>')
        if destination.startswith(('https:', 'http:', '#', 'app:', 'codex:')): continue
        checks += 1
        if not (path.parent / unquote(destination.split('#', 1)[0])).exists():
            failures.append(name+':'+destination)
report = {'checks': checks, 'failed': len(failures), 'failures': failures,
    'manifest_sha256': hashlib.sha256(blob).hexdigest(),
    'execution': {'git_blob_reads': len(records), 'git_binary_bytes': git_bytes,
        'local_binary_reads': reads, 'local_binary_bytes': read_bytes,
        'wall_seconds': time.perf_counter()-wall, 'cpu_seconds': time.process_time()-cpu,
        'timing_scope': 'checks through report assembly; excludes final report writing',
        'model_calls': 0, 'physics': 0, 'updates': 0, 'diagnostic_reexecutions': 0, 'new_statistics': 0}}
with output.open('x', encoding='utf-8', newline='\n') as stream:
    json.dump(report, stream, indent=2); stream.write('\n')
print(json.dumps(report, indent=2))
raise SystemExit(int(bool(failures)))
