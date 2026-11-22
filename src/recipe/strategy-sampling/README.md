# 同任务战略采样 Recipe

对照同一初态下的独立规划采样与提示探索其他路线。Recipe 负责 A/B 条件、候选选择、重复次数和分析口径。模型、任务加载、Executor 提示、环境执行和轨迹记录复用 toolkit。[基础库与复用规则](../../toolkit/README.md#基础库与-recipe) · [首轮实验结果](../../../experiments/strategy-sampling/README.md)

首轮 A/B 的 Planner 回复包括 `<route>` 和 `<plan>`，B 组用前序 `<route>` 构造下一次请求。`sample.py` 保留此次对照的提示和解析供历史复现。重新使用这套专用提示须取得明确授权。统一 Planner 模板的输出约定为 `<plan>`，采用它做同类采样时需要先确定路线摘要的来源。[统一提示词](../../toolkit/README.md#统一提示词)

## 首轮实验协议

首轮从 ALFWorld `dev` 的六种任务类型按目标分层抽取八个任务，随机种子 417。任务 ID 为 3、6、12、14、68、72、103、104。另选 2、17、18、77 检查四组预先写好的替代路线。全部 12 项都以完整初始观察核对了唯一的 `gamefile` 映射。两组条件收到同一初态和任务。

| 条件 | 生成方式 |
| --- | --- |
| A | 每任务独立请求 8 份高层计划。 |
| B | 每任务最多 8 份，后续调用请求考虑实质不同的可行路线。B 只看到自身先前生成的路线简介，每份截取前 30 个词。首个请求与 A 使用同一提示，两次调用独立。 |

两组均用 `deepseek-flash` 非思考模式，温度 0.8，最多 320 个输出 token，不启用自动重试。生成后打乱文本，按会改变信息获取、路线或子目标先后的关键决策归组。标注材料隐藏条件、生成顺序和执行结果。每任务报告从前 2、4、8 份中观察到的路线数。成本匹配使用每任务两组总 token 数的较小值，分别取其预算内的最长生成前缀，包含输入历史和输出。单独保留无明确路线的标记。

从 A 的常见路线和 B 在共同预算内新增的路线各取首个代表。若无 B 新路线，优先比较其他已出现的路线。当前缀内两组只有同类路线时，取 B 首个有效计划比较执行表现。每任务至多执行两份生成计划，另执行预先写好的八份参照计划。每份在同一 `gamefile` 独立重置三次。Executor 固定为 `deepseek-flash` 非思考模式，温度 0.6，最多 30 步，每步最多 256 个输出 token。使用一条 ALFWorld 示例，并在同一位置注入计划。服务端 seed 未指定。首轮规模上限为 192 份生成计划和 96 条完整轨迹。

## 运行

当前 Executor 不再加载示例。用当前 Recipe 执行时，请使用新运行目录，不要续跑首轮。复现首轮请参考[原运行记录](../../../experiments/strategy-sampling/README.md#运行与产物)。

使用 `planner-worlds` Conda 环境或项目 Docker 工作区，并准备 ALFWorld 数据。[环境与数据准备](../../toolkit/README.md#环境与数据)

在本方案的 [`config.yaml`](config.yaml) 设置 `run_dir` 和 `data_dir`。采样、执行和分析参数由本方案维护。运行时，`toolkit` 下的字段覆盖[基础库默认值](../../toolkit/config.yaml)中同名字段，不改写公共文件。例如，`toolkit.environments.alfworld.max_steps` 只调整本方案的 ALFWorld 步数上限，采样提示与实际执行都使用它。

三条命令均支持 `--config` 指定另一份方案配置，原命令行参数仍可覆盖对应值。运行和数据目录的相对路径基于当前工作目录，执行指令的相对路径基于 `src/`。

运行目录需包含 `tasks.jsonl`、`controls.jsonl` 和 `gamefiles.jsonl`。`planner.api_base`、`planner.api_key` 覆盖 Toolkit 的 Planner 连接默认值，`toolkit.executor` 覆盖 Executor 默认值。`api_key` 为空时，采样和执行待运行样本读取通用环境变量 `OPENAI_API_KEY`。本机网关可直接配置普通字符串 key；真实密钥留在环境变量或未跟踪的本地配置中。运行设置不保存 key。[Toolkit 依赖与离线检查](../../toolkit/README.md#使用与检查)

两个角色统一使用 `thinking` 和 `reasoning_effort`。`thinking: disabled` 发送 `thinking: {type: disabled}`；`reasoning_effort: none` 发送同名请求字段。`null` 表示省略该字段，不能视为关闭内置思考。按所用接口选择字段：当前 [DeepSeek 直连](https://api-docs.deepseek.com/guides/thinking_mode/)配置保留 `thinking: disabled`，[同济接口](https://agi.tongji.edu.cn/docs/reasoning)使用 `reasoning_effort: none`。客户端不识别供应商或自动转换字段。续跑严格比较当前设置与运行记录，不转换旧字段或接受指令路径迁移；历史记录保留，复现须检出对应源码版本。

从仓库根目录启动采样和盲审材料生成。`--samples` 可限制本次采样的槽位数；盲审仍要求达到 YAML 中设置的完整数量。

```bash
python src/recipe/strategy-sampling/sample.py
python src/recipe/strategy-sampling/analyze.py blind
```

将路线标注放入 `labels/`，再生成执行队列、执行计划并汇总结果。盲审和汇总分别使用运行记录中设定的每组候选数与每份计划执行次数。续跑要求设置与该运行的记录一致。

```bash
python src/recipe/strategy-sampling/analyze.py queue
python src/recipe/strategy-sampling/execute.py
python src/recipe/strategy-sampling/analyze.py report
```

离线集成检查使用模型和环境替身。

```bash
PYTHONPATH=src python -m unittest discover -s src/recipe/strategy-sampling/tests -q
```
