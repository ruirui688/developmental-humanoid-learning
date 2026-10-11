# C4 Q：固定局部二阶原生转移开发结果

Q 从 clean commit `20fa0321c84eb766eeafb9f8d906f554bca60622` 首次完成固定开发评估，
**Q→K 与 Q→D 两门仍失败**。H1 速度通过20%门，H2/H5 q/v 和 H15 v 在全部 seed/轴不劣；
剩余失败项是 H15 q：相对 K 肩/肘改善均值6.682%/5.973%，相对 D 为6.490%/5.532%，未达20%。
全部固定组完整。这是已见开发bank上的有限改善，Q 不进入控制；scientific_adoption、
C4验收、C5依赖解除均为false，旧门不追认。持续目标active，C4仍最早未验收。

## 唯一候选、来源与权限

[Q协议](GUARD_QUADRATIC_NATIVE_TRANSITION_DEVELOPMENT_PROTOCOL.md)保留 K 原始29列、
x22、lambda=.01、prior、当前 guard/hinge 与 previous_v，只追加固定六变量全部21个二次项：

```text
z = ((q0-qref0)/.12, (q1-qref1)/.12, v0/1, v1/1, startG0/.5, startG1/.5)
quadratic21 = (z[i]*z[j] for i=0..5 for j=i..5)
phi50 = [phi29_K, quadratic21]
W50x22 = solve(Phi50.T @ Phi50 + .01 I50, Phi50.T @ saved_K_Delta400x22)
```

训练只用保存 K Phi400x29 / Delta400x22 / IDs / qref，追加项共用同一训练/预测映射，
不重生标签、不重拟合 K、不更新 D。qrel 不再减 qref，startG 来自同次原 K mapping，
不再次 guard。尺度来自公开位置.12rad、速度1rad/s和权限.5Nm，
零列保留；无RMS、中心化、筛选、P过去请求或第二配方。
预测在自己的当前状态上重算特征，22输出全部自身递推，previous_v 推进旧current v。
共享保存未来请求是离线oracle条件，不能称在线规划或完整闭环控制。

run记录 status=completed、failure=null、clean_committed_bytes_verified=true；
execution returncode=0、subprocess_invocations=1、automatic_retry=false、stderr_bytes=0。
代码29,407 bytes SHA256
`6a8109ed9ba68b61674f9744ac0ea4ffce421ff8b4400abfe7cc081b5c16a147`；
协议5,230 bytes SHA256
`77cb47c42efad889f4d15cf64207b528ab2c7e29908d55d3f16441b0b7a6c5d3`。
C/D/K九输入及原commit沿用冻结协议身份。K22/D11三个seed前后fingerprint一致。
正式环境为Python3.10.11、NumPy1.26.4、Windows-10-10.0.26200-SP0；
原C metadata的MuJoCo3.15.0/NumPy2.2.6是来源环境，本次没有运行物理。

保存依据：
[run](../results/cpu_validation/2026-10-12_guard_quadratic_native_transition/raw/run.json)、
[metrics](../results/cpu_validation/2026-10-12_guard_quadratic_native_transition/raw/metrics.json)、
[根manifest](../results/cpu_validation/2026-10-12_guard_quadratic_native_transition/manifest.json)、
[execution](../results/cpu_validation/2026-10-12_guard_quadratic_native_transition/execution.json)。

## 全部seed关键RMSE与完整双门

seed0/1/2，Q22/K22/D11，H1/2/5/15每组固定100/99/96/86原点；prediction来源每seed100条。
metrics保存576个通道组，两门all_fixed_usable_counts/evaluated均为true；
协议固定布局为3,429个预测记录，不做部分轨迹排名。
q0/v0为肩轴0，q1/v1为肘轴1；q通道是q−qref，误差单位仍为rad。
下表摘录所有seed关键RMSE，四舍五入到9位，原精度与其他时距/全部22状态通道指标保留于metrics。

| seed | predictor | H1 v0 RMSE (rad/s) | H1 v1 RMSE (rad/s) | H15 q0 RMSE (rad) | H15 q1 RMSE (rad) |
|---:|---|---:|---:|---:|---:|
| 0 | Q22 | 0.040041740 | 0.085085688 | 0.002764463 | 0.005787464 |
| 0 | K22 | 0.055610966 | 0.115630578 | 0.002983588 | 0.006162089 |
| 0 | D11 | 0.055843602 | 0.115797919 | 0.002973809 | 0.006141591 |
| 1 | Q22 | 0.040677167 | 0.085485175 | 0.002860724 | 0.005828053 |
| 1 | K22 | 0.055731662 | 0.115451769 | 0.003023645 | 0.006181709 |
| 1 | D11 | 0.056068842 | 0.115767920 | 0.003028402 | 0.006145407 |
| 2 | Q22 | 0.040031211 | 0.085021034 | 0.002767574 | 0.005788799 |
| 2 | K22 | 0.055625580 | 0.115590937 | 0.002985946 | 0.006165986 |
| 2 | D11 | 0.055869791 | 0.115779545 | 0.002972474 | 0.006136387 |

两门都要求 H1 v、H15 q **每seed严格改善且各轴逐seed相对RMSE改善均值≥20%**；
H2/H5 q/v 和 H15 v 要求每轴每seed不劣。H1 q仅描述。
零/非有限基线、缺组或不可用记录使相应门失败/不可评估，两个完整门必须同时通过。

下表仅格式化保存的mean_relative_improvement；正值为改善，不是pooled RMSE或新留出效果。

| H | signal | axis | Q→K mean relative improvement | Q→K | Q→D mean relative improvement | Q→D |
|---:|---|---:|---:|---|---:|---|
| 1 | v | 0 | 27.681225% | 通过 | 28.032373% | 通过 |
| 1 | v | 1 | 26.272832% | 通过 | 26.415620% | 通过 |
| 2 | q | 0 | 25.137479% | 通过 | 42.983112% | 通过 |
| 2 | q | 1 | 25.161998% | 通过 | 42.911502% | 通过 |
| 2 | v | 0 | 20.587102% | 通过 | 19.654139% | 通过 |
| 2 | v | 1 | 19.690056% | 通过 | 18.754677% | 通过 |
| 5 | q | 0 | 20.847481% | 通过 | 19.782752% | 通过 |
| 5 | q | 1 | 23.051548% | 通过 | 22.527353% | 通过 |
| 5 | v | 0 | 8.395363% | 通过 | 8.941640% | 通过 |
| 5 | v | 1 | 8.784889% | 通过 | 8.788043% | 通过 |
| 15 | q | 0 | 6.681975% | 失败 | 6.489928% | 失败 |
| 15 | q | 1 | 5.972586% | 失败 | 5.531504% | 失败 |
| 15 | v | 0 | 9.500155% | 通过 | 9.467319% | 通过 |
| 15 | v | 1 | 8.812996% | 通过 | 8.092872% | 通过 |

每个比较的14个轴级检查中12项通过、H15 q两轴失败。
H1 v相对K改善均值27.681%/26.273%，相对D为28.032%/26.416%；
H15 q各seed均严格改善，但幅度不达20%。H2/H5 q/v及H15 v全部逐seed不劣。
不能降低位置门、只采纳速度门或把两门的passed=false解释成整体通过。

## 正式、准备、归档与报告费用

| 正式新增离线计算 | 保存费用 |
|---|---:|
| 50×50、22 RHS fit / solve | 3尝试 / 3返回 / 0失败 |
| 重复scalar labels请求 / 返回 | 26,400 / 26,400 |
| 拟合scalar coefficients / heads | 3,300 / 66 |
| K设计 / labels / weights scalar验证 | 34,800 / 26,400 / 1,914 |
| 训练追加映射 | 1,200尝试 / 1,200返回 |
| 训练尺度除法 / 二次乘积 | 7,200 / 25,200请求与返回 |
| 原设计复制 / 50列设计materialization | 34,800 / 60,000请求与返回 |
| Gram / cross | 各3尝试 / 3返回 |
| 逻辑乘 / 加请求 | 4,320,000 / 4,309,200 |
| ridge identity entry additions | 7,500请求 / 7,500返回 |
| Q22 / K22完整状态转移 | 各6,204尝试 / 6,204返回 |
| Q22 / K22 prior与residual scalar输出 | 每方法各136,488 |
| Q预测尺度除法 / 二次乘积 | 37,224 / 130,284请求与返回 |
| Q预测特征materialization / previous_v scalar复制 | 310,200 / 12,408 |
| D11 pair / scalar预测 | 6,204 / 12,408尝试与返回 |
| native state encoding / score scalar error calculations | 2,286 / 54,864 |
| 物理调用 / 子步 / RLS / MPC / K refit / D update | 全部0 |

正式来源检查13次Git query返回171,694 bytes，11次源码读171,653 bytes、2次helper load。
九输入读取/校验15,425,784 bytes，8次普通JSON解析；C原trace完整解压86,628,874 bytes、
7,230行JSON解析，只保留prediction原生窗口，未使用calibration原生端点生成标签。
内层wall/CPU为3.858591/3.375000 s，排除最终序列化/写盘；外层subprocess wall为4.784106 s。
逻辑乘加不是硬件FLOPs；新增50列计算与3,300参数不能宣称等总计算预算，重复标签不能算新独立证据。

正式归档另有10 payload、20次读取、47,826,696 bytes、copy_failures=[]，
wall/CPU0.196519/0.062500 s；no_scientific_recalculation=true、automatic_retry=false。
这只描述保存状态，不证明科学门通过。

[准备归档](../results/cpu_validation/2026-10-12_guard_quadratic_native_transition_preparation/manifest.json)
单列首次4个新case：固定顺序/公开尺度/零列与训练预测映射一致，零追加列解析等价，
x22自身递推/previous_v推进，以及新50维solve失败的paid/partial保存。
P失败JSON合同直接复用，没有重复P非有限case。
合成设计生成20,000 scalar，生成标签8,800 scalar；成功fit与mock失败fit合计17,600重复标签消费，
solve2尝试/1返回/1预置失败，拟合1,100系数，物理/RLS/MPC为0。
合成内层wall/CPU0.109406/0.109375 s，外层wall0.431626 s；
准备归档21 payload、42次读取、1,217,210 bytes、copy失败0，wall/CPU0.173603/0.031250 s。
准备源码/schema/AST/hash费用记录在external/c4_q_preparation_reads.json，与正式计算分开。

本报告只读保存run/metrics/根manifest/execution一次：4读、348,798 bytes、4次JSON解析，
Python读/解析/hash wall/CPU0.003489/0 s。external/c4_q_reporting_reads.json保存精确身份与费用；
报告未读参数、trace、预测路径或源码，未调用模型、fit或重算指标/门。文档格式化及最终写盘另计，
不把报告准备当作新的科学评估。

## 结论边界

首次[保存输出契约](../results/cpu_validation/2026-10-12_guard_quadratic_native_transition/output_contract/report.json)
15个组级检查全部通过；6次读取/23,920,355字节、3,433次JSON解析，
内层wall/CPU .428115/.4375秒、外层 .535466秒。模型恢复和科学指标/门重算为0，
只说明证据一致；准确首次checker及stdio保留。科学双门仍失败，不解除C4/C5依赖。
[报告读取账本](../results/cpu_validation/2026-10-12_guard_quadratic_native_transition/reporting/c4_q_reporting_reads.json)
与[唯一下一方向](../results/cpu_validation/2026-10-12_guard_quadratic_native_transition/reporting/c4_after_q_direction.md)
已封存；原正式manifest保持不变。

Q支持的有限结论是：在已使用的C开发bank与固定未来请求条件下，这个完整二次配方改善了
一阶速度及多项递推指标；固定H15位置幅度门仍未通过，不能宣布开发候选合格或C4完成。
公开尺度改变了相对正则先验，新增函数类和尺度作为整个配方受检验；
结果不能归因于某个单项，也没有识别刚体非线性、摩擦、接触或prior结构的因果机制。

本次没有新留出、完整控制、未知动力学适应、成熟门控或真机；零新增物理不能证明安全、
样本效率或“零停止”。保留H15失败，不补跑到成功、不自动扩阶/扫参/加数据，
不把Q接入控制。后续结构须另定依据、协议和冻结首次执行；Q门与历史负结果保持原样。
