[English](README.md) | 中文

# benchmark — `gap benchmark` 的配置

> **内容：** 网格评测配置：1 格冒烟 → 位姿变化网格 → 发布门槛 · **需要：** `grocery`（CUDA）+ LLM 密钥 · **耗时：** 数分钟到数小时

从 1 格冒烟到发布验收门槛的评测配置。框架把一份配置展开成单元格网格（`模式 × 任务族 × 变化 × 任务编号 × 种子`），跑每个格子（生成和/或执行），并把 `summary.json` / `summary.tsv` 以及汇总视频写到配置的 `output_dir` 下。

## 运行

```bash
CUDA_HOME=/usr/local/cuda uv sync --extra grocery   # 这些评测任务族用 CuRobo 规划
export OPENROUTER_API_KEY=...                       # 代码生成 + VLM（或 vertex）
MUJOCO_GL=egl uv run gap benchmark examples/benchmark/smoke.yaml
```

| 配置 | 是什么 |
|---|---|
| [smoke.yaml](smoke.yaml) | 1 个任务 × 1 个种子的健全性检查（约数分钟） |
| [posvar.yaml](posvar.yaml) | 在位姿变化任务族上铺开的网格 |
| [grocery_acceptance_smoke.yaml](grocery_acceptance_smoke.yaml) | 门槛的 20 次试验冒烟（任务 0–1） |
| [grocery_acceptance.yaml](grocery_acceptance.yaml) | **发布门槛**：完整验收网格，由配置的 `gate_threshold` 把关 |

## 门槛语义

```bash
MUJOCO_GL=egl uv run gap benchmark examples/benchmark/grocery_acceptance.yaml --gate --resume
```

- `--gate` 在 `success_rate` 低于配置的 `gate_threshold` 时以非零状态退出。可以直接接进 CI 或发布检查清单。
- `--resume` 跳过 `output_dir` 里已有结果的格子，并重建汇总。一次很长的验收运行中断后可以接着跑。
- 格子在并行工作进程里跑。用 `GAP_MUJOCO_EGL_DEVICES=0,1,2` 把 EGL 渲染摊到多张 GPU 上，并在配置里限制工作进程数。

## 读结果

```bash
uv run gap viz            # 浏览每个格子的轨迹和视频
column -ts$'\t' outputs/<run>/summary.tsv
```

`summary.json` 带按任务透视的数据（每个任务、每个种子的成功率和完成率），方便程序读取。

## 接下来

- [grocery_fulfillment](../grocery_fulfillment/) — 验收任务族实际做什么，以及一份已提交的生成图。
