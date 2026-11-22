"""Configure and run the current framework benchmark."""

import argparse
import asyncio
import os
import platform
import subprocess
import sys
from pathlib import Path
from time import perf_counter
from datetime import datetime, timezone
from importlib.metadata import version

SOURCE_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = SOURCE_ROOT.parent
sys.path.insert(0, str(SOURCE_ROOT))

from toolkit.envs.alfworld_env import AlfWorldEnv, alfworld_settings
from toolkit.frameworks import FRAMEWORK_PROTOCOL, run_framework
from toolkit.utils.config import resolve_config
from toolkit.utils.files import read_yaml_mapping, write_json

SPLIT = "dev"
TASK_ID = 2
EXECUTOR_LIMIT = 20
CONFIG_PATH = Path(__file__).with_name("config.yaml")
RECIPE_CONFIG = read_yaml_mapping(CONFIG_PATH)
TOOLKIT_SETTINGS = resolve_config(RECIPE_CONFIG.get("toolkit", {}))
SHARED_MODEL_SETTINGS = {"timeout": 60, "seed": None}
ROLE_OPTIONS = {
    "planner": {"temperature": 0.2, "max_tokens": 1536, "stop": None},
    "executor": {"temperature": 0.6, "max_tokens": 768, "stop": ["\nObservation:", "\nTask:", "\n---"]},
}


def load_model_settings(path=CONFIG_PATH):
    recipe = read_yaml_mapping(path)
    config = resolve_config(recipe.get("toolkit", {}), defaults=TOOLKIT_SETTINGS)
    settings, api_keys = {}, {}
    for role, section in (("planner", "planner_generation"), ("executor", "executor")):
        connection = config[section]
        settings[role] = {**SHARED_MODEL_SETTINGS, **ROLE_OPTIONS[role],
                          "base_url": connection["api_base"], "model": connection["model_name"],
                          **{name: connection[name] for name in ("thinking", "reasoning_effort")
                             if connection[name] is not None}}
        api_keys[role] = connection["api_key"] or os.getenv("OPENAI_API_KEY")
    return settings, api_keys


def load_context_window(path=CONFIG_PATH):
    config = resolve_config(read_yaml_mapping(path).get("toolkit", {}), defaults=TOOLKIT_SETTINGS)
    return config["context_window"]


MODEL_SETTINGS = load_model_settings()[0]


def model_call(client, role, *, model_settings=MODEL_SETTINGS):
    """Send the current request; Toolkit owns context selection and budgeting."""
    client = client[role] if isinstance(client, dict) else client
    settings = model_settings[role]
    options = {name: settings[name] for name in ("model", "temperature", "max_tokens")}
    options["model"] = settings["model"] or model_settings["executor"]["model"]
    if settings.get("reasoning_effort") is not None:
        options["reasoning_effort"] = settings["reasoning_effort"]
    if settings.get("thinking") is not None:
        options["extra_body"] = {"thinking": {"type": settings["thinking"]}}
    if settings["stop"] is not None:
        options["stop"] = settings["stop"]

    async def complete(messages, **tool_options):
        started = perf_counter()
        response = await client.complete(messages=messages, **options, **tool_options)
        choice = next(iter(response.choices or ()), None)
        message = choice.message if choice else None
        tool_calls = getattr(message, "tool_calls", None)
        return {
            "text": message.content if message and message.content is not None else "",
            **({"tool_calls": [call.model_dump(mode="json", exclude_none=True) for call in tool_calls]}
               if tool_calls else {}),
            **{name: getattr(message, name) for name in ("reasoning", "reasoning_content")
               if getattr(message, name, None) is not None},
            "usage": response.usage.model_dump(exclude_none=True) if response.usage else None,
            "model": response.model, "id": response.id,
            "finish_reason": choice.finish_reason if choice else None,
            "seconds": round(perf_counter() - started, 6),
        }

    return complete


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def source_version():
    paths = ["src/toolkit", "src/recipe/planner-centered"]
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True).strip()
    changes = subprocess.check_output(
        ["git", "status", "--porcelain", "--", *paths], cwd=REPO_ROOT, text=True,
    )
    return {"baseline_commit": commit, "version": "working_tree" if changes else "committed", "paths": paths}

def save_trial(path, identifiers, record):
    events = [{**identifiers, **event} for event in record["events"]]
    write_json(path, {**record, **identifiers, "events": events})

def task_goal(row):
    goal = row["task"].partition("\nYour task is to: ")[2].strip()
    if not goal:
        raise ValueError(f"ALFWorld task {row['id']} has no goal line")
    return goal


def runtime_versions(packages=None):
    if packages is None:
        packages = ("alfworld", "textworld", "openai", "PyYAML")
    return {
        "python": platform.python_version(), "platform": platform.platform(),
        "dependencies": {package: version(package) for package in packages},
    }


async def run_matched_trial(pool, row, client, *, mode, workspace_id, save,
                            model_settings=MODEL_SETTINGS, context_window=None,
                            executor_limit=EXECUTOR_LIMIT, protocol_version=FRAMEWORK_PROTOCOL):
    with pool.open_slot() as slot:
        task = slot.load_task(row)
        env = AlfWorldEnv(task, **{**alfworld_settings(), "max_steps": executor_limit})
        return await run_framework(
            mode=mode, env=env, goal=task_goal(row), workspace_id=workspace_id,
            executor_limit=executor_limit, context_window=context_window,
            planner=model_call(client, "planner", model_settings=model_settings) if mode != "eo" else None,
            executor=model_call(client, "executor", model_settings=model_settings),
            save=save, benchmark="alfworld", protocol_version=protocol_version,
        )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", required=True, type=Path)
    parser.add_argument("--gamefiles", required=True, type=Path)
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    args = parser.parse_args(argv)
    from benchmark import run_benchmark
    settings, keys = load_model_settings(args.config)
    asyncio.run(run_benchmark(
        args.run_dir, args.data_dir, args.gamefiles, keys, split=SPLIT, task_id=TASK_ID,
        concurrency=1, model_order=(settings["executor"]["model"],), model_settings=settings,
        context_window=load_context_window(args.config),
    ))


if __name__ == "__main__":
    main()
