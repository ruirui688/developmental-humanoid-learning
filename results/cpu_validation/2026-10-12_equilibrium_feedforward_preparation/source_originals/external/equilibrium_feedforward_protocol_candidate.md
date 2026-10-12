# EF1B：目标处模型保持请求前馈与原生PD（正式协议草案）

2026-10-12。仅静态候选，尚未激活、冻结或执行，不触发读取raw/模型或新增物理。root已审定下述唯一数值规则；源码一致性与必要新检查通过后绑定source pins，从clean提交首次执行一次。阶段提交和推送后持续目标仍active。

## 唯一问题、依据与边界

问题是：复用少量原生动作—感觉辨识形成的冻结身体模型，估计当前目标处的零速度保持请求，能否改善已有500Hz经典PD的完整双关节跟踪，并满足原实际努力门？本次固定**两fresh组18,000物理，复用已审PD/zero参考**。

root转述FR4B模型贡献通过、强PD失败：joint改善5.4624%，肘退化17.8586%，两种actual努力超门。一次FR4D learned600锚点均存在/可行，12被选、其余588保存cost差为负；这只描述保存排序，不识别失败原因或PD实际反事实。原网格微调族已关闭。

成功最多支持“学习模型为已有经典反馈能力提供保持请求补偿”。理想感觉、公开身体、500Hz PD、目标、既有辨识刺激和保护都是披露先验；没有教师、PPO、预训练任务策略、GPU或真机。本bank8101/8102/8103已见，只属开发，不能称儿童式技能获得、全身发育或安全收益。

## 身体、模型、任务与权限

保持FR4自由root、仰卧原8轴身体、同asset/reset/接触/重力/关节顺序与原环境配置。只请求两个左臂关节，其余六轴零；2ms反馈/物理步、每轴最终请求±.5Nm、公共关节限位/guard和独立保护保持。每fresh trial为1000zero prefix+2000active；qref取合法prefix端点，方向仍由公开关节范围确定；A active0–999目标qref+s*.04rad，B1000–1999目标qref+s*.08rad。控制不预览目标切换。

active StudyAbort保持原两轴相对位置.12rad、速度1rad/s及环境terminated、非有限和异常规则；停止前已付端点、接触query失败和实际努力未知均保留。prefix只是既有落地稳定初始条件，不称低风险学习。

每seed只恢复其FR4A合法cold/learned冻结snapshot，保持原18系数coupled_hinge9、2ms闭合预测、qref、原公共G及h、初始prior与辨识身份；不恢复FR3或其他域模型、不重拟合。控制与评分期间0RLS/fit/模型参数更新，初末模型fingerprint一致。部署只消费原生两轴q/v、当前已知请求、当前目标和公开guard；接触/root/其余轴/隐藏动力学不进入模型，真实接触力与实际力矩只资格/离线记录。

## 单个保持请求逆解与反馈

每个model/seed在**当前**A、B目标第一次出现时各求一次，最多12次；目标未出现不提前求解，不把两个目标预计算为切换预览，不跨seed复用结果。对当前合法target和假想v=(0,0)求：

```text
u_hold = argmin ||u||²
subject to predicted_next_v(target, (0,0), u) = (0,0), u in [-.5,.5]²
```

完整复合G(target,u)与h(G)均进入反演。G包含原±.5限幅，以及q≤L+.03且u<0或q≥U−.03且u>0的方向阻断；位置等号及原严格请求符号保持。h为sign(G)*max(abs(G)-.25,0)，不能按轴除gain、遗漏guard/hinge或使用隐藏参数。模型目标处的零速度是假想求解状态，不是实测静态力矩或接触/重力辨识。

root已审定唯一数值规则：每轴四闭盒[-.5,-.25]/[-.25,0]/[0,.25]/[.25,.5]，Cartesian16分支；完整G/h在盒内形成耦合仿射方程。SVD rank阈值 `128*float64_eps*smax`，smax=0为rank0。rank2耦合solve；rank1只在同一耦合仿射可行集内求盒约束最小范数，比较无约束最小范数点及最多四edge交点；rank0取盒内离零最近点。严格盒归属，不clip越界根；闭盒可重复边界根，每盒最多一个合法min-norm根进入完整G/h与Counted model.predict(target,0,u)回验。两head共同残差阈值为 `128*float64_eps*max(1, absolute_contributing_products_sum)`：linear以A*point全部4项及2个offset的绝对和取scale；完整G/h与model回验共用theta*features全部18项的绝对和。两输出残差最大绝对值与该共同scalar阈值比较，不逐head单独缩放、不以未来动力学调tol。跨盒根按请求二范数平方、signed u0/u1排序；重复请求再以branch index固定tie。tol只是结构数值契约，不是控制误差或科学新门，不扫描tol、正则或前馈比例。

有限输入/参数且16盒全部无合法核验根时，记录 `no_equilibrium_root`、u_hold=(0,0)，仍运行本结构forecast。非有限输入/参数/中间结果、SVD/solve/predictor技术错误保留首失败并终止相应trial，不伪装成无根、成功fallback或可采用结果。

实际每2ms用当前native q/v请求 `clip(64*(target-q)-4*v+u_hold,-.5,.5)`，再经原当前角guard。前馈在**raw PD与最终公共限幅之间**加入，不先clip PD再加前馈，不增益扫描。保持请求缓存至当前目标改变，反馈/guard随当前感觉改变。

每20ms决策只从当前同一q/v递推这条“当前目标PD+u_hold”轨迹H150=300ms，全150步均用当前目标、预测q/v、相同u_hold与完整原guard；不读取未来实际状态、不预览B目标、不计算cost或排序其他控制候选。保持原forecast相对radius.15rad、velocity1.5rad/s及原joint-limit margin；仅有限位置/速度约束拒绝时实际literal-zero十微步fallback，再按20ms节拍决策。forecast model.predict的任何技术异常同样raise并保留付费/部分计数，不转成fallback。模型状态不clip，forecast资格不等于实际安全。

冷prior在zero-v时原位置/常数漂移为零，合法cold保持请求应为零；forecast拒绝仍可能令cold与PD轨迹不同。若两者实际相同，原20%模型贡献门意味着必须较PD获得至少同量级改善，不能以5%joint门代替贡献门，也不能削弱cold以制造优势。

## 六fresh与六reused来源

每seed依次运行cold+本新controller、learned+同controller，六fresh trial共18,000控制/子步、36s模拟时间；全部从原同seed独立reset和zero prefix开始。PD/zero直接复用**已首审passed的FR4B**三seed六开发来源，不重新物理、校准、评分或增加其付费次数。完整12项人口的来源标签必须分别为fresh或reused，并保留旧trial完整/停止/异常/资格/实际努力及其原首次身份。

冻结时绑定FR4A原manifest/run/models与合法snapshot、原预测通过证据；FR4B原manifest/run/metrics、已首审passed的audit.json、exact source commit和三seed参考trial ID，A/B manifest逐项绑定payload，不额外要求旧audit receipt读取链。固定来源如下（均由root交接，仅恢复结论，不重跑审计）：

| 来源 | bytes | SHA256 / source commit |
|---|---:|---|
| FR4A manifest.json | 2209 | `776cd4abbb69b5c6189c0d015ba4868cffa1713f5c43f388377ff868da9228d9` |
| FR4A source commit | — | `f4fca3f4236acddc92a25c6707f9c29150ee3ca6` |
| FR4B manifest.json | 3154 | `ee66a39474fe6716af90a7671452a95a53541ec676ee7125e07416eed3153d9d` |
| FR4B source commit | — | `490fcffa0080125e7c2a8b887c99cc2743dcc01f` |
| FR4B audit.json（passed，674441项/0失败） | 41990 | `639fc31e3ff6792a8313765ec0a4244f513f50db8b3fa76017f9e7b6830e0b53` |

只恢复既有结论与逐seed指标/资格，不重跑旧audit、预测、RMSE、努力或物理；读取/恢复/解析费用另计，历史费用不归零。

fresh与reused必须匹配相同seed/reset初始化、原asset及环境/物理配置、关节映射、权限/guard/终止、prefix长度、qref/方向规则、A/B目标与active长度；共享相关源码/config身份逐项绑定，不要求新controller源码或新commit与FR4B相同。实际合法prefix端点的reference/目标需与对应reused参考一致；对比身份或首审passed绑定缺失/不匹配时参考不可用，正式强PD门不可评，不补跑参考或换seed修复。复用可减少本次交互，不构成新未见检验。

## 原完整门与自身预测

完整优先，cold/learned/PD必要trial须完整2000active、finite、原接触域资格和actual努力已知；prefix/A/B各1000phase至少一个left_arm-floor正端点。接触共现不证明持续承重或因果。zero只描述，不因其停止添加采用veto；任何停止/缺失不排名partial子集。

模型贡献保持：每seed joint及两axis RMSE严格优于本新cold；三seed原joint/各axis RMSE算术均值分别改善≥20%；两轴合计actual absolute/squared努力原均值各≤1.05×cold。强PD门以前者通过为前置：reused PD全seed完整/资格/努力完整且来源匹配；learned每seed joint/axis不劣于PD，原joint均值改善≥5%；两种actual努力原均值各≤1.05×PD。baseline RMSE0/非finite百分比不可用，effort0要求candidate0；不放宽门、替换弱PD、pool样本或以低努力覆盖误差失败。

actual努力沿原active2000与已付2ms原生actuator_torque端点分母，prefix付费另列；requested/guarded/actual分列，未知None不补零，不称连续力矩积分。复用参考指标原样转录，新fresh按原同函数评分；全部seed、轴、停止和不利指标公开。

自身条件预测仅六条fresh cold/learned来源，各用本seed两个冻结模型，H1/10/20/50/150及两轴q/v全部评分。origin仍active每10步；每条source/model的五H origin数200/200/199/196/186；未来保存final requests只作离线条件输入，未来actual q/v只评分，不注入递推。不对reused PD/zero新增预测或旧指标重算。无事后self-veto，所有退化、missing、nonfinite与有效域限制完整披露。

## 一次预算、保存与关闭

| 本次上限 | 数量 |
|---|---:|
| fresh / reused trial | 6 / 6 |
| 新控制调用 / 物理子步 | 18000 / 18000 |
| fit / RLS vector/scalar更新 | 全部0 |
| 当前目标逆解 / 分支 | 12 / 192 |
| H150单轨decision / forecast pair | 1200 / 180000 |
| 根完整模型verify pair / scalar | 192 / 384 |
| 规划总pair / scalar前向 | 180192 / 360384 |
| fresh自身条件预测记录 | 11772 |
| fresh自身评分pair / scalar前向 | 526560 / 1053120 |
| reused参考新物理/自身预测/旧指标重算 | 全部0 |

planning实际decision为6×200=1200，早停/拒绝只降低actual返回次数，不作效率优势。每根最多16分支、每分支最多一个min-norm根verify，解析SVD/solve、rank1边界候选、范数排序、系数读取、PD/guard和核验分别计actual；这些不是零模型计算。构造/reset/forward、snapshot恢复/指纹、source/协议/参考身份读取、压缩、保存、准备和必要新检查另计，不补未知内部I/O为零。

本批前正式累计固定 **487,297控制 /2,766,970子步**，online118,452+offline7,200=125,652scalar更新；本批新增最多18,000/18,000/0，执行后只按actual追加，不重复增加reused FR4B36,000或FR4A21,000。若全部完成，物理累计上限505,297/2,784,970，scalar更新总量不变；计划上限不能替代实际账。CPU/wall公开，少规划不证明实时或同算力优势。

canonical协议为 `docs/EQUILIBRIUM_FEEDFORWARD_CONTROL_PROTOCOL.md`。新生产路径为 `src/developmental_physics/equilibrium_feedforward_pair.py`、`src/developmental_physics/equilibrium_feedforward_development.py`、`scripts/develop_equilibrium_feedforward.py`；`EquilibriumFeedforwardPairMPC` decision保存root_result/root_cache_hit/root_accounting/forecast_accounting、当前目标、保持请求、forecast/fallback和实际请求。正式身份EF1B/stage controlonly，局部门键 `ef1b_model_contribution_gate_passed`、`ef1b_pd_reference_gate_passed`；无protocol pin或sourceclean失败禁止生产执行。保留配置/版本/clean commit/源码原件、六fresh逐2ms轨迹/停止、六reused身份/指标、模型初末、全部自身预测、费用及首次stdio，不新增复杂重复audit或文书。

`scientific_adoption`、`old_free_root_C4_validation`、`c4_scientific_validation`、`c4_contact_scientific_validation`、`c5_scientific_dependency_released`全部false；开发全门通过才另冻新最终C4留出，C5适应、C6成熟/门控与C7综合仍待验收。首技术失败和科学失败分列保留，不重跑到成功。此单候选未过原门即关闭，不扫描前馈比例、逆解正则/容差、目标状态、增益、权重或seed。阶段检查、提交推送后继续active目标，不以本协议、报告或局部门宣称整个目标完成。
