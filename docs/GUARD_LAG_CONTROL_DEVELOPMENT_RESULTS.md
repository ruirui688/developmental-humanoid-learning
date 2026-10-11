# C4 E：single-lag 冻结位置控制开发结果

2026-10-11；按[正式协议](GUARD_LAG_CONTROL_DEVELOPMENT_PROTOCOL.md)从 clean `dda82b1854d80483d0b16e0532bc414906e6a402` 首次执行一次。12 trial 中 **9 完整、3 研究速度停止、0 异常、0 blocked**。冻结学习模型的三个 seed 均只完成 104/200 active，控制假设与 PD 参考门未评价、未通过；完整 C4 仍未验收。

本报告仅引用保存的首次独立审计及一次薄汇总，没有重新读取轨迹、运行物理、调用模型或重算科学统计。原失败、全部 trial 与源码见[原件清单](../results/cpu_validation/2026-10-11_guard_lag_control/manifest.json)。

## 固定问题与实际结果

[D 历史速度差诊断](GUARD_LAG_OFFLINE_DEVELOPMENT_RESULTS.md)的 sparse11 在原长请求停止轨迹上有较低的 H15 位置误差，但共同脉冲预测与短时域结果不支持普适采用。E 只检验这一新开发控制假设，不追认 D 旧预测门通过，也不把已见开发 seed 当新留出。

seed 0/1/2 各依次执行 `cold11`、`learned_sparse11`、`PDselected`、`zero`，每 trial fresh 仰卧 baseline、100 步计账零力矩前缀及 200 active。原 `.04→.08 rad` 目标、每轴 `.5 N·m` 权限、H15/81 常向量、相对位置 `.12 rad` 与速度 `1 rad/s` 的原生研究停止均保持。学习组仅恢复 D sparse11 每 seed 经 400 次双轴更新形成的完整 snapshot，全部模型、规划器、增益与门控冻结；E 新增更新为 0。

| 方法 | seed 0 | seed 1 | seed 2 |
|---|---|---|---|
| cold11 | 完整 200 active | 完整 200 active | 完整 200 active |
| learned_sparse11 | 左肘速度停止，104 active | 左肘速度停止，104 active | 左肘速度停止，104 active |
| PDselected | 完整 200 active | 完整 200 active | 完整 200 active |
| zero | 完整 200 active | 完整 200 active | 完整 200 active |

学习组最后保存行均为 `step_index=203`，该停止行完整执行 10 子步，纳入已发生交互及误差。三个左肘保存速度分别为 `1.0427719075906787`、`1.074403418590931`、`1.0828296411971559 rad/s`。这里发生的是速度停止；B/C sparse 的旧位置停止不能代替本轮原因。

只有完整组可以列出原始 tracking RMSE；学习组不完整，不排名部分区间，不计算学习改善，也不据较少交互声称努力或风险下降。

| 方法 | seed 0 joint RMSE/rad | seed 1 joint RMSE/rad | seed 2 joint RMSE/rad |
|---|---:|---:|---:|
| cold11 | 0.044536694516386324 | 0.04435897843345624 | 0.044357569893000603 |
| PDselected | 0.010401445519984794 | 0.010644472251318818 | 0.010935465170751784 |
| zero | 0.06326975771413691 | 0.0631996451938821 | 0.06333763749375929 |
| learned_sparse11 | 未完整，不比较 | 未完整，不比较 | 未完整，不比较 |

## 冻结判门

| 原输出键 | evaluated | passed | 结果含义 |
|---|---|---|---|
| control_hypothesis | false | false | 学习组三个 seed 均未完整，`validated_pass=false` |
| pd_reference | false | false | 前置控制门失败，`validated_pass=false` |
| matrix_complete | — | false | 3/12 trial 研究停止 |
| c4_scientific_validation | false | false | D 原独立 20% 预测门未过；E 仅开发控制子假设 |

因此不能宣布双关节身体学习控制贡献、强 PD 优势、低风险或全身技能。C5 的科学适应依赖仍未解除；工程事件接口已通过的事实单独保留。

## 实际费用与累计

| 本轮实际量 | 数值 |
|---|---:|
| 控制调用 / 物理子步 | 3,312 / 33,120 |
| 在线 / 离线模型更新 | 0 / 0 |
| 独立诊断 pair / scalar 预测 | 4,224 / 8,448 |
| MPC 规划 pair / scalar 预测 | 918,873 / 1,837,746 |
| public input projections | 4,224 |
| 恢复学习模型 / 初建 cold 模型 | 3 / 3 |
| clone attempts / returns | 24 / 24 |

前缀实际为 1,200 控制调用 / 12,000 子步，已包含在总量中。采集 wall/CPU 为 `76.5802856 / 72.875 s`，外层 wall 为 `77.0825208 s`；首次审计 wall/CPU 为 `36.3693586 / 33.640625 s`，外层 wall 为 `36.6274149 s`。审计另付费重算 923,097 pair / 1,846,194 scalar，0 新物理或更新。

每 seed/kind 的逐轴努力、饱和、完整/部分分母及 full/prefix/control 风险均保留在一次汇总中。停止轨迹的较小累计量不能据此与完整组宣布风险下降；共同前缀仍计入完整风险。

恢复、初始化、复制、guard 与 history 计算为非零计算；恢复/复制没有新增 fit、predict 或 update。诊断及规划预测已在上表单列，不能把零更新写作零计算。实际停止预算保留，没有用 3,600/36,000 的计划上限代替实际费用。

正式物理研发累计为 **249,662 控制调用 / 2,496,620 物理子步**；历史 **22,452 在线 scalar + 7,200 离线 scalar = 29,652 scalar 更新计算**。E 没有新增在线或离线更新。测试、独立审计、薄汇总、读取与归档成本分别列报，不混入物理或学习更新预算。

## 首次审计、一次汇总与原字节封口

[首次独立审计](../results/cpu_validation/2026-10-11_guard_lag_control/first_audit.json)保存 **1,888,017 checks / 0 failures**，最大数值差 `4.3876013933186186e-13`。这是来源、隔离、日志、预算及冻结判门的证据一致性检查；零失败不代表上述科学门通过。

[一次薄汇总](../results/cpu_validation/2026-10-11_guard_lag_control/summary_once/summary.json)仅复制首次保存值，binding checks **33 / 0 failures**，没有重调用模型、重跑 audit 或重算统计；没有另造不存在的 summary stdout 文件。

| 原件 | SHA256 |
|---|---|
| raw manifest | `d584de2194f8387bf5fdbd85d727924f748a8b87ce7e950d1c324f1f1bf2b519` |
| first audit | `ba27cbc47f1291ffbb003102f2d19a0da35821092cd6b1ac790416b7fe80a8e7` |
| summary_once/summary.json | `74c0b148950dc8c33d130492b3f0b636a6da9eba2bd3239e3d7952036437b32e` |

正式[归档](../results/cpu_validation/2026-10-11_guard_lag_control/manifest.json)保留 **22 payload / 6,167,928 bytes**，原字节复制 22 检查零失败；44 次 binary reads / 12,335,856 bytes，wall `0.2781852 s`，该计时不含末 manifest 写盘。归档没有新增模型调用、物理、audit 或 summary。

## 接着执行

结果及账本检查、提交、推送后继续 F：仅用保存的其余六关节原生 q/v 与 IMU gyro/acceleration，对照已保存一步误差，先冻结分层与描述规则。该诊断为 0 物理、0 模型更新；当前原生观测没有 orientation，特权 root quaternion 不得补入。相关性只能指导下一项候选，不能证明因果或控制收益。

依据明确证据只选择一个最小模型修订，另冻协议与预算，再评价独立预测和完整同权限控制。不直接增加探索量、放宽任务/停止或重复 E 到成功。C4 科学验收后再执行 C5 适应、C6 成熟对照与 C7 新留出综合验收。持续目标保持 active，不在报告、局部门或 commit 后停止；阶段顺序见[持续账本](CONTINUOUS_EXECUTION_PLAN.md)。
