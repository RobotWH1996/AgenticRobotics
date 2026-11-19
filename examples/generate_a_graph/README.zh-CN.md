[English](README.md) | 中文

# generate_a_graph — 从指令到校验过的工作流

> **内容：** 指令 → 校验过的工作流目录；命令行 + Python，全部提供商 · **需要：** `uv sync` + LLM 密钥 · **耗时：** 数分钟

这是标准的生成流程：一句自然语言指令经过 LLM 智能体流水线（协调者 → 每个子图的智能体 → 检查点智能体 → 校验 + 脚本修复循环），出来的是一份带类型、经过校验的工作流目录。这和 [gap.builder](../build_a_graph/) 手写的、`gap run` 执行的是**同一份产物**。

## 命令行

生成只需要引擎（`uv sync`）、本仓库旁边的 open-robot-skills 检出，以及一份 LLM 凭证：

```bash
export OPENROUTER_API_KEY=...   # 默认提供商；见下文「提供商」

uv run gap generate "pick up the alphabet soup can and place it in the basket" --out my_graph
```

open-robot-skills 的检出目录会自动发现（`$GAP_SKILLS_PATH`，或与 graph-as-policy 并列的那个检出）；传入 `--skills /path/to/open-robot-skills` 可覆盖。`--provider`、`--model` 和 `--config <yaml>` 用来调节流水线。

## Python

```python
import gap

graph = gap.agent.generate_sync(
    "pick up the alphabet soup can and place it in the basket",
    out_dir="my_graph",          # 省略 skills= 则自动发现
)
print(graph)                     # 图，以终端文本呈现（见下）
print(graph.path)                # 写出的工作流文件夹
print(sorted(graph.code))        # 每一个生成的源文件
```

`print(graph)` 用方框字符把工作流画出来，和 `gap generate` 打印的是同一份输出。对已提交的 [sample_generated_graph](../grocery_fulfillment/sample_generated_graph) 来说是：

```text
task_00
Pick the blue and yellow alphabet soup can and place it in the basket.

START
  │
  ▼
┌─ target_sg ───────────────────────────────────────── perceiving-objects ─┐
│ observe ─▶ perceive ─▶ filter_obb                                        │
└──────────────────────────────────────────────────────────────────────────┘
  │ found                                                    abort ▶ ✗ abort
  ▼
┌─ container_sg ────────────────────────────────────── perceiving-objects ─┐
│ observe ─▶ perceive ─▶ filter_obb                                        │
└──────────────────────────────────────────────────────────────────────────┘
  │ found                                                    abort ▶ ✗ abort
  ▼
┌─ grasp_sg ─────────────────────────────────────── grasping-with-planner ─┐
│ open ─▶ compute_grasp ─▶ approach ─▶ observe ─▶ build_world ─▶ plan      │
│   ─▶ execute ─▶ close                                                    │
└──────────────────────────────────────────────────────────────────────────┘
  │ grasped                                                  abort ▶ ✗ abort
  ▼
┌─ transport_sg ──────────────────────────────────── transporting-objects ─┐
│ compute_drop ─▶ move_above ─▶ release                                    │
└──────────────────────────────────────────────────────────────────────────┘
  │ placed ▶ ✓ done                                          abort ▶ ✗ abort

✓ done (success)   ✗ abort (failure, recovery: open_gripper, go_home)
```

（`gap.viz.to_text(workflow)` 对任意工作流字典或目录都这样渲染；`gap.agent.generate` 是异步版本。）[generate.py](generate.py) 用一个小命令行包了这一层：

```bash
uv run python examples/generate_a_graph/generate.py "pick up the milk and put it in the basket"
```

## 输出目录里有什么

```
my_graph/task_00/           # = graph.path
├── workflow.json           # v3 图：顶层有向图 + 每个子图一条
├── scripts/                # 智能体编写的脚本，由 type:script 节点引用
│   ├── perceive_dino_vlm.py
│   ├── plan_grasp.py
│   └── ...
├── checkpoints/            # LLM 为每个子图编写的后置条件旁路文件
│   ├── grasp_sg.py         #   （validate=True 的谓词，在子图出口
│   └── transport_sg.py     #    对照仿真真值强制执行）
├── agent_traces/           # 每个智能体的 LLM 对话记录，用于调试
└── multi_agent_meta.json   # 流水线出处（模型、重试、耗时）
```

`gap.agent.generate_sync` 把这个确切文件夹作为 `graph.path` 返回。[grocery_fulfillment/sample_generated_graph](../grocery_fulfillment/sample_generated_graph) 是一份已提交、未改动的实例。

## 校验并运行结果

```bash
uv run gap run my_graph/task_00 --validate-only           # 结构 + 技能检查
MUJOCO_GL=egl uv run gap run my_graph/task_00 \
  --sim libero_object_all_variance/0                      # 在 LIBERO 上执行
uv run gap viz                                            # 浏览轨迹
```

或者用 Python：`gap.execute(graph.path, gap.connector.sim("libero", task=...))`。

## 提供商

| 提供商 | 配置 |
|---|---|
| `openrouter`（默认） | `export OPENROUTER_API_KEY=...`；默认模型 `gemini-3.1-flash-lite-preview`（用 `--model gemini-3.1-pro-preview` 或 `GAP_LLM_MODEL` 覆盖）。要通过 `--config` YAML 里的 `llm: {provider: openrouter, endpoint: ...}` 指向任何其他 OpenAI 兼容服务器（例如本地 vLLM） |
| `vertex` | `gcloud auth application-default login`，`export GOOGLE_CLOUD_PROJECT=...`（`GOOGLE_CLOUD_REGION` 可选，默认 `global`）；每次调用选择（`--provider vertex`，默认模型 `gemini-3.1-flash-lite-preview`，用 `--model <m>` 覆盖），或每个 shell 设一次（`export GAP_LLM_PROVIDER=vertex GAP_LLM_MODEL=<m>`），并带上 SDK：`uv run --extra vertex gap generate ...`；仅 Gemini 模型 |

每次调用用 `--provider/--model` 选，或者把温度、重试、每个智能体的模型全部钉在一份配置 YAML 里，用 `--config` 传入。

## 评测量级的生成

生成一张图是基本单位；评测框架用同一条流水线扫任务 × 种子的网格。旗舰配方见 [grocery_fulfillment](../grocery_fulfillment/)：对杂货指令做 `gap generate`，覆盖位姿 / 排列 / 换篮子这些变化，并由配置里的 `gate_threshold` 把关。
