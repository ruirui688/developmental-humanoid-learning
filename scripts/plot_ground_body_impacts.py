"""CPU figure for sampled contact peaks and passive-motion controls."""

from __future__ import annotations

import argparse
import gzip
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    profile = json.loads((args.archive / "impact_profile.json").read_text(encoding="utf-8"))
    worst = max(profile["trials"], key=lambda t: t["endpoint_peak_miss_percent"])
    rows = []
    with gzip.open(args.archive / "trace.jsonl.gz", "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if row["trial_id"] == worst["trial_id"]:
                rows.append(row)
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))
    times, forces = [], []
    for row in rows:
        diagnostic = row["diagnostics"]
        values = diagnostic["substep_ground_normal_forces"]
        times.extend(diagnostic["time"] - np.arange(len(values) - 1, -1, -1) * .002)
        forces.extend(values)
    axes[0].plot(times, forces, color="#2575a8", linewidth=1.4, label="2 ms physics samples")
    axes[0].scatter([r["diagnostics"]["time"] for r in rows],
                    [r["diagnostics"]["ground_normal_force"] for r in rows],
                    color="#de812c", s=17, label="20 ms control endpoints", zorder=3)
    axes[0].set(xlim=(0, 1.2), xlabel="Time (s)", ylabel="Total ground normal force (N)",
                title=f"Largest sampling miss: {worst['pose']}, seed {worst['seed']}\n{worst['endpoint_peak_miss_percent']:.1f}% of peak missed")
    axes[0].legend(fontsize=8)
    poses = ("supine", "prone", "left_side", "right_side")
    x = np.arange(4)
    for mode, offset, color, label in (("zero_torque", -.18, "#2575a8", "Zero torque (passive)"),
                                      ("smooth_random", .18, "#de812c", "Smooth random torque")):
        values = [max(t["peak_substep_ground_normal_force_n"] for t in profile["trials"] if t["pose"] == pose and t["mode"] == mode) for pose in poses]
        bars = axes[1].bar(x + offset, values, width=.34, color=color, label=label)
        axes[1].bar_label(bars, fmt="%.0f", fontsize=8)
    axes[1].set_xticks(x, ["Supine", "Prone", "Left side", "Right side"])
    axes[1].set(ylabel="Maximum sampled force (N)", ylim=(0, 1150),
                title="Maximum across 3 seeds per pose / mode\nStrong peaks also occur without motor commands")
    axes[1].legend(fontsize=8)
    for ax in axes:
        ax.grid(axis="y", alpha=.2)
        ax.set_axisbelow(True)
    fig.suptitle("Fixed-action CPU replay / zero parameter updates / 2 ms samples are not continuous-time bounds", fontsize=10)
    fig.tight_layout()
    fig.savefig(args.output, dpi=140)
    plt.close(fig)


if __name__ == "__main__":
    main()
