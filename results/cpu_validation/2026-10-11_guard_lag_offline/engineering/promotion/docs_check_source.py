"""Read-only local link check for the five changed D handoff documents."""
import json
from pathlib import Path
import re

root=Path(__file__).resolve().parents[1]
names=('AGENTS.md','README.md','docs/PROGRESS.md','docs/CONTINUOUS_EXECUTION_PLAN.md','docs/GUARD_LAG_OFFLINE_DEVELOPMENT_PROTOCOL.md')
count=0;missing=[]
for name in names:
    path=root/name
    for match in re.finditer(r'!?\[[^\]]*\]\(([^)]+)\)',path.read_text(encoding='utf-8')):
        destination=match.group(1).strip().strip('<>')
        if destination.startswith(('http:','https:','app:','codex:','mailto:','#')):
            continue
        destination=destination.split('#',1)[0]
        if not destination:
            continue
        count+=1
        if not (path.parent/destination).exists():
            missing.append({'document':name,'target':destination})
result={'local_links_checked':count,'missing':missing,'model_calls':0,'physics_calls':0}
output=root/'external/guard_lag_offline_promotion_01/docs_check.json'
with output.open('x',encoding='utf-8',newline='\n') as stream:
    json.dump(result,stream,ensure_ascii=False,indent=2);stream.write('\n')
(output.parent/'docs_check_source.py').write_bytes(Path(__file__).read_bytes())
print(json.dumps(result,ensure_ascii=False))
raise SystemExit(bool(missing))
