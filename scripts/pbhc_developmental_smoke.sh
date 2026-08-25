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
PYTHONPATH="${repo_root}/src${PYTHONPATH:+:${PYTHONPATH}}" \
TORCH_EXTENSIONS_DIR="${cache_root}/torch_extensions" \
WANDB_MODE=disabled \
"${python_bin}" humanoidverse/train_agent.py \
    "hydra.searchpath=[file://${repo_root}/configs/pbhc]" \
    +exp=dhl_developmental \
    project_name=DHL_PBHC_Smoke \
    experiment_name=developmental_smoke \
    num_envs=1 \
    seed=1 \
    +device=cuda:0 \
    headless=true \
    use_wandb=false \
    algo.config.num_steps_per_env=24 \
    algo.config.num_learning_epochs=1 \
    algo.config.num_mini_batches=1 \
    algo.config.num_learning_iterations=1 \
    algo.config.save_interval=1 \
    "$@"
