"""Copy the first new EF1B artifacts without replacing files or rerunning work."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import time

repo = Path(__file__).resolve().parents[1]
source = repo / 'external/ef1b_control_first'
destination = repo / 'results/cpu_validation/2026-10-12_equilibrium_feedforward_control'
assert not destination.exists()
destination.mkdir(parents=True, exist_ok=False)
started = time.perf_counter()
files = {}
copied_bytes = 0
for subdir, output in [('raw', 'raw'), ('stdio', 'first_execution')]:
    for path in sorted((source / subdir).rglob('*')):
        if not path.is_file():
            continue
        name = (Path(output) / path.relative_to(source / subdir)).as_posix()
        target = destination / name
        data = path.read_bytes()
        assert len(data) < 100_000_000, name
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as stream:
            stream.write(data)
        copied = target.read_bytes()
        assert copied == data, name
        files[name] = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
        copied_bytes += len(data)
receipt = {
    'status': 'copied_without_overwrite', 'completed_utc': datetime.now(timezone.utc).isoformat(),
    'source': str(source), 'destination': str(destination), 'files': files,
    'source_read_bytes': copied_bytes, 'destination_written_bytes': copied_bytes,
    'destination_verification_read_bytes': copied_bytes,
    'raw_decoding': 0, 'new_physics': 0, 'new_model_calls': 0, 'fit': 0, 'RLS': 0,
    'wall_before_receipt_seconds': time.perf_counter() - started,
}
with (destination / 'delivery.json').open('xb') as stream:
    stream.write((json.dumps(receipt, ensure_ascii=False, indent=2) + '\n').encode())
print(json.dumps({'status': receipt['status'], 'payloads': len(files), 'bytes': copied_bytes}))
