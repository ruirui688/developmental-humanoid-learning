"""Plot a frozen CPU history/horizon archive without running a controller.

Usage: python scripts/plot_cpu_history_summary.py PATH/report.json [--output PNG]
Only report.json and the adjacent trace.csv.gz are read as experiment inputs.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np


MODES = ("immediate_h20", "history_h20", "immediate_h50", "history_h50", "pd")
LABELS = ("Immediate H20", "History H20", "Immediate H50", "History H50", "Fixed PD")
COLORS = ("#426bba", "#945cb4", "#3798a5", "#d07b32", "#6b874d")
STYLES = ("--", "--", "-", "-", ":")
SCENARIO_LABELS = {
    "nominal": "Nominal",
    "constant_delay_6": "Constant delay 0.12 s",
    "constant_delay_15": "Constant delay 0.30 s",
    "constant_delay_30": "Constant delay 0.60 s",
    "delay_jump_0_to_30_at225": "Delay 0 -> 0.60 s",
    "delay_jump_15_to_30_at225": "Delay 0.30 -> 0.60 s",
    "gain_drop_1_to_0.25_at225": "Gain 1 -> 0.25",
    "gain_drop_1_to_0.125_at225": "Gain 1 -> 0.125",
}


def _optional_finite(value, name):
    if value is None or value == "":
        return None
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite or explicitly missing")
    return result


def _is_exit(record):
    return record["termination_reason"] != "completed"


def plot_summary(report_path: Path, output: Path):
    report_path, output = Path(report_path), Path(output)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report["kind"] != "cpu_no_training_history_horizon_diagnostic":
        raise ValueError("expected a history/horizon diagnostic report")
    config = report["config"]
    scenarios = [item["plant"]["name"] for item in config["scenarios"]]
    seeds = config["config"]["seeds"]
    dt = float(config["config"]["dt"])
    records = report["records"]
    indexed = {(item["scenario"], int(item["seed"]), item["mode"]): item for item in records}
    if len(indexed) != len(records):
        raise ValueError("duplicate run records")
    for scenario in scenarios:
        for mode in MODES:
            for seed in seeds:
                if (scenario, int(seed), mode) not in indexed:
                    raise ValueError(f"missing run: {scenario}, {seed}, {mode}")

    selected = ("constant_delay_30", "delay_jump_15_to_30_at225")
    selected_seed = 10
    trace = {(scenario, mode): [] for scenario in selected for mode in MODES}
    with gzip.open(report_path.parent / "trace.csv.gz", "rt", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            key = (row["scenario"], row["mode"])
            if key in trace and int(row["seed"]) == selected_seed:
                trace[key].append(row)

    fig = plt.figure(figsize=(16.3, 9.2))
    grid = fig.add_gridspec(2, 2, width_ratios=(1.18, 1.0), height_ratios=(1.0, 1.0),
                           left=0.155, right=0.975, top=0.845, bottom=0.20,
                           wspace=0.33, hspace=0.36)
    overview = fig.add_subplot(grid[:, 0])
    constant = fig.add_subplot(grid[0, 1])
    jump = fig.add_subplot(grid[1, 1], sharex=constant)
    all_values = [_optional_finite(row["full_target_rmse"], "full_target_rmse") for row in records]
    finite_values = [value for value in all_values if value is not None]
    if not finite_values:
        plt.close(fig)
        raise ValueError("the archive has no finite full-target RMSE values")
    x_max = max(0.10, max(finite_values) * 1.35)
    missing_notes = []
    for mode_index, (mode, color) in enumerate(zip(MODES, COLORS)):
        offset = (mode_index - 2) * 0.16
        for row_index, scenario in enumerate(scenarios):
            rows = [indexed[(scenario, int(seed), mode)] for seed in seeds]
            y = row_index + offset
            values = []
            for row in rows:
                value = _optional_finite(row["full_target_rmse"], "full_target_rmse")
                if value is not None:
                    values.append(value)
                    overview.scatter(value, y, s=28 if _is_exit(row) else 19,
                                     marker="x" if _is_exit(row) else "o",
                                     color=color, alpha=0.65, linewidths=1.15, zorder=2)
            if values:
                mean = float(np.mean(values))
                overview.scatter(mean, y, s=43, marker="D", color=color,
                                 edgecolors="white", linewidths=0.5, zorder=3)
            else:
                mean = 0.0  # Position of the missing-data label, never a substituted metric.
            exit_count = sum(_is_exit(row) for row in rows)
            missing = len(rows) - len(values)
            notes = []
            if exit_count:
                notes.append(f"{exit_count}/{len(rows)} exits")
            if missing:
                notes.append(f"{missing} missing")
                missing_notes.append((scenario, mode, missing))
            if notes:
                overview.text(mean + x_max * 0.025, y, "; ".join(notes), fontsize=7.6,
                              color=color, va="center", ha="left")
    overview.set_yticks(range(len(scenarios)), [SCENARIO_LABELS.get(name, name) for name in scenarios])
    overview.set_ylim(len(scenarios) - 0.48, -0.53)
    overview.set_xlim(0, x_max)
    overview.set_xlabel("Recorded-trajectory full-target RMSE (rad)", fontsize=10)
    overview.set_title("All scenarios: per-seed dots and mean diamonds", loc="left", fontsize=11.5, weight="bold")
    overview.grid(axis="x", alpha=0.22)
    overview.tick_params(axis="y", labelsize=10)

    def draw_trajectory(axis, scenario, modes):
        for mode in modes:
            index = MODES.index(mode)
            record = indexed[(scenario, selected_seed, mode)]
            rows = sorted(trace[(scenario, mode)], key=lambda row: int(row["step"]))
            if len(rows) != int(record["executed_steps"]):
                raise ValueError(f"trace/record step mismatch: {scenario}, {mode}")
            times = [0.0]
            errors = [_optional_finite(record["initial_full_target_rmse"], "initial_full_target_rmse")]
            for row in rows:
                times.append(float(row["physical_seconds"]))
                errors.append(_optional_finite(row["full_target_rmse"], "full_target_rmse"))
            # Matplotlib treats explicit missing values as gaps; never replace them with zero.
            axis.plot(times, errors, color=COLORS[index], linestyle=STYLES[index], linewidth=1.7)
            if _is_exit(record) and errors[-1] is not None:
                axis.scatter(times[-1], errors[-1], marker="x", color=COLORS[index], s=46, zorder=4)
        axis.grid(alpha=0.2)
        axis.set_ylabel("Per-step target RMSE (rad)", fontsize=10)

    draw_trajectory(constant, selected[0], MODES)
    constant.set_title("Constant delay 0.60 s: seed 10", loc="left", fontsize=11.5, weight="bold")
    constant.tick_params(axis="x", labelbottom=False)
    constant.text(0.98, 0.95, "x marks an early-exit endpoint", transform=constant.transAxes,
                  fontsize=8, color="#555555", va="top", ha="right")
    draw_trajectory(jump, selected[1], ("immediate_h50", "history_h50"))
    change = next(item["plant"]["change_step"] for item in config["scenarios"]
                  if item["plant"]["name"] == selected[1])
    jump.axvline(change * dt, color="#555555", linestyle=":", linewidth=1.2)
    jump.set_title("Delay 0.30 -> 0.60 s: H50, seed 10", loc="left", fontsize=11.5, weight="bold")
    jump.text(0.98, 0.95, "History assumption stays at 0.30 s", transform=jump.transAxes,
              fontsize=8, color="#555555", va="top", ha="right")
    jump.set_xlabel("Simulation time (s)", fontsize=10)
    jump.set_xlim(0, config["config"]["rollout_steps"] * dt)

    handles = [Line2D([0], [0], color=color, linestyle=style, linewidth=2, marker="D", markersize=4,
                      label=label) for color, style, label in zip(COLORS, STYLES, LABELS)]
    fig.legend(handles=handles, loc="lower center", bbox_to_anchor=(0.55, 0.093),
               ncol=5, fontsize=10, frameon=False, columnspacing=1.6, handlelength=2.7)
    fig.suptitle("CPU command-history and horizon diagnostics", fontsize=17, weight="bold", y=0.965)
    fig.text(0.55, 0.911, "Known initial delay supplied as prior | 0 parameter updates | Fixed full permissions",
             ha="center", fontsize=10.5, color="#444444")
    fig.text(0.55, 0.064, "Early-exit RMSE uses recorded steps only; exit counts remain explicit. Missing metrics remain missing.",
             ha="center", fontsize=9.5, color="#444444")
    fig.text(0.55, 0.033, "Stable supported two-joint fixture; no learned-delay, G1, or real-robot claim.",
             ha="center", fontsize=9.5, color="#444444")
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=160)
    plt.close(fig)
    return {"output": str(output), "records": len(records), "missing_metric_groups": missing_notes}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    print(json.dumps(plot_summary(args.report, args.output or args.report.parent / "summary.png"), indent=2))


if __name__ == "__main__":
    main()
