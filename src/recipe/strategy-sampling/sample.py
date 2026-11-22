"""Sample same-task ALFWorld plans with and without prior route descriptions."""

import argparse
import asyncio
import os
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from toolkit.models.openai import AsyncChatClient
from toolkit.envs.alfworld_env import alfworld_settings
from toolkit.utils.config import resolve_config
from toolkit.utils.files import read_jsonl, read_yaml_mapping, write_jsonl
from toolkit.utils.runfiles import save_settings


# Preserve the first run's prompt and route format for reproduction.
BASE_PROMPT = """You are the high-level planner for a household task in ALFWorld.
A separate executor will observe the environment and choose its own actions.
It can navigate to receptacles, inspect them by moving or opening them, pick up
and place objects, and use the appropriate appliance for cleaning, heating,
cooling, or examination. It has at most {executor_max_steps} turns.

Return one complete strategy from the initial state to the goal. Give the
executor the key decisions: how to find relevant objects, prerequisite order,
and when to switch routes if an assumption fails. Use only the task description
and the visible starting information. Leave locations of hidden objects
conditional. Keep the plan high level, about 70–130 words. Return:
<route>a one-sentence summary of the key strategic choices</route>
<plan>the plan to hand to the executor</plan>

Starting observation and goal:
{task}"""

HISTORY_PROMPT = """\n
Earlier candidate routes for this same task:
{routes}
Try a materially different feasible choice if the task permits it. Focus on
what to check first, which dependencies to satisfy first, or how to search.
Use a justified route if the alternatives would violate the task constraints."""


def strategy_prompt(task, prior_routes=None, *, executor_max_steps, history_words):
    """Format a task, optionally asking for a different route."""
    prompt = BASE_PROMPT.format(task=task, executor_max_steps=executor_max_steps)
    if prior_routes is not None:
        routes = "\n".join(f"- {' '.join(route.split()[:history_words])}" for route in prior_routes if route)
        prompt += HISTORY_PROMPT.format(routes=routes)
    return prompt


def parse_strategy_reply(content):
    """Extract the first route and plan tags, using empty strings when absent."""
    cleaned = {}
    for tag in ("route", "plan"):
        match = re.search(f"<{tag}>(.*?)</{tag}>", content, re.DOTALL | re.IGNORECASE)
        cleaned[tag] = match.group(1).strip() if match else ""
    return cleaned


async def sample(run_dir, tasks, settings, *, samples):
    api_key = settings.get("api_key") or os.environ["OPENAI_API_KEY"]
    save_settings(run_dir / "planner_settings.json", {name: value for name, value in settings.items()
                                                    if name != "api_key"
                                                    and (name != "reasoning_effort" or value is not None)})
    results_dir = run_dir / "plans"
    results_dir.mkdir(exist_ok=True)

    async with AsyncChatClient(
        base_url=settings["api_base"], api_key=api_key,
        timeout=settings["request_timeout_seconds"], max_retries=settings["automatic_retries"],
        max_concurrency=settings["concurrency"],
    ) as client:
        async def one_task(task):
            task_id = str(task["id"])
            path = results_dir / f"{task_id}.jsonl"
            rows = read_jsonl(path) if path.exists() else []
            done = {(row["condition"], row["sample"]): row for row in rows}
            order = ["A", "B"]
            random.Random(f"{settings['order_seed']}/{task_id}").shuffle(order)
            for slot in range(samples):
                for condition in order:
                    if (condition, slot) in done:
                        continue
                    prior_routes = None
                    if condition == "B" and slot:
                        prior_routes = [done[condition, i]["route"] for i in range(slot)]
                    prompt = strategy_prompt(
                        task["task"], prior_routes, executor_max_steps=settings["executor_max_steps"],
                        history_words=settings["history_words"],
                    )
                    response = await client.complete(messages=[{"role": "user", "content": prompt}], **options)
                    choice = response.choices[0]
                    content = choice.message.content or ""
                    row = {
                        "task_id": task["id"], "condition": condition, "sample": slot,
                        "id": response.id, "model": response.model, "prompt": prompt,
                        "finish_reason": choice.finish_reason, "response": content,
                        "usage": response.usage.model_dump() if response.usage else {},
                        **parse_strategy_reply(content),
                    }
                    if choice.finish_reason != "stop" or not row["route"] or not row["plan"]:
                        row.update(route="", plan="")
                    rows.append(row)
                    done[condition, slot] = row
                    write_jsonl(path, rows)
            print(f"Task {task_id}: {len(rows)} completions, "
                  f"{sum(bool(row['plan']) for row in rows)} valid format", flush=True)

        options = {"model": settings["model"], settings["token_parameter"]: settings["max_output_tokens"]}
        if settings["temperature"] is not None:
            options["temperature"] = settings["temperature"]
        if settings["thinking"] is not None:
            options["extra_body"] = {"thinking": {"type": settings["thinking"]}}
        if settings.get("reasoning_effort") is not None:
            options["reasoning_effort"] = settings["reasoning_effort"]
        outcomes = await asyncio.gather(*(one_task(task) for task in tasks), return_exceptions=True)
        failures = [
            f"Task {task['id']}: {type(result).__name__}, HTTP {getattr(result, 'status_code', '-')}"
            for task, result in zip(tasks, outcomes) if isinstance(result, Exception)
        ]
        if failures:
            print("\n".join(failures), file=sys.stderr)
            raise SystemExit(1)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path(__file__).with_name("config.yaml"))
    parser.add_argument("--run-dir", type=Path)
    parser.add_argument("--model")
    parser.add_argument("--concurrency", type=int)
    parser.add_argument("--task-id", help="Sample a single task using the same run settings")
    parser.add_argument("--samples", type=int, help="Sample up to this many slots per condition")
    args = parser.parse_args(argv)
    recipe = read_yaml_mapping(args.config)
    run_dir = args.run_dir or recipe["run_dir"]
    if not run_dir:
        parser.error("Set run_dir in the recipe config or pass --run-dir")
    run_dir = Path(run_dir)
    config = resolve_config(recipe.get("toolkit", {}))
    env_config = alfworld_settings(config)
    settings = {**{name: config["planner_generation"][name]
                   for name in ("api_base", "api_key", "thinking", "reasoning_effort")},
                **recipe["planner"], "executor_max_steps": env_config["max_steps"]}
    if args.model is not None:
        settings["model"] = args.model
    if args.concurrency is not None:
        settings["concurrency"] = args.concurrency
    for name, minimum in (
        ("concurrency", 1), ("samples_per_condition", 1), ("history_words", 1),
        ("executor_max_steps", 1), ("max_output_tokens", 1), ("automatic_retries", 0),
    ):
        if type(settings[name]) is not int or settings[name] < minimum:
            parser.error(f"{name} must be an integer of at least {minimum}")
    if settings["token_parameter"] not in ("max_tokens", "max_completion_tokens"):
        parser.error("Unsupported Planner token_parameter")
    samples = settings["samples_per_condition"] if args.samples is None else args.samples
    if not 1 <= samples <= settings["samples_per_condition"]:
        parser.error("--samples must be within the configured per-condition count")
    task_id = recipe["task_id"] if args.task_id is None else args.task_id
    tasks = [row for row in read_jsonl(run_dir / "tasks.jsonl")
             if task_id is None or str(row["id"]) == str(task_id)]
    if not tasks:
        parser.error("Select at least one task")
    asyncio.run(sample(run_dir, tasks, settings, samples=samples))


if __name__ == "__main__":
    main()
