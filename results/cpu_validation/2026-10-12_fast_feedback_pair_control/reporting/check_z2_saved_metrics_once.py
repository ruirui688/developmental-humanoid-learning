"""Independently verify new Z2 tracking/effort and conditional endpoint RMSE."""
from collections import defaultdict
import gzip
import hashlib
import json
import math
from pathlib import Path
import time

repo = Path(__file__).resolve().parents[1]
raw = repo / 'results/cpu_validation/2026-10-12_fast_feedback_pair_control/raw'
out = repo / 'external/c4_z2_new_metrics_check.json'
if out.exists():
    raise FileExistsError(out)
began, cpu = time.perf_counter(), time.process_time()
pins = {}
def read(name):
    data = (raw / name).read_bytes()
    pins[name] = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
    return data
run = json.loads(read('run.json'))
tracking = defaultdict(lambda: [[], []])
effort = defaultdict(lambda: {'abs': [], 'squared': [], 'substeps': 0})
trace_data = gzip.decompress(read('trace.jsonl.gz'))
trace_rows = 0
for line in trace_data.splitlines():
    row = json.loads(line)
    trace_rows += 1
    key = (row['trial_id'], row['phase'])
    samples = (row.get('diagnostics') or row.get('saved_partial') or {}).get('substep_native_and_contact_records', [])
    for sample in samples:
        actual = sample['actual_actuator_torque8']
        if len(actual) != 8 or not all(math.isfinite(v) for v in actual):
            continue
        effort[key]['substeps'] += 1
        effort[key]['abs'].append(.002*(abs(actual[0])+abs(actual[1])))
        effort[key]['squared'].append(.002*(actual[0]**2+actual[1]**2))
    if row['phase'] == 'active' and row.get('returned') is True and row.get('observation_after') is not None:
        q = row['observation_after']['joint_position']
        target = row['current_target_q2']
        for axis in range(2):
            error = q[axis]-target[axis]
            assert math.isfinite(error)
            tracking[row['trial_id']][axis].append(error*error)
checks, skipped = [], []
def close(values, saved):
    return all(math.isclose(c, s, rel_tol=1e-11, abs_tol=1e-14) for c, s in zip(values, saved))
for seed_row in run['seed_results']:
    for name, trial in seed_row['controls'].items():
        trial_id = trial['trial_id']
        for phase in ('prefix', 'active'):
            got, saved = effort[(trial_id, phase)], trial['actual_effort'][phase]
            assert got['substeps'] == saved['captured_substeps']
            values = [math.fsum(got['abs']), math.fsum(got['squared'])]
            expected = [saved['actual_absolute_two_axis_nm_s'], saved['actual_squared_two_axis_nm2_s']]
            assert close(values, expected)
            checks.append({'trial': trial_id, 'phase': phase, 'kind': 'new_actual_effort', 'computed': values, 'saved': expected, 'passed': True})
        score = seed_row['tracking_scores'][name]
        if score['available']:
            errors = tracking[trial_id]
            assert len(errors[0]) == len(errors[1]) == score['planned_active_count'] == 2000
            axis = [math.sqrt(math.fsum(e)/len(e)) for e in errors]
            joint = math.sqrt(math.fsum(errors[0]+errors[1])/4000)
            expected = [*score['axis_rmse_rad'], score['joint_rmse_rad']]
            assert close([*axis, joint], expected)
            checks.append({'trial': trial_id, 'kind': 'new_tracking_RMSE', 'computed': [*axis, joint], 'saved': expected, 'passed': True})
        else:
            skipped.append({'trial': trial_id, 'kind': 'tracking', 'reason': 'saved_complete_population_unavailable'})
del trace_data
groups = defaultdict(lambda: {'q': [[], []], 'v': [[], []]})
population = defaultdict(int)
prediction_data = gzip.decompress(read('predictions.jsonl.gz'))
prediction_rows = 0
for line in prediction_data.splitlines():
    row = json.loads(line)
    prediction_rows += 1
    if not row['available']:
        continue
    key = (row['trial_id'], row['horizon'], row['model'])
    population[key] += 1
    for signal in ('q', 'v'):
        path = row['predicted_'+signal+'_path']
        assert len(path) == row['horizon']
        actual = row['actual_endpoint_'+signal+'2']
        for axis in range(2):
            error = path[-1][axis]-actual[axis]
            assert math.isfinite(error)
            groups[key][signal][axis].append(error*error)
conditional_vectors = 0
for seed_row in run['seed_results']:
    for trial_score in seed_row['conditional_prediction_scores'].values():
        for h, horizon in trial_score['horizons'].items():
            for model, metrics in horizon['models'].items():
                key = (trial_score['trial_id'], int(h), model)
                assert population[key] == metrics['observed_origin_count']
                if not metrics['available']:
                    skipped.append({'trial': key[0], 'horizon': key[1], 'model': model, 'reason': 'saved_complete_population_unavailable'})
                    continue
                assert population[key] == horizon['planned_origin_count']
                for signal, field in [('q', 'q_rmse_axis_rad'), ('v', 'v_rmse_axis_rad_s')]:
                    computed = [math.sqrt(math.fsum(e)/len(e)) for e in groups[key][signal]]
                    assert close(computed, metrics[field])
                    conditional_vectors += 1
                    checks.append({'trial': key[0], 'horizon': key[1], 'model': model, 'signal': signal, 'kind': 'new_conditional_RMSE', 'computed': computed, 'saved': metrics[field], 'passed': True})
record = {'status': 'passed', 'checks': checks, 'skipped': skipped, 'trace_rows': trace_rows, 'prediction_rows': prediction_rows, 'new_conditional_RMSE_vectors': conditional_vectors, 'source_files': pins, 'reads': len(pins), 'read_bytes': sum(p['bytes'] for p in pins.values()), 'wall_seconds': time.perf_counter()-began, 'cpu_seconds': time.process_time()-cpu, 'model_fit_physics_calls': 0, 'old_scientific_metrics_recomputed': False, 'automatic_retry': False}
with out.open('x', encoding='utf-8') as stream:
    json.dump(record, stream, indent=2, allow_nan=False)
print(json.dumps({k: v for k, v in record.items() if k not in ('checks', 'skipped', 'source_files')}))
