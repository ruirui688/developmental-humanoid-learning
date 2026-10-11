"""Copy the first O output without recomputing its diagnostic."""
import hashlib
import json
from pathlib import Path
import shutil
import time

repo = Path(__file__).resolve().parents[1]
first = repo / "external/c4_o_saved_recursion_01"
target = repo / "results/cpu_validation/2026-10-11_guard_saved_recursion"
if not first.is_dir() or target.exists():
    raise SystemExit("missing first output or archive exists; no automatic retry")
start_wall, start_cpu = time.perf_counter(), time.process_time()
target.mkdir()
files, reads, byte_count = {}, 0, 0
copy_failures = []

def copy(source, relative):
    global reads, byte_count
    data = source.read_bytes()
    reads += 1
    byte_count += len(data)
    dest = target / relative
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, dest)
    copied = dest.read_bytes()
    reads += 1
    byte_count += len(copied)
    files[relative.as_posix()] = {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
                                 "original_path": source.relative_to(repo).as_posix()}
    if data != copied:
        copy_failures.append(relative.as_posix())

for source in sorted(first.rglob("*")):
    if source.is_file():
        copy(source, source.relative_to(first))
copy(repo / "external/run_o_saved_recursion_once.py", Path("execution/run_o_saved_recursion_once.py"))
copy(Path(__file__), Path("execution/archive_o_saved_recursion_once.py"))
record = {"files": files, "payload_count": len(files), "file_reads": reads,
          "read_bytes": byte_count, "copy_failures": copy_failures,
          "wall_seconds": time.perf_counter() - start_wall,
          "cpu_seconds": time.process_time() - start_cpu,
          "no_scientific_recalculation": True, "automatic_retry": False}
(target / "manifest.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({k: v for k, v in record.items() if k != "files"}))
raise SystemExit(bool(copy_failures))
