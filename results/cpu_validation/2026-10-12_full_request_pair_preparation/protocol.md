# FR3：完整首请求网格的自由身体辨识与匹配控制

2026-10-12。本文与新 scalar/batch controller、collector、runner 在任何 FR3 新数据前一起冻结、提交和推送。只执行一次 FR3A；其原预测门全部通过后执行同次冻结的 FR3B。失败关闭本候选后续依赖，不扫描 seed、网格、增益、时距、代价或辨识剂量，不重跑到成功。

## 问题、依据与证据边界

[FR1](FREE_ROOT_PAIR_PREDICTION_RESULTS.md)自由身体独立预测通过；[FR2](FREE_ROOT_PAIR_CONTROL_RESULTS.md)12条控制全部完整，学习模型相对同MPC的joint/肩/肘误差改善12.2978%/11.3197%/14.7473%，未达到原20%门，正式强PD门不可评。

[一次保存动作诊断](FREE_ROOT_PAIR_AUTHORITY_RESULTS.md)发现learned三组每200个决策中，肩179/182/182次、肘各198次选到±.125Nm残差边界；learned全部81候选可行。肩有部分clip吞掉修正，肘多数修正生效，不能把收益不足统称为饱和。这支持检验控制函数类限制，不识别它是失败原因。

唯一新结构是**完整首请求网格按当前公共PD换算held residual**。最终电机许可不变；控制函数类、首请求分辨率和纯PD候选包含性改变，均为额外先验。新seed上的结果不构成旧FR2与FR3之间的匹配状态因果消融。模型贡献来自新实验内部cold/learned的同controller比较。FR3成功也只是开发证据，仍需独立C4最终留出、C5适应、C6门控和C7综合验收。

## 固定人口、身体与信息

固定开发bank为 **8001、8002、8003**，依次执行，不按结果选择seed。首次公开源码/文档exact整数搜索无命中，搜索命令、范围、source commit与exit1保留；未检索raw或非公开历史，因此不宣称全局未用或最终未见。7901–7903已用于开发，不恢复其learned权重到新seed。

保持[FR原协议](FREE_ROOT_LEARNING_PROTOCOL.md)的自由root、仰卧原8轴身体、原接触/重力/reset与asset；两个左臂关节为学习/控制轴，其余六轴请求零。2ms原生反馈和物理步，1000步zero prefix。公共PD每轴 `p=clip(64*(target-q)-4*v,-.5,.5)`；最终请求每轴±.5Nm，原guard、公共关节限位及底层保护独立。

reference取合法prefix端点，方向根据公开关节范围按原确定性规则选择；所有方法共享其目标和选择规则。完整任务active前1000目标qref+s*.04rad，后1000为qref+s*.08rad；不预览未来目标。prefix用于落地稳定，不把它宣称为低风险学习；active研究停止仍是原相对位置.12rad/速度1rad/s及原环境终止、非有限/异常规则，停止前付费数据不丢弃。

部署模型只消费原生两轴q/v、当前已知请求和公开guard，q按原运动学积分。模型为18系数coupled_hinge9，每轴P100I、lambda1、原冷prior和原阈值/尺度；关节q/v、最终请求之外的IMU、root、其余关节、接触模式未闭合。真实接触力/动力学/动能只资格与诊断，不能暗中进入预测或策略。理想感觉、PD保持能力、公开身体、目标、保护和固定探索刺激须披露；没有任务教师、预训练任务策略、PPO或GPU。

## FR3A：新bank身体辨识与独立预测

每seed从同冷prior构造cold和learned；cold始终冻结，learned仅在本seed校准合法转移上在线更新。完整校准fresh1000zero+4000active，共5000控制/子步。先保存paid native，再audit，再StudyAbort，最后合法连续转移才RLS；audit错误或停止不吞掉已付费端点或偷偷更新。

原4000active刺激不变：20个200微步块，四组方向肩(1,0)、肘(0,1)、同向(1,1)、反向(1,-1)，每组五块幅度.125/.25/.375/.5/.25Nm。每块slot0正、slot10反，各10微步，其余零。每微步先clip公共PD、加已知pulse、再clip最终±.5；不按感觉选择剂量，不添加控制轨迹fit。每seed最大4000vector/8000scalar提交，相关微标签不能写成独立样本。

随后两模型冻结；独立预测fresh1000zero+1000active，0更新。五个200微步块方向(1,0)/(0,1)/(1,1)/(1,-1)/(1,1)，幅度.125/.25/.375/.5/.375Nm；slot1正、slot9反，各10微步，其余零，PD目标qref。每seed独立origin active0,10,…，未来保存final requests仅作离线条件输入；未来实际q/v只评分，不注入递推。

| H微步 | 时距 | FR3A origin/seed | FR3B每条自身control origin |
|---|---|---:|---:|
| 1 | 2ms，仅报告 | 100 | 200 |
| 10 | 20ms | 100 | 200 |
| 20 | 40ms | 99 | 199 |
| 50 | 100ms | 96 | 196 |
| 150 | 300ms | 86 | 186 |

独立预测门原样保留：H10v/H150q每seed两轴严格改善，各轴三seed**原RMSE算术均值**改善≥20%；H150v及H20/H50 q/v每seed两轴不劣。H1与H10q全部报告，不另加事后门。完整所需物理、接触域资格、origin、finite与冻结身份才可评；baseline0/非finite不可算百分比，不去掉失败seed或排名finite子集。任何必要条件或原门失败，FR3B关闭。

## FR3B：唯一新控制参数化

每轴固定九点首请求网格 `U=(-.5,-.375,-.25,-.125,0,.125,.25,.375,.5)` Nm，spacing=.125，双轴81组合。每次macro仅用当前实际native q/v和当前目标计算一次共享p_current；每候选按 `delta=u_grid-p_current` 换算。相同cold/learned实现不以模型权重或未来状态生成网格。

stage0采用实际浮点表达式 `clip(p_current+(u_grid-p_current),-.5,.5)`，不承诺逐bit等于标称grid。预测、首成本、tie和实际执行使用同一roundtrip，保存实际请求；不能在首步暗换成标称grid。delta静态可达±1Nm，但每阶段最终请求仍±.5Nm。

每候选从当前同一q/v闭合递推；前10个2ms预测微步用自身预测q/v重算PD，加不变delta再clip。stage10–149 residual零，仍原H150=300ms公共PD尾。实际每2ms用新native q/v重算PD加held delta，十步后重新规划；不把首请求恒持20ms，不预览目标切换。全候选不合格时保持literal-zero十微步，与delta0继续PD分开。

标称首请求0对应delta=-p_current，后续不是literal-zero十步。一般没有delta=(0,0)的纯PD候选；不得加第十点或替换网格点补入PD。旧residual网格间距.03125、新final-grid间距.125，扩大覆盖也变粗分辨率；不是单一幅度消融。此结构可抵消/反转clip后的PD，可能损害稳定性，不预告低风险或收益。

原81/H150/20ms规划/2ms反馈、forecast radius.15rad/velocity1.5rad/s/margin、成本和tie保持：position.1、velocity.0002、effort.000002，每阶段计完整final requested torque；首change.00002对上一已知final request，無discount。tie仍cost、abs(first full request)、signed first request、signed residual。模型状态不clip；forecast阈值不等于真实研究停止安全保证。

新scalar参考与新batch明确独立，旧生产controller不改。新batch支持条件绑定新full-grid及Counted类身份，不能沿用旧固定residual等价结果或绕过资格检查。仅作一次有界新参数化契约检查：非grid与饱和p、81映射、首roundtrip、stage9/10、最终限幅、literal-zero与PD区别、新scalar/batch完整decision及计数、显式Counted适配；不重复旧RLS/MPC数学或旧物理。

## 完整比较、接触资格与科学门

FR3A全门通过后，每seed依次cold+新MPC、learned+同新MPC、公共强PD、zero，四fresh trial，各1000zero+2000active，共3000控制/子步。cold/learned模型引用本seedFR3A合法冻结snapshot，0新更新。源码、身体、reference、关节顺序、model protocol与校准4000原子提交必须匹配；不能读取旧悬挂、790x或控制模型来替代。

所有12项完整报告。cold/learned/PD所需prefix/A/B各1000完整phase至少一个left_arm-floor正端点；沿用FR工程资格，正接触共现不证明持续承重、接触因果或安全。zero接触只描述，zero停止不增加采用veto，但停止/缺失保留。完整优先，未知actual努力、缺失最大接触力保留unknown/None，不补零，不部分排名。

**原模型贡献门**：cold/learned每seed完整2000active、接触域资格及actual努力完整；每seed joint和两axis RMSE严格改善；三seed原joint/每axis RMSE均值各改善≥20%；两轴合计actual absolute/squared effort原均值各≤1.05×cold。

**原强PD门**：贡献门通过为前置；所需PD全seed完整/域资格/努力完整；learned每seed joint/axis不劣于PD，原joint均值改善≥5%；两种actual努力均值各≤1.05×PD。贡献失败则正式PD门不可评；baseline RMSE0百分比不可用，effort0要求candidate0，不用事后弱PD或较低努力宣告通过。

actual努力按所有已付2ms原生actuator_torque端点样本计算，非未测连续积分；requested、guarded command和actual分列。模型/控制停止、异常、接触query异常和未尝试人口完整保存。

## 自身预测、来源与成本

FR3B六条cold/learned自身轨迹分别用两个本seed冻结模型和实际保存final requests条件递推，完整H1/10/20/50/150及肩/肘q/v全部报告，不pool不同人口，不把planner尾假设与再规划actual差直接归因模型。校准范围和全2000自身起点越域摘要仅描述，不筛选、不追加fit。原门没有self veto，不事后追加；自身失配限制结论，不被独立预测通过覆盖。

| 费用上限 | FR3A | 条件FR3B |
|---|---:|---:|
| fresh trial | 6 | 12 |
| 控制调用/物理子步 | 21,000/21,000 | 36,000/36,000 |
| RLS vector/scalar提交 | 12,000/24,000 | 0/0 |
| MPC决策 | 0 | 1,200 |
| planning pair/scalar前向 | 0 | 14,580,000/29,160,000 |
| 全条件评分pair/scalar | 124,680/249,360 | 526,560/1,053,120 |

总最大57,000调用/子步、114s模拟时间；历史截至FR2为373,297控制/2,652,970子步，在线70,452+离线7,200=77,652scalar更新计算。按实际停止成本累加，不因新bank归零。规划、RLS preupdate、guard、PD、scalar dots/batch kernels、restore/snapshot、源码hash/读取、接触查询、构造/reset/forward、输出压缩及首次检查分别计账；未知内部I/O不补零。保存真实CPU/wall，仿真等待规划不证明20ms实时或同算力优势。

固定本地CPU依赖沿用Python3.10.11、NumPy2.2.6、MuJoCo3.15.0；运行时保存实际版本。没有新增外部数据、依赖、动作教师或策略检查点。源码原件/commit/协议pin、所有微步/决策/候选/labels/predictions、模型初末/更新、首stdio、付费ledger、努力/接触/停止/异常/未尝试及manifest齐全。

## 冻结与继续规则

生产路径为 `src/developmental_physics/full_request_pair_mpc.py`、`full_request_pair_development.py` 和 `scripts/develop_full_request_pair.py`；旧FR源码和协议保持。FR3A结果目录为 `results/cpu_validation/2026-10-12_full_request_pair_prediction/`，FR3B为 `.../2026-10-12_full_request_pair_control/`。新bank与所有controller/runner在任何FR3A数据前一并冻结，预测后不能换controller。

必要新检查与静态review → 干净冻结提交/推送 → FR3A首次一次 → 全预测门通过才FR3B首次一次 → 新保存证据核验/全部结果报告/累计成本 → 提交推送后立即继续active目标。技术失败与科学失败分列；保存首失败，不自动重跑、不放宽旧门。

`scientific_adoption`、`old_free_root_C4_validation`、`c4_scientific_validation`、`c4_contact_scientific_validation`、`c5_scientific_dependency_released`在本开发结果均false。FR3A/B阶段门独立命名，不覆盖FR1既有通过或FR2失败。用户持续目标仍active；若失败，关闭本冻结候选的成功依赖，做一次有证据、有限预算的下一判断，不无限扩grid或扫描参数。若通过，另冻结新留出C4综合验收；随后C5、C6、C7，不以一次报告或局部门结束目标。
