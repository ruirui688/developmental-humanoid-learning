"""Preserve first CFD1 checks and frozen crossfit navigation, without mathematics."""
from pathlib import Path
import hashlib
import json

repo = Path(r"D:\Codex_ws\robot_rl")
origin = repo/"external/cfd1_first_preparation"
output = repo/"results/cpu_validation/2026-10-12_causal_difference_preparation"
output.mkdir(parents=True, exist_ok=False)
first = output/"first"
first.mkdir()

def identity(blob):
    return {"bytes": len(blob), "sha256": hashlib.sha256(blob).hexdigest()}

payload = {}
for path in sorted(origin.iterdir()):
    blob = path.read_bytes()
    (first/path.name).write_bytes(blob)
    payload["first/"+path.name] = identity(blob)
checks = json.loads((first/"checks.json").read_bytes())
if checks["status"] != "passed":
    raise ValueError("preserve first failed checks; do not freeze")
source_paths = ("scripts/develop_causal_difference_prediction.py", "docs/CAUSAL_DIFFERENCE_PREDICTION_PROTOCOL.md",
    "src/developmental_physics/causal_incremental_pair_model.py", "src/developmental_physics/instrumental_action_model.py",
    "src/developmental_physics/__init__.py")
final_runner = (repo/source_paths[0]).read_bytes()
original_runner = final_runner.replace(b'REQUIRED_NUMPY_VERSION = "1.26.4"', b'REQUIRED_NUMPY_VERSION = "2.2.6"').replace(
    b'locked_NumPy_1_26_4_default_rcond_runtime_required', b'locked_NumPy_2_2_6_default_rcond_runtime_required')
if identity(original_runner) != checks["source"][source_paths[0]]:
    raise ValueError("runtime lock correction must preserve exact originally checked source")
(output/"runtime_lock_original_runner.py").write_bytes(original_runner)
payload["runtime_lock_original_runner.py"] = identity(original_runner)
manifest = {"status": "ready_after_first_necessary_checks_and_static_review", "first_status": checks["status"],
    "first_failure": checks.get("first_failure"), "saved_synthetic_cases": len(checks["checks"]),
    "pre_freeze_runtime_lock_correction": {"original_literal": "2.2.6", "actual_runtime_and_CF1_source": "1.26.4",
        "only_required_version_literal_and_error_string_changed": True,
        "synthetic_checked_runner_identity": checks["source"]["scripts/develop_causal_difference_prediction.py"],
        "mathematical_functions_changed": False, "passed_cases_repeated": 0,
        "first_formal_experiment_executed": False},
    "case_results_saved_immediately": True, "design": "crossfit delta-velocity target; exact same CF1 causal formula",
    "unique_training_rows_scalar_labels": [5997, 11994], "fold_repeated_training_rows_scalar_labels": [11994, 23988],
    "rank4_solves_B_coefficients": [3, 24], "new_learn_records_pair_velocity_heads": [2073, 67950, 135900],
    "matched_cold_reuse": "84 saved RMSE scalars and 2 saved H1 means; no cold forward or score recomputation",
    "static_review": "one final protocol/implementation review; no old audit or mathematics",
    "new_physics_RLS": 0, "preparation_OLS_fit_calls": "see first synthetic checks; no real data fit",
    "old_model_calls_RMSE_gate_recomputations": 0, "old_raw_reads_in_preparation": 0,
    "source_closure": {name: identity((repo/name).read_bytes()) for name in source_paths},
    "payload": payload, "unmeasured_IO_import_work": "unknown_not_zero"}
(output/"manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
(output/"preparation_delivery_script.py").write_bytes(Path(__file__).read_bytes())

for name in ("README.md", "AGENTS.md", "docs/CONTINUOUS_EXECUTION_PLAN.md", "docs/DEVELOPMENT_ROADMAP.md"):
    path = repo/name
    text = path.read_text(encoding="utf-8")
    start = text.index("当前最早未验收的是 **C4双关节完整接触控制**。")
    end = text.index("新最终留出。", start)+len("新最终留出。")
    prefix = "docs/" if name in ("README.md", "AGENTS.md") else ""
    text = text[:start]+f"当前最早未验收的是 **C4双关节完整接触控制**。[CF1完整负结果]({prefix}CAUSAL_INCREMENTAL_PREDICTION_RESULTS.md)保持关闭；下一唯一[CFD1差分crossfit协议]({prefix}CAUSAL_DIFFERENCE_PREDICTION_PROTOCOL.md)已准备，首次必要合成检查通过，最终静态审阅完成。先clean冻结提交推送，再首次执行；不在准备通过后宣称科学成功。\n\n唯一回归目标Δv_t−Δv_(t−1)=BΔphi，四动作特征、2×4单OLS/rcondNone，无截距/正则/尺度/lag。每eval seed只在其它两完整trial active1..1999拟合，3rank4solve/24Bcoeff、23988重复scalar标签用途（unique11994）；训练与评分整trial隔离，但全数据已见开发，非最终留出或因果证明。只新预测CFDlearn2073/67950/135900，严格同人口CF1cold84scalar/mean2转录，0新物理/RLS/旧模型重算。新H1v20%及H2/H5非劣、全部7H报告保持。\n\n累计 **544,345 控制 /2,824,018 子步**；历史 **125,652 scalar RLS更新**保持，全部已有费用另列。结果检查、提交、推送后立即继续最早未验收项，C4–C7未验收。通过也须另冻完整控制与20%/5%/1.05实际努力和新最终留出。"+text[end:]
    path.write_bytes(text.replace("\n", "\r\n").encode("utf-8"))
target = repo/"docs/CPU_VALIDATION_TARGET.md"
text = target.read_text(encoding="utf-8")
start = text.index("**CF1已首次完整失败，立即继续有限的局部动作差分辨识设计。**")
end = text.index("\n\n累计", start)
text = text[:start]+"**立即执行已准备的[CFD1局部动作差分crossfit](CAUSAL_DIFFERENCE_PREDICTION_PROTOCOL.md)。** 每seed只拟合其它两完整trial，四特征单OLS，23988重复标签/3rank4solve/24Bcoeff；只新计算2073learn路径，matched cold已有分数直接转录。0新物理/RLS，无lag/正则/比例扫描；首次新检查与静态review后clean冻结提交推送、首次执行。CF1及旧长时失败保持，C4控制仍需20%/5%/1.05门和新最终留出。"+text[end:]
target.write_bytes(text.encode("utf-8"))
ledger = repo/"docs/CONTINUOUS_EXECUTION_PLAN.md"
with ledger.open("a", encoding="utf-8", newline="") as handle:
    handle.write("\r\n\r\n### CFD1准备与首次执行入口（2026-10-12）\r\n\r\n[CFD1协议](CAUSAL_DIFFERENCE_PREDICTION_PROTOCOL.md)唯一差分crossfit：每eval seed只拟合另两完整trial1999+1999行，3rank4OLS/rcondNone/24Bcoeff，23988重复训练scalar（unique11994）；完整9000原生先资格，全部fit合格才新评分2073records/67950pair/135900heads，cold84scalar+mean2严格匹配转录。仅四动作特征，无lag/截距/正则/scale/扫描；普通motor时序即时对齐，不归因延迟。首次必要合成与静态review通过后clean冻结推送并首次执行，0新物理/RLS，CF1及旧控制关闭。已见trial crossfit不能称新留出/因果B。C4–C7未验收，active目标阶段交付后继续。\r\n")
print(json.dumps({"preparation": str(output), "cases": len(checks["checks"]), "new_physics_RLS": 0}))
