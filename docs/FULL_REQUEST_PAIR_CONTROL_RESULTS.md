# FR3B：FR3B首次完整首请求匹配控制（首次物理执行）

从clean `20e899a48d3b92211c09c3589fe710b16cb692d3` 首次物理控制执行一次，保存状态 **completed**；保存本域控制门未全部通过/不可评。实际新增36,000控制返回/36,000确认子步/0在线scalar提交；首新保存核验passed、660,047项/0失败。

[事前冻结协议](FULL_REQUEST_PAIR_LEARNING_PROTOCOL.md) · [根归档](../results/cpu_validation/2026-10-12_full_request_pair_control/manifest.json) · [唯一实验输入](../results/cpu_validation/2026-10-12_full_request_pair_control/report_inputs.json)

开发seed8001/8002/8003按冻结顺序，不宣称全局未使用或最终留出。原free root/仰卧8轴身体、理想感觉、公开guard/保护、2ms PD64/Kd4_4、固定刺激与任务目标均为先验。没有任务教师、预训练策略、PPO或GPU。接触只资格/诊断，紧凑模型只含两轴q/v和已知final requests，不能宣称全身状态闭合、安全或真机学习。

## 全部12项匹配跟踪与实际努力

每seed cold+新MPC、learned+同新MPC、强PD、zero依次fresh/reset一次。各计划1000zero+2000active。cold/learned/PD必须完整且满足prefix/A/B域资格；zero接触只描述，停止不另加采用veto。

| seed | 方法 | 完整/域资格/score available | active已保存/计划 | joint/肩/肘RMSE rad | actual absolute Nm·s | actual squared Nm²·s | unknown努力子步 |
|---|---|---|---|---|---:|---:|---:|
| 8001 | cold | true/true/true | 2000/2000 | 0.04515684037/0.03853727978/0.05092306483 | 1.483698924 | 0.7068551097 | 0 |
| 8001 | learned | true/true/true | 2000/2000 | 0.007579362277/0.007828772208/0.007321460972 | 1.558282784 | 0.5465532329 | 0 |
| 8001 | pd | true/true/true | 2000/2000 | 0.008002481354/0.009511702919/0.006132448389 | 1.428748932 | 0.4188226658 | 0 |
| 8001 | zero | true/true/true | 2000/2000 | 0.0632842251/0.06332287531/0.06324555127 | 0 | 0 | 0 |
| 8002 | cold | true/true/true | 2000/2000 | 0.04515739609/0.03853850983/0.05092311954 | 1.483711374 | 0.7068638269 | 0 |
| 8002 | learned | true/true/true | 2000/2000 | 0.007456890192/0.007884076916/0.007003695728 | 1.536670233 | 0.5344869458 | 0 |
| 8002 | pd | true/true/true | 2000/2000 | 0.008002663028/0.0095120471/0.006132388689 | 1.428811056 | 0.4188598229 | 0 |
| 8002 | zero | true/true/true | 2000/2000 | 0.06328385243/0.06332213039/0.0632455513 | 0 | 0 | 0 |
| 8003 | cold | true/true/true | 2000/2000 | 0.04573507414/0.03967769631/0.05107909973 | 1.531099117 | 0.7219809832 | 0 |
| 8003 | learned | true/true/true | 2000/2000 | 0.007675762872/0.007967806593/0.007372159075 | 1.582424503 | 0.5740047491 | 0 |
| 8003 | pd | true/true/true | 2000/2000 | 0.008126365118/0.009744535161/0.006092590136 | 1.467496123 | 0.443012514 | 0 |
| 8003 | zero | true/true/true | 2000/2000 | 0.06310477842/0.06296368735/0.06324555475 | 0 | 0 | 0 |

## 原控制门（保存值）

贡献门仍要求每seed joint/两轴严格改善，三seed原RMSE均值三指标各改善≥20%，actual absolute/squared两轴合计均值各≤1.05×cold。贡献通过才评PD：每seed三指标不劣、joint原均值改善≥5%，两种努力均值各≤1.05×PD；RMSE0百分比不可用、effort0要求candidate0。

| 比较 | available/passed | 基线joint/肩/肘均值 | learned均值 | 保存改善 | 各seed保存available/passed |
|---|---|---|---|---|---|
| cold贡献 | true/true | 0.0453497702/0.03891782864/0.0509750947 | 0.00757067178/0.007893551906/0.007232438592 | 83.3060%/79.7174%/85.8118% | 8001:true/true; 8002:true/true; 8003:true/true |
| 强PD参考 | true/false | 0.0080438365/0.009589428393/0.006119142405 | 0.00757067178/0.007893551906/0.007232438592 | 5.8823%/17.6849%/-18.1937% | 8001:true/false; 8002:true/false; 8003:true/false |

| 比较 | actual信号 | 保存基线均值 | learned均值 | 保存passed |
|---|---|---:|---:|---|
| cold | actual_absolute_two_axis_nm_s | 1.499503138 | 1.55912584 | true |
| cold | actual_squared_two_axis_nm2_s | 0.7118999733 | 0.5516816426 | true |
| PD | actual_absolute_two_axis_nm_s | 1.44168537 | 1.55912584 | false |
| PD | actual_squared_two_axis_nm2_s | 0.4268983342 | 0.5516816426 | false |

## 全部自身条件预测

六条自身来源分别用本seed两模型和已保存final requests递推；不pool、无事后self veto。下表保留全部五H、两轴q/v与availability（完整时120个向量）。FR3A通过不能覆盖自身有效域；planner 140步PD尾与actual再规划之差不能直接归因模型。

| seed/自身来源 | H/时距 | 预测模型 | available/observed/planned | q肩/肘 rad | v肩/肘 rad/s |
|---|---|---|---|---|---|
| 8001/cold | 1/2ms | cold | true/200/200 | 6.176352083e-05/0.000107463662 | 0.03088176042/0.05373183098 |
| 8001/cold | 1/2ms | learned | true/200/200 | 5.587683337e-05/8.779071662e-05 | 0.02793841668/0.04389535831 |
| 8001/cold | 10/20ms | cold | true/200/200 | 0.002259008493/0.00460599074 | 0.1924991617/0.3942270182 |
| 8001/cold | 10/20ms | learned | true/200/200 | 0.00174514325/0.003659535028 | 0.1416159952/0.2961989448 |
| 8001/cold | 20/40ms | cold | true/199/199 | 0.006393508351/0.01291370602 | 0.2656481671/0.5393365473 |
| 8001/cold | 20/40ms | learned | true/199/199 | 0.0044971835/0.009325566188 | 0.1677731/0.3483731642 |
| 8001/cold | 50/100ms | cold | true/196/196 | 0.02400842213/0.04850920138 | 0.3690118388/0.7471352307 |
| 8001/cold | 50/100ms | learned | true/196/196 | 0.01006439467/0.02100397843 | 0.1796214682/0.3739926282 |
| 8001/cold | 150/300ms | cold | true/186/186 | 0.0639823889/0.1274475179 | 0.3316823826/0.6607504929 |
| 8001/cold | 150/300ms | learned | true/186/186 | 0.009338697169/0.01938704162 | 0.1836848256/0.3815719687 |
| 8001/learned | 1/2ms | cold | true/200/200 | 2.904112997e-05/7.152078007e-05 | 0.01452056499/0.03576039004 |
| 8001/learned | 1/2ms | learned | true/200/200 | 2.210425794e-05/5.3213351e-05 | 0.01105212897/0.0266066755 |
| 8001/learned | 10/20ms | cold | true/200/200 | 0.0009306511257/0.001984681802 | 0.0701903839/0.1431743759 |
| 8001/learned | 10/20ms | learned | true/200/200 | 0.0006674700095/0.001458107978 | 0.0494876186/0.1041296463 |
| 8001/learned | 20/40ms | cold | true/199/199 | 0.001907382253/0.003855060735 | 0.06073764675/0.121682508 |
| 8001/learned | 20/40ms | learned | true/199/199 | 0.001394561662/0.002888577391 | 0.0496307532/0.1037110705 |
| 8001/learned | 50/100ms | cold | true/196/196 | 0.006312170193/0.01239573089 | 0.09887997881/0.1897347548 |
| 8001/learned | 50/100ms | learned | true/196/196 | 0.003543318798/0.007366350204 | 0.04803375446/0.1017130234 |
| 8001/learned | 150/300ms | cold | true/186/186 | 0.02579199647/0.04111963718 | 0.1341343438/0.1797969998 |
| 8001/learned | 150/300ms | learned | true/186/186 | 0.00734490512/0.01511130947 | 0.04497066208/0.09556095064 |
| 8002/cold | 1/2ms | cold | true/200/200 | 6.176358918e-05/0.0001074638273 | 0.03088179459/0.05373191366 |
| 8002/cold | 1/2ms | learned | true/200/200 | 5.587724467e-05/8.779121063e-05 | 0.02793862233/0.04389560531 |
| 8002/cold | 10/20ms | cold | true/200/200 | 0.00225901553/0.004606013204 | 0.1924994737/0.3942285539 |
| 8002/cold | 10/20ms | learned | true/200/200 | 0.001745156234/0.003659566331 | 0.141616808/0.2962012072 |
| 8002/cold | 20/40ms | cold | true/199/199 | 0.006393511207/0.01291374852 | 0.2656479856/0.5393379311 |
| 8002/cold | 20/40ms | learned | true/199/199 | 0.004497203567/0.009325632329 | 0.1677736885/0.3483754527 |
| 8002/cold | 50/100ms | cold | true/196/196 | 0.02400836626/0.04850926037 | 0.3690107292/0.7471356668 |
| 8002/cold | 50/100ms | learned | true/196/196 | 0.01006440891/0.02100407639 | 0.1796217165/0.3739940245 |
| 8002/cold | 150/300ms | cold | true/186/186 | 0.06398225467/0.1274477254 | 0.3316816771/0.6607514639 |
| 8002/cold | 150/300ms | learned | true/186/186 | 0.009338871324/0.01938716979 | 0.1836849965/0.3815731608 |
| 8002/learned | 1/2ms | cold | true/200/200 | 2.739976905e-05/6.889026524e-05 | 0.01369988453/0.03444513262 |
| 8002/learned | 1/2ms | learned | true/200/200 | 2.085886686e-05/5.300589256e-05 | 0.01042943343/0.02650294628 |
| 8002/learned | 10/20ms | cold | true/200/200 | 0.0008695178814/0.001828487994 | 0.06445897468/0.1312754394 |
| 8002/learned | 10/20ms | learned | true/200/200 | 0.000638844783/0.001373861439 | 0.04687514061/0.09774012067 |
| 8002/learned | 20/40ms | cold | true/199/199 | 0.001772471317/0.003549319275 | 0.05638049762/0.1129509668 |
| 8002/learned | 20/40ms | learned | true/199/199 | 0.001340207995/0.002767500308 | 0.04819521485/0.1002698539 |
| 8002/learned | 50/100ms | cold | true/196/196 | 0.006003074155/0.01161529562 | 0.09266983852/0.1745266914 |
| 8002/learned | 50/100ms | learned | true/196/196 | 0.003439643683/0.007124360305 | 0.04600503692/0.09615732901 |
| 8002/learned | 150/300ms | cold | true/186/186 | 0.02506065548/0.03863472608 | 0.1306274829/0.1663095606 |
| 8002/learned | 150/300ms | learned | true/186/186 | 0.00732000663/0.0149892318 | 0.0425099218/0.08915205539 |
| 8003/cold | 1/2ms | cold | true/200/200 | 5.760800315e-05/0.0001185578234 | 0.02880400158/0.0592789117 |
| 8003/cold | 1/2ms | learned | true/200/200 | 4.29877486e-05/9.395306529e-05 | 0.0214938743/0.04697653265 |
| 8003/cold | 10/20ms | cold | true/200/200 | 0.002285758939/0.004672508015 | 0.1901327967/0.3826357234 |
| 8003/cold | 10/20ms | learned | true/200/200 | 0.001718775324/0.003657987645 | 0.1373195296/0.2855188875 |
| 8003/cold | 20/40ms | cold | true/199/199 | 0.006256029952/0.01280733613 | 0.2569242828/0.5217524796 |
| 8003/cold | 20/40ms | learned | true/199/199 | 0.004292563122/0.009104506678 | 0.1614017383/0.3373544143 |
| 8003/cold | 50/100ms | cold | true/196/196 | 0.02284087355/0.04648004534 | 0.3550860913/0.7186023373 |
| 8003/cold | 50/100ms | learned | true/196/196 | 0.009457486374/0.02001766256 | 0.1713022873/0.3554228702 |
| 8003/cold | 150/300ms | cold | true/186/186 | 0.06158420429/0.1228669236 | 0.3054462667/0.6050501583 |
| 8003/cold | 150/300ms | learned | true/186/186 | 0.009292016022/0.01931306634 | 0.1759514421/0.3643747804 |
| 8003/learned | 1/2ms | cold | true/200/200 | 2.810639293e-05/6.223636328e-05 | 0.01405319647/0.03111818164 |
| 8003/learned | 1/2ms | learned | true/200/200 | 2.081068511e-05/4.675220372e-05 | 0.01040534256/0.02337610186 |
| 8003/learned | 10/20ms | cold | true/200/200 | 0.0009138124804/0.001924376833 | 0.0689794223/0.1401636043 |
| 8003/learned | 10/20ms | learned | true/200/200 | 0.0006521255734/0.001421647661 | 0.0488780142/0.1021482359 |
| 8003/learned | 20/40ms | cold | true/199/199 | 0.00197114246/0.003972548132 | 0.06677933551/0.1328695693 |
| 8003/learned | 20/40ms | learned | true/199/199 | 0.001396076535/0.002927704555 | 0.05036802406/0.1046963086 |
| 8003/learned | 50/100ms | cold | true/196/196 | 0.006316752676/0.01220327616 | 0.09682274751/0.180051922 |
| 8003/learned | 50/100ms | learned | true/196/196 | 0.003439819897/0.007238831584 | 0.04758049378/0.1006920596 |
| 8003/learned | 150/300ms | cold | true/186/186 | 0.02631286068/0.04065025064 | 0.1372480876/0.1755587806 |
| 8003/learned | 150/300ms | learned | true/186/186 | 0.007087061025/0.01517785234 | 0.0444855069/0.09459207603 |

新grid spacing=.125（旧残差.03125），delta=grid−当前clip PD可达±1，但所有final请求仍±.5；通常不含purePD候选。首请求采用clip(p+(grid−p))roundtrip，前10微步held delta与native反馈、后140预测PD尾；literal-zero fallback独立。扩大函数类、粗分辨率与PD抵消均为新增先验。

FR3B的fr3a_prediction_gate_passed默认false仅表示本阶段未重宣FR3A；保留已经通过的A报告与FR1事实，不用源检查失败的零物理尝试默认值覆盖它们。

## 全部trial、接触资格与实际努力

未尝试、停止与异常完整保留，未知值不补零。接触只资格/报告，不证明连续承重、因果或安全；actual为已保存2ms actuator_torque端点样本，不是未测连续积分。

| seed | trial | status/native完整/域资格 | 已返回/计划 | 停止/异常 |
|---|---|---|---|---|
| 8001 | cold | completed/true/true | 3000/3000 | 无 |
| 8001 | learned | completed/true/true | 3000/3000 | 无 |
| 8001 | pd | completed/true/true | 3000/3000 | 无 |
| 8001 | zero | completed/true/true | 3000/3000 | 无 |
| 8002 | cold | completed/true/true | 3000/3000 | 无 |
| 8002 | learned | completed/true/true | 3000/3000 | 无 |
| 8002 | pd | completed/true/true | 3000/3000 | 无 |
| 8002 | zero | completed/true/true | 3000/3000 | 无 |
| 8003 | cold | completed/true/true | 3000/3000 | 无 |
| 8003 | learned | completed/true/true | 3000/3000 | 无 |
| 8003 | pd | completed/true/true | 3000/3000 | 无 |
| 8003 | zero | completed/true/true | 3000/3000 | 无 |

| seed/trial | phase | 记录/计划 | 已付/已观察/unknown接触 | 左臂正端点 | feet正端点 | other正端点 | 资格 |
|---|---|---|---|---:|---:|---:|---|
| 8001/cold | prefix | 1000/1000 | 1000/1000/0 | 951 | 0 | 985 | true |
| 8001/cold | target_A | 1000/1000 | 1000/1000/0 | 956 | 0 | 1000 | true |
| 8001/cold | target_B | 1000/1000 | 1000/1000/0 | 888 | 0 | 1000 | true |
| 8001/learned | prefix | 1000/1000 | 1000/1000/0 | 951 | 0 | 985 | true |
| 8001/learned | target_A | 1000/1000 | 1000/1000/0 | 975 | 0 | 1000 | true |
| 8001/learned | target_B | 1000/1000 | 1000/1000/0 | 965 | 0 | 1000 | true |
| 8001/pd | prefix | 1000/1000 | 1000/1000/0 | 951 | 0 | 985 | true |
| 8001/pd | target_A | 1000/1000 | 1000/1000/0 | 990 | 0 | 1000 | true |
| 8001/pd | target_B | 1000/1000 | 1000/1000/0 | 988 | 0 | 1000 | true |
| 8001/zero | prefix | 1000/1000 | 1000/1000/0 | 951 | 0 | 985 | true |
| 8001/zero | target_A | 1000/1000 | 1000/1000/0 | 1000 | 0 | 1000 | true |
| 8001/zero | target_B | 1000/1000 | 1000/1000/0 | 1000 | 0 | 1000 | true |
| 8002/cold | prefix | 1000/1000 | 1000/1000/0 | 946 | 0 | 985 | true |
| 8002/cold | target_A | 1000/1000 | 1000/1000/0 | 956 | 0 | 1000 | true |
| 8002/cold | target_B | 1000/1000 | 1000/1000/0 | 888 | 0 | 1000 | true |
| 8002/learned | prefix | 1000/1000 | 1000/1000/0 | 946 | 0 | 985 | true |
| 8002/learned | target_A | 1000/1000 | 1000/1000/0 | 975 | 0 | 1000 | true |
| 8002/learned | target_B | 1000/1000 | 1000/1000/0 | 963 | 0 | 1000 | true |
| 8002/pd | prefix | 1000/1000 | 1000/1000/0 | 946 | 0 | 985 | true |
| 8002/pd | target_A | 1000/1000 | 1000/1000/0 | 990 | 0 | 1000 | true |
| 8002/pd | target_B | 1000/1000 | 1000/1000/0 | 988 | 0 | 1000 | true |
| 8002/zero | prefix | 1000/1000 | 1000/1000/0 | 946 | 0 | 985 | true |
| 8002/zero | target_A | 1000/1000 | 1000/1000/0 | 1000 | 0 | 1000 | true |
| 8002/zero | target_B | 1000/1000 | 1000/1000/0 | 1000 | 0 | 1000 | true |
| 8003/cold | prefix | 1000/1000 | 1000/1000/0 | 950 | 0 | 985 | true |
| 8003/cold | target_A | 1000/1000 | 1000/1000/0 | 963 | 0 | 1000 | true |
| 8003/cold | target_B | 1000/1000 | 1000/1000/0 | 892 | 0 | 1000 | true |
| 8003/learned | prefix | 1000/1000 | 1000/1000/0 | 950 | 0 | 985 | true |
| 8003/learned | target_A | 1000/1000 | 1000/1000/0 | 975 | 0 | 1000 | true |
| 8003/learned | target_B | 1000/1000 | 1000/1000/0 | 961 | 0 | 1000 | true |
| 8003/pd | prefix | 1000/1000 | 1000/1000/0 | 950 | 0 | 985 | true |
| 8003/pd | target_A | 1000/1000 | 1000/1000/0 | 989 | 0 | 1000 | true |
| 8003/pd | target_B | 1000/1000 | 1000/1000/0 | 987 | 0 | 1000 | true |
| 8003/zero | prefix | 1000/1000 | 1000/1000/0 | 950 | 0 | 985 | true |
| 8003/zero | target_A | 1000/1000 | 1000/1000/0 | 1000 | 0 | 1000 | true |
| 8003/zero | target_B | 1000/1000 | 1000/1000/0 | 1000 | 0 | 1000 | true |

| seed/trial | phase | 努力完整/已捕获 | actual absolute Nm·s | actual squared Nm²·s | unknown子步 |
|---|---|---|---:|---:|---:|
| 8001/cold | prefix | true/1000 | 0 | 0 | 0 |
| 8001/cold | active | true/2000 | 1.483698924 | 0.7068551097 | 0 |
| 8001/learned | prefix | true/1000 | 0 | 0 | 0 |
| 8001/learned | active | true/2000 | 1.558282784 | 0.5465532329 | 0 |
| 8001/pd | prefix | true/1000 | 0 | 0 | 0 |
| 8001/pd | active | true/2000 | 1.428748932 | 0.4188226658 | 0 |
| 8001/zero | prefix | true/1000 | 0 | 0 | 0 |
| 8001/zero | active | true/2000 | 0 | 0 | 0 |
| 8002/cold | prefix | true/1000 | 0 | 0 | 0 |
| 8002/cold | active | true/2000 | 1.483711374 | 0.7068638269 | 0 |
| 8002/learned | prefix | true/1000 | 0 | 0 | 0 |
| 8002/learned | active | true/2000 | 1.536670233 | 0.5344869458 | 0 |
| 8002/pd | prefix | true/1000 | 0 | 0 | 0 |
| 8002/pd | active | true/2000 | 1.428811056 | 0.4188598229 | 0 |
| 8002/zero | prefix | true/1000 | 0 | 0 | 0 |
| 8002/zero | active | true/2000 | 0 | 0 | 0 |
| 8003/cold | prefix | true/1000 | 0 | 0 | 0 |
| 8003/cold | active | true/2000 | 1.531099117 | 0.7219809832 | 0 |
| 8003/learned | prefix | true/1000 | 0 | 0 | 0 |
| 8003/learned | active | true/2000 | 1.582424503 | 0.5740047491 | 0 |
| 8003/pd | prefix | true/1000 | 0 | 0 | 0 |
| 8003/pd | active | true/2000 | 1.467496123 | 0.443012514 | 0 |
| 8003/zero | prefix | true/1000 | 0 | 0 | 0 |
| 8003/zero | active | true/2000 | 0 | 0 | 0 |

## 全部保存费用与首审

| 保存counter | 值 |
|---|---:|
| GPU_training_seconds | 0 |
| MPC_decision_attempts | 1200 |
| MPC_decision_exceptions | 0 |
| MPC_decision_returns | 1200 |
| RLS_scalar_update_commits | 0 |
| RLS_vector_update_attempts | 0 |
| RLS_vector_update_commits | 0 |
| RLS_vector_update_exceptions | 0 |
| RLS_vector_update_returns | 0 |
| audit_contact_force_query_attempts | 281564 |
| audit_contact_force_query_returns | 281564 |
| audit_contact_pair_inspections | 281564 |
| audit_contact_snapshot_attempts | 36000 |
| audit_contact_snapshot_returns | 36000 |
| audit_geom_name_query_attempts | 281564 |
| audit_geom_name_query_returns | 281564 |
| batch_fit_calls | 0 |
| body_model_build_attempts | 6 |
| body_model_build_returns | 6 |
| body_model_fingerprint_attempts | 96 |
| body_model_fingerprint_returns | 96 |
| body_model_restoration_attempts | 6 |
| body_model_restoration_returns | 6 |
| body_model_snapshot_attempts | 6 |
| body_model_snapshot_returns | 6 |
| captured_native_endpoints | 36000 |
| captured_substep_endpoint_forward_returns | 36000 |
| collector_asset_read_bytes | 41160 |
| collector_asset_reads | 12 |
| confirmed_physics_substeps | 36000 |
| control_call_attempts | 36000 |
| control_call_exceptions | 0 |
| control_call_returns | 36000 |
| control_cold_pd_request_attempts | 3050 |
| control_cold_pd_request_returns | 3050 |
| control_conditional_prediction_axis_RMSE_vector_computations | 120 |
| control_conditional_prediction_feature_guard_projection_attempts | 526560 |
| control_conditional_prediction_feature_guard_projection_returns | 526560 |
| control_conditional_prediction_pair_prediction_attempts | 526560 |
| control_conditional_prediction_pair_prediction_returns | 526560 |
| control_conditional_prediction_scalar_prediction_attempts | 1053120 |
| control_conditional_prediction_scalar_prediction_returns | 1053120 |
| control_learned_pd_request_attempts | 6000 |
| control_learned_pd_request_returns | 6000 |
| control_pd_pd_request_attempts | 6000 |
| control_pd_pd_request_returns | 6000 |
| cpu_seconds | 607.765625 |
| environment_constructor_attempts | 12 |
| environment_constructor_returns | 12 |
| gate_file_read_attempts | 7 |
| gate_file_read_returns | 7 |
| gate_json_parses | 7 |
| gate_read_and_hash_bytes | 1150573 |
| git_query_attempts | 21 |
| git_return_bytes | 306509 |
| output_manifest_file_read_attempts | 1 |
| output_manifest_file_read_returns | 1 |
| output_manifest_read_and_hash_bytes | 58531512 |
| paid_interval_serialized_bytes | 521880891 |
| paid_interval_write_attempts | 72000 |
| paid_interval_write_returns | 72000 |
| physical_asset_bytes_read | 82320 |
| physical_asset_read_returns | 24 |
| physical_identity_attempts | 24 |
| physical_identity_returns | 24 |
| planning_batch_feature_batch_rows | 12715227 |
| planning_batch_original_scalar_dot_calls | 25430454 |
| planning_batch_serial_fallback_selections | 0 |
| planning_batch_stage_batches | 157293 |
| planning_fallback_returns | 295 |
| planning_feature_guard_projection_attempts | 12715227 |
| planning_feature_guard_projection_returns | 12715227 |
| planning_pair_prediction_attempts | 12715227 |
| planning_pair_prediction_returns | 12715227 |
| planning_pd_request_attempts | 12619227 |
| planning_pd_request_returns | 12619227 |
| planning_residual_candidate_attempts | 97200 |
| planning_returned_candidate_rejections | 23895 |
| planning_scalar_prediction_attempts | 25430454 |
| planning_scalar_prediction_returns | 25430454 |
| reset_attempts | 12 |
| reset_returns | 12 |
| source_file_read_attempts | 19 |
| source_file_read_returns | 19 |
| source_read_and_hash_bytes | 306468 |
| task_policy_updates | 0 |
| teacher_calls | 0 |
| wall_seconds | 613.5447988 |

内部计时/构造/forward/PD/guard/RLS/restore/snapshot/batch/接触/source与输出边界分别保留原件；未知内部I/O不补零，不宣称20ms实时。首次外进程wall=645.2132546s；Python3.10.11/NumPy2.2.6/MuJoCo3.15.0。

累计 **430,297控制调用 /2,709,970子步**；在线 **94,452**、离线 **7,200**，scalar更新计算合计 **101,652**。基点来自root显式提供的A后实际累计，加本次保存实际增量，不用计划预算替代停止成本。

主任务首次audit **passed，660,047checks/0failed，120个新RMSE向量**；[audit](../results/cpu_validation/2026-10-12_full_request_pair_control/audit_first/audit.json) · [指标复核](../results/cpu_validation/2026-10-12_full_request_pair_control/audit_first/metric_recheck.json)。audit事实仅由root CLI传入，writer不打开audit文件。保存一致不代替科学门。

## 下一步与边界

关闭本冻结候选的成功依赖；保留负结果，做一次有证据的有界下一判断，不补跑、扩大grid或放宽门。 阶段检查与正常提交推送后立即继续active目标。

scientific_adoption、old_free_root_C4_validation、c4_scientific_validation、c4_contact_scientific_validation、c5_scientific_dependency_released保持false。C4最终新留出及C5–C7尚未验收；零停止不能证明安全。全部停止、异常、未尝试及不利时距见本报告与完整JSON，未重新算RMSE/门、fit、模型或物理。
