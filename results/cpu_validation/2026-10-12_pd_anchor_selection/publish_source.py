"""Publish one completed saved projection; never read physics inputs or models."""
from pathlib import Path
import hashlib
import json
import shutil

root = Path(__file__).resolve().parents[1]
capture = root / 'external/fr4d_first_selection_projection'
archive = root / 'results/cpu_validation/2026-10-12_pd_anchor_selection'
assert not archive.exists()
receipt = json.loads((capture / 'first_execution_receipt.json').read_text(encoding='utf-8'))
assert receipt['exit_code'] == 0 and not receipt['first_launcher_failure']
projection = json.loads((capture / 'result/projection.json').read_text(encoding='utf-8'))
assert projection['status'] == 'saved_selection_projection_complete'
assert projection['first_failure'] is None
assert projection['declared_frozen_protocol_sha256'] == '8075b168b5037fff11e03047e224e56c4e5b3f63ea19d1bdc6e7bfbcc67c0b1a'
assert len(projection['origin_records']) == 1200 and len(projection['matrix']) == 12
archive.mkdir()
pins = {}
for path in sorted(capture.rglob('*')):
    if path.is_file():
        relative = path.relative_to(capture)
        data = path.read_bytes()
        destination = archive / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        pins[relative.as_posix()] = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
source = Path(__file__).read_bytes()
(archive / 'publish_source.py').write_bytes(source)
pins['publish_source.py'] = {'bytes': len(source), 'sha256': hashlib.sha256(source).hexdigest()}
rows = []
for cell in projection['matrix']:
    count = lambda name: '/'.join(str(cell[name][key]) for key in ('true', 'false', 'NA'))
    distribution = cell['selected_minus_anchor_saved_cost_distribution']
    rows.append(f"| {cell['seed']} | {cell['method']} | {cell['scope']} | {cell['observed_origins']}/100 | {count('anchor_present_in_expected_slot')} | {count('anchor_feasible')} | {count('anchor_chosen')} | {distribution['negative']}/{distribution['exact_zero']}/{distribution['positive']}/{distribution['NA']} |")
report = '''# FR4D：一次保存 PD 锚点选择诊断

[事前协议](PD_ANCHOR_SELECTION_DIAGNOSTIC_PROTOCOL.md) · [原始输出与清单](../results/cpu_validation/2026-10-12_pd_anchor_selection/manifest.json) · [FR4B 原控制结果](PD_ANCHOR_PAIR_CONTROL_RESULTS.md)

从已推送冻结检查点 `10ae761` 首次执行一次，状态 `saved_selection_projection_complete`，无技术失败。唯一原物理来源为 clean `490fcffa0080125e7c2a8b887c99cc2743dcc01f` 的 FR4B；不重算旧控制门，不调用模型、物理、fit 或 RLS。

学习组的 600 个计划起点中，PD 锚点全部存在、全部保存为可行；只选中 12 次，另外 588 次保存的 chosen-minus-anchor 预测成本为负。纯 PD 不在候选中、或被预测约束拒绝，均不是本轮学习组这些保存起点的缺口。但成本排序不等于实际反事实表现，不能据此识别模型失配、目标偏好或真实接触的因果贡献。

冷模型的 600 个起点全部有锚点，329 个保存为可行、271 个不可行，146 个选中；271 个 fallback 时保存 public PD 字段缺失，保留 NA。其状态与学习组不同，仅作事前描述对照，不以跨状态比较认定学习原因。

## 全部固定人口

每个单元固定 100 个 origin，不筛选可行子集。前三类计数顺序为 True/False/NA；成本差为负/零/正/NA。逐起点 rejection_reason、保存 PD 字段关系、原 fallback、原成本与缺失原因完整保存在 projection.json。

| seed | 方法 | 阶段 | origin | 存在 | 可行 | 选中 | 成本差 |
|---|---|---|---|---|---|---|---|
''' + '\n'.join(rows) + f'''

## 实际费用与结论边界

本次读取 3 个固定 raw 文件、解码一次 gzip 的 36,000 行；恢复 1,200 个当前 PD 请求，21,600 次距离、2,400 次 nearest 选择、97,200 个预期 pair 枚举，只检查预定锚点槽。实际保存成本差 929 次，12 个描述单元。wall {projection['wall_seconds_before_output']:.6f}s、CPU {projection['cpu_seconds_before_output']:.6f}s，时长不含最终输出写盘；外进程时长另存首次 receipt。

新增物理、模型前向、拟合、RLS 和旧科学门重算均为零。累计保持 487,297 控制调用 / 2,766,970 子步；118,452 在线与 7,200 离线 scalar 更新合计 125,652。准备、保存投影与交付计算另列，历史费用没有归零。

关闭 PD 锚点/首请求网格微调族，不再扫描网格、成本权重、增益、时距或 seed。FR4B 肘误差和实际努力失败保持原判定，C4 及 C5–C7 未验收，五项科学采用标志仍为 false。

下一项只检验一个不同的控制用途：由冻结原生身体模型估计目标处静态保持请求，与原 PD 反馈组合，取消 81 条成本排名，保留原预测约束、实际停止与权限。目标处模型零漂移不等于真实平衡或重力辨识，必须先冻结数学规则、来源、预算与原门，再首次有限开发。该项失败则关闭单候选，不追加前馈比例或逆解阈值扫描。持续目标保持 active，提交推送后继续。
'''
(root / 'docs/PD_ANCHOR_SELECTION_DIAGNOSTIC_RESULTS.md').write_text(report, encoding='utf-8', newline='\n')
(archive / 'manifest.json').write_text(json.dumps({
    'stage': 'FR4D', 'status': projection['status'], 'files': pins,
    'source_commit': projection['source_commit'], 'frozen_protocol_sha256': projection['declared_frozen_protocol_sha256'],
    'saved_projection_cost': projection['cost'], 'science_recomputations_by_publisher': 0,
    'physics_or_model_or_fit_or_RLS_by_publisher': 0,
    'grid_family_closed': True, 'scientific_adoption': False,
    'c4_scientific_validation': False, 'c5_scientific_dependency_released': False,
    'continuous_goal_stays_active': True,
}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'stage': 'FR4D', 'status': projection['status'], 'copied_capture_files': len(pins)-1, 'report_written': True}))
