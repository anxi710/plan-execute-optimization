# 研究讨论

按主题持续更新。这里整理问题、工作假设和候选对照。已确认的研究状态与决定见[研究工作台](RESEARCH.md)，实验结果见[实验目录](experiments/README.md)。

## 全面审核清单

本轮先确认需要讨论与审核的问题清单，之后再开始新架构推演。本文集中维护清单，不另建平行待办。A 表记录已有材料的审核，D 表记录尚未决定的问题，R 表保留需要经验或资源证据回答的研究问题；编号沿用或续编，不表示处理优先级。列入清单不等于已经选定答案或批准执行。

已有材料的核查范围更新为：本地 `main@59faddd` 加当时的工作区修改、提案 v0.6、完整 run02 及 `test/1` 01／02／03 复验。提案 v0.6 的原审核基线为 `6f531c6`，当前计划 v1.2 待审核。既有检查通过与运行完成不等于研究者已验收。

已确认的主线是高层 Planner 驱动任务、保留原生 harness 的自主执行能力，Executor 认为规划无法继续时请求重规划；这不要求每步回调 Planner。固定 Executor、只优化 Planner，区分计划与已确认结果，保留历史数据及原评分，继续有效。现有 ALFWorld 环境、动作菜单、`assessment` 名称、完整外层 JSON 围栏容忍、默认 `null` 输入窗口及 PE-D-S 可自主完成等决定不逐项重开；它们对未来协议的适用性另行讨论。[权威决定记录](RESEARCH.md#decisions)

### 待人工验收的实现与证据

| 编号 | 当前事实 | 剩余验收内容 |
| --- | --- | --- |
| A1 | 当前 `two-phase-v3` 使用六配置独立提示目录，统一行动／求助分支；环境终局和预算停止后不再额外调用 Planner。03 已保存六组共 93 次真实请求。 | 审核实际角色输入、工具交接、提示文案及停止行为是否符合当时协议；这项事实审核不等于同意继续采用单步 PC。[03 设置与原文入口](experiments/planner-centered-v2/README.md#完整-json-围栏容忍后的复验) |
| A2 | Recipe 使用 Magpie native 路径与裸模型名；03 全部请求有用量，显式推理 token 为 0。此前故障与未知用量保留。 | 审核配置与实际请求是否对应，区分 API 推理设置、普通 Thought 和可训练 token；不能据此认定旧异常由网关造成。[配置](src/recipe/planner-centered/config.yaml) · [讨论](#模型内置推理与显式思考) |
| A3 | 最新 03 两种 PE-D 都只有初始规划，未触发在线求助；旧 S 范围求助不替代新 F 范围验收。 | 明确真实动态交接证据仍缺哪些内容。若以后继续使用该分支，再定有界验收；不强制求助、不自动追加运行，也不把旧分支补齐作为架构推演前提。 |
| A4 | 03 两种 PC 成功；PC-S 事件 18 覆盖围栏 JSON 的真实接受，PC-F 本轮无围栏输出。弃用目标分支未触发，相关边界仍主要由离线检查覆盖。 | 审核围栏原文、实际应用与后续执行，区分格式接受、阶段语义与独立验证。`revision_reason`、`verified`／转段及弃用目标的职责仍需结合 D10–D13 讨论。[原文与检查边界](experiments/planner-centered-v2/README.md#完整-json-围栏容忍后的复验) |
| A5 | 已决定独立新实验，旧成绩归档保留。 | 已回应，不再要求审核旧轨迹作为新实验前置。[新实验](experiments/planner-centered-v2/README.md) |
| A6 | ALFWorld 0.4.2 与主 requirements 环境已核查，依赖冲突及 TextWorld wheel 标签问题已有修复记录。 | 原问题已处理，不作为待重新决定事项。其他后端的来源与依赖只在实际纳入时核查。[环境证据](experiments/planner-centered-v2/README.md#环境与依赖) |
| A7 | 提案 v0.6 仍是当前已实现六配置和未经训练测试的正文，待审核；研究者随后澄清的目标不能由其旧单步图直接表达。 | 区分“准确记录旧实现”与“作为下一阶段研究提案获准”。先确认哪些部分保留、哪些待协议讨论后改写，不能直接将 v0.6 整体通过视为新架构获准。[提案](PROPOSAL.md) |
| A8 | 完整 run02 为 804 格、465 条有分、339 条缺评，全部尝试成本保留；03 六组成功，查看页原文已有检查记录。 | 审核原生 `null`、系统确认完成率、终止原因、恢复成本与证据限制；单任务成功、仅有分成功率均不代替架构或学习收益。[完整结果](experiments/planner-centered-v2/README.md#完整测试结果与最终异常审查) · [03 查看页与记录](experiments/planner-centered-v2/README.md#完整-json-围栏容忍后的复验) |
| A9 | 已核对《Planner Matters!》v1 的正文、提示词及官方 Web 控制循环；其 Actor 为逐步执行，不是自主多步阶段 Verifier。完整 RL 代码暂未核实。 | 审核这一来源修正是否准确，区分原始设想、近邻机制与未核实主张；原分享对话中的其他论文概括不能自动成为已确认依据。[核查范围与固定代码](#pc-的职责与执行式验证) |
| A10 | `NEXT_PHASE_PLAN.md` v1.2 保留 M0–M4、H01，以及前稿的配置、样本规模、阈值和训练基线建议。 | 审核讨论范围、安排与依赖，标明保留／待修订／待证据事项。`PC-S-stage`、`K=4`、SFT 起点及三配置矩阵均未冻结，不能直接照表启动。[计划](NEXT_PHASE_PLAN.md) |

### 尚未确定的设计选择

以下 D8–D16 汇总本轮需要确认的讨论范围。这里只登记问题，不预先设计协议或选择答案；其中接口、采样和统计的具体细节将在相应设计中再定。

| 编号 | 需要讨论清楚的问题 | 当前边界与对应材料 |
| --- | --- | --- |
| D8 | 高层策略的具体学习对象是什么：规划内容、规划形成过程、持续路线维护，还是其中若干可区分决策？整条 Planner 轨迹与单次调用各是什么单位？ | 高层学习方向已确认，不以既有 initial／monitor 两种问答反向限定研究对象。[学习对象](#两种规划架构下的-planner-优化) |
| D9 | 六配置中哪些具有独立职责差异，哪些只是覆盖范围、调用频率和工具组织的组合？PC／PE 标签及 F/S 是否仍适合表达目标架构？ | 不预先决定保留、合并或淘汰；已有实现与历史结果按原定义保留。[控制与验证](#pc-的职责与执行式验证) |
| D10 | Executor 的自主执行、局部规划、取证与条件判断如何区分？Planner 判断、执行器自报、独立 verifier 与环境终局分别能支持什么结论？ | 不将一个动作或一份 `verified` 标签当作整份计划被验证，也不预设需要另加验证模型。[职责边界](#planner-centered-的研究主线与协议边界) |
| D11 | 协议推演需要覆盖哪些交互问题：委派内容、局部自由度、无法继续的请求、返回证据、暂停／恢复和预算边界？ | 先确认问题范围，具体字段、流程与返回时机留待新架构推演，不固定 K 或要求每步回调。[协同与交互](#planner-centered-的研究主线与协议边界) |
| D12 | Planner 与 Executor 分别需要保留哪些决策和执行历史？“明确上下文”如何兼顾信息充分、职责边界与会话连续性？ | 当前 Planner 不完整回送自身历史已核实；完整对话、状态重建与摘要尚未选定，默认 null 窗口不解决记忆语义。[上下文与多轮](#多轮策略上下文重建与初始动态规划) |
| D13 | 如何把整任务反馈用于跨轮学习，同时区分初始选择、后续修订、格式适配和执行随机性？各步样本、episode、分组、奖励／优势与 token mask 如何对应？ | 当前没有训练适配；不同指令不自动意味着多个 RL 目标，统一终局信号也不代表信用分配已解决。不先选 RL 算法。[多轮策略](#多轮策略上下文重建与初始动态规划) · R2–R5 |
| D14 | 原生 harness 接入的研究要求具体到什么程度？ALFWorld 的机制诊断、真实任务域训练、接口验证及同域迁移分别承担什么作用？Planner 的可训练容量与实际资源如何衔接？ | 保留完整原生执行能力是方向要求；具体后端、模型、训练域和预算未定，接口接通与所学策略迁移分开。[部署与替代路线](#独立规划优化的必要性与部署边界) · R7–R8 |
| D15 | 希望支持什么贡献与适用范围，需要怎样的简单强基线、成本匹配、主要指标与泛化证据？已暴露测试、开发／训练／验证／冻结评测及同状态候选如何隔离？ | 不把解耦或一次分数提高当新贡献；既有测试身份与结果不回改，具体划分和比较协议未冻结。[计划 §5、§7、§10–11](NEXT_PHASE_PLAN.md) · R1–R7 |
| D16 | 下一阶段计划哪些判断保留，哪些需在架构推演后重写？M0–M4／H01 的依赖、规模与停止条件应如何重新界定？ | 当前先确认清单，不自动采用三配置、K=4 或 SFT 建议，不启动新适配器、采样或训练。[计划](NEXT_PHASE_PLAN.md) · A10 |

此前 D1–D7 的状态如下，避免把已决定的设置重新包装成待选项，也避免遗漏尚未解决的细节：

| 编号 | 当前决定与剩余问题 | 边界 |
| --- | --- | --- |
| D1 | `assessment` 的含义和当前 JSON 已定；是否改用标签、哪些普通文本进入训练仍未定。 | 标签与 Schema 等细节在 D11／D13 的相关设计后处理；当前保留 `Thought:`／`Action:`，不擅自改为 `<think>`。[格式讨论](#实机轨迹审阅上下文与输出格式) |
| D2 | 研究者接受单个 JSON 对象的外层 Markdown 代码围栏，不要求仅因包装终止任务。P10 的重复块、块顺序、未知键和截断等其余扩展解析策略仍延后。 | 提交 `937ff44` 仅规范化完整外层围栏，再执行既有字段与阶段校验。原始回复保留，未来是否设置独立 format reward 仍待训练设计。历史协议缺评不回改。 |
| D3 | Toolkit 输入 token 窗口已实现，默认容量 `null`，超限淘汰最早完整交互，无自动摘要。 | 单次正文嵌入历史，保留当前原生工具交接；完整日志与窗口选择分开。默认计数为保守估计，实际用量单独记录，不累计重复历史 token。[实现](src/toolkit/models/context.py) |
| D4 | 独立阶段语义 verifier 尚未引入；当前 `verified` 是 Planner 基于可见证据的判断。 | 当前事实已明确，未来职责归 D10；环境终局与 Terminal 原生验收不能与阶段自评混同。 |
| D5 | 已核查并配置 Magpie native 透传。两轮有用量的真实响应均显式报告推理 token 为 0。 | 原因假设与事实分开；单次结果不能证明旧异常由网关造成。未来训练文本与 loss 的选择不属于当前测试前置。 |
| D6 | `hypotheses`／`remaining_work` 暂留，空剩余工作不触发结束。 | 独立用途及修订语义未定，归 D11／D12；不因字段已存在就要求新架构沿用。 |
| D7 | 已获授权的完整 134 游戏六配置 test 评测及配额恢复已经结束，原设置、全部尝试与评分保留。 | 这是已完成的运行授权，不是当前待启动事项，不扩展到新模型、重采或训练。[最终结果与边界](experiments/planner-centered-v2/README.md#完整测试结果与最终异常审查) |

### 需要证据回答的研究问题

以下问题需要经验或资源证据回答。本轮只核对是否完整保留及其与 D 表的关系，不在盘点时宣布假设成立，也不把全部问题先得到肯定答案设为原型或训练前提。当前没有本项目训练结果，不能由接口或单任务成功推断学习收益。

| 编号 | 尚无结论的问题 | 当前证据与下一项可审核内容 |
| --- | --- | --- |
| R1 | 候选是否缺少任务相关的高层战略差异，独立采样漏掉可行路线有多普遍，什么探索机制和强基线值得比较。 | 已有一个固定 Executor 能执行替代路线的案例，不外推发生率。[采样诊断](experiments/strategy-sampling/README.md) · [规划多样性](#规划多样性与执行评价) |
| R2 | 如何区分战略变化、等义写法适配和固定 Executor 的随机性。 | 策略×写法交叉对照尚未做；可审核怎样保持信息与策略不变、每份计划重复执行多少次。[策略与表述](#策略与表述如何区分) |
| R3 | 组内相对优势学到的是战略选择、表达适配还是执行波动；去重是否会丢失有价值的决策差异。 | 已区分组内相对评价与绝对期望表现，但无本项目训练结论。[组内相对优势](#组内相对优势包含哪些差异) |
| R4 | 哪些低成本证据足以支持前提判断、局部动作或整体策略价值；未知时如何补证据或暂不排序，部分执行改变状态后如何校准。 | 评价机制、校准和补证据规则仍需设计，不把单个片段成功当整条策略可靠。[提案 §3.2](PROPOSAL.md) · [评价讨论](#规划多样性与执行评价) |
| R5 | 优化交付计划、规划形成过程还是 PC 高层决策序列；训练数据、更新方法、奖励和信用分配如何选择。 | 尚未选定具体机制或算法，不提前锁定 GRPO 等；贡献需落在 Planner 学习而非架构拆分。[提案 §3.3](PROPOSAL.md) · [研究边界](RESEARCH.md#unknown-context) |
| R6 | 已实例化、按状态筛选的动作菜单，只降低接口噪声，还是改变计划间的效用与排序；能否迁移到自行填参的接口。 | 当前保留 action prompt 已决定，本项只限定研究解释和潜在对照，不重开接口修改。[动作辅助边界](#参数实例化状态筛选与-planner-评价) |
| R7 | 单任务以外的适用范围、学习收益、跨任务／模型泛化与成本收益。 | 现有接口验收和少量诊断不足以回答，需在机制和正式协议确定后评价。[最大未知](RESEARCH.md#最大未知) · [实验记录](experiments/README.md) |
| R8 | 可用算力、训练周期与投稿条件。 | L40／48GB 只是资源规划背景，实际卡数、可用时长、训练耗时及 ICML 2027 正式截止日期尚未核实。[资源与投稿约束](RESEARCH.md#submission-constraints) |

旧 Q1–Q4、P1–P14 保留为当时方案形成过程，现有实现与记录的问题按 A／D／R 表回查。已完成设置、撤回的短窗口／强制工具封装不重新成为必选设计；A5／A6 不列为待重新决定项。真实求助与弃用目标等未覆盖分支保留为证据缺口，是否补验取决于后续是否继续使用相关协议。先确认本清单，再逐项讨论与审核；本轮不推演新架构。

## 规划多样性与执行评价

### 规划如何影响执行

同一任务的规划多样性，指候选在信息获取顺序、子目标依赖、资源使用或失败后的备选等高层决定上有差异。先依据计划内容判断差异，再用执行轨迹检验固定 Executor 是否会因此采用不同的行动。同一规划可能产生不同轨迹；不同规划也可能在执行中汇合。重复执行可以帮助区分规划引起的变化与 Executor 的执行波动，不要求每次 rollout 都换规划。

[首轮采样诊断](experiments/strategy-sampling/README.md#结果)的任务 2 提供了一个例子。固定初态和 Executor 后，优先查茶几和优先查电视柜的计划分别三次在对应位置找到遥控器，均四步成功。不同的高层决定可以改变执行行为，即使成功与步数相同。这个个案尚不能说明这种影响有多普遍。

### 策略与表述如何区分

如果同题候选只有一种高层策略，比较结果无法提供策略之间的学习信号。采到不同策略后，策略与表述仍可能同时变化。工作假设是：如果更新长期依赖这种混在一起的信号，Planner 可能主要学会以当前 Executor 容易遵循的方式写计划。清晰表达对固定系统有实际价值，但它和高层决策改善需要分开评价。

候选对照：让两种高层策略各用两种等义写法。改写时保持任务信息、约束、关键顺序和备选条件。每份计划在同一初态和固定 Executor 下重复执行，先看关键分叉是否按计划变化，再比较成功与成本。同一写法下换策略，可以观察决策的影响；同一策略下换写法，可以观察 Executor 对表述的敏感性。首轮实验没有做这个交叉对照。

若后续进入训练，可以在未见任务上检验：等义改写后，训练收益是否仍能保持。收益跨写法保持，能为高层决策有所改善提供额外证据；只在原写法下观察到收益，则仍需区分表达适配和策略改善。

### 组内相对优势包含哪些差异

讨论范围扩展为使用同题候选的组内相对表现估计优势的策略优化方法。具体基线和归一化方式需分别核对。例如，[DeepSeekMath §4.1.2](https://arxiv.org/html/2402.03300v3#S4.SS1.SSS2) 中的 GRPO 对组内回报中心化并按标准差缩放；[RLOO §2.2–2.3](https://arxiv.org/html/2402.14740v1#S2.SS3) 用其余候选的平均回报作为基线。这里只核查这些优势估计的定义，不据此概括各算法的全部行为。

执行回报来自具体规划文本与固定 Executor 的交互，混合了高层策略、表达适配和执行波动的影响。组内相对优势再以同组候选为参照，因此还随比较对象变化。它本身不提供规划绝对期望表现的独立估计，也不能区分策略选择和表述分别贡献了多少。若组内高层决策雷同，回报差异仍可能由 Executor 对写法的理解或执行波动产生，并进入 Planner 的更新。这是待检验的学习机制假设。

相对优势用于构造更新信号，仍可以服务于提高整体期望回报。例如，满足独立采样等条件的 RLOO 用组内基线降低梯度估计方差，并不因此将目标改为只胜过本组其他候选。具体的归一化、裁剪和筛选还可能改变训练权重，需按选用的方法分析。

在当前只按环境终局判断任务成功的设置中，写法主要通过改变 Executor 对计划的理解与执行行为影响奖励。高层策略与表述可以经由同一执行过程起作用，不能将表述影响当作执行路径之外的一项独立奖励。若以后加入文本评价器或格式奖励，则需另行区分其直接作用。

因此，多样性采样要为组内比较提供任务相关的决策差异；多样性本身不保证优势主要反映这些差异。前述策略与写法的交叉对照用于判断，组内信号是否支持高层策略之间的比较，以及表达适配在其中占多大作用。

### 是否提前去重

执行前识别决策重复的计划，可以作为节省评估预算的候选做法。同一粗粒度路线标签还不足以判定两份计划等价，筛掉重复也不会自动产生新策略。是否值得筛选，需看节省的成本和丢失的决策差异。

规划多样性早于学习更新。不同策略可能同分，同一策略也可能因执行波动而得分不同。是否存在相对更新信号，不能单独用来判断是否采到了不同策略。这些讨论尚未选定去重机制或更新算法。

## 独立规划优化的必要性与部署边界

[原始 ChatGPT 讨论](https://chatgpt.com/share/6b06c5af-2b28-83e8-a11e-11e44a183b50)开头提出六项疑问：优化独立 Planner、基模还是 harness；为何解耦；训练与测试框架的关系；真实后端如何接入；小模型的知识和成本；单 benchmark 的任务特化能支持什么贡献。这些问题已纳入[下一阶段计划](NEXT_PHASE_PLAN.md)，具体协议与安排仍待审核，不改变提案审核或实验授权；研究者进一步明确的主线见[架构与协议边界](#planner-centered-的研究主线与协议边界)。

工作判断是：独立 Planner 的价值须由“高层干预改变行动与结果—反馈进入参数更新—未见任务收益”分别支持，不能从架构存在或任务很长推导。原对话曾提出训练前先证明干预收益，后续又明确允许接口稳定后做有界学习试验；计划采用后者，不增设零样本 PC 胜出的前提。现有采样案例只支持存在可操纵的路线差异，尚不证明战略覆盖不足是主要瓶颈。

| 主题 | 当前工作定义或候选比较 | 尚未解决的问题 |
| --- | --- | --- |
| 解耦 | 角色、上下文、参数、训练和控制权分别定义。主线冻结独立的 Executor 参数实例；它仍可在子任务内规划。 | 交接收益能否超过信息丢失、错误限制及额外调用的代价？共享参数时只屏蔽执行 token 的 loss，不能保持执行策略严格不变。 |
| 训练与运行 | 候选搜索、筛选或奖励估计可只用于训练；观察来源、交付语义、调用和返回规则属于运行依赖。 | 移植后保留了哪些语义？接口可调用、指导被采用和所学策略迁移，需分别验证。 |
| 替代路线 | 组件训练与直接训练单体智能体均是研究选项。先保留原生执行、简单规则或执行模型自行规划的强对照。 | 现有工具便于组件训练不证明它更优；直接更新执行模型超出当前固定 Executor 边界，未获实施授权。 |
| 模型容量 | 不以小 Planner 必须成立为前提。区分参数知识、环境事实、历史和证据整合，按全部执行成本评价效率。 | 小模型是否能使用证据、避免错误限制强执行器？更强参考指导没有增益也不是不可学习的证明。 |
| 贡献范围 | 严格未见任务下的任务特化可有价值；换任务族、Executor、harness 和必要决策跨度回答不同问题。 | 本项目尚无训练收益或迁移证据，不能仅凭模拟环境提高分数宣称通用规划能力。 |

计划继续保留阶段级 PC 候选与提前穿插的 H01，均不是已选定方法。H01 检验外置高层控制与完整原生执行系统，不作为 ALFWorld 学习试验的硬依赖。M2 还须区分固定初始指导的执行重复与后续 Planner 在线采样；后者的波动不能全部归因于 Executor。原对话中的具体论文结论和产品接口未在本次独立复核，不转写为已确认文献证据。下一项是审核计划的研究对象、比较与预算边界，不启动代码改造或训练。

## 两种规划架构下的 Planner 优化

四种框架及规划覆盖范围的工作定义见[提案 v0.5](PROPOSAL.md)。讨论的重点是 Planner 在任务中重新获得决策权后，三项研究问题对应的观察对象如何变化。

| 研究问题 | Planner-Centered 中的研究对象 |
| --- | --- |
| 战略探索 | 比较先取什么证据、如何委派，以及不同反馈下如何改变路线。 |
| 低成本评价 | 分开判断证据是否支持一个前提、行动是否推进任务，以及整条策略的终局价值。取证可能改变状态或消耗预算。可用从同一初态独立运行的完整轨迹校准局部证据，并计入取证成本。 |
| 策略更新 | 记录 Planner 每次决策时实际可见的信息、选择与后续结果。在线反馈可以触发修订，用什么信号更新 Planner 参数及更新是否有效需要另证。 |

2026-11-18 的 Planner-Centered 测试工作稿用未经专项训练的 EO（无外部 Planner）、PE-S（一次性外部规划）与 Planner-Centered 比较系统的成功率和端到端成本。该比较同时涉及在线反馈、计算投入和阶段委派。若进一步检验学习收益，在各自架构内固定执行和运行协议，对照更新前后 Planner 在未见任务上的表现。跨架构比较使用同一任务与冻结 Executor，计入额外模型调用和环境交互。主要未知是哪些新证据会改变高层路线，以及这种改变能否在可比预算下改善结果。

### 多轮策略、上下文重建与初始／动态规划

研究者提出：当前上下文将完整 rollout 拆成初始计划生成和动态重规划等单轮问答，是否因此拆散优化对象、要求 RL 同时优化多个目标？当前判断是：**请求形式、策略记忆和信用分配是不同维度。重建单轮输入不排除多轮策略优化，但当前固定的记忆筛选确实限制了可学习策略；其效果尚未验证。**

本次静态核对发现，`runtime.py` 的 [`_history_units()`](src/toolkit/frameworks/runtime.py)纳入初始观察、Executor 回复及工具／环境反馈，不纳入 Planner 历次原始回复；`_planner_context()`另加入当前计划、活动阶段、最近修订理由、已验证阶段、假设与剩余工作。它保留部分规划状态，但不保留完整的 Planner 决策、assessment、弃用路线及其理由历史。`_history_context()`将这些内容重新序列化为单个 user 消息；初始／后续调用使用不同指令和字段要求。完整事件日志包含各次真实输入、回复及关联决策，但不等于这些信息都对下一次 Planner 可见。[运行器](src/toolkit/frameworks/runtime.py) · [调用记录](src/toolkit/rollout/session.py)

令 `h_t` 为截至决策前的完整历史，`c_t = F(h_t)` 为当前运行器实际提供的上下文，`m_t` 表示初始或后续决策模式。可把 Planner 写作 `z_t ~ πθ(· | c_t, m_t)`，以完整任务回报 `J(θ) = E[R(τ)]` 为共同目标。初始决定下一步、后续根据新证据维持或修订，是不同状态下的决策职责，不自动产生多个优化目标。只有另设独立的初始计划评分、局部进展奖励或分阶段 loss 等，才需分析这些局部目标与终局目标是否一致。共享参数的不同状态分布仍可能产生优化干扰，初始调用少而监测调用多也会影响训练权重；这些是需测量的问题，不能从 prompt 不同直接推断。

按调用分别计算 loss 也不必然切断时序信用：可以保留每步真实条件输入与生成输出，以完整 episode 组织采样、回报／优势和分组，再将各步的策略梯度项聚合。反之，若去掉 episode 关联，以互不相干的局部标签训练，则不等价于原先的完整策略优化。完整任务共享终局信号是粗粒度基线，仍不能识别哪次初始决定或修订值得奖励。同题初态的完整轨迹可以做 episode 组；不同中间状态不能仅因都叫“重规划”而当成同状态局部候选。

存在直接近邻：[GiGPO v1 Appendix A](https://arxiv.org/html/2505.10978v1#A1)明确采用逐步构造输入、不拼接全部历史的多轮交互；[verl-agent 官方说明的 Key Features](https://github.com/langfengQ/verl-agent#key-features)允许自定义每步输入与记忆，同时在完整 episode 上组织 GRPO 等训练。此次阅读范围为该论文相关定义、§4 与附录 A，以及仓库 README，不是复现或逐行代码审核。这支持“此类组织方式可以做多轮 RL”，不证明本项目的字段筛选、参数共享或学习效果已经成立。

当前设计的实质风险是**历史混叠**：两个不同的过去经 `F` 得到相同输入，但正确下一步依赖被丢掉的决定、排除理由或承诺。若必要信息无法从公开执行历史和保留状态中恢复，模型无法仅凭相同输入作出依赖该信息的不同选择。完整对话历史可保留更多决策记忆，但也可能增加上下文成本与错误历史影响；当前状态重建可更明确控制输入，却把记忆保留规则固定在运行器中。二者是候选设计，尚未选定优劣。

另有训练接入风险：当前重建输入不保证前缀追加，不能把各次回复拼成一条新对话后，默认其概率就是原采样概率。[verl Agent Loop 的 token 一致性说明](https://verl.readthedocs.io/en/latest/advance/agent_loop.html#chat-completion-vs-token-in-token-out)明确区分服务端文本记录与训练 token 轨迹。本项目目前未实现 RL 训练适配；接入时须核对每次实际 prompt／response token、策略版本、生成概率和训练 mask，Executor 与环境输出不进入 Planner 的动作 loss，过去回复作为当前输入也不能重复当成本轮动作计 loss。回复 EOS 不等于任务终止。

下一项讨论应先固定“完整 Planner 决策轨迹为优化单位，局部调用为决策单位”是否符合研究目标，再选择保留哪些决策记忆及如何表示初始／后续决策。可比较当前状态重建与加入 Planner 决策历史的版本；统一决策接口是另一独立维度，不与记忆变化捆绑。尚无本项目证据证明两阶段参数更新存在冲突、上下文重建已经造成失败，或需要新 RL 算法。本轮仅维护讨论与未决状态，不修改运行协议或启动训练。

## 模型内置推理与显式思考

本轮核查区分三个对象，不能只凭名称中有 thinking 就视为同一机制：

| 对象 | 操作性定义 | 如何判断 |
| --- | --- | --- |
| API 内置推理 | 接口通过请求字段控制服务端的推理模式或强度。 | 按接口及模型文档设置参数，并核对返回字段和用量。 |
| 显式思考文本 | 模型在回复序列中生成的推理文字，例如 `<think>…</think>`。 | 核对 prompt、实际生成 token、动作解析与训练 mask。 |
| 框架状态判断 | 当前 JSON 的 `assessment`，陈述可见状态、阶段判断及依据，帮助理解计划维持或修订。 | 它是普通生成文本，不是隐藏思考的总结，不独立裁定成功或验证阶段。 |

2026-11-21 用 Chrome DevTools 核对的[同济接口文档](https://agi.tongji.edu.cn/docs/reasoning)以 `reasoning_effort` 统一控制开关和强度，`none` 表示关闭。省略参数会采用模型默认值，不支持的等级可能被重定向；支持范围仍取决于模型。该文档的示例把推理放在 `message.reasoning`，与 `content` 分开。[DeepSeek 原生 Chat Completions 文档](https://api-docs.deepseek.com/guides/thinking_mode/)则支持 `thinking.type` 开关和 `reasoning_effort` 强度，其推理字段是 `reasoning_content`。因此，接口兼容不代表扩展字段及返回字段完全一致；同一模型经不同网关调用，应以实际入口的接口约定为准。

当前配置将两个角色的字段统一为 `thinking`，并均提供可选 `reasoning_effort`。`null` 表示不发送，不代表关闭；Recipe 按目标接口填写，通用客户端不根据服务商名称推断或转换。Planner-Centered 的 `reasoning_effort: none` 已从 Python 常量移到两角色 YAML，历史原始请求保留。[默认值](src/toolkit/config.yaml) · [Recipe 配置](src/recipe/planner-centered/config.yaml)

RAGEN 的核查范围为[原论文 v1，§2.2.2–§2.2.3](https://arxiv.org/html/2504.20073v1#S2.SS2)与官方仓库 2025-05-08 的固定版本，而非后续 RAGEN-2。每轮生成 `<think>思考</think><answer>动作</answer>`，环境只执行动作。思考是生成轨迹的一部分，标签属于提示与输出协议；其中开头的 `<think>` 可由 prompt 预填，并非每个标签都必然由策略采样。[输出解析](https://github.com/mll-lab-nu/RAGEN/blob/b93b1a29772fe09f97981fedfdcce958ea8ddeef/ragen/llm_agent/ctx_manager.py#L143-L168) · [生成前后的标签处理](https://github.com/mll-lab-nu/RAGEN/blob/b93b1a29772fe09f97981fedfdcce958ea8ddeef/ragen/llm_agent/ctx_manager.py#L246-L341)

默认 `enable_response_mask: True` 时，原版代码对 assistant 轮的生成 token 计算策略损失，包含思考和动作，环境观察仍作上下文；关闭该选项会改变此边界。[原版配置](https://github.com/mll-lab-nu/RAGEN/blob/b93b1a29772fe09f97981fedfdcce958ea8ddeef/config/base.yaml#L11) · [mask 实现](https://github.com/mll-lab-nu/RAGEN/blob/b93b1a29772fe09f97981fedfdcce958ea8ddeef/ragen/llm_agent/ctx_manager.py#L35-L71) · [训练器接入](https://github.com/mll-lab-nu/RAGEN/blob/b93b1a29772fe09f97981fedfdcce958ea8ddeef/ragen/trainer/agent_trainer.py#L555-L556)。纳入策略损失不表示每句思考有真值标签或正确性奖励；原论文 §4.4 还报告思考退化及与环境状态不符的文本，不能把格式合规或任务成功当作思考可靠性的充分证据。

这次核查澄清了 API 开关与可训练文本的区别，未选定本项目的训练表示或更新算法。RAGEN 的联合轨迹训练也不直接证明固定 Executor、只优化 Planner 的收益。两阶段单任务实机虽请求 `reasoning_effort: none`，返回用量仍报告非零 `reasoning_tokens`；是否确实关闭推理尚未核实。开启内置推理后的完整保存与工具调用回传也尚未验收，不能把 API 另返回的推理字段自动当成本项目已有训练数据。若后续研究该机制，需先明确哪些生成 token 进入上下文、记录和损失，再确定对照与预算。[实机设置与原始用量](experiments/planner-centered/README.md#两阶段运行协议)

本轮按安装版 Magpie `0.1.4657` 核对官方实现，并改用 `http://127.0.0.1:3425/v1/magpie/native/tongji/v1`。native 路由把请求路径接到配置的上游 host，因此这里保留 `/v1`；正文模型名用上游裸名称，避免普通网关的模型重写。普通本机 Bearer `magpie` 即可，通用客户端无需专用分支。[官方连接说明](https://github.com/yetone/magpie/blob/v0.1.4657/docs/reference.md#connecting-anything-else) · [原生转发实现](https://github.com/yetone/magpie/blob/v0.1.4657/internal/gateway/native.go#L359)

源码显示该路径转发原始 body，但匹配隐私遮蔽规则时仍可能解析并改写 JSON。本轮没有更改 Magpie 全局配置，也没有调用模型；因此不能断言逐字节透传或旧推理用量异常已解决。模型适配器已保存响应中实际出现的 `reasoning`／`reasoning_content`，其是否存在和真实语义仍需目标接口验证。

## 四框架接口与评分口径

首版接口验收加入 PE-D。在 ALFWorld 的双动作边界，PE-D 和 PC 都读到了遥控器已被拿起的公开证据。PE-D 在原整项请求下更新剩余规划，PC 发出新阶段请求，将目标改为把拿起的遥控器放到沙发上。四组最终动作相同。该接口已经在原子动作之间验证了续接。更复杂的阶段返回和独立隐藏验收需要其他后端。[实际轨迹与实现](experiments/planner-centered/README.md)

原实现将整个 Planner 状态和反馈日志事件序列化进模型上下文，额外带入了运行标识、时间、计划版本和用量，也告知模型执行额度等技术限制。当前工作区改为显式构造任务上下文，保留任务、公开证据、规划和公开观察引用，具体边界见[框架接口](src/toolkit/README.md#四种运行框架)。执行额度用于防止无限运行，只由运行器执行和记录；剩余额度、返回间隔、阶段动作上限和内部返回原因不告知模型。此次修复没有重跑实验，不能据此判断这些额外字段对既有比较的影响；历史 prompt 按原样保存，后续若需核验影响，应单独定义对照与预算。

### Planner-Centered 的研究主线与协议边界

研究者于 2026-11-26 进一步明确：出发点是学习一个可在现有 harness 之上使用的高层策略，保留执行器自主权；Planner 驱动整任务，Executor 在给定的明确上下文内执行，认为规划无法继续时再请求 Planner 重规划。已明确的是这种协同分工，具体信息交换、返回和上下文规则才是需要设计的协议。不能让现有原子 Action 接口、六配置名称或预定采样矩阵反过来定义研究对象。该方向已记入[研究工作台](RESEARCH.md)，不等于批准实现或训练。

研究者所说原生 harness“更像 PC-F”，指先形成整体路线、执行中持续修订这一功能结构，不是断言其内部遵循本仓库逐步回调的 `pc-f` 协议，也没有据此选定未来必须采用 full-plan。分离高层规划职责后，仍允许 Executor 为委派工作选择工具、局部规划和纠错；Executor 发起重规划不自动意味着整任务路线由它掌握。新定义可能与已有 PE-D 有交叠，六配置的互斥性须重新检查，不为保留分类而限制原生能力。

| 已明确的协同原则 | 仍需设计的交互策略 |
| --- | --- |
| Planner 负责高层目标和路线 | 交付整体路线、当前委派及未知条件时，哪些内容约束 Executor，哪些允许局部调整？ |
| Executor 保留原生自主能力 | 为完成委派需要哪些任务信息、观察和权限？局部重试与路线改变的边界是什么？ |
| 无法继续时请求重规划 | 如何区分前提失效、信息不足、局部执行失败与资源边界？请求发出后如何交还与恢复控制？ |
| 执行反馈进入下一轮规划 | 返回哪些环境证据、局部结论和未解决条件？何种判断需要另行核验？ |
| 学习面向持续高层策略 | 如何保留 Planner 自身决策与修订历史、关联完整 episode，而不把运行语义拆成互不相关的问答？ |

“明确上下文”要求职责和信息边界清楚，不等于越短越好或默认清空历史。是否保留会话、如何移交必要证据，须与真实后端能力及策略需要一致。《Planner Matters!》曾被当作这一设想的机制来源；前轮核查表明，它的已读协议是逐动作 Actor。论文仍是相关工作，但不能替代当前架构意图的独立论证。对本项目为何走向同样单步循环的工作解释是：实现把 Planner 的高层主导权具体化成每步回调，继而让已有动作接口决定交互粒度；这是设计回顾，不是已经完成的因果实验。

前稿把 `K=4` 作为工程起点，仍只处理调用频率，不能承担恢复原始架构意图的全部工作。当前先保留更宽的协议设计空间，不固定 F/S、交接字段或触发算法；随后从待学习决策、原生后端接口与可比较的职责差异出发，形成足以指导一轮构建的协议，不要求穷尽所有选项。现有单步实现和历史实验继续按原定义保留。

### PC 的职责与执行式验证

研究者质疑：原先希望 Planner 推动整任务，Executor 自主执行以检验计划；当前 PC 却在每个真实动作后交回 Planner，由后者判断阶段完成。若恢复 Executor 自主执行，PC 是否与 PE 重合？本轮判断是：当前实现没有独立的阶段执行式验证闭环，与这一设想存在差距；但执行粒度、整任务控制权和验证职责是不同维度，尚不能据此认定所有 PC 均无独立含义。

验证须区分执行取证、条件判断和终局评价。“自主执行以验证”是为待证条件选择多步调查／测试的候选职责，不是 verifier 一词的通用必要定义；多步执行也不自动保证证据充分。如果所有局部行动选择都算作 planning，就无法同时要求 Executor 自主取证而没有任何规划能力。可操作的边界应区分高层目标／路线选择与委派边界内的工具规划。

当前 [`runtime.py`](src/toolkit/frameworks/runtime.py) 的 PC 每次 `_executor_step()` 后调用 `_plan_pc()`；[`pc_s/alfworld.py`](src/toolkit/prompts/pc_s/alfworld.py)由 Planner 判断阶段是否维持、完成或替换，Executor 交付一个动作。`verified` 是 Planner 判断，不是独立执行器验收。PE-D 则由 Executor 循环执行、原生调用 `request_plan`；[提案](PROPOSAL.md#2-共同设定与框架选择)接受 PE-D-S 在可直接完成整任务时继续行动。因此两者当前控制流有差别，但并非“完整验证器”与“完整执行器”的比较。

**《Planner Matters!》核查。** 阅读 [arXiv:2605.02168v1](https://arxiv.org/html/2605.02168v1) §3.1／§4.1、图 2、附录 A.3／A.6／A.9／A.11，并查看 PDF 第 3、21、22 页。Planner 初始生成步骤计划，后续结合旧计划、观察、动作和记忆给出更新及下一步；Actor 每次输出一个动作。附录 A.11 的更新模板为 `<plan>`／`<subgoal>`，允许建议 STOP；Actor 指令明确一次一个动作。图 2 的 DONE／STUCK／PENDING 不足以证明存在多步自主阶段 Verifier。论文另以 VLM-as-judge 评价完整轨迹，并报告冻结 Actor／记忆组件、只训练 Planner；在线 Actor 与事后评价器职责不同。

官方代码固定于提交 `0111b0022fc26969f376b16f73c78180fe68e06f`。[入口 run.py](https://github.com/WenyiWU0111/Planner-Matters-GUI-Agent/blob/0111b0022fc26969f376b16f73c78180fe68e06f/planner-matter-inference/run.py#L5)导入 `agent_new.py` 和 `test_runner_new.py`；[Actor prompt](https://github.com/WenyiWU0111/Planner-Matters-GUI-Agent/blob/0111b0022fc26969f376b16f73c78180fe68e06f/planner-matter-inference/agent/agent_new.py#L180)要求一次一个动作；[Web runner](https://github.com/WenyiWU0111/Planner-Matters-GUI-Agent/blob/0111b0022fc26969f376b16f73c78180fe68e06f/planner-matter-inference/benchmarks/webvoyager_evaluation/test_runner_new.py#L320)在开启 Planner 且相关状态存在时逐轮更新，而不等待 Actor 自主完成阶段。[更新 prompt](https://github.com/WenyiWU0111/Planner-Matters-GUI-Agent/blob/0111b0022fc26969f376b16f73c78180fe68e06f/planner-matter-inference/memory/plan_with_memory.py#L505)实际采用 `<next action>`，标签与论文不同。Actor 可以输出 STOP；Planner 的 STOP 建议进入计划文本，不是独立成功验收。

本次没有运行官方系统。该提交的 `planner-matter-RL` 是没有可解析仓库 URL 的 gitlink／子模块入口，完整训练实现暂未核实，算法细节只按论文报告。已读取的 Web 推理路径也不能代替未核对的 OSWorld／MCP 实现。

| 维度 | 本项目当前 PC | 论文及已核对的官方 Web 路径 | 原设想的执行式验证候选 |
| --- | --- | --- | --- |
| 高层目标与路线 | Planner 维持、推进或修订 | Planner 更新计划并指定下一步 | Planner 选择目标、待证条件与后续路线 |
| Executor 范围 | 一次一个环境动作 | Actor 一次一个动作 | 委派边界内自主多步取证／执行 |
| 返回 Planner | 每个非终局真实动作后 | 开启规划时逐轮更新 | 完成、受阻、证据不足或预算边界后 |
| 条件与成功判断 | Planner 判断阶段；环境／benchmark 判终局 | 未核实到独立多步阶段验收；终局 judge 另设 | 证据、结论与未覆盖条件分别返回；独立复核另定 |

六配置是整任务推进权、规划覆盖范围、委派粒度、介入触发与证据判断职责的特定组合，不是已证明互不重合的六类理论架构。多步 Executor 仍可只完成 Planner 委派的阶段；PE-D 的 Executor 可持有整任务并按需求助。若两组的目标选择、权限、返回、证据与采纳规则也相同，则可能是同一协议的两种叙述，无需为保留名称制造差别；目前尚未合并或淘汰配置。

计划前稿的 `K=4` 只改变返回频率，不自动构成自主验证，也不能解决分类是否重合。高层策略与自主 Executor 的研究主线已在[后续澄清](#planner-centered-的研究主线与协议边界)中明确，具体可学习决策和有独立意义的对照仍需设计。原子动作反馈是证据来源，不能直接等同于完整规划价值评估；一次执行成功也不证明整条路线的稳定价值。本轮只维护讨论与未决状态，不改提案、代码或历史结果。

### 规划覆盖范围与控制权

实施前的四配置协议要求 Planner 生成覆盖全部剩余工作的计划，解析器检查非空 `<plan>`。旧 PC 向 Executor 下发阶段目标与 `soft_guidance`，整体计划保留在 Planner 状态中。下文按原问题编号保留针对该版本的分析。[实施前协议快照](experiments/planner-centered/protocol-review.html#issues)

这里的 sub-plan 覆盖一个可跨多次环境交互的高层阶段。当前两阶段协议由 Executor 推进 EO 和 PE，PC 固定单步执行后由 Planner 监测；只有 PE-D 的在线求助使用模型工具。动态 PE 和 PC 都可以采用 full 或 sub 范围。Planner 先判断再交付，Executor 按生效的 sub-plan 更新当前指导，完整交互历史跨阶段保留，并采用 P6 的预算与终止规则。`remaining_work` 暂留，P10 扩展解析细则延后。下列 Q/P 保留形成 v1 时的讨论，其中短窗口与历史摘录方案已由 v2 的完整历史替代。[实施方案](experiments/planner-centered/protocol-design.md) · [运行验收状态](experiments/planner-centered/README.md#两阶段运行协议)

#### 四个运行问题

**Q1　谁发起重规划？** 当前运行器按累计 Executor 调用数检查 `return_every`，格式错误也计数。ALFWorld 和 WebShop 的常用设置为两次，ScienceWorld 和 Terminal-Bench 正式配置为四次。EO 和 PE-S 在边界只写反馈，Executor 接着执行。PE-D 与 PC 在边界强制调用 Planner，可能改指令，也可能因 Planner 额度已满而提前停止。两步足以复现基线，却无法表达「第一步已推翻前提」或「第三步才能观察到结果」。[控制循环](src/toolkit/frameworks/control.py) · [采样配置](src/recipe/planner-centered/benchmark.py)

| 拟议配置 | 谁决定重新规划、何时决定 | Executor 接下来做什么 |
| --- | --- | --- |
| EO | 无 Planner。 | 自主承担整项任务。 |
| PE-S | 首步前交付一次整体计划，之后无需规划检查。 | 持续执行。 |
| PE-D-F | Executor 发现原路线所依赖的前提改变，调用配置为 full 的规划工具。 | 读取针对剩余整任务的更新建议，继续持有整任务。 |
| PE-D-S | Executor 判断当前子目标已达成、受阻或需要替换，调用同一规划工具的 sub 配置。 | 得到一份可执行的子计划，决定何时发起下一次调用。 |
| PC-F | Planner 形成带编号的完整计划，指定当前子计划。每步反馈后决定继续、推进编号或修订路线。 | 接到 Planner 的单步执行调用，选择并派发一个环境动作。 |
| PC-S | Planner 先给当前阶段子计划，每步反馈后判断是否满足该阶段条件以及下一目标。 | 执行同一个单步工具。环境返回动作结果，Executor 无须另外撰写报告。 |

PE-D 中，Executor 通过原生 `request_plan` 调用触发重规划。工具文档说明适用时机、理由参数和返回内容。Executor 提供本次求助的原因，Harness 从已有状态补齐任务、约束、当前计划和有关观察，因而完整的 Planner 请求无须由 Executor 重写。原生调用可能减少格式学习负担，时机判断和证据选择仍需由模型承担，其效果尚待测量。PC 每个真实动作得到环境反馈后都由 Planner 查看，监控可以维持当前阶段；“看过结果”和“实际修改计划”应分别计数。

**Q2　初次规划和重规划应共用什么？** 现行动态指令反复要求剩余整体计划。下一版的 PE-D-F 复核求助理由并决定是否修订剩余路线，PE-D-S 根据触发原因给下一子计划。PC-S 和 PC-F 共用两个明确的阶段。**Initial Sub-Plan Generation** 首次确定当前阶段，PC-S 生成首个子计划，PC-F 生成带编号的完整计划并指定第一个生效的子计划。**Continuous Execution Monitoring** 在每次实际动作得到环境反馈后由 Planner 判断维持、转段或修订。两阶段都先判断再交付，公开输出先给能回查的简短判断依据，计划只写待做工作。旧轨迹中“确认马克杯已放入柜子”属于核对事项，观察即使证实放入，也不足以证明它满足 `cup` 类别。[当前 PC 模板组织](src/toolkit/README.md#四种运行框架) · [旧任务 58](experiments/planner-centered/finish-advice.md)

**Q3　下一次决策真正要读什么？** 当前动态 Planner 每次收到初始观察、全部累计公开观察和最近一段动作与观察。初始观察在模板和累计事实中重复，最近一段也在两个字段中重复；上一轮实际委派的 `stage_objective` 却未显式送回 Planner。Executor 每步重发完整 `state.history`，包含旧指令、旧动作菜单和整段模型回答。WebShop 当前两处入口都指定 `observation_mode="text"`，模型看到的是商品页面文本，长列表和菜单仍会反复发送。若每步增加约 *b* 个 token，*T* 步下来仅 Executor 历史输入就约为 *bT(T+1)/2*。现有请求字节上限只能拒绝超长输入。这是增长关系，尚无新协议的实测 token 节省值。[Planner 输入](src/toolkit/frameworks/control.py) · [Executor 输入](src/toolkit/rollout/session.py) · [WebShop 配置](src/recipe/planner-centered/webshop_benchmark.py) · [请求字节检查](src/recipe/planner-centered/run.py)

建议完整事件与原文留作可回放轨迹，模型输入按角色生成有界视图：

| 使用者 | 每轮可见 | 谁维护 |
| --- | --- | --- |
| Planner | 原目标与硬约束、实际交付中的计划或阶段、与判断相关且可追溯的事实、未证实的假设、暂留的剩余工作，以及本次触发原因和新增证据。 | 运行器保留交付原文与公开事件；Planner 维护假设、剩余工作及要保留的证据。引用指向有实质信息的观察，可按需回查。 |
| Executor | 角色与硬约束、当前有效委派或建议、当前观察与原生动作菜单、最近少量动作及其结果；跨窗口仍有用的事实可带公开摘录和出处。 | 运行器按同一窗口和输入上限构造；旧菜单与旧委派不再作为有效指令，环境状态持续。 |

PC-S 的监控输入保留全部已验证子计划及其依据、当前子计划、最新动作与环境反馈，以及已有的阶段退回原因。PC-F 保留生效的完整计划、当前子计划编号和发生修订时的原因。正常单步返回时尚未作出阶段判断，界面可以写“本步得到环境反馈”；是否结束阶段与转向理由由 Planner 据此判断后写入状态。范围修订时保持已验证结果可追溯，避免旧编号误指新目标。

本地核对了模型调用入口。verl-agent 的默认训练 rollout 逐步从本轮观察构造单条 user 消息，经 chat template 编码后交给生成 worker。verl-agent-system 的外部 Executor 在每步把本轮格式化观察与当前 metaplan 组成一条 user 消息，调用 Chat Completions。WebShop 的环境模板可在单条消息内带最近 K 次交互，默认 K=2，带历史的提示超过 13,000 个字符时当轮去掉历史。本仓库的 Executor 则直接把累计 `state.history` 作为请求的 `messages`。命中前缀缓存仍占上下文长度，是否命中及实际成本须按模型返回的 usage 核对。窗口长度与重规划时机可以独立选择。[verl-agent rollout](https://github.com/langfengQ/verl-agent/blob/796ed310287fa605c9292a0fce07a86d79fde05e/agent_system/multi_turn_rollout/rollout_loop.py) · [上游 WebShop 窗口](https://github.com/langfengQ/verl-agent/blob/796ed310287fa605c9292a0fce07a86d79fde05e/agent_system/environments/env_manager.py#L464-L505) · [本仓库 Executor 请求](src/toolkit/rollout/session.py)

**Q4　谁解析 `<decision>`？** 现行 PE-D/PC 在运行器中解析 JSON，PE-D 下发计划正文，PC 重建阶段请求但仍将其序列化进 Executor 的消息。PE-S 在缺少 `<plan>` 时可把整段非空回复当作计划。新工具协议要求 Harness 解析决定、参数与结果，分别给目标角色渲染任务文字、具体动作和公开反馈。原生 API 的工具定义、参数与调用配对仍属于传输协议，跨角色内容不嵌入整段请求 JSON。更细的格式兼容问题按 P10 暂缓。[解析与下发](src/toolkit/frameworks/control.py) · [PE-S 回退](src/toolkit/prompts/plans.py)

#### 审查页 P1–P14 的回应

**P1　当前阶段和完整计划各由谁维护？** PC-S 的当前阶段目标本身就是 sub-plan，无需额外的一份 full-plan。PC-F 允许 Planner 维护一份带编号的 full-plan 和当前子计划编号，推进到已有的下一阶段可只更新编号。两者都让 Planner 在下一轮监控时看到上轮真实交付，并只调用 Executor 做当前的一步。旧实现同时要求互相独立的完整计划和阶段文本，导致两者可能分歧。见 Q2、P7、P8。

**P2　执行记忆采用短窗口与可追溯事实。** 研究者认可这一方向。当前任务、有效阶段、最新页面与原生动作菜单持续可见，最近少量动作及结果支撑局部操作；更早的价格、对象或约束可以作为带出处的事实保留。对四架构使用同一窗口和证据规则，Executor 无须额外产出记忆报告。窗口取值与事实选取的代价应结合输入 token、遗漏旧属性和任务结果核验。见 Q3、P12、P13。

**P3　阶段完成、取证结束和安全返回如何落地？** 建议分别记录此次取得的公开证据、该证据是否满足阶段目标、运行器有无因资源或故障中断。查到商品价格高于限价时，核价取证可结束；若阶段是寻找合格商品，阶段仍未完成。PC 每次单步执行的环境反馈都可以交付这个价格，由 Planner 决定阶段去留，得到结果本身不改变阶段编号。预算或安全边界只改变执行状态，保留最后一次观察和待验阶段。见 Q1、P4、P6。

**P4　规划求助与单步执行怎样返回？** 动态 PE 由 Executor 在需要规划的时刻调用规划工具，参数带原因及必要公开证据。工具返回可读的完整剩余计划或下一子计划；这次求助不执行环境动作。PC 采用固定调用顺序，每个非终局轮由运行器直接调用 Executor 执行一个环境动作，并把实际动作与环境反馈送回 Planner，不需要模型发起 function calling。此前用“工具”统一描述两类角色调用，研究者已明确 PC 不需要这层封装。两类调用都不需要另设阶段返回动作，也不会把阶段返回误发为整任务 `finish`。见 P3、P6。

**P5　Planner 有没有足够证据宣告任务结束？** 核查了四套正式旧运行实际保存的 965 条 PC 轨迹。环境结束前被接受的三次 `finish` 全部来自 ALFWorld，三条原生奖励都为 0。Planner 分别把 `handtowel` 当作 `cloth`、`mug` 当作 `cup`、`butterknife` 当作 `knife`。日志能证明操作了相应物品，无法证明该物品满足目标类别。反过来，在被提示环境已经结束之后，ALFWorld 的 118 条有效收尾都得到 1 分；这取决于调用时点和样本，无法据此估计主动识别终局的能力。WebShop 也有收尾称全部满足、原生分数只有 0.4 的轨迹。P6 确定有原生终止信号时由环境判终，模型意见可保留供分析。三条主动叫停无法估计模型的一般误停率。[结束建议原文、同轮证据、事件编号与评分](experiments/planner-centered/finish-advice.md)

**P6　终止与预算已确认。** 闭合任务按原生终局结束。此前允许终局后至多一次 Planner 只读收尾，研究者后续已撤回该要求：当前环境终局或预算停止后直接记录结果，不额外调用 Planner。开放任务按环境已定义的提交接口交付，验收缺席记待验；模型自然语言不参与终局判定，不预设完成声明或关键词检测。常规 Planner 调用、真实环境步、token 与耗时分别记账；已完成实验的原有收尾成本仍保留。采用真实派发的环境交互作主预算，取消独立 Planner 总额度，无动作往返设界以防空转，模型不可见剩余额度。末步先处理已发生的原生终局或验收。见 P3、P4、P5、P14。

**P7　按生效的 sub-plan 刷新 Executor 上下文。** 研究者已确认此边界。新子计划生效或当前阶段的职责被替换时，Executor 从当前目标、硬约束、环境观察、原生动作菜单和可追溯事实重建输入，工作区与真实环境连续。同一阶段内使用短窗口。PC 监控决定维持、PE 的规划工具给出维持意见，或 full-plan 只修订未来阶段时，当前窗口继续使用。PC-F 推进当前阶段编号、PC-S 换目标以及 PE-D-S 启用下一子计划时才开启新窗口。PE-D-F 与 PE-S 若有可辨认的当前执行阶段，同样按该阶段切换；EO 缺少显式 sub-plan 时以整任务为边界。LongHorizon-Harness 按子任务契约刷新上下文，一个契约内也可多步执行。见 P1、P8、P12。[原论文 §2.3](https://arxiv.org/html/2608.01964v1#S2.SS3)

**P8　独立配置规划覆盖范围。** full 覆盖剩余整任务，sub 覆盖一个可以跨步的阶段。EO 无规划范围，PE-S 一次性交付 full。PE-D-F/S 绑定到同一规划工具的不同配置，PC-F/S 则决定 Planner 保存完整计划与当前编号，还是保存已验证的阶段序列与当前阶段。两轴分开后，可以在相同范围内考察谁控制下一步。见 Q2、P1、P9。

**P9　PE-D-F 和 PE-D-S 共用动态指导的实现。** 已明确用这两个名称。F 修订剩余整项计划；S 在当前子目标结束后给下一份建议。两者都由 Executor 持有整任务，可在相同模型和记忆条件下比较覆盖范围。建议从框架族和 scope 派生唯一的运行标签，调度、清单、轨迹、汇总和阅读器沿用它，避免同一结果被算两次或混到一起。历史 `pe-d` 有全计划要求和固定边界，阅读时注明旧协议；不能直接当作新版 PE-D-F 的测量。见 Q1、P7、P8。

**P10　解析细则延后。** 当前动态解析取第一个匹配块，不检验块顺序、额外键或计划是否覆盖整任务。新接口先明确工具参数、行动方、返回内容与消息去向；重复块、扩展键及旧文本格式的兼容策略按研究者要求在其余部分完善后再审。协议能解析与证据能否支持阶段完成仍需分别验证。见 Q4、P5、P14。

**P11　暂留 `remaining_work`，明确其认识边界。** 运行器持有公开观察、来源、实际交付和动作结果；Planner 维护假设与剩余工作估计。当前两个列表每轮被替换，某项从列表消失可能表示已完成、被推翻或模型遗忘。因此空列表不能触发终止，遗漏也不能删除事实。建议先允许保留、修正或撤销估计，随后再比较它对下一次决策是否有独立作用、与 plan 的重复量和 token 成本。在其他变化稳定前保留该字段，避免同时改动太多因素。见 Q3、P5、P13。

**P12　两个角色需要不同的历史视图。** 完整原始轨迹可回放。Executor 每轮只取当前执行上下文、阶段内近期动作与跨阶段仍有关的事实；PC 的 Planner 读取 Q3 中按 F/S 区分的状态和本次实际动作及反馈。验收时同时检查旧商品价格能否按来源取回、旧页面菜单是否退出，以及阶段刷新后环境是否仍保留先前动作产生的变化。见 Q3、P2、P7。

**P13　`soft_guidance` 是否有独立用途？** 当前日志在 PE-S/PE-D 用它存整份计划，在 PC 用它存可选建议。即便字符串相同，交付职责也不同；对这个字段做统一统计容易误读。待选 **A**：删除独立软提示，PE 的 `plan`、PC 的 `stage_objective` 各只生成、交付和记录一次。**B**：保留可选执行建议，但必须说明与阶段目标、假设、证据均不同的用途，例如两条都满足硬约束的路线之间有一项偏好。建议先选 A；若研究需要控制这种偏好，再引入 B，并承认它改变了 Executor 收到的指导。旧字段继续按历史语义读取。见 P1、P2、P11。

**P14　如何知道 Executor 真的做到了？** 旧实现曾把首个行首 `Action:` 前的文本另存为 `executor_claims`，它只是原文截取，没有用于判断完成；当前已删除该派生字段。研究者明确不预设 Executor 输出完成声明，不按自然语言关键词判断成败。完整回复留在模型调用日志；PC 单步执行返回实际动作与环境观察，阶段判断依据这些证据。PE 调用规划工具的理由也仅是请求方的说明。有文件交付的后端按已定义的提交接口和原生测试验收，隐藏测试保持隔离。见 P4、P5、P10。

这些选择有四处耦合最强：触发权与阶段范围决定谁还能行动，记忆与字段决定双方能核对什么，格式与验收决定一个建议有多大权限，反馈频率与上下文长度共同决定成本。各组应在同一个反例上检验，再解释框架差异。[当前验收条件](experiments/planner-centered/protocol-design.md#两阶段协议验收)

### Function Tool 的定义与执行绑定

当前工作区使用 `two-phase-v3`。[单次运行状态 `FrameworkRun`](src/toolkit/frameworks/runtime.py) 复用执行会话，显式区分初始规划和后续循环。只有 PE-D 的 Executor 使用 `FunctionTool` 请求在线规划；Planner 通过普通 JSON 交付计划，PC 直接调用 Executor。`tools=[...]` 声明与 `invoke_tool()` 分发共用同一工具定义，不另建工具控制流程。旧数据和既有静态页面原样保留，当前代码只运行及读取 v3；旧控制器、字段回退和旧实验读取／评分回填已删除。重现历史需检出对应源码。[工具绑定](src/toolkit/frameworks/tools.py) · [框架入口](src/toolkit/README.md#四种运行框架) · [请求适配](src/recipe/planner-centered/run.py)

研究者进一步明确了 PE-D 与 PC 的两阶段控制流：先生成初始规划，再进入持续执行与监测。两种框架在第二阶段采用不同的调用机制：PE-D 的 Executor 按需通过原生工具调用请求规划；PC 每个非终局轮固定调用 Executor 一次，不需要模型工具调用。

研究者明确 Planner 角色说明使用任务类型，不直接填 benchmark 名称：ALFWorld 为 `household`、SciWorld 为 `scientific`、WebShop 为 `shopping`。当前领域说明直接写在各配置的 benchmark 模块中；Terminal-Bench 保留已有说明。已完成 run02 的原始提示和成绩保留，不将后续文案追溯应用到历史运行。[提示词组织与加载](src/toolkit/README.md#统一提示词)

研究者删除初始规划与持续监测的英文阶段标题，不再将它们提供给 Planner。初始／后续任务说明和两阶段调用顺序继续由运行器选择，阶段信息仅记在日志 `planner_phase` 的 `initial_planning`／`execution_monitoring` 中。后续又取消终局后的自动 Planner review，当前不再记录新的 `terminal_review`；旧轨迹中的收尾标记与成本保留。这些改动同步清理相关提示与测试依赖，历史轨迹与页面不回改。

PC 的提示组织保留 full/sub × initial/monitor 四份独立文案。Full 与 Sub 分别位于 `prompts/pc_f/<benchmark>.py` 和 `prompts/pc_s/<benchmark>.py`，模块内使用相同的 `PLANNER_INITIAL_PROMPT`／`PLANNER_MONITOR_PROMPT` 字段。监测提示按反馈判断、阶段处理与输出字段组织，不再字面叠加两套规则。研究者明确：若证据表明当前目标无法推进，可以舍弃并重新规划；Full 重规划剩余目标，Sub 直接给出新目标。Full 同时区分阶段是否改变与整体计划是否修订，保持当前阶段也可修改未来计划。被移除或改写的未完成目标原文留在 `discarded_stages`，当前阶段的状态与证据留在 `stage_result`，不将舍弃记为完成，也不把后续目标都标成受阻。运行器从所选模块读取角色和格式要求，再加入历史、当前状态和动态 JSON 字段契约。保留研究者已经完成的非 PC 文案删减；PC 四份文案仅迁移，继续待审，本轮目录调整未重采实验。[Full 模板](src/toolkit/prompts/pc_f/alfworld.py) · [Sub 模板](src/toolkit/prompts/pc_s/alfworld.py) · [记录边界](src/toolkit/README.md#四种运行框架)

| 框架 | 第一阶段 | 第二阶段的控制流 |
| --- | --- | --- |
| PE-D | 直接调用 Planner，交付初始规划。范围仍按 F/S 配置。 | Executor 执行任务并观察反馈；调用 `request_plan` 时转入 Planner，工具结果返回后由 Executor 继续执行。 |
| PC | Planner 先完成初始规划。 | 按当前规划直接调用 Executor 执行一步，获取环境反馈；环境未终止时由 Planner 监测并维持或更新规划，再进入下一次执行。 |

此前的工具协议强制 Executor 请求初始计划，并把 PC 初始规划与首步委派合在 `execute_step` 中。这个封装不是 PC 的架构要求。当前两阶段实现已去掉强制求助开场和执行工具：初始 Planner 完成交付后才调用 Executor；PC 后续只在实际反馈之后监测。[两阶段运行流程](src/toolkit/frameworks/runtime.py)

PE-D 收到 `request_plan` 才进入在线规划分支，返回结果与原调用 ID 配对；PC 按固定循环直接推进 Planner 与 Executor。工具对象只负责实际需要的声明与 handler 绑定。消息配对、参数和证据验证、持久环境、上下文、实际动作预算、日志与终局判定继续由运行会话承担。`deliver_plan`、`execute_step` 与 `submit_task` 不再作为模型工具。JSON 交付只增加完成此流程必需的对象解码，P10 的扩展解析策略仍延后。

PC 每个非终局轮必须执行一次 Executor，任务终止与成败依据执行后的环境反馈，不由 Planner 是否调用工具或自行宣告完成决定。预算耗尽和外部故障仍记为运行停止，不能替代环境成功。环境明确终局或预算停止后直接记录结果，不再额外调用 Planner；终止依据环境的 done／原因，中间奖励不单独触发停止。模型文本不作为完成信号，不进行自然语言关键词校验。ALFWorld 直接采用原生环境结果；Terminal-Bench 已有的提交工作区与 Harbor 原生测试路径单列，不为当前任务新增验收环节。先前列出的“PC 不调用工具时如何继续”源于把统一叙述误当作必需的工具接口，已撤回。研究者已授权实施和同一 `dev/2` 六配置实机验收，每组最多 20 个真实环境步；当前代码和离线契约检查对应这一两阶段目标。

新实机的六配置均在 4 个真实环境步后获奖励 1。PE-D-S 在找到、拿起遥控器后分别触发 `request_plan`，结果与调用 ID 配对。初始子计划为定位，随后交付拿取、移动到沙发；Executor 移动后直接完成放置，没有第三次求助。研究者接受这一最终轨迹：Executor 驱动整任务，能够直接完成目标时，无需为阶段形式追加规划。研究者同时明确工具说明暂不修改，不据本例另定通用触发规则或加入阶段门控，也不再将该样本列为待修复缺口。当时两种 PC 均验证固定单步循环和终局后的唯一只读收尾，无模型工具；该收尾策略现已取消，原有调用与成本保留。PC-F 首次规划超时保留归档，恢复后成功。PE-D-F 只有初始规划，在线复核或修订分支仍未得到实机验收。本次运行不构成成功率、成本优势或学习收益证据。[实机记录](experiments/planner-centered/README.md#两阶段运行协议)

2026-11-21 核查了以下项目的官方源码。阅读范围为工具定义、参数处理、工具列表装配和执行分发，未安装或运行这些框架。

| 项目 | 工具定义与执行如何连接 |
| --- | --- |
| OpenAI Agents SDK | `FunctionTool` 同时持有名称、描述、schema 和 `on_invoke_tool`。函数装饰器从签名生成参数模型和 schema，Agent 显式接收工具列表，Runner 按名称找到工具对象。手动构造 schema 也受支持。[工具对象](https://github.com/openai/openai-agents-python/blob/6c4e4a29cd08eef454db6980d74da6afc8939d24/src/agents/tool.py#L455) · [官方用法](https://openai.github.io/openai-agents-python/tools/#function-tools) |
| LangChain / LangGraph | `StructuredTool` 保存参数 schema 与 `func/coroutine`；`bind_tools()` 向模型声明工具，`ToolNode(tools)` 建立实例内名称映射并调用工具。声明和执行是两个入口，共用同一组工具对象。[工具构造](https://github.com/langchain-ai/langchain/blob/master/libs/core/langchain_core/tools/structured.py#L250-L266) · [执行绑定](https://github.com/langchain-ai/langgraph/blob/main/libs/prebuilt/langgraph/prebuilt/tool_node.py#L795-L808) |
| AutoGen | `FunctionTool` 从函数签名生成 Pydantic 参数模型，保存 callable；`run_json()` 使用参数模型验证后再执行。`StaticWorkbench` 从工具列表按名称查找，不要求字典注册表。[函数包装](https://github.com/microsoft/autogen/blob/main/python/packages/autogen-core/src/autogen_core/tools/_function_tool.py#L88-L116) · [查找与调用](https://github.com/microsoft/autogen/blob/main/python/packages/autogen-core/src/autogen_core/tools/_static_workbench.py#L94-L124) |
| smolagents | `@tool` 从类型和 docstring 生成工具定义并绑定 `forward`；Agent 用实例内的名称字典查找工具。其参数检查覆盖参数名、必填项与顶层类型，不能据此视为完整的嵌套 schema 验证。[工具构造](https://github.com/huggingface/smolagents/blob/main/src/smolagents/tools.py#L1061-L1101) · [调用分发](https://github.com/huggingface/smolagents/blob/main/src/smolagents/agents.py#L1455-L1488) |

此前的绑定整理采用标准库的小型工具对象关联 schema 与 handler，没有新增框架依赖。该做法继续用于 PE-D 的真实求助调用，不要求所有角色交付都包装成工具。环境、客户端、预算和日志通过运行上下文提供，不成为模型填写的工具参数。

`Agent.as_tool()` 的运行边界需要另行核对。OpenAI 的实现会启动嵌套 `Runner.run()`，AutoGen 的 `AgentTool` 也启动一次子任务运行；它们不会自动保持本项目“同一环境中执行一步即返回”的约定。当前 PC 不采用这类封装，环境持续、上下文刷新、成本与事件记录仍由会话维护。[OpenAI 实现](https://github.com/openai/openai-agents-python/blob/6c4e4a29cd08eef454db6980d74da6afc8939d24/src/agents/agent.py#L646) · [AutoGen 实现](https://github.com/microsoft/autogen/blob/main/python/packages/autogen-agentchat/src/autogen_agentchat/tools/_task_runner_tool.py#L20-L44)

此前仅整理绑定和命名时，七份离线记录在忽略时间字段后与旧实现一致；该证据只证明了当时的行为保持。本轮改变调用顺序与消息格式，使用新协议身份并按两阶段契约验收，不能再要求与旧记录逐请求等价。旧运行的原始消息、工具调用和评分保留。[工具绑定检查](src/toolkit/tests/test_function_tools.py) · [两阶段检查](src/toolkit/tests/test_framework_runtime.py)。除 OpenAI 的固定 commit 链接外，上表其余源码指向核查时的默认分支，后续实现与行号可能变化。

### 实机轨迹审阅：上下文与输出格式

下表保留从 v1 实机审阅到 v2 输入修订的问题来源。当前 v3 在这些修改上新增 `assessment` 命名和可配置输入窗口，删除全部旧实验兼容。旧任务完成不表示当前版本已实机验收。

| 项目 | v1 审阅事实 | v2 处理或未决项 |
| --- | --- | --- |
| Hard constraints | Recipe 固定传入「仅通过 ALFWorld 文本环境行动」，并非从任务提取。执行接口本身已限定环境。 | 研究者已决定删除独立字段、接口参数及注入块，不再另行抽取或复制任务约束。任务原文的价格、规格等要求保留；历史轨迹保留，当前代码不再读取旧格式。 |
| Observation 编号 | 直接使用共享日志的 `event_id`，模型调用与规划事件也占号。PC-F 的观察为 1、6、13、20、25。 | 观察从 1 连续编号，日志事件另记编号；规划求助、本地格式拒绝和模型调用不占观察号。`evidence_refs` 与报告链接按独立观察号处理。 |
| 初始观察中的任务 | ALFWorld reset 返回包含场景和 `Your task is to`；适配器保留该任务行，框架又单独加入 `Task goal`。 | 框架初始观察只返回场景，任务目标独立提供；原始 task、canonical 校验及普通 rollout 完整任务输入保留。 |
| Recent interactions | 当前阶段内最多两个已派发动作，包含最新动作；阶段字典变化即清空窗口。 | 移除该窗口与独立块，恢复完整交互历史，不因换阶段清空。 |
| Earlier public evidence | 按引用、出窗项与初始观察摘录，动作和观察分别截为 120／360 字符，总上限 1,800 字符。 | 移除引用筛选与字符截断。这只是回放和裁剪，没有自动压缩；研究者明确不保留该机制。完整 Executor 回复、动作、环境反馈与工具往返保留。 |
| PE-S Planner 提示 | PE-S 与 PE-D 共用模板，混入后续求助说明。 | 区分 PE-S 一次性规划与 PE-D 初始、后续求助；原生工具说明保持原样。 |
| JSON 与 thinking_summary | 普通响应要求 JSON，`thinking_summary` 必填，是实现契约。 | 当前字段改为 `assessment`，计划内部保留 JSON。研究者提出以 `<think>` 和 `<plan>` 划分文本，最终标签表示仍待讨论。 |
| Verified phases | 整段当轮 `thinking_summary` 被归档并回放，已完成阶段夹带未来工作。 | 模型输入只保留阶段目标、完成条件与证据引用，原始判断留日志。`verified` 是 Planner 判断；单独的语义 verifier 曾讨论但尚未引入。 |

上下文与编号实现见[运行实现](src/toolkit/frameworks/runtime.py)，格式约定见 [Planner 模板组织](src/toolkit/README.md#统一提示词)。标签可以划分公开判断、规划和动作，但不等同于服务端单独返回的推理内容；本批请求 `reasoning_effort: none` 后用量仍报告非零推理 token，不能据请求值断言实际已关闭。PE-D 求助继续是原生 `tool_calls`，不因普通文本格式选择而改为伪工具命令。

上下文容量管理与自动压缩分开。当前 Toolkit 提供 `context_window.max_input_tokens`，默认 `null`，研究者明确先不设数值。单次 prompt 正文嵌入按时间排列的完整交互；配置上限后，按角色持续淘汰最早的完整单元，不因固定前缀缩短重新补回已淘汰项，必要引用可明确保护。当前任务、计划或阶段、当前观察和正在交接的原生工具消息保留；这些内容本身放不下时记录窗口错误，不发送请求。没有模型摘要，完整原始日志不变。

默认计数是保守的 UTF-8 字节估计，接口允许注入模型 tokenizer；二者不是同一种精度。每请求记录计数方法、保留与淘汰记录、估计输入与服务端返回用量。历史请求的输入重复出现，不能把各次 `total_tokens` 相加作为当前窗口大小。Recipe 的独立字节拒绝已移除。

对照核查了原版 verl-agent 固定提交 `796ed310287fa605c9292a0fce07a86d79fde05e`：默认 `history_length=2`，`SimpleMemory.fetch()` 取最后 K 个完整观察／动作记录，不按字符摘录或生成摘要。ALFWorld 保存的是行动前观察与该动作，新返回的当前观察另列；所以 K=2 表示两个过去观察／动作对再加当前观察。内存保留先前记录，输入只选最近 K 条，只在环境 reset 清空，未按子计划清空。核查依据为本地固定提交源码，对应官方链接：[配置](https://github.com/langfengQ/verl-agent/blob/796ed310287fa605c9292a0fce07a86d79fde05e/verl/trainer/config/ppo_trainer.yaml#L292-L297) · [memory](https://github.com/langfengQ/verl-agent/blob/796ed310287fa605c9292a0fce07a86d79fde05e/agent_system/memory/memory.py#L81-L100) · [ALFWorld 存储与构造](https://github.com/langfengQ/verl-agent/blob/796ed310287fa605c9292a0fce07a86d79fde05e/agent_system/environments/env_manager.py#L147-L208)。本轮远端读取遇连接错误，未声称核验了上游最新版本。

同版本 WebShop 另有带历史完整提示超过 13,000 字符后，当轮切换无历史模板的规则；这不属于 ALFWorld，也不是摘要压缩。[WebShop 源码](https://github.com/langfengQ/verl-agent/blob/796ed310287fa605c9292a0fce07a86d79fde05e/agent_system/environments/env_manager.py#L464-L502)。本地 `verl-agent-system` 修改版固定提交 `d9ba39f88fcd327afca1a9eb701f2a362666842f` 的 ALFWorld 沿用上述窗口，Executor 将格式化观察与 metaplan 拼成一条 user 消息；它与原版分别核查，不能拼成同一个实现结论。本项目 v2 按研究者本轮决定使用完整历史，没有照搬 K=2 窗口或 WebShop 的无历史降级规则。

真实任务要求的一个本地例子是[WebShop 后端检查所用任务](src/toolkit/tests/test_live_backends.py)：要求双频、四核的播放器，价格低于 340 美元。价格上限与功能要求已经在任务原文里；研究者据此决定不保留独立 Hard constraints。运行器、四后端 Recipe 和新清单已移除该字段；旧 WebShop 回放代码已删除，历史产物保留。

PE-D-S 的观察须准确表述为「可一步完成整任务时，Executor 直接行动」，而非「提前看到环境的任务完成标志」。[原始轨迹](experiments/planner-centered/runs/two-phase-magpie-dev2-campus/trials/m5-t2-pe-d-s.json)中，事件 22 只返回沙发场景与当前动作列表，事件 23 是普通单步反馈；事件 24 的公开说明认为放置即可完成任务，随后实际放置。终局反馈到事件 25、26 才出现。原目标持续可见、动作菜单列出了可直接放置的命令、通用执行提示要求完成整任务，都可能影响该选择，单条轨迹不能分离原因。研究者接受本次自主完成的结果形式，并明确保持工具说明原样；记录该现象及理由，不将其视为必须补齐求助的失败，也不扩大为其他情形均无需求助的结论。

PE-D-F 本次只验证了初始规划和正常执行。后续需在公开反馈确实构成重新规划理由的情形中，观察 Executor 是否自主求助，以及 Planner 如何保持或修订整体计划。不能以 PE-D-S 的求助轨迹替代该范围的验收，也不通过强制调用伪造动态触发。补验范围与预算另定，本轮不启动。

首次 v3 采样（01）的[六配置单任务轨迹](experiments/planner-centered-v2/README.md#本轮单任务实机验收)已生成，未修改提示或补跑。五组 4 步成功，PC-F 在首次监测时将阶段 2 具体化为从 `coffeetable 1` 拾取，重发 `full_plan` 却漏 `revision_reason`，被现行契约拒绝；这不是原生环境失败。当前实现按完整计划结构变化识别修订，因此也覆盖措辞变化和位置具体化。是否接受这种边界、是否将阶段更新和路线修订区分，留待研究者审阅真实输出，不在本轮自行更改。两种 PE-D 本轮均未求助，原生交接分支仍未实机覆盖。

核对 PC-F 事件 8 的实际请求，提示确有「Only provide full_plan again when you revise the route, with revision_reason.」，但只将该字段关联到路线修订，没有说明任意措辞变化或已知位置具体化也强制需要理由。该次 JSON 字段契约的 `required` 仅含 `assessment`，没有表达条件必需；运行器则对变化后的 `full_plan` 一律要求非空 `revision_reason`。因此本次拒绝符合代码，却暴露了提示语义与判定范围没有对齐，不能仅归因为 Planner 遗漏已明确约定的字段。[当时实际请求](experiments/planner-centered-v2/runs/v3-deepseek-dev2-01/report.html) · [判定](src/toolkit/frameworks/runtime.py)

研究者随后授权先明确 `revision_reason` 的 JSON 字段要求：修改后整体计划和非空理由放在同一个 JSON，首次规划不要求理由，只转到已有阶段时省略整体计划。本轮按现有代码将任意计划内容变化视为修改，不重新定义路线修订，也不增加回退或重试。

研究者提出将完整历史前移，随后明确 Planner 同样调整。两角色输入现按基础说明、任务目标、完整可见历史、本轮规则与当前计划状态排列。Executor 的当前动作菜单位于历史之后、指导之前，Planner 仍无菜单。保留完整历史和当前工具交接，不以位置调整替代历史选择或压缩。历史是否导致 PE-D-S 不再求助仍是假设：该轨迹还受到任务难度、子计划粒度、任务原文与执行提示影响。研究者已授权按同任务、同模型、六配置各 20 步重新采样；同时改动字段说明和顺序的一次采样不能分离各因素的因果作用。

第二轮（02）已完成：六组均 4 步成功，EO 首请求的服务端故障单独归档并仅补一次；两种 PE-D 仍仅初始规划、无在线求助。PC-F 只推进已有阶段，首次重发的整体计划内容未变，后续省略 `full_plan`，没有触发修改后要求理由的分支。实际输入顺序已核对；本轮未观察到更多求助，不能由单次结果确定或排除历史位置的作用。[新轨迹、成本与源码边界](experiments/planner-centered-v2/README.md#提示修订后的第二轮采样02)

### Planner 能力说明与动作接口

规划粒度与动作信息的可见范围分别定义。高层 Planner 负责子目标、前提依赖、取证和路线调整，需要了解 Executor 的能力与约束；知道动作接口本身不使它成为低层策略。原 ALFWorld 与 ScienceWorld 模板直接列出原子命令，并以执行者口吻描述，存在诱导逐动作规划的风险。按研究者要求，四环境的独立计划模板参考本地 `verl-agent-system` 的抽象 global plan 写法，改为子目标、前提和证据要求，删除具体命令指令；这些模板现保存在 `pe_s/` 各 benchmark 模块的 `PLANNER_TEMPLATE` 中。动态候选目录只加入 Executor 消息，Planner 接收原始公开观察与已执行动作；职责分离同时落实在提示词和输入构造中。[当前固定计划模板](src/toolkit/prompts/pe_s/alfworld.py) · [规划职责](PROPOSAL.md)

动作语法模板、动作与对象的候选组合、当前状态的有效动作须分开。按本轮实际依赖核查，ALFWorld 0.4.2 的 TextWorld 后端返回 `info["admissible_commands"]`；ScienceWorld 1.2.3 提供 `get_possible_actions()` 模板、包含无效项的 `get_possible_action_object_combinations()`，以及 `get_valid_action_object_combinations()` 和 `info["valid"]`。当前适配器将 ALFWorld 与 ScienceWorld 原生 reset/step 返回的有效列表提供给 Executor，ALFWorld 缓存更新方式参考 verl-agent。WebShop `64fa2a5` 的 `get_available_actions()` 从当前页面提取搜索框与可点击标签，也经统一接口提供给 Executor。四种框架沿用同一后端的相同规则；候选不保证动作推进任务或购物成功。[ALFWorld 接口](https://github.com/alfworld/alfworld/blob/0.4.2/alfworld/agents/environment/alfred_tw_env.py) · [ScienceWorld 接口](https://github.com/allenai/ScienceWorld/blob/1.2.3/scienceworld/scienceworld.py) · [WebShop 接口](https://github.com/princeton-nlp/WebShop/blob/64fa2a5c15c7daa698b9ac93f5bb5437b634c9bd/web_agent_site/envs/web_agent_text_env.py)

静态 Executor 模板不保存具体动作清单；当前列表在构造最终请求时以 `Available actions: ...` 动态加入。普通 rollout 的 reset/step 经 `BaseEnv._executor_feedback()` 注入，框架的 `_executor_context()` 从环境读取当步列表后注入，二者共用 `render_action_feedback()`。此前工具协议的七项离线检查及六配置夹具确认了 23 次 Executor 请求只含当步列表；两阶段协议继续检查相同的角色可见性和刷新边界。夹具是合成输入检查，不是新的模型或后端实测。[渲染函数](src/toolkit/prompts/templates.py) · [普通 rollout](src/toolkit/envs/base.py) · [框架请求](src/toolkit/frameworks/runtime.py)

真实请求证据来自 2026-11-20 保存的 `native-tools-magpie-dev2`：抽样 EO、PC-F、PE-D-S 共 13 次 Executor 请求均含列表，动作后列表与环境反馈记录一致。PC-F 的 event 11 出现 `take remotecontrol 3 from coffeetable 1`，拾取后的 event 19 改为包含 `examine remotecontrol 3` 与放置动作。反之，旧正式运行 `alfworld-test-01` 的 EO 轨迹 `m1-t1-eo` 在 event 3 的完整请求中只有静态行动要求，未附 `Available actions` 列表。因此，旧结果页可能确实没有清单，不能据此判断当前代码仍缺失。旧正式运行仅抽查这一条，不外推整批；历史 prompt 保留原样，该次动作列表核查未调用模型或重跑实验。[实机 PC-F 原始请求](experiments/planner-centered/runs/native-tools-magpie-dev2/trials/m1-t2-pc-f.json) · [旧正式 EO 原始请求](experiments/planner-centered/runs/alfworld-test-01/trials/m1-t1-eo.json)

原手写列表存在实际不匹配：核查 ALFWorld 测试清单中 task 0 与首个灯下查看任务的游戏内嵌 grammar，`ToggleObject` 使用 `use {o}`，旧模板却写 `toggle {obj} {recep}`，适配器没有对应转换。旧列表还遗漏 `look`、`inventory`、`examine`；ScienceWorld 旧列表同样不完整，容器内部检视应区分 `look in` 与 `look at`。这些是静态源码与游戏定义核查，不代表已重测所有任务。当前 Executor 改用环境候选，不再维护手写目录。Terminal-Bench 保留实际 shell 执行和 `finish` 接口，不伪造有限候选列表。动态有效列表提供额外的状态可行动性信息，不等同于 expert plan 或 gold path。本次协议改动没有重跑旧实验，也未核验对既有比较的影响；历史原始 prompt 和结果保留。[ALFWorld 清单](experiments/planner-centered/runs/alfworld-test-01/manifest.json) · [ALFWorld 适配器](src/toolkit/envs/alfworld_env.py) · [ScienceWorld 适配器](src/toolkit/envs/sciworld_env.py) · [WebShop 适配器](src/toolkit/envs/webshop_env.py)

#### 参数实例化、状态筛选与 Planner 评价

verl-agent 原版在固定版本 `796ed310287fa605c9292a0fce07a86d79fde05e` 中，把每轮后端的 `admissible_commands` 传给 `build_text_obs()`，过滤 `help` 后逐条填入 `{admissible_actions}`。这个占位符代表整份已实例化候选列表，不是 `go to {recep}` 中待模型填写的参数；所核查的主链路没有另外附上后一种语法目录。官方固定版本与本地相关文件已交叉核对。[候选渲染](https://github.com/langfengQ/verl-agent/blob/796ed310287fa605c9292a0fce07a86d79fde05e/agent_system/environments/env_manager.py#L180-L208) · [模板](https://github.com/langfengQ/verl-agent/blob/796ed310287fa605c9292a0fce07a86d79fde05e/agent_system/environments/prompts/alfworld.py#L17-L35)

这里须区分三种输入，不能把它们统一描述为补充动作说明：

| 输入 | 运行器提供什么 | Executor 还要判断什么 |
| --- | --- | --- |
| 命令模板，如 `go to {recep}` | 命令语法与参数位置。 | 选择实体、填写参数、判断前提和目标用途。 |
| 仅按已观察实体填参的候选 | 部分实体 grounding，即把参数关联到具体对象名称；不按当前状态筛选。 | 判断哪些组合此刻可行、哪些推进目标。 |
| 当前 `admissible_commands` | 已填参，并依据环境内部状态筛选的候选。 | 从候选中决定取证和行动路线；合法不等于有助于目标。 |

TextWorld 1.7.0 从内部符号状态的 `all_applicable_actions()` 得到 `valid_actions`，再生成 `admissible_commands`，并非从已交付的观察文本解析候选。因此它超出纯语法帮助，提供状态可行动性信息；但没有证明每个任务的列表都包含文本观察或历史无法推导的隐藏信息，也未证明它覆盖所有可执行字符串。它与专家计划是不同通道。ALFWorld 官方示例还注明 BUTLER 不使用该列表，且 `AlfredThorEnv` 不提供这一接口，不能把文本模拟中的便利条件直接视为具身部署的通用能力。[候选生成](https://github.com/microsoft/TextWorld/blob/1.7.0/textworld/envs/wrappers/tw_inform7.py#L267-L272) · [内部状态来源](https://github.com/microsoft/TextWorld/blob/1.7.0/textworld/generator/game.py#L995-L998) · [ALFWorld 官方说明](https://github.com/alfworld/alfworld/blob/0.4.2/README.md#L65-L73)

具体到已核查的 `dev/2` PC-F 样本，初始菜单的 15 个导航目标均已出现在原始初始观察中。这一例不支持“额外泄露了容器名称”的判断；后续候选仍依状态筛选，其信息作用须另行分析。[原始观察与请求](experiments/planner-centered/runs/native-tools-magpie-dev2/trials/m1-t2-pc-f.json)

对本研究，它可以作为明确的辅助执行条件：高层 Planner 关注子目标、依赖、取证与路线调整，候选菜单可能减少命令误写、实体编号填写或无效动作对评价的干扰。同一模型、prompt、采样与预算之外，还应固定候选生成和交付规则。比较能够支持的是“在该 Executor 与接口条件下，Planner 有何作用”，而非脱离执行接口的本征规划能力。不同计划到达不同状态，收到的具体候选也可不同；固定菜单规则不等于给每条轨迹相同提示。

主要风险是菜单补偿计划遗漏、替代部分状态前提判断或减轻执行记忆负担，从而改变计划间的差异甚至排序，而不只减少随机波动。Planner 未直接看到菜单，也不能排除这种影响，因为菜单先改变 Executor 行为，再改变 Planner 接收的反馈。向需要自行填参或没有可行动作查询的接口迁移仍待验证；列表的输入 token、上下文占用和环境派发成本也须记录。已有旧正式运行的输入还须与当前菜单协议分开，不能合并解释接口收益。这些是机制风险与适用限制，不是已观察到的负面结果。

建议的最小核查是固定同一批任务、计划、Executor 与预算，对照“经过核准的命令模板”和“当前状态筛选候选”，重复执行后比较原生成功率、无效动作率、同计划波动和计划间效用或排序。此对照先测整体接口辅助效应；若需要区分填参与状态筛选，再补仅对已观察实体填参的中间条件。旧模板须先核准语法与覆盖范围，不能以有错误的目录作基线。二元成功结果的方差随成功率变化，不能仅因方差降低就认定评价噪声已被消除。研究者已决定暂时保留当前 action prompt 与已填参数的候选列表；这不等于证实其只减少评价噪声。本轮仅实施框架控制流，未启动这项接口对照实验。

### 评分与外部故障

ALFWorld 的 HTTP 429、连接错误、超时和服务端错误会留下缺评。原生零分对应环境给出的失败结果。定向补跑只覆盖有外部故障证据且仍缺评的组合，固定任务、模型、框架和单条执行额度，保留该组合首个有效原生评分。比较报告用共同有分任务配对，已归档尝试只参与可核对的成本统计。[补跑证据与评分口径](experiments/planner-centered/README.md#完整测试集评测)

当前 `planner-centered-v2` 完整测试 run02 的首轮配额故障属于运行资源问题。当时终止进程的异常是 `fast_downward` 向 `/tmp` 复制 32,534,448 字节动态库时遇到 `Errno 122`，该挂载点启用了用户配额；磁盘整体空闲量不能排除用户配额耗尽。TextWorld 关闭环境未卸载该库，原来每条 trial 新建后端，已删除的库副本仍由进程映射持有。无模型诊断中，12 次加载对应 12 份库；改用 4 个独占 slot 重载 12 轮、共 48 次后，库副本恒为 4。这个检查支持限制副本增长，不证明作用域结束后 native 库已卸载，也不构成框架性能结果。[原始诊断与最小修复](experiments/planner-centered-v2/README.md#run02-quota-中断与恢复)

本轮恢复只覆盖 606 条无事件的 `OSError` 启动失败和 7 条 `InternalServerError`，共 613 条，已于 2026-11-23 15:01:26（北京时间）完成；首轮 116 条有效评分（76 成功、40 预算耗尽零分）保留，75 条协议错误维持缺评且未重采。每条至多两次尝试，原失败与成本保留，模型、prompt 和评分契约不变。最终 804 条中 465 条有分、339 条缺评，其中 333 条为协议终止、6 条为外部故障；不将这些最终总数与首轮快照相加。[最终结果及完整异常审查页](experiments/planner-centered-v2/README.md#完整测试结果与最终异常审查)

### 当前协议拒绝与规划能力的区分

研究者明确，单个 JSON 对象外包 Markdown 代码围栏可以接受，没有必要只因这一包装中断任务。当前实现将运行可解析性与输出格式偏好分开：只规范化完整的三反引号围栏（`json` 标记或无标记），随后仍检查 JSON 对象、必需字段、阶段编号和证据引用，不补写或猜测规划内容。原始回复继续保存；若未来训练希望抑制围栏，可依据原文单独计算 format reward，不能在规范化后将原格式抹去。这是候选训练处理，不代表已选定奖励形式或启动 RL。研究者已授权先提交已有改动，再完成该有界解析修订和新的单任务六配置验证；旧实验拒绝与成本保留原样。[实现与检查边界](src/toolkit/README.md#四种运行框架) · [新一轮设置](experiments/planner-centered-v2/README.md#完整-json-围栏容忍后的复验)

解析修订后的 `test/1` 03 六配置均获原生奖励 1。PC-S 事件 18 的真实围栏 JSON 正常产生 keep 决策，后续继续环境动作且最终成功，原始围栏文本仍在日志与页面；这是接受分支的实机证据。PC-F 本轮没有围栏，相关场景由离线集成检查覆盖。93 次实际请求与页面原文已核对，无重采；单次结果不说明架构成功率或排除采样随机性，PE-D 在线求助和弃用目标仍未触发。[结果、源码补丁及围栏审计](experiments/planner-centered-v2/README.md#完整-json-围栏容忍后的复验)

首轮 75 条协议缺评的直接触发输出来自 Planner 60 条、Executor 15 条，均已按原始响应和实际拒绝条件核查。代码围栏和 JSON Schema 外壳属于生成格式与解析契约的冲突，不能直接解释为规划内容错误；schema 用于说明字段时，模型仍可能输出 schema 本身或将实例值置于 `properties` 中。是否给解析器有限兼容或改写格式说明，需在后续独立版本中决定，本轮未更换输入。[首轮分布与原始证据](experiments/planner-centered-v2/README.md#首轮-75-条协议缺评核查) · [最终异常轨迹查看页](experiments/planner-centered-v2/runs/alfworld-test-qwen38-27b-deepseek-02/failure-review.html)（含全部归档异常，不能视为首轮核查的同一分母）

另有三处已确认的运行边界。第一，PE-D 的第二次连续 `request_plan` 在真正调用 Planner 前即因 `no_action_rounds > 1` 被拒绝；该上限未在模型提示中说明，不能说成 Planner 第二次回答失败。第二，当前 `keep: true` 与计划字段同时出现就被拒绝，即使重发值与已有计划相同；这把冗余表达也当作冲突，是否放宽仍待讨论。第三，`previous_stage_status: verified` 要求同时存在证据引用、旧阶段且新旧阶段不同；本轮对应样本是仍指向原阶段而被拒绝，并非独立 verifier 判断完成证据在语义上不成立。阶段状态、阶段切换与完成验证应分清；当前仍没有独立阶段语义 verifier。本轮只记录这些限制，未在恢复中修改协议、prompt 或评分。最终 PC-F 仅 2 / 134 条有效评分、PC-S 为 37 / 134；仅有分样本的条件成功率不能代替完整任务覆盖下的架构表现。

研究者审阅 `m1-t1-pe-d-s` 后，进一步区分了“当前子目标仍有效”和“当前指导已回答求助”。Executor 问定位 bowl 的更有效方法，Planner 认可请求但 keep；工具只重送原目标与完成条件，不回送 assessment。随后 Executor 表示准备查 countertop，却又调用规划工具，因第二次连续求助而在 0 个环境步时终止。该例支持分别审查请求满足程度、动作／求助分支选择和运行器停止规则，也暴露出保持同一子目标时补充方法指导的职责与交付边界。它尚不能证明三者之间的因果关系，或证明放宽限制、增补指导、采用 benchmark 专用提示词能改善成功率。[逐事件证据与解释边界](experiments/planner-centered-v2/README.md#定位-bowl-时的求助与连续调用)

首次 `test/1` 采样的两条 PE-D 又出现了可见执行方向与实际工具分支不一致。`Thought:` 是普通响应正文，可与原生 `tool_calls` 同时返回；协议禁止的是 `Action:` 与规划调用混发。两条第二次请求均表示准备搜索 countertop，却仍调用 `request_plan`，理由没有提出新的规划问题。当前本地客户端没有设置强制工具选择，也没有从 Thought 合成工具请求，日志中的正文与调用字段分别取自模型 API 响应；这一核查不等于核验了网关改写前的上游原始响应。候选解释是混合接口带来的选择困难：环境动作用 `Action:` 文本，唯一原生工具却是规划求助；基础提示还无条件要求每轮一条 Action，后置规则则允许求助并禁止附带 Action，例外未在基础要求中写清。该歧义已确认存在，是否导致此次行为仍须对照，不能从可见 Thought 推断内部决策过程。该次核查只记录问题，没有修改当次实验提示或追加生成请求。[当时采样与原始轨迹](experiments/planner-centered-v2/README.md#最新提示词单任务轨迹验收test1)

研究者随后要求先统一行动／求助输出，并将提示词按六种实际配置、再按 benchmark 组织。当前工作区使用 `eo/`、`pe_s/`、`pe_d_f/`、`pe_d_s/`、`pc_f/`、`pc_s/` 六个目录；Full/sub 的角色、规划文案、执行指令和求助说明可分别审核。框架按 `mode` 与 benchmark 加载唯一模块，不再将环境默认 Action 指令与求助例外叠加。PE-D 单轮选择一个环境动作或一次原生规划求助；Thought 可解释该分支，求助须提出具体未解决的规划需求，不能只宣布执行意图。工具原有 Full/sub 时机说明保留，不新增强制求助或行动间隔；连续无动作保护和其他解析、预算规则不变。离线请求组装与回归检查通过后，研究者授权同一 `test/1` 六配置各一次的真实复验；不能由结构简化或文字澄清推断旧行为的原因或成功率改善。[六配置提示入口](src/toolkit/README.md#统一提示词)

六目录更新后的 `test/1` 02 已完成，58 份实际请求均对应所选配置的 benchmark 模块，Full/sub 初始与监测文案、PE-D 互斥规则及原生工具描述已逐条核对。EO、PE-S 和两种 PE-D 成功；PE-D 全程自主行动，仅各一次初始 Planner，本轮未触发在线求助。两种 PC 均在第 2 步后以 Markdown 围栏交付 JSON，触发 `invalid_planner_json` 而缺评；没有按零分统计，也未修改解析后重采。弃用目标仍未触发。这次结果只能用于审核组装与实际行为，不能说明统一规则消除了连续求助，或说明新文案改善架构性能。[设置、完整轨迹与逐请求核对](experiments/planner-centered-v2/README.md#六配置独立目录更新后的复验)
