# G 固定 PD 尾段 collector 交付

实现已完成，仅用于 root 提升与冻结；当前 `FORMAL_CONTROL_ENABLED = False`。
没有执行正式采集、真实数据读取、D 模型预检、模型构造、模型预测、参数更新或物理查询。

## 源码与 API

- 最终文件：`pd_tail_control_development.py`，42400 binary bytes，SHA256
  `47407917ff7ac184ab7f0859a6fb63d30946805e3ad23cc4268d3eae4b115720`。
- canonical：`src/developmental_physics/pd_tail_control_development.py`。
- entry：`run_pd_tail_control_development(output, *, protocol_path=None)`。
- suite：`pd_tail_control_development`。
- 协议：`docs/GUARD_PD_TAIL_CONTROL_DEVELOPMENT_PROTOCOL.md`，由 root 冻结。
- 独立审计：`scripts/audit_guard_pd_tail_control.py`，由 `coupled_audit` 实现。
- planner canonical：`src/developmental_physics/pd_tail_pair_mpc.py`，class
  `FixedPDTailGuardLagPairMPC`；当前 staging 原件 SHA256
  `6d1af186eb02e033a31fcc294eedd38fa743a418a69d16744350fa02aec3beed`。

collector 复制当前 E 源码，原件为 `guard_lag_control_development.original.py`，
SHA256 `3ea1b07dcfdf6c6fdadc7d82269871f629e098f3f74c0d5c2c9520162f55e7da`。
只改新入口/绑定、固定尾段 metadata、planner import/factory、PD 增益绑定校核
与必需的源码归档检查。`run_trial`、`restore_lag_snapshot`、`load_d_models`、
`native_history`、`bind_prefix` 及其余四个核心函数 AST 保持 E 原件不变。

两个 MPC 组使用原默认 H15/81 候选/config，不传配置调优参数。h0 是原候选 b；
h1..14 使用每个候选自己的 predicted q/v 与当前 target，固定
Kp=(64,64)、Kd=(0,4)、clip ±0.5 Nm。实际只执行 h0，下一个 20 ms 重新观察与规划。
原目标、forecast 界限、study stop、权限、原生 history 和支付/异常分支均保留。
选中轨迹的 `trajectory_requested_torque` 通过原 `decision.to_dict()` 自动保存。
全候选 requests 由独立 auditor 重建，不新增全轨迹日志。

cold11/learned_sparse11/PDselected/zero、seed 0/1/2、新鲜 100 prefix+200 active
与原 D sparse11 恢复契约保持相同。模型、策略、增益、门控更新均为零；原 D
snapshot 创建和旧 PD 增益开发已有非零费用，不在新运行中重新归零或重新选择。
原 D 预测 20% 失败保持不变；G 为开发对照，C4/C5 科学状态仍为 false。

## Metadata 与 source ZIP

metadata 保留原字段，并新增 `planner_variant`、`tail_policy` 和尾请求费用说明。
`tail_policy` 明确固定增益、h0/tail 规则、当前 target、无未来实际状态、只执行 h0、
stage request effort 和仅第一 b 对 previous actual request 的 change cost。
`_formal_provenance` 在 PD binding 读取后明确校核 Kp/Kd 与固定尾段完全一致。

新 `SOURCE_PATH`、`MPC_SOURCE_PATH`、`MPC_BASE_SOURCE_PATH`、`AUDITOR_PATH`、
`PROTOCOL_PATH` 必须全部进入 clean HEAD 的逐字节核查与 source ZIP。
physics 包完整源码 glob 保留；原 E auditor 与其五个既有支持加入 G 支持清单。
因此 new collector/planner/auditor/frozen protocol，以及原 MPC/helper/model/math/loader
依赖均有来源绑定。原 D/PD 输入的冻结 hash、完整 snapshot 与复位核查保持 E 方式。

规划 pair/scalar 预测与 PD 尾请求计算分开记账：

- `maximum_tail_request_vector_evaluations = 1360800`；
- `maximum_first_request_candidate_evaluations = 97200`；
- `tail_request_accounting` 声明：每个完整 decision 在确认 81 个 candidate records
  完整覆盖后，first=81，tail=Σmax(pair_prediction_attempts−1,0)，包括被拒绝的 stage；
- 无完整 decision 的 planner 异常保留未知工作与已保存完整 decisions 的下界；
  `_tail_request` 可在下一次 prediction attempt 前失败，不能只看预测数或 selected
  trajectory 长度而声称尾计算完整。

独立 auditor 从已保存的 regular/唯一 exception decisions 去重后输出 actual
`paid_tail_request_accounting`，与其自身重建成本分开。collector 没有虚构 actual 零值。

## 必要检查与保留失败

`engineering_01/run.json` 保留首次检查器失败：tuple 形式的
`PREFIX_STEPS, CONTROL_STEPS = ...` 不在只索引 Name 的字典中，出现 `KeyError`。
当时 18 项已通过，检查器失败没有导致生产代码更改。

`engineering_02/run.json` 完成必要剩余检查：**44 passed / 0 failed**，其中 18 项
引用第一次原件的通过结果，26 项为新检查。通过完整 AST 的 metadata-only bridge
核定第一次源快照与最终源之间只有新增尾请求费用说明，再复用已通过项；没有
重跑旧 E fixture 或已通过的尾段 5 项数学检查。

检查只解析源码，不导入模型/仿真代码。唯一动态调用是从 AST 提取 G entry，令
formal=False，确认在 Path、来源读取、模型与物理入口前立即退出；没有创建采集输出。
每次检查的输入原件另存 `engineering_*/source_snapshot/`，失败没有覆盖。

## 本开发交付的费用

以下为保存/检查器显式应用层读取，不含解释器或标准库内部读取：

| 操作 | opens | binary bytes | hashes | AST parses |
| --- | ---: | ---: | ---: | ---: |
| 当前 E code 原件保存 | 1 | 40309 | 1 | 0 |
| 首次失败 wire checker 的源码读取 | 5 | 123833 | 5 | 5 |
| 必要检查器恢复的源码读取 | 1 | 12141 | 1 | 0 |
| 恢复检查 source 读取 | 6 | 166233 | 6 | 6 |
| 恢复检查读取首轮 checkpoint 记录 | 1 | 2788 | 1 | 0 |
| 小计 | **14** | **345304** | **14** | **11** |

首检查 wall/CPU 为 0.04574389988556504/0.03125 s；恢复检查为
0.1389109999872744/0.109375 s。动态 disabled entry 调用 1 次、预期退出 1 次；
模型导入/构造/预测、RLS、参数更新、物理、真实 E/C/D/F 读取、旧 fixture 重跑、
Git 均为 0。普通 AST/复制/哈希/分类检查计算不是零计算。

协调阶段另有 4 次完整源码文本读取（129137 binary bytes）与 3 次截取源码/README
文本读取；后者 shell 内部实际 binary bytes 没有仪表，不能声称精确为零或加入
精确总计。目录与文件名搜索未读取真实实验 payload。首次目录搜索使用了不存在
的 staging 路径，返回路径不存在；随后按实际文件名继续，不构成模型或采集失败。

新完整性清单生成的实际文件读取/hash 单列在 `INTEGRITY.json`，不混入上述小计。
本子代理没有 tracked 修改、Git 操作或物理放行。正式运行仍由 root 在协议、
审计、canonical 字节与 clean commit 完整冻结后决定。
