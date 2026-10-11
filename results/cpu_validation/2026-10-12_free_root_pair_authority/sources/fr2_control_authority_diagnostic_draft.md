# FR2 控制作用范围与一次有限描述诊断

准备于 FR2 结果揭晓前。本轮只读当前控制/collector/序列化源码；未读 FR2、FR0 或其他 raw、模型参数与快照，未调用模型、fit、物理或核验。诊断与后续分支由 root 在 FR2 首次结果归档后决定；此处不修改科学门、网格、权重或生产代码。

## 静态控制边界

当前模型只选择 residual。每轴先得到 `p = clip(64*(target-q)-4*v, -.5, .5)`，再执行 `u = clip(p+delta, -.5, .5)`，其中 `delta` 在 ±.125 Nm 内，保持十个 2 ms 步；每步仍以真实当前 q/v 重算 PD。预测的其余 140 步 residual 为零。它不是对未裁剪 PD 直接加 residual，也不是学习完整任务控制器。

每轴实际可达区间为 `[max(-.5,p-.125), min(.5,p+.125)]`。只有内、外两次 clip 均未生效时，residual 才可视为不超过 `.125/64 = .001953125 rad` 的等效目标偏移；当 `abs(p)>.125`，它不能反转请求方向。PD 饱和时只能向内减小请求，向外 residual 可以完全不改变最终请求。这些是作用范围限制，不能据此预判模型贡献门。

PD 为 +.5 时，九个 residual 只形成五种首请求：.375、.40625、.4375、.46875、.5；双轴同时饱和时首向量至多 25 种。但同首请求的不同 residual 可能在随后十步 PD 解饱和时分叉，不能据首请求把 81 条完整候选去重。模型也可能通过选择不同 residual 或拒绝候选影响控制；全部候选不可行时是整十步 literal zero fallback，必须与 `delta=(0,0)` 仍执行 PD 区分。

## 一次无模型 trace 投影

固定输入为新 FR2 的 manifest、FR2 run 派生 summary、trace.jsonl.gz；每个文件最多读一次，trace 单次解压/顺序投影。禁止读取 models.json、predictions、FR1 轨迹、paid journal 或源码 ZIP；禁止模型恢复/预测/fit、重算 RMSE/真实努力/接触/旧科学门。FR2 run 的 control summary 不含模型系数，读取其 `control_origin_domain`、完成/停止、计数与现有科学门即可。保存本诊断配置、输入身份、实际 I/O/CPU 与全部缺失；不重试。

有限上限：三 seed × cold/learned/PD/zero，最多 36,000 行（包括 prefix），24,000 active 起点；cold/learned 最多 1,200 个保存决策、97,200 个 candidate records。不解析候选未保存的完整轨迹，不选择最佳时间窗口；PD/residual/fallback 仅按固定 target A active 0–999、B 1000–1999 与全 0–1999 报告。q/v 越域只引用 collector 已保存的全2000摘要，不造分段越域结论。所有组、所有停止保留，部分人口不排名。

每 seed/method 输出同一张简表，覆盖计划的全部 2,000 起点，至少并列：

1. **原生域覆盖**：直接复制 `control_origin_domain.q2/v2` 的 planned/paid/known/unknown、两轴 outside counts/fractions。只有 known=2000 才保留现有全人口比例，缺失时保持 null。该摘要含所有 active 起点，不重新用校准参数计算边界，也不按是否越域挑样本；轴内 min/max 盒不能代表联合动态、接触或预测有效域。
2. **PD 和最终请求饱和**：使用已保存 `public_pd_request2` 与 `requested_torque[:2]`，分别计 `abs(p)==.5`、`abs(u)==.5`，并报告 saved-PD-known、fallback、missing-nonfallback 数。fallback 没有 saved PD 时保持 unavailable，不填零、不从未来值补齐、不重放 PD。每项写明分母为该字段已知起点；只有覆盖全部2000且试验完整时，才给完整人口比例。
3. **residual 的生效幅度/方向**：仅非 fallback 且 p/u/delta 都已保存的行，描述 `d_eff=u-p` 的两轴均值绝对值、最大绝对值；分列 delta 为零、delta 非零但 d_eff 为零、同向/反向请求修正。最终 clip 损失用保存量的简单代数 `abs((p+delta)-u)` 描述，避免把浮点 subtraction 的极小差异当成剪裁。区分“修正与 delta 同向”和“修正与 PD 同向/反向”，不把 requested correction 当成实际 actuator effort。
4. **fallback 与决策描述**：每 active 行计 held_fallback；每保存 macro 决策计 fallback、feasible 数、selected residual（零/边界/内部）、首请求 unique 数、原 rejection reasons。计数分母分别为 observed active rows/returned macro decisions/returned candidate records，绝不把提前拒绝当作任务效率优势。首向量压缩仅为描述，不能证明完整候选等价。

越域摘要与饱和/residual/fallback **并列**，不计算“越域引发失败”或“饱和造成控制差”的回归/相关性因果解释。cold/learned 在各自状态上的差异不是匹配状态反事实；本轮不新增离线重规划。缺失/停止与全部2000起点分母同时可见，不以筛掉 fallback/越域点得到漂亮比例。科学门只引用正式首次结果，不由诊断重新解释或放宽。

## 后续 CPU 候选的有限边界

若后续明确需要降低规划费用，可另冻“原非负运行成本的严格下界提前截断”：只有已得到完整 feasible incumbent 且另一候选的累计成本严格大于 incumbent 完整成本时，才能不再预测该候选；相等不能截断，grid/H150/权重/guard/tie key 不变。pruned 候选的未来可行性未知，需单列状态和实际预测计数，不能伪记原 feasible/rejection records。同步81行全 horizon batch 的 incumbent 最后才产生，单纯加这个条件未必节省 CPU；如何安排 incumbent 必须另冻，不在此实现。

可证伪要求是完整选择（请求/成本/tie/selected trajectory）仍与原语义一致，实际 CPU/预测费用下降；任一失败则不能部署。该优化不会改变原控制效果，也不能挽救学习模型贡献门，因此本轮不实现新控制/新 check，不把它当作科学下一项。要扩大模型控制作用或改变优化器，必须由 root 在 FR2 结果与本诊断后提出单个有依据修订，并重新冻结；不预认定饱和、越域、更多探索或新控制结构是原因或解法。
