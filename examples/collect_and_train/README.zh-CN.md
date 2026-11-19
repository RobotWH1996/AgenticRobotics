[English](README.md) | 中文

# 采集示教 → 训练策略 → 在图里运行

> **内容：** 把图当作脚本专家 → HDF5/LeRobot 数据集 → 在外部训练 → 策略回到图里 · **需要：** `quickstart` + `policy` + LLM 密钥 · **耗时：** 采集按每回合若干秒计

完整的数据闭环：一张校验过的 GaP 图充当**脚本专家**，它的回合变成示教数据集，外部配方在上面训练一个视觉-语言-动作策略，训练好的策略再作为自己的**策略技能**节点回到 GaP（和随仓库发布的 `pi05-libero` / `molmoact-libero` 技能一样），并由采集数据时用的同一套感知来引导（见 [`../steered_policy/`](../steered_policy)）。

## 1. 采集

```bash
uv sync --extra quickstart --extra policy   # 仿真 + 感知 + openpi 客户端

uv run python examples/collect_and_train/collect.py --episodes 50 --out demos.hdf5 \
    --graph examples/libero_quickstart/graph
```

每个回合重置到一个新的烘焙变化种子，并在每个控制步记录：各相机 RGB（`/observations/<相机>_rgb`，uint8）、本体感觉状态（`/observations/state`，float32）、下发的动作（`/actions`）、奖励，以及带成功标志的回合边界。写入方是 `gap.connector.collector.DataCollector`。

## 2. 转换并训练（外部）

这份 HDF5 布局直接对应 LeRobot 的数据集字段（`observation.images.*`、`observation.state`、`action`、回合下标）。用 LeRobot 的 `lerobot/scripts/push_dataset_to_hub.py` 风格加载器，或大约 30 行的自定义 `LeRobotDataset.from_raw` 适配器来转换，滤到 `success=True` 的回合，再用你选的配方训练。例如 [LeRobot](https://github.com/huggingface/lerobot) 的 ACT/扩散基线，或 [OpenPI](https://github.com/Physical-Intelligence/openpi) 微调（`pi05` 配置）。模型怎么托管是你的事。GaP 只需要一个 websocket 策略服务器。

## 3. 服务并运行训练好的策略

图里引用了随仓库发布的策略技能（`pi05-libero` / `molmoact-libero`）时，会自动拉起它的预设，不用额外配置。要手工跑那个服务器，或服务你自己的检查点：

```bash
uv run gap policy serve pi05-libero --port 9100   # 手工跑一个随仓库发布的预设
# 你自己的检查点：把它包成一个策略技能包；或者一次性使用时，
# 在任务 yaml 里加上 policies: {my_policy: {start_cmd: "... --port {port}"}}

MUJOCO_GL=egl uv run gap run examples/steered_policy/graph_loop \
    --sim libero_object_all_variance/0
```

这张引导图悬停在感知到的物体上方，然后把控制权交给你的策略。交接时的位姿和这个采集脚本产出的分布一致，因为两边用的是同一套包围盒感知和接近动作。
