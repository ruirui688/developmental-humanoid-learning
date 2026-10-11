# C4-A：左肘经典控制开发的冻结协议

2026-10-11；在新增左肘真实试验前固定。实现、独立审计及关键合成检查完成并提交推送后，从干净源码一次执行。该阶段只选择有上限的经典控制基线，不更新身体模型或任务策略。

## 固定选择与任务

第二关节固定为 supine / j1 left_elbow。选择只来自已公开 development0/1/2 探针：按原执行器索引升序排除已使用 j0，j1 是首个在 .5 N·m 三开发 seed 均通过原响应门的关节。后续失败不能换关节；肩部 PD64/0 不能称为肘部调优基线。

沿用原 MuJoCo CPU 身体、baseline 接触、理想原生感觉、2 ms 子步、每调用10子步和全部环境保护。目标关节请求上限 .5 N·m，另外七关节恒零。公共身体信息、PD 形式、任务目标、零请求前缀和安全保护均是共享先验，不是从随机策略获得的全身技能。

每 trial 独立 reset；原 `SeedSequence(seed).spawn(2)[0].generate_state(1)[0]` 派生规则。每 trial 自己付费执行100步零请求前缀，从其末端 encoder q 与公共限位一次确定 qref 和方向 s。保持原生 qref，即使肘在柔性限位下略小于0也不裁剪、不缓存历史值。随后200步控制：active0–99 目标 qref+s*.04，active100–199 为 qref+s*.08；只传当前目标，无切换预告。目标必须在公共限位 .03 rad 内缩内，不可行则失败且不裁目标。

PD 原式 `raw=Kp*(target-q)-Kd*v`，请求 `clip(raw,-.5,.5)`；只读当前 encoder q/v 和当前任务目标，没有模型输入、实际未来力矩、接触或仿真特权参数。原生 velocity damping 和公共限位方向规则不更改。

## 候选、顺序与选择门

固定开发 seed `[0,1,2]`，seed 外层、Kp `[4,16,64]` 中层、Kd `[0,.2,1]` 内层，共九组/27 trial。不得追加网格、按 seed 调参、先看 trial 再改执行顺序或补跑到成功。20/21/22 已在单肩最终评价使用；本开发不读取这些轨迹。后续左肘正式评价另冻结新留出。

每候选三个 seed 全部300完整调用/3,000子步、100 prefix/200控制完整20ms转移、无 study/env stop、异常、非法请求或非有限状态才 eligible。完整末计划转移触发停止也不 eligible。全部候选保留，截断后较低RMSE不能参与排序。

eligible 候选按三个 seed **原始 tracking RMSE 算术均值**由小到大；精确相等依次按控制 active **请求平方努力均值**、Kp、Kd、candidate index 排序。不取整后判并列，不使用实际努力替代冻结决胜。无 eligible 候选记录选择失败，不假定已有强基线。该选择为离线经典控制开发，在线增益更新0。

## 研究停止、部分转移与故障

所有 active 返回端点检查 `abs(q-qref)>=.12` 或 `abs(v)>=1`，等值触发，只停止，无纠正动作。prefix 只有原环境保护。StudyAbort 与环境停止各自保存：`study_abort`、`environment_terminated`、`environment_stop_reason`；共同发生时环境原因可作主 reason，但不丢研究停止。不能更改环境 flag 或抛伪造异常表示正常研究停止。

完整20ms terminal转移可进 tracking；partial 保存已返回原生状态、当前已知 target 的原始误差、付费子步和真实努力，不进主20ms tracking RMSE。评分数、计划数、缺失数和停终状态分开。停止原因和缺失主指标不允许填零。

普通停止/非fatal试验失败继续剩余候选；中断、IO或 trace 写入失败 fatal，剩余 planned 记 blocked，不补跑。所有 `env.step` 尝试/返回/实际付费子步、已返回未存行及失败快照分别记录；努力在 finally 按实际执行子步计。实际力矩只能取已返回历史；缺失遥测保留下界、未知量和缺失子步，不补零。底层保护与原源码不修改。

## 预算、风险与独立核验

完整计划27 trial / **8,100控制调用 /81,000子步 /162 s模拟时间**；prefix2,700/27,000，control5,400/54,000。身体/策略/教师/演示更新均0。所有九候选、失败、前缀及停止前动作计入经典开发成本；之后所选基线的共同评价成本另列。模拟时间、CPU墙钟和现实动物学习时间不能混写。

每 trial 保存完整 q/v、原生链、raw/clipped PD、目标、方向、请求/实际绝对及平方努力、全部子步接触峰/冲量、动能、穿透、八关节速度、软限位/屏蔽、饱和、研究/环境停止。full/prefix/control 分开，不以active低风险遮盖前缀。零停止或日志一致性不证明安全，不预设风险改善门。

标准库独立审计不导入模拟器或控制器实现，按 j1 真实档案重算：协议/源码ZIP及原字节SHA/Git来源、所有prefix配对、派生seed、方向/限位/目标、PD命令、20ms/partial评分、端点研究停止、努力、phase/trial/batch成本、风险、失败完整性与上述选择。不能重排观测伪装肩关节档案，不能直接用旧j0审计的硬编码口径。

采集入口：`developmental_physics.elbow_feedback_validate`；独立审计：`scripts/audit_elbow_feedback.py`。CLI只接受 output/protocol，关节、seed、网格固定。正式运行前至少检查负qref合法目标、停止但env flag仍false、partial排除且计成本、末步停止不完整、写盘fatal及剩余blocked、无完整候选/精确排序；只用合成数据。

正式物理累计基点 **208,850控制 /2,088,500子步 /9,900 RLS**；本批若完整为216,950/2,169,500/9,900。按实际而非计划累加。测试、规划、离线排序及独立审计计算另报。

## 连续执行

先冻结并推送，从clean一次采集、一次首次审计，完整归档全部候选/失败和选择，再检查提交推送。随后迁移固定 short/old/hinge5/Euler 至左肘，不复用肩theta/P；然后固定肩—肘模型协调实验，继续未知动力学与成熟门控。此经典基线阶段不结束[持续目标](CONTINUOUS_EXECUTION_PLAN.md)。相关：[单肩最终协议](LOCAL_FROZEN_VALIDATION_PROTOCOL.md)、[肩部经典开发](CLASSICAL_PD_DEVELOPMENT_RESULTS.md)、[逐关节选择](JOINT_PROBE_PROTOCOL.md)。
