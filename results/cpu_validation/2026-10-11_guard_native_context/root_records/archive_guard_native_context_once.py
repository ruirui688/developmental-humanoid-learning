"""Seal first F outputs, source cache and original delivery repairs without replay."""
import hashlib
import json
from pathlib import Path
import time
root = Path(__file__).resolve().parents[1]
target = root / 'results/cpu_validation/2026-10-11_guard_native_context'
target.mkdir()
wall, cpu = time.perf_counter(), time.process_time()
records = {}; reads = read_bytes = checks = 0
def copy(path, name):
    global reads, read_bytes, checks
    data = path.read_bytes(); reads += 1; read_bytes += len(data)
    saved = target / name; saved.parent.mkdir(parents=True, exist_ok=True)
    with saved.open('xb') as stream: stream.write(data)
    back = saved.read_bytes(); reads += 1; read_bytes += len(back); checks += 1
    assert data == back, name
    records[name] = {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data),
        'original_path': path.relative_to(root).as_posix()}
source = root / 'external/guard_native_context_20261011_first'
for path in sorted(source.rglob('*')):
    if path.is_file(): copy(path, 'first/' + path.relative_to(source).as_posix())
for name in ['guard_native_context_20261011_first_stdout.txt', 'guard_native_context_20261011_first_execution.json',
        'c4_f_preparation_delivery_01.json', 'c4_f_binding_crlf_original.json',
        'c4_f_binding_lineending_correction_01.json', 'c4_f_binding_staged_repair_01.json',
        'c4_f_saved_projection_01.json', 'c4_f_saved_projection_schema_repair_01.json',
        'verify_guard_native_preparation_once.py', 'run_guard_native_context_once.py',
        'archive_guard_native_context_once.py']:
    copy(root / 'external' / name, 'root_records/' + name)
review = root / 'external/c4_native_context_output_review_staging'
assert (review / 'REVIEW.md').exists(), 'first output review must be sealed'
for path in sorted(review.rglob('*')):
    if path.is_file() and '__pycache__' not in path.parts:
        copy(path, 'output_review/' + path.relative_to(review).as_posix())
manifest = {'schema_version': 1, 'source_commit': '734ab7dab53563327b7dc072378551d2045b68ac',
    'kind': 'first_fixed_native_context_saved_description', 'files': records,
    'payload_count': len(records), 'payload_bytes': sum(item['bytes'] for item in records.values()),
    'copy_checks': checks, 'failed': 0,
    'boundary': 'Descriptive only. Original E stops and C4/C5 dependencies remain. The first root projection has invalid null flattened event fields; its schema repair preserves actual nested event counts.',
    'execution': {'binary_read_opens': reads, 'binary_read_bytes': read_bytes,
        'wall_seconds': time.perf_counter()-wall, 'cpu_seconds': time.process_time()-cpu,
        'timing_scope': 'copy and equality through manifest assembly; excludes manifest writing',
        'diagnostic_reexecutions': 0, 'new_statistics': 0, 'model_calls': 0, 'physics': 0, 'updates': 0}}
with (target / 'manifest.json').open('x', encoding='utf-8', newline='\n') as stream:
    json.dump(manifest, stream, indent=2); stream.write('\n')
print(json.dumps({k:manifest[k] for k in ('payload_count', 'payload_bytes', 'copy_checks', 'failed', 'execution')}, indent=2))
