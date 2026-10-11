# L：固定原生转移的数据增量开发

本协议与 `scripts/develop_guard_native_augmentation.py` 在实际 trace/weights 读取、
模型调用和拟合前冻结。准备草稿位于 `external/c4_native_augmentation_staging/`，
准备仅可读 C/G/K manifest 与 metadata/run 的来源身份；不读实际 trace、K parameters，不拟合或预测。

本轮仅改变拟合数据：每 seed 的 C sparse400 加已保存 G PDselected200，共600。
原生表示、29列特征、current-v位置prior、.01 ridge及闭合递归全部保持 K。
既有PD64/(0,4)本有任务能力且经过增益开发，PD采样属于额外任务/采样先验。
样本量与数据分布同时改变，不能识别纯覆盖因果；不能声称同预算效率、冷启动技能获得或安全。
K/D旧失败门保留。即使 L 的两开发门通过，scientific_adoption、C4科学验收和C5依赖解除仍false。

## 固定来源与匹配

C commit `5ea8df42b09588845760daf0dc1f270aef2a87f1`，
D commit `f7710c7b048dccab3e436d1fa16432f881a35992`，
G commit `91dcf6c111a87427c8f3fdd8b959d4792b1bb5a2`，
K commit `b46c6d37fddc8e6534384168fb76663bc2c5236c`。
脚本 pins 固定 C/G 原始 manifest、metadata、trace，D manifest/diagnostics，K manifest/run/parameters。
K参数pin仅从已发布manifest取得，准备不读权重。
正式执行验证 raw manifest payload hashes、C/G来源clean/正式身份、K clean source/输入绑定。

从 K 发布 parameters 只恢复三个29×22权重、八轴qref和参数身份，不重拟合或消费其训练设计、标签、预测、分数。
完整 K 参数指纹须一致；恢复权重设为只读，运行前后复核指纹。
D11仅按K既有恢复函数还原各 seed sparse11冻结snapshot，无更新。
纯helper包括canonical K脚本及其五个NumPy helper，全部按新L clean HEAD冻结，
且必须保持K首次发布数学源码的SHA。不得调用K main_run/read_inputs/frozen_sources。

C/G须共享 environment_config、pose、joint_indices、native joint count、model input basis、
MuJoCo版本/依赖、公开模型资产与environment/guard源码身份、PD gains及PD来源绑定。
G的D_binding必须指向上述D和C；不修配来源、物理、动作或不一致输入。
八维qref分别由各 selected trial 的完整100步前缀step99 after取得，
C calibration、C prediction和G PDselected都必须逐轴等于本seed恢复K的固定qref。
不补零、不跨trial、不按实际分数选择样本。

## 保持的数学与新增数据

`x22=[8(q-qref),8v,3gyro,3accel/9.81]`。
`phi29=[x22,2 current startG,2 signed hinges(.25),1,2(v-previous_v)]`。
公开KnownAngleGuard映射限幅.5 Nm、距限位.03 rad向外请求归零，原生q不夹。
prior八轴q_next=q+.02*v_current；前两轴v_next=v+.02*startG，其余v/gyro/归一化accel保持。
所有后续22通道由预测自身闭合生成，lag推进为old predicted current v。

每 seed 固定先 C `seed{s}_calibration_sparse` active0…399，再 G `seed{s}_PDselected` active0…199。
每个trial必须具备自己的完整前缀、连续历史与完整主动区间，源active counts正好400/200；
G200不得停止或部分执行。不足600时该seed不可拟合，不缩减、补零、重复、筛除或补跑。
每个训练区间的current/previous v只来自该trial过去step99/98或随后合法原生端点，
分别调用K窗口检查；不把C最后端点接到G起点。
标签只为原生未来state22减prior。requested torque是已知转移条件，
不把PD action、target、reward、真实力矩、接触、quaternion或动力学真值作为学习目标/附加特征。

固定 `Phi(600,29)` / `Delta(600,22)`，float64
`W=solve(Phi.T@Phi+.01*I29, Phi.T@Delta)`。
L新增入口只把K固定400行shape资格改为600，其Gram/cross/正则与一次共享solve算术保持。
每 seed 13,200 scalar标签、638新系数，三seed共3 solves /39,600标签 /1,914新系数。
是新增非RLS离线学习，历史K26,400标签/3 solves与历史RLS费用继续保留。
保存source/transition IDs、设计/标签/prior/normal/cross/weights、恢复和拟合开销及失败原件。

## 固定预测与双门

只在 C 公共prediction100上评分。矩阵固定 K22/L22/D11，不新增cold组。
G PD为训练数据，不评分、不用于方法排名。
H固定1/2/5/15，各seed全origin分别100/99/96/86；每method、每horizon独立递归，
仅origin current native和合法过去历史初始化。未来请求序列为已保存的离线条件，
不声称在线预知未来真实veto；未来真实native只用于最终端点评分和窗口资格。
完整source stop最后区间可评分，停止后不可延伸。不得排名缺样子集。

L22相对K22的数据增量门与L22相对D11的原K规则门独立命名、独立报告，均固定：

- 三method、每seed、每H均有完整固定counts100/99/96/86，source prediction为100。
- H1两v每seed严格改善；每轴三seed算术平均相对RMSE改善≥20%。
- H15两q每seed严格改善且每轴平均≥20%；两v每seed不劣。
- H2/H5两q/v每seed不劣。

基线RMSE为零、非有限或缺固定全窗口时相关门不可评估。进入新留出/匹配完整控制须**两门均通过**；
即使双门通过仍不是科学采用。不能追认K或D旧失败门，不改变任务、门、seed或数据。

## 预算、冻结与故障

新增正式物理/RLS为0。额外使用每seed G已付费200active+100prefix，
合计900控制调用/9000子步，已经包含历史G物理账，不再次加为新增物理；
PD既有9配置增益开发与选择成本见 `docs/PAIR_PD_DEVELOPMENT_PROTOCOL.md` 及阶段账本，不能归零。
所有已付费失败/校准与K计算仍累计保留。
每method预测无故障全seed6204步；D为6204pair/12408scalar heads，K/L各闭合22通道，
三method共3429origin记录；与新39,600拟合标签分别计账。

正式首次运行要求canonical路径、clean精确source commit、所有来源pins吻合，output必须不存在。
逐seed恢复attempt/return与拟合labels/matrix/solve/publication、逐method预测开销与失败分列。
记录已返回的部分原件；source验证未返回为unknown，读过的input记录保留，未返回读取记录为unknown。
不重试实际fit/预测或补跑；新开发门失败公开否定。

```powershell
python scripts/develop_guard_native_augmentation.py --repo . --source-commit SOURCE_COMMIT --output NEW_OUTPUT
```

准备检查待静态确认，只检查新数据混合/隔离、跨trial历史、600完整资格和双门命名；
不重跑K旧六分支或人工ridge，不重复已揭晓物理、数学或审计。
