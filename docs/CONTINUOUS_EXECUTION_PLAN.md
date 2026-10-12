# CPU 发育式学习：持续执行目标与阶段账本

## 持续目标与当前入口（2026-10-12）

**目标 active：C4 双关节接触控制 → C5 未知动力学适应 → C6 固定成熟/能力门控 → C7 新留出综合验收。** 每次检查、提交、推送后立即推进下一项，不等待再次“继续”。四项完成条件见[持续目标](CPU_VALIDATION_TARGET.md)。当前仅 CPU，允许少量身体辨识；不用任务教师、预训练任务策略、大规模 PPO、GPU 或真机。

当前最早未验收的是 **C4双关节完整接触控制**。上一轮[IV3完整负结果](NEAR_REFERENCE_IDENTIFICATION_RESULTS.md)保持关闭；现在[CF1因果增量协议](CAUSAL_INCREMENTAL_PREDICTION_PROTOCOL.md)与纯代码已准备完成，首次2个必要合成case通过，最终静态审阅完成。先冻结到clean提交并推送，再首次执行唯一开发预测；不在准备通过后宣称科学成功。

CF1只提取已有IV1 action8，与同历史CFcold比较；active0使用真实prefix最后区间，后续递推只用自身预测和已知请求。完整4146记录/135900pair/271800velocity heads，0新物理/fit/RLS。新门仅检验H1速度20%及H2/H5不劣，全部7H报告；旧H10/H150失败保持，不开放300ms规划或控制。准备手算遗漏H20 origin1980已在执行前更正并保存。

累计 **544,345 控制 /2,824,018 子步**；历史 **125,652 scalar RLS更新**保持，已有IV1学习与IV3采集/OLS另列。C4及C5–C7未验收，目标active。首次结果检查、提交、推送后立即继续最早未验收项；通过CF1也须另冻完整控制、强PD、20%/5%/1.05实际努力和新最终留出。

> 2026-10-12：这是持续执行的目标，不是一次性任务。阶段报告、检查、提交和推送完成后，立即推进下一项。

用户概览与四项验收条件见[一页持续目标](CPU_VALIDATION_TARGET.md)。本文件保留详细阶段与费用账本。

## 1. 当前持续目标

**持续目标保持 active。** 用户已授权少量 CPU 在线身体辨识，以及开发过程中正常提交、推送可验证的中间进度。沿用这项授权继续工作，不要求用户每个阶段再说“继续”；不重建目标，也不因一次报告或局部门通过标记完成。

初期目标是完成可复核的低维多关节算法验证：用自身动作与原生感觉建立身体模型，检验它对完整闭环控制、未知动力学适应和能力门控的贡献。公开先验、全部失败、实际交互和计算费用。当前仅用 CPU，不运行大规模 PPO、任务教师、预训练任务策略或真机。

完整翻身、起身、站立、行走以及 G1/真机属于后续长期路线，需要对应资源与安全验收。当前的完成条件见第 4 节；一个肩关节或悬挂手臂的成功不能代替整个初期验证。

**当前卡点是 C4，尚未验收。** [E1 v2](CPU_LOCAL_BODY_RESULTS.md)已经证明指定轨迹下的单肩预测和同 MPC 跟踪改善，但闭环自身预测退化、努力与动能升高仍存在。双关节完整控制、真实接触迁移及后续适应、门控还缺证据。

当前执行入口：

- **历史 EF1B 首次结果：** [EF1B首次保持补偿结果](EQUILIBRIUM_FEEDFORWARD_CONTROL_RESULTS.md)从clean f9f5007完整完成六fresh轨迹，18,000新控制/子步、0停止/异常/fit/RLS。同结构模型贡献joint9.0203%、肩8.8254%、肘9.4825%，actual努力两门通过，但未达原20%门；正式PD门因前置失败不可评。本单候选关闭，不scan保持比例/逆解容差/目标状态/gain/权重/seed。累计505,297控制/2,784,970子步、125,652scalar更新。C4及C5–C7未验收，持续目标active；归档核验提交推送后继续有依据的下一方向。

- **Z0首次完整工程门通过。** [首次结果](FAST_FEEDBACK_ENGINEERING_RESULTS.md)从clean824749b一次seed7600完成1000zero+2000PD、3000控制/3000子步，0异常/停止/fit；两个末200点/.4s窗口的肩/肘四项MAE均≤.01rad。root首新thin contract零failed，独立4个Z0 MAE；记录一致与工程通过仍不证明学习或科学验收。
- [2ms反馈协议](FAST_FEEDBACK_ENGINEERING_PROTOCOL.md)保持物理/PD64/Kd(4,4)/权限/6s任务，反馈/感觉与active研究停止检查频率增多，公开额外经典控制能力。全子步left_arm/feet/other接触零观察；固定支撑反力unknown，不从不同seed的X/Y失败识别频率因果，不追认自由root真实接触C4或解除C5科学依赖。
- **Z1预测通过，Z2完整控制贡献门失败。** [Z1](FAST_FEEDBACK_PAIR_PREDICTION_RESULTS.md)指定独立预测门通过；[Z2](FAST_FEEDBACK_PAIR_CONTROL_RESULTS.md)首次12组全部完整36000控制/子步、0停止异常。joint/肩/肘贡献7.5535%/8.8449%/5.6905%，均不足原20%；实际努力门通过，正式PD门按前置条件不可评。自身长时肩预测退化，不能将独立预测结论延伸到闭环有效域。120新条件RMSE向量及新跟踪/努力核验通过；只证明保存一致。随后[FR0首次接触工程](FREE_ROOT_FAST_FEEDBACK_ENGINEERING_RESULTS.md)完整通过；零学习，下一项另冻本域辨识/预测/匹配控制。不改Z2门补跑，C4及C5–C7仍未验收。

Y0执行前的[首次准备封存](../results/cpu_validation/2026-10-12_damped_suspended_pair_engineering_preparation/manifest.json)保留为历史：
已完成：两项新反馈检查通过，最终protocol pin匹配；runner从反馈检查以来仅pin改变。
15payload、32读/245,367bytes、15写/108,618bytes，末manifest前wall/CPU为.241098/.046875s。
首导航链接检查零失败；没有重复装配、旧测试或物理执行。准备通过不代表工程通过，
Y0后来已从精确干净提交首次执行并失败；本段准备通过不追认工程或科学门，当前goal继续active。

接下来的顺序和验收：

| 顺序 | 要取得的证据 | 阶段验收边界 |
|---|---|---|
| **C4：当前** | 双关节一步/多步预测、完整闭环与可归于身体学习的控制贡献 | 先工程资格，再学习/控制对照，最终回到自由root真实接触域并使用新留出；悬挂机制不能代替接触C4 |
| **C5：C4后** | 未见载荷、延迟等动力学变化下的冻结/适应对照 | 少量更新的恢复交互、预测、控制、实际努力及失败完整报告；事件接口通过不等于科学适应通过 |
| **C6：C5后** | 固定成熟与能力门控的公平对照 | 任务、最终权限和完成标准一致，计入探索/校准及晋退级成本；不能靠永久小动作取得优势 |
| **C7：最后** | 新留出综合验证、强经典基线、组件消融和可复现交付 | 未见seed/条件、全部失败和费用、源码与原件齐全；按第4节判断初期验证完成 |

每个阶段都先冻结人口、权限、停止条件与科学门，先要求完整执行，再评价预测/控制收益；
部分轨迹不排名，不放宽旧门，不把工程通过解释成学习成功。算法效果按数据判断，
不承诺固定日期或预定的正结果。以下关闭路线的说明及后续阶段历史保持原记录。

持续执行不等于无限重复同一失败。U为当前Q phi50/C400/双q-head多步目标候选族的最后一次优化器修订；
若仍未过原K/D全门，公开该配置与预算下的局部负结果，不再同bank追加优化器、步长或特征。
随后依据保存结果作一次有边界路线判断或新物理信息设计，继续最早未验收阶段；C5/C6工程可独立准备，
科学实验仍依赖C4。数值失败、训练拟合不足、开发泛化失败分别解释，不将它们混成算法已被证明无效。

## 2. 执行方式

1. 围绕最早未验收阶段，选一个有依据、预算有限的下一项；先做最小实现和必要新检查。
2. 在读取正式结果前冻结协议、代码、阈值、种子与预算，并提交、推送；开发数据和正式留出分开。
3. 从干净源码首次执行 CPU 实验，保存实际交互、更新、停止与异常，不删除失败或补跑到成功。
4. 核对本次必要证据和信息边界，分开报告记录一致、工程资格与科学结论；不机械重跑已过实验/审计。
5. 更新结果、阶段账本和费用，相关检查后正常提交、推送；同步远端并保留既有工作，不强推。
6. **交付后立即继续下一项**：先说明结论改变了什么，再执行下一步，不停在报告、commit或“请再说继续”。

候选失败后，先公开负结果及成立的结论边界，再依据证据另冻唯一有限修订或新信息设计。
不无限追加同bank拟合、优化器或增益，不修改旧留出门，也不把已见seed再称未见。
有新资源或信息依赖时，继续不依赖它的工作；必要依赖、授权范围或科研选择有实质变化时明确记录。

工作中持续给出简短进度，说明已获得的证据、当前卡点和下一步；用户补充意见作为目标的调整。
只有用户明确暂停时才暂停本目标；完成则必须满足第4节，不以一次交付结束。
需要GPU、真机授权/现场条件或无法获得的资源时记录具体依赖，继续独立CPU工作；不虚构完成、静默安装驱动或绕过安全层。

## 3. 连续阶段与交付

| 顺序 | 阶段 | 必须交付 | 当前状态 |
|---|---|---|---|
| C0 | 单关节局部初期验收 | 探针、冻结/学习模型、独立预测、同 MPC 闭环、PD/零对照、原始数据与失败 | 完成；`cf1c154` |
| C1 | 闭环模型有效域 | 开发轨迹覆盖分析、动作切换残差、位置积分误差、2/5/15 步自由递推；名义/学习/持久性对照 | 开发诊断完成；[结果](MODEL_DOMAIN_RESULTS.md) |
| C2 | 最小模型/探索修订与消融 | 分离校准剂量与折点结构，必要时比较动作历史或直接位移预测；新留出预测与控制及各方法总成本 | 三个修订均未采用；[新最终](LOCAL_FROZEN_VALIDATION_RESULTS.md)同MPC贡献通过29.505%，自身一步与位置有效域仍有缺口 |
| C3 | 调优经典控制强基线 | 有上限的开发增益/积分候选；所有调优交互计账；新留出统一权限比较 | 九组PD选64/0；新最终只改善2.674%，未过5%门，保留失败结论 |
| C4 | 新增关节与低维协调 | 至少两个有可重复响应的关节；单关节与双关节任务、耦合/独立模型对照 | 左肘[迁移](ELBOW_BODY_DEVELOPMENT_RESULTS.md)贡献与PD门失败；首次[双关节](PAIR_BODY_DEVELOPMENT_RESULTS.md)校准/组合PD停止。[短脉冲](PAIR_CALIBRATION_DEVELOPMENT_RESULTS.md)1/9可执行；[双轴PD](PAIR_PD_DEVELOPMENT_RESULTS.md)有限选择64/(0,4)；[A](GUARD_PAIR_DEVELOPMENT_RESULTS.md)学习控制2/4active停止；[B](GUARD_COUPLED_DEVELOPMENT_RESULTS.md)三seed106active位置停止；[C](GUARD_EXPLORATION_DEVELOPMENT_RESULTS.md)18完整/6停止、科学门未过。[D](GUARD_LAG_OFFLINE_DEVELOPMENT_RESULTS.md)长轨迹H15位置局部改善、共同脉冲/短步负效混合；[E](GUARD_LAG_CONTROL_DEVELOPMENT_RESULTS.md)9完整/3学习组104active速度停止、控制门未评价/未过。[F](GUARD_NATIVE_CONTEXT_DIAGNOSTIC_RESULTS.md)不支持追加特征；[G](GUARD_PD_TAIL_CONTROL_DEVELOPMENT_RESULTS.md)8完整/4肘速度停止，只有一条学习轨迹完整，控制子门失败。C4未验收；[H保存诊断](GUARD_PD_TAIL_FORECAST_STOP_DIAGNOSTIC_RESULTS.md)确认学习预测合规但实际超速，[I因果残差](GUARD_PD_TAIL_NATIVE_RESIDUAL_DIAGNOSTIC_RESULTS.md)主门失败；[J六轴IMU残差](GUARD_IMU_RESIDUAL_DEVELOPMENT_RESULTS.md)主门失败；[K完整状态转移](GUARD_NATIVE_TRANSITION_DEVELOPMENT_RESULTS.md)主门失败；[L固定数据增量](GUARD_NATIVE_AUGMENTATION_DEVELOPMENT_RESULTS.md)双门失败；接着有限结构诊断 |
| C5 | 未知动力学变化 | 至少两类变化的冻结/适应对照；恢复交互、预测、控制、努力与失败曲线 | [事件工程](C5_ENGINEERING_RESULTS.md)4完整480/4,800/0更新、独立481,538项零失败；科学适应对照仍待 C4 |
| C6 | 固定成熟与能力门控 | 同最终任务与完成标准；校准成本、权限轨迹、晋退级、失败和风险；不能靠永久小动作取胜 | 待 C5 |
| C7 | 综合验收与可复现交付 | 未见种子/条件、强基线、组件消融、全部失败与成本；说明成立和不成立的机制 | 待各阶段结果 |

C1 的离线多步诊断可以条件于日志中的请求序列，但该序列不能被解释为在线控制器提前知道未来动作。用校准样本重拟合属于离线模型开发，需要记录重放更新/候选计算；它不产生新的物理交互，也不是正式在线学习成功。

C2/C3 的正式矩阵根据 C1 的开发依据另写冻结协议。C4–C6 在实施前各自固定任务、基线、完成条件、停止条件、风险分母与预算；本文件是执行顺序，不代替实验预注册。

## 4. 目标完成条件

本持续目标的交付需要完成低维多关节的身体预测、闭环控制、变化适应和成熟机制对照，并具备以下证据：

- 真实刚体接触；模型只使用原生感觉与当前已知命令，底层保护独立。
- 至少两个关节与双关节局部任务；既有单肩结果单独报告。
- 同初始知识、相同权限/目标/场景下的冻结模型、学习模型和调优经典控制；单步与多步预测同时报告。
- 未见动力学变化中的冻结/适应对照，冷启动、变化适应与技能复用成本分开。
- 固定成熟与能力门控的公平对照，完成标准一致，风险/努力/交互和停滞均保留。
- 开发与正式留出分开；各阶段门在结果前冻结，模型选择不读取正式留出。
- 全部结果可从源码提交、配置、逐 seed 原始轨迹、参数/更新记录与清单复核；相关检查、普通提交与推送完成。

完成实验与证明优势是不同结论。如果强基线、消融或风险指标否定候选，必须公开；持续研究据此推进有依据的修订。不能仅因增加模块或留下文档就把整个目标标记完成，也不能用仿真结论替代真机验收。

## 5. 资源与信息边界

仅 CPU，允许少量 RLS/局部系统辨识；不运行大规模 PPO，不引入步态教师、预训练任务策略或外部任务动作。基线控制器、公开身体与限位、固定模型结构、任务目标和理想传感都属于需要披露的先验。

接触力、动能、真实参数等只作诊断；它们不能暗中进入部署模型。共同上限不代表相同实际努力；零停止不代表安全。原 E1 留出 seed 10/11/12 已使用，后续版本需要新的独立最终评估。

正式物理研发累计基点为174,950控制调用/1,749,500子步；九组肩PD、三个C2开发批次及单肩新最终后为208,850/2,088,500/9,900。左肘PD实际新增7,521/75,210/0，左肘身体模型实际新增5,292/52,920/900，首次双关节实际新增2,919/29,190/2,052，C5事件工程新增480/4,800/0，短脉冲校准新增2,586/25,860/0，双轴PD开发新增4,536/45,360/0，A匹配模型对照新增6,318/63,180/4,800scalar，B复用校准后新增618/6180与离线2400scalar，C探索新增7230/72300/4800在线scalar，D同数据诊断新增0物理/4800离线scalar，E冻结控制新增3312/33120/0更新，G反馈尾控制新增3028/30280/0更新，W0固定支撑域新增300/3000/0更新，X0悬挂域首次新增104/1040/0更新，Y0共享阻尼首次新增203/2030/0更新，Z0独立2ms工程首次新增3000/3000/0更新，Z1微步辨识新增21000/21000/24000在线scalar，Z2首次控制新增36000/36000/0，FR0自由root工程新增3000/3000/0，FR1自由root辨识/预测新增21000/21000/24000在线scalar，FR2首次匹配控制新增36000/36000/0更新；FR3A实际新增21000/21000/24000在线scalar；FR3B实际新增36000/36000/0在线scalar；FR4A实际新增21,000/21,000/24,000在线scalar；FR4B实际新增36,000/36,000/0在线scalar；当前累计 **487,297 控制调用 / 2,766,970 子步 / 118,452 在线scalar及7,200离线重放scalar**，scalar计算合计125652，没有用完整计划替代停止成本。短脉冲的全部失败及付费前缀见[归档清单](../results/cpu_validation/2026-10-11_pair_calibration/manifest.json)。J/K/L分别用2400/26400/39600scalar标签和各3个小型batch ridge solve，不计为RLS或新物理。后续逐批累加。测试、离线重放/模型搜索、规划计算、旧 NumPy/二维/G1 成本分开列报。共同控制评价时域不代表各方法同总成本：学习校准、经典调优与共同预测评价分别披露。

## 6. 开发记录与当前动作

下方保留已执行开发的选择与结果。当前动作以首页看板和最后记录为准，历史文字不能触发重跑。

当前最早未验收的是C4多关节完整控制与预测。[H](GUARD_PD_TAIL_FORECAST_STOP_DIAGNOSTIC_RESULTS.md)确认模型乐观失配，[I](GUARD_PD_TAIL_NATIVE_RESIDUAL_DIAGNOSTIC_RESULTS.md)上一原base残差主门失败：learned seed0/1两轴退化，seed2改善，肩/肘平均3.18%/4.68%；cold全退化。不将此候选接入控制。[J六轴IMU残差](GUARD_IMU_RESIDUAL_DEVELOPMENT_RESULTS.md)首次完成且主门失败：共同prediction肩/肘均值退化3.39%/2.77%，全部seed两轴退化。[K完整状态转移](GUARD_NATIVE_TRANSITION_DEVELOPMENT_RESULTS.md)已从cleanb46c6d3首次完成，所有窗口有限，但H1速度改善不足20%，H15位置未改善，开发门失败。L固定数据增量已完成且双门失败，PD采样先验及费用披露；不进控制，接着有限结构诊断，不再追加PD数据或维度。C5只有事件接口通过，科学适应与C6/C7未验收；旧seed保持已见。

B、C、D、E均已首次执行并保存原失败：[B](GUARD_COUPLED_DEVELOPMENT_RESULTS.md)三seed106active位置停止；[C](GUARD_EXPLORATION_DEVELOPMENT_RESULTS.md)continuation4active速度停止、sparse106active位置停止；[D](GUARD_LAG_OFFLINE_DEVELOPMENT_RESULTS.md)普适预测未通过，原长轨迹H15位置改善与共同脉冲/短步负效混合，唯一读取单位首审失败及50项纯字节补充保留；E冻结控制仍未完整。它们是已完成的开发历史，不再列为待首次执行的矩阵。

既有阶段按以下顺序推进，已完成项保留交付状态：

1. E结果已提交推送cf71bd2。[F固定原生上下文结果](GUARD_NATIVE_CONTEXT_DIAGNOSTIC_RESULTS.md)已从clean734ab7d首次完成并推送cb2c6a9：2112完整active、288固定分组、12events、24quality，0物理/模型预测/更新；32payload原件及首核查50255/24超范围断言/纯契约补充封口。F交付211项零失败，不重跑F或E。
2. [G单项反馈尾结果](GUARD_PD_TAIL_CONTROL_DEVELOPMENT_RESULTS.md)已从clean91dcf6c首次完成，8完整/4速度停止，控制子假设失败；生产/来源/预算与原失败完整保存，不重跑G。[H保存诊断](GUARD_PD_TAIL_FORECAST_STOP_DIAGNOSTIC_RESULTS.md)已从clean a46633c首次完成，原selected/末窗口、输入身份和成本封口。学习组失败主要是一步乐观失配；cold2远期规划许可不解释它。[I固定上一原base残差检验](GUARD_PD_TAIL_NATIVE_RESIDUAL_DIAGNOSTIC_RESULTS.md)已从clean1f239f3首次完成，主门失败且未采用。[J六轴IMU残差](GUARD_IMU_RESIDUAL_DEVELOPMENT_RESULTS.md)从clean9e8a212首次完成且失败，新增离线ridge2400标签/3solve/36系数，0新物理/RLS。[K完整状态转移](GUARD_NATIVE_TRANSITION_DEVELOPMENT_RESULTS.md)从cleanb46c6d3首次完成，3429记录/576组完整，开发门失败，新增离线ridge26400标签/3solve/1914系数。[L固定数据增量](GUARD_NATIVE_AUGMENTATION_DEVELOPMENT_RESULTS.md)从来源修复后clean3bbc34d完成，双门失败，39,600离线标签、0新物理/RLS；原来源失败保留。接着一次有限结构诊断，详见后段；新预测/控制仍需验证。
3. G即使控制子门通过，也不能替D旧独立预测失败或解除C4/C5依赖。依据新完整控制/预测证据，另冻结必要的新预测验收或单个有依据模型修订，再完成同权限闭环与经典基线比较；没有明确依据时继续必要诊断，不无限重试、不只增加探索、不放宽任务或停止条件。每个可验证阶段完成后继续最早未验收项。
4. C4科学门通过后，执行C5未知动力学冻结/适应对照，再执行C6固定成熟/能力门控及C7新留出综合验收。每批检查、提交、推送后立即接着推进，不等待重复“继续”；局部门、报告或commit不结束active目标。

相关资料：[项目路线](DEVELOPMENT_ROADMAP.md)、[当前局部结果](CPU_LOCAL_BODY_RESULTS.md)、[研发进度](PROGRESS.md)、[项目交接](../AGENTS.md)。

### L 固定数据增量开发（已完成，双门失败）

保持 K 原生 x22/phi29、prior、.01 ridge 与闭合递推；每 seed 固定 C sparse400 加已有 G PDselected200，总600。
只学习下一原生状态，不学习 PD 动作、目标或奖励。PD 已有任务能力、增益开发和采样先验须披露；
样本数、分布、经验权重与相对正则同时改变，不能归因为纯覆盖或声称等预算效率、无先验冷启动。
新增39,600 scalar 标签/3 solve/1,914系数，0新增物理/RLS；G900控制/9,000子步已在历史累计，不重复加账。

矩阵固定 K22/L22/D11，在已见 C 公共 prediction100 比较 H1/2/5/15 全窗口。
L 相对 K 的数据增量门和 L 相对 D11 的原 K 规则门分别报告，两门通过才考虑新留出与匹配完整控制。
H1 v 与 H15 q 各 seed 严格改善、每轴均值至少20%；H15 v 及 H2/H5 q/v 各 seed 不劣。
即使开发双门通过，C4科学门、C5依赖与科学采用仍关闭；不追认旧 K/D 失败。

协议、来源、原始字节与新增四分支检查先冻结提交，再从 clean HEAD 首次运行；失败完整保留，不补跑。
完成 L 后继续最早未验收项，不能把一次开发、结果报告或提交当作持续目标完成。

L首次来源运行从clean2dce248在D归档身份比较停止，0恢复/fit/predict/物理；[原失败](GUARD_NATIVE_AUGMENTATION_DEVELOPMENT_RESULTS.md)已推送c733482。
仅修D记录bytes/SHA比较，允许original_path注释；一次新增合成binding检查通过，旧四枝/K数学不重复。
首次12文件/19,147,304字节读取及wall费用保留；修复后从新clean提交/新目录首次进行模型计算，不能追改原失败。

L修复后从clean3bbc34d完成全部3429预测记录/576组，16项有限输出契约零失败；相对K/D两开发门均失败。
相对K H1速度肩/肘6.391%/2.867%，H15位置退化77.159%/79.757%；相对D H1速度6.842%/3.054%，H15位置退化77.484%/80.618%。
肘H1 seed0两基线均退化，H5位置三seed两轴退化，H5/H15速度各seed改善不能代替主门。
新增39,600标签/3solve/1,914系数，0物理/RLS；K/D冻结恢复后重新预测，各方法6204步，基线指纹前后一致。
实际内部wall/CPU8.693235/8.265625秒、外层8.999760秒，首次来源费用仍保留。
不进L控制、不重复本次实验/数学/审计、不继续增数据或维度；接着做一次有限结构诊断，再依据证据冻结单个新方向。
C4最早未验收，C5只有工程，C6/C7未验收；本次报告/commit不结束持续目标。

### M 固定矩阵诊断（已完成，无预测/控制验收）

L两门失败后只进行一次原设计几何诊断，暂不执行位置—速度混合候选或其积分诊断。
K400与L600三seed共六套，先核共享C400的Phi/Delta/IDs/qref精确一致再计算。
固定18次float64薄SVD、36matmul；最低残差投影等价新增无正则估计，66,000原生scalar标签用途、
12,000命令条件投影响应用途以及66,000归档ridge前向输出分别计账，不能称0拟合。
A四基函数只有两个物理动作通道；谱、秩与训练残差都不代替因果、泛化或科学门。
所有seed/22输出保留，ALL与C/G分组保存交叉项，不合计不同输出单位。
无参数/lambda搜索、无新可部署W，无新物理、旧递推或RLS；K/L/D旧门及C4/C5依赖不变。
协议/源码、新合成四case与原件先冻结提交；从clean HEAD首次正式执行，失败不重试，之后公开结果并继续C4。

从clean4d10eac首次正式完成，六套资格通过、18SVD/36matmul全部返回；14项输出契约零失败。
全seed K四关注输出shrink均大于floor，L反之；满秩设计29/Z25/A_perp4不能证明泛化或动作因果。
L条件动作能量比例低，但绝对能量/每行均方均更高；C/G交叉项保留，不作单一覆盖归因。
新增66,000原生标签与12,000命令响应投影估计，66,000归档ridge前向输出分列；0物理/RLS。
内部wall/CPU .318810/.140625秒（序列化前）、外层wall .869572秒；全部330摘要及原件保留。
详见[M结果](GUARD_DESIGN_GEOMETRY_DIAGNOSTIC_RESULTS.md)。接着冻结单个尺度/正则配方及原预测门，
不扫描lambda、不加PD数据、不自动执行旧位置—速度候选；C4/C5科学依赖不解除，持续目标active。

### N 输入尺度修订（已完成，双门失败）

M已完成后直接准备一个可否定候选，不再插入诊断层：原C400的phi29逐列未中心化RMS，
`s_j=sqrt(mean(phi_j²))`、`phi_scaled=phi/s`，固定.01 ridge学习全部22输出，
`W_raw=B/s`回原尺度、原prior及22通道闭合不变。尺度只用训练输入；所有s必须finite且>0，
否则资格失败，不后验添加floor、删列或换配方。近零列放大风险明确披露。
不增加数据/特征、不扫描lambda；K保存W/D snapshot只恢复不重fit。
N/K/D在C公共prediction100的H1/2/5/15全窗口比较，原单位判两门：
H1v/H15q每seed严格改善且轴均值≥20%，H2/5q/v及H15v各seed不劣，H1q描述。
全部22输出、全部seed与失败均保留；新fit26,400scalar/3solve/1,914系数，预测成本分列。
先静态审查、新尺度/失败合成检查及协议源码冻结，再clean首次实际执行；不重跑K/L/M。
开发门通过后才另冻新留出预测及匹配完整控制，当前C4未验收、C5依赖不解除。

N准备首CHECK_01：尺度等价、zero拒绝、near-zero风险三case通过；failure_partial夹具
遗漏Ctrace占位blob，在mock parse实参求值前KeyError，尚无fixture fit/solve，首失败及源码保留。
仅补该blob一行，生产/协议不变；新CHECK_02仅failure_partial通过，前三case未重复。
补充分支触发预置mock solve失败、8800合成标签用途/2matmul返回，partial与费用均保留；
这是合成工程检查，不是实际N科学结果。原失败不能写成首次全部通过。
准备原件已封口并随74725ea推送。正式N从该clean提交首次完成，3429预测记录/576通道组完整有限，
15项输出契约零失败；相对K/D两门均失败。H1肩速度三seed退化，肘改善不足20%；
H15位置平均约12%–13%不足20%，两轴速度三seed退化。H2速度/H5位置局部收益不能代替主门。
新增26,400标签/3solve/1,914系数；N/K各6204转移、D6204pair预测，0新物理/RLS。
内部wall/CPU3.483691/3.031250秒、外层wall4.237827秒。全部原件与首夹具失败保留。
详见[N结果](GUARD_SCALED_NATIVE_TRANSITION_DEVELOPMENT_RESULTS.md)；不进入控制或放宽旧门。

### O方向选择与停止边界（诊断已执行）

O选择时只冻结一次保存预测诊断：在固定共同原点对齐H1与递推路径，分解总误差、真实起点局部误差、
模型内递推输入差及交叉项；已知命令阶段仅作条件描述，不解释为实际施加力矩或因果响应。
只读正式保存的预测结果与来源记录，不恢复W、调用模型、fit或增加物理交互。
协议/代码冻结后首次执行一次；若字段不足则记录不可用，不补跑旧模型。诊断不重裁判N/K/D旧门。
随后只选择一个有明确依据的结构修订，冻结原预测门与预算；开发通过后新留出和匹配完整控制。

持续目标的停止条件是全套C4–C7验收完成、用户明确暂停，或无法继续推进的真实外部阻塞。
一次失败、报告、提交、推送或上下文交接都不是停止条件；检查通过后直接推进下一行动。

O的[保存预测协议](GUARD_SAVED_RECURSION_DIAGNOSTIC_PROTOCOL.md)与最小脚本已准备。
一次静态review后加固D原路径形状，首次合成检查三case通过，保留负交叉项、坐标/请求/历史失配
及terminal-only不可用；未读取实际参数/trace或重跑旧科学结果。
合成检查54条生成源记录、629组标量分解；内部wall/CPU .018624/.031250秒、外层wall .109470秒。
准备读取和原件分别归档；冻结提交后首次一次正式保存诊断，之后接着最早未验收的C4。

O已从clean77bf803首次完成：3,429原预测索引、11,910输出记录/792固定组完整，
50,040 scalar分解、10项有限输出契约零失败。H1三seed两轴保持/释放N相对K退化而开启略改善；
肩持续零轻退化、肘持续零改善，不能只归因为首次开启。H15两轴v递推差能量增加与负交叉抵消
完整保留，0模型调用/fit/物理/RLS，不重裁判旧门。[O结果](GUARD_SAVED_RECURSION_DIAGNOSTIC_RESULTS.md)
与全部原件已交付；内部wall/CPU1.227838/1.046875秒、外层wall1.333494秒。

### P单段已知请求记忆（首次完成，双门失败）

下一项P只做一个可否定结构修订：以K原始phi29为基底追加同trial上一合法两轴known request，
新phi31，C400/.01/prior/22输出闭合不变；不保留N尺度、不扫描lag或正则。
训练与预测均要求连续合法past_request，active0使用prefix99真实已知请求，缺失直接失败，
不补零、不跨trial或改变人口。数学递推只推进已知旧request及旧current_v，不读未来实际力矩。
新fit预计26,400scalar标签/3solve/2,046系数，K/D只恢复不refit；两原预测门完整保持。
准备、冻结提交和首次开发后，未过不进控制，过后新留出及匹配完整控制；持续目标active。

P于2026-10-12完成唯一配方和静态review修订。首次准备静态常量解析因HELPER_PINS中名称key
失败，无模块执行或科学输入；仅修静态检查器名称解析，原失败及费用保留，生产数学未变。
随后首次合成self-check五case全部通过：31输入与记忆推进、缺历史拒绝、零记忆解析等价、
预置solve失败paid/partial保存、非有限failed JSON显式编码。未读取实际参数/trace。
合成设计12,400scalar/标签8,800scalar生成，两个cross各消费8,800合成标签，
两solve尝试一返回一预置失败，682系数；0物理/RLS。内部wall/CPU .129742/.125秒，
外层wall .472524秒。准备原件封存后冻结提交，从clean HEAD首次正式执行一次。
准备归档27payload、54文件读取/906,608字节、0复制失败，wall/CPU .214119/.03125秒；
45个本地Markdown链接零缺失。准确首次检查源码、stdio、两失败夹具和review均已保存。
这只是工程合约通过，P科学门尚未执行，C4/C5科学依赖仍关闭；阶段提交后继续。

P准备已冻结推送8315e61，正式从clean8315e610e69194f236fc8e3ba4381be1bddb4144首次完成。
全部3429记录/576组完整有限，P→K及P→D两门均失败：H1v肩/肘相对K改善2.879%/2.904%，
相对D改善3.350%/3.092%，均不足20%；H15q相对K退化7.141%/6.917%，
相对D退化7.365%/7.419%。H2位置改善，但H2速度及H5/H15位置/速度退化，不能替主门。
新增26,400scalar标签/3solve/2,046系数，0物理/RLS，K/D只恢复且指纹前后一致。
内部wall/CPU3.876407/3.328125秒、外层wall4.668242秒；正式归档10payload、20读取/
41,056,136字节、0复制失败，wall/CPU .142244/.046875秒。当前C4/C5依赖不解除，
不进入P控制、不增加第二lag或重复旧诊断；接着冻结有明确动机的单个结构修订。
首次保存输出契约116,912结构/身份/尺寸检查零失败，6读取/20,531,660字节、3,433解析，
wall/CPU .386008/.390625秒，0模型恢复/指标/门重算；213本地链接零缺失。
契约只证明保存一致，不改变P双门失败；报告和契约附属原件另封存，旧manifest保持不变。

### Q固定局部二阶候选（首次完成，H15q门未过）

唯一下一项是K原phi29追加六个当前变量的全部21二次单项，phi50。
z=(qrel0/.12,qrel1/.12,v0/1,v1/1,startG0/.5,startG1/.5)，尺度来自既有公开
StudyAbort和动作权限，不估训练RMS；零列保留，不删列或补采。C400/.01/prior/
22输出闭合保持，无P记忆/N尺度/参数扫描。局部二阶可直接作用速度预测，
但旧负结果没有识别非线性原因；新增函数类与相对正则先验一起变化，递推风险披露。
预计26,400重复scalar标签/3个50x50 solve/3,300系数、0新物理/RLS；K/D只恢复。
先最小合成检查和静态review、冻结提交，再clean首次开发；原两门不改，未过不进控制。
当前C4/C5科学依赖保持关闭，准备和P提交后立即继续active目标。

Q于2026-10-12准备AST/compile与9helper pins通过，无静态失败；首次合成四case全部通过，
验证21项公开尺度/顺序/零列与train-predict同映射、零追加列解析等价、x22闭合与old-v推进、
新fit50预置solve失败paid/partial保存。旧P失败JSON合同复用，未重跑旧NaNcase或科学数学。
合成设计20,000scalar/标签8,800scalar生成，两cross合计17,600重复标签，
两solve尝试一返回一预置失败、1,100系数；0物理/RLS。内部wall/CPU .109406/.109375秒，
外层wall .431626秒。44本地Markdown链接零缺失；准确首次源码和stdio已保留。
静态review封口与准备归档后冻结提交，从clean HEAD首次开发，不在准备检查处停止。
Q独立静态review无实质阻断；准备归档21payload、42读取/1,217,210字节、0复制失败，
wall/CPU .173603/.03125秒。首次源码/协议、预置失败、stdio和review完整封存。

准备冻结推送20fa032，正式从clean20fa0321c84eb766eeafb9f8d906f554bca60622首次完成。
全部3429记录/576组完整有限；H1v相对K肩/肘改善27.681%/26.273%，相对D28.032%/26.416%，
每seed严格改善且均值超过20%；H2/H5qv及H15v各seed均不劣。两门仅H15q未过：
相对K6.682%/5.973%、相对D6.490%/5.532%，虽各seed改善但不足20%，不进Q控制。
新增26,400重复scalar标签/3solve/3,300系数、0物理/RLS，K/D指纹不变。
内部wall/CPU3.858591/3.375秒、外层wall4.784106秒；正式归档10payload、20读取/
47,826,696字节、0复制失败，wall/CPU .196519/.0625秒。旧门不改，C4/C5依赖保持关闭。
公开结果及检查后接着一次位置—速度一致性结构修订；不扩阶、扫参数或重跑旧诊断。
Q首次保存输出契约15个组级检查零失败，6读取/23,920,355字节、3,433解析，
内wall/CPU .428115/.4375秒、外 .535466秒，0模型恢复/指标/门重算；216本地链接零缺失。
报告和首契约附属原件另封存，原manifest保持不变，不把证据一致当作科学门通过。

### R受控位置—速度一致性（首次完成，长位置门未过）

唯一R配方冻结Q已保存weights50x22，先产生完整Q next22，再仅覆盖q0/1为
oldq+.01*(oldv+nextv)，其它20输出不变，previous_v推进oldcurrent_v。
0新fit/标签估计；Q原全部22标签与两个丢弃位置head计算仍计账，不能声称只训练20输出。
Q/K/D只恢复/重新预测，R/Q/K/D共4572记录/840组，原R→K/D双门保持。
新动机是Q速度门已过而长位置是唯一缺口，但位置反馈可能伤害多步速度，仍验全部seed/时距。
不增加blend、残差、尺度、阶数、数据或搜索；先新约束小check、静态review和冻结，再clean首次执行。
开发通过后仍另需新留出与matched完整控制，科学采用和C4/C5flags不解除；持续目标active。

R静态AST/compile与11helper pins通过，无静态失败；首次新约束四case全部通过。
合成44state scalar生成/22复制、1,100零权重占位，5次梯形覆盖（20加法/10乘法/10覆盖），
2次mock-Q候选与2次R完整递推；0真实Q数学/fit/物理/RLS。内部wall/CPU .057895/.046875秒，
外层wall .577640秒；44本地Markdown链接零缺失。准确首次源码/协议和stdio已保存。
独立静态review封口及准备归档后冻结提交，从clean HEAD首次正式执行，不在小check处停止。
R准备归档15payload、30文件读取/125,646字节、0复制失败，wall/CPU .144717/.015625秒。
准备原件及准确首次源码已封存；远端main与当前HEAD一致，正式数据执行次数仍为0。
接着冻结提交并推送，再一次正式R开发；本准备提交不解除C4/C5依赖或结束持续目标。

R准备冻结推送7d2cbab，正式从clean7d2cbabe5208b3c18eb252a8fd4683e2c4d2951c首次完成。
全部4,572记录/840组完整有限；R→K和R→D各12/14项通过，仅H15q肩/肘幅度门失败。
H1v相对K27.681%/26.273%、相对D28.032%/26.416%；H15q相对K8.854%/2.942%，
相对D8.668%/2.487%，每seed严格改善但均值不足20%。H2/H5qv及H15v各seed均不劣。
相对Q，R长位置肩全seed略好、肘全seed更差，不能称约束解决了递推失配。
0新fit/物理/RLS/MPC；Q/K/D参数指纹不变，原Q学习费用保持。
内部wall/CPU5.095665/4.546875秒、外层wall6.476011秒；正式归档10payload、20读取/
96,489,224字节、0复制失败，wall/CPU .239747/.109375秒。
首次薄输出契约15个组级检查全过，6读/48,253,211字节、4,576解析；内wall/CPU
.963817/.953125秒、外1.198073秒，0模型恢复或指标/门重算，只证明保存一致。
契约附属归档14读/85,946字节、0复制失败，wall/CPU .110190/0秒；原根manifest不改。
公开[R结果](GUARD_KINEMATIC_NATIVE_TRANSITION_DEVELOPMENT_RESULTS.md)后继续C4：
唯一S检验一步训练目标与多步位置要求的失配假设，Q同50列/22输出，只拟合两受控q-head。
原C400合法连续H1/2/5/15校准窗口、有限CPU优化、全部原门和旧bank开发边界保持；
不增加物理，不将R/Q接入控制，不扩阶或搜索配方，C4/C5科学依赖仍关闭。
R报告只读四个科学保存文件一次：493,533字节/4解析，wall/CPU .004683/0秒；
作者文档验证1读/9,511字节、7链接通过；本轮导航221本地链接零缺失。
报告附属首次归档因尚未生成链接记录而中断，已完成report reads复制保留，未重做科学计算。
记录首次2读/3,382字节、计时未返回；随后仅补两个缺失文件，5读/3,065字节、wall/CPU
.020712/0秒，0复制失败。原失败另存，原raw/root manifest及首成功副本保持。

### S有限多步位置目标（首次完成，数值拟合失败）

唯一S保留Q原phi50/公开尺度/prior/22自身闭合，仅重拟合两q-head，共100系数/seed；
其余20head系数冻结但状态继续自身递推，不使用R硬替换。只用C400合法连续校准窗口
H1/2/5/15，各400/399/396/386原点，future q只作terminal label，prediction不进优化。
目标为四时距等权的两轴归一化位置均方误差（尺度.12），加.01*sum((U-UQ)^2)。
这个归一化、以Q为中心的损失先验不同于原ridge，不能称正则效果不变。
每seed800唯一q标签、每完整目标3,162标签用途/1,581窗/8,968转移；实际重复费用另计。
CPU float64单线程Torch autograd与有限L-BFGS-B，无配方搜索；具体接受/失败与预算
先于真实计算写入独立协议。120秒为计算边界检查，披露跨界费用，不宣称抢占式硬上限。
原S→K/D双门、Q描述及全部失败保留；通过才新留出/匹配完整控制，C4/C5依赖仍关闭。
已确认使用预安装torch2.2.2+cpu、scipy1.15.3、numpy1.26.4，未下载或安装新包。
记录包嵌入source commit、上游tag及安装metadata/license文件校验范围；预装wheel下载时间
与wheel checksum不可用，不虚构。依赖身份读取6文件/607,190字节，wall/CPU .222725/.125秒。
S首次三组新合成检查通过：六起点Torch/Q逐步值等价，四步自身闭合两方向梯度及label隔离，
accepted/budget/line-search/initial失败夹具。合成Torch step6、Q对照6、gradient递推72、
autograd1；mock目标12尝试/11返回、11backward、9checkpoint写，fit3返回/2预置失败。
发布300合成位置系数仅为fixture，0真实fit/标签/物理/RLS；不重复旧模型数学case。
内部wall/CPU5.417045/1.578125秒、外5.899110秒，首次准确源码/协议及stdio保存。
独立review曾绑定f89aff版本；封口消息前增加的失败证据转录（未改数学/选择）使首次检查
源码为22097d00bbb884e29b9d0e6cd060b53e0448beb72321685c11e7942762acfe7e。
仅此证据增补另静态收口，不重跑已过case；之后冻结干净提交，首次真实数据执行次数仍0。
S准备封存52payload、104文件读取/714,974字节、0复制失败，wall/CPU .549542/.0625秒；
47本地链接零缺失。独立静态收口与首次源码均绑定22097d版本；协议ce5e8f不变。
准备源显示/编排失败及未知费用在读取账本明确保留，没有科学输入、fit或物理执行。
接着提交推送准备并从clean HEAD首次拟合/评价，S准备交付不结束持续目标。
准备封存后作者仅附属账本文档验证再读2次/21,945字节、wall/CPU .000824/0秒；
原准备manifest仍为封存时52payload快照，生产源码/协议及已过首次检查字节未变。

准备冻结推送fcab231，正式从cleanfcab231a511996de83e28d93ce6749326b38308f首次执行。
三seed各objective1/2初始点有限、objective3首次试探在quadratic21非有限，0callback；
iteration0仅留证据，非预算失败不发布，S全部unavailable。固定4,572记录/840通道组保留，
Q/K/D完整且指纹不变；S→K/D均不可评、未过，不能据此否定多步目标。
新增fit3尝试/0返回/3失败、objective9/6/3、backward6，2,400唯一q标签与26,142重复用途；
训练转移74,922尝试/73,764返回/1,158失败，0新物理/RLS/MPC/基线refit，0发布系数。
内wall/CPU7.659888/6.703125秒、外11.001600秒；正式归档14payload、28读/
79,104,330字节、0复制失败，wall/CPU .253798/.093750秒。
报告科学输入仅读五保存文件一次，17,805,255字节/5解析，wall/CPU .146066/.140625秒；
首派生摘要显示过大被截断，原件/摘要保留，后只简取派生字段，0科学重算。
公开[S结果](GUARD_MULTISTEP_POSITION_TRANSITION_DEVELOPMENT_RESULTS.md)后继续唯一T：
保留S模型、损失与窗口，从Q初始化，固定1e-3系数L2信赖步、Armijo1e-4和最多10回退。
每seed最多30accepted/100objective/120秒边界；非有限trial拒绝并计费，不clip状态或伪梯度，
不续S或扫配方。科学采用/C4/C5仍关闭，提交后继续首次T准备与冻结。
S首次薄契约15组全过：10读/39,568,133字节、4,580解析，4,572记录/840通道组及3初始checkpoint；
wall/CPU .601227/.609375秒，exec_command外1.091306秒，0模型恢复/指标/门重算。
科学失败与固定不可用人口保存一致，不能据此验收C4；封存报告附属材料后提交推送，再继续T。
S导航228本地链接零缺失；报告/契约附属封存18读/130,698字节、0复制失败，
wall/CPU .224235/.015625秒，原raw/root manifest不变，无科学重算。

### T有限信赖步与回退（首次完成，长位置门未过）

S失败已正常提交推送c530457。唯一T保留S全部模型/训练窗口/目标，从冻结Q重新初始化，
新增固定数值优化先验：每轮方向为最后accepted真实gradient的负单位向量，系数L2步距1e-3，
Armijo c=1e-4、回退乘.5、最多10trial；最多30accepted/100总objective/120秒边界。
这些数值不是公共身体安全限位，不能从S失败推为最优或保证控制安全；不扫描参数。
非有限模型/目标/gradient的试探仅拒绝并保留付费partial；shape/来源/IO/内部错误仍fit_failed。
10trial全拒绝为optimizer_stalled、无候选；非预算失败accepted仅证据。预算退出仅允许已有
真实T accepted更新，0更新不把Q iteration0伪称新拟合。每次登记含写盘出口deadline。
复用pinned S kernel/训练映射/恢复与Q rollout，不重跑旧mapping/gradientcase，只检查新优化分支。
正式依赖/source及S失败费用另绑定；S根manifest元数据单读1次/3,373字节，wall/CPU
.000163/0秒，原科学payload未重读。新合成检查、冻结提交和首次正式执行后继续原C4。

T新优化器首次12个合成fixture全部通过；没有调用S/Q旧mapping/gradientcase、真实标签/模型或物理。
合成fit12尝试/5返回/7预置失败、objective42/39/3、backward39、Armijo拒绝16、非有限拒绝1，
7accepted更新及21checkpoint写、19注册返回；发布500合成系数仅fixture，0真实fit/RLS/物理。
内wall/CPU1.674847/1.390625秒、外2.173838秒；准确首次源码52d20a、协议cb1c43与stdio保存。
静态审阅修复了跨界结构异常不得伪装budget和S根manifest无status的资格假设；未读科学payload。
T准备封存103payload、206读/1,502,086字节、0复制失败，wall/CPU1.106094/.093750秒。
之后冻结干净提交、推送并一次真实T；本检查和准备交付不解除C4/C5或结束持续目标。
T导航49本地链接零缺失。首次cached空白检查发现生产与原件尾空行，exit1完整保留；
只删生产py/协议各1个尾空行，原首检查源码及封存bytes不改，归档目录仅豁免此尾空行样式。
2读/55,032字节、wall/CPU .043712/.046875秒，py AST一致且compile通过，0模块执行/旧case重跑。
最终冻结py为46,375bytes/e4cd9e06d078e85ba82614f05b160e69e8b11bd6e66773d795646f5766759464；
协议8,655bytes/79a18f3bc52ded3b650d00f0942d7dfc0d4584727c7c71a4a254860af8a59824。

准备冻结推送585540f，正式从clean585540fe8ba07c1149e61c4aa6e9638679ecabb3首次完成。
三seed各12accepted/100objective，硬objective预算退出，无收敛；300objective/backward有限返回，261Armijo拒绝。
4,572记录/840组完整，Q/K/D指纹不变；原两门各12/14通过，仅H15q幅度未到20%。
相对K肩/肘7.540708%/6.360919%，相对D7.350490%/5.921648%；H1v继承Q，不归因于T。
新增fit3/3/0、2,400唯一q标签、948,600重复用途、2,690,400训练转移、300位置系数，0新物理/RLS/MPC。
内wall/CPU26.1016302/24.953125秒、外29.9272868秒；归档49payload、98读/101,055,954bytes、0复制失败。
首15组薄契约全过，45读/50,530,507bytes/4,615解析、wall/CPU .7812956/.765625秒；0模型/指标/门重算。
详见[T结果](GUARD_TRUST_POSITION_TRANSITION_DEVELOPMENT_RESULTS.md)。报告输入只读五保存文件一次，19,534,531bytes/5解析。
提交推送后立即准备U：保持科学核心/预算，从Q重启，5正曲率pair有限L-BFGS方向，范数只上限1e-3。
U是本候选族最后优化器修订；仍未过则转有限路线判断，不追加同bank搜索。C4/C5科学依赖仍关闭，持续目标active。
T本轮导航234本地链接零缺失；报告/契约附属封存20读/99,240bytes、0复制失败，wall/CPU .2483099/0秒。
原raw/root manifest保持不变，附属一致不改变两开发门失败。

### U 有界有限记忆方向（首次完成，结束本族优化器修订）

唯一U保留T科学核心，从Q重启；history最多5个相邻registered accepted正曲率pair，初H=I，
有history时gamma=sTy/yTy；two-loop得到p=-Hg，L2只cap≤1e-3，不放大小方向。
trial=U+t*p，t从1开始；Armijo用最终cap后g·p，.5回退及10trial/30accepted/100objective/120秒边界不变。
方向/gamma/rho非有限或非下降时仅一次清history、负真实gradient同cap fallback；拒绝/未注册trial不加pair。
不改状态或gradient、不扫参数、不续T。U为本候选族最后优化器修订；失败后转有限路线判断。
协议与方向/登记/预算差异静态审阅无实质阻断，AST/compile/pins/options/LF/link通过。
最终py53,997bytes/7c2c2ea6cbe421edca73bd0e53adc1ad2f373390c694e8c7950d5b1b32f1ef95；
协议7,744bytes/222f9f65e09c9b71f9bfdae12c39f95bce8472e3652e85bb107b9ed8156669ed。
首9组仅新增几何fixture全过：8direction尝试/7返回/1预置失败，6正曲率加记忆/2拒绝/1逐出，
3非有限或非下降方向fallback均返回；0真实fit/objective/标签/物理/RLS，不重跑T12工程case或旧模型数学。
内wall/CPU1.6784172/1.5625秒、外2.1937794秒。准确首次源码、协议及stdio保存。
静态读取stdout、文件长度和实际IO费用分别标明，未知不补测；T metadata绑定源自既有report reads及一次rawmanifest身份读。
接着封存准备、正常提交推送，从clean HEAD一次正式U。准备交付不解除C4/C5依赖或结束active目标。
U准备归档15payload、30读/506,652bytes、0复制失败，wall/CPU .1331129/.015625秒；
导航51本地链接零缺失，不重跑科学计算。冻结推送后立即正式U，持续目标active。
首git add因新U目录尚无results白名单而exit1，已暂存源码/文档保留；仅补两精确目录例外，
原失败另存准备附属文件，不重跑已过夹具、科学计算或原封存。

U准备冻结推送7358ff9，正式从clean7358ff9f583d9a20460e94c914cd8ea172c9780a首次完成。
三seed各30accepted、objective46/39/39，最大accepted预算退出、未收敛；124objective/backward有限、31Armijo拒绝。
训练损失约6.45–6.55e-5降至4.76–4.88e-5，H15训练误差明显下降；开发H15位置却仅改善约2%–5%，
相对K肩/肘2.589331%/4.844233%，相对D2.389922%/4.397552%。两门各12/14通过，其它时距各seed不劣。
4,572记录/840组完整，Q/K/D指纹不变；不进控制，按冻结分支结束本候选族优化器修订，不再同bank加步长/特征。
新增fit3/3/0、2,400唯一q标签、392,088重复用途、1,112,032训练转移、300位置系数，0新物理/RLS/MPC。
内wall/CPU15.9039526/14.765625秒、外19.9362021秒；归档103payload、206读/107,815,614bytes、0复制失败。
首15组薄契约全过，99读/53,909,602bytes/4,669解析、wall/CPU .8565182/.859375秒，0模型/指标/门重算。
报告只读五保存文件一次22,398,076bytes/5解析；详见[U结果](GUARD_BOUNDED_LBFGS_POSITION_TRANSITION_DEVELOPMENT_RESULTS.md)。
下一项只作有边界信息诊断或新采样设计，不能从优化失败直接认定缺特征/接触因果。C4/C5科学依赖仍关闭，持续目标active。
U导航236本地链接零缺失；报告/契约附属封存16读/107,972bytes、0复制失败，wall/CPU .3156414/.015625秒。
原raw/root manifest不变。检查与推送后继续C4，阶段交付不作为结束。

### V 非受控通道闭合敏感性（首次完成，干预无收益）

U校准训练收益未转为开发长位置门；唯一V只问冻结Q/U是否对其余18通道的未来尾反馈敏感。
保留受控(0,1,8,9)的q/v预测和预测previous_v历史，每步先完成有限full22，再在非terminal步
把(2..7,10..15,16..21)替换为同trial实际端点；末18不覆盖或评分，不把它们的零误差算成果。
实际native端点来自U保存H1记录，缺标签不可用、不回退另读C。Q/U旧自身闭合记录只转录。
全seed0/1/2、H1/2/5/15、origins0..100-H，四通道4,572固定记录；两oracle新增最多12,408full22转移、
10,122非terminal18覆盖/182,196未来native scalar标签用途，0新fit/物理/RLS。H1受控与保存值应精确一致。
每source单报描述性反馈规则：H15q各seed严格改善且各轴mean相对≥20%；H2/H5qv和H15v各seed不劣。
这不是新科学采用门，不调用K/D旧门、不选最佳模型或自动部署。future18可能含受控运动信息，
混合状态也可能不物理；任何改善只定位这项oracle反馈路径的计算敏感性，不能识别缺传感或支撑因果。
V后不追加通道oracle组合；仍无清晰依据时，进入一次有边界新物理/支撑域设计。持续目标保持active。
U元数据身份从既有report reads复用，rawmanifest两次必要身份/字段读取分别明确；公共guard从U已有
baseline_restorations.D11[].public_guard转录，不恢复D模型或添加C/D原件。正式V仍须绑定这些来源。
先最小新clamp/history/缺label检查与静态审阅、冻结提交推送，再一次正式V，不在准备或报告处停下。

V首检查源码42,154bytes/15493565c44c1f44eb1df18a0fa4cda95147df602f62e58f2bfe03af399fcceb；
协议7,764bytes/2e002e051677774bceb52c3b5c78a70559370027a9d1e4804b3be170fa5bccaa。
首次六项新层夹具全部通过；合成full22前向7尝试/6返回、18头丢弃计算108项，
label4尝试/2返回、2次非terminal覆盖/36scalar用途、3个预置失败均保留。
0真实模型/标签/fit/物理/RLS，不重跑旧映射或数学检查。内部wall/CPU .0028713/0秒，
外 .3166057秒；源码/协议首快照49,918bytes。准备归档18payload、36读/152,034bytes，
0复制失败、wall/CPU .1665942/.03125秒；精确首源码、stdio、绑定ledger及静态审阅保留。
root首次显示误找不存在的self_check.json，只有路径读取失败，随后从run.json读取case，
没有补跑夹具或科学实验；显示读取的准确字节/CPU未知，不补测。准备交付后继续冻结正式V。
首cached空白检查发现六项尾空行，随后stat掩盖shell退出码；全部发现保留。
仅删除生产py/协议各一个尾空行，AST等价与compile-only通过，不执行模块或重跑六夹具。
两读49,918bytes、wall/CPU .0354609/.03125秒；首检查原件和准备manifest字节保持。
正式冻结py42,153bytes/0915fdd404176ef62206d65c6126e7fb7de3976ea61caeb55415faed187b4335；
协议7,763bytes/67fd0bbcaab93208a2f994a0b71deca1c5d6bdc77dcf2481e43f6db84d1c995d。
导航51本地链接零缺失；导航及空白修复receipt作为准备附属保存，原manifest不追写。

V从clean7e1e5dd0cbaad322cdb9169cba07d10818649cfd首次完成，exit0无重试。
4,572记录/192组完整、600H1逐记录精确；Q/U前后指纹不变，各12描述checks均失败。
H2/H5及H15controlled q/v全seed略退化；H15q三seed均值相对Q肩/肘−1.119960%/−.400178%，
U肩/肘−1.243129%/−.569639%。不把负结果识别为缺传感/支撑因果，不调用旧K/D门。
新增12,408full22前向/0失败、10,122非末步覆盖、182,196未来scalar用途、9,144受控误差/96新组。
0fit/物理/RLS/MPC/旧自身前向误差metric重算；原物理累计不变。
内部wall/CPU4.2947398/3.46875秒，外9.4376252秒；归档10payload、20读/13,243,530bytes、0复制失败。
报告仅读五保存文件一次186,859bytes/5解析，内wall/CPU .0108797/0秒。
首8薄契约全过，6读/6,623,818bytes、4,576JSON/58,765,151解压bytes，wall/CPU1.3901324/1.375秒。
root显示误找contract.json，仅路径失败、未重跑契约；派生显示实际IO未知不补测。
详见[V结果](GUARD_ORACLE_TAIL_DIAGNOSTIC_RESULTS.md)。关闭oracle路线与同bank优化，接着有边界新支撑域
双关节机制设计；区分机械支撑、身体辨识与控制贡献，新域不能追认旧C4，最终仍须完整接触控制。
持续目标active，报告检查提交推送后立即继续，不以本诊断或准备交付结束。
V结果导航239本地链接零缺失；附属stage20读/491,694bytes、wall/CPU .1369639/0秒，
seal15读/252,555bytes、wall/CPU .0201421/.015625秒。原raw/rootmanifest不改，
附属报告、首契约及静态读取账独立封存，0科学重算。随后正常提交推送并继续新支撑域设计。

### W0 固定躯干安装与任务资格（首次完成，资格失败）

V负结果已正常推送05c0f78，立即进入[独立新支撑域设计](SUPPORTED_PAIR_DOMAIN_DESIGN.md)。
只删除rootfreejoint，把torso固定为原supine几何reset安装位姿；原资产/八轴/地面/材料和0.5Nm权限保持。
支撑消除6root自由度并承担反力，是公开的额外机械能力，不是零支撑或原C4修复。
新工程seed7300、100zero前缀+200PD64/(0,4)共同任务，原.04→.08、原研究停止及底层保护；
完整/原生有限、左臂真实floor接触、两段末20各轴MAE≤.01作为预先冻结的严格资格。
原正向任务可能压入地面，需先实测可达性；首次最多300calls/3,000substeps，0RLS/MPC/模型预测。
失败保留actual费用，本安装不拟合，也不改高度/方向/摩擦或权限直到通过。
学习W1与控制W2只是有条件后续设计，须资格通过后另冻结clean提交；支撑域成功仍不能追认旧C4。
首次执行前仅新模块/runner/协议实现与必要新装配检查准备，没有新物理，持续目标active。

W0独立静态审阅修复停止状态、先保存返回端点、编译装配对照与forward费用语义；
首准备在D:/Python3.10 import mujoco失败，0构造/reset/fixture/物理，失败原件保存16payload。
已找到既有external/cpu_physics_env（numpy2.2.6/mujoco3.15.0），0安装；仅纠正协议两CLI及runner协议pin，
AST除pin外完全一致，2读/41,083bytes、wall/CPU .0282695/.03125秒，没有改数学或重跑已过case。
恢复后在新attempt02目录首次实际运行唯一装配fixture，0mj_step；原/新各compile1/resetforward2，
八轴mapping与公共参数差异空、原初始几何position/matrix最大差均0。实际拓扑15q/14v/9j→8q/8v/8j，
torso weld1→0，6rootDOF/7qpos移除及有效静态碰撞集合变化明确披露。
内部wall/CPU .3020494/.171875秒，外 .6089705秒；恢复准备18payload/36读/212,466bytes，0复制失败。
首次依赖失败、恢复检查与各自源码/stdio分开保留，原准备manifest不追写。
最终env11,642bytes/c10c72659fe5234febcaed78f04312f1913e494ce2533274b52baccf7c970cb0；
runner24,683bytes/5c75e5db6f8721180bbbb17158f29ed736b0e10554672e585867f433b3766825；
协议16,438bytes/e03f158d274c510fc1fca222e5a2a75e4afc3d0264ee6e227904950f6c4423a7。
接着正常冻结推送，从clean HEAD一次W0物理资格；准备通过不代表目标可达或C4通过，阶段交付不结束目标。

[W0首次结果](SUPPORTED_PAIR_ENGINEERING_RESULTS.md)已从clean54cf4c2253f211ee71cb093aa664681fede69592完成：
seed7300全部100prefix+200active、300返回/3,000连续有限子步，0控制异常，stop/failure为空。
固定prefix80..99左前臂/floor正法向力接触满足，但active80..99肩/肘MAE为
.014550680096836115/.013884623424544693rad，active180..199为.03919046106253779/.006530098506649712rad。
两窗各20端点可用，四项只有第二段肘≤.01，完整工程资格失败。本安装W1/W2关闭，
不移动安装、改变seed/方向/摩擦/权限/PD/目标或放宽门补跑；本结果不识别接触因果或证明所有控制不可达。
固定机械支撑与公开PD先验须披露，不追认原free-root C4，C5科学依赖保持关闭。

W0正式新增300控制/3,000子步/0fit、RLS、MPC或teacher，累计252,990/2,529,900；
online22,452/offline7,200scalar更新计算保持。实际Σ|τ|dt/Στ²dt为
3.947884319255555Nm·s/1.9711742072439733Nm²·s，覆盖3,000子步；正式reset2forward与3,000端点forward分列。
正式内部wall/CPU1.378252899972722/.984375秒，外2.536983600119129秒；
[根归档](../results/cpu_validation/2026-10-12_supported_pair_engineering/manifest.json)10payload、20读取/2,359,776bytes、0复制失败。
报告只读取一次保存派生摘要，不重读raw、重算MAE/旧科学门或调用模型/物理；派生保存5读取/99,939bytes费用另列。

下一唯一X0直立悬挂域设计，明确固定支撑的额外机械能力与可能非接触的域边界；
X0须先过工程资格，后续辨识与匹配控制协议在X0数据读取前冻结，防止按揭晓结果选配方。
新域不能解除C4，最终仍须完整接触控制。持续目标active，阶段报告、检查、提交、推送后立即继续。

### X0 悬挂域准备已通过，首次工程资格待执行

新env7076bytes/f5154b7e059ed9939ed130d9a5c9eda2af455b9f660a4e843c72b996a44d81f8；runner24490/14f8d36c19b683dad9e96d5ed3379f55e5ee681670d083603dbfed065ec8db08；协议10498/1fe9129300663a3b51199cf21f2813279a35f3dcbcd3740dafd4e8085c42d695。
静态审阅落实reset-attempt锁、height前/后XML保存及异常unknown费用；不改冻结W0保护core。
首次唯一新装配通过：共享/新域/原upright参照/installedXML共4编译，reset2+静态参照3共5forward，0积分，几何position/matrix差0。内wall/CPU .209933/.109375秒，外 .434217秒。
新PD残差controller在数据前固定；首4checks有1个测试严格浮点等号失败，改仅该断言容差后该case通过。新增PD/candidate计账后，必要5cases全部通过，异常PD计算也留账；没有旧RLS测试或物理。
[准备归档](../results/cpu_validation/2026-10-12_suspended_pair_engineering_preparation/manifest.json)29payload、58读/358108bytes、30写/186146bytes，wall/CPU .394440/.03125秒，0重跑。装配报告2读/18571bytes，0科学重算。
X0只engineer300/3000、0fit；X1/X2仅事前协议/controller固定，生产runner仍独立准备。工程资格先通过才学习；悬挂非接触证据不能解除旧C4/C5。累计物理仍252990/2529900、online22452/offline7200。现正常冻结提交推送，从clean首次执行，随后报告推送并立即继续。

### X0 首次工程肩速度停止，完整门失败，X1/X2关闭

[X0首次结果](SUSPENDED_PAIR_ENGINEERING_RESULTS.md)从clean `6319fb6fe4a847f9c5178759a057cefd4b0e82ff`
一次执行，seed7400、100prefix完整+4/200active，104控制调用全部返回/1,040已确认积分子步。
`X0_seed7400:103`第4个active完整10子步先保留计费，肩速度1.0957066489965022rad/s触发原1rad/s StudyAbort；
环境terminated=false/reason=null、0控制异常/failure=null。wrapper exit0只是程序保存停止结果，不能称资格通过。
active80..99及180..199的observed_count均0、availablefalse/MAEnull；不partial排名或额外执行到通过。
固定mount3000子步门为false因完整人口未形成，不能从该字段识别安装漂移；参数前后指纹相同。

所有保存子步及prefix末20区间的left_arm/feet/other floor pair及正法向力事件均0。
真实机械固定支撑存在、反力unknown；不宣称接触身体学习、站立或旧自由root成功。
完整工程资格失败，X1/X2关闭，原X协议及公共PD残差controller不按揭晓结果修改。
全部scientific/contact/adoption及C5科学依赖flagsfalse，C4/C5科学依赖保持关闭。

正式新增104/1,040/0fit、RLS、model-forward、MPC或teacher，PD4次；当前累计
253,094控制/2,530,940子步，online22,452/offline7,200不变。
实际all8Σ|τ|dt/Στ²dt为.07438647108079902Nm·s/.03637436632447757Nm²·s；
prefix1,000与active40子步均saved/valid，unavailable effort0，不能用少交互与低总努力声称方法优势。
正式2模型编译/1reset/2resetforward，内部wall/CPU .8093905/.359375s、外1.1996382s。
[根归档](../results/cpu_validation/2026-10-12_suspended_pair_engineering/manifest.json)19payload、
38读/743,602bytes、19写/371,801bytes，wall/CPU .269599/.046875s，不含末manifest写盘；无自动重试。
首报告汇总5读/27,746bytes、5JSON解析、wall .0007403s，0科学重算；文档只一次读取其派生摘要，
不重读raw/检查器或重算数学。root已执行首thin contract零失败，仅证明保存契约一致，工程门仍失败。

负结果只否定当前PD64/(Kd0,4)与该安装在原完整任务/速度门下的工程资格，不能证明所有控制不可达
或识别阻尼/支撑/接触/模型误差因果。下一独立Y候选只公共肩Kd0→已有肘Kd4，
安装/目标/权限/原阈值和保护保持、不scan；增加经典速度反馈是控制先验，不是身体学习。
须独立科学静态判断、另冻结精确任务/seed/源码/有限预算后首次执行，不承诺通过，不称X0成功补跑。
持续目标active，报告检查提交推送后立即继续；最终仍须自由root真实接触控制、C5适应、C6门控和C7新留出。

### Y0 首次肘速度停止，完整工程资格失败，Y1/Y2关闭

[Y0首次结果](DAMPED_SUSPENDED_PAIR_ENGINEERING_RESULTS.md)从clean `1ef7bbe3df016b01b47b0bea0ccc27821c0d7091`
一次执行seed7500、公共PD64/Kd(4,4)，100zero prefix完整+103/200active，203控制全部返回/2,030子步。
`Y0_seed7500:202`第103active完整10子步已保存计费，肘速度1.1258089506362488rad/s触发原1rad/s StudyAbort；
环境terminatedfalse/reasonnull、0控制异常/failurenull，wrapper exit0不证明工程通过。
第一active80..99虽observed20，full trial失败使availablefalse/MAEnull；第二180..199为observed0。
无部分MAE重算或排名，完整工程门失败，Y1/Y2关闭、不scan增益或同安装拟合到通过。

全部保存子步/前缀末20的left_arm/feet/other floor pair及正法向力事件均零观察。
机械固定支撑仍提供安装能力、反力unknown；新增经典速度反馈不是身体学习，C4/contact/C5/adoptionflags均false。
固定mount3000门为false因人口未完成，不单据此推断漂移；参数前后指纹相同。
X/Y不同工程seed，停止步数不可作匹配因果比较；旧X/W0/V关闭分支及原Y配方保持。

正式新增203控制/2,030子步，累计253,297/2,532,970，online22,452/offline7,200保持。
0model-forward/fit/恢复/RLS/MPC/teacher，PD103次；actual all8Σ|τ|dt/Στ²dt为
1.949838328533223Nm·s/.9441707527036306Nm²·s，prefix1,000及active1,030子步全部努力有限。
两模型编译/一次reset/两resetforward，内部wall/CPU1.0698817/.609375s、外1.6939075s。
[根归档](../results/cpu_validation/2026-10-12_damped_suspended_pair_engineering/manifest.json)19payload、
38读/1,220,036bytes、19写/610,018bytes，wall/CPU .2566124/.03125s（末manifest前），无自动重试。
首报告汇总5读/27,839bytes、5JSON解析、wall .0007565s，0科学重算；文档仅一次派生摘要读取，
不重读raw/调用检查器/重算旧科学；root新thin contract零failed、0MAE重算只支持证据一致，工程门仍失败。

下一方向仅控制时间尺度与底层保护有限审阅，先区分已知实现与证据边界，未承诺新实验或周期/保护修改。
本负结果不识别控制周期、guard或其他动力学原因；不能放宽原研究门、扫描增益或用部分完成声称优势。
后续若有独立方案须有依据另冻结，不追认旧C4；持续目标active，报告检查、正常提交推送后继续。
科学后序仍为完整自由root真实接触C4→C5变化适应→C6成熟/门控→C7新留出综合验收。


### Z0 首次2ms反馈完整工程通过，继续独立学习协议

[Z0首次结果](FAST_FEEDBACK_ENGINEERING_RESULTS.md)从clean `824749bbe8610e553be3d06ca6c9306c853153ed`
一次执行seed7600，1,000zero prefix+2,000PD active全部完成，3,000attempts/3,000returns/0exceptions，
3,000已确认且保存子步；control/physics均2ms、每调用1子步，完整任务仍6s。
PD64/Kd(4,4)、每轴.5Nm、目标.04→.08rad及原保护保持；active研究停止检查cadence改2ms，
原.12rad/1rad/s阈值不变。反馈/感觉/停止取样增加明确披露，不把不同seed的X/Y失败作频率因果对照。

全子步原生/实际努力有限，固定mount覆盖完整人口；环境停止、StudyAbort及failure均null。
active800..999与1800..1999均observed200、availabletrue，每窗末.4s；肩/肘MAE分别为
.0006295311018428831/.00025252531693680436和.0012676433238115938/.0004689585769959476rad。
四项均≤.01，事前完整工程门通过；root首独立thin contract零failed、独立4个新Z0 MAE，
只支持本次工程/保存契约，不证明学习、方法优势或风险下降。
全保存子步与prefix末200窗口的left_arm/feet/other floor及正法向力事件零观察。
机械固定支撑反力unknown，全部scientific/adoption/contact/C5依赖flags仍false，不追认自由root真实接触C4。

正式新增3,000控制/3,000子步，累计256,297/2,535,970，online22,452/offline7,200保持。
PD2,000次，body-model forward/fit/恢复/RLS/MPC/teacher全0。
实际all8Σ|τ|dt/Στ²dt为.380273295959645Nm·s/.04576971762158434Nm²·s，
prefix1,000与active2,000努力valid、unavailable0，实际actuator与applied command一致。
内部wall/CPU2.0159694999456406/1.4375s、外3.501302600139752s；source9读101,732bytes、
Git11查询返回101,773bytes，parameter及explicit physical fingerprint各2尝试/2返回，执行前后各自相同。
内部时间不含启动/import/最终压缩与写盘；未确认核心异常尝试、未保存端点及努力仍unknown/下界。

[根归档](../results/cpu_validation/2026-10-12_fast_feedback_engineering/manifest.json)20payload、
40读/2,240,592bytes、20写/1,120,296bytes，wall/CPU .41693429998122156/0s（末manifest前），无自动重试。
首次stdio、精确source、两XML、全部子步和978,185bytes trace保留。
首次报告汇总5读31,855bytes/5JSON、wall .0012329998426139355s、0科学重算；
文档只一次派生摘要读取，不重读raw/调用检查器、模型或物理，不重算MAE/旧科学。

下一项独立冻结2ms学习协议，保留300ms预测时距设计，重新规定动作、标签/更新及预测/控制计算预算；
300ms对应150个2ms基础子步，不自动继承旧20ms snapshots、H15或更新预算。
cold/learned/强经典组共享频率/感觉/目标/最终权限/保护和完整努力分母，未来真实力矩不能进入预测输入。
旧X/Y/W0/V分支保持关闭，接着少量辨识/预测与匹配完整控制；未来仍须自由root真实接触C4、
C5未知动力学适应、C6成熟/能力门控及C7新留出综合验收。
持续目标active，阶段检查、正常提交推送后立即继续，本工程交付不结束整个目标。


### Z1/Z2事前实现与首次新检查已封存

[学习协议](FAST_FEEDBACK_LEARNING_PROTOCOL.md)与微步模型/controller/入口在任何Z1数据前冻结。
7文件外部原件保持；生产仅CRLF→LF，全部AST等价，模型与协议原bytes不变。
首7新checks全部通过，pytest .72s、wrapper wall1.1280911s；真实装配/积分及正式RLS更新0，
新模型构造与fake forwards见测试原件，不称零。仅必要新检查，旧suite/旧实验不重复。
[准备manifest](../results/cpu_validation/2026-10-12_fast_feedback_pair_prediction_preparation/manifest.json)
41payload，83读712495bytes、42写365983bytes含manifest，wall/CPU .4937801/.09375s。
设计、独立adapter/源码review、publication身份、首次stdout/stderr与执行helpers齐全；准备不证明科学通过。

首次Z1三个seed7701/7702/7703，上限21000控制/子步、12000vector/24000scalar更新；
RLS内部preupdate与124680pair独立评分另计。全部完整且原20/40/100/300ms预测门通过才Z2。
Z2 controller在Z1前冻结：MPC每20ms、PD每2ms；literal-zero fallback与delta-zero PD明确区分。
任何Z1失败先封存并关闭Z2，完整科学失败仅做保存预测/标签有限诊断，不scan或补跑到通过。
当前正式累计256297/2535970、online22452/offline7200未变；最早未过仍完整接触C4。
持续目标active，正常提交推送后立即首次Z1，不以阶段报告停止。


### Z1首次三seed完整身体辨识与独立预测通过

[首次结果](FAST_FEEDBACK_PAIR_PREDICTION_RESULTS.md)从clean7d323dcc4b8c303c8d76430763a09b36dbb8130a首次执行，
三个seed各1000zero+4000calibration及fresh1000zero+1000prediction全部完成。
21000attempts/returns/confirmedsubsteps，0异常/stop/failure；12000vector/24000scalar在线原子更新，
124680pair/249360scalar独立递推另计，RLS preupdate12000pair另计。H10v与H150q严格改善及均值20%门、
H20/H50qv与H150v不劣门全部通过；原生H1/H10q仅报告，无新增veto。
内wall/CPU50.2563824002/48.859375s，外75.1023936002s；0MPC/teacher/batchfit/GPU。
首次必要新saved metrics核验60RMSE向量/2886originrecords全部通过，2读5494391bytes，
解压19415072bytes，wall/CPU .5657869/.5s，0模型/fit/物理，旧科学未重算。
首薄契约只读本次4个JSON，829项保存一致性检查零失败，不重算科学指标；报告/准备补充记录已封存。

[根归档](../results/cpu_validation/2026-10-12_fast_feedback_pair_prediction/manifest.json)
40payload、80读66289600bytes、41写33154999bytes含manifest，wall/CPU .7025529/.140625s。
累积物理277297控制/2556970子步；在线scalar46452、离线7200不变，总scalar更新53652。
此前准备归档derive_sources原件含1处行尾空格，首次cached diffcheck报出后命令仍commit；
随后仅新增该归档文件whitespace属性，原bytes未修改，diffcheck通过并正常补充推送7d323dc，正式源干净。

固定机械支撑、公开身体、理想感觉、高频PD及新增初始化/相关标签预算全部披露。
悬挂机制开发预测通过不能追认旧自由root接触C4、控制收益/实际努力改善或C5科学依赖。
接着执行事前冻结Z2 cold/learned MPC/PD/zero完整同预算控制；不改已冻结controller与门。
阶段报告检查提交推送后立即继续，持续目标active。

### FR0自由root接触工程：首次必要新检查与准备封存

[FR0协议](FREE_ROOT_FAST_FEEDBACK_ENGINEERING_PROTOCOL.md)在首次物理前固定：原自由root/仰卧资产，
seed7800、1000zero+两目标各1000active、PD64/Kd(4,4)、2ms反馈、.5Nm，原保护和研究停止不放宽。
三个阶段各至少一个left_arm-floor正法向力端点；完整两末200点窗四MAE≤.01rad才工程资格通过。
生产代码与外部候选AST等价，runner仅绑定最终协议pin；六项新增纯检查首次通过，pytest .23s，
wrapper .6356235s，无真实积分/正式学习；未重复旧suite或旧实验。
[准备封存](../results/cpu_validation/2026-10-12_free_root_fast_feedback_engineering_preparation/manifest.json)
40payload，81读499633bytes、含manifest41写259400bytes，wall/CPU .4065866/.09375s。
保留候选原件、独立静态review、生产身份、首次stdio、执行/归档/新指标核验helpers和事前失败分支规则。
准备不代表工程或科学通过。正常提交推送后从clean源码首次运行一次，不改任务/seed补跑。
完整工程通过才另冻本域辨识/独立预测/匹配控制；失败按新保存证据有限说明，再选择一个有依据新设计。
当前累计313297控制/2592970子步不变，online46452/offline7200scalar不变；C4及C5–C7未验收。
持续目标active，提交推送后立即首次FR0，不停在准备交付。


### Z2首次完整匹配控制：原贡献门失败

[首次结果](FAST_FEEDBACK_PAIR_CONTROL_RESULTS.md)从clean1aaccc1fdfcfa0f7722494e93f82e670b5f3d9c9一次执行。
三个seed各cold/learned MPC/PD/zero四组，共12组完整；36000控制/子步，0异常/停止/failure/新增更新。
joint/肩/肘三seed原RMSE均值改善7.5534654%/8.8448927%/5.6905041%，均低于原20%门；
每seed各轴严格改善及实际努力上限通过，仍不足以通过model contribution，正式PD门不可评。
自身条件H50/H150肩q/v三seed两轨迹均退化，不把Z1独立轨迹预测通过当作闭环有效域通过。
1200MPC决策、14571279pair规划（含243返回候选拒绝、3 literal-zero fallback）、526560pair自身条件预测。
内wall/CPU1500.0350099/1484.75s，外1534.8893477s；经典反馈/支撑与额外计算费用披露。
首新保存核验120条件RMSE向量、12跟踪、24努力通过，36000trace/11772prediction records；
0模型/fit/物理及旧科学重算。首thin contract零失败，仅保存身份/计数/门一致性，不改变科学结论。
[根归档](../results/cpu_validation/2026-10-12_fast_feedback_pair_control/manifest.json)46payload，
92读146180352bytes，含manifest47写73101730bytes；报告/检查另封存。
当前累计313297控制/2592970子步；在线scalar46452、离线7200不变，总53652。
不改Z2 controller、阈值或同bank补跑；下一项为事前独立准备的FR0自由root接触工程资格，
生产发布、首次必要新纯检查、冻结/正常提交推送后首次有界运行。工程通过也仅另冻本域学习协议，
不恢复Z snapshots或解除科学C4/C5–C7；失败保留并只作有依据有限下一步。持续目标active。


### FR0首次自由root真实接触工程通过：继续本域学习协议

[首次结果](FREE_ROOT_FAST_FEEDBACK_ENGINEERING_RESULTS.md)从cleane5466d326773c9565aa98f0e7063314a32eba5d4一次完成。
原仰卧freejoint、seed7800，1000zero+两目标各1000active全完整3000控制/子步，0停止/异常/failure。
两个完整末200端点窗肩/肘MAE为.000798999789/.00317621993和.00113787695/.00298779686rad，四项均≤.01。
prefix/A/B各1000接触端点无缺失，leftarm正端点949/990/988，feet均0，other985/1000/1000，工程资格通过。
prefix other峰552.5024N，接触比例不证明持续承重、接触因果或安全；公共PD/理想感觉/资产及目标是先验。
2000PD请求、3000audit快照、23493pair检查/force查询；0模型/fit/RLS/MPC/教师/任务策略/GPU。
内wall/CPU2.7291348/2.25s，外3.268851s，构造器内部forward和OS IO等unknown不补零。
[根归档](../results/cpu_validation/2026-10-12_free_root_fast_feedback_engineering/manifest.json)18payload，
36读75221368bytes、18写37610684bytes（不含末manifest写）；首thin64项零失败，
首新指标核验3000trace、四MAE/努力/接触摘要通过，3读18530042bytes、wall/CPU .3986438/.390625s，
0模型/fit/物理及旧科学重算。报告与检查另封存，不把保存一致性当学习贡献。
累计316297控制/2595970子步，online46452/offline7200scalar保持，总53652。
接着另冻自由root新初始化的身体辨识/独立预测/匹配控制协议，不恢复Z snapshots，不改既定科学门。
FR0只开放新学习协议准备，C4及C5–C7科学依赖仍未解除；持续目标active，交付后立即继续。


### FR1首次自由root身体辨识与独立预测通过：接着已冻FR2

[FR1首次本域身体预测](FREE_ROOT_PAIR_PREDICTION_RESULTS.md)从clean41ccb85完成六条完整轨迹、21,000控制/子步与12,000vector/24,000scalar在线更新，0停止异常；H10v肩/肘均值改善34.5534%/29.4351%，H150q改善76.4129%/71.3583%，原预测门全部通过。首新保存核验680,448项零失败、60新RMSE向量及努力/接触、来源/付费账一致；随后执行已在FR1数据前冻结的FR2。原自由root/仰卧、理想感觉、2ms公共PD与固定刺激为披露先验；尚无控制/安全通过，C4及C5–C7未验收。累计337,297控制/2,616,970子步，online70,452+offline7,200=77,652scalar；阶段检查提交推送后继续active目标。

每seed校准1000zero+4000active及独立预测fresh1000zero+1000active，六trial全完整，所有prefix/active left_arm接触phase资格通过，缺失0；接触只资格/诊断，不选择训练样本。H10v/H150q严格改善与两轴原RMSE均值≥20%，H20/H50qv及H150v逐seed不劣全过；H1/H10q只报告。
124680pair/249360scalar独立前向、RLS preupdate12000pair/24000scalar、15000actor PD、21000audit快照/165068force查询，0MPC/teacher/taskpolicy/GPU；内wall/CPU66.0724589/64.625s、外88.2356413s。源码、native、模型初末、全部origins、stdio和停止边界归档。
首保存核验680448项零失败、60个新RMSE向量/努力/接触/来源/付费账通过；[audit](../results/cpu_validation/2026-10-12_free_root_pair_prediction/audit_first/audit.json)及[metric recheck](../results/cpu_validation/2026-10-12_free_root_pair_prediction/audit_first/metric_recheck.json)保存。0模型/fit/新物理/旧科学重算，不重跑旧核验。预测通过不替代控制/努力优势、安全、状态闭合或C4科学验收；五个adoption/release flags固定false。
检查报告正常提交推送后继续已冻FR2 cold/learned MPC/强PD/zero；原控制门、支撑/信息/权限不改，持续目标active。


### FR2首次自由root匹配控制：全部保存结果与下一项

[FR2首次自由root匹配控制](FREE_ROOT_PAIR_CONTROL_RESULTS.md)从cleanf9a0e00保存状态completed，本域原控制门未全部通过；实际新增36,000控制/36,000子步，0更新。原模型贡献门false、强PD available=false/passed=false；首新保存核验passed、77,669项/0失败。全部12计划组、停止/努力及六种自身来源×两模型×五时距完整保留。累计373,297/2,652,970，online70,452+offline7,200=77,652scalar；C4最终新留出及C5–C7未验收。关闭本冻结候选的成功依赖，不补跑或放宽门；依据本次完整保存证据做一次有界判断，再确定独立下一项。 提交推送后继续active目标。

全部tracking/effort、conditional availability及H150肩指标见新报告和完整JSON，不pool自身轨迹、不partial排名。保存门不替代最终新留出或C5release。


### FR2动作描述后唯一FR3候选

[FR3完整首请求网格协议](FULL_REQUEST_PAIR_LEARNING_PROTOCOL.md)已与新scalar/batch、collector/runner一并准备；首次新参数化契约672项通过，48,762pair/97,524scalar前向、0物理/fit/RLS。固定开发seed8001/8002/8003，先原配方FR3A辨识/独立预测，全门通过才执行已冻FR3B；旧FR2失败保留，原20%/5%/努力门不改。最终±.5Nm、首10微步反馈/140PD尾保留；新delta可达±1、网格变粗且一般无purePD候选为新增先验。C4及C5–C7仍未验收，持续目标active，提交推送后立即首次执行。

[一次保存动作诊断](FREE_ROOT_PAIR_AUTHORITY_RESULTS.md)不识别失败原因，不重算旧科学门；新bank先自辨识，不恢复旧参数。


### FR3A首次新bank独立预测

[FR3A首次新bank独立预测](FULL_REQUEST_PAIR_PREDICTION_RESULTS.md)从clean2584ed5保存状态completed，保存原预测门通过；实际新增21,000/21,000/24,000在线scalar。首新保存核验passed、680,623项/0失败、60个新RMSE向量；完整人口、努力/接触与停止原样保留。累计394,297/2,673,970，online94,452+offline7,200=101,652scalar。完成A首审、报告检查及检查点提交推送后，继续在A数据前已冻结的FR3B；controller、模型配方、seed、原门不改。 C4最终新留出及C5–C7未验收，阶段提交推送后继续active目标。


### FR3B首次完整首请求匹配控制

[FR3B首次完整首请求匹配控制](FULL_REQUEST_PAIR_CONTROL_RESULTS.md)从clean20e899a保存状态completed，保存本域控制门未全部通过/不可评；实际新增36,000/36,000/0在线scalar。首新保存核验passed、660,047项/0失败、120个新RMSE向量；完整人口、努力/接触与停止原样保留。累计430,297/2,709,970，online94,452+offline7,200=101,652scalar。关闭本冻结候选的成功依赖；保留负结果，做一次有证据的有界下一判断，不补跑、扩大grid或放宽门。 C4最终新留出及C5–C7未验收，阶段提交推送后继续active目标。


### FR3D零物理保存诊断与唯一下一判断

[FR3D保存轴与阶段诊断](FULL_REQUEST_PAIR_TRADEOFF_RESULTS.md)已一次完成36,000解码/18,000主组active/72轴窗口统计，0失败、物理、模型或更新。肘A/B误差与两类努力均增加，切换窗误差下降仍有努力增加；learned purePD仅27/600存在。只作描述，不识别因果或改判FR3原门。下一唯一FR4以当前PD替换最近nominal点、仍81候选；原H/cost/权限/停止/校准/20%/5%/1.05门保持，新开发8101/8102/8103先检查冻结再首次A→条件B。累计430,297控制/2,709,970子步，在线94,452+离线7,200=101,652scalar保持；C4新留出与C5–C7未验收，提交推送后继续active目标。


### FR4准备与连续执行入口

[FR4 PD锚点协议](PD_ANCHOR_PAIR_LEARNING_PROTOCOL.md)与新控制器、采集器和入口已完成准备。首次新映射契约58项通过，48,600 pair/97,200 scalar前向，0物理/fit/RLS；runner仅行尾归一化，AST相同且协议pin匹配。新开发seed8101/8102/8103，先执行FR4A身体辨识与独立预测，原全部门通过后才执行已冻FR4B完整控制。候选仍81对，每轴当前PD替换最近原槽；纯PD可表达不保证可行、被选或收益。保留原任务、H150、权限、努力与20%/5%门。累计430,297控制/2,709,970子步、101,652 scalar更新保持；C4新留出及C5适应、C6门控、C7综合未验收。持续目标active，检查、提交、推送后立即首次执行。


### FR4A首次结果与立即继续

[FR4A首次PD锚点身体预测](PD_ANCHOR_PAIR_PREDICTION_RESULTS.md)从cleanf4fca3f完成，原独立预测门通过；实际新增21,000控制/21,000子步/24,000在线scalar。首新保存核验passed、680,475项/0失败，60个新RMSE向量；完整人口、实际努力与停止原样公开。累计451,297/2,730,970，online118,452+offline7,200=125,652scalar。提交推送后立即执行在A数据前已冻结的FR4B，19项依赖字节保持相同。 C4最终新留出及C5适应、C6门控、C7综合未验收，持续目标active。


### FR4B首次结果与立即继续

[FR4B首次PD锚点完整控制](PD_ANCHOR_PAIR_CONTROL_RESULTS.md)从clean490fcff完成，本域原完整控制门未全部通过/不可评；实际新增36,000控制/36,000子步/0在线scalar。首新保存核验passed、674,441项/0失败，120个新RMSE向量；完整人口、实际努力与停止原样公开。累计487,297/2,766,970，online118,452+offline7,200=125,652scalar。关闭本冻结候选成功依赖，保留负结果后继续有依据的有限开发判断，不扫描增益、权重或网格。 C4最终新留出及C5适应、C6门控、C7综合未验收，持续目标active。


### FR4D一次投影与结构路线关闭

[FR4D一次保存选择诊断](PD_ANCHOR_SELECTION_DIAGNOSTIC_RESULTS.md)完成：learned600个起点的PD锚点全部存在/可行，chosen12、其余588保存成本差为负；仅限定保存选择结构，不识别实际反事实或失败因果。0新增物理/model/fit/RLS，累计487,297/2,766,970和125,652scalar不变。关闭PD锚点/首请求网格微调族，接着冻结唯一目标保持前馈的控制用途，保留原权限、停止与科学门。C4及C5–C7未验收，持续目标active。

### EF1B唯一控制结构冻结与首次执行

[EF1B目标保持前馈协议](EQUILIBRIUM_FEEDFORWARD_CONTROL_PROTOCOL.md)已完成首次新合成检查9类96项及剩余15项静态对照，原结果前规则固定。仅新增六条cold/learned轨迹，最多18,000控制/子步、0fit/RLS；FR4B已审PD/zero参考直接复用。先从精确clean提交首次执行，原20%模型贡献、5%强PD及1.05实际努力门不变。尚无EF1B物理结果；累计487,297控制/2,766,970子步和125,652scalar更新不变。C4及C5–C7未验收，持续目标active，阶段提交推送后立即继续。

首静态准备把新增错误费用字段误当作不变函数，触发AssertionError: failure，0物理/fit/RLS；保留该首错误后，仅补齐剩余静态对照，failure除新增两项ledger外AST相同。不重跑已通过的9类96项新数学检查、旧物理、旧预测或旧审计。

### EF1B首次完整结果与立即继续

[EF1B首次保持补偿结果](EQUILIBRIUM_FEEDFORWARD_CONTROL_RESULTS.md)从clean f9f5007完整完成六fresh轨迹，18,000新控制/子步、0停止/异常/fit/RLS。同结构模型贡献joint9.0203%、肩8.8254%、肘9.4825%，actual努力两门通过，但未达原20%门；正式PD门因前置失败不可评。本单候选关闭，不scan保持比例/逆解容差/目标状态/gain/权重/seed。累计505,297控制/2,784,970子步、125,652scalar更新。C4及C5–C7未验收，持续目标active；归档核验提交推送后继续有依据的下一方向。

12目标根全部存在、3有限forecast fallback；零技术异常不证明安全或当前目标根的实际物理因果。首次外进程wall246.827482s，内部wall/CPU245.971729/238.671875s。六新与六复用人口、全部预测与费用原样保存，旧数据不重算。

### IV1 首次完成与 IV2 唯一修订（2026-10-12）

[IV1 首次结果](INSTRUMENTAL_ACTION_RESPONSE_RESULTS.md)从 clean d7eb8508f2872e24212d7e3580951c7c44fe8228 一次完成六条 trial、15,000 控制/子步，0 停止/异常。3 次 rank4 fit、12,000 新 IV scalar 标签用途、24 动作系数另计；125,652 历史 scalar RLS 保持。累计变为 529,345 控制 /2,809,018 子步。原预测门 false，动作项单独替换不能产生有效完整递推；不进入控制。27 项轻量身份/人口/冻结/源码 ZIP 检查 passed，未重新执行数学或科学门。

下一唯一 IV2 固定 IV1 八动作系数，仅用每 seed 全部 2000 已付费辨识原生转移重拟合十个非动作系数：psi=(v0,v1,qrel0,qrel1,1)，y=next_v−IV1_action@G/h；每 seed 一次 lstsq、rcond=128eps、rank5/finite 必需。三 solve /30 系数 /12,000 reused offline scalar 标签用途，0 新训练物理与 RLS。随后 fresh 预测上限 6000 控制/子步，新 pulse 时相 slot3 正/slot13 反，原五 H/人口/权限/保护和 cold→新模型门不变，cold/oldlearned/IV1/IV2 全报告。不得拟合 IV1 已见预测或 PAR1 fork；失败关闭单候选，不增特征、正则、扫描或补采。C4–C7 未验收，持续目标 active；阶段交付后立即继续。

### IV2 首次结果与下一唯一保存诊断（2026-10-12）

从 clean d8491b2e0f8b3bae649b8bf9a297bebba7f76270 一次完成三组2000转移状态拟合及三条fresh预测；全部rank5、action8字节保持、5772预测记录完整，0停止/异常。实际6000新预测控制/子步，0新训练物理/独特训练标签/RLS；12000 reused offline scalar标签用途、3solve/30状态系数另计。wall160.03955910005607s，CPU106.296875s。29项新保存人口/身份/参数冻结/ZIP核验全部passed，未解码trace、重算fit/科学门。

原预测门false。H10速度两轴 cold均值 .008679099679/.016107455266，newmatched .113035701660/.240747457478；H150位置 cold .002043547974/.003459631955，newmatched .100373462503/.192411435429。H1也全部退化，完整误差有限不表示模型可用，不进入control。状态项单独一致化不能修复本候选；仍不识别唯一因果，不加正则/特征/数据扫描或补跑。下一唯一IV2D冻结新保存残差与覆盖诊断，仅新离线代数，0物理/fit/model.predict，不重算旧门。累计535345控制/2815018子步，历史125652 scalar RLS不变，IV1新标签与IV2复用标签分列。C4–C7未验收，持续目标active，提交推送后继续。

### IV2D 首次保存诊断与唯一 IV3（2026-10-12）

[IV2D 首次诊断](CONSISTENT_MODEL_RESIDUAL_RESULTS.md)从 clean 14088b6 完整完成，0 新物理/fit/model.predict/RLS；12 项保存轻核 passed，首交付字段命名空间 KeyError 与修正完整归档。训练内误差下降，但 fresh H1 三 seed 均有肩正、肘负速度偏差；原生坐标出箱多为不足 .00030rad 的微小角度越界，不能断言唯一原因。下一唯一 IV3：固定 IV1 action8 与 psi5/一次 OLS，仅将训练 PD 目标改为恒定 qref；最多 9,000 新训练控制/子步、12,000 新 scalar 标签用途。新候选只评估既有 IV2 已见人口，旧分数转录，不扫描或改门；协议/代码/必要新检查冻结提交推送后首次执行。C4–C7 未验收，目标 active。

全六训练槽、60 保存模型×时距组、300 唯一 native H1 起点完整。6 固定 matmul/24,000 reused Y scalar用途；5,772 保存端点、249,360 重复条件递推输入点。wall1.488785000052303s/CPU1.296875s，0 停止/异常；物理535345/2815018与历史125652 scalar RLS不增加。首交付 utility 将 run 字段误从 analysis 读取，原失败保留，仅修命名空间完成既有原件交付，不重跑数学。训练 bias 近零却不能迁移至 fresh H1；频繁微小 q 越界不识别因果。原 IV2 门 false 仅转录，五科学 flags 与 controller 开放均 false。

IV3 保留每 seed1000zero+2000随机 active、PD64/Kd4、base±.375Nm/两轴独立±.125Nm/最终±.5Nm、guard/hinge/接触资格与原停止；新训练全9000控制/子步，3solve/30state系数，0RLS。仅计算新候选在既有 IV2 1443 个 origin 的五 H，预计62340pair/124680velocity head；旧四模型指标只转录。这是已见开发检验，不是最终留出；失败关闭单候选，通过亦需另冻控制。

### IV3首次完整负结果与局部反馈方向（2026-10-12）

当前最早未验收的是 **C4双关节完整接触控制**。[IV3首次结果](NEAR_REFERENCE_IDENTIFICATION_RESULTS.md)从 clean dec307a49cd6ad883b7f6016b2634dd3730a8d7d 完整完成：9,000 新训练控制/子步、12,000 新 scalar 标签用途、3 次 rank5 fit/30 状态系数、1,443 条已见开发预测，0 停止/异常。原预测门 false，H10速度退化，H150位置预测误差巨大；实际仿真轨迹完整。28 项[保存轻核](../results/cpu_validation/2026-10-12_near_reference_identification/delivery_checks.json)passed 只证明保存一致，不代表科学成功。

关闭仅改变辨识姿态的数据域修复及固定 action8＋无约束 psi5 OLS 长时闭合预测器，不采用 IV3 控制。下一唯一方向是**局部动作增量响应＋因果反馈控制**：每2ms用上一合法同trial原生端点与已知请求估计漂移，保持公共PD与保护；不再以失败的自由OLS状态头递推150步选择动作。具体公式、预测资格、失效处理和预算仍需独立冻结，不预先宣称收益，不新增跨历史大诊断。旧预测与20%/5%/1.05控制门保持旧结论，C4–C7未验收。

累计 **544,345 控制 /2,824,018 子步**；历史 **125,652 scalar RLS 更新**保持，IV3新标签/3solve/30系数另计。首合成夹具 TypeError 与未执行部分的2项 passed 均归档；原4次命令只记executed，不追称passed。持续目标 active，提交推送后立即继续下一方法设计。

H10v cold原均值 .008679099679002308/.016107455266461564，IV3 .12157781096361586/.26110297473924593；H150q cold .002043547974399852/.003459631955202392，IV3 2812986448.526063/6014469971.625361。模型误差巨大不是实际物理发散；rank5和finite不代表稳定或完整身体状态闭合。wall26.333276299992576s/CPU22.03125s，62340新pair/124680velocity head；旧240 RMSE scalar分数转录，0旧模型/fit/门重算。首次28保存检查零失败，仅身份/人口/来源/冻结，不重复物理或模型数学。下一设计仍须独立预测资格与完整控制、强经典参照，不能复活旧I残差或默认采用IV1/IV3失败整体模型。


### CF1准备与立即首次执行（2026-10-12）

[CF1协议](CAUSAL_INCREMENTAL_PREDICTION_PROTOCOL.md)与纯runner/model完成，首次必要合成2case passed，逐case及时封存；只验新记忆/guard/单位/ownstate递推及原生连续契约，0新物理/fit/旧数据读/旧数学。完整4146/135900/271800；原手算4140/135780/271560漏H20 origin1980，已在执行前更正，记录于[准备manifest](../results/cpu_validation/2026-10-12_causal_incremental_preparation/manifest.json)。最终静态review后clean冻结提交推送，首次只读IV3已付9000原生区间。新短时门不追认旧长时门，不开放控制；结果交付后继续active目标，C4–C7未验收。
