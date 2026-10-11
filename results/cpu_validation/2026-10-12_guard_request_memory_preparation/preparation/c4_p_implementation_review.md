# C4 P 单次静态实质审查

初稿审查身份（对同一次读取字节计算 SHA256）：

| 文件 | 字节 | SHA256 |
|---|---:|---|
| scripts/develop_guard_request_memory_transition.py | 28197 | aab753ffaa721c8019791fe60a04f13e7a2070e995e2d78f5437b4d92a7a5ac9 |
| docs/GUARD_REQUEST_MEMORY_TRANSITION_DEVELOPMENT_PROTOCOL.md | 5871 | 7b9dca23f6b8c66244f22d84d7873bd38f94007e77fefb83d51d0f86b185b213 |

只静态阅读这两个文件，并定点核对 pinned support.restore_K 与 core.continuous /
feature_and_prior / summarize / development_gate 的调用契约。不读取真实 trace、W、
参数载荷或旧科学指标；不执行合成、拟合、预测或物理；不提出其他候选或 lag。
首次有限 self-check 由父任务执行并保存；本 reviewer 未执行或读取其实际输出。

## 已核对的主要语义

- P31 仅追加同 trial 紧邻上一已知 requested_torque 的两受控轴原值，未再次 clip/
  guard。既有当前 guard/hinge/prior 保留，新增列的先验系数是零。
- 训练仍直接使用 K 已保存 Phi400×29 与 Delta400×22。support.restore_K 严格核对
  100..499 的 ordered training IDs、C400计数、feature/state顺序和原fingerprint；
  P 的历史循环顺序与这些 IDs 对应，没有重生标签或重拟合 K。
- 第一校准行/第一预测原点均使用同 trial prefix99 请求；其余使用 step−1。
  parser 的 trial/step/ID约束与 continuous 的同trial、相邻step、完整端点、
  前序无停止及 native端点连续检查共同保证合法来源；没有跨trial或补零。
- 递推初始化显式传入 previous_v2 与 past_request2。每步构造特征后才把记忆推进为
  该步原已知 request[:2]，previous_v 推进为旧 current v；未来 x22 全部自身递推。
  不读未来真实感觉或实际力矩；保存未来请求仍是披露的离线oracle条件。
- K/D只恢复并预测，前后 fingerprint 核对；P拟合新31×22权重，未修改 saved K
  Phi/Delta/weights。D仅恢复冻结sparse11。
- summarize / dual_gate 只用临时 pure-helper 名字映射，并把结果恢复 P22/K22/D11；
  两个完整旧规则子门保留。失败/通过都不释放C4/C5或科学采用标志。
- 源码图使用精确helper pins与committed bytes；输入沿用绑定N支持函数的九原件。
  拟合/预测尝试及付费在计算前记账，失败主路径保留parameters/predictions/run/
  metrics/manifest/failure输出。以下小修订是该保存合同的必要补充。

## 三个已交父任务的小修订

1. **非有限 partial 的序列化。** 初稿在矩阵/weights .tolist()后才有限验证；
   失败 record 可留下 NaN/Inf，最后 allow_nan=False 序列化又在主try外失败，导致
   paid/failure无法落盘。父任务也独立发现此项，已要求作者用显式JSON安全编码保存
   非有限位置/失败语义，并做一次直接payload验证，不再fit。
2. **完整 clean 声明。** 初稿 sources 使用 git status --porcelain
   --untracked-files=no；这仅核tracked状态，与协议“clean”声明不完全一致。
   建议直接使用完整 --porcelain，保留 exact HEAD 和全部 committed bytes 核对。
3. **历史 preflight 的 partial。** 初稿 history/history_ids 直到400行全部成功才挂入
   record；中途缺失历史时已消费的合法请求/ID丢失。建议在循环前把空列表挂入record，
   随消费追加；usable计数在成功后赋400或逐行推进，固定分母另行声明。不得以此修订
   过滤行、改C400人口或补造缺失历史。

这三项针对身份/失败证据合同，不要求读取真实payload、扩大框架或新增科学诊断。
未观测到实际载荷失配。本文不是正式执行、数学复现或科学门通过证明。

## 最终三处定点封口：ready

作者停止修改后，对最终两个文件各一次字节读取/哈希，仅输出并核对上述三处修订及
对应协议，不重复一般审查；两次最终文件读取共36,700字节。

| 文件 | 最终字节 | 最终 SHA256 |
|---|---:|---|
| scripts/develop_guard_request_memory_transition.py | 30497 | cae9a9fdd4dd2c1563f2163e40bd8edcb8906ce2743e5c90960d5fa20d50491c |
| docs/GUARD_REQUEST_MEMORY_TRANSITION_DEVELOPMENT_PROTOCOL.md | 6203 | cbb04927f77fc43cc0539b7acc23c4a9e9366866e867d1963cd2f86cb658375a |

- 失败 writer 在 failed 状态下递归使用 nonfinite_float 显式标签编码 NaN/±Inf，
  保留原 failure；成功状态保持原严格有限序列化。直接 failed payload 保存 case
  不追加 fit；局部 solve-failure paid 在 finally 合并。
- source 检查已使用完整 git status --porcelain。
- training_fixed_count=400，usable从0随合法历史返回推进；history/ID列表已在400
  循环前挂入record，途中失败保留已消费partial。
- 协议计时排除范围已明确包含所有最终输出序列化/写盘。

三处最终修订确认完成，交父任务准备归档；本 review 封口后不再修改。
有限合成检查由父任务通知为首次通过，本文不重评其计算或科学意义。
