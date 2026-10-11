"""Preserve first check bytes and remove only one production trailing blank line."""
import ast
import hashlib
import json
from pathlib import Path
import time
root=Path(__file__).resolve().parents[1]
output=root/'external/c4_v_terminal_normalization_01.json'
if output.exists():
    raise SystemExit('first normalization receipt exists')
wall,cpu=time.perf_counter(),time.process_time()
records=[]
for name in ('scripts/diagnose_guard_oracle_tail.py','docs/GUARD_ORACLE_TAIL_DIAGNOSTIC_PROTOCOL.md'):
    path=root/name
    before=path.read_bytes()
    if not before.endswith(b'\n\n') or before.endswith(b'\n\n\n'):
        raise ValueError('expected exactly one extra terminal blank line')
    after=before[:-1]
    record={'path':name,'before_bytes':len(before),'before_sha256':hashlib.sha256(before).hexdigest(),
            'after_bytes':len(after),'after_sha256':hashlib.sha256(after).hexdigest()}
    if name.endswith('.py'):
        old_tree=ast.parse(before.decode('utf-8'))
        new_tree=ast.parse(after.decode('utf-8'))
        assert ast.dump(old_tree)==ast.dump(new_tree)
        compile(new_tree,name,'exec')
        record.update(ast_equivalent=True,compile_only_passed=True,module_execution=False)
    path.write_bytes(after)
    records.append(record)
result={'files':records,'reads':2,'read_bytes':sum(x['before_bytes'] for x in records),
        'wall_seconds':time.perf_counter()-wall,'cpu_seconds':time.process_time()-cpu,
        'first_cached_diff_failure':'six terminal blank line findings; subsequent git diff stat masked shell exit',
        'original_checked_and_archived_bytes_unchanged':True,'scientific_execution':False,
        'passed_fixture_rerun':False}
output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
print(json.dumps(result))
