#!/usr/bin/env python3
"""Extract an auditable paper contact sheet from a G1 evaluation video."""

from __future__ import annotations

import argparse
import subprocess
import tempfile
from pathlib import Path

import matplotlib.pyplot as plt


def extract_frame(video: Path, time_s: float, output: Path) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-loglevel",
            "error",
            "-ss",
            str(time_s),
            "-i",
            str(video),
            "-frames:v",
            "1",
            "-y",
            str(output),
        ],
        check=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("video", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--times", type=float, nargs="+", default=[1.0, 3.0, 5.0, 7.0])
    parser.add_argument(
        "--title",
        default="Frozen G1 policy: motion-aware standing sequence",
    )
    parser.add_argument(
        "--footer",
        default="Qualitative single-trajectory visualization; quantitative claims use the frozen multi-environment episode bank.",
    )
    args = parser.parse_args()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="g1-contact-sheet-") as directory:
        frames = []
        for index, time_s in enumerate(args.times):
            frame = Path(directory) / f"frame-{index}.png"
            extract_frame(args.video, time_s, frame)
            frames.append(plt.imread(frame))

    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11})
    fig, axes = plt.subplots(1, len(frames), figsize=(4.4 * len(frames), 3.2))
    if len(frames) == 1:
        axes = [axes]
    fig.suptitle(args.title, fontsize=17, fontweight="bold")
    for axis, image, time_s in zip(axes, frames, args.times):
        axis.imshow(image)
        axis.set_title(f"t = {time_s:g} s", fontweight="bold")
        axis.axis("off")
    fig.text(0.5, 0.015, args.footer, ha="center", color="#475569", fontsize=10)
    fig.subplots_adjust(left=0.01, right=0.99, top=0.86, bottom=0.10, wspace=0.025)
    fig.savefig(args.output, dpi=220, bbox_inches="tight", facecolor="white")
    plt.close(fig)


if __name__ == "__main__":
    main()
