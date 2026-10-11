"""Archive first FR0 bytes without executing any science or physics."""
import hashlib
import json
from pathlib import Path
import time

repo = Path(__file__).resolve().parents[1]
origin = repo / 'external/c4_fr0_engineering_01'
out = repo / 'results/cpu_validation/2026-10-12_free_root_fast_feedback_engineering'
out.mkdir(exist_ok=False)
began, cpu = time.perf_counter(), time.process_time()
files, cost = {}, dict(reads=0, read_bytes=0, writes=0, write_bytes=0)
def copy(source, relative):
    data = source.read_bytes()
    cost['reads'] += 1
    cost['read_bytes'] += len(data)
    path = out / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(data)
    cost['writes'] += 1
    cost['write_bytes'] += len(data)
    verify = path.read_bytes()
    cost['reads'] += 1
    cost['read_bytes'] += len(verify)
    assert verify == data
    files[relative.as_posix()] = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(), 'source': source.relative_to(repo).as_posix()}
for path in sorted(origin.rglob('*')):
    if path.is_file():
        copy(path, path.relative_to(origin))
for name in ('run_fr0_once.py', 'archive_fr0_once.py'):
    copy(repo / 'external' / name, Path('execution') / name)
record = {'status': 'archived', 'files': files, 'cost_before_manifest_write': cost.copy(), 'wall_seconds': time.perf_counter()-began, 'cpu_seconds': time.process_time()-cpu, 'model_fit_physics_or_scientific_metric_calls': 0, 'automatic_retry': False}
with (out / 'manifest.json').open('x', encoding='utf-8') as stream:
    json.dump(record, stream, indent=2)
print(json.dumps({'payloads': len(files), **cost}))
