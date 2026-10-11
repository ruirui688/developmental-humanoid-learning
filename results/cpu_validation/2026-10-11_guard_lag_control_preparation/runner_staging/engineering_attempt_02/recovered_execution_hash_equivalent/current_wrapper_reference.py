"""Archive one small engineering attempt, including any original failure."""
from contextlib import redirect_stdout, redirect_stderr
from io import StringIO
import hashlib
import json
from pathlib import Path
import runpy
import sys
import time
import traceback

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root/"src"))
staging = Path(__file__).resolve().parent
output = staging/"engineering_attempt_02"
output.mkdir(exist_ok=False)
captured = StringIO()
wall, cpu = time.perf_counter(), time.process_time()
error = None
with redirect_stdout(captured), redirect_stderr(captured):
    try:
        runpy.run_path(str(staging/"check_guard_lag_control_small.py"), run_name="__main__")
    except BaseException:
        error = traceback.format_exc()
        captured.write(error)
text = captured.getvalue()
(output/"output.txt").write_text(text, encoding="utf-8")
record = {"status": "failed" if error else "completed", "wall_seconds": time.perf_counter()-wall,
          "cpu_seconds": time.process_time()-cpu, "error": error,
          "source_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in
                            (staging/"guard_lag_control_development.py", staging/"check_guard_lag_control_small.py")},
          "output_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()}
(output/"execution.json").write_text(json.dumps(record, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
print(text)
print(json.dumps(record, ensure_ascii=False))
if error:
    raise SystemExit(1)
