# M：固定 K/L 设计矩阵几何诊断

正式位置：`scripts/diagnose_guard_design_geometry.py` 与本协议。
准备草稿在 `external/c4_design_geometry_staging/`。准备只读取获准K/L manifest/run身份；
不读参数payload、trace、预测输出，不执行实际SVD、拟合、预测或物理。此前位置—速度候选不执行。

## 固定输入

三seed全部保留，每seed两套且顺序固定K400→L600，共六套。
K原件来自 clean `b46c6d37fddc8e6534384168fb76663bc2c5236c` 的 C sparse400
`fit.phi400x29`、`fit.delta_labels400x22`、`fit.weights29x22` 与训练IDs。
L原件来自 clean `3bbc34d05e83162cb052590e84981e3c690f9bd4` 的 C400＋G PD200
`phi600x29`、`delta_labels600x22`、`fit.weights29x22`、训练IDs与collection标签。
只消费上述矩阵、固定定义/qref/ID元信息，不读取其它参数记录的prior、预测或评价。
K/L raw manifest/run/parameters及L首来源失败归档manifest各有固定SHA pins；按bytes/SHA逐字段绑定。
K400与L前400的Phi/Delta/qref、ID须完全相同；C IDs为本seed calibration_sparse:100…499，
L后200须为本seed PDselected:100…299（扣除100前缀后active0…199），
所有29列/22输出的名称和.01 ridge一致，来源/数量不符就停止，不修配或缩减。
不读取G/C trace，不重放K/L已揭晓预测，不生成新采样或恢复控制模型。

L原首来源失败clean2dce248及其读取费用保留，不能改称成功；本轮绑定其公开归档manifest，
不读取失败payload。K/L旧学习、PD增益开发、物理和失败费用持续累计。

## 固定数学

所有数组float64；每个SVD固定`full_matrices=False`，
`tol=eps(float64)*max(matrix.shape)*smax`、`rank=count(s>tol)`；零矩阵tol=0/rank=0。
保存全部singulars、被丢弃singulars和tol，不扫描阈值、不设替代科学通过门。

每套Phi做一次SVD：`Phi=U S Vt`，取保留秩Ur。
`floor=Delta-Ur@(Ur.T@Delta)`；
`shrink=Ur@(diag(.01/(s_retained**2+.01))@(Ur.T@Delta))`；
`saved_ridge_residual=Delta-Phi@W_saved`。
floor是在该固定数值列空间外的残差，可能包含噪声、遗漏状态、非线性或数值截断，不能唯一归因。
最低残差投影数学上等价**新增离线无正则线性估计**，不是“0拟合/免费诊断”。
W只用原归档权重核ridge残差；不计算/保存/部署新的参数空间W，不扫描lambda。

固定A列索引`22,23,24,25`（两startG、两hinge），
固定Z列索引`0…21,26,27,28`（22原生state、常数、两lag）。
Z做一次SVD，`A_perp=A-Uz@(Uz.T@A)`，A_perp再做一次SVD。
每套总3次SVD，六套共18次；不是按C/G子组另拟合。
保存A四列raw/conditional能量和均方、逐列保留比例、A_perp全奇异值/秩/Vt方向。
A有两个物理请求通道，hinge是另外两基函数；rank<4可能仅因hinge/请求共线，
不能等同两个关节缺激励或证明动作因果不足。条件投影仅描述输入激励，不学习任务动作控制器。

## 输出与解释

每套原始矩阵不重复复制，保存input hashes、完整IDs及必要新floor/shrink/ridge residual/A_perp原件。
ALL以及K的C400、L的C400/G200分别逐22输出保存floor/shrink能量、
`2*sum(floor*shrink)`交叉项、总重构能量、saved ridge能量、残差恒等式max discrepancy。
全样本floor/shrink理论正交；C/G子组不假定正交，交叉项不可省略。
数值秩截断可令重构与原ridge有小差异，报告全部差异，不据阈值追认科学门。
肩/肘q/v标记为科学关注列，其他18输出完整保留；各输出单位明确，不合计不同单位成方法优势。
列尺度只逐列描述及同物理列跨K/L比较；混合单位谱只是本固定单位下的数值几何。
C/G均为训练数据诊断，不能作泛化排名或单一覆盖因果；增样本/分布/相对正则/PD任务采样同时改变。

仅按连续数值讨论ridge收缩、列空间外残差、条件动作变化及C/G混合权衡；解释可以并存。
本轮不自动选择seed、lambda、特征或新候选。K/L/D旧失败门不变，
scientific_adoption/C4/C5=false，没有替代科学pass门。

## 首次执行和成本

要求新output和canonical脚本/protocol的精确clean冻结commit，无helper控制器导入。
按每个真实attempt/return记录SVD、矩阵乘法/输入输出标量、投影估计和标签用途。
六套native估计使用66,000 scalar标签（K26,400＋L39,600），
来自39,600已用转移标签的重复计算；六套命令条件投影另用12,000 scalar响应。
这两种新增离线估计用途分列，不能写“0拟合”。归档ridge前向仅核训练残差，另计66,000输出标量。
预计18 SVD、36矩阵乘法；rank相关乘法输出与逻辑乘/加数量按真实形状记录，
这些是代数操作计数，不假装测量硬件FLOPs。新physics/RLS/MPC/递归预测为0。
保存run.json、diagnostics.json、manifest.json；partial输出和首异常不覆盖，input/source未返回状态为unknown。
实际失败不重试、不补跑。准备的必要新合成检查须另经静态审查授权；不重跑旧检查或人工ridge。

```powershell
python scripts/diagnose_guard_design_geometry.py --repo . --source-commit SOURCE_COMMIT --output NEW_OUTPUT
```
