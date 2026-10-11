# C4 R：冻结Q模型的受控关节位置—速度一致性开发协议

Q已首次完整执行：H1v相对K/D约26%–28%改善，H2/H5qv和H15v各seed不劣，
原双门只剩H15q不足20%。本次在这个新证据上冻结一个位置结构候选，不增加模型
阶数、数据、lag或参数搜索；不能据此断言独立位置head是旧误差的唯一原因。

## 唯一干预

完全恢复Q的已保存phi50/weights50x22及公共尺度。每步只计算一次原Q完整next_x22，
然后替换受控位置0/1，其余20输出保持该步Q结果：

```text
next_Q22 = prior_K22(x, previous_v, current_request) + phi50_Q(x, previous_v, current_request) @ saved_W_Q
next_R22 = copy(next_Q22)
next_R22[0:2] = x[0:2] + .01 * (x[8:10] + next_Q22[8:10])
previous_v_next = old_x[8:10]
```

`.01=DT/2`，DT=.02s沿用原控制区间；x位置已是q−qref，不再减qref。
这是两端速度的梯形运动学近似，带有公开物理先验；20ms内接触/速度变化可能使它
失效，不能假设端点平均等于真实区间积分。没有新增位置残差、blend系数、系数搜索、
速度修正或裁剪。Q两个独立位置head在R中被丢弃；仍计算原22输出并计其计算费用，
Q原22标签拟合费用全部保留，不能声称只用了20输出训练。

首步速度理论上与Q相同，后续R位置反馈会改变phi50与current guard，可能恶化
其他时距的速度与位置；因此保持全部原规则，不只验长位置。22状态全部自身闭合，
previous_v推进旧current v；不读未来真实感觉、实际施加力矩、接触或隐藏参数。
P请求记忆、N尺度、Q新拟合及新数据均不加入。

## 冻结恢复与来源

Q源commit为`20fa0321c84eb766eeafb9f8d906f554bca60622`，其源码SHA256
`6a8109ed9ba68b61674f9744ac0ea4ffce421ff8b4400abfe7cc081b5c16a147`，
协议SHA256`77cb47c42efad889f4d15cf64207b528ab2c7e29908d55d3f16441b0b7a6c5d3`。
新R clean exact HEAD先核R源码/协议和全部pure helpers的committed bytes/pins，
再恢复Q/K/D。Q的根/raw manifest、run、parameters用首次归档精确身份绑定，
原C/D/K九输入、来源commit、qref、训练IDs及K保存参数身份保持同Q。

Q恢复要求3seed各400标签来源、lambda.01、六公开尺度、21顺序、50输入22输出、
原fingerprint完全一致，参数前后指纹一致；Q/K/D只恢复，不fit/update。
可以读取Qmanifest身份冻结pins，不读取真实weights、trace或预测结果选择配方。
生产不读取Q保存预测或metrics重写旧门；只将恢复的Q重新预测作为描述对照。
C原trace全部读取/解压/解析计费，只保留合法prediction窗口，其余特权字段丢弃。

## 完整开发矩阵与原双门

R22/Q22/K22/D11，seed0/1/2、H1/2/5/15，对应100/99/96/86固定原点。
原人口1,143个窗口，每方法各1,143记录，共4,572记录；native三方法各22通道，
D四通道，共840组。共享初态、目标条件、保存未来请求、权限和完整分母。
未来请求仍为离线oracle条件，不能称在线规划、完整控制或真机学习成功。

只对R→K和R→D判原双门：H1v/H15q每seed严格改善、各轴逐seed相对RMSE改善均值≥20%；
H2/H5qv及H15v各seed不劣，H1q仅描述。Q仅作为该结构干预的描述对照，不要求
R对Q的一步速度改善20%，不把Q已有优势当R新增学习。全部固定组、缺失/停止/非有限
都保留；不排名部分轨迹，不修改或追认Q/K/D旧门。
无论开发结果，科学采用、C4验收与C5依赖解除均false；通过后另冻新留出和matched完整控制。

## 预算、工程检查与交付

0新增fit、标签拟合、参数估计、物理、RLS或MPC；恢复Q已有3,300参数用途计账，
Q原26,400标签/3solve成本保留。R/Q/K各6,204完整状态转移、136,488残差scalar输出，
D6,204pair/12,408scalar预测。R与Q各自二阶130,284乘积、37,224尺度除法分列。
R梯形约束额外24,816scalar加法、12,408乘法和12,408位置覆盖；丢弃的两个q输出
仍包含在R136,488残差输出中。计划不是实际费用；尝试、返回、失败和partial分别保存。

输出parameters.json、predictions.jsonl、metrics.json、run.json、manifest.json，
失败另存failure.json。保存冻结参数恢复身份、ignored head、所有自身路径/历史、
完整分母、双门和已计算付费；非有限failed/unavailable数据以显式JSON标签保存，
不补0或丢掉失败。计时排除最终输出序列化/写盘，原stdout/stderr与准确首源码封存。

小合成检查仅针对新约束：端点速度相同退化为Euler、非零速度改变的梯形位置、
两个Q位置head不作用而其余20输出保留、连续两步自身闭合与old-current-v推进。
不拟合、不重新执行Q/P/K旧case或数学；小case计算单列。准备不读真实参数/trace。
必要新恢复schema身份失败只用合成对象，不扩大通用审计。
先准备/独立静态review/首次合成并冻结推送，再从clean源码首次正式一次。
失败不补跑、不扩阶/扫描或接入控制；结果报告/提交后继续最早未验收C4，持续目标active。
