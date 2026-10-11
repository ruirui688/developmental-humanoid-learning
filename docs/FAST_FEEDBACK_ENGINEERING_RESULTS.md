# Z0：2ms原生反馈首次完整工程资格通过

Z0 从干净提交 `824749bbe8610e553be3d06ca6c9306c853153ed` 首次执行一次，
完成 1,000 zero prefix + 2,000 PD active，全部 **3,000 控制调用 / 3,000 子步** 返回。
没有控制异常、环境停止或 StudyAbort；两段末 0.4s 的肩/肘 MAE 四项均 `<=.01 rad`，
事前完整工程门通过。独立新 thin contract 零失败，复核四个新 Z0 MAE。

本次没有身体辨识、模型预测或模型控制，只说明冻结悬挂安装、经典反馈与该 seed 的任务可完整执行。
机械支撑、理想原生感觉和更高反馈频率均为公开先验；它不能验收学习收益、自由 root 真实接触 C4，
也不解除 C5 科学依赖。持续目标保持 active，阶段交付后继续独立学习协议准备。
协议见 [Z0事前冻结设计](FAST_FEEDBACK_ENGINEERING_PROTOCOL.md)，
选择依据见 [控制接口路线审阅](CONTROL_INTERFACE_ROUTE_REVIEW.md)。

## 固定条件与来源

| 项目 | 实际记录 |
|---|---|
| seed / domain | `7600 / Z_fast_feedback_suspended_fixed_upright_torso` |
| 运行状态 / wrapper exit | `completed / 0`；一次 invocation，无自动重试 |
| Python / NumPy / MuJoCo | `3.10.11 / 2.2.6 / 3.15.0`；Windows，CPU |
| 实际任务 | 1,000 zero prefix（2s）+ 2,000 PD active（4s），共6s |
| control / physics dt | `.002 / .002 s`，每控制1子步 |
| 公共经典控制 | `Kp=(64,64), Kd=(4,4)`，最终每轴 `.5 Nm`；其他六轴请求零 |
| 目标 / 研究停止 | 相对qref `.04→.08 rad`；原 `.12 rad / 1 rad/s` 阈值，active检查cadence为2ms |
| 安装 | identity upright torso 固定于世界；原最低点 + 5mm，一次安装高度赋值，无settling |
| torso 世界位姿 | `(0,0,.5957317505438554 m)`、quaternion `(1,0,0,0)`，trial内不调整 |
| 原资产与地面 | 原八轴几何/物理参数与baseline contact保持，`changes_from_asset=[]` |

独立环境仅把执行配置 `control_substeps` 从10改1，原物理 timestep `.002 s` 及模型数组保持。
PD每2ms读当前原生两轴q/v并计算请求，先clip到每轴 `.5 Nm`，再经过原角度方向guard。
它没有切换预览、增益扫描、额外速度屏障或重力补偿。
反馈/感觉计算和active研究停止检查频率增多；数值阈值保持不表示旧20ms终止语义完全等价。

prefix999 after原生q形成 `qref=(-.00422653739735379,.0167626315988532) rad`。
公开限位距离规则选择两轴正方向，两个实际目标是
`(.03577346260264621,.0567626315988532)` 与
`(.07577346260264621,.0967626315988532) rad`。
controller只消费当前目标及原生两轴q/v；接触、其他感觉、root位姿与真实动力学只诊断。

固定支撑移除6 root DOF / 7 root qpos，保留8q/8v/8actuator，改变固定支撑与有效碰撞拓扑。
安装反力没有测量，为unknown；不能称零支撑、站立学习或接触学习。
Z0与X/Y使用不同工程seed，反馈频率和研究停止检查频率也改变，
不能从Z0通过与X/Y停止识别反馈频率的因果效果。零停止本身不证明安全或风险下降。

冻结来源中，独立环境 `6,476 bytes`、SHA256
`7a731aaa02a431c7bb3f93450352f7a393979af2655b5ba6c2084a8c2d898455`；
runner `23,011 bytes`、SHA256
`34c5cfc835198f5e53bb17feaa43065c118f7fef5caa9b2dbc95681633b12bb5`；
协议 `9,430 bytes`、SHA256
`5b71ac014786ebbc464becc8579c36df906360e256d47232612ddc141b8bcee4`。
精确源码、依赖版本与首次stdio均随正式归档保存。

## 完整任务、末窗与资格

| 指标 | 保存结果 |
|---|---|
| 控制 attempts / returns / exceptions | **`3,000 / 3,000 / 0`** |
| 已确认积分 / 已保存子步 | **`3,000`**：prefix1,000 + active2,000，每次完整返回1子步 |
| 原生感觉 / 实际努力 / 固定mount | 全部3,000子步有限，固定安装确认覆盖完整人口 |
| 环境停止 / StudyAbort / failure | 全部null |
| 前段末窗active800..999 | observed200、availabletrue；肩/肘MAE `.0006295311018428831 / .00025252531693680436 rad` |
| 后段末窗active1800..1999 | observed200、availabletrue；肩/肘MAE `.0012676433238115938 / .0004689585769959476 rad` |
| 完整 / 工程资格 | 完整人口通过，四项MAE均 `<=.01 rad`，`engineering_qualification_passed=true` |

两末窗各200个完整端点，均覆盖0.4s；整trial完整后才available，没有partial排名。
200点均值属于新2ms接口的事前工程统计，不追认旧20点MAE或旧控制科学门。
root首次独立thin contract零failed，独立复核4个新Z0 MAE；没有重跑原物理或旧科学指标。
它支持本次保存契约与工程判定一致，不代表身体学习或算法科学验收。

全部保存子步及prefix末200窗口的left_arm、feet、other floor pair与正法向力事件均零观察。
floor存在不能使本悬挂任务成为真实接触控制。
`scientific_adoption`、`old_free_root_C4_validation`、`c4_scientific_validation`、
`c5_scientific_dependency_released`、`c4_contact_scientific_validation` 全部false。

参数指纹执行前后相同：
`e1fecaba209e7c55d27c768f599a3134e697f010cc464172246c55d990ce8696`。
显式physical configuration指纹执行前后相同：
`cd9f148903c64c109a9e6df863e3494a358aa00e861d2facb6ef260ff5e41704`。

## 实际努力、计算与归档

| 阶段 | 保存且努力有限的子步 | 实际全八轴 Σ\|τ\|dt，Nm·s | 实际全八轴 Στ²dt，Nm²·s |
|---|---:|---:|---:|
| prefix | 1,000 | 0 | 0 |
| active | 2,000 | `.380273295959645` | `.04576971762158434` |

active肩/肘绝对努力为 `.2720176098265791 / .10825568613306495 Nm·s`，
平方努力为 `.03497915270354165 / .010790564918042799 Nm²·s`。
prefix与active的unavailable effort均0，实际actuator torque与applied command努力一致。
努力分母覆盖全部付费子步；零prefix执行器努力不表示零机械支撑。

新增 **3,000 控制调用 / 3,000 子步**，正式累计
**256,297 控制调用 / 2,535,970 子步**；历史在线 `22,452` 与离线 `7,200` scalar更新计算保持。
PD计算2,000次；body-model forward、fit、RLS、恢复、MPC、教师及策略更新全部0。
冻结核心未独立确认的异常integration/endpoint-forward尝试、未保存端点及努力仍按unknown/下界披露；
不能把保存capture人口当成所有可能未确认计算的计数。

内部wall/CPU `2.0159694999456406 / 1.4375 s`，外层wall `3.501302600139752 s`。
内部时间不含进程启动、全局import、最终压缩/序列化/写盘；OS IO与backend import字节unknown。
source核验9读/`101,732 bytes`，Git11次查询返回`101,773 bytes`。
parameter fingerprint尝试/返回2次，另explicit physical fingerprint尝试/返回2次，费用分列。

[正式根归档](../results/cpu_validation/2026-10-12_fast_feedback_engineering/manifest.json)
保存20payload；40读/`2,240,592 bytes`、20写/`1,120,296 bytes`，无自动重试。
archive wall/CPU `.41693429998122156 / 0 s`，不含末manifest写盘；trace为`978,185 bytes`。
首次stdio、精确source、两个XML和全部逐控制/子步轨迹保留：

- [首次执行记录](../results/cpu_validation/2026-10-12_fast_feedback_engineering/execution.json)
- [原始run](../results/cpu_validation/2026-10-12_fast_feedback_engineering/raw/run.json)
- [原始metrics](../results/cpu_validation/2026-10-12_fast_feedback_engineering/raw/metrics.json)
- [原始清单](../results/cpu_validation/2026-10-12_fast_feedback_engineering/raw/manifest.json)
- [逐子步trace](../results/cpu_validation/2026-10-12_fast_feedback_engineering/raw/trace.jsonl.gz)
- [高度前XML](../results/cpu_validation/2026-10-12_fast_feedback_engineering/raw/suspended_body_before_height.xml)
- [安装后XML](../results/cpu_validation/2026-10-12_fast_feedback_engineering/raw/suspended_body_installed.xml)

首报告汇总5读/`31,855 bytes`、5JSON解析，wall `.0012329998426139355 s`、0科学重算。
本文只使用一次读取的派生摘要 `external/c4_z0_reporting_summary.json` 转录，
没有重读raw、调用检查器、模型或物理，也没有重算MAE、努力或旧门。

## 下一项与持续执行

工程通过使独立2ms学习机制候选具备准备依据；它尚未说明在线身体建模能带来控制收益。
下一项另冻结原生动作—感觉学习协议，保留 **300ms预测时距设计**，
重新规定动作语义、真实时距、辨识标签/更新、预测/规划计算与控制预算。
2ms下的300ms相当于150个基础子步，不能把旧20ms模型的H15或snapshots直接移到新接口。

cold、learned与强经典反馈须共享反馈/感觉频率、当前目标、最终权限、安装、保护和完整努力分母，
新学习预算及所有预测时距先独立冻结；未来实际力矩不得成为预测输入。
旧X1/X2、Y1/Y2及W0/V关闭路线保持，不因Z0成功重开或修改旧配方。
新的悬挂机制学习即使通过，也仍需自由root真实接触的完整双关节控制，
随后才是C5未知动力学适应、C6成熟/能力门控和C7新留出综合验收。
阶段报告、相关检查、普通提交与推送后立即继续，不把本工程报告作为持续目标终点。
