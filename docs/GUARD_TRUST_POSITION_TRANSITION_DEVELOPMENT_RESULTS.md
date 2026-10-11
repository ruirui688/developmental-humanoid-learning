# T：有限多步拟合已稳定，长位置开发门仍未通过

T 三个 seed 均得到合法、有限的身体模型，解决了 S 首次试探的数值溢出。本轮仍未通过原 T→K、T→D 开发双门：各 14 项中 12 项通过，唯一缺口仍是 H15 两轴位置改善不足 20%。不进入控制，C4 与 C5 科学依赖仍未验收。

首次执行源为 clean `585540fe8ba07c1149e61c4aa6e9638679ecabb3`；源码 SHA256 `e4cd9e06d078e85ba82614f05b160e69e8b11bd6e66773d795646f5766759464`，协议 SHA256 `79a18f3bc52ded3b650d00f0942d7dfc0d4584727c7c71a4a254860af8a59824`。单次 subprocess，exit 0、stderr 0 bytes、无重试。见 [协议](GUARD_TRUST_POSITION_TRANSITION_DEVELOPMENT_PROTOCOL.md)、[run](../results/cpu_validation/2026-10-12_guard_trust_position_transition/raw/run.json)、[metrics](../results/cpu_validation/2026-10-12_guard_trust_position_transition/raw/metrics.json)、[parameters](../results/cpu_validation/2026-10-12_guard_trust_position_transition/raw/parameters.json)、[execution](../results/cpu_validation/2026-10-12_guard_trust_position_transition/execution.json)与[归档清单](../results/cpu_validation/2026-10-12_guard_trust_position_transition/manifest.json)。

## 优化与选择

保持 S 的 Q phi50、22 维自身闭合、C400 连续 H1/2/5/15 校准窗口和多步位置目标；只优化两个位置 head，其余 20 head 系数冻结。方向为真实 gradient 的负单位向量，每轮从系数 L2 步距 1e-3 开始，以 Armijo 1e-4 和 .5 回退。预测 bank 未进入损失。

| seed | 初始损失 | 最后 accepted 损失 | 最后 gradient L2 | accepted / objective | 退出原因 |
|---|---:|---:|---:|---:|---|
| 0 | 0.000064485321 | 0.000063988328 | 0.0342861533 | 12 / 100 | 硬 objective 预算 |
| 1 | 0.000065533238 | 0.000065098140 | 0.0347832204 | 12 / 100 | 硬 objective 预算 |
| 2 | 0.000064750286 | 0.000064249114 | 0.0343001559 | 12 / 100 | 硬 objective 预算 |

300 次 objective 和 backward 全部有限返回，无 fit 失败、无 120 秒跨界。39 个 checkpoint 为 3 个 initial 加 36 个 accepted；候选只取截止前完成持久化登记的最后真实更新，initial 不作为新拟合结果。261 次 Armijo 拒绝消耗了大部分预算；没有收敛，不能称优化充分，也不能据此否定多步目标。

## 原门与预测结果

4,572 条记录、840 个通道组全部完整有限。Q/K/D 只恢复和评价，指纹前后一致。以下为保存的逐 seed 相对改善均值，肩/肘分列；没有重算模型或门。

| 指标 | T→K 肩 / 肘 | T→D 肩 / 肘 | 原门结论 |
|---|---:|---:|---|
| H1 速度 | 27.681225% / 26.272832% | 28.032373% / 26.415620% | 通过，完全继承 Q |
| H15 位置 | 7.540708% / 6.360919% | 7.350490% / 5.921648% | 未达到 20% |
| H15 速度 | 9.348466% / 8.670397% | 9.315567% / 7.949143% | 各 seed 不劣，通过 |

H15 位置的三个 seed 均严格改善，但幅度不足。T→K 肩分别 8.221076%、6.223842%、8.177207%，肘 6.477703%、6.095707%、6.509347%；T→D 肩 7.919296%、6.371152%、7.761022%，肘 6.165563%、5.540996%、6.058385%。H2/H5 位置和速度各 seed 不劣。

H1 速度 head 没有被 T 优化，该收益不能归于 T 的多步位置拟合。C bank 已用于开发，未来命令是离线条件，不代表在线控制预知未来动作。本轮没有新留出、完整控制或适应实验；保存一致不能代替科学验收。

## 实际费用与保存检查

| 新增工作 | 保存值 |
|---|---:|
| fit 尝试 / 发布 / 失败 | 3 / 3 / 0 |
| objective / backward | 300 / 300 |
| Armijo 拒绝 / accepted 更新 | 261 / 36 |
| 唯一校准 q scalar 标签 | 2,400 |
| 重复 terminal 标签用途 | 948,600 |
| 训练转移 | 2,690,400 |
| prior / residual scalar 输出 | 各 59,188,800 |
| 发布位置系数 / heads | 300 / 6 |
| T/Q/K/D 各预测转移 | 6,204 |
| 新物理 / RLS / MPC / 基线 refit | 全部 0 |
| 内 wall / CPU | 26.1016302 / 24.953125 s |
| 外 subprocess wall | 29.9272868 s |

Q 原拟合、S 失败努力及 C 历史物理费用保留。物理累计仍为 252,690 控制调用 / 2,526,900 子步；在线 22,452、离线重放 7,200 scalar RLS 不变。离线重复用途不能算作新物理，也不能省略计算成本。

首次归档 49 payload，98 reads / 101,055,954 bytes，复制失败 0，wall/CPU .8165675/.15625 s。报告输入为五个保存文件各读一次，19,534,531 bytes / 5 JSON parses，wall/CPU .1706116/.171875 s，见 [读取账](../results/cpu_validation/2026-10-12_guard_trust_position_transition/reporting/c4_t_reporting_reads.json)。

[首次薄输出契约](../results/cpu_validation/2026-10-12_guard_trust_position_transition/output_contract/report.json)15 组全部通过：45 reads / 50,530,507 bytes、4,615 JSON parses，wall/CPU .7812956/.765625 s，exec_command 外 wall 1.3835132 s。模型恢复、指标与门重算均为 0；核对来源、固定人口、失败隔离、accepted 实体及最后登记选择。静态 checker 曾有一次 import-symbol 误断言，纠正记录另存；正式 checker 首次执行通过，没有重跑科学实验。

报告导航 234 个本地链接无缺失；附属封存 20 reads / 99,240 bytes、复制失败 0，wall/CPU .2483099/0 s，原 raw/root manifest 保持不变。见[附属清单](../results/cpu_validation/2026-10-12_guard_trust_position_transition/reporting/manifest.json)。

## 接着执行

唯一 U 保留模型、窗口、损失、双门和 30 accepted / 100 objective / 120 秒边界，从 Q 重新初始化。用最多 5 个正曲率 accepted 对形成有限 L-BFGS 方向，步幅只设 1e-3 上限，不把较小方向放大；原 Armijo 回退、非有限拒绝与候选登记规则保持。新增优化器先验和计算全部披露。

U 是当前 Q phi50/C400/双位置头多步目标候选族的最后一次优化器修订。若仍未过原门，保存局部负结论，停止同 bank 的优化器、步长和特征追加；持续目标保持 active，转一次有边界的路线判断或新物理信息设计。数值失败不能否定多步目标；训练损失下降而开发门失败也只能支持此配置与预算下的局部结论。

先新方向最小检查、静态审阅、冻结提交推送，再一次 U 开发。开发通过后仍须新留出预测与匹配完整控制，之后依次 C5 变化适应、C6 成熟门控、C7 综合验收。本报告、检查及推送均是中间交付。
