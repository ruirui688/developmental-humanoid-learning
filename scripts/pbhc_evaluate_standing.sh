#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 4 || $# -gt 7 ]]; then
    echo "usage: $0 CHECKPOINT [NUM_ENVS] [HORIZON_STEPS] [SEED] [VELOCITY_MIN] [VELOCITY_MAX] [ACTION_SMOOTHING_ALPHA]" >&2
    exit 2
fi

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
pbhc_root="${PBHC_ROOT:-${repo_root}/external/PBHC}"
pbhc_prefix="${PBHC_CONDA_PREFIX:-${repo_root}/external/conda/pbhc}"
cache_root="${PBHC_CACHE_ROOT:-${repo_root}/external/cache}"
python_bin="${pbhc_prefix}/bin/python"

checkpoint="$(realpath "$1")"
num_envs="${2:-8192}"
horizon_steps="${3:-1000}"
evaluation_seed="$4"
velocity_min="${5:--0.05}"
velocity_max="${6:-0.05}"
action_smoothing_alpha="${7:-0.50}"
source_revision="$(git -C "${repo_root}" rev-parse HEAD)"
if [[ -n "$(git -C "${repo_root}" status --short)" ]]; then
    source_revision="${source_revision}+dirty"
fi
pbhc_revision="$(git -C "${pbhc_root}" rev-parse HEAD)"

if [[ ! -f "${checkpoint}" ]]; then
    echo "checkpoint not found: ${checkpoint}" >&2
    exit 2
fi
if [[ ! -x "${python_bin}" ]]; then
    echo "PBHC Python not found: ${python_bin}" >&2
    exit 2
fi

mkdir -p "${cache_root}/torch_extensions"
cd "${pbhc_root}"
PATH="${pbhc_prefix}/bin:/usr/bin:/bin" \
LD_LIBRARY_PATH="${pbhc_prefix}/lib" \
PYTHONPATH="${repo_root}/src${PYTHONPATH:+:${PYTHONPATH}}" \
TORCH_EXTENSIONS_DIR="${cache_root}/torch_extensions" \
WANDB_MODE=disabled \
"${python_bin}" humanoidverse/train_agent.py \
    "hydra.searchpath=[file://${repo_root}/configs/pbhc]" \
    +exp=dhl_developmental \
    project_name=DHL_G1_Evaluation \
    experiment_name=frozen_standing \
    num_envs="${num_envs}" \
    seed=7 \
    +device=cuda:0 \
    headless=true \
    use_wandb=false \
    checkpoint="${checkpoint}" \
    algo.config.load_optimizer=false \
    algo.config.competence_evaluation.enabled=false \
    algo.config.evaluation_only.enabled=true \
    algo.config.evaluation_only.seed="${evaluation_seed}" \
    algo.config.evaluation_only.episode_banks=1 \
    algo.config.evaluation_only.horizon_steps="${horizon_steps}" \
    algo.config.evaluation_only.checkpoint_path="${checkpoint}" \
    algo.config.evaluation_only.source_revision="${source_revision}" \
    algo.config.evaluation_only.pbhc_revision="${pbhc_revision}" \
    env.config.max_episode_length_s=1000.0 \
    maturation.mode=adaptive \
    maturation.gate.enabled=true \
    maturation.action_smoothing_alpha="${action_smoothing_alpha}" \
    "maturation.reset_root_velocity_range=[${velocity_min},${velocity_max}]"
