"""Promote reviewed M bytes; no repeat of diagnostic arithmetic checks."""
import ast
import hashlib
import json
from pathlib import Path
import time

root = Path(__file__).resolve().parents[1]
draft = root/'external/c4_design_geometry_staging'
out = root/'results/cpu_validation/2026-10-11_guard_design_geometry_preparation'
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
    if relative == 'diagnose_guard_design_geometry.py':
        ast.parse(data)
        target = root/'scripts'/relative
    elif relative == 'GUARD_DESIGN_GEOMETRY_DIAGNOSTIC_PROTOCOL.md':
        target = root/'docs'/relative
    else:
        continue
    assert not target.exists() and b'\r' not in data
    target.write_bytes(data)
    saved = target.read_bytes()
    reads += 1
    size += len(saved)
    assert data == saved
for source, relative in (
    (root/'external/c4_after_l_independent_direction.md', 'decision/independent_direction.md'),
    (root/'external/c4_after_l_direction.md', 'decision/unexecuted_kinematic_proposal.md'),
    (root/'external/c4_m_root_scope_review.md', 'decision/root_scope.md'),
    (root/'external/c4_m_implementation_review.md', 'static_review/implementation_review.md'),
    (root/'external/run_m_design_geometry_once.py', 'run_m_design_geometry_once.py'),
    (Path(__file__), 'prepare_m_design_geometry_once.py'),
):
    copy(source, relative)
record = {'schema_version': 1, 'files': files, 'promotion': 'reviewed bytes; AST only; no repeated passed checks',
          'cost': {'binary_reads': reads, 'input_bytes': size, 'copy_checks': len(files), 'copy_failures': 0,
                   'wall_seconds': time.perf_counter()-started, 'cpu_seconds': time.process_time()-cpu},
          'actual_parameter_payload_reads': 0, 'SVD_calls': 0, 'offline_estimates': 0, 'physics': 0}
(out/'manifest.json').write_text(json.dumps(record, indent=2)+'\n', encoding='utf-8')
print(json.dumps({'payloads': len(files), 'cost': record['cost']}))
