# IV2：固定动作响应后的原生状态 head 一致化

状态：**事前有限协议，尚未执行。** 只开放下述一个离线状态 head 拟合和新开发预测，不开放 controller。协议、源码、依赖闭包、输入 pin 与必要新检查先冻结到干净提交并推送，再首次执行一次。保留首失败，不补跑、增数据、扫描、改特征或放宽原门；持续目标 active，C4及C5–C7未验收。

## 问题与唯一来源

IV1 已完整执行，但原独立预测全门未通过。本候选只检验一个假设：保持 IV1 估计的动作响应不变，用同一批合法原生转移重拟合其余状态项，是否形成更一致的局部预测模型。它不认定旧非动作 head 是唯一原因，不证明身体状态已闭合、工具变量正确或控制必有收益。IV1 的全部不利结果和旧门保持；PAR1 fork、旧预测轨迹和特权状态不进入拟合。

唯一来源为已归档 **IV1 canonical结果 raw/** 的三个原件，实际路径由冻结 runner manifest 明列，字节身份不能由路径或当前HEAD替代：

| 原件 | bytes | SHA256 |
|---|---:|---|
| `run.json` | 875053 | `d8531ce2a63819451ac0a294b28c1cf60a5ffd376945cd9ea3c383a3ded354f5` |
| `models.json` | 15911 | `923f73ffea0de6f200204e0961134297a50abe128df840eb1f872505e6fc7756` |
| `source_trace.jsonl.gz` | 15282107 | `c2ded7e3a54fc74befb0cea7eba17bf6b65dd2ac6e3562c3d40f4900abc354a6` |

来源执行提交 **`d7eb8508f2872e24212d7e3580951c7c44fe8228`**；来源保存轻核27项通过只绑定既有证据，不重跑该检查、原预测门或旧数学。上述 gzip pin 是**压缩原件**身份，不能与 run 的 decoded JSONL身份混用。

恢复各 seed 的 cold、oldlearned 和 IV1 冻结 snapshot；IV1是原 `corrected` 的本批报告名。新模型名为 `newmatched`，从本 seed IV1拷贝形成。所有原模型保持，不按结果选择初始化。

## 离线人口与信息边界

固定开发 seed **8101、8102、8103**。只取 IV1 source_trace **top-level、完整、合法的 identification active 行**，每 seed 的原 active index0…1999恰好2000个，`(seed,index)`唯一且连续，上一行端点 q/v与下一行起点精确一致。不得重复计入 nested paid endpoint、annotation、prefix或 prediction 行；不得补零、补样本、跳过错误行或从旧预测/PAR1 fork取得标签。

先核三个来源 pin、run completed身份、完整标识人口及原冻结模型/guard/qref/range/2ms身份，再使用对应合法转移。任何缺失、重复、停止、非法请求、非有限或连续性/来源不符立即停止全批，保存已读数据与费用，不 fit部分人口。原源接触、努力及工程资格只读取其保存字段，不重新计算旧接触或旧评分。

模型仍只消费原生两轴 q/v、已知请求、公开关节范围与角度 guard。真实执行力矩、root、IMU、其他关节、接触力、动能或隐藏动力学不进入回归、特征选择和新动作。公开身体、仰卧/free-root域、理想感觉、基础保护、PD64/Kd4、目标与刺激均为需披露先验；无 GPU、PPO、教师、任务预训练、fork/opaque 或真机。

## 唯一状态拟合

固定 IV1的 `theta[:,4:8]` **8个动作系数**；已知请求按原公开角度 guard映射到 G，signed hinge保持 `h(G)=sign(G)*max(abs(G)-.25,0)`。对每条合法连续源转移：

`psi = (v0,v1,qrel0,qrel1,1)`；

`y = native_next_v - fixed_action8 @ (G0,G1,hG0,hG1)`。

每 seed构造 **Psi形状2000×5、Y形状2000×2**，不中心化、归一化、增二次项或追加 lag。只调用一次 **`np.linalg.lstsq(Psi,Y,rcond=128*float64_eps)`**，两 head共同 fit；返回解5×2，转置写入 `theta[:,[0,1,2,3,8]]` **10个非动作系数**。rank必须为5，输入、解及所需返回值有限，否则立即停止全批；无 ridge、补秩、伪造 gradient、替代解或扫描。

Psi/Y、合法native fit记录、来源身份、sample count、解、rank、singular values、原RSS和每次 attempted/returned/failed fit保存；空数组原样保存，不补“零误差”。IV1 action8逐项及其float64字节精确不变，cold/oldlearned/IV1指纹始终不变，newmatched记录初始/新冻结指纹。fit后全部冻结，不RLS、不在线更新。原九列、coupled_hinge9、qref、guard/hinge、2ms下一速度语义和原Euler位置积分均不变，不额外乘dt。

本批只重用已付原生标签：**6000对 /12000 scalar label用途，3次共同solve /30个新保存系数**。没有新的训练物理或独特训练标签；新预测轨迹不能再用来 refit。IV1独特新标签12000、3fit/24动作系数与本批reuse12000、3fit/30状态系数分开记账，不能写成RLS提交。

## 新开发预测人口

每 seed一条 fresh **1000 zero prefix +1000 active**，共3条新预测trial、**6000 control /6000子步**；cold/oldlearned/IV1/newmatched在同一新轨迹上预测。原自由root八轴身体、reset、限位、每2ms反馈/物理、其余六轴请求零和原底层保护保持。

qref取prefix第1000个合法完整端点，公共范围/qref与对应四个冻结模型精确匹配，不用保存qref覆盖fresh状态。预测目标为当前fresh qref；公共PD先 `clip(64*(target-q)-4*v,±.5)`，加事前pulse再clip最终±.5。不用模型选择动作，不读取未来目标。

保持原五个200微步块方向 `(1,0)/(0,1)/(1,1)/(1,-1)/(1,1)`、幅度 `.125/.25/.375/.5/.375` Nm；**仅将时相固定改为slot3正、slot13反，各10微步，其余零**。这是改变probe时相的新开发预测；seed已使用，不称新heldout、单一因果消融或原IV1成功复验。不扫描slot、符号、目标或幅度。

每trial prefix/active完整1000步阶段均须至少一个left_arm-floor正端点；原保护/接触资格及完整努力记录不变，接触只资格/离线记录，不筛origin或指导控制。正接触共现不证明承重或安全收益。

origin为active0、10…，未来保存final requests仅作离线条件输入，未来actual q/v只评分、不注入闭合递推。原five-H完整人口如下：

| H微步 | 时距 | origin/seed/model |
|---|---:|---:|
| 1 | 2ms | 100 |
| 10 | 20ms | 100 |
| 20 | 40ms | 99 |
| 50 | 100ms | 96 |
| 150 | 300ms | 86 |

全批 **5772预测记录、249360条件pair前向 /498720 velocity-head输出**。全部H/seed/轴/q/v及四模型差异报告，不择优模型、不pool或partial排名。

## 不变的原门与全批停止

正式门仅 **cold→newmatched**：H10v/H150q每seed两轴严格改善，各轴三seed原RMSE算术均值改善≥20%；H150v及H20/H50 q/v每seed两轴不劣。H1q/v、H10q仅全部报告；oldlearned、IV1与newmatched的全部不利变化同样公开，不追加其成功门或改用最佳者。

完整物理、接触域资格、来源/冻结指纹、origin、finite是可评前置。baseline0的百分比不可用，不补零、不删seed；任何必要条件或科学门失败，本候选不得进入controller。原C4的20%模型贡献、5%强PD及1.05努力门均未执行或改变；预测通过也不自动打开控制，后续仍需独立冻结完整控制。

保持原环境终止、非有限/异常和active相对qref位置 **.12rad**、速度 **1rad/s** StudyAbort及每2ms检查。任一来源/解析、fit、fresh物理、接触审计、预测或身份异常立即记录首错并停止全批，不执行剩余seed/trial/预测。保留停止前实际付费完整/部分记录、所有计划槽和not_executed；次写盘错误附首错，不替换首错。不能以早停证明节省样本，不能把部分RMSE排成方法优势。

## 费用、冻结与交付

当前物理累计 **529345 control /2809018 substep**，历史RLS为 **125652 scalar更新**，全部保持。IV2按实际新增预测物理累计；离线复用标签/solve/系数独立计账，0新RLS、0训练物理、0任务教师、0fork/opaque、0controller。既有来源fit费用不因新候选归零。

实际source读取/hash/解压/JSON解析、顶层选择与连续性核验、native label访问、G/h/固定action前向、Psi/Y构造、lstsq内核及输出、全部新预测和q积分、模型恢复/指纹、构造/reset/forward、每个付费端点、接触/原生actuator努力与requested/guarded努力、准备/必要新检查及输出IO分别计费；未知内部工作标unknown，不补零。新训练样本、复用label用途、预测评分用途分列。

生产路径为 `src/developmental_physics/consistent_action_state_model.py`、`scripts/refit_instrumental_state.py` 与本协议。runner在首次执行前绑定protocol pin和三个输入pin，要求exact clean source commit；source.zip归档模型/runner/协议及完整环境、资产、原five-H评分helper闭包。保存实际Python/NumPy/MuJoCo版本、CPU、wall/CPU和全部固定配置；不增加外部依赖或数据。

首次全新目录拒覆盖，原件为 `run.json`、`models.json`、`moments.json`、`metrics.json`、`source.zip`、`source_trace.jsonl.gz`、`predictions.jsonl.gz`、`first_stdout.log`、`first_stderr.log`。run保存3个事前fit槽、3个fresh预测trial槽、5772个预测槽、首错、来源、模型指纹、所有费用/努力/接触与未执行人口；moments保存逐seed Psi/Y与原lstsq输出、fixed action字节及来源。metrics只保存同次评分，不重复评分。native fit记录及完整预测原件由冻结schema绑定，不覆盖或修改IV1。

`scientific_adoption`、`old_free_root_C4_validation`、`c4_scientific_validation`、`c4_contact_scientific_validation`、`c5_scientific_dependency_released`全false。首次结果只做必要的新保存轻核，不重算旧门/旧数学或旧审计；报告完整负结果与限制，检查、提交和推送后继续active目标。局部预测或本报告不能代表C4、C5–C7或真机成功。
