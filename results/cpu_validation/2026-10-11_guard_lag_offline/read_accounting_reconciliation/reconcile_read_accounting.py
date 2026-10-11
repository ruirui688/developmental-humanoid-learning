"""One-purpose stdlib byte reconciliation; never replay models or the old audit.

The failed first audit and all original artifacts remain byte-identical. This
certificate only explains raw CRLF bytes versus UTF-8 universal-newline text
bytes in the single original read-accounting check.
"""
from __future__ import annotations
import argparse
import ast
from collections import Counter
from datetime import datetime,timezone
import gzip
import hashlib
import io
import json
from pathlib import Path
import platform
import sys
import time
import zipfile

FIRST_AUDIT_SHA='668e6ec65c949f4d7a87349e5b6076dcfeae1d53e9f770364ae4fec943b15da5'
D_MANIFEST_SHA='f5d6e0fc017d708a8c8b2b03a6876704248afee92266985ebd5d137267acb3c6'
D_COMMIT='f7710c7b048dccab3e436d1fa16432f881a35992'
AUDITOR_SHA='bede59d0984edddf6d7384b6d11c0beddae711dfcc616571f4bfd9ee8ce3211b'
RUNNER_SHA='4aa5c9bd0f724d818b205f5de8cb72a18a6064eef736ee001d73b0ed0e217e0c'
RUNNER='src/developmental_physics/guard_lag_offline_development.py'
AUDITOR='scripts/audit_guard_lag_offline.py'
D_FILES=('attempt.json','source_binding.json','source_snapshot.zip','calibration_updates.jsonl.gz',
    'diagnostics.json','rollouts.jsonl.gz','summary.json','run.json','manifest.json')
C_FILES=('metadata.json','episodes.json','seed_results.json','trace.jsonl.gz','source_snapshot.zip','manifest.json')

class Certificate:
    def __init__(self):self.checks=[];self.hash_cost=Counter()
    def check(self,condition,label):self.checks.append({'check':label,'passed':bool(condition)})
    def sha(self,blob,scope):self.hash_cost[scope]+=1;return hashlib.sha256(blob).hexdigest()
    @property
    def failed(self):return sum(not row['passed'] for row in self.checks)

def json_blob(blob):return json.loads(blob.decode('utf-8'))
def same_expr(node,text):return ast.dump(node,include_attributes=False)==ast.dump(ast.parse(text,mode='eval').body,include_attributes=False)
def metric_dicts(tree):
    result=[]
    for node in ast.walk(tree):
        if isinstance(node,ast.Dict):
            values={k.value:v for k,v in zip(node.keys,node.values) if isinstance(k,ast.Constant) and isinstance(k.value,str)}
            if 'identity_sha_reads' in values and 'trace_decompressed_bytes' in values:result.append(values)
    return result

def reconcile(input_dir,source_root,first_audit):
    started_wall,started_cpu=time.perf_counter(),time.process_time();c=Certificate()
    audit_blob=first_audit.read_bytes();audit=json_blob(audit_blob);audit_sha=c.sha(audit_blob,'first_audit_file')
    c.check(audit_sha==FIRST_AUDIT_SHA,'pinned_unchanged_first_audit_bytes')
    c.check(audit['audit_script_sha256']==AUDITOR_SHA,'pinned_first_auditor_identity')
    c.check(audit['checks']==4000346 and audit['failed']==1,'original_first_4000346_checks_one_failure_retained')
    c.check(audit['violations']==[{'check':'exact_source_or_causal_identity','location':'runner_original_read_accounting'}],
        'sole_original_violation_exact_identity')
    c.check(audit['data_consistency_verified'] is False,'original_failed_data_flag_retained')
    files={name:(input_dir/name).read_bytes() for name in D_FILES}
    hashes={name:c.sha(blob,'D_output_file') for name,blob in files.items()}
    manifest=json_blob(files['manifest.json']);binding=json_blob(files['source_binding.json'])
    c.check(hashes['manifest.json']==D_MANIFEST_SHA,'pinned_D_manifest_bytes')
    c.check(hashes==audit['input_file_sha256']==audit['archive']['input_file_sha256'],'all_nine_D_bytes_bound_to_first_audit')
    c.check(set(manifest['files'])==set(D_FILES)-{'manifest.json'},'exact_eight_manifest_output_members')
    for name,entry in manifest['files'].items():
        c.check(entry=={'sha256':hashes[name],'bytes':len(files[name])},'D_manifest_original_bytes/'+name)
    c.check(binding['source_freeze']['source_commit']==D_COMMIT,'pinned_D_source_commit')
    c.check(binding['execution_context']['verified_source_commit']==D_COMMIT and binding['execution_context']['verified_clean_worktree'] is True,
        'original_clean_execution_context')
    raw={name:(source_root/'raw'/name).read_bytes() for name in C_FILES}
    original_hashes={name:c.sha(blob,'C_original_file') for name,blob in raw.items()}
    c.check(original_hashes==audit['archive']['original_input_sha256'],'original_six_C_files_bound_to_first_audit')
    c.check(binding['original_inputs']=={name:{'sha256':original_hashes[name],'bytes':len(blob)} for name,blob in raw.items()},
        'D_bound_original_input_bytes')
    with zipfile.ZipFile(io.BytesIO(files['source_snapshot.zip'])) as archive:
        names=archive.namelist();members={name:archive.read(name) for name in names}
    frozen=binding['source_freeze']['source_sha256']
    c.check(len(names)==len(set(names)) and set(names)==set(frozen)|{'runtime_source_freeze.json'},'original_frozen_zip_unique_exact_coverage')
    for name,expected in frozen.items():c.check(c.sha(members[name],'frozen_source_member')==expected,'frozen_source_member/'+name)
    c.check(c.sha(members['runtime_source_freeze.json'],'runtime_freeze_member')==binding['source_freeze_sha256'] and
        json_blob(members['runtime_source_freeze.json'])==binding['source_freeze'],'original_runtime_freeze_record_bytes')
    c.check(frozen[RUNNER]==RUNNER_SHA and frozen[AUDITOR]==AUDITOR_SHA,'pinned_runner_and_auditor_sources')
    runner_tree=ast.parse(members[RUNNER].decode('utf-8'));auditor_tree=ast.parse(members[AUDITOR].decode('utf-8'))
    opens=[node for node in ast.walk(runner_tree) if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute)
        and isinstance(node.func.value,ast.Name) and node.func.value.id=='gzip' and node.func.attr=='open'
        and len(node.args)>1 and isinstance(node.args[1],ast.Constant) and node.args[1].value=='rt']
    c.check(len(opens)==1 and any(k.arg=='encoding' and isinstance(k.value,ast.Constant) and k.value.value=='utf-8' for k in opens[0].keywords)
        and all(k.arg!='newline' for k in opens[0].keywords),'runner_uses_UTF8_text_with_default_universal_newlines')
    increments=[node for node in ast.walk(runner_tree) if isinstance(node,ast.AugAssign) and isinstance(node.target,ast.Name)
        and node.target.id=='decoded_bytes']
    c.check(len(increments)==1 and isinstance(increments[0].op,ast.Add) and same_expr(increments[0].value,'len(line.encode("utf-8"))'),
        'runner_counts_reencoded_normalized_text_line_bytes')
    rd,ad=metric_dicts(runner_tree),metric_dicts(auditor_tree)
    c.check(len(rd)==1 and same_expr(rd[0]['trace_decompressed_bytes'],'decoded_bytes'),'runner_field_stores_normalized_text_counter')
    c.check(len(ad)==1 and same_expr(ad[0]['trace_decompressed_bytes'],'len(trace_bytes)'),'original_auditor_expected_binary_decompressed_length')
    # One decompression and a text-only pass over the resulting byte buffer.
    # No JSON records, native states, model coefficients or predictions parse.
    trace=gzip.decompress(raw['trace.jsonl.gz']);raw_bytes=len(trace)
    crlf=trace.count(b'\r\n');bare_cr=trace.count(b'\r')-crlf;bare_lf=trace.count(b'\n')-crlf
    text_lines=normalized_bytes=0
    with io.TextIOWrapper(io.BytesIO(trace),encoding='utf-8',newline=None) as stream:
        for line in stream:text_lines+=1;normalized_bytes+=len(line.encode('utf-8'))
    reported=binding['read_cost'];expected_other={'identity_sha_reads':9+len(frozen),'trace_rows_parsed':text_lines,
        'raw_seed_results_bytes':len(raw['seed_results.json'])}
    for key,expected in expected_other.items():c.check(reported[key]==expected,'unchanged_read_counter/'+key)
    c.check(set(reported)==set(expected_other)|{'trace_decompressed_bytes'},'exact_original_read_cost_fields')
    c.check(reported['trace_decompressed_bytes']==normalized_bytes,'original_runner_counter_exactly_matches_UTF8_normalized_text')
    c.check(raw_bytes!=normalized_bytes,'original_binary_and_text_units_differ')
    c.check(raw_bytes-normalized_bytes==crlf,'byte_difference_exactly_equals_CRLF_normalization_count')
    c.check(bare_cr==0 and crlf==text_lines and bare_lf==0,'one_CRLF_per_original_trace_line_no_other_line_endings')
    c.check(reported=={**expected_other,'trace_decompressed_bytes':normalized_bytes},'sole_original_expectation_mismatch_reconciled')
    byte_only_verified=c.failed==0
    return {'schema_version':1,'created_at_utc':datetime.now(timezone.utc).isoformat(),
        'checks':len(c.checks),'failed':c.failed,'results':c.checks,'first_audit_sha256':audit_sha,
        'first_audit_failed':audit['failed'],'first_audit_checks':audit['checks'],
        'first_audit_data_consistency_verified':audit['data_consistency_verified'],
        'sole_original_violation_location':'runner_original_read_accounting',
        'input_file_sha256':hashes,'original_input_sha256':original_hashes,
        'manifest_sha256':hashes['manifest.json'],'source_binding_sha256':hashes['source_binding.json'],
        'source_commit':D_COMMIT,'original_read_cost_unmodified':reported,
        'reconciled_measurements':{'raw_decompressed_bytes':raw_bytes,'normalized_text_utf8_bytes':normalized_bytes,
            'difference_bytes':raw_bytes-normalized_bytes,'CRLF_count':crlf,'bare_CR_count':bare_cr,'bare_LF_count':bare_lf,
            'text_line_count':text_lines,'raw_seed_results_bytes':len(raw['seed_results.json']),'identity_sha_reads':9+len(frozen)},
        'classification':'auditor_expected_binary_bytes_for_normalized_text_counter; collector_field_name_ambiguous',
        'collector_counter_value_correct_for_executed_source_semantics':byte_only_verified,
        'byte_only_reconciliation_verified':byte_only_verified,'effective_data_consistency_verified':byte_only_verified,
        'effective_flag_semantics':'original complete math audit with its sole byte-unit expectation mismatch reconciled; original failed=1 and false flag remain unchanged',
        'no_scientific_gates_or_ranking':True,'tool_sha256':c.sha(Path(__file__).read_bytes(),'executing_tool'),
        'execution':{'wall_seconds':time.perf_counter()-started_wall,'cpu_seconds':time.process_time()-started_cpu,
            'python':sys.version,'platform':platform.platform(),'hash_operations':dict(c.hash_cost),
            'trace_decompression_calls':1,'trace_text_buffer_passes':1,'trace_JSON_records_parsed':0,
            'full_math_audit_reexecutions':0,'model_refits':0,'model_prediction_calls':0,'scalar_RLS_updates':0,
            'physics_control_calls':0,'physics_substeps':0,'online_helper_imports':0,'git_commands':0}}

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--input',required=True,type=Path)
    parser.add_argument('--source-root',required=True,type=Path);parser.add_argument('--first-audit',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path);args=parser.parse_args()
    if args.output.exists():parser.error('Refuse to overwrite original reconciliation')
    report=reconcile(args.input,args.source_root,args.first_audit)
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps({k:report[k] for k in ('checks','failed','first_audit_failed','reconciled_measurements','effective_data_consistency_verified')},allow_nan=False))
    return 0 if report['failed']==0 else 1
if __name__=='__main__':raise SystemExit(main())
