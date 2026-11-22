# Planner–Executor Optimization

个人研究仓库，计划投稿 ICML 2027。当前关注高层 Planner 的战略探索、执行证据支持的低成本评价与策略更新。

[打开研究网站](http://localhost:5173/) · [当前提案](PROPOSAL.md) · [研究工作台](RESEARCH.md) · [研究讨论](DISCUSSION.md) · [历史方案](archive/pre-v04/RESEARCH.md) · [论文](papers/README.md) · [实验](experiments/README.md)

提案的[审核记录](RESEARCH.md#decisions)和[下一步](RESEARCH.md#下一步)见研究工作台。

## 研究设置

```mermaid
flowchart LR
  P["相对小型 Planner · 优化参数"] -->|计划| E["Executor · 冻结"]
  E --> T["环境交互"]
  T -->|训练反馈| P
  E -.->|Planner-Centered 阶段反馈| P
```

提案以 EO、PE-S、PE-D 和 PC 比较外部规划的介入时机与阶段委派权限。各组使用固定 Executor。Planner 优先使用相对小的模型，进入学习阶段后只更新 Planner。跨 Executor 复用保留为后续分析。具体设定见[当前提案](PROPOSAL.md)。

不预设长时程特异性。按[研究判断原则](AGENTS.md#研究判断)定位真实困难、核查近邻与简单基线，再选择优化方法。研究问题不受现有训练基座或奖励实现限制；研究者可以按问题需要搭建新框架，已有实现仅作背景与复用参考。

研究按“工作假设—构建—评价—修正”循环推进，系统与实验也用于完善问题理解。讨论足以指导本轮实现后，可逆设计允许暂定；需要完整训练闭环才能观察的现象，应由相应系统与实验回答。小规模测试用于回答其能覆盖的问题，不代替学习收益与适用范围的评估，当前安排见[研究工作台](RESEARCH.md#research-process)。

本次投稿的核心贡献应落在 Planner 的训练方法、训练信号或学习效率。选题同时考虑截止前完成证据的可行性，导师要求、投稿日期核查与资源条件统一见[投稿筛选约束](RESEARCH.md#submission-constraints)。

## 怎么用

可用[项目 Docker 工作区](src/toolkit/README.md#环境与数据)运行 Python 实验和研究网站；仓库与产物留在宿主机。也可继续使用本机 Conda 和 Node.js。

研究网站的维护范围仅包括 PC 端浏览器。

网站采用“看现状 → 阅读提案 → 查阅历史”的阅读入口：总览展示判断、未知、下一步与提案审核状态；当前提案和配套调研独立阅读；旧题卡、编号对照与证据作为历史材料保留。

`RESEARCH.md` 保存当前状态，`PROPOSAL.md` 保存提案正文，`archive/` 保存历史方案。网站直接读取这些 Markdown，开发时内容变化会自动更新。详细证据就近保存在论文或实验目录，不在网站维护第二份研究状态。

首次安装依赖，再启动网站：

```bash
npm --prefix web ci --include=dev
npm --prefix web run dev
```

浏览 [http://localhost:5173/](http://localhost:5173/)。

<details>
<summary>文档的读者与写法</summary>

| 读者 | 材料 | 写法 |
|---|---|---|
| 智能体 | `AGENTS.md` 与局部指令 | 精简的动作、约束、路径和判断条件，背景用链接 |
| 你 | 概览、README、论文笔记、实验报告、Issue / PR | 先讲判断，再解释依据与限制。图表帮助理解，细节按需展开 |

智能体文档结合 Simple English、Ponytail 和 Stop-that-shit：表达直接，改动完整且精简，守住任务范围与必要保证。

`RESEARCH.md` 同时用于你的阅读与智能体接续，保持一份内容源。简洁不等于省略必要解释，也不能改变证据条件和“可能／建议／必须”的强度。

每次修改都核对所有文档并同步受影响的内容、状态与入口，维护规则见 [AGENTS.md](AGENTS.md#记录与-github)。

</details>

<details>
<summary>默认科研技能如何参与研究</summary>

本项目默认结合 auto-research、Scientific Agent Skills（K-Dense）和 Academic Research Skills（ARS）辅助科研。auto-research 组织研究接续与记录，Scientific Agent Skills 支持科学推理、实验与分析，Academic Research Skills 支持问题界定、文献、写作与评审。具体使用约定见 [默认科研技能](AGENTS.md#默认科研技能)。

可以在阅读、讨论选题、设计、执行、分析、写作或评审时，选择当前需要的模块，也可以组合已授权的步骤。已有材料决定入口，无需从头走完所有阶段。

auto-research 的来源、当前版本与默认技能采用决定记录在 [RESEARCH.md](RESEARCH.md#decisions)。研究判断、论文、实验和 GitHub 任务仍保存在原位置，网站展示同一份 Markdown 内容。

在真实任务中发现流程问题时，记录问题及影响，尝试最小改动。行为改进用同一任务、工具和预算比较基线与候选，保留原有正确行为，再决定是否采用。项目内约定与共享工作流分别维护，改进遵循包内的演化流程与实际授权范围。

人工审核与资源预算沿用既有规则。持续使用工作流不表示已批准所有后续研究，也不表示需要为每次讨论新增流程文档。

</details>

<details>
<summary>网站架构、构建与检查</summary>

网站使用 [React](https://react.dev/)、TypeScript、[Vite](https://vite.dev/guide/) 和 [Ant Design](https://ant.design/components/overview/)。界面采用 [Catppuccin Mocha](https://catppuccin.com/palette/) 深色配色。导航与页面通过 React Router 组织，正文使用 react-markdown、GFM 与 Mermaid 渲染。

| 位置 | 职责 |
|---|---|
| `web/src/content/` | 从仓库 Markdown 读取当前状态、提案与历史题卡，组织文档、图片、实验可视化和搜索 |
| `web/src/App.tsx` | 主题入口与页面路由 |
| `web/src/layouts/`、`web/src/pages/` | 应用布局与研究页面 |
| `web/src/components/Markdown.tsx` | 文档阅读、表格、折叠内容、图和站内链接 |
| `web/src/styles.css` | 阅读排版与响应式布局 |

历史 Dxx 题卡保留原有编号与定位点，不自动列入当前候选。当前内容更新其权威 Markdown，网站不单独保存研究状态。

使用 Node.js 22.12 或更新版本。检查与构建：

```bash
npm --prefix web test
npm --prefix web run build
```

PC 端浏览器检查使用 `npm --prefix web run test:e2e`。需要本机 Chrome 或 Playwright Chromium，可通过 `CHROMIUM_PATH` 指定浏览器。

产物在 `web/dist/`。本地预览构建结果：

```bash
npm --prefix web run preview
```

浏览 [http://localhost:4173/](http://localhost:4173/)。网站通过本地服务阅读，不再依赖直接打开单个 HTML 文件。对外发布另行确定。

</details>

## GitHub 与版本记录

| 入口 | 保存什么 |
|---|---|
| `RESEARCH.md` | 当前判断、提案审核状态、缺口与下一步 |
| `DISCUSSION.md` | 按主题持续更新的讨论、假设与候选对照 |
| `PROPOSAL.md` | 当前关注的提案正文 |
| `archive/` | 历史方案、题卡、证据与决定 |
| Milestone / Issue | 阶段与任务范围、依赖、预算和验收 |
| 分支 / commit / PR | 有范围的变更与个人检查记录 |
| tag / Release | 按需固定复现或投稿版本 |

通过链接关联，不重复维护待办。Issue 关闭或 PR 合并不代表假设成立。日常讨论和小修无需逐项创建任务。

<details>
<summary>版本规则与当前配置</summary>

Codex 创建的分支默认使用 `codex/` 前缀。提交信息用 `<type>(<scope>): <description>`。PR 用 `Refs #编号` 关联任务，全部验收完成后才用 `Closes #编号`。交付与审核的版本追踪使用 Git，具体约定见 [助手规范](AGENTS.md#记录与-github)。

模板：[研究任务](.github/ISSUE_TEMPLATE/research-task.yml)、[PR](.github/pull_request_template.md)。当前尚未配置 Git remote；现有任务卡暂存在研究工作台，建立 Issue 后迁移任务范围与验收。

创建远端任务、提交、推送、创建或合并 PR、发布 tag / Release，按用户明确授权的范围执行。范围内连续推进，无需逐步重复确认。高成本实验仍须预算与授权。助手规范见 [AGENTS.md](AGENTS.md)。

</details>

<details>
<summary>固定边界与已有基础</summary>

主对照固定 Executor 的模型、prompt、工具权限、采样策略和预算规则。实际轨迹与调用次数可以不同，差异须计入成本。改变 Executor 的对照单独报告。

已有基础由研究者提供，代码和结果尚未迁入或核验：

既有研究关注 planning hallucination、error accumulation、reward shaping 和 credit assignment。

| 内容 | 起始基础 |
|---|---|
| 架构 | Planner 一次生成 full-plan，固定 Executor 执行 |
| 训练 | 已探索 SFT→GRPO，奖励含 `r_exec` 与 `r_fmt`；研究者确认 `r_exec` 只按任务完成结果计算，不包含 ECGR 或有／无计划比较，原讨论见[历史 D03](archive/pre-v04/RESEARCH.md#d03) |
| 技术栈 | VeRL、verl-agent、vLLM |
| 环境 | ALFWorld、SciWorld、WebShop |
| 资源偏好 | 优先 1.5B～13B；实际硬件与预算在实验前核对 |

这些基础本身不构成新贡献。工具、memory、reflection 和重规划按问题需要引入。

本仓库计划保持 Private。对外分享和公开代码的范围由研究者决定。

</details>
