# C4 双轴有限 PD 开发：冻结协议

2026-10-11。根据首次 shoulder/elbow 组合 PD64/(0,1) 三个 development seed 在 active1 速度停止的已知结果，冻结本有限双轴开发。此前仅使用合成数据完成实现与独立标准库审计联调；代码、协议和相关检查提交推送后，从 clean HEAD 一次执行预定矩阵。

固定 development0/1/2、supine、原生 j0 left_shoulder 和 j1 left_elbow，不改变原8D顺序，其他六轴请求恒零。Kp=(64,64)，阻尼按 `product([0,1,2], [1,2,4])` 顺序：candidate0=(0,1)、1=(0,2)、2=(0,4)、3=(1,1)、4=(1,2)、5=(1,4)、6=(2,1)、7=(2,2)、8=(2,4)。候选0是原组合；固定Kp的有限阻尼开发不称全增益最优，也不构成身体模型方法优势。

每 trial fresh reset，seed 原 `SeedSequence(seed).spawn(2)[0]` 派生，真实100步zero prefix。自己的付费原生8D末端和公共关节范围确定 qref0/1 与固定方向，略负肘 qref 不裁剪；不缓存或复用前缀。200active前100步目标 qref+s*.04，后100步 qref+s*.08，每次只读取当前目标，切换不预告；任何目标不满足公开范围内侧 `.03` 则 trial普通失败，不裁剪或换目标。共享 baseline接触、20ms控制/2ms子步、每轴±.5Nm及原环境保护。PD `clip(64*(target-q)-kd*v, -.5,.5)`只读取当时原生q/v/target，不读取身体模型、接触或未来实际力矩。

执行次序 seed0全部九候选、seed1全部九候选、seed2全部九候选。完整计划27trial/8100calls/81000substeps/0updates，162s模拟；prefix2700calls/27000substeps、active5400calls/54000substeps。每候选每seed启动与控制均计开发费用；所有失败、停止、partial、复位后动作均记实际费用，不补跑、不延长prefix、不增删候选或改seed。

active返回端点任一所选轴abs(q-qref)>=.12或abs(v)>=1触发StudyAbort，等值触发；prefix只使用原环境保护。study/env/error分别保存，环境主reason优先。完整terminal端点可计20ms跟踪，最后计划端点stop仍不complete；partial保留两轴原始目标误差，不进入20ms评分。普通失败继续独立下一trial；KeyboardInterrupt/SystemExit/IO或任何trace序列化/写错误fatal，余下planned记录blocked。PD请求计算异常发生在step前，不增加物理费用。

请求绝对/平方努力按finally已付费子步累计。实际努力仅读returned原始8D applied history，各axis和双轴和都保存；缺失历史继续明示known下界/missing，不填零，不能获选；非法历史是普通trial错误。没返回的paid子步也计费并保持actual/risk unknown。full/prefix/control保存全身体子步接触峰/冲量、动能、穿透、8D最大原生速度、guard计数/限位端点/饱和及遥测缺失，不能把努力称机械能或给安全保证。

逐trial保存两轴及200×2联合tracking原始RMSE、完整/partial errors；两目标段0–99/100–199与原计划末20端点80–99/180–199，分别保存planned、returned、complete、partial、missing、signed mean与RMSE。窗口不足为实际数量/缺失/null，不重新编号、填零或缩短计划。记录全部候选和原生8D观测、请求、actual history、公开limits、qref/方向、PD raw/clipped、study/env/error、qpos/qvel仅诊断和paid账本。

选择资格：同candidate所有development0/1/2均200active完整、fresh100prefix完整、无stop/异常/非法非有限/trace缺失，而且每trial实际力矩历史覆盖全部paid子步。未完成candidate不得按截短RMSE排序。eligible按以下精确顺序升序：①三seed联合tracking原始RMSE均值；②三个seed联合tracking原始RMSE的最大值（最差seed）；③三seed双轴active实际平方努力和的均值；④candidate索引。精确并列只依该顺序，不用epsilon、更改gain或各seed各选一个。若没有eligible，selection状态blocked、picked=null，所有候选的资格失败原因与已付费成本继续公开。

独立最终或身体方法对照必须另冻结；development0/1/2已见，20/21/22也已在此前肩评价使用，均不冒充新最终bank。此开发矩阵不读取新留出，不进行身体拟合、策略或增益在线更新；选择结论限于上述有限候选。

每次归档source原字节ZIP/SHA、协议SHA、依赖版本/Python/CPU/GPU=null、sourcecommit/status/每文件Gitblob与快照绑定、环境参数前后fingerprint及实际账本。`scripts/audit_pair_pd.py` 与其依赖必须纳入ZIP；缺独立auditor、dirty或未tracked来源禁止正式physics。工程synthetic显式替换真实env，sourcecommit/blob不伪造，metadata清楚记录未进行Git读取及auditor待补，不支持科学采用。

正式实现为 `src/developmental_physics/pair_pd_development.py`，独立审计为 `scripts/audit_pair_pd.py`；FORMAL_EXECUTION_FROZEN=True，审计PRODUCTION_SPEC科学冻结。协议、代码、相关测试提交推送后，从clean HEAD一次执行完整预定九候选×三seed，保存所有失败而不补跑。草稿03联调采用旧worst-axis排序；在真实执行前发现与原指定worst-seed层级不一致，已同步修正collector/auditor/protocol并用独立反例检验，03原始档案保持原样。

复现：`python -m developmental_physics.pair_pd_development --output <新目录> --protocol docs/PAIR_PD_DEVELOPMENT_PROTOCOL.md`；审计：`python scripts/audit_pair_pd.py --input <原始目录> --output <新JSON>`。在仓库根目录设置 `PYTHONPATH=src`，使用可选MuJoCo CPU环境。源码ZIP涵盖全部当前physics Python源、资产、协议、pyproject及两份独立审计；每份与clean采集commit的Git blob及SHA绑定。生产和合成检查均使用tracked源路径；合成scope显式 `synthetic_fixture=True`、`scientific_frozen=False`，始终不能获得科学采用。
