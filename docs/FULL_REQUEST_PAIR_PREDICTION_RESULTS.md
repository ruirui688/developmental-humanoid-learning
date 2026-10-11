# FR3A：FR3A首次新bank独立预测

从clean `2584ed5dfcbea6ae3fc472f47101c55fb0561e7d` 首次执行一次，保存状态 **completed**；保存原预测门通过。实际新增21,000控制返回/21,000确认子步/24,000在线scalar提交；首新保存核验passed、680,623项/0失败。

[事前冻结协议](FULL_REQUEST_PAIR_LEARNING_PROTOCOL.md) · [根归档](../results/cpu_validation/2026-10-12_full_request_pair_prediction/manifest.json) · [唯一实验输入](../results/cpu_validation/2026-10-12_full_request_pair_prediction/report_inputs.json)

开发seed8001/8002/8003按冻结顺序，不宣称全局未使用或最终留出。原free root/仰卧8轴身体、理想感觉、公开guard/保护、2ms PD64/Kd4_4、固定刺激与任务目标均为先验。没有任务教师、预训练策略、PPO或GPU。接触只资格/诊断，紧凑模型只含两轴q/v和已知final requests，不能宣称全身状态闭合、安全或真机学习。

## 原独立预测门与全部保存RMSE

以下直接转录保存checks与原RMSE，百分比仅格式化已保存fraction。H10v/H150q要求每seed两轴严格改善、各轴三seed原RMSE算术均值改善≥20%；H150v及H20/H50 q/v每seed两轴不劣。H1/H10q只报告，完整优先、不部分排名。

| 保存门 | gated/available/passed | cold肩/肘 | learned肩/肘 | 保存改善 |
|---|---|---|---|---|
| 8001/H1q | false/true/true | 8.629422044e-06/1.65369817e-05 | 5.813427582e-06/1.163950474e-05 | 不可评 |
| 8002/H1q | false/true/true | 8.629414154e-06/1.653701509e-05 | 5.813461636e-06/1.163958592e-05 | 不可评 |
| 8003/H1q | false/true/true | 8.623688464e-06/1.655323415e-05 | 5.834680522e-06/1.168371065e-05 | 不可评 |
| 8001/H1v | false/true/true | 0.004314711022/0.008268490848 | 0.002906713791/0.005819752371 | 不可评 |
| 8002/H1v | false/true/true | 0.004314707077/0.008268507543 | 0.002906730818/0.00581979296 | 不可评 |
| 8003/H1v | false/true/true | 0.004311844232/0.008276617074 | 0.002917340261/0.005841855324 | 不可评 |
| 8001/H10q | false/true/true | 0.0001591754463/0.0002993787081 | 0.0001084940489/0.0002178479687 | 不可评 |
| 8002/H10q | false/true/true | 0.0001591743269/0.0002993782171 | 0.0001084937069/0.0002178479984 | 不可评 |
| 8003/H10q | false/true/true | 0.000158533386/0.0002991123651 | 0.000108376735/0.0002178942892 | 不可评 |
| 8001/H10v | true/true/true | 0.008691519097/0.01611306136 | 0.005687799387/0.01137081768 | 不可评 |
| 8002/H10v | true/true/true | 0.008691441283/0.01611302648 | 0.005687743054/0.01137075444 | 不可评 |
| 8003/H10v | true/true/true | 0.008646089953/0.01609517551 | 0.005662170793/0.01134165901 | 不可评 |
| three_seed_raw_RMSE_mean/H10v | true/true/true | 0.008676350111/0.01610708778 | 0.005679237745/0.01136107704 | 34.5435%/29.4654% |
| 8001/H20q | true/true/true | 0.0002855906607/0.0005274561916 | 0.0001786163541/0.0003553023387 | 不可评 |
| 8002/H20q | true/true/true | 0.0002855880821/0.0005274547991 | 0.0001786145288/0.0003553001221 | 不可评 |
| 8003/H20q | true/true/true | 0.0002841545314/0.0005267527462 | 0.0001778418853/0.000354359507 | 不可评 |
| 8001/H20v | true/true/true | 0.008189508924/0.01470186317 | 0.005563269868/0.01110962187 | 不可评 |
| 8002/H20v | true/true/true | 0.008189409043/0.0147017876 | 0.005563187795/0.01110950478 | 不可评 |
| 8003/H20v | true/true/true | 0.008136227201/0.01466515343 | 0.005526343375/0.01105494358 | 不可评 |
| 8001/H50q | true/true/true | 0.0006482503678/0.00113712067 | 0.0002909792404/0.0005797374395 | 不可评 |
| 8002/H50q | true/true/true | 0.0006482429579/0.001137115631 | 0.0002909726449/0.000579727302 | 不可评 |
| 8003/H50q | true/true/true | 0.0006444997609/0.00113467893 | 0.0002881155726/0.000575262453 | 不可评 |
| 8001/H50v | true/true/true | 0.008670776529/0.01459010566 | 0.005606850415/0.01129086078 | 不可评 |
| 8002/H50v | true/true/true | 0.008670672788/0.01459003996 | 0.005606765178/0.01129073896 | 不可评 |
| 8003/H50v | true/true/true | 0.008623453987/0.01455853688 | 0.00556828297/0.0112336475 | 不可评 |
| 8001/H150q | true/true/true | 0.002035774741/0.003449347018 | 0.000480540434/0.0009882574017 | 不可评 |
| 8002/H150q | true/true/true | 0.002035757373/0.00344933658 | 0.000480525656/0.0009882358622 | 不可评 |
| 8003/H150q | true/true/true | 0.002033346389/0.00344441672 | 0.0004737375138/0.000979244602 | 不可评 |
| three_seed_raw_RMSE_mean/H150q | true/true/true | 0.002034959501/0.003447700106 | 0.0004782678679/0.0009852459553 | 76.4974%/71.4231% |
| 8001/H150v | true/true/true | 0.009160752876/0.01638667278 | 0.005926396994/0.01195143947 | 不可评 |
| 8002/H150v | true/true/true | 0.009160602196/0.0163866329 | 0.005926308308/0.01195131142 | 不可评 |
| 8003/H150v | true/true/true | 0.009151767365/0.01636900154 | 0.005886376613/0.01189185343 | 不可评 |

全部三个seed×两模型×五H的q/v两轴保存向量如下（完整时共60个RMSE向量）；不可用和未尝试仍列出。

| seed | H/时距 | 模型 | available/observed/planned origins | q肩/肘 rad | v肩/肘 rad/s |
|---|---|---|---|---|---|
| 8001 | 1/2ms | cold | true/100/100 | 8.629422044e-06/1.65369817e-05 | 0.004314711022/0.008268490848 |
| 8001 | 1/2ms | learned | true/100/100 | 5.813427582e-06/1.163950474e-05 | 0.002906713791/0.005819752371 |
| 8001 | 10/20ms | cold | true/100/100 | 0.0001591754463/0.0002993787081 | 0.008691519097/0.01611306136 |
| 8001 | 10/20ms | learned | true/100/100 | 0.0001084940489/0.0002178479687 | 0.005687799387/0.01137081768 |
| 8001 | 20/40ms | cold | true/99/99 | 0.0002855906607/0.0005274561916 | 0.008189508924/0.01470186317 |
| 8001 | 20/40ms | learned | true/99/99 | 0.0001786163541/0.0003553023387 | 0.005563269868/0.01110962187 |
| 8001 | 50/100ms | cold | true/96/96 | 0.0006482503678/0.00113712067 | 0.008670776529/0.01459010566 |
| 8001 | 50/100ms | learned | true/96/96 | 0.0002909792404/0.0005797374395 | 0.005606850415/0.01129086078 |
| 8001 | 150/300ms | cold | true/86/86 | 0.002035774741/0.003449347018 | 0.009160752876/0.01638667278 |
| 8001 | 150/300ms | learned | true/86/86 | 0.000480540434/0.0009882574017 | 0.005926396994/0.01195143947 |
| 8002 | 1/2ms | cold | true/100/100 | 8.629414154e-06/1.653701509e-05 | 0.004314707077/0.008268507543 |
| 8002 | 1/2ms | learned | true/100/100 | 5.813461636e-06/1.163958592e-05 | 0.002906730818/0.00581979296 |
| 8002 | 10/20ms | cold | true/100/100 | 0.0001591743269/0.0002993782171 | 0.008691441283/0.01611302648 |
| 8002 | 10/20ms | learned | true/100/100 | 0.0001084937069/0.0002178479984 | 0.005687743054/0.01137075444 |
| 8002 | 20/40ms | cold | true/99/99 | 0.0002855880821/0.0005274547991 | 0.008189409043/0.0147017876 |
| 8002 | 20/40ms | learned | true/99/99 | 0.0001786145288/0.0003553001221 | 0.005563187795/0.01110950478 |
| 8002 | 50/100ms | cold | true/96/96 | 0.0006482429579/0.001137115631 | 0.008670672788/0.01459003996 |
| 8002 | 50/100ms | learned | true/96/96 | 0.0002909726449/0.000579727302 | 0.005606765178/0.01129073896 |
| 8002 | 150/300ms | cold | true/86/86 | 0.002035757373/0.00344933658 | 0.009160602196/0.0163866329 |
| 8002 | 150/300ms | learned | true/86/86 | 0.000480525656/0.0009882358622 | 0.005926308308/0.01195131142 |
| 8003 | 1/2ms | cold | true/100/100 | 8.623688464e-06/1.655323415e-05 | 0.004311844232/0.008276617074 |
| 8003 | 1/2ms | learned | true/100/100 | 5.834680522e-06/1.168371065e-05 | 0.002917340261/0.005841855324 |
| 8003 | 10/20ms | cold | true/100/100 | 0.000158533386/0.0002991123651 | 0.008646089953/0.01609517551 |
| 8003 | 10/20ms | learned | true/100/100 | 0.000108376735/0.0002178942892 | 0.005662170793/0.01134165901 |
| 8003 | 20/40ms | cold | true/99/99 | 0.0002841545314/0.0005267527462 | 0.008136227201/0.01466515343 |
| 8003 | 20/40ms | learned | true/99/99 | 0.0001778418853/0.000354359507 | 0.005526343375/0.01105494358 |
| 8003 | 50/100ms | cold | true/96/96 | 0.0006444997609/0.00113467893 | 0.008623453987/0.01455853688 |
| 8003 | 50/100ms | learned | true/96/96 | 0.0002881155726/0.000575262453 | 0.00556828297/0.0112336475 |
| 8003 | 150/300ms | cold | true/86/86 | 0.002033346389/0.00344441672 | 0.009151767365/0.01636900154 |
| 8003 | 150/300ms | learned | true/86/86 | 0.0004737375138/0.000979244602 | 0.005886376613/0.01189185343 |

FR3A只校准及独立条件预测，没有匹配MPC控制。未来保存final requests用于离线条件输入，未来实际q/v只评分。原FR1通过与FR2负结果保持；本阶段控制flags默认false表示尚未声明控制成功。

主任务另公开一次过早FR3B入口的strict-clean source gate拒绝：A归档尚未提交，0环境构造/物理/模型/fit；[该零物理源拒绝原件保留](../results/cpu_validation/2026-10-12_full_request_pair_prediction/control_source_failure/preservation_manifest.json)。这是root提供的工程事实，writer未读取该记录；它不改写A保存预测通过，也不作为B已取得物理结果。先完成A检查点提交推送，再启动已冻结B的首次物理执行。

## 全部trial、接触资格与实际努力

未尝试、停止与异常完整保留，未知值不补零。接触只资格/报告，不证明连续承重、因果或安全；actual为已保存2ms actuator_torque端点样本，不是未测连续积分。

| seed | trial | status/native完整/域资格 | 已返回/计划 | 停止/异常 |
|---|---|---|---|---|
| 8001 | calibration | completed/true/true | 5000/5000 | 无 |
| 8001 | prediction | completed/true/true | 2000/2000 | 无 |
| 8002 | calibration | completed/true/true | 5000/5000 | 无 |
| 8002 | prediction | completed/true/true | 2000/2000 | 无 |
| 8003 | calibration | completed/true/true | 5000/5000 | 无 |
| 8003 | prediction | completed/true/true | 2000/2000 | 无 |

| seed/trial | phase | 记录/计划 | 已付/已观察/unknown接触 | 左臂正端点 | feet正端点 | other正端点 | 资格 |
|---|---|---|---|---:|---:|---:|---|
| 8001/calibration | prefix | 1000/1000 | 1000/1000/0 | 951 | 0 | 985 | true |
| 8001/calibration | active | 4000/4000 | 4000/4000/0 | 4000 | 0 | 4000 | true |
| 8001/prediction | prefix | 1000/1000 | 1000/1000/0 | 951 | 0 | 985 | true |
| 8001/prediction | active | 1000/1000 | 1000/1000/0 | 1000 | 0 | 1000 | true |
| 8002/calibration | prefix | 1000/1000 | 1000/1000/0 | 946 | 0 | 985 | true |
| 8002/calibration | active | 4000/4000 | 4000/4000/0 | 4000 | 0 | 4000 | true |
| 8002/prediction | prefix | 1000/1000 | 1000/1000/0 | 946 | 0 | 985 | true |
| 8002/prediction | active | 1000/1000 | 1000/1000/0 | 1000 | 0 | 1000 | true |
| 8003/calibration | prefix | 1000/1000 | 1000/1000/0 | 950 | 0 | 985 | true |
| 8003/calibration | active | 4000/4000 | 4000/4000/0 | 4000 | 0 | 4000 | true |
| 8003/prediction | prefix | 1000/1000 | 1000/1000/0 | 950 | 0 | 985 | true |
| 8003/prediction | active | 1000/1000 | 1000/1000/0 | 1000 | 0 | 1000 | true |

| seed/trial | phase | 努力完整/已捕获 | actual absolute Nm·s | actual squared Nm²·s | unknown子步 |
|---|---|---|---:|---:|---:|
| 8001/calibration | prefix | true/1000 | 0 | 0 | 0 |
| 8001/calibration | active | true/4000 | 0.2992953565 | 0.07190548118 | 0 |
| 8001/prediction | prefix | true/1000 | 0 | 0 | 0 |
| 8001/prediction | active | true/1000 | 0.0904058605 | 0.02480842431 | 0 |
| 8002/calibration | prefix | true/1000 | 0 | 0 | 0 |
| 8002/calibration | active | true/4000 | 0.2992849107 | 0.07190576464 | 0 |
| 8002/prediction | prefix | true/1000 | 0 | 0 | 0 |
| 8002/prediction | active | true/1000 | 0.09040565844 | 0.02480848102 | 0 |
| 8003/calibration | prefix | true/1000 | 0 | 0 | 0 |
| 8003/calibration | active | true/4000 | 0.3046170643 | 0.07220113146 | 0 |
| 8003/prediction | prefix | true/1000 | 0 | 0 | 0 |
| 8003/prediction | active | true/1000 | 0.09215985885 | 0.02486792403 | 0 |

## 全部保存费用与首审

| 保存counter | 值 |
|---|---:|
| GPU_training_seconds | 0 |
| MPC_decision_attempts | 0 |
| MPC_decision_exceptions | 0 |
| MPC_decision_returns | 0 |
| RLS_scalar_update_commits | 24000 |
| RLS_vector_update_attempts | 12000 |
| RLS_vector_update_commits | 12000 |
| RLS_vector_update_exceptions | 0 |
| RLS_vector_update_returns | 12000 |
| audit_contact_force_query_attempts | 165154 |
| audit_contact_force_query_returns | 165154 |
| audit_contact_pair_inspections | 165154 |
| audit_contact_snapshot_attempts | 21000 |
| audit_contact_snapshot_returns | 21000 |
| audit_geom_name_query_attempts | 165154 |
| audit_geom_name_query_returns | 165154 |
| batch_fit_calls | 0 |
| body_model_build_attempts | 9 |
| body_model_build_returns | 9 |
| body_model_clone_attempts | 3 |
| body_model_clone_returns | 3 |
| body_model_fingerprint_attempts | 24 |
| body_model_fingerprint_returns | 24 |
| body_model_snapshot_attempts | 12015 |
| body_model_snapshot_returns | 12015 |
| calibration_pd_request_attempts | 12000 |
| calibration_pd_request_returns | 12000 |
| captured_native_endpoints | 21000 |
| captured_substep_endpoint_forward_returns | 21000 |
| collector_asset_read_bytes | 20580 |
| collector_asset_reads | 6 |
| confirmed_physics_substeps | 21000 |
| control_call_attempts | 21000 |
| control_call_exceptions | 0 |
| control_call_returns | 21000 |
| cpu_seconds | 66.015625 |
| environment_constructor_attempts | 6 |
| environment_constructor_returns | 6 |
| gate_file_read_attempts | 3 |
| gate_file_read_returns | 3 |
| gate_json_parses | 3 |
| gate_read_and_hash_bytes | 18620 |
| git_query_attempts | 21 |
| git_return_bytes | 306509 |
| independent_prediction_axis_RMSE_vector_computations | 60 |
| independent_prediction_feature_guard_projection_attempts | 124680 |
| independent_prediction_feature_guard_projection_returns | 124680 |
| independent_prediction_pair_prediction_attempts | 124680 |
| independent_prediction_pair_prediction_returns | 124680 |
| independent_prediction_scalar_prediction_attempts | 249360 |
| independent_prediction_scalar_prediction_returns | 249360 |
| output_manifest_file_read_attempts | 1 |
| output_manifest_file_read_returns | 1 |
| output_manifest_read_and_hash_bytes | 23975649 |
| paid_interval_serialized_bytes | 263980273 |
| paid_interval_write_attempts | 42000 |
| paid_interval_write_returns | 42000 |
| physical_asset_bytes_read | 41160 |
| physical_asset_read_returns | 12 |
| physical_identity_attempts | 12 |
| physical_identity_returns | 12 |
| prediction_pd_request_attempts | 3000 |
| prediction_pd_request_returns | 3000 |
| reset_attempts | 6 |
| reset_returns | 6 |
| rls_preupdate_feature_guard_projection_attempts | 24000 |
| rls_preupdate_feature_guard_projection_returns | 24000 |
| rls_preupdate_pair_prediction_attempts | 12000 |
| rls_preupdate_pair_prediction_returns | 12000 |
| rls_preupdate_scalar_prediction_attempts | 24000 |
| rls_preupdate_scalar_prediction_returns | 24000 |
| source_file_read_attempts | 19 |
| source_file_read_returns | 19 |
| source_read_and_hash_bytes | 306468 |
| task_policy_updates | 0 |
| teacher_calls | 0 |
| wall_seconds | 67.6825074 |

内部计时/构造/forward/PD/guard/RLS/restore/snapshot/batch/接触/source与输出边界分别保留原件；未知内部I/O不补零，不宣称20ms实时。首次外进程wall=89.8097976s；Python3.10.11/NumPy2.2.6/MuJoCo3.15.0。

累计 **394,297控制调用 /2,673,970子步**；在线 **94,452**、离线 **7,200**，scalar更新计算合计 **101,652**。基点来自root固定FR3A前历史，加本次保存实际增量，不用计划预算替代停止成本。

主任务首次audit **passed，680,623checks/0failed，60个新RMSE向量**；[audit](../results/cpu_validation/2026-10-12_full_request_pair_prediction/audit_first/audit.json) · [指标复核](../results/cpu_validation/2026-10-12_full_request_pair_prediction/audit_first/metric_recheck.json)。audit事实仅由root CLI传入，writer不打开audit文件。保存一致不代替科学门。

## 下一步与边界

完成A首审、报告检查及检查点提交推送后，继续在A数据前已冻结的FR3B；controller、模型配方、seed、原门不改。 阶段检查与正常提交推送后立即继续active目标。

scientific_adoption、old_free_root_C4_validation、c4_scientific_validation、c4_contact_scientific_validation、c5_scientific_dependency_released保持false。C4最终新留出及C5–C7尚未验收；零停止不能证明安全。全部停止、异常、未尝试及不利时距见本报告与完整JSON，未重新算RMSE/门、fit、模型或物理。
