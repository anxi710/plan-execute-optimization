import unittest
from copy import deepcopy
from unittest.mock import patch

from toolkit.models import openai as model_api
from toolkit.utils.config import DEFAULT_CONFIG, resolve_config


class ConfigTest(unittest.TestCase):
    def test_recipe_connection_overrides_preserve_toolkit_defaults(self):
        original = deepcopy(DEFAULT_CONFIG)
        connection = {"api_base": "http://model.test/v1", "api_key": "configured-key"}
        config = resolve_config({"planner_generation": connection, "executor": connection})
        for section in ("planner_generation", "executor"):
            self.assertEqual({name: config[section][name] for name in connection}, connection)
        self.assertEqual(DEFAULT_CONFIG, original)
        with self.assertRaisesRegex(ValueError, "Unknown toolkit setting"):
            resolve_config({"executor": {"unknown": "value"}})
        reasoning = {"thinking": "disabled", "reasoning_effort": "none"}
        config = resolve_config({"planner_generation": reasoning, "executor": reasoning})
        for section in ("planner_generation", "executor"):
            self.assertEqual({name: config[section][name] for name in reasoning}, reasoning)
        with self.assertRaisesRegex(ValueError, "Unknown toolkit setting: deepseek_thinking"):
            resolve_config({"executor": {"deepseek_thinking": "disabled"}})

    def test_chat_client_requires_explicit_connection(self):
        with patch.object(model_api.openai, "AsyncOpenAI") as factory:
            with self.assertRaises(TypeError):
                model_api.AsyncChatClient(timeout=5)
            factory.assert_not_called()
            model_api.AsyncChatClient(base_url="http://planner.test/v1", api_key="planner-key", timeout=5)
            factory.assert_called_once_with(
                base_url="http://planner.test/v1", api_key="planner-key", timeout=5, max_retries=0,
            )

    def test_metered_model_uses_explicit_resolved_settings(self):
        defaults = DEFAULT_CONFIG["executor"]
        for connection in ({}, {"api_base": "http://model.test/v1", "api_key": "configured-key"}):
            with (self.subTest(connection=connection),
                  patch.object(model_api.openai, "OpenAI") as sync_factory):
                settings = {**defaults, **connection}
                model = model_api.MeteredChatModel({**settings, "model_name": "fake-model"})
                sync_factory.assert_called_once_with(
                    base_url=settings["api_base"], api_key=settings["api_key"],
                    timeout=settings["request_timeout"], max_retries=0,
                )
                model.close()
