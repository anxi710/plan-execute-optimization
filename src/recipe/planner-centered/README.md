# Planner-Centered Recipe

本入口为 [planner-centered-v2](../../../experiments/planner-centered-v2/README.md) 准备未经本项目专项训练的框架性能测试。复用 `toolkit.frameworks`，只支持 `two-phase-v3` 的 EO、PE-S、PE-D-F/S 和 PC-F/S。旧实验文件保留，当前代码不提供旧控制流、旧字段解析、历史评分回填或跨运行融合；重现旧实验需检出对应源码。

## 配置与单任务验收

[config.yaml](config.yaml) 覆盖 [Toolkit 默认配置](../../toolkit/config.yaml)。连接、模型名和推理选项按角色配置，密钥不写入运行清单。`planner_generation.model_name: null` 表示 Planner 使用所选 Executor 的模型名，具体解析后的设置写入 manifest。

当前两个角色经本机 Magpie 的原生透传入口 `http://127.0.0.1:3425/v1/magpie/native/tongji/v1` 调用同济服务，使用裸上游模型名和本机通行值 `api_key: magpie`。该值不是同济密钥，上游凭据由 Magpie 管理。[官方连接说明](https://github.com/yetone/magpie/blob/v0.1.4657/docs/reference.md#connecting-anything-else)说明 native 路径用法。Magpie 的隐私遮蔽仍可能改写正文，不能仅据路径断言逐字节透传。

两个角色均可配置 `thinking` 和 `reasoning_effort`；`null` 表示不发送。通用客户端不按服务商名称转换字段。当前请求 `reasoning_effort: none`；[本轮单任务](../../../experiments/planner-centered-v2/README.md#本轮单任务实机验收)的 31 次响应均显式报告推理 token 为 0，但不能据此确定旧异常的原因。适配器保留返回的 `reasoning`／`reasoning_content`，与正文及框架 `assessment` 分开。

Toolkit 的 `context_window.max_input_tokens` 控制输入窗口，当前默认为 `null`，不预设容量。历史交互嵌入 prompt 正文；超过已设上限时淘汰最早完整交互，保留当前任务、计划、当前观察及必要工具配对。完整日志保留，没有自动摘要。默认使用明确标记的 UTF-8 保守估计，可注入模型 tokenizer；估计与服务端实际输入用量分开记录。Recipe 不再设独立请求体字节上限。

真实模型运行需要先按新实验文档冻结任务、模型和预算。以下为入口示例，不代表已批准启动：

```bash
PYTHONPATH=src python src/recipe/planner-centered/run.py \
  --data-dir "$ALFWORLD_DATA" \
  --gamefiles "$ALFWORLD_GAMEFILES" \
  --run-dir experiments/planner-centered-v2/runs/dev2-01
```

单任务入口固定 `dev/2`、配置的 Executor 模型、六配置、并发 1。当前开发默认每组最多 20 个真实环境步。非 EO 首先直接生成规划；只有 PE-D 的 Executor 注册 `request_plan`；PC 固定单步执行、反馈、监测。规划求助和本地拒绝不计环境步，所有模型请求计成本。

提示词由框架按实际 `mode` 与 benchmark 从 `toolkit/prompts/<mode>/<benchmark>.py` 加载。六配置各有目录，Full/sub 分开；每份模块包含其实际需要的 Planner、Executor、格式和工具说明。PE-D 明确单轮行动／求助二选一，不再叠加环境通用 Action 要求与求助例外。显式 `instruction_path` 仍替换 Executor 指令，文件需自行给出该配置的输出规则。[提示词目录与接口](../../toolkit/README.md#统一提示词)

## ALFWorld 矩阵入口

```bash
PYTHONPATH=src python src/recipe/planner-centered/benchmark.py \
  --data-dir "$ALFWORLD_DATA" \
  --gamefiles "$ALFWORLD_GAMEFILES" \
  --run-dir experiments/planner-centered-v2/runs/alfworld-01 \
  --config src/recipe/planner-centered/config.yaml \
  --concurrency 4
```

默认核对全部 134 个官方 test game。指定 `--split dev --task-id 2` 可只选开发任务。模型顺序来自配置的 `models`。清单冻结实际模型、提示采样、环境版本、上下文设置、真实步预算、顺序 seed 和代码状态。当前已授权矩阵为 Qwen Planner／DeepSeek Executor 的 804 条测试，范围与预算见[固定协议](../../../experiments/planner-centered-v2/README.md#完整测试集评测qwen-planner-与-deepseek-executor)；其他配置不因保留默认值自动获准运行。

`--resume` 仅恢复同一当前协议运行中未完成或可重试的外部故障。运行锁阻止并发改写同一目录，完成评分不重跑；每格最多两次尝试，原文件先归档，所有尝试成本计入。清单不匹配时拒绝恢复，不把旧运行重标为新协议。

ALFWorld 矩阵的预检与任务调度共用 `pool.reuse_slots()`，归还后的完整后端供后续任务重载，借出期间独占。并发 4 时最多持有 4 个后端；退出作用域统一关闭。该资源修复限制 `fast_downward` 已删除动态库副本的累积，不改任务初态、模型输入或评分。run02 已完成对 606 条无事件 `OSError` 启动失败与 7 条服务端故障各一次的恢复；首轮 116 条已有评分与 75 条协议缺评均未重跑。最终为 465 条有分、339 条缺评，全部失败尝试与成本保留。[故障证据](../../../experiments/planner-centered-v2/README.md#run02-quota-中断与恢复) · [最终结果与异常审查](../../../experiments/planner-centered-v2/README.md#完整测试结果与最终异常审查)

默认每分钟最多 100 次请求，Planner 和 Executor 共用限速。多个进程可通过同一个 `PLANNER_BENCHMARK_RATE_FILE` 共享派发节奏。`PLANNER_BENCHMARK_UNPACED=1` 仅用于明确选择不限速的环境，实际设置写入清单。网络可用性与凭据检查不代替模型行为验收。

## 其他后端

以下入口也迁至当前协议，但尚未纳入新实验的已冻结范围。依赖及数据要求见 [Toolkit](../../toolkit/README.md#环境与数据)，来源限制见各环境的历史记录；当前没有重新启动旧批次。

| 入口 | 所需参数与职责 |
| --- | --- |
| [sciworld_benchmark.py](sciworld_benchmark.py) | `--catalog-dir`，先 `--prepare` 无模型生成目录；运行另给 `--run-dir`，可用 `--step-limits` 和 `--model` 明确选择。 |
| [webshop_benchmark.py](webshop_benchmark.py) | `--data-dir`、`--run-dir`；当前代码不重放旧缺评轨迹补分。 |
| [terminal_benchmark.py](terminal_benchmark.py) | `--terminal-bench-root`，选择 `--preflight-output` 或 `--run-dir`；原生验收依赖 Harbor／Docker。已审核任务限制保留，不自动扩大任务范围。 |

这些入口均支持 `--config`。真实后端检查与模型调用分开记录；缺少可选依赖时不能将离线通过说成后端运行成功。

## 轨迹与报告

每个 run 保存 manifest、当前 trials 与归档 attempts。评分来源是实际环境终局／独立原生验收；缺评保持 `null`，不能折算零分。`assessment` 是 Planner 的状态或阶段判断，不是隐藏推理总结，也不是成功真值。Observation 从 1 连续编号，日志 event_id 另记，引用按 observation_id 定位。

单 run HTML 报告及 ALFWorld 查看页只消费当前协议：

```bash
PYTHONPATH=src python src/recipe/planner-centered/report.py \
  --run-dir experiments/planner-centered-v2/runs/dev2-01

PYTHONPATH=src python src/recipe/planner-centered/export_alfworld.py \
  --run-dir experiments/planner-centered-v2/runs/dev2-01 \
  --standalone
```

`--standalone` 将完整 prompt、原始 response、工具参数、环境反馈与成本嵌入可离线打开的 HTML。普通导出默认写入所选 run 的 `alfworld/data/`；若要生成实验根目录页面，显式设置 `--output experiments/planner-centered-v2/alfworld/data/`，再用 `npm --prefix web run build:alfworld` 构建查看页。导出不改写原始轨迹，不合并不同 run 或旧实验成绩。

## 最小检查

使用安装了主 requirements 的 Python 环境：

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python -m unittest discover \
  -s src/toolkit/tests -q
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python -m unittest discover \
  -s src/recipe/planner-centered/tests -q
```

真实后端检查按环境变量显式启用，不发送模型请求。当前协议的[两轮开发任务实机轨迹](../../../experiments/planner-centered-v2/README.md#本轮单任务实机验收)及[六目录更新后 test/1 六配置复验](../../../experiments/planner-centered-v2/README.md#六配置独立目录更新后的复验)已生成；各轮协议缺评与原始输出分别保留待审核。完整矩阵已按冻结设置完成，其他模型测试另定范围与预算。
