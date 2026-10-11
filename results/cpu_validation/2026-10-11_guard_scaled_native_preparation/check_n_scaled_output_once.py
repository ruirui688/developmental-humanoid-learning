"""Finite N byte/count/dependency contract; no metrics or model recomputation."""
import hashlib
import json
from pathlib import Path
import time

root = Path(__file__).resolve().parents[1]
out = root/'external/c4_n_scaled_native_01'
report = root/'external/c4_n_output_check_01.json'
assert not report.exists()
started, cpu = time.perf_counter(), time.process_time()
reads, size, checks = 0, 0, []

def read(path):
    global reads, size
    data = path.read_bytes()
    reads += 1
    size += len(data)
    return data

def check(name, condition):
    checks.append({'name': name, 'passed': bool(condition)})

manifest = json.loads(read(out/'manifest.json'))
docs, prediction_count = {}, None
for name, binding in manifest['files'].items():
    data = read(out/name)
    check('bytes_and_sha_'+name, len(data) == binding['bytes'] and
          hashlib.sha256(data).hexdigest() == binding['sha256'])
    if name.endswith('.json'):
        docs[name] = json.loads(data)
    elif name == 'predictions.jsonl':
        prediction_count = data.count(b'\n')
run, metrics, parameters = docs['run.json'], docs['metrics.json'], docs['parameters.json']
cost = run['cost']
check('status_retained', manifest['status'] == run['status'] == metrics['status'])
check('new_fit_bounded', 0 <= cost['fit_returns'] <= cost['fit_attempts'] <= 3 and
      0 <= cost['fit_shared_29x29_22rhs_solve_returns'] <= cost['fit_shared_29x29_22rhs_solve_attempts'] <= 3 and
      0 <= cost['fit_scalar_labels_returned'] <= cost['fit_scalar_labels_requested'] <= 26400 and
      0 <= cost['transition_scalar_coefficients_fitted'] <= 1914)
check('zero_physics_and_old_refits', all(cost[k] == 0 for k in
      ('physics_calls', 'physics_substeps', 'RLS_updates', 'MPC_calls', 'K22_refits', 'D11_updates')))
check('scientific_dependencies_closed', all(run[k] is False and metrics[k] is False for k in
      ('scientific_adoption', 'c4_scientific_validation', 'c5_scientific_dependency_released')))
if run['status'] == 'completed':
    gate = metrics['development_gate']
    check('clean_source_and_full_inputs', run['source']['clean_committed_bytes_verified'] and
          len(run['inputs']) == 9 and not run['inputs_without_returned_read_record'] and run['failure'] is None)
    check('all_fixed_new_fits', cost['fit_attempts'] == cost['fit_returns'] == 3 and cost['fit_failures'] == 0 and
          cost['fit_shared_29x29_22rhs_solve_attempts'] == cost['fit_shared_29x29_22rhs_solve_returns'] == 3 and
          cost['fit_scalar_labels_returned'] == 26400 and cost['transition_scalar_coefficients_fitted'] == 1914 and
          cost['scale_estimation_attempts'] == cost['scale_estimation_returns'] == 3)
    check('all_seed_scale_definitions_retained', [r['seed'] for r in parameters] == [0, 1, 2] and
          all(r['available'] and r['uncentered_column_RMS'] and r['scale_floor'] is None and
              r['scale_search'] is False and len(r['fit']['scale29']) == 29 and
              len(r['training_transition_ids']) == 400 for r in parameters))
    check('all_baselines_frozen', run['K22_fingerprints_before'] == run['K22_fingerprints_after'] and
          run['D11_fingerprints_before'] == run['D11_fingerprints_after'] and
          cost['K22_restoration_returns'] == cost['D11_restoration_returns'] == 3)
    check('all_prediction_records_and_channels_retained', prediction_count == 3429 and len(metrics['groups']) == 576)
    check('all_fixed_channel_counts_reported', all(r['record_count'] == 101-r['horizon'] and
          r['fixed_origin_count'] == 101-r['horizon'] and r['source_active_count'] == 100 and
          r['partial_subset_method_ranking'] is False for r in metrics['groups']))
    check('both_original_gates_and_status_retained', set(gate['comparisons']) == {'N22_vs_K22', 'N22_vs_D11'} and
          all(len(g['checks']) == 14 for g in gate['comparisons'].values()) and
          gate['passed'] == run['development_gate_passed'] == metrics['development_gate_passed'] and
          all(gate[k] is False for k in ('scientific_adoption', 'c4_scientific_validation',
                                       'c5_scientific_dependency_released')))
else:
    check('first_failure_and_partial_retained', run['failure'] is not None and 'failure.json' in docs and
          docs['failure.json']['failure'] == run['failure'])
record = {'scope': 'output bytes and reported count/budget/dependency declarations only; no fitting, rollout, metric or gate recomputation',
          'first_attempt': True, 'checks': checks, 'failures': sum(not r['passed'] for r in checks),
          'cost': {'binary_reads': reads, 'input_bytes': size, 'wall_seconds': time.perf_counter()-started,
                   'cpu_seconds': time.process_time()-cpu},
          'actual_input_reads': 0, 'model_fits': 0, 'model_predictions': 0, 'physics': 0}
with report.open('x', encoding='utf-8') as handle:
    json.dump(record, handle, indent=2)
    handle.write('\n')
print(json.dumps(record))
if record['failures']:
    raise SystemExit(1)
