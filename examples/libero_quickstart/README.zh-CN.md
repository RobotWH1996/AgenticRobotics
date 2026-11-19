[English](README.md) | 中文

# libero_quickstart — 把汤罐放进篮子

> **内容：** 端到端主示例：真实视觉 → 有向包围盒抓取 → 搬运，并用真值校验 · **需要：** `quickstart` + GPU + LLM 密钥 · **耗时：** 每次试验约 25–55 秒

GaP 的端到端快速开始：一张静态、完整编写好的工作流图。它用真实视觉模型（Grounding DINO + SAM3 + 托管的视觉语言模型）感知目标物体和容器，从融合后的三维有向包围盒推出自上而下的抓取，用直接逆解「先对齐再下降」把物体抓起，放进篮子。仿真器自己的成功条件，以及一条真值检查点 `target_held`，负责验收。

## 运行

在 GaP 检出目录里（open-robot-skills 克隆在旁边）：

```bash
uv sync --extra quickstart            # 引擎 + LIBERO 仿真 + 感知模型
uv run gap skills check --download    # 校验技能包并预取权重（约 3.5 GB）
export OPENROUTER_API_KEY=...          # VLM 提供商，其他选择见下文

MUJOCO_GL=egl uv run gap run examples/libero_quickstart/graph \
  --sim libero_object_all_variance/0
uv run gap viz                        # 浏览录下的试验
```

- open-robot-skills 的检出目录会自动发现（`$GAP_SKILLS_PATH`，或与 graph-as-policy 并列的那个检出）；`--skills PATH` 可覆盖。
- `--validate-only` 只检查图，不执行。
- `--checkpoints warn`（默认）在每个子图之后评测 `graph/checkpoints/` 里的真值后置条件（仅仿真）。`grasp_sg.target_held` 用特权接触信息确认合爪之后夹爪确实夹住了罐子。
- 轨迹（每个节点的输入输出、每一次模型调用、渲染帧）写到 `outputs/run_<时间戳>/`。

## 两种变体

| 图 | 抓取策略 | 需要 |
|---|---|---|
| `graph/`（**默认**） | 直接逆解，先对齐再下降（`grasping-direct-ik` 技能配方）：在包围盒上方的安全高度预先转到抓取偏航，垂直下降，闭合 | `--extra quickstart` |
| `graph_planner/` | 对同一批抓取候选做 CuRobo 目标集规划（`grasping-with-planner`）：从 RGB-D 重建碰撞世界，规划到最佳可达候选的无碰撞关节轨迹 | `--extra grocery`（CUDA 构建，见下文） |

`graph_planner/` 是开发树里 `libero_pro/graph_cartesian_obb` 示例的忠实移植。默认的 `graph/` 只把抓取子图换成不需要规划器的配方，这样快速开始不必安装 CuRobo；感知和搬运两边相同。

`--extra quickstart` 会拉下 torch、torchvision、SAM3（钉死的 git SHA）、Grounding DINO（transformers）和 CPU 几何依赖，版本由提交的 `uv.lock` 钉死。模型权重（`facebook/sam3`、`IDEA-Research/grounding-dino-base`）在首次调用时从 HuggingFace 下载。（pip 的等价安装见[主 README](../../README.md#installation-details)。）

## 可能出什么问题

试验失败时，轨迹几乎总是指向感知，而不是抓取机械本身：

- **目标认错** — DINO + VLM 的消歧选错了检测框，于是抓取干净地执行在错误物体的位置上。表现为 `target_held` 检查点失败。
- **容器感知** — 退化或过大的篮子包围盒把放下位姿带偏，夹着的物体被放在篮子旁边（或篮沿上）。规划器变体用的是同一套感知子图，所以 CuRobo 补不回这些错误。

在一张 A100 上，每次试验的墙钟时间约 25–55 秒（模型在同一进程里跨试验常驻；一次会话的**第一次**试验要付冷加载的代价，端到端可能要几分钟）。

## VLM 提供商

感知流水线用托管的视觉语言模型（`vlm.query`）给 DINO 检测消歧。默认提供商是 OpenRouter：

```bash
export OPENROUTER_API_KEY=...                  # 默认提供商；覆盖模型：
export GAP_VLM_MODEL=gemini-3.1-pro-preview    # 可选（不设 = gemini-3.1-flash-lite-preview）
```

另一种是带应用默认凭证的 Vertex AI（上面那些结果就是用它测的）：

```bash
gcloud auth application-default login
export GAP_VLM_PROVIDER=vertex
export GAP_VLM_PROJECT_ID=<你的项目>
export GAP_VLM_REGION=global
export GAP_VLM_MODEL=gemini-3.1-pro-preview
```

任何 OpenAI 兼容端点（例如本地 vLLM）也可以。把 `GAP_VLM_BASE_URL` 指过去（并设置 `GAP_VLM_MODEL`）。默认的 `openrouter` 提供商说的就是 OpenAI 兼容协议。

## 规划器变体

要跑 `graph_planner/`，先安装 CuRobo（CUDA 构建），再让 `gap run` 指向它：

```bash
CUDA_HOME=/usr/local/cuda uv sync --extra grocery
MUJOCO_GL=egl uv run gap run examples/libero_quickstart/graph_planner \
  --sim libero_object_all_variance/0
```

## 图的结构

```
START → target → container → grasp → transport → done
            ↘ not_found      ↘ failed   ↘ blocked → abort（松开夹爪，回原位）
```

- **target_sg**（`perceiving-objects`）：在一次观测上走一条 DINO 检测 + 成对 VLM 裁剪锦标赛 + SAM3 的感知路径，反投影到世界坐标系点云，再由 `geometry.filter_and_compute_obb` 拟合目标的有向包围盒。
- **container_sg**（同一技能包）：对篮子做 DINO + VLM 感知 → 容器包围盒。
- **grasp_sg**（`graph/` 里是 `grasping-direct-ik`）：`robot.open_gripper` → `geometry.top_down_grasp_candidates(obb)` → 算出包围盒顶面上方 15 厘米的对齐位姿 → `robot.go_to_pose`（在高处转向）→ `robot.go_to_pose` 垂直下降到 `candidates.poses[0]` → `robot.close_gripper`。在 `graph_planner/` 里则是：移到目标上方 → 重新观测 → `geometry.build_world_config`（从 RGB-D 建碰撞场景，用 SAM3 掩码把目标挖掉）→ 对全部候选调用 `curobo.plan_to_grasp_poses` → `robot.execute_trajectory`。
- **transport_sg**（`transporting-objects`）：由容器包围盒算放下位姿 → 抬起并横向经过 `robot.go_to_pose` 路点 → 下降、张开、`robot.go_home`。

`graph*/scripts/` 下的脚本是 open-robot-skills 里标准技能包脚本（`skills/<技能包>/scripts/`）按工作流复制的副本。子图的 `skill:` 字段标出所属技能包，这样脚本按该包的命名空间导入（加载提示词、同级导入）。

## 接下来

- [build_a_graph](../build_a_graph/) — 用 `gap.builder` 用 Python 编写这同一张图。
- [generate_a_graph](../generate_a_graph/) — 让 LLM 流水线根据一条指令编写它。
- [grocery_fulfillment](../grocery_fulfillment/) — 建立在同样技能上的、由图生成的验收评测。
