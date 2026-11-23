import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from export_alfworld import export_alfworld, interaction_trace, write_standalone
from report import event_anchor, render_benchmark, render_event
from toolkit.frameworks import FRAMEWORK_MODES, FRAMEWORK_PROTOCOL
from toolkit.utils.files import read_json, write_json


class AlfworldExportTest(unittest.TestCase):
    def make_run(self, directory):
        run = Path(directory) / "planner-centered-v2/runs/fixture"
        outcome = {"reason": "executor_budget", "reward": 0, "success": False}
        manifest = {
            "schema_version": 2, "run_id": "fixture", "status": "complete",
            "purpose": "untrained_framework_benchmark", "experiment": "planner-centered-v2",
            "protocol_version": FRAMEWORK_PROTOCOL, "modes": list(FRAMEWORK_MODES),
            "model_order": ["model"],
            "models": {"model": {"planner": {"model": "model", "max_tokens": 1000},
                                 "executor": {"model": "model", "max_tokens": 1000}}},
            "benchmark": {"name": "ALFWorld", "selection": "single_task", "split": "dev",
                          "tasks": [{"task_id": "1", "goal": "Find it."}]},
            "budget": {"unit": "real_environment_dispatch", "executor_limit": 20,
                       "context_window": {"max_input_tokens": None}},
            "trials": {}, "records": {},
        }
        for mode in FRAMEWORK_MODES:
            trial_id = f"m1-t1-{mode}"
            identity = {"run_id": "fixture", "trial_id": trial_id, "model": "model", "task_id": "1",
                        "mode": mode, "protocol_version": FRAMEWORK_PROTOCOL}
            path, archive = f"trials/{trial_id}.json", f"attempts/{trial_id}/attempt-000001.json"
            record = {**identity, "attempt": 2, "workspace_id": f"fixture/{trial_id}/attempt-2",
                      "goal": "Find it.", "status": "complete", "outcome": outcome,
                      "events": [
                          {"event_id": 1, "type": "initial_observation", "observation_id": 1,
                           "observation": "Initial room"},
                          {"event_id": 2, "type": "model_call", "role": "executor",
                           "messages": [{"role": "user", "content": "Original prompt\nKeep  spaces."}],
                           "context_window": {"max_input_tokens": None, "dropped_record_ids": []},
                           "response": {"text": "Action: look", "usage": {"total_tokens": 10}}},
                          {"event_id": 3, "type": "tool_event", "observation_id": 2, "action": "look",
                           "observation": "Room clear", "valid": True, "dispatched": True},
                          {"event_id": 4, "type": "stop", "reason": "executor_budget"},
                          {"event_id": 5, "type": "verifier", **outcome},
                      ]}
            write_json(run / path, record)
            write_json(run / archive, {**identity, "attempt": 1, "workspace_id": f"fixture/{trial_id}/attempt-1",
                                      "status": "unscored", "events": [
                                          {"event_id": 1, "type": "model_call", "role": "planner", "response": None,
                                           "messages": [], "error": "RateLimitError"},
                                          {"event_id": 2, "type": "stop", "reason": "runtime_error"}]})
            manifest["trials"][trial_id] = {**identity, "status": "complete", "archived_attempts": [archive]}
            manifest["records"][trial_id] = path
        write_json(run / "manifest.json", manifest)
        return run

    def test_current_six_modes_preserve_raw_calls_and_count_all_attempts(self):
        with tempfile.TemporaryDirectory() as directory:
            run = self.make_run(directory)
            index = export_alfworld(run)
            self.assertEqual(index["modes"], list(FRAMEWORK_MODES))
            self.assertEqual(index["protocolVersion"], FRAMEWORK_PROTOCOL)
            self.assertEqual(index["manifestUrl"], "manifest.json")
            self.assertEqual(index["roleModels"], {"model": {"planner": "model", "executor": "model"}})
            self.assertEqual(index["budget"]["environmentStepLimit"], 20)
            self.assertEqual(index["budget"]["contextWindow"], {"max_input_tokens": None})
            for trial in index["trials"]:
                self.assertEqual((trial["plannerCalls"], trial["executorCalls"], trial["tokens"]), (1, 1, 10))
                self.assertEqual((trial["knownTokenCalls"], trial["totalTokenCalls"], trial["archivedAttempts"]), (1, 2, 1))
                trace = read_json(run / "alfworld/data/traces" / f"{trial['id']}.json")
                original = read_json(run / f"trials/{trial['id']}.json")["events"][1]
                call = trace["interactions"][1]
                self.assertEqual(call["messages"], original["messages"])
                self.assertEqual(call["response"], original["response"])
                self.assertEqual(call["output"], original["response"]["text"])
                self.assertEqual(call["contextWindow"], original["context_window"])
                self.assertIn("Observation #1", trace["interactions"][0]["title"])
                self.assertEqual(trial["score"], 0)
            self.assertEqual(read_json(run / "alfworld/data/index.json"), index)

    def test_export_preserves_distinct_role_model_names(self):
        with tempfile.TemporaryDirectory() as directory:
            run = self.make_run(directory)
            manifest = read_json(run / "manifest.json")
            manifest["models"]["model"]["planner"]["model"] = "Qwen3.8-27B"
            manifest["models"]["model"]["executor"]["model"] = "DeepSeek-V4.1-Flash"
            write_json(run / "manifest.json", manifest)
            index = export_alfworld(run)
            self.assertEqual(index["roleModels"], {
                "model": {"planner": "Qwen3.8-27B", "executor": "DeepSeek-V4.1-Flash"},
            })
            self.assertTrue(all(trial["model"] == "model" for trial in index["trials"]))

    def test_native_tool_calls_and_assessment_are_preserved(self):
        tool = {"id": "call_1", "type": "function", "function": {
            "name": "request_plan", "arguments": '{\n  "assessment": "Need a plan <tag>"\n}'}}
        events = [
            {"event_id": 7, "type": "model_call", "role": "executor",
             "messages": [{"role": "user", "content": "History embedded\nexactly  here"}],
             "request_options": {"tools": [{"type": "function", "function": {"name": "request_plan"}}]},
             "response": {"text": None, "tool_calls": [tool]}},
            {"event_id": 8, "type": "planner_decision", "decision": "revise", "assessment": "Object visible",
             "model_event_id": 7, "planner_phase": "Continuous Execution Monitoring"},
            {"event_id": 9, "type": "model_tool_result", "name": "request_plan", "content": "Take it."},
        ]
        record = {"trial_id": "example", "mode": "pe-d-s", "protocol_version": FRAMEWORK_PROTOCOL,
                  "model": "model", "task_id": "1", "goal": "Find it.", "events": events}
        trace = interaction_trace(record)["interactions"]
        self.assertEqual(trace[0]["toolCalls"], [tool])
        self.assertEqual(trace[0]["response"], events[0]["response"])
        self.assertIsNone(trace[0]["response"]["text"])
        self.assertEqual(trace[0]["messages"], events[0]["messages"])
        self.assertEqual(trace[1]["content"], "Object visible")
        self.assertEqual(trace[2]["content"], "Take it.")

    def test_observation_references_link_to_environment_observation_ids(self):
        observation = {"event_id": 11, "type": "tool_event", "observation_id": 2,
                       "action": "take object", "observation": "Object held", "valid": True, "dispatched": True}
        closure = {"event_id": 12, "type": "stage_result", "status": "verified", "evidence_refs": [2],
                   "stage": {"stage_objective": "Take object"}, "assessment": "Object held"}
        record = {"trial_id": "example", "mode": "pc-s", "protocol_version": FRAMEWORK_PROTOCOL,
                  "model": "model", "task_id": "1", "goal": "Place it.", "events": [observation, closure]}
        trace = interaction_trace(record)["interactions"]
        self.assertIn("Observation #2", trace[0]["title"])
        self.assertIn("观察编号 2", trace[1]["content"])
        rendered = render_event("example", closure, {2: 11})
        self.assertIn(f'href="#{event_anchor("example", 11)}">#2</a>', rendered)
        self.assertNotIn(f'href="#{event_anchor("example", 2)}"', rendered)

    def test_missing_score_is_distinct_from_valid_zero_and_report_includes_cost(self):
        with tempfile.TemporaryDirectory() as directory:
            run = self.make_run(directory)
            manifest = read_json(run / "manifest.json")
            manifest["benchmark"].update(selection="full_split", split="test", canonical_task_count=1)
            trial = manifest["trials"]["m1-t1-pc-f"]
            trial["status"] = "unscored"
            path = run / manifest["records"][trial["trial_id"]]
            record = read_json(path)
            record.update(status="unscored", outcome={"reason": "runtime_error", "reward": None, "success": None})
            record["events"][-2:] = [{"event_id": 4, "type": "stop", "reason": "runtime_error"},
                                    {"event_id": 5, "type": "verifier", **record["outcome"]}]
            write_json(path, record)
            write_json(run / "manifest.json", manifest)
            index = export_alfworld(run)
            self.assertIsNone(next(item for item in index["trials"] if item["mode"] == "pc-f")["score"])
            self.assertEqual(next(item for item in index["trials"] if item["mode"] == "eo")["score"], 0)
            report = render_benchmark(run, run / "report.html", "example")
            self.assertIn("缺评不计为零分", report)
            self.assertIn("≥10", report)
            self.assertIn("Original prompt", report)
            self.assertIn("两个角色采用同一基座模型", report)

    def test_export_rejects_invalid_terminal_and_missing_archive_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            run = self.make_run(directory)
            path = run / "trials/m1-t1-eo.json"
            record = read_json(path)
            record["events"][-1]["reward"] = 1
            write_json(path, record)
            with self.assertRaisesRegex(ValueError, "Verifier does not match"):
                export_alfworld(run)
            record["events"][-1]["reward"] = 0
            write_json(path, record)
            (run / "attempts/m1-t1-eo/attempt-000001.json").unlink()
            with self.assertRaisesRegex(ValueError, "all archived cost evidence"):
                export_alfworld(run)

    def test_current_reader_rejects_archived_protocols(self):
        with tempfile.TemporaryDirectory() as directory:
            run = self.make_run(directory)
            manifest = read_json(run / "manifest.json")
            manifest["protocol_version"] = "archived-protocol"
            write_json(run / "manifest.json", manifest)
            with self.assertRaisesRegex(ValueError, "current-protocol"):
                export_alfworld(run)

    def test_standalone_keeps_payload_and_escapes_html_boundaries(self):
        with tempfile.TemporaryDirectory() as directory:
            run = self.make_run(directory)
            with patch("export_alfworld.write_standalone") as write_page:
                index = export_alfworld(run, standalone=True)
            self.assertEqual(write_page.call_args.args[0], run / "alfworld.html")
            self.assertEqual(len(write_page.call_args.args[1]), len(FRAMEWORK_MODES) + 1)
            self.assertEqual(index["manifestUrl"], "manifest.json")
            def build(command, check):
                destination = Path(command[-1])
                (destination / "alfworld/assets").mkdir(parents=True)
                (destination / "alfworld/assets/viewer.js").write_text("export const viewer=1;")
                (destination / "alfworld/assets/viewer.css").write_text("body{margin:0}")
                (destination / "alfworld.html").write_text(
                    '<script type="module" crossorigin src="./alfworld/assets/viewer.js"></script>'
                    '<link rel="stylesheet" crossorigin href="./alfworld/assets/viewer.css">'
                    '<div id="root"></div>')
            output = Path(directory) / "viewer.html"
            with patch("export_alfworld.subprocess.run", side_effect=build):
                write_standalone(output, {"raw": "</script><tag>"})
            page = output.read_text()
            self.assertIn('id="alfworld-data"', page)
            self.assertIn("\\u003c/script>", page)
            self.assertNotIn('src="./alfworld/assets/', page)


if __name__ == "__main__":
    unittest.main()
