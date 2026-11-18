"""Load toolkit defaults and derive settings for one recipe."""

from copy import deepcopy
from pathlib import Path

from .files import read_yaml_mapping


SOURCE_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = SOURCE_ROOT / "toolkit" / "config.yaml"


def load_config(path=CONFIG_PATH):
    config = read_yaml_mapping(path)
    for section in ("planner_generation", "executor", "environments"):
        if not isinstance(config.get(section), dict):
            raise ValueError(f"Expected a '{section}' mapping in {path}")
    return config


DEFAULT_CONFIG = load_config()


def resolve_config(overrides, defaults=DEFAULT_CONFIG):
    """Apply toolkit overrides without modifying the shared defaults."""
    if not isinstance(overrides, dict):
        raise ValueError("Toolkit overrides must be a mapping")
    config = deepcopy(defaults)
    for name, value in overrides.items():
        if name not in defaults:
            raise ValueError(f"Unknown toolkit setting: {name}")
        config[name] = resolve_config(value, defaults[name]) if isinstance(defaults[name], dict) else value
    return config
