# CPU 局部身体学习：探针通过，第一版模型暴露非线性失配

> 2026-10-11；真实刚体接触的自建简化身体，CPU；不使用 PPO、步态教师、预训练策略或真机。

用户已允许少量在线辨识。本轮先完成动作—感觉前置验收，再检查少量身体模型更新能否改善预测和闭环。局部关节结果不能证明翻身、起身、站立或行走学习；旧二维与 G1 证据仍分开报告。

## 1. 固定单关节探针可以获得重复响应

按 [探针协议](JOINT_PROBE_PROTOCOL.md) 完成开发与留出各 300 trials：四姿态、三 seed、八关节、三幅度，以及每个初态一条真实共享零力矩对照。合计 **120,000 控制调用 / 1,200,000 物理子步**；其中前缀 60,000 / 600,000，脉冲窗口 15,000 / 150,000，恢复窗口 45,000 / 450,000。0 停止、0 异常、0 参数更新。墙钟分别为 170.57 s、189.34 s。

两个 split 的全部 576 个脉冲配对都有精确相同的零力矩前缀。共有 **20/32 个姿态/关节组合**在 0.5 N·m 下，全部六个 seed 的脉冲末端有符号配对响应达到预先固定的 1 mrad 门。其他组合和三剂量完整保留，门只表示理想传感模型中的局部响应，不表示安全或学习成功。

依照开发集预定顺序选中仰卧左肩；没有选最大响应，也没有用留出结果改选。

| seed | split | 0.5 N·m 脉冲末端沿请求方向的配对关节变化 / rad |
|---:|---|---:|
| 0 | development | 0.030990 |
| 1 | development | 0.030363 |
| 2 | development | 0.031423 |
| 10 | holdout | 0.029933 |
| 11 | holdout | 0.029762 |
| 12 | holdout | 0.030219 |

独立标准库审计 **47,944,690 项、0 失败**，最大重算差 `3.13e-13`。实际物理/动作/协议的九个核心文件跨 split 字节一致；开发源提交 `61df2d0`，留出为 `fadef21`，唯一源码差异是探针不调用的学习 runner 失败计账修复。两份源码 ZIP 全部成员都与各自 Git blob 原字节一致。

## 2. 第一版：控制改善，预测反而退化

按 [第一版 E1 协议](LOCAL_BODY_LEARNING_PROTOCOL.md) 从 clean `fadef21` 执行三个开发 seed。每 seed 用 2 s 真实零前缀、6 s 固定双向校准，更新四参数线性 ARX/RLS；随后冻结全部参数，用独立真实 reset 比较预测与控制。没有使用下一时刻实际力矩作预测特征，没有接触或惯量真值输入。

| seed | 冻结速度预测 RMSE / rad/s | 学习后速度预测 RMSE / rad/s | 冻结 MPC 跟踪 RMSE / rad | 学习后 MPC / rad | 固定 PD / rad | 零力矩 / rad |
|---:|---:|---:|---:|---:|---:|---:|
| 0 | 0.005007 | 0.006189 | 0.022606 | 0.015862 | 0.050050 | 0.063294 |
| 1 | 0.004999 | 0.006012 | 0.022881 | 0.016116 | 0.050130 | 0.063154 |
| 2 | 0.005013 | 0.006248 | 0.022117 | 0.015625 | 0.050013 | 0.063430 |

学习后 MPC 的三个 RMSE 均改善，原始 RMSE 均值降低 **29.59%**；但单步速度预测误差增加约 **20.27%–24.63%**，与预定“每 seed 至少改善 20%”相反。因此第一版没有通过完整学习验收。不能只挑控制表来宣称模型整体成功，也不能把预测退化改写成无关指标。

第一版正式开发成本 **5,400 控制步 / 54,000 子步、900 次 RLS 更新、14.61 s 墙钟**。全部 18 个 episode 完整执行，0 停止/异常。独立标准库审计 **2,141,463 项、0 失败**，重算 RLS、因果预测、全部 MPC 候选、PD、前缀、模型冻结、来源及预算。该审计确认记录可信；它没有宣称科研门通过。

因开发预测门未通过，**第一版学习留出尚未执行**。留出不是失败后删除的样本；不存在它的成功率或学习指标。开发负结果和代码快照完整归档。

## 3. 第二版候选针对动作非线性

小幅和较大幅度的身体响应不成线性比例。线性模型只用 ±0.5 N·m 校准，再预测 ±0.25 N·m 的独立轨迹，会混合接触约束、摩擦及身体耦合的作用。当前不能从这些数据唯一识别具体物理原因，也不能把模型系数称为测得的惯量。

按单独的 [第二版协议](LOCAL_BODY_LEARNING_V2_PROTOCOL.md) 检验一个五参数模型，增加 `sign(u)*max(abs(u)-0.25, 0)` 动作基函数，并在同样 300 个校准转移内覆盖三种幅度。0.25 N·m 是这次开发修订公开的结构选择；它没有被在线学习成接触阈值。

预测轨迹、控制目标、候选动作、时域、代价和 0.5 N·m 权限全部沿用第一版。第二版另计开发与留出成本，先冻结再运行；不覆盖第一版负结果。当前这一节记录候选设计，不代表第二版已通过。

## 4. 可核查原始证据

- [探针开发配置与预算](../results/cpu_validation/2026-10-11_joint_probes/development/metadata.json)、[留出配置](../results/cpu_validation/2026-10-11_joint_probes/holdout/metadata.json)
- [探针开发全条件分析](../results/cpu_validation/2026-10-11_joint_probes/development_profile.json)、[留出全条件分析](../results/cpu_validation/2026-10-11_joint_probes/holdout_profile.json)
- [探针独立审计](../results/cpu_validation/2026-10-11_joint_probes/audit.json)、[外层校验清单](../results/cpu_validation/2026-10-11_joint_probes/manifest.json)
- [开发选择规则与输入 hash](../results/cpu_validation/2026-10-11_local_learning/selection.json)
- [第一版逐 seed 模型与指标](../results/cpu_validation/2026-10-11_local_learning/v1_development/seed_results.json)、[完整计划及实际 episode 账本](../results/cpu_validation/2026-10-11_local_learning/v1_development/episodes.json)
- [第一版原始预测/更新/物理轨迹](../results/cpu_validation/2026-10-11_local_learning/v1_development/trace.jsonl.gz)、[精确源码](../results/cpu_validation/2026-10-11_local_learning/v1_development/source_snapshot.zip)
- [第一版独立审计](../results/cpu_validation/2026-10-11_local_learning/v1_development_audit.json)、[学习外层校验清单](../results/cpu_validation/2026-10-11_local_learning/manifest.json)

两 split 的共享对照、时间点和模型预测都不能作为额外独立 seed。项目成本还包括此前地面身体采集的 38,750 控制调用 / 387,500 子步；测试、其他 NumPy 原型和正式物理采集分别列报。校准前缀、选择探针和失败版本成本不会从“少量学习”的宣传预算中消失。
