# X1/X2：悬挂双关节身体模型机制验证（结果读取前的设计）

本设计在 X0 数据产生前确定。执行前仍需生产入口、必要新检查和精确源码冻结，
且 X0 独立非接触工程资格必须通过；本文件不会自动启动学习或控制。
工程安装见 [X0设计](SUSPENDED_PAIR_DOMAIN_DESIGN.md)。W0 已失败的安装不使用本协议。

这是机械固定躯干、直立悬挂的左肩/左肘局部任务。机械支撑、公开资产、理想原生感觉、
关节保护及经典 PD 都是共享先验。接触按实际情况描述，不能称学习站立、接触技能或
自由 root C4 通过。只有后续完整真实接触迁移及 C5–C7 验收后，才能完成持续目标。

## 固定条件与信息边界

- 新开发 seed 固定 **7401、7402、7403**，三个都报告，不作为最终未见 seed。
- 每条轨迹 fresh 环境、原八轴初态+jitter、公共最低点+5mm 安装算法、100 zero prefix。
  不试探安装，不从成功轨迹选择初态，不重置到通过。
- 仅左肩/左肘有请求，其他六轴请求零，最终每轴权限 .5 Nm；原资产参数、地面和保护保持。
- `qref` 来自每条完整 prefix 的最后原生位置；目标方向仍按公共限位可用距离，平手正。
  fresh 轨迹与同 seed 校准 qref 必须逐轴相差≤1e-12，否则付费失败，不重新选参考。
- 原 StudyAbort 在完整控制端点检查 `abs(q-qref)>=.12 rad` 或 `abs(v)>=1 rad/s`。
  停止就是停止，不增加纠正动作，不以零停止证明安全。
- 模型仅用当前 q/v、已知最终请求和公开关节保护。下一实际 v 是自监督标签。
  接触力、真实动力学、机械反力、root姿态、IMU之外的特权状态不作模型输入。
- 公共 PD 是 **先 clip** 的 `clip(64*(target-q)-(0,4)*v,-.5,.5)`，来源是既有增益开发，
  两组共享，不再次调优。PD 和固定躯干已有能力不能记作学习获得。

## X1：有限在线辨识与独立预测

只使用原 `GuardCoupledPairBodyModel` / `coupled_hinge9` 原子两输出 RLS，
原 generic own prior、零 cross prior、P100I、lambda1、hinge .25、dt .02、endpoint Euler 不改。
每 seed 18 个系数，不引入旧 Q/K/D/22-head 或新的特征、优化器、剂量扫描。

每 seed：

1. 一条校准轨迹：100 zero + **400 active**。固定 PD 目标为 qref，最终请求为
   `clip(public_PD(qref)+pulse,-.5,.5)`。20个20步块：前5块肩、次5块肘、次5块同向、
   末5块反向；每组幅度 `.125/.25/.375/.5/.25`，块内 slot0 正、slot10 反，其余零。
   每个完整且未停止的校准 transition 原子更新两 head 一次；前缀与不完整/停止端点不更新。
   保存已付 transition 及实际提交数。cold 同初始化且冻结；learned 只在校准更新。
2. 一条 fresh 独立预测轨迹：100 zero + **100 active**。固定 PD 目标仍 qref，五个20步块
   `(1,0)/(0,1)/(1,1)/(1,-1)/(1,1)`，幅度 `.125/.25/.375/.5/.375`，slot1 正、slot9 反。
   不更新。每个 origin 分别用 cold 与 learned 递推自身 q/v；未来保存的已知 requests
   只作为离线条件输入，未来真实 q/v 仅评分，不在递推中替换。

H=`1/2/5/15` 的 origin 数分别 `100/99/96/86`。每 origin 存模型输入、预测、真实标签与误差。
全部人口完整才判门，分母零或非有限不可评，不使用有限子集排名。

预测门：H1v 每 seed 两轴严格改善，且每轴三 seed 原 RMSE 均值至少改善20%；
H15q 同样至少改善20%；H15v 以及 H2/H5 的 q/v 每 seed 两轴均不劣。
科学门失败即不进入 X2；不在同数据追加拟合、脉冲或改阈值到通过。

X1 上限 **2,100 控制调用 /21,000 子步**、**1,200 vector /2,400 scalar 在线提交**；
三个 learned frozen snapshots。独立预测上限 **12,408 pair /24,816 scalar 前向**，
RLS 内部 preupdate 前向、失败尝试和额外 PD 计算分别计数。0任务教师/策略梯度更新。

## X2：匹配完整控制

controller 在 X1 结果读取前冻结为 [ResidualPDPairMPC](../src/developmental_physics/residual_pd_pair_mpc.py)，
模型 API 为 `predict(q,v,u)`，不伪造 previous_v。

首段 `delta` 为9×9网格，逐轴范围 `[-.125,.125]`；
`u0=clip(public_PD(current)+delta,-.5,.5)`。
剩余14段只用各 candidate 自身预测 q/v 的 public PD，residual 零。
只执行首请求，再观察/重规划。目标仅当前目标，不预览切换。
`.125` 是共同权限四分之一及既有最小非零脉冲，是设计先验，不依新数据选择。
代价保持原 H15/MPCConfig：每段计 **完整最终 request** 的 effort，首change计完整请求
相对上一实际已知 request；不只给 residual 计代价。81候选包括clip后重复请求，全部计费。
完全不可行时 fallback `(0,0)`；相同 full-request/cost 的 residual 按 signed delta 固定解平手。

每 seed 四条 fresh 轨迹，顺序 cold+residual MPC、learned+residual MPC、公共 PD、zero。
每条100zero+200active；前100active为方向×.04，后100为方向×.08，均相对各自 qref。
模型/增益/门全程冻结。支撑与安装、最后权限、停止条件和评价分母各组相同。

先判模型贡献：cold/learned 全 seed 都须完整200active且实际努力完整；
每 seed joint及两axis RMSE严格改善，三个seed原 joint/各axis 均值各改善至少20%。
actual absolute 与 squared effort 两轴合计均值各≤1.05×cold。
贡献通过后再判强经典门：所需 PD 全完整，每 seed joint/axis 不劣于 PD，
joint原均值改善至少5%，两种 actual effort 均值各≤1.05×PD。
基线零时不产生百分比优势；effort基线零须candidate也零。部分停止不排名。

控制自身轨迹 H1/2/5/15 条件预测与 X1 公共预测分别报告，未来 actual requests 仅离线条件输入。
planner保存的自身PD预测轨迹与这种条件预测也分别标识；不把未来requests当在线已知信息。
完整控制门不能替代预测门，工程门不能替代科学门。

X2 上限 **3,600 控制调用 /36,000 子步**、**1,200 MPC decision**；
规划前向上限 **1,458,000 pair /2,916,000 scalar**。
自身轨迹条件预测对6条模型控制轨迹各用两个冻结模型评分，上限另
**52,416 pair /104,832 scalar**（6轨迹×2模型×4,368），
该费用不混入控制规划。记录所有完整请求PD计算、候选尝试、拒绝、fallback和异常下界。

## 科研判定与继续动作

X0+X1+X2 完整物理上限为6,000/60,000；实际按返回、停止与异常付费，不预填计划值。
每阶段保存配置、seed、精确commit/源码及依赖、原始逐子步、实际努力、模型前后指纹、
全部失败和首stdio。工程资格与科学门分列。

即使 X1/X2 都通过，也仅支持悬挂双关节机制。下一步另冻原 GroundBodyEnv
自由root/真实接触迁移、新 seed bank、共同权限与完整预测/控制门；不追认旧失败。
失败则公开收窄结论，再基于证据设计下一项，不延长同安装或同bank优化。
阶段报告、检查、正常提交和推送后立即继续持续目标，不把本阶段当终点。
