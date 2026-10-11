"""Source-only promotion verification; no imports, fits or prediction calls."""
import ast
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
staging = root / 'external/c4_lag_mpc_staging'
source = root / 'src/developmental_physics/guard_lag_pair_mpc.py'
original = (staging / 'guard_lag_pair_mpc.py').read_bytes()
promoted = source.read_bytes()
tree = ast.parse(promoted)
cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'FixedGuardLagPairMPC')
select = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'select')
checks = {
    'staging_hash_matches_delivery': hashlib.sha256(original).hexdigest() == '2f6c9f4f7f7f128157897f67d40a6cfef09fef582aaeac55945d28399a59d97d',
    'promoted_bytes_only_normalize_line_endings': promoted == original.replace(b'\r\n', b'\n'),
    'required_explicit_history': [a.arg for a in select.args.args] == ['self', 'q', 'v', 'target_q', 'previous_v'] and not select.args.defaults,
    'inherits_original_controller': isinstance(cls.bases[0], ast.Name) and cls.bases[0].id == 'FixedPairMPC',
    'old_core_unchanged': hashlib.sha256((root / 'src/developmental_physics/local_pair_model.py').read_bytes()).hexdigest() == '81e0c9147bbfd7f825f14ad7439e6752c021bc08922abd04589a89b59fc509df',
}
test = (root / 'tests/test_guard_lag_pair_mpc.py').read_text(encoding='utf-8')
expected = (staging / 'test_guard_lag_pair_mpc.py').read_text(encoding='utf-8').replace('from guard_lag_pair_mpc import FixedGuardLagPairMPC', 'from developmental_physics.guard_lag_pair_mpc import FixedGuardLagPairMPC').replace('Path(__file__).with_name("guard_lag_pair_mpc.py")', 'Path(__file__).resolve().parents[1]/"src/developmental_physics/guard_lag_pair_mpc.py"')
checks['test_only_import_and_canonical_source_path_changes'] = test == expected
report = {'checks': checks, 'passed': sum(checks.values()), 'failed': sum(not x for x in checks.values()), 'promoted_sha256': hashlib.sha256(promoted).hexdigest(), 'model_imports': 0, 'predictions': 0, 'updates': 0, 'physics': 0, 'note': 'Nine first engineering checks and five original AST checks are retained; not rerun.'}
with (root / 'external/c4_e_mpc_promotion_01.json').open('x', encoding='utf-8') as stream:
    json.dump(report, stream, indent=2)
    stream.write('\n')
print(json.dumps(report, indent=2))
raise SystemExit(int(report['failed'] != 0))
