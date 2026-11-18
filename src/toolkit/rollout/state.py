"""Serializable state for one rollout."""

from copy import deepcopy
from dataclasses import dataclass, field


@dataclass
class State:
    """One rollout's conversation, environment outcome, and action trace."""

    reward: float | None = None
    finished: bool = False
    success: bool = False
    terminate_reason: str | None = None
    error: str | None = None
    steps: int = 0
    incomplete: bool = False
    history: list[dict] = field(default_factory=list)
    action_trace: list[dict] = field(default_factory=list)

    def interrupt(self, code, error_type):
        self.finished = False
        self.incomplete = True
        self.success = False
        self.reward = None
        self.terminate_reason = f"executor_{code}"
        self.error = f"Executor interrupted: {code} ({error_type})"

    @classmethod
    def load_json(cls, data):
        final = data[-1]
        return cls(
            reward=final["reward"], finished=final["finished"], success=final["success"],
            terminate_reason=final["terminate_reason"], error=final["error"], steps=final["steps"],
            incomplete=final.get("incomplete", False), history=data[:-1], action_trace=final["action_trace"],
        )

    def to_dict(self):
        final = {
            "steps": self.steps, "reward": self.reward, "finished": self.finished,
            "success": self.success, "terminate_reason": self.terminate_reason, "error": self.error,
            "action_trace": deepcopy(self.action_trace),
        }
        if self.incomplete:
            final["incomplete"] = True
        return [*deepcopy(self.history), final]
