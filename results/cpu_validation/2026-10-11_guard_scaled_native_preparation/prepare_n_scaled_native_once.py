"""Promote reviewed N source/protocol and preserve the first preparation bytes."""
import hashlib
import json
from pathlib import Path
import time

root = Path(__file__).resolve().parents[1]
stage = root/'external/c4_scaled_native_staging'
out = root/'results/cpu_validation/2026-10-11_guard_scaled_native_preparation'
source_pairs = ((stage/'develop_guard_scaled_native_transition.py',
                 root/'scripts/develop_guard_scaled_native_transition.py'),
                (stage/'GUARD_SCALED_NATIVE_TRANSITION_DEVELOPMENT_PROTOCOL.md',
                 root/'docs/GUARD_SCALED_NATIVE_TRANSITION_DEVELOPMENT_PROTOCOL.md'))
assert all(src.is_file() and not dst.exists() for src, dst in source_pairs)
assert not out.exists()
started, cpu = time.perf_counter(), time.process_time()
out.mkdir(parents=True)
files, reads, size = {}, 0, 0

def copy(path, relative):
    global reads, size
    data = path.read_bytes()
    target = out/relative
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('xb') as handle:
        handle.write(data)
    saved = target.read_bytes()
    reads += 2
    size += len(data)+len(saved)
    assert saved == data
    files[relative] = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
                       'copy_verified': True}

for path in sorted(stage.rglob('*')):
    if path.is_file() and '__pycache__' not in path.parts:
        assert path.resolve().is_relative_to(stage.resolve())
        copy(path, 'draft/'+path.relative_to(stage).as_posix())
for name, relative in (
    ('c4_after_m_direction.md', 'decision/independent_direction.md'),
    ('c4_m_interpretation_review.md', 'decision/M_interpretation_review.md'),
    ('c4_n_implementation_review.md', 'static_review/implementation_review.md'),
    ('prepare_n_scaled_native_once.py', 'prepare_n_scaled_native_once.py'),
    ('run_n_scaled_native_once.py', 'run_n_scaled_native_once.py'),
    ('run_n_scaled_synthetic_once.py', 'run_n_scaled_synthetic_once.py'),
    ('run_n_failed_fixture_once.py', 'run_n_failed_fixture_once.py'),
    ('seal_n_preparation_once.py', 'seal_n_preparation_once.py'),
    ('check_n_scaled_output_once.py', 'check_n_scaled_output_once.py')):
    copy(root/'external'/name, relative)
promoted = {}
for src, dst in source_pairs:
    data = src.read_bytes()
    with dst.open('xb') as handle:
        handle.write(data)
    saved = dst.read_bytes()
    reads += 2
    size += len(data)+len(saved)
    assert saved == data
    promoted[dst.relative_to(root).as_posix()] = {'bytes': len(data),
        'sha256': hashlib.sha256(data).hexdigest()}
record = {'schema_version': 1, 'files': files, 'promoted': promoted,
          'cost': {'binary_reads': reads, 'input_bytes': size,
                   'copy_checks': len(files)+len(promoted), 'copy_failures': 0,
                   'wall_seconds': time.perf_counter()-started,
                   'cpu_seconds': time.process_time()-cpu},
          'actual_payload_reads': 0, 'actual_fits': 0, 'actual_forecasts': 0, 'physics': 0}
(out/'manifest.json').write_text(json.dumps(record, indent=2)+'\n', encoding='utf-8')
print(json.dumps({'payloads': len(files), 'promoted': promoted, 'cost': record['cost']}))
