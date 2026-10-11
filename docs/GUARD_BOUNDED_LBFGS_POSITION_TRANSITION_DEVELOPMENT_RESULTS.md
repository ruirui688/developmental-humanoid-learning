# U：校准拟合改善，长位置开发门仍失败

U 用更少目标计算完成三 seed 各 30 个合法 accepted 更新，校准损失明显下降，但原 U→K、U→D 双门仍各只有 12/14 项通过。H15 位置改善约 2%–5%，不足原 20% 门，且比 T 更小。**本候选族结束优化器修订，不进入控制；C4 与 C5 科学依赖仍未验收。**

首次运行源为 clean `7358ff9f583d9a20460e94c914cd8ea172c9780a`，源码 SHA256 `7c2c2ea6cbe421edca73bd0e53adc1ad2f373390c694e8c7950d5b1b32f1ef95`，协议 SHA256 `222f9f65e09c9b71f9bfdae12c39f95bce8472e3652e85bb107b9ed8156669ed`。单次 subprocess、exit 0、stderr 0、无重试。见[协议](GUARD_BOUNDED_LBFGS_POSITION_TRANSITION_DEVELOPMENT_PROTOCOL.md)、[run](../results/cpu_validation/2026-10-12_guard_bounded_lbfgs_position_transition/raw/run.json)、[parameters](../results/cpu_validation/2026-10-12_guard_bounded_lbfgs_position_transition/raw/parameters.json)、[metrics](../results/cpu_validation/2026-10-12_guard_bounded_lbfgs_position_transition/raw/metrics.json)、[execution](../results/cpu_validation/2026-10-12_guard_bounded_lbfgs_position_transition/execution.json)和[归档清单](../results/cpu_validation/2026-10-12_guard_bounded_lbfgs_position_transition/manifest.json)。

## 优化与原门

保持 T/S 的模型、C400 校准窗口、完整闭合、损失和预算，从 Q 重新初始化。唯一修订为 memory5 的有限 L-BFGS 方向、1e-3 范数上限和不放大小方向；原 Armijo 及登记/异常规则保持。

| seed | objective / accepted | 初始损失 → 最后损失 | 最后 gradient L2 | 退出 |
|---|---:|---:|---:|---|
| 0 | 46 / 30 | 0.000064485321 → 0.000048482007 | 0.012360758 | accepted 数预算 |
| 1 | 39 / 30 | 0.000065533238 → 0.000048774355 | 0.065705364 | accepted 数预算 |
| 2 | 39 / 30 | 0.000064750286 → 0.000047581132 | 0.065346579 | accepted 数预算 |

124 objective/backward 全部有限，31 个 Armijo 拒绝、90 accepted、90 正曲率加入；93 checkpoint 包含 3 initial。没有 fit 失败或时间跨界，也没有收敛。只选截止前完成持久化登记的最后真实更新；未续跑 T 或追加预算。

| 保存指标 | U→K 肩 / 肘 | U→D 肩 / 肘 |
|---|---:|---:|
| H1 速度 | 27.681225% / 26.272832% | 28.032373% / 26.415620% |
| H15 位置 | **2.589331% / 4.844233%** | **2.389922% / 4.397552%** |
| H15 速度 | 6.421195% / 5.981587% | 6.387440% / 5.239232% |

H1v 完全继承 Q，不能归于 U。H15q 三 seed 均严格改善，但未达均值幅度门；H2/H5 q/v 与 H15v 各 seed 不劣。4,572 条记录、840 通道组全部完整有限，Q/K/D 指纹不变。开发数据已见，没有新留出或完整控制结论。

## 训练与开发的分离

保存的训练 H15 两轴归一化位置均方误差为：seed0 `0.000140517885 → 0.000082029778`，seed1 `0.000144379069 → 0.000079524746`，seed2 `0.000141516849 → 0.000081644639`。训练 H1/H2 误差上升，四时距总目标下降。因此优化器已取得真实拟合收益；这个收益没有转化为原开发位置门的足够改善。

这支持停止把优化效率作为唯一修复方向；它没有识别数据覆盖、部分可观测、非光滑保护或模型结构的因果，也没有证明多步目标普遍无效。gradient 仍非零，不能称找到了该函数类的最佳解。按预先冻结分支，本配置与预算下的候选族缺乏进入控制的充分开发证据，不再同 bank 增加优化器、步长或特征。

## 实际费用与保存

新增 fit3/3/0；2,400 唯一 q scalar 标签、392,088 重复 terminal 用途、1,112,032 训练转移；300 位置系数/6 heads。U/Q/K/D 各 6,204 预测转移。新物理、RLS、MPC 和基线 refit 均为 0；Q 原拟合及 S/T 全部失败和优化费用继续保留。物理累计仍为 252,690 控制调用/2,526,900 子步，在线 22,452 与离线重放 7,200 scalar RLS 不变。

内 wall/CPU `15.9039526/14.765625 s`，外 wall `19.9362021 s`。首次归档 103 payload、206 reads/107,815,614 bytes、0 复制失败，wall/CPU `2.4046932/.1875 s`。报告五个保存文件各读一次，22,398,076 bytes/5 parses，wall/CPU `.2280175/.21875 s`，见[读取账](../results/cpu_validation/2026-10-12_guard_bounded_lbfgs_position_transition/reporting/c4_u_reporting_reads.json)。

[首薄输出契约](../results/cpu_validation/2026-10-12_guard_bounded_lbfgs_position_transition/output_contract/report.json)15 组全过：99 reads/53,909,602 bytes/4,669 parses，wall/CPU `.8565182/.859375 s`，exec_command 外 `1.4677885 s`；模型恢复、指标和门重算均为 0。它核对保存一致，不能改变科学门失败。

首结果导航236个本地链接无缺失；报告/契约附属封存16 reads/107,972 bytes、0复制失败，wall/CPU `.3156414/.015625 s`，原raw/root manifest保持不变。

接着进行一次有边界的校准—评价信息诊断或新物理采样设计，先冻结问题与费用，不自动采用新模型、不改变旧门、不重新排名失败轨迹。持续目标保持 active，提交推送后继续最早未验收的 C4；C5/C6 工程可独立准备，科学对照仍依赖完整 C4。
