# C4 E 候选：single-lag 冻结模型的物理控制开发对照

前瞻草案，仅收拢接口；D 离线结果尚未知，本文件不是执行授权或冻结协议。
本轮不实现、不运行、不读取 D/C 数值结果，不改变阈值。root 依据 D 的逐轴
预测、数学失败和模态诊断决定是否准备物理；不得只挑有利 seed、H 或模型。

## 研究含义与候选组

最低共同矩阵为三开发 seed 0/1/2，各五个 fresh 控制 trial：

| 组 | 固定模型/控制 | 主要解释 |
| --- | --- | --- |
| cold11 | 与 D 相同冷初始化的冻结 11D；lag 系数为零 | 与学习组相同结构、权限和 MPC 的初始模型对照 |
| lag_sparse11 | D 的 sparse400 单次离线更新后已发布冻结模型 | sparse 数据学得模型的闭环贡献 |
| lag_continuation11 | D 的 continuation400 单次离线更新后已发布冻结模型 | continuation 数据学得模型的闭环贡献 |
| PDselected | Kp=(64,64)、Kd=(0,4)，绑定原选择身份 | 已具备任务能力的固定经典控制比较 |
| zero | 两轴零请求 | 被动运动、支撑与环境变化的参照 |

这里不做新 RLS、重拟合或参数更新；D 的 2400 vector/4800 scalar 上限是旧
离线成本，必须保留实际账本，不能称本轮新在线学习或冷启动技能获得。
三 seed 和旧 C/D 数据已经用于开发；新增物理轨迹也只能称开发对照。
缺失或失败的 D 冻结模型明确 unavailable/blocked，不用 prior 替换学习组。

可选增加 nominal9，作为 cold11 的数值一致性与接口回归对照，不作为更强
算法基线。零 lag 的 cold11 应在相同 q/v/u、guard、dt 与 prior 下退化为
nominal9；先用人工合成验收证明。若只保留 cold11，不能宣称已物理验证两者
精确等价；若增加 nominal9，必须事前固定全三 seed，并支付额外预算。

## 原任务与历史接口

保持原 supine/baseline、肩 j0/肘 j1、其余六轴请求零、20 ms 控制区间与
10×2 ms 子步；各 fresh trial 支付100次零前缀和最多200 active。
reset seeds 固定3757552657/1641411168/2001025171，前缀原生 qref、公开范围
和方向精确共同一致；不得裁剪、重基准、缓存或补复位以匹配旧模型。
active0–99 目标为 qref+s*.04，100–199 为 qref+s*.08，无预告或裁剪。
最终权限 ±.5 N m，控制期无探索 veto。原环境保护不变；active 返回端点
任一轴 abs(q−qref)>=.12 rad 或 abs(v)>=1 rad/s 时停止，等号触发。
完整 terminal 可作最后评分标签，但不算完整 trial；partial 单列，不混 RMSE。

active0 的当前 q/v 来自 prefix99 返回端点，previous_v 来自 prefix98 返回
端点；两区间完整、原生、连续，且 active0 起点精确相接。之后每个真实控制
起点的 previous_v 只来自过去已返回的原生端点；不能零填、跨 trial 拼接或
用本次/未来端点初始化。历史缺失在发出 active 命令前 blocked，已付前缀保留。

MPC 保持 H15、9×9=81 常力矩向量候选、原成本、预测边界、tie/fallback。
每个候选独立复制当前 native q/v/previous_v；每步 G 在该候选自身 predicted q
重新计算。得到 next_q/next_v 后令 previous_v=当前预测 v，再推进 q/v；不能
共享候选 history、保持初值或用真实未来端点纠正。只能使用候选常请求，不能
读取未来实际力矩、接触教师、隐藏动力学或后续控制请求。预测状态不能改写
真实历史；PD/zero 不调用学习模型作动作教师或接管控制。

## 评价边界、来源与预算

分别报告冷模型对两学习组、两探索来源之间及 PD 比较；完整优先、逐 seed/
axis/joint 保留结果和实际努力、风险。原20%模型贡献、5% PD比较及1.05努力
门不放宽；停止前误差不能凑门。D 同数据离线预测不替代新的独立条件，也
不能凭这一控制补试验宣布 C4 全验收或 C5/C6 放行。

root 冻结最终协议时须选择：仅做控制开发诊断，或另加原规则共同 prediction
100 active。若宣称通过原完整身体贡献门，必须明确其预测与校准依赖如何
满足；不能悄悄取消预测门。新增共同 prediction 每 seed 另付100 prefix+100
active；原 continuation/veto 仅在该采集使用，控制不使用。学习模型全程冻结。

执行前绑定精确 clean 源提交、协议/runner/auditor/core/asset 字节、Python/
NumPy/MuJoCo 版本、D manifest与首审、两已发布冻结 snapshot及fingerprint、
C 原件绑定和 PD 原选择身份。只读恢复模型，不重放 C/D 更新；D 模型失败、
来源或 fresh prefix/qref 不一致均不得自动修配。源ZIP、逐步 native 前后值、
真实历史来源ID、模型/候选预测历史、请求/start-G/实际子步、失败和账本留档。

五组方案上限15 trial、4500控制调用/45000子步；加入 nominal9 为18 trial、
5400/54000。三 MPC 组的规划上限2187000 pair/4374000 scalar预测；增加
nominal9 另付729000 pair/1458000 scalar。若加共同 prediction，另付600调用/
6000子步；三11D模型评分最多900 pair/1800 scalar，含nominal9则1200/2400。
起点诊断、工程合成、失败尝试、未知头级下界和保存预测复用分别计账；不能
把模型恢复、历史维护和诊断计算写成无计算。新模型更新0，GPU/PPO/真机0。

待 root 决定：D 结果是否支持进入控制、五组或六组、是否新增共同预测，以及
完整采用门的证据依赖。全部在首次物理前冻结；本草案不提前选择胜者或放行。
