"""Generate one plan per task with the shared Planner prompts."""

import asyncio
from os import PathLike
from pathlib import Path

from ..agents.openai_agent import AsyncChatClient
from ..prompts import extract_plan, render_planner_prompt
from ..tasks.rows import task_rows_by_id
from ..utils.config import DEFAULT_CONFIG
from ..utils.files import read_jsonl, write_jsonl
from ..utils.runfiles import exclusive_run_lock, save_settings


DEFAULTS = DEFAULT_CONFIG["planner_generation"]


class PlannerOutputTruncated(ValueError):
    """The Planner reached its output limit while generating a plan."""


async def _generate_plan(client, benchmark, row, options, max_retries):
    messages = [{"role": "user", "content": render_planner_prompt(benchmark, row["task"])}]
    for attempt in range(max_retries + 1):
        try:
            reply = await client.complete(messages=messages, **options)
        except Exception as error:
            failure = type(error).__name__
        else:
            choices = getattr(reply, "choices", None)
            if not choices or len(choices) != 1:
                failure = "expected one reply"
            else:
                choice = choices[0]
                finish_reason = getattr(choice, "finish_reason", None)
                if finish_reason == "length":
                    raise PlannerOutputTruncated(f"Planner output was truncated for task {row['id']}")
                content = getattr(getattr(choice, "message", None), "content", None)
                plan = extract_plan(content) if isinstance(content, str) else ""
                if plan:
                    usage = getattr(reply, "usage", None)
                    return {
                        "id": row["id"], "task": row["task"], "plan": plan,
                        "response": content, "finish_reason": finish_reason,
                        "model": getattr(reply, "model", None),
                        "usage": usage.model_dump() if usage is not None else {},
                    }
                failure = "empty plan"
        if attempt == max_retries:
            raise RuntimeError(f"Planner failed for task {row['id']} ({failure})")
        await asyncio.sleep(2 ** attempt)


def _resume_plans(output_file, settings_path, settings, selected):
    if output_file.exists() and not settings_path.exists():
        raise ValueError("The existing plan file has no settings record. Choose a new output file.")
    save_settings(settings_path, settings)

    saved = read_jsonl(output_file) if output_file.exists() else []
    completed = task_rows_by_id(saved)
    for task_id, item in completed.items():
        if task_id not in selected or selected[task_id]["task"] != item["task"]:
            raise ValueError("The existing plan file contains different tasks. Choose a new output file.")
        if not isinstance(item.get("plan"), str) or not extract_plan(item["plan"]):
            raise ValueError(f"The existing plan for task {task_id} is empty.")
    return saved, [row for task_id, row in selected.items() if task_id not in completed]


async def generate_plans(tasks, output_file, *, benchmark, api_base, api_key, model, max_tokens,
                         temperature=DEFAULTS["temperature"], token_parameter=DEFAULTS["token_parameter"],
                         thinking=DEFAULTS["thinking"], timeout=DEFAULTS["timeout"],
                         max_retries=DEFAULTS["max_retries"], max_concurrency=DEFAULTS["max_concurrency"],
                         batch_size=DEFAULTS["batch_size"], task_id=None):
    """Generate or resume a plan JSONL from a task JSONL path or task rows."""
    for name, value, minimum in (
        ("max_tokens", max_tokens, 1), ("max_retries", max_retries, 0),
        ("max_concurrency", max_concurrency, 1), ("batch_size", batch_size, 1),
    ):
        if type(value) is not int or value < minimum:
            raise ValueError(f"{name} must be an integer of at least {minimum}.")
    if timeout <= 0:
        raise ValueError("timeout must be positive.")
    if token_parameter not in ("max_tokens", "max_completion_tokens"):
        raise ValueError(f"Unsupported token parameter {token_parameter!r}.")
    output_file = Path(output_file).resolve()
    settings_path = output_file.with_suffix(f"{output_file.suffix}.meta")
    lock_path = output_file.with_suffix(f"{output_file.suffix}.lock")
    input_file = Path(tasks).resolve() if isinstance(tasks, (str, PathLike)) else None
    if input_file in (output_file, settings_path.resolve(), lock_path.resolve()):
        raise ValueError("Planner input and output paths must differ.")
    selected = task_rows_by_id(read_jsonl(input_file) if input_file is not None else tasks)
    if not selected:
        raise ValueError("No Planner tasks were supplied.")
    if task_id is not None:
        task_id = str(task_id)
        if task_id not in selected:
            raise ValueError(f"Task ID {task_id} is not in the Planner input.")
        selected = {task_id: selected[task_id]}

    options = {"model": model, token_parameter: max_tokens}
    if temperature is not None:
        options["temperature"] = temperature
    if thinking is not None:
        options["extra_body"] = {"thinking": {"type": thinking}}
    settings = {
        "benchmark": benchmark, "prompt_template": render_planner_prompt(benchmark, "{task}"),
        "input_file": str(input_file) if input_file is not None else None, "task_id": task_id,
        "api_base": api_base, "request": options, "timeout": timeout, "max_retries": max_retries,
        "max_concurrency": max_concurrency, "batch_size": batch_size,
    }

    with exclusive_run_lock(lock_path):
        saved, pending = _resume_plans(output_file, settings_path, settings, selected)
        if not pending:
            return saved
        async with AsyncChatClient(base_url=api_base, api_key=api_key, timeout=timeout,
                                   max_concurrency=max_concurrency) as client:
            for offset in range(0, len(pending), batch_size):
                results = await asyncio.gather(*(
                    _generate_plan(client, benchmark, row, options, max_retries)
                    for row in pending[offset:offset + batch_size]
                ), return_exceptions=True)
                plans = [result for result in results if not isinstance(result, BaseException)]
                if plans:
                    saved.extend(plans)
                    write_jsonl(output_file, saved)
                for result in results:
                    if isinstance(result, BaseException):
                        raise result
    return saved
