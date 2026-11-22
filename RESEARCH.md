# 研究工作台

更新：2026-11-23 · 阶段：新实验实现准备，提案 v0.6 待审核 · [研究网站](http://localhost:5173/)

## 当前判断

当前准备独立的 `planner-centered-v2` 未训练框架性能测试，尚未启动模型测试或训练。现行协议为 `two-phase-v3`，实现与环境检查通过，提案 v0.6 待审核。旧实验数据保留，当前代码无需兼容。

<details id="implementation-context">
<summary>当前架构、实现与环境检查</summary>

当前长期研究仍关注高层 Planner 的战略探索、执行证据支持的评价与策略更新。本轮先独立测试未经本项目专项训练的模型在不同框架下的任务表现和成本，不开展训练，不以架构测试推断学习收益。[提案 v0.6](PROPOSAL.md)已按最新架构修订，原 v0.5 审核保留，新正文待审核。

研究者决定新建 [planner-centered-v2](experiments/planner-centered-v2/README.md)，不从旧实验导入成绩。旧实验的原始请求、评分、报告和源码证据保留；当前代码删除旧控制器、旧字段回退、旧轨迹读取、历史评分回填和跨运行融合。重现旧实验须检出其对应源码，不由当前入口续跑。

当前框架协议为 `two-phase-v3`，实验名称的 v2 与协议版本分别记录。非 EO 先直接生成初始规划；PE-D 由 Executor 原生调用 `request_plan` 按需求助；PC 固定执行一步、读取环境反馈、再由 Planner 监测。任务完成依据环境反馈。研究者接受 PE-D-S 在可直接完成任务时自主行动，工具说明保持原样，不加阶段门控。[运行实现](src/toolkit/README.md#四种运行框架)

完整交互历史嵌入单次 prompt 正文。Toolkit 提供可配置输入 token 窗口，超限时丢弃最早的完整交互，保留当前任务、有效规划、当前观察和必要工具配对；完整日志不裁剪，没有自动压缩。研究者要求先不设数值，`max_input_tokens` 默认为 `null`。默认计数为明确标记的保守 UTF-8 估计，服务端用量单独记录，不将历次重复输入相加作为窗口占用。[上下文实现](src/toolkit/models/context.py)

Planner JSON 中的 `assessment` 表示当前可见状态或阶段判断，替换易误导的旧字段名，不是隐藏推理的总结，也不裁定任务成功。计划内部继续使用 JSON；标签表示仍待讨论。独立 Hard constraints、字符摘录和 Recent interactions 重复块已移除。观察从 1 连续编号，初始任务目标去重，PE-S 与 PE-D 提示分开，verified 阶段只回送必要已验证信息；尚未引入独立阶段语义 verifier。

ALFWorld 的当前候选菜单已经填入实体参数并按环境状态筛选。研究者决定保留该 action prompt，Planner 不获取该动态目录。其降低接口错误与补充状态信息的作用尚未分离，作为设置条件记录，不在本轮修改。[动作接口边界](DISCUSSION.md#参数实例化状态筛选与-planner-评价)

本轮已将 `plan-test` 对齐主 requirements 的固定版本：ALFWorld 0.4.2、TextWorld 1.7.0、ScienceWorld 1.2.3、OpenAI SDK 3.20.0、PyYAML 6.0.1。ALFWorld 重载及真实动作检查通过，不调用模型。原 Hugging Face 版本冲突已通过将 hub 调整为 1.33.0 修复；TextWorld 官方 wheel 标签格式已修复，程序及数据未变。全环境 `pip check` 与相关包导入复查通过。[依赖与检查边界](experiments/planner-centered-v2/README.md#环境与依赖)

Recipe 已配置 Magpie 官方原生透传入口，模型名使用上游名称。该路径减少普通网关转换，隐私遮蔽配置仍可能改写正文。尚未进行新模型调用，旧的非零推理 token 是否由网关包装造成仍未证实。[透传核查](DISCUSSION.md#模型内置推理与显式思考)

</details>

<details id="judgment-context">
<summary>方向切换与历史方案</summary>

2026-11-12，研究者将 v0.4 列为当前关注提案，留待后续审核。原 D03、D05 及其他题卡随[历史研究方案](archive/pre-v04/RESEARCH.md)归档。旧方案的候选优先级与下一步指归档时的安排。原证据、未决项和历史决定随题卡保留。

</details>

## 最大未知

候选是否缺少有价值的战略差异、什么执行证据足以支持低成本评价，以及反馈能否改善 Planner 学习，仍是待验证的问题。

<details id="unknown-context">
<summary>尚未确定的设计与证据</summary>

规划表示、内部形成过程、评价方法和更新算法尚未选定。多轮形成、经验检索、元规划库、树搜索和条件转换图均不因方向切换成为必需组件。四种基础运行框架由 [`toolkit.frameworks`](src/toolkit/README.md#四种运行框架) 提供，与固定计划评估共用 [`toolkit.rollout` 的执行与采样组件](src/toolkit/README.md#执行与采样的组合)；本轮评测的后端装配与预算见 [Recipe](src/recipe/planner-centered/README.md)，后续机制对照与训练设计仍待确定。

首轮 ALFWorld 诊断确认了一个独立采样漏掉可行路线的案例。该路线由固定 Executor 三次执行成功，与独立采样代表路线的步数相同。发生频率、跨任务和模型的适用范围仍待验证。[采样诊断](experiments/strategy-sampling/README.md)

旧 `native-tools-v1` 的六配置经 Magpie 调用 `tongji/DeepSeek-V4.1-Flash`，分别从同一 ALFWorld `dev/2` 初态完成任务，原生奖励均为 1。两种 PC 均逐步监控并走过阶段切换，当时实机的 PE-D 只观察到初次规划；PE-D-S 的补验确认收紧提示后首份交付聚焦一个子目标。旧协议证据与当前两阶段验收分别保留。单任务运行用于验收接口与行为；框架成功率、成本优势及学习收益仍需独立评估。[实施方案](experiments/planner-centered/protocol-design.md) · [旧协议实机验收](experiments/planner-centered/README.md#六配置原生工具协议) · [18 项讨论](DISCUSSION.md#规划覆盖范围与控制权)

</details>

## 下一步

先审核新提案与实验设置，再冻结模型、任务、重复次数和预算。PE-D-F 自主求助仍待实机验收。[剩余审核项](DISCUSSION.md#全面审核清单)

<details id="experiment-context">
<summary>新实验设置与历史证据</summary>

先审核新提案及[新实验设置](experiments/planner-centered-v2/README.md)，在启动模型测试前冻结任务、模型矩阵、重复次数、执行与调度预算。当前仅完成代码、离线检查和无模型环境检查，没有新实验成绩，也未自动沿用旧运行授权。PE-D-F 自主求助仍需在合适任务中验收。[剩余审核项](DISCUSSION.md#全面审核清单)

旧实验的 ALFWorld 四模型四框架 2,144 个组合已保存原生评分；其他环境的停止决定和既有成绩保留在[旧实验记录](experiments/planner-centered/README.md)，不作为当前待启动运行。

</details>

<details id="next-context">
<summary>原型推进方式</summary>

研究继续采用“工作假设—构建—评价—修正”。讨论足以指导一轮实现后，可以用原型和实验回答未决的经验问题，不要求先证明所有组件独立有效。

</details>

<details id="current-proposal" open>
<summary>当前提案与阅读材料</summary>

- [当前研究提案 v0.6 · 待审核](PROPOSAL.md)
- [Full-plan 优化文献调研](papers/fullplan-optimization-review.md)：一次规划的形成过程、学习近邻与证据筛选。
- [Planner-Centered 架构调研](papers/planner-centered-review.md)：在线闭环的架构先例、状态语义与未决优化对象。
- [历史研究方案](archive/pre-v04/RESEARCH.md)：切换前的完整题卡、来源、草案和决定，仅作历史参考。

</details>

<details id="evidence">
<summary>证据状态</summary>

两份专题调研记录了论文与官方代码的核查范围及限制。已有文献与历史证据分别见[论文索引](papers/README.md)和[原来源索引](archive/pre-v04/RESEARCH.md#direction-sources)。

[同任务的高层战略采样](experiments/strategy-sampling/README.md)保留结果、标注和原始执行轨迹。可运行的代码与协议见[战略采样 Recipe](src/recipe/strategy-sampling/README.md)。

</details>

<details id="research-process">
<summary>研究推进方式</summary>

研究聚焦高层规划的战略探索、执行证据支持的低成本评价与策略更新。主对照固定 Executor；跨 Executor 复用只保留为后续分析。具体机制由讨论、构建和评价逐步确定，不要求三个环节同时创新，也不提前限定 RL 算法。

规划覆盖范围与形成过程的调用次数分别定义。高层规划不等于低层动作清单，也不因“脚本”类比固定为代码表示。[研究讨论](DISCUSSION.md)持续整理未确认的解释、假设和候选对照，与本工作台的已确认判断分开。

API 内置推理开关、显式思考文本和框架状态判断分开定义；文本是否参与参数更新须核对实际生成与训练 mask，不能由字段名或标签判断。[接口文档与 RAGEN 核查边界](DISCUSSION.md#模型内置推理与显式思考)

执行与证据要求沿用 [AGENTS.md](AGENTS.md#研究判断)。

</details>

<details id="submission-constraints">
<summary>投稿目标与已有资源背景</summary>

投稿目标仍为 ICML 2027，优化贡献应落在 Planner 的训练方法、训练信号或学习效率。正式截止日期尚未在本项目核实，旧方案的工期情景不自动成为新提案排期。

研究者提供的资源规划基准为 NVIDIA L40 PCIe / 48GB，优先探索 1.5B–13B 模型。实际卡数、可用时长、基线训练耗时仍需核对；既有训练栈与实验背景不等于本仓库已复现结果。[原始记录与限制](archive/pre-v04/RESEARCH.md#submission-constraints)保留供接续使用。

</details>

<details id="decisions">
<summary>当前决定与历史入口</summary>

| 事项 | 状态与依据 |
|---|---|
| 项目关注方向 | 2026-11-12 研究者明确要求转向 PROPOSAL.md 中的新提案。 |
| v0.4 内容审核 | 2026-11-17，研究者在 Codex 对话中同意将 v0.4 列为通过审核。审核对应 2026-11-11 的正文修订，见 `0076b55:PROPOSAL.md`。 |
| v0.5 内容审核 | 2026-11-18，研究者在 Codex 对话中批准 2026-11-18 修订的 [PROPOSAL.md](PROPOSAL.md)，范围包括四种框架的正文、总览图与四张详图。审核对应未提交的工作区版本。 |
| 新实验与 v0.6 | 研究者明确要求启动独立的 planner-centered-v2，先测试未经专项训练的框架表现；已授权同步提案、实现与记录。v0.6 正文为本轮工作区修改，待审核。 |
| 当前兼容边界 | 研究者明确要求删除现有代码面向旧实验的兼容逻辑，保留历史数据；当前运行与导出仅支持 two-phase-v3。 |
| 环境与上下文 | 采用 ALFWorld 0.4.2 和主 requirements 固定依赖；输入 token 窗口可配置，默认 null，不新增压缩。 |
| 旧研究方案 | 保存于 archive/pre-v04/RESEARCH.md，保留原题卡、证据和决定；不再作为当前计划。 |
| 首轮采样诊断 | 研究者授权使用 DeepSeek 开展首轮采样诊断。 |
| 四框架接口验收 | 2026-11-19 研究者授权使用同济 API。真实接口验收完成，[HTML 与源码](experiments/planner-centered/README.md)待研究者审核。 |

此前的分组、编号、归并与审核决定保存在[历史决定](archive/pre-v04/RESEARCH.md#decisions)。固定研究约束与操作规则仍见 [README](README.md) 和 [AGENTS](AGENTS.md)，不复制为另一套状态。

工作流来源（相对本仓库根目录）：`../auto-research/skills/research-workflow/SKILL.md`。本轮核对，元数据版本仍为 `0.1.11-synthesis.3`；旧采用记录见[存档](archive/pre-v04/RESEARCH.md#decisions)。人工审核与范围判断使用同包 `references/human-review.md`。来源为本地文件，持续使用工作流不豁免提案审核。

</details>
