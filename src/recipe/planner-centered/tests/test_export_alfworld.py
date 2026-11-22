import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from export_alfworld import export_alfworld, interaction_trace
from report import event_anchor, render, render_benchmark, render_event
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

    def make_run(self, directory, *, use_tool_protocol=False, protocol_version="native-tools-v1"):
        run = Path(directory) / "run"
        outcome = {"reason": "executor_budget", "reward": 0, "success": False}
        manifest = {"schema_version": 2, "run_id": "fixture", "status": "complete", "model_order": ["model"],
                    "benchmark": {"name": "ALFWorld", "selection": "full_split", "split": "test",
                                  "canonical_task_count": 1, "tasks": [{"task_id": "1", "goal": "Find it."}]},
                    "budget": {"executor_limit": 12, "planner_limits": {}, "return_every": 2},
                    "trials": {}, "records": {}}
        legacy_modes = ("eo", "pe-s", "pe-d", "pc")
        if use_tool_protocol:
            manifest.update(modes=["eo", "pe-s", "pe-d-f", "pe-d-s", "pc-f", "pc-s"],
                            protocol_version=protocol_version, purpose="paired_model_framework_benchmark")
            manifest["benchmark"].update(selection="single_task", split="dev")
            manifest["budget"] = {"executor_limit": 12}
        for mode in manifest.get("modes", legacy_modes):
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
            if use_tool_protocol and mode == "pc-f" and protocol_version == "native-tools-v1":
                record.update(status="unscored", outcome={"reason": "protocol_error", "reward": None, "success": None})
                tool_call = {"id": "call_pc", "type": "function", "function": {
                    "name": "execute_step",
                    "arguments": '{\n  "thinking_summary": "Observed  <tag>"\n}',
                }}
                record["events"] = [
                    {"event_id": 1, "type": "model_call", "role": "planner",
                     "messages": [{"role": "assistant", "content": None, "tool_calls": [tool_call]},
                                  {"role": "tool", "tool_call_id": "call_pc", "content": "Original observation\n"}],
                     "request_options": {"tools": [{"type": "function", "function": {"name": "execute_step"}}]},
                     "response": {"text": None, "tool_calls": [tool_call]}},
                    {"event_id": 2, "type": "planner_decision", "decision": "advance", "model_event_id": 1,
                     "planner_phase": "Continuous Execution Monitoring", "thinking_summary": "Observed  <tag>"},
                    {"event_id": 3, "type": "execution_request", "request_id": "fixture:stage-1",
                     "current_subplan_id": 2, "stage_objective": "Find it.", "completion_condition": "Item visible"},
                    {"event_id": 4, "type": "model_tool_result", "name": "execute_step", "content": "Floor clear"},
                    {"event_id": 5, "type": "decision_error", "error": "invalid_tool_decision"},
                    {"event_id": 6, "type": "stop", "reason": "protocol_error"},
                    {"event_id": 7, "type": "verifier", **record["outcome"]},
                ]
            archive = f"attempts/{trial_id}/attempt-000001.json"
            write_json(run / path, record)
            write_json(run / archive, {**identity, "attempt": 1, "workspace_id": f"fixture/{trial_id}/attempt-1",
                                      "status": "unscored", "events": [
                                          {"type": "model_call", "role": "planner", "response": None,
                                           "error": "RateLimitError"},
                                          {"type": "stop", "reason": "runtime_error"}]})
            manifest["trials"][trial_id] = {**identity, "status": record["status"], "archived_attempts": [archive]}
            manifest["records"][trial_id] = path
        write_json(run / "manifest.json", manifest)
        return run

    def test_two_phase_json_requests_export_without_becoming_tool_calls(self):
        with tempfile.TemporaryDirectory() as directory:
            run = self.make_run(directory, use_tool_protocol=True, protocol_version="two-phase-v1")
            manifest_path = run / "manifest.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["budget"] = {"unit": "real_environment_dispatch", "executor_limit": 20}
            write_json(manifest_path, manifest)
            path = run / "trials/m1-t1-pc-f.json"
            record = json.loads(path.read_text())
            messages = [{"role": "user", "content": "Initial planning\nPreserve  all spaces."}]
            output = '{\n  "thinking_summary": "观察 <tag>",\n  "current_subplan_id": 1\n}'
            record["protocol_version"] = "two-phase-v1"
            record["events"].insert(0, {"event_id": 0, "type": "model_call", "role": "planner",
                                         "messages": messages, "response": {"text": output}})
            write_json(path, record)
            output_dir = Path(directory) / "export"
            index = export_alfworld(run, output_dir)
            self.assertEqual(index["protocolVersion"], "two-phase-v1")
            self.assertEqual(index["budget"]["environmentStepLimit"], 20)
            self.assertNotIn("executorLimit", index["budget"])
            exported = json.loads((output_dir / "traces/m1-t1-pc-f.json").read_text())["interactions"][0]
            self.assertEqual(exported["messages"], messages)
            self.assertEqual(exported["output"], output)
            self.assertNotIn("toolCalls", exported)

    def test_observation_references_link_to_environment_events(self):
        observation = {"event_id": 11, "type": "tool_event", "observation_id": 2,
                       "action": "take object", "observation": "The object is held.", "valid": True}
        closure = {"event_id": 12, "type": "stage_result", "status": "verified", "evidence_refs": [2],
                   "stage": {"stage_objective": "Take object."}, "thinking_summary": "The object is held."}
        record = {"trial_id": "example", "mode": "pc-s", "model": "model", "task_id": "1", "goal": "Place it.",
                  "events": [observation, closure]}
        interactions = interaction_trace(record)["interactions"]
        self.assertIn("Observation #2", interactions[0]["title"])
        self.assertIn("观察编号 2", interactions[1]["content"])
        rendered = render_event("pc-s", closure, observation, {2: 11})
        self.assertIn(f'href="#{event_anchor("pc-s", 11)}">#2</a>', rendered)
        self.assertIn("观察引用", rendered)
        self.assertNotIn(f'href="#{event_anchor("pc-s", 2)}"', rendered)
        historical = render_event("pc-s", closure, observation)
        self.assertIn(f'href="#{event_anchor("pc-s", 2)}">#2</a>', historical)
        with tempfile.TemporaryDirectory() as directory:
            run = self.make_run(directory, use_tool_protocol=True, protocol_version="two-phase-v2")
            index = export_alfworld(run, Path(directory) / "export")
            self.assertEqual(index["protocolVersion"], "two-phase-v2")

    def test_export_validates_scores_and_counts_archived_cost(self):
        with tempfile.TemporaryDirectory() as directory:
            run = self.make_run(directory)
            output = Path(directory) / "export"
            index = export_alfworld(run, output)
            self.assertEqual(len(index["trials"]), 4)
            self.assertEqual(index["budget"]["executorLimit"], 12)
            self.assertNotIn("environmentStepLimit", index["budget"])
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

    def test_tool_protocol_run_exports_six_variants_and_preserves_original_tool_calls(self):
        with tempfile.TemporaryDirectory() as directory:
            run = self.make_run(directory, use_tool_protocol=True)
            with patch("export_alfworld.write_standalone") as write_page:
                index = export_alfworld(run, standalone=True)
            path, dataset = write_page.call_args.args
            self.assertEqual(path, run / "alfworld.html")
            self.assertEqual(index["manifestUrl"], "manifest.json")
            self.assertEqual(index["protocolVersion"], "native-tools-v1")
            self.assertEqual(index["modes"], ["eo", "pe-s", "pe-d-f", "pe-d-s", "pc-f", "pc-s"])
            self.assertEqual(len(index["trials"]), 6)
            pc = next(trial for trial in index["trials"] if trial["mode"] == "pc-f")
            self.assertIsNone(pc["score"])
            events = dataset[pc["traceUrl"]]["interactions"]
            raw = json.loads((run / f"trials/{pc['id']}.json").read_text())["events"][0]
            self.assertEqual(events[0]["messages"], raw["messages"])
            self.assertEqual(events[0]["toolCalls"], raw["response"]["tool_calls"])
            self.assertEqual(events[0]["phase"], "Continuous Execution Monitoring")
            self.assertEqual(events[2]["stageId"], 2)
            self.assertEqual(events[3]["content"], "Floor clear")
            self.assertEqual(events[-1]["content"], "缺评")

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

    def test_report_describes_recorded_role_models(self):
        with tempfile.TemporaryDirectory() as directory:
            run = self.make_run(directory, use_tool_protocol=True)
            manifest = json.loads((run / "manifest.json").read_text())
            for planner in ("model", "separate-planner"):
                with self.subTest(planner=planner):
                    manifest["models"] = {"model": {
                        "planner": {"model": planner}, "executor": {"model": "model"},
                    }}
                    result = render_benchmark(run, Path(directory) / "audit.html", "example", manifest=manifest)
                    self.assertEqual("两个角色采用同一基座模型" in result, planner == "model")
                    self.assertEqual("分别按运行清单中的角色配置调用模型" in result, planner != "model")


if __name__ == "__main__":
    unittest.main()
