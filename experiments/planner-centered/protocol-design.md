# 动态规划协议实施方案（历史快照）

本文件保留 `two-phase-v2` 及更早方案的形成过程，不再作为当前实施协议。当前实验与 v3 协议见 [Planner-Centered v2](../planner-centered-v2/README.md)，运行入口只支持新协议；下文旧字段、预算与兼容路径按快照当时状态解释。

该快照实现采用 `two-phase-v2`，在两阶段控制流上恢复完整交互历史和独立观察编号。环境动作接口、原生求助工具说明和环境已填好名称、按状态筛选的候选列表保持不变；本轮不评估动作接口辅助的收益。[研究讨论](../../DISCUSSION.md#实机轨迹审阅上下文与输出格式) · [实现](../../src/toolkit/frameworks/runtime.py)

按研究者最新决定，独立 Hard constraints 参数、状态字段、清单字段和提示块已删除。任务原文要求保留，历史原始输入不改写；下方折叠的旧方案仍保留当时的字段和措辞。

## 当前两阶段控制流

| 配置 | 初始规划 | 执行与监测 |
| --- | --- | --- |
| EO | 无 Planner。 | Executor 直接选择环境动作。 |
| PE-S | 直接调用 Planner 交付一次 full-plan。 | Executor 继续整任务，不提供规划工具。 |
| PE-D-F/S | 直接调用 Planner，分别交付 full-plan 或当前 sub-plan。 | Executor 平时直接执行；收到它的原生 `request_plan` 才进入在线规划分支，配对返回后继续执行。 |
| PC-F/S | Planner 以普通 JSON 交付初始整体计划与当前编号，或当前阶段。 | 每个非终局轮直接调用一次 Executor；环境未终止时再由 Planner 监测、维持或更新，然后继续执行。双方不注册执行工具。 |

两种 PC 的第一阶段只规划，不执行环境动作。第二阶段使用固定的“单步执行 → 环境反馈 → 非终局监测”循环。Planner 可以判断阶段是否完成和是否改路线，整任务的终止与成败由环境反馈及独立验收确定。开放任务由 Executor 经环境提交，不使用 Planner 的 `submit_task`。终局或预算后最多一次只读收尾，失败不改写已有裁决。

## 规划交付与真实工具调用

Planner 的初始规划和在线监测均返回普通文本中的一个 JSON 对象，不带 `tools`、`tool_choice` 或 provider 专用格式参数。`thinking_summary` 必填，`evidence_refs` 只能引用当前可见观察；对象解码和原有字段、阶段、引用校验先于状态交付。P10 的未知键、Markdown 等扩展兼容策略继续延后。

| 角色与范围 | 初始交付 | 后续交付 |
| --- | --- | --- |
| PE full/sub | `full_plan` 或 `stage_objective`、`completion_condition`。 | 对应范围的新指导，或 `keep: true`。 |
| PC-F | `full_plan` 与 `current_subplan_id`。 | 保持时省略计划字段；转段更新当前编号；修订路线时给完整计划、编号和 `revision_reason`。 |
| PC-S | `stage_objective` 与 `completion_condition`。 | 保持时省略两字段；转段交付新阶段。 |

PC 沿用公开证据、已验证阶段、`previous_stage_status`、`hypotheses` 和 `remaining_work` 的边界，空剩余工作不能触发结束。完整计划保留在 PC-F 的 Planner 侧，Executor 只接收当前实际交付的阶段。已完成阶段只回放阶段目标、完成条件与观察引用，不携带当轮判断中的未来不确定性；完整 `thinking_summary` 仍保留在原始日志。`verified` 是 Planner 判断，阶段独立语义 verifier 尚未引入。

只有 PE-D 的 Executor 通过 `FunctionTool` 请求 `request_plan(reason, evidence_refs?)`。首次计划已由运行器直接取得；这个工具仅用于执行阶段的后续求助。运行器补齐任务目标、当前计划和公开观察，Planner 返回 JSON 后渲染为文字工具结果，保留原 `tool_call_id` 配对。一次工具求助不派发环境动作；不能在同一次回复中混合工具请求与环境 `Action:`。`deliver_plan`、`execute_step`、`submit_task` 不再作为模型工具。

## 状态、预算与版本边界

单次 `FrameworkRun` 保存规划、阶段和公开证据，复用 `RolloutSession` 执行模型和环境调用。真实环境与工作区持续存在；双方保留完整可见交互历史，不再使用 Recent／Earlier 两块或跨阶段清空窗口。Executor 原始回复、原生工具配对及完整动作反馈保留；当前动作列表由环境单独注入，Planner 不获得该目录。ALFWorld 的初始场景与任务目标分开呈现。运行器参数、剩余额度和事件元数据不进入任务正文。

初始观察从 1 开始，后续实际环境反馈连续编号；本地格式拒绝、模型调用和规划求助不占号。事件日志保留独立 `event_id`，观察另存 `observation_id`，规划引用使用观察号。完整历史不会自动摘要，现有调用方请求体字节预算仍显式检查；Toolkit 统一上下文窗口与压缩策略尚待设计。

初始化规划的模型成本单列。执行阶段以实际派发的环境交互计主预算，本地无效输出和规划求助不计环境步；两次真实动作之间最多一次无动作往返。初始规划之后到第一步也采用这个执行阶段限制。末步环境终局先于预算检查，异常保留已派发及结果未知状态，不自动重放。

新清单和轨迹标记 `two-phase-v2`，调用链显式传递协议。旧 `two-phase-v1`、`native-tools-v1` 及旧四配置记录仍可读取、汇总、导出；当前运行器拒绝两个旧六配置协议续跑，避免新流程或新引用语义被保存成旧版本。无协议的旧四配置仍保留 `--legacy` 执行路径。原始提示、回复、评分与归档尝试不改写。

## 两阶段协议验收

| 验收项 | 离线通过条件 |
| --- | --- |
| 两阶段与工具边界 | 非 EO 首调用为 Planner，初始失败时零执行；仅 PE-D Executor 暴露 `request_plan`，PC 交替执行与监测且无模型工具调用。 |
| 证据与上下文 | 求助 ID 配对；公开引用按观察号校验；长历史及原始 Executor 回复跨阶段完整保留，最新观察不重复，当前菜单仅 Executor 可见；环境只 reset 一次。 |
| 环境与预算 | 单步真实派发计量；末步终局优先；Planner 不能主观结束；非派发的环境提交仍保存终局观察；收尾失败保留裁决。 |
| 装配与兼容 | Recipe 的真实装配路径传入协议，新记录使用新身份；旧工具协议在环境准备、API 或写入之前拒绝续跑；新旧记录分别保持原始消息导出。 |

实现与测试入口为 [框架测试](../../src/toolkit/tests/test_framework_runtime.py)、[Recipe 存储与调用](../../src/recipe/planner-centered/tests/test_benchmark_storage.py)和[原始轨迹导出](../../src/recipe/planner-centered/tests/test_export_alfworld.py)。v2 本轮只做离线与无模型后端检查。此前 v1 按研究者授权使用同一 `dev/2`、一个模型、六配置和每组 20 个真实环境步完成实机验收；实际设置、原始轨迹、网络拒绝及恢复记录见[实机记录](README.md#two-phase-v1-实机验收)。旧单任务证据不验证 v2 的历史与编号改动，也不能证明成功率或学习收益。

<details>
<summary>历史 native-tools-v1 实施方案与当时核查</summary>

以下保留旧工具协议的设计、输入核查及当时验收条件，仅用于解释既有轨迹；其中的执行工具和实机步骤不代表当前两阶段流程。

EO 和 PE 由 Executor 推进整项任务，PC 由 Planner 推进整项任务。PE 的规划入口统一为原生 `request_plan`。两种 PC 共用 **Initial Sub-Plan Generation** 和 **Continuous Execution Monitoring**，Planner 先判断，再交付。Executor 的上下文跟随实际生效的 sub-plan 切换。以下规定六种配置的控制流、角色可见状态、预算和验收条件。[逐项讨论](../../DISCUSSION.md#规划覆盖范围与控制权) · [实施前协议快照](protocol-review.html#compare)

## 1. 六种配置与两条调用链

| 配置 | 首次规划 | 谁根据新证据推进任务 |
| --- | --- | --- |
| EO | 无 Planner。 | Executor 选择环境动作。 |
| PE-S | Executor 首步前取一次整体计划。 | Executor 持有整任务，此后规划工具关闭。 |
| PE-D-F | 规划工具交付剩余整项任务的 full-plan。 | Executor 平时自主行动。若重要前提失效或原路线不能满足约束，它调用规划工具，取得维持意见或一份可直接替换的剩余整体计划。 |
| PE-D-S | 同一工具交付下一个高层 sub-plan。 | Executor 判断本子目标已达成、受阻或需改方向时，再调用规划工具。它持有整任务，一份子计划可以跨多个环境动作。 |
| PC-S | Planner 用 *Initial Sub-Plan Generation* 产生第一个阶段目标。 | 每次单步执行工具返回后，Planner 用 *Continuous Execution Monitoring* 判断继续本阶段、验证完成并进入下阶段，或因新证据放弃、改写本阶段。 |
| PC-F | Planner 用 *Initial Sub-Plan Generation* 一次生成有编号的 full-plan，选定其中一个 sub-plan 生效。 | 每次单步工具返回后进入 *Continuous Execution Monitoring*。当前阶段完成时可仅推进编号；未来路线失效时才修订整体计划。 |

运行清单分别记录框架族、`plan_scope` 和协议版本。EO 的范围为空，PE-S 为 full，动态框架按 full 或 sub 派生对应的 F/S 标签。PE-D-F 与 PC-F 共用有序计划表示。PC-F 由 Planner 维护**当前阶段编号**并逐步判断，PE-D-F 的 Executor 自主决定执行位置和求助时机。两种 PC 的 Executor 都只接收当前阶段、原任务、硬约束和执行所需的公开证据。PC-F 的完整计划保留在 Planner 侧。

以购物限价 80、商品页显示 95 为例。PE-D-F 若已规定超价换品，Executor 自行换品；若购买路线原本依赖该商品符合预算，它才主动请求修订。PE-D-S 若收到“查明这件商品的价格”，Executor 可判断取证已完成并请求下一建议。同一次动作在 PC 中会自动返回给 Planner。PC-S 可核实价格并委派寻找替代品；PC-F 若已有“比较替代商品”阶段，只需转到该编号。四者都能利用同一观察，谁发起下一次决策、下一次需生成多少计划则不同。

## 2. 工具文档与角色交付

### PE：Executor 调用规划工具

按 `plan_scope` 向 Executor 注册原生工具 `request_plan(reason, evidence_refs?)` 的 full 或 sub profile。只有收到该工具的原生调用才进入规划流程。工具文档说明调用时机、所需输入和结果。若端点在正常请求中报告不支持原生工具，记录为配置不兼容。

| 工具文档项 | 给 Executor 的说明 |
| --- | --- |
| 用途 | 根据当前公开事实，请 Planner 给出初始计划、复核现有计划或提供下一子目标。若现有建议仍可执行，通常自行继续。 |
| 何时调用 | 首次规划按实验协议调用。F 在新事实改变重要前提、依赖或硬约束时调用，局部失败已有备选时直接执行。S 在本子目标已完成、证据表明不可行或需要下一方向时调用。 |
| 参数 | `reason` 写清要解决的规划问题、一句关键变化及其影响。可附 `evidence_refs` 指向当时可见的公开观察。初次调用只需说明要制定初始计划。 |
| 结果与代价 | F 返回维持意见或完整的剩余计划，S 返回维持意见或下一份子计划；工具结果渲染为文字。调用会实际消耗一次 Planner 推理，环境状态原地保留。 |

例如，Executor 可填写“当前商品售价 95，超过限价 80，原计划依赖购买这件商品。请给出剩余路线”，并引用价格观察。Harness 补入原任务、硬约束、有效计划及所引用的观察，形成完整的 Planner 请求。PE-S 和两种 PE-D 在首个环境动作之前都要求 Executor 调用一次 `request_plan`。首次取计划计一次 Executor 调用、一次 Planner 调用、零次环境交互。成功后 PE-S 撤下该工具，两种 PE-D 保持可用；同一初始状态下也适用第 5 节的空转限制。

一次 Executor 选择要么派发一个环境动作，要么调用 `request_plan(reason, evidence_refs?)`。两者同时出现时不执行，避免在新计划到达前修改环境。工具出错只产生可归因的调用错误，不能伪造计划或环境观察。返回示例为“剩余计划已更新。排除此候选；在合规候选中比较尺寸和价格；核实规格后购买。”同样的事实在 sub profile 下可以只返回“下一子目标：找到另一件尺寸匹配且标价低于 80 的商品”。

### PC：Planner 调用单步 Executor

向 Planner 注册原生工具 `execute_step`。首次或变更阶段时提交委派，保持阶段时引用生效阶段即可。Harness 按该阶段为 Executor 组装文字输入，Executor 根据当前原生动作接口选择**一个**动作，Harness 将它送入同一个环境。工具收据直接取自执行记录，提供**实际动作和公开环境反馈**。动作未派发、已派发但结果未知以及环境已终局分别记录。阶段判断由 Planner 承担，Executor 无需编写状态报告。

例如 PC-F 已有“1 核价、2 比较替代品”的计划，Planner 在监控时选择阶段 2 并调用一次 `execute_step`。Harness 用当前编号找到“比较替代品”，把这句阶段目标交给 Executor；完整计划继续由 Planner 持有。PC-S 在同一位置直接给出新的阶段目标。若只是继续执行，两个 profile 都可沿用已存的当前阶段，避免模型反复复写计划。

**PC-S、PC-F 使用同一组两阶段提示。** 每个任务初始化一次；每个有公开反馈的实际动作之后监控一次，包括任务的最后一步。初始化和每次监控各用一次 Planner 调用，在当轮完成判断与交付。

| 阶段 | 提示的共同任务 | PC-S 的交付 | PC-F 的交付 |
| --- | --- | --- | --- |
| **Initial Sub-Plan Generation** | 检查原任务、硬约束与初始观察。先给简短判断依据，再指定第一个可根据环境观察核对的阶段；需要行动时调用一次 `execute_step`。 | 直接给出首个 sub-plan 及达成条件。 | 一次给出带稳定编号的 sub-plan 列表作为 full-plan，指定首个活动编号。Executor 的委派取自该条目。 |
| **Continuous Execution Monitoring** | 对照已交付阶段、刚执行的动作和环境反馈，先说明已证实与未知的内容，再决定继续、转段或修订。 | 继续时沿用目标；转段时记录旧阶段结果及依据，并交付新的 sub-plan。 | 沿原路线推进仅更新活动编号；路线需要修订时更新 full-plan、活动编号和修订原因。 |

非终局监控若决定继续执行，直接调用一次 `execute_step`。正常流程为“初始化 → 单步执行 → 监控 → 单步执行 → 监控”。最后一次监控按第 5 节只读收尾。同一份环境反馈只触发一次 Planner 调用。

单步工具的最小交付按运行配置解释：

- PC-S 初始化或换段时提供 `stage_objective` 及达成条件，运行器保存为当前委派。监控维持时复用已保存的委派；离开旧阶段时记录其结果（已验证、受阻或被替换）、依据和公开证据引用。
- PC-F 初始化时提供 `full_plan`（一组带编号、目标和达成条件的阶段）与 `current_subplan_id`。监控时可只指定已有活动编号；修订路线才交付更新后的完整计划、活动编号及原因。工具始终从活动条目生成 Executor 的文字任务。
- 两种配置都在该轮决定中携带 `thinking_summary`。运行器先保存已接受的决定和证据，再向 Executor 派发一次；任务已终止或耗尽预算时，仅保存只读判断。

**线上传输与跨角色输入。** 工具定义放在 API 的 `tools` 中。调用模型会看到工具名、用途和参数约定。Harness 读取结构化 `tool_calls` 及其参数，保留同一次原生往返所需的关联 ID 和相应的工具结果消息。进入**被调用角色**的 `content` 则由选定字段重新组装为文字；返回给调用方的工具结果也写为文字。完整的 HTTP JSON、工具参数字典、日志事件、预算、原始 `<decision>` 都不应出现在跨角色任务正文中。下一次重建上下文，如已完成的工具往返被移出窗口，整组移出，避免悬空的工具响应。

例如同一笔执行，PC 的两个角色分别读到：

> **Executor 收到**　任务是买一件不超过 80 元且尺寸符合要求的商品。当前阶段是核对候选 A 的价格。当前页面和可用动作如下……
>
> **Planner 随后收到**　当前阶段是核对候选 A 的价格。刚才执行了 `click[候选 A]`。环境在观察 17 返回“价格 95 元”。本次返回由单步执行完成触发。

## 3. Planner 记忆、阶段返回与公开输出

| 配置 | 每次监控都要送回 Planner 的状态 | 转移时更新什么 |
| --- | --- | --- |
| PC-S | 原任务与硬约束；**全部已验证 sub-plan**，每项保留目标、已验证结果与证据引用；当前实际交付的 sub-plan 及其判定条件；本次返回原因、实际动作和新增反馈。 | Planner 对照公开证据判断。已满足的阶段加入已验证清单；受阻、被替换或证据不足的阶段另记状态和退回原因。切换前保留原阶段目标及其去向。 |
| PC-F | 原任务与约束；**当前完整的 full-plan、当前执行的 sub-plan 编号**及相应目标；刚才的动作、反馈、已有修订原因或本次触发来源。 | 沿原计划推进只更新编号。需重规划时，Planner 说明哪项新证据推翻哪项前提，修订剩余路线并明确新计划的活动阶段。修订前后的阶段对应关系留在运行器，避免重排后让同一编号指错目标。 |

每次都能知道“因一次动作得到反馈而唤醒”；是否需要结束阶段或改计划，要等本次监控才能判断。先把已知返回原因写入输入，Planner 新判出的修订原因随决定保存，下轮可见。不能请 Executor 预填 Planner 尚未形成的理由。PC-S 的已验证阶段逐条压缩成短记录，保留所有条目，原始事件按引用回查；超过容量时显式记录，便于判断长期账本是否可行。两种配置都暂留 `hypotheses` 与 `remaining_work` 作 Planner 的估计，只有公开证据支持的阶段达成才进入已验证清单。判断主体与证据来源可回查。

**P3、P4 的处理。** 将一次返回的**来源**与阶段的**判定**分开记录。来源由 Harness 写入，阶段判定由掌握控制权的角色作出。

| 情况 | 能据此确定什么 | PE 与 PC 如何处理 |
| --- | --- | --- |
| 取证结束 | 目标事实已有结果，包括否定结果。查到价格为 95，已回答“价格是多少”。 | PE 的 Executor 可用事实继续或通过 `request_plan` 求助。PC 的每步工具返回都会将该观察交给 Planner。 |
| 阶段完成 | 证据满足**已下发**的阶段条件。95 可完成“核价”，无法完成“找到低于 80 的商品”。两项判定在核价阶段可以同时成立。 | PE-D-S 由 Executor 判定并请求下一建议；PC 由 Planner 核对依据后登记并切换阶段。 |
| 安全返回或中断 | 技术或资源边界已到，阶段结果可能未知。 | 记录触发原因、是否派发及最后公开状态。逐步监控的 PC 已有自然返回点。预算耗尽按 P6 停止，仍未知的事项不记作完成。 |

**先判断，再交付。** 每次 Planner 调用产生一句公开判断依据（`thinking_summary`），再交付计划、维持意见、工具选择或收尾结论。依据只写证据支持的结论和关键不确定性；初始化时可写先要核实的前提。若模型通过工具参数交付，将依据保存在同一次决定中，由 Harness 先渲染依据、再呈现决定。计划栏只写待执行的工作。给 Executor 的输入只含实际交付及所需事实；公开依据留在 Planner 记录中供回查。

旧 ALFWorld 案例中，观察 22 和 32 支持“加热并放置了 mug 1”，缺少“mug 满足目标 cup”的证据。一份可接受的监控输出可以是：“判断依据：已放置 mug，目标 cup 仍未证实。下一阶段：找到并核实符合目标的 cup。”这比把“确认是否完成”写成两步计划后马上宣告成功更容易审查。它是改进方案示例，未重跑该轨迹。[历史原始回复](runs/alfworld-test-01-recovery-03/trials/m1-t58-pc.json#L1579)

## 4. Executor 请求与阶段上下文

**完整交互历史应留在轨迹中；在线请求只需要当前执行所需的信息。** 这里核对的是送进生成接口的请求，而非仅查看环境如何保存观察。

| 核对的调用入口 | 一次生成真正收到什么 |
| --- | --- |
| 本仓库的旧四配置协议 | `RolloutSession.step` 把累计 `state.history` 整份传给 Executor。环境每步追加 assistant 回复和 user 反馈；框架还追加指导。`model_call` 将该列表作为 SDK 的 `messages`，旧协议读取响应文本。 |
| 本地 verl-agent 上游训练 rollout | 每轮用当步环境管理器组装的文本建立一条 user 消息，套 chat template，生成 `input_ids`、`attention_mask`、`position_ids` 等，再把批次交给 `generate_sequences`。这是本地生成入口，不能将它描述成某个服务端 HTTP 请求。 |
| 上游 verl-agent 自带的 ALFWorld HTTP 示例 | `get_action_from_gpt` 把 `obs["text"][i]` 作为唯一一条 user 消息发给 SDK，调用参数包括 `model`、`temperature`、`n`、`stop`。[示例源码](https://github.com/langfengQ/verl-agent/blob/796ed310287fa605c9292a0fce07a86d79fde05e/examples/prompt_agent/gpt4o_alfworld.py#L34-L46) |
| 本地 verl-agent-system 的独立 Executor | rollout 每步把当前 metaplan 和组装好的执行观察传给 `sample_actions`。它新建一条 `user`，正文为当步观察、文字提示和该 metaplan，随后调用 Chat Completions。先前观察可由环境窗口写进这条文字。 |

**离线捕获的请求 JSON。** 使用实际 SDK 和内存 HTTP 响应，分别经过本仓库的 `run_framework` 和 fork 的 `Executor.sample_actions` 连续调用三次。在本仓库 EO 的三步样例中，`messages` 长度依次为 **1、3、5**，第三步是 user → assistant → user → assistant → user。外层字段为 `model`、`messages`、`max_tokens`、`temperature`、`reasoning_effort`、`stop`。fork 的三次长度为 **1、1、1**。下面用占位文字替换测试输入，保留 fork 的字段形状与默认生成参数：

```json
{
  "model": "Qwen2.5-7B-Instruct",
  "messages": [{"role": "user", "content": "<当步格式化观察>\nThis workflow might be helpful to you:\n<当前 metaplan>"}],
  "max_completion_tokens": 512, "temperature": 0.7, "top_p": 0.9, "stop": null
}
```

另向上游 WebShop 记忆放入四条带不同标记的旧观察。K=2 时，发送文字只含第三、第四条和当前观察，第一、第二条没有进入消息。这项方法级检查核对了一条消息**里面**究竟有什么。HTTP 捕获验证了消息形状，未测量线上缓存或模型能否正确选用新工具。

在上游 WebShop 环境管理器中，当步文字可包括当前任务、当前页、当前动作菜单及最近 K 次交互；配置默认 K=2。超过 13,000 个字符时，当步改用无历史模板。这个阈值作用于带历史的完整提示字符串。上游窗口实现与 fork 的 HTTP Executor 分别核对，不能由两处代码拼出一个已经实测的 fork WebShop 端到端结果。[本仓库会话](../../src/toolkit/rollout/session.py) · [本仓库请求与响应](../../src/recipe/planner-centered/run.py) · [上游 rollout](https://github.com/langfengQ/verl-agent/blob/796ed310287fa605c9292a0fce07a86d79fde05e/agent_system/multi_turn_rollout/rollout_loop.py#L90-L101) · [上游 WebShop 窗口](https://github.com/langfengQ/verl-agent/blob/796ed310287fa605c9292a0fce07a86d79fde05e/agent_system/environments/env_manager.py#L464-L505) · [本地 fork 的 Executor](../../../graduation_proj/codebase/verl-agent-system/agent_system/executor/executor.py) · [其 HTTP 调用](../../../graduation_proj/codebase/verl-agent-system/agent_system/executor/openai_agent.py)

**按生效的 sub-plan 刷新 Executor 上下文。** 控制器在新阶段首次执行前更新当前交付并清空旧阶段的交互窗口。每次请求由原任务、硬约束、当前交付、当前观察与动作菜单、本阶段最近 K 次动作及结果、跨阶段仍有用的公开事实组成。实施默认 K=2，各组使用同一规则。跨阶段事实以短摘录和公开出处保留。缓存命中、总输入、延迟及成功率分开测量，服务端未报告时记未知。

| 阶段边界 | 何时给 Executor 新上下文 |
| --- | --- |
| PC-S / PC-F | 新 sub-plan 生效、PC-F 转入另一编号，或当前目标及其达成条件被替换时换窗。保持当前阶段、更新假设或只修订未来路线时保留窗口。 |
| PE-D-S | 首次或下一份子计划生效时换窗。单纯求助、取得证据、Planner 维持旧建议，都沿用当前阶段。 |
| PE-D-F / PE-S | Executor 持有整任务。若已有明确生效的子计划交付，进入下一阶段时执行同一换窗规则。普通整项建议只有全文更新而没有显式阶段切换时，替换当前指导、保留近期交互。没有显式阶段时默认使用任务级短窗口。 |
| EO | 任务级短窗口。一个任务的所有动作共用同一个环境与记忆范围。 |

换窗依据取自控制器**实际接受并交付**的阶段转移。保持当前阶段目标时沿用其身份，替换目标或达成条件时为新交付分配身份。PC-F 重排未来条目时保留活动条目的身份。先配对已完成的工具调用与结果，再在新阶段只带入与新目标有关的公开事实、当前观察和原约束。真实环境、工作区、完整轨迹及预算计数持续保留。

该边界借鉴 LongHorizon-Harness 的子任务契约。它允许在同一契约内多次行动，跨契约保留状态与选定证据；本方案的 PC 按单步工具反馈监控。[LongHorizon-Harness §2.3](https://arxiv.org/html/2608.01964v1#S2.SS3) · [契约提示构造](https://github.com/AMAP-ML/LongHorizon-Harness/blob/v0.1.8/src/lh_harness/role_prompts.py#L149-L179)

## 5. 已同意的预算、收尾与落地顺序

**P6 已同意。** 共用真实环境交互上限，取消单独 Planner 次数额度。动作送入后端即计一步，包括后端拒绝的动作；在本地被判无效、规划工具调用及其他无动作往返单列。两次真实动作之间最多允许一次无动作往返，初始观察到第一步同样受约束。落实时以适配器是否实际派发为准，单凭已解析出动作文本会高估步数。[现行事件记录](../../src/toolkit/rollout/session.py) · [WebShop 派发位置](../../src/toolkit/envs/webshop_env.py)

闭合任务由环境判终，原生评分或独立 verifier 验收。末步先记录实际结果，再处理预算。PC 的最后一条动作反馈也交给 Planner；已终局时这次调用兼作唯一的只读收尾，到限未终局时只记状态，不再派发动作。收尾失败保留已知环境裁决。开放任务由负责人带证据提交，按约定验收；获准公开的驳回理由可在仍有余额时用于续接，待验和验收故障分别记录。收尾独立计费，实际调用、输入输出 token 和时间保留。终局信号、环境成功及 Planner 认为成功是三项不同的事实。[历史结束建议与评分](finish-advice.md)

| 实施次序与现有入口 | 离线验收条件 |
| --- | --- |
| 1. 模型调用。从 [recipe 的 model_call](../../src/recipe/planner-centered/run.py) 到[共享客户端](../../src/toolkit/models/openai.py)保留原生工具定义、返回参数与配对 ID，请求长度检查覆盖实际提示及工具定义。 | 用内存响应分别返回普通文本和仅含工具调用的消息；调用一次、正确配对一次，被调用角色收到文字任务。PE 取计划的环境步计为零，PE-S 下一次请求已撤下工具。 |
| 2. 控制与输入。在[框架控制器](../../src/toolkit/frameworks/control.py)实现六种配置和生效阶段转移，在[框架提示模板](../../src/toolkit/prompts/frameworks.py)实现两个 PC 共同阶段，在[共享会话](../../src/toolkit/rollout/session.py)按阶段构建 Executor 输入。 | 对同一条价格观察运行四个动态配置。两种 PC 各初始化一次，实际动作每得到一次反馈就监控一次；同轮记录判断依据和交付。PC-S 能回查全部已验证阶段；PC-F 能通过编号推进，也能只改未来计划。 |
| 3. 预算与清单。[环境适配器](../../src/toolkit/envs/base.py)在实际派发处计步，[recipe 调度](../../src/recipe/planner-centered/benchmark.py)与调用包装同步移除原先的按周期返回和角色上限。保留已获授权的运行资源边界。 | 本地无效动作计零环境步，后端拒绝已派发动作计一步。最后一步成功优先保留环境结果，最后一次只读收尾失败不改评分，连续无动作往返可终止。模型输入中没有剩余额度。 |
| 4. 轨迹与结果。[配对报告](../../src/recipe/planner-centered/report.py)和[轨迹导出](../../src/recipe/planner-centered/export_alfworld.py)从清单读取协议版本与配置集合，阅读器展示对应的实际交付。 | 旧四配置的样本仍按当时协议读取，新六配置各自可选、可配对。能从同一轨迹区分环境步、监控、换阶段、修订与收尾。历史 `pe-d` 或 `pc` 记录不并入新版变体的结果。 |

换窗回归用同一份三步夹具验收：第一步在阶段 A 观察到价格并记录出处；第二步仅修订未来阶段，此时仍可读到 A 的第一步交互；第三步转到阶段 B，传给 Executor 的请求已去掉 A 的对话和旧菜单，同时保留价格摘录及出处、当前页面和既有环境步数。P10 的扩展解析规则按约定延后。

## 6. 哪些问题必须一起审核

- **工具调用与控制权。** 比较 PE-D-S 和 PC-S 时固定子计划范围与 Executor 模型，同时记录谁获得观察机会、谁要求改计划、谁能继续整任务。PC 每步必监控，工具返回次数不能当作重规划次数。
- **全计划表示与阶段上下文。** 比较 PE-D-F 与 PC-F 时尽量对齐计划内容和反馈来源，单列 PC-F 的活动编号、Planner 的逐步监控以及给 Executor 的计划可见范围。仅换阶段、修订剩余路线和更新假设分别计数。
- **成本与效果。** 工具调用可能降低自定义协议的使用难度，也会增加往返或工具描述长度。短窗口、按阶段刷新、前缀缓存又分别影响输入成本。固定其他条件后比较触发正确性、误停、跨阶段事实遗漏、成功率、真实环境步与各角色调用成本。以上是协议设计与验收条件，收益有待实测。

## 7. 本轮实施验收

| 验收项 | 通过条件 |
| --- | --- |
| 六种控制流 | EO 全程没有 Planner；PE-S 只规划一次；PE-D 在原生工具请求时才规划；两种 PC 各初始化一次，逐条处理真实环境反馈，最后一条只读收尾。 |
| 交付与记忆 | 工具响应与调用 ID 配对，跨角色收到文字交付。PC-F 的 Executor 看到当前阶段；换段清除旧对话与旧菜单，任务事实及来源仍能回查，环境与步数继续累积。 |
| 停机与兼容 | 本地拒绝和取计划计零环境步；终局优先于预算；收尾失败保留已有评分；无法确定结果的动作保留其派发状态；旧四配置清单可继续验证和阅读。 |
| ALFWorld 实机 | 六组使用同一任务初态、相同环境步数上限和 Magpie 路由 `tongji/DeepSeek-V4.1-Flash`。各组留下真实模型请求、工具往返、环境记录和原生评分。分数按环境返回保留，接口错误和协议中断单列。 |
| 可视化 | 用现有 ALFWorld 阅读器展示六条轨迹；可切换架构、对照全文，查到原始提示、回复、工具调用、动作、反馈和终局。 |

实机验收使用已有的 ALFWorld `dev/2`（将遥控器放到沙发上），每种配置独立从同一游戏文件初始化。先跑上述离线验收，再执行一次六组实机运行。

</details>
