# C2-B：校准剂量 × 身体模型结构的开发消融

> 2026-10-11；正式物理运行前冻结。development0/1/2，supine / joint0；不读取或执行新最终20/21/22。

## 1. 问题与固定条件

分别检验改变校准幅度配方、增加固定signed-hinge特征是否改善独立预测并转化为控制收益。两个因素为old/new校准 × linear4/hinge5结构；两条配方都是多剂量。

全组固定 **endpoint_euler**。依据C2-A clean source `11410862f7cc450322d143abfd1eb7102a222212`、首次独立审计SHA256 `f45e6f1937dc87fc9da6b858a4131b38215a76212919675347e107cce1ba9925`：数据一致性通过，积分采用门失败，`validated_pass=false`。不在本批结果后切换积分。

共享旧身体资产、baseline接触、理想原生信号、supine/left_shoulder、派生reset seed、公开限位与独立保护。控制20 ms、物理子步2 ms，请求上限.5 N·m，其余七关节零请求。模型仅读当前encoder q/v及当前已知请求u，下一encoder v是校准标签；实际未来力矩、接触、隐藏质量和仿真状态只作诊断，不进入控制。目标、模型结构、固定折点和MPC属于公开先验。

## 2. 校准与双模型更新

每trial独立reset并执行100步真实零请求前缀。qref和一次性方向由前缀末原生encoder及公开限位得到，各trial必须精确配对。校准各300步，10个30步block均为5正/10零/5反/10零：

```text
old = [.125,.25,.5,.125,.25,.5,.125,.25,.5,.125]
new = [.125,.25,.5,.375,.25,.5,.375,.25,.5,.375]
```

只改变第4/7/10个block的.125→.375，不修改时序、目标、权限或按误差挑动作。两配方前90校准步须精确复现。new减少.125暴露且增加.375，不能把整套配方效果只归因于增加剂量，或宣称已解决q覆盖。

每条真实校准同时更新两个独立冷启动模型：linear4特征`[v,q-qref,u,1]`、theta=`[1,0,.02,0]`；hinge5特征`[v,q-qref,u,sign(u)*max(abs(u)-.25,0),1]`、theta=`[1,0,.02,0,0]`。各自P=100I、lambda=1、原RLS更新/对称化；不同模型互不读取参数、残差或更新结果。相同输入的两个名义初始化预测完全等价。raw更新位置诊断沿用Euler，评价也固定Euler。

每完整20 ms转移，各模型预更新预测后分别原子更新；共享转移ID与各自ID/theta/P/count/hash保存。每seed600真实校准转移、1,200模型更新，全批1,800转移/3,600更新；不称3,600独立物理样本。部分间隔不更新，成功的另一模型更新不能因单结构失败被抹掉。

old/new校准active完整请求绝对/平方努力分别.55/.20与.70/.275（N·m·s / (N·m)²·s），增加27.2727%/37.5%。全批两配方合计3.75/1.425。实际努力从真实子步力矩计算，不能声称同努力预算。

## 3. 共同预测、闭环与固定预算

两条共同预测各100前缀+100active，5个20步block均为7正/3零/7反/3零：

```text
low  = [.25,.25,.25,.25,.25]
full = [.125,.25,.375,.5,.375]
```

全部四个冻结learned模型、共同nominal和恒速度持久性评价同一真实轨迹，预测在step前生成，不更新。low/full完整请求绝对/平方努力分别.35/.0875与.455/.170625；full的.375有两个block、共28非零样本，.125/.25/.5各14，零30。所有block与幅度分箱均保留，不选有利段；不同预测轨迹误差不作为配对模型因果差值。

五闭环为old_linear4、old_hinge5、new_linear4、new_hinge5及nominal MPC，各100前缀+200active。固定原H15、9候选、权重/范围/回退/决胜；前100active当前目标qref+direction×.04，后100为×.08，不预告切换，不更改控制器或用PD结果调参。

每seed固定顺序：calibration_old、calibration_new、prediction_low、prediction_full、old_linear4_mpc、old_hinge5_mpc、new_linear4_mpc、new_hinge5_mpc、nominal_mpc。三seed共 **27 trials / 8,100控制调用 /81,000子步 /3,600 RLS更新**。前缀2,700/27,000，校准1,800/18,000，预测600/6,000，控制3,000/30,000。模拟时间162 s；策略、教师、演示均0。规划数学调用与wall、审计重放另外计账。

任一结构更新/校准失败，该剂量calibration标失败并保留各自已付更新，阻塞该剂量两MPC及依赖两条完整校准的low/full预测；另一剂量和nominal独立继续。nominal从自己的付费前缀建立公开名义模型，不依赖成功校准。普通trial失败不补跑；日志/IO/中断fatal，剩余计划blocked。请求努力按真实执行子步计费；已返回未存行从ledger与唯一异常请求恢复，缺失实际遥测/指标标下界或不可重算，不能填零冒充完整。

## 4. 独立审计与预定开发选择

数据一致性与科研门分别判定。独立标准库审计重算4/5维RLS、全部输入/冻结hash、Euler/MPC、源commit/blob/ZIP/manifest、前缀、合法窗口与真实努力、各phase/trial/batch上限、失败依赖及成本。历史锚点为旧C2-A/E1开发old-hinge校准、low预测、nominal和old-hinge控制，精确复现不增加独立seed数。

以 **old_hinge5** 为anchor。候选编号0=old_linear4、1=old_hinge5、2=new_linear4、3=new_hinge5。新候选须三seed全部完整，两个共同预测的完整速度RMSE逐seed不劣于anchor；200步tracking逐seed不劣，原始RMSE算术均值至少低5%；控制实际绝对/平方努力均值分别≤1.05×anchor。零分母不算百分比，努力anchor=0仅允许candidate=0。无候选通过保留anchor；多候选按raw tracking均值、实际平方努力均值、维数、编号精确决胜。不按每seed选不同模型，不改门/追加剂量。

全报逐seed结构差hinge−linear、剂量差new−old、差中差，对q/v预测、tracking、努力与风险分别计算；三开发seed不作显著性或未见优势。共同预测是配对输入，闭环差是各组不同状态轨迹上的整套控制效果。采用门只决定默认，不能同时证明单组件贡献或安全。

## 5. 描述性诊断、风险与后续

全模型在两预测、校准最终in-sample和各自控制轨迹上报告1/5/15/50步自由递推端点/路径q/v、持久性、有效/排除窗口数及非有限预测；不回灌未来状态，不跨stop，完整terminal转移可作窗口末端。预测合法计划窗口100/96/86/51，控制200/196/186/151，校准300/296/286/251；重叠窗口不算独立seed。记录未来请求只是离线条件输入。

报告每block/幅度、切换/保持、校准q/v包络、闭环越界比例与最近校准样本距离。描述口径固定：各剂量的300个完整active转移的输入q/v构成校准样本；控制使用完整active转移的输入状态，q/v分别以严格小于min或大于max计域外（端点等值算域内），各自及并集比例均报。最近样本距离为`min_i abs(q-q_i)`（rad），报告均值/最大值；它只描述位置距离，不声称联合q/v或动作距离，不作阈值门。包络不是安全集。全部full/prefix/calibration/prediction/control子步接触峰/冲量、动能峰、最深接触距离、八关节原生端点速度/软限位/权限屏蔽、饱和/回退/停止保留。缺失遥测标下界；努力门不授予安全结论，不能只用共同前缀峰掩盖active风险。

本批不新增PD物理，C3选定Kp64/Kd0及全部调优成本保留。新最终20/21/22保持未见；配方与最终门共同冻结后一次评估，不能先揭晓PD再选模型。若本批不能解决q覆盖，继续另立位置探索版本，明确额外开发成本。随后继续C4多关节、C5未知变化、C6成熟门控，单肩消融不结束持续目标。

```powershell
$env:PYTHONPATH = 'src'
external/cpu_physics_env/Scripts/python.exe -m developmental_physics.local_dose_ablation `
  --output external/local_dose_20261011_development `
  --protocol docs/LOCAL_DOSE_ABLATION_PROTOCOL.md --integration endpoint_euler
```

协议/实现/审计及相关测试先提交推送，从clean源码执行一次。相关：[A结果](LOCAL_INTEGRATION_ABLATION_RESULTS.md)、[PD](CLASSICAL_PD_DEVELOPMENT_RESULTS.md)、[持续阶段](CONTINUOUS_EXECUTION_PLAN.md)。
