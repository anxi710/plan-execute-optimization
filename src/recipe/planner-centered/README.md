# 四种规划框架的接口验收

本 Recipe 调用 [`toolkit.frameworks`](../../toolkit/README.md#四种运行框架) 中的 EO、PE-S、PE-D 和 PC，负责装配模型、环境、预算与结果分析。框架控制策略和证据协议由 [`frameworks/control.py`](../../toolkit/frameworks/control.py) 的 `run_framework()` 入口维护；四框架与固定计划采样共用 [`RolloutSession`](../../toolkit/rollout/session.py) 的执行循环，批量调度共用 [`sample_jobs()`](../../toolkit/rollout/batch.py)。[组件边界](../../toolkit/README.md#执行与采样的组合)

环境模板、框架协议文本与渲染、解析函数统一从 `toolkit.prompts` 导入。修改内置提示词时，按环境或框架协议编辑对应模板；Executor 自定义文件覆盖方式见[统一提示词](../../toolkit/README.md#统一提示词)。

当前工作区的 Planner 模板只要求高层子目标、前提和证据，不列具体动作命令。Executor 使用环境返回的当前候选动作；候选目录与 Planner 的原始公开观察分开，来源及 Terminal-Bench 的接口例外见[统一提示词](../../toolkit/README.md#统一提示词)。这与下述历史验收的提示协议不同，已有结果和原始 prompt 保持原样，没有按新协议重跑。

本次接口验收用同一个 ALFWorld 开发任务检验控制流和证据隔离。请求、返回、隔离验收与对照要求参考本地测试提案 `Planner_Centered_Test_Proposal.pdf` 的 §2、§5 和 §6.2。该 PDF 不纳入 Git。测试提案的三组主比较与本次四组接口验收属于不同阶段。

各组独立加载同一个已核对的 `dev/2` 游戏。组内持续使用同一个环境和 Executor 对话。运行器在完成两个原子动作轮后检查返回边界。格式错误也消耗动作轮额度。Executor 可调整软指导，使用各组共有的工具与提示词。PE-D 和 PC 延续已完成工具动作的结果。PC 使用固定阶段额度，由 Planner 决定下一阶段或是否结束。

Planner 可见任务、规划、初始观察、公开动作与观察及来源明确的 Executor 陈述。未验证假设单独保存。执行额度、返回间隔等技术限制由运行器执行和记录，不告知模型；具体输入边界见[框架接口](../../toolkit/README.md#四种运行框架)。ALFWorld 的原生任务结束信号可触发收尾，PC 可在运行器允许时记录结束建议，`won` 与奖励只在停止后写入验收记录。任务终局始终由环境判定。停止并记录原生判定后不再发起模型调用或环境动作。文本动作同步返回，所以本适配器可在动作之间安全续接。非原子操作中途暂停和后端原生阶段返回留待其他适配器验证。

## 运行

从仓库根目录运行，使用[工具集 Python 环境](../../toolkit/README.md#环境与数据)和已有 ALFWorld 数据。`RUN_DIR` 指向新的本地目录。`ALFWORLD_GAMEFILES` 指向包含 `dev/2` 的已核对游戏映射，例如历史战略采样运行的 `gamefiles.jsonl`。CLI 从环境读取 `TONGJI_API_KEY`，请求走[同济人工智能服务平台](https://nic.tongji.edu.cn/fwzn/kyfw/rgznfwpt.htm)。如果本机已在学校网络且代理把请求送到校外，为本次进程在 `NO_PROXY` 和 `no_proxy` 中加上 `agi.tongji.edu.cn`。

```bash
PYTHONPATH=src python src/recipe/planner-centered/run.py \
  --data-dir "$ALFWORLD_DATA" \
  --gamefiles "$ALFWORLD_GAMEFILES" \
  --run-dir "$RUN_DIR"
```

每组最多 12 次 Executor 请求，PE-S 最多 1 次 Planner 请求，PE-D 和 PC 各最多 6 次 Planner 请求。两类角色都使用 `DeepSeek-V4.1-Flash`，请求设 `reasoning_effort=none`。Executor 固定温度 0.6、最多 256 个输出 token。Planner 固定温度 0.2、最多 512 个输出 token。每次调用设 60 秒超时，均无自动重试。每轮四组合计最多 61 次请求、18,944 个输出 token。每次请求的序列化消息上限为 11,000 个 UTF-8 字节。

`manifest.json` 保存实际配置、路径、版本与边界。各组 JSON 保存公开提示、回复、用量、工具返回、结束理由和隔离验收。`tool_event.dispatched` 标记动作是否送到环境。格式错误的反馈仍有事件编号，回查时可与实际环境动作区分。

使用原始记录生成可离线阅读的 `experiments/planner-centered/audit.html`：

```bash
PYTHONPATH=src python src/recipe/planner-centered/report.py --run-dir "$RUN_DIR"
```

## 离线检查

```bash
PYTHONPATH=src python -m unittest discover -s src/toolkit/tests -q
PYTHONPATH=src python -m unittest discover -s src/recipe/planner-centered/tests -q
```

框架检查使用脚本化模型验证模式隔离、状态持续、预算、证据、错误和终局语义；Recipe 检查覆盖调度、存储、后端适配和结果导出。真实调用用来核对这些结构是否实际出现。这个已见开发任务用于接口联调。正式成功率、成本比较与学习收益需要独立的任务和实验协议。

[本次真实验收记录](../../../experiments/planner-centered/README.md)保存完整轨迹、首轮失败和两轮对应的源码补丁。

## 完整测试集

本轮继续正式评分的 benchmark 是 ALFWorld。将 `DeepSeek-V4.1-Flash`、`MiniMax-M3.1-Flash`、`GLM-5.3-Flash` 和 `Qwen3.8-27B` 与四种框架配对。每格运行一次，同一模型组的 Planner 和 Executor 使用同一模型。各框架共用对应环境的工具和执行额度。原生分数保留，无法取得分数的运行故障记缺评。WebShop 和 ScienceWorld 已停止，已有分数用于同任务比较。Terminal-Bench 已终止，已出分数交人工核验。[实验记录](../../../experiments/planner-centered/README.md#完整测试集评测)

Planner 和 Executor 的输出上限分别为 1,536 和 768 token。各模型均请求 `reasoning_effort=none`，推理用量取服务端实际记录。调度顺序种子为 417，模型采样 seed 未指定。默认四路并行。用同一个本地 `PLANNER_BENCHMARK_RATE_FILE` 路径启动多个进程，可让所有角色和模型共用每分钟 100 次的本机请求限速。设置 `PLANNER_BENCHMARK_UNPACED=1` 可取消本机限速，运行清单逐次记录该选择和并发度。单次请求无自动重试。用 `--resume` 恢复中断及可重试的缺评，原始尝试放入 `attempts/`，已取得原生分数的轨迹直接保留。已归档且确定发生在首个事件之前的环境启动错误不占模型尝试额度。

### ALFWorld

使用 ALFWorld 0.4.2 的全部 134 个配置内 `valid_unseen` 测试游戏。测试 ID 对应本地历史游戏路径表的行号。每个 ID 的初态由对应游戏复位获得，与现有规范文本的整体多重集合相同。重复初态文本不用于猜测旧任务号的归属。每条最多 12 次 Executor 请求。两个在线模式每两轮读取反馈，最多 6 次 Planner 请求。

```bash
PYTHONPATH=src python src/recipe/planner-centered/benchmark.py \
  --data-dir "$ALFWORLD_TEST_OVERLAY" \
  --gamefiles "$ALFWORLD_TEST_GAMEFILES" \
  --run-dir "$BENCHMARK_RUN_DIR"
```

### WebShop

按 Princeton 官方源码 `64fa2a5` 的原生目标顺序执行前 500 个测试会话。采用完整商品镜像和原生 Lucene 索引，每次任务独立复位，使用同一个只读索引。准备入口用 `--catalog`、`--attributes`、`--human-annotations` 和 `--official-goals` 指定原始数据，从 `webshop_catalog.py` 生成并核验 `--data-dir`。运行入口要求核验通过的目录。使用原生购买分数，满分为成功。

```bash
PYTHONPATH="src:$WEBSHOP_UPSTREAM" python src/recipe/planner-centered/webshop_benchmark.py \
  --data-dir "$WEBSHOP_TEST_CATALOG" \
  --run-dir "$BENCHMARK_RUN_DIR"
```

对输入超过字节上限且请求尚未发送的轨迹，用同一个运行目录和目录数据，加 `--replay-native` 原生重放。仅当初态和所有已记录的动作、观察与有效性完全匹配时，才在 `native-replay/` 写入评分。重放保留原始轨迹和清单，无额外模型调用。

### ScienceWorld

使用 ScienceWorld 1.2.3 从内置 Java 模拟器列出的 30 类、1,819 个 `test` 变体。仓库原有的 211 条是这些变体的一套历史样本。沿用 `easy` 简化设置及已有 `max_steps.json` 的逐类上限，未列出的类使用原生服务器 200 步上限。动态返回间隔为四轮。科学任务允许部分得分，按原生分数除以 100 展示。当前轨迹和历史尝试用 `.json.gz` 保存，HTML 链接指向原始压缩记录，运行清单保持普通 JSON。

```bash
PYTHONPATH=src python src/recipe/planner-centered/sciworld_benchmark.py \
  --prepare --catalog-dir "$SCIWORLD_TEST_CATALOG"

PYTHONPATH=src python src/recipe/planner-centered/sciworld_benchmark.py \
  --catalog-dir "$SCIWORLD_TEST_CATALOG" \
  --step-limits "$SCIWORLD_DATA/max_steps.json" \
  --model DeepSeek-V4.1-Flash \
  --run-dir "$BENCHMARK_RUN_DIR"
```

### Terminal-Bench

按 v4.1.0 的 66 个官方任务记录覆盖率。目前评测入口只接受已通过隔离预检的指定任务版本。每条轨迹最多 40 次 Executor 请求，在线模式每四轮返回。Harbor 0.26.0 为每条轨迹创建单独的工作环境。Executor 停止后，独立 Verifier 读取提交产物并给出原生奖励。两个容器均断网。已审阅任务和原生记录见[评测记录](../../../experiments/planner-centered/README.md#完整测试集评测)。

```bash
PYTHONPATH=src python src/recipe/planner-centered/terminal_benchmark.py \
  --terminal-bench-root "$TERMINAL_MUSIC_CHECKOUT" \
  --additional-task-root fin-saccr-rwa "$TERMINAL_FINANCE_CHECKOUT" \
  --additional-task-root photonic-waveguide-routing "$TERMINAL_PHOTONIC_CHECKOUT" \
  --additional-task-root production-planning "$TERMINAL_PRODUCTION_CHECKOUT" \
  --additional-task-root sound-change-cascade "$TERMINAL_SOUND_CHANGE_CHECKOUT" \
  --additional-task-root mvcc-lsm-compaction "$TERMINAL_MVCC_CHECKOUT" \
  --additional-task-root vf2-speedup-networkx "$TERMINAL_VF2_CHECKOUT" \
  --additional-task-root batched-eval-parity "$TERMINAL_BATCHED_CHECKOUT" \
  --additional-task-root coq-block-bound "$TERMINAL_COQ_CHECKOUT" \
  --additional-task-root ks-solver-cpp "$TERMINAL_KS_CHECKOUT" \
  --additional-task-root embedding-drift-monitor "$TERMINAL_EMBEDDING_CHECKOUT" \
  --additional-task-root cargo-flight-dispatch "$TERMINAL_CARGO_CHECKOUT" \
  --additional-task-root ontology-kg-querying "$TERMINAL_ONTOLOGY_CHECKOUT" \
  --additional-task-root wal-recovery-ordering "$TERMINAL_WAL_CHECKOUT" \
  --additional-task-root risk-scorer-replay "$TERMINAL_RISK_CHECKOUT" \
  --run-dir "$BENCHMARK_RUN_DIR"
```

生成正式验收页时，为每份已完成的评测清单传一个 `--benchmark-dir`。Terminal-Bench 的补充批次只有在任务互不重叠且原生评分协议一致时才一起汇总。验收页用同一模型四种框架均有评分的任务比较框架，用所有模型和框架均有评分的任务比较模型。两种配对各自显示任务数。

`PYTHONPATH=src python src/recipe/planner-centered/preview.py` 从当前原始轨迹生成阶段性比较页。页面列出读取时段、六组两两比较及共同任务 ID。已停止的 WebShop 和 ScienceWorld 也可用已有分数复核。

[ALFWorld 独立结果页](../../../experiments/planner-centered/alfworld.html)从原审查页拆出，集中展示最新完整结果、原始交互轨迹与双栏对比。每次调用的完整 prompt 按原始 role 顺序逐条展示，response 逐字保留，不转换字段、不截断。在仓库根目录运行 `PYTHONPATH=src conda run -n plan-test python src/recipe/planner-centered/export_alfworld.py`，将最终合并清单和全部 2,144 条最终轨迹导出到 `experiments/planner-centered/alfworld/data/`，再用 `npm --prefix web run build:alfworld` 构建独立 HTML。导出只读取现有记录，归档尝试计入成本，轨迹在页面按需加载。[使用与本地服务说明](../../../experiments/planner-centered/README.md#完整测试集评测)

ALFWorld 的外部故障补跑使用 [recover_alfworld.py](recover_alfworld.py)。用 `--wave N --dry-run` 核对该轮名单和请求上限。每轮只为当前仍有外部故障缺评的组合增加一次尝试，独立运行目录保留前序结果和费用。生成正式报告时将 `--benchmark-dir` 指向最新补跑目录。重新生成比较页时用 `--alfworld-run` 指定该目录名。

### 已中断的开发预跑

在 ALFWorld `dev` 上配对运行 `DeepSeek-V4.1-Flash`、`MiniMax-M3.1-Flash`、`GLM-5.3-Flash` 和 `Qwen3.8-27B`。每个模型各执行四种框架。组内的 Planner 和 Executor 使用同一个基座模型。每个模型、框架和任务组合独立重置一次，共 64 条轨迹。

运行前冻结四个任务。每类从已核对映射的任务中选公开初态里编号容器数最少的一项，同分取数值 ID 最小者。排除接口验收用的 `dev/2`。挑选时只读任务族和初始观察。

| `dev` ID | 任务族 | 可见编号容器数 |
| --- | --- | ---: |
| `25` | 放置单个物体 | 9 |
| `79` | 清洁后放置 | 12 |
| `109` | 在灯下查看物体 | 7 |
| `124` | 放置两个物体 | 9 |

采用测试提案中的「相同执行机会」口径。每条最多 12 个 Executor 请求。PE-D 和 PC 每两轮返回一次，各最多 6 次 Planner 请求。PE-S 只有一次初始 Planner 请求。各模型用相同角色温度、60 秒超时和零自动重试。Planner 和 Executor 输出上限分别为 1,536 和 768 token，序列化输入上限为每请求 32,000 UTF-8 字节。各模型均请求 `reasoning_effort=none`，以服务端实际报告的推理用量为准。模型预检只使用合成提示。运行顺序用种子 417 打乱，并行上限为 4。模型采样 seed 未指定。

开发预跑在研究者明确要求完整测试集后停止。该批次用于诊断协议格式及网关限额，记录独立保存在 `experiments/planner-centered/runs/benchmark-01/`。
