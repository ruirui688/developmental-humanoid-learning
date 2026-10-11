# C5 工程验证冻结协议：固定肩—肘扰动、零学习

本协议在首轮真实采集前冻结。`src/developmental_physics/c5_engineering.py` 的 `DRAFT=False`，包装器为 `src/developmental_physics/perturbed_environment.py`。协议、独立审计和源哈希绑定 `docs/C5_ENGINEERING_BINDING.json` 同次提交；从该干净提交只执行一次四组工程检查。草稿与所有合成失败原件保留，clone 后运行不依赖 ignored 目录。

## 事前固定计划

只有 supine、development seed 0、reset seed **3757552657**，四个 fresh trial 顺序固定：`base_identity`、`wrapper_identity`、`gain_half`、`armature_double`。每个 trial 从新环境和资产参数开始，重置不产生积分。每个 trial 100 次零力矩前缀，然后 20 次 active；每次控制调用计划 10 个 0.002 s 子步。完整计划 480 次调用 / 4,800 子步 / **0 参数更新**。前缀、失败、普通停止和异常的实际交互全部计账；不会补跑或替换 trial。

active 的原生 j0/j1 共同请求固定为：`(+0.25,+0.25)×5 / (0,0)×5 / (-0.25,-0.25)×5 / (0,0)×5` N m，其余六轴零。没有 PD、任务目标、步态教师、奖励、预测器、RLS 或策略更新。请求来自固定时序；hidden gains/armature 不进入 actor。

在完整 prefix 后、first active 前（boundary 100）记录一次事件：base 不改变参数；wrapper_identity 设置 gains 全 1；gain_half 设置 `[0.5,0.5,1,1,1,1,1,1]`；armature_double 通过原生关节名称/关节 ID/DOF lookup 将 j0/j1 armature 从资产 0.01 改为 0.02，其余 DOF 保持原资产值。不得把变化写到错误的 DOF，也不得重置或插入等待。已持有 `data.ctrl` 在 gain 事件瞬间保持原值，缩放从下一次 request 开始。真实计划事件前 ctrl 为零，非零 held-ctrl 语义另由合成测试检验。

## 观测与资产检查

actor 只可看到原生六类观测：8 维 joint_position/joint_velocity/actuator_torque/previous_command，3 维 imu_gyro/imu_acceleration；全部有限数值。不额外提供 hidden 参数、接触或质量矩阵。previous_command 维持公开 clip 后请求，actual force 单独记录。八个原生关节必须按名称 lookup 映射到 qpos 和 DOF，不能假定 ID 顺序。预审 motor stateless fixed unit gain、unit gear、zero bias、native joint transmission、0.5 N m 公共动作限幅与 .002/10 控制时序，native asset armature 全 .01。

## 每子步仪器与独立力矩核验

用局部 `try/finally` 临时替换原环境使用的 module.mj_step。每个原子步只读 pre 原生角度与 `data.ctrl`，调用**一次原 mj_step**，正常返回后读取 `data.actuator_force`。hook 不增加 mj_forward/mj_step，并在任何异常/停止后恢复原 module API。用 pre 角度及公开 joint range 的 ±.03 重新计算限位 guard；比较 `(公开接受请求 × hidden gain) × guard` 与 actual ctrl，再核对 unchanged unit motor force。容差 1e-12。guard 是环境的公开保护，不是学习结果。

hook 正常收到原 kernel 返回时立即记录 independently_returned；即使随后 force 读取失败、环境尚未 increment counter，该子步仍计入 known paid 下界。每次调用 paid 子步取 `max(environment counter delta, independently returned kernel delta)`。原 kernel 未返回时记录 unknown original attempt；真实额外积分未知，不能写为零积分，actual history 和成本明确为下界。若 setup/reset 自身异常后发现已增加环境计数，保留其已知成本。

## 边界诊断

事件 before/after 保存 qpos/qvel/time/counters/last_command/**data.ctrl**/完整 armature/base 与 plant fingerprints。上述 persistent 状态不得变化。gain 只改变完整 plant fingerprint，不改变 base fingerprint。armature 调用原包装器的非积分 live mj_forward，因此派生 force/sensor 可变化，但 q/v/ctrl/time/counters/previous command 不变；事件后重新读取原生 observation，不插入额外 live forward。

在同一个 live q 上，分别新建 scratch MjData、复制 qpos/qvel/ctrl、调用非积分 mj_forward 与 mj_fullM，记录完整广义质量矩阵。scratch 不触碰 live 状态/观测，不是 actor 输入，0 交互。armature_double 的两个 native lookup DOF 对角线应各 +.01，其他矩阵元素变化在 1e-12 内；其他三组矩阵不变。诊断失败为 fatal；这仅验证动力学事件生效，不代表适应或学习。

本机 MuJoCo 3.15.0 的已安装声明采用 `mj_fullM(model, data, dst)`，adapter 使用该签名；没有自动回退/重试。首次合成测试只验证 stub，静态 API 复核发现旧签名不适用后保留原测试 attempt，并另建修复 attempt。依赖不兼容必须显式失败，不补跑。

## 停止、异常与工件

active StudyAbort：任一 j0/j1 `abs(q-qref) >= .12 rad` 或 `abs(v) >= 1 rad/s`；qref 是完整 prefix 结束的 native q。prefix 不启用 StudyAbort，只用原环境保护。普通 StudyAbort/environment stop 终止本 trial，下一 fresh trial继续；任何异常（资产、事件、原 kernel、仪器、有限观测、日志/工件等）为 fatal，后续 planned trial 标 blocked，0 请求，禁止补跑。环境原停止规则不修改。

每次控制调用写 native before/after、qpos/qvel、diagnostics、actual substep history 与两个停止条件；异常写 failed request、last before observation、partial records、best-effort live state 与 parameter-event 原件。写盘异常停止后续采集；尽可能保存其他文件，并在 stdout 打印已付费事实。磁盘全失效无法保证原件落盘，因此外层 execution wrapper 独立捕获 stdout/exit/预算。文件和输出目录排他创建，不覆盖旧 attempt。

完整 base/wrapper identity 要求各 120 行原生观测、state 和 actual history 逐字节一致，或每数值叶绝对差 ≤1e-12；短共同前缀匹配不能称完整 identity 通过。完整每trial 120 calls/120 endpoints/1,200 known returned 子步且 unknown=0。努力量记录请求与实际力矩绝对/平方积分，缺 force 或 unknown kernel attempt 时注明下界。metadata 保存 dependency versions、CPU wall/process time、source snapshot/hash、计划、0 update、实际预算、事件、停止/异常、blocked 与 identity。

## 正式来源绑定与运行入口

real 入口只有 DRAFT=False 才可能继续。必须 clean 当前 HEAD，tracked binding 实际 bytes 等于 HEAD blob；binding schema=1/draft=false/plan 精确等于事前计划。fixed 七个 minimal source 路径（runner、wrapper、environment、package init、asset、protocol、`scripts/audit_c5_engineering.py`）实际 bytes 同时等于 HEAD blob 和声明 SHA256；runner 自身必须在清单，protocol 路径与 hash 固定。binding 不包含自己的期望 hash，也不硬写自己的 commit；runtime clean HEAD 与实际 binding hash写入 metadata。源码 ZIP 包含七 source 与 binding原字节。合成 fixture只 stub Git，不能给 real 绕过 freeze。独立 audit 由 root 提供，在冻结前缺失时 real 不得运行；audit 不导入 runner/wrapper，另行重算 guard/force/质量矩阵/identity/成本。

正式 CLI 为 `python -m developmental_physics.c5_engineering --project-root <clone-root> --output <new-directory>`，包通过 `PYTHONPATH=src` 或安装访问。RealBackend 在 freeze 检验之后才 lazy import MuJoCo/NumPy/两个环境类，fresh factory只构造声明四组；草稿 main 不能启动真实 factory。CLI 只有四组完整且完整 identity 通过、无 fatal 才返回 0；普通停止仍保留并继续其他 fresh trial，最终以非零状态明确本轮未完整验收。

工程验证不检验算法优越性、少量学习、能力晋级、全身技能或真机安全。科学扰动/在线辨识对照需在工程结果复核后另行事前冻结；本次固定计划不因结果更换参数。
