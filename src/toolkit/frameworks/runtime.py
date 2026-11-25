"""Run initial planning followed by execution and feedback over one session."""

import json
import re
from functools import partial

from toolkit.prompts import load_executor_instruction, load_framework_prompts, render_action_feedback
from toolkit.models.context import ContextRecord, ContextWindow, ContextWindowExceeded
from toolkit.rollout.log import EventLog
from toolkit.rollout.session import RolloutSession

from .tools import FunctionTool, ToolProtocolError, invoke_tool


FRAMEWORK_PROTOCOL = "two-phase-v3"
PLAN_SCOPES = {"eo": None, "pe-s": "full", "pe-d-f": "full", "pe-d-s": "sub", "pc-s": "sub", "pc-f": "full"}
FRAMEWORK_MODES = tuple(PLAN_SCOPES)

_TEXT = {"type": "string"}
_ID = {"type": "integer", "minimum": 1}
_REFS = {"type": "array", "items": _ID}
_LIST = {"type": "array", "items": _TEXT}
_JUDGMENT = {
    "assessment": {**_TEXT, "description": "A brief assessment of the current evidence and active phase."},
    "evidence_refs": {**_REFS, "description": "Only use observation numbers visible in your request."},
}
_STAGE_FIELDS = {
    "stage_objective": {**_TEXT, "description": "A single observable sub-goal. Omit to retain the active stage."},
    "completion_condition": {**_TEXT, "description": "The observable evidence needed to establish completion."},
}
_FULL_PLAN = {"type": "array", "items": {
    "type": "object",
    "properties": {"id": _ID, **_STAGE_FIELDS},
    "required": ["id", "stage_objective", "completion_condition"],
}}


def _function(name, description, properties, required, handler):
    return FunctionTool(name, description, {"type": "object", "properties": properties, "required": required}, handler)


def _plan_request(description, handler):
    return _function("request_plan", description, {
        "reason": {**_TEXT, "description": "State why you need a plan and what relevant fact or condition changed."},
        "evidence_refs": _JUDGMENT["evidence_refs"],
    }, ["reason"], handler)


def _plan_schema(scope, *, pc, initial):
    plan = {"full_plan": _FULL_PLAN} if scope == "full" else _STAGE_FIELDS
    fields = {**_JUDGMENT, **plan}
    required = ["assessment"]
    if pc:
        if scope == "full":
            fields.update(current_subplan_id=_ID, revision_reason={
                **_TEXT, "description": "On later calls, required in the same JSON object when full_plan changes, "
                                        "including wording changes or added details. Provide a nonempty reason. "
                                        "Not required for the initial plan.",
            })
        fields.update(
            previous_stage_status={
                "type": "string", "enum": ["verified", "blocked", "replaced"],
                "description": "Classify the previous phase when switching; verified requires evidence.",
            },
            hypotheses=_LIST, remaining_work=_LIST,
        )
        if initial:
            required.extend([*plan, *(["current_subplan_id"] if scope == "full" else [])])
    else:
        if not initial:
            fields["keep"] = {"type": "boolean", "description": "Retain existing guidance; omit new plan fields."}
        if initial:
            required.extend(plan)
    return {"type": "object", "properties": fields, "required": required}


def _planner_json(event):
    response = event["response"]
    if response.get("finish_reason") == "length":
        raise ToolProtocolError("truncated_response")
    if response.get("tool_calls"):
        raise ToolProtocolError("unavailable_tool")
    try:
        fields = json.loads(response.get("text"))
    except (TypeError, json.JSONDecodeError) as error:
        raise ToolProtocolError("invalid_planner_json") from error
    if not isinstance(fields, dict):
        raise ToolProtocolError("invalid_planner_json")
    return fields


def _text(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ToolProtocolError(f"missing_{field}")
    return value.strip()


def _positive_id(value, field):
    if type(value) is not int or value < 1:
        raise ToolProtocolError(f"invalid_{field}")
    return value


def _stage(fields):
    return {name: _text(fields.get(name), name) for name in _STAGE_FIELDS}


def _full_plan(value):
    if not isinstance(value, list) or not value or any(not isinstance(item, dict) for item in value):
        raise ToolProtocolError("invalid_full_plan")
    result = [{"id": _positive_id(item.get("id"), "subplan_id"), **_stage(item)} for item in value]
    if len({item["id"] for item in result}) != len(result):
        raise ToolProtocolError("duplicate_subplan_id")
    return result


def _refs(fields, visible):
    refs = fields.get("evidence_refs", [])
    if not isinstance(refs, list) or any(type(ref) is not int or ref not in visible for ref in refs):
        raise ToolProtocolError("unknown_evidence_ref")
    return list(dict.fromkeys(refs))


def _list(fields, name, previous):
    value = fields.get(name, previous)
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ToolProtocolError(f"invalid_{name}")
    return value


def _numbered_plan(plan):
    return "\n".join(
        f"- {item['id']}. {item['stage_objective']} (done when: {item['completion_condition']})" for item in plan
    )


class FrameworkRun:
    """Keep one run's planning, evidence and execution state."""

    def __init__(self, *, mode, env, planner, executor, goal, workspace_id, executor_limit,
                 save, benchmark, external_verifier, context_window=None):
        self.mode = mode
        self.scope = PLAN_SCOPES[mode]
        self.pc = mode.startswith("pc")
        self.benchmark = benchmark
        self.prompts = load_framework_prompts(mode, benchmark)
        self.plan_request_description = self.prompts.PLAN_REQUEST_DESCRIPTION if mode.startswith("pe-d") else None
        self.external_verifier = external_verifier
        self.goal = goal
        self.workspace_id = workspace_id
        self.limit = executor_limit
        self.plan_version = 0
        self.stage_number = 0
        self.request_id = f"{workspace_id}:task"
        self.record = {
            "mode": mode, "framework_family": mode[:4] if mode.startswith("pe-d") else "pc" if self.pc else mode,
            "plan_scope": self.scope, "protocol_version": FRAMEWORK_PROTOCOL, "workspace_id": workspace_id,
            "goal": goal, "budgets": {"executor_limit": executor_limit},
            "events": [], "outcome": None,
        }
        self.log = EventLog(self.record["events"], context=lambda: {
            "workspace_id": self.workspace_id, "request_id": self.request_id, "plan_version": self.plan_version,
        }, save=lambda: save(self.record))
        self.session = RolloutSession(env, {"planner": planner, "executor": executor}, log=self.log,
                                      count_dispatched=True)
        instruction_path = getattr(env, "instruction_path", None)
        self.instruction = (load_executor_instruction(benchmark, instruction_path, mode=mode)
                            if instruction_path is not None else self.prompts.EXECUTOR_PROMPT)
        self.context_windows = {role: ContextWindow(**(context_window or {})) for role in ("planner", "executor")}
        self.context_metadata = {}
        self.record["context_window"] = {"max_input_tokens": self.context_windows["executor"].max_input_tokens}
        self.observations = {}
        self.last_feedback = None
        self.verified_stages = []
        self.stage = None
        self.plan = None
        self.revision_reason = None
        self.hypotheses = []
        self.remaining_work = []
        self.steps = 0
        self.no_action_rounds = 0
        self.stop_reason = None

    @property
    def state(self):
        return self.session.state

    def _initialize(self):
        self.session.reset()
        initial = self.log.emit("initial_observation", observation=self.session.env.initial_observation,
                                observation_id=1)
        self.observations[1] = initial
        if self.mode == "eo":
            self._execution_request()

    def _goal(self):
        return f"Task goal: {self.goal}"

    def _execution_request(self, refs=()):
        self.log.emit(
            "execution_request", goal=self.goal, evidence_refs=list(refs),
            stage_objective=self.stage["stage_objective"] if self.stage else None,
            completion_condition=self.stage["completion_condition"] if self.stage else None,
            current_subplan_id=self.stage.get("id") if self.stage else None,
            plan=self.plan if not self.pc else None,
        )

    def _stage_update(self, stage):
        if self.stage == stage:
            return False
        self.stage = stage
        self.stage_number += 1
        self.request_id = f"{self.workspace_id}:stage-{self.stage_number}"
        return True

    def _observation(self, event):
        prefix = f"Observation #{event['observation_id']}"
        if event.get("action"):
            prefix += f" after {event['action']}"
        return f"{prefix}: {event['observation']}"

    @staticmethod
    def _executor_message(event):
        response = event["response"]
        message = {"role": "assistant", "content": response.get("text")}
        if response.get("tool_calls"):
            message["tool_calls"] = response["tool_calls"]
        elif message["content"] is None:
            message["content"] = ""
        return message

    def _history_units(self):
        units = [{"record_id": self.observations[1]["event_id"], "events": [self.observations[1]]}]
        by_call = {}
        for event in self.log.events:
            if event["type"] == "model_call" and event.get("role") == "executor" and event.get("response"):
                unit = {"record_id": event["event_id"], "events": [event]}
                by_call[event["event_id"]] = unit
                units.append(unit)
            elif event["type"] in {"tool_event", "model_tool_result"}:
                by_call[event["model_event_id"]]["events"].append(event)
        return units

    def _history_record(self, unit, *, planner):
        lines, refs = [], []
        for event in unit["events"]:
            kind = event["type"]
            if kind == "model_call":
                response = event["response"]
                if response.get("text"):
                    lines.append(f"Executor reply:\n{response['text']}")
                for call in response.get("tool_calls", []):
                    function = call["function"]
                    lines.append(f"Executor planning request: {function['name']}({function['arguments']})")
            elif kind in {"initial_observation", "tool_event"}:
                if "observation_id" in event:
                    refs.append(event["observation_id"])
                    lines.append(self._observation(event))
                else:
                    lines.append(f"Local action feedback: {event['observation']}")
            elif kind == "model_tool_result" and not planner:
                lines.append(f"Planning tool result:\n{event['content']}")
        return ContextRecord(unit["record_id"], "\n\n".join(lines), tuple(refs))

    def _history_context(self, role, blocks, *, trailing_blocks=(), required=(), planning=False, actions=None):
        units = self._history_units()
        records = [self._history_record(unit, planner=role == "planner") for unit in units]
        latest_ref = max(self.observations)
        protected_refs = {latest_ref, *required}
        protected = {record.record_id for record in records if protected_refs.intersection(record.observation_ids)}
        paired, paired_id = [], None
        latest = units[-1]
        protected.add(latest["record_id"])
        call = latest["events"][0]
        if call["type"] == "model_call" and call["response"].get("tool_calls"):
            if role == "executor":
                results = [event for event in latest["events"] if event["type"] == "model_tool_result"]
                paired = [self._executor_message(call), *[
                    {"role": "tool", "tool_call_id": event["tool_call_id"], "content": event["content"]}
                    for event in results
                ]]
                paired_id = latest["record_id"]

        def render(selected):
            history = "\n\n".join(record.text for record in selected if record.record_id != paired_id)
            title = "Public interaction history:" if role == "planner" else "Interaction history:"
            content = "\n\n".join([*blocks, title + "\n" + history])
            if actions is not None:
                content = render_action_feedback(content, actions)
            content = "\n\n".join([content, *trailing_blocks])
            return [{"role": "user", "content": content}, *paired]

        options = {"tools": [_plan_request(self.plan_request_description, self._request_plan).schema]} if planning else {}
        try:
            messages, metadata, visible = self.context_windows[role].prepare(
                records, render, protected=protected, model_options=options,
            )
        except ContextWindowExceeded as error:
            self.log.emit("context_window_error", role=role, error=type(error).__name__,
                          context_window=error.metadata, messages=error.messages, dispatched=False)
            raise
        self.context_metadata[role] = metadata
        return messages, visible

    def _executor_context(self, *, planning):
        guidance = []
        if self.stage:
            guidance.append(f"Active sub-plan: {self.stage['stage_objective']}\n"
                            f"Completion condition: {self.stage['completion_condition']}")
        elif self.plan:
            guidance.append(f"Current advisory plan:\n{_numbered_plan(self.plan)}")
        get_actions = getattr(self.session.env, "get_available_actions", None)
        actions = get_actions() if get_actions else None
        return self._history_context("executor", [self.instruction, self._goal()], trailing_blocks=guidance,
                                     planning=planning, actions=actions)

    def _planner_context(self, prompt, *, reason=None, required=()):
        guidance = [prompt]
        if self.plan:
            guidance.append(f"Current full-plan:\n{_numbered_plan(self.plan)}")
        if self.stage:
            cursor = f" #{self.stage['id']}" if "id" in self.stage else ""
            guidance.append(f"Active sub-plan{cursor}: {self.stage['stage_objective']}\n"
                            f"Completion condition: {self.stage['completion_condition']}")
        if self.revision_reason:
            guidance.append(f"Last route revision: {self.revision_reason}")
        if self.verified_stages:
            guidance.append("Verified phases:\n" + "\n".join(
                f"- {item['stage']['stage_objective']}\n"
                f"  Completion condition met: {item['stage']['completion_condition']} "
                f"(observations {', '.join(map(str, item['evidence_refs']))})"
                for item in self.verified_stages
            ))
        if self.hypotheses:
            guidance.append("Unverified hypotheses:\n- " + "\n- ".join(self.hypotheses))
        if self.remaining_work:
            guidance.append("Estimated work remaining:\n- " + "\n- ".join(self.remaining_work))
        if reason:
            guidance.append(f"Trigger: {reason}")
        messages, visible = self._history_context(
            "planner", [self.prompts.PLANNER_PROMPT, self._goal()],
            trailing_blocks=guidance, required=required,
        )
        visible.update(ref for item in self.verified_stages for ref in item["evidence_refs"])
        return messages, visible

    async def _call_model(self, role, messages, **options):
        event = await self.session.call(role, messages, context_metadata=self.context_metadata[role], **options)
        self.context_windows[role].observe(event["context_window"], event["response"].get("usage"))
        self.log.flush()
        return event

    def _tool_result(self, event, tool, content):
        self.log.emit("model_tool_result", name=tool["function"]["name"], tool_call_id=tool["id"], content=content,
                      model_event_id=event["event_id"])

    def _planner_log(self, call, decision, summary, refs, *, phase, **fields):
        self.log.emit("planner_decision", decision=decision, assessment=summary, evidence_refs=refs,
                      planner_phase=phase, model_event_id=call["event_id"],
                      stage_objective=self.stage["stage_objective"] if self.stage else None,
                      current_subplan_id=self.stage.get("id") if self.stage else None,
                      verified_stages=self.verified_stages.copy(), **fields)

    def _no_action(self):
        self.no_action_rounds += 1
        if self.no_action_rounds > 1:
            raise ToolProtocolError("consecutive_no_action_rounds")

    async def _request_plan(self, event, tool, params, *, visible):
        if re.search(r"^Action:", event["response"].get("text") or "", flags=re.MULTILINE):
            raise ToolProtocolError("mixed_action_and_tool_call")
        reason = _text(params.get("reason"), "reason")
        refs = _refs(params, visible)
        self._no_action()
        guidance = await self._plan_pe(initial=False, reason=reason, required=refs)
        return self._tool_result(event, tool, guidance)

    async def _plan_pe(self, *, initial, reason=None, required=()):
        schema = _plan_schema(self.scope, pc=False, initial=initial)
        prompt = self.prompts.PLANNER_INITIAL_PROMPT if initial else self.prompts.PLANNER_MONITOR_PROMPT
        messages, visible = self._planner_context(
            f"{prompt}\n\n"
            + self.prompts.PLANNER_JSON_FORMAT.format(schema=json.dumps(schema, ensure_ascii=False)),
            reason=f"Executor requests planning: {reason}" if reason else "Initial planning before execution.",
            required=required,
        )
        planner = await self._call_model("planner", messages)
        choice = _planner_json(planner)
        summary = _text(choice.get("assessment"), "assessment")
        refs = _refs(choice, visible)
        keep = choice.get("keep", False)
        if type(keep) is not bool or (keep and initial):
            raise ToolProtocolError("invalid_keep")
        if keep and any(key in choice for key in ("full_plan", *_STAGE_FIELDS)):
            raise ToolProtocolError("conflicting_plan_delivery")
        changed = False
        if not keep:
            if self.scope == "full":
                plan = _full_plan(choice.get("full_plan"))
                changed = self.plan != plan
                self.plan = plan
            else:
                changed = self._stage_update(_stage(choice))
        if changed:
            self.plan_version += 1
        self._planner_log(planner, "keep" if keep else "guide", summary, refs,
                          phase="initial_planning" if initial else "execution_monitoring", reason=reason,
                          plan=self.plan, stage_changed=changed and self.scope == "sub")
        if changed:
            self._execution_request(refs)
        guidance = (_numbered_plan(self.plan) if self.plan else
                    f"{self.stage['stage_objective']}\nCompletion condition: {self.stage['completion_condition']}")
        return ("Retain current advisory guidance.\n" if keep else "Updated advisory guidance.\n") + guidance

    def _after_step(self, event):
        if event["dispatched"]:
            self.steps += 1
            self.no_action_rounds = 0
        if event["dispatched"] or (self.state.finished and event["valid"]):
            event["observation_id"] = len(self.observations) + 1
            self.observations[event["observation_id"]] = event
            self.log.flush()
        native_reason = self.state.terminate_reason
        if self.state.finished and native_reason == "max_error_steps":
            self.stop_reason = "environment_limit"
        elif self.state.finished and native_reason != "max_steps":
            self.stop_reason = "task_finish"
        elif self.steps >= self.limit or native_reason == "max_steps":
            self.stop_reason = "executor_budget"
        if event["dispatched"] or self.stop_reason:
            reason = self.stop_reason or "step_feedback"
            self.last_feedback = reason
            self.log.emit("execution_feedback", tool_event_refs=[event["event_id"]],
                          observed_changes=[{"event_id": event["event_id"],
                                             **({"observation_id": event["observation_id"]}
                                                if "observation_id" in event else {}),
                                             "observation": event["observation"]}],
                          return_reason=reason)
            return True
        self._no_action()
        return False

    async def _executor_step(self):
        while True:
            planning = self.mode.startswith("pe-d")
            messages, visible = self._executor_context(planning=planning)
            tools = [_plan_request(self.plan_request_description, partial(self._request_plan, visible=visible))] if planning else []
            options = {"tools": [tool.schema for tool in tools]} if tools else {}
            call = await self._call_model("executor", messages, **options)
            if call["response"].get("tool_calls"):
                if not planning:
                    raise ToolProtocolError("unavailable_tool")
                await invoke_tool(call, tools)
                continue
            event = await self.session.step(call=call)
            if self._after_step(event):
                return event

    def _pc_stage(self, params, *, initial):
        plan, reason = self.plan, self.revision_reason
        if self.scope == "full":
            if "full_plan" in params or initial:
                plan = _full_plan(params.get("full_plan"))
                if not initial and plan != self.plan:
                    reason = _text(params.get("revision_reason"), "revision_reason")
            cursor = params.get("current_subplan_id", self.stage.get("id") if self.stage else None)
            cursor = _positive_id(cursor, "current_subplan_id")
            stage = next((item for item in plan if item["id"] == cursor), None)
            if stage is None:
                raise ToolProtocolError("unknown_subplan_id")
        else:
            stage = _stage(params) if initial or any(key in params for key in _STAGE_FIELDS) else self.stage
        return stage, plan, reason

    async def _plan_pc(self, *, initial):
        prompt = self.prompts.PLANNER_INITIAL_PROMPT if initial else self.prompts.PLANNER_MONITOR_PROMPT
        schema = _plan_schema(self.scope, pc=True, initial=initial)
        messages, visible = self._planner_context(
            f"{prompt}\n\n"
            + self.prompts.PLANNER_JSON_FORMAT.format(schema=json.dumps(schema, ensure_ascii=False)),
            reason=self.last_feedback,
        )
        call = await self._call_model("planner", messages)
        params = _planner_json(call)
        summary = _text(params.get("assessment"), "assessment")
        refs = _refs(params, visible)
        stage, plan, reason = self._pc_stage(params, initial=initial)
        previous_stage = self.stage
        status = params.get("previous_stage_status")
        changed = stage != previous_stage
        if status is not None and status not in ("verified", "blocked", "replaced"):
            raise ToolProtocolError("invalid_previous_stage_status")
        if status == "verified" and (not refs or not previous_stage or not changed):
            raise ToolProtocolError("unverified_stage_transition")
        hypotheses = _list(params, "hypotheses", self.hypotheses)
        remaining = _list(params, "remaining_work", self.remaining_work)
        if previous_stage and changed:
            status = status or "replaced"
            closure = {"status": status, "stage": previous_stage, "assessment": summary, "evidence_refs": refs}
            self.log.emit("stage_result", **closure)
            if status == "verified":
                self.verified_stages.append({"stage": previous_stage, "evidence_refs": refs})
        revised = plan != self.plan
        discarded_stages = []
        if previous_stage and changed and params.get("previous_stage_status") in {"blocked", "replaced"}:
            if self.scope == "full":
                active_index = next(index for index, item in enumerate(self.plan)
                                    if item["id"] == previous_stage["id"])
                verified_stages = [item["stage"] for item in self.verified_stages]
                discarded_stages = [item.copy() for item in self.plan[active_index:]
                                    if item not in plan and item not in verified_stages]
            else:
                discarded_stages = [previous_stage.copy()]
        self.plan, self.revision_reason = plan, reason
        self.hypotheses, self.remaining_work = hypotheses, remaining
        self._stage_update(stage)
        if revised or (changed and self.scope == "sub"):
            self.plan_version += 1
        choice = "delegate" if initial else "revise" if revised else "advance" if changed else "keep"
        self._planner_log(call, choice, summary, refs,
                          phase="initial_planning" if initial else "execution_monitoring",
                          plan=self.plan, stage_changed=changed,
                          revision_reason=reason, previous_stage_status=status, discarded_stages=discarded_stages)
        if changed:
            self._execution_request(refs)

    async def run(self):
        try:
            self._initialize()
            if self.pc:
                await self._plan_pc(initial=True)
                while self.stop_reason is None:
                    await self._executor_step()
                    if self.stop_reason is None:
                        await self._plan_pc(initial=False)
            else:
                if self.mode != "eo":
                    await self._plan_pe(initial=True)
                while self.stop_reason is None:
                    await self._executor_step()
        except ToolProtocolError as error:
            self.stop_reason = "protocol_error"
            self.log.emit("decision_error", error=_error_name(error))
        except Exception as error:
            self.stop_reason = "runtime_error"
            self.log.emit("runtime_error", error=_error_name(error))
        self.steps += sum(event.get("dispatched") is True for event in self.log.events if event["type"] == "tool_error")
        self.log.emit("stop", reason=self.stop_reason, attempts=self.session.attempts.copy(),
                      real_environment_steps=self.steps)
        if not self.external_verifier:
            scored = self.stop_reason not in {"runtime_error", "protocol_error"}
            self.record["outcome"] = {
                "reason": self.stop_reason, "success": self.state.success if scored else None,
                "reward": self.state.reward if scored else None,
            }
            self.log.emit("verifier", **self.record["outcome"])
        return self.record


def _error_name(error):
    return str(error) if isinstance(error, ToolProtocolError) else type(error).__name__
