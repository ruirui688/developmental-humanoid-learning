# Y：共享双轴阻尼的悬挂双关节工程与有条件机制协议

本协议冻结唯一 Y0 工程候选及有条件 Y1/Y2 科学配方；生产入口、独立控制器及必要新静态/合成检查仍须先封口、提交推送，再从干净精确源码首次执行。本文作者不运行物理、fit、模型或正式结果检查，不读取 X0 raw 或旧 metrics。Y 是另名实验族，不能回写 X 的设计或追认原失败。

## 依据、唯一改变及结论边界

主代理提供的 X0 首次事实为：从 clean `6319fb6fe4a847f9c5178759a057cefd4b0e82ff` 执行 104 控制调用 / 1,040 子步，包含 100 prefix 和 4 active；第四个 active 完整端点肩速度为 `1.09570665 rad/s`，超过原 `1 rad/s` StudyAbort，环境停止为 false。零 fit；两个末20工程窗口均 unavailable。薄输出契约零失败只说明保存一致，不代表工程或科学通过。X0 原件、完整付费停止与负结论必须保留；不能把104步比完整300步称作效率优势。

唯一改变是将公共肩 PD 的 `Kd=0` 改为 **4**，直接采用已经公开的肘 `Kd=4`；`Kp=(64,64)`、肘 `Kd=4`、最终权限、安装、目标和全部原门不变。两轴公共 PD 为

`public_PD(target,q,v) = clip(64*(target-q) - (4,4)*v, -.5, .5)`。

该候选有有限的物理依据：原肩控制只反馈位置误差，新速度项可在位置误差尚未变号时产生制动请求；直立悬挂轻臂的步进目标和扭矩饱和允许速度先积累，加入速度反馈值得一次检验。这里不估惯量、不求最优或临界阻尼、不用 X0 轨迹拟合增益。已有肘增益在肩上并不保证合适；最终请求可能饱和，阻尼也可能增加换向、降低跟踪能力或改变探索覆盖。不能保证 Y0 通过，更不能从一条 X0 失败识别其失配因果。

**共享 `Kd=(4,4)` 是新增的经典控制先验**，具有控制知识和可能已有的任务能力。它不是学习获得；Y1/Y2 的 cold、learned、PD、校准和独立预测统一使用。X 公共 `Kd=(0,4)` 与 X1/X2/controller 的源码和协议保持冻结；不因 X0 负结果修改 X 学习控制器，也不将 Y 的收益算回 X。

降低目标或 `Kp`、平滑目标、改变安装、扩大速度阈值分别会改变任务、控制先验或验收标准；它们不是本协议的备选分支。共享速度反馈是当前一个有边界候选，不宣称它是全局最小或唯一合理设计。**Y0 若未过，立即封存并重新判断路线，不继续在同安装扫描 `Kp/Kd`、seed、目标、脉冲或权限。** 持续目标仍 active，路线判断及非物理工作继续，不把失败改成通过。

## 共同安装、信息、权限与来源

完整安装由 [X0 固定协议](SUSPENDED_PAIR_DOMAIN_DESIGN.md) 定义，直接使用已冻结的 `SuspendedGroundBodyEnv`：原资产去除 torso freejoint，identity quaternion `(1,0,0,0)`，保留八轴和八电机、几何/质量/原生阻尼/armature/限位/接触配置；另外六轴请求恒零，仍被动自由。原八轴初态 `(0,.12,0,.12,0,.12,0,.12)` 加每 seed 独立均匀 `±.015` jitter、零速度；公共最低点算法一次设置 `z=.005-lowest`，两次 reset forward，无 settling。每 fresh 对象只 reset 一次，trial 内不移动或重装。

X 已完成的 identity 装配 fixture 不重跑；Y 的安装来源、类和依赖字节完全相同。每条新物理 fresh 实例仍实际编译和 reset，这些必要计算逐项计账；它们不称新的装配验证。每 seed 的校准、独立预测和控制轨迹必须有相同安装 XML / 物理指纹及 prefix qref；不符合即付费失败，不试另一安装。固定躯干改变自由 root 动力学，支撑反力未测为 unknown，不能称零支撑。

模型只消费自身两轴原生 `q/v`、已知最终请求、公开关节限位以及合法同 trial 标签；不读未来实际力矩、不补虚构历史。接触、根世界位姿、真实动力学与安装反力只作诊断；IMU、其余六轴 q/v 也不进入模型/动作选择。left_arm/feet/other 的真实 floor 接触完整描述，但不参与悬挂工程门；偶然脚部接触不能证明手臂接触学习。

原环境 2ms 子步保护、每控制10子步及基础 guard 不变。完整控制端点 StudyAbort 任一受控轴 `abs(q-qref)>=.12 rad` 或 `abs(v)>=1 rad/s` 即停止，等号停止。终端完整区间先保存/付费，停止和 partial 均不算 completed；不补纠正动作。prefix 失败不发布 qref 或执行 active。

qref 来自本 trial 完整 prefix99 after 原生两轴位置。公共限位方向仍为 `+1` 当 `U-qref >= qref-L`，否则 `-1`，平手正；目标必须保留 `.03 rad` 限位 margin，不裁目标/改方向。控制任务 active0..99 为 `qref+s*.04`，100..199 为 `qref+s*.08`，没有切换预览。

独立源码名为 `scripts/validate_damped_suspended_pair_engineering.py` 和 `src/developmental_physics/damped_residual_pd_pair_mpc.py`；工程 runner 只绑定工程静态依赖，不能暗中导入学习入口。生产源、本文和所有实际静态依赖使用精确 bytes/SHA 及 clean40位 commit 核验；源验证失败先于构造，原件和零/已付费失败分支保留。Y 科学入口另实现并冻结，不自动由本文 fit。新 KD4 控制器只复制冻结 X 的控制语义并改变共享增益，不修订 X 文件。

## Y0：唯一工程资格

唯一工程 seed 为 **7500**，最大 **300 控制调用 /3,000 子步**：100 zero prefix 后200公共 PD active。没有 pulse、模型恢复/forward、fit、RLS、MPC、策略、增益更新或教师。KD4 新 prior 在执行前固定，不能由途中表现更新。

工程门保持原完整优先语义：

1. 固定 upright torso 与公开八轴/八电机映射、参数、编译拓扑符合冻结安装，安装未漂移。
2. 全100prefix+200active和全部3,000子步完整；无环境停止、StudyAbort或采集异常；原生传感、实际 actuator torque、已应用请求、时间与固定 mount 诊断完整有限。
3. active80..99及180..199各20个完整端点，肩和肘各 MAE `<=.01 rad`；共四 MAE 必须通过。`full_trial_required=True`；partial 不能给出可用窗口或子集通过。结构完整时每窗另需自身20个有限误差，后处理失败的 availability 独立记录。

一次资格失败即关闭 Y1/Y2 物理开关。源/运行/后处理错误保留其类别、首次 stdio、原件及付费下界，不能伪称科学门失败或补跑到成功；后续路线判断不能暗中重启本次 Y0。工程通过只允许执行已经先冻结、另有来源与预算的 Y1；不代表学习、风险下降或旧自由 root C4 通过。

以下 flags 在 Y0 保持 false：`scientific_adoption`、`old_free_root_C4_validation`、`c4_scientific_validation`、`c4_contact_scientific_validation`、`c5_scientific_dependency_released`。Y1/Y2 若通过，只能另报告悬挂局部机制开发门，不把这些旧域/整体结论 flags 改为 true。

## 有条件 Y1：同模型的有限在线辨识与独立预测

仅在 Y0 完整资格通过且 Y1/Y2 源码、必要新检查及本文已经冻结后执行。开发 seeds 唯一 **7501、7502、7503**，全部报告，既不选择最好 seed，也不当最终未见 bank。除共享 `Kd=(4,4)` 与独立 seed 名称外，保持 [X1/X2 配方](SUSPENDED_PAIR_LEARNING_PROTOCOL.md)。

使用原 `GuardCoupledPairBodyModel` / `coupled_hinge9`，原 generic own prior、zero cross prior、`P=100I`、lambda1、hinge `.25`、dt `.02` 和 endpoint Euler 不变。每 seed18系数；cold 同初始化冻结，learned 只在校准做原子两 head RLS。不引入 Q/K/D/22-head、额外特征、优化器、拟合回放或剂量扫描。

每 seed 一条 fresh 校准：100zero+400active，当前目标固定 qref。公共 PD **先 clip**，再加 pulse，最终再 clip `.5 Nm`。20个20步块：前5肩、次5肘、次5同向、末5反向；每组幅度 `.125/.25/.375/.5/.25`，slot0正、slot10反，其余零。只对完整且未停止 transition 原子更新两 head；prefix、partial 和停止端点不更新，已付费样本及尝试仍保存计账。

每 seed 另一条 fresh 独立预测：100zero+100active，固定 PD 目标 qref，五个20步块方向 `(1,0)/(0,1)/(1,1)/(1,-1)/(1,1)`，幅度 `.125/.25/.375/.5/.375`，slot1正、slot9反。禁止更新。fresh qref 与同 seed 校准逐轴差 `<=1e-12`，否则原样失败。

每个 origin 对 cold/learned 独立递推自身 q/v。H=`1/2/5/15` 的 origin 数为 `100/99/96/86`；未来保存 requests 仅为离线条件输入，未来真实 q/v 只评分。保存全部模型输入、预测、标签、误差及模型指纹；全人口完整才判门，零分母或非有限不可评，不使用有限子集排名。

原预测双门保持：H1v 与 H15q 每 seed 两轴严格改善，且各轴三个 seed 的原 RMSE 均值至少改善20%；H15v 以及 H2/H5 q/v 每 seed 两轴均不劣。H1q只报告，不新加或放宽 veto。未通过不进入 Y2，不在同 bank 追加校准、改 pulse、改模型或门。

Y1 上限 **2,100 控制调用 /21,000 子步**、**1,200 vector /2,400 scalar 在线提交**，三个 learned frozen snapshots；独立评分上限 **12,408 pair /24,816 scalar 前向**。RLS内部 preupdate 前向、失败尝试、额外 PD 计算分开计账；0任务教师或策略梯度更新。

## 有条件 Y2：共享 KD4 的匹配完整控制

仅 Y1 原预测门全过且生产 controller 在 Y1 结果读取前已冻结才执行；即使工程或预测门通过也不修改控制器。每 seed 四条 fresh 轨迹，依次 cold+残差 MPC、learned+残差 MPC、公共 KD4 PD、zero。各100zero+200active，模型/增益/权限/安装/停止/门全程冻结；目标使用上述 `.04 -> .08`，各100active。

与 X 控制语义一致：H15；首残差逐轴 `[-.125,.125]` 的9×9网格，公共 PD 先 clip、加首 delta 后最终 clip `.5`。余14段仅各 candidate 自身预测 q/v 的公共 KD4 PD、残差零；只执行首请求，再观测/重规划。81候选包括 clip 后重复请求且全部计费；目标只当前值，不预告切换；全部不可行 fallback `(0,0)`。同 full-request/cost 以 signed delta 固定解平手。

代价保持原 H15/MPCConfig；每段用**完整最终 request** 的 effort，首 change 相对上一实际已知 request，不能只罚 residual。模型 API 仍 `predict(q,v,u)`，不虚构 previous_v 或注入 privileged 状态。

先判模型贡献：cold/learned 全 seed 完整200active及实际努力完整；每 seed joint和两axis RMSE严格改善，三个 seed 原 joint/各axis 均值分别至少改善20%；两轴合计 actual absolute/squared effort 原均值分别 `<=1.05*cold`。

贡献过后判强经典门：PD全 seed 完整，每 seed joint/axis 不劣于 PD，joint 原均值至少改善5%；两种 actual effort 原均值分别 `<=1.05*PD`。RMSE基线零不产生百分比优势；努力基线零则 candidate也须零。zero组停止原样报告，不以 partial RMSE 给任何停止轨迹排名。

自身控制轨迹 H1/2/5/15 条件预测、Y1共同独立预测及 planner 自身PD预测轨迹分别报告；未来实际请求只作离线条件输入，不能称在线已知。工程、预测、控制与强PD门分列，互不代替。

Y2 上限 **3,600 控制调用 /36,000 子步**、**1,200 MPC decisions**、**1,458,000 pair /2,916,000 scalar 规划前向**。另6条模型控制轨迹×2冻结模型×4,368的自身条件评分上限 **52,416 pair /104,832 scalar 前向**，不混入规划。公共 PD 调用、候选尝试/拒绝、fallback、模型异常、下界与未知均记录。

## 计账、失败和后续持续目标

Y0+有条件Y1+有条件Y2完整上限为 **6,000 控制调用 /60,000 子步**；只有实际执行才入实际账，不预填完整值。X0 的104/1,040、旧W0和此前正式费用继续保留并另加，不因另名 Y 归零。

每阶段保存配置、全部 seeds、精确 commit/依赖、首 stdio、XML和参数指纹、原始逐子步/控制端点、实际 absolute/squared effort、模型前后 snapshots、全部停止/异常和逐 seed 原指标。控制调用尝试/返回、已确认积分与保存 capture分别报告。冻结核心不能完整测量的异常 integration/forward尝试、未保存端点及努力明确 unknown/已知下界；0 fit不等于0计算。来源读取、静态解析、编译/reset、PD、RLS、规划/评分、压缩/写盘和外层耗时分项，不以sample数代替已付积分。

通过 Y 所有门也仅支持：在公开机械支撑、原生感觉和共享 KD4 PD 先验下，悬挂双关节在线模型提供的局部机制收益。X/Y 用不同 seed且 X0未完整，不是新增阻尼的匹配因果实验；不声称纯婴儿式从零运动、自由 root接触成功、载荷适应或真实机器人可用。

后续仍需另冻结完整自由 root/真实接触迁移、新留出综合对照及 C5变化适应、C6成熟、C7验收，旧C4依赖不解除。Y0失败则路线重新判断；Y1/Y2负结果公开收窄结论，不通过延长剂量或连续参数候选取得漂亮结果。报告、相关检查、正常提交推送后直接继续 active持续目标，不把本局部阶段当终点。

## 本次设计读取和准备边界

首次准备仅读取冻结 X 安装协议10,498 bytes及 X 学习协议7,267 bytes，共17,765已知返回源字节；没有读正式raw、X0/旧metrics或调用模型。公共 docs/README/AGENTS/src/scripts/tests 的整数字边界搜索发现7500仅既有费用预算/测试，未见作为seed；7501–7503无匹配。此核查不证明未公开raw从未使用这些数。初次rg未启PCRE2而语法拒绝，随后一次正确查询已保留；搜索和OS/backend IO真实总量未知。

X0事实由主代理转录，精确源commit用只读 `git rev-parse`解析。另与设计代理核对同一未执行科学配方，不读取结果。本文首次静态语法/格式/链接及新KD4源review的费用由后续receipt另记；本次作者 **0物理、0fit、0model/RLS、0正式结果审计、0装配重复、0commit/push**。
