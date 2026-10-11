# 左肘一次身体模型开发独立审读

正式一次采集及首次审计后，按 root 明确授权执行一次标准库 summary。只读真实原生 8 维中的 j1；未重排数组，未导入 runner/audit/MuJoCo/NumPy，未执行物理、RLS 数学重播、参数拟合或新模型预测。

结论：524,210 项独立核对、0 失败，最大差异 5.551115123125783e-17。数据一致性通过；五必要试验模型贡献门 false/unevaluated、六必要试验 PD 门 false/unevaluated、七试验完整矩阵 false。算法验收没有通过。

采集 clean commit `46077b1d30089d68f1c935e3fc547dfdfa4c4e66`，development seed 0/1/2。每 seed fresh θ=[1,0,.02,0,0]、P=100I、原生负 qref，300 次校准更新，后续评估参数冻结。已见开发 seed 不充作新留出。

正式预算：5,292 控制调用、52,920 子步、900 RLS；21 计划试验中 15 完成、6 研究停止、0 环境停止、0 异常。prefix=2,100 调用、calibration=900、prediction=453、control=1,839。停止段最后完整端点可计残差和费用，但不能称 completed。

含本轮正式物理累计 221,663 调用 / 2,216,630 子步 / 10,800 RLS。PD 开发额外 7,521 / 75,210 / 0 已单独披露，body 中 tuned PD64/1 来源 commit/audit/summary/候选8 固定核验。

## 冻结门与完整对照

| seed | low nominal v RMSE | low learned v RMSE | 降低 | nominal tracking (完整200) | learned tracking (仅13) | PD tracking (完整200) | zero tracking (完整200) |
|---|---:|---:|---:|---:|---:|---:|---:|
| 0 | 0.0753258117109 | 0.0668952729631 | 11.192098% | 0.048999710973 | 0.0411417586773 | 0.00620931138421 | 0.0632455520761 |
| 1 | 0.0753948855492 | 0.0670354052215 | 11.087596% | 0.0484466721528 | 0.0410664447359 | 0.00621041721647 | 0.0632455546362 |
| 2 | 0.0752469882506 | 0.0666660449066 | 11.403703% | 0.0488933479012 | 0.041225655829 | 0.00620792183055 | 0.0632455475057 |

low 三 seed 完整，但速度改善 11.09%–11.40%，不足固定 20% 门。full 三 seed 各仅 51 active 端点，learned MPC 各仅 13，完整低/高预测及闭环对照条件不成立。不能用截断 full 的较低残差、短 learned tracking/累计努力或零环境停止声称模型控制优势、节能或安全。

完整控制均值：nominal tracking=0.048779910342356465 rad、PD64/1=0.006209216810408327 rad、zero=0.06324555140602196 rad；learned 完整均值 null。PD实际 |u|、u²积分均值=0.9705302323162487 N m s / 0.24873701123073969 N² m² s。nominal=0.9350833333333336 / 0.45944791666666696。不同控制器闭环轨迹分别评价。

learned 启动成本每 seed 已支付 calibration400 + own control113 =513调用/5130子步；PD/nominal/zero各300/3000。共同 prediction 351/3510 单列。局部控制窗口权限相同不等于总体启动成本相同。

## 六次原生停止

| seed | kind | step (0起) | active (0起) | q rad | q-qref rad | v rad/s | 当前请求 N m | trigger |
|---|---|---:|---:|---:|---:|---:|---:|---|
| 0 | prediction_full | 150 | 50 | 0.0345613272558 | 0.0351375752708 | -1.02913133848 | -0.375 | absolute_velocity_rad_s |
| 0 | learned_mpc | 112 | 12 | 0.119818493547 | 0.120394741562 | 0.570385092747 | 0.375 | absolute_q_minus_qref_rad |
| 1 | prediction_full | 150 | 50 | 0.0344406402153 | 0.0350169577692 | -1.0343372361 | -0.375 | absolute_velocity_rad_s |
| 1 | learned_mpc | 112 | 12 | 0.119652520108 | 0.120228837662 | 0.569455819009 | 0.375 | absolute_q_minus_qref_rad |
| 2 | prediction_full | 150 | 50 | 0.0346971450777 | 0.0352732998709 | -1.02821969599 | -0.375 | absolute_velocity_rad_s |
| 2 | learned_mpc | 112 | 12 | 0.120002587135 | 0.120578741929 | 0.571394198912 | 0.375 | absolute_q_minus_qref_rad |

所有研究停止由 summary 从 j1 原生端点独立重算，和首次 audit、episode 完全一致；研究停止与环境终止分别计账。full 固定探索负命令 −0.375 N m 的快速反向响应越过 |v|≥1；不能事后削掉该段或提升阈值。

## learned MPC 失配证据

每 seed 13 active 控制端点、130 子步，实际 j1 力矩均非零、与请求完全相等，0 限位动作屏蔽、0 fallback；记录可行候选为8×3次及7×10次。最初三次及停止步选择均为 +0.375 N m（未从截断低努力声称节能）。因此这次闭环停止不是所选关节实际动作被屏蔽或候选全不可行导致。

| seed | θ (v,qoffset,u,hinge,1) | stop前 v | recorded预测下一v | 实际下一v | recorded预测下一q | 实际下一q | q域外/13 | v域外/13 |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| 0 | 0.809434881862, -3.53743883052, 0.0362110512252, 0.617300050464, 0.0204742430205 | 0.575880154392 | 0.192668971338 | 0.570385092747 | 0.112023720503 | 0.119818493547 | 3 | 0 |
| 1 | 0.811325071525, -3.5182639598, 0.0359284905187, 0.615294733061, 0.020391724953 | 0.574968770703 | 0.195183531472 | 0.569455819009 | 0.111926310527 | 0.119652520108 | 3 | 0 |
| 2 | 0.805977966818, -3.60450842555, 0.0367028558935, 0.62290004207, 0.020689095019 | 0.576872715227 | 0.184692279057 | 0.571394198912 | 0.112028405916 | 0.120002587135 | 3 | 0 |

三 seed 最初预测 +0.375 约在目标 .0394 rad 附近形成转向/恢复，实际关节继续向正方向超调。停止步模型仍预测下一 q≈.112、下一 v≈.185–.195，真实下一 q≈.11965–.12000、v≈.569–.571；一步速度残差明显。该描述使用原件保存的 chosen forecasts，首次 audit 已独立重播选择，summary 没有新算预测。

校准 qoffset 范围约 −.00626至+.07679，learned 起点三seed各3/13域外(23.08%)，v起点0/13域外；最早多数控制输入仍在分别计算的q/v envelope内。矩形范围不保证联合状态、动作、接触历史都受支持，不能把“范围内”称可靠模型或安全集，也不能将全部失败归因于最后3个域外状态。

模型 qoffset 系数约 −3.52至−3.60、非零 bias≈+.0203至+.0207，表现为较强恢复预测；零力矩平稳评估上它的v一步RMSE≈.0203–.0207，而连续/nominal模型约1e−9，提示该拟合的条件误差。校准每seed负命令有500子步被所选关节限位保护屏蔽，low有350、full有140；requested输入与真实执行的差异和接触/关节耦合是待检验机制，不能仅凭本轮识别其因果贡献。

MPC公共预测范围约[−.03,qref+.15]、速度许可1.5rad/s，研究停止为|q−qref|≥.12或|v|≥1，两套边界不是相同阈值。止前记录预测本身在其许可范围且未预见实际越界。保持原门与负qref，不裁目标，不用放宽停止改善结果。PD实际能完整跟踪，支持诊断对象是本次模型与预测控制组合而非该关节完全不可控。

## 诊断来源与风险

一步 q/v 残差、tracking、努力、q/v coverage、实际调用/子步、研究停止、stored model hash链由summary原生重算或核验。风险/conditional/tail/free_rollouts完整保留首次audit来源，没有独立重算模型多步轨迹。首次audit只有1/5/15/50步；2步明确未记录。learned控制5步只有9窗口，15/50步0窗口，不能把null解释为零误差或长时域通过。

风险包含所有paid prefix、失败和主动段；环境零停止不等于安全。j1负qref是MuJoCo原生轻微公共限位穿透，未clamp；soft_limit/接触峰等原件全保留。summary guard计数覆盖8关节，j1动作屏蔽另按实际history隔离；缺少实际子步时努力仅下界。

下一步建议：本开发配方左肘不采用为已验收控制。进入明确新协议的肩—肘原生映射与预测有效域检查，先保证动作权限、受支持预测与共同控制评估；将guard、接触条件、联合状态支持和恢复预测偏差作为假设逐项消融。新协议应固定预算、独立强PD、研究门及新seed，保留本失败，不以本开发seed充新最终留出。

## 一次执行、合成失败与文件

summary wall=1.3045454998500645, CPU=1.3125；wrapper wall=1.6233240999281406, CPU=1.46875。首次audit731662/0失败、SHA 1bd3632fd805064951addf72120992b63dca2df255fddc54840b22d014c4f78a。

有限合成第1轮8测试中1失败：递归dict compare只要求期望键，漏掉冻结后新增键；修复为before/after完整dict相等并核验saved model键。第2轮8项全通过；两轮分别wall=.1977621999103576/.221563900122419 s，parent CPU=0/.015625 s。child unittest CPU未单独测量，不能把parent CPU称完整测试CPU；unittest .076/.074 s只是测试elapsed。两轮没有正式原件读取、物理或更新。

第1轮源码当时未snapshot，交付`synthetic_01_source_reconstructed.py`是依据三处明确修复逆向重建的生成件，不冒充执行保存原件。第2轮source copy与后来实际summary executed源码完全相同，原测试源码两轮未改。旧失败stdout及execution exact copies保留来源说明，不补跑。

| file | SHA256 | type/source |
|---|---|---|
| `external/elbow_body_20261011_summary_01_attempt.json` | `0b408c1cf7ab30869b6ccd7d7de388498101fe32192a6a3ddea93a23260b7dbd` | original or saved-summary-derived |
| `external/elbow_body_20261011_summary_01_delivery_builder.py` | `99f164dbbf5c72e05f8a3235a34a84c55f3d9fe45fa8bfe9b9219d35c92da61a` | original or saved-summary-derived |
| `external/elbow_body_20261011_summary_01_execution.json` | `282e027d9d15ab03c9a6022989c94bf82e5c67ec57c66cb7e4ccca656934a3da` | original or saved-summary-derived |
| `external/elbow_body_20261011_summary_01_review_tables.json` | `c023c66e993431b7eb4d2236c62864d4e5684e170367dd372fbd82acb9d0ceac` | original or saved-summary-derived |
| `external/elbow_body_20261011_summary_01_stdout.txt` | `e3d7728c170f92492578ca29d96ac6cb3446a44b7c0fad566702dfc326b75e2c` | original or saved-summary-derived |
| `external/elbow_body_20261011_summary_01_summary.json` | `0d745e678bd5644c1167252cd794b156c570984793ecdbed588a6c3ac7ffb39a` | original or saved-summary-derived |
| `external/elbow_body_20261011_summary_01_summary_executed.py` | `d815bd5979ad1270bc90508c4847c05bf4d8498de32783ffeea6937d9fd0f88e` | original or saved-summary-derived |
| `external/elbow_body_20261011_summary_01_synthetic_01_execution.json` | `42888429931176f5fb0b3236f9b7a08b2627579d48b499dc5bd360993da6a43d` | copied/reconstructed/generated provenance distinguishes exact types |
| `external/elbow_body_20261011_summary_01_synthetic_01_source_reconstructed.py` | `dab3f0757c08db44c7beb860642738da223c7b24baf8830dc51157664a69533f` | copied/reconstructed/generated provenance distinguishes exact types |
| `external/elbow_body_20261011_summary_01_synthetic_01_stdout.txt` | `d2cfde2ccdeab4019eecc9535c5778131f8ac2aef9dd40ba66b3c19bf449e333` | copied/reconstructed/generated provenance distinguishes exact types |
| `external/elbow_body_20261011_summary_01_synthetic_02_execution.json` | `1d7022018e6e3fc7883dee4bcf526efeca83f96dda52d1c46ef6318fc49bec04` | copied/reconstructed/generated provenance distinguishes exact types |
| `external/elbow_body_20261011_summary_01_synthetic_02_source_copy.py` | `d815bd5979ad1270bc90508c4847c05bf4d8498de32783ffeea6937d9fd0f88e` | copied/reconstructed/generated provenance distinguishes exact types |
| `external/elbow_body_20261011_summary_01_synthetic_02_stdout.txt` | `c96f3110c99b5eff8e4fc23a7a2fd3c7cc18ef2a7be6e25f3d55c78ddde870a3` | copied/reconstructed/generated provenance distinguishes exact types |
| `external/elbow_body_20261011_summary_01_synthetic_copy_provenance.json` | `c8f1106a9ae75e2c68c33b911deed4c6b8e769dcf53f4d57f30862909b23f49b` | copied/reconstructed/generated provenance distinguishes exact types |
| `external/elbow_body_20261011_summary_01_synthetic_tests.py` | `eab6c2c6b747c0d6bf715f5707241c4cd077b1050dbb851e1595075b74cfdf36` | copied/reconstructed/generated provenance distinguishes exact types |
| `external/elbow_body_20261011_summary_01_wrapper_executed.py` | `fe8866222f745da620b72f808e294be3d653e8acad9fbe31ec17500d7101e7ee` | original or saved-summary-derived |
| `external/elbow_body_summary_prepare.py` | `d815bd5979ad1270bc90508c4847c05bf4d8498de32783ffeea6937d9fd0f88e` | original or saved-summary-derived |
| `external/elbow_body_summary_wrapper_01.py` | `fe8866222f745da620b72f808e294be3d653e8acad9fbe31ec17500d7101e7ee` | original or saved-summary-derived |
| `external/test_elbow_body_summary_prepare.py` | `eab6c2c6b747c0d6bf715f5707241c4cd077b1050dbb851e1595075b74cfdf36` | original or saved-summary-derived |
| `external/prepare_elbow_body_summary_delivery.py` | `99f164dbbf5c72e05f8a3235a34a84c55f3d9fe45fa8bfe9b9219d35c92da61a` | original or saved-summary-derived |
| `external/elbow_body_summary_synthetic_01_stdout.txt` | `d2cfde2ccdeab4019eecc9535c5778131f8ac2aef9dd40ba66b3c19bf449e333` | copied/reconstructed/generated provenance distinguishes exact types |
| `external/elbow_body_summary_synthetic_01_execution.json` | `42888429931176f5fb0b3236f9b7a08b2627579d48b499dc5bd360993da6a43d` | copied/reconstructed/generated provenance distinguishes exact types |
| `external/elbow_body_summary_synthetic_02_stdout.txt` | `c96f3110c99b5eff8e4fc23a7a2fd3c7cc18ef2a7be6e25f3d55c78ddde870a3` | copied/reconstructed/generated provenance distinguishes exact types |
| `external/elbow_body_summary_synthetic_02_execution.json` | `1d7022018e6e3fc7883dee4bcf526efeca83f96dda52d1c46ef6318fc49bec04` | copied/reconstructed/generated provenance distinguishes exact types |

## 补充精确表（仅读取已保存summary）

以下是固定一次summary已有字段的算术整理，没有重新读取raw/audit或重新运行summary；q绝对范围由qref+原生输入qoffset范围计算。多关节遗漏/保护条件只为机制假设，没有因果采用结论。

| seed | qref rad | cal qoffset min | cal qoffset max | cal q absolute min | cal q absolute max | cal v min | cal v max | learned q域外率 | learned v域外率 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 0 | -0.00057624801499955814 | -0.0062625881503391139 | 0.076710577355439707 | -0.0068388361653386725 | 0.076134329340440149 | -0.85009504796281521 | 0.94714219128083177 | 0.23076923076923078 | 0 |
| 1 | -0.00057631755385963439 | -0.0051218353374651963 | 0.076638437647152766 | -0.0056981528913248305 | 0.076062120093293134 | -0.85151045760293642 | 0.94639184091873141 | 0.23076923076923078 | 0 |
| 2 | -0.000576154793236481 | -0.0061028550114277137 | 0.076792287339791002 | -0.0066790098046641943 | 0.076216132546554516 | -0.84871909303333426 | 0.94798681912707461 | 0.23076923076923078 | 0 |

| seed | 首次current q | 首次current v | target q | chosen u | chosen cost | 15步预测末q | 15步预测末v |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 0 | -0.00057624801499955814 | 6.9911622210818443e-10 | 0.039423751985000442 | 0.375 | 0.0055064649118435728 | 0.036661198396847554 | -0.06810169927006933 |
| 1 | -0.00057631755385963439 | -8.8534506626824468e-10 | 0.039423682446140369 | 0.375 | 0.0055129298766223214 | 0.036831123102823639 | -0.068514236811439033 |
| 2 | -0.000576154793236481 | 2.1433824547860861e-09 | 0.039423845206763522 | 0.375 | 0.0054925585862478981 | 0.036048061909770307 | -0.068532952629383109 |

| seed | stop112 current q | current v | predicted next q | predicted next v | actual next q | actual next v | target q | chosen u | chosen cost |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 0 | 0.10817034107593437 | 0.57588015439158247 | 0.11202372050268911 | 0.19266897133773633 | 0.11981849354668098 | 0.57038509274697047 | 0.039423751985000442 | 0.375 | 0.029466945630416273 |
| 1 | 0.10802263989734502 | 0.57496877070252639 | 0.1119263105267935 | 0.19518353147242393 | 0.1196525201076937 | 0.56945581900933828 | 0.039423682446140369 | 0.375 | 0.029552046386716414 |
| 2 | 0.10833456033476653 | 0.57687271522661965 | 0.1120284059159032 | 0.18469227905683344 | 0.12000258713540408 | 0.57139419891216947 | 0.039423845206763522 | 0.375 | 0.02925406810669377 |

补充表路径 `external/elbow_body_20261011_summary_01_review_detail_tables.json` SHA256 `9e3af0e71e295f61ffb4b0bddace435846fb7bdc4f9e4279d7096f7c60fa8497`。
补充生成源码 `external/elbow_body_20261011_summary_01_detail_append_builder.py` SHA256 `bd2f0ec436b34024808d875ba0534b39e1520b8df9901891e6f1aeafde154875`。
补充整理wall=0.023791000014171004 s，CPU=0.015625 s；scope为saved-summary读取/表构建/源码保存，JSON写盘之前。
