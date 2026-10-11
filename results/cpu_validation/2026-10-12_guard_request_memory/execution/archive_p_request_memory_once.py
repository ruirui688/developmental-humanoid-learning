"""Archive one P invocation without repeating model or test calculations."""
import argparse
import hashlib
import json
from pathlib import Path
import time

parser = argparse.ArgumentParser()
parser.add_argument("--preparation", action="store_true")
args = parser.parse_args()
repo = Path(__file__).resolve().parents[1]
label = "c4_p_selfcheck_01" if args.preparation else "c4_p_request_memory_01"
stem = "2026-10-12_guard_request_memory" + ("_preparation" if args.preparation else "")
first, target = repo/"external"/label, repo/"results/cpu_validation"/stem
if not first.is_dir() or target.exists():
    raise SystemExit("missing first output or archive exists; no automatic repeat")
wall, cpu = time.perf_counter(), time.process_time()
target.mkdir()
sources = [(p, p.relative_to(first)) for p in sorted(first.rglob("*")) if p.is_file()]
for name in ("run_p_request_memory_once.py", "archive_p_request_memory_once.py"):
    sources.append((repo/"external"/name, Path("execution")/name))
if args.preparation:
    for name in ("c4_p_preparation_reads.json", "c4_p_implementation_review.md", "c4_after_o_direction.md"):
        sources.append((repo/"external"/name, Path("preparation")/name))
files, reads, byte_count, failures = {}, 0, 0, []
for source, name in sources:
    data = source.read_bytes()
    reads += 1
    byte_count += len(data)
    dest = target/name
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    copied = dest.read_bytes()
    reads += 1
    byte_count += len(copied)
    files[name.as_posix()] = {"bytes":len(data), "sha256":hashlib.sha256(data).hexdigest(),
                              "original_path":source.relative_to(repo).as_posix()}
    if data != copied:
        failures.append(name.as_posix())
record = {"payload_count":len(files), "files":files, "file_reads":reads,
          "read_bytes":byte_count, "copy_failures":failures,
          "wall_seconds":time.perf_counter()-wall, "cpu_seconds":time.process_time()-cpu,
          "no_scientific_recalculation":True, "automatic_retry":False}
(target/"manifest.json").write_text(json.dumps(record, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
print(json.dumps({k:v for k,v in record.items() if k != "files"}))
raise SystemExit(bool(failures))
