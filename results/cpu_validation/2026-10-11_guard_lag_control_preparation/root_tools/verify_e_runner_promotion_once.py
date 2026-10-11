"""Check the final E promotion source and API without reopening D or running fixtures."""
import ast
import hashlib
import json
from pathlib import Path
root = Path(__file__).resolve().parents[1]
stage = root/'external/c4_lag_control_runner_staging'
old = (stage/'guard_lag_control_development.py').read_bytes()
new = (root/'src/developmental_physics/guard_lag_control_development.py').read_bytes()
expected = old.decode('utf-8').replace('Ignored staging has no formal execution permission. Engineering callers must', 'Formal collection requires a clean byte-bound source commit. Engineering callers must').replace('FORMAL_CONTROL_ENABLED = False','FORMAL_CONTROL_ENABLED = True').encode('utf-8')
tree = ast.parse(new)
functions = {n.name:n for n in tree.body if isinstance(n,ast.FunctionDef)}
flag = next(n for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='FORMAL_CONTROL_ENABLED' for t in n.targets))
checks = {'delivered_source_identity':hashlib.sha256(old).hexdigest()=='32b068c0c6ea67ea16f5063b7b0a4f4578ca81bcab7ccdcba45b0c853916be2f',
    'only_release_flag_and_documentation_changed':new==expected,'formal_flag_enabled':flag.value.value is True,
    'run_trial_env_is_explicit_required':functions['run_trial'].args.kwonlyargs[0].arg=='env_factory' and functions['run_trial'].args.kw_defaults[0] is None,
    'D_loader_has_no_fit_or_prediction_calls':not any(isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr in ('predict','update','fit') for n in ast.walk(functions['load_d_models'])),
    'canonical_test_identical_to_static_adapter':(root/'tests/test_guard_lag_control_development.py').read_bytes()==(stage/'test_guard_lag_control_development.py').read_bytes()}
for path in ('src/developmental_physics/guard_lag_control_development.py','tests/test_guard_lag_control_development.py'):
    compile((root/path).read_bytes(),path,'exec')
    checks['compiled/'+path]=True
report={'checks':checks,'passed':sum(checks.values()),'failed':sum(not x for x in checks.values()),'source_sha256':hashlib.sha256(new).hexdigest(),
    'new_model_imports':0,'new_model_predictions':0,'new_updates':0,'new_physics':0,'D_data_reopens':0,'fake_fixture_reexecutions':0,
    'previous_evidence':'Six first hand checks, original environment import failure and one D readonly preflight retained.'}
with (root/'external/c4_e_runner_promotion_01.json').open('x',encoding='utf-8') as f:
    json.dump(report,f,indent=2);f.write('\n')
print(json.dumps(report,indent=2))
raise SystemExit(int(report['failed']!=0))
