"""Update current navigation and cumulative ledger after first Z2 completion."""
from pathlib import Path

repo = Path(__file__).resolve().parents[1]
current = ('最早未验收仍为C4。[Z1预测](docs/FAST_FEEDBACK_PAIR_PREDICTION_RESULTS.md)通过后，'
           '[Z2首次匹配控制](docs/FAST_FEEDBACK_PAIR_CONTROL_RESULTS.md)从clean1aaccc1完成12组全部'
           '36,000控制/子步、0停止异常。joint/肩/肘贡献7.5535%/8.8449%/5.6905%，未达原20%门；'
           '实际努力下降，正式PD门按前置条件不可评，自身长时肩预测退化。'
           '不放宽阈值或补跑，立即推进事前独立准备的FR0自由root接触工程资格。'
           '固定支撑、理想感觉与2ms经典PD是披露先验；C4及C5–C7仍未验收。'
           '持续目标active，阶段检查提交推送后立即继续。')
for name, prefix in [('README.md', '**当前执行入口：** '), ('AGENTS.md', '')]:
    path = repo / name
    data = path.read_text(encoding='utf-8')
    lines = data.splitlines()
    hits = [i for i, line in enumerate(lines) if line.startswith(prefix+'最早未验收仍为C4。[Z1首次身体预测结果]')]
    assert len(hits) == 1, (name, hits)
    lines[hits[0]] = prefix+current
    data = '\n'.join(lines)+'\n'
    if name == 'README.md':
        start = data.index('正式物理累计 **256,297')
        end = data.index('\n', start)
        data = data[:start]+('正式物理累计 **313,297 控制调用 /2,592,970 子步**；'
               'Z1新增21,000/21,000/24,000在线scalar更新，Z2新增36,000/36,000/0更新。'
               '在线46,452与离线7,200scalar更新计算保持分列，总53,652；'
               '小型ridge、规划、测试及历史GPU费用另计，记录一致不能代替科学验收。')+data[end:]
    else:
        data = data.replace('277,297控制调用 /2,556,970子步', '313,297控制调用 /2,592,970子步')
        data = data.replace('；Z0新增3,000/3,000/0更新', '；Z2新增36,000/36,000/0更新，Z0新增3,000/3,000/0更新')
    path.write_text(data, encoding='utf-8', newline='\n')

path = repo / 'docs/CONTINUOUS_EXECUTION_PLAN.md'
data = path.read_text(encoding='utf-8')
old = '；当前累计 **256,297 控制调用 / 2,535,970 子步 / 22,452 在线scalar及7,200离线重放scalar**，scalar计算合计29652'
new = ('，Z1微步辨识新增21000/21000/24000在线scalar，Z2首次控制新增36000/36000/0；'
       '当前累计 **313,297 控制调用 / 2,592,970 子步 / 46,452 在线scalar及7,200离线重放scalar**，scalar计算合计53652')
assert data.count(old) == 1
data = data.replace(old, new)
data += '''

### Z2首次完整匹配控制：原贡献门失败

[首次结果](FAST_FEEDBACK_PAIR_CONTROL_RESULTS.md)从clean1aaccc1fdfcfa0f7722494e93f82e670b5f3d9c9一次执行。
三个seed各cold/learned MPC/PD/zero四组，共12组完整；36000控制/子步，0异常/停止/failure/新增更新。
joint/肩/肘三seed原RMSE均值改善7.5534654%/8.8448927%/5.6905041%，均低于原20%门；
每seed各轴严格改善及实际努力上限通过，仍不足以通过model contribution，正式PD门不可评。
自身条件H50/H150肩q/v三seed两轨迹均退化，不把Z1独立轨迹预测通过当作闭环有效域通过。
1200MPC决策、14571279pair规划（含243返回候选拒绝、3 literal-zero fallback）、526560pair自身条件预测。
内wall/CPU1500.0350099/1484.75s，外1534.8893477s；经典反馈/支撑与额外计算费用披露。
首新保存核验120条件RMSE向量、12跟踪、24努力通过，36000trace/11772prediction records；
0模型/fit/物理及旧科学重算。首thin contract零失败，仅保存身份/计数/门一致性，不改变科学结论。
[根归档](../results/cpu_validation/2026-10-12_fast_feedback_pair_control/manifest.json)46payload，
92读146180352bytes，含manifest47写73101730bytes；报告/检查另封存。
当前累计313297控制/2592970子步；在线scalar46452、离线7200不变，总53652。
不改Z2 controller、阈值或同bank补跑；下一项为事前独立准备的FR0自由root接触工程资格，
生产发布、首次必要新纯检查、冻结/正常提交推送后首次有界运行。工程通过也仅另冻本域学习协议，
不恢复Z snapshots或解除科学C4/C5–C7；失败保留并只作有依据有限下一步。持续目标active。
'''
path.write_text(data, encoding='utf-8', newline='\n')

path = repo / 'docs/PROGRESS.md'
data = path.read_text(encoding='utf-8')
intro = '''## 当前入口：2026-10-12 Z2完整控制贡献门失败，继续FR0接触工程

[Z1指定独立预测](FAST_FEEDBACK_PAIR_PREDICTION_RESULTS.md)全门通过后，
[Z2首次控制](FAST_FEEDBACK_PAIR_CONTROL_RESULTS.md)12组全部完整36000控制/子步，零停止异常。
同MPC joint贡献7.5535%，低于事前20%门；实际努力下降，正式PD门不可评。
自身长时肩预测退化，C4及C5–C7仍未验收；不改门或补跑，立即推进事前独立准备的FR0自由root接触工程资格。
累计313297控制/2592970子步，online46452/offline7200scalar更新计算分列。
持续目标active，阶段检查提交推送后立即继续；[一页目标](CPU_VALIDATION_TARGET.md)与[阶段账本](CONTINUOUS_EXECUTION_PLAN.md)为当前导航。

'''
assert data.startswith('# 开发进度与仓库检查点\n\n')
data = data.replace('## 当前入口：2026-10-12 Z0完整工程通过，准备独立学习协议', '## 历史：2026-10-12 Z0完整工程通过，准备独立学习协议', 1)
data = data.replace('# 开发进度与仓库检查点\n\n', '# 开发进度与仓库检查点\n\n'+intro, 1)
path.write_text(data, encoding='utf-8', newline='\n')
print('Updated four current navigation/ledger documents; no experiments or metrics recalculated.')
