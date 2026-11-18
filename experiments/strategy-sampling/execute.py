"""Run three fixed-Executor ALFWorld rollouts for each queued plan."""

import argparse
import asyncio
import fcntl
import json
import os
import re
import sys
import time
from collections import Counter
from pathlib import Path


PLANNER_EVAL = Path(__file__).resolve().parents[2] / "src" / "planner-eval"
SAMPLES = 3
MAX_STEPS = 30
TOKEN_FIELDS = (
    "prompt_tokens", "completion_tokens", "total_tokens",
    "prompt_cache_hit_tokens", "prompt_cache_miss_tokens",
)


def load_queue(run_dir, data_dir):
    from plan_eval.plans import extract_plan, read_jsonl
    from tasks.base import load_task_rows

    rows = load_task_rows(
        data_dir, "alfworld", "dev", selection_path=run_dir / "tasks.jsonl",
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
            raise ValueError(f"Plan {plan_id} has no matching canonical dev task and gamefile")
        plan = extract_plan(item["plan"]) if isinstance(item["plan"], str) else ""
        if not plan:
            raise ValueError(f"Empty plan: {plan_id}")
        plans[plan_id] = {**row, "plan": plan}
    if not plans:
        raise ValueError("Execution queue is empty")
    return plans


def save_settings(path, settings):
    from plan_eval.plans import write_json

    if path.exists():
        if json.loads(path.read_text(encoding="utf-8")) != settings:
            raise ValueError(f"Resume settings differ at {path}")
    else:
        write_json(path, settings)


async def execute(jobs, data_dir, env_config, agent_config, concurrency):
    from agents import OpenAIAgent
    from plan_eval.execution import ExecutorRunIncomplete, _mark_incomplete, async_interactive_loop
    from plan_eval.plans import write_json
    from tasks.alfworld import AlfWorldRolloutPool
    from utils.datatypes import State

    class MeteredExecutor(OpenAIAgent):
        def reset_usage(self):
            self.requests = 0
            self.responses = 0
            self.usage_responses = 0
            self.tokens = Counter()
            self.response_models = set()

        async def async_call(self, messages):
            self.requests += 1
            return await super().async_call(messages)

        def _response_content(self, response):
            self.responses += 1
            usage = getattr(response, "usage", None)
            if usage is not None:
                self.usage_responses += 1
                for field in TOKEN_FIELDS:
                    count = getattr(usage, field, None)
                    if count is not None:
                        self.tokens[field] += count
            model = getattr(response, "model", None)
            if model:
                self.response_models.add(model)
            return super()._response_content(response)

    rows = {row["id"]: {**row, "plan": None} for _, row, _, _ in jobs}
    pool = AlfWorldRolloutPool(data_dir, "dev", rows.values())
    pending = iter(jobs)
    completed = 0
    interrupted = 0

    async def worker():
        nonlocal completed, interrupted
        with pool.open_slot() as slot:
            agent = MeteredExecutor(agent_config)
            try:
                for plan_id, row, sample_id, path in pending:
                    started = time.monotonic()
                    agent.reset_usage()
                    latest = State()

                    def save(state, provisional=False):
                        nonlocal latest
                        latest = state
                        data = state.to_dict()
                        data[-1].update(
                            plan_id=plan_id, task_id=str(row["id"]), sample_id=sample_id,
                            gamefile=row["gamefile"], executor_seed=None,
                            executor_requests=agent.requests, executor_responses=agent.responses,
                            executor_usage_responses=agent.usage_responses,
                            executor_usage=dict(agent.tokens),
                            executor_response_models=sorted(agent.response_models),
                            elapsed_seconds=round(time.monotonic() - started, 3),
                        )
                        if provisional:
                            data[-1]["incomplete"] = True
                        write_json(path, data)

                    try:
                        task = slot.load_task(row)
                        task.plan = row["plan"]
                        state = await async_interactive_loop(
                            task, agent, env_config, "query", lambda state: save(state, provisional=True)
                        )
                    except asyncio.CancelledError:
                        _mark_incomplete(latest, "cancelled", "CancelledError")
                        save(latest)
                        raise
                    except ExecutorRunIncomplete as error:
                        state = error.state
                    except Exception as error:
                        state = latest
                        _mark_incomplete(state, "environment_error", type(error).__name__)
                    save(state)
                    if state.finished and not state.incomplete:
                        completed += 1
                        print(f"{plan_id}/{sample_id} finished: success={state.success}, steps={state.steps}", flush=True)
                    else:
                        interrupted += 1
                        print(f"{plan_id}/{sample_id} interrupted: {state.error}", file=sys.stderr, flush=True)
            finally:
                await agent.aclose()

    async with asyncio.TaskGroup() as workers:
        for _ in range(min(concurrency, len(jobs))):
            workers.create_task(worker())
    return completed, interrupted


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--model", default="deepseek-flash")
    parser.add_argument("--concurrency", type=int, default=12)
    parser.add_argument("--limit", type=int, help="Run only the first N plans in the queue.")
    parser.add_argument("--retry-incomplete", action="store_true", help="Archive incomplete samples before restarting them.")
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive")
    if args.concurrency < 1:
        parser.error("--concurrency must be positive")

    sys.path.insert(0, str(PLANNER_EVAL))
    from plan_eval.settings import task_definition
    from utils.datatypes import State

    run_dir, data_dir = args.run_dir.resolve(), args.data_dir.resolve()
    plans = load_queue(run_dir, data_dir)
    env_config = task_definition("alfworld")
    for name in ("task_class", "filepath"):
        env_config.pop(name)
    for name in ("instruction_path", "icl_path"):
        env_config[name] = str(PLANNER_EVAL / env_config[name])
    env_config["max_steps"] = MAX_STEPS
    agent_config = {
        "model_name": args.model,
        "api_base": "https://api.deepseek.com",
        "temperature": 0.6,
        "max_completion_tokens": 256,
        "token_parameter": "max_tokens",
        "request_timeout": 60,
        "request_max_retries": 0,
        "deepseek_thinking": "disabled",
    }
    output = run_dir / "executions"
    output.mkdir(exist_ok=True)
    with (output / ".lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            parser.error("This run already has an active Executor process")
        save_settings(output / "run_settings.meta", {
            "executor": agent_config, "environment": env_config, "data_dir": str(data_dir),
            "split": "dev", "samples_per_plan": SAMPLES, "plan_placement": "query",
            "concurrency": args.concurrency,
        })
        pending = []
        archived = []
        complete = incomplete = 0
        for plan_id, row in list(plans.items())[:args.limit]:
            directory = output / plan_id
            save_settings(directory / "plan.meta", row)
            for sample_id in range(SAMPLES):
                path = directory / f"sample_{sample_id}.json"
                if path.exists():
                    data = json.loads(path.read_text(encoding="utf-8"))
                    final = data[-1]
                    if (final.get("plan_id"), final.get("task_id"), final.get("sample_id"), final.get("gamefile")) != (
                        plan_id, str(row["id"]), sample_id, row["gamefile"]
                    ):
                        raise ValueError(f"Saved rollout does not match the queued plan: {path}")
                    state = State.load_json(data)
                    if state.finished and not state.incomplete:
                        complete += 1
                        continue
                    if not args.retry_incomplete:
                        incomplete += 1
                        continue
                    archived.append(path)
                pending.append((plan_id, row, sample_id, path))
        if pending:
            key = os.environ.get("EXECUTOR_API_KEY")
            if not key or key == "EMPTY":
                parser.error("Export EXECUTOR_API_KEY before executing pending samples")
            for path in archived:
                history = path.parent / "interrupted"
                history.mkdir(exist_ok=True)
                path.rename(history / f"{path.stem}_{time.time_ns()}.json")
            completed_now, interrupted_now = asyncio.run(
                execute(pending, data_dir, env_config, {**agent_config, "api_key": key}, args.concurrency)
            )
            complete += completed_now
            incomplete += interrupted_now
        print(f"Completed rollouts: {complete}; interrupted rollouts: {incomplete}")
    return int(incomplete != 0)


if __name__ == "__main__":
    raise SystemExit(main())
