import json
import os
from contextlib import contextmanager
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import sciworld_benchmark as sciworld
import webshop_benchmark as webshop


class ConnectionEntrypointsTest(unittest.TestCase):
    def test_recipe_connection_and_models_reach_backend_runners(self):
        with TemporaryDirectory() as directory:
            config = Path(directory) / "config.yaml"
            config.write_text(
                "models: [custom-model]\ntoolkit:\n  planner_generation:\n    model_name: planner-model\n"
                "    api_base: http://planner.test/v1\n    api_key: planner-key\n  executor:\n"
                "    model_name: custom-model\n    api_base: http://executor.test/v1\n    api_key: executor-key\n"
                "  context_window:\n    max_input_tokens: 12345\n",
                encoding="utf-8",
            )
            entries = (
                (sciworld, "run_sciworld", 3,
                 ["--catalog-dir", directory, "--run-dir", directory, "--step-limits", directory,
                  "--model", "override-model"]),
                (webshop, "run_webshop", 2, ["--run-dir", directory, "--data-dir", directory]),
            )
            for module, name, key_index, args in entries:
                with (self.subTest(backend=module.__name__),
                      patch.dict(os.environ, {}, clear=True),
                      patch.object(module, name, new_callable=AsyncMock) as dispatch,
                      patch.object(sys, "argv", [module.__name__, "--config", str(config), *args])):
                    module.main()
                    self.assertEqual(dispatch.await_args.args[key_index],
                                     {"planner": "planner-key", "executor": "executor-key"})
                    options = dispatch.await_args.kwargs
                    self.assertEqual(options["model_order"], ["custom-model"])
                    self.assertEqual(options["model_settings"]["planner"]["base_url"], "http://planner.test/v1")
                    self.assertEqual(options["model_settings"]["planner"]["model"], "planner-model")
                    self.assertEqual(options["model_settings"]["executor"]["base_url"], "http://executor.test/v1")
                    self.assertEqual(options["model_settings"]["executor"]["model"], "custom-model")
                    self.assertEqual(options["context_window"], {"max_input_tokens": 12345})
                    for key in ("planner-key", "executor-key"):
                        self.assertNotIn(key, json.dumps(options))
                    if module is sciworld:
                        self.assertEqual(options["model"], "override-model")

    def test_offline_entries_do_not_load_connection_config(self):
        with TemporaryDirectory() as directory:
            with (patch.object(sciworld, "load_model_settings", side_effect=AssertionError("Unexpected connection load")),
                  patch.object(sciworld, "prepare_catalog"),
                  patch.object(sys, "argv", ["sciworld", "--config", str(Path(directory) / "missing.yaml"),
                                             "--catalog-dir", directory, "--prepare"])):
                sciworld.main()


def response(text):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text), finish_reason="stop")],
                           usage=None, model="fixture", id="offline")


class BackendTrialContractTest(unittest.IsolatedAsyncioTestCase):
    async def test_webshop_trial_uses_current_window_and_keeps_purchase_score_private(self):
        from toolkit.tasks.webshop import WebShopTask

        task = WebShopTask("0", 0, "Instruction: Buy soap.")
        actions = []

        class Native:
            def reset(self, session):
                return "Search", None

            def get_instruction_text(self):
                return task.observation

            def get_available_actions(self):
                return {"has_search_bar": True, "clickables": ["buy now"]}

            def step(self, action):
                actions.append(action)
                return ("Visible product details", 0, False, {}) if len(actions) == 1 else (
                    "Your score (min 0.0, max 1.0): 1.0", 1, True, {})

        @contextmanager
        def isolated(_server, selected, limit):
            self.assertIs(selected, task)
            yield webshop.WebShopBenchmarkEnv(task, Native(), **{**webshop.webshop_settings(), "max_steps": limit})

        from run import MODEL_SETTINGS
        client = SimpleNamespace(complete=AsyncMock(side_effect=[
            response("Action: search[soap]"), response("Action: click[buy now]"),
        ]))
        with patch.object(webshop, "isolated_environment", new=isolated):
            record = await webshop.run_one(
                None, task, client, mode="eo", workspace_id="offline-webshop", model_settings=MODEL_SETTINGS,
                context_window={"max_input_tokens": 12000}, save=lambda _: None, executor_limit=3,
            )
        self.assertEqual(actions, ["search[soap]", "click[buy now]"])
        self.assertEqual(record["protocol_version"], webshop.FRAMEWORK_PROTOCOL)
        self.assertEqual(record["outcome"], {"reason": "task_finish", "success": True, "reward": 1.0})
        self.assertEqual(record["context_window"], {"max_input_tokens": 12000})
        self.assertEqual([len(call.kwargs["messages"]) for call in client.complete.await_args_list], [1, 1])
        final_feedback = [event for event in record["events"] if event["type"] == "tool_event"][-1]
        self.assertNotIn("1.0", final_feedback["observation"])
        self.assertIn("purchase ended", final_feedback["observation"])

    async def test_sciworld_matrix_passes_the_window_into_the_current_trial(self):
        from run import MODEL_SETTINGS

        task = SimpleNamespace(task_id="find_0", observation="Find the object.", sub_task_name="find", variation_idx=0)

        class Native:
            def get_task_names(self):
                return ["find"]

            def load(self, *args, **kwargs):
                pass

            def get_variations_test(self):
                return [0]

            def reset(self):
                return "An object is visible.", {"taskDesc": task.observation, "score": 0, "valid": ["take object"]}

            def step(self, action):
                self.action = action
                return "The object is held.", 1, True, {"score": 100, "valid": []}

        servers = []

        @contextmanager
        def backend():
            native = Native()
            servers.append(native)
            yield native

        window = {"max_input_tokens": 12000}

        async def matrix(path, rows, dataset, key, *, run_one, context_window, protocol_version, **options):
            self.assertIs(context_window, window)
            self.assertNotIn("max_input_bytes", dataset)
            self.assertNotIn("return_every", dataset)
            client = SimpleNamespace(complete=AsyncMock(return_value=response("Action: take object")))
            record = await run_one(
                rows[task.task_id], client, mode="eo", workspace_id="offline-sciworld", model_settings=MODEL_SETTINGS,
                context_window=context_window, save=lambda _: None, executor_limit=1,
                protocol_version=protocol_version,
            )
            self.assertEqual(record["outcome"], {"reason": "task_finish", "success": True, "reward": 1.0})
            self.assertEqual(record["context_window"], window)
            self.assertEqual(len(client.complete.await_args.kwargs["messages"]), 1)

        with (TemporaryDirectory() as directory,
              patch.object(sciworld.SciWorldTask, "load_tasks", return_value=([task], 1)),
              patch.object(sciworld, "open_sciworld_backend", new=backend),
              patch.object(sciworld, "version", return_value="offline"),
              patch.object(sciworld, "run_matrix", new=matrix),
              patch.dict(sys.modules, {"scienceworld.utils": SimpleNamespace(infer_task=lambda name: name)})):
            limits = Path(directory) / "steps.json"
            limits.write_text('{"find": 1}', encoding="utf-8")
            await sciworld.run_sciworld(Path(directory), Path(directory), limits, "unused", concurrency=1,
                                        resume=False, model_settings=MODEL_SETTINGS, context_window=window)
        self.assertEqual(servers[-1].action, "take object")
