"""Render the planner-centered live run as a self-contained review page."""

import argparse
import json
import math
import os
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from html import escape
from pathlib import Path
from urllib.parse import quote

SRC = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SRC))

from toolkit.rollout.terminalbench import load_terminalbench_trial
from toolkit.tasks.terminalbench import TerminalBenchTask
from toolkit.utils.files import read_json, write_text_atomic

ROOT = SRC.parent
OUTPUT = ROOT / "experiments/planner-centered/audit.html"
MODES = {
    "eo": ("EO", "执行器自主完成整项任务"),
    "pe-s": ("PE-S", "执行前一次性交付整体规划"),
    "pe-d": ("PE-D", "按边界更新剩余整体规划，续接同一整项请求"),
    "pc": ("PC", "更新整体规划并委派新的有界阶段"),
}
EVENT_NAMES = {
    "initial_observation": "初始观察",
    "planner_decision": "Planner 决策",
    "execution_request": "执行请求",
    "tool_event": "环境交互",
    "tool_error": "环境错误",
    "decision_error": "规划协议错误",
    "runtime_error": "运行错误",
    "execution_feedback": "反馈返回",
    "stop": "运行停止",
    "verifier": "环境终局",
}
REASONS = {
    "budget_pause": "达到预设返回边界",
    "native_return": "阶段原生返回",
    "task_finish": "环境任务终止",
    "planner_finish": "Planner 建议结束",
    "executor_budget": "Executor 总额度耗尽",
    "planner_budget": "Planner 总额度耗尽",
    "protocol_error": "规划协议错误",
    "runtime_error": "运行错误",
}
ROLES = {"planner": "Planner", "executor": "Executor"}
BENCHMARK_EVIDENCE = {
    "ALFWorld": ("benchmark.py", "ALFWorld 原生 won 标志为真时得 1 分并计为成功，其余得 0 分。"),
    "ScienceWorld": ("sciworld_benchmark.py", "得分为 ScienceWorld 模拟器分数除以 100。原生分数达到 100 时计为成功。"),
    "WebShop": ("webshop_benchmark.py", "得分为 WebShop 原生购买奖励，可得部分分。已购买且奖励达到 1 时计为成功。"),
    "Terminal-Bench": ("terminal_benchmark.py", "得分为 Harbor 原生 Verifier 的有效 reward。奖励为 1 时计为成功。"),
}

STYLE = """
:root {
  color-scheme: dark;
  --page: #181825; --panel: #1e1e2e; --inset: #141420;
  --text: #edf0ff; --muted: #b9c1da; --line: #3b3d55;
  --planner: #cbb5fa; --executor: #9fc6fc; --return: #f2c781;
  --verifier: #a2dfb5; --fail: #ffb4bd;
  --mono: "IBM Plex Mono", "Maple Mono NF CN", ui-monospace, monospace;
  font: 16px/1.6 "Source Sans 3", "Noto Sans CJK SC", "Microsoft YaHei", system-ui, sans-serif;
  background: var(--page); color: var(--text);
}
* { box-sizing: border-box; }
body { margin: 0; }
p { margin: .55rem 0 0; max-width: 70ch; }
a { color: var(--planner); text-decoration-thickness: 1px; text-underline-offset: .22em; }
a:hover { color: var(--text); }
:focus-visible { outline: 2px solid var(--planner); outline-offset: 3px; }
::selection { background: #51466b; color: var(--text); }
.wrap { width: min(1200px, calc(100% - 5rem)); margin-inline: auto; }
.skip { position: absolute; top: -5rem; left: 1rem; }
.skip:focus { top: .5rem; z-index: 3; background: var(--inset); padding: .7rem; }
header { border-bottom: 1px solid var(--line); }
.masthead { display: flex; justify-content: space-between; align-items: center; gap: 1rem; min-height: 3.8rem; }
nav, .links, .legend { display: flex; flex-wrap: wrap; column-gap: 1.2rem; row-gap: .4rem; }
header a { text-decoration: none; color: var(--muted); }
header a:hover { text-decoration: underline; }
h1, h2, h3, h4 { margin: 0; line-height: 1.25; font-weight: 730; letter-spacing: -.025em; }
h1 { font-size: 2.78rem; text-wrap: balance; }
h2 { font-size: 1.65rem; }
h3 { font-size: 1.25rem; }
h4 { font-size: 1.05rem; }
.hero { display: grid; grid-template-columns: minmax(0, .84fr) minmax(0, 1.16fr); gap: 2.6rem; align-items: center; padding: 3rem 0 2.6rem; }
.hero p { margin-top: .9rem; }
.hero .task { padding-left: .9rem; border-left: 1px solid var(--planner); }
.task strong { display: block; margin-bottom: .2rem; }
.small, .muted { color: var(--muted); }
.small { font-size: .88rem; }
code, pre, .number, .mode, .sequence { font-family: var(--mono); font-variant-numeric: tabular-nums; }
code { font-size: .9em; overflow-wrap: anywhere; }
figure { margin: 0; background: var(--panel); border: 1px solid var(--line); border-radius: .8rem; padding: 1rem 1.15rem .9rem; }
figcaption { font-weight: 700; margin-bottom: .6rem; }
.track { display: grid; grid-template-columns: 3.5rem 1fr; align-items: baseline; gap: .65rem; padding: .47rem 0; border-top: 1px solid var(--line); }
.track > a { color: var(--text); font-weight: 650; text-decoration: none; }
.track > a:hover { text-decoration: underline; }
.sequence { display: flex; align-items: baseline; gap: .21rem; flex-wrap: wrap; min-width: 0; }
.mark { min-width: 1.25rem; border: 1px solid currentColor; border-radius: .22rem; padding: 0 .16rem; font: 650 .74rem/1.45 var(--mono); text-align: center; text-decoration: none; }
.mark:hover { background: var(--inset); text-decoration: underline; }
.planner { color: var(--planner); }
.executor { color: var(--executor); }
.return { color: var(--return); }
.verifier, .pass { color: var(--verifier); }
.fail { color: var(--fail); }
.legend { border-top: 1px solid var(--line); margin: .45rem 0 0; padding-top: .65rem; gap: .35rem .9rem; }
.legend strong { margin-right: .28rem; font: 650 .81rem var(--mono); }
section { padding: 2.25rem 0; border-top: 1px solid var(--line); }
.table-wrap { overflow-x: auto; margin-top: 1.1rem; border-block: 1px solid var(--line); }
table { width: 100%; border-collapse: collapse; text-align: left; font-size: .93rem; }
th, td { padding: .72rem .75rem; border-bottom: 1px solid var(--line); }
tbody tr:last-child > * { border-bottom: 0; }
thead th { font-size: .84rem; color: var(--muted); background: var(--panel); white-space: nowrap; }
tbody th { white-space: nowrap; }
.number { white-space: nowrap; }
.benchmark h3 { margin-top: 1.7rem; }
.benchmark .matrix th:not(:first-child), .benchmark .matrix td { text-align: center; }
.benchmark .matrix thead th { text-align: center; }
.benchmark .matrix tbody th { min-width: 12rem; white-space: normal; }
.benchmark .matrix td { min-width: 3.9rem; }
.benchmark .matrix th[scope="row"], .benchmark .matrix th[rowspan] { position: sticky; left: 0; z-index: 1; }
.benchmark .matrix th[scope="row"] { background: var(--page); }
.benchmark .matrix th[scope="colgroup"], .benchmark .matrix .group-start { border-left: 1px solid var(--line); }
.benchmark .score.pass a { color: var(--verifier); }
.benchmark .score.fail a { color: var(--fail); }
.benchmark .score a:hover { color: var(--text); }
.benchmark .model-rows + .model-rows tr:first-child > * { border-top: 1px solid var(--line); }
.benchmark .stops { min-width: 8.5rem; overflow-wrap: anywhere; }
.benchmark .links { margin-top: 1.05rem; }
.benchmark .reasoning { display: block; margin-top: .16rem; }
.benchmark .matrix-group { border-top: 1px solid var(--line); padding: .5rem 0; }
.benchmark .matrix-group .table-wrap { margin-top: .5rem; }
.checks { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0 1.5rem; margin-top: 1rem; }
.checks > div { border-top: 1px solid var(--line); padding: .65rem 0; }
.checks dt { font-weight: 700; margin-bottom: .15rem; }
dd { margin: 0; }
.trace { padding: 1.1rem 0; border-top: 1px solid var(--line); scroll-margin-top: 1.2rem; }
.trace:first-of-type { margin-top: 1.2rem; }
.trace-head { display: flex; flex-wrap: wrap; gap: .4rem 1rem; justify-content: space-between; align-items: baseline; }
.trace-title { display: flex; align-items: baseline; gap: .65rem; }
.trace > ol { list-style: none; padding: 0; margin: .75rem 0 0; }
.event { display: grid; grid-template-columns: 9.75rem minmax(0, 1fr); gap: 0 .9rem; border-top: 1px solid var(--line); padding: .57rem .35rem .57rem 0; scroll-margin-top: .8rem; }
.event:target { background: #302a48; border-radius: .3rem; }
.event-heading { color: var(--text); font-weight: 635; font-size: .88rem; }
.event-heading a { color: var(--muted); text-decoration: none; margin-right: .35rem; }
.event p { margin-top: 0; overflow-wrap: anywhere; }
.event .event-meta { margin: .26rem 0; display: block; }
details { margin-top: .45rem; }
summary { cursor: pointer; width: fit-content; color: var(--planner); padding: .1rem 0; }
summary:hover { color: var(--text); }
summary::marker { color: var(--planner); }
pre { white-space: pre-wrap; overflow-wrap: anywhere; background: var(--inset); color: var(--text); border: 1px solid var(--line); padding: .85rem; border-radius: .4rem; font-size: .83rem; max-height: 31rem; overflow: auto; }
footer { padding: 0 0 2.5rem; color: var(--muted); }
:target { scroll-margin-top: 1rem; }
@media (max-width: 875px) {
  .wrap { width: calc(100% - 2.5rem); }
  .hero { grid-template-columns: 1fr; gap: 1.35rem; padding: 2rem 0; }
}
@media (max-width: 520px) {
  .wrap { width: calc(100% - 1.5rem); }
  .masthead { display: block; padding: .65rem 0; }
  nav { margin-top: .25rem; }
  h1 { font-size: 2rem; }
  .event, .checks { grid-template-columns: 1fr; }
  .event-heading { margin-bottom: .2rem; }
  .benchmark .matrix tbody th { min-width: 9rem; }
}
@media print {
  :root { color-scheme: light; --page: #fff; --text: #161625; --muted: #434354; --line: #aaa; --panel: #f4f3f8; --inset: #f4f3f8; --planner: #503279; --executor: #22507a; --return: #654509; --verifier: #22562c; --fail: #802337; }
  .wrap { width: 100%; }
  .hero { grid-template-columns: 1fr; padding-block: 1rem; }
  nav, .skip { display: none; }
  figure, .event { break-inside: avoid; }
}
"""


def pretty(value):
    return json.dumps(value, ensure_ascii=False, indent=2)


def html(value):
    if value is None:
        return "未知"
    return escape(str(value))


def link(path, label, output, *, accessible_label=None):
    relative = os.path.relpath(Path(path).resolve(), output.parent)
    attributes = f' aria-label="{html(accessible_label)}" title="{html(accessible_label)}"' if accessible_label else ""
    return f'<a href="{html(quote(relative, safe="/"))}"{attributes}>{html(label)}</a>'


def details(label, payload):
    return f"<details><summary>{html(label)}</summary><pre>{html(pretty(payload))}</pre></details>"


def events(record, event_type):
    return [event for event in record.get("events", []) if event.get("type") == event_type]


def model_responses(record, role):
    return [
        event.get("response") for event in events(record, "model_call")
        if event.get("role") == role
    ]


def usage_count(response, field):
    usage = (response or {}).get("usage") or {}
    details = usage.get("prompt_tokens_details") or {}
    if field == "prompt_cache_hit_tokens":
        return usage.get(field, details.get("cached_tokens"))
    if field == "created_cache_tokens":
        return details.get(field)
    if field == "reasoning_tokens":
        return usage.get(field, (usage.get("completion_tokens_details") or {}).get(field))
    return usage.get(field)


def token_count(responses, field="total_tokens"):
    if not responses:
        return "0"
    values = [usage_count(response, field) for response in responses]
    known = [value for value in values if type(value) is int]
    if not known:
        return "未知"
    return ("" if len(known) == len(values) else "≥") + f"{sum(known):,}"


def reason_label(reason):
    return REASONS.get(reason, reason or "未知")


def feedback_label(mode, reason):
    if mode in ("eo", "pe-s") and reason == "budget_pause":
        return "达到执行检查点，沿原请求续接"
    return reason_label(reason)


def elapsed(record):
    timeline = record.get("events", [])
    if len(timeline) < 2:
        return "未知"
    try:
        start, end = (
            datetime.fromisoformat(event["timestamp"].replace("Z", "+00:00"))
            for event in (timeline[0], timeline[-1])
        )
        return f"{(end - start).total_seconds():.1f} s"
    except (KeyError, TypeError, ValueError):
        return "未知"


def task_outcome(record):
    verifier = next(iter(events(record, "verifier")), {})
    success = verifier.get("success")
    if success is True:
        return '<strong class="pass">成功</strong>'
    if success is False:
        return '<strong class="fail">未成功</strong>'
    return "未判定"


def event_anchor(mode, event_id):
    return f"{mode}-e{html(event_id)}"


def timeline(mode, record):
    label = MODES[mode][0]
    if record is None:
        return f'<div class="track"><span class="mode">{label}</span><span class="small">无运行记录</span></div>'
    markers = []
    for event in record.get("events", []):
        kind = event["type"]
        if kind == "model_call":
            role = event["role"]
            mark = "P" if role == "planner" else "E"
            css = role
            name = f"{ROLES[role]} 调用"
            if event.get("response") is None:
                mark += "!"
                name += "未返回响应"
        elif kind == "execution_feedback":
            mark, css, name = "R", "return", feedback_label(mode, event.get("return_reason"))
        elif kind == "execution_request" and event.get("stage_objective"):
            mark, css, name = "D", "planner", "委派有界阶段"
        elif kind == "execution_request" and event.get("soft_guidance"):
            mark, css, name = "G", "planner", "交付整项任务指导"
        elif kind == "verifier":
            mark, css, name = "V", "verifier", "环境终局"
        else:
            continue
        anchor = event_anchor(mode, event["event_id"])
        name = html(f"{name} · 事件 {event['event_id']}")
        markers.append(f'<a class="mark {css}" href="#{anchor}" aria-label="{name}" title="{name}">{mark}</a>')
    sequence = "".join(markers) or '<span class="small">暂无事件</span>'
    return f'<div class="track"><a class="mode" href="#{mode}">{label}</a><div class="sequence">{sequence}</div></div>'


def result_row(mode, record):
    label = MODES[mode][0]
    if record is None:
        return f'<tr><th scope="row">{label}</th><td colspan="7">无运行记录</td></tr>'
    planner, executor = (model_responses(record, role) for role in ROLES)
    tasks = events(record, "tool_event")
    tools = sum(event.get("dispatched", event.get("action") is not None) for event in tasks)
    pauses = sum(event.get("return_reason") in ("budget_pause", "native_return")
                 for event in events(record, "execution_feedback"))
    stop = next(iter(events(record, "stop")), {})
    return (
        f'<tr><th scope="row"><a href="#{mode}" class="mode">{label}</a></th>'
        f'<td>{task_outcome(record)}</td>'
        f'<td class="number">{len(planner)} / {len(executor)}</td>'
        f'<td class="number">{tools}</td><td class="number">{pauses}</td>'
        f'<td class="number">{token_count(planner + executor)}</td>'
        f'<td class="number">{elapsed(record)}</td>'
        f'<td>{html(reason_label(stop.get("reason")))}</td></tr>'
    )


def links_to_events(mode, refs, label="事件引用"):
    if not refs:
        return ""
    links = []
    for ref in refs:
        if type(ref) is int:
            links.append(f'<a href="#{event_anchor(mode, ref)}">#{ref}</a>')
        else:
            links.append(f"<code>{html(ref)}</code>")
    return f'<div class="small">{label} {" · ".join(links)}</div>'


def render_event(mode, event, previous):
    kind, event_id = event["type"], event["event_id"]
    name = EVENT_NAMES.get(kind, kind)
    refs = event.get("evidence_refs") or event.get("tool_event_refs")
    model_ref = event.get("model_event_id")
    if kind == "model_call":
        role = event["role"]
        response = event.get("response") or {}
        name = f"{ROLES[role]} 调用"
        if event.get("response") is None:
            excerpt = f'未返回响应 · {html(event.get("error"))}'
        else:
            excerpt = f'{html(response.get("model"))} · {token_count([response])} token'
        label = "查看请求消息与模型回复"
    elif kind == "initial_observation":
        excerpt = html(event.get("observation"))
        label = "查看初始公开观察"
    elif kind == "planner_decision":
        decision = event.get("decision")
        excerpt = {"guide": "更新整项任务指导", "delegate": "委派有界阶段", "finish": "建议整项任务结束"}.get(decision, html(decision))
        label = "查看规划状态、约束和证据"
    elif kind == "execution_request":
        objective = event.get("stage_objective")
        excerpt = html(objective) if objective else "整项任务"
        label = "查看完整请求与外部指导"
    elif kind == "tool_event":
        action = event.get("action")
        dispatched = event.get("dispatched", action is not None)
        command = f"<code>{html(action)}</code>" if dispatched else "动作格式无效，未发送到环境"
        excerpt = f'{command} · {html(event.get("observation"))}'
        label = "查看日志观察与模型事件"
    elif kind == "execution_feedback":
        excerpt = html(feedback_label(mode, event.get("return_reason")))
        label = "查看反馈、证据和预算"
    elif kind == "stop":
        excerpt = html(reason_label(event.get("reason")))
        label = "查看停止事件"
    elif kind == "verifier":
        excerpt = f'{task_outcome({"events": [event]})} · 原生奖励 {html(event.get("reward"))}'
        label = "查看环境判定记录"
    elif kind.endswith("_error"):
        excerpt, label = html(event.get("error")), "查看错误记录"
    else:
        excerpt, label = "", "查看事件"
    anchor = event_anchor(mode, event_id)
    request = event.get("request_id")
    version = event.get("plan_version")
    context = []
    if request is not None:
        context.append(f"请求 {html(request)}")
    if version is not None:
        context.append(f"规划版本 {html(version)}")
    metadata = f'<span class="small event-meta">{" · ".join(context)}</span>' if context else ""
    evidence = links_to_events(mode, refs)
    if model_ref is not None:
        evidence += links_to_events(mode, [model_ref], "对应模型调用")
    elif kind.endswith("_error") and previous is not None:
        evidence += links_to_events(mode, [previous["event_id"]], "此前事件")
    return (
        f'<li class="event" id="{anchor}"><div class="event-heading">'
        f'<a class="number" href="#{anchor}" aria-label="事件 {html(event_id)}">#{html(event_id)}</a>{html(name)}</div>'
        f"<div><p>{excerpt}</p>{metadata}{evidence}{details(label, event)}</div></li>"
    )


def trace(mode, record, raw_path, output):
    if record is None:
        return ""
    label, semantic = MODES[mode]
    usage = {
        ROLES[role]: {
            name: token_count(model_responses(record, role), field)
            for name, field in (
                ("输入", "prompt_tokens"), ("输出", "completion_tokens"),
                ("缓存命中", "prompt_cache_hit_tokens"), ("缓存未命中", "prompt_cache_miss_tokens"),
                ("新建缓存", "created_cache_tokens"),
                ("总量", "total_tokens"),
            )
        }
        for role in ROLES
    }
    raw_link = link(raw_path, f"下载 {label} 原始 JSON", output)
    timeline = record.get("events", [])
    log = "".join(render_event(mode, event, timeline[index - 1] if index else None)
                  for index, event in enumerate(timeline))
    return (
        f'<article class="trace" id="{mode}"><div class="trace-head"><div class="trace-title">'
        f'<h3 class="mode">{label}</h3><span class="muted">{semantic}</span></div>{raw_link}</div>'
        f'<p class="small">工作区 <code>{html(record.get("workspace_id"))}</code></p>'
        f"{details('查看 Planner 与 Executor 的分项用量（token）', usage)}"
        f'<ol aria-label="{label} 事件">{log}</ol></article>'
    )


def observed(record):
    decisions = events(record, "planner_decision")
    requests = events(record, "execution_request")
    versions = sorted({event["plan_version"] for event in decisions if event.get("plan_version") is not None})
    request_ids = {event["request_id"] for event in requests if event.get("request_id") is not None}
    stage_count = sum(bool(event.get("stage_objective")) for event in requests)
    responses = model_responses(record, "planner")
    returned = sum(response is not None for response in responses)
    versions_text = "、".join(str(version) for version in versions) or "无"
    errors = [event for event in record.get("events", []) if event["type"].endswith("_error")]
    issues = "".join(f" {EVENT_NAMES.get(event['type'], event['type'])} {event.get('error')}。" for event in errors)
    return (f"Planner 返回 {returned} 次。整项或阶段请求 ID 共 {len(request_ids)} 个，"
            f"其中有界阶段请求 {stage_count} 次。已记录的 Planner 决策版本为 {versions_text}。{issues}")


def protocol_row(mode, record):
    label, description = MODES[mode]
    if record is None:
        return f"<div><dt>{label} · {description}</dt><dd>无运行记录</dd></div>"
    decisions = events(record, "planner_decision")
    relevant = decisions or events(record, "decision_error") or events(record, "execution_request")
    refs = links_to_events(mode, [event["event_id"] for event in relevant], "查看关键事件")
    return f"<div><dt>{label} · {description}</dt><dd>{html(observed(record))}{refs}</dd></div>"


@dataclass(frozen=True)
class BenchmarkTrial:
    path: Path
    has_record: bool
    past: tuple[Path | None, ...]
    score: float | None
    success: bool | None
    stop: str
    cost: Counter
    replay: Path | None = None
    harbor_budget: Path | None = None


def accumulate_attempt_cost(cost, record):
    failed_before_events = record.get("status") == "error" and record.get("events") == []
    if not failed_before_events and not events(record, "stop"):
        cost["incomplete"] += 1
    cost["actions"] += sum(event.get("dispatched", event.get("action") is not None)
                           for event in events(record, "tool_event"))
    for call in events(record, "model_call"):
        cost[call["role"]] += 1
        if call.get("error") in {"PromptBudgetExceeded", "RequestBudgetExceeded"}:
            cost["undispatched"] += 1
            continue
        for field in ("total_tokens", "reasoning_tokens"):
            value = usage_count(call.get("response"), field)
            if type(value) is int:
                cost[field] += value
                cost[f"known_{field}"] += 1


def benchmark_token_count(cost, field):
    expected = sum(cost[role] for role in ROLES) - cost["undispatched"] + cost["incomplete"]
    known = cost[f"known_{field}"]
    if not expected:
        return "0"
    if not known:
        return "未知"
    return ("" if known == expected else "≥") + f"{cost[field]:,}"


def load_benchmark_attempt(path, run_id, trial_id, configuration, attempt):
    try:
        record = read_json(path)
    except FileNotFoundError:
        return None
    if attempt is Ellipsis:
        attempt = record.get("attempt")
        if type(attempt) is not int or attempt < 1:
            raise ValueError(f"Invalid benchmark attempt in {path}")
    identity = (record.get("run_id"), record.get("trial_id"), record.get("model"),
                record.get("task_id"), record.get("mode"))
    if (identity != (run_id, trial_id, *configuration)
            or (attempt is not None and (record.get("attempt") != attempt
                                         or record.get("workspace_id") != f"{run_id}/{trial_id}/attempt-{attempt}"))):
        raise ValueError(f"Wrong benchmark trial identity in {path}")
    return record


def load_webshop_replay(path, source, record, max_input_bytes):
    replay = read_json(path)
    keys = ("run_id", "trial_id", "model", "task_id", "mode", "attempt", "workspace_id")
    calls = events(record, "model_call")
    call = calls[-1] if calls else {}
    tools = events(record, "tool_event")
    input_bytes = len(json.dumps(call.get("messages"), ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    outcome = replay.get("outcome") or {}
    score, success = outcome.get("reward"), outcome.get("success")
    if (record.get("status") != "unscored"
            or record.get("outcome") != {"reason": "runtime_error", "reward": None, "success": None}
            or any(replay.get(key) != record.get(key) for key in keys)
            or replay.get("source") != source or replay.get("method") != "webshop_native_context_limit_replay"
            or call.get("error") != "PromptBudgetExceeded" or call.get("role") != "executor"
            or call.get("response") is not None or replay.get("blocked_call_event_id") != call.get("event_id")
            or replay.get("tool_events_replayed") != len(tools) or any(t["event_id"] >= call["event_id"] for t in tools)
            or replay.get("max_input_bytes") != max_input_bytes or replay.get("input_bytes") != input_bytes
            or input_bytes <= max_input_bytes or outcome.get("reason") != "prompt_budget"
            or type(score) not in (int, float) or score != 0 or success is not False):
        raise ValueError(f"WebShop native replay does not match its original trial in {path}")
    return score, success


def load_terminal_budget_result(run_dir, benchmark, task, record, max_input_bytes):
    """Return the existing independent grade for a prompt blocked before dispatch."""
    if (record.get("status") != "unscored"
            or record.get("outcome") != {"reason": "runtime_error", "reward": None, "success": None}):
        return None
    suffix = record.get("events", [])[-5:]
    kinds = [event["type"] for event in suffix]
    if kinds == ["model_call", "execution_feedback", "runtime_error", "stop", "verifier"]:
        if suffix[1].get("return_reason") != "runtime_error":
            return None
        del suffix[1]
    elif kinds[-4:] == ["model_call", "runtime_error", "stop", "verifier"]:
        suffix = suffix[-4:]
    else:
        return None
    call, failure, _, verifier = suffix
    messages = call.get("messages")
    if (call.get("role") not in ROLES or call.get("status") != "error"
            or call.get("error") != "PromptBudgetExceeded" or failure.get("error") != "PromptBudgetExceeded"
            or "response" not in call or call["response"] is not None
            or not isinstance(messages, list) or not messages or not all(isinstance(item, dict) for item in messages)
            or messages[-1].get("role") != "user" or type(max_input_bytes) is not int or max_input_bytes < 1
            or len(json.dumps(messages, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) <= max_input_bytes):
        return None
    harbor = record.get("harbor")
    pins = {"release": benchmark.get("data_version"), "commit": benchmark.get("source_commit"),
            "task_version": task.get("task_version"), "agent_network": "no-network",
            "verifier_phase_network": "no-network"}
    if not isinstance(harbor, dict) or any(not value or harbor.get(key) != value for key, value in pins.items()):
        return None
    source = verifier.get("native_result")
    if not isinstance(source, str) or harbor.get("result") != source:
        return None
    result = Path(source)
    if result.name != "result.json" or result.parent.parent != run_dir.resolve() / "harbor":
        return None
    lock = result.with_name("lock.json")
    if harbor.get("lock") != str(lock):
        return None
    try:
        if any(path.resolve() != path or not path.is_file() for path in (result, lock)):
            return None
        native = read_json(result)
        if (not isinstance(native, dict) or native.get("verifier_environment_mode") != "separate"
                or native.get("reward_valid") is not True or "exception_info" not in native
                or native["exception_info"] is not None or native.get("trial_name") != result.parent.name
                or datetime.fromisoformat(native["finished_at"]) != datetime.fromisoformat(verifier["timestamp"])):
            return None
        imported = load_terminalbench_trial(
            result, TerminalBenchTask(f'terminal-bench/{task["task_id"]}', task["task_version"], ""),
        )
    except (KeyError, OSError, RuntimeError, TypeError, ValueError):
        return None
    return imported["reward"], imported["success"], result


def load_benchmark_trials(run_dir, manifest, *, preview=False):
    trials = {}
    versioned = manifest.get("schema_version", 1) >= 2
    benchmark = manifest["benchmark"]
    terminal_tasks = ({task["task_id"]: task for task in benchmark["tasks"]}
                      if benchmark["name"] == "Terminal-Bench" and benchmark.get("selection") == "reviewed_subset"
                      else {})
    for trial_id, trial in manifest["trials"].items():
        key = (trial["model"], trial["task_id"], trial["mode"])
        if key in trials:
            raise ValueError(f"Duplicate benchmark configuration {key}")
        path = run_dir / manifest["records"][trial_id]
        if preview:
            record = load_benchmark_attempt(path, manifest["run_id"], trial_id, key, Ellipsis if versioned else None)
            suffix = "".join(path.suffixes)
            archived_paths = sorted((run_dir / "attempts" / trial_id).glob(f"attempt-*{suffix}"))
            if record is not None and versioned:
                # A retry can archive the record after the atomic read.
                prior = record["attempt"] - 1
                if len(archived_paths) < prior:
                    raise ValueError(f"Missing earlier benchmark attempts in {path}")
                archived_paths = archived_paths[:prior]
            status = record["status"] if record else "queued"
        else:
            archived_paths = [run_dir / relative for relative in trial.get("archived_attempts", [])]
            attempt = len(archived_paths) + 1 if versioned else None
            record = load_benchmark_attempt(path, manifest["run_id"], trial_id, key, attempt)
            status = trial["status"]
        if archived_paths and len({item.resolve() for item in [path, *archived_paths]}) != len(archived_paths) + 1:
            raise ValueError(f"Duplicate benchmark attempt path for {trial_id}")
        stop = next(iter(events(record or {}, "stop")), {})
        verifier = next(iter(events(record or {}, "verifier")), {})
        if verifier:
            last_events = record["events"][-2:]
            outcome = record.get("outcome") or {}
            if (last_events != [stop, verifier] or stop.get("reason") != outcome.get("reason")
                    or any(verifier.get(field) != outcome.get(field) for field in ("reason", "reward", "success"))):
                raise ValueError(f"Verifier does not match the recorded terminal outcome in {path}")
        score = verifier.get("reward")
        success = verifier.get("success")
        if score is not None and (type(score) not in (int, float) or not math.isfinite(score) or type(success) is not bool):
            raise ValueError(f"Invalid benchmark score or success flag in {path}")
        if (status == "complete") != (score is not None):
            raise ValueError(f"Benchmark score and completed status disagree for {path}")
        error_source = (record or {}) if preview else trial
        error = error_source.get("error") if score is None else None
        if stop:
            reason = stop.get("reason")
            label = reason_label(reason)
            error_type = {"protocol_error": "decision_error", "runtime_error": "runtime_error"}.get(reason)
            errors = events(record, error_type) if error_type is not None else []
            if errors and error is None:
                error = errors[-1].get("error")
        elif status == "error":
            label = "运行启动或基础设施错误"
        elif preview:
            label = "轨迹尚未结束" if record else "尚无当前轨迹"
        else:
            label = "无停止事件"
        if error:
            label += f" · {error}"
        replay = run_dir / "native-replay" / f"{trial_id}.json"
        if benchmark["name"] == "WebShop" and replay.is_file():
            score, success = load_webshop_replay(replay, manifest["records"][trial_id], record or {},
                                                 manifest["budget"]["max_input_bytes_per_request"])
            label = "输入预算耗尽 · 原生重放"
        else:
            replay = None
        harbor_budget = None
        budget_error = error if preview else trial.get("error")
        if status == "unscored" and budget_error == "PromptBudgetExceeded" and record and key[1] in terminal_tasks:
            native = load_terminal_budget_result(
                run_dir, benchmark, terminal_tasks[key[1]], record, manifest["budget"].get("max_input_bytes_per_request"),
            )
            if native is not None:
                score, success, harbor_budget = native
                label = "输入预算耗尽 · Harbor 原生评分"
        cost = Counter()
        accumulate_attempt_cost(cost, record or {})
        past = []
        for index, archive_path in enumerate(archived_paths, 1):
            archive = load_benchmark_attempt(archive_path, manifest["run_id"], trial_id, key,
                                             index if versioned else None)
            accumulate_attempt_cost(cost, archive or {})
            past.append(archive_path if archive is not None else None)
        trials[key] = BenchmarkTrial(path, record is not None, tuple(past), score, success, label, cost,
                                     replay, harbor_budget)
    return trials


def benchmark_score_row(mode, model, trials, model_scores, shared_scores, add_model):
    scores = [trial.score for trial in trials if trial.score is not None]
    count = len(scores)
    total = math.fsum(scores)
    average = f"{total / count:.4g}" if count else "未评"
    model_average = f"{math.fsum(model_scores) / len(model_scores):.4g}" if model_scores else "未评"
    shared_average = f"{math.fsum(shared_scores) / len(shared_scores):.4g}" if shared_scores else "未评"
    failure_count = sum(trial.score is not None and trial.success is False for trial in trials)
    unavailable = len(trials) - count
    cost = Counter()
    for trial in trials:
        cost.update(trial.cost)
    incomplete = cost["incomplete"]
    request_counts = " / ".join(
        (f"≥{cost[role]}" if cost[role] else "未知") if incomplete else str(cost[role])
        for role in ROLES
    )
    action_count = cost["actions"]
    actions = str(action_count) if not incomplete else f"≥{action_count}" if action_count else "未知"
    stops = Counter(trial.stop for trial in trials)
    stop_text = "<br>".join(f"{html(reason)} ×{amount}" for reason, amount in stops.items())
    model_cell = (
        f'<th scope="rowgroup" rowspan="{len(MODES)}">{html(model)}<br>'
        f'<span class="small">配对任务 {len(model_scores):,} / {len(trials):,}</span></th>'
        if add_model else ""
    )
    return (
        f'<tr>{model_cell}<th scope="row" class="mode">{MODES[mode][0]}</th>'
        f'<td class="number">{average}</td><td class="number">{model_average}</td>'
        f'<td class="number"><strong>{shared_average}</strong></td>'
        f'<td class="number">{total:g} / {count}</td>'
        f'<td class="number">{count} / {len(trials)}</td><td class="number">{failure_count} / {unavailable}</td>'
        f'<td class="number">{actions}</td><td class="number">{request_counts}</td>'
        f'<td class="number">{benchmark_token_count(cost, "total_tokens")}'
        f'<span class="reasoning small">推理 {benchmark_token_count(cost, "reasoning_tokens")}</span></td>'
        f'<td class="stops">{stop_text}</td></tr>'
    )


def benchmark_task_row(task, models, trials, output):
    task_id = task["task_id"]
    cells = []
    for model in models:
        for index, (mode, (mode_label, _)) in enumerate(MODES.items()):
            trial = trials[model, task_id, mode]
            group = " group-start" if index == 0 else ""
            if trial.score is None:
                description = html(f"{model} · {mode_label} · 任务 {task_id} · 缺评 · {trial.stop}")
                cells.append(f'<td class="number score muted{group}" '
                             f'aria-label="{description}" title="{description}">缺评</td>')
                continue
            css = "pass" if trial.success else "fail"
            text = f"{trial.score:g}"
            description = f"{model} · {mode_label} · 任务 {task_id} · {text} · {trial.stop}"
            content = (link(trial.path, text, output, accessible_label=f"{description} · 最终评分轨迹")
                       if trial.has_record else f'<span title="{html(description)}">{text}</span>')
            for source, label in ((trial.replay, "原生重放"), (trial.harbor_budget, "Harbor 原生评分")):
                if source:
                    evidence = link(source, label, output, accessible_label=f"{description} · {label}证据")
                    content += f'<br><span class="small">{evidence}</span>'
            cells.append(f'<td class="number score {css}{group}">{content}</td>')
    goal = task.get("goal") or task.get("task")
    return f'<tr><th scope="row"><span class="number">{html(task_id)}</span> · {html(goal)}</th>{"".join(cells)}</tr>'


def benchmark_matrix(tasks, models, trials, output):
    columns = f'<colgroup span="{len(MODES)}"></colgroup>' * len(models)
    model_headers = "".join(f'<th scope="colgroup" colspan="{len(MODES)}">{html(model)}</th>' for model in models)
    mode_headers = len(models) * "".join(
        f'<th scope="col" class="{"group-start" if index == 0 else ""}">{label}</th>'
        for index, (label, _) in enumerate(MODES.values())
    )
    page_size = 24
    groups = []
    for start in range(0, len(tasks), page_size):
        page = tasks[start:start + page_size]
        rows = "".join(benchmark_task_row(task, models, trials, output) for task in page)
        label = f"第 {start + 1}–{start + len(page)} 项"
        opened = " open" if start == 0 else ""
        groups.append(f"""
<details class="matrix-group"{opened}><summary>{label}</summary>
<div class="table-wrap" tabindex="0" role="region" aria-label="逐任务配对结果 · {label}">
<table class="matrix"><colgroup span="1"></colgroup>{columns}
<thead><tr><th scope="col" rowspan="2">任务</th>{model_headers}</tr><tr>{mode_headers}</tr></thead>
<tbody>{rows}</tbody></table></div></details>
""")
    return "".join(groups)


def matched_trials(run_dir, manifest, *, preview=False):
    tasks = manifest["benchmark"]["tasks"]
    models = manifest["model_order"]
    trials = load_benchmark_trials(run_dir, manifest, preview=preview)
    expected = {(model, task["task_id"], mode) for model in models for task in tasks for mode in MODES}
    if trials.keys() != expected or len(expected) != len(models) * len(tasks) * len(MODES):
        raise ValueError("Benchmark manifest does not contain one trial per configuration and matched task")
    return trials


def terminal_protocol(manifest):
    dataset = manifest["benchmark"]
    budget = manifest["budget"]
    return (
        manifest["purpose"], manifest["models"], manifest["model_order"], manifest["runtime"],
        *(dataset.get(key) for key in ("name", "selection", "split", "canonical_task_count", "data_version",
                                       "source_commit", "constraints")),
        *(budget.get(key) for key in ("executor_limit", "planner_limits", "return_every",
                                      "max_input_bytes_per_request", "dispatch_rate_per_minute", "automatic_retries",
                                      "max_attempts_per_trial")),
    )


def render_benchmark(run_dir, output, section_id, *, manifest=None, supplements=()):
    run_dir = Path(run_dir).resolve()
    manifest_path = run_dir / "manifest.json"
    if manifest is None:
        manifest = read_json(manifest_path)
    purposes = {"paired_model_framework_screen", "paired_model_framework_benchmark"}
    if manifest["status"] != "complete" or manifest["purpose"] not in purposes:
        raise ValueError("Expected a completed paired benchmark manifest")
    benchmark = manifest["benchmark"]
    budget = manifest["budget"]
    tasks, models = list(benchmark["tasks"]), manifest["model_order"]
    limits = sorted({entry["executor_limit"] for entry in budget.get("budgets_by_task", {}).values()})
    if budget["executor_limit"] is not None:
        executor_budget = f'每条轨迹至多 {html(budget["executor_limit"])} 次 Executor 请求。'
    elif limits:
        executor_budget = f"任务级 Executor 请求上限为 {limits[0]} 到 {limits[-1]} 次。"
    else:
        executor_budget = "任务级 Executor 请求上限见运行清单。"
    full_split = benchmark.get("selection") == "full_split"
    if full_split and benchmark.get("canonical_task_count") != len(tasks):
        raise ValueError("Complete-split selection does not match the canonical task count")
    trials = matched_trials(run_dir, manifest)
    if supplements:
        if benchmark["name"] != "Terminal-Bench" or benchmark.get("selection") != "reviewed_subset":
            raise ValueError("Supplemental matrices require a reviewed Terminal-Bench scope")
        protocol = terminal_protocol(manifest)
        for directory, supplement in supplements:
            if supplement["status"] != "complete" or terminal_protocol(supplement) != protocol:
                raise ValueError(f"Terminal-Bench supplement differs from the completed matching protocol at {directory}")
            extra = matched_trials(directory, supplement)
            if trials.keys() & extra.keys():
                raise ValueError(f"Terminal-Bench supplement contains duplicate configurations at {directory}")
            tasks.extend(supplement["benchmark"]["tasks"])
            trials.update(extra)
        if len(tasks) > benchmark["canonical_task_count"]:
            raise ValueError("Reviewed Terminal-Bench coverage exceeds the canonical task count")
    task_ids = [task["task_id"] for task in tasks]
    model_matches = {
        model: {task_id for task_id in task_ids if all(trials[model, task_id, mode].score is not None for mode in MODES)}
        for model in models
    }
    shared = [task_id for task_id in task_ids if all(task_id in matches for matches in model_matches.values())]
    groups = []
    for model in models:
        matched = [task_id for task_id in task_ids if task_id in model_matches[model]]
        rows = "".join(benchmark_score_row(
            mode, model, [trials[model, task["task_id"], mode] for task in tasks],
            [trials[model, task_id, mode].score for task_id in matched],
            [trials[model, task_id, mode].score for task_id in shared], index == 0,
        ) for index, mode in enumerate(MODES))
        groups.append(f'<tbody class="model-rows">{rows}</tbody>')
    matrix = benchmark_matrix(tasks, models, trials, output)
    scored = sum(trial.score is not None for trial in trials.values())
    replayed = sum(trial.replay is not None for trial in trials.values())
    harbor_budget = sum(trial.harbor_budget is not None for trial in trials.values())
    archived = sum(len(trial.past) for trial in trials.values())
    archived_found = sum(path is not None for trial in trials.values() for path in trial.past)
    cost_note = (f"已把 {archived_found:,} / {archived:,} 条归档尝试中可核对的消耗计入总量。" if archived else "")
    scope = html(benchmark["split"])
    if full_split and benchmark["split"] == "test":
        scope = "完整测试集"
    elif benchmark.get("selection") == "reviewed_subset":
        scope = f'已审阅子集 · {len(tasks)} / {html(benchmark.get("canonical_task_count"))} 个官方任务'
    if benchmark.get("data_version"):
        scope += f' · 数据版本 <code>{html(benchmark["data_version"])}</code>'
    run_time = ""
    cohort = [manifest, *(extra for _, extra in supplements)]
    if all(run.get("started_at") and run.get("finished_at") for run in cohort):
        start = min(datetime.fromisoformat(run["started_at"]) for run in cohort)
        end = max(datetime.fromisoformat(run["finished_at"]) for run in cohort)
        run_time = f"评测历时 {(end - start).total_seconds() / 3600:.2f} 小时，含续跑间隔。"
    entrypoint, scoring = BENCHMARK_EVIDENCE.get(benchmark["name"], ("benchmark.py", "评分字段定义见运行清单。"))
    if replayed:
        scoring += f" {replayed:,} 格在原输入预算处重放原生环境。重放没有额外模型调用。"
    if harbor_budget:
        scoring += (f" {harbor_budget:,} 格在本地输入预算处停止，计入同次运行已产出的 Harbor 原生评分。"
                    "导入无额外模型调用。")
    files = [(manifest_path, "配对评测运行清单 JSON"),
             (run_dir / "recovery-selection.json", "外部故障定向补跑清单"),
             (run_dir / "source.patch", "配对评测运行时源码补丁"),
             (run_dir / "recovery-source.patch", "断点恢复源码补丁"),
             (run_dir / "parallel-source.patch", "并发续跑源码补丁"),
             (run_dir / "unpaced-source.patch", "无本机速率上限续跑源码补丁"),
             (run_dir / "native-replay-source.patch", "原生重放源码补丁"),
             (ROOT / "experiments/planner-centered/README.md", "任务选择与复现说明"),
             (Path(__file__).parent / entrypoint, "配对评测执行入口")]
    files.extend((path, f"外部故障定向补跑清单 · {path.stem.rsplit('-', 1)[1]}")
                 for path in sorted(run_dir.glob("recovery-selection-*.json")))
    if benchmark.get("canonical_task_file"):
        files.append((Path(benchmark["canonical_task_file"]), "测试任务表"))
    if benchmark["name"] == "Terminal-Bench" and benchmark.get("selection") == "reviewed_subset":
        inventory = ROOT / "experiments/planner-centered/runs/data/terminalbench/v4.1-metadata-review.json"
        files.append((inventory, "官方任务覆盖与环境清单"))
    for directory, _ in supplements:
        files.extend(((directory / "manifest.json", f"补充清单 · {directory.name}"),
                      (directory / "source.patch", f"补充源码 · {directory.name}")))
    sources = "".join(link(path, label, output) for path, label in files if path.is_file())
    return f"""
<section id="{section_id}" class="benchmark"><h2>{html(benchmark["name"])} 配对评测</h2>
<p class="muted">{scope} · {len(models)} 个模型 × {len(MODES)} 种框架 × {len(tasks)} 个计划任务 · 每格保留一条最终记录。</p>
<p class="small">有效评分 {scored:,} / {len(trials):,}。全配置配对任务 {len(shared):,} / {len(tasks):,}。{scoring}</p>
<p class="small">使用 Planner 的配置为两个角色选用同一基座模型。各配置在相同任务上共用环境、工具与执行额度。{executor_budget}动态框架每 {html(budget["return_every"])} 轮检查返回。{run_time}</p>
<div class="table-wrap" tabindex="0" role="region" aria-label="模型与框架汇总">
<table><thead><tr><th scope="col">基础模型</th><th scope="col">框架</th><th scope="col">有效任务均值</th>
<th scope="col">模型内配对均值</th><th scope="col">全配置配对均值</th>
<th scope="col">得分和 / 有效数</th><th scope="col">有效 / 计划</th>
<th scope="col">失败 / 缺评</th><th scope="col">提交动作</th><th scope="col">调用尝试 P / E</th>
<th scope="col">总 token</th><th scope="col">停止原因</th></tr></thead>
{"".join(groups)}</table></div>
<p class="small">有效任务均值使用本配置已评分的任务。模型内配对均值使用该模型四种框架均有评分的任务。全配置配对均值使用所有模型和框架均有评分的任务。</p>
<p class="small">失败指已评分且未达到成功条件。缺评计入计划分母。</p>
<p class="small">提交动作包含适配器拒绝的命令。调用尝试也包含发送前被本地预算拦截的请求。总量和推理 token 取服务端实报字段，用量缺失时显示已知下界或未知。{cost_note}</p>
<h3>逐任务得分</h3>
<p class="small">点击分值打开最终评分轨迹。缺评格提供停止原因。每个任务的初始环境在所有配置间独立重置。</p>
{matrix}
<p class="small">分值和消耗对应这批运行。每格一个评分记录用于匹配比较，未估计重复运行的波动。</p>
<p class="links">{sources}</p></section>
"""


def render_alfworld_entry(output, section_id):
    target = Path(output).parent / "alfworld.html"
    return (f'<section id="{html(section_id)}" class="benchmark"><h2>ALFWorld 完整实验结果</h2>'
            '<p>完整测试集的结果分析、交互轨迹与轨迹比较已移至独立页面。</p>'
            f'<p class="links">{link(target, "打开 ALFWorld 完整实验结果", output)}</p></section>')


def render(run_dir, output, prior_audit=None, benchmark_dirs=()):
    run_dir, output = Path(run_dir).resolve(), Path(output).resolve()
    manifest_path = run_dir / "manifest.json"
    manifest = read_json(manifest_path)
    raw_paths = {mode: run_dir / manifest["records"].get(mode, f"{mode}.json") for mode in MODES}
    records = {
        mode: read_json(path) if path.is_file() else None
        for mode, path in raw_paths.items()
    }
    benchmark = manifest["benchmark"]
    available = sum(record is not None for record in records.values())
    sequence = "".join(timeline(mode, record) for mode, record in records.items())
    rows = "".join(result_row(mode, record) for mode, record in records.items())
    checks = "".join(protocol_row(mode, record) for mode, record in records.items())
    traces = "".join(trace(mode, record, raw_paths[mode], output) for mode, record in records.items())
    sources = [
        (ROOT / "PROPOSAL.md", "研究提案"),
        (ROOT / "Planner_Centered_Test_Proposal.pdf", "测试提案 PDF"),
        (Path(__file__).parent / "README.md", "Recipe 与复现说明"),
        (Path(__file__).parent / "runner.py", "四种框架运行器"),
        (Path(__file__).parent / "run.py", "真实模型运行入口"),
        (manifest_path, "运行清单 JSON"),
        (run_dir / "source.patch", "运行时源码补丁"),
    ]
    if benchmark_dirs:
        sources.append((ROOT / "experiments/planner-centered/audit-preview.html", "阶段性同任务比较"))
    source_links = "".join(link(path, label, output) for path, label in sources if path.is_file())
    prior_link = ""
    if prior_audit is not None:
        if not prior_audit.is_file():
            raise FileNotFoundError(prior_audit)
        prior_link = f'<p class="small">{link(prior_audit, "查看前一轮运行与错误轨迹", output)}</p>'
    observed_models = sorted({
        response["model"]
        for record in records.values() if record is not None
        for role in ROLES
        for response in model_responses(record, role)
        if response and response.get("model")
    })
    models = "、".join(observed_models) or "未知"
    task = benchmark.get("goal") or benchmark.get("task")
    report_type = "真实模型验收" if manifest.get("purpose") == "live_model_interface_smoke" else "运行记录审查"
    status = {"complete": "执行完成", "interrupted": "运行中断", "running": "运行中"}.get(manifest.get("status"), "状态未知")
    head_data = (
        f'{html(benchmark.get("name"))} · {html(benchmark.get("split"))} · '
        f'任务 {html(benchmark.get("task_id"))} · {available} / {len(MODES)} 份轨迹'
    )
    benchmark_runs = [(Path(directory).resolve(), read_json(Path(directory) / "manifest.json"))
                      for directory in benchmark_dirs]
    terminal_indices = [index for index, (_, run) in enumerate(benchmark_runs)
                        if run["benchmark"]["name"] == "Terminal-Bench"]
    primary_terminal = terminal_indices[0] if terminal_indices else None
    supplements = [benchmark_runs[index] for index in terminal_indices[1:]]
    paired = "".join(
        render_alfworld_entry(output, f"benchmark-{index + 1}")
        if run["benchmark"]["name"] == "ALFWorld" and run["benchmark"].get("selection") == "full_split"
        else render_benchmark(directory, output, f"benchmark-{index + 1}", manifest=run,
                              supplements=supplements if index == primary_terminal else ())
        for index, (directory, run) in enumerate(benchmark_runs) if index not in terminal_indices[1:]
    )
    if paired:
        paired = f'<div id="benchmark">{paired}</div>'
    paired_nav = '<a href="#benchmark">配对评测</a>' if paired else ""
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="四种 Planner–Executor 框架的真实模型调用、协议轨迹与环境终局。">
<title>四种规划框架 · 运行审查</title>
<style>{STYLE}</style>
</head>
<body>
<a class="skip" href="#main">跳至主要内容</a>
<header><div class="wrap masthead"><strong>Planner 实验 · 运行审查</strong>
<nav aria-label="页面目录">{paired_nav}<a href="#results">运行结果</a><a href="#protocol">接口验收</a>
<a href="#traces">事件轨迹</a><a href="#sources">来源与复现</a></nav></div></header>
<main class="wrap" id="main">
<div class="hero"><div><h1>四种规划框架的<br>{report_type}</h1>
<p class="small">{head_data} · {status}</p>
<p class="task"><strong>共同任务</strong>{html(task)}</p>
<p class="small">返回模型 <code>{html(models)}</code></p>
<p class="muted">四组各运行同一个开发任务一次，用于核对框架接口与控制流。结果和成本只描述本次样本。</p></div>
<figure><figcaption>按事件顺序查看模型调用与执行边界</figcaption>
{sequence}
<p class="legend small"><span><strong class="planner">P</strong>Planner</span>
<span><strong class="executor">E</strong>Executor</span><span><strong class="planner">G</strong>交付指导</span>
<span><strong class="planner">D</strong>委派阶段</span><span><strong class="return">R</strong>检查点或反馈</span>
<span><strong class="verifier">V</strong>环境终局</span></p></figure></div>{paired}
<section id="results"><h2>运行结果</h2>
<p class="muted">各行对应一段实际轨迹。环境终局来自同一原生判定规则。</p>
<div class="table-wrap" tabindex="0" role="region" aria-label="四种框架运行结果">
<table><thead><tr><th scope="col">框架</th><th scope="col">环境终局</th><th scope="col">调用 P / E</th>
<th scope="col">环境动作</th><th scope="col">中途执行边界</th><th scope="col">总 token</th>
<th scope="col">轨迹耗时</th><th scope="col">停止原因</th></tr></thead>
<tbody>{rows}</tbody></table></div>
<p class="small">EO 和 PE-S 的中途边界只记日志，Executor 沿原请求续接。PE-D 和 PC 在中途边界向 Planner 提供执行反馈。</p>
<p class="small">环境动作包含被环境拒绝的命令。调用数包含模型请求失败及发送前被本地预算拒绝的尝试。用量缺失时显示已知下界或未知。轨迹耗时取首末事件时间差。</p>
{prior_link}</section>
<section id="protocol"><h2>接口验收</h2>
<p class="muted">从调用数、请求 ID、规划版本和阶段目标核对四种运行语义。点击上方的事件标记或下方的引用即可查看原文。</p>
<dl class="checks">{checks}</dl></section>
<section id="traces"><h2>事件轨迹</h2>
<p class="muted">展开单个事件查看入参与原始回复。事件引用可以回查 Planner 决策实际关联的执行证据。</p>
{traces}</section>
<section id="sources"><h2>来源与复现</h2>
<p class="links">{source_links}</p>
<p class="small">运行 <code>{html(manifest.get("run_id"))}</code> · 开始时间 <code>{html(manifest.get("started_at"))}</code></p>
{details('查看实际运行清单与预算', manifest)}</section>
</main>
<footer class="wrap">四种规划框架 · {html(manifest.get("run_id"))}</footer>
</body></html>
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--output", default=OUTPUT, type=Path)
    parser.add_argument("--prior-audit", type=Path)
    parser.add_argument("--benchmark-dir", type=Path, action="append", default=[])
    args = parser.parse_args()
    write_text_atomic(args.output, render(args.run_dir, args.output, args.prior_audit, args.benchmark_dir))
    print(args.output.resolve())


if __name__ == "__main__":
    main()
