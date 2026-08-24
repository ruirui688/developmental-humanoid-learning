"""Export publication-ready MP4/GIF demonstrations from trained checkpoints."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.animation import FFMpegWriter, FuncAnimation, PillowWriter
import numpy as np
import torch

from .env import IdealStickmanEnv
from .evaluate import joint_points, record_rollout
from .ppo import ActorCritic


COLORS = {"torso": "#0f172a", "left": "#2563eb", "right": "#ef4444", "accent": "#14b8a6"}


def load_model(checkpoint: Path) -> ActorCritic:
    data = torch.load(checkpoint, map_location="cpu", weights_only=False)
    model = ActorCritic(IdealStickmanEnv.observation_size, IdealStickmanEnv.action_size)
    model.load_state_dict(data["state_dict"])
    model.eval()
    return model


def _setup_axis(ax, title: str):
    ax.set_ylim(-0.08, 1.95)
    ax.set_aspect("equal")
    ax.set_yticks([])
    ax.set_xlabel("Forward distance (m)")
    ax.set_title(title, fontsize=13, weight="bold")
    ax.grid(axis="x", alpha=0.18)
    for side in ["left", "right", "top"]:
        ax.spines[side].set_visible(False)
    torso, = ax.plot([], [], "o-", lw=4, ms=8, color=COLORS["torso"])
    left, = ax.plot([], [], "o-", lw=5, ms=8, color=COLORS["left"])
    right, = ax.plot([], [], "o-", lw=5, ms=8, color=COLORS["right"])
    ground, = ax.plot([], [], lw=2, color="#475569")
    trail, = ax.plot([], [], lw=2, color=COLORS["accent"], alpha=0.5)
    status = ax.text(
        0.02, 0.96, "", transform=ax.transAxes, va="top", ha="left", fontsize=10,
        family="monospace", bbox=dict(boxstyle="round,pad=0.4", facecolor="white", alpha=0.88, edgecolor="#cbd5e1")
    )
    return torso, left, right, ground, trail, status


def _draw_frame(ax, artists, frame, trail_x, failed_latched=False):
    torso_line, left_line, right_line, ground, trail, status = artists
    head, torso, hip, lk, lf, rk, rf = joint_points(frame)
    torso_line.set_data([head[0], torso[0], hip[0]], [head[1], torso[1], hip[1]])
    left_line.set_data([hip[0], lk[0], lf[0]], [hip[1], lk[1], lf[1]])
    right_line.set_data([hip[0], rk[0], rf[0]], [hip[1], rk[1], rf[1]])
    x = frame["x"]
    ax.set_xlim(x - 1.45, x + 1.45)
    ground.set_data([x - 1.55, x + 1.55], [0.02, 0.02])
    trail.set_data(trail_x, np.full(len(trail_x), 1.05))
    state = "FALL" if failed_latched or frame.get("fallen", False) else "WALKING"
    status.set_text(
        f"t = {frame['time']:5.2f} s\n"
        f"x = {frame['x']:5.2f} m\n"
        f"v = {frame['speed']:5.2f} m/s\n"
        f"tilt = {np.degrees(frame['tilt']):5.1f} deg\n"
        f"support = OFF\nstate = {state}"
    )
    status.set_color("#b91c1c" if state == "FALL" else "#0f766e")
    return artists


def save_single(frames, mp4_path: Path, gif_path: Path | None = None, fps: int = 25):
    fig, ax = plt.subplots(figsize=(9.6, 5.4), dpi=120)
    fig.suptitle("DHP-PPO: Idealized Independent Walking", fontsize=16, weight="bold")
    artists = _setup_axis(ax, "Held-out seed 10 · deterministic policy · external support disabled")
    trail_x = []

    def update(i):
        frame = frames[i]
        trail_x.append(frame["x"])
        return _draw_frame(ax, artists, frame, trail_x)

    animation = FuncAnimation(fig, update, frames=len(frames), interval=1000 / fps, blit=False)
    mp4_path.parent.mkdir(parents=True, exist_ok=True)
    animation.save(
        mp4_path,
        writer=FFMpegWriter(fps=fps, codec="libx264", bitrate=3500, extra_args=["-pix_fmt", "yuv420p", "-movflags", "+faststart"]),
        dpi=120,
    )
    if gif_path is not None:
        gif_indices = list(range(0, len(frames), 2))
        gif_trail = []

        def update_gif(j):
            frame = frames[gif_indices[j]]
            gif_trail.append(frame["x"])
            return _draw_frame(ax, artists, frame, gif_trail)

        gif_animation = FuncAnimation(fig, update_gif, frames=len(gif_indices), interval=80, blit=False)
        gif_animation.save(gif_path, writer=PillowWriter(fps=fps // 2), dpi=90)
    plt.close(fig)


def save_comparison(traditional, developmental, output: Path, fps: int = 25):
    fig, axes = plt.subplots(1, 2, figsize=(12.8, 5.4), dpi=120)
    fig.suptitle("Same PPO interaction budget: direct training vs. developmental learning", fontsize=16, weight="bold")
    art_trad = _setup_axis(axes[0], "Direct PPO")
    art_dev = _setup_axis(axes[1], "DHP-PPO (developmental)")
    trail_trad, trail_dev = [], []
    n = max(len(traditional), len(developmental))
    trad_fall_time = traditional[-1]["time"] if traditional[-1].get("fallen") else None

    def update(i):
        ti = min(i, len(traditional) - 1)
        di = min(i, len(developmental) - 1)
        tframe, dframe = traditional[ti], developmental[di]
        if i < len(traditional):
            trail_trad.append(tframe["x"])
        if i < len(developmental):
            trail_dev.append(dframe["x"])
        _draw_frame(axes[0], art_trad, tframe, trail_trad, failed_latched=trad_fall_time is not None and i >= len(traditional) - 1)
        _draw_frame(axes[1], art_dev, dframe, trail_dev)
        return (*art_trad, *art_dev)

    animation = FuncAnimation(fig, update, frames=n, interval=1000 / fps, blit=False)
    output.parent.mkdir(parents=True, exist_ok=True)
    animation.save(
        output,
        writer=FFMpegWriter(fps=fps, codec="libx264", bitrate=5000, extra_args=["-pix_fmt", "yuv420p", "-movflags", "+faststart"]),
        dpi=120,
    )
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--developmental", type=Path, required=True)
    parser.add_argument("--traditional", type=Path)
    parser.add_argument("--output", type=Path, default=Path("results/validation/media"))
    parser.add_argument("--seed", type=int, default=20_010)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    dev_frames = record_rollout(load_model(args.developmental), seed=args.seed)
    save_single(dev_frames, args.output / "developmental_walk.mp4", args.output / "developmental_walk.gif")
    if args.traditional:
        trad_frames = record_rollout(load_model(args.traditional), seed=args.seed)
        save_comparison(trad_frames, dev_frames, args.output / "ppo_vs_developmental.mp4")


if __name__ == "__main__":
    main()

