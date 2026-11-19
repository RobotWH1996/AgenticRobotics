[English](README.md) | 中文

# real_franka_pick_place — 在真机 Franka 上把果冻盒放进桶里

> **内容：** 通过 robots_realtime 桥接的 Franka + Robotiq 抓取放置循环 · **需要：** `real` + Franka/Robotiq/ZED · **耗时：** 每周期若干秒 · **安全：** 先读 [../../docs/safety.md](../../docs/safety.md)

把桌上每一盒 Jello 果冻抓起来放进白桶，循环 `perceive_target → grasp → transport`，直到感知子图报告桌面已清空。跑在一台带 Robotiq 夹爪和 ZED 相机的 Franka Panda 上，经 [robots_realtime](../../third_party/robots_realtime) 桥接驱动。

```
graph/workflow.json        v3 图（从开发树的 v2 模式手工迁移）
graph/scripts/             感知 + 接近/对齐/放下脚本
task.yaml                  任务元数据（提示词、套件、相机）
```

## 安全须知：运行前先读

这个示例会移动一台真机械臂。

- **急停始终放在够得着的地方。** 第一次运行前先试一下。
- **清空工作空间：** 机械臂可达包络内不能有人；除了任务物品，不要放易碎物；线缆和相机三脚架放在扫掠体积之外。
- 连接器在实时客户端连上之前预先写入一条**保持原位**指令，所以启动时机械臂保持当前位姿，而不是跳到 Viser 控件的目标。尽管如此，开始时仍应让机械臂处在靠近原位的合理构型。
- `robot.go_home` 在真机上**被禁用**（连接器打一条警告，什么都不做）。仿真路径里那种盲目回原位可能扫过你的场景。运行前后手动移到空旷处。`abort` 结束节点的恢复动作只张开夹爪。
- `graph/workflow.json` 里的接近高度和放下间隙是按一张特定桌子的高度调的。第一次下降之前，对照你的装置再检查一遍。

## 硬件配置（rr-session）

robots_realtime 栈作为钉死版本的子模块随仓库提供，跑在**它自己的**进程和环境里。GaP 从不导入它：

```bash
git submodule update --init third_party/robots_realtime
cd third_party/robots_realtime && uv sync   # 一次；需要 Franka/robotiq 这些 extra
```

会话配置是 `third_party/robots_realtime/configs/franka/franka_robotiq_client.yaml`：一个 `RobotNode`（Franka + Robotiq）、一个 ZED `CameraNode`，以及连接到 GaP 在 `127.0.0.1:9000` 上的 msgpack 服务器的 `FrankaOscClientCartesianAgent` 客户端。按你的工作单元调整相机的 `device_id`、外参文件和机器人配置。

线协议（两个方向都是 4 字节大端长度 + 带 numpy 支持的 msgpack）：客户端发送观测 `{left: {joint_pos[8]}, <相机>: {images, depth_data, intrinsics, pose_mat}}`，接收以 50 Hz 重发的动作 `{timestamp, left: {joint_pos[7], gripper}}`。

## 运行

```bash
# 先校验图（不需要硬件）：
uv run gap run examples/real_franka_pick_place/graph --validate-only

# 完整运行：自动拉起 rr-session，等到第一帧相机画面，然后执行图：
uv run gap run examples/real_franka_pick_place/graph --real franka
```

双终端调试流程（看实时客户端自己的日志和界面）：

```bash
# 终端 1
uv run --directory third_party/robots_realtime \
    rr-session configs/franka/franka_robotiq_client.yaml

# 终端 2
uv run gap run examples/real_franka_pick_place/graph --real franka --no-rr-autostart
```

编程方式：

```python
import gap

conn = gap.connector.real("franka")           # rr_autostart=True，端口 9000
result = gap.execute("examples/real_franka_pick_place/graph", conn)
conn.close()
```

如果启动卡在 `wait_ready`，超时错误会告诉你哪一段线路是静默的（没有客户端连上 / 相机节点没有发布 / 缺 RGB 键）。同时看它指向的 rr-session 日志。

## 感知要求

感知子图通过 open-robot-skills 的工具包调用 Grounding-DINO + SAM3 + 一个托管的视觉语言模型。你需要一张 GPU，以及 `grounding-dino` 和 `sam3` 的模型权重，还要配好 VLM 提供商（`OPENROUTER_API_KEY` 或一套 vertex 配置）。见 open-robot-skills 的 README。

## v2 → v3 迁移说明

开发树的源图是模式 v2（`states` / `transitions`，每个状态有 `on_success` / `on_failure`）。这里做的映射是：

- 每个 v2 子图状态 → 一个 v3 节点；线性的 `on_success` 链 → `edges`；
- 子图内部所有 `on_failure` 目标收成唯一的 `on_error` 出口符号（v3 的失败是异常，不是边）；
- v2 的终止状态 → 列在 `exit.success_values` 里的一个 `noop` 节点；
- v2 的 `transitions` → 顶层的 `conditional_edges` 映射（包括 `transport → perceive_target` 这条循环）；
- 服务/技能状态 → `type: tool` 节点（`gripper.Open` → `robot.open_gripper`，`RobotControl.GoToPose` → `robot.go_to_pose`，`top_down_grasp_poses_from_obb` → `geometry.top_down_grasp_candidates`，`filter_and_obb` → `geometry.filter_and_compute_obb`）；
- 不可达的 v2 `slip` 结束状态被删掉了。
