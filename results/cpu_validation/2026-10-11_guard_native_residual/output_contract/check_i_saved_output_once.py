"""Finite I output contract and copied metrics; no residual-score recomputation."""
import hashlib
import json
from pathlib import Path
import time

root = Path(__file__).resolve().parents[1]
source = root / 'external/c4_i_native_residual_01'
output = root / 'external/c4_i_output_check_01.json'
assert not output.exists()
started, cpu = time.perf_counter(), time.process_time()
reads, size = 0, 0
def read(name):
    global reads, size
    data = (source / name).read_bytes()
    reads += 1
    size += len(data)
    return data
manifest_bytes = read('manifest.json')
manifest = json.loads(manifest_bytes)
blobs = {name: read(name) for name in manifest['files']}
checks = []
def check(name, value):
    checks.append({'name': name, 'passed': bool(value)})
for name, data in blobs.items():
    expected = manifest['files'][name]
    check('output_bytes_' + name, len(data) == expected['bytes'] and hashlib.sha256(data).hexdigest() == expected['sha256'])
run = json.loads(blobs['run.json'])
description = json.loads(blobs['description.json'])
pairs = [json.loads(x) for x in blobs['adjacent_pairs.jsonl'].splitlines()]
check('completed_source_binding', run['status'] == 'completed' and run['diagnostic_source']['clean_committed_bytes_verified'] and len(run['diagnostic_source']['commit']) == 40)
check('four_pinned_H_reads', run['cost']['H_input_file_reads'] == 4 and run['inputs']['manifest.json']['sha256'] == 'b3c9969c6d65987c0993c32e0143a7f5f4e704410d5d4e7cbe423a950b5ed538')
check('zero_model_RLS_physics', all(run['cost'][x] == 0 for x in ('model_predictions', 'model_updates', 'RLS_updates', 'physics_calls')))
check('old_scientific_dependencies', description['scientific_adoption'] is False and description['c4_scientific_validation'] is False and description['c5_scientific_dependency_released'] is False)
check('fixed_96_groups_six_trials', len(description['groups']) == 96 and len(description['source_trials']) == 6)
check('paired_count_matches', len(pairs) == run['cost']['adjacent_pairs'])
check('first_or_unavailable_history_explicit', len(pairs) + len(description['unscored_records']) == run['cost']['last20_records_parsed'])
check('current_labels_not_declared_inputs', all(x['current_actual_used_in_correction'] is False and x['current_step_index'] == x['previous_step_index']+1 and x['current_active_index'] == x['previous_active_index']+1 for x in pairs))
check('primary_learned_gate_consistent', run['primary_development_gate_passed'] == description['primary_development_gate_passed'] == description['development_gates_by_kind']['learned_sparse11']['passed'])
all_velocity = [x for x in description['groups'] if x['segment'] == 'ALL' and x['signal'] == 'v']
terminal = [next((x for x in reversed(pairs) if x['trial_id'] == trial['trial_id']), None) for trial in description['source_trials']]
report = {'checks': checks, 'passed': sum(x['passed'] for x in checks), 'failed': sum(not x['passed'] for x in checks),
          'source_commit': run['diagnostic_source']['commit'], 'output_manifest_sha256': hashlib.sha256(manifest_bytes).hexdigest(),
          'gates_copied': description['development_gates_by_kind'], 'ALL_velocity_metrics_copied': all_velocity,
          'terminal_pairs_copied': terminal, 'I_cost_copied': run['cost'],
          'check_cost': {'input_reads': reads, 'input_bytes': size, 'wall_seconds': time.perf_counter()-started, 'cpu_seconds': time.process_time()-cpu},
          'scope': 'fixed output contract and saved metrics only; no I rerun, residual score/gate recomputation, H/G reads, model or physics'}
output.write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
print(json.dumps({'passed': report['passed'], 'failed': report['failed'], 'output_manifest_sha256': report['output_manifest_sha256'], 'gates': report['gates_copied'], 'terminal_pairs': terminal, 'I_cost': run['cost'], 'check_cost': report['check_cost']}))
