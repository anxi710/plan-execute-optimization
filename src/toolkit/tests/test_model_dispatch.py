import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx

from toolkit.models import openai as model_api
from toolkit.models.base import BaseModel
from toolkit.prompts import PlanInjection
from toolkit.utils.config import DEFAULT_CONFIG


class LocalModel(BaseModel):
    def _complete(self, messages, *, prefix=None):
        return prefix or messages[-1]["content"]

    def close(self):
        self.closed = True


class ModelDispatchTest(unittest.IsolatedAsyncioTestCase):
    def test_reasoning_controls_preserve_assistant_prefix_body(self):
        reply = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))],
                                usage=None, model="fake-model")
        for thinking, effort in ((None, None), ("disabled", None), (None, "none"), ("enabled", "low")):
            with (self.subTest(thinking=thinking, reasoning_effort=effort),
                  patch.object(model_api.openai, "OpenAI") as factory):
                factory.return_value.chat.completions.create.return_value = reply
                model = model_api.MeteredChatModel({
                    **DEFAULT_CONFIG["executor"], "model_name": "fake-model",
                    "thinking": thinking, "reasoning_effort": effort,
                })
                self.assertEqual(model.continue_assistant([{"role": "user", "content": "Task"}], "Continue"), "ok")
                options = factory.return_value.chat.completions.create.call_args.kwargs
                body = options["extra_body"]
                self.assertTrue(body["continue_final_message"])
                self.assertFalse(body["add_generation_prompt"])
                self.assertEqual(options["messages"][-1], {"role": "assistant", "content": "Continue"})
                if thinking is None:
                    self.assertNotIn("thinking", body)
                else:
                    self.assertEqual(body["thinking"], {"type": thinking})
                if effort is None:
                    self.assertNotIn("reasoning_effort", options)
                else:
                    self.assertEqual(options["reasoning_effort"], effort)
                model.close()

    async def test_sync_backend_supports_both_plan_dispatch_paths(self):
        async def run_in_thread(function, *args, **kwargs):
            return function(*args, **kwargs)

        model = LocalModel()
        messages = [{"role": "user", "content": "Task"}]
        injection = PlanInjection("thought", "Find the cup")
        expected = "This plan may be helpful to complete the task:\nFind the cup\nThought: "
        self.assertEqual(injection.thought_prefix, expected)
        self.assertEqual(model.continue_assistant(messages, injection.thought_prefix), expected)
        with patch("toolkit.models.base.asyncio.to_thread", side_effect=run_in_thread) as dispatch:
            self.assertEqual(await model.async_continue_assistant(messages, injection.thought_prefix), expected)
            self.assertEqual(await model.async_call(messages), "Task")
            await model.aclose()
            self.assertEqual(dispatch.await_count, 3)
        self.assertEqual(model.usage_metadata()["requests"], 3)
        self.assertTrue(model.closed)

    async def test_metered_model_reports_generic_usage_and_wraps_sync_and_async_failures(self):
        settings = {**DEFAULT_CONFIG["executor"], "model_name": "fake-model", "request_max_retries": 0}
        reply = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))], model="reported-model",
            usage=SimpleNamespace(total_tokens=4),
        )
        error = model_api.openai.APIConnectionError(
            message="provider details", request=httpx.Request("POST", "http://model.test/v1"),
        )
        async_client = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=AsyncMock(side_effect=error))),
            close=AsyncMock(),
        )
        with (patch.object(model_api.openai, "OpenAI") as sync_factory,
              patch.object(model_api.openai, "AsyncOpenAI", return_value=async_client)):
            model = model_api.MeteredChatModel(settings)
            create = sync_factory.return_value.chat.completions.create
            create.return_value = reply
            self.assertEqual(model([{"role": "user", "content": "check"}]), "ok")
            self.assertEqual(model.usage_metadata(), {
                "requests": 1, "responses": 1, "usage_responses": 1,
                "usage": {"total_tokens": 4}, "response_models": ["reported-model"],
            })
            create.side_effect = error
            with self.assertRaises(model_api.ModelRequestFailed) as synchronous:
                model([])
            with self.assertRaises(model_api.ModelRequestFailed) as asynchronous:
                await model.async_call([])
            for failure in (synchronous.exception, asynchronous.exception):
                self.assertEqual(failure.code, "request_error")
                self.assertNotIn("provider details", str(failure))
            self.assertEqual(model.usage_metadata()["requests"], 3)
            self.assertEqual(model.usage_metadata()["responses"], 1)
            await model.aclose()
            sync_factory.return_value.close.assert_called_once()
            async_client.close.assert_awaited_once()
