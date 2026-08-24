"""Command-line entry point for reproducible comparison experiments."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import platform
import time

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import torch
from scipy.stats import ttest_rel, wilcoxon

from .evaluate import evaluate, joint_points, record_rollout
from .ppo import PPOConfig, train_ppo


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--methods", nargs="+", default=["traditional", "developmental"])
    p.add_argument("--seeds", nargs="+", type=int, default=[0, 1, 2])
    p.add_argument("--updates", type=int, default=80)
    p.add_argument("--num-envs", type=int, default=32)
    p.add_argument("--rollout-steps", type=int, default=96)
    p.add_argument("--eval-episodes", type=int, default=30)
    p.add_argument("--body-model-coef", type=float, default=0.08)
    p.add_argument("--human-prior-coef", type=float, default=0.50)
    p.add_argument("--human-prior-samples", type=int, default=8192)
    p.add_argument("--human-prior-updates", type=int, default=120)
    p.add_argument("--output", type=Path, default=Path("results/main"))
    return p.parse_args()


def save_summary_plot(metrics: pd.DataFrame, output: Path):
    order = [m for m in ["traditional", "developmental"] if m in set(metrics["method"])]
    colors = {"traditional": "#64748b", "developmental": "#14b8a6"}
    fig, axes = plt.subplots(1, 3, figsize=(10.5, 3.2))
    for ax, key, title in zip(
        axes,
        ["success_rate", "fall_rate", "joint_tracking_rmse"],
        ["Success rate ↑", "Fall rate ↓", "Joint RMSE ↓"],
    ):
        grouped = [metrics.loc[metrics.method == m, key].to_numpy() for m in order]
        names = order
        means = [x.mean() for x in grouped]
        stds = [x.std(ddof=1) if len(x) > 1 else 0.0 for x in grouped]
        ax.bar(names, means, yerr=stds, capsize=4, color=[colors[m] for m in names])
        ax.set_title(title)
        ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(output / "comparison.png", dpi=180)
    plt.close(fig)


def save_rollout_plot(frames, output: Path):
    if not frames:
        return
    # Show roughly one gait cycle. Sampling the whole rollout can alias the
    # periodic gait and accidentally select nearly identical phases.
    start = min(20, max(0, len(frames) // 5))
    stop = min(len(frames) - 1, start + 22)
    indices = np.linspace(start, stop, min(8, stop - start + 1), dtype=int)
    fig, ax = plt.subplots(figsize=(11, 3.4))
    for j, i in enumerate(indices):
        pts = joint_points(frames[i])
        shift = np.array([j * 1.05 - pts[2][0], 0.0])
        head, torso, hip, lk, lf, rk, rf = [p + shift for p in pts]
        alpha = 0.35 + 0.65 * j / max(1, len(indices) - 1)
        ax.plot([head[0], torso[0], hip[0]], [head[1], torso[1], hip[1]], "o-", color="#0f172a", alpha=alpha)
        ax.plot([hip[0], lk[0], lf[0]], [hip[1], lk[1], lf[1]], "o-", color="#2563eb", alpha=alpha)
        ax.plot([hip[0], rk[0], rf[0]], [hip[1], rk[1], rf[1]], "o-", color="#ef4444", alpha=alpha)
    ax.axhline(0.02, color="#334155", lw=1)
    ax.set_aspect("equal")
    ax.set_xlim(-0.7, len(indices) * 1.05)
    ax.set_ylim(-0.08, 1.95)
    ax.axis("off")
    ax.set_title("Learned independent-walking rollout (time runs left to right)")
    fig.tight_layout()
    fig.savefig(output / "stickman_rollout.png", dpi=180)
    plt.close(fig)


def save_fall_curve(curves: pd.DataFrame, output: Path):
    fig, ax = plt.subplots(figsize=(6.5, 3.8))
    colors = {"traditional": "#64748b", "developmental": "#14b8a6"}
    for method in ["traditional", "developmental"]:
        part = curves[curves.method == method]
        if part.empty:
            continue
        grouped = part.groupby("environment_steps")["training_falls"]
        x = np.array(sorted(grouped.groups))
        mean = grouped.mean().reindex(x).to_numpy()
        std = grouped.std().fillna(0).reindex(x).to_numpy()
        ax.plot(x, mean, label=method, color=colors[method], lw=2)
        ax.fill_between(x, mean - std, mean + std, color=colors[method], alpha=0.15)
    ax.set_xlabel("Environment interactions")
    ax.set_ylabel("Cumulative training falls")
    ax.grid(alpha=0.25)
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(output / "training_falls.png", dpi=180)
    plt.close(fig)


def save_statistics(metrics: pd.DataFrame, output: Path):
    traditional = metrics[metrics.method == "traditional"].set_index("seed")
    developmental = metrics[metrics.method == "developmental"].set_index("seed")
    common = traditional.index.intersection(developmental.index)
    stats = {}
    for key in ["training_falls", "mean_speed", "mean_distance", "joint_tracking_rmse"]:
        diff = developmental.loc[common, key] - traditional.loc[common, key]
        sem = float(diff.sem())
        # t_(0.975, 4)=2.776 for the default five-seed validation. Keep
        # scipy's interval computation out of the stored format for readability.
        from scipy.stats import t as student_t
        critical = float(student_t.ppf(0.975, max(1, len(diff) - 1)))
        stats[key] = {
            "paired_difference_mean": float(diff.mean()),
            "ci95": [float(diff.mean() - critical * sem), float(diff.mean() + critical * sem)],
            "paired_t_p": float(ttest_rel(developmental.loc[common, key], traditional.loc[common, key]).pvalue),
            "wilcoxon_p": float(wilcoxon(developmental.loc[common, key], traditional.loc[common, key]).pvalue),
        }
    stats["training_fall_reduction"] = float(
        1.0 - developmental.training_falls.mean() / traditional.training_falls.mean()
    )
    stats["distance_ratio"] = float(
        developmental.mean_distance.mean() / traditional.mean_distance.mean()
    )
    (output / "statistics.json").write_text(json.dumps(stats, indent=2), encoding="utf-8")


def main():
    args = parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    cfg = PPOConfig(
        num_envs=args.num_envs,
        rollout_steps=args.rollout_steps,
        total_updates=args.updates,
        body_model_coef=args.body_model_coef,
        human_prior_coef=args.human_prior_coef,
        human_prior_samples=args.human_prior_samples,
        human_prior_updates=args.human_prior_updates,
    )
    all_curves, all_metrics = [], []
    best = None
    best_score = -np.inf
    started = time.time()
    for method in args.methods:
        for seed in args.seeds:
            print(f"training method={method} seed={seed}", flush=True)
            model, curves = train_ppo(method, seed, cfg)
            metrics = evaluate(model, seed=10_000 + seed, episodes=args.eval_episodes)
            metrics.update(
                method=method,
                seed=seed,
                environment_steps=cfg.num_envs * cfg.rollout_steps * cfg.total_updates,
                training_falls=curves[-1]["training_falls"],
                human_prior_samples=(cfg.human_prior_samples if method == "developmental" else 0),
            )
            print(json.dumps(metrics, ensure_ascii=False), flush=True)
            all_curves.extend(curves)
            all_metrics.append(metrics)
            torch.save({"state_dict": model.state_dict(), "config": vars(cfg), "metrics": metrics}, args.output / f"{method}_seed{seed}.pt")
            score = metrics["success_rate"] - metrics["fall_rate"]
            if method == "developmental" and score > best_score:
                best, best_score = model, score

    curves_df = pd.DataFrame(all_curves)
    metrics_df = pd.DataFrame(all_metrics)
    curves_df.to_csv(args.output / "learning_curves.csv", index=False)
    metrics_df.to_csv(args.output / "metrics_by_seed.csv", index=False)
    numeric = [c for c in metrics_df.columns if c not in {"method", "seed"}]
    summary = metrics_df.groupby("method")[numeric].agg(["mean", "std"])
    summary.to_csv(args.output / "summary.csv")
    save_summary_plot(metrics_df, args.output)
    save_fall_curve(curves_df, args.output)
    if set(args.methods) >= {"traditional", "developmental"}:
        save_statistics(metrics_df, args.output)
    if best is not None:
        save_rollout_plot(record_rollout(best), args.output)
    metadata = {
        "elapsed_seconds": time.time() - started,
        "config": vars(cfg),
        "methods": args.methods,
        "seeds": args.seeds,
        "evaluation": "deterministic policy, independent_walk, support=0",
        "python": platform.python_version(),
        "torch": torch.__version__,
        "platform": platform.platform(),
    }
    (args.output / "run_metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(summary.to_string(), flush=True)


if __name__ == "__main__":
    main()
