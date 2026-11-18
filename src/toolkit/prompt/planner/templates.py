from pathlib import Path


INSTRUCTION_DIR = Path(__file__).with_name("instruction")
ALFWORLD_TEMPLATE = (INSTRUCTION_DIR / "alfworld.txt").read_text(encoding="utf-8")
SCIWORLD_TEMPLATE = (INSTRUCTION_DIR / "sciworld.txt").read_text(encoding="utf-8")
WEBSHOP_TEMPLATE = (INSTRUCTION_DIR / "webshop.txt").read_text(encoding="utf-8")
TERMINALBENCH_TEMPLATE = (INSTRUCTION_DIR / "terminalbench.txt").read_text(encoding="utf-8")


def render_planner_prompt(benchmark: str, task: str) -> str:
    """Render the shared Planner template for one benchmark task."""
    templates = {
        "alfworld": ALFWORLD_TEMPLATE, "sciworld": SCIWORLD_TEMPLATE,
        "webshop": WEBSHOP_TEMPLATE, "terminalbench": TERMINALBENCH_TEMPLATE,
    }
    return templates[benchmark].format(task=task)
