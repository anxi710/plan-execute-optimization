"""Control planning and delegation for EO, PE-S, PE-D, and PC."""

import json
import re

from toolkit.prompts import (
    DELEGATED_STAGE_TEMPLATE, PC_CONTROL_TEMPLATE, PC_TERMINAL_CONTROL_TEMPLATE,
    PE_D_CONTROL_TEMPLATE, PLAN_GUIDANCE_TEMPLATE, PLAN_HINT, PLANNER_CONTEXT_TEMPLATE,
    PLANNER_DECISION_TEMPLATE, PLANNER_TASK_REQUIREMENTS_TEMPLATE, extract_plan, render_planner_prompt,
)
from toolkit.rollout.log import EventLog
from toolkit.rollout.session import RolloutSession

from .runtime import FRAMEWORK_MODES, FRAMEWORK_PROTOCOL, FrameworkRun


MODES = ("eo", "pe-s", "pe-d", "pc")
DYNAMIC = ("pe-d", "pc")


class InvalidPlannerDecision(ValueError):
    """The model answered outside the active framework's decision protocol."""


def _parse_planner_decision(text, mode, evidence_ids, *, terminal):
    block = re.search(r"<decision>(.*?)</decision>", text, flags=re.DOTALL)
    if not block:
        raise InvalidPlannerDecision("missing_decision")
    try:
        decision = json.loads(block[1])
    except json.JSONDecodeError as error:
        raise InvalidPlannerDecision("invalid_decision_json") from error
    allowed = {"guide"} if mode == "pe-d" else ({"finish"} if terminal else {"delegate", "finish"})
    choice = decision.get("decision") if isinstance(decision, dict) else None
    if not isinstance(choice, str) or choice not in allowed:
        raise InvalidPlannerDecision("unsupported_decision")
    for key in ("hypotheses", "remaining_work"):
        values = decision.get(key)
        if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
            raise InvalidPlannerDecision(f"invalid_{key}")
    refs = decision.get("evidence_refs")
    if not isinstance(refs, list) or any(type(ref) is not int or ref not in evidence_ids for ref in refs):
        raise InvalidPlannerDecision("unknown_evidence_ref")
    if choice == "finish":
        return decision, None
    plan = extract_plan(text) if re.search(r"<plan>.*?</plan>", text, re.DOTALL | re.IGNORECASE) else None
    if not plan:
        raise InvalidPlannerDecision("missing_full_plan")
    if mode == "pc":
        stage = decision.get("stage_objective")
        if not isinstance(stage, str) or not stage.strip():
            raise InvalidPlannerDecision("missing_stage_objective")
        if not isinstance(decision.get("soft_guidance", ""), str):
            raise InvalidPlannerDecision("invalid_soft_guidance")
    return decision, plan


def _error_code(error):
    return error.args[0] if isinstance(error, InvalidPlannerDecision) else type(error).__name__


def _executor_usage(events):
    calls = [event for event in events if event["type"] == "model_call" and event["role"] == "executor"]
    tokens = {}
    reported = 0
    for call in calls:
        usage = (call["response"] or {}).get("usage")
        if usage is not None:
            reported += 1
            for name, value in usage.items():
                if type(value) is int:
                    tokens[name] = tokens.get(name, 0) + value
    return {"attempts": len(calls), "usage_responses": reported, "tokens": tokens}


class _FrameworkController:
    """Apply framework decisions while the rollout session advances execution."""

    def __init__(self, *, mode, env, planner, executor, goal, workspace_id,
                 executor_limit, planner_limit, return_every, save, benchmark, external_verifier):
        self.mode = mode
        self.benchmark = benchmark
        self.external_verifier = external_verifier
        self.goal = goal
        self.workspace_id = workspace_id
        self.budgets = {"executor_limit": executor_limit, "planner_limit": planner_limit,
                        "return_every": return_every}
        self.record = {"mode": mode, "workspace_id": workspace_id, "goal": goal,
                       "budgets": self.budgets, "events": [], "outcome": None}
        self.events = self.record["events"]
        self.plan_version = 0
        self.stage_number = 0
        self.request_id = None if mode == "pc" else f"{workspace_id}:task"
        self.planner_state = {"goal": goal, "observed_facts": [],
                              "evidence_refs": [], "hypotheses": [], "global_plan": None,
                              "remaining_work": [], "plan_version": 0}
        self.public_observations = {}
        self.last_feedback = None
        self.segment_start = 0
        self.log = EventLog(self.events, context=lambda: {
            "workspace_id": self.workspace_id, "request_id": self.request_id, "plan_version": self.plan_version,
        }, save=lambda: save(self.record))
        self.session = RolloutSession(env, {"planner": planner, "executor": executor}, log=self.log)
        self.attempts = self.session.attempts

    @property
    def state(self):
        return self.session.state

    def initialize_session(self):
        self.session.reset()
        self.initial_observation = self.session.env.initial_observation
        event = self.log.emit("initial_observation", observation=self.initial_observation)
        self.public_observations[event["event_id"]] = self.initial_observation

    def build_planner_messages(self, *, terminal):
        prompt = render_planner_prompt(self.benchmark, self.initial_observation)
        if self.mode == "pe-s":
            context = {"goal": self.goal}
            return [{"role": "user", "content": PLANNER_TASK_REQUIREMENTS_TEMPLATE.format(
                prompt=prompt, context=json.dumps(context),
            )}]
        control = PE_D_CONTROL_TEMPLATE if self.mode == "pe-d" else PC_CONTROL_TEMPLATE
        if terminal:
            control = PC_TERMINAL_CONTROL_TEMPLATE
        protocol = PLANNER_DECISION_TEMPLATE.format(control=control)
        planner_state = {key: self.planner_state[key] for key in (
            "goal", "global_plan", "hypotheses", "remaining_work", "evidence_refs",
        )}
        planner_state["observed_facts"] = [
            {"event_id": ref, "observation": observation} for ref, observation in self.public_observations.items()
        ]
        feedback = None
        if self.last_feedback is not None:
            tools = self.last_feedback["tools"]
            feedback = {
                "observed_changes": [
                    {"event_id": event["event_id"], "action": event["action"], "observation": event["observation"]}
                    for event in tools
                ],
                "executor_claims": [
                    {"event_id": event["event_id"], "text": event["executor_claims"]}
                    for event in tools if event["executor_claims"]
                ],
            }
        context = {"planner_state": planner_state, "feedback": feedback}
        return [{"role": "user", "content": PLANNER_CONTEXT_TEMPLATE.format(
            prompt=prompt, protocol=protocol, context=json.dumps(context, ensure_ascii=False),
        )}]

    async def request_planner_decision(self, *, terminal=False):
        self.planner_state = {**self.planner_state, "observed_facts": [
            {"event_id": ref, "observation": observation} for ref, observation in self.public_observations.items()
        ]}
        call = await self.session.call("planner", self.build_planner_messages(terminal=terminal))
        reply = call["response"]
        text = reply.get("text")
        if reply.get("finish_reason") == "length":
            raise InvalidPlannerDecision("truncated_plan")
        if not isinstance(text, str) or not text.strip():
            raise InvalidPlannerDecision("empty_reply")
        if self.mode == "pe-s":
            plan = extract_plan(text)
            if not plan:
                raise InvalidPlannerDecision("empty_plan")
            decision = {"decision": "guide", "hypotheses": [], "remaining_work": [], "evidence_refs": []}
        else:
            decision, plan = _parse_planner_decision(text, self.mode, self.public_observations, terminal=terminal)
        choice = decision["decision"]
        prior_request = self.request_id
        stage = decision["stage_objective"].strip() if choice == "delegate" else None
        guidance = decision.get("soft_guidance", "").strip() if choice == "delegate" else plan
        if plan is not None:
            self.plan_version += 1
            self.planner_state = {**self.planner_state, "global_plan": plan, "plan_version": self.plan_version}
        refs = list(dict.fromkeys(decision["evidence_refs"]))
        self.planner_state = {**self.planner_state, "evidence_refs": refs, "hypotheses": decision["hypotheses"],
                              "remaining_work": decision["remaining_work"]}
        if choice == "delegate":
            self.stage_number += 1
            self.request_id = f"{self.workspace_id}:stage-{self.stage_number}"
        self.log.emit("planner_decision", decision=choice, planner_state=self.planner_state, stage_objective=stage,
                   soft_guidance=guidance, evidence_refs=refs, model_event_id=call["event_id"],
                   prior_request_id=prior_request)
        if choice != "finish":
            self.issue_execution_request(stage, guidance, refs)
        return choice

    def issue_execution_request(self, stage=None, guidance=None, refs=()):
        if not self.request_id:
            raise RuntimeError("Executor scope has no request ID")
        self.log.emit("execution_request", goal=self.goal, stage_objective=stage,
                   soft_guidance=guidance, evidence_refs=list(refs))
        if stage is not None:
            request = {"goal": self.goal, "stage_objective": stage,
                       "soft_guidance": guidance, "evidence": [
                           {"event_id": ref, "observation": self.public_observations[ref]} for ref in refs
                       ]}
            directive = DELEGATED_STAGE_TEMPLATE.format(request=json.dumps(request, ensure_ascii=False))
        elif guidance:
            directive = PLAN_GUIDANCE_TEMPLATE.format(plan_hint=PLAN_HINT, guidance=guidance)
        else:
            return
        self.state.history.append({"role": "user", "content": directive})

    def record_execution_feedback(self, reason):
        segment = self.events[self.segment_start:]
        tools = [event for event in segment if event["type"] == "tool_event"]
        data = {"tool_event_refs": [event["event_id"] for event in tools], "executor_claims": [
            {"event_id": event["event_id"], "text": event["executor_claims"]} for event in tools
            if event["executor_claims"]
        ], "observed_changes": [{"event_id": event["event_id"], "observation": event["observation"]} for event in tools],
            "artifact_refs": [], "usage": _executor_usage(segment), "return_reason": reason}
        self.last_feedback = {"tools": tools}
        self.log.emit("execution_feedback", **data)
        self.segment_start = len(self.events)

    async def control_execution(self):
        self.initialize_session()
        if self.mode == "eo":
            self.issue_execution_request()
        elif await self.request_planner_decision() == "finish":
            return "planner_finish"
        return await self.session.run(after_step=self.on_executor_step) or "task_finish"

    async def on_executor_step(self, event):
        self.public_observations[event["event_id"]] = event["observation"]
        if self.state.finished and self.state.terminate_reason == "max_error_steps":
            self.record_execution_feedback("environment_limit")
            return "environment_limit"
        if self.state.finished and self.state.terminate_reason != "max_steps":
            self.record_execution_feedback("task_finish")
            if self.mode == "pc" and self.attempts["planner"] < self.budgets["planner_limit"]:
                try:
                    await self.request_planner_decision(terminal=True)
                except Exception as error:
                    # An advisory response cannot reopen a terminated environment or change its score.
                    self.log.emit("decision_error", error=_error_code(error), return_reason="task_finish")
            return "task_finish"
        if self.attempts["executor"] >= self.budgets["executor_limit"]:
            self.record_execution_feedback("executor_budget")
            return "executor_budget"
        if self.attempts["executor"] % self.budgets["return_every"] == 0:
            self.record_execution_feedback("budget_pause")
            if self.mode in DYNAMIC:
                if self.attempts["planner"] >= self.budgets["planner_limit"]:
                    return "planner_budget"
                if await self.request_planner_decision() == "finish":
                    return "planner_finish"

    async def run(self):
        try:
            reason = await self.control_execution()
        except InvalidPlannerDecision as error:
            self.log.emit("decision_error", error=_error_code(error))
            reason = "protocol_error"
        except Exception as error:
            if self.request_id and self.state.history:
                self.record_execution_feedback("runtime_error")
            self.log.emit("runtime_error", error=_error_code(error))
            reason = "runtime_error"
        self.log.emit("stop", reason=reason, attempts=self.attempts.copy())
        if self.external_verifier:
            return self.record
        # The adapter's native verdict is read only once online control has stopped.
        assessable = reason != "runtime_error"
        self.record["outcome"] = {"reason": reason, "success": self.state.success if assessable else None,
                                  "reward": self.state.reward if assessable else None}
        self.log.emit("verifier", **self.record["outcome"])
        return self.record


async def run_framework(*, mode, env, planner, executor, goal, workspace_id,
                        executor_limit, save, planner_limit=None, return_every=None, benchmark="alfworld",
                        external_verifier=False, protocol_version=None):
    """Apply a framework's control policy over a persistent rollout session."""
    if type(executor_limit) is not int or executor_limit < 1:
        raise ValueError("executor_limit must be an integer of at least 1")
    if getattr(env, "max_steps", executor_limit) < executor_limit:
        raise ValueError("Environment limits must permit the requested Executor budget")
    options = dict(mode=mode, env=env, planner=planner, executor=executor, goal=goal,
                   workspace_id=workspace_id, executor_limit=executor_limit, save=save, benchmark=benchmark,
                   external_verifier=external_verifier)
    if protocol_version not in {None, FRAMEWORK_PROTOCOL}:
        raise ValueError(f"Unsupported execution protocol: {protocol_version}; historical records remain read-only")
    use_framework_protocol = (protocol_version == FRAMEWORK_PROTOCOL or mode not in MODES
                              or (mode in {"eo", "pe-s"} and planner_limit is None and return_every is None))
    if use_framework_protocol:
        if mode not in FRAMEWORK_MODES:
            raise ValueError(f"Unknown framework mode: {mode}")
        return await FrameworkRun(**options).run()
    if mode not in MODES:
        raise ValueError(f"Unknown framework: {mode}")
    for name, value, minimum in (("return_every", return_every, 1),
                                 ("planner_limit", planner_limit, int(mode != "eo"))):
        if type(value) is not int or value < minimum:
            raise ValueError(f"{name} must be an integer of at least {minimum}")
    return await _FrameworkController(**options, planner_limit=planner_limit, return_every=return_every).run()
