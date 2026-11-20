# PC 历史轨迹中的结束建议

正式 ALFWorld 测试中，Planner 在环境终止前主动建议结束共 **3 次，原生得分均为 0**。另有 118 次发生在环境终止之后，提示词已要求模型输出 `finish`。前者能检验模型在仍可执行时是否误停；后者只能检验它对既有终局的解释。以下编号对应原始 JSON 的 `event_id`。“阅读任务”链接适用于已通过本地服务打开的 ALFWorld 结果页，原始 JSON 可直接在本机读取。

## 环境仍可执行时的三条建议

三次运行都在阶段反馈 `budget_pause` 后让 Planner 自选 `delegate` 或 `finish`。控制器接受了 `finish` 并以 `planner_finish` 停止。当时环境尚未报告任务结束，记录中的 `success` 都是 `false`。

| 目标 | Planner 建议原文（节选） | 它当时能看到什么 | 事件与轨迹 |
| --- | --- | --- | --- |
| 放一块干净的 **cloth** 到台面 | “The handtowel 1 was already clean since cleaning attempts produced no change (events 16, 22, 30).” | 三次清洁都只返回 “Nothing happens.”，不能证明已经干净。事件 32 还列出另一件名为 `cloth 3` 的物品。事件 38 确认放上台面的是 `handtowel 1`。 | 41 返回 → 42 原文 → 43 建议 → 44 停止 → 45 评分 **0**。[阅读任务 2](alfworld.html?tab=read&left=m1-t2-pc) · [原始 JSON 第 2092 行](runs/alfworld-test-01-recovery-03/trials/m1-t2-pc.json#L2092) |
| 放一个加热过的 **cup** 到柜子 | “The mug 1 was heated in the microwave (event 22), so it qualifies as a hot cup.” | 22 确认加热了 `mug 1`，32 确认将它放入柜子。两条观察均未证实该物品符合目标中的 `cup`。 | 33 返回 → 34 原文 → 35 建议 → 36 停止 → 37 评分 **0**。[阅读任务 58](alfworld.html?tab=read&left=m1-t58-pc) · [原始 JSON 第 1579 行](runs/alfworld-test-01-recovery-03/trials/m1-t58-pc.json#L1579) |
| 放一把干净的 **knife** 到台面 | “Butterknife 1 satisfies the 'knife' requirement, based on event_id 8 showing it in drawer 1.” | 8 只证明抽屉里有 `butterknife 1`。24、32 确认清洁并放置了该物品。物品类别等价是 Planner 的推断。 | 33 返回 → 34 原文 → 35 建议 → 36 停止 → 37 评分 **0**。[阅读任务 92](alfworld.html?tab=read&left=m3-t92-pc) · [原始 JSON 第 1579 行](runs/alfworld-test-01-recovery-03/trials/m3-t92-pc.json#L1579) |

这三条都能裁定“此刻宣告成功”有误。提前停止后继续执行能否取得成功，现有轨迹无法回答。

## 已获知环境结束后的判断

这类调用的原始提示包含 “The environment reached a native terminal state. Set decision to \"finish\"”。下列例子分别展示正确解释终局，以及把终局误解为目标已满足。

- **ALFWorld，解释与评分相符。** 目标是把铅笔放上架子。事件 16 返回 “You put the pencil 1 in/on the shelf 1.”；17 标记 `task_finish`。18 中 Planner 写道 “Pencil 1 was successfully placed in/on shelf 1, completing the task.”，19 接受 `finish`，21 评分 **1**。[任务 112 原始轨迹](runs/alfworld-test-01-recovery-03/trials/m1-t112-pc.json)
- **WebShop，购买成功，商品匹配仅获部分分。** 目标涉及床的尺寸、材质、颜色和价格。24 的观察是 “The purchase ended the WebShop session.”。25 返回 `task_finish` 后，Planner 在 26 中写道 “The DHP Dakota King Camel item satisfies all constraints: King size, Camel color, faux leather upholstery, and price $100.0 < $630.00”。27 接受 `finish`，29 的原生奖励为 **0.4**。环境确认交易结束；“全部满足”与评分冲突，轨迹的终局观测没有逐项列出扣分原因。[任务 348 原始轨迹](runs/webshop-test-01/trials/m1-t348-pc.json)
- **ScienceWorld，环境终止于失败。** 任务要求依次聚焦温度计、锡，并按熔点选择盒子。执行记录到事件 20 聚焦 `tin cup` 为止，没有后续选择盒子的动作。21 返回 `task_finish`；Planner 在 22 中称此次终止 “indicating the measurement/focus protocol was accepted.”，23 给出 `finish`。25 的原生奖励为 **−1**，`success=false`。这条运行确实已经结束，终局本身不能证明测量通过。[锡熔点任务原始轨迹，gzip](runs/sciworld-test-01-four-models/trials/m2-tmeasure-melting-point-known-substance_341-pc.json.gz)

## 核查范围和计数

统计正式目录中实际存在的 PC 轨迹文件，包括已中断或缺评的记录。以 `planner_decision.decision == "finish"` 认定协议已接受的建议，通过该事件的 `model_event_id` 回查当轮提示与原话，再按最近的 `execution_feedback.return_reason` 区分终局前后。最终得分读取同条轨迹的 `verifier`。普通 `delegate`、PE-D 的 `guide`、正文中提到 “finish” 以及被拒绝的决定均不计为已接受的建议。

| 正式运行 | 有记录的 PC 轨迹 | 环境结束前接受 `finish` | 环境终局后接受 `finish` | 后一组原生奖励 |
| --- | ---: | ---: | ---: | --- |
| [ALFWorld，最终合并清单](runs/alfworld-test-01-recovery-03/manifest.json) | 536 | 3 | 118 | 118 条为 1 |
| [WebShop，停止时的清单](runs/webshop-test-01/manifest.json) | 215 | 0 | 37 | 19 条为 1，17 条介于 0 和 1 之间，1 条为 0 |
| ScienceWorld，[单模型清单](runs/sciworld-test-01/manifest.json)与[四模型快照](runs/sciworld-test-01-four-models/manifest.json) | 168 | 0 | 31 | 29 条为 1，2 条为 −1 |
| Terminal-Bench，正式批次 01–06 | 46 | 0 | 0 | 结束后由独立 Harbor verifier 判分。可核对一例[控制器轨迹](runs/terminalbench-reviewed-02/trials/m1-tks-solver-cpp-pc.json)与[原生结果](runs/terminalbench-reviewed-02/harbor/ks-solver-cpp-6984cf6a8936/result.json)。 |

四套正式记录中有 233 条出现 `execution_feedback.return_reason=task_finish`，其中 186 条获得协议接受的收尾建议。其余 47 条里，29 条当时已用完 Planner 额度，3 条收尾请求遇到限流，8 条返回了协议不支持的决定，7 条写了 `finish` 却引用了不存在的证据编号。后两类在日志中有 `decision_error`。另逐条检查了这 965 份轨迹中 Planner 原始回复的显式 `"decision":"finish"` 字段。终局前仅命中上述三次；七条写出该字段而未获接受的回复都在终局后。

ALFWorld 每个模型、任务、架构只取最终合并清单的当前记录。ScienceWorld 两份快照按 `workspace_id` 去重，重合的 43 条事件和结果一致。另查各正式目录 `attempts/` 的 PC 归档，按工作区去重后 560 条，未见已接受的结束建议。开发验收另计，[live-02](runs/live-02/pc.json) 有一次终局后 `finish`，开发集 [benchmark-01](runs/benchmark-01/manifest.json) 有两次，均为原生满分；[live-01](runs/live-01/pc.json) 的委派因格式错误被拒绝。原始运行文件取自本地 `runs/`。

## 逐条审核索引

正式运行中全部 186 条终局后获接受的建议按环境和模型列出。每个链接标为“任务 ID · #决定事件”，对应轨迹中的 `planner_decision`，可由其 `model_event_id` 找到原始输入和回复。ScienceWorld 原始 JSON 使用 gzip 压缩。

<details>
<summary>ALFWorld · DeepSeek-V4.1-Flash（34 条）</summary>

[3 · #41](runs/alfworld-test-01-recovery-03/trials/m1-t3-pc.json) · [14 · #41](runs/alfworld-test-01-recovery-03/trials/m1-t14-pc.json) · [15 · #35](runs/alfworld-test-01-recovery-03/trials/m1-t15-pc.json) · [35 · #35](runs/alfworld-test-01-recovery-03/trials/m1-t35-pc.json) · [42 · #35](runs/alfworld-test-01-recovery-03/trials/m1-t42-pc.json) · [46 · #33](runs/alfworld-test-01-recovery-03/trials/m1-t46-pc.json) · [47 · #25](runs/alfworld-test-01-recovery-03/trials/m1-t47-pc.json) · [48 · #35](runs/alfworld-test-01-recovery-03/trials/m1-t48-pc.json) · [54 · #43](runs/alfworld-test-01-recovery-03/trials/m1-t54-pc.json) · [57 · #33](runs/alfworld-test-01-recovery-03/trials/m1-t57-pc.json) · [60 · #41](runs/alfworld-test-01-recovery-03/trials/m1-t60-pc.json) · [68 · #33](runs/alfworld-test-01-recovery-03/trials/m1-t68-pc.json) · [71 · #35](runs/alfworld-test-01-recovery-03/trials/m1-t71-pc.json) · [72 · #25](runs/alfworld-test-01-recovery-03/trials/m1-t72-pc.json) · [78 · #41](runs/alfworld-test-01-recovery-03/trials/m1-t78-pc.json) · [86 · #19](runs/alfworld-test-01-recovery-03/trials/m1-t86-pc.json) · [87 · #43](runs/alfworld-test-01-recovery-03/trials/m1-t87-pc.json) · [100 · #35](runs/alfworld-test-01-recovery-03/trials/m1-t100-pc.json) · [105 · #41](runs/alfworld-test-01-recovery-03/trials/m1-t105-pc.json) · [107 · #25](runs/alfworld-test-01-recovery-03/trials/m1-t107-pc.json) · [108 · #41](runs/alfworld-test-01-recovery-03/trials/m1-t108-pc.json) · [110 · #25](runs/alfworld-test-01-recovery-03/trials/m1-t110-pc.json) · [112 · #19](runs/alfworld-test-01-recovery-03/trials/m1-t112-pc.json) · [113 · #33](runs/alfworld-test-01-recovery-03/trials/m1-t113-pc.json) · [116 · #19](runs/alfworld-test-01-recovery-03/trials/m1-t116-pc.json) · [118 · #19](runs/alfworld-test-01-recovery-03/trials/m1-t118-pc.json) · [120 · #41](runs/alfworld-test-01-recovery-03/trials/m1-t120-pc.json) · [121 · #35](runs/alfworld-test-01-recovery-03/trials/m1-t121-pc.json) · [123 · #35](runs/alfworld-test-01-recovery-03/trials/m1-t123-pc.json) · [125 · #41](runs/alfworld-test-01-recovery-03/trials/m1-t125-pc.json) · [126 · #43](runs/alfworld-test-01-recovery-03/trials/m1-t126-pc.json) · [129 · #43](runs/alfworld-test-01-recovery-03/trials/m1-t129-pc.json) · [130 · #25](runs/alfworld-test-01-recovery-03/trials/m1-t130-pc.json) · [131 · #41](runs/alfworld-test-01-recovery-03/trials/m1-t131-pc.json)

</details>

<details>
<summary>ALFWorld · MiniMax-M3.1-Flash（41 条）</summary>

[2 · #35](runs/alfworld-test-01-recovery-03/trials/m2-t2-pc.json) · [3 · #41](runs/alfworld-test-01-recovery-03/trials/m2-t3-pc.json) · [4 · #33](runs/alfworld-test-01-recovery-03/trials/m2-t4-pc.json) · [5 · #35](runs/alfworld-test-01-recovery-03/trials/m2-t5-pc.json) · [8 · #41](runs/alfworld-test-01-recovery-03/trials/m2-t8-pc.json) · [11 · #35](runs/alfworld-test-01-recovery-03/trials/m2-t11-pc.json) · [14 · #41](runs/alfworld-test-01-recovery-03/trials/m2-t14-pc.json) · [21 · #35](runs/alfworld-test-01-recovery-03/trials/m2-t21-pc.json) · [22 · #33](runs/alfworld-test-01-recovery-03/trials/m2-t22-pc.json) · [29 · #41](runs/alfworld-test-01-recovery-03/trials/m2-t29-pc.json) · [32 · #35](runs/alfworld-test-01-recovery-03/trials/m2-t32-pc.json) · [35 · #35](runs/alfworld-test-01-recovery-03/trials/m2-t35-pc.json) · [41 · #43](runs/alfworld-test-01-recovery-03/trials/m2-t41-pc.json) · [42 · #41](runs/alfworld-test-01-recovery-03/trials/m2-t42-pc.json) · [43 · #35](runs/alfworld-test-01-recovery-03/trials/m2-t43-pc.json) · [47 · #25](runs/alfworld-test-01-recovery-03/trials/m2-t47-pc.json) · [54 · #43](runs/alfworld-test-01-recovery-03/trials/m2-t54-pc.json) · [56 · #27](runs/alfworld-test-01-recovery-03/trials/m2-t56-pc.json) · [57 · #33](runs/alfworld-test-01-recovery-03/trials/m2-t57-pc.json) · [62 · #35](runs/alfworld-test-01-recovery-03/trials/m2-t62-pc.json) · [65 · #35](runs/alfworld-test-01-recovery-03/trials/m2-t65-pc.json) · [67 · #25](runs/alfworld-test-01-recovery-03/trials/m2-t67-pc.json) · [68 · #33](runs/alfworld-test-01-recovery-03/trials/m2-t68-pc.json) · [70 · #27](runs/alfworld-test-01-recovery-03/trials/m2-t70-pc.json) · [74 · #33](runs/alfworld-test-01-recovery-03/trials/m2-t74-pc.json) · [85 · #19](runs/alfworld-test-01-recovery-03/trials/m2-t85-pc.json) · [93 · #35](runs/alfworld-test-01-recovery-03/trials/m2-t93-pc.json) · [96 · #43](runs/alfworld-test-01-recovery-03/trials/m2-t96-pc.json) · [98 · #19](runs/alfworld-test-01-recovery-03/trials/m2-t98-pc.json) · [100 · #35](runs/alfworld-test-01-recovery-03/trials/m2-t100-pc.json) · [101 · #43](runs/alfworld-test-01-recovery-03/trials/m2-t101-pc.json) · [103 · #35](runs/alfworld-test-01-recovery-03/trials/m2-t103-pc.json) · [112 · #19](runs/alfworld-test-01-recovery-03/trials/m2-t112-pc.json) · [116 · #19](runs/alfworld-test-01-recovery-03/trials/m2-t116-pc.json) · [118 · #19](runs/alfworld-test-01-recovery-03/trials/m2-t118-pc.json) · [119 · #41](runs/alfworld-test-01-recovery-03/trials/m2-t119-pc.json) · [121 · #27](runs/alfworld-test-01-recovery-03/trials/m2-t121-pc.json) · [123 · #35](runs/alfworld-test-01-recovery-03/trials/m2-t123-pc.json) · [127 · #33](runs/alfworld-test-01-recovery-03/trials/m2-t127-pc.json) · [129 · #41](runs/alfworld-test-01-recovery-03/trials/m2-t129-pc.json) · [131 · #19](runs/alfworld-test-01-recovery-03/trials/m2-t131-pc.json)

</details>

<details>
<summary>ALFWorld · GLM-5.3-Flash（43 条）</summary>

[2 · #41](runs/alfworld-test-01-recovery-03/trials/m3-t2-pc.json) · [5 · #33](runs/alfworld-test-01-recovery-03/trials/m3-t5-pc.json) · [7 · #35](runs/alfworld-test-01-recovery-03/trials/m3-t7-pc.json) · [11 · #41](runs/alfworld-test-01-recovery-03/trials/m3-t11-pc.json) · [12 · #35](runs/alfworld-test-01-recovery-03/trials/m3-t12-pc.json) · [14 · #41](runs/alfworld-test-01-recovery-03/trials/m3-t14-pc.json) · [17 · #33](runs/alfworld-test-01-recovery-03/trials/m3-t17-pc.json) · [18 · #35](runs/alfworld-test-01-recovery-03/trials/m3-t18-pc.json) · [19 · #27](runs/alfworld-test-01-recovery-03/trials/m3-t19-pc.json) · [20 · #35](runs/alfworld-test-01-recovery-03/trials/m3-t20-pc.json) · [21 · #35](runs/alfworld-test-01-recovery-03/trials/m3-t21-pc.json) · [24 · #27](runs/alfworld-test-01-recovery-03/trials/m3-t24-pc.json) · [25 · #25](runs/alfworld-test-01-recovery-03/trials/m3-t25-pc.json) · [29 · #33](runs/alfworld-test-01-recovery-03/trials/m3-t29-pc.json) · [35 · #35](runs/alfworld-test-01-recovery-03/trials/m3-t35-pc.json) · [41 · #43](runs/alfworld-test-01-recovery-03/trials/m3-t41-pc.json) · [42 · #41](runs/alfworld-test-01-recovery-03/trials/m3-t42-pc.json) · [52 · #43](runs/alfworld-test-01-recovery-03/trials/m3-t52-pc.json) · [65 · #33](runs/alfworld-test-01-recovery-03/trials/m3-t65-pc.json) · [66 · #41](runs/alfworld-test-01-recovery-03/trials/m3-t66-pc.json) · [69 · #19](runs/alfworld-test-01-recovery-03/trials/m3-t69-pc.json) · [70 · #33](runs/alfworld-test-01-recovery-03/trials/m3-t70-pc.json) · [72 · #25](runs/alfworld-test-01-recovery-03/trials/m3-t72-pc.json) · [76 · #33](runs/alfworld-test-01-recovery-03/trials/m3-t76-pc.json) · [78 · #41](runs/alfworld-test-01-recovery-03/trials/m3-t78-pc.json) · [81 · #35](runs/alfworld-test-01-recovery-03/trials/m3-t81-pc.json) · [85 · #19](runs/alfworld-test-01-recovery-03/trials/m3-t85-pc.json) · [90 · #43](runs/alfworld-test-01-recovery-03/trials/m3-t90-pc.json) · [95 · #35](runs/alfworld-test-01-recovery-03/trials/m3-t95-pc.json) · [100 · #43](runs/alfworld-test-01-recovery-03/trials/m3-t100-pc.json) · [101 · #35](runs/alfworld-test-01-recovery-03/trials/m3-t101-pc.json) · [106 · #35](runs/alfworld-test-01-recovery-03/trials/m3-t106-pc.json) · [107 · #25](runs/alfworld-test-01-recovery-03/trials/m3-t107-pc.json) · [108 · #43](runs/alfworld-test-01-recovery-03/trials/m3-t108-pc.json) · [109 · #33](runs/alfworld-test-01-recovery-03/trials/m3-t109-pc.json) · [112 · #19](runs/alfworld-test-01-recovery-03/trials/m3-t112-pc.json) · [115 · #35](runs/alfworld-test-01-recovery-03/trials/m3-t115-pc.json) · [116 · #19](runs/alfworld-test-01-recovery-03/trials/m3-t116-pc.json) · [120 · #35](runs/alfworld-test-01-recovery-03/trials/m3-t120-pc.json) · [123 · #35](runs/alfworld-test-01-recovery-03/trials/m3-t123-pc.json) · [125 · #35](runs/alfworld-test-01-recovery-03/trials/m3-t125-pc.json) · [129 · #43](runs/alfworld-test-01-recovery-03/trials/m3-t129-pc.json) · [130 · #25](runs/alfworld-test-01-recovery-03/trials/m3-t130-pc.json)

</details>

<details>
<summary>WebShop · DeepSeek-V4.1-Flash（22 条）</summary>

[27 · #33](runs/webshop-test-01/trials/m1-t27-pc.json) · [44 · #27](runs/webshop-test-01/trials/m1-t44-pc.json) · [61 · #27](runs/webshop-test-01/trials/m1-t61-pc.json) · [73 · #27](runs/webshop-test-01/trials/m1-t73-pc.json) · [82 · #35](runs/webshop-test-01/trials/m1-t82-pc.json) · [102 · #43](runs/webshop-test-01/trials/m1-t102-pc.json) · [194 · #19](runs/webshop-test-01/trials/m1-t194-pc.json) · [223 · #17](runs/webshop-test-01/trials/m1-t223-pc.json) · [250 · #19](runs/webshop-test-01/trials/m1-t250-pc.json) · [263 · #19](runs/webshop-test-01/trials/m1-t263-pc.json) · [317 · #27](runs/webshop-test-01/trials/m1-t317-pc.json) · [323 · #27](runs/webshop-test-01/trials/m1-t323-pc.json) · [348 · #27](runs/webshop-test-01/trials/m1-t348-pc.json) · [413 · #25](runs/webshop-test-01/trials/m1-t413-pc.json) · [419 · #19](runs/webshop-test-01/trials/m1-t419-pc.json) · [443 · #41](runs/webshop-test-01/trials/m1-t443-pc.json) · [456 · #17](runs/webshop-test-01/trials/m1-t456-pc.json) · [458 · #35](runs/webshop-test-01/trials/m1-t458-pc.json) · [465 · #41](runs/webshop-test-01/trials/m1-t465-pc.json) · [470 · #35](runs/webshop-test-01/trials/m1-t470-pc.json) · [471 · #19](runs/webshop-test-01/trials/m1-t471-pc.json) · [482 · #25](runs/webshop-test-01/trials/m1-t482-pc.json)

</details>

<details>
<summary>WebShop · MiniMax-M3.1-Flash（5 条）</summary>

[169 · #17](runs/webshop-test-01/trials/m2-t169-pc.json) · [366 · #25](runs/webshop-test-01/trials/m2-t366-pc.json) · [394 · #33](runs/webshop-test-01/trials/m2-t394-pc.json) · [448 · #33](runs/webshop-test-01/trials/m2-t448-pc.json) · [478 · #33](runs/webshop-test-01/trials/m2-t478-pc.json)

</details>

<details>
<summary>WebShop · GLM-5.3-Flash（10 条）</summary>

[21 · #33](runs/webshop-test-01/trials/m3-t21-pc.json) · [82 · #33](runs/webshop-test-01/trials/m3-t82-pc.json) · [127 · #19](runs/webshop-test-01/trials/m3-t127-pc.json) · [257 · #19](runs/webshop-test-01/trials/m3-t257-pc.json) · [328 · #33](runs/webshop-test-01/trials/m3-t328-pc.json) · [335 · #17](runs/webshop-test-01/trials/m3-t335-pc.json) · [384 · #17](runs/webshop-test-01/trials/m3-t384-pc.json) · [390 · #17](runs/webshop-test-01/trials/m3-t390-pc.json) · [447 · #27](runs/webshop-test-01/trials/m3-t447-pc.json) · [496 · #33](runs/webshop-test-01/trials/m3-t496-pc.json)

</details>

<details>
<summary>ScienceWorld · DeepSeek-V4.1-Flash（20 条）</summary>

[find-living-thing_275 · #33](runs/sciworld-test-01/trials/m1-tfind-living-thing_275-pc.json.gz) · [find-living-thing_294 · #25](runs/sciworld-test-01/trials/m1-tfind-living-thing_294-pc.json.gz) · [find-non-living-thing_264 · #13](runs/sciworld-test-01/trials/m1-tfind-non-living-thing_264-pc.json.gz) · [inclined-plane-determine-angle_159 · #69](runs/sciworld-test-01/trials/m1-tinclined-plane-determine-angle_159-pc.json.gz) · [inclined-plane-friction-named-surfaces_1112 · #61](runs/sciworld-test-01/trials/m1-tinclined-plane-friction-named-surfaces_1112-pc.json.gz) · [inclined-plane-friction-named-surfaces_1218 · #49](runs/sciworld-test-01/trials/m1-tinclined-plane-friction-named-surfaces_1218-pc.json.gz) · [inclined-plane-friction-named-surfaces_1256 · #61](runs/sciworld-test-01/trials/m1-tinclined-plane-friction-named-surfaces_1256-pc.json.gz) · [inclined-plane-friction-named-surfaces_1335 · #83](runs/sciworld-test-01/trials/m1-tinclined-plane-friction-named-surfaces_1335-pc.json.gz) · [measure-melting-point-known-substance_357 · #25](runs/sciworld-test-01/trials/m1-tmeasure-melting-point-known-substance_357-pc.json.gz) · [measure-melting-point-known-substance_385 · #61](runs/sciworld-test-01/trials/m1-tmeasure-melting-point-known-substance_385-pc.json.gz) · [measure-melting-point-unknown-substance_229 · #27](runs/sciworld-test-01/trials/m1-tmeasure-melting-point-unknown-substance_229-pc.json.gz) · [measure-melting-point-unknown-substance_242 · #25](runs/sciworld-test-01/trials/m1-tmeasure-melting-point-unknown-substance_242-pc.json.gz) · [measure-melting-point-unknown-substance_250 · #21](runs/sciworld-test-01/trials/m1-tmeasure-melting-point-unknown-substance_250-pc.json.gz) · [mendelian-genetics-unknown-plant_371 · #183](runs/sciworld-test-01/trials/m1-tmendelian-genetics-unknown-plant_371-pc.json.gz) · [test-conductivity_714 · #81](runs/sciworld-test-01/trials/m1-ttest-conductivity_714-pc.json.gz) · [test-conductivity_844 · #71](runs/sciworld-test-01/trials/m1-ttest-conductivity_844-pc.json.gz) · [test-conductivity_845 · #69](runs/sciworld-test-01/trials/m1-ttest-conductivity_845-pc.json.gz) · [use-thermometer_410 · #59](runs/sciworld-test-01/trials/m1-tuse-thermometer_410-pc.json.gz) · [use-thermometer_463 · #59](runs/sciworld-test-01/trials/m1-tuse-thermometer_463-pc.json.gz) · [use-thermometer_478 · #63](runs/sciworld-test-01/trials/m1-tuse-thermometer_478-pc.json.gz)

</details>

<details>
<summary>ScienceWorld · MiniMax-M3.1-Flash（2 条）</summary>

[find-non-living-thing_233 · #37](runs/sciworld-test-01-four-models/trials/m2-tfind-non-living-thing_233-pc.json.gz) · [measure-melting-point-known-substance_341 · #23](runs/sciworld-test-01-four-models/trials/m2-tmeasure-melting-point-known-substance_341-pc.json.gz)

</details>

<details>
<summary>ScienceWorld · GLM-5.3-Flash（9 条）</summary>

[find-animal_253 · #35](runs/sciworld-test-01-four-models/trials/m3-tfind-animal_253-pc.json.gz) · [find-living-thing_247 · #21](runs/sciworld-test-01-four-models/trials/m3-tfind-living-thing_247-pc.json.gz) · [find-non-living-thing_273 · #23](runs/sciworld-test-01-four-models/trials/m3-tfind-non-living-thing_273-pc.json.gz) · [inclined-plane-friction-named-surfaces_1050 · #37](runs/sciworld-test-01-four-models/trials/m3-tinclined-plane-friction-named-surfaces_1050-pc.json.gz) · [inclined-plane-friction-named-surfaces_1349 · #23](runs/sciworld-test-01-four-models/trials/m3-tinclined-plane-friction-named-surfaces_1349-pc.json.gz) · [inclined-plane-friction-named-surfaces_1352 · #25](runs/sciworld-test-01-four-models/trials/m3-tinclined-plane-friction-named-surfaces_1352-pc.json.gz) · [inclined-plane-friction-unnamed-surfaces_146 · #61](runs/sciworld-test-01-four-models/trials/m3-tinclined-plane-friction-unnamed-surfaces_146-pc.json.gz) · [measure-melting-point-known-substance_395 · #71](runs/sciworld-test-01-four-models/trials/m3-tmeasure-melting-point-known-substance_395-pc.json.gz) · [measure-melting-point-unknown-substance_283 · #57](runs/sciworld-test-01-four-models/trials/m3-tmeasure-melting-point-unknown-substance_283-pc.json.gz)

</details>

<details>
<summary>终局后模型写出 finish、但证据引用无效的 7 条</summary>

链接标为“任务 ID · #模型原文事件→#拒绝事件”。这七条的 `decision_error` 均为 `unknown_evidence_ref`，另有八条终局回复选择了不支持的决定。

- ALFWorld · GLM-5.3-Flash（5 条）　[50 · #24→#25](runs/alfworld-test-01-recovery-03/trials/m3-t50-pc.json) · [71 · #32→#33](runs/alfworld-test-01-recovery-03/trials/m3-t71-pc.json) · [73 · #24→#25](runs/alfworld-test-01-recovery-03/trials/m3-t73-pc.json) · [75 · #42→#43](runs/alfworld-test-01-recovery-03/trials/m3-t75-pc.json) · [94 · #26→#27](runs/alfworld-test-01-recovery-03/trials/m3-t94-pc.json)
- ScienceWorld · GLM-5.3-Flash（2 条）　[inclined-plane-determine-angle_128 · #26→#27](runs/sciworld-test-01-four-models/trials/m3-tinclined-plane-determine-angle_128-pc.json.gz) · [inclined-plane-friction-unnamed-surfaces_123 · #24→#25](runs/sciworld-test-01-four-models/trials/m3-tinclined-plane-friction-unnamed-surfaces_123-pc.json.gz)

</details>
