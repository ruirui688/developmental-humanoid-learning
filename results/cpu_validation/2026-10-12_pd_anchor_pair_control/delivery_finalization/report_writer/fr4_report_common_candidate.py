"""FR4 first report writers: only their own fixed report_inputs is read.

Root runs a stage entry once with --write, first-audit facts and its actual
historical baseline. No raw, parameter, earlier result, audit or navigation
document is opened. Only this stage's new result document and receipt are written.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

SEEDS = (8101, 8102, 8103)
HORIZONS = (1, 10, 20, 50, 150)
METHODS = ('cold', 'learned', 'pd', 'zero')
FLAGS = ('scientific_adoption', 'old_free_root_C4_validation',
         'c4_scientific_validation', 'c4_contact_scientific_validation',
         'c5_scientific_dependency_released')
GATE_FLAGS = ('fr4a_prediction_gate_passed', 'fr4b_model_contribution_gate_passed',
              'fr4b_pd_reference_gate_passed', 'fr4_free_root_mechanism_validation')
CONFIG = {
    'FR4A': ('prediction', '2026-10-12_pd_anchor_pair_prediction',
             'PD_ANCHOR_PAIR_PREDICTION_RESULTS.md', 'FR4A首次PD锚点候选独立预测'),
    'FR4B': ('control', '2026-10-12_pd_anchor_pair_control',
             'PD_ANCHOR_PAIR_CONTROL_RESULTS.md', 'FR4B首次PD锚点替换匹配控制'),
}


def identity(data):
    return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def number(value):
    if value is None:
        return '不可评/unknown'
    return f'{value:.10g}' if isinstance(value, float) else str(value)


def vector(values):
    return '不可评' if values is None else '/'.join(number(x) for x in values)


def percent(values):
    return '不可评' if values is None else '/'.join(
        '不可评' if x is None else f'{x*100:.4f}%' for x in values)


def boolean(value):
    return 'true' if value is True else 'false' if value is False else 'unknown'


def required_counter(cost, key):
    value = cost[key]
    if type(value) is not int or value < 0:
        raise ValueError('saved_nonnegative_integer_counter_required:' + key)
    return value


def contact_and_effort(parts, by_seed, stage):
    kinds = ('calibration', 'prediction') if stage == 'FR4A' else METHODS
    parts.append('\n## 全部trial、接触资格与实际努力\n\n'
        '未尝试、停止与异常完整保留，未知值不补零。接触只资格/报告，不证明连续承重、因果或安全；'
        'actual为已保存2ms actuator_torque端点样本，不是未测连续积分。\n\n'
        '| seed | trial | status/native完整/域资格 | 已返回/计划 | 停止/异常 |\n|---|---|---|---|---|\n')
    trials = []
    for seed in SEEDS:
        sr = by_seed.get(seed, {})
        for kind in kinds:
            trial = sr.get(kind) if stage == 'FR4A' else sr.get('controls', {}).get(kind)
            planned = 5000 if kind == 'calibration' else 2000 if kind == 'prediction' else 3000
            if not trial or 'trial_id' not in trial:
                status = (trial or {}).get('status', '未尝试')
                reason = (trial or {}).get('reason', '未尝试')
                parts.append(f'| {seed} | {kind} | {status}/false/unknown | unknown/{planned} | {reason} |\n')
                continue
            trials.append((seed, kind, trial))
            reason = (trial.get('stop') or {}).get('primary_reason') or (trial.get('failure') or {}).get('type') or '无'
            parts.append(f"| {seed} | {kind} | {trial.get('status', 'unknown')}/{boolean(trial.get('complete'))}/{boolean(trial.get('free_root_domain_qualification_passed'))} | {number(trial.get('returned_intervals'))}/{planned} | {reason} |\n")
    parts.append('\n| seed/trial | phase | 记录/计划 | 已付/已观察/unknown接触 | 左臂正端点 | feet正端点 | other正端点 | 资格 |\n|---|---|---|---|---:|---:|---:|---|\n')
    for seed, kind, trial in trials:
        for phase, row in trial.get('contact_population', {}).get('phases', {}).items():
            classes = row.get('classes', {})
            positives = [number(classes.get(name, {}).get('positive_contact_endpoint_count')) for name in ('left_arm', 'feet', 'other')]
            parts.append(f"| {seed}/{kind} | {phase} | {number(row.get('record_count'))}/{number(row.get('planned_count'))} | {number(row.get('confirmed_substeps'))}/{number(row.get('observed_contact_endpoints'))}/{number(row.get('unknown_paid_contact_substeps'))} | {' | '.join(positives)} | {boolean(row.get('qualification_passed'))} |\n")
    parts.append('\n| seed/trial | phase | 努力完整/已捕获 | actual absolute Nm·s | actual squared Nm²·s | unknown子步 |\n|---|---|---|---:|---:|---:|\n')
    for seed, kind, trial in trials:
        for phase in ('prefix', 'active'):
            row = trial.get('actual_effort', {}).get(phase, {})
            parts.append(f"| {seed}/{kind} | {phase} | {boolean(row.get('complete'))}/{number(row.get('captured_substeps'))} | {number(row.get('actual_absolute_two_axis_nm_s'))} | {number(row.get('actual_squared_two_axis_nm2_s'))} | {number(row.get('unknown_actual_effort_substeps'))} |\n")


def prediction_sections(parts, metrics, by_seed):
    parts.append('\n## 原独立预测门与全部保存RMSE\n\n'
        '以下直接转录保存checks与原RMSE，百分比仅格式化已保存fraction。H10v/H150q要求每seed两轴严格改善、'
        '各轴三seed原RMSE算术均值改善≥20%；H150v及H20/H50 q/v每seed两轴不劣。H1/H10q只报告，完整优先、不部分排名。\n\n'
        '| 保存门 | gated/available/passed | cold肩/肘 | learned肩/肘 | 保存改善 |\n|---|---|---|---|---|\n')
    for row in metrics.get('checks', []):
        who = str(row.get('seed', row.get('scope', 'unknown')))
        label = f"{who}/H{row.get('horizon', 'unknown')}{row.get('signal', '')}"
        cold = row.get('cold_axis_mean', row.get('cold_axis'))
        learned = row.get('learned_axis_mean', row.get('learned_axis'))
        parts.append(f"| {label} | {boolean(row.get('gated', True))}/{boolean(row.get('available'))}/{boolean(row.get('passed'))} | {vector(cold)} | {vector(learned)} | {percent(row.get('improvement_fractions'))} |\n")
    parts.append('\n全部三个seed×两模型×五H的q/v两轴保存向量如下（完整时共60个RMSE向量）；不可用和未尝试仍列出。\n\n'
        '| seed | H/时距 | 模型 | available/observed/planned origins | q肩/肘 rad | v肩/肘 rad/s |\n|---|---|---|---|---|---|\n')
    for seed in SEEDS:
        scores = by_seed.get(seed, {}).get('prediction_scores', {}).get('horizons', {})
        for horizon in HORIZONS:
            row = scores.get(str(horizon), {})
            for model in ('cold', 'learned'):
                saved = row.get('models', {}).get(model, {})
                parts.append(f"| {seed} | {horizon}/{2*horizon}ms | {model} | {boolean(saved.get('available'))}/{number(saved.get('observed_origin_count'))}/{number(row.get('planned_origin_count'))} | {vector(saved.get('q_rmse_axis_rad'))} | {vector(saved.get('v_rmse_axis_rad_s'))} |\n")


def control_sections(parts, metrics, by_seed):
    contribution = metrics.get('model_contribution', {})
    pd = metrics.get('pd_reference', {})
    parts.append('\n## 全部12项匹配跟踪与实际努力\n\n'
        '每seed cold+新MPC、learned+同新MPC、强PD、zero依次fresh/reset一次。各计划1000zero+2000active。'
        'cold/learned/PD必须完整且满足prefix/A/B域资格；zero接触只描述，停止不另加采用veto。\n\n'
        '| seed | 方法 | 完整/域资格/score available | active已保存/计划 | joint/肩/肘RMSE rad | actual absolute Nm·s | actual squared Nm²·s | unknown努力子步 |\n|---|---|---|---|---|---:|---:|---:|\n')
    for seed in SEEDS:
        sr = by_seed.get(seed, {})
        for method in METHODS:
            trial = sr.get('controls', {}).get(method, {})
            score = sr.get('tracking_scores', {}).get(method, {})
            effort = trial.get('actual_effort', {}).get('active', {})
            rmse = [score['joint_rmse_rad'], *score['axis_rmse_rad']] if score.get('available') is True else None
            parts.append(f"| {seed} | {method} | {boolean(trial.get('complete'))}/{boolean(trial.get('free_root_domain_qualification_passed'))}/{boolean(score.get('available'))} | {number(score.get('observed_active_count'))}/2000 | {vector(rmse)} | {number(effort.get('actual_absolute_two_axis_nm_s'))} | {number(effort.get('actual_squared_two_axis_nm2_s'))} | {number(effort.get('unknown_actual_effort_substeps'))} |\n")
    parts.append('\n## 原控制门（保存值）\n\n'
        '贡献门仍要求每seed joint/两轴严格改善，三seed原RMSE均值三指标各改善≥20%，actual absolute/squared两轴合计均值各≤1.05×cold。'
        '贡献通过才评PD：每seed三指标不劣、joint原均值改善≥5%，两种努力均值各≤1.05×PD；RMSE0百分比不可用、effort0要求candidate0。\n\n'
        '| 比较 | available/passed | 基线joint/肩/肘均值 | learned均值 | 保存改善 | 各seed保存available/passed |\n|---|---|---|---|---|---|\n')
    for name, gate in (('cold贡献', contribution), ('强PD参考', pd)):
        mean = next((row for row in gate.get('checks', []) if row.get('scope') == 'three_seed_raw_RMSE_mean'), {})
        seeds = '; '.join(f"{row['seed']}:{boolean(row.get('available'))}/{boolean(row.get('passed'))}" for row in gate.get('checks', []) if 'seed' in row)
        parts.append(f"| {name} | {boolean(gate.get('available'))}/{boolean(gate.get('passed'))} | {vector(mean.get('baseline_joint_axis_mean'))} | {vector(mean.get('learned_joint_axis_mean'))} | {percent(mean.get('improvement_fractions'))} | {seeds or '不可评'} |\n")
    if contribution.get('passed') is not True:
        parts.append('\n贡献前置未通过，正式PD门不可评；完整保留PD实际表现，不以事后比较追认。\n')
    parts.append('\n| 比较 | actual信号 | 保存基线均值 | learned均值 | 保存passed |\n|---|---|---:|---:|---|\n')
    for name, gate in (('cold', contribution), ('PD', pd)):
        for row in gate.get('checks', []):
            if row.get('scope') == 'three_seed_actual_effort_mean':
                parts.append(f"| {name} | {row['signal']} | {number(row.get('baseline_mean'))} | {number(row.get('learned_mean'))} | {boolean(row.get('passed'))} |\n")
    parts.append('\n## 全部自身条件预测\n\n'
        '六条自身来源分别用本seed两模型和已保存final requests递推；不pool、无事后self veto。下表保留全部五H、两轴q/v与availability（完整时120个向量）。'
        'FR4A通过不能覆盖自身有效域；planner 140步PD尾与actual再规划之差不能直接归因模型。\n\n'
        '| seed/自身来源 | H/时距 | 预测模型 | available/observed/planned | q肩/肘 rad | v肩/肘 rad/s |\n|---|---|---|---|---|---|\n')
    for seed in SEEDS:
        sr = by_seed.get(seed, {})
        for source in ('cold', 'learned'):
            scores = sr.get('conditional_prediction_scores', {}).get(source, {}).get('horizons', {})
            for horizon in HORIZONS:
                row = scores.get(str(horizon), {})
                for model in ('cold', 'learned'):
                    saved = row.get('models', {}).get(model, {})
                    parts.append(f"| {seed}/{source} | {horizon}/{2*horizon}ms | {model} | {boolean(saved.get('available'))}/{number(saved.get('observed_origin_count'))}/{number(row.get('planned_origin_count'))} | {vector(saved.get('q_rmse_axis_rad'))} | {vector(saved.get('v_rmse_axis_rad_s'))} |\n")





def saved_counter_or_unknown(cost, key):
    return required_counter(cost, key) if key in cost else None


def failure_sections(parts, saved):
    failure = saved.get('failure')
    parts.append('\n## 保存状态、异常与全部未尝试\n\n'
        f'保存status={saved.get("status", "unknown")}；complete_population='
        f'{boolean(saved.get("metrics", {}).get("complete_population"))}。'
        '科学门、首保存核验与执行完整性分别报告，不用失败的默认false覆盖旧阶段事实。\n')
    if isinstance(failure, dict):
        parts.append(f'\n保存失败type={failure.get("type", "unknown")}，'
                     f'phase={failure.get("phase", saved.get("metrics", {}).get("failure_phase", "unknown"))}，'
                     f'message={failure.get("message", "unknown")}。\n')
    elif failure is not None:
        parts.append('\n保存failure=' + str(failure) + '。\n')
    else:
        parts.append('\n保存顶层failure=None；各trial停止、异常、缺失仍须逐项报告，不能据此声称安全。\n')
    unattempted = saved.get('unattempted_seeds')
    parts.append('\n保存unattempted_seeds=' + ('unknown/未声明' if unattempted is None else str(unattempted))
                 + '；下方固定三个seed的所有planned trial均列出，缺失不补零。\n')


def main(stage):
    if stage not in CONFIG:
        raise ValueError('own_fixed_FR4_stage_required')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true')
    parser.add_argument('--audit-status', required=True, choices=('passed', 'failed'))
    parser.add_argument('--audit-checks', required=True, type=int)
    parser.add_argument('--audit-failed', required=True, type=int)
    parser.add_argument('--audit-rmse-vectors', required=True, type=int)
    for name in ('control', 'substeps', 'online-scalar', 'offline-scalar'):
        parser.add_argument('--base-' + name, required=True, type=int)
    args = parser.parse_args()
    if not args.write:
        raise ValueError('explicit_write_required_before_any_input_read')
    counts = (args.audit_checks, args.audit_failed, args.audit_rmse_vectors)
    if any(value < 0 for value in counts) or args.audit_failed > args.audit_checks or (args.audit_status == 'passed' and args.audit_failed != 0):
        raise ValueError('consistent_root_first_audit_facts_required')
    kind, directory, report_name, title = CONFIG[stage]
    input_path = Path('results/cpu_validation') / directory / 'report_inputs.json'
    report_path = Path('docs') / report_name
    receipt_path = Path('external/fr4_report_candidate') / (stage.lower() + '_report_writing_receipt.json')
    if report_path.exists() or receipt_path.exists():
        raise FileExistsError('first_stage_report_or_receipt_exists_do_not_rerun')
    base = (args.base_control, args.base_substeps, args.base_online_scalar, args.base_offline_scalar)
    if any(type(value) is not int or value < 0 for value in base):
        raise ValueError('explicit_nonnegative_actual_stage_baseline_required')
    data = input_path.read_bytes()
    saved = json.loads(data)
    if saved.get('experiment_id') != stage or ('stage' in saved and saved['stage'] != kind):
        raise ValueError('only_own_canonical_stage_report_inputs_required')
    cost, metrics = saved['cost'], saved['metrics']
    if any(metrics.get(key) is not False or (key in saved and saved[key] is not False) for key in FLAGS):
        raise ValueError('saved_five_C4_C5_adoption_flags_must_remain_false')
    increment = (saved_counter_or_unknown(cost, 'control_call_returns'),
                 saved_counter_or_unknown(cost, 'confirmed_physics_substeps'),
                 saved_counter_or_unknown(cost, 'RLS_scalar_update_commits'))
    vectors = saved_counter_or_unknown(cost, 'RLS_vector_update_commits')
    if stage == 'FR4B' and (increment[2] not in (None, 0) or vectors not in (None, 0)):
        raise ValueError('FR4B_frozen_models_must_not_update')
    totals = tuple(None if increment[index] is None else base[index]+increment[index] for index in range(3)) + (base[3],)
    total_scalar = None if totals[2] is None else totals[2]+totals[3]
    gate_key = 'fr4a_prediction_gate_passed' if stage == 'FR4A' else 'fr4_free_root_mechanism_validation'
    gate_passed = metrics.get(gate_key) is True
    qualified = (gate_passed and args.audit_status == 'passed' and saved.get('status') == 'completed'
                 and saved.get('failure') is None and all(value is not None for value in increment))
    outcome = ('保存原预测门通过' if gate_passed else '保存原预测门未通过/不可评') if stage == 'FR4A' else (
               '保存本域控制门通过' if gate_passed else '保存本域控制门未全部通过/不可评')
    if stage == 'FR4A':
        next_action = ('完成A首审、报告检查及检查点提交推送后，继续在A数据前已冻结的FR4B；controller、模型配方、seed、原门不改。' if qualified else
                       'FR4B成功依赖保持关闭；保留首失败或首保存核验问题，做一次有证据的有界下一判断，不补跑或放宽门。')
    else:
        next_action = ('接着另冻结对应候选的新留出C4综合验收，保留自身有效域缺口；随后分别检验C5、C6、C7。' if qualified else
                       '关闭本冻结候选的成功依赖；保留负结果，做一次有证据的有界下一判断，不补跑、scan/扩大grid、改权重或放宽门。')
    audit_short = f'首新保存核验{args.audit_status}、{args.audit_checks:,}项/{args.audit_failed:,}失败'
    archive = '../results/cpu_validation/' + directory + '/'
    commit = saved['source']['commit']
    first_execution_text = '首次物理控制执行一次' if stage == 'FR4B' else '首次执行一次'
    report_title = title + '（首次物理执行）' if stage == 'FR4B' else title
    parts = [f'# {stage}：{report_title}\n\n从clean `{commit}` {first_execution_text}，保存状态 **{saved["status"]}**；{outcome}。'
             f'实际新增{number(increment[0])}控制返回/{number(increment[1])}确认子步/{number(increment[2])}在线scalar提交；{audit_short}。\n\n'
             f'[事前冻结协议](PD_ANCHOR_PAIR_LEARNING_PROTOCOL.md) · [根归档]({archive}manifest.json) · [唯一实验输入]({archive}report_inputs.json)\n\n'
             '开发seed8101/8102/8103按冻结顺序；公开source/docs首次搜索无命中，raw/非公开历史未知，不宣称全局未用或最终留出。'
             '原free root/仰卧8轴身体、理想感觉、公开guard/保护、2ms PD64/Kd4_4、固定刺激与任务目标均为先验。'
             '没有任务教师、预训练策略、PPO或GPU。接触只资格/诊断，紧凑模型只含两轴q/v和已知final requests，不能宣称全身状态闭合、安全或真机学习。\n']
    failure_sections(parts, saved)
    seed_rows = saved.get('seed_results', [])
    if any(row.get('seed') not in SEEDS for row in seed_rows) or len({row['seed'] for row in seed_rows}) != len(seed_rows):
        raise ValueError('own_seed_rows_unique_subset_of_fixed_bank_required')
    by_seed = {row['seed']: row for row in seed_rows}
    if stage == 'FR4A':
        prediction_sections(parts, metrics, by_seed)
        parts.append('\nFR4A只校准及独立条件预测，没有匹配MPC控制。未来保存final requests仅作离线条件输入，未来actual q/v只评分。'
                     'FR1/FR3A通过及FR2/FR3B负结果保持；本阶段控制stagekeys默认false表示未声明控制成功，不覆盖历史事实。\n')
    else:
        control_sections(parts, metrics, by_seed)
        parts.append('\n## PD锚点结构与覆盖代价\n\n'
            '每轴用当前clip PD替换nearest nominal九点slot，distance相同按原index；保持原slot Cartesian枚举81候选。'
            'delta0只保证纯PD rollout可表达，不保证feasible/chosen/较低努力或实际收益；仍按原forecast、cost与tie选择。'
            '替换每轴点位移最多.0625Nm，gap可达.1875Nm，±.5端点可丢，双轴可能只保留64原nominal对。'
            '新增PD候选和删除原点一起改变函数类；FR3保存诊断没有识别量化或缺PD为失败原因，不能称因果解释。\n\n'
            'delta=替换点−当前clip PD仍可达±1，所有final请求仍±.5；首请求采用clip(p+(point−p))roundtrip，'
            '前10微步held delta与native反馈、后140预测PD尾，literal-zero fallback独立；cost、优化tie、保护和原20%/5%/1.05门不变。'
            '每macro18 scalar distance/2 nearest选择是额外工程计算，源码/spec数量说明不替代actual费用；缺少单独实测counter保留unknown，不补零。\n\n'
            'FR4B的fr4a_prediction_gate_passed默认false仅表示本阶段未重宣FR4A；保留已通过的A报告，'
            '不以源检查失败的零物理尝试或本阶段默认值覆盖它。\n')
    contact_and_effort(parts, by_seed, stage)
    parts.append('\n## 四个独立stagekeys与五个科学flags\n\n| 保存key | 保存值 |\n|---|---|\n')
    for key in (*GATE_FLAGS, *FLAGS):
        parts.append(f'| {key} | {boolean(metrics.get(key))} |\n')
    parts.append('\n## 全部保存费用与首审\n\n| 保存counter | 值 |\n|---|---:|\n')
    for key, value in sorted(cost.items()):
        parts.append(f'| {key} | {number(value)} |\n')
    runtime = saved.get('runtime', {})
    parts.append(f'\n内部计时/构造/forward/PD/guard/RLS/restore/snapshot/batch/接触/source与输出边界分别保留原件；'
        f'未知内部I/O不补零，不宣称20ms实时。首次外进程wall={number(saved.get("first_execution", {}).get("wall_seconds"))}s；'
        f'Python{runtime.get("python_version", "unknown")}/NumPy{runtime.get("numpy", "unknown")}/MuJoCo{runtime.get("mujoco", "unknown")}。\n\n'
        f'累计 **{number(totals[0])}控制调用 /{number(totals[1])}子步**；在线 **{number(totals[2])}**、'
        f'离线 **{number(totals[3])}**，scalar更新计算合计 **{number(total_scalar)}**。'
        '基点为root显式CLI提供的本阶段前actual累计，只加本次保存实际增量；缺失counter保持unknown，不用计划替代停止成本或补零。\n\n'
        f'主任务首次audit **{args.audit_status}，{args.audit_checks:,}checks/{args.audit_failed:,}failed，'
        f'{args.audit_rmse_vectors}个新RMSE向量**；[audit]({archive}audit_first/audit.json) · '
        f'[指标复核]({archive}audit_first/metric_recheck.json)。audit事实仅由root CLI传入，writer不打开audit文件。保存一致不代替科学门。\n\n'
        f'## 下一步与边界\n\n{next_action} 阶段检查与正常提交推送后立即继续active目标。\n\n'
        'scientific_adoption、old_free_root_C4_validation、c4_scientific_validation、c4_contact_scientific_validation、'
        'c5_scientific_dependency_released保持false。C4最终新留出及C5–C7尚未验收；零停止不能证明安全。'
        '全部停止、异常、未尝试及不利时距见本报告与完整JSON；writer未重算RMSE/门、fit、模型或物理。\n')
    report = ''.join(parts)
    report_bytes = report.encode('utf-8')
    # All fixed-stage input validations and report transformations precede mutation.
    with report_path.open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(report)
    receipt = {'schema': stage + '_first_report_writing_receipt_v1', 'status': 'written',
        'created_at_utc': datetime.now(timezone.utc).isoformat(), 'source_commit': commit,
        'only_experimental_input': {'path': str(input_path), **identity(data), 'file_read_count': 1, 'JSON_parse_count': 1},
        'report_inputs_stage_contract': 'stage may be absent; if present it must match the fixed experiment_id/config',
        'first_audit_from_root_CLI': {'status': args.audit_status, 'checks': args.audit_checks, 'failed': args.audit_failed,
                                      'new_RMSE_vectors': args.audit_rmse_vectors},
        'historical_baseline': {'controls': base[0], 'substeps': base[1], 'online_scalar': base[2], 'offline_scalar': base[3],
                                'source': 'explicit_root_CLI_actual_before_own_stage'},
        'actual_saved_increment': {'control_returns': increment[0], 'confirmed_substeps': increment[1], 'online_scalar_commits': increment[2]},
        'cumulative_after_stage': {'controls': totals[0], 'substeps': totals[1], 'online_scalar': totals[2], 'offline_scalar': totals[3]},
        'saved_scientific_metrics_transcription_only': True,
        'raw_model_parameter_old_experimental_result_or_audit_file_reads': 0,
        'embedded_snapshots': 'not selected/restored/copied', 'scientific_metrics_model_fit_RLS_physics_calls': 0,
        'navigation_document_reads_or_writes': 0,
        'written_documents': {str(report_path): identity(report_bytes)},
        'other_filesystem_IO': 'unmeasured_not_zero', 'commit_or_push_by_child': False}
    with receipt_path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(receipt, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'stage': stage, 'report': str(report_path), 'receipt': str(receipt_path), 'outcome': outcome,
                      'first_audit_status': args.audit_status, 'cumulative_after_stage': receipt['cumulative_after_stage'],
                      'navigation_modified': False}, ensure_ascii=False, allow_nan=False))
