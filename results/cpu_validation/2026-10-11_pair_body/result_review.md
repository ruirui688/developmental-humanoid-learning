# 肩—肘首次开发：独立只读 summary 与下一候选冻结依据

2026-10-11。正式采集源为 clean `884188416b982ad03c0b3ba6f94999e162ddf98f`，development0/1/2、supine、原生j0肩/j1肘。本审读未重执行物理、模型fit/更新/新预测或任何audit，未读20–22，也没有修改tracked或Git。正式原件仅在独立summary中读取一次；此后只查看该summary生成的表及root结果文档。

## 1. 采集完整归档，但学习比较没有进入评价

24个计划trial：**6完整、6研究停止、12依赖blocked，0环境停止、0异常**。三个calibration均只执行171/400个active；两个模型的失败校准快照保留但没有发布。每seed两prediction和两个learned MPC均因该seed calibration未完成而blocked，真实交互和更新均0。名义MPC与zero各三seed200active完整；组合PD各三seed第二个控制端点停止。

首次独立audit **1,540,296 checks / 0 failures**，最大差 `4.3876013933186186e−13`；SHA256 `bb717cd064af534a84a4b8fac43e80c16bd59220392d9aaeedc27feee1614456`，wall `12.5934297000058 s`、CPU `11.609375 s`。本summary **273,442 checks / 0 failures**，最大算术差 `5.551115123125783e−17`；manifest、metadata/episode/seed/raw账、source ZIP全成员与Git blob、原生8D映射、固定pulse、已记录预测残差、更新数量、stop/blocked及完整tracking/effort一致。

两个模型贡献、coupled增量、两个组合PD比较与完整矩阵门均未通过；首次audit的各科学比较 `evaluated=false`。这是资格失败和未执行，**不是耦合机制被否定，也不是较差耦合控制的实验结果**。audit的数据一致性与科学门是两件事。此summary不重新做RLS/MPC/多步预测；多步、风险、支持与首次audit的门按来源引用保存。

## 2. 停止位置：首个大幅反向命令，而非已经执行了长负脉冲

| seed | calibration step / active | 已知请求(j0,j1) N·m | j0速度 rad/s | j1速度 rad/s | 触发 |
|---|---|---|---:|---:|---|
| 0 | 270 / 170 | (0,−.5) | +.6241620591 | −1.3187497823 | j1 abs(v)>=1 |
| 1 | 270 / 170 | (0,−.5) | +.6245805207 | −1.3197447514 | j1 abs(v)>=1 |
| 2 | 270 / 170 | (0,−.5) | +.6070512271 | −1.3312411112 | j1 abs(v)>=1 |

active/step均零起算；active170是第171次active调用、block8的slot10。block8为**肘-only、.5幅度**；真实顺序是5个+.5、5个zero、首个−.5。首个负向20 ms的10个子步实际全部执行−.5，0屏蔽；研究停止使其余4个负向及5个zero未执行。不能写成已经完成5个或更长负向命令后失败。

三seed在停止前的五个zero端点active165–169中，肘速度依次约 `+.438、+.020、−.230、−.424、−.539`（seed2末端约−.569）。zero不是已经静止：反向命令开始前肘已沿负向运动；j0请求为零而当时速度约+.257至+.297，随后上升到+.607至+.625。seed0末五步及停止完整原生8D q/v、已知请求、feedback、10子步actual和stop记录已保存在detail表，其他seed也同样保存。

这是“较高幅度 + 当时仍有被动/跨轴运动 + 原生执行模式”的观测，尚无逐因素干预对照，不能断言具体耦合、接触、残余状态或脉冲强度是唯一原因；不能说身体模型控制导致这次calibration停止，因为calibration动作固定不读取模型。

另三次停止是组合PD：肩64/0、肘64/1，在active0、1均请求(−.5,+.5)，各20 ms真实全执行；肘速度先约+.616，再分别到 **+1.0718411278 / +1.0714563918 / +1.0722633003**。它只是两个单轴已调增益的组合，本条件下不能完整执行，仍需独立双轴增益开发；不支持“经典控制总体无效”。

## 3. 动作激励与guard必须分开报告

各seed固定方向(−1,+1)，qref肩约+.094至+.101、肘约−.000576，未裁剪略负肘qref。肩-only blocks0–4共100active完整；对应肩峰值速度在小剂量约.005/.010/.016，.5剂量块约.093；肘虽请求零，.5肩块肘峰值约.214。肘-only blocks5–7各20active完整，幅度.125/.25/.375；各块全部5个负向请求的50子步被guard屏蔽，**每seed j1总150子步屏蔽**。

| 每seed calibration主动阶段 | j0 | j1 |
|---|---:|---:|
| 请求绝对努力 N·m·s | .300 | .210 |
| 实际绝对努力 N·m·s | .300 | .135 |
| 请求平方努力 N²·m²·s | .10625 | .07375 |
| 实际平方努力 N²·m²·s | .10625 | .051875 |
| 已返回子步 | 1710 | 1710 |
| 屏蔽子步 | 0 | 150 |

blocks5–7的负向在当时接近下限状态被屏蔽；block8首个负向却全部执行，停止端点肘q约+.0371，执行前约+.0570。这说明同样的请求方向在不同原生状态下执行模式不同，不能把前面小剂量“未停止”当成这些反向剂量已经真实充分激励的证据。

block8返回11active（5正/5zero/1反），其余229active未运行；block9及同向/反向双轴blocks10–19均未到达。因此当前校准没有覆盖原计划的双轴共同激励；不能宣称coupled模型已完成其共同预测/控制测试，也不由此臆断回归rank或某个系数的物理原因。

## 4. 完整控制、截断控制与被动对照

| seed | nominal完整联合RMSE rad | zero完整联合RMSE rad | nominal fallback / 200 | nominal肘屏蔽子步 | nominal实际绝对/平方努力(双轴合计) |
|---|---:|---:|---:|---:|---|
| 0 | .0443250701 | .0632697577 | 94 | 299 | 1.552 / .7358125 |
| 1 | .0450631666 | .0631996452 | 103 | 250 | 1.42375 / .68203125 |
| 2 | .0441239048 | .0633376375 | 93 | 312 | 1.5405 / .7405625 |

名义MPC与zero均200完整端点，不是截断片段。nominal是通用cold模型的固定控制响应，没有身体更新，不能把其相对zero的差叫学习优势。nominal fallback仍很多，第二目标段计划末20的肘有符号误差约−.0476至−.0634rad，完整运行不等于任务能力已经形成。两轴、两目标段、计划末20窗口及缺失数都保留，未新增绝对成功阈值。

组合PD只有2个完整端点，联合RMSE约.02926、实际努力合计.04/.02；两个末20窗口均缺20。这些数只描述终止片段，不能拿它们和nominal/zero的200端点或后续学习控制做优势比较。zero实际努力0、肘速度约1e−9、tracking约.063，稳定而不跟随目标；不能称零动作学会协调。

首次audit风险引用按full/prefix/active单列：本批active校准力峰约74.10–74.14N、动能峰约.01204–.01211J、穿透约.102–.103mm；包括zero在内的paidprefix有更高冲击/速度，因此不能凭active零环境停止给出全程安全结论。原生其余六轴及IMU都保存，禁止把诊断contact/world state送入模型。

## 5. 实际预算与summary成本

每seed真实271 calibration +300 nominal +102 PD +300 zero =973调用。三seed总 **2919调用 /29190子步 /2052 scalar RLS /1026 vector RLS**，phase prefix1200、calibration513、control1206、prediction0；模拟时间58.38s。每模型每seed171 vector/342 scalar，三seed每模型513 vector/1026 scalar；最后完整终止转移按原协议更新，不假定失败意味着0成本，也不把两模型共享转移算成双倍物理。

正式累计 **224582调用 /2245820子步 /12852 scalar RLS**。collector wall `35.55822899984196 s`、CPU `35.328125 s`，MuJoCo `3.15.0`、Python `3.10.11`、GPU=null。

summary脚本与wrapper在真实summary前已exclusive保存exact source snapshots，原件只读取一次，之后hash和计算用内存字节。summary wall `1.9191321001853794 s`、CPU `1.09375 s`；完整wrapper wall `2.3382744998671114 s`、CPU `1.3125 s`，包含imports、源码快照、读取、Git验证、写盘与输出hash，最终execution写盘另说明。有限手算synthetic **10 passed**，wall `.029364499961957335 s`、CPU `.03125 s`；partial只按实际3子步、guard、原生非identity映射、5/5/5/5与缺失窗口均有明确算例。新增物理、参数更新、预测和audit复跑为0。

## 6. 下一候选的冻结依据与边界

优先解决**固定校准可执行性**与**组合PD完整性**，暂不叠加guard输入、rest约束、coupled采用和未知扰动科学比较。当前学习对照被calibration挡住，直接用失败模型冻结做控制或追加prediction会破坏协议；所有新动作是新候选、新成本。

root提出的下一项是有限无学习校准诊断：原20块布局、400active、100paidprefix、剂量[.125,.25,.375,.5,.25]不变；两个明确候选 `2正/8zero/2反/8zero` 与 `1正/9zero/1反/9zero`，各development0/1/2，共6trial上限3000调用/30000子步/0updates。原5/5失败记录保留且不重跑。更短正脉冲与更长zero可能改变反向开始时原生状态，属于待检验的机制/可执行性选择；本次“一次反向20 ms也能停止”的证据说明不能保证缩短后通过。

先2/8、再1/9的采用规则应root事前冻结为：三seed全部400active完整、stop0、全部原始遥测/actual历史完备；2/8 eligible时选2/8，否则检查预定1/9；两者均无eligible则blocked。不能以截断努力、较低冲击或较少动作选择，不能提前复位补跑，也不把选择的短脉冲叫学习收益。工程/科学预算与已知开发条件必须明示；强基线增益开发另冻结，与校准诊断不混为学习优势。

后续模型版本若降低所有剂量到<=.25，原hinge特征将全为0，必须披露信息/结构变化；若保留当前剂量，guard模式及原生时序仍须验收。输入执行规则的工程改进只能基于当前q、已知请求和公开限位，未来actual只诊断。公共规则收益、模型更新收益及限制权限的收益必须匹配对照分别报告。

## 7. root文档与归档接口审读

已只读审查 `docs/PAIR_BODY_DEVELOPMENT_RESULTS.md`：停止步/触发轴、171更新、未发布与12blocked、nominal/zero完整、PD停止、预算/累计、collector/audit/summary CPU/wall和证据边界与此次summary一致。文档quoted nominal数值取首次audit，和本summary差约1e−17，属于有来源的浮点算术差，不需改写成同一个小数。该文档未把未评价耦合写为机制否定。

`external/archive_pair_body.py` 等待的两个名字与本交付兼容：`pair_body_20261011_summary_01_summary.json`、`pair_body_20261011_summary_delivery.md`。其`summary_01_*` glob会包含exact source、tables、stdout和execution；建议另复制 `pair_body_summary_synthetic_01_*` 原始synthetic stdout/execution/源码快照，当前glob不包含该前缀，不能只留下10-test源码而遗漏其CPU/通过记录。归档脚本由root执行，本代理未执行。

## 8. 文件与精确hash

| 当前external文件 | SHA256 |
|---|---|
| `pair_body_20261011_summary_01_summary.json` | `27b46508ed6e0d01bcfdf61b3f0854672465c3990e297378526828b9c1b97feb` |
| `pair_body_20261011_summary_01_review_tables.json` | `d81759c7b45313543418c56fc044183ed1479afb797290b9361b4064559cce72` |
| `pair_body_20261011_summary_01_review_detail_tables.json` | `2124d2dcf7af0360add8b5a478aa7535fbc99f15f169547123a5ed3dc3910e01` |
| `pair_body_20261011_summary_01_execution.json` | `2387a1e272723144a4877a7cdec737a3e353c7626daa5a31c259a0cc64537738` |
| `pair_body_20261011_summary_01_summary_executed.py` | `8caae18a3a409783e162695557ae738420fd1fbdeebb1861af39192afa52536c` |
| `pair_body_20261011_summary_01_wrapper_executed.py` | `4e73077c47837e331e440ebc0b991b2b7daff810b507b3b76110b2afe52f857e` |
| `pair_body_20261011_summary_01_synthetic_tests.py` | `1288c97b09b767fc335a011aaebf734ec0b264c2e351e78423bb095e627463f7` |
| `pair_body_summary_synthetic_01_execution.json` | `f1babef2020dd9087a116773c4315ae75a5ca68d504d781d124c906d69df21de` |

所有原件与source ZIP成员hash在summary，所有生成文件hash在execution；不重新读原件补hash。结果保留失败与未评价项，不补跑、不升科研门、不声称婴儿式学习、全身技能、未见泛化或真机。
