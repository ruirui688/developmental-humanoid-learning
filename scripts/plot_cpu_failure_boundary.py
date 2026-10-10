"""Plot archived CPU diagnostics without rerunning a controller or fitting.

Usage: python scripts/plot_cpu_failure_boundary.py PATH/report.json
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


MODES = ("pd", "full", "competence", "competence_sustained")
LABELS = ("Fixed PD", "Full-permission planner", "Original gate", "Persistent-failure variant")
COLORS = ("#617d51", "#5879aa", "#be762e", "#9b4d77")
SCENARIO_LABELS = (
    "Nominal", "Delay 0.12 s", "Delay 0.30 s", "Delay 0.60 s",
    "Delay jump to 0.60 s", "Gain drops to 0.25", "Gain rises to 4", "Inertia rises to 4x",
)


def plot_summary(report_path: Path, output: Path):
    report = json.loads(report_path.read_text(encoding="utf-8"))
    records = report["records"]
    scenarios = [scenario["name"] for scenario in report["config"]["scenarios"]]
    fig = plt.figure(figsize=(14.5, 8.5), layout="constrained")
    grid = fig.add_gridspec(2, 2, width_ratios=(1.05, 1.0), height_ratios=(1.5, 1.0))
    overview = fig.add_subplot(grid[:, 0])
    error = fig.add_subplot(grid[0, 1])
    level = fig.add_subplot(grid[1, 1], sharex=error)
    for index, (mode, label, color) in enumerate(zip(MODES, LABELS, COLORS)):
        offset = (index - 1.5) * 0.14
        for row_index, scenario in enumerate(scenarios):
            rows = [record for record in records if record["scenario"] == scenario and record["mode"] == mode]
            values = [record["audit_halves"]["second225"]["full_target_rmse"] for record in rows
                      if record["audit_halves"]["second225"] is not None]
            ypos = row_index + offset
            if values:
                overview.scatter(values, [ypos] * len(values), s=16, alpha=0.5, color=color)
                overview.scatter(np.mean(values), ypos, s=60, marker="D", color=color,
                                 label=label if row_index == 0 else None, zorder=3)
            else:
                overview.text(0.00085, ypos, "3 exits before step 225", fontsize=8, color=color, va="center")
        # The mean does not replace disclosure of shorter trajectories.
    overview.text(0.17, 3.4, "PD: 0 exits; full: 3 exits", color="#734353", fontsize=8, ha="right")
    overview.set_yticks(range(len(scenarios)), SCENARIO_LABELS)
    overview.set_ylim(8.8, -0.5)  # Leave a separate area for the four-entry legend.
    overview.set_xscale("log")
    overview.set_xlim(0.0008, 0.23)
    overview.set_xlabel("Full-target RMSE after step 225 (rad, log scale)")
    overview.set_title("All fixed scenarios: each dot is one seed", loc="left", fontsize=12, weight="bold")
    overview.grid(axis="x", alpha=0.2, which="both")
    overview.legend(loc="lower left", fontsize=8, frameon=False)

    selected = "gain_drop_1_to_0.25_at225"
    with gzip.open(report_path.parent / "trace.csv.gz", "rt", encoding="utf-8", newline="") as handle:
        trace = [row for row in csv.DictReader(handle) if row["scenario"] == selected and row["mode"] in MODES]
    for mode, label, color in zip(MODES, LABELS, COLORS):
        rows = [row for row in trace if row["mode"] == mode]
        steps = sorted({int(row["step"]) for row in rows})
        by_step = {step: [] for step in steps}
        for row in rows:
            by_step[int(row["step"])].append(float(row["full_target_rmse"]))
        error.plot(np.asarray(steps) * report["config"]["config"]["dt"],
                   [np.mean(by_step[step]) for step in steps], color=color, label=label, linewidth=1.7)
    error.axvline(4.5, color="#444444", linestyle="--", linewidth=1)
    error.text(4.6, 0.072, "Actuator gain 1 -> 0.25", fontsize=9)
    error.set_ylim(0, 0.08)
    error.set_ylabel("Per-step full-target RMSE (rad)")
    error.set_title("Gain-drop case: mean across 3 seeds", loc="left", fontsize=12, weight="bold")
    error.grid(alpha=0.2)
    for mode, label, color in zip(MODES[2:], LABELS[2:], COLORS[2:]):
        rows = [row for row in trace if row["mode"] == mode and int(row["seed"]) == 10]
        # Permission used for the new command, not the delayed actuator torque.
        level.step([float(row["physical_seconds"]) - report["config"]["config"]["dt"] for row in rows],
                   [int(row["level"]) for row in rows], where="post", color=color, label=label, linewidth=2)
    level.axvline(4.5, color="#444444", linestyle="--", linewidth=1)
    level.set_yticks((0, 1, 2))
    level.set_ylim(-0.2, 2.3)
    level.set_ylabel("New-command permission level")
    level.set_xlabel("Simulation time (s)")
    level.set_title("Permission changes (seed 10)", loc="left", fontsize=11)
    level.grid(alpha=0.2)
    level.legend(loc="upper left", fontsize=8, frameon=False)
    fig.suptitle("CPU failure boundary: withdrawal can worsen task tracking", fontsize=16, weight="bold")
    fig.supxlabel("Fixed models; no learning. 144 runs; state exits retained. Permission withdrawal is not a success criterion.", fontsize=10)
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=160)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    plot_summary(args.report, args.output or args.report.parent / "summary.png")


if __name__ == "__main__":
    main()
