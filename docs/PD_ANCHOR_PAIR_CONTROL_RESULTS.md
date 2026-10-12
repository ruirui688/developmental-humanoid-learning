# FR4B：FR4B首次PD锚点替换匹配控制（首次物理执行）

从clean `490fcffa0080125e7c2a8b887c99cc2743dcc01f` 首次物理控制执行一次，保存状态 **completed**；保存本域控制门未全部通过/不可评。实际新增36000控制返回/36000确认子步/0在线scalar提交；首新保存核验passed、674,441项/0失败。

[事前冻结协议](PD_ANCHOR_PAIR_LEARNING_PROTOCOL.md) · [根归档](../results/cpu_validation/2026-10-12_pd_anchor_pair_control/manifest.json) · [唯一实验输入](../results/cpu_validation/2026-10-12_pd_anchor_pair_control/report_inputs.json)

开发seed8101/8102/8103按冻结顺序；公开source/docs首次搜索无命中，raw/非公开历史未知，不宣称全局未用或最终留出。原free root/仰卧8轴身体、理想感觉、公开guard/保护、2ms PD64/Kd4_4、固定刺激与任务目标均为先验。没有任务教师、预训练策略、PPO或GPU。接触只资格/诊断，紧凑模型只含两轴q/v和已知final requests，不能宣称全身状态闭合、安全或真机学习。

## 保存状态、异常与全部未尝试

保存status=completed；complete_population=unknown。科学门、首保存核验与执行完整性分别报告，不用失败的默认false覆盖旧阶段事实。

保存顶层failure=None；各trial停止、异常、缺失仍须逐项报告，不能据此声称安全。

保存unattempted_seeds=[]；下方固定三个seed的所有planned trial均列出，缺失不补零。

## 全部12项匹配跟踪与实际努力

每seed cold+新MPC、learned+同新MPC、强PD、zero依次fresh/reset一次。各计划1000zero+2000active。cold/learned/PD必须完整且满足prefix/A/B域资格；zero接触只描述，停止不另加采用veto。

| seed | 方法 | 完整/域资格/score available | active已保存/计划 | joint/肩/肘RMSE rad | actual absolute Nm·s | actual squared Nm²·s | unknown努力子步 |
|---|---|---|---|---|---:|---:|---:|
| 8101 | cold | true/true/true | 2000/2000 | 0.0456304988/0.03928977927/0.05119177752 | 1.474352995 | 0.6921167968 | 0 |
| 8101 | learned | true/true/true | 2000/2000 | 0.007530326435/0.007895515187/0.007146500708 | 1.582364156 | 0.5479569777 | 0 |
| 8101 | pd | true/true/true | 2000/2000 | 0.007976217182/0.009462435056/0.006140228326 | 1.420417335 | 0.4139144822 | 0 |
| 8101 | zero | true/true/true | 2000/2000 | 0.06333080339/0.0634159441/0.06324554806 | 0 | 0 | 0 |
| 8102 | cold | true/true/true | 2000/2000 | 0.04060515483/0.03583879035/0.0448680098 | 1.757878361 | 0.841188875 | 0 |
| 8102 | learned | true/true/true | 2000/2000 | 0.007631882144/0.007864225138/0.00739224006 | 1.574425282 | 0.5562553106 | 0 |
| 8102 | pd | true/true/true | 2000/2000 | 0.008006025122/0.009519023021/0.00613034071 | 1.430911585 | 0.4200167694 | 0 |
| 8102 | zero | true/true/true | 2000/2000 | 0.06326765933/0.06328975876/0.06324555219 | 0 | 0 | 0 |
| 8103 | cold | true/true/true | 2000/2000 | 0.04396734502/0.03731021158/0.04974136075 | 1.536215125 | 0.7171984427 | 0 |
| 8103 | learned | true/true/true | 2000/2000 | 0.007574676085/0.007998737038/0.00712542219 | 1.60266078 | 0.566486465 | 0 |
| 8103 | pd | true/true/true | 2000/2000 | 0.00806839288/0.009636105282/0.006110924834 | 1.450700313 | 0.4320541737 | 0 |
| 8103 | zero | true/true/true | 2000/2000 | 0.06316557545/0.06308549439/0.06324555511 | 0 | 0 | 0 |

## 原控制门（保存值）

贡献门仍要求每seed joint/两轴严格改善，三seed原RMSE均值三指标各改善≥20%，actual absolute/squared两轴合计均值各≤1.05×cold。贡献通过才评PD：每seed三指标不劣、joint原均值改善≥5%，两种努力均值各≤1.05×PD；RMSE0百分比不可用、effort0要求candidate0。

| 比较 | available/passed | 基线joint/肩/肘均值 | learned均值 | 保存改善 | 各seed保存available/passed |
|---|---|---|---|---|---|
| cold贡献 | true/true | 0.04340099955/0.03747959373/0.04860038269 | 0.007578961555/0.007919492454/0.007221387653 | 82.5374%/78.8699%/85.1413% | 8101:true/true; 8102:true/true; 8103:true/true |
| 强PD参考 | true/false | 0.008016878395/0.009539187786/0.006127164624 | 0.007578961555/0.007919492454/0.007221387653 | 5.4624%/16.9794%/-17.8586% | 8101:true/false; 8102:true/false; 8103:true/false |

| 比较 | actual信号 | 保存基线均值 | learned均值 | 保存passed |
|---|---|---:|---:|---|
| cold | actual_absolute_two_axis_nm_s | 1.58948216 | 1.586483406 | true |
| cold | actual_squared_two_axis_nm2_s | 0.7501680382 | 0.5568995844 | true |
| PD | actual_absolute_two_axis_nm_s | 1.434009744 | 1.586483406 | false |
| PD | actual_squared_two_axis_nm2_s | 0.4219951417 | 0.5568995844 | false |

## 全部自身条件预测

六条自身来源分别用本seed两模型和已保存final requests递推；不pool、无事后self veto。下表保留全部五H、两轴q/v与availability（完整时120个向量）。FR4A通过不能覆盖自身有效域；planner 140步PD尾与actual再规划之差不能直接归因模型。

| seed/自身来源 | H/时距 | 预测模型 | available/observed/planned | q肩/肘 rad | v肩/肘 rad/s |
|---|---|---|---|---|---|
| 8101/cold | 1/2ms | cold | true/200/200 | 6.934756365e-05/0.0001148479662 | 0.03467378183/0.05742398308 |
| 8101/cold | 1/2ms | learned | true/200/200 | 5.96963673e-05/8.678379835e-05 | 0.02984818365/0.04339189918 |
| 8101/cold | 10/20ms | cold | true/200/200 | 0.002324621711/0.004638100201 | 0.1874422178/0.3823672648 |
| 8101/cold | 10/20ms | learned | true/200/200 | 0.001762759472/0.003593783813 | 0.1355187015/0.28419622 |
| 8101/cold | 20/40ms | cold | true/199/199 | 0.006352736135/0.0127610625 | 0.2571426001/0.5216601794 |
| 8101/cold | 20/40ms | learned | true/199/199 | 0.004352808088/0.008960497119 | 0.1600641025/0.3342274075 |
| 8101/cold | 50/100ms | cold | true/196/196 | 0.02321492892/0.04702644686 | 0.3579991211/0.7261014689 |
| 8101/cold | 50/100ms | learned | true/196/196 | 0.009532942018/0.01991679165 | 0.1715612352/0.3590958691 |
| 8101/cold | 150/300ms | cold | true/186/186 | 0.06153744513/0.1228424699 | 0.3160027446/0.631300945 |
| 8101/cold | 150/300ms | learned | true/186/186 | 0.009232187884/0.01903339281 | 0.1757370037/0.3668867717 |
| 8101/learned | 1/2ms | cold | true/200/200 | 2.835315158e-05/6.889987059e-05 | 0.01417657579/0.03444993529 |
| 8101/learned | 1/2ms | learned | true/200/200 | 2.148560134e-05/5.239238948e-05 | 0.01074280067/0.02619619474 |
| 8101/learned | 10/20ms | cold | true/200/200 | 0.00089669787/0.001924519356 | 0.06628161539/0.1380878168 |
| 8101/learned | 10/20ms | learned | true/200/200 | 0.0006560138136/0.001428790823 | 0.04785321009/0.1021642311 |
| 8101/learned | 20/40ms | cold | true/199/199 | 0.001839890471/0.003801335195 | 0.05889791409/0.1232169181 |
| 8101/learned | 20/40ms | learned | true/199/199 | 0.001376458991/0.00287861323 | 0.0490670266/0.10424365 |
| 8101/learned | 50/100ms | cold | true/196/196 | 0.006047618289/0.01190447998 | 0.09208028193/0.1741840546 |
| 8101/learned | 50/100ms | learned | true/196/196 | 0.003474414457/0.007173004247 | 0.04671013983/0.09913101535 |
| 8101/learned | 150/300ms | cold | true/186/186 | 0.02519651729/0.03974015833 | 0.1317386392/0.1746661145 |
| 8101/learned | 150/300ms | learned | true/186/186 | 0.007525159682/0.01520437244 | 0.04337140968/0.09239484713 |
| 8102/cold | 1/2ms | cold | true/200/200 | 6.88168322e-05/0.00012612378 | 0.0344084161/0.06306189002 |
| 8102/cold | 1/2ms | learned | true/200/200 | 5.239686431e-05/9.603427998e-05 | 0.02619843215/0.04801713999 |
| 8102/cold | 10/20ms | cold | true/200/200 | 0.002599291432/0.00529340167 | 0.2115301052/0.4328392766 |
| 8102/cold | 10/20ms | learned | true/200/200 | 0.001838650347/0.003875640609 | 0.1481146991/0.3118497143 |
| 8102/cold | 20/40ms | cold | true/199/199 | 0.006471455217/0.0131697942 | 0.2501972064/0.5120938012 |
| 8102/cold | 20/40ms | learned | true/199/199 | 0.004373303111/0.009165436024 | 0.1674869196/0.3508074778 |
| 8102/cold | 50/100ms | cold | true/196/196 | 0.02198141091/0.04471873688 | 0.338157858/0.6876020272 |
| 8102/cold | 50/100ms | learned | true/196/196 | 0.01028170824/0.02170272141 | 0.1746308712/0.366636289 |
| 8102/cold | 150/300ms | cold | true/186/186 | 0.06335967513/0.126837075 | 0.3020081189/0.6029351773 |
| 8102/cold | 150/300ms | learned | true/186/186 | 0.00991000647/0.02095248831 | 0.1813363866/0.3796880916 |
| 8102/learned | 1/2ms | cold | true/200/200 | 2.71577341e-05/5.842416345e-05 | 0.01357886705/0.02921208172 |
| 8102/learned | 1/2ms | learned | true/200/200 | 1.973411062e-05/4.539709556e-05 | 0.009867055311/0.02269854778 |
| 8102/learned | 10/20ms | cold | true/200/200 | 0.0008908087764/0.001836426363 | 0.06712249336/0.1352571484 |
| 8102/learned | 10/20ms | learned | true/200/200 | 0.0006473508201/0.001395687798 | 0.04910620022/0.1004789469 |
| 8102/learned | 20/40ms | cold | true/199/199 | 0.002052969618/0.004073360074 | 0.07112089156/0.1406788633 |
| 8102/learned | 20/40ms | learned | true/199/199 | 0.00146589599/0.00305798325 | 0.0530669384/0.1076552379 |
| 8102/learned | 50/100ms | cold | true/196/196 | 0.006484902062/0.01242409052 | 0.09811860395/0.1809689328 |
| 8102/learned | 50/100ms | learned | true/196/196 | 0.003538652492/0.007360470215 | 0.05018374083/0.1014448803 |
| 8102/learned | 150/300ms | cold | true/186/186 | 0.02638436019/0.04126381072 | 0.1379743575/0.1816901066 |
| 8102/learned | 150/300ms | learned | true/186/186 | 0.007344240917/0.01512245961 | 0.04735946778/0.09544463299 |
| 8103/cold | 1/2ms | cold | true/200/200 | 6.149466627e-05/0.0001110411 | 0.03074733313/0.05552055002 |
| 8103/cold | 1/2ms | learned | true/200/200 | 5.336323322e-05/9.029218314e-05 | 0.02668161661/0.04514609157 |
| 8103/cold | 10/20ms | cold | true/200/200 | 0.002262548087/0.004672763528 | 0.1925859475/0.3972184244 |
| 8103/cold | 10/20ms | learned | true/200/200 | 0.001716360079/0.003661637236 | 0.1415776486/0.2990020102 |
| 8103/cold | 20/40ms | cold | true/199/199 | 0.006221458023/0.01272708385 | 0.257694178/0.5258110549 |
| 8103/cold | 20/40ms | learned | true/199/199 | 0.004356103961/0.009144048901 | 0.1657638311/0.346316264 |
| 8103/cold | 50/100ms | cold | true/196/196 | 0.02291115734/0.04652690383 | 0.357112501/0.7255829824 |
| 8103/cold | 50/100ms | learned | true/196/196 | 0.009747708338/0.02041916612 | 0.1775609196/0.3709888958 |
| 8103/cold | 150/300ms | cold | true/186/186 | 0.06242995708/0.124730174 | 0.3209950897/0.6383838856 |
| 8103/cold | 150/300ms | learned | true/186/186 | 0.009521172914/0.01963118529 | 0.1821347982/0.3795842551 |
| 8103/learned | 1/2ms | cold | true/200/200 | 2.674678032e-05/6.481617995e-05 | 0.01337339016/0.03240808997 |
| 8103/learned | 1/2ms | learned | true/200/200 | 2.037623045e-05/4.988967485e-05 | 0.01018811522/0.02494483743 |
| 8103/learned | 10/20ms | cold | true/200/200 | 0.0008595331078/0.001812615967 | 0.06422873629/0.1319081718 |
| 8103/learned | 10/20ms | learned | true/200/200 | 0.0006298987162/0.00136003169 | 0.04658776054/0.09797422517 |
| 8103/learned | 20/40ms | cold | true/199/199 | 0.001812320878/0.003659217236 | 0.05867888551/0.1186249019 |
| 8103/learned | 20/40ms | learned | true/199/199 | 0.001353919164/0.002820952305 | 0.04845896441/0.1015207634 |
| 8103/learned | 50/100ms | cold | true/196/196 | 0.00601752386/0.0116424598 | 0.09225302656/0.1723331486 |
| 8103/learned | 50/100ms | learned | true/196/196 | 0.003416386209/0.007121911576 | 0.04576534936/0.09660761893 |
| 8103/learned | 150/300ms | cold | true/186/186 | 0.02549167588/0.03891790598 | 0.1337401835/0.167687303 |
| 8103/learned | 150/300ms | learned | true/186/186 | 0.007237060695/0.01508338762 | 0.04231598369/0.08955498864 |

## PD锚点结构与覆盖代价

每轴用当前clip PD替换nearest nominal九点slot，distance相同按原index；保持原slot Cartesian枚举81候选。delta0只保证纯PD rollout可表达，不保证feasible/chosen/较低努力或实际收益；仍按原forecast、cost与tie选择。替换每轴点位移最多.0625Nm，gap可达.1875Nm，±.5端点可丢，双轴可能只保留64原nominal对。新增PD候选和删除原点一起改变函数类；FR3保存诊断没有识别量化或缺PD为失败原因，不能称因果解释。

delta=替换点−当前clip PD仍可达±1，所有final请求仍±.5；首请求采用clip(p+(point−p))roundtrip，前10微步held delta与native反馈、后140预测PD尾，literal-zero fallback独立；cost、优化tie、保护和原20%/5%/1.05门不变。每macro18 scalar distance/2 nearest选择是额外工程计算，源码/spec数量说明不替代actual费用；缺少单独实测counter保留unknown，不补零。

FR4B的fr4a_prediction_gate_passed默认false仅表示本阶段未重宣FR4A；保留已通过的A报告，不以源检查失败的零物理尝试或本阶段默认值覆盖它。

## 全部trial、接触资格与实际努力

未尝试、停止与异常完整保留，未知值不补零。接触只资格/报告，不证明连续承重、因果或安全；actual为已保存2ms actuator_torque端点样本，不是未测连续积分。

| seed | trial | status/native完整/域资格 | 已返回/计划 | 停止/异常 |
|---|---|---|---|---|
| 8101 | cold | completed/true/true | 3000/3000 | 无 |
| 8101 | learned | completed/true/true | 3000/3000 | 无 |
| 8101 | pd | completed/true/true | 3000/3000 | 无 |
| 8101 | zero | completed/true/true | 3000/3000 | 无 |
| 8102 | cold | completed/true/true | 3000/3000 | 无 |
| 8102 | learned | completed/true/true | 3000/3000 | 无 |
| 8102 | pd | completed/true/true | 3000/3000 | 无 |
| 8102 | zero | completed/true/true | 3000/3000 | 无 |
| 8103 | cold | completed/true/true | 3000/3000 | 无 |
| 8103 | learned | completed/true/true | 3000/3000 | 无 |
| 8103 | pd | completed/true/true | 3000/3000 | 无 |
| 8103 | zero | completed/true/true | 3000/3000 | 无 |

| seed/trial | phase | 记录/计划 | 已付/已观察/unknown接触 | 左臂正端点 | feet正端点 | other正端点 | 资格 |
|---|---|---|---|---:|---:|---:|---|
| 8101/cold | prefix | 1000/1000 | 1000/1000/0 | 948 | 0 | 985 | true |
| 8101/cold | target_A | 1000/1000 | 1000/1000/0 | 961 | 0 | 1000 | true |
| 8101/cold | target_B | 1000/1000 | 1000/1000/0 | 899 | 0 | 1000 | true |
| 8101/learned | prefix | 1000/1000 | 1000/1000/0 | 948 | 0 | 985 | true |
| 8101/learned | target_A | 1000/1000 | 1000/1000/0 | 975 | 0 | 1000 | true |
| 8101/learned | target_B | 1000/1000 | 1000/1000/0 | 961 | 0 | 1000 | true |
| 8101/pd | prefix | 1000/1000 | 1000/1000/0 | 948 | 0 | 985 | true |
| 8101/pd | target_A | 1000/1000 | 1000/1000/0 | 990 | 0 | 1000 | true |
| 8101/pd | target_B | 1000/1000 | 1000/1000/0 | 989 | 0 | 1000 | true |
| 8101/zero | prefix | 1000/1000 | 1000/1000/0 | 948 | 0 | 985 | true |
| 8101/zero | target_A | 1000/1000 | 1000/1000/0 | 1000 | 0 | 1000 | true |
| 8101/zero | target_B | 1000/1000 | 1000/1000/0 | 1000 | 0 | 1000 | true |
| 8102/cold | prefix | 1000/1000 | 1000/1000/0 | 954 | 0 | 985 | true |
| 8102/cold | target_A | 1000/1000 | 1000/1000/0 | 959 | 0 | 1000 | true |
| 8102/cold | target_B | 1000/1000 | 1000/1000/0 | 908 | 0 | 1000 | true |
| 8102/learned | prefix | 1000/1000 | 1000/1000/0 | 954 | 0 | 985 | true |
| 8102/learned | target_A | 1000/1000 | 1000/1000/0 | 976 | 0 | 1000 | true |
| 8102/learned | target_B | 1000/1000 | 1000/1000/0 | 957 | 0 | 1000 | true |
| 8102/pd | prefix | 1000/1000 | 1000/1000/0 | 954 | 0 | 985 | true |
| 8102/pd | target_A | 1000/1000 | 1000/1000/0 | 990 | 0 | 1000 | true |
| 8102/pd | target_B | 1000/1000 | 1000/1000/0 | 988 | 0 | 1000 | true |
| 8102/zero | prefix | 1000/1000 | 1000/1000/0 | 954 | 0 | 985 | true |
| 8102/zero | target_A | 1000/1000 | 1000/1000/0 | 1000 | 0 | 1000 | true |
| 8102/zero | target_B | 1000/1000 | 1000/1000/0 | 1000 | 0 | 1000 | true |
| 8103/cold | prefix | 1000/1000 | 1000/1000/0 | 946 | 0 | 985 | true |
| 8103/cold | target_A | 1000/1000 | 1000/1000/0 | 962 | 0 | 1000 | true |
| 8103/cold | target_B | 1000/1000 | 1000/1000/0 | 889 | 0 | 1000 | true |
| 8103/learned | prefix | 1000/1000 | 1000/1000/0 | 946 | 0 | 985 | true |
| 8103/learned | target_A | 1000/1000 | 1000/1000/0 | 975 | 0 | 1000 | true |
| 8103/learned | target_B | 1000/1000 | 1000/1000/0 | 961 | 0 | 1000 | true |
| 8103/pd | prefix | 1000/1000 | 1000/1000/0 | 946 | 0 | 985 | true |
| 8103/pd | target_A | 1000/1000 | 1000/1000/0 | 990 | 0 | 1000 | true |
| 8103/pd | target_B | 1000/1000 | 1000/1000/0 | 987 | 0 | 1000 | true |
| 8103/zero | prefix | 1000/1000 | 1000/1000/0 | 946 | 0 | 985 | true |
| 8103/zero | target_A | 1000/1000 | 1000/1000/0 | 1000 | 0 | 1000 | true |
| 8103/zero | target_B | 1000/1000 | 1000/1000/0 | 1000 | 0 | 1000 | true |

| seed/trial | phase | 努力完整/已捕获 | actual absolute Nm·s | actual squared Nm²·s | unknown子步 |
|---|---|---|---:|---:|---:|
| 8101/cold | prefix | true/1000 | 0 | 0 | 0 |
| 8101/cold | active | true/2000 | 1.474352995 | 0.6921167968 | 0 |
| 8101/learned | prefix | true/1000 | 0 | 0 | 0 |
| 8101/learned | active | true/2000 | 1.582364156 | 0.5479569777 | 0 |
| 8101/pd | prefix | true/1000 | 0 | 0 | 0 |
| 8101/pd | active | true/2000 | 1.420417335 | 0.4139144822 | 0 |
| 8101/zero | prefix | true/1000 | 0 | 0 | 0 |
| 8101/zero | active | true/2000 | 0 | 0 | 0 |
| 8102/cold | prefix | true/1000 | 0 | 0 | 0 |
| 8102/cold | active | true/2000 | 1.757878361 | 0.841188875 | 0 |
| 8102/learned | prefix | true/1000 | 0 | 0 | 0 |
| 8102/learned | active | true/2000 | 1.574425282 | 0.5562553106 | 0 |
| 8102/pd | prefix | true/1000 | 0 | 0 | 0 |
| 8102/pd | active | true/2000 | 1.430911585 | 0.4200167694 | 0 |
| 8102/zero | prefix | true/1000 | 0 | 0 | 0 |
| 8102/zero | active | true/2000 | 0 | 0 | 0 |
| 8103/cold | prefix | true/1000 | 0 | 0 | 0 |
| 8103/cold | active | true/2000 | 1.536215125 | 0.7171984427 | 0 |
| 8103/learned | prefix | true/1000 | 0 | 0 | 0 |
| 8103/learned | active | true/2000 | 1.60266078 | 0.566486465 | 0 |
| 8103/pd | prefix | true/1000 | 0 | 0 | 0 |
| 8103/pd | active | true/2000 | 1.450700313 | 0.4320541737 | 0 |
| 8103/zero | prefix | true/1000 | 0 | 0 | 0 |
| 8103/zero | active | true/2000 | 0 | 0 | 0 |

## 四个独立stagekeys与五个科学flags

| 保存key | 保存值 |
|---|---|
| fr4a_prediction_gate_passed | false |
| fr4b_model_contribution_gate_passed | true |
| fr4b_pd_reference_gate_passed | false |
| fr4_free_root_mechanism_validation | false |
| scientific_adoption | false |
| old_free_root_C4_validation | false |
| c4_scientific_validation | false |
| c4_contact_scientific_validation | false |
| c5_scientific_dependency_released | false |

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
| audit_contact_force_query_attempts | 281444 |
| audit_contact_force_query_returns | 281444 |
| audit_contact_pair_inspections | 281444 |
| audit_contact_snapshot_attempts | 36000 |
| audit_contact_snapshot_returns | 36000 |
| audit_geom_name_query_attempts | 281444 |
| audit_geom_name_query_returns | 281444 |
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
| control_cold_pd_request_attempts | 3290 |
| control_cold_pd_request_returns | 3290 |
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
| cpu_seconds | 1001.84375 |
| environment_constructor_attempts | 12 |
| environment_constructor_returns | 12 |
| gate_file_read_attempts | 7 |
| gate_file_read_returns | 7 |
| gate_json_parses | 7 |
| gate_read_and_hash_bytes | 1151311 |
| git_query_attempts | 21 |
| git_return_bytes | 312065 |
| output_manifest_file_read_attempts | 1 |
| output_manifest_file_read_returns | 1 |
| output_manifest_read_and_hash_bytes | 58819808 |
| paid_interval_serialized_bytes | 522973408 |
| paid_interval_write_attempts | 72000 |
| paid_interval_write_returns | 72000 |
| physical_asset_bytes_read | 82320 |
| physical_asset_read_returns | 24 |
| physical_identity_attempts | 24 |
| physical_identity_returns | 24 |
| planning_batch_feature_batch_rows | 12908736 |
| planning_batch_original_scalar_dot_calls | 25817472 |
| planning_batch_serial_fallback_selections | 0 |
| planning_batch_stage_batches | 159662 |
| planning_fallback_returns | 271 |
| planning_feature_guard_projection_attempts | 12908736 |
| planning_feature_guard_projection_returns | 12908736 |
| planning_pair_prediction_attempts | 12908736 |
| planning_pair_prediction_returns | 12908736 |
| planning_pd_request_attempts | 12812736 |
| planning_pd_request_returns | 12812736 |
| planning_residual_candidate_attempts | 97200 |
| planning_returned_candidate_rejections | 22122 |
| planning_scalar_prediction_attempts | 25817472 |
| planning_scalar_prediction_returns | 25817472 |
| reset_attempts | 12 |
| reset_returns | 12 |
| source_file_read_attempts | 19 |
| source_file_read_returns | 19 |
| source_read_and_hash_bytes | 312024 |
| task_policy_updates | 0 |
| teacher_calls | 0 |
| wall_seconds | 2453.049567 |

内部计时/构造/forward/PD/guard/RLS/restore/snapshot/batch/接触/source与输出边界分别保留原件；未知内部I/O不补零，不宣称20ms实时。首次外进程wall=2487.56671s；Python3.10.11/NumPy2.2.6/MuJoCo3.15.0。

累计 **487297控制调用 /2766970子步**；在线 **118452**、离线 **7200**，scalar更新计算合计 **125652**。基点为root显式CLI提供的本阶段前actual累计，只加本次保存实际增量；缺失counter保持unknown，不用计划替代停止成本或补零。

主任务首次audit **passed，674,441checks/0failed，120个新RMSE向量**；[audit](../results/cpu_validation/2026-10-12_pd_anchor_pair_control/audit_first/audit.json) · [指标复核](../results/cpu_validation/2026-10-12_pd_anchor_pair_control/audit_first/metric_recheck.json)。audit事实仅由root CLI传入，writer不打开audit文件。保存一致不代替科学门。

## 下一步与边界

关闭本冻结候选的成功依赖；保留负结果，做一次有证据的有界下一判断，不补跑、scan/扩大grid、改权重或放宽门。 阶段检查与正常提交推送后立即继续active目标。

scientific_adoption、old_free_root_C4_validation、c4_scientific_validation、c4_contact_scientific_validation、c5_scientific_dependency_released保持false。C4最终新留出及C5–C7尚未验收；零停止不能证明安全。全部停止、异常、未尝试及不利时距见本报告与完整JSON；writer未重算RMSE/门、fit、模型或物理。
