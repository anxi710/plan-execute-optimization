"""Opt-in smoke tests against local benchmark data and real simulators."""

import asyncio
import os
import unittest
from functools import partial
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from toolkit.envs.alfworld_env import AlfWorldEnv, alfworld_settings
from toolkit.envs.sciworld_env import SciWorldEnv, open_sciworld_backend, sciworld_settings
from toolkit.envs.webshop_env import WebShopEnv, open_webshop_backend, webshop_settings
from toolkit.rollout.runner import RolloutRunner
from toolkit.tasks.alfworld import AlfWorldRolloutPool
from toolkit.tasks.sciworld import SciWorldTask
from toolkit.tasks.webshop import WebShopTask
from toolkit.utils.files import read_jsonl, write_jsonl


class LiveBackendTest(unittest.TestCase):
    @unittest.skipUnless(os.getenv("TOOLKIT_ALFWORLD_DATA") and os.getenv("TOOLKIT_ALFWORLD_GAMEFILES"),
                         "requires ALFWorld data and a matched gamefile map")
    def test_alfworld_reload_and_step_real_game(self):
        data = Path(os.environ["TOOLKIT_ALFWORLD_DATA"])
        row = next(row for row in read_jsonl(os.environ["TOOLKIT_ALFWORLD_GAMEFILES"]) if row.get("gamefile"))
        pool = AlfWorldRolloutPool(data, "dev", [row])
        with pool.open_slot() as slot:
            for _ in range(2):
                task = slot.load_task(row)
                env = AlfWorldEnv(task, plan_placement="query", **alfworld_settings())
                prompt, _ = env.reset()
                self.assertIn(row["task"], prompt)
                _, state = env.step("Action: look")
                self.assertEqual(state.steps, 1)
                self.assertTrue(state.action_trace[-1]["valid"])

    @unittest.skipUnless(os.getenv("TOOLKIT_SCIWORLD_DATA"), "requires local ScienceWorld evaluation rows")
    def test_sciworld_reset_and_step_using_bundled_jar(self):
        tasks, _ = SciWorldTask.load_tasks(os.environ["TOOLKIT_SCIWORLD_DATA"])
        task = next(task for task in tasks if task.sub_task_name.endswith("find-non-living-thing"))
        with open_sciworld_backend() as backend:
            env = SciWorldEnv(task, backend, plan_placement="query", **sciworld_settings())
            prompt, _ = env.reset()
            self.assertIn("Observation: ", prompt)
            _, state = env.step("Action: look around")
            self.assertEqual(state.steps, 1)
            self.assertTrue(state.action_trace[-1]["valid"])

    @unittest.skipUnless(os.getenv("TOOLKIT_WEBSHOP_SMOKE"),
                         "requires the prepared WebShop 1,000-product catalog and index")
    def test_webshop_repeats_native_search_and_purchase(self):
        # Pin the task text independently of reset so a wrong goal index fails the smoke test.
        goal = ("Instruction: Find me dual band streaming media players with quad core, "
                "and price lower than 340.00 dollars")
        with TemporaryDirectory() as directory:
            write_jsonl(Path(directory) / "webshop_test_tasks.jsonl", [
                {"id": "decorative-pillows", "session": 0,
                 "task": 'Instruction: Find me double sided, machine washable decorative pillows with '
                         'printing technology with size: 28" x 28", and price lower than 50.00 dollars'},
                {"id": "streaming-player", "session": 3, "task": goal},
            ])
            tasks, count = WebShopTask.load_tasks(directory, task_id="streaming-player")
            self.assertEqual(count, 1)
            task, = tasks
        self.assertEqual(task.task_id, "streaming-player")

        actions = ("search[dual band quad core streaming media player]", "click[b09lskqf8c]", "click[buy now]")
        with open_webshop_backend() as backend:
            environment_factory = partial(WebShopEnv, env=backend, **webshop_settings())
            episodes = []
            for _ in range(2):
                agent = SimpleNamespace(async_call=AsyncMock(side_effect=[f"Action: {action}" for action in actions]))
                runner = RolloutRunner(lambda _: task, agent, environment_factory, plan_placement="query")
                state = asyncio.run(runner.run({"id": task.task_id}, task.plan, Mock()))
                self.assertTrue(state.finished, state.error)
                self.assertTrue(state.success)
                self.assertEqual(state.terminate_reason, "success")
                self.assertEqual(state.reward, 1.0)
                self.assertEqual(state.steps, len(actions))
                self.assertEqual([step["action"] for step in state.action_trace], list(actions))
                self.assertTrue(all(step["valid"] for step in state.action_trace), state.action_trace)
                prompt = state.history[0]["content"]
                self.assertIn(goal, prompt)
                self.assertIn("Available actions: search[keywords]", prompt)
                episodes.append(state.to_dict())
            self.assertEqual(*episodes)
