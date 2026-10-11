"""Copy exact single-run pair evidence; no simulation, prediction, fitting or audit."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import time
import zipfile

ROOT = Path(__file__).resolve().parents[1]
EXT = ROOT/'external'
DEST = ROOT/'results/cpu_validation/2026-10-11_pair_body'
COMMIT = '884188416b982ad03c0b3ba6f94999e162ddf98f'
AUDIT_SHA = 'bb717cd064af534a84a4b8fac43e80c16bd59220392d9aaeedc27feee1614456'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    wall, cpu = time.perf_counter(), time.process_time()
    if DEST.exists():
        raise FileExistsError('Never overwrite the single formal evidence archive')
    summary = EXT/'pair_body_20261011_summary_01_summary.json'
    delivery = EXT/'pair_body_20261011_summary_delivery.md'
    if not summary.is_file() or not delivery.is_file():
        raise FileNotFoundError('Wait for the independent single summary and final review')
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
    raw = EXT/'pair_body_20261011_development'
    for path in sorted(raw.iterdir()):
        if path.is_file():
            copy(path, 'development/'+path.name)
    for source, target in {
        'pair_body_20261011_first_audit.json': 'audit.json',
        'pair_body_20261011_first_audit_stdout.txt': 'audit_stdout.txt',
        'pair_body_20261011_collection_stdout.txt': 'collection_stdout.txt',
        'pair_body_20261011_summary_delivery.md': 'result_review.md',
        'c4b_pair_promoted_tests_01_stdout.txt': 'tests/first_promoted_stdout.txt',
        'c4b_pair_promoted_freeze_fix_01_stdout.txt': 'tests/freeze_increment_stdout.txt',
        'c4b_pair_promoted_full_01_stdout.txt': 'tests/full_regression_stdout.txt',
        'c4_elbow_archive_final_review.md': 'reviews/prior_elbow_archive.md',
        'c4_elbow_archive_final_review.json': 'reviews/prior_elbow_archive.json',
        'c4_elbow_tracked_sync_review.json': 'reviews/prior_elbow_entry_sync.json',
    }.items():
        copy(EXT/source, target)
    for path in sorted(EXT.glob('pair_body_20261011_summary_01_*')):
        if path.is_file():
            copy(path, 'summary/'+path.name.removeprefix('pair_body_20261011_summary_01_'))
    for path in sorted(EXT.glob('pair_body_summary_synthetic_01_*')):
        if path.is_file():
            copy(path, 'summary/synthetic/'+path.name.removeprefix('pair_body_summary_synthetic_01_'))
    for path in sorted((EXT/'c4b_pair_promoted_schema_01').rglob('*')):
        if path.is_file():
            copy(path, 'synthetic_schema/'+path.relative_to(EXT/'c4b_pair_promoted_schema_01').as_posix())
    for source, target in {
        'scripts/audit_pair_frozen.py': 'audit_source.py',
        'scripts/audit_local_frozen.py': 'audit_dependency_source.py',
        'src/developmental_physics/pair_frozen_validation.py': 'collector_source.py',
        'src/developmental_physics/local_pair_model.py': 'model_source.py',
        'docs/PAIR_BODY_DEVELOPMENT_PROTOCOL.md': 'protocol.md',
        'tests/test_pair_frozen_validation.py': 'tests/test_pair_frozen_validation.py',
        'tests/test_pair_frozen_audit.py': 'tests/test_pair_frozen_audit.py',
        'tests/test_local_pair_model.py': 'tests/test_local_pair_model.py',
    }.items():
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
    assert sha((DEST/'audit.json').read_bytes()) == AUDIT_SHA
    assert audit['checks'] == 1540296 and audit['failed'] == 0
    assert audit['archive']['budget'] == {'control_calls_attempted': 2919, 'control_steps': 2919,
        'physics_steps': 29190, 'model_updates': 2052, 'vector_model_updates': 1026}
    assert sha((DEST/'audit_source.py').read_bytes()) == audit['audit_script_sha256']
    assert sha((DEST/'audit_dependency_source.py').read_bytes()) == audit['audit_dependency_sha256']['scripts/audit_local_frozen.py']
    for name, expected in json.loads((DEST/'development/manifest.json').read_text()).items():
        assert sha((DEST/'development'/name).read_bytes()) == expected
    source_count = 0
    with zipfile.ZipFile(DEST/'development/source_snapshot.zip') as snapshot:
        for name, expected in metadata['source_sha256'].items():
            data = snapshot.read(name)
            assert sha(data) == expected
            assert data == subprocess.check_output(['git', 'show', COMMIT+':'+name], cwd=ROOT)
            source_count += 1
    readme = '''# 肩—肘首次开发：校准与组合PD速度停止

从clean `8841884`一次执行，6完整/6研究停止/12依赖blocked，2919控制/29190子步/2052 scalar RLS/1026 vector更新。cal三个seed在active170肘速度停止，未发布learned模型；组合PD三个seed在active1肘速度停止。nominal MPC与zero完整。耦合收益尚未评价，不把未运行记作耦合机制已被否定；全部科学门未通过。

首次独立审计1540296项零失败是记录/数学一致性；全部原字节和停止保留，不补跑。[metadata](development/metadata.json)、[episodes](development/episodes.json)、[seed results](development/seed_results.json)、[trace](development/trace.jsonl.gz)、[source ZIP](development/source_snapshot.zip)、[audit](audit.json)、[独立summary](summary/summary.json)、[审读](result_review.md)、[manifest](manifest.json)。

累计正式物理224582调用/2245820子步/12852 scalar RLS；synthetic、审计、summary与规划成本单列。已见开发0/1/2，不称未见泛化、安全或全身技能。归档仅复制核对，不执行物理、模型或审计。[完整结果](../../../docs/PAIR_BODY_DEVELOPMENT_RESULTS.md)、[持续目标](../../../docs/CONTINUOUS_EXECUTION_PLAN.md)。
'''
    (DEST/'README.md').write_text(readme, encoding='utf-8', newline='\n')
    data = (DEST/'README.md').read_bytes()
    entries['README.md'] = {'kind': 'generated_archive_index', 'source': 'external/archive_pair_body.py',
                           'bytes': len(data), 'sha256': sha(data)}
    execution = {'wall_seconds': time.perf_counter()-wall, 'cpu_seconds': time.process_time()-cpu,
        'new_physical_calls': 0, 'new_physics_substeps': 0, 'model_prediction_or_update_calls': 0,
        'audit_reexecutions': 0, 'summary_reexecutions': 0,
        'scope': 'Copies and raw hash/Git/ZIP verification; excludes final execution and manifest writes'}
    (DEST/'archival_execution.json').write_text(json.dumps(execution, indent=2)+'\n', encoding='utf-8')
    data = (DEST/'archival_execution.json').read_bytes()
    entries['archival_execution.json'] = {'kind': 'generated_archival_provenance', 'source': 'external/archive_pair_body.py',
                                        'bytes': len(data), 'sha256': sha(data)}
    manifest = {'source_commit': COMMIT, 'source_dirty': False, 'verified_git_source_files': source_count,
        'purpose': 'Exact original bytes; manifest excludes itself', 'files': entries,
        'physical_budget': audit['archive']['budget'],
        'formal_cumulative_physics': {'control_calls': 224582, 'physics_substeps': 2245820, 'rls_updates': 12852},
        'first_audit': {'checks': audit['checks'], 'failed': 0, 'sha256': AUDIT_SHA},
        'scientific_gates': audit['final_gates'], 'archival_execution': execution,
        'claim_boundary': 'Incomplete pair calibration and failed combined PD. Coupled learned control not evaluated.'}
    (DEST/'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    assert {p.relative_to(DEST).as_posix() for p in DEST.rglob('*') if p.is_file()} == set(entries)|{'manifest.json'}
    print(json.dumps({'archived_files': len(entries), 'verified_git_sources': source_count,
        'new_physical_calls': 0, 'model_calls': 0, 'audit_reexecutions': 0, 'summary_reexecutions': 0}))


if __name__ == '__main__':
    main()
