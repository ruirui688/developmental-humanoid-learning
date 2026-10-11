"""Directed final metadata-shape check, without importing any auditor."""
import ast
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path

root=Path(__file__).resolve().parent;output=root/'artificial_003_manifest_projection.json'
if output.exists():raise SystemExit('Refuse to overwrite directed metadata check')
source=(root/'audit_guard_lag_control.py').read_bytes();tree=ast.parse(source.decode('utf-8'))
target=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='bind_d_states')
expressions=[]
for node in ast.walk(target):
    if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id=='exact' and len(node.args)==4 and isinstance(node.args[1],ast.DictComp):
        expressions.append(node.args[1])
if len(expressions)!=2:raise SystemExit('Exactly the two selected D metadata byte projections required')
sha='0'*64;literal={'sha256':sha,'bytes':123,'original_path':'ignored/metadata/path'}
context={'manifest':{'files':{'selected':literal}},'raw_manifest':{'files':{'diagnostics.json':literal}},'relative':'selected'}
checks=1;failed=0;results=[]
for expression in expressions:
    value=eval(compile(ast.Expression(body=expression),'<directed-own-source-projection>','eval'),{'__builtins__':{}},context)
    checks+=1;passed=value=={'sha256':sha,'bytes':123};failed+=not passed;results.append({'projected':value,'passed':passed})
record={'schema_version':1,'created_at_utc':datetime.now(timezone.utc).isoformat(),'checks':checks,'failed':failed,
    'purpose':'AST plus two direct byte-identity projections from own final source; original_path metadata remains bound by entire manifest SHA',
    'source_sha256':hashlib.sha256(source).hexdigest(),'results':results,'old_contracts_reexecuted':0,
    'auditor_imports':0,'old_data_reads':0,'mathematical_predictions':0,'model_or_RLS_updates':0,'physics_calls':0}
(root/'artificial_003_auditor.py').write_bytes(source)
output.write_text(json.dumps(record,indent=2,allow_nan=False)+'\n',encoding='utf-8')
print(json.dumps({'checks':checks,'failed':failed,'source_sha256':record['source_sha256']},allow_nan=False))
raise SystemExit(0 if failed==0 else 1)
