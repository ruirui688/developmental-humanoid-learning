"""One finite output-contract check; no scientific statistics recomputation."""
import hashlib
import json
from pathlib import Path
import time

root = Path(__file__).resolve().parents[1]
out = root / 'external/c4_j_imu_residual_01'
report = root / 'external/c4_j_output_check_01.json'
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
manifest = json.loads(read(out / 'manifest.json'))
documents = {}
for name, record in manifest['files'].items():
    data = read(out/name)
    check('bytes_and_sha_' + name, len(data) == record['bytes'] and hashlib.sha256(data).hexdigest() == record['sha256'])
    if name.endswith('.json'):
        documents[name] = json.loads(data)
    elif name == 'predictions.jsonl':
        check('saved_prediction_record_count', len(data.splitlines()) == 3328)
run, metrics, cost = documents['run.json'], documents['metrics.json'], documents['run.json']['cost']
check('complete_source_inputs', run['status'] == 'completed' and len(run['inputs']) == 9 and run['diagnostic_source']['clean_committed_bytes_verified'])
check('restoration_attempts_returns', all(cost[k] == 3 for k in ('frozen_base_restorations','frozen_base_restoration_attempts','frozen_base_restoration_returns')))
check('base_prediction_cost', cost['base_model_pair_attempts'] == cost['base_model_pair_returns'] == 1500 and cost['base_model_scalar_attempts'] == cost['base_model_scalar_returns'] == 3000 and cost['saved_base_prediction_reuses'] == 1828)
check('fixed_fit_cost', cost['fit_scalar_labels'] == 2400 and cost['fit_shared_6x6_two_rhs_solve_attempts'] == cost['fit_shared_6x6_two_rhs_solve_returns'] == 3 and cost['residual_scalar_coefficients_fitted'] == 36)
check('all_fixed_groups_retained', len(metrics['groups']) == 168)
check('no_model_or_physics_updates', all(cost[k] == 0 for k in ('physics_calls','MPC_calls','base_model_updates','RLS_updates')))
check('old_scientific_dependencies_closed', all(metrics[k] is False for k in ('scientific_adoption','G_method_ranking','c4_scientific_validation','c5_scientific_dependency_released')))
check('full_common_prediction_counts', all(g['pair_count'] == g['source_active_count_ALL'] == 100 for g in metrics['groups'] if g['collection']=='C' and g['kind']=='prediction'))
record = {'scope': 'output byte identity, reported costs and declarations only; residuals, ridge and scientific gate not recomputed', 'first_attempt': True,
          'checks': checks, 'failures': sum(not c['passed'] for c in checks), 'cost': {'binary_reads': reads, 'input_bytes': size, 'wall_seconds': time.perf_counter()-started, 'cpu_seconds': time.process_time()-cpu},
          'actual_CDG_trace_reads': 0, 'fits': 0, 'model_calls': 0, 'physics_calls': 0}
report.write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
print(json.dumps(record))
