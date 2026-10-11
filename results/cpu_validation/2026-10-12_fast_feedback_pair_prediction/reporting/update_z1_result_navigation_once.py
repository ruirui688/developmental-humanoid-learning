from pathlib import Path
repo = Path(__file__).resolve().parents[1]
intro = '**当前执行入口：** 最早未验收仍为C4。[Z1首次身体预测结果](docs/FAST_FEEDBACK_PAIR_PREDICTION_RESULTS.md)从clean7d323dc完成三个seed全部21,000控制/子步、12,000vector/24,000scalar在线更新，0停止/异常。20ms速度预测平均改善肩99.2325%/肘98.8250%，300ms位置改善97.0043%/97.6122%，全部原预测门通过。首60新RMSE向量核验通过；接着执行事前冻结Z2匹配控制，与cold MPC和强PD比较完整跟踪及实际努力。固定支撑、理想感觉与2ms经典PD是披露先验；悬挂预测通过不能解除自由root接触C4及C5–C7。持续目标active，阶段提交推送后立即继续。'
for name in ('README.md', 'AGENTS.md'):
    p = repo / name
    text = p.read_text(encoding='utf-8')
    if name == 'README.md':
        lines = text.splitlines()
        found = [i for i, line in enumerate(lines) if line.startswith('**当前执行入口：**')]
        assert len(found) == 1
        lines[found[0]] = intro
        text = '\n'.join(lines)+'\n'
    else:
        start = text.index('[Z0首次结果]')
        end = text.index('\n\n', start)
        text = text[:start]+intro.replace('**当前执行入口：** ', '')+text[end:]
        text = text.replace('正式物理累计 **256,297控制调用 /2,535,970子步**', '正式物理累计 **277,297控制调用 /2,556,970子步**')
        text = text.replace('历史在线22,452+离线7,200=29,652scalar更新计算保持', '历史在线22,452加Z1在线24,000，当前在线46,452+离线7,200=53,652scalar更新')
    p.write_text(text, encoding='utf-8', newline='\n')
plan = repo / 'docs/CONTINUOUS_EXECUTION_PLAN.md'
text = plan.read_text(encoding='utf-8')
start = text.index('- **Z1/Z2配方与控制器已准备')
end = text.index('\n', start)
text = text[:start]+'- **Z1首次身体预测全门通过，Z2待执行。** [结果](FAST_FEEDBACK_PAIR_PREDICTION_RESULTS.md)三seed完整21000/21000、12000vector/24000scalar更新、0停止/异常，H10v平均改善99.2325%/98.8250%，H150q改善97.0043%/97.6122%。60新RMSE向量独立核验通过；只证明悬挂开发域中指定独立轨迹预测贡献。事前冻结Z2完整控制上限36000调用/子步、1200MPC决策及14580000pair规划，另自身条件评分526560pair。最早未过仍完整接触C4，报告提交推送后立即Z2。'+text[end:]
text+='''

### Z1首次三seed完整身体辨识与独立预测通过

[首次结果](FAST_FEEDBACK_PAIR_PREDICTION_RESULTS.md)从clean7d323dcc4b8c303c8d76430763a09b36dbb8130a首次执行，
三个seed各1000zero+4000calibration及fresh1000zero+1000prediction全部完成。
21000attempts/returns/confirmedsubsteps，0异常/stop/failure；12000vector/24000scalar在线原子更新，
124680pair/249360scalar独立递推另计，RLS preupdate12000pair另计。H10v与H150q严格改善及均值20%门、
H20/H50qv与H150v不劣门全部通过；原生H1/H10q仅报告，无新增veto。
内wall/CPU50.2563824002/48.859375s，外75.1023936002s；0MPC/teacher/batchfit/GPU。
首次必要新saved metrics核验60RMSE向量/2886originrecords全部通过，2读5494391bytes，
解压19415072bytes，wall/CPU .5657869/.5s，0模型/fit/物理，旧科学未重算。

[根归档](../results/cpu_validation/2026-10-12_fast_feedback_pair_prediction/manifest.json)
40payload、80读66289600bytes、41写33154999bytes含manifest，wall/CPU .7025529/.140625s。
累积物理277297控制/2556970子步；在线scalar46452、离线7200不变，总scalar更新53652。
此前准备归档derive_sources原件含1处行尾空格，首次cached diffcheck报出后命令仍commit；
随后仅新增该归档文件whitespace属性，原bytes未修改，diffcheck通过并正常补充推送7d323dc，正式源干净。

固定机械支撑、公开身体、理想感觉、高频PD及新增初始化/相关标签预算全部披露。
悬挂机制开发预测通过不能追认旧自由root接触C4、控制收益/实际努力改善或C5科学依赖。
接着执行事前冻结Z2 cold/learned MPC/PD/zero完整同预算控制；不改已冻结controller与门。
阶段报告检查提交推送后立即继续，持续目标active。
'''
plan.write_text(text, encoding='utf-8', newline='\n')
print('updated current Z1 evidence and Z2 execution entry; no metrics recalculation')
