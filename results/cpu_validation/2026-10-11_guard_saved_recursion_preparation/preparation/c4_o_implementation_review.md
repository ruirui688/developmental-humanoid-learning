# C4 O 单次静态实施审查

范围：只阅读 `scripts/diagnose_guard_saved_recursion.py` 与
`docs/GUARD_SAVED_RECURSION_DIAGNOSTIC_PROTOCOL.md` 的实现/协议；不执行脚本、不读实际
预测载荷、W 或 trace，不计算科学统计量、不重算旧门。父任务后续增加/执行的有限合成
self-check 不属于此次独立执行；本 reviewer 没有运行数学、模型或物理。

在指定的标签坐标、固定人口及解读边界上，没有发现阻断性错误；提出一处小型 D 路径
shape 修订，父任务已转交作者纳入首次有限合成检查。此结论是静态审查，不能宣布正式
运行、科学门或 C4/C5 通过。

## 核心检查

- D11 使用保存的 terminal_qv 加原 actual−predicted terminal_errors 恢复同记录绝对
  标签，不取 qref 参数；恢复速度与原生 actual_endpoint_x22 核对。绝对 q 与原生相对 q
  的差相对 origin0 保持固定，再核 H15 最终标签与匹配 H1 标签；固定 1e−12 容差没有
  输出或部署估计 qref。D 不参与 N−K 主差表。
- 主人口是各 seed 全部 86 个 H15 origins、每个 k=1..15。每步 local H1 原点 t+k−1
  对应相同真实端点，initial/history、连续 native endpoints、previous_v、15 个已保存
  请求及最终 actual 都有匹配要求。H15 第一步预测与本 predictor 的 H1 必须相同。
- H1 的全部 100 原点单独进入固定命令阶段分类。阶段由本轴保存请求和合法上一请求
  按精确零/相等定义；q0/v0 使用第一轴类别，q1/v1 使用第二轴类别。origin0 为 trial
  首次；历史缺失有明确类别，不补零。各 predictor 的固定分母相同，不筛选失败单元。
- O 采用预测−真实，原 N terminal_errors 是相反符号。实现 e=recursive−actual、
  b=local−actual、r=recursive−local，故 e=b+r；平方能量交叉项保留。它没有累加 H1，
  没有用 RMSE 相减替代配对，也没有将 r 写为独立因果贡献。
- N−K 差仅在固定组完整、非空时给出；空或不完整组明确不可排名。q/v、各轴分开，
  没有跨单位能量排名。窗口标签复用、条件请求含 veto、guard 投影未保存及不可识别
  边界均披露。完整只表示缓存覆盖完整。
- 生产输入限制为绑定 N manifest/run/predictions，未导入预测器或仿真器，不读取旧
  metrics/trace/参数。诊断输出保留 unavailable、partial records、失败原因、费用及
  manifest；scientific_adoption/C4/C5 标志始终为 false。

## 唯一实施修订

首次静态读取时，D 路径 comprehension 包含
`if isinstance(x, list) and len(x) == 2`。这会静默过滤坏步骤；若原列表异常超长，过滤后
仍可得到 horizon 个步骤，导致步号压缩后的路径进入分析。建议先要求原
predicted_path_qv 是长度等于 horizon 的 list，再对每项严格验证两元素 list、q/v 各两
个有限标量；不静默过滤。

这是一处保存 schema/端点匹配加固，并非已经观测到的实际载荷问题。不要为此打开真实
预测数据、重跑模型或扩展一般审计。父任务已同意转作者修订，并将其放入首次有限合成
self-check；正式源码/协议的最终冻结身份及有限检查由父任务记录。

O 完成后，应据完整 e/b/r/交叉项只形成一次有依据的结构修订。此次静态审查没有提供
隐藏动力学、运动技能、控制收益或因果识别结论；旧科学门失败和持续目标 active 保持。
