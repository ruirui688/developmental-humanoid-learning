# IV2D：固定保存模型的残差与坐标覆盖诊断

状态：**事前有限协议，尚未执行。** 仅对下述IV2原件做一次固定代数与描述统计；不打开训练或controller。统计、人口、预算、源码与protocol pin先冻结到干净提交并推送，再首次执行一次。不按结果增加统计、选子集、扫描或重跑。

## 问题与来源边界

IV2已完整执行，原独立预测全门false。IV2D区分三个保存事实：训练内状态head残差、fresh一步误差，以及较长递推的误差与坐标出箱情况。它不识别IV2失败的唯一原因，不证明状态闭合、训练覆盖充分或控制优势；坐标共现不是因果。完整负结果、原门与C4/C5–C7未验收保持，持续目标active。

唯一输入根为 `results/cpu_validation/2026-10-12_consistent_action_state/raw`，来源执行提交 **`d8491b2e0f8b3bae649b8bf9a297bebba7f76270`**：

| 原件 | bytes | SHA256 |
|---|---:|---|
| `run.json` | 1145452 | `a6fd68bb909ac8d8607986aeb55918d76dce18b51f8a0bbcd2d93b8caef2a0ec` |
| `models.json` | 21758 | `96e94bc63311262878114354e1fb4f084564e5116cf14435ee47936415176dcd` |
| `moments.json` | 1425018 | `a199bb517cafc059bfcf6af23b9dba258f4d4bcf31787c363ea255ebced7c2ea` |
| `predictions.jsonl.gz` | 10936879 | `de32524abd8f5b8a7f45d6dbc92158143c67b5fe05893656401c38dddfd58685` |

gzip pin为压缩原件身份，不与decoded JSONL hash混比。**不读取source_trace、IV1 raw、PAR1 fork、旧prediction或其他历史文件**；不重跑既有保存核验、旧科学门或旧数学。仅核本次必要来源/完整人口/finite/模型身份，原工程资格和RMSE读取保存字段。

## 1. 全训练内状态head残差

固定seed **8101、8102、8103**。每seed使用全部已存 **Psi 2000×5、Y 2000×2**，不删除、增权或分割行。Psi顺序为 `(v0,v1,qrel0,qrel1,1)`；Y已扣除固定IV1 action8。只比较 **IV1、newmatched** 的非动作列 `[0,1,2,3,8]`：

`state_prediction = Psi @ theta[:,[0,1,2,3,8]].T`；

`state_error = state_prediction - saved_Y`。

每seed/model恰好一次batch matmul，共 **6 matmul /24000 velocity-head scalar输出 /24000 reused Y scalar label用途**。IV1和newmatched action8须逐项身份一致；本误差是同一条件标签下的状态block残差，不将cold/oldlearned的statehead对该Y之差称完整模型误差。不再计算G/h、不重新形成原训练标签、不fit、不调用model.predict。

每seed/model/轴固定报告全部2000误差的 **bias、MAE、RMSE、population std、maxabs**。bias为有符号均值，MAE为绝对值均值，RMSE为平方均值开根，population std使用ddof0，maxabs为最大绝对值。训练内RMSE是本次新残差统计，不代表泛化；所有head、seed和不利比较同样保存，不添加成功阈值或“最好模型”。

## 2. 全fresh保存误差

读取全部 **5772** 完整保存prediction记录：3seed×4模型 `cold/oldlearned/IV1/newmatched` ×原 `H1/10/20/50/150` 人口，各H origin/seed/model为 **100/100/99/96/86**，stride10。不重新forward、形成endpoint误差或重算已存fresh RMSE/原门。

对保存的两轴 `q_error_rad` 与 `v_error_rad_s`，每seed/model/H固定报告 **bias、MAE、population std、maxabs**；H1是同一统计中的H1行，不另算一次，不遗漏其全部100 origins。较长H的统计只描述其保存误差，人口大小随H不同，不称误差变化的因果分解或同一初态因果比较。原fresh RMSE只从run逐项转录，缺失不重算；原门false直接保存，不重新判门。

符号一律为 `predicted-actual`，不改成绝对误差后解释方向。全5772记录对应 **23088 saved endpoint error scalar用途**；q单位rad、v单位rad/s分开报告，不合并不同单位或pool种子。无bootstrap、相关扫描、SVD/逆解或参数选择。

## 3. 唯一坐标箱覆盖

每seed只用全部2000个训练Psi的前四列形成闭箱 `[min_j,max_j]`，顺序为 `(v0,v1,qrel0,qrel1)`。不估训练RMS、分位数、凸包、距离模型或新有效域门。

两类固定population：

1. **Native H1起点：** 每seed全部100 origins，用cold H1的已存native `model_input q/v`作为共同来源，四模型对应原生起点须一致；去除跨模型重复后恰好 **300点 /1200 scalar坐标用途**。不把cold预测值当native。
2. **递推输入：** 四模型各H的全部记录，每slot输入为已存native起点，再加其已存预测path前H−1个端点；恰好H个输入，不把最终第H端点多计。共 **249360点 /997440 scalar坐标用途**。这些包含重复的有条件计算点，不称独特物理状态或新环境样本。只读取路径，不执行递推。

qrel由对应seed冻结qref扣除；模型qref身份须一致。每类/seed，以及递推每seed/model/H，固定报告四列各自out-of-box count、任意列出箱point count和各列最大绝对越界量：

`outside_j = x_j < min_j or x_j > max_j`；

`exceedance_j = max(min_j-x_j, x_j-max_j, 0)`。

边界算在箱内，零宽列保持零宽，不补epsilon、除以宽度或调尺度。v与q越界量分别保留原单位，不做混合max。全部点保留，不按箱内/箱外选取更好误差、不增加错误条件统计。坐标箱只是有限描述；箱内不证明支持域、动作识别或泛化，出箱不证明失败由覆盖导致。

## 固定预算、停止与费用

| 正式人口/运算 | 全批固定上限 |
|---|---:|
| 输入原件 | 4 |
| 训练Psi/Y行 | 6000 |
| 保存stateblock batch matmul | 6 |
| statehead scalar输出 /reused Y用途 | 24000/24000 |
| 保存prediction记录 /endpoint error scalar用途 | 5772/23088 |
| native H1点 /坐标scalar用途 | 300/1200 |
| 保存递推输入点 /坐标scalar用途 | 249360/997440 |
| fit/RLS/model.predict/新物理/fork/teacher/原门重算 | 全部0 |

系数复用、Psi访问与matmul内核、残差/统计/箱比较、qrel减法、已存RMSE转录、源文件读取/hash/gzip解压/JSON、模型身份/人口、输出IO、准备和必要新检查分别计账。24000是对既有Y的两模型复用用途，不是新独特标签或RLS提交；997440也不是新采样。未知内部运算与IO标unknown，不补零，物理与RLS累计不增加。

四输入pin、source completed身份、全部seed/model/H/origin/shape、finite、路径长度或冻结身份任何异常即记录首错并停止全批；不跳记录、补数组或对部分人口排名。保留已解码/已计算部分、全部计划population和未执行状态；次写盘错误附首错。没有新科学成功门；技术完成只说明本保存诊断可交付，不追认IV2或C4。

## 冻结与交付

生产runner为 `scripts/diagnose_consistent_model_residual.py`，必要新准备检查为 `external/new_consistent_residual_checks_once.py`。执行前protocol与输入pin冻结，exact clean source commit及runner/协议/全部实际代数依赖保存至source.zip；新检查只验证新增统计/人口/边界，不能重跑旧fit、物理或科学评分。

首次全新输出目录拒覆盖。保存run/source、首stdout/stderr、完整训练残差/5772记录身份/覆盖人口与全部固定摘要、模型指纹、config/seed、依赖版本、CPU/wall/CPU及实际IO；具体原件名/schema由冻结runner明列。保留first failure、负结果、未执行population和unknown费用，不追加拟合或控制请求。

`scientific_adoption`、`old_free_root_C4_validation`、`c4_scientific_validation`、`c4_contact_scientific_validation`、`c5_scientific_dependency_released`全false，`control_candidate_opened`为false。首次保存轻核、完整报告、提交和推送后继续active目标；该诊断只支持一次有边界的下一判断，不自动授权训练、控制或结果筛选。
