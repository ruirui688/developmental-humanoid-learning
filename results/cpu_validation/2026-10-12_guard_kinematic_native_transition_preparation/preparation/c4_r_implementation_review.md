# C4 R 新实现静态 review

审查结论：未发现阻断首次合成检查和冻结开发的实质问题。该结论只针对新 R 源码
的实现与协议一致性；不证明科学门通过，也不解除 C4/C5 依赖。已有协议审核不重做，
本轮未读取真实 weights、trace、预测或科学指标，不运行模块、模型或旧数学。

## 已绑定的 final-ready 身份

- `scripts/develop_guard_kinematic_native_transition.py`：31,640 bytes，
  SHA256 `07a0135e6cd30e169f780f30eef09472fe857570fa0556f552dcdcbe258c693d`。
- `docs/GUARD_KINEMATIC_NATIVE_TRANSITION_DEVELOPMENT_PROTOCOL.md`：5,202 bytes，
  SHA256 `8f3c86ccfc4626dbf6219e904daa73b208d2cac044a855e050875aecd62e5c45`。

作者和主任务确认 final-ready 后，仅核对上述两文件字节与 SHA256；不重复作者
已完成的 AST/compile/helper-pin 检查，不执行 selfcheck 或正式实验。本 review 至此封口。

## 关键新路径

`read_Q_inputs`只取冻结 Q 根/raw manifest、run 和 parameters，逐文件比对精确
身份，并核根/raw绑定、clean Q commit、原 C/D/K 输入和 pure-helper 身份。
它不读 Q 保存预测或 metrics 来调整配方。`restore_Q`核三 seed、50/22顺序、
21二次项与公开尺度、C400 IDs、qref、K/D指纹及 Q 原参数指纹，只复制保存 W50x22；
运行路径无 Q/K/D 重 fit 或 update。末尾重新核三种基线指纹，保留 Q 原已付 fit 成本。

`q_step50`调用冻结 Q 的单步原逻辑，取得完整 Q candidate 与 old-current v。
其局部 paid counter 在 `finally`全部合入 R 费用；Q candidate 的转移尝试/返回/失败
另名为 R22_Q_candidate，避免与完整 R 转移混淆。其余 Q 计算计入 R；两个将被
弃用的 q residual head 仍包含在原22输出及费用内。

`kinematic_override`只覆盖0/1两轴相对位置：old_q + .01*(old_v + next_Q_v)，
不再次减 qref；其余20项保持本步 Q candidate。替换前保存两项 discarded q 输出，
额外加法/乘法/覆盖先记请求，再记返回，非有限替换保存 partial 并失败。
`rollout_R`在该覆盖成功且有限之后才登记完整 R 转移返回；下一步输入就是自己的
R22状态，previous_v推进 Q单步所返回的旧current v，不读未来真实速度。

## 完整人口、门与失败

R/Q/K/D每 seed 使用同一原生初态、连续过去history及未来已知请求条件。
全部 H1/2/5/15 的100/99/96/86原点保留，生成4,572记录、840通道组；
缺失窗口为四方法同时保存 unavailable，预测失败保留路径与 attempted history。
实际未来原生端点仅在所有方法rollout之后评分。完整计数优先，部分轨迹不排名。

双门只选 R→K与R→D，沿用原 H1v/H15q 的20%规则和其余不劣规则；Q为描述对照。
映射到旧 pure gate 时，多余cold别名不进入两个被选方法的阈值比较，但其完整性
仍可使门失败。科学采用/C4验收/C5解除始终 false。

主失败保留 failure.json、已返回输入身份、已付 counter及所有 partial。
unavailable/failed 非有限值以显式JSON标签保留，未改成0或裁轨。
新合成case只检验梯形替换与两步闭合，用mock Q而不重跑旧Q数学。
来源 pins和clean-commit核验由正式路径负责；本静态review不替代首次工程结果。
