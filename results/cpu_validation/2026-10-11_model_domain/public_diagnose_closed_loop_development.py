"""Development-only native-signal replay diagnostics; no simulator imports.

Only E1 development seeds 0/1/2 are accepted. No project or simulator module
is imported. Candidate fits are diagnostic, not a new physical result.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import time

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUTS = {
    "v1": ROOT / "results/cpu_validation/2026-10-11_local_learning/v1_development",
    "v2": ROOT / "results/cpu_validation/2026-10-11_local_learning/v2_development",
}
DT = 0.02
KINDS = ("calibration", "prediction", "frozen_mpc", "learned_mpc", "fixed_pd", "zero_torque")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_outputs(inputs, output, markdown, history_report=None):
    """Reject collisions and resolved input descendants before any fitting."""
    archives = [Path(path).resolve() for path in inputs.values()]
    output, markdown = Path(output).resolve(), Path(markdown).resolve()
    if output == markdown:
        raise ValueError("JSON and Markdown outputs must have different paths")
    for candidate in (output, markdown):
        if candidate.exists():
            raise ValueError(f"Refusing to overwrite output: {candidate}")
        if any(candidate.is_relative_to(archive) for archive in archives):
            raise ValueError("Diagnostic outputs must be outside input archives")
        if history_report is not None and candidate == Path(history_report).resolve():
            raise ValueError("Cannot overwrite the previous diagnostic report")
    if output.is_relative_to(markdown) or markdown.is_relative_to(output):
        raise ValueError("An output file cannot be a parent of the other output")
    return output, markdown


def load_history(path, inputs):
    if path is None:
        return [], None
    path = Path(path).resolve()
    previous = json.loads(path.read_text(encoding="utf-8"))
    if previous.get("holdout_read") is not False:
        raise ValueError("Previous history must also exclude holdout access")
    for version, archive in inputs.items():
        if any(sha(archive/name) != expected for name, expected in previous["inputs"][version]["sha256"].items()):
            raise ValueError("Previous history must refer to the same input bytes")
    history = previous.get("diagnostic_computation_history", [{
        "wall_seconds":previous["wall_seconds"],
        "ridge_solves":previous["replay_accounting"]["ridge_solves"],
        "sample_exposures":previous["replay_accounting"]["sample_exposures_across_solves"],
        "script_sha256":previous["environment"]["script_sha256"],
        "note":"Preserved prior diagnostic computation."}])
    return history, {"path":str(path), "sha256":sha(path)}


def git_source():
    def read(*args):
        try:
            return subprocess.check_output(["git", *args], cwd=ROOT, text=True, stderr=subprocess.DEVNULL).strip()
        except (OSError, subprocess.CalledProcessError):
            return None
    commit, status = read("rev-parse", "HEAD"), read("status", "--porcelain", "--untracked-files=all")
    return {"commit":commit, "status":status, "dirty":None if status is None else bool(status),
            "script_sha256":sha(Path(__file__))}


def extract(row, joint):
    """Whitelist causal native inputs and native labels; drop all diagnostics."""
    before, after = row["observation_before"], row["observation_after"]
    return {
        "step": row["step_index"], "phase": row["phase"],
        "q": before["joint_position"][joint],
        "v": before["joint_velocity"][joint],
        "u": row["requested_torque"][joint],
        "previous_u": before["previous_command"][joint],
        "next_q": after["joint_position"][joint],
        "next_v": after["joint_velocity"][joint],
    }


def load(path, version):
    metadata = json.loads((path / "metadata.json").read_text(encoding="utf-8"))
    if metadata["split"] != "development" or metadata["seeds"] != [0, 1, 2]:
        raise ValueError("Only development seeds 0/1/2 permitted")
    if metadata.get("pose") != "supine" or metadata.get("joint_index") != 0:
        raise ValueError("This E1 diagnosis requires supine joint 0")
    if metadata.get("variant", "linear") != ("linear" if version == "v1" else "hinge"):
        raise ValueError("The input slot and model variant differ")
    models = {r["seed"]: r for r in json.loads((path / "seed_results.json").read_text(encoding="utf-8"))}
    if set(models) != {0, 1, 2}:
        raise ValueError("Saved model seed set differs from development metadata")
    groups = defaultdict(list)
    with gzip.open(path / "trace.jsonl.gz", "rt", encoding="utf-8") as stream:
        for line in stream:
            raw = json.loads(line)
            if raw["seed"] not in models or raw["kind"] not in KINDS:
                raise ValueError("Unexpected development seed or trial kind")
            if raw["phase"] != "prefix":
                native=extract(raw, metadata["joint_index"])
                if not all(np.isfinite(native[name]) for name in ("q", "v", "u", "previous_u", "next_q", "next_v")):
                    raise ValueError("Native transition values must be finite")
                if abs(native["u"]) > .5 or abs(native["previous_u"]) > .5:
                    raise ValueError("Native command exceeds the disclosed permission")
                groups[(raw["seed"], raw["kind"])].append(native)
    if set(groups) != {(seed, kind) for seed in models for kind in KINDS}:
        raise ValueError("Missing planned development trajectory")
    for key, rows in groups.items():
        if any(b["step"] != a["step"] + 1 for a, b in zip(rows, rows[1:])):
            raise ValueError(f"Noncontiguous active samples: {key}")
        if any(b["q"] != a["next_q"] or b["v"] != a["next_v"] or b["previous_u"] != a["u"] for a,b in zip(rows,rows[1:])):
            raise ValueError(f"Native state/command continuity failed: {key}")
        expected=300 if key[1] == "calibration" else (100 if key[1] == "prediction" else 200)
        if len(rows) != expected:
            raise ValueError(f"Unexpected development count: {key}")
    return metadata, models, groups


def rmse(values):
    a = np.asarray(values, dtype=float)
    return None if not len(a) else float(np.sqrt(np.mean(a*a)))


def stats(values):
    a = np.asarray(values, dtype=float)
    return {"count": len(a), "minimum": float(a.min()), "maximum": float(a.max()),
            "mean": float(a.mean()), "std": float(a.std()),
            "quantiles_0_10_50_90_100": np.quantile(a, [0., .1, .5, .9, 1.]).tolist()}


def phi(q, v, u, ref, variant="hinge", previous_u=0., history=False):
    values = [v, q-ref, u]
    if variant == "hinge":
        values.append(float(np.sign(u)) * max(abs(u)-.25, 0.))
    if history:
        values.append(previous_u)
    return np.asarray([*values, 1.])


def predictions(rows, ref, theta_v, theta_avg=None, history=False, variant="hinge", integration="endpoint"):
    x = np.asarray([phi(r["q"], r["v"], r["u"], ref, variant, r["previous_u"], history) for r in rows])
    pv = x @ np.asarray(theta_v)
    if theta_avg is not None:
        average = x @ np.asarray(theta_avg)
    elif integration == "trapezoid":
        average = .5*(np.asarray([r["v"] for r in rows])+pv)
    else:
        average = pv
    pq = np.asarray([r["q"] for r in rows])+DT*average
    return pq, pv


def score(rows, ref, theta_v, theta_avg=None, history=False, variant="hinge", integration="endpoint"):
    pq, pv = predictions(rows, ref, theta_v, theta_avg, history, variant, integration)
    qn, vn = (np.asarray([r[k] for r in rows]) for k in ("next_q", "next_v"))
    eq, ev = pq-qn, pv-vn
    return {"samples": len(rows), "position_rmse_rad": rmse(eq),
            "endpoint_velocity_rmse_rad_s": rmse(ev),
            "mean_velocity_rmse_rad_s": rmse(eq/DT),
            "position_bias_rad": float(eq.mean()), "endpoint_velocity_bias_rad_s": float(ev.mean())}


def rollout_scores(rows, ref, theta_v, theta_avg=None, history=False, variant="hinge", integration="endpoint"):
    result = {}
    for horizon in (1, 5, 15, 50):
        eq, ev = [], []
        for start in range(len(rows)-horizon+1):
            q, v = rows[start]["q"], rows[start]["v"]
            for row in rows[start:start+horizon]:
                features = phi(q, v, row["u"], ref, variant, row["previous_u"], history)
                nv = float(features @ np.asarray(theta_v))
                av = (float(features @ np.asarray(theta_avg)) if theta_avg is not None else
                      (.5*(v+nv) if integration == "trapezoid" else nv))
                q, v = q+DT*av, nv
            end = rows[start+horizon-1]
            eq.append(q-end["next_q"])
            ev.append(v-end["next_v"])
        result[str(horizon)] = {"window_count": len(eq), "position_rmse_rad": rmse(eq),
                                "endpoint_velocity_rmse_rad_s": rmse(ev)}
    return result


def ridge(rows, ref, history, label):
    x = np.asarray([phi(r["q"], r["v"], r["u"], ref, previous_u=r["previous_u"], history=history) for r in rows])
    target = np.asarray([r["next_v"] if label == "endpoint_velocity" else (r["next_q"]-r["q"])/DT for r in rows])
    prior = np.asarray([1., 0., .02, 0., *([0.] if history else []), 0.])
    # Exactly the existing P0=100I, lambda=1 prior; no regularizer search.
    theta = np.linalg.solve(x.T @ x + .01*np.eye(x.shape[1]), x.T @ target + .01*prior)
    return theta, {"label": label, "features": ["v", "q-qref", "u", "hinge(u)", *(["previous_u"] if history else []), "1"],
                   "samples": len(rows), "ridge": .01, "prior": prior.tolist(),
                   "coefficients": theta.tolist(), "design_singular_values": np.linalg.svd(x, compute_uv=False).tolist(),
                   "training_velocity_rmse_rad_s": rmse(x@theta-target)}


def base_metrics(rows, reference):
    q = np.asarray([r["q"]-reference for r in rows]); v=np.asarray([r["v"] for r in rows])
    u = np.asarray([r["u"] for r in rows]); up=np.asarray([r["previous_u"] for r in rows])
    average=np.asarray([(r["next_q"]-r["q"])/DT for r in rows]); vn=np.asarray([r["next_v"] for r in rows])
    trap=.5*(v+vn)
    return {"samples": len(rows), "q_minus_ref_rad": stats(q), "v_rad_s": stats(v),
            "u_nm": stats(u), "observed_average_velocity_rad_s": stats(average),
            "negative_u_samples": int(np.sum(u<0)), "zero_u_samples": int(np.sum(u==0)),
            "positive_u_samples": int(np.sum(u>0)), "action_switch_samples": int(np.sum(u!=up)),
            "endpoint_integration_oracle_position_rmse_rad": rmse(DT*(vn-average)),
            "trapezoid_oracle_position_rmse_rad": rmse(DT*(trap-average)),
            "endpoint_minus_mean_velocity_rmse_rad_s": rmse(vn-average),
            "trapezoid_minus_mean_velocity_rmse_rad_s": rmse(trap-average),
            "correlation_average_endpoint_velocity": float(np.corrcoef(average,vn)[0,1]),
            "correlation_average_trapezoid_velocity": float(np.corrcoef(average,trap)[0,1])}


def conditioned_scores(rows, ref, nominal, learned, variant):
    conditions = {}
    for field, value_fn in (("requested_magnitude", lambda r: f'{abs(r["u"]):.6f}'),
                            ("requested_sign", lambda r: str(int(np.sign(r["u"])))),
                            ("action_switch", lambda r: str(r["u"] != r["previous_u"])),
                            ("velocity_sign", lambda r: str(int(np.sign(r["v"]))))):
        partition=defaultdict(list)
        for r in rows: partition[value_fn(r)].append(r)
        conditions[field] = {key:{"nominal":score(rs,ref,nominal,variant=variant),
                                     "learned":score(rs,ref,learned,variant=variant)}
                             for key, rs in sorted(partition.items())}
    return conditions


def run(inputs, history_report=None):
    inputs={key:Path(path).resolve() for key,path in inputs.items()}
    if set(inputs) != {"v1", "v2"}:
        raise ValueError("Exactly v1 and v2 development archives are required")
    started=time.perf_counter(); loaded={key:load(path,key) for key,path in inputs.items()}
    prior_history, history_source = load_history(history_report, inputs)
    provenance={key:{"path":str(path), "source_commit":loaded[key][0]["source_commit"],
                     "sha256":{name:sha(path/name) for name in ("metadata.json","seed_results.json","trace.jsonl.gz")}}
                for key,path in inputs.items()}
    per_version={}; fits=[]; candidate_records=[]; replay_exposures=0; solves=0
    for version,(metadata,models,groups) in loaded.items():
        version_results=[]; variant="hinge" if version == "v2" else "linear"
        for seed in (0,1,2):
            ref=models[seed]["reference_q"]
            nominal=models[seed]["initial_model"]["coefficients"]
            learned=models[seed]["learned_model"]["coefficients"]
            cal=groups[(seed,"calibration")]
            cq=np.asarray([r["q"] for r in cal]); cv=np.asarray([r["v"] for r in cal])
            observed=[]
            for kind in ("calibration","prediction","frozen_mpc","learned_mpc","fixed_pd","zero_torque"):
                rows=groups[(seed,kind)]
                q=np.asarray([r["q"] for r in rows]);v=np.asarray([r["v"] for r in rows])
                times=[]
                for start in range(0,len(rows),50):
                    part=rows[start:start+50]
                    times.append({"active_start":start,"active_end":start+len(part),"native":base_metrics(part,ref),
                                  "nominal":score(part,ref,nominal,variant=variant),"learned":score(part,ref,learned,variant=variant)})
                observed.append({"kind":kind,"native":base_metrics(rows,ref),
                                 "outside_calibration_q_fraction":float(np.mean((q<cq.min())|(q>cq.max()))),
                                 "outside_calibration_v_fraction":float(np.mean((v<cv.min())|(v>cv.max()))),
                                 "requested_magnitudes_absent_in_calibration_nm":sorted(set(round(abs(r["u"]),6) for r in rows)-set(round(abs(r["u"]),6) for r in cal)),
                                 "nominal":score(rows,ref,nominal,variant=variant),
                                 "learned":score(rows,ref,learned,variant=variant),
                                 "conditional_residuals":conditioned_scores(rows,ref,nominal,learned,variant),
                                 "time_blocks":times,
                                 "rollout":{"nominal":rollout_scores(rows,ref,nominal,variant=variant),
                                            "learned":rollout_scores(rows,ref,learned,variant=variant)}})
            version_results.append({"seed":seed,"qref_rad":ref,"initial_coefficients":nominal,
                                    "learned_coefficients":learned,"episodes":observed})
            if version == "v2":
                fitted={}
                for history,label in ((False,"endpoint_velocity"),(True,"endpoint_velocity"),
                                      (False,"mean_velocity"),(True,"mean_velocity")):
                    theta,record=ridge(cal,ref,history,label)
                    fits.append({"seed":seed,**record});fitted[(history,label)]=theta
                    replay_exposures += len(cal);solves+=1
                if not np.allclose(fitted[(False,"endpoint_velocity")],learned,atol=1e-12,rtol=1e-10):
                    raise ValueError("Independent ridge reconstruction differs from frozen RLS")
                candidates=[("v2_endpoint_original",learned,None,False,"endpoint"),
                            ("v2_endpoint_trapezoid",learned,None,False,"trapezoid"),
                            ("endpoint_with_previous_command",fitted[(True,"endpoint_velocity")],None,True,"endpoint"),
                            ("separate_mean_velocity_5_features",learned,fitted[(False,"mean_velocity")],False,"endpoint"),
                            ("separate_mean_and_endpoint_history_6_features",fitted[(True,"endpoint_velocity")],fitted[(True,"mean_velocity")],True,"endpoint")]
                for name,tv,ta,history,integration in candidates:
                    candidate_records.append({"seed":seed,"candidate":name,"theta_endpoint":list(tv),
                                              "theta_mean":None if ta is None else list(ta),"history":history,"integration":integration,
                                              "episodes":[{"kind":kind,"one_step":score(groups[(seed,kind)],ref,tv,ta,history,integration=integration),
                                                           "rollout":rollout_scores(groups[(seed,kind)],ref,tv,ta,history,integration=integration)}
                                                          for kind in ("calibration","prediction","learned_mpc","frozen_mpc","fixed_pd","zero_torque")]})
        per_version[version]=version_results
    report={"created_at_utc":datetime.now(timezone.utc).isoformat(),"purpose":"Development-only closed-loop model-domain and integration diagnosis",
            "inputs":provenance,"input_whitelist":["native encoder q/v before","current requested torque","native previous_command before","native next encoder q/v as labels","row phase/step/seed/kind"],
            "prohibited_fit_features":["qpos/qvel","diagnostics","contact forces","simulator hidden parameters","future actual torque","future commands"],
            "holdout_read":False,"new_physical_control_steps":0,"new_physics_steps":0,"new_policy_updates":0,
            "replay_accounting":{"ridge_solves":solves,"sample_exposures_across_solves":replay_exposures,
                                 "unique_calibration_transitions":900,"RLS_update_calls":0,"candidate_count":5,
                                 "fit_scope":"Each seed independently fitted on its existing v2 calibration only; no grid search; ridge=0.01 reproduces P0=100I prior.",
                                 "evaluation_scope":"Existing development trajectories only, observational replay; all are development diagnostics, including in-sample calibration scores."},
            "rollout_interpretation":"Every rolling window starts from logged native q/v, then free state prediction uses the recorded requested command sequence. Future recorded commands are diagnostic replay inputs, not a claim that a deployment controller knows future closed-loop actions. No simulator queries.",
            "versions":per_version,"candidate_fits":fits,"candidate_replay_scores":candidate_records,
            "environment":{"python":platform.python_version(),"numpy":np.__version__,"GPU":None,"script_sha256":sha(Path(__file__))},
            "diagnosis_source":git_source(),"prior_report_source":history_source,
            "wall_seconds":time.perf_counter()-started}
    report["diagnostic_computation_history"]=[*prior_history, {
        "wall_seconds":report["wall_seconds"],"ridge_solves":solves,"sample_exposures":replay_exposures,
        "script_sha256":report["environment"]["script_sha256"],
        "note":"Full development-only replay analysis and independent RLS-equivalent ridge reconstruction."}]
    report["cumulative_replay_accounting"]={
        "runs":len(report["diagnostic_computation_history"]),
        "ridge_solves":sum(h["ridge_solves"] for h in report["diagnostic_computation_history"]),
        "sample_exposures":sum(h["sample_exposures"] for h in report["diagnostic_computation_history"]),
        "wall_seconds":sum(h["wall_seconds"] for h in report["diagnostic_computation_history"]),
        "new_physical_steps":0,"new_RLS_update_calls":0}
    for key,path in inputs.items():
        if any(sha(path/name) != expected for name,expected in provenance[key]["sha256"].items()):
            raise ValueError("Input changed while diagnosing")
    return report


def markdown_text(report):
    lines=["# E1 开发集闭环模型失配诊断", "", "此报告只分析 v1/v2 开发 seed 0/1/2，没有读取留出数据、运行物理或改动主模型。候选仅由原生编码器与已知命令拟合；全部结果属于开发集离线诊断。", "", "## 结论与最小修订建议", "", "当前退化至少涉及校准覆盖、模型输出含义和时域三个问题。校准的正负短脉冲使位置大致回到原点，控制则在整个200步内保持负方向请求并逐步到达约−0.075 rad；97%的控制点在校准位置范围外，11%–12%的初始速度也超出校准范围。控制另外使用了校准从未出现的0.375 N·m。在这批开发数据中，0.375及0.5的残差大，而0.125及0.25预测较好；位置、方向、剂量和时间相互混杂，不能仅凭条件表把退化归因于任一因素。", "", "校准范围内的0.5 N·m样本也已出现模型退化，因此单纯扩大位置范围未必够用。原来的五特征端点模型在低剂量预测测试上良好，不足以证明全权限模型有效。", "", "末端速度误差较差，但15步位置回放误差较好，说明端点速度、积分位置和控制收益不能相互替代。原模型 q+dt×预测末端速度 的一步积分近似存在独立误差；仅换梯形积分可以减小该误差，不能修好速度预测，也不能保证长时域收益。", "", "建议先冻结一个最小积分消融：同一校准、同一端点速度参数、同一MPC，只比较原积分与梯形积分，纳入独立动作序列、闭环轨迹、多步位置和努力指标；零拟合梯形候选的一步改善约47%，但50步位置误差略增，是必须保留的负结果。随后单独修订校准覆盖：包含0.375剂量、两种方向和较长连续动作，在固定权限及原生编码器边界下覆盖实际使用范围。修订采集与模型结构应分开比较，不能一次改两个因素后归因于其中一个。", "", "五特征双输出（端点速度与平均速度）可作为第二个明确候选：已有开发回放中一步位置改善约57%，但固定输入一步位置退化约34%，原端点速度退化仍在。增加 previous_command 的候选只改善原闭环端点速度约14%，却把固定输入端点速度RMSE从约0.0007增至0.0037，不建议作为默认。任何新增方案的闭环收益都必须通过新物理试验验证。", "", "## 轨迹覆盖与积分误差", "", "| 版本/seed | 校准 q 范围(rad，相对qref) | learned MPC q 范围 | MPC超出校准q比例 | 校准v范围(rad/s) | MPC超出校准v比例 | MPC切换步 | 末端速度积分真值误差(rad) | 梯形积分真值误差(rad) |", "|---|---|---|---:|---|---:|---:|---:|---:|"]
    for version, results in report["versions"].items():
        for row in results:
            e={e["kind"]:e for e in row["episodes"]};cal=e["calibration"];mpc=e["learned_mpc"]
            cq=cal["native"]["q_minus_ref_rad"];mq=mpc["native"]["q_minus_ref_rad"];cv=cal["native"]["v_rad_s"]
            lines.append(f'| {version}/{row["seed"]} | {cq["minimum"]:.6f}..{cq["maximum"]:.6f} | {mq["minimum"]:.6f}..{mq["maximum"]:.6f} | {100*mpc["outside_calibration_q_fraction"]:.1f}% | {cv["minimum"]:.6f}..{cv["maximum"]:.6f} | {100*mpc["outside_calibration_v_fraction"]:.1f}% | {mpc["native"]["action_switch_samples"]}/200 | {mpc["native"]["endpoint_integration_oracle_position_rmse_rad"]:.7f} | {mpc["native"]["trapezoid_oracle_position_rmse_rad"]:.7f} |')
    lines += ["", "积分真值误差仅以原生下一步编码器末端速度为诊断基准，不是可用的事前控制预测。即使末端速度预测完美，q+dt×末端速度也未必等于实际20 ms内的位置变化。", "", "## 校准冻结后的原始模型误差", "", "| v2 seed/轨迹 | 名义末端v RMSE | 学习末端v RMSE | 名义一步q RMSE | 学习一步q RMSE | 名义15步q RMSE | 学习15步q RMSE |", "|---|---:|---:|---:|---:|---:|---:|"]
    for row in report["versions"]["v2"]:
        for e in row["episodes"]:
            if e["kind"] in ("prediction","learned_mpc","zero_torque"):
                n,l=e["nominal"],e["learned"];rn,rl=e["rollout"]["nominal"]["15"],e["rollout"]["learned"]["15"]
                lines.append(f'| {row["seed"]}/{e["kind"]} | {n["endpoint_velocity_rmse_rad_s"]:.7f} | {l["endpoint_velocity_rmse_rad_s"]:.7f} | {n["position_rmse_rad"]:.7f} | {l["position_rmse_rad"]:.7f} | {rn["position_rmse_rad"]:.7f} | {rl["position_rmse_rad"]:.7f} |')
    lines += ["", "校准分段残差使用最终冻结模型重新评分，属于训练数据回放；不是原日志中随更新变化的pre-update误差，也不是留出验证。", "", "## 请求剂量与时序残差（v2开发seed0，完整三个seed见JSON）", "", "| 轨迹/绝对请求N·m | 步数 | 名义端点v RMSE | 学习端点v RMSE | 名义一步q RMSE | 学习一步q RMSE |", "|---|---:|---:|---:|---:|---:|"]
    seed0=report["versions"]["v2"][0]
    for e in seed0["episodes"]:
        if e["kind"] in ("calibration","prediction","learned_mpc"):
            for amplitude,c in e["conditional_residuals"]["requested_magnitude"].items():
                n,l=c["nominal"],c["learned"]
                lines.append(f'| {e["kind"]}/{amplitude} | {l["samples"]} | {n["endpoint_velocity_rmse_rad_s"]:.7f} | {l["endpoint_velocity_rmse_rad_s"]:.7f} | {n["position_rmse_rad"]:.7f} | {l["position_rmse_rad"]:.7f} |')
    lines += ["", "校准300步中，200步为零请求、正负请求各50步；控制200步全为负请求。校准切换40/300步，控制切换33–35/200步；因而退化不能概括为单纯更高的动作切换频率。seed0闭环各50步段的端点速度RMSE依次约0.03265/0.02315/0.01766/0.02688 rad/s，位置预测偏差符号也随时间改变，并非恒定偏置即可修正。", ""]
    lines += ["", "## 五个固定诊断候选（无超参数搜索）", "", "| seed/候选 | prediction一步q | learned MPC一步q | learned MPC末端v | learned MPC15步q | learned MPC50步q |", "|---|---:|---:|---:|---:|---:|"]
    for c in report["candidate_replay_scores"]:
        e={e["kind"]:e for e in c["episodes"]};m=e["learned_mpc"]
        lines.append(f'| {c["seed"]}/{c["candidate"]} | {e["prediction"]["one_step"]["position_rmse_rad"]:.7f} | {m["one_step"]["position_rmse_rad"]:.7f} | {m["one_step"]["endpoint_velocity_rmse_rad_s"]:.7f} | {m["rollout"]["15"]["position_rmse_rad"]:.7f} | {m["rollout"]["50"]["position_rmse_rad"]:.7f} |')
    lines += ["", "完整 JSON 包含各请求幅度、正负方向、动作切换、速度方向以及50步时间段的原始模型残差；另含完整v1开发负结果。", "", "## 回放成本与证据边界", "", f'- 新增物理控制步/物理子步/策略更新：0/0/0。',f'- 12次岭回归矩阵求解，900个唯一校准转移共重复暴露{report["replay_accounting"]["sample_exposures_across_solves"]}次，RLS逐样本更新调用0。四个拟合组合×三个seed；五个候选含原始模型和零拟合的梯形积分。', f'- 离线脚本墙钟：{report["wall_seconds"]:.3f} s；仅CPU，NumPy {report["environment"]["numpy"]}。', '- 每seed独立校准拟合，保留原始先验及0.01正则。原五特征端点模型重算与已存RLS参数一致。', '- 离线预测改进不能证明新候选闭环收益、风险下降或未知动力学泛化。观测回放评分没有执行新候选的动作，也无法验证其改变状态分布后的表现。', '- 多步回放使用记录的未来请求序列，仅为诊断；不表示在线控制器能事先获得未来闭环命令。', '- 全部开发候选及负结果公开；后续协议必须在新增物理之前冻结，已使用seed 10/11/12不能重新称最终未见留出。', ""]
    b=report["cumulative_replay_accounting"]
    lines += [f'- 含首次计算和文档/连续性检查修订后的重算，累计{b["runs"]}轮、{b["ridge_solves"]}次矩阵求解、{b["sample_exposures"]}次样本暴露、{b["wall_seconds"]:.3f} s；计算历史与脚本哈希全部保留。', '- 原生q/v与previous_command逐步连续性、每轨迹样本数及输入文件运行前后哈希均通过检查。', ""]
    return "\n".join(lines)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v1", type=Path, default=DEFAULT_INPUTS["v1"], help="Original E1 v1 development archive")
    parser.add_argument("--v2", type=Path, default=DEFAULT_INPUTS["v2"], help="Original E1 v2 development archive")
    parser.add_argument("--output", type=Path, required=True, help="New JSON path; overwrite is refused")
    parser.add_argument("--markdown", type=Path, required=True, help="New Markdown path outside input archives")
    parser.add_argument("--history-report", type=Path, help="Optional prior development report for cumulative replay accounting")
    args=parser.parse_args()
    inputs={"v1":args.v1,"v2":args.v2}
    try:
        output, markdown=validate_outputs(inputs,args.output,args.markdown,args.history_report)
        result=run(inputs,args.history_report)
        json_text=json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+"\n"
        md_text=markdown_text(result)
        output.parent.mkdir(parents=True,exist_ok=True)
        markdown.parent.mkdir(parents=True,exist_ok=True)
        with output.open("x",encoding="utf-8") as stream:
            stream.write(json_text)
        with markdown.open("x",encoding="utf-8") as stream:
            stream.write(md_text)
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(2,f"Diagnosis rejected: {error}\n")
    print(json.dumps({"json":str(output),"markdown":str(markdown),"wall_seconds":result["wall_seconds"],
                      "replay":result["replay_accounting"],"cumulative_replay":result["cumulative_replay_accounting"]},ensure_ascii=False))


if __name__ == "__main__":
    main()
