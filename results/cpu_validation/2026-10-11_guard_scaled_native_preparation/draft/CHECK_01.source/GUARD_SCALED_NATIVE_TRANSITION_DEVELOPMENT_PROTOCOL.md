# N：单次 C400 输入 RMS 尺度 ridge 开发

正式脚本 `scripts/develop_guard_scaled_native_transition.py`；本协议正式放入 `docs/`。
准备目录 `external/c4_scaled_native_staging/`。准备禁止 actual payload、fit、rollout 或物理；
新合成分支须先静态审查、再经父任务授权首次执行，旧检查不重复。

## 固定单候选与来源

M clean4d10eac 的六套保存摘要显示：K 的肩/肘 q/v 四关注输出在三个 seed 均 shrink>floor，
L 均 floor>shrink；两套 Phi/Z/A_perp 数值 rank 29/25/4。L同C上的floor增加、shrink下降，
条件动作能量比率下降但绝对能量未消失。它们只支持检验尺度导致的收缩，不证明机制唯一或动作缺激励。
不延续此前位置—速度方案，不增加特征/数据/门/诊断层。

唯一 N 候选只消费 K clean `b46c6d37fddc8e6534384168fb76663bc2c5236c` 的原 C400：
三seed各400×29 Phi、400×22 delta、原W/qref/IDs。原K仅恢复，不重新拟合；
D clean `f7710c7b048dccab3e436d1fa16432f881a35992` 的 sparse11 snapshot按原 helper恢复、冻结。
C clean `5ea8df42b09588845760daf0dc1f270aef2a87f1` trace只消费公共 prediction100及其连续prefix/history；
可解析整文件且如实计读取费用，不重新生成calibration标签，不消费G/L、旧预测、update日志或审计。
K/C/D原件固定hash及逐字段bytes/SHA绑定；K helper原source SHA和全部依赖精确冻结。

每seed对原训练Phi **不中心化**：`s_j=sqrt(mean_i(Phi_ij^2))`，`Psi=Phi/s`；
`B=solve(Psi.T@Psi+.01*I29,Psi.T@Delta)`，`W_raw=B/s[:,None]`。
全部29列（包括常数）同样参与；constant原列为1，RMS仍为1。
所有scale须finite且严格正；零或算术失败立即保存partial并停止整次run，
无floor、删列、改lambda、回退、扫描或再求解。每seed仅一次29×29/22 RHS求解。
同一函数空间在精确算术中不变；原单位目标等价 `||Delta-Phi W||²+.01||diag(s)W||²`。
近零列会放大微弱或噪声变化，RMS把训练幅度用作参数惩罚先验，未给出噪声/激励充分性证明。
归一化后每列尺度无量纲，delta输出仍分别为rad、rad/s或/g；不合并混合单位损失宣称优势。

## 权限、闭合与开发双门

全部state22、feature29、KnownAngleGuard、hinge .25、prior与K原helper相同。
位置prior仍 `q+.02*current_v`，不改用predicted_next_v；全部22输出都递归生成，
previous_v只取本trial合法过去端点，递归更新为old predicted current v。
仅原生q/v/6轴IMU、已知请求与连续过去端点；无orientation、接触/实际力矩/动力学/quaternion特权输入。
未来保存请求仅作离线条件输入；真实未来原生终端在三组rollout后评分，不注入状态。

N22/K22/D11全部三个seed，H `(1,2,5,15)`、每seed固定origin `(100,99,96,86)`，
每horizon独立初始化，缺样或非finite不缩分母、不排名可用子集。
K/D重新预测、各自费用单列；恢复后参数指纹前后严格不变。
仅N新增fit；K/D恢复的参数不算新拟合。

对 **N→K与N→D分别且同时**使用原K门：
H1两轴v每seed严格改善、每轴三seed平均相对RMSE改善≥20%；
H15两轴q每seed严格改善且每轴平均≥20%，两轴v每seed不劣；
H2/H5两轴q/v每seed不劣。H1q仅描述。所有三组必须完整固定count；
零/非有限基线RMSE或缺样使门不可评估，不通过。
同C已见开发比较只否定/筛选单候选，不能识别噪声因果、通过新留出或完整控制。
K/D旧失败门不追认；无论N门结果，scientific_adoption/C4/C5仍false。

## 首次执行与费用

canonical脚本/protocol/helper字节须同精确clean40位commit；新output，失败不覆盖、不重试。
成功预计3新solve、26,400重复使用已付费native scalar标签、1,914新独立系数；
归一化B与raw W是同一1914系数的两个表示，不翻倍计新参数。
scale使用34,800训练输入scalar/87尺度；normalization34,800与映回1,914 scalar除法分列。
fit两矩阵乘法各3次，actualattempt/return/failure、形状与逻辑乘加请求均保存；
logical请求不当作测量硬件FLOPs，wall与CPU process_time分列。
预计每方法全seed6204递归步，D6204pair/12408scalar头，3429origin/predictor原件、576组指标；
N/K各136488残差头输出。所有失败前付费计算继续累计，物理/RLS/MPC为0。

固定输出 parameters.json、predictions.jsonl、metrics.json、run.json、manifest.json；
失败另保存failure.json，已形成的新scale/矩阵/参数、轨迹、计数保留。
source verifier未返及input record未返明确unknown，不写0来冒充未发生费用。

```powershell
python scripts/develop_guard_scaled_native_transition.py --repo . --source-commit SOURCE_COMMIT --output NEW_OUTPUT
```
