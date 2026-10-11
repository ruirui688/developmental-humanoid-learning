# 肩—肘固定校准可执行性：无学习冻结开发协议

本协议在首轮真实执行前冻结。实现为 `src/developmental_physics/pair_calibration_development.py`，标准库独立审计为 `scripts/audit_pair_calibration.py`；源码、协议和相关synthetic检查提交推送后，从clean HEAD只执行一次预定六trial，audit显式指定该提交。保留全部失败与真实成本，不修改首次pair的5/5停止与科学门，不运行PPO/RLS/监督拟合/模型预测/策略或增益更新。

依据首次pair真实开发：三seed在cal active170、肘-only .5 block首个−.5命令停止，负向10子步全执行；此前5个zero端点仍有明显肘负向及肩零请求下的运动。block5–7的负向各被guard50子步屏蔽。故要先检验固定短脉冲完整采集，而不能从5/5结果断言缩短即可通过。

## 固定矩阵与计账

两候选pulse2/zero8/pulse2/zero8，以及pulse1/zero9/pulse1/zero9；每block20active，正/反指相对每轴固定s。每候选各development0/1/2，顺序pulse2 seed0/1/2后pulse1 seed0/1/2，**预定六trial均执行**；不按第一候选结果新增、删除或重试动作。

原supine、原生j0肩+j1肘、其余六轴请求0、fresh env/reset、各轴权限.5、baseline接触、20ms/2ms、原保护全部保持。各trial独立100真实zero prefix，再400active；固定已披露SeedSequence派生reset seed：0→3757552657，1→1641411168，2→2001025171。prefix末原生qref不裁，按公开limit较大距离选s，equal选正；不缓存上trial prefix。

20个block原布局不变：0–4仅肩、5–9仅肘、10–14两轴同向、15–19两轴反向；幅度各重复[.125,.25,.375,.5,.25]。正slot为0至pulse−1，反slot为10至10+pulse−1，其余0。没有未来actual反馈选择幅度、zero等待终点或按表现增加probe。原5/5不重跑。

完整上限 **3000env.step /30000子步 /0学习更新**，每候选1500/15000。phase prefix600/6000、active2400/24000；模拟60s。2/8每trial每轴计划request绝对/平方努力.36/.1275，1/9为.18/.06375；actual子步history另算。停止、失败与partial按真实attempted/returned/paid计，不按计划凑数。

## 停止、原始观测与完整性

active返回原生端点任一j0/j1 `abs(q−qref)>=.12` 或 `abs(v)>=1` 触发StudyAbort，equal触发；prefix只原环境退出。原环境stop优先主reason，study及全部触发轴独立保留。末计划步terminal也不算complete。partial端点、非有限/非法8D、子步history缺失或不完整risk telemetry均不能获得eligible；不补齐10子步、不延长prefix、不复位重试。

只用当前原生8D encoder、step前已知request及公开限位决定固定方向/命令；IMU、actuator feedback、previous accepted command原序保存。qpos/qvel、contact/force/energy/penetration、actualhistory和fingerprint只诊断，不进入动作反馈。无body model对象，没有模型或任务教师输出。

每完整/partial返回行保存native8D请求、前后观测、原生8D actual子步history、每子步force/energy/contact distance、study、qpos/qvel和model_update=None。真实call/step/physics、phase request努力finally计账；actual努力只取完整合法returned历史，缺失unknown/lower bound。未返回paid子步、已返回未写行、trace失败独立保存。ordinary stop/incomplete继续下一预定trial；interrupt/integration/IO/trace/非法遥测异常fatal，余下planned blocked，不补跑。

plant/source/config保持固定，fingerprint变化或缺失不能eligible。exception后尽力保留原异常与计账，after fingerprint单字段失败不能把已付费用清零或覆盖主异常。

## 候选选择门与结论边界

每候选必须三seed各500完整调用/5000子步、100prefix+400完整active、stop/error/trace failure均0、原生和子步遥测完备、实际努力无缺失、plant fingerprint不变，才eligible。先选2/8，只有2/8不eligible时选已预定1/9；两者均无eligible记blocked。

不按截断努力、较低峰值、平均误差或“更少动作”排序；三seed不全pass不能用成功seed过门。通过只表示这条固定短pulse可完整采集，不等于安全、充分辨识/满rank、身体模型有效、耦合改善、技能学习或未见泛化。执行原生状态改变属于探索响应，学习更新仍0；当两者都失败时保留失败，不自动创建第三候选。

source ZIP固定八份源码与协议，含collector/auditor自身、environment/probes/collect/pyproject/asset；逐份SHA及clean当前HEAD原字节在真实构造前核验。原始目录和输出排他创建，外层保存stdout、退出码与实际commit；独立audit使用事前执行提交核验Git blob，不导入collector/环境/模型。已见0/1/2属于开发，不选择新留出，不把fake环境成功称MuJoCo证据。

复现：`python -m developmental_physics.pair_calibration_development --output <新目录> --protocol docs/PAIR_CALIBRATION_DEVELOPMENT_PROTOCOL.md`；独立审计：`python scripts/audit_pair_calibration.py <原始目录> --output <新JSON> --source-commit <采集前冻结提交>`。在仓库根目录设置 `PYTHONPATH=src`，使用可选MuJoCo CPU环境。普通停止保留并继续下一fresh trial；fatal后其余blocked，禁止补跑。
