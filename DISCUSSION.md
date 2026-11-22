# 研究讨论

按主题持续更新。这里整理问题、工作假设和候选对照。已确认的研究状态与决定见[研究工作台](RESEARCH.md)，实验结果见[实验目录](experiments/README.md)。

## 全面审核清单

审核范围：当前工作区的新协议实现、提案 v0.6 与新实验设置。已提交的上一轮修改见 `6afb80e`、`a719e04`、`3cb3113`；这些提交不代表本轮未提交修改。以下编号保留供回查，不表示优先级。

研究者已确认：新建 `planner-centered-v2`，旧数据保留但当前代码无需兼容；使用 ALFWorld 0.4.2 及主 requirements 固定版本；当前只测未经专项训练模型的框架表现；同步提案并记录实验协议；将判断字段改名为 `assessment`；以嵌入 prompt 的交互历史和可配置 token 窗口替代 Recipe 字节拒绝；先不设窗口容量。此前的独立约束删除、连续观察号、目标去重、PE 模板分开、精简 verified 输入、保留已实例化动作菜单和接受 PE-D-S 自主完成的决定继续有效。

### 待人工验收的实现与证据

| 编号 | 当前事实 | 剩余验收内容 |
| --- | --- | --- |
| A1 | 当前协议 `two-phase-v3` 实现完整历史与可配置窗口、独立观察号、目标去重、提示分开和约束删除；尚无该版本模型实机轨迹。 | 最终角色输入、工具配对和停止行为。启动模型检查前仍需冻结任务、模型和预算。[框架与检查](src/toolkit/tests/test_framework_runtime.py) |
| A2 | 通用模型客户端保持透传；Recipe 已改为 Magpie 官方 native 路径与裸上游模型名。 | 配置与真实请求的对应；非零推理 token 原因仍待实测，不能由路径推定已经关闭推理。[配置](src/recipe/planner-centered/config.yaml) |
| A3 | 旧 PE-D-F 实机仅观察到初始规划，S 范围求助不替代 F 范围验收。 | 在有重新规划理由的任务中观察自主触发，不能强制求助凑轨迹。归入新实验验收。 |
| A4 | PC 的 revision、blocked／replaced 等边界有离线检查；Terminal 完整后端检查依赖 Harbor。 | 区分离线契约与真实模型／环境证据。[框架检查](src/toolkit/tests/test_framework_runtime.py) |
| A5 | 已决定独立新实验，旧成绩归档保留。 | 已回应，不再要求审核旧轨迹作为新实验前置。[新实验](experiments/planner-centered-v2/README.md) |
| A6 | 已指定并安装 ALFWorld 0.4.2 及主 requirements 版本，真实 ALFWorld 重载／动作检查通过。 | 原 hub 版本冲突与 TextWorld wheel 标签错误已修复，pip check 及后端复查通过；WebShop 来源限制只在纳入时核查。 |
| A7 | 提案 v0.6 已同步两阶段控制流、六配置、约束删除和当前性能测试范围。 | 审核新的正文与 Mermaid 图，原 v0.5 审批不自动覆盖本轮修改。[提案](PROPOSAL.md) |
| A8 | 查看页与导出只处理当前协议，保留完整 prompt／response、工具参数、缺评和重试成本。 | 只核对展示与性能统计口径，当前无需学习机制的科研解释。[导出](src/recipe/planner-centered/export_alfworld.py) |

### 尚未确定的设计选择

| 编号 | 当前决定与剩余问题 | 边界 |
| --- | --- | --- |
| D1 | `assessment` 是模型给出的状态／阶段判断，用于理解计划更新及其证据；不是 thinking 总结、独立 verifier 或成功裁决。计划内部继续 JSON。是否改用标签仍待讨论。 | 当前只改名，无旧字段回退；保留 `Thought:`／`Action:`，不擅自改为 `<think>` 标签。[格式讨论](#实机轨迹审阅上下文与输出格式) |
| D2 | P10 的重复块、块顺序、Markdown 包裹、未知键和截断等扩展解析策略仍延后。 | 当前不维护旧实验输出兼容，不把解析成功当计划正确。 |
| D3 | Toolkit 输入 token 窗口已实现，默认容量 `null`，超限淘汰最早完整交互，无自动摘要。 | 单次正文嵌入历史，保留当前原生工具交接；完整日志与窗口选择分开。默认计数为保守估计，实际用量单独记录，不累计重复历史 token。[实现](src/toolkit/models/context.py) |
| D4 | 独立阶段语义 verifier 尚未引入；当前 `verified` 是 Planner 基于可见证据的判断。 | 环境终局与 Terminal 原生验收另有机制，不能混为没有 verifier。 |
| D5 | 已核查并配置 Magpie native 透传。是否真正关闭推理仍待新请求验证。 | 原因假设与事实分开；本轮不进行模型调用。未来训练文本与 loss 的选择不属于当前测试前置。 |
| D6 | `hypotheses`／`remaining_work` 暂留，空剩余工作不触发结束。 | 独立用途及修订语义仍待实测，不据此裁定任务完成。 |
| D7 | 新实验的任务、模型、重复次数、主指标、采样和预算尚未冻结。 | 当前准备实现和协议；不自动继承旧运行授权。[设置清单](experiments/planner-centered-v2/README.md#启动前需要固定的设置) |

### 需要证据回答的研究问题

研究者目前不要求回答这些问题。它们保留为后续经验研究，不是当前未训练框架测试的前置选择。当前没有本项目训练结果，不能由接口或单任务成功推断学习收益。

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

旧 Q1–Q4、P1–P14 的内容继续作为方案形成过程保存。其实现验收归 A1／A3／A4，当前格式与解析归 D1／D2，证据判断归 D4，暂留状态归 D6；已撤回的记忆窗口和工具封装不形成另一份待办。本轮已回应的编号按上表处理，研究问题等待后续证据，不要求现在逐项判断。

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

## 两种规划架构下的 Planner 优化

四种框架及规划覆盖范围的工作定义见[提案 v0.5](PROPOSAL.md)。讨论的重点是 Planner 在任务中重新获得决策权后，三项研究问题对应的观察对象如何变化。

| 研究问题 | Planner-Centered 中的研究对象 |
| --- | --- |
| 战略探索 | 比较先取什么证据、如何委派，以及不同反馈下如何改变路线。 |
| 低成本评价 | 分开判断证据是否支持一个前提、行动是否推进任务，以及整条策略的终局价值。取证可能改变状态或消耗预算。可用从同一初态独立运行的完整轨迹校准局部证据，并计入取证成本。 |
| 策略更新 | 记录 Planner 每次决策时实际可见的信息、选择与后续结果。在线反馈可以触发修订，用什么信号更新 Planner 参数及更新是否有效需要另证。 |

2026-11-18 的 Planner-Centered 测试工作稿用未经专项训练的 EO（无外部 Planner）、PE-S（一次性外部规划）与 Planner-Centered 比较系统的成功率和端到端成本。该比较同时涉及在线反馈、计算投入和阶段委派。若进一步检验学习收益，在各自架构内固定执行和运行协议，对照更新前后 Planner 在未见任务上的表现。跨架构比较使用同一任务与冻结 Executor，计入额外模型调用和环境交互。主要未知是哪些新证据会改变高层路线，以及这种改变能否在可比预算下改善结果。

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

### 规划覆盖范围与控制权

实施前的四配置协议要求 Planner 生成覆盖全部剩余工作的计划，解析器检查非空 `<plan>`。旧 PC 向 Executor 下发阶段目标与 `soft_guidance`，整体计划保留在 Planner 状态中。下文按原问题编号保留针对该版本的分析。[实施前协议快照](experiments/planner-centered/protocol-review.html#issues)

这里的 sub-plan 覆盖一个可跨多次环境交互的高层阶段。当前两阶段协议由 Executor 推进 EO 和 PE，PC 固定单步执行后由 Planner 监测；只有 PE-D 的在线求助使用模型工具。动态 PE 和 PC 都可以采用 full 或 sub 范围。Planner 先判断再交付，Executor 按生效的 sub-plan 更新当前指导，完整交互历史跨阶段保留，并采用 P6 的预算与收尾规则。`remaining_work` 暂留，P10 扩展解析细则延后。下列 Q/P 保留形成 v1 时的讨论，其中短窗口与历史摘录方案已由 v2 的完整历史替代。[实施方案](experiments/planner-centered/protocol-design.md) · [运行验收状态](experiments/planner-centered/README.md#两阶段运行协议)

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

**Q2　初次规划和重规划应共用什么？** 现行动态指令反复要求剩余整体计划。下一版的 PE-D-F 复核求助理由并决定是否修订剩余路线，PE-D-S 根据触发原因给下一子计划。PC-S 和 PC-F 共用两个明确的阶段。**Initial Sub-Plan Generation** 首次确定当前阶段，PC-S 生成首个子计划，PC-F 生成带编号的完整计划并指定第一个生效的子计划。**Continuous Execution Monitoring** 在每次实际动作得到环境反馈后由 Planner 判断维持、转段或修订。两阶段都先判断再交付，公开输出先给能回查的简短判断依据，计划只写待做工作。旧轨迹中“确认马克杯已放入柜子”属于核对事项，观察即使证实放入，也不足以证明它满足 `cup` 类别。[现行模板](src/toolkit/prompts/frameworks.py) · [旧任务 58](experiments/planner-centered/finish-advice.md)

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

**P6　收尾与预算已确认。** 闭合任务按原生终局结束，随后至多一次只读收尾。开放任务由整任务负责人提交，验收缺席记待验。收尾、常规 Planner 调用、真实环境步、token 与耗时分别记账。采用真实派发的环境交互作主预算，取消独立 Planner 总额度，无动作往返设界以防空转，模型不可见剩余额度。末步先处理已发生的原生终局或验收；PC 对终局动作的最后一次观察可兼作收尾。见 P3、P4、P5、P14。

**P7　按生效的 sub-plan 刷新 Executor 上下文。** 研究者已确认此边界。新子计划生效或当前阶段的职责被替换时，Executor 从当前目标、硬约束、环境观察、原生动作菜单和可追溯事实重建输入，工作区与真实环境连续。同一阶段内使用短窗口。PC 监控决定维持、PE 的规划工具给出维持意见，或 full-plan 只修订未来阶段时，当前窗口继续使用。PC-F 推进当前阶段编号、PC-S 换目标以及 PE-D-S 启用下一子计划时才开启新窗口。PE-D-F 与 PE-S 若有可辨认的当前执行阶段，同样按该阶段切换；EO 缺少显式 sub-plan 时以整任务为边界。LongHorizon-Harness 按子任务契约刷新上下文，一个契约内也可多步执行。见 P1、P8、P12。[原论文 §2.3](https://arxiv.org/html/2608.01964v1#S2.SS3)

**P8　独立配置规划覆盖范围。** full 覆盖剩余整任务，sub 覆盖一个可以跨步的阶段。EO 无规划范围，PE-S 一次性交付 full。PE-D-F/S 绑定到同一规划工具的不同配置，PC-F/S 则决定 Planner 保存完整计划与当前编号，还是保存已验证的阶段序列与当前阶段。两轴分开后，可以在相同范围内考察谁控制下一步。见 Q2、P1、P9。

**P9　PE-D-F 和 PE-D-S 共用动态指导的实现。** 已明确用这两个名称。F 修订剩余整项计划；S 在当前子目标结束后给下一份建议。两者都由 Executor 持有整任务，可在相同模型和记忆条件下比较覆盖范围。建议从框架族和 scope 派生唯一的运行标签，调度、清单、轨迹、汇总和阅读器沿用它，避免同一结果被算两次或混到一起。历史 `pe-d` 有全计划要求和固定边界，阅读时注明旧协议；不能直接当作新版 PE-D-F 的测量。见 Q1、P7、P8。

**P10　解析细则延后。** 当前动态解析取第一个匹配块，不检验块顺序、额外键或计划是否覆盖整任务。新接口先明确工具参数、行动方、返回内容与消息去向；重复块、扩展键及旧文本格式的兼容策略按研究者要求在其余部分完善后再审。协议能解析与证据能否支持阶段完成仍需分别验证。见 Q4、P5、P14。

**P11　暂留 `remaining_work`，明确其认识边界。** 运行器持有公开观察、来源、实际交付和动作结果；Planner 维护假设与剩余工作估计。当前两个列表每轮被替换，某项从列表消失可能表示已完成、被推翻或模型遗忘。因此空列表不能触发终止，遗漏也不能删除事实。建议先允许保留、修正或撤销估计，随后再比较它对下一次决策是否有独立作用、与 plan 的重复量和 token 成本。在其他变化稳定前保留该字段，避免同时改动太多因素。见 Q3、P5、P13。

**P12　两个角色需要不同的历史视图。** 完整原始轨迹可回放。Executor 每轮只取当前执行上下文、阶段内近期动作与跨阶段仍有关的事实；PC 的 Planner 读取 Q3 中按 F/S 区分的状态和本次实际动作及反馈。验收时同时检查旧商品价格能否按来源取回、旧页面菜单是否退出，以及阶段刷新后环境是否仍保留先前动作产生的变化。见 Q3、P2、P7。

**P13　`soft_guidance` 是否有独立用途？** 当前日志在 PE-S/PE-D 用它存整份计划，在 PC 用它存可选建议。即便字符串相同，交付职责也不同；对这个字段做统一统计容易误读。待选 **A**：删除独立软提示，PE 的 `plan`、PC 的 `stage_objective` 各只生成、交付和记录一次。**B**：保留可选执行建议，但必须说明与阶段目标、假设、证据均不同的用途，例如两条都满足硬约束的路线之间有一项偏好。建议先选 A；若研究需要控制这种偏好，再引入 B，并承认它改变了 Executor 收到的指导。旧字段继续按历史语义读取。见 P1、P2、P11。

**P14　如何知道 Executor 真的做到了？** 当前 `executor_claims` 取自首个行首 `Action:` 之前的内容，`artifact_refs` 恒为空。PC 单步执行直接返回实际动作与环境观察；阶段验证把这些证据与阶段目标对应，推断标明仍待验证。PE 调用规划工具的理由也仅是请求方的说明。通用协议可先用公开事件与出处，有文件交付的后端再给可读取的版本引用和验收状态。隐藏测试保持隔离。见 P4、P5、P10。

这些选择有四处耦合最强：触发权与阶段范围决定谁还能行动，记忆与字段决定双方能核对什么，格式与验收决定一个建议有多大权限，反馈频率与上下文长度共同决定成本。各组应在同一个反例上检验，再解释框架差异。[当前验收条件](experiments/planner-centered/protocol-design.md#两阶段协议验收)

### Function Tool 的定义与执行绑定

当前工作区使用 `two-phase-v3`。[单次运行状态 `FrameworkRun`](src/toolkit/frameworks/runtime.py) 复用执行会话，显式区分初始规划和后续循环。只有 PE-D 的 Executor 使用 `FunctionTool` 请求在线规划；Planner 通过普通 JSON 交付计划，PC 直接调用 Executor。`tools=[...]` 声明与 `invoke_tool()` 分发共用同一工具定义，不另建工具控制流程。旧数据和既有静态页面原样保留，当前代码只运行及读取 v3；旧控制器、字段回退和旧实验读取／评分回填已删除。重现历史需检出对应源码。[工具绑定](src/toolkit/frameworks/tools.py) · [框架入口](src/toolkit/README.md#四种运行框架) · [请求适配](src/recipe/planner-centered/run.py)

研究者进一步明确了 PE-D 与 PC 的两阶段控制流：先生成初始规划，再进入持续执行与监测。两种框架在第二阶段采用不同的调用机制：PE-D 的 Executor 按需通过原生工具调用请求规划；PC 每个非终局轮固定调用 Executor 一次，不需要模型工具调用。

| 框架 | 第一阶段 | 第二阶段的控制流 |
| --- | --- | --- |
| PE-D | 直接调用 Planner，交付初始规划。范围仍按 F/S 配置。 | Executor 执行任务并观察反馈；调用 `request_plan` 时转入 Planner，工具结果返回后由 Executor 继续执行。 |
| PC | Planner 先完成初始规划。 | 按当前规划直接调用 Executor 执行一步，获取环境反馈；环境未终止时由 Planner 监测并维持或更新规划，再进入下一次执行。 |

此前的工具协议强制 Executor 请求初始计划，并把 PC 初始规划与首步委派合在 `execute_step` 中。这个封装不是 PC 的架构要求。当前两阶段实现已去掉强制求助开场和执行工具：初始 Planner 完成交付后才调用 Executor；PC 后续只在实际反馈之后监测。[两阶段运行流程](src/toolkit/frameworks/runtime.py)

PE-D 收到 `request_plan` 才进入在线规划分支，返回结果与原调用 ID 配对；PC 按固定循环直接推进 Planner 与 Executor。工具对象只负责实际需要的声明与 handler 绑定。消息配对、参数和证据验证、持久环境、上下文、实际动作预算、日志与终局判定继续由运行会话承担。`deliver_plan`、`execute_step` 与 `submit_task` 不再作为模型工具。JSON 交付只增加完成此流程必需的对象解码，P10 的扩展解析策略仍延后。

PC 每个非终局轮必须执行一次 Executor，任务终止与成败依据执行后的环境反馈，不由 Planner 是否调用工具或自行宣告完成决定。预算耗尽和外部故障仍记为运行停止，不能替代环境成功。开放任务由 Executor 经环境提交后独立验收。终局或额度用尽后至多一次只读收尾；失败不抹去已有裁决。先前列出的“PC 不调用工具时如何继续”源于把统一叙述误当作必需的工具接口，已撤回。研究者已授权实施和同一 `dev/2` 六配置实机验收，每组最多 20 个真实环境步；当前代码和离线契约检查对应这一两阶段目标。

新实机的六配置均在 4 个真实环境步后获奖励 1。PE-D-S 在找到、拿起遥控器后分别触发 `request_plan`，结果与调用 ID 配对。初始子计划为定位，随后交付拿取、移动到沙发；Executor 移动后直接完成放置，没有第三次求助。研究者接受这一最终轨迹：Executor 驱动整任务，能够直接完成目标时，无需为阶段形式追加规划。研究者同时明确工具说明暂不修改，不据本例另定通用触发规则或加入阶段门控，也不再将该样本列为待修复缺口。两种 PC 均验证固定单步循环和终局后的唯一只读收尾，无模型工具；PC-F 首次规划超时保留归档，恢复后成功。PE-D-F 只有初始规划，在线复核或修订分支仍未得到实机验收。本次运行不构成成功率、成本优势或学习收益证据。[实机记录](experiments/planner-centered/README.md#两阶段运行协议)

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

上下文与编号实现见[运行实现](src/toolkit/frameworks/runtime.py)，格式约定见 [Planner 模板](src/toolkit/prompts/frameworks.py)。标签可以划分公开判断、规划和动作，但不等同于服务端单独返回的推理内容；本批请求 `reasoning_effort: none` 后用量仍报告非零推理 token，不能据请求值断言实际已关闭。PE-D 求助继续是原生 `tool_calls`，不因普通文本格式选择而改为伪工具命令。

上下文容量管理与自动压缩分开。当前 Toolkit 提供 `context_window.max_input_tokens`，默认 `null`，研究者明确先不设数值。单次 prompt 正文嵌入按时间排列的完整交互；配置上限后，按角色持续淘汰最早的完整单元，不因固定前缀缩短重新补回已淘汰项，必要引用可明确保护。当前任务、计划或阶段、当前观察和正在交接的原生工具消息保留；这些内容本身放不下时记录窗口错误，不发送请求。没有模型摘要，完整原始日志不变。

默认计数是保守的 UTF-8 字节估计，接口允许注入模型 tokenizer；二者不是同一种精度。每请求记录计数方法、保留与淘汰记录、估计输入与服务端返回用量。历史请求的输入重复出现，不能把各次 `total_tokens` 相加作为当前窗口大小。Recipe 的独立字节拒绝已移除。

对照核查了原版 verl-agent 固定提交 `796ed310287fa605c9292a0fce07a86d79fde05e`：默认 `history_length=2`，`SimpleMemory.fetch()` 取最后 K 个完整观察／动作记录，不按字符摘录或生成摘要。ALFWorld 保存的是行动前观察与该动作，新返回的当前观察另列；所以 K=2 表示两个过去观察／动作对再加当前观察。内存保留先前记录，输入只选最近 K 条，只在环境 reset 清空，未按子计划清空。核查依据为本地固定提交源码，对应官方链接：[配置](https://github.com/langfengQ/verl-agent/blob/796ed310287fa605c9292a0fce07a86d79fde05e/verl/trainer/config/ppo_trainer.yaml#L292-L297) · [memory](https://github.com/langfengQ/verl-agent/blob/796ed310287fa605c9292a0fce07a86d79fde05e/agent_system/memory/memory.py#L81-L100) · [ALFWorld 存储与构造](https://github.com/langfengQ/verl-agent/blob/796ed310287fa605c9292a0fce07a86d79fde05e/agent_system/environments/env_manager.py#L147-L208)。本轮远端读取遇连接错误，未声称核验了上游最新版本。

同版本 WebShop 另有带历史完整提示超过 13,000 字符后，当轮切换无历史模板的规则；这不属于 ALFWorld，也不是摘要压缩。[WebShop 源码](https://github.com/langfengQ/verl-agent/blob/796ed310287fa605c9292a0fce07a86d79fde05e/agent_system/environments/env_manager.py#L464-L502)。本地 `verl-agent-system` 修改版固定提交 `d9ba39f88fcd327afca1a9eb701f2a362666842f` 的 ALFWorld 沿用上述窗口，Executor 将格式化观察与 metaplan 拼成一条 user 消息；它与原版分别核查，不能拼成同一个实现结论。本项目 v2 按研究者本轮决定使用完整历史，没有照搬 K=2 窗口或 WebShop 的无历史降级规则。

真实任务要求的一个本地例子是[WebShop 后端检查所用任务](src/toolkit/tests/test_live_backends.py)：要求双频、四核的播放器，价格低于 340 美元。价格上限与功能要求已经在任务原文里；研究者据此决定不保留独立 Hard constraints。运行器、四后端 Recipe 和新清单已移除该字段；旧 WebShop 回放代码已删除，历史产物保留。

PE-D-S 的观察须准确表述为「可一步完成整任务时，Executor 直接行动」，而非「提前看到环境的任务完成标志」。[原始轨迹](experiments/planner-centered/runs/two-phase-magpie-dev2-campus/trials/m5-t2-pe-d-s.json)中，事件 22 只返回沙发场景与当前动作列表，事件 23 是普通单步反馈；事件 24 的公开说明认为放置即可完成任务，随后实际放置。终局反馈到事件 25、26 才出现。原目标持续可见、动作菜单列出了可直接放置的命令、通用执行提示要求完成整任务，都可能影响该选择，单条轨迹不能分离原因。研究者接受本次自主完成的结果形式，并明确保持工具说明原样；记录该现象及理由，不将其视为必须补齐求助的失败，也不扩大为其他情形均无需求助的结论。

PE-D-F 本次只验证了初始规划和正常执行。后续需在公开反馈确实构成重新规划理由的情形中，观察 Executor 是否自主求助，以及 Planner 如何保持或修订整体计划。不能以 PE-D-S 的求助轨迹替代该范围的验收，也不通过强制调用伪造动态触发。补验范围与预算另定，本轮不启动。

### Planner 能力说明与动作接口

规划粒度与动作信息的可见范围分别定义。高层 Planner 负责子目标、前提依赖、取证和路线调整，需要了解 Executor 的能力与约束；知道动作接口本身不使它成为低层策略。原 ALFWorld 与 ScienceWorld 模板直接列出原子命令，并以执行者口吻描述，存在诱导逐动作规划的风险。按研究者要求，当前四环境模板参考本地 `verl-agent-system` 的抽象 global plan 写法，改为子目标、前提和证据要求，删除具体命令指令。动态候选目录只加入 Executor 消息，Planner 接收原始公开观察与已执行动作；职责分离同时落实在提示词和输入构造中。[当前模板](src/toolkit/prompts/alfworld.py) · [规划职责](PROPOSAL.md)

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
