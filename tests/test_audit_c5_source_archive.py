"""Independent pure source-archive fixtures; never call collector or physics.

Only verify_sources is exercised. All Git reads are in-memory stubs. Invalid
archives are created as new files; the valid fixture and executed sources remain.
"""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import zipfile

import pytest

ROOT=next(p for p in Path(__file__).resolve().parents if (p/'pyproject.toml').exists())
audit_path=Path(__file__).with_name('audit_c5_engineering.py')
if not audit_path.exists():audit_path=ROOT/'scripts/audit_c5_engineering.py'
spec=importlib.util.spec_from_file_location('independent_c5_audit',audit_path)
core=importlib.util.module_from_spec(spec);spec.loader.exec_module(core)

BINDING='docs/C5_ENGINEERING_BINDING.json'
PROTOCOL='docs/C5_ENGINEERING_PROTOCOL.md'
AUDITOR='scripts/audit_c5_engineering.py'
PLAN={'pose':'supine','development_seed':0,'reset_seed':3757552657,
    'trials':['base_identity','wrapper_identity','gain_half','armature_double'],
    'fresh_environment_per_trial':True,'prefix_steps':100,'active_steps':20,
    'physics_substeps_per_call':10,'physics_dt_seconds':.002,'maximum_calls':480,
    'maximum_substeps':4800,'parameter_updates':0,'selected_native_joints':[0,1],
    'active_blocks':'(+.25,+.25)*5 / zero*5 / (-.25,-.25)*5 / zero*5',
    'event_boundary':100,'gain_half':[.5,.5,1.,1.,1.,1.,1.,1.],
    'armature_double_native_values':[.02,.02],
    'study_q_offset_limit_rad':.12,'study_velocity_limit_rad_s':1.}


def digest(value): return hashlib.sha256(value).hexdigest()


def write_archive(path,sources,metadata,duplicate=None):
    path.mkdir(exist_ok=False)
    with zipfile.ZipFile(path/'source_snapshot.zip','x',compression=zipfile.ZIP_DEFLATED) as stream:
        for name,value in sources.items(): stream.writestr(name,value)
        if duplicate is not None: stream.writestr(duplicate,sources[duplicate])
    with (path/'source_metadata_fixture.json').open('x',encoding='utf-8') as stream:
        json.dump(metadata,stream,indent=2)


def fixture(tmp_path):
    sources={name:('inert source fixture '+name).encode() for name in core.RUNTIME if name!=BINDING}
    sources[AUDITOR]=Path(core.__file__).read_bytes()
    binding={'schema_version':1,'draft':False,'protocol_path':PROTOCOL,
        'protocol_sha256':digest(sources[PROTOCOL]),'plan':deepcopy(PLAN),
        'source_sha256':{name:digest(value) for name,value in sources.items()}}
    sources[BINDING]=json.dumps(binding,sort_keys=True).encode()
    metadata={'source_sha256':{name:digest(value) for name,value in sources.items()},
        'fixed_plan':deepcopy(PLAN),'source_binding':{'source_commit':'9'*40,'source_dirty':False,
        'source_status':'','binding_path':BINDING,'binding_sha256':digest(sources[BINDING]),'binding':deepcopy(binding)}}
    path=tmp_path/'valid';write_archive(path,sources,metadata)
    return path,sources,metadata,binding


def replace_binding(sources,metadata,binding):
    sources[BINDING]=json.dumps(binding,sort_keys=True).encode()
    metadata['source_sha256'][BINDING]=digest(sources[BINDING])
    metadata['source_binding']['binding_sha256']=digest(sources[BINDING])
    metadata['source_binding']['binding']=deepcopy(binding)


def check(path,metadata,monkeypatch,blobs,git=True):
    calls=[]
    def fake_git(args,cwd):
        calls.append(list(args))
        assert args[0:2]==['git','show'] and args[2].startswith('9'*40+':')
        return blobs[args[2][41:]]
    monkeypatch.setattr(core.subprocess,'check_output',fake_git)
    checks=core.Checks();error=None
    try: core.verify_sources(path,metadata,checks,Path('inert_git_fixture') if git else None)
    except (OSError,ValueError,TypeError,KeyError,IndexError,zipfile.BadZipFile) as exc:
        error={'type':type(exc).__name__,'message':str(exc)}
    with (path/'source_checks.json').open('x',encoding='utf-8') as stream:
        json.dump({'checks':checks.count,'failed':checks.failed,'violations':checks.violations,
            'exception':error,'stub_git_calls':calls,'real_git_calls':0,
            'physical_calls':0,'collector_imports':0},stream,indent=2)
    return checks,error,calls


@pytest.mark.parametrize('git',[False,True])
def test_exact_source_archive_and_optional_original_commit_blobs(tmp_path,monkeypatch,git):
    path,sources,metadata,_=fixture(tmp_path)
    checks,error,calls=check(path,metadata,monkeypatch,sources,git=git)
    assert error is None and checks.failed==0
    assert len(calls)==(8 if git else 0)


@pytest.mark.parametrize('fault',[
    'zip_bytes','source_hash','git_blob','missing_required','duplicate_zip',
    'dirty','status','commit','binding_record','binding_path','draft',
    'schema_version','schema_bool','plan','coordinated_plan',
    'protocol_hash','self_hash','executed_auditor','unsafe_path'])
def test_corrupted_archive_or_source_binding_rejected(tmp_path,monkeypatch,fault):
    _,sources,metadata,binding=fixture(tmp_path)
    original_blobs=deepcopy(sources);sources=deepcopy(sources);metadata=deepcopy(metadata);binding=deepcopy(binding)
    duplicate=None;git=True
    runner='src/developmental_physics/c5_engineering.py'
    if fault=='zip_bytes': sources[runner]+=b'changed inert body'
    elif fault=='source_hash': metadata['source_sha256'][runner]='0'*64
    elif fault=='git_blob': original_blobs[runner]+=b'different original HEAD'
    elif fault=='missing_required':
        sources.pop(runner);metadata['source_sha256'].pop(runner);binding['source_sha256'].pop(runner)
    elif fault=='duplicate_zip': duplicate=runner
    elif fault=='dirty': metadata['source_binding']['source_dirty']=True
    elif fault=='status': metadata['source_binding']['source_status']=' M inert\n'
    elif fault=='commit': metadata['source_binding']['source_commit']='not_a_commit';git=False
    elif fault=='binding_record': metadata['source_binding']['binding']['draft']=True
    elif fault=='binding_path': metadata['source_binding']['binding_path']='docs/wrong_binding.json'
    elif fault=='draft': binding['draft']=True
    elif fault=='schema_version': binding['schema_version']=2
    elif fault=='schema_bool': binding['schema_version']=True
    elif fault=='plan': binding['plan']['active_steps']=21
    elif fault=='coordinated_plan':
        binding['plan']['maximum_calls']=481;metadata['fixed_plan']['maximum_calls']=481
    elif fault=='protocol_hash': binding['protocol_sha256']='0'*64
    elif fault=='self_hash': binding['source_sha256'][BINDING]='0'*64
    elif fault=='executed_auditor':
        sources[AUDITOR]=b'inert different audit source';original_blobs[AUDITOR]=sources[AUDITOR]
        metadata['source_sha256'][AUDITOR]=digest(sources[AUDITOR]);binding['source_sha256'][AUDITOR]=digest(sources[AUDITOR])
    elif fault=='unsafe_path':
        sources['../escape.py']=b'inert extra source';binding['source_sha256']['../escape.py']=digest(sources['../escape.py'])
        metadata['source_sha256']['../escape.py']=digest(sources['../escape.py']);git=False
    if fault not in ('zip_bytes','source_hash','git_blob','duplicate_zip','dirty','status','commit','binding_record','binding_path'):
        replace_binding(sources,metadata,binding)
        # The inert HEAD consistently records the corrupted binding, so only
        # independent schema/plan/path requirements can reject coordinated changes.
        original_blobs[BINDING]=sources[BINDING]
    path=tmp_path/'corrupted';write_archive(path,sources,metadata,duplicate=duplicate)
    checks,error,_=check(path,metadata,monkeypatch,original_blobs,git=git)
    assert error is not None or checks.failed>0,('source verifier accepted corruption',fault)
