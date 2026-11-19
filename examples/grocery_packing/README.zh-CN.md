[English](README.md) | 中文

# grocery_packing — 用循环把每一件物体都装进篮子

> **内容：** 一张带真正**回边**的抓取放置图：循环直到每件杂货都进了篮子 · **需要：** `uv sync` + `gap skills install --all`（CUDA）+ GPU + LLM 密钥 · **耗时：** 每件约一分钟 · **产物：** 一份静态 `workflow.json`（v3），直接运行。

[build_a_graph](../build_a_graph/) 抓的是一件被描述的物体。这个示例**循环**：感知桌上的下一件物体，用规划器配方抓住它，运进篮子，然后路由**回到**感知，再重复，直到评测报告每件物品都已送达。

这是一张自包含的静态图：`packing_graph/workflow.json` 加上它引用的 `scripts/`。没有构建步骤，像任何其他 v3 图一样加载并运行。

```
packing_graph/
├── workflow.json            # v3 图：3 个子图 + done/abort 两个结束节点
└── scripts/
    ├── perceive_dino_vlm.py # DINO + VLM 锦标赛 + SAM3 → 世界坐标系点云
    ├── exterior_view.py     # 只保留 agentview 相机（丢掉腕部相机）
    ├── route_next_object.py # 循环控制：全部装完 → done，否则 found/none
    ├── grasp_move.py        # VAB 风格的抓取接近（升起 → XY → 垂直 Z）
    ├── transport_move.py    # VAB 风格的运进篮子（垂直 Z）
    └── place_release.py     # 张开夹爪 + 直线撤回
```

## 循环

```
START ──→ perceive_next ──found──→ grasp ──grasped──→ transport ──┐
            │  │ none                 │ failed           │ blocked │ placed
  not_found │  ↓                      ↓                  │         │
            ↓  done（干净的          abort ←─────────────┘         │
          abort  成功出口）                                        │
            └──────────────── perceive_next ←──────────────────────┘
                    回边（transport → perceive_next）
```

`transport --placed--> perceive_next` 是一个真正的环。条件边解析到一个已经完成过的节点时，执行器把它当作循环：重置循环体（`perceive_next`、`grasp`、`transport`）再跑一遍。跨子图存储保留最近一次的生产者，所以每一轮抓住的是刚感知到的 `target_obb`，放进的是刚感知到的 `container_obb`。循环头每一圈都重新定位**下一件物品和篮子**。`GAP_ITERATION_CAP` 限制失控的循环。回边语义见 `docs/runtime.md` §7.2。

## 子图

- **perceive_next_sg**（`perceiving-objects`）是**循环头**，并且**每一轮**都定位抓取的两端：`get_observation → exterior_view → perceive("basket") → filter_and_compute_obb → perceive("grocery item") → decide`。没有单独的、只跑一次的容器子图。篮子（`container_obb`）和下一件物品一起每轮重新感知，所以放下位姿始终反映当前场景（代价是每轮多一次感知）。有两件事保证物品挑选是老实的：
  - 感知节点传入一段 `object_description`：「一件包装好的杂货，例如罐子、盒子、纸盒、广口瓶或瓶子；绝不是柳条篮子或储物容器」，于是只要桌上还有真物品，VLM 的成对锦标赛就会优先选它而不是篮子。
  - `decide`（`route_next_object.py`）是循环的停止信号：每一轮的 **VLM 完成检查**，不是仿真器的特权判决（见下文）。

- **grasp_sg**：`open → top_down_grasp_candidates → grasp_move → observe → close`。`grasp_move.py` 是 **VAB 接近配方**：升到悬停高度（直线笛卡尔），在物体上方做 XY 平移（笛卡尔），再用 cuRobo 的**轴向约束**直线规划垂直下降（`plan_directed_linear`，`allowed_axes=["Z"]`，`orientation_mode="LOCK"`）。这是保证垂直的下落，不是一条弯曲的逆解路径。

- **transport_sg**：`transport_move → release`。`transport_move.py` 抬起，在篮子上方做 XY 平移，然后用同样锁轴的垂直 Z 下降*进*篮子；`place_release.py` 张开夹爪并直线撤回。

## 终止：不依赖特权信息，由 VLM 确认

`route_next_object.py` 不需要仿真器的特权信号，同一份策略在真机上不用改就能跑。信号是分层的：

1. **VLM 完成检查（主信号）。** 每一轮，外部相机画面交给 VLM：「所有杂货是不是都已经放进篮子了？」确信的 YES → **`none` → done（成功）**。这个检查只会强制停止：NO（或 VLM 不可用）从不会强制循环继续，所以下面的保护仍然保证能停下来。
2. **环境判决（次信号，仅仿真的兜底）。** 轮询 `sim.check_success`；`task_completed` 读的是环境在自己的 `step()` 里缓存的成功，它不会重新评估有状态的 `pack_all_into` 谓词（那个谓词每次评估都会把已送达的物体传送走）。包了一层，非仿真连接器会干净地落空。
3. **无进展保护。** 连续三轮重新感知到*同一个*目标（点云质心在 3 厘米以内），说明上一轮抓取加搬运什么都没改变（一次送达会把那件物品拿走）→ `none`。30 轮的预算兜住病态的来回切换。保护状态按轨迹目录分开存，评测工作进程不会把一次试验的状态漏到下一次。
4. **感知。** 其余情况：返回了一件物品 → `found`（去抓）；什么都没有 → `none`。

`none` 是正常出口（不是 `on_error`），所以结束看起来不是失败。

## 打包评测（送达即传送）

默认任务是 **Variational-Automation-Benchmark** 的全部打包套件（`libero_object_packing`）。物体在篮子里停稳的那一刻，`pack_all_into` 谓词把它标成*已送达*，环境把它**传送到坟场位姿**（移出场景），得分 `completion_rate = 已送达 / 总数`。每件送达的物体从桌上消失，于是下一次 `perceive_next` 找到*下一件*；全部装完时 `task_completed` 触发，循环退出。图始终是纯策略（感知 / 抓取 / 搬运）；传送和计分归*评测*管。

## 执行

需要 `perceiving-objects` 的权重、CuRobo（`uv sync --extra grocery`）、一份 VLM 凭证，以及这个检出里执行器的回边支持：

```bash
# 对着 VAB 的全部打包套件跑；运行视频默认录到
# <轨迹目录>/run_video.mp4（加 --no-video 可跳过）。
MUJOCO_GL=egl uv run gap run examples/grocery_packing/packing_graph \
    --sim libero_object_packing/0
uv run gap viz     # 浏览录下的轨迹：每件物体都会再访问一次 perceive_next
```

`open-robot-skills` 的检出目录会自动发现（`$GAP_SKILLS_PATH` 或并列的检出）；传入 `--skills /path/to/open-robot-skills` 可覆盖。VLM 的提供商和模型来自 `GAP_VLM_PROVIDER` / `GAP_VLM_MODEL`（外加该提供商的凭证）。

在默认摆放下，循环每轮送达一件，并在最后一件送达的下一轮干净退出。和其他 CuRobo 示例一样，一次会话的第一次运行要付一次性代价（视觉模型冷加载 + CuRobo 的 CUDA 核 JIT，约 40 秒），之后每轮的计时才稳定下来。

## 自己生成它

上面这张静态图，也是 `gap generate` 从任务句子里产出的东西。`perceiving-next-item` / `grasping-with-planner` / `transporting-objects` 技能带着和本示例脚本相同的调好的配方，所以生成的循环在结构和行为上与这一份一致：

```bash
# LLM 代码生成（需要 LLM 凭证；这里是 Vertex，OpenRouter 也可以）：
export GAP_LLM_PROVIDER=vertex GAP_LLM_MODEL=gemini-3.1-pro-preview \
       GOOGLE_CLOUD_PROJECT=<你的项目>       # 外加 `gcloud auth application-default login`
uv run gap generate "Pick all the objects and place them in the basket" \
    --provider vertex --model gemini-3.1-pro-preview

# 在同一套件上跑生成的图：
MUJOCO_GL=egl uv run gap run outputs/generated_<时间戳>/task_00 \
    --sim libero_object_packing/0
```

**评测注意：** `gap benchmark` 施加的是按*单次*抓取定的每试验安全限额（`max_perception_calls: 50` 等）。六件物品的全部打包循环工作量大约是 6 倍。在评测 YAML 里把它们调高，否则工作进程会在循环中途杀掉回合：

```yaml
safety_limits: {max_perception_calls: 400, max_planning_calls: 200, max_sim_steps: 40000}
```

## 接下来看哪里

- [build_a_graph](../build_a_graph/) — 这张图的单物体版本。
- [grocery_fulfillment](../grocery_fulfillment/) — 由 LLM 生成的验收评测，其抓取/搬运配方与本示例一致。
- `docs/runtime.md` §7.2 — 执行器实现的循环（回边）语义。
