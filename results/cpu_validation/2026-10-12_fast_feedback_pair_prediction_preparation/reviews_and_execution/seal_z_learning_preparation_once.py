"""Seal new model/controller checks and preparation receipts without experiments."""
import ast
import hashlib
import json
from pathlib import Path
import time

repo = Path(__file__).resolve().parents[1]
target = repo / 'results/cpu_validation/2026-10-12_fast_feedback_pair_prediction_preparation'
target.mkdir(exist_ok=False)
began, cpu = time.perf_counter(), time.process_time()
cost = dict(file_reads=0, read_bytes=0, file_writes=0, write_bytes=0)
files = {}
def read(path):
    data = path.read_bytes()
    cost['file_reads'] += 1
    cost['read_bytes'] += len(data)
    return data
def identity(data):
    return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
def copy(source, relative):
    data = read(source)
    dest = target / relative
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open('xb') as stream:
        stream.write(data)
    cost['file_writes'] += 1
    cost['write_bytes'] += len(data)
    assert read(dest) == data
    files[relative.as_posix()] = {**identity(data), 'source': source.relative_to(repo).as_posix()}
    return data
checks = repo / 'external/c4_z_learning_checks_01'
record = json.loads(read(checks / 'execution.json'))
assert record['returncode'] == 0
for name, pin in record['source_files'].items():
    assert identity(copy(repo / name, Path('source') / name)) == pin
tree = ast.parse((target / 'source/scripts/develop_fast_feedback_pair.py').read_bytes())
pin = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'PROTOCOL_PIN' for t in n.targets))
assert pin == record['source_files']['docs/FAST_FEEDBACK_LEARNING_PROTOCOL.md']
for path in sorted(checks.rglob('*')):
    if path.is_file():
        copy(path, Path('first_checks') / path.relative_to(checks))
for path in sorted((repo / 'external/z_learning_candidate').rglob('*')):
    if path.is_file():
        copy(path, Path('external_originals') / path.relative_to(repo / 'external/z_learning_candidate'))
for name in ('c4_z_learning_design_receipt.json', 'c4_z_pair_model_static_review.json', 'c4_z_learning_publication.json', 'publish_z_learning_once.py', 'run_z_learning_checks_once.py', 'prepare_z_learning_helpers_once.py', 'run_fast_pair_once.py', 'archive_fast_pair_stage_once.py', 'seal_z_learning_preparation_once.py'):
    copy(repo / 'external' / name, Path('reviews_and_execution') / name)
result = {'status': 'prepared_not_scientifically_validated', 'files': files, 'first_seven_new_checks_passed': True, 'final_protocol_pin_matches': True, 'assembly_or_old_tests_repeated': False, 'physics_fit_or_formal_RLS_calls_in_sealing': 0, 'cost_before_manifest_write': dict(cost), 'wall_seconds_before_manifest_write': time.perf_counter()-began, 'cpu_seconds_before_manifest_write': time.process_time()-cpu, 'automatic_retry': False}
data = (json.dumps(result, indent=2, allow_nan=False)+'\n').encode()
with (target / 'manifest.json').open('xb') as stream:
    stream.write(data)
cost['file_writes'] += 1
cost['write_bytes'] += len(data)
print(json.dumps({'payloads': len(files), 'cost': cost, 'wall_seconds': time.perf_counter()-began, 'cpu_seconds': time.process_time()-cpu}))
