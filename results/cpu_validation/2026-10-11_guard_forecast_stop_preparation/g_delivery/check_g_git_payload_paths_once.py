"""Check Git path coverage only after the nested-ignore fix; no payload rehash."""
import json
from pathlib import Path
import subprocess
import time
root=Path(__file__).resolve().parents[1]
output=root/'external/c4_g_delivery_paths_01.json'
assert not output.exists()
wall,cpu=time.perf_counter(),time.process_time()
git_bytes=subprocess.check_output(['git','ls-files','-z'],cwd=root)
tracked=set(git_bytes.decode('utf-8').split('\0'))
checks=read_bytes=0
missing=[]
for name in ('2026-10-11_guard_pd_tail_preparation','2026-10-11_guard_pd_tail_control'):
    base='results/cpu_validation/'+name
    data=(root/base/'manifest.json').read_bytes();read_bytes+=len(data)
    manifest=json.loads(data)
    for member in manifest['files']:
        checks+=1
        if base+'/'+member not in tracked: missing.append(base+'/'+member)
result={'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),
    'git_payload_path_checks':checks,'failed':len(missing),'missing':missing,
    'manifest_opens':2,'manifest_binary_bytes':read_bytes,'git_path_return_bytes':len(git_bytes),
    'wall_seconds':time.perf_counter()-wall,'cpu_seconds':time.process_time()-cpu,
    'scope':'Git path membership only; no payload reads, hashes, copy replay, math, model, physics or old audit'}
output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
print(json.dumps(result,indent=2))
assert not missing
