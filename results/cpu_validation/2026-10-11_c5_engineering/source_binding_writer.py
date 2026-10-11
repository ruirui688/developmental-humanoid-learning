"""Write the pre-execution source binding, excluding its own hash."""
import hashlib
import importlib.util
import json
from pathlib import Path

root=Path(__file__).resolve().parents[1]
paths=['src/developmental_physics/c5_engineering.py',
       'src/developmental_physics/perturbed_environment.py',
       'src/developmental_physics/environment.py',
       'src/developmental_physics/__init__.py',
       'src/developmental_physics/assets/ground_body.xml',
       'docs/C5_ENGINEERING_PROTOCOL.md','scripts/audit_c5_engineering.py',
       'tests/test_c5_engineering.py','tests/test_perturbed_environment.py',
       'tests/test_audit_c5_engineering.py','tests/test_audit_c5_source_archive.py']
for path in paths:
    source=root/path
    if path.endswith(('.py','.md')) and path not in (
        'src/developmental_physics/environment.py','src/developmental_physics/__init__.py'):
        source.write_bytes(source.read_bytes().replace(b'\r\n',b'\n'))
spec=importlib.util.spec_from_file_location('frozen_c5',root/paths[0])
core=importlib.util.module_from_spec(spec);spec.loader.exec_module(core)
assert core.DRAFT is False
hashes={p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in paths}
value={'schema_version':1,'draft':False,'protocol_path':core.FROZEN_PROTOCOL_PATH,
       'protocol_sha256':hashes[core.FROZEN_PROTOCOL_PATH],'source_sha256':hashes,'plan':core.PLAN}
(root/core.FROZEN_BINDING_PATH).write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8',newline='\n')
print(json.dumps({'sources':len(hashes),'binding_sha256':hashlib.sha256((root/core.FROZEN_BINDING_PATH).read_bytes()).hexdigest()}))
