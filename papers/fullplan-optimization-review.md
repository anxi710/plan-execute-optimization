# Full-plan 优化：生成过程、证据与文献筛选

核查日期：2026-11-11。本文回答一次高层完整规划如何形成、在哪里学习，以及相关结果能支持什么。它是文献调研，不代表本项目已经选择机制或获得结果。原文、附录和下列官方代码均为只读核查，未运行复现。

## 判断

**最接近本项目的 MPO 和 EAGLET，确实把一个完整规划候选作为一次主要生成的输出，再通过执行评价更新 Planner。** TraceLift 和 PTTS 也采用类似的候选生成接口，但其对象分别是推理轨迹和联合 outline 集合，不能直接等同于交互任务的高层 full-plan。这支持“具名直接近邻常采用单次候选生成”的观察，不支持“所有 full-plan 优化都默认单轮 prompt”的全称判断。

此次筛选也不支持用若干多轮系统替代这个问题。推理时搜索、局部运动轨迹修订、执行后的剩余计划更新，分别回答不同问题。**目前有用的研究依据是：已有方法怎样构造战略候选、怎样用执行证据评价候选、怎样更新规划策略；多调用本身既不是贡献，也不是可靠性的保证。**

机制相关性不足以确定一篇论文在本项目中的用途。下文区分“存在相邻机制”与“足以支撑研究动机”的证据；PlanGEN 和 Foresight 仅保留为邻域线索，不作为主 proposal 的论据。筛选依据是具体实验与适用条件，不以发表身份或代码公开替代证据审查。

## 1. 核查单位与筛选标准

这里的 full-plan 指覆盖任务整体路线的高层规划。它可以保留未知条件和执行自由度，不要求写成脚本或逐动作清单。“端到端”同时可能指参数训练目标或一次输出，容易混淆，本文不用它判断调用结构。

| 要区分的对象 | 本文怎样辨认 |
| --- | --- |
| 单个原始候选 | 一次主要 completion 给出完整规划；其中可以包含长推理、自检或多个 outlines。 |
| 独立多候选 | 多次生成后选择；后一个候选没有接收前一个候选的评价证据。API 批量采样也属于此类。 |
| 交付前多调用形成 | 同一份最终规划在交给 Executor 前，经多次信息处理、候选构造或语义修订形成。格式重试单独记录。 |
| 执行后重规划 | 真实环境已经发生变化，再形成全局或剩余全局规划。它不说明前一次规划内部调用了几次。 |
| 数据构造、学习与部署 | 教师合成数据时多调用，不等于被训练策略多调用；训练期重复执行，不等于部署时修订规划。 |

筛选围绕具体用途，检查任务和交付单位、学习对象、反馈来源、额外数据、计算控制、消融、测试信息与代码。以下分层不是论文总质量排行榜：

- **可作主对照／核心机制依据**：接口与主线直接接近，或能支撑一个明确的局部机制比较；采用前仍需匹配本项目协议。
- **只作存在性或邻域线索**：机制有相似处，但任务、学习位置或证据条件不同，不承担主线收益判断。
- **暂不承载结论**：具体主张缺少所需证据，或实现／报告差异尚未解决。缺少报告不等于确定没有实施。

## 2. 可作主对照或核心机制依据

### 2.1 MPO：最直接的完整执行评价基线

MPO 的 meta plan 是任务级抽象指导。SFT 后，为每个任务生成多个计划，每个计划重复执行，再用执行质量形成 DPO 偏好对。它清楚区分“多采计划”和“同计划多次执行”，适合作为本项目评价与学习主线的直接基线。[原文 v2 §2–3](https://arxiv.org/html/2503.02682v2#S3)

证据的长处是三个交互环境、固定 Agent 加／不加计划的比较，以及 SFT、DPO 和采样数量分析。§5.5 分别改变计划数与重复执行数，支持把评价噪声纳入研究；但该设计并不是固定总执行预算下的最优分配比较。“更多重复有效”不能直接推出“本项目应少探索、多评价”。其训练均使用完整执行，也没有验证低成本评价替代方案。[实验与分析 §4–5](https://arxiv.org/html/2503.02682v2#S4)

**使用判断：**作为“独立候选＋重复完整执行＋偏好更新”的主对照候选。若实际任务不相同，应复用机制、重新测量，不能引用原论文增益作为本项目收益。代码已读到 [`gen_metaplan.py`](https://github.com/WeiminXiong/MPO/blob/main/scripts/gen_metaplan.py)：主要生成是任务条件下的 chat completion，错误时重试同一请求；未见把执行反馈回填给同一候选作语义修订。没有运行其训练栈，不承诺公开脚本可直接复现全部论文结果。

### 2.2 EAGLET：执行增益奖励的直接近邻

EAGLET 用黄金轨迹合成 global plan，经执行过滤做 SFT，再以一组候选规划做 GRPO。两个同源、能力不同的 Executor 在 RL 阶段冻结，奖励包含有／无规划的执行增益、效率和格式项。执行反馈进入奖励与参数更新，论文没有把它写成交付前改写同一候选的内循环。[v3 §3.1–3.2](https://arxiv.org/html/2510.05608v3#S3)

其主实验覆盖三个交互环境，Table 4 和 Appendix C 比较 SFT、过滤、RL、直接完成率及不同执行器奖励来源，能支撑“规划价值依赖执行器能力”的局部依据。需要保留两个限制：去除 ECGR 的主消融同时改变奖励构造与执行器来源，Appendix C 的单执行器变体才更接近拆分因素；宣称相对 Executor RL 的训练效率，也不能当作本项目不同 Planner 算法的等预算优势。[实验 §4、Appendix C](https://arxiv.org/html/2510.05608v3#S4)

**使用判断：**作为执行增益与直接完成率的机制对照。双 Executor 不是本项目必须采用的设置。正式身份可见 [ACL 2026 论文页](https://aclanthology.org/2026.acl-long.597/)，但本次读取的[官方代码目录说明](https://github.com/S1s-Z/EAGLET/blob/main/code/README.md)仍为 Coming Soon。因此调用结构有论文级证据，未核定 API 重试、奖励缓存和全部运行细节。

### 2.3 PTTS：联合战略候选的机制依据，目标是集合覆盖

PTTS 在一次 autoregressive pass 中联合生成多个解题 outlines，再让固定 Executor 分别完成解题；RL 优化整组解的 pass@k。它是“一个生成输出可以包含有协调的多个战略候选”的明确近邻，并非交付前反馈修订方法。[v1 §3.1–3.3](https://arxiv.org/html/2609.27374v1#S3)

论文比较 repeated sampling、零样本 PTTS 与 RL，并在固定总解数下改变组内分支数。它还改变训练时 Executor 推理预算，展示执行器过强的自我修正会影响 Planner 的训练信号。不过，等解数不等于等总 token／墙钟；pass@k 衡量候选集合含正确解的概率，不等于没有选择 oracle 时交付一个计划的成功率。其模式收缩分析依赖文中明确的简化假设，不能写成任意 GRPO 都会战略塌缩的定理。[§4 与 Appendix A](https://arxiv.org/html/2609.27374v1#S4)

**使用判断：**作为联合候选构造和集合奖励的机制对照，适用范围先限于数学解题。已读[官方测试脚本](https://github.com/shirley-wu/planned-test-time-scaling/blob/main/eval/ptts_infer.py)：默认每组 4 个 outlines，为累计 64 个解会独立形成多组；解析／请求失败重试不带语义反馈。不能把“每组一次生成”误写成“整道题一次调用”。

### 2.4 TraceLift：评价信号的近邻，不是低成本评价已经成立的证据

TraceLift 训练 reasoning reward model，再以固定 Executor 的正确性与增益奖励优化 reasoning Planner。v4 奖励为 `0.5 × R_exec + 0.5 × RM × uplift`；同一 reasoning 在重复执行估计中保持固定。测试时用 greedy reasoning → 固定 Executor，不调用 RM 或 uplift 估计器。[v4 §3.2.2、§4.1](https://arxiv.org/html/2605.03862v4#S3.SS2.SSS2)

其 Exec-only 对照、奖励拆分、执行重复数分析和三个模型家族，比仅展示组合系统的结果更有解释力。主表报告三次运行均值。不过，主要对象是代码／数学推理轨迹，奖励需要额外离线标注、RM 训练及重复执行；同训练步数也不保证同总成本。因此它能说明应比较“文字质量评分”与“执行效用”，不能证明低成本评分可靠，更不能证明复杂 RM 必要。[§4.2–4.5](https://arxiv.org/html/2605.03862v4#S4.SS5)

**使用判断：**作为执行反馈锚定的评价机制近邻。已读 [`train_code_grpo.py`](https://github.com/MasaiahHan/TraceLift/blob/main/scripts/train_code_grpo.py#L704) 和 [math 训练入口](https://github.com/MasaiahHan/TraceLift/blob/main/scripts/train_math_grpo_trl.py)：候选先生成后求 reward，未见将该 reward 作为上下文反复修订原候选。论文收益未在本项目复测，RM 数据与总成本的复现核对仍未完成。

### 2.5 PLANSEARCH：战略探索的推理时对照，应认真比较

PLANSEARCH 先形成并组合问题 observations，再生成自然语言解法，部分路径经过批评与另一个解法生成，最后转成代码。它没有参数学习，但比“只增加采样温度”更直接地改变解法构造方式，因而适合作为战略探索的推理时对照。[v2 §4.2–4.3](https://arxiv.org/html/2409.03733v2#S4.SS3)

证据包括 repeated sampling、IdeaSearch、CoT、设计消融与生成 token 归一化比较。仍须保留：代码基准上的战略差异不替代本项目测量；多样性指标含模型判断；公开测试过滤与隐藏测试评估必须分开；作者在 Appendix O 承认相关采样使通常 pass@k 估计的解释发生变化。不能只按最终代码候选数比较效率，也不能把相关性解释为多样性带来收益的单一因果证据。[§5–6、Appendix D/H/O](https://arxiv.org/html/2409.03733v2#A4)

已读官方 [`combo_observation_model.py`](https://github.com/scaleapi/plansearch/blob/main/search/combo_observation_model.py#L288)：解法、批评和修订是分开的调用，保留原解法与修改解法；[`simple_filter_models.py`](https://github.com/scaleapi/plansearch/blob/main/search/simple_filter_models.py#L28)使用公开测试过滤。这里的 observation 主要是模型推断，不是主动取得的环境新事实。

**使用判断：**可以改造为固定 Executor 下的探索基线，但不能作为“已经学会多轮 full-plan 形成过程”的证据。它的价值在于明确可比机制，不在于提供一个字面反例。

## 3. 一次规划的内部调用：有界结论

| 工作与交付单位 | 训练／数据阶段 | 交付一次规划的内部过程 | 不能混入的任务级过程 |
| --- | --- | --- | --- |
| MPO：meta plan | 教师轨迹反推计划；多候选、多次执行后 DPO | 单次主要 completion；错误重试 | MC 重复执行是评价采样。 |
| EAGLET：global plan | 教师合成与过滤；候选组 GRPO | 论文按完整 thinking＋plan 候选描述；实现细节未公开核定 | 双 Executor、有／无计划比较用于 reward。 |
| TraceLift：reasoning trace | RM 数据构造多阶段；候选 GRPO | 单个 reasoning completion；评价不改写候选 | Executor 重复解题用于估计 uplift。 |
| PTTS：outline set | 一组 outlines 联合获得集合奖励 | 一次 completion 输出一组；不同组独立 | 总解数增加会带来多组调用。 |
| PLANSEARCH：自然语言解法→代码 | 无参数训练 | observation 组合、解法、批评、修订等多调用 | 最终代码测试过滤是另一环节。 |
| Plan-and-Act：全局／剩余全局计划 | 轨迹合成、扩充并分别 SFT 两模块 | 初始 plan 的主要生成为单次；代码允许格式反馈修复 | dynamic 模式在环境动作后更新剩余计划。 |

Plan-and-Act 是实用的边界对照：它分别训练 Planner 和 Executor，不能将最佳系统的收益全归于 Planner。静态 Planner 的固定 base Executor 消融较适合分离作用；动态重规划结果属于另一个问题。官方 [`plan.py`](https://github.com/SqueezeAILab/plan-and-act/blob/main/plan_and_act/cot/inference/plan.py#L36) 和 [`dynamic_plan.py`](https://github.com/SqueezeAILab/plan-and-act/blob/main/plan_and_act/cot/inference/dynamic_plan.py#L53)会在输出标签不合规时回填旧输出和格式纠错请求。这个事实只用于准确描述调用次数，不承担战略修订的论证。[原文 §3–5](https://arxiv.org/html/2503.09572v3#S3)

据此，较准确的表述是：

> 本轮核查的固定 Executor 参数优化近邻，通常对一次主要生成得到的完整候选进行执行评价与参数更新。交付前多调用的解法构造和修订已有推理时先例，但这些结果尚不足以判断：在本项目的高层 full-plan 接口下，主动获取信息并据证据修订，是否优于等成本的长推理、独立多候选与筛选。

这项比较需要区分额外计算、额外信息、信息选择和修订本身。它并不要求预先采用树、库、独立 Critic 或某一种 RL 算法。

## 4. 低权重邻域：PlanGEN 与 Foresight

### 4.1 PlanGEN：存在多调用规划构造，但不足以支撑主线机制

**身份已核实。**完整标题为 *PlanGEN: A Multi-Agent Framework for Generating Planning and Reasoning Trajectories for Complex Problem Solving*，正式发表于 EMNLP 2025 主会，Anthology ID `2025.emnlp-main.1042`。此次以[正式论文及附录](https://aclanthology.org/2025.emnlp-main.1042.pdf)为准，不仅使用较早 arXiv v1。[正式出版页](https://aclanthology.org/2025.emnlp-main.1042/)

| 检查项 | 证据与使用判断 |
| --- | --- |
| 一份计划的形成 | §2 的不同变体包括独立候选选择、树搜索和依据反馈继续优化。不能将所有变体都叫“同一计划反复修订”。不更新模型参数。 |
| 反馈的含义 | Constraint／verification agents 从题目提取约束、推断质量。这里的 verifier 不是环境执行得到的真值，也不是有完备保证的形式验证器。 |
| 有哪些有效对照 | 正式版 §4、App C/F 有去约束、随机／UCB 选择、同模型 BoN 和直接解答等比较。不能说论文没有消融或只比单次 CoT。 |
| 哪些主张证据不足 | 等计算 BoN 是局部案例；最高组合结果不能推广为全面等 token／总成本优势。调用与时间分析包含估算，不能代替本项目实测全流程成本。 |
| 可比性实例 | App F Table 5 的 Blocksworld v1，REBASE 因资源限制只测 315 个样本，其他设置为 500 个；不能将该表直接读成同测试集合上的成对增益。 |
| 复现深度 | 已读正式方法、主要分析、对应附录和示例入口；未核实完整官方可执行实现。第三方同名仓库不作为官方证据。 |

**筛选结果：只作存在性／邻域线索。**它足以说明多调用形成自然语言计划已有设计，不足以支持固定 Executor 的参数学习、执行证据低成本评价或主动获取环境信息的收益。上述限制有具体位置，并不等同于整篇研究无价值。

### 4.2 Foresight：内部循环确实存在，研究对象与主线不同

本次讨论的是 Arthur Zhang 等人的 *Foresight: Iterative Reasoning About Clues that Matter for Navigation*，arXiv `2606.12550v1`，不是其他同名工作。截止核查日，[arXiv](https://arxiv.org/abs/2606.12550)、[作者页](https://carl-qi.github.io/)和[项目引用](https://amrl.cs.utexas.edu/foresight/)支持预印本身份，未核实正式录用，不能写成 EMNLP 或其他会议论文。

| 检查项 | 证据与使用判断 |
| --- | --- |
| 一次规划的内部过程 | §4.1 明确区分内部 refinement index 与机器人执行时间。共享 VLM 交替提出局部图像航点、批评、修订，接收的是同一上下文，不是环境实际执行后的验证。 |
| 学习对象与反馈 | SFT 后在 plan–critique–refine 轨迹上做 RL；奖励含人类偏好 RM 与专家轨迹对齐。它不是独立高层 Planner 从固定 Executor 的任务成功学习。 |
| 实际轮数 | App F.3.3 训练最大 refinement 为 `K=1`。有循环学习的证据，但不能引用为长内循环训练已经成熟。 |
| 有哪些有效控制 | 有 no-RL／no-refinement、奖励项和模块训练消融；离线比较共用 grounding policy，硬件比较共用低层控制。不能笼统说它只靠换模型获得收益。 |
| 测量与外推 | 离线主要衡量专家轨迹距离，未必覆盖所有有效策略；硬件为 6 个环境、每方法每环境 4 次，并允许有限人工干预。结果不等于独立于任务／偏好定义的全自主稳定性。 |
| 尚未消除的解释 | 组合训练与推理计算同时变化；本次未核实同 token 独立重采样／选择能否达到同样效果。单人偏好标注也限制了偏好奖励的外推范围。 |

这些判断可在[项目论文 §4–5、App F.2–F.4](https://amrl.cs.utexas.edu/foresight/static/pdfs/ForesightPreprint.pdf)复核。另有一处报告差异：正文 §5 写每类包含 seen 与 unseen 环境，项目页称部署地点全部 held-out。两者可能使用不同层级的 seen 定义，但尚未核清，因此不引用“六个完全未见环境”作为泛化证据。

**代码状态需要更正。**官方仓库已经公开。[`waypoint_planner_node.py`](https://github.com/ut-amrl/foresight_public/blob/main/legged_deployment/legged_deployment/waypoint_planner_node.py#L584)中 motion／critic 分别调用，批评进入后续上下文，满足停止条件后返回计划；[`architecture.md`](https://github.com/ut-amrl/foresight_public/blob/main/docs/architecture.md)给出默认一次 refinement。与此同时，[`training.md` 的 Scope](https://github.com/ut-amrl/foresight_public/blob/main/docs/training.md#scope)明确仅移植 SFT，RL 入口仍依赖原研究仓库、不能在公开仓库直接运行。公开推理代码支持机制存在，尚不等于 RL 结果已可复现。

**筛选结果：只作循环学习的邻域线索，暂不承担高层 full-plan 的效果结论。**作者关于训练后期忽略 critique 的观察值得作为风险线索；它对信用分配原因的解释仍是作者假设，不能当作已隔离的因果机制。无需因这条线索将本项目改成联合 Planner／Critic 训练。

## 5. 暂不承载主线结论的其他工作与主张

| 项目 | 保留到什么程度 | 不用于什么结论 |
| --- | --- | --- |
| [ISR-LLM](https://arxiv.org/html/2308.13724v1#S4.SS3) | 方法级核查确认完整符号动作序列经过 validator 反馈修订。 | 不作高层抽象规划可低成本验证、或参数学习有效的证据；公开代码完整性未核定。 |
| [PLAN-TUNING](https://aclanthology.org/2025.emnlp-main.1087.pdf) | 新增定向核对 §3：教师多候选过滤用于数据合成；学生联合学习 plan 与答案。 | 不把教师的数据合成循环算成部署 Planner 内部循环，也不算固定独立 Executor 的直接对照。未扩展为完整效果评审。 |
| AgentFlow 等任务级多轮系统 | 仅作任务级多轮系统参照，按实际 Planner 交付单位判断。 | 不以整任务的多轮 step-plan 反驳一次 full-plan 的内部调用命题。 |
| PIVOT 等在线修订系统 | 属于不同优化对象的邻域，详见独立架构调研。 | 不从“会更新计划”推出“训练了交付前 full-plan 形成过程”。 |
| “多轮更稳定”“首次学习 full-plan 形成过程” | 当前均未建立。 | 不进入 proposal 的事实或创新声明。 |

这里没有把找不到严格匹配的论文写成研究空白。真正需要验证的是：在约定的任务、信息权限、形成成本与 Executor 下，哪种形成策略改善了有意义的战略覆盖，评价是否可信，更新后是否保留收益。

## 6. SFT 数据复用：保留问题，不宣称新范式

已有示范可以继续参与后训练，这不是空白。[LUFFY §2](https://arxiv.org/html/2504.14945v2#S2)把外部推理轨迹与当前 rollout 用于 RL；[ReLIFT §2.2](https://arxiv.org/html/2506.07527v1#S2.SS2)按困难题引入监督更新；[SDFT §3](https://arxiv.org/html/2601.19897v2#S3)让示范作为教师上下文指导学生自身轨迹的蒸馏。这些工作只支持“示范可在不同阶段发挥不同作用”，不证明它们都复用了同一份已做 SFT 的数据，也不证明适合本项目。

本项目值得保留的问题是：旧示范提供候选构造知识、继续监督，还是评价参照？它在当前 Executor 下仍有效吗？只有最终 plan 的数据，不能凭空监督真实检索、验证和修订过程。以上三篇沿用现有讨论中已核查的方法段落，本轮未扩大效果评审或阅读队列。

## 7. 检索范围、判断变化与停止条件

本轮先读项目现有研究记录，再核对论文版本、正式出版页、方法／实验／附录和官方关键代码。初次检索覆盖固定 Executor 的 Planner 学习、推理时计划搜索／修订、执行后重规划、检索辅助 global planning 和局部运动规划。此次补检集中在用途筛选、PlanGEN 正式版与 Foresight 公开实现，没有重新开展无界文献收集。

主要检索式包括：`"full-plan" "refinement" planner optimization`、`"global planner" "iterative refinement" training`、`"planning" "execution-guided" "refinement"`、`"planner" "multi-round" "reinforcement" "plan"`，以及具名论文标题、arXiv、官方代码、正式会议身份的定向查询。检索截止 2026-11-11，不声称穷尽全领域。

此次相较初稿的实质变化：

1. 将 MPO／EAGLET 的直接学习接口，与 PTTS／TraceLift 的领域化机制依据分开；保留可比性和成本限制。
2. 将 PLANSEARCH 作为值得认真比较的探索方法，而非仅用来反驳“全部单轮”。
3. PlanGEN、Foresight 移入低权重区；补读正式版本与实现后，同时记录有效控制和实际缺口。
4. 更正 Foresight 代码公开状态，限定其可复现训练范围；不把 PlanGEN 的正式发表身份转化为质量背书。

目前证据足以确定各篇的可用范围，无需继续增加弱近邻。如果之后选择“主动获取证据并学习完整形成过程”作为贡献，下一次文献核查应围绕已经固定的交付接口、证据权限和学习轨迹，追查直接近邻的引用与被引，并核实成本与数据隔离。当前最大未知仍是本项目候选的战略差异及其学习价值，文献不能替代这一测量。
