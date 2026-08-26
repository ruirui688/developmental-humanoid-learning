#!/usr/bin/env python3
"""Render paper figures from the frozen G1 standing evidence manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


COLORS = {
    "blue": "#2563EB",
    "green": "#059669",
    "amber": "#D97706",
    "red": "#DC2626",
    "slate": "#475569",
    "light": "#E2E8F0",
}


def _style() -> None:
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 11,
            "axes.titlesize": 13,
            "axes.titleweight": "bold",
            "axes.labelsize": 11,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "figure.facecolor": "white",
            "axes.facecolor": "#F8FAFC",
            "grid.color": "#CBD5E1",
            "grid.alpha": 0.55,
        }
    )


def render_summary(manifest: dict, output_dir: Path) -> None:
    runs = manifest["twenty_second_by_seed"]
    long_run = manifest["hundred_second_test"]
    labels = [str(run["seed"]) for run in runs] + ["93101\n(100 s)"]
    episodes = np.array([8192] * len(runs) + [long_run["episodes"]])
    recovered = np.array(
        [run["recovered"] for run in runs]
        + [long_run["recovered_standing_episodes"]]
    )
    zero_tolerance = np.array(
        [run["zero_tolerance"] for run in runs]
        + [long_run["zero_tolerance_strict_episodes"]]
    )
    recovered_pct = 100.0 * recovered / episodes
    zero_pct = 100.0 * zero_tolerance / episodes
    mean_violation = np.array(
        [run["mean_motion_violation_steps"] for run in runs]
        + [long_run["mean_motion_violation_steps"]]
    )
    max_consecutive = np.array(
        [run["max_consecutive"] for run in runs]
        + [long_run["max_consecutive_motion_violation_steps"]]
    )
    angular_mean = np.array(
        [run["post_recovery_mean_max_angular_speed"] for run in runs]
        + [long_run["post_recovery_mean_max_angular_speed"]]
    )
    angular_global = np.array(
        [run["post_recovery_global_max_angular_speed"] for run in runs]
        + [long_run["post_recovery_global_max_angular_speed"]]
    )

    _style()
    fig, axes = plt.subplots(2, 2, figsize=(16, 10), constrained_layout=True)
    fig.get_layout_engine().set(w_pad=0.08, h_pad=0.12, wspace=0.08, hspace=0.10)
    fig.suptitle(
        "Frozen G1 standing evaluation — checkpoint model 4260",
        fontsize=17,
        fontweight="bold",
    )
    x = np.arange(len(labels))

    ax = axes[0, 0]
    width = 0.36
    ax.bar(
        x - width / 2,
        recovered_pct,
        width,
        color=COLORS["green"],
        label="Recovery-standing",
    )
    ax.bar(
        x + width / 2,
        zero_pct,
        width,
        color=COLORS["slate"],
        label="Zero-tolerance sensitivity",
    )
    ax.set_ylim(97.0, 100.15)
    ax.set_ylabel("Episodes passing (%)")
    ax.set_title("A  Finite-horizon acceptance")
    ax.set_xticks(x, labels)
    ax.grid(axis="y")
    ax.legend(loc="lower left", frameon=False)
    for index, value in enumerate(recovered_pct):
        ax.text(
            index - width / 2,
            value + 0.035,
            f"{value:.3f}%",
            ha="center",
            va="bottom",
            fontsize=8.5,
        )

    ax = axes[0, 1]
    ax.bar(x, mean_violation, color=COLORS["blue"], width=0.58)
    ax.set_ylabel("Mean threshold-crossing steps / episode")
    ax.set_title("B  Transient corrective motion")
    ax.set_xticks(x, labels)
    ax.grid(axis="y")
    ax2 = ax.twinx()
    ax2.plot(
        x,
        max_consecutive,
        color=COLORS["red"],
        marker="o",
        linewidth=2,
        label="Worst consecutive steps",
    )
    ax2.axhline(5, color=COLORS["red"], linestyle="--", alpha=0.5)
    ax2.set_ylim(0, 5.7)
    ax2.set_ylabel("Worst consecutive steps", color=COLORS["red"])
    ax2.spines["right"].set_visible(True)
    ax2.legend(loc="upper left", frameon=False)

    ax = axes[1, 0]
    ax.plot(
        x,
        angular_mean,
        color=COLORS["blue"],
        marker="o",
        linewidth=2.2,
        label="Mean per-trajectory maximum",
    )
    ax.plot(
        x,
        angular_global,
        color=COLORS["amber"],
        marker="s",
        linewidth=2.2,
        label="Global maximum",
    )
    ax.axhline(
        0.5,
        color=COLORS["red"],
        linestyle="--",
        linewidth=1.5,
        label="Instantaneous threshold",
    )
    ax.set_ylim(0.25, 0.66)
    ax.set_ylabel("Base angular speed (rad/s)")
    ax.set_title("C  Post-recovery angular-speed tail")
    ax.set_xticks(x, labels)
    ax.grid(axis="y")
    ax.legend(loc="lower right", frameon=False, fontsize=9)

    ax = axes[1, 1]
    names = ["5 × 20 s\nfresh seeds", "1 × 100 s\nlong horizon"]
    trajectory_counts = [40960, long_run["episodes"]]
    simulated_hours = [
        40960 * 20 / 3600,
        long_run["episodes"] * 100 / 3600,
    ]
    bars = ax.bar(
        names,
        simulated_hours,
        color=[COLORS["green"], COLORS["blue"]],
        width=0.55,
    )
    ax.set_ylabel("Aggregate simulated robot-hours")
    ax.set_title("D  Frozen evaluation scale")
    ax.set_ylim(0, 255)
    ax.grid(axis="y")
    for bar, hours, count in zip(bars, simulated_hours, trajectory_counts):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            hours + 5,
            f"{count:,} trajectories\n{hours:.1f} robot-hours",
            ha="center",
            va="bottom",
            fontsize=10,
        )
    ax.text(
        0.02,
        0.02,
        "Fixed dynamics; initial 6-D root velocity ∼ U[−0.05, 0.05]",
        transform=ax.transAxes,
        fontsize=9,
        color=COLORS["slate"],
        bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.85, "pad": 2},
    )

    for suffix in ("png", "svg"):
        fig.savefig(
            output_dir / f"g1_frozen_standing_summary.{suffix}",
            dpi=220,
            bbox_inches="tight",
        )
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("results/validation/g1_frozen_standing_test_20260826.json"),
    )
    parser.add_argument(
        "--output-dir", type=Path, default=Path("results/validation")
    )
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    with args.input.open(encoding="utf-8") as stream:
        manifest = json.load(stream)
    render_summary(manifest, args.output_dir)


if __name__ == "__main__":
    main()
