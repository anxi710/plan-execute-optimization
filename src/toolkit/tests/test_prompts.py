import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from toolkit.prompts import extract_plan, load_executor_instruction, load_framework_prompts, render_planner_prompt


class PlannerPromptTest(unittest.TestCase):
    def test_framework_and_benchmark_select_their_own_prompt_module(self):
        families = {"eo": "eo", "pe-s": "pe_s", "pe-d-f": "pe_d_f", "pe-d-s": "pe_d_s",
                    "pc-f": "pc_f", "pc-s": "pc_s"}
        for mode, family in families.items():
            for benchmark in ("alfworld", "sciworld", "webshop", "terminalbench"):
                with self.subTest(mode=mode, benchmark=benchmark):
                    prompts = load_framework_prompts(mode, benchmark)
                    self.assertEqual(prompts.__name__, f"toolkit.prompts.{family}.{benchmark}")
                    self.assertEqual(load_executor_instruction(benchmark, mode=mode), prompts.EXECUTOR_PROMPT)
                    if mode == "pe-s":
                        self.assertEqual(render_planner_prompt(benchmark, "A task"),
                                         prompts.PLANNER_TEMPLATE.format(task="A task"))
                    elif mode != "eo":
                        self.assertTrue(prompts.PLANNER_INITIAL_PROMPT)
                        self.assertTrue(prompts.PLANNER_MONITOR_PROMPT)
                        self.assertFalse(any(name.startswith(("PE_FULL_", "PE_SUB_", "PC_FULL_", "PC_SUB_"))
                                             for name in vars(prompts)))
                        if mode.startswith("pe-d"):
                            self.assertTrue(prompts.PLAN_REQUEST_DESCRIPTION)
        with self.assertRaises(KeyError):
            load_framework_prompts("pe-d", "alfworld")
        with self.assertRaises(KeyError):
            load_framework_prompts("eo", "unknown-benchmark")

    def test_dynamic_executor_has_one_action_or_help_contract(self):
        for mode in ("pe-d-f", "pe-d-s"):
            for benchmark in ("alfworld", "sciworld", "webshop", "terminalbench"):
                with self.subTest(mode=mode, benchmark=benchmark):
                    prompt = load_executor_instruction(benchmark, mode=mode)
                    self.assertEqual(prompt.count("Choose exactly one branch per turn:"), 1)
                    self.assertIn("Environment action: output exactly one nonempty Action: <command> line "
                                  "and do not call request_plan.", prompt)
                    self.assertIn("Planning help: call the native request_plan tool "
                                  "and do not output an Action: line.", prompt)
                    self.assertIn("You may include a brief Thought: line explaining the chosen branch.", prompt)
                    self.assertNotIn("Write exactly one nonempty Action: <command> line per turn.", prompt)
                    self.assertNotIn("Return one Action line per turn.", prompt)
                    self.assertNotIn("Choose one environment action, or call request_plan", prompt)

    def test_explicit_executor_instruction_file_overrides_each_framework(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "executor.txt"
            path.write_text("Custom {obj} instruction.\n", encoding="utf-8")
            for mode in ("eo", "pe-s", "pe-d-f", "pe-d-s", "pc-f", "pc-s"):
                with self.subTest(mode=mode):
                    self.assertEqual(load_executor_instruction("alfworld", path, mode=mode),
                                     "Custom {obj} instruction.\n")

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
