"""Archive one V invocation; copy originals without scientific recomputation."""
import argparse
import hashlib
import json
from pathlib import Path
import time

parser=argparse.ArgumentParser()
parser.add_argument('--preparation',action='store_true')
args=parser.parse_args()
repo=Path(__file__).resolve().parents[1]
label='c4_v_selfcheck_01' if args.preparation else 'c4_v_oracle_tail_01'
stem='2026-10-12_guard_oracle_tail'+('_preparation' if args.preparation else '')
first,target=repo/'external'/label,repo/'results/cpu_validation'/stem
if not first.is_dir() or target.exists():
    raise SystemExit('missing first output or archive exists; no repeat')
wall,cpu=time.perf_counter(),time.process_time()
target.mkdir()
sources=[(p,p.relative_to(first)) for p in sorted(first.rglob('*')) if p.is_file()]
for name in ('run_v_oracle_once.py','archive_v_oracle_once.py'):
    sources.append((repo/'external'/name,Path('execution')/name))
if args.preparation:
    for name in ('c4_v_preparation_reads.json','c4_v_implementation_review.md','c4_v_U_metadata_bindings.json','c4_v_U_input_bindings.json','c4_v_public_guard_bindings.json','c4_v_U_metrics_binding.json'):
        sources.append((repo/'external'/name,Path('preparation')/name))
files={}; reads=byte_count=0; failures=[]
for source,name in sources:
    data=source.read_bytes(); reads+=1; byte_count+=len(data)
    dest=target/name; dest.parent.mkdir(parents=True,exist_ok=True); dest.write_bytes(data)
    check=dest.read_bytes(); reads+=1; byte_count+=len(check)
    files[name.as_posix()]={'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),
      'original_path':source.relative_to(repo).as_posix()}
    if check!=data:
        failures.append(name.as_posix())
record={'payload_count':len(files),'files':files,'file_reads':reads,'read_bytes':byte_count,
  'copy_failures':failures,'wall_seconds':time.perf_counter()-wall,'cpu_seconds':time.process_time()-cpu,
  'no_scientific_recalculation':True,'automatic_retry':False}
(target/'manifest.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:v for k,v in record.items() if k!='files'}))
raise SystemExit(bool(failures))
