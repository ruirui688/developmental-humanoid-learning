# X0：悬挂双关节首次工程资格失败

X0 从干净提交 `6319fb6fe4a847f9c5178759a057cefd4b0e82ff` 首次执行一次。
100 次零请求前缀完整，active 只完成 4/200 次；第 4 个完整控制区间返回后，
左肩速度 `1.0957066489965022 rad/s` 超过既定 `1 rad/s` StudyAbort 阈值。
完整工程资格未过，两个末 20 点 MAE 窗口均不可评估，本安装 X1/X2 关闭。
不把较少的停止交互、局部误差或可信归档解释成控制收益、效率优势或科学验收。

协议见 [X0 事前设计](SUSPENDED_PAIR_DOMAIN_DESIGN.md)。后续少量辨识及残差控制的
[X1/X2 配方](SUSPENDED_PAIR_LEARNING_PROTOCOL.md)保持原样，本次没有执行学习。
持续目标保持 active；原自由 root C4、C5 科学适应、C6/C7 仍未完成。

## 首次来源与固定条件

| 项目 | 实际记录 |
|---|---|
| seed / trial | `7400` / `X0_seed7400` |
| 运行状态 / wrapper exit | `stopped` / `0`；一次 invocation，无自动重试 |
| Python / NumPy / MuJoCo | `3.10.11 / 2.2.6 / 3.15.0`；Windows，CPU |
| 任务与预算 | 100 zero prefix + 200 PD active；计划最多 300 控制调用 / 3,000 子步 |
| 控制 / 物理步长 | `.02 s / .002 s`，每控制 10 子步 |
| 公共经典控制 | `Kp=(64,64), Kd=(0,4)`，旧增益开发先验，两轴最终权限各 `.5 Nm` |
| 其余六轴 | 原被动关节保留，全部请求零 |
| 安装 | torso 固定于世界，identity quaternion；原最低点 + 5 mm 算法，只赋高度一次 |
| 固定 torso 位姿 | `(0,0,.5952706017427153 m)`、quaternion `(1,0,0,0)` |
| 原资产/接触参数 | baseline 地面与参数保持，`changes_from_asset=[]` |

前缀最后原生位置形成 `qref=(-.005175192229041098,.020363383411416386) rad`。
公共限位可用距离规则对两轴都选正方向，两个目标分别为
`(.0348248077709589,.06036338341141639)` 与
`(.0748248077709589,.10036338341141639) rad`，即相对 qref 的 `.04→.08`。
本次没有到达第二目标段，也没有使用目标切换预览。

固定支撑消除了 6 个 root 自由度、7 个 root qpos，并改变有效静态碰撞集合及动力学反馈。
它提供机械安装能力，安装反力没有测量，记为 unknown；不能称零支撑、站立学习或原自由 root 域修复。
原生 q/v、当前目标及公共 PD 选择动作；接触、root 世界位姿及真实动力学只作诊断。

## 停止与工程门

| 指标 | 结果 |
|---|---|
| 返回控制调用 / 已确认积分子步 | **104 / 1,040**：100 prefix + 4 active，全部返回区间各 10 子步 |
| 控制调用异常 / collector failure | `0 / null` |
| 环境终止 / 环境 reason | `false / null`；停止来自更严格的研究端点门 |
| 最后 transition | `X0_seed7400:103`，完整 10 子步先保存、计费，再停止 |
| 最后肩/肘 q | `.03617395420844502 / .04129557435838188 rad` |
| 最后肩/肘 v | **`1.0957066489965022`** / `-.3954140496069138 rad/s` |
| StudyAbort | 肩速度；阈值仍为 `abs(v)>=1 rad/s` 或 `abs(q-qref)>=.12 rad` |
| active80..99 与 180..199 | 两窗 observed_count 均 0，`available=false`、MAE `null`，均未通过 |
| 完整工程门 | `full_100_prefix_200_active=false`，`engineering_qualification_passed=false` |

要求覆盖全部 3,000 子步的固定安装门也为 false；这是完整人口未形成的结果，
不能据该字段单独断言安装发生漂移。实际物理参数前后指纹相同：
`1aa739b7217ab8be97cffb5d599b118d70921cf8364822d605265b857afc91f1`。
不能用前 4 个 active 的部分排名替代完整任务，也不补执行到通过。

保存的 1,040 子步及前缀最后 20 区间中，left_arm、feet、other 三类 floor pair 事件及
有限正法向力事件全部为 **0**。保留地面几何不等于产生了接触，更不能声称本次学会接触控制。
接触本就不属于非接触 X0 工程通过条件；本次失败由完整控制/研究停止门决定。

`scientific_adoption`、`old_free_root_C4_validation`、`c4_scientific_validation`、
`c5_scientific_dependency_released`、`c4_contact_scientific_validation` 全部保持 false。

## 实际费用与证据保存

| 阶段 | 已保存且努力有限的子步 | 实际 Σ\|τ\|dt，Nm·s | 实际 Στ²dt，Nm²·s |
|---|---:|---:|---:|
| prefix，全部八轴 | 1,000 | 0 | 0 |
| active，全部八轴 | 40 | `.07438647108079902` | `.03637436632447757` |

active 肩/肘绝对努力分别为 `.04000000000000003 / .03438647108079899 Nm·s`，
平方努力分别为 `.020000000000000014 / .016374366324477557 Nm²·s`。
已保存子步中的 unavailable effort 计数为 0，实际 actuator 努力与 applied command 努力一致。
这里的零前缀执行器努力不能解释成零机械支撑或零外部负担。

本次新增 **104 控制调用 / 1,040 子步**；正式物理累计为
**253,094 控制调用 / 2,530,940 子步**。历史在线 `22,452` 与离线 `7,200` scalar 更新计算不变。
新增 body-model forward、fit、恢复、RLS、MPC、教师及策略更新全部为 0；公共 PD 计算为 4 次。

正式构造包含共享 supine 和新 identity 两次模型编译，reset 一次、两次 reset forward。
完整的已确认积分与保存端点计账，不声称冻结保护核心对异常中的全部 integration/forward 尝试都可观测。
本次没有积分/forward/诊断异常；一般未确认部分仍按协议记 unknown/下界，不补零。
内部 wall/CPU 为 `.8093904999550432/.359375 s`，外层 wall 为 `1.199638199992478 s`。
内部时间不含进程启动、全局 import、最终序列化/压缩和写盘；OS IO 及 backend import 字节未知。
source 核验 8 读 / `97,803 bytes`，Git 10 次查询返回 `97,844 bytes`；两次参数指纹另读原资产。

[正式根归档](../results/cpu_validation/2026-10-12_suspended_pair_engineering/manifest.json)
保存 19 个 payload：首次 stdio、wrapper、8 个精确 source、两份派生 XML、run/metrics、全部停止前轨迹。
归档为 38 读 / `743,602 bytes`、19 写 / `371,801 bytes`，无自动重试；
归档 wall/CPU `.269598999992013/.046875 s`，不含末 manifest 写盘。
入口与原件：

- [首次执行记录](../results/cpu_validation/2026-10-12_suspended_pair_engineering/execution.json)
- [原始 run](../results/cpu_validation/2026-10-12_suspended_pair_engineering/raw/run.json)
- [原始 metrics](../results/cpu_validation/2026-10-12_suspended_pair_engineering/raw/metrics.json)
- [逐子步 trace](../results/cpu_validation/2026-10-12_suspended_pair_engineering/raw/trace.jsonl.gz)
- [高度赋值前 XML](../results/cpu_validation/2026-10-12_suspended_pair_engineering/raw/suspended_body_before_height.xml)
- [安装后 XML](../results/cpu_validation/2026-10-12_suspended_pair_engineering/raw/suspended_body_installed.xml)

报告来源的首汇总为 5 读 / `27,746 bytes`、5 JSON 解析，wall `.000740300165489316 s`，0 科学重算。
本文仅一次读取其派生摘要 `external/c4_x0_reporting_summary.json` 后转录，不重读 raw、调用检查器、
重算旧门或执行模型/物理。独立 thin contract 首次零失败（root 已执行），
只证明证据契约一致，不能把它解释成完整工程门或科学门通过。

## 接着验证什么

本负结果只否定当前固定安装与 `PD64/(Kd0,4)` 在既定速度/完整任务门下的工程资格。
它不能证明所有控制器都不可达，也不能从一次轨迹识别接触、支撑、阻尼或身体模型误差的因果。
X1/X2 关闭，原协议和残差 controller 不因本次揭晓结果修改；没有追加探索、辨识或拟合。

下一独立 Y 候选仅把公共经典肩 `Kd=0` 改为已公开肘的 `Kd=4`，不改变安装、目标、权限、
研究阈值或原保护，不扫描增益。增加经典速度反馈是新控制先验，不是身体学习成果；
其依据须独立科学静态审阅，并另冻结精确源码、任务、seed 与有限预算，才首次执行。
它可能仍失败；本报告不承诺 Y 通过，也不将它作为 X0 的成功补跑。
阶段报告、检查、正常提交推送后继续持续目标，最终仍须自由 root 真实接触控制及 C5–C7。
