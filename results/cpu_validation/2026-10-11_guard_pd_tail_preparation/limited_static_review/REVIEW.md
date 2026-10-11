# G 独立审计器有限静态审查

结论：**本次有限范围内没有新的阻塞项**。当前草稿源码与协议对齐，正式状态
关闭。本审查不能证明物理执行、数值复现或控制门通过，也不放行正式采样。

## 原件与范围

仅读取以下两份原件，并保存在本目录：

| 原件 | SHA256 | bytes |
| --- | --- | ---: |
| `audit_guard_pd_tail_control.original.py` | `38322b00e04782a640f989ddc568d06e27c6fc8e5e18b68bfe0f9807cf38483a` | 76376 |
| `G_PROTOCOL_DRAFT.original.md` | `e69d1453d3d70a37e9685f593f7ff6da182fbd3bb471b145a3c4d475e8a56167` | 7039 |

来源分别为 `external/c4_pd_tail_control_audit_staging/audit_guard_pd_tail_control.py`
与 `external/c4_pd_tail_protocol_staging/G_PROTOCOL_DRAFT.md`。

审查限定为新 PD 尾规则、显式 history、selected requested trajectory、actual
tail 请求计费、来源与科学边界。既有 E 物理主体、D 恢复、原来源 API 与已通过
的 wire/tail 数学不再复查。runner/planner 契约引用已封存的
`47407917ff7ac184ab7f0859a6fb63d30946805e3ad23cc4268d3eae4b115720` 与
`6d1af186eb02e033a31fcc294eedd38fa743a418a69d16744350fa02aec3beed`，
本次没有重新读取它们。作者报告的新 27 项检查已通过；本审查没有读取或
执行该 fixture，因此不把作者的检查数算作审查自身验证数。

## 确认内容

1. `candidate_math` 的 stage 1 对应 h0，使用原网格 b；其余 stage 调用
   固定 `tail_requested`，仅依该候选自身预测 q/v 与当前 target，Kp=(64,64)、
   Kd=(0,4)，clip ±0.5。只 first b 对 previous request 计 change cost，
   每 stage effort 使用该 stage request。候选独立复制 q/v/previous_v，先预测
   再将 previous_v 更新为旧 current_v；没有目标切换预览或未来真实反馈。
2. `validate` 保留原 forecast 半径 .15、public range ±.03、速度 1.5 与
   target margin .03；metadata 仍约束实际 study stop .12/1.0、原权限、
   100 prefix+200 active 和十二组矩阵。本轮没有同时修改这些条件。
3. `native_history` 只从同 trial 的两个连续、完整、未终止原生 endpoint
   构造历史，active0 使用 prefix98/99。`decision_at` 用原生 q/v/previous_v、
   当前 target 和 previous request 重建，保存输入须逐字段一致。
4. `candidate_math` 记录与 q/v 同 stage 的 requested trajectory；
   `choose_feasible` 同时选出请求轨迹，fallback 的三个轨迹均空。
   `decision_at` 比较完整重建 decision，因此会核 selected
   `trajectory_requested_torque`，并核实际第一请求等于选中的 b。
   全候选 requests 由 auditor 重建，没有要求在线保存全 H15 请求日志。
5. `paid_tail_requests` 将 regular 与唯一 exception decision 去重，
   先核 81 个原顺序候选和每候选合法 pair attempts，再将 first+=81、
   tail+=Σmax(attempts−1,0)。被拒绝预测 stage 的 tail 请求仍计费。
   该账不依赖 scalar_counts_complete，因此未知 scalar 工作不会被混写
   成已知 tail 零计算。无完整 decision 或非法候选覆盖记 unknown/lower_bound；
   `_tail_request` 可在 prediction attempt 增加前失败的情形明确披露。
6. actual paid tail 账与 `COUNTS['tail_request_reconstructions']` 等审计重建
   工作分开。逐 trial 返回已知 first/tail、完整性与未知 failed calls，batch
   聚合并核 97200/1360800 上限；不是用 selected 轨迹长度代替实际计算。
7. `required_sources` 明确包含新 collector/planner/auditor/protocol、原 base
   MPC、原 E audit 和既有支持、D/PD 来源。ZIP、metadata 哈希、执行审计器
   字节、支持字节与 clean commit 分别绑定；来源检查不调用在线模型/fit。
8. `verify_tail_metadata` 核固定增益、tail 规则、计费说明完整字典。
   开发控制与 PD 门保持完整执行优先与原逐 seed 聚合；
   `c4_scientific_validation` 明确 evaluated=false/passed=false，保留 D
   原 20% 预测门失败，不以 G 控制开发收益解除 C5 依赖。

## 正式冻结时的状态契约

当前 `FORMAL_AUDIT_ENABLED=False`，planner 的
`FORMAL_PD_TAIL_CONTROL_ENABLED=False`，collector 的正式状态也为 false。
审计 `planner_spec` 的 `formal_experiment_enabled` 取 audit flag，而实际
planner spec 取自己的 helper flag。正式提升时 root 必须统一这些状态，
否则 spec/fingerprint 审计会不一致。这是冻结条件提醒，不是当前草稿缺项；
已直接告知作者与 root，不请求重跑数学或修改核心。

## 审查费用与限制

第一次读取 audit/protocol 原件：2 opens / 83415 binary bytes；3 hashes
（audit 首先核预先给出的 SHA，再给两份原件分别记录 SHA）；1 次 audit AST
解析仅用于函数/行号目录，没有执行源码。

从已保存的 audit 原件投影必要函数：1 cache open / 76376 bytes。首次工具
输出截断了部分 actor/计账内容，随后仅补显示缺失内容：额外 1 cache open /
76376 bytes。两次投影都没有 hash、AST 解析、源码执行或数学复跑，源码未改。
对应原记录为 `PROJECTION_RECORD.json` 和 `PROJECTION_RECOVERY_RECORD.json`。

新清单生成前合计 **4 explicit opens / 236167 binary bytes / 3 hashes /
1 AST parse**。原件读取 wall/CPU 为 0.014420700026676059/0.015625 s，
首次投影为 0.014195600058883429/0 s；恢复投影没有声明独立 wall/CPU 测量。
完整性清单生成读取/hash 另列在 `INTEGRITY.json`；解释器内部读取不在显式
应用层记录内。

本次模型导入/调用、数学或 fixture 复跑、物理查询、实际 E/C/D/F 数据读取、
参数更新、Git 操作、tracked 修改全部为 **0**。没有读取实际输出或预检模型，
没有对 G 的控制、收益、风险或科学门作结果判断。
