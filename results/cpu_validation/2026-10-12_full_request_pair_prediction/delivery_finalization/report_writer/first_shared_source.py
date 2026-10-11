"""FR3 first report writers: each invocation reads only its own report_inputs.

Root runs a stage entry once with --write and first-audit facts. No raw, model
parameter file, earlier experimental result or audit output is opened here.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

SEEDS = (8001, 8002, 8003)
HORIZONS = (1, 10, 20, 50, 150)
METHODS = ('cold', 'learned', 'pd', 'zero')
DOCS = tuple(Path(name) for name in (
    'docs/PROGRESS.md', 'docs/CPU_VALIDATION_TARGET.md',
    'docs/CONTINUOUS_EXECUTION_PLAN.md', 'README.md', 'AGENTS.md'))
BASE_A = (373297, 2652970, 70452, 7200)
CONFIG = {
    'FR3A': ('prediction', '2026-10-12_full_request_pair_prediction',
             'FULL_REQUEST_PAIR_PREDICTION_RESULTS.md', 'FR3A首次新bank独立预测'),
    'FR3B': ('control', '2026-10-12_full_request_pair_control',
             'FULL_REQUEST_PAIR_CONTROL_RESULTS.md', 'FR3B首次完整首请求匹配控制'),
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


def first_paragraph(text, anchor, replacement, maximum_start=14000):
    start = text.find(anchor)
    if not 0 <= start <= maximum_start:
        raise ValueError('current_navigation_anchor_missing:' + anchor)
    end = text.find('\n\n', start)
    end = len(text) if end < 0 else end
    return text[:start] + replacement + text[end:]


def unique_replace(text, old, new):
    if text.count(old) != 1:
        raise ValueError('unique_navigation_anchor_required:' + old[:100])
    return text.replace(old, new)


def replace_totals(paragraph, stage, base, totals, increment, *, agents=False):
    match = re.search(r'正式物理累计 \*\*([\d,]+)\s*控制调用 /([\d,]+)\s*子步\*\*；', paragraph)
    if not match or tuple(int(x.replace(',', '')) for x in match.groups()) != base[:2]:
        raise ValueError('navigation_physics_baseline_differs:' + stage)
    prefix = f'正式物理累计 **{totals[0]:,}控制调用 /{totals[1]:,}子步**；'
    paragraph = paragraph[:match.start()] + prefix + (
        f'{stage}新增{increment[0]:,}/{increment[1]:,}/{increment[2]:,}在线scalar；') + paragraph[match.end():]
    if agents:
        pattern = r'当前在线([\d,]+)\+离线([\d,]+)=([\d,]+)scalar更新'
        replacement = f'当前在线{totals[2]:,}+离线{totals[3]:,}={totals[2]+totals[3]:,}scalar更新'
    else:
        pattern = r'在线([\d,]+)与离线([\d,]+)scalar更新计算保持分列，总([\d,]+)'
        replacement = f'在线{totals[2]:,}与离线{totals[3]:,}scalar更新计算保持分列，总{totals[2]+totals[3]:,}'
    match = re.search(pattern, paragraph)
    if not match or tuple(int(x.replace(',', '')) for x in match.groups()) != (base[2], base[3], base[2]+base[3]):
        raise ValueError('navigation_scalar_baseline_differs:' + stage)
    return paragraph[:match.start()] + replacement + paragraph[match.end():]


def contact_and_effort(parts, by_seed, stage):
    kinds = ('calibration', 'prediction') if stage == 'FR3A' else METHODS
    parts.append('\n## 全部trial、接触资格与实际努力\n\n'
        '未尝试、停止与异常完整保留，未知值不补零。接触只资格/报告，不证明连续承重、因果或安全；'
        'actual为已保存2ms actuator_torque端点样本，不是未测连续积分。\n\n'
        '| seed | trial | status/native完整/域资格 | 已返回/计划 | 停止/异常 |\n|---|---|---|---|---|\n')
    trials = []
    for seed in SEEDS:
        sr = by_seed.get(seed, {})
        for kind in kinds:
            trial = sr.get(kind) if stage == 'FR3A' else sr.get('controls', {}).get(kind)
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
        'FR3A通过不能覆盖自身有效域；planner 140步PD尾与actual再规划之差不能直接归因模型。\n\n'
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


def navigation(stage, entry, base, totals, increment, outcome, audit_short):
    source_bytes = {path: path.read_bytes() for path in DOCS}
    before = {str(path): identity(data) for path, data in source_bytes.items()}
    texts = {path: data.decode('utf-8') for path, data in source_bytes.items()}
    _, _, report_name, title = CONFIG[stage]
    rooted = entry.replace('](' + report_name + ')', '](docs/' + report_name + ')')
    previous = '[FR3完整首请求网格协议]' if stage == 'FR3A' else '[FR3A首次新bank独立预测]'
    path = Path('docs/PROGRESS.md')
    text, count = re.subn(r'^## 当前入口：[^\n]+', '## 历史：上一阶段入口', texts[path], count=1, flags=re.M)
    if count != 1:
        raise ValueError('top_progress_heading_missing')
    texts[path] = unique_replace(text, '# 开发进度与仓库检查点\n\n', '# 开发进度与仓库检查点\n\n## 当前入口：' + title + '\n\n' + entry + '\n\n')
    path = Path('docs/CPU_VALIDATION_TARGET.md')
    marker_prefix = '| [FR2 自由身体控制]' if stage == 'FR3A' else '| [FR3A 新bank独立预测]'
    matches = [line for line in texts[path].splitlines() if line.startswith(marker_prefix)]
    if len(matches) != 1:
        raise ValueError('unique_validation_table_prior_row_required')
    label = 'FR3A 新bank独立预测' if stage == 'FR3A' else 'FR3B 完整首请求控制'
    text = unique_replace(texts[path], matches[0], matches[0] + f'\n| [{label}]({report_name}) | {outcome}；全部人口与不利结果保留 | {audit_short}；开发证据不解除最终C4或C5–C7 |')
    texts[path] = first_paragraph(text, previous, entry)
    path = Path('docs/CONTINUOUS_EXECUTION_PLAN.md')
    old_anchor = '- **当前入口FR3：**' if stage == 'FR3A' else '- **当前入口FR3A：**'
    text = first_paragraph(texts[path], old_anchor, f'- **当前入口{stage}：** ' + entry)
    pattern = r'当前累计 \*\*([\d,]+) 控制调用 / ([\d,]+) 子步 / ([\d,]+) 在线scalar及([\d,]+)离线重放scalar\*\*，scalar计算合计([\d,]+)'
    match = re.search(pattern, text)
    if not match or tuple(int(x.replace(',', '')) for x in match.groups()) != (*base, base[2]+base[3]):
        raise ValueError('stage_ledger_saved_baseline_differs')
    replacement = f'{stage}实际新增{increment[0]}/{increment[1]}/{increment[2]}在线scalar；当前累计 **{totals[0]:,} 控制调用 / {totals[1]:,} 子步 / {totals[2]:,} 在线scalar及{totals[3]:,}离线重放scalar**，scalar计算合计{totals[2]+totals[3]}'
    texts[path] = text[:match.start()] + replacement + text[match.end():] + '\n\n### ' + title + '\n\n' + entry + '\n'
    for path, agents in ((Path('README.md'), False), (Path('AGENTS.md'), True)):
        text = first_paragraph(texts[path], '**当前执行入口：**' if not agents else previous,
                               '**当前执行入口：** ' + rooted if not agents else rooted)
        start = text.find('正式物理累计 **')
        if start < 0:
            raise ValueError('navigation_physics_paragraph_missing')
        end = text.find('\n\n', start)
        end = len(text) if end < 0 else end
        texts[path] = text[:start] + replace_totals(text[start:end], stage, base, totals, increment, agents=agents) + text[end:]
    return texts, before


def main(stage):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true')
    parser.add_argument('--audit-status', required=True, choices=('passed', 'failed'))
    parser.add_argument('--audit-checks', required=True, type=int)
    parser.add_argument('--audit-failed', required=True, type=int)
    parser.add_argument('--audit-rmse-vectors', required=True, type=int)
    if stage == 'FR3B':
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
    receipt_path = Path('external') / (stage.lower() + '_report_writing_receipt.json')
    if report_path.exists() or receipt_path.exists():
        raise FileExistsError('first_stage_report_or_receipt_exists_do_not_rerun')
    base = BASE_A if stage == 'FR3A' else (args.base_control, args.base_substeps, args.base_online_scalar, args.base_offline_scalar)
    if any(type(value) is not int or value < 0 for value in base):
        raise ValueError('explicit_nonnegative_actual_stage_baseline_required')
    data = input_path.read_bytes()
    saved = json.loads(data)
    if saved.get('experiment_id') != stage or saved.get('stage') != kind:
        raise ValueError('only_own_canonical_stage_report_inputs_required')
    cost, metrics = saved['cost'], saved['metrics']
    increment = (required_counter(cost, 'control_call_returns'), required_counter(cost, 'confirmed_physics_substeps'), required_counter(cost, 'RLS_scalar_update_commits'))
    if stage == 'FR3B' and (increment[2] != 0 or required_counter(cost, 'RLS_vector_update_commits') != 0):
        raise ValueError('FR3B_frozen_models_must_not_update')
    totals = (base[0]+increment[0], base[1]+increment[1], base[2]+increment[2], base[3])
    gate_key = 'fr3a_prediction_gate_passed' if stage == 'FR3A' else 'fr3_free_root_mechanism_validation'
    gate_passed = metrics.get(gate_key) is True
    qualified = gate_passed and args.audit_status == 'passed' and saved.get('status') == 'completed' and saved.get('failure') is None
    outcome = '保存原预测门通过' if stage == 'FR3A' and gate_passed else '保存原预测门未通过/不可评' if stage == 'FR3A' else '保存本域控制门通过' if gate_passed else '保存本域控制门未全部通过/不可评'
    if stage == 'FR3A':
        next_action = ('完成A首审、报告检查及检查点提交推送后，继续在A数据前已冻结的FR3B；controller、模型配方、seed、原门不改。' if qualified else
                       'FR3B成功依赖保持关闭；保留首失败或审计问题，做一次有证据的有界下一判断，不补跑或放宽门。')
    else:
        next_action = ('接着另冻结新留出C4综合验收，保留自身有效域缺口；随后分别检验C5、C6、C7。' if qualified else
                       '关闭本冻结候选的成功依赖；保留负结果，做一次有证据的有界下一判断，不补跑、扩大grid或放宽门。')
    audit_short = f'首新保存核验{args.audit_status}、{args.audit_checks:,}项/{args.audit_failed:,}失败'
    archive = '../results/cpu_validation/' + directory + '/'
    commit = saved['source']['commit']
    parts = [f'# {stage}：{title}\n\n从clean `{commit}` 首次执行一次，保存状态 **{saved["status"]}**；{outcome}。实际新增{increment[0]:,}控制返回/{increment[1]:,}确认子步/{increment[2]:,}在线scalar提交；{audit_short}。\n\n'
             f'[事前冻结协议](FULL_REQUEST_PAIR_LEARNING_PROTOCOL.md) · [根归档]({archive}manifest.json) · [唯一实验输入]({archive}report_inputs.json)\n\n'
             '开发seed8001/8002/8003按冻结顺序，不宣称全局未使用或最终留出。原free root/仰卧8轴身体、理想感觉、公开guard/保护、2ms PD64/Kd4_4、固定刺激与任务目标均为先验。'
             '没有任务教师、预训练策略、PPO或GPU。接触只资格/诊断，紧凑模型只含两轴q/v和已知final requests，不能宣称全身状态闭合、安全或真机学习。\n']
    by_seed = {row['seed']: row for row in saved.get('seed_results', [])}
    if stage == 'FR3A':
        prediction_sections(parts, metrics, by_seed)
        parts.append('\nFR3A只校准及独立条件预测，没有匹配MPC控制。未来保存final requests用于离线条件输入，未来实际q/v只评分。原FR1通过与FR2负结果保持；本阶段控制flags默认false表示尚未声明控制成功。\n')
        parts.append(f'\n主任务另公开一次过早FR3B入口的strict-clean source gate拒绝：A归档尚未提交，0环境构造/物理/模型/fit；'
                     f'[该零物理源拒绝原件保留]({archive}control_source_failure/preservation_manifest.json)。'
                     '这是root提供的工程事实，writer未读取该记录；它不改写A保存预测通过，也不作为B已取得物理结果。先完成A检查点提交推送，再启动已冻结B的首次物理执行。\n')
    else:
        control_sections(parts, metrics, by_seed)
        parts.append('\n新grid spacing=.125（旧残差.03125），delta=grid−当前clip PD可达±1，但所有final请求仍±.5；通常不含purePD候选。首请求采用clip(p+(grid−p))roundtrip，前10微步held delta与native反馈、后140预测PD尾；literal-zero fallback独立。扩大函数类、粗分辨率与PD抵消均为新增先验。\n\nFR3B的fr3a_prediction_gate_passed默认false仅表示本阶段未重宣FR3A；保留已经通过的A报告与FR1事实，不用源检查失败的零物理尝试默认值覆盖它们。\n')
    contact_and_effort(parts, by_seed, stage)
    parts.append('\n## 全部保存费用与首审\n\n| 保存counter | 值 |\n|---|---:|\n')
    for key, value in sorted(cost.items()):
        parts.append(f'| {key} | {number(value)} |\n')
    runtime = saved.get('runtime', {})
    parts.append(f'\n内部计时/构造/forward/PD/guard/RLS/restore/snapshot/batch/接触/source与输出边界分别保留原件；未知内部I/O不补零，不宣称20ms实时。首次外进程wall={number(saved.get("first_execution", {}).get("wall_seconds"))}s；Python{runtime.get("python_version", "unknown")}/NumPy{runtime.get("numpy", "unknown")}/MuJoCo{runtime.get("mujoco", "unknown")}。\n\n'
        f'累计 **{totals[0]:,}控制调用 /{totals[1]:,}子步**；在线 **{totals[2]:,}**、离线 **{totals[3]:,}**，scalar更新计算合计 **{totals[2]+totals[3]:,}**。基点来自{"root固定FR3A前历史" if stage == "FR3A" else "root显式提供的A后实际累计"}，加本次保存实际增量，不用计划预算替代停止成本。\n\n'
        f'主任务首次audit **{args.audit_status}，{args.audit_checks:,}checks/{args.audit_failed:,}failed，{args.audit_rmse_vectors}个新RMSE向量**；[audit]({archive}audit_first/audit.json) · [指标复核]({archive}audit_first/metric_recheck.json)。audit事实仅由root CLI传入，writer不打开audit文件。保存一致不代替科学门。\n\n'
        f'## 下一步与边界\n\n{next_action} 阶段检查与正常提交推送后立即继续active目标。\n\n'
        'scientific_adoption、old_free_root_C4_validation、c4_scientific_validation、c4_contact_scientific_validation、c5_scientific_dependency_released保持false。C4最终新留出及C5–C7尚未验收；零停止不能证明安全。全部停止、异常、未尝试及不利时距见本报告与完整JSON，未重新算RMSE/门、fit、模型或物理。\n')
    report = ''.join(parts)
    entry = f'[{title}]({report_name})从clean{commit[:7]}保存状态{saved["status"]}，{outcome}；实际新增{increment[0]:,}/{increment[1]:,}/{increment[2]:,}在线scalar。{audit_short}、{args.audit_rmse_vectors}个新RMSE向量；完整人口、努力/接触与停止原样保留。累计{totals[0]:,}/{totals[1]:,}，online{totals[2]:,}+offline{totals[3]:,}={totals[2]+totals[3]:,}scalar。{next_action} C4最终新留出及C5–C7未验收，阶段提交推送后继续active目标。'
    texts, before = navigation(stage, entry, base, totals, increment, outcome, audit_short)
    # All data and navigation transformations succeed before the first mutation.
    with report_path.open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(report)
    for path, text in texts.items():
        path.write_text(text, encoding='utf-8', newline='\n')
    receipt = {'schema': stage + '_first_report_writing_receipt_v1', 'status': 'written',
        'created_at_utc': datetime.now(timezone.utc).isoformat(), 'source_commit': commit,
        'only_experimental_input': {'path': str(input_path), **identity(data), 'file_read_count': 1, 'JSON_parse_count': 1},
        'first_audit_from_root_CLI': {'status': args.audit_status, 'checks': args.audit_checks, 'failed': args.audit_failed, 'new_RMSE_vectors': args.audit_rmse_vectors},
        'root_additional_engineering_fact': 'FR3B premature strict-clean gate rejection, 0 constructor/physics/model/fit, preserved under A/control_source_failure; linked only, not read' if stage == 'FR3A' else None,
        'historical_baseline': {'controls': base[0], 'substeps': base[1], 'online_scalar': base[2], 'offline_scalar': base[3], 'source': 'root_fixed_before_FR3A' if stage == 'FR3A' else 'explicit_root_CLI_actual_after_FR3A'},
        'actual_saved_increment': {'control_returns': increment[0], 'confirmed_substeps': increment[1], 'online_scalar_commits': increment[2]},
        'cumulative_after_stage': {'controls': totals[0], 'substeps': totals[1], 'online_scalar': totals[2], 'offline_scalar': totals[3]},
        'saved_scientific_metrics_transcription_only': True, 'raw_model_parameter_old_experimental_result_or_audit_file_reads': 0,
        'embedded_snapshots': 'not selected/restored/copied', 'scientific_metrics_model_fit_RLS_physics_calls': 0,
        'before_navigation_documents': before, 'written_documents': {str(path): identity(path.read_bytes()) for path in (report_path, *DOCS)},
        'other_filesystem_IO': 'unmeasured_not_zero', 'commit_or_push_by_child': False}
    with receipt_path.open('x', encoding='utf-8') as stream:
        json.dump(receipt, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'stage': stage, 'report': str(report_path), 'receipt': str(receipt_path), 'outcome': outcome, 'first_audit_status': args.audit_status, 'cumulative_after_stage': receipt['cumulative_after_stage']}, ensure_ascii=False, allow_nan=False))

