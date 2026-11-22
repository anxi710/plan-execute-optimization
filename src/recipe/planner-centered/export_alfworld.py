"""Export a completed ALFWorld run for the trajectory reader."""

import argparse
import json
import os
import re
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import quote

from report import EVENT_NAMES, ROOT, feedback_label, manifest_modes, matched_trials, reason_label
from toolkit.frameworks import FRAMEWORK_MODES, FRAMEWORK_PROTOCOL
from toolkit.utils.files import read_json, write_text_atomic


PC_MODES = {"pc-s", "pc-f"}
BOUNDARIES = {
    "model_tool_result": ("R", "返回原生工具结果"),
    "stage_result": ("R", "记录上一阶段结果"),
}


def interaction_trace(record):
    if record.get("protocol_version") != FRAMEWORK_PROTOCOL or record.get("mode") not in FRAMEWORK_MODES:
        raise ValueError("Expected a current-protocol trajectory")
    requests = {}
    phases = {}
    for event in record["events"]:
        if event["type"] == "execution_request" and event.get("request_id") not in requests:
            requests[event.get("request_id")] = (f"阶段 {len(requests) + 1}" if record["mode"] in PC_MODES
                                                  else "整任务")
        if event["type"] == "planner_decision" and event.get("planner_phase"):
            phases[event["model_event_id"]] = event["planner_phase"]
    interactions = []
    for event in record["events"]:
        kind = event["type"]
        item = {"id": str(event["event_id"]), "kind": "boundary", "title": ""}
        if event.get("request_id") in requests:
            item["requestId"] = requests[event["request_id"]]
        if event.get("plan_version"):
            item["planVersion"] = event["plan_version"]
        if event.get("stage_objective"):
            item["stageObjective"] = event["stage_objective"]
        phase = event.get("planner_phase") or phases.get(event["event_id"])
        if phase:
            item["phase"] = phase
        if kind == "model_call":
            response = event.get("response") or {}
            role = event["role"]
            item.update(kind="call", role=role, marker="P" if role == "planner" else "E", title=f"{role.title()} 调用",
                        messages=event["messages"],
                        output=response.get("text") or "", response=event.get("response"))
            options = event.get("request_options") or {}
            if options:
                item["requestOptions"] = options
            if event.get("context_window"):
                item["contextWindow"] = event["context_window"]
            if options.get("tools"):
                item["tools"] = options["tools"]
                item["toolChoice"] = options.get("tool_choice")
            if response.get("tool_calls"):
                item["toolCalls"] = response["tool_calls"]
            reasoning = response.get("reasoning_content") or response.get("reasoning")
            if reasoning:
                item["reasoning"] = reasoning
            if event.get("error"):
                item["content"] = f"调用未取得回复：{event['error']}"
        elif kind == "initial_observation":
            item.update(kind="observation", title="初始环境观察", content=event["observation"])
        elif kind == "tool_event":
            action = event.get("action")
            dispatched = event["dispatched"]
            title = "环境反馈" if event.get("valid") else ("环境拒绝动作" if dispatched else "动作未派发")
            item.update(kind="observation", title=title,
                        content=f"动作：{action or '未解析出可执行动作'}\n\n{event.get('observation', '')}")
        elif kind == "planner_decision":
            decision = event["decision"]
            item["title"] = {"guide": "Planner 更新指导", "delegate": "Planner 委派阶段",
                             "keep": "Planner 维持当前阶段", "advance": "Planner 推进阶段",
                             "revise": "Planner 修订计划", "finish": "Planner 建议结束",
                             "review": "Planner 只读收尾", "submit": "Planner 提交任务"}.get(decision, decision)
            if event.get("read_only"):
                item["title"] = "Planner 只读收尾"
            item["content"] = "\n\n".join(filter(None, [event.get("assessment"), event.get("stage_objective")]))
        elif kind == "execution_request":
            if event.get("stage_objective"):
                item["marker"] = "D"
            elif event.get("plan"):
                item["marker"] = "G"
            if record["mode"] == "pe-d-s":
                item["marker"] = "G"
            if record["mode"] in PC_MODES:
                item["title"] = f"委派{item.get('requestId', '当前阶段')}"
            elif record["mode"] == "pe-d-f" and event.get("plan_version", 0) > 1:
                item["title"] = "修订剩余整体规划，续接同一任务"
            elif record["mode"] == "pe-d-s":
                item["title"] = "交付子计划，续接同一整项任务"
            elif record["mode"] in {"pe-s", "pe-d-f"}:
                item["title"] = "交付整体规划，执行整项任务"
            else:
                item["title"] = "开始整任务执行"
            directive = event.get("stage_objective") or event.get("plan")
            if isinstance(directive, list):
                directive = "\n".join(f"{stage['id']}. {stage['stage_objective']}\n完成条件：{stage['completion_condition']}"
                                      for stage in directive)
            item["content"] = directive or event.get("goal", "")
            if event.get("completion_condition"):
                item["content"] += f"\n完成条件：{event['completion_condition']}"
            if event.get("current_subplan_id") is not None:
                item["stageId"] = event["current_subplan_id"]
        elif kind == "execution_feedback":
            item.update(marker="R", title="执行边界与反馈", content=feedback_label(record["mode"], event["return_reason"]))
        elif kind in {"decision_error", "runtime_error", "tool_error"}:
            item.update(kind="error", title={"decision_error": "规划协议拒绝", "runtime_error": "运行错误",
                                             "tool_error": "环境错误"}[kind], content=event.get("error", ""))
        elif kind == "stop":
            item.update(title="在线运行停止", content=reason_label(event["reason"]))
        elif kind == "verifier":
            native = event["reward"]
            verdict = "缺评" if native is None else f"{'成功' if event['success'] else '失败'} · 得分 {native}"
            item.update(marker="V", title="环境原生评分", content=verdict)
        elif kind in BOUNDARIES:
            marker, title = BOUNDARIES[kind]
            item.update(marker=marker, title=title)
            if kind == "model_tool_result":
                item["title"] = f"{title} · {event['name']}"
                item["content"] = event["content"]
            else:
                stage_result = {"verified": "已验证", "blocked": "受阻", "replaced": "已替换"}.get(event["status"],
                                                                                                  event["status"])
                evidence = "、".join(map(str, event["evidence_refs"])) or "—"
                item["content"] = (f"{stage_result} · {event['stage']['stage_objective']}\n{event['assessment']}"
                                   f"\n观察编号 {evidence}")
        else:
            item["title"] = EVENT_NAMES.get(kind, kind)
        if "observation_id" in event:
            item["title"] += f" · Observation #{event['observation_id']}"
        interactions.append(item)
    return {"id": record["trial_id"], "mode": record["mode"], "model": record["model"],
            "taskId": record["task_id"], "goal": record["goal"], "interactions": interactions}


def write_payload(path, payload):
    write_text_atomic(path, json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")


def export_alfworld(run_dir, output=None, *, standalone=False):
    run_dir = Path(run_dir)
    manifest = read_json(run_dir / "manifest.json")
    benchmark = manifest["benchmark"]
    selection = benchmark.get("selection")
    full_test = (selection == "full_split" and benchmark.get("split") == "test"
                 and benchmark.get("canonical_task_count") == len(benchmark["tasks"]))
    single_task = selection == "single_task" and len(benchmark["tasks"]) == 1
    if manifest["status"] != "complete" or benchmark["name"] != "ALFWorld" or not (full_test or single_task):
        raise ValueError("Expected a completed full-test or single-task ALFWorld manifest")
    if standalone and not single_task:
        raise ValueError("The self-contained page is for single-task ALFWorld runs")
    if output is None:
        output = run_dir / "alfworld.html" if standalone else run_dir / "alfworld/data"
    output = Path(output)
    trials = matched_trials(run_dir, manifest)
    if any(not trial.has_record or any(path is None for path in trial.past)
           for trial in trials.values()):
        raise ValueError("The ALFWorld export requires all final trajectories and all archived cost evidence")
    budget = manifest["budget"]
    index = {
        "schemaVersion": 1, "runId": manifest["run_id"], "benchmark": benchmark["name"],
        "selection": selection, "protocolVersion": manifest["protocol_version"], "split": benchmark.get("split"),
        "models": manifest["model_order"], "modes": manifest_modes(manifest),
        "tasks": [{"id": task["task_id"], "goal": task["goal"], "family": task.get("family", ""),
                   "initial": task.get("task", "")} for task in benchmark["tasks"]],
        "budget": {"environmentStepLimit": budget["executor_limit"],
                   "contextWindow": budget["context_window"],
                   "plannerMaxTokens": {model: settings["planner"]["max_tokens"]
                                        for model, settings in manifest.get("models", {}).items()}},
        "trials": [],
    }
    traces = {}
    page_dir = output.parent if standalone else output.parent.parent
    index["manifestUrl"] = quote(os.path.relpath(run_dir / "manifest.json", page_dir))
    for trial_id, scheduled in manifest["trials"].items():
        if not re.fullmatch(r"[A-Za-z0-9_-]+", trial_id):
            raise ValueError(f"Invalid trial export filename: {trial_id}")
        trial = trials[scheduled["model"], scheduled["task_id"], scheduled["mode"]]
        record = read_json(trial.path)
        errors = [event["error"] for event in record["events"]
                  if event["type"] in {"decision_error", "runtime_error", "tool_error"}]
        stop = next((event["reason"] for event in record["events"] if event["type"] == "stop"), None)
        cost = trial.cost
        trace_url = f"alfworld/data/traces/{trial_id}.json"
        index["trials"].append({
            "id": trial_id, "taskId": scheduled["task_id"], "model": scheduled["model"], "mode": scheduled["mode"],
            "score": trial.score, "success": trial.success, "stop": trial.stop, "stopReason": stop,
            "error": errors[-1] if errors else None, "actions": cost["actions"],
            "plannerCalls": cost["planner"], "executorCalls": cost["executor"],
            "tokens": cost["total_tokens"], "knownTokenCalls": cost["known_total_tokens"],
            "totalTokenCalls": cost["planner"] + cost["executor"] - cost["undispatched"] + cost["incomplete"],
            "archivedAttempts": len(trial.past), "traceUrl": trace_url,
        })
        trace = interaction_trace(record)
        if standalone:
            traces[trace_url] = trace
        else:
            write_payload(output / "traces" / f"{trial_id}.json", trace)
    if standalone:
        write_standalone(output, {"alfworld/data/index.json": index, **traces})
    else:
        write_payload(output / "index.json", index)
    return index


def write_standalone(output, dataset):
    with TemporaryDirectory() as temporary:
        destination = Path(temporary)
        subprocess.run(["npm", "--prefix", str(ROOT / "web"), "run", "build:alfworld", "--",
                        "--outDir", temporary], check=True)
        page = (destination / "alfworld.html").read_text()
        patterns = (
            (r'<script type="module" crossorigin src="([^"]+)"></script>', "script", '<script type="module">'),
            (r'<link rel="stylesheet" crossorigin href="([^"]+)">', "style", "<style>"),
        )
        for pattern, tag, opening in patterns:
            match = re.search(pattern, page)
            if not match or not match[1].startswith("./alfworld/assets/"):
                raise ValueError("Unexpected ALFWorld viewer build output")
            source = (destination / match[1]).read_text()
            if re.search(fr"</{tag}", source, re.IGNORECASE):
                raise ValueError(f"Cannot embed a raw closing {tag} tag")
            page = page[:match.start()] + opening + source + f"</{tag}>" + page[match.end():]
        payload = json.dumps(dataset, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
        page = page.replace('<div id="root"></div>', f'<div id="root"></div>\n'
                            f'<script type="application/json" id="alfworld-data">{payload}</script>', 1)
    write_text_atomic(output, page)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, help="Data directory, or HTML filename with --standalone.")
    parser.add_argument("--standalone", action="store_true", help="Build a single-task viewer that opens offline.")
    args = parser.parse_args()
    index = export_alfworld(args.run_dir, args.output, standalone=args.standalone)
    print(f"Exported {len(index['trials']):,} ALFWorld trajectories for {index['runId']}.")


if __name__ == "__main__":
    main()
