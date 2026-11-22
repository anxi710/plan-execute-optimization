import gzip
import json
import os
import sys
import tempfile
import unittest
from collections import Counter
from contextlib import asynccontextmanager, nullcontext, redirect_stdout
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import benchmark
import run
from run import PromptBudgetExceeded, model_call
from toolkit.frameworks import FRAMEWORK_MODES, FRAMEWORK_PROTOCOL, PLAN_SCOPES
from toolkit.envs.base import ActionResult, BaseEnv
from report import accumulate_attempt_cost, benchmark_token_count, matched_trials, render_benchmark
from toolkit.utils.files import read_json, write_json


class APIConnectionError(Exception):
    pass


@asynccontextmanager
async def offline_client(**kwargs):
    yield object()


class BenchmarkStorageTest(unittest.IsolatedAsyncioTestCase):
    def test_cli_uses_configured_endpoint_and_key(self):
        with (tempfile.TemporaryDirectory() as directory,
              patch.dict(os.environ, {}, clear=True),
              patch.object(benchmark, "run_benchmark", new_callable=AsyncMock) as run_benchmark):
            config = Path(directory) / "config.yaml"
            config.write_text("models: [custom/model-name]\ntoolkit:\n  planner_generation:\n"
                              "    model_name: custom/planner-name\n    api_base: http://planner.test/v1\n"
                              "    api_key: planner-test-key\n    thinking: null\n    reasoning_effort: null\n"
                              "  executor:\n"
                              "    model_name: custom/model-name\n    api_base: http://127.0.0.1:3425/v1\n"
                              "    api_key: magpie\n    thinking: null\n    reasoning_effort: null\n", encoding="utf-8")
            for entry in (run.main, benchmark.main):
                with self.subTest(entry=entry.__module__):
                    entry(["--config", str(config), "--run-dir", str(Path(directory) / entry.__module__),
                           "--data-dir", directory, "--gamefiles", str(Path(directory) / "gamefiles.json")])
                    self.assertEqual(run_benchmark.await_args.args[3],
                                     {"planner": "planner-test-key", "executor": "magpie"})
                    self.assertEqual(tuple(run_benchmark.await_args.kwargs["model_order"]), ("custom/model-name",))
                    expected = {"planner": ("http://planner.test/v1", "custom/planner-name"),
                                "executor": ("http://127.0.0.1:3425/v1", "custom/model-name")}
                    for role, settings in run_benchmark.await_args.kwargs["model_settings"].items():
                        self.assertEqual((settings["base_url"], settings["model"]), expected[role])
                        self.assertNotIn("api_key", settings)
                        self.assertNotIn("thinking", settings)
                        self.assertNotIn("reasoning_effort", settings)

    def test_empty_config_key_uses_openai_environment(self):
        with (tempfile.TemporaryDirectory() as directory,
              patch.dict(os.environ, OPENAI_API_KEY="environment-test-key")):
            config = Path(directory) / "config.yaml"
            for explicit_role, section in (("planner", "planner_generation"), ("executor", "executor")):
                with self.subTest(explicit_role=explicit_role):
                    config.write_text(f"toolkit:\n  {section}:\n    api_key: configured-test-key\n",
                                      encoding="utf-8")
                    settings, keys = run.load_model_settings(config)
                    self.assertEqual(keys[explicit_role], "configured-test-key")
                    self.assertEqual(keys["executor" if explicit_role == "planner" else "planner"],
                                     "environment-test-key")
                    self.assertNotIn("configured-test-key", json.dumps(settings))
                    self.assertNotIn("environment-test-key", json.dumps(settings))

    async def test_model_calls_use_the_client_for_each_role(self):
        clients = {
            role: SimpleNamespace(complete=AsyncMock(return_value=SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=f"{role}-reply", tool_calls=None),
                                         finish_reason="stop")], usage=None, model=role, id=role,
            ))) for role in ("planner", "executor")
        }
        for role in clients:
            result = await model_call(clients, role)([{"role": "user", "content": "Choose a step."}])
            self.assertEqual(result["text"], f"{role}-reply")
        for client in clients.values():
            client.complete.assert_awaited_once()

    async def test_role_reasoning_configuration_controls_request_fields(self):
        defaults, _keys = run.load_model_settings()
        recorded_keys = {"model", "base_url", "timeout", "seed", "temperature", "max_tokens", "stop",
                         "reasoning_effort"}
        for settings in defaults.values():
            self.assertEqual(set(settings), recorded_keys)
            self.assertEqual(settings["reasoning_effort"], "none")
        cases = (
            ({"planner": {"thinking": None, "reasoning_effort": "high"},
              "executor": {"thinking": None, "reasoning_effort": "none"}},
             {"planner": {"reasoning_effort": "high"}, "executor": {"reasoning_effort": "none"}}),
            ({"planner": {"thinking": "enabled", "reasoning_effort": None},
              "executor": {"thinking": "disabled", "reasoning_effort": None}},
             {"planner": {"extra_body": {"thinking": {"type": "enabled"}}},
              "executor": {"extra_body": {"thinking": {"type": "disabled"}}}}),
            ({"planner": {"thinking": "enabled", "reasoning_effort": "medium"},
              "executor": {"thinking": None, "reasoning_effort": None}},
             {"planner": {"reasoning_effort": "medium", "extra_body": {"thinking": {"type": "enabled"}}},
              "executor": {}}),
        )
        response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="reply", tool_calls=None), finish_reason="stop")],
            usage=None, model="fake-model", id="id",
        )
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.yaml"
            for configured, expected in cases:
                with self.subTest(configured=configured):
                    config.write_text(json.dumps({"toolkit": {"planner_generation": configured["planner"],
                                                             "executor": configured["executor"]}}), encoding="utf-8")
                    settings, _keys = run.load_model_settings(config)
                    clients = {role: SimpleNamespace(complete=AsyncMock(return_value=response)) for role in settings}
                    for role, client in clients.items():
                        await model_call(clients, role, model_settings=settings)([{"role": "user", "content": "Task"}])
                        payload = client.complete.await_args.kwargs
                        self.assertEqual({name: payload[name] for name in ("reasoning_effort", "extra_body")
                                          if name in payload}, expected[role])

    async def test_configured_transport_is_recorded_without_key(self):
        task = {"task_id": "sample", "executor_limit": 4}
        dataset = {"name": "ALFWorld", "selection": "single_task", "tasks": [task]}
        connections = {"planner": ("http://planner.test/v1", "planner-test-key"),
                       "executor": ("https://configured.invalid/v1", "executor-test-key")}
        models = {"planner": "custom/planner-name", "executor": "custom/model-name"}
        clients, closed = {}, []

        @asynccontextmanager
        async def transport(**options):
            role = next(role for role, (url, _key) in connections.items() if options["base_url"] == url)
            self.assertEqual(options["api_key"], connections[role][1])
            clients[role] = SimpleNamespace(complete=AsyncMock(return_value=SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=f"{role}-reply", tool_calls=None),
                                         finish_reason="stop")], usage=None, model=role, id=role,
            )))
            try:
                yield clients[role]
            finally:
                closed.append(role)

        async def run_one(_row, client, *, mode, workspace_id, save, model_settings, **_kwargs):
            events = []
            for role in ("executor",) if mode == "eo" else ("planner", "executor"):
                self.assertEqual(model_settings[role]["base_url"], connections[role][0])
                self.assertEqual(model_settings[role]["model"], models[role])
                result = await model_call(client, role, model_settings=model_settings)(
                    [{"role": "user", "content": "Choose a step."}],
                )
                self.assertEqual(result["text"], f"{role}-reply")
                events.append({"type": "model_call", "role": role, "response": result})
            outcome = {"reason": "task_finish", "success": True, "reward": 1}
            record = {"mode": mode, "workspace_id": workspace_id, "outcome": outcome,
                      "events": [*events, {"type": "stop", **outcome},
                                 {"type": "verifier", "timestamp": "end", **outcome}]}
            save(record)
            return record

        with (tempfile.TemporaryDirectory() as directory,
              patch.object(benchmark, "AsyncChatClient", side_effect=transport) as client_factory,
              patch.object(benchmark, "source_version", return_value={}),
              patch.object(benchmark, "runtime_versions", return_value={}),
              patch.dict(os.environ, {benchmark.UNPACED_ENV: "1"}),
              redirect_stdout(StringIO())):
            config = Path(directory) / "config.yaml"
            config.write_text("toolkit:\n  planner_generation:\n    model_name: custom/planner-name\n"
                              "    api_base: http://planner.test/v1\n    api_key: planner-test-key\n"
                              "  executor:\n    model_name: custom/model-name\n"
                              "    api_base: https://configured.invalid/v1\n"
                              "    api_key: executor-test-key\n", encoding="utf-8")
            settings, keys = run.load_model_settings(config)
            run_dir = Path(directory) / "run"
            await benchmark.run_matrix(run_dir, {"sample": task}, dataset, keys, run_one=run_one,
                                       concurrency=1, protocol_version=FRAMEWORK_PROTOCOL,
                                       model_order=(settings["executor"]["model"],), model_settings=settings)
            self.assertEqual(client_factory.call_count, 2)
            self.assertEqual(clients["planner"].complete.await_count, 5)
            self.assertEqual(clients["executor"].complete.await_count, 6)
            for role, client in clients.items():
                self.assertEqual(client.complete.await_args.kwargs["model"], models[role])
            self.assertCountEqual(closed, ["planner", "executor"])
            manifest = read_json(run_dir / "manifest.json")
            self.assertEqual(manifest["model_order"], ["custom/model-name"])
            for role, (url, _key) in connections.items():
                self.assertEqual(manifest["models"]["custom/model-name"][role]["base_url"], url)
                self.assertEqual(manifest["models"]["custom/model-name"][role]["model"], models[role])
            self.assertEqual(manifest["trial_counts"], {"complete": 6})
            for path in run_dir.rglob("*.json"):
                for _url, key in connections.values():
                    self.assertNotIn(key, path.read_text(encoding="utf-8"))

    async def test_tool_protocol_model_adapter_preserves_tool_call_and_measures_full_request(self):
        tool = {"type": "function", "function": {"name": "request_plan", "parameters": {"type": "object"}}}
        choice = {"type": "function", "function": {"name": "request_plan"}}
        call = {"id": "call-1", "type": "function", "function": {"name": "request_plan", "arguments": "{}"}}
        item = SimpleNamespace(model_dump=lambda **_options: call)
        response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=None, tool_calls=[item]), finish_reason="tool_calls")],
            usage=None, model=run.MODEL_SETTINGS["executor"]["model"], id="id",
        )
        client = SimpleNamespace(complete=AsyncMock(return_value=response))
        messages = [{"role": "user", "content": "先定计划"}]
        complete = model_call(client, "executor")
        result = await complete(messages, tools=[tool], tool_choice=choice)
        self.assertEqual(result.get("tool_calls"), [call])
        self.assertEqual(result["text"], "")
        payload = client.complete.await_args.kwargs
        self.assertEqual((payload["tools"], payload["tool_choice"]), ([tool], choice))
        size = len(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
        check = model_call(client, "executor", max_input_bytes=size - 1)
        with self.assertRaises(PromptBudgetExceeded):
            await check(messages, tools=[tool], tool_choice=choice)
        client.complete.assert_awaited_once()

    async def test_tool_protocol_single_task_dispatches_six_arms_without_role_limits(self):
        task = {"task_id": "2", "executor_limit": 4}
        dataset = {"name": "ALFWorld", "selection": "single_task", "tasks": [task]}
        model = run.MODEL_SETTINGS["executor"]["model"]
        base_url = run.MODEL_SETTINGS["executor"]["base_url"]
        modes = []

        async def run_one(row, client, *, mode, model_settings, planner_limit, return_every, save, **kwargs):
            self.assertIs(row, task)
            self.assertEqual((planner_limit, return_every, kwargs["executor_limit"]), (None, None, 4))
            self.assertEqual(model_settings["executor"]["model"], model)
            self.assertEqual(kwargs["protocol_version"], FRAMEWORK_PROTOCOL)
            modes.append(mode)
            outcome = {"reason": "task_finish", "success": True, "reward": 1}
            record = {"mode": mode, "workspace_id": kwargs["workspace_id"], "outcome": outcome,
                      "events": [{"type": "stop", **outcome}, {"type": "verifier", "timestamp": "end", **outcome}]}
            save(record)
            return record

        with (tempfile.TemporaryDirectory() as directory,
              patch.object(benchmark, "AsyncChatClient", side_effect=offline_client) as client_factory,
              patch.object(benchmark, "source_version", return_value={}),
              patch.object(benchmark, "runtime_versions", return_value={}),
              redirect_stdout(StringIO())):
            run_dir = Path(directory) / "run"
            await benchmark.run_matrix(run_dir, {"2": task}, dataset, "test-key", run_one=run_one,
                                       concurrency=1, protocol_version=FRAMEWORK_PROTOCOL, model_order=(model,))
            self.assertEqual(client_factory.call_args.kwargs["api_key"], "test-key")
            self.assertEqual(client_factory.call_args.kwargs["base_url"], base_url)
            manifest = read_json(run_dir / "manifest.json")
            self.assertEqual(manifest["protocol_version"], FRAMEWORK_PROTOCOL)
            self.assertEqual(manifest["modes"], list(FRAMEWORK_MODES))
            self.assertEqual(modes, list(FRAMEWORK_MODES))
            self.assertNotIn("planner_limits", manifest["budget"])
            self.assertNotIn("return_every", manifest["budget"])
            self.assertEqual(manifest["models"][model]["executor"]["base_url"], base_url)
            self.assertEqual(manifest["trial_counts"], {"complete": 6})
            for trial in manifest["trials"].values():
                saved = read_json(run_dir / trial["file"])
                self.assertEqual(saved["protocol_version"], FRAMEWORK_PROTOCOL)
                self.assertEqual(saved["plan_scope"], PLAN_SCOPES[trial["mode"]])

    async def test_historical_protocols_cannot_be_resumed_or_relabelled(self):
        task = {"task_id": "2", "executor_limit": 4}
        dataset = {"name": "ALFWorld", "tasks": [task]}
        with (tempfile.TemporaryDirectory() as directory,
              patch.object(benchmark, "AsyncChatClient") as client_factory):
            run_dir = Path(directory)
            write_json(run_dir / "trial.json", {"messages": ["Keep the historical request."]})
            for historical in ("native-tools-v1", "two-phase-v1"):
                write_json(run_dir / "manifest.json", {"protocol_version": historical})
                original = {path.name: path.read_bytes() for path in run_dir.iterdir()}
                with self.assertRaisesRegex(ValueError, "historical runs are read-only"):
                    benchmark.requested_protocol(run_dir, resume=True)
                run_one = AsyncMock()
                for requested in (None, FRAMEWORK_PROTOCOL, historical):
                    with self.subTest(historical=historical, requested=requested):
                        with self.assertRaisesRegex(ValueError, "historical runs are read-only"):
                            await benchmark.run_matrix(run_dir, {"2": task}, dataset, "unused", run_one=run_one,
                                                       resume=True, protocol_version=requested)
                client_factory.assert_not_called()
                run_one.assert_not_awaited()
                self.assertEqual({path.name: path.read_bytes() for path in run_dir.iterdir()}, original)

    async def test_alfworld_runner_preserves_two_phase_calls_and_replanning_receipt(self):
        class Environment(BaseEnv):
            def __init__(self):
                super().__init__(observation="A room.", instruction="Choose an action.", max_steps=4)
                self.actions = []

            def execute_action(self, action):
                self.actions.append(action)
                done = action == "finish"
                return ActionResult("Task finished." if done else "An object is visible.",
                                    float(done), True, done=done, success=done)

        def response(value):
            calls = None
            if isinstance(value, dict):
                calls = [SimpleNamespace(model_dump=lambda tool_call=value, **_options: tool_call)]
                value = None
            return SimpleNamespace(choices=[SimpleNamespace(
                message=SimpleNamespace(content=value, tool_calls=calls),
                finish_reason="tool_calls" if calls else "stop",
            )], usage=None, model="offline", id="offline")

        request = {"type": "function", "id": "plan-request", "function": {
            "name": "request_plan", "arguments": json.dumps({"reason": "An object is visible."}),
        }}
        stage = {"stage_objective": "Inspect and finish the task.", "completion_condition": "Task is finished."}
        for mode in ("pe-d-f", "pc-s"):
            with self.subTest(mode=mode):
                env, calls = Environment(), []
                initial = {"thinking_summary": "Inspect the room.",
                           **({"full_plan": [{"id": 1, **stage}]} if mode == "pe-d-f" else stage)}
                replies = {
                    "planner": iter([json.dumps(initial),
                                     json.dumps({"thinking_summary": "Continue.", **({"keep": True} if mode == "pe-d-f" else {})}),
                                     "Judgment: The environment finished."]),
                    "executor": iter(["Action: inspect", *([request] if mode == "pe-d-f" else []), "Action: finish"]),
                }

                def complete(role):
                    async def call(**options):
                        calls.append((role, options))
                        return response(next(replies[role]))
                    return call

                clients = {role: SimpleNamespace(complete=complete(role)) for role in replies}
                pool = SimpleNamespace(open_slot=lambda: nullcontext(SimpleNamespace(load_task=lambda _row: object())))
                with patch.object(run, "AlfWorldEnv", return_value=env):
                    record = await run.run_matched_trial(
                        pool, {"id": 2, "task": "Room\nYour task is to: inspect and finish."}, clients,
                        mode=mode, workspace_id="offline", save=lambda _record: None,
                        executor_limit=4, protocol_version=FRAMEWORK_PROTOCOL,
                    )
                self.assertEqual(record["protocol_version"], FRAMEWORK_PROTOCOL)
                self.assertNotIn("constraints", record)
                self.assertTrue(all("hard_constraints" not in event for event in record["events"]))
                self.assertNotIn("Hard constraints", json.dumps(calls))
                self.assertEqual(env.actions, ["inspect", "finish"])
                self.assertTrue(record["outcome"]["success"])
                expected = (["planner", "executor", "executor", "planner", "executor"] if mode == "pe-d-f"
                            else ["planner", "executor", "planner", "executor", "planner"])
                self.assertEqual([role for role, _options in calls], expected)
                self.assertTrue(all("tools" not in options and "tool_choice" not in options
                                    for role, options in calls if role == "planner" or mode == "pc-s"))
                if mode == "pe-d-f":
                    self.assertNotIn("tool_choice", calls[1][1])
                    messages = calls[-1][1]["messages"]
                    self.assertEqual(messages[-1]["role"], "tool")
                    self.assertEqual(messages[-1]["tool_call_id"], "plan-request")

    async def test_shared_rate_file_paces_distinct_clients_and_ignores_old_boot(self):
        transport = SimpleNamespace(complete=AsyncMock(return_value="reply"))
        with tempfile.TemporaryDirectory() as directory:
            rate_file = Path(directory) / "rate"
            rate_file.write_text("old-boot 9000\n", encoding="ascii")
            with (patch.dict(os.environ, PLANNER_BENCHMARK_RATE_FILE=str(rate_file)),
                  patch.object(benchmark, "monotonic", side_effect=[100.0, 100.0, 100.0, 100.6]),
                  patch.object(benchmark.asyncio, "sleep", new_callable=AsyncMock) as sleep):
                first = benchmark.PacedClient(transport)
                second = benchmark.PacedClient(transport)
                self.assertEqual(await first.complete(model="first"), "reply")
                self.assertEqual(await second.complete(model="second"), "reply")
            sleep.assert_awaited_once()
            self.assertAlmostEqual(sleep.await_args.args[0], 0.6)
            self.assertEqual(transport.complete.await_count, 2)
            boot, timestamp = rate_file.read_text(encoding="ascii").split()
            self.assertEqual(boot, first.boot_id)
            self.assertAlmostEqual(float(timestamp), 101.2)

    async def test_unconfigured_rate_remains_local_to_each_client(self):
        transport = SimpleNamespace(complete=AsyncMock())
        with (patch.dict(os.environ, PLANNER_BENCHMARK_RATE_FILE=""),
              patch.object(benchmark, "REQUESTS_PER_MINUTE", 1),
              patch.object(benchmark.asyncio, "sleep", new_callable=AsyncMock) as sleep):
            first = benchmark.PacedClient(transport)
            second = benchmark.PacedClient(transport)
            await first.complete()
            await second.complete()
            sleep.assert_not_awaited()
            await first.complete()
        sleep.assert_awaited_once()
        self.assertGreater(sleep.await_args.args[0], 0)

    async def test_role_clients_share_request_pacing(self):
        planner = SimpleNamespace(complete=AsyncMock(return_value="plan"))
        executor = SimpleNamespace(complete=AsyncMock(return_value="action"))
        with (patch.dict(os.environ, PLANNER_BENCHMARK_RATE_FILE=""),
              patch.object(benchmark, "REQUESTS_PER_MINUTE", 1),
              patch.object(benchmark.asyncio, "sleep", new_callable=AsyncMock) as sleep):
            first = benchmark.PacedClient(planner)
            second = benchmark.PacedClient(executor, pacer=first)
            self.assertEqual(await first.complete(model="planner-model"), "plan")
            sleep.assert_not_awaited()
            self.assertEqual(await second.complete(model="executor-model"), "action")
        sleep.assert_awaited_once()
        self.assertGreater(sleep.await_args.args[0], 0)
        planner.complete.assert_awaited_once_with(model="planner-model")
        executor.complete.assert_awaited_once_with(model="executor-model")

    async def test_partial_alfworld_catalog_cannot_claim_full_split(self):
        partial_split = [{"id": "1", "task": "A test goal", "gamefile": "only-one"}]
        with patch.object(benchmark, "load_alfworld_rows", return_value=partial_split):
            with self.assertRaisesRegex(ValueError, "all 134 official test games"):
                await benchmark.run_benchmark(Path("unused"), Path("unused"), Path("unused"), "unused")

    def test_json_codec_preserves_plain_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            plain = Path(directory) / "trial.json"
            compressed = Path(directory) / "trial.json.gz"
            value = {"task": "测量", "events": [{"text": "重复的观察"}] * 100}
            for path in (plain, compressed):
                write_json(path, value)
                self.assertEqual(read_json(path), value)
            self.assertEqual(plain.read_text(encoding="utf-8"), json.dumps(value, ensure_ascii=False, indent=2) + "\n")
            self.assertEqual(gzip.decompress(compressed.read_bytes()), plain.read_bytes())

    def test_startup_error_before_any_events_has_zero_request_cost(self):
        cost = Counter()
        accumulate_attempt_cost(cost, {"status": "error", "error": "OSError", "events": []})
        self.assertEqual(benchmark_token_count(cost, "total_tokens"), "0")
        accumulate_attempt_cost(cost, {})
        self.assertEqual(benchmark_token_count(cost, "total_tokens"), "未知")

    def test_retry_budget_ignores_archived_startup_error_before_any_events(self):
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory)
            trial = {"status": "unscored", "error": "APIConnectionError", "file": "trial.json",
                     "archived_attempts": ["startup.json"]}
            write_json(run / "startup.json", {"status": "error", "error": "OSError", "events": []})
            write_json(run / "trial.json", {"status": "unscored", "events": [{"type": "model_call"}]})
            self.assertTrue(benchmark.can_retry_trial(run, trial))
            trial["archived_attempts"].append("model.json")
            write_json(run / "model.json", {"status": "unscored", "events": [{"type": "model_call"}]})
            self.assertFalse(benchmark.can_retry_trial(run, trial))

    async def test_model_selection_preserves_trial_identity_and_checks_resume(self):
        dataset = {"tasks": [{"task_id": "sample", "executor_limit": 4}], "compress_traces": True}
        rows = {"sample": dataset["tasks"][0]}
        model = benchmark.MODELS[0]
        with (tempfile.TemporaryDirectory() as directory,
              patch.object(benchmark, "source_version", return_value={}),
              patch.object(benchmark, "runtime_versions", return_value={}),
              patch.object(benchmark, "run_pending", new_callable=AsyncMock) as run_pending):
            run_dir = Path(directory)
            full = benchmark.scheduled_manifest(dataset, "run-id")
            for invalid in (model, (model, model)):
                with self.assertRaises(ValueError):
                    benchmark.scheduled_manifest(dataset, "run-id", model_order=invalid)
            selected = benchmark.scheduled_manifest(dataset, "run-id", model_order=(model,))
            self.assertEqual(full["model_order"], list(benchmark.MODELS))
            self.assertEqual(selected["model_order"], [model])
            self.assertEqual(selected["trials"], {key: trial for key, trial in full["trials"].items()
                                                   if trial["model"] == model})
            write_json(run_dir / "manifest.json", selected)
            await benchmark.run_matrix(run_dir, rows, dataset, "unused", run_one=None, resume=True,
                                       model_order=(model,))
            with self.assertRaisesRegex(ValueError, "Saved schedule or runtime differs"):
                await benchmark.run_matrix(run_dir, rows, dataset, "unused", run_one=None, resume=True)
            run_pending.assert_awaited_once()

    async def test_resume_and_report_read_both_trace_formats(self):
        task = {"task_id": "example", "goal": "测量样品", "executor_limit": 4}
        rows = {"example": task}

        async def run_one(_task, _client, *, mode, workspace_id, save, **_limits):
            if mode == "eo" and workspace_id.endswith("/attempt-1"):
                raise APIConnectionError
            outcome = {"reason": "environment_done", "reward": 0.75, "success": False}
            record = {
                "mode": mode, "workspace_id": workspace_id, "outcome": outcome,
                "events": [{"type": "stop", "timestamp": "end", "reason": outcome["reason"]},
                           {"type": "verifier", "timestamp": "end", **outcome}],
            }
            save(record)
            return record

        with (tempfile.TemporaryDirectory() as directory,
              patch.object(benchmark, "AsyncChatClient", offline_client),
              patch.object(benchmark, "MODELS", ("offline",)),
              patch.object(benchmark, "source_version", return_value={}),
              patch.object(benchmark, "runtime_versions", return_value={}),
              redirect_stdout(StringIO())):
            output = Path(directory) / "report.html"
            for suffix, options in ((".json", {}), (".json.gz", {"compress_traces": True})):
                with self.subTest(suffix=suffix):
                    dataset = {"name": "Storage test", "split": "test", "selection": "full_split",
                               "canonical_task_count": 1, "tasks": [task], **options}
                    run_dir = output.parent / f"run{suffix}"
                    trial_id = "m1-texample-eo"
                    record_path = f"trials/{trial_id}{suffix}"
                    archive_path = f"attempts/{trial_id}/attempt-000001{suffix}"
                    with patch.dict(os.environ, {benchmark.RATE_FILE_ENV: str(output.parent / "matrix.rate")}):
                        await benchmark.run_matrix(run_dir, rows, dataset, "unused", run_one=run_one, concurrency=1)
                    self.assertEqual(read_json(run_dir / record_path)["error"], "APIConnectionError")
                    missing_html = render_benchmark(run_dir, output, "storage-test")
                    self.assertNotIn(f'href="{run_dir.name}/{record_path}"', missing_html)
                    self.assertIn('aria-label="offline · EO · 任务 example · 缺评 · '
                                  '运行启动或基础设施错误 · APIConnectionError"', missing_html)
                    self.assertIn(">缺评</td>", missing_html)

                    await benchmark.run_matrix(run_dir, rows, dataset, "unused", run_one=run_one,
                                               concurrency=1, resume=True)
                    self.assertEqual(read_json(run_dir / archive_path)["attempt"], 1)
                    self.assertEqual(read_json(run_dir / record_path)["attempt"], 2)

                    await benchmark.run_matrix(run_dir, rows, dataset, "unused", run_one=run_one,
                                               concurrency=1, resume=True)
                    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
                    self.assertEqual(manifest["invocations"][0]["dispatch_rate_scope"], "host_shared")
                    self.assertEqual(manifest["trials"][trial_id]["archived_attempts"], [archive_path])
                    self.assertEqual(manifest["invocations"][-1]["pending_trials"], 0)
                    self.assertEqual(manifest["trial_counts"], {"complete": 4})
                    html = render_benchmark(run_dir, output, "storage-test")
                    self.assertIn(f'href="{run_dir.name}/{record_path}"', html)
                    self.assertNotIn(f'href="{run_dir.name}/{archive_path}"', html)
                    self.assertIn("已把 1 / 1 条归档尝试中可核对的消耗计入总量。", html)
                    self.assertIn(">0.75</a>", html)

                    stale = benchmark.scheduled_manifest(dataset, manifest["run_id"])
                    observed = matched_trials(run_dir, stale, preview=True)["offline", "example", "eo"]
                    self.assertEqual(observed.score, 0.75)
                    self.assertEqual(observed.past, (run_dir / archive_path,))

    def test_report_compares_common_tasks_and_validates_attempts(self):
        with (tempfile.TemporaryDirectory() as directory,
              patch.object(benchmark, "MODELS", ("first", "second")),
              patch.object(benchmark, "source_version", return_value={}),
              patch.object(benchmark, "runtime_versions", return_value={})):
            run_dir = Path(directory)
            dataset = {"name": "ScienceWorld", "split": "test", "selection": "full_split",
                       "canonical_task_count": 2, "tasks": [{"task_id": "a"}, {"task_id": "b"}]}
            manifest = benchmark.scheduled_manifest(dataset, "example")
            manifest["status"] = "complete"
            missing_trial = "m2-tb-pc"
            for trial_id, trial in manifest["trials"].items():
                if trial_id == missing_trial:
                    trial["status"] = "error"
                    continue
                trial["status"] = "complete"
                score = 0.75 if trial["task_id"] == "a" else 1
                outcome = {"reason": "task_finish", "reward": score, "success": score == 1}
                record = {**trial, "run_id": manifest["run_id"], "attempt": 1, "outcome": outcome,
                          "events": [{"type": "stop", "reason": outcome["reason"]},
                                     {"type": "verifier", **outcome}]}
                write_json(run_dir / manifest["records"][trial_id], record)
            manifest_path = run_dir / "manifest.json"
            output = run_dir / "report.html"
            write_json(manifest_path, manifest)
            html = render_benchmark(run_dir, output, "comparison")
            self.assertIn("有效评分 15 / 16。全配置配对任务 1 / 2。", html)
            for model, count, average in (("first", 2, "0.875"), ("second", 1, "0.75")):
                self.assertIn(
                    f'{model}<br><span class="small">配对任务 {count} / 2</span></th>'
                    '<th scope="row" class="mode">EO</th><td class="number">0.875</td>'
                    f'<td class="number">{average}</td><td class="number"><strong>0.75</strong></td>', html,
                )
            self.assertIn("ScienceWorld 模拟器分数除以 100", html)
            self.assertIn("/sciworld_benchmark.py", html)

            trial = manifest["trials"][missing_trial]
            trial["status"] = "complete"
            write_json(manifest_path, manifest)
            with self.assertRaisesRegex(ValueError, "score and completed status disagree"):
                render_benchmark(run_dir, output, "comparison")

            trial["status"] = "error"
            trial["archived_attempts"] = [trial["file"]]
            write_json(manifest_path, manifest)
            with self.assertRaisesRegex(ValueError, "Duplicate benchmark attempt path"):
                render_benchmark(run_dir, output, "comparison")

    def test_report_keeps_raw_trace_and_validates_native_webshop_replay(self):
        with (tempfile.TemporaryDirectory() as directory,
              patch.object(benchmark, "MODELS", ("offline",)),
              patch.object(benchmark, "source_version", return_value={}),
              patch.object(benchmark, "runtime_versions", return_value={})):
            run_dir = Path(directory)
            dataset = {"name": "WebShop", "split": "test", "selection": "full_split",
                       "canonical_task_count": 1, "tasks": [{"task_id": "a"}], "max_input_bytes": 5}
            manifest = benchmark.scheduled_manifest(dataset, "webshop-run")
            manifest["status"] = "complete"
            for trial in manifest["trials"].values():
                trial["status"] = "error"
            trial_id = "m1-ta-eo"
            trial = manifest["trials"][trial_id]
            trial.update(status="unscored", error="PromptBudgetExceeded")
            identity = {**trial, "run_id": manifest["run_id"], "attempt": 1}
            original_outcome = {"reason": "runtime_error", "reward": None, "success": None}
            messages = [{"role": "user", "content": "找杯子"}]
            events = [{"type": "model_call", "event_id": 1, "role": "executor", "response": None,
                       "messages": messages, "error": "PromptBudgetExceeded"},
                      {"type": "stop", "reason": "runtime_error"}, {"type": "verifier", **original_outcome}]
            original = run_dir / trial["file"]
            write_json(original, {**identity, "outcome": original_outcome, "events": events})
            write_json(run_dir / "manifest.json", manifest)
            sidecar = run_dir / "native-replay" / f"{trial_id}.json"
            input_bytes = len(json.dumps(messages, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
            replay = {**identity, "source": trial["file"], "method": "webshop_native_context_limit_replay",
                      "blocked_call_event_id": 1, "input_bytes": input_bytes, "max_input_bytes": 5,
                      "tool_events_replayed": 0, "outcome": {"reason": "prompt_budget", "reward": 0, "success": False}}
            write_json(sidecar, replay)
            html = render_benchmark(run_dir, run_dir / "report.html", "webshop")
            self.assertIn("有效评分 1 / 4。全配置配对任务 0 / 1。", html)
            self.assertIn(
                'offline<br><span class="small">配对任务 0 / 1</span></th>'
                '<th scope="row" class="mode">EO</th><td class="number">0</td>'
                '<td class="number">未评</td><td class="number"><strong>未评</strong></td>', html,
            )
            self.assertIn(f'href="native-replay/{trial_id}.json"', html)
            self.assertIn(f'href="trials/{trial_id}.json"', html)
            self.assertIn(">0</a>", html)
            self.assertEqual(read_json(original)["outcome"], original_outcome)
            write_json(sidecar, {**replay, "outcome": {"reason": "prompt_budget", "reward": 1, "success": True}})
            with self.assertRaisesRegex(ValueError, "native replay does not match"):
                render_benchmark(run_dir, run_dir / "report.html", "webshop")
            write_json(sidecar, {**replay, "blocked_call_event_id": 2})
            with self.assertRaisesRegex(ValueError, "native replay does not match"):
                render_benchmark(run_dir, run_dir / "report.html", "webshop")

    def test_report_imports_only_matching_terminal_budget_verdict(self):
        with (tempfile.TemporaryDirectory() as directory,
              patch.object(benchmark, "MODELS", ("offline",)),
              patch.object(benchmark, "source_version", return_value={}),
              patch.object(benchmark, "runtime_versions", return_value={})):
            run_dir = Path(directory)
            output = run_dir / "report.html"
            messages = [{"role": "user", "content": "查任务"}]
            size = len(json.dumps(messages, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
            dataset = {"name": "Terminal-Bench", "split": "test", "selection": "reviewed_subset",
                       "canonical_task_count": 66, "source_commit": "official", "data_version": "v4.1.0",
                       "tasks": [{"task_id": "a", "task_version": "2.2.1"}], "max_input_bytes": size - 1}
            manifest = benchmark.scheduled_manifest(dataset, "terminal-run")
            manifest["status"] = "complete"
            for trial in manifest["trials"].values():
                trial["status"] = "error"
            trial = manifest["trials"]["m1-ta-eo"]
            trial.update(status="unscored", error="PromptBudgetExceeded")
            original = run_dir / trial["file"]
            manifest_path = run_dir / "manifest.json"
            result = run_dir / "harbor/a-native/result.json"
            lock = result.with_name("lock.json")
            harbor = {"release": "v4.1.0", "commit": "official", "task_version": "2.2.1",
                      "agent_network": "no-network", "verifier_phase_network": "no-network",
                      "result": str(result), "lock": str(lock)}
            outcome = {"reason": "runtime_error", "reward": None, "success": None}
            call = {"type": "model_call", "role": "executor", "status": "error", "response": None,
                    "messages": messages, "error": "PromptBudgetExceeded"}
            verdict = {"type": "verifier", **outcome, "native_result": str(result),
                       "timestamp": "2026-11-19T10:00:00+00:00"}
            events = [call, {"type": "execution_feedback", "return_reason": "runtime_error"},
                      {"type": "runtime_error", "error": "PromptBudgetExceeded"},
                      {"type": "stop", "reason": "runtime_error"}, verdict]
            record = {**trial, "run_id": manifest["run_id"], "attempt": 1, "outcome": outcome,
                      "events": events, "harbor": harbor}
            native = {"task_name": "terminal-bench/a", "finished_at": "2026-11-19T10:00:00Z",
                      "trial_name": "a-native", "reward_valid": True, "exception_info": None,
                      "verifier_environment_mode": "separate", "verifier_result": {"rewards": {"reward": 0}}}
            locked = {"task": {"name": "a", "version": "2.2.1"}}
            write_json(lock, locked)
            write_json(result, native)
            write_json(original, record)
            write_json(manifest_path, manifest)

            html = render_benchmark(run_dir, output, "terminal")
            self.assertIn("有效评分 1 / 4", html)
            self.assertIn("1 格在本地输入预算处停止", html)
            self.assertIn('href="harbor/a-native/result.json"', html)
            self.assertIn('href="trials/m1-ta-eo.json"', html)
            self.assertNotIn("原生重放", html)
            self.assertEqual(read_json(original), record)
            self.assertEqual(read_json(manifest_path), manifest)

            for name, path, changed, baseline in (
                ("provider fault", original, {**record, "events": [
                    {**call, "error": "RateLimitError"}, events[1],
                    {**events[2], "error": "RateLimitError"}, *events[-2:],
                ]}, record),
                ("tool after local rejection", original,
                 {**record, "events": [call, {"type": "tool_event", "action": "look"}, *events[1:]]}, record),
                ("response present", original, {**record, "events": [{**call, "response": {}}, *events[1:]]}, record),
                ("unlinked result", original,
                 {**record, "events": [*events[:-1], {**verdict, "native_result": str(lock)}]}, record),
                ("wrong source commit", original, {**record, "harbor": {**harbor, "commit": "other"}}, record),
                ("wrong task lock", lock, {"task": {"name": "a", "version": "2.2.0"}}, locked),
                ("invalid reward", result, {**native, "reward_valid": False}, native),
                ("wrong result time", result, {**native, "finished_at": "2026-11-19T11:00:00Z"}, native),
                ("native exception", result, {**native, "exception_info": {"type": "Error"}}, native),
                ("shared environment", result, {**native, "verifier_environment_mode": "shared"}, native),
                ("at byte limit", manifest_path,
                 {**manifest, "budget": {**manifest["budget"], "max_input_bytes_per_request": size}}, manifest),
            ):
                with self.subTest(name=name):
                    write_json(path, changed)
                    self.assertIn("有效评分 0 / 4", render_benchmark(run_dir, output, "terminal"))
                    write_json(path, baseline)

            external_lock = run_dir / "external-lock.json"
            write_json(external_lock, locked)
            lock.unlink()
            lock.symlink_to(external_lock)
            self.assertIn("有效评分 0 / 4", render_benchmark(run_dir, output, "terminal"))

    def test_report_combines_only_disjoint_matching_terminal_supplements(self):
        with (tempfile.TemporaryDirectory() as directory,
              patch.object(benchmark, "MODELS", ("offline",)),
              patch.object(benchmark, "source_version", return_value={}),
              patch.object(benchmark, "runtime_versions", return_value={})):
            root = Path(directory)
            runs = []
            for task_id in ("a", "b"):
                run_dir = root / task_id
                dataset = {"name": "Terminal-Bench", "split": "test", "selection": "reviewed_subset",
                           "canonical_task_count": 66, "source_commit": "official", "tasks": [{"task_id": task_id}]}
                manifest = benchmark.scheduled_manifest(dataset, task_id)
                manifest["status"] = "complete"
                for trial in manifest["trials"].values():
                    trial["status"] = "complete"
                    outcome = {"reason": "task_finish", "reward": 0, "success": False}
                    record = {**trial, "run_id": task_id, "attempt": 1, "outcome": outcome,
                              "events": [{"type": "stop", "reason": "task_finish"}, {"type": "verifier", **outcome}]}
                    write_json(run_dir / trial["file"], record)
                write_json(run_dir / "manifest.json", manifest)
                runs.append((run_dir, manifest))
            output = root / "report.html"
            html = render_benchmark(runs[0][0], output, "terminal", supplements=runs[1:])
            self.assertIn("2 / 66 个官方任务", html)
            self.assertIn("有效评分 8 / 8", html)
            self.assertIn('href="b/trials/m1-tb-eo.json"', html)
            with self.assertRaisesRegex(ValueError, "duplicate configurations"):
                render_benchmark(runs[0][0], output, "terminal", supplements=runs[:1])
            runs[1][1]["benchmark"]["source_commit"] = "different"
            with self.assertRaisesRegex(ValueError, "differs from the completed matching protocol"):
                render_benchmark(runs[0][0], output, "terminal", supplements=runs[1:])
