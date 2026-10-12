"""Finish only the IV3 checks not reached after the first tuple fixture error."""
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
import hashlib
import importlib.util
import json
import sys
import traceback
import numpy as np

root = Path(__file__).resolve().parents[1]
output = root / 'external/iv3_remainder_preparation'
output.mkdir(exist_ok=False)
runner = root / 'scripts/run_near_reference_identification.py'
blob = runner.read_bytes()
result = {'status': 'not_started', 'first_failure': None, 'checks': [],
          'runner': {'bytes': len(blob), 'sha256': hashlib.sha256(blob).hexdigest()},
          'new_command_calls': 0, 'new_template_calls': 0, 'previous_four_command_calls_reexecuted': 0,
          'physics_calls': 0, 'fit_calls': 0, 'model_predict_calls': 0, 'saved_raw_reads': 0,
          'RLS_updates': 0, 'unmeasured_import_IO': 'unknown_not_zero'}
with (output/'first_stdout.log').open('x', encoding='utf-8') as stdout, (output/'first_stderr.log').open('x', encoding='utf-8') as stderr:
    with redirect_stdout(stdout), redirect_stderr(stderr):
        try:
            assert result['runner']['sha256'] == '203d799e40516506dc7239ce2be2024d3a54ee315ee758870229d9884e640cf0'
            spec = importlib.util.spec_from_file_location('iv3_remainder', runner)
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
            qref = np.asarray((.13, -.07))
            command = module.near_reference_request(qref, np.zeros(2), qref, (1, 0))
            result['new_command_calls'] += 1
            assert command['current_target_q2'].tobytes() == qref.tobytes()
            assert np.array_equal(command['known_base2'], (0., 0.))
            assert np.array_equal(command['request2'], (.125, -.125))
            result['checks'].append({'name': 'zero_velocity_numpy_fixture_at_fixed_qref', 'passed': True, 'command': module.safe(command)})
            poison = {'model': 'oldlearned', 'actual_endpoint_q2': 'must_not_be_read', 'actual_endpoint_v2': 'must_not_be_read'}
            result['new_template_calls'] += 1
            assert module.saved_cold_template(poison) is None
            cold = {'seed': 8101, 'model': 'cold', 'horizon': 10, 'origin_active_index': 0,
                    'status': 'completed', 'available': True, 'model_fingerprint': 'synthetic_cold',
                    'model_input': {'q2': [.13, -.07], 'v2': [.1, -.2], 'known_requests2': [[.125, -.125]]*10},
                    'actual_endpoint_q2': [.14, -.08], 'actual_endpoint_v2': [.2, -.3]}
            result['new_template_calls'] += 1
            template = module.saved_cold_template(cold)
            assert template['known_requests2'].shape == (10, 2)
            assert np.array_equal(template['q2'], qref)
            assert np.array_equal(template['actual_endpoint_v2'], (.2, -.3))
            result['new_template_calls'] += 1
            rejected = False
            try:
                module.saved_cold_template({**cold, 'available': False})
            except ValueError:
                rejected = True
            assert rejected
            result['checks'].append({'name': 'cold_only_complete_saved_template_selection', 'passed': True, 'template': module.safe(template)})
            result['status'] = 'passed'
        except BaseException as exc:
            result['status'] = 'failed'
            result['first_failure'] = {'type': type(exc).__name__, 'message': str(exc), 'traceback': traceback.format_exc()}
            traceback.print_exc()
(output/'checks.json').write_text(json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2)+'\n', encoding='utf-8', newline='\n')
print(json.dumps({'status': result['status'], 'checks': len(result['checks'])}))
raise SystemExit(0 if result['status'] == 'passed' else 1)
