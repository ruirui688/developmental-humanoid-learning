"""One explicitly synthetic tracked-schema coordination run; no real physics.

Uses tracked SyntheticEnv and the original FixedPairMPC mathematics. No pytest
suite is executed. The archived fixture costs cannot be counted as physical data.
"""
from contextlib import redirect_stdout, redirect_stderr
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import platform
import sys
import time
import traceback
import zipfile

ROOT=next(p for p in Path(__file__).resolve().parents if (p/'pyproject.toml').is_file())
BASE=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'src'))

def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def save(path,value):
    Path(path).write_text(json.dumps(value,indent=2,sort_keys=True,allow_nan=False)+'\n',encoding='utf-8',newline='\n')

def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    loaded=importlib.util.module_from_spec(spec)
    sys.modules[name]=loaded
    spec.loader.exec_module(loaded)
    return loaded

def main():
    if (BASE/'execution_started.json').exists() or (BASE/'archive').exists():
        raise RuntimeError('Refusing to repeat this one-run coordination artifact.')
    started,cpu_started=time.perf_counter(),time.process_time()
    inputs=['scripts/audit_pair_frozen.py','scripts/audit_local_frozen.py',
        'src/developmental_physics/pair_frozen_validation.py','src/developmental_physics/local_pair_model.py',
        'src/developmental_physics/local_model.py','src/developmental_physics/assets/ground_body.xml',
        'docs/PAIR_BODY_DEVELOPMENT_PROTOCOL.md','tests/test_pair_frozen_validation.py']
    hashes={name:sha(ROOT/name) for name in inputs}
    save(BASE/'execution_started.json',{'utc':datetime.now(timezone.utc).isoformat(),
        'exact_driver_sha256':sha(__file__),'input_sha256':hashes,'real_physical_budget_delta':0})
    (BASE/'tracked_fixture_source.py').write_bytes((ROOT/'tests/test_pair_frozen_validation.py').read_bytes())
    execution={'synthetic':True,'physical_simulation_calls':0,'real_physical_budget_delta':0,
        'python_executable':sys.executable,'python':sys.version,'platform':platform.platform(),
        'input_sha256':hashes,'exact_driver_sha256':sha(__file__),
        'fixture_declarations':{'environment':'tracked SyntheticEnv','planner':'original FixedPairMPC H15/81',
            'seeds':[0],'prefix_steps':100,'calibration_steps':400,'prediction_steps':100,'control_steps':2,
            'forced_stop':{'trial_index':3,'step_index':100,'joint_index':1,'signal':'velocity exactly 1.0'}},
        'git_source_verification_enabled':False,
        'git_boundary':'Precommit dirty source is rejected; raw source ZIP/hash and both audit dependencies are verified. No Git blob pass is claimed.'}
    summary=None
    with (BASE/'stdout.txt').open('x',encoding='utf-8',newline='\n') as stream, redirect_stdout(stream), redirect_stderr(stream):
        try:
            fixture=module('promoted_pair_synthetic_fixture',ROOT/'tests/test_pair_frozen_validation.py')
            runner,core,env=fixture.runner,fixture.core,fixture.SyntheticEnv
            assert runner.FixedPairMPC is core.FixedPairMPC
            assert runner.GroundBodyEnv is runner._REAL_ENV
            assert (runner.PREFIX_STEPS,runner.CALIBRATION_STEPS,runner.PREDICTION_STEPS,runner.CONTROL_STEPS)==(100,400,100,200)
            env.instances=[]
            env.stop_step=100;env.fail_step=None;env.stop_joint=1;env.stop_signal='v'
            env.partial=env.missing_history=env.prefix_excursion=False
            env.failure_type=RuntimeError;env.fault_trial=3
            runner.GroundBodyEnv=env
            runner.FixedPairMPC=core.FixedPairMPC
            runner.DEVELOPMENT_SEEDS=(0,)
            runner.CONTROL_STEPS=2
            print('Explicit synthetic-only tracked collector; full 100/400/100 and two-step control fixture.')
            collector_start=time.perf_counter()
            metadata=runner.run_pair_validation(BASE/'archive',protocol_path=ROOT/runner.PROTOCOL_PATH,synthetic=True)
            execution['collector_wall_seconds']=time.perf_counter()-collector_start
            assert metadata['synthetic'] is True and metadata['backend']=='synthetic, no physics'
            assert metadata['gpu'] is None and metadata['source_dirty'] is True
            assert len(env.instances)==8
            assert (metadata['control_calls_attempted'],metadata['control_steps'],metadata['physics_steps'],
                    metadata['model_updates'],metadata['vector_model_updates'])==(1409,1409,14090,1600,800)
            auditor=module('promoted_pair_independent_audit',ROOT/'scripts/audit_pair_frozen.py')
            spec=replace(auditor.PAIR_DEVELOPMENT_SPEC,synthetic_fixture=True,seeds=(0,),
                reset_seed_pairs=((0,3757552657),),control_steps=2)
            assert (spec.prefix_steps,spec.calibration_steps,spec.prediction_steps)==(100,400,100)
            audit_start=time.perf_counter()
            result=auditor.audit(BASE/'archive',git_root=None,spec=spec)
            execution['audit_wall_seconds']=time.perf_counter()-audit_start
            save(BASE/'audit.json',result)
            assert result['archive'] is not None, result['violations']
            assert result['failed']==1 and len(result['violations'])==1 and result['violations'][0]['check']=='clean_collection_source', result['violations']
            assert result['archive']['budget']=={'control_calls_attempted':1409,'control_steps':1409,'physics_steps':14090,
                                               'model_updates':1600,'vector_model_updates':800}
            assert result['audit_dependency_sha256']=={'scripts/audit_local_frozen.py':hashes['scripts/audit_local_frozen.py']}
            for name in ('diagonal_contribution','coupled_contribution','coupled_increment'):
                assert result['final_gates'][name]['validated_pass'] is False
            for gate in result['final_gates']['combined_pd_comparison'].values(): assert gate['validated_pass'] is False
            archive_hashes=metadata['source_sha256']
            dependencies=['scripts/audit_pair_frozen.py','scripts/audit_local_frozen.py',
                'src/developmental_physics/pair_frozen_validation.py','src/developmental_physics/local_pair_model.py']
            with zipfile.ZipFile(BASE/'archive/source_snapshot.zip') as snapshot:
                for name in dependencies:
                    assert name in archive_hashes and archive_hashes[name]==hashes[name]
                    assert snapshot.read(name)==(ROOT/name).read_bytes()
            assert all(sha(ROOT/name)==value for name,value in hashes.items()), 'Tracked input changed during coordination.'
            execution.update(status='completed',expected_only_dirty_source_failure=True,
                tracked_inputs_stable=True,archived_audit_dependencies=dependencies,
                synthetic_budget=result['archive']['budget'],audit_checks=result['checks'],audit_failed=result['failed'],
                source_commit=metadata['source_commit'],source_dirty=metadata['source_dirty'],
                all_formal_scientific_passes_rejected=True)
            summary={'status':'completed','checks':result['checks'],'failed':result['failed'],
                'only_failure':'clean_collection_source','synthetic_budget':result['archive']['budget'],
                'physical_simulation_calls':0,'real_physical_budget_delta':0}
            print(json.dumps(summary,indent=2,sort_keys=True))
        except BaseException as exc:
            execution.update(status='failed',error={'type':type(exc).__name__,'message':str(exc)})
            traceback.print_exc()
            raise
        finally:
            execution['wall_seconds']=time.perf_counter()-started
            execution['cpu_seconds']=time.process_time()-cpu_started
            execution['timing_scope']='Driver entry through final execution metadata; excludes process start/imports of driver and final report/hash writing'
            save(BASE/'execution.json',execution)
    save(BASE/'hashes.json',{p.relative_to(BASE).as_posix():sha(p) for p in sorted(BASE.rglob('*')) if p.is_file() and p.name!='hashes.json'})
    print(json.dumps(summary,sort_keys=True))

if __name__=='__main__': main()
