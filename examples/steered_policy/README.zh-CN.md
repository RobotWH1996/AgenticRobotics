[English](README.md) | 中文

# 引导式策略 — 先悬停，再把控制权交给 VLA

> **内容：** 混合图：感知并悬停在目标上方，然后把控制权交给一个 VLA 策略 · **需要：** `quickstart` + `policy` + LLM 密钥 · **耗时：** 每次试验约一分钟

两张用几何感知*引导*学习策略的混合图：有向包围盒感知定位目标（在被扰动的布局上比较稳），一次笛卡尔接近把末端执行器安全地预置到物体**上方**，然后才把控制权交给闭环的视觉-语言-动作策略。策略从这个接近其训练分布的位姿开始。

- **`graph_loop/`** — 清空所有物品的循环：`capture` 记录回合开始时的手臂位姿；每一轮 `reset` 回到那里，感知下一件物品（`perceiving-objects-oneshot`，它的 VLM 回答「没有」时循环干净结束），接近到其包围盒上方，然后策略技能的 `.run` 工具（例如 `pi05-libero.run`）负责抓起*并放下*。终止条件是夹爪一次完整的开→合→开循环。
- **`graph_grasp/`** — VLA 抓取加几何放置的拆分：策略只做灵巧抓取（由一次「已夹住并抬起」的 VLM 检查终止；开发树用的是夹爪*抓取*检测器，移植后的引擎没有带上，见下面的说明），然后 `place_above_basket.py` 垂直抬起，高位搬运，下降到篮子包围盒上方，松开。

## 运行

```bash
uv sync --extra quickstart --extra policy   # 外加 openpi 的 websocket 客户端
```

图引用一个策略**技能**（例如 `pi05-libero`），启动器会自动拉起它的预设服务器（首次使用时下载检查点；需要 `$GAP_OPENPI_DIR` 上有一份 [openpi](https://github.com/Physical-Intelligence/openpi) 检出）。也可以手工跑那个服务器，例如在多次运行之间共用：

```bash
uv run gap policy serve pi05-libero --port 9100
```

然后把 `{{policy_id}}` 具体化成一个策略技能名，例如 `pi05-libero`（形成 `pi05-libero.run` 工具；评测框架按格子做这件事。单独跑时，用 sed 替换占位符，或给工作流做模板）：

```bash
MUJOCO_GL=egl uv run gap run examples/steered_policy/graph_loop \
    --sim libero_object_all_variance/0
```

## 说明

- 策略节点写的是技能的 `.run` 工具（例如 `pi05-libero.run`），**不带 `policy_id`**：模型归技能所有。它读取图作用域的 `observation_stream`，并在 `gripper_cycle` / VLM / `max_windows` 上终止。`molmoact-libero` 是同一任务族的 MolmoAct 替代。
- `graph_grasp` 相对开发树的差异：`gripper_grasp_termination`（检测开→合并保持）只存在于策略循环的一个开发分支变体上。忠实移植的引擎提供的是循环检测加 VLM 终止，所以抓取阶段用的是 `termination_prompt: "Is the object held in the gripper and lifted off the surface?"`。
- 接近脚本有意保留当前末端执行器的朝向，并用较紧的 `move_tolerance`（0.003）和较宽的步数预算，让交接时的本体感觉留在分布内。调参理由见脚本的文档字符串。
