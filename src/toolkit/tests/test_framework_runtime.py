import json
import re
import unittest
from unittest.mock import AsyncMock

from toolkit.envs.base import ActionResult
from toolkit.frameworks import FRAMEWORK_MODES, FRAMEWORK_PROTOCOL, PLAN_SCOPES, run_framework
from toolkit.prompts.frameworks import CONTINUOUS_EXECUTION_MONITORING, INITIAL_SUB_PLAN_GENERATION

from test_frameworks import Household, events, reply


def plan(summary, **fields):
    return reply(json.dumps({"thinking_summary": summary, **fields}))


def tool(name, **args):
    result = reply("")
    result.update(text=None, finish_reason="tool_calls",
                  tool_calls=[{"type": "function", "id": f"call-{name}",
                               "function": {"name": name, "arguments": json.dumps(args)}}])
    return result


FIND = {"stage_objective": "Locate and obtain the object.", "completion_condition": "The object is held."}
PLACE = {"stage_objective": "Put the object on the shelf.", "completion_condition": "Placement is confirmed."}
ACTIONS = ["inspect box", "take object", "put object on shelf"]


def full_plan(*stages):
    return [{"id": index, **stage} for index, stage in enumerate(stages, start=1)]


def observation_ref(messages, action):
    text = messages_text(messages)
    return int(re.findall(rf"Observation #(\d+) after {re.escape(action)}:", text)[-1])


def messages_text(messages):
    return "\n".join(message.get("content") or "" for message in messages)


def verified_placement(messages, *, full=False):
    fields = {"current_subplan_id": 2} if full else PLACE
    return plan("The feedback confirms that the object is held.", previous_stage_status="verified",
                evidence_refs=[observation_ref(messages, "take object")], **fields)


class MenuHousehold(Household):
    def get_available_actions(self):
        return [ACTIONS[min(self.state.steps, len(ACTIONS) - 1)]]


class FrameworkRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def trial(self, mode, planner_replies, executor_replies, *, limit=8, external=False, environment=None,
                    goal="Put the object on the shelf."):
        env = environment or Household()
        answers = iter(planner_replies)

        async def complete(messages, **_options):
            value = next(answers)
            if isinstance(value, Exception):
                raise value
            return value(messages) if callable(value) else value

        planner = AsyncMock(side_effect=complete)
        executor = AsyncMock(side_effect=executor_replies)
        snapshots = []
        record = await run_framework(
            mode=mode, env=env, planner=planner, executor=executor, goal=goal,
            workspace_id="private-workspace", executor_limit=limit,
            external_verifier=external, save=lambda value: snapshots.append(json.loads(json.dumps(value))),
            protocol_version=FRAMEWORK_PROTOCOL,
        )
        self.assertEqual(record, snapshots[-1])
        self.assertEqual(env.resets, 1)
        self.assertNotIn("constraints", record)
        self.assertTrue(all("private-workspace" not in json.dumps(event["messages"])
                            for event in events(record, "model_call")))
        return record, env, planner, executor

    async def test_task_requirements_remain_in_goal_without_a_constraints_block(self):
        goal = "Put the object on the shelf. Keep its label attached."
        record, *_ = await self.trial(
            "pe-s", [plan("Collect and place it.", full_plan=full_plan(FIND, PLACE))],
            [reply(f"Action: {action}") for action in ACTIONS], goal=goal,
        )
        self.assertTrue(record["outcome"]["success"])
        self.assertEqual(record["goal"], goal)
        for event in events(record, "model_call"):
            text = json.dumps(event["messages"])
            self.assertIn(goal, text)
            self.assertNotIn("Hard constraints", text)
            self.assertNotIn('"hard_constraints"', text)
        self.assertTrue(all("hard_constraints" not in event for event in record["events"]))

    async def test_six_variants_start_with_planning_and_use_their_own_execution_loop(self):
        taken = [reply(f"Action: {action}") for action in ACTIONS]
        update = tool("request_plan", reason="I found the object.")
        route = full_plan(FIND, PLACE)
        revised = {**PLACE, "stage_objective": "Put the identified object on the shelf."}
        initial_full = plan("The task mentions an object and a shelf.", full_plan=route)
        initial_sub = plan("The location needs confirmation.", **FIND)
        finish = reply("Judgment: The environment ended; the score has not been supplied.")
        cases = {
            "eo": ([], taken, "eee"),
            "pe-s": ([initial_full], taken, "peee"),
            "pe-d-f": ([initial_full, plan("Specify the identified object.", full_plan=full_plan(FIND, revised))],
                       [taken[0], update, *taken[1:]], "peepee"),
            "pe-d-s": ([initial_sub, plan("Obtain and place the object.",
                                         stage_objective="Obtain and place the identified object.",
                                         completion_condition="The object is on the shelf.")],
                       [taken[0], update, *taken[1:]], "peepee"),
            "pc-s": ([initial_sub, plan("Continue collecting the object."), verified_placement, finish],
                     taken, "pepepep"),
            "pc-f": ([plan("The first phase is collection.", full_plan=route, current_subplan_id=1),
                      plan("Specify the identified object.", full_plan=full_plan(FIND, revised),
                           revision_reason="Specify the identified object."),
                      lambda messages: verified_placement(messages, full=True), finish], taken, "pepepep"),
        }
        self.assertEqual(tuple(cases), FRAMEWORK_MODES)
        for mode, (planner_replies, executor_replies, order) in cases.items():
            with self.subTest(mode=mode):
                record, env, planner, executor = await self.trial(
                    mode, planner_replies, executor_replies, environment=MenuHousehold(),
                )
                self.assertEqual(record["plan_scope"], PLAN_SCOPES[mode])
                self.assertEqual(record["protocol_version"], "two-phase-v2")
                self.assertEqual(env.actions, ACTIONS)
                self.assertEqual(record["outcome"], {"reason": "task_finish", "success": True, "reward": 1.0})
                self.assertEqual(events(record, "stop")[0]["real_environment_steps"], 3)
                calls = events(record, "model_call")
                self.assertEqual("".join(event["role"][0] for event in calls), order)
                steps = 0
                for event in record["events"]:
                    if event["type"] == "model_call":
                        content = "\n".join(item.get("content") or "" for item in event["messages"])
                        if event["role"] == "executor":
                            self.assertIn(f"Available actions: {ACTIONS[min(steps, 2)]}", content)
                        else:
                            self.assertNotIn("Available actions:", content)
                    elif event["type"] == "tool_event" and event["dispatched"]:
                        steps += 1
                for call in planner.await_args_list:
                    self.assertNotIn("tools", call.kwargs)
                    self.assertNotIn("tool_choice", call.kwargs)
                for call in executor.await_args_list:
                    self.assertEqual([item["function"]["name"] for item in call.kwargs.get("tools", [])],
                                     ["request_plan"] if mode.startswith("pe-d") else [])
                    self.assertNotIn("tool_choice", call.kwargs)
                if mode.startswith("pc"):
                    decisions = events(record, "planner_decision")
                    self.assertEqual([item["planner_phase"] for item in decisions],
                                     [INITIAL_SUB_PLAN_GENERATION, *[CONTINUOUS_EXECUTION_MONITORING] * 3])
                    self.assertEqual([item["stage_changed"] for item in decisions[:-1]], [True, False, True])
                    self.assertTrue(decisions[-1]["read_only"])
                    self.assertEqual(decisions[-1]["verified_stages"][0]["stage"]["stage_objective"],
                                     FIND["stage_objective"])
                    self.assertFalse(events(record, "model_tool_result"))
                    self.assertTrue(all(item["role"] != "tool" for call in calls for item in call["messages"]))
                    planner_calls = [event for event in calls if event["role"] == "planner"]
                    for earlier, later in zip(planner_calls, planner_calls[1:]):
                        between = [event for event in events(record, "tool_event")
                                   if earlier["event_id"] < event["event_id"] < later["event_id"]]
                        self.assertEqual(len(between), 1)
                        self.assertIn(between[0]["observation"], json.dumps(later["messages"]))
                    messages = [call.args[0] for call in executor.await_args_list]
                    self.assertIn("You see an object in the box.", str(messages[1]))
                    self.assertIn("You see an object in the box.", str(messages[2]))
                    self.assertIn("You take the object.", str(messages[2]))
                elif mode.startswith("pe-d"):
                    request = executor.await_args_list[2].args[0]
                    index = next(index for index, item in enumerate(request) if item.get("tool_calls"))
                    self.assertEqual(request[index]["role"], "assistant")
                    self.assertEqual(request[index + 1]["role"], "tool")
                    self.assertEqual(request[index + 1]["tool_call_id"], request[index]["tool_calls"][0]["id"])
                    self.assertEqual(len(events(record, "tool_event")), 3)

    async def test_initial_planning_failure_never_calls_executor(self):
        truncated = plan("Start collecting.", **FIND)
        truncated["finish_reason"] = "length"
        cases = (
            ("pe-s", reply("Action: inspect box"), "invalid_planner_json"),
            ("pe-s", plan("Keep initial guidance.", keep=True), "invalid_keep"),
            ("pc-s", plan("Start collecting."), "missing_stage_objective"),
            ("pc-s", plan("Start collecting.", evidence_refs=[999], **FIND), "unknown_evidence_ref"),
            ("pc-s", tool("execute_step", thinking_summary="Start collecting.", **FIND), "unavailable_tool"),
            ("pc-s", truncated, "truncated_response"),
        )
        for mode, response, error in cases:
            with self.subTest(mode=mode, error=error):
                record, env, planner, executor = await self.trial(mode, [response], [])
                self.assertEqual(env.actions, [])
                self.assertEqual(planner.await_count, 1)
                executor.assert_not_awaited()
                self.assertTrue(events(record, "decision_error", error=error))
                self.assertEqual(record["outcome"], {"reason": "protocol_error", "success": None, "reward": None})

    async def test_invalid_replanning_request_is_rejected_before_planner_or_environment_replay(self):
        mixed = tool("request_plan", reason="Plan.")
        mixed["text"] = "Action: inspect box"
        invalid = (mixed, tool("request_plan", reason="Plan.", evidence_refs=[999]), tool("execute_step"))
        for response in invalid:
            with self.subTest(response=response):
                record, env, planner, executor = await self.trial(
                    "pe-d-s", [plan("Start collecting.", **FIND)], [response],
                )
                self.assertEqual(env.actions, [])
                self.assertEqual(planner.await_count, 1)
                executor.assert_awaited_once()
                self.assertEqual(record["outcome"]["reason"], "protocol_error")

    async def test_stage_change_keeps_history_and_only_current_action_menu(self):
        class PricedHousehold(MenuHousehold):
            def execute_action(self, action):
                result = super().execute_action(action)
                if action == "inspect box":
                    return ActionResult("The object costs 7 credits.", result.reward, result.valid)
                return result

        def retain_price(messages):
            return plan("Keep collecting; retain the observed price.",
                        evidence_refs=[observation_ref(messages, "inspect box")])

        record, env, _, executor = await self.trial(
            "pc-s", [plan("Collect the object.", **FIND), retain_price, verified_placement, reply("Judgment: Finished.")],
            [reply(f"Action: {action}") for action in ACTIONS], environment=PricedHousehold(),
        )
        last = messages_text(executor.await_args_list[-1].args[0])
        price_event = next(event for event in events(record, "tool_event") if event["action"] == "inspect box")
        self.assertIn(f"Observation #{price_event['observation_id']} after inspect box: Observation: The object costs 7 credits.", last)
        self.assertIn(PLACE["stage_objective"], last)
        self.assertNotIn(FIND["stage_objective"], last)
        self.assertIn("Available actions: put object on shelf", last)
        self.assertNotIn("Available actions: inspect box", last)
        self.assertEqual(env.actions, ACTIONS)
        self.assertTrue(env.holding)
        self.assertEqual(len({event["request_id"] for event in events(record, "execution_request")}), 2)

    async def test_full_history_survives_long_feedback_and_stage_changes(self):
        initial = "Initial room detail. " * 150 + "INITIAL_HISTORY_END"
        observed = "Observed object detail. " * 200 + "OBSERVATION_HISTORY_END"
        executor_reply = "Thought: " + "Visible execution judgment. " * 100 + "EXECUTOR_REPLY_END\nAction: inspect box"

        class LongHousehold(MenuHousehold):
            def __init__(self):
                super().__init__()
                self._initial_observation = initial

            def execute_action(self, action):
                result = super().execute_action(action)
                if action == "inspect box":
                    return ActionResult(observed, result.reward, result.valid)
                return result

        record, env, planner, executor = await self.trial(
            "pc-s", [plan("Collect the object.", **FIND), plan("Continue collecting."),
                     verified_placement, reply("Judgment: Finished.")],
            [reply(executor_reply), reply("Action: take object"), reply("Action: put object on shelf")],
            environment=LongHousehold(),
        )
        last_executor = messages_text(executor.await_args_list[-1].args[0])
        last_monitor = messages_text(planner.await_args_list[-1].args[0])
        for original in (initial, observed, executor_reply):
            self.assertIn(original, last_executor)
            self.assertIn(original, last_monitor)
        self.assertEqual(re.findall(r"Observation #(\d+)", last_executor), ["1", "2", "3"])
        self.assertEqual(last_executor.count("Available actions:"), 1)
        for call in events(record, "model_call"):
            text = messages_text(call["messages"])
            self.assertNotIn("Earlier public evidence:", text)
            self.assertNotIn("Recent interactions in this execution context:", text)
            if call["role"] == "planner":
                self.assertNotIn("Available actions:", text)
        self.assertEqual(env.actions, ACTIONS)

    async def test_observation_numbers_ignore_planning_and_local_rejections(self):
        record, env, planner, executor = await self.trial(
            "pe-d-s", [plan("Collect the object.", evidence_refs=[1], **FIND),
                       plan("The current guidance still applies.", evidence_refs=[2], keep=True)],
            [reply(""), reply("Action: inspect box"),
             tool("request_plan", reason="The object is now visible.", evidence_refs=[2]),
             reply("Action: take object"), reply("Action: put object on shelf")],
        )
        initial = events(record, "initial_observation")[0]
        dispatched = [event for event in events(record, "tool_event") if event["dispatched"]]
        rejected = [event for event in events(record, "tool_event") if not event["dispatched"]]
        self.assertEqual(initial["observation_id"], 1)
        self.assertEqual([event["observation_id"] for event in dispatched], [2, 3, 4])
        self.assertTrue(all(event.get("observation_id") is None for event in rejected))
        self.assertNotEqual([event["event_id"] for event in dispatched], [2, 3, 4])
        self.assertEqual(events(record, "planner_decision")[1]["evidence_refs"], [2])
        self.assertEqual(env.actions, ACTIONS)
        self.assertEqual(planner.await_count, 2)
        self.assertEqual(executor.await_count, 5)
        self.assertEqual(record["outcome"]["reward"], 1)

    async def test_verified_phase_prompt_keeps_completion_and_evidence_without_old_judgment(self):
        summary = "The object is held. FUTURE_UNCERTAINTY: reaching the shelf is not established."

        def verified(messages):
            return plan(summary, previous_stage_status="verified",
                        evidence_refs=[observation_ref(messages, "take object")], **PLACE)

        record, _, planner, _ = await self.trial(
            "pc-s", [plan("Collect the object.", **FIND), plan("Keep collecting."),
                     verified, reply("Judgment: Finished.")],
            [reply(f"Action: {action}") for action in ACTIONS],
        )
        terminal_context = messages_text(planner.await_args_list[-1].args[0])
        self.assertIn(FIND["stage_objective"], terminal_context)
        self.assertIn(FIND["completion_condition"], terminal_context)
        self.assertIn("You take the object.", terminal_context)
        self.assertNotIn("FUTURE_UNCERTAINTY", terminal_context)
        self.assertEqual(events(record, "stage_result")[0]["thinking_summary"], summary)

    async def test_static_planning_prompt_has_no_later_request_instructions(self):
        taken = [reply(f"Action: {action}") for action in ACTIONS]
        initial = plan("Collect and place the object.", full_plan=full_plan(FIND, PLACE))
        _, _, planner, _ = await self.trial("pe-s", [initial], taken)
        static = messages_text(planner.await_args_list[0].args[0])
        self.assertNotIn("On a later Executor request", static)
        self.assertNotIn("keep the current guidance if it still answers the request", static)
        _, _, planner, _ = await self.trial(
            "pe-d-f", [initial, plan("The current guidance remains appropriate.", keep=True)],
            [taken[0], tool("request_plan", reason="Check the newly visible object."), *taken[1:]],
        )
        first = messages_text(planner.await_args_list[0].args[0])
        later = messages_text(planner.await_args_list[1].args[0])
        self.assertNotIn("keep the current guidance if it still answers the request", first)
        self.assertIn("Check the newly visible object.", later)
        self.assertIn("current guidance", later)

    async def test_planner_completion_claim_and_empty_work_do_not_end_pc(self):
        record, env, _, executor = await self.trial(
            "pc-s", [plan("Collect the object.", **FIND),
                     plan("I think the whole task is complete.", remaining_work=[]),
                     plan("Keep the current phase."), reply("Judgment: The environment ended.")],
            [reply(f"Action: {action}") for action in ACTIONS],
        )
        self.assertEqual(env.actions, ACTIONS)
        self.assertEqual(executor.await_count, 3)
        self.assertEqual(record["outcome"], {"reason": "task_finish", "success": True, "reward": 1.0})

    async def test_local_rejection_counts_no_env_steps_and_stops_repeated_empty_rounds(self):
        record, env, _, _ = await self.trial("eo", [], [reply(""), reply("")], limit=1)
        self.assertEqual(env.actions, [])
        self.assertEqual(events(record, "stop")[0]["real_environment_steps"], 0)
        self.assertEqual([event["dispatched"] for event in events(record, "tool_event")], [False, False])
        self.assertTrue(events(record, "decision_error", error="consecutive_no_action_rounds"))

    async def test_terminal_review_failure_keeps_final_step_and_native_verdict(self):
        record, _, planner, _ = await self.trial(
            "pc-s", [plan("Place the object.", **PLACE), TimeoutError()],
            [reply("Action: put object on shelf")], limit=1,
        )
        self.assertEqual(planner.await_count, 2)
        self.assertEqual(record["outcome"], {"reason": "task_finish", "success": False, "reward": 0.5})
        self.assertTrue(events(record, "decision_error", error="TimeoutError"))
        self.assertIn("The simulator ended the episode.", str(planner.await_args_list[-1].args[0]))

    async def test_read_only_review_at_the_step_limit(self):
        record, _, planner, executor = await self.trial(
            "pc-s", [plan("Inspect the box.", **FIND), reply("Judgment: Object seen.")],
            [reply("Action: inspect box")], limit=1,
        )
        self.assertEqual(planner.await_count, 2)
        executor.assert_awaited_once()
        self.assertNotIn("tools", planner.await_args_list[-1].kwargs)
        self.assertEqual(record["outcome"]["reason"], "executor_budget")
        self.assertTrue(events(record, "planner_decision", read_only=True))

    async def test_pc_submission_goes_through_executor_and_environment(self):
        class SubmissionEnvironment(Household):
            def execute_action(self, action):
                self.actions.append(action)
                return ActionResult("Submission accepted for independent verification.", 0, True,
                                    done=True, dispatched=False)

        record, env, planner, executor = await self.trial(
            "pc-s", [plan("Prepare the submission.", **PLACE), reply("Judgment: Submission accepted.")],
            [reply("Action: finish")], external=True, environment=SubmissionEnvironment(),
        )
        self.assertEqual(env.actions, ["finish"])
        executor.assert_awaited_once()
        self.assertIsNone(record["outcome"])
        self.assertEqual(events(record, "stop")[0]["reason"], "task_finish")
        self.assertEqual(events(record, "stop")[0]["real_environment_steps"], 0)
        self.assertEqual(events(record, "initial_observation")[0]["observation_id"], 1)
        self.assertEqual(events(record, "tool_event")[0]["observation_id"], 2)
        self.assertIn("Submission accepted for independent verification.", str(planner.await_args_list[-1].args[0]))


if __name__ == "__main__":
    unittest.main()
