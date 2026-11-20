import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from toolkit.prompts import render_planner_prompt
from toolkit.rollout.terminalbench import load_terminalbench_trial
from toolkit.tasks.rows import task_rows_by_id
from toolkit.tasks.terminalbench import TerminalBenchTask
from toolkit.utils.files import write_json


class TerminalBenchImportTest(unittest.TestCase):
    def test_reviewed_task_and_native_result(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "task.toml").write_text(
                '[task]\nname = "terminal-bench/music-harmony"\nversion = "2.2.1"\n', encoding="utf-8",
            )
            (root / "instruction.md").write_text("Create a four-part score.", encoding="utf-8")
            task = TerminalBenchTask.load(root)
            row = task_rows_by_id([task.planner_row()])["music-harmony"]
            self.assertIn(task.observation, render_planner_prompt("terminalbench", row["task"]))
            path = root / "result.json"
            lock_path = root / "lock.json"
            trial = {
                "schema_version": 1,
                "task_name": "music-harmony",
                "finished_at": "2026-11-19T00:00:00Z",
                "reward_valid": True,
                "verifier_result": {"rewards": {"reward": 0}},
            }
            write_json(path, trial)
            with self.assertRaises(FileNotFoundError):
                load_terminalbench_trial(path, task)
            write_json(lock_path, {"schema_version": 2, "task": {"name": "music-harmony", "version": "2.2.0"}})
            with self.assertRaisesRegex(ValueError, "task lock does not match"):
                load_terminalbench_trial(path, task)
            write_json(lock_path, {"schema_version": 2, "task": {"name": "music-harmony", "version": "2.2.1"}})
            result = load_terminalbench_trial(path, task)
            self.assertEqual((result["reward"], result["success"]), (0, False))
            self.assertEqual(result["task_version"], "2.2.1")
            write_json(path, dict(trial, reward_valid=False, verifier_result=None))
            result = load_terminalbench_trial(path, task)
            self.assertEqual((result["reward"], result["success"]), (None, None))
            write_json(path, dict(trial, task_name="other-task"))
            with self.assertRaisesRegex(ValueError, "does not match"):
                load_terminalbench_trial(path, task)
            (root / "task.toml").write_text(
                '[task]\nname = "terminal-bench/music-harmony"\nversion = "unreviewed"\n', encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "not in the reviewed list"):
                TerminalBenchTask.load(root)
