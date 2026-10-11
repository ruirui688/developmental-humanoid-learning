# 左肘 body 归档最终只读复核

核对 240 项，失败 0。归档含41个有hash的文件及manifest本身；19份source ZIP成员逐份匹配 clean 46077b1d30089d68f1c935e3fc547dfdfa4c4e66 的Git原字节。没有重新运行物理、模型预测/拟合、audit或summary，没有tracked/Git修改。

manifest SHA256 `1072815dc76dbe6aa77d4d3cbd0c2c737a9ad625166e9b87d3da84045603782d`；结果文档 SHA256 `f2614c492ff58c50f88eac0ccbebc1e6aae55111326ee5733f0b8e6b3b12a951`。

费用来自episodes实际计数：5292调用/52920子步/900更新；与metadata、audit、summary及manifest一致。提交前协议中的既有实际基点216371/2163710/9900加本批，累计221663/2216630/10800正确，未用6000/60000计划数替代失败成本。

21trial包含15完整、6研究停止、0环境停止、0异常；三seed满幅预测step150/active50、151 paid calls速度停止，三seed learned MPC step112/active12、113 calls位置停止。后者只有13次active控制，不可与完整200次PD作优势百分比或努力排序。5门和6门均false/unevaluated，7矩阵false独立保留。

文档低幅逐seed速度、11.09%–11.40%降低、learned截断tracking与PD完整tracking均与保存summary一致。seed1满幅停止v=-1.0343372360978609，文档约-1.034符合近似表达。三seed各300更新、原生j1负qref、实际130/130子步/零屏蔽/零fallback证据一致。

人工措辞审读：文档把数据一致与算法门失败分开，明确cal完成不等于控制有效；没有由截断误差、努力或零环境停止声称优势/节能/安全。只使用首3与停止步选择，未泛化所有中间命令。模型恢复预测偏差可作诊断，未把遗漏耦合或guard条件当已识别因果，也未保证双关节模型必修复。下一版5步脉冲是开发候选，校准和满幅预测的时序/幅值同时不同，本批不能孤立识别脉冲长度因果；现文明确成功/风险待检验、无安全结论。

同配方跨肩肘未通过新增关节验收，不能由单肩局部通过推出通用全身能力。当前文档的范围为指定配方/任务；未作未见seed、全身技能或真机结论。首次合成8测试中1失败和修复后通过原字节保存，01源码逆向重建明确生成件，未冒充当时执行快照。

离线复核wall=1.4162802000064403 s，Python review CPU=0.15625 s；另起git只读进程CPU未单独测量。计时包括hash、JSON读取、19份ZIP/Git及6份archived Git blob核验、文档检查；止于输出JSON/Markdown写盘前。

附核对JSON：`external/c4_elbow_archive_final_review.json`。源脚本：`external/c4_elbow_archive_final_review.py`。

| seed | kind | step | q-qref | v | trigger |
|---|---|---:|---:|---:|---|
| 0 | prediction_full | 150 | 0.035137575270811114 | -1.0291313384819958 | absolute_velocity_rad_s |
| 0 | learned_mpc | 112 | 0.12039474156168053 | 0.57038509274697047 | absolute_q_minus_qref_rad |
| 1 | prediction_full | 150 | 0.035016957769176446 | -1.0343372360978609 | absolute_velocity_rad_s |
| 1 | learned_mpc | 112 | 0.12022883766155333 | 0.56945581900933828 | absolute_q_minus_qref_rad |
| 2 | prediction_full | 150 | 0.035273299870910081 | -1.0282196959908183 | absolute_velocity_rad_s |
| 2 | learned_mpc | 112 | 0.12057874192864057 | 0.57139419891216947 | absolute_q_minus_qref_rad |

## 后续入口同步复核

root同步后只读检查README、AGENTS、连续计划和PROGRESS：13项、0失败。README明确最新15完整/6停止与5292/52920/900，后三文件最新累计221663/2216630/10800，负门措辞一致。PROGRESS保留的旧未执行描述由文件头明确历史检查点，不作为当前结果。

补充wall=0.0007450999692082405 s，CPU=0.0 s；hash/核对项见external/c4_elbow_tracked_sync_review.json。没有原件改动或重新计算模型/audit/summary。
