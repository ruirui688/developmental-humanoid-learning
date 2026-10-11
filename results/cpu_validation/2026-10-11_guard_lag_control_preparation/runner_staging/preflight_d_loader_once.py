"""One explicitly authorized read-only D interface check, never a fit/predict."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time
import traceback

staging = Path(__file__).resolve().parent
root = staging.parents[1]
sys.path.insert(0, str(root/"src"))
output = staging/"preflight_d_loader_01"
output.mkdir(exist_ok=False)
source = (staging/"guard_lag_control_development.py").read_bytes()
(output/"loader_source.py").write_bytes(source)
started_wall, started_cpu = time.perf_counter(), time.process_time()
record = {"status": "started", "source_sha256": hashlib.sha256(source).hexdigest(),
          "real_physics_calls": 0, "model_predictions": 0, "model_updates": 0,
          "MPC_select_calls": 0, "Git_calls": 0, "old_audit_reexecutions": 0}
error = None
try:
    spec = importlib.util.spec_from_file_location("e_loader_preflight", staging/"guard_lag_control_development.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.FORMAL_CONTROL_ENABLED is False
    models, snapshots, binding, blobs = module.load_d_models(root)
    record.update(status="completed", D_binding=binding, pinned_file_reads=len(blobs),
                  pinned_file_bytes_read=sum(len(x) for x in blobs.values()),
                  restored_models=3, independent_cold_initializations=3,
                  per_trial_clones=0, initialization_compute="nonzero object/array construction and snapshot/hash comparisons",
                  model_identities={str(seed): {name: {"frozen": not model.trainable,
                      "qref_rad": list(model.qref), "vector_update_count_loaded": model.update_count,
                      "fingerprint": snapshots[seed][name]["parameter_fingerprint"]}
                      for name, model in group.items()} for seed, group in models.items()})
except BaseException:
    error = traceback.format_exc()
    record.update(status="failed", error=error)
finally:
    record.update(wall_seconds=time.perf_counter()-started_wall, cpu_seconds=time.process_time()-started_cpu)
    (output/"execution.json").write_text(json.dumps(record, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
print(json.dumps(record, ensure_ascii=False, indent=2))
if error:
    raise SystemExit(1)
