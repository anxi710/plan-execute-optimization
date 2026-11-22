from pathlib import Path
import tempfile
import unittest

from toolkit.prompts import PlanInjection, render_action_feedback
from toolkit.rollout.state import State
from toolkit.rollout.traces import conversation_parts, load_records, load_trace
from toolkit.utils.files import write_json


class TraceTest(unittest.TestCase):
    def test_selects_samples_and_pairs_observations_even_with_plan_injection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            observation = "Observation: A cupboard is open."
            for sample_id in (1, 0):
                state = State(steps=1, finished=True, success=sample_id == 1)
                state.action_trace = [{"observation": observation}]
                feedback = observation
                if sample_id == 1:
                    state.action_trace[0]["available_actions"] = ["take cup from cupboard"]
                    feedback = render_action_feedback(observation, ["take cup from cupboard"])
                state.history = [
                    {"role": "user", "content": "Find a cup."},
                    {"role": "assistant", "content": "Action: open cupboard"},
                    {"role": "user", "content": PlanInjection("observation", "Check cupboards").observation(feedback)},
                ]
                data = state.to_dict()
                data[-1].update(task_id=3, sample_id=sample_id)
                write_json(root / "3" / f"sample_{sample_id}.json", data)
            self.assertEqual([row["sample_id"] for row in load_records(root, 3)], [0, 1])
            record, = load_records(root, 3, status="success")
            self.assertEqual(record["sample_id"], 1)
            prefix, pairs = conversation_parts(record)
            self.assertEqual(prefix[0]["content"], "Find a cup.")
            self.assertTrue(pairs[0][1]["content"].startswith(observation))
            self.assertIn("take cup from cupboard", pairs[0][1]["content"])
            first_sample, = load_records(root, 3, sample_id=0)
            self.assertEqual(conversation_parts(first_sample)[0][0]["content"], "Find a cup.")
            record["trace"][0]["observation"] = "Observation: Something else."
            with self.assertRaisesRegex(ValueError, "Trace/history observation mismatch"):
                conversation_parts(record)

    def test_reads_only_sample_directories_and_preserves_archived_task_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            task_file = root / "3.json"
            archived = State(finished=True, success=True).to_dict()
            write_json(task_file, archived)
            with self.assertRaisesRegex(ValueError, "No trajectory for task 3"):
                load_records(root, 3)
            sample = State(finished=True, success=False).to_dict()
            sample[-1].update(task_id=3, sample_id=2)
            write_json(root / "3" / "sample_2.json", sample)
            record, = load_records(root, 3)
            self.assertEqual(record["sample_id"], 2)
            self.assertFalse(record["success"])
            self.assertEqual(load_trace(task_file)["success"], True)

    def test_rejects_an_incomplete_trace_and_path_traversal(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "3.json"
            write_json(path, State(incomplete=True).to_dict())
            with self.assertRaisesRegex(ValueError, "Unfinished"):
                load_trace(path)
            with self.assertRaisesRegex(ValueError, "path-safe"):
                load_records(directory, "../3")
