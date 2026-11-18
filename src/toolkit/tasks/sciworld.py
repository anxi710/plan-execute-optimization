"""Select ScienceWorld subtasks and variations from canonical task rows."""

from dataclasses import dataclass
from pathlib import Path

from .rows import load_task_rows
from ..utils.config import DEFAULT_CONFIG


@dataclass
class SciWorldTask:
    task_id: int | str
    sub_task_name: str
    variation_idx: int
    observation: str
    data_path: Path
    plan: str | None = None

    @classmethod
    def load_tasks(cls, path, plan_path=None, split=DEFAULT_CONFIG["environments"]["sciworld"]["split"],
                   **selection):
        rows = load_task_rows(path, "sciworld", split, plan_path, **selection)
        tasks = (cls(
            task_id=row["id"], sub_task_name=row["subtask_name"],
            variation_idx=int(str(row["id"]).rsplit("_", 1)[1]),
            observation=row["task"], data_path=Path(path), plan=row["plan"],
        ) for row in rows)
        return tasks, len(rows)
