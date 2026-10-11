"""Exclusive byte archive of first C4 A failures; no audit/model execution."""
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import subprocess
import time
import zipfile

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT/'results/cpu_validation/2026-10-11_guard_pair'
RAW = ROOT/'external/guard_pair_20261011_first'
SUMMARY = ROOT/'external/guard_pair_20261011_summary_01'
COMMIT = 'e7d495f03439ab0380a7b1db7cd81cdf43560644'
PROTOCOL = 'docs/GUARD_PAIR_DEVELOPMENT_PROTOCOL.md'
STAGES = ('c4_guard_pair_audit_staging', 'c4_guard_promoted_01',
          'c4_guard_preflight_staging', 'c4_guard_preflight_promoted_03',
          'c4_guard_freeze_checks_01', 'c4_guard_pair_summary_staging',
          'guard_pair_20261011_archive_attempt01')
LOOSE = ('c4_guard_promoted_01_stdout.txt', 'c4_guard_promoted_path02_stdout.txt',
         'c4_pd_real_binding_01_stdout.txt', 'c4_guard_audit_promoted_01_stdout.txt',
         'c4_guard_preflight_promoted_03_stdout.txt', 'c4_guard_freeze_checks_01_stdout.txt',
         'c4_guard_preflight_review.md', 'reconcile_guard_promoted_cost_once.py',
         'check_c4_guard_preflight_03.py', 'check_c4_guard_freeze_01.py')

def sha(data): return hashlib.sha256(data).hexdigest()
def encode(obj): return (json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False)+'\n').encode()

def main():
    wall, cpu = time.perf_counter(), time.process_time()
    OUTPUT.mkdir(parents=True, exist_ok=False)
    files, bundles, input_hashes, violations = {}, {}, {}, []
    count = 0
    def check(ok, label):
        nonlocal count
        count += 1
        if not ok: violations.append(label)
    def store(name, data, kind, source):
        path = OUTPUT/name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('xb') as stream: stream.write(data)
        files[name] = {'kind': kind, 'source': source, 'bytes': len(data), 'sha256': sha(data)}
        check(path.read_bytes() == data, 'exact_copy/'+name)
        return data
    def copy(name, path, kind):
        data = path.read_bytes()
        input_hashes[path.relative_to(ROOT).as_posix()] = {'bytes': len(data), 'sha256': sha(data)}
        return store(name, data, kind, path.relative_to(ROOT).as_posix())
    own = Path(__file__).read_bytes()
    store('archival_source.py', own, 'archival_tool_source', Path(__file__).relative_to(ROOT).as_posix())
    store('attempt.json', encode({'source_commit': COMMIT, 'started_at_utc': datetime.now(timezone.utc).isoformat(),
        'physical_calls': 0, 'model_updates': 0, 'new_predictions': 0, 'audit_executions': 0,
        'summary_executions': 0, 'scope': 'Byte copy/hash/ZIP and readonly Git show only; exclusive output.'}),
        'archival_attempt', 'This exclusive invocation')
    error, protocol = None, None
    try:
        required = {'metadata.json', 'episodes.json', 'seed_results.json', 'trace.jsonl.gz', 'source_snapshot.zip', 'manifest.json'}
        check({p.name for p in RAW.iterdir() if p.is_file()} == required, 'raw_exact_six_files')
        raw = {name: copy('raw/'+name, RAW/name, 'original_formal_raw') for name in sorted(required)}
        metadata, manifest = json.loads(raw['metadata.json']), json.loads(raw['manifest.json'])
        check(set(manifest) == required-{'manifest.json'}, 'raw_manifest_exact_five')
        for name, expected in manifest.items(): check(sha(raw[name]) == expected, 'raw_manifest/'+name)
        check(metadata['source_commit'] == COMMIT and metadata['source_dirty'] is False and metadata['source_status'] == '', 'clean_source_commit')
        check([metadata[k] for k in ('control_calls_attempted','control_steps','physics_steps','model_updates')] == [6318,6318,63180,4800], 'first_paid_cost')
        check([metadata[k] for k in ('completed_trials','terminated_trials','exception_trials','blocked_trials')] == [18,6,0,0], 'first_outcomes')
        protocol = metadata['protocol']
        check(protocol['path'] == PROTOCOL, 'protocol_path')
        audit = json.loads(copy('first_audit.json', ROOT/'external/guard_pair_20261011_first_audit.json', 'original_first_stdlib_audit'))
        check(audit['checks'] == 3207643 and audit['failed'] == 0, 'first_audit_preserved')
        check(audit['archive']['input_hashes'] == {name: sha(data) for name, data in raw.items()}, 'audit_exact_raw_binding')
        check(audit['final_gates']['complete_matrix'] is False, 'failed_complete_matrix_preserved')
        for group in ('model_contribution','selected_pd_comparison'):
            check(all(audit['final_gates'][group][b]['validated_pass'] is False for b in ('raw','guard')), 'failed_scientific_gate_preserved/'+group)
        for name, path in [('execution/first_execution.json','external/guard_pair_20261011_first_execution.json'),
                           ('execution/first_stdout.txt','external/guard_pair_20261011_first_stdout.txt'),
                           ('execution/first_audit_stdout.txt','external/guard_pair_20261011_first_audit_stdout.txt'),
                           ('execution/run_guard_pair_once.py','external/run_guard_pair_once.py')]:
            copy(name, ROOT/path, 'original_first_execution')
        execution = json.loads((OUTPUT/'execution/first_execution.json').read_bytes())
        check(execution['source_commit'] == COMMIT and execution['repeated'] is False, 'exclusive_first_process')
        summary_execution = None
        for path in sorted(SUMMARY.rglob('*')):
            if path.is_file():
                name = path.relative_to(SUMMARY).as_posix()
                data = copy('summary_once/'+name, path, 'original_once_only_summary')
                if name == 'execution.json': summary_execution = json.loads(data)
        check(summary_execution is not None and summary_execution['exit_code'] == 0, 'summary_success')
        check(summary_execution['audit_executions'] == 0 and summary_execution['new_body_predictions'] == 0 and summary_execution['model_parameter_updates'] == 0, 'summary_no_model_or_audit')
        for name, expected in summary_execution['output_sha256'].items():
            check(files['summary_once/'+name]['sha256'] == expected, 'summary_output_sha/'+name)
        copy('summary_once/stdout.txt', ROOT/'external/guard_pair_20261011_summary_01_stdout.txt', 'original_once_summary_stdout')
        read_cost = json.loads((OUTPUT/'summary_once/read_cost.json').read_bytes())
        check(len(read_cost['original_inputs']) == 7 and all(v['read_attempts'] == 1 and v['successful_reads'] == 1
              for v in read_cost['original_inputs'].values()), 'summary_reads_each_once')
        for path in sorted((ROOT/'external/guard_pair_20261011_failure_diagnostic_01').iterdir()):
            if path.is_file(): copy('saved_failure_diagnostic/'+path.name, path, 'saved_prediction_extraction_no_new_model_call')
        copy('saved_failure_diagnostic/stdout.txt', ROOT/'external/guard_pair_20261011_failure_diagnostic_01_stdout.txt', 'original_diagnostic_stdout')
        sources = {}
        test_names = {'tests/test_guard_pair_development.py', 'tests/test_audit_guard_pair_development.py', 'tests/test_pd_selection_binding.py'}
        for name in sorted(set(metadata['source_sha256']) | test_names):
            data = subprocess.check_output(['git','show',COMMIT+':'+name], cwd=ROOT)
            sources[name] = data
            store('frozen_source/'+name, data, 'exact_frozen_git_blob', 'git '+COMMIT+':'+name)
        with zipfile.ZipFile(io.BytesIO(raw['source_snapshot.zip'])) as archive:
            check(len(archive.namelist()) == len(set(archive.namelist())) and set(archive.namelist()) == set(metadata['source_sha256']), 'raw_source_unique_exact_members')
            for name in archive.namelist():
                data = archive.read(name)
                check(sha(data) == metadata['source_sha256'][name], 'raw_source_sha/'+name)
                check(data == sources[name], 'raw_source_git/'+name)
                git_id = subprocess.check_output(['git','rev-parse',COMMIT+':'+name], cwd=ROOT, text=True).strip()
                check(hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest() == git_id, 'raw_git_blob_id/'+name)
        check(protocol['sha256'] == sha(sources[PROTOCOL]), 'frozen_protocol_sha')
        check(audit['audit_script_sha256'] == sha(sources['scripts/audit_guard_pair_development.py']), 'executing_audit_identity')
        for name, expected in audit['audit_dependency_sha256'].items(): check(sha(sources[name]) == expected, 'executing_support_identity/'+name)
        buffer, members = io.BytesIO(), {}
        paths = []
        for dirname in STAGES:
            directory = ROOT/'external'/dirname
            check(directory.is_dir(), 'original_stage_exists/'+dirname)
            paths.extend((dirname+'/'+p.relative_to(directory).as_posix(), p) for p in sorted(directory.rglob('*')) if p.is_file() and '__pycache__' not in p.parts)
        paths.extend(('loose/'+name, ROOT/'external'/name) for name in LOOSE)
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for name, path in paths:
                check(not Path(name).is_absolute() and '..' not in Path(name).parts, 'safe_bundle_path/'+name)
                data = path.read_bytes()
                archive.writestr(name, data)
                members[name] = {'source': path.relative_to(ROOT).as_posix(), 'bytes': len(data), 'sha256': sha(data)}
        data = buffer.getvalue()
        store('staging_evidence.zip', data, 'all_original_engineering_failures_and_checks', 'external stages and exact stdout, excluding __pycache__')
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            check(len(archive.namelist()) == len(set(archive.namelist())) == len(members) and archive.testzip() is None, 'bundle_complete_crc')
            for name in archive.namelist(): check(sha(archive.read(name)) == members[name]['sha256'], 'bundle_member_sha/'+name)
        bundles['staging_evidence.zip'] = {'member_count': len(members), 'bytes': len(data), 'sha256': sha(data), 'members': members,
            'preserves_initial_schema_failures_old_59_version_and_wrapper_miscounts': True}
    except BaseException as exc:
        error = {'type': type(exc).__name__, 'message': str(exc)}
    finally:
        check(sha(Path(__file__).read_bytes()) == sha(own), 'archive_tool_unchanged')
        record = {'created_at_utc': datetime.now(timezone.utc).isoformat(), 'source_commit': COMMIT, 'protocol': protocol,
            'files': files, 'bundles': bundles, 'input_hashes': input_hashes,
            'verification': {'checks': count, 'failed': len(violations), 'violations': violations, 'exception': error},
            'cumulative_accounting': {'prior_formal_control_calls': 232184, 'this_batch_control_calls': 6318,
                'formal_control_calls': 238502, 'formal_physics_substeps': 2385020, 'scalar_model_updates': 17652,
                'this_batch_scalar_updates': 4800},
            'execution': {'wall_seconds': time.perf_counter()-wall, 'cpu_seconds': time.process_time()-cpu,
                'exit_code': int(bool(violations) or error is not None), 'physical_calls': 0, 'model_updates': 0,
                'new_predictions': 0, 'audit_executions': 0, 'summary_executions': 0},
            'manifest_self_hash_excluded': True, 'claim_boundary': 'Byte integrity only; scientific failure preserved.'}
        with (OUTPUT/'manifest.json').open('xb') as stream: stream.write(encode(record))
    print(json.dumps({'output': str(OUTPUT), 'files': len(files), 'checks': count, 'failed': len(violations),
        'exception': error, 'manifest_sha256': sha((OUTPUT/'manifest.json').read_bytes()), 'execution': record['execution']}))
    return record['execution']['exit_code']

if __name__ == '__main__': raise SystemExit(main())
