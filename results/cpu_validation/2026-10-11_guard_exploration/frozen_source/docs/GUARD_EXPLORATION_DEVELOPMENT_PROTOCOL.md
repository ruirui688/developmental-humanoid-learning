# C4 C：同一身体模型下的固定探索规则对照

正式开发协议，执行开关已冻结。提交推送后仅从 clean tracked HEAD 首次执行；
来源字节、独立审计和已选 PD 身份在任何物理之前核验。工程假档及其失败
永久保留；它们不构成科研通过。C 不读取或重放 A/B 原始学习轨迹。

本实验使用同一 `GuardCoupledPairBodyModel`、cold prior、双输出原子 RLS
和原 `FixedPairMPC`。sparse 与 continuation 是两条独立 fresh 校准，标签不
共享。唯一研究干预为“2/8 脉冲加原生感觉 veto”整个探索规则，不能分别归因
于脉冲时长或 veto。没有任务策略、增益、成熟门控或 MPC 参数更新。

## 固定物理、模型和任务

development seed 0/1/2，对应 reset seed 3757552657/1641411168/2001025171。
supine、baseline 接触、原生肩 j0/肘 j1；其余六轴请求零。±.5 N m 权限、
20 ms 控制区间、10×2 ms 子步和原环境保护保持不变。每 trial 都新建环境、
reset 并支付100次零前缀。首次完整前缀提供 qref/v/公开范围/方向/plant 参考，
随后各前缀必须精确共同一致；不能缓存、裁 qref、修配或补复位。

两个9维身体模型分别 cold 初始化；features、P100I9、lambda1、hinge .25、
Euler .02、原子双 head publish 不变。nominal 使用同结构同初始化但冻结。
G 只来自当前原生 q、最终已知请求和公开范围，预测在自己的 predicted q
重算；不能输入计划请求、未来实际力矩、子步平均 guard、接触或隐藏参数。

控制使用原 H15、9×9=81 常向量候选、原成本、预测边界、tie/fallback。
目标 active0–99 为 qref+s*.04，100–199 为 qref+s*.08，无预告或裁剪。
PDselected 必须绑定原已选 PD 的五份身份及原协议；不扩网格、不用默认 gain。

active 返回端点任一轴 abs(q−qref)>=.12 rad 或 abs(v)>=1 rad/s 时原 StudyAbort
停止，等号触发；prefix 仅原环境保护。完整 terminal 可以 update/score，但
trial 不完整且校准不能发布 frozen；partial 单列、不更新、不混完整 RMSE。

## 探索规则

两校准各400 active，共20个20-step block：五肩、五肘、五同向、五反向。
每五块幅度依次 .125/.25/.375/.5/.25，乘固定公开方向。sparse slot0正、
slot10反，其余零。continuation slot0/1正、slot10/11反，其余零。

只有 continuation calibration 和共同 prediction 使用逐轴 native veto：本次
计划请求非零且当前 abs(v)>=.5 或 abs(q−qref)>=.06 时，该轴本次最终请求
置零。等号触发；另一轴独立决定。自然零 slot 不记 command_vetoed；当前
两种条件仍可诊断记录。threshold 是公开固定探索先验，不是学习、安全证明
或成熟门控。veto 的等待和零动作计入原预算，不延长或补采。

共同 prediction100 active、五块形状 (1,0)/(0,1)/(1,1)/(1,-1)/(1,1)、幅度
.125/.25/.375/.5/.375，使用 continuation/veto。所有可用模型先 predict，
再 step；next-v 只评分。校准只使用 update 返回的 preupdate prediction，
不得另加报告预测。控制期没有 exploration veto，最终权限不降低。

## 固定24计划和失败依赖

每 seed 顺序：calibration_sparse、calibration_continuation、prediction、
nominal_guard、learned_sparse、learned_continuation、PDselected、zero。
各两校准100+400、prediction100+100、五控制各100+200。

单组校准停止或普通数学异常仍继续另一预定组；只有该组400完整更新且
无 stop/error 才发布自己的 frozen。prediction 在至少一组发布时继续，按
nominal_guard/learned_sparse/learned_continuation 固定顺序只评分可用模型，
并评分 persistence；不存在的组明确 unavailable，不填先验或零误差。
两组都失败时 prediction blocked。learned 控制只依赖自己的校准，不能因
另一校准失败或 prediction 普通停止跳过。nominal/PD/zero 无学习依赖。
IO/中断/trace 写失败 fatal，余下计划 blocked；保留原件，不补跑。

## root 预冻结的科学门

科学门由独立 auditor 推导，runner 不判门；synthetic 永不 validate。

1. 每学习组分别要求三个 seed 必要校准、共同prediction、nominal 与自身
   控制全部完整。每seed每axis velocity RMSE<=.8 nominal；每seed每axis与
   joint tracking 严格改善，原三seed每axis均值和joint均值各改善>=20%。
2. 探索干预要求 continuation 自身贡献先通过且两组全部必要试验完整。
   每seed每axis prediction<=.8 sparse；tracking 每seed各axis/joint严格
   改善，三seed各axis/joint均值改善>=20%；joint实际绝对/平方努力均值
   各<=1.05 sparse。sparse 失败则未评价，不用截短分数凑门。
3. 各组 PD 比较先自身贡献通过，必要试验与PD三seed完整；每seed各axis/
   joint tracking不劣，joint均值改善>=5%，joint实际绝对/平方努力均值
   各<=1.05 PD。零/零满足，不允许正数对零或未知actual满足门。
4. 最低激励资格事前固定：每组每axis校准完整区间至少一条非零 start-G
   且该axis实际绝对努力总量>0；共同prediction每axis至少一条非零
   start-G。不加rank阈值；此门仅排除全零输入，不能证明充分激励。
5. matrix_complete、data_consistency_verified 分开报告；停止符合原规则
   不等于数据一致性错误。C 不提供新未见条件、技能、真机或安全结论。

## 预算与原件

24 fresh trial 最大8100控制calls/81000子步；校准2400 vector/4800 scalar
RLS，内置preupdate2400 pair/4800 scalar预测；独立prediction最多900 pair/
1800 scalar；控制起点诊断1800 pair/3600 scalar；MPC最大2187000 pair/
4374000 scalar。统计实际费用和失败/未知下界，不用 trace 完整行数替代。
新增物理和RLS仅来自C；不重放或读取A/B calibration，不复用其控制评分。

保存 metadata.json、episodes.json、seed_results.json、trace.jsonl.gz、
source_snapshot.zip、manifest.json。每校准一个独立model_update，前缀绑定、
available模型、因果预测、计划/最终请求/veto、start-G、真实子步历史和
原子失败账完整保存；计划/最终/start-G/actual剂量与veto仅描述诊断。
source ZIP 覆盖当前physics源码、asset、pyproject、C协议、C auditor、B及其
三个stdlib数学支撑、原coupled core、PDhelper/五身份原件和原PD协议。
首次执行前 root 核验clean tracked精确commit及字节，记录依赖/Python/
MuJoCo/CPU，GPU=None，提交推送后一次执行，停止和不利指标全部保留。
