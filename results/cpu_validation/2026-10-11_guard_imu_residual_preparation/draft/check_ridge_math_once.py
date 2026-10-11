"""Two purely synthetic solves, run once; no actual trace or base model."""
from collections import Counter
import importlib.util
import json
from pathlib import Path
import time

import numpy as np

stage = Path(__file__).resolve().parent
destination = stage / "CHECK_RIDGE_01.json"
if destination.exists():
    raise FileExistsError("first synthetic ridge check already exists; do not rerun")
spec = importlib.util.spec_from_file_location("j_synthetic_ridge", stage / "develop_guard_imu_residual.py")
j = importlib.util.module_from_spec(spec)
spec.loader.exec_module(j)
cost = Counter()
wall, cpu = time.perf_counter(), time.process_time()
design = np.zeros((400, 6), dtype=np.float64)
design[:6] = np.eye(6)
labels = np.zeros((400, 2), dtype=np.float64)
known_rhs = np.arange(1., 13.).reshape(6, 2)
labels[:6] = known_rhs
identity_weights, _ = j.fit_residual(design, labels, cost)
np.testing.assert_allclose(identity_weights, known_rhs/(1.+j.RIDGE), rtol=1e-14, atol=1e-14)
zero_weights, _ = j.fit_residual(np.zeros((400, 6)), np.ones((400, 2)), cost)
np.testing.assert_array_equal(zero_weights, np.zeros((6, 2)))
record = {"status": "passed", "first_invocations": 1, "reruns": 0,
          "scope": "two synthetic ridge solves only; actual trace/base model/formal fit/physics zero",
          "checks": ["identity design W=known_rhs/(1+.01)", "zero feature matrix yields zero head"],
          "cost": dict(cost), "wall_seconds": time.perf_counter()-wall,
          "cpu_seconds": time.process_time()-cpu,
          "formal_J_executions": 0, "actual_trace_reads": 0, "base_model_calls": 0,
          "physics_calls": 0, "runtime": {"numpy": np.__version__}}
destination.write_text(json.dumps(record, indent=2, allow_nan=False)+"\n", encoding="utf-8")
print(json.dumps(record, indent=2, allow_nan=False))
