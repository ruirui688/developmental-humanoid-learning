# C4 I：H 保存窗口的因果 native 残差诊断冻结协议

本协议仅检验“上一原始一步速度残差能否修正下一步”这一开发假设。它不发布模型，不运行 MPC，不改变 forecast、目标、动作权限、研究停止或任何旧科学门。`scientific_adoption=false`，C4 未验收，C5 科学依赖保持。

## 固定来源与执行

脚本：`scripts/diagnose_guard_pd_tail_native_residual.py`。协议：本文件 `docs/GUARD_PD_TAIL_NATIVE_RESIDUAL_DIAGNOSTIC_PROTOCOL.md`。二者先检查、提交；再从干净 tracked 状态首次执行一次，显式给出该 I source commit。脚本验证 HEAD 与传入完整 commit 相同，且自身脚本和协议的工作区字节与该 commit 字节相同。失败输出保留，不覆盖、不补跑到通过。

默认输入目录：`results/cpu_validation/2026-10-11_guard_forecast_stop/raw`。只打开以下四个 H 文件：`manifest.json`、`run.json`、`description.json`、`last20.jsonl`。H manifest SHA256 固定为 `b3c9969c6d65987c0993c32e0143a7f5f4e704410d5d4e7cbe423a950b5ed538`；其所列三项允许 payload 的长度与 hash 必须匹配。manifest 中列出的 `intervals.jsonl` 不打开。

H run 必须是 completed、scientific_adoption=false、clean_committed_bytes_verified=true；H diagnostic source commit 固定 `a46633c71e95826835ebc43f0aeaf6d5fdfd19e8`，G physical source commit 固定 `91dcf6c111a87427c8f3fdd8b959d4792b1bb5a2`。I 记录自身 source commit 和两份源字节 SHA256，与上述 H/G 双绑定。只核对 I 必需的来源、字段与末20窗口绑定；不重跑 H 的 forecast/stop 描述、H13 核对或 G 审计。

```powershell
python scripts/diagnose_guard_pd_tail_native_residual.py --source-commit <I完整commit> --output external/c4_i_native_residual_01
```

输出必须是新目录。脚本只依赖 Python 标准库。禁止读 G raw、模型 snapshot、仿真器、额外 H 文件或其他 results；禁止 model predict/fit/RLS、模型候选重构、新物理、增益/参数搜索或正式诊断的准备期执行。

## 固定六 trial 与连续性

固定 `(seed=0,1,2) × (cold11,learned_sparse11)`，trial_id 按 H 保存名称识别，不混方法或 seed。每 trial 仅使用 H `last20.jsonl` 已固定的最后 min(20,实际 active 数) 记录，不扩窗、不访问窗前历史、不删不利末端。H description 的六 trial、末20数量及最后 active index用于窗口绑定。

按文件中每个 trial 的原有记录顺序处理，不排序修复。一个可作为历史的记录必须：完整20 ms（executed_substeps=10、complete_20ms_interval=true），actual_next_qv 和 independent_current_request_prediction.saved_prediction_qv 均可用且是有限 `[q_pair,v_pair]`，prediction_available=true。相邻 pair 还要求 step_index、active_index 同时恰好 +1。H 窗口没有 current-start endpoint 字段，连续性只按上述保存字段确认，不伪造额外端点核查。

每 trial 首记录没有窗内历史，只初始化偏差，不评分、不补0。partial、missing prediction/actual、无可用 prediction 记录中断历史；该行不评分。noncontiguous 的当前完整有效行不评分，但可作为下一个连续 pair 的新历史。重复或乱序绝不跨越使用。终止前最后完整20 ms 行仍可评分，停止不删除付费端点。全部中断原因和未评分记录单列。

## 因果修正与评分

对当前 t 的原基模型预测 `(qhat_t,vhat_t)`，先取上一连续完整记录相对**原基模型**的速度残差 `b_previous = actual_v_previous - base_vhat_previous`。固定：

`corrected_vhat_t = base_vhat_t + b_previous`

`corrected_qhat_t = base_qhat_t + .02 * b_previous`

没有拟合、滤波系数或递归残差。上一偏差永远不取 previous actual-minus-corrected prediction。当前 actual label 只评分当前预测，并在评分后构成下一次可用的原基模型残差；不能进入当前修正。所有预测来自 `independent_current_request_prediction`，包括 fallback 行；不改用 selected_stage0_prediction。

输出每个可评分相邻 pair 的 previous/current index、previous 原速度残差、当前 base/corrected/actual q/v、误差和跨段标志，便于审查当前 label 未进入修正。算法不重新调用模型。

逐 trial × ALL/A/B/CROSS_A_TO_B × q/v × 肩/肘轴报告 pair 数、base/corrected RMSE、MAE、signed actual-minus-prediction bias，以及 RMSE/MAE 相对改善、绝对 bias 变化。A/B 按**当前** active_index<100 判 A，否则 B；A→B 的历史允许，该 pair 计入 ALL 和 B，同时在 CROSS_A_TO_B 单列。空组为 null，并明确 empty；不补零。baseline RMSE=0 时相对改善未定义，不能通过严格改善门。

## 固定开发门与边界

仅 ALL 参与开发门，RMSE 是判门误差。主候选为 learned_sparse11：每个 seed 的两速度轴 corrected RMSE 都严格小于同 pair 的 base RMSE，且每轴三个 seed 的相对 RMSE 改善 `(base-corrected)/base` 的算术平均 >=20%。任一缺少 pair、base=0 或计算非有限则该门不通过并给原因。cold11 按同一规则单列，不合并六 trial、不要求 cold 同时通过才能称 learned 的有限开发可行。

q、MAE、bias、A/B、cross 均只描述，不代替速度主门。B 段的2/4个端点、cold 短窗口、空组不能证明分段有效域或稳定误差规律。即使主门通过，也只支持在这些已见开发窗口中继续研究残差候选；不支持新留出、独立预测门、全任务控制成功、冷启动能力、风险下降或 C4/C5 科学验收。停止轨迹不按误差或少步骤排名，D 旧20%预测门不追认。

## 费用与输出

新增 H 读取次数/原字节、hash 字节、JSON文档与jsonl记录解析数；自身两源读取与字节、Git只读查询/返回字节、实际 wall/CPU分别计账。计 eligible 原速度残差的两 scalar 计算/状态发布、adjacent pair 数、corrected velocity scalar addition、q修正乘法/加法、评分误差插入统计。model_predictions/model_updates/RLS_updates/physics_calls 全部为0，偏差状态计算单列，不能写成零计算。

保存 `adjacent_pairs.jsonl`、`description.json`、`run.json` 和 `manifest.json`；run 保存四输入的长度/hash与双 source binding。异常保存 `failure.json`，原目录不覆盖。wall/CPU测量在最后 run/manifest写盘前结束，这一排除边界明确记录。必要准备测试只使用合成小分支，不读取 H 或执行正式诊断。
