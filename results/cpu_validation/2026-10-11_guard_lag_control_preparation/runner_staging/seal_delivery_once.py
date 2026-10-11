"""One stdlib-only provenance recovery and canonical adapter preparation.

No runner/test imports, fake execution, D archive reads, Git or physics.
"""
from __future__ import annotations

import ast
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time


staging = Path(__file__).resolve().parent
wall, cpu = time.perf_counter(), time.process_time()
checks = []


def digest(blob):
    return hashlib.sha256(blob).hexdigest()


def dump(node):
    return ast.dump(node, include_attributes=False)


def write_new(path, blob):
    with path.open("xb") as file:
        file.write(blob)


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2)+"\n").encode("utf-8")


record = json.loads((staging/"engineering_attempt_02/execution.json").read_bytes())
source = (staging/"guard_lag_control_development.py").read_bytes()
test = (staging/"check_guard_lag_control_small.py").read_bytes()
for filename, blob in (("guard_lag_control_development.py", source),
                       ("check_guard_lag_control_small.py", test)):
    assert digest(blob) == record["source_sha256"][filename], filename
    checks.append("attempt02 saved hash equals recoverable current bytes: "+filename)

recovery = staging/"engineering_attempt_02/recovered_execution_hash_equivalent"
recovery.mkdir(exist_ok=False)
write_new(recovery/"guard_lag_control_development.py", source)
write_new(recovery/"check_guard_lag_control_small.py", test)
wrapper = (staging/"run_small_checks.py").read_bytes()
write_new(recovery/"current_wrapper_reference.py", wrapper)
write_new(recovery/"RECOVERY.json", json_bytes({
    "recovered_at_utc": datetime.now(timezone.utc).isoformat(),
    "attribution": "Source/test bytes recovered after execution; equal original recorded SHA256, not contemporaneously captured bytes",
    "original_execution_record": "../execution.json",
    "source_sha256": record["source_sha256"],
    "wrapper_sha256": digest(wrapper),
    "wrapper_attribution": "Current wrapper reference only; original attempt02 wrapper was not hashed/captured, execution binding unproven",
    "attempt01_runner_bytes_available": False,
    "attempt01_test_hash_equal_to_recovered_test": True,
}))

original = test.decode("utf-8")
old_import = '''PATH = Path(__file__).with_name("guard_lag_control_development.py")
spec = importlib.util.spec_from_file_location("e_hand_collector", PATH)
collector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(collector)'''
new_import = '''import pytest

pytest.importorskip("mujoco")
from developmental_physics import guard_lag_control_development as collector'''
assert original.count(old_import) == 1
canonical = original.replace("import importlib.util\n", "").replace(old_import, new_import)
old_flag = '''    try:
        collector.run_guard_lag_control_development(Path(__file__).with_name("never_created"))
    except RuntimeError:
        pass
    else:
        raise AssertionError("draft public formal flag failed closed")'''
new_flag = '''    prior_formal_flag = collector.FORMAL_CONTROL_ENABLED
    try:
        collector.FORMAL_CONTROL_ENABLED = False
        try:
            collector.run_guard_lag_control_development(Path(__file__).with_name("never_created"))
        except RuntimeError:
            pass
        else:
            raise AssertionError("draft public formal flag failed closed")
    finally:
        collector.FORMAL_CONTROL_ENABLED = prior_formal_flag'''
assert canonical.count(old_flag) == 1
canonical = canonical.replace(old_flag, new_flag)
canonical = canonical.replace('if __name__ == "__main__":\n    main()',
    'def test_hand_fixtures():\n    main()\n\n\nif __name__ == "__main__":\n    main()')
canonical_path = staging/"test_guard_lag_control_development.py"
write_new(canonical_path, canonical.encode("utf-8"))

original_tree, canonical_tree = ast.parse(original), ast.parse(canonical)
original_nodes = {x.name: x for x in original_tree.body if isinstance(x, (ast.FunctionDef, ast.ClassDef))}
canonical_nodes = {x.name: x for x in canonical_tree.body if isinstance(x, (ast.FunctionDef, ast.ClassDef))}
for name in ("FakeEnv", "BadWriter", "trial"):
    assert dump(original_nodes[name]) == dump(canonical_nodes[name])
    checks.append("canonical adapter unchanged AST: "+name)

old_main, new_main = original_nodes["main"], canonical_nodes["main"]
old_index = next(i for i, x in enumerate(old_main.body)
                 if isinstance(x, ast.Try) and "run_guard_lag_control_development" in dump(x))
new_index = next(i for i, x in enumerate(new_main.body)
                 if isinstance(x, ast.Assign) and "prior_formal_flag" in dump(x))
assert old_index == new_index
assert [dump(x) for x in old_main.body[:old_index]] == [dump(x) for x in new_main.body[:new_index]]
flag_try = new_main.body[new_index+1]
assert isinstance(flag_try, ast.Try) and len(flag_try.body) == 2
assert dump(old_main.body[old_index]) == dump(flag_try.body[1])
assert [dump(x) for x in old_main.body[old_index+1:]] == [dump(x) for x in new_main.body[new_index+2:]]
assert dump(flag_try.body[0]) == dump(ast.parse("collector.FORMAL_CONTROL_ENABLED = False").body[0])
assert dump(flag_try.finalbody[0]) == dump(ast.parse("collector.FORMAL_CONTROL_ENABLED = prior_formal_flag").body[0])
checks.append("canonical main unchanged except formal False guard/finally restoration")
assert len(canonical_nodes["test_hand_fixtures"].body) == 1
assert dump(canonical_nodes["test_hand_fixtures"].body[0]) == dump(ast.parse("main()").body[0])
checks.append("pytest entry calls original explicit fake main only")

source_tree = ast.parse(source)
flag = next(x for x in source_tree.body if isinstance(x, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "FORMAL_CONTROL_ENABLED" for t in x.targets))
assert isinstance(flag.value, ast.Constant) and flag.value.value is False
checks.append("runner formal flag remains False")

for path in sorted(staging.glob("*.py")):
    compile(path.read_bytes(), str(path), "exec")
    checks.append("static parse/compile only: "+path.name)
for filename in ("API_OUTLINE.md", "DELIVERY.md"):
    text = (staging/filename).read_text(encoding="utf-8")
    assert all(not x.endswith((" ", "\t")) for x in text.splitlines())
    checks.append("document trailing whitespace absent: "+filename)

statics = {
    "status": "completed", "checks": len(checks), "failed": 0, "cases": checks,
    "runner_sha256": digest(source), "original_test_sha256": digest(test),
    "canonical_test_sha256": digest(canonical.encode("utf-8")),
    "fake_environment_calls": 0, "model_predictions": 0, "model_updates": 0,
    "D_archive_reads": 0, "physical_calls": 0, "Git_calls": 0,
    "wall_seconds": time.perf_counter()-wall,
    "cpu_seconds": time.process_time()-cpu,
    "scope": "stdlib AST/compile/hash/copy/whitespace checks; no module execution/imports",
}
write_new(staging/"static_delivery_checks.json", json_bytes(statics))
inventory = []
for path in sorted(staging.rglob("*")):
    if path.is_file() and "__pycache__" not in path.parts and path.name != "INTEGRITY.json":
        blob = path.read_bytes()
        inventory.append({"path": path.relative_to(staging).as_posix(),
                          "bytes": len(blob), "sha256": digest(blob)})
write_new(staging/"INTEGRITY.json", json_bytes({
    "sealed_at_utc": datetime.now(timezone.utc).isoformat(),
    "files": inventory,
    "exclude": ["__pycache__", "INTEGRITY.json (self-referential)"]
}))
print(json.dumps(statics, ensure_ascii=False, indent=2))
