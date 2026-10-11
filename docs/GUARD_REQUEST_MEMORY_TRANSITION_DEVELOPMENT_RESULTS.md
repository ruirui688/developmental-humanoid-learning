# C4 P：单个已知请求记忆转移开发结果

P 已首次完成固定开发评估，**P→K 与 P→D 两门均失败**。H1 速度在每个 seed 的两轴均小幅改善，
但各轴逐 seed 相对改善均值只有 2.879%–3.350%，未达 20%。H15 位置在所有 seed 的两轴均退化，
H2 速度、H5 位置/速度和 H15 速度也在所有 seed 的两轴均退化。P 不进入控制，
scientific_adoption、C4 验收和 C5 依赖解除均为 false；C4 仍是最早未验收阶段，持续目标 active。

本报告只摘录已保存 run、metrics、根 manifest 和 execution；不读取参数、原始 trace 或预测路径，
不调用模型，不重算误差、门或拟合。表中仅将保存的 RMSE 和相对改善格式化，原精度留在 metrics。

## 固定候选与首次身份

协议见 [P 开发协议](GUARD_REQUEST_MEMORY_TRANSITION_DEVELOPMENT_PROTOCOL.md)。
唯一候选保留 K 的原尺度 Phi29/x22、lambda=.01、公开 prior、KnownAngleGuard、hinge 和
previous_v 语义，在 C sparse400 的保存设计上追加合法同 trial 上一请求两轴：

```text
Phi31 = [saved_K_Phi400x29, legal_past_requested_u0/u1]
W31x22 = solve(Phi31.T @ Phi31 + .01 I31, Phi31.T @ saved_K_Delta400x22)
```

新增请求使用已知 requested_torque 原值，无额外 clip、过去 guard 投影或实际力矩。
首训练行和 prediction origin0 分别取各自 prefix99；递推后推进本步旧已知请求和旧 current v，
22 个状态输出全部自身递推。C 原生端点只用于历史连续性、prefix 身份及预测评价；
训练标签与原29设计直接恢复自 K。没有 RMS、lambda/lag/权重扫描、新数据、K 重拟合或 D 更新。
O 的条件误差观察只提供候选动机，没有识别请求记忆的因果作用。

正式首次来自 clean exact commit
`8315e610e69194f236fc8e3ba4381be1bddb4144`，运行保存状态 completed，
execution returncode=0、subprocess_invocations=1、automatic_retry=false、stderr_bytes=0。
源代码 SHA256 为
`cae9a9fdd4dd2c1563f2163e40bd8edcb8906ce2743e5c90960d5fa20d50491c`（30,497 bytes），
协议 SHA256 为
`cbb04927f77fc43cc0539b7acc23c4a9e9366866e867d1963cd2f86cb658375a`（6,203 bytes）。
run 记录 clean committed bytes verified=true。C/D/K 原件 commit 分别为
`5ea8df42b09588845760daf0dc1f270aef2a87f1`、
`f7710c7b048dccab3e436d1fa16432f881a35992`、
`b46c6d37fddc8e6534384168fb76663bc2c5236c`。

正式运行环境为 Python 3.10.11、NumPy 1.26.4、Windows-10-10.0.26200-SP0；
原 C metadata 记录 MuJoCo 3.15.0 / NumPy 2.2.6，这些是来源环境，本次 P 没有运行物理。
K22/D11 三个 seed 的前后 fingerprint 在 run 中保持一致。

原件与执行身份见：
[run](../results/cpu_validation/2026-10-12_guard_request_memory/raw/run.json)、
[metrics](../results/cpu_validation/2026-10-12_guard_request_memory/raw/metrics.json)、
[根 manifest](../results/cpu_validation/2026-10-12_guard_request_memory/manifest.json)、
[execution](../results/cpu_validation/2026-10-12_guard_request_memory/execution.json)。

## 固定完整分母与全部 seed RMSE

seed0/1/2、P22/K22/D11、H1/2/5/15 固定每组 100/99/96/86 原点。来源每 seed calibration_sparse
400 条、prediction 100 条。metrics 保存 576 个固定通道组；两门
all_fixed_usable_counts=true、evaluated=true，全部固定组完整，不使用部分轨迹排名。
协议固定布局为 3,429 个 predictor/origin/horizon 记录。

下表公开受控两轴全部 seed、方法和时距；q0/v0 为轴0（肩），q1/v1 为轴1（肘）。
q 的通道是 q−qref，误差单位仍为 rad，v 为 rad/s；RMSE 四舍五入到小数点后9位。
H1 q 只描述，不纳入门。P/K全部22状态通道的保存指标仍保留在原 metrics，本报告不重算或筛选为替代门。

### H1：每组固定 100 个原点

| seed | predictor | q0 RMSE (rad) | q1 RMSE (rad) | v0 RMSE (rad/s) | v1 RMSE (rad/s) |
|---:|---|---:|---:|---:|---:|
| 0 | P22 | 0.000688183 | 0.001375882 | 0.054010573 | 0.112287729 |
| 0 | K22 | 0.000711214 | 0.001417768 | 0.055610966 | 0.115630578 |
| 0 | D11 | 0.001194290 | 0.002420294 | 0.055843602 | 0.115797919 |
| 1 | P22 | 0.000678112 | 0.001372847 | 0.054118764 | 0.112053263 |
| 1 | K22 | 0.000701544 | 0.001415370 | 0.055731662 | 0.115451769 |
| 1 | D11 | 0.001198059 | 0.002418703 | 0.056068842 | 0.115767920 |
| 2 | P22 | 0.000689010 | 0.001377204 | 0.054032422 | 0.112265472 |
| 2 | K22 | 0.000711489 | 0.001417769 | 0.055625580 | 0.115590937 |
| 2 | D11 | 0.001194351 | 0.002418888 | 0.055869791 | 0.115779545 |

### H2：每组固定 99 个原点

| seed | predictor | q0 RMSE (rad) | q1 RMSE (rad) | v0 RMSE (rad/s) | v1 RMSE (rad/s) |
|---:|---|---:|---:|---:|---:|
| 0 | P22 | 0.001850718 | 0.003727085 | 0.067349951 | 0.137975106 |
| 0 | K22 | 0.001873874 | 0.003767244 | 0.066273207 | 0.136204897 |
| 0 | D11 | 0.002453131 | 0.004936414 | 0.065477904 | 0.134616538 |
| 1 | P22 | 0.001838802 | 0.003722930 | 0.067469530 | 0.138129958 |
| 1 | K22 | 0.001861564 | 0.003763361 | 0.066367551 | 0.136317182 |
| 1 | D11 | 0.002458265 | 0.004937801 | 0.065649620 | 0.134788989 |
| 2 | P22 | 0.001851911 | 0.003727626 | 0.067393141 | 0.137962291 |
| 2 | K22 | 0.001874308 | 0.003765969 | 0.066316429 | 0.136191497 |
| 2 | D11 | 0.002453995 | 0.004934560 | 0.065518783 | 0.134602265 |

### H5：每组固定 96 个原点

| seed | predictor | q0 RMSE (rad) | q1 RMSE (rad) | v0 RMSE (rad/s) | v1 RMSE (rad/s) |
|---:|---|---:|---:|---:|---:|
| 0 | P22 | 0.003486369 | 0.007056537 | 0.070142186 | 0.146734250 |
| 0 | K22 | 0.003430910 | 0.006959007 | 0.067027612 | 0.141194755 |
| 0 | D11 | 0.003381519 | 0.006915544 | 0.067411819 | 0.141169834 |
| 1 | P22 | 0.003502692 | 0.007070526 | 0.070196062 | 0.146693032 |
| 1 | K22 | 0.003445047 | 0.006971666 | 0.067026118 | 0.141056866 |
| 1 | D11 | 0.003407732 | 0.006918618 | 0.067482514 | 0.141156500 |
| 2 | P22 | 0.003491646 | 0.007063020 | 0.070194100 | 0.146745970 |
| 2 | K22 | 0.003435587 | 0.006963838 | 0.067070710 | 0.141194171 |
| 2 | D11 | 0.003385358 | 0.006919020 | 0.067436202 | 0.141133670 |

### H15：每组固定 86 个原点

| seed | predictor | q0 RMSE (rad) | q1 RMSE (rad) | v0 RMSE (rad/s) | v1 RMSE (rad/s) |
|---:|---|---:|---:|---:|---:|
| 0 | P22 | 0.003196586 | 0.006586132 | 0.072865461 | 0.151878427 |
| 0 | K22 | 0.002983588 | 0.006162089 | 0.069850441 | 0.146627946 |
| 0 | D11 | 0.002973809 | 0.006141591 | 0.069801518 | 0.145453031 |
| 1 | P22 | 0.003238018 | 0.006609013 | 0.072969246 | 0.151946752 |
| 1 | K22 | 0.003023645 | 0.006181709 | 0.069877642 | 0.146573924 |
| 1 | D11 | 0.003028402 | 0.006145407 | 0.069918135 | 0.145512741 |
| 2 | P22 | 0.003200789 | 0.006595017 | 0.072920657 | 0.151885879 |
| 2 | K22 | 0.002985946 | 0.006165986 | 0.069899828 | 0.146631109 |
| 2 | D11 | 0.002972474 | 0.006136387 | 0.069831929 | 0.145420742 |

## 两个开发门的完整结果

H1 v、H15 q 要求每 seed 严格改善且各轴逐 seed 相对 RMSE 改善均值至少20%；
H2/H5 q/v 与 H15 v 要求每轴每 seed 不劣。两比较都必须通过。
下表摘录保存的 mean_relative_improvement，转为百分比；正值代表改善，负值代表退化。
它是逐 seed 相对改善均值，不能解释为 pooled RMSE 或新留出效果。

| H | signal | axis | P→K mean relative improvement | P→K | P→D mean relative improvement | P→D |
|---:|---|---:|---:|---|---:|---|
| 1 | v | 0 | 2.878651% | 失败 | 3.349700% | 失败 |
| 1 | v | 1 | 2.903852% | 失败 | 3.091719% | 失败 |
| 2 | q | 0 | 1.217785% | 通过 | 24.763642% | 通过 |
| 2 | q | 1 | 1.052824% | 通过 | 24.520134% | 通过 |
| 2 | v | 0 | -1.636241% | 失败 | -2.830668% | 失败 |
| 2 | v | 1 | -1.309904% | 失败 | -2.489948% | 失败 |
| 5 | q | 0 | -1.640485% | 失败 | -3.008983% | 失败 |
| 5 | q | 1 | -1.414588% | 失败 | -2.105219% | 失败 |
| 5 | v | 0 | -4.677660% | 失败 | -4.053678% | 失败 |
| 5 | v | 1 | -3.950334% | 失败 | -3.946832% | 失败 |
| 15 | q | 0 | -7.141339% | 失败 | -7.364646% | 失败 |
| 15 | q | 1 | -6.917301% | 失败 | -7.418702% | 失败 |
| 15 | v | 0 | -4.354120% | 失败 | -4.392143% | 失败 |
| 15 | v | 1 | -3.610032% | 失败 | -4.428311% | 失败 |

两门都只有 H2 q 的两个轴检查通过，其余12项均失败。H1 v 的各 seed 都有正改善，但幅度不达
固定20%门；H15 q 不仅不达门，而且每 seed 都退化。H2 v、H5 q/v、H15 v 也全部逐 seed 退化，
不能用 H1 或 H2 q 的局部改善覆盖这些不利结果。旧 D 门不追认；两门保存的 passed=false，
整体 development_gate_passed=false。

## 分列实际费用

正式计算已完成的尝试/返回如下；没有失败的正式 fit 或 rollout。
这些是本次新增离线计算，不能把重复利用 C/K 数据当作新的独立证据，也不能把新候选费用归零。

| 正式 P 项目 | 保存费用 |
|---|---:|
| 31×31、22 RHS fit / solve | 3尝试 / 3返回 / 0失败 |
| 重复 scalar labels 请求 / 返回 | 26,400 / 26,400 |
| 新拟合 scalar coefficients / heads | 2,046 / 66 |
| 恢复 K 的设计 / labels / weights scalar 验证 | 34,800 / 26,400 / 1,914 |
| K 保存设计复制 / 新训练过去请求设计复制 | 34,800 / 2,400 |
| 合法前序请求历史请求 / 返回 | 2,343 / 2,343 |
| 前序请求 scalar 消费（含预测初始化） | 4,686 |
| Gram / cross 矩阵 | 各3尝试 / 3返回 |
| 逻辑乘 / 加请求 | 1,971,600 / 1,966,671 |
| ridge identity entry additions 请求 / 返回 | 2,883 / 2,883 |
| P22 完整状态转移 | 6,204尝试 / 6,204返回 |
| P22 prior / residual scalar 输出 | 各136,488 |
| P22 memory feature scalar 消费 / history scalar 复制 | 12,408 / 24,816 |
| K22 完整状态转移 | 6,204尝试 / 6,204返回 |
| K22 prior / residual scalar 输出 | 各136,488 |
| D11 pair / scalar 预测 | 6,204 / 12,408尝试与返回 |
| native state encoding / score scalar error calculations | 2,286 / 54,864 |
| 物理控制调用 / 子步 / RLS / MPC / K refit / D update | 全部0 |

正式来源检查包括13次只读 Git query（返回173,757 bytes）、11次源码读取（173,716 bytes）、
2次 helper module load；科学原件9次读取/校验共15,425,784 bytes，8次普通 JSON 解析，
C gzip 解压后86,628,874 bytes、7,230行 JSON 解析。解压/解析全 C 原件是读取费用，
没有把其他 trial 或特权字段加入模型。

正式内层 wall/CPU 为 3.876407 / 3.328125 s，排除所有最终输出序列化/写盘；
外层 subprocess wall 为 4.668242 s。逻辑矩阵操作不是硬件 FLOPs，短 wall 时间不能证明控制效率、
样本效率或风险下降。根归档另有10 payload、20次读取、41,056,136 bytes，
copy_failures=[]、wall/CPU 0.142244 / 0.046875 s；归档声明 no_scientific_recalculation=true，
automatic_retry=false。这只说明该次保存操作的完成状态。

### 准备与报告费用

准备日志封存在
[准备目录](../results/cpu_validation/2026-10-12_guard_request_memory_preparation/manifest.json)。
首个非执行静态检查在 AST literal_eval 遇到 HELPER_PINS 的 SUPPORT_PATH 名称键时
报 ValueError（工具 chunk `55205e`）；修正的是检查器的静态常量名称解析，没有执行生产模型。
这次失败的源码读取、AST解析及错误位置保留在 external/c4_p_preparation_reads.json。
修正后的 AST/静态 compile 和9个 helper hash 均通过，仍未 import/执行 P 或 helper。

父任务首次小 self-check 的5个 case 全部通过：31特征与合法 history 推进、缺失 history 拒绝、
零新增列与解析参考等价、mock solve 失败的 paid/partial 保存、直接非有限 failed payload 保存。
这不是开发门通过。合成设计生成12,400 scalar、生成标签8,800 scalar；
同标签成功 fit 与预置失败 fit 各消费8,800，合计17,600重复标签。
solve 2尝试/1返回/1预置失败，拟合682 scalar 系数；物理/RLS为0。
合成内层 wall/CPU 0.129742 / 0.125000 s，外层 wall 0.472524 s。
准备归档27 payload、54次读取、906,608 bytes、copy失败0，
wall/CPU 0.214119 / 0.031250 s。这些合成与保存费用单列，不加入正式预测效果。

本报告首次四限定文件读取/解析完成后，输出传输过大使外层 JSON.parse 遇到截断警告失败；
随后进行一次限定摘要提取，保留两次有限读取，未重算科学指标。报告读取 run/metrics/
根 manifest/execution 合计8次、697,302 bytes、8次 JSON 解析，
Python读取/解析/hash wall/CPU合计0.006823 / 0 s；另读取自身账本1次、1,762 bytes并解析1次。
报告账本 external/c4_p_reporting_reads.json 记录文件精确身份、首次传输失败与两次费用。
报告没有参数/trace/预测文件读取、source读取、fit、model call、物理、RLS或MPC；
计时不含文档/账本序列化与写盘或 shell 启动输出。

## 科学限制与后续边界

首次[保存输出契约](../results/cpu_validation/2026-10-12_guard_request_memory/output_contract/report.json)
完成116,912个结构、身份与尺寸检查，零失败；6次读取/20,531,660字节、3,433次JSON解析，
内部wall/CPU .386008/.390625秒。模型恢复、指标及科学门重算为0；检查通过只说明证据一致。
准确首次checker及外层stdout/stderr另封存，未重跑正式数学。
[报告读取账本](../results/cpu_validation/2026-10-12_guard_request_memory/reporting/c4_p_reporting_reads.json)
和[下一唯一方向](../results/cpu_validation/2026-10-12_guard_request_memory/reporting/c4_after_p_direction.md)
已随结果保存，原正式归档manifest保持不变。

P 结果否定的是这个已冻结的 raw-scale31特征、lambda=.01、保存C400配方在已见开发bank上
通过固定完整双门的能力。它没有证明过去请求普遍无用，也没有识别 O 观察到的保持/释放退化
由请求记忆缺失导致。不能把 H1 的小改善称作机制确证、任务技能获得或安全改进。

C 开发来源已被多轮开发使用，P/K/D共享保存未来请求序列；未来请求是离线 oracle 条件，
不是部署中的在线规划或完整闭环控制。本次没有新留出、未知动力学适应、成熟机制或全身技能；
K/D恢复与公共身体/底层 prior 是已披露先验。零新增物理不构成“零停止”安全证据。

不修改旧门，不补跑到成功，不按最佳 seed/轴/时距采纳，不将 P 接入控制。
只有后续单个有依据且先冻结的修订通过相应开发门后，才可讨论新留出与 matched 完整控制；
C4/C5 科学验收和长期 G1/真机结论仍未取得。
