# CFD1：整trial交叉拟合的局部动作差分预测

状态：**事前有限协议，尚未执行。** 只开放一次已付原生数据的差分拟合与开发预测，0新物理/RLS/controller。协议、输入pin、实际纯代码闭包及必要新检查先冻结到干净提交并推送，再首次执行一次。失败关闭本候选，不补跑、scan或改门；持续目标active，C4及C5–C7未验收。

## 唯一变化与输入身份

[CF1负结果](CAUSAL_INCREMENTAL_PREDICTION_RESULTS.md)关闭旧IV1 action8在因果增量预测中的用途及CF2控制。本候选保留CF1公共guard/hinge、因果记忆、2ms积分及完整评估人口，只改动作B的拟合目标：**相邻速度增量差对应相邻动作特征差**。它不恢复IV1/IV2/IV3状态头，不调整B比例/滤波/gain/lag或采样seed；差分消去局部近似不变漂移是待检验假设，不能从CF1失败认定执行器延迟或动作因果。

唯一canonical根 `results/cpu_validation/2026-10-12_causal_incremental_prediction/raw`，来源 **`bb7e4b8fa744b4ec7c76855cfe6730ebbca26421`**；pin采用[CF1交付原件身份](../results/cpu_validation/2026-10-12_causal_incremental_prediction/delivery_manifest.json)：

| 原件 | bytes | SHA256 |
|---|---:|---|
| `run.json` | 813956 | `1dd1a1c329c268d095f90bb49bb95a6e85bbc3fa1c918c794a3cfecd1329b19b` |
| `models.json` | 9975 | `e8948ddc1f88c3552912fae1f6741528796c17c41dd504436988c1d7b1038b56` |
| `native_source.jsonl.gz` | 884195 | `63f2b0cf315353e55a3ef93893a65f78db14ae0939a91c2852e0c16cd521b530` |

gzip pin为压缩原件身份。只读这三个输入，不读IV3大trace、CF1旧预测流、嵌套fit数据或跨历史原件。固定seed **8101/8102/8103**，每seed完整 **1000 zero prefix+2000 active**。一次解码9000 compact原生区间，核run来源/完整状态/原接触资格、流身份、顺序、同trial连续q/v、权限及before/request/after的单区间合同；全部资格后才能拟合。缺行/历史或失败不能补零、重排或删origin。

请求属于当前before状态至after端点的2ms完整区间，上一请求属于紧邻前一区间；按此固定时间合同构造差分，不由误差选择时移，不用实际执行力矩替换请求。模型只消费肩/肘q/v、已知请求及公开范围，其他关节、root、接触、IMU、隐藏动力学和actuator实际力矩不进入模型。公开范围必须三seed float64字节精确共享，否则失败。

## 三个独立map的一次OLS

两轴肩/肘。定义 `delta_v_t=next_v_t-v_t`；公共 `phi_t=(G0,G1,h0,h1)` 使用当前before q和已知请求，沿用下限+.03/上限−.03rad角度guard与 `h(G)=sign(G)*max(abs(G)-.25,0)`。

对连续active **t=1..1999**，只构造：

`X_t=phi_t-phi_(t-1)`

`Y_t=delta_v_t-delta_v_(t-1)`。

每个评估seed s只用**另外两个seed的整个trial**构造其训练X/Y，按seed递增、active递增拼接，形状 **X3998×4、Y3998×2**。不得随机分点、在自身trial上拟合或选择窗口。允许在资格解码阶段读取全部原生端点；每个map的设计/Y构造及solve严格不消费自身评估seed数据。其他map会把该trial用于训练，因此不能声称全局评估标签未用于拟合。

每map仅一次 **`np.linalg.lstsq(X,Y,rcond=None)`**，NumPy实际版本锁定并保存；rank必须4，输入、解、返回rank/singular/RSS及必要输出有限。解4×2转置成该map的2×4 B，共三solve/**24个B系数**。`rcond=None`使用锁定runtime默认，不能另设128eps、截断谱或按结果修阈值；rank4仅是拟合资格，不证明谱稳定、泛化或因果识别。无截距、ridge、尺度估计、权重、补秩、正则/feature/solver扫描或fallback。

**三个map的完整资格与一次fit全部完成，才开始任何候选预测或排名。** 保存每map训练seed/排除seed、全部索引、X/Y与输入来源、solve返回值/成本及首失败。成功B随后冻结，0在线更新。完整拟合重复使用 **23988 scalar标签**，唯一差分目标 **11994 scalar**；这是既有端点形成的离线拟合用途，不是新采集标签或RLS更新。

## 固定因果预测与cold转录

`CFDlearn`直接使用CF1同一个纯 `CausalIncrementalPairModel` 和新map B：

`f_B(q,u)=B@phi(q,u)`；

`d_t=(v_t-v_(t-1))-f_B(q_(t-1),u_(t-1))`；

`vhat_(t+1)=v_t+d_t+f_B(q_t,u_t)`；

`qhat_(t+1)=q_t+.002*vhat_(t+1)`。

B已是2ms速度增量响应，不再乘dt。origin的真实history来自同trial紧邻完整区间，active0必须取prefix区间999；后续只能用自身预测q/v及已知请求更新memory。未来真实q/v只评分，不能teacher force、重估漂移或clip预测状态。已知未来请求仅是离线条件，不证明部署时有未来反馈预览；H150全部报告，但不开放300ms规划。

为避免重算旧cold，**CF1cold每seed/七H/qv/两轴共84个原RMSE scalar及保存H1v三seed均值2个scalar只直接转录**。禁止cold前向、cold RMSE/均值/旧门重算。转录前必须绑定CF1完成状态、CFcold固定B=`[[.002,0,0,0],[0,.002,0,0]]`、公开范围与record/指纹、相同原生流、全部cold origin/H/available人口，以及原评分语义。

同公式身份同时绑定当前冻结源码和CF1 `run.source.files`：

| 共享纯源码 | bytes | SHA256 |
|---|---:|---|
| `src/developmental_physics/causal_incremental_pair_model.py` | 10782 | `e719bf097d5f16624f504d794ad6c1ad1b170306120fdb5baedb4868432d0619` |
| `src/developmental_physics/instrumental_action_model.py` | 9302 | `cb0d3f6314682553fabe2f37b56764bd8098551221e14cbe8f3aece14b014c51` |

任一公式、流、权限、积分、范围或人口不同则整个cold转录不可用，全批失败，不以新跑cold补救。不得用CF1learn或旧完整模型替代固定CFDlearn。

## 完整人口与唯一新门

每seed、每H的origin仍严格为 **`range(0,2000-H+1,20)`**；H=`(1,2,5,10,20,50,150)`，各H为 **100/100/100/100/100/98/93**，H20必须含origin1980。起点为对应active区间before q/v，末端为第H区间after q/v，known requests完整同序。

只新预测CFDlearn：**2073记录/67950 pair/135900 velocity heads**，**8292 scalar末端评分标签用途/42新RMSE向量**。全部三seed、七H、q/v、两轴原RMSE及不利差异报告；输入/fit/每条路径/评分全体完整有限是判门前置，不排名partial人口。

唯一新门与CF1事前短时门同标准：CFcold→CFDlearn **H1v每seed两轴严格改善**；各轴三seed原RMSE算术均值改善≥20%，cold均值直接转录，learn均值新算。改善为 `(copied_mean_cold-new_mean_learn)/copied_mean_cold`，不平均逐seed百分比；cold分母0则不可用，不能判通过。**H2/H5 q/v每seed两轴不劣**。H1q及其余H仅完整报告，不事后加门或用其替代失败项。

这是整trial交叉拟合的**已见开发**，不是新最终留出、独立物理复验、随机动作因果证明或完整控制验收。失败关闭本候选；通过也仅支持另行冻结完整反馈控制。CF1、旧长时预测门及旧控制入口不追认；C4贡献20%、强PD优势5%、1.05实际努力及新最终留出要求不变。

## 首错、费用与交付

新物理/构造reset/teacher/fork/RLS均0，正式物理累计保持 **544345控制/2824018子步**，历史 **125652 scalar RLS**不变。既有IV1校准、IV3采集/OLS、CF1预测费用保持，不能把已付原生轨迹或cold分数称免费。新fit标签重复/唯一用途、差分/guard/hinge、三solve内核及系数、冻结模型构造、预测memory/d/积分、42新RMSE、84+2 cold转录、新gate与评分标签、解压/JSON/source与input hash/准备/IO分别计账，未知工作标unknown。

首异常停止全批，保留三map槽、全部2073预测槽、已付fit尝试、所有未执行/失败/不可评项及原首错；次输出错误附加，不覆盖。不得补数据/重跑成功、scan比例/滤波/gain/seed或把早停当效率。输出首次新建拒覆盖，保存run/config/runtime/CPU/wall/CPU、完整X/Y及fit返回、冻结B/指纹、预测与标签原件、cold转录来源、新指标、源码ZIP和首stdio，具体schema由冻结runner明列。

runner为 `scripts/develop_causal_difference_prediction.py`，必要新检查为 `external/new_causal_difference_checks_once.py`。实际source.zip闭包为新runner、本协议及上表两个共享纯module、`src/developmental_physics/__init__.py`，共五文件；不新增模型源码或引入旧runner/物理后端。输入/协议/共享源码pin绑定exact clean source commit，准备记录和首次结果完整归档。

五scientific flags及`control_candidate_opened`全false。首次保存只做一次必要新轻核，报告边界、检查、提交推送后继续active目标；CFD1局部预测不代表C4、C5–C7或真机成功。
