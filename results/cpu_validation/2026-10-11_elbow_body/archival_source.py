"""Single exact-byte archive; no physical, model, audit or summary work."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import time
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT/'results/cpu_validation/2026-10-11_elbow_body'
EXT = ROOT/'external'
COMMIT = '46077b1d30089d68f1c935e3fc547dfdfa4c4e66'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    wall, cpu = time.perf_counter(), time.process_time()
    if DEST.exists():
        raise FileExistsError('Never overwrite or repeat the formal evidence archive')
    summary_path = EXT/'elbow_body_20261011_summary_01_summary.json'
    if not summary_path.is_file():
        raise FileNotFoundError('Wait for single independent summary before creating archive')
    DEST.mkdir()
    entries = {}
    def copy(source, target):
        destination = DEST/target
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        data = destination.read_bytes()
        assert data == source.read_bytes()
        entries[target] = {'kind': 'exact_filesystem_copy', 'source': source.relative_to(ROOT).as_posix(),
                           'bytes': len(data), 'sha256': sha(data)}
    raw = EXT/'elbow_body_20261011_development'
    for path in sorted(raw.iterdir()):
        if path.is_file():
            copy(path, 'development/'+path.name)
    pairs = {
        'elbow_body_20261011_first_audit.json': 'audit.json',
        'elbow_body_20261011_first_audit_stdout.txt': 'audit_stdout.txt',
        'elbow_body_20261011_collection_stdout.txt': 'collection_stdout.txt',
        'elbow_body_20261011_summary_delivery.md': 'result_review.md',
        'c4a_body_affected_tests_stdout.txt': 'tests/affected_tests_stdout.txt',
        'c4a_body_elbow_native_test_stdout.txt': 'tests/elbow_native_stdout.txt',
        'c4a_body_audit_cross_review.md': 'reviews/joint_generalization.md',
        'c4a_body_freeze_increment_review.md': 'reviews/freeze_increment.md',
    }
    for source, target in pairs.items():
        copy(EXT/source, target)
    for path in sorted(EXT.glob('elbow_body_20261011_summary_01_*')):
        if path.is_file():
            copy(path, 'summary/'+path.name.removeprefix('elbow_body_20261011_summary_01_'))
    git_sources = {
        'scripts/audit_local_frozen.py': 'audit_source.py',
        'src/developmental_physics/local_frozen_validation.py': 'collector_source.py',
        'docs/ELBOW_BODY_DEVELOPMENT_PROTOCOL.md': 'protocol.md',
        'tests/test_local_frozen_validation.py': 'tests/test_local_frozen_validation.py',
        'tests/test_local_frozen_audit.py': 'tests/test_local_frozen_audit.py',
        'tests/test_joint_frozen_audit.py': 'tests/test_joint_frozen_audit.py',
    }
    for source, target in git_sources.items():
        data = subprocess.check_output(['git', 'show', COMMIT+':'+source], cwd=ROOT)
        destination = DEST/target
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        entries[target] = {'kind': 'exact_git_blob', 'source': source, 'source_commit': COMMIT,
                           'bytes': len(data), 'sha256': sha(data)}
    copy(Path(__file__), 'archival_source.py')
    metadata = json.loads((DEST/'development/metadata.json').read_text(encoding='utf-8'))
    audit = json.loads((DEST/'audit.json').read_text(encoding='utf-8'))
    assert metadata['source_commit'] == COMMIT and metadata['source_dirty'] is False
    assert sha((DEST/'audit.json').read_bytes()) == '1bd3632fd805064951addf72120992b63dca2df255fddc54840b22d014c4f78a'
    assert sha((DEST/'audit_source.py').read_bytes()) == audit['audit_script_sha256']
    raw_manifest = json.loads((DEST/'development/manifest.json').read_text(encoding='utf-8'))
    for name, expected in raw_manifest.items():
        assert sha((DEST/'development'/name).read_bytes()) == expected
    source_count = 0
    with zipfile.ZipFile(DEST/'development/source_snapshot.zip') as snapshot:
        for name, expected in metadata['source_sha256'].items():
            data = snapshot.read(name)
            assert sha(data) == expected
            assert data == subprocess.check_output(['git', 'show', COMMIT+':'+name], cwd=ROOT)
            source_count += 1
    readme = '''# 左肘身体模型开发负结果的原始证据

从clean `46077b1`一次执行，15完整/6研究停止，5292控制/52920子步/900RLS；模型贡献、PD比较和完整矩阵门均未过。731662项首次独立审计零失败。全部失败及截断指标保留，不补跑。

记录入口：[metadata](development/metadata.json)、[episodes](development/episodes.json)、[seed results](development/seed_results.json)、[raw trace](development/trace.jsonl.gz)、[源码ZIP](development/source_snapshot.zip)、[首次audit](audit.json)、[独立summary](summary/summary.json)、[独立结果审读](result_review.md)、[manifest](manifest.json)。

本批实际累计正式物理221663调用/2216630子步/10800RLS；合成测试、规划、审计与独立summary计算单列。模型/PD协议先冻结，development0/1/2已见，不能称未见评价。归档只复制、核验原始字节，不重新拟合、预测、运行物理或审计。

仓库结果：[完整说明](../../../docs/ELBOW_BODY_DEVELOPMENT_RESULTS.md)；持续推进：[阶段账本](../../../docs/CONTINUOUS_EXECUTION_PLAN.md)。
'''
    (DEST/'README.md').write_text(readme, encoding='utf-8', newline='\n')
    for target in ('README.md',):
        data = (DEST/target).read_bytes()
        entries[target] = {'kind': 'generated_archive_index', 'source': 'external/archive_elbow_body.py',
                           'bytes': len(data), 'sha256': sha(data)}
    execution = {'wall_seconds': time.perf_counter()-wall, 'cpu_seconds': time.process_time()-cpu,
                 'new_physical_calls': 0, 'new_physics_substeps': 0, 'model_prediction_or_update_calls': 0,
                 'audit_reexecutions': 0, 'summary_reexecutions': 0,
                 'scope': 'archive copies, raw hashes and Git/source ZIP verification; excludes final manifest write'}
    (DEST/'archival_execution.json').write_text(json.dumps(execution, indent=2)+'\n', encoding='utf-8')
    data = (DEST/'archival_execution.json').read_bytes()
    entries['archival_execution.json'] = {'kind': 'generated_archival_provenance', 'source': 'external/archive_elbow_body.py',
                                          'bytes': len(data), 'sha256': sha(data)}
    manifest = {'purpose': 'Exact original bytes; manifest itself excluded from self-hashing',
                'source_commit': COMMIT, 'source_dirty': False, 'verified_git_source_files': source_count,
                'files': entries, 'physical_budget': audit['archive']['budget'],
                'formal_cumulative_physics': {'control_calls': 221663, 'physics_substeps': 2216630, 'rls_updates': 10800},
                'first_audit': {'checks': audit['checks'], 'failed': audit['failed'], 'sha256': sha((DEST/'audit.json').read_bytes())},
                'scientific_gates': audit['final_gates'], 'archival_execution': execution,
                'claim_boundary': 'Specified elbow development failed. No independent holdout, safety or skill claim.'}
    (DEST/'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    assert {p.relative_to(DEST).as_posix() for p in DEST.rglob('*') if p.is_file()} == set(entries)|{'manifest.json'}
    print(json.dumps({'archived_files': len(entries), 'verified_git_sources': source_count,
                      'new_physical_calls': 0, 'model_calls': 0, 'audit_reexecutions': 0, 'summary_reexecutions': 0}))


if __name__ == '__main__':
    main()
