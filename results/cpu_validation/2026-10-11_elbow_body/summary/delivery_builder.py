"""Copy existing summary/test evidence and derive review tables from saved summary only."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXT = ROOT/'external'
PREFIX = EXT/'elbow_body_20261011_summary_01'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write_new(path, data):
    with path.open('xb') as stream:
        stream.write(data)


def json_new(path, data):
    write_new(path, (json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False)+'\n').encode())


copies = []
for suffix in ('01_stdout.txt', '01_execution.json', '02_stdout.txt', '02_execution.json'):
    source = EXT/('elbow_body_summary_synthetic_'+suffix)
    destination = Path(str(PREFIX)+'_synthetic_'+suffix)
    data = source.read_bytes()
    write_new(destination, data)
    copies.append({'source': str(source), 'destination': str(destination), 'sha256': sha(data), 'type': 'exact_byte_copy'})
for original, suffix in (('test_elbow_body_summary_prepare.py', '_synthetic_tests.py'),
                         ('elbow_body_20261011_summary_01_summary_executed.py', '_synthetic_02_source_copy.py')):
    source = EXT/original
    destination = Path(str(PREFIX)+suffix)
    data = source.read_bytes()
    write_new(destination, data)
    copies.append({'source': str(source), 'destination': str(destination), 'sha256': sha(data),
        'type': 'exact_byte_copy', 'note': 'No edits after successful synthetic round 02 before formal summary; test source was unchanged between rounds.'})
data = (EXT/'elbow_body_20261011_summary_01_summary_executed.py').read_bytes()
repairs = [
    (b"checks.check(evaluation['models_before'] == evaluation['models_after'], location+'/'+kind+'/frozen_parameters')",
     b"checks.compare(evaluation['models_before'], evaluation['models_after'], location+'/'+kind+'/frozen_parameters')"),
    (b"checks.check(evaluation['integration_models_before'] == evaluation['integration_models_after'], location+'/'+kind+'/frozen_integration')",
     b"checks.compare(evaluation['integration_models_before'], evaluation['integration_models_after'], location+'/'+kind+'/frozen_integration')"),
    (b"                checks.check(set(expected_models) == set(evaluation['models_before']), location+'/'+kind+'/saved_model_keys')\n", b'')]
for old, new in repairs:
    if data.count(old) != 1:
        raise ValueError('Exact repair reversal unavailable.')
    data = data.replace(old, new)
reconstructed = Path(str(PREFIX)+'_synthetic_01_source_reconstructed.py')
write_new(reconstructed, data)
copies.append({'source': str(EXT/'elbow_body_20261011_summary_01_summary_executed.py'),
    'destination': str(reconstructed), 'sha256': sha(data), 'type': 'generated_reconstruction',
    'note': 'Round 01 source was not snapshotted when tests ran. Reconstructed by reversing the three recorded repair edits; not represented as an execution-captured original.'})
builder_copy = Path(str(PREFIX)+'_delivery_builder.py')
write_new(builder_copy, Path(__file__).read_bytes())
json_new(Path(str(PREFIX)+'_synthetic_copy_provenance.json'), {
    'created_at_utc': datetime.now(timezone.utc).isoformat(), 'copies': copies,
    'formal_summary_reexecutions': 0, 'audit_reexecutions': 0, 'physical_calls': 0, 'parameter_updates': 0,
    'synthetic_timing_semantics': 'Original wrapper wall and parent CPU retained; child unittest CPU was not separately measured and remains unknown. Unittest elapsed .076/.074 seconds is elapsed test time, not CPU.'})

summary_path = Path(str(PREFIX)+'_summary.json')
s = json.loads(summary_path.read_text(encoding='utf-8'))
tables = {'source_summary_path': str(summary_path), 'source_summary_sha256': sha(summary_path.read_bytes()),
    'semantics': 'Read saved one-attempt summary only; no formal raw/audit reread, new predictions, parameter fit or additional interaction.',
    'trials': [], 'stops': [], 'model_parameters': [], 'learned_mpc_diagnostics': [], 'audited_rollout_excerpt': []}
for seed, audited in zip(s['raw_recomputed_seed_details'], s['audited_seed_details']):
    sid = seed['seed']
    tables['model_parameters'].append({'seed': sid, **seed['cold_start_and_frozen_parameters']})
    for kind, e in seed['evaluations'].items():
        tables['trials'].append({'seed': sid, 'kind': kind, 'status': e['status'], 'completed': e['completed'],
            'eligible': e['eligible'], 'paid_budget': e['paid_budget'], 'tracking_rmse_rad': e['tracking_rmse_rad'],
            'position_prediction_rmse': e['position_prediction_rmse'], 'velocity_prediction_rmse': e['velocity_prediction_rmse'],
            'actual_effort_complete': e['actual_effort_complete'], 'phase_effort': e['phase_effort'],
            'metric_control_step_count': e['metric_control_step_count'], 'metric_prediction_step_count': e['metric_prediction_step_count'],
            'state_coverage': e.get('state_coverage'), 'ranking_eligible': e['completed'] and e['eligible']})
        for stop in seed['native_trajectory_diagnostics'][kind]['stop_native_transitions']:
            tables['stops'].append({'seed': sid, 'kind': kind, **stop})
    d = seed['native_trajectory_diagnostics']['learned_mpc']
    tables['learned_mpc_diagnostics'].append({'seed': sid, **d})
    for win in audited['evaluations']['learned_mpc']['free_rollouts']:
        tables['audited_rollout_excerpt'].append({'seed': sid, 'source': 'first independent audit retained verbatim', **win})
json_new(Path(str(PREFIX)+'_review_tables.json'), tables)

def fmt(x):
    return '—' if x is None else f'{x:.12g}'

lines = [
    '# 左肘一次身体模型开发独立审读', '',
    '正式一次采集及首次审计后，按 root 明确授权执行一次标准库 summary。只读真实原生 8 维中的 j1；未重排数组，未导入 runner/audit/MuJoCo/NumPy，未执行物理、RLS 数学重播、参数拟合或新模型预测。', '',
    '结论：524,210 项独立核对、0 失败，最大差异 5.551115123125783e-17。数据一致性通过；五必要试验模型贡献门 false/unevaluated、六必要试验 PD 门 false/unevaluated、七试验完整矩阵 false。算法验收没有通过。', '',
    '采集 clean commit `46077b1d30089d68f1c935e3fc547dfdfa4c4e66`，development seed 0/1/2。每 seed fresh θ=[1,0,.02,0,0]、P=100I、原生负 qref，300 次校准更新，后续评估参数冻结。已见开发 seed 不充作新留出。', '',
    '正式预算：5,292 控制调用、52,920 子步、900 RLS；21 计划试验中 15 完成、6 研究停止、0 环境停止、0 异常。prefix=2,100 调用、calibration=900、prediction=453、control=1,839。停止段最后完整端点可计残差和费用，但不能称 completed。', '',
    '含本轮正式物理累计 221,663 调用 / 2,216,630 子步 / 10,800 RLS。PD 开发额外 7,521 / 75,210 / 0 已单独披露，body 中 tuned PD64/1 来源 commit/audit/summary/候选8 固定核验。', '',
    '## 冻结门与完整对照', '',
    '| seed | low nominal v RMSE | low learned v RMSE | 降低 | nominal tracking (完整200) | learned tracking (仅13) | PD tracking (完整200) | zero tracking (完整200) |',
    '|---|---:|---:|---:|---:|---:|---:|---:|']
for seed in s['raw_recomputed_seed_details']:
    e=seed['evaluations']; low=e['prediction_low']['velocity_prediction_rmse']
    lines.append(f"| {seed['seed']} | {fmt(low['nominal_mpc'])} | {fmt(low['learned_mpc'])} | {(1-low['learned_mpc']/low['nominal_mpc'])*100:.6f}% | {fmt(e['nominal_mpc']['tracking_rmse_rad'])} | {fmt(e['learned_mpc']['tracking_rmse_rad'])} | {fmt(e['tuned_pd']['tracking_rmse_rad'])} | {fmt(e['zero_torque']['tracking_rmse_rad'])} |")
lines += ['', 'low 三 seed 完整，但速度改善 11.09%–11.40%，不足固定 20% 门。full 三 seed 各仅 51 active 端点，learned MPC 各仅 13，完整低/高预测及闭环对照条件不成立。不能用截断 full 的较低残差、短 learned tracking/累计努力或零环境停止声称模型控制优势、节能或安全。', '',
    '完整控制均值：nominal tracking=0.048779910342356465 rad、PD64/1=0.006209216810408327 rad、zero=0.06324555140602196 rad；learned 完整均值 null。PD实际 |u|、u²积分均值=0.9705302323162487 N m s / 0.24873701123073969 N² m² s。nominal=0.9350833333333336 / 0.45944791666666696。不同控制器闭环轨迹分别评价。', '',
    'learned 启动成本每 seed 已支付 calibration400 + own control113 =513调用/5130子步；PD/nominal/zero各300/3000。共同 prediction 351/3510 单列。局部控制窗口权限相同不等于总体启动成本相同。', '',
    '## 六次原生停止', '',
    '| seed | kind | step (0起) | active (0起) | q rad | q-qref rad | v rad/s | 当前请求 N m | trigger |',
    '|---|---|---:|---:|---:|---:|---:|---:|---|']
for stop in tables['stops']:
    reason=stop['study_abort']
    lines.append(f"| {stop['seed']} | {stop['kind']} | {stop['step_index']} | {stop['active_step_index']} | {fmt(stop['q_after_rad'])} | {fmt(stop['q_minus_qref_after_rad'])} | {fmt(stop['v_after_rad_s'])} | {fmt(stop['requested_torque_nm'])} | {', '.join(reason['triggers'])} |")
lines += ['', '所有研究停止由 summary 从 j1 原生端点独立重算，和首次 audit、episode 完全一致；研究停止与环境终止分别计账。full 固定探索负命令 −0.375 N m 的快速反向响应越过 |v|≥1；不能事后削掉该段或提升阈值。', '',
    '## learned MPC 失配证据', '',
    '每 seed 13 active 控制端点、130 子步，实际 j1 力矩均非零、与请求完全相等，0 限位动作屏蔽、0 fallback；记录可行候选为8×3次及7×10次。最初三次及停止步选择均为 +0.375 N m（未从截断低努力声称节能）。因此这次闭环停止不是所选关节实际动作被屏蔽或候选全不可行导致。', '',
    '| seed | θ (v,qoffset,u,hinge,1) | stop前 v | recorded预测下一v | 实际下一v | recorded预测下一q | 实际下一q | q域外/13 | v域外/13 |',
    '|---|---|---:|---:|---:|---:|---:|---:|---:|']
for seed in s['raw_recomputed_seed_details']:
    sid=seed['seed']; diag=seed['native_trajectory_diagnostics']['learned_mpc']; stop=diag['stop_native_transitions'][0]
    pred=stop['recorded_chosen_planner_decision']; cov=seed['evaluations']['learned_mpc']['state_coverage']
    theta=seed['cold_start_and_frozen_parameters']['final_coefficients']
    lines.append(f"| {sid} | {', '.join(fmt(x) for x in theta)} | {fmt(stop['v_before_rad_s'])} | {fmt(pred['predicted_v'][0])} | {fmt(stop['v_after_rad_s'])} | {fmt(pred['predicted_q'][0])} | {fmt(stop['q_after_rad'])} | {cov['q_outside_count']} | {cov['v_outside_count']} |")
lines += ['',
    '三 seed 最初预测 +0.375 约在目标 .0394 rad 附近形成转向/恢复，实际关节继续向正方向超调。停止步模型仍预测下一 q≈.112、下一 v≈.185–.195，真实下一 q≈.11965–.12000、v≈.569–.571；一步速度残差明显。该描述使用原件保存的 chosen forecasts，首次 audit 已独立重播选择，summary 没有新算预测。', '',
    '校准 qoffset 范围约 −.00626至+.07679，learned 起点三seed各3/13域外(23.08%)，v起点0/13域外；最早多数控制输入仍在分别计算的q/v envelope内。矩形范围不保证联合状态、动作、接触历史都受支持，不能把“范围内”称可靠模型或安全集，也不能将全部失败归因于最后3个域外状态。', '',
    '模型 qoffset 系数约 −3.52至−3.60、非零 bias≈+.0203至+.0207，表现为较强恢复预测；零力矩平稳评估上它的v一步RMSE≈.0203–.0207，而连续/nominal模型约1e−9，提示该拟合的条件误差。校准每seed负命令有500子步被所选关节限位保护屏蔽，low有350、full有140；requested输入与真实执行的差异和接触/关节耦合是待检验机制，不能仅凭本轮识别其因果贡献。', '',
    'MPC公共预测范围约[−.03,qref+.15]、速度许可1.5rad/s，研究停止为|q−qref|≥.12或|v|≥1，两套边界不是相同阈值。止前记录预测本身在其许可范围且未预见实际越界。保持原门与负qref，不裁目标，不用放宽停止改善结果。PD实际能完整跟踪，支持诊断对象是本次模型与预测控制组合而非该关节完全不可控。', '',
    '## 诊断来源与风险', '',
    '一步 q/v 残差、tracking、努力、q/v coverage、实际调用/子步、研究停止、stored model hash链由summary原生重算或核验。风险/conditional/tail/free_rollouts完整保留首次audit来源，没有独立重算模型多步轨迹。首次audit只有1/5/15/50步；2步明确未记录。learned控制5步只有9窗口，15/50步0窗口，不能把null解释为零误差或长时域通过。', '',
    '风险包含所有paid prefix、失败和主动段；环境零停止不等于安全。j1负qref是MuJoCo原生轻微公共限位穿透，未clamp；soft_limit/接触峰等原件全保留。summary guard计数覆盖8关节，j1动作屏蔽另按实际history隔离；缺少实际子步时努力仅下界。', '',
    '下一步建议：本开发配方左肘不采用为已验收控制。进入明确新协议的肩—肘原生映射与预测有效域检查，先保证动作权限、受支持预测与共同控制评估；将guard、接触条件、联合状态支持和恢复预测偏差作为假设逐项消融。新协议应固定预算、独立强PD、研究门及新seed，保留本失败，不以本开发seed充新最终留出。', '',
    '## 一次执行、合成失败与文件', '',
    f"summary wall={s['execution']['wall_seconds']}, CPU={s['execution']['cpu_seconds']}；wrapper wall=1.6233240999281406, CPU=1.46875。首次audit731662/0失败、SHA 1bd3632fd805064951addf72120992b63dca2df255fddc54840b22d014c4f78a。", '',
    '有限合成第1轮8测试中1失败：递归dict compare只要求期望键，漏掉冻结后新增键；修复为before/after完整dict相等并核验saved model键。第2轮8项全通过；两轮分别wall=.1977621999103576/.221563900122419 s，parent CPU=0/.015625 s。child unittest CPU未单独测量，不能把parent CPU称完整测试CPU；unittest .076/.074 s只是测试elapsed。两轮没有正式原件读取、物理或更新。', '',
    '第1轮源码当时未snapshot，交付`synthetic_01_source_reconstructed.py`是依据三处明确修复逆向重建的生成件，不冒充执行保存原件。第2轮source copy与后来实际summary executed源码完全相同，原测试源码两轮未改。旧失败stdout及execution exact copies保留来源说明，不补跑。', '',
    '| file | SHA256 | type/source |', '|---|---|---|']
files = sorted(EXT.glob('elbow_body_20261011_summary_01_*'))
originals = [EXT/'elbow_body_summary_prepare.py', EXT/'elbow_body_summary_wrapper_01.py',
             EXT/'test_elbow_body_summary_prepare.py', EXT/'prepare_elbow_body_summary_delivery.py',
             EXT/'elbow_body_summary_synthetic_01_stdout.txt', EXT/'elbow_body_summary_synthetic_01_execution.json',
             EXT/'elbow_body_summary_synthetic_02_stdout.txt', EXT/'elbow_body_summary_synthetic_02_execution.json']
for p in files+originals:
    lines.append(f"| `{p.relative_to(ROOT).as_posix()}` | `{sha(p.read_bytes())}` | {'copied/reconstructed/generated provenance distinguishes exact types' if '_synthetic_' in p.name else 'original or saved-summary-derived'} |")
delivery = EXT/'elbow_body_20261011_summary_delivery.md'
write_new(delivery, ('\n'.join(lines)+'\n').encode())
print(json.dumps({'delivery': str(delivery), 'delivery_sha256': sha(delivery.read_bytes()),
    'saved_summary_sha256': sha(summary_path.read_bytes()), 'tables': str(Path(str(PREFIX)+'_review_tables.json')),
    'copies': len(copies), 'summary_reexecutions': 0, 'physical_calls': 0}, ensure_ascii=False))
