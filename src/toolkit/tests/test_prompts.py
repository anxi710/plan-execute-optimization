import unittest

from toolkit.prompts import extract_plan, load_executor_instruction, render_planner_prompt


class PlannerPromptTest(unittest.TestCase):
    def test_planners_request_abstract_subgoals_without_command_catalogs(self):
        task = "Find the object and complete the goal."
        for benchmark in ("alfworld", "sciworld", "webshop", "terminalbench"):
            with self.subTest(benchmark=benchmark):
                prompt = render_planner_prompt(benchmark, task)
                self.assertIn(f"{task}\n</task>", prompt)
                self.assertIn("high-level global plan", prompt)
                self.assertIn("abstract subgoals", prompt)
                self.assertIn("Executor", prompt)
                self.assertIn("<plan>\nStep 1:", prompt)
                for command in ("go to {recep}", "take {obj}", "toggle {obj}", "open OBJ", "teleport to LOC",
                                "search[keywords]", "click[label]", "Action:"):
                    self.assertNotIn(command, prompt)
                self.assertNotIn("The available actions are:", prompt)

    def test_executors_use_current_environment_actions(self):
        for benchmark in ("alfworld", "sciworld", "webshop"):
            with self.subTest(benchmark=benchmark):
                prompt = load_executor_instruction(benchmark)
                self.assertIn("current Available actions supplied by the environment", prompt)
                self.assertIn("Action: <command>", prompt)
                self.assertIn("Thought is reasoning text, not an environment command", prompt)
                for command in ("go to {recep}", "toggle {obj}", "open OBJ", "teleport to LOC",
                                "search[keywords]", "click[label]"):
                    self.assertNotIn(command, prompt)

        terminal = load_executor_instruction("terminalbench")
        self.assertIn("Action: <one shell command>", terminal)
        self.assertIn("Action: finish", terminal)
        self.assertNotIn("Available actions", terminal)

    def test_plan_tag_and_untagged_text_are_parsed(self):
        self.assertEqual(extract_plan("<PLAN>\nStep 1: Find the object.\n</PLAN>"),
                         "Step 1: Find the object.")
        self.assertEqual(extract_plan("  Step 1: Find the object.  "), "Step 1: Find the object.")
