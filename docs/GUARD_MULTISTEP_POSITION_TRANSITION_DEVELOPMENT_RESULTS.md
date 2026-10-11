# S：有限多步位置拟合的首次数值失败

S 三个 seed 均在第一次优化参数试探时产生非有限二次特征，**没有可发布的 S 模型**。S→K 与 S→D 双门不可评、未通过；这不是多步训练目标无效的科学结论。科学采用、C4 验证及 C5 科学依赖释放仍为 false。

协议见 [S protocol](GUARD_MULTISTEP_POSITION_TRANSITION_DEVELOPMENT_PROTOCOL.md)。首次执行源为 clean `fcab231a511996de83e28d93ce6749326b38308f`，源码 SHA256 为 `22097d00bbb884e29b9d0e6cd060b53e0448beb72321685c11e7942762acfe7e`。来源字节验证通过，一个 subprocess、exit 1、stderr 0 bytes，无补跑。完整证据见 [run](../results/cpu_validation/2026-10-12_guard_multistep_position_transition/raw/run.json)、[parameters](../results/cpu_validation/2026-10-12_guard_multistep_position_transition/raw/parameters.json)、[metrics](../results/cpu_validation/2026-10-12_guard_multistep_position_transition/raw/metrics.json)、[execution](../results/cpu_validation/2026-10-12_guard_multistep_position_transition/execution.json)及[根 manifest](../results/cpu_validation/2026-10-12_guard_multistep_position_transition/manifest.json)。

## 发生了什么

仅调整冻结 Q 的两个位置头，100 系数/seed；其余 20 头系数冻结，22 维状态完整自身递推。训练只用 C400 校准、H1/2/5/15 连续窗口，损失与预算按协议冻结。预测数据没有进入优化。CPU float64、Torch 单线程与 SciPy L-BFGS-B 已按准备身份使用。

各 seed 的 objective 1 是有限 Q 初始点，并保存 iteration0；objective 2 是优化器重复计算的同一点，也有限。objective 3 是首个参数试探，在长递推中以 `nonfinite_tensor:quadratic21` 失败。每 seed 没有 accepted callback、没有 budget 耗尽。所有非预算异常按原协议使 fit_failed，iteration0 只留证据，不能作为 S 候选。

| seed | 初始损失 | 初始梯度 L2 | objective 开始/返回 | accepted 更新 | fit wall (s) | 结果 |
|---|---:|---:|---:|---:|---:|---|
| 0 | 0.000064485321 | 0.053007550 | 3 / 2 | 0 | 0.216638500 | 非有限试探，无候选 |
| 1 | 0.000065533238 | 0.049435468 | 3 / 2 | 0 | 0.163762200 | 非有限试探，无候选 |
| 2 | 0.000064750286 | 0.052932081 | 3 / 2 | 0 | 0.160067500 | 非有限试探，无候选 |

失败试探的 H1、H2 位置归一化均方误差已升至约 66–67、583–586；H5 约为 5.2–7.5×10²⁵，随后二次特征溢出。原初始点仍有限，当前证据支持先限制优化试探步幅，未识别缺数据或多步目标无效。失败张量及非有限值显式保存在 parameters，未替换成零、有限罚值或假梯度。

## 固定评价人口与原门

仍保留 S/Q/K/D、三 seed、H1/2/5/15 的完整 4,572 条计划记录与 840 保存通道组。S 全部 unavailable，原因为 `fit_failed_no_S_candidate`；Q/K/D 完整评价，指纹前后一致。双门均 evaluated=false、passed=false，不删除种子，不以 Q 的指标替代 S，不排名不可用人口。

原门不变：H1v 和 H15q 各 seed 严格改善、各轴均值至少 20%；H2/H5 q/v 与 H15v 各 seed 不劣。C bank 已反复用于开发，未来请求是离线 oracle 条件，本轮没有新留出或完整控制结果。

## 实际费用

| 项目 | 保存值 |
|---|---:|
| fit 尝试 / 发布 / 失败 | 3 / 0 / 3 |
| objective 尝试 / 返回 / 失败 | 9 / 6 / 3 |
| backward 尝试 / 返回 | 6 / 6 |
| 唯一校准 q scalar 标签 | 2,400 |
| terminal q 重复标签用途 | 26,142 |
| 训练转移尝试 / 返回 / 失败 | 74,922 / 73,764 / 1,158 |
| prior / residual scalar 输出 | 1,648,284 / 1,622,808 |
| initial checkpoint 写入 | 3 |
| 已发布位置系数 / heads | 0 / 0 |
| Q/K/D 各预测转移 | 6,204 |
| 新物理 / 子步 / RLS / MPC / Q/K/D refit | 全部 0 |
| 内 wall / CPU | 7.659887800 / 6.703125 s |
| 外 subprocess wall | 11.001600400 s |

计数包含重复初始目标和失败批次；不能以零发布声称零拟合努力。Q 原 26,400 重复标签、3 solve、3,300 系数及 C 历史物理费用继续保留。物理累计仍为 252,690 控制调用 / 2,526,900 子步，在线 22,452 与离线重放 7,200 scalar RLS 不变。

首次归档 14 payload、28 reads / 79,104,330 bytes，复制失败 0，wall/CPU .253797500/.093750 s。报告从五个保存文件各读取一次，17,805,255 bytes / 5 JSON parses，wall/CPU .146065500/.140625 s，见 [report reads](../results/cpu_validation/2026-10-12_guard_multistep_position_transition/reporting/c4_s_reporting_reads.json)。报告只转录保存值；派生摘要因包含失败张量导致首显示被截断，原数据和摘要保留，随后只从派生摘要取简要字段，没有重算模型、指标或门。

[首次薄输出契约](../results/cpu_validation/2026-10-12_guard_multistep_position_transition/output_contract/report.json)的 15 个组级检查全部通过：10 reads / 39,568,133 bytes、4,580 JSON parses，检查 4,572 记录 / 840 通道组 / 3 参数记录 / 3 初始 checkpoint，wall/CPU .601226800/.609375 s，exec_command 外 wall 1.091306 s。模型恢复、指标与门重算均为 0。检查通过只说明失败、不可用人口和原件保存一致，不能把 S 科学门改为通过。

## 唯一下一步

冻结一个 T 数值优化修订：保留 S 函数类、完整递推、训练窗口和损失，以有限梯度步长及 Armijo 回退替代无界 L-BFGS-B 试探。非有限试探拒绝并保存，有限下降点才能接受；不裁剪模型状态、不伪造梯度、不平滑 guard、不扩大数据或扫描配方。新尝试和失败回退全部另计账，候选仅取预算内最后合法 accepted。

先最小新分支检查、静态审阅、冻结并推送，再一次正式执行。T 开发通过后仍须新留出预测和匹配完整控制。S 报告和提交是中间交付，持续目标保持 active。
