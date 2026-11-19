<div align="center">

[English](README.md) | 中文

# Graph-as-Policy
<h3 align="center">
  <strong>🧪 测试版代码发布</strong> | <em>Beta</em> | 2026 年 7 月 1 日
</h3>



**CoRL 2026** · [论文（arXiv）](https://arxiv.org/abs/2607.05369) · [项目主页](https://graph-robots.github.io/gap/)

🆕 **2026 年 11 月 — 自学习流水线已开源：**
[**agentic-self-learning**](https://github.com/graph-robots/agentic-self-learning)
· [论文（arXiv）](https://arxiv.org/abs/2611.09030)
· [项目主页](https://graph-robots.github.io/agentic-self-learning/)

**图即策略。**
GaP 面向*变分自动化*（Variational Automation）：机器人要在大量变化的实例上持续、可靠地完成同一类任务（物体的几何形状和位姿都会变），而不是只成功一次。它把自然语言任务编译成一张带类型、经过校验的模块化技能计算图，在仿真里自我改进，然后在仿真器和真机上执行的是这张图，而不是一个黑盒策略。

[![License: Apache 2.0](https://img.shields.io/badge/license-Apache--2.0-green.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](pyproject.toml)
[![Skills: open-robot-skills](https://img.shields.io/badge/skills-open--robot--skills-orange.svg)](https://github.com/graph-robots/open-robot-skills)
[![Docs](https://img.shields.io/badge/docs-quickstart-0f766e.svg)](https://graph-robots.github.io/graph-as-policy/getting-started/quickstart.html)

![GaP 在真机上运行：杂货打包、爆米花、工具装箱、USB-C 插入](docs/assets/real_robots_strip.gif)

<sub>GaP 在真机上运行：图由自然语言任务生成，在仿真中打磨，再在硬件上执行。从左到右：杂货打包（Franka，10 倍速）、爆米花（长程灶台操作，16 倍速）、工具与充电器装入带标签的箱子，以及 USB-C 插入（带力反馈的 UR5）。</sub>

</div>

```python
import gap

conn   = gap.connector.sim("libero", task="libero_object/0")
result = gap.execute("examples/libero_quickstart/graph", conn)
graph  = gap.agent.generate_sync("pick the soup can and put it in the basket")
print(graph)                  # 策略，以图的形式呈现
gap.viz.serve("outputs")      # 浏览录制的试验
```

技能放在同级仓库
[**open-robot-skills**](https://github.com/graph-robots/open-robot-skills)
（Anthropic Agent Skills 格式，欢迎贡献），按路径自动发现。把两个仓库克隆到同一目录下，所有命令都能找到这些技能。

## 快速开始

**环境要求：** **1 张 NVIDIA RTX 4090（显存 ≥24 GB，Linux + EGL）**、一个
LLM API 密钥（OpenRouter / Vertex），以及
[uv](https://docs.astral.sh/uv/)。首次运行会下载约 3.5 GB 的模型权重；默认感知路径依赖需申请权限的 SAM3 权重，因此第一次运行前还需要 `HF_TOKEN`（一个已开通 SAM3 访问权限的免费
[HuggingFace token](https://huggingface.co/settings/tokens)）。

```bash
git clone --recurse-submodules https://github.com/graph-robots/graph-as-policy.git
#   ^ 子模块是必需的（内置仿真栈）。如果已经普通克隆过，请运行：
#     git submodule update --init --recursive
git clone https://github.com/graph-robots/open-robot-skills.git    # 同级目录，自动发现
cd graph-as-policy
uv sync                                  # 引擎 + LIBERO 仿真（现为基线）
# 若代码生成要用 --provider vertex，请改用 `uv sync --extra vertex`
uv run gap skills install --all          # 按技能包安装虚拟环境（sam3、cuRobo、vlm 等）
#   --all 会装上较重的学习策略包；只跑某一个例子时，
#   `gap skills install --workflow <graph-dir>` 只安装它实际用到的包

export HF_TOKEN=...                      # 用于下载需授权的 SAM3 权重
uv run gap skills check --download       # 预取权重（SAM3 + GDINO）并做能力检查

# 为代码生成和图内 VLM 选一个 LLM 提供商。默认是 openrouter；
# 使用 vertex 请看 `docs/source/authoring/llm-providers.md`。
export OPENROUTER_API_KEY=...
MUJOCO_GL=egl uv run gap run examples/libero_quickstart/graph \
  --sim libero_object_all_variance/0
uv run gap viz                           # 在 localhost:9432 浏览这次试验
```

完整流程（克隆 → 运行 → 生成 → 追踪）见
**[15 分钟导览](https://graph-robots.github.io/graph-as-policy/getting-started/quickstart.html)**。

## 示例

| 示例 | 说明 |
|---|---|
| [libero_quickstart](examples/libero_quickstart/) | 主示例：视觉 → 有向包围盒抓取 → 搬运，并用真值校验 |
| [grocery_packing](examples/grocery_packing/) | 用循环打包每一件物品：图里有一条真正的回边 |
| [generate_a_graph](examples/generate_a_graph/) | 从指令生成并校验工作流目录；覆盖全部 LLM 提供商 |
| [build_a_graph](examples/build_a_graph/) | 用 `gap.builder` 完整地用 Python 编写图：检查点与恢复 |
| [agent_quickstart](examples/agent_quickstart/) | Claude Code 加一个技能：一句话 → 图 → 仿真成功 |
| [grocery_fulfillment](examples/grocery_fulfillment/) | 旗舰验收任务族；每个任务的图由 LLM 生成 |
| [benchmark](examples/benchmark/) | 网格评测：冒烟 → 位姿变化 → 发布门槛 |
| [steered_policy](examples/steered_policy/) | 先感知并悬停，再交给学习到的 VLA 策略 |
| [collect_and_train](examples/collect_and_train/) | 把图当作脚本专家 → 数据集 → 训练 → 策略节点 |
| [cable_ur](examples/cable_ur/) | 真机 UR + ZED 感知（运动已禁用） |
| [real_franka_pick_place](examples/real_franka_pick_place/) | 通过 robots_realtime 在真机 Franka 上抓取放置 |

安装需求与耗时见完整列表
**[examples/README.md](examples/README.md)**。真机示例请先阅读
[docs/safety.md](docs/safety.md)。

## 自学习流水线

在仿真中自我改进图的闭环已作为
**[agentic-self-learning](https://github.com/graph-robots/agentic-self-learning)**
单独发布。编码智能体（Claude Code 或 Codex）编写 GaP 的 `workflow.json` 策略，在
[RoboSimStudio](https://github.com/robosimstudio/robosimstudio)
任务上运行，读取结构化的仿真反馈，再改写这张图。研究中的每一种反馈条件（状态、关系或视觉反馈；空间如何描述；按回合、按动作或按节点计时）都是一项配置，来自
[open-robot-skills](https://github.com/graph-robots/open-robot-skills)
的技能则作为智能体的技能库接入。

它配套论文 *A Controlled Study of Models, Skills, Feedback, and Curriculum
in Agentic Robotics*（[arXiv](https://arxiv.org/abs/2611.09030) ·
[项目主页](https://graph-robots.github.io/agentic-self-learning/)）。

## 文档

完整文档站：**<https://graph-robots.github.io/graph-as-policy/>**

- [快速开始（15 分钟导览）](https://graph-robots.github.io/graph-as-policy/getting-started/quickstart.html) — 克隆 → 运行 → 生成 → 追踪
- [运行时与模式](https://graph-robots.github.io/graph-as-policy/reference/workflow-schema.html) — workflow JSON、执行器语义、检查点
- [技能编写](https://graph-robots.github.io/graph-as-policy/skills/authoring-bundles.html) — Agent Skills 格式、`gap.requires:` frontmatter
- [LLM 提供商](https://graph-robots.github.io/graph-as-policy/authoring/llm-providers.html) — openrouter / vertex
- [技能注册表](https://graph-robots.github.io/graph-as-policy/skills/registries.html) — `--skills`、`$GAP_SKILLS_PATH`、`gap registry …`
- [CLI 参考](https://graph-robots.github.io/graph-as-policy/reference/cli.html) — 每一个 `gap` 子命令
- [安全](https://graph-robots.github.io/graph-as-policy/real-robots/safety.html) — 运行任何真机示例前的必读材料

## 配合 Claude Code 与 AI 智能体使用

GaP 自带一个智能体技能（[`agent/`](agent/)），用来教 AI 编码智能体上面这些工作流：

```bash
claude plugin marketplace add graph-robots/graph-as-policy
claude plugin install gap@gap
```

然后可以直接问：*"这台机器人现在能做什么？"*、*"在仿真里跑快速开始的图"*、*"生成一张打包杂货的图"*、*"这次试验为什么失败了？"*。真机命令必须经过人的明确确认才会执行。其他智能体（Cursor、Codex 等）以及免安装用法见
[agent/INSTALL.md](agent/INSTALL.md)。

## 引用

如果在研究中使用了 GaP，请引用我们的 CoRL 2026 论文：

```bibtex
@inproceedings{chen2026gap,
  title     = {GaP: A Graph-as-Policy Multi-Agent Self-Learning Harness
               for Variational Automation (VA) Tasks},
  author    = {Chen, Kaiyuan and Xie, Shuangyu and Fu, Letian and Yu, Justin and
               Pacini, William and Bajamahal, Sandeep and Kim, Hudson and
               Drake, Jaimyn and Kim, Daehwa and Xue, Haoru and Francis, Jonathan and
               Juette, Christian and Schaldenbrand, Peter and Seker, Muhammet Yunus and
               Wickramarachchi, Ruwan and Yoo, Uksang and Wang, Guanzhi and
               Murali, Adithyavairavan and Sundaralingam, Balakumar and
               Sastry, S. Shankar and Huang, Spencer and Zhu, Yuke and
               Fan, Linxi and Goldberg, Ken},
  booktitle = {Conference on Robot Learning (CoRL)},
  year      = {2026},
  url       = {https://arxiv.org/abs/2607.05369}
}
```

如果使用了自学习流水线
（[agentic-self-learning](https://github.com/graph-robots/agentic-self-learning)），
请同时引用：

```bibtex
@misc{chen2026controlled,
  title         = {A Controlled Study of Models, Skills, Feedback, and Curriculum
                   in Agentic Robotics},
  author        = {Chen, Kaiyuan and Zhu, Xinyue and Xie, Shuangyu and Yoo, Uksang and
                   Luong, Thi Thu Phuong and Gualtieri, Marcus and Juette, Christian and
                   Ren, Liu and Huang, Spencer and Goldberg, Ken},
  year          = {2026},
  eprint        = {2611.09030},
  archivePrefix = {arXiv},
  primaryClass  = {cs.RO},
  url           = {https://arxiv.org/abs/2611.09030}
}
```

## 许可证与署名

graph-as-policy 与 open-robot-skills 采用 Apache-2.0 许可证。它们建立在第三方工作之上，包括 LIBERO/LIBERO-PRO、Variational-Automation-Benchmark、robosuite、robots_realtime、pyroki、SAM3、Grounding DINO，以及（可选的）NVIDIA cuRobo。完整署名表见 **[NOTICE.md](NOTICE.md)**。
