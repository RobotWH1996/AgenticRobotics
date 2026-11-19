[English](README.md) | 中文

# cable_ur — 用 UR 机械臂和 ZED 相机定位线缆上的标记

> **内容：** 只做感知的 UR + ZED 连接器：运动在结构上不可能（只读 RTDE） · **需要：** `real` + ZED SDK + UR 机械臂 · **耗时：** 数秒 · **安全：** 先读 [../../docs/safety.md](../../docs/safety.md)

只做感知的示例：检测线缆上的白色胶带标记，把分割和 ZED 深度融合成世界坐标系点云，拟合有向包围盒和局部平面，并报告标记在机器人基坐标系里的三维位置和朝向。然后用 `visualize.py` 在三维里查看结果。

这是**独立连接器**的故事：`ur_zed` 连接器把真实传感器接进一张 GaP 图，**不带任何运动栈**。环境直接从 ZED 采集（pyzed SDK），并通过只读 RTDE 读取 UR 关节状态；相机位姿来自 URDF 正运动学加上手眼标定。连接器*只*注册观测/相机工具：注册表里没有 `robot.go_to_pose`、没有夹爪、没有轨迹工具，所以一张图即使意外也不会让机械臂动。

```
graph/workflow.json        v3 图（感知 → 过滤 → 包围盒 → 报告）
graph/scripts/             DINO + VLM 感知 + RANSAC 平面报告
visualize.py               录下轨迹的 viser 查看器
task.yaml                  任务元数据（提示词、套件、相机）
```

## 硬件前置条件

- **ZED SDK（手动安装）。** 这里的 `pyzed` 不能用 pip 装。从 <https://www.stereolabs.com/docs/app-development/python/install> 安装 ZED SDK 和它的 Python API。其余都来自 `uv sync --extra real`（它提供 `ur-rtde` / `rtde_receive`）。
- 一台网络可达的 UR 机械臂（默认 IP `172.22.22.2`；把 `robot_ip=` 传给连接器）。只用 RTDE 的*接收*接口，这个示例从不给机械臂下指令。
- 腕部安装的 ZED，以及一份存成 `.npy` 的 4×4 相机→腕部标定矩阵。用 `GAP_UR_ZED_CALIB` 指向它（或传入 `calibration_path=`）。没有它时，相机位姿退回腕部位姿，报告的三维位置会偏出一个安装偏移。
- 用于正运动学的 UR URDF：`GAP_UR_URDF=<ur5e.urdf 的路径>`，或不设置以使用 `robot_descriptions` 的 `ur5e_description`。

## 产生手眼标定

这个示例需要的 `.npy` 是一个 4×4 矩阵，把**相机坐标系映射到腕部坐标系**。要为 UR5e 上腕部安装的 ZED 产生一份，用 [TobiasRecker/zed_hand_eye_calibration](https://github.com/TobiasRecker/zed_hand_eye_calibration)：打印它的 ChArUco 板，用 `capture_sample.py` 采集 20–40 个腕部位姿，然后跑 `compute_handeye.py`（`cv2.calibrateHandEye`，Tsai）。把结果拿过来时有两处要注意：

- `compute_handeye.py` **打印**相机→tool0 变换（以及它的 ROS `static_transform_publisher` 参数），但不写文件。自己把打印出的 4×4 存下来，例如 `np.save("camera_to_wrist_transform.npy", T_cam2gripper)`。
- 它的坐标系是 ROS 约定：父坐标系 `tool0`，子坐标系是 ZED 的**左镜头光心坐标系**。连接器把这个矩阵用在 URDF 的腕部连杆上。确切约定见 `gap/envs/ur_zed_env.py`，并用 `visualize.py` 做健全性检查：渲染出的相机视锥应该坐在物理安装位置上，点云应该落在机械臂的工作空间里。

## 运行

```bash
# 校验图（不需要硬件）：
uv run gap run examples/cable_ur/graph --validate-only

# 实况感知：
GAP_UR_ZED_CALIB=/path/to/camera_to_wrist_transform.npy \
uv run gap run examples/cable_ur/graph --real ur_zed
```

编程方式（可调的旋钮更多）：

```python
import gap

conn = gap.connector.real(
    "ur_zed",
    robot_ip="172.22.22.2",
    calibration_path="/path/to/camera_to_wrist_transform.npy",
)
result = gap.execute("examples/cable_ur/graph", conn)   # 技能自动发现
conn.close()
```

报告节点打印标记在基坐标系和相机坐标系里的位置，并写入 `/tmp/white_tape_location.json`。

## 可视化

```bash
uv run python examples/cable_ur/visualize.py     # 最新的 outputs/run_*
uv run python examples/cable_ur/visualize.py --trace outputs/run_20260610_120000 \
    --calib /path/to/camera_to_wrist_transform.npy
```

在 viser 里渲染：记录下来的关节构型上的 UR、相机视锥（带拍到的图像）、感知点云、包围盒，以及拟合出的平面。

## 感知要求

感知脚本通过 open-robot-skills 的工具包调用 Grounding-DINO + SAM3 + 一个托管的视觉语言模型（GPU 权重 + `OPENROUTER_API_KEY`，或一套 vertex 配置）。见 open-robot-skills 的 README。`graph/workflow.json` 里的提示词（`object_name`、`dino_prompt`、`text_prompts`）针对黑线缆上的一条白色胶带；换成你的标记时改这些提示词。

## 完整的线缆项目（配套仓库）

这个示例是一个更大的线缆操作项目的感知阶段。运动那一侧在独立的 ROS 1 栈里，有意**不**属于这个连接器（只读设计就是要点）。如果要流水线的其余部分：

- [TobiasRecker/usb_c_insertion](https://github.com/TobiasRecker/usb_c_insertion)：同一套 UR5e + ZED 设备上的力引导 USB-C 插入（扭转控制、对着标记的视觉伺服、基于平面的偏航对齐、螺旋搜索、力控插入）。它的运行视觉服务消费的正是本示例报告节点写出的 JSON。它的启动文件默认是 `/tmp/green_sticker_location.json`，而本示例写的是 `/tmp/white_tape_location.json`。把两边接起来时，把启动参数指到这个路径（或复制文件）。
- [TobiasRecker/zed_hand_eye_calibration](https://github.com/TobiasRecker/zed_hand_eye_calibration)：上面的手眼标定流程。
- [TobiasRecker/vertical_cable_routing](https://github.com/TobiasRecker/vertical_cable_routing) 和 [TobiasRecker/debug_gui](https://github.com/TobiasRecker/debug_gui)：项目里线缆布线的那一半，在双臂 ABB YuMi 上（学习到的线缆追踪、逐卡扣的路径规划、双臂交接）。机器人不同，线缆相同：适合当作「找到标记之后做什么」的参考。
