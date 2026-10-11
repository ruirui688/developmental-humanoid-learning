# Z0：2ms原生反馈的独立工程资格协议

本协议只冻结一次新控制接口工程验证，**不包含身体模型、辨识、策略或科学配方**。有限选择依据见 [控制接口路线判断](CONTROL_INTERFACE_ROUTE_REVIEW.md)。Y0 已因肘超速失败，Y1/Y2关闭；X/Y原件、协议和控制器不修改。更快反馈不是旧实验补跑或共享增益扫描，不承诺资格通过。

## 唯一变化与共享先验

物理仍为2ms，公共 `PD64/Kd(4,4)`、最终每轴 `.5 Nm`、相同公开资产、悬挂固定安装、目标幅度、关节保护和研究阈值保持。唯一结构改变是将20ms恒请求改为**每2ms读取新的原生两轴q/v并重新计算下一请求**；一个控制调用只执行一个物理子步。其他六轴请求恒零。

当前目标下 `raw=64*(target-q)-(4,4)*v`，先逐轴 clip 到 `±.5 Nm`，再由原环境执行角度方向 guard，必要时置零；不新增速度制动屏障、额外滤波、加速度控制、重力补偿、增益调节或切换预览。PD只读两轴q/v和当前公开目标。接触、IMU、其余关节、真实动力学、root位姿与机械反力只诊断，不选择动作。

公共PD、理想原生感觉、固定机械支撑及更高观测/反馈频率都是先验和已有控制知识，不能记作学习获得。3,000控制调用/反馈机会相对完整Y的300上限增加10倍；实际Y仅203次返回，不能拿它作为完整同预算效率分母。不同seed和未完整X/Y不构成反馈周期因果对照。

## 安装、配置和来源

独立文件为 `src/developmental_physics/fast_feedback_environment.py` 和 `scripts/validate_fast_feedback_engineering.py`。固定安装直接复用冻结 `SuspendedGroundBodyEnv` / 原core；不编辑X/Y或原XML，不重跑已通过的X装配fixture。

新配置边界为 baseline `ExplorationConfig` **仅 `control_substeps=1`**，`physics_dt=.002`和其余字段全部不变。冻结X构造器要求完整baseline配置；新类先使用该baseline完成同源构造，再显式设置自身单子步配置，记录构造配置与执行配置的差异和作用范围。这只改变控制分组和反馈节奏，不改变资产、物理步长或安装；不能把修改藏在旧入口、运行时monkeypatch或原类中。新配置在首次reset/step前固定，全trial不切换。

环境继承的原生mapping、motor、角度guard、基础停止、完整/partial capture路径保留。每fresh实例仍实际执行两次模型构造（共享supine及identity悬挂），一次reset内两次forward，无settling；这些必要计算记录费用，不称重复装配验收。物理指纹包含新control配置，与旧X/Y不同应明确记录，不能要求旧fingerprint相同。

唯一seed为 **7600**。原八轴初态 `(0,.12,0,.12,0,.12,0,.12)` 加 `default_rng(seed).uniform(-.015,.015,8)`，零速度。固定identity torso、去freejoint、原primitive最低点及5mm clearance高度算法不变；其他六轴仍被动自由。全trial不换高度/姿态/摩擦/权限或reset到通过。机械反力未测为unknown，不能称零支撑。

固定代码、此协议、安装/core/helper/资产及实际静态依赖使用精确bytes/SHA和clean40位HEAD核验，先于构造。工程source pins不引入学习/MPC代码；不调用X/Y旧main。只复用冻结的公开目标、StudyAbort、编码等纯helpers；旧资格helper硬编码300调用/10子步/20点，不用于Z资格。Z完整时间人口和200点窗口由独立代码实现，先静态review和仅必要的新契约检查，再封口提交推送。

## 固定物理时间与任务

唯一fresh trial最多 **3,000控制调用 /3,000物理子步 /6s模拟时间**：

- control0..999：1,000次零请求prefix，恰为2s。
- active0..999：1,000次PD反馈，目标 `qref+s*.04 rad`，恰为2s。
- active1000..1999：1,000次PD反馈，目标 `qref+s*.08 rad`，恰为2s。

qref只在完整、有限、未发生基础停止的prefix结束后，从prefix999 after原生两轴q获取；不恢复旧prefix或提前估参考。方向逐轴为 `+1` 当 `U-qref >= qref-L`，否则 `-1`，等距取正。两个目标必须位于公开限位margin `.03 rad`内，不可行原样失败，不clip目标或尝试反方向。目标只当前值，切换不预告；每个完整2ms之后获取新感觉供下一次反馈。

prefix不调用研究StudyAbort，与X/Y的phase语义相同，仅走原2ms基础保护。active每个**完整返回2ms区间**后以同一qref执行原StudyAbort：任一受控轴 `abs(q-qref)>=.12 rad` 或 `abs(v)>=1 rad/s` 即停止，等号停止。原环境保护仍每子步积分前后执行；其20rad/s基础速度门、关节/数值/solver/能量保护不放宽。研究检查频率由20ms改为2ms，停止延迟和取样发生改变，即使数值阈值不变也不能说所有旧终止语义等价。

终端完整区间先保存/付费，再停止；不标completed、不增加纠正动作。环境reason和研究停止分别保留。partial/0子步返回/采集异常都保留原事实，不能给完整资格；prefix失败不发布qref或继续active。

## 工程资格与独立availability

唯一工程门同时要求：

1. 新执行配置确为2ms控制/2ms物理，只有control_substeps与baseline不同；固定upright八轴/八电机mapping、公开参数和安装符合冻结来源，无trial内漂移。
2. 全1,000prefix+2,000active和全部3,000子步完整；每次返回恰一子步，无环境停止、StudyAbort或采集异常；原生传感、已应用请求、实际actuator torque、时间、接触诊断及固定mount完整有限。
3. 前段active800..999、后段active1800..1999，分别末200完整端点，即各末0.4s；每窗肩和肘MAE `<=.01 rad`，共四项均通过。

两窗 `full_trial_required=True`：整个trial不完整时两窗均unavailable，不使用partial人口排名或通过。结构完整时每窗另外要求自身200个有限target_error和原生after-target绑定；单窗后处理失败独立记录，整门false。200点算术均值是更密取样后的工程统计，不追认旧20点MAE。实际努力分母为全部付费子步，不只窗口或成功段。

floor保留，left_arm/feet/other接触只描述，其存在不参与非接触悬挂资格。fixture reaction仍unknown。`scientific_adoption`、`old_free_root_C4_validation`、`c4_scientific_validation`、`c4_contact_scientific_validation`、`c5_scientific_dependency_released`均false。工程通过也不能宣称接触、站立、发育学习、方法优势或风险下降。

## 首次执行、计账及失败分支

先完成必要新反馈/config/时间人口/窗口/失败契约的静态与有限纯检查，保存首次结果；不重复旧MPC、RLS、X装配或已揭晓物理。协议与生产source封口正常提交推送后，仅从干净精确commit一次执行seed7600。output必须新建，拒绝覆盖；不得把`--self-check`装配模式当Z0执行前的新fixture要求。

本trial **0模型forward/恢复、0fit、0RLS、0MPC、0任务教师、0策略梯度或控制器更新**。PD调用仅2,000active次上限；prefix请求固定零，避免把prefix记成反馈PD。控制尝试/返回/异常、已确认积分、保存capture、native观测与PD评估分别记账；实际小于计划时按停止原数，不预填3,000。

保存配置/seed/精确source与依赖版本、首stdio、高度前/安装后XML、安装及参数指纹、全部逐控制/子步原生状态、请求/实际力矩、所有停止、原始四MAE及availability、实际absolute/squared effort、原件manifest。源读取/hash、构造/reset、保护/感觉、PD、写盘压缩与外层耗时分项；原核心不能测的integration/endpoint-forward未确认尝试、未保存端点及对应努力为unknown/已知下界，保存capture数不代替付费子步。

首次资格失败即封存、路线重新判断，**不继续扫描反馈周期、增益、seed、目标、权限或安装**，不放宽旧研究阈值，不改X/Y。source/运行/后处理失败与物理停止分清，但都不能自动补跑到通过。负结果后持续目标仍active，后续只按有依据的新路线推进。

## 后续科学边界

通过仅表示更高频经典反馈下这个受支撑任务具备工程资格。Y1/Y2仍关闭；本协议不自动继承任何旧学习配方、snapshot、预算、H1/2/5/15或科学门。原20ms模型与H15=300ms不等于2ms模型/H15=30ms。后续若做模型贡献，须另冻结动作语义、真实时距、标签/更新与计算预算，并让cold/learned/强经典组共享频率/感觉/最终权限/目标/保护/努力分母；未来真实力矩不能暗作预测输入。

完整自由root真实接触C4、C5变化适应、C6成熟、C7综合验收仍未完成。阶段结果、相关检查、正常提交推送后立即继续最早未过门，不把Z0工程当持续目标终点。

## 准备边界

作者本轮仅core静态源读取37,970bytes及缓存PD/action/model信息；没有raw/旧metrics、模型、物理、fit、装配或测试。7600在公开docs/README/AGENTS/src/scripts/tests整数字边界搜索无匹配，不能据此保证未公开raw未使用。新协议、route文件及source review的读取/解析与必要检查另由receipt计账，搜索/Git/编辑器/OS IO未知。本协议的具体执行源指纹由完成实现后冻结，不将作者设计当作已执行证据。
