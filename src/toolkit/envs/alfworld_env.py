"""ALFWorld action and feedback adapter."""

import re

from .base import ActionResult, BaseEnv
from ..prompt.executor.template import load_executor_instruction, resolve_executor_instruction_path
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

    def __init__(self, task, *, plan_placement, instruction_path,
                 max_steps=DEFAULT_CONFIG["environments"]["default_max_steps"], **_):
        self.task = task
        super().__init__(
            observation=task.observation, plan=task.plan, plan_placement=plan_placement,
            instruction=load_executor_instruction(instruction_path),
            max_steps=max_steps,
        )

    @staticmethod
    def parse_action(reply):
        action = BaseEnv.parse_action(reply)
        put = re.fullmatch(r"put\s+(.+?)\s+(?:in|on)\s+(.+)", action)
        return f"put {put[1]} in/on {put[2]}" if put else action

    def execute_action(self, action: str) -> ActionResult:
        observations, _, dones, info = self.task.env.step([action])
        observation = observations[0]
        if observation.startswith("You arrive at loc "):
            observation = observation[observation.find(". ") + 2:]
        reward = float(info["won"][0])
        return ActionResult(
            observation=observation, reward=reward, valid=not observation.strip().startswith("Nothing happens."),
            done=bool(dones[0]), success=bool(reward),
        )
