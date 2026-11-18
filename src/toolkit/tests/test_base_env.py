import unittest

from toolkit.envs.base import ActionResult, BaseEnv


class PartialRewardEnv(BaseEnv):
    def __init__(self):
        super().__init__(observation="Room", plan="Check the table", plan_placement="observation",
                         instruction="Choose one action", max_steps=2)
        self.actions = []

    def execute_action(self, action):
        self.actions.append(action)
        return ActionResult("Partially complete", reward=0.5, valid=True, done=True, success=False)


class BaseEnvTest(unittest.TestCase):
    def test_reset_starts_with_instruction_and_observation(self):
        prompt, state = PartialRewardEnv().reset()
        self.assertEqual(prompt, "Choose one action\n\nRoom")
        self.assertEqual(state.history, [{"role": "user", "content": prompt}])

    def test_partial_reward_and_step_limit_use_benchmark_outcome(self):
        env = PartialRewardEnv()
        env.reset()
        _, state = env.step("Missing the action")
        self.assertEqual(env.actions, [])
        self.assertFalse(state.action_trace[0]["valid"])
        self.assertFalse(state.finished)

        feedback, state = env.step("Action: inspect table")
        self.assertEqual(env.actions, ["inspect table"])
        self.assertEqual(state.steps, 2)
        self.assertTrue(state.finished)
        self.assertFalse(state.success)
        self.assertEqual(state.reward, 0.5)
        self.assertEqual(state.terminate_reason, "environment_done")
        self.assertIn("Check the table", feedback)
        self.assertEqual(state.action_trace[-1]["observation"], "Observation: Partially complete")
