import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from toolkit.envs.sciworld_env import SciWorldEnv


class ScienceWorldActionsTest(unittest.TestCase):
    def make_environment(self):
        task = SimpleNamespace(
            task_id="conductivity-3", observation="Test conductivity", sub_task_name="conductivity",
            variation_idx=3,
        )
        backend = Mock()
        backend.reset.return_value = (
            "A laboratory.",
            {"taskDesc": "Task Description: Test conductivity", "score": 20,
             "valid": ["inventory", "look in drawer"]},
        )
        env = SciWorldEnv(task, backend, instruction_path=None, max_steps=8)
        return env, backend

    def test_native_actions_refresh_without_entering_planner_observations(self):
        env, backend = self.make_environment()
        prompt, state = env.reset()
        self.assertEqual(env.get_available_actions(), ["inventory", "look in drawer"])
        self.assertIn("Available actions:", prompt)
        self.assertIn("look in drawer", prompt)
        self.assertNotIn("Available actions:", env.initial_observation)
        self.assertEqual(state.reward, 0.2)
        backend.load.assert_called_once_with("conductivity", 3, simplificationStr="easy", generateGoldPath=False)

        backend.step.return_value = (
            "You carry a wire.", 20, False,
            {"score": 40, "valid": ["drop wire", "focus on bulb"]},
        )
        feedback, state = env.step("Action: inventory")
        self.assertEqual(env.get_available_actions(), ["drop wire", "focus on bulb"])
        self.assertIn("drop wire", feedback)
        self.assertNotIn("look in drawer", feedback)
        self.assertEqual(state.action_trace[-1]["observation"], "Observation: You carry a wire.")
        self.assertEqual(state.reward, 0.4)
        self.assertFalse(state.finished)
        backend.get_valid_action_object_combinations.assert_not_called()

        backend.step.return_value = ("Experiment complete.", 60, True, {"score": 100, "valid": []})
        _, state = env.step("Action: focus on bulb")
        self.assertEqual(env.get_available_actions(), [])
        self.assertEqual((state.reward, state.success, state.terminate_reason), (1.0, True, "success"))

    def test_missing_or_malformed_native_actions_do_not_fall_back_to_a_static_list(self):
        for actions in (None, "inventory", ["inventory", 1]):
            with self.subTest(actions=actions):
                env, backend = self.make_environment()
                observation, info = backend.reset.return_value
                if actions is None:
                    del info["valid"]
                    error = KeyError
                else:
                    info["valid"] = actions
                    error = ValueError
                backend.reset.return_value = observation, info
                with self.assertRaises(error):
                    env.reset()
