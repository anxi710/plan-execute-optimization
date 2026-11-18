import tempfile
import unittest
from functools import partial
from pathlib import Path
from unittest.mock import Mock

from toolkit.envs.alfworld_env import AlfWorldEnv, alfworld_settings
from toolkit.envs.sciworld_env import SciWorldEnv, sciworld_settings
from toolkit.envs.webshop_env import WebShopEnv, webshop_settings
from toolkit.tasks.alfworld import AlfWorldTask
from toolkit.tasks.sciworld import SciWorldTask
from toolkit.tasks.webshop import WebShopTask
from toolkit.utils.config import SOURCE_ROOT, resolve_config


class ExecutorTemplateTest(unittest.TestCase):
    def test_default_and_custom_instructions_preserve_conversation_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "max_steps.json").write_text('{"conductivity": 3}', encoding="utf-8")
            custom_path = root / "custom.txt"
            custom_path.write_bytes("  指令 {obj}\r\nSecond line  \r\n".encode("utf-8"))

            plan = "Check the {object}.\nThen stop."
            sci_backend = Mock()
            sci_backend.reset.return_value = ("Lab", {"taskDesc": "Task Description: Test conductivity", "score": 0})
            shop_backend = Mock()
            shop_backend.reset.return_value = ("Store", None)
            shop_backend.get_instruction_text.return_value = "Find a bag"
            shop_backend.get_available_actions.return_value = {"has_search_bar": True, "clickables": ["search"]}
            adapters = (
                ("alfworld", alfworld_settings, partial(AlfWorldEnv, AlfWorldTask(1, None, "Room", "game", plan)),
                 "Room"),
                ("sciworld", sciworld_settings,
                 partial(SciWorldEnv, SciWorldTask("task_4", "conductivity", 4, "Test conductivity", root, plan),
                         sci_backend), "Test conductivity\n\nObservation: Lab"),
                ("webshop", webshop_settings, partial(WebShopEnv, WebShopTask("bag", 7, "Find a bag", plan),
                                                      shop_backend),
                 "Find a bag\n\nObservation: Store\nAvailable actions: search[keywords]"),
            )
            suffix = f"\n\nThis plan may be helpful for you to complete the task:\n{plan}"
            feedback_text = "Observation: Invalid format. Supply one nonempty 'Action: ...' line."
            for benchmark, settings, make_env, initial in adapters:
                default_path = SOURCE_ROOT / f"toolkit/prompt/executor/instructions/{benchmark}_inst.txt"
                custom_config = resolve_config({"environments": {benchmark: {"instruction_path": str(custom_path)}}})
                for path, instruction, options in (
                    (default_path, default_path.read_text(encoding="utf-8"), settings()),
                    (custom_path, "  指令 {obj}\nSecond line  \n", settings(custom_config)),
                ):
                    for placement in ("query", "observation", "thought"):
                        with self.subTest(benchmark=benchmark, path=path.name, placement=placement):
                            self.assertEqual(options["instruction_path"], str(path.resolve()))
                            env = make_env(plan_placement=placement, **options)
                            prompt, state = env.reset()
                            expected_prompt = f"{instruction}\n\n{initial}"
                            if placement == "query":
                                expected_prompt += suffix
                            self.assertEqual(prompt, expected_prompt)
                            self.assertEqual(state.history, [{"role": "user", "content": expected_prompt}])

                            feedback, state = env.step("Missing the action")
                            expected_feedback = feedback_text + (suffix if placement == "observation" else "")
                            self.assertEqual(feedback, expected_feedback)
                            self.assertEqual(state.history[-1], {"role": "user", "content": expected_feedback})
                            self.assertEqual(state.action_trace[-1]["observation"], feedback_text)
