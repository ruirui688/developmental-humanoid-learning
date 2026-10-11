"""Plot bound first-audit metrics and saved predictions, with no model calls."""
import hashlib
import json
from pathlib import Path
import statistics

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT/'results/cpu_validation/2026-10-11_guard_pair'
INPUTS = {
    'first_audit.json': 'bf9b6c0e9eed25443f3e1ceee3c33cfa1da4b21db37dbaa17df23147acf385b2',
    'saved_failure_diagnostic/saved_failed_controls.json': '78f81f68847838d44feca6924dd54214413317fc56caaeb31882498aea7c0fc6',
}

def main():
    loaded = {}
    for name, expected in INPUTS.items():
        data = (ARCHIVE/name).read_bytes()
        if hashlib.sha256(data).hexdigest() != expected:
            raise ValueError('Archived byte binding failed: '+name)
        loaded[name] = json.loads(data)
    audit = loaded['first_audit.json']
    rows = loaded['saved_failure_diagnostic/saved_failed_controls.json']['rows']
    fig, axes = plt.subplots(2, 2, figsize=(12, 8), layout='constrained')
    kinds = ['nominal_raw','learned_raw','nominal_guard','learned_guard','PDselected','zero']
    labels = ['Nominal raw','Learned raw','Nominal guard','Learned guard','Selected PD','Zero']
    ax = axes[0, 0]
    completions = []
    for i, kind in enumerate(kinds):
        values = [seed['evaluations'][kind]['complete_score_endpoints'] for seed in audit['archive']['seeds']]
        completions.append({'kind': kind, 'complete_active_endpoints': values})
        ax.barh(i, statistics.mean(values), color='#dc6a56' if kind.startswith('learned') else '#3e8a95', alpha=.8)
        for seed, value in enumerate(values):
            ax.scatter(value, i+(seed-1)*.14, s=18, color='#203640', zorder=3)
        ax.text(max(values)+2, i, str(values[0]) if len(set(values)) == 1 else str(values), va='center', fontsize=9)
    ax.set(yticks=range(6), yticklabels=labels, xlim=(0, 232), xlabel='Completed active intervals per seed', title='Control completion (planned: 200)')
    ax.invert_yaxis()
    ax.axvline(200, color='#7d858c', lw=1, ls='--')
    ax = axes[0, 1]
    prediction = []
    for i, (basis, axis) in enumerate([('raw',0),('raw',1),('guard',0),('guard',1)]):
        values = [100*(1-s['learned_velocity_prediction'][axis]/s['nominal_velocity_prediction'][axis])
                  for s in audit['final_gates']['model_contribution'][basis]['per_seed']]
        prediction.append({'basis': basis, 'axis': axis, 'improvement_percent': values})
        ax.scatter([i]*3, values, color='#3e8a95', s=26)
        ax.plot([i-.2,i+.2], [statistics.mean(values)]*2, color='#203640', lw=2)
    ax.axhline(20, color='#7d858c', ls='--', label='Numeric threshold (20%)')
    ax.set(xticks=range(4), xticklabels=['Raw\nshoulder','Raw\nelbow','Guard\nshoulder','Guard\nelbow'],
           ylim=(0, 42), ylabel='Velocity RMSE reduction (%)', title='Complete independent pulse prediction')
    ax.text(.03, .06, 'Contribution gate also requires complete control.', transform=ax.transAxes, fontsize=9)
    colors = ['#237a9b','#b67322','#5d618f']
    for ax, kind, label in [(axes[1,0],'learned_raw','Raw learned'),(axes[1,1],'learned_guard','Guard learned')]:
        for seed in (0,1,2):
            selected = [r for r in rows if r['seed'] == seed and r['kind'] == kind]
            x = list(range(1, len(selected)+1))
            ax.plot(x, [r['measured_next_v'][1] for r in selected], 'o-', color=colors[seed], lw=1.5,
                    label=f'Seed {seed}: measured')
            ax.plot(x, [r['saved_prediction_next_v'][1] for r in selected], 'x--', color=colors[seed], lw=1.3,
                    label=f'Seed {seed}: saved prediction')
        ax.axhline(1, color='#b24239', ls=':', label='Study stop threshold')
        ax.set(xlabel='Active interval (20 ms each)', ylabel='Elbow endpoint velocity (rad/s)', ylim=(0,1.18),
               xticks=range(1, 5 if kind == 'learned_guard' else 3), title=label+': saved forecast and measured response')
    handles, legend_labels = axes[1,1].get_legend_handles_labels()
    fig.legend(handles, legend_labels, ncols=4, loc='outside lower center', fontsize=8)
    for ax in axes.flat:
        ax.spines[['top','right']].set_visible(False)
        ax.grid(axis='y', alpha=.16)
    fig.suptitle('C4 A: independent prediction and closed-loop failure', fontsize=15)
    output = ROOT/'docs/figures'
    output.mkdir(exist_ok=True)
    png = output/'guard_pair_development.png'
    fig.savefig(png, dpi=180)
    plt.close(fig)
    metadata = {'inputs': INPUTS, 'read_passes_per_input': 1, 'model_calls': 0, 'physics_calls': 0,
        'audit_executions': 0, 'matplotlib_version': matplotlib.__version__, 'completion': completions,
        'independent_prediction_numeric_improvement': prediction,
        'scientific_gates': audit['final_gates'], 'png_sha256': hashlib.sha256(png.read_bytes()).hexdigest(),
        'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'claim_boundary': 'Saved values only. Stopped controls have no full-window tracking ranking.'}
    (output/'guard_pair_development.json').write_text(json.dumps(metadata, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'png': str(png), 'model_calls': 0, 'physics_calls': 0}))

if __name__ == '__main__': main()
