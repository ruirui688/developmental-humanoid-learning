# IV1：连续原生动作的工具变量响应辨识

状态：**事前有限协议，尚未执行。** 只开放本次动作响应辨识与独立预测，不开放控制实验。协议、runner、最小必要新检查和源码依赖先冻结到干净提交并推送，再首次执行一次。失败保留，不补跑、改 seed、扫描正则或放宽原门。持续目标 active，C4及C5–C7未验收。

## 问题与范围

PAR1 的相同仿真状态有限动作响应只提供描述性诊断；其完整状态复制是额外仿真资源，不能作为本轮免费训练数据。本候选只检验：在连续新轨迹中加入事前随机请求，用条件中心化的有效动作特征估计响应，能否修订冻结模型的动作系数并通过原独立预测门。它不证明非动作模型正确、工具变量足够强、预测改进能转化为控制优势，或机器人能像动物快速获得完整运动技能。

固定开发 seed **8101、8102、8103** 已使用，不能称新最终留出。初始化唯一来源为 EF1B 的 `results/cpu_validation/2026-10-12_equilibrium_feedforward_control/raw/models.json`：**60,924 bytes / SHA256 `3cfbd871c275a8f5d8a07615a239ee9e8192b5e93dcf35104cf61a01f6a6a992`**。EF1B 来源提交 `f9f500706364aab32bd18047266d4b06358e4473`，模型形成源 FR4A 为 `f4fca3f4236acddc92a25c6707f9c29150ee3ca6`。只恢复各 seed 的原 `cold` 与 `oldlearned`，不重拟合旧数据，不读取 PAR1 fork/opaque 数据、旧 trace 或旧预测。

公开身体、自由 root/仰卧安装、理想感觉、基础保护、PD64/Kd4、任务目标及刺激规则均是披露先验。CPU/NumPy/MuJoCo；无 GPU、PPO、外部任务教师、预训练任务策略或真机。部署输入仍只有两轴原生 q/v、当前已知请求和公开 guard；root、接触力、动能、真实动力学仅作工程资格和离线记录，不进入模型或动作选择。

## 完整新物理人口

每 seed 依次完成一条标识 trial 和一条独立预测 trial，共 **6 个事前 trial 槽**。任一 trial 停止即停止全批，不尝试剩余 seed/trial；计划人口及未执行状态必须保存。

保持原自由 root 八轴资产、reset、重力、接触、限位、每次2ms物理和反馈；只对左臂两轴发请求，其余六轴请求零。每 trial fresh 构造并 reset 一次，zero prefix 恰好1000步，constructor/reset/forward另计。qref 取合法 prefix 第1000个完整端点两轴 q，公开范围和 qref 必须与本 seed 冻结模型精确相同，不用旧 qref 覆盖新身体状态。每个实际端点先保存付费记录，再接触审计和原 StudyAbort；禁止停止端点进入 moment 或预测。

### 标识：每 seed 1000 zero + 2000 active

active A/B 各1000步，当前目标分别为 `qref + direction*.04`、`qref + direction*.08` rad。direction 按正/负公开关节余量选择较大一侧，平局选正；目标满足原公开合法性，不预览下一阶段目标。

每 active 步先从当前 q/v、当前目标计算 `raw_PD = 64*(target-q)-4*v`，公共 base 唯一 clip 为 **±.375 Nm**。每 seed 唯一生成器为 `Generator(PCG64(seed+100000))`；每步按 axis0/axis1 顺序各取独立等概率符号，扰动各为 **±.125 Nm**，最终已知请求为 `base + perturbation`。全部四种符号组合原始请求均合法于±.5Nm；不再 clip 扰动、不换符号、不按感觉选剂量。实际采样 API 和顺序由冻结源码绑定并在配置保存，不能按结果重置 RNG。

每步的公共角度 guard 为 `G(q,u)`：下限+.03rad附近阻断负请求，上限−.03rad附近阻断正请求，其他保持原请求；signed hinge 为 `h(G)=sign(G)*max(abs(G)-.25,0)`。所有组合在同一当前原生 q 和当前公共 base 上计算，无物理 fork、状态复制或额外动作试探。

每 trial 的 prefix/A/B 各1000完整阶段均须至少有一个 `left_arm-floor` 正端点，全部接触与努力人口保留。完整物理、连续转移、原保护、接触资格及冻结身份通过后才 fit；接触共现不证明持续承重、安全或学习收益，不按接触结果挑选转移。

## 唯一 moment 与一次 fit

原九列顺序保持 `x=(v0,v1,qrel0,qrel1,G0,G1,hG0,hG1,1)`。oldlearned 的 `theta[:,[0,1,2,3,8]]` 共 **10个非动作系数冻结**。对每个合法连续 active 转移，用当前实际 q/v 算冻结非动作 head：

`n = theta[:,[0,1,2,3,8]] @ (v0,v1,qrel0,qrel1,1)`，

`response_label = native_next_v - n`。

动作特征 `phi=(G0,G1,hG0,hG1)`。从当前 q/base 的全部四个合法扰动组合计算各自 phi，并作等权均值 `mean_phi`；实际已抽符号的工具为 **`z=phi_actual-mean_phi`**。不使用真实执行力矩替代已知请求，不按标签重新中心化，不用未来状态、其他关节或接触选择特征。

每 seed 按原连续时间顺序只积累：

`M = Σ outer(z, phi_actual)`，形状4×4；

`Y = Σ outer(z, native_next_v - frozen_nonaction_head)`，形状4×2。

样本数必须恰好2000。只调用一次 **`np.linalg.lstsq(M,Y,rcond=128*float64_eps)`**，两 head 共同 fit。返回解形状4×2，转置替换 corrected 的 **`theta[:,4:8]` 共8个动作系数**；其余10个系数逐项不变。M/Y、解、返回 rank、singular values、原 residuals 和所有 attempted/returned/failed fit 都保存。rank 必须为4，所有所需值有限；square system 的空 residuals 原样保存，不能补为“零误差”。失败立即全批停止，不加 ridge、补秩、伪逆方案、重权、扫描或重做。

`corrected` 从本 seed 的冻结 oldlearned 拷贝形成；cold/oldlearned 参数指纹始终不变。corrected 记录初始 oldlearned 身份、8个替换值、10个不变值与新冻结指纹，fit 后禁止再更新。原 `coupled_hinge9`、公开 guard/hinge、qrel、原2ms Euler位置积分和闭合递推不变；theta 已是2ms下一速度系数，不额外乘 dt。

该 moment 方法依赖随机化和条件中心化的识别假设。固定非动作 head、有限刺激及未闭合的身体状态仍可能带来偏差；rank4不证明强工具、泛化或因果动力学正确。保存不利结果，不追加传感、标签或模型维度。

## 独立预测：原 FR4A 人口与原门

每 seed 在独立 fresh **1000 zero + 1000 active** 上同时评估 cold/oldlearned/corrected，0新更新。保持[原 FR4A 协议](PD_ANCHOR_PAIR_LEARNING_PROTOCOL.md)的五个200微步块：方向 `(1,0)/(0,1)/(1,1)/(1,-1)/(1,1)`，幅度 `.125/.25/.375/.5/.375` Nm；10微步 slot1正、slot9反，其余零。PD目标为 fresh qref：先 clip 公共PD到±.5，加固定 pulse，再 clip最终±.5；不沿用标识的±.375 base。prefix/active完整阶段各至少一个 left_arm-floor 正端点，原工程资格保持。

origin为 active0、10、20…；未来保存 final requests 仅作离线条件输入，未来 actual q/v 只评分，不注入递推。三模型共享同一新轨迹与人口，不选择有限子集、不重算旧轨迹。

| H微步 | 时距 | origin/seed/model |
|---|---:|---:|
| 1 | 2ms | 100 |
| 10 | 20ms | 100 |
| 20 | 40ms | 99 |
| 50 | 100ms | 96 |
| 150 | 300ms | 86 |

原 **cold→corrected** 门保持：H10v/H150q每 seed两轴严格改善，各轴三 seed原RMSE算术均值改善≥20%；H150v及H20/H50 q/v每 seed两轴不劣。H1q/v、H10q全部报告，不事后加门。完整所需物理、接触、连续 origin、finite和冻结身份是前置；baseline0的百分比不可用，不补零、不删失败 seed、不排名partial人口。

oldlearned 在所有 H/seed/轴/q/v 的结果及相对 cold、corrected 的全部不利变化都报告，不以三模型里最好者替代固定 corrected 门。此诊断不增加 oldlearned 成功门，不把历史成功追认成本批成功。预测不通过，禁止进入 corrected 控制；即便通过也只形成开发预测证据，后续完整控制须另行冻结，不自动开放 controller。原C4 20%模型贡献、5%强PD及1.05努力门均未执行或改变。

## 停止与费用

保持原底层终止、非有限/异常、active两轴相对 qref **.12rad** 或速度 **1rad/s** StudyAbort与每2ms检查。标识、评估、接触审计、identity、moment/fit或预测任一停止/技术异常立即保存首错并停止全批。失败写盘或复原等次错误附首错，不替换它。保留全部付费完整/部分端点、未执行人口与负结论，不用提前停止宣称样本节省；准备失败也单独归档。

| 正式固定人口/上限 | 全批 |
|---|---:|
| fresh trial | 6 |
| 标识 control/substep | 9000/9000 |
| 独立预测 control/substep | 6000/6000 |
| 总 control/substep | 15000/15000 |
| 新原生 label pair / scalar用途 | 6000/12000 |
| moment fit / 替换系数 | 3/24 |
| 原 five-H 条件 pair前向 / velocity head输出 | 187020/374040 |
| RLS更新 / fork / opaque / teacher调用 | 全部0 |

12,000 scalar是新 moment 标签用途，24是保存的替换系数，**均不写成12,000次RLS更新**。旧模型形成费用保持；旧 RLS累计不因新fit归零。当前累计 **514,345 control /2,794,018 substep /125,652 scalar更新**，本批按实际付费新增物理；IV moment/fit另列。

四组合 phi/公共guard/hinge、conditional mean、z、M/Y outer与累加、冻结非动作 head及标签读取、lstsq内核/返回值、全部预测 head/q积分、恢复/指纹、实际 effort/contact、构造/reset/forward、源码/模型/文件IO、准备与必要新检查分别计费。内部未测工作标 unknown，不补零；全部实际requested、guarded与原生actuator effort分列。没有实时或安全收益声明。

## 冻结与保存合同

runner为 `scripts/develop_instrumental_action_response.py`，协议pin在首次执行前冻结，输入模型字节身份与本协议相同。执行要求exact clean source commit，source.zip归档runner、协议及完整环境/模型/原预测helper/资产闭包；不能用当前dirty源码解释旧结果。依赖实际版本、CPU、wall/CPU费用、RNG/seed和完整参数保存；无新增外部依赖或数据。

首次全新 `--output` 目录拒覆盖，原件至少包含 `run.json`、`models.json`、`moments.json`、`source.zip`、`source_trace.jsonl.gz`、`predictions.jsonl.gz`、`first_stdout.log`、`first_stderr.log`。run保存状态、首错、source/runtime/config/cost、6个完整事前trial槽、逐seed metrics、接触/实际努力与模型指纹；models保存cold/oldlearned/corrected原生snapshot；moments保存逐seed M/Y/sample count及原lstsq输出。JSONL逐端点/标签/预测人口、所有停止/NA/未执行及实际IO保留，最终schema由冻结runner绑定。不覆盖旧实验、不重跑旧数学或audit。

`scientific_adoption`、`old_free_root_C4_validation`、`c4_scientific_validation`、`c4_contact_scientific_validation`、`c5_scientific_dependency_released`全false。首次完整或停止结果作一次新保存轻核，报告全部限制，检查、提交、推送后继续active目标；本候选失败不通过无限重复取得漂亮结果，局部预测门不代表C4或真机成功。
