"""Write new FR1 report from saved report_inputs only; no model/physics calls."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

INPUT = Path('results/cpu_validation/2026-10-12_free_root_pair_prediction/report_inputs.json')
PIN = {'bytes': 614989, 'sha256': '6b3e4aa9332d5269cd46210c5ce69e78ff5e2ede62291014bd3ab85e33758434'}
RECEIPT = Path('external/fr1_report_writing_receipt.json')
TARGET = Path('docs/FREE_ROOT_PAIR_PREDICTION_RESULTS.md')
DOCS = [Path(name) for name in ('docs/PROGRESS.md','docs/CPU_VALIDATION_TARGET.md','docs/CONTINUOUS_EXECUTION_PLAN.md','README.md','AGENTS.md')]

def identity(data):
    return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}

def fmt(x):
    return f'{x:.10g}'

def pair(values):
    return '/'.join(fmt(x) for x in values)

def replace(text, old, new):
    if text.count(old) != 1:
        raise ValueError('unique_document_anchor_required:' + old[:100])
    return text.replace(old, new)

if RECEIPT.exists() or TARGET.exists():
    raise FileExistsError('First report exists; no overwrite or rerun')
b = INPUT.read_bytes()
if identity(b) != PIN:
    raise ValueError('frozen_report_inputs_identity_differs')
d = json.loads(b)
metrics, cost = d['metrics'], d['cost']
means = {(r['horizon'],r['signal']):r for r in metrics['checks'] if r.get('scope') == 'three_seed_raw_RMSE_mean'}
v_text = '/'.join(f'{x*100:.4f}%' for x in means[(10,'v')]['improvement_fractions'])
q_text = '/'.join(f'{x*100:.4f}%' for x in means[(150,'q')]['improvement_fractions'])
commit = d['source']['commit']
parts = [f'''# FR1：自由root接触域身体辨识与独立预测首次结果

2026-10-12，从clean `{commit}` 首次执行一次。三个开发seed7901/7902/7903的六条校准/独立预测轨迹全部完整，21,000控制调用/21,000物理子步，0停止、0控制异常；12,000vector/24,000scalar原子在线更新。保存的原独立预测门全部通过：H10v（20ms）肩/肘三seed原RMSE均值改善 **{v_text}**，H150q（300ms）改善 **{q_text}**。

这支持本仰卧自由root域、经典PD与固定刺激条件下的局部独立条件预测贡献。FR1没有执行匹配MPC控制，不能声称控制收益、安全收益、适应或C4验收通过。首次新保存核验680,448项零失败，随后执行在FR1数据前已经冻结的FR2。

[冻结协议](FREE_ROOT_LEARNING_PROTOCOL.md) · [本次根归档](../results/cpu_validation/2026-10-12_free_root_pair_prediction/manifest.json) · [报告唯一实验输入](../results/cpu_validation/2026-10-12_free_root_pair_prediction/report_inputs.json)

## 完整人口和先验

每seed校准为1,000zero prefix+4,000active，独立预测fresh对象为1,000zero prefix+1,000active；全部按冻结顺序完成，各对象仅reset一次，没有停止补跑、自动retry或换seed。cold/learned使用本域新初始化，未恢复悬挂learned参数；learned只在校准合法完整端点更新，独立预测冻结。

原身体freejoint、仰卧初态、理想原生感觉、公开关节范围/guard、2ms反馈、PD Kp(64,64)/Kd(4,4)、受控轴最终±.5Nm、其余六轴请求零和固定刺激均为披露的初始先验。模型使用当前两轴q/v及已知最终请求；接触只作资格/诊断，不作部署输入或按接触挑训练样本。free root、其他六轴和接触模式未进入这个紧凑模型，不据此宣称状态闭合。

未来已保存final requests仅用于离线条件递推，模型逐步递推自己的q/v，未来真实q/v只作为端点标签。它不等于未知未来动作下的预测，也不覆盖FR2各控制器自身轨迹。

## 原独立预测门

以下直接转录保存的mean/check字段，未重新计算RMSE、模型或拟合；百分比仅为保存fraction的显示格式。

| 指标 | cold肩 | learned肩 | 肩改善 | cold肘 | learned肘 | 肘改善 | 事前门/保存结果 |
|---|---:|---:|---:|---:|---:|---:|---|
''']
for h,signal,label in ((10,'v','H10v，rad/s'),(150,'q','H150q，rad')):
    r=means[(h,signal)]
    parts.append(f"| {label} | {fmt(r['cold_axis_mean'][0])} | {fmt(r['learned_axis_mean'][0])} | {r['improvement_fractions'][0]*100:.4f}% | {fmt(r['cold_axis_mean'][1])} | {fmt(r['learned_axis_mean'][1])} | {r['improvement_fractions'][1]*100:.4f}% | 两轴原RMSE算术均值≥20%，通过 |\n")
parts.append('''
H10v与H150q还要求每seed两轴严格改善；H20/H50 q/v及H150v要求每seed两轴不劣，保存结果全部通过。H1与H10q仅完整报告，不追加事后veto。`complete_population=true`、`fr1_prediction_gate_passed=true`；未用有限子集排名。

下表完整公开三个seed、五个H的q/v保存结果；数对依次肩/肘，q单位rad、v单位rad/s。origin固定每10个active微步一个，两模型使用同一人口。

| seed | H/时距 | 信号 | 完整origins | cold肩/肘RMSE | learned肩/肘RMSE | 门角色与保存结果 |
|---|---|---|---:|---:|---:|---|
''')
seedmap={r['seed']:r for r in d['seed_results']}
for r in metrics['checks']:
    if 'seed' not in r: continue
    h=r['horizon']
    n=seedmap[r['seed']]['prediction_scores']['horizons'][str(h)]['planned_origin_count']
    role='只报告，完整可用' if not r['gated'] else '每轴严格改善，通过' if r['strict'] else '每轴不劣，通过'
    parts.append(f"| {r['seed']} | {h}/{h*2}ms | {r['signal']} | {n} | {pair(r['cold_axis'])} | {pair(r['learned_axis'])} | {role} |\n")
parts.append('''
## 自由root接触资格与实际努力

六条trial均native完整、metadata稳定、本域资格通过；prefix与active每个完整phase至少一个left_arm-floor正法向力端点。所有phase已付费与观察分母一致、unknown=0。接触共现不证明连续承重、支撑因果或安全；feet正接触计数为零。

| seed | trial | phase/已付费分母 | left_arm正端点 | feet正端点 | other正端点 | left_arm采样峰N | other采样峰N |
|---|---|---|---:|---:|---:|---:|---:|
''')
for sr in d['seed_results']:
    for kind in ('calibration','prediction'):
        for phase,r in sr[kind]['contact_population']['phases'].items():
            c=r['classes']
            parts.append(f"| {sr['seed']} | {kind} | {phase}/{r['confirmed_substeps']} | {c['left_arm']['positive_contact_endpoint_count']} | {c['feet']['positive_contact_endpoint_count']} | {c['other']['positive_contact_endpoint_count']} | {fmt(c['left_arm']['maximum_endpoint_normal_force_n'])} | {fmt(c['other']['maximum_endpoint_normal_force_n'])} |\n")
parts.append('''
逐0.4s块的接触比例/缺失及native输入范围完整保存在报告输入与归档，不按事后block表现新增门或剔除样本。下表actual努力为所有active已保存2ms actuator_torque端点样本的两轴合计，不能称未测连续积分或努力优势；本阶段两模型没有各自控制不同轨迹。

| seed | trial | active样本 | actual absolute，Nm·s | actual squared，Nm²·s | unknown子步 |
|---|---|---:|---:|---:|---:|
''')
for sr in d['seed_results']:
    for kind in ('calibration','prediction'):
        e=sr[kind]['actual_effort']['active']
        parts.append(f"| {sr['seed']} | {kind} | {e['captured_substeps']} | {fmt(e['actual_absolute_two_axis_nm_s'])} | {fmt(e['actual_squared_two_axis_nm2_s'])} | {e['unknown_actual_effort_substeps']} |\n")
parts.append('''
## 实际预算与计算

| 费用 | 本次保存值 |
|---|---:|
''')
fields=[('控制attempts/returns','control_call_returns'),('确认物理子步','confirmed_physics_substeps'),('保存原生端点','captured_native_endpoints'),('环境构造attempts/returns','environment_constructor_returns'),('reset attempts/returns','reset_returns'),('RLS vector attempts/returns/commits','RLS_vector_update_commits'),('RLS scalar commits','RLS_scalar_update_commits'),('RLS preupdate pair forward','rls_preupdate_pair_prediction_returns'),('RLS preupdate scalar forward','rls_preupdate_scalar_prediction_returns'),('独立预测pair attempts/returns','independent_prediction_pair_prediction_returns'),('独立预测scalar attempts/returns','independent_prediction_scalar_prediction_returns'),('独立预测axis RMSE向量计算','independent_prediction_axis_RMSE_vector_computations'),('校准PD请求','calibration_pd_request_returns'),('独立预测PD请求','prediction_pd_request_returns'),('接触审计快照attempts/returns','audit_contact_snapshot_returns'),('pair检查/force查询attempts/returns','audit_contact_force_query_returns'),('body model builds','body_model_build_returns'),('冻结clone','body_model_clone_returns'),('snapshots','body_model_snapshot_returns'),('fingerprints','body_model_fingerprint_returns'),('源码read/hash bytes','source_read_and_hash_bytes'),('FR0 gate读取bytes','gate_read_and_hash_bytes'),('paid journal写入记录','paid_interval_write_returns'),('paid journal序列化bytes','paid_interval_serialized_bytes')]
for label,key in fields: parts.append(f"| {label} | {cost[key]:,} |\n")
parts.append(f'''
0MPC决策、0教师调用、0batch fit、0任务策略更新、0GPU训练；本阶段没有control planner运行，已冻batch实现尚未产生FR2控制证据。RLS preupdate、guard/feature、actor PD及snapshot/clone分别计费，不把24,000scalar更新当作全部算力。

collector wall **{cost['wall_seconds']:.7f}s**、CPU **{cost['cpu_seconds']:.6f}s**；外部首次进程wall **{d['first_execution']['wall_seconds']:.7f}s**、exit0、stderr0bytes，首stdout保留。内部计时不含最终序列化/压缩/写盘；构造/reset内部model-build/forward次数与OS I/O未测，不填零，也不宣称实时。Python{d['runtime']['python_version']} / NumPy{d['runtime']['numpy']} / MuJoCo{d['runtime']['mujoco']}；平台{d['runtime']['platform']}。

正式物理累计 **337,297控制调用 /2,616,970子步**。本次新增21,000/21,000和24,000在线scalar；在线 **70,452**、离线重放 **7,200**，scalar更新计算合计 **77,652**。历史停止/失败、经典调优、其他ridge、规划与必要检查费用保持，不归零；准备合成检查不计为本次正式物理。

## 首次保存核验

主任务首次独立新核验 **passed，680,448 checks/0failed**，核对60个新RMSE向量、完整人口、努力/接触及来源/付费账；0模型调用、0fit、0新物理、0旧科学重算。原FR1 gate仍true。\n\n[首次audit](../results/cpu_validation/2026-10-12_free_root_pair_prediction/audit_first/audit.json) · [首次新指标复核](../results/cpu_validation/2026-10-12_free_root_pair_prediction/audit_first/metric_recheck.json)。auditor源码及首stdout/stderr同存。报告实验数值只读取本次report_inputs.json，核验事实来自主任务本次首结果转录；未打开raw、模型参数文件或旧结果，未重新调用模型、fit或物理。保存一致不能替代控制/安全科学门。

## 下一步与结论边界

完成首新保存核验、报告检查及正常提交推送后，继续同一持续目标，执行在FR1数据前冻结的[FR2](FREE_ROOT_LEARNING_PROTOCOL.md)。三个相同seed各cold+MPC、learned+MPC、强PD、zero四条fresh控制；目标、最终权限、停止、接触资格和actual努力条件保持，原20%模型贡献门先通过才评5%强PD门。不能依据FR1结果改kernel、prior、phi、刺激、时距、网格、增益或门，不恢复旧悬挂learned。

fr2_model_contribution_gate_passed、fr2_pd_reference_gate_passed、free_root_mechanism_validation当前false。scientific_adoption、old_free_root_C4_validation、c4_scientific_validation、c4_contact_scientific_validation、c5_scientific_dependency_released固定false。FR1仅本域局部独立预测开发证据；C4完整控制/新留出、C5适应、C6成熟机制与C7综合验收仍未完成。0停止不能推出安全收益。
''')
report=''.join(parts)
texts={p:p.read_text(encoding='utf-8') for p in DOCS}
before={str(p):identity(p.read_bytes()) for p in DOCS}
entry=f"[FR1首次本域身体预测](FREE_ROOT_PAIR_PREDICTION_RESULTS.md)从clean{commit[:7]}完成六条完整轨迹、21,000控制/子步与12,000vector/24,000scalar在线更新，0停止异常；H10v肩/肘均值改善{v_text}，H150q改善{q_text}，原预测门全部通过。首新保存核验680,448项零失败、60新RMSE向量及努力/接触、来源/付费账一致；随后执行已在FR1数据前冻结的FR2。原自由root/仰卧、理想感觉、2ms公共PD与固定刺激为披露先验；尚无控制/安全通过，C4及C5–C7未验收。累计337,297控制/2,616,970子步，online70,452+offline7,200=77,652scalar；阶段检查提交推送后继续active目标。"

p=Path('docs/PROGRESS.md')
texts[p]=replace(texts[p],'## 当前入口：2026-10-12 FR1/FR2自由身体学习协议准备','## 历史准备：2026-10-12 FR1/FR2自由身体学习协议准备')
texts[p]=replace(texts[p],'# 开发进度与仓库检查点\n\n','# 开发进度与仓库检查点\n\n## 当前入口：2026-10-12 FR1本域预测通过，核验后进入已冻FR2\n\n'+entry+'\n\n')

p=Path('docs/CPU_VALIDATION_TARGET.md')
old='| [FR0 自由身体接触工程](FREE_ROOT_FAST_FEEDBACK_ENGINEERING_RESULTS.md) | 6 秒完整通过：四项末窗误差与三阶段左臂接触条件均满足，零停止异常 | 本轮零学习，只证明该环境的工程资格；尚无身体学习贡献或安全结论 |'
texts[p]=replace(texts[p],old,old+f'\n| [FR1 自由身体预测](FREE_ROOT_PAIR_PREDICTION_RESULTS.md) | 六条完整、12,000vector/24,000scalar在线更新；20ms速度肩/肘均值改善{v_text}，300ms位置{q_text}，原预测门通过 | 首新保存核验680,448项零失败；指定接触域独立预测贡献，尚无匹配控制、安全或C4验收通过 |')
start='Z2 控制门失败已公开；[FR0自由身体接触工程]'
old=start+texts[p].split(start,1)[1].split('\n\n',1)[0]
texts[p]=replace(texts[p],old,entry+'\n\n已冻结FR2比较相同初始模型与学习模型、强PD的完整跟踪及actual努力，保留全部失败。C4验收后依次进入C5未知动力学适应、C6成熟机制和C7新留出综合验收。')

p=Path('docs/CONTINUOUS_EXECUTION_PLAN.md')
start='- **FR1/FR2新自由身体学习协议准备完成，等待冻结提交后首次FR1。**'
old=start+texts[p].split(start,1)[1].split('\n\n',1)[0]
texts[p]=replace(texts[p],old,'- **FR1首次本域原预测门通过，首保存核验后继续已冻FR2。** '+entry)
texts[p]=replace(texts[p],'FR0自由root工程新增3000/3000/0；当前累计 **316,297 控制调用 / 2,595,970 子步 / 46,452 在线scalar及7,200离线重放scalar**，scalar计算合计53652','FR0自由root工程新增3000/3000/0，FR1自由root辨识/预测新增21000/21000/24000在线scalar；当前累计 **337,297 控制调用 / 2,616,970 子步 / 70,452 在线scalar及7,200离线重放scalar**，scalar计算合计77652')
texts[p]+='\n\n### FR1首次自由root身体辨识与独立预测通过：接着已冻FR2\n\n'+entry+'\n\n每seed校准1000zero+4000active及独立预测fresh1000zero+1000active，六trial全完整，所有prefix/active left_arm接触phase资格通过，缺失0；接触只资格/诊断，不选择训练样本。H10v/H150q严格改善与两轴原RMSE均值≥20%，H20/H50qv及H150v逐seed不劣全过；H1/H10q只报告。\n124680pair/249360scalar独立前向、RLS preupdate12000pair/24000scalar、15000actor PD、21000audit快照/165068force查询，0MPC/teacher/taskpolicy/GPU；内wall/CPU66.0724589/64.625s、外88.2356413s。源码、native、模型初末、全部origins、stdio和停止边界归档。\n首保存核验680448项零失败、60个新RMSE向量/努力/接触/来源/付费账通过；[audit](../results/cpu_validation/2026-10-12_free_root_pair_prediction/audit_first/audit.json)及[metric recheck](../results/cpu_validation/2026-10-12_free_root_pair_prediction/audit_first/metric_recheck.json)保存。0模型/fit/新物理/旧科学重算，不重跑旧核验。预测通过不替代控制/努力优势、安全、状态闭合或C4科学验收；五个adoption/release flags固定false。\n检查报告正常提交推送后继续已冻FR2 cold/learned MPC/强PD/zero；原控制门、支撑/信息/权限不改，持续目标active。\n'

p=Path('README.md')
start='**当前执行入口：**'
old=start+texts[p].split(start,1)[1].split('\n\n',1)[0]
rootentry=entry.replace('](FREE_ROOT_PAIR_PREDICTION_RESULTS.md)','](docs/FREE_ROOT_PAIR_PREDICTION_RESULTS.md)')
texts[p]=replace(texts[p],old,start+' '+rootentry)
texts[p]=replace(texts[p],'正式物理累计 **316,297 控制调用 /2,595,970 子步**；FR0新增3,000/3,000/0更新，Z1新增21,000/21,000/24,000在线scalar更新，Z2新增36,000/36,000/0更新。在线46,452与离线7,200scalar更新计算保持分列，总53,652；','正式物理累计 **337,297 控制调用 /2,616,970 子步**；FR1新增21,000/21,000/24,000在线scalar更新，FR0新增3,000/3,000/0更新，Z1新增21,000/21,000/24,000在线scalar更新，Z2新增36,000/36,000/0更新。在线70,452与离线7,200scalar更新计算保持分列，总77,652；')
start='下一执行入口为[FR1/FR2自由身体学习协议]'
old=start+texts[p].split(start,1)[1].split('\n\n',1)[0]
texts[p]=replace(texts[p],old,'[FR1首次自由身体预测](docs/FREE_ROOT_PAIR_PREDICTION_RESULTS.md)保存的原独立门通过；首次新保存核验680,448项零失败。\n完成首核验及阶段提交推送后，立即进入已冻结的[FR2完整匹配控制](docs/FREE_ROOT_LEARNING_PROTOCOL.md)。\n尚无FR2控制/安全结果，C4及C5–C7未验收，持续目标保持active。')

p=Path('AGENTS.md')
start='FR1/FR2本域[新学习协议]'
old=start+texts[p].split(start,1)[1].split('\n\n',1)[0]
texts[p]=replace(texts[p],old,rootentry)
start='最早未验收仍为C4。[Z2完整控制]'
old=start+texts[p].split(start,1)[1].split('\n\n',1)[0]
new=old.replace(start,'历史入口（不触发重跑）：[Z2完整控制]').replace('立即另冻本域少量身体辨识、独立预测与匹配控制，不恢复悬挂learned snapshots。','后续已冻结并执行本域FR1；本段工程事实不能替代新预测/控制门，不恢复悬挂learned snapshots。')
texts[p]=replace(texts[p],old,new)
texts[p]=replace(texts[p],'正式物理累计 **316,297控制调用 /2,595,970子步**；FR0新增3,000/3,000/0更新，','正式物理累计 **337,297控制调用 /2,616,970子步**；FR1新增21,000/21,000/24,000在线scalar，FR0新增3,000/3,000/0更新，')
texts[p]=replace(texts[p],'历史在线22,452加Z1在线24,000，当前在线46,452+离线7,200=53,652scalar更新。','历史在线22,452加Z1在线24,000及FR1在线24,000，当前在线70,452+离线7,200=77,652scalar更新。')

TARGET.write_text(report,encoding='utf-8',newline='\n')
for p,text in texts.items(): p.write_text(text,encoding='utf-8',newline='\n')
receipt={'schema':'FR1_report_writing_receipt_v1','created_at_utc':datetime.now(timezone.utc).isoformat(),'status':'written_with_root_first_audit_facts','only_experimental_input':{'path':str(INPUT),**PIN,'file_read_count':3,'file_read_and_hash_bytes':1844967,'JSON_parse_count':3},'input_read_history':['first identity/content display, large output truncated','second selected summary display, output truncated','third report/navigation generation'],'source_commit':commit,'saved_metrics_used_without_recompute':True,'embedded_snapshot_fields':'Not selected/used/restored/copied into report; report_inputs itself includes them.','raw_reads':0,'model_parameter_file_reads':0,'old_result_file_reads':0,'models_or_physics_or_metrics_recomputed':0,'fit':0,'RLS':0,'cumulative_totals':'Parent-provided historical baseline plus saved FR1 increment: 337297 controls/2616970 substeps, online70452/offline7200/total77652 scalar','first_audit':{'source':'parent first result message; no audit file content read','status':'passed','checks':680448,'failed':0,'new_RMSE_vectors':60,'models_or_fit_or_new_physics_or_old_science':0},'before_documents':before,'written_documents':{str(p):identity(p.read_bytes()) for p in [TARGET,*DOCS]},'preparation_note':'Initial writer-source construction had a Python triple-quote syntax failure before any source input or document mutation; corrected source-generation quoting only.','other_filesystem_IO':'unmeasured_not_zero','commit_or_push_by_child':False}
with RECEIPT.open('x',encoding='utf-8') as stream:
    json.dump(receipt,stream,ensure_ascii=False,indent=2);stream.write('\n')
print(json.dumps({'report':str(TARGET),'report_bytes':identity(TARGET.read_bytes())['bytes'],'updated_navigation':[str(p) for p in DOCS],'receipt':str(RECEIPT),'source_reads':3,'audit':'passed_from_parent_first_result'},ensure_ascii=False))
