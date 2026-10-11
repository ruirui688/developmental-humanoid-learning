"""One scientific G completion figure from the saved report projection only."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import sys
import time

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Patch


def main():
    out = Path(__file__).resolve().parent
    source_root = out.parents[1]
    input_path = source_root/'external/c4_g_report_projection_01.json'
    figure_path = out/'g_active_steps_by_method_seed.png'
    execution_path = out/'run.json'
    if figure_path.exists() or execution_path.exists():
        raise FileExistsError('preserve the once-only G figure and execution record')
    wall, cpu = time.perf_counter(), time.process_time()
    input_bytes = input_path.read_bytes()
    source_bytes = Path(__file__).read_bytes()
    data = json.loads(input_bytes)
    rows = {(row['kind'], row['seed']): row for row in data['rows']}
    methods = [('cold11', 'Cold11 + PD tail'),
               ('learned_sparse11', 'Learned sparse11 + PD tail'),
               ('PDselected', 'Selected PD'), ('zero', 'Zero torque')]
    seeds = (0, 1, 2)
    complete_color, stop_color, remaining_color = '#19756d', '#c13b38', '#e8edf2'
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10,
                         'axes.spines.top': False, 'axes.spines.right': False})
    fig, axes = plt.subplots(1, 4, figsize=(13.3, 4.1), sharex=True, sharey=True)
    for axis, (method, title) in zip(axes, methods):
        axis.barh(seeds, [200, 200, 200], height=.54, color=remaining_color, zorder=1)
        for seed in seeds:
            row = rows[(method, seed)]
            active = row['active_steps']
            complete = row['status'] == 'completed'
            color = complete_color if complete else stop_color
            axis.barh(seed, active, height=.54, color=color, zorder=2)
            if active == 200:
                axis.text(194, seed, f'{active}/200', ha='right', va='center',
                          color='white', fontsize=10, fontweight='bold')
            else:
                axis.text(active+4, seed, f'{active}/200', ha='left', va='center',
                          color=stop_color, fontsize=10, fontweight='bold')
        axis.set_title(title, fontsize=11, fontweight='bold', pad=13)
        axis.set_xlim(0, 225)
        axis.set_xticks([0, 100, 200])
        axis.set_yticks(seeds, [f'Seed {seed}' for seed in seeds])
        axis.grid(axis='x', color='#d9e0e6', linewidth=.65, zorder=0)
        axis.set_axisbelow(True)
        axis.spines['left'].set_visible(False)
        axis.spines['bottom'].set_color('#adb8c4')
        axis.tick_params(axis='both', length=0, pad=6)
    axes[0].invert_yaxis()
    fig.suptitle('G development: active control steps executed', fontsize=15,
                 fontweight='bold', x=.055, ha='left', y=.96)
    fig.legend(handles=[Patch(facecolor=complete_color, label='Complete trial'),
                        Patch(facecolor=stop_color, label='Research stop'),
                        Patch(facecolor=remaining_color, label='Unexecuted planned steps')],
               loc='upper left', bbox_to_anchor=(.05, .90), ncol=3, frameon=False,
               columnspacing=2.2, handlelength=1.3)
    fig.supxlabel('Active control steps (planned: 200 per trial)', y=.215, fontsize=11)
    fig.text(.055, .12, 'Stopped bars indicate failure, not interaction efficiency. G is development only.',
             fontsize=10, color='#343e4b')
    fig.text(.055, .055, f'Saved projection only | source commit {data["source_commit"][:12]}',
             fontsize=8, color='#697482')
    fig.subplots_adjust(left=.085, right=.98, top=.70, bottom=.30, wspace=.27)
    fig.savefig(figure_path, dpi=190, facecolor='white')
    plt.close(fig)
    figure_bytes = figure_path.read_bytes()
    record = {'schema_version': 1, 'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'input': {'path': input_path.relative_to(source_root).as_posix(),
                  'sha256': hashlib.sha256(input_bytes).hexdigest(), 'bytes': len(input_bytes)},
        'plot_source': {'path': Path(__file__).relative_to(source_root).as_posix(),
                        'sha256': hashlib.sha256(source_bytes).hexdigest(), 'bytes': len(source_bytes)},
        'figure': {'path': figure_path.relative_to(source_root).as_posix(),
                   'sha256': hashlib.sha256(figure_bytes).hexdigest(), 'bytes': len(figure_bytes),
                   'dpi': 190, 'figsize_inches': [13.3, 4.1]},
        'source_commit': data['source_commit'], 'summary_sha256': data['summary_sha256'],
        'numeric_fields_used': ['rows.kind', 'rows.seed', 'rows.status', 'rows.active_steps'],
        'displayed_methods': [method for method, title in methods], 'displayed_seeds': list(seeds),
        'planned_active_steps_per_trial': 200,
        'preparation_input_read_bytes': 10279,
        'render_input_read_bytes': len(input_bytes), 'render_source_read_bytes': len(source_bytes),
        'output_hash_read_bytes': len(figure_bytes),
        'wall_seconds': time.perf_counter()-wall, 'cpu_seconds': time.process_time()-cpu,
        'timing_scope': 'input/source reads through single render/save and output hashing; excludes imports and final record write',
        'python': sys.version, 'platform': platform.platform(), 'matplotlib': matplotlib.__version__,
        'raw_audit_E_F_reads': 0, 'model_calls': 0, 'physics_steps': 0, 'updates': 0,
        'new_improvement_statistics': 0, 'partial_RMSE_rankings': 0, 'tests': 0,
        'scope': 'Only saved active step counts and status are plotted; plot geometry computation is nonzero. Research stops are failures, not interaction efficiency; development only.'}
    with execution_path.open('x', encoding='utf-8') as stream:
        json.dump(record, stream, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps(record, indent=2))


if __name__ == '__main__':
    main()
