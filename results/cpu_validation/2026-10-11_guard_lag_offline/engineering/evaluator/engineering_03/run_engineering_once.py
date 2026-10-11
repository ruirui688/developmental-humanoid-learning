"""Retain one numbered attempt of the small handwritten engineering suite."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import time
import unittest


root = Path(__file__).resolve().parent
index = 1
while (root/f"engineering_{index:02d}").exists():
    index += 1
output = root/f"engineering_{index:02d}"
output.mkdir()
files = ("guard_lag_offline_development.py", "test_guard_lag_offline_development.py", "run_engineering_once.py")
sources = {}
for name in files:
    path = root/name
    shutil.copyfile(path, output/name)
    sources[name] = hashlib.sha256(path.read_bytes()).hexdigest()
(output/"before.json").write_text(json.dumps({"source_sha256": sources, "real_C_reads": 0, "real_model_predictions": 0,
    "real_model_fits": 0, "physical_calls": 0, "git_calls": 0}, indent=2)+"\n", encoding="utf-8")
spec = importlib.util.spec_from_file_location("engineering_tests", root/files[1])
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
started_wall, started_cpu = time.perf_counter(), time.process_time()
with (output/"stdout.txt").open("w", encoding="utf-8") as stream:
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(module))
record = {"source_sha256": sources, "tests": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
    "wall_seconds": time.perf_counter()-started_wall, "cpu_seconds": time.process_time()-started_cpu,
    "timing_scope": "test body; excludes import/startup and final writing", "artificial_handmodel_and_diagnostic_cost": dict(module.ARTIFICIAL_COST),
    "real_C_reads": 0, "real_model_predictions": 0, "real_model_fits": 0, "physical_calls": 0, "git_calls": 0,
    "failures_retained": True}
(output/"result.json").write_text(json.dumps(record, indent=2)+"\n", encoding="utf-8")
print(json.dumps({"output": str(output), **record}, indent=2))
raise SystemExit(0 if result.wasSuccessful() else 1)
