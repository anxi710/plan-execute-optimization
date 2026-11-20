import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch

from toolkit.envs.sciworld_env import SciWorldEnv, open_sciworld_backend, sciworld_settings
from toolkit.envs.webshop_env import WebShopEnv, webshop_settings
from toolkit.tasks import alfworld
from toolkit.tasks.rows import load_task_rows
from toolkit.tasks.sciworld import SciWorldTask
from toolkit.tasks.webshop import WebShopTask
from toolkit.utils.config import resolve_config
from toolkit.utils.files import read_jsonl, write_jsonl


class BenchmarkAdapterTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name)

    def test_selection_uses_canonical_order_and_binds_plans(self):
        tasks = [{"id": i, "task": f"task {i}"} for i in range(4)]
        write_jsonl(self.path / "alfworld_dev_tasks.jsonl", tasks)
        plans = self.path / "plans.jsonl"
        write_jsonl(plans, [dict(row, plan=f"<plan>Plan {row['id']}</plan>") for row in reversed(tasks)])
        gamefile_map = self.path / "map.jsonl"
        write_jsonl(gamefile_map, [dict(row, gamefile=f"game-{row['id']}") for row in tasks])
        rows = alfworld.load_alfworld_rows(self.path, "dev", plan_path=plans,
                                           part_num=2, part_idx=1, max_tasks=1,
                                           gamefile_map_path=gamefile_map)
        self.assertEqual(rows, [{"id": 2, "task": "task 2", "gamefile": "game-2", "plan": "Plan 2"}])
        self.assertEqual(load_task_rows(self.path, "alfworld", "dev", task_id=3)[0]["id"], 3)
        with self.assertRaisesRegex(ValueError, "Conflicting ALFWorld gamefiles"):
            alfworld.load_alfworld_rows(self.path, "dev", gamefile_map_path=gamefile_map,
                                        selection_rows=[dict(tasks[0], gamefile="different")])

    def test_alfworld_scan_preserves_ambiguity_and_closes_backend(self):
        gamefiles = [str(self.path / f"game-{index}") for index in range(3)]
        observed = [(f"header\n\n{goal}", path) for goal, path in zip(
            ("Same goal", "Same goal", "Other goal"), gamefiles)]

        def resets(observations):
            return [([goal], {"extra.gamefile": [path]}) for goal, path in observations]

        game = Mock()
        game.reset.side_effect = resets(observed)
        source = SimpleNamespace(game_files=gamefiles, init_env=Mock(return_value=game))
        textworld = ModuleType("textworld")
        textworld.gym = ModuleType("textworld.gym")
        textworld.gym.registry = {}
        write_jsonl(self.path / "alfworld_dev_tasks.jsonl", [
            {"id": "a", "task": " Same  goal "}, {"id": "b", "task": "Same goal"},
            {"id": "c", "task": "Other goal"},
        ])
        output = self.path / "map.jsonl"
        with patch.object(alfworld, "_source", return_value=source), patch.dict(
                sys.modules, {"textworld": textworld, "textworld.gym": textworld.gym}):
            summary = alfworld.prepare_gamefile_map(self.path, "dev", output)
            self.assertEqual(summary, {"total": 3, "ready": 1, "unresolved": 2, "missing": 0})
            rows = read_jsonl(output)
            self.assertEqual(rows[0]["candidates"], ["game-0", "game-1"])
            self.assertEqual(rows[2]["gamefile"], "game-2")
            saved = output.read_bytes()
            game.reset.side_effect = resets([observed[0], observed[0]])
            with self.assertRaisesRegex(ValueError, "unexpected or repeated gamefile"):
                alfworld.prepare_gamefile_map(self.path, "dev", output)
            self.assertEqual(output.read_bytes(), saved)
        self.assertEqual(game.close.call_count, 2)

    def test_sciworld_task_loading_and_native_terminal_score(self):
        write_jsonl(self.path / "sciworld_test_tasks.jsonl", [
            {"id": "task_4", "task": "Test conductivity", "subtask_name": "conductivity"},
        ])
        tasks, count = SciWorldTask.load_tasks(self.path)
        self.assertEqual(count, 1)
        task, = tasks
        self.assertEqual(task.variation_idx, 4)
        (self.path / "max_steps.json").write_text(json.dumps({"conductivity": 3}), encoding="utf-8")
        game = Mock()
        game.reset.return_value = (
            "look", {"taskDesc": "Task Description:\nTest  conductivity", "score": 20, "valid": ["look around"]},
        )
        env = SciWorldEnv(task, game, **sciworld_settings())
        self.assertEqual(env.max_steps, 3)
        prompt, state = env.reset()
        self.assertIn("Test  conductivity\n\nObservation: look", prompt)
        game.load.assert_called_once_with("conductivity", 4, simplificationStr="easy", generateGoldPath=False)
        self.assertEqual(state.reward, 0.2)
        env.step("No action")
        self.assertEqual(state.reward, 0.2)
        game.step.return_value = ("finished", 80, True, {"score": 100, "valid": []})
        _, state = env.step("Action: focus on object")
        self.assertTrue(state.success)
        self.assertEqual((state.reward, state.terminate_reason), (1.0, "success"))
        game.reset.return_value = ("look", {"taskDesc": "different task", "score": 0})
        with self.assertRaisesRegex(ValueError, "description differs"):
            env.reset()

        (self.path / "max_steps.json").unlink()
        config = resolve_config({"environments": {"sciworld": {"max_steps": 1}}})
        game.reset.return_value = ("look", {"taskDesc": "Test conductivity", "score": 0, "valid": ["look around"]})
        limited = SciWorldEnv(task, game, **sciworld_settings(config))
        limited.reset()
        _, state = limited.step("No action")
        self.assertEqual(state.terminate_reason, "max_steps")

    def test_sciworld_backend_uses_bundled_jar_and_closes_on_error(self):
        game = SimpleNamespace(close=Mock())
        fake_sdk = SimpleNamespace(ScienceWorldEnv=Mock(return_value=game))
        with patch.dict(sys.modules, {"scienceworld": fake_sdk}):
            with self.assertRaisesRegex(RuntimeError, "backend failure"):
                with open_sciworld_backend() as backend:
                    self.assertIs(backend, game)
                    raise RuntimeError("backend failure")
        fake_sdk.ScienceWorldEnv.assert_called_once_with(serverPath=None, envStepLimit=200)
        game.close.assert_called_once_with()

    def test_webshop_checks_goal_and_uses_native_purchase_score(self):
        write_jsonl(self.path / "webshop_test_tasks.jsonl", [
            {"id": "bag", "task": "Find a blue bag", "session": 7},
        ])
        tasks, count = WebShopTask.load_tasks(self.path)
        self.assertEqual(count, 1)
        task = next(tasks)
        game = Mock()
        game.reset.return_value = ("search page", None)
        game.get_instruction_text.return_value = task.observation
        game.get_available_actions.side_effect = [
            {"has_search_bar": True, "clickables": ["search"]},
            {"has_search_bar": False, "clickables": ["buy now"]},
        ]
        game.step.side_effect = [("item page", 0.0, False, None), ("done", 0.75, True, None)]
        env = WebShopEnv(task, game, **webshop_settings())
        prompt, _ = env.reset()
        game.reset.assert_called_once_with(session=7)
        self.assertIn("search[keywords]", prompt)
        _, state = env.step("Action: click[Buy Now]")
        self.assertFalse(state.action_trace[-1]["valid"])
        _, state = env.step("Action: search[<a> blue]")
        self.assertFalse(state.action_trace[-1]["valid"])
        game.step.assert_not_called()
        feedback, _ = env.step("Action: search[blue bag]")
        self.assertIn("click[buy now]", feedback)
        _, state = env.step("Action: click[Buy Now]")
        self.assertEqual(game.step.call_count, 2)
        self.assertTrue(state.finished)
        self.assertFalse(state.success)
        self.assertEqual(state.reward, 0.75)

        game.get_instruction_text.return_value = "Find different goods"
        with self.assertRaisesRegex(ValueError, "goal differs"):
            env.reset()
