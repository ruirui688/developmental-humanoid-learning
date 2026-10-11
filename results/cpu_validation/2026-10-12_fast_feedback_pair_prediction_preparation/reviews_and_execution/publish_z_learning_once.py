"""Publish stable external candidates once, preserving originals and LF identity."""
import ast
import hashlib
import json
from pathlib import Path
import time

repo = Path(__file__).resolve().parents[1]
origin = repo / 'external/z_learning_candidate'
status = json.loads((origin / 'implementation_status.json').read_bytes())
receipt = repo / 'external/c4_z_learning_publication.json'
if receipt.exists():
    raise FileExistsError(receipt)
started, cpu = time.perf_counter(), time.process_time()
records = {}
for name, pin in status['files'].items():
    path = origin / name
    original = path.read_bytes()
    assert len(original) == pin['bytes']
    assert hashlib.sha256(original).hexdigest() == pin['sha256']
    normalized = original.replace(b'\r\n', b'\n')
    assert ast.dump(ast.parse(original.decode('utf-8')), include_attributes=False) == ast.dump(ast.parse(normalized.decode('utf-8')), include_attributes=False)
    destination = repo / name
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open('xb') as stream:
        stream.write(normalized)
    records[name] = {'original': pin, 'published': {'bytes': len(normalized), 'sha256': hashlib.sha256(normalized).hexdigest()}, 'CRLF_to_LF_count': original.count(b'\r\n'), 'AST_equivalent': True}
record = {'status': 'published_before_first_checks', 'files': records, 'wall_seconds': time.perf_counter()-started, 'cpu_seconds': time.process_time()-cpu, 'production_imports': 0, 'tests': 0, 'model_fit_physics_calls': 0, 'external_originals_modified': False, 'automatic_retry': False}
with receipt.open('x', encoding='utf-8') as stream:
    json.dump(record, stream, indent=2)
print(json.dumps(record))
