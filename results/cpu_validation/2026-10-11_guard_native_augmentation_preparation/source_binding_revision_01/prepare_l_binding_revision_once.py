"""Preserve and promote only the reviewed L source-binding repair."""
import ast
import hashlib
import json
from pathlib import Path
import time

root = Path(__file__).resolve().parents[1]
draft = root/'external/c4_native_augmentation_staging'
out = root/'results/cpu_validation/2026-10-11_guard_native_augmentation_preparation/source_binding_revision_01'
out.mkdir(parents=True, exist_ok=False)
started, cpu = time.perf_counter(), time.process_time()
files, reads, size = {}, 0, 0

def copy(source, relative):
    global reads, size
    data = source.read_bytes()
    target = out/relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    saved = target.read_bytes()
    reads += 2
    size += len(data)+len(saved)
    assert data == saved
    files[relative] = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(), 'copy_verified': True}
    return data

for source in sorted((draft/'source_binding_revision_01').rglob('*')):
    if source.is_file() and '__pycache__' not in source.parts and source.suffix != '.pyc':
        copy(source, 'draft/'+source.relative_to(draft/'source_binding_revision_01').as_posix())
for name, directory in (('develop_guard_native_augmentation.py', 'scripts'), ('GUARD_NATIVE_AUGMENTATION_DEVELOPMENT_PROTOCOL.md', 'docs')):
    data = copy(draft/name, 'final/'+name)
    assert b'\r' not in data
    if name.endswith('.py'):
        ast.parse(data)
    target = root/directory/name
    target.write_bytes(data)
    saved = target.read_bytes()
    reads += 1
    size += len(saved)
    assert data == saved
copy(draft/'INTEGRITY.json', 'final/INTEGRITY.json')
copy(root/'external/c4_l_binding_revision_review.md', 'static_review.md')
copy(root/'external/run_l_native_augmentation_02_once.py', 'run_l_native_augmentation_02_once.py')
copy(Path(__file__), 'prepare_l_binding_revision_once.py')
record = {'scope': 'source binding repair only; all original checks and first failed run retained', 'files': files,
          'cost': {'binary_reads': reads, 'input_bytes': size, 'copy_checks': len(files), 'copy_failures': 0,
                   'wall_seconds': time.perf_counter()-started, 'cpu_seconds': time.process_time()-cpu},
          'actual_trace_or_weights_reads': 0, 'fits': 0, 'model_calls': 0, 'physics': 0}
(out/'manifest.json').write_text(json.dumps(record, indent=2)+'\n', encoding='utf-8')
print(json.dumps({'payloads': len(files), 'cost': record['cost']}))
