"""Publish first FR0 report and update the current navigation, no new science."""
from pathlib import Path

repo = Path(__file__).resolve().parents[1]
report = repo / 'docs/FREE_ROOT_FAST_FEEDBACK_ENGINEERING_RESULTS.md'
assert not report.exists()
report.write_bytes((repo / 'external/c4_fr0_report.md').read_bytes())
current = ('最早未验收仍为C4。[Z2完整控制](docs/FAST_FEEDBACK_PAIR_CONTROL_RESULTS.md)贡献7.55%，'
           '未达到原20%门，自身长时肩预测退化；不补跑或追认。'
           '[FR0自由root接触工程](docs/FREE_ROOT_FAST_FEEDBACK_ENGINEERING_RESULTS.md)从cleane5466d3首次'
           '完成3,000控制/子步、0停止异常；四MAE≤.01rad，三阶段左臂正接触949/990/988 of1000，工程资格通过。'
           '本轮零学习，公共PD、理想感觉与原仰卧身体是披露先验，不代表学习或安全收益。'
           '立即另冻本域少量身体辨识、独立预测与匹配控制，不恢复悬挂learned snapshots。'
           'C4及C5–C7仍未验收；持续目标active，阶段检查提交推送后立即继续。')
for name, prefix in [('README.md', '**当前执行入口：** '), ('AGENTS.md', '')]:
    path = repo / name
    lines = path.read_text(encoding='utf-8').splitlines()
    hits = [i for i, line in enumerate(lines) if line.startswith(prefix+'最早未验收仍为C4。[Z1预测]')]
    assert len(hits) == 1
    lines[hits[0]] = prefix+current
    data = '\n'.join(lines)+'\n'
    data = data.replace('313,297 控制调用 /2,592,970 子步', '316,297 控制调用 /2,595,970 子步')
    data = data.replace('313,297控制调用 /2,592,970子步', '316,297控制调用 /2,595,970子步')
    data = data.replace('；Z1新增21,000', '；FR0新增3,000/3,000/0更新，Z1新增21,000')
    data = data.replace('；Z2新增36,000', '；FR0新增3,000/3,000/0更新，Z2新增36,000')
    path.write_text(data, encoding='utf-8', newline='\n')

path = repo / 'docs/CPU_VALIDATION_TARGET.md'
data = path.read_text(encoding='utf-8')
old = '| [FR0 自由身体接触工程](FREE_ROOT_FAST_FEEDBACK_ENGINEERING_PROTOCOL.md) | 生产代码与协议已准备，六项新增纯检查首次通过；来源与失败分支规则已封存 | 尚未产生物理结果；工程通过也只允许另冻本域学习协议 |'
new = '| [FR0 自由身体接触工程](FREE_ROOT_FAST_FEEDBACK_ENGINEERING_RESULTS.md) | 6 秒完整通过：四项末窗误差与三阶段左臂接触条件均满足，零停止异常 | 本轮零学习，只证明该环境的工程资格；尚无身体学习贡献或安全结论 |'
assert data.count(old) == 1
data = data.replace(old, new)
start = data.index('Z2 首次结果已完整保存，控制门失败')
end = data.index('\n', start)
data = data[:start]+('Z2 控制门失败已公开；[FR0自由身体接触工程](FREE_ROOT_FAST_FEEDBACK_ENGINEERING_RESULTS.md)随后首次完整通过。'
       '现在另冻本域少量身体辨识、独立预测和匹配完整控制，重新初始化，不恢复悬挂学习模型。'
       '比较相同初始模型与学习模型、强 PD 的实际表现，保留原完整人口、控制门、努力约束和所有失败。'
       'C4 验收后依次进入 C5 动力学适应、C6 成熟机制和 C7 综合验收。')+data[end:]
path.write_text(data, encoding='utf-8', newline='\n')

path = repo / 'docs/CONTINUOUS_EXECUTION_PLAN.md'
data = path.read_text(encoding='utf-8')
data = data.replace('；当前累计 **313,297 控制调用 / 2,592,970 子步', '，FR0自由root工程新增3000/3000/0；当前累计 **316,297 控制调用 / 2,595,970 子步')
old = '下一项为事前独立准备的FR0自由root接触工程资格，另冻/检查/提交推送后首次执行；不改Z2门补跑，C4及C5–C7仍未验收。'
new = '随后[FR0首次接触工程](FREE_ROOT_FAST_FEEDBACK_ENGINEERING_RESULTS.md)完整通过；零学习，下一项另冻本域辨识/预测/匹配控制。不改Z2门补跑，C4及C5–C7仍未验收。'
assert data.count(old) == 1
data = data.replace(old, new)
data += '''

### FR0首次自由root真实接触工程通过：继续本域学习协议

[首次结果](FREE_ROOT_FAST_FEEDBACK_ENGINEERING_RESULTS.md)从cleane5466d326773c9565aa98f0e7063314a32eba5d4一次完成。
原仰卧freejoint、seed7800，1000zero+两目标各1000active全完整3000控制/子步，0停止/异常/failure。
两个完整末200端点窗肩/肘MAE为.000798999789/.00317621993和.00113787695/.00298779686rad，四项均≤.01。
prefix/A/B各1000接触端点无缺失，leftarm正端点949/990/988，feet均0，other985/1000/1000，工程资格通过。
prefix other峰552.5024N，接触比例不证明持续承重、接触因果或安全；公共PD/理想感觉/资产及目标是先验。
2000PD请求、3000audit快照、23493pair检查/force查询；0模型/fit/RLS/MPC/教师/任务策略/GPU。
内wall/CPU2.7291348/2.25s，外3.268851s，构造器内部forward和OS IO等unknown不补零。
[根归档](../results/cpu_validation/2026-10-12_free_root_fast_feedback_engineering/manifest.json)18payload，
36读75221368bytes、18写37610684bytes（不含末manifest写）；首thin64项零失败，
首新指标核验3000trace、四MAE/努力/接触摘要通过，3读18530042bytes、wall/CPU .3986438/.390625s，
0模型/fit/物理及旧科学重算。报告与检查另封存，不把保存一致性当学习贡献。
累计316297控制/2595970子步，online46452/offline7200scalar保持，总53652。
接着另冻自由root新初始化的身体辨识/独立预测/匹配控制协议，不恢复Z snapshots，不改既定科学门。
FR0只开放新学习协议准备，C4及C5–C7科学依赖仍未解除；持续目标active，交付后立即继续。
'''
path.write_text(data, encoding='utf-8', newline='\n')

path = repo / 'docs/PROGRESS.md'
data = path.read_text(encoding='utf-8')
intro = '''## 当前入口：2026-10-12 FR0自由身体接触工程通过，进入本域学习协议

[FR0首次结果](FREE_ROOT_FAST_FEEDBACK_ENGINEERING_RESULTS.md)完成3000控制/子步，零停止异常。
四MAE均≤.01rad，prefix/A/B左臂正接触949/990/988 of1000，完整工程门通过。
本轮零学习，接触和公共PD不能替代身体模型贡献或安全结论；[Z2原20%控制门失败](FAST_FEEDBACK_PAIR_CONTROL_RESULTS.md)保持。
当前累计316297控制/2595970子步，online46452/offline7200scalar不变。
立即另冻本自由root域新辨识、独立预测与匹配控制，不恢复悬挂learned snapshots。
C4及C5–C7未验收，持续目标active；检查提交推送后继续，以下旧记录不触发重跑。

'''
data = data.replace('## 当前入口：2026-10-12 Z2完整控制贡献门失败，继续FR0接触工程', '## 历史：2026-10-12 Z2完整控制贡献门失败，继续FR0接触工程', 1)
data = data.replace('# 开发进度与仓库检查点\n\n', '# 开发进度与仓库检查点\n\n'+intro, 1)
path.write_text(data, encoding='utf-8', newline='\n')
print('Published first FR0 result and updated current target/navigation/ledger.')
