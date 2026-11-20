import asyncio
import tempfile
import unittest
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from toolkit.envs.base import ActionResult, BaseEnv
from toolkit.rollout.batch import RolloutJob, archive_incomplete_rollout, load_saved_rollout, run_rollouts, sample_jobs
from toolkit.rollout.state import State
from toolkit.utils.files import write_json
from toolkit.utils.runfiles import exclusive_run_lock, save_settings


class RunFilesTest(unittest.TestCase):
    def test_run_lock_and_settings_prevent_conflicting_resume(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            lock_path = root / ".lock"
            settings = root / "run.meta"
            with exclusive_run_lock(lock_path):
                save_settings(settings, {"model": "baseline"})
                save_settings(settings, {"model": "baseline"})
                with self.assertRaisesRegex(ValueError, "Resume settings differ"):
                    save_settings(settings, {"model": "different"})
                with self.assertRaises(BlockingIOError), exclusive_run_lock(lock_path):
                    self.fail("A second caller acquired the run lock")
            with exclusive_run_lock(lock_path):
                save_settings(settings, {"model": "baseline"})

    def test_resume_checks_seed_and_archives_only_incomplete_records(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample_0.json"
            job = RolloutJob({"id": 4}, "Test plan", path, {"sample_id": 0}, seed=3)
            state = State(finished=True, success=True)
            rows = state.to_dict()
            rows[-1].update(job.identity)
            write_json(path, rows)
            self.assertTrue(load_saved_rollout(job).success)
            with self.assertRaisesRegex(ValueError, "Expected an incomplete rollout"):
                archive_incomplete_rollout(job)
            different_seed = RolloutJob(job.row, job.plan, path, job.metadata, seed=5)
            with self.assertRaisesRegex(ValueError, "does not match"):
                load_saved_rollout(different_seed)

            rows[-1].update(finished=False, success=False, incomplete=True)
            write_json(path, rows)
            before = path.read_bytes()
            archived = archive_incomplete_rollout(job)
            self.assertEqual(archived.read_bytes(), before)
            self.assertIsNone(load_saved_rollout(job))


class RolloutBatchTest(unittest.IsolatedAsyncioTestCase):
    async def test_samples_are_bounded_ordered_and_release_workers(self):
        opened = []
        closed = []
        completed = []
        reported = []
        release_first = asyncio.Event()
        active = maximum = 0

        @asynccontextmanager
        async def open_worker():
            worker_id = len(opened)
            opened.append(worker_id)

            async def run_one(job):
                nonlocal active, maximum
                active += 1
                maximum = max(maximum, active)
                if job == 0:
                    await release_first.wait()
                else:
                    release_first.set()
                completed.append(job)
                active -= 1
                return None if job == 1 else 2 * job

            try:
                yield run_one
            finally:
                closed.append(worker_id)

        results = await sample_jobs(range(3), open_worker=open_worker, concurrency=2,
                                    on_result=lambda job, result: reported.append((job, result)))
        self.assertEqual(results, [0, None, 4])
        self.assertEqual(completed[0], 1)
        self.assertEqual(maximum, 2)
        self.assertEqual(sorted(closed), opened)
        self.assertEqual(reported, [(job, results[job]) for job in completed])

    async def test_sample_failure_cancels_peers_and_releases_workers(self):
        entered = []
        closed = []
        peer_started = asyncio.Event()

        @asynccontextmanager
        async def open_worker():
            worker_id = len(entered)
            entered.append(worker_id)

            async def run_one(job):
                if job == 0:
                    await peer_started.wait()
                    raise ValueError("sample failed")
                peer_started.set()
                await asyncio.Future()

            try:
                yield run_one
            finally:
                closed.append(worker_id)

        with self.assertRaises(ExceptionGroup) as failure:
            await sample_jobs(range(2), open_worker=open_worker, concurrency=2)
        self.assertEqual(str(failure.exception.exceptions[0]), "sample failed")
        self.assertEqual(sorted(closed), entered)

    async def test_cancelled_sample_cannot_return_partial_results(self):
        closed = []

        @asynccontextmanager
        async def open_worker():
            async def run_one(job):
                raise asyncio.CancelledError

            try:
                yield run_one
            finally:
                closed.append(True)

        with self.assertRaises(asyncio.CancelledError):
            await sample_jobs([0], open_worker=open_worker, concurrency=1)
        self.assertEqual(closed, [True])

    async def test_seed_changes_replace_the_agent_in_the_same_slot(self):
        agents = []
        resets = []

        def create_agent(seed):
            agent = SimpleNamespace(
                seed=seed, async_call=AsyncMock(return_value="Action: finish"), aclose=AsyncMock(),
                reset_usage=lambda: None, usage_metadata=lambda: {},
            )
            agents.append(agent)
            return agent

        @contextmanager
        def open_slot():
            def load_task(row):
                resets.append(row["id"])
                return SimpleNamespace()
            yield SimpleNamespace(load_task=load_task)

        class Environment(BaseEnv):
            def __init__(self, task):
                super().__init__(observation="start", instruction="Choose an action.")

            def execute_action(self, action):
                return ActionResult("done", reward=1, valid=True, done=True, success=True)

        with tempfile.TemporaryDirectory() as directory:
            jobs = [
                RolloutJob({"id": 9}, "plan", Path(directory) / f"{sample}.json",
                           {"sample_id": sample}, seed=seed)
                for sample, seed in enumerate((7, 7, 21))
            ]
            results = await run_rollouts(
                jobs, open_slot=open_slot, create_agent=create_agent, environment_factory=Environment,
                plan_placement="query", concurrency=1,
            )
            self.assertEqual([load_saved_rollout(job).success for job in jobs], [True, True, True])
        self.assertEqual([state.finished for state in results], [True, True, True])
        self.assertEqual(resets, [9, 9, 9])
        self.assertEqual([agent.seed for agent in agents], [7, 21])
        self.assertEqual([agent.async_call.await_count for agent in agents], [2, 1])
        for agent in agents:
            agent.aclose.assert_awaited_once()
