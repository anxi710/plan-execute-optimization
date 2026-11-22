"""Run fixed-Executor ALFWorld rollouts for each queued plan."""

import argparse
import asyncio
import os
import re
import sys
from contextlib import ExitStack
from functools import partial
from importlib.metadata import version
from pathlib import Path


SOURCE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SOURCE_ROOT))
from toolkit.envs.alfworld_env import alfworld_settings
from toolkit.prompts import PlanInjection, load_executor_instruction
from toolkit.utils.config import resolve_config
from toolkit.utils.files import read_yaml_mapping


def load_queue(run_dir, data_dir, split):
    from toolkit.prompts import extract_plan
    from toolkit.tasks.alfworld import load_alfworld_rows
    from toolkit.utils.files import read_jsonl

    rows = load_alfworld_rows(
        data_dir, split, selection_path=run_dir / "tasks.jsonl",
        gamefile_map_path=run_dir / "gamefiles.jsonl",
    )
    tasks = {str(row["id"]): row for row in rows}
    plans = {}
    for item in read_jsonl(run_dir / "execution_queue.jsonl"):
        task_id, plan_id = item["task_id"], item["plan_id"]
        if not isinstance(plan_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", plan_id):
            raise ValueError("Expected a path-safe plan_id")
        if plan_id in plans:
            raise ValueError(f"Duplicate plan_id: {plan_id}")
        row = tasks.get(str(task_id))
        if type(task_id) is not int or not row or row["task"] != item["task"] or not row.get("gamefile"):
            raise ValueError(f"Plan {plan_id} has no matching canonical {split} task and gamefile")
        plan = extract_plan(item["plan"]) if isinstance(item["plan"], str) else ""
        if not plan:
            raise ValueError(f"Empty plan: {plan_id}")
        plans[plan_id] = {**row, "plan": plan}
    if not plans:
        raise ValueError("Execution queue is empty")
    return plans


def rollout_job(plan_id, row, sample_id, path, *, seed):
    from toolkit.rollout.batch import RolloutJob

    return RolloutJob(
        row, row["plan"], path,
        {"plan_id": plan_id, "sample_id": sample_id, "gamefile": row["gamefile"]}, seed=seed,
    )


async def execute(jobs, data_dir, env_config, agent_config, *, split, plan_placement, concurrency):
    from toolkit.models.openai import MeteredChatModel
    from toolkit.envs.alfworld_env import AlfWorldEnv
    from toolkit.rollout.batch import run_rollouts
    from toolkit.tasks.alfworld import AlfWorldRolloutPool

    agent_config = resolve_config({"executor": agent_config})["executor"]
    rows = {job.row["id"]: {**job.row, "plan": None} for job in jobs}
    pool = AlfWorldRolloutPool(data_dir, split, rows.values())

    def report(job, state):
        label = f"{job.metadata['plan_id']}/{job.metadata['sample_id']}"
        if state.finished and not state.incomplete:
            print(f"{label} finished: success={state.success}, steps={state.steps}", flush=True)
        else:
            print(f"{label} interrupted: {state.error}", file=sys.stderr, flush=True)

    results = await run_rollouts(
        jobs,
        open_slot=pool.open_slot,
        create_agent=lambda seed: MeteredChatModel({**agent_config, "seed": seed}),
        environment_factory=partial(AlfWorldEnv, **env_config),
        plan_placement=plan_placement,
        concurrency=concurrency,
        on_result=report,
    )
    completed = sum(state.finished and not state.incomplete for state in results)
    return completed, len(results) - completed


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path(__file__).with_name("config.yaml"))
    parser.add_argument("--run-dir", type=Path)
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--model")
    parser.add_argument("--concurrency", type=int)
    parser.add_argument("--limit", type=int, help="Run only the first N plans in the queue.")
    parser.add_argument("--retry-incomplete", action=argparse.BooleanOptionalAction,
                        help="Archive incomplete samples before restarting them.")
    args = parser.parse_args(argv)
    from toolkit.rollout.batch import archive_incomplete_rollout, load_saved_rollout
    from toolkit.utils.runfiles import exclusive_run_lock, save_settings

    recipe = read_yaml_mapping(args.config)
    run_dir, data_dir = args.run_dir or recipe["run_dir"], args.data_dir or recipe["data_dir"]
    if not run_dir or not data_dir:
        parser.error("Set run_dir and data_dir in the recipe config or pass --run-dir and --data-dir")
    run_dir, data_dir = Path(run_dir).resolve(), Path(data_dir).resolve()
    rollout = recipe["rollout"]
    concurrency = rollout["concurrency"] if args.concurrency is None else args.concurrency
    limit = rollout["limit"] if args.limit is None else args.limit
    retry = rollout["retry_incomplete"] if args.retry_incomplete is None else args.retry_incomplete
    samples_per_plan = rollout["samples_per_plan"]
    placement = rollout["plan_placement"]
    split = recipe["split"]
    config = resolve_config(recipe.get("toolkit", {}))
    env_config = alfworld_settings(config)
    agent_config = config["executor"].copy()
    if args.model is not None:
        agent_config["model_name"] = args.model
    for name, value, minimum in (
        ("concurrency", concurrency, 1), ("samples_per_plan", samples_per_plan, 1),
        ("max_steps", env_config["max_steps"], 1),
        ("max_completion_tokens", agent_config["max_completion_tokens"], 1),
        ("request_max_retries", agent_config["request_max_retries"], 0),
    ):
        if type(value) is not int or value < minimum:
            parser.error(f"{name} must be an integer of at least {minimum}")
    if limit is not None and (type(limit) is not int or limit < 1):
        parser.error("limit must be a positive integer or null")
    if type(retry) is not bool:
        parser.error("retry_incomplete must be a boolean")
    PlanInjection(placement)
    plans = load_queue(run_dir, data_dir, split)
    output = run_dir / "executions"
    with ExitStack() as run:
        try:
            run.enter_context(exclusive_run_lock(output / ".lock"))
        except BlockingIOError:
            parser.error("This run already has an active Executor process")
        save_settings(output / "run_settings.meta", {
            "executor": {name: value for name, value in agent_config.items()
                         if name != "api_key" and (name != "reasoning_effort" or value is not None)},
            "environment": env_config, "data_dir": str(data_dir),
            "environment_versions": {package: version(package) for package in ("alfworld", "textworld")},
            "executor_instruction": load_executor_instruction("alfworld", env_config["instruction_path"]),
            "split": split, "samples_per_plan": samples_per_plan, "plan_placement": placement,
            "concurrency": concurrency,
        })
        pending = []
        archived = []
        complete = incomplete = 0
        for plan_id, row in list(plans.items())[:limit]:
            directory = output / plan_id
            save_settings(directory / "plan.meta", row)
            for sample_id in range(samples_per_plan):
                path = directory / f"sample_{sample_id}.json"
                sample = rollout_job(plan_id, row, sample_id, path, seed=agent_config["seed"])
                state = load_saved_rollout(sample)
                if state is not None:
                    if state.finished and not state.incomplete:
                        complete += 1
                        continue
                    if not retry:
                        incomplete += 1
                        continue
                    archived.append(sample)
                pending.append(sample)
        if pending:
            key = agent_config["api_key"] or os.environ.get("OPENAI_API_KEY")
            if not key:
                parser.error("Set toolkit.executor.api_key or export OPENAI_API_KEY before executing pending samples")
            for sample in archived:
                archive_incomplete_rollout(sample)
            completed_now, interrupted_now = asyncio.run(
                execute(pending, data_dir, env_config, {**agent_config, "api_key": key},
                        split=split, plan_placement=placement, concurrency=concurrency)
            )
            complete += completed_now
            incomplete += interrupted_now
        print(f"Completed rollouts: {complete}; interrupted rollouts: {incomplete}")
    return int(incomplete != 0)


if __name__ == "__main__":
    raise SystemExit(main())
