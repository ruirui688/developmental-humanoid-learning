"""Bind existing N checks and first failures; no model/metric computation."""
import hashlib
import json
from pathlib import Path
import time

root = Path(__file__).resolve().parents[1]
stage = root/'external/c4_scaled_native_staging'
target = stage/'INTEGRITY.json'
assert not target.exists()
started, cpu = time.perf_counter(), time.process_time()
reads, size = 0, 0

def read(path):
    global reads, size
    data = path.read_bytes()
    reads += 1
    size += len(data)
    return data

first = json.loads(read(stage/'CHECK_01.json'))
supplement = json.loads(read(stage/'CHECK_02.json'))
assert first['passed'] is False
assert [(r['case'], r['status']) for r in first['cases']] == [
    ('scale_equivalence', 'passed'), ('zero_rejection', 'passed'),
    ('near_zero_risk', 'passed'), ('failure_partial', 'failed')]
assert supplement['passed'] and [(r['case'], r['status']) for r in supplement['cases']] == [('failure_partial', 'passed')]
for name in ('develop_guard_scaled_native_transition.py', 'GUARD_SCALED_NATIVE_TRANSITION_DEVELOPMENT_PROTOCOL.md'):
    assert first['source_sha256'][name] == supplement['source_sha256'][name] == hashlib.sha256(read(stage/name)).hexdigest()
first_fixture = json.loads(read(stage/'CHECK_01.fixtures/solve_failure/run.json'))
assert first_fixture['failure']['type'] == 'KeyError' and first_fixture['cost']['fit_attempts'] == 0
files = {}
for path in sorted(stage.rglob('*')):
    if path.is_file() and '__pycache__' not in path.parts:
        data = read(path)
        files[path.relative_to(stage).as_posix()] = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
record = {'schema_version': 1, 'files': files, 'first_check_passed': False,
          'all_four_cases_covered_after_fixture_only_supplement': True,
          'previous_three_passed_cases_repeated': False,
          'first_fixture_failure': first_fixture['failure'],
          'first_fixture_cost': first_fixture['cost'],
          'check_cost_records': {
              'CHECK_01': {'wall_seconds_before_serialization': first['wall_seconds_before_serialization'],
                           'cpu_seconds_before_serialization': first['cpu_seconds_before_serialization'],
                           'cases': [{'case': r['case'], 'status': r['status'],
                                      'detail': r.get('detail'), 'journal': r.get('journal')} for r in first['cases']]},
              'CHECK_02': {'wall_seconds_before_serialization': supplement['wall_seconds_before_serialization'],
                           'cpu_seconds_before_serialization': supplement['cpu_seconds_before_serialization'],
                           'cases': supplement['cases']}},
          'scope': 'existing reported check status and file identities only; no new mathematical checks',
          'cost': {'binary_reads': reads, 'input_bytes': size, 'wall_seconds': time.perf_counter()-started,
                   'cpu_seconds': time.process_time()-cpu},
          'actual_payload_reads': 0, 'model_fits': 0, 'model_predictions': 0, 'physics': 0}
with target.open('x', encoding='utf-8') as handle:
    json.dump(record, handle, indent=2)
    handle.write('\n')
print(json.dumps({'payloads_bound': len(files), 'first_check_passed': False,
                  'all_four_cases_covered_after_fixture_only_supplement': True, 'cost': record['cost']}))
