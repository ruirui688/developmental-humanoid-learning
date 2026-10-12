# IV1 首次原生工具变量动作辨识结果

**首次 completed、退出0，三次拟合均返回 rank 4，但原预测门未通过。** 6 条 fresh trial 完整，本批新增 **15,000 control / 15,000 substep**、6,000 moment pair / **12,000 新 IV scalar 标签用途**、3 次 fit / 24 个动作系数输出；4,329 预测记录与187,020 pair prediction calls 完整，没有停止或异常，`first_failure=null`。

corrected 在 H1 q/v 上的保存误差比 oldlearned 更大，H10及以上的保存检查均未通过；工程完成、rank 4 和零停止不能替代预测、控制或安全验收。此冻结修订没有开放控制候选。本报告只转录四份 fresh JSON 的已有字段，不读取 trace、旧 raw，不重算矩阵/预测/RMSE、旧门或旧审计，不新增统计或拟合。

## 首次身份、任务与原生标签

首次 clean source 为 **`d7eb8508f2872e24212d7e3580951c7c44fe8228`**，`clean_committed_bytes_verified=true`。协议 [INSTRUMENTAL_ACTION_RESPONSE_PROTOCOL.md](INSTRUMENTAL_ACTION_RESPONSE_PROTOCOL.md)：11144 bytes / SHA256 `476e3292b52817ab3c3c8686bb9115b09ae7c17105cf4d0f0f6aed1f0f421e33`；runner 37971 bytes / `a7cd0e7ea7986d29b4fa56ddccef56b894f08f7a7adcbbe719527e7157086e09`；模型实现 9302 bytes / `cb0d3f6314682553fabe2f37b56764bd8098551221e14cbe8f3aece14b014c51`。完成时间 2026-10-12T11:03:21.365834+08:00。

原件入口：[run.json](../results/cpu_validation/2026-10-12_instrumental_action_response/raw/run.json)、[metrics.json](../results/cpu_validation/2026-10-12_instrumental_action_response/raw/metrics.json)、[models.json](../results/cpu_validation/2026-10-12_instrumental_action_response/raw/models.json)、[moments.json](../results/cpu_validation/2026-10-12_instrumental_action_response/raw/moments.json)。完整源代码/依赖及交付记录由归档保留；[27 项轻量保存检查](../results/cpu_validation/2026-10-12_instrumental_action_response/delivery_checks.json)全部通过，检查身份、人口、参数冻结与 ZIP 的提交绑定，未解码 trace、重算拟合或科学门。本报告转录不等于独立数学复核。

CPU Intel64 Family 6 Model 140 Stepping 2, GenuineIntel、8 logical cores；Python 3.10.11、NumPy 2.2.6、MuJoCo 3.15.0、Windows-10-10.0.26200-SP0，GPU_used=false。原模型来源 EF1B 60,924 bytes / `3cfbd871c275a8f5d8a07615a239ee9e8192b5e93dcf35104cf61a01f6a6a992`，EF1B source `f9f500706364aab32bd18047266d4b06358e4473`、FR4A source `f4fca3f4236acddc92a25c6707f9c29150ee3ca6`；只在 fresh models 原件恢复记录中转录，不重读旧模型或旧预测。

每 seed 的辨识为1,000 zero prefix + 2,000 active，A/B各1,000、目标偏移.04/.08rad；公共PD64/Kd4基准clip±.375Nm后加双轴独立±.125Nm，`Generator(PCG64(seed+100000))`，抽样API `rng.integers(0, 2, size=2)`。原2ms/±.5Nm、.12rad/1rad/s StudyAbort及底层保护保持。辨识标签只有连续原生next velocity；`fork_label_uses=0`、`opaque_state_uses=0`，未使用PAR1反事实标签或特权状态。

每 seed 的预测源是独立fresh 1,000 zero prefix + 1,000原pulse/PD目标qref；三个冻结模型在同一保存请求上递推自身q/v。已知未来请求只用于离线条件预测，不是控制器切换预览。seed8101/8102/8103均为既有开发seed，本批不是新最终留出。

| trial | 类型 | planned controls | 首次状态 | 完整阶段接触资格 | stop |
|---|---|---:|---|---|---|
| s8101_identification | identification | 3000 | completed | true | null |
| s8101_prediction | prediction | 2000 | completed | true | null |
| s8102_identification | identification | 3000 | completed | true | null |
| s8102_prediction | prediction | 2000 | completed | true | null |
| s8103_identification | identification | 3000 | completed | true | null |
| s8103_prediction | prediction | 2000 | completed | true | null |

接触资格仅是完整阶段工程资格，接触/实际力矩telemetry不进入actor或拟合标签。共享身体、仰卧/free root、经典PD、目标、公开guard和理想感觉均为披露先验。

## 拟合返回与动作系数

工具特征为 `phi=(G0,G1,hG0,hG1)`，同一步前四种候选的平均给出 `z=phi_actual−mean`；`M=Σouter(z,phi)`为4×4、`Y=Σouter(z,nextv−frozen_statehead)`为4×2。每seed一次 `lstsq(M,Y)` 的4×2 solution转置后替换两head各四个动作系数。每head非动作列 `[0,1,2,3,8]`、qref/guard/hinge/integration保持冻结，不添加ridge或参数扫描。

| seed | samples | fit attempted | 返回rank | 返回singular values（原精度） | rcond | lstsq residuals |
|---|---:|---|---:|---|---|---|
| 8101 | 2000 | true | 4 | (45.32642182703722, 31.970526840818575, 4.435695660696219, 1.6019894329267512) | 2.842170943040401e-14 | [] |
| 8102 | 2000 | true | 4 | (43.744762586455266, 32.045212255316066, 4.170664923744363, 1.4911913457206756) | 2.842170943040401e-14 | [] |
| 8103 | 2000 | true | 4 | (47.21592789810932, 30.810854137062147, 3.959148783717501, 1.454197787134289) | 2.842170943040401e-14 | [] |

空 `lstsq_residuals=[]` 是保存的方阵求解返回，不能称为真实物理残差零或正确识别。M/Y、完整4×2 solution和冻结列声明见 [moments.json](../results/cpu_validation/2026-10-12_instrumental_action_response/raw/moments.json)。本报告没有重新求解或验证矩阵。

下表完整转录三个corrected模型的24个动作系数，列顺序为G0/G1/hG0/hG1；全部18系数、oldlearned/cold原件与预测前后fingerprint在 [models.json](../results/cpu_validation/2026-10-12_instrumental_action_response/raw/models.json)，不为表格重新拟合。

| seed | 速度head | B0 | B1 | H0 | H1 |
|---|---|---|---|---|---|
| 8101 | 肩 | 0.03402642713227079 | -0.060561981077108605 | 0.0007728701574589327 | 0.008661789394366567 |
| 8101 | 肘 | -0.06198242644551944 | 0.12998307502152165 | 0.00995347473641963 | -0.02465252173927656 |
| 8102 | 肩 | 0.03606030749093939 | -0.06027376328366993 | -0.0017099766195630816 | -0.0033860208080467237 |
| 8102 | 肘 | -0.06568251275603537 | 0.1298260212237015 | 0.009382602923464255 | -0.019358462812983788 |
| 8103 | 肩 | 0.03257218162333091 | -0.0658982723586539 | -0.0006022993601749643 | 0.006771017873251852 |
| 8103 | 肘 | -0.05825364980619004 | 0.141325369690227 | 0.004180304457459168 | -0.022398989544225176 |

rank4只说明本次工具矩在固定数值规则下返回满秩，不能视为真实动力学Jacobian或全身模型正确。修正B/H以后，与冻结漂移/耦合head的匹配仍需检验；本次退化不能识别某一个唯一失配原因，也不能以rank4宣布已解决它。

## 全seed、全时距、三模型预测指标

下表逐项转录 `run.seed_results[].prediction_scores.horizons`，没有新增RMSE。q单位rad，v单位rad/s；显示八位有效数字，完整精度保留原件。每个horizon planned origin为100/100/99/96/86，全部模型available；完整人口与 `partial_subset_ranking=false` 保留。预测模型递推条件为 `saved known future requests offline; recursive own predicted q/v`。

| seed | H | 模型 | observed/planned origins | available | q肩 RMSE | q肘 RMSE | v肩 RMSE | v肘 RMSE |
|---|---:|---|---|---|---|---|---|---|
| 8101 | 1 | cold | 100/100 | true | 0.0000086302767 | 0.000016532803 | 0.0043151383 | 0.0082664013 |
| 8101 | 1 | oldlearned | 100/100 | true | 0.0000058094218 | 0.000011629617 | 0.0029047109 | 0.0058148084 |
| 8101 | 1 | corrected | 100/100 | true | 0.0000071768745 | 0.000014855756 | 0.0035884372 | 0.0074278778 |
| 8101 | 10 | cold | 100/100 | true | 0.00015930895 | 0.00029943841 | 0.0087007489 | 0.016117380 |
| 8101 | 10 | oldlearned | 100/100 | true | 0.00010853997 | 0.00021784693 | 0.0056949536 | 0.011378896 |
| 8101 | 10 | corrected | 100/100 | true | 0.00029056122 | 0.00060396565 | 0.022698399 | 0.047325923 |
| 8101 | 20 | cold | 99/99 | true | 0.00028590105 | 0.00052762911 | 0.0082016873 | 0.014711341 |
| 8101 | 20 | oldlearned | 99/99 | true | 0.00017885225 | 0.00035559009 | 0.0055737192 | 0.011124457 |
| 8101 | 20 | corrected | 99/99 | true | 0.00072233358 | 0.0015080995 | 0.026977444 | 0.056582754 |
| 8101 | 50 | cold | 96/96 | true | 0.00064916721 | 0.0011377535 | 0.0086839471 | 0.014598374 |
| 8101 | 50 | oldlearned | 96/96 | true | 0.00029182763 | 0.00058103904 | 0.0056176837 | 0.011306257 |
| 8101 | 50 | corrected | 96/96 | true | 0.0018602122 | 0.0039299581 | 0.028532772 | 0.060230664 |
| 8101 | 150 | cold | 86/86 | true | 0.0020383387 | 0.0034506746 | 0.0091838113 | 0.016391845 |
| 8101 | 150 | oldlearned | 86/86 | true | 0.00048241380 | 0.00099104670 | 0.0059376761 | 0.011967657 |
| 8101 | 150 | corrected | 86/86 | true | 0.0040082405 | 0.0089009448 | 0.029910028 | 0.063184793 |
| 8102 | 1 | cold | 100/100 | true | 0.0000086290547 | 0.000016538466 | 0.0043145274 | 0.0082692329 |
| 8102 | 1 | oldlearned | 100/100 | true | 0.0000058150049 | 0.000011643194 | 0.0029075025 | 0.0058215972 |
| 8102 | 1 | corrected | 100/100 | true | 0.0000075360868 | 0.000015227699 | 0.0037680434 | 0.0076138495 |
| 8102 | 10 | cold | 100/100 | true | 0.00015912485 | 0.00029935667 | 0.0086879953 | 0.016111506 |
| 8102 | 10 | oldlearned | 100/100 | true | 0.00010847907 | 0.00021784927 | 0.0056852883 | 0.011367989 |
| 8102 | 10 | corrected | 100/100 | true | 0.00029939143 | 0.00061347941 | 0.023322828 | 0.047901371 |
| 8102 | 20 | cold | 99/99 | true | 0.00028547446 | 0.00052739413 | 0.0081850269 | 0.014698506 |
| 8102 | 20 | oldlearned | 99/99 | true | 0.00017853551 | 0.00035520409 | 0.0055596211 | 0.011104407 |
| 8102 | 20 | corrected | 99/99 | true | 0.00073941603 | 0.0015198044 | 0.027577442 | 0.056901764 |
| 8102 | 50 | cold | 96/96 | true | 0.00064791951 | 0.0011368969 | 0.0086661868 | 0.014587190 |
| 8102 | 50 | oldlearned | 96/96 | true | 0.00029068672 | 0.00057928871 | 0.0056030592 | 0.011285440 |
| 8102 | 50 | corrected | 96/96 | true | 0.0018891376 | 0.0039178251 | 0.029060389 | 0.060228916 |
| 8102 | 150 | cold | 86/86 | true | 0.0020350504 | 0.0034488837 | 0.0091545697 | 0.016384907 |
| 8102 | 150 | oldlearned | 86/86 | true | 0.00047988168 | 0.00098730638 | 0.0059224529 | 0.011945747 |
| 8102 | 150 | corrected | 86/86 | true | 0.0039988710 | 0.0085897089 | 0.030526062 | 0.063310820 |
| 8103 | 1 | cold | 100/100 | true | 0.0000086260373 | 0.000016547682 | 0.0043130187 | 0.0082738408 |
| 8103 | 1 | oldlearned | 100/100 | true | 0.0000058264767 | 0.000011667833 | 0.0029132383 | 0.0058339167 |
| 8103 | 1 | corrected | 100/100 | true | 0.0000076691053 | 0.000016104806 | 0.0038345527 | 0.0080524031 |
| 8103 | 10 | cold | 100/100 | true | 0.00015877401 | 0.00029921062 | 0.0086632574 | 0.016101625 |
| 8103 | 10 | oldlearned | 100/100 | true | 0.00010840610 | 0.00021787428 | 0.0056705675 | 0.011351498 |
| 8103 | 10 | corrected | 100/100 | true | 0.00030719471 | 0.00064717545 | 0.024008311 | 0.050702531 |
| 8103 | 20 | cold | 99/99 | true | 0.00028468421 | 0.00052700222 | 0.0081554156 | 0.014677818 |
| 8103 | 20 | oldlearned | 99/99 | true | 0.00017808451 | 0.00035466185 | 0.0055383654 | 0.011073331 |
| 8103 | 20 | corrected | 99/99 | true | 0.00076210328 | 0.0016104533 | 0.028453546 | 0.060353666 |
| 8103 | 50 | cold | 96/96 | true | 0.00064580819 | 0.0011355216 | 0.0086388315 | 0.014569397 |
| 8103 | 50 | oldlearned | 96/96 | true | 0.00028902902 | 0.00057671428 | 0.0055808681 | 0.011252868 |
| 8103 | 50 | corrected | 96/96 | true | 0.0019475827 | 0.0041563878 | 0.030030265 | 0.064032112 |
| 8103 | 150 | cold | 86/86 | true | 0.0020327767 | 0.0034461229 | 0.0091400459 | 0.016375042 |
| 8103 | 150 | oldlearned | 86/86 | true | 0.00047600400 | 0.00098207039 | 0.0058994020 | 0.011911716 |
| 8103 | 150 | corrected | 86/86 | true | 0.0041411676 | 0.0091779003 | 0.031526328 | 0.067267907 |

## 保存检查与全部失败项

总体 `complete_population=true`，**`iv1_prediction_gate_passed=false`**。以下列出 [metrics.json](../results/cpu_validation/2026-10-12_instrumental_action_response/raw/metrics.json) 的全部检查，未追加门或改变门。H1 q/v的passed=true是保存的非gated附带检查，不能当成主要预测门已通过；H10 q的gated=false也保持原样。表内各seed H10/20/50/150 q/v的false与两项原幅度失败全部公开。

| seed/保存scope | H | signal | available | gated/原条件 | strict | passed |
|---|---:|---|---|---|---|---|
| 8101 | 1 | q | true | false | false | **true** |
| 8102 | 1 | q | true | false | false | **true** |
| 8103 | 1 | q | true | false | false | **true** |
| 8101 | 1 | v | true | false | false | **true** |
| 8102 | 1 | v | true | false | false | **true** |
| 8103 | 1 | v | true | false | false | **true** |
| 8101 | 10 | q | true | false | false | **false** |
| 8102 | 10 | q | true | false | false | **false** |
| 8103 | 10 | q | true | false | false | **false** |
| 8101 | 10 | v | true | true | true | **false** |
| 8102 | 10 | v | true | true | true | **false** |
| 8103 | 10 | v | true | true | true | **false** |
| 三seed原RMSE均值 | 10 | v | true | 原20%幅度 | — | **false** |
| 8101 | 20 | q | true | true | false | **false** |
| 8102 | 20 | q | true | true | false | **false** |
| 8103 | 20 | q | true | true | false | **false** |
| 8101 | 20 | v | true | true | false | **false** |
| 8102 | 20 | v | true | true | false | **false** |
| 8103 | 20 | v | true | true | false | **false** |
| 8101 | 50 | q | true | true | false | **false** |
| 8102 | 50 | q | true | true | false | **false** |
| 8103 | 50 | q | true | true | false | **false** |
| 8101 | 50 | v | true | true | false | **false** |
| 8102 | 50 | v | true | true | false | **false** |
| 8103 | 50 | v | true | true | false | **false** |
| 8101 | 150 | q | true | true | true | **false** |
| 8102 | 150 | q | true | true | true | **false** |
| 8103 | 150 | q | true | true | true | **false** |
| 三seed原RMSE均值 | 150 | q | true | 原20%幅度 | — | **false** |
| 8101 | 150 | v | true | true | false | **false** |
| 8102 | 150 | v | true | true | false | **false** |
| 8103 | 150 | v | true | true | false | **false** |

两项三seed幅度门只转录已有原RMSE均值、fraction与要求，不计算新改善比例：

| H | signal | cold axis mean（肩,肘） | corrected axis mean | 保存improvement fractions | required improvement | passed |
|---|---|---|---|---|---|---|
| 10 | v | (0.0086840005, 0.016110170) | (0.023343179, 0.048643275) | (-1.6880675, -2.0194141) | 0.2 | false |
| 150 | q | (0.0020353886, 0.0034485604) | (0.0040494264, 0.0088895180) | (-0.98951017, -1.5777475) | 0.2 | false |

oldlearned全部指标及其相对cold/corrected的已保存差保留于metrics原件；没有删去不利seed或用部分人口排名。此处预测失败不能以接触资格、完整执行或少量fit成功追认。

## 付费步骤、标签与全部成本边界

辨识9,000和预测源6,000 control/substep分别付费，共15,000/15,000；RLS_updates=0，额外IV三次fit与24个系数另列。12,000是新原生标签用途，不是12,000次RLS。四候选特征、工具矩outer products、lstsq和预测数学都单独计费；预测端点标签17,316用途不混入拟合标签。

下表为完整 `run.cost` 保存字段的分组转录，各组值与字段按相同顺序对应；原始字典见 [run.json 的 cost](../results/cpu_validation/2026-10-12_instrumental_action_response/raw/run.json)，没有补算费用或将未测量项目写成零：

| 原cost字段（顺序对应） | 首次保存值 |
|---|---|
| `source_git_attempts` / `source_git_returns` / `source_git_bytes` | 12 / 12 / 169067 |
| `source_file_reads` / `source_bytes_read` / `source_archive_bytes_written` | 10 / 169026 / 50238 |
| `model_file_read_attempts` / `model_file_read_returns` / `model_bytes_read` | 1 / 1 / 60924 |
| `source_environment_constructor_attempts` / `source_environment_constructor_returns` | 6 / 6 |
| `MjModel_from_xml_path_attempts` / `MjModel_from_xml_path_returns` | 6 / 6 |
| `MjData_build_attempts` / `MjData_build_returns` | 6 / 6 |
| `explicit_reset_attempts` / `explicit_reset_returns` | 6 / 6 |
| `mj_resetData_attempts` / `mj_resetData_returns` | 6 / 6 |
| `mj_forward_attempts` / `mj_forward_returns` | 15012 / 15012 |
| `physical_identity_attempts` / `physical_identity_returns` / `physical_asset_read_returns` / `physical_asset_bytes_read` | 12 / 12 / 12 / 41160 |
| `PCG64_Generator_builds` / `Rademacher_pair_draws` | 3 / 6000 |
| `total_control_attempts` / `total_control_returns` / `confirmed_physics_substeps` | 15000 / 15000 / 15000 |
| `identification_control_attempts` / `identification_control_returns` / `identification_confirmed_physics_substeps` | 9000 / 9000 / 9000 |
| `prediction_control_attempts` / `prediction_control_returns` / `prediction_confirmed_physics_substeps` | 6000 / 6000 / 6000 |
| `mj_step_attempts` / `mj_step_returns` | 15000 / 15000 |
| `effort_requested_guarded_actual_scalar_samples` | 360000 |
| `audit_contact_snapshot_attempts` / `audit_contact_snapshot_returns` | 15000 / 15000 |
| `mj_contactForce_attempts` / `mj_contactForce_returns` | 351132 / 351132 |
| `audit_contact_pair_inspections` / `audit_geom_name_query_attempts` / `audit_geom_name_query_returns` / `audit_contact_force_query_attempts` / `audit_contact_force_query_returns` | 117044 / 117044 / 117044 / 117044 / 117044 |
| `initial_snapshot_fingerprint_checks` / `initial_theta_scalar_reads` / `native_model_builds` | 6 / 108 / 6 |
| `identification_public_PD_attempts` / `identification_public_PD_returns` | 6000 / 6000 |
| `IV_moment_update_attempts` / `IV_moment_update_returns` / `new_IV_scalar_label_uses` | 6000 / 6000 / 12000 |
| `instrument_pair_attempts` / `instrument_pair_returns` | 6000 / 6000 |
| `conditional_mapping_candidates` / `conditional_mapping_mean_scalar_outputs` / `instrument_scalar_outputs` | 24000 / 24000 / 24000 |
| `public_guard_projection_attempts` / `public_guard_projection_returns` / `public_guard_input_scalar_uses` | 217020 / 217020 / 1736160 |
| `signed_hinge_scalar_evaluations` / `action_feature_scalar_outputs` | 434040 / 868080 |
| `frozen_nonaction_matvec_attempts` / `frozen_nonaction_matvec_returns` / `frozen_nonaction_coefficient_scalar_uses` | 6000 / 6000 / 60000 |
| `IV_outer_products` / `IV_moment_scalar_additions` | 12000 / 144000 |
| `IV_fit_attempts` / `IV_fit_returns` / `IV_lstsq_attempts` / `IV_lstsq_returns` / `IV_fitted_coefficient_scalar_outputs` | 3 / 3 / 3 / 3 / 24 |
| `prediction_public_PD_attempts` / `prediction_public_PD_returns` | 3000 / 3000 |
| `pair_prediction_attempts` / `pair_prediction_returns` / `scalar_velocity_head_attempts` / `scalar_velocity_head_returns` | 187020 / 187020 / 374040 / 374040 |
| `prediction_coefficient_scalar_uses` / `predicted_qv_scalar_outputs` | 3366360 / 748080 |
| `new_prediction_endpoint_scalar_label_uses` / `prediction_endpoint_error_scalar_outputs` / `new_axis_RMSE_vector_computations` | 17316 / 17316 / 90 |
| `frozen_native_model_fingerprint_checks` / `original_snapshot_fingerprint_checks_after` | 9 / 6 |
| `oldlearned_report_RMSE_scalar_differences` / `three_seed_raw_RMSE_mean_comparisons` | 120 / 2 |
| `JSONL_encode_attempts` / `JSONL_encode_returns` / `JSONL_write_attempts` / `JSONL_write_returns` / `JSONL_decoded_bytes_written` | 40329 / 40329 / 40329 / 40329 / 172544283 |
| `wall_seconds` / `cpu_seconds` | 55.33234490011819 / 52.1875 |

`controller_inverse_solves=0`、`old_math_recomputations=0`、`old_trace_or_prediction_reads=0`、fork control=0、RLS_updates=0。本批记录的wall/CPU不包括 `final_JSON_encoding_and_payload_writes`；物理内部forward、lstsq内部factorization和未测量filesystem/import I/O均为unknown-not-zero。准备合成检查、原件复制及交付核对费用由对应归档另计，本报告不将它们假定为零。

source_trace保存36000条decoded JSONL / 143038363 bytes / `41d896c23e699a2a1e1a2a4df380478d9310b5bdc8642cd43a20b9c445c9263a`；predictions保存4329条 / 29505920 bytes / `c8871a685be3ea645c37ab948fdb9b9698236b95a7c58d7efb4abb6b8c160075`。JSONL行数不是物理步数；本报告未读取两个trace/预测流。

## requested、guarded、actual努力分列

下表只显示受控肩/肘两轴，保持每个trial/阶段的付费子步分母，既没有跨阶段相加，也没有计算控制努力改善。完整8轴值与接触记录见 `run.trials[].stage_telemetry` 原字段；展示精度为八位有效数字。requested、guarded和actual是三个保存口径，不能互相替代。

absolute积分（肩,肘），单位Nm·s：

| seed | trial/阶段 | captured substeps | requested absolute | guarded absolute | actual absolute |
|---|---|---:|---|---|---|
| 8101 | 辨识/prefix | 1000 | (0.0000000, 0.0000000) | (0.0000000, 0.0000000) | (0.0000000, 0.0000000) |
| 8101 | 辨识/A | 1000 | (0.51113586, 0.32450799) | (0.51113586, 0.31889956) | (0.51113586, 0.31889956) |
| 8101 | 辨识/B | 1000 | (0.54408935, 0.31634502) | (0.54408935, 0.31634502) | (0.54408935, 0.31634502) |
| 8101 | 预测源/prefix | 1000 | (0.0000000, 0.0000000) | (0.0000000, 0.0000000) | (0.0000000, 0.0000000) |
| 8101 | 预测源/active | 1000 | (0.061821102, 0.062512285) | (0.061821102, 0.028753599) | (0.061821102, 0.028753599) |
| 8102 | 辨识/prefix | 1000 | (0.0000000, 0.0000000) | (0.0000000, 0.0000000) | (0.0000000, 0.0000000) |
| 8102 | 辨识/A | 1000 | (0.51480079, 0.32484540) | (0.51480079, 0.32007264) | (0.51480079, 0.32007264) |
| 8102 | 辨识/B | 1000 | (0.55524660, 0.31341171) | (0.55524660, 0.31341171) | (0.55524660, 0.31341171) |
| 8102 | 预测源/prefix | 1000 | (0.0000000, 0.0000000) | (0.0000000, 0.0000000) | (0.0000000, 0.0000000) |
| 8102 | 预测源/active | 1000 | (0.061566171, 0.062530504) | (0.061566171, 0.028829782) | (0.061566171, 0.028829782) |
| 8103 | 辨识/prefix | 1000 | (0.0000000, 0.0000000) | (0.0000000, 0.0000000) | (0.0000000, 0.0000000) |
| 8103 | 辨识/A | 1000 | (0.52703921, 0.32240877) | (0.52703921, 0.31691893) | (0.52703921, 0.31691893) |
| 8103 | 辨识/B | 1000 | (0.58069430, 0.30234324) | (0.58069430, 0.30234324) | (0.58069430, 0.30234324) |
| 8103 | 预测源/prefix | 1000 | (0.0000000, 0.0000000) | (0.0000000, 0.0000000) | (0.0000000, 0.0000000) |
| 8103 | 预测源/active | 1000 | (0.062456764, 0.062607713) | (0.062456764, 0.028975336) | (0.062456764, 0.028975336) |

squared积分（肩,肘），单位Nm²·s：

| seed | trial/阶段 | captured substeps | requested squared | guarded squared | actual squared |
|---|---|---:|---|---|---|
| 8101 | 辨识/prefix | 1000 | (0.0000000, 0.0000000) | (0.0000000, 0.0000000) | (0.0000000, 0.0000000) |
| 8101 | 辨识/A | 1000 | (0.18172371, 0.080016151) | (0.18172371, 0.078986600) | (0.18172371, 0.078986600) |
| 8101 | 辨识/B | 1000 | (0.20049093, 0.075657561) | (0.20049093, 0.075657561) | (0.20049093, 0.075657561) |
| 8101 | 预测源/prefix | 1000 | (0.0000000, 0.0000000) | (0.0000000, 0.0000000) | (0.0000000, 0.0000000) |
| 8101 | 预测源/active | 1000 | (0.017397592, 0.019933330) | (0.017397592, 0.0074058420) | (0.017397592, 0.0074058420) |
| 8102 | 辨识/prefix | 1000 | (0.0000000, 0.0000000) | (0.0000000, 0.0000000) | (0.0000000, 0.0000000) |
| 8102 | 辨识/A | 1000 | (0.18470875, 0.079690020) | (0.18470875, 0.078865137) | (0.18470875, 0.078865137) |
| 8102 | 辨识/B | 1000 | (0.20500246, 0.072057550) | (0.20500246, 0.072057550) | (0.20500246, 0.072057550) |
| 8102 | 预测源/prefix | 1000 | (0.0000000, 0.0000000) | (0.0000000, 0.0000000) | (0.0000000, 0.0000000) |
| 8102 | 预测源/active | 1000 | (0.017394085, 0.019937359) | (0.017394085, 0.0074171201) | (0.017394085, 0.0074171201) |
| 8103 | 辨识/prefix | 1000 | (0.0000000, 0.0000000) | (0.0000000, 0.0000000) | (0.0000000, 0.0000000) |
| 8103 | 辨识/A | 1000 | (0.19020353, 0.077673570) | (0.19020353, 0.076537644) | (0.19020353, 0.076537644) |
| 8103 | 辨识/B | 1000 | (0.21912891, 0.070453130) | (0.21912891, 0.070453130) | (0.21912891, 0.070453130) |
| 8103 | 预测源/prefix | 1000 | (0.0000000, 0.0000000) | (0.0000000, 0.0000000) | (0.0000000, 0.0000000) |
| 8103 | 预测源/active | 1000 | (0.017405429, 0.019943447) | (0.017405429, 0.0074348447) | (0.017405429, 0.0074348447) |

## 结论与持续目标

本批证明规定原生辨识与独立fresh预测流程完整可执行、工具矩拟合三次rank4返回；**没有通过冻结预测门，没有控制收益或安全收益结论**。保留只改动作项后的全时距退化，不因数值满秩增加ridge/扫描或补跑本候选。旧statehead与新B/H可能不匹配是仍待检验的结构问题，不能作为已经识别的因果原因。下一唯一 IV2 已决定：固定本次八个动作系数，用各 seed 全部 2000 条已付费标识转移一次拟合十个非动作系数，再做新 pulse 时相的 fresh 独立预测。三次 solve /30 个系数 /12,000 reused offline scalar 标签用途，0 新训练物理与 RLS；预测最多 6000 新控制/子步。不得拟合本次预测标签或 PAR1 fork 标签，不扫描参数；先冻结新协议/代码再首次执行，本结果不自动开放控制。

累计从514,345 control /2,794,018 substep增至 **529,345 /2,809,018**；原在线118,452+离线7,200=**125,652 scalar RLS累计**不变，**本批IV 12,000标签用途/3fit/24系数另计**，不能将新增辨识成本包装成零训练或旧RLS数。

五science flags保持 `scientific_adoption=false`、`old_free_root_C4_validation=false`、`c4_scientific_validation=false`、`c5_scientific_dependency_released=false`、`c4_contact_scientific_validation=false`；`control_candidate_opened=false`。C4原预测/控制/强PD/实际努力门不改，**C4–C7未验收，持续目标active**。首次原件与必要检查提交推送后继续最早未验收项，单次失败报告不会结束持续目标。
