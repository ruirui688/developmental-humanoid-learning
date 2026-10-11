# C4 B：同公开 guard 输入的耦合候选（正式冻结）

本协议、生产代码和标准库独立审计已冻结。`FORMAL_EXECUTION_FROZEN=True`；正式入口必须先核验 clean tracked HEAD 原字节与已封口 A 来源，随后才构造 MuJoCo 环境。人工工程尝试与真实执行分别保存；只执行一次正式开发矩阵，所有停止和实际成本保留。

正式目标是检验耦合身体模型是否对同输入映射的独立模型带来增量。A 的科学贡献通过不是 B 的运行依赖。A 数据独立审计零失败及该 seed 的完整 400 校准才是重放依赖；A 控制失败也必须原样保存。若 A 的 learned_guard 控制不完整，仍允许 B 耦合控制，但其相对 diagonal 控制增量门未评价。

## 1. 不变条件与身份

- development seeds 0/1/2，reset seeds 3757552657/1641411168/2001025171；supine；原生 8 轴中的肩 j0 与肘 j1，其余 6 轴零；baseline 接触。
- 固定 0.5 N m/轴；控制周期 20 ms，10 个 2 ms 子步；每个新增物理 trial fresh reset + 100 步零力矩前缀，不缓存、不复用物理前缀。
- 前缀后原生 qref、速度、公开范围、公开距离选定 s 与 plant fingerprint 必须精确绑定 A；不裁 qref、不修配、不重新校准。
- A 封口只接受 `results/cpu_validation/2026-10-11_guard_pair/{manifest.json,first_audit.json,raw/...}`。一个标准库 `ASourceBinding` 验证外层清单、原 raw 清单、首审 input hashes、首审脚本/依赖原字节、sourceZIP 唯一覆盖、公共资产/源代码/配置/依赖身份。所有 A 输入只通过这个对象读取；getter 返回深拷贝。
- A 审计身份使用 `failed==0`、`final_gates.data_consistency_verified==true`，生产 scope 不许降级到 synthetic；不重新执行 A auditor。缺失或不完整 calibration 按 seed blocked，无默认数据/参数。
- 正式运行前独立冻结本协议、源代码与审计脚本，从 clean tracked HEAD 开始。B 可以有新提交，但共享 A 公共资产/代码须原字节相同。

## 2. 已付费 A 数据复用

A 的 400 active 原生 calibration transitions 由原 ID、命令、完整终点与完整 20 ms 区间绑定。prefix、partial、未返回或未完成的 A calibration 不提供可用的 B 校准。完整 terminal 区间不能把其所在的未完成 calibration trial 变成完整依赖。

只建立一个 cold `GuardCoupledPairBodyModel`，结构 `coupled_hinge9`，同公开 guard 输入；每个 head 的 own prior `[1,0,.02,0]`、constant 0、四个 cross prior 0、P100I9、lambda 1、hinge .25、Euler .02。9 维对 A diagonal 5 维的参数量差异披露。每个完整 A transition 只调用原 atomic two-head RLS 一次。模型输入只为 before 原生 q/v、当时已知 request、public ranges；原生 next-v 仅作标签。G 在当前模型的 q 重算，不读未来实际力矩、平均 guard 或隐藏状态。

额外离线更新最多 1,200 vector / 2,400 scalar，不隐去、不与已付费 A 更新混合。RLS 内部原有旧模型预测最多 1,200 pair / 2,400 scalar，单独计数，不为报表重复 predict。原子失败保留已发布完整双 head 状态及计数；IO/中断后停止余下工作并 blocked，不补跑。成功后 clone_frozen；不能在预测/控制期更新。

A 独立 100 active prediction 的每个已返回起点，对 frozen coupled 只一次因果预测。完整 terminal 可评分但整个 trial 仍不完整；partial 单列、不混 complete RMSE；next state 仅在预测调用之后用于分数。不再预测、拟合或采集 A nominal_guard、learned_guard、PDselected、zero。A 对照与审计指标原样复用，注明此前已付费。此预测复用是 development reuse，不是新留出。

## 3. 唯一新增物理试验

每 seed 一个 `coupled_guard` trial：100 zero prefix + 200 active。目标前 100 为 qref+s*.04，后 100 为 qref+s*.08；模型仅看到当前目标，不预告 switch。目标在公开范围 ±.03 外则失败，不裁目标。

使用原 `FixedPairMPC`，H15、每轴 9 候选、81 常向量、原 position/velocity/effort/change cost、原边界、原 tie-break 与 zero fallback 均不变。每个数学预测在其自己的 predicted q 重算公开 G。

active 任一轴 `abs(q-qref)>=.12` 或 `abs(v)>=1` 研究停止，equal 触发，独立环境原保护不变。完整 terminal 仍计入指标和预算，但不是 completed。ordinary stop/数学异常保存并继续后续 seed；IO/中断/trace 写入失败 fatal，余下 blocked，不重跑。

实际努力来自所有原生 2 ms applied torque history，request 与 actual 分列，prefix 成本计入新物理账。已支付但未返回/未写入的子步保留；actual history 不完整时保留已知 lower bound，不把缺失视作零。风险 telemetry、fallback、饱和、末端错误、完整与 partial、初态和 frozen fingerprints 都保留。

## 4. 科学门由独立 auditor 推导

runner 不计算门。auditor 不导入 runner 或模型，不执行物理或参数学习。A 首审 data verified 是数据依赖，不替代 B 的独立重算。

1. **Coupled 自身贡献**：三个 seed 的 A calibration、A prediction、A nominal_guard 和 B coupled_guard 全完整，逐 seed 逐 axis 一步 velocity RMSE 不超过匹配 nominal 的 .8；逐 seed joint 与每轴 tracking 严格改善；joint 与每轴的三 seed mean tracking 各至少 20% 改善。
2. **相对 diagonal 增量**：先通过 coupled 自身贡献，三个 seed 必需的 A learned_guard 预测/控制也完整；逐 seed 逐 axis velocity prediction 与 tracking 不劣于 diagonal，joint tracking 三 seed mean 至少改善 5%；实际绝对努力与平方努力的 joint 三 seed mean 各不超过 diagonal 的 1.05，零分母采用零/零原规则。diagonal 控制失败时门未评价，不能用截短 RMSE 判胜。
3. **相对选定 PD**：先通过 coupled 自身贡献；三个 seed 的 A PDselected 与 B 控制完整、actual effort 完整；逐 seed joint 与各 axis tracking 不劣，joint mean 至少改善 5%，两种 joint 实际努力 mean 各不超过 PD 的 1.05。此门不要求 diagonal 增量门通过。

公共规则收益、模型学习与耦合增量分别解释；不把候选参数量差异消失化，不放宽任务、权限或停止以获得好看数字。保留全部停止 seed；没有完整依赖则 failed/未评价，不能据停止前分数通过。

## 5. 预算与输出

| 新增 B 成本（完整上限） | 数量 |
|---|---:|
| 物理 trial | 3 |
| fresh prefix + control calls | 900 |
| physics substeps | 9,000 |
| offline replay RLS vector / scalar commits | 1,200 / 2,400 |
| offline RLS internal prediction pair / scalar calls | 1,200 / 2,400 |
| offline A prediction pair / scalar calls | 300 / 600 |
| control diagnostic pair / scalar calls | 600 / 1,200 |
| MPC maximum pair / scalar attempts | 729,000 / 1,458,000 |

A 已支付的全部校准/预测/对照成本通过绑定 ledger 披露，不伪装成新增采集，也不从累计项目账移除。失败只按实际已付费/attempt/commit计；unknown 保留 lower-bound 标识，CPU/wall 时间分别报告。

输出 `metadata.json`、`episodes.json`、`seed_results.json`、`source_snapshot.zip`、`manifest.json`、`calibration_replay.jsonl.gz`、`prediction_replay.jsonl.gz`、`trace.jsonl.gz`。前两份 replay trace 只有离线数学操作；第三份 trace 只有新增 B 物理 trial。sourceZIP 包含 B 当前公共源以及 binding 已缓存的 A 外层清单、首审、六 raw 和原 sourceZIP members 原字节。A trace 的存储副本不产生新物理交互、拟合或预测；这份副本使独立 B 审计可离线重构原件。

只评价本轮 development 两关节机制。无技能获得、未见泛化、变化适应、真机或安全结论；A prediction 并非旧 low/full 门的复现。
