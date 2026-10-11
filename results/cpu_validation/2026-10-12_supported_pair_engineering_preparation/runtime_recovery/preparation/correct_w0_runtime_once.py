"""Correct the documented runtime and pin; preserve the unstarted first check."""
import ast
import hashlib
import json
from pathlib import Path
import time
repo=Path(__file__).resolve().parents[1]
receipt=repo/'external/c4_w0_runtime_correction_01.json'
if receipt.exists():
    raise SystemExit('first runtime correction already exists')
wall,cpu=time.perf_counter(),time.process_time()
protocol_path=repo/'docs/SUPPORTED_PAIR_DOMAIN_DESIGN.md'
runner_path=repo/'scripts/validate_supported_pair_engineering.py'
before_protocol=protocol_path.read_bytes(); before_runner=runner_path.read_bytes()
needle=b'D:/Python3.10/python.exe scripts/validate_supported_pair_engineering.py'
replacement=b'external/cpu_physics_env/Scripts/python.exe scripts/validate_supported_pair_engineering.py'
assert before_protocol.count(needle)==2
after_protocol=before_protocol.replace(needle,replacement)
old_pin='{\"bytes\": 16400, \"sha256\": \"cf7e9b39a7dc95b6b592fa64aed39a8dd3324c9a50e0cc80452dc3a89237db9a\"}'
new_pin=json.dumps({'bytes':len(after_protocol),'sha256':hashlib.sha256(after_protocol).hexdigest()})
text=before_runner.decode('utf-8')
assert text.count(old_pin)==1
after_runner=text.replace(old_pin,new_pin).encode('utf-8')
old_tree,new_tree=ast.parse(before_runner),ast.parse(after_runner)
for tree in (old_tree,new_tree):
    for item in tree.body:
        if isinstance(item,ast.Assign) and any(isinstance(x,ast.Name) and x.id=='PROTOCOL_PIN' for x in item.targets):
            item.value=ast.Constant(value=None)
assert ast.dump(old_tree)==ast.dump(new_tree)
compile(after_runner,str(runner_path),'exec')
protocol_path.write_bytes(after_protocol); runner_path.write_bytes(after_runner)
records=[]
for name,before,after in (('docs/SUPPORTED_PAIR_DOMAIN_DESIGN.md',before_protocol,after_protocol),
                         ('scripts/validate_supported_pair_engineering.py',before_runner,after_runner)):
    records.append({'path':name,'before_bytes':len(before),'before_sha256':hashlib.sha256(before).hexdigest(),
                    'after_bytes':len(after),'after_sha256':hashlib.sha256(after).hexdigest()})
record={'files':records,'reads':2,'read_bytes':len(before_protocol)+len(before_runner),
        'same_math_and_fixture_AST_except_document_pin':True,'compile_only_passed':True,
        'module_execution':False,'initial_fixture_attempted':False,'physics_calls':0,
        'existing_runtime':'external/cpu_physics_env/Scripts/python.exe',
        'verified_installed_versions':{'numpy':'2.2.6','mujoco':'3.15.0'},
        'new_package_installations':0,'runtime_metadata_read_IO':'unknown_not_zero',
        'wall_seconds':time.perf_counter()-wall,'cpu_seconds':time.process_time()-cpu}
receipt.write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
print(json.dumps(record))
