"""AST/source-only revision check; no F module or statistic is executed."""
import ast
import copy
import hashlib
import json
from pathlib import Path
import time
import traceback

p = Path(__file__).resolve().parent.parent
r = p/"revision_01"
paths = [p/"diagnose_guard_native_context.py", r/"diagnose_guard_native_context.original.py",
         p.parent/"c4_native_context_protocol_staging/F_PROTOCOL_DRAFT.md", r/"F_PROTOCOL_DRAFT.original.md"]
started_wall, started_cpu = time.perf_counter(), time.process_time()
blobs = [path.read_bytes() for path in paths]
record = {"reads": {"opens": len(blobs), "binary_bytes": sum(map(len, blobs)),
                    "hash_operations": len(blobs), "AST_parses": 2},
          "source_before_sha256": hashlib.sha256(blobs[1]).hexdigest(),
          "source_after_sha256": hashlib.sha256(blobs[0]).hexdigest(),
          "protocol_before_sha256": hashlib.sha256(blobs[3]).hexdigest(),
          "protocol_after_sha256": hashlib.sha256(blobs[2]).hexdigest(),
          "new_statistical_math": 0, "model_imports": 0, "new_model_calls": 0,
          "new_physics": 0, "actual_E_C_D_reads": 0}
try:
    a, b = ast.parse(blobs[0]), ast.parse(blobs[1])
    methods = lambda tree: {node.name: node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.ClassDef))}
    x, y = methods(a), methods(b)
    dump = lambda node: ast.dump(node, include_attributes=False)
    protected = ("finite", "vector", "sub", "mul", "div", "total", "square", "root", "norm",
                 "native_equal", "native_scores", "saved_errors", "describe", "safe_mean", "pearson",
                 "score_statistics", "summarize_records")
    old_notice = next(copy.deepcopy(node.values[node.keys.index(key)]) for node in ast.walk(y["derive_rows"])
                      if isinstance(node, ast.Dict) for key in node.keys
                      if isinstance(key, ast.Constant) and key.value == "identity_status")

    class StripEngineering(ast.NodeTransformer):
        def visit_AugAssign(self, node):
            if (isinstance(node.target, ast.Subscript) and isinstance(node.target.value, ast.Name)
                    and node.target.value.id == "fee"):
                return None
            return self.generic_visit(node)

        def visit_Assign(self, node):
            if (len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
                    and node.targets[0].id in {"category", "quality_flags"}):
                return None
            return self.generic_visit(node)

        def visit_Dict(self, node):
            node = self.generic_visit(node)
            for i in reversed(range(len(node.keys))):
                key = node.keys[i]
                if isinstance(key, ast.Constant) and key.value == "input_quality_flags":
                    node.keys.pop(i)
                    node.values.pop(i)
                elif isinstance(key, ast.Constant) and key.value == "identity_status":
                    node.values[i] = copy.deepcopy(old_notice)
            return node

    checks = {name: dump(x[name]) == dump(y[name]) for name in protected}
    checks["derive_dataflow_unchanged_after_removing_flags_and_identity_fee"] = (
        dump(StripEngineering().visit(copy.deepcopy(x["derive_rows"])))
        == dump(StripEngineering().visit(copy.deepcopy(y["derive_rows"]))))
    checks["formal_flag_false"] = any(isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "FORMAL_DIAGNOSTIC_ENABLED" for target in node.targets)
        and isinstance(node.value, ast.Constant) and node.value.value is False for node in a.body)
    try_body = next(node.body for node in x["run_diagnostic"].body if isinstance(node, ast.Try))
    identity_index = next(i for i, node in enumerate(try_body) if isinstance(node, ast.Assign)
        and isinstance(node.targets[0], ast.Subscript) and isinstance(node.targets[0].slice, ast.Constant)
        and node.targets[0].slice.value == "f_provenance")
    e_read_index = next(i for i, node in enumerate(try_body) if isinstance(node, ast.Assign)
        and isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name)
        and node.value.func.id == "sealed_e_inputs")
    checks["f_identity_saved_before_first_e_read"] = identity_index < e_read_index
    record.update(checks=checks, passed=sum(checks.values()), failed=sum(not value for value in checks.values()))
except BaseException as exc:
    record.update(passed=None, failed=1, checker_exception={"type": type(exc).__name__,
                  "message": str(exc), "traceback": traceback.format_exc()})
finally:
    record.update(wall_seconds=time.perf_counter()-started_wall, cpu_seconds=time.process_time()-started_cpu)
    with (r/"AST_SOURCE_CHECK_02.json").open("x", encoding="utf-8") as writer:
        json.dump(record, writer, indent=2)
        writer.write("\n")
    print(json.dumps(record, indent=2))
raise SystemExit(int(record["failed"] != 0))
