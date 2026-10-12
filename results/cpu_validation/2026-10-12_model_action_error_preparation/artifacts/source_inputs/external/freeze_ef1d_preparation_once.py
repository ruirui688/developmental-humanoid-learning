"""Archive the reviewed EF1D preparation exactly once when explicitly requested.

This utility never imports the runner, executes checks, reads experiment streams,
fits a model, or performs diagnostic mathematics. Current navigation is prepended;
every archival output is created with xb and an existing destination is refused.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
import traceback


ARCHIVE_RELATIVE = "results/cpu_validation/2026-10-12_model_action_error_preparation"
RESULT_RELATIVE = "results/cpu_validation/2026-10-12_model_action_error"
PROTOCOL_RELATIVE = "docs/MODEL_ACTION_ERROR_DIAGNOSTIC_PROTOCOL.md"
RUNNER_RELATIVE = "scripts/diagnose_model_action_error.py"
CHECKS_SCRIPT_RELATIVE = "external/new_model_action_error_checks_once.py"
CHECKS_RELATIVE = "external/ef1d_new_checks_first"
SELF_RELATIVE = "external/freeze_ef1d_preparation_once.py"
START_RELATIVE = "external/ef1d_preparation_freeze_first_started.json"
FAILURE_RELATIVE = "external/ef1d_preparation_freeze_first_failure.json"
INPUTS = (
    PROTOCOL_RELATIVE, RUNNER_RELATIVE, CHECKS_SCRIPT_RELATIVE,
    "external/after_ef1b_scientific_review.md",
    "external/after_ef1b_direction_candidate.md", SELF_RELATIVE,
)
PINS = {
    PROTOCOL_RELATIVE: {
        "bytes": 10242,
        "sha256": "1f9af9e89c1127e0210fdc99b805c6777b2f1f8214ed381cdee71fe907c94949",
    },
    RUNNER_RELATIVE: {
        "bytes": 31436,
        "sha256": "fb2aaa26116f4ed75453ef570318c8ffae7828c86a792b73d0c3bc53ec909859",
    },
}
NAVIGATION = (
    "AGENTS.md", "README.md", "docs/CONTINUOUS_EXECUTION_PLAN.md",
    "docs/CPU_VALIDATION_TARGET.md", "docs/DEVELOPMENT_ROADMAP.md",
)
MARKER = "EF1D 冻结准备与当前入口（2026-10-12）"
HISTORICAL = {
    "control_calls": 505297, "physics_substeps": 2784970,
    "online_scalar_updates": 118452, "offline_scalar_updates": 7200,
    "total_scalar_updates": 125652,
    "meaning": "Root-transcribed cumulative budget after EF1B; no historical data rescoring.",
    "other_historical_compute": "Retained in prior stage ledgers; unknown here, not zero.",
}
ZERO_NEW = {
    "physics_calls": 0, "control_calls": 0, "physics_substeps": 0,
    "fit_calls": 0, "RLS_updates": 0, "model_predict_calls": 0,
    "experiment_stream_or_model_payload_reads": 0,
    "saved_label_mathematics": 0, "check_executions": 0,
    "runner_imports": 0, "old_audit_or_contract_executions": 0,
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def identity(data):
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--execute-freeze", action="store_true")
    args = parser.parse_args()
    if not args.execute_freeze:
        parser.error("--execute-freeze required; no files changed")
    repo = args.repo.resolve()
    archive = repo / ARCHIVE_RELATIVE
    started_path, failure_path = repo / START_RELATIVE, repo / FAILURE_RELATIVE
    wall, cpu = time.perf_counter(), time.process_time()
    cost = {"source_read_attempts": 0, "source_read_returns": 0, "source_read_bytes": 0,
            "archive_write_attempts": 0, "archive_write_returns": 0, "archive_write_bytes": 0,
            "tracked_write_attempts": 0, "tracked_write_returns": 0,
            "tracked_write_bytes": 0}
    source_identities, copied_files, navigation_edits = {}, {}, {}
    first_failure, started = None, False

    def inside(relative):
        path = repo / relative
        require(path.resolve().is_relative_to(repo), "path_outside_repository:" + relative)
        require(not path.is_symlink(), "symlink_refused:" + relative)
        return path

    def read(relative):
        path = inside(relative)
        require(path.is_file(), "source_file_required:" + relative)
        cost["source_read_attempts"] += 1
        data = path.read_bytes()
        cost["source_read_returns"] += 1
        cost["source_read_bytes"] += len(data)
        source_identities[relative] = identity(data)
        return data

    def write_once(path, data):
        require(path.resolve().is_relative_to(repo), "write_outside_repository")
        cost["archive_write_attempts"] += 1
        with path.open("xb") as stream:
            require(stream.write(data) == len(data), "short_archive_write:" + str(path))
        cost["archive_write_returns"] += 1
        cost["archive_write_bytes"] += len(data)
        copied_files[path.relative_to(repo).as_posix()] = identity(data)

    def write_json(path, value):
        write_once(path, (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8"))

    def edit_expected(relative, before, after, mode):
        require(read(relative) == before, "tracked_input_changed_before_append:" + relative)
        path = inside(relative)
        require(len(after) >= len(before), "tracked_edit_must_not_shorten_file:" + relative)
        cost["tracked_write_attempts"] += 1
        with path.open("r+b") as stream:
            require(stream.write(after) == len(after), "short_tracked_write:" + relative)
        cost["tracked_write_returns"] += 1
        cost["tracked_write_bytes"] += len(after)
        navigation_edits[relative] = {
            "mode": mode, "before": identity(before), "after": identity(after),
        }

    def suffix(before, text):
        newline = "\r\n" if b"\r\n" in before else "\n"
        prefix = newline if before.endswith(b"\n") else newline + newline
        return (prefix + text.replace("\n", newline).rstrip("\r\n") + newline).encode("utf-8")

    try:
        require(repo.is_dir(), "repository_directory_required")
        require(Path(__file__).resolve() == inside(SELF_RELATIVE).resolve(), "fixed_utility_location_required")
        for relative in (ARCHIVE_RELATIVE, RESULT_RELATIVE, START_RELATIVE, FAILURE_RELATIVE):
            require(not inside(relative).exists(), "fresh_destination_required:" + relative)
        require(started_path.parent.is_dir(), "existing_external_directory_required")
        write_json(started_path, {
            "schema": "ef1d_preparation_first_started_v1",
            "started_utc": datetime.now(timezone.utc).isoformat(),
            "archive": ARCHIVE_RELATIVE, "formal_result": RESULT_RELATIVE,
            "automatic_retry": False, "explicit_execute_freeze": True,
        })
        started = True
        buffers = {relative: read(relative) for relative in INPUTS}
        for relative, expected in PINS.items():
            require(source_identities[relative] == expected, "final_source_pin_differs:" + relative)
        for relative in (PROTOCOL_RELATIVE, RUNNER_RELATIVE):
            require(b"\r" not in buffers[relative], "final_LF_source_required:" + relative)
        checks_root = inside(CHECKS_RELATIVE)
        require(checks_root.is_dir(), "first_checks_directory_required")
        check_files = sorted(path for path in checks_root.rglob("*") if path.is_file())
        require(check_files, "first_checks_files_required")
        for path in check_files:
            relative = path.relative_to(repo).as_posix()
            buffers[relative] = read(relative)
        required_checks = tuple(CHECKS_RELATIVE + "/" + name for name in
                                ("checks.json", "first_stdout.log", "first_stderr.log"))
        require(all(relative in buffers for relative in required_checks), "complete_first_checks_stdio_JSON_required")
        report = json.loads(buffers[required_checks[0]].decode("utf-8"))
        require(report.get("status") == "passed", "new_first_checks_status_must_be_passed")
        require(report.get("first_failure") is None, "new_first_checks_failure_must_be_empty")
        checks = report.get("checks")
        require(isinstance(checks, list) and len(checks) == 8
                and all(item.get("passed") is True for item in checks), "eight_new_first_checks_passed_required")
        reported_sources = report.get("source_identities", {})
        for relative in (RUNNER_RELATIVE, CHECKS_SCRIPT_RELATIVE):
            matches = [value for name, value in reported_sources.items()
                       if Path(name).resolve() == inside(relative).resolve()]
            require(len(matches) == 1 and matches[0] == source_identities[relative],
                    "first_checks_source_binding_differs:" + relative)
        tracked_before = {relative: read(relative) for relative in
                          (*NAVIGATION, ".gitignore", ".gitattributes")}
        for relative in NAVIGATION:
            require(MARKER.encode("utf-8") not in tracked_before[relative],
                    "fresh_navigation_entry_required:" + relative)
        archive.mkdir(parents=True, exist_ok=False)
        for relative, data in buffers.items():
            subtree = "first_checks" if relative.startswith(CHECKS_RELATIVE + "/") else "source_inputs"
            tail = Path(relative).relative_to(CHECKS_RELATIVE) if subtree == "first_checks" else Path(relative)
            destination = archive / "artifacts" / subtree / tail
            destination.parent.mkdir(parents=True, exist_ok=True)
            write_once(destination, data)
        for relative, data in tracked_before.items():
            destination = archive / "tracked_before" / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            write_once(destination, data)
        write_json(archive / "static_review_fact.json", {
            "status": "READY", "source": "Root-transcribed checkpoint_review static declaration.",
            "runner": PINS[RUNNER_RELATIVE], "protocol": PINS[PROTOCOL_RELATIVE],
            "new_first_checks_status": "passed", "new_first_checks_count": 8,
            "review_rerun_by_this_utility": False,
        })
        ignore_rules = []
        for directory in (ARCHIVE_RELATIVE, RESULT_RELATIVE):
            ignore_rules.extend(("!" + directory + "/", "!" + directory + "/**/external/",
                                 "!" + directory + "/**/external/**"))
        attribute_rules = [directory + "/** -text whitespace=cr-at-eol,-blank-at-eof"
                           for directory in (ARCHIVE_RELATIVE, RESULT_RELATIVE)]
        attribute_rules.extend((RUNNER_RELATIVE + " text eol=lf", PROTOCOL_RELATIVE + " text eol=lf"))
        for relative, rules in ((".gitignore", ignore_rules), (".gitattributes", attribute_rules)):
            existing_lines = tracked_before[relative].decode("utf-8").splitlines()
            missing = [rule for rule in rules if rule not in existing_lines]
            if missing:
                addition = suffix(tracked_before[relative], "# EF1D frozen preparation and intact results\n" + "\n".join(missing))
                edit_expected(relative, tracked_before[relative], tracked_before[relative] + addition,
                              "append_missing_archive_and_LF_rules")
        for relative in NAVIGATION:
            docs_prefix = "" if Path(relative).parent.as_posix() == "docs" else "docs/"
            archive_link = "../" + ARCHIVE_RELATIVE + "/freeze_manifest.json" if docs_prefix == "" else ARCHIVE_RELATIVE + "/freeze_manifest.json"
            entry = (
                "## " + MARKER + "\n\n"
                "当前入口为 [EF1D 保存一步误差动作尺度诊断协议](" + docs_prefix + "MODEL_ACTION_ERROR_DIAGNOSTIC_PROTOCOL.md)，"
                "[首次准备封存](" + archive_link + ")保留最终源码与8项新合成检查、stdout/stderr/JSON；"
                "首次合成passed、静态READY仅代表准备资格，正式诊断尚未执行。\n\n"
                "完整2,400 H1/1,200配对origin，至多11,772行解码、38,400盒成员检查/9,600相邻SVD；"
                "复用首审来源，不读trace，0新物理/fit/RLS/model.predict，离线费用另计。"
                "此前累计505,297控制/2,784,970子步，online118,452+offline7,200=125,652scalar更新，旧费用保持。"
                "EF1B单候选关闭，EF1D不自动放行control；C4–C7未验收、原门及五science flags false保持，持续目标active。"
                "准备检查提交推送后直接继续首次有界诊断，不把准备或单个报告当作持续目标完成。"
            )
            before = tracked_before[relative]
            remaining = before
            mode = "prepend_current_entry_after_title"
            if relative == "docs/CPU_VALIDATION_TARGET.md":
                obsolete = "FR4网格微调族已关闭。EF1B开发全门通过才另冻适配本控制器的新最终C4留出；之后依次进入C5未知动力学适应、C6成熟机制和C7综合验收。".encode("utf-8")
                replacement = "FR4网格微调族与EF1B单候选均已关闭。EF1D保存诊断不自动放行control；C4–C7仍未验收，后续控制须另行冻结并满足原门。".encode("utf-8")
                require(remaining.count(obsolete) == 1, "single_obsolete_CPU_target_boundary_required")
                remaining = remaining.replace(obsolete, replacement, 1)
                mode += "_and_replace_single_obsolete_dependency"
            title_end = remaining.find(b"\n")
            require(title_end >= 0, "navigation_title_newline_required:" + relative)
            insertion = suffix(before, entry)
            after = remaining[:title_end + 1] + insertion + remaining[title_end + 1:]
            edit_expected(relative, before, after, mode)
        write_json(archive / "freeze_manifest.json", {
            "schema": "ef1d_preparation_freeze_manifest_v1", "status": "frozen_preparation_complete",
            "archive": ARCHIVE_RELATIVE, "future_formal_result": RESULT_RELATIVE,
            "explicit_execute_freeze": True, "automatic_retry": False,
            "source_pins": source_identities, "reviewed_final_pins": PINS,
            "copied_files": dict(copied_files), "navigation_edits": navigation_edits,
            "historical_budget": HISTORICAL, "new_preparation_zero_experiment_cost": ZERO_NEW,
            "archived_new_first_synthetic_cost": report.get("synthetic_only_cost"),
            "synthetic_cost_source": "Unchanged checks.json transcription; no arithmetic recomputation.",
            "preparation_IO_cost_before_manifest": dict(cost),
            "wall_seconds_before_manifest": time.perf_counter() - wall,
            "cpu_seconds_before_manifest": time.process_time() - cpu,
            "formal_diagnostic_executed": False, "C4_validated": False,
            "C5_scientific_dependency_released": False, "continuous_goal": "active",
            "first_failure": None,
        })
    except BaseException as exc:
        first_failure = {
            "schema": "ef1d_preparation_first_failure_v1", "status": "failed",
            "type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc(),
            "started_marker_created": started, "automatic_retry": False,
            "cost": dict(cost), "source_identities_observed": source_identities,
            "copied_files_before_failure": dict(copied_files),
            "navigation_edits_before_failure": navigation_edits,
            "historical_budget": HISTORICAL, "new_preparation_zero_experiment_cost": ZERO_NEW,
        }
        if failure_path.resolve().is_relative_to(repo) and failure_path.parent.is_dir() and not failure_path.exists():
            write_json(failure_path, first_failure)
    print(json.dumps({
        "status": "failed" if first_failure else "frozen_preparation_complete",
        "archive": str(archive), "automatic_retry": False, "cost": cost,
        "first_failure": first_failure,
    }, ensure_ascii=False, allow_nan=False))
    return int(first_failure is not None)


if __name__ == "__main__":
    raise SystemExit(main())
