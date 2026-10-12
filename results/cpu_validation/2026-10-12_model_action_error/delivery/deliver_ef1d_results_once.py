"""Deliver only the first EF1D saved outputs; never recompute diagnostic math.

The root runs this once after reviewing the source. No EF1B or historical raw
file is opened. Failed experiments remain failed and are archived without ranking.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import io
import json
from pathlib import Path
import re
import time
import traceback
import zipfile

SOURCE_COMMIT = "8c0397a98ea7bd4bc7169cd0531b14205b0deee5"
RAW_PATH = "external/ef1d_action_error_first/raw"
RESULT_PATH = "results/cpu_validation/2026-10-12_model_action_error"
DOC_PATH = "docs/MODEL_ACTION_ERROR_DIAGNOSTIC_RESULTS.md"
RUNNER_PATH = "scripts/diagnose_model_action_error.py"
PROTOCOL_PATH = "docs/MODEL_ACTION_ERROR_DIAGNOSTIC_PROTOCOL.md"
NAVIGATION = ("README.md", "AGENTS.md", "docs/CONTINUOUS_EXECUTION_PLAN.md",
              "docs/DEVELOPMENT_ROADMAP.md", "docs/CPU_VALIDATION_TARGET.md")
PREPARATION_HEADING = "## EF1D 冻结准备与当前入口（2026-10-12）"
FLAGS = ("scientific_adoption", "old_free_root_C4_validation", "c4_scientific_validation",
         "c5_scientific_dependency_released", "c4_contact_scientific_validation")
SEEDS, METHODS = (8101, 8102, 8103), ("cold", "learned")
MAX_FILE_BYTES = 100_000_000


def identity(data, cost=None):
    if cost is not None:
        cost["identity_hash_calls"] += 1
        cost["identity_hash_byte_uses"] += len(data)
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+"\n").encode("utf-8")


def read(path, cost):
    cost["file_read_attempts"] += 1
    data = path.read_bytes()
    cost["file_read_returns"] += 1
    cost["bytes_read"] += len(data)
    return data


def write_new(path, data, cost):
    if len(data) >= MAX_FILE_BYTES:
        raise ValueError("delivery_file_must_remain_below_100MB:"+str(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    cost["file_write_attempts"] += 1
    with path.open("xb") as stream:
        stream.write(data)
    cost["file_write_returns"] += 1
    cost["bytes_written"] += len(data)


def check(checks, name, condition, detail=None):
    checks.append({"name": name, "passed": bool(condition), "detail": detail})


def verify_saved(blobs, expected_commit, cost):
    """A small metadata/stream contract; no J, SVD, error or old-gate math."""
    checks = []
    if "run.json" not in blobs:
        raise ValueError("first_run_report_missing")
    cost["run_JSON_parse_attempts"] += 1
    run = json.loads(blobs["run.json"])
    cost["run_JSON_parse_returns"] += 1
    status = run.get("status")
    completed = status == "completed"
    failed = status == "failed"
    check(checks, "EF1D_completed_or_preserved_failed", run.get("experiment_id") == "EF1D"
          and (completed or failed) and ((completed and run.get("first_failure") is None)
                                       or (failed and isinstance(run.get("first_failure"), dict))))
    check(checks, "all_scientific_flags_false", all(run.get(key) is False for key in FLAGS))
    for key in ("new_physics_calls", "new_control_calls", "new_fit_calls", "new_RLS_updates",
                "model_predict_calls", "trace_reads", "scientific_gate_recomputations",
                "constraint_searches", "clipped_deltas"):
        check(checks, "saved_zero_boundary_"+key, run.get(key) == 0)
    source = run.get("source")
    if source is None and failed:
        check(checks, "source_refusal_preserved_without_invented_binding", True,
              "source unavailable after recorded first failure; no successful source claim")
    else:
        check(checks, "exact_clean_source_commit", isinstance(source, dict)
              and source.get("commit") == expected_commit
              and source.get("clean_committed_bytes_verified") is True)
        source_files = source.get("files", {}) if isinstance(source, dict) else {}
        check(checks, "two_source_file_bindings", set(source_files) == {RUNNER_PATH, PROTOCOL_PATH})
        if "source.zip" in blobs:
            cost["source_ZIP_decode_attempts"] += 1
            with zipfile.ZipFile(io.BytesIO(blobs["source.zip"])) as archive:
                names = archive.namelist()
                check(checks, "source_ZIP_exact_two_entries", len(names) == 2
                      and set(names) == {RUNNER_PATH, PROTOCOL_PATH})
                for name in (RUNNER_PATH, PROTOCOL_PATH):
                    data = archive.read(name)
                    cost["source_ZIP_entry_returns"] += 1
                    cost["source_ZIP_decoded_bytes"] += len(data)
                    check(checks, "source_ZIP_binding_"+name, identity(data, cost) == source_files.get(name))
            cost["source_ZIP_decode_returns"] += 1
        else:
            check(checks, "source_ZIP_present_or_failed_before_archive", failed,
                  "source archive absent; failed execution retained" if failed else None)
    required = {"run.json", "first_stdout.log", "first_stderr.log"}
    if completed:
        required |= {"source.zip", "diagnostic_records.jsonl"}
    check(checks, "required_first_outputs_present", required <= set(blobs))
    population = run.get("fixed_population_accounting", {})
    check(checks, "fixed_population_2400_1200", population.get("planned_model_records") == 2400
          and population.get("planned_paired_origins") == 1200)
    groups = population.get("groups", [])
    expected_groups = {(f"EF1B_{seed}_control_{method}", model)
                       for seed in SEEDS for method in METHODS for model in METHODS}
    check(checks, "all_twelve_population_groups_retained", len(groups) == 12
          and {(row.get("trial_id"), row.get("model")) for row in groups} == expected_groups
          and all(row.get("planned_records") == 200 and 0 <= row.get("unique_identities_seen", -1) <= 200
                  and row.get("unseen_or_unattempted_records") == 200-row.get("unique_identities_seen", -1)
                  for row in groups))
    regular_ids, pairs, partial_rows, lines = set(), set(), 0, 0
    data = blobs.get("diagnostic_records.jsonl", b"")
    for line in data.splitlines(keepends=True):
        cost["new_diagnostic_JSON_parse_attempts"] += 1
        if not line.endswith(b"\n"):
            raise ValueError("first_diagnostic_stream_has_unterminated_row")
        row = json.loads(line)
        cost["new_diagnostic_JSON_parse_returns"] += 1
        lines += 1
        if "technical_failure_partial" in row:
            partial_rows += 1
            continue
        seed, trial, model, origin = (row.get(key) for key in
                                     ("seed", "trial_id", "model", "origin_active_index"))
        key = (trial, model, origin)
        if (seed not in SEEDS or trial not in {f"EF1B_{seed}_control_{method}" for method in METHODS}
                or model not in METHODS or type(origin) is not int or origin not in range(0, 2000, 10)
                or key in regular_ids):
            raise ValueError("new_diagnostic_identity_missing_duplicate_or_outside_fixed_population")
        regular_ids.add(key)
        pairs.add((trial, origin))
    cost["new_diagnostic_identity_uses"] = len(regular_ids)
    cost["new_diagnostic_decoded_rows"] = lines
    stream = run.get("diagnostic_stream", {})
    check(checks, "new_stream_saved_bytes_SHA_rows", stream.get("records") == lines
          and stream.get("bytes") == len(data) and stream.get("sha256") == identity(data, cost)["sha256"])
    check(checks, "failed_partials_are_preserved_not_ranked", (not completed or partial_rows == 0)
          and partial_rows <= 1 and len(regular_ids) <= 2400)
    result = run.get("result")
    if completed:
        expected_ids = {(trial, model, origin) for trial, model in expected_groups
                        for origin in range(0, 2000, 10)}
        check(checks, "complete_2400_lines_and_1200_pairs", lines == 2400
              and regular_ids == expected_ids and len(pairs) == 1200
              and population.get("unique_model_identities_seen") == 2400
              and population.get("paired_origins_seen") == 1200)
        check(checks, "original_result_population_complete", isinstance(result, dict)
              and result.get("complete_model_records") == 2400 and result.get("complete_paired_origins") == 1200
              and result.get("partial_subset_ranking") is False
              and result.get("scientific_gate_recomputation") is False)
        summaries = result.get("summaries", []) if isinstance(result, dict) else []
        expected_summary = {(seed, method, model) for seed in SEEDS for method in METHODS for model in METHODS}
        check(checks, "twelve_original_summary_groups", len(summaries) == 12
              and {(row.get("seed"), row.get("control_source_method"), row.get("model"))
                   for row in summaries} == expected_summary
              and all(row.get("model_rows") == 200 for row in summaries))
    else:
        check(checks, "failed_has_no_subset_ranking", population.get("partial_subset_ranking") is False
              and (result is None or result.get("partial_subset_ranking") is False))
    return run, {"status": "passed" if all(item["passed"] for item in checks) else "failed",
                 "checks": checks, "check_count": len(checks),
                 "failed_count": sum(not item["passed"] for item in checks),
                 "new_stream_rows": lines, "regular_model_records": len(regular_ids),
                 "written_paired_origins": len(pairs), "technical_partial_rows": partial_rows,
                 "diagnostic_math_recomputed": False, "old_raw_reads": 0,
                 "scientific_ranking_or_gate_recomputation": False}


def cell(value):
    if value is None:
        return "不可评"
    if isinstance(value, dict):
        return "; ".join(str(key)+":"+str(item) for key, item in sorted(value.items())) or "无"
    return str(value)


def document(run, verification):
    complete = run.get("status") == "completed" and verification.get("status") == "passed"
    cost, result = run.get("cost", {}), run.get("result") or {}
    text = ["# EF1D：保存一步误差动作尺度诊断首次结果", "",
            "2026-10-12。首次执行原件及一次轻量保存核对；不重算 J、SVD、delta 或旧指标。", "",
            f"首次保存状态 **{run.get('status')}**，轻量核对 **{verification.get('status')}**；"
            f"源码提交 `{SOURCE_COMMIT}`。"
            + ("完整人口为 2,400 个 H1 模型条目、1,200 个配对 origin。" if complete else
               "首次失败与已完成/未尝试人口原样保留，不能对部分记录排名。"), "",
            f"原件见 [结果 manifest](../{RESULT_PATH}/manifest.json)、"
            f"[首次 run](../{RESULT_PATH}/raw/run.json)、"
            f"[轻量保存核对](../{RESULT_PATH}/delivery/verification.json)。"
            "冻结[协议](MODEL_ACTION_ERROR_DIAGNOSTIC_PROTOCOL.md)保持原文，"
            "本次不是控制实验，也没有新的方法改善门。", "",
            "## 原汇总的逐组转录", "",
            "下表仅转录首次 run.result.summaries 的原保存字段。rank 与分支理由使用原分支分母；"
            "any/all 可评使用每组原 200 条模型记录分母，不能通过邻盒重复计权宣布模型胜负。", "",
            "| seed | 控制来源 | 输出模型 | 记录/分支 | rank 0/1/2 | any/all 可评 | 原不可评理由及次数 | delta 全分支均值/最大 Nm | 原权限最小余量均值/最小 Nm |",
            "|---:|---|---|---|---|---|---|---|---|"]
    if complete:
        for row in result["summaries"]:
            ranks = row["rank_counts"]
            delta = row.get("delta_l2_all_branches") or {}
            margins = row.get("permission_margin_min_per_row") or {}
            text.append("| "+" | ".join(map(str, (
                row["seed"], row["control_source_method"], row["model"],
                f"{row['model_rows']}/{row['branches']}",
                "/".join(str(ranks.get(str(i), 0)) for i in range(3)),
                f"{row['rows_any_branch_available']}/{row['rows_all_branches_available']}",
                cell(row.get("unavailable_reason_counts", {})),
                f"{cell(delta.get('mean'))}/{cell(delta.get('maximum'))}",
                f"{cell(margins.get('mean'))}/{cell(margins.get('minimum'))}",
            )))+" |")
    else:
        text += ["", "完整汇总不可评；仅保留首次错误、逐条部分记录及固定人口账，不转录部分群体排名。",
                 "", "```json", json.dumps(run.get("first_failure"), ensure_ascii=False, indent=2), "```"]
    text += ["", "## 首次实际费用", "",
             "以下逐项转录首次 run.cost，不把零物理/训练写成零计算。", "",
             "| 费用字段 | 首次保存值 |", "|---|---:|"]
    text += [f"| `{key}` | {cell(value)} |" for key, value in sorted(cost.items())]
    text += ["", "交付工具的读取、哈希、JSON/ZIP 解码、复制及文档写入费用单列在"
             f"[交付 I/O 账](../{RESULT_PATH}/delivery/io_cost.json)，不计作新物理或模型预测。", "",
             "## 科学边界与阶段状态", "",
             "本诊断只描述冻结模型内部的最小范数局部误差映射。跨原闭盒、超权限或像空间缺口"
             "使该映射不可评；rank 1 的最小范数解越盒不排除其它 nullspace 可行解，本次没有搜索。"
             "这不能识别真实动作敏感度、接触原因或反事实控制收益；条件数、根存在及局部可评也"
             "不能自动批准动态逆补偿。全部邻盒保留，没有 clip、选优、fit/RLS、model.predict 或物理。", "",
             "EF1B 静态保持候选关闭。C4 原 20% 模型贡献、5% 强 PD、1.05 实际努力门不变；"
             "五 science flags false，C4、C5 科学适应、C6/C7 均未验收。累计仍为"
             " **505,297 控制 / 2,784,970 子步**；online118,452+offline7,200=125,652scalar 更新。", "",
             "持续目标 active。首次交付检查后提交/推送，再由 root 记录有依据的唯一后续判断；"
             "本结果不自动开放新控制/物理分支，也不代表持续目标完成。", ""]
    return "\n".join(text).encode("utf-8")


def navigation_blocks(repo, run, verification, cost):
    complete = run.get("status") == "completed" and verification.get("status") == "passed"
    changes = []
    for name in NAVIGATION:
        path = repo / name
        before = read(path, cost)
        lines = before.decode("utf-8").splitlines(keepends=True)
        indices = [i for i, line in enumerate(lines) if line.rstrip("\r\n") == PREPARATION_HEADING]
        if len(indices) != 1 or indices[0] > 8:
            raise ValueError("exact_front_EF1D_preparation_block_missing:"+name)
        start = indices[0]
        old = lines[start:start+6]
        if (len(old) != 6 or old[1].strip() or old[3].strip() or old[5].strip()
                or "MODEL_ACTION_ERROR_DIAGNOSTIC_PROTOCOL.md" not in old[2]
                or "505,297" not in old[4]):
            raise ValueError("frozen_six_line_navigation_shape_differs:"+name)
        link = "MODEL_ACTION_ERROR_DIAGNOSTIC_RESULTS.md" if name.startswith("docs/") else "docs/MODEL_ACTION_ERROR_DIAGNOSTIC_RESULTS.md"
        status = "首次 completed、完整2,400 H1/1,200配对origin" if complete else "首次失败/保存资格缺口原样保留，部分人口不可排名"
        replacement = ("## EF1D 首次结果与当前入口（2026-10-12）\n\n"
                       f"当前入口为 [EF1D 保存一步误差动作尺度诊断结果]({link})：{status}；"
                       "仅转录首次汇总并完成一次轻量身份/人口/源码绑定核对，不重算J/SVD/delta或旧门。\n\n"
                       "0新增物理/fit/RLS/model.predict，离线代数与交付I/O另计；累计505,297控制/2,784,970子步，"
                       "online118,452+offline7,200=125,652scalar更新不变。最小norm同盒映射的不可评不能"
                       "识别物理原因或否定其它nullspace解；不自动放行control。C4–C7未验收、原门及五science flags false保持，"
                       "持续目标active，阶段提交推送后继续有界研究。\n\n")
        after = ("".join(lines[:start])+replacement+"".join(lines[start+6:])).encode("utf-8")
        changes.append((path, after, {"path": name, "before": identity(before, cost), "after": identity(after, cost),
                                      "change": "only_exact_six_line_front_EF1D_block"}))
    return changes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--source-commit", default=SOURCE_COMMIT)
    args = parser.parse_args()
    repo = args.repo.resolve()
    if args.source_commit != SOURCE_COMMIT or not re.fullmatch(r"[0-9a-f]{40}", args.source_commit):
        parser.error("exact_first_EF1D_source_commit_required")
    raw, output, doc = (repo / name for name in (RAW_PATH, RESULT_PATH, DOC_PATH))
    if not raw.is_dir() or output.exists() or doc.exists():
        parser.error("first_raw_required_and_delivery_output_document_must_not_exist")
    wall, cpu, cost = time.perf_counter(), time.process_time(), Counter()
    output.mkdir(parents=True, exist_ok=False)
    blobs, outputs, first_failure, run, verification = {}, {}, None, None, None
    try:
        files = sorted(path for path in raw.rglob("*") if path.is_file())
        cost["raw_files_enumerated"] = len(files)
        for path in files:
            if not path.resolve().is_relative_to(raw.resolve()):
                raise ValueError("raw_file_link_escaped_first_input")
            name = path.relative_to(raw).as_posix()
            data = read(path, cost)
            blobs[name] = data
            destination = "raw/"+name
            write_new(output / destination, data, cost)
            outputs[destination] = identity(data, cost)
        utility = read(Path(__file__).resolve(), cost)
        write_new(output / "delivery/deliver_ef1d_results_once.py", utility, cost)
        outputs["delivery/deliver_ef1d_results_once.py"] = identity(utility, cost)
        run, verification = verify_saved(blobs, args.source_commit, cost)
        report = document(run, verification)
        # Preflight all five exact replacements before mutating any navigation.
        changes = navigation_blocks(repo, run, verification, cost)
        write_new(doc, report, cost)
        write_new(output / "delivery/MODEL_ACTION_ERROR_DIAGNOSTIC_RESULTS.md", report, cost)
        outputs["delivery/MODEL_ACTION_ERROR_DIAGNOSTIC_RESULTS.md"] = identity(report, cost)
        navigation = []
        for path, data, binding in changes:
            cost["navigation_write_attempts"] += 1
            path.write_bytes(data)
            cost["navigation_write_returns"] += 1
            cost["navigation_bytes_written"] += len(data)
            navigation.append(binding)
        verification["navigation_changes"] = navigation
        verification["result_document_identity"] = identity(report, cost)
    except BaseException as exc:
        first_failure = {"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()}
        verification = verification or {"status": "failed", "checks": [], "check_count": 0, "failed_count": 0}
        verification["delivery_first_failure"] = first_failure
        verification["status"] = "failed"
    verification["execution_boundary"] = {"J_SVD_delta_recomputations": 0, "old_metric_or_gate_recomputations": 0,
        "EF1B_or_other_old_raw_reads": 0, "physics_calls": 0, "fit_RLS_calls": 0, "model_predict_calls": 0}
    verification_blob = encoded(verification)
    write_new(output / "delivery/verification.json", verification_blob, cost)
    outputs["delivery/verification.json"] = identity(verification_blob, cost)
    cost["wall_seconds"], cost["cpu_seconds"] = time.perf_counter()-wall, time.process_time()-cpu
    io_blob = encoded({"scope": "new_EF1D_archive_identity_copy_and_summary_transcription_only", "cost": dict(cost),
                       "accounting_cutoff": "before_final_IO_ledger_and_manifest_encoding_writes",
                       "unmeasured_filesystem_IO": "unknown_not_zero", "no_scientific_math": True})
    write_new(output / "delivery/io_cost.json", io_blob, cost)
    outputs["delivery/io_cost.json"] = identity(io_blob, cost)
    manifest = {"experiment_id": "EF1D", "source_commit": args.source_commit,
                "first_execution_status": run.get("status") if run else "unavailable",
                "delivery_status": verification["status"], "files": outputs,
                "raw_path": RAW_PATH, "result_document": DOC_PATH,
                "failed_results_preserved_without_subset_ranking": True,
                **{key: False for key in FLAGS}}
    write_new(output / "manifest.json", encoded(manifest), cost)
    print(json.dumps({"experiment_id": "EF1D", "delivery_status": verification["status"],
                      "output": str(output), "first_failure": first_failure}, ensure_ascii=False))
    return 1 if verification["status"] != "passed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
