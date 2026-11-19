[English](README.md) | 中文

# 用 AI 编码智能体驱动 GaP（Claude Code）

这个示例记录的逐步闭环是真实跑过的：下面每条命令和输出都来自一次实际会话。**Claude Code 只装了一个技能，从一句话生成抓取放置图，校验通过后，这张图在 LIBERO 仿真里把奶油芝士放进了篮子（75 秒，有视频）。**

这里有两层智能体，不要混在一起：

```
Claude Code ──（`gap` 技能）──▶ 驱动 CLI：gap check / generate / run / skills …
                                         │
                                         ▼
                            GaP 自己的代码生成智能体（`gap generate`）
                                         │  从磁盘读取技能包的 SKILL.md
                                         ▼
                       技能注册表（例如 ../open-robot-skills）
```

Claude Code **只需要 `gap` 这一个技能**。[open-robot-skills](https://github.com/graph-robots/open-robot-skills) 里的机器人技能包是给 GaP *内部*代码生成智能体当磁盘上的文件用的，不必装进 Claude Code。

## 0. 前置条件（做一次）

```bash
git clone --recurse-submodules https://github.com/graph-robots/graph-as-policy.git
git clone https://github.com/graph-robots/open-robot-skills.git   # 并列克隆
cd graph-as-policy
uv sync --extra quickstart            # 引擎 + 仿真 + 感知技能包
uv run gap skills check --download    # 校验技能包并预取权重（约 3.5 GB）
```

为代码生成和图内的 VLM 感知选一个 LLM 提供商（`gap check` 会告诉你当前配了什么）：

```bash
export OPENROUTER_API_KEY=...         # 最简单：一把密钥两边都用
```

也可以用 Vertex AI（不用 API 密钥，走 gcloud 的应用默认凭证）。每个 shell 设一次（或写进 `.bashrc`），之后裸的 `gap generate "<任务>"` 不用再加参数：

```bash
gcloud auth application-default login                  # 一次
export GOOGLE_CLOUD_PROJECT=<你的项目>
export GAP_LLM_PROVIDER=vertex GAP_LLM_MODEL=<gemini 模型>   # 代码生成
export GAP_VLM_PROVIDER=vertex GAP_VLM_PROJECT_ID=$GOOGLE_CLOUD_PROJECT \
       GAP_VLM_REGION=global GAP_VLM_MODEL=<gemini 模型>     # 感知技能包
```

uv 有一处容易踩坑：每次 `uv run` 都要带上这个 extra。单独的 `uv run` 会重新同步项目虚拟环境，把刚装上的包再裁掉：

```bash
uv run --extra vertex gap generate "<任务>"
```

## 1. 安装智能体技能（做一次）

```bash
claude plugin marketplace add graph-robots/graph-as-policy
claude plugin install gap@gap
```

在新的 Claude Code 会话里验证：问 *"有哪些机器人技能可用？"*，列表里应该有 `gap`。就在这个检出目录里工作的话，技能内容在 [agent/skills/gap/](../../agent/skills/gap/)。其他智能体（Cursor、Codex 等）见 [agent/INSTALL.md](../../agent/INSTALL.md)。

## 2. 让 Claude Code 生成一张图

录制那次会话用的提示是：

> Using your gap skill: generate a robot task graph for "pick up the
> cream cheese and put it in the basket" with output directory
> outputs/agent_gen_test. Then validate the generated graph without
> running any simulator or real robot.

智能体实际做的事都是这个技能教的，你也可以自己跑同样的三条命令：

```bash
uv run gap check                                   # 先出能力报告
uv run gap generate "pick up the cream cheese and put it in the basket" \
    --out outputs/agent_gen_test
# vertex 变体（已验证）：
#   GOOGLE_CLOUD_PROJECT=<项目> uv run --extra vertex gap generate "..." \
#       --provider vertex --model <gemini 模型> --out outputs/agent_gen_test
uv run gap run outputs/agent_gen_test/task_00 --validate-only
```

预期结尾是 `OK: 0 errors`，以及这样一个工作流目录：

```
outputs/agent_gen_test/task_00/
├── workflow.json      # 4 个子图：perceive_target、perceive_container、
│                      #   grasp_target（grasping-with-planner）、
│                      #   place_target（transporting-objects）
├── scripts/           # 图所调用的标准技能脚本
├── checkpoints/       # 生成的后置条件谓词
└── agent_traces/      # 代码生成智能体自己的对话记录
```

那次会话里，智能体第一次 `gap generate` 缺了 vertex SDK。它读了报错，跑了 `uv sync --inexact --extra vertex`，然后重试成功。这种自我修复就是该技能的排障手册在按设计工作。

## 3. 在仿真里跑（带视频）

奶油芝士场景是 `libero_object_all_variance` 套件的任务 **1**（经典 LIBERO 编号）：

```bash
MUJOCO_GL=egl uv run gap run outputs/agent_gen_test/task_00 \
    --sim libero_object_all_variance/1 \
    --record-video --trace-dir outputs/agent_gen_sim
```

录到的结果：

```
SUCCESS (exit=success, 75.0s)
trace: outputs/agent_gen_sim
checkpoint: ... name='target_held'      passed=True   ← 夹爪夹住了奶油芝士
checkpoint: ... name='target_in_basket' passed=True   ← 它最后进了篮子
video: outputs/agent_gen_sim/run_video.mp4 (506 frames)
```

你也可能看到生成的*感知审计*检查点报 `passed=False`（例如 `target_obb_matches_truth`）。它们拿机器人坐标系里的感知包围盒去比世界坐标系里的特权位姿，是生成谓词的坐标系对不上，不是任务失败。物理检查点（`target_held`、`target_in_basket`）才是真值。检查点默认以 `warn` 模式运行，所以无论通过与否，运行都会继续。

## 4. 观看与调试

```bash
uv run gap viz          # 在 localhost:9432 浏览试验：
                        # 视频、图的泳道、每个节点的输入输出、掩码、规划
```

也可以直接打开 mp4，读 `outputs/agent_gen_sim/dag_trace.json`，并用 `gap trace-diff <a> <b>` 比较两次运行。

## 5. 继续迭代

- 让智能体修改或扩展这张图（它会改 `workflow.json` / 脚本并重新校验），或者用 `gap.builder` 手写（[build_a_graph](../build_a_graph/)）。
- 缺一项能力？`gap skills new my-skill --kind skill` 会搭一个**带单元测试**的技能包；`gap skills test my-skill` 运行它。你自己的注册表叠在公开注册表之上：`gap registry init`。
- 要声称成功率，需要 `gap benchmark <yaml> --gate`（[benchmark](../benchmark/)），一次跑通不算数。

**安全：** 这个技能对真机命令是硬门槛。没有你的明确确认，智能体不会跑 `gap run --real ...`，而且要求先仿真。做任何硬件工作之前先读 [docs/safety.md](../../docs/safety.md)。
