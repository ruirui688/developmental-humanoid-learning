# FR1/FR2：自由root地面接触域身体辨识与匹配控制候选

事前外部候选，尚未生产发布/执行。FR0已从clean `e5466d3` 首次完成3,000控制/子步，0停止异常；主代理转录的A/B肩肘四MAE约 .000799/.003176/.001138/.002988rad，prefix/A/B左臂正接触949/990/988个端点（各分母1000）。这些是固定PD与该初态的工程可达性，不是身体学习。FR0、悬挂Z1/Z2及已有费用全部保留。

本候选唯一研究问题：**在原自由root仰卧地面域、相同2ms原生反馈/经典PD/权限下，新形成的紧凑身体预测模型，能否改善独立多时距预测，并在完整匹配控制中贡献≥20%、通过强PD比较？** 不把FR0接触共现当作支撑因果，也不从悬挂预测成功或Z2贡献失败推断本域结论。

## 1. 共用身体、信息、seed与停止

沿用FR0的原 `GroundBodyEnv` freejoint root、supine reset、八轴/电机/资产、baseline contact、重力、5mm reset clearance及原jitter算法。只使用已冻结2ms反馈接口（control_substeps=1）；不新增固定安装、支撑、重力/接触修改或pose搜索。所有方法最终每受控轴±.5Nm，其他六轴请求零；公共PD Kp(64,64)/Kd(4,4)，原逐子步限位方向guard不变。

开发seed候选固定 **7901、7902、7903**。主代理已做一次公开exact整数边界搜索（README/AGENTS/docs/src/scripts/tests，不含raw/results/external）：1数字匹配为 `tests/test_feedback_development_audit.py:257` 的synthetic `control_calls_attempted=7901`，0公开seed匹配。保留这一事实，不写0matches或绝对unused，不保证非公开用途完全未见。正式发布再绑定该搜索receipt，不重复搜索到0；三个seed不是最终未见bank。

每条fresh对象仅reset一次。所有prefix均为1,000zero/2s，仅走基础保护；完整prefix999 after才绑定qref。各同seed校准、独立预测和控制轨迹的公开范围/资产/物理/执行配置相同，prefix qref逐轴差≤1e-12；失配付费并blocked，不换qref、重装或重置到一致。FR0不存在安装XML修改，不要求虚构悬挂installed XML或机械反力。

方向为公共范围较宽方向，平手取正；目标须位于公共限位margin .03rad内，不clip或换方向。active每个完整返回2ms后原StudyAbort：任一受控轴 `abs(q-qref)>=.12rad` 或 `abs(v)>=1rad/s` 即停止，等号停止。原八轴20rad/s、数值/solver/能量/关节保护等不变，环境reason与研究停止分别保存。终端先付费/保存，停止后不补积分、制动、纠正、重试或partial排名。

## 2. 唯一模型假设；不是自动复制悬挂动力学

本候选有意选择一个可证伪、18系数的小模型：2ms两轴native q/v、已知最终请求及公开角度guard的 `coupled_hinge9`；它是**自由root接触域的新局部条件预测假设**，不是已验证的接触动力学，也不识别真实质量、惯量或摩擦。

每个velocity head共享九列：

`phi=[v0,v1,q0-qref0,q1-qref1,G0(q0,u0),G1(q1,u1),h(G0),h(G1),1]`

其中G仅复用公开control-start角度方向guard，`h(a)=sign(a)*max(abs(a)-.25,0)`。每head预测下一完整2ms原生v，位置使用 `q_next=q+.002*v_next`。相同九列不等于相同学得参数；每seed新初始化并独立更新两head。

free root运动、其余六轴、地面接触模式及约束冲量均未进入phi。原完整native可用于报告这些伴随变化，但不能把缺失状态视作已经闭合，也不能声称q/v必然Markov。FR0的高接触比例只证明该工程轨迹上观察到接触，不证明新脉冲下的模型或8sactive校准有效域。这个可解释的小函数类优先用于一次有限验证；失配时公开负结论，不自动补最佳相关IMU/接触特征、lag或维度。

**重新初始化：**仅从公开未学习generic20ms prior固定转换到2ms：`Theta_2ms=E+.1*(Theta_generic20ms-E)`，E只保留本轴v identity；own request初始系数.002，q/cross/hinge/constant初始零。P100I、lambda1、hinge .25和原子两head RLS复用。18系数/seed是有效参数数，不把更多时间相关微标签当独立样本增加。单位响应及时间缩放是需要披露的结构先验，不是测得的本域动力学。

不恢复Z1/Z2、X/Y、D/G或其他旧learned snapshot。新FR2可恢复**本协议FR1已保存且通过所有门的本seed冻结结果**，并重新验证该域/时间/初始参考/范围/源绑定；不能把这一必要恢复混写成0恢复计算。冷模型保持相同新prior，学习前性能和全部初始/最终权重、协方差及计数保存。

标签只来自当前trial连续的完整native transition：输入为动作前两轴q/v与已知最终requested u，标签为动作返回后的两轴原生v。不能读未来actual torque、接触力、root quaternion、真实动力学或未来真实状态作输入；public guard不读取仿真隐参数。位置不另fit，target/pulse是控制器公开请求生成条件，不加入身体phi。模型训练不按接触力挑样本、加权或丢弃不利端点。

## 3. 独立free-root采集接口与付费顺序

需要独立 `free_root_pair_development.py` / `scripts/develop_free_root_pair.py`（拟路径），配合FR0 `FreeRootFastFeedbackGroundBodyEnv` 的supine和audit-only接口。**不能只替换Z collector的env_factory**：Z硬编码upright并依赖support_configuration、installed XML、interface_fingerprint、engineering_operations及substep_native_and_contact_records；FR0没有这些悬挂契约。禁止monkeypatch或伪装接口、悄悄使用upright。

每次step的顺序冻结为：

1. 计控制attempt及实际确认的积分；返回后持久保存paid_native_endpoint（原生after、diagnostics、请求/实际actuator样本与已付费子步），保留原积分/forward主体。
2. 只在完整返回的一次2ms端点调用新floor-pair审计，遍历ncon，仅floor pair额外mj_contactForce一次（包含Fn≤0）；没有额外mj_forward/mj_step。left_arm/feet/other分类、signed/positive力单位N、查询attempt/return/exception分别计账。
3. active在相同qref下进行StudyAbort；任何停止/audit异常/原生不完整不得更新RLS。保存audit/stop annotation，缺失接触标unknown，既有native/努力和确认积分不丢。
4. 仅校准active合法、完整且未停止的transition执行一次原子两head RLS；RLS异常保留尝试/失败与已付费端点，不提交单head、不重试样本。独立预测、prefix、FR2全程不更新。

接触标签只资格/风险诊断，既不传给PD/MPC/phi，也不选择下一请求或RLS训练人口。校准/独立预测的prefix与完整active各至少一个left_arm-floor Fn>0端点，作为**本域完整资格**；另外逐0.4s块全报接触比例/缺失、native范围和努力，不事后追加block门。FR2科学采用所需的cold/learned/PD保持FR0的prefix/A/B三个完整phase各≥1条件，分母分别1000；zero全部保存并描述，可停止，不新增zero采用门。新域要求轨迹中出现接触，不声称全时持续接触；含Fn=0的合法端点仍用于同一native辨识人口。

## 4. FR1：固定少量在线辨识与独立预测

每seed先校准，完整/本域资格/4000vector提交均通过才尝试该seed的fresh独立预测。某seed失败不补跑，其他seed按已冻结顺序保留独立事实；全局源码/依赖不可用的fatal工程错误则停止余下执行并明确unattempted。

校准：1,000zero+**4,000active**，共10s/5,000调用/子步。这是8s的有限2ms辨识，不运行任务策略训练；三seed最多12,000vector/24,000scalar提交。公共PD目标固定qref，每微步先clip PD，再叠加已知pulse，再clip最终±.5。

20个固定0.4s块（每块200微步/20个20ms slots）：四组方向依次肩(1,0)、肘(0,1)、同向(1,1)、反向(1,-1)，每组五块幅度 .125/.25/.375/.5/.25Nm。每块slot0的10微步为正pulse，slot10的10微步为反pulse，其余零；不按新感觉更改幅度/相位/目标或追加剂量。此刺激是共享的身体探索先验，不是外部动作教师；公共PD提供了已有的局部保持能力。

冷/学模型共享新prior与qref，cold全冻结、learned仅校准更新；校准后两者冻结。不得用FR0或PD控制轨迹追加fit；不得为完成4000更新继续到停止后的额外时间。连续微标签高度相关，不能把12,000vector提交写成12,000独立探索样本。

独立预测：fresh 1,000zero+**1,000active**，共4s/2,000调用/子步、0更新。五个0.4s块方向(1,0)/(0,1)/(1,1)/(1,-1)/(1,1)，幅度 .125/.25/.375/.5/.375Nm；slot1正、slot9反，各保持10微步，其余零。PD目标仍qref。未来已保存的final requests只作离线条件输入，未来真实q/v只评分。

origin固定为active请求前起点0,10,20,…；每模型递推自身q/v与公开guard，不能在递推中注入未来真实状态或contact。完整时距和人口：

| H微步 | 时距 | FR1独立origin/seed | FR2单条完整自身control origin |
|---|---|---:|---:|
| 1 | 2ms，仅报告 | 100 | 200 |
| 10 | 20ms | 100 | 200 |
| 20 | 40ms | 99 | 199 |
| 50 | 100ms | 96 | 196 |
| 150 | 300ms | 86 | 186 |

保持原独立预测门：H10v/H150q每seed两轴严格改善，各轴三seed**原RMSE算术均值**改善≥20%；H150v及H20/H50 q/v每seed两轴不劣。H1与H10q完整报告，不增加事后门。全部所需物理、本域资格、origin、输出finite及模型冻结一致才可评；baseline0/非finite的百分比不可用，不能去掉失败seed或有限子集排名。

FR1任一完整/本域资格/预测门未过关闭FR2；保存原先付费数据、模型与不可用原因。失败不改prior、phi、脉冲、数据量、lambda、增益、频率或阈值再试，不把新seed用作优化扫描。

## 5. FR2：相同初始化的完整闭环控制

FR1全部所需门通过、且controller/collector早已冻结才启动。每seed依次cold+MPC、learned+MPC、强PD、zero，四fresh trial，各1,000zero+2,000active/6s。active前1,000目标为qref+s*.04rad，后1,000为qref+s*.08rad。所有模型、gain及gate冻结，actual微反馈/最终权限/停止/域资格及努力分母统一。

规范参考为现有**scalar** `FastFeedbackResidualPDPairMPC` 的相同数学规则，free-root适配只独立绑定新域/新模型/配置/证据，不改controller参数：每20ms（active0,10,…1990）一次决策，H150=300ms，81个首10微步held residual，每轴9点覆盖[-.125,.125]Nm。每candidate用自身预测q/v重算并clip公共PD、叠加前10步residual、再clip最终请求；剩余140步residual零。实际也每2ms用新native q/v重算PD加held residual；10步后重新规划，不把首torque恒持20ms。目标只当前值、不预览切换。

全candidate不合格时为literal zero请求模式，后10微步请求零；与residual=0继续PD不同。完整请求effort和首change计成本，change对上一已知final requested u，不能换成actual力矩或上一macro起点旧请求。无discount；running position/velocity/effort权重 .1/.0002/.000002，首change .00002；forecast radius .15rad、velocity1.5rad/s、margin/tie/guard/回退保持原规范。forecast阈值与真实 `.12/1` 不同，不能当实际安全保证。

批候选实现由其他代理另准备，**本候选默认不采用**。若主代理在FR1任何新数据前决定采用同语义batch，必须先完成新的有限评分/feasible/fallback/tie/selected residual与请求语义检查、明确数值边界和最终kernel身份并重冻源码；全部方法共用。不能FR1后依据结果替换kernel、顺带改网格/时距/代价或把一批调用计作一个逻辑前向。

**模型贡献门：**cold/learned全seed完整2000active、各所需phase接触资格及actual努力完整；每seed joint与两axis RMSE严格改善，三个seed原joint/各axis RMSE均值各改善≥20%；两轴合计actual absolute/squared effort原均值各≤1.05×cold。

**强PD门：**贡献门先通过，所需PD全seed完整/本域资格/努力完整；每seed joint/axis不劣于PD，原joint均值改善≥5%；两种actual努力原均值各≤1.05×PD。贡献失败时PD门不可评，不用事后比较或较低努力宣告正式通过。RMSE0基线不能产生百分比优势，effort0基线要求candidate也0。

全部12trial的matrix完整性另报；zero停止完整保留，无新zero采用门，不partial排名。zero失败不偷换cold/learned/PD各自所需完整优先条件，也不消失在报告里。任何所需模型贡献/PD门不通过即负结论，不补跑或放宽门。

## 6. Z2肩长期自身预测缺口如何在本域显式检验/报告

FR1共同独立预测与FR2各方法自身轨迹分开。对6条cold/learned控制轨迹，每条都用本seed两个冻结模型在相同已保存未来final requests上条件递推，按上表完整macro origins评分。逐seed、轨迹来源、预测模型、H、q/v和肩/肘分别保存原RMSE；不能pool轨迹、不把cold自身与learned自身不同人口拼成模型优劣。独立预测通过不覆盖自身肩H150退化。

同时报告校准native q/v/request/公开G范围、每条自身起点越域比例（分母全部2000active起点）和每H的完整availability；范围是描述，不据此剔除起点、改门或训练标签。接触/其余关节/IMU/root动态只作新保存诊断，不因最大相关性就认定因果或新增部署输入。

本开发协议不对原未门控的self H1/H150事后加veto或修改原科学门；它们是必须公开的有效域证据。若本域出现长期肩退化，即使其他门通过，也只支持那些已通过的指定人口/任务，不称闭环预测普适改善或模型已经覆盖全部接触模式；新留出验收必须继承并明确审查这一缺口。

planner自身PD rollout另存selected预测、feasible/reason和fallback；其首10步为当前held residual反馈，10步以后假定residual零，而实际会再规划。不能把300ms planner预测与再规划后的actual差直接归因于身体模型，因为未来动作规则不同。自身条件评分使用实际保存requests，避免混写这两类预测。

## 7. 有界CPU、更新与实际努力账

| 费用上限 | FR1 | 条件FR2 |
|---|---:|---:|
| fresh trial | 6（3校准+3独立） | 12 |
| 控制调用 / 物理子步 | 21,000 /21,000 | 36,000 /36,000 |
| 付费模拟时间 | 42s | 72s |
| RLS提交vector /scalar | 12,000 /24,000 | 0 /0 |
| actor PD向量反馈 | 15,000 | 18,000 |
| MPC决策 | 0 | 1,200 |
| planning pair /scalar前向 | 0 | 14,580,000 /29,160,000 |
| 条件主时距pair /scalar评分 | 124,080 /248,160 | 524,160 /1,048,320 |
| H1报告pair /scalar评分 | 600 /1,200 | 2,400 /4,800 |
| 全条件评分pair /scalar | 124,680 /249,360 | 526,560 /1,053,120 |

科学新增最大57,000调用/子步、114s模拟时间；FR0已付3000/3000另列，旧累计不归零。每seed仅18系数/两个9×9协方差，RLS小矩阵可CPU运行；14.58m pair规划仍是显著有限计算，不称轻量辨识等于轻量全控制。scalar规范有固定最大1200×81×150结构，不做重复benchmark或GPU训练；实际CPU/wall、每决策计算及deadline超时若有分别披露。仿真等待规划，不证明2ms或20ms实时deadline、真机执行或同计算预算优势。

表中前向是逻辑上限；candidate拒绝/停止按实际次数计，少失败计算不当效率优势。RLS内部preupdate前向、guard、actor与planner PD、clone/同协议restore/snapshot、每head原子提交、查询、hash/来源读取、构造/reset/原forward、压缩/写盘均另外实际计账，不能把24k scalar更新当全部算力。

actual absolute/squared努力明确按所有已付费2ms的原生actuator_torque端点样本估算，不暗称未测连续积分。requested/guarded applied command与actual样本各自保存；audit异常不抹掉native已知努力，未返回/未保存actual为unknown或已知下界。接触为端点采样观察：额外force查询是实际Fn获取费用，不是模型forward，也不新增积分；冲量为端点样本×2ms估算。

## 8. 冻结、首次检查、证据与持续执行

拟生产协议 `docs/FREE_ROOT_LEARNING_PROTOCOL.md`，独立collector/runner及必要模型域元数据/控制绑定先审查。正式FR1与FR2controller都在任何FR1学习/预测数据前一起冻结、正常提交推送；从clean精确commit第一次执行FR1一次，通过全部原门后再执行已冻FR2一次。源码/环境/时间/模型与初始化/协议/FR0来源及同协议参数身份逐项绑定，不通过任意旧结果自动开放。

只做新增free-root/supine wiring、paid-native→audit→study→RLS顺序、原子失败保留、跨trial参考/范围/模型冻结、完整人口/接触可用性和输出契约的必要纯检查；不重复旧悬挂装配、已过RLS/MPC数学或已揭晓物理。新batch若未采用不把其检查强行加入此路线。

保存配置/seed/完整精确source/版本/首次stdio、所有原生微步、macro决策与候选计数/代价/可行性/回退、模型初末状态、全部origin标签/预测、当前最终请求/actual、接触分类/queries、停止/异常/未尝试、四个层次的eligibility/availability/门以及实际费用。technical/source failure与科学失败分清，首次坏分支和负结果原样归档，不修报告成成功。

即使FR1/FR2全过，也仅是此自由root两轴开发人口的局部机制证据；原C4要另冻新留出综合验收，C5/C6/C7仍后续独立检验。工程PD已完成的能力不算学得；没有预训练任务策略，但身体/经典控制/保护/刺激及公共目标都是明确先验。`scientific_adoption`、`old_free_root_C4_validation`、`c4_scientific_validation`、`c4_contact_scientific_validation`、`c5_scientific_dependency_released`在本开发结果固定false。

阶段检查、报告和正常提交推送后继续最早未过门；失败关闭本冻结候选的后续依赖，再依据有限的新保存证据提出一个独立下一项，不无限扫描到漂亮结果。持续目标仍active，本外部设计不启动采样或预告科学成功。

## 本次设计读取与执行边界

仅静态读取Z学习协议、generic2ms adapter/MPC源码，以及coupled_hinge9/公开guard feature定义和位置积分API的窄片段；使用主代理转录的FR0事实与7901/7902/7903公开搜索结果。没有读取任何旧raw、Z1/Z2/FR0保存权重或协方差、参数snapshot；0生产import/模型调用/物理/fit/RLS/测试/fixture执行。生产文件未改。本协议费用由新计划整数算术核对，不重算旧科学结果。
