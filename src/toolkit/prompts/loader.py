"""Load one framework's benchmark-specific prompt module."""

from importlib import import_module
from types import ModuleType


FRAMEWORK_FOLDERS = {
    "eo": "eo",
    "pe-s": "pe_s",
    "pe-d-f": "pe_d_f",
    "pe-d-s": "pe_d_s",
    "pc-f": "pc_f",
    "pc-s": "pc_s",
}
BENCHMARKS = ("alfworld", "sciworld", "webshop", "terminalbench")


def load_framework_prompts(mode: str, benchmark: str) -> ModuleType:
    """Select prompts by the actual execution mode and benchmark."""
    family = FRAMEWORK_FOLDERS[mode]
    if benchmark not in BENCHMARKS:
        raise KeyError(benchmark)
    return import_module(f".{family}.{benchmark}", package=__package__)
