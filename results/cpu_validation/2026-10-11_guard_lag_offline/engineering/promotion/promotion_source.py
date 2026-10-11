"""One pure source promotion; never repeats the passed handwritten mathematics."""
import argparse
import ast
import hashlib
import importlib
import inspect
import json
from pathlib import Path
import time

root=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--runner-sha256',required=True)
parser.add_argument('--auditor-sha256',required=True)
args=parser.parse_args()
output=root/'external/guard_lag_offline_promotion_01'
output.mkdir(exist_ok=False)
started_wall,started_cpu=time.perf_counter(),time.process_time()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def text_file(path,content):
    with path.open('x',encoding='utf-8',newline='\n') as stream:
        stream.write(content)


sources=(
 ('external/c4_lag_offline_staging/guard_lag_offline_development.py','src/developmental_physics/guard_lag_offline_development.py',args.runner_sha256),
 ('external/c4_lag_offline_audit_staging/audit_guard_lag_offline.py','scripts/audit_guard_lag_offline.py',args.auditor_sha256),
 ('external/c4_lag_offline_staging/test_guard_lag_offline_development.py','tests/test_guard_lag_offline_development.py',None),
 ('external/c4_lag_offline_audit_staging/test_guard_lag_offline_audit.py','tests/test_guard_lag_offline_audit.py',None),
)
records=[]
for original,destination,expected in sources:
    data=(root/original).read_bytes()
    if expected is not None:
        assert sha(data)==expected,original
    source=data.decode('utf-8').replace('\r\n','\n')
    if destination.endswith('/guard_lag_offline_development.py'):
        assert source.count('FORMAL_OFFLINE_ENABLED = False')==1
        source=source.replace('FORMAL_OFFLINE_ENABLED = False','FORMAL_OFFLINE_ENABLED = True')
        source=source.replace('The public entry is intentionally disabled in ignored staging. Only root may\npromote/freeze it and execute the fixed C data once. Internal functions support',
            'The formal entry requires the committed runtime source binding and clean\nroot execution context. It executes the fixed C data once. Internal functions support')
    elif destination.endswith('/test_guard_lag_offline_development.py'):
        start=source.index('try:\n    from developmental_physics')
        end=source.index('ARTIFICIAL_COST',start)
        source=source[:start]+'from developmental_physics import guard_lag_offline_development as subject\n\n\n'+source[end:]
    elif destination.endswith('/test_guard_lag_offline_audit.py'):
        source=source[:source.index('\ndef main():')]+"\n\nif __name__ == '__main__':\n    unittest.main()\n"
    ast.parse(source)
    text_file(root/destination,source)
    records.append({'original':original,'original_sha256':sha(data),'destination':destination,
        'promoted_sha256':sha((root/destination).read_bytes())})

helper_sha='f3bcedf05b2c956357929e51dcab026ec13311428fa3c6c3383db114da3f7e57'
assert sha((root/'src/developmental_physics/guard_lag_pair_model.py').read_bytes())==helper_sha
subject=importlib.import_module('developmental_physics.guard_lag_offline_development')
helper=importlib.import_module('developmental_physics.guard_lag_pair_model')
assert subject.FORMAL_OFFLINE_ENABLED is True
assert Path(subject.__file__).resolve()==(root/subject.CANONICAL_RUNNER).resolve()
assert subject.HORIZONS==(1,2,5,15) and len(subject.PREDICTORS)==5
assert 'previous_v' in inspect.signature(helper.GuardLagPairBodyModel.predict).parameters
assert 'previous_v' in inspect.signature(helper.GuardLagPairBodyModel.update).parameters
for record in records:
    source=(root/record['destination']).read_text(encoding='utf-8')
    if record['destination'].startswith('tests/'):
        assert 'write_bytes(' not in source and 'write_text(' not in source
for name in ('external/summarize_guard_lag_saved_once.py','external/run_guard_lag_offline_once.py'):
    ast.parse((root/name).read_text(encoding='utf-8'))
report={'files':records,'helper_sha256_unchanged':helper_sha,'pure_production_preflight_passed':True,
 'checks_scope':'AST/source SHA and production import/flag/history signature only; no passed mathematical suites repeated',
 'new_model_constructions':0,'new_model_predictions':0,'new_model_updates':0,'new_physics_calls':0,
 'mpc_select_calls':0,'audit_reexecutions':0,'git_calls':0,
 'execution':{'wall_seconds':time.perf_counter()-started_wall,'cpu_seconds':time.process_time()-started_cpu}}
text_file(output/'result.json',json.dumps(report,ensure_ascii=False,indent=2)+'\n')
text_file(output/'promotion_source.py',Path(__file__).read_text(encoding='utf-8'))
print(json.dumps(report,ensure_ascii=False))
