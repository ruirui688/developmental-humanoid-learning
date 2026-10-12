# CF1：局部动作响应与因果反馈增量预测

状态：**事前有限协议，尚未执行。** 只开放一次已付原生轨迹的开发预测，0新物理/fit/RLS/controller。协议、输入pin、实际纯代码闭包及必要新合成检查先冻结到干净提交并推送，再首次执行一次。失败关闭本候选，不补跑、扫描或改门；持续目标active，C4及C5–C7未验收。

## 唯一候选与输入

IV1/IV2/IV3完整状态模型及原预测/控制入口保持关闭。本候选仅提取已有IV1局部动作响应，用上一完整区间的原生反馈估计本步增量；不复活旧状态头、旧残差候选或H150规划。固定2ms更新、原公共guard/hinge和权限是披露先验，不证明漂移稳定、动作因果充分或控制收益。

唯一canonical根为 `results/cpu_validation/2026-10-12_near_reference_identification/raw`，原执行来源提交 **`dec307a49cd6ad883b7f6016b2634dd3730a8d7d`**：

| 原件 | bytes | SHA256 |
|---|---:|---|
| `run.json` | 342682 | `599308e788d9c293d2b9ac53b5d17284a0547b1c8d261840fa02a3b9aaadcc6d` |
| `models.json` | 25865 | `5ff8f01698c0ddc6b3cd92fc61002f7a58f4e214565d0b2d5bf682bc1fe03f52` |
| `source_trace.jsonl.gz` | 9570465 | `6d4b62b70edd19e9f42f6f040215f531ca14c9fe0ee6e8381ee6804c71047d35` |

gzip pin为压缩原件身份。输入必须先通过字节/SHA、来源、三seed完整训练trial、stage/连续性和模型元数据资格。seed固定 **8101/8102/8103**，每seed只接受top-level原生 **1000 zero prefix+2000 active** 完整合法连续行；不得读取嵌套fit samples、moments、旧预测文件或跨历史trace。不补行、重采样或选择成功子集。

`CFlearn`只从对应seed保存的IV1 snapshot提取动作列`[4,5,6,7]`的2×4 action8及公开qref/范围/guard元数据，要求原`coupled_hinge9`顺序、2ms语义和有限值一致。不恢复或使用非动作状态系数，不调用任何旧模型、拟合器或物理环境。`CFcold`的同形B为 `[[.002,0,0,0],[0,.002,0,0]]`，共享相同公开guard/hinge。IV1校准和IV3采集/OLS的已有费用分别披露，不能把已学习action8当作免费冷启动先验；详见[IV1结果](INSTRUMENTAL_ACTION_RESPONSE_RESULTS.md)和[IV3结果](NEAR_REFERENCE_IDENTIFICATION_RESULTS.md)。

## 因果历史及闭合递推

两轴顺序为肩/肘。公共角度guard `G(q,u)` 在下限+.03rad阻断负请求、上限−.03rad阻断正请求；其他保留已知请求。signed hinge为 `h(G)=sign(G)*max(abs(G)-.25,0)`，`phi=(G0,G1,hG0,hG1)`。定义 **`f_B(q,u)=B@phi(q,u)`**，其结果已是2ms速度增量，不再乘dt。

origin时刻t只使用当前原生`q_t/v_t`和**同trial上一完整区间**的`q_(t-1)/v_(t-1)/u_(t-1)`：

`d_t=(v_t-v_(t-1))-f_B(q_(t-1),u_(t-1))`

`vhat_(t+1)=v_t+d_t+f_B(q_t,u_t)`

`qhat_(t+1)=q_t+.002*vhat_(t+1)`。

active0的历史必须来自prefix最后一个合法完整区间，不能补零或跳过该origin。所有真实历史和连续性先核完整；跨seed/trial/reset、缺历史、未完成区间及不一致端点均失败，不重建隐藏状态。只用原生q/v、公开范围及已知请求；真实执行力矩、guarded/actual effort、root、接触、IMU和隐藏动力学不进入模型。

H>1完全使用自身预测的q/v与该路径已知请求；每步用自身`qhat/vhat/u`更新上一段memory，再按同式形成下一步d。真实未来q/v只用于末端评分，不能teacher force、重新估漂移、clip状态、滤波或按误差调增益/残差比例。所有已知未来请求只是离线条件，不等同于控制时可预览未来反馈请求。短时局部结构不保证长时稳定；H150照样报告，但不据此开放300ms规划。

## 唯一完整预测人口与新门

在全部9000原生行和两模型资格通过后，评估两个固定模型的全部路径。每seed/model、每H，origin严格为 **`range(0,2000-H+1,20)`**，H固定 **`(1,2,5,10,20,50,150)`**。起点为该active行before q/v，终点为第H个完整区间的after q/v，所有H段请求保持原值及顺序。

| H | 1 | 2 | 5 | 10 | 20 | 50 | 150 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 每seed/model origins | 100 | 100 | 100 | 100 | 100 | 98 | 93 |

完整人口为 **4146记录、135900 pair预测、271800 velocity-head输出**。准备阶段原手算4140/135780/271560遗漏H20的origin1980，已在执行前纠正；准备manifest保留该设计错误，不能据原小人口截去末origin，也不把它计为实验首失败。

每H/seed/模型/轴报告q/v原RMSE及全部不利差异。唯一新门为 **CFcold→CFlearn**：H1v每seed两轴严格改善，各轴三seed原RMSE算术均值改善≥20%；H2/H5 q/v每seed两轴不劣。均值改善为`(mean_cold-mean_learn)/mean_cold`，不能平均逐seed百分比。cold分母为0时改善不可用，不能判门通过。全部7H均报告；H10/H20/H50/H150及H1q不事后加门或替代失败项。

全部输入、模型身份、4146路径和评分必须完整有限，才可判新门；首失败或partial人口不可排名、不删seed/origin。IV3 run保存的五旧模型、五旧H分数和旧门只转录到独立表；旧人口不同，禁止称匹配比较、计算跨人口改进、重算旧RMSE/门或重新调用旧模型。旧H10v/H150q门失败保持，不以新H1局部门追认旧能力。

这是已见开发轨迹，**不是新留出、独立物理复验或完整控制证据**。新门失败关闭本候选；通过也只支持另行冻结完整反馈控制协议。原C4贡献20%、强PD优势5%、努力1.05门及新最终留出要求不变。

## 计账、首错与冻结交付

| 本批固定上限/人口 | 数量 |
|---|---:|
| 新物理control/substep、fit/OLS/RLS、teacher/fork | 全部0 |
| 原生top-level已付区间 | 9000 |
| 新预测记录 /pair /velocity heads | 4146/135900/271800 |
| 新模型B系数 /已学IV1 action scalar提取 | 48/24（三seed两模型/仅learn） |
| 旧完整模型前向、旧评分/门重算 | 全部0 |

正式物理累计保持 **544345控制调用/2824018子步**，历史RLS scalar **125652**不变。原生历史、未来请求与评分标签的重复用途、guard/hinge/action计算、memory/d、积分、指标及gate、旧指标转录、JSON解码/解压、source/input hash、准备和输出IO分别计账；未测内部工作标unknown。旧实验费用不归零，新增评分标签用途不是拟合标签或在线学习。

任一pin/来源/schema/完整连续性/历史/模型资格/预测finite异常停止全批，保留首错、已处理人口及全部事前4146槽的executed/not_executed/failed状态，不能覆盖原错或只保存成功记录。输出目录首次新建拒覆盖；保存全部config、seed、输入identity、CPU/依赖/wall/CPU与实际费用、源ZIP、原始预测/标签、全精度新指标、旧转录表及首stdio。输出失败附加记录，不替代首实验错误。失败不scan filter/gain/B/比例或用原bank挑最佳模型。

runner为 `scripts/develop_causal_incremental_prediction.py`，模型为 `src/developmental_physics/causal_incremental_pair_model.py`。source.zip保存新runner、本协议、新模型及实际纯依赖 `src/developmental_physics/instrumental_action_model.py`、`src/developmental_physics/__init__.py`；必要新合成检查与确切闭包在冻结runner/准备manifest中绑定。没有旧runner、物理环境或状态head调用。所有输入pin和协议pin与exact clean source commit绑定，源码不能dirty替换解释首结果。

五scientific flags全false，`control_candidate_opened=false`。首结果只做一次新保存轻核；报告负结果与边界、检查、提交推送后继续active目标，不以局部预测宣布C4、C5–C7或真机成功。
