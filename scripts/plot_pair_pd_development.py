"""Plot the sealed PD summary without reading trajectories or rerunning models."""
from pathlib import Path
import hashlib
import json

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap


ROOT = Path(__file__).resolve().parents[1]


def main():
    archive = ROOT/'results/cpu_validation/2026-10-11_pair_pd'
    manifest = json.loads((archive/'manifest.json').read_text(encoding='utf-8'))
    summary_bytes = (archive/'summary_once/summary.json').read_bytes()
    summary_hash = hashlib.sha256(summary_bytes).hexdigest()
    assert summary_hash == manifest['files']['summary_once/summary.json']['sha256']
    summary = json.loads(summary_bytes)
    assert summary['failed'] == 0 and summary['model_updates'] == 0
    selected = summary['selection']['picked']['candidate']
    counts = [[0]*3 for _ in range(3)]
    for row in summary['trials']:
        counts[row['candidate']//3][row['candidate']%3] += int(row['complete'])

    fig, (grid, errors) = plt.subplots(1, 2, figsize=(9, 4.7),
                                      gridspec_kw={'width_ratios': [1, 1.15]})
    grid.imshow(counts, cmap=ListedColormap(['#fce5e5', '#dff1eb']), vmin=0, vmax=3)
    for shoulder in range(3):
        for elbow in range(3):
            candidate = shoulder*3+elbow
            label = f'{counts[shoulder][elbow]} / 3\ncompleted'
            label += '\nselected' if candidate == selected else ''
            if counts[shoulder][elbow] == 0:
                label += '\nvelocity stop'
            grid.text(elbow, shoulder, label, ha='center', va='center', fontsize=9)
    grid.set(xticks=[0, 1, 2], xticklabels=['1', '2', '4'],
             yticks=[0, 1, 2], yticklabels=['0', '1', '2'],
             xlabel='Elbow damping Kd', ylabel='Shoulder damping Kd',
             title='Full 200-step completion')
    grid.set_xticks([.5, 1.5], minor=True)
    grid.set_yticks([.5, 1.5], minor=True)
    grid.grid(which='minor', color='white', linewidth=2)
    grid.tick_params(which='minor', length=0)
    candidates = summary['eligible_ranked_candidates']
    # Selection order is retained; stopped candidates have no full-window score.
    for index, record in enumerate(candidates):
        candidate = record['candidate']
        values = [row['tracking']['joint'] for row in summary['trials']
                  if row['candidate'] == candidate]
        errors.scatter([index]*3, values, color='#245c55', s=40, zorder=3)
        errors.hlines(record['sort_key'][0], index-.22, index+.22,
                      color='#172f2b', linewidth=2)
    errors.set(xticks=list(range(len(candidates))),
               xticklabels=[f"Kd {r['kd'][0]:g}/{r['kd'][1]:g}" for r in candidates],
               ylabel='Joint tracking RMSE (rad)',
               title='Eligible candidates: all three seeds')
    errors.set_ylim(0, .014)
    errors.grid(axis='y', alpha=.25)
    fig.suptitle('Paired PD development: finite damping comparison', fontsize=14)
    fig.text(.5, .025,
        'Fixed Kp 64/64; development seeds 0/1/2; 9 complete, 18 stopped; no learning updates.\n'
        'Dots: individual seeds. Lines: raw seed means. Truncated trials are excluded from ranking.',
        ha='center', fontsize=9)
    fig.tight_layout(rect=[0, .10, 1, .93])
    output = ROOT/'docs/figures/pair_pd_development.png'
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=180)
    plt.close(fig)
    record = {'source_commit': summary['source_commit'],
              'summary_sha256': summary_hash, 'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'figure_sha256': hashlib.sha256(output.read_bytes()).hexdigest(),
              'matplotlib_version': matplotlib.__version__, 'physics_calls': 0,
              'model_calls': 0, 'audit_calls': 0, 'summary_calls': 0}
    output.with_suffix('.json').write_text(json.dumps(record, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(record))


if __name__ == '__main__':
    main()
