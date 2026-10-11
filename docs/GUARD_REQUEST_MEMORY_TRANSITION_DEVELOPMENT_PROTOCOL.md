# C4 P：单个已知请求记忆转移开发协议

本协议固定一个候选：在 K 原始尺度 phi29/x22、lambda=.01、C sparse400 上追加上一合法
同 trial 的两受控轴已知请求。不保留 N 的 RMS 修订，不扫描 lag/正则/权重，不改数据、
位置结构、先验或旧门。O 的保持/释放条件退化仅给出检验动机，不能识别记忆的因果作用。

## 唯一模型与合法历史

`phi31 = [phi29_K, requested_u0[t−1], requested_u1[t−1]]`，新增列单位 Nm，使用原保存
requested_torque 两轴原值，不额外 clip、不作过去 guard 投影。它是机器人已知请求，
不是实际执行力矩或20ms区间平均输入；原请求也可能含原 native veto。

保持 K 当前 KnownAngleGuard、hinge、当前速度的位置prior、公开prior、previous_v语义与
22输出闭合。新增过去请求在prior中的系数固定0，学习残差可使用它们。每seed唯一求解：

```text
Phi31 = concatenate(saved_K_Phi400x29, legal_past_requests400x2)
W31x22 = solve(Phi31.T @ Phi31 + .01*I31, Phi31.T @ saved_K_Delta400x22)
```

使用 K 已保存设计/标签/IDs/qref，不重生标签或重拟合 K。每行对应原 calibration_sparse
step100…499；必须存在同trial连续、完整且合法的前序区间，第一行用 prefix99 的已知
请求。校验原生连续端点仅用于历史来源合法性，不提取新拟合标签。不得跨trial、补零、
用未来实际量或放宽缺失历史。保存 past request 与来源ID；固定400行分母单列，合法
历史可用计数从0逐步增加，中途失败保留已消费历史。

预测沿原全窗口：origin0 用同 prediction trial prefix99 请求初始化；其他原点用对应
前序请求。每成功递推步后，past_request 更新该步旧已知 request[:2]；previous_v 更新
该步旧 current v[:2]。未来22维原生状态全部自身递推；不读未来真实感觉。K/D共享原
目标条件、同一保存未来请求序列、原权限与完整分母。未来请求是离线oracle条件，不能
称在线规划或控制成功。

## 固定来源与权限

来源沿用已冻结 N 的9输入定义与全部精确hash：C manifest/metadata/trace，D根manifest/
raw manifest/diagnostics，K manifest/run/parameters。C/D/K 原commit分别为
`5ea8df42b09588845760daf0dc1f270aef2a87f1`、
`f7710c7b048dccab3e436d1fa16432f881a35992`、
`b46c6d37fddc8e6534384168fb76663bc2c5236c`。
固定 N 纯支持脚本 SHA256
`df0833d08e722391f98de1bc2cbf81e2d0a866a3ea65def24e9b216d25787518`，
K 纯helper SHA256
`f910bb6fd9f01ebf5fd52426b40b43414e50bebcfe6460cf6132bccb1a2192bb`；
两原协议及五个纯包helper身份也在生产常量中固定。

新 clean exact HEAD 先核本脚本/协议及全部helper committed bytes 与pins，再加载纯函数。
只调用 N 的来源读取/恢复 K/fingerprint 和 K 的原生映射/基线递推/指标/门；不调用 N
RMS拟合或其正式main，不改变helper globals。K22和D11均重新预测但不更新，前后参数
fingerprint必须一致；D只恢复原 sparse11 snapshot。全部费用分列。

C压缩原件全部读取/解压/逐行解析计费；仅保留 calibration_sparse 与 prediction 的连续
原生端点、请求、ID与完整/停止字段。calibration 原生值只作历史连续性与prefix身份检查，
训练只消费 K 已保存 Phi/Delta；其他trial、接触、实际力矩、root姿态、隐藏物理立即丢弃。
不读取 G/L 或旧保存预测、旧更新日志；准备不读真实参数/trace来选择配方。

## 固定完整双门

P22/K22/D11，seed0/1/2，H1/2/5/15各100/99/96/86原点。沿 N 两门原规则：

- P→K 与 P→D 的 H1 v：每seed严格改善，各轴逐seed相对RMSE改善均值至少20%；
- H15 q：同样每seed严格改善且各轴均值至少20%；H15 v每seed不劣；
- H2/H5 q/v：各轴每seed不劣；H1 q仅描述；
- 全固定组完整；零/非有限分母、缺失或不可用使相应门不可评估/失败，不排名部分轨迹。

两门都必须通过，不能只对 hold/release、某轴、某时距或最佳seed排名。
无论门结果，scientific_adoption/C4验收/C5依赖解除都为false；旧D门不追认。
失败不进入控制。开发通过仍需新留出和matched完整控制，不能宣布C4完成。

## 固定预算、输出与首次执行

预期3次31×31/22RHS求解，26,400重复scalar标签、2,046新系数；原K设计34,800个scalar
复制消费，新增历史2,400个scalar。P/K各6,204步完整状态递推、136,488个残差scalar输出；
D6,204pair/12,408scalar预测。3,429预测记录、576固定组。物理/RLS/MPC为0。

保存参数/新增设计/历史来源/labels/Gram/cross/normal/weights、全部预测路径/历史advance、
双门、source/input身份、依赖、读取/解析、尝试/返回/失败与耗时；失败保留partial paid。
输出固定 parameters.json、predictions.jsonl、metrics.json、run.json、manifest.json；
失败另存failure.json。不覆盖旧目录，不补跑到成功。所有复用计算独立计账，逻辑矩阵
操作不是硬件FLOPs，计时不含所有最终输出序列化/写盘。失败记录中的非有限数值用
`nonfinite_float`及`NaN/+Infinity/-Infinity`显式编码，原failure类型、消息与位置保留。

准备小self-check仅验证新31特征/过去请求与previous_v推进、无历史拒绝、零新增列与
固定合成解析参考等价、预置solve失败的partial/paid保存、直接非有限failed payload保存；
不为序列化检查新增求解。共用case尝试日志，父任务
首次一次执行。不得执行正式拟合、旧数学/测试/审计或读取真实payload。

```powershell
python scripts/develop_guard_request_memory_transition.py --repo . --self-check --output <new-preparation-directory>
python scripts/develop_guard_request_memory_transition.py --repo . --source-commit <exact-clean-P-HEAD> --output <new-formal-raw-directory>
```

准备读取日志见 external/c4_p_preparation_reads.json，由父任务封存；schema阅读与合成计算
各自计账。阶段完成后按实际双门决定后续，C4仍最早未验收，持续目标active。
