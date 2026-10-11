# C4 H：预测许可与真实停止的保存诊断结果

按[冻结协议](GUARD_PD_TAIL_FORECAST_STOP_DIAGNOSTIC_PROTOCOL.md)，从 clean `a46633c71e95826835ebc43f0aeaf6d5fdfd19e8` 首次执行。只读取 G 已保存的五个输入，描述六个 MPC trial 的 628 个 active 决策、十二个 A/B 组和 102 个固定末窗口端点；没有模型调用、更新或新物理。

## 核心发现

学习组三个 seed 共 406 个 selected H15，首步和预测尾均没有触及原研究停止界限（位置偏离 .12 rad、速度 1 rad/s）。但 seed0/2 在切换目标后仍真实超速停止：

| 学习 trial 的停止端点 | 预测肘速度 rad/s | 实际肘速度 rad/s | actual−prediction rad/s |
|---|---:|---:|---:|
| seed0，active101 | .27077458 | 1.07094720 | .80017262 |
| seed2，active103 | .17284681 | 1.06543372 | .89258691 |

两行均完整执行 10 子步，原独立一步与 selected stage0 相同。末肩速度也被低估，误差分别为 −.38419047、−.44509550 rad/s。学习组 B 段分别仅 2、100、4 点，不能把两个很短的停止段当作充分的模型有效域证据。

这否定了“学习组只是因为规划容许超过原停止界限而失败”的解释。收紧名义 forecast 无法直接处理这两次已经预测为合规的实际越界；下一项优先检验因果身体预测修正。没有因此认定某个残差观察器必然有效。

冷模型首步 selected 同样无越界。cold seed2 的肘预测尾有 36 个位置越界 stage、涉及 10 个决策，最早为 h11，分布在 A/B 的 32/4 stage、9/1 决策；该 trial 实际完整。这说明远期规划许可与任务定义仍不一致，但它不是学习组停止的直接证据。cold seed0/1 的停止行是 fallback，不能补成“selected 预测安全”；其独立请求预测与实际肘速度差分别为 −.02544113、−.02553305 rad/s。

## 检查、成本与边界

[有限输出核对](../results/cpu_validation/2026-10-11_guard_forecast_stop/output_contract/c4_h_output_check_01.json)13 项零失败，只检查输出原字节、固定计数、缺失/partial 契约和原门保持；不重复 H 统计、G 首审或科学验收。原 G control/PD 门和 C4 科学门保持失败/未评价，scientific_adoption=false。

H 读取 5 文件、4,575,413 原字节；解析 4 JSON 和 3,028 trace 行，解压 32,832,111 字节。自身来源读取 2 文件/22,213 字节、4 Git queries；wall/CPU .833451/.656250 秒，外层 wall .983652 秒。输出核对读 5 文件/746,465 字节，wall/CPU .023318/.015625 秒。标准库描述和 hash 有实际计算，零更新不表示零计算。

[结果原件清单](../results/cpu_validation/2026-10-11_guard_forecast_stop/manifest.json)保存 11 payload/810,047 字节，11 次复制核对零失败，22 binary reads/1,620,094 字节；归档 wall/CPU .175545/.031250 秒。raw manifest SHA256 为 `b3c9969c6d65987c0993c32e0143a7f5f4e704410d5d4e7cbe423a950b5ed538`。首次 stdio、外层费用和核对代码均保留。准备原件、此前 G Git 路径补充及方法/schema 审查见[准备清单](../results/cpu_validation/2026-10-11_guard_forecast_stop_preparation/manifest.json)；已过检查未重跑。

正式物理累计仍为 **252,690 控制调用 /2,526,900 子步**；在线 22,452 与离线 7,200 scalar 辨识计算不变。

## 接着执行

I 先冻结一个零新物理的因果残差诊断：只用 H 固定末窗口中的上一完整连续区间误差，检验其能否修正下一步速度；当前实际端点只作评分，不能进入当前修正。基模型误差与修正后误差分开，首记录、缺失与断序不补零。若该开发依据成立，再冻结最小观察器和匹配控制验证；若不成立，公开失败并改选有依据候选。

H 是已见开发描述，不能代替独立预测、完整闭环或未知动力学验收。C4/C5/C6/C7 和[持续目标](CONTINUOUS_EXECUTION_PLAN.md)仍未完成；结果提交推送后直接进入 I。
