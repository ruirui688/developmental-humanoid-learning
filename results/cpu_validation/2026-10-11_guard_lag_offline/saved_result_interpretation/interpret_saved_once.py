"""Read exactly three existing D reports once; scalar descriptive algebra only."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import time


source = Path('external/guard_lag_offline_20261011_first')
output = Path(__file__).resolve().parent
if (output/'interpretation.json').exists():
    raise FileExistsError('one cached read/interpretation attempt; never overwrite')
started_wall, started_cpu = time.perf_counter(), time.process_time()
cache, identities = {}, {}
for name in ('summary.json', 'diagnostics.json', 'run.json'):
    data = (source/name).read_bytes()
    identities[name] = {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}
    cache[name] = json.loads(data.decode('utf-8'))

algebra = Counter()


def ratio(candidate, baseline):
    if not isinstance(candidate, (int, float)) or not isinstance(baseline, (int, float)):
        algebra['non_numeric_ratio_unavailable'] += 1
        return None
    if baseline == 0:
        algebra['zero_denominator_ratio_unavailable'] += 1
        return None
    algebra['scalar_divisions'] += 1
    return candidate/baseline


def difference(candidate, baseline):
    if not isinstance(candidate, (int, float)) or not isinstance(baseline, (int, float)):
        return None
    algebra['scalar_subtractions'] += 1
    return candidate-baseline


metrics, comparisons, description_counts = [], [], Counter()
for trial in cache['summary.json']['trials']:
    all_metrics = [m for m in trial['metrics'] if m['group'] == 'all']
    for metric in all_metrics:
        metrics.append({'seed': trial['seed'], 'kind': trial['kind'], 'original_status': trial['original_status'],
                        'original_completed': trial['original_completed'], **metric})
    by_key = {(m['predictor'], m['axis'], m['h']): m for m in all_metrics}
    for name, baseline in (('lag_sparse11', 'sparse9'), ('lag_continuation11', 'continuation9')):
        for axis in (0, 1):
            for h in (1, 2, 5, 15):
                candidate, original = by_key[(name, axis, h)], by_key[(baseline, axis, h)]
                record = {'seed': trial['seed'], 'kind': trial['kind'], 'axis': axis, 'h': h, 'candidate': name, 'baseline': baseline,
                          'original_status': trial['original_status'], 'original_completed': trial['original_completed'],
                          'complete_window_count': candidate['complete_window_count'],
                          'candidate_available': candidate['available'], 'baseline_available': original['available'],
                          'candidate_reason': candidate['reason'], 'baseline_reason': original['reason'],
                          'candidate_mathematical_failure_count': candidate['mathematical_failure_count'],
                          'baseline_mathematical_failure_count': original['mathematical_failure_count'], 'q': None, 'v': None}
                if candidate['available'] and original['available']:
                    for variable in ('q', 'v'):
                        a, b = candidate[variable], original[variable]
                        rmse_ratio = ratio(a['rmse'], b['rmse'])
                        max_ratio = ratio(a['maximum_absolute_error'], b['maximum_absolute_error'])
                        bias_delta = difference(a['signed_bias_prediction_minus_observation'], b['signed_bias_prediction_minus_observation'])
                        record[variable] = {'candidate': a, 'baseline': b, 'rmse_ratio_candidate_over_baseline': rmse_ratio,
                                            'maximum_error_ratio_candidate_over_baseline': max_ratio,
                                            'signed_bias_delta_candidate_minus_baseline': bias_delta,
                                            'direction_rmse': 'better' if rmse_ratio is not None and rmse_ratio < 1 else 'worse' if rmse_ratio is not None and rmse_ratio > 1 else 'equal' if rmse_ratio == 1 else 'unavailable'}
                        description_counts[f'{name}|{trial["kind"]}|H{h}|{variable}|{record[variable]["direction_rmse"]}'] += 1
                        algebra['descriptive_counter_increments'] += 1
                else:
                    description_counts[f'{name}|{trial["kind"]}|H{h}|unavailable'] += 1
                    algebra['descriptive_counter_increments'] += 1
                comparisons.append(record)

diagnostics = []
for diag in cache['diagnostics.json']:
    item = {'seed': diag['seed'], 'calibration': diag['calibration'],
            'start_G_negative_counts': diag['start_G_negative_counts'], 'start_G_zero_counts': diag['start_G_zero_counts'],
            'start_G_positive_counts': diag['start_G_positive_counts'], 'hinge_nonzero_counts': diag['hinge_nonzero_counts'],
            'saved_actual_dose': diag['saved_actual_dose'], 'designs': {}, 'snapshots': {}}
    for key in ('design9', 'design11'):
        design = diag[key]
        item['designs'][key] = {field: design[field] for field in ('rows', 'columns', 'numerical_rank', 'rank_tolerance',
            'standardized_design_condition', 'standardized_gram_condition', 'condition_reason', 'constant_columns',
            'zero_variance_columns', 'standardized_design_singular_values', 'gram_singular_values', 'standardized_gram',
            'column_correlation', 'column_correlation_defined', 'coefficient_column_scale')}
    for key in ('original9_saved_coefficient_drift', 'lag11_coefficient_drift'):
        snapshots = []
        for saved in diag[key]:
            if not saved['available']:
                snapshots.append(saved)
                continue
            snap = saved['snapshot']
            snapshots.append({'vector_update_count': saved['vector_update_count'], 'change_from_vector_update_count': saved['change_from_vector_update_count'],
                'parameter_fingerprint': snap['parameter_fingerprint'], 'coefficients': snap['coefficients'],
                'raw_change_l2_per_head': saved['raw_change_l2_per_head'],
                'column_scale_weighted_change_l2_per_head': saved['column_scale_weighted_change_l2_per_head'],
                'modal_diagnostics': saved['modal_diagnostics']})
        item['snapshots'][key] = snapshots
    diagnostics.append(item)

run = cache['run.json']
record = {'schema_version': 1, 'scope': 'read-only same-development-data scalar interpretation; no model calls or gate/ranking',
          'source': {'directory': str(source), 'files': identities, 'read_opens': 3, 'read_bytes': sum(x['bytes'] for x in identities.values())},
          'source_status': run['status'], 'original_trial_metrics_all_axes_horizons': metrics,
          'matched_single_lag_comparisons_all_axes_horizons': comparisons, 'descriptive_counts': dict(description_counts),
          'saved_diagnostics': diagnostics, 'saved_run_cost_ledger': run['cost_ledger'],
          'saved_calibration_outcomes': run['calibrations'], 'saved_run_execution': run['execution'],
          'new_cost': {'source_reads': 3, 'model_fit_calls': 0, 'model_prediction_calls': 0, 'rls_updates': 0,
                       'physics_calls': 0, 'audit_reexecutions': 0, 'git_calls': 0, 'linear_algebra_calls': 0,
                       'descriptive_scalar_algebra': dict(algebra)},
          'timing': {'wall_seconds': time.perf_counter()-started_wall, 'cpu_seconds': time.process_time()-started_cpu,
                     'scope': 'three cache reads, parsing, extraction and ratios; excludes final artifact writes'}}
(output/'interpretation.json').write_text(json.dumps(record, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')

lines = ['# 首次 D 保存结果：只读解读', '',
    '同开发数据；独立首审仍在进行。本文件不判科学门，不对停止控制排名，不宣称闭环通过。', '',
    f'三文件一次缓存读取：{record["source"]["read_bytes"]} bytes。新增模型拟合/预测/物理/审计/Git/线性代数均0。', '',
    '下表为 H1/H15 的速度RMSE比值（lag11 / 对应9D；<1为此保存轨迹预测更低）。括号为共同完整窗口数。', '',
    '| seed | 原轨迹 | lag候选 | 肩H1 | 肘H1 | 肩H15 | 肘H15 | 原轨迹状态 |',
    '|---|---|---|---:|---:|---:|---:|---|']
for seed in (0, 1, 2):
    for kind in ('prediction', 'nominal_guard', 'learned_sparse', 'learned_continuation', 'PDselected', 'zero'):
        for name in ('lag_sparse11', 'lag_continuation11'):
            own = [x for x in comparisons if x['seed'] == seed and x['kind'] == kind and x['candidate'] == name]
            values = []
            for axis, h in ((0, 1), (1, 1), (0, 15), (1, 15)):
                x = next(x for x in own if x['axis'] == axis and x['h'] == h)
                value = x['v']['rmse_ratio_candidate_over_baseline'] if x['v'] else None
                values.append(f'{value:.4f} ({x["complete_window_count"]})' if value is not None else f'unavailable ({x["complete_window_count"]})')
            lines.append(f'| {seed} | {kind} | {name} | '+ ' | '.join(values)+f' | {own[0]["original_status"]} |')
lines += ['', 'JSON保留五predictor的各seed/轨迹/axis/H全部q/v RMSE、signed bias、最大误差、失败与窗口数，以及对应候选各项比值。H2/H5和不利结果没有省略。', '',
          'Gram/系数/模态均直接摘录保存字段；未重新计算SVD、特征值或模型输出。单个局部谱半径不代表真实接触系统稳定性。', '',
          '此初稿的研究解释待人工审阅上述正负结果补充；不得依据停止前预测误差采用控制器。']
(output/'INTERPRETATION.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
print(json.dumps({'read': record['source'], 'new_cost': record['new_cost'], 'timing': record['timing'],
                  'calibrations': run['calibrations'], 'diagnostic_summary': [{'seed':d['seed'],'calibration':d['calibration'],
                    'ranks':[d['designs'][k]['numerical_rank'] for k in ('design9','design11')],
                    'condition':[d['designs'][k]['standardized_design_condition'] for k in ('design9','design11')],
                    'rho9':[s['modal_diagnostics']['spectral_radius'] for s in d['snapshots']['original9_saved_coefficient_drift']],
                    'rho11':[s['modal_diagnostics']['spectral_radius'] for s in d['snapshots']['lag11_coefficient_drift']],
                    'lag_final':[r[9:11] for r in d['snapshots']['lag11_coefficient_drift'][-1]['coefficients']]}
                    for d in diagnostics], 'markdown': '\n'.join(lines)}, ensure_ascii=False, indent=2))
