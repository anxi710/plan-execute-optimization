"""Plan placement in Executor conversations."""

from dataclasses import dataclass


PLAN_HINT = "This plan may be helpful for you to complete the task:"
THOUGHT_PLAN_HINT = "This plan may be helpful to complete the task:"


@dataclass(frozen=True)
class PlanInjection:
    placement: str = "query"
    plan: str | None = None

    def __post_init__(self):
        if self.placement not in ("query", "observation", "thought"):
            raise ValueError(f"Unsupported plan placement: {self.placement}")

    def _append_plan(self, text):
        if not self.plan:
            return text
        return f"{text}\n\n{PLAN_HINT}\n{self.plan}"

    def initial_task(self, task_text):
        return self._append_plan(task_text) if self.placement == "query" else task_text

    def observation(self, observation_text):
        return self._append_plan(observation_text) if self.placement == "observation" else observation_text

    def _thought_prefix(self):
        if self.placement == "thought" and self.plan:
            return f"{THOUGHT_PLAN_HINT}\n{self.plan}\nThought: "
        return None

    def call_agent(self, agent, messages):
        prefix = self._thought_prefix()
        if prefix is not None:
            return agent.continue_assistant(messages, prefix)
        return agent(messages)

    async def async_call_agent(self, agent, messages):
        prefix = self._thought_prefix()
        if prefix is not None:
            return await agent.async_continue_assistant(messages, prefix)
        return await agent.async_call(messages)
