"""Validate and index benchmark task rows."""

import re
from pathlib import Path

from ..prompts import extract_plan
from ..utils.files import read_jsonl


def task_rows_by_id(rows):
    indexed = {}
    for row in rows:
        task_id = str(row["id"])
        if not re.fullmatch(r"[A-Za-z0-9_-]+", task_id):
            raise ValueError(f"Invalid task ID: {task_id!r}")
        if task_id in indexed:
            raise ValueError(f"Duplicate task ID: {task_id}")
        if not isinstance(row.get("task"), str) or not row["task"].strip():
            raise ValueError(f"Task {task_id} has blank task text")
        indexed[task_id] = row
    return indexed


def load_task_rows(path, task_name, split, plan_path=None, selection_path=None,
                   part_num=1, part_idx=-1, max_tasks=None, selection_rows=None,
                   task_id=None, gamefile_map_path=None):
    """Select canonical task IDs before loading any environment."""
    if not re.fullmatch(r"[A-Za-z0-9_-]+", task_name):
        raise ValueError(f"Invalid benchmark name: {task_name!r}")
    if split not in ("train", "dev", "test"):
        raise ValueError(f"Unsupported split: {split}")
    if part_num < 1 or (part_num == 1 and part_idx != -1) or (part_num > 1 and not 0 <= part_idx < part_num):
        raise ValueError("Invalid task partition")
    if max_tasks is not None and max_tasks < 1:
        raise ValueError("--max-tasks must be positive")
    if task_id is not None and part_num != 1:
        raise ValueError("--task-id cannot be combined with task partitioning")
    canonical = task_rows_by_id(read_jsonl(Path(path) / f"{task_name}_{split}_tasks.jsonl"))
    metadata = task_rows_by_id(read_jsonl(gamefile_map_path)) if gamefile_map_path else {}
    for map_id, row in metadata.items():
        if map_id not in canonical or row["task"] != canonical[map_id]["task"]:
            raise ValueError(f"Gamefile map task {map_id} differs from the {split} task file")
    plans = task_rows_by_id(read_jsonl(plan_path)) if plan_path else {}
    for plan_id, row in plans.items():
        if plan_id not in canonical or row["task"] != canonical[plan_id]["task"]:
            raise ValueError(f"Plan task {plan_id} differs from the {split} task file")
        if not isinstance(row.get("plan"), str) or not extract_plan(row["plan"]):
            raise ValueError(f"Task {plan_id} must have one nonempty plan")
    if selection_rows is None:
        selection_rows = read_jsonl(selection_path) if selection_path else list(plans.values() or canonical.values())
    requested = task_rows_by_id(selection_rows)
    if not requested:
        raise ValueError("The task selection is empty")
    if task_id is not None:
        task_id = str(task_id)
        if task_id not in canonical:
            raise ValueError(f"Task ID {task_id} is not in the {split} task file")
        if task_id not in requested:
            raise ValueError(f"Task ID {task_id} is not in the selected tasks")
        requested = {task_id: requested[task_id]}
    for task_id, row in requested.items():
        if task_id not in canonical or row["task"] != canonical[task_id]["task"]:
            raise ValueError(f"Selected task {task_id} differs from the {split} task file")
        if plan_path and task_id not in plans:
            raise ValueError(f"No plan matched task {task_id}")
    # Canonical ordering makes limits and partitioning independent of plan order.
    rows = []
    for task_id, row in canonical.items():
        if task_id not in requested:
            continue
        selected = dict(row)
        if "gamefile" in metadata.get(task_id, {}):
            if "gamefile" in selected and selected["gamefile"] != metadata[task_id]["gamefile"]:
                raise ValueError(f"Conflicting ALFWorld gamefiles for task {task_id}")
            selected["gamefile"] = metadata[task_id]["gamefile"]
        if "gamefile" in requested[task_id]:
            if "gamefile" in selected and selected["gamefile"] != requested[task_id]["gamefile"]:
                raise ValueError(f"Conflicting ALFWorld gamefiles for task {task_id}")
            selected["gamefile"] = requested[task_id]["gamefile"]
        selected["plan"] = extract_plan(plans[task_id]["plan"]) if plan_path else None
        rows.append(selected)
    if part_num > 1:
        start = len(rows) * part_idx // part_num
        end = len(rows) * (part_idx + 1) // part_num
        rows = rows[start:end]
    return rows[:max_tasks] if max_tasks is not None else rows
