"""Read saved C records once; stdlib only, no model imports or recomputation.

Saved future encoders are offline diagnostic labels. This tool copies causal
saved predictions/selected H15 trajectories and computes ranges/errors only.
It never fits, predicts, plans, audits, simulates, ranks trials or judges gates.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import gzip
import hashlib
import io
import json
import math
from pathlib import Path
import time

STAGE = Path(__file__).resolve().parent
RAW_FILES = ("metadata.json", "episodes.json", "seed_results.json", "trace.jsonl.gz", "source_snapshot.zip", "manifest.json")
EXPECTED_COMMIT = "5ea8df42b09588845760daf0dc1f270aef2a87f1"
EXPECTED_AUDITOR = "962a928b5d643ed2a3d4da20da2940a9a4e17932818c859beb204f11bf59ffa3"
CAL_KINDS = {"calibration_sparse": "learned_sparse", "calibration_continuation": "learned_continuation"}
LEARNED = tuple(CAL_KINDS.values())


def pair(value):
    if not isinstance(value, (list, tuple)) or len(value) < 2:
        raise ValueError("saved native/predicted pair missing")
    result = [float(x) for x in value[:2]]
    if any(not math.isfinite(x) for x in result):
        raise ValueError("nonfinite saved pair")
    return result


class Range:
    def __init__(self):
        self.values = []

    def add(self, value):
        value = float(value)
        if not math.isfinite(value):
            raise ValueError("nonfinite range input")
        self.values.append(value)

    def report(self):
        values = self.values
        return {"samples": len(values), "minimum": min(values) if values else None,
            "maximum": max(values) if values else None, "span": max(values)-min(values) if values else None,
            "nonzero_samples": sum(x != 0. for x in values), "exact_unique_values": len(set(values)),
            "exactly_constant": len(set(values)) == 1 if values else None}


class Runs:
    """Nonzero episode lengths with explicit zero/gap/unknown boundaries."""
    def __init__(self, unit, dt):
        self.unit, self.dt = unit, dt
        self.active = {key: 0 for key in ("axis0", "axis1", "joint_any", "joint_both")}
        self.hist = {key: Counter() for key in self.active}
        self.last_index = None
        self.samples = self.unknown_samples = self.gap_boundaries = 0

    def close(self):
        for key, value in self.active.items():
            if value:
                self.hist[key][value] += 1
            self.active[key] = 0

    def observe(self, index, value):
        if self.last_index is not None and index != self.last_index+1:
            self.close(); self.gap_boundaries += 1
        self.last_index = index
        if value is None:
            self.close(); self.unknown_samples += 1
            return
        a, b = pair(value)
        flags = {"axis0": a != 0., "axis1": b != 0., "joint_any": a != 0. or b != 0., "joint_both": a != 0. and b != 0.}
        self.samples += 1
        for key, flag in flags.items():
            if flag:
                self.active[key] += 1
            elif self.active[key]:
                self.hist[key][self.active[key]] += 1
                self.active[key] = 0

    def report(self):
        self.close()
        return {"unit": self.unit, "nominal_unit_seconds": self.dt,
            "known_samples": self.samples, "unknown_samples": self.unknown_samples,
            "gap_boundaries": self.gap_boundaries, "nonzero_definition": "exact saved value != 0, no tuned threshold",
            "run_length_distributions": {key: {"histogram": dict(sorted(hist.items())),
                "run_count": sum(hist.values()), "maximum_length": max(hist, default=0),
                "maximum_nominal_duration_seconds": self.dt*max(hist, default=0)} for key, hist in self.hist.items()}}


def new_calibration():
    return {"native_start_axes": [{key: Range() for key in
        ("q_minus_qref_rad", "velocity_rad_s", "requested_nm", "start_G_nm")} for _ in range(2)],
        "feature_columns": [Range() for _ in range(9)], "feature_rows": 0,
        "complete_intervals": 0, "partial_intervals": 0, "terminal_complete_intervals": 0}


def save_control(row, qref):
    kind = row["kind"]
    before, after = row["observation_before"], row["observation_after"]
    q, v = pair(before["joint_position"]), pair(before["joint_velocity"])
    next_q, next_v = pair(after["joint_position"]), pair(after["joint_velocity"])
    predicted_q, predicted_v = map(pair, row["predicted_next_qv"][kind])
    planner = row["planner_decision"]
    selected_q = [pair(values) for values in planner["predicted_q"]]
    selected_v = [pair(values) for values in planner["predicted_v"]]
    if len(selected_q) != len(selected_v):
        raise ValueError("saved selected trajectory q/v lengths differ")
    target = pair(row["target_q"])
    return {"source_transition_id": row["shared_transition_id"], "active_index": row["step_index"]-100,
        "step_index": row["step_index"], "executed_substeps": row["diagnostics"]["executed_substeps"],
        "complete_20ms_interval": row["diagnostics"]["executed_substeps"] == 10,
        "native_pre_step_q_rad": q, "native_pre_step_q_minus_qref_rad": [q[i]-qref[i] for i in range(2)],
        "native_pre_step_v_rad_s": v, "known_requested_nm": pair(row["requested_torque"]),
        "saved_start_G_nm": pair(row["model_input_diagnostics"][kind]["model_feature_command_nm"]),
        "target_q_rad": target, "saved_next_prediction_q_rad": predicted_q,
        "saved_next_prediction_v_rad_s": predicted_v, "observed_next_q_rad_offline_label": next_q,
        "observed_next_v_rad_s_offline_label": next_v,
        "offline_position_prediction_error_rad": [next_q[i]-predicted_q[i] for i in range(2)],
        "offline_velocity_prediction_error_rad_s": [next_v[i]-predicted_v[i] for i in range(2)],
        "offline_target_error_rad": [next_q[i]-target[i] for i in range(2)],
        "saved_selected_H15_q_rad": selected_q, "saved_selected_H15_v_rad_s": selected_v,
        "saved_selected_H15_length": len(selected_q), "saved_planner_fallback": planner["fallback"],
        "study_abort": row.get("study_abort")}


def errors(rows):
    rows = [row for row in rows if row["complete_20ms_interval"]]
    values = [row["offline_target_error_rad"] for row in rows]
    return {"complete_endpoint_count": len(values), "active_indices": [row["active_index"] for row in rows],
        "target_error_rmse_per_axis_rad": [math.sqrt(sum(value[i]**2 for value in values)/len(values)) for i in range(2)] if values else None,
        "target_error_rmse_joint_rad": math.sqrt(sum(x*x for value in values for x in value)/(2*len(values))) if values else None,
        "last_target_error_rad": values[-1] if values else None,
        "claim_boundary": "descriptive observed window, not a full-control score or comparison/ranking"}


def bounds(calibration):
    return [(axis["q_minus_qref_rad"].report(), axis["velocity_rad_s"].report())
            for axis in calibration["native_start_axes"]]


def outside(saved_points, qref, calibration_bounds):
    counters = [[0, 0], [0, 0]]
    total = outside_any = 0
    ranges = [{"q_minus_qref_rad": Range(), "velocity_rad_s": Range()} for _ in range(2)]
    for q, v in saved_points:
        flags = []
        for axis in range(2):
            values = (q[axis]-qref[axis], v[axis])
            for signal, value in enumerate(values):
                bound = calibration_bounds[axis][signal]
                if bound["samples"] == 0:
                    return {"available": False, "reason": "own calibration has no native-start bounds"}
                flag = value < bound["minimum"] or value > bound["maximum"]
                counters[axis][signal] += int(flag)
                flags.append(flag)
            ranges[axis]["q_minus_qref_rad"].add(values[0]); ranges[axis]["velocity_rad_s"].add(values[1])
        total += 1; outside_any += int(any(flags))
    return {"available": True, "saved_pair_count": total, "outside_any_q_or_v_count": outside_any,
        "outside_any_q_or_v_fraction": outside_any/total if total else None,
        "per_axis": [{"q_outside_count": counters[i][0], "v_outside_count": counters[i][1],
            "q_outside_fraction": counters[i][0]/total if total else None,
            "v_outside_fraction": counters[i][1]/total if total else None,
            "saved_ranges": {key: meter.report() for key, meter in ranges[i].items()}} for i in range(2)],
        "boundary": "exact marginal native-start min/max only; within-box does not establish identification or prediction validity"}


def format_range(record):
    return "unobserved" if record["samples"] == 0 else f"[{record['minimum']:.6g}, {record['maximum']:.6g}]"


def markdown(report):
    lines = ["# C 保存轨迹有效域诊断", "", "仅从已首审的原档提取保存值和离线误差；没有模型导入、拟合、新预测、MPC、物理、Git或科学门重算。",
        "", f"原档commit `{report['source_commit']}`；首审 {report['first_audit_checks']} 项、0失败。保存读取 {report['trace_rows']} 行，已有费用 {report['original_paid_budget']}。", "",
        "校准范围取完整20ms区间的原生起点；域外率只比较逐轴q−qref/v边界。落在范围内不能证明可辨识或预测有效。连续请求以控制调用计，实际力矩以保存2ms子步计，零/未知/断档会结束连续段。", "",
        "| seed / 校准 | q−qref肩 / 肘(rad) | v肩 / 肘(rad/s) | start-G肩 / 肘(Nm) | joint_any连续请求最长 | joint_any实际最长 |", "|---|---|---|---|---|---|"]
    for key, cal in report["calibrations"].items():
        axes = cal["native_start_axes"]
        trial = report["continuous_nonzero"][key]
        known = trial["known_request"]["run_length_distributions"]["joint_any"]["maximum_length"]
        actual = trial["actual_torque"]["run_length_distributions"]["joint_any"]["maximum_length"]
        columns = [" / ".join(format_range(axis[name]) for axis in axes) for name in
                   ("q_minus_qref_rad", "velocity_rad_s", "start_G_nm")]
        lines.append(f"| {key} | {' | '.join(columns)} | {known}调用 | {actual}子步 |")
    lines += ["", "| 控制 | 保存active数 / 状态 | 起点 / 首步 / H15域外率 | stop末q误差(rad) | 末v预测 / 实测(rad/s) |", "|---|---|---|---|---|"]
    for key, control in report["learned_controls"].items():
        fractions = []
        for name in ("native_control_starts", "saved_selected_first_step", "saved_selected_whole_horizon"):
            value = control["own_calibration_domain_comparison"][name].get("outside_any_q_or_v_fraction")
            fractions.append("未观测" if value is None else f"{100*value:.1f}%")
        last = control["saved_steps"][-1] if control["saved_steps"] else None
        error = "未观测" if last is None else "/".join(f"{x:.6g}" for x in last["offline_target_error_rad"])
        velocity = "未观测" if last is None else f"{last['saved_next_prediction_v_rad_s']} / {last['observed_next_v_rad_s_offline_label']}"
        lines.append(f"| {key} | {len(control['saved_steps'])} / {control['status']} | {' / '.join(fractions)} | {error} | {velocity} |")
    lines += ["", "完整JSON保留每个learned控制起点、已知请求、保存的一步预测/选中H15、实测、停止原因和切换前后窗口。提前停止的缺失窗口明确未观测，不排名截短控制。",
        "", "feature列只报告原保存范围、精确unique和恒定性；bias恒定1是设计事实。未计算rank、未重拟合、未把边界诊断提升为科研门。", "",
        f"本只读工具费用：wall {report['read_only_cost']['wall_seconds']:.3f}s / CPU {report['read_only_cost']['cpu_seconds']:.3f}s，新增物理/模型调用全部0。", ""]
    return "\n".join(lines)


def diagnose(raw, audit_path, summary_path, output):
    started, cpu_started = time.perf_counter(), time.process_time()
    output = Path(output).resolve()
    if not output.is_relative_to(STAGE) or output.exists():
        raise ValueError("exclusive new diagnostics output within own ignored directory required")
    output.mkdir(parents=True)
    input_bytes, hashes, report = {}, {}, None
    try:
        for name in RAW_FILES:
            blob = (Path(raw)/name).read_bytes(); input_bytes[name] = blob
            hashes[str((Path(raw)/name).resolve())] = hashlib.sha256(blob).hexdigest()
        audit_blob, summary_blob = Path(audit_path).read_bytes(), Path(summary_path).read_bytes()
        hashes[str(Path(audit_path).resolve())] = hashlib.sha256(audit_blob).hexdigest()
        hashes[str(Path(summary_path).resolve())] = hashlib.sha256(summary_blob).hexdigest()
        metadata = json.loads(input_bytes["metadata.json"])
        seed_results, episodes = json.loads(input_bytes["seed_results.json"]), json.loads(input_bytes["episodes.json"])
        audit, summary = json.loads(audit_blob), json.loads(summary_blob)
        if (metadata["suite"] != "guard_exploration_development" or metadata["synthetic"] is not False
                or metadata["source_commit"] != EXPECTED_COMMIT or audit["failed"] != 0
                or audit["audit_script_sha256"] != EXPECTED_AUDITOR):
            raise ValueError("explicit fixed C production archive and completed clean first audit required")
        for name in RAW_FILES:
            if audit["archive"]["input_hashes"][name] != hashes[str((Path(raw)/name).resolve())]:
                raise ValueError("original input changed after first audit: "+name)
        results = {seed["seed"]: seed for seed in seed_results}
        episode_map = {episode["trial_id"]: episode for episode in episodes}
        calibration = {f"seed{seed}_{kind}": new_calibration() for seed in results for kind in CAL_KINDS}
        run_trackers = {episode["trial_id"]: {"known_request": Runs("control intervals (partial intervals separately counted)", .02),
            "actual_torque": Runs("saved physics substeps", .002), "partial_intervals": 0} for episode in episodes}
        controls = {f"seed{seed}_{kind}": [] for seed in results for kind in LEARNED}
        trace_rows = exception_rows = skipped_prefix = 0
        with gzip.GzipFile(fileobj=io.BytesIO(input_bytes["trace.jsonl.gz"]), mode="rb") as compressed:
            with io.TextIOWrapper(compressed, encoding="utf-8") as stream:
                for line in stream:
                    row = json.loads(line); trace_rows += 1
                    if "collector_exception" in row:
                        exception_rows += 1; continue
                    if row["phase"] == "prefix":
                        skipped_prefix += 1; continue
                    tid, seed, kind = row["trial_id"], row["seed"], row["kind"]
                    requested, qref = pair(row["requested_torque"]), pair(results[seed]["reference_q"])
                    index, diagnostic = row["step_index"]-100, row["diagnostics"]
                    executed = diagnostic["executed_substeps"]
                    tracker = run_trackers[tid]
                    tracker["known_request"].observe(index, requested)
                    tracker["partial_intervals"] += int(executed != 10)
                    history = diagnostic.get("applied_torque_history")
                    first_physics = diagnostic["physics_steps"]-executed
                    if isinstance(history, list) and len(history) == executed:
                        for offset, torque in enumerate(history):
                            tracker["actual_torque"].observe(first_physics+offset, torque)
                    else:
                        for offset in range(executed):
                            tracker["actual_torque"].observe(first_physics+offset, None)
                    if kind in CAL_KINDS:
                        cal = calibration[tid]
                        if executed != 10:
                            cal["partial_intervals"] += 1; continue
                        cal["complete_intervals"] += 1
                        cal["terminal_complete_intervals"] += int(row.get("study_abort") is not None)
                        before = row["observation_before"]
                        q, v = pair(before["joint_position"]), pair(before["joint_velocity"])
                        g = pair(row["model_input_diagnostics"][CAL_KINDS[kind]]["model_feature_command_nm"])
                        for axis in range(2):
                            for name, value in (("q_minus_qref_rad", q[axis]-qref[axis]), ("velocity_rad_s", v[axis]),
                                                ("requested_nm", requested[axis]), ("start_G_nm", g[axis])):
                                cal["native_start_axes"][axis][name].add(value)
                        update = row.get("model_update")
                        if update and update.get("updated") is True:
                            features = update["features_per_output"]
                            if len(features) != 2 or len(features[0]) != 9 or features[0] != features[1]:
                                raise ValueError("saved coupled9 common feature columns mismatch")
                            for column, value in enumerate(features[0]):
                                cal["feature_columns"][column].add(value)
                            cal["feature_rows"] += 1
                    elif kind in LEARNED:
                        controls[tid].append(save_control(row, qref))
        reported_cal, reported_control = {}, {}
        for tid, cal in calibration.items():
            seed = episode_map[tid]["seed"]; group = episode_map[tid]["kind"].removeprefix("calibration_")
            names = results[seed]["calibrations"][group]["initial_model"]["features_per_output"][0]
            reported_cal[tid] = {"status": episode_map[tid]["status"], "completed": episode_map[tid]["completed"],
                "complete_intervals": cal["complete_intervals"], "partial_intervals": cal["partial_intervals"],
                "terminal_complete_intervals": cal["terminal_complete_intervals"],
                "native_start_axes": [{name: meter.report() for name, meter in axis.items()} for axis in cal["native_start_axes"]],
                "saved_feature_rows": cal["feature_rows"], "saved_feature_columns": [
                    {"column": i, "name": names[i], **meter.report()} for i, meter in enumerate(cal["feature_columns"])],
                "feature_scope": "copied successful update feature rows, no new feature construction/rank/fitting"}
        for tid, rows in controls.items():
            episode = episode_map[tid]; seed, kind = episode["seed"], episode["kind"]
            qref = pair(results[seed]["reference_q"])
            own = calibration[f"seed{seed}_calibration_{kind.removeprefix('learned_')}"]
            cal_bounds = bounds(own)
            start = [(row["native_pre_step_q_rad"], row["native_pre_step_v_rad_s"]) for row in rows]
            first = [(row["saved_selected_H15_q_rad"][0], row["saved_selected_H15_v_rad_s"][0]) for row in rows if row["saved_selected_H15_length"]]
            whole = [(q, v) for row in rows for q, v in zip(row["saved_selected_H15_q_rad"], row["saved_selected_H15_v_rad_s"])]
            reported_control[tid] = {"status": episode["status"], "completed": episode["completed"],
                "reason": episode["reason"], "saved_active_count": len(rows), "unobserved_planned_active_count": 200-len(rows),
                "saved_steps": rows, "stop_endpoint": rows[-1] if rows else None,
                "current_target_switch_windows": {"before_switch_active_0_99": errors([row for row in rows if row["active_index"] < 100]),
                    "after_switch_active_100_199": errors([row for row in rows if row["active_index"] >= 100]),
                    "last20_before_switch_active_80_99": errors([row for row in rows if 80 <= row["active_index"] < 100]),
                    "first20_after_switch_active_100_119": errors([row for row in rows if 100 <= row["active_index"] < 120])},
                "own_calibration_domain_comparison": {"native_control_starts": outside(start, qref, cal_bounds),
                    "saved_selected_first_step": outside(first, qref, cal_bounds), "saved_selected_whole_horizon": outside(whole, qref, cal_bounds)}}
        report = {"schema": "c4-saved-domain-diagnostics-v1", "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "source_commit": metadata["source_commit"], "first_audit_checks": audit["checks"], "first_audit_failed": audit["failed"],
            "trace_rows": trace_rows, "exception_rows_excluded_and_counted": exception_rows, "prefix_rows_excluded": skipped_prefix,
            "original_paid_budget": audit["archive"]["budget"], "calibrations": reported_cal,
            "continuous_nonzero": {tid: {"known_request": tracker["known_request"].report(),
                "actual_torque": tracker["actual_torque"].report(), "partial_known_request_intervals": tracker["partial_intervals"]} for tid, tracker in run_trackers.items()},
            "learned_controls": reported_control, "original_hashes": hashes,
            "summary_reference": {"path": str(Path(summary_path).resolve()), "top_level_keys": list(summary)},
            "claim_boundary": "saved native-start marginal domains and selected saved trajectories only; no identification, success gates, truncated-control ranking or new prediction",
            "future_label_boundary": "next native encoders are offline diagnostic labels only, never supplied to a controller/model",
            "read_only_cost": {"input_files": len(hashes), "input_bytes": sum(len(value) for value in input_bytes.values())+len(audit_blob)+len(summary_blob),
                "wall_seconds": time.perf_counter()-started, "cpu_seconds": time.process_time()-cpu_started,
                "physical_calls": 0, "physics_substeps": 0, "model_imports": 0, "model_predictions": 0,
                "RLS_updates": 0, "MPC_selects": 0, "audit_replays": 0, "scientific_gate_recomputations": 0, "git_calls": 0}}
        (output/"diagnostics.json").write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False)+"\n", encoding="utf-8")
        (output/"DIAGNOSTICS.md").write_text(markdown(report), encoding="utf-8")
        (output/"tool_source.py").write_bytes(Path(__file__).read_bytes())
        output_hashes = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in output.iterdir() if path.is_file()}
        (output/"manifest.json").write_text(json.dumps(output_hashes, indent=2)+"\n", encoding="utf-8")
        print(json.dumps({"output": str(output), "trace_rows": trace_rows, "input_hashes": hashes,
                          "output_hashes": output_hashes, "read_only_cost": report["read_only_cost"]}, indent=2))
        return report
    except BaseException as error:
        (output/"failure.json").write_text(json.dumps({"type": type(error).__name__, "message": str(error),
            "original_hashes_read": hashes, "wall_seconds": time.perf_counter()-started, "cpu_seconds": time.process_time()-cpu_started,
            "physical_calls": 0, "model_predictions": 0, "RLS_updates": 0, "MPC_selects": 0, "audit_replays": 0, "git_calls": 0}, indent=2)+"\n", encoding="utf-8")
        (output/"tool_source.py").write_bytes(Path(__file__).read_bytes())
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    diagnose(args.raw, args.audit, args.summary, args.output)


if __name__ == "__main__":
    main()
