"""Run the four matched frameworks on the complete ALFWorld test split."""

import argparse
import asyncio
import math
import os
import random
import re
from collections import Counter
from contextlib import asynccontextmanager
from functools import partial
from pathlib import Path
from time import monotonic
from uuid import uuid4

from run import (
    CONSTRAINTS, EXECUTOR_LIMIT, MODEL_SETTINGS, PLANNER_LIMITS, RETURN_EVERY,
    run_matched_trial, runtime_versions, save_trial, source_version, task_goal, utc_now,
)
from toolkit.agents.openai_agent import AsyncChatClient
from toolkit.rollout.batch import sample_jobs
from toolkit.tasks.alfworld import AlfWorldRolloutPool, load_alfworld_rows
from toolkit.tasks.rows import task_rows_by_id
from toolkit.utils.files import read_json, write_json, write_text_atomic
from toolkit.utils.runfiles import exclusive_run_lock


MODELS = ("DeepSeek-V4.1-Flash", "MiniMax-M3.1-Flash", "GLM-5.3-Flash", "Qwen3.8-27B")
SPLIT = "test"
ALFWORLD_TEST_COUNT = 134
CONCURRENCY = 4
MAX_CONCURRENCY = 24
REQUESTS_PER_MINUTE = 100
RATE_FILE_ENV = "PLANNER_BENCHMARK_RATE_FILE"
UNPACED_ENV = "PLANNER_BENCHMARK_UNPACED"
MAX_TRIAL_ATTEMPTS = 2
TRANSIENT_ERRORS = {"RateLimitError", "APITimeoutError", "APIConnectionError", "InternalServerError"}
ORDER_SEED = 417
MAX_INPUT_BYTES = 32_000
MAX_OUTPUT = {"planner": 1536, "executor": 768}
SCHEMA_VERSION = 2
PURPOSE = "paired_model_framework_benchmark"


class PacedClient:
    """Space dispatches locally or across processes sharing a rate file."""

    def __init__(self, client):
        self.client = client
        self.lock = asyncio.Lock()
        self.next_request = 0.0
        rate_file = os.getenv(RATE_FILE_ENV)
        self.rate_file = Path(rate_file).expanduser().resolve() if rate_file else None
        if self.rate_file is not None:
            self.boot_id = Path("/proc/sys/kernel/random/boot_id").read_text(encoding="ascii").strip()
            self.rate_file.parent.mkdir(parents=True, exist_ok=True)
            self.rate_lock = self.rate_file.with_name(self.rate_file.name + ".lock")

    def _reserve_shared(self, interval):
        import fcntl

        # Hold a stable lock inode while replacing the rate state atomically.
        with self.rate_lock.open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return monotonic() + 0.01
            try:
                boot_id, timestamp = self.rate_file.read_text(encoding="ascii").split()
            except FileNotFoundError:
                boot_id = None
            now = monotonic()
            if boot_id == self.boot_id:
                deadline = float(timestamp)
                if not math.isfinite(deadline):
                    raise ValueError("Invalid benchmark rate reservation timestamp")
                if deadline > now:
                    return deadline
            write_text_atomic(self.rate_file, f"{self.boot_id} {now + interval}\n")
            return None

    async def complete(self, **kwargs):
        interval = 60 / REQUESTS_PER_MINUTE
        async with self.lock:
            if self.rate_file is None:
                loop = asyncio.get_running_loop()
                delay = self.next_request - loop.time()
                if delay > 0:
                    await asyncio.sleep(delay)
                self.next_request = loop.time() + interval
            else:
                while (deadline := self._reserve_shared(interval)) is not None:
                    await asyncio.sleep(max(0, deadline - monotonic()))
        return await self.client.complete(**kwargs)


def trial_status(record):
    outcome = record.get("outcome")
    if outcome is None:
        return record.get("status", "interrupted")
    if (len(record["events"]) < 2
            or [event["type"] for event in record["events"][-2:]] != ["stop", "verifier"]
            or any(record["events"][-1].get(field) != outcome.get(field)
                   for field in ("reason", "reward", "success"))):
        raise ValueError("Terminal outcome is missing its matching stop and verifier")
    if outcome["reason"] == "runtime_error" and outcome["reward"] is None:
        return "unscored"
    score = outcome["reward"]
    if type(score) not in (int, float) or not math.isfinite(score) or type(outcome["success"]) is not bool:
        raise ValueError("Terminal outcome has no valid native score")
    return "complete"


def checkpoint_error(record, status):
    if status == "unscored":
        return next((event["error"] for event in reversed(record["events"]) if event["type"] == "runtime_error"), None)
    return record.get("error")


def scheduled_manifest(dataset, run_id, *, model_order=None):
    model_order = MODELS if model_order is None else tuple(model_order)
    if not model_order or len(set(model_order)) != len(model_order) or set(model_order) - set(MODELS):
        raise ValueError("Select distinct benchmark models from the supported list")
    trace_suffix = ".json.gz" if dataset.get("compress_traces") else ".json"
    models = {
        model: {role: {**config, "model": model, "max_tokens": MAX_OUTPUT[role]}
                for role, config in MODEL_SETTINGS.items()}
        for model in model_order
    }
    return_every = dataset.get("return_every", RETURN_EVERY)
    if type(return_every) is not int or return_every < 1:
        raise ValueError("Expected a positive return interval")
    input_limit = dataset.get("max_input_bytes", MAX_INPUT_BYTES)
    if type(input_limit) is not int or input_limit < 1:
        raise ValueError("Expected a positive model input byte limit")
    budgets = {}
    for task in dataset["tasks"]:
        task_id = task["task_id"]
        limit = task.get("executor_limit", EXECUTOR_LIMIT)
        if (not re.fullmatch(r"[A-Za-z0-9_-]+", str(task_id)) or str(task_id) in budgets
                or type(limit) is not int or limit < 1):
            raise ValueError(f"Invalid task identity or Executor limit: {task_id}")
        dynamic = (limit + return_every - 1) // return_every
        budgets[str(task_id)] = {"executor_limit": limit,
                                 "planner_limits": {**PLANNER_LIMITS, "pe-d": dynamic, "pc": dynamic}}
    trials = {}
    for model in model_order:
        index = MODELS.index(model) + 1
        for task in dataset["tasks"]:
            task_id = task["task_id"]
            for mode in PLANNER_LIMITS:
                trial_id = f"m{index}-t{task_id}-{mode}"
                trials[trial_id] = {
                    "trial_id": trial_id, "model": model, "task_id": task_id, "mode": mode,
                    "workspace_id": f"{run_id}/{trial_id}/attempt-1", "file": f"trials/{trial_id}{trace_suffix}",
                    "status": "queued", "started_at": None, "finished_at": None, "archived_attempts": [],
                    "executor_limit": budgets[str(task_id)]["executor_limit"],
                    "planner_limit": budgets[str(task_id)]["planner_limits"][mode], "return_every": return_every,
                }
    order = list(trials)
    random.Random(ORDER_SEED).shuffle(order)
    executor_calls = sum(trial["executor_limit"] for trial in trials.values())
    planner_calls = sum(trial["planner_limit"] for trial in trials.values())
    executor_limits = {budget["executor_limit"] for budget in budgets.values()}
    uniform = len(executor_limits) == 1
    return {
        "schema_version": SCHEMA_VERSION, "run_id": run_id, "purpose": PURPOSE,
        "status": "running", "started_at": utc_now(), "finished_at": None, "invocations": [],
        "models": models, "model_order": list(model_order), "benchmark": dataset,
        "budget": {
            "executor_limit": next(iter(executor_limits)) if uniform else None,
            "planner_limits": next(iter(budgets.values()))["planner_limits"] if uniform else None,
            "budgets_by_task": budgets,
            "return_every": return_every, "max_requests": executor_calls + planner_calls,
            "max_output_tokens": executor_calls * MAX_OUTPUT["executor"] + planner_calls * MAX_OUTPUT["planner"],
            "max_input_bytes_per_request": input_limit, "automatic_retries": 0,
            "dispatch_rate_per_minute": REQUESTS_PER_MINUTE, "max_attempts_per_trial": MAX_TRIAL_ATTEMPTS,
        },
        "order_seed": ORDER_SEED, "run_order": order, "trials": trials,
        "records": {trial_id: trial["file"] for trial_id, trial in trials.items()},
        "source": source_version(), "runtime": runtime_versions(dataset.get("runtime_packages")),
    }


def restore_checkpoint(run_dir, run_id, trial):
    path = run_dir / trial["file"]
    archive_dir = run_dir / "attempts" / trial["trial_id"]
    trace_suffix = "".join(path.suffixes)
    archives = sorted(archive_dir.glob(f"attempt-*{trace_suffix}"))
    trial["archived_attempts"] = [str(path.relative_to(run_dir)) for path in archives]
    if not path.exists():
        trial.update(status="queued", started_at=None, finished_at=None)
        return
    record = read_json(path)
    if (record["run_id"] != run_id or any(record[key] != trial[key] for key in ("trial_id", "mode", "task_id", "model"))
            or record["attempt"] != len(archives) + 1):
        raise ValueError(f"Saved trial identity differs at {path}")
    trial.update(status=trial_status(record), workspace_id=record["workspace_id"],
                 started_at=record["started_at"], finished_at=record["finished_at"])
    if error := checkpoint_error(record, trial["status"]):
        trial["error"] = error


def can_retry_trial(run_dir, trial):
    unfinished = trial["status"] in ("queued", "running", "interrupted")
    if trial["status"] == "complete" or not (unfinished or trial.get("error") in TRANSIENT_ERRORS):
        return False
    paths = [run_dir / path for path in trial["archived_attempts"]]
    current = run_dir / trial["file"]
    if current.is_file():
        paths.append(current)
    attempts = len(paths)
    for path in paths:
        if attempts < MAX_TRIAL_ATTEMPTS:
            break
        record = read_json(path)
        if record["status"] == "error" and record.get("error") == "OSError" and record["events"] == []:
            attempts -= 1
    return attempts < MAX_TRIAL_ATTEMPTS


async def run_matrix(run_dir, rows, dataset, api_key, *, run_one, concurrency=CONCURRENCY, resume=False,
                     model_order=None):
    if not 1 <= concurrency <= MAX_CONCURRENCY:
        raise ValueError(f"Concurrency must be between 1 and {MAX_CONCURRENCY}")
    if not rows or set(rows) != {task["task_id"] for task in dataset["tasks"]}:
        raise ValueError("The scheduled tasks differ from the prepared dataset rows")
    if not resume:
        run_dir.mkdir(parents=True, exist_ok=False)
    manifest_path = run_dir / "manifest.json"
    if resume and not manifest_path.is_file():
        raise ValueError("A saved manifest is required for --resume")
    with exclusive_run_lock(run_dir / ".run.lock"):
        manifest = read_json(manifest_path) if resume else None
        run_id = manifest["run_id"] if resume else uuid4().hex
        expected = scheduled_manifest(dataset, run_id, model_order=model_order)
        if resume:
            frozen = ("schema_version", "purpose", "models", "model_order", "benchmark", "budget", "source", "runtime",
                      "run_order", "records")
            if any(manifest.get(key) != expected[key] for key in frozen):
                raise ValueError("Saved schedule or runtime differs from the requested resume")
            for trial in expected["trials"].values():
                restore_checkpoint(run_dir, run_id, trial)
            manifest["trials"] = expected["trials"]
        else:
            manifest = expected
        await run_pending(run_dir, manifest, rows, api_key, run_one, concurrency, resume)


async def run_pending(run_dir, manifest, rows, api_key, run_one, concurrency, resume):
    manifest_path = run_dir / "manifest.json"
    trials = manifest["trials"]
    pending = [trial_id for trial_id in manifest["run_order"] if can_retry_trial(run_dir, trials[trial_id])]
    invocation = {"started_at": utc_now(), "finished_at": None, "resume": resume, "concurrency": concurrency,
                  "pending_trials": len(pending)}
    unpaced = os.getenv(UNPACED_ENV) == "1"
    if unpaced:
        invocation.update(dispatch_rate_scope="unpaced", dispatch_rate_per_minute=None)
    elif os.getenv(RATE_FILE_ENV):
        invocation["dispatch_rate_scope"] = "host_shared"
    manifest["invocations"].append(invocation)
    manifest.setdefault("concurrency", concurrency)
    manifest.pop("interrupted_by", None)
    manifest.update(status="running", finished_at=None)
    write_json(manifest_path, manifest)
    async def one_trial(client, trial):
        trial_id, model = trial["trial_id"], trial["model"]
        path = run_dir / trial["file"]
        attempt = len(trial["archived_attempts"]) + 1
        if path.exists():
            trace_suffix = "".join(path.suffixes)
            archive = run_dir / "attempts" / trial_id / f"attempt-{attempt:06d}{trace_suffix}"
            archive.parent.mkdir(parents=True, exist_ok=True)
            if archive.exists():
                raise FileExistsError(archive)
            path.rename(archive)
            trial["archived_attempts"].append(str(archive.relative_to(run_dir)))
            attempt += 1
        trial.pop("error", None)
        trial.update(status="running", started_at=utc_now(), finished_at=None,
                     workspace_id=f"{manifest['run_id']}/{trial_id}/attempt-{attempt}")
        identity = {"run_id": manifest["run_id"], "task_id": trial["task_id"], "trial_id": trial_id,
                    "arm": trial["mode"], "model": model, "attempt": attempt}

        def checkpoint(record):
            status = trial_status(record) if record.get("outcome") is not None else trial["status"]
            finished_at = record["events"][-1]["timestamp"] if record.get("outcome") else trial["finished_at"]
            save_trial(path, identity, {**record, "status": status, "started_at": trial["started_at"],
                                        "finished_at": finished_at})

        checkpoint({"mode": trial["mode"], "workspace_id": trial["workspace_id"], "events": [], "outcome": None})
        try:
            record = await run_one(
                rows[trial["task_id"]], client, mode=trial["mode"], workspace_id=trial["workspace_id"],
                model_settings=manifest["models"][model],
                max_input_bytes=manifest["budget"]["max_input_bytes_per_request"], save=checkpoint,
                executor_limit=trial["executor_limit"], planner_limit=trial["planner_limit"],
                return_every=trial["return_every"],
            )
            trial.update(status=trial_status(record), finished_at=record["events"][-1]["timestamp"])
            if error := checkpoint_error(record, trial["status"]):
                trial["error"] = error
            print(f"{trial_id}: {record['outcome']['reason']}", flush=True)
        except asyncio.CancelledError:
            trial.update(status="interrupted", finished_at=utc_now())
            checkpoint(read_json(path))
            raise
        except Exception as error:
            trial.update(status="error", error=type(error).__name__, finished_at=utc_now())
            checkpoint({**read_json(path), "error": trial["error"]})
            print(f"{trial_id}: {trial['error']}", flush=True)

    transport = MODEL_SETTINGS["executor"]
    try:
        if pending:
            async with AsyncChatClient(base_url=transport["base_url"], api_key=api_key, timeout=transport["timeout"],
                                       max_retries=0, max_concurrency=concurrency) as transport_client:
                client = transport_client if unpaced else PacedClient(transport_client)

                @asynccontextmanager
                async def open_worker():
                    yield partial(one_trial, client)

                await sample_jobs([trials[trial_id] for trial_id in pending],
                                  open_worker=open_worker, concurrency=concurrency)
    except (Exception, asyncio.CancelledError, KeyboardInterrupt) as error:
        manifest.update(status="interrupted", interrupted_by=type(error).__name__)
        raise
    else:
        manifest["status"] = "complete"
    finally:
        manifest["finished_at"] = invocation["finished_at"] = utc_now()
        manifest["trial_counts"] = dict(Counter(trial["status"] for trial in trials.values()))
        write_json(manifest_path, manifest)


async def run_benchmark(run_dir, data_dir, gamefiles, api_key, *, concurrency=CONCURRENCY, resume=False):
    rows = task_rows_by_id(load_alfworld_rows(data_dir, SPLIT, gamefile_map_path=gamefiles))
    if len(rows) != ALFWORLD_TEST_COUNT or any(not row.get("gamefile") for row in rows.values()):
        raise ValueError(f"Expected all {ALFWORLD_TEST_COUNT} official test games with verified gamefile assignments")
    pool = AlfWorldRolloutPool(data_dir, SPLIT, rows.values())
    if set(pool.gamefiles.values()) != set(pool.source.game_files):
        raise ValueError("The assigned gamefiles differ from the complete official test pool")
    tasks = [
        {"task_id": task_id, "task": row["task"], "goal": task_goal(row), "gamefile": row["gamefile"],
         "family": Path(row["gamefile"]).parent.parent.name.split("-", 1)[0]}
        for task_id, row in rows.items()
    ]
    dataset = {"name": "ALFWorld", "data_version": "json_2.1.1", "split": SPLIT, "selection": "full_split",
               "canonical_task_file": str(data_dir / f"alfworld_{SPLIT}_tasks.jsonl"), "canonical_task_count": len(tasks),
               "tasks": tasks, "data_dir": str(data_dir), "gamefile_map": str(gamefiles), "constraints": CONSTRAINTS}
    # Verify each game and its public initial observation before contacting the model service.
    with pool.open_slot() as slot:
        for row in rows.values():
            slot.load_task(row)
    await run_matrix(run_dir, rows, dataset, api_key, run_one=partial(run_matched_trial, pool),
                     concurrency=concurrency, resume=resume)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True, type=Path, help="New output directory, or an existing run with --resume.")
    parser.add_argument("--data-dir", required=True, type=Path, help="Local ALFWorld dataset directory.")
    parser.add_argument("--gamefiles", required=True, type=Path, help="Verified complete ALFWorld test gamefile map.")
    parser.add_argument("--concurrency", type=int, default=CONCURRENCY, help=f"Simultaneous trials (1–{MAX_CONCURRENCY}).")
    parser.add_argument("--resume", action="store_true", help="Restart unfinished trials or transient API failures once.")
    args = parser.parse_args(argv)
    api_key = os.getenv("TONGJI_API_KEY")
    if not api_key:
        parser.error("Set TONGJI_API_KEY in the environment")
    if not 1 <= args.concurrency <= MAX_CONCURRENCY:
        parser.error(f"Choose --concurrency between 1 and {MAX_CONCURRENCY}")
    if args.run_dir.exists() != args.resume:
        parser.error("Use a new --run-dir for a fresh run or pass --resume for an existing run")
    try:
        asyncio.run(run_benchmark(args.run_dir.resolve(), args.data_dir.resolve(), args.gamefiles.resolve(), api_key,
                                  concurrency=args.concurrency, resume=args.resume))
    except KeyboardInterrupt:
        parser.exit(130, "Benchmark interrupted.\n")
    except Exception as error:
        parser.exit(1, f"Benchmark stopped ({type(error).__name__}). Check the output directory for saved evidence.\n")


if __name__ == "__main__":
    main()
