# PBHC 接入与本机复现记录

本项目不另写一套 G1 仿真环境。近期 G1 工作以 PBHC 的 HumanoidVerse、G1
资产、Hydra 配置和训练入口为上游底座，本仓库只保存薄接入脚本、验证和研究组件。

## 已固定的上游

- PBHC commit：`ffac5cded61fe78b39b051f09ac2ed0f6a1ccea0`；
- PBHC 许可证：仓库 `LICENSE` 与 README 为 CC BY-NC 4.0；`setup.py` 中的
  MIT 字段与之冲突，在上游澄清前按更明确的仓库级 CC BY-NC 4.0 处理；
- canonical G1 URDF SHA-256：
  `3ed3fc32b66e6389667f780726cdb9ee044e2d579638347a1612d130c26ae546`；
- canonical G1 MuJoCo XML SHA-256：
  `9af12a57f88f0bcf1eeab485046165080f0ad58141fd2266cbef4ad9f7c5274f`；
- NVIDIA Isaac Gym：Preview 4，下载包 SHA-256 为
  `c51d77ac1144b91b356f439c7313d8d59468147e37187ebffe7cdbc3154fdb8f`；
- 本机 PBHC Python：3.8.20；PyTorch：2.4.1+cu121；GPU：RTX 4090；
- 本地路径均位于被 Git 忽略的 `external/`，不提交上游源码、环境、缓存、动作或权重。

机器可读来源记录见 `provenance/external_sources.yaml`。

## 启动约定

本机的全局 `LD_LIBRARY_PATH` 含 CUDA 12.1 路径，可能覆盖 pip Torch 自带的
CUDA 库。PBHC 运行脚本只给运行进程设置 Conda prefix 的 `lib`，不修改用户的
shell、驱动或 `base` 环境。默认路径为：

```text
external/PBHC
external/isaacgym
external/conda/pbhc
external/cache
```

路径不同时可通过 `PBHC_ROOT`、`PBHC_CONDA_PREFIX` 和 `PBHC_CACHE_ROOT`
覆盖。

## 验证

CPU 静态 mapping 验证读取 PBHC 自身 YAML 和 URDF，不复制关节表：

```bash
external/conda/pbhc/bin/python scripts/validate_pbhc_g1.py
```

完整 smoke test 直接调用 PBHC 原始训练入口，只训练一个环境、一个 PPO iteration：

```bash
bash scripts/pbhc_smoke.sh
```

纯发育式 G1 链路使用本仓库的 Hydra overlay 和算法扩展，不加载动作文件：

```bash
bash scripts/pbhc_developmental_smoke.sh
```

2026-08-25 的首次结果：

- Isaac Gym GPU PhysX 与 GPU tensor pipeline 正常；
- PBHC 的 23 个 action 与 URDF 23 个非固定关节名称、顺序和限位一致；
- 固定关节折叠后 24 个 rigid body 与 PBHC 配置一致；
- Horse-stance 示例动作共 210 帧、6.967 秒，成功载入 GPU；
- 1 env × 24 steps × 1 PPO iteration 完成，保存 `model_0.pt`；
- 首次单环境 smoke 的 collection + learning 用时约 0.39 秒，不能作为正式吞吐基准。

2026-08-26 的纯发育式 smoke 进一步验证：

- 最终配置中的 `robot.motion.motion_file` 为 `null`；
- `DevelopmentalG1Env` 的阶段 0 开放 11/23 个残差动作，探索缩放为 0.25；
- actor 只读取 IMU 类信号、关节状态、执行动作历史和成熟状态；
- 52 维 Body Schema 辅助头完成一次 done-masked 更新；
- checkpoint 同时包含 Body Schema 参数和成熟控制器状态；
- 1 env × 24 steps × 1 Developmental PPO iteration 在 GPU 上完成。

PBHC 会警告 30 个 rigid shapes 与 24 个 bodies 数量不同。这是多个 collision
shape 归属同一 rigid body；其代码会给全部 30 个 shape 设置摩擦，但当前只把前
24 个 shape 写入摩擦诊断 tensor。该警告不改变按 body 返回的 contact-force tensor，
但在正式启用摩擦随机化统计前应修正诊断记录，不能把两类数量当作一一对应。

## 科研边界

PBHC 的机器人资产和仿真框架可以作为所有实验组共享的环境基础。PBHC 示例动作、
人体动作处理、教师策略和预训练 checkpoint 属于额外任务先验：使用它们的 smoke
或强基线必须归入 human-prior / teacher-assisted 条件，不能作为 pure developmental
结果。当前 smoke 使用了 Horse-stance 动作，只验证软件链路，不是本项目站立基线结果。
`pbhc_developmental_smoke.sh` 不使用该动作，才是 pure-developmental 软件链路验证；
它仍然不是收敛结果或正式实验结果。
