"""Import an official Harbor terminal trial without executing it."""

import json
from pathlib import Path


def load_terminalbench_trial(path, task):
    """Check the recorded task version and keep valid zero separate from no score."""
    path = Path(path)
    result = json.loads(path.read_text(encoding="utf-8"))
    version = result.get("schema_version", 1) if isinstance(result, dict) else None
    if type(version) is not int or version != 1:
        raise ValueError(f"Unsupported Harbor trial schema: {path}")
    names = (task.task_id, task.task_id.removeprefix("terminal-bench/"))
    if result.get("task_name") not in names:
        raise ValueError(f"Harbor trial does not match {task.task_id}: {path}")
    if not result.get("finished_at") or type(result.get("reward_valid")) is not bool:
        raise ValueError(f"Harbor trial is unfinished or has no reward validity flag: {path}")
    lock_path = path.with_name("lock.json")
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    locked_task = lock.get("task") if isinstance(lock, dict) else None
    if (not isinstance(locked_task, dict) or locked_task.get("name") not in names
            or locked_task.get("version") != task.version):
        raise ValueError(f"Harbor task lock does not match {task.task_id}@{task.version}: {lock_path}")
    reward = None
    if result["reward_valid"]:
        verifier = result.get("verifier_result")
        rewards = verifier.get("rewards") if isinstance(verifier, dict) else None
        reward = rewards.get("reward") if isinstance(rewards, dict) else None
        if type(reward) not in (int, float) or not 0 <= reward <= 1:
            raise ValueError(f"Invalid official Terminal-Bench reward: {path}")
    return {
        "path": str(path),
        "task_id": task.task_id,
        "task_version": task.version,
        "trial_id": result.get("id"),
        "task_checksum": result.get("task_checksum"),
        "reward": reward,
        "success": reward == 1 if reward is not None else None,
    }
