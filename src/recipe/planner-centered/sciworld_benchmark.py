"""Prepare or run the complete test variation split of the bundled ScienceWorld simulator."""

import argparse
import asyncio
import json
import os
from contextlib import ExitStack
from importlib.metadata import version
from pathlib import Path

from benchmark import CONCURRENCY, MAX_CONCURRENCY, MODELS, run_matrix
from run import model_call
from runner import run_trial
from toolkit.envs.sciworld_env import DEFAULTS, SciWorldEnv, open_sciworld_backend, sciworld_settings
from toolkit.tasks.sciworld import SciWorldTask
from toolkit.utils.files import write_jsonl


CATALOG = "sciworld_test_tasks.jsonl"
RETURN_EVERY = 4
CONSTRAINTS = ["Act only through the provided ScienceWorld text environment."]


def test_variations(env):
    variants = []
    for name in sorted(env.get_task_names()):
        env.load(name, 0, simplificationStr=DEFAULTS["simplification"], generateGoldPath=False)
        variants.extend((name, int(index)) for index in sorted(env.get_variations_test()))
    return variants


def prepare_catalog(catalog_dir):
    target = catalog_dir / CATALOG
    if target.exists():
        raise FileExistsError("Use a new ScienceWorld catalog directory")
    with open_sciworld_backend() as env:
        rows = []
        for name, index in test_variations(env):
            env.load(name, index, simplificationStr=DEFAULTS["simplification"], generateGoldPath=False)
            goal = env.get_task_description().removeprefix("Task Description:").strip()
            if not goal:
                raise ValueError(f"Missing public task description: {name}_{index}")
            rows.append({"id": f"{name}_{index}", "task": goal, "subtask_name": name})
        write_jsonl(target, rows)
    print(f"Prepared {len(rows)} official test variations in {target}")


async def run_sciworld(run_dir, catalog_dir, step_limits_path, api_key, *, concurrency, resume, model=None):
    from scienceworld.utils import infer_task

    tasks = {task.task_id: task for task in SciWorldTask.load_tasks(catalog_dir, split="test")[0]}
    with open_sciworld_backend() as env:
        expected = set(test_variations(env))
    actual = {(task.sub_task_name, task.variation_idx) for task in tasks.values()}
    if actual != expected or len(tasks) != len(expected):
        raise ValueError("The ScienceWorld catalog must contain the full official test variation split")
    limits = {infer_task(name): limit for name, limit in json.loads(step_limits_path.read_text()).items()}
    fallback_limit = DEFAULTS["server_step_limit"]
    dataset = {
        "name": "ScienceWorld", "data_version": version("scienceworld"), "split": "test",
        "selection": "full_split", "canonical_task_file": str(catalog_dir / CATALOG),
        "canonical_task_count": len(tasks), "return_every": RETURN_EVERY,
        "max_input_bytes": 262_144, "compress_traces": True,
        "runtime_packages": ["scienceworld", "openai", "PyYAML"],
        "constraints": CONSTRAINTS, "simplification": DEFAULTS["simplification"],
        "step_limits_path": str(step_limits_path), "unlisted_family_step_limit": fallback_limit,
        "tasks": [{"task_id": task_id, "task": task.observation, "goal": task.observation,
                   "family": task.sub_task_name, "variation_id": task.variation_idx,
                   "executor_limit": limits.get(task.sub_task_name, fallback_limit)}
                  for task_id, task in tasks.items()],
    }

    with ExitStack() as stack:
        slots = asyncio.Queue()
        for _ in range(concurrency):
            slots.put_nowait(stack.enter_context(open_sciworld_backend()))

        async def run_one(task, client, *, mode, workspace_id, model_settings, max_input_bytes, save,
                          executor_limit, planner_limit, return_every):
            server = await slots.get()
            try:
                config = {**sciworld_settings(), "max_steps": executor_limit}
                env = SciWorldEnv(task, server, plan_placement="query", **config)
                model = {"model_settings": model_settings, "max_input_bytes": max_input_bytes}
                return await run_trial(
                    mode=mode, env=env, goal=task.observation, constraints=CONSTRAINTS,
                    workspace_id=workspace_id, executor_limit=executor_limit, planner_limit=planner_limit,
                    return_every=return_every, save=save, benchmark="sciworld",
                    planner=model_call(client, "planner", planner_limit, **model) if planner_limit else None,
                    executor=model_call(client, "executor", executor_limit, **model),
                )
            finally:
                slots.put_nowait(server)

        await run_matrix(run_dir, tasks, dataset, api_key, run_one=run_one, concurrency=concurrency, resume=resume,
                         model_order=(model,) if model is not None else None)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog-dir", required=True, type=Path, help="Directory for the complete generated test catalog.")
    parser.add_argument("--prepare", action="store_true", help="Generate the official test catalog without model calls.")
    parser.add_argument("--run-dir", type=Path)
    parser.add_argument("--step-limits", type=Path, help="The existing ScienceWorld dataset's max_steps.json.")
    parser.add_argument("--concurrency", type=int, default=CONCURRENCY)
    parser.add_argument("--model", choices=MODELS, help="Run one model. By default, run all four benchmark models.")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    if args.prepare:
        prepare_catalog(args.catalog_dir.resolve())
        return
    if args.run_dir is None or args.step_limits is None or not 1 <= args.concurrency <= MAX_CONCURRENCY:
        parser.error("Running requires --run-dir, --step-limits and valid --concurrency")
    key = os.environ.get("TONGJI_API_KEY")
    if not key:
        parser.error("Set TONGJI_API_KEY in the environment")
    asyncio.run(run_sciworld(args.run_dir.resolve(), args.catalog_dir.resolve(), args.step_limits.resolve(), key,
                             concurrency=args.concurrency, resume=args.resume, model=args.model))


if __name__ == "__main__":
    main()
