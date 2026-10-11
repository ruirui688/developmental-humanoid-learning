# C4 双关节数学核心交叉审查

2026-10-11；只读核对 ignored draft；不是 C4 正式协议、物理验收或已通过的科学门。

## 范围与来源

完整读取 `external/c4_staging/local_pair_model.py`、`test_local_pair_model.py`、`external/c4_development_design_review.md`，并核对既有 scalar `src/developmental_physics/local_model.py` 的通用初始化、RLS、MPCConfig 与 FixedLocalMPC。没有修改 tracked 文件，没有读取任何留出数据、reset 或运行物理；没有使用真实标签拟合或重放。Python导入集合检查确认未导入 MuJoCo。

首次源码/测试 SHA256：`6af00b7c08f69a5c03929ecb016ee37d9ff85284ee49222abc598b4008ef1523` / `172917b4dd2f944bcfdde442e456bb92e4441ac67d8771b2d064b6f3763b060c`。

单state提交修订后的当前 SHA256：`81e0c9147bbfd7f825f14ad7439e6752c021bc08922abd04589a89b59fc509df` / `69fdb61395ceb4408cf8806e1cf2ab716551730019ac286c008d8305d418f68d`。本审查没有重跑实施代理已经完成的全套测试；下面三个数值/故障例是新增的纯合成算术诊断，另有一次提交边界 opcode 故障注入。

## 与设计一致的部分

- coupled 两输出都读同一个九维 `v0,v1,q0-qref0,q1-qref1,u0,u1,h(u0),h(u1),1`，各有自己的 theta/P；没有未来实际力矩、接触、隐藏动力学或 next_v 输入到 predict。next_v 只作为 update 标签。diagonal 每输出五维，与旧 HingeBodyModel 一致；两个模型都处理同一完整向量转移的两个标签。
- cold coupled output0 的 v0/u0 系数分别1/.02，output1对应 v1/u1，cross 初值0；diagonal 两输出各为旧 hinge5 初值。P=100I、lambda1、折点.25、endpoint Euler、dt.02一致。qref 原值（包括近肘下限的负偏移）保留，不裁成0。
- 新增独立手算以 P=100I、九维特征做一次 RLS，theta/P 相对实现最大差 `3.552713678800501e-15`。这是合成标签算术检查，不是机器人辨识结果。
- 同模型先算两个完整proposal、检查维数/有限，再提交；第二 head 的同步 proposal 失败不会提交第一个 head。未提交proposal不计RLS更新。
- 跨模型采用固定 mapping 顺序而非全体回滚；已成功的 diagonal 两个输出保留，后来 coupled失败也保留所有模型快照。向量 update_count 每次成功加1、scalar count加2、两个 output count同步。两个结构共用600向量转移时每seed4×600=2400标量更新，不等于2400真实交互。
- 二维 MPC 每轴保留旧 H15/9候选/权重/权限；81个常向量候选，不预告未来目标，预测递推自己的状态。位置/速度/努力/首步变化成本分别按两轴求和；forecast bounds为 qref±.15 与公开限位±.03 的交集，target bounds为 qref±.15 与公开限位内缩.03的交集。肘保持 qref+.04 合法，保持近下限qref会被拒绝。
- 精确决胜为 `cost,sum(abs(u)),signed u0,signed u1`，无后验epsilon；全拒绝回退(0,0)。初始可分离模型已有合成测试逐轨迹/动作/费用对齐两个scalar MPC，这属于数学 sanity check，不代表耦合后等价。
- 完整可行搜索上限每decision1215 pair预测、2430 scalar head预测；规划边界/预测失败仍计attempt。head0失败各候选 scalar attempt1/success0，head1失败attempt2/success1；unknown adapter失败另报scalar下界。C4-B原18trial/1800decisions完整上限为2,187,000 pair /4,374,000 scalar；不包含日志一步预测/更新内部预测，也不是物理调用。

## 已修复的 fatal proposal ledger

第二head抛 OSError 前，head0 已计算但未提交的proposal原先只存在原异常 `pair_update_accounting`，shared nested `failure_record`仅type/message。纯合成复现得到原proposal长度1、shared遗漏该细节，diag count2/coupled0仍正确。

实施代理已在 ignored draft 修订 wrapper 优先保留原异常附加pair ledger，再用to_dict或普通type/message；新定向测试通过（实施代理报告1pass/16 deselected，.07s）。本次静态复读确认修订存在。没有改变模型算法、训练数据、共享顺序或统计门。

## 已修复的提交边界原子性

旧多次 STORE_ATTR 提交会在theta写后中断而保留旧P/count；此前纯opcode故障已经复现。当前修订改为单个冻结 `_PairParameterState(theta,covariance,vector_update_count)`，数组readonly，以唯一 `self._state=next_state` 发布。update、snapshot、clone、两head预测捕获同一个state引用；记录在提交前构造，异常ledger以实际state恢复0或2标量提交。

本次仅短复查修改范围及定向合成测试：`-k 'commit_boundary or shared_boundary or binds or fatal'`，6 passed /17 deselected，.07s。测试精确命中唯一提交opcode的前/后边界，确认theta/P/count全旧或全新；shared nested failure_record保留原pair ledger，已完成diagonal与实际提交的coupled分别记账。未重复全套review或MPC测试，未导入物理或读留出。

## 已提交但调用返回失败的计账

新增纯合成callee包装：coupled先成功原子update再抛OSError。shared completed_records只含diagonal，而两个snapshot的scalar count分别2/2。这种快照保留正确，但 collector/auditor必须按所有模型的最终快照及参数链恢复4次实际成功更新，不能把failed_model或没有返回item自动记为0。原生已付转移仍只一次，成功更新与缺失遥测/指标分开计账。建议正式collector包含该回归。

## 结论

九维输入、cold prior、同步两输出proposal、跨模型部分成功和二维MPC配置/计数整体符合草稿设计；fatal nested ledger及提交中断的单state原子性已修复，本报告只确认数学核心与故障计账，不授予C4物理或科学验收通过。后续正式协议仍需冻结校准顺序、合法完整interval、失败依赖、原生StudyAbort、预算、距离/覆盖、两独立科学门及所有风险口径，再做物理采集。
