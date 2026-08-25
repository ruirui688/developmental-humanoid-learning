#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
pbhc_root="${PBHC_ROOT:-${repo_root}/external/PBHC}"
pbhc_prefix="${PBHC_CONDA_PREFIX:-${repo_root}/external/conda/pbhc}"
cache_root="${PBHC_CACHE_ROOT:-${repo_root}/external/cache}"

python_bin="${pbhc_prefix}/bin/python"
if [[ ! -x "${python_bin}" ]]; then
    echo "PBHC Python not found: ${python_bin}" >&2
    exit 2
fi
if [[ ! -f "${pbhc_root}/humanoidverse/train_agent.py" ]]; then
    echo "PBHC checkout not found: ${pbhc_root}" >&2
    exit 2
fi

mkdir -p "${cache_root}/torch_extensions"

"${python_bin}" "${repo_root}/scripts/validate_pbhc_g1.py" --pbhc-root "${pbhc_root}"

cd "${pbhc_root}"
PATH="${pbhc_prefix}/bin:/usr/bin:/bin" \
LD_LIBRARY_PATH="${pbhc_prefix}/lib" \
TORCH_EXTENSIONS_DIR="${cache_root}/torch_extensions" \
WANDB_MODE=disabled \
"${python_bin}" humanoidverse/train_agent.py \
    +simulator=isaacgym \
    +exp=motion_tracking \
    +terrain=terrain_locomotion_plane \
    project_name=DHL_PBHC_Smoke \
    num_envs=1 \
    +obs=motion_tracking/main \
    +robot=g1/g1_23dof_lock_wrist \
    +domain_rand=dr_nil \
    +rewards=motion_tracking/main \
    experiment_name=smoke \
    robot.motion.motion_file=example/motion_data/Horse-stance_pose.pkl \
    seed=1 \
    +device=cuda:0 \
    headless=True \
    use_wandb=False \
    algo.config.num_learning_iterations=1 \
    algo.config.save_interval=1
