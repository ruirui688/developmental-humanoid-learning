"""One read-only human report from frozen final tables, with full provenance."""
import base64
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time

wall, cpu = time.perf_counter(), time.process_time()
root = Path(__file__).resolve().parent.parent
input_path = root/'external/local_final_review_tables_01.json'
output_path = root/'external/local_final_results_review.md'
provenance_path = root/'external/local_final_results_review_provenance_01.json'
if output_path.exists() or provenance_path.exists():
    raise SystemExit('Refusing a repeated report or overwrite.')
blob = input_path.read_bytes()
input_hash = hashlib.sha256(blob).hexdigest()
if input_hash != 'f9feee54df6d29a8cc735d0b40e114bffdfffa999abbdefd0bef02046d9e51bc':
    raise SystemExit('Frozen table input changed.')
t = json.loads(blob)
gates = t['independent_final_gates']
model, pd = gates['model_contribution_gate'], gates['classical_comparison_gate']
means = t['raw_three_seed_means']
controls = ('nominal_mpc', 'learned_mpc', 'tuned_pd', 'zero_torque')
fmt = lambda value: 'None' if value is None else f'{value:.15g}'
lines = ['# 冻结单肩最终20/21/22：独立只读复核', '',
    '结论：五 trial 同 MPC 局部模型贡献门通过；六 trial 的经典 PD 比较门失败；'
    '七 trial 的 complete_matrix 通过。可报告冻结单肩环境中的模型贡献，不能称超过强经典基线或获得站立/行走。', '',
    f'- Summary {t["checks"]:,} checks / {t["failed"]} failed，三门和逐 seed原始残差/努力/coverage/原生停止/存储更新计数'
    '均与首次 audit 对齐。独立 summary只执行一次，未重跑采集或 audit。',
    f'- 首次标准库 audit {t["authoritative_audit_checks"]:,} checks / 0 failed；audit SHA256 {t["audit_sha256"]}。',
    f'- Source commit {t["source_commit"]}，clean；固定short/old/hinge5/endpoint_euler、supine/j0、PD64/0。',
    '- 全21trial完整；0 study stop、0 environment stop、0 exception、0 blocked；'
    '6000 control/60000 physics/900RLS。20/21/22现在已揭晓，后续不能再称未见。', '',
    '## 冻结门和原始逐seed表现', '',
    '| seed | nominal tracking RMSE(rad) | learned(rad) | PD(rad) | zero(rad) | low v改善 | full v改善 |',
    '|---|---|---|---|---|---|---|']
for r in model['per_seed']:
    ev = next(s for s in t['seeds'] if s['seed'] == r['seed'])['evaluations']
    pred = r['prediction_gates']
    lines.append(f'| {r["seed"]} | {fmt(r["nominal_tracking_rmse_rad"])} | {fmt(r["learned_tracking_rmse_rad"])} | '
        f'{fmt(ev["tuned_pd"]["tracking_rmse_rad"])} | {fmt(ev["zero_torque"]["tracking_rmse_rad"])} | '
        f'{100*pred["prediction_low"]["relative_improvement"]:.9g}% | {100*pred["prediction_full"]["relative_improvement"]:.9g}% |')
lines += ['',
    f'同MPC三原始tracking均值 {fmt(model["nominal_raw_tracking_mean"])}→{fmt(model["learned_raw_tracking_mean"])} rad，'
    f'降低 {100*model["tracking_mean_improvement"]:.12g}%；三seed严格改善、low/full逐seed≤.8nominal，主门通过。', '',
    f'PD均值 {fmt(pd["pd_raw_tracking_mean"])} rad，learned改善 {100*pd["tracking_mean_improvement"]:.12g}%，'
    '低于冻结≥5%门。逐seed非劣及努力门虽通过，经典控制总门仍失败。', '',
    '| 控制 | tracking原始均值(rad) | actual ∫|u|dt(Nm·s) | actual ∫u²dt(N²m²·s) |',
    '|---|---|---|---|']
for kind in controls:
    m = means[kind]
    lines.append(f'| {kind} | {fmt(m["tracking_raw_mean_rad"])} | '
        f'{fmt(m["actual_control_effort_raw_means"]["actual_absolute_nm_s"])} | '
        f'{fmt(m["actual_control_effort_raw_means"]["actual_squared_nm2_s"])} |')
for key, e in pd['actual_effort_gates'].items():
    lines.append(f'- learned相对PD {key}增加 {100*e["relative_increase"]:.12g}%，≤5%努力门通过。')
lines += ['',
    '权限/当前目标/配对控制时域一致不等于总启动预算一致：学习控制每seed需700次物理调用'
    '（400真实校准+300自身控制trial），nominal/PD/zero每方法自身300次；共享两prediction另400次/seed作为评价成本。'
    '每trial的100零请求prefix都付费。九组PD调参和C2开发另计，不从本批总账中消失。', '',
    '## 位置与速度的独立预测诊断', '',
    '| 共同轨迹 | 指标 | nominal原始均值 | learned原始均值 | persistence原始均值 |',
    '|---|---|---|---|---|']
for kind in ('prediction_low', 'prediction_full'):
    for field in ('position_prediction_rmse', 'velocity_prediction_rmse'):
        values = means[kind][field]
        lines.append(f'| {kind} | {field} | {fmt(values["nominal_mpc"])} | {fmt(values["learned_mpc"])} | {fmt(values["persistence"])} |')
lines += ['',
    'full幅位置一步RMSE三seed均退化，不能由速度门推出所有状态预测更好。'
    '预测门来自共同低/全幅轨迹；控制自身轨迹的残差与多步误差另报，不替换门。', '',
    '## 校准支持与控制域外', '',
    '| seed/control | q域外count/200 | v域外count/200 | q或v域外count/200 | q nearest平均/最大(rad) |',
    '|---|---|---|---|---|']
for s in t['seeds']:
    for kind in controls:
        c = s['evaluations'][kind]['state_coverage']
        lines.append(f'| {s["seed"]}/{kind} | {c["q_outside_count"]} | {c["v_outside_count"]} | {c["either_outside_count"]} | '
            f'{fmt(c["nearest_q_distance_mean_rad"])} / {fmt(c["nearest_q_distance_max_rad"])} |')
lines += ['', '每seed校准300完整active输入的q/v包络与四控制200完整输入独立重算。'
    '严格越界、等值域内，nearest是q-only。高域外保留为有效域缺口，最终贡献门没有事后新增coverage阈值；'
    '也不能把通过贡献门说成覆盖修复。', '',
    '## 固定尾窗', '',
    '| seed/control/window | returned/scored/partial/missing | complete_without_stop | RMSE(rad) | mean signed(rad) | max absolute(rad) |',
    '|---|---|---|---|---|---|']
for s in t['seeds']:
    for kind in controls:
        for name, w in s['evaluations'][kind]['tail_tracking'].items():
            counts = '/'.join(str(w[k]) for k in ('returned_endpoints','scored_complete_endpoints','partial_endpoints','missing_planned_endpoints'))
            lines.append(f'| {s["seed"]}/{kind}/{name} | {counts} | {w["complete_without_stop"]} | '
                f'{fmt(w["tracking_rmse_rad"])} | {fmt(w["mean_signed_error_rad"])} | {fmt(w["maximum_absolute_error_rad"])} |')
lines += ['', '两个计划窗口各20端点：active80–99、180–199。只完整20ms转移评分，缺失不填零；'
    '完整terminal可评分但stop阻止窗口完成。描述性尾窗不能替代全部200步tracking门。', '',
    '## 多步原始RMSE均值', '',
    '下表按每seed各自完整诊断的RMSE取三个原始均值；不池化重叠窗口，校准final模型为in-sample。'
    '全部1/5/15/50步逐seed端点/路径q/v、有效/排除/terminal/非法预测窗口及分箱原值保留于JSON。'
    '未来已记录request仅作离线条件输入，零重新模型预测。', '',
    '| 轨迹/H | 模型 | endpoint q(rad) | endpoint v(rad/s) | path q(rad) | path v(rad/s) |',
    '|---|---|---|---|---|---|']
multistep_compact = []
for kind in ('calibration','prediction_low','prediction_full',*controls):
    for horizon in (1,5,15,50):
        rows = [next(r for r in s['evaluations'][kind]['audited_risk_and_multistep']['free_rollouts']
                     if r['horizon_control_steps'] == horizon) for s in t['seeds']]
        for predictor in ('nominal_mpc','learned_mpc','persistence'):
            values = [r['predictors'][predictor] for r in rows]
            fields = ('terminal_position_rmse_rad','terminal_velocity_rmse_rad_s','path_position_rmse_rad','path_velocity_rmse_rad_s')
            mm = {field: sum(v[field] for v in values)/3 if all(v[field] is not None for v in values) else None for field in fields}
            multistep_compact.append({'kind':kind,'horizon':horizon,'predictor':predictor,**mm})
            lines.append(f'| {kind}/{horizon} | {predictor} | '+' | '.join(fmt(mm[field]) for field in fields)+' |')
lines += ['', '## 风险全/前缀/active', '',
    '| seed/trial | full peak(N) | prefix peak(N) | active peak(N) | full impulse(N·s) | active max penetration(m) | active max soft excursion(rad) |',
    '|---|---|---|---|---|---|---|']
for s in t['seeds']:
    for kind, e in s['evaluations'].items():
        risk = e['audited_risk_and_multistep']
        active = 'calibration' if kind == 'calibration' else 'prediction' if kind.startswith('prediction_') else 'control'
        a, p, f = risk['phase_risk'][active], risk['phase_risk']['prefix'], risk['full_risk']
        lines.append(f'| {s["seed"]}/{kind} | {fmt(f["ground_force_peak_n"])} | {fmt(p["ground_force_peak_n"])} | '
            f'{fmt(a["ground_force_peak_n"])} | {fmt(f["ground_normal_impulse_ns"])} | '
            f'{fmt(a["maximum_penetration_m"])} | {fmt(max(a["soft_limit_excursion_peak_rad"]))} |')
lines += ['', '风险和多步/tail完整原值保留自首次audit，summary没有重新执行其模型数学。'
    '接触峰/冲量/穿透/动能取物理子步，原生速度/软限位取控制端点；未知遥测保持下界。'
    '零停止不能授予安全，prefix峰不能被active小峰遮盖。', '',
    '下一步按持续路线进入左肘的公开限位/权限/反馈与校准诊断，再验证肩—肘协调。'
    '单肩结果局部成立，经典PD比较未通过、位置与有效域缺口存在；不追加当前留出调参或采样。', '',
    '## 只读复核产物与成本', '',
    '- Summary external/local_frozen_20261011_final_summary.json，SHA256 15d0234ec4b2225d63be01e47197e51c96984cace6fb8c09084638430cfa3ed8。',
    '- 精确executed源码 external/local_final_review_summary_executed_01.py，38384 bytes，SHA256 '
    '8d88fa1c0e38813f4b16e29d01beec42f463d9eca46c618b13baf42c8f4773b8。',
    '- Summary内部wall .9615617999807s / CPU .90625s；外部wall1.18640650017187s / wrapperCPU0.0s（不含child）。',
    '- external/local_final_review_summary_stdout_01.txt 与 external/local_final_review_summary_execution_01.json'
    '保留stdout/stderr、returncode、精确源码/wrapper bytes-base64-hash、输入hash与外部clock。',
    f'- 表提取 source SHA256 {t["extraction_source_sha256"]}，wall {t["wall_seconds"]:.17g}s / CPU {t["cpu_seconds"]:.17g}s；'
    f'输出SHA256 {input_hash}，全部逐seed风险/多步/tail保留。',
    '- 本子任务0物理调用、0模型预测、0RLS数学重放、0拟合/参数更新、0新交互。统计已存原子update事件不是重新学习。',
]
text = '\n'.join(lines)+'\n'
source = Path(__file__).read_bytes()
provenance = {'schema_version':1, 'created_at_utc':datetime.now(timezone.utc).isoformat(),
    'input_path':str(input_path), 'input_sha256':input_hash,
    'source_sha256':hashlib.sha256(source).hexdigest(), 'source_bytes_base64':base64.b64encode(source).decode('ascii'),
    'output_path':str(output_path), 'output_sha256':hashlib.sha256(text.encode('utf-8')).hexdigest(),
    'wall_seconds':time.perf_counter()-wall,'cpu_seconds':time.process_time()-cpu,
    'timing_scope':'report entry through input/source reads and assembly; excludes imports and writes',
    'physical_simulation_calls':0,'model_prediction_calls':0,'rls_replay_calls':0,'real_parameter_updates':0,'new_environment_interactions':0,
    'copied_multistep_raw_rmse_three_seed_means':multistep_compact}
with output_path.open('x',encoding='utf-8',newline='\n') as stream:
    stream.write(text)
with provenance_path.open('x',encoding='utf-8',newline='\n') as stream:
    json.dump(provenance,stream,ensure_ascii=False,indent=2,allow_nan=False)
    stream.write('\n')
print(json.dumps({k:provenance[k] for k in ('output_path','output_sha256','source_sha256','wall_seconds','cpu_seconds')}))
print('\n'.join(lines[:lines.index('## 多步原始RMSE均值')]))
print('\n'.join(lines[lines.index('## 风险全/前缀/active'):lines.index('## 只读复核产物与成本')]))
print(json.dumps([r for r in multistep_compact if r['kind'] in ('learned_mpc','prediction_full') and r['horizon'] in (15,50)]))
