"""Export the completed ALFWorld matrix for its standalone results page."""

import argparse
import json
import re
from pathlib import Path

from report import MODES, ROOT, feedback_label, matched_trials, reason_label
from toolkit.utils.files import read_json, write_text_atomic


DEFAULT_RUN = ROOT / "experiments/planner-centered/runs/alfworld-test-01-recovery-03"
DEFAULT_OUTPUT = ROOT / "experiments/planner-centered/alfworld/data"


def interaction_trace(record):
    requests = {}
    for event in record["events"]:
        if event["type"] == "execution_request" and event.get("request_id") not in requests:
            requests[event.get("request_id")] = (f"阶段 {len(requests) + 1}" if record["mode"] == "pc"
                                                  else "整任务")
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
        if kind == "model_call":
            response = event.get("response") or {}
            role = event["role"]
            item.update(kind="call", role=role, marker="P" if role == "planner" else "E", title=f"{role.title()} 调用",
                        messages=[{"role": message["role"], "content": message["content"]}
                                  for message in event["messages"]],
                        output=response.get("text") or "")
            reasoning = response.get("reasoning_content") or response.get("reasoning")
            if reasoning:
                item["reasoning"] = reasoning
            if event.get("error"):
                item["content"] = f"调用未取得回复：{event['error']}"
        elif kind == "initial_observation":
            item.update(kind="observation", title="任务与初始环境", content=event["observation"])
        elif kind == "tool_event":
            action = event.get("action")
            item.update(kind="observation", title="环境反馈" if event.get("valid") else "环境拒绝动作",
                        content=f"动作：{action or '未解析出可执行动作'}\n\n{event.get('observation', '')}")
        elif kind == "planner_decision":
            decision = event["decision"]
            item["title"] = {"guide": "Planner 更新整体指导", "delegate": "Planner 委派阶段",
                             "finish": "Planner 建议结束"}.get(decision, decision)
            item["content"] = event.get("stage_objective") or ""
        elif kind == "execution_request":
            if event.get("stage_objective"):
                item["marker"] = "D"
            elif event.get("soft_guidance"):
                item["marker"] = "G"
            if record["mode"] == "pc":
                item["title"] = f"委派{item['requestId']}"
            elif record["mode"] == "pe-d" and event.get("plan_version", 0) > 1:
                item["title"] = "修订剩余整体规划，续接同一任务"
            elif record["mode"] in {"pe-s", "pe-d"}:
                item["title"] = "交付整体规划，执行整项任务"
            else:
                item["title"] = "开始整任务执行"
            item["content"] = event.get("stage_objective") or event.get("soft_guidance") or event.get("goal", "")
        elif kind == "execution_feedback":
            item.update(marker="R", title="执行边界与反馈", content=feedback_label(record["mode"], event["return_reason"]))
        elif kind in {"decision_error", "runtime_error", "tool_error"}:
            item.update(kind="error", title={"decision_error": "规划协议拒绝", "runtime_error": "运行错误",
                                             "tool_error": "环境错误"}[kind], content=event.get("error", ""))
        elif kind == "stop":
            item.update(title="在线运行停止", content=reason_label(event["reason"]))
        elif kind == "verifier":
            item.update(marker="V", title="环境原生评分", content=f"{'成功' if event['success'] else '失败'} · 得分 {event['reward']}")
        else:
            raise ValueError(f"Unsupported ALFWorld event type: {kind}")
        interactions.append(item)
    return {"id": record["trial_id"], "mode": record["mode"], "model": record["model"],
            "taskId": record["task_id"], "goal": record["goal"], "interactions": interactions}


def write_payload(path, payload):
    write_text_atomic(path, json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")


def export_alfworld(run_dir=DEFAULT_RUN, output=DEFAULT_OUTPUT):
    run_dir, output = Path(run_dir), Path(output)
    manifest = read_json(run_dir / "manifest.json")
    benchmark = manifest["benchmark"]
    if (manifest["status"] != "complete" or benchmark["name"] != "ALFWorld"
            or benchmark.get("selection") != "full_split" or benchmark.get("split") != "test"
            or benchmark.get("canonical_task_count") != len(benchmark["tasks"])):
        raise ValueError("Expected a completed full-test ALFWorld manifest")
    trials = matched_trials(run_dir, manifest)
    if any(trial.score is None or not trial.has_record or any(path is None for path in trial.past)
           for trial in trials.values()):
        raise ValueError("The ALFWorld export requires every final score and all archived cost evidence")
    index = {
        "schemaVersion": 1, "runId": manifest["run_id"], "benchmark": benchmark["name"],
        "models": manifest["model_order"], "modes": list(MODES),
        "tasks": [{"id": task["task_id"], "goal": task["goal"], "family": task.get("family", ""),
                   "initial": task.get("task", "")} for task in benchmark["tasks"]],
        "budget": {"executorLimit": manifest["budget"]["executor_limit"],
                   "plannerLimits": manifest["budget"]["planner_limits"],
                   "returnEvery": manifest["budget"]["return_every"],
                   "plannerMaxTokens": {model: settings["planner"]["max_tokens"]
                                        for model, settings in manifest.get("models", {}).items()}},
        "trials": [],
    }
    for trial_id, scheduled in manifest["trials"].items():
        if not re.fullmatch(r"[A-Za-z0-9_-]+", trial_id):
            raise ValueError(f"Invalid trial export filename: {trial_id}")
        trial = trials[scheduled["model"], scheduled["task_id"], scheduled["mode"]]
        record = read_json(trial.path)
        errors = [event["error"] for event in record["events"]
                  if event["type"] in {"decision_error", "runtime_error", "tool_error"}]
        stop = next(event["reason"] for event in record["events"] if event["type"] == "stop")
        cost = trial.cost
        index["trials"].append({
            "id": trial_id, "taskId": scheduled["task_id"], "model": scheduled["model"], "mode": scheduled["mode"],
            "score": trial.score, "success": trial.success, "stop": trial.stop, "stopReason": stop,
            "error": errors[-1] if errors else None, "actions": cost["actions"],
            "plannerCalls": cost["planner"], "executorCalls": cost["executor"],
            "tokens": cost["total_tokens"], "knownTokenCalls": cost["known_total_tokens"],
            "totalTokenCalls": cost["planner"] + cost["executor"] - cost["undispatched"] + cost["incomplete"],
            "archivedAttempts": len(trial.past), "traceUrl": f"alfworld/data/traces/{trial_id}.json",
        })
        write_payload(output / "traces" / f"{trial_id}.json", interaction_trace(record))
    write_payload(output / "index.json", index)
    return index


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, default=DEFAULT_RUN)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    index = export_alfworld(args.run_dir, args.output)
    print(f"Exported {len(index['trials']):,} ALFWorld trajectories to {args.output}")


if __name__ == "__main__":
    main()
