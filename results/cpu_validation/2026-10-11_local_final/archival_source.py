"""Copy frozen evidence bytes once; no model replay or physical experiment."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import time
import zipfile

ROOT = Path(__file__).resolve().parents[1]
EXT = ROOT / 'external'
DEST = ROOT / 'results/cpu_validation/2026-10-11_local_final'

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    started, cpu = time.perf_counter(), time.process_time()
    DEST.mkdir(exist_ok=False)
    shutil.copytree(EXT/'local_frozen_20261011_final', DEST/'final')
    pairs = {
        'local_frozen_20261011_final_audit.json': 'audit.json',
        'local_frozen_20261011_first_audit_stdout.txt': 'audit_stdout.txt',
        'local_frozen_20261011_collection_stdout.txt': 'collection_stdout.txt',
        'local_frozen_20261011_final_summary.json': 'summary.json',
        'local_final_review_summary_executed_01.py': 'summary_source.py',
        'local_final_review_summary_execute_01.py': 'summary_wrapper.py',
        'local_final_review_summary_execution_01.json': 'summary_execution.json',
        'local_final_review_summary_stdout_01.txt': 'summary_stdout.txt',
        'local_final_review_tables_01.json': 'tables.json',
        'local_final_review_extract_tables_01.py': 'table_extraction_source.py',
        'local_final_cross_review.md': 'protocol_cross_review.md',
        'local_final_results_review.md': 'result_review.md',
        'local_final_review_write_report_01.py': 'report_source.py',
        'local_final_results_review_provenance_01.json': 'report_provenance.json',
    }
    for src, dest in pairs.items():
        shutil.copyfile(EXT/src, DEST/dest)
        assert sha(EXT/src) == sha(DEST/dest)
    shutil.copyfile(ROOT/'scripts/audit_local_frozen.py', DEST/'audit_source.py')
    shutil.copyfile(Path(__file__), DEST/'archival_source.py')
    audit = json.loads((DEST/'audit.json').read_text(encoding='utf-8'))
    assert sha(DEST/'audit_source.py') == audit['audit_script_sha256']
    metadata = json.loads((DEST/'final/metadata.json').read_text(encoding='utf-8'))
    assert metadata['source_dirty'] is False
    assert metadata['source_commit'] == '449079af0961d5dbc47afc9e26d9db424aafa947'
    raw_manifest = json.loads((DEST/'final/manifest.json').read_text(encoding='utf-8'))
    for name, expected in raw_manifest.items():
        assert sha(DEST/'final'/name) == expected
    source_count = 0
    with zipfile.ZipFile(DEST/'final/source_snapshot.zip') as snap:
        for name, expected in metadata['source_sha256'].items():
            data = snap.read(name)
            assert hashlib.sha256(data).hexdigest() == expected
            original = subprocess.check_output(['git','show', metadata['source_commit']+':'+name],cwd=ROOT)
            assert original == data, name
            source_count += 1
    report = {
        'purpose':'Exact-byte final evidence archive, no physical or model work',
        'source_commit':metadata['source_commit'],
        'source_dirty':False,
        'verified_git_source_files': source_count,
        'file_sha256':{p.relative_to(DEST).as_posix():sha(p) for p in sorted(DEST.rglob('*')) if p.is_file()},
        'raw_manifest':raw_manifest,
        'physical_budget':audit['archive']['budget'],
        'cumulative_formal_physics':{'control_calls':208850,'physics_substeps':2088500,'rls_updates':9900},
        'first_audit_sha256':sha(DEST/'audit.json'),
        'first_audit_checks':audit['checks'], 'first_audit_failed':audit['failed'],
        'final_gates':audit['final_gates'],
        'read_only_costs':{'audit':audit['execution'],
            'summary':json.loads((DEST/'summary.json').read_text(encoding='utf-8'))['execution']},
        'archival_cost':{'wall_seconds':time.perf_counter()-started,'cpu_seconds':time.process_time()-cpu,
            'new_physical_interactions':0,'model_prediction_or_update_calls':0},
        'note':'Final README is added after this manifest; physical evidence hashes remain exact. New shoulder seeds20/21/22 are now seen.'
    }
    (DEST/'manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps({'copied_files':len(report['file_sha256']),'verified_git_sources':source_count,
        'wall_seconds':report['archival_cost']['wall_seconds'],'audit_failed':audit['failed']}))

if __name__=='__main__':
    main()
