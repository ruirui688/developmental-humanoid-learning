"""Write one human-readable review from frozen C2-C summary/table artifacts."""
import base64
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time

wall, cpu = time.perf_counter(), time.process_time()
root = Path(__file__).resolve().parent.parent
tables_path = root/'external/c2c_review_tables_01.json'
review_path = root/'external/c2c_results_review.md'
provenance_path = root/'external/c2c_results_review_provenance_01.json'
if review_path.exists() or provenance_path.exists():
    raise SystemExit('Refusing report overwrite or repeat.')
blob = tables_path.read_bytes()
table_hash = hashlib.sha256(blob).hexdigest()
if table_hash != '945384a2c40c411e7b85f3134e87d920bcb57014ef7433647d594bad8a3b7bf6':
    raise SystemExit('Frozen table input changed.')
t = json.loads(blob)
gate = t['independent_adoption_gate']
p = gate['performance_gate']
means = t['raw_three_seed_means']
low = means['prediction_low']['velocity_prediction_rmse']
full = means['prediction_full']['velocity_prediction_rmse']
lines = [
    '# C2-C development 独立只读复核', '',
    '正式数据与首次审计完成后，仅执行一次 summary；随后各一次只读表提取与文稿生成。'
    '不运行物理、模型预测、RLS 数学重放、参数拟合或新留出。', '',
    '结论：保持 old 剂量、hinge5、endpoint_euler、short 时序。reordered 的覆盖门与表现门均失败；'
    '3 个开发 seed 均完整，数据一致性成功与算法采用失败是不同的结论。', '',
    f'- Summary：{t["checks"]:,} checks，{t["failed"]} failed；逐 seed 原始残差、努力、'
    '校准/控制输入包络、原生停止和存储的成功原子更新计数与首次 audit 对齐。',
    '- 首次 audit：963,372 checks / 0 failed；12 条历史锚轨迹精确复现。风险与多步诊断完整保留自首次 audit，'
    '本 summary 没有重新执行风险遥测数学核验或模型预测。',
    '- 正式原始数据 source commit：a2fe5c2c19602d759bd98b882000753036645432（clean）。',
    '- 21/21 completed；0 study stop、0 environment stop、0 exception、0 blocked。'
    '6300 control steps / 63000 physics substeps / 1800 RLS updates。',
    '- Prefix 2100/21000，calibration 1800/18000，prediction 600/6000，control 1800/18000。'
    '每个 prefix 和两次独立校准的成本都计入。', '',
    '## 覆盖门', '',
    '每 seed 的 short/reordered 两参考控制轨迹上，重排校准 q 域外均为 187/200 = 93.5%，'
    'short 校准为 194/200 = 97%。重排虽然增加 q 方向跨度，仍远高于冻结的 ≤20/200 =10% 门。'
    'short 参考轨迹上 v 域外 seed0 23→24、seed1 24→25、seed2 22→22；'
    'reordered 参考轨迹依次 22→22、24→23、22→22。不能跨控制轨迹替换比较。', '',
    '| seed | short q offset 包络(rad) | reordered q offset 包络(rad) | short v 包络(rad/s) | reordered v 包络(rad/s) |',
    '|---|---|---|---|---|',
]
for s in t['seeds']:
    a, b = s['calibration_support']['short'], s['calibration_support']['reordered']
    def envelope(values):
        return '['+', '.join(f'{x:.12g}' for x in values)+']'
    lines.append(f'| {s["seed"]} | {envelope(a["q_offset_envelope_rad"])} | {envelope(b["q_offset_envelope_rad"])} | '
                 f'{envelope(a["velocity_envelope_rad_s"])} | {envelope(b["velocity_envelope_rad_s"])} |')
lines += ['', '全部包络使用 300 个完整 active 原生输入。每个控制轨迹使用 200 个完整输入；严格越界、'
    '等值域内。nearest q-only 逐轨迹/逐 seed 原值在 summary/table；不是 q/v 距离或安全集合。', '',
    '## 表现门', '',
    '| seed | short tracking RMSE(rad) | reordered tracking RMSE(rad) | low v RMSE short→reordered(rad/s) | full v RMSE short→reordered(rad/s) |',
    '|---|---|---|---|---|']
for r in p['per_seed']:
    a, b = r['prediction_gates']['prediction_low'], r['prediction_gates']['prediction_full']
    lines.append(f'| {r["seed"]} | {r["short_tracking_rmse_rad"]:.15g} | {r["reordered_tracking_rmse_rad"]:.15g} | '
        f'{a["short_velocity_rmse"]:.15g} → {a["reordered_velocity_rmse"]:.15g} | '
        f'{b["short_velocity_rmse"]:.15g} → {b["reordered_velocity_rmse"]:.15g} |')
lines += ['',
    f'三原始 tracking RMSE 均值 {p["short_raw_tracking_mean"]:.17g} → '
    f'{p["reordered_raw_tracking_mean"]:.17g} rad，改善 {100*p["tracking_mean_improvement"]:.12g}%，低于 ≥5% 门。'
    '三 seed tracking 非劣通过，但不足以通过总表现门。', '',
    f'低幅速度 RMSE 均值 {low["short_mpc"]:.17g} → {low["reordered_mpc"]:.17g} rad/s，'
    f'增加 {100*(low["reordered_mpc"]/low["short_mpc"]-1):.12g}%；三 seed 均退化。'
    f'full 均值 {full["short_mpc"]:.17g} → {full["reordered_mpc"]:.17g} rad/s，'
    f'改善 {100*(1-full["reordered_mpc"]/full["short_mpc"]):.12g}%；三 seed 均通过，但不能替代 low 门。', '',
    'actual control 努力的两门均通过：']
for key, effort in p['actual_effort_gates'].items():
    lines.append(f'- {key}: {effort["short_mean"]:.17g} → {effort["reordered_mean"]:.17g}，'
        f'增加 {100*effort["relative_increase"]:.12g}%。')
lines += ['', '两校准的 requested 与 actual |u|/u² 积分均约 0.55 N·m·s / 0.20 N²·m²·s（仅浮点求和舍入差）。'
    '本次命令权限未被屏蔽，所以这里实际校准努力也相同；这一事实不能推广为所有环境的保证。'
    '时序变化同时改变 q/v 暴露、接触与辨识顺序，不能称为单独 q 覆盖的因果收益。', '',
    '## 风险与证据边界', '',
    '下表保留所有 7 类 trial 的 full/prefix/active 接触峰与冲量，并列出 control phase 的原生端点软限位越界。'
    '完整 per-phase 风险、接触穿透、动能、各关节速度/干预，以及 conditional/free rollout 原值在 JSON 中。'
    '不合并窗口为独立样本，不按较好 seed 或块选择。', '',
    '| seed/trial | full peak(N) | prefix peak(N) | active peak(N) | full impulse(N·s) | control max soft excursion(rad) |',
    '|---|---|---|---|---|---|']
for s in t['seeds']:
    for kind, ev in s['evaluations'].items():
        risk = ev['audited_risk_and_multistep']
        active = 'calibration' if kind.startswith('calibration_') else 'prediction' if kind.startswith('prediction_') else 'control'
        phases = risk['phase_risk']
        lines.append(f'| {s["seed"]}/{kind} | {risk["full_risk"]["ground_force_peak_n"]:.12g} | '
            f'{phases["prefix"]["ground_force_peak_n"]:.12g} | {phases[active]["ground_force_peak_n"]:.12g} | '
            f'{risk["full_risk"]["ground_normal_impulse_ns"]:.12g} | '
            f'{max(risk["control_risk"]["soft_limit_excursion_peak_rad"]):.12g} |')
lines += ['',
    '零停止与完整遥测只说明冻结包络内这一小型开发矩阵完成；不证明安全、未见泛化、独立动作成熟、'
    '冷启动站立/行走或真机可用。原生速度/软限位风险是控制端点采样，接触峰/冲量/穿透含物理子步。'
    'prefix 风险不能用 active 小峰掩盖。', '',
    '下一阶段使用已选 short/old/hinge5/endpoint_euler 按冻结最终协议比较同 MPC 的 nominal/learned，'
    '再以独立门比较 PD；留出 20/21/22 仍未读取或运行于本子任务。q 预测退化、覆盖缺口与多步结果须完整报告。', '',
    '## 复现产物与只读成本', '',
    '- Summary 原件：external/local_coverage_20261011_development_summary.json',
    '- Summary SHA256：f6658949cbcecbc1f425db77c11f41d64aaa861b3a919ef87d3f91242c000163',
    '- 精确执行源码：external/c2c_review_summary_executed_01.py（36660 bytes）',
    '- 执行源码 SHA256：d9b36fe54013d0214658e7e5ca4db70f37ad5bb090d452ca302d0d0a82c31efe',
    '- Summary 内部 wall 1.0529676999431103 s / CPU 0.984375 s；外部 wall 1.253389999968931 s / '
    'wrapper CPU 0.0 s（外部 CPU 不含 child）。',
    '- external/c2c_review_summary_stdout_01.txt 与 external/c2c_review_summary_execution_01.json '
    '保留 stdout/stderr、返回码、精确 executed bytes/base64/hash、wrapper bytes/base64/hash、输入 hash 和时域。',
    f'- 单次 table extraction SHA256：{t["extraction_source_sha256"]}，wall {t["wall_seconds"]:.17g} s / '
    f'CPU {t["cpu_seconds"]:.17g} s；输出 SHA256：{table_hash}。',
    '- 0 次物理、0 次模型预测、0 次 RLS 数学重放、0 次真实参数更新、0 次新交互；'
    '统计已有 update 事件与 snapshot 不属于重新学习。',
]
text = '\n'.join(lines)+'\n'
source = Path(__file__).read_bytes()
provenance = {'schema_version': 1, 'created_at_utc': datetime.now(timezone.utc).isoformat(),
    'input_path': str(tables_path), 'input_sha256': table_hash,
    'source_sha256': hashlib.sha256(source).hexdigest(), 'source_bytes_base64': base64.b64encode(source).decode('ascii'),
    'output_path': str(review_path), 'output_sha256': hashlib.sha256(text.encode('utf-8')).hexdigest(),
    'wall_seconds': time.perf_counter()-wall, 'cpu_seconds': time.process_time()-cpu,
    'timing_scope': 'entry through input/source read and report assembly, excludes imports and output writes',
    'physical_simulation_calls': 0, 'model_prediction_calls': 0, 'rls_replay_calls': 0,
    'real_parameter_updates': 0, 'new_environment_interactions': 0}
with review_path.open('x', encoding='utf-8', newline='\n') as stream:
    stream.write(text)
with provenance_path.open('x', encoding='utf-8', newline='\n') as stream:
    json.dump(provenance, stream, ensure_ascii=False, indent=2, allow_nan=False)
    stream.write('\n')
print(json.dumps({k: provenance[k] for k in ('output_path', 'output_sha256', 'source_sha256', 'wall_seconds', 'cpu_seconds')}))
print('\n'.join(lines[lines.index('## 风险与证据边界'):lines.index('## 复现产物与只读成本')]))
