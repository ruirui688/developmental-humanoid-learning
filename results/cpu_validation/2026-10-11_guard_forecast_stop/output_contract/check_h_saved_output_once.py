"""Finite H output contract and saved-value inspection; no statistic recomputation."""
import hashlib
import json
from pathlib import Path
import time

root = Path(__file__).resolve().parents[1]
source = root / 'external/c4_h_forecast_stop_01'
output = root / 'external/c4_h_output_check_01.json'
assert not output.exists()
started, cpu = time.perf_counter(), time.process_time()
reads, size = 0, 0
def read(name):
    global reads, size
    data = (source / name).read_bytes()
    reads += 1
    size += len(data)
    return data
manifest = json.loads(read('manifest.json'))
blobs = {name: read(name) for name in manifest['files']}
checks = []
def check(name, value):
    checks.append({'name': name, 'passed': bool(value)})
for name, data in blobs.items():
    expected = manifest['files'][name]
    check('output_bytes_' + name, len(data) == expected['bytes'] and hashlib.sha256(data).hexdigest() == expected['sha256'])
run = json.loads(blobs['run.json'])
description = json.loads(blobs['description.json'])
intervals = [json.loads(x) for x in blobs['intervals.jsonl'].splitlines()]
last20 = [json.loads(x) for x in blobs['last20.jsonl'].splitlines()]
check('completed_fixed_identity', run['status'] == 'completed' and run['diagnostic_source']['commit'] == 'a46633c71e95826835ebc43f0aeaf6d5fdfd19e8' and run['diagnostic_source']['clean_committed_bytes_verified'])
check('no_scientific_adoption', run['scientific_adoption'] is False and description['scientific_adoption'] is False)
check('exact_five_G_input_reads', run['cost']['G_input_file_reads'] == 5)
check('zero_model_updates_physics', all(run['cost'][x] == 0 for x in ('model_predictions', 'model_updates', 'physics_calls')))
check('fixed_twelve_groups_six_trials', len(description['groups']) == 12 and len(description['trials']) == 6)
check('saved_active_counts', len(intervals) == run['cost']['selected_active_records_described'] == sum(x['saved_active_count'] for x in description['trials']) == sum(x['saved_active_count'] for x in description['groups']))
check('fixed_last20_counts', len(last20) == sum(x['last20_count'] for x in description['trials']))
check('partial_and_missing_remain_explicit', all((x['interval_effort']['complete_20ms_interval'] or all(x[k]['absolute_error_qv'] is None for k in ('independent_current_request_prediction', 'selected_stage0_prediction'))) and (x['forecast_category'] == 'valid_selected_h15' or not x['selected_stage0_prediction']['prediction_available']) for x in last20))
check('old_c4_gate_remains_false', description['original_G_final_gates']['c4_scientific_validation']['passed'] is False)
terminal = []
for trial in description['trials']:
    tail = [x for x in last20 if x['trial_id'] == trial['trial_id']]
    final = tail[-1] if tail else None
    interval = next((x for x in reversed(intervals) if x['trial_id'] == trial['trial_id']), None)
    terminal.append({'trial': trial, 'last_saved_interval': interval, 'last_saved_endpoint': final})
report = {'checks': checks, 'passed': sum(x['passed'] for x in checks), 'failed': sum(not x['passed'] for x in checks),
          'groups_copied_without_recomputation': description['groups'], 'terminal_saved_values': terminal,
          'H_cost_copied': run['cost'], 'H_inputs_copied': run['inputs'],
          'output_manifest_sha256': hashlib.sha256((json.dumps(manifest) if False else b'')).hexdigest() if False else None,
          'check_cost': {'input_reads': reads, 'input_bytes': size, 'wall_seconds': time.perf_counter()-started, 'cpu_seconds': time.process_time()-cpu},
          'scope': 'output bytes, fixed counts, missing/partial contract and copied saved values; no H re-run, scientific statistic, old G audit, model or physics'}
output.write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
print(json.dumps({'passed': report['passed'], 'failed': report['failed'], 'H_cost': run['cost'], 'groups': description['groups'], 'terminal': terminal, 'check_cost': report['check_cost']}))
