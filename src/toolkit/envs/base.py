"""Shared execution state and prompt handling for benchmark environments."""

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass

from ..prompts import render_action_feedback, render_executor_prompt
from ..rollout.state import State
from ..utils.config import DEFAULT_CONFIG


@dataclass(frozen=True)
class ActionResult:
    observation: str
    reward: float | None
    valid: bool
    done: bool = False
    success: bool = False


class BaseEnv(ABC):
    """Manage an Executor conversation for one already loaded task."""

    def __init__(self, *, observation, instruction,
                 max_steps=DEFAULT_CONFIG["environments"]["default_max_steps"]):
        self._initial_observation = observation
        self.instruction = instruction
        self.max_steps = max_steps

    @property
    def initial_observation(self):
        """Return the public task and initial observation prepared by the adapter."""
        return self._initial_observation

    def reset(self):
        self.state = State(reward=0)
        observation, _ = self._executor_feedback(self._initial_observation)
        prompt = render_executor_prompt(self.instruction, observation)
        self.state.history = [{"role": "user", "content": prompt}]
        return prompt, self.state

    def get_available_actions(self):
        """Return native action candidates, or None for an open-ended interface."""
        return None

    def _executor_feedback(self, observation, *, terminal=False):
        actions = None if terminal else self.get_available_actions()
        feedback = observation if actions is None else render_action_feedback(observation, actions)
        return feedback, actions

    @staticmethod
    def parse_action(reply):
        actions = re.findall(r"^Action:[ \t]*(.*)$", reply.strip(), flags=re.MULTILINE)
        if len(actions) != 1 or not actions[0].strip():
            raise ValueError("Expected one nonempty Action line")
        return actions[0].strip()

    def step(self, reply):
        state = self.state
        state.history.append({"role": "assistant", "content": reply})
        action = None
        try:
            action = self.parse_action(reply)
        except ValueError:
            result = ActionResult("Invalid format. Supply one nonempty 'Action: ...' line.", state.reward, False)
        else:
            result = self.execute_action(action)
        state.reward = result.reward
        state.steps += 1
        observation = f"Observation: {result.observation}"
        feedback, actions = self._executor_feedback(observation, terminal=result.done)
        event = {"action": action, "observation": observation, "valid": result.valid}
        if actions is not None:
            event["available_actions"] = list(actions)
        state.action_trace.append(event)
        state.history.append({"role": "user", "content": feedback})
        if result.done:
            state.finished = True
            state.success = result.success
            state.terminate_reason = "success" if result.success else "environment_done"
        elif state.steps >= self.max_steps:
            state.finished = True
            state.terminate_reason = "max_steps"
        return feedback, state

    @abstractmethod
    def execute_action(self, action: str) -> ActionResult:
        """Advance the benchmark and report its outcome for this action."""
