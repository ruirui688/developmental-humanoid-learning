"""Transcribe the new FR3D projection once; no raw or model access."""
from pathlib import Path
import hashlib
import json

root = Path(__file__).resolve().parents[1]
source = root/'external/fr3d_first/result/projection.json'
report = root/'docs/FULL_REQUEST_PAIR_TRADEOFF_RESULTS.md'
receipt = root/'external/fr3d_report_receipt.json'
assert not report.exists() and not receipt.exists(), 'first report exists; no rerun'
data = source.read_bytes()
r = json.loads(data)
assert r['status'] == 'saved_projection_complete' and not r['failures']
archive = '../results/cpu_validation/2026-10-12_full_request_pair_tradeoff/'
def vector(values):
    return '/'.join('NA' if x is None else f'{x:.9g}' for x in values)
parts = ['# FR3D：完整首请求控制的关节与阶段取舍\n\n'
         'FR3B原模型贡献门通过，正式强PD门失败：总RMSE改善5.8823%，肘退化18.1937%，两种实际努力超限。'
         '本轮只描述首次保存的轨迹，不重算或改判这些门，不增加物理、模型调用、fit或更新。\n\n'
         '[原控制结果](FULL_REQUEST_PAIR_CONTROL_RESULTS.md) · '
         f'[冻结诊断设计]({archive}frozen_design.md) · [全部新投影]({archive}result/projection.json) · '
         f'[首次执行与来源]({archive}manifest.json)\n\n'
         '固定8001/8002/8003×cold/learned/pd九组。A=active0–999，B=1000–1999；'
         'pre=900–999、post=1000–1099，各200ms且包含在A/B内。不同控制方法的真实状态不同，'
         '同index差分是描述，不是匹配状态反事实。缺失保持NA，不部分排名或按峰值挑窗口。\n\n'
         '实际努力为保存2ms原生执行器端点的样本积分估计，不是连续积分、能量或安全指标。'
         '原full2000跟踪/努力只从run转录到JSON，没有重新计算原RMSE、接触或科学百分比。\n\n'
         '## 全部轴与固定窗口\n\n'
         '| seed/方法 | scope/轴 | available/known/planned | SSE rad² | signed mean rad | MAE rad | max abs rad | actual abs Nm·s | actual squared Nm²·s |\n'
         '|---|---|---|---:|---:|---:|---:|---:|---:|\n']
for row in r['matrix']:
    for scope, item in row['scopes'].items():
        for axis, a in enumerate(item['axes']):
            values = [a['error_squared_sum'], a['mean_signed_error_rad'], a['mean_absolute_error_rad'],
                      a['error_abs_max'], a['complete_actual_absolute_nm_s'], a['complete_actual_squared_nm2_s']]
            parts.append(f"| {row['seed']}/{row['method']} | {scope}/{'肩' if axis == 0 else '肘'} | "
                         f"{a['available']}/{a['error_known']}/{a['planned_rows']} | " +
                         ' | '.join('NA' if x is None else f'{x:.9g}' for x in values) + ' |\n')
parts.append('\n## learned−PD的全部固定窗口差分\n\n'
             'SSE差分为正表示该窗口误差平方和更高，不是原RMSE门的新百分比。\n\n'
             '| seed | scope/轴 | available | SSE差 | actual abs差 | actual squared差 |\n|---|---|---|---:|---:|---:|\n')
for row in r['learned_minus_PD_scope_differences']:
    d = row['learned_minus_PD']
    parts.append(f"| {row['seed']} | {row['scope']}/{row['axis']} | {row['available']} | " +
                 ' | '.join('NA' if x is None else f'{x:.9g}' for x in d.values()) + ' |\n')
parts.append('\n## 保存macro的PD候选存在性\n\n'
             '两轴当前保存PD精确属于九点grid才存在delta=(0,0)。fallback未保存PD时不补算。'
             'nearest是每轴最小绝对残差距离；已选残差超出它的部分不代表错误选择。'
             '网格只规定macro首请求，后九步native反馈请求仍连续变化。\n\n'
             '| seed/方法 | scope | macros/PD known/unknown | purePD存在/缺失 | 存在且可行/不可行/可行性未知 | nearest距离和 肩/肘 | 已选abs(delta)和 肩/肘 | 超出nearest的和 肩/肘 |\n'
             '|---|---|---|---|---|---|---|---|\n')
for row in r['matrix']:
    if row['method'] == 'pd':
        continue
    for scope, item in row['scopes'].items():
        m = item['macro']
        parts.append(f"| {row['seed']}/{row['method']} | {scope} | {m['macros']}/{m['PD_known']}/{m['PD_unknown']} | "
                     f"{m['pure_PD_present']}/{m['pure_PD_absent']} | {m['pure_PD_feasible']}/{m['pure_PD_infeasible']}/{m['pure_PD_present_feasibility_unknown']} | "
                     f"{vector(m['nearest_grid_distance_sum_nm'])} | {vector(m['selected_abs_delta_sum_nm'])} | "
                     f"{vector(m['selected_delta_excess_over_nearest_sum_nm'])} |\n")
parts.append('\n固定switch窗与所属phase的全部SSE/努力比例见JSON，零分母或未知为NA；没有扫描窗口。'
             '以上存在性、距离与误差/努力同现只能提出结构问题，不能识别其造成肘退化或努力增加。\n\n'
             '## 实际新增费用与边界\n\n| 新保存投影counter | 值 |\n|---|---:|\n')
for key, value in r['cost'].items():
    parts.append(f'| {key} | {value} |\n')
parts.append(f"\n内部wall={r['wall_seconds_before_output']:.9g}s、CPU={r['cpu_seconds_before_output']:.9g}s；"
             '只读本次manifest/run/trace各一次。旧raw、models、predictions、journal和sourceZIP读取0；'
             '模型、PD方法、rollout、cost/tie重放、fit、RLS、物理调用0。报告只读新投影一次。\n\n'
             '正式物理累计保持430,297控制调用/2,709,970子步；在线94,452+离线7,200=101,652scalar更新计算。'
             '本轮0新增交互/学习，不将描述计数当新身体能力。\n\n'
             '## 继续推进\n\n'
             '接着根据固定分解作唯一有界控制结构判断，另在新开发数据前冻结源码、协议、seed和原门。'
             '不扩大候选数量、扫描权重/增益、增加辨识剂量或补跑FR3；不放宽20%/5%/1.05原门。'
             'C4完整新留出以及C5–C7仍未验收，五科学flags保持false。阶段检查、提交、推送后立即继续active目标。\n')
report.write_text(''.join(parts), encoding='utf-8', newline='\n')
value = {'input': {'path': str(source), 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
                   'file_reads': 1, 'JSON_parses': 1}, 'status': 'written', 'raw_reads': 0,
         'model_fit_RLS_physics_or_scientific_gate_calls': 0, 'document': str(report)}
receipt.write_text(json.dumps(value, indent=2)+'\n', encoding='utf-8')
for row in r['matrix']:
    if row['method'] not in ('learned', 'pd'):
        continue
    print(json.dumps({'seed': row['seed'], 'method': row['method'],
        'A_B': {scope: {'SSE': [x['error_squared_sum'] for x in row['scopes'][scope]['axes']],
                       'actual_abs': [x['actual_absolute_nm_s'] for x in row['scopes'][scope]['axes']],
                       'actual_squared': [x['actual_squared_nm2_s'] for x in row['scopes'][scope]['axes']],
                       'macro': row['scopes'][scope]['macro']} for scope in ('A', 'B')}}, ensure_ascii=False))
print(json.dumps(value))
