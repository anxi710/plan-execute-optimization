# Planner Experiment Toolkit

`src/toolkit/` 是 Planner 实验的基础库。`src/recipe/` 保存可运行的实验方案，`experiments/` 保存结果和证据。这个分工参考 veRL 的基础库与 recipe。[veRL recipe 说明](https://github.com/verl-project/verl-recipe)

## 基础库与 Recipe

基础库提供模型、环境、提示词、运行框架、任务加载和轨迹等可复用组件。Recipe 使用 toolkit 中已有的对应组件，包括提示词与解析逻辑。替换或自行实现已有组件须取得研究者明确授权。依赖方向由 recipe 指向 toolkit。每份 recipe 负责装配组件、编排实验流程，并记录选用的模型、提示词、benchmark、对照条件和预算。Python 环境由调用方提供。

## 统一提示词

框架按实际 `mode` 和 benchmark 调用 `load_framework_prompts(mode, benchmark)`，直接选择一份提示词模块。Full-plan 与 sub-plan 在目录层面区分，不再先加载环境通用指令、再拼接框架例外。渲染、解析函数与 `PlanInjection` 仍从 `toolkit.prompts` 导入。

| 运行配置 | 提示词目录 | 规划范围 |
| --- | --- | --- |
| `eo` | `prompts/eo/` | 无 Planner。 |
| `pe-s` | `prompts/pe_s/` | 一次整体规划。 |
| `pe-d-f` | `prompts/pe_d_f/` | 按需提供剩余整体指导。 |
| `pe-d-s` | `prompts/pe_d_s/` | 按需提供当前子计划。 |
| `pc-f` | `prompts/pc_f/` | 整体规划与当前阶段。 |
| `pc-s` | `prompts/pc_s/` | 当前阶段目标与完成条件。 |

每个目录下按 benchmark 保存 `alfworld.py`、`sciworld.py`、`webshop.py` 和已有的 `terminalbench.py`。对应模块集中保存角色、初始规划、后续监测、Executor、JSON 格式及实际需要的规划工具说明；无需该角色或阶段的配置不定义对应字段。Terminal-Bench 仅迁移已有文案和调用，不扩展功能。

EO、PE-S 和 PC 的 Executor 每轮输出一条非空 `Action: <command>`。PE-D 每轮只能选择一个分支：输出一条环境 `Action:`，或原生调用 `request_plan` 求助；同轮不能两者并发。`Thought:` 可解释所选分支，不能替代动作或工具调用；已有足够信息执行时直接行动，求助应说明具体未解决的规划需求。Full/sub 的求助时机分别由对应模块的工具说明定义。

框架 Planner 的初始规划与在线监测交付普通 JSON。独立的固定计划生成保留原接口：`render_planner_prompt(benchmark, task)` 使用 `pe_s/<benchmark>.py` 的 `PLANNER_TEMPLATE`，要求 `<plan>...</plan>`；`extract_plan()` 取首个标签正文，缺少标签时保留去除首尾空白后的文本。该 XML 接口不控制框架运行。

| 文件 | 职责 |
| --- | --- |
| `prompts/<mode>/<benchmark>.py` | 保存该配置和 benchmark 的完整指令文本，供直接审核与修改。 |
| `prompts/loader.py` | 将六种运行配置与 benchmark 定位到对应模块。 |
| `prompts/templates.py` | 渲染独立计划与执行反馈，加载显式指定的自定义指令文件。 |
| `prompts/plans.py` | 解析模型返回的计划。 |
| `prompts/plan_injection.py` | 构造计划注入文本，由执行会话应用。 |

ALFWorld、ScienceWorld 和 WebShop 的 `environments.<benchmark>.instruction_path` 默认设为 `null`。普通环境／rollout 使用 EO 指令，框架运行使用自身配置的 `EXECUTOR_PROMPT`。显式指定 UTF-8 文件路径时，仍按既有路径规则替换执行指令，文件应自行写明所需输出规则，框架不改写其正文。Terminal-Bench 复用同一加载入口。环境适配器不持有计划注入策略，也不选择或调用模型。[ALFWorld 战略采样 Recipe](../recipe/strategy-sampling/README.md#运行)

Executor 不维护手写动作目录。ALFWorld 的候选缓存方式参考 verl-agent 的 admissible commands 接口，每次原生 reset/step 后更新。候选只加入 Executor 消息，Planner 使用原始公开观察与已经执行的动作，不额外接收这份候选目录。

静态 Executor 模板只说明使用规则；具体列表在最终请求中以 `Available actions: ...` 动态附加。普通 rollout 由 [`BaseEnv`](envs/base.py) 在 reset/step 时加入，框架运行由 [`_executor_context()`](frameworks/runtime.py) 从当前环境重新读取并加入，两者共用 [`render_action_feedback()`](prompts/templates.py)。核查模型实际可见内容应读取轨迹中的 `model_call.messages`。[当前与旧轨迹的核查边界](../../DISCUSSION.md#planner-能力说明与动作接口)

| 后端 | Executor 动作接口 |
| --- | --- |
| ALFWorld | 原生 reset/step 的 `info["admissible_commands"]`。 |
| ScienceWorld | 原生 reset/step 的 `info["valid"]`。 |
| WebShop | 当前页面的 `get_available_actions()`；搜索关键词仍是开放参数。 |
| Terminal-Bench | 实际 shell 执行与 `finish` 接口，没有有限可枚举的候选目录。 |

同一后端的四类架构、六种配置使用相同的动作信息。候选表示当前允许的操作，不保证推进任务或成功；不读取 expert plan、gold path 或隐藏评分。历史实验结果和原始 prompt 保持原样，不按当前协议重跑或改写。

ALFWorld 的状态筛选候选同时提供参数实例化与可行动性辅助，不能等同于只给命令语法。框架对照的结论须限定在这一输入接口下；它是否仅减少接口错误、是否补偿计划遗漏，以及向无菜单接口的适用性尚未验证。[研究判断与候选对照](../../DISCUSSION.md#参数实例化状态筛选与-planner-评价)

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
| `models/` | `BaseModel` 定义调用和计量接口。`AsyncChatClient` 支持限并发的 OpenAI 兼容请求，`MeteredChatModel` 复用该客户端并计量用量。`ContextWindow` 按输入预算维护完整交互单元的窗口。模型类接收调用方解析后的配置，不绑定 Planner 或 Executor；角色标签由执行层记录。 |
| `tasks/` | 按任务 ID、划分和分片选择任务，校验计划与任务的对应关系。ALFWorld 支持生成 `task_id → gamefile` 映射，SciWorld 按子任务与 variation 加载。 |
| `envs/` | `BaseEnv` 管理环境状态、动作轨迹和步数。ALFWorld、SciWorld 和 WebShop 适配器处理初态、动作反馈和 benchmark 的终局判定。 |
| `prompts/` | 按六种运行配置、再按 benchmark 组织提示词，提供加载、渲染、计划注入和输出解析。 |
| `planning/` | `generate_plans()` 使用统一模板批量生成计划，记录用量并支持校验与续跑。 |
| `frameworks/` | EO、PE-S、PE-D 和 PC 的控制策略，管理规划介入、阶段委派、公开反馈、预算与停止条件。 |
| `rollout/` | 共享执行会话与运行循环，组合批量采样、记录输出和已有轨迹读取。 |
| `utils/` | 读写 JSON 和 JSONL，写入时原子替换目标文件。 |

## 四种运行框架

`toolkit.frameworks.run_framework()` 通过 `mode` 选择控制流。四种架构族有六种运行配置，公用环境、调用与事件记录组件。

当前运行器只支持 `two-phase-v3`。除 EO 外，各组先直接调用 Planner 生成初始规划，再进入执行与监测；第一阶段不执行环境动作。[定义与验收边界](../../DISCUSSION.md#function-tool-的定义与执行绑定)

| 模式 | 谁控制任务 | 何时调用 Planner |
| --- | --- | --- |
| `eo` | Executor | 无 Planner。 |
| `pe-s` | Executor | 首步前直接规划一次，之后不提供规划工具。 |
| `pe-d-f` / `pe-d-s` | Executor | 首步前直接取计划，后续由 Executor 按需发起 `request_plan`；分别取得整体计划或子计划。 |
| `pc-f` / `pc-s` | Planner | 初始规划后固定执行一步；环境未终止时再监测、维持或更新规划。F 持有整体规划与当前编号，S 维护当前阶段。双方不注册执行工具。 |

[`FrameworkRun`](frameworks/runtime.py) 保存单次运行的状态并显式推进两阶段流程，复用 `RolloutSession`；公开常量为 `FRAMEWORK_PROTOCOL`、`FRAMEWORK_MODES` 与 `PLAN_SCOPES`。模型回调返回含 `text`、结束原因和用量的字典，仅 PE-D 的 Executor 请求带 `tools` 并可返回原生 `tool_calls`。EO 的 `planner` 可设为 `None`。运行器按适配器实际派发的环境步计 `executor_limit`，不再设置独立 Planner 调用额度或固定返回间隔。完整交互日志跨阶段保留，模型输入按下文的上下文窗口选择。Planner 读取公开动作、Executor 回复与环境反馈；候选菜单仅向 Executor 提供当前列表。事件元数据和剩余额度只在运行记录中保存。

Planner 的角色说明在各 benchmark 模块中直接使用任务类型：ALFWorld 为 `household`、SciWorld 为 `scientific`、WebShop 为 `shopping`。环境标识符不变；Terminal-Bench 现有调用保留原说明。

PC 的任务说明分别保存在 [pc_f/alfworld.py](prompts/pc_f/alfworld.py) 和 [pc_s/alfworld.py](prompts/pc_s/alfworld.py) 等 benchmark 模块中，各自包含初始与监测两份文案。运行器先选择实际配置的模块，再读取本轮文案，附加该模块的 JSON 格式说明与动态 Schema。任务目标、交互历史和当前规划状态仍由外层组装。PC 文案待研究者继续审阅删减。

| 规划范围 | 初始规划 | 后续监测 |
| --- | --- | --- |
| Full plan：`pc_f/<benchmark>.py` | `PLANNER_INITIAL_PROMPT` | `PLANNER_MONITOR_PROMPT` |
| Sub-plan：`pc_s/<benchmark>.py` | `PLANNER_INITIAL_PROMPT` | `PLANNER_MONITOR_PROMPT` |

Monitor 将反馈判断直接对应到维持、完成后推进或弃用重规划。Full 的当前阶段处理与整体计划修订分别判断，保留当前阶段时也可以调整未来目标；若证据表明当前目标不可行或已不适用，则弃用并重规划剩余目标。Sub 在该情况下直接交付新的阶段目标与完成条件。原始任务要求不因弃用中间目标而改变。

弃用记录由运行器写入 `planner_decision.discarded_stages`，不要求模型重述旧目标。Planner 明确以 `blocked`／`replaced` 关闭并切换当前阶段时，Full 按旧计划中当前阶段的位置检查剩余目标，将新路线移除或改写的旧定义原样留档，排除已验证完成的阶段；Sub 留存被舍弃的旧阶段。普通措辞修订不自动记为弃用，也不将被重规划的后续目标都判为受阻。当前阶段的原文、状态、判断与证据仍由 `stage_result` 保存。该字段只用于轨迹留档，不额外注入 Planner 上下文。

Planner 正文不注入初始规划或持续监测的阶段标题，直接使用本轮任务说明与输出要求。两阶段控制流由运行器推进；`planner_phase` 仅作为日志元数据记录 `initial_planning` 或 `execution_monitoring`，不进入模型输入。

初始观察编号为 1，后续环境反馈依次为 2、3……；模型调用、规划求助和本地格式错误不占观察号。事件日志另存 `event_id`，观察事件持久保存 `observation_id`，`evidence_refs` 引用观察号。ALFWorld 的框架初始观察只含场景，任务目标独立提供；原始任务文本及普通 rollout 的任务输入保留。PE-S 的 Planner 模板只说明一次初始规划，PE-D 区分初始规划与后续求助。已完成阶段的模型输入只保留阶段、完成条件和证据引用，原始判断保存在日志中；`verified` 是 Planner 判断，尚未引入独立阶段 verifier。

PE-D 的工具声明与本地绑定共用 [`FunctionTool`](frameworks/tools.py)，`invoke_tool(event, tools)` 检查原生调用信封及 JSON 参数后执行绑定的 handler。Planner 的初始规划与监测返回一个普通 JSON 对象：`assessment` 陈述当前观察和阶段判断，计划字段按 full/sub 配置给出；PC-F 初始化还给 `current_subplan_id`。`assessment` 是可见的结构化输出，不代表模型内部推理轨迹，也不控制 API 的推理开关。JSON 解码与字段、阶段、证据校验在执行前完成，不新增 provider 专用响应模式或 P10 扩展解析策略。

PC-F 后续返回修改后的 `full_plan` 时，必须在同一 JSON 对象提供非空字符串 `revision_reason`，说明改了什么、为什么改。当前判定涵盖措辞调整和新增细节；首次规划不要求理由。只推进到已有阶段时返回 `current_subplan_id`，省略 `full_plan`。提示和字段说明明确这项条件，判定范围暂不调整。

任务要求只由任务原文提供，不维护或注入独立 `constraints`／`hard_constraints` 字段；`run_framework()` 不接受该参数。

PC 每个非终局轮必须调用一次 Executor，随后根据环境反馈继续或停止。Planner 只维护规划与阶段判断，不能自行宣告任务结束。环境明确终局或真实步数预算耗尽后直接记录结果，不再调用 Planner 收尾；终局按 `done`／`terminate_reason` 判断，中间奖励不触发停止。模型回复原样保存在 `model_call.response`，不提取独立的 `executor_claims`，不按自然语言关键词推断任务完成。ALFWorld 直接使用环境裁决；Terminal-Bench 按环境规定的提交动作交付工作区，由 Harbor 原生验证器判分，在线记录保留待验状态。`deliver_plan`、`execute_step` 与 `submit_task` 不再作为模型工具。

环境、模型客户端、预算和日志由运行会话持有，不进入模型工具参数。当前动作模板和环境填好名称、按状态筛选的候选列表保持不变，辅助性质及评价限制仍须说明。

历史实验数据保留归档。当前代码不提供旧协议、旧字段或旧轨迹布局的读取、续跑与导出兼容；读取或复现历史实验须检出对应源码版本。调用方装配模型、环境、输出路径与调度，并在外部验收后补写独立分数。[Recipe 入口](../recipe/planner-centered/README.md) · [新实验协议与验收边界](../../experiments/planner-centered-v2/README.md#六配置的运行协议)

## 输入上下文窗口

[`ContextWindow`](models/context.py) 由 Toolkit 维护，Recipe 只传实验配置。`toolkit/config.yaml` 中的 `context_window.max_input_tokens` 默认为 `null`，暂不设置容量。显式设置正整数时，它约束单次请求的输入预算；各角色的输出 `max_tokens` 另行设置，两者不冒充模型原生总上下文容量。

```python
await run_framework(
    # mode、环境、模型和保存回调等装配参数
    context_window={"max_input_tokens": None},
    **runner_options,
)
```

Planner 和 Executor 分别维护自己的窗口，权限保持不变。每次请求把保留的完整交互单元写进一个 `user` prompt，淘汰最早的完整单元，不截断单条回复或观察。已淘汰的单元不会因后续固定 prompt 变短而自动返回；Executor 明确引用的证据可临时重新提供给 Planner。PE-D 只把当前必要的原生 `assistant` 工具调用和匹配的 `tool` 结果保留为独立消息，旧工具往返写入 prompt 正文。

两角色先给对应模块的角色或执行说明与任务，再给完整可见历史。Executor 的行动／求助输出规则已合并在模块执行说明中，历史后依次给当前 `Available actions` 和当前计划或阶段；Planner 不接收动作菜单，将本轮规划要求、JSON 字段约定和当前计划状态放在历史之后。当前原生工具配对仍作为合法的 assistant／tool 消息接在 user prompt 后。

任务目标、当前计划或阶段、当前观察、Executor 的当前动作菜单和当前原生工具交接不会被裁掉。窗口同时计入这些固定内容和工具声明。固定内容仍超限时，运行器在派发请求前记录 `context_window_error` 并保留缺评。原始事件、完整请求与回复持续保存在日志，不做自动摘要。

调用方可注入 `count_tokens(payload)`。未注入时，默认使用明确标注的 UTF-8 字节保守估计，不声称具有跨 provider 的精确 tokenizer。`model_call.context_window` 保存估算方法、估算输入量、保留／淘汰的交互与观察编号、受保护的交互编号，以及响应中实际报告的输入和输出 token。实际 `prompt_tokens` 只反馈请求中未计入的额外开销，不累加历次请求的 `total_tokens` 作为窗口占用。淘汰范围与完整原始轨迹可以分别核查。

## 执行与采样的组合

| 部分 | 接口与职责 |
| --- | --- |
| 执行会话 | [`RolloutSession`](rollout/session.py) 统一环境初始化、模型调用、同步或异步动作推进和持续执行。返回边界处保留同一环境与对话，供控制策略继续使用。 |
| 框架控制 | [`run_framework()`](frameworks/control.py) 组合执行会话，决定何时规划、更新整体指导、委派阶段或停止。 |
| 批量采样 | [`sample_jobs()`](rollout/batch.py) 负责并发和结果顺序。调用方的 `open_worker` 异步上下文提供单样本执行函数，并管理模型和环境资源。 |
| 记录输出 | [`rollout/log.py`](rollout/log.py) 处理事件和状态记录。保存回调决定落盘方式，执行会话不依赖文件路径或某一种磁盘格式。 |

`RolloutRunner.run(row, plan, save)` 接收外部生成的固定计划，组合上述执行会话完成 PE-S 的执行采样；同一计划可独立采样多次。`plan=None` 时执行无计划采样。`run_framework()` 在共享执行能力上组合四类架构的六种配置。普通 rollout 的状态轨迹与框架的事件轨迹使用各自的保存和读取接口。

自行组合控制逻辑时，提供环境、异步模型回调和返回边界函数：

```python
from toolkit.rollout.session import RolloutSession

session = RolloutSession(env, {"executor": executor})
session.reset()
await session.run(after_step=controller)
```

`executor(messages)` 返回含 `text` 的响应字典。`controller(tool_event)` 可同步或异步执行；返回 `None` 时继续，返回停止或暂停理由时交还控制权。暂停后可更新对话，再次调用 `session.run()`，延续同一环境和执行历史。每个独立样本创建新的会话。调用方通过 `EventLog` 的保存回调接入记录输出；会话不自行选择文件路径。

## 组合运行

基础库默认值在 [`src/toolkit/config.yaml`](config.yaml)，包括 Planner 与 Executor 的 `api_base`、`api_key`。调用方可显式传参，或调用 `resolve_config()` 派生一份配置，不改写公共文件。Recipe 在 YAML 中覆盖本轮的连接和模型设置；客户端统一把 `api_base` 传给 SDK 的 `base_url`，不区分服务商或本机网关。`api_key` 为空时，Recipe 从通用环境变量 `OPENAI_API_KEY` 读取；受跟踪的配置不填写真实密钥，实际 key 不写入运行记录。实验方案的参数由各 Recipe 自己管理。[规划框架配置](../recipe/planner-centered/config.yaml) · [战略采样配置](../recipe/strategy-sampling/config.yaml)

模型内置推理的配置统一为 `thinking` 和 `reasoning_effort`。前者生成 `extra_body.thinking.type`，后者发送为同名请求字段；`null` 均表示省略，不能据此断言推理已关闭。具体开关、取值和默认行为依目标接口及模型能力确定，不通过服务商名称推断。[同济接口](https://agi.tongji.edu.cn/docs/reasoning)用 `reasoning_effort: none` 关闭；[DeepSeek 原生接口](https://api-docs.deepseek.com/guides/thinking_mode/)支持 `thinking.type: disabled`。这些参数不控制提示词中的显式思考文本。

- `tasks.rows.load_task_rows()` 可选择 canonical 任务并绑定计划文件。`tasks.alfworld.prepare_gamefile_map()` 从本地环境生成映射。并发执行时，每条 ALFWorld 轨迹用已确认的游戏文件重新初始化。
- `toolkit.planning.generation.generate_plans()` 接收任务行或任务 JSONL，用指定 benchmark 的统一模板为每个任务生成一份计划。输出记录回复、用量和实际设置，续跑时跳过已经保存且通过校验的任务。
- `rollout.batch.run_rollouts()` 为固定计划采样装配任务、模型、环境和状态日志，再调用共享的 `sample_jobs()`。Recipe 提供每条样本的 seed 和结果路径，决定是否续跑。`load_saved_rollout()` 校验记录属于哪条样本，显式重试时调用 `archive_incomplete_rollout()` 保留中断轨迹。
- `rollout.traces.load_trace()` 校验一份已完成的普通 rollout 轨迹；`load_records()` 只读取 `<task_id>/sample_<id>.json`，按任务、样本和成功状态筛选；`conversation_parts()` 核对每条环境反馈与消息记录。

ALFWorld 的 [`AlfWorldRolloutPool`](tasks/alfworld.py) 提供显式 `with pool.reuse_slots():` 作用域。在其中，`open_slot()` 从空闲池借出完整后端，归还后才允许复用；并发借出的 slot 互相独立。每条任务仍通过 `slot.load_task()` 重载指定游戏并恢复初态，框架会话和历史逐条新建。调用方负责并发上限，预检和正式调度应共用同一作用域；正常或异常退出时统一关闭所有底层环境。作用域外的 `open_slot()` 仍即开即关，不改变其他 Recipe 的生命周期。

该作用域用于限制 TextWorld／`fast_downward` native 库副本增长：当前上游关闭环境后仍保留已删除动态库的进程映射，因此逐条新开后端会持续占用临时文件配额；复用完整后端使副本数受并发 slot 数限制，不全局共享 native 库句柄，也不声称已修复上游卸载。顺序复用、并发隔离、异常清理和域外行为见[测试](tests/test_alfworld_slot_reuse.py)；真实无模型资源检查见[本轮实验记录](../../experiments/planner-centered-v2/README.md#run02-quota-中断与恢复)。

SciWorld 可用 `tasks.sciworld.SciWorldTask.load_tasks()` 和 `envs.sciworld_env.open_sciworld_backend()` 装配。默认使用安装包内的 JAR。历史环境如需指定自己的 JAR，显式传入 `jar_path`。

## 环境与数据

| 后端 | Python 3.11 运行依赖 | 旧评测目录如何复用 |
| --- | --- | --- |
| [ALFWorld 0.4.2](https://pypi.org/project/alfworld/0.4.2/) | [TextWorld 1.7.0](https://pypi.org/project/textworld/1.7.0/)、`base_config.yaml` 和配置指向的游戏数据。上游用 `traj_data.json` 筛选任务类型，用 `game.tw-pddl` 加载可运行游戏。文本模式不需要 Java 或视觉权重。 | 可挂载原 `data/alfworld/`，复用 `json_2.1.1/` 下的游戏和配套 `logic/`。`alfworld_<split>_tasks.jsonl` 是项目的选题文本；重复 rollout 使用已核对的 JSONL 游戏映射，不读取旧 `gamefile_id.txt`。 |
| [ScienceWorld 1.2.3](https://pypi.org/project/scienceworld/1.2.3/) | Java（本项目验证 OpenJDK 21）和 Py4J。wheel 内置模拟器 JAR 和任务目录，无需另下载游戏数据。 | 可挂载原 `data/sciworld/`。`sciworld_<split>_tasks.jsonl` 固定任务和 variation；`max_steps.json` 提供项目的逐类预算。Toolkit 不直接读取旧 `*_indices.json` 或 `taskname2id.json`，默认也不读取旧 JAR。 |

ALFWorld 无现成数据时，按[官方指南](https://github.com/alfworld/alfworld#quickstart)准备游戏数据。官方 `alfworld-download` 默认也下载视觉检测器，但文本回放不使用它；已有游戏数据无需重复下载。上游游戏数据不替代项目选题 JSONL。ScienceWorld 不需要预先打开所有容器；[官方说明](https://github.com/allenai/ScienceWorld#simplifications)中的 `easy` 不含 `openContainers`。

ScienceWorld 的 `environments.sciworld.max_steps` 为 `null` 时读取数据目录中的逐类预算。Recipe 可将它覆盖为正整数。两种文本环境均已回放至真实成功终局。ALFWorld 回放了已保存的 `dev` 任务 2 的四步动作，ScienceWorld 回放了非生物分类任务 variation 225 的七步官方参考动作。

WebShop 使用 Princeton 官方源码快照 `64fa2a5` 的文本 API。Python 3.11、Java 21、PySerini 0.17.0 和 NumPy 1.26.4 已用 1,000 商品索引验证任务选取和两次完整 rollout。脚本 Executor 各用三步完成搜索、点击和购买，原生奖励均为 1。完整目录与 500 个官方测试目标的核验见 Planner-Centered 评测记录。测试数据来自公开镜像 `ce990ff`，与 Google Drive 原件的字节一致性未核实。浏览器环境未验证。[Princeton 官方源码快照](https://github.com/princeton-nlp/WebShop/tree/64fa2a5c15c7daa698b9ac93f5bb5437b634c9bd) · [公开镜像](https://huggingface.co/datasets/YWZBrandon/webshop-data/tree/ce990ff) · [完整目录核验](../../experiments/planner-centered/README.md#完整测试集评测)

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

<details>
<summary>TextWorld 1.7.0 平台标签与本机依赖修复</summary>

本轮下载的官方 Linux 1.7.0 wheel 在 `WHEEL` 文件的 `Tag:` 前多了一行空行。pip 按头字段读取时得不到平台标签，因此 `pip check` 报 `textworld 1.7.0 is not supported on this platform`。实际 ALFWorld 重载与动作可运行。这是所检查 wheel 的元数据错误，不据此降级环境版本。[官方发布包](https://pypi.org/project/textworld/1.7.0/)

[修复脚本](scripts/repair_textworld_wheel.py)只移动该标签到头部并由 `wheel` 重建 `RECORD`，逐文件确认代码与数据不变。需要 `wheel` 包，修复后再安装：

```bash
python -m pip download --no-deps --dest /tmp/textworld-wheel textworld==1.7.0
python src/toolkit/scripts/repair_textworld_wheel.py \
  /tmp/textworld-wheel/textworld-1.7.0-py3-none-manylinux_2_5_x86_64.manylinux1_x86_64.manylinux_2_17_x86_64.manylinux2014_x86_64.whl \
  /tmp/textworld-wheel/fixed
python -m pip install --no-index --no-deps --force-reinstall \
  /tmp/textworld-wheel/fixed/textworld-1.7.0-py3-none-manylinux_2_5_x86_64.manylinux1_x86_64.manylinux_2_17_x86_64.manylinux2014_x86_64.whl
python -m pip check
```

本机 `plan-test` 另有已有 Hugging Face 包冲突：`transformers 5.17.0` 要求 `huggingface-hub>=1.5,<2`，`tokenizers 0.23.2` 要求 `<2`，原安装值是 `2.1.1`。本轮将 hub 调整为 `1.33.0`，保留其余两包，再通过导入检查与 `pip check`。这项本机修复不加入主 requirements；WebShop 的独立环境仍按其专用依赖安装，不混用两套 Hugging Face 版本。

</details>

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
  -e OPENAI_API_KEY \
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
