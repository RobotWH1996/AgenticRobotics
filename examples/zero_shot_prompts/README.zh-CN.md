[English](README.md) | 中文

# zero_shot_prompts — grocery_fulfillment 的零样本提示词矩阵

> **内容：** 六条零样本测试提示词，原样喂给 `gap.agent.generate`，每条用一个针对仿真真值的程序化**物体状态准则**来评判 · **需要：** `grocery`（CUDA）+ LLM 凭证（生成和感知 VLM） · **耗时：** 每个案例约 10–30 分钟（一次生成 + 1–3 次执行）。

提示词和它们的**基线**列来自一次人工测试（观察到的结果和怀疑的原因，引在 `cases.py` 里）。这套测试用测量结果替换目测判决：执行期间在**每一次工具调用**周围记录真值世界状态，并按物理上发生了什么给每条提示词打分：哪些物体真的被抓住并抬起、什么最后进了篮子、东西移动了多远、朝哪个方向、罐子是否仍然直立。从不依据模型自己声称的成功，也从不依据环境内置的奖励（那衡量的是另一个任务；它只作为参考元数据被记录）。

## 矩阵

提示词列保持原文，因为它们会原样送给生成器。

| 案例 | 提示词 | 测试者基线 | 测量准则（节选） |
|---|---|---|---|
| `soup_basket` | "Pick up the alphabet soup can and place it in the basket" | 成功，对位置变化稳健 | 每个种子：汤罐**被抓住并抬起** ∧ 最终停稳在篮子里 ∧ 没有别的东西被装入；在 **3 个种子**上跑（布局确实不同），全部通过才算通过 |
| `all_objects` | "Pick up all objects and place them in the basket" | 失败：只抓了汤罐；归咎于「GaP 只是有向无环图，任务需要环」 | 6/6 停稳在篮子里（得分 = 比例）；逐物体的抓取事件；**诊断：生成的图是否含环，以及执行器在运行时是否真的重访了节点** |
| `soup_then_milk` | "…soup in the basket, then …milk in the basket" | 失败：卡在抓牛奶（怀疑是网格加载） | 两次不同的抓取事件 ∧ 两件都装入 ∧ 汤罐严格先进入篮子；墙钟上的**卡住是一等结果**：被杀掉的运行按其已刷出的部分轨迹打分，最后一次尚未返回的工具调用被报告为卡住位置 |
| `two_inches_right` | "…place it down two inches to the right" | 失败：抓起来，然后把它碰倒 | 被抓住 ∧ 最终 Δy = 5.1 ± 3 厘米（两个 y 方向都接受：**在 agentview 视频里 +y 是图像右侧，从相机坐标系测得**；−y 是机器人的右侧；方向会被记录）∧ Δx ≤ 5 厘米 ∧ **仍然直立**（初始朝上的物体轴与垂直方向夹角 ≤ 30°；碰倒约 90°）∧ 在桌面上松开 |
| `cream_cheese` | "Pick up the cream cheese and put it in the basket" | 失败：CuRobo 找不到无碰撞规划；`geometry.top_down_grasp_candidates` 给出过大的包围盒 | 被抓住并抬起 ∧ 停稳在篮子里 ∧ 没有别的东西被装入；**诊断：规划器工具错误 + 每一次 `geometry.*` 的数值输出**，用来和真值尺寸比较（测得 8.3 × 4.3 × 2.0 厘米，它确实是个矮物体） |
| `move_basket_ranch` | "Move the basket to the opposite side, then pick up the ranch and place it in the basket" | （没有记录结果） | 篮子位移 ≥ 20 厘米并有横向翻边（或 x 方向 ≥ 30 厘米）∧ ranch（`salad_dressing`）被抓住 ∧ 停稳在**被挪走之后**的篮子里（包含关系跟着篮子的实时位姿）；跑在种子 1 上，那里篮子开始时明显在一侧 |

### 扩展矩阵（新的能力探针 + 更多 VAB 任务/套件）

另外七个案例探测测试者矩阵没覆盖的轴，全部落在 Variational-Automation-Benchmark 自己的杂货任务族里（`third_party/Variational-Automation-Benchmark/tasks/`）。词汇覆盖 10 件物品（alphabet_soup、bbq_sauce、butter、chocolate_pudding、cream_cheese、ketchup、milk、orange_juice、salad_dressing、tomato_sauce）：每个变化任务带不同的 6 件子集加篮子，换篮子套件会在各个初始状态之间挪动篮子。下面每个场景在写下准则之前都实机探测过：

| 案例 | VAB 任务 | 提示词 | 探测什么 | 准则（节选） |
|---|---|---|---|---|
| `stack_butter_on_cream_cheese` | all_variance/0 | "Stack the butter on top of the cream cheese" | 精确放置 | 黄油停在奶油芝士**上面**（`is_on_strict` 风格的窗口，质心在底座范围内），底座没有被拖走 |
| `all_except_milk` | all_variance/0 | "Put all the objects except the milk into the basket" | 否定 | 5 件非牛奶物体在篮子里 ∧ **牛奶留在外面** |
| `soup_left_of_milk` | all_variance/0 | "Place the alphabet soup to the left of the milk" | 空间关系 | 汤罐沿 y 停在离牛奶 6–30 厘米处（「左」的两种读法都接受；哪一侧会被记录），x 方向 ≤ 15 厘米，在桌面上 |
| `both_boxes` | all_variance/0 | "Put both boxes in the basket" | 类别定位 | 恰好两件盒状物品（butter、cream_cheese）在篮子里；罐子/瓶子/纸盒留在外面 |
| `pudding_basket` | all_variance/3 | "Pick up the chocolate pudding and place it in the basket" | 不同的任务场景 + 新物体 | chocolate_pudding 被抓起并停稳在篮子里（场景：布丁、橙汁、烧烤酱、番茄酱、沙拉酱、汤） |
| `oj_swap_scene` | target_basket_swap_variance/5 | "Pick up the orange juice and place it in the basket" | 换篮子套件，2 个种子 | orange_juice 在两种篮子摆放下都被抓起并停稳在篮子里 |
| `pack_scene_all` | libero_object_packing/0 | "Pick all the objects and place them in the basket"（套件自己的任务语言，原样） | 原生打包套件 | 全部 6 件可动物体停稳在篮子里；套件的 `pack_all_into` 奖励作为外部交叉核对被记录 |

扩展运行的种子覆盖：`soup_basket` 和 `cream_cheese` 各 3 个种子，`two_inches_right`、`soup_then_milk` 和 `oj_swap_scene` 各 2 个，其余 1 个（挪篮子的案例留在种子 1，那里「对面」是明确的）。

每个被执行的种子还要过 `scene_sane`：任何物体都不能离开工作空间包络（被甩下桌子 / 穿过地板）；一旦违反，不论任务进展如何，这个种子失败。

## 运行

```bash
# 在合成轨迹上做准则自测（无仿真、无 LLM，约 1 秒）
uv run python examples/zero_shot_prompts/selftest.py

# 一个案例
MUJOCO_GL=egl uv run python \
    examples/zero_shot_prompts/run_prompt.py \
    --case soup_basket --out outputs/zero_shot_prompts/dev

# 整个矩阵（每个案例一个子进程，每案例超时，
# 可续跑：用同一个 --out 再跑会跳过已完成的案例）
MUJOCO_GL=egl uv run python \
    examples/zero_shot_prompts/run_all.py \
    --out outputs/zero_shot_prompts/run1
```

默认：提供商 `vertex`，模型 `gemini-3.1-pro-preview`（用 `--provider/--model` 或 `GAP_LLM_PROVIDER`/`GAP_LLM_MODEL` 覆盖）。如果没设 `GOOGLE_CLOUD_PROJECT`，运行器使用 `~/.config/gcloud/application_default_credentials.json` 里的 ADC 配额项目。运行器还会把 `TMPDIR` 挪到家目录所在卷（视频帧缓冲），并保持 `GAP_DECIDE_TRUST_ENV` 不设置。那个标志会让生成的决策循环信任环境*自己的*任务奖励，而那不是这条提示词的任务。

## 判决是怎么产生的

```
run_all.py ── 子进程 + 超时，卡住时 killpg ──▶ run_prompt.py
  1. 生成        gap.agent.generate_sync(prompt)      → <案例>/gen/task_00
  2. 每个种子    新建 gap.connector.sim(...)；StateRecorder 包住
                 conn.tool_registry.invoke（每个脚本/工具节点调用的
                 唯一分发点）；
                 gap.execute(graph, conn, checkpoints="warn")
                   → seed<k>/events.jsonl   （调用/返回/错误，已刷出）
                   → seed<k>/state.jsonl    （每次调用的真值快照）
                   → seed<k>/run_video.mp4  （外加每相机的附加视频）
  3. 打分        criteria.evaluate_seed(...)          → seed<k>/result_seed.json
                 汇总（PASS = 全部种子通过）           → <案例>/result.json
```

- **卡住：** `call` 事件写在分发*之前*，所以一个挂住的工具会留下一次没有匹配返回的调用，作为最后一条已刷出的行。`run_all.py` 在超时时杀掉进程组，放下 `timeout_marker.json`，并重新给部分轨迹打分（`run_prompt.py --re-eval`）。判决是 `TIMEOUT`，并附上卡住位置（工具、节点、kwargs）。
- **生成拒绝/错误**有自己的判决（`GEN_REFUSED` / `GEN_ERROR`），从不会被悄悄换成任务失败。
- **防投机：** 「被抓起」要求引擎的 `held_body()` 在夹爪闭合时报告该物体，*并且*物体比初始高度高出至少 3 厘米。推一下不算，一件从没被搬运过却出现在篮子里的物体，抓取检查会失败。包含关系镜像 `Body.contains`（外接 AABB 上 ±2 厘米；LIBERO 上的篮子没有登记内部空腔，这是探测出来的）。
- **重新打分：** 准则在已保存的轨迹上迭代很便宜：`run_prompt.py --case X --out DIR --re-eval`。一张手写的图可以不经过生成就做基线：`--graph <工作流目录>`。

## 测得的约定（在 `libero_object_all_variance/0` 上实机探测）

- 快照在**机器人基坐标系**里。在这个环境中它等于 MuJoCo 世界坐标系（robot0_base 在原点，单位旋转）。桌面大约在 z 0。可动物体：alphabet_soup、butter、cream_cheese、milk、salad_dressing、tomato_sauce（加篮子）。
- **Agentview 图像右侧 = +y**（从相机坐标系轴看：相机在世界坐标 (0.90, 0, 0.65)，朝回机器人看）。机器人的右侧是 −y。`two_inches_right` 接受「右」的两种读法，并记录实际采用的方向。
- 汤罐的局部 z 轴在静止时是**水平的**（资产建模如此），所以直立度是相对初始朝上的那条物体方向来量的，不是相对局部 z。
- 初始布局随种子变化（例如篮子在种子 0/2 上生成于 (0.75, 0.03)，在种子 1 上生成于 (0.71, −0.23)）。`soup_basket` 的三种子稳健性门槛练的就是这个变化。
- 执行器自己的节点访问上限（`GAP_ITERATION_CAP`，默认 10000）正是为了限制*重复访问节点*。一张生成的图是否真的含环、节点在运行时是否被重访，每次运行都会根据工作流的边列表和执行器的 `node_data/<节点>/iters/` 布局报告出来。

## 输出

`<out>/report.md`（用 `run_all.py --out DIR --report-only` 重建）放判决表，加上每个种子的检查和诊断。每条结论都可以审计：`state.jsonl`（每次工具调用的真值）、`events.jsonl`（每次调用及 kwargs/结果摘要）、`graph.txt` + `gen/task_00/`（生成的图）、`trace/`（执行器轨迹）、`run_video.mp4`（人会看到的画面）。
