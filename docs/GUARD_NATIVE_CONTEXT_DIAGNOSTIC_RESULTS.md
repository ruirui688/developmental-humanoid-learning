# C4 F：保存原生上下文与一步误差的描述结果

2026-10-11，从 clean `734ab7dab53563327b7dc072378551d2045b68ac` 按[冻结协议](GUARD_NATIVE_CONTEXT_DIAGNOSTIC_PROTOCOL.md)首次完成一次。没有新增物理、模型预测、辨识、策略、增益或门控更新。**这些关联不足以采用新特征，也不能解除 C4/C5 科学依赖。** 接着检验固定反馈尾规划这一单项控制结构候选。

## 完整来源与分母

仅消费 E 保存的原生关节位置/速度、gyro、acceleration、过去端点、独立预测和返回标签。三个固定分数为其余六关节的 `body6`、当前 `gyro`、相邻动作前 `acc_delta`；固定 bins 为 `[0,.5)`、`[.5,1)`、`[1,∞)`，不按结果改分层。没有调用身体模型，没有使用 root orientation、接触真值或未来力矩作为输入。

一次解压 3,312 条原 trace，其中 1,200 prefix、**2,112 active**；全部 active 为完整 20 ms 区间，partial=0。12 个事件表、24 个输入质量分组、288 个误差分组和 864 个 score 统计块全部保存；输入质量标志未发现缺失。未发生的计划端点保持 unobserved，停止轨迹不与完整轨迹排名。

| 组别 | 每 seed 保存 active | A/B | 末20 A/B | earlier A/B |
|---|---:|---|---|---|
| cold11、PDselected、zero | 200 | 100/100 | 不适用 | 不适用 |
| learned_sparse11 | 104 | 100/4 | 16/4 | 84/0 |

三个学习 trial 的研究停止仍为 E 的肘速度停止，terminal ID 为 step203。事件末20共20、earlier共84；earlier 的 B 空分段没有从其他窗口补样本。全体 predictor/axis/q-v/seed/kind/目标段/窗口的 signed、absolute Pearson 与 bins 均见[原描述文件](../results/cpu_validation/2026-10-11_guard_native_context/first/description.json)。

## 证据能说明什么

以学习控制轨迹、学习 predictor、肘速度误差为具体例子，三个 seed 的 A 段各 n=100；body6 与 absolute error 的相关分别为 `−.78566/−.72051/−.75747`，gyro 为 `.71210/.67399/.66686`，acc_delta 为 `.41880/.49935/.32985`。同一三分数并不提供统一的误差方向。

B 段各仅 n=4，body6 的 signed/absolute r 为 `.99878/.99847/.99783`，gyro 为 `.89018/.86432/.89031`，acc_delta 为 `.44592/.44533/.41929`。这些高相关建立在只有4点的停止截断区间上，不能识别遗漏状态的因果；时间趋势、动作选择与目标切换均可能混合其中。在这些示例里所有分数配对都落入第一个 bin，其余 bins 保持 n=0，没有重划边界获取对比。

PD 完整轨迹的 B 段、同一学习 predictor 的肘速度 absolute error 与 body6 为 `−.58456/−.49412/−.61941`，gyro 为 `.55507/.57378/.58534`，acc_delta 为 `−.11449/−.06507/−.05995`，各 n=100。这仍是各自轨迹内部关联，不能与学习停止轨迹比较控制优劣，也不能以相关幅度挑选最佳特征。F 不排除遗漏状态，但没有证明追加某个上下文块会改善控制。

结合 E 已保存的事实——学习模型在 PD 轨迹上一步预测较好，在自己的停止轨迹上反而较差——下一项先分离规划结构问题：原 H15 常力矩预测无法表达未来反馈制动。候选只改变预测尾部为已选 PD 的反馈，第一步仍用原81个请求候选，实际只执行第一步，再观察并重规划。PD 的任务控制能力与增益开发是既有先验，必须公开；它不是本轮身体模型学得的能力。这是另一个可证伪开发假设，并非 F 证明的因果。

## 费用、核对与失败保留

F wall/CPU 为 `1.5925358 / 1.25 s`，主计时不含末 run/manifest 写盘与输出完整性核对；末段另为 `.026376 / .015625 s`，外层 wall 为 `1.8247324 s`。7 个 E 来源文件读取 4,522,763 binary bytes；cache JSON 6 opens/448,352 bytes，cache gzip 1 open/4,074,411 compressed bytes，解压 40,240,158 binary bytes。F 来源本地3文件/55,343 bytes，Git5次返回55,384 bytes。描述计算为非零：6,336 norms、443,136 subtractions、212,544 squares、1,728 correlation descriptions 等完整账保存在[run](../results/cpu_validation/2026-10-11_guard_native_context/first/run.json)。

首次有限输出契约核对 **50,255 checks / 24 failures** 原样保留；24项都是检查者额外要求所有空目标分段有 `empty_window_reason`。冻结协议只在 N≤20、整个 earlier 为空时要求该原因，本轮 N=104/earlier=84，空 B 分段已有正确零分母、null Pearson 及原因。[纯契约补充](../results/cpu_validation/2026-10-11_guard_native_context/output_review/CONTRACT_SCOPE_SUPPLEMENT.md)明确了该断言超出原协议。没有删失败、改 F 或重跑到零失败；不能把原首审报告改称零失败。审查累计8 opens/6,389,001 bytes，未读 derived/trace 或重算 Pearson/norm。

准备交付的首次217项检查也保留1个 Windows CRLF/LF 字节不一致；只把 binding 转为 LF，JSON 含义不变，再核这一处字节相等，没有重复其余216项。原 unified diff 的必要空白通过文件专用属性保留。root 首次保存字段投影误用了不存在的平铺事件键，产生的 null 事件字段明确作废；另存 schema 修正，事件数采用原嵌套字段。以上原件与错误解释都在[结果清单](../results/cpu_validation/2026-10-11_guard_native_context/manifest.json)，没有掩盖工程错误或将其混作实验停止。

结果归档 **32 payload / 13,071,887 bytes**，32 次原字节复制检查零失败，64 binary opens/26,143,774 bytes；wall/CPU `.3241045 / .0625 s`，不含最后 manifest 写盘，0诊断重跑或新统计。原 F manifest SHA `4363934feadb964839ebfaeb902342262aeac70b428e10e3ce3bb17262875565`，description SHA `26c90bbb0cf2c8197f3b5ecd5722a87a645c288810cb0ff895e4224c56a63413`。

正式物理累计仍 **249,662 控制调用 / 2,496,620 子步**，历史在线22,452+离线7,200=29,652 scalar 更新计算。D 旧预测门、E 完整控制/PD 门、C4/C5 依赖保持原失败或未评价状态。检查、提交、推送后继续单项反馈尾开发，再做必要新预测/完整闭环验收；不在此报告或局部诊断后结束[持续目标](CONTINUOUS_EXECUTION_PLAN.md)。
