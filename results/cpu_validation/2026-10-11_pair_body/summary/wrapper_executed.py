"""Single authorized formal-log summary; exact bytes saved before first input read."""
import contextlib
from datetime import datetime, timezone
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import platform
import subprocess
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT/'external/pair_body_20261011_development'
AUDIT = ROOT/'external/pair_body_20261011_first_audit.json'
SOURCE = ROOT/'external/pair_body_summary_prepare.py'
TESTS = ROOT/'external/test_pair_body_summary_prepare.py'
PREFIX = ROOT/'external/pair_body_20261011_summary_01'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def save_json(path,value):
    with path.open('x',encoding='utf-8',newline='\n') as f:
        json.dump(value,f,indent=2,ensure_ascii=False,allow_nan=False)
        f.write('\n')


def main():
    wall,cpu=time.perf_counter(),time.process_time()
    record={'started_at_utc':datetime.now(timezone.utc).isoformat(),
        'authorization':'Root authorized one independent read-only summary after completed clean8841884 collection and zero-failure first audit.',
        'python':sys.version,'platform':platform.platform(),'argv':sys.argv,
        'archive':str(ARCHIVE),'first_audit':str(AUDIT),
        'git_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'git_status':subprocess.check_output(['git','status','--porcelain','--untracked-files=all'],cwd=ROOT,text=True),
        'physical_calls':0,'physics_substeps':0,'parameter_updates':0,'audit_reexecutions':0,'new_predictions':0,
        'one_attempt_consumed_even_on_failure':True,'source':{}}
    save_json(Path(str(PREFIX)+'_attempt.json'),record)
    snapshots={SOURCE:Path(str(PREFIX)+'_summary_executed.py'),
               Path(__file__):Path(str(PREFIX)+'_wrapper_executed.py'),
               TESTS:Path(str(PREFIX)+'_synthetic_tests.py')}
    for original,copy in snapshots.items():
        data=original.read_bytes()
        with copy.open('xb') as f:f.write(data)
        record['source'][str(copy)]={'original':str(original),'sha256':sha(data)}
    stream=io.StringIO();output=None;code=1
    with contextlib.redirect_stdout(stream),contextlib.redirect_stderr(stream):
        try:
            spec=importlib.util.spec_from_file_location('executed_pair_readonly_summary',snapshots[SOURCE])
            module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
            output=module.review(ARCHIVE,AUDIT,ROOT)
            summary_path=Path(str(PREFIX)+'_summary.json')
            save_json(summary_path,output)
            tables={'budget':output['independently_recomputed_budget'],'cumulative':output['cumulative_actual_budget'],
                'statuses':output['statuses'],'committed_by_model':output['committed_scalar_updates_by_model'],
                'gates':output['first_audit_scientific_gates'],
                'episodes':[{k:v for k,v in ep.items() if k not in ('calibration_blocks','prediction_residuals_from_recorded_predictions')}
                            for ep in output['episodes']]}
            details={'input_hashes':output['input_hashes'],'stops':output['stops'],
                'calibration_blocks':{ep['trial_id']:ep['calibration_blocks'] for ep in output['episodes'] if ep.get('kind')=='calibration'},
                'first_audit_derived_metrics':output['first_audit_derived_metrics']}
            save_json(Path(str(PREFIX)+'_review_tables.json'),tables)
            save_json(Path(str(PREFIX)+'_review_detail_tables.json'),details)
            print(json.dumps({'checks':output['checks'],'failed':output['failed'],'violations':output['violations'],
                'budget':output['independently_recomputed_budget'],'cumulative':output['cumulative_actual_budget'],
                'statuses':output['statuses'],
                'stops':[{'trial_id':s['trial_id'],'step':s['endpoint']['step_index'],
                    'active':s['endpoint']['active_index_zero_based'],'block':s['endpoint']['block_zero_based'],
                    'slot':s['endpoint']['slot_zero_based'],'request':s['endpoint']['known_request_native8'][:2],
                    'q':s['endpoint']['after_q_native8'][:2],'v':s['endpoint']['after_v_native8'][:2],
                    'trigger':s['endpoint']['study_abort']['triggers']} for s in output['stops']],
                'tracking':[{ 'trial_id':ep['trial_id'],'status':ep['status'],'rmse':ep['tracking']['rmse'],
                              'actual_effort':ep['phase_effort']['control']['per_axis']} for ep in output['episodes']
                            if ep.get('kind') in ('nominal_mpc','combined_pd','zero_torque')],
                'summary_execution':output['execution']},ensure_ascii=False))
            record['inputs_sha256']=output['input_hashes'];code=int(output['failed']!=0)
        except BaseException as exc:
            record['exception']={'type':type(exc).__name__,'message':str(exc)}
            traceback.print_exc()
    stdout_bytes=stream.getvalue().encode()
    with Path(str(PREFIX)+'_stdout.txt').open('xb') as f:f.write(stdout_bytes)
    artifacts=[Path(str(PREFIX)+suffix) for suffix in ('_summary_executed.py','_wrapper_executed.py','_synthetic_tests.py',
               '_summary.json','_review_tables.json','_review_detail_tables.json','_stdout.txt','_attempt.json')]
    record['artifacts_sha256']={str(p):sha(p.read_bytes()) for p in artifacts if p.is_file()}
    record.update(finished_at_utc=datetime.now(timezone.utc).isoformat(),exit_code=code,
        wrapper_wall_seconds=time.perf_counter()-wall,wrapper_cpu_seconds=time.process_time()-cpu,
        timing_scope='Complete wrapper including imports, source snapshot, one input read, Git blob verification, report writes and artifact hashes; excludes final execution-record write.')
    save_json(Path(str(PREFIX)+'_execution.json'),record)
    print(stream.getvalue(),end='')
    print(json.dumps({'exit_code':code,'wrapper_wall_seconds':record['wrapper_wall_seconds'],'wrapper_cpu_seconds':record['wrapper_cpu_seconds'],
                      'execution':str(Path(str(PREFIX)+'_execution.json'))}))
    return code


if __name__=='__main__':raise SystemExit(main())
