#!/usr/bin/env python3
"""Render the repository's evidence levels and current G1 developmental frontier."""

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch


OUTPUT = Path("results/validation/project_evidence_map.png")


def box(ax, x, y, width, height, color, title, detail, text_color="white"):
    patch = FancyBboxPatch(
        (x, y),
        width,
        height,
        boxstyle="round,pad=0.012,rounding_size=0.025",
        linewidth=0,
        facecolor=color,
    )
    ax.add_patch(patch)
    ax.text(x + 0.025, y + height * 0.64, title, color=text_color, weight="bold", fontsize=12)
    ax.text(x + 0.025, y + height * 0.25, detail, color=text_color, fontsize=8.7)


def main() -> None:
    fig = plt.figure(figsize=(13, 7.2), facecolor="#F8FAFC")
    ax = fig.add_axes((0.03, 0.05, 0.94, 0.90))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    ax.text(0.02, 0.95, "Developmental Humanoid Learning — Evidence Map", fontsize=20, weight="bold", color="#0F172A")
    ax.text(0.02, 0.905, "Completed evidence, engineering audits, and open claims are kept separate.", fontsize=11, color="#475569")

    box(ax, 0.02, 0.70, 0.225, 0.15, "#0F766E", "2D concept proof", "COMPLETE\nSame-budget DHP-PPO vs Direct PPO")
    box(ax, 0.265, 0.70, 0.225, 0.15, "#64748B", "G1 standing MVP", "INFRASTRUCTURE ONLY\nCanonical upright reset")
    box(ax, 0.51, 0.70, 0.225, 0.15, "#D97706", "G1 ground track", "ACTIVE — STAGE 2\nRoll / brace gate passed")
    box(ax, 0.755, 0.70, 0.225, 0.15, "#CBD5E1", "Physical G1", "NOT STARTED\nSafety design only", text_color="#334155")

    ax.text(0.02, 0.625, "G1 developmental sequence", fontsize=14, weight="bold", color="#0F172A")
    stages = [
        ("0", "Body exploration", "passed", "#0F766E"),
        ("1", "Roll + brace", "passed", "#0F766E"),
        ("2", "Supported rise", "active: ~0.31 m", "#D97706"),
        ("3", "Crouch + upright", "pending", "#CBD5E1"),
        ("4", "Independent stand", "pending: 20 s", "#CBD5E1"),
    ]
    start_x, width, gap = 0.02, 0.176, 0.018
    for index, (number, title, status, color) in enumerate(stages):
        x = start_x + index * (width + gap)
        text_color = "white" if color != "#CBD5E1" else "#334155"
        box(ax, x, 0.39, width, 0.16, color, f"{number}  {title}", status, text_color=text_color)
        if index < len(stages) - 1:
            ax.annotate("", xy=(x + width + gap * 0.85, 0.47), xytext=(x + width + 0.003, 0.47), arrowprops={"arrowstyle": "->", "color": "#64748B", "lw": 1.8})

    ax.text(0.02, 0.30, "Current evidence", fontsize=12, weight="bold", color="#0F172A")
    ax.text(0.02, 0.245, "0.20 → 0.23 → 0.26 → 0.29 m frontier passed; 0.32 m target remains a supine-limited plateau.", fontsize=10.5, color="#334155")
    ax.text(0.02, 0.195, "Rejected branch", fontsize=12, weight="bold", color="#991B1B")
    ax.text(0.02, 0.145, "80% caregiver unloading briefly improved height, then regressed; sustained raised event stayed at zero.", fontsize=10.5, color="#7F1D1D")
    ax.text(0.02, 0.075, "No G1 efficiency advantage is claimed until common-budget, multi-seed Direct / Fixed / Adaptive comparisons are complete.", fontsize=10.5, weight="bold", color="#0F172A")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUTPUT, dpi=220, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)


if __name__ == "__main__":
    main()
