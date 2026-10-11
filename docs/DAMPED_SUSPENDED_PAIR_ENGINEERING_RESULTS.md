# Y0：共享肩肘阻尼的首次工程资格失败

Y0 从干净提交 `1ef7bbe3df016b01b47b0bea0ccc27821c0d7091` 首次执行一次。
100 zero prefix 完整、103/200 active 返回后，左肘速度 `1.1258089506362488 rad/s`
触发原 `1 rad/s` StudyAbort。完整工程门未过，Y1/Y2 关闭，没有执行身体辨识或模型控制。
第一段末窗虽然保存了 20 个端点，但完整 trial 失败使该窗不可评；第二窗没有端点。
不从部分轨迹计算 MAE、排名或声称收益，也不追加增益扫描。

协议见 [Y 事前冻结设计](DAMPED_SUSPENDED_PAIR_PROTOCOL.md)，
前序 [X0负结果](SUSPENDED_PAIR_ENGINEERING_RESULTS.md)保持原件和结论。
持续目标 active，C4 双关节完整预测/控制与自由 root 真实接触迁移仍未验收，C5–C7 后序不变。

## 固定条件与来源

| 项目 | 实际记录 |
|---|---|
| seed / trial | `7500 / Y0_seed7500` |
| 运行状态 / wrapper exit | `stopped / 0`；一次 invocation，无自动重试 |
| Python / NumPy / MuJoCo | `3.10.11 / 2.2.6 / 3.15.0`；Windows，CPU |
| 计划任务 / 预算 | 100 zero + 200 PD active；最多 300 控制调用 / 3,000 子步 |
| control / physics dt | `.02 / .002 s`，每控制 10 子步 |
| 公共经典控制 | `Kp=(64,64), Kd=(4,4)`，最终每轴 `.5 Nm`；其他六轴请求零 |
| 阻尼来源 | 肩复用已公开肘 Kd4，未扫描增益；新增经典速度反馈是控制先验 |
| 安装 | identity upright torso 固定于世界；原最低点 + 5 mm 公共算法 |
| torso 世界位姿 | `(0,0,.5949188584148503 m)`、quaternion `(1,0,0,0)`，trial内不调整 |
| 原资产与地面 | 原八轴几何/物理参数与baseline contact保持，`changes_from_asset=[]` |

前缀最后原生 q 形成 `qref=(-.004583792782270922,.017796353833440106) rad`。
公开限位距离规则为两轴选择正方向，两目标是
`(.035416207217729076,.0577963538334401)` 与
`(.07541620721772908,.09779635383344011) rad`，相对 qref 的 `.04→.08` 不变。
controller 不预览切换，仍仅用当前目标和原生 q/v；原生其他感觉、接触和 root 位姿只记诊断。

固定支撑移除 6 root DOF / 7 root qpos，torso world weld 及有效静态碰撞集合改变。
机械支撑本身提供安装能力，反力未测为 unknown，不能称零支撑或学习站立。
Y 与 X 使用不同工程 seed；本次没有匹配因果对照，不能用停止步数差识别肩阻尼的因果收益。

## 停止、末窗与资格判定

| 指标 | 保存结果 |
|---|---|
| 控制 attempts / returns / exceptions | **`203 / 203 / 0`** |
| 已确认积分 / 已保存子步 | **`2,030`**：prefix1,000 + active1,030，返回区间各10子步 |
| 最后 transition | `Y0_seed7500:202`，active102，第103个active完整区间先保存/计费再停止 |
| 最后肩/肘 q | `.052059105774279496 / .06305066380933125 rad` |
| 最后肩/肘 v | `.38696151259255285 / 1.1258089506362488 rad/s` |
| StudyAbort | 左肘速度，仍按端点 `abs(v)>=1 rad/s` 或 `abs(q-qref)>=.12 rad` |
| 环境 terminated / reason / collector failure | `false / null / null` |
| active80..99 | observed20，full trial未完成，所以 `available=false`、MAE `null`、passedfalse |
| active180..199 | observed0、`available=false`、MAE `null`、passedfalse |
| 完整 / 工程资格 | `full_100_prefix_200_active=false`、`engineering_qualification_passed=false` |

wrapper exit0 表示程序保存了停止结果，不代表工程通过。原更宽底层保护没有触发，
研究端点门已触发；不继续动作，不把研究停止降格为普通完整轨迹。
完整3,000子步固定安装门为false，同样不能从完整人口不足单独推断安装漂移。
实际物理参数前后指纹相同：
`f043434a99895d96af5b2f5996a1cd777e86dc748ea95fedc168490152b9014d`。

所有保存子步及prefix末20区间的 left_arm、feet、other floor pair 事件和正法向力事件均 **0**。
这是零接触观察，不能因floor存在宣称接触控制；接触本就不是悬挂工程门的要求。
`scientific_adoption`、`old_free_root_C4_validation`、`c4_scientific_validation`、
`c5_scientific_dependency_released`、`c4_contact_scientific_validation` 全部false。

## 实际费用与归档

| 阶段 | 保存且努力有限的子步 | 实际全八轴 Σ\|τ\|dt，Nm·s | 实际全八轴 Στ²dt，Nm²·s |
|---|---:|---:|---:|
| prefix | 1,000 | 0 | 0 |
| active | 1,030 | `1.949838328533223` | `.9441707527036306` |

active肩/肘绝对努力为 `.9489925524284429 / 1.000845776104781 Nm·s`，
平方努力为 `.45190209735670406 / .4922686553469244 Nm²·s`。
保存子步中 unavailable effort 均0，实际 actuator 与 applied command 努力一致；
零前缀执行器努力不表示零机械支撑。完整任务未完成，不能用部分总努力比较方法效率。

新增 **203 控制调用 / 2,030 子步**，正式累计
**253,297 控制调用 / 2,532,970 子步**；历史在线 `22,452` 与离线 `7,200` scalar 更新计算保持。
新增 body-model forward、fit、恢复、RLS、MPC、教师和策略更新全部0；公共 PD 计算103次。
正式构造包括共享supine/新identity两次编译，reset一次、两次reset forward。
冻结保护核心没有对异常下所有integration/endpoint-forward尝试做独立计数；
未确认尝试、未保存端点及对应努力一般保持unknown/下界。本次无控制异常，不把实际停止预算替换成完整计划。

内部wall/CPU `1.069881700212136/.609375 s`，外层wall `1.6939075000118464 s`。
内部时间不含进程启动、全局import、最终压缩/序列化/写盘；未测OS IO与backend import字节未知。
source核验8读/`101,728 bytes`，Git10查询返回`101,769 bytes`，两次参数指纹另读原资产。

[正式根归档](../results/cpu_validation/2026-10-12_damped_suspended_pair_engineering/manifest.json)
保存19payload；38读/`1,220,036 bytes`、19写/`610,018 bytes`，无自动重试。
归档wall/CPU `.25661240005865693/.03125 s`，不含末manifest写盘。
首次stdio、精确source、两个XML及全部停止前轨迹保留：

- [首次执行记录](../results/cpu_validation/2026-10-12_damped_suspended_pair_engineering/execution.json)
- [原始run](../results/cpu_validation/2026-10-12_damped_suspended_pair_engineering/raw/run.json)
- [原始metrics](../results/cpu_validation/2026-10-12_damped_suspended_pair_engineering/raw/metrics.json)
- [逐子步trace](../results/cpu_validation/2026-10-12_damped_suspended_pair_engineering/raw/trace.jsonl.gz)
- [高度前XML](../results/cpu_validation/2026-10-12_damped_suspended_pair_engineering/raw/suspended_body_before_height.xml)
- [安装后XML](../results/cpu_validation/2026-10-12_damped_suspended_pair_engineering/raw/suspended_body_installed.xml)

首报告汇总5读/`27,839 bytes`、5 JSON解析，wall `.0007565000560134649 s`、0科学重算。
本文仅一次读取派生摘要 `external/c4_y0_reporting_summary.json` 后转录，不重读raw、调用检查器或重算科学指标。
root已执行独立新thin contract，零failed，0 MAE重算；它证明保存契约一致，不能替代完整工程或科学门。

## 继续方向与不成立的结论

负结果只说明冻结 `PD64/Kd(4,4)` 与seed7500悬挂安装在原任务和速度门下未完成工程资格。
不能证明所有经典控制器不可达，也不能识别控制周期、动作限幅、角度guard或其他动力学因素的因果。
Y1/Y2关闭，原Y配方不因结果修改，不继续扫描增益或同安装拟合到通过。

下一项只做**控制时间尺度与底层保护的有限审阅**，先区分已知实现、证据支持与尚不能判断的机制。
当前未承诺新实验、采样周期或保护修订；需要新方案时，先确定依据、共享先验、任务和预算，再另冻结。
研究端点停止及原保护不能因失败放宽。阶段报告、检查、正常提交推送后继续同一active目标；
最终仍须真实接触双关节预测/完整控制、C5适应、C6成熟与C7新留出综合验收。
