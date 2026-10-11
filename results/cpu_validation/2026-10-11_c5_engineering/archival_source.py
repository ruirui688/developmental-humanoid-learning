"""Archive immutable first-run evidence; no physics, prediction, fit or audit."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import time
import zipfile

ROOT=Path(__file__).resolve().parents[1]
EXT=ROOT/'external'
DEST=ROOT/'results/cpu_validation/2026-10-11_c5_engineering'
COMMIT='652f9d59ce8e13d552327a0b19f331270fd85aa9'


def sha(data):return hashlib.sha256(data).hexdigest()


def main():
    wall,cpu=time.perf_counter(),time.process_time()
    if DEST.exists():raise FileExistsError('Never overwrite the first engineering archive')
    summary_root=EXT/'c5_engineering_20261011_summary_01'
    summary=list(summary_root.rglob('*'))
    if not (summary_root/'summary.json').is_file():
        raise FileNotFoundError('Wait for the single independent summary')
    DEST.mkdir()
    entries={}
    def copy(source,target):
        destination=DEST/target;destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(source,destination);data=destination.read_bytes()
        assert data==source.read_bytes()
        entries[target]={'kind':'exact_filesystem_copy','source':source.relative_to(ROOT).as_posix(),
                         'bytes':len(data),'sha256':sha(data)}
    raw=EXT/'c5_engineering_20261011_first'
    for p in sorted(raw.iterdir()):
        if p.is_file():copy(p,'first/'+p.name)
    for source,target in {
        'c5_engineering_20261011_first_audit.json':'audit.json',
        'c5_engineering_20261011_first_stdout.txt':'collection_stdout.txt',
        'c5_engineering_20261011_first_execution.json':'collection_execution.json',
        'run_c5_once.py':'collection_wrapper.py',
        'freeze_c5_binding.py':'source_binding_writer.py',
        'c5_promoted_tests01_stdout.txt':'tests/promoted99_stdout.txt',
        'c5_promoted_audit02_stdout.txt':'tests/audit12_increment_stdout.txt',
        'c5_final_audit03_stdout.txt':'tests/audit12_flags_stdout.txt',
        'c5_final33_stdout.txt':'tests/final33_stdout.txt',
    }.items():copy(EXT/source,target)
    for p in summary:
        if p.is_file():copy(p,'summary/'+p.relative_to(summary_root).as_posix())
    for p in EXT.glob('c5_engineering_summary_synthetic_01*'):
        if p.is_file():copy(p,'summary/synthetic/'+p.name.removeprefix('c5_engineering_summary_synthetic_01_'))
    bundles=['c5_staging','c5_engineering_staging','c5_audit_staging',
             'c5_promoted_tests01_work','c5_promoted_audit02_work','c5_final_audit03_work','c5_final33_work']
    for name in bundles:
        source=EXT/name;target='synthetic/'+name+'.zip'
        destination=DEST/target;destination.parent.mkdir(exist_ok=True)
        index={}
        with zipfile.ZipFile(destination,'x',compression=zipfile.ZIP_DEFLATED) as stream:
            for p in sorted(source.rglob('*')):
                if not p.is_file() or '__pycache__' in p.parts or '.pytest_cache' in p.parts:continue
                relative=p.relative_to(source).as_posix();data=p.read_bytes()
                stream.writestr(relative,data);index[relative]=sha(data)
        with zipfile.ZipFile(destination) as stream:
            assert set(stream.namelist())==set(index)
            assert all(sha(stream.read(n))==h for n,h in index.items())
        data=destination.read_bytes()
        entries[target]={'kind':'exact_member_bundle','source_directory':source.relative_to(ROOT).as_posix(),
                         'bytes':len(data),'sha256':sha(data),'member_sha256':index}
    metadata=json.loads((raw/'metadata_final.json').read_text())
    audit=json.loads((DEST/'audit.json').read_text())
    assert metadata['source_binding']['source_commit']==COMMIT
    assert metadata['source_dirty'] is False
    assert audit['checks']==481538 and audit['failed']==0 and audit['engineering_pass'] is True
    assert audit['archive']['budget']['control_calls_attempted']==480
    assert audit['archive']['budget']['known_physics_substeps_lower_bound']==4800
    raw_manifest=json.loads((raw/'manifest.json').read_text())
    assert all(sha((DEST/'first'/name).read_bytes())==expected for name,expected in raw_manifest.items())
    count=0
    with zipfile.ZipFile(DEST/'first/source_snapshot.zip') as stream:
        for name,expected in metadata['source_sha256'].items():
            data=stream.read(name);assert sha(data)==expected
            assert data==subprocess.check_output(['git','show',COMMIT+':'+name],cwd=ROOT)
            count+=1
    copy(Path(__file__),'archival_source.py')
    manifest={'source_commit':COMMIT,'physical_calls':480,'physics_substeps':4800,
              'model_updates':0,'engineering_only':True,'verified_source_git_blobs':count,
              'files':entries,'execution':{'wall_seconds':time.perf_counter()-wall,
              'cpu_seconds':time.process_time()-cpu,'physical_calls':0,'model_updates':0}}
    (DEST/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'archive':str(DEST),'members':len(entries),'source_git_blobs':count,
                     'bytes':sum(x['bytes'] for x in entries.values())}))


if __name__=='__main__':main()
