# W0 固定躯干支撑域：完整执行，任务资格失败

> 2026-10-12；首次工程资格结果。协议：[固定躯干新支撑域设计](SUPPORTED_PAIR_DOMAIN_DESIGN.md)。本结果不验收旧 free-root C4，也不解除 C5 科学依赖。

W0 从 clean `54cf4c2253f211ee71cb093aa664681fede69592` 首次完成 seed7300 的全部 100 次零请求前缀与 200 次公开 PD 控制，返回 300 个完整控制区间、3,000 个物理子步。固定前缀末 20 区间存在左前臂与 floor 的真实正法向力接触，但四项末窗位置 MAE 只有第二段左肘满足事前的 0.01 rad 门。**工程资格失败，本安装的 W1 身体辨识与 W2 控制比较关闭。**

## 1. 任务、安装与已知先验

这是独立的新机械支撑域。仅删除原身体资产的 root freejoint，把 torso 刚性固定在原 supine reset 的安装位姿；保留原八轴关节、地面、材料、0.5 Nm 力矩权限及底层保护。安装 torso 世界位置为 `(0, 0, 0.09)` m，四元数为 `(0.7071067811865476, 0, -0.7071067811865476, 0)`。不进行 settling 积分、安装搜索或试验内重装。

固定躯干移除了 6 个 root 自由度、7 个 root qpos；模型从原 15q/14v/9joint 变为 8q/8v/8joint，torso weld 从 1 变为 0。支撑承担反力，改变自由基座运动、有效惯性与接触反馈；world-welded torso/head 还可能改变有效静态碰撞过滤。它属于公开的额外机械能力，不能作为原自由躯干地面任务的匹配因果对照。

控制器沿用已开发的 PD64/Kd(0,4)，其任务能力、增益选择和旧开发费用属于先验。控制仅使用当前原生关节 q/v 与当前目标；其余六轴请求为零，没有切换预览、身体模型拟合、MPC、教师或预训练任务策略。接触、实际力矩及固定 root 位姿只保存为离线诊断。

前缀结束后，qref 只取完整 prefix99 的原生 q0/1：`(0.1722022518568856, -0.0005742568000454366)` rad。根据两侧公开限位余量选择方向 `(-1,+1)`，相等时选正向；两段目标分别为 qref 加该方向的 0.04 与 0.08 rad：

| active 区间 | 左肩目标 rad | 左肘目标 rad |
|---|---:|---:|
| 0–99 | 0.13220225185688558 | 0.039425743199954566 |
| 100–199 | 0.09220225185688559 | 0.07942574319995456 |

控制间隔 0.02 s，每个区间包含 10 个 0.002 s 子步。研究停止仍为完整区间后任一受控轴 `|q−qref|≥0.12 rad` 或 `|v|≥1 rad/s`，等号停止；环境停止和同时的研究停止分别保留。目标需满足公开限位 0.03 rad 余量，不裁剪或换方向补跑。

## 2. 事前资格与首次结果

资格先要求全部 100+200 区间完整、每区间恰好 10 个连续且有限的原生/努力/接触子步，再要求 prefix80–99 存在左上臂或左前臂与 floor 的有限正法向力接触，最后要求 active80–99 和 active180–199 的两轴 post-step 位置 MAE **全部 ≤0.01 rad**。窗口按当前目标计算 `|q_after−target|`，每轴分母固定为 20。

| 检查 | 首次保存结果 | 判定 |
|---|---|---|
| 100 prefix + 200 active，完整有限子步 | 300 返回 / 3,000 子步 | 满足 |
| prefix80–99 左臂/floor 正法向力接触 | 保存左前臂/floor 接触 | 满足 |
| active80–99 左肩 MAE | 0.014550680096836115 rad | 未满足 |
| active80–99 左肘 MAE | 0.013884623424544693 rad | 未满足 |
| active180–199 左肩 MAE | 0.03919046106253779 rad | 未满足 |
| active180–199 左肘 MAE | 0.006530098506649712 rad | 满足 |
| 完整工程资格 | `engineering_qualification_passed=false` | 失败 |

两末窗均保存全部 20 个端点，可用性为 true。run 状态为 `completed`，stop 与 failure 均为 null，300 次尝试全部返回、0 控制异常；完成采集与资格通过是两个判断。没有停止不能证明安全，也不能抵消目标误差门失败。

该结果只否定本次固定安装、公开 PD 与任务下的工程资格。它不证明所有控制器均不可达，不识别误差的接触或支撑因果原因，不证明身体学习没有作用，也不追认旧 C4。保留失败结果与全部费用，不改变本安装的高度、姿态、seed、方向、摩擦、权限、增益或门来取得通过。

## 3. 交互、计算与依赖账

| 项目 | 首次实际费用 |
|---|---:|
| 正式 control 尝试 / 返回 / 异常 | 300 / 300 / 0 |
| 确认物理子步 | 3,000 |
| 确认子步端点 forward 返回 | 3,000 |
| 正式 model build / reset | 1 / 1 |
| 正式 reset forward 尝试 / 返回 | 2 / 2 |
| RLS / fit / restoration / MPC / teacher | 全部 0 |
| 实际 `Σ|τ|dt` | 3.947884319255555 Nm·s |
| 实际 `Στ²dt` | 1.9711742072439733 Nm²·s |
| 正式内部 wall / CPU | 1.378252899972722 / 0.984375 s |
| 正式进程外层 wall | 2.536983600119129 s |

实际努力覆盖全部 3,000 子步；实际 actuator torque 与 applied command 的两种努力总值相同。内部时间不含最终序列化、压缩与写盘；未测物理文件系统 I/O 为 unknown，不记为零。source 校验记录 6 文件/72,177 读取并哈希字节，8 Git 查询/72,218 返回字节。

准备首次使用 `D:/Python3.10/python.exe` 时在 import mujoco 失败，0 constructor/reset/fixture/物理，16 payload 失败原件已保留。仅改正协议两条 CLI 与 runner 的协议 pin 后，使用已有 `external/cpu_physics_env`，没有安装依赖。attempt02 首次执行唯一无积分装配 fixture：原/新各 1 次 compile、2 次 reset forward，总计 2 models/4 forwards/0 mj_step；八轴映射及公共参数差异为空，初始几何 position/matrix 最大差为 0。恢复准备 18 payload、36 读取/212,466 bytes、0 复制失败；准备通过不能证明任务资格。

正式环境为 Windows CPU、Python3.10.11、NumPy2.2.6、MuJoCo3.15.0。正式新增 300/3,000/0 后，物理研发累计 **252,990 控制调用 / 2,529,900 子步**。历史在线 22,452 与离线重放 7,200 scalar 更新计算保持不变，合计 29,652；旧离线 ridge、规划及二维/G1 成本继续分列，没有因新域归零。

## 4. 源码与保存证据

| 冻结对象 | bytes | SHA256 |
|---|---:|---|
| `supported_environment.py` | 11,642 | `c10c72659fe5234febcaed78f04312f1913e494ce2533274b52baccf7c970cb0` |
| `validate_supported_pair_engineering.py` | 24,683 | `5c75e5db6f8721180bbbb17158f29ed736b0e10554672e585867f433b3766825` |
| `SUPPORTED_PAIR_DOMAIN_DESIGN.md` | 16,438 | `e03f158d274c510fc1fca222e5a2a75e4afc3d0264ee6e227904950f6c4423a7` |
| 实际安装 XML | 3,515 | `b0bc118158cdcdf684ebf5bc6a98bd8b4417704db8c575da8ee8449753b1b6e1` |

正式 source 的 `clean_committed_bytes_verified=true`；物理参数前后 fingerprint 都为 `0874573510959ebd9248efdb614efdccfaf069f035b4478def4064e8287b8842`。

[正式归档清单](../results/cpu_validation/2026-10-12_supported_pair_engineering/manifest.json)保存 10 payload，复制阶段 20 读取/2,359,776 bytes、0 复制失败，wall/CPU 0.11078899982385337/0 s，无自动重试。原件包括 [run](../results/cpu_validation/2026-10-12_supported_pair_engineering/raw/run.json)、[metrics](../results/cpu_validation/2026-10-12_supported_pair_engineering/raw/metrics.json)、[trace](../results/cpu_validation/2026-10-12_supported_pair_engineering/raw/trace.jsonl.gz)与[实际安装 XML](../results/cpu_validation/2026-10-12_supported_pair_engineering/raw/supported_body_installed.xml)，以及冻结来源与首次 stdio。

本报告只读取一次已有派生摘要 `external/c4_w0_reporting_summary.json`，复制保存值；本次文档工作没有读取 raw、调用模型或物理、重算 MAE 或旧科学门。派生摘要保存阶段的 5 文件/99,939 bytes、5 JSON parses、wall/CPU 0.0014812999870628119/0 s 单列，不能将这些读取或另行工程指标核对写成零计算。

首次独立输出检查确认300记录/3,000子步，0 failed checks；只重算本次4项工程MAE并验证一次新工程门，结果一致、资格仍失败，0旧科学指标/模型/物理/RLS调用。检查费用为6文件/1,181,623 bytes、303 JSON解析、10,821,204解压bytes，wall/CPU .2154672/.21875 s。静态审阅原件保留提出的schema修正及缓存语义结论，不把审阅本身写成执行。

附属 `reporting/reporting_manifest.json` 封存派生摘要、读取账、独立检查、静态审阅与首次239项零失败导航检查。只复制和核对字节，原root/raw manifest不改；24读取/290,392 bytes、11写入/145,238 bytes，wall/CPU .1367054/0 s，0科学重算或检查器重跑。

## 5. 结论与后续

本安装 W1/W2 关闭。唯一下一项是 X0 直立悬挂域设计与工程资格，须明确披露固定支撑的机械先验以及左臂可能非接触的域边界；新的安装与姿态是新任务域，不能当作本次门的修正通过。X0 先过工程资格，后续少量辨识与匹配控制仍须独立冻结、记录新费用，并最终回到完整真实接触控制。

`scientific_adoption`、`old_free_root_C4_validation`、`c4_scientific_validation` 与 `c5_scientific_dependency_released` 全部为 false。当前最早未验收仍是 C4，C5 科学适应、C6 成熟机制和 C7 新留出综合对照保持待验收；持续目标 active，阶段报告、检查、提交与推送后继续推进。
