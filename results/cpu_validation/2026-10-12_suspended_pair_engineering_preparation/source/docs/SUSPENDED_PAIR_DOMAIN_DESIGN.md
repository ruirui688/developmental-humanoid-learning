# X0：直立固定躯干、悬挂双关节的工程资格协议

本协议只冻结一次有边界的安装与可达性验证，**不包含学习执行**。生产源码、此协议及必要新装配检查封口并提交推送后，从干净提交首次执行一次。身体模型/残差控制的 X1/X2 由单独协议提前冻结，X0 通过也不得自动 fit 或进入学习。

## 选择依据与证据边界

W0 首次从 clean `54cf4c2253f211ee71cb093aa664681fede69592` 完成300控制调用/3000子步、零停止与零fit，但两目标段末20点的肩/肘 MAE 分别为 `.0145506801/.0138846234`、`.0391904611/.00653009851 rad`，没有通过每轴 `.01 rad` 资格门。原件保留；本协议不重跑该安装、不调整其高度或方向，也不读 W0 raw。

W0 失败只否定这个固定安装与冻结PD的工程资格，不能从一次PD失败证明普适不可达，也不能识别接触/传感/模型失配的因果。已转录实际 absolute/squared effort `3.947884319 Nm s /1.971174207 Nm² s` 接近共同权限的4/2上界，但尚未逐子步独立核对饱和，不能据此断言全部时间饱和。

唯一新选择是 **upright、机械固定torso、悬挂左肩/左肘**。它验证小角度可达性与基础采集工程，不是接触学习。原floor仍存在且记录真实接触，但左臂位于地面上方；被动脚部接触也不能说成受控手臂接触学习。原自由root C4、接触科学门、C5依赖与整个持续目标保持未完成。

公共形态提供选择动机：上臂/前臂质量 `.3/.2 kg`、长度 `.20/.18 m`，直立附近重力矩随小角度变化。忽略capsule端部质心微差的近似为

`tau_shoulder = 9.81*(.03*sin(q0)+.04*sin(q0)+.018*sin(q0+q1))`，
`tau_elbow = 9.81*.018*sin(q0+q1)`。

例如 `q0=.08,q1=.08~.20` 的肩重力矩约 `.08~.10 Nm`，与仰卧水平悬臂约 `.86 Nm` 不同。这是基于公开形态的静态近似，未使用 simulator 真值或 W0轨迹，不保证动态可达或PD通过，也不向控制器提供重力补偿。

## 唯一安装与信息边界

独立 `SuspendedGroundBodyEnv` 从原 `ground_body.xml` 生成XML：只移除torso freejoint，设置torso quaternion为 **identity `(1,0,0,0)`**，先设置位置 `(0,0,0)`。八轴关节/电机及标称几何、质量、阻尼、armature、限位、接触参数、碰撞过滤保留；另外六轴仍被动自由，请求恒零。移除六个root自由度改变编译拓扑、动力学、惯性反馈和实际静态碰撞过滤，必须披露，不能称与原自由root动力学等价。

X0 runner唯一seed为 **7400**。已对 docs/src/scripts/tests 搜索该整数：只有旧费用数字4374000的子串匹配，未发现seed使用；没有读取raw验证未公开用途。通用环境支持其他非负整数seed，供未来冻结协议fresh构造；每个对象只允许一次reset，X0不改变seed。

八轴初态为 `(0,.12,0,.12,0,.12,0,.12)` 加 `default_rng(seed).uniform(-.015,.015,8)`，全部速度零。使用原primitive最低点算法，在identity姿态先一次forward，再设置固定安装高度 `z=.005-lowest`，再一次forward。没有settling积分；全trial不移动安装、不换姿态/高度/摩擦/权限。生成前高度XML、安装后XML和runtime数组差异分别保存。

原5mm clearance在固定root下可能持续存在，脚部也可能没有地面接触。因此 **left_arm/feet/other真实floor pairs只作描述**，不要求接触才能通过非接触工程资格，不把保留floor几何当作接触证据。每个接触类都报告已保留子步的pair计数、正法向力事件与原始记录；若没有，明确为零观察。

机械安装全程提供固定支撑；安装反力未测为unknown，不能写成零支撑或零外部负担。actor只使用原生两轴q/v、当前目标和公开PD；原生IMU/其余q/v、接触、root世界位姿与真实动力学只记诊断，不选择动作。没有教师、策略、模型恢复、辨识或更新。

## 固定任务、权限和停止

100次零请求prefix完整且有限、无停止后，qref从本trial prefix99 after原生前两轴q获取。每轴方向精确为 `s_i=+1` 当 `U_i-qref_i >= qref_i-L_i`，否则 `-1`，等距取正；L/U为公开限位。不裁qref，不按接触改方向，不恢复旧prefix。

active0..99的目标为 `qref+s*.04`，active100..199为 `qref+s*.08 rad`，不预告切换。两个目标必须在公开限位margin `.03 rad`内；不可行失败，不clip目标或试另方向。

公共PD固定 `Kp=(64,64),Kd=(0,4)`，先按当前目标/原生q/v计算，再逐轴clip到 `.5 Nm`；其他六轴请求零。它已有控制知识，X0行为不称学习获得。原2ms子步、每控制10子步、baseline contact/config与角度guard保留。

原环境在每2ms积分前后执行保护。StudyAbort仍只在返回完整10子步后的控制端点判定：任一受控轴 `abs(q-qref)>=.12 rad` 或 `abs(v)>=1 rad/s`即停止，等号停止。完整terminal区间先保存/计费，再停止；不标completed。环境reason优先保留，同时StudyAbort另记；partial不通过完整门，prefix失败不能发布qref或继续active。

## 工程门、预算与失败分支

唯一矩阵为1个fresh trial，**100prefix+200active**，最大 **300控制调用/3000子步**；0身体模型forward、fit、RLS、MPC、策略/gain/gate更新、教师与预训练恢复。

工程资格必须同时满足：

1. 新identity XML确实编译为固定upright torso；`nq=nv=nu=8`，八轴name/address/motor映射正确，原标称关节/执行器/接触参数与公开资产一致，无意外参数漂移。
2. 全100prefix及200active、全部3000子步完整，无环境停止、StudyAbort或collector失败；每子步原生传感、实际actuator torque、applied request及时间完整有限，固定torso世界位姿未漂移。
3. 两段各最后20个完整active端点，每轴 MAE均 `<=.01 rad`，即active80..99和180..199；完整trial不可用时两个窗口均不可评估，不用partial子集通过。

接触不参与该门。四种旧科学/adoption flags永远false。通过只表示悬挂非接触工程可达性，不能表示接触身体建模、风险下降、效率优势、站立或儿童式技能获得。

任何资格失败立即封存付费交互、stop/error及负结论；本安装不在同invocation改变seed/高度/方向到通过。不能根据X0结果调整已经提前冻结的学习controller。下一选择另有依据、另冻结；原W0与旧自由root失败不删除。

## 独立实现、来源绑定和首次命令

新入口为 `src/developmental_physics/suspended_environment.py`、`scripts/validate_suspended_pair_engineering.py`。W0 frozen源码不修改：环境继承其逐子步保护/capture/partial账，runner仅复用其纯编码、公开目标/StudyAbort与窗口检查helper，不调用旧main_run，不monkeypatch。

通用环境为避免大段复制，先调用冻结W0 constructor（一次supine编译），再从原XML设置identity后重新编译真正的upright模型；不用修改已编译supine quaternion代替独立编译。两个constructor build都真实计账；唯一装配self-check还编译原asset的upright参照和安装后XML，都是非零计算、零积分。

source pins包括新runner/env、本协议、冻结W0 runner/env及原environment/asset/__init__的精确bytes/SHA；正式要求全部tracked字节等于clean40位HEAD，先核验再构造。X0 pins不包含学习/MPC实现。既有W0 helper中的旧协议pin不执行；新runner验证本协议和实际静态依赖。首次同trial逐子步telemetry由原保护路径采集，接触分类只附加标签。

唯一必要新装配self-check（由root首次执行，作者不预跑）：检查identity源XML/installed XML/当前模型几何、upright原资产静态对照、named public参数、native映射、世界root语义及0积分。该检查不重跑旧RLS/控制数学或科学raw审计。

```powershell
$env:PYTHONPATH = "src"
external/cpu_physics_env/Scripts/python.exe scripts/validate_suspended_pair_engineering.py --repo D:/Codex_ws/robot_rl --output external/c4_x_selfcheck_01 --self-check
```

新检查与协议封口、提交推送后，将 `SOURCE_COMMIT` 替换为真实冻结40位commit；只从cleanHEAD首次运行：

```powershell
$env:PYTHONPATH = "src"
external/cpu_physics_env/Scripts/python.exe scripts/validate_suspended_pair_engineering.py --repo D:/Codex_ws/robot_rl --output external/c4_x_engineering_01 --source-commit SOURCE_COMMIT
```

output必须新建、已有拒绝覆盖。保存首次stdio、配置/seed/版本/source、高度前与安装后派生XML、全部已捕获子步轨迹、native/fixed mount/contact三类记录、实际绝对/平方努力、source读/hash、编译/重置forward及PD账、控制调用尝试/返回、已确认积分子步、保存capture数和原件manifest。冻结保护核心没有完整的逐子步integration/endpoint-forward尝试计数：发生积分、forward或诊断异常时，未确认尝试、未保存端点及对应实际努力明确unknown/已知下界，不宣称全部attempt可测。写盘/压缩与wrapper外耗时另报；0学习不表示0计算。

## 后续路线与本次准备读取账

X1/X2需要自己的冻结协议、source和新物理预算；候选是仅自身两轴q/v和已知请求的coupled_hinge9原子RLS，并在共享已披露PD反馈的同一个残差controller中比较cold/learned，保持旧20%模型/同controller收益、PD5%、actual effort1.05及完整优先门，不用非接触工程门代替科学门。此处不授权执行、追加特征或调优化器。

即使悬挂机制通过，最终仍需另冻结原GroundBodyEnv的自由root真实接触域完整预测/控制迁移，再完成C5变化适应、C6成熟与C7新留出。被动feet接触或悬挂两臂可达均不解除这项依赖。支撑域结果与自由root不是单一因素的匹配因果对照。

本次X准备仅读取W0环境/runner静态源码各一次（11642/24683 bytes），随后为固定SHA各再读一次；原environment/asset/__init__仅为pins各读一次（15822/3430/162 bytes）。截至写入本协议，已知上述返回字节92,064；rg内容搜索、目录和OS IO真实字节未知，不以文件长度伪造测量。没有读W0或其他科学raw，没有实验import/执行、物理、body-model或RLS；新源码仅做必要AST语法检查。后续root审阅/self-check的实际读取/计算由相应receipt另计。
