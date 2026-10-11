# C4-C 肩—肘身体模型协调：冻结开发协议

2026-10-11。在本批真实物理执行前固定；实现和独立审计通过相关检查、提交推送后，从clean源码一次执行。当前尚无本批真实结果。development0/1/2已见，不称未见评价。

固定 supine / 原生 j0 left_shoulder + j1 left_elbow；development0/1/2 按该顺序。每 trial 独立 reset，原 SeedSequence 派生；100 个真实零请求 prefix 从自己的原生 8D encoder 和公开限位确定两个 qref/方向，不裁略负的肘 qref。其余六轴请求恒零，各目标轴权限 .5 N·m，baseline 接触、20 ms 调用/2 ms 子步与原保护不改。只读当前 q/v 和 step 前已知请求；未来实际力矩、接触、隐藏参数只诊断。

同一个 calibration 的 400 个完整 active 转移按固定顺序 shared 给两个独立 cold 模型：diagonal_hinge5（每 head 自己的 v/q-qref/u/h(u)/1）及 coupled_hinge9（每 head 的 v0/v1/q0-qref0/q1-qref1/u0/u1/h(u0)/h(u1)/1）。theta 初始仅 own v=1、own u=.02，其余0；P=100I，lambda1，hinge.25，endpoint Euler；单模型两个 heads 原子提交，两个模型间不是原子事务。先 diag 后 coupled，若后者失败保留前者已提交更新；所有 finally 以真实 snapshot vector/scalar counts 计账，不以“抛错”假定0。partial/prefix 不更新，所有评价冻结，不复用肩/肘参数或真实20–22。

正式冻结前的开发选择：已归档单肘short校准5步脉冲完整，7步full预测三seed停止；据此 root 明确将尚未执行的pair 7正/3零/7反/3零草稿改为 **5正/5零/5反/5零**。此前pair草稿没有真实执行，成本0；不改单肘档案，不把本选择称为独立验证或安全保证，新序列仍可能失败。

明确的固定命令：20个20步block，每block5正/5零/5反/5零。block0–4仅j0、5–9仅j1，幅度各 [.125,.25,.375,.5,.25]；block10–14两轴同向，15–19两轴反向，幅度仍各 [.125,.25,.375,.5,.25]。两轴各乘自身固定方向 s；反向指相对各自 s 的第二轴符号取反。400命令只依 index/s，不反馈。每轴完整计划请求绝对努力0.9 N·m·s、平方努力 .31875 N²·m²·s；合计1.8/.6375，实际另计。

共同 low/full 各100 active：五个20步block，同5正/5零/5反/5零；low幅度[.25]*5，full[.125,.25,.375,.5,.375]。向量形状依次 [(1,0),(0,1),(1,1),(1,-1),(1,1)]，各轴乘自身 s。nominal/diag/coupled/persistence 在同一真实轨迹评分，不按模型重采。

固定每seed顺序：calibration500、prediction_low200、prediction_full200、nominal_mpc300、diagonal_mpc300、coupled_mpc300、combined_pd300、zero_torque300；均含100 prefix。每seed8trial/2400调用/24000子步；三seed24trial/**7200调用/72000子步/4800 scalar RLS**（400×2heads×2models×3），模型 vector 更新总数2400。phase prefix2400/24000，calibration1200/12000，prediction600/6000，control3000/30000；144s模拟时长。最初文字提案的7500预算是求和错误，合成完整计划在冻结前发现并改正，未添加真实动作凑数。实际失败成本/partial/停止按真实相加。

五种控制各200 active，两轴当前目标前100为qref+s*.04、后100 qref+s*.08，无切换预告；不可行不裁。PairMPC 原H15/每轴9候选/81向量候选、原逐轴成本相加、公共预测界、零回退和精确 tie-break 不改。组合 PD 肩64/0、肘64/1仅是两个单轴调优结果的组合，没有双轴调优，不能称双轴 strong baseline；请求分别 clip(kp*(target-q)-kd*v,-.5,.5)。zero 全零同目标评分。

所有active每个返回端点任一轴 abs(q-qref)>=.12 或 abs(v)>=1 即 StudyAbort，等值触发，prefix只原环境保护。study/env/error 独立保存，环境主reason优先；完整 terminal 可update/score，末计划端点stop也不complete；partial保存已知target原始两轴误差但不score/update。cal失败只阻塞两prediction与diag/coupled控制；nominal/组合PD/zero自身付费prefix独立继续。普通失败继续既定trial；中断/IO/trace写失败fatal、余下planned blocked，不补跑。

验收分开输出，阈值由 root 明确冻结：diag与coupled各自五trial模型贡献门（cal、两prediction、nominal、本模型控制）：全三seed完整无任何stop/error/非法非有限，low/full每轴速度RMSE逐seed<=.8nominal；每seed每轴tracking严格优于nominal，各轴三seed原始RMSE均值至少降低20%，200×2联合tracking每seed也严格改善，三seed联合原始RMSE均值至少降低20%。coupled对diag的六trial增量门：前述必要trial及两个learned控制完整，coupled贡献门须通过，low/full每轴预测及tracking逐seed不劣于diag，联合tracking逐seed<=diag且三seed原始均值改善>=5%，实际绝对/平方努力三seed均值各<=1.05diag。组合PD比较对diag与coupled分别输出：本模型贡献门须先通过，六个必要trial完整；每seed每轴及联合tracking均不劣于组合PD，三seed联合原始RMSE均值至少低5%，双轴实际绝对及平方努力均值各不超过1.05倍PD。这个数值门独立报告，不称超越双轴调优强基线。全部8trial矩阵完整独立输出。零分母百分比未定义；tracking均值分母0则改善门失败；努力baseline0仅允许candidate0。不按结果改门。

原生8D观测、8D请求/实际子步历史、两个模型共享transition ID、所有更新proposal/真实最终snapshot/失败记录、已返回未存行、未返回paid子步、完整/partial评分端点全部归档。请求努力finally以paid子步计，实际努力只取returned历史；缺失或invalid历史标下界/未知/missing计数不补零。规划成功及失败分别计attempts/完整标记，下界与未知scalar count保留；CPU/离线审计/内部数学预算与物理预算分开。

输出所有逐轴及联合tracking/prediction、两目标段/计划末20端点（80–99、180–199）的返回/完整/缺失与有符号误差；cal in-sample及各配对控制的一步原生误差、2/5/15步自由递推/路径、支持q/v域外/nearest、全身体full/prefix/cal/pred/control子步力峰/冲量、穿透、动能、8轴速度、屏蔽/限位/饱和/回退/停止由独立审计重算。包络不称安全集，努力不称机械能或风险下降；未晋级/零动作/截短失败不能算优势。

原字节源码ZIP/SHA、clean/source commit、协议、NumPy/MuJoCo/Python/CPU、GPU=null、全成本和失败均保存。标准库独立审计不得导入runner/模型或将8D重新排序；完整更新轨迹按原生j0/j1重算，全部失败不丢。此批只开发多关节局部贡献，不证明全身技能、未见seed/扰动泛化或真机。上一批单肘实际为5292调用/52920子步/900更新，保留全部6次停止与失败门，不补跑、不换关节；正式累计基点 **221663控制/2216630子步/10800RLS**，本批若完整为 **228863/2288630/15600 scalar RLS**。按实际累计，不用计划替代执行；未来独立新bank另冻结。实现、审计和协议相关检查完成后提交推送，从clean一次采集、一次首次审计，归档全部成功与失败后继续未知动力学和成熟门控。


```powershell
$env:PYTHONPATH = 'src'
external/cpu_physics_env/Scripts/python.exe -m developmental_physics.pair_frozen_validation `
  --output external/pair_body_20261011_development `
  --protocol docs/PAIR_BODY_DEVELOPMENT_PROTOCOL.md
```

相关：[单肘负结果](ELBOW_BODY_DEVELOPMENT_RESULTS.md)、[双模型核心](../src/developmental_physics/local_pair_model.py)、[持续目标](CONTINUOUS_EXECUTION_PLAN.md)。
