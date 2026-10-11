# V：固定 future-native18 夹持敏感性诊断

本协议在首执行前冻结。V 只使用 U 保存原件，转录 Q22/U22 自身闭环，与两条新 oracle18 混合回放比较。Qphi50/C400/双位置头优化器修订族已经由 U 负结果封口；V 不重新拟合、扫描、续训、增加特征或调用新物理。V 完成后关闭此 oracle 路线，下一项工作应是有依据、预算有限的新物理设计。

## 来源和共享先验

唯一科学输入根为
`results/cpu_validation/2026-10-12_guard_bounded_lbfgs_position_transition`，
U 首次干净提交为 `7358ff9f583d9a20460e94c914cd8ea172c9780a`。
正式首执行读取该根的 `manifest.json`、`raw/manifest.json`、
`raw/run.json`、`raw/parameters.json`、`raw/predictions.jsonl`、
`raw/metrics.json` 各一次。源码内冻结 bytes/SHA，核对根/raw manifest、完整 commit
与 U 原件记录的共享 helper 身份；不读 C 原始物理、D 模型、K/Q/T 原件或 U checkpoint。

Q50×22 恢复自 U parameter 的 `frozen_Q_weights50x22`，
U50×22 恢复自 `selected_weights50x22`；
引用原 qref、Q/U 指纹、状态/特征顺序及仅两 q 头变化。
恢复前后核对同一指纹，U 其他20头应与 Q 精确相同。不重复 U 优化器、拟合、
旧 K/D 门或旧失败工程的检查。

公共 guard 只来自已绑定 Urun 的
`baseline_restorations.D11[].public_guard` 元数据，核对三个 seed 的完整 spec。
该字段的使用不恢复 D 模型。公开肩范围
[-1.7453292519943295, 1.7453292519943295] rad、肘范围
[0, 2.356194490192345] rad，margin .03 rad、request clip ±.5 Nm。
保留原当前控制起点 guard、.02 s prior 和已知保存 request/qref。这些均是共享先验。
原原生状态含8关节 q/v 和6维 IMU，没有 orientation。实际连续轨迹、其公共环境、
历史开发费用和源证据仍为 U 所引用的既有记录，不能因 V 归零。

新代码复用固定 R loader、Q `rollout50` 单步前向与 K/N 纯 helper；
不用 R 的运动学位置覆盖，不 import U/T/S 拟合运行时。
所有 helper 与协议源码 SHA 固定。NumPy CPU；无 torch/scipy、模拟器、训练或控制调用。

## 人口和四条通道

固定 seed 0/1/2，H=1/2/5/15，origin=0..100-H（含两端）。
每个 model/seed 381 窗口。通道名为：

- `Q22_saved_self`：U 保存 Q 自身22闭环原输出/误差的受控部分，直接转录。
- `U22_saved_self`：U 保存 U 自身22闭环原输出/误差的受控部分，直接转录。
- `Q22_oracle18`：冻结 Q 全22前向加以下非terminal18覆盖。
- `U22_oracle18`：冻结 U 全22前向加相同覆盖。

自身记录2,286，新 oracle 记录2,286，共4,572条请求。
controlled indices 固定为 (0,1,8,9)，即肩/肘 q/v；
oracle indices 固定为 (2,3,4,5,6,7,10,11,12,13,14,15,16,17,18,19,20,21)。
每通道/seed/H/受控轴一组，共192组。
源缺失、歧义、停止、非法连续窗口、模型或标签不可用仍在固定分母，
不做 C 回退，不用 common-finite 子集排名。

自身96个受控 metric 组只从 U `raw/metrics.json` 转录并改通道名，
不重新算旧 RMSE 或门；源 metric 缺失或与转录记录数量不一致保留不可用状态。
只为新 oracle 的4个受控终点误差生成96个新描述组。
全部方法使用同一源 origin/请求/目标/qref 与原始停止记录。

## 每步唯一操作

每个合法源窗口沿用保存 `initial_x22`、`previous_v2`、
`history_transition_ids`、`requested_transition_ids`、`requested_sequence8`。
previous_v 的初值是该窗口原合法过去，不跨 trial，不补零。

1. 原 Q mapping 和固定 Q/U 权重产生下一 full22。即使18头随后丢弃，也完整计算并计账。
2. full22 必须全有限，且原 forward 成功；此检查早于任何 label 查询或 oracle 覆盖。
   原18头非有限不能被实际值遮掉，保存已付费前向、失败映射及原数组的显式非有限编码。
3. previous_v 取原 forward 的旧当前受控 v；后续保持预测受控 v 历史，
   绝不把 actual controlled v 注入 history。
4. 仅当该步不是窗口 terminal，才将下一状态的指定18列覆盖为对应实际原生 endpoint。
   controlled4 保持原预测；terminal18 不覆盖、不评分。
5. 只在窗口 terminal 对 controlled4 评分。

oracle label pool **仅** U22 H1 保存 `actual_endpoint_x22`。
origin o 的窗口第 j 步非terminal label 为 H1 origin o+j，且 H1 唯一 request ID
必须精确等于该窗口第 j 个 request ID，同 seed/trial/连续端点。
H1 源窗口必须 available/scored、未在 endpoint 停止；否则该 oracle 窗口不可用。
H1 自身无需任何 oracle label。每个 H1 controlled terminal 和误差必须与已保存自身输出精确相同；
600对逐记录精确同一性是必需工程约束，不重新算自身闭环。

future18 是未来特权诊断量，可能通过身体耦合或 IMU 含受控未来信息。
混合的预测 controlled4 和实际18不保证物理一致。改善只能描述该混合回放
对未来原生尾部的敏感性，不能识别闭环误差的唯一因果来源，也不能保证部署能复现。
不得把本诊断当成新特征、任务教师、可部署信息、控制门通过或科学采纳。

## 固定描述规则与封口

分别对 Q source 和 U source 作判断，不挑最好模型：

- H15 两个 q 轴：每 seed 都严格改善，且该轴三个 seed 平均相对改善 ≥20%。
- H2/H5 的 q/v、H15 的 v：每 seed 不更差。
- 需要完整固定人口及 H1 逐记录精确一致；任何不可用不算通过。
- 不回放旧 K/D 开发门，不释放 C4/C5；所有 scientific/adoption flags 均 false。

该规则只是固定的诊断敏感性阈值，不能转化为科学门。
V 后不追加其他 oracle 子集、source、组合或同 bank 优化。
无论描述阈值是否满足，都应公开结论及限制，再形成有依据的新物理协议。

## 费用、输出与首次执行

在全部窗口可用时，新增 full22 forward12,408，非terminal18覆盖10,122，
future18 scalar use182,196。每个完整前向的18个未评分头同样付费，
terminal18也计算但不覆盖/评分。oracle controlled error9,144个，
新 metric组96；自身转录2,286记录/9,144误差/96metric组。
新物理、控制、RLS、拟合、优化objective/gradient及自身重算均为0。
文件读/hash/parse、源码验证、helper load、wall/CPU独立记账；
原 U 成本只转录引用，不重复计算。停止/失败前已经完成的前向和覆盖保留计账；
理论预算与实际费用分别报告。

脚本写 `parameters.json`（仅恢复引用、qref/publicguard与前后指纹）、
`metrics.json`、`run.json`、确定性mtime0的 `predictions.jsonl.gz`、
payload manifest，失败另存 `failure.json`。预测保存原前向全22、历史、
非terminal覆盖标签身份和混合状态；不把未评分18的误差伪造为0。
拒绝已有输出及输入/输出目录重叠。正式执行要求干净完整40位源码 commit，
冻结源码/协议后从干净提交首次一次执行，完整原件和首次 stdio 封存。

self-check 只运行六个新 layer 夹具：非terminal18与controlled4隔离、预测history、
H1不查label、非有限18不能被掩盖、missing label保留付费失败、
跨trial/ID不匹配不回退。夹具注入简单前向，不 import/调用旧模型、
拟合、mapping或旧科学原件。准备阶段只静态检查，不提前执行这六项。

源码：[diagnose_guard_oracle_tail.py](../scripts/diagnose_guard_oracle_tail.py)。
先前协议：[U固定有限记忆方向修订](GUARD_BOUNDED_LBFGS_POSITION_TRANSITION_DEVELOPMENT_PROTOCOL.md)。
