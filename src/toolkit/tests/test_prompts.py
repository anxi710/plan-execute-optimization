import unittest

from toolkit.prompt.planner.templates import render_planner_prompt
from toolkit.prompt.plans import extract_plan


class PlannerPromptTest(unittest.TestCase):
    def test_shared_templates_accept_a_task_and_request_a_plan(self):
        task = "Find the object and complete the goal."
        actions = {
            "alfworld": "go to {recep}", "sciworld": "teleport to LOC", "webshop": "search by keywords",
        }
        for benchmark, action in actions.items():
            with self.subTest(benchmark=benchmark):
                prompt = render_planner_prompt(benchmark, task)
                self.assertIn(f"{task}\n</task>", prompt)
                self.assertIn(action, prompt)
                self.assertIn("<plan>\nStep 1:", prompt)
                self.assertNotIn("<route>", prompt)

    def test_plan_tag_and_legacy_text_are_parsed(self):
        self.assertEqual(extract_plan("<PLAN>\nStep 1: Find the object.\n</PLAN>"),
                         "Step 1: Find the object.")
        self.assertEqual(extract_plan("  Step 1: Find the object.  "), "Step 1: Find the object.")
