"""Static figures from archived probe and local-learning records only.

No fitting, simulator calls, synthetic final outcomes, or overwrite of prior
outputs. Figures retain negative probe responses and mark missing evaluations.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import TwoSlopeNorm
from matplotlib.patches import Rectangle
import numpy as np


POSES = ("supine", "prone", "left_side", "right_side")
POSE_LABELS = ("Supine", "Prone", "Left side", "Right side")
JOINT_LABELS = ("L shoulder", "L elbow", "R shoulder", "R elbow", "L hip", "L knee", "R hip", "R knee")
CONTROL_KINDS = ("frozen_mpc", "learned_mpc", "fixed_pd", "zero_torque")
CONTROL_LABELS = ("Initial model MPC", "Learned model MPC", "Fixed PD", "Zero torque")
CONTROL_COLORS = ("#277da8", "#df7c2e", "#4e9b61", "#6b6b6b")


def _hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _metadata(inputs, figure_name):
    return {"Description": json.dumps({
        "figure": figure_name,
        "plotter_sha256": _hash(Path(__file__)),
        "input_sha256": {str(path.resolve()): _hash(path) for path in inputs},
        "parameter_updates_by_plotter": 0,
        "physical_steps_by_plotter": 0,
    }, sort_keys=True)}


def _probe_values(profile):
    by_case = {(row["pose"], row["joint_index"], row["seed"]): row
               for row in profile["pairs"] if row["amplitude_nm"] == .5}
    values = np.full((4, 8), np.nan)
    if len(profile["seeds"]) != 3:
        return values
    for i, pose in enumerate(POSES):
        for joint in range(8):
            rows = [by_case.get((pose, joint, seed)) for seed in profile["seeds"]]
            if all(row is not None and row["available"] and row["exact_prefix_replay"] for row in rows):
                deltas = [row["pulse_end"]["target_joint_directed_paired_delta_rad"] for row in rows]
                if all(_finite(value) for value in deltas):
                    values[i, joint] = 1000 * min(deltas)
    return values


def plot_probes(development, holdout, output, inputs):
    matrices = [_probe_values(profile) for profile in (development, holdout)]
    finite = np.concatenate([matrix[np.isfinite(matrix)] for matrix in matrices])
    limit = max(1., float(np.max(np.abs(finite))) if finite.size else 1.)
    norm = TwoSlopeNorm(vmin=-limit, vcenter=0., vmax=limit)
    fig, axes = plt.subplots(1, 2, figsize=(15.5, 5.8), layout="constrained")
    for axis, matrix, title, profile in zip(axes, matrices, ("Development", "Holdout"), (development, holdout)):
        image = axis.imshow(np.ma.masked_invalid(matrix), cmap="RdBu_r", norm=norm, aspect="auto")
        axis.set_xticks(range(8), JOINT_LABELS, rotation=35, ha="right")
        axis.set_yticks(range(4), POSE_LABELS)
        axis.set_title(f"{title}: minimum directed pulse-end response\n0.5 N m, seeds {', '.join(map(str, profile['seeds']))}", fontsize=11)
        axis.set_xticks(np.arange(-.5, 8, 1), minor=True)
        axis.set_yticks(np.arange(-.5, 4, 1), minor=True)
        axis.grid(which="minor", color="white", linewidth=1)
        axis.tick_params(which="minor", bottom=False, left=False)
        for (row, column), value in np.ndenumerate(matrix):
            if not np.isfinite(value):
                axis.text(column, row, "NA", ha="center", va="center", color="#444444", fontsize=10)
                continue
            axis.text(column, row, f"{value:.3g}", ha="center", va="center", fontsize=10,
                      color="white" if abs(value) > .6 * limit else "black")
            if value >= 1.:
                axis.add_patch(Rectangle((column - .48, row - .48), .96, .96, fill=False,
                                         edgecolor="#202020", linewidth=1.8))
    fig.colorbar(image, ax=axes, shrink=.8, label="Minimum directed paired encoder delta (mrad)")
    fig.suptitle("Fixed single-joint probes: every response sign is retained / ideal native sensors", fontsize=14)
    fig.supxlabel("Outline: all 3 paired seeds reach the fixed 1 mrad measurement criterion. NA: a complete valid pair is missing.\n"
                  "Shared zero references do not add independent seeds. All three doses, raw seeds and risk metrics remain in the input JSON.",
                  fontsize=9)
    fig.savefig(output, dpi=160, metadata=_metadata(inputs, "probe minimum response heatmaps"))
    plt.close(fig)


def _evaluation(seed_record, kind):
    record = seed_record.get("evaluations", {}).get(kind)
    return record if record is not None and record.get("completed") else None


def _bar_series(axis, x, values, width, offset, label, color):
    present = np.isfinite(values)
    axis.bar(x[present] + offset, np.asarray(values)[present], width=width, color=color, label=label)
    for location in x[~present] + offset:
        axis.text(location, 0, "NA", rotation=90, va="bottom", ha="center", color=color, fontsize=8)


def _control_rows(archive, seed):
    groups = {kind: [] for kind in CONTROL_KINDS}
    with gzip.open(archive / "trace.jsonl.gz", "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if row.get("seed") == seed and row.get("kind") in groups and "collector_exception" not in row:
                groups[row["kind"]].append(row)
    return groups


def plot_learning(development, holdout, output, inputs):
    dev_meta, hold_meta = (_json(folder / "metadata.json") for folder in (development, holdout))
    if (dev_meta["pose"], dev_meta["joint_index"]) != (hold_meta["pose"], hold_meta["joint_index"]):
        raise ValueError("development and holdout learning tasks differ")
    records = {row["seed"]: row for row in _json(holdout / "seed_results.json")}
    seeds = hold_meta["seeds"]
    fig = plt.figure(figsize=(14.5, 10))
    grid = fig.add_gridspec(2, 2, height_ratios=(1., 1.25))
    prediction_axis, tracking_axis = fig.add_subplot(grid[0, 0]), fig.add_subplot(grid[0, 1])
    trajectory_axis = fig.add_subplot(grid[1, :])
    x = np.arange(len(seeds), dtype=float)
    for name, offset, color, label in (("frozen", -.18, CONTROL_COLORS[0], "Initial frozen model"),
                                      ("learned", .18, CONTROL_COLORS[1], "Learned model, frozen for evaluation")):
        values = []
        for seed in seeds:
            evaluation = _evaluation(records.get(seed, {}), "prediction")
            value = None if evaluation is None else evaluation.get("velocity_prediction_rmse", {}).get(name)
            values.append(value if _finite(value) else np.nan)
        _bar_series(prediction_axis, x, values, .33, offset, label, color)
    prediction_axis.set(ylabel="Single-step native velocity RMSE (rad/s)",
                        title="Independent fixed-input prediction trial\nSeed-local calibration; no evaluation updates")
    prediction_axis.legend(fontsize=8)
    for index, (kind, color, label) in enumerate(zip(CONTROL_KINDS, CONTROL_COLORS, CONTROL_LABELS)):
        values = []
        for seed in seeds:
            evaluation = _evaluation(records.get(seed, {}), kind)
            value = None if evaluation is None else evaluation.get("tracking_rmse_rad")
            values.append(value if _finite(value) else np.nan)
        _bar_series(tracking_axis, x, values, .19, (index - 1.5) * .20, label, color)
    tracking_axis.set(ylabel="Native encoder tracking RMSE (rad)",
                      title="Identical goals and physical torque permission\nAll four methods and every planned holdout seed")
    tracking_axis.legend(fontsize=8)
    for axis in (prediction_axis, tracking_axis):
        axis.set_xticks(x, [f"Seed {seed}" for seed in seeds])
        axis.grid(axis="y", alpha=.2)
        axis.set_axisbelow(True)
        axis.set_ylim(bottom=0)
    seed = seeds[0]
    joint = hold_meta["joint_index"]
    groups = _control_rows(holdout, seed)
    physical_dt = hold_meta["environment_config"]["physics_dt"]
    control_dt = physical_dt * hold_meta["environment_config"]["control_substeps"]
    prefix_seconds = hold_meta["prefix_steps"] * control_dt
    duration_seconds = (hold_meta["prefix_steps"] + hold_meta["control_steps_per_trial"]) * control_dt
    for kind, color, label in zip(CONTROL_KINDS, CONTROL_COLORS, CONTROL_LABELS):
        rows = groups[kind]
        if rows:
            times, positions = [0.], [rows[0]["observation_before"]["joint_position"][joint]]
            for row in rows:
                q = row["observation_after"]["joint_position"][joint]
                t = row["diagnostics"]["time"]
                if _finite(q) and _finite(t):
                    times.append(t)
                    positions.append(q)
                else:
                    times.append(t if _finite(t) else np.nan)
                    positions.append(np.nan)
            evaluation = _evaluation(records.get(seed, {}), kind)
            trajectory_axis.plot(times, positions, color=color, linewidth=1.5,
                                 label=label + (" (incomplete)" if evaluation is None else ""))
    target_rows = next(([row for row in groups[kind] if row.get("target_q") is not None]
                        for kind in CONTROL_KINDS if any(row.get("target_q") is not None for row in groups[kind])), [])
    if target_rows:
        times = [row["diagnostics"]["time"] - row["diagnostics"]["executed_substeps"] * physical_dt for row in target_rows]
        values = [row["target_q"] for row in target_rows]
        times.append(target_rows[-1]["diagnostics"]["time"])
        values.append(values[-1])
        trajectory_axis.step(times, values, where="post", color="black", linestyle="--", linewidth=1.6, label="Declared task target")
    trajectory_axis.axvspan(0, prefix_seconds, color="#b8bcc0", alpha=.20, label="Paid zero-torque prefix")
    trajectory_axis.axvline(prefix_seconds, color="#777777", linewidth=.8, linestyle=":")
    trajectory_axis.set(xlabel="Actual physical time from reset (s)", ylabel="Native joint encoder position (rad)",
                        xlim=(0, duration_seconds),
                        title=f"Holdout seed {seed}: full physical budget, including the {prefix_seconds:g} s passive prefix")
    trajectory_axis.grid(alpha=.18)
    trajectory_axis.legend(fontsize=8, ncols=3)
    fig.suptitle(f"Local body learning: {hold_meta['pose']} / {JOINT_LABELS[joint]} / {len(seeds)} held-out seeds\n"
                 "Shared fixed calibration, frozen evaluation, CPU only", fontsize=14)
    fig.text(.5, .015,
             "Each control method: 100 paid prefix + 200 control steps. Each seed additionally pays 400 shared calibration and 200 shared prediction steps.\n"
             "NA marks a missing or incomplete evaluation; partial RMSE is not displayed as a complete result. "
             "These are single-joint simulation outcomes; all model priors, failures and raw traces stay archived.",
             ha="center", fontsize=9)
    fig.tight_layout(rect=(0, .065, 1, .94))
    fig.savefig(output, dpi=150, metadata=_metadata(inputs, "local learning and full-budget holdout trajectory"))
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probes-development", type=Path, required=True)
    parser.add_argument("--probes-holdout", type=Path, required=True)
    parser.add_argument("--learning-development", type=Path, required=True)
    parser.add_argument("--learning-holdout", type=Path, required=True)
    parser.add_argument("--output-prefix", type=Path, required=True)
    args = parser.parse_args()
    outputs = [args.output_prefix.with_name(args.output_prefix.name + suffix) for suffix in ("_probes.png", "_learning.png")]
    input_folders = [args.learning_development, args.learning_holdout]
    for path in (args.probes_development, args.probes_holdout):
        # A standalone analysis JSON in external/ does not make that entire
        # working directory an archive. Protect its original bytes, and also
        # protect its enclosing directory when it is an actual raw archive.
        if (path.parent / "metadata.json").is_file() and (path.parent / "trace.jsonl.gz").is_file():
            input_folders.append(path.parent)
    if any(output.resolve().is_relative_to(folder.resolve()) for output in outputs for folder in input_folders):
        parser.error("outputs must be outside every read-only input archive")
    if any(output.exists() for output in outputs):
        parser.error("one or more output figures already exist; preserve previous versions")
    inputs = [args.probes_development, args.probes_holdout]
    for folder in (args.learning_development, args.learning_holdout):
        inputs.extend(folder / name for name in ("metadata.json", "seed_results.json", "episodes.json", "trace.jsonl.gz"))
    if any(not path.is_file() for path in inputs):
        parser.error("all formal input files must exist before drawing results")
    for folder in (args.learning_development, args.learning_holdout):
        _json(folder / "metadata.json")
        _json(folder / "seed_results.json")
    args.output_prefix.parent.mkdir(parents=True, exist_ok=True)
    plot_probes(_json(args.probes_development), _json(args.probes_holdout), outputs[0], inputs)
    plot_learning(args.learning_development, args.learning_holdout, outputs[1], inputs)
    print(json.dumps({"outputs": [str(output.resolve()) for output in outputs],
                      "parameter_updates_by_plotter": 0, "physical_steps_by_plotter": 0}, indent=2))


if __name__ == "__main__":
    main()
