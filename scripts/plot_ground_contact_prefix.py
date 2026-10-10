"""Static CPU figure for fixed contact/prefix diagnostics; no model fitting."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


SETTINGS = (("baseline", 0), ("baseline", 100), ("compliant", 0), ("compliant", 100))
LABELS = ("Baseline\nNo prefix", "Baseline\n2 s prefix", "Compliant\nNo prefix", "Compliant\n2 s prefix")
COLORS = ("#276e9a", "#78a5bd", "#bf6828", "#dda66c")
POSES = ("supine", "prone", "left_side", "right_side")
MARKERS = ("o", "s", "^", "D")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--profile", type=Path, help="Optional analysis JSON outside the archive")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.resolve().is_relative_to(args.archive.resolve()):
        parser.error("figure output must be outside the read-only input archive")
    if args.output.exists():
        parser.error("output already exists; preserve the previous figure")
    profile_path = args.profile or args.archive / "contact_prefix_profile.json"
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    trials = [trial for trial in profile["trials"] if trial["metrics_available"]]
    pairs = [pair for pair in profile["paired_active_responses"] if pair["complete"]]
    shared = profile["shared_active_steps"]
    planned_seconds = profile["planned_control_steps_per_trial"] * profile["nominal_control_dt_seconds"]
    case_count = len({(trial["pose"], trial["seed"]) for trial in profile["trials"]})
    fig, axes = plt.subplots(2, 3, figsize=(19, 10))
    for index, (setting, color) in enumerate(zip(SETTINGS, COLORS)):
        selected = [trial for trial in trials if (trial["contact_profile"], trial["prefix_steps"]) == setting]
        for mode, offset, fill, label in (("zero_torque", -.10, "none", "Zero torque"),
                                           ("smooth_random", .10, color, "Smooth random")):
            group = [trial for trial in selected if trial["mode"] == mode]
            for trial in group:
                pose_index = POSES.index(trial["pose"])
                jitter = (pose_index * 3 + trial["seed"] - 5.5) * .009
                axes[0, 0].scatter(index + offset + jitter,
                                  trial["whole_trial"]["peak_ground_normal_force_n"],
                                  marker=MARKERS[pose_index], facecolors=fill, edgecolors=color, s=34,
                                  label=label if index == 0 and trial is group[0] else None)
                axes[0, 2].scatter(index + offset + jitter,
                                  1000 * trial["whole_trial"]["minimum_contact_distance_m"],
                                  marker=MARKERS[pose_index], facecolors=fill, edgecolors=color, s=34)
        response = [pair for pair in pairs if (pair["contact_profile"], pair["prefix_steps"]) == setting]
        for pair in response:
            pose_index = POSES.index(pair["pose"])
            jitter = (pose_index * 3 + pair["seed"] - 5.5) * .021
            axes[0, 1].scatter(index + jitter,
                              pair["native_position_trajectory_difference_rms_rad_all_joints"],
                              marker=MARKERS[pose_index], color=color, s=37)
    for axis in axes[0]:
        axis.set_xticks(range(4), LABELS)
        axis.set_xlim(-.45, 3.45)
        axis.grid(axis="y", alpha=.2)
        axis.set_axisbelow(True)
    axes[0, 0].set(ylabel="Peak sampled ground normal force (N)",
                   title=f"All pose / seed / mode runs, whole {planned_seconds:g} s budget\nOpen symbols: passive zero-torque control")
    axes[0, 0].legend(fontsize=8)
    axes[0, 1].set(ylabel="Paired encoder trajectory difference RMS (rad)",
                   title=f"Smooth random versus zero torque\nFirst {shared} active commands, {case_count} pose / seed cases")
    axes[0, 2].set(ylabel="Minimum sampled contact distance (mm)",
                   title="Soft-contact cost: deeper geometric overlap\nWhole budget; includes ground and self-contacts")
    axes[0, 2].axhline(0, color="#555555", linewidth=.8, alpha=.5)
    heat = np.full((4, 8), np.nan)
    for index, setting in enumerate(SETTINGS):
        selected = [trial for trial in trials if (trial["contact_profile"], trial["prefix_steps"]) == setting
                    and trial["mode"] == "smooth_random" and trial["shared_active_window"]["complete"]]
        if selected:
            numerator = np.array([trial["shared_active_window"]["action_metrics"]["blocked_nonzero_request_substeps_per_joint"]
                                  for trial in selected], dtype=float)
            denominator = np.array([trial["shared_active_window"]["action_metrics"]["nonzero_requested_substeps_per_joint"]
                                    for trial in selected], dtype=float)
            total_denominator = np.sum(denominator, axis=0)
            heat[index] = np.divide(np.sum(numerator, axis=0), total_denominator,
                                    out=np.full(8, np.nan), where=total_denominator != 0)
    image = axes[1, 0].imshow(np.ma.masked_invalid(heat), vmin=0, vmax=1, cmap="YlOrRd", aspect="auto")
    axes[1, 0].set_xticks(range(8), ["L sh", "L el", "R sh", "R el", "L hip", "L knee", "R hip", "R knee"], rotation=35)
    axes[1, 0].set_yticks(range(4), [label.replace("\n", " / ") for label in LABELS])
    axes[1, 0].set_title(f"Pooled blocked / nonzero requested substeps\nFirst {shared} active commands, smooth random only")
    for (row, column), value in np.ndenumerate(heat):
        if np.isfinite(value):
            axes[1, 0].text(column, row, f"{100 * value:.0f}%", ha="center", va="center", fontsize=8,
                            color="white" if value > .6 else "black")
    fig.colorbar(image, ax=axes[1, 0], fraction=.035, pad=.02, label="Blocked fraction")
    for profile_name, color in (("baseline", COLORS[0]), ("compliant", COLORS[2])):
        # Before active commands, both modes share the same state; show one
        # mode so duplicated prefix endpoints do not suggest extra evidence.
        group = [trial for trial in trials if trial["contact_profile"] == profile_name
                 and trial["prefix_steps"] == 100 and trial["mode"] == "zero_torque"
                 and trial["prefix_endpoint"]["available"]]
        for trial in group:
            endpoint = trial["prefix_endpoint"]
            axes[1, 1].scatter(endpoint["maximum_joint_speed_rad_s"], endpoint["kinetic_energy_j"],
                              marker=MARKERS[POSES.index(trial["pose"])], color=color, s=43,
                              label=profile_name if trial is group[0] else None)
    axes[1, 1].scatter([0], [0], marker="x", color="black", s=50, label="No-prefix reset (declared qvel=0)")
    axes[1, 1].set(xlabel="Maximum native joint speed at prefix end (rad/s)",
                   ylabel="Kinetic energy at prefix end (J)",
                   title="Fixed 2 s passive prefix endpoints\nOne copy per pose / seed; no stability threshold")
    axes[1, 1].legend(fontsize=8)
    axes[1, 1].grid(alpha=.2)
    axes[1, 2].axis("off")
    total_steps = profile["planned_control_steps_per_trial"]
    axes[1, 2].set_title("Interaction budget and interpretation", loc="left", fontsize=13)
    axes[1, 2].text(0, .95,
                    f"Every run: {total_steps} total control steps = {planned_seconds:g} s\n\n"
                    f"No prefix: 0 passive + {total_steps} active steps\n"
                    f"2 s prefix: 100 passive + {total_steps - 100} active steps\n\n"
                    f"Matched response: first {shared} active commands\n"
                    "All prefix interactions stay in the total budget.\n\n"
                    "A lower force peak can accompany deeper overlap.\n"
                    "Negative contact distance means geometric overlap.\n\n"
                    "Contact and passive prefix are fixed conditions.\n"
                    "Body model, policy and gate updates remain zero.\n\n"
                    "Two zero-torque prefix labels repeat trajectories;\n"
                    "both runs are charged, without adding independent seeds.\n\n"
                    "All per-seed values remain in the analysis JSON.",
                    transform=axes[1, 2].transAxes, ha="left", va="top", fontsize=10.5,
                    linespacing=1.25)
    unavailable = len(profile["metrics_unavailable_trial_ids"])
    stopped = len(profile["terminated_trial_ids"])
    fig.suptitle("Fixed contact / zero-command prefix / CPU only / zero learning updates", fontsize=14)
    fig.text(.5, .018,
             f"Pose markers: circle=supine, square=prone, triangle=left side, diamond=right side. "
             f"Unavailable trials={unavailable}; stopped={stopped}.\n"
             "Contact and passive-prefix changes are environment/initial conditions; paired differences are descriptive. "
             "2 ms force samples do not establish hardware safety.", ha="center", fontsize=8)
    fig.tight_layout(rect=(0, .065, 1, .96))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.output, dpi=150, metadata={"Description": json.dumps({
        "plot_script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "analysis_input_sha256": hashlib.sha256(profile_path.read_bytes()).hexdigest(),
        "analysis_parameter_updates": 0,
    })})
    plt.close(fig)


if __name__ == "__main__":
    main()
