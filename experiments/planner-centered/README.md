# 四框架真实模型验收

[打开 ALFWorld 完整结果页](alfworld.html)：集中查看最新 134 个测试任务、四模型与四框架的 2,144 条有效评分，以及可选择、可对比的交互轨迹。下文保留单任务接口验收、各套评测范围与原始证据。

EO、PE-S、PE-D 和 PC 在同一 ALFWorld `dev/2` 初态上各完成一次真实模型运行。四组都在四步后获得环境原生奖励 1。每组保留独立环境，组内延续 Executor 会话与环境状态。使用同济平台的 `DeepSeek-V4.1-Flash`，Planner 与 Executor 的角色设置在各组固定。[打开审查页](audit.html) · [实现与复现](../../src/recipe/planner-centered/README.md)

| 框架 | Planner / Executor 请求 | 动作数 | 总 token | 实际观察 |
| --- | ---: | ---: | ---: | --- |
| EO | 0 / 4 | 4 | 2,484 | Executor 自主执行整项任务。 |
| PE-S | 1 / 4 | 4 | 3,133 | 首步前交付一次整体规划。 |
| PE-D | 2 / 4 | 4 | 5,069 | 两步后读到遥控器已拿起，保持原请求编号，将剩余规划修订为去沙发并放下。 |
| PC | 3 / 4 | 4 | 7,422 | 先委派寻找并拿起遥控器，再委派放到沙发上。第二阶段使用新请求编号。原生终局后，Planner 记录结束建议。 |

四组采取相同动作。22 条真实模型响应合计 18,108 token。PC 的最后一次 Planner 请求用于原生终局后的结束建议。四组都先停止在线运行，再记录原生判定。该样本用于核对控制流、证据与成本口径。后续仍需在更长任务上检验战略差异、成功率和学习收益。

## 失败与复验

第一轮 PC 给出 `delegate` 和整体计划，但缺少必填 `stage_objective`。运行器拒绝委派，Executor 调用为 0。修正提示明确了阶段目标必须在同一个 JSON 对象里，并附完整委派格式。第二轮重新初始化四组。两轮的实际输出、运行设置和代码快照均可回查。[首轮失败轨迹](runs/live-01/audit.html) · [复验轨迹](audit.html)

## 证据与版本

- [复验运行清单](runs/live-02/manifest.json)记录 Python 3.11.16、ALFWorld 0.4.2、TextWorld 1.7.0、OpenAI SDK 3.20.0、数据版本、无自动重试的调用设定与随机种子未指定的设置。
- [EO](runs/live-02/eo.json) · [PE-S](runs/live-02/pe-s.json) · [PE-D](runs/live-02/pe-d.json) · [PC](runs/live-02/pc.json)保存请求、公开观察、模型响应、用量、终止及判定。
- 运行时的 toolkit 对应提交 `2747786` 的内容。Recipe 为工作区修改。各轮的补丁可应用到该提交，恢复对应轮次的运行入口与运行器。[首轮源码补丁](runs/live-01/source.patch) · [复验源码补丁](runs/live-02/source.patch)

`runs/` 为本地证据。审查页内嵌了公开事件与模型响应，可以离线查看。源文件、运行清单和原始 JSON 的链接依赖本地仓库目录。

## 完整测试集评测

ALFWorld 的[独立结果页](alfworld.html)从[原审查页](audit.html)拆出，读取最终合并清单，展示结果分析、轨迹阅读与双栏对比。四种架构按实际交互协议展示完整 prompt 和原始 response：prompt 按原始 role 顺序逐条展示，内容逐字保留，不转换字段、不截断；环境反馈与模型调用、规划交付、阶段委派和反馈边界可在轨迹中定位。页面不额外展示日志时间戳和运行元数据，原始 prompt 内已有的字段仍原样保留。评分只使用最终有效尝试，归档尝试计入可核对成本。

<details>
<summary>独立结果页的数据与使用</summary>

从仓库根目录，在 `plan-test` 环境导出本地证据，再构建独立 HTML 并启动本地文件服务：

```bash
PYTHONPATH=src conda run -n plan-test python src/recipe/planner-centered/export_alfworld.py
npm --prefix web run build:alfworld
python -m http.server 4174 --bind 127.0.0.1 --directory experiments/planner-centered
```

浏览 [http://localhost:4174/alfworld.html](http://localhost:4174/alfworld.html)，或从同服务下的 [audit.html](http://localhost:4174/audit.html)进入。导出内容在 `alfworld/data/`：摘要覆盖全部 2,144 条最终轨迹，交互数据在选择轨迹后按需读取。更新原始证据后需重新导出。导出只读取现有运行记录，不调用模型或重新运行实验。

`alfworld.html` 和同目录的 `alfworld/` 配套使用，通过本地服务读取交互数据。原始记录与归档继续保留在 `runs/`，结果页的导出数据不代替原始证据。

</details>

ALFWorld 官方测试集评分已结束。正式验收页按原生判定、配对任务和模型用量汇总。WebShop 和 ScienceWorld 按研究者决定停止。Terminal-Bench 在已出有效分数均为零后终止，原始结果供人工核验。比较快照保留四套已有轨迹及各自的范围。[正式验收 HTML](audit.html) · [四套配对比较 HTML](audit-preview.html) · [评测协议](../../src/recipe/planner-centered/README.md#完整测试集) · [已中断的开发预跑](runs/benchmark-01/manifest.json)

ALFWorld 已调度四模型、四框架、134 个正式测试任务，共 2,144 条轨迹。主机重启后从检查点续跑。一次集中启动错误发生在模型调用前，468 条原生评分保留，1,657 条启动失败记录已归档，相关任务在切换临时目录后恢复真实模型评分。恢复补丁让首个事件前的已知启动错误不占模型尝试额度。该补丁的调用在清单中单独标注。运行中以逐条轨迹检查点为准。[运行清单](runs/alfworld-test-01/manifest.json) · [启动错误原始清单](runs/alfworld-test-01/incident-20261119T093443/original-manifest.json) · [游戏映射](runs/data/alfworld/alfworld_test_gamefiles.jsonl) · [初始运行源码补丁](runs/alfworld-test-01/source.patch) · [恢复源码补丁](runs/alfworld-test-01/recovery-source.patch)

首轮全部 2,144 格均有真实模型调用记录，2,034 格取得原生评分。110 格缺评，其中 99 格遇到 HTTP 429、6 格遇到服务端错误、4 格遇到连接错误、1 格超时。在所有模型与框架均有评分的 57 个共同任务上，EO、PE-S、PE-D 和 PC 的均分依次为 0.465、0.447、0.289、0.294。[首轮运行清单](runs/alfworld-test-01/manifest.json)

研究者要求定向补跑仍受外部故障影响的组合。核对了首轮 2,144 条当前轨迹和 2,021 条归档尝试，确认上述 110 格涉及 77 个任务。1,657 条启动 `OSError` 中，1,554 格后来已有原生评分，其余 103 格已在补跑名单中。补跑以同一任务、模型、框架、单条额度和原生评分器为准，保留首轮证据。第一轮使用 6 路并发，无本机请求速率上限。每格增加一次尝试的请求上限合计为 1,613 次。[补跑名单](runs/alfworld-test-01-recovery-01/recovery-selection.json) · [执行入口](../../src/recipe/planner-centered/recover_alfworld.py)

第一轮实际调用覆盖全部 110 格，取得 59 条原生评分。余下 51 格均再次遇到 HTTP 429。第二轮使用 2 路并发，取得 50 条原生评分和 1 条超时。第三轮串行补回最后 1 条评分。三轮均无本机请求速率上限。合并清单保留首轮 2,034 条有效轨迹和各轮归档的原始字节，共有 2,144 条有效评分、134 个全配置共同任务。得分表只链接最终有分的轨迹，缺评格用文字标记，归档依旧计入可核对成本。[第一轮补跑清单](runs/alfworld-test-01-recovery-01/manifest.json) · [第二轮名单](runs/alfworld-test-01-recovery-02/recovery-selection-02.json) · [第三轮名单](runs/alfworld-test-01-recovery-03/recovery-selection-03.json) · [合并后的最终清单](runs/alfworld-test-01-recovery-03/manifest.json)

在 73 个 Qwen 四框架共同有分的 ALFWorld 任务中，PE-D 有 72 次、PC 有 73 次在首次 Planner 回复被协议拒绝。模型把已提供的整数 ID `1` 写成了字符串 `"1"`。当前零分集中反映了这项输出格式差异。[PE-D 示例](runs/alfworld-test-01/trials/m4-t1-pe-d.json) · [PC 示例](runs/alfworld-test-01/trials/m4-t1-pc.json) · [协议解析](../../src/recipe/planner-centered/runner.py)

ScienceWorld 按研究者决定停止正式评分。四模型运行曾切换为 DeepSeek 单模型，保留全部 1,819 个官方变体的任务清单。停止时单模型记录中有 102 条原生评分、85 条缺评和 5 条中断轨迹。四模型原始轨迹保存在独立快照中。两份清单保留实际运行证据。[完整任务表](runs/data/sciworld/sciworld_test_tasks.jsonl) · [DeepSeek 停止清单](runs/sciworld-test-01/manifest.json) · [四模型快照](runs/sciworld-test-01-four-models/manifest.json) · [切换源码补丁](runs/runtime/sciworld-deepseek-source.patch)

WebShop 已核对并复位全部 500 个官方测试目标，正式评分按研究者决定停止。清单保留 754 条已评分轨迹、142 条缺评和 8 条中断轨迹。另外两条用已完成的原生重放计分。完整目录含 1,181,430 件商品，Lucene 索引含 1,181,370 件商品。索引按原生规则跳过 60 条空文本，所有测试目标的商品均可定位。目录使用 `YWZBrandon/webshop-data@ce990ff` 的完整镜像，原始 Drive 链接返回 404，两份数据的字节一致性未核实。[数据清单](runs/data/webshop/prepared/catalog.json) · [原生数据核验](runs/data/webshop/prepared/verified.json) · [官方测试目标](runs/data/webshop/raw/human_goals.json) · [停止清单](runs/webshop-test-01/manifest.json)

两条 WebShop 轨迹在发送请求前触及 32,000 字节输入上限。按原任务和已执行动作重放，初态与每一步观察均匹配。原生环境给出未购买的 0 分，证据与原轨迹均保留。[PC 原生重放](runs/webshop-test-01/native-replay/m1-t198-pc.json) · [EO 原生重放](runs/webshop-test-01/native-replay/m4-t474-eo.json)

Terminal-Bench 以 v4.1.0 的 66 项清单为覆盖分母。首批八项通过 Harbor 0.26.0 的隔离预检，已启动 128 条真实模型轨迹。预检使用脚本动作触发独立 Verifier，原生奖励均为预期的 0。工作容器和评分容器均断网。bootkit 任务排除，要求本机缺失的 GPU 或其他后端能力的任务单列。其余候选逐项核对镜像、资源和评分。正式 HTML 按实际覆盖范围标注。[首批运行清单](runs/terminalbench-reviewed-01/manifest.json) · [任务覆盖与环境清单](runs/data/terminalbench/v4.1-metadata-review.json) · [音乐预检](runs/data/terminalbench/native-preflight-03/trial.json) · [金融预检](runs/data/terminalbench/native-preflight-fin-02/trial.json) · [光波导预检](runs/data/terminalbench/native-preflight-photonic-01/trial.json) · [生产排程预检](runs/data/terminalbench/native-preflight-production-04/trial.json) · [语言音变预检](runs/data/terminalbench/native-preflight-sound-change-02/trial.json) · [MVCC 预检](runs/data/terminalbench/native-preflight-mvcc-03/trial.json) · [图同构预检](runs/data/terminalbench/native-preflight-vf2-02/trial.json) · [批量评测预检](runs/data/terminalbench/native-preflight-batched-02/trial.json)

Coq 和 KS 补充批次已完成 32 个配对组合，取得 26 条原生评分。另 6 条在重试后仍因网关限流缺评。这两项使用与首批相同的模型、框架和执行预算。验收页核对任务互不重叠后一起汇总。[补充运行清单](runs/terminalbench-reviewed-02/manifest.json) · [Coq 预检](runs/data/terminalbench/native-preflight-coq-02/trial.json) · [KS 预检](runs/data/terminalbench/native-preflight-ks-02/trial.json)

KS 的 DeepSeek PC 轨迹生成了原环境中没有的 `solution.cpp`。独立评分器接收并编译了该文件，编译测试通过，数值精度测试失败，原生终局为零分。这一例可作为人工核验的入口。[提交和轨迹](runs/terminalbench-reviewed-02/trials/m1-tks-solver-cpp-pc.json) · [评分器输出](runs/terminalbench-reviewed-02/harbor/ks-solver-cpp-6984cf6a8936/verifier/test-stdout.txt) · [Harbor 原生结果](runs/terminalbench-reviewed-02/harbor/ks-solver-cpp-6984cf6a8936/result.json)

Embedding Drift 和 Cargo 的 32 个组合已完成，取得 30 条原生评分。另 2 条在重试后仍因网关限流缺评。两个任务与前两批互不重叠，复用同一评分协议。[Embedding Drift 预检](runs/data/terminalbench/native-preflight-embedding-02/trial.json) · [Cargo 预检](runs/data/terminalbench/native-preflight-cargo-02/trial.json) · [第三批运行清单](runs/terminalbench-reviewed-03/manifest.json)

Ontology 的 16 个组合已完成，原始运行记录含 12 条原生评分。另有一条在触及本地输入上限后取得有效的同次 Harbor 原生评分，汇总纳入该条，实际可评分 13 / 16。其余 3 条因网关限流缺评。[Ontology 预检](runs/data/terminalbench/native-preflight-ontology-02/trial.json) · [第四批运行清单](runs/terminalbench-reviewed-04/manifest.json) · [输入上限对应的 Harbor 独立评分](runs/terminalbench-reviewed-04/harbor/ontology-kg-querying-fb97c7036157/result.json)

WAL Recovery Ordering 2.5.0 通过离线隔离预检。两次 PC 委派共享工作区，独立评分器为原始应用返回有效零分。16 格正式运行取得 15 条原生评分，另 1 格重试后仍缺评。[WAL 预检](runs/data/terminalbench/native-preflight-wal-01/trial.json) · [第五批运行清单](runs/terminalbench-reviewed-05/manifest.json)

Risk Scorer Replay 2.2.1 通过离线隔离预检。任务数据为合成记录，独立评分器为原始应用返回有效零分。16 格正式运行均取得原生评分。[Risk 预检](runs/data/terminalbench/native-preflight-risk-01/trial.json) · [第六批运行清单](runs/terminalbench-reviewed-06/manifest.json)

ALFWorld 按研究者指示于 21:46（北京时间）从检查点改为 16 条并发，并取消每分钟 100 次的本机限速。切换时保留 2,007 条原生评分，评测于 21:59 结束。[本地队列入口](runs/runtime/resume-queue.sh) · [并发调度](runs/runtime/parallel-queue.sh) · [最终汇总入口](runs/runtime/finalize-audit.sh) · [原并发补丁](runs/alfworld-test-01/parallel-source.patch) · [取消本机限速的源码补丁](runs/alfworld-test-01/unpaced-source.patch) · [WebShop 原生重放源码补丁](runs/webshop-test-01/native-replay-source.patch)

共享队列从真实轨迹判断网关故障。10 秒内有 5 个不同试验发生连接错误时，延后请求 30 秒。10 秒内有 3 个不同试验出现限流时，延后请求 10 秒。两个条件同时满足时使用较长的等待时间。触发记录保存在本地 `gateway-cooldowns.log`。[网关退避实现](runs/runtime/gateway-watch.py)

11 月 19 日 20:16（北京时间）主机重启。重启前多套评测集中收到 HTTP 429，现有记录无法判定配额归属。按研究者指示更换同济 API 凭据，单次真实对话验证返回 HTTP 200。队列于 20:21 从原检查点恢复，继续使用相同的模型和请求限速。
