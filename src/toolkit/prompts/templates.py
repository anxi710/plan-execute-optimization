"""Select and render prompt constants or explicit custom instruction files."""

from pathlib import Path

from .alfworld import ALFWORLD_EXECUTOR_TEMPLATE, ALFWORLD_PLANNER_TEMPLATE
from .sciworld import SCIWORLD_EXECUTOR_TEMPLATE, SCIWORLD_PLANNER_TEMPLATE
from .terminalbench import TERMINALBENCH_EXECUTOR_TEMPLATE, TERMINALBENCH_PLANNER_TEMPLATE
from .webshop import WEBSHOP_EXECUTOR_TEMPLATE, WEBSHOP_PLANNER_TEMPLATE


def render_planner_prompt(benchmark: str, task: str) -> str:
    templates = {
        "alfworld": ALFWORLD_PLANNER_TEMPLATE, "sciworld": SCIWORLD_PLANNER_TEMPLATE,
        "webshop": WEBSHOP_PLANNER_TEMPLATE, "terminalbench": TERMINALBENCH_PLANNER_TEMPLATE,
    }
    return templates[benchmark].format(task=task)


def resolve_executor_instruction_path(benchmark: str, config=None) -> str | None:
    """Resolve an explicit file override; None selects the built-in template."""
    if config is None:
        from ..utils.config import DEFAULT_CONFIG
        config = DEFAULT_CONFIG
    path = config["environments"][benchmark]["instruction_path"]
    if path is None:
        return None
    return str((Path(__file__).resolve().parents[2] / path).resolve())


def load_executor_instruction(benchmark: str, instruction_path: str | Path | None = None) -> str:
    if instruction_path is not None:
        return Path(instruction_path).read_text(encoding="utf-8")
    templates = {
        "alfworld": ALFWORLD_EXECUTOR_TEMPLATE, "sciworld": SCIWORLD_EXECUTOR_TEMPLATE,
        "webshop": WEBSHOP_EXECUTOR_TEMPLATE, "terminalbench": TERMINALBENCH_EXECUTOR_TEMPLATE,
    }
    return templates[benchmark]


def render_executor_prompt(instruction: str, task: str) -> str:
    return f"{instruction}\n\n{task}"


def render_action_feedback(observation: str, actions: list[str]) -> str:
    """Append the environment's current action candidates to Executor feedback."""
    if not isinstance(actions, list) or any(not isinstance(action, str) for action in actions):
        raise ValueError("Environment actions must be a list of strings")
    return f"{observation}\nAvailable actions: {', '.join(actions)}"
