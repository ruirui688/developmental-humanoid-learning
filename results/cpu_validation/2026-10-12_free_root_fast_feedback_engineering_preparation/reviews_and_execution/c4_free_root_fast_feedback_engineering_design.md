# 待审草案：原自由 root 地面域的 2ms 双关节反馈工程资格

状态：仅事前设计，尚未批准为正式协议、未写生产控制代码、未执行。主代理在 Z2 首次结果归档后选择是否冻结这一唯一候选。本草案不读取旧 raw、不复算旧数学、不导入 MuJoCo、不调用模型、物理、fit 或辨识。

## 研究位置与可检验假设

悬挂固定域已经取得的工程和预测证据不能代替自由身体、真实地面接触 C4。这里提出一个有界的经典控制可达性检查：原自由 root 仰卧地面身体在相同物理和权限下，每 2ms 原生两轴 q/v 反馈与固定 PD64/Kd(4,4)，能否完整执行原两目标并在两个末窗达到指定位置误差？

工程通过只允许另行设计该域的辨识；它不能证明模型学习、预测贡献、风险降低、站立、发育成熟、C4 科学验收或 C5 依赖解除。Z2 尚在执行，本草案不预设其结果，也不引用未读取的结果数值。

## 原域的准确初始条件

来源为 [GroundBodyEnv](../src/developmental_physics/environment.py)、[原身体资产](../src/developmental_physics/assets/ground_body.xml)与 [G 冻结协议](../docs/GUARD_PD_TAIL_CONTROL_DEVELOPMENT_PROTOCOL.md)。旧 G collector 的初态、目标、研究停止定义只作静态参考，没有调用其恢复、预测、指标或物理代码。

- 原资产保留 `freejoint name="root"`；没有 mount、固定支撑、外部约束或吊架。floor、全部身体几何、质量/惯量、碰撞过滤、关节、电机和 IMU 均保留。
- 只使用原 `GroundBodyEnv(ExplorationConfig(control_substeps=1))` 配置；其余 dataclass 字段取原默认值：physics_dt=.002s、torque_limit=.5Nm、基础 joint_speed_limit=20rad/s、joint_limit_margin=.08rad、kinetic_energy_limit=50J、reset_clearance=.005m、ground_contact_profile="baseline"。
- 原重力 `(0,0,-9.81)`、implicitfast、资产关节 damping=.15/armature=.01 和原接触参数保持，不修改以取得通过。PD 的 Kd 是动作计算中的反馈系数，不修改资产 damping。
- 姿态固定为 `supine`，对应 root 初始轴角 `(0,1,0), -pi/2`。原 reset 关节值 `[0,.12,0,.12,0,.12,0,.12]` 加该 seed 的每轴 uniform(-.015,.015)；原 resetData、几何最低点抬至 floor 上 .005m 的算法保持。
- 这不是从已接触、已稳定状态开始：reset 刻意留 5mm clearance。原零请求前缀的落地、被动滚动和接触全部付费；不偷偷预积分、修改位姿、选择落地后帧重置或跳过冲击。
- 工程 seed 建议固定 `7800`，唯一 fresh trial、唯一 reset。正式冻结前主代理核对其未用于本域的试验或候选选择；若有已用事实，只能在首次执行前明确更换并冻结，不能根据输出更换。当前没有读取旧 raw 来验证 seed 是否未见。

## 唯一候选、时间与目标

相对原环境仅把 `control_substeps:10→1`；物理积分仍为 2ms，一个返回控制区间最多一次积分，每 2ms 重新读取原生 q/v 并计算下一请求。

相对 G 原控制实验，不能描述为只改变反馈周期：G 的共享 PD 是 Kp(64,64)/Kd(0,4)，本候选 Kd(4,4)还新增肩阻尼。它继承悬挂 Z 工程所用的公共控制知识，**不是身体学习获得的增益**。研究检查也由 20ms 变为 2ms；数字阈值相同仍不等于旧终止语义完全相同。

完整上限为 6s、3,000 控制调用/3,000 物理子步：

| 区间 | 固定调用人口 | 请求/目标 |
|---|---:|---|
| prefix 0..999，2s | 1,000 | 八轴请求均零 |
| active 0..999，2s | 1,000 | 两轴目标 qref+s*.04rad |
| active 1000..1999，2s | 1,000 | 两轴目标 qref+s*.08rad |

qref 只来自完整 prefix999 的 after 原生肩/肘 q。方向逐轴由原公开范围选择：`s=+1 if U-qref >= qref-L else -1`，等距取正。两个目标都须落在 `[L+.03,U-.03]`；不可行即失败，不 clip 目标、不换方向、不更换 seed/姿态。只消费当前目标，不预告切换。

active 每步 `raw_i=64*(target_i-q_i)-4*v_i`，逐轴 clip 到 ±.5Nm；其他六轴请求始终零。原逐积分关节方向 guard 保留：距限位 .03rad 内若请求指向限位外，则该轴执行请求置零。实际 actuator torque 与最终已知请求分别记录，不能假定二者完全相同。

不加入模型、MPC、教师、重力补偿、速度屏障、滤波、增益扫描、额外目标或救援动作。原机身仍可被动滚动；这不是悬挂或站立域，也不要求保持某个仿真 root 姿态来选择动作。

## 原停止与新检查语义

原环境在积分前后执行基础保护：非有限 state/传感/能量、solver warning、任一八轴速度超过20rad/s、角度超公共范围与 .08rad 容差、动能超过50J等均锁存停止。这些保护不放宽。

prefix 只走基础保护；没有先验 qref，也不追加研究 StudyAbort。完整 prefix 成功后才生成 qref/目标。active 每次完整返回的 2ms 区间后，肩或肘任一轴 `abs(q-qref)>=.12rad` 或 `abs(v)>=1rad/s` 即 StudyAbort，等号停止。该规则保留 G 的 active-only/any-axis/阈值与比较；更高检查频率是新接口先验。

终端区间先计费、保存原生端点与全部诊断，再停止；即使执行了单个完整子步，触发停止的 trial 也不标 complete。停止后不追加制动/纠正、不重新 reset，不用较少动作称样本效率优势。部分/零子步返回、异常或保存失败明确归档。

## 最低完整工程资格

以下条件同时成立才允许准备新辨识协议；不据此执行辨识：

1. 原自由 root 资产/物理/范围/接触/pose/reset 算法精确符合冻结来源，只有执行 substeps 配置改变；新执行配置为 2ms/2ms、trial 内不漂移。原 `parameter_fingerprint` 包含 config，因此会随 substeps 改变，不能要求与 G 整体指纹相等。正式实现须分别绑定资产/物理数组与新执行接口，不能伪造旧 hash 相等。
2. 全部 1,000prefix+2,000active 及 3,000 子步完整，每次返回恰一子步；0 环境停止/StudyAbort/采集异常。逐步时间、原生 observation、请求/已应用请求、actuator torque、实际努力及接触诊断完整有限，完整与风险资格独立保存。
3. 全 trial 完整后，active800..999 与1800..1999，各200个完整端点/末0.4s；肩/肘分别 MAE<=.01rad，四项均通过。任何 trial 不完整时两个窗均 unavailable；不以 partial RMSE 排名、不用 prefix 稀释 active 误差。MAE 窗/门是事前工程资格，不追认 G 旧控制/预测门。
4. **真实接触资格另行明确记录：** prefix、目标段A、目标段B每个完整阶段至少一次观察到 floor 与 left_upper_arm_geom 或 left_forearm_geom 配对，且该配对法向力>0；逐阶段保存有限已确认观察数、持续时间/比例、法向冲量与峰值。只出现其他身体接触不足以确认受控臂接触。该最低条件只证明该阶段观察到受控臂—地面相互作用，不证明持续支撑、任务全程受接触主导或控制接触因果；不能把一次接触称作完整接触技能。所有端点/努力仍用完整人口。

接触定义需要主代理在正式冻结时确认是否足以承接后续研究问题；它不能在揭晓后通过改分类/窗口/正力阈值取得资格。若研究必须检验持续左臂支撑，应在首次执行前另外选择明确比例标准，此时不能仍称本草案已冻结。本草案没有根据已见轨迹估计比例阈值。

原 `diagnostics()` 只提供总 ground_contact_count/ground_normal_force，不返回接触 geom-pair 及分配到 left_arm 的法向力。因此第4项目前有**具体接口依赖**：未来工程 collector 须离线记录每个2ms after端点的 floor 配对几何和法向力，并按预定 left_arm/feet/other 分类；它只作资格/风险审计，绝不传入 PD、未来部署模型或选择动作。若未补这个只读遥测接口，最多能验证全身体总地面接触，不能声称受控臂接触资格通过。

## 可用感觉与信息边界

原 observation 提供理想八轴 joint_position/joint_velocity、IMU gyro/acceleration、actuator_torque 与 previous_command。PD 只消费当前肩/肘 q/v 和公开当前目标；公开关节范围只用于目标方向、可行性及底层 guard。

未来身体辨识仍须另冻结输入、初始化、更新预算与留出人口。本草案不决定新增模型特征，也不把 IMU 可用等同于已识别接触/朝向。原 observation 没有 root quaternion/orientation。已知请求和同 trial 连续过去端点可以另按协议使用；未来实际 torque、接触标签、真实动力学、root 位姿/朝向与机械能只作离线诊断，不作为部署输入。悬挂 Z1 learned snapshot 不恢复到该接触域，不把迁移先验包装成原地面从零辨识。

## 预算、先验与解释边界

上限控制尝试3,000/确认积分3,000/PD向量请求2,000；0模型forward/restore、0fit、0RLS、0MPC、0教师/任务策略/GPU训练。原控制/物理累计账不归零。构造/reset/forward、感觉、保护、PD、接触诊断、写盘及来源核对也计计算费用；未确认积分、未保存端点/努力保持 unknown 或已知下界，不预填为0。真实努力按全部已付费子步分别算 absolute/squared，停止前交互同样保留。

较20ms接口，完整6s物理子步预算不变，但控制/感觉/反馈机会从300到3,000；较 G 原 PD 同时改变肩阻尼。不同 seed、域、旧停止轨迹或新通过结果不构成频率/阻尼因果对照。公共 PD、理想感觉、身体/底层保护、两个人工目标与初始姿态都属于需要披露的先验。自由 root 和真实碰撞存在也不能自动证明物理安全、机器人学习或真机泛化。

正式路线如果采用此草案：先完成遥测与新接口必要纯检查/静态 review，冻结单个精确协议与源码，正常提交推送后仅从 clean commit 首次执行一次。失败封存，关闭其辨识入口；不在同安装上补跑到通过或扫描 seed/增益/频率/目标/物理。通过后仍需另冻结本接触域新校准、独立多时距预测、匹配完整控制与强 PD 对照，全部原科学门及新留出验收缺一不可。

`scientific_adoption=false`、`old_free_root_C4_validation=false`、`c4_scientific_validation=false`、`c4_contact_scientific_validation=false`、`c5_scientific_dependency_released=false`。C4/C5–C7依赖未解除，持续目标保持 active。
