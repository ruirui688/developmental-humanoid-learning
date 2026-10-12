"""Archive the first IV2 synthetic check and source identities, without model math."""
from pathlib import Path
import hashlib,json,shutil,time,sys
root=Path(__file__).resolve().parents[1]
check_dir=root/'external/iv2_state_checks_first'
out=root/'results/cpu_validation/2026-10-12_consistent_action_state_preparation'
wall,cpu=time.perf_counter(),time.process_time()
out.mkdir(parents=True,exist_ok=False)
checks=json.loads((check_dir/'checks.json').read_text(encoding='utf-8'))
identities={}
source=['scripts/refit_instrumental_state.py','src/developmental_physics/consistent_action_state_model.py','docs/CONSISTENT_ACTION_STATE_PROTOCOL.md']
for rel in source:
 b=(root/rel).read_bytes();identities[rel]={'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
(out/'checks').mkdir()
for name in ['checks.json','first_stdout.log','first_stderr.log']:
 shutil.copyfile(check_dir/name,out/'checks'/name)
for src in [root/'external/new_iv_state_checks_once.py',Path(__file__).resolve()]:
 shutil.copyfile(src,out/'checks'/src.name)
manifest={'experiment':'IV2_preparation','status':checks['status'],'source':identities,
 'synthetic_check_count':len(checks['checks']),'first_failure':checks['first_failure'],
 'physical_calls':0,'real_fit_calls':0,'old_science_reexecution':False,
 'continuous_goal':'active','wall_seconds_before_manifest':time.perf_counter()-wall,
 'cpu_seconds_before_manifest':time.process_time()-cpu,
 'unmeasured_filesystem_IO':'unknown_not_zero'}
(out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'status':checks['status'],'checks':len(checks['checks']),'output':str(out)}))
if checks['status']!='passed' or len(checks['checks'])!=5:sys.exit(1)
