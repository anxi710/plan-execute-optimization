"""Load and render benchmark Executor instructions."""

from pathlib import Path

from ...utils.config import DEFAULT_CONFIG, SOURCE_ROOT


def resolve_executor_instruction_path(benchmark: str, config=DEFAULT_CONFIG) -> str:
    """Resolve a configured instruction path relative to the source root."""
    path = config["environments"][benchmark]["instruction_path"]
    return str((SOURCE_ROOT / path).resolve())


def load_executor_instruction(instruction_path: str | Path) -> str:
    """Read the selected instruction as UTF-8 text."""
    return Path(instruction_path).read_text(encoding="utf-8")


def render_executor_prompt(instruction: str, task: str) -> str:
    """Join the instruction and the prepared initial task text."""
    return f"{instruction}\n\n{task}"
