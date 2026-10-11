"""Freeze the one new saved-value projection before opening FR3B raw."""
import ast
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
directory = root/'external/fr3d_candidate'
receipt = directory/'preparation_receipt.json'
assert not receipt.exists(), 'preparation exists; do not repeat'
source = (directory/'describe_fr3_control_tradeoff_once.py').read_bytes()
design = (root/'external/fr3_axis_phase_saved_diagnostic_design.md').read_bytes()
assert hashlib.sha256(design).hexdigest() == 'a14bf5c06d32e32559b856975255ef798f4ded0686251dc01539366edcda0d32'
ast.parse(source)
def identity(data):
    return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
(directory/'frozen_design.md').write_bytes(design)
value = {'stage': 'FR3D', 'candidate': identity(source), 'design': identity(design),
         'source_AST_passed': True, 'source_AST_parse_count': 1,
         'candidate_executions': 0, 'raw_reads': 0, 'physics_model_fit_RLS_calls': 0,
         'root_reviewed_static_design': True, 'caps': {'trace_rows': 36000, 'main_active_rows': 18000,
          'axis_scope_cells': 72, 'row_scope_projections': 19800, 'axis_scope_updates': 39600,
          'macros': 1200, 'macro_scope_projections': 1320, 'macro_axis_scope_projections': 2640,
          'nearest_grid_scalar_distances': 21600, 'pure_PD_candidate_records_read': 1200,
          'fixed_window_parent_ratios': 108, 'axis_sse_effort_difference_entries': 72},
         'scientific_gates_unchanged': True, 'new_control_automatically_selected': False}
receipt.write_text(json.dumps(value, indent=2)+'\n', encoding='utf-8')
print(json.dumps(value))
