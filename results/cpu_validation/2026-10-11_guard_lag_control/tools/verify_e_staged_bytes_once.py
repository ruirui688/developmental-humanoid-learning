"""One cached Git-byte check before freezing E; never runs test/model math."""
import hashlib
import json
from pathlib import Path
import subprocess
root=Path(__file__).resolve().parents[1]
base='results/cpu_validation/2026-10-11_guard_lag_control_preparation'
manifest=json.loads((root/base/'manifest.json').read_bytes())
records={base+'/'+name:r for name,r in manifest['files'].items()}
for name in (base+'/manifest.json','src/developmental_physics/guard_lag_control_development.py','src/developmental_physics/guard_lag_pair_mpc.py','scripts/audit_guard_lag_control.py','docs/GUARD_LAG_CONTROL_DEVELOPMENT_PROTOCOL.md'):
    data=(root/name).read_bytes();records[name]={'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)}
checks=[]
for name,r in records.items():
    data=subprocess.check_output(['git','show',':'+name],cwd=root)
    checks.append({'path':name,'equal':len(data)==r['bytes'] and hashlib.sha256(data).hexdigest()==r['sha256']})
report={'checks':len(checks),'failed':sum(not c['equal'] for c in checks),'failures':[c for c in checks if not c['equal']],
        'git_blob_reads':len(checks),'model_predictions':0,'updates':0,'physics':0}
with (root/'external/c4_e_staged_bytes_01.json').open('x',encoding='utf-8') as f:
    json.dump(report,f,indent=2);f.write('\n')
print(json.dumps(report,indent=2))
raise SystemExit(int(report['failed']!=0))
