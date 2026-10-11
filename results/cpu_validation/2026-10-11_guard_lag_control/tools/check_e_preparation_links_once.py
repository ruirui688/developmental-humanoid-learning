"""Only check current Markdown local link targets before the E source freeze."""
import json
from pathlib import Path
import re
from urllib.parse import unquote
root=Path(__file__).resolve().parents[1]
paths=['README.md','AGENTS.md','docs/PROGRESS.md','docs/CONTINUOUS_EXECUTION_PLAN.md','docs/GUARD_LAG_CONTROL_DEVELOPMENT_PROTOCOL.md']
checks=[]
for name in paths:
    p=root/name
    for match in re.finditer(r'!?\[[^\]]*\]\(([^\)]+)\)',p.read_text(encoding='utf-8')):
        target=match.group(1).strip().split(' "')[0].strip('<>')
        if target.startswith(('https:','http:','#','app:','codex:')):
            continue
        target=unquote(target.split('#',1)[0])
        checks.append({'source':name,'target':target,'exists':(p.parent/target).exists()})
report={'checks':len(checks),'failed':sum(not x['exists'] for x in checks),'missing':[x for x in checks if not x['exists']],
        'physics':0,'model_predictions':0,'updates':0}
with (root/'external/c4_e_freeze_links_01.json').open('x',encoding='utf-8') as f:
    json.dump(report,f,indent=2);f.write('\n')
print(json.dumps(report,indent=2))
raise SystemExit(int(report['failed']!=0))
