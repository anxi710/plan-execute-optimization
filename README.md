# Planner–Executor Optimization

个人研究仓库。以 ICML 为目标，研究冻结 Executor 时如何有效优化 Planner。投稿年份待定。

[打开研究网站](http://localhost:5173/) · [研究工作台](RESEARCH.md) · [论文](papers/README.md) · [实验](experiments/README.md)

## 研究设置

```mermaid
flowchart LR
  P["Planner · 优化参数"] -->|计划| E["Executor · 冻结"]
  E --> T["环境交互"]
  T -->|执行反馈| P
```

不预设长时程特异性。先定位真实瓶颈，再核查近邻和简单基线。

## 怎么用

看概览中的判断、未知与下一步，按需要展开题卡。详细证据就近保存在论文或实验目录。

`RESEARCH.md` 是研究内容源。网站直接读取仓库中的 Markdown，开发时内容变化会自动更新。

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

</details>

<details>
<summary>auto-research 如何参与研究</summary>

auto-research 是本项目持续使用的科研工作流。可以在阅读、讨论选题、设计、执行、分析、写作或评审时，选择当前需要的一部分，也可以组合已授权的步骤。已有材料决定入口，无需从头走完所有阶段。

来源与当前版本记录在 [RESEARCH.md](RESEARCH.md#decisions)。研究判断、论文、实验和 GitHub 任务仍保存在原位置，网站展示同一份 Markdown 内容。

在真实任务中发现流程问题时，记录问题及影响，尝试最小改动。行为改进用同一任务、工具和预算比较基线与候选，保留原有正确行为，再决定是否采用。项目内约定与共享工作流分别维护，改进遵循包内的演化流程与实际授权范围。

人工审核与资源预算沿用既有规则。持续使用工作流不表示已批准所有后续研究，也不表示需要为每次讨论新增流程文档。

</details>

<details>
<summary>网站架构、构建与检查</summary>

网站使用 [React](https://react.dev/)、TypeScript、[Vite](https://vite.dev/guide/) 和 [Ant Design](https://ant.design/components/overview/)。导航与页面通过 React Router 组织，正文使用 react-markdown、GFM 与 Mermaid 渲染。

| 位置 | 职责 |
|---|---|
| `web/src/content/` | 从仓库 Markdown 提取摘要、组织文档和搜索 |
| `web/src/App.tsx` | 主题入口与页面路由 |
| `web/src/layouts/`、`web/src/pages/` | 应用布局与研究页面 |
| `web/src/components/Markdown.tsx` | 文档阅读、表格、折叠内容、图和站内链接 |
| `web/src/styles.css` | 阅读排版与响应式布局 |

使用 Node.js 22.12 或更新版本。检查与构建：

```bash
npm --prefix web test
npm --prefix web run build
```

浏览器检查使用 `npm --prefix web run test:e2e`。需要本机 Chrome 或 Playwright Chromium，可通过 `CHROMIUM_PATH` 指定浏览器。

产物在 `web/dist/`。本地预览构建结果：

```bash
npm --prefix web run preview
```

浏览 [http://localhost:4173/](http://localhost:4173/)。网站通过本地服务阅读，不再依赖直接打开单个 HTML 文件。对外发布另行确定。

</details>

## GitHub 与版本记录

| 入口 | 保存什么 |
|---|---|
| `RESEARCH.md` | 研究判断、缺口与下一项关键证据 |
| Milestone / Issue | 阶段与任务范围、依赖、预算和验收 |
| 分支 / commit / PR | 有范围的变更与个人检查记录 |
| tag / Release | 按需固定复现或投稿版本 |

通过链接关联，不重复维护待办。Issue 关闭或 PR 合并不代表假设成立。日常讨论和小修无需逐项创建任务。

<details>
<summary>版本规则与当前配置</summary>

Codex 创建的分支默认使用 `codex/` 前缀。提交信息用 `<type>(<scope>): <description>`。PR 用 `Refs #编号` 关联任务，全部验收完成后才用 `Closes #编号`。

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
| 训练 | 已探索 SFT→GRPO，奖励含 `r_exec` 与 `r_fmt` |
| 技术栈 | VeRL、verl-agent、vLLM |
| 环境 | ALFWorld、SciWorld、WebShop |
| 资源偏好 | 优先 1.5B～13B；实际硬件与预算在实验前核对 |

这些基础本身不构成新贡献。工具、memory、reflection 和重规划按问题需要引入。

本仓库计划保持 Private。对外分享和公开代码的范围由研究者决定。

</details>
