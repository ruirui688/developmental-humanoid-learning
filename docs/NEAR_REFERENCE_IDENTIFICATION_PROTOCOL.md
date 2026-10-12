# IV3：近qref的原生状态辨识

状态：**事前有限协议，尚未执行。** 仅开放一次新原生辨识及已见开发人口预测，0controller。协议、输入pin、源码闭包与必要新检查先冻结到干净提交并推送，再首次执行一次；失败关闭本候选，不补跑、扫描或改旧门。持续目标active，C4及C5–C7未验收。

## 唯一变化与来源

保持IV2的psi5、固定IV1 action8、一次OLS、`rcond=128*float64_eps`和rank5要求；只把训练公共PD目标从qref偏移.04/.08rad改为**始终固定qref**。新数据不是原轨迹的匹配反事实，不认定旧目标或覆盖是唯一失败原因。公开身体、free-root/仰卧域、理想感觉、PD64/Kd4、保护及固定刺激是披露先验，无GPU、PPO、教师、任务预训练或真机。

恢复唯一IV2 canonical根 `results/cpu_validation/2026-10-12_consistent_action_state/raw`，来源提交 **`d8491b2e0f8b3bae649b8bf9a297bebba7f76270`**：

| 原件 | bytes | SHA256 |
|---|---:|---|
| `run.json` | 1145452 | `a6fd68bb909ac8d8607986aeb55918d76dce18b51f8a0bbcd2d93b8caef2a0ec` |
| `models.json` | 21758 | `96e94bc63311262878114354e1fb4f084564e5116cf14435ee47936415176dcd` |
| `predictions.jsonl.gz` | 10936879 | `de32524abd8f5b8a7f45d6dbc92158143c67b5fe05893656401c38dddfd58685` |

gzip pin是压缩原件身份。cold/oldlearned/IV1/IV2（原newmatched）只恢复身份并转录已存指标；不重新预测、fit或评分。新模型名 **IV3**，初始化从对应seed IV1拷贝，冻结其8个动作系数。不得使用IV2 moments、旧source_trace、PAR1 fork或评估端点作为训练标签；所有原模型参数与指纹保持。

## 新训练与一次状态拟合

固定seed **8101、8102、8103**，每seed fresh构造/reset一次，**1000 zero prefix +2000连续active**。原八轴身体、接触、关节范围、保护、2ms反馈/物理不变；左臂两轴学习，其余六轴请求零。qref取prefix第1000个合法完整端点；qref/公开范围须与本seed冻结模型精确相同，不覆写fresh身体状态。

每active步只用当前原生q/v和qref计算 `base=clip(64*(qref-q)-4*v,±.375)`。每seed唯一 `Generator(PCG64(seed+100000))`，每步一次 `rng.integers(0,2,size=2)`，axis0/1顺序形成独立Rademacher **±.125Nm**；最终已知请求为base+扰动，位于原±.5Nm权限，不另clip扰动或改符号。原公共角度guard、signed hinge、底层accepted/guarded处理不变，模型不读取实际力矩、root/IMU、其他关节、接触或隐藏动力学。

prefix/A/B仍各1000完整步，A/B只为预算和接触阶段，**两个阶段目标均为同一qref**。每阶段至少一个left_arm-floor正端点；完整轨迹、连续转移、努力、保护及冻结身份是前置。先保存每个已付端点，再audit/StudyAbort，再使用合法nextv；停止端点不进拟合。

**先完成全部三trial的6000合法active pairs，核每seed2000完整样本及连续性，再按8101/02/03依次一次fit。** 对本次新native转移：

`psi=(v0,v1,qrel0,qrel1,1)`；

`y=native_next_v - fixed_IV1_action8 @ (G0,G1,hG0,hG1)`。

每seed构造Psi2000×5、Y2000×2，只一次 `np.linalg.lstsq(Psi,Y,rcond=128*float64_eps)`，两head共同fit；解5×2转置替换`theta[:,[0,1,2,3,8]]`共10个状态系数。rank必须5，所有所需输入/返回值有限，否则全批停止。保存样本、Psi/Y、native fit记录、解/rank/singular/RSS及失败；无ridge、尺度改动、补秩、feature/lag变化、重权或扫描。

IV1 action8逐项及float64字节精确不变，原九特征、coupled_hinge9、2ms下一速度语义和Euler位置积分不变。fit后IV3冻结，0RLS/在线更新；旧参数指纹始终保持。

## 唯一已见评估人口

三个input可先hash；**全部训练与fit完成后才解压并读取保存prediction输入/实际端点评估标签**，训练流程不得消费这些标签。只取已存cold作为公共模板：3seed×原five-H **1443记录**，各H origin/seed为100/100/99/96/86、stride10。保存原生起点、已知future final requests及实际endpoint只用于固定条件预测/评分，不注入闭合递推或训练。

只对IV3执行新前向，预计 **62340 pair /124680 velocity-head输出**。旧cold/oldlearned/IV1/IV2全H/seed/轴/q/v指标直接从run转录，不重跑旧physics、模型、RMSE或旧门。全部模板身份、完整H路径/请求和finite必须满足，否则全批停止，不补标签或排名子集。

这是已见开发集，**不是新留出**；原时相slot3正/13反及五块probe已经用于IV2，不能据此声称泛化验收、独立复验或单一因果消融。

唯一新门 **cold→IV3** 保持：H10v/H150q每seed两轴严格改善，各轴三seed原RMSE算术均值改善≥20%；H150v及H20/H50 q/v每seed两轴不劣。H1q/v、H10q仅全部报告，baseline0百分比不可用。四个旧模型与IV3的全部不利差异公开，不择优替代IV3。局部key为`iv3_prediction_gate_passed`；失败关闭单候选，通过也仅是开发预测，控制必须另冻。原C4 20%模型贡献、5%强PD、1.05努力门未执行或改变。

## 预算、停止与保存

| 本批固定人口/上限 | 数量 |
|---|---:|
| 新训练trial /control /substep | 3/9000/9000 |
| 新native label pair /scalar用途 | 6000/12000 |
| 共同OLS /新状态系数 | 3/30 |
| 已见评估记录 | 1443 |
| IV3条件pair前向 /velocity-head输出 | 62340/124680 |
| 新评估物理 /RLS /fork /teacher /旧模型前向 | 全部0 |

训练新标签、已有评估标签用途、旧指标转录、fit系数、RLS和物理分别计账，不以30系数或12000label用途冒称RLS更新。既有累计保持，按实际新增训练物理记账；失败前校准/prefix/复位后的动作和全部付费端点不删去。PD/随机请求/guard、固定action、Psi/Y、OLS内核、预测/q积分、源码/输入hash/解压/JSON、构造/reset/forward、接触/actual actuator努力、准备与输出IO另计，未知工作标unknown。

沿用原环境终止、非有限/异常及active相对qref位置 **.12rad**、速度 **1rad/s** StudyAbort，每2ms检查不变。任一source/pin/连续性/接触/fit/预测/冻结身份异常立即记录首错并停止全批；保留已付完整/partial、全部事前trial/fit/1443预测槽和not_executed。次写盘错误附首错，不覆盖原错；不以早停声称效率。

runner为 `scripts/run_near_reference_identification.py`，必要新准备为 `external/new_near_reference_checks_once.py`。执行要求protocol/输入pin及exact clean source commit；source.zip保存新runner/协议与完整实际环境、资产、IV1保护/计费helper、IV2纯fit/model依赖闭包。首次全新目录拒覆盖，保存run、models、moments/Psi/Y、native source与IV3预测原件、旧指标转录来源、首stdio、全人口/失败、config/seed、依赖/CPU/wall/CPU与实际IO；具体schema由冻结runner明列，不修改IV2原件或重跑旧audit。

五science flags全false，`control_candidate_opened`为false。首次保存轻核、全部结果与限制报告、提交推送后继续active目标；本局部预测不代表C4、C5–C7或真机成功。
