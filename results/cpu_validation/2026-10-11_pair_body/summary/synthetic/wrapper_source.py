"""One finite pure-data synthetic attempt; exact source snapshots before tests."""
import contextlib
from datetime import datetime, timezone
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import time
import traceback
import unittest

ROOT = Path(__file__).resolve().parents[1]
PREFIX = ROOT/'external/pair_body_summary_synthetic_01'


def save_json(path,value):
    with path.open('x',encoding='utf-8',newline='\n') as f:
        json.dump(value,f,indent=2,ensure_ascii=False,allow_nan=False)
        f.write('\n')


def main():
    wall,cpu=time.perf_counter(),time.process_time()
    source = ROOT/'external/pair_body_summary_prepare.py'
    tests = ROOT/'external/test_pair_body_summary_prepare.py'
    copies = {str(source):Path(str(PREFIX)+'_summary_source.py'),str(tests):Path(str(PREFIX)+'_tests_source.py'),
              str(Path(__file__)):Path(str(PREFIX)+'_wrapper_source.py')}
    snapshots=[]
    for original,copy in copies.items():
        data=Path(original).read_bytes()
        with copy.open('xb') as f: f.write(data)
        snapshots.append({'original':original,'copy':str(copy),'sha256':hashlib.sha256(data).hexdigest()})
    record={'started_at_utc':datetime.now(timezone.utc).isoformat(),'source':snapshots,
        'python':sys.version,'physical_calls':0,'parameter_updates':0,'formal_raw_reads':0,'first_audit_reads':0}
    save_json(Path(str(PREFIX)+'_attempt.json'),record)
    stream=io.StringIO();code=1
    with contextlib.redirect_stdout(stream),contextlib.redirect_stderr(stream):
        try:
            spec=importlib.util.spec_from_file_location('pair_summary_finite_tests',tests)
            module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
            result=unittest.TextTestRunner(stream=stream,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(module))
            code=int(not result.wasSuccessful());record.update(tests_run=result.testsRun,failures=len(result.failures),errors=len(result.errors))
        except BaseException as e:
            record['exception']={'type':type(e).__name__,'message':str(e)};traceback.print_exc()
    text=stream.getvalue().encode()
    with Path(str(PREFIX)+'_stdout.txt').open('xb') as f:f.write(text)
    record.update(exit_code=code,wall_seconds=time.perf_counter()-wall,cpu_seconds=time.process_time()-cpu,
        stdout_sha256=hashlib.sha256(text).hexdigest())
    save_json(Path(str(PREFIX)+'_execution.json'),record)
    print(stream.getvalue(),end='');print(json.dumps({'exit_code':code,'wall_seconds':record['wall_seconds'],'cpu_seconds':record['cpu_seconds']}))
    return code


if __name__=='__main__':raise SystemExit(main())
