"""One bounded projection of saved FR3B axis/phase tradeoffs; stdlib only."""
import argparse
from collections import Counter
import gzip
import hashlib
import io
import json
import math
from pathlib import Path
import sys
import time
import traceback

SEEDS = (8001, 8002, 8003)
METHODS = ('cold', 'learned', 'pd')
GRID = (-.5, -.375, -.25, -.125, 0., .125, .25, .375, .5)
SCOPES = {'A': (0, 1000), 'B': (1000, 2000),
          'switch_pre': (900, 1000), 'switch_post': (1000, 1100)}
PARENT_COMMIT = '20e899a48d3b92211c09c3589fe710b16cb692d3'
FLAGS = ('scientific_adoption', 'old_free_root_C4_validation', 'c4_scientific_validation',
         'c4_contact_scientific_validation', 'c5_scientific_dependency_released')


def identity(data):
    return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def bad_constant(value):
    raise ValueError('nonfinite_JSON_constant:' + value)


def load(data):
    return json.loads(data, parse_constant=bad_constant)


def pair(values):
    if not isinstance(values, (list, tuple)) or len(values) != 2:
        return None
    if not all(type(x) in (int, float) and math.isfinite(x) for x in values):
        return None
    return tuple(float(x) for x in values)


def axis_stats():
    return {'rows': 0, 'error_known': 0, 'error_sum': 0., 'error_abs_sum': 0.,
            'error_squared_sum': 0., 'error_abs_max': None, 'effort_known': 0,
            'actual_absolute_nm_s': 0., 'actual_squared_nm2_s': 0.}


def macro_stats():
    return {'macros': 0, 'fallback_known': 0, 'fallback': 0,
            'PD_known': 0, 'pure_PD_present': 0, 'pure_PD_feasible_known': 0,
            'pure_PD_feasible': 0, 'nearest_grid_distance_sum_nm': [0., 0.],
            'delta_known': 0, 'selected_abs_delta_sum_nm': [0., 0.],
            'selected_delta_excess_over_nearest_sum_nm': [0., 0.]}


def finish_axis(stats, planned, complete):
    row = dict(stats)
    row['planned_rows'] = planned
    available = complete and row['rows'] == row['error_known'] == row['effort_known'] == planned
    row['available'] = available
    row['mean_signed_error_rad'] = row['error_sum']/planned if available else None
    row['mean_absolute_error_rad'] = row['error_abs_sum']/planned if available else None
    row['mean_squared_error_rad2'] = row['error_squared_sum']/planned if available else None
    if not available:
        # Retain observed accumulators with their counts, but no complete-scope score.
        row['complete_actual_absolute_nm_s'] = row['complete_actual_squared_nm2_s'] = None
    else:
        row['complete_actual_absolute_nm_s'] = row['actual_absolute_nm_s']
        row['complete_actual_squared_nm2_s'] = row['actual_squared_nm2_s']
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', default='.')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    repo, output = Path(args.repo).resolve(), Path(args.output).resolve()
    if output.exists():
        raise FileExistsError('first projection output exists; no rerun')
    output.mkdir(parents=True)
    raw = repo/'results/cpu_validation/2026-10-12_full_request_pair_control/raw'
    wall, cpu = time.perf_counter(), time.process_time()
    cost = Counter()
    pins, failures, run = {}, [], {}
    groups = {(seed, method): {'seed': seed, 'method': method, 'trial': {}, 'score': {},
              'seen_active': set(), 'scopes': {name: {'axes': [axis_stats(), axis_stats()],
                          'macro': macro_stats()} for name in SCOPES}}
              for seed in SEEDS for method in METHODS}
    seen = {f'FR3_{seed}_control_{method}': set() for seed in SEEDS
            for method in (*METHODS, 'zero')}

    def read(name, cap):
        path = raw/name
        if path.stat().st_size > cap:
            raise ValueError('input size cap exceeded:' + name)
        cost['input_read_attempts'] += 1
        data = path.read_bytes()
        cost['input_read_returns'] += 1
        cost['input_bytes'] += len(data)
        pins[name] = identity(data)
        return data

    try:
        manifest = load(read('manifest.json', 4*1024*1024))
        run = load(read('run.json', 16*1024*1024))
        compressed = read('trace.jsonl.gz', 128*1024*1024)
        if run.get('experiment_id') != 'FR3B' or run.get('stage') != 'control':
            raise ValueError('only canonical physical FR3B required')
        if run.get('source', {}).get('commit') != PARENT_COMMIT:
            raise ValueError('exact parent physical source commit required')
        if run.get('status') != 'completed' or run.get('failure') is not None:
            raise ValueError('completed parent required; no partial ranking')
        for name in ('run.json', 'trace.jsonl.gz'):
            if manifest.get('files', {}).get(name) != pins[name]:
                raise ValueError('parent payload pin differs:' + name)
        for saved in run.get('seed_results', []):
            seed = saved.get('seed')
            if seed not in SEEDS:
                raise ValueError('unexpected seed')
            for method in METHODS:
                group = groups[seed, method]
                group['trial'] = saved.get('controls', {}).get(method, {})
                group['score'] = saved.get('tracking_scores', {}).get(method, {})
        with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as stream:
            while True:
                line = stream.readline(1024*1024 + 1)
                if not line:
                    break
                cost['decoded_bytes'] += len(line)
                cost['trace_rows'] += 1
                if len(line) > 1024*1024 or cost['decoded_bytes'] > 512*1024*1024 or cost['trace_rows'] > 36000:
                    raise ValueError('trace decode cap exceeded')
                row = load(line)
                trial_id, index = row.get('trial_id'), row.get('control_index')
                if trial_id not in seen or type(index) is not int or not 0 <= index < 3000 or index in seen[trial_id]:
                    raise ValueError('bounded unique parent control row required')
                seen[trial_id].add(index)
                if row.get('phase') == 'prefix':
                    continue
                phase_index = row.get('phase_index')
                method = trial_id.rsplit('_', 1)[1]
                seed = row.get('seed')
                if row.get('phase') != 'active' or type(phase_index) is not int or not 0 <= phase_index < 2000:
                    raise ValueError('bounded active phase required')
                if method == 'zero':
                    continue
                if (seed, method) not in groups:
                    raise ValueError('unexpected main-group row')
                group = groups[seed, method]
                if phase_index in group['seen_active']:
                    raise ValueError('duplicate active index')
                group['seen_active'].add(phase_index)
                cost['main_active_rows'] += 1
                error = pair(row.get('target_error_rad'))
                actual8 = row.get('observation_after', {}).get('actuator_torque')
                actual = pair(actual8[:2]) if isinstance(actual8, list) and len(actual8) == 8 else None
                paid = row.get('confirmed_completed_substeps') == 1 and row.get('complete_native_endpoint') is True
                selected_scopes = [name for name, (start, end) in SCOPES.items() if start <= phase_index < end]
                macro = None
                if 'planning_decision' in row:
                    if method not in ('cold', 'learned') or phase_index % 10:
                        raise ValueError('macro scope differs')
                    cost['macros'] += 1
                    if cost['macros'] > 1200:
                        raise ValueError('macro cap exceeded')
                    decision = row['planning_decision']
                    if not isinstance(decision, dict):
                        raise ValueError('saved decision object required')
                    p = pair(row.get('public_pd_request2'))
                    delta = pair(decision.get('selected_residual_nm'))
                    nearest, present, feasible = None, None, None
                    if p is not None:
                        nearest = tuple(min(abs(value-grid) for grid in GRID) for value in p)
                        cost['nearest_grid_scalar_distances'] += 18
                        present = all(value in GRID for value in p)
                        if present:
                            candidates = decision.get('candidate_records')
                            if not isinstance(candidates, list) or len(candidates) != 81:
                                raise ValueError('saved 81-candidate array required')
                            selected = candidates[GRID.index(p[0])*9 + GRID.index(p[1])]
                            cost['pure_PD_candidate_records_read'] += 1
                            feasible = selected.get('feasible')
                    macro = (decision.get('fallback'), p, delta, nearest, present, feasible)
                for name in selected_scopes:
                    cost['row_scope_projections'] += 1
                    stats = group['scopes'][name]
                    for axis, item in enumerate(stats['axes']):
                        cost['axis_scope_updates'] += 1
                        item['rows'] += 1
                        if error is not None and paid:
                            e = error[axis]
                            item['error_known'] += 1
                            item['error_sum'] += e
                            item['error_abs_sum'] += abs(e)
                            item['error_squared_sum'] += e*e
                            item['error_abs_max'] = max(item['error_abs_max'] or 0., abs(e))
                        if actual is not None and paid:
                            t = actual[axis]
                            item['effort_known'] += 1
                            item['actual_absolute_nm_s'] += abs(t)*.002
                            item['actual_squared_nm2_s'] += t*t*.002
                    if macro is not None:
                        cost['macro_scope_updates'] += 1
                        cost['macro_axis_scope_projections'] += 2
                        fallback, p, delta, nearest, present, feasible = macro
                        item = stats['macro']
                        item['macros'] += 1
                        if type(fallback) is bool:
                            item['fallback_known'] += 1
                            item['fallback'] += fallback
                        if p is not None:
                            item['PD_known'] += 1
                            item['pure_PD_present'] += present
                            if type(feasible) is bool:
                                item['pure_PD_feasible_known'] += 1
                                item['pure_PD_feasible'] += feasible
                            for axis in range(2):
                                item['nearest_grid_distance_sum_nm'][axis] += nearest[axis]
                        if delta is not None and p is not None:
                            item['delta_known'] += 1
                            for axis in range(2):
                                value = abs(delta[axis])
                                item['selected_abs_delta_sum_nm'][axis] += value
                                item['selected_delta_excess_over_nearest_sum_nm'][axis] += max(0., value-nearest[axis])
        if cost['row_scope_projections'] > 19800 or cost['axis_scope_updates'] > 39600 or cost['macro_scope_updates'] > 1320:
            raise ValueError('scope projection cap exceeded')
        if cost['nearest_grid_scalar_distances'] > 21600 or cost['pure_PD_candidate_records_read'] > 1200:
            raise ValueError('grid projection cap exceeded')
    except BaseException as exc:
        failures.append({'type': type(exc).__name__, 'message': str(exc), 'traceback': traceback.format_exc()})
    matrix = []
    for (seed, method), group in groups.items():
        trial = group['trial']
        complete = trial.get('complete') is True and not failures
        for stats in group['scopes'].values():
            macro = stats['macro']
            macro.update(PD_unknown=macro['macros']-macro['PD_known'],
                         pure_PD_absent=macro['PD_known']-macro['pure_PD_present'],
                         pure_PD_infeasible=macro['pure_PD_feasible_known']-macro['pure_PD_feasible'],
                         pure_PD_present_feasibility_unknown=macro['pure_PD_present']-macro['pure_PD_feasible_known'],
                         pure_PD_presence_denominator=macro['PD_known'],
                         pure_PD_unknown_denominator=macro['macros'],
                         pure_PD_feasibility_denominator=macro['pure_PD_present'])
        matrix.append({'seed': seed, 'method': method, 'parent_complete': trial.get('complete'),
            'parent_status': trial.get('status'), 'parent_stop': trial.get('stop'),
            'whole_2000_tracking_scores_transcribed': group['score'],
            'whole_2000_actual_effort_transcribed': trial.get('actual_effort', {}).get('active'),
            'scopes': {name: {'axes': [finish_axis(item, SCOPES[name][1]-SCOPES[name][0], complete)
                                     for item in stats['axes']], 'macro': stats['macro']}
                       for name, stats in group['scopes'].items()}})
    differences, window_shares = [], []
    indexed = {(row['seed'], row['method']): row for row in matrix}
    for seed in SEEDS:
        for name in SCOPES:
            for axis in range(2):
                learned = indexed[seed, 'learned']['scopes'][name]['axes'][axis]
                pd = indexed[seed, 'pd']['scopes'][name]['axes'][axis]
                known = learned['available'] and pd['available']
                cost['axis_sse_effort_difference_entries'] += 3
                differences.append({'seed': seed, 'scope': name, 'axis': axis, 'available': known,
                    'learned_minus_PD': {key: learned[key]-pd[key] if known else None for key in (
                        'error_squared_sum', 'actual_absolute_nm_s', 'actual_squared_nm2_s')}})
    for row in matrix:
        for window, parent in (('switch_pre', 'A'), ('switch_post', 'B')):
            for axis in range(2):
                part = row['scopes'][window]['axes'][axis]
                whole = row['scopes'][parent]['axes'][axis]
                known = part['available'] and whole['available']
                cost['fixed_window_parent_ratios'] += 3
                window_shares.append({'seed': row['seed'], 'method': row['method'],
                    'window': window, 'parent': parent, 'axis': axis,
                    'ratios': {key: part[key]/whole[key] if known and whole[key] > 0. else None
                               for key in ('error_squared_sum', 'actual_absolute_nm_s', 'actual_squared_nm2_s')}})
    result = {'experiment_id': 'FR3D', 'status': 'saved_projection_complete' if not failures else 'first_projection_failed',
        'failures': failures, 'input_identities': pins, 'parent_source_commit': PARENT_COMMIT,
        'matrix': matrix, 'learned_minus_PD_scope_differences': differences,
        'fixed_switch_window_shares_of_parent_scope': window_shares,
        'cost': dict(cost), 'scope_intervals_half_open': SCOPES,
        'full_RMSE_effort_and_scientific_gates_recomputed': False,
        'local_axis_error_sums_and_actual_effort_recomputed': True,
        'model_PD_method_rollout_cost_tie_fit_RLS_physics_calls': 0,
        'models_prediction_journal_source_ZIP_old_raw_reads': 0,
        'macro_grid_does_not_quantize_all_native_feedback_requests': True,
        'causal_inference': False, 'partial_subset_ranking': False, 'automatic_retry': False,
        'scientific_flags': {name: False for name in FLAGS},
        'wall_seconds_before_output': time.perf_counter()-wall,
        'cpu_seconds_before_output': time.process_time()-cpu, 'python': sys.version}
    payload = (json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)+'\n').encode()
    (output/'projection.json').write_bytes(payload)
    (output/'candidate_source.py').write_bytes(Path(__file__).read_bytes())
    receipt = {'status': result['status'], 'projection': identity(payload),
               'first_execution': True, 'automatic_retry': False,
               'script': identity((output/'candidate_source.py').read_bytes())}
    (output/'first_execution_receipt.json').write_text(json.dumps(receipt, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'status': result['status'], 'failures': failures, 'cost': dict(cost)}, ensure_ascii=False))
    return int(bool(failures))


if __name__ == '__main__':
    raise SystemExit(main())
