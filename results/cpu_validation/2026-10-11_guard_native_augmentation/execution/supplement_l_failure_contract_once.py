"""Correct only full-count applicability for the preserved source-failed run."""
import json
from pathlib import Path
import time

root = Path(__file__).resolve().parents[1]
report = root/'external/c4_l_failure_contract_supplement_01.json'
assert not report.exists()
started, cpu = time.perf_counter(), time.process_time()
original = json.loads((root/'external/c4_l_output_check_01.json').read_bytes())
prediction_bytes = (root/'external/c4_l_native_augmentation_01/predictions.jsonl').read_bytes()
failed = [r['name'] for r in original['checks'] if not r['passed']]
assert failed == ['all_fixed_prediction_records']
record = {'scope': 'only the first output-check assertion that required completed-run counts on a source-failed run',
          'original_check_retained': True, 'original_failures': failed,
          'full_count_assertion_applicable': False, 'empty_prediction_records_expected': True,
          'passed': prediction_bytes == b'', 'passed_original_checks_repeated': False,
          'fits': 0, 'model_calls': 0, 'physics': 0,
          'cost': {'binary_reads': 2, 'wall_seconds': time.perf_counter()-started, 'cpu_seconds': time.process_time()-cpu}}
report.write_text(json.dumps(record, indent=2)+'\n', encoding='utf-8')
print(json.dumps(record))
if not record['passed']:
    raise SystemExit(1)
