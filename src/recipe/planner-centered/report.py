"""Render one current-protocol benchmark run with its original evidence."""

import argparse
import json
import math
import os
import sys
from collections import Counter
from dataclasses import dataclass
from html import escape
from pathlib import Path
from urllib.parse import quote

SRC = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SRC))

from toolkit.frameworks import FRAMEWORK_MODES, FRAMEWORK_PROTOCOL
from toolkit.utils.files import read_json, write_text_atomic

ROOT = SRC.parent
MODES = {
    "eo": ("EO", "Executor 自主执行"),
    "pe-s": ("PE-S", "执行前一次性整体规划"),
    "pe-d-f": ("PE-D-F", "Executor 按需请求剩余整体规划"),
    "pe-d-s": ("PE-D-S", "Executor 按需请求子计划"),
    "pc-f": ("PC-F", "整体规划与逐步执行监测"),
    "pc-s": ("PC-S", "子计划与逐步执行监测"),
}
EVENT_NAMES = {
    "initial_observation": "初始环境观察", "model_call": "模型调用",
    "planner_decision": "Planner 判断", "execution_request": "执行请求",
    "tool_event": "环境交互", "tool_error": "环境错误",
    "decision_error": "规划协议错误", "runtime_error": "运行错误",
    "execution_feedback": "执行反馈", "model_tool_result": "工具结果",
    "stage_result": "阶段结果", "stop": "运行停止", "verifier": "环境终局",
}
REASONS = {
    "step_feedback": "单步动作与环境反馈", "environment_limit": "达到环境步上限",
    "task_finish": "环境任务终止", "executor_budget": "达到环境步上限",
    "protocol_error": "规划协议错误", "runtime_error": "运行错误",
}
ROLES = {"planner": "Planner", "executor": "Executor"}
STYLE = """
:root{color-scheme:dark;font:16px/1.6 system-ui,sans-serif;background:#181825;color:#edf0ff}
body{max-width:1200px;margin:2rem auto;padding:0 1rem}a{color:#cbb5fa}
table{border-collapse:collapse;width:100%;margin:1rem 0}th,td{padding:.6rem;border:1px solid #45455a;text-align:left}
pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#11111b;padding:1rem}
details{margin:.7rem 0}summary{cursor:pointer}section{margin:2rem 0}small{color:#bac2de}
"""


def pretty(value):
    return json.dumps(value, ensure_ascii=False, indent=2)


def html(value):
    return "未知" if value is None else escape(str(value))


def link(path, label, output):
    relative = quote(os.path.relpath(Path(path).resolve(), Path(output).resolve().parent))
    return f'<a href="{escape(relative, quote=True)}">{html(label)}</a>'


def details(label, payload):
    return f'<details><summary>{html(label)}</summary><pre>{html(pretty(payload))}</pre></details>'


def events(record, event_type):
    return [event for event in record.get("events", []) if event.get("type") == event_type]


def usage_count(response, field):
    usage = (response or {}).get("usage") or {}
    if field == "reasoning_tokens":
        return usage.get(field, (usage.get("completion_tokens_details") or {}).get(field))
    return usage.get(field)


def reason_label(reason):
    return REASONS.get(reason, reason or "未知")


def feedback_label(mode, reason):
    return reason_label(reason)


@dataclass(frozen=True)
class BenchmarkTrial:
    path: Path
    has_record: bool
    past: tuple[Path | None, ...]
    score: float | None
    success: bool | None
    stop: str
    cost: Counter


def accumulate_attempt_cost(cost, record):
    failed_before_events = record.get("status") == "error" and record.get("events") == []
    if not failed_before_events and not events(record, "stop"):
        cost["incomplete"] += 1
    cost["actions"] += sum(event["dispatched"] is True for event in events(record, "tool_event"))
    cost["actions"] += sum(event.get("dispatched") is True for event in events(record, "tool_error"))
    for call in events(record, "model_call"):
        cost[call["role"]] += 1
        if call.get("error") == "ContextWindowExceeded":
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


def manifest_modes(manifest):
    if (manifest.get("protocol_version") != FRAMEWORK_PROTOCOL
            or manifest.get("experiment") != "planner-centered-v2"
            or manifest.get("purpose") != "untrained_framework_benchmark"):
        raise ValueError("Expected a planner-centered-v2 current-protocol manifest")
    modes = manifest.get("modes")
    if (not isinstance(modes, list) or not modes
            or any(mode not in FRAMEWORK_MODES for mode in modes)
            or len(modes) != len(set(modes))):
        raise ValueError("Invalid benchmark mode list")
    return modes


def load_benchmark_attempt(path, run_id, trial_id, configuration, attempt):
    try:
        record = read_json(path)
    except FileNotFoundError:
        return None
    identity = (record.get("run_id"), record.get("trial_id"), record.get("model"),
                record.get("task_id"), record.get("mode"))
    if (record.get("protocol_version") != FRAMEWORK_PROTOCOL
            or identity != (run_id, trial_id, *configuration)
            or record.get("attempt") != attempt
            or record.get("workspace_id") != f"{run_id}/{trial_id}/attempt-{attempt}"):
        raise ValueError(f"Wrong benchmark trial identity or protocol in {path}")
    return record


def load_benchmark_trials(run_dir, manifest):
    manifest_modes(manifest)
    trials = {}
    for trial_id, scheduled in manifest["trials"].items():
        key = (scheduled["model"], scheduled["task_id"], scheduled["mode"])
        if key in trials:
            raise ValueError(f"Duplicate benchmark configuration {key}")
        path = run_dir / manifest["records"][trial_id]
        archives = [run_dir / relative for relative in scheduled.get("archived_attempts", [])]
        if len({item.resolve() for item in [path, *archives]}) != len(archives) + 1:
            raise ValueError(f"Duplicate benchmark attempt path for {trial_id}")
        record = load_benchmark_attempt(path, manifest["run_id"], trial_id, key, len(archives) + 1)
        if record is not None and any(record.get(field) != scheduled.get(field)
                                      for field in ("plan_scope", "framework_family")):
            raise ValueError(f"Wrong benchmark framework configuration in {path}")
        stop = next(iter(events(record or {}, "stop")), {})
        verifier = next(iter(events(record or {}, "verifier")), {})
        if verifier:
            outcome = record.get("outcome") or {}
            if (record["events"][-2:] != [stop, verifier] or stop.get("reason") != outcome.get("reason")
                    or any(verifier.get(field) != outcome.get(field) for field in ("reason", "reward", "success"))):
                raise ValueError(f"Verifier does not match the recorded terminal outcome in {path}")
        score, success = verifier.get("reward"), verifier.get("success")
        if score is not None and (type(score) not in (int, float) or not math.isfinite(score)
                                  or type(success) is not bool):
            raise ValueError(f"Invalid benchmark score or success flag in {path}")
        if (scheduled["status"] == "complete") != (score is not None):
            raise ValueError(f"Benchmark score and completed status disagree for {path}")
        if score is None and success is not None:
            raise ValueError(f"Unscored benchmark has a success flag in {path}")
        label = reason_label(stop.get("reason")) if stop else "无停止事件"
        error = scheduled.get("error") if score is None else None
        if error:
            label += f" · {error}"
        cost = Counter()
        accumulate_attempt_cost(cost, record or {})
        past = []
        for attempt, archive_path in enumerate(archives, 1):
            archive = load_benchmark_attempt(archive_path, manifest["run_id"], trial_id, key, attempt)
            accumulate_attempt_cost(cost, archive or {})
            past.append(archive_path if archive is not None else None)
        trials[key] = BenchmarkTrial(path, record is not None, tuple(past), score, success, label, cost)
    return trials


def matched_trials(run_dir, manifest):
    tasks, models, modes = manifest["benchmark"]["tasks"], manifest["model_order"], manifest_modes(manifest)
    trials = load_benchmark_trials(Path(run_dir), manifest)
    expected = {(model, task["task_id"], mode) for model in models for task in tasks for mode in modes}
    if trials.keys() != expected or len(expected) != len(models) * len(tasks) * len(modes):
        raise ValueError("Benchmark manifest does not contain one trial per configuration and matched task")
    return trials


def event_anchor(trial_id, event_id):
    return f"{html(trial_id)}-e{html(event_id)}"


def render_event(trial_id, event, observation_events):
    title = EVENT_NAMES.get(event["type"], event["type"])
    if "observation_id" in event:
        title += f" · Observation #{event['observation_id']}"
    refs = event.get("evidence_refs", [])
    references = "、".join(
        f'<a href="#{event_anchor(trial_id, observation_events[ref])}">#{html(ref)}</a>'
        for ref in refs if ref in observation_events
    )
    return (f'<article id="{event_anchor(trial_id, event["event_id"])}">'
            + details(title, event) + (f"<p>观察引用：{references}</p>" if references else "") + "</article>")


def render_benchmark(run_dir, output, section_id, *, manifest=None):
    run_dir, output = Path(run_dir).resolve(), Path(output).resolve()
    manifest = read_json(run_dir / "manifest.json") if manifest is None else manifest
    trials = matched_trials(run_dir, manifest)
    modes, models = manifest_modes(manifest), manifest["model_order"]
    rows = []
    for model in models:
        for mode in modes:
            selected = [trial for (trial_model, _, trial_mode), trial in trials.items()
                        if trial_model == model and trial_mode == mode]
            scored = [trial for trial in selected if trial.score is not None]
            cost = sum((trial.cost for trial in selected), Counter())
            mean = f"{sum(trial.score for trial in scored) / len(scored):.4f}" if scored else "缺评"
            rows.append("<tr>" + "".join(f"<td>{html(value)}</td>" for value in (
                model, MODES[mode][0], mean, f"{len(scored)}/{len(selected)}",
                sum(trial.success is True for trial in scored), len(selected) - len(scored),
                cost["actions"], cost["planner"], cost["executor"], benchmark_token_count(cost, "total_tokens"),
            )) + "</tr>")
    role_models = manifest.get("models", {})
    same_models = all(settings["planner"]["model"] == settings["executor"]["model"]
                      for settings in role_models.values()) if role_models else False
    role_text = "两个角色采用同一基座模型。" if same_models else "两个角色分别按运行清单中的角色配置调用模型。"
    headers = ("模型", "框架", "有效均分", "有效评分/任务", "成功数", "缺评数", "环境步", "Planner 调用", "Executor 调用", "总 token")
    body = (f'<section id="{html(section_id)}"><h2>{html(manifest["benchmark"]["name"])} · {html(manifest["run_id"])}</h2>'
            f'<p>未经本项目训练的模型框架性能测试。{role_text}缺评不计为零分。调用与 token 成本包含同一运行的所有重试。</p>'
            f'<p>{link(run_dir / "manifest.json", "原始运行清单", output)}</p>'
            + details("设置与环境", {key: manifest.get(key) for key in ("experiment", "protocol_version", "models", "budget", "runtime", "source")})
            + "<table><thead><tr>" + "".join(f"<th>{item}</th>" for item in headers)
            + "</tr></thead><tbody>" + "".join(rows) + "</tbody></table>")
    for key, trial in trials.items():
        trial_id = next(trial_id for trial_id, scheduled in manifest["trials"].items()
                        if key == (scheduled["model"], scheduled["task_id"], scheduled["mode"]))
        body += f'<details><summary>{html(" / ".join(key))} · {html(trial.stop)}</summary>'
        body += f'<p>{link(trial.path, "原始轨迹", output) if trial.has_record else "缺少当前轨迹"}</p>'
        if trial.past:
            body += "<p>重试成本证据：" + "、".join(link(path, str(i), output) if path else f"{i} 缺失"
                                                  for i, path in enumerate(trial.past, 1)) + "</p>"
        if trial.has_record:
            record = read_json(trial.path)
            observation_events = {event["observation_id"]: event["event_id"] for event in record["events"]
                                  if "observation_id" in event}
            body += "".join(render_event(trial_id, event, observation_events) for event in record["events"])
        body += "</details>"
    return body + "</section>"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = args.output or args.run_dir / "report.html"
    section = render_benchmark(args.run_dir, output, "benchmark")
    write_text_atomic(output, '<!doctype html><html lang="zh-CN"><meta charset="utf-8">'
                      '<meta name="viewport" content="width=device-width,initial-scale=1">'
                      f"<title>框架性能与轨迹</title><style>{STYLE}</style><body>{section}</body></html>")


if __name__ == "__main__":
    main()
