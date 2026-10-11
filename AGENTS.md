# AGENTS.md

本文件是本仓库给 Codex 和其他代码智能体的项目级交接说明。开始工作前先读本文件和 `README.md`；其余文档按当前任务需要查阅，不要求机械地全部加载。

## 1. 项目使命

本项目研究：能否把人类运动发育中的低风险探索、身体模型形成、能力门控的运动成熟和技能积累，转化为刚性人形机器人的安全、样本高效运动学习方法。

长期目标是让一台**没有预训练翻身、起身或站立任务策略**的真实人形机器人，在独立安全系统保护下逐步学会身体探索、翻身、起身、站立和行走。“从零”不表示移除关节限位、急停、底层控制或传感器校准。

用户于 2026-10-10 再次明确：二维火柴人也应沿着模拟小孩的发育学习路线，通过探索和反馈形成运动能力。这是原初目标，不能把解析步态教师或预训练行走策略解释成该目标的自然起点。主研究轨保留身体结构、原生感觉、基础控制和安全约束；特定步态示范、步态跟踪监督及已具备任务能力的教师属于单独先验对照。旧二维 DHP-PPO 实际包含这些任务先验，其成功不能证明纯小孩发育路线已经实现。关闭教师仍需审计环境中的参考步态奖励、速度代理和相位接触；详见 `docs/STICKMAN_CPU_COMPARISON.md`。

核心路线是通过少量真实交互建立身体模型、形成协调能力并积累技能，减少对大规模任务策略训练的依赖。优先验证自监督在线系统辨识、局部预测控制和能力门控的组合；这些是待检验的算法候选，PPO 保留为比较基线。不能把动物出生后的快速运动发展等同于无先验机器人从随机动作快速学会行走。

二维理想火柴人概念验证显示完整 DHP-PPO 组合方案优于相同环境交互预算下的直接 PPO，但不能识别单个组件的因果贡献。同步后的仓库还包含 PBHC + Isaac Gym Preview 4 的 G1 工程审计与地面发育记录：翻身/支撑门已通过，辅助起身仍处于平台，尚无 G1 多 seed 方法优势或真机结论。详见 `docs/PBHC_INTEGRATION.md` 和 `docs/EXPERIMENT_LOG.md`；这些是其他环境的既有证据，本轮 CPU 验证没有复现 GPU 实验。

## 2. 当前最优先目标与持续执行

用户明确要求：把项目作为持续目标推进，阶段检查、提交和推送后立即继续，不等待再次说“继续”。当前持续目标保持active，阶段账本见 [docs/CONTINUOUS_EXECUTION_PLAN.md](docs/CONTINUOUS_EXECUTION_PLAN.md)。单个局部门、一次报告或提交都不是整个目标完成；用户明确暂停时才暂停。

当前仅CPU，用户已允许少量在线身体辨识。主方法候选为原生动作—感觉建模、局部预测控制及能力门控；不运行大规模PPO、GPU训练、任务教师、预训练任务策略或真机。历史零更新实验保持原边界，新辨识、离线重放、校准、规划及评估分别计账。经典PD、固定模型、公开身体与底层保护属于需要披露的先验。

本持续目标要完成低维多关节的预测、完整闭环控制、未知动力学适应、固定成熟/能力门控及新留出综合对照。顺序是C0单关节 → C1有效域 → C2修订/消融 → C3强经典基线 → C4双关节 → C5变化适应 → C6成熟机制 → C7综合验收。G1完整翻身、起身、站立和行走是后续长期路线，不能用局部CPU结果宣布真机成功。

### 当前证据与最早未验收阶段

- C0局部学习已通过：[E1 v2](docs/CPU_LOCAL_BODY_RESULTS.md)每seed300次RLS，独立预测改善85.6%–86.7%、同MPC跟踪改善28.9%。自身闭环预测仍退化、努力增加，不能声称风险下降或全身技能。
- C1/C2/C3开发及单肩新最终已完成：[新最终结果](docs/LOCAL_FROZEN_VALIDATION_RESULTS.md)同MPC贡献通过29.505%，相对调优PD只改善2.674%，未过5%门；自身一步与位置有效域仍有缺口。旧留出10/11/12及20/21/22已经使用，不作为修订后的未见bank。
- **当前卡在C4双关节完整控制。** 左肘及A/B/C/D/E/G的失败完整保留；[F上下文描述](docs/GUARD_NATIVE_CONTEXT_DIAGNOSTIC_RESULTS.md)不能识别因果，不支持直接追加最佳相关特征。[G结果](docs/GUARD_PD_TAIL_CONTROL_DEVELOPMENT_RESULTS.md)从clean91dcf6c首次完成8完整/4肘速度停止：cold0/1各11active、learned0/2各102/104active，learned1/cold2及全部PD/zero完整。控制子门未过，D旧独立预测20%门不追认。
- C5只有[事件工程](docs/C5_ENGINEERING_RESULTS.md)通过，未取得科学适应结论；C5科学实验仍依赖完整C4，C6/C7未验收。

G原件与结果已推送e8c6c04；首审1,422,925项零失败和一次summary35绑定零失败只证明证据一致，不代表科学门通过。结果24payload保留原始轨迹、源码ZIP、首次stdio、全部停止及绘图。准备首schema失败、Git嵌套external忽略与长路径失败也已归档，不重跑旧数学、已揭晓物理或审计。

### 当前下一步

[Y0首次结果](docs/DAMPED_SUSPENDED_PAIR_ENGINEERING_RESULTS.md)从clean1ef7bbe3df016b01b47b0bea0ccc27821c0d7091一次完成100prefix+103active、203控制/2,030子步后，肘速度1.1258089506362488rad/s触发原1rad/s StudyAbort；环境terminatedfalse、failure空，0异常/fit/RLS。第一窗虽observed20但full trial失败而availablefalse/MAEnull，第二窗0，不partial排名。完整工程资格失败，Y1/Y2关闭、不scan增益；X0/W0/V关闭保持。下一项仅控制时间尺度与底层保护有限审阅，尚未承诺新实验或周期/保护修订，不因失败放宽门。零接触观察、机械固定支撑及经典反馈先验披露，不追认C4或解除C5科学依赖。持续目标active，阶段检查提交推送后继续。

旧X0阶段记录：[X0首次结果](docs/SUSPENDED_PAIR_ENGINEERING_RESULTS.md)从clean6319fb6首次完成100prefix+4active、104控制/1,040子步，肩速度1.0957066489965022rad/s触发原1rad/s StudyAbort；0异常/fit/RLS，两个末窗不可评，完整工程资格失败，本安装X1/X2关闭。所存子步left_arm/feet/other接触全部零观察，不宣称接触或站立学习，不partial排名。接着唯一独立Y候选仅把公共肩Kd0改为已有肘Kd4，安装/权限/目标/阈值不改、不scan，须科学静态review、另冻结及有界首次执行；不是X0成功补跑，也不承诺通过。旧X协议/controller保持，旧W0/V分支关闭，C4/C5科学依赖未解除。此段为旧决策，不触发重跑。

旧W0阶段记录：[W0首次结果](docs/SUPPORTED_PAIR_ENGINEERING_RESULTS.md)从clean54cf4c2完成全部300控制/3,000子步，固定前缀左臂真实接触满足，但active80..99肩/肘MAE .01455068/.01388462、180..199为.03919046/.00653010rad，四项仅一项≤.01，工程资格失败。本安装W1/W2关闭，不改安装/seed/增益/目标补跑，不推论所有控制不可达、接触因果或旧C4通过。下一唯一X0直立悬挂域设计，明确机械固定支撑先验及可能非接触的域边界；新域仍不能解除C4，最终须完整接触控制。以下旧记录只作历史，不触发重跑。

[V首次结果](docs/GUARD_ORACLE_TAIL_DIAGNOSTIC_RESULTS.md)从clean7e1e5dd完成：4,572记录/192组完整，600H1精确，Q/U受控H2/H5/H15均略退化。12,408前向、10,122覆盖/182,196未来scalar用途；0fit/物理/RLS/旧self重算，首8薄契约全过。不进控制，关闭oracle路线与同bank优化，继续一个有边界的新支撑域双关节机制设计；它不能追认原地面接触C4，最终仍需完整接触控制。不能从负结果识别缺传感或支撑因果。持续目标仍active、C4/C5科学依赖未解除。以下为旧决策历史，不能据此重跑；当前入口以阶段账本首页及最后记录为准。

[H保存诊断](docs/GUARD_PD_TAIL_FORECAST_STOP_DIAGNOSTIC_RESULTS.md)确认学习预测合规但实际超速；[I因果残差结果](docs/GUARD_PD_TAIL_NATIVE_RESIDUAL_DIAGNOSTIC_RESULTS.md)从clean1f239f3首次完成102端点/96pair，learned seed0/1两轴退化、seed2改善，肩/肘三seed均值仅3.18%/4.68%，主门失败；cold全退化。不采用上一残差进控制。[J六轴IMU残差](docs/GUARD_IMU_RESIDUAL_DEVELOPMENT_RESULTS.md)从clean9e8a212首次完成，C共同prediction肩/肘均值退化3.39%/2.77%，全部seed两轴退化；不采用。新增离线ridge2400scalar标签/3solve/36系数，0新物理/RLS。[K完整原生状态闭合转移](docs/GUARD_NATIVE_TRANSITION_DEVELOPMENT_RESULTS.md)从cleanb46c6d3首次完成，所有H1/2/5/15窗口有限；H1速度只改善0.485%/0.194%，H15位置退化0.208%/0.469%，开发门失败，不进控制。K新增离线ridge26400标签/3solve/1914系数，0新物理/RLS。L固定数据增量已执行，结论见下段；这些修订均不解除C4/C5依赖，已见数据只开发，新留出/控制仍另需验证。

[L固定数据增量结果](docs/GUARD_NATIVE_AUGMENTATION_DEVELOPMENT_RESULTS.md)已完成：clean2dce248来源校验误拒绝，0fit/predict，原失败已公开；仅修D记录bytes/SHA比较后从clean3bbc34d完成3429记录/576组、16契约零失败。L相对K/D两门均失败：H1速度约3%–7%，H15位置退化约77%–81%；不进入控制，不追加PD数据/维度，下一项做有限结构诊断。新增ridge39,600标签/3solve/1,914系数、0新物理/RLS；PD能力/采样先验及旧费用披露。原4工程分支未重跑，来源修复新增一次合成检查；首输出契约误对来源失败要求完整计数的断言及仅该项补充也保留。

[M固定设计诊断](docs/GUARD_DESIGN_GEOMETRY_DIAGNOSTIC_RESULTS.md)已从clean4d10eac首次完成：六套资格通过、18SVD/36matmul返回、14项输出契约零失败。K全seed四个关注输出shrink大于floor，L则floor大于shrink；所有设计rank29、上下文rank25、条件动作rank4。满秩/训练floor不证明泛化或动作因果，L条件能量比例低但绝对能量及均方更高。新增66,000原生标签/12,000命令响应离线投影估计，另66,000归档ridge前向输出，0新物理/RLS。旧预测门不改，不进控制；接着依据收缩证据冻结单个尺度/正则候选，不扫描lambda/增数据，不自动执行旧位置—速度proposal。

[N单一输入RMS尺度ridge](docs/GUARD_SCALED_NATIVE_TRANSITION_DEVELOPMENT_RESULTS.md)已从clean74725ea首次完成，3429记录/576组完整有限、15契约零失败；相对K/D两门均失败。H1肩速度退化，H15位置改善不足20%、两轴速度退化；不进控制。新增26,400标签/3solve/1,914系数，0新物理/RLS，K/D只恢复不fit。首夹具漏blob失败与仅该分支补充均保留。下一项限定一次保存预测的局部误差/递推输入差分解，不调用模型或fit、不自动追加特征或扫描参数；有依据后再冻结单个结构修订。当前C4未验收，阶段提交后直接继续active目标。

[O保存诊断](docs/GUARD_SAVED_RECURSION_DIAGNOSTIC_RESULTS.md)已从clean77bf803完成全部11,910记录/792组，10项有限输出契约零失败；0模型调用/fit/新物理/RLS。N相对K在三seed两轴保持/释放组退化、开启略改善；H15递推差增加伴交叉抵消，不能解释为因果贡献。下一项P只追加上一合法同trial两轴已知请求到K原始phi29，形成phi31；C400/.01/原prior/22闭合及K/D两门不变，预计26,400标签/3solve/2,046系数。缺历史失败、不补零或改人口，不保留N尺度、不扫lag/正则；先冻结/首次开发，未过不进控制。C4/C5科学依赖仍关闭。

[P单段请求记忆结果](docs/GUARD_REQUEST_MEMORY_TRANSITION_DEVELOPMENT_RESULTS.md)已从clean8315e61首次完成3,429记录/576组；P→K及P→D两门均失败。H1v相对K仅改善2.879%/2.904%、相对D3.350%/3.092%，H15q两基线均退化约7%；H2v/H5qv/H15v也退化。不接入P控制，不追加第二lag或重跑旧诊断。新增26,400离线scalar标签/3solve/2,046系数、0物理/RLS，K/D只恢复且指纹不变；首准备静态解析失败、五合成case与正式原件保存。下一项只冻结一个直接作用于速度预测的结构修订，保持C400与两原门，不扫描参数；C4/C5科学依赖仍关闭，持续目标active。

P后唯一Q候选为K原phi29追加(qrel0/.12,qrel1/.12,v0/1,v1/1,startG0/.5,startG1/.5)的全21二次项，phi50。尺度来自公开StudyAbort及权限，不估训练RMS、零列保留；C400/.01/prior/22闭合不变，无P记忆/N尺度/扫描。预计26,400标签/3solve/3,300系数，0物理/RLS；先新合成检查/静态review、冻结提交，再首次开发，保持两原门。局部二阶动机不证明原失配原因，新增函数类/正则先验及递推风险须披露。P报告/提交后直接继续准备Q，持续目标active。

[Q正式结果](docs/GUARD_QUADRATIC_NATIVE_TRANSITION_DEVELOPMENT_RESULTS.md)已从clean20fa032首次完整3429记录/576组；H1v相对K/D约26%–28%改善，H2/H5qv/H15v全部不劣。两门仅H15q不足20%（约6%），不进Q控制。新增26,400标签/3solve/3,300系数，0物理/RLS；K/D指纹不变。下一唯一R冻结Q weights，每步完整Qnext22后仅q0/1改为oldq+.01*(oldv+nextv)，其余20输出保留，0fit；两丢弃q-head计算仍计账。新证据支持检验运动学一致性，不能保证收益或追认旧门；仍需全部时距/seed及原K/D双门。C4/C5科学依赖保持关闭，Q报告/提交后直接继续R准备。

[R首次结果](docs/GUARD_KINEMATIC_NATIVE_TRANSITION_DEVELOPMENT_RESULTS.md)从clean7d2cbab完整4,572记录/840组；两门各12/14项通过，仅H15q幅度失败（相对K肩/肘8.854%/2.942%，不足20%）。0新fit/物理/RLS，Q/K/D指纹不变，首薄契约15组全过只证明保存一致。R/Q不进控制，C4/C5科学依赖不解除。下一唯一S保留Q同50列/22闭合及其余20head，只用C400连续窗口做有限多步位置拟合；全部原门不变，不增加物理或扫描参数，旧bank仅开发。代码/协议/新必要检查先冻结，再首次执行；阶段提交后继续active目标。

[S首次结果](docs/GUARD_MULTISTEP_POSITION_TRANSITION_DEVELOPMENT_RESULTS.md)从cleanfcab231执行，三seed初始目标与梯度有限、第一次优化试探全部quadratic21溢出，无候选。4,572计划记录/840通道组保留，S不可用、双门不可评；fit3尝试/3失败、objective9/6/3、0新物理/RLS。数值失败不否定多步目标。下一唯一T保持S损失/模型/C400窗口，以固定1e-3系数L2信赖步、Armijo1e-4与最多10回退修订优化；非有限trial拒绝保留费用，不clip状态或伪造gradient、不扫描。先冻结/新最小检查再首次执行，C4/C5依赖保持关闭，阶段提交后继续。

新物理必须先冻结任务、信息、权限、完整优先门、seed和预算，从干净提交首次执行一次；保留停止前付费交互和负结果，不补跑到成功、不放宽旧门。不能拿部分RMSE排名、不用较少步骤当作停止轨迹的效率优势，也不能用“零停止”证明安全。所有方法共享相同目标、最终权限、停止与实际努力分母。

当前模型只消费原生关节q/v、已知请求及连续过去端点；previous_v不得跨trial或补零，不得读未来实际力矩。D sparse11仅恢复其冻结snapshot，G不重拟合。PD64/(0,4)及其旧增益开发费用明确披露，预测尾只用当前目标，无切换预览。接触力、动能、真实动力学和root quaternion只作离线诊断，不进入部署模型；当前native没有orientation。

正式物理累计 **253,297控制调用 /2,532,970子步**；Y0新增203/2,030/0更新，X0/W0此前新增104/1,040与300/3,000，历史在线22,452+离线7,200=29,652scalar更新计算保持。G新增3,028/30,280/0更新。费用及A–G完整历史见阶段账本与对应结果，不因新候选归零。科学证据否定机制时公开负结论，再做有依据开发；不以无限重复或改任务取得漂亮结果。

G1与机器接管仍按 [docs/NEW_MACHINE_BOOTSTRAP.md](docs/NEW_MACHINE_BOOTSTRAP.md)、[docs/DATA_SOURCES.md](docs/DATA_SOURCES.md)和 [docs/DEVELOPMENT_ROADMAP.md](docs/DEVELOPMENT_ROADMAP.md)；采用新依赖/后端时锁定来源、版本与许可。当前CPU工作不要求安装GPU仿真器。

## 3. 近期非目标

- 不改造 G1 硬件，不把压力鞋垫或电子皮肤设为启动条件；
- 不直接从二维火柴人跳到无保护真机训练；
- 不在第一篇论文中承诺完整的“婴儿式”翻身、起身、站立和行走全流程；
- 不把 Isaac Lab 中的结果称为真机结果或 Sim2Real 成功；
- 不在使用外部动作、教师或预训练检查点后仍声称实验没有任务先验；
- 不为追求漂亮结果而省略失败种子、不利指标或额外数据预算。

## 4. 近期论文问题与实验组

近期问题应收敛为：

> 在受支撑站立与重心控制任务中，在线身体建模、局部预测控制和能力门控能否在相同先验与成功标准下，减少交互和危险动作，并提高对载荷、延迟和动力学变化的适应性？

第一轮机制实验采用：

1. 适合任务的经典反馈控制及系统辨识/预测控制；
2. 相同初始化的冻结身体模型与在线更新模型；
3. 完整控制权限、固定成熟与能力门控成熟；
4. 受约束随机探索与主动探索的消融。

G1 阶段补充 Direct PPO；需要评价任务策略或人体先验时加入合适的 motion-imitation 或其他强基线。各阶段按研究问题选择实验组，不要求在最小原型阶段实现所有算法。接触估计和人体先验分别作为组件或独立实验轨披露，不能默认完整方案同时包含它们。

“纯发育轨”和“人体先验轨”必须分开报告：前者不使用预训练任务策略或外部任务演示，共享并披露身体资产、公共身体信息、底层控制与安全条件；后者可使用合适的动作数据或教师作为参考，但必须披露数据量、许可和使用组别。任何共享控制器已有的任务能力均须报告，额外接触教师标签也须单列。

## 5. 科研与数据规范

- 优先使用可验证的官方或上游来源；不要随意下载或执行不明 fork；
- 外部来源必须记录 URL、精确 commit/tag、许可证、下载日期、校验值、转换步骤和使用实验组；
- 机器人模型和公共配置可以作为所有方法共享的环境信息；动作数据属于额外先验；预训练检查点属于教师或强基线；三者不得混写；
- 只有实际采用某个外部项目时，才将它加入依赖或数据清单，并遵守其许可、署名和用途限制；
- 不把外部仓库源码、原始数据集或大型检查点直接提交到本仓库。放入 `external/`、`third_party/`、`data/raw/` 或本机专用目录；
- 比较方法时统一 G1 关节顺序、动作定义、终止条件、训练/评估场景和环境交互预算；
- 人体演示样本、教师调用次数、预训练计算和 GPU 时间与 RL environment steps 分开报告；
- 所有方法记录学习前表现；校准、探索、失败、复位后的动作和在线更新期间的真实交互计入预算；纯适应实验不得声称冷启动技能获得；
- 底层控制器、已知物理模型、任务目标、默认姿态和外部支撑均属于需披露的初始条件；评估时统一权限和支撑，学习模型不得读取仿真器隐藏参数；
- 仿真接触力可以作为训练教师标签，但部署策略不得暗中读取真机不可用的特权观测。

## 6. 安全边界

任何真实机器人工作开始前都必须具备独立于学习策略的急停、关节/电流/力矩/速度/温度限制、软垫或吊架、人工监护和低风险初始姿态。学习策略不能覆盖硬件安全控制器。没有用户明确授权和现场安全条件时，只做仿真与离线分析。

## 7. 仓库地图

```text
src/robot_rl/                  二维概念验证实现
src/developmental_control/     NumPy 固定模型控制与能力门控原型
src/developmental_physics/     可选 MuJoCo CPU 地面采集与局部身体辨识
src/developmental_g1/          既有 PBHC / Isaac Gym G1 研究组件
tests/                         CPU 单元测试
results/validation/            已公开的验证数据、图表和视频
paper/论文初稿.md               当前中文论文初稿
docs/PROJECT_OVERVIEW.md       项目定位、优势与验证矩阵
docs/DEVELOPMENT_ROADMAP.md    当前算法路线、阶段验收与近期待办
docs/CPU_VALIDATION.md        CPU 无训练验证、证据边界与后续轻量方法
docs/DEVELOPMENTAL_ROBOT_VISION.md
                               长期真机愿景和系统设计
docs/DATA_SOURCES.md           外部资源选择、记录和公平使用原则
docs/NEW_MACHINE_BOOTSTRAP.md  新环境接管与资源自适应步骤
docs/RESEARCH_DIALOGUE.md      决策来源和讨论记录
```

在线学习核心与未来 Isaac Lab 代码应放入独立且清晰的包/目录，不要把仿真器依赖强行加入现有轻量二维单元测试路径。

## 8. 常用命令

在仓库根目录执行：

```powershell
python -m pip install -e .
$env:PYTHONPATH = "src"
python -m pytest -q
git diff --check
```

现有实验复现和视频导出命令见 `README.md`。Isaac Lab 安装命令必须以实施当天的官方文档为准，并在首次成功后锁定精确版本，不能长期追踪浮动分支。

## 9. 修改和交付规则

- 先检查 `git status`，保留用户已有改动，不覆盖无关文件；
- 先做最小可验证实现，再扩大训练规模；
- 修改代码后运行相关测试；修改 Markdown 后运行 `git diff --check` 并检查链接；
- 用户已于 2026-10-10 授权开发过程中持续提交并推送可验证的中间进度；每个阶段完成相关检查后及时保存代码、实验记录和文档，提交信息说明研究含义。推送前同步远端并保留已有工作，不强制推送；
- 每次实验保存配置、seed、源代码 commit、依赖版本、GPU、训练预算和原始逐种子指标；
- 遇到缺少硬件、凭据或会改变科研结论的选择时，清楚记录阻塞，不虚构结果。

## 10. 新会话的第一项行动

如果这是新环境中的首次 Codex 会话：先按 `docs/NEW_MACHINE_BOOTSTRAP.md` 识别实际软硬件条件并运行现有 CPU 测试；随后读取 `docs/DEVELOPMENT_ROADMAP.md` 选择当前可完成的阶段。在关节/刚体映射和站立 smoke test 通过前，不开始 G1 长时间训练或大规模采样。缺少 GPU 时继续 CPU 身体建模与控制原型，不静默安装驱动或操作真实机器人。

最新准备：Y0失败已推送7fe5b27，X/Y学习分支关闭。一次[接口审阅](docs/CONTROL_INTERFACE_ROUTE_REVIEW.md)后，独立[Z0协议](docs/FAST_FEEDBACK_ENGINEERING_PROTOCOL.md)将反馈改2ms、原物理/PD/权限及6s任务不改；控制调用/感觉计算与active停止检查频率增多明确披露。14项新纯合成检查首次通过、0真实装配/物理；仅工程候选，冻结后clean首次seed7600最多3000/3000。新学习配方不得自动继承旧20ms模型、H15或原更新预算；Z0成功也不追认接触C4。持续目标active，阶段交付后继续。

X0首次结果入口：[停止结果](docs/SUSPENDED_PAIR_ENGINEERING_RESULTS.md)、[原悬挂域协议](docs/SUSPENDED_PAIR_DOMAIN_DESIGN.md)、[关闭的事前X1/X2配方](docs/SUSPENDED_PAIR_LEARNING_PROTOCOL.md)。首次工程104/1,040后肩速度停止、末窗不可评；独立thin contract零失败只证明证据一致，不代表工程或科学通过。下一独立Y肩阻尼候选须另review/冻结，不修改X协议或controller；非接触悬挂机制不能追认旧C4或解除C5科学依赖，持续目标保持active。

Y当前结果：[首次阻尼工程停止结果](docs/DAMPED_SUSPENDED_PAIR_ENGINEERING_RESULTS.md)与[原冻结协议](docs/DAMPED_SUSPENDED_PAIR_PROTOCOL.md)。seed7500首次203/2,030后肘速度停止、完整门失败，Y1/Y2关闭，不scan增益。首thin contract零failed、0MAE重算仅证明证据一致。接着只审阅控制时间尺度与底层保护，不预设新实验；用户要求持续执行，阶段提交推送后继续最早未过门，完整自由root接触C4及C5–C7仍未验收。
