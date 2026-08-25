#!/usr/bin/env python3
"""Validate PBHC's canonical 23-DoF G1 config against its URDF.

Run this with the PBHC environment because PBHC uses PyYAML for Hydra configs.
The script deliberately reads the upstream checkout instead of copying its mapping.
"""

from __future__ import annotations

import argparse
import math
import xml.etree.ElementTree as ET
from pathlib import Path

import yaml


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--pbhc-root",
        type=Path,
        default=Path("external/PBHC"),
        help="Path to the pinned PBHC checkout.",
    )
    return parser.parse_args()


def _require_equal(label: str, actual: object, expected: object) -> None:
    if actual != expected:
        raise AssertionError(f"{label} mismatch:\nactual={actual}\nexpected={expected}")


def main() -> None:
    root = _parse_args().pbhc_root.resolve()
    config_path = root / "humanoidverse/config/robot/g1/g1_23dof_lock_wrist.yaml"
    urdf_path = root / "description/robots/g1/g1_23dof_lock_wrist.urdf"

    if not config_path.is_file() or not urdf_path.is_file():
        raise FileNotFoundError(f"PBHC G1 files not found under {root}")

    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))["robot"]
    urdf = ET.parse(urdf_path)
    movable_joints = [
        joint for joint in urdf.findall(".//joint") if joint.attrib.get("type") != "fixed"
    ]
    urdf_joint_names = [joint.attrib["name"] for joint in movable_joints]
    urdf_link_names = [link.attrib["name"] for link in urdf.findall(".//link")]

    _require_equal("joint order", config["dof_names"], urdf_joint_names)
    _require_equal("action dimension", config["actions_dim"], len(urdf_joint_names))
    _require_equal("DOF observation size", config["dof_obs_size"], len(urdf_joint_names))
    _require_equal("configured body count", config["num_bodies"], len(config["body_names"]))
    _require_equal(
        "configured body order in URDF",
        [name for name in urdf_link_names if name in config["body_names"]],
        config["body_names"],
    )

    limit_fields = (
        ("lower", "dof_pos_lower_limit_list"),
        ("upper", "dof_pos_upper_limit_list"),
        ("velocity", "dof_vel_limit_list"),
        ("effort", "dof_effort_limit_list"),
    )
    for urdf_field, config_field in limit_fields:
        configured = config[config_field]
        _require_equal(f"{config_field} length", len(configured), len(movable_joints))
        for index, (joint, configured_value) in enumerate(zip(movable_joints, configured)):
            limit = joint.find("limit")
            if limit is None or urdf_field not in limit.attrib:
                raise AssertionError(f"{joint.attrib['name']} has no {urdf_field} limit")
            urdf_value = float(limit.attrib[urdf_field])
            if not math.isclose(urdf_value, float(configured_value), rel_tol=0.0, abs_tol=1e-5):
                raise AssertionError(
                    f"{config_field}[{index}] ({joint.attrib['name']}): "
                    f"config={configured_value}, URDF={urdf_value}"
                )

    contact_bodies = set(config["contact_bodies"])
    body_names = set(config["body_names"])
    if not contact_bodies or not contact_bodies <= body_names:
        raise AssertionError("contact_bodies must be a non-empty subset of body_names")

    print(f"PBHC root: {root}")
    print("G1 mapping valid: 23 actions, 23 movable joints, 24 collapsed bodies")
    print(f"Contact bodies: {', '.join(config['contact_bodies'])}")


if __name__ == "__main__":
    main()
