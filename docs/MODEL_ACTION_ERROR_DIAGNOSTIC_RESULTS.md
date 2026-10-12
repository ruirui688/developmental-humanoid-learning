# EF1D：保存一步误差动作尺度诊断首次结果

2026-10-12。首次执行原件及一次轻量保存核对；不重算 J、SVD、delta 或旧指标。

首次保存状态 **completed**，轻量核对 **passed**；源码提交 `8c0397a98ea7bd4bc7169cd0531b14205b0deee5`。完整人口为 2,400 个 H1 模型条目、1,200 个配对 origin。

原件见 [结果 manifest](../results/cpu_validation/2026-10-12_model_action_error/manifest.json)、[首次 run](../results/cpu_validation/2026-10-12_model_action_error/raw/run.json)、[轻量保存核对](../results/cpu_validation/2026-10-12_model_action_error/delivery/verification.json)。冻结[协议](MODEL_ACTION_ERROR_DIAGNOSTIC_PROTOCOL.md)保持原文，本次不是控制实验，也没有新的方法改善门。

## 原汇总的逐组转录

下表仅转录首次 run.result.summaries 的原保存字段。rank 与分支理由使用原分支分母；any/all 可评使用每组原 200 条模型记录分母，不能通过邻盒重复计权宣布模型胜负。

| seed | 控制来源 | 输出模型 | 记录/分支 | rank 0/1/2 | any/all 可评 | 原不可评理由及次数 | delta 全分支均值/最大 Nm | 原权限最小余量均值/最小 Nm |
|---:|---|---|---|---|---|---|---|---|
| 8101 | cold | cold | 200/203 | 0/3/200 | 2/2 | minimum_norm_direction_outside_logged_one_sided_branch:13; minimum_norm_exceeds_shared_permission:33; minimum_norm_leaves_logged_closed_box:201; saved_error_not_in_numeric_image:3 | 1.7256240445327937/37.95231935034607 | 0.21946679401575545/0.0 |
| 8101 | cold | learned | 200/203 | 0/3/200 | 0/0 | minimum_norm_direction_outside_logged_one_sided_branch:31; minimum_norm_exceeds_shared_permission:120; minimum_norm_leaves_logged_closed_box:203; saved_error_not_in_numeric_image:3 | 0.5830279476605215/18.2303694411052 | 0.21946679401575545/0.0 |
| 8101 | learned | cold | 200/200 | 0/2/198 | 1/1 | minimum_norm_direction_outside_logged_one_sided_branch:9; minimum_norm_exceeds_shared_permission:29; minimum_norm_leaves_logged_closed_box:199; saved_error_not_in_numeric_image:2 | 1.332301202210981/37.95231935034607 | 0.2227063058092282/0.0 |
| 8101 | learned | learned | 200/200 | 0/2/198 | 0/0 | minimum_norm_direction_outside_logged_one_sided_branch:25; minimum_norm_exceeds_shared_permission:116; minimum_norm_leaves_logged_closed_box:200; saved_error_not_in_numeric_image:2 | 0.8881798831194523/19.551823055029462 | 0.2227063058092282/0.0 |
| 8102 | cold | cold | 200/203 | 0/3/200 | 0/0 | minimum_norm_direction_outside_logged_one_sided_branch:16; minimum_norm_exceeds_shared_permission:34; minimum_norm_leaves_logged_closed_box:203; saved_error_not_in_numeric_image:3 | 1.9010966430292882/37.935615145399076 | 0.21743072471918215/0.0 |
| 8102 | cold | learned | 200/203 | 0/3/200 | 0/0 | minimum_norm_direction_outside_logged_one_sided_branch:32; minimum_norm_exceeds_shared_permission:120; minimum_norm_leaves_logged_closed_box:203; saved_error_not_in_numeric_image:3 | 0.8062091834650597/19.042110885442387 | 0.21743072471918215/0.0 |
| 8102 | learned | cold | 200/200 | 0/2/198 | 0/0 | minimum_norm_direction_outside_logged_one_sided_branch:9; minimum_norm_exceeds_shared_permission:29; minimum_norm_leaves_logged_closed_box:200; saved_error_not_in_numeric_image:2 | 1.3843902797253689/37.935615145399076 | 0.2207180064145795/0.0 |
| 8102 | learned | learned | 200/200 | 0/2/198 | 0/0 | minimum_norm_direction_outside_logged_one_sided_branch:23; minimum_norm_exceeds_shared_permission:115; minimum_norm_leaves_logged_closed_box:200; saved_error_not_in_numeric_image:2 | 0.9517098957102622/20.005900243914166 | 0.2207180064145795/0.0 |
| 8103 | cold | cold | 200/203 | 0/3/200 | 0/0 | minimum_norm_direction_outside_logged_one_sided_branch:14; minimum_norm_exceeds_shared_permission:36; minimum_norm_leaves_logged_closed_box:203; saved_error_not_in_numeric_image:3 | 2.104522964152337/37.90985037134946 | 0.21307636100687527/0.0 |
| 8103 | cold | learned | 200/203 | 0/3/200 | 0/0 | minimum_norm_direction_outside_logged_one_sided_branch:26; minimum_norm_exceeds_shared_permission:119; minimum_norm_leaves_logged_closed_box:203; saved_error_not_in_numeric_image:3 | 1.1139696965612487/18.02574702919505 | 0.21307636100687527/0.0 |
| 8103 | learned | cold | 200/200 | 0/2/198 | 1/1 | minimum_norm_direction_outside_logged_one_sided_branch:11; minimum_norm_exceeds_shared_permission:26; minimum_norm_leaves_logged_closed_box:199; saved_error_not_in_numeric_image:2 | 1.0526812676515818/37.90985037134946 | 0.21704106609930757/0.0 |
| 8103 | learned | learned | 200/200 | 0/2/198 | 0/0 | minimum_norm_direction_outside_logged_one_sided_branch:26; minimum_norm_exceeds_shared_permission:114; minimum_norm_leaves_logged_closed_box:200; saved_error_not_in_numeric_image:2 | 0.5012477214415011/6.7630310961527424 | 0.21704106609930757/0.0 |

## 首次实际费用

以下逐项转录首次 run.cost，不把零物理/训练写成零计算。

| 费用字段 | 首次保存值 |
|---|---:|
| `H1_model_records` | 2400 |
| `branch_saved_error_scalar_uses` | 4836 |
| `closed_box_membership_checks` | 38400 |
| `cpu_seconds` | 2.28125 |
| `delta_and_unmapped_l2_norm_attempts` | 4836 |
| `delta_and_unmapped_l2_norm_returns` | 4836 |
| `descriptive_distribution_calls` | 48 |
| `descriptive_distribution_value_uses` | 7240 |
| `diagnostic_JSON_encode_attempts` | 2400 |
| `diagnostic_JSON_encode_returns` | 2400 |
| `diagnostic_bytes_written` | 4909083 |
| `diagnostic_hash_byte_uses` | 4909083 |
| `diagnostic_record_write_attempts` | 2400 |
| `diagnostic_record_write_returns` | 2400 |
| `frozen_theta_scalars_read` | 108 |
| `gzip_decode_attempts` | 2 |
| `gzip_decode_returns` | 2 |
| `image_residual_tolerance_evaluations` | 2418 |
| `independent_saved_error_scalar_uses` | 4800 |
| `input_file_read_attempts` | 6 |
| `input_file_read_returns` | 6 |
| `input_hash_calls` | 6 |
| `input_stored_bytes_read` | 30009082 |
| `jacobian_build_attempts` | 2418 |
| `jacobian_build_returns` | 2418 |
| `jacobian_coefficient_scalar_uses` | 19344 |
| `jacobian_entry_scalars` | 9672 |
| `matvec_attempts` | 7254 |
| `matvec_returns` | 7254 |
| `metadata_JSON_parse_attempts` | 3 |
| `metadata_JSON_parse_returns` | 3 |
| `minimum_norm_mapping_attempts` | 2418 |
| `minimum_norm_mapping_returns` | 2418 |
| `other_horizon_records_decoded_without_mathematics` | 9372 |
| `paired_origins` | 1200 |
| `population_summary_identity_uses` | 2400 |
| `prediction_JSON_parse_attempts` | 11772 |
| `prediction_JSON_parse_returns` | 11772 |
| `prediction_decoded_bytes` | 78779518 |
| `prediction_decoded_hash_byte_uses` | 157559036 |
| `prediction_decoded_hash_updates` | 23544 |
| `prediction_decoded_records` | 11772 |
| `rank1_branches` | 30 |
| `rank2_branches` | 2388 |
| `row_algebra_attempts` | 2400 |
| `row_algebra_returns` | 2400 |
| `singular_component_division_attempts` | 4806 |
| `singular_component_division_returns` | 4806 |
| `source_archive_build_attempts` | 1 |
| `source_archive_build_returns` | 1 |
| `source_archive_bytes_written` | 15366 |
| `source_archive_write_attempts` | 1 |
| `source_archive_write_returns` | 1 |
| `source_bytes_read` | 41678 |
| `source_file_read_attempts` | 2 |
| `source_file_read_returns` | 2 |
| `source_git_query_attempts` | 4 |
| `source_git_query_returns` | 4 |
| `source_git_return_bytes` | 41719 |
| `svd_attempts` | 2418 |
| `svd_returns` | 2418 |
| `wall_seconds` | 2.502085199812427 |

交付工具的读取、哈希、JSON/ZIP 解码、复制及文档写入费用单列在[交付 I/O 账](../results/cpu_validation/2026-10-12_model_action_error/delivery/io_cost.json)，不计作新物理或模型预测。

## 科学边界与阶段状态

本诊断只描述冻结模型内部的最小范数局部误差映射。跨原闭盒、超权限或像空间缺口使该映射不可评；rank 1 的最小范数解越盒不排除其它 nullspace 可行解，本次没有搜索。这不能识别真实动作敏感度、接触原因或反事实控制收益；条件数、根存在及局部可评也不能自动批准动态逆补偿。全部邻盒保留，没有 clip、选优、fit/RLS、model.predict 或物理。

EF1B 静态保持候选关闭。C4 原 20% 模型贡献、5% 强 PD、1.05 实际努力门不变；五 science flags false，C4、C5 科学适应、C6/C7 均未验收。累计仍为 **505,297 控制 / 2,784,970 子步**；online118,452+offline7,200=125,652scalar 更新。

持续目标 active。首次交付检查后提交/推送，再由 root 记录有依据的唯一后续判断；本结果不自动开放新控制/物理分支，也不代表持续目标完成。

## 本次发现与下一项决定

学习模型在六个来源组各 200 条记录中，所有相邻盒可评数与存在可评盒数均为 0；全部原邻盒的最小范数映射跨盒。其六组动作修正向量 L2 中位数分别为 0.340644、0.359029、0.345447、0.366736、0.360531、0.376026 Nm。逐轴超权限也已保存，不能只拿向量范数与单轴 ±0.5 Nm 权限比较。冷模型只有三个组分别存在 2、1、1 条可评记录，其余组为 0；这不是控制收益排名。

全部 2,418 个邻盒中 rank 2 为 2,388，rank 1 为 30。多数矩阵满秩并没有使本局部修正可用。本结果拒绝采用当前最小范数同盒补偿，但没有识别真实动作敏感度，也没有排除跨盒求解或其它控制方法。

root 据此确定唯一下一项 PAR1：在仿真中共享完整动作前状态，用事前固定的两轴 ±0.125 Nm 请求干预测量 2 ms 的有限响应，再与冻结模型的响应比较。四个固定 origin × 三个开发 seed，构造新公共 PD 来源与全部预定侧，上限 9,060 控制/子步、0 更新；不重新评分旧控制数据、不称新留出。完整状态复制只属于仿真评估资源，不能提供给部署模型或宣称真机可以精确复位。

PAR1 必须先完成独立协议、最小实现和必要新检查，再冻结推送后首次执行；当前结果没有批准物理执行或控制接入。其后仍继续最早未验收的 C4，C5–C7 的科学依赖保持。
