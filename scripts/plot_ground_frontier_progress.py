#!/usr/bin/env python3
"""Plot the auditable ground-start height frontier from competence windows."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "inputs",
        type=Path,
        nargs="+",
        help="One or more chronological competence logs; later files win on overlap.",
    )
    parser.add_argument("--output", type=Path, default=Path("results/validation/g1_ground_frontier_progress.png"))
    parser.add_argument(
        "--summary-output",
        type=Path,
        help="Optional path for an auditable JSON copy of the plotted records.",
    )
    args = parser.parse_args()
    rows_by_iteration = {}
    for input_path in args.inputs:
        if input_path.suffix == ".json":
            input_rows = json.loads(input_path.read_text())["records"]
        else:
            input_rows = [json.loads(line) for line in input_path.read_text().splitlines()]
        for row in input_rows:
            rows_by_iteration[row["training_iteration"]] = row
    rows = [rows_by_iteration[key] for key in sorted(rows_by_iteration)]
    if not rows:
        raise ValueError("competence log is empty")
    iterations = [row["training_iteration"] for row in rows]
    diagnostics = [row["diagnostics"] for row in rows]
    target = [d.get("rise_frontier_height_target", float("nan")) for d in diagnostics]
    height = [d["frontier_conservative_height_quantile"] for d in diagnostics]
    success = [d["frontier_conservative_height_target_success_fraction"] for d in diagnostics]
    raised = [d["event_raised_conservative_fraction"] for d in diagnostics]
    impulse = [d["assistance_mean_impulse_ns"] for d in diagnostics]
    fig, axes = plt.subplots(2, 1, figsize=(11, 7), sharex=True, constrained_layout=True)
    axes[0].plot(iterations, height, label="Weakest-pose height q80", color="#2563EB", marker="o")
    axes[0].step(iterations, target, where="post", label="Training frontier target", color="#D97706", linewidth=2)
    axes[0].axhline(0.45, color="#DC2626", linestyle="--", label="Fixed raised event (0.45 m)")
    axes[0].set_ylabel("Pelvis/base height (m)")
    axes[0].set_ylim(0.1, 0.5)
    axes[0].legend(frameon=False, ncol=3, fontsize=9)
    axes[0].grid(alpha=0.3)
    axes[0].axvspan(1500, max(iterations), color="#FCA5A5", alpha=0.20)
    axes[0].text(1503, 0.475, "80% support\ndiagnostic", color="#991B1B", fontsize=8, va="top")
    axes[1].plot(iterations, success, label="Height-target success", color="#059669", marker="o")
    axes[1].plot(iterations, raised, label="Raised event", color="#DC2626", marker="x")
    axes[1].plot(iterations, [min(1.0, value / 1000.0) for value in impulse], label="Assistance impulse / 1000 N·s", color="#7C3AED")
    axes[1].axhline(0.40, color="#059669", linestyle=":", label="Stage-step gate (0.40)")
    axes[1].set_xlabel("Training iteration")
    axes[1].set_ylabel("Fraction / normalized assistance")
    axes[1].set_ylim(0, 1.02)
    axes[1].legend(frameon=False, ncol=3, fontsize=9)
    axes[1].grid(alpha=0.3)
    axes[1].axvspan(1500, max(iterations), color="#FCA5A5", alpha=0.20)
    fig.suptitle("G1 ground-start development: evidence-gated height frontier", fontsize=14, fontweight="bold")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.output, dpi=220, bbox_inches="tight")
    plt.close(fig)
    if args.summary_output:
        plotted_keys = (
            "rise_frontier_height_target",
            "frontier_conservative_height_quantile",
            "frontier_conservative_height_target_success_fraction",
            "event_raised_conservative_fraction",
            "assistance_mean_impulse_ns",
            "low_risk_fraction",
            "low_saturation_fraction",
        )
        compact_rows = [
            {
                "training_iteration": row["training_iteration"],
                "diagnostics": {
                    key: row["diagnostics"][key]
                    for key in plotted_keys
                    if key in row["diagnostics"]
                },
            }
            for row in rows
        ]
        summary = {
            "schema_version": 1,
            "description": "Development-only G1 supported-rise height-frontier records plotted in the paper.",
            "source_logs": [str(path) for path in args.inputs],
            "records": compact_rows,
        }
        args.summary_output.parent.mkdir(parents=True, exist_ok=True)
        args.summary_output.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
