"""Run the planner frameworks on one matched ALFWorld development task."""

import argparse
import asyncio
import json
import os
import platform
import subprocess
import sys
from contextlib import AsyncExitStack
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path
from time import perf_counter
from uuid import uuid4


SOURCE_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = SOURCE_ROOT.parent
sys.path.insert(0, str(SOURCE_ROOT))

from toolkit.models.openai import AsyncChatClient
from toolkit.envs.alfworld_env import AlfWorldEnv, alfworld_settings
from toolkit.frameworks import run_framework
from toolkit.tasks.alfworld import AlfWorldRolloutPool, load_alfworld_rows
from toolkit.utils.config import resolve_config
from toolkit.utils.files import read_yaml_mapping, write_json


SPLIT = "dev"
TASK_ID = 2
EXECUTOR_LIMIT = 12
RETURN_EVERY = 2
PLANNER_LIMITS = {"eo": 0, "pe-s": 1, "pe-d": 6, "pc": 6}
CONFIG_PATH = Path(__file__).with_name("config.yaml")
RECIPE_CONFIG = read_yaml_mapping(CONFIG_PATH)
TOOLKIT_SETTINGS = resolve_config(RECIPE_CONFIG.get("toolkit", {}))
MAX_INPUT_BYTES = 11_000
SHARED_MODEL_SETTINGS = {
    "timeout": 60, "seed": None,
}
ROLE_OPTIONS = {
    "planner": {"temperature": 0.2, "max_tokens": 512, "stop": None},
    "executor": {"temperature": 0.6, "max_tokens": 256, "stop": ["\nObservation:", "\nTask:", "\n---"]},
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


MODEL_SETTINGS = load_model_settings()[0]


class PromptBudgetExceeded(RuntimeError):
    """The recorded input exceeded the local limit before any HTTP request."""


class RequestBudgetExceeded(RuntimeError):
    """The role exceeded its allowance before any HTTP request."""


def model_call(client, role, limit=None, *, model_settings=MODEL_SETTINGS, max_input_bytes=MAX_INPUT_BYTES):
    """Send one model request and preserve native tool calls alongside text."""
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
    requests = 0

    async def complete(messages, **tool_options):
        nonlocal requests
        payload = {"messages": messages, **options, **tool_options}
        # Historical context-limit replays measure the messages array.
        input_body = payload if limit is None else messages
        encoded = json.dumps(input_body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if len(encoded) > max_input_bytes:
            raise PromptBudgetExceeded
        if limit is not None and requests >= limit:
            raise RequestBudgetExceeded
        requests += 1
        started = perf_counter()
        response = await client.complete(**payload)
        choice = next(iter(response.choices or ()), None)
        tool_calls = getattr(choice.message, "tool_calls", None) if choice else None
        return {
            "text": choice.message.content if choice and choice.message.content is not None else "",
            **({"tool_calls": [call.model_dump(mode="json", exclude_none=True) for call in tool_calls]}
               if tool_calls else {}),
            "usage": response.usage.model_dump(exclude_none=True) if response.usage else None,
            "model": response.model,
            "id": response.id,
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
                            model_settings=MODEL_SETTINGS, max_input_bytes=MAX_INPUT_BYTES,
                            executor_limit=EXECUTOR_LIMIT, planner_limit=None, return_every=None,
                            protocol_version=None):
    if return_every is not None and planner_limit is None:
        planner_limit = PLANNER_LIMITS[mode]
    with pool.open_slot() as slot:
        task = slot.load_task(row)
        env = AlfWorldEnv(task, **{**alfworld_settings(), "max_steps": executor_limit})
        model_options = {"model_settings": model_settings, "max_input_bytes": max_input_bytes}
        return await run_framework(
            mode=mode, env=env, goal=task_goal(row),
            workspace_id=workspace_id, executor_limit=executor_limit,
            planner_limit=planner_limit, return_every=return_every,
            planner=model_call(client, "planner", planner_limit, **model_options) if mode != "eo" else None,
            executor=model_call(client, "executor", executor_limit if return_every is not None else None,
                                **model_options),
            save=save, protocol_version=protocol_version,
        )


async def run(run_dir, data_dir, gamefiles, api_key, *, model_settings=MODEL_SETTINGS):
    model_settings = {role: {**settings, "model": settings["model"] or model_settings["executor"]["model"]}
                      for role, settings in model_settings.items()}
    row, = load_alfworld_rows(data_dir, SPLIT, task_id=TASK_ID, gamefile_map_path=gamefiles)
    goal = task_goal(row)
    pool = AlfWorldRolloutPool(data_dir, SPLIT, [row])
    run_id = uuid4().hex
    records = {mode: f"{mode}.json" for mode in PLANNER_LIMITS}
    executor_calls = len(records) * EXECUTOR_LIMIT
    planner_calls = sum(PLANNER_LIMITS.values())
    manifest = {
        "schema_version": 1, "run_id": run_id, "purpose": "live_model_interface_smoke",
        "started_at": utc_now(), "finished_at": None, "status": "running",
        "run_order": list(records), "records": records,
        "benchmark": {
            "name": "ALFWorld", "data_version": "json_2.1.1", "split": SPLIT, "task_id": TASK_ID,
            "task": row["task"], "goal": goal,
            "data_dir": str(data_dir), "gamefile": row["gamefile"], "gamefile_map": str(gamefiles),
        },
        "budget": {
            "executor_limit": EXECUTOR_LIMIT, "planner_limits": PLANNER_LIMITS,
            "return_every": RETURN_EVERY, "max_requests": executor_calls + planner_calls,
            "max_input_bytes_per_request": MAX_INPUT_BYTES, "automatic_retries": 0,
            "max_output_tokens": executor_calls * model_settings["executor"]["max_tokens"]
            + planner_calls * model_settings["planner"]["max_tokens"],
        },
        "models": model_settings,
        "source": source_version(),
        "runtime": runtime_versions(),
    }
    run_dir.mkdir(parents=True, exist_ok=False)
    manifest_path = run_dir / "manifest.json"
    write_json(manifest_path, manifest)

    try:
        async with AsyncExitStack() as stack:
            clients = {}
            for role, settings in model_settings.items():
                key = api_key[role] if isinstance(api_key, dict) else api_key
                clients[role] = await stack.enter_async_context(AsyncChatClient(
                    base_url=settings["base_url"], api_key=key, timeout=settings["timeout"], max_retries=0,
                ))
            for mode in PLANNER_LIMITS:
                identifiers = {"run_id": run_id, "task_id": TASK_ID, "trial_id": mode, "arm": mode}
                print(f"{mode}: started", flush=True)
                record = await run_matched_trial(
                    pool, row, clients, mode=mode, workspace_id=f"{run_id}/{mode}",
                    save=lambda record: save_trial(run_dir / records[mode], identifiers, record),
                    planner_limit=PLANNER_LIMITS[mode], return_every=RETURN_EVERY,
                    model_settings=model_settings,
                )
                print(f"{mode}: recorded {len(record['events'])} events", flush=True)
    except (Exception, asyncio.CancelledError, KeyboardInterrupt) as error:
        manifest.update(status="interrupted", interrupted_by=type(error).__name__)
        raise
    else:
        manifest["status"] = "complete"
    finally:
        manifest["finished_at"] = utc_now()
        write_json(manifest_path, manifest)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog=f"No retries. Each model request accepts at most {MAX_INPUT_BYTES:,} UTF-8 message bytes.",
    )
    parser.add_argument("--run-dir", required=True, type=Path, help="New output directory.")
    parser.add_argument("--data-dir", required=True, type=Path, help="Local ALFWorld dataset directory.")
    parser.add_argument("--gamefiles", required=True, type=Path, help="Verified ALFWorld dev gamefile map.")
    parser.add_argument("--config", type=Path, default=CONFIG_PATH, help="Recipe YAML with toolkit overrides.")
    parser.add_argument("--legacy", action="store_true", help="Reproduce the historical four-framework smoke run.")
    args = parser.parse_args(argv)
    model_settings, api_key = load_model_settings(args.config)
    if not all(api_key.values()):
        parser.error("Set api_key in the recipe config or OPENAI_API_KEY in the environment")
    if args.run_dir.exists():
        parser.error("Choose a new --run-dir; the directory already exists")
    try:
        if args.legacy:
            asyncio.run(run(args.run_dir.resolve(), args.data_dir.resolve(), args.gamefiles.resolve(), api_key,
                            model_settings=model_settings))
        else:
            from benchmark import run_benchmark

            asyncio.run(run_benchmark(
                args.run_dir.resolve(), args.data_dir.resolve(), args.gamefiles.resolve(), api_key,
                split=SPLIT, task_id=TASK_ID, concurrency=1,
                model_order=(model_settings["executor"]["model"],), model_settings=model_settings,
            ))
    except KeyboardInterrupt:
        parser.exit(130, "Run interrupted.\n")
    except Exception as error:
        parser.exit(1, f"Run stopped ({type(error).__name__}). Check the output directory for saved evidence.\n")


if __name__ == "__main__":
    main()
