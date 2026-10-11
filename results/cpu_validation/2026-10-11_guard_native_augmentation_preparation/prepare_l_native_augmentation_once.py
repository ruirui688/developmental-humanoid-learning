"""Byte-preserving L promotion; no repeated passed engineering checks."""
import ast
import hashlib
import json
from pathlib import Path
import time

root = Path(__file__).resolve().parents[1]
draft = root/'external/c4_native_augmentation_staging'
out = root/'results/cpu_validation/2026-10-11_guard_native_augmentation_preparation'
assert (draft/'CHECK_01.json').exists() and (draft/'INTEGRITY.json').exists()
assert json.loads((draft/'CHECK_01.json').read_bytes())['passed']
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

for source in sorted(draft.rglob('*')):
    if not source.is_file() or '__pycache__' in source.parts or source.suffix == '.pyc':
        continue
    relative = source.relative_to(draft).as_posix()
    data = copy(source, 'draft/'+relative)
    if relative == 'develop_guard_native_augmentation.py':
        ast.parse(data)
        target = root/'scripts'/relative
    elif relative == 'GUARD_NATIVE_AUGMENTATION_DEVELOPMENT_PROTOCOL.md':
        target = root/'docs'/relative
    else:
        continue
    assert not target.exists() and b'\r' not in data
    target.write_bytes(data)
    saved = target.read_bytes()
    reads += 1
    size += len(saved)
    assert saved == data
for source, relative in (
    (root/'external/c4_l_coverage_review.md', 'static_review/coverage_review.md'),
    (root/'external/c4_l_implementation_review.md', 'static_review/implementation_review.md'),
    (root/'external/c4_l_root_review.md', 'root_review.md'),
    (root/'external/run_l_native_augmentation_once.py', 'run_l_native_augmentation_once.py'),
    (Path(__file__), 'prepare_l_native_augmentation_once.py'),
):
    copy(source, relative)
record = {'schema_version': 1, 'files': files,
          'promotion': 'exact reviewed source bytes; AST only; new engineering checks not repeated; caches excluded',
          'cost': {'binary_reads': reads, 'input_bytes': size, 'copy_checks': len(files), 'copy_failures': 0,
                   'wall_seconds': time.perf_counter()-started, 'cpu_seconds': time.process_time()-cpu},
          'actual_C_G_trace_reads': 0, 'actual_K_weight_reads': 0, 'fits': 0, 'model_calls': 0, 'physics': 0}
(out/'manifest.json').write_text(json.dumps(record, indent=2)+'\n', encoding='utf-8')
print(json.dumps({'payloads': len(files), 'cost': record['cost'],
                  'script_sha256': files['draft/develop_guard_native_augmentation.py']['sha256']}))
