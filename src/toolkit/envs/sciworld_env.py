"""ScienceWorld actions and feedback over the official Java backend."""

import json
from contextlib import contextmanager
from pathlib import Path

from .base import ActionResult, BaseEnv
from ..prompts import load_executor_instruction, resolve_executor_instruction_path
from ..utils.config import DEFAULT_CONFIG


DEFAULTS = DEFAULT_CONFIG["environments"]["sciworld"]


def sciworld_settings(config=DEFAULT_CONFIG):
    settings = config["environments"]["sciworld"]
    return {
        "instruction_path": resolve_executor_instruction_path("sciworld", config),
        "max_steps": settings.get("max_steps", DEFAULTS["max_steps"]),
        "max_error_steps": settings["max_error_steps"],
        "simplification": settings["simplification"],
    }


@contextmanager
def open_sciworld_backend(jar_path=DEFAULTS["jar_path"], *,
                          server_step_limit=DEFAULTS["server_step_limit"]):
    """Use the bundled ScienceWorld JAR unless the caller provides one."""
    jar = Path(jar_path).resolve() if jar_path is not None else None
    if jar is not None and not jar.is_file():
        raise FileNotFoundError(jar)
    if type(server_step_limit) is not int or server_step_limit < 1:
        raise ValueError("ScienceWorld server_step_limit must be positive")
    from scienceworld import ScienceWorldEnv

    env = ScienceWorldEnv(serverPath=str(jar) if jar is not None else None,
                          envStepLimit=server_step_limit)
    try:
        yield env
    finally:
        env.close()


class SciWorldEnv(BaseEnv):
    """Apply ScienceWorld scoring, task identity checks and step limits."""

    def __init__(self, task, env, *, instruction_path,
                 max_steps=DEFAULTS["max_steps"],
                 max_error_steps=DEFAULTS["max_error_steps"], simplification=DEFAULTS["simplification"]):
        if max_error_steps < 1:
            raise ValueError("ScienceWorld max_error_steps must be positive")
        self.task = task
        self.env = env
        self.max_error_steps = max_error_steps
        self.simplification = simplification
        if max_steps is None:
            budgets = json.loads((task.data_path / "max_steps.json").read_text(encoding="utf-8"))
            max_steps = budgets[task.sub_task_name]
        if type(max_steps) is not int or max_steps < 1:
            raise ValueError("ScienceWorld max_steps must be a positive integer")
        super().__init__(
            observation=task.observation,
            instruction=load_executor_instruction("sciworld", instruction_path),
            max_steps=max_steps,
        )

    def reset(self):
        self.env.load(self.task.sub_task_name, self.task.variation_idx,
                      simplificationStr=self.simplification, generateGoldPath=False)
        observation, info = self.env.reset()
        description = info["taskDesc"].removeprefix("Task Description:").strip()
        expected = self.task.observation.removeprefix("Task Description:").strip()
        if description.split() != expected.split():
            raise ValueError(f"ScienceWorld task description differs for task {self.task.task_id}")
        self._initial_observation = f"{description}\n\nObservation: {observation}"
        self._cache_available_actions(info)
        self.error_steps = 0
        observation, state = super().reset()
        state.reward = info["score"] / 100.0
        return observation, state

    def execute_action(self, action):
        observation, _, done, info = self.env.step(action)
        self._cache_available_actions(info)
        reward = info["score"] / 100.0
        return ActionResult(
            observation=observation, reward=reward,
            valid="No known action matches that input" not in observation,
            done=done, success=reward >= 1.0,
        )

    def _cache_available_actions(self, info):
        actions = info["valid"]
        if not isinstance(actions, list) or any(not isinstance(action, str) for action in actions):
            raise ValueError("ScienceWorld valid actions must be a list of strings")
        self.available_actions = actions.copy()

    def get_available_actions(self):
        return self.available_actions

    def step(self, reply):
        feedback, state = super().step(reply)
        self.error_steps = 0 if state.action_trace[-1]["valid"] else self.error_steps + 1
        if self.error_steps >= self.max_error_steps and not state.finished:
            state.finished = True
            state.terminate_reason = "max_error_steps"
        return feedback, state
