"""Select WebShop goals by canonical task ID and fixed goal index."""

from dataclasses import dataclass

from .rows import load_task_rows
from ..utils.config import DEFAULT_CONFIG


@dataclass
class WebShopTask:
    task_id: int | str
    session: int
    observation: str
    plan: str | None = None

    @classmethod
    def load_tasks(cls, path, plan_path=None, split=DEFAULT_CONFIG["environments"]["webshop"]["split"],
                   **selection):
        rows = load_task_rows(path, "webshop", split, plan_path, **selection)
        tasks = []
        for row in rows:
            session = row.get("session")
            if type(session) is not int or session < 0:
                raise ValueError(f"WebShop task {row['id']} requires a nonnegative session index")
            tasks.append(cls(row["id"], session, row["task"], row["plan"]))
        return iter(tasks), len(tasks)
