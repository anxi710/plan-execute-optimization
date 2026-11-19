"""Run the four planner frameworks on one matched ALFWorld development task."""

import argparse
import asyncio
import json
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path
from time import perf_counter
from uuid import uuid4


SOURCE_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = SOURCE_ROOT.parent
sys.path.insert(0, str(SOURCE_ROOT))

from runner import run_trial
from toolkit.agents.openai_agent import AsyncChatClient
from toolkit.envs.alfworld_env import AlfWorldEnv, alfworld_settings
from toolkit.tasks.alfworld import AlfWorldRolloutPool, load_alfworld_rows
from toolkit.utils.files import write_json


SPLIT = "dev"
TASK_ID = 2
EXECUTOR_LIMIT = 12
RETURN_EVERY = 2
PLANNER_LIMITS = {"eo": 0, "pe-s": 1, "pe-d": 6, "pc": 6}
MAX_INPUT_BYTES = 11_000
CONSTRAINTS = ["Act only through the provided ALFWorld text environment."]
SHARED_MODEL_SETTINGS = {
    "model": "DeepSeek-V4.1-Flash", "base_url": "https://agi.tongji.edu.cn/v1", "reasoning_effort": "none",
    "timeout": 60, "seed": None,
}
MODEL_SETTINGS = {
    "planner": {**SHARED_MODEL_SETTINGS, "temperature": 0.2, "max_tokens": 512, "stop": None},
    "executor": {**SHARED_MODEL_SETTINGS, "temperature": 0.6, "max_tokens": 256,
                 "stop": ["\nObservation:", "\nTask:", "\n---"]},
}


class PromptBudgetExceeded(RuntimeError):
    """The recorded input exceeded the local limit before any HTTP request."""


class RequestBudgetExceeded(RuntimeError):
    """The role exceeded its allowance before any HTTP request."""


def model_call(client, role, limit, *, model_settings=MODEL_SETTINGS, max_input_bytes=MAX_INPUT_BYTES):
    """Use the toolkit transport and retain the API's original usage fields."""
    settings = model_settings[role]
    options = {name: settings[name] for name in ("model", "temperature", "max_tokens", "reasoning_effort")}
    if settings["stop"] is not None:
        options["stop"] = settings["stop"]
    requests = 0

    async def complete(messages):
        nonlocal requests
        encoded = json.dumps(messages, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if len(encoded) > max_input_bytes:
            raise PromptBudgetExceeded
        if requests >= limit:
            raise RequestBudgetExceeded
        requests += 1
        started = perf_counter()
        response = await client.complete(messages=messages, **options)
        choice = next(iter(response.choices or ()), None)
        return {
            "text": choice.message.content if choice and choice.message.content is not None else "",
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
                            executor_limit=EXECUTOR_LIMIT, planner_limit=None, return_every=RETURN_EVERY):
    if planner_limit is None:
        planner_limit = PLANNER_LIMITS[mode]
    with pool.open_slot() as slot:
        task = slot.load_task(row)
        env = AlfWorldEnv(task, plan_placement="query", **{**alfworld_settings(), "max_steps": executor_limit})
        model_options = {"model_settings": model_settings, "max_input_bytes": max_input_bytes}
        return await run_trial(
            mode=mode, env=env, goal=task_goal(row), constraints=CONSTRAINTS.copy(),
            workspace_id=workspace_id, executor_limit=executor_limit,
            planner_limit=planner_limit, return_every=return_every,
            planner=model_call(client, "planner", planner_limit, **model_options) if planner_limit else None,
            executor=model_call(client, "executor", executor_limit, **model_options),
            save=save,
        )


async def run(run_dir, data_dir, gamefiles, api_key):
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
            "task": row["task"], "goal": goal, "constraints": CONSTRAINTS,
            "data_dir": str(data_dir), "gamefile": row["gamefile"], "gamefile_map": str(gamefiles),
        },
        "budget": {
            "executor_limit": EXECUTOR_LIMIT, "planner_limits": PLANNER_LIMITS,
            "return_every": RETURN_EVERY, "max_requests": executor_calls + planner_calls,
            "max_input_bytes_per_request": MAX_INPUT_BYTES, "automatic_retries": 0,
            "max_output_tokens": executor_calls * MODEL_SETTINGS["executor"]["max_tokens"]
            + planner_calls * MODEL_SETTINGS["planner"]["max_tokens"],
        },
        "models": MODEL_SETTINGS,
        "source": source_version(),
        "runtime": runtime_versions(),
    }
    run_dir.mkdir(parents=True, exist_ok=False)
    manifest_path = run_dir / "manifest.json"
    write_json(manifest_path, manifest)

    settings = MODEL_SETTINGS["executor"]
    try:
        async with AsyncChatClient(base_url=settings["base_url"], api_key=api_key,
                                   timeout=settings["timeout"], max_retries=0) as client:
            for mode in PLANNER_LIMITS:
                identifiers = {"run_id": run_id, "task_id": TASK_ID, "trial_id": mode, "arm": mode}
                print(f"{mode}: started", flush=True)
                record = await run_matched_trial(
                    pool, row, client, mode=mode, workspace_id=f"{run_id}/{mode}",
                    save=lambda record: save_trial(run_dir / records[mode], identifiers, record),
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
    args = parser.parse_args(argv)
    api_key = os.getenv("TONGJI_API_KEY")
    if not api_key:
        parser.error("Set TONGJI_API_KEY in the environment")
    if args.run_dir.exists():
        parser.error("Choose a new --run-dir; the directory already exists")
    try:
        asyncio.run(run(args.run_dir.resolve(), args.data_dir.resolve(), args.gamefiles.resolve(), api_key))
    except KeyboardInterrupt:
        parser.exit(130, "Run interrupted.\n")
    except Exception as error:
        parser.exit(1, f"Run stopped ({type(error).__name__}). Check the output directory for saved evidence.\n")


if __name__ == "__main__":
    main()
