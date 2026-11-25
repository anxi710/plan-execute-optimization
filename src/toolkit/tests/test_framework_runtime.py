import json
import re
import unittest
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, patch

from toolkit.envs.base import ActionResult
from toolkit.frameworks import FRAMEWORK_MODES, FRAMEWORK_PROTOCOL, PLAN_SCOPES, run_framework
from toolkit.models.context import ContextWindow
from toolkit.prompts import load_framework_prompts

from test_frameworks import Household, events, reply


def plan(summary, **fields):
    return reply(json.dumps({"assessment": summary, **fields}))


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
                    goal="Put the object on the shelf.", context_window=None, benchmark="alfworld"):
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
            protocol_version=FRAMEWORK_PROTOCOL, context_window=context_window,
            benchmark=benchmark,
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
        update["text"] = "Thought: The new observation requires updated guidance."
        route = full_plan(FIND, PLACE)
        revised = {**PLACE, "stage_objective": "Put the identified object on the shelf."}
        initial_full = plan("The task mentions an object and a shelf.", full_plan=route)
        initial_sub = plan("The location needs confirmation.", **FIND)
        cases = {
            "eo": ([], taken, "eee"),
            "pe-s": ([initial_full], taken, "peee"),
            "pe-d-f": ([initial_full, plan("Specify the identified object.", full_plan=full_plan(FIND, revised))],
                       [taken[0], update, *taken[1:]], "peepee"),
            "pe-d-s": ([initial_sub, plan("Obtain and place the object.",
                                         stage_objective="Obtain and place the identified object.",
                                         completion_condition="The object is on the shelf.")],
                       [taken[0], update, *taken[1:]], "peepee"),
            "pc-s": ([initial_sub, plan("Continue collecting the object."), verified_placement],
                     taken, "pepepe"),
            "pc-f": ([plan("The first phase is collection.", full_plan=route, current_subplan_id=1),
                      plan("Specify the identified object.", full_plan=full_plan(FIND, revised),
                           revision_reason="Specify the identified object."),
                      lambda messages: verified_placement(messages, full=True)], taken, "pepepe"),
        }
        self.assertEqual(tuple(cases), FRAMEWORK_MODES)
        for mode, (planner_replies, executor_replies, order) in cases.items():
            with self.subTest(mode=mode):
                record, env, planner, executor = await self.trial(
                    mode, planner_replies, executor_replies, environment=MenuHousehold(),
                )
                self.assertEqual(record["plan_scope"], PLAN_SCOPES[mode])
                self.assertEqual(record["protocol_version"], "two-phase-v3")
                self.assertEqual(env.actions, ACTIONS)
                self.assertEqual(record["outcome"], {"reason": "task_finish", "success": True, "reward": 1.0})
                self.assertEqual(events(record, "stop")[0]["real_environment_steps"], 3)
                calls = events(record, "model_call")
                prompts = load_framework_prompts(mode, "alfworld")
                self.assertEqual("".join(event["role"][0] for event in calls), order)
                steps = 0
                for event in record["events"]:
                    if event["type"] == "model_call":
                        content = event["messages"][0]["content"]
                        goal_position = content.index("Task goal:")
                        if event["role"] == "executor":
                            self.assertTrue(content.startswith(prompts.EXECUTOR_PROMPT + "\n\nTask goal:"))
                            history_position = content.index("Interaction history:")
                            menu_position = content.index("Available actions:")
                            self.assertLess(goal_position, history_position)
                            self.assertLess(history_position, menu_position)
                            self.assertIn(f"Available actions: {ACTIONS[min(steps, 2)]}", content)
                            if mode != "eo":
                                guidance = ("Active sub-plan:" if mode in {"pe-d-s", "pc-f", "pc-s"}
                                            else "Current advisory plan:")
                                self.assertLess(menu_position, content.index(guidance))
                            if mode.startswith("pe-d"):
                                self.assertEqual(content.count("Choose exactly one branch per turn:"), 1)
                                self.assertNotIn("Write exactly one nonempty Action: <command> line per turn.", content)
                        else:
                            self.assertNotIn("Available actions:", content)
                            history_position = content.index("Public interaction history:")
                            self.assertLess(goal_position, history_position)
                            self.assertLess(history_position, content.index("Return exactly one JSON object"))
                            self.assertNotIn("Initial Sub-Plan Generation", content)
                            self.assertNotIn("Continuous Execution Monitoring", content)
                            if "Current full-plan:" in content:
                                self.assertLess(history_position, content.index("Current full-plan:"))
                            if "Active sub-plan" in content:
                                self.assertLess(history_position, content.index("Active sub-plan"))
                    elif event["type"] == "tool_event" and event["dispatched"]:
                        steps += 1
                for call in planner.await_args_list:
                    self.assertNotIn("tools", call.kwargs)
                    self.assertNotIn("tool_choice", call.kwargs)
                for call in executor.await_args_list:
                    self.assertEqual([item["function"]["name"] for item in call.kwargs.get("tools", [])],
                                     ["request_plan"] if mode.startswith("pe-d") else [])
                    self.assertNotIn("tool_choice", call.kwargs)
                    if mode.startswith("pe-d"):
                        self.assertEqual(call.kwargs["tools"][0]["function"]["description"],
                                         prompts.PLAN_REQUEST_DESCRIPTION)
                if mode.startswith("pc"):
                    decisions = events(record, "planner_decision")
                    self.assertEqual([item["planner_phase"] for item in decisions],
                                     ["initial_planning", "execution_monitoring", "execution_monitoring"])
                    self.assertEqual([item["stage_changed"] for item in decisions], [True, False, True])
                    self.assertTrue(all(item["discarded_stages"] == [] for item in decisions))
                    self.assertFalse(events(record, "planner_decision", read_only=True))
                    self.assertEqual(decisions[-1]["verified_stages"][0]["stage"]["stage_objective"],
                                     FIND["stage_objective"])
                    self.assertFalse(events(record, "model_tool_result"))
                    self.assertTrue(all(item["role"] != "tool" for call in calls for item in call["messages"]))
                    planner_calls = [event for event in calls if event["role"] == "planner"]
                    initial_prompt, monitor_prompt = prompts.PLANNER_INITIAL_PROMPT, prompts.PLANNER_MONITOR_PROMPT
                    self.assertIn(initial_prompt, messages_text(planner_calls[0]["messages"]))
                    self.assertNotIn(monitor_prompt, messages_text(planner_calls[0]["messages"]))
                    for monitor in planner_calls[1:]:
                        self.assertIn(monitor_prompt, messages_text(monitor["messages"]))
                        self.assertNotIn(initial_prompt, messages_text(monitor["messages"]))
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

    async def test_runtime_uses_selected_framework_and_benchmark_prompts(self):
        for benchmark in ("alfworld", "sciworld", "webshop", "terminalbench"):
            for mode in FRAMEWORK_MODES:
                with self.subTest(mode=mode, benchmark=benchmark):
                    initial = (plan("Collect and place it.", full_plan=full_plan(FIND, PLACE), current_subplan_id=1)
                               if PLAN_SCOPES[mode] == "full" else plan("Collect the object.", **FIND))
                    record, _, planner, executor = await self.trial(
                        mode, [] if mode == "eo" else [initial], [reply("Action: finish")], benchmark=benchmark,
                    )
                    prompts = load_framework_prompts(mode, benchmark)
                    content = executor.await_args.args[0][0]["content"]
                    self.assertTrue(content.startswith(prompts.EXECUTOR_PROMPT + "\n\nTask goal:"))
                    self.assertNotIn("Think as needed. Choose one Action.", content)
                    self.assertEqual(record["outcome"]["reason"], "task_finish")
                    if mode == "eo":
                        planner.assert_not_awaited()
                    else:
                        content = planner.await_args.args[0][0]["content"]
                        self.assertTrue(content.startswith(prompts.PLANNER_PROMPT + "\n\nTask goal:"))
                        self.assertIn(prompts.PLANNER_INITIAL_PROMPT, content)

    async def test_explicit_instruction_file_takes_precedence_in_runtime(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "executor.txt"
            instruction = "Custom executor instructions with {literal parameters}.\n"
            path.write_text(instruction, encoding="utf-8")
            for mode in ("eo", "pe-s", "pe-d-f", "pe-d-s", "pc-f", "pc-s"):
                with self.subTest(mode=mode):
                    env = Household()
                    env.instruction_path = path
                    initial = (plan("Collect and place it.", full_plan=full_plan(FIND, PLACE), current_subplan_id=1)
                               if PLAN_SCOPES[mode] == "full" else plan("Collect the object.", **FIND))
                    _, _, _, executor = await self.trial(
                        mode, [] if mode == "eo" else [initial], [reply("Action: finish")], environment=env,
                    )
                    self.assertTrue(executor.await_args.args[0][0]["content"].startswith(instruction + "\n\nTask goal:"))

    async def test_replanning_tool_schema_matches_context_budget_and_actual_request(self):
        prepare = ContextWindow.prepare
        for mode in ("pe-d-f", "pe-d-s"):
            with self.subTest(mode=mode):
                options = []

                def capture(window, records, render, **kwargs):
                    if kwargs.get("model_options"):
                        options.append(deepcopy(kwargs["model_options"]))
                    return prepare(window, records, render, **kwargs)

                initial = (plan("Collect and place it.", full_plan=full_plan(FIND, PLACE))
                           if mode == "pe-d-f" else plan("Collect the object.", **FIND))
                request = tool("request_plan", reason="The object is visible.", evidence_refs=[2])
                request["text"] = "Thought: The observed object needs new planning guidance."
                with patch.object(ContextWindow, "prepare", new=capture):
                    record, _, _, executor = await self.trial(
                        mode, [initial, plan("The guidance remains applicable.", keep=True)],
                        [reply("Action: inspect box"), request, reply("Action: take object"),
                         reply("Action: put object on shelf")],
                    )
                self.assertTrue(record["outcome"]["success"])
                self.assertEqual(options, [call.kwargs for call in executor.await_args_list])
                self.assertTrue(all(option["tools"][0]["function"]["description"] ==
                                    load_framework_prompts(mode, "alfworld").PLAN_REQUEST_DESCRIPTION
                                    for option in options))

    async def test_initial_planning_failure_never_calls_executor(self):
        truncated = plan("Start collecting.", **FIND)
        truncated["finish_reason"] = "length"
        cases = (
            ("pe-s", reply("Action: inspect box"), "invalid_planner_json"),
            ("pe-s", plan("Keep initial guidance.", keep=True), "invalid_keep"),
            ("pc-s", plan("Start collecting."), "missing_stage_objective"),
            ("pc-s", plan("Start collecting.", evidence_refs=[999], **FIND), "unknown_evidence_ref"),
            ("pc-s", tool("execute_step", assessment="Start collecting.", **FIND), "unavailable_tool"),
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
            "pc-s", [plan("Collect the object.", **FIND), retain_price, verified_placement],
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
                     verified_placement],
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

    async def test_bounded_prompt_discards_oldest_interactions_but_keeps_raw_log(self):
        class LongFeedback(Household):
            def execute_action(self, action):
                self.actions.append(action)
                count = len(self.actions)
                return ActionResult(f"FEEDBACK_{count}:" + "x" * 8000, int(count == 3), True,
                                    done=count == 3, success=count == 3)

        record, env, _, executor = await self.trial(
            "eo", [], [reply("Action: inspect box"), reply("Action: take object"),
                       reply("Action: put object on shelf")], environment=LongFeedback(),
            context_window={"max_input_tokens": 11000},
        )
        calls = executor.await_args_list
        self.assertTrue(all(len(call.args[0]) == 1 and call.args[0][0]["role"] == "user" for call in calls))
        self.assertIn("FEEDBACK_1:" + "x" * 8000, messages_text(calls[1].args[0]))
        last = messages_text(calls[2].args[0])
        self.assertNotIn("FEEDBACK_1:", last)
        self.assertIn("FEEDBACK_2:" + "x" * 8000, last)
        self.assertIn("FEEDBACK_1:" + "x" * 8000, events(record, "tool_event")[0]["observation"])
        meta = events(record, "model_call")[-1]["context_window"]
        self.assertIn(2, meta["dropped_observation_ids"])
        self.assertIn(3, meta["kept_observation_ids"])
        self.assertEqual(meta["reported_input_tokens"], 10)
        self.assertTrue(all("context_metadata" not in call.kwargs for call in calls))
        self.assertEqual(record["outcome"]["reward"], 1)

    async def test_only_current_native_handoff_remains_outside_the_single_prompt(self):
        record, _, _, executor = await self.trial(
            "pe-d-s", [plan("Find it.", **FIND), plan("Pick it up.", **FIND), plan("Place it.", **PLACE)],
            [reply("Action: inspect box"), tool("request_plan", reason="Object found.", evidence_refs=[2]),
             reply("Action: take object"), tool("request_plan", reason="Object held.", evidence_refs=[3]),
             reply("Action: put object on shelf")],
        )
        requests = [call.args[0] for call in executor.await_args_list]
        self.assertEqual([len(messages) for messages in requests], [1, 1, 3, 1, 3])
        self.assertEqual([message["role"] for message in requests[-1]], ["user", "assistant", "tool"])
        self.assertIn("Object found.", requests[-1][0]["content"])
        self.assertIn("Planning tool result:", requests[-1][0]["content"])
        self.assertEqual(len(events(record, "model_tool_result")), 2)

    async def test_current_local_feedback_is_protected_from_window_eviction(self):
        record, env, _, executor = await self.trial(
            "eo", [], [reply("Malformed current reply " + "x" * 8000), reply("Action: inspect box")],
            context_window={"max_input_tokens": 4000},
        )
        executor.assert_awaited_once()
        self.assertEqual(env.actions, [])
        self.assertEqual(record["outcome"]["reason"], "runtime_error")
        overflow = events(record, "context_window_error")[0]
        self.assertIn("Malformed current reply " + "x" * 8000, overflow["messages"][0]["content"])
        self.assertIn("Local action feedback:", overflow["messages"][0]["content"])
        self.assertEqual(overflow["context_window"]["dropped_record_ids"], [])

    async def test_verified_phase_prompt_keeps_completion_and_evidence_without_old_judgment(self):
        summary = "The object is held. FUTURE_UNCERTAINTY: reaching the shelf is not established."

        class TransitHousehold(Household):
            def execute_action(self, action):
                if action == "go to shelf":
                    self.actions.append(action)
                    return ActionResult("You are at the shelf.", self.state.reward, True)
                return super().execute_action(action)

        def verified(messages):
            return plan(summary, previous_stage_status="verified",
                        evidence_refs=[observation_ref(messages, "take object")], **PLACE)

        record, _, planner, _ = await self.trial(
            "pc-s", [plan("Collect the object.", **FIND), plan("Keep collecting."),
                     verified, plan("Place the object on the shelf.")],
            [reply(f"Action: {action}") for action in [*ACTIONS[:2], "go to shelf", ACTIONS[2]]],
            environment=TransitHousehold(),
        )
        monitor_context = messages_text(planner.await_args_list[-1].args[0])
        self.assertIn("Verified phases:", monitor_context)
        self.assertIn(FIND["stage_objective"], monitor_context)
        self.assertIn(FIND["completion_condition"], monitor_context)
        self.assertIn("You take the object.", monitor_context)
        self.assertNotIn("FUTURE_UNCERTAINTY", monitor_context)
        self.assertEqual(events(record, "stage_result")[0]["assessment"], summary)

    async def test_blocked_goals_are_replanned_without_rewriting_discarded_goals(self):
        old_goal = {"stage_objective": "Find the object in the sealed box.",
                    "completion_condition": "The object from that box is held."}
        old_future = {"stage_objective": "Deliver that specific object to the shelf.",
                      "completion_condition": "The object from the sealed box is on the shelf."}
        new_goal = {"stage_objective": "Find an accessible replacement object.",
                    "completion_condition": "An accessible object is held."}
        new_future = {"stage_objective": "Place the replacement object on the shelf.",
                      "completion_condition": "The replacement object is on the shelf."}

        class BlockedHousehold(Household):
            def execute_action(self, action):
                if action == "inspect box":
                    self.actions.append(action)
                    return ActionResult("The box is sealed and cannot be opened.", 0, True)
                return super().execute_action(action)

        for mode in ("pc-f", "pc-s"):
            with self.subTest(mode=mode):
                full = mode == "pc-f"
                old_route = [{"id": 7, **old_goal}, {"id": 3, **old_future}]
                new_route = [{"id": 11, **new_goal}, {"id": 19, **new_future}]
                initial = {"full_plan": old_route, "current_subplan_id": 7} if full else old_goal
                replacement = ({"full_plan": new_route, "current_subplan_id": 11,
                                "revision_reason": "The sealed box makes the old route infeasible."}
                               if full else new_goal)
                advance = {"current_subplan_id": 19} if full else new_future
                record, env, _, _ = await self.trial(
                    mode, [plan("Find and deliver the object.", **initial),
                           plan("The sealed box cannot be opened; use another object.",
                                previous_stage_status="blocked", evidence_refs=[2], **replacement),
                           plan("The replacement object is held.", previous_stage_status="verified",
                                evidence_refs=[3], **advance)],
                    [reply(f"Action: {action}") for action in ACTIONS], environment=BlockedHousehold(),
                )
                decisions = events(record, "planner_decision")
                self.assertEqual(decisions[1]["discarded_stages"], old_route if full else [old_goal])
                self.assertEqual(decisions[1]["stage_objective"], new_goal["stage_objective"])
                self.assertEqual(decisions[1]["evidence_refs"], [2])
                closure = events(record, "stage_result")[0]
                self.assertEqual(closure["status"], "blocked")
                self.assertEqual(closure["stage"], old_route[0] if full else old_goal)
                self.assertEqual(decisions[-1]["discarded_stages"], [])
                if full:
                    self.assertEqual(decisions[0]["plan"], old_route)
                    self.assertEqual(decisions[1]["plan"], new_route)
                self.assertEqual(env.actions, ACTIONS)
                self.assertTrue(record["outcome"]["success"])

    async def test_completed_goals_removed_from_remaining_plan_are_not_discarded(self):
        old_route = [{"id": 7, **FIND}, {"id": 3, **PLACE}]
        record, *_ = await self.trial(
            "pc-f", [plan("Collect and place it.", full_plan=old_route, current_subplan_id=7),
                     plan("Collection is complete.", full_plan=[old_route[1]], current_subplan_id=3,
                          previous_stage_status="verified", evidence_refs=[2],
                          revision_reason="Keep only the remaining placement phase.")],
            [reply("Action: take object"), reply("Action: put object on shelf")],
        )
        self.assertEqual(events(record, "planner_decision")[-1]["discarded_stages"], [])
        self.assertEqual(events(record, "stage_result")[0]["stage"], old_route[0])
        self.assertEqual(events(record, "stage_result")[0]["status"], "verified")

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

    async def test_model_completion_claims_and_empty_work_do_not_end_pc(self):
        record, env, _, executor = await self.trial(
            "pc-s", [plan("Collect the object.", **FIND),
                     plan("I think the whole task is complete.", remaining_work=[]),
                     plan("Keep the current phase.")],
            [reply("Thought: The task is complete.\nAction: inspect box"),
             *[reply(f"Action: {action}") for action in ACTIONS[1:]]],
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

    async def test_native_terminal_feedback_stops_without_another_planner_call(self):
        record, _, planner, _ = await self.trial(
            "pc-s", [plan("Place the object.", **PLACE)],
            [reply("Action: put object on shelf")], limit=1,
        )
        planner.assert_awaited_once()
        self.assertEqual(record["outcome"], {"reason": "task_finish", "success": False, "reward": 0.5})
        self.assertFalse(events(record, "decision_error"))
        self.assertIn("The simulator ended the episode.", events(record, "tool_event")[-1]["observation"])

    async def test_step_limit_stops_without_another_planner_call(self):
        record, _, planner, executor = await self.trial(
            "pc-s", [plan("Inspect the box.", **FIND)],
            [reply("Action: inspect box")], limit=1,
        )
        planner.assert_awaited_once()
        executor.assert_awaited_once()
        self.assertNotIn("tools", planner.await_args_list[-1].kwargs)
        self.assertEqual(record["outcome"]["reason"], "executor_budget")
        self.assertFalse(events(record, "planner_decision", read_only=True))

    async def test_pc_submission_goes_through_executor_and_environment(self):
        class SubmissionEnvironment(Household):
            def execute_action(self, action):
                self.actions.append(action)
                return ActionResult("Submission accepted for independent verification.", 0, True,
                                    done=True, dispatched=False)

        record, env, planner, executor = await self.trial(
            "pc-s", [plan("Prepare the submission.", **PLACE)],
            [reply("Action: finish")], external=True, environment=SubmissionEnvironment(),
        )
        self.assertEqual(env.actions, ["finish"])
        planner.assert_awaited_once()
        executor.assert_awaited_once()
        self.assertIsNone(record["outcome"])
        self.assertEqual(events(record, "stop")[0]["reason"], "task_finish")
        self.assertEqual(events(record, "stop")[0]["real_environment_steps"], 0)
        self.assertEqual(events(record, "initial_observation")[0]["observation_id"], 1)
        self.assertEqual(events(record, "tool_event")[0]["observation_id"], 2)
        self.assertIn("Submission accepted for independent verification.", events(record, "tool_event")[-1]["observation"])


if __name__ == "__main__":
    unittest.main()
