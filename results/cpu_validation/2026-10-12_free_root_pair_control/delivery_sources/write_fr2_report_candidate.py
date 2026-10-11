"""Unexecuted FR2 report candidate; report_inputs only, explicit --write required."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

INPUT = Path('results/cpu_validation/2026-10-12_free_root_pair_control/report_inputs.json')
REPORT = Path('docs/FREE_ROOT_PAIR_CONTROL_RESULTS.md')
RECEIPT = Path('external/fr2_report_writing_receipt.json')
DOCS = tuple(Path(p) for p in ('docs/PROGRESS.md','docs/CPU_VALIDATION_TARGET.md','docs/CONTINUOUS_EXECUTION_PLAN.md','README.md','AGENTS.md'))
BASE_CONTROL, BASE_SUBSTEPS = 337297, 2616970
ONLINE, OFFLINE = 70452, 7200
HORIZONS = (1,10,20,50,150)
METHODS = ('cold','learned','pd','zero')
ARCHIVE = '../results/cpu_validation/2026-10-12_free_root_pair_control/'


def identity(data):
    return {'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}


def number(value):
    return '不可评/unknown' if value is None else f'{value:.8g}' if isinstance(value,float) else str(value)


def vector(values):
    return '不可评' if values is None else '/'.join(number(x) for x in values)


def percent(values):
    return '不可评' if values is None else '/'.join('不可评' if x is None else f'{x*100:.4f}%' for x in values)


def boolean(value):
    return 'true' if value is True else 'false' if value is False else 'unknown'


def replace_once(text, old, new):
    if text.count(old)!=1:
        raise ValueError('unique_navigation_anchor_required:'+old[:100])
    return text.replace(old,new)


def current_paragraph(text, start, replacement):
    if start not in text:
        raise ValueError('current_navigation_anchor_missing:'+start)
    old=start+text.split(start,1)[1].split('\n\n',1)[0]
    return replace_once(text,old,replacement)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write',action='store_true',help='Root must authorize the completed FR2 report before execution.')
    parser.add_argument('--audit-status',choices=('pending','passed','failed'),default='pending')
    parser.add_argument('--audit-checks',type=int)
    parser.add_argument('--audit-failed',type=int)
    parser.add_argument('--audit-rmse-vectors',type=int)
    args=parser.parse_args()
    if not args.write:
        raise ValueError('explicit_authorized_write_required; no input has been read')
    if REPORT.exists() or RECEIPT.exists():
        raise FileExistsError('first report/receipt exists; do not overwrite or rerun')
    if args.audit_status!='pending' and (args.audit_checks is None or args.audit_failed is None):
        raise ValueError('first_root_audit_check_and_failure_counts_required')
    data=INPUT.read_bytes()
    d=json.loads(data)
    if d.get('experiment_id')!='FR2':
        raise ValueError('only_new_FR2_report_inputs_required')
    cost, metrics, rows=d['cost'],d['metrics'],d['seed_results']
    if cost['RLS_vector_update_commits']!=0 or cost['RLS_scalar_update_commits']!=0:
        raise ValueError('frozen_FR2_must_not_update')
    total_control=BASE_CONTROL+cost['control_call_returns']
    total_substeps=BASE_SUBSTEPS+cost['confirmed_physics_substeps']
    contribution=metrics['model_contribution']
    pd=metrics['pd_reference']
    success=metrics['free_root_mechanism_validation'] is True
    outcome='本域开发控制机制门通过' if success else '本域原控制门未全部通过'
    if success:
        next_action='接着冻结新留出综合C4验收，保留自身预测有效域缺口，再分别检验C5未知动力学适应、C6成熟机制与C7综合验收。'
    else:
        next_action='关闭本冻结候选的成功依赖，不补跑或放宽门；依据本次完整保存证据做一次有界判断，再确定独立下一项。'
    if args.audit_status=='pending':
        audit='**pending — FR2_AUDIT_PENDING_ROOT_FIRST_RESULT。** 首次新保存核验尚待主任务填入，不宣称独立核验已经通过。'
        audit_short='首新保存核验pending'
    else:
        audit=f"主任务首次新保存核验 **{args.audit_status}，{args.audit_checks:,} checks/{args.audit_failed:,} failed**。"
        if args.audit_rmse_vectors is not None:
            audit+=f' 新条件RMSE向量核对{args.audit_rmse_vectors}个。'
        audit+=f" [首次audit]({ARCHIVE}audit_first/audit.json) · [新指标复核]({ARCHIVE}audit_first/metric_recheck.json)。核验源码及首stdout/stderr同存。"
        audit_short=f'首新保存核验{args.audit_status}、{args.audit_checks:,}项/{args.audit_failed}失败'
    commit=d['source']['commit']
    chunks=[f'''# FR2：自由root双关节完整匹配控制首次结果

从clean `{commit}` 首次执行一次，保存状态 **{d['status']}**；{outcome}。本次实际{cost['control_call_returns']:,}控制返回/{cost['confirmed_physics_substeps']:,}确认子步，0新增RLS；{audit_short}。模型贡献门保存值为{boolean(contribution['passed'])}，强PD门available={boolean(pd['available'])}/passed={boolean(pd['passed'])}。

[事前冻结协议](FREE_ROOT_LEARNING_PROTOCOL.md) · [本次根归档]({ARCHIVE}manifest.json) · [完整报告输入]({ARCHIVE}report_inputs.json)

## 完整跟踪与实际努力矩阵

按seed依次cold+MPC、learned+MPC、强PD、zero四个fresh对象；各计划1,000zero prefix+2,000active。下表保留全部计划12项，包括停止、不完整及未尝试。RMSE仅完整且符合所需域资格的2000active人口可用，数对/三元组分别肩/肘或joint/肩/肘。actual为已保存2ms端点样本的两轴合计；不完整努力是已知下界，unknown不补零。

| seed | 方法 | 原生完整/域资格 | active已保存/计划 | joint/肩/肘RMSE rad | actual absolute Nm·s | actual squared Nm²·s | actual unknown子步 | 停止/异常 |
|---|---|---|---|---|---:|---:|---|---|
''']
    by_seed={r['seed']:r for r in rows}
    for seed in (7901,7902,7903):
        sr=by_seed.get(seed,{})
        for method in METHODS:
            trial=sr.get('controls',{}).get(method)
            score=sr.get('tracking_scores',{}).get(method,{})
            if trial is None:
                chunks.append(f'| {seed} | {method} | 未尝试 | 0/2000 | 不可评 | unknown | unknown | 未尝试 | 未尝试 |\n')
                continue
            effort=trial.get('actual_effort',{}).get('active',{})
            rmse=None if not score.get('available') else [score['joint_rmse_rad'],*score['axis_rmse_rad']]
            reason=(trial.get('stop') or {}).get('primary_reason') or (trial.get('failure') or {}).get('type') or '无'
            chunks.append(f"| {seed} | {method} | {boolean(trial.get('complete'))}/{boolean(trial.get('free_root_domain_qualification_passed'))} | {score.get('observed_active_count','unknown')}/2000 | {vector(rmse)} | {number(effort.get('actual_absolute_two_axis_nm_s'))} | {number(effort.get('actual_squared_two_axis_nm2_s'))} | {number(effort.get('unknown_actual_effort_substeps'))} | {reason} |\n")
    chunks.append('''
cold/learned/PD采用所需prefix/A/B各1000完整phase至少一个left_arm-floor正端点；zero接触仅描述，zero停止不是新增采用veto。原自由root/仰卧、理想感觉、2ms经典PD、公开guard与目标均为披露先验。零停止不能解释为安全收益，接触共现不能解释为持续支撑或接触因果。

## 原控制门

保存的三seed原RMSE算术均值直接转录，未重新计算。模型贡献要求各seed joint/两轴严格改善，三均值各改善≥20%；强PD比较以前门通过为前置，各seed三指标不劣、joint均值改善≥5%。两比较的actual absolute/squared两轴合计均值各≤1.05×基线；baseline effort0要求candidate0，RMSE0百分比不可用。

| 比较 | available/passed | 基线joint/肩/肘均值 | learned joint/肩/肘均值 | 保存改善 | 三seed逐项保存结果 |
|---|---|---|---|---|---|
''')
    for name,g in (('cold模型贡献',contribution),('强PD参考',pd)):
        mean=next((r for r in g.get('checks',[]) if r.get('scope')=='three_seed_raw_RMSE_mean'),{})
        seedchecks='; '.join(f"{r['seed']}:{boolean(r.get('available'))}/{boolean(r.get('passed'))}" for r in g.get('checks',[]) if 'seed' in r)
        chunks.append(f"| {name} | {boolean(g.get('available'))}/{boolean(g.get('passed'))} | {vector(mean.get('baseline_joint_axis_mean'))} | {vector(mean.get('learned_joint_axis_mean'))} | {percent(mean.get('improvement_fractions'))} | {seedchecks or '不可评'} |\n")
    if not contribution['passed']:
        chunks.append('\n模型贡献前置失败，正式PD门不可评；保留PD实际轨迹，不以事后比较宣告强PD门通过。\n')
    chunks.append('\n| actual努力比较 | 信号 | 保存基线均值 | learned均值 | 保存passed |\n|---|---|---:|---:|---|\n')
    for name,g in (('cold',contribution),('PD',pd)):
        for r in g.get('checks',[]):
            if r.get('scope')=='three_seed_actual_effort_mean':
                chunks.append(f"| {name} | {r['signal']} | {number(r['baseline_mean'])} | {number(r['learned_mean'])} | {boolean(r['passed'])} |\n")
    chunks.append(f'''
## 自身条件预测：全部来源和时距

六种来源为三个seed各自cold/learned控制轨迹，分别用本seed两个冻结模型、相同已保存final requests递推；不pool不同自身人口。下表每格为cold预测模型/learned预测模型的保存availability。q/v两轴原RMSE、planned/observed origins及所有H1/10/20/50/150均完整保存在[完整条件JSON]({ARCHIVE}report_inputs.json)的seed_results[].conditional_prediction_scores；该链接保留所有结果，不删不利时距或失败来源。

| seed/自身来源 | H1 2ms | H10 20ms | H20 40ms | H50 100ms | H150 300ms |
|---|---|---|---|---|---|
''')
    for seed in (7901,7902,7903):
        sr=by_seed.get(seed,{})
        for origin in ('cold','learned'):
            score=sr.get('conditional_prediction_scores',{}).get(origin,{})
            values=[]
            for h in HORIZONS:
                models=score.get('horizons',{}).get(str(h),{}).get('models',{})
                values.append('/'.join(boolean(models.get(model,{}).get('available')) for model in ('cold','learned')))
            chunks.append('| '+f'{seed}/{origin}'+' | '+' | '.join(values)+' |\n')
    chunks.append('\n重点公开H150肩q/v，完整肘及其他时距仍见上述JSON；以下为保存RMSE，不计算新差值/百分比，不以部分finite点排名。\n\n| seed/自身来源 | 预测模型 | H150保存available/observed origins | 肩q RMSE rad | 肩v RMSE rad/s |\n|---|---|---|---:|---:|\n')
    for seed in (7901,7902,7903):
        sr=by_seed.get(seed,{})
        for origin in ('cold','learned'):
            h=sr.get('conditional_prediction_scores',{}).get(origin,{}).get('horizons',{}).get('150',{})
            for model in ('cold','learned'):
                r=h.get('models',{}).get(model,{})
                q,v=r.get('q_rmse_axis_rad'),r.get('v_rmse_axis_rad_s')
                chunks.append(f"| {seed}/{origin} | {model} | {boolean(r.get('available'))}/{r.get('observed_origin_count','unknown')} | {number(q[0] if q is not None else None)} | {number(v[0] if v is not None else None)} |\n")
    chunks.append('''
planner H150使用当前target、首10步held residual及其后PD尾；actual随后会再规划。不能把planner与actual差直接归因模型。条件评分使用实际保存requests，独立FR1通过不覆盖自身有效域；即使控制门通过也不宣称闭环预测普适改善。

## 实际费用与首次核验

| 费用 | 本次保存值 |
|---|---:|
''')
    fields=(('控制attempts','control_call_attempts'),('控制returns','control_call_returns'),('确认物理子步','confirmed_physics_substeps'),('控制异常','control_call_exceptions'),('MPC attempts','MPC_decision_attempts'),('MPC returns','MPC_decision_returns'),('MPC exceptions','MPC_decision_exceptions'),('planning pair attempts','planning_pair_prediction_attempts'),('planning scalar attempts','planning_scalar_prediction_attempts'),('自身条件pair attempts','control_conditional_prediction_pair_prediction_attempts'),('自身条件scalar attempts','control_conditional_prediction_scalar_prediction_attempts'),('batch stage kernels','planning_batch_stage_batches'),('batch feature rows','planning_batch_feature_batch_rows'),('原scalar dots','planning_batch_original_scalar_dot_calls'),('serial fallback selections','planning_batch_serial_fallback_selections'),('audit snapshots','audit_contact_snapshot_returns'),('contact force queries','audit_contact_force_query_returns'))
    for label,key in fields:
        chunks.append(f"| {label} | {number(cost.get(key))} |\n")
    chunks.append(f'''
0新增RLS/任务策略学习，恢复、构造、clone/snapshot、PD、模型/guard前向与batch kernel分别保留实际计账，缺字段不填0。完整预算最多36,000控制/子步与1,200MPC决策；失败/候选拒绝按实际费用保留，不把少计算当效率优势。内部wall/CPU为{number(cost.get('wall_seconds'))}/{number(cost.get('cpu_seconds'))}s，外部首进程wall为{number(d.get('first_execution',{}).get('wall_seconds'))}s；最终压缩/写盘等边界见原件，未测内部构造/OS I/O不补零，不宣称实时。

累计 **{total_control:,}控制调用 /{total_substeps:,}子步**；在线70,452+离线7,200=77,652scalar更新计算保持。本次实际增量计账，原停止/失败、FR1辨识及准备检查费用不归零。

{audit}

报告只读取本次report_inputs.json；首audit事实由root传入。0模型/fit/物理/旧科学重算。核验只证明保存一致，不能代替科学门。

## 当前边界与下一步

{next_action} 阶段必要检查、正常提交推送后立即继续active目标。

本域开发成功也不等于C4最终新留出通过。scientific_adoption、old_free_root_C4_validation、c4_scientific_validation、c4_contact_scientific_validation、c5_scientific_dependency_released保持false；C5适应、C6成熟机制和C7综合验收仍未完成。任何停止与不利自身预测完整公开，不补跑或改门。
''')
    report=''.join(chunks)
    entry=f"[FR2首次自由root匹配控制](FREE_ROOT_PAIR_CONTROL_RESULTS.md)从clean{commit[:7]}保存状态{d['status']}，{outcome}；实际新增{cost['control_call_returns']:,}控制/{cost['confirmed_physics_substeps']:,}子步，0更新。原模型贡献门{boolean(contribution['passed'])}、强PD available={boolean(pd['available'])}/passed={boolean(pd['passed'])}；{audit_short}。全部12计划组、停止/努力及六种自身来源×两模型×五时距完整保留。累计{total_control:,}/{total_substeps:,}，online70,452+offline7,200=77,652scalar；C4最终新留出及C5–C7未验收。{next_action} 提交推送后继续active目标。"
    texts={p:p.read_text(encoding='utf-8') for p in DOCS}
    before={str(p):identity(p.read_bytes()) for p in DOCS}
    p=Path('docs/PROGRESS.md')
    texts[p]=re.sub(r'## 当前入口：[^\n]+','## 历史：FR1阶段入口',texts[p],count=1)
    texts[p]=replace_once(texts[p],'# 开发进度与仓库检查点\n\n','# 开发进度与仓库检查点\n\n## 当前入口：FR2首次完整匹配控制结果\n\n'+entry+'\n\n')
    p=Path('docs/CPU_VALIDATION_TARGET.md')
    marker=next(line for line in texts[p].splitlines() if line.startswith('| [FR1 自由身体预测]'))
    texts[p]=replace_once(texts[p],marker,marker+f'\n| [FR2 自由身体控制](FREE_ROOT_PAIR_CONTROL_RESULTS.md) | {outcome}；保存模型贡献门{boolean(contribution["passed"])}、PD门{boolean(pd["passed"])}，全部实际轨迹/努力公开 | {audit_short}；本域开发不等于新留出C4、安全或C5 release |')
    texts[p]=current_paragraph(texts[p],'[FR1首次本域身体预测]',entry)
    p=Path('docs/CONTINUOUS_EXECUTION_PLAN.md')
    start='- **FR1首次本域原预测门通过，首保存核验后继续已冻FR2。**'
    texts[p]=current_paragraph(texts[p],start,'- **FR2首次结果：** '+entry)
    old='FR1自由root辨识/预测新增21000/21000/24000在线scalar；当前累计 **337,297 控制调用 / 2,616,970 子步 / 70,452 在线scalar及7,200离线重放scalar**'
    new=f"FR1自由root辨识/预测新增21000/21000/24000在线scalar，FR2首次匹配控制新增{cost['control_call_returns']}/{cost['confirmed_physics_substeps']}/0更新；当前累计 **{total_control:,} 控制调用 / {total_substeps:,} 子步 / 70,452 在线scalar及7,200离线重放scalar**"
    texts[p]=replace_once(texts[p],old,new)
    texts[p]+='\n\n### FR2首次自由root匹配控制：全部保存结果与下一项\n\n'+entry+'\n\n全部tracking/effort、conditional availability及H150肩指标见新报告和完整JSON，不pool自身轨迹、不partial排名。保存门不替代最终新留出或C5release。\n'
    rooted=entry.replace('](FREE_ROOT_PAIR_CONTROL_RESULTS.md)','](docs/FREE_ROOT_PAIR_CONTROL_RESULTS.md)')
    p=Path('README.md')
    texts[p]=current_paragraph(texts[p],'**当前执行入口：**','**当前执行入口：** '+rooted)
    texts[p]=replace_once(texts[p],'正式物理累计 **337,297 控制调用 /2,616,970 子步**；',f"正式物理累计 **{total_control:,} 控制调用 /{total_substeps:,} 子步**；FR2新增{cost['control_call_returns']:,}/{cost['confirmed_physics_substeps']:,}/0更新；")
    texts[p]=current_paragraph(texts[p],'[FR1首次自由身体预测]',rooted)
    p=Path('AGENTS.md')
    texts[p]=current_paragraph(texts[p],'[FR1首次本域身体预测]',rooted)
    texts[p]=replace_once(texts[p],'正式物理累计 **337,297控制调用 /2,616,970子步**；',f"正式物理累计 **{total_control:,}控制调用 /{total_substeps:,}子步**；FR2新增{cost['control_call_returns']:,}/{cost['confirmed_physics_substeps']:,}/0更新，")
    REPORT.write_text(report,encoding='utf-8',newline='\n')
    for p,text in texts.items():p.write_text(text,encoding='utf-8',newline='\n')
    receipt={'schema':'FR2_report_writing_receipt_v1','created_at_utc':datetime.now(timezone.utc).isoformat(),'status':'written','only_experimental_input':{'path':str(INPUT),**identity(data),'file_read_count':1,'JSON_parse_count':1},'first_audit_from_root':{'status':args.audit_status,'checks':args.audit_checks,'failed':args.audit_failed,'new_RMSE_vectors':args.audit_rmse_vectors},'source_commit':commit,'saved_metrics_transcription_only':True,'raw_or_model_parameter_or_old_result_file_reads':0,'models_or_fit_or_physics_or_scientific_metrics_recomputed':0,'embedded_snapshot_fields':'not selected or restored','before_documents':before,'written_documents':{str(p):identity(p.read_bytes()) for p in (REPORT,*DOCS)},'other_filesystem_IO':'unmeasured_not_zero','commit_or_push_by_child':False}
    RECEIPT.write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'report':str(REPORT),'receipt':str(RECEIPT),'actual_control_increment':cost['control_call_returns'],'actual_substeps_increment':cost['confirmed_physics_substeps'],'cumulative_control':total_control,'cumulative_substeps':total_substeps,'audit_status':args.audit_status},ensure_ascii=False))


if __name__=='__main__':
    main()
