# C4 O：保存预测局部创新与递推输入效应诊断协议

本协议固定一次已有 N 保存预测诊断；不拟合、不调用模型、不增加物理，不重新计算或裁判
N/K/D 的旧预测门。N 失败、C4/C5 依赖与持续目标状态不因本诊断改变。

## 唯一问题与信息边界

对相同 seed、trial、原点和已保存请求，区分真实端点上的一步预测误差与自身递推输入偏离
对应的端点差；描述 H1 误差在固定命令阶段中的分布。条件分组不能识别动作因果增益、
延迟、隐藏动力学或 guard 机制，不作为特征、权重、正则或数据搜索依据。

科学输入仅为 `results/cpu_validation/2026-10-11_guard_scaled_native_transition/raw/`
下三个文件；读取全原字节并逐次计费，不再复制原 N 载荷：

| 文件 | 字节 | SHA256 |
|---|---:|---|
| manifest.json | 646 | f393ee50b6f8de6d33264eee4ea9a20ca3328ea5a1d545d93a54240d37c36570 |
| run.json | 12,866 | f4a40fe58caae01f91df0678dbd6eff1def4aa8bc20a9fac076bb6fcf13bb9ff |
| predictions.jsonl | 16,304,217 | 23c3c78afc4ba301a700cb0e4ad73fa6bc24a5c0072b7136f2933eacf058aff7 |

必须绑定 completed、clean N `74725ea22ec1e9a12085a1fa70ce228e848c761f`。N run 中两个
schema 源身份固定为 N 脚本 27,537 字节、SHA256
`df0833d08e722391f98de1bc2cbf81e2d0a866a3ea65def24e9b216d25787518`；
K helper 脚本 36,390 字节、SHA256
`f910bb6fd9f01ebf5fd52426b40b43414e50bebcfe6460cf6132bccb1a2192bb`。
正式只核 run 中该绑定，不再次读或导入 N/K 源码。

不读参数、旧 trace、旧 metrics、隐藏动力学、实际未来力矩或接触。解析整个 predictions
JSONL 的费用记录；H2/H5 只索引身份、不作新的科学计算。异常重复或未知身份停止运行；
缺失、不完整或非有限的需要记录记为 unavailable，保留固定分母与原因，不补跑模型。

## 固定原点、坐标与精确匹配

seed 固定 0/1/2；主分析 N22/K22，D11 仅描述。每 seed 使用原 H15 全部 86 原点
`0…85`，逐 k=`1…15`，所有 k 保持同一原点集；另用 H1 全部 100 原点 `0…99`
描述命令条件。不按误差选择窗口、seed、通道或组。

只分析 q0/q1/v0/v1。N/K 的 q 是固定 qref 的相对位置；v 为原生速度。检查同原点的
initial_x22、actual_endpoint_x22、previous_v2、8轴请求精确相同；原生 H1 相邻端点与
下一 initial_x22 精确连续，previous_v2 对应同 trial 上一 initial 的 v0/v1。
ID 固定为原 `seedN_prediction:98+origin/99+origin` 两过去端点以及
`seedN_prediction:100+origin…` 请求端点。origin0 的过去来源只核保存原件，不补造前史。
递推 H15 initial/history 与同原点 H1 匹配，15 个请求逐一与相应 H1 请求匹配，最终真实
端点与第15个 H1 完全相同；H15 第一步路径必须与同 predictor H1 路径精确一致。

保存记录没有 qref 数值；N/K 共享固定坐标由已绑定 N 源码以及以上精确原生匹配保证，
不声称读取/重新验证 qref 值。D 路径 q 为绝对位置；从已保存 D terminal_qv 加其原
`actual−predicted` terminal_errors 恢复该记录的既有绝对标签，不推定或使用模型参数。
D 恢复的 v 标签必须与 actual_endpoint_x22 v 一致；q 绝对标签与相对原生 q 的坐标差
相对固定 origin0 在整个 trial 一致，H15最终绝对标签与匹配 H1 标签一致。
浮点标签重构容差固定绝对 `1e−12`（各自 rad 或 rad/s），不调参；坐标差只做一致性检查，
不输出或部署估计 qref。D 不参与 N−K 主差表。

若逐步路径未保存，仅有 terminal，则相应固定单元 unavailable。未保存 guard 投影，
本次一律 `unavailable_not_saved`，不重建 guard 或从实际力矩推断。

## 固定公式与输出

O 统一使用 `预测−真实`；原 N 保存 terminal_errors 和旧 bias 使用相反符号。
P 的递推原点 t、终点步 k 对应 H1 原点 `t+k−1`：

```text
e = saved_recursive_endpoint(P,t,k) − actual_endpoint(t+k)
b = saved_H1_endpoint(P,t+k−1) − actual_endpoint(t+k)
r = saved_recursive_endpoint(P,t,k) − saved_H1_endpoint(P,t+k−1)
e = b + r
sum(e²) = sum(b²) + sum(r²) + 2*sum(b*r)
```

r 是模型内递推输入与真实输入的端点差，可能包含历史或预测 guard 分支改变；它不是独立
动力学残差或因果贡献。b 不是从原点开始累加的创新；不使用 H×H1 RMSE 或 RMSE 相减。
同一 H1 端点在重叠窗口中重复使用，不能称 1,290 个独立样本。

每 seed/predictor/k/channel 保存 e/b/r 的平方能量、bias、MAE、RMSE、带符号交叉项和
点级/能量恒等式数值残差，以及固定/可用/不可用计数。q 单位 rad，v 为 rad/s；平方单位
分别 rad²、(rad/s)²，不能跨单位或轴合并排名。H1 条件组以同公式 r=0 保存一步误差。
N−K 的三个平方能量差和交叉项差仅在两组完整、非空且固定配对时报告；空或部分组明确
不可用，不报告部分排名。完整本身不表示科学通过。

本轴已知请求阶段固定：持续零、开启、保持、释放、变更、trial 首次；采用保存数值精确
零/相等比较，不选幅值阈值。另一轴请求保留于8轴请求原件。没有合法上一保存请求时，
origin0 用 trial 首次；需要的历史缺失用 `unavailable_request_history`，不补零。
所有类别保留，包括空组；已知请求含旧 native veto，是离线 oracle 条件，不能视为在线
规划权限或实际区间平均力矩。状态与命令共变、窗口重叠及三 seed 限制因果解释。

仅输出 `records.jsonl`、`diagnostics.json`、`run.json`、`manifest.json`。
完整预算为 300 条 H1 条件记录、11,610 条递推记录；递推关注46,440个scalar e/b/r组合，
H1另3,600个组合。组表固定540个递推组和252个 H1组（六阶段及不可用历史），N−K差表264组。
这些是计算/重复标签使用量，不是新交互或独立样本量。D 仅描述参照。

## 费用、失败与正式一次执行

记录文件读取尝试/返回、字节与哈希、JSON解析、source/Git核查、记录验证、D标签还原、
差分、平方、交叉项、聚合输入使用及耗时。逻辑请求量不是硬件 FLOPs；软件索引/比较与
序列化开销通过 wall/CPU 和文件字节披露，不宣称逐CPU指令计费。
关键算术费用在尝试之前记录，失败保留已发生费用、partial records、原因与失败 manifest。
缺失 schema/坐标不一致的单元不可用，绝不重跑模型。run/manifest最终写盘不在计时内。
科学采用、C4验收与C5依赖解除全部 false，不输出新的旧门 verdict。

准备只查看绑定 N/K schema、N manifest/run 及 predictions 首行；首次5次读取80,558字节、
3次JSON解析、2次源码decode；schema补充2次读取63,927字节、2次decode、0次JSON。
首行读取3,119字节，SHA256
`4a0aa0095ef3c57385e578f0ef0d76c3ce9af263d0f7ca3169c4ac8d0334aab4`，不把首行 hash 当全文件 hash。
读取日志由准备归档保留，既有方向阅读与本次准备分列。

父任务只做一次有限新合成验证，检验 signed 分解/负交叉项、精确身份/历史/请求失配、
D绝对坐标与 terminal-only/异常原路径 unavailable；不重复旧 K/N 数学。合成三 case
共享费用与尝试 journal，断言失败也保留前序费用。54个固定合成输入记录仅用于新诊断函数；
无实际输入读取、模型/物理/拟合或旧门裁判。先完整对齐，再一次有限故障夹具检查：
N请求失配、K缺path均保留不可用，D仅失配端点k2不可用，合法D其他端点继续保留。
静态审查一次，修订明确保存。准备命令由父任务首次一次执行到新目录：

```powershell
python scripts/diagnose_guard_saved_recursion.py --repo . --self-check --output <new-preparation-check-directory>
```

正式源码/协议先 clean 提交，脚本核 canonical两文件与 exact HEAD committed bytes 一致，
且 Git clean；父任务从冻结提交首次一次执行到全新目录：

```powershell
python scripts/diagnose_guard_saved_recursion.py --repo . --source-commit <exact-O-HEAD> --output <new-raw-directory>
```

本诊断完成后依完整局部/递推/交叉项和固定请求条件决定单个有依据结构修订；若不能识别，
公开不可识别结论。不通过 RMS floor、lambda/权重扫描、追加数据/特征或恢复旧位置—速度
候选追逐已揭晓分数。C4最早未验收、持续目标 active。
