"""Finite L output contract; no scientific metric or model recomputation."""
import hashlib
import json
from pathlib import Path
import time

root = Path(__file__).resolve().parents[1]
out = root/'external/c4_l_native_augmentation_02'
report = root/'external/c4_l_output_check_02.json'
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
docs = {}
for name, binding in manifest['files'].items():
    data = read(out/name)
    check('bytes_and_sha_'+name, len(data) == binding['bytes'] and hashlib.sha256(data).hexdigest() == binding['sha256'])
    if name.endswith('.json'):
        docs[name] = json.loads(data)
    elif name == 'predictions.jsonl' and manifest['status'] == 'completed':
        check('all_fixed_prediction_records', len(data.splitlines()) == 3429)
if manifest['status'] == 'failed':
    failure = docs['failure.json']
    cost = failure['cost']
    check('failed_run_preserved', failure['status'] == 'failed')
    check('scientific_dependencies_closed', all(failure[k] is False for k in ('scientific_adoption', 'both_development_gates_passed',
        'c4_scientific_validation', 'c5_scientific_dependency_released')))
    record = {'scope': 'failed-run byte identity and declared zero compute only; no source reload, models or gate recomputation',
              'first_attempt': True, 'checks': checks, 'failures': sum(not r['passed'] for r in checks),
              'cost': {'binary_reads': reads, 'input_bytes': size, 'wall_seconds': time.perf_counter()-started, 'cpu_seconds': time.process_time()-cpu},
              'actual_C_G_K_source_payload_reads': 0, 'fits': 0, 'model_calls': 0, 'physics': 0}
    report.write_text(json.dumps(record, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(record))
    raise SystemExit(int(bool(record['failures'])))
run, metrics = docs['run.json'], docs['metrics.json']
cost = run['cost']
check('complete_source_inputs', run['status'] == 'completed' and len(run['inputs']) == 12 and run['source']['clean_committed_bytes_verified'])
check('frozen_baselines_immutable', all(cost[n+'_restoration_attempts'] == cost[n+'_restoration_returns'] == 3 and
    run[n+'_fingerprints_before'] == run[n+'_fingerprints_after'] for n in ('K22', 'D11')))
check('fixed_fit_budget', cost['fit_scalar_labels'] <= 39600 and cost['fit_shared_29x29_22rhs_solve_attempts'] <= 3 and
    cost['fit_shared_29x29_22rhs_solve_returns'] <= cost['fit_shared_29x29_22rhs_solve_attempts'] and cost['transition_scalar_coefficients_fitted'] <= 1914)
check('fixed_rollout_budgets', all(cost[k] <= 6204 for k in ('K22_transition_attempts', 'L22_transition_attempts', 'D11_pair_prediction_attempts')) and cost['D11_scalar_prediction_attempts'] <= 12408)
check('all_channel_groups_retained', len(metrics['groups']) == 576)
check('all_source_trial_counts', all(run['source_active_counts'][f'seed{s}_{k}'] == n for s in (0, 1, 2)
    for k, n in (('calibration_sparse', 400), ('prediction', 100), ('PDselected', 200))))
check('zero_new_physics_RLS_baseline_fits', all(cost[k] == 0 for k in ('physics_calls', 'physics_substeps', 'MPC_calls', 'RLS_updates', 'D11_updates', 'K22_refits')))
gates = (metrics['data_augmentation_gate'], metrics['matched_D11_gate'])
check('separate_named_gates', [g['name'] for g in gates] == ['L22_vs_K22_data_augmentation', 'L22_vs_D11_original_K_rules'] and
    metrics['both_development_gates_passed'] == all(g['passed'] for g in gates) and
    metrics['new_holdout_control_development_eligible'] == metrics['both_development_gates_passed'])
check('scientific_dependencies_closed', all(metrics[k] is False for k in ('scientific_adoption', 'c4_scientific_validation', 'c5_scientific_dependency_released', 'G_PD_method_ranking')) and all(g['old_K_D_gates_reinterpreted'] is False for g in gates))
record = {'scope': 'byte identity and reported count/budget/dependency declarations only; no model, metrics or gate recomputation',
          'first_attempt': True, 'checks': checks, 'failures': sum(not r['passed'] for r in checks),
          'cost': {'binary_reads': reads, 'input_bytes': size, 'wall_seconds': time.perf_counter()-started, 'cpu_seconds': time.process_time()-cpu},
          'actual_C_G_K_source_payload_reads': 0, 'fits': 0, 'model_calls': 0, 'physics': 0}
report.write_text(json.dumps(record, indent=2)+'\n', encoding='utf-8')
print(json.dumps(record))
if record['failures']:
    raise SystemExit(1)
