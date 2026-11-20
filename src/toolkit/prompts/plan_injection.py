"""Plan placement in Executor conversations."""

from dataclasses import dataclass

from .frameworks import PLAN_HINT, THOUGHT_PLAN_HINT


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

    @property
    def thought_prefix(self):
        if self.placement == "thought" and self.plan:
            return f"{THOUGHT_PLAN_HINT}\n{self.plan}\nThought: "
        return None
