"""Byte-preserving J preparation; exact canonical promotion after review."""
import ast
import hashlib
import json
from pathlib import Path
import time

root = Path(__file__).resolve().parents[1]
draft = root / 'external/c4_imu_residual_development_staging'
out = root / 'results/cpu_validation/2026-10-11_guard_imu_residual_preparation'
out.mkdir(parents=True, exist_ok=False)
started, cpu = time.perf_counter(), time.process_time()
files, reads, size = {}, 0, 0
def copy(source, relative):
    global reads, size
    data = source.read_bytes()
    target = out / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    saved = target.read_bytes()
    reads += 2
    size += len(data)+len(saved)
    assert data == saved, relative
    files[relative] = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(), 'copy_verified': True}
    return data
assert (draft / 'CHECK_01.json').exists() and (draft / 'INTEGRITY.json').exists()
for source in sorted(draft.iterdir()):
    if not source.is_file():
        continue
    data = copy(source, 'draft/' + source.name)
    if source.name == 'develop_guard_imu_residual.py':
        ast.parse(data)
        assert b'\r' not in data
        target = root / 'scripts' / source.name
    elif source.name == 'GUARD_IMU_RESIDUAL_DEVELOPMENT_PROTOCOL.md':
        assert b'\r' not in data
        target = root / 'docs' / source.name
    else:
        continue
    assert not target.exists()
    target.write_bytes(data)
    saved = target.read_bytes()
    reads += 1
    size += len(saved)
    assert saved == data
copy(root / 'external/c4_j_review/REVIEW.md', 'static_review/REVIEW.md')
copy(root / 'external/c4_j_root_review.md', 'root_review.md')
copy(root / 'external/run_j_imu_residual_once.py', 'run_j_imu_residual_once.py')
copy(Path(__file__), 'prepare_j_imu_residual_once.py')
record = {'schema_version': 1, 'files': files, 'promotion': 'exact reviewed draft bytes; AST parse only; passed checks not repeated',
          'cost': {'binary_reads': reads, 'input_bytes': size, 'copy_checks': len(files), 'copy_failures': 0,
                   'wall_seconds': time.perf_counter()-started, 'cpu_seconds': time.process_time()-cpu},
          'actual_source_trace_reads': 0, 'formal_fits': 0, 'model_calls': 0, 'physics_calls': 0}
(out / 'manifest.json').write_text(json.dumps(record, indent=2)+'\n', encoding='utf-8')
print(json.dumps({'payloads': len(files), 'cost': record['cost'], 'script_sha256': files['draft/develop_guard_imu_residual.py']['sha256']}))
