# C4 I：上一原基模型残差的因果检验结果

按[冻结协议](GUARD_PD_TAIL_NATIVE_RESIDUAL_DIAGNOSTIC_PROTOCOL.md)，从 clean `1f239f38262b8f3d964a69732ea6def7570fbc27` 首次执行。只消费 H 四个已保存文件，用 102 个固定末窗口完整端点形成 96 个连续相邻 pair；首记录不补历史。**学习组和冷模型开发门均失败，残差候选不进入控制。**

## 正负结果

修正严格使用上一时刻 actual−original base 的速度残差；当前实际端点只评分，并在之后发布给下一步。没有递归使用 corrected 残差、滤波调参、额外数据或模型调用。每个 pair 的 base/corrected 使用相同标签与分母。

| 速度 RMSE 相对改善 | seed0 | seed1 | seed2 | 三 seed 算术均值 |
|---|---:|---:|---:|---:|
| learned，肩 | −9.20% | −3.86% | 22.60% | 3.18% |
| learned，肘 | −4.88% | −6.00% | 24.92% | 4.68% |
| cold，肩 | −48.44% | −48.45% | −48.12% | −48.34% |
| cold，肘 | −48.35% | −48.34% | −51.65% | −49.45% |

负号表示预测更差。学习组 seed0/1 的两轴均退化，seed2 改善；两轴三 seed 均值都未达到冻结的 20%，也不满足各 seed 严格改善。cold 每个 seed 的两轴均退化。不能从 seed2 的有利数字选择性采用。

学习 seed0/2 的停止端点被修正为肘速度 .75113309/.77542604 rad/s，实际仍为 1.07094720/1.06543372；末端误差有所降低，但预测仍乐观。这两行不能替代全部固定 pair 的开发门。cold seed0/1 的末端修正严重过冲，反映上一误差不能普遍作为下一步的常值偏差。本诊断不识别接触模式、迟滞或任何真实动力学原因。

全部 96 组 ALL/A/B/cross × q/v × 轴的 RMSE、MAE、bias 和空组，以及每个 pair 的原预测、修正、标签和历史都保存在原件。A/B 与位置只描述；停止轨迹上的预测配对不构成控制表现排名，没有补跑、扩大窗口或修改旧门。

## 检查、来源和费用

准备 8 个合成小分支通过，独立静态审查无评分或信息泄漏问题。唯一补充只为 failure.json 保存声明来源与已返回身份；原草稿、首次测试输出重建说明、diff 和来源字节保留于[准备清单](../results/cpu_validation/2026-10-11_guard_native_residual_preparation/manifest.json)，没有重跑已过八项数学。

[有限输出核对](../results/cpu_validation/2026-10-11_guard_native_residual/output_contract/c4_i_output_check_01.json)12 项零失败，仅核输出原字节、计数、历史声明与旧依赖；没有重算 I 残差或判门、H/G 原统计。原 C4/C5 科学依赖保持，scientific_adoption=false。

I 读取 4 文件/181,035 字节，解析 3 JSON、102 记录；自身读取 2 文件/26,372 字节、4 Git queries。96 pair、204 scalar 原偏差计算/发布、192 velocity 加法及各 192 q 乘法/加法，统计插入 1,552 scalar。model/RLS/新物理均 0；偏差算术有计算，不能称零计算或新在线辨识。wall/CPU .181176/.031250 秒（不含最后 run/manifest 写盘），外层 wall .266800 秒。

输出核对读 4 文件/177,119 字节，wall/CPU .042686/0 秒。[结果原件](../results/cpu_validation/2026-10-11_guard_native_residual/manifest.json)10 payload/212,968 字节，10 复制项零失败、20 binary reads/425,936 字节；归档 wall/CPU .120814/.015625 秒。raw manifest SHA256 为 `afa5be1c41d3bce19313b195919ff1aee1a0adf09e05cf5322547ed75c995f99`。首次 stdio、源码提交和外层费用完整保留。

准备 schema 查询的实际字节/耗时未在当时计量，明确 unknown；六次读取四种 H 文件，不补写成零。正式物理累计仍 **252,690 控制 /2,526,900 子步**；在线 22,452、离线 7,200 scalar RLS 计算不变。

## 下一项

J 单独检验一个原生感觉结构假设：当前完整六通道 IMU 是否给冻结 lag11 基模型提供额外的一步残差信息。依据是自由根部与局部两关节状态的结构缺口，不能用 F 的相关性挑轴或证明原因。

先在已有 C sparse 校准上进行一次有计账的小型离线拟合，所有六通道、单位尺度和正则先冻结；在 C 共同脉冲和 G 既有控制轨迹上只评价一步预测。原基模型在同一校准上已经拟合，重复数据费用明确披露。当前 IMU 只取 control-start observation，不能把当前 IMU 复制到未来 H15，更不直接接入 MPC。

J 是已见数据的开发消融，不是新留出或在线学习成功。它通过后仍需新留出与匹配控制；失败则保留负结论。I 提交推送后直接进入 J，[持续目标](CONTINUOUS_EXECUTION_PLAN.md)保持 active。
