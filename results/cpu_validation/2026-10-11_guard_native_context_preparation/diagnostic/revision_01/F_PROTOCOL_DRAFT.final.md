# C4 F：固定原生上下文与保存一步误差的零更新分层

**前瞻草稿，未正式放行。** 仅在 E 首次结果、原独立首审与归档封口后，由 root
决定是否提升、绑定来源并冻结。当前没有打开任何 E 新物理、C/D 原始文件，
没有执行下述统计。本协议不改 E 候选或科学门，不引入模型特征或控制动作。

2026-10-11 工程修订：按独立静态审查补全读取费用、失败身份与独立输入质量
计数，明确异常伴 stop 和两种 score 分母；三个分数、统计公式、bins 与科学门
不变。原草稿及原源字节保存在诊断 staging 的 `revision_01/`，不覆盖首轮检查。

## 1. 问题与唯一数据来源

问题：E 保存的一步身体预测误差，是否随未输入模型的全身运动上下文变化？
只做描述性诊断，不识别因果、马达延迟或接触状态，不证明新模型贡献。

输入限于 E **首次封口保存**的 run/summary/manifest/trace：seed 0/1/2，kind
`cold11`、`learned_sparse11`、`PDselected`、`zero`，active 0–199。
同一 active 上两个独立诊断 predictor `cold11`、`learned_sparse11` 全部保留；
不得使用 planner 内部候选预测替代，不能追加 C/D 数据或拟合/预测调用。
执行前绑定 E clean commit、来源文件 SHA256、首审身份、状态与实际预算；
只允许一次流式来源提取并缓存此任务的派生行，后续从缓存描述。

唯一配对键为 `(trial_id, shared_transition_id)`，核对 seed/kind/phase/
step_index、相邻端点与 .02 s 完整区间。active = step_index−100；目标段固定
`A=0–99 (.04rad)`、`B=100–199 (.08rad)`，不按误差选择切点。

每行只用 `observation_before` 的 8D `joint_position/joint_velocity`、3D
`imu_gyro/imu_acceleration`；当前模型命令与 native history 只供来源核查。
读取该行已保存 `predicted_next_qv[predictor]` 与返回端点，按 E 原定义得到
`e_q = observed_next_q − saved_predicted_next_q`、
`e_v = observed_next_v − saved_predicted_next_v`，单位 rad/rad/s。
这两次差值是描述代数，必须另计，绝非重新调用模型。若来源已保存逐步误差，
直接复用并绑定同一个 ID，不用重新算 RMSE 或重新执行 E 首审。

只有返回并保存 **10/10 子步**、输入/预测/标签均有限且身份一致的 active
区间进入主误差统计。完整的 terminal endpoint 可进入；部分区间单列，不与
20 ms 误差合并。paid 未返回、返回但未保存、重复/缺失 ID、诊断未成功、缺失
sensor/target/history 各有独立计数；不拼接、补零、插值或重采缺失端点。
禁止读取 root quaternion、特权 qpos/qvel、未来 actual torque 或接触真值。

regular 的缺失/错误/重复 transition ID、错误 seed/kind/step/phase、倒序或非法
子步身份属于来源损坏：先记独立失败类别，再中止本次描述，不将损坏行纳入
有效统计。异常通知的重复/缺失 ID 单列，不能产生第二个 endpoint。缺失值、
形状错误、scalar 类型错误、非有限 sensor/target/保存预测/标签、未知或不连续
history、非有限误差差值等以逐行 `input_quality_flags` 和按 seed/kind/目标段的
辅助计数分别保留；同一行可有多个标志，不能将各计数相加当作样本总数。
辅助标志不替换原主误差的可用性规则，target/history 缺失也不覆盖其他质量标志。

## 2. 预先固定三个 scalar block 分数

肩肘轴为 j0/j1；其余六轴固定 j2…j7，不按相关性排序或挑某个关节。
每个 trial 的 8D `qref` 取**自己的 prefix99 原生返回端点**，不能读 D qref
或按最终姿态修配。加速度上一端点必须来自同 trial、相邻完整 20 ms 区间；
active0 用 prefix98 endpoint 对比 current prefix99 endpoint，之后沿真实过去
原生端点移位。没有连续来源时该分数 missing，绝不设成零。

| 固定分数 | 明确计算式与尺度 |
| --- | --- |
| `body6` | `sqrt(sum(j=2..7)[((q_j−qref_j)/0.15rad)^2 + (v_j/1rad/s)^2] / 12)` |
| `gyro` | `sqrt(gx^2+gy^2+gz^2) / (1rad/s)`，当前动作前陀螺仪 |
| `acc_delta` | `sqrt(sum(i=x,y,z)(a_t,i−a_(t−1),i)^2) / (1m/s^2)`，相邻动作前端点的加速度变化范数 |

三者均为无量纲；尺度固定用于可复现描述，不是安全阈值或学得门控。
加速度没有姿态解旋/重力补偿，变化可混合躯干旋转、振动和运动；不能解释成
纯线性加速度。此轮不做单维筛选、角速度积分、PCA、特征拟合或最佳滞后搜索。

三个分数分别使用完全相同的固定 bins：`[0,0.5)`、`[0.5,1)`、`[1,+∞)`。
不使用样本分位数、不合并空 bin、不看结果改边界，也不做三分数的交叉筛选。

## 3. 完整分母、连续相关与固定分段

主表固定按 **seed × kind × axis(j0/j1) × predictor × 目标段(A/B)** 分组；
q/v 误差分别报告。每个分组首先列 planned active 数、保存返回数、完整区间数、
有效诊断误差数，以及每个 score 的 valid/missing 数；不 pool seed 或不同 kind。
完整 trial 的目标段计划分母各100；停止后未发生的 endpoint 仍标 unobserved。

`counts.score_valid_n/missing_n` 的分母是所选窗口中**全部保存动作前 context**，
可能包含 partial 或唯一 unreturned 记录；它说明感觉信息可用性。
`paired_n` 与 bins 的 `fraction_of_valid_score_error_pairs` 分母则仅包含同一
predictor/axis/q-v 的完整有效误差和有效 score 配对；不把前者的 valid 数作为
后者分母。事件表同时保存这两种数量，不用缺失区间的 context 补足误差样本。

连续描述对每个 score 同时固定报告与 `signed e`、`abs(e)` 的 Pearson r，
不挑较大的相关性：以配对有效行、`math.fsum` 中心化二阶和计算。
给出 n、score/error 的 min/max、均值和中心化平方和；n<3 时 r=null/
`too_few_pairs`，任一平方和为0时 r=null/`zero_variance`，数值下溢或非有限
结果为 null/`numerical_unavailable`。无 p 值、独立样本显著性、因果解释、
拟合斜率或相关性采用阈值；序列自相关、动作选择与停止截断使 r 仅为描述。

每个固定 bin 列 n、占对应 score 有效分母的比例、signed error 均值、
mean absolute error、max absolute error；空 bin 的误差统计为 null，n=0。
不以停止前 tracking/prediction RMSE 对 kind、seed 或模型排名。
所有 predictor/axis/q/v/score 表均输出，禁止只报告有利组合。

## 4. source stop 的末20 endpoint

source stop 仅采用 E 已声明的 study/environment stop，不用误差或上下文数值
事后定义事件，常规 tail20/earlier 窗口还要求原 outcome `status=terminated`。
若 `status=exception` 同时保存 study/environment stop 标志，保留
`declared_source_stop_flags_present` 和 `stop_flags_in_exception`、原停止原因及
全部费用，但不作常规 source-stop 窗口；这表示合并异常结局单独披露，**不能
解释为没有发生物理停止**。对常规 source-stop trial，令 N 为**保存且返回的
active endpoint 个数**，
含部分 terminal endpoint，按原 step_index 排序；固定 `tail20=最后min(20,N)个`，
`earlier=之前max(N−20,0)个`。先在不分目标段的事件计数中公开：N、terminal
ID/原因、两窗口原始 endpoint 数、完整/partial 数、有效误差数、score valid/
missing 数和未返回/未保存成本；其后在原主表内增加 window 标识、仍按目标段
公开。每个 bin 和相关性的分母只来自该窗口实际有效配对，不能用20替代。

N≤20 时 earlier 分母明确为0，所有 earlier 统计为 null/`empty_window`；
不借其他 trial 填充，不计算“临停/之前改善百分比”。完整200active的 trial 没有
source stop，事件窗口为 `not_applicable`；普通异常独立报告，不能冒充物理停止。
末20的标签仅供离线事件描述，**不进入任何模型输入**；也不把短停止轨迹的
小误差、零方差或没有 earlier 当作优势。

## 5. 输出、计账与边界

输出只包含：来源/配置身份、逐 active 派生记录与 missing 原因、全固定分组表、
事件分母、全部连续相关/固定 bins、一次描述日志和完整性清单。预先独立记录
压缩/解压二进制读取 bytes 与 opens（不混用 CRLF 文本编码单位），派生行数、
有限性失败、每个 norm/平方/减法/聚合/相关性次数及 wall/CPU；保留首次失败。
实现和审计均只用标准库，不导入身体模型、runner、MuJoCo 或旧 C/D auditor。

F 本地 own source/binding/protocol 的实际 opens/binary bytes 与 Git 返回 bytes、
E 源读取、任务缓存读取分开计账。成功核对 clean F 身份后立即写入运行内存账，
再读取 E；即使首个 E hash/身份失败，最终失败记录仍保留已核 F 身份与已付费
读取。主 wall/CPU 范围止于描述输出写入和最后 run 快照，明确排除 run/manifest
最终写盘及输出完整性读取/hash；末尾 run 写盘与完整性读取/hash 另计范围，最终
manifest 序列化/写盘仍明确排除，不把这些尾部工作声称零费用。

新物理、model.predict、RLS、策略/增益/门控更新、C/D refit 和旧预测重算全部0。
`scientific_adoption.evaluated=false/passed=false` 始终固定；旧20%预测门、E完整
控制门、PD5%/努力门及 C4/C5 依赖保持原结果，不由关联或分层追认通过。
若出现一致关联，只能建议另冻结单个原生上下文模型候选；若无关联，不能排除
所有遗漏状态或非线性失配。本轮既不选新特征集，也不放行 PD 残差或新物理。
