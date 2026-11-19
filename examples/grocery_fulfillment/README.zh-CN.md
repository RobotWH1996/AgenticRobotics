[English](README.md) | 中文

# grocery_fulfillment — 验收评测

> **内容：** 旗舰验收任务族：每个任务的图由 LLM 生成，没有手写的 · **需要：** `grocery`（CUDA）+ LLM 密钥 · **耗时：** 数分钟（冒烟）

旗舰任务族：抓起一件*被描述的*杂货，放进篮子，并处在变分自动化评测烘焙好的位姿 / 排列 / 换篮子变化之下。图是 `gap.agent.generate` **按任务生成**的（`llm_generation` 模式），没有手写的。完整配置同时充当发布门槛：`--gate` 让某个格子低于配置的 `gate_threshold` 时，`gap benchmark` 以非零状态退出。

## 运行

```bash
# 加上 --extra vertex：下面的配置钉死了 vertex 提供商，
# 它的 SDK（google-genai）在引擎侧，用于图生成
CUDA_HOME=/usr/local/cuda uv sync --extra grocery --extra vertex
uv run gap skills check --download

# 20 次试验的冒烟（任务 0–1）
MUJOCO_GL=egl uv run gap benchmark examples/benchmark/grocery_acceptance_smoke.yaml --gate

# 完整验收门槛（可中断；--resume 接着跑）
MUJOCO_GL=egl uv run gap benchmark examples/benchmark/grocery_acceptance.yaml --gate --resume
```

图生成还需要一份 LLM 凭证。这些配置钉的是 Vertex 加 `gemini-3.1-pro-preview`；改配置里的 `llm:` 块就可以用 `openrouter`。

## 配方（原样移植）

[`examples/benchmark/grocery_acceptance.yaml`](../benchmark/grocery_acceptance.yaml)：每个任务一个套件，带按任务整理的物体描述（`target` / `expected_label` / `shape_hint`。这些提示会附到代码生成的提示词上，是承重的），每次试验的超时给得很宽（扁平盒子的抓取规划在目标集规划器退回到逐位姿迭代时，确实会跑很久），并打开视频。

## 示例图

[`sample_generated_graph/`](sample_generated_graph) 是任务 0 的一份 `gap.agent.generate` 输出（「拿起蓝黄相间的字母汤罐，放进篮子」）：协调者把任务拆成两个 `perceiving-objects` 子图（先目标，再篮子）→ `grasping-with-planner` → `transporting-objects`；子图智能体编写了内部状态机和脚本；检查点智能体挂上了 `validate=True` 的后置条件。`gap.execute(checkpoints="warn"|"raise")` 在每个子图出口对照仿真真值强制执行：感知包围盒与特权物体位姿的误差在容差内、抓取后被夹住、放下位姿在篮子腔内、并在篮子里停稳。

它的抓取子图（`grasp_sg`）带着和 [grocery_packing](../grocery_packing/) 的 `grasp_move.py` 相同的调好的抓取配方，收成单物体情形（`scripts/grasp_sg/grasp_descend_linear.py`）：

```
open → top_down_grasp_candidates → grasp_descend_linear → observe → close
```

- **快路径（默认）：** 升起，在物体上方做 XY 平移（转到抓取偏航），再用 `curobo.plan_directed_linear` 做**锁轴的垂直 Z 下降**（`allowed_axes=["Z"]`，`orientation_mode="LOCK"`）：纯垂直，没有横向漂移。和规划器的目标集不同，它也能抓住*扁平*物体（例如奶油芝士盒），只要直接降到上面。
- **回退：** 如果直线求解不可行（物体在远边，固定的自上而下腕部没有逆解），就交给有碰撞感知的 CuRobo 规划器，在整把候选扇面里找一个可达、无碰撞的腕部位姿。
- **深度：** 在感知到的顶部附近浅抓，下限停在物体底部稍上方，手指不会撞桌子。扁平盒子仍然能在中等高度真正夹住，高纸盒不会被手掌掀翻。

可以直接跑，不必再生成（仍然需要感知 VLM 的凭证）：

```bash
MUJOCO_GL=egl uv run gap run examples/grocery_fulfillment/sample_generated_graph \
  --sim libero_object_all_variance/0 --checkpoints warn
```

一次干净的运行会感知到罐子和篮子，抓住，放下，并通过全部七条检查点。一次会话的第一次运行要付一次性代价：视觉模型冷加载，加上 CuRobo 的 CUDA 核 JIT（约 40 秒）。所以在每个节点的计时稳定之前，要多留几分钟。

## 接下来

- [benchmark](../benchmark/) — 全部评测配置、门槛语义，以及续跑行为。
- [grocery_packing](../grocery_packing/) — 把所有东西都装完的循环，这个任务族与它共用抓取/搬运配方。
- [generate_a_graph](../generate_a_graph/) — 这个评测在网格规模上驱动的生成流水线。
