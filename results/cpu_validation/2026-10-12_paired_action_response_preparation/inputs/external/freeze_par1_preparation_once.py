"""Copy the completed PAR1 preparation once; no physics or check execution."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import time

repo = Path(__file__).resolve().parents[1]
base = repo / 'results/cpu_validation/2026-10-12_paired_action_response_preparation'
assert not base.exists(), 'first preparation destination must be absent'
wall, cpu = time.perf_counter(), time.process_time()
cost = {'read_files': 0, 'read_bytes': 0, 'write_files': 0, 'write_bytes': 0}
files = {}

def identity(data):
    return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}

def read(path):
    data = path.read_bytes()
    cost['read_files'] += 1
    cost['read_bytes'] += len(data)
    return data

def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(data)
    cost['write_files'] += 1
    cost['write_bytes'] += len(data)
    files[path.relative_to(base).as_posix()] = identity(data)

inputs = [
    'docs/PAIRED_ACTION_RESPONSE_DIAGNOSTIC_PROTOCOL.md',
    'scripts/diagnose_paired_action_response.py',
    'external/new_paired_action_response_checks_once.py',
    'external/freeze_par1_preparation_once.py',
]
buffers = {name: read(repo / name) for name in inputs}
check_dir = repo / 'external/par1_new_checks_first'
for path in sorted(check_dir.iterdir()):
    if path.is_file():
        buffers[path.relative_to(repo).as_posix()] = read(path)
checks = json.loads(buffers['external/par1_new_checks_first/checks.json'])
assert checks['status'] == 'passed' and checks.get('first_failure') is None
assert checks['checks'] and all(row['passed'] for row in checks['checks'])
for name in ['scripts/diagnose_paired_action_response.py',
             'external/new_paired_action_response_checks_once.py']:
    matches = [value for path, value in checks['source_identities'].items()
               if Path(path).resolve() == (repo / name).resolve()]
    assert matches == [identity(buffers[name])], 'first checks must bind final source'
base.mkdir(parents=True, exist_ok=False)
for name, data in buffers.items():
    write(base / 'inputs' / name, data)

for name, rules in {
    '.gitignore': '\n!results/cpu_validation/2026-10-12_paired_action_response_preparation/\n!results/cpu_validation/2026-10-12_paired_action_response_preparation/**/external/\n!results/cpu_validation/2026-10-12_paired_action_response_preparation/**/external/**\n!results/cpu_validation/2026-10-12_paired_action_response/\n',
    '.gitattributes': '\nresults/cpu_validation/2026-10-12_paired_action_response_preparation/** -text whitespace=cr-at-eol,-blank-at-eof\nresults/cpu_validation/2026-10-12_paired_action_response/** -text whitespace=cr-at-eol,-blank-at-eof\nscripts/diagnose_paired_action_response.py text eol=lf\ndocs/PAIRED_ACTION_RESPONSE_DIAGNOSTIC_PROTOCOL.md text eol=lf\ndocs/PAIRED_ACTION_RESPONSE_DIAGNOSTIC_RESULTS.md text eol=lf\n',
}.items():
    path = repo / name
    before = read(path)
    assert 'paired_action_response_preparation' not in before.decode('utf-8')
    after = before + rules.encode('utf-8')
    path.write_bytes(after)
    cost['write_files'] += 1
    cost['write_bytes'] += len(after)

for name in ['AGENTS.md', 'README.md', 'docs/CONTINUOUS_EXECUTION_PLAN.md',
             'docs/CPU_VALIDATION_TARGET.md', 'docs/DEVELOPMENT_ROADMAP.md']:
    path = repo / name
    before = read(path)
    text = before.decode('utf-8')
    prefix = '' if name.startswith('docs/') else 'docs/'
    entry = ('\n\n## PAR1 冻结准备与当前入口（2026-10-12）\n\n'
             '当前继续 [相同仿真状态的有限动作响应诊断](' + prefix +
             'PAIRED_ACTION_RESPONSE_DIAGNOSTIC_PROTOCOL.md)：三开发 seed、12 origin、48计划侧，'
             '上限9,060控制/子步、0更新。首次必要合成检查passed，仅代表准备资格；正式物理尚未执行。'
             '完整状态复制仅供仿真评估，模型仍只使用原生信息。\n\n'
             '此前505,297控制/2,784,970子步、125,652scalar更新；C4–C7未验收，原门不变，'
             '持续目标active。冻结检查提交推送后立即继续首次实验。\n')
    assert '## PAR1 冻结准备与当前入口' not in text
    first, rest = text.split('\n', 1)
    after = (first.rstrip('\r') + entry + '\n' + rest).encode('utf-8')
    path.write_bytes(after)
    cost['write_files'] += 1
    cost['write_bytes'] += len(after)

manifest = {'experiment': 'PAR1', 'status': 'preparation_frozen',
    'created_utc': datetime.now(timezone.utc).isoformat(), 'files': files,
    'new_check_cost': checks.get('synthetic_only_cost'),
    'historical': {'controls': 505297, 'substeps': 2784970, 'scalar_updates': 125652},
    'preparation_physics': 0, 'preparation_fit': 0, 'checks_reexecuted': False,
    'readonly_runtime_API_query': {'mujoco_version': '3.15.0', 'mj_copyData_available': True,
        'mj_getState_available': True, 'integration_state_mask': 16383,
        'model_or_data_constructions': 0, 'physics_calls': 0,
        'query_import_and_internal_IO': 'unmeasured_unknown_not_zero'},
    'review': 'Root and checkpoint performed one source-only review; no raw review or execution.',
    'IO_before_manifest': dict(cost), 'wall_seconds_before_manifest': time.perf_counter()-wall,
    'cpu_seconds_before_manifest': time.process_time()-cpu,
    'unmeasured_internal_filesystem_IO': 'unknown_not_zero', 'continuous_goal': 'active'}
write(base / 'manifest.json', (json.dumps(manifest, ensure_ascii=False, indent=2)+'\n').encode())
print(json.dumps({'status': 'preparation_frozen', 'files': len(files), 'cost': cost}))
