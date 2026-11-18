"""Schedule repeated rollouts and verify the identity of saved results."""

import asyncio
import json
import time
from dataclasses import dataclass
from pathlib import Path

from .log import JsonRolloutLog
from .runner import RolloutRunner
from .state import State


@dataclass(frozen=True)
class RolloutJob:
    row: dict
    plan: str | None
    path: Path
    metadata: dict
    seed: int | None = None

    @property
    def identity(self):
        return {**self.metadata, "task_id": str(self.row["id"]), "executor_seed": self.seed}


def load_saved_rollout(job):
    """Read a result, including an interrupted rollout, for this exact job."""
    if not job.path.exists():
        return None
    data = json.loads(job.path.read_text(encoding="utf-8"))
    if not isinstance(data, list) or not data or not isinstance(data[-1], dict):
        raise ValueError(f"Invalid rollout record: {job.path}")
    final = data[-1]
    if any(key not in final or type(final[key]) is not type(value) or final[key] != value
           for key, value in job.identity.items()):
        raise ValueError(f"Saved rollout does not match the queued sample: {job.path}")
    state = State.load_json(data)
    if type(state.finished) is not bool or type(state.incomplete) is not bool:
        raise ValueError(f"Invalid rollout status: {job.path}")
    return state


def archive_incomplete_rollout(job):
    """Keep an interrupted artifact before a caller-approved retry."""
    state = load_saved_rollout(job)
    if state is None or state.finished and not state.incomplete:
        raise ValueError(f"Expected an incomplete rollout: {job.path}")
    history = job.path.parent / "interrupted"
    history.mkdir(exist_ok=True)
    return job.path.rename(history / f"{job.path.stem}_{time.time_ns()}.json")


async def run_rollouts(jobs, *, open_slot, create_agent, environment_factory, plan_placement,
                       concurrency, on_result=None):
    """Load each task afresh while each worker owns an environment slot and model.

    Callers use their run lock when separate processes share an output directory.
    """
    if type(concurrency) is not int or concurrency < 1:
        raise ValueError("Rollout concurrency must be a positive integer")
    jobs = list(jobs)
    paths = {job.path.resolve() for job in jobs}
    if len(paths) != len(jobs):
        raise ValueError("Duplicate rollout output path")
    if existing := next((job.path for job in jobs if job.path.exists()), None):
        raise ValueError(f"Rollout output already exists: {existing}")
    pending = iter(enumerate(jobs))
    results = [None] * len(jobs)

    async def worker():
        with open_slot() as slot:
            agent = None
            seed = None
            try:
                for index, job in pending:
                    if agent is None or seed != job.seed:
                        if agent is not None:
                            previous, agent = agent, None
                            await previous.aclose()
                        seed = job.seed
                        agent = create_agent(seed)
                        runner = RolloutRunner(slot.load_task, agent, environment_factory,
                                               plan_placement=plan_placement)
                    agent.reset_usage()
                    log = JsonRolloutLog(job.path, job.identity, usage_metadata=agent.usage_metadata)
                    state = await runner.run(job.row, job.plan, log.save)
                    results[index] = state
                    if on_result is not None:
                        on_result(job, state)
            finally:
                if agent is not None:
                    await agent.aclose()

    async with asyncio.TaskGroup() as workers:
        for _ in range(min(concurrency, len(jobs))):
            workers.create_task(worker())
    if any(state is None for state in results):
        raise asyncio.CancelledError
    return results
