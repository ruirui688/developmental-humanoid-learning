# C4 D 候选：同数据 single-lag 原生速度差诊断

本轮已从本协议冻结提交首次完成；实际结果与唯一读取计量补充见[结果报告](GUARD_LAG_OFFLINE_DEVELOPMENT_RESULTS.md)。以下首段保留首次执行前状态，不修改已执行配方或重放数据。

正式开发离线协议，必须从本协议与代码的明确clean提交首次执行。纯数学11D
helper的8项手写检查通过；evaluator的最终7项人工检查、独立auditor的15项
人工契约检查及6项最终schema/失败费用检查通过。所有中间源码和尝试保留，
未对真实C数据拟合或预测。提升仅开启正式入口、绑定生产来源，不重复已通过
数学矩阵。本阶段不宣称闭环收益、新留出或 C5 通过；已有C保存值/协方差
代数诊断单独保留在C归档。

## 问题与唯一候选

C 两组校准均完整，continuation 的共同脉冲预测优于 sparse，但其控制仅
4 active 后肘速度停止；sparse 在106 active 位置停止。三个 seed 均保留。
continuation 肘只有29个非零 start-G 完整区间/400，veto 只有1次；不能称
veto 广泛抑制激励或把失败直接归于动作少。增大剂量没有验证持续控制。

静态环境使用直接 motor/gear1，没有显式马达滤波或指令延迟。两轴模型
省略其余身体自由度和接触上下文。历史可以代理遗漏的状态或非线性；
即使预测改善，也不能据此识别马达延迟、摩擦机制或完整身体 Markov 状态。

唯一固定结构为原 coupled9 的九列末尾增加
`dv_prev0 = v_t0 - v_(t-1)0`、`dv_prev1 = v_t1 - v_(t-1)1`，每输出11参数。
两个 lag 系数初始均为0；原九列顺序/own prior/cross prior/hinge .25、
dt .02、P100I、lambda1、float64、两头原子更新、endpoint Euler 保持。
无 lag 网格、参数约束投影、忘记率/尺度调优、动作修改或新增传感器。
Gram 的标准化只用于诊断；实际 RLS 始终使用原尺度的11列。

## 固定输入与来源

C collection commit：`5ea8df42b09588845760daf0dc1f270aef2a87f1`。
只采用已通过首审的 C 原件；不读取/重放 A/B cal，不重拟合旧模型。
输入绑定 summary：`external/guard_exploration_20261011_summary_01/summary.json`。
summary SHA256：`dbc368dc628cb5785415c8b27416215e628a892cf550284a681447f9867aa4af`。
first audit SHA256：`985137b28d9ee6eb19c98c80e807c815d0d79273a46c938b5f1e4c59be3f33ac`。
原 auditor SHA256：`962a928b5d643ed2a3d4da20da2940a9a4e17932818c859beb204f11bf59ffa3`。
root 归档路径可迁移；六 raw 文件必须精确匹配绑定 summary 的原 SHA。
执行前固定独立 C 原件绑定核验，不再运行旧全档 auditor。

seed固定0/1/2；分别使用 sparse/continuation 的自身400完整 cal interval，
各新建一个冷11D模型，共6个模型。原 nominal9/sparse9/continuation9 只读
已发布 snapshot。PD/zero/nominal/learned 控制数据只作预测评估，绝不拟合。
PD 自带任务能力及其轨迹分布单列；不得作为“儿童自主校准”教师或安全接管。

## 先诊断已有九列与系数

先于新拟合，对两 cal 每 seed 的原完整 native 起点构造九列矩阵。
报告原单位列范围、均值/方差、start-G正/负/零数、hinge非零数、实际剂量。
非恒定列中心化并除以其中心化 RMS；常数列保留1，零方差列保留0并显式标记。
保存标准化 Gram `Xz.T @ Xz / N`、奇异值、列相关性和数值秩。
秩 tolerance 固定 `eps_float64 * max(N,p) * largest_singular_value`；
缺秩时条件数记为无限及原因，不改变旧最低激励门，不事后设 rank 采用门。

从已保存 cal snapshot 读取100/200/300/400更新处的系数与变化量；不重拟合9D。
报告每 head 原尺度和列尺度加权的系数变化，不将变化直接解释为学习稳定。
令 A为两头velocity两列、B为q-qref两列，报告固定 guard branch 的线性模态
`F4 = [[I+.02B, .02A], [B, A]]` 的全部特征值、谱半径和非正规性诊断。
这些是局部数学诊断，未包含 guard 跳变或接触切换；不强制谱半径<=1。

## 历史初始化、更新与冻结

每 fresh trial active0 的 v_t 来自prefix99返回端点，v_(t-1)来自prefix98返回端点；
两者必须完整、原生且连续。不得零填历史、跨episode拼接或用未来端点初始化。
cal active后续历史只由已经返回的原生端点向前移位，labels为本次完整 next-v。
每组按原400条顺序只拟合一次；更新失败保留零/两头原子费用与剩余未执行计划。
参数冻结后不再更新；校准preupdate只用更新内部已有预测，不额外报告predict。
原9D模型不重拟合、不改变 fingerprint；各11D模型独立单列offline更新和内部预测。
报告11列Gram以及 lag系数和相同局部模态，作为同一个固定候选的诊断。
令 C为两lag列，扩展状态 `[q-qref,v,v_prev]`，模式矩阵为
`F6=[[I+.02B,.02(A+C),-.02C],[B,A+C,-C],[0,I,0]]`。
任何以后MPC候选 rollout，都必须每步以自己的预测v更新history，不能保持初值。

## 固定开发离线预测评估

统一五个predictor：原 nominal9/sparse9/continuation9、lag_sparse11/lag_continuation11。
在每 seed 的共同prediction100及五条已存控制轨迹上分别报告，不汇成选择分数。
H固定1/2/5/15。每起点用本次native q/v及过去native v初始化，之后纯开环滚动。
每个未来步的输入是原保存的最终 requested command；不是未来actual/applied力矩。
未来request仅在这项“条件于原请求序列”的离线诊断中可见；actor不能预知它。
G始终在该模型自己的predicted q重新计算；中途不以真值纠正q/v/history。

只对同episode中连续、完整返回的真实窗口评分；终止端点可以作为最后标签，
但不能跨stop继续。所有模型共享固定有效窗口，不裁掉某模型误差大的窗口。
某条4-step控制没有H5/H15窗口时明确unavailable，不补齐或使用其他轨迹替代。
逐seed/axis/H报告q/v RMSE、signed bias、最大误差、完整窗口数和数学失败数。
有nonfinite模型预测时保留失败；该整项RMSE记不可评价，不能删除失败后排序。
另按已知start-G正/负/零及持续非零请求长度作预固定描述分组，样本不足显式报告。
已存且fingerprint/输入精确匹配的一步预测直接复用；其余新增数学调用单列。
每起点每模型仅滚至最高可用H，复用其H1/2/5/15端点，不为报告重复计算。

## 冻结来源与独立审计

正式首次运行前先提交协议、helper、evaluator和独立auditor。从明确的clean
完整commit，由root排他生成`external/`下runtime source-freeze JSON；记录该commit
及每个源码、支持脚本、协议和依赖配置的SHA256，并核对工作字节等于Git blob。
evaluator只读该freeze及独立执行context，不调用Git。输出source ZIP保留全部
冻结成员及runtime freeze原字节；独立首审另以`git show`核对该提交。
commit写入运行时原件，避免把未来提交值写入tracked协议造成自指循环。

独立auditor只使用标准库，不导入在线helper、不调用物理或MPC，不重新执行C首审。
在D真实结果未知前固定标量重算容差为`abs 1e-10 + rel 5e-10`，模态特征
多项式的scaled residual容差为`1e-8`；float64/BLAS算术差异与数值病态显式报告。
原始输入身份、history、fingerprint、保存预测复用、窗口和成本仍精确核对。
首审之后的描述汇总仅缓存读取原件、检查字节绑定、复制保存指标；不再fit、
predict或重跑audit。数学一致性通过不产生新的科学采用门，也不解除C5依赖。

## 费用、边界与后续

新物理0、旧9D refit0、策略/增益/门控更新0、PD教师调用0、真机0。
新offline RLS最多2400 vector/4800 scalar，内部preupdate最多2400 pair/4800 scalar。
评估上限按3seed×(pred100+5control200)×5模型×H15计算：247500 pair/495000 scalar。
RLS与评估分账；失败尝试、未知头级下界、复用预测数及所有未评分窗口均保留。
Gram/特征/模态线性代数费用单列，不能写作零计算；无MPC select或仿真调用。

本阶段仅比较同开发数据下的记忆候选，不把旧C数据称为新留出。
报告所有逐轴正负结果、可辨识性和模态；不由停止前误差宣布闭环优势。
若后续采用11D进入控制，必须另冻结同权限、任务、H15、81候选、停止和原科学门，
付新交互，并使用模型自己的预测history。任何经典反馈或独立安全层新增作用
必须匹配对照、单列先验和贡献，不能据此将学习模型失败改写为学习成功。
