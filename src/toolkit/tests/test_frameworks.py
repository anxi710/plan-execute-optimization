import unittest
from unittest.mock import AsyncMock

from toolkit.envs.base import ActionResult, BaseEnv
from toolkit.frameworks import FRAMEWORK_MODES, FRAMEWORK_PROTOCOL, run_framework


class Household(BaseEnv):
    """A public action path and a private result that can disagree with the model."""

    def __init__(self):
        observation = "Room with a box and a shelf. Your task is to put the object on the shelf."
        self.task = type("Task", (), {"observation": observation})()
        super().__init__(observation=observation,
                         instruction="Think as needed. Choose one Action.", max_steps=12)
        self.resets = 0
        self.actions = []
        self.holding = False

    def reset(self):
        self.resets += 1
        self.holding = False
        return super().reset()

    def execute_action(self, action):
        self.actions.append(action)
        if action == "inspect box":
            return ActionResult("You see an object in the box.", 0.8321, True)
        if action == "take object":
            self.holding = True
            return ActionResult("You take the object.", 0.8321, True)
        return ActionResult("The simulator ended the episode.", 1.0 if self.holding else 0.5,
                            True, done=True, success=self.holding)


def reply(text, index=1):
    return {"text": text, "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            "model": "test-stub", "id": f"test-{index}", "finish_reason": "stop", "seconds": 0.01}


def events(record, event_type, **fields):
    return [event for event in record["events"] if event["type"] == event_type
            and all(event.get(key) == value for key, value in fields.items())]


class FrameworkEntryTests(unittest.IsolatedAsyncioTestCase):
    async def trial(self, **overrides):
        options = dict(mode="eo", env=Household(), planner=None,
                       executor=AsyncMock(return_value=reply("Action: finish")),
                       goal="Put the object on the shelf.", workspace_id="entry-test",
                       executor_limit=2, save=lambda _: None)
        options.update(overrides)
        return await run_framework(**options)

    async def test_current_protocol_and_six_modes_are_explicit(self):
        self.assertEqual(FRAMEWORK_PROTOCOL, "two-phase-v3")
        self.assertEqual(FRAMEWORK_MODES, ("eo", "pe-s", "pe-d-f", "pe-d-s", "pc-s", "pc-f"))
        record = await self.trial()
        self.assertEqual(record["protocol_version"], FRAMEWORK_PROTOCOL)
        self.assertEqual(record["outcome"]["reason"], "task_finish")

    async def test_unsupported_modes_and_protocols_stop_before_reset(self):
        for options in ({"mode": "pe-d"}, {"mode": "pc"}, {"protocol_version": None},
                        {"protocol_version": "two-phase-v2"}):
            env = Household()
            with self.subTest(options=options), self.assertRaises(ValueError):
                await self.trial(env=env, **options)
            self.assertEqual(env.resets, 0)

    async def test_environment_and_dispatch_limits_are_checked(self):
        for limit in (0, True, 13):
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                await self.trial(executor_limit=limit)

    async def test_fixed_context_exhaustion_sends_no_request(self):
        executor = AsyncMock(return_value=reply("Action: finish"))
        record = await self.trial(executor=executor, context_window={"max_input_tokens": 1})
        executor.assert_not_awaited()
        self.assertIsNone(record["outcome"]["reward"])
        self.assertEqual(events(record, "runtime_error")[0]["error"], "ContextWindowExceeded")
        failure = events(record, "context_window_error")[0]
        self.assertEqual(failure["context_window"]["max_input_tokens"], 1)
        self.assertFalse(failure["dispatched"])
