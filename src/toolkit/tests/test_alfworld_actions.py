import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock

from toolkit.envs.alfworld_env import AlfWorldEnv, alfworld_settings
from toolkit.tasks.alfworld import AlfWorldRolloutSlot, AlfWorldTask


class AlfWorldActionsTest(unittest.TestCase):
    def test_slot_preserves_native_reset_commands_without_an_extra_reset(self):
        with TemporaryDirectory() as directory:
            gamefile = str(Path(directory) / "game.tw-pddl")
            observation = "Room with a lamp. Your task is to examine a book in the light."
            commands = ["look", "use desklamp 1"]
            backend = Mock()
            backend.batch_env.reset.return_value = ([f"Header\n\n{observation}"], {
                "extra.gamefile": [gamefile], "admissible_commands": [commands],
            })
            row = {"id": 7, "task": observation}
            slot = AlfWorldRolloutSlot(backend, {"7": row}, {"7": gamefile})
            task = slot.load_task(row)
            self.assertEqual(task.admissible_commands, commands)
            self.assertIsNot(task.admissible_commands, commands)
            backend.batch_env.load.assert_called_once_with([gamefile])
            backend.batch_env.reset.assert_called_once_with()

            env = AlfWorldEnv(task, **alfworld_settings())
            env.reset()
            self.assertEqual(env.get_available_actions(), commands)
            backend.batch_env.reset.assert_called_once_with()
            backend.reset.assert_not_called()

    def test_actions_are_refreshed_from_native_step_without_filtering_commands(self):
        backend = Mock()
        initial = ["use desklamp 1", "look"]
        task = AlfWorldTask(7, backend, "Room with a lamp.", "game", admissible_commands=initial)
        env = AlfWorldEnv(task, **alfworld_settings())
        env.reset()
        self.assertEqual(env.get_available_actions(), initial)
        returned = env.get_available_actions()
        returned.append("not a native command")
        self.assertEqual(env.get_available_actions(), initial)

        next_commands = ["examine book 1", "inventory"]
        backend.step.return_value = (["The lamp is on."], [0], [False], {
            "won": [False], "admissible_commands": [next_commands],
        })
        result = env.execute_action("use desklamp 1")
        backend.step.assert_called_once_with(["use desklamp 1"])
        self.assertEqual(result.observation, "The lamp is on.")
        self.assertTrue(result.valid)
        self.assertEqual(env.get_available_actions(), next_commands)
        next_commands.append("late backend mutation")
        self.assertEqual(env.get_available_actions(), ["examine book 1", "inventory"])

        backend.step.return_value = (["Nothing happens."], [0], [False], {
            "won": [False], "admissible_commands": [["inventory"]],
        })
        result = env.execute_action("a command outside the native list")
        self.assertFalse(result.valid)
        backend.step.assert_called_with(["a command outside the native list"])
        self.assertEqual(env.get_available_actions(), ["inventory"])

    def test_missing_initial_native_commands_is_an_error(self):
        task = AlfWorldTask(7, Mock(), "Room", "game")
        env = AlfWorldEnv(task, **alfworld_settings())
        with self.assertRaisesRegex(ValueError, "native admissible commands"):
            env.reset()


if __name__ == "__main__":
    unittest.main()
