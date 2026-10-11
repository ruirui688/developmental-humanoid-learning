"""Seal first FR0 preparation/check sources once; no test or physical execution."""
import ast
import hashlib
import json
from pathlib import Path
import time
import traceback

repo = Path(__file__).resolve().parents[1]
target = repo / "results/cpu_validation/2026-10-12_free_root_fast_feedback_engineering_preparation"
checks = repo / "external/c4_fr0_checks_01"
origin = repo / "external/c4_free_feedback_candidate"
assert (repo / "results/cpu_validation/2026-10-12_fast_feedback_pair_control/manifest.json").is_file()
assert (repo / "external/fr0_publication.json").is_file()
assert checks.is_dir() and (checks / "execution.json").is_file()
if target.exists():
    raise FileExistsError(target)
target.mkdir()
wall, cpu = time.perf_counter(), time.process_time()
cost = dict(file_reads=0, read_bytes=0, file_writes=0, write_bytes=0)
files = {}

def read(path):
    data = path.read_bytes()
    cost["file_reads"] += 1
    cost["read_bytes"] += len(data)
    return data

def identity(data):
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}

def copy_bytes(data, source, relative):
    path = target / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(data)
    cost["file_writes"] += 1
    cost["write_bytes"] += len(data)
    if read(path) != data:
        raise ValueError("copied_bytes_differ:" + relative.as_posix())
    files[relative.as_posix()] = {**identity(data), "source": source.relative_to(repo).as_posix()}

def copy(path, relative):
    data = read(path)
    copy_bytes(data, path, relative)
    return data

try:
    record = json.loads(read(checks / "execution.json"))
    assert record["returncode"] == 0 and record["test_invocations"] == 1
    published = {}
    for name, pin in record["source_files"].items():
        data = read(repo / name)
        if identity(data) != pin:
            raise ValueError("production_changed_since_first_checks:" + name)
        published[name] = data
    runner = "scripts/validate_free_root_fast_feedback_engineering.py"
    protocol = "docs/FREE_ROOT_FAST_FEEDBACK_ENGINEERING_PROTOCOL.md"
    tree = ast.parse(published[runner])
    assignments = {node.targets[0].id: node.value for node in tree.body
                   if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)}
    pin = ast.literal_eval(assignments["PROTOCOL_PIN"])
    assert pin == record["source_files"][protocol]
    dependencies = tuple(
        ast.literal_eval(assignments[item.id]) if isinstance(item, ast.Name)
        else ast.literal_eval(item)
        for item in assignments["DEPENDENCIES"].elts)
    for name in dependencies:
        if name not in published:
            published[name] = read(repo / name)
    for name, data in published.items():
        copy_bytes(data, repo / name, Path("source") / name)
    for path in sorted(checks.rglob("*")):
        if path.is_file():
            copy(path, Path("first_checks") / path.relative_to(checks))
    original_receipt = json.loads(copy(origin / "preparation_receipt.json",
                                      Path("external_originals/preparation_receipt.json")))
    for name, pin in original_receipt["files"].items():
        assert Path(name).name == name
        data = copy(origin / name, Path("external_originals") / name)
        assert identity(data) == pin
    required = (
        "FR0_ENGINEERING_PROTOCOL_CANDIDATE.md", "fr0_engineering_protocol_preparation.json",
        "fr0_narrow_static_review.json", "fr0_publication.json",
        "publish_fr0_once.py", "run_fr0_checks_once.py", "run_fr0_once.py", "archive_fr0_once.py",
        "archive_fr0_guarded_once.py", "seal_fr0_preparation_once.py", "check_fr0_first_contract.py",
        "check_fr0_new_metrics_once.py", "read_fr0_reporting_once.py",
        "fr0_next_decision_draft.md", "fr0_next_decision_receipt.json",
        "fr0_gitattributes_fragment.txt", "fr0_gitignore_fragment.txt",
        "fr0_delivery_helpers_preparation.json",
    )
    for name in required:
        copy(repo / "external" / name, Path("reviews_and_execution") / name)
    for name in ("c4_free_root_fast_feedback_engineering_design.md",
                 "c4_free_root_fast_feedback_engineering_design_receipt.json"):
        if (repo / "external" / name).is_file():
            copy(repo / "external" / name, Path("reviews_and_execution") / name)
    result = {"status": "FR0_prepared_not_engineering_or_scientifically_validated",
              "files": files, "first_six_new_checks_passed": True,
              "final_protocol_pin_matches": True, "original_source_bytes_preserved": True,
              "tests_or_old_experiments_repeated": False, "formal_physics_or_model_fit_calls": 0,
              "production_source_writes": 0, "automatic_retry": False,
              "cost_before_manifest_write": dict(cost),
              "wall_seconds_before_manifest_write": time.perf_counter() - wall,
              "cpu_seconds_before_manifest_write": time.process_time() - cpu}
    data = (json.dumps(result, indent=2, allow_nan=False) + "\n").encode("utf-8")
    with (target / "manifest.json").open("xb") as stream:
        stream.write(data)
    cost["file_writes"] += 1
    cost["write_bytes"] += len(data)
    print(json.dumps({"target": str(target), "payloads": len(files), "cost": cost,
                      "wall_seconds": time.perf_counter() - wall, "cpu_seconds": time.process_time() - cpu}))
except BaseException as exc:
    data = (json.dumps({"status": "preparation_seal_failed_preserved", "type": type(exc).__name__,
                       "message": str(exc), "traceback": traceback.format_exc(),
                       "files_copied_before_failure": files, "cost_before_failure_record": cost,
                       "automatic_retry": False, "physics_or_model_fit_calls": 0}, indent=2) + "\n").encode("utf-8")
    with (target / "failure.json").open("xb") as stream:
        stream.write(data)
    raise

