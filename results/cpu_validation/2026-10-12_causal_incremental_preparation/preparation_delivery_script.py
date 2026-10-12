"""Archive the first CF1 synthetic checks and update the active milestone."""
from pathlib import Path
import hashlib
import json

repo = Path(r"D:\Codex_ws\robot_rl")
origin = repo / "external/cf1_first_preparation"
output = repo / "results/cpu_validation/2026-10-12_causal_incremental_preparation"
output.mkdir(parents=True, exist_ok=False)
first = output / "first"
first.mkdir()

def identity(blob):
    return {"bytes": len(blob), "sha256": hashlib.sha256(blob).hexdigest()}

payload = {}
for path in sorted(origin.iterdir()):
    blob = path.read_bytes()
    (first / path.name).write_bytes(blob)
    payload["first/"+path.name] = identity(blob)
checks = json.loads((first / "checks.json").read_bytes())
if checks["status"] != "passed":
    raise ValueError("first saved necessary checks not passed; preserve and stop freeze")
source_paths = ("scripts/develop_causal_incremental_prediction.py", "docs/CAUSAL_INCREMENTAL_PREDICTION_PROTOCOL.md",
    "src/developmental_physics/causal_incremental_pair_model.py", "src/developmental_physics/instrumental_action_model.py",
    "src/developmental_physics/__init__.py")
manifest = {"status": "ready_after_first_necessary_checks_and_static_review", "first_status": checks["status"],
    "first_failure": checks["first_failure"], "saved_synthetic_cases": len(checks["checks"]),
    "case_results_saved_immediately": True, "new_synthetic_pair_prediction_returns": 2,
    "expected_history_rejections": 3, "new_native_selector_contract_case": 1,
    "prior_design_count_error": {"original_records_pair_heads": [4140, 135780, 271560],
        "corrected_before_experiment": [4146, 135900, 271800], "cause": "H20 origin1980 omitted in hand count",
        "preserved_full_range": True, "experiment_executed_at_correction": False},
    "static_review": "one final protocol/implementation review; no old audit or mathematics",
    "new_physics": 0, "fit": 0, "RLS": 0, "old_model_calls": 0,
    "old_RMSE_gate_recomputations": 0, "old_raw_reads_in_preparation": 0,
    "source_closure": {name: identity((repo/name).read_bytes()) for name in source_paths},
    "payload": payload, "unmeasured_IO_import_work": "unknown_not_zero"}
(output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
(output / "preparation_delivery_script.py").write_bytes(Path(__file__).read_bytes())

for name in ("README.md", "AGENTS.md", "docs/CONTINUOUS_EXECUTION_PLAN.md", "docs/DEVELOPMENT_ROADMAP.md"):
    path = repo / name
    text = path.read_text(encoding="utf-8")
    start = text.index("当前最早未验收的是 **C4双关节完整接触控制**。")
    end = text.index("下一方法设计。", start)+len("下一方法设计。")
    prefix = "docs/" if name in ("README.md", "AGENTS.md") else ""
    result_prefix = "" if not prefix else ""
    text = text[:start]+f"当前最早未验收的是 **C4双关节完整接触控制**。上一轮[IV3完整负结果]({prefix}NEAR_REFERENCE_IDENTIFICATION_RESULTS.md)保持关闭；现在[CF1因果增量协议]({prefix}CAUSAL_INCREMENTAL_PREDICTION_PROTOCOL.md)与纯代码已准备完成，首次2个必要合成case通过，最终静态审阅完成。先冻结到clean提交并推送，再首次执行唯一开发预测；不在准备通过后宣称科学成功。\n\nCF1只提取已有IV1 action8，与同历史CFcold比较；active0使用真实prefix最后区间，后续递推只用自身预测和已知请求。完整4146记录/135900pair/271800velocity heads，0新物理/fit/RLS。新门仅检验H1速度20%及H2/H5不劣，全部7H报告；旧H10/H150失败保持，不开放300ms规划或控制。准备手算遗漏H20 origin1980已在执行前更正并保存。\n\n累计 **544,345 控制 /2,824,018 子步**；历史 **125,652 scalar RLS更新**保持，已有IV1学习与IV3采集/OLS另列。C4及C5–C7未验收，目标active。首次结果检查、提交、推送后立即继续最早未验收项；通过CF1也须另冻完整控制、强PD、20%/5%/1.05实际努力和新最终留出。"+text[end:]
    path.write_bytes(text.replace("\n", "\r\n").encode("utf-8"))
target = repo / "docs/CPU_VALIDATION_TARGET.md"
text = target.read_text(encoding="utf-8")
start = text.index("**立即继续局部动作增量响应＋因果反馈控制的唯一方法设计。**")
end = text.index("\n\n累计", start)
text = text[:start]+"**立即执行已准备的[CF1因果增量预测](CAUSAL_INCREMENTAL_PREDICTION_PROTOCOL.md)。** 新模型与纯runner首次两个必要合成case通过，静态审阅完成；冻结提交推送后首次评估全部4146记录/135900pair/271800velocity heads。0新物理/fit/RLS。用真实上一完整区间估计漂移，递推只用自身预测；匹配CFcold，H1速度20%及H2/H5不劣为新短时用途资格。原长时失败与C4控制门保持，通过也须另冻完整控制。准备人口手算遗漏已更正保留，不删末origin，不重跑旧数学。"+text[end:]
target.write_bytes(text.replace("\n", "\r\n").encode("utf-8"))
ledger = repo / "docs/CONTINUOUS_EXECUTION_PLAN.md"
with ledger.open("a", encoding="utf-8", newline="") as handle:
    handle.write("\r\n\r\n### CF1准备与立即首次执行（2026-10-12）\r\n\r\n[CF1协议](CAUSAL_INCREMENTAL_PREDICTION_PROTOCOL.md)与纯runner/model完成，首次必要合成2case passed，逐case及时封存；只验新记忆/guard/单位/ownstate递推及原生连续契约，0新物理/fit/旧数据读/旧数学。完整4146/135900/271800；原手算4140/135780/271560漏H20 origin1980，已在执行前更正，记录于[准备manifest](../results/cpu_validation/2026-10-12_causal_incremental_preparation/manifest.json)。最终静态review后clean冻结提交推送，首次只读IV3已付9000原生区间。新短时门不追认旧长时门，不开放控制；结果交付后继续active目标，C4–C7未验收。\r\n")
print(json.dumps({"preparation": str(output), "cases": 2, "physics_fit_RLS": 0}))
