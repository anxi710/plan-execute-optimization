"""Load reviewed Terminal-Bench instructions without running task code."""

import tomllib
from dataclasses import dataclass
from pathlib import Path

from ..utils.config import DEFAULT_CONFIG


@dataclass(frozen=True)
class TerminalBenchTask:
    task_id: str
    version: str
    observation: str

    def planner_row(self):
        """Use the task's local name as the Planner row ID."""
        return {"id": self.task_id.removeprefix("terminal-bench/"), "task": self.observation}

    @classmethod
    def load(cls, task_dir, config=DEFAULT_CONFIG):
        """Read only the Harbor manifest and instruction for an approved task."""
        directory = Path(task_dir)
        with (directory / "task.toml").open("rb") as source:
            manifest = tomllib.load(source)
        settings = config["environments"]["terminalbench"]
        task = manifest.get("task", {})
        if not isinstance(task, dict):
            raise ValueError(f"Terminal-Bench manifest has no task table: {directory}")
        task_id, version = task.get("name"), task.get("version")
        versions = settings["reviewed_task_versions"]
        if not isinstance(task_id, str) or task_id not in versions or versions[task_id] != version:
            raise ValueError(f"Terminal-Bench task/version is not in the reviewed list: {task_id!r} {version!r}")
        instruction = (directory / "instruction.md").read_text(encoding="utf-8").strip()
        if not instruction:
            raise ValueError(f"Terminal-Bench task has no instruction: {task_id}")
        return cls(task_id, version, instruction)
