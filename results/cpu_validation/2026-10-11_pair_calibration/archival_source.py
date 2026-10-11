"""Exclusive evidence archive; stdlib copy/hash/ZIP/Git-show only, no reruns."""
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import time
import zipfile

ROOT=Path(__file__).resolve().parent.parent
OUTPUT=ROOT/'results/cpu_validation/2026-10-11_pair_calibration'
RAW=ROOT/'external/pair_calibration_20261011_first'
SUMMARY=ROOT/'external/pair_calibration_20261011_summary_01'
STAGING=ROOT/'external/c4d_pair_calibration_staging'
COMMIT='86453c1280c986748717ca79ae4d4d3d45b52973'
SOURCE=('src/developmental_physics/pair_calibration_development.py','scripts/audit_pair_calibration.py',
    'docs/PAIR_CALIBRATION_DEVELOPMENT_PROTOCOL.md','src/developmental_physics/environment.py',
    'src/developmental_physics/probes.py','src/developmental_physics/collect.py',
    'src/developmental_physics/assets/ground_body.xml','pyproject.toml')
TESTS=('tests/test_pair_calibration_development.py','tests/test_audit_pair_calibration.py')

def sha(data):return hashlib.sha256(data).hexdigest()
def json_bytes(obj):return (json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode()

class Checks:
    def __init__(self):self.count=0;self.failed=0;self.violations=[]
    def check(self,condition,label):
        self.count+=1
        if not condition:self.failed+=1;self.violations.append(label)

def main():
    wall,cpu=time.perf_counter(),time.process_time()
    OUTPUT.mkdir(parents=True,exist_ok=False)
    checks=Checks();files={};bundles={};inputs={};code=1;error=None
    def store(name,data,*,kind,source):
        path=OUTPUT/name;path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('xb') as stream:stream.write(data)
        files[name]={'kind':kind,'source':source,'bytes':len(data),'sha256':sha(data)}
        checks.check(path.read_bytes()==data,'copy_exact/'+name)
        return data
    def copy(name,path,kind):
        data=path.read_bytes();inputs[str(path.relative_to(ROOT))]={'bytes':len(data),'sha256':sha(data)}
        return store(name,data,kind=kind,source=path.relative_to(ROOT).as_posix())
    own=Path(__file__).read_bytes()
    store('archival_source.py',own,kind='archival_tool_source',source=Path(__file__).relative_to(ROOT).as_posix())
    attempt={'started_at_utc':datetime.now(timezone.utc).isoformat(),'source_commit':COMMIT,
        'archival_source_sha256':sha(own),'python':sys.version,'output':str(OUTPUT),
        'scope':'Only copy/hash/ZIP/Git-show read verification; no audit, summary, physics, fit or prediction execution',
        'physical_calls':0,'model_updates':0,'new_predictions':0,'audit_executions':0,'summary_executions':0}
    store('attempt.json',json_bytes(attempt),kind='archival_attempt',source='This exclusive archival invocation')
    metadata=None;audit=None;summary_record=None;staging_count=0;staging_bytes=0
    try:
        required={'metadata.json','episodes.json','manifest.json','source_snapshot.zip','trace.jsonl.gz'}
        checks.check({p.name for p in RAW.iterdir() if p.is_file()}==required,'raw_exact_five_original_files')
        raw={name:copy('raw/'+name,RAW/name,'original_formal_raw') for name in sorted(required)}
        metadata=json.loads(raw['metadata.json']);raw_manifest=json.loads(raw['manifest.json'])
        checks.check(set(raw_manifest)==required-{'manifest.json'},'raw_manifest_exact_four')
        for name,value in raw_manifest.items():checks.check(value==sha(raw[name]),'raw_manifest_hash/'+name)
        checks.check(metadata['source_commit']==COMMIT,'raw_clean_commit_identity')
        checks.check(metadata['source_dirty'] is False and metadata['source_status']=='','raw_clean_metadata')
        for key,expected in (('control_calls_attempted',2586),('control_steps',2586),('physics_steps',25860),('model_updates',0)):
            checks.check(metadata[key]==expected,'raw_recorded_budget/'+key)
        audit=json.loads(copy('first_audit.json',ROOT/'external/pair_calibration_20261011_first_audit.json','original_first_independent_audit'))
        checks.check(audit['checks']==466758 and audit['failed']==0,'preserved_first_audit_counts')
        checks.check(audit['archive']['source_commit']==COMMIT,'first_audit_source_identity')
        copy('execution/first_stdout.txt',ROOT/'external/pair_calibration_20261011_first_stdout.txt','original_first_stdout')
        physical_execution=json.loads(copy('execution/first_execution.json',ROOT/'external/pair_calibration_20261011_first_execution.json','original_first_wrapper_execution'))
        checks.check(physical_execution['source_commit']==COMMIT,'first_wrapper_source_identity')
        checks.check(physical_execution['repeated'] is False,'first_wrapper_declared_not_repeated')
        copy('execution/run_pair_calibration_once.py',ROOT/'external/run_pair_calibration_once.py','original_first_physical_wrapper_source')
        copy('checks/c4d_promoted28_stdout.txt',ROOT/'external/c4d_promoted28_stdout.txt','original_promoted_test_stdout')
        copy('checks/c4d_light10_stdout.txt',ROOT/'external/c4d_light10_stdout.txt','original_light_test_stdout')
        summary_files=sorted(p for p in SUMMARY.rglob('*') if p.is_file())
        for path in summary_files:
            name=path.relative_to(SUMMARY).as_posix()
            value=copy('summary_once/'+name,path,'original_once_only_descriptive_summary')
            if name=='execution.json':summary_record=json.loads(value)
        checks.check(summary_record is not None,'summary_execution_preserved')
        checks.check(summary_record['raw_read_passes']==1 and summary_record['audit_executions']==0,'summary_declared_single_raw_pass_no_audit')
        checks.check(summary_record['failed']==0 and summary_record['checks']==44685,'summary_preserved_check_counts')
        for name,item in summary_record['output_sha256'].items():checks.check(files['summary_once/'+name]['sha256']==item,'summary_original_output_hash/'+name)
        copy('summary_delivery.md',ROOT/'external/pair_calibration_20261011_summary_delivery.md','original_summary_delivery')
        git_blobs={}
        for name in SOURCE+TESTS:
            data=subprocess.check_output(['git','show',COMMIT+':'+name],cwd=ROOT)
            git_blobs[name]=data;store('frozen_source/'+name,data,kind='exact_frozen_git_blob',source='git '+COMMIT+':'+name)
        with zipfile.ZipFile(io.BytesIO(raw['source_snapshot.zip'])) as archive:
            names=archive.namelist();checks.check(len(names)==len(set(names))==8,'raw_source_zip_eight_unique')
            checks.check(set(names)==set(SOURCE),'raw_source_zip_exact_source_set')
            checks.check(set(metadata['source_sha256'])==set(SOURCE),'raw_metadata_exact_eight_source_hashes')
            for name in names:
                data=archive.read(name)
                checks.check(sha(data)==metadata['source_sha256'][name],'raw_source_member_recorded_hash/'+name)
                checks.check(data==git_blobs[name],'raw_source_member_frozen_git_blob/'+name)
            checks.check(audit['audit_script_sha256']==sha(git_blobs['scripts/audit_pair_calibration.py']),'first_audit_executed_source_binding')
        stage_files=sorted(p for p in STAGING.rglob('*') if p.is_file() and '__pycache__' not in p.relative_to(STAGING).parts)
        members={};buffer=io.BytesIO()
        with zipfile.ZipFile(buffer,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
            for path in stage_files:
                name=path.relative_to(STAGING).as_posix();data=path.read_bytes()
                checks.check(not Path(name).is_absolute() and '..' not in Path(name).parts,'staging_safe_member/'+name)
                archive.writestr(name,data)
                members[name]={'source':path.relative_to(ROOT).as_posix(),'bytes':len(data),'sha256':sha(data)}
                staging_bytes+=len(data)
        bundle=buffer.getvalue();store('staging_evidence.zip',bundle,kind='all_original_staging_sources_attempts_failures_and_deliveries',source=STAGING.relative_to(ROOT).as_posix())
        with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
            checks.check(len(archive.namelist())==len(members)==len(set(archive.namelist())),'staging_unique_complete_member_set')
            checks.check(archive.testzip() is None,'staging_zip_crc_integrity')
            for name in archive.namelist():
                data=archive.read(name);checks.check(len(data)==members[name]['bytes'] and sha(data)==members[name]['sha256'],'staging_member_sha/'+name)
        staging_count=len(members)
        bundles['staging_evidence.zip']={'source':STAGING.relative_to(ROOT).as_posix(),'members':members,
            'member_count':staging_count,'uncompressed_bytes':staging_bytes,'bundle_bytes':len(bundle),'sha256':sha(bundle),
            'excluded':['__pycache__'],'original_failures_retained':True,'member_hashes_verified':True}
        cumulative={'formal_control_calls':227648,'formal_physics_substeps':2276480,'scalar_model_updates':12852,
            'accounting_source':'Root-authorized project cumulative totals; this archived six-trial batch independently remains2586/25860/0',
            'this_batch':{'formal_control_calls':metadata['control_calls_attempted'],'formal_physics_substeps':metadata['physics_steps'],'scalar_model_updates':0},
            'previous_pair_archive_plus_c5_plus_this_batch_calls':[224582,480,2586]}
        checks.check(sum(cumulative['previous_pair_archive_plus_c5_plus_this_batch_calls'])==227648,'cumulative_call_arithmetic')
        checks.check(cumulative['formal_physics_substeps']==cumulative['formal_control_calls']*10,'cumulative_substep_arithmetic')
        code=int(checks.failed!=0)
    except BaseException as exc:
        error={'type':type(exc).__name__,'message':str(exc)}
        cumulative={'formal_control_calls':227648,'formal_physics_substeps':2276480,'scalar_model_updates':12852,'not_recomputed_after_exception':True}
    finally:
        checks.check(sha(Path(__file__).read_bytes())==sha(own),'archival_source_unchanged')
        if checks.failed:code=1
        result={'created_at_utc':datetime.now(timezone.utc).isoformat(),'source_commit':COMMIT,
            'archival_source_sha256':sha(own),'files':files,'bundles':bundles,'input_hashes':inputs,
            'verification':{'checks':checks.count,'failed':checks.failed,'violations':checks.violations,'exception':error},
            'execution':{'wall_seconds':time.perf_counter()-wall,'cpu_seconds':time.process_time()-cpu,'exit_code':code,
                'physical_calls':0,'model_updates':0,'new_predictions':0,'audit_executions':0,'summary_executions':0,
                'retains_all_partial_files_on_failure':True},'cumulative_accounting':cumulative,
            'manifest_self_hash_excluded':True,'claim_boundary':'Archive integrity only; no new experimental evidence or acceptance decision.'}
        with (OUTPUT/'manifest.json').open('xb') as stream:stream.write(json_bytes(result))
    print(json.dumps({'output':str(OUTPUT),'checks':checks.count,'failed':checks.failed,'exception':error,
        'archived_file_count':len(files),'staging_members':staging_count,'staging_uncompressed_bytes':staging_bytes,
        'manifest_sha256':sha((OUTPUT/'manifest.json').read_bytes()),'wall_seconds':result['execution']['wall_seconds'],
        'cpu_seconds':result['execution']['cpu_seconds'],'exit_code':code}))
    return code

if __name__=='__main__':raise SystemExit(main())
