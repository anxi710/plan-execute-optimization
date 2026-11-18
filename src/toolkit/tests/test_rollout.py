import asyncio
import json
import tempfile
import unittest
from functools import partial
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from toolkit.envs.alfworld_env import AlfWorldEnv, alfworld_settings
from toolkit.rollout.log import JsonRolloutLog
from toolkit.rollout.runner import RolloutRunner


class RolloutIntegrationTest(unittest.IsolatedAsyncioTestCase):
    async def test_cancelled_rollout_saves_latest_state_and_propagates(self):
        agent = SimpleNamespace(async_call=AsyncMock(side_effect=asyncio.CancelledError))
        task = SimpleNamespace(observation="initial observation", env=None)
        runner = RolloutRunner(
            lambda _: task,
            agent, partial(AlfWorldEnv, **alfworld_settings()), plan_placement="query",
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cancelled.json"
            log = JsonRolloutLog(path, {"plan_id": "cancelled"}, usage_metadata=dict)
            with self.assertRaises(asyncio.CancelledError):
                await runner.run({}, "Search the table", log.save)
            prompt, final = json.loads(path.read_text())
        self.assertIn("Search the table", prompt["content"])
        self.assertEqual(final["plan_id"], "cancelled")
        self.assertEqual(final["terminate_reason"], "executor_cancelled")
        self.assertTrue(final["incomplete"])
        self.assertFalse(final["finished"])
