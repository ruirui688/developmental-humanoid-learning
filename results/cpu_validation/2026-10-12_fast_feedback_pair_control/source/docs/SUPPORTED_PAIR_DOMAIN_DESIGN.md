# W：固定躯干、真实地面接触的新支撑域设计

本文件的 **W0 安装与任务资格段是本次正式冻结工程协议**；W1/W2 与迁移段仅是有条件的后续设计，尚未实现或获准直接运行学习。W0 的源码、必要新检查和本协议提交推送后，才从干净提交首次执行一次；正式学习仍须另行实现、审阅和冻结到新的干净提交。U 的 Q phi50/C400 优化器候选族已关闭；V 的 oracle18 路径已关闭。本设计不恢复这些搜索，不追认原自由躯干 C4，不解除原 C5 科学依赖，也不能作为整个持续目标完成。

## 要回答的问题

在机械支撑固定躯干、仍保留原身体资产和真实地面接触的条件下，少量原生左肩/左肘反馈能否形成有效的两轴耦合预测，并在相同经典反馈与残差控制器中改善完整任务？

固定躯干有明确的额外机械先验与支撑能力；PD 已有任务控制能力。即使通过，结论也只适用于这个新支撑域，不代表婴儿式全身技能获得。不能把 V 的负结果解释为支撑、感觉或接触的因果证据。改变支撑的动机是建立有边界的分层任务，而非识别旧失配原因。

## 唯一安装方案及原域差异

supported 模型从原 `ground_body.xml` 在 reset 前生成派生 XML，保留源文件的八个关节、八电机及标称几何、惯量、阻尼、armature、限位、接触材料与碰撞过滤。结构改动是移除 torso 的 freejoint，使 torso 固定在世界安装位姿。删除六个自由 root DOF 会改变编译模型、动力学与约束反力；不能声称它与原资产完整动力学相同。每 trial 保存派生 XML 原字节、安装变换及实际编译参数差分；生成 XML 与安装后的 runtime arrays 分开记录，不把编译前 XML 假称实际安装模型。六个非受控关节仍是原被动自由关节，请求恒零；不增添持姿控制器，也不锁死它们。

安装姿态固定为原 supine 的 `R_y(-pi/2)`。每个 fresh trial 的八轴初态完全使用原 reset 规则：近中性 `(0,.12,0,.12,0,.12,0,.12)` 加同一 seed 的八维 `[-.015,.015]` 扰动，速度全零。首先在这个角度/姿态计算所有身体 primitive 的最低点，再一次性设置 torso 安装高度，使最低点高于原 floor **.005 m**。这一计算与原 reset 摆放法一致，发生在第一次物理之前；没有未计费 settling。

安装高度仅由公开形态、固定初态及固定 clearance 算法确定，不能读取试跑结果。prefix、校准或评估开始后，torso 位姿与安装高度保持不变。禁止在 smoke 后降低/抬高安装、换方向、换 contact profile、改变摩擦或增大权限来获得通过。

原任务每轴方向精确固定为 `s_i=+1` 当 `U_i-qref_i >= qref_i-L_i`，否则 `s_i=-1`；L/U 是该轴公开限位，等距取正。原 `.04 -> .08 rad` 目标保留；不能根据 contact 或表现倒转目标。supine 下正肩角可能压向地面，固定 torso 后目标可能不可达，这是需实测并可否定本安装的主要风险。不能把解析几何担忧冒充已发生物理失败。

地面与全部身体碰撞均保留，不能以水平无接触两连杆替代正式域。固定 torso 不等于固定接触集合：左臂可发生接触、分离、摩擦和限位保护；这些事件从真实 MuJoCo 积分记录。机械安装阻止躯干运动并承担未知反力。安装暴露为全程固定支撑，不能计为零支撑；未测安装反力明确 unknown，不假称支撑力或能耗为零。

## W0：先冻结的有限工程/任务资格

本次唯一工程 seed 固定为 **7300**，它不作为后续未见科学 seed。fresh reset，**100 zero prefix + 200 active**，最大 **300 控制调用 / 3,000 子步**，无 RLS、模型预测或 MPC。

active 使用已公开的 `PD Kp=(64,64), Kd=(0,4)`，总请求逐轴 clip 到 `.5 Nm`，另外六轴零。两段目标精确为 active0..99 的 `qref+s*.04`、active100..199 的 `qref+s*.08`，不预告切换。qref 是本 trial 完整 prefix99 后的原生 q，不使用旧 trace、缓存或修配。只有完整、有限且无停止的100prefix才发布qref；先按公开限位margin `.03`验证两个目标，目标不可行即失败，不clip或调方向。

所有原环境 before/after 每2ms保护保留；StudyAbort仍是控制端点规则，不伪称每子步的独立安全保护。每个返回完整10子步的active区间先保存完整原生端点、目标误差、实际history、接触与paid账，再判任一受控轴 `abs(q-qref)>=.12 rad` 或 `abs(v)>=1 rad/s` 仍研究停止，等号停止。该完整terminal区间计费/保存，但不把trial标completed。环境停止保留主reason，若同时达到StudyAbort可另记，不覆盖；partial区间不得通过完整门。工程门额外要求：

1. 独立资产无 freejoint，八关节/电机名称顺序与动作映射完整，`nq=nv=nu=8`；公开限位和原执行器/接触参数无意外变化。所有日志的 root 位姿来自 torso 世界位姿，不能把新的 qpos 前三项误当 root。
2. 不积分的 reset 对照显示 supported 与原 supine 的初始世界几何一致；随后 torso pose 完全固定，原生传感器有限，保护及 paid counters 正确。
3. 一个完整 100 prefix 与完整 200 active，2000 active 子步完整，原实际 absolute/squared 努力完整；不允许 partial RMSE 代替完成。
4. 通过原始 contact pair/force 记录证明左上臂或左前臂确有与 floor 的真实接触。资格固定要求完整 prefix 最后 20 区间至少一个已保存子步具有这些 pair 的有限正法向力；这只确认域，不证明安全或模型有效。
5. **新增严格可达性门**：两目标段各最后 20 个完整端点，每轴目标 MAE 都 `<=.01 rad`。该值是本协议首次物理前冻结的工程阈值，不得看结果后调整。这一工程门不能替代后续 20%/5% 科学比较。

W0 首次只运行一次。停止、solver warning、接触资格不满足、目标不可达或写盘失败均封存实际费用和结果；本安装不开始正式学习。若安装被否定，后续只能另立新域协议、重新冻结与计账，不能在本次 invocation 中移动安装直到通过。旧自由 root 失败与 W0 负结果永久保留。

### W0 首次命令与冻结门

生产入口固定为 `src/developmental_physics/supported_environment.py` 和 `scripts/validate_supported_pair_engineering.py`；本协议固定为当前文件。source pins 包含新代码、本协议以及作为共享形态/保护先验的原 environment/asset 原字节，不读科学 raw。独立派生 XML 在 reset 生成并保存，不新增浮动外部资产依赖。

仓库根目录的唯一准备 self-check（仅新的编译/mj_forward/组合夹具，0mj_step；只首次执行）：

```powershell
$env:PYTHONPATH = "src"
external/cpu_physics_env/Scripts/python.exe scripts/validate_supported_pair_engineering.py --repo D:/Codex_ws/robot_rl --output external/c4_w_selfcheck_01 --self-check
```

必要新检查与协议封口、提交推送后，检查工作树clean、HEAD与实际tracked bytes一致；将下列 `SOURCE_COMMIT` 替换为真实40位冻结commit。唯一正式物理首次命令为：

```powershell
$env:PYTHONPATH = "src"
external/cpu_physics_env/Scripts/python.exe scripts/validate_supported_pair_engineering.py --repo D:/Codex_ws/robot_rl --output external/c4_w_engineering_01 --source-commit SOURCE_COMMIT
```

output 必须是新目录，已有则拒绝覆盖。wrapper负责保存首次stdio与外耗时。正式入口只运行W0，**不能因W0通过而自动fit、calibrate或进入W1/W2**；W0失败立即封存，随后有依据的新选择仍另需冻结。source/pins/安装/保护/任务资格不满足，保存已经发生的费用及unknown，不重试到成功。

工程准备只需新 XML/映射、固定 root 日志语义、reset 安装数学、保护/partial 支付和新 failure wire 的合成检查。MuJoCo 编译/forward 的静态检查是非零计算、零积分；实际 smoke 才计物理。不要重跑已通过的 RLS 数学、旧 MPC 或旧 G/V 科学审计。

## W1：单一身体模型与新物理数据

W0 通过后，正式学习仍等待生产实现/协议/必要新检查冻结并推送，再从新 clean commit 首次执行。建议 development seeds **7301/7302/7303**，正式冻结前按账本核实；不称其未见最终测试 bank。

只使用原 `GuardCoupledPairBodyModel` 的 `coupled_hinge9` 原子双 head RLS：当前两轴 q/v、当前已知最终请求和公开 guard。原 generic own prior、零 cross prior、P100I、lambda1、hinge .25、dt .02 和 endpoint Euler 保留；每 seed 18 个系数。没有 22-head 转移、Q 二次特征、未来 18 替换、额外优化器或参数扫描。

每 seed 一个 fresh calibration trial：100 zero prefix + 400 active。两个模型共享 cold 初始化；cold 禁止更新，learned 每完整 calibration transition 原子更新两 head。可用的行为候选是**固定 PD(qref) + 原 C400 脉冲**：前五块肩、再五块肘、再五块同向、末五块反向，20-step block、slot0/10 为正/反脉冲，其余零，幅度 `.125/.25/.375/.5/.25`，最后总请求 clip `.5`。PD 稳定 qref，脉冲增加辨识信息；模型消费最终已知请求，不消费未来实际力矩。该行为与旧 open-loop C400 不同，属于额外经典反馈先验，须单独冻结，不是从原数据补标签。

每 seed 一个独立 fresh prediction trial：100 zero prefix + 100 active，固定五块 `(1,0)/(0,1)/(1,1)/(1,-1)/(1,1)`、幅度 `.125/.25/.375/.5/.375`，同样固定 PD(qref) 与 1/9 脉冲，总请求 `.5`。calibration 与 prediction 不混用。qref/public ranges 的一致性先核验，失配付费并失败，不调安装匹配。

预测仅对新 trace 的完整窗口进行一次评分，H=`1/2/5/15`，固定 origin 数 `100/99/96/86`。未来已保存最终 requests 仅作离线条件输入，实际未来 q/v 只在评分使用；不能在闭合中注入真实状态。新域比较 cold9/learned9，旧 K/D 数值和旧双门仍原样保留，不跨域恢复旧模型当匹配基线。

W1 完整上限 **2,100 控制调用 /21,000 子步**，**1,200 vector /2,400 scalar 在线 RLS 提交**，3 个 frozen learned snapshots。两个模型的 H1/2/5/15 预测上限 **12,408 pair /24,816 scalar 调用**；RLS 内部 preupdate 和 PD 计算另记，预测失败的已付尝试照计。

新域独立预测门沿用已有严格规则：全部人口完整；H1v 各 seed 两轴严格改善且每轴三 seed 原 RMSE 均值改善至少20%；H15q 同样至少20%，H15v 各 seed 不劣；H2/H5 q/v 各 seed 不劣。分母零/非有限不可评估，不以可用子集通过。W1 失败不进入 W2，也不通过追加数据、改变脉冲或模型取得通过。

## W2：共享经典反馈的完整控制比较

W1 通过才首次运行新控制矩阵；controller 必须在 W1 科学结果读取前冻结，避免据结果选择残差尺度。新 `ResidualPDPairMPC` 仅接受三参数 plain pair `predict(q,v,u)`，无需 previous_v，不通过伪造零 history 适配旧 lag planner。

两 MPC 组共享经典 PD，第一段从 `9x9` 网格选择 residual `delta_i in [-.125,.125]`，后续 14 段 residual 固定零：

`u0=clip(PD(current q/v,current target)+delta,-.5,.5)`；
`u_h=clip(PD(predicted q/v,current target),-.5,.5)`，h=1..14。

`.125` 是共同最大权限 `.5` 的四分之一及既有最小非零校准幅度，是冻结设计先验，不按新数据调参。每 candidate 独立递推自身 q/v，每次模型预测重新做 public guard；只执行第一请求，观察后重规划，无切换预览。H15、原成本权重、forecast bounds、fallback/tie 保留。成本使用各 stage **完整最终请求**的 effort，change 使用第一最终请求相对上一实际已知请求；不能只给 residual 计成本。

每 seed 顺序 cold9+residual MPC、learned9+residual MPC、PD64/(0,4)、zero，共 **12 fresh trial**。各 100zero+200active、相同 `.04 -> .08`、最终两轴 `.5 Nm`、另六轴零、同安装与停止。W0 的已见 PD trace 不直接变成未见科学参考，也不反复调 PD 增益。

完整优先门保留：cold/learned 所需 trial 全 seed 完整 200 active、实际 effort完整；每 seed joint/两 axis RMSE 严格改善，三个 seed 原 joint 与各 axis 均值各改善至少20%。实际 absolute 与 squared effort 的两轴合计均值各 `<=1.05*cold`。PD 门仅在该学习贡献门通过且所需 trial 完整后评：每 seed joint/axis 不劣于 PD、joint 原均值改善至少5%，两种实际 effort 均值各 `<=1.05*PD`。baseline 为零时不产生百分比优势；effort baseline零，仅candidate也零才不增加。

cold 与 learned 差只解释固定支撑/共享 PD 下的身体模型贡献；共享 PD 的已有能力不能记作学习获得。零停止不等于安全，部分轨迹不排名，不把较少付费停止计为效率收益。独立预测通过不能代替控制门，反之亦然。

W2 上限 **3,600 控制调用 /36,000 子步**。两个 MPC 共 **1,200 decision**，数学预测上限 **1,458,000 pair /2,916,000 scalar**；所有 stage 的 PD/full-request 计算、81 candidate 尝试与拒绝、fallback、已付失败分别计账。模型、gain、gate 全程冻结。自身控制轨迹的 H1/2/5/15 与公共 prediction 分开报告，不能以仅公共脉冲好预测声称自身闭环预测普适改善。

W0+W1+W2 完整新物理上限 **6,000 控制调用 /60,000 子步**。加既有基点后上限 **258,690 /2,586,900**；实际按停止/异常账，不预填完整数。历史在线22,452、离线RLS7,200保持；新RLS实际另加，ridge/规划/静态加载/归档与读写计算分别记录。

## 冻结与输出

具体新入口建议：已选的 `src/developmental_physics/supported_environment.py` 与工程入口 `scripts/validate_supported_pair_engineering.py`；学习/控制的 `supported_pair_development.py`、`residual_pd_pair_mpc.py` 仅是未来候选路径。每 trial 保存 reset 生成的派生 XML，不要求另一个 tracked fixed XML。不改旧资产或旧结果。新的 root/native/fingerprint/reset 语义须显式实现；原 GroundBodyEnv 的 `qpos[:3]` root 假设不能直接复用到固定 root。

必要新 controller 合成检查仅包括：81残差请求/clip、零残差等于公共 PD、candidate 各自闭合与无真实未来输入、完整 full-request成本/首段change、预测/规划/物理失败的实际支付与未知下界。原耦合 RLS/共享更新核心只作来源/API检查，不重复其已过数学。

每阶段保存 source commit/clean bytes、资产身份与原资产差分、版本、seed/reset、安装/公共 guard/PD先验、原始逐子步接触与实际努力、全部 stop/error/blocked、模型前后指纹、更新尝试/提交、预测与控制费用、首次 stdout/stderr 和完整 manifest。模拟接触、真实动力学、root姿态和反力只作离线安装/风险核查，不给模型或控制器。

## 回到完整接触控制的路径

W 只是工程与分层机制阶段。若 W1/W2 全通过，也只登记 `supported_pair_domain` 通过，原自由 root C4 与整个持续目标仍未完成。下一项另冻结**一次**原 GroundBodyEnv supine 的无机械 torso 固定迁移：相同两轴模型、相同 PD残差 controller、相同任务/最终权限/停止/科学门，使用预先保留且未读的新 seed bank和新物理预算。旧失败域不删除，不从成功 supported trace 选最好初态代替原reset。

迁移中需要同时满足独立预测、完整控制与强经典基线门；不只看一段走得好或 RMSE 排名。只有完整真实接触域通过，才讨论该域的 C5 动力学变化、C6 固定/能力门控及 C7 新留出综合验收。支撑域和自由 root 结果不是单一改变的匹配因果对照，不将跨域差归于某个机制。迁移失败就明确保持原依赖关闭，不把 toy、机械支撑或经典 PD 成果当作初期全流程完成。

W0 的任务不可达、W1 的预测失败或W2无增益都是可证伪结论。后续设计依据这些结论另行冻结，持续目标保持active；每个阶段提交推送后继续，但不通过同一安装/数据/预算无限修订到成功。
