"""ALFWorld action and feedback adapter."""

import re

from .base import ActionResult, BaseEnv
from ..prompts import load_executor_instruction, resolve_executor_instruction_path
from ..utils.config import DEFAULT_CONFIG


def alfworld_settings(config=DEFAULT_CONFIG):
    settings = config["environments"]["alfworld"]
    return {
        "env_class": "AlfWorldEnv",
        "instruction_path": resolve_executor_instruction_path("alfworld", config),
        "max_steps": settings["max_steps"],
    }


class AlfWorldEnv(BaseEnv):
    """Translate Executor actions and ALFWorld's native feedback."""

    def __init__(self, task, *, instruction_path,
                 max_steps=DEFAULT_CONFIG["environments"]["default_max_steps"], **_):
        self.task = task
        self.available = None
        super().__init__(
            observation=task.observation,
            instruction=load_executor_instruction("alfworld", instruction_path),
            max_steps=max_steps,
        )

    def reset(self):
        if self.task.admissible_commands is None:
            raise ValueError("ALFWorld task has no native admissible commands from reset")
        self.available = self.task.admissible_commands.copy()
        return super().reset()

    def get_available_actions(self):
        if self.available is None:
            raise ValueError("Reset the ALFWorld adapter before reading its available actions")
        return self.available.copy()

    @staticmethod
    def parse_action(reply):
        action = BaseEnv.parse_action(reply)
        put = re.fullmatch(r"put\s+(.+?)\s+(?:in|on)\s+(.+)", action)
        return f"put {put[1]} in/on {put[2]}" if put else action

    def execute_action(self, action: str) -> ActionResult:
        observations, _, dones, info = self.task.env.step([action])
        self.available = info["admissible_commands"][0].copy()
        observation = observations[0]
        if observation.startswith("You arrive at loc "):
            observation = observation[observation.find(". ") + 2:]
        reward = float(info["won"][0])
        return ActionResult(
            observation=observation, reward=reward, valid=not observation.strip().startswith("Nothing happens."),
            done=bool(dones[0]), success=bool(reward),
        )
