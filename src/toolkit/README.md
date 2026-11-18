# Planner Experiment Toolkit

`src/toolkit/` 是 Planner 实验的基础库。`src/recipe/` 保存可运行的实验方案，`experiments/` 保存结果和证据。这个分工参考 veRL 的基础库与 recipe。[veRL recipe 说明](https://github.com/verl-project/verl-recipe)

## 基础库与 Recipe

基础库提供模型、环境、提示词、任务加载和轨迹等可复用组件。Recipe 使用 toolkit 中已有的对应组件，包括提示词与解析逻辑。替换或自行实现已有组件须取得研究者明确授权。依赖方向由 recipe 指向 toolkit。每份 recipe 负责装配组件、编排实验流程，并记录选用的模型、提示词、benchmark、对照条件和预算。Python 环境由调用方提供。

## 统一提示词

Recipe 选择 benchmark 并提供输入，模板和解析方式由 toolkit 维护。

| 角色 | 输入 | 输出 |
| --- | --- | --- |
| Planner | `render_planner_prompt(benchmark, task)` 接收 `alfworld`、`sciworld`、`webshop` 或 `terminalbench`，以及 benchmark 提供的完整任务文本。模板填入 `<task>`，并说明环境约束。 | 回复使用 `<plan>...</plan>`，按步骤列出计划。`extract_plan()` 取首个标签正文。沿用原解析规则，回复缺少标签时保留去除首尾空白后的文本。 |
| Executor | ALFWorld、ScienceWorld 或 WebShop 的执行指令、当前任务和每步环境反馈。可按 `query`、`observation` 或 `thought` 注入已有计划。 | 每步含一行非空 `Action: ...`，前面可带 `Thought:`。环境适配器执行解析出的动作并生成下一条观察。 |

Planner 的指令文本在 `prompt/planner/instruction/`，由 `prompt/planner/templates.py` 加载和渲染。计划解析在 `prompt/plans.py`。Executor 的指令文本在 `prompt/executor/instructions/`，由 `prompt/executor/template.py` 加载和渲染。[ALFWorld 战略采样 Recipe](../recipe/strategy-sampling/README.md#运行)

## 计划提供的能力

| 组件 | 职责 |
| --- | --- |
| 提示词与解析 | 提供可复用的 Planner 和 Executor 提示词，明确所需输入和输出格式。 |
| 模型调用 | 支持限并发请求，返回原始回复、结束原因和 token 用量。 |
| Agent 执行 | 提供可组合的 Agent 组件和执行循环，支持实验自行编排规划与执行。 |
| Benchmark 与环境 | 加载指定划分和任务实例，提供环境重置、动作执行与终局反馈接口。 |
| 文件与日志 | 解析任务和计划文件，保存生效配置、运行状态、轨迹和成本。 |

具体允许使用的提示词、benchmark 和框架逐项确认。实验脚本从中选择组件，定义采样策略、对照条件、预算、重复次数和分析方式。运行时可以按事先定义的策略使用前序结果，例如根据已生成的路线决定下一次采样。[实验目录](../../experiments/README.md)

## 当前实现

| 目录 | 职责 |
| --- | --- |
| `agents/` | `BaseModel` 定义调用和计量接口。`AsyncChatClient` 支持限并发的 OpenAI 兼容请求，`MeteredExecutor` 复用该客户端并计量执行用量。 |
| `tasks/` | 按任务 ID、划分和分片选择任务，校验计划与任务的对应关系。ALFWorld 支持生成 `task_id → gamefile` 映射，SciWorld 按子任务与 variation 加载。 |
| `envs/` | `BaseEnv` 管理对话、动作轨迹和步数。ALFWorld、SciWorld 和 WebShop 适配器处理初态、动作反馈和 benchmark 的终局判定。 |
| `prompt/` | 管理统一的 Planner 和 Executor 提示、计划注入和输出解析。 |
| `planning/` | `generate_plans()` 使用统一模板批量生成计划，记录用量并支持校验与续跑。 |
| `rollout/` | 采样单条或一批轨迹。记录检查点、终局与中断，并读取、核对及筛选已有轨迹。 |
| `utils/` | 读写 JSON 和 JSONL，写入时原子替换目标文件。 |

## 组合运行

基础库默认值在 [`src/toolkit/config.yaml`](config.yaml)。调用方可显式传参，或调用 `resolve_config()` 派生一份配置，不改写公共文件。实验方案的参数由各 Recipe 自己管理。[战略采样配置示例](../recipe/strategy-sampling/config.yaml)

- `tasks.rows.load_task_rows()` 可选择 canonical 任务并绑定计划文件。`tasks.alfworld.prepare_gamefile_map()` 从本地环境生成映射。并发执行时，每条 ALFWorld 轨迹用已确认的游戏文件重新初始化。
- `toolkit.planning.generation.generate_plans()` 接收任务行或任务 JSONL，用指定 benchmark 的统一模板为每个任务生成一份计划。输出记录回复、用量和实际设置，续跑时跳过已经保存且通过校验的任务。
- `rollout.batch.run_rollouts()` 接收样本队列、模型和环境组件，按并发上限采样。Recipe 提供每条样本的 seed 和结果路径，决定是否续跑。`load_saved_rollout()` 校验记录属于哪条样本，显式重试时调用 `archive_incomplete_rollout()` 保留中断轨迹。
- `rollout.traces.load_trace()` 读取已完成轨迹，`load_records()` 可按任务、样本和成功状态筛选，`conversation_parts()` 核对每条环境反馈与消息记录。

SciWorld 可用 `tasks.sciworld.SciWorldTask.load_tasks()` 和 `envs.sciworld_env.open_sciworld_backend()` 装配。默认使用安装包内的 JAR。历史环境如需指定自己的 JAR，显式传入 `jar_path`。

## 环境与数据

| 后端 | Python 3.11 运行依赖 | 旧评测目录如何复用 |
| --- | --- | --- |
| [ALFWorld 0.4.2](https://pypi.org/project/alfworld/0.4.2/) | [TextWorld 1.7.0](https://pypi.org/project/textworld/1.7.0/)、`base_config.yaml` 和配置指向的游戏数据。上游用 `traj_data.json` 筛选任务类型，用 `game.tw-pddl` 加载可运行游戏。文本模式不需要 Java 或视觉权重。 | 可挂载原 `data/alfworld/`，复用 `json_2.1.1/` 下的游戏和配套 `logic/`。`alfworld_<split>_tasks.jsonl` 是项目的选题文本；重复 rollout 使用已核对的 JSONL 游戏映射，不读取旧 `gamefile_id.txt`。 |
| [ScienceWorld 1.2.3](https://pypi.org/project/scienceworld/1.2.3/) | Java（本项目验证 OpenJDK 21）和 Py4J。wheel 内置模拟器 JAR 和任务目录，无需另下载游戏数据。 | 可挂载原 `data/sciworld/`。`sciworld_<split>_tasks.jsonl` 固定任务和 variation；`max_steps.json` 提供项目的逐类预算。Toolkit 不直接读取旧 `*_indices.json` 或 `taskname2id.json`，默认也不读取旧 JAR。 |

ALFWorld 无现成数据时，按[官方指南](https://github.com/alfworld/alfworld#quickstart)准备游戏数据。官方 `alfworld-download` 默认也下载视觉检测器，但文本回放不使用它；已有游戏数据无需重复下载。上游游戏数据不替代项目选题 JSONL。ScienceWorld 不需要预先打开所有容器；[官方说明](https://github.com/allenai/ScienceWorld#simplifications)中的 `easy` 不含 `openContainers`。

ScienceWorld 的 `environments.sciworld.max_steps` 为 `null` 时读取数据目录中的逐类预算。Recipe 可将它覆盖为正整数。两种文本环境均已回放至真实成功终局。ALFWorld 回放了已保存的 `dev` 任务 2 的四步动作，ScienceWorld 回放了非生物分类任务 variation 225 的七步官方参考动作。

WebShop 使用 [Princeton 官方源码快照](https://github.com/princeton-nlp/WebShop/tree/64fa2a5c15c7daa698b9ac93f5bb5437b634c9bd) 的文本 API。Python 3.11、Java 21、PySerini 0.17.0 和 NumPy 1.26.4 已用 1,000 商品索引验证任务选取和两次完整 rollout。脚本 Executor 各用三步完成搜索、点击和购买，原生奖励均为 1。测试数据来自[公开镜像 `ce990ff`](https://huggingface.co/datasets/YWZBrandon/webshop-data/tree/ce990ff)，未核对其与 Google Drive 原件的字节一致性。未验证全量商品库或浏览器环境。

任务文件 `webshop_<split>_tasks.jsonl` 每行需要 `id`、`task` 和整数 `session`。固定商品目录、索引和 `environments.webshop.catalog_seed` 后，用同一个 goal index 重置，并核对目标文本。购买时记录原生分数，仅满分算成功。

[Terminal-Bench 4.1](https://github.com/harbor-framework/terminal-bench/releases/tag/v4.1.0) 支持读取已核查的本地任务说明和导入 Harbor 评分。`TerminalBenchTask.load()` 读取 `task.toml` 和 `instruction.md`，只接受 `toolkit/config.yaml` 中列出的任务及版本。把 `task.planner_row()` 放入 `generate_plans()` 的任务列表，选用 `terminalbench` 模板。

`rollout.terminalbench.load_terminalbench_trial()` 读取官方 trial 的 `result.json` 和同目录的 `lock.json`，核对任务名称和版本，并区分有效零分与无评分。归档时一起保留这两个文件。任务执行与评分由独立的 Harbor 负责。[Harbor 0.26.0 的 Python 版本要求](https://pypi.org/project/harbor/0.26.0/)

本机已运行 `music-harmony` 2.2.1 的官方解法并生成乐谱。首次构建评分镜像遇到镜像站连接问题。补评分从官方 Registry 拉取相同 digest 的基础镜像，并缓存锁定依赖。Harbor 对原乐谱的 13 项检查全部通过，原生奖励为 1。Python 3.11 toolkit 已验证可导入该分数。

### Conda

按 Recipe 选用的 benchmark 创建对应环境。ALFWorld 和 ScienceWorld 共用 Python 3.11。WebShop 文本后端单独安装旧版 Gym、NumPy 1.26 和 Java 搜索依赖。Harbor 使用 Python 3.12。拆分方式参考 [verl-agent 的环境安装说明](https://github.com/langfengQ/verl-agent#install-supported-environments)。

从仓库根目录运行相应命令。已有环境可以用于检查。本机测试使用 `plan-test` 和隔离的依赖安装目录。

#### ALFWorld 与 ScienceWorld

```bash
conda create -n planner-worlds --override-channels -c conda-forge \
  python=3.11 pip openjdk=21 c-compiler cxx-compiler make cmake
conda activate planner-worlds
python -m pip install -r src/toolkit/requirements.txt
java -version
```

编译工具用于安装 TextWorld 的源码依赖。两个后端可使用上文列出的本地数据。

#### WebShop 文本后端

```bash
conda create -n planner-webshop --override-channels -c conda-forge \
  python=3.11 pip openjdk=21
conda activate planner-webshop
python -m pip install --index-url https://download.pytorch.org/whl/cpu torch==2.13.0
python -m pip install -r src/toolkit/requirements-webshop.txt
python -m pip install --no-deps pyserini==0.17.0
java -version
```

这组命令使用 Linux 的 CPU PyTorch。激活 Conda 环境会设置 `JAVA_HOME`，供 PyJNIus 加载 Java 21。PySerini 声明的 Cython、SentencePiece、nmslib 和 LightGBM 仍会出现在 `pip check` 的缺项中，文本索引与检索路径用不到这些包。下一步准备源码、商品数据和索引。[WebShop 文本检查](#webshop-文本检查)

#### Terminal-Bench 的 Harbor

```bash
conda create -n planner-harbor --override-channels -c conda-forge python=3.12 pip
conda activate planner-harbor
python -m pip install harbor==0.26.0
harbor --version
docker --context default compose version
docker --context default info --format '{{.ServerVersion}}'
```

这套环境用来运行 Harbor CLI。本地评测使用宿主机 Docker。任务读取、Planner 提示和评分导入可直接在 Python 3.11 的 toolkit 环境运行。

使用官方 `v4.1.0` 源码中的 `tasks/music-harmony` 做单任务检查。令 `TERMINAL_BENCH_ROOT` 指向该 checkout，`JOBS_DIR` 指向保存结果的目录。这一步执行官方解法和评分，不调用模型 API。[任务版本](https://github.com/harbor-framework/terminal-bench/tree/v4.1.0/tasks/music-harmony)

```bash
DOCKER_CONTEXT=default BUILDX_BUILDER=default HARBOR_TELEMETRY=0 harbor run \
  --path "$TERMINAL_BENCH_ROOT/tasks/music-harmony" --agent oracle --env docker \
  --n-attempts 1 --n-concurrent 1 --jobs-dir "$JOBS_DIR"
```

评分导入使用试验子目录中的 `result.json`，即与该试验的 `lock.json` 并列的文件。

### Docker 工作区

[项目 Dockerfile](../Dockerfile) 和构建上下文都在 `src/`。项目镜像包含 Python 3.11、ALFWorld、ScienceWorld、Java 21 和 Node.js 22。进入容器后，从仓库根目录启动 Recipe、网站或测试。仓库挂载到 `/workspace`，配置修改与实验产物留在宿主机。环境数据单独只读挂载。

```bash
docker --context default build --builder default --load \
  -t planner-research:py311 src
docker --context default run --rm -it --init \
  --user "$(id -u):$(id -g)" -e HOME=/tmp \
  -e DEEPSEEK_API_KEY -e EXECUTOR_API_KEY \
  --mount "type=bind,source=$PWD,target=/workspace" \
  --mount "type=bind,source=$BENCHMARK_DATA_DIR,target=/data,readonly" \
  -p 127.0.0.1:5173:5173 planner-research:py311
```

`BENCHMARK_DATA_DIR` 指向含 `alfworld/` 和 `sciworld/` 的目录。进入后可运行 `python src/recipe/strategy-sampling/execute.py --run-dir "$RUN_DIR" --data-dir /data/alfworld`，其中 `RUN_DIR` 是已备好执行队列的容器内路径。要开发网站，运行 `npm --prefix web ci --include=dev`，再从 `web/` 运行 `npm exec -- vite --host 0.0.0.0 --port 5173 --strictPort`。仅运行 Python 时可省略端口映射，仅使用网站时可省略数据挂载和模型密钥。构建与运行显式指定同一个 Docker context，不依赖 Kiri 的全局构建器选择。

依赖相同的 Recipe 共用项目镜像。模型、数据路径和采样协议在各自的 `config.yaml` 中设置。Recipe 需要容器化的专用依赖时，可按 Python、系统库或硬件要求派生镜像。WebShop 的专用依赖目前通过上面的 Conda 环境安装。Harbor 自身的运行环境、Terminal-Bench 的任务与评分镜像各自独立。

## 扩展组件

新增使用同类提示和动作格式的环境时，继承 `BaseEnv` 并实现 `execute_action()`。环境返回观察、奖励、动作有效性和终局结果。`success` 由 benchmark 判定，即使部分完成给出正奖励，也可以报告失败。

新增模型后端时，继承 `BaseModel` 并实现 `_complete()` 和 `_async_complete()`。后端负责请求参数、重试和响应解析，每收到一条回复就把解析出的模型名称与 token 用量交给基类。日志字段 `requests` 统计逻辑调用，单次调用内部重试共用一次计数。

## 使用与检查

以下命令从仓库根目录运行工具集离线测试。使用上文的 `planner-worlds`、`planner-webshop` 或项目 Docker 工作区。Recipe 的集成检查见对应的运行说明。[战略采样 Recipe](../recipe/strategy-sampling/README.md#运行)

```bash
PYTHONPATH=src python -m unittest discover -s src/toolkit/tests -q
```

为同一命令设置 `TOOLKIT_ALFWORLD_DATA` 与 `TOOLKIT_ALFWORLD_GAMEFILES` 可测试一个已匹配的 `dev` 游戏；后者指向现成的 `gamefiles.jsonl`。设置 `TOOLKIT_SCIWORLD_DATA` 可测试一个非生物分类任务。未配置的后端跳过。检查不调用模型 API。

### WebShop 文本检查

先创建并激活上面的 `planner-webshop` 环境。[安装命令](#webshop-文本后端)

把官方快照检出到 `WEBSHOP_ROOT`，在其 `data/` 放入 `items_shuffle_1000.json`、`items_ins_v2_1000.json` 和 `items_human_ins.json`。按[上游数据准备说明](https://github.com/princeton-nlp/WebShop/blob/64fa2a5c15c7daa698b9ac93f5bb5437b634c9bd/setup.sh)取这些文件，不要直接运行其中的旧版依赖安装步骤。只建文本测试需要的一个索引：

```bash
(
  cd "$WEBSHOP_ROOT/search_engine" || exit 1
  mkdir -p resources resources_100 resources_1k resources_100k
  python convert_product_file_format.py
  python -m pyserini.index.lucene --collection JsonCollection \
    --input resources_1k --index indexes_1k --generator DefaultLuceneDocumentGenerator \
    --threads 1 --storePositions --storeDocvectors --storeRaw
)
PYTHONPATH="src:$WEBSHOP_ROOT" TOOLKIT_WEBSHOP_SMOKE=1 \
  python -m unittest discover -s src/toolkit/tests -p test_live_backends.py -q
```
