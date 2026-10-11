# C4-A 左肘 PD 开发协议只读交叉复核

2026-10-11。只读 docs/ELBOW_PD_DEVELOPMENT_PROTOCOL.md（6223 bytes，SHA256 81b48a5117041fd98294b68d1d6af4f17df15c0228de3825016e313b2a7b12fd）。未运行物理、预测、拟合、排序/summary或新留出；不修改 tracked。以下是协议复核，不替代未来 runner/audit 代码及合成验收。

协议层面没有遗漏关键 failure 门，也没有把外部教师或已训练任务策略引入本阶段。PD 结构、当前任务目标、公开限位方向、原生感觉与100步零请求prefix属于公开初始信息；PD 本身已有位置控制能力，是具有任务能力的经典基线，不能称为无任务先验或从随机动作学成的身体技能。协议已经直接披露这些先验与结论边界，措辞可维持。

核对要点：

- j1 的选择来自公开0/1/2逐关节响应门及索引顺序，不从20–22或本次候选结果挑关节。失败不换 joint，不移用肩64/0作为已调肘基线；后续身体模型仍冷启动，不复用肩theta/P。
- supine/j1、baseline接触/.5Nm、另外七关节零请求、公开限位和环境保护固定。qref可负且保持原生；target+0.04/+0.08按当前披露，不预告。目标落在公共内缩域外即失败，不裁目标制造容易任务。
- exact seed/Kp/Kd顺序、9候选×3seed全部保留；每候选必须3seed各300完整调用/3000子步、无study/env/异常/非法/非有限才eligible。所有候选截断低RMSE都不能入选，末计划转移stop仍失败；无eligible明确选择失败，无默认获胜。
- 用三个原始tracking RMSE算术均值，精确并列再用active请求平方努力/Kp/Kd/candidate index；未按seed选择、未改为实际努力决胜、未取整/epsilon制造并列。调优就是额外开发交互，应与未来共同评价分账。
- StudyAbort每返回active端点≥.12/≥1，仅停止；prefix原环境门；study与env各自记录、环境主reason不遮蔽研究stop，不伪造环境终止flag。full terminal可评分但不能eligible；partial target原生误差/paid子步保留，不混20ms主RMSE。
- env.step尝试/返回/paid、已返回未存行与快照分别计；IO/trace/中断fatal标未开始blocked；普通失败继续原计划、无补跑。实际未知history不填零，requested/actual下界/缺失子步分别保存，停止理由/None主指标不填零。
- 27trial8100/81000=162s；prefix2700/27000、active5400/54000；模型/策略更新和教师/演示均0，当前累计基点208850/2088500/9900，完整后216950/2169500/9900，实际失败成本仍按原件付账。模拟时间不冒充CPU或动物发育时间。
- 风险full/prefix/control分别保留，8关节与子步/端点采样含义不混；无事后风险改善门，零stop不授予安全。j1标准库audit须真重算j1，而非重排数据或复用硬编码j0审计；已列负qref、独立StudyAbort、partial、末步stop、写盘fatal、无完整候选/排序合成验收项。

本阶段是开发强基线，不测试学习贡献，也不获得冷启动站立/行走或真机证据。正式C4评价仍需另冻结未见seed bank；20–22已经单肩揭晓，本次不再读取其轨迹用于调参。没有协议层面的实质阻塞；后续实现必须按本文件在正式采集前通过相应合成与全回归。
