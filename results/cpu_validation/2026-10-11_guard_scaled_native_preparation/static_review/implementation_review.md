# N 固定 RMS 候选有限静态审查

当前封口结论：**限定范围内无剩余静态阻塞，必需最小修复为无**。生产脚本/协议保持原固定候选；新增case费用保存及一次夹具接口缺口已最小修复。首CHECK_01失败永久保留，CHECK_02只执行修复后的failure_partial，前三case没有重跑。本审查智能体未运行任何检查或实际计算。

范围：只读 `external/c4_scaled_native_staging/develop_guard_scaled_native_transition.py`、同目录协议和 `check_scaled_native_transition.py`。未读actual K/C/D payload、trace或旧预测，未fit/rollout/SVD/物理，未重审旧K数学或扩大检查。

## 生产路径确认

- 原C400/29列固定不中心化RMS，每列finite且严格正，零列/算术失败停止整run；没有floor/drop/centering/lambda搜索。`.01` ridge归一化求B，映回raw W，原prior和全部22输出闭合继续用原K helper。精确算术下函数空间相同、惩罚先验改变，不能称原单位正则完全相同。
- 每seed固定恢复K的Phi400/Delta400/W、qref和完整IDs，K不求解；D只恢复原sparse11 snapshot。所有原件pins和source/helper绑定固定。K/D指纹运行前后核对，N唯一新fit。
- C parser仅保留公共prediction和prefix/history，当前原生q/v/IMU、请求及合法过去端点；不消费calibration/update/G/L日志或特权信号。未来请求仍是记录条件，真实未来state仅窗口资格/最终评分。预测prefix/qref/100active必须与K/D一致。
- N→K和N→D独立调用冻结原K门；alias仅为复用指标实现，返回seed字段已改为N22及真实baseline RMSE，scope、candidate/baseline明确。所有三组完整固定counts为共同条件，无缩分母、最佳子集或q-only绕过H1速度门。科学采用/C4/C5一直false。
- 已修scale输入requested在RMS运算前计；RMS原始returns和scale validation failures分离。矩阵backend失败与原始返回后的finite validation失败分列。标签用途、solve attempt/return、映回除法、拟合系数分别记录，B/rawW不双算参数。已返回C dependencies保留，未返回为unknown。
- 生产失败保留已形成合法scale/normalized design/gram/cross/normal/weights与付费计数，整run停止不重试；来源和输入未返回有unknown语义。近零正RMS的噪声放大风险明确披露，finite不等于鲁棒。

## 四个新合成case的允许范围

1. 新对角惩罚与raw/normalized前向等价：仅新N目标，包含一次独立参考solve及其费用，未重做旧K各数学分支。
2. zero列拒绝：检查已计算RMS/费用和partial保留、solve前停止，不引入替代尺度。
3. near-zero：仅证明该配方可将很小训练幅度映成很大raw系数；不能声称实际C某列就是噪声或真实失败原因。
4. 注入solve失败：全部真实来源/恢复/解析均mock为合成fixture，生产partial和已付费label/矩阵保存，没有actual payload或rollout。

四case未增加，更未重跑旧检查。执行授权与结果由根任务单独负责；结果按下列首执行记录分别保留，静态审查不替代执行。

## 准备runner的首审缺口与修复确认

首稿main在case函数异常时仅写traceback，局部Counter/reference_cost只在成功return才附detail，可能丢失已付费合成计算记录。最终仅复核新增journal段：每case先建立unknown状态；fit前将活Counter注册共享journal，独立参考矩阵/solve的attempt、return、failure及标签用途实时更新；前向/敏感性运算的请求和返回分列。注入solve失败的main以wrapper绑定其真实fit Counter；case异常仍写出journal。未注册部分保持unknown，成功预算没有替代实际费用。原四case、生产数学/协议均不变。

## 最终审查版本

只重新读取新增共享journal/参考计账及runner异常分支，没有新检查。确认SHA-256：

- production：`df0833d08e722391f98de1bc2cbf81e2d0a866a3ea65def24e9b216d25787518`
- protocol：`0027650441b59159b407e21b687057e816c61c127ca6f5f4f06b6ac44b8b87b7`
- 首CHECK_01 synthetic check：`ed435129afa901ce6ac0e4d3c3ba9c4e63b2c6e462dae8ff2172f60c3db68b53`
- fixture-only修订后 synthetic check：`e92d8701822c03c0be8a426425d93fc096bffffa004247b3a3214bdf26685b1e`

若版本再改变，本结论不自动覆盖新修订。实际payload/正式fit/rollout未执行。

## 首检查夹具失败与一次修复

根任务报告首次CHECK_01前三case通过，failure_partial失败：mock `read_inputs` 返回的blobs为空，生产main在调用已mock的parser前仍须求值 `blobs[Ctrace]`，因此先发生KeyError，预置solve失败尚未触发，0fit/0solve。首静态审查漏掉了这处mock实参求值顺序。0fit不表示整个准备免费：前三case已发生的拟合/独立参考solve、label/矩阵使用和准备CPU费用仍保留原首报告；夹具首异常、stdio/fixture和三源before字节由根任务保存在CHECK_01.source等原件，不改称首检查成功。

本次只比较 `CHECK_01.source/check_scaled_native_transition.py` 与当前check的diff：唯一变化为mock blobs从 `{}` 改为 `{f"{code.C_ROOT}/trace.jsonl.gz": b""}`。parser仍mock返回合成trials/counts，占位字节不进行gzip/JSON解析，不读取actual trace，不改变production/协议/前三case/候选数学或门。三源哈希再次确认，production与protocol仍为上述原值。

根任务报告只以 `--only failure_partial` 首次执行新CHECK_02并通过：预置mock solve失败被触发，1fit尝试/0fit返回、8,800合成label用途、2matmul返回、1mock solve失败，partial保存；0actual输入/物理。该工程fixture内的预置失败不是正式N科学失败或成功，也不能冲销CHECK_01。此处只引用根任务提供的执行事实，没有再次读取report/fixture、执行case或重算预算。
