"""Preserve the first G outputs and their evidence; no scientific recomputation."""
import hashlib
import json
from pathlib import Path
import time

root = Path(__file__).resolve().parents[1]
target = root/'results/cpu_validation/2026-10-11_guard_pd_tail_control'
target.mkdir(parents=True, exist_ok=False)
wall, cpu = time.perf_counter(), time.process_time()
records = {}
opens = size = 0

def copy(source, destination):
    global opens, size
    data = (root/source).read_bytes(); opens += 1; size += len(data)
    saved_path = target/destination
    saved_path.parent.mkdir(parents=True, exist_ok=True)
    with saved_path.open('xb') as stream:
        stream.write(data)
    saved = saved_path.read_bytes(); opens += 1; size += len(saved)
    assert saved == data, destination
    records[destination] = {'bytes': len(saved), 'sha256': hashlib.sha256(saved).hexdigest(),
                            'original_path': source}

for path in sorted((root/'external/guard_pd_tail_control_20261011_first').iterdir()):
    assert path.is_file()
    copy(path.relative_to(root).as_posix(), 'raw/'+path.name)
for suffix, destination in (
    ('_stdout.txt', 'collection_stdout.txt'),
    ('_execution.json', 'collection_execution.json'),
    ('_runtime_source_freeze.json', 'runtime_source_freeze.json'),
    ('_audit.json', 'first_audit.json'),
    ('_audit_stdout.txt', 'first_audit_stdout.txt'),
    ('_audit_execution.json', 'first_audit_execution.json'),
):
    copy('external/guard_pd_tail_control_20261011_first'+suffix, destination)
copy('external/guard_pd_tail_control_20261011_summary_01/summary.json', 'summary_once/summary.json')
for path in sorted((root/'external/guard_pd_tail_control_20261011_first_audit_reservation').rglob('*')):
    if path.is_file():
        copy(path.relative_to(root).as_posix(), 'first_audit_reservation/'+
             path.relative_to(root/'external/guard_pd_tail_control_20261011_first_audit_reservation').as_posix())
copy('external/c4_g_first_wrapper_staging/run_pd_tail_control_once.py', 'tools/run_pd_tail_control_once.py')
copy('external/c4_g_summary_tools_staging/run_guard_pd_tail_control_first_audit_once.py', 'tools/run_first_audit_once.py')
copy('external/c4_g_summary_tools_staging/summarize_guard_pd_tail_control_saved_once.py', 'tools/summarize_saved_once.py')
copy('external/archive_guard_pd_tail_control_once.py', 'tools/archive_once.py')
summary = json.loads((target/'summary_once/summary.json').read_bytes()); opens += 1
size += records['summary_once/summary.json']['bytes']
manifest = {'schema_version': 1, 'kind': 'first_fixed_pd_tail_control_development_evidence',
    'source_commit': summary['source_commit'], 'files': records,
    'payload_count': len(records), 'payload_bytes': sum(x['bytes'] for x in records.values()),
    'checks': len(records), 'failed': 0, 'outcomes': summary['outcomes'],
    'scientific_gates': summary['final_gates'], 'c4_scientifically_validated': False,
    'preparation_archive': 'results/cpu_validation/2026-10-11_guard_pd_tail_preparation/manifest.json',
    'execution': {'explicit_binary_opens': opens, 'binary_bytes': size,
        'wall_seconds': time.perf_counter()-wall, 'cpu_seconds': time.process_time()-cpu,
        'scope': 'byte copying/equality and one saved summary read through manifest assembly; excludes final write',
        'new_physics_predictions_updates': 0, 'audit_summary_reexecutions': 0}}
with (target/'manifest.json').open('x', encoding='utf-8') as stream:
    json.dump(manifest, stream, indent=2, allow_nan=False); stream.write('\n')
print(json.dumps({key: manifest[key] for key in ('source_commit', 'payload_count', 'payload_bytes', 'checks', 'failed', 'outcomes', 'execution')}, indent=2))
