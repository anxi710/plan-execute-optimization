"""Adapt the official WebShop text simulator to Executor rollouts."""

import random
import re
from contextlib import contextmanager
from pathlib import Path

from .base import ActionResult, BaseEnv
from ..prompts import load_executor_instruction, resolve_executor_instruction_path
from ..utils.config import DEFAULT_CONFIG


WEBSHOP_ACTION = re.compile(r"(search|click)\[([^\[\]]+)\]")
INTERNAL_SEARCH_PREFIXES = {"<r>", "<a>", "<c>", "<q>"}


def webshop_settings(config=DEFAULT_CONFIG):
    settings = config["environments"]["webshop"]
    return {
        "instruction_path": resolve_executor_instruction_path("webshop", config),
        "max_steps": settings["max_steps"],
    }


@contextmanager
def open_webshop_backend(config=DEFAULT_CONFIG):
    """Open a text-only WebShop simulator from the installed upstream checkout."""
    from web_agent_site.envs import WebAgentTextEnv

    settings = config["environments"]["webshop"]
    options = {
        "observation_mode": "text",
        "num_products": settings["num_products"],
        "human_goals": settings["human_goals"],
    }
    if settings["catalog_path"] is not None:
        options["file_path"] = str(Path(settings["catalog_path"]).resolve(strict=True))
    random_state = random.getstate()
    try:
        random.seed(settings["catalog_seed"])
        env = WebAgentTextEnv(**options)
    finally:
        random.setstate(random_state)
    try:
        yield env
    finally:
        env.close()


class WebShopEnv(BaseEnv):
    """Use fixed goal indices and score the native purchase result."""

    def __init__(self, task, env, *, instruction_path, max_steps):
        self.task = task
        self.instruction_path = instruction_path
        self.env = env
        super().__init__(
            observation=task.observation,
            instruction=load_executor_instruction("webshop", instruction_path), max_steps=max_steps,
        )

    def reset(self):
        observation, _ = self.env.reset(session=self.task.session)
        if self.env.get_instruction_text().split() != self.task.observation.split():
            raise ValueError(f"WebShop goal differs for task {self.task.task_id}")
        self.available = self.env.get_available_actions()
        self._initial_observation = f"{self.task.observation}\n\nObservation: {observation}"
        return super().reset()

    def get_available_actions(self):
        actions = ["search[keywords]"] if self.available["has_search_bar"] else []
        actions.extend(f"click[{label}]" for label in self.available["clickables"] if label != "search")
        return actions

    def execute_action(self, action):
        match = WEBSHOP_ACTION.fullmatch(action)
        if match is None or not (target := match[2].strip()):
            return ActionResult("Choose one action from the current environment actions.", self.state.reward, False,
                                dispatched=False)
        verb = match[1]
        if verb == "search":
            allowed = self.available["has_search_bar"] and target.split()[0].lower() not in INTERNAL_SEARCH_PREFIXES
        else:
            allowed = target.lower() != "search" and target.lower() in self.available["clickables"]
        if not allowed:
            return ActionResult("That action is not available.", self.state.reward, False, dispatched=False)
        observation, reward, done, _ = self.dispatch(self.env.step, f"{verb}[{target}]")
        if not done:
            self.available = self.env.get_available_actions()
        return ActionResult(observation, float(reward), True, done=done, success=done and reward >= 1.0)
