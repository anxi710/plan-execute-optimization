# 研究工作台

更新：2026-11-22 · 阶段：提案 v0.5 通过审核 · [研究网站](http://localhost:5173/)

## 当前判断

当前研究聚焦高层 Planner 的战略探索、执行证据支持的低成本评价与策略更新。已通过审核的[提案 v0.5](PROPOSAL.md)按 EO、PE-S、PE-D 和 PC 定义框架对照。

四种框架通过一次真实模型接口复验。EO 无外部规划，PE-S 首步前交付一次，PE-D 续接同一个整项任务请求，PC 随反馈发出新的阶段委派。四组均在四步后通过同一 ALFWorld 开发任务。该样本确认控制流；完整测试集结果和待人工核验的轨迹见实验记录。[轨迹与源码](experiments/planner-centered/README.md)

当前工作区的模型输入只构造任务上下文。日志元数据及执行额度等运行器技术限制不告知模型，运行器继续执行和记录这些限制。Planner 模板已改为高层子目标与证据要求，Executor 的候选动作改由环境接口提供；候选目录与 Planner 原始观察分开。源码、离线请求及已保存实机请求确认列表在运行时动态加入；旧正式 EO 轨迹的一次抽样则未附列表。这些协议修改未重跑旧实验，对既有比较的影响尚未核验；历史原始 prompt 与结果保留。[输入核查与抽样限制](DISCUSSION.md#planner-能力说明与动作接口)

当前实现使用 `two-phase-v2`：保留直接初始规划、PE-D 原生按需求助、PC 固定单步执行与反馈监测的两阶段控制流，恢复完整交互历史，独立连续编号观察，去重 ALFWorld 初始目标，拆分 PE-S／PE-D 提示，精简已完成阶段输入，并删除独立 Hard constraints 字段及注入。任务原文要求保留。Planner 普通 JSON 与 `thinking_summary` 暂时保留，标签表示仍在讨论；工具说明和动作接口不变，尚未引入独立阶段 verifier。Python 核心固定于本地提交 `6afb80e`，本轮不调用模型。[当前实现](src/toolkit/README.md#四种运行框架)

此前 `two-phase-v1` 在同一 `dev/2` 的六配置均于 4 个真实环境步后获奖励 1，上限为每组 20 步；PE-D-S 实际触发两次在线求助，两种 PC 验证了无工具的固定循环。研究者接受 PE-D-S 最后直接完成放置、未再求助的轨迹形式；工具说明暂不修改，不将其列为待修复缺口。实际 ALFWorld 为 `plan-test` 中的 0.3.5，区别于更早批次的 0.4.2。旧原始请求和评分不改写，也不能作为 v2 输入改动的实机证据。P10 扩展解析策略继续延后。[实机结果与完整轨迹](experiments/planner-centered/README.md#两阶段运行协议)

研究者已决定删除独立约束字段，并撤回按引用截取历史、按阶段保留最近两轮的输入方案。当前恢复完整历史，但现有 Recipe 请求体字节预算仍生效；统一到 Toolkit 维护上下文预算、如何应对超限及是否引入压缩仍是待讨论方案。PE-D-F 尚无在线求助的实机证据。所有当前未审事项已汇总为[全面审核清单](DISCUSSION.md#全面审核清单)，区分人工验收、设计选择和待检验问题；已确认或撤回的方案不重新列为待决。

ALFWorld 的当前候选菜单既填入实体参数，也依环境状态筛选，超出命令语法帮助。研究者决定暂时保留该 action prompt；降低接口失败与补偿任务状态判断的作用尚未分离，不能仅解释为规划评价降噪。候选辅助与风险继续作为解释实验结果的条件，本轮未改变动作接口或启动接口对照实验。[参数与状态筛选的评价边界](DISCUSSION.md#参数实例化状态筛选与-planner-评价)

旧 `native-tools-v1` 及更早四配置的原始轨迹、提示和评分保留，可继续读取和导出；当前运行器拒绝续跑旧工具协议，避免把新流程保存成旧版本。旧四配置的显式 legacy 路径仍可运行。[协议与历史记录](src/recipe/planner-centered/README.md)

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

ALFWorld 的 134 个官方测试任务已跑完四模型、四框架的 2,144 个组合。定向补回 110 条外部故障缺评后，全部组合均有原生评分，134 个任务均可进行全配置比较。Terminal-Bench 在 167 条有效评分均为零后按研究者决定终止，已有轨迹供人工核验。WebShop 和 ScienceWorld 已停止，已有评分用于同任务比较。[正式验收](experiments/planner-centered/audit.html) · [四套同任务比较](experiments/planner-centered/audit-preview.html) · [实验记录](experiments/planner-centered/README.md)

<details id="next-context">
<summary>原型推进方式</summary>

研究继续采用“工作假设—构建—评价—修正”。讨论足以指导一轮实现后，可以用原型和实验回答未决的经验问题，不要求先证明所有组件独立有效。

</details>

<details id="current-proposal" open>
<summary>当前提案与阅读材料</summary>

- [当前研究提案 v0.5 · 高层规划器优化](PROPOSAL.md)
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

API 内置推理开关、显式思考文本和框架公开判断分开定义；文本是否参与参数更新须核对实际生成与训练 mask，不能由字段名或标签判断。[接口文档与 RAGEN 核查边界](DISCUSSION.md#模型内置推理与显式思考)

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
| 旧研究方案 | 保存于 archive/pre-v04/RESEARCH.md，保留原题卡、证据和决定；不再作为当前计划。 |
| 首轮采样诊断 | 研究者授权使用 DeepSeek 开展首轮采样诊断。 |
| 四框架接口验收 | 2026-11-19 研究者授权使用同济 API。真实接口验收完成，[HTML 与源码](experiments/planner-centered/README.md)待研究者审核。 |

此前的分组、编号、归并与审核决定保存在[历史决定](archive/pre-v04/RESEARCH.md#decisions)。固定研究约束与操作规则仍见 [README](README.md) 和 [AGENTS](AGENTS.md)，不复制为另一套状态。

工作流来源（相对本仓库根目录）：`../auto-research/skills/research-workflow/SKILL.md`。2026-11-12 重新读取，元数据版本仍为 `0.1.11-synthesis.3`；旧采用记录见[存档](archive/pre-v04/RESEARCH.md#decisions)。人工审核与范围判断使用同包 `references/human-review.md`。来源为本地文件，持续使用工作流不豁免提案审核。

</details>
