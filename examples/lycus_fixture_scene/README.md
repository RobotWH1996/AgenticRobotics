# Lycus 双桌夹具场景

前侧夹具初始闭合并夹住工件，后侧夹具初始打开且留空。两边均使用被动手柄、连杆和滑台。场景带三个 RGB-D 机位及双臂关节接口。

在 GAP 仓库根目录运行场景检查：

```bash
MUJOCO_GL=egl .venv/bin/gap run examples/lycus_fixture_scene --sim lycus_fixture/0 --no-video
```

打开 MuJoCo 窗口：

```bash
.venv/bin/python -m gap.envs.lycus_fixture_env --viewer
```

模型文件为 `outputs/scenes/lycus_fixture/model.xml`。Python 中可用 `gap.connector.sim("lycus_fixture", task=0)`。笛卡尔节点可通过 `ik` 参数注入 Lycus 规划后端。夹具和工件的接触使用近似碰撞几何。

## 生成本地模型

准备基础 Lycus MJZ、夹具 OBJ 和工件 OBJ。在仓库根目录运行：

```bash
python examples/lycus_fixture_scene/build_gap_scene.py \
  --robot-scene /path/to/lycus.mjz \
  --fixture /path/to/fixture.obj \
  --workpiece /path/to/workpiece.obj \
  --output outputs/scenes/lycus_fixture
```

`--fixture` 使用生成脚本针对的原始夹具网格。输入 CAD 和生成的场景资产单独准备。
