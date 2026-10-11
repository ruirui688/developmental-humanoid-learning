# Z1/Z2：2ms身体辨识与20ms规划的事前机制协议

Z0 从 clean `824749bbe8610e553be3d06ca6c9306c853153ed` 完成3,000控制/3,000子步、零停止及零fit，首次工程资格通过。这是高频经典反馈的受支撑可达性，不是身体学习；本协议在任何新的Z1学习数据产生前独立确定。生产入口、模型、controller、必要新纯检查及精确来源必须先冻结、正常提交推送；controller也必须在读取Z1结果前冻结。工程通过不自动继承X/Y科学门或旧snapshot。

## 架构、共享条件与明确新增费用

唯一架构为**2ms原生转移模型、每20ms一次残差MPC、实际PD每2ms重算**。模型预测一个2ms内恒定的已知最终请求；target/held delta用于controller生成请求，不直接加入身体特征。cold/learned/PD/zero共享 [Z0安装与动作接口](FAST_FEEDBACK_ENGINEERING_PROTOCOL.md)：固定upright torso、原八轴/电机/资产、同2ms物理和反馈、最终每轴 `.5 Nm`、其余六轴请求零、原生感觉及基础保护。left_arm/feet/other接触与机械反力只作诊断，固定支撑和PD已有能力均披露。

开发seeds唯一 **7701、7702、7703**。公开docs/README/AGENTS/src/scripts/tests整数字边界搜索一次无匹配，未读raw，不能保证未公开用途。三个seed完整报告，不作为最终未见bank；每条fresh对象只reset一次，原初态/jitter/最低点5mm安装算法不变。同seed各轨迹安装XML/物理配置及prefix qref逐轴差须 `<=1e-12`；不符合付费失败，不改参考或重装到通过。

prefix仍是1,000次零请求/2s，只走基础保护；qref取完整prefix999 after。方向按公共限位余量，平手正；目标margin `.03rad`，不可行不clip或试反向。active每完整2ms后原StudyAbort `abs(q-qref)>=.12rad` 或 `abs(v)>=1rad/s`，等号停止；环境reason另记。终端区间先付费/保存，不纠正、补跑或partial排名。

相同真实时间不表示相同计算预算：相比旧20ms配方，校准提交与反馈调用增加10倍，主预测/规划前向也增加10倍。2ms连续标签高度时间相关，不能当独立样本数增加10倍；原P100I/lambda1的数字不变但更多更新改变先验相对权重。仿真会等待CPU计算，2ms仿真接口和20ms决策节奏不证明CPU实时deadline或真机可执行。

独立生产路径为 `fast_feedback_pair_model.py`、`fast_feedback_pair_mpc.py`、`fast_feedback_pair_development.py`（均在 `src/developmental_physics/`）和 `scripts/develop_fast_feedback_pair.py`。不修改或恢复冻结X/Y实现，科学入口另名、另source/配置/预算，禁止未授权的物理开关。

## 唯一2ms初始化与模型信息

原PairBodyModel构造器拒绝dt非 `.02`，仅改变position Euler字段不会自动修正velocity prior。因此使用独立adapter：从**未学习的公开generic20ms初始化**构造基准，再固定新dt `.002`；velocity head用

`Theta_2ms = E + (.002/.02)*(Theta_generic_20ms - E)`，

其中E只复制本轴当前v。由此本轴v identity保持1、generic own请求项 `.02 -> .002`、原零cross/q/hinge/constant保持零。这是假定generic速度增量按时间一阶缩放的新增初始化先验，不是测得的动力学或已证明的2ms模型。两个组共享同一处理，不加载X/Y/D等learned snapshot。

原coupled_hinge9、公开角度KnownAngleGuard、hinge `.25`、零cross prior、P100I、lambda1及原子两head RLS保持；每seed18系数。模型输入仅当前自身两轴q/v和已知最终请求，下一真实v为自监督标签；位置输出为 `q_next=q+.002*v_next`。不读未来真实力矩、接触、root姿态、真实动力学或未知未来状态，不虚构previous_v。新clone/snapshot必须保留2ms配置、初始化身份、权重/协方差和更新数，不能回落到拒绝2ms的旧clone构造或旧时间语义。

## Z1：固定时间脉冲校准与独立预测

每seed两条fresh轨迹，顺序校准、独立预测。校准为1,000zero+**4,000active**，共10s；PD目标固定qref，每2ms先计算并clip公共PD，再加当前已知pulse，最终clip `.5`。20个0.4s块，等价每块20个20ms macro slots、每slot10个微步；四组依次肩/肘/同向/反向，各五块幅度 `.125/.25/.375/.5/.25`。每块macro slot0全10微步为正pulse，slot10全10微步为反pulse，其余零。幅度/时长/相位不得由新数据调整。

只在完整且未停止的active transition原子更新两head；prefix、不完整、停止端点不更新，但付费数据保留。learned只在校准更新；cold同一新初始化冻结，校准后两者都冻结。RLS失败不得提交单head、偷偷恢复或再试同样本。全部seed/失败人口保留；缺少完整校准或独立预测时该seed不可验收，不用较少提交数声称效率优势。

独立预测为1,000zero+**1,000active**，共4s，无更新。五个0.4s块，方向 `(1,0)/(0,1)/(1,1)/(1,-1)/(1,1)`，幅度 `.125/.25/.375/.5/.375`；macro slot1正、slot9反，各保持10微步，其余零。PD目标仍qref。保存全部1,000微步原生轨迹/请求，未来保存request仅为离线条件输入，未来真实q/v只评分。

主评分origin为active起点状态 `0,10,20,...`；一个origin从对应微步请求前q/v出发，cold/learned各自递推，禁止用未来真值替换中间状态。H和完整origin人口为：

| 微步H | 真实时距 | 独立origin数 | 控制自身origin数 |
| --- | --- | ---: | ---: |
| 1 | 2ms，仅报告 | 100 | 200 |
| 10 | 20ms | 100 | 200 |
| 20 | 40ms | 99 | 199 |
| 50 | 100ms | 96 | 196 |
| 150 | 300ms | 86 | 186 |

H1也仅使用同macro origins，不使用全1,000/2,000微origin，不新增veto。原物理时距科学门保持：H10v与H150q每seed两轴严格改善，各轴三个seed**原RMSE均值**至少改善20%；H150v和H20/H50 q/v每seed两轴均不劣。H10q与原生H1全部报告，不额外放宽或追认门。全人口完整且finite才判门；基线零/非finite不可百分比评估，不排有限子集。

Z1任一所需完整/预测门未过即关闭Z2。三seed负结果/不可用原因都报告，不增加校准、改脉冲、特征、prior、频率或门到通过。技术失败与科学失败分清，均保存首次证据，不自动复跑。

## Z2：宏决策、微反馈的匹配完整控制

只有Z1所需完整轨迹和全部原预测门通过，且controller早已冻结才执行。每seed依次四条fresh轨迹：cold+MPC、learned+MPC、公共PD、zero；每条1,000zero+2,000active/6s。active前1,000为方向×`.04`、后1,000为方向×`.08`，均相对各自qref。全程无模型/增益/gate更新，全部组共享反馈、最后权限、支撑、停止和努力分母。

MPC在active0、10、20…1990决策，每模型控制轨迹200次。H150微步=300ms，81首残差为每轴 `[-.125,.125]` 的9点笛卡尔网格。每candidate独立用自身预测q/v计算并clip公共PD，再加残差再clip最终权限：首10微步held delta固定，余140微步delta零；每微步重新预测其自身PD请求。目标只当前值，未来切换不预告。

实际执行也每2ms用新原生q/v重算公共PD、加同一个held delta并clip；只执行前10微步，然后观察并重新规划。不能将planner算出的首扭矩恒持20ms，也不能用真实未来q/v刷新candidate；途中停止立即结束，不额外完成剩余微步。

全部candidate不可行时采用**literal zero request模式**，后10微步请求零；它与held delta零时继续PD不同。fallback/残差模式在结果中明确保存，不把缺计划伪装成PD候选。clip后重复候选仍全部尝试/计费，沿用完整请求与signed residual的固定平手规则。

无discount。每微步runningcost使用原权重×`.1`：position `.1`、velocity `.0002`、effort `.000002`；全部effort为最终完整request而非residual。首change只计一次，权重 `.00002`不缩，比较首完整请求与**上一实际已知微步最终request**，不使用actual actuator force或上macro起点旧请求。此时间权重使150个2ms段与15个20ms段的阶段代价处于相同尺度，并非由新数据调权。

保留原forecast radius `.15rad`、velocity `1.5rad/s`、tolerance/targetmargin `.03rad`等公开配置，预测可行性每微步检查。它与真实StudyAbort `.12/1`不同；更密forecast veto也改变内部观察频率，不能声称该模型可行性是实际速度安全证明。真实研究阈值不改变。

先验收模型贡献：cold/learned所有seed完整2,000active及实际努力完整；每seed joint与两axis RMSE严格改善，三seed原joint/各axis均值各至少改善20%；两轴合计actual absolute和squared effort均值各 `<=1.05*cold`。

贡献门通过后验收强经典门：所需PD全部完整，每seed joint/axis不劣于PD，原joint均值至少改善5%，两种actual effort原均值各 `<=1.05*PD`。RMSE零基线不产生百分比优势，effort零基线须candidate也零。zero组停止原样报告，不partial排名，不将低步骤数或零停止当效率/安全证据。

控制自身条件预测采用上表macro origins，6条模型控制轨迹分别由本seed两个冻结模型离线评分。与Z1共同独立预测、planner自身PD预测分开；未来实际requests只离线条件输入。工程、预测、控制模型贡献及强PD门分别报告，不互相代替。

## 确切计划预算与证据

| 费用 | Z1上限 | Z2上限 |
| --- | ---: | ---: |
| 控制调用 / 物理子步 | 21,000 /21,000 | 36,000 /36,000 |
| 在线提交 | 12,000vector /24,000scalar | 0 |
| 实际actor的PD反馈上限 | 15,000 | 18,000 |
| MPC decisions | 0 | 1,200 |
| 规划前向pair /scalar | 0 | 14,580,000 /29,160,000 |
| 主时距条件评分pair /scalar | 124,080 /248,160 | 524,160 /1,048,320 |
| 原生H1另报告pair /scalar | 600 /1,200 | 2,400 /4,800 |
| 全部离线评分pair /scalar | 124,680 /249,360 | 526,560 /1,053,120 |

Z1校准三条各5,000、独立三条各2,000；Z2十二条各3,000。actor PD为Z1的 `3*(4,000+1,000)`，Z2的 `6MPC traces*2,000+3PD traces*2,000`；prefix和zero不算PD，planner内部预测PD另计。主评分公式为 `2models*3seeds*sum(origins*H)=124,080`；自身为 `6traces*2models*sum(origins*H)=524,160`。规划为 `1,200*81*150`；若candidate提前拒绝，实际前向计原数，不预填上限、不将更少失败计算当优势。原生H1费用不混入原科学时距。

Z0+有条件Z1+有条件Z2为60,000调用/60,000子步/120s；科学新增最大57,000/57,000，Z0已付3,000/3,000另列。旧X/Y及此前累计费用保留，不归零。没有GPU、教师/任务策略恢复、策略梯度或追加离线fit；online RLS、内部preupdate前向、clone/snapshot、规划、PD反馈、条件评分各记实际费用。

保存全部逐seed配置/源码commit/依赖、首次stdio、原始微步及宏决策、请求/实际力矩、停止/异常、模型前后权重/协方差/更新时间、全部origin预测与真实标签、候选计数/可行性/代价/fallback/选中预测轨迹。实际absolute/squared effort按全部付费2ms子步计，不只成功段/窗口。已确认积分、保存capture、观测/PD/保护、source读/hash、构造/reset和压缩/写盘分项；未确认尝试、未保存端点和努力为unknown/已知下界。

## 判定与继续方向

本协议是新反馈接口下的悬挂机制**开发验证**；即使全部通过，也只支持共享公开身体、固定支撑、理想感觉和经典PD下的局部身体模型贡献，不代表小孩从零技能、接触控制、站立、适应、真机或公平同计算预算优越性。新增初始化/更新频率/模型时距/规划计算都须在结果中披露。

没有科学结果前不开放新采样；每阶段失败封存并关闭后续依赖，不同bank/剂量/频率/参数扫描到通过。完整自由root接触C4、C5变化适应、C6成熟与C7新留出依旧需要独立设计验收，旧域/adoption flags不由Z1/Z2开发门改成true。报告、必要检查和正常提交推送后继续最早未过门，持续目标不以局部报告为终点。

## 本次准备范围

本协议作者只用已经冻结的Z接口文档、主代理转录的Z0工程事实、PD/model/planner代理缓存的API信息及新的计划整数算术；未读任何source正文、旧raw/metrics，也未调用模型/物理/fit/RLS/装配/实验import或测试。一次公开seed搜索与gitstatus是只读。source约束和adapter实现由对应代理另静态review；正文格式/链接、最终bytes/SHA及预算receipt另保存，不以设计当科学结果。
