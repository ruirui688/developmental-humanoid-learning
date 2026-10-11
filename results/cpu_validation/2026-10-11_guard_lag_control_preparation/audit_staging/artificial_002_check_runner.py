"""One recorded small artificial-contract execution, with immutable outputs."""
from collections import Counter
from datetime import datetime,timezone
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import platform
import sys
import time
import unittest

root=Path(__file__).resolve().parent
output=root/'artificial_002.json';log_path=root/'artificial_002.log'
if output.exists() or log_path.exists():raise SystemExit('Refuse to overwrite one artificial check attempt')
source=root/'audit_guard_lag_control.py';tests=root/'test_lag_control_audit_contract.py'
blobs={'auditor':source.read_bytes(),'contracts':tests.read_bytes(),'check_runner':Path(__file__).read_bytes()}
wall,cpu=time.perf_counter(),time.process_time()
spec=importlib.util.spec_from_file_location('_E_artificial_contract_tests',tests)
module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
before_math=Counter(module.m.lag.MATH_COST);before_counts=Counter(module.m.COUNTS);before_read=Counter(module.m.READ_COST)
stream=io.StringIO();result=unittest.TextTestRunner(stream=stream,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(module))
log_path.write_text(stream.getvalue(),encoding='utf-8')
for name,blob in blobs.items():(root/f'artificial_002_{name}.py').write_bytes(blob)
record={'schema_version':1,'created_at_utc':datetime.now(timezone.utc).isoformat(),'purpose':'eight new handwritten E archive contracts; original eight planning tests not repeated',
    'checks':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'successful':result.wasSuccessful(),
    'source_sha256':{name:hashlib.sha256(blob).hexdigest() for name,blob in blobs.items()},
    'log_sha256':hashlib.sha256(log_path.read_bytes()).hexdigest(),'wall_seconds':time.perf_counter()-wall,'cpu_seconds':time.process_time()-cpu,
    'python':sys.version,'platform':platform.platform(),'math_cost':dict(module.m.lag.MATH_COST-before_math),
    'E_contract_counts':dict(module.m.COUNTS-before_counts),'formal_read_accounting':dict(module.m.READ_COST-before_read),
    'new_physics_calls':0,'new_physics_substeps':0,'D_or_C_data_reads':0,'D_or_C_audit_reexecutions':0,
    'RLS_or_model_updates':0,'online_model_or_simulator_imports':0,'complete_fake_archive_matrices':0,
    'partial_history_fixture_endpoints':3,'returned_unwritten_physical_records_handwritten':1}
output.write_text(json.dumps(record,indent=2,allow_nan=False)+'\n',encoding='utf-8')
print(json.dumps({'checks':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'successful':result.wasSuccessful()},allow_nan=False))
raise SystemExit(0 if result.wasSuccessful() else 1)
