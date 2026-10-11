"""Entry/path and retained wrapper-mechanism inspection; never execute wrapper."""
from pathlib import Path
import ast
import hashlib
import json
import time

out=Path(__file__).parent
result_path=out/'STATIC_CHECK_01.json'
if result_path.exists():raise RuntimeError('preserve first static check')
project=next(p for p in out.resolve().parents if (p/'pyproject.toml').is_file())
paths=[project/'external/run_guard_lag_control_once.py',out/'run_pd_tail_control_once.py']
started=time.perf_counter()
blobs=[path.read_bytes() for path in paths]
trees=[ast.parse(blob) for blob in blobs]
compile(blobs[1],str(paths[1]),'exec')
old,new=trees
checks=[{'label':'new_wrapper_syntax_without_execution','passed':True}]
def check(condition,label):checks.append({'label':label,'passed':bool(condition)})
constants={node.value for node in ast.walk(new) if isinstance(node,ast.Constant) and isinstance(node.value,str)}
check('developmental_physics.pd_tail_control_development' in constants and 'developmental_physics.guard_lag_control_development' not in constants,'new_G_module_entry')
check('external/guard_pd_tail_control_20261011_first' in constants and 'external/guard_lag_control_20261011_first' not in constants,'unified_exclusive_new_G_output_path')
required={'scripts/audit_guard_pd_tail_control.py','scripts/audit_guard_lag_control.py',
    'scripts/audit_guard_lag_offline.py','scripts/audit_guard_coupled_development.py',
    'scripts/audit_guard_pair_development.py','scripts/audit_pair_frozen.py',
    'scripts/audit_local_frozen.py','docs/GUARD_PD_TAIL_CONTROL_DEVELOPMENT_PROTOCOL.md','pyproject.toml'}
check(required.issubset(constants),'new_G_and_retained_independent_source_paths')
check(any(isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and node.func.attr=='add_argument'
    and node.args and isinstance(node.args[0],ast.Constant) and node.args[0].value=='--expected-commit'
    and any(k.arg=='required' and isinstance(k.value,ast.Constant) and k.value.value is True for k in node.keywords)
    for node in ast.walk(new)),'expected_commit_remains_required_CLI_not_hardcoded')
root_assign=next(node for node in new.body if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='root' for t in node.targets))
check(isinstance(root_assign.value,ast.Call) and isinstance(root_assign.value.func,ast.Name) and root_assign.value.func.id=='next'
    and any(isinstance(n,ast.Constant) and n.value=='pyproject.toml' for n in ast.walk(root_assign)),'staging_depth_project_root_discovery')
def subprocess_run(tree):
    return [ast.dump(node,include_attributes=False) for node in ast.walk(tree) if isinstance(node,ast.Call)
        and isinstance(node.func,ast.Attribute) and isinstance(node.func.value,ast.Name)
        and node.func.value.id=='subprocess' and node.func.attr=='run']
check(subprocess_run(old)==subprocess_run(new),'original_child_launch_combined_stdout_stderr_mechanism_retained')
def asserts(tree):return [ast.dump(node,include_attributes=False) for node in tree.body if isinstance(node,ast.Assert)]
check(asserts(old)==asserts(new),'original_clean_commit_clean_status_and_exclusive_assertions_retained')
byte_asserts=lambda tree:[ast.dump(node,include_attributes=False) for node in ast.walk(tree) if isinstance(node,ast.Assert)
    and isinstance(node.test,ast.Compare) and isinstance(node.test.left,ast.Name) and node.test.left.id=='data']
check(byte_asserts(old)==byte_asserts(new),'original_working_bytes_equal_git_blob_assertion_retained')
result={'schema_version':1,'scope':'new wrapper entry/path syntax and retained mechanism AST only; wrapper not imported/executed',
    'checks':checks,'passed':sum(item['passed'] for item in checks),'failed':sum(not item['passed'] for item in checks),
    'input_records':[{'path':str(path),'bytes':len(blob),'sha256':hashlib.sha256(blob).hexdigest()} for path,blob in zip(paths,blobs)],
    'explicit_source_read_opens':2,'explicit_source_read_bytes':sum(len(blob) for blob in blobs),
    'wall_seconds':time.perf_counter()-started,'timing_scope':'two source reads, parse/compile and AST checks through report assembly; excludes final JSON serialization/write',
    'wrapper_child_executions':0,'real_physics':0,'model_or_math_runs':0,'actual_E_C_D_F_data_reads':0,'tracked_or_canonical_changes':0}
(out/'run_guard_lag_control_once.original.py').write_bytes(blobs[0])
(out/'run_pd_tail_control_once.original.py').write_bytes(blobs[1])
result_path.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
print(json.dumps(result))
raise SystemExit(bool(result['failed']))
