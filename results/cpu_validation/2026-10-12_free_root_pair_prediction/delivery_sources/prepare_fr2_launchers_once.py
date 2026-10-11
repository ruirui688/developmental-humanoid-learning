"""Stdlib launch/archive wiring only; the FR2 controller was already frozen."""
from pathlib import Path
import ast
import hashlib
import json

root = Path(__file__).resolve().parents[1]
pins = {}
for src, dst in [('run_fr1_first_once.py', 'run_fr2_first_once.py'),
                 ('archive_fr1_first_once.py', 'archive_fr2_first_once.py')]:
    before = (root/'external'/src).read_bytes()
    text = before.decode().replace('FR1', 'FR2').replace('fr1', 'fr2')
    text = text.replace("'--stage', 'prediction'", "'--stage', 'control'")
    text = text.replace('2026-10-12_free_root_pair_prediction', '2026-10-12_free_root_pair_control')
    text = text.replace('fr2_prediction_gate_passed', 'fr2_model_contribution_gate_passed')
    ast.parse(text)
    path = root/'external'/dst
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(text)
    after = path.read_bytes()
    pins[dst] = {'source': src, 'source_sha256': hashlib.sha256(before).hexdigest(),
                 'bytes': len(after), 'sha256': hashlib.sha256(after).hexdigest()}
with (root/'external/fr2_launcher_preparation.json').open('x', encoding='utf-8') as stream:
    json.dump({'files': pins, 'new_models_physics_or_fit': 0,
               'FR2_mathematics_and_source_dependencies_changed': False}, stream, indent=2)
    stream.write('\n')
print(json.dumps(pins))
