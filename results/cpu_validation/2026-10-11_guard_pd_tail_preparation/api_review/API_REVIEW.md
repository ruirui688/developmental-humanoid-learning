# G collector / planner API 有限只读审查

Root已选择完整PD反馈尾作为唯一G开发候选，正式物理尚未放行。本审查只读shared staging源码并协调collector与独立auditor，没有读取actual E/C/D/F结果、构造模型/环境、运行预测/拟合/物理或重跑任何已通过数学/AST检查。旧尾工程及其首次5个人工数学原件保持封口。

## 当前身份与接口

已读planner：`external/c4_pd_tail_mpc_staging/pd_tail_pair_mpc.py`，8210bytes，SHA256 `6d1af186eb02e033a31fcc294eedd38fa743a418a69d16744350fa02aec3beed`。
最终collector：`external/c4_pd_tail_control_runner_staging/pd_tail_control_development.py`，42400bytes，SHA256 `47407917ff7ac184ab7f0859a6fb63d30946805e3ad23cc4268d3eae4b115720`。本次读入完整原字节保存为 `runner_source_review_01.py`，身份记录为 `runner_read_record_01.json`。

Canonical路径已声明：`src/developmental_physics/pd_tail_control_development.py`、`src/developmental_physics/pd_tail_pair_mpc.py`、`scripts/audit_guard_pd_tail_control.py`、`docs/GUARD_PD_TAIL_CONTROL_DEVELOPMENT_PROTOCOL.md`。suite为`pd_tail_control_development`，collector formal=False。原件仍是external工程源码，不冒称clean生产提交或物理结果。

planner公开API为 `FixedPDTailGuardLagPairMPC(model, joint_ranges, config=None)`，构造继承原显式history MPC；`select(q,v,target_q,previous_v,*,previous_torque=(0,0))` 返回 `PDTailMPCDecision`。它继承原PairMPCDecision字段并增加 `trajectory_requested_torque`；其to_dict沿用dataclass递归转换，collector原decision.to_dict记录会保留该字段。

选中的可行trajectory中request、predicted_q、predicted_v必须等长H15；request[h]产生对应q[h]/v[h]。request[0]等于返回first torque b。fallback时三者为空，不能虚构H15 trajectory。candidate_records仍是81个原短字段：torque是h0候选b，不是整个尾的constant request。独立auditor从固定q/v/history/target、冻结模型和gain重建每candidate各stage request、cost、rejection及paid attempts，不新增all-candidate H15日志。

## 结构与spec/fingerprint契约

所有候选从同native q/v和explicit previous_v初始化，h0是原网格b；h1..14是clip(64*(current target-own predicted q)-(0,4)*own predicted v,-.5,.5)。实际只执行b，20ms后重新观察优化；没有target切换预览、未来实际状态、真实力矩或特权接触输入。history先predict再把old current v推进为previous_v，候选之间隔离。

成本常数不变，stage effort用当stage requested torque，change只b对前次实际发出的requested torque。这里previous_torque不是未来/上一段真实applied guard力矩，不能借名称混入特权或未来输入。selected tail只是假设未来反馈动作的规划结构，后续真实重规划不保证等于该tail。

已读继承fingerprint定义为`_digest(self.spec())`，因此newtail spec中的gains、history、成本说明与配置都进入planner身份；它不绑定模型系数，collector保留独立model fingerprints/snapshots/before/after字段完成模型身份绑定。planner spec明确尾gains来源是既有已选PD、0gain/model updates、no preview/futurestate、first-only执行及request字段。

formal整个MPCConfig必须原默认：H15、candidate_count9、torque .5、position1、velocity .002、effort/change .00002、local radius .15、prediction tolerance .03、target margin .03、velocity limit1.5。collector构造planner不传config；独立auditor仍应核完整默认spec，不能通过可选config偷偷改权限或同时改forecast。原study stop仍为相对qref>=.12rad或速度>=1rad/s。

## 已确认metadata与身份连接

最终source只读投影明确：`planner_variant=first_free_fixed_pd_tail`；`tail_policy`含固定64/64,0/4、h0/tail规则、first-change/stage-effort、no-preview/futurestate、first-only执行和selected-only request scope。每row保留planner_input、decision.to_dict，试验结果保留planner.spec与before/after fingerprints。newrunner从canonical newplanner导入并传给原run_trial mpc_factory；sourceZIP路径覆盖数学包、协议、asset和auditor支持链。

作者确认最终47407917版`_formal_provenance`已在load_pd_binding后硬比较kp==(64,64)、kd==(0,4)，不一致立即拒绝，随后才读archive source；入口在其返回后才load_d_models/model/env。作者已保存wire检查`tail_and_PDselected_gains_bound_before_source_archive`。本审查的定向投影没有展示该函数，我一度把该检查建议为可能缺项，收到作者说明后已向root/两代理更正；不存在因此新增源码修改或重测。该guard处以作者已保存检查和源身份佐证，不能称本次投影独立执行过该检查。

独立auditor同时核PD archived binding、metadata pd_gains、tail metadata/spec固定gains及fingerprint，防止只做metadata自洽比较。collector已通过的9个E核心AST和44个恢复检查由作者保存；本审查没有重新运行它们，不能把其通过数算作本次新增检查。

## 新尾请求计算费用

metadata上限：first-candidate evaluations 97200；PD tail vector request evaluations 1360800，均与pair/scalar model预测分开记账。

对于独立确认完整81 candidate records的已返回decision，first=81，tail=sum(max(record.pair_prediction_attempts-1,0))。这包括当前tail已算出后被predict拒绝的stage，不能只数completed_prediction_steps或选中trajectory长度。普通模型ValueError的scalar head费用未知不自动使已完整记录的pair/tail次数未知，两种计算完整性分开说明。

若planner没有完整返回decision、candidate记录缺失或异常阶段无法还原，完成decisions所推导值只是总费用下界，unknown必须公开。尤其_tail_request发生在pair_attempt++之前，其自身异常可能已有未进入pair计数的tail尝试；BaseException全局pair_planning_accounting也不记录已经开始candidate数，不能据此假称精确tail总计。正常row、exception notice、returned-unwritten复原的同次decision须按付费规划身份去重；物理失败之前已返回且保存的规划也计费用。双方已收到上述边界；独立auditor将实现派生账，不改planner数学。

## 有限结论与科学门

当前接口和new metadata能表达所选结构，没有待修API漏项。仍需root完成正式协议、生产源码/AST提升、独立auditor新增分支检查及首次clean物理放行；本审查不是这些步骤的替代，也未检查actual档案。

已选PD反馈任务能力和旧gain开发预算必须披露；cold/learned同尾，同目标/权限/支撑/停止。F关联不识因果。D sparse11旧共同pulse预测没有通过原20%门，即使G控制子门通过，也不能替换或追认旧门，完整C4仍需另冻结新预测/必要校准与控制验证。E部分tracking不用于方法排名；C4科学false、C5依赖不解除。

## 读取成本和原件范围

本次4个内容读取/静态parse/hash pass共116067bytes：planner8210、首次runner copy WIP40309、已有工程source snapshot的local_pair_model25148、最终collector42400。这是显式逻辑覆盖，不是OS实际磁盘I/O。rg --files仅枚举路径未读内容。没有统计重算、测试、模型/环境构造、predict、fit或physics。

首次WIP SHA256 `3ea1b07dcfdf6c6fdadc7d82269871f629e098f3f74c0d5c2c9520162f55e7da`，当时仍为E copy，只记中间读取成本，不能用于最终G背书；本审查未另保存其当时全字节。planner与base已有首次数学source snapshot；本次最终collector准确字节已另存。定向stdout投影选择了一部分源码，不称独立逐行检查所有函数。审查文档/record写入费用未包含内容读取覆盖字节。
