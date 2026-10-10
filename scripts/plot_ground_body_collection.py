"""Plot physical geometry snapshots with CPU Matplotlib; no MuJoCo renderer."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    records = json.loads((args.archive / "geometry.json").read_text(encoding="utf-8"))
    seeds = sorted({r["seed"] for r in records})
    seed = seeds[0]
    poses = ("supine", "prone", "left_side", "right_side")
    fig = plt.figure(figsize=(11, 11))
    for row, pose in enumerate(poses):
        selected = {r["mode"]: r for r in records if r["pose"] == pose and r["seed"] == seed}
        for column, (label, shapes) in enumerate((
            ("Initial ground pose", selected["zero_torque"]["initial"]),
            ("Zero torque: passive response", selected["zero_torque"]["final"]),
            ("Smooth random torque: response", selected["smooth_random"]["final"]),
        )):
            ax = fig.add_subplot(4, 3, row * 3 + column + 1, projection="3d")
            for shape in shapes:
                ends = np.asarray(shape["endpoints"])
                ax.plot(ends[:, 0], ends[:, 1], ends[:, 2], color="#2672ac", linewidth=max(2, 90 * shape["radius"]))
                center = shape["center"]
                if shape["name"] == "head":
                    ax.scatter(*center, s=180, color="#ecae50", depthshade=False)
            grid = np.array([[-.8, -.8, 0], [.8, -.8, 0], [.8, .8, 0], [-.8, .8, 0], [-.8, -.8, 0]])
            ax.plot(grid[:, 0], grid[:, 1], grid[:, 2], color="#a0a0a0", alpha=.6)
            ax.set(xlim=(-.8, .8), ylim=(-.8, .8), zlim=(0, .8))
            ax.set_box_aspect((2, 2, 1))
            ax.view_init(elev=28, azim=-60)
            ax.set_xticks([]); ax.set_yticks([]); ax.set_zticks([0, .4, .8])
            ax.set_title(f"{pose}: {label}", fontsize=9)
    fig.suptitle(f"CPU physical body exploration / seed {seed} / zero parameter updates\nGeometry endpoints from simulation; marker thickness is illustrative", fontsize=12)
    fig.tight_layout(rect=(0, 0, 1, .96))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.output, dpi=130)
    plt.close(fig)


if __name__ == "__main__":
    main()
