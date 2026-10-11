"""Original bytes and canonical promotion of the minimal I diagnostic."""
import ast
import hashlib
import json
from pathlib import Path
import time

root = Path(__file__).resolve().parents[1]
draft = root / 'external/c4_h_residual_diagnostic_staging'
out = root / 'results/cpu_validation/2026-10-11_guard_native_residual_preparation'
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
for name in ('diagnose_guard_pd_tail_native_residual.py', 'GUARD_PD_TAIL_NATIVE_RESIDUAL_DIAGNOSTIC_PROTOCOL.md',
             'test_native_residual_staging.py', 'CHECK_01.json', 'INTEGRITY.json'):
    data = copy(draft / name, 'draft/' + name)
    if name == 'diagnose_guard_pd_tail_native_residual.py':
        data = copy(root / 'external/c4_i_failure_provenance_revision' / name, 'revision/' + name)
        ast.parse(data)
        assert b'\r' not in data
        target = root / 'scripts' / name
    elif name == 'GUARD_PD_TAIL_NATIVE_RESIDUAL_DIAGNOSTIC_PROTOCOL.md':
        assert b'\r' not in data
        target = root / 'docs' / name
    else:
        continue
    assert not target.exists()
    target.write_bytes(data)
    saved = target.read_bytes()
    reads += 1
    size += len(saved)
    assert saved == data
copy(root / 'external/c4_i_review/REVIEW.md', 'static_review/REVIEW.md')
copy(root / 'external/c4_native_observation_review/REVIEW.md', 'native_observation_review/REVIEW.md')
for name in ('REVISION.json', 'REVISION.patch'):
    copy(root / 'external/c4_i_failure_provenance_revision' / name, 'revision/' + name)
copy(root / 'external/run_i_native_residual_once.py', 'run_i_native_residual_once.py')
copy(Path(__file__), 'prepare_i_native_residual_once.py')
record = {'schema_version': 1, 'files': files,
          'canonical_promotion': 'draft protocol; only script failure-source revision, AST parse, eight passed small checks not repeated',
          'cost': {'binary_reads': reads, 'input_bytes': size, 'copy_checks': len(files), 'copy_failures': 0,
                   'wall_seconds': time.perf_counter()-started, 'cpu_seconds': time.process_time()-cpu},
          'formal_I_runs': 0, 'H_payload_reads': 0, 'model_calls': 0, 'physics_calls': 0}
(out / 'manifest.json').write_text(json.dumps(record, indent=2)+'\n', encoding='utf-8')
print(json.dumps({'files': len(files), 'cost': record['cost'], 'canonical_source_sha256': files['revision/diagnose_guard_pd_tail_native_residual.py']['sha256']}))
