"""AST-only equivalence check; never imports a model or runs mathematics."""
import ast
import copy
import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OLD = ROOT/"src/developmental_physics/local_pair_model.py"
NEW = HERE/"guard_lag_pair_mpc.py"


def methods(source, name):
    tree = ast.parse(source)
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == name)
    return cls, {node.name: node for node in cls.body if isinstance(node, ast.FunctionDef)}


old_bytes, new_bytes = OLD.read_bytes(), NEW.read_bytes()
old_class, old_methods = methods(old_bytes, "FixedPairMPC")
new_class, new_methods = methods(new_bytes, "FixedGuardLagPairMPC")

init = copy.deepcopy(new_methods["__init__"])
for node in ast.walk(init):
    if isinstance(node, ast.Name) and node.id == "GuardLagPairBodyModel":
        node.id = "PairBodyModel"
    if isinstance(node, ast.Constant) and node.value == "model must be a GuardLagPairBodyModel":
        node.value = "model must be a PairBodyModel"

select = copy.deepcopy(new_methods["select"])
select.args.args = [arg for arg in select.args.args if arg.arg != "previous_v"]
select.body[0].targets[0].elts.pop()  # the new history input
select.body[0].value.generators[0].iter.elts.pop()


class RemoveOnlyExplicitHistory(ast.NodeTransformer):
    def visit_Assign(self, node):
        if (len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id in ("rollout_previous_v", "old_current_v")):
            return None
        return self.generic_visit(node)

    def visit_Call(self, node):
        node = self.generic_visit(node)
        if (isinstance(node.func, ast.Attribute) and node.func.attr == "predict"
                and len(node.args) == 4):
            node.args.pop()
        return node


select = RemoveOnlyExplicitHistory().visit(select)
dump = lambda node: ast.dump(node, include_attributes=False)
controller_assignments = [node.targets[0].attr for node in ast.walk(new_class)
                          if isinstance(node, ast.Assign) and len(node.targets) == 1
                          and isinstance(node.targets[0], ast.Attribute)
                          and isinstance(node.targets[0].value, ast.Name)
                          and node.targets[0].value.id == "self"]
checks = {
    "init_equivalent_except_required_model_type": dump(init) == dump(old_methods["__init__"]),
    "select_equivalent_except_explicit_history_input_and_recurrence": dump(select) == dump(old_methods["select"]),
    "inherits_original_fixed_pair_mpc": dump(new_class.bases[0]) == dump(ast.Name(id="FixedPairMPC", ctx=ast.Load())),
    "no_controller_mutable_velocity_history": not any("history" in name or "previous_v" in name for name in controller_assignments),
    "previous_v_required_positional_input": new_methods["select"].args.args[-1].arg == "previous_v" and not new_methods["select"].args.defaults,
}
report = {"checks": checks, "passed": sum(checks.values()), "failed": sum(not value for value in checks.values()),
          "source_sha256": {str(OLD): hashlib.sha256(old_bytes).hexdigest(), str(NEW): hashlib.sha256(new_bytes).hexdigest()},
          "model_imports": 0, "prediction_calls": 0, "rls_updates": 0, "physical_queries": 0}
output = HERE/"source_ast_01.json"
with output.open("x", encoding="utf-8") as handle:
    json.dump(report, handle, ensure_ascii=False, indent=2)
    handle.write("\n")
print(json.dumps(report, ensure_ascii=False, indent=2))
raise SystemExit(int(report["failed"] != 0))
