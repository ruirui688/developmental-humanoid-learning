"""Extract saved absolute metrics from our derived cache; no new ratios/math."""
import hashlib
import json
from pathlib import Path


folder = Path(__file__).resolve().parent
data = (folder/'interpretation.json').read_bytes()
cached = json.loads(data.decode('utf-8'))
rows = [{key: metric[key] for key in ('seed', 'kind', 'original_status', 'original_completed', 'predictor', 'axis', 'h',
          'complete_window_count', 'mathematical_failure_count', 'available', 'reason', 'q', 'v')}
        for metric in cached['original_trial_metrics_all_axes_horizons']
        if metric['predictor'] in ('nominal9', 'sparse9', 'continuation9')
        and metric['kind'] in ('nominal_guard', 'PDselected') and metric['h'] in (1, 15)]
target = folder/'ORIGINAL9_ABSOLUTE_RMSE.json'
if target.exists():
    raise FileExistsError('never overwrite cached extraction')
record = {'scope': 'extract existing original9 nominal/PD H1/H15 absolute q/v prediction metrics; not actual tracking metrics',
          'derived_input': {'path': 'interpretation.json', 'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)},
          'source_D_file_reads': 0, 'new_scalar_algebra': 0, 'model_or_linear_algebra_calls': 0,
          'all_72_seed_trial_model_axis_h_records': rows}
target.write_text(json.dumps(record, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')
for row in rows:
    print(f"{row['seed']} {row['kind']} {row['predictor']} a{row['axis']} H{row['h']} q={row['q']['rmse']:.8g} v={row['v']['rmse']:.8g}")
