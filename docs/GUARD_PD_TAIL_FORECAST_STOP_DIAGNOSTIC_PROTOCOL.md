# C4 H：固定保存 forecast 与停止界限诊断

本项只描述 G 已保存数据，先冻结脚本与本协议，再从干净提交执行一次。
G 是已见开发证据；H 不构成新留出、控制试验或科学采用。正式开关在准备阶段为 False。

## 固定问题与来源

G 的 selected H15 容许 .15 rad / 1.5 rad/s，原真实 study stop 为 .12 rad / 1 rad/s。
检查已保存决策在 first stage 与后续 tail 是否跨入真实停止界限，并与末 20 步的
原独立一步、selected stage0 预测误差并列描述。结果不预先支持收紧 forecast 或追加特征。

只读取此次 G 的五个文件：raw/manifest.json、raw/metadata.json、
raw/seed_results.json、raw/trace.jsonl.gz、first_audit.json。默认公开目录为
`results/cpu_validation/2026-10-11_guard_pd_tail_control`。
物理 source commit 为 `91dcf6c111a87427c8f3fdd8b959d4792b1bb5a2`；
raw manifest SHA256 为 `7eff4abb7cbe9c42a66d59615939a63a491c56fe87b5271d4ff4836d7b220a4c`；
first audit SHA256 为 `ad98a41ea342808521945fac998a864eff9709d1593fbb3c3c459ce2d48d60bc`。
G 数据首次公开归档提交为 e8c6c04，不要求它们已存在于物理 source commit。
本脚本来源另绑定执行时实际冻结 HEAD、干净状态及脚本/协议 committed bytes。
manifest 绑定三个 payload 的原字节；first audit 要求 failed=0、原 source 和读取 payload hash 一致。
只复制原 G final gates 与预算，不重算它们，不重读 sourceZIP、旧批次或审计。

## 固定统计契约

固定 seed0/1/2 × cold11/learned_sparse11 六 trial，所有实际保存 active 记录。
active<100 为 A，其他为 B，预先建立全部十二组；空组明确 empty_target_segment。
只消费 selected decision，不读取、重构或重放 candidate_records。

valid selected 必须 fallback=False、feasible_candidates>0，q/v/request 三条
轨迹均为有限 15×2。stage0 单独，tail 为 stage1…14；逐轴判断
`abs(q-qref)>=.12` 与 `abs(v)>=1`，qref 仅取本 trial fresh prefix 的原生 reference_q。
保存各 violation stage、first violation stage、max，以及每组 stage/decision 分母、
q/v/任一越界计数。无有效 forecast 的 max=null，fallback/missing/invalid 独立计数，
不当作预测安全；没有 selected trajectory 时绝不补预测。

每 trial 固定最后 min(20,实际保存 active 数)，短 trial 全取，零记录显式空原因。
原 `predicted_next_qv[kind]` 是当前实际请求的独立一步；原 selected q/v[0] 是
有效选中 H15 的 stage0，两者分别披露，不把 fallback 的独立预测补成 selected。
实际端点只取原生 joint_position/velocity。误差符号为 actual-prediction，另存绝对值；
保存原请求与实际 applied_torque_history 的逐轴 absolute/squared effort×原 .002s。
10 子步才是完整 20ms 主误差端点；partial 保留预测/实际、执行子步和付费 effort，
主误差为 null，并给出原因。缺失 effort 为 unknown，不当零。
完整与停止 trial 使用同规则，partial 不排名，不补样、延长窗口或改任务/停止门。

不计算 Pearson、筛选特征、拟合/调用模型、候选重构、更新、物理或重审计。
JSON 解析虽包含原完整 trace，特权 qpos/qvel/root/contact 等字段不被消费；
输入只为来源身份、原生端点、已保存 selected/独立预测、请求与实际 effort。
scientific_adoption 永远 false，原 C4/C5 科学门保持原值。

## 输出、费用与首次执行

标准库脚本 `scripts/diagnose_guard_pd_tail_forecast_stop.py` 输出：
description.json（固定组/原门/预算）、intervals.jsonl（所有 active 的越界描述）、
last20.jsonl（固定末 20）、run.json（来源/计算/失败）、manifest.json（输出原字节封口）。
输出目录 exclusive，不覆盖失败或先前结果；失败保留已经读取来源和费用。
计账输入读取/原字节/hash字节、JSON 文档/trace 行/解压字节、描述 active 数、
自身 source 读取/Git queries/wall/CPU；模型预测、更新、物理全部 0，不称 0 计算。

准备只核计数、空段、partial 和来源/信息隔离的必要小分支，不建大 fixture，
不读实际 G。正常提升并提交推送后，从 clean H HEAD 只执行一次正式诊断。
描述结果与原件提交推送后继续有依据的最小修订；H 不结束持续目标。
