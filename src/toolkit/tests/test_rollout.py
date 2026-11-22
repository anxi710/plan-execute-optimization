import asyncio
import json
import tempfile
import unittest
from functools import partial
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from toolkit.envs.alfworld_env import AlfWorldEnv, alfworld_settings
from toolkit.envs.base import ActionResult, BaseEnv
from toolkit.prompts import PLAN_HINT, PlanInjection
from toolkit.rollout.log import JsonRolloutLog
from toolkit.rollout.runner import RolloutRunner
from toolkit.rollout.session import RolloutSession


class LocalEnvironment(BaseEnv):
    def __init__(self):
        super().__init__(observation="Find the object.", instruction="Choose an action.", max_steps=3)
        self.resets = 0

    def reset(self):
        self.resets += 1
        return super().reset()

    def execute_action(self, action):
        return ActionResult(f"Result of {action}", 0.5, True, done=action == "finish", success=action == "finish")


class RolloutIntegrationTest(unittest.IsolatedAsyncioTestCase):
    async def test_fixed_plan_placements_preserve_executor_inputs(self):
        plan = "Inspect the box, then finish."
        for placement in ("query", "observation", "thought"):
            with self.subTest(placement=placement):
                env = LocalEnvironment()
                agent = SimpleNamespace(
                    async_call=AsyncMock(side_effect=["Action: inspect", "Action: finish"]),
                    async_continue_assistant=AsyncMock(side_effect=["Action: inspect", "Action: finish"]),
                )
                runner = RolloutRunner(lambda _: object(), agent, lambda _: env, plan_placement=placement)
                state = await runner.run({}, plan, lambda *_args, **_kwargs: None)
                self.assertTrue(state.success)
                self.assertEqual(env.resets, 1)
                self.assertFalse(hasattr(env, "plan_injection"))
                complete = agent.async_continue_assistant if placement == "thought" else agent.async_call
                other = agent.async_call if placement == "thought" else agent.async_continue_assistant
                self.assertEqual(complete.await_count, 2)
                other.assert_not_awaited()
                initial = "Choose an action.\n\nFind the object."
                if placement == "query":
                    initial += f"\n\n{PLAN_HINT}\n{plan}"
                self.assertEqual(complete.await_args_list[0].args[0], [{"role": "user", "content": initial}])
                feedback = "Observation: Result of inspect"
                if placement == "observation":
                    feedback += f"\n\n{PLAN_HINT}\n{plan}"
                self.assertEqual(complete.await_args_list[1].args[0][-1]["content"], feedback)
                if placement == "thought":
                    self.assertEqual(complete.await_args_list[0].args[1], PlanInjection(placement, plan).thought_prefix)

    async def test_session_pauses_and_resumes_an_async_environment(self):
        class AsyncEnvironment(LocalEnvironment):
            async def step(self, reply):
                await asyncio.sleep(0)
                return super().step(reply)

        env = AsyncEnvironment()
        executor = AsyncMock(side_effect=[{"text": "Action: inspect"}, {"text": "Action: finish"}])
        session = RolloutSession(env, {"executor": executor})
        session.reset()
        self.assertEqual(await session.run(after_step=lambda event: "pause"), "pause")
        self.assertFalse(session.state.finished)
        self.assertEqual(session.state.steps, 1)
        session.state.history.append({"role": "user", "content": "Continue with the next stage."})
        await session.run()
        self.assertTrue(session.state.success)
        self.assertEqual(env.resets, 1)
        self.assertEqual(session.state.steps, 2)
        self.assertEqual(session.attempts, {"executor": 2})
        self.assertEqual(executor.await_args_list[1].args[0][-1]["content"], "Continue with the next stage.")
        self.assertEqual([event["type"] for event in session.log.events], ["model_call", "tool_event"] * 2)
        self.assertEqual([event["event_id"] for event in session.log.events], [1, 2, 3, 4])

    async def test_cancelled_rollout_saves_latest_state_and_propagates(self):
        agent = SimpleNamespace(async_call=AsyncMock(side_effect=asyncio.CancelledError))
        task = SimpleNamespace(observation="initial observation", env=None, admissible_commands=["look"])
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

    async def test_tool_protocol_turn_reuses_a_tool_aware_response_and_records_dispatch_failure(self):
        class FailingEnvironment(LocalEnvironment):
            def execute_action(self, action):
                def fail(_):
                    raise TimeoutError

                return self.dispatch(fail, action)

        executor = AsyncMock(return_value={"text": "Action: inspect"})
        session = RolloutSession(FailingEnvironment(), {"executor": executor}, count_dispatched=True)
        session.reset()
        messages = [{"role": "user", "content": "Fresh context"}]
        call = await session.call("executor", messages, tool_choice="none")
        with self.assertRaises(TimeoutError):
            await session.step(call=call)
        executor.assert_awaited_once_with(messages, tool_choice="none")
        event = session.log.events[-1]
        self.assertEqual(event["type"], "tool_error")
        self.assertTrue(event["dispatched"])
        self.assertTrue(event["result_unknown"])
