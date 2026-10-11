# FR2 后唯一控制结构候选：完整首请求网格（静态建议）

本文件仅为 root 结合一次新 FR2 authority 诊断选择下一项的设计建议，未冻结实验、未实现或执行。仅静态读取当前 `docs/FREE_ROOT_LEARNING_PROTOCOL.md`、`src/developmental_physics/fast_feedback_pair_mpc.py` 和 `external/fr2_control_authority_diagnostic_draft.md`；未读取 FR2 raw、参数、快照或旧结果。这里不认定原贡献门失败由权限结构引起，不修改 FR1/FR2 原协议、门或旧依赖。

## 可检验的静态限制

原公共反馈每轴为 `p(q,v)=clip(64*(target-q)-4*v,-.5,.5)`，原 residual `delta∈[-.125,.125]`，最终请求 `u=clip(p+delta,-.5,.5)`。因此每个当前状态的请求区间为 `[max(-.5,p-.125),min(.5,p+.125)]`。当 `abs(p)>.125` 时，非 fallback 的候选不能反转当前 PD 请求方向；PD 饱和时向外 residual 可完全被最终 clip 吞掉。

这只是控制函数类的限制。模型仍可选择缩小请求、在后续解饱和时产生不同作用或改变可行性/fallback；不能从以上代数推出实际 FR2 性能、预测准确性、接触因果或扩大权限后的收益。原 81 条候选即使具有相同首请求，随后十步仍可能分叉，不能对旧 FR2 按首请求去重、重算或追认任何门。

## 选定一个有限修订

建议选择“固定完整首请求网格、状态换算 held residual”，而不是试探多种固定 residual 幅度。

每轴网格固定 `U=(-.5,-.375,-.25,-.125,0,.125,.25,.375,.5)` Nm，共九点，**spacing=.125 Nm**。每次 macro 决策先仅用 actual 当前 native q/v 和当前目标得到公共 `p_current=clip(PD(actual_current),±.5)`。对每个首请求网格值定义 `delta_j=u_grid_j-p_current`；双轴 Cartesian product 仍为 81 条候选。

- stage 0 的 final requested torque 固定为 roundtrip语义 `clip(p_current+(u_grid_j-p_current),±.5)`；数学上覆盖完整首请求网格，但不预先承诺逐bit等于标称网格值。预测、实际、首成本和tie均使用这一实际浮点表达式，浮点舍入按原最终 clip 的实际输出保存，不能用标称网格替换已算请求，也不在首实际请求改用直接grid值。
- 每条预测都从同一个当前 native q/v 开始；每个预测微步用该候选自己的预测 q/v 重算相同 PD。前十个 2ms 微步使用不变的 `delta_j`，即 `clip(PD(predicted_qv)+delta_j,±.5)`；stage 10–149 的 residual 为零，保持原 H150=300ms 公共 PD 尾。
- 实际前十步每 2ms 用新 actual native q/v 重算同一个 PD，叠加本 macro 的 held `delta_j` 后再 clip。active0,10,…1990 重新规划；不把首 torque 恒持十步，不读未来目标切换。
- 当前 `p_current` 必须只计算一次并对所有候选共享，既不依候选模型参数生成网格，也不看未来 actual。cold/learned 采用同一规则。
- fallback 保留 literal zero 十微步；若网格换算得到 `delta=(0,0)`，它仍表示执行 PD，不能混写二者。

`delta_j` 的静态范围可以达到 ±1 Nm（如 p=.5、u_grid=-.5），但最终 requested torque 仍严格逐轴 ±.5 Nm，其他六轴请求零。扩大的是模型可选的控制函数类，并非提高电机最终许可。这个候选允许抵消和反转已 clip 的 PD，属于必须披露的新控制结构先验，也可能减弱 PD 的实际稳定作用；不能称没有新增先验或已经降低风险。

新网格必有标称首请求0，但它对应的delta是−p_current，不能把零首请求称为纯PD或literal-zero十步fallback。只有p_current两轴恰为网格值时才保证有delta=(0,0)候选；一般不保证pure-PD候选存在，这是相对原81网格的另一函数类改变，强PD仍须独立完整比较。不能加第十个点补入PD或暗中替换一个网格点。

原 residual 九点间隔 .03125 Nm 不能与新 final-grid 九点间隔 .125 Nm混写。新结构覆盖更广，但初始最终请求分辨率更粗；不在此同时保留窄网格、追加点、增加第二动作段、改变 PD 增益或扫描代价。两个结构的差异不只是一项数值幅度参数，后续结论只针对这一个冻结候选。

## 为什么选择它而不统一扩大固定 residual

只把固定 residual 从 ±.125 扩到更大值仍受当前 p 的平移和 clip 影响，不同当前状态可能出现较多重复首请求，并改变有效分辨率。完整首请求网格直接把每次规划可选的首请求人口写清楚，仍固定81/H150和同最终±.5许可。它是一项容易审查的结构实验，不是寻找最佳 residual 幅度，也不保证同首请求在后续十步等价。

另一种完整最终 torque 恒持方案会移除微步 PD 反馈；多个未来 residual 段又会改变时域函数类和搜索规模。本建议不同时引入它们。原 H150后140步假定 residual零与实际不断再规划的差异仍然存在，并需继续公开。

## 保持的比较任务和原门

身体和 free root/supine、资产/接触/重力/reset、2ms反馈/底层公开guard、原研究停止 `.12rad/1rad/s`、基础保护、方向选择、A/B目标 `.04/.08rad`、两轴最终±.5、prefix1000/active2000、实际努力分母全部保持当前协议。

成本仍逐步计完整 final request，沿用 position .1 /velocity .0002 /effort .000002，首 change .00002且对上一已知 final requested u；无 discount、相同forecast radius/速度阈值/margin/tie规则。候选 tie 保留 cost、abs(first full request)、signed first full request、signed residual；即使新首网格唯一也不修改规则。状态和预测不clip或补未来信息，接触只资格/报告，不进入部署模型。

比较组仍每seed依次 cold+同新MPC、learned+同新MPC、共享强PD、zero，每条 fresh/reset一次。必须原生执行和 actual努力完整，并满足 required方法 prefix/A/B 各完整1000且至少一个 left_arm正接触端点；zero只描述，停止原样保留，不加采用veto、不partial排名。

原贡献门不变：cold/learned每seed joint和两axis RMSE严格改善；三seed原RMSE均值joint/各axis各改善≥20%；actual absolute/squared两轴合计原均值各≤1.05×cold。贡献先过才评强PD：每seed joint/axis不劣，原joint均值改善≥5%，两种actual努力各≤1.05×PD。任何基线0或人口不可用仍按原规则；不因新函数类降20%、5%或努力门。自身条件预测全报告，不增加事后self veto。

成功也只支持新自由root双关节开发人口的局部机制。`scientific_adoption`、原C4/接触C4/C5依赖释放五flags保持false；另需新综合留出与C5/C6/C7。原 FR2 的成功依赖关闭，不把新候选作原 FR2补跑或追认。

## 新 seed 与身体模型来源

必须在任何新数据前固定三个新 seed。暂不凭未搜索整数宣称unseen，也不指定一个已用bank；root应只做一次公开源码/文档 exact整数资格搜索，记录非公开用途未知，之后冻结，不搜索到0、不扫描seed。

新seed不能把已保存7901/7902/7903的learned参数冒充同seed模型。建议在同一次事前协议中先固定新bank的原FR1配方：每seedfresh1000zero+4000active RLS校准，另fresh1000zero+1000active独立预测，冷prior/phi9/P100/lambda1/固定pulse与原预测门保持。新bank全门通过才做新controller四组完整控制，不追加FR2轨迹fit或按新诊断优化phi/增益；来源/参考/物理/执行绑定不通过即停止，全部费用保存。

若root另选择已见开发seed来做结构诊断，就应明确是开发，不称新seed验证；该选择不属于本建议的新bank完整控制路线。

## 预算、必要检查与冻结顺序

一次新bank最大21,000校准/独立控制与子步、12,000vector/24,000scalar在线提交；匹配控制最大36,000控制/子步、1200macro、14,580,000pair/29,160,000scalar规划逻辑前向；条件评分最多526,560pair/1,053,120scalar。合计57,000控制/子步，原历史累计另列不归零。81/H150不增加，但14.58m规划仍需披露真实CPU/wall，仿真等规划不证明20ms实时。

原 scalar/batch controller 及原 FR2永久保留。新结构应另有清晰候选实现/协议。现有 batch支持判定绑定原固定 residual列表，不能只绕过support检查或换私有网格而声称原等价检查覆盖新算法；如采用新batch，必须仅对新状态换算网格、micro feedback/held delta、fallback、计数与scalar reference进行必要新检查，并冻结实际实现。原RLS/MPC数学不重核，旧物理不重跑。

建议顺序：一次authority保存诊断归档 → root仅选择此一个结构或明确不采用 → 新最小实现/边界检查和静态review → 新协议/seed/预算/门/依赖源码commit正常提交推送 → clean首次一次新bank预测 → 原门通过后首次一次新匹配控制 → 保存所有停止/负结果和paid账 → 核验/报告/提交推送后继续active目标。失败不扫描delta、grid密度、H、gain、cost或seed到成功。

## 本文件边界

0 raw/参数/snapshot读取，0生产import/模型调用/fit/RLS/physics/测试或fixture执行，0生产编辑。本文只提出静态机制候选，不能代替尚待authority诊断、root的单一修订决定、正式冻结或实验事实。
