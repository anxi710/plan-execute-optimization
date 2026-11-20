import unittest
from unittest.mock import patch

from toolkit.agents.base import BaseModel
from toolkit.prompts import PlanInjection


class LocalModel(BaseModel):
    def _complete(self, messages, *, prefix=None):
        return prefix or messages[-1]["content"]

    def close(self):
        self.closed = True


class ModelDispatchTest(unittest.IsolatedAsyncioTestCase):
    async def test_sync_backend_supports_both_plan_dispatch_paths(self):
        async def run_in_thread(function, *args, **kwargs):
            return function(*args, **kwargs)

        model = LocalModel()
        messages = [{"role": "user", "content": "Task"}]
        injection = PlanInjection("thought", "Find the cup")
        expected = "This plan may be helpful to complete the task:\nFind the cup\nThought: "
        self.assertEqual(injection.thought_prefix, expected)
        self.assertEqual(model.continue_assistant(messages, injection.thought_prefix), expected)
        with patch("toolkit.agents.base.asyncio.to_thread", side_effect=run_in_thread) as dispatch:
            self.assertEqual(await model.async_continue_assistant(messages, injection.thought_prefix), expected)
            self.assertEqual(await model.async_call(messages), "Task")
            await model.aclose()
            self.assertEqual(dispatch.await_count, 3)
        self.assertEqual(model.usage_metadata()["requests"], 3)
        self.assertTrue(model.closed)
