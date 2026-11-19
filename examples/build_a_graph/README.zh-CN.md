[English](README.md) | 中文

# build_a_graph — 用 `gap.builder` 用 Python 编写工作流

> **内容：** 完整的编写示例：检查点、恢复动作、`--execute` · **需要：** `uv sync` 即可构建 · **耗时：** 约 1 分钟

LLM 生成是产出图的一种方式，不是唯一的方式。这个示例用 builder API 手工搭出完整的快速开始式抓取放置工作流。**builder 和 `gap generate` 走的是同一条产物流水线**：它写出同样的工作流目录（`workflow.json` + `scripts/` + `checkpoints/`），经过和智能体输出相同的解析与结构校验，并用同样的 `gap run` / `gap.execute` 运行。

```bash
uv run python examples/build_a_graph/build_graph.py --out my_graph   # 构建并校验
```

这条命令会打印校验报告，并留下一份可运行的产物：

```
my_graph/
├── workflow.json              # v3 图（4 个子图 + done/abort 两个结束节点）
├── scripts/                   # 原样复制的技能包脚本
│   ├── perceive_dino_vlm.py   #   来自 open-robot-skills 检出；和 `gap generate`
│   ├── compute_align_pose.py  #   为每个工作流写出的副本完全一样
│   ├── compute_drop_pose.py
│   ├── waypoint_move.py
│   └── descend_release.py
└── checkpoints/
    └── grasp_sg.py            # 真值后置条件 `target_held`
```

## 构建出什么

这张图是能跑的，不是示意。它对齐 [libero_quickstart](../libero_quickstart/) 的结构，跑同一个任务（`libero_object_all_variance/0`）：

```
START → target → container → grasp → transport → done
           ↘ not_found       ↘ failed   ↘ blocked → abort（松开夹爪，回原位）
```

- **target_sg / container_sg**（`perceiving-objects`）：`robot.get_observation` → 该技能包的标准 DINO + VLM + SAM3 脚本 → `geometry.filter_and_compute_obb`。输出（`target_obb`、`container_obb` 等）按名字绑定到下游子图的输入。
- **grasp_sg**（`grasping-direct-ik`）：张开 → `geometry.top_down_grasp_candidates(obb)` → 在高处预先转到抓取朝向 → 直线下降（`robot.go_to_pose`，进程内逆解，没有规划器）→ 闭合。由一条 `validate=True` 的检查点（`target_held`）把关，对照仿真器真值评测。
- **transport_sg**（`transporting-objects`）：由容器包围盒算出放下位姿 → 抬起并横向经过路点 → 下降、松开、撤回。

## 20 行里的 builder API

```python
from gap.builder import Workflow, Subgraph, Ref

sg = Subgraph(name="grasp_sg", skill="grasping-direct-ik")
sg.add_input("target_obb", type_name="OrientedBoundingBox")
sg.add_node("open", type="tool", tool="robot.open_gripper")
sg.add_node("compute_grasp", type="tool",
            tool="geometry.top_down_grasp_candidates",
            inputs={"obb": Ref("in.target_obb")})
sg.add_node("descend", type="tool", tool="robot.go_to_pose",
            inputs={"pose": Ref("compute_grasp.candidates.poses.0")})
sg.add_node("close", type="tool", tool="robot.close_gripper")
sg.add_exit("grasped")            # 空节点，成功标记
sg.set_on_error("failed")         # 任何异常 → "failed" 出口
for src, dst in [("START", "open"), ("open", "compute_grasp"),
                 ("compute_grasp", "descend"), ("descend", "close"),
                 ("close", "grasped"), ("grasped", "END")]:
    sg.add_edge(src, dst)

wf = Workflow(name="pick_into_basket")
wf.add_subgraph(sg)               # 再加上感知 / 搬运子图
wf.add_node("grasp", type="subgraph", ref="grasp_sg")
# ... 按每个子图的出口值加条件边 ...
wf.save("my_graph/workflow.json")   # 解析 + 结构校验
```

`Ref("node.field.path")` 是数据流的基本写法，序列化后就是 JSON 里的 `{"$ref": ...}`。`Ref("in.<name>")` 读取已声明的子图输入。跨子图的数据不用显式连线：名为 `target_obb` 的子图输入会绑定到上游某个同名的子图输出。

完整程序见 [build_graph.py](build_graph.py)，包括技能包脚本如何复制进来，以及检查点旁路文件如何写出。

## 执行

要求和快速开始相同（`uv sync --extra quickstart`，权重已下载，并配置了 VLM 凭证）：

```bash
MUJOCO_GL=egl uv run python examples/build_a_graph/build_graph.py --out my_graph --execute
# 或者等价地：
MUJOCO_GL=egl uv run gap run my_graph --sim libero_object_all_variance/0
uv run gap viz     # 浏览录下的轨迹
```

open-robot-skills 的检出目录会自动发现（`$GAP_SKILLS_PATH`，或与 graph-as-policy 并列的那个检出）。要改位置，传入 `--skills /path/to/open-robot-skills`。

## 接下来看哪里

- [generate_a_graph](../generate_a_graph/) — 让 LLM 流水线根据一句话写出同一份产物。
- [libero_quickstart](../libero_quickstart/) — 这张图经过手工调好、已提交的版本，端到端对照仿真真值运行。
- [grocery_packing](../grocery_packing/) — 循环版本：同样的感知 → 抓取 → 搬运，一直重复到每件物品都装完。
- `docs/runtime.md` — builder 所针对的 JSON 模式和执行器语义。
