"""Run the four framework protocols over one persistent benchmark session."""

import asyncio
import json
import re
from datetime import datetime, timezone
from inspect import isawaitable
from time import perf_counter

from toolkit.prompt.executor.plan_injection import PLAN_HINT
from toolkit.prompt.planner.templates import render_planner_prompt
from toolkit.prompt.plans import extract_plan


MODES = ("eo", "pe-s", "pe-d", "pc")
DYNAMIC = ("pe-d", "pc")


class InvalidPlannerDecision(ValueError):
    """The model answered outside the active framework's decision protocol."""


def _planner_decision(text, mode, evidence_ids, *, terminal):
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


def _usage(events):
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


class _Trial:
    def __init__(self, *, mode, env, planner, executor, goal, constraints, workspace_id,
                 executor_limit, planner_limit, return_every, save, benchmark, external_verifier):
        self.env = env
        self.models = {"planner": planner, "executor": executor}
        self.save = save
        self.mode = mode
        self.benchmark = benchmark
        self.external_verifier = external_verifier
        self.goal = goal
        self.constraints = list(constraints)
        self.workspace_id = workspace_id
        self.budgets = {"executor_limit": executor_limit, "planner_limit": planner_limit,
                        "return_every": return_every}
        self.record = {"mode": mode, "workspace_id": workspace_id, "goal": goal, "constraints": self.constraints,
                       "budgets": self.budgets, "events": [], "outcome": None}
        self.events = self.record["events"]
        self.attempts = {"planner": 0, "executor": 0}
        self.plan_version = 0
        self.stage_number = 0
        self.request_id = None if mode == "pc" else f"{workspace_id}:task"
        self.state = None
        self.planner_state = {"goal": goal, "constraints": self.constraints, "observed_facts": [],
                              "evidence_refs": [], "hypotheses": [], "global_plan": None,
                              "remaining_work": [], "plan_version": 0}
        self.public_observations = {}
        self.last_feedback = None
        self.segment_start = 0

    def event(self, kind, **fields):
        event = {"event_id": len(self.events) + 1, "type": kind, "timestamp": datetime.now(timezone.utc).isoformat(),
                 "workspace_id": self.workspace_id, "request_id": self.request_id, "plan_version": self.plan_version,
                 **fields}
        self.events.append(event)
        self.save(self.record)
        return event

    async def call(self, role, messages):
        self.attempts[role] += 1
        messages = [message.copy() for message in messages]
        event = self.event("model_call", role=role, messages=messages, response=None, error=None,
                           status="pending", seconds=None)
        started = perf_counter()
        try:
            response = await self.models[role](messages)
        except (asyncio.CancelledError, KeyboardInterrupt) as error:
            event.update(status="interrupted", error=_error_code(error))
            raise
        except Exception as error:
            event.update(status="error", error=_error_code(error))
            raise
        else:
            event.update(status="complete", response=response)
            return event
        finally:
            event["seconds"] = perf_counter() - started
            self.save(self.record)

    def start(self):
        _, self.state = self.env.reset()
        if self.constraints:
            listed = "\n".join(f"- {constraint}" for constraint in self.constraints)
            self.state.history[0]["content"] += f"\n\nHard constraints for the entire task:\n{listed}"
        self.initial_observation = self.env.initial_observation
        event = self.event("initial_observation", observation=self.initial_observation)
        self.public_observations[event["event_id"]] = self.initial_observation

    def planner_messages(self, *, terminal):
        prompt = render_planner_prompt(self.benchmark, self.initial_observation)
        if self.mode == "pe-s":
            context = {"goal": self.goal, "hard_constraints": self.constraints}
            return [{"role": "user", "content": f"{prompt}\n\nTask requirements:\n{json.dumps(context)}"}]
        control = (
            'Set decision to "guide". The Executor owns the entire task. Give advisory full-plan guidance '
            'and leave stage_objective and soft_guidance out of the JSON object.'
            if self.mode == "pe-d" else
            'Set decision to "delegate" when work remains. In that same JSON object, the string '
            'stage_objective is required and soft_guidance is optional. The Executor receives only the current '
            'stage and chooses its own actions. Use this JSON shape for delegation, with a concrete objective '
            'that fits the stage budget and values grounded in the current task:\n'
            '{"decision":"delegate","stage_objective":"<next observable subgoal>","soft_guidance":"",'
            '"hypotheses":[],"remaining_work":[],"evidence_refs":[]}\n'
            'If you recommend ending the entire task, set decision to "finish" and omit stage_objective and soft_guidance.'
        )
        if terminal:
            control = ('The environment reached a native terminal state. Set decision to "finish", cite the relevant '
                       'public observations, and omit the stage fields and plan.')
        protocol = (
            "Keep a complete plan for all remaining task work in <plan>...</plan>. "
            "Separate unverified hypotheses from observations. Cite observations by their supplied event_id. "
            "After the plan, output <decision> and </decision> around a single JSON object. "
            'The common JSON fields are decision, hypotheses (array of strings), remaining_work (array of strings), '
            'and evidence_refs (array of event IDs). Add the decision-specific fields listed below. '
            'A finish decision can omit <plan>.\n'
            f"{control}"
        )
        context = {"planner_state": self.planner_state, "feedback": self.last_feedback,
                   "executor_attempts_remaining": self.budgets["executor_limit"] - self.attempts["executor"],
                   "planner_attempts_remaining_after_this_call": self.budgets["planner_limit"] - self.attempts["planner"] - 1,
                   "return_every": self.budgets["return_every"]}
        return [{"role": "user", "content": f"{prompt}\n\n{protocol}\n\n{json.dumps(context, ensure_ascii=False)}"}]

    async def plan(self, *, terminal=False):
        self.planner_state = {**self.planner_state, "observed_facts": [
            {"event_id": ref, "observation": observation} for ref, observation in self.public_observations.items()
        ]}
        call = await self.call("planner", self.planner_messages(terminal=terminal))
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
            decision, plan = _planner_decision(text, self.mode, self.public_observations, terminal=terminal)
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
        self.event("planner_decision", decision=choice, planner_state=self.planner_state, stage_objective=stage,
                   soft_guidance=guidance, evidence_refs=refs, model_event_id=call["event_id"],
                   prior_request_id=prior_request)
        if choice != "finish":
            self.issue_request(stage, guidance, refs)
        return choice

    def issue_request(self, stage=None, guidance=None, refs=()):
        if not self.request_id:
            raise RuntimeError("Executor scope has no request ID")
        self.event("execution_request", goal=self.goal, stage_objective=stage, hard_constraints=self.constraints,
                   soft_guidance=guidance, evidence_refs=list(refs))
        if stage is not None:
            turns = min(self.budgets["return_every"], self.budgets["executor_limit"] - self.attempts["executor"])
            request = {"goal": self.goal, "stage_objective": stage, "hard_constraints": self.constraints,
                       "soft_guidance": guidance, "evidence": [
                           {"event_id": ref, "observation": self.public_observations[ref]} for ref in refs
                       ]}
            directive = (
                f"Current delegated stage (up to {turns} actions). This supersedes prior stages. "
                "Choose actions autonomously within the stage objective, and keep the original task and hard "
                f"constraints. Treat soft guidance as advice.\n{json.dumps(request, ensure_ascii=False)}"
            )
        elif guidance:
            directive = f"Continue to own the entire original task. The latest guidance supersedes earlier guidance.\n{PLAN_HINT}\n{guidance}"
        else:
            return
        self.state.history.append({"role": "user", "content": directive})

    async def step(self):
        call = await self.call("executor", self.state.history)
        text = call["response"].get("text")
        text = text if isinstance(text, str) else ""
        claims = re.split(r"^Action:[ \t]*", text, maxsplit=1, flags=re.MULTILINE)[0].strip()
        started = perf_counter()
        try:
            result = self.env.step(text)
            _, self.state = await result if isawaitable(result) else result
        except Exception as error:
            self.event("tool_error", error=_error_code(error), model_event_id=call["event_id"],
                       seconds=perf_counter() - started)
            raise
        action = self.state.action_trace[-1]
        event = self.event("tool_event", action=action["action"], observation=action["observation"], valid=action["valid"],
                           dispatched=action["action"] is not None, model_event_id=call["event_id"],
                           executor_claims=claims, seconds=perf_counter() - started)
        self.public_observations[event["event_id"]] = event["observation"]

    def feedback(self, reason):
        segment = self.events[self.segment_start:]
        tools = [event for event in segment if event["type"] == "tool_event"]
        data = {"tool_event_refs": [event["event_id"] for event in tools], "executor_claims": [
            {"event_id": event["event_id"], "text": event["executor_claims"]} for event in tools
            if event["executor_claims"]
        ], "observed_changes": [{"event_id": event["event_id"], "observation": event["observation"]} for event in tools],
            "artifact_refs": [], "usage": _usage(segment), "return_reason": reason}
        self.last_feedback = self.event("execution_feedback", **data)
        self.segment_start = len(self.events)

    async def execute(self):
        self.start()
        if self.mode == "eo":
            self.issue_request()
        elif await self.plan() == "finish":
            return "planner_finish"
        while True:
            await self.step()
            if self.state.finished and self.state.terminate_reason == "max_error_steps":
                self.feedback("environment_limit")
                return "environment_limit"
            if self.state.finished and self.state.terminate_reason != "max_steps":
                self.feedback("task_finish")
                if self.mode == "pc" and self.attempts["planner"] < self.budgets["planner_limit"]:
                    try:
                        await self.plan(terminal=True)
                    except Exception as error:
                        # An advisory response cannot reopen a terminated environment or change its score.
                        self.event("decision_error", error=_error_code(error), return_reason="task_finish")
                return "task_finish"
            if self.attempts["executor"] >= self.budgets["executor_limit"]:
                self.feedback("executor_budget")
                return "executor_budget"
            if self.attempts["executor"] % self.budgets["return_every"] == 0:
                self.feedback("budget_pause")
                if self.mode in DYNAMIC:
                    if self.attempts["planner"] >= self.budgets["planner_limit"]:
                        return "planner_budget"
                    if await self.plan() == "finish":
                        return "planner_finish"

    async def run(self):
        try:
            reason = await self.execute()
        except InvalidPlannerDecision as error:
            self.event("decision_error", error=_error_code(error))
            reason = "protocol_error"
        except Exception as error:
            if self.request_id and self.state is not None:
                self.feedback("runtime_error")
            self.event("runtime_error", error=_error_code(error))
            reason = "runtime_error"
        self.event("stop", reason=reason, attempts=self.attempts.copy())
        if self.external_verifier:
            return self.record
        # The adapter's native verdict is read only once online control has stopped.
        assessable = reason != "runtime_error" and self.state is not None
        self.record["outcome"] = {"reason": reason, "success": self.state.success if assessable else None,
                                  "reward": self.state.reward if assessable else None}
        self.event("verifier", **self.record["outcome"])
        return self.record


async def run_trial(*, mode, env, planner, executor, goal, constraints, workspace_id,
                    executor_limit, planner_limit, return_every, save, benchmark="alfworld", external_verifier=False):
    """Execute one framework with fixed atomic turn boundaries."""
    if mode not in MODES:
        raise ValueError(f"Unknown framework: {mode}")
    for name, value, minimum in (("executor_limit", executor_limit, 1), ("return_every", return_every, 1),
                                 ("planner_limit", planner_limit, int(mode != "eo"))):
        if type(value) is not int or value < minimum:
            raise ValueError(f"{name} must be an integer of at least {minimum}")
    if getattr(env, "max_steps", executor_limit) < executor_limit:
        raise ValueError("Environment limits must permit the requested Executor budget")
    return await _Trial(mode=mode, env=env, planner=planner, executor=executor, goal=goal, constraints=constraints,
                        workspace_id=workspace_id, executor_limit=executor_limit, planner_limit=planner_limit,
                        return_every=return_every, save=save, benchmark=benchmark,
                        external_verifier=external_verifier).run()
