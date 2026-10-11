# C4 E：single-lag位置预测的最小物理控制假设

正式开发协议；源码、独立审计、来源和预算先提交并推送，再从clean提交首次执行一次物理。
这是[D结果](GUARD_LAG_OFFLINE_DEVELOPMENT_RESULTS.md)之后选择的新开发假设，
不是预注册于D之前的最终验收，也不把D旧开发数据重新称为未见留出。

## 为什么只运行这个候选

D sparse11在原106-step长请求停止轨迹的H15位置RMSE降低约31%–38%，
速度近似持平，H1位置/速度退化；共同脉冲预测也退化。continuation11的结果
更矛盾，不进入本小试验。我们拒绝默认替换模型，但保留一个具体可证伪问题：
同任务、同权限下，sparse11较低的H15位置误差是否帮助控制避免原位置停止？

即使本轮控制改善，也不能追认D普适预测通过或完整C4验收。旧20%预测门、
完整控制要求、PD比较及C5科学依赖均不放宽。身体模型使用past native history
不代表识别出马达延迟；环境没有显式马达滤波或延迟。

## 固定矩阵与知识

seed固定0/1/2，均为开发seed。每seed依次四组：`cold11`、`learned_sparse11`、
`PDselected`、`zero`，各fresh环境、仰卧baseline接触、100零力矩prefix和
200active控制。每轴最终权限.5Nm，其余六关节请求0；执行层公开guard不改。

cold11由同qref/ranges、原九列own prior和两个lag0、P100/lambda1组成，
不更新；learned_sparse11只恢复D该seed完整400更新final snapshot并冻结。
不重放C/D拟合、不新增calibration、不用PD轨迹训练。不继承cont11。
PD使用已经按独立协议选择的Kp=(64,64)、Kd=(0,4)，无本轮调优；zero请求0。
控制器、目标、模型结构、理想原生传感和公开安全规则属于共同披露的先验。

每fresh prefix结束的qref必须精确匹配原D绑定qref、public ranges和物理条件。
不一致是工程依赖失败，不重设qref、改模型或自动对齐；仍保存已付费prefix。
12计划trial先建账，独立研究停止/普通异常继续其余组；IO/中断的原义保留。

## 历史与规划

active0的current native v来自prefix99返回端点，previous_v来自prefix98。
后续current v和previous_v来自已返回的相邻端点，带原transition ID；不跨trial、
不填零、不读未来真实端点。部分返回或source stop以后不继续规划。

MPC接口显式`select(q,v,target_q,previous_v,*,previous_torque)`。
H15、每轴9候选、81常向量、原位置/速度/努力/change cost、forecast/target
bounds、tie break与zero fallback保持；只消费当前target，没有目标切换预览。
每候选从同native历史独立初始化，每步以自身predicted q重算guard，并令
下一步previous_v为本步预测前的current v。模型自身不存mutable历史；不得
用真值校正预测、保持初始history或让候选间共享递推末态。

控制目标仍为原两轴方向下`.04→.08rad`局部目标，切换时刻和target_pair函数
不变。native study stop仍为相对qref`.12rad`或速度`1rad/s`，原环境逐子步
安全终止保持。人工veto不加入控制；不设置额外PD接管或反馈残差。

四个控制组的每完整active起点都用cold11和learned_sparse11作独立一步诊断，
在动作返回前预测，输入为当前已知final requested两轴力矩和真实过去history。
PD/zero也同诊断；未来actual、特权接触和真实qpos/qvel只供离线风险核查。
独立诊断不改变MPC自己的预测历史。所有模型/规划器/增益全程冻结。

## 完整优先的开发判据与边界

逐seed/axis报告200active完成、tracking RMSE、一步q/v误差、请求/实际努力、
饱和、风险峰值/冲量、停止与全部原费用；部分区间单列，停止前RMSE不排序。
只有对应两组所有seed均完整才评价控制假设。报告同cold11的逐轴与joint
均值改善、最差seed，以及原20%控制改善和5% PD/1.05实际努力参考门。
未完成就`evaluated=false/passed=false`，不能删seed或改变终止凑门。

冻结四个输出键（均为开发判据，不添加zero比较门）：

- `control_hypothesis`：cold11和learned_sparse11所有seed均完成200active、
  effort遥测完整才evaluated。每seed的joint与两axis RMSE均严格降低；
  三seed原始joint RMSE算术均值改善至少20%，每axis原始RMSE均值也至少20%；
  三seed实际absolute/squared effort两轴合计的各自均值均不超过cold11的1.05倍。
- `pd_reference`：control_hypothesis已passed，且PD和学习组全seed完整、
  effort完整才evaluated；每seed joint/axis RMSE均不劣于PD，三seedjoint原始
  RMSE均值改善至少5%；两个实际effort均值均不超过PD的1.05倍。
- `matrix_complete`：12计划trial全部completed、原200active/2000子步完整；
  明确布尔值，不把异常/停止/blocked算完整。
- `c4_scientific_validation`：固定`evaluated=false/passed=false`，原因包含
  D所选sparse11共同脉冲预测未过旧20%门及本轮仅开发控制子假设。zero结果全量报告但不作采用门。

joint RMSE是同轨迹两轴所有完整误差的合并RMSE，三seed均值不混成一次pooled
大样本RMSE。均值ratio分母为0时，仅candidate也为0才满足不增加努力；tracking
改善分母为0不产生百分比优势。其他risk指标完整公开，不额外事后设风险采用门。

这些只是本轮开发控制假设的判据。完整身体贡献还需要冻结的独立预测证据；
D所选sparse11相应脉冲预测没有通过旧20%门。因此`c4_scientifically_validated=false`，
不以控制子门解除C5科学依赖，不称新留出/低风险/技能或真机成功。

## 首次物理之前的来源与预算

绑定已封口D archive、原首审failed1及唯一读取单位补充、一次summary原件、
原C collection commit和PD选择身份。声明D离线4800scalar已付费，本轮0更新。
模型恢复须核对完整snapshot/fingerprint、dt、prior/P/lambda、guard、11列定义，
不能只加载系数或接受失败cal。运行时root核明确cleancommit/source bytes；
源码ZIP保留runner/MPC/helper/独立auditor/support/协议/asset/配置的原字节。
独立标准库审计不导入在线模型、物理或调用旧C/D全档审计。

| 上限 | 量 |
|---|---:|
| 新trial | 12 |
| 新控制调用 / 物理子步 | 3600 / 36000 |
| 其中prefix | 1200 / 12000 |
| 新模型、策略、增益或门控更新 | 0 |
| 独立诊断pair / scalar预测 | 4800 / 9600 |
| 两MPC组规划pair / scalar预测 | 1458000 / 2916000 |

失败尝试、拒绝candidate的实际步数、未知scalar下界、部分物理、返回但未写行、
实际努力的缺失分母均保留。snapshot恢复/guard/history计算、工程人工数学、
独立audit和汇总费用单列，不写作零计算。不会重采C/D校准或追加PD候选。

## 工程提升与首次执行约束

生产入口为`src/developmental_physics/guard_lag_control_development.py`，显式历史
规划器为`src/developmental_physics/guard_lag_pair_mpc.py`，独立标准库入口为
`scripts/audit_guard_lag_control.py`。独立支持链固定为`audit_guard_lag_offline.py`、
`audit_guard_coupled_development.py`、`audit_guard_pair_development.py`、
`audit_pair_frozen.py`、`audit_local_frozen.py`，均在`scripts/`；只复用独立数学，
不执行旧C/D全档审计。完整支持、物理源码、asset、配置、协议及D/PD绑定字节
必须同时进入clean Git核对和本次source ZIP。

显式历史MPC首次9人工检查、原逻辑5项AST检查通过；采集器首次6手工边界
检查通过，304 fake calls/3028 fake substeps、6 pair数学诊断，真实物理0；
独立审计原8规划数学与新8接口/完整性门检查均通过，未复跑原数学。
一次D只读加载预检恢复3学习模型/3 cold模型，六文件5690368bytes，0预测/更新。
准备阶段的其他读取、默认Python缺MuJoCo失败、错路径及恢复源码的来源局限
见[工程原件清单](../results/cpu_validation/2026-10-11_guard_lag_control_preparation/manifest.json)，
不能把后补原件标作执行时快照。正式试验另从clean源码记录完整原字节。

提升只核源码/AST/API、编译和pytest入口；已通过数学、手写fake区间和D预检不重复。
正常测试使用显式fake环境，formal拒绝fixture临时关闭开关并恢复，不能启动物理。
生产开关放行仍受clean源码、固定路径和绑定身份限制；root一次wrapper拒绝已有
输出，并记录外层费用。正式运行时恢复3模型/初建3 cold、每trial clone2个模型，
上限24次clone；构造、数组复制、snapshot/hash检查非零计算，0拟合/更新。

相关检查和工程原件封口后提交推送，再一次物理、一次首审和一次保存指标汇总。
结果失败则保留，据具体失配继续最小修订；不会在本轮报告后停止。
