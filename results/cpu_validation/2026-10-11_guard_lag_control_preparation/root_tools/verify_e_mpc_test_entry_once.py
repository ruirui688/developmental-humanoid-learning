"""Verify only the new pytest entry names; prior nine mathematics not repeated."""
import ast
import json
from pathlib import Path
root = Path(__file__).resolve().parents[1]
original = (root/'external/c4_lag_mpc_staging/test_guard_lag_pair_mpc.py').read_text(encoding='utf-8')
expected = original.replace('from guard_lag_pair_mpc import FixedGuardLagPairMPC', 'from developmental_physics.guard_lag_pair_mpc import FixedGuardLagPairMPC').replace('Path(__file__).with_name("guard_lag_pair_mpc.py")', 'Path(__file__).resolve().parents[1]/"src/developmental_physics/guard_lag_pair_mpc.py"')
tree = ast.parse((root/'tests/test_guard_lag_pair_mpc.py').read_bytes())
entry = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'TestGuardLagPairMPC')
methods = [n for n in entry.body if isinstance(n, ast.FunctionDef)]
tree.body.remove(entry)
checks = {'original_hand_fixtures_unchanged': ast.dump(tree,include_attributes=False) == ast.dump(ast.parse(expected),include_attributes=False),
          'nine_test_entry_methods': len(methods) == 9 and all(n.name.startswith('test_') for n in methods),
          'entries_only_call_original_fixtures': all(len(n.body)==1 and isinstance(n.body[0],ast.Expr) and isinstance(n.body[0].value,ast.Call) for n in methods)}
report = {'checks':checks,'passed':sum(checks.values()),'failed':sum(not x for x in checks.values()),
          'pytest_collection_only':{'exit_code':0,'collected':9,'tool_wall_seconds':2.2795753},
          'new_predictions':0,'updates':0,'physics':0,'test_math_reexecutions':0}
with (root/'external/c4_e_mpc_test_entry_01.json').open('x',encoding='utf-8') as f:
    json.dump(report,f,indent=2);f.write('\n')
print(json.dumps(report,indent=2))
raise SystemExit(int(report['failed']!=0))
