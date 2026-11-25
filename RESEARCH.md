# 研究工作台

更新：2026-11-25 · 阶段：未经专项训练的框架测试，提案 v0.6 待审核 · [研究网站](http://localhost:5173/)

## 当前判断

`planner-centered-v2` 的 Qwen Planner／DeepSeek Executor 完整 ALFWorld test 六架构测试（804 条）已于 2026-11-23 15:01:26（北京时间）结束：465 条有有效原生评分，339 条缺评，其中 333 条协议终止、6 条外部故障。配额修复后的恢复按原预算完成，首轮有效评分与协议缺评未重采。最终异常审查页已生成，使用[独立静态入口](http://127.0.0.1:4176/failure-review.html)；大量且不均衡的协议缺评限制架构性能比较。[完整结果与口径](experiments/planner-centered-v2/README.md#完整测试结果与最终异常审查) · 尚未训练，提案 v0.6 待审核。

六目录更新后的 `test/1`（清洗 bowl 后放入 cabinet）02 六配置复验已于 2026-11-25 18:33:12（北京时间）完成：EO、PE-S、PE-D-F、PE-D-S 成功，两种 PC 在第 2 个环境步后的 Planner 回复以 Markdown 围栏包装 JSON，被解析拒绝而缺评。共 49 个真实步、58 次请求和 63,107 token，无重采。实际 58 份请求均核对了对应六目录模块与 Full/sub 文案；两种 PE-D 均未发起在线求助，弃用目标分支未触发。模型仍为 Qwen Planner／DeepSeek Executor，每组最多 20 个真实步、并发 1；只供实际 prompt 与轨迹审核，不据此证明提示收益或架构性能。[本轮完整轨迹页](http://127.0.0.1:4178/alfworld.html#/?tab=read&left=m1-t1-pe-d-s) · [设置与结果](experiments/planner-centered-v2/README.md#六配置独立目录更新后的复验)

PE-D 的 `Thought` 与原生工具调用可以同时出现；已观察的异常是文字表示准备执行，实际却重复请求规划。本地调用链没有强制工具选择或把 Thought 改写成调用。按研究者要求，当前工作区已统一为单轮环境行动／规划求助二选一，并按六种配置、再按 benchmark 保存完整文案，Full/sub 在目录层面分开；不再叠加基础 Action 要求与后置求助例外。当前单任务复验用于检查实际组装，不能据此确认旧行为的原因或架构性能收益。[提示词组织](src/toolkit/README.md#统一提示词) · [接口与解释边界](DISCUSSION.md#当前协议拒绝与规划能力的区分)

研究者接受单个 JSON 对象的外层 Markdown 代码围栏，不要求仅因该包装终止任务。建议仅移除外层围栏，再执行原有字段、阶段和证据校验；运行可解析性与未来格式偏好分开，若引入 format reward，应按保留的原始回复评价。目前解析器尚未放宽，本轮讨论未改代码或重采，训练奖励设计仍未确定，旧协议缺评不回改。[讨论与边界](DISCUSSION.md#当前协议拒绝与规划能力的区分)

<details id="implementation-context">
<summary>当前架构、实现与环境检查</summary>

当前长期研究仍关注高层 Planner 的战略探索、执行证据支持的评价与策略更新。本轮先独立测试未经本项目专项训练的模型在不同框架下的任务表现和成本，不开展训练，不以架构测试推断学习收益。[提案 v0.6](PROPOSAL.md)已按最新架构修订，原 v0.5 审核保留，新正文待审核。

研究者决定新建 [planner-centered-v2](experiments/planner-centered-v2/README.md)，不从旧实验导入成绩。旧实验的原始请求、评分、报告和源码证据保留；当前代码删除旧控制器、旧字段回退、旧轨迹读取、历史评分回填和跨运行融合。重现旧实验须检出其对应源码，不由当前入口续跑。

当前框架协议为 `two-phase-v3`，实验名称的 v2 与协议版本分别记录。非 EO 先直接生成初始规划；PE-D 由 Executor 原生调用 `request_plan` 按需求助；PC 固定执行一步、读取环境反馈、再由 Planner 监测。任务完成依据环境反馈。研究者接受 PE-D-S 在可直接完成任务时自主行动，工具说明保持原样，不加阶段门控。[运行实现](src/toolkit/README.md#四种运行框架)

当前 Planner 的领域角色直接写入各配置的 benchmark 模块：ALFWorld 为 `household`、SciWorld 为 `scientific`、WebShop 为 `shopping`；Terminal-Bench 保留已有说明。框架按实际 `mode` 与 benchmark 加载唯一模块，不再通过中央模板插值。已完成 run02 使用当时的 benchmark 名称插值，其冻结源码与原始轨迹保留，不回改提示或成绩。[加载入口](src/toolkit/prompts/loader.py) · [目录与字段](src/toolkit/README.md#统一提示词)

初始规划和持续监测的英文阶段标题已从当前 Planner 输入移除，保留各次请求所需的任务说明与格式要求。两阶段控制流不变，阶段标识仅写入轨迹日志；已完成实验仍以当时冻结提示为准。

PC 提示词按 full/sub 分别放在 `pc_f/` 与 `pc_s/`，每份 benchmark 模块各有 initial/monitor 文案，运行器每次选择一份，另附该模块的格式说明与 Schema。Monitor 已按维持、完成推进和弃用重规划整合：有证据表明当前目标无法推进时，Full 重规划剩余目标，Sub 给出新目标；被舍弃的旧目标定义原样记入轨迹，不能视为已完成。已保留研究者对 ALFWorld、PE 与 Executor 文案的手动删减，PC 四份初始／监测文案仅迁移；PC 文案继续待研究者审核。此前 `test/1` 未触发弃用分支。[Full 模板](src/toolkit/prompts/pc_f/alfworld.py) · [Sub 模板](src/toolkit/prompts/pc_s/alfworld.py)

当前工作区已取消终局后的 Planner 自动复核：环境明确终止或真实步数预算耗尽后直接记录结果，中间奖励不单独触发停止。不预设 Executor 输出完成声明，不提取独立声明字段，也不按自然语言关键词判停；任务成败由环境已定义的反馈或提交验收确定。run02 与开发验收原有的收尾调用及成本保留，改动只影响后续运行。[终止边界](src/toolkit/README.md#四种运行框架)

完整交互历史嵌入单次 prompt 正文。Toolkit 提供可配置输入 token 窗口，超限时丢弃最早的完整交互，保留当前任务、有效规划、当前观察和必要工具配对；完整日志不裁剪，没有自动压缩。研究者要求先不设数值，`max_input_tokens` 默认为 `null`。默认计数为明确标记的保守 UTF-8 估计，服务端用量单独记录，不将历次重复输入相加作为窗口占用。[上下文实现](src/toolkit/models/context.py)

Planner JSON 中的 `assessment` 表示当前可见状态或阶段判断，替换易误导的旧字段名，不是隐藏推理的总结，也不裁定任务成功。计划内部继续使用 JSON；标签表示仍待讨论。独立 Hard constraints、字符摘录和 Recent interactions 重复块已移除。观察从 1 连续编号，初始任务目标去重，PE-S 与 PE-D 提示分开，verified 阶段只回送必要已验证信息；尚未引入独立阶段语义 verifier。

实机审阅后，研究者授权明确 PC-F 的 `revision_reason` 同一 JSON 字段要求，并将两角色 prompt 的完整可见历史前移、本轮规则和当前计划状态后置。代码的计划变化判定范围暂不改变；历史是否导致 PE-D-S 减少求助尚无因果证据。已按授权以同任务、同模型和六配置各最多 20 个真实步完成第二轮采样，六组均成功，PE-D 求助未增加；01 原轨迹保留。提示实现现见提交 `0d8dac2`。02 实际运行源码仍以 `1972b47` 和当时保存的补丁为准。[修订与再采样记录](experiments/planner-centered-v2/README.md#本轮单任务实机验收)

研究者已授权一轮完整 ALFWorld test 六架构评测：134 游戏 × 6，共 804 条；确认 Planner 为 `Qwen3.8-27B`、Executor 为 `DeepSeek-V4.1-Flash`。沿用每条 20 个真实步、并发 4、共享 100 请求／分钟，使用独立配置、持久隔离源码副本与新运行目录；用户要求删除刚才的旧完整运行后从零重启，旧轮不混入新成绩；[本轮固定协议](experiments/planner-centered-v2/README.md#完整测试集评测qwen-planner-与-deepseek-executor)在启动前记录，训练未获授权。

完整测试 run02 的首轮配额异常是在复制 32,534,448 字节 `libdownward.so` 时出现 `OSError: [Errno 122] Disk quota exceeded`，对应 `/tmp` 的用户配额。无模型复现确认：原实现每条任务新开 TextWorld 后端，已删除的 native 库仍被进程持有，12 次加载累积 12 份；改为一个显式 `pool.reuse_slots()` 作用域，在 4 个独占 slot 上重载 12 轮共 48 次，库副本恒为 4。作用域结束会关闭后端，但不声称上游已卸载 native 库。修复不改模型、prompt、动作接口、评分或预算。[诊断产物与恢复边界](experiments/planner-centered-v2/README.md#run02-quota-中断与恢复)

首轮 75 条协议缺评已按原始输出逐条核查。已确认包括代码围栏、JSON Schema 外壳、第二次连续求助前的运行器上限、`keep` 与同值计划并存的拒绝，以及 `verified` 状态与阶段切换的结构校验；后者并非独立语义 verifier。本轮恢复保持既有输入和协议，最终协议缺评累计 333 条；首轮机制核查不等于逐条核实了全部最终样本，统计不能直接解释为高层规划能力失败。[首轮分布与边界](experiments/planner-centered-v2/README.md#首轮-75-条协议缺评核查) · [最终异常轨迹查看页](experiments/planner-centered-v2/runs/alfworld-test-qwen38-27b-deepseek-02/failure-review.html)

ALFWorld 的当前候选菜单已经填入实体参数并按环境状态筛选。研究者决定保留该 action prompt，Planner 不获取该动态目录。其降低接口错误与补充状态信息的作用尚未分离，作为设置条件记录，不在本轮修改。[动作接口边界](DISCUSSION.md#参数实例化状态筛选与-planner-评价)

本轮已将 `plan-test` 对齐主 requirements 的固定版本：ALFWorld 0.4.2、TextWorld 1.7.0、ScienceWorld 1.2.3、OpenAI SDK 3.20.0、PyYAML 6.0.1。ALFWorld 重载及真实动作检查通过；随后从 `main` 完成一次真实模型的六配置单任务验收。原 Hugging Face 版本冲突已通过将 hub 调整为 1.33.0 修复；TextWorld 官方 wheel 标签格式已修复，程序及数据未变。全环境 `pip check` 与相关包导入复查通过。[依赖与检查边界](experiments/planner-centered-v2/README.md#环境与依赖)

Recipe 已配置 Magpie 官方原生透传入口，模型名使用上游名称。该路径减少普通网关转换，隐私遮蔽配置仍可能改写正文。两轮有用量的响应均显式报告推理 token 为 0，EO 的一次故障请求用量未知，旧异常是否由网关包装造成仍未证实。[透传核查](DISCUSSION.md#模型内置推理与显式思考)

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

使用[本轮 test/1 02 完整轨迹页](http://127.0.0.1:4178/alfworld.html#/?tab=read&left=m1-t1-pe-d-s)审核六目录提示词的实际组装、PE-D 的独立行动及 PC 的 JSON 拒绝。采样服务已正常退出；页面由 `planner-alfworld-prompts-review-4178.service` 独立静态服务提供。旧单任务轨迹和完整矩阵全部 1,417 次尝试保持原样；在线求助往返与弃用目标分支本轮未覆盖。后续修改或重采待研究者指示。[设置、结果与原始产物](experiments/planner-centered-v2/README.md#六配置独立目录更新后的复验) · [剩余审核项](DISCUSSION.md#全面审核清单)

<details id="experiment-context">
<summary>新实验设置与历史证据</summary>

两轮单任务六配置验收均已完成：[首次](experiments/planner-centered-v2/README.md#本轮单任务实机验收)五组成功、PC-F 协议缺评，提示修订后的第二轮六组成功，原始轨迹待审核。两轮开发验收均未触发 PE-D 在线求助，该分支需结合完整测试进一步检查。当前完整矩阵的任务、模型、次数与预算已冻结并获授权；提案 v0.6 审核仍待研究者决定。[固定设置与恢复边界](experiments/planner-centered-v2/README.md#完整测试集评测qwen-planner-与-deepseek-executor) · [剩余审核项](DISCUSSION.md#全面审核清单)

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
| 新实验与 v0.6 | 研究者明确要求启动独立的 planner-centered-v2，先测试未经专项训练的框架表现；已授权同步提案、实现与记录。v0.6 正文固定于本地提交 `6f531c6`，待审核。 |
| 当前兼容边界 | 研究者明确要求删除现有代码面向旧实验的兼容逻辑，保留历史数据；当前运行与导出仅支持 two-phase-v3。 |
| 环境与上下文 | 采用 ALFWorld 0.4.2 和主 requirements 固定依赖；输入 token 窗口可配置，默认 null，不新增压缩。 |
| 旧研究方案 | 保存于 archive/pre-v04/RESEARCH.md，保留原题卡、证据和决定；不再作为当前计划。 |
| 首轮采样诊断 | 研究者授权使用 DeepSeek 开展首轮采样诊断。 |
| 提示重排与再采样 | 研究者明确授权先明确 revision_reason 的 JSON 字段要求，再将两角色历史前移、指导后置，并重采样同任务六配置。第二轮均 4 步成功，EO 单独恢复一次；原轨迹不改写，修改后的计划理由分支与 PE-D 在线求助仍未在第二轮触发。 |
| 本轮 v3 单任务验收 | 研究者授权先提交并合并本地 main，再运行一个真实 ALFWorld 任务。六配置各最多 20 步，五组原生成功，PC-F 因缺少修订原因缺评；完整原始轨迹保留，未补跑，待研究者审核。 |
| 四框架接口验收 | 2026-11-19 研究者授权使用同济 API。真实接口验收完成，[HTML 与源码](experiments/planner-centered/README.md)待研究者审核。 |

此前的分组、编号、归并与审核决定保存在[历史决定](archive/pre-v04/RESEARCH.md#decisions)。固定研究约束与操作规则仍见 [README](README.md) 和 [AGENTS](AGENTS.md)，不复制为另一套状态。

工作流来源（相对本仓库根目录）：`../auto-research/skills/research-workflow/SKILL.md`。本轮核对，元数据版本仍为 `0.1.11-synthesis.3`；旧采用记录见[存档](archive/pre-v04/RESEARCH.md#decisions)。人工审核与范围判断使用同包 `references/human-review.md`。来源为本地文件，持续使用工作流不豁免提案审核。

</details>
