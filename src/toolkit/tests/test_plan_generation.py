import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from toolkit.planning import generation
from toolkit.utils.files import read_jsonl, write_jsonl


OPTIONS = {
    "benchmark": "alfworld", "api_base": "http://model.test", "api_key": "test-key",
    "model": "fake-model", "max_tokens": 256, "max_retries": 0, "max_concurrency": 2,
}


def response(content, finish_reason="stop"):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content), finish_reason=finish_reason)],
        model="fake-model", usage=SimpleNamespace(model_dump=lambda: {"total_tokens": 5}),
    )


class PlanGenerationTest(unittest.IsolatedAsyncioTestCase):
    async def test_reasoning_controls_are_saved_only_when_sent(self):
        for thinking, effort in ((None, None), ("disabled", None), (None, "none")):
            with (self.subTest(thinking=thinking, reasoning_effort=effort),
                  tempfile.TemporaryDirectory() as directory,
                  patch.object(generation, "AsyncChatClient") as factory):
                client = factory.return_value.__aenter__.return_value
                client.complete = AsyncMock(return_value=response("Search."))
                output = Path(directory) / "plans.jsonl"
                rows = [{"id": 1, "task": "Find the lamp."}]
                await generation.generate_plans(rows, output, **OPTIONS, thinking=thinking, reasoning_effort=effort)
                request = client.complete.await_args.kwargs
                if thinking is None:
                    self.assertNotIn("extra_body", request)
                else:
                    self.assertEqual(request["extra_body"], {"thinking": {"type": thinking}})
                if effort is None:
                    self.assertNotIn("reasoning_effort", request)
                else:
                    self.assertEqual(request["reasoning_effort"], effort)
                saved = json.loads(output.with_suffix(".jsonl.meta").read_text())["request"]
                self.assertEqual(saved.get("reasoning_effort"), effort)
                await generation.generate_plans(rows, output, **OPTIONS, thinking=thinking, reasoning_effort=effort)
                client.complete.assert_awaited_once()
                with self.assertRaisesRegex(ValueError, "Resume settings differ"):
                    await generation.generate_plans(rows, output, **OPTIONS, thinking=thinking, reasoning_effort="high")

    async def test_missing_model_fails_before_calling_client(self):
        with patch.object(generation, "AsyncChatClient") as factory:
            with self.assertRaisesRegex(ValueError, "Planner model_name is required"):
                await generation.generate_plans([], "unused.jsonl", benchmark="alfworld", max_tokens=256,
                                                 model=None)
            factory.assert_not_called()

    async def test_connection_defaults_and_explicit_recipe_overrides(self):
        for connection in ({}, {"api_base": "http://model.test/v1", "api_key": "configured-key"}):
            with (self.subTest(connection=connection),
                  tempfile.TemporaryDirectory() as directory,
                  patch.object(generation, "AsyncChatClient") as factory):
                factory.return_value.__aenter__.return_value.complete = AsyncMock(return_value=response("Search."))
                output = Path(directory) / "plans.jsonl"
                await generation.generate_plans(
                    [{"id": 1, "task": "Find the lamp."}], output,
                    benchmark="alfworld", model="fake-model", max_tokens=256, **connection,
                )
                expected = {**generation.DEFAULTS, **connection}
                factory.assert_called_once_with(
                    base_url=expected["api_base"], api_key=expected["api_key"], timeout=expected["timeout"],
                    max_concurrency=expected["max_concurrency"],
                )
                settings = json.loads(output.with_suffix(".jsonl.meta").read_text())
                self.assertEqual(settings["api_base"], expected["api_base"])
                self.assertNotIn("api_key", settings)
                self.assertNotIn("configured-key", json.dumps(settings))

    async def test_truncated_batch_preserves_success_and_resumes_only_pending_tasks(self):
        rows = [{"id": 1, "task": "Find the lamp."}, {"id": 2, "task": "Find the key."}]
        with (tempfile.TemporaryDirectory() as directory,
              patch.object(generation, "AsyncChatClient") as factory):
            tasks = Path(directory) / "tasks.jsonl"
            plans = Path(directory) / "plans.jsonl"
            write_jsonl(tasks, rows)
            client = factory.return_value.__aenter__.return_value
            client.complete = AsyncMock(side_effect=[
                response("<plan>Search the desk.</plan>"), response("Incomplete", "length"),
            ])
            with self.assertRaises(generation.PlannerOutputTruncated):
                await generation.generate_plans(tasks, plans, **OPTIONS)
            self.assertEqual(client.complete.await_count, 2)
            self.assertEqual(read_jsonl(plans)[0]["usage"], {"total_tokens": 5})
            settings = json.loads((plans.parent / "plans.jsonl.meta").read_text())
            self.assertEqual(settings["max_concurrency"], 2)
            self.assertNotIn(OPTIONS["api_key"], json.dumps(settings))

            client.complete = AsyncMock(return_value=response("Search the table."))
            records = await generation.generate_plans(tasks, plans, **OPTIONS)
            client.complete.assert_awaited_once()
            self.assertIn(rows[1]["task"], client.complete.await_args.kwargs["messages"][0]["content"])
            self.assertEqual([row["id"] for row in records], [1, 2])
            self.assertEqual(records[1]["plan"], records[1]["response"])

            client.complete.reset_mock()
            self.assertEqual(await generation.generate_plans(tasks, plans, **OPTIONS), records)
            client.complete.assert_not_awaited()

    async def test_retries_malformed_responses_with_the_same_prompt(self):
        with (tempfile.TemporaryDirectory() as directory,
              patch.object(generation, "AsyncChatClient") as factory,
              patch.object(generation.asyncio, "sleep", new_callable=AsyncMock) as sleep):
            client = factory.return_value.__aenter__.return_value
            client.complete = AsyncMock(side_effect=[
                SimpleNamespace(choices=[]), response("<plan> </plan>"), response("<plan>Find the lamp.</plan>"),
            ])
            plans = await generation.generate_plans(
                [{"id": 1, "task": "Find the lamp."}], Path(directory) / "plans.jsonl",
                **{**OPTIONS, "max_retries": 2},
            )
            self.assertEqual(plans[0]["plan"], "Find the lamp.")
            self.assertEqual(client.complete.await_count, 3)
            self.assertEqual(sleep.await_count, 2)
            self.assertTrue(all(call == client.complete.await_args for call in client.complete.await_args_list))

    async def test_resume_rejects_untracked_outputs_or_changed_settings_and_tasks(self):
        rows = [{"id": 1, "task": "Find the lamp."}]
        with (tempfile.TemporaryDirectory() as directory,
              patch.object(generation, "AsyncChatClient") as factory):
            plans = Path(directory) / "plans.jsonl"
            write_jsonl(plans, [{**rows[0], "plan": "An existing plan."}])
            with self.assertRaisesRegex(ValueError, "no settings record"):
                await generation.generate_plans(rows, plans, **OPTIONS)
            factory.assert_not_called()

            plans.unlink()
            factory.return_value.__aenter__.return_value.complete = AsyncMock(return_value=response("Search."))
            await generation.generate_plans(rows, plans, **OPTIONS)
            saved = plans.read_bytes()
            factory.reset_mock()
            with self.assertRaises(ValueError):
                await generation.generate_plans(rows, plans, **{**OPTIONS, "model": "other-model"})
            with self.assertRaisesRegex(ValueError, "different tasks"):
                await generation.generate_plans([{"id": 1, "task": "Find the key."}], plans, **OPTIONS)
            factory.assert_not_called()
            self.assertEqual(plans.read_bytes(), saved)
