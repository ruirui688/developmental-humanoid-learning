# FR4A：FR4A首次PD锚点候选独立预测

从clean `f4fca3f4236acddc92a25c6707f9c29150ee3ca6` 首次执行一次，保存状态 **completed**；保存原预测门通过。实际新增21000控制返回/21000确认子步/24000在线scalar提交；首新保存核验passed、680,475项/0失败。

[事前冻结协议](PD_ANCHOR_PAIR_LEARNING_PROTOCOL.md) · [根归档](../results/cpu_validation/2026-10-12_pd_anchor_pair_prediction/manifest.json) · [唯一实验输入](../results/cpu_validation/2026-10-12_pd_anchor_pair_prediction/report_inputs.json)

开发seed8101/8102/8103按冻结顺序；公开source/docs首次搜索无命中，raw/非公开历史未知，不宣称全局未用或最终留出。原free root/仰卧8轴身体、理想感觉、公开guard/保护、2ms PD64/Kd4_4、固定刺激与任务目标均为先验。没有任务教师、预训练策略、PPO或GPU。接触只资格/诊断，紧凑模型只含两轴q/v和已知final requests，不能宣称全身状态闭合、安全或真机学习。

## 保存状态、异常与全部未尝试

保存status=completed；complete_population=true。科学门、首保存核验与执行完整性分别报告，不用失败的默认false覆盖旧阶段事实。

保存顶层failure=None；各trial停止、异常、缺失仍须逐项报告，不能据此声称安全。

保存unattempted_seeds=[]；下方固定三个seed的所有planned trial均列出，缺失不补零。

## 原独立预测门与全部保存RMSE

以下直接转录保存checks与原RMSE，百分比仅格式化已保存fraction。H10v/H150q要求每seed两轴严格改善、各轴三seed原RMSE算术均值改善≥20%；H150v及H20/H50 q/v每seed两轴不劣。H1/H10q只报告，完整优先、不部分排名。

| 保存门 | gated/available/passed | cold肩/肘 | learned肩/肘 | 保存改善 |
|---|---|---|---|---|
| 8101/H1q | false/true/true | 8.630276653e-06/1.653280267e-05 | 5.809421833e-06/1.162961681e-05 | 不可评 |
| 8102/H1q | false/true/true | 8.629054717e-06/1.653846586e-05 | 5.815004941e-06/1.164319432e-05 | 不可评 |
| 8103/H1q | false/true/true | 8.626037308e-06/1.654768151e-05 | 5.826476651e-06/1.166783338e-05 | 不可评 |
| 8101/H1v | false/true/true | 0.004315138326/0.008266401333 | 0.002904710917/0.005814808403 | 不可评 |
| 8102/H1v | false/true/true | 0.004314527359/0.008269232932 | 0.002907502471/0.005821597161 | 不可评 |
| 8103/H1v | false/true/true | 0.004313018654/0.008273840754 | 0.002913238325/0.00583391669 | 不可评 |
| 8101/H10q | false/true/true | 0.0001593089461/0.0002994384115 | 0.0001085399694/0.0002178469306 | 不可评 |
| 8102/H10q | false/true/true | 0.0001591248536/0.0002993566727 | 0.0001084790734/0.0002178492661 | 不可评 |
| 8103/H10q | false/true/true | 0.0001587740074/0.0002992106161 | 0.0001084061007/0.0002178742835 | 不可评 |
| 8101/H10v | true/true/true | 0.00870074892/0.01611738002 | 0.005694953645/0.01137889617 | 不可评 |
| 8102/H10v | true/true/true | 0.008687995279/0.01611150593 | 0.005685288266/0.01136798858 | 不可评 |
| 8103/H10v | true/true/true | 0.008663257446/0.01610162486 | 0.0056705675/0.01135149766 | 不可评 |
| three_seed_raw_RMSE_mean/H10v | true/true/true | 0.008684000548/0.01611017027 | 0.005683603137/0.01136612747 | 34.5509%/29.4475% |
| 8101/H20q | true/true/true | 0.0002859010474/0.0005276291085 | 0.000178852255/0.0003555900949 | 不可评 |
| 8102/H20q | true/true/true | 0.0002854744596/0.0005273941327 | 0.0001785355094/0.0003552040899 | 不可评 |
| 8103/H20q | true/true/true | 0.0002846842149/0.0005270022168 | 0.0001780845131/0.0003546618475 | 不可评 |
| 8101/H20v | true/true/true | 0.008201687292/0.01471134148 | 0.005573719244/0.01112445745 | 不可评 |
| 8102/H20v | true/true/true | 0.008185026948/0.01469850641 | 0.005559621068/0.01110440676 | 不可评 |
| 8103/H20v | true/true/true | 0.008155415641/0.01467781809 | 0.005538365421/0.01107333091 | 不可评 |
| 8101/H50q | true/true/true | 0.0006491672069/0.001137753535 | 0.0002918276318/0.0005810390428 | 不可评 |
| 8102/H50q | true/true/true | 0.0006479195123/0.001136896857 | 0.0002906867178/0.000579288715 | 不可评 |
| 8103/H50q | true/true/true | 0.0006458081933/0.00113552158 | 0.0002890290208/0.0005767142837 | 不可评 |
| 8101/H50v | true/true/true | 0.008683947058/0.01459837358 | 0.005617683718/0.01130625651 | 不可评 |
| 8102/H50v | true/true/true | 0.008666186816/0.01458718976 | 0.005603059246/0.01128543969 | 不可评 |
| 8103/H50v | true/true/true | 0.008638831451/0.01456939744 | 0.005580868133/0.01125286772 | 不可评 |
| 8101/H150q | true/true/true | 0.002038338737/0.003450674625 | 0.0004824137985/0.0009910467 | 不可评 |
| 8102/H150q | true/true/true | 0.002035050443/0.003448883661 | 0.0004798816798/0.0009873063795 | 不可评 |
| 8103/H150q | true/true/true | 0.002032776662/0.003446122886 | 0.0004760040014/0.0009820703858 | 不可评 |
| three_seed_raw_RMSE_mean/H150q | true/true/true | 0.002035388614/0.003448560391 | 0.0004794331599/0.0009868078218 | 76.4451%/71.3849% |
| 8101/H150v | true/true/true | 0.009183811338/0.01639184497 | 0.005937676075/0.01196765696 | 不可评 |
| 8102/H150v | true/true/true | 0.00915456966/0.01638490728 | 0.005922452861/0.01194574665 | 不可评 |
| 8103/H150v | true/true/true | 0.009140045888/0.01637504174 | 0.005899402041/0.01191171552 | 不可评 |

全部三个seed×两模型×五H的q/v两轴保存向量如下（完整时共60个RMSE向量）；不可用和未尝试仍列出。

| seed | H/时距 | 模型 | available/observed/planned origins | q肩/肘 rad | v肩/肘 rad/s |
|---|---|---|---|---|---|
| 8101 | 1/2ms | cold | true/100/100 | 8.630276653e-06/1.653280267e-05 | 0.004315138326/0.008266401333 |
| 8101 | 1/2ms | learned | true/100/100 | 5.809421833e-06/1.162961681e-05 | 0.002904710917/0.005814808403 |
| 8101 | 10/20ms | cold | true/100/100 | 0.0001593089461/0.0002994384115 | 0.00870074892/0.01611738002 |
| 8101 | 10/20ms | learned | true/100/100 | 0.0001085399694/0.0002178469306 | 0.005694953645/0.01137889617 |
| 8101 | 20/40ms | cold | true/99/99 | 0.0002859010474/0.0005276291085 | 0.008201687292/0.01471134148 |
| 8101 | 20/40ms | learned | true/99/99 | 0.000178852255/0.0003555900949 | 0.005573719244/0.01112445745 |
| 8101 | 50/100ms | cold | true/96/96 | 0.0006491672069/0.001137753535 | 0.008683947058/0.01459837358 |
| 8101 | 50/100ms | learned | true/96/96 | 0.0002918276318/0.0005810390428 | 0.005617683718/0.01130625651 |
| 8101 | 150/300ms | cold | true/86/86 | 0.002038338737/0.003450674625 | 0.009183811338/0.01639184497 |
| 8101 | 150/300ms | learned | true/86/86 | 0.0004824137985/0.0009910467 | 0.005937676075/0.01196765696 |
| 8102 | 1/2ms | cold | true/100/100 | 8.629054717e-06/1.653846586e-05 | 0.004314527359/0.008269232932 |
| 8102 | 1/2ms | learned | true/100/100 | 5.815004941e-06/1.164319432e-05 | 0.002907502471/0.005821597161 |
| 8102 | 10/20ms | cold | true/100/100 | 0.0001591248536/0.0002993566727 | 0.008687995279/0.01611150593 |
| 8102 | 10/20ms | learned | true/100/100 | 0.0001084790734/0.0002178492661 | 0.005685288266/0.01136798858 |
| 8102 | 20/40ms | cold | true/99/99 | 0.0002854744596/0.0005273941327 | 0.008185026948/0.01469850641 |
| 8102 | 20/40ms | learned | true/99/99 | 0.0001785355094/0.0003552040899 | 0.005559621068/0.01110440676 |
| 8102 | 50/100ms | cold | true/96/96 | 0.0006479195123/0.001136896857 | 0.008666186816/0.01458718976 |
| 8102 | 50/100ms | learned | true/96/96 | 0.0002906867178/0.000579288715 | 0.005603059246/0.01128543969 |
| 8102 | 150/300ms | cold | true/86/86 | 0.002035050443/0.003448883661 | 0.00915456966/0.01638490728 |
| 8102 | 150/300ms | learned | true/86/86 | 0.0004798816798/0.0009873063795 | 0.005922452861/0.01194574665 |
| 8103 | 1/2ms | cold | true/100/100 | 8.626037308e-06/1.654768151e-05 | 0.004313018654/0.008273840754 |
| 8103 | 1/2ms | learned | true/100/100 | 5.826476651e-06/1.166783338e-05 | 0.002913238325/0.00583391669 |
| 8103 | 10/20ms | cold | true/100/100 | 0.0001587740074/0.0002992106161 | 0.008663257446/0.01610162486 |
| 8103 | 10/20ms | learned | true/100/100 | 0.0001084061007/0.0002178742835 | 0.0056705675/0.01135149766 |
| 8103 | 20/40ms | cold | true/99/99 | 0.0002846842149/0.0005270022168 | 0.008155415641/0.01467781809 |
| 8103 | 20/40ms | learned | true/99/99 | 0.0001780845131/0.0003546618475 | 0.005538365421/0.01107333091 |
| 8103 | 50/100ms | cold | true/96/96 | 0.0006458081933/0.00113552158 | 0.008638831451/0.01456939744 |
| 8103 | 50/100ms | learned | true/96/96 | 0.0002890290208/0.0005767142837 | 0.005580868133/0.01125286772 |
| 8103 | 150/300ms | cold | true/86/86 | 0.002032776662/0.003446122886 | 0.009140045888/0.01637504174 |
| 8103 | 150/300ms | learned | true/86/86 | 0.0004760040014/0.0009820703858 | 0.005899402041/0.01191171552 |

FR4A只校准及独立条件预测，没有匹配MPC控制。未来保存final requests仅作离线条件输入，未来actual q/v只评分。FR1/FR3A通过及FR2/FR3B负结果保持；本阶段控制stagekeys默认false表示未声明控制成功，不覆盖历史事实。

## 全部trial、接触资格与实际努力

未尝试、停止与异常完整保留，未知值不补零。接触只资格/报告，不证明连续承重、因果或安全；actual为已保存2ms actuator_torque端点样本，不是未测连续积分。

| seed | trial | status/native完整/域资格 | 已返回/计划 | 停止/异常 |
|---|---|---|---|---|
| 8101 | calibration | completed/true/true | 5000/5000 | 无 |
| 8101 | prediction | completed/true/true | 2000/2000 | 无 |
| 8102 | calibration | completed/true/true | 5000/5000 | 无 |
| 8102 | prediction | completed/true/true | 2000/2000 | 无 |
| 8103 | calibration | completed/true/true | 5000/5000 | 无 |
| 8103 | prediction | completed/true/true | 2000/2000 | 无 |

| seed/trial | phase | 记录/计划 | 已付/已观察/unknown接触 | 左臂正端点 | feet正端点 | other正端点 | 资格 |
|---|---|---|---|---:|---:|---:|---|
| 8101/calibration | prefix | 1000/1000 | 1000/1000/0 | 948 | 0 | 985 | true |
| 8101/calibration | active | 4000/4000 | 4000/4000/0 | 4000 | 0 | 4000 | true |
| 8101/prediction | prefix | 1000/1000 | 1000/1000/0 | 948 | 0 | 985 | true |
| 8101/prediction | active | 1000/1000 | 1000/1000/0 | 1000 | 0 | 1000 | true |
| 8102/calibration | prefix | 1000/1000 | 1000/1000/0 | 954 | 0 | 985 | true |
| 8102/calibration | active | 4000/4000 | 4000/4000/0 | 4000 | 0 | 4000 | true |
| 8102/prediction | prefix | 1000/1000 | 1000/1000/0 | 954 | 0 | 985 | true |
| 8102/prediction | active | 1000/1000 | 1000/1000/0 | 1000 | 0 | 1000 | true |
| 8103/calibration | prefix | 1000/1000 | 1000/1000/0 | 946 | 0 | 985 | true |
| 8103/calibration | active | 4000/4000 | 4000/4000/0 | 4000 | 0 | 4000 | true |
| 8103/prediction | prefix | 1000/1000 | 1000/1000/0 | 946 | 0 | 985 | true |
| 8103/prediction | active | 1000/1000 | 1000/1000/0 | 1000 | 0 | 1000 | true |

| seed/trial | phase | 努力完整/已捕获 | actual absolute Nm·s | actual squared Nm²·s | unknown子步 |
|---|---|---|---:|---:|---:|
| 8101/calibration | prefix | true/1000 | 0 | 0 | 0 |
| 8101/calibration | active | true/4000 | 0.301093958 | 0.07188097532 | 0 |
| 8101/prediction | prefix | true/1000 | 0 | 0 | 0 |
| 8101/prediction | active | true/1000 | 0.09057470169 | 0.02480343434 | 0 |
| 8102/calibration | prefix | true/1000 | 0 | 0 | 0 |
| 8102/calibration | active | true/4000 | 0.2989636014 | 0.07191871805 | 0 |
| 8102/prediction | prefix | true/1000 | 0 | 0 | 0 |
| 8102/prediction | active | true/1000 | 0.09039595268 | 0.0248112048 | 0 |
| 8103/calibration | prefix | true/1000 | 0 | 0 | 0 |
| 8103/calibration | active | true/4000 | 0.3010198854 | 0.072061691 | 0 |
| 8103/prediction | prefix | true/1000 | 0 | 0 | 0 |
| 8103/prediction | active | true/1000 | 0.09143209981 | 0.02484027408 | 0 |

## 四个独立stagekeys与五个科学flags

| 保存key | 保存值 |
|---|---|
| fr4a_prediction_gate_passed | true |
| fr4b_model_contribution_gate_passed | false |
| fr4b_pd_reference_gate_passed | false |
| fr4_free_root_mechanism_validation | false |
| scientific_adoption | false |
| old_free_root_C4_validation | false |
| c4_scientific_validation | false |
| c4_contact_scientific_validation | false |
| c5_scientific_dependency_released | false |

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
| audit_contact_force_query_attempts | 165080 |
| audit_contact_force_query_returns | 165080 |
| audit_contact_pair_inspections | 165080 |
| audit_contact_snapshot_attempts | 21000 |
| audit_contact_snapshot_returns | 21000 |
| audit_geom_name_query_attempts | 165080 |
| audit_geom_name_query_returns | 165080 |
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
| cpu_seconds | 66.546875 |
| environment_constructor_attempts | 6 |
| environment_constructor_returns | 6 |
| gate_file_read_attempts | 3 |
| gate_file_read_returns | 3 |
| gate_json_parses | 3 |
| gate_read_and_hash_bytes | 18620 |
| git_query_attempts | 21 |
| git_return_bytes | 312065 |
| independent_prediction_axis_RMSE_vector_computations | 60 |
| independent_prediction_feature_guard_projection_attempts | 124680 |
| independent_prediction_feature_guard_projection_returns | 124680 |
| independent_prediction_pair_prediction_attempts | 124680 |
| independent_prediction_pair_prediction_returns | 124680 |
| independent_prediction_scalar_prediction_attempts | 249360 |
| independent_prediction_scalar_prediction_returns | 249360 |
| output_manifest_file_read_attempts | 1 |
| output_manifest_file_read_returns | 1 |
| output_manifest_read_and_hash_bytes | 23952659 |
| paid_interval_serialized_bytes | 263865808 |
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
| source_read_and_hash_bytes | 312024 |
| task_policy_updates | 0 |
| teacher_calls | 0 |
| wall_seconds | 68.2051607 |

内部计时/构造/forward/PD/guard/RLS/restore/snapshot/batch/接触/source与输出边界分别保留原件；未知内部I/O不补零，不宣称20ms实时。首次外进程wall=90.5748493s；Python3.10.11/NumPy2.2.6/MuJoCo3.15.0。

累计 **451297控制调用 /2730970子步**；在线 **118452**、离线 **7200**，scalar更新计算合计 **125652**。基点为root显式CLI提供的本阶段前actual累计，只加本次保存实际增量；缺失counter保持unknown，不用计划替代停止成本或补零。

主任务首次audit **passed，680,475checks/0failed，60个新RMSE向量**；[audit](../results/cpu_validation/2026-10-12_pd_anchor_pair_prediction/audit_first/audit.json) · [指标复核](../results/cpu_validation/2026-10-12_pd_anchor_pair_prediction/audit_first/metric_recheck.json)。audit事实仅由root CLI传入，writer不打开audit文件。保存一致不代替科学门。

## 下一步与边界

完成A首审、报告检查及检查点提交推送后，继续在A数据前已冻结的FR4B；controller、模型配方、seed、原门不改。 阶段检查与正常提交推送后立即继续active目标。

scientific_adoption、old_free_root_C4_validation、c4_scientific_validation、c4_contact_scientific_validation、c5_scientific_dependency_released保持false。C4最终新留出及C5–C7尚未验收；零停止不能证明安全。全部停止、异常、未尝试及不利时距见本报告与完整JSON；writer未重算RMSE/门、fit、模型或物理。
