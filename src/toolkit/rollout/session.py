"""Advance a persistent execution session without choosing a framework."""

import asyncio
import re
from copy import deepcopy
from inspect import isawaitable
from time import perf_counter

from .log import EventLog
from .state import State


class RolloutSession:
    """Share model calls, environment turns, and resumable execution."""

    def __init__(self, env, models, *, log=None, plan_injection=None, count_dispatched=False):
        self.env = env
        if count_dispatched:
            self.env.count_dispatched = True
        self.models = models
        self.log = EventLog() if log is None else log
        self.plan_injection = plan_injection
        self.state = State()
        self.attempts = {role: 0 for role in models}
        self.phase = None

    def reset(self):
        prompt, self.state = self.env.reset()
        if self.plan_injection is not None:
            prompt = self.plan_injection.initial_task(prompt)
            self.state.history[0]["content"] = prompt
        return prompt, self.state

    async def call(self, role, messages, *, context_metadata=None, **model_options):
        self.phase = "request"
        self.attempts[role] += 1
        messages = deepcopy(messages)
        request_options = {"request_options": deepcopy(model_options)} if model_options else {}
        context = {"context_window": deepcopy(context_metadata)} if context_metadata is not None else {}
        event = self.log.emit("model_call", role=role, messages=messages, response=None, error=None,
                              status="pending", seconds=None, **context, **request_options)
        started = perf_counter()
        try:
            response = await self.models[role](messages, **model_options)
        except (asyncio.CancelledError, KeyboardInterrupt) as error:
            event.update(status="interrupted", error=type(error).__name__)
            raise
        except Exception as error:
            event.update(status="error", error=type(error).__name__)
            raise
        else:
            event.update(status="complete", response=response)
            self.phase = None
            return event
        finally:
            event["seconds"] = perf_counter() - started
            self.log.flush()

    async def step(self, messages=None, *, call=None):
        if call is None:
            call = await self.call("executor", self.state.history if messages is None else messages)
        text = call["response"].get("text")
        text = text if isinstance(text, str) else ""
        claims = re.split(r"^Action:[ \t]*", text, maxsplit=1, flags=re.MULTILINE)[0].strip()
        self.phase = "environment"
        started = perf_counter()
        try:
            result = self.env.step(text)
            observation, self.state = await result if isawaitable(result) else result
            if self.plan_injection is not None:
                self.state.history[-1]["content"] = self.plan_injection.observation(observation)
        except (Exception, asyncio.CancelledError, KeyboardInterrupt) as error:
            dispatched = getattr(self.env, "last_dispatched", None)
            self.log.emit("tool_error", error=type(error).__name__, model_event_id=call["event_id"],
                          dispatched=dispatched, result_unknown=dispatched is not False,
                          seconds=perf_counter() - started)
            raise
        self.phase = None
        action = self.state.action_trace[-1]
        return self.log.emit(
            "tool_event", action=action["action"], observation=action["observation"], valid=action["valid"],
            dispatched=action.get("dispatched", action["action"] is not None), model_event_id=call["event_id"],
            executor_claims=claims, seconds=perf_counter() - started,
            **({"available_actions": action["available_actions"]} if "available_actions" in action else {}),
        )

    async def run(self, *, after_step=None):
        """Run until the environment ends or the controller returns a pause/stop reason."""
        while not self.state.finished:
            event = await self.step()
            if after_step is not None:
                reason = after_step(event)
                reason = await reason if isawaitable(reason) else reason
                if reason is not None:
                    return reason
