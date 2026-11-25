# Planner-Centered v2：未经专项训练的框架性能测试

本实验独立测试 EO、PE-S、PE-D-F/S 和 PC-F/S 在未进行本项目专项训练时的任务表现与运行成本。模型不更新参数。本轮直接报告原生评分、成功、缺评和成本，不评估训练收益，也不要求先回答战略探索或学习机制的问题。

当前状态：完整外层 JSON 围栏的解析修订见提交 `937ff44`。[test/1 03 六配置验证](#完整-json-围栏容忍后的复验)已全部成功，[新完整轨迹页](http://127.0.0.1:4179/alfworld.html#/?tab=read&left=m1-t1-pc-s)可审核 PC-S 事件 18 的围栏原文及后续执行。此前[02 复验](#六配置独立目录更新后的复验)为四组成功、两种 PC 围栏 JSON 缺评，01 为三组成功、三组协议缺评，原始产物保留。Qwen Planner／DeepSeek Executor 的完整 test 六架构评测 run02 已于 2026-11-23 15:01:26（北京时间）结束：804 条中 465 条有有效原生评分、339 条缺评，[最终结果及异常审查页](#完整测试结果与最终异常审查)保留原样。协议缺评显著限制架构比较，尚未训练。旧实验保留在[原实验目录](../planner-centered/README.md)，不导入本实验样本或评分。

## 实验标识与范围

| 项目 | 当前约定 |
| --- | --- |
| 实验名称／产物根目录 | `planner-centered-v2`／本目录。 |
| 框架协议 | `two-phase-v3`，与实验名称的 v2 分开记录。 |
| 运行实现 | 复用 [Toolkit 框架](../../src/toolkit/frameworks/runtime.py)与[Planner-Centered Recipe](../../src/recipe/planner-centered/README.md)，不复制一套运行器。 |
| 模型状态 | 未经本项目专项训练，Planner 与 Executor 均不更新参数。 |
| 当前优先环境 | ALFWorld 0.4.2。其他环境若纳入，另行固定任务范围和后端设置。 |
| 旧实验 | 保留原数据与日志；当前运行与导出只处理新协议，不添加旧字段回退或旧数据读取兼容。 |

## 六配置的运行协议

| 配置 | 首个环境动作之前 | 非终局执行流程 |
| --- | --- | --- |
| EO | 无 Planner。 | Executor 持续根据任务与观察行动。 |
| PE-S | 直接调用 Planner 一次，交付整体规划。 | Executor 负责整任务，没有后续求助工具。 |
| PE-D-F | 直接调用 Planner，交付整体规划。 | Executor 自主行动，按需原生调用 `request_plan`；Planner 复核或更新剩余整体指导。 |
| PE-D-S | 直接调用 Planner，交付当前子计划。 | Executor 自主行动，按需调用同一工具取得子计划；接受其在可直接完成整任务时继续执行的结果形式，工具说明保持原样。 |
| PC-F | Planner 生成带编号的整体规划并选择当前阶段。 | 固定调用 Executor 执行一步，环境未终止时再由 Planner 监测、维持、转段或修订。 |
| PC-S | Planner 生成当前阶段目标及完成条件。 | 同样固定单步执行和监测，Planner 按反馈维持或交付下一阶段。 |

初始规划不执行环境动作。只有 PE-D 的 Executor 使用原生规划工具；Planner 以及两种 PC 不注册执行工具。规划求助不计环境步，原生调用与工具结果配对。Executor 原始回复、实际动作、公开反馈、计划交付和模型用量均保存在轨迹中。

任务原文保留其全部要求，不额外维护或注入 Hard constraints。ALFWorld 初始观察从场景中分离任务目标，避免重复。Observation 从 1 开始，后续实际环境反馈连续编号；内部日志事件另记编号，模型调用、求助和本地格式拒绝不占观察号。

任务终止与成败依据环境反馈。当前工作区在环境明确终局或真实步数预算耗尽后直接记录结果，不再调用 Planner 收尾；中间奖励不单独触发停止。不预设 Executor 输出完成声明，也不按自然语言关键词判断终止；ALFWorld 直接采用环境的终止状态、成功标志与奖励。预算耗尽、格式错误和外部故障分别记录，不能替代环境成功；阶段 `verified` 是 Planner 基于可见证据的判断，尚未引入独立阶段语义 verifier。下文已完成的 run02 与开发验收使用当时的收尾策略，其原始请求和成本保留；本次删除只影响后续运行。

## 输入、规划表示与上下文

当前提示词按六种运行配置分目录：`eo/`、`pe_s/`、`pe_d_f/`、`pe_d_s/`、`pc_f/`、`pc_s/`，各自再按 benchmark 保存完整文案。框架按 `mode` 与 benchmark 加载对应模块，Full/sub 不在同一文件中混放。PE-D 的 Executor 单轮输出一个环境 Action 或原生调用 `request_plan`，Thought 仅解释选择，求助须有具体未解决的规划需求；原有工具时机说明、预算和连续无动作保护不变。其余配置继续逐轮输出环境动作。离线检查完成后，研究者授权单任务 02 复验；此前已完成运行使用当时冻结的提示词。[目录与加载规则](../../src/toolkit/README.md#统一提示词)

当前 Planner 普通输出采用 JSON，使用 `assessment` 表示基于当前可见观察的状态或阶段判断。计划字段按 full／sub 范围给出，PC-F 另维护当前阶段编号。`assessment` 不是服务端隐藏推理的摘要，也不独立决定任务成功。是否把判断与计划放入 `<think>`／`<plan>` 等标签、计划内部是否继续使用 JSON，仍是待讨论的表示问题，本轮不擅自变更。

历史交互嵌入单次 prompt 正文，使用 Toolkit 的可配置 token 上下文窗口；PE-D 当轮必要的原生 assistant／tool 交接仍保留合法配对。超过已配置窗口时淘汰最早的完整交互单元，不按字符摘取观察、不生成模型摘要；任务、当前计划或阶段、当前观察和必要工具交接保留。完整原始日志不因窗口淘汰而删除。

Planner 只获取公开观察、实际动作和来源明确的 Executor 声明，不获得动态动作目录或隐藏验收信息。当前可执行动作列表只提供给 Executor，保留环境已填好参数、按状态筛选的接口。本轮不改变 action prompt。

`context_window.max_input_tokens` 当前为 `null`：先完成可配置实现，不设置未经确认的数值，也不宣称具备模型标称最大容量。正式运行需明确该值或明确保持未设定。当前默认使用完整请求的 UTF-8 字节数作保守 token 估计，再依据服务端 `prompt_tokens` 校准额外开销；该估计不是模型 tokenizer 的精确计数。估计值与服务端用量分别记录。历次 `total_tokens` 包含重复输入，不能相加作为当前窗口占用。

## 环境与依赖

使用 [requirements.txt](../../src/toolkit/requirements.txt)及其引用的 [requirements-core.txt](../../src/toolkit/requirements-core.txt)中明确固定的版本，不执行无界的“升级到任意最新版本”。本轮已对齐并核验的安装版本如下：

| 软件 | 版本 |
| --- | --- |
| ALFWorld | 0.4.2 |
| TextWorld | 1.7.0 |
| ScienceWorld | 1.2.3 |
| OpenAI Python SDK | 3.20.0 |
| PyYAML | 6.0.1 |

后续运行清单继续记录实际 Python、平台与安装版本。旧批次在 ALFWorld 0.3.5 下的结果保留原标记，不能作为本实验新版本的测试结果。安装版本通过不代表模型接口或全部环境任务已经实测。

本轮修复了 `plan-test` 的两类安装问题：将不满足现有 Transformers／Tokenizers 约束的 `huggingface-hub 2.1.1` 调整为 `1.33.0`；修复官方 TextWorld 1.7.0 wheel 在平台 `Tag` 前的空行，并重建安装包元数据，代码与数据逐文件不变。`pip check` 返回 `No broken requirements found.`，相关包导入及 ALFWorld 重载／真实动作复查通过。[原因与可复现修复](../../src/toolkit/README.md#alfworld-与-scienceworld)

## 启动前需要固定的设置

以下是每轮运行需要固定的设置；当前已授权完整矩阵的具体值见[本轮协议](#完整测试集评测qwen-planner-与-deepseek-executor)。配置和 manifest 保存实际值，不从旧实验自动继承模型矩阵、任务或步数上限。

| 设置 | 当前状态／冻结要求 |
| --- | --- |
| Planner／Executor 模型与服务入口 | 当前完整矩阵已按[下文协议](#完整测试集评测qwen-planner-与-deepseek-executor)冻结。逐角色保存实际模型名、入口和请求选项，密钥不进入记录。当前 Magpie 采用 `http://127.0.0.1:3425/v1/magpie/native/tongji/v1` 原生路径和裸上游模型名；已核查官方 0.1.4657 源码，单任务与完整测试已完成调用；隐私遮蔽仍可能改写请求体。 |
| ALFWorld 数据、划分和任务 | 开发联调与正式测试分开；起跑前固定 canonical 划分、任务 ID 与 gamefile 映射，避免根据待报告结果调整任务。 |
| 六配置与角色采样 | 框架已定。同一模型比较组固定 Executor 模型、基础 prompt、动作接口和采样；Planner／Executor 各自温度、输出上限及停止规则写入配置。 |
| 环境步与其他停止规则 | 本轮每任务最多 20 个真实环境步；求助、本地拒绝不计环境步，所有额外模型调用计入成本。无动作往返限制等运行规则一并保存。 |
| 上下文窗口 | `max_input_tokens: null`，当前未确定容量；不得把窗口改动和不同配置的执行差异混为同一设置。 |
| 请求与调度 | 保存超时、请求级重试、可恢复尝试数、并发和限速。当前完整矩阵采用下文固定值，其他运行单独确认。 |
| seed 与重复次数 | 当前完整矩阵任务顺序 seed 417、模型采样 seed 未指定、每格一次；保存这些设置，未重复时不编造波动估计。 |
| 代码与提示版本 | 保存实际 Git 提交／工作区状态、协议、两角色完整输入输出和依赖版本；不以提交前 HEAD 冒充工作区源码。 |

## 本轮单任务实机验收

研究者已授权在分批提交当前工作区后，用真实 ALFWorld 单任务检查实际轨迹。固定 `dev/2`（把遥控器放到沙发），六种配置各执行一次，均从同一游戏初态独立开始；不扩展正式测试矩阵，不训练。Planner 与 Executor 均使用 `DeepSeek-V4.1-Flash`，经配置的 Magpie 原生透传入口。使用 `plan-test` 的 ALFWorld 0.4.2，每组最多 20 个真实环境步，并发 1；输入窗口 `max_input_tokens: null`。

Planner／Executor 温度为 0.2／0.6，输出上限为 1,536／768 token；两者请求 `reasoning_effort: none`，模型采样 seed 未指定。每次超时 60 秒，请求级自动重试为 0；外部故障按当前同 run 恢复规则至多补一次并保留成本，不重跑已有有效评分。沿用 100 请求／分钟的共享限速。此次授权只用于这个单任务验收，不代表正式评测或提案 v0.6 已通过审核。

首次采样（01）从本地 `main` 的已提交版本 `6f531c6` 运行，清单记录源码为 `committed`。实际产物在 `runs/v3-deepseek-dev2-01/`，不修改旧实验数据。[离线六配置完整轨迹](runs/v3-deepseek-dev2-01/alfworld.html) · [原始清单](runs/v3-deepseek-dev2-01/manifest.json) · [原始事件报告](runs/v3-deepseek-dev2-01/report.html)。这些大产物保留本地，不纳入 Git。

| 配置 | 原生奖励 | 真实环境步 | Planner / Executor 请求 | 总 token |
| --- | ---: | ---: | ---: | ---: |
| EO | 1 | 4 | 0 / 4 | 1,971 |
| PE-S | 1 | 4 | 1 / 4 | 3,070 |
| PE-D-F | 1 | 4 | 1 / 4 | 4,493 |
| PE-D-S | 1 | 4 | 1 / 4 | 4,311 |
| PC-S | 1 | 4 | 5 / 4 | 6,774 |
| PC-F | 缺评 | 1 | 2 / 1 | 2,624 |

共 21 个真实环境步、31 次模型请求，全部返回用量，总 token 23,243（输入 20,718、输出 2,525）。清单墙钟约 25.49 秒，无失败重试或归档尝试。31 次响应均显式报告推理 token 为 0；这与关闭推理的请求一致，但单次运行不能证明旧异常由网关包装造成。

五组各在 4 步后获环境原生奖励 1。PC-F 在第 1 步后将阶段 2 的目标从一般拾取具体化为从 `coffeetable 1` 拾取，重发了变化后的 `full_plan` 并转至阶段 2，却未提供 `revision_reason`；事件 9 因 `missing_revision_reason` 拒绝，原始输出在事件 8。按当前契约它是协议终止、无原生评分，不能当环境失败零分。该次实机验收未修提示、未改校验、未重跑；是否应把这种具体化视作路线修订，留待研究者审核。

实际事件 8 的 prompt 提到路线修订时给 `revision_reason`，但没有说明任意计划文字变化都算路线修订；JSON 字段契约也未表达其条件必需。代码对变化后的 `full_plan` 一律要求理由。这是提示与校验范围未对齐的具体案例，不能仅解释为模型漏遵守清楚的字段要求。

上述结果对应 `6f531c6` 的原始 prompt。研究者随后授权在工作区明确 `revision_reason` 的同一 JSON 字段要求，并将 Planner／Executor 的历史前移、当前规则与计划状态后置；[当前规则与顺序](../../src/toolkit/README.md#四种运行框架)已同步。仍保留全部可见历史和当前菜单，不改变工具触发或计划变化判定。研究者随后授权以相同任务、模型和六配置各 20 步重新采样，结果见下；01 的输入与结果保持原样。

EO 与 PE 的执行均由 Executor 推进；本轮两种 PE-D 的 8 次 Executor 请求均声明了原生规划工具，但实际求助为 0，不能验收 native 往返配对或动态重规划。PC-S 按执行一步、环境反馈、Planner 监测的固定循环运行，验证两次阶段转换，并在终局后一次只读收尾。

六组 Observation 均从 1 连续编号，任务目标与初始场景去重、Planner 不获取动作菜单、输入窗口未淘汰历史等检查通过。页面保留 PC-F 被拒绝的完整原始输出，供比较设计与真实行为；单任务结果只用于接口验收。

### 提示修订后的第二轮采样（02）

第二轮使用同一模型与任务，六配置最终均获原生奖励 1，每组 4 个真实环境步。运行基线为本地 `main` 的 `1972b47`，源码标记为 `working_tree`，实际修改随 `source.patch` 保存。提示实现现见提交 `0d8dac2`。[离线六配置轨迹](runs/v3-deepseek-dev2-02/alfworld.html) · [清单](runs/v3-deepseek-dev2-02/manifest.json) · [完整事件报告](runs/v3-deepseek-dev2-02/report.html) · [运行源码补丁](runs/v3-deepseek-dev2-02/source.patch)

| 配置 | 原生奖励 | 真实环境步 | Planner / Executor 请求尝试 | 总 token |
| --- | ---: | ---: | ---: | ---: |
| EO | 1 | 4 | 0 / 5 | ≥1,952 |
| PE-S | 1 | 4 | 1 / 4 | 3,026 |
| PE-D-F | 1 | 4 | 1 / 4 | 4,536 |
| PE-D-S | 1 | 4 | 1 / 4 | 4,321 |
| PC-S | 1 | 4 | 5 / 4 | 6,926 |
| PC-F | 1 | 4 | 5 / 4 | 8,310 |

EO 的首请求遇到 `InternalServerError`，零环境步、无用量。按同 run 至多两次的既定恢复规则，仅补跑 EO 一次，原失败保存在 `attempts/m1-t2-eo/attempt-000001.json`，其余五组未重跑。共 24 个真实环境步、38 次请求尝试；37 次已报告用量合计 29,071 token（输入 25,946、输出 3,125），故总成本至少 29,071 token，未返回的用量保持未知。37 次返回均显式报告推理 token 为 0。

实际请求确认两角色均为基础说明、任务目标、完整可见历史、本轮规则和当前计划状态的顺序；只有 Executor 在历史与指导之间附当步动作菜单，观察号均为 1–5。完整历史、工具权限和环境步预算保持原约定。

PC-F 在首次监测重发与初始值相同的 `full_plan`，并推进已有阶段 ID 2；后续省略整体计划，仅给已有 ID 3。因为整体计划内容没有变化，本轮没有验证修改计划后填写 `revision_reason` 的分支。PC-F 的成功不能单独归因于字段说明。两种 PE-D 的 Planner 调用仍各为 1、在线求助均为 0；这一次未观察到历史前移带来更多求助，也不能由单次样本排除位置影响。任务、采样随机性、子计划粒度及同时修订的字段说明没有被分离。

## 最新提示词单任务轨迹验收：test/1

### 完整 JSON 围栏容忍后的复验

研究者于 2026-11-25 授权先分批提交现有改动，再接受完整代码围栏包裹的单个 JSON 对象，随后重新运行单任务。已有工作区分别提交为 `c080a02`（运行器与六目录提示词）、`d01e9f4`（研究与实验记录）、`59faddd`（研究者提供的论文源文件），未推送。新运行使用 `59faddd` 加解析器及相关检查的工作区修改，完整补丁与隔离源码随新 run 保存；此前 01、02 和完整矩阵的原始输出与评分不变。

本轮只改变 Planner 普通回复的 JSON 解码：接受纯 JSON，以及完整三反引号围栏（`json` 标记或无标记）包裹的单个 JSON 对象。原始响应不改写，截断、工具调用、字段、阶段和证据校验保持。提示词、模型和采样不改；未来 format reward 未实现。

验证范围仍是 `test/1`（清洗 bowl 后放入 cabinet）的六配置各一次，每组最多 20 个真实环境步、并发 1、共享 100 请求／分钟；`plan-test` 的 ALFWorld 0.4.2／TextWorld 1.7.0，Planner `Qwen3.8-27B`、Executor `DeepSeek-V4.1-Flash`，温度 0.2／0.6、输出上限 1,536／768、`reasoning_effort: none`、模型采样 seed 未指定、输入窗口 `null`、请求超时 60 秒、自动重试 0。新目录为 `runs/alfworld-test1-qwen38-prompts-03/`，隔离源码为 `runs/.source-alfworld-test1-qwen38-prompts-03/`；不为修正协议错误重采，不从单次结果推断架构性能或格式处理的因果收益。Toolkit 95 项（92 通过、3 后端跳过）与 Recipe 33 项（31 通过、2 跳过）离线检查通过；冻结副本已核对六目录加载和新解码行为。后台服务 `planner-alfworld-test1-prompts-03.service` 于 2026-11-25 19:02:32（北京时间）记录六配置全部结束，正常退出（状态 0）；日志在 `runs/alfworld-test1-qwen38-prompts-03.log`。

| 配置 | 原生奖励 | 真实环境步 | Planner / Executor 请求 | 总 token |
| --- | --- | --- | --- | --- |
| EO | 1 | 10 | 0 / 10 | 8,387 |
| PE-S | 1 | 13 | 1 / 13 | 14,482 |
| PE-D-F | 1 | 10 | 1 / 10 | 14,501 |
| PE-D-S | 1 | 11 | 1 / 11 | 15,799 |
| PC-S | 1 | 10 | 10 / 10 | 23,420 |
| PC-F | 1 | 13 | 13 / 13 | 36,644 |

共 67 个真实环境步、93 次请求（Planner 26、Executor 67），113,233 token（输入 105,548／输出 7,685）；所有调用均有用量，显式推理 token 为 0。六条均以 `task_finish` 终止，无协议缺评或归档重采。

本次只有 PC-S 的 Planner 事件 18 输出完整围栏 JSON：前三个真实动作之后，它维持定位 bowl 阶段；事件 19 正常应用该判断，下一环境动作是 `go to shelf 1`，最终任务成功。原始响应仍含围栏，证明新解析分支在真实运行中走通。PC-F 本轮没有围栏输出，该配置的围栏处理由离线集成检查覆盖，不能声称本次也有对应实机样例。两种 PE-D 仍各只有一次初始规划、未发起在线求助；弃用目标分支也未触发。单次结果不能估计架构成功率，亦不能将六组的行为变化都归因于解析修订。

实际 93 份请求已按冻结的六目录文案与工具说明核对；原文围栏的接受、规划应用及响应留存见[围栏与请求审计](runs/alfworld-test1-qwen38-prompts-03/fence-acceptance-audit.json)。其他产物为[清单](runs/alfworld-test1-qwen38-prompts-03/manifest.json)、[汇总](runs/alfworld-test1-qwen38-prompts-03/summary.json)、[配置](runs/alfworld-test1-qwen38-prompts-03/config.yaml)、[源码补丁](runs/alfworld-test1-qwen38-prompts-03/source.patch)、[源码来源](runs/alfworld-test1-qwen38-prompts-03/source.json)、[启动脚本](runs/alfworld-test1-qwen38-prompts-03/launch.py)与[完整离线轨迹页](runs/alfworld-test1-qwen38-prompts-03/alfworld.html)。[在线完整轨迹](http://127.0.0.1:4179/alfworld.html#/?tab=read&left=m1-t1-pc-s)由 `planner-alfworld-prompts-review-4179.service` 独立静态服务提供，不经过 Live Server。

已用本机无头 Chrome 逐条核对六配置共 93 次调用，页面展示的全部消息正文与响应和原始 JSON 完全一致，PC-S 围栏原文可见；无脚本错误，检查期间无自动导航或刷新。[浏览器核对记录](runs/alfworld-test1-qwen38-prompts-03/viewer-check.json)保存在同一目录。

### 六配置独立目录更新后的复验

研究者于 2026-11-25 授权用更新代码再跑同一单任务并展示完整实际请求。运行目录为 `runs/alfworld-test1-qwen38-prompts-02/`，隔离源码为 `runs/.source-alfworld-test1-qwen38-prompts-02/`；保存当前 Git 基线、包括未跟踪提示词模块的工作区补丁和完整提示词副本。旧 01 和完整矩阵产物不覆盖。

本轮只检查六目录路由、Full/sub 文案和行动／求助规则的实际组装与模型行为。沿用 `test/1`（`clean some bowl and put it in cabinet.`）、Planner `Qwen3.8-27B`／Executor `DeepSeek-V4.1-Flash`、`plan-test` 的 ALFWorld 0.4.2，每配置一次、最多 20 个真实步，并发 1、共享 100 请求／分钟。两角色温度 0.2／0.6，输出上限 1,536／768，`reasoning_effort: none`、模型采样 seed 未指定、输入窗口 `null`；请求超时 60 秒、自动重试 0。环境候选接口、协议校验和连续无动作保护不变，不为修正协议错误重采。后台服务 `planner-alfworld-test1-prompts-02.service` 正常退出（状态 0），清单于 2026-11-25 18:33:12（北京时间）记录六配置全部结束；日志在 `runs/alfworld-test1-qwen38-prompts-02.log`。这不是架构性能比较或文案收益的因果实验。

| 配置 | 原生奖励 | 真实环境步 | Planner / Executor 请求 | 总 token | 停止原因 |
| --- | --- | --- | --- | --- | --- |
| EO | 1 | 14 | 0 / 14 | 13,538 | `task_finish` |
| PE-S | 1 | 11 | 1 / 11 | 11,378 | `task_finish` |
| PE-D-F | 1 | 10 | 1 / 10 | 15,397 | `task_finish` |
| PE-D-S | 1 | 10 | 1 / 10 | 13,760 | `task_finish` |
| PC-S | 缺评 | 2 | 3 / 2 | 4,173 | `invalid_planner_json` |
| PC-F | 缺评 | 2 | 3 / 2 | 4,861 | `invalid_planner_json` |

共 49 个真实环境步、58 次请求（Planner 9、Executor 49），63,107 token（输入 59,477／输出 3,630），所有请求均有用量、显式推理 token 为 0；无归档重采。两种 PC 的事件 13 都以 Markdown 代码围栏包装 JSON，事件 14 被直接 JSON 解析拒绝；这里的缺评不计原生零分。两种 PE-D 的全部 Executor 请求均注册对应 Full/sub 工具，但实际在线求助为 0；本轮没有重复求助，也没有覆盖在线规划往返，不能将单次结果归因于提示修订。弃用目标分支仍未触发。

已逐条核对 58 份实际请求：均采用冻结副本中对应六目录模块，Planner 的 initial/monitor 文案与 Full/sub 范围匹配；任务／完整历史／当前菜单与规划的组装顺序符合当前实现。PE-D 只含一份互斥输出规则，工具描述与对应模块一致；Planner 不接收候选目录，未强制 `tool_choice`。组装核对通过不表示模型全部遵守输出契约。

产物包括[清单](runs/alfworld-test1-qwen38-prompts-02/manifest.json)、[汇总](runs/alfworld-test1-qwen38-prompts-02/summary.json)、[请求组装核对](runs/alfworld-test1-qwen38-prompts-02/prompt-assembly-audit.json)、[源码补丁](runs/alfworld-test1-qwen38-prompts-02/source.patch)、[源码来源](runs/alfworld-test1-qwen38-prompts-02/source.json)、[启动脚本](runs/alfworld-test1-qwen38-prompts-02/launch.py)、[完整提示词目录](runs/alfworld-test1-qwen38-prompts-02/prompts/)与[完整离线轨迹页](runs/alfworld-test1-qwen38-prompts-02/alfworld.html)。[在线轨迹入口](http://127.0.0.1:4178/alfworld.html#/?tab=read&left=m1-t1-pe-d-s)由 `planner-alfworld-prompts-review-4178.service` 独立静态服务提供，不经 Live Server，旧目录不覆盖。

已用本机无头 Chrome 打开实际独立页，依次读取六配置，将 58 次调用全部展示的消息正文和响应与原始轨迹逐字比对；无页面脚本错误，检查期间无自动导航或刷新。[浏览器核对结果](runs/alfworld-test1-qwen38-prompts-02/viewer-check.json)保留在同一运行目录。独立页使用 HashRouter，直达阅读需使用 `alfworld.html#/?tab=read&left=<trial_id>`。

### 首轮单任务采样

研究者授权使用最新工作区提示词运行一个真实 ALFWorld 任务，检查实际输入、规划与执行是否符合预期。本次选用此前讨论的 `test/1`，目标为 `clean some bowl and put it in cabinet.`，六配置各从同一初态独立执行一次。不扩展到完整测试集，不训练，不以该样本估计架构成功率；协议错误与有效评分不为改善结果而重采。

| 项目 | 本次固定设置 |
| --- | --- |
| 模型 | Planner `Qwen3.8-27B`／Executor `DeepSeek-V4.1-Flash`；EO 无 Planner，经现有 Magpie 同济原生入口。 |
| 环境与任务 | `plan-test`，ALFWorld 0.4.2／TextWorld 1.7.0；`runs/data/alfworld-test` 的 canonical 任务与 gamefile 映射，仅加载 `test/1`。 |
| 架构与预算 | EO、PE-S、PE-D-F、PE-D-S、PC-S、PC-F 各一次，每组最多 20 个真实环境步，并发 1，共享 100 请求／分钟。 |
| 采样与窗口 | Planner／Executor 温度 0.2／0.6，输出上限 1,536／768 token；`reasoning_effort: none`，模型 seed 未指定，输入窗口 `null`。 |
| 故障与尝试 | 请求超时 60 秒、请求级自动重试 0；仅可恢复外部故障按既定规则补一次，每条总尝试至多两次，保留原失败与全部成本。 |
| 提示与控制 | 使用任务类型映射、四份独立 PC 模板和新的 monitor 文案；不注入阶段标题，不做 Planner 终局 review，不提取 `executor_claims`。被舍弃目标按当前实现原文留档。文案本身仍待研究者审核。 |
| 源码与产物 | Git 基线 `3db2de9` 加本轮工作区补丁，冻结在 `runs/.source-alfworld-test1-qwen38-prompts-01/`；新 run 为 `runs/alfworld-test1-qwen38-prompts-01/`。 |

采样由后台服务 `planner-alfworld-test1-prompts-01.service` 执行，清单于 2026-11-23 18:04:42（北京时间）记录全部结束，后台正常退出。隔离副本已核对与启动时主工作区的 Planner、Executor、运行器和 session 文件一致，后续编辑未进入本次请求。实际保存了[源码补丁](runs/alfworld-test1-qwen38-prompts-01/source.patch)、[配置](runs/alfworld-test1-qwen38-prompts-01/config.yaml)、[启动脚本](runs/alfworld-test1-qwen38-prompts-01/launch.py)、[框架文案](runs/alfworld-test1-qwen38-prompts-01/prompts/frameworks.py)／[ALFWorld 文案](runs/alfworld-test1-qwen38-prompts-01/prompts/alfworld.py)、[清单](runs/alfworld-test1-qwen38-prompts-01/manifest.json)、[汇总](runs/alfworld-test1-qwen38-prompts-01/summary.json)与[完整离线轨迹页](runs/alfworld-test1-qwen38-prompts-01/alfworld.html)；不能用基线提交冒充未提交文案。[六配置轨迹页](http://127.0.0.1:4177/alfworld.html)已通过 `planner-alfworld-prompts-review-4177.service` 的独立静态服务提供，不经过 Live Server 的热刷新。

| 配置 | 原生奖励 | 真实环境步 | Planner / Executor 请求 | 总 token | 停止原因 |
| --- | ---: | ---: | ---: | ---: | --- |
| EO | 1 | 14 | 0 / 14 | 12,647 | `task_finish` |
| PE-S | 1 | 11 | 1 / 11 | 11,207 | `task_finish` |
| PE-D-F | 缺评 | 0 | 2 / 2 | 4,069 | `consecutive_no_action_rounds` |
| PE-D-S | 缺评 | 0 | 2 / 2 | 3,444 | `consecutive_no_action_rounds` |
| PC-S | 1 | 13 | 13 / 13 | 32,689 | `task_finish` |
| PC-F | 缺评 | 7 | 8 / 7 | 17,705 | `invalid_planner_json` |

六组均为 attempt 1，没有恢复或归档尝试；累计 45 个真实环境步、75 次模型请求（Planner 26／Executor 49），全部返回用量，合计 81,761 token（输入 74,867、输出 6,894）。75 次响应均显式报告推理 token 为 0。缺评维持 null，不当作环境零分。

实际 Planner 请求首句均使用 `household`，没有两种英文阶段标题；新事件不含 `terminal_review`、`read_only` 或 `executor_claims`。PC-S 的 13 个环境动作对应 13 次 Planner 调用，最后一次 Executor 获得环境终局后直接停止。两种 PE-D 均在 Thought 中表示准备检查 countertop，却再次调用 `request_plan`，在尚未派发环境动作时因第二次连续求助停止；PC-F 在第 7 步后的 Planner 回复用 Markdown 代码围栏包裹 JSON，直接 JSON 解析拒绝并缺评。原始响应保留，未为修正这些协议问题重采。所有 `discarded_stages` 记录均为空，本次没有验收弃用目标与重规划的实际分支；该能力仍只有离线覆盖。这一个任务不能支持架构性能或本轮 prompt 收益的比较结论。

## 完整测试集评测：Qwen Planner 与 DeepSeek Executor

研究者已明确授权在官方 ALFWorld 测试集完成一轮六架构测试，并确认接口实际 Planner 为 `Qwen3.8-27B`（原消息的 `qwen3.2-27b` 经实时模型目录核对后更正），Executor 为 `DeepSeek-V4.1-Flash`。本轮不训练，不扩展到其他模型或任务集。

| 项目 | 本轮固定设置 |
| --- | --- |
| 数据与划分 | ALFWorld 0.4.2、`json_2.1.1/valid_unseen` 的全部 134 个游戏；test 对应 `eval_out_of_distribution`。 |
| 架构与次数 | EO、PE-S、PE-D-F、PE-D-S、PC-F、PC-S，每任务各一次，共 804 条。EO 无 Planner。 |
| 两角色模型 | Planner `Qwen3.8-27B`，Executor `DeepSeek-V4.1-Flash`；两者经同济 Magpie 原生透传入口。 |
| 输入与输出 | 使用当前历史前置、指导后置的 prompt 及明确的 revision_reason 说明；窗口容量 null，保留完整可见历史。Planner／Executor 输出上限 1,536／768 token。 |
| 采样 | Planner／Executor 温度 0.2／0.6；模型采样 seed 未指定，任务顺序 seed 417。 |
| 执行预算 | 每条最多 20 个真实环境步；首次完整尝试总上限 16,080 步，本地拒绝与求助按既定规则单列。 |
| 调度与恢复 | 并发 4，两角色共享 100 请求／分钟；请求超时 60 秒、请求级自动重试 0。全部首轮结束后，只对未完成或可重试外部故障恢复一次，每条总计最多两次尝试；保留所有尝试成本，不重跑已有评分或协议缺评。 |
| 评分与缺评 | 保存原生奖励与成功标志；协议／基础设施缺评保持 null，不当零分。报告各架构有效评分数、成功率、覆盖率与成本，并保留完整轨迹。 |
| 配置与产物 | [独立 Recipe 配置](../../src/recipe/planner-centered/config-alfworld-qwen38-27b.yaml)；新目录 `runs/alfworld-test-qwen38-27b-deepseek-02/`，与两轮 dev/2 验收隔离。 |

静态准备数据位于 `runs/data/alfworld-test/`。测试集任务表与旧的已核对映射存在 ID 排序差异，不能混用；新副本同时复制已匹配的 canonical 任务表与完整映射，保持 134 个游戏各出现一次，再用当前环境逐游戏重载核验。静态来源为 `experiments/planner-centered/runs/data/alfworld/data/alfworld_test_tasks.jsonl` 与同级准备目录的 `alfworld_test_gamefiles.jsonl`；新副本已在 ALFWorld 0.4.2 下完成全部 134 游戏的无模型重载检查。只复用任务元数据，不导入任何旧成绩。运行使用隔离的源码工作副本，保存 Git 基线与工作区补丁，后续 main 的修改不改变正在执行的测试。

研究者要求重新开始，并明确允许删除刚才的旧完整运行。旧进程已确认不在，旧完整测试目录与日志已删除，开发验收与测试元数据保留；旧轮不并入本轮成绩。本轮从零重新执行 804 条。隔离源码改存实验目录下的持久位置，不再依赖临时目录。

完整评测最初作为用户后台服务 `planner-alfworld-qwen38-27b-02.service` 启动。执行源码副本为 `experiments/planner-centered-v2/runs/.source-alfworld-test-qwen38-27b-deepseek-02`，由 Git 基线 `1972b47`、当时的工作区补丁和独立配置构成。源码副本与 main 后续修改隔离。首轮 `source.patch` 保留原样，恢复时同步的资源修复另存为 [recovery-source.patch](runs/alfworld-test-qwen38-27b-deepseek-02/recovery-source.patch)。

执行证据以 `runs/alfworld-test-qwen38-27b-deepseek-02/manifest.json`、逐条 checkpoint 和旁边的 `.log` 为准；manifest 的汇总在每次 invocation 结束时更新，运行中不能把尚未刷新的 queued 数量当作实际进度。首轮完成预检并调用两角色模型后发生下述配额中断；按既定范围恢复后，完整调度已结束，并写入 `summary.json`／`results.md`、`alfworld/data/` 与 `alfworld.html`，失败与缺评仍保留。

### run02 quota 中断与恢复

首轮 804 条均留下终止记录，其中 116 条有有效原生评分，688 条缺评。恢复前状态如下；这是中断快照，不是最终六架构成功率：

| 类别 | 条数 | 处理 |
| --- | ---: | --- |
| 原生成功 | 76 | 保留评分与完整轨迹，不重跑。 |
| 20 步预算耗尽、原生零分 | 40 | 保留有效零分，不重跑。 |
| 无事件的 `OSError` 启动失败 | 606 | 在实际模型／环境事件产生前失败；修复后各恢复一次。 |
| `InternalServerError` | 7 | 保留失败尝试及已发生的成本，各恢复一次。 |
| 协议错误 | 75 | 保持缺评，不重新采样；[完整核查](#首轮-75-条协议缺评核查)见下。 |

最终异常明确位于 `fast_downward` 复制动态库：目标副本大小 32,534,448 字节，返回 `[Errno 122] Disk quota exceeded`；`/tmp` 挂载点启用了 `usrquota`。原执行方式每条 trial 新建 TextWorld 后端；`fast_downward` 将动态库复制到临时文件、加载后删除路径，TextWorld 的环境关闭没有卸载该库，进程仍持有已删除的库副本。文件名已删除不代表其占用已经释放，磁盘整体剩余空间也不能排除用户配额耗尽。

最小修复是在 Toolkit 的 `AlfWorldRolloutPool` 增加显式 `reuse_slots()` 作用域，Recipe 将预检和全部任务调度放在同一作用域中。完整 slot 归还后才可复用，并发借出彼此隔离，每条任务仍重载其游戏、从指定初态开始；并发 4 时最多建立 4 个底层环境，退出时统一关闭。作用域外沿用即开即关，不修改 `fast_downward` 的全局加载函数，不全局共享单个 native 库句柄，也不更改模型、prompt、框架协议或评分。当前代码是未提交工作区修复。

无模型资源验证直接检查进程映射中的不同库副本：[修复前](runs/alfworld-test-qwen38-27b-deepseek-02/diagnostics/mappings-before.json)逐条新建并加载 12 次，库副本从 1 增至 12；[修复后](runs/alfworld-test-qwen38-27b-deepseek-02/diagnostics/mappings-after.json)同时借出 4 个 slot、重载 12 轮，共 48 次任务加载，副本始终为 4。该诊断支持复用能限制库副本增长，未证明作用域退出后上游完成卸载；模型调用数为 0。Toolkit 的顺序复用、并发隔离、异常清理和作用域外行为测试通过，完整 Toolkit 检查为 82 项通过、3 项跳过。

恢复保持同一 run，仅对上述 606 + 7 = 613 条运行 `--resume`，每条包括首轮在内最多两次。首轮失败先归档，全部尝试成本保留；已有 116 条评分与 75 条协议错误不重跑，不将缺评补成零分。模型、134 游戏、六配置、20 个真实步、并发 4、100 请求／分钟及采样设置保持原协议。恢复进度需读取新的 checkpoint；本节快照不随恢复结果冒充最终成绩。

恢复选择已写入 [recovery-selection.json](runs/alfworld-test-qwen38-27b-deepseek-02/recovery-selection.json)，核对为 613 条，首轮 116 条原生评分和 75 条协议缺评未改写。用户后台服务 `planner-alfworld-qwen38-27b-02-recover.service` 完成 134 游戏的复用预检与模型恢复，于 2026-11-23 15:01:26（北京时间）结束调度，随后正常退出（状态 0）；启动入口保存为 [recovery-launch.py](runs/alfworld-test-qwen38-27b-deepseek-02/recovery-launch.py)，日志为 `runs/alfworld-test-qwen38-27b-deepseek-02-recovery.log`。隔离源码的 4 项 slot 测试与 19 项 benchmark storage 测试通过。[最终状态与结果](#完整测试结果与最终异常审查)见下。

### 首轮 75 条协议缺评核查

以下只统计配额中断时首轮的 75 条协议终止。原生环境评分均缺失，不作为 75 个环境零分，也不重采。完整机器明细与原始事件位置见 [protocol-audit.json](runs/alfworld-test-qwen38-27b-deepseek-02/protocol-audit.json) 的 `initial_snapshot` 和 `protocol_outcomes`；架构、直接触发角色与实际响应模型分别记录，不用 trial 的 Executor 标签替代 Planner 归属。

| 拒绝原因 | EO | PE-S | PE-D-F | PE-D-S | PC-F | PC-S | 合计 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `invalid_planner_json` | 0 | 0 | 2 | 0 | 17 | 7 | 26 |
| `missing_assessment` | 0 | 2 | 0 | 0 | 7 | 3 | 12 |
| `conflicting_plan_delivery` | 0 | 0 | 4 | 3 | 0 | 0 | 7 |
| `unverified_stage_transition` | 0 | 0 | 0 | 0 | 2 | 13 | 15 |
| `consecutive_no_action_rounds` | 0 | 0 | 7 | 7 | 0 | 0 | 14 |
| `mixed_action_and_tool_call` | 0 | 0 | 0 | 1 | 0 | 0 | 1 |
| **合计** | **0** | **2** | **13** | **11** | **26** | **23** | **75** |

直接触发输出为 Planner `Qwen3.8-27B` 60 条、Executor `DeepSeek-V4.1-Flash` 15 条；这只是触发位置，不能将交互循环的全部原因归责于最后一个角色。已核实的边界如下：

- **JSON 格式与 schema 外壳：38 条。** 26 条回复在外层增加 Markdown 代码围栏，围栏内均可解析为 JSON 对象，运行器直接解析原始正文而拒绝；另 10 条把真实实例值放在 `properties` 中，2 条直接返回同请求提供的 JSON Schema，导致顶层缺少 `assessment`。这说明输出格式与提示契约存在摩擦；去围栏或提取字段不证明后续阶段校验通过，更不能补出环境成功。
- **维持计划与重复交付：7 条。** Planner 同时返回 `keep: true` 和计划／阶段字段，逐条核对均与此前接受值相同。校验只看字段是否同时存在，不比较新旧值，因此同值重发也拒绝。这是当前维持协议的严格边界，不等于已观察到错误路线。
- **已验证状态与阶段不变：15 条。** 均返回 `previous_stage_status: "verified"`，证据引用非空、旧阶段存在，但计算后的当前阶段没有变化，触发结构校验。拒绝不是证据引用格式错误，也不是独立 verifier 判断语义不成立；当前尚未引入独立阶段语义 verifier。
- **连续求助上限：14 条。** Executor 在两次已派发环境动作之间第二次调用 `request_plan`，被未在模型 prompt 中说明的运行器上限拒绝；拒绝发生在第二次 Planner 调用之前，并不存在第二份 Planner 回复。13 条尚未执行真实动作，另 1 条在已执行 7 步后连续求助。这与环境最多 20 步是不同限制。
- **求助与动作混发：1 条。** 同一 Executor 回复既有 `Action:` 行又有原生规划工具调用，违反已说明的二选一规则。

恢复中新发生的协议终止单独统计，不能把首轮 75 条写成持续不变的全 run 总数。2026-11-23 13:40:18（北京时间）的有界审计快照新增 15 条：围栏 8、schema 外壳 2、阶段未变 2、连续求助 3；合并当时共 90 条协议缺评，详见同一机器文件的 `recovery_snapshot`／`combined_snapshot`。扫描时恢复仍在运行，后续结果不在该快照内。

本轮只补齐分析与轨迹审核入口，恢复继续使用原有模型、prompt、格式解析与阶段／求助规则。是否调整格式容忍、`keep` 的同值处理、`verified` 与转段的关系，以及连续求助上限，留作后续版本的明确决定，不在运行中更换协议。

实际审阅使用[异常轨迹查看页](runs/alfworld-test-qwen38-27b-deepseek-02/failure-review.html)，页面保留完整 prompt／response、工具与环境事件，可跳转原始 JSON 和拒绝位置。首次[临时快照清单](runs/alfworld-test-qwen38-27b-deepseek-02/failure-review-data/snapshot-interim-134205.json)采于 2026-11-23 13:42:05（北京时间），比上述机器审计更晚：710 条异常尝试，包括 606 条启动 `OSError`、7 条服务端故障和 97 条协议终止，含已归档尝试；排除 147 条 `task_finish`／`executor_budget` 尝试及 4 条仍在运行的尝试。不能把它与 13:40:18 的 90 条审计或首轮 75 条相加。

研究者通过 VS Code 的 Open with Live Server 打开临时页时遇到持续刷新。实测该 HTTP 页面被 Live Server 注入 WebSocket 刷新脚本，8 秒内收到 9 次 `reload` 通知；磁盘 HTML 本身没有自动刷新逻辑。研究者改为等待实验结束后审查完整页面，不修改插件全局设置。

后台任务 `planner-alfworld-qwen38-27b-02-final-review.service` 已在恢复服务退出后运行 [build_failure_review.py --final](runs/alfworld-test-qwen38-27b-deepseek-02/build_failure_review.py)，确认 804 条最终轨迹及 613 条归档尝试齐全、没有未结束尝试，于 2026-11-23 15:01:31（北京时间）生成最终查看页与 [snapshot.json](runs/alfworld-test-qwen38-27b-deepseek-02/failure-review-data/snapshot.json)。[最终异常轨迹审查页](http://127.0.0.1:4176/failure-review.html)现由不注入热刷新脚本的独立静态服务提供，也可直接打开 HTML。入口为 [finalize_failure_review.py](runs/alfworld-test-qwen38-27b-deepseek-02/finalize_failure_review.py)，状态日志为 `runs/alfworld-test-qwen38-27b-deepseek-02/review-finalization.log`；该导出未增加模型调用或重跑。

### 完整测试结果与最终异常审查

本轮 804 条最终轨迹均已结束：465 条有原生评分，其中 314 条成功、151 条预算耗尽零分；339 条缺评，其中 333 条协议终止、6 条外部故障。全部 613 次恢复保留首轮归档，总计 1,417 次尝试，无运行中记录。结果来源为 [manifest.json](runs/alfworld-test-qwen38-27b-deepseek-02/manifest.json)、[summary.json](runs/alfworld-test-qwen38-27b-deepseek-02/summary.json) 和 [results.md](runs/alfworld-test-qwen38-27b-deepseek-02/results.md)。[完整结果与全部最终轨迹页](http://127.0.0.1:4176/alfworld.html)可与异常审查页分别查看。

| 架构 | 有效评分 / 134 | 评分覆盖率 | 原生成功数 | 成功率（仅有分） | 缺评 |
| --- | ---: | ---: | ---: | ---: | ---: |
| EO | 134 / 134 | 100.0% | 88 | 65.7% | 0 |
| PE-S | 121 / 134 | 90.3% | 73 | 60.3% | 13 |
| PE-D-F | 93 / 134 | 69.4% | 64 | 68.8% | 41 |
| PE-D-S | 78 / 134 | 58.2% | 55 | 70.5% | 56 |
| PC-F | 2 / 134 | 1.5% | 2 | 100.0% | 132 |
| PC-S | 37 / 134 | 27.6% | 32 | 86.5% | 97 |

缺评保持 `null`，不计为原生零分。仅有分样本的成功率受不均衡的协议终止筛选，不能直接排名架构性能；尤其 PC-F 的 100% 只来自 2 条有分轨迹，并不表示完整测试成功率为 100%。只有 test/112 与 test/116 在六配置中都有原生评分，完整六架构配对比较只覆盖这两个任务。本轮单次、未训练的配置测试也不提供训练收益或机制因果证据。

最终[异常审查页](http://127.0.0.1:4176/failure-review.html)固定收录 952 次异常结束的尝试，保留完整 prompt／response、环境事件和归档原始 JSON；排除 465 次 `task_finish`／`executor_budget`，未结束尝试为 0。下表区分最终格子与全部尝试，不能将归档启动故障重复计入最终缺评数：

| 停止错误 | 最终轨迹 | 全部异常尝试（含归档） |
| --- | ---: | ---: |
| `invalid_planner_json` | 127 | 127 |
| `missing_assessment` | 49 | 49 |
| `unverified_stage_transition` | 74 | 74 |
| `consecutive_no_action_rounds` | 56 | 56 |
| `conflicting_plan_delivery` | 22 | 22 |
| `mixed_action_and_tool_call` | 4 | 4 |
| `missing_revision_reason` | 1 | 1 |
| `InternalServerError` | 4 | 11 |
| `APITimeoutError` | 2 | 2 |
| 启动 `OSError` | 0 | 606 |
| 合计 | 339 | 952 |

协议错误共 333 条，分架构为 EO 0、PE-S 10、PE-D-F 41、PE-D-S 55、PC-F 131、PC-S 96；全部尝试另含 13 次服务／超时故障和 606 次启动故障。上文 `protocol-audit.json` 仍是首轮与恢复早期的有界审计，不是最终 333 条的逐条机制核查；最终数量以本节和查看页快照为准。已核查的首轮机制不能直接推广为全部后续样本的原因。

唯一 `missing_revision_reason` 出现在 `m1-t89-pc-f` 的 attempt 2，模型事件 18 后由事件 19 拒绝。该次把整体计划第一阶段完成条件中的 `cup` 改为 `cup (or mug)`，没有同时给出 `revision_reason`；实际请求已明确要求任何整体计划内容变化均须填写该字段。这一条属于当前已说明的字段契约，不沿用最早开发验收中提示缺失的解释。[原始轨迹](runs/alfworld-test-qwen38-27b-deepseek-02/trials/m1-t89-pc-f.json)

全部尝试累计 7,248 次真实环境派发、2,305 次 Planner 请求与 7,446 次 Executor 请求。9,738 / 9,751 次请求返回 token 用量，已报告合计至少 11,267,225 token（输入 10,459,415、输出 807,810），另 13 次用量未知；失败与归档尝试均计入，详见 `summary.json` 的角色成本。结果与运行时源码补丁保留在本地，下一步为研究者审查异常与协议处理，不自动重采或修改本轮成绩。

### 定位 bowl 时的求助与连续调用

研究者指出的 `m1-t1-pe-d-s`（attempt 2）体现了规划援助、执行分支选择与运行器停止规则的叠加。[原始轨迹](runs/alfworld-test-qwen38-27b-deepseek-02/trials/m1-t1-pe-d-s.json) · [定位到审查页](http://127.0.0.1:4176/failure-review.html#/?tab=read&left=m1-t1-pe-d-s-attempt-2)

| 事件 | 实际输出与处理 |
| --- | --- |
| 2 | Planner 给出定位 bowl 的目标，完成条件为找到并拿起 bowl。 |
| 5 | Executor 已在 Thought 中表示先查 countertops，但实际调用 `request_plan`，询问更高效的定位方法。 |
| 6 | Planner 的 assessment 认可求助合理，同时返回 `keep: true`，没有补充搜索顺序或方法。 |
| 8 | 工具结果只回送“保留当前指导”及原目标、完成条件；Planner 的 assessment 不回送 Executor。 |
| 9 | Executor 再次表示先查 countertop，却把这项执行意图写进新的 `request_plan.reason`，没有生成 `Action:`。 |
| 10–12 | 第二次连续求助触发 `consecutive_no_action_rounds`，再次调用 Planner 前即停止；真实环境步为 0，评分为 null。 |

Planner 判断当前目标仍有必要，并未回答请求中的搜索方法；`keep` 在结构上合规，但需要区分目标有效性与援助是否满足请求。当前子计划工具描述侧重阶段完成、受阻或失效后的规划请求，而该次请求希望在目标不变时获得方法指导。现有交付中 `keep` 只重送原目标与完成条件，assessment 不进入工具返回，也没有独立的补充指导字段；这构成待审的职责与接口边界，不由单例直接决定应采用的新格式。

第二次工具调用没有提出新的求助问题，其参数表达的是准备执行；这是可见执行意图与实际调用分支不一致，不能从 Thought 推定或代执行某个命令。先查 countertops 的想法在首次求助前已有，不能说成 Planner 回复后才形成。初始目标为 locate、完成条件却包括 pick up，粒度也需留意，但本例尚无环境动作，不能归为直接终止原因。该例不证明更具体的 Planner 回复或放宽连续求助限制就会使任务成功，也不单独证明需要 benchmark 专用 Planner 提示词。

## 测量与结果记录

| 项目 | 口径 |
| --- | --- |
| 原生表现 | 按任务和模型报告原生分数、成功与有效评分数；缺评不当 0 分，任务失败与运行／协议错误分别记录。 |
| 真实环境步 | 计实际派发的环境交互，包含环境拒绝的动作；本地拒绝和规划求助单列。 |
| 模型开销 | 分 Planner／Executor 记录请求尝试、输入／输出 token、服务端报告的推理与缓存用量，以及缺失用量。失败和恢复尝试不从成本中删除。 |
| 上下文与时间 | 保存窗口估算依据、保留与淘汰的历史范围、服务端实际用量，以及模型调用时间和端到端墙钟时间。 |
| 轨迹 | 保留完整 prompt、原始响应、原生工具参数和结果、环境反馈、阶段判断与停止理由，便于逐条检查。 |

本轮只比较未经专项训练配置的实际任务表现与成本，不增加训练收益或机制因果解释。阶段统计用于核对调用链是否实际出现，例如 PE-D-F 的原生求助是否触发，不由未触发样本推定该分支已经验收。

## 产物与运行状态

新输出使用本目录下独立的 `runs/<run-name>/`，包含运行清单、配置设置、`trials/` 原始轨迹、恢复尝试与由其导出的查看页。原始大产物保留本地，按项目约定不提交凭据、数据集或大规模日志。报告链接明确对应新运行，不合并旧实验评分。

两轮单任务接口验收及完整测试 run02 均已结束，结果与最终异常审查页已导出；框架协议与规划能力的解释仍待研究者审核。先前实现已随五批本地提交合并到 `main`，后续 prompt、矩阵入口与资源修复仍为工作区修改，结果记录与隔离运行源码分别追踪。

| 检查 | 结果与限制 |
| --- | --- |
| Python 离线检查 | Toolkit 78 项、Planner-Centered 31 项、Strategy-Sampling 4 项，共 108 项通过、5 项因后端依赖或显式开关跳过。 |
| 环境检查 | 主 requirements 固定版本已安装；pip check、相关 Hugging Face 包导入与 ALFWorld 实际重载／动作通过。 |
| 查看页与研究网站 | 12 项单元检查、6 项浏览器检查与静态构建通过；ALFWorld 页面使用合成 v3 数据，不读取旧轨迹。4 张提案 Mermaid 图已在浏览器渲染。 |
| 资源修复检查 | Toolkit 82 项通过、3 项跳过；真实无模型检查中 48 次重载保持 4 个 native 库副本。与上方早期开发检查分开记录。 |
| 未运行范围 | 没有训练；模型运行限定为上述 ALFWorld 开发验收和已授权完整测试。未安装 Harbor，Terminal 原生集成未运行。WebShop／ScienceWorld 未进行本轮真实后端复验。 |

后续审查完整异常轨迹与协议边界，再确定独立版本中的修改和测试。研究者的后续训练问题保持为未来研究，不作为这一轮配置测试的前置答案。
