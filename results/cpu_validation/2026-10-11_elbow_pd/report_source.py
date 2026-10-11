"""Format only the completed summary artifact; never reread raw archive/audit."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT/"external/elbow_pd_20261011_summary_01_summary.json"
OUTPUT = ROOT/"external/elbow_pd_20261011_summary_delivery.md"
EXECUTION = ROOT/"external/elbow_pd_20261011_report_execution.json"
started, cpu = time.perf_counter(), time.process_time()
data = SOURCE.read_bytes()
summary = json.loads(data)
lines = ["# C4-A 左肘 PD 开发：单次独立汇总", "",
    "本报告只格式化已完成的 summary JSON；未重新读取原始轨迹或首次audit，未运行物理、audit、模型或训练。原始量和失败均在不可覆盖的 summary 中保留。",
    "", f"采集源码 `{summary['source_commit']}`；首次审计352,833项零失败；本次原生j1独立汇总84,356项零失败。",
    "", "**开发选择：candidate8 / Kp64 / Kd1。** 原始三seed tracking均值0.006209216810408326 rad；精确请求平方努力决胜量均值0.24873701123073969 N²m²s。这是离线经典开发选择，不是身体学习优势。",
    "", "## 所有候选（原始量不取整用于排序）", "",
    "| candidate | Kp | Kd | 完整seed数 | 三seed tracking RMSE | eligible 原始均值 | eligible 请求平方均值 |",
    "|---|---:|---:|---:|---|---:|---:|"]
for c in summary["candidates"]:
    rows = [r for r in summary["trials"] if r["candidate"] == c["candidate"]]
    lines.append(f"| {c['candidate']} | {c['kp']} | {c['kd']} | {sum(r['eligible'] for r in rows)} | {c['per_seed_tracking_rmse_rad']} | {c['mean_tracking_rmse_rad']} | {c['mean_requested_squared_effort_nm2s']} |")
lines += ["", "## 失败与风险", "",
    "candidate6 / Kp64 / Kd0 的三个seed均提前研究停止：它们的截断RMSE保留，但不参与选择。不能移用单肩64/0。研究停止只结束采集，未加入制动；零环境停止不是安全证明。", "",
    "| trial | 调用/子步 | 主评分端点 | 原生qref | 研究停止端点 | 终点v(rad/s) | 理由 |", "|---|---|---:|---:|---:|---:|---|"]
for r in summary["trials"]:
    if not r["eligible"]:
        stop = r["stops"][-1] if r["stops"] else None
        raw_stop = r["collector_episode_record"].get("study_abort") or {}
        lines.append(f"| {r['trial_id']} | {r['paid_budget']['control_steps']}/{r['paid_budget']['physics_steps']} | {r['scored_complete_endpoints']} | {r['qref_rad']} | {None if stop is None else stop['index']} | {raw_stop.get('velocity_rad_s')} | {raw_stop.get('triggers', r['reason'])} |")
lines += ["", "风险计入已付费 prefix/full；下表只是汇总展示，全部八关节限位、屏蔽、速度、接触冲量及努力在summary逐trial保存。峰值不能与学习收益混写。", "",
    "| candidate | full接触峰(N)最大 | prefix接触峰(N)最大 | control接触峰(N)最大 | 最深穿透(m) | 最大全关节端点速度(rad/s) | active实际绝对努力均值 | active实际平方努力均值 |",
    "|---|---:|---:|---:|---:|---:|---:|---:|"]
for c in summary["candidates"]:
    rows = [r for r in summary["trials"] if r["candidate"] == c["candidate"]]
    peaks = [max(r["phase_risk"][p]["ground_force_peak_n"] for r in rows) for p in ("full", "prefix", "control")]
    penetration = max(r["phase_risk"]["full"]["penetration_peak_m"] for r in rows)
    speed = max(max(r["phase_risk"]["full"]["joint_speed_peak_rad_s"]) for r in rows)
    actual = [sum(r["phase_effort"]["control"][key] for r in rows)/3 for key in ("actual_absolute_effort_nms", "actual_squared_effort_nm2s")]
    lines.append(f"| {c['candidate']} | {peaks[0]} | {peaks[1]} | {peaks[2]} | {penetration} | {speed} | {actual[0]} | {actual[1]} |")
budget = summary["budget"]
lines += ["", "## 成本与下一步", "",
    f"27 attempted / 24完整 / 3研究停止 / 0异常；实际{budget['control_calls_attempted']}调用/{budget['physics_steps']}子步，模拟时间{budget['simulated_seconds']}s，身体/策略/增益更新0。所有候选与全部prefix均属于增益调优成本。prefix为2700调用/27000子步；control为4821/48210。",
    "", "采集wall18.052950200159103 s、CPU17.953125 s；summary wall1.3255032000597566 s、CPU1.265625 s；wrapper wall1.5780213000252843 s、CPU1.34375 s，均不等于动物的现实学习时长。",
    "", "正式物理累加：208850+7521=216371调用；2088500+75210=2163710子步；RLS仍9900。之后左肘固定short/old/hinge5/Euler应单独冻结协议，不复用肩theta/P，PD64/1选择来源及本轮调优成本需披露；继续body及肩—肘协调，持续目标不在此停止。",
    "", "## 原件与执行来源", "",
    f"summary SHA256 `{hashlib.sha256(data).hexdigest()}`；summary source `563e28ac3f99c5776a06e21152c6aebaefbea1b737437def8df48fc2c17c98c2`；wrapper `41f15be6bc56d31864a413821495aa236c181d88f93279c5322f37ffb0cc0e21`；stdout `ff934eb1ce51fcc4c0e61e7c8cba08dee9a0b85d3fc138356344532657d28804`；execution `a14be2fa12ff99451f9373c6b9d10571c3df2841a2e59533b8acd3531513ab8b`。",
    "", "路径前缀 `external/elbow_pd_20261011_summary_01_`：summary.json、summary_executed.py、wrapper_executed.py、stdout.txt、execution.json、attempt.json。Permanent attempt marker防止静默复跑，首次失败也会消费次数。所有输入hash和collector源码/依赖/配置均保留。", ""]
with OUTPUT.open("x", encoding="utf-8", newline="\n") as stream:
    stream.write("\n".join(lines))
record = {"created_at_utc": datetime.now(timezone.utc).isoformat(), "purpose": __doc__,
    "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), "input_summary_sha256": hashlib.sha256(data).hexdigest(),
    "output_sha256": hashlib.sha256(OUTPUT.read_bytes()).hexdigest(), "wall_seconds": time.perf_counter()-started,
    "cpu_seconds": time.process_time()-cpu, "raw_archive_reads": 0, "audit_reads": 0, "summary_executions": 0,
    "physical_calls": 0, "parameter_updates": 0}
with EXECUTION.open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(record, stream, indent=2)
    stream.write("\n")
print(json.dumps({"report": str(OUTPUT), **record}))
