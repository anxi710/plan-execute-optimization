"""Read and validate saved rollout trajectories."""

import json
import re
from pathlib import Path

from ..prompts import PLAN_HINT, render_action_feedback


def load_trace(path):
    path = Path(path)
    history = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(history, list) or not history or not isinstance(history[-1], dict):
        raise ValueError(f"Malformed trajectory: {path}")
    final = history[-1]
    trace = final.get("action_trace")
    if final.get("finished") is not True or final.get("incomplete") or not isinstance(trace, list):
        raise ValueError(f"Unfinished or missing action trace: {path}")
    if type(final.get("steps")) is not int or final["steps"] != len(trace) or not isinstance(final.get("success"), bool):
        raise ValueError(f"Inconsistent steps or success flag: {path}")
    return {"path": str(path), "history": history, "trace": trace,
            "success": final["success"], "steps": final["steps"]}


def load_records(results_dir, task_id, sample_id=None, *, status="all"):
    """Read either the legacy task file or samples from one task directory."""
    results_dir, task_id = Path(results_dir), str(task_id)
    if not re.fullmatch(r"[A-Za-z0-9_-]+", task_id):
        raise ValueError("Expected a path-safe task ID")
    if sample_id is not None and (type(sample_id) is not int or sample_id < 0):
        raise ValueError("Sample ID must be a non-negative integer")
    if status not in ("all", "success", "failure"):
        raise ValueError(f"Unsupported trajectory status: {status}")
    legacy_path = results_dir / f"{task_id}.json"
    sample_dir = results_dir / task_id
    if legacy_path.exists() and sample_dir.exists():
        raise ValueError(f"Ambiguous trajectory layout for task {task_id}: "
                         f"both {legacy_path} and {sample_dir} exist")
    if legacy_path.is_file():
        if sample_id not in (None, 0):
            raise ValueError(f"No trajectory for task {task_id}, sample {sample_id}")
        paths = [(0, legacy_path)]
    elif sample_dir.is_dir():
        paths = []
        for path in sample_dir.glob("sample_*.json"):
            match = re.fullmatch(r"sample_(0|[1-9][0-9]*)\.json", path.name)
            if match and path.is_file():
                index = int(match.group(1))
                if sample_id is None or index == sample_id:
                    paths.append((index, path))
        paths.sort(key=lambda item: item[0])
    else:
        paths = []
    if not paths:
        sample_label = f", sample {sample_id}" if sample_id is not None else ""
        raise ValueError(f"No trajectory for task {task_id}{sample_label}: {results_dir}")

    records = []
    for index, path in paths:
        record = load_trace(path)
        final = record["history"][-1]
        if "task_id" in final and str(final["task_id"]) != task_id:
            raise ValueError(f"Trajectory task ID does not match task {task_id}: {path}")
        if "sample_id" in final and final["sample_id"] != index:
            raise ValueError(f"Trajectory sample ID does not match sample {index}: {path}")
        record.update(task_id=task_id, sample_id=index)
        if status == "all" or record["success"] == (status == "success"):
            records.append(record)
    if not records:
        raise ValueError(f"No {status} trajectories for task {task_id}")
    return records


def conversation_parts(record):
    """Pair the saved replies with steps and return the preceding messages separately."""
    history, trace = record["history"], record["trace"]
    start = len(history) - 1 - 2 * len(trace)
    if start < 1:
        raise ValueError(f"Missing initial prompt or step messages: {record['path']}")
    prefix = history[:start]
    turns = history[start:-1]
    pairs = list(zip(turns[::2], turns[1::2]))
    for step, ((reply, feedback), event) in enumerate(zip(pairs, trace), 1):
        if not isinstance(reply, dict) or not isinstance(feedback, dict) or (
            reply.get("role") != "assistant" or feedback.get("role") != "user"
        ):
            raise ValueError(f"Unexpected message roles at step {step}: {record['path']}")
        if not isinstance(reply.get("content"), str) or not isinstance(feedback.get("content"), str):
            raise ValueError(f"Missing message content at step {step}: {record['path']}")
        # With observation placement, the saved user message also includes the plan.
        observation = event.get("observation") if isinstance(event, dict) else None
        if isinstance(observation, str) and "available_actions" in event:
            observation = render_action_feedback(observation, event["available_actions"])
        if not isinstance(observation, str) or not (
            feedback["content"] == observation
            or feedback["content"].startswith(f"{observation}\n\n{PLAN_HINT}\n")
        ):
            raise ValueError(f"Trace/history observation mismatch at step {step}: {record['path']}")
    return prefix, pairs
