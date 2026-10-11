"""Finite M output identity/count contract; no SVD or statistics recomputation."""
import hashlib
import json
from pathlib import Path
import time

root = Path(__file__).resolve().parents[1]
out = root/'external/c4_m_design_geometry_01'
report = root/'external/c4_m_output_check_01.json'
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
    docs[name] = json.loads(data)
run, diagnostic = docs['run.json'], docs['diagnostics.json']
cost = run['cost']
check('status_retained', manifest['status'] == run['status'] == diagnostic['status'])
check('bounded_algebra_cost', 0 <= cost['svd_returns'] <= cost['svd_attempts'] <= 18 and
      0 <= cost['matmul_returns'] <= cost['matmul_attempts'] <= 36 and
      len(run['operations']) == cost['svd_attempts']+cost['matmul_attempts'])
check('bounded_projection_uses', all(0 <= cost[k+'_scalar_uses_returned'] <= cost[k+'_scalar_uses_requested'] <= n
      for k, n in (('native_projection_label', 66000), ('command_projection_response', 12000))))
check('bounded_complete_estimates', all(0 <= cost[k+'_returns'] <= cost[k+'_attempts'] <= 6
      for k in ('native_projection_estimation', 'command_projection_estimation')))
check('zero_new_control_or_coefficients', all(cost[k] == 0 for k in ('physics_control_calls', 'physics_substeps',
      'RLS_updates', 'MPC_calls', 'model_restores', 'recursive_forecast_calls', 'new_parameter_space_coefficients')))
check('new_offline_estimation_declared', diagnostic['computation_type'] == 'new_offline_unregularized_projection_estimation')
check('scientific_dependencies_closed', all(diagnostic[k] is False for k in ('scientific_adoption', 'C4_passed', 'C5_passed'))
      and diagnostic['scientific_pass_threshold'] is None and diagnostic['subgroup_refits'] == 0
      and diagnostic['mixed_output_unit_loss_aggregation'] is False)
if run['status'] == 'completed':
    check('clean_source_and_full_inputs', run['source']['clean_committed_bytes_verified'] and len(run['inputs']) == 7
          and not run['inputs_without_returned_read_record'] and run['failure'] is None)
    check('all_six_qualified', run['input_qualification'] == 'all_six_validated_and_K400_L_first400_exactly_equal_each_seed')
    check('complete_cost_counts', cost['svd_attempts'] == cost['svd_returns'] == 18 and
          cost['matmul_attempts'] == cost['matmul_returns'] == 36 and cost['datasets_completed'] == 6 and
          cost['native_projection_estimation_returns'] == cost['command_projection_estimation_returns'] == 6 and
          cost['native_projection_label_scalar_uses_returned'] == cost['archived_ridge_forward_output_scalars_returned'] == 66000 and
          cost['command_projection_response_scalar_uses_returned'] == 12000)
    expected = [(s, label, n) for s in (0, 1, 2) for label, n in (('K', 400), ('L', 600))]
    check('all_fixed_datasets_retained', [(r['seed'], r['collection'], r['count']) for r in diagnostic['datasets']] == expected and
          all(r['status'] == 'completed' for r in diagnostic['datasets']))
    check('all22_output_groups_retained', sum(len(r['output_summaries']) for r in diagnostic['datasets']) == 330 and
          all(len(r['output_summaries']) == (44 if r['collection'] == 'K' else 66) for r in diagnostic['datasets']))
else:
    check('failure_reason_retained', run['failure'] is not None)
record = {'scope': 'output bytes and reported count/budget/dependency declarations only; no SVD, projection, metrics or gate recomputation',
          'first_attempt': True, 'checks': checks, 'failures': sum(not r['passed'] for r in checks),
          'cost': {'binary_reads': reads, 'input_bytes': size, 'wall_seconds': time.perf_counter()-started, 'cpu_seconds': time.process_time()-cpu},
          'actual_K_L_input_reads': 0, 'SVD_calls': 0, 'offline_estimates': 0, 'physics': 0}
report.write_text(json.dumps(record, indent=2)+'\n', encoding='utf-8')
print(json.dumps(record))
if record['failures']:
    raise SystemExit(1)
