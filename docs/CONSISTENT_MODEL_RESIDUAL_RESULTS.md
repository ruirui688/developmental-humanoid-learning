# IV2D：保存残差与坐标覆盖首次结果

**首次状态 completed，完整人口可交付；不追认 IV2 原预测门。** 保存的 first_failure 为 null、complete_population 为 true；原 IV2 prediction gate 原样转录为 false。训练内状态残差明显下降，但 newmatched 在 fresh H1 已有同方向系统 bias，随后保存的长时预测误差与递推出箱增加。它们是相关证据，不能识别唯一原因或打开 controller；C4及C5–C7仍未验收，持续目标 active。

事前协议为 [IV2D协议](CONSISTENT_MODEL_RESIDUAL_PROTOCOL.md)。本次从 clean `14088b6a877af05e7ff061ebc0ac011f44a796e8` 首次执行；仅使用已保存 IV2 数据，来源执行 commit 为 `d8491b2e0f8b3bae649b8bf9a297bebba7f76270`。本报告只转录保存字段，没有新增数学、模型调用、fit、物理或门重算。

完整原件：[run.json](../results/cpu_validation/2026-10-12_consistent_model_residual/raw/run.json)、[analysis.json](../results/cpu_validation/2026-10-12_consistent_model_residual/raw/analysis.json)、[source.zip](../results/cpu_validation/2026-10-12_consistent_model_residual/raw/source.zip)、[首次stdout](../results/cpu_validation/2026-10-12_consistent_model_residual/raw/first_stdout.log)、[首次stderr](../results/cpu_validation/2026-10-12_consistent_model_residual/raw/first_stderr.log)。输入四原件的路径、bytes/SHA、模型指纹、计划人口和实际费用均保存在 run。

交付补充由主任务记录：canonical五原件已封存，首次12项必要保存轻核passed。首交付utility曾因将analysis/run字段命名空间取错而触发KeyError；原失败脚本及[首交付失败记录](../results/cpu_validation/2026-10-12_consistent_model_residual/checks/first_delivery_failure.json)完整保留。仅修正该命名空间，没有重跑实验、代数或旧数学。轻核通过只绑定保存证据，不代表科学门通过。

## 人口与统计边界

全 seed 8101/8102/8103、每 seed 全部2000训练行，分别报告 IV1/newmatched 六个状态槽；四模型 cold/oldlearned/IV1/newmatched 的全H1/10/20/50/150共有5772保存预测记录、60统计组。各H每 seed/model origin数为100/100/99/96/86，stride10，H1没有重复评分。所有六训练槽、三个native槽和60组状态均为 completed。

误差符号为 predicted−actual，向量顺序为(肩,肘)。训练state误差是在共同 IV1 action8 已扣除的 saved Y 上计算，六次固定state block batch matmul；cold/oldlearned action不同，不纳入这种训练state比较。fresh误差直接读取保存向量，原fresh RMSE只转录，不重新计算。std均为population std，ddof0。下表仅将保存数值格式化为八位有效数字；完整精度及全部MAE/std/maxabs、四列箱计数、越界量、原RMSE和origin身份保留在 analysis。

## 全部训练内状态残差

每行2000对，全部数值单位为rad/s。newmatched三seed两轴RMSE与MAE下降，bias接近浮点零；这只说明同一训练人口上的拟合一致性。maxabs没有一致下降：seed8101/8103的肘maxabs反而增加，不能把平均残差改善称为每条转移改善。

| seed | model | bias | MAE | RMSE | population std | maxabs |
|---|---|---|---|---|---|---|
| 8101 | IV1 | (-0.010492048, 0.02088715) | (0.010612432, 0.021141246) | (0.011013095, 0.021589175) | (0.0033474142, 0.0054607183) | (0.046453827, 0.046807868) |
| 8101 | newmatched | (-7.6217244E-18, -6.851247E-17) | (0.00087733439, 0.0015155443) | (0.0025728677, 0.0029464669) | (0.0025728677, 0.0029464669) | (0.03850517, 0.052028157) |
| 8102 | IV1 | (-0.011105395, 0.022058727) | (0.01118623, 0.022234975) | (0.011494732, 0.022592866) | (0.0029663228, 0.0048836634) | (0.043752513, 0.042107751) |
| 8102 | newmatched | (-2.2176705E-17, 1.7898009E-18) | (0.00066836102, 0.0011754803) | (0.0021733796, 0.002359139) | (0.0021733796, 0.002359139) | (0.033474228, 0.035722591) |
| 8103 | IV1 | (-0.010786214, 0.021663783) | (0.010895485, 0.021883022) | (0.011283685, 0.022391371) | (0.0033134751, 0.005661625) | (0.049928556, 0.04297899) |
| 8103 | newmatched | (-2.8541405E-17, 1.6648662E-16) | (0.00091812203, 0.001426615) | (0.0023844529, 0.0026346268) | (0.0023844529, 0.0026346268) | (0.041269501, 0.047488957) |

## Fresh一步偏差与native坐标覆盖

newmatched在全部100个H1 origins已有肩正、肘负的速度bias；三seed的MAE接近bias绝对值。这一偏移已出现在原生起点的一步预测，不能把全部退化仅归于长时递推。训练人口与fresh probe动作不同，保存诊断不能将偏移唯一归因于状态head、动作head、未闭合状态或覆盖。

| seed | H1 v bias(rad/s) | H1 v MAE(rad/s) | H1 v population std(rad/s) | H1 v maxabs(rad/s) |
|---|---|---|---|---|
| 8101 | (0.01099691, -0.026841759) | (0.011087133, 0.026923629) | (0.0034552102, 0.0072546217) | (0.025379805, 0.054831142) |
| 8102 | (0.011376092, -0.027869844) | (0.011444375, 0.027895801) | (0.0036304709, 0.0074392178) | (0.02619101, 0.057817959) |
| 8103 | (0.011512266, -0.029315874) | (0.011626453, 0.029374705) | (0.0036965649, 0.0079066228) | (0.024890601, 0.056979667) |

训练闭箱使用各seed全部Psi前四列min/max；箱坐标顺序为(v0,v1,qrel0,qrel1)。native H1只取cold保存原生起点，各model相同起点已作保存身份匹配，跨model去重后每seed100点。边界在箱内，无epsilon、归一化或箱内筛样。

| seed | 四列out count(v0,v1,qrel0,qrel1) | 任意列out/全部点 | 四列最大越界量(rad/s,rad/s,rad,rad) |
|---|---|---|---|
| 8101 | (0, 1, 65, 18) | 78/100 | (0, 0.013553776, 0.00029679923, 0.00014198833) |
| 8102 | (0, 1, 51, 27) | 73/100 | (0, 0.016432385, 0.00027340023, 0.00014267894) |
| 8103 | (0, 1, 39, 44) | 78/100 | (0, 0.011631329, 0.00023438159, 0.00014379826) |

native任意列出箱分别为78/100、73/100、78/100，但四列计数显示速度列只有0/1个出箱，q列频繁出箱且最大越界仅约0.00014–0.00030rad。不能以出箱频率断言真实支持域外推或唯一失配原因。四模型H1共享这批坐标输入，cold/oldlearned bias仍小得多，也限制了单凭出箱解释newmatched退化。

## newmatched长时保存趋势

下表完整列出全部seed的H1/H10/H150重点；其余H与全部模型在完整 analysis中保留。误差增长与出箱共现只描述已保存递推，较长H的origin人口也不同，不是同一初态因果比较。箱内不证明模型有效，出箱不证明失败由覆盖造成；预测偏差或预测输入越界不等于实际物理轨迹越界，也不证明安全收益。

| seed | H | origins | q bias(rad) | q MAE(rad) | v bias(rad/s) | v MAE(rad/s) | recursive out-any/输入点 |
|---|---|---|---|---|---|---|---|
| 8101 | 1 | 100 | (2.1993821E-05, -5.3683517E-05) | (2.2174266E-05, 5.3847259E-05) | (0.01099691, -0.026841759) | (0.011087133, 0.026923629) | 78/100 |
| 8101 | 10 | 100 | (0.0011965963, -0.0026031686) | (0.0011989024, 0.0026069776) | (0.10573316, -0.22376442) | (0.1059411, 0.22413212) | 953/1000 |
| 8101 | 150 | 86 | (0.092066173, -0.17500348) | (0.092066173, 0.17500348) | (0.38618929, -0.68302253) | (0.38618929, 0.68302253) | 12845/12900 |
| 8102 | 1 | 100 | (2.2752183E-05, -5.5739688E-05) | (2.2888751E-05, 5.5791602E-05) | (0.011376092, -0.027869844) | (0.011444375, 0.027895801) | 73/100 |
| 8102 | 10 | 100 | (0.0012295663, -0.0026947223) | (0.0012318833, 0.0026968919) | (0.10842584, -0.23122851) | (0.10861575, 0.23153545) | 951/1000 |
| 8102 | 150 | 86 | (0.087843003, -0.16767561) | (0.087843003, 0.16767561) | (0.34105897, -0.59887051) | (0.34105897, 0.59887051) | 12852/12900 |
| 8103 | 1 | 100 | (2.3024533E-05, -5.8631747E-05) | (2.3252907E-05, 5.8749409E-05) | (0.011512266, -0.029315874) | (0.011626453, 0.029374705) | 78/100 |
| 8103 | 10 | 100 | (0.0012765991, -0.0028349935) | (0.0012796025, 0.0028372138) | (0.11352223, -0.24412064) | (0.11368912, 0.24428411) | 951/1000 |
| 8103 | 150 | 86 | (0.120201, -0.23268635) | (0.120201, 0.23268635) | (0.60154488, -1.1071963) | (0.60154488, 1.1071963) | 12848/12900 |

## 全部组的保存入口

全60组（四模型×三seed×五H）的 bias、MAE、std、maxabs、原RMSE、四列出箱计数与越界量见 [analysis.json](../results/cpu_validation/2026-10-12_consistent_model_residual/raw/analysis.json)。249360个递推输入点包含重叠origin、时距和model的重复条件点，不是独特物理状态或新样本；不pool种子、重判门或partial排名。

## 本次费用与结论边界

| 保存实际用途/调用 | 本次 |
|---|---:|
| 训练Psi/Y scalar读取 | 30000/12000 |
| 固定state batch matmul attempted/returned | 6/6 |
| state scalar输出 / reused Y scalar用途 | 24000/24000 |
| 保存prediction记录 / endpoint error scalar用途 | 5772/23088 |
| native H1点 / box scalar用途 | 300/1200 |
| 重复条件递推输入点 / box scalar用途 | 249360/997440 |
| 原RMSE scalar转录（未重算） | 240 |
| 固定error统计调用 / axis statistic输出 | 126/1020 |
| 输入read/hash原件 / bytes | 4/4 / 13529107 |
| gzip decoded记录 / bytes | 5772/39015029 |
| new controls/substeps / fit / model.predict / RLS | 0/0 / 0 / 0 / 0 |
| source_trace reads / 原门重算 / fresh RMSE重算 | 0/0/0 |
| wall / CPU seconds（不含最终JSON写盘） | 1.4887850000523/1.296875 |

运行环境为Python3.10.11、NumPy2.2.6、Windows CPU，8逻辑核，GPU_used=false。内部NumPy matmul/reduction和未测import IO保持unknown，不补零。复用Y用途不是新增独特标签或RLS；累计物理 **535345 controls /2815018 substeps**、历史 **125652 scalar RLS** 均不增加。

scientific_adoption、old_free_root_C4_validation、c4_scientific_validation、c4_contact_scientific_validation、c5_scientific_dependency_released与control_candidate_opened均为false。训练内改善未延续到fresh一步，完整诊断保留负结果；它未识别唯一机制、不追认IV2/C4、不解除C5科学依赖，不自动采用新模型或controller。

## 下一唯一判断

主任务依据本次有限证据决定唯一IV3近qref原生辨识候选：固定IV1 action8、原psi5与一次OLS，仅将训练公共PD目标从原两级.04/.08rad偏移改为恒定qref。保留三seed、1000zero prefix+2000active、PD base clip±.375Nm及Rademacher±.125Nm、原guard/最终±.5Nm权限、StudyAbort和rank5要求。事前上限为9000新训练controls/substeps、12000新state scalar标签、3solve/30系数；尚未执行，不因本报告自动宣称有效。

预测只用既有IV2评估的全1443个cold保存记录作为固定origin/请求/评分来源，运行IV3新模型一次（62340 pair/124680 velocity-head输出），旧四model分数转录，0新评估物理。该评估已见，只属开发，不能称最终新留出；它的label不得进入fit，也不允许据此校正bias常数。下一协议、代码与新必要检查仍须先冻结至干净提交并推送，再首次执行；完整失败、原门、旧候选关闭及C4/C5科学依赖保持。阶段交付后持续目标仍active。
