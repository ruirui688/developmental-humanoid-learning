# C4 S 概念 review：冻结Q其余20head，只开发两位置head

结论：这个单候选有明确动机，可以在下述边界冻结后做一次有限开发；没有理由
预先承诺它会通过。Q速度优势与R位置结构未过门，使直接约束多步位置误差成为
可检验的下一项。S不是新控制成功、在线适应或未见数据验证，C4/C5仍关闭。
本轮只读已冻结的KnownAngleGuard源码确认其分支语义；未读真实payload、运行数学
或写实现。不能从这次训练归因某个head是旧误差的唯一原因。

## 冻结前必须消除的歧义

损失必须固定为均方，不是先取带符号误差均值再平方。设N_h为400/399/396/386，
明确两轴也在均值分母中：

```text
L(U) = (1/4) * sum_h [ (1/(2*N_h)) * sum_origin sum_axis
                         ((q_pred_end(U)-q_actual_end)/.12)^2 ]
       + .01 * sum_50x2 (U-U_Q)^2
```

`.12`是已公开位置尺度，不能改成training RMS或prediction误差估计。
每h等权、每轴等权；正则项为全部100系数的sum，不再除100，也不除seed数。
这与Q原ridge的未归一化标签平方和/零中心正则有不同的有效强度，虽然数值都为.01；
应披露为新的固定损失先验，不能说只是原ridge不变。不得再扫尺度、权重或lambda。

120秒必须定义计时起止和中断粒度。同步forward/backward不能在任意指令处被
普通perf_counter检查抢占；入口/出口及callback检查只提供边界式deadline，单次计算
可能跨过120秒。推荐明确采用该粒度，保留跨界实际费用和overrun，停止下一次计算、
候选回退到deadline前已登记的最后accepted snapshot。若要宣称严格hard wall上限，
则须独立worker、父进程超时终止及逐callback持久化checkpoint；不能在未实现抢占时
把超时后的计算时间省略。此处是预算语义需要冻结，非科学原因禁止继续。

## 原数据、标签和闭合

C400是每seed100..499的400段已付校准交互。H1/2/5/15的全部合法origins固定为
400/399/396/386，不因停止、缺失或非有限挑选子集。逐窗核同trial过去两端点、
连续感觉与请求、完整子步及源停止；不能跨trial补previous_v或将缺失补零。
若原固定人口无法构造，应保存开发失败而不是缩小训练分母。

每窗只把首个原生x22、合法previous_v及该窗已知请求序列传入rollout。
未来实际两轴q仅在末端loss使用；不能把真实中间q/v/IMU灌入递推，不能detach
自己的中间状态后将其替换为数据。q是相对qref坐标，actual q也须同一qref定义。
其余20head的系数冻结，但自身输出会受新的q反馈影响，不是冻结20个状态值。
全22输出、guard、phi50及previous_v仍按自己的路径推进。R不恢复。

区分以下费用，不能因为同一数据曾被Q使用就写“0标签训练”：

- 每seed唯一未来两轴q端点标签为800scalar，三seed共2,400；物理仍0新增。
- 每次完整objective涉及1,581窗、3,162个末端q误差标签用途；三seed一次各完整评估
  合计9,486用途。实际重复次数按每seed实际forward尝试/返回计，不用计划上限代替。
- 每次完整objective递推8,968次原生转移；全部22残差输出若都计算，则197,296scalar
  输出。不同h重复递推也付费；向量化不将窗或标签用途计为1。
- 恢复Q既有3,300参数及原26,400标签/3solve费用继承。S每seed仅100个位置系数
  可优化，共300；冻结的其余20head是每seed1,000系数。无新参数维度不等于无估计。

可预先构造固定训练窗口/target tensor一次，记录读取与材料化费用；每次objective
重复标签和forward/backward用途另列。生产科学评分必须仍使用完整S/Q/K/D人口、
S→K/D原两门，Q描述对照。已见C prediction不参与梯度、早停或参数挑选；本开发bank
不能以后改称未见验收bank。

## 不连续guard与L-BFGS的边界

KnownAngleGuard在q<=lower+.03或q>=upper-.03且请求向外时，将非零clip请求
直接切到0。它对q存在有限跳变，不只是连续函数的折点；hinge还存在折点。
Torch实现必须保留原比较的等号、clip/zero/hinge语义、q不被裁剪及current-start时序。
不能用平滑近似、直通梯度或固定真实guard轨迹偷偷改变S模型。

布尔分支内autograd给出当前分支导数，不提供开关跳跃的导数。其余闭合路径应完整
传播梯度；把guard分支值转成NumPy/Python造成整个q路径detach则不合配方。
L-BFGS-B可作为这个固定目标的一次启发式优化，但其平滑假设不满足；线搜索异常、
梯度范数小或success=true都不是模型有效性证据。固定gtol/ftol/maxls10不改，不在失败
后换solver、重启、扫超参或加平滑。若无bounds，应明确`bounds=None`而非虚构盒约束。

新增的必要小合成检查只针对Torch新转移/梯度路径：guard远离阈值的少数参数梯度、
完全自身闭合及previous_v、其它20head系数不变和精确阈值forward语义。
用合成对象，不调用真实数据挑epsilon，不泛化成复跑Q/P/K旧测试或大规模梯度审计。
Torch/scipy版本、CPU float64、单线程和任何依赖来源/许可沿项目规则锁定。

## Objective预算与可发布候选

建议一次call返回loss与analytic gradient，即scipy `jac=True`；一次真实forward加
backward才是一份objective工作。分别记录实际函数调用、forward/backward尝试/返回、
SciPy nfev/njev、callback accepted迭代和失败，不能把nfev+njev作为相同工作做两遍
计数，也不能靠缓存少计已实际重复的计算。初始loss/gradient、额外finite验证若调用
objective也消耗100calls；callback和结尾不要隐含再次评估已保存accepted参数。

每seed启动前预登记100call硬计数与time deadline；在下一次objective计算前检查，
超限不执行。maxiter30/maxfun60/maxls10为solver固定限制，maxfun可能在迭代边界才
停；它不能替代实际hard-call guard。所有line-search trial，无论接受、拒绝或失败，
都保留请求/返回计数、loss/gradient有限性和已付费用。不因不利结果重置seed预算。

在首次有限initial objective/gradient完成后，可登记U_Q为iteration0的已接受初始化。
只有callback确认的有限accepted参数才能替换snapshot；不能选最低prediction分数、
最低line-search试探loss、异常result.x或“最后一次objective输入”。正常结束也使用
同一last-accepted定义；若无callback，则只能是合法iteration0，明确0 accepted更新。
若初始loss/gradient非有限或deadline前未完成，不能把未经验证的U_Q当已训练候选。

预算/超时终止保留最后合法snapshot并标budget_exhausted；SciPy maxiter/maxfun限制也
单列具体reason。ABNORMAL_TERMINATION/非有限gradient等为optimizer_failed或对应异常，
不能都归成预算耗尽。若此前有有限accepted snapshot，可否仍发布它必须现在冻结；
建议允许，但同时保留optimizer_failed、accepted iteration与实际费用，科学门全照旧。
没有合法snapshot则该seed无候选，不静默用cold替代、不删seed、不补跑。

最终候选选择只由训练过程accepted次序决定。源码、配方、预算、seed和上述状态映射
先冻结后首次执行；有限候选及optimizer停止状态只具工程意义，原科学门不放宽。
完成本阶段归档、检查与提交后继续最早未验收C4，不能因一次训练或报告停止目标。
