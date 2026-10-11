# FR4：PD锚点替换网格的自由身体辨识与匹配控制

2026-10-12。本文与新scalar/batch controller、collector和runner在任何FR4新数据前一起冻结、提交和推送。只执行一次FR4A；原预测门全部通过后，才执行同次冻结的FR4B。失败关闭本候选后续依赖，不扫描seed、网格、增益、时距、代价、权重或辨识剂量，不重跑到成功。FR3原协议、源码、通过与失败保持。

## 问题、依据与证据边界

[FR3完整首请求协议](FULL_REQUEST_PAIR_LEARNING_PROTOCOL.md)保持最终±.5Nm，通过扩大首请求候选取得模型贡献，但[FR3B首次完整控制](FULL_REQUEST_PAIR_CONTROL_RESULTS.md)未通过正式强PD门：joint改善5.8823%，肘退化18.1937%，actual absolute/squared努力超出原门。模型贡献通过约83.3%不能覆盖强基线失败，不解除C4/C5依赖。

[一次保存诊断FR3D](FULL_REQUEST_PAIR_TRADEOFF_RESULTS.md)显示learned肘在A/B两阶段SSE和actual absolute/squared努力都增加；切换pre/post窗肘SSE下降但努力增加，失配不限于切换瞬态。纯PD候选仅在27/600个保存decision存在，27个均feasible，其余573个不存在；肘选中delta远大于nearest nominal距离。后者不能证明量化已解释失败，候选存在或可行也不证明应被选中或能改善实际控制。

唯一FR4结构修订是：**每轴用当前公共PD请求替换最近nominal网格点，保持9×9个原槽位组合。** 它保证delta0候选在函数类中可表达，检验原候选包含性限制，不识别FR3失败的原因。新grid既增加PD锚点又删除一个原点，属于新增控制函数类先验和覆盖代价；不得称单一量化因果消融、低风险改进或成功预告。新的seed与FR3不同，FR3/FR4跨批比较不构成匹配状态因果对照；模型贡献仍来自FR4内部cold/learned同controller比较。

## 固定人口、身体与信息

固定开发bank为**8101、8102、8103**，依次执行，不按结果选择seed。root首次公开源码/文档exact整数搜索无命中，搜索命令、范围、来源commit和exit1另行保存；raw与非公开历史未检索，不能宣称全局未用或最终未见。8001–8003已用于FR3开发，不恢复其权重到FR4新seed。

保持[自由root原学习协议](FREE_ROOT_LEARNING_PROTOCOL.md)的自由root、仰卧原8轴身体、原接触/重力/reset/asset；两个左臂关节为学习/控制轴，其余六轴请求零。2ms原生反馈和物理步，1000步zero prefix。公共PD每轴 `p=clip(64*(target-q)-4*v,-.5,.5)`；最终请求每轴±.5Nm，原guard、公共关节限位及底层保护独立。

reference取合法prefix端点，方向按公开关节范围的原确定性规则选择；所有方法共享同一规则和目标。完整任务active前1000目标qref+s*.04rad，后1000为qref+s*.08rad；不预览未来目标。prefix用于落地稳定，不称低风险学习；active StudyAbort保持原两轴相对位置.12rad/速度1rad/s及原环境终止、非有限/异常规则，停止前付费数据保留。

部署模型只消费原生两轴q/v、当前已知请求和公开guard，q按原运动学积分。18系数coupled_hinge9、每轴P100I、lambda1、原冷prior/尺度/阈值不变。IMU、root、其余关节和接触模式未闭合；真实接触力、隐藏动力学、动能只资格与诊断，不进入部署预测或控制。理想感觉、PD保持能力、公开身体、任务目标、保护和固定探索刺激均为披露先验；没有任务教师、预训练任务策略、PPO、GPU或真机。

## FR4A：新bank身体辨识与独立预测

每seed从同冷prior构造cold和learned；cold始终冻结，learned仅在本seed校准合法转移上更新。完整校准fresh1000zero+4000active，共5000控制/子步。顺序保持paid native保存→audit→StudyAbort→合法连续转移RLS；audit错误或停止不能吞掉付费端点，也不能偷偷更新。

原4000active刺激保持：20个200微步块，四组方向肩(1,0)、肘(0,1)、同向(1,1)、反向(1,-1)，每组五块幅度.125/.25/.375/.5/.25Nm。每块slot0正、slot10反，各10微步，其余零。每微步先clip公共PD、加已知pulse、再clip最终±.5；不按感觉选剂量，不添加控制标签fit。每seed最多4000vector/8000scalar提交，相关微标签不写成独立样本。

随后两模型冻结；独立预测fresh1000zero+1000active，0更新。原五个200微步块方向(1,0)/(0,1)/(1,1)/(1,-1)/(1,1)，幅度.125/.25/.375/.5/.375Nm；slot1正、slot9反，各10微步，其余零，PD目标qref。每seed的origin为active0,10,…；未来保存final requests只作离线条件输入，未来actual q/v只评分，不注入递推。

| H微步 | 时距 | FR4A origin/seed | FR4B每条自身control origin |
|---|---|---:|---:|
| 1 | 2ms，仅报告 | 100 | 200 |
| 10 | 20ms | 100 | 200 |
| 20 | 40ms | 99 | 199 |
| 50 | 100ms | 96 | 196 |
| 150 | 300ms | 86 | 186 |

原独立预测门不变：H10v/H150q每seed两轴严格改善，各轴三seed原RMSE算术均值改善≥20%；H150v及H20/H50 q/v每seed两轴不劣。H1与H10q全部报告，不加事后门。完整所需物理、接触域资格、origin、finite和冻结身份才可评；baseline0/非finite不可算百分比，不删失败seed、不排名finite子集。任何必要条件或原门失败，FR4B关闭。

## FR4B：唯一PD锚点替换结构

静态nominal每轴九点 `U=(-.5,-.375,-.25,-.125,0,.125,.25,.375,.5)` Nm，原spacing=.125。每次select仅从当前actual native q/v和当前目标计算一次共享p_current。对每轴i，计算九个 `abs(U[j]-p_current[i])`，按(distance, original_index)取唯一nearest槽j_i；仅该槽替换为 `p_current[i]`。距离相等按较小original index取，不用模型权重、未来状态、候选cost或feasibility选择替换槽。

保持九个原slot顺序，不排序、不deduplicate、不append第十点；两个axis的九槽按原Cartesian枚举得到81个候选。每候选仍 `delta[i]=replaced_grid[i]-p_current[i]`，对本macro计算一次并held。新helper只消费这一已计算p；不会为每候选重算当前PD，也不因select改变静态nominal self._candidates/spec/fingerprint。

slot组合(j_0,j_1)的delta=(0,0)，保证纯公共PD rollout可以表达：首10微步的held delta0以及后140微步的PD tail。**不保证该候选feasible、被chosen、较低实际努力或收益。** 原forecast约束可能拒绝它，原成本/tie也可能选其他候选；不强制选择、不优先排序、不加新veto/安全门/权重或与PD实际误差的oracle比较。

覆盖代价明确：每轴替换点移动最多.0625Nm，相邻gap可扩大至.1875Nm；若nearest是±.5端点，原端点可能被删除。p恰为原点时实际轴grid不变；一般每轴只保留8个原nominal点，双轴新候选可能只保留64个原nominal对，不能称原81点覆盖全部保留或包含FR3全部动作。新增PD候选与删除原点一起改变控制函数类。

stage0仍用实际浮点表达式 `clip(p_current+(replaced_grid-p_current),-.5,.5)`，不承诺逐bit等于nominal或replaced_grid。预测、首成本、tie和实际执行使用同一roundtrip，保存实际first requests与选中residual，不能首步暗换标称点。delta最大绝对值仍≤1Nm；每阶段最终请求仍±.5Nm。

每候选从当前同一q/v闭合递推；前10个2ms预测微步用预测q/v重算PD，加不变delta再clip；stage10–149 residual零，原H150=300ms公共PD尾。实际每2ms用新native q/v重算PD加held delta，十步后重新规划；不是将首请求恒持20ms，不预览目标切换。全候选不合格时仍literal-zero十微步，与delta0继续PD不同。

原81/H150/20ms规划/2ms反馈、forecast radius.15rad/velocity1.5rad/s/margin、成本与tie全保持：position.1、velocity.0002、effort.000002，每阶段完整final requested torque；首change.00002对上一已知final request，无discount。优化tie仍cost、abs(first full request)、signed first request、signed residual，与nearest替换tie的original index分开。模型状态不clip；forecast约束不等于真实安全保证。

新scalar `PDAnchorResidualPDPairMPC` 与新batch `BatchedPDAnchorResidualPDPairMPC` 独立于FR3原生产实现；batch支持资格明确绑定新映射和显式Counted身份。static spec用nominal grid和替换规则描述，actual动态grid不伪装成静态点。新增每macro18次scalar distance及两次nearest选择作为工程计算开销另计；原前向预算不因这一结构变化归零或缩减。

必要一次有界新契约只验证新增nearest/tie与原槽81映射、off-grid/on-grid/saturated p、delta0表达、最大位移/gap/端点与64原对的覆盖边界、stage0 roundtrip、新scalar/batch完整decision和计数、显式Counted适配及unsupported回退边界。保留原stage9/10、±.5、cost/tie和literal-zero事实，不重跑旧RLS/MPC数学、旧物理、旧审计或FR3D。所有新合成首次失败与费用保留；检查通过不预告科学收益。

## 完整比较、接触资格与原科学门

FR4A全门通过后，每seed依次cold+新MPC、learned+同新MPC、公共强PD、zero，四fresh trial各1000zero+2000active，共3000控制/子步。只恢复本seedFR4A合法冻结snapshot，控制0新更新。源码、身体、reference、关节顺序、model protocol与4000原子提交身份一致；不得恢复旧FR3、790x、悬挂或控制模型。

所有12项完整报告。cold/learned/PD所需prefix/A/B各1000完整phase至少一个left_arm-floor正端点，沿用原自由root工程资格；正接触共现不证明持续承重、接触因果或安全。zero接触只描述，zero停止不增加采用veto，但停止/缺失保留。完整优先，未知actual努力或最大接触力保留unknown/None，不补零、不部分排名。

**原模型贡献门**：cold/learned每seed完整2000active、接触域资格和actual努力完整；每seed joint及两axis RMSE严格改善；三seed原joint/各axis RMSE均值各改善≥20%；两轴合计actual absolute/squared努力原均值各≤1.05×cold。

**原强PD门**：贡献门通过为前置；所需PD全seed完整/域资格/努力完整；learned每seed joint/axis不劣于PD，原joint均值改善≥5%；两种actual努力均值各≤1.05×PD。贡献失败则正式PD门不可评；baseline RMSE0百分比不可用，effort0要求candidate0，不换弱PD、不以较低努力替代通过。

actual努力按所有已付2ms原生actuator_torque端点样本计算，不称未测连续积分；requested、guarded command和actual分列。全部停止、异常、接触query失败及未尝试人口保留。PD candidate包含性只属于controller结构事实，不成为新科学门。

## 自身预测、来源与同预算

FR4B六条cold/learned自身来源分别用两个本seed冻结模型和实际保存final requests条件递推；完整H1/10/20/50/150及两轴q/v逐seed报告，不pool、不把planner PD尾与再规划actual差直接归因模型。校准范围和全2000自身起点越域摘要只描述，不筛起点、不追加fit。无self性能veto，不事后追加；自身退化、缺失和nonfinite限制结论，不由独立预测门覆盖。

| 费用上限 | FR4A | 条件FR4B |
|---|---:|---:|
| fresh trial | 6 | 12 |
| 控制调用/物理子步 | 21000/21000 | 36000/36000 |
| RLS vector/scalar提交 | 12000/24000 | 0/0 |
| MPC decision | 0 | 1200 |
| planning pair/scalar前向 | 0 | 14580000/29160000 |
| 全条件评分pair/scalar | 124680/249360 | 526560/1053120 |

一次总上限57000调用/子步、114s模拟时间；历史累计按本批前封存阶段账本actual继续增加，不用旧成功、当前计划或新bank归零。额外nearest计算上限21600 scalar distance/2400 nearest index选择，另报实际。规划、RLS preupdate、PD/guard、scalar dots/batch kernels、snapshot/clone/restore、源码hash/读取、接触query、构造/reset/forward、输出压缩、准备/首次检查均另计；未知内部I/O不补零。实际CPU/wall公开，仿真等待规划不证明20ms实时或同算力优势。

沿用本地CPU依赖Python3.10.11、NumPy2.2.6、MuJoCo3.15.0，运行保存实际版本；没有新增外部数据/依赖/教师/策略checkpoint。保存源码原件/commit/协议pin、所有微步/decision/candidate/label/prediction、模型初末/更新、首stdio、付费ledger、接触/努力/停止/异常/未尝试和manifest。

## 独立stage身份、冻结与持续执行

生产路径为 `src/developmental_physics/pd_anchor_pair_mpc.py`、`src/developmental_physics/pd_anchor_pair_development.py`、`scripts/develop_pd_anchor_pair.py`。FR4A/B experiment_id独立；stage保持prediction/control，四stagekeys为 `fr4a_prediction_gate_passed`、`fr4b_model_contribution_gate_passed`、`fr4b_pd_reference_gate_passed`、`fr4_free_root_mechanism_validation`。FR3历史stagekeys/raw保持，不覆盖FR1/FR3A预测通过或FR2/FR3B失败。

FR4A路径为 `results/cpu_validation/2026-10-12_pd_anchor_pair_prediction/`，FR4B为 `results/cpu_validation/2026-10-12_pd_anchor_pair_control/`；不覆盖旧attempt。19项minimal source依赖保持原FR3数量，只更换本3个新生产文件与本协议，完整列表由新runner绑定。A/B的19份算法/协议bytes和SHA逐项相同；A交付检查点允许HEAD变化，但不能据其结果改controller、模型、门、任务、seed或预算。协议自身pin在运行前固定，新runner未获得pin时禁止生产执行。读取原FR0工程资格只恢复既有证据、不重跑；FR4B仅读取本新FR4A预测门及合法模型。

`scientific_adoption`、`old_free_root_C4_validation`、`c4_scientific_validation`、`c4_contact_scientific_validation`、`c5_scientific_dependency_released`在FR4开发结果全部false，局部stage门通过不回写这些flags。FR4全部通过才另冻结对应候选的新留出C4验收，随后仍需C5适应、C6成熟/门控、C7综合验证；不激活以FR3B原门通过为前提的旧草案，不称全身/真机成功。

必要新检查与静态review → clean冻结提交/推送 → FR4A首次一次 → 原全部预测门通过才FR4B首次一次 → 新保存证据必要核验/全部结果与限制报告/actual累计 → 提交推送后立即继续active目标。技术失败与科学失败分列，首失败保留，不自动重跑、不改变原门。失败关闭本冻结候选的成功依赖，依据完整保存证据做一次有边界判断，不scan/扩grid/改权重到成功。报告或局部门不结束持续目标。
