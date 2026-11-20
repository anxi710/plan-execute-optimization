# 研究工作台

更新：2026-11-20 · 阶段：提案 v0.5 通过审核 · [研究网站](http://localhost:5173/)

## 当前判断

当前研究聚焦高层 Planner 的战略探索、执行证据支持的低成本评价与策略更新。已通过审核的[提案 v0.5](PROPOSAL.md)按 EO、PE-S、PE-D 和 PC 定义框架对照。

四种框架通过一次真实模型接口复验。EO 无外部规划，PE-S 首步前交付一次，PE-D 续接同一个整项任务请求，PC 随反馈发出新的阶段委派。四组均在四步后通过同一 ALFWorld 开发任务。该样本确认控制流；完整测试集结果和待人工核验的轨迹见实验记录。[轨迹与源码](experiments/planner-centered/README.md)

<details id="judgment-context">
<summary>方向切换与历史方案</summary>

2026-11-12，研究者将 v0.4 列为当前关注提案，留待后续审核。原 D03、D05 及其他题卡随[历史研究方案](archive/pre-v04/RESEARCH.md)归档。旧方案的候选优先级与下一步指归档时的安排。原证据、未决项和历史决定随题卡保留。

</details>

## 最大未知

候选是否缺少有价值的战略差异、什么执行证据足以支持低成本评价，以及反馈能否改善 Planner 学习，仍是待验证的问题。

<details id="unknown-context">
<summary>尚未确定的设计与证据</summary>

规划表示、内部形成过程、评价方法和更新算法尚未选定。多轮形成、经验检索、元规划库、树搜索和条件转换图均不因方向切换成为必需组件。四框架评测的后端、返回协议和预算已记录在[实验实现](src/recipe/planner-centered/README.md)，后续机制对照与训练设计仍待确定。

首轮 ALFWorld 诊断确认了一个独立采样漏掉可行路线的案例。该路线由固定 Executor 三次执行成功，与独立采样代表路线的步数相同。发生频率、跨任务和模型的适用范围仍待验证。[采样诊断](experiments/strategy-sampling/README.md)

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
