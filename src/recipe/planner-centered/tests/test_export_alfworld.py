import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from export_alfworld import export_alfworld, interaction_trace
from report import render
from toolkit.utils.files import write_json


class AlfworldExportTest(unittest.TestCase):
    def test_full_messages_outputs_and_protocol_boundaries_are_preserved(self):
        for mode in ("eo", "pe-s", "pe-d", "pc"):
            with self.subTest(mode=mode):
                record = {"trial_id": "example", "mode": mode, "model": "model", "task_id": "1", "goal": "Find it.",
                          "events": []}
                messages = [{"role": "user", "content": "Original prompt"},
                            {"role": "assistant", "content": "Previous output"},
                            {"role": "user", "content": "Environment observation"}]
                events = [
                    {"type": "initial_observation", "observation": "Initial room"},
                    {"type": "execution_request", "request_id": "private:stage-1" if mode == "pc" else "private:task",
                     "stage_objective": "Find object" if mode == "pc" else None,
                     "soft_guidance": None if mode == "eo" else "Find it.", "goal": "Find it.", "plan_version": 1},
                    {"type": "model_call", "role": "executor", "messages": messages,
                     "response": {"text": "Thought: Look.\nAction: inspect box"}},
                    {"type": "tool_event", "action": "inspect box", "observation": "You see an object.", "valid": True},
                    {"type": "execution_feedback", "return_reason": "budget_pause"},
                    {"type": "execution_request", "request_id": "private:stage-2" if mode == "pc" else "private:task",
                     "stage_objective": "Take object" if mode == "pc" else None,
                     "soft_guidance": None if mode == "eo" else "Take it.", "goal": "Find it.", "plan_version": 2},
                    {"type": "planner_decision", "decision": "delegate" if mode == "pc" else "guide"},
                    {"type": "decision_error", "error": "unknown_evidence_ref"},
                    {"type": "stop", "reason": "protocol_error"},
                    {"type": "verifier", "reward": 0, "success": False},
                ]
                record["events"] = [{**event, "event_id": i, "timestamp": "not exported", "workspace_id": "private"}
                                    for i, event in enumerate(events, 1)]
                trace = interaction_trace(record)
                self.assertEqual(len(trace["interactions"]), len(events))
                call = trace["interactions"][2]
                self.assertEqual(call["messages"], messages)
                self.assertEqual(call["output"], "Thought: Look.\nAction: inspect box")
                self.assertEqual(trace["interactions"][7]["kind"], "error")
                expected_markers = (["E", "R", "V"] if mode == "eo" else
                                    ["D", "E", "R", "D", "V"] if mode == "pc" else
                                    ["G", "E", "R", "G", "V"])
                self.assertEqual([item["marker"] for item in trace["interactions"] if "marker" in item], expected_markers)
                self.assertNotIn("marker", trace["interactions"][6])  # Planner decision is not another delegation.
                self.assertNotIn("marker", trace["interactions"][8])  # Only the verifier adds V.
                requests = [trace["interactions"][i] for i in (1, 5)]
                self.assertEqual([request["requestId"] for request in requests],
                                 ["阶段 1", "阶段 2"] if mode == "pc" else ["整任务", "整任务"])
                if mode == "pe-d":
                    self.assertIn("续接同一任务", requests[1]["title"])
                self.assertFalse(any({"timestamp", "workspace_id", "seconds"} & item.keys()
                                     for item in trace["interactions"]))

    def test_planner_call_has_p_marker(self):
        record = {"trial_id": "example", "mode": "pc", "model": "model", "task_id": "1", "goal": "Find it.",
                  "events": [{"event_id": 1, "type": "model_call", "role": "planner", "messages": [],
                              "response": None, "error": "RateLimitError"}]}
        self.assertEqual(interaction_trace(record)["interactions"][0]["marker"], "P")

    def make_run(self, directory):
        run = Path(directory) / "run"
        outcome = {"reason": "executor_budget", "reward": 0, "success": False}
        manifest = {"schema_version": 2, "run_id": "fixture", "status": "complete", "model_order": ["model"],
                    "benchmark": {"name": "ALFWorld", "selection": "full_split", "split": "test",
                                  "canonical_task_count": 1, "tasks": [{"task_id": "1", "goal": "Find it."}]},
                    "budget": {"executor_limit": 12, "planner_limits": {}, "return_every": 2},
                    "trials": {}, "records": {}}
        for mode in ("eo", "pe-s", "pe-d", "pc"):
            trial_id = f"m1-t1-{mode}"
            path = f"trials/{trial_id}.json"
            identity = {"run_id": "fixture", "trial_id": trial_id, "model": "model", "task_id": "1", "mode": mode}
            record = {**identity, "attempt": 2, "workspace_id": f"fixture/{trial_id}/attempt-2", "goal": "Find it.",
                      "status": "complete", "outcome": outcome,
                      "events": [{"event_id": 1, "type": "model_call", "role": "executor",
                                  "messages": [{"role": "user", "content": "Original prompt"}],
                                  "response": {"text": "Action: look", "usage": {"total_tokens": 10}}},
                                 {"event_id": 2, "type": "stop", "reason": "executor_budget"},
                                 {"event_id": 3, "type": "verifier", **outcome}]}
            archive = f"attempts/{trial_id}/attempt-000001.json"
            write_json(run / path, record)
            write_json(run / archive, {**identity, "attempt": 1, "workspace_id": f"fixture/{trial_id}/attempt-1",
                                      "status": "unscored", "events": [
                                          {"type": "model_call", "role": "planner", "response": None,
                                           "error": "RateLimitError"},
                                          {"type": "stop", "reason": "runtime_error"}]})
            manifest["trials"][trial_id] = {**identity, "status": "complete", "archived_attempts": [archive]}
            manifest["records"][trial_id] = path
        write_json(run / "manifest.json", manifest)
        return run

    def test_export_validates_scores_and_counts_archived_cost(self):
        with tempfile.TemporaryDirectory() as directory:
            run = self.make_run(directory)
            output = Path(directory) / "export"
            index = export_alfworld(run, output)
            self.assertEqual(len(index["trials"]), 4)
            for trial in index["trials"]:
                self.assertEqual((trial["plannerCalls"], trial["executorCalls"], trial["tokens"]), (1, 1, 10))
                self.assertEqual((trial["knownTokenCalls"], trial["totalTokenCalls"], trial["archivedAttempts"]), (1, 2, 1))
                trace = json.loads((output / "traces" / f"{trial['id']}.json").read_text())
                self.assertEqual(len(trace["interactions"]), 3)
                self.assertEqual(trial["traceUrl"], f"alfworld/data/traces/{trial['id']}.json")
            self.assertEqual(json.loads((output / "index.json").read_text()), index)
            path = run / "trials/m1-t1-eo.json"
            record = json.loads(path.read_text())
            record["events"][-1]["reward"] = 1
            write_json(path, record)
            with self.assertRaisesRegex(ValueError, "Verifier does not match"):
                export_alfworld(run, output)

    def test_export_rejects_missing_archived_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            run = self.make_run(directory)
            (run / "attempts/m1-t1-eo/attempt-000001.json").unlink()
            with self.assertRaisesRegex(ValueError, "all archived cost evidence"):
                export_alfworld(run, Path(directory) / "export")

    def test_audit_links_full_alfworld_and_preserves_other_benchmark_rendering(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            smoke = root / "smoke"
            write_json(smoke / "manifest.json", {
                "records": {}, "benchmark": {"name": "ALFWorld", "split": "dev", "task_id": "2", "goal": "Test goal"},
                "purpose": "live_model_interface_smoke", "status": "complete", "run_id": "smoke", "started_at": "start",
            })
            benchmarks = []
            for name, selection in (("ALFWorld", "full_split"), ("Terminal-Bench", "reviewed_subset"),
                                    ("WebShop", "full_split")):
                path = root / name
                write_json(path / "manifest.json", {"benchmark": {"name": name, "selection": selection}})
                benchmarks.append(path)
            with patch("report.render_benchmark", side_effect=["Terminal pending human review", "WebShop stopped"]) as paired:
                result = render(smoke, root / "audit.html", benchmark_dirs=benchmarks)
            self.assertIn('<section id="benchmark-1" class="benchmark"><h2>ALFWorld 完整实验结果</h2>', result)
            self.assertIn('href="alfworld.html"', result)
            self.assertIn("Terminal pending human review", result)
            self.assertIn("WebShop stopped", result)
            self.assertEqual(paired.call_count, 2)
            self.assertEqual([call.args[0] for call in paired.call_args_list], benchmarks[1:])


if __name__ == "__main__":
    unittest.main()
