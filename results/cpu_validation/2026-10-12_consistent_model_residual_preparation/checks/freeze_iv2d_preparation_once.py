"""Archive first IV2D check/source pins without executing saved-data math."""
from pathlib import Path
import hashlib,json,shutil,time
root=Path(__file__).resolve().parents[1]
check_dir=root/'external/iv2d_residual_checks_first'
out=root/'results/cpu_validation/2026-10-12_consistent_model_residual_preparation'
wall,cpu=time.perf_counter(),time.process_time()
out.mkdir(parents=True,exist_ok=False);(out/'checks').mkdir()
checks=json.loads((check_dir/'checks.json').read_bytes())
source={}
for rel in ['scripts/diagnose_consistent_model_residual.py','docs/CONSISTENT_MODEL_RESIDUAL_PROTOCOL.md']:
 b=(root/rel).read_bytes();source[rel]={'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
for name in ['checks.json','first_stdout.log','first_stderr.log']:
 shutil.copyfile(check_dir/name,out/'checks'/name)
for src in [root/'external/new_consistent_residual_checks_once.py',Path(__file__).resolve()]:
 shutil.copyfile(src,out/'checks'/src.name)
manifest={'experiment':'IV2D_preparation','status':checks['status'],'source':source,
 'synthetic_checks':len(checks['checks']),'first_failure':checks['first_failure'],
 'physical_calls':0,'real_fit_calls':0,'real_saved_data_math':0,'old_gate_reexecution':False,
 'continuous_goal':'active','wall_seconds_before_manifest':time.perf_counter()-wall,
 'cpu_seconds_before_manifest':time.process_time()-cpu,'unmeasured_filesystem_IO':'unknown_not_zero'}
(out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'status':checks['status'],'checks':len(checks['checks']),'output':str(out)}))
if checks['status']!='passed' or len(checks['checks'])!=1:raise SystemExit(1)
