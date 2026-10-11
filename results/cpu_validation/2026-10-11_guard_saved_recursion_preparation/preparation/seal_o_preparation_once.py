"""Seal existing O preparation without repeating any mathematics."""
import hashlib
import json
from pathlib import Path
import time

repo = Path(__file__).resolve().parents[1]
target = repo / "results/cpu_validation/2026-10-11_guard_saved_recursion_preparation"
if target.exists():
    raise SystemExit("preparation already sealed; preserve it")
wall, cpu = time.perf_counter(), time.process_time()
target.mkdir()
sources = [(p, p.relative_to(repo/"external/c4_o_selfcheck_01"))
           for p in sorted((repo/"external/c4_o_selfcheck_01").rglob("*")) if p.is_file()]
for name in ("c4_o_preparation_reads.json", "c4_o_implementation_review.md",
             "c4_n_interpretation_direction.md", "c4_after_n_direction.md",
             "run_o_selfcheck_once.py", "seal_o_preparation_once.py"):
    sources.append((repo/"external"/name, Path("preparation")/name))
files, reads, byte_count, failures = {}, 0, 0, []
for source, name in sources:
    raw = source.read_bytes()
    reads += 1
    byte_count += len(raw)
    dest = target/name
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(raw)
    copied = dest.read_bytes()
    reads += 1
    byte_count += len(copied)
    files[name.as_posix()] = {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
                              "original_path": source.relative_to(repo).as_posix()}
    if raw != copied:
        failures.append(name.as_posix())
record = {"payload_count": len(files), "files": files, "file_reads": reads,
          "read_bytes": byte_count, "copy_failures": failures,
          "wall_seconds": time.perf_counter()-wall, "cpu_seconds": time.process_time()-cpu,
          "no_scientific_recalculation": True, "automatic_retry": False}
(target/"manifest.json").write_text(json.dumps(record, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
print(json.dumps({k:v for k,v in record.items() if k != "files"}))
raise SystemExit(bool(failures))
