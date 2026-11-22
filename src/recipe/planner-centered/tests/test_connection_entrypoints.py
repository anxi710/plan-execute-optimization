import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
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
                "    model_name: custom-model\n    api_base: http://executor.test/v1\n    api_key: executor-key\n",
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
                    for key in ("planner-key", "executor-key"):
                        self.assertNotIn(key, json.dumps(options))
                    if module is sciworld:
                        self.assertEqual(options["model"], "override-model")

    def test_offline_entries_do_not_load_connection_config(self):
        with TemporaryDirectory() as directory:
            entries = (
                (sciworld, "prepare_catalog", ["--catalog-dir", directory, "--prepare"]),
                (webshop, "replay_native_context_limits",
                 ["--run-dir", directory, "--data-dir", directory, "--replay-native"]),
            )
            for module, name, args in entries:
                with (self.subTest(backend=module.__name__),
                      patch.object(module, "load_model_settings", side_effect=AssertionError("Unexpected connection load")),
                      patch.object(module, name, return_value=0),
                      patch.object(sys, "argv", [module.__name__, "--config", str(Path(directory) / "missing.yaml"), *args]),
                      patch("builtins.print")):
                    module.main()
