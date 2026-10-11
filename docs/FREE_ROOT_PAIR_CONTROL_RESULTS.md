# FR2：自由root双关节完整匹配控制首次结果

从clean `f9a0e0062727fd756751e97f7aff850e2069340c` 首次执行一次，保存状态 **completed**；本域原控制门未全部通过。本次实际36,000控制返回/36,000确认子步，0新增RLS；首新保存核验passed、77,669项/0失败。模型贡献门保存值为false，强PD门available=false/passed=false。

[事前冻结协议](FREE_ROOT_LEARNING_PROTOCOL.md) · [本次根归档](../results/cpu_validation/2026-10-12_free_root_pair_control/manifest.json) · [完整报告输入](../results/cpu_validation/2026-10-12_free_root_pair_control/report_inputs.json)

## 完整跟踪与实际努力矩阵

按seed依次cold+MPC、learned+MPC、强PD、zero四个fresh对象；各计划1,000zero prefix+2,000active。下表保留全部计划12项，包括停止、不完整及未尝试。RMSE仅完整且符合所需域资格的2000active人口可用，数对/三元组分别肩/肘或joint/肩/肘。actual为已保存2ms端点样本的两轴合计；不完整努力是已知下界，unknown不补零。

| seed | 方法 | 原生完整/域资格 | active已保存/计划 | joint/肩/肘RMSE rad | actual absolute Nm·s | actual squared Nm²·s | actual unknown子步 | 停止/异常 |
|---|---|---|---|---|---:|---:|---|---|
| 7901 | cold | true/true | 2000/2000 | 0.0087011419/0.010343389/0.0066658863 | 1.5048002 | 0.45956969 | 0 | 无 |
| 7901 | learned | true/true | 2000/2000 | 0.0076378302/0.0091945319/0.0056686405 | 1.4787614 | 0.45189675 | 0 | 无 |
| 7901 | pd | true/true | 2000/2000 | 0.0079681152/0.0094470832/0.0061428282 | 1.4175569 | 0.41223339 | 0 | 无 |
| 7901 | zero | true/true | 2000/2000 | 0.063349847/0.063453975/0.063245546 | 0 | 0 | 0 | 无 |
| 7902 | cold | true/true | 2000/2000 | 0.0087538647/0.010443563/0.0066477273 | 1.5214987 | 0.46944586 | 0 | 无 |
| 7902 | learned | true/true | 2000/2000 | 0.0076782133/0.0092600848/0.0056710447 | 1.4953413 | 0.46170167 | 0 | 无 |
| 7902 | pd | true/true | 2000/2000 | 0.008012912/0.009532031/0.0061281238 | 1.4331731 | 0.4213885 | 0 | 无 |
| 7902 | zero | true/true | 2000/2000 | 0.063255183/0.063264813/0.063245553 | 0 | 0 | 0 | 无 |
| 7903 | cold | true/true | 2000/2000 | 0.0087794951/0.010490916/0.0066407641 | 1.5280296 | 0.4737857 | 0 | 无 |
| 7903 | learned | true/true | 2000/2000 | 0.0076921877/0.0092826858/0.0056719704 | 1.5016447 | 0.46548824 | 0 | 无 |
| 7903 | pd | true/true | 2000/2000 | 0.0080339073/0.0095715039/0.0061215723 | 1.4397922 | 0.42542374 | 0 | 无 |
| 7903 | zero | true/true | 2000/2000 | 0.063220091/0.063194617/0.063245554 | 0 | 0 | 0 | 无 |

cold/learned/PD采用所需prefix/A/B各1000完整phase至少一个left_arm-floor正端点；zero接触仅描述，zero停止不是新增采用veto。原自由root/仰卧、理想感觉、2ms经典PD、公开guard与目标均为披露先验。零停止不能解释为安全收益，接触共现不能解释为持续支撑或接触因果。

## 原控制门

保存的三seed原RMSE算术均值直接转录，未重新计算。模型贡献要求各seed joint/两轴严格改善，三均值各改善≥20%；强PD比较以前门通过为前置，各seed三指标不劣、joint均值改善≥5%。两比较的actual absolute/squared两轴合计均值各≤1.05×基线；baseline effort0要求candidate0，RMSE0百分比不可用。

| 比较 | available/passed | 基线joint/肩/肘均值 | learned joint/肩/肘均值 | 保存改善 | 三seed逐项保存结果 |
|---|---|---|---|---|---|
| cold模型贡献 | true/false | 0.0087448339/0.010425956/0.0066514592 | 0.0076694104/0.0092457675/0.0056705518 | 12.2978%/11.3197%/14.7473% | 7901:true/true; 7902:true/true; 7903:true/true |
| 强PD参考 | false/false | 不可评 | 不可评 | 不可评 | 不可评 |

模型贡献前置失败，正式PD门不可评；保留PD实际轨迹，不以事后比较宣告强PD门通过。

| actual努力比较 | 信号 | 保存基线均值 | learned均值 | 保存passed |
|---|---|---:|---:|---|
| cold | actual_absolute_two_axis_nm_s | 1.5181095 | 1.4919158 | true |
| cold | actual_squared_two_axis_nm2_s | 0.46760041 | 0.45969555 | true |

## 自身条件预测：全部来源和时距

六种来源为三个seed各自cold/learned控制轨迹，分别用本seed两个冻结模型、相同已保存final requests递推；不pool不同自身人口。下表每格为cold预测模型/learned预测模型的保存availability。q/v两轴原RMSE、planned/observed origins及所有H1/10/20/50/150均完整保存在[完整条件JSON](../results/cpu_validation/2026-10-12_free_root_pair_control/report_inputs.json)的seed_results[].conditional_prediction_scores；该链接保留所有结果，不删不利时距或失败来源。

| seed/自身来源 | H1 2ms | H10 20ms | H20 40ms | H50 100ms | H150 300ms |
|---|---|---|---|---|---|
| 7901/cold | true/true | true/true | true/true | true/true | true/true |
| 7901/learned | true/true | true/true | true/true | true/true | true/true |
| 7902/cold | true/true | true/true | true/true | true/true | true/true |
| 7902/learned | true/true | true/true | true/true | true/true | true/true |
| 7903/cold | true/true | true/true | true/true | true/true | true/true |
| 7903/learned | true/true | true/true | true/true | true/true | true/true |

重点公开H150肩q/v，完整肘及其他时距仍见上述JSON；以下为保存RMSE，不计算新差值/百分比，不以部分finite点排名。

| seed/自身来源 | 预测模型 | H150保存available/observed origins | 肩q RMSE rad | 肩v RMSE rad/s |
|---|---|---|---:|---:|
| 7901/cold | cold | true/186 | 0.019282758 | 0.11306647 |
| 7901/cold | learned | true/186 | 0.0056990927 | 0.028524387 |
| 7901/learned | cold | true/186 | 0.02008936 | 0.11707616 |
| 7901/learned | learned | true/186 | 0.0064787519 | 0.028625065 |
| 7902/cold | cold | true/186 | 0.019448185 | 0.114646 |
| 7902/cold | learned | true/186 | 0.0055611746 | 0.028338722 |
| 7902/learned | cold | true/186 | 0.020340282 | 0.11809336 |
| 7902/learned | learned | true/186 | 0.0063338331 | 0.028421086 |
| 7903/cold | cold | true/186 | 0.019551483 | 0.11510844 |
| 7903/cold | learned | true/186 | 0.0055061919 | 0.028146658 |
| 7903/learned | cold | true/186 | 0.020536725 | 0.11887003 |
| 7903/learned | learned | true/186 | 0.0062781095 | 0.028354857 |

planner H150使用当前target、首10步held residual及其后PD尾；actual随后会再规划。不能把planner与actual差直接归因模型。条件评分使用实际保存requests，独立FR1通过不覆盖自身有效域；即使控制门通过也不宣称闭环预测普适改善。

## 实际费用与首次核验

| 费用 | 本次保存值 |
|---|---:|
| 控制attempts | 36000 |
| 控制returns | 36000 |
| 确认物理子步 | 36000 |
| 控制异常 | 0 |
| MPC attempts | 1200 |
| MPC returns | 1200 |
| MPC exceptions | 0 |
| planning pair attempts | 14569200 |
| planning scalar attempts | 29138400 |
| 自身条件pair attempts | 526560 |
| 自身条件scalar attempts | 1053120 |
| batch stage kernels | 179868 |
| batch feature rows | 14569200 |
| 原scalar dots | 29138400 |
| serial fallback selections | 0 |
| audit snapshots | 36000 |
| contact force queries | 281885 |

0新增RLS/任务策略学习，恢复、构造、clone/snapshot、PD、模型/guard前向与batch kernel分别保留实际计账，缺字段不填0。完整预算最多36,000控制/子步与1,200MPC决策；失败/候选拒绝按实际费用保留，不把少计算当效率优势。内部wall/CPU为700.78251/694.125s，外部首进程wall为735.11725s；最终压缩/写盘等边界见原件，未测内部构造/OS I/O不补零，不宣称实时。

累计 **373,297控制调用 /2,652,970子步**；在线70,452+离线7,200=77,652scalar更新计算保持。本次实际增量计账，原停止/失败、FR1辨识及准备检查费用不归零。

主任务首次新保存核验 **passed，77,669 checks/0 failed**。 新条件RMSE向量核对120个。 [首次audit](../results/cpu_validation/2026-10-12_free_root_pair_control/audit_first/audit.json) · [新指标复核](../results/cpu_validation/2026-10-12_free_root_pair_control/audit_first/metric_recheck.json)。核验源码及首stdout/stderr同存。

报告只读取本次report_inputs.json；首audit事实由root传入。0模型/fit/物理/旧科学重算。核验只证明保存一致，不能代替科学门。

## 当前边界与下一步

关闭本冻结候选的成功依赖，不补跑或放宽门；依据本次完整保存证据做一次有界判断，再确定独立下一项。 阶段必要检查、正常提交推送后立即继续active目标。

本域开发成功也不等于C4最终新留出通过。scientific_adoption、old_free_root_C4_validation、c4_scientific_validation、c4_contact_scientific_validation、c5_scientific_dependency_released保持false；C5适应、C6成熟机制和C7综合验收仍未完成。任何停止与不利自身预测完整公开，不补跑或改门。
