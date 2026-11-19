import asyncio
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock

from toolkit.envs.base import ActionResult, BaseEnv

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runner import run_trial


class Household(BaseEnv):
    """A public action path and a private result that can disagree with the model."""

    def __init__(self):
        observation = "Room with a box and a shelf. Your task is to put the object on the shelf."
        self.task = type("Task", (), {"observation": observation})()
        super().__init__(observation=observation, plan=None, plan_placement="query",
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


def decision(kind, index=1, evidence_refs=()):
    value = {"decision": kind, "evidence_refs": list(evidence_refs), "hypotheses": ["Object might be under the bed."],
             "remaining_work": ["Put the object on the shelf."] if kind != "finish" else []}
    if kind == "delegate":
        value.update(stage_objective=f"Complete stage {index}", soft_guidance="Try the bed if useful.")
    plan = f"<plan>Remaining route v{index}: find the object, then place it on the shelf.</plan>\n"
    return reply(f"{plan if kind != 'finish' else ''}<decision>{json.dumps(value)}</decision>", index)


def events(record, event_type, **fields):
    return [event for event in record["events"] if event["type"] == event_type
            and all(event.get(key) == value for key, value in fields.items())]


class FrameworkTests(unittest.IsolatedAsyncioTestCase):
    async def trial(self, mode, planner_replies, executor_replies, **limits):
        env = Household()
        planner = AsyncMock(side_effect=planner_replies)
        executor = AsyncMock(side_effect=executor_replies)
        snapshots = []
        record = await run_trial(
            mode=mode, env=env, planner=planner, executor=executor,
            goal="Put the object on the shelf.", constraints=["Use the household action interface."],
            workspace_id=f"test-{mode}", save=lambda value: snapshots.append(json.loads(json.dumps(value))),
            **{"executor_limit": 8, "planner_limit": 6, "return_every": 1, **limits},
        )
        self.assertEqual(snapshots[-1], record)
        self.assertEqual(env.resets, 1)
        return record, env, planner, executor

    async def test_control_boundaries_and_continuing_workspace(self):
        scripts = {
            "eo": [],
            "pe-s": [reply("<plan>Look under the bed before placing the object on the shelf.</plan>")],
            "pe-d": [decision("guide", index) for index in range(1, 4)],
            "pc": [*(decision("delegate", index) for index in range(1, 4)), decision("finish", 4)],
        }
        base_prompts = []
        for mode, planner_replies in scripts.items():
            with self.subTest(mode=mode):
                record, env, planner, executor = await self.trial(mode, planner_replies, [
                    reply("Thought: I can explore locally.\nAction: inspect box"),
                    reply("Action: take object"), reply("Action: put object on shelf"),
                ])
                self.assertEqual(planner.await_count, len(planner_replies))
                self.assertEqual(executor.await_count, 3)
                self.assertEqual(env.actions, ["inspect box", "take object", "put object on shelf"])
                self.assertTrue(record["outcome"]["success"])
                self.assertEqual({event["workspace_id"] for event in record["events"]}, {f"test-{mode}"})
                self.assertEqual([event["type"] for event in record["events"][-2:]], ["stop", "verifier"])
                model_events = events(record, "model_call")
                self.assertEqual(len(model_events), len(planner_replies) + 3)
                self.assertEqual(sum(e["response"]["usage"]["total_tokens"] for e in model_events),
                                 15 * len(model_events))
                self.assertNotIn("0.8321", json.dumps([e["messages"] for e in model_events]))
                execution_calls = events(record, "model_call", role="executor")
                base_prompts.append(execution_calls[0]["messages"][0])
                self.assertIn("You take the object", json.dumps(execution_calls[-1]["messages"]))
                requests = events(record, "execution_request")
                if mode in {"eo", "pe-s"}:
                    self.assertEqual(len(requests), 1)
                if mode in {"pe-d", "pc"}:
                    self.assertEqual(len(requests), 3)
                    self.assertEqual([e["plan_version"] for e in requests], [1, 2, 3])
                    self.assertTrue(events(record, "execution_feedback", return_reason="budget_pause"))
                    self.assertIn("You see an object", json.dumps(events(record, "model_call", role="planner")[1]["messages"]))
                    for item in events(record, "planner_decision"):
                        state = item["planner_state"]
                        self.assertIn("Object might be under the bed.", state["hypotheses"])
                        self.assertNotIn("Object might be under the bed.", json.dumps(state["observed_facts"]))
                if mode == "pc":
                    self.assertEqual(len({e["request_id"] for e in requests}), 3)
                    self.assertEqual([e["stage_objective"] for e in requests],
                                     ["Complete stage 1", "Complete stage 2", "Complete stage 3"])
                else:
                    self.assertEqual(len({e["request_id"] for e in requests}), 1)
                    self.assertTrue(all(e["stage_objective"] is None for e in requests))
                for request in requests:
                    self.assertEqual(request["goal"], record["goal"])
                    self.assertEqual(request["hard_constraints"], record["constraints"])
        self.assertTrue(all(prompt == base_prompts[0] for prompt in base_prompts))

    async def test_planner_claim_does_not_override_verifier(self):
        record, env, _, _ = await self.trial("pc", [decision("delegate"), decision("finish")], [
            reply("Thought: The object is already on the shelf.\nAction: finish"),
        ])
        self.assertEqual(env.actions, ["finish"])
        self.assertFalse(record["outcome"]["success"])
        self.assertEqual(record["outcome"]["reward"], 0.5)
        self.assertTrue(events(record, "execution_feedback", return_reason="task_finish"))
        self.assertEqual(events(record, "planner_decision")[-1]["decision"], "finish")
        self.assertNotIn('"reward"', json.dumps(events(record, "model_call", role="planner")[-1]["messages"]))

    async def test_invalid_action_spends_a_turn_and_api_failure_is_preserved(self):
        record, env, _, executor = await self.trial("eo", [], [
            reply("I hereby declare success without an Action line."),
            TimeoutError("never serialize exception credentials"),
        ])
        self.assertEqual(env.actions, [])
        self.assertEqual(executor.await_count, 2)
        self.assertIsNone(events(record, "tool_event")[0]["action"])
        self.assertFalse(events(record, "tool_event")[0]["dispatched"])
        self.assertEqual(record["outcome"]["reason"], "runtime_error")
        self.assertIsNone(record["outcome"]["success"])
        self.assertNotIn("never serialize exception credentials", json.dumps(record))
        self.assertEqual(events(record, "model_call")[-1]["error"], "TimeoutError")

    async def test_dynamic_protocol_errors_and_budget_do_not_trigger_replay(self):
        malformed, env, planner, executor = await self.trial("pc", [reply("Missing decision")], [])
        self.assertEqual(malformed["outcome"]["reason"], "protocol_error")
        self.assertEqual(env.actions, [])
        self.assertEqual(planner.await_count, 1)
        self.assertEqual(executor.await_count, 0)

        unknown_evidence, _, _, _ = await self.trial("pc", [decision("delegate", evidence_refs=[999])], [])
        self.assertEqual(unknown_evidence["outcome"]["reason"], "protocol_error")

        invalid_decision, _, _, _ = await self.trial("pc", [reply('<decision>{"decision":[]}</decision>')], [])
        self.assertEqual(invalid_decision["outcome"]["reason"], "protocol_error")

        missing_stage, _, planner, executor = await self.trial("pc", [reply(
            '<plan>Locate and place the object.</plan><decision>'
            '{"decision":"delegate","hypotheses":[],"remaining_work":[],"evidence_refs":[]}'
            '</decision>',
        )], [])
        self.assertTrue(events(missing_stage, "decision_error", error="missing_stage_objective"))
        self.assertEqual(executor.await_count, 0)
        self.assertIn('"stage_objective":"<next observable subgoal>"', planner.await_args.args[0][0]["content"])

        capped, env, planner, executor = await self.trial(
            "pe-d", [decision("guide")], [reply("Action: inspect box")], executor_limit=1,
        )
        self.assertEqual(capped["outcome"]["reason"], "executor_budget")
        self.assertEqual(env.actions, ["inspect box"])
        self.assertEqual(planner.await_count, 1)
        self.assertEqual(executor.await_count, 1)

    async def test_cancellation_keeps_the_started_attempt(self):
        snapshots = []
        awaiting_reply = asyncio.Event()

        async def executor(_):
            awaiting_reply.set()
            await asyncio.Future()

        trial = asyncio.create_task(run_trial(
            mode="eo", env=Household(), planner=None, executor=executor,
            goal="Put the object on the shelf.", constraints=[], workspace_id="test-cancel",
            save=lambda value: snapshots.append(json.loads(json.dumps(value))),
            executor_limit=8, planner_limit=0, return_every=2,
        ))
        await asyncio.wait_for(awaiting_reply.wait(), timeout=1)
        attempt = events(snapshots[-1], "model_call")[0]
        self.assertEqual(attempt["status"], "pending")
        trial.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await trial
        recorded = events(snapshots[-1], "model_call")[0]
        self.assertEqual(recorded["event_id"], attempt["event_id"])
        self.assertEqual(recorded["status"], "interrupted")
        self.assertIsNone(snapshots[-1]["outcome"])

    async def test_async_backend_leaves_scoring_to_external_verifier(self):
        class AsyncHousehold(Household):
            async def step(self, text):
                await asyncio.sleep(0)
                return super().step(text)

        env = AsyncHousehold()
        record = await run_trial(
            mode="eo", env=env, planner=None, executor=AsyncMock(return_value=reply("Action: finish")),
            goal="Example task", constraints=[], workspace_id="test-external", executor_limit=2,
            planner_limit=0, return_every=1, save=lambda _: None, benchmark="terminalbench", external_verifier=True,
        )
        self.assertEqual(env.actions, ["finish"])
        self.assertEqual(record["events"][-1]["type"], "stop")
        self.assertIsNone(record["outcome"])
        self.assertEqual(events(record, "verifier"), [])


if __name__ == "__main__":
    unittest.main()
