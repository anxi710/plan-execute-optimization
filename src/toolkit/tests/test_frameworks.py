import asyncio
import json
import unittest
from unittest.mock import AsyncMock, patch

from toolkit.envs.base import ActionResult, BaseEnv
from toolkit.frameworks import MODES, run_framework
from toolkit.frameworks.control import _FrameworkController
from toolkit.rollout.log import EventLog


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
    def assert_task_context_only(self, calls, *, private_values=()):
        metadata_fields = (
            "timestamp", "workspace_id", "request_id", "plan_version", "type", "usage", "usage_responses",
            "tokens", "prompt_tokens", "completion_tokens", "total_tokens", "model_event_id", "future_metadata",
            "budgets", "executor_limit", "planner_limit", "return_every", "executor_attempts_remaining",
            "planner_attempts_remaining_after_this_call", "return_reason",
        )
        for call in calls:
            text = "\n".join(message["content"] for message in call["messages"])
            for field in metadata_fields:
                self.assertNotIn(f'"{field}"', text)
            for phrase in ("stage budget", "budget_pause", "executor_budget", "planner_budget"):
                self.assertNotIn(phrase, text)
            self.assertNotRegex(text, r"up to \d+ actions")
            for value in private_values:
                self.assertNotIn(value, text)

    async def trial(self, mode, planner_replies, executor_replies, **limits):
        env = Household()
        planner = AsyncMock(side_effect=planner_replies)
        executor = AsyncMock(side_effect=executor_replies)
        snapshots = []
        record = await run_framework(
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
        self.assertEqual(tuple(scripts), MODES)
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
                self.assert_task_context_only(model_events, private_values=(f"test-{mode}",))
                self.assertTrue(all(event["timestamp"] for event in record["events"]))
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
                    planner_calls = events(record, "model_call", role="planner")
                    context = json.loads(planner_calls[1]["messages"][0]["content"].rsplit("\n\n", 1)[1])
                    self.assertIn("Thought: I can explore locally.", json.dumps(context["feedback"]))
                    self.assertIn("Object might be under the bed.", context["planner_state"]["hypotheses"])
                    self.assertEqual(context["planner_state"]["remaining_work"], ["Put the object on the shelf."])
                    self.assertEqual(context["planner_state"]["observed_facts"][0]["event_id"], 1)
                    self.assertNotIn("Object might be under the bed.", json.dumps(context["planner_state"]["observed_facts"]))
                    for item in events(record, "planner_decision"):
                        state = item["planner_state"]
                        self.assertIn("Object might be under the bed.", state["hypotheses"])
                        self.assertNotIn("Object might be under the bed.", json.dumps(state["observed_facts"]))
                if mode == "pc":
                    terminal_context = json.loads(planner_calls[-1]["messages"][0]["content"].rsplit("\n\n", 1)[1])
                    self.assertIn("The simulator ended the episode.", json.dumps(terminal_context["feedback"]))
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

    async def test_internal_limits_do_not_change_initial_model_inputs(self):
        settings = (
            {"executor_limit": 2, "planner_limit": 2, "return_every": 1},
            {"executor_limit": 7, "planner_limit": 5, "return_every": 3},
        )
        for mode in MODES:
            with self.subTest(mode=mode):
                initial_inputs = []
                for limits in settings:
                    plans = {
                        "eo": [],
                        "pe-s": [reply("<plan>Find the object and place it on the shelf.</plan>")],
                        "pe-d": [decision("guide")],
                        "pc": [decision("delegate"), decision("finish")],
                    }[mode]
                    record, env, planner, executor = await self.trial(
                        mode, plans, [reply("Action: finish")], **limits,
                    )
                    self.assertEqual(record["budgets"], limits)
                    self.assertEqual(record["outcome"]["reason"], "task_finish")
                    self.assertEqual(env.actions, ["finish"])
                    self.assertEqual(executor.await_count, 1)
                    self.assert_task_context_only(events(record, "model_call"))
                    initial_inputs.append({
                        role: events(record, "model_call", role=role)[0]["messages"]
                        for role in ("planner", "executor")
                        if role == "executor" or planner.await_count
                    })
                self.assertEqual(*initial_inputs)

    async def test_native_action_candidates_are_only_added_to_executor_messages(self):
        class CandidateHousehold(Household):
            def get_available_actions(self):
                return [f"NATIVE_CANDIDATE_{self.state.steps}"]

        record = await run_framework(
            mode="pc", env=CandidateHousehold(),
            planner=AsyncMock(side_effect=[decision("delegate", 1), decision("delegate", 2), decision("finish", 3)]),
            executor=AsyncMock(side_effect=[reply("Action: take object"), reply("Action: put object on shelf")]),
            goal="Put the object on the shelf.", constraints=[], workspace_id="native-actions",
            executor_limit=4, planner_limit=3, return_every=1, save=lambda _: None,
        )
        self.assertTrue(record["outcome"]["success"])
        planner_calls = events(record, "model_call", role="planner")
        executor_calls = events(record, "model_call", role="executor")
        self.assertNotIn("NATIVE_CANDIDATE_", json.dumps([call["messages"] for call in planner_calls]))
        self.assertIn("Available actions: NATIVE_CANDIDATE_0", executor_calls[0]["messages"][0]["content"])
        self.assertIn("NATIVE_CANDIDATE_1", json.dumps(executor_calls[1]["messages"]))
        self.assertTrue(all("Available actions:" not in event["observation"] for event in events(record, "tool_event")))

    async def test_prompt_projection_excludes_future_log_and_state_metadata(self):
        emit = EventLog.emit
        private_log_value = "PRIVATE_LOG_FIELD_SENTINEL"
        private_state_value = "PRIVATE_STATE_FIELD_SENTINEL"

        def record_with_extra_metadata(log, kind, **fields):
            event = emit(log, kind, **fields)
            event["future_metadata"] = private_log_value
            if kind == "execution_feedback":
                for item in [*event["observed_changes"], *event["executor_claims"]]:
                    item["future_metadata"] = private_log_value
            return event

        for mode in ("pe-d", "pc"):
            with self.subTest(mode=mode):
                plans = [decision("guide" if mode == "pe-d" else "delegate", index) for index in range(1, 4)]
                if mode == "pc":
                    plans.append(decision("finish", 4))
                controller = _FrameworkController(
                    mode=mode, env=Household(), planner=AsyncMock(side_effect=plans),
                    executor=AsyncMock(side_effect=[reply("Thought: Inspect locally.\nAction: inspect box"),
                                                   reply("Action: take object"), reply("Action: put object on shelf")]),
                    goal="Put the object on the shelf.", constraints=["Use the household action interface."],
                    workspace_id="PRIVATE_WORKSPACE_SENTINEL", executor_limit=8, planner_limit=6, return_every=1,
                    save=lambda _: None, benchmark="alfworld", external_verifier=False,
                )
                controller.planner_state["future_metadata"] = private_state_value
                with patch.object(EventLog, "emit", record_with_extra_metadata):
                    record = await controller.run()
                self.assertTrue(record["outcome"]["success"])
                self.assert_task_context_only(events(record, "model_call"), private_values=(
                    private_log_value, private_state_value, "PRIVATE_WORKSPACE_SENTINEL",
                ))
                self.assertTrue(all(event["future_metadata"] == private_log_value for event in record["events"]))
                self.assertEqual(events(record, "execution_feedback")[0]["usage"]["tokens"]["total_tokens"], 15)
                self.assertEqual(events(record, "execution_feedback")[0]["observed_changes"][0]["future_metadata"],
                                 private_log_value)

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
        self.assertEqual(capped["budgets"]["executor_limit"], 1)
        self.assertTrue(events(capped, "execution_feedback", return_reason="executor_budget"))
        self.assertEqual(env.actions, ["inspect box"])
        self.assertEqual(planner.await_count, 1)
        self.assertEqual(executor.await_count, 1)

        planner_capped, env, planner, executor = await self.trial(
            "pe-d", [decision("guide")], [reply("Action: inspect box")], planner_limit=1,
        )
        self.assertEqual(planner_capped["outcome"]["reason"], "planner_budget")
        self.assertEqual(planner_capped["budgets"]["planner_limit"], 1)
        self.assertTrue(events(planner_capped, "execution_feedback", return_reason="budget_pause"))
        self.assertEqual(env.actions, ["inspect box"])
        self.assertEqual(planner.await_count, 1)
        self.assertEqual(executor.await_count, 1)

    async def test_cancellation_keeps_the_started_attempt(self):
        snapshots = []
        awaiting_reply = asyncio.Event()

        async def executor(_):
            awaiting_reply.set()
            await asyncio.Future()

        trial = asyncio.create_task(run_framework(
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
        record = await run_framework(
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
