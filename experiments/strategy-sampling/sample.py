"""Sample same-task ALFWorld plans with and without prior route descriptions."""

import argparse
import asyncio
import os
import random
import re
import sys
from pathlib import Path

from openai import AsyncOpenAI

ROOT = Path(__file__).resolve().parents[2] / "src" / "planner-eval"
sys.path.insert(0, str(ROOT))
from plan_eval.plans import read_jsonl, write_json, write_jsonl


BASE_PROMPT = """You are the high-level planner for a household task in ALFWorld.
A separate executor will observe the environment and choose its own actions.
It can navigate to receptacles, inspect them by moving or opening them, pick up
and place objects, and use the appropriate appliance for cleaning, heating,
cooling, or examination. It has at most 30 turns.

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


def tags(content):
    cleaned = {}
    for tag in ("route", "plan"):
        match = re.search(f"<{tag}>(.*?)</{tag}>", content, re.DOTALL | re.IGNORECASE)
        cleaned[tag] = match.group(1).strip() if match else ""
    return cleaned


async def sample(args, tasks):
    settings = {
        "model": args.model,
        "temperature": 0.8,
        "thinking": "disabled",
        "max_output_tokens": 320,
        "samples_per_condition": 8,
        "api_base": "https://api.deepseek.com",
        "request_timeout_seconds": 60,
        "automatic_retries": 0,
    }
    settings_path = args.run_dir / "planner_settings.json"
    if settings_path.exists():
        import json

        if json.loads(settings_path.read_text()) != settings:
            raise ValueError("Planner settings differ from this run")
    else:
        write_json(settings_path, settings)
    results_dir = args.run_dir / "plans"
    results_dir.mkdir(exist_ok=True)
    limit = asyncio.Semaphore(args.concurrency)

    async with AsyncOpenAI(
        base_url=settings["api_base"], api_key=os.environ["DEEPSEEK_API_KEY"],
        timeout=settings["request_timeout_seconds"], max_retries=0,
    ) as client:
        async def one_task(task):
            task_id = str(task["id"])
            path = results_dir / f"{task_id}.jsonl"
            samples = read_jsonl(path) if path.exists() else []
            done = {(row["condition"], row["sample"]): row for row in samples}
            order = ["A", "B"]
            random.Random(f"42/{task_id}").shuffle(order)
            for slot in range(args.samples):
                for condition in order:
                    if (condition, slot) in done:
                        continue
                    prompt = BASE_PROMPT.format(task=task["task"])
                    if condition == "B" and slot:
                        routes = [done[condition, i]["route"] for i in range(slot)]
                        prompt += HISTORY_PROMPT.format(routes="\n".join(
                            f"- {' '.join(route.split()[:30])}" for route in routes if route
                        ))
                    async with limit:
                        response = await client.chat.completions.create(
                            model=settings["model"], temperature=settings["temperature"],
                            max_tokens=settings["max_output_tokens"],
                            extra_body={"thinking": {"type": settings["thinking"]}},
                            messages=[{"role": "user", "content": prompt}],
                        )
                    choice = response.choices[0]
                    content = choice.message.content or ""
                    row = {
                        "task_id": task["id"], "condition": condition, "sample": slot,
                        "id": response.id, "model": response.model, "prompt": prompt,
                        "finish_reason": choice.finish_reason, "response": content,
                        "usage": response.usage.model_dump() if response.usage else {},
                        **tags(content),
                    }
                    if choice.finish_reason != "stop" or not row["route"] or not row["plan"]:
                        row.update(route="", plan="")
                    samples.append(row)
                    done[condition, slot] = row
                    write_jsonl(path, samples)
            print(f"Task {task_id}: {len(samples)} completions, "
                  f"{sum(bool(row['plan']) for row in samples)} valid format", flush=True)

        outcomes = await asyncio.gather(*(one_task(task) for task in tasks), return_exceptions=True)
        failures = [
            f"Task {task['id']}: {type(result).__name__}, HTTP {getattr(result, 'status_code', '-')}"
            for task, result in zip(tasks, outcomes) if isinstance(result, Exception)
        ]
        if failures:
            print("\n".join(failures), file=sys.stderr)
            raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--model", default="deepseek-flash")
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--task-id", help="Sample a single task using the same run settings")
    parser.add_argument("--samples", type=int, choices=range(1, 9), default=8)
    args = parser.parse_args()
    tasks = [row for row in read_jsonl(args.run_dir / "tasks.jsonl")
             if args.task_id is None or str(row["id"]) == args.task_id]
    if not tasks or args.concurrency < 1:
        parser.error("Select at least one task and a positive concurrency")
    asyncio.run(sample(args, tasks))
