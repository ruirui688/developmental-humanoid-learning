# C4 J：完整 native IMU 的一步残差开发协议

I 已否定“上一原始速度残差直接修正下一步”的开发候选。J 只检验完整六通道当前 IMU 是否对冻结 D sparse11 的一步速度残差提供增量信息，不进行控制。此为已见数据开发，`scientific_adoption=false`；D 旧预测门、C4 完整控制/强PD门与 C5 科学依赖保持原样。

## 一次执行与来源

canonical 脚本 `scripts/develop_guard_imu_residual.py`，协议 `docs/GUARD_IMU_RESIDUAL_DEVELOPMENT_PROTOCOL.md`。先审查、检查、提交冻结二者与四个纯模型 helper/包根源码，再从干净 tracked 状态首次执行一次，显式给完整 J source commit；工作区字节须与该 commit 一致。新输出目录不覆盖，失败和全部负指标保留，不改参数补跑。

```powershell
D:/Python3.10/python.exe scripts/develop_guard_imu_residual.py --source-commit <J完整commit> --output external/c4_j_imu_residual_01
```

仅 NumPy 与 Python 标准库。只恢复 `GuardLagPairBodyModel` 纯模型，不 import MuJoCo/环境/旧 collector，不拟合 D 基模型，不重跑 C/D/G 数百万旧审计。准备期不打开实际 trace/模型系数，不执行 actual-data predict/fit 或物理；六个小分支只用合成 native 字段与评分误差。额外仅准许一次数学小检查中的两个纯合成6×6/2rhs solve：identity设计的已知ridge解与zero-feature的零head，独立记录engineering标签/solve费用，不运行正式fit。

正式允许九个既有输入：C raw 的 manifest/metadata/trace；D root manifest 与 raw manifest/diagnostics；G raw manifest/metadata/trace。路径与 SHA256 固定在脚本。C source `5ea8df42b09588845760daf0dc1f270aef2a87f1`，D source `f7710c7b048dccab3e436d1fa16432f881a35992`，G physical source `91dcf6c111a87427c8f3fdd8b959d4792b1bb5a2`。D root manifest SHA `38df6b99e15c3667a33d6c9995a8efd664f70ce59be8a511fa49def59727a4d7`，D diagnostics SHA `9307f3f37d5a3c23ef6f9097d8c352a9fc7f2e34e562b5cf4e7075e20bbbe130`；C/G raw manifests、payload 精确 hash 和原依赖版本一并绑定，不读取旧 audit/summary/rollouts/update 日志。原 D failed1/reconciliation 历史不改写。

## 固定数据与因果信息

seed 固定0/1/2。训练仅 C `calibration_sparse` 每seed400完整 native区间；主评分仅 C `prediction` 每seed100共同请求完整区间。C 这些评分数据也已见，不能称新留出。G 四方法 `cold11/learned_sparse11/PDselected/zero` 全部实际 active 区间按12 trial 各自评分，停止前付费端点保留；不跨停止轨迹作部分 RMSE 方法排名。

基模型是每seed D 已发布400-vector/800-scalar sparse11 frozen snapshot，完整参数/协方差/指纹恢复，不更新。它已经使用相同 C sparse400 数据；J 再次使用这些1200区间拟合残差层，是新离线学习计算、重复已有数据，不是新物理，也不能把历史辨识/PD开发费用归零。

当前输入只取 `observation_before` 的原生 joint q/v、已知最终 requested_torque 及 gyro/acceleration。模型 previous_v 必须由本 trial 连续完整过去两个返回端点取得，98/99 prefix可为active0提供历史；逐区间验证相邻step、端点 q/v一致、完整10子步和此前未停止。缺失、partial、不连续、reset或跨trial不补零；记录不可用原因。当前停止端点完整时可以评分，停止之后不读成新样本。

IMU site 固定于 torso；environment 在每返回端点重算 sensors 后复制原生 gyro/acceleration，当前 row 的 observation_before 是执行本区间之前的值。它是原 q/v 输入边界的公开 native 信息扩展，包含重力与接触反作用的混合感觉，不读 root quaternion/contact/真实动力学或未来实际力矩，不从相关性宣称隐藏机制因果。

固定 `phi=[gyro_x,gyro_y,gyro_z,accel_x/9.81,accel_y/9.81,accel_z/9.81]`（gyro单位缩放1rad/s），六列全保留，无轴筛选、截距、均值中心化、滤波、未来 IMU或额外 bias。零/退化设计仍按同一ridge算术处理；ridge可解不证明信息充分。

## 固定拟合与一步评分

对每seed的400训练区间，仅以 `Y=actual_next_v-base_next_v` 为二输出标签，令 `W=solve(Phi.T@Phi + .01*I6, Phi.T@Y)`，float64、6×2、零prior。lambda=.01来自既有 INITIAL_COVARIANCE=100 的precision；这是无forgetting的batch ridge，不冒称等价原RLS。共3次共享6×6、2rhs solve，2400 scalar训练标签、36新系数；没有lambda/轴/模型选择。训练数量不足或异常该seed不发布残差参数，其评分不足必须使主门不通过；完整保留其他固定输出。

一步残差 `r=phi@W`，`corrected_v=base_v+r`，`corrected_q=base_q+.02*r`。当前真实下一端点只供训练标签或评分，不供feature。q只是 endpoint-Euler 一步诊断，多子步积分不保证这个位置修正成立。

C训练400及C共同预测100的 base 用 D frozen model 重新predict，上限1500 pair/3000 scalar。G仅复用原 row.predicted_next_qv['learned_sparse11'] 独立当前请求预测，须匹配 D frozen fingerprint、原 G model_updates=0、记录的当前q/v/request/previous_v/history。禁止用 selected forecast代替，缺失时不能悄悄改为新predict。记录 saved_base_prediction_reuses 和原G依赖来源，不声称本轮重新计算 G 数值一致。

训练、C主评分和G各trial分别输出 q/v × 两轴 base/corrected RMSE、MAE、signed actual-minus-prediction bias、pair数及相对改善。G固定 ALL/A/B，A/B按当前 active<100；空组null，不补零；原实际active数、不可用数及停止标志一起列出。训练误差为in-sample描述，不能选参。

仅 C共同prediction参与开发门：必须每seed100完整可用；每seed两速度轴 corrected RMSE严格小于base，且各轴三seed相对RMSE改善的算术平均>=20%。零baseline/非有限/不足则不通过并写原因；MAE、bias、q、训练及G均不参与门。通过也只是已见共同请求的一步开发可行性，不发布MPC模型或证明完整控制、IMU因果贡献/有效域、冷启动、安全或适应。禁止固定未来IMU做H15，不能解除C5依赖。

## 输出与实际费用

保存 source binding、拟合设计/标签/系数、逐样本 base/corrected/actual/phi及原生历史来源、所有固定指标与PASS/FAIL、不可用和异常；不只保留有利seed。manifest绑定全部输出。正式执行前的 source身份失败也保存failure与已读来源。

计输入打开/原压缩字节/hash字节、两trace解压字节/parsed行、source字节/Git只读查询；实际 C base pair/scalar成功与失败、G saved复用、特征缩放、fit标签scalar、Gram/cross matrix product、3 solveattempt/return、36拟合系数、残差forward/修正/评分算术；零 base/RLS更新、零新物理/MPC。新残差学习与历史在线22452+离线7200scalar更新计算分栏。sys.version、numpy.__version__、platform、C/G原依赖、base fingerprint、wall/CPU保存；计时排除最后run/manifest写盘明确披露。
