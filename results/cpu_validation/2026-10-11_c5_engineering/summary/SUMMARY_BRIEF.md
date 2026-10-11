# C5 首次工程汇总

一次只读汇总完成，未重新采集、审计、拟合或调用模型。四组全部完整，各120控制调用/1200子步，总计 **480调用 / 4800子步 / 0未知kernel attempt / 0模型或策略更新**。原独立审计481,538检查、0失败、工程门通过；本汇总39项记录一致性检查、0失败。

base/wrapper共同120行观测/状态/实际子步历史精确一致，79,800数值叶比较、最大差0。100前缀后的事件均保持qpos/qvel/ctrl/last_command/time/计数；gain_half改变完整plant fingerprint，base物理fingerprint不变；armature_double在native DOF6/7上的同q质量矩阵对角各+.01，最大偏差1.734723475976807e-18，事件不增加积分。

| Trial | j0/j1 请求绝对努力 N m s | j0/j1 实际力矩绝对努力 N m s |
|---|---|---|
| base_identity | .05 / .05 | .05 / .025 |
| wrapper_identity | .05 / .05 | .05 / .025 |
| gain_half | .05 / .05 | .025 / .0125 |
| armature_double | .05 / .05 | .05 / .025 |

合计j0/j1请求努力各.2，实际努力.175/.0875。实际力矩和请求不同应继续单独披露；不能将执行器增益下降或限位保护导致的努力变化称为适应、技能学习或算法优越性。本次没有模型更新，也没有学习/适应证据。

summary源SHA256：`13491bf344701637f2c44f9812659dac6d1a8ef54be9d510d8891164a59818bc`。
summary结果SHA256：`739e9ce157a4712ae603e1e285f03d804cb7ddca3aece1b4be946f7ea832b3eb`。
同进程wall=.006100099999457598 s，process CPU=0.0 s（短任务低于Windows计时分辨率）；仅一次raw+audit读取，无自动等待、重试或复跑。

此前四个手算fixture均通过，保存在 `external/c5_engineering_staging/summary_fixture_attempt_01/`。本目录保存一次执行的source、attempt、summary、stdout和execution原件，root负责后续归档与结果文档。
