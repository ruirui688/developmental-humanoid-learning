#!/usr/bin/env python3
"""Plot the frozen baseline and rejected stage-2 subskill diagnostics."""

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


INPUT = Path("results/validation/g1_supine_subskill_diagnostic_20260826.json")
OUTPUT = Path("results/validation/g1_supine_subskill_diagnostic.png")


def main() -> None:
    data = json.loads(INPUT.read_text())
    rows = data["records"]
    labels = ["Baseline", "v1 all poses", "v2 supine only"]
    colors = ["#2563EB", "#DC2626", "#D97706"]
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8), constrained_layout=True)

    heights = [row["weakest_height_q80_m"] for row in rows]
    axes[0].bar(labels, heights, color=colors)
    axes[0].axhline(data["evaluation"]["height_target_m"], color="#0F172A", linestyle="--", label="0.32 m target")
    axes[0].set_ylim(0.295, 0.323)
    axes[0].set_ylabel("Weakest-pose height q80 (m)")
    axes[0].set_title("Neither subskill variant improved the frontier")
    axes[0].legend(frameon=False)
    for index, value in enumerate(heights):
        axes[0].text(index, value + 0.0005, f"{value:.4f}", ha="center", fontsize=9)

    poses = ["supine", "prone", "left_side", "right_side"]
    x = np.arange(len(poses))
    width = 0.25
    for index, (row, label, color) in enumerate(zip(rows, labels, colors)):
        values = [row["pose_target_success"][pose] for pose in poses]
        axes[1].bar(x + (index - 1) * width, values, width, label=label, color=color)
    axes[1].set_xticks(x, ["Supine", "Prone", "Left side", "Right side"])
    axes[1].set_ylim(0, 1.05)
    axes[1].set_ylabel("0.32 m target success fraction")
    axes[1].set_title("Shared-policy interference remained in v2")
    axes[1].legend(frameon=False, fontsize=8)
    axes[1].grid(axis="y", alpha=0.25)

    fig.suptitle("G1 stage-2 local subskill diagnostic — rejected variants", fontsize=14, weight="bold")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUTPUT, dpi=220, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    main()
