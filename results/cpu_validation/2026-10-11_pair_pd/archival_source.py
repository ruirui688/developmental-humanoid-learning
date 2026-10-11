"""Exclusive pair-PD evidence archive: copy/hash/ZIP/readonly Git verification."""
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
OUTPUT=ROOT/'results/cpu_validation/2026-10-11_pair_pd'
RAW=ROOT/'external/pair_pd_20261011_first'
SUMMARY=ROOT/'external/pair_pd_20261011_summary_01'
COMMIT='f9f35fe9bb338aa398cc426e144eff048fde3746'
PROTOCOL='docs/PAIR_PD_DEVELOPMENT_PROTOCOL.md'
STAGING=('c4_pair_pd_staging','c4_pair_pd_audit_staging','c4_pair_pd_schema_01','c4_pair_pd_schema_02',
    'c4_pair_pd_schema_03','c4_pair_pd_selection_01','c4c_promoted_tests01_work')
STDOUT=('c4c_promoted_tests01_stdout.txt','c4c_audit_fix02_stdout.txt')
TESTS=('tests/test_pair_pd_development.py','tests/test_pair_pd_audit.py')

def sha(data):return hashlib.sha256(data).hexdigest()
def json_bytes(obj):return (json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode()
class Checks:
    def __init__(self):self.count=0;self.failed=0;self.violations=[]
    def check(self,condition,label):
        self.count+=1
        if not condition:self.failed+=1;self.violations.append(label)

def main():
    wall,cpu=time.perf_counter(),time.process_time();OUTPUT.mkdir(parents=True,exist_ok=False)
    checks=Checks();files={};bundles={};input_hashes={};code=1;error=None;protocol=None
    def store(name,data,kind,source):
        path=OUTPUT/name;path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('xb') as f:f.write(data)
        files[name]={'kind':kind,'source':source,'bytes':len(data),'sha256':sha(data)}
        checks.check(path.read_bytes()==data,'copy_exact/'+name);return data
    def copy(name,path,kind):
        data=path.read_bytes();input_hashes[path.relative_to(ROOT).as_posix()]={'bytes':len(data),'sha256':sha(data)}
        return store(name,data,kind,path.relative_to(ROOT).as_posix())
    own=Path(__file__).read_bytes()
    store('archival_source.py',own,'archival_tool_source',Path(__file__).relative_to(ROOT).as_posix())
    attempt={'started_at_utc':datetime.now(timezone.utc).isoformat(),'python':sys.version,'source_commit':COMMIT,
        'archival_source_sha256':sha(own),'physical_calls':0,'model_updates':0,'new_predictions':0,'audit_executions':0,'summary_executions':0,
        'scope':'Only original-file copy/hash/ZIP and readonly Git show; retain every failure, no overwrite/delete'}
    store('attempt.json',json_bytes(attempt),'archival_attempt','This exclusive archival invocation')
    member_count=uncompressed=bundle_size=0
    try:
        required={'metadata.json','episodes.json','selection.json','manifest.json','source_snapshot.zip','trace.jsonl.gz'}
        checks.check({p.name for p in RAW.iterdir() if p.is_file()}==required,'raw_exact_six_files')
        raw={name:copy('raw/'+name,RAW/name,'original_formal_selection' if name=='selection.json' else 'original_formal_raw') for name in sorted(required)}
        metadata=json.loads(raw['metadata.json']);raw_manifest=json.loads(raw['manifest.json'])
        checks.check(set(raw_manifest)==required-{'manifest.json'},'raw_manifest_exact_five')
        for name,value in raw_manifest.items():checks.check(value==sha(raw[name]),'raw_manifest/'+name)
        checks.check(metadata['source_commit']==COMMIT and metadata['source_dirty'] is False and metadata['source_status']=='','raw_clean_commit')
        checks.check(metadata['control_calls_attempted']==4536 and metadata['control_steps']==4536 and metadata['physics_steps']==45360 and metadata['model_updates']==0,'raw_recorded_budget')
        protocol=dict(metadata['protocol']);checks.check(protocol['path']==PROTOCOL,'explicit_frozen_protocol_path')
        first_audit=json.loads(copy('first_audit.json',ROOT/'external/pair_pd_20261011_first_audit.json','original_first_stdlib_audit'))
        checks.check(first_audit['check_count']==591017 and first_audit['failed_checks']==0 and first_audit['validated_selection'] is True,'preserved_first_audit')
        physical_execution=json.loads(copy('execution/first_execution.json',ROOT/'external/pair_pd_20261011_first_execution.json','original_first_physical_wrapper_execution'))
        checks.check(physical_execution['source_commit']==COMMIT and physical_execution['repeated'] is False,'first_wrapper_source_and_once')
        copy('execution/first_stdout.txt',ROOT/'external/pair_pd_20261011_first_stdout.txt','original_first_physical_stdout')
        copy('execution/run_pair_pd_once.py',ROOT/'external/run_pair_pd_once.py','original_first_physical_wrapper_source')
        for name in STDOUT:copy('checks/'+name,ROOT/'external'/name,'original_promoted_failure_or_fix_stdout')
        summary_record=None
        for path in sorted(SUMMARY.rglob('*')):
            if path.is_file():
                name=path.relative_to(SUMMARY).as_posix();data=copy('summary_once/'+name,path,'original_once_only_summary')
                if name=='execution.json':summary_record=json.loads(data)
        checks.check(summary_record is not None and summary_record['raw_read_passes']==1 and summary_record['audit_executions']==0,'summary_once_no_audit')
        checks.check(summary_record['checks']==198435 and summary_record['failed']==0,'summary_preserved_counts')
        for name,value in summary_record['output_sha256'].items():checks.check(files['summary_once/'+name]['sha256']==value,'summary_original_hash/'+name)
        copy('summary_delivery.md',ROOT/'external/pair_pd_20261011_summary_delivery.md','original_summary_delivery')
        source_bytes={}
        for name in sorted(set(metadata['source_sha256'])|set(TESTS)):
            blob=subprocess.check_output(['git','show',COMMIT+':'+name],cwd=ROOT);source_bytes[name]=blob
            store('frozen_source/'+name,blob,'exact_frozen_git_blob','git '+COMMIT+':'+name)
        with zipfile.ZipFile(io.BytesIO(raw['source_snapshot.zip'])) as archive:
            names=archive.namelist();checks.check(len(names)==len(set(names)) and set(names)==set(metadata['source_sha256']),'raw_source_exact_member_set')
            for name in names:
                data=archive.read(name);checks.check(sha(data)==metadata['source_sha256'][name],'raw_source_recorded_sha/'+name)
                checks.check(data==source_bytes[name],'raw_source_exact_git_blob/'+name)
                git_sha=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
                checks.check(git_sha==metadata['source_git_blobs'][name],'raw_source_git_blob_id/'+name)
        checks.check(sha(source_bytes[PROTOCOL])==protocol['sha256'],'protocol_binding_sha')
        checks.check(first_audit['audit_sources_sha256']['auditor']==sha(source_bytes['scripts/audit_pair_pd.py']),'first_runtime_auditor_binding')
        checks.check(first_audit['audit_sources_sha256']['common']==sha(source_bytes['scripts/audit_local_frozen.py']),'first_runtime_common_binding')
        buffer=io.BytesIO();members={};prefix_counts={}
        with zipfile.ZipFile(buffer,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
            for dirname in STAGING:
                directory=ROOT/'external'/dirname;checks.check(directory.is_dir(),'required_original_stage/'+dirname)
                paths=sorted(p for p in directory.rglob('*') if p.is_file() and '__pycache__' not in p.relative_to(directory).parts)
                prefix_counts[dirname]=len(paths)
                for path in paths:
                    name=dirname+'/'+path.relative_to(directory).as_posix();data=path.read_bytes()
                    checks.check(not Path(name).is_absolute() and '..' not in Path(name).parts,'safe_stage_member/'+name)
                    archive.writestr(name,data);members[name]={'source':path.relative_to(ROOT).as_posix(),'bytes':len(data),'sha256':sha(data)};uncompressed+=len(data)
            for filename in STDOUT:
                path=ROOT/'external'/filename;data=path.read_bytes();name='promoted_stdout/'+filename
                archive.writestr(name,data);members[name]={'source':path.relative_to(ROOT).as_posix(),'bytes':len(data),'sha256':sha(data)};uncompressed+=len(data)
        bundle=buffer.getvalue();bundle_size=len(bundle)
        store('staging_evidence.zip',bundle,'all_original_pd_staging_failed_schemas_old_sort_selection_and_promoted_attempts','external PD staging prefixes, excluding __pycache__')
        with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
            checks.check(len(archive.namelist())==len(set(archive.namelist()))==len(members),'stage_complete_unique_member_set')
            checks.check(archive.testzip() is None,'stage_zip_crc')
            for name in archive.namelist():
                data=archive.read(name);checks.check(len(data)==members[name]['bytes'] and sha(data)==members[name]['sha256'],'stage_member_sha/'+name)
        member_count=len(members)
        bundles['staging_evidence.zip']={'member_count':member_count,'uncompressed_bytes':uncompressed,'bundle_bytes':bundle_size,'sha256':sha(bundle),
            'prefix_counts':prefix_counts,'members':members,'excluded':['__pycache__'],'original_01_02_failures_and_03_old_sort_preserved':True,
            'selection01_and_promoted_two_failures_fix02_preserved':True,'member_hashes_verified':True}
        selection_inputs={'source_commit':COMMIT,'protocol':protocol,
            'raw_selection':{'path':'raw/selection.json','sha256':files['raw/selection.json']['sha256']},
            'first_audit':{'path':'first_audit.json','sha256':files['first_audit.json']['sha256']},
            'independent_summary':{'path':'summary_once/summary.json','sha256':files['summary_once/summary.json']['sha256']},
            'picked':first_audit['selection']['picked'],'binding_record_status':'root may generate a separate exact schema record after archival delivery',
            'avoid_hash_cycle':'If later record is included in files, bind immutable input hashes above and do not embed manifest SHA in that record'}
        cumulative={'formal_control_calls':232184,'formal_physics_substeps':2321840,'scalar_model_updates':12852,
            'prior_formal_control_calls':227648,'this_batch_control_calls':4536,'this_batch_physics_substeps':45360,'this_batch_scalar_updates':0}
        checks.check(227648+4536==232184 and 232184*10==2321840,'cumulative_arithmetic')
        code=int(checks.failed!=0)
    except BaseException as exc:
        error={'type':type(exc).__name__,'message':str(exc)};selection_inputs=None
        cumulative={'formal_control_calls':232184,'formal_physics_substeps':2321840,'scalar_model_updates':12852,'exception_preserved':True}
    finally:
        checks.check(sha(Path(__file__).read_bytes())==sha(own),'archival_source_unchanged')
        if checks.failed:code=1
        record={'created_at_utc':datetime.now(timezone.utc).isoformat(),'source_commit':COMMIT,'protocol':protocol,
            'archival_source_sha256':sha(own),'files':files,'bundles':bundles,'input_hashes':input_hashes,
            'verification':{'checks':checks.count,'failed':checks.failed,'violations':checks.violations,'exception':error},
            'execution':{'wall_seconds':time.perf_counter()-wall,'cpu_seconds':time.process_time()-cpu,'exit_code':code,
                'physical_calls':0,'model_updates':0,'new_predictions':0,'audit_executions':0,'summary_executions':0,'retain_all_partial_files_on_failure':True},
            'cumulative_accounting':cumulative,'selection_binding_inputs':selection_inputs,'manifest_self_hash_excluded':True,
            'claim_boundary':'Archival integrity only; no rerun or scientific acceptance decision.'}
        with (OUTPUT/'manifest.json').open('xb') as f:f.write(json_bytes(record))
    print(json.dumps({'output':str(OUTPUT),'checks':checks.count,'failed':checks.failed,'exception':error,'files':len(files),
        'staging_members':member_count,'staging_bytes':uncompressed,'zip_bytes':bundle_size,'manifest_sha256':sha((OUTPUT/'manifest.json').read_bytes()),
        'wall_seconds':record['execution']['wall_seconds'],'cpu_seconds':record['execution']['cpu_seconds'],'exit_code':code}))
    return code

if __name__=='__main__':raise SystemExit(main())
