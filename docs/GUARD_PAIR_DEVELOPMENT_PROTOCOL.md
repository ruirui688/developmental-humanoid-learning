# C4 A：raw / public-guard 身体模型冻结开发协议

本协议与独立审计已在 A 物理结果未知时冻结；正式入口 `FORMAL_EXECUTION_FROZEN=True`。实际执行仍须先通过 clean HEAD、tracked 原字节与 PD 来源绑定，再构造环境。合成测试只有实现证据，下列科学门不随正式结果变更，collector 不自行计算或修改这些门。

## 固定条件与信息边界

development seeds 0/1/2（均已见），reset seeds 3757552657 / 1641411168 / 2001025171。仰卧，原生八轴顺序中的左肩 j0、左肘 j1，另外六轴请求恒零。baseline 接触、每轴 ±0.5 N m；20 ms 控制调用由 10 个 2 ms 子步组成。环境与保护参数固定。

每个 trial fresh environment/reset，独立支付 100 次零力矩前缀。前缀结束的原生角度直接作为 qref，不裁剪或缓存；按公开关节范围中较大可用距离确定 s，等距取正。共同前缀的 qref、方向须严格相同，否则该 trial 失败，不能修配。前缀只用原保护；active 结束时任一目标轴 abs(q−qref) >= .12 rad 或 abs(v) >= 1 rad/s 触发 StudyAbort，等号也触发。

所有模型与动作选择只接收当前原生 q/v、已知请求 u、公开 range 与当前任务目标。公开 G 在控制起点以 q <= L+.03 或 q >= U−.03 阻断向外请求，先 clip±.5，原生 q 不裁。guard basis 用 G/h(G) 替换 u/h(u)。它不等于真实 20 ms 内平均输入；环境 guard 每 2 ms 执行。MPC 每次数学预测均在自己预测起点重新计算 G，未来实际角度、实际力矩、子步 guard 均值、接触与隐藏参数只能写诊断日志，不进入特征、更新或控制。

## 24 个 trial 与共享校准

每 seed 顺序固定为 calibration、prediction、nominal_raw、learned_raw、nominal_guard、learned_guard、PDselected、zero。两条名义模型分别匹配 raw/guard basis 并冻结；两条学习模型各自独立 cold 初始化，只有 calibration 更新。

校准 400 active，20 个 20-step block：前五肩单轴、再五肘单轴、再五同方向、末五反方向；每五块幅度 .125/.25/.375/.5/.25 N m。每块 slot0 正脉冲、slot10 负脉冲，其余零，即 1正/9零/1反/9零，逐轴乘固定 s。选择来自此前已归档短脉冲开发，2/8 三 seed 停止、1/9 三 seed 完整；此前 2586 调用 / 25860 子步 / 0 更新独立计账，不并入本轮收益。

每个完整校准 transition 用同一 ID、同一原生 next-v 依次更新 learned_raw、learned_guard。各模型原始 diagonal_hinge5、速度连续性/力矩响应初始化、P100I、lambda1、hinge.25 和 endpoint Euler 不变；原 pair 原子 RLS 与 shared update 核心不改。每模型两个 head 原子发布；跨模型后者失败时保留前者已提交状态。前缀或不足 10 子步的区间不更新。完整 terminal 区间可以更新与评分，但校准不标 completed，不发布评估模型。

校准全部完成后冻结 clone。独立 prediction 只有一条 100-active 物理轨迹，同时评分四模型与 persistence；五块形状 (1,0)/(0,1)/(1,1)/(1,−1)/(1,1)，幅度 .125/.25/.375/.5/.375，仍为 1/9。独立 prediction 每模型每控制起点只预测一次，step 后评分。calibration 的 preupdate_prediction 实际在 step 返回后，由原 RLS 在提交更新前计算；仅用本区间开始 q/v、已知请求和更新前参数，next-v 只进入更新标签及评分，不进入该预测。它是同区间的因果 preupdate 诊断，不声称调用发生在物理 step 之前；从 RLS 返回值评分，不额外 predict。绘图、summary 或审计不得重复拟合或调用在线模型来补报告。

六条控制各 200 active。当前目标前 100 为 qref+s*.04，后 100 为 qref+s*.08；无切换预告，不可行目标失败而不裁。四条 MPC 全用原 FixedPairMPC（H15、9×9 离散向量、原成本/边界/fallback/tie-break）；每条只在相应模型中选择动作。MPC 正常返回时额外一次当前起点诊断预测独立计账；数学候选预测另计。PDselected 只有本轮独立双轴网格已验证候选可用，无旧组合 PD 默认值；zero 请求恒零。

## PD 来源与源码冻结

正式固定路径为 `src/developmental_physics/guard_pair_development.py`、`docs/GUARD_PAIR_DEVELOPMENT_PROTOCOL.md`、`scripts/audit_guard_pair_development.py` 和 `src/developmental_physics/pd_selection_binding.py`。PD selection 为 `results/cpu_validation/2026-10-11_pair_pd/selection.json`，同目录 manifest.json/first_audit.json。不得预填未知候选。

PD helper 验证独立 selection 原字节、manifest/audit SHA、audit validated_selection、picked 与所选候选/增益一致、来源 8D/姿态/目标/权限/seed 条件及原 PD 协议身份。raw trace 不逐步重读；来源身份数据按明确 API 一次读取。正式 collector 要求 clean HEAD、所有依赖 tracked、每份归档原字节等于 HEAD blob，然后才构造环境。ZIP 包含整个 physics Python 包、body asset、pyproject、当前协议与独立 auditor 及其实际公共辅助代码、PD selection/helper/manifest/audit 及核验需要的来源身份原件。源码 ZIP 与逐文件 SHA 单独记录。

## 失败、停止与计账

普通环境停止和 StudyAbort 保留结束区间，不补跑。校准失败时该 seed 的 prediction、learned_raw、learned_guard 依赖 blocked；nominal_raw、nominal_guard、PDselected、zero 继续并支付自己的前缀。中断、OSError、trace 写盘失败为 fatal，剩余计划 blocked。模型/规划失败记录 attached structured accounting；原子提交前后中断按实际状态计 committed scalar 数，不把失败记成零成本。

调用尝试数、已完成控制区间、已执行子步、未返回子步、返回未写盘区间、各 phase 努力与未知实际努力分别记录。partial 末端目标误差保留但不混入完整区间 RMSE。请求努力按实际 paid substeps 积分，实际努力只从有效完整历史计，缺失部分明确 lower bound。fallback 仍为零请求并计次数；饱和、终止、原生观测、公开输入映射与模型前后 fingerprint 全部保留。

| 完整新增上限 | 数量 |
|---|---:|
| trial | 24 |
| 控制调用 / 子步 | 7500 / 75000 |
| scalar / vector RLS 更新 | 4800 / 2400 |
| 独立 prediction pair / scalar | 1200 / 2400 |
| RLS 内部 preupdate pair / scalar | 2400 / 4800 |
| 四 MPC 数学预测 pair / scalar 上限 | 2916000 / 5832000 |
| 控制起点诊断 pair / scalar 上限 | 2400 / 4800 |

失败按实际成本；RLS、MPC、诊断预测成本分别记录，不把数学调用混为环境交互。无 policy、gain、gate、教师或演示更新。A 后续耦合 B 单独协议与预算，不在本轮偷加。

## 冻结与首次交付

协议、独立 auditor 与 PD 绑定核验已完成；提交并推送这一冻结检查点后，从 clean commit 首次运行一次，保留停止、异常及实际费用，不补跑。发展 seed 成功不能称未见泛化、技能成熟或真机安全。公开规则收益与同 basis 的 RLS 收益分开比较；raw→guard 的总差不能全算学习。合成测试只证明实现、账本和故障路径，不能证明物理科学门通过。

## root 预先冻结的 A 科学门

raw 与 guard 各自独立判身体学习贡献：所需 calibration、单 prediction、匹配 nominal 控制、learned 控制在三个 seed 都完整，无 stop、error 或非法区间；prediction 每 seed 每 axis 速度 RMSE <= .8 倍匹配 nominal。tracking 每 seed 每 axis 及 joint 必须严格改善；三个 seed 的原始 axis 均值和 joint 均值各改善 >=20%。tracking denominator 为零时门失败，不能以截短 RMSE、零动作或少付费通过。这个单 prediction 是新的开发门，不称旧 low/full 门已复现。

每 basis 的 PD 比较另判：先通过本 basis 身体学习贡献门，PD 与所需 trial 全部完整；learned 每 seed 每 axis/joint 均不劣于 PD，joint 原始均值改善 >=5%，实际绝对与平方努力均值各 <=1.05 倍 PD。PD 对应 baseline 数值为零时，仅 candidate 数值也为零才允许相应不劣/努力项通过。PD 被选中是强基线可用的证据，不自动代表 A 的优势。

nominal_guard 与 nominal_raw 的差作为公共规则诊断独立报告。四模型/persistence 在独立 prediction 上的误差、自身控制一步误差、2/5/15 步自由递推、域外、分段末20区间及完整 risk/effort/fallback 诊断，由独立 auditor 从原件离线数学重算，不调用在线模型的 predict，不更新模型。诊断不补充新的采用门，也不把 raw→guard 总差算为学习收益。
