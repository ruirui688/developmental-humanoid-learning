# 地面身体探索：子步冲击与固定动作复现协议

> 2026-10-10；在新增诊断采集前冻结。本阶段不训练、不改变身体、动作权限或探索分布。

上一轮完整矩阵仅在 20 ms 控制终点记录接触指标，采样最大法向力 895.07 N，不能代表全部 2 ms 物理子步的最大值。下一项问题是：这个采样遗漏有多大；较大接触力主要出现于同初态零力矩的被动落地，还是持续探索期间？

## 固定条件与预算

- 复用完整 [24 组身体探索矩阵](GROUND_BODY_RESULTS.md)：四种躺姿、根 seed 0/1/2、零力矩与平滑随机命令、每试验 250 控制步。
- 共享完全相同的资产、物理参数、执行器、限位保护、派生随机流、原生观测和停止条件；只加特权子步诊断。
- 新增 6,000 控制步、60,000 物理子步；这也是额外交互，应与此前采集累计计账。若停止/非有限值/写盘失败则保留全部失败数据，不补成成功。
- 模型、策略、门控参数更新为 0；不添加接触教师、参考动作或反馈策略。

## 记录与验收

每次真实积分后记录全部地面接触的法向力之和、动能和最小接触距离，再检查停止。日志给出各子步列表、真实执行子步数、采样最大值，以及法向力时间积分，部分控制步按实际长度计账。法向力积分包含持续重力支撑，不能直接叫“碰撞冲量”。有限步长下的采样也不是连续时间上界。

独立测试通过 `mj_contactForce` 在真实积分终点核对子步列表，验证短时峰值可能高于控制终点、提前停止预算不多计；raw-engine 回放确认增加遥测没有改变状态、传感器或实际命令。特权字段不得进入探索器观测。

完整采集后逐控制步与旧冻结轨迹比较 `qpos`、`qvel`、所有原生观测和实际子步力矩；本机相同版本/配置要求精确相等。若不相等，先报告复现偏差，不能把新曲线称为原实验更密的观测。

时间窗预先固定为 **0–0.5 s** 与 **0.5–5 s**，分别报告采样最大值与法向力积分；同时报告真正发生峰值的时间，避免把窗口名当作动力学因果证明。所有 seed 保留，组间仅做描述比较，不进行学习效率统计检验。

## 复现

```powershell
$env:PYTHONPATH = "src"
external/cpu_physics_env/Scripts/python.exe -m pytest -q tests/test_ground_body_substep_telemetry.py
external/cpu_physics_env/Scripts/python.exe -m developmental_physics.collect --output results/cpu_validation/ground_impacts_local --seeds 0 1 2 --steps 250
python scripts/analyze_ground_body_impacts.py results/cpu_validation/ground_impacts_local --reference results/cpu_validation/2026-10-10_ground_body_verified --output results/cpu_validation/ground_impacts_profile_local.json
```

根据结果再决定是否准备初态/接触柔顺性的无训练对照。当前不修改身体或支撑来降低数字，不把更多停止或更小动作幅度称为能力提高，也不因为有了接触真值便声称身体模型已形成。
