# C4-A 左肘 PD 开发：最小复用技术方案

2026-10-11；ignored 设计稿，不是冻结协议。没有新物理、真实标签拟合、留出读取或 tracked 改动。C4 pair 核心已停止编辑，仅按 root 授权完成失败 ledger 的定向修补。

## 固定任务与预算建议

supine / joint1 left_elbow / development0/1/2，Kp外层 `[4,16,64]` × Kd内层 `[0,.2,1]`，固定九组。每 trial 独立 reset、100步真实零请求前缀、200步控制；当前目标前100为 `qref+s*.04`、后100为 `qref+s*.08`，没有切换预告。qref取自己付费前缀，保留肘部轻微负角，不裁到0；公开限位方向及.03 rad目标内缩沿用原规则。其余七关节请求0，目标关节每轴.5 N·m权限。

完整计划27 trial / 8,100调用 /81,000子步；prefix2,700/27,000，control5,400/54,000，162 s模拟时间。身体、策略、教师和演示更新均0。所有九候选、失败、前缀及停止前成本计入控制器开发，不能只计被选中的一次。

## 为什么不直接包装旧 run_feedback

`src/developmental_physics/feedback_validate.py` 的 PD公式、付费前缀、目标和请求平方努力符合本任务，可直接复用其 `pd_request`。但旧 collector 没有研究停止钩子：仅从 `result.terminated` 跳出，episode status又从 `env.terminated`决定；直接复用无法独立记录StudyAbort。其完整性只检查300控制步，未区分300个完整20 ms转移与部分保护间隔；tracking也把每个返回partial端点计进主RMSE。

因此不应让代理环境篡改 `env.terminated` / `result.terminated`，也不应在 step 返回后抛伪造异常来表示正常研究停止：后者会使完整terminal转移落到旧异常行，混乱遥测、主指标与完整性口径。事后只修summary也不能补回未被停止的物理动作。

旧 `scripts/audit_feedback_development.py` 的 `_consume` / `audit` 硬编码j0、旧协议、无StudyAbort，且同样将partial控制端点计进tracking。不能仅把metadata中的joint改1再调用旧审计，更不能重排原始观测去伪装j0。旧 collector、旧 auditor、历史源码与档案原字节都应保留。

## 最小实现建议

建议新建一个受限 PD-only collector，约220–300行的任务专用执行器。它不是复制整个学习/MPC runner；只借用已审核C2-C的实际成本/日志故障处理和独立研究停止口径。复用以下已有原语，不改其源码：

- `feedback_validate.pd_request`：原生q/v、当前target、固定候选增益产生clipped请求和raw PD输出；不输入身体模型。
- `probes.direction_record`、`GroundBodyEnv`、`ExplorationConfig`：原公开方向、身体、接触、2 ms保护与20 ms调用。
- `collect._archive_record/_exception_snapshot/_write_json/_hash`：异常快照、有效JSON、checkpoint及原字节归档。
- `local_coverage_ablation.native_study_abort`：active返回端点原生 `abs(q-qref)>=.12` 或 `abs(v)>=1`，prefix不施加新阈值。

CLI仅 `--output/--protocol`，pose/joint/seeds/gains/grid顺序固定在新文件常量。API不接受20–22、任意joint或任意gain。实现前root另冻结正式C4-A经典开发协议和独立审计口径；本稿不启动采集。

每个trial流程仍为prefix→当前目标PD→一次env.step→检查原生StudyAbort→保存原始行→退出/继续。研究停止不产生纠正动作，不改环境保护或环境flag；同时保存 `study_abort`、`environment_terminated`、`environment_stop_reason`。环境原因优先作episode主reason，但独立study flag不得丢。普通失败继续剩余候选；中断、IO或任何日志写失败fatal，剩余planned标blocked，不补跑。

所有请求绝对/平方努力在step的finally按实际付费子步计算，prefix/control单列。实际努力只能取已返回的 `(executed_substeps,8)` 力矩历史；缺失历史记录已观测/缺失子步及下界，不补零。完整20 ms terminal转移可进主RMSE；partial原生状态、已知target误差及真实努力单列，不能当作完整tracking。即使第300计划步触发StudyAbort，也status=terminated、complete=false。

完整性建议同时要求300完整调用/3,000子步、100prefix/200控制主指标、无study/env stop、异常、非法请求或非有限状态。没有RLS或模型参数对象，增益始终固定；gain选择是离线开发，不能称在线学习。

## 新独立标准库审计 adapter

可直接复用旧审计的标准库工具 `Checks/near/finite_tree/vector/count/canonical/rmse` 以及未改的 `select_candidates`。source ZIP/Git/manifest的结构核验可沿用同一算法，但显式传入新协议、collector和upstream依赖清单，不通过篡改原始档案达成复用。

新adapter必须自己按j1重算：公开限位方向、两个当前目标、raw/clipped PD、真实子步请求/实际努力、原生链、active StudyAbort触发的值/phase/index、独立env原因、完整/partial tracking、全部phase/trial/batch预算与失败暴露。full/prefix/control的八关节速度、限位/屏蔽、子步接触峰/冲量、动能和接触深度都保留。

优先新增薄的 `_consume_elbow` 与trial完整性检查，复用原选择函数；不修改旧j0 auditor。若薄adapter为了更换元数据而仍需拷贝整个审计循环，可建立独立受限新脚本，仍共享上述无条件原语，不能用转换后的虚拟档案冒充真实日志。

选择输入的 `eligible` 必须来自新审计逐端点重算，不能只信collector flag。每候选三个seed全部完整才能排序；使用三个原始tracking RMSE的算术均值，精确并列按**请求**平方努力均值、Kp、Kd、candidate。不是实际平方努力，也不先对RMSE取整。任何seed研究停止的候选即使截断RMSE最低也不参与；无完整候选记录选择失败。零停止不是安全验证。

## 当前可做的少量合成验证

本目录的 `selection_probe.py` 只读取旧审计源代码，执行其 `select_candidates` 的四个纯标准库假记录用例：研究停止候选排除、请求平方努力及增益精确决胜、原始均值的微小差异优先、全不完整时选择失败。它不验证新StudyAbort重算，没有原生轨迹或正式档案，不是C4-A验收。

后续新collector需要有限关键合成测试：j1负qref与合法目标、active端点研究停止且env flag仍false、partial主指标排除/原始误差/成本、最后计划步停止不完整、IO/trace故障fatal及剩余blocked。新auditor再用完整/停止/partial/异常小假档案验证字段与选择，不运行真实物理或留出。

root审查本方案后，再选择是否实现受限collector及adapter；目前无需生成600行学习runner，也不能从C3肩上64/0直接认定肘的强基线已经调好。
