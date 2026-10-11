# FR0：自由 root 地面域的2ms反馈工程资格

状态：事前外部候选，尚未生产发布、源码冻结或执行。拟生产路径为 `docs/FREE_ROOT_FAST_FEEDBACK_ENGINEERING_PROTOCOL.md`。本候选只依据既有设计与主代理确认的条件；不读取 Z2 输出、旧 raw，不导入实验、不调用模型、fit 或物理。主代理先完成 Z2 首次结果归档，再发布、必要新纯检查、冻结来源及正常提交推送；FR0 只能随后从干净提交首次执行一次。

本阶段检验：原自由 root 仰卧地面身体在原物理与权限下，固定 PD64/Kd(4,4)每2ms反馈，能否完整完成两目标、满足末窗误差，并在三个阶段分别观察到受控左臂与地面的正法向力。工程通过只允许另行冻结本域学习协议；不证明身体学习、接触因果、持续支撑、风险降低或 C4/C5 科学验收。

## 唯一来源、初态与先验

实现路径固定为：

- `src/developmental_physics/free_root_fast_feedback_environment.py`，类 `FreeRootFastFeedbackGroundBodyEnv`；
- `scripts/validate_free_root_fast_feedback_engineering.py`；
- `tests/test_free_root_fast_feedback_engineering.py`。

wrapper 继承原 `GroundBodyEnv.step/reset`，只构造 `ExplorationConfig(control_substeps=1)`。原 ground_body 资产的 free root、floor、几何、质量/惯量、接触参数、碰撞过滤、电机、关节、IMU、重力与积分器不改，不加 mount、吊架或固定支撑。physics_dt=.002s、torque_limit=.5Nm、基础速度20rad/s、joint_limit_margin=.08rad、动能50J、reset_clearance=.005m、baseline地面 profile等原默认物理和保护保持。PD 的 Kd 是动作反馈系数，不修改资产 damping。

唯一 seed 为 **7800**，fresh对象仅一次 reset，pose固定 `supine`。主代理已对公开 README/AGENTS/docs/src/scripts/tests 做一次 exact整数边界搜索，0matches；未读取 raw，不能保证非公开用途未见。原关节初值、该 seed 的 jitter、root初态及几何最低点抬至地面上5mm的 reset算法保持。prefix的落地、被动滚动与冲击全部付费；不预积分、选择接触后帧重置或更换姿态。

与旧 G 比较，本候选同时改变反馈/研究检查频率和肩 Kd（0→4），不能当单独频率因果对照。公共身体、理想原生感觉、PD增益、基础保护、仰卧姿态及人工目标均为公开先验；增益不是学习获得的。与悬挂 Z 域的差异也不能直接归因为接触。

## 时间、动作和目标

上限为6s、**3,000控制调用 / 3,000物理子步**。每次完整返回恰一次2ms积分；在下一个请求前重新读取原生 q/v。

| 阶段 | 固定完整人口 | 请求/目标 |
| --- | ---: | --- |
| prefix 0..999 | 1,000端点 / 2s | 八轴请求零 |
| A：active 0..999 | 1,000端点 / 2s | qref+s*.04rad |
| B：active 1000..1999 | 1,000端点 / 2s | qref+s*.08rad |

qref只取完整 prefix999 after端点的肩/肘 q。逐轴以公开限位选择 `s=+1 if U-qref>=qref-L else -1`，等距取正。两个目标均须在 `[L+.03,U-.03]`；不可行即失败，不 clip目标、换方向或重装到通过。actor只使用当前目标，没有切换预告。

active两轴请求为 `clip(64*(target-q)-4*v,-.5,.5)`，其余六轴始终请求零。原逐积分方向 guard保持：距限位.03rad内向外请求置零。保存控制请求、环境已应用请求和实际 actuator torque，三者不混写。不加重力补偿、模型、MPC、教师、滤波、速度屏障、救援动作、增益或频率扫描。

## 停止与完整工程门

prefix只走原基础保护，不提前定义 qref或追加 StudyAbort。active每个完整2ms返回端点后，肩/肘任一轴 `abs(q-qref)>=.12rad` 或 `abs(v)>=1rad/s` 即研究停止，等号停止。原环境非有限量、solver warning、八轴速度/角度/动能等保护不放宽。研究检查由20ms变2ms，数字阈值相同仍是新的检查语义。

先计费并保存终端区间，再评停止或后续审计。停止、部分/零子步、采集/查询/写盘异常均保留已支付数据和未知项，不追加控制或 reset。停止端点即使已完整积分也不能使 trial complete。

工程 pass 必须同时满足：

1. 原自由 root 物理/资产和新执行接口精确绑定冻结来源，trial前后不漂移；分别保存物理与执行配置身份。整体原参数 hash含substeps，不能伪称与旧 G hash相等。
2. 完整1,000prefix+2,000active及3,000确认子步；每次恰一子步；零环境/研究停止与采集异常。原生端点、时间、请求、实际努力与接触审计完整有限。
3. 仅在整个 trial complete后评分：A的 active800..999、B的 active1800..1999，各200个完整端点，肩/肘共四项位置 MAE均 **<=.01rad**。任一停止/异常令四项全部 unavailable，即使先前窗口已收满；不部分排名或用prefix稀释误差。
4. prefix、A、B各完整阶段至少一个端点具有 **left_arm-floor正法向力**。三阶段分别验收，不以另一阶段或其他身体接触代替。下面定义与分类冻结，揭晓后不改比例、正力阈值或窗口。

## 端点接触资格与额外只读查询

每个已确认保存的2ms端点，audit遍历全部 `data.ncon`，逐对计 `audit_contact_pair_inspections`。仅 floor配对额外调用一次 `mj_contactForce`（Fn<=0也查询），分别计尝试/返回/异常；不调用额外 `mj_forward`、step或积分。原环境既有诊断查询与新增audit查询分开计账。原付费返回先保存，audit失败不抹去此前原生端点。

floor配对按另一 geom唯一分类：`left_upper_arm_geom/left_forearm_geom`为left_arm，`left_foot_geom/right_foot_geom`为feet，其余为other。逐对保存 geom1/2及other名称、distance_m、contact_frame_force6、signed_normal_force_n和 `positive_normal_force_n=max(0,Fn)`（力单位N）；非有限力或距离为失败，不能筛掉后称完整。原生端点完整性与接触audit完整性分开保存；audit失败仍保留已取得的实际力矩、努力及确认子步，接触缺失明确为unknown/已知下界。

每类别在一个端点的positive值为该类所有floor配对positive_normal_force之和；和>0则该端点该类别计1，与该端点配对数无关。left_arm资格使用该规则，严格阈值0，不设数据驱动 epsilon。全部类别、全部阶段的实际比例都报告。

完整阶段各分母固定1,000；保存positive端点数、数/1,000比例、端点计数对应的 `数*.002s`，以及正法向力峰值和 `ΣFn_positive*.002`端点采样冲量估计。采样时长/冲量不等于连续接触时长或精确连续冲量。部分阶段同时报告 planned/paid/captured/unknown及已保存人口上的比例，不把未知端点当零，也不以这些比例验收工程门。

每阶段一次正力只证明该阶段观察到受控臂—地面相互作用，不证明持续支撑、任务受接触主导、控制接触因果或完整接触技能。接触力、分类、root位姿、机械能和未来实际力矩只作审计，不进入 PD或未来部署模型。actor仍只使用当前两轴q/v、公开当前目标；native没有root quaternion/orientation。

## 预算、保存与继续边界

控制尝试/确认子步上限3,000/3,000，actor PD向量请求上限2,000。**0学习模型构造/restore/forward、0fit、0RLS、0MPC、0教师/任务策略/GPU训练**；MuJoCo物理模型构造/reset及原工程forward另计。感觉、保护、PD、既有诊断、新接触pair inspections/force查询、来源读/hash、序列化、压缩、写盘与CPU/wall分别计实际费用。接触查询数量由已付费端点的实际 ncon/floor配对决定，不预填上限或零。

实际 absolute/squared努力按全部已支付2ms子步积分，prefix/active和停止前数据都保留；未确认积分、未保存端点/努力保持unknown或已知下界。历史物理与计算账不归零。不用较少步骤、查询或零停止宣称效率/安全优势；2ms仿真反馈不证明CPU实时deadline或真机可执行。

保存唯一seed、完整配置/依赖、clean源commit、全部必要source字节pin、接口/物理/资产与初态身份、首次stdio、逐步原生轨迹与请求/实际力矩、停止/异常、全部额外查询计数与contact记录、阶段接触摘要、完整性/四MAE及不可用原因、实际努力和预算。生产入口固定绑定生产协议路径，要求clean HEAD且必要source bytes等于 `git show`，正式pin在发布/必要纯检查后冻结。

首次失败封存并关闭该域学习入口，不补跑同一配方到通过，不扫描seed、目标、增益、频率、接触分类或物理。若有可证明的实现错误，保存原失败后仅做源码修复，后续实验仍须另冻结前瞻协议；科学失败则先限于已保存证据的有界诊断，不预认更多探索/新特征必然有效。

FR0通过也仅允许另冻本域校准、独立预测、匹配完整控制及强PD协议；不能立即运行学习或恢复悬挂Z learned snapshot。所有科学标志保持：
`scientific_adoption=false`、`old_free_root_C4_validation=false`、`c4_scientific_validation=false`、`c4_contact_scientific_validation=false`、`c5_scientific_dependency_released=false`。C4/C5–C7未验收，持续目标保持active。

