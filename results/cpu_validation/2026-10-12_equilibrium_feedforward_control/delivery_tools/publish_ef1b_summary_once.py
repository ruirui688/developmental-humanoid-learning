"""Publish saved new EF1B summaries; no old scores or models are recomputed."""
from pathlib import Path
import json

repo = Path(__file__).resolve().parents[1]
base = repo / 'results/cpu_validation/2026-10-12_equilibrium_feedforward_control'
run = json.loads((base / 'raw/run.json').read_bytes())
metrics = json.loads((base / 'raw/metrics.json').read_bytes())
execution = json.loads((base / 'first_execution/first_execution_receipt.json').read_bytes())
assert run['status'] == 'completed' and run['failure'] is None
assert run['cost']['control_call_returns'] == run['cost']['confirmed_physics_substeps'] == 18000
assert metrics['ef1b_model_contribution_gate_passed'] is False
assert metrics['ef1b_pd_reference_gate_passed'] is False
cost = run['cost']
lines = [
    '# EF1B首次目标保持前馈控制结果', '',
    '2026-10-12。六条新轨迹全部完整，零停止/技术异常/fit/RLS。学习模型相对同结构冷模型的joint、肩、肘误差分别降低'
    '**9.0203%、8.8254%、9.4825%**，原实际努力两门通过；改善幅度未达到原20%门。'
    '**本候选关闭，C4及C5–C7仍未验收，持续目标active。**', '',
    '正式强PD门因模型贡献前置失败而不可评，不把逐seed描述表当作正式通过。'
    '本次只是已见开发bank的局部双关节控制，不能解释为儿童式技能、全身能力、真实平衡或安全收益。', '',
    '## 首次身份与范围', '',
    f"- clean source commit：`{run['source']['commit']}`，首次exit `{execution['exit_code']}`。",
    '- [结果前冻结协议](EQUILIBRIUM_FEEDFORWARD_CONTROL_PROTOCOL.md)；新算法为模型目标保持请求+原PD64/Kd4，最终单次±.5Nm限幅。',
    '- 原FR4A cold/learned snapshot只恢复；六条新cold/learned，各1000zero prefix+2000active、2ms步。',
    '- 三seed8101/8102/8103；FR4B的三PD/三zero原身份与已审指标复用，零新增参考物理/旧自身预测/旧评分。',
    '- 自由root、仰卧8轴身体与原接触/guard/停止/目标保持；只请求两左臂关节。六fresh完整且原接触资格通过。',
    '- 公共身体、目标、500Hz经典PD、理想感觉、落地prefix和原辨识激励是披露先验；接触及隐藏动力学不进入部署模型。', '',
    '## 全部逐seed控制摘要', '',
    '下表直接转录保存摘要；PD/zero为reused原记录。误差单位rad；努力为active2000个已付原生端点，'
    '分别乘2ms后的两轴absolute/squared和，不称连续积分。', '',
    '| seed | 组/来源 | joint RMSE | 肩 RMSE | 肘 RMSE | actual absolute Nm·s | actual squared Nm²·s |',
    '|---|---|---:|---:|---:|---:|---:|',
]
for seed in run['seed_results']:
    for name in ['cold', 'learned', 'pd', 'zero']:
        row = seed['tracking_scores'][name]
        values = [row['joint_rmse_rad'], *row['axis_rmse_rad'], row['actual_absolute_two_axis_nm_s'], row['actual_squared_two_axis_nm2_s']]
        lines.append('| ' + str(seed['seed']) + ' | ' + name + ('/fresh' if name in ['cold', 'learned'] else '/reused') + ' | ' + ' | '.join(f'{value:.9g}' for value in values) + ' |')
lines += ['', '## 原门与有限结论', '',
    '- 每seed两轴与joint均严格优于新cold；三seed原RMSE算术均值改善9.0203%/8.8254%/9.4825%，三项均不足20%。',
    '- 保存actual absolute均值：cold1.43556581491、learned1.41841363082；squared：cold0.424754004879、learned0.410901032370。两项均满足原1.05上限。',
    '- 保存贡献门false；正式PD门available=false/passed=false；所有科学采用、C4验收和C5依赖释放标志false。',
    '- 12次目标逆解全部有根，30个完整模型pair回验；3次有限forecast拒绝走原literal-zero十微步。存在根及预测可行不证明实际静态保持或因果机制。',
    '- 不追加保持比例、逆解正则/容差、目标状态、gain、权重或seed扫描，不补跑本候选。', '',
    '## 新自身条件预测', '',
    '全部六fresh来源×两模型×五H保存；未来已知请求仅供离线条件输入，实际未来q/v只评分，'
    '不注入递推或部署。下表是保存逐seed RMSE的算术均值，未pool误差。全部逐seed/有效域/不利指标保留于raw/run.json。', '',
    '| fresh来源 | H/微步 | 评分模型 | 肩q RMSE/rad | 肘q RMSE/rad | 肩v RMSE/(rad/s) | 肘v RMSE/(rad/s) |',
    '|---|---:|---|---:|---:|---:|---:|',
]
for source in ['cold', 'learned']:
    for horizon in ['1', '10', '20', '50', '150']:
        for model in ['cold', 'learned']:
            rows = [seed['conditional_prediction_scores'][source]['horizons'][horizon]['models'][model] for seed in run['seed_results']]
            assert all(row['available'] for row in rows)
            values = [sum(row[field][axis] for row in rows)/len(rows) for field in ['q_rmse_axis_rad', 'v_rmse_axis_rad_s'] for axis in [0, 1]]
            lines.append('| ' + source + ' | ' + horizon + ' | ' + model + ' | ' + ' | '.join(f'{value:.9g}' for value in values) + ' |')
lines += ['', '## 实际费用与原件', '',
    f"新增**18,000控制/18,000子步**，0fit/RLS/策略更新；内部wall/CPU `{cost['wall_seconds']:.6f}/{cost['cpu_seconds']:.6f}s`，外进程wall `{execution['process_wall_seconds']:.6f}s`。不据此声称实时性能或同计算预算优势。",
    '正式累计**505,297控制/2,784,970子步**；online118,452+offline7,200=125,652scalar更新不变。规划、条件评分、准备、核验、压缩及I/O费用另列在原件，reused费用不重复增加。', '',
    '- [新run与费用](../results/cpu_validation/2026-10-12_equilibrium_feedforward_control/raw/run.json)',
    '- [原科学门](../results/cpu_validation/2026-10-12_equilibrium_feedforward_control/raw/metrics.json)',
    '- [有序分片manifest](../results/cpu_validation/2026-10-12_equilibrium_feedforward_control/raw/manifest.json)',
    '- [首次外进程记录](../results/cpu_validation/2026-10-12_equilibrium_feedforward_control/first_execution/first_execution_receipt.json)',
    '- [结果前准备及首静态错误](../results/cpu_validation/2026-10-12_equilibrium_feedforward_preparation/preparation.json)',
    '', '必要新保存核验结果单独附后；记录一致与科学门通过分开。阶段检查、提交推送后继续最早未验收C4，后续C5适应/C6成熟/C7新留出不跳过。',
]
report = repo / 'docs/EQUILIBRIUM_FEEDFORWARD_CONTROL_RESULTS.md'
assert not report.exists()
report.write_bytes(('\n'.join(lines) + '\n').encode())
for name in ['AGENTS.md', 'README.md', 'docs/CPU_VALIDATION_TARGET.md', 'docs/CONTINUOUS_EXECUTION_PLAN.md', 'docs/DEVELOPMENT_ROADMAP.md']:
    path = repo / name
    content = path.read_text(encoding='utf-8')
    link = 'docs/EQUILIBRIUM_FEEDFORWARD_CONTROL_RESULTS.md' if '/' not in name else 'EQUILIBRIUM_FEEDFORWARD_CONTROL_RESULTS.md'
    entry = (f'[EF1B首次保持补偿结果]({link})从clean f9f5007完整完成六fresh轨迹，18,000新控制/子步、0停止/异常/fit/RLS。'
             '同结构模型贡献joint9.0203%、肩8.8254%、肘9.4825%，actual努力两门通过，但未达原20%门；'
             '正式PD门因前置失败不可评。本单候选关闭，不scan保持比例/逆解容差/目标状态/gain/权重/seed。'
             '累计505,297控制/2,784,970子步、125,652scalar更新。'
             'C4及C5–C7未验收，持续目标active；归档核验提交推送后继续有依据的下一方向。')
    lines = content.splitlines()
    index = next(i for i, line in enumerate(lines) if '[EF1B目标保持前馈协议]' in line)
    prefix = '**当前执行入口：** ' if name == 'README.md' else '- **当前入口EF1B首次结果：** ' if name.endswith('CONTINUOUS_EXECUTION_PLAN.md') else ''
    lines[index] = prefix + entry
    if name == 'AGENTS.md':
        lines = [line.replace('正式物理累计 **487,297控制调用 /2,766,970子步**', '正式物理累计 **505,297控制调用 /2,784,970子步**；EF1B新增18,000/18,000/0更新') for line in lines]
    if name.endswith('CONTINUOUS_EXECUTION_PLAN.md'):
        lines += ['', '### EF1B首次完整结果与立即继续', '', entry,
                  '', '12目标根全部存在、3有限forecast fallback；零技术异常不证明安全或当前目标根的实际物理因果。'
                  '首次外进程wall246.827482s，内部wall/CPU245.971729/238.671875s。六新与六复用人口、全部预测与费用原样保存，旧数据不重算。']
    path.write_bytes(('\n'.join(lines) + '\n').encode())
attrs = repo / '.gitattributes'
attrs.write_bytes(attrs.read_bytes() + b'\ndocs/EQUILIBRIUM_FEEDFORWARD_CONTROL_RESULTS.md text eol=lf\n')
print(json.dumps({'report': str(report), 'cumulative_controls': 505297, 'cumulative_substeps': 2784970}))
