"""Archive a first FR3 stage, transcribing its new report input once."""
from pathlib import Path
import argparse
import hashlib
import json
import time

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--stage', choices=('prediction','control'), required=True)
parser.add_argument('--capture-kind', choices=('first','physical_first'), default='first')
args = parser.parse_args()
assert args.stage=='control' or args.capture_kind=='first'
source = root/('external/fr3_'+args.stage+'_'+args.capture_kind)
dest = root/('results/cpu_validation/2026-10-12_full_request_pair_'+args.stage)
assert (source/'first_execution_receipt.json').is_file(), 'stage process still active'
assert not dest.exists(), 'first stage archive exists; do not rerun'
dest.mkdir()
start_wall, start_cpu = time.perf_counter(), time.process_time()
pins, cache = {}, {}
def identity(data):
    return {'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
def save(name, data):
    target = dest/name
    target.parent.mkdir(parents=True,exist_ok=True)
    with target.open('xb') as stream:
        stream.write(data)
    pins[name] = identity(data)
def encoded(value):
    return (json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode()
for path in sorted(source.rglob('*')):
    if path.is_file():
        name=path.relative_to(source).as_posix()
        data=path.read_bytes()
        save(name,data)
        if name in ('raw/run.json','raw/metrics.json','raw/manifest.json','first_execution_receipt.json'):
            cache[name]=json.loads(data)
for name, expected in cache['raw/manifest.json']['files'].items():
    assert pins['raw/'+name] == expected, name
run, metrics = cache['raw/run.json'],cache['raw/metrics.json']
assert run['experiment_id'] == ('FR3A' if args.stage=='prediction' else 'FR3B')
save('report_inputs.json',encoded({
    'experiment_id':run['experiment_id'],'source':run['source'],'status':run['status'],
    'runtime':run['runtime'],'cost':run['cost'],'failure':run['failure'],
    'unattempted_seeds':run['unattempted_seeds'],'seed_results':run['seed_results'],
    'metrics':metrics,'first_execution':cache['first_execution_receipt.json'],
    'raw_verified_for_copy_only':True,'models_or_physics_or_metrics_recomputed':0}))
launchers=['run_fr3_first_once.py','archive_fr3_first_once.py']
if args.capture_kind=='physical_first':
    launchers.append('run_fr3_control_after_checkpoint_once.py')
    assert cache['first_execution_receipt.json']['first_physical_attempt'] is True
for name in launchers:
    save('launchers/'+name,(root/'external'/name).read_bytes())
save('archive_receipt.json',encoded({'first_archive':True,'source':str(source),'destination':str(dest),
    'source_commit':run['source']['commit'],'copy_pins_match_first_manifest':True,
    'wall_seconds_before_receipt':time.perf_counter()-start_wall,
    'cpu_seconds_before_receipt':time.process_time()-start_cpu,
    'model_or_fit_or_physics_or_old_science':0}))
save('manifest.json',encoded({'stage':run['experiment_id']+'_first_archive','status':run['status'],
    'files_before_top_manifest':pins.copy(),'scientific_adoption':False,'continuous_goal_stays_active':True}))
print(json.dumps({'first_archive_complete':True,'stage':run['experiment_id'],'status':run['status'],
    'cost':run['cost'],'gate':metrics.get('fr3a_prediction_gate_passed') if args.stage=='prediction' else metrics.get('fr3b_model_contribution_gate_passed')}))
